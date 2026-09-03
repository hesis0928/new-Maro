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

namespace {

// targetMeshes(메시지 배열)에 연결된 소스 노드를 전부 모은다.
// elementByLogicalIndex(0)이 아니라 evaluateNumElements()+
// elementByPhysicalIndex()를 쓴다: 논리 인덱스 접근은 없는 원소를 요구하면
// 데이터블록에 빈 원소를 만들어 넣는다(firstConnectedMesh가 쓰던 것과
// 같은 이유로 유지).
std::vector<MObject> allConnectedMeshes(MPlug meshesPlug) {
    std::vector<MObject> meshes;
    const unsigned int count = meshesPlug.evaluateNumElements();
    for (unsigned int i = 0; i < count; ++i) {
        MPlugArray sources;
        meshesPlug.elementByPhysicalIndex(i).connectedTo(sources, true, false);
        if (sources.length() > 0) meshes.push_back(sources[0].node());
    }
    return meshes;
}

}  // namespace

LidarScanResult scanLidarNode(const MObject& lidarNode, maro::lidar::ScanEngine& engine,
                               const SceneUnit& unit, std::vector<Vec3>& outPoints,
                               LidarGeometry* outGeometry) {
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

    if (!std::isfinite(verticalMinAngle) || !std::isfinite(verticalMaxAngle) ||
        !std::isfinite(horizontalMinAngle) || !std::isfinite(horizontalMaxAngle) ||
        !std::isfinite(rangeMinMaya) || !std::isfinite(rangeMaxMaya) ||
        !std::isfinite(offsetTranslateXMeters) || !std::isfinite(offsetTranslateYMeters) ||
        !std::isfinite(offsetTranslateZMeters) || !std::isfinite(offsetRotateX) ||
        !std::isfinite(offsetRotateY) || !std::isfinite(offsetRotateZ)) {
        return LidarScanResult::kInvalidConfig;
    }
    // Embree가 문서로 요구하는 전제: 0 <= tnear <= tfar.
    if (rangeMinMaya < 0.0 || rangeMaxMaya < rangeMinMaya) return LidarScanResult::kInvalidConfig;

    // [다중 메쉬 지원] 유효 월드 행렬/원점 계산을 타겟 메쉬 확인보다
    // 앞으로 옮겼다 -- 이 값들은 타겟 메쉬 존재 여부와 무관하게 계산
    // 가능해야, 다음 태스크의 조회 커맨드가 kNoTargetMesh/
    // kMeshExtractFailed/kRayCountExceeded에서도 이 지오메트리를 돌려줄
    // 수 있다(설계 스펙 §3.4/§8).
    MDagPath lidarPath;
    if (MDagPath::getAPathTo(lidarNode, lidarPath) != MS::kSuccess) {
        return LidarScanResult::kInvalidConfig;
    }
    const MMatrix worldMatrix = lidarPath.inclusiveMatrix();

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

    if (outGeometry) {
        outGeometry->rangeMinMaya = rangeMinMaya;
        outGeometry->rangeMaxMaya = rangeMaxMaya;
        outGeometry->verticalMinAngle = verticalMinAngle;
        outGeometry->verticalMaxAngle = verticalMaxAngle;
        outGeometry->horizontalMinAngle = horizontalMinAngle;
        outGeometry->horizontalMaxAngle = horizontalMaxAngle;
        outGeometry->effectiveWorldMatrix = effectiveWorldMatrix;
    }

    const long long rayCount = static_cast<long long>(verticalSamples) *
                               static_cast<long long>(horizontalSamples);
    if (rayCount > kMaxRaysPerScan) return LidarScanResult::kRayCountExceeded;

    // [다중 메쉬 지원] targetMeshes[]에 연결된 것 전부를 모아 하나의
    // 버퍼로 병합한다(설계 스펙 §3.2) -- 첫 번째 것만 보던 기존 동작을
    // 대체한다. 일부 메쉬만 추출에 실패해도 나머지로 계속 진행한다(§3.3).
    const std::vector<MObject> meshNodes =
        allConnectedMeshes(lidarFn.findPlug(MaroLidarNode::aTargetMeshes, false));
    if (meshNodes.empty()) return LidarScanResult::kNoTargetMesh;

    std::vector<float> mergedVertices;
    std::vector<std::uint32_t> mergedIndices;
    bool anyExtracted = false;
    for (const MObject& meshNode : meshNodes) {
        std::vector<float> vertices;
        std::vector<std::uint32_t> indices;
        if (!extractMeshBuffers(meshNode, vertices, indices)) continue;
        const std::uint32_t vertexOffset =
            static_cast<std::uint32_t>(mergedVertices.size() / 3);
        mergedVertices.insert(mergedVertices.end(), vertices.begin(), vertices.end());
        for (std::uint32_t index : indices) mergedIndices.push_back(index + vertexOffset);
        anyExtracted = true;
    }
    if (!anyExtracted) return LidarScanResult::kMeshExtractFailed;
    if (!engine.setMesh(mergedVertices, mergedIndices)) return LidarScanResult::kMeshExtractFailed;

    const auto localDirections = maro::lidar::computeRayDirections(
        verticalSamples, verticalMinAngle, verticalMaxAngle, horizontalSamples,
        horizontalMinAngle, horizontalMaxAngle);

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
