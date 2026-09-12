#pragma once

#include <atomic>
#include <cstdint>
#include <mutex>
#include <string>

#include <maya/MObject.h>
#include <maya/MPxThreadedDeviceNode.h>
#include <maya/MStatus.h>
#include <maya/MString.h>
#include <maya/MTypeId.h>

namespace maro {

// ROS 2 -> Maya 수신 전담. Maya가 백그라운드 스레드를 만들고 끝낸다.
// threadHandler()는 그 스레드에서 돈다 -- DG를 절대 건드리지 않는다
// (compute()만 건드린다). 큐도 뮤텍스도 우리가 만들지 않는다;
// acquireDataStorage()/pushThreadData()/popThreadData()가 devkit 내부
// 락과 링버퍼로 그 역할을 대신한다.
class MaroCommandDeviceNode : public MPxThreadedDeviceNode {
public:
    MaroCommandDeviceNode();
    ~MaroCommandDeviceNode() override;

    void postConstructor() override;
    MStatus compute(const MPlug& plug, MDataBlock& data) override;

    // kUntrusted: 평가 관리자(PEM)가 이 노드를 평가하는 동안 다른 어떤
    // 노드도 동시에 평가하지 않는다. compute()의 applyToMatchingAxis()는
    // 자기 출력이 아니라 **다른 노드**(maroAxis.rosCommand)의 플러그에
    // 쓰는, 이 플러그인에서 유일한 지점이다 -- Serial(기본)은 같은 평가
    // 체인 안에서만 순차를 보장하므로 축 노드가 다른 워커에서 같은 플러그를
    // 읽는 사이에 쓸 수 있다. 이 노드는 commandOut 외에 DG 소비자가 없어
    // 병렬성 손실은 없다.
    SchedulingType schedulingType() const override;

    void threadHandler() override;
    void threadShutdownHandler() override;

    static void* creator();
    static MStatus initialize();

    // 메인 스레드에서, 노드를 만든 직후(live를 켜기 전)에 한 번만 부른다.
    // 로봇 네임스페이스를 스레드로 안전하게 건너 보낸다.
    void setRobotName(const MString& robotName);

    static void resetStats();
    static std::uint64_t appliedCommandCount();
    static std::uint64_t threadTickCount();
    static std::uint64_t skippedUnchangedCount();
    static bool isThreadAlive();

    static MTypeId id;
    static MObject aCommandOut;   // 값 자체는 안 쓴다 -- dirty 표시 전용

private:
    std::string robotNameSnapshot() const;
    static void applyToMatchingAxis(const std::string& jointName, double value);

    mutable std::mutex m_configMutex;
    std::string m_robotName;

    static std::atomic<std::uint64_t> s_applied;
    static std::atomic<std::uint64_t> s_ticks;
    static std::atomic<std::uint64_t> s_dropped;         // 관절 이름이 너무 길어 버려진 개수
    static std::atomic<std::uint64_t> s_poolExhausted;    // 버퍼 풀이 꽉 차 버려진 개수
    // 델타체크로 건너뛴 개수 -- 값이 실제로 안 바뀌어 setDouble()을 호출하지
    // 않은 경우. s_applied와 합치면 이 노드가 처리한 명령 총수가 된다.
    static std::atomic<std::uint64_t> s_skippedUnchanged;
    // 살아있는 threadHandler() 인스턴스 개수 (bool 아님). maroCommandDevice는
    // 사용자가 여러 개 만들 수 있는 등록 노드 타입이라, 인스턴스 하나가
    // 끝난다고 다른 인스턴스의 스레드까지 죽었다고 해선 안 된다.
    static std::atomic<int> s_threadAliveCount;

    // compute()의 방울 경고(rate-limited warning)가 마지막으로 보고한 값.
    // resetStats()가 함께 0으로 되돌려야 재시작 후 unsigned 뺄셈이
    // 언더플로우해 말도 안 되는 수를 찍는 일이 없다 (main 스레드 전용,
    // atomic 아님).
    static std::uint64_t s_lastReportedDropped;
    static std::uint64_t s_lastReportedPoolExhausted;
};

}  // namespace maro
