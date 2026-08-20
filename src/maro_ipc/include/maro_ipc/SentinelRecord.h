#pragma once

#include <cstdint>
#include <filesystem>
#include <optional>

namespace maro::ipc {

// PID 기록 파일 한 장. 사람이 손으로 감시자를 찾을 때 헤매지 않게 하고,
// 다음 플러그인 로드의 자가 점검이 이 정보로 낡은 감시자를 알아본다.
struct SentinelRecord {
    std::uint64_t sentinelPid = 0;
    std::uint64_t ownerMayaPid = 0;
    std::uint64_t startTimeMs = 0;

    // 시작 시점에 isCurrentProcessInJob()이 감시자 프로세스 자신을 관측한
    // 결과. lastSessionEndedCleanly와 달리 세션이 끝나기를 기다릴 필요가
    // 없다 -- 감시자가 뜨는 순간 바로 answer가 나오므로 std::optional이
    // 아니라 평범한 bool이다.
    //
    // 현재 상태(정확히 이것뿐이다): 이 값은 감시자가 **쓰고**, 기록 파일에
    // 남아 사람과 다음 세션이 읽을 수 있다. 하지만 **플러그인은 아직 이
    // 값을 읽지 않는다** -- C-1 골격에서는 spawn 성공
    // (CreateProcess의 CREATE_BREAKAWAY_FROM_JOB, 실패 시 WMI ExecMethod)
    // 자체를 탈출 성공의 충분한 신호로 삼기로 한 의도적 축소다.
    //
    // 그 축소가 놓치는 경우: 중첩 job. breakaway가 *직속* job에 대해서는
    // 성공했지만 그 바깥 조상 job이 프로세스를 계속 붙잡고 있으면
    // CreateProcess는 성공하는데 감시자는 여전히 어떤 job 안에 있다. 그때
    // 이 필드만이 그 사실을 알려준다 -- 나중 단계가 이 값을 읽어
    // tier 2(WMI)로 승격할지 판단할 자리이며, 그 승격 로직은 이 플랜에
    // 없다.
    bool sentinelInJob = false;

    // 크래시 판정에서 C-1이 관측 가능한 결과를 내는 유일한 자리. 세션이 끝나기 전에는
    // nullopt("아직 모른다"), 감시자가 SESSION_END_CLEAN 없이 파이프가
    // 끊긴 것을 본 순간 false로 쓴다. true는 이 플랜에서 실제로 쓰지
    // 않는다 -- 정상 종료 시 감시자는 판정을 남길 필요 없이 그냥 종료하므로
    // (§3.4 "절대 수명" 참고), 이 필드가 있는데 값이 없으면 "아직 세션
    // 진행 중이거나 판정 전에 파일이 남았다"는 뜻이다.
    std::optional<bool> lastSessionEndedCleanly;
};

// 실패해도 예외를 던지지 않는다. 부모 디렉터리가 없으면 만든다.
bool writeSentinelRecord(const std::filesystem::path& path, const SentinelRecord& record);

// 파일이 없거나 형식이 깨졌으면 false. out은 그때 건드리지 않는다.
bool readSentinelRecord(const std::filesystem::path& path, SentinelRecord& out);

}  // namespace maro::ipc
