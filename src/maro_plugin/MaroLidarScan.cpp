#include "MaroLidarScan.h"

#include <cmath>
#include <cstdint>

#include <maya/MAngle.h>
#include <maya/MDagPath.h>
#include <maya/MDistance.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MFnMesh.h>
#include <maya/MIntArray.h>
#include <maya/MMatrix.h>
#include <maya/MPlug.h>
#include <maya/MPlugArray.h>
#include <maya/MPoint.h>
#include <maya/MPointArray.h>
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
// .message를 잇는다 -- MFnMesh는 트랜스폼을 받지 않으므로 여기서 셰이프까지
// 내려간다. MObject가 아니라 MDagPath로 함수 세트를 만드는 것이 중요하다:
// MSpace::kWorld는 경로 컨텍스트가 있어야 조상 체인을 포함한 진짜 월드
// 좌표를 준다.
bool extractMeshBuffers(const MObject& meshNode, std::vector<float>& vertices,
                        std::vector<std::uint32_t>& indices) {
    MDagPath meshPath;
    if (MDagPath::getAPathTo(meshNode, meshPath) != MS::kSuccess) return false;
    if (!meshPath.hasFn(MFn::kMesh)) {
        if (meshPath.extendToShape() != MS::kSuccess) return false;
        if (!meshPath.hasFn(MFn::kMesh)) return false;
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
    const MMatrix worldMatrix = lidarPath.inclusiveMatrix();
    const MVector worldOrigin(MPoint(0, 0, 0) * worldMatrix);
    const Vec3 origin{worldOrigin.x, worldOrigin.y, worldOrigin.z};
    if (!isFinite(origin)) return LidarScanResult::kInvalidConfig;

    // 방향 벡터에서 평행이동 성분을 제거하기 위해 함께 뺄 기준점.
    const MVector directionBias = MVector(0, 0, 0) * worldMatrix;

    for (const Vec3& localDir : localDirections) {
        const MVector localVec(localDir.x, localDir.y, localDir.z);
        const MVector worldDir = (localVec * worldMatrix - directionBias).normal();
        const maro::lidar::RayHit hit =
            engine.castRay(origin, Vec3{worldDir.x, worldDir.y, worldDir.z}, rangeMinMaya, rangeMaxMaya);
        if (hit.hit && isFinite(hit.position)) outPoints.push_back(hit.position);
    }
    return LidarScanResult::kOk;
}

}  // namespace maro
