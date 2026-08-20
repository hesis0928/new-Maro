#include "MaroPump.h"

#include <cmath>
#include <cstdint>
#include <vector>

#include <maya/MAngle.h>
#include <maya/MDagPath.h>
#include <maya/MDistance.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MFnMesh.h>
#include <maya/MGlobal.h>
#include <maya/MIntArray.h>
#include <maya/MItDependencyNodes.h>
#include <maya/MMatrix.h>
#include <maya/MPlug.h>
#include <maya/MPlugArray.h>
#include <maya/MPoint.h>
#include <maya/MPointArray.h>
#include <maya/MQuaternion.h>
#include <maya/MTimerMessage.h>
#include <maya/MTransformationMatrix.h>
#include <maya/MVector.h>

#include "maro_lidar/RayPattern.h"
#include "maro_lidar/ScanEngine.h"

#include "MaroAxisNode.h"
#include "MaroDiag.h"
#include "MaroLidarNode.h"
#include "MaroRosRuntime.h"

namespace maro {

MCallbackId MaroPump::s_timerId = 0;
MaroRosRuntime* MaroPump::s_runtime = nullptr;
std::atomic<std::uint64_t> MaroPump::s_collected{0};

namespace {

constexpr float kPumpIntervalSeconds = 1.0f / 30.0f;

// Maya의 현재 선형 단위를 미터 배율로 바꾼다.
// 하드코딩하면 사용자가 단위를 바꿨을 때 로봇이 100배로 나온다.
SceneUnit currentSceneUnit() {
    SceneUnit unit;
    unit.metersPerMayaUnit = MDistance(1.0, MDistance::internalUnit())
                                 .asMeters();
    return unit;
}

AxisConvention conventionOf(const MFnDependencyNode& axisFn) {
    AxisConvention conv;
    const short axisIndex =
        axisFn.findPlug(MaroAxisNode::aConventionAxis, false).asShort();
    conv.axis = (axisIndex == 0) ? LocalAxis::X
                                 : ((axisIndex == 2) ? LocalAxis::Z : LocalAxis::Y);
    conv.invert = axisFn.findPlug(MaroAxisNode::aConventionInvert, false).asBool();
    return conv;
}

}  // namespace

MStatus MaroPump::start(MaroRosRuntime& runtime) {
    if (s_timerId != 0) return MS::kSuccess;

    s_runtime = &runtime;
    s_collected.store(0);

    MStatus status;
    s_timerId = MTimerMessage::addTimerCallback(kPumpIntervalSeconds, onTimer,
                                                nullptr, &status);
    if (!status) {
        s_runtime = nullptr;
        s_timerId = 0;
    }
    return status;
}

MStatus MaroPump::stop() {
    if (s_timerId != 0) {
        MMessage::removeCallback(s_timerId);
        s_timerId = 0;
    }
    s_runtime = nullptr;
    return MS::kSuccess;
}

bool MaroPump::isRunning() { return s_timerId != 0; }

std::uint64_t MaroPump::collectedSampleCount() { return s_collected.load(); }

void MaroPump::onTimer(float, float, void*) {
    // Maya 콜백이다. 예외가 새면 Maya가 죽는다. 이 타이머는 항상 메인
    // 스레드에서 불리므로(MTimerMessage 콜백) compute()류의 워커 스레드
    // 제약이 없다 -- 리뷰 Finding I3.
    //
    // 그런데도 여기서 채울 수 있는 컨텍스트는 제한적이다: collectSamples()는
    // 씬의 모든 maroAxis를 순회하며 발행하는데, 예외가 나면 그 루프 상태(몇
    // 번째 축을 보던 중이었는지)는 이미 잃은 뒤다 -- 특정 축 인스턴스를
    // 지목하려면 collectSamples() 내부에서 축 하나하나를 따로 try/catch로
    // 감싸는 구조 변경이 필요한데, 그건 지금 실패 하나로 이 틱의 발행
    // 전체를 중단하는 현재 동작을 "한 축의 실패가 나머지 축의 발행을 막지
    // 않는다"로 바꾸는 별개의 행동 변화라 이 배치의 범위를 넘는다. 대신
    // nodeType만 채운다 -- "어떤 노드 타입을 순회하다 터졌는지"만으로도
    // 컨텍스트 없음보다는 낫다.
    try {
        if (s_runtime == nullptr) return;
        collectSamples(*s_runtime);
        // 같은 try 안이다 -- LiDAR 캡처가 던져도 Maya 콜백 경계를 넘지 않고
        // 아래 catch가 잡는다.
        collectLidarScans(*s_runtime);
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroPump.onTimer.Exception",
                              MString("Maro: pump tick failed: ") + e.what(),
                              maro::onfix::capture("maroAxis", "", ""));
    } catch (...) {
        maro::BoadMaro::error("MaroPump.onTimer.UnknownException",
                              "Maro: pump tick failed with unknown error.",
                              maro::onfix::capture("maroAxis", "", ""));
    }
}

void MaroPump::collectSamples(MaroRosRuntime& runtime) {
    const SceneUnit unit = currentSceneUnit();

    for (MItDependencyNodes it(MFn::kPluginLocatorNode); !it.isDone(); it.next()) {
        MFnDependencyNode axisFn(it.thisNode());
        if (axisFn.typeId() != MaroAxisNode::id) continue;
        if (!axisFn.findPlug(MaroAxisNode::aEnabled, false).asBool()) continue;

        const MString joint =
            axisFn.findPlug(MaroAxisNode::aJointName, false).asString();
        if (joint.length() == 0) continue;   // 이름 없는 축은 발행하지 않는다

        AxisSample sample;
        sample.jointName = joint.asChar();
        // aOutValue는 MFnUnitAttribute::kAngle이다. asDouble()로 읽으면
        // Maya가 UI 각도 단위(기본 도)로 변환한 값을 돌려줄 수 있어
        // 라디안이 필요한 이 파이프라인에서 값이 어긋난다. asAngle()로
        // 받아 asRadians()로 명시해야 항상 라디안이다.
        sample.value =
            axisFn.findPlug(MaroAxisNode::aOutValue, false).asMAngle().asRadians();
        sample.convention = conventionOf(axisFn);
        sample.unit = unit;

        if (!std::isfinite(sample.value)) continue;

        // /tf는 이 축이 구동하는 실제 Maya 오브젝트의 월드 변환이 있어야
        // 의미가 있다. targetObject는 message 연결이라(데이터를 나르지
        // 않는다) MaroBindAxisCommand::doIt과 같은 방식으로만 오브젝트를
        // 얻을 수 있다 -- connectedTo(asDst=true)로 이 축에 연결된 소스
        // 쪽(바인딩된 트랜스폼)을 본다. 바인딩이 없으면 이 축은 씬 안의
        // 어떤 위치도 대표하지 않으므로, 이름 없는 축과 같은 이유로
        // 건너뛴다 -- 원점(identity)을 발행하는 것보다는 아예 발행하지
        // 않는 쪽이 낫다 (이 태스크가 고치는 바로 그 문제).
        MPlugArray targetSources;
        axisFn.findPlug(MaroAxisNode::aTargetObject, false)
            .connectedTo(targetSources, true, false);
        if (targetSources.length() == 0) continue;

        // MFnDagNode를 MObject로 바로 생성하면 경로 컨텍스트를 잃어
        // parentCount()/월드 행렬 조회가 조용히 틀어진다 -- 이미
        // MaroBindAxisCommand::doIt(MaroCommands.cpp)과
        // MaroDeleteWatcher.cpp에서 같은 함정에 걸렸다. MDagPath::getAPathTo로
        // 실제 경로를 얻어야 inclusiveMatrix()가 조상 체인을 포함한 진짜
        // 월드 행렬을 돌려준다.
        MDagPath targetPath;
        if (MDagPath::getAPathTo(targetSources[0].node(), targetPath) !=
            MS::kSuccess) {
            continue;
        }

        // /tf 프레임은 전부 공통 루트("world") 기준으로 발행되므로(
        // MaroRosRuntime::drainAndPublish 참고) 로컬이 아니라 월드 행렬을
        // 쓴다. 스케일/기울임은 이 파이프라인이 다루지 않으므로 kTransform
        // 공간으로 평행이동을, rotation()으로 회전만 뽑아낸다 -- 둘 다
        // Maya가 순수 행렬에서 피벗 없이 성분을 복원하는 표준 경로다.
        const MMatrix worldMatrix = targetPath.inclusiveMatrix();
        MTransformationMatrix xform(worldMatrix);

        MStatus translationStatus;
        const MVector t =
            xform.getTranslation(MSpace::kTransform, &translationStatus);
        const MQuaternion q = xform.rotation();

        // 이 값들은 백그라운드 스레드를 거쳐 그대로 ROS 2 와이어로 나간다.
        // NaN/inf가 거기까지 새지 않도록 여기서 막는다 (sample.value에 이미
        // 적용한 것과 같은 가드).
        const Vec3 position{t.x, t.y, t.z};
        const Quat rotation{q.x, q.y, q.z, q.w};
        if (!translationStatus || !isFinite(position) || !isFinite(rotation)) {
            continue;
        }

        sample.position = position;
        sample.rotation = rotation;

        runtime.publishQueue().push(std::move(sample));
        s_collected.fetch_add(1, std::memory_order_relaxed);
    }
}

namespace {

// meshNode는 targetMeshes에 연결된 노드다. 사용자는 보통 트랜스폼의
// .message를 잇는다(test_lidar_node.py가 이미 그 관례로 바인딩한다) --
// MFnMesh는 트랜스폼을 받지 않으므로 여기서 셰이프까지 내려간다.
//
// MObject가 아니라 MDagPath로 함수 세트를 만드는 것이 중요하다:
// MSpace::kWorld는 경로 컨텍스트가 있어야 조상 체인을 포함한 진짜 월드
// 좌표를 준다 -- collectSamples()가 MDagPath::getAPathTo를 쓰는 것과 같은
// 이유이고, 이 프로젝트가 이미 세 번 걸린 함정이다.
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
// 데이터블록에 빈 원소를 만들어 넣는다(MPlug.h의 설명) -- 매 틱 30Hz로
// 도는 캡처 경로가 씬을 조용히 바꾸면 안 된다. 물리 인덱스는 이미 있는
// 원소만 본다. (evaluateNumElements()는 compute() 안에서는 금지지만 여기는
// 메인 스레드 타이머 콜백이라 허용된다.)
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

void MaroPump::collectLidarScans(MaroRosRuntime& runtime) {
    const SceneUnit unit = currentSceneUnit();

    for (MItDependencyNodes it(MFn::kPluginLocatorNode); !it.isDone(); it.next()) {
        MFnDependencyNode lidarFn(it.thisNode());
        if (lidarFn.typeId() != MaroLidarNode::id) continue;
        if (!lidarFn.findPlug(MaroLidarNode::aEnabled, false).asBool()) continue;

        MObject meshNode;
        if (!firstConnectedMesh(lidarFn.findPlug(MaroLidarNode::aTargetMeshes, false),
                                meshNode)) {
            continue;
        }

        std::vector<float> vertices;
        std::vector<std::uint32_t> indices;
        if (!extractMeshBuffers(meshNode, vertices, indices)) continue;

        // 워킹 스켈레톤은 더티 체크를 하지 않는다 -- 매 스캔마다 새로 만든다
        // (§범위 밖). 지역 변수라 이 반복이 끝날 때 소멸자가 Embree
        // 씬/디바이스를 반납한다.
        maro::lidar::ScanEngine engine;
        if (!engine.setMesh(vertices, indices)) continue;

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
        const MString frameId = lidarFn.findPlug(MaroLidarNode::aFrameId, false).asString();

        const auto localDirections = maro::lidar::computeRayDirections(
            verticalSamples, verticalMinAngle, verticalMaxAngle, horizontalSamples,
            horizontalMinAngle, horizontalMaxAngle);

        MDagPath lidarPath;
        if (MDagPath::getAPathTo(it.thisNode(), lidarPath) != MS::kSuccess) continue;
        const MMatrix worldMatrix = lidarPath.inclusiveMatrix();
        const MVector worldOrigin(MPoint(0, 0, 0) * worldMatrix);

        const Vec3 origin{worldOrigin.x, worldOrigin.y, worldOrigin.z};
        // 이 값들은 백그라운드 스레드를 거쳐 그대로 ROS 2 와이어로 나간다.
        // collectSamples()가 위치/회전에 거는 것과 같은 가드다.
        if (!isFinite(origin)) continue;

        LidarSample sample;
        sample.frameId = frameId.asChar();
        sample.unit = unit;

        // 방향 벡터에서 평행이동 성분을 제거하기 위해 함께 뺄 기준점 --
        // 점이 아니라 벡터를 옮기는 표준 트릭(영벡터를 같은 행렬로 옮겨
        // 빼면 평행이동이 상쇄된다). MVector와 MMatrix의 곱이 평행이동을
        // 포함하든 안 하든 결과가 같으므로 그 관례에 의존하지 않는다.
        // 레이마다 다시 계산할 이유가 없어 루프 밖에서 한 번만 구한다.
        const MVector directionBias = MVector(0, 0, 0) * worldMatrix;

        for (const Vec3& localDir : localDirections) {
            const MVector localVec(localDir.x, localDir.y, localDir.z);
            // normal()은 행렬의 스케일을 걷어내 rangeMin/rangeMax가 실제
            // 거리 단위로 남게 한다 -- ScanEngine이 origin + direction * t로
            // 충돌점을 만들기 때문에 방향은 반드시 단위 벡터여야 한다.
            const MVector worldDir = (localVec * worldMatrix - directionBias).normal();

            const maro::lidar::RayHit hit = engine.castRay(
                origin, Vec3{worldDir.x, worldDir.y, worldDir.z}, rangeMin, rangeMax);
            if (hit.hit && isFinite(hit.position)) sample.points.push_back(hit.position);
        }

        if (!sample.points.empty()) {
            runtime.lidarQueue().push(std::move(sample));
        }
    }
}

}  // namespace maro
