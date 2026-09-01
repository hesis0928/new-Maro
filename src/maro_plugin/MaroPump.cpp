#include "MaroPump.h"

#include <chrono>
#include <cmath>
#include <cstdint>
#include <memory>
#include <vector>

#include <maya/MAngle.h>
#include <maya/MDagPath.h>
#include <maya/MDistance.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MFnMesh.h>
#include <maya/MFnPointArrayData.h>
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

#include "maro_lidar/Decimation.h"
#include "maro_lidar/ScanEngine.h"

#include "MaroAxisNode.h"
#include "MaroDiag.h"
#include "MaroLidarNode.h"
#include "MaroLidarScan.h"
#include "MaroPointCloudNode.h"
#include "MaroRosRuntime.h"

namespace maro {

MCallbackId MaroPump::s_timerId = 0;
MaroRosRuntime* MaroPump::s_runtime = nullptr;
std::atomic<std::uint64_t> MaroPump::s_collected{0};
std::unordered_map<unsigned int, MaroPump::LidarNodeState> MaroPump::s_lidarNodeState;
std::unique_ptr<maro::lidar::ScanEngine> MaroPump::s_scanEngine;

namespace {

constexpr float kPumpIntervalSeconds = 1.0f / 30.0f;

// aVisualize가 켜진 maroLidar가 매 틱 짝 maroPointCloud로 밀어 넣는 프리뷰
// 포인트 상한. 실제 스캔(runtime.lidarQueue()로 나가는 전체 포인트)에는
// 영향을 주지 않는다 -- 이건 순전히 뷰포트 프리뷰용 디시메이션이다.
constexpr std::size_t kMaxPreviewPoints = 4096;

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
    s_lidarNodeState.clear();

    // Embree 디바이스는 브리지가 사는 동안만 산다 (Finding I5). 여기서
    // 만들어 stop()에서 놓는 것이 이 클래스가 다른 상태를 다루는 방식과
    // 같고, 정적 소멸자에 rtcReleaseDevice를 맡기지 않는 유일한 방법이다.
    s_scanEngine = std::make_unique<maro::lidar::ScanEngine>();

    MStatus status;
    s_timerId = MTimerMessage::addTimerCallback(kPumpIntervalSeconds, onTimer,
                                                nullptr, &status);
    if (!status) {
        s_runtime = nullptr;
        s_timerId = 0;
        s_scanEngine.reset();
    }
    return status;
}

MStatus MaroPump::stop() {
    if (s_timerId != 0) {
        MMessage::removeCallback(s_timerId);
        s_timerId = 0;
    }
    s_runtime = nullptr;
    // 타이머 콜백을 뗀 뒤에 놓는다 -- 순서가 반대면 아직 도는 틱 하나가
    // 방금 반납한 Embree 디바이스를 만질 수 있다.
    s_scanEngine.reset();
    s_lidarNodeState.clear();
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
        // driveIsLinear가 이 틱에 어느 출력이 유효한지 알려준다 -- 스택을
        // 다시 훑지 않고 MaroAxisNode::compute()가 이미 판정해 둔 플래그
        // 하나만 읽는다(Task 3).
        if (axisFn.findPlug(MaroAxisNode::aDriveIsLinear, false).asBool()) {
            // aOutValueLinear는 MFnUnitAttribute::kDistance다.
            // asMDistance().asMeters()로 읽으면 씬의 내부 선형 단위(Maya는
            // 항상 센티미터)와 무관하게 항상 미터로 받는다 -- aOutValue를
            // asMAngle().asRadians()로 읽는 것과 같은 이유, 같은 관례다.
            sample.value = axisFn.findPlug(MaroAxisNode::aOutValueLinear, false)
                               .asMDistance()
                               .asMeters();
        } else {
            // aOutValue는 MFnUnitAttribute::kAngle이다. asDouble()로 읽으면
            // Maya가 UI 각도 단위(기본 도)로 변환한 값을 돌려줄 수 있어
            // 라디안이 필요한 이 파이프라인에서 값이 어긋난다. asAngle()로
            // 받아 asRadians()로 명시해야 항상 라디안이다.
            sample.value = axisFn.findPlug(MaroAxisNode::aOutValue, false)
                               .asMAngle()
                               .asRadians();
        }
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


void MaroPump::collectLidarScans(MaroRosRuntime& runtime) {
    if (!s_scanEngine) return;

    const SceneUnit unit = currentSceneUnit();

    for (auto stateIt = s_lidarNodeState.begin(); stateIt != s_lidarNodeState.end();) {
        if (!stateIt->second.handle.isAlive()) {
            stateIt = s_lidarNodeState.erase(stateIt);
        } else {
            ++stateIt;
        }
    }

    const auto tickNow = std::chrono::steady_clock::now();

    for (MItDependencyNodes it(MFn::kPluginLocatorNode); !it.isDone(); it.next()) {
        const MObject lidarObj = it.thisNode();
        MFnDependencyNode lidarFn(lidarObj);
        if (lidarFn.typeId() != MaroLidarNode::id) continue;
        if (!lidarFn.findPlug(MaroLidarNode::aEnabled, false).asBool()) continue;

        LidarNodeState& state = s_lidarNodeState[MObjectHandle::objectHashCode(lidarObj)];
        if (!state.handle.isValid() || state.handle != lidarObj) {
            state = LidarNodeState{};
            state.handle = MObjectHandle(lidarObj);
        }

        const double updateRate =
            lidarFn.findPlug(MaroLidarNode::aUpdateRate, false).asDouble();
        if (std::isfinite(updateRate) && updateRate > 0.0 && state.hasScanned) {
            const std::chrono::duration<double> sinceLast = tickNow - state.lastScan;
            if (sinceLast.count() < 1.0 / updateRate) continue;
        }

        std::vector<Vec3> points;
        const LidarScanResult result = scanLidarNode(lidarObj, *s_scanEngine, unit, points);

        if (result == LidarScanResult::kRayCountExceeded) {
            if (!state.warnedRayCap) {
                state.warnedRayCap = true;
                const int verticalSamples =
                    lidarFn.findPlug(MaroLidarNode::aVerticalSamples, false).asInt();
                const int horizontalSamples =
                    lidarFn.findPlug(MaroLidarNode::aHorizontalSamples, false).asInt();
                maro::BoadMaro::error(
                    "MaroPump.collectLidarScans.RayCountTooLarge",
                    MString("Maro: maroLidar '") + lidarFn.name() + "' asks for " +
                        verticalSamples + " x " + horizontalSamples +
                        " rays, over the per-tick cap of " +
                        static_cast<int>(kMaxRaysPerScan) +
                        ". The scan is skipped -- lower verticalSamples/"
                        "horizontalSamples.",
                    maro::onfix::capture("maroLidar", "verticalSamples", lidarFn.name()));
            }
            continue;
        }
        // 값이 다시 상한 아래로 내려오면 래치를 푼다.
        state.warnedRayCap = false;

        if (result != LidarScanResult::kOk) continue;

        // 스캔이 실제로 돌았다. 히트가 하나도 없었더라도 이번 틱에 이
        // 노드의 몫은 끝났으므로 스로틀 기준점을 갱신한다.
        state.lastScan = tickNow;
        state.hasScanned = true;

        // 라이브 프리뷰(Task 5) -- points가 아래에서 std::move로 큐에 들어가기
        // 전에 먼저 처리해야 한다(그렇지 않으면 빈 벡터를 읽는다). 전역
        // 제약: cmds/MDGModifier를 거치지 않는 raw plug write여야 한다 --
        // 이 틱마다(~30fps) 도는 코드가 undo 큐를 도배하면 안 된다(Phase 3
        // idle-loop 교훈과 같은 이유).
        if (lidarFn.findPlug(MaroLidarNode::aVisualize, false).asBool()) {
            MPlug messagePlug = lidarFn.findPlug("message", false);
            MPlugArray destinations;
            messagePlug.connectedTo(destinations, false, true);
            for (unsigned int i = 0; i < destinations.length(); ++i) {
                if (destinations[i].attribute() != MaroPointCloudNode::aSourceLidar) continue;
                MFnDependencyNode pointCloudFn(destinations[i].node());
                if (pointCloudFn.typeId() != MaroPointCloudNode::id) continue;

                const auto preview = maro::lidar::decimateForPreview(points, kMaxPreviewPoints);
                MPointArray mayaPoints;
                mayaPoints.setLength(static_cast<unsigned int>(preview.size()));
                for (unsigned int j = 0; j < mayaPoints.length(); ++j) {
                    mayaPoints[j] = MPoint(preview[j].x, preview[j].y, preview[j].z, 1.0);
                }
                MFnPointArrayData pointArrayDataFn;
                MObject pointsData = pointArrayDataFn.create(mayaPoints);
                MPlug pointsPlug = pointCloudFn.findPlug(MaroPointCloudNode::aPoints, false);
                pointsPlug.setValue(pointsData);
                break;
            }
        }

        if (!points.empty()) {
            LidarSample sample;
            sample.unit = unit;
            sample.points = std::move(points);
            runtime.lidarQueue().push(std::move(sample));
        }
    }
}

}  // namespace maro
