#include "MaroLidarScan.h"

#include <cmath>
#include <cstdint>

#include <maya/MAngle.h>
#include <maya/MDagPath.h>
#include <maya/MDistance.h>
#include <maya/MEulerRotation.h>
#include <maya/MFnDagNode.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MFnMesh.h>
#include <maya/MIntArray.h>
#include <maya/MMatrix.h>
#include <maya/MPlug.h>
#include <maya/MPlugArray.h>
#include <maya/MPoint.h>
#include <maya/MPointArray.h>
#include <maya/MTransformationMatrix.h>
#include <maya/MVector.h>

#include "maro_lidar/RayPattern.h"
#include "maro_lidar/ScanEngine.h"

#include "MaroLidarNode.h"

namespace maro {

SceneUnit currentSceneUnit() {
    SceneUnit unit;
    unit.metersPerMayaUnit = MDistance(1.0, MDistance::internalUnit()).asMeters();
    return unit;
}

namespace {

// meshNode는 targetMeshes에 연결된 노드다. 사용자는 보통 트랜스폼의
// .message를 잇는다(tests/maya/test_lidar_node.py와 python/maroDagMenu.py가
// 이미 그 관례로 바인딩한다) -- MFnMesh는 트랜스폼을 받지 않으므로 여기서
// 셰이프까지 내려간다.
//
// [최종 리뷰 Minor-7] MObject가 아니라 MDagPath로 함수 세트를 만드는 것이
// 중요하다: MSpace::kWorld는 경로 컨텍스트가 있어야 조상 체인을 포함한 진짜
// 월드 좌표를 준다. **이 프로젝트가 이미 여러 번 걸린 함정이다** --
// MaroCommands.cpp의 MaroBindAxisCommand::doIt, MaroDeleteWatcher.cpp,
// MaroPump::collectSamples가 전부 같은 이유로 MDagPath::getAPathTo를 먼저
// 부른다. 맨 MObject로 만든 함수 세트는 에러를 내지 않고 **조용히 틀린 값**을
// 준다는 것이 이 함정의 성질이다.
bool extractMeshBuffers(const MObject& meshNode, std::vector<float>& vertices,
                        std::vector<std::uint32_t>& indices) {
    MDagPath meshPath;
    if (MDagPath::getAPathTo(meshNode, meshPath) != MS::kSuccess) return false;
    if (!meshPath.hasFn(MFn::kMesh)) {
        // [최종 리뷰 C-1 검증 중 실측으로 발견] 예전에는 여기서
        // `meshPath.extendToShape()`만 불렀다. 그 API는 **셰이프가 정확히
        // 하나일 때만** 성공한다 -- 트랜스폼 밑에 셰이프가 둘 이상이면
        // 실패를 돌려준다.
        //
        // 그리고 이 플러그인의 주력 생성 경로가 정확히 그 상황을 만든다:
        // python/maroDagMenu.py의 `_onLidarMenuItemClicked()`은 클릭한 메쉬
        // **트랜스폼 자신**을 targetMeshes[0]로 잇고, 동시에 maroLidar
        // 로케이터 셰이프를 `cmds.parent(..., shape=True)`로 그 **같은
        // 트랜스폼** 밑에 얹는다. 그 순간 그 트랜스폼의 셰이프는 둘(mesh +
        // maroLidar)이 되고, extendToShape()는 실패하며, 스캔은 매번
        // kMeshExtractFailed로 끝난다 -- 즉 마킹 메뉴로 만든 LiDAR는 자기가
        // 올라탄 메쉬를 **원리적으로 한 번도 못 읽었다**. (C-1의 rangeMin
        // 수정만으로는 이 경로가 여전히 0점이었고, 그 검증 테스트가 이
        // 두 번째 결함을 드러냈다.)
        //
        // 그래서 직속 셰이프들을 직접 훑어 첫 번째 진짜 메쉬를 고른다.
        // intermediate object(디포머 히스토리의 원본 셰이프)는 건너뛴다 --
        // 그것은 화면에 그려지지 않는 셰이프라 레이캐스트 대상이 아니고,
        // 디포머가 걸린 메쉬에서는 그것까지 세어 셰이프가 둘이 되므로 예전
        // extendToShape() 경로가 조용히 실패하던 또 다른 흔한 경우이기도 하다.
        unsigned int shapeCount = 0;
        meshPath.numberOfShapesDirectlyBelow(shapeCount);
        bool foundMesh = false;
        for (unsigned int i = 0; i < shapeCount; ++i) {
            MDagPath candidate = meshPath;
            if (candidate.extendToShapeDirectlyBelow(i) != MS::kSuccess) continue;
            if (!candidate.hasFn(MFn::kMesh)) continue;
            MStatus dagStatus;
            MFnDagNode candidateFn(candidate, &dagStatus);
            if (dagStatus && candidateFn.isIntermediateObject()) continue;
            meshPath = candidate;
            foundMesh = true;
            break;
        }
        if (!foundMesh) return false;
    }

    MStatus status;
    MFnMesh meshFn(meshPath, &status);
    if (!status) return false;

    MPointArray points;
    if (meshFn.getPoints(points, MSpace::kWorld) != MS::kSuccess) return false;
    vertices.clear();
    vertices.reserve(static_cast<std::size_t>(points.length()) * 3);
    for (unsigned int i = 0; i < points.length(); ++i) {
        vertices.push_back(static_cast<float>(points[i].x));
        vertices.push_back(static_cast<float>(points[i].y));
        vertices.push_back(static_cast<float>(points[i].z));
    }

    MIntArray triangleCounts, triangleVertices;
    if (meshFn.getTriangles(triangleCounts, triangleVertices) != MS::kSuccess) return false;
    indices.clear();
    indices.reserve(static_cast<std::size_t>(triangleVertices.length()));
    for (unsigned int i = 0; i < triangleVertices.length(); ++i) {
        indices.push_back(static_cast<std::uint32_t>(triangleVertices[i]));
    }
    return true;
}

// targetMeshes(메시지 배열)에서 처음으로 연결된 소스 노드를 찾는다.
// elementByLogicalIndex(0)가 아니라 evaluateNumElements()+
// elementByPhysicalIndex()를 쓴다: 논리 인덱스 접근은 없는 원소를 요구하면
// 데이터블록에 빈 원소를 만들어 넣는다.
bool firstConnectedMesh(MPlug meshesPlug, MObject& meshNode) {
    const unsigned int count = meshesPlug.evaluateNumElements();
    for (unsigned int i = 0; i < count; ++i) {
        MPlugArray sources;
        meshesPlug.elementByPhysicalIndex(i).connectedTo(sources, true, false);
        if (sources.length() > 0) {
            meshNode = sources[0].node();
            return true;
        }
    }
    return false;
}

}  // namespace

LidarScanResult scanLidarNode(const MObject& lidarNode, maro::lidar::ScanEngine& engine,
                               const SceneUnit& unit, std::vector<Vec3>& outPoints) {
    outPoints.clear();
    MFnDependencyNode lidarFn(lidarNode);

    const int verticalSamples =
        lidarFn.findPlug(MaroLidarNode::aVerticalSamples, false).asInt();
    const double verticalMinAngle =
        lidarFn.findPlug(MaroLidarNode::aVerticalMinAngle, false).asMAngle().asRadians();
    const double verticalMaxAngle =
        lidarFn.findPlug(MaroLidarNode::aVerticalMaxAngle, false).asMAngle().asRadians();
    const int horizontalSamples =
        lidarFn.findPlug(MaroLidarNode::aHorizontalSamples, false).asInt();
    const double horizontalMinAngle =
        lidarFn.findPlug(MaroLidarNode::aHorizontalMinAngle, false).asMAngle().asRadians();
    const double horizontalMaxAngle =
        lidarFn.findPlug(MaroLidarNode::aHorizontalMaxAngle, false).asMAngle().asRadians();
    const double rangeMin = lidarFn.findPlug(MaroLidarNode::aRangeMin, false).asDouble();
    const double rangeMax = lidarFn.findPlug(MaroLidarNode::aRangeMax, false).asDouble();

    // rangeMin/rangeMax는 미터다. 레이캐스팅은 Maya 월드 단위에서 돈다 --
    // castRay에 넘긴 값이 그대로 ray.tnear/ray.tfar가 되기 때문이다.
    const double mayaPerMeter = 1.0 / unit.metersPerMayaUnit;
    const double rangeMinMaya = rangeMin * mayaPerMeter;
    const double rangeMaxMaya = rangeMax * mayaPerMeter;

    if (!std::isfinite(verticalMinAngle) || !std::isfinite(verticalMaxAngle) ||
        !std::isfinite(horizontalMinAngle) || !std::isfinite(horizontalMaxAngle) ||
        !std::isfinite(rangeMinMaya) || !std::isfinite(rangeMaxMaya)) {
        return LidarScanResult::kInvalidConfig;
    }
    // Embree가 문서로 요구하는 전제: 0 <= tnear <= tfar.
    if (rangeMinMaya < 0.0 || rangeMaxMaya < rangeMinMaya) return LidarScanResult::kInvalidConfig;

    const long long rayCount = static_cast<long long>(verticalSamples) *
                               static_cast<long long>(horizontalSamples);
    if (rayCount > kMaxRaysPerScan) return LidarScanResult::kRayCountExceeded;

    MObject meshNode;
    if (!firstConnectedMesh(lidarFn.findPlug(MaroLidarNode::aTargetMeshes, false), meshNode)) {
        return LidarScanResult::kNoTargetMesh;
    }

    std::vector<float> vertices;
    std::vector<std::uint32_t> indices;
    if (!extractMeshBuffers(meshNode, vertices, indices)) return LidarScanResult::kMeshExtractFailed;
    if (!engine.setMesh(vertices, indices)) return LidarScanResult::kMeshExtractFailed;

    const auto localDirections = maro::lidar::computeRayDirections(
        verticalSamples, verticalMinAngle, verticalMaxAngle, horizontalSamples,
        horizontalMinAngle, horizontalMaxAngle);

    MDagPath lidarPath;
    if (MDagPath::getAPathTo(lidarNode, lidarPath) != MS::kSuccess) {
        return LidarScanResult::kInvalidConfig;
    }
    // 마운트 지점(이 노드가 얹힌 트랜스폼)의 있는 그대로의 월드 행렬. 이
    // 노드는 전용 트랜스폼 없이 대상 오브젝트 트랜스폼에 직접 얹히므로
    // (이전 태스크의 검증된 설계 결정, 범위 밖), 실제 센서 원점이 이
    // 마운트 지점과 정확히 겹치는 경우는 현실에서 사실상 없다. 그 간극을
    // offsetTranslate/offsetRotate로 메운다: 로컬 오프셋 행렬을 먼저 만들고
    // (로컬 공간에서 오프셋 적용), 그 다음 마운트의 월드 행렬로 옮긴다
    // (오프셋된 행렬 * 마운트 월드 행렬). raw worldMatrix 자체는 그대로
    // 남겨 둔다 -- 원점/방향 계산에는 effectiveWorldMatrix만 쓴다.
    const MMatrix worldMatrix = lidarPath.inclusiveMatrix();

    const double offsetTranslateXMeters =
        lidarFn.findPlug(MaroLidarNode::aOffsetTranslateX, false).asDouble();
    const double offsetTranslateYMeters =
        lidarFn.findPlug(MaroLidarNode::aOffsetTranslateY, false).asDouble();
    const double offsetTranslateZMeters =
        lidarFn.findPlug(MaroLidarNode::aOffsetTranslateZ, false).asDouble();
    const double offsetRotateX =
        lidarFn.findPlug(MaroLidarNode::aOffsetRotateX, false).asMAngle().asRadians();
    const double offsetRotateY =
        lidarFn.findPlug(MaroLidarNode::aOffsetRotateY, false).asMAngle().asRadians();
    const double offsetRotateZ =
        lidarFn.findPlug(MaroLidarNode::aOffsetRotateZ, false).asMAngle().asRadians();

    // offsetTranslate*는 미터다 (rangeMin/rangeMax와 같은 규칙, 위 주석
    // 참고) -- 같은 mayaPerMeter로 Maya 단위로 바꿔야 아래 행렬 합성이
    // 같은 단위계 안에서 이뤄진다.
    MTransformationMatrix offsetXform;
    offsetXform.setTranslation(
        MVector(offsetTranslateXMeters * mayaPerMeter, offsetTranslateYMeters * mayaPerMeter,
                offsetTranslateZMeters * mayaPerMeter),
        MSpace::kTransform);
    offsetXform.rotateTo(MEulerRotation(offsetRotateX, offsetRotateY, offsetRotateZ));
    const MMatrix offsetMatrix = offsetXform.asMatrix();
    const MMatrix effectiveWorldMatrix = offsetMatrix * worldMatrix;

    const MVector worldOrigin(MPoint(0, 0, 0) * effectiveWorldMatrix);
    const Vec3 origin{worldOrigin.x, worldOrigin.y, worldOrigin.z};
    if (!isFinite(origin)) return LidarScanResult::kInvalidConfig;

    // 방향 벡터에서 평행이동 성분을 제거하기 위해 함께 뺄 기준점.
    const MVector directionBias = MVector(0, 0, 0) * effectiveWorldMatrix;

    for (const Vec3& localDir : localDirections) {
        const MVector localVec(localDir.x, localDir.y, localDir.z);
        const MVector worldDir = (localVec * effectiveWorldMatrix - directionBias).normal();
        const maro::lidar::RayHit hit =
            engine.castRay(origin, Vec3{worldDir.x, worldDir.y, worldDir.z}, rangeMinMaya, rangeMaxMaya);
        if (hit.hit && isFinite(hit.position)) outPoints.push_back(hit.position);
    }
    return LidarScanResult::kOk;
}

}  // namespace maro
