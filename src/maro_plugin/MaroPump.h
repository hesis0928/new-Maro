#pragma once

#include <atomic>
#include <chrono>
#include <cstdint>
#include <memory>
#include <unordered_map>

#include <maya/MCallbackIdArray.h>
#include <maya/MObjectHandle.h>
#include <maya/MStatus.h>

namespace maro::lidar {
class ScanEngine;
}

namespace maro {

class MaroRosRuntime;

// Maya 메인 스레드에서만 도는 발행 펌프. DG에서 축 상태를 읽어 큐에
// 적재하는, 발행 방향 전담이다.
// 변환에 필요한 컨텍스트(씬 단위, 축 보정)는 Maya 조회가 필요하므로
// 여기서 읽어 샘플에 함께 실어 보낸다. 백그라운드는 Maya를 조회하지 않는다.
//
// 수신 방향(명령 적용)은 더 이상 여기 없다. MaroCommandDeviceNode::compute()가
// 대신한다 — 이 펌프가 만든 타이머가 아니라 devkit이 관리하는 dirty 전파로
// 불린다 (Task 10 설계 노트 참고).
class MaroPump {
public:
    static MStatus start(MaroRosRuntime& runtime);
    static MStatus stop();
    static bool isRunning();

    static std::uint64_t collectedSampleCount();

private:
    static void onTimer(float elapsed, float last, void* clientData);
    static void collectSamples(MaroRosRuntime& runtime);
    static void collectLidarScans(MaroRosRuntime& runtime);

    static MCallbackId s_timerId;
    static MaroRosRuntime* s_runtime;
    static std::atomic<std::uint64_t> s_collected;

    // LiDAR 노드 하나에 대해 틱 사이에 기억해야 하는 것들. 메인 스레드
    // 전용이다(collectLidarScans는 MTimerMessage 콜백에서만 불린다) --
    // 원자성이 필요 없다.
    struct LidarNodeState {
        // 맵 키는 MObjectHandle::objectHashCode()라 노드가 지워졌는지
        // 판정할 수 없다. 핸들을 함께 들고 있어야 죽은 항목을 걷어낼 수
        // 있다 -- 안 그러면 씬을 여러 번 새로 열 때 맵이 계속 자란다.
        MObjectHandle handle;
        std::chrono::steady_clock::time_point lastScan{};
        bool hasScanned = false;
        // 레이 개수 상한 진단을 이 노드에 대해 이미 한 번 냈는지.
        // 30Hz로 같은 에러를 계속 찍으면 진단 스트림이 무의미해진다
        // (MaroCommandDeviceNode의 "상태 변화 시 1회만" 가드와 같은 취지).
        bool warnedRayCap = false;
    };

    // updateRate 스로틀(Finding I3)과 레이 상한 1회 경고(Finding I2)를
    // 위한 노드별 상태. start()에서 비우고 stop()에서 비운다.
    static std::unordered_map<unsigned int, LidarNodeState> s_lidarNodeState;

    // 모든 LiDAR 노드가 공유하는 Embree 디바이스 (Finding I5). 예전에는
    // collectLidarScans의 노드 루프 안에서 매 틱 ScanEngine을 새로
    // 만들었는데, EMBREE_TASKING_SYSTEM=INTERNAL에서는 rtcNewDevice()가
    // 하드웨어 코어 수만큼 워커 스레드 풀을 통째로 만들고 부순다 -- 초당
    // 30번, 그것도 Maya UI가 도는 메인 스레드에서.
    //
    // 함수 지역 static이 아닌 이유: 그러면 소멸자가 .mll 언로드 시점(Maya가
    // 이미 해체를 시작한 뒤)에 돌아 rtcReleaseDevice가 너무 늦게 불린다 --
    // 이 프로젝트가 COM 수명(ComUninitGuard/JobEscape)에서 한 번 겪은 것과
    // 같은 순서 문제다. 대신 start()에서 만들고 stop()에서 명시적으로
    // 놓는다. stop()은 uninitializePlugin -> shutdownBridge()(MaroCommands.cpp)
    // 경로에서 반드시 불리므로, 정적 소멸 시점에는 항상 비어 있다.
    static std::unique_ptr<maro::lidar::ScanEngine> s_scanEngine;
};

}  // namespace maro
