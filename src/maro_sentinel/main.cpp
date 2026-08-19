#include <windows.h>

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <string>
#include <thread>

#include "maro_ipc/JobEscape.h"
#include "maro_ipc/NamedMutexGuard.h"
#include "maro_ipc/NamedPipe.h"
#include "maro_ipc/Naming.h"
#include "maro_ipc/SentinelRecord.h"

namespace {

// 접속을 기다리는 시간. 이 안에 아무도 안 붙으면 좀비로 남지 않고
// 스스로 종료한다(원 스펙 §5.2 "절대 수명").
constexpr DWORD kConnectionTimeoutMs = 15000;

// 메시지 루프 한 바퀴의 대기 시간. 짧게 잡아 킬 이벤트 확인 주기를
// 촘촘히 유지한다 -- 이것이 "모든 대기에 타임아웃"을 만족시키는 지점이다.
constexpr DWORD kReceivePollMs = 500;

// 접속은 됐는데 첫 메시지(HELLO)조차 안 오는 채로 버틸 수 있는 최대 시간 --
// 붙기만 하고 말이 없는 클라이언트에 대한 안전망. **연결이 성립한 뒤 첫
// 메시지까지에만** 적용된다. HELLO를 한 번 받고 나면 세션이 성립한 것이고,
// 그 뒤로는 아무 말이 없는 것이 정상이다: C-1의 프로토콜은 메시지가 둘뿐이라
// (HELLO, SESSION_END_CLEAN) 로드와 언로드 사이에 아무것도 오가지 않는다.
constexpr std::uint64_t kFirstMessageTimeoutMs = 30000;

// [브리프에서 고침] receiveMessage는 실패를 bool 하나로만 알려주지만, 그
// 실패에 걸린 *시간*이 "끊김"과 "아직 아무 말이 없음"을 가른다. 파이프가
// 끊겼으면 ReadFile이 ERROR_BROKEN_PIPE로 곧바로 떨어져 기다리는 시늉조차
// 하지 않는다(Task 5가 tests/ipc/test_named_pipe.cpp의
// ServerDetectsDisconnectWithoutMessage에서 2000ms 타임아웃에 대해
// "1000ms 미만"으로 고정해 둔 성질이다 -- 실측은 사실상 0ms). 반대로 진짜
// 타임아웃은 정의상 timeoutMs를 꽉 채운다. 그래서 "자기 타임아웃의 1/5도
// 안 쓰고 돌아온 실패"는 기다린 적이 없다는 뜻이고, 곧 끊김이다.
constexpr std::uint64_t kDidNotWaitMs = kReceivePollMs / 5;

// 위 판정을 한 번의 관측으로 내리지 않는 이유: receiveMessage는 끊김 말고도
// 즉시 false를 줄 수 있다(decodeMessage가 거부하는 깨진 메시지, 8KB를 넘는
// 메시지의 ERROR_MORE_DATA). 그런 일회성 사고를 크래시로 오판하지 않도록
// 연속으로 몇 번 그러는지를 본다 -- 진짜 끊김이면 이후 모든 시도가 예외 없이
// 즉시 실패하므로 곧바로 채워지고, 일회성이면 다음 호출이 타임아웃을 꽉 채워
// 카운터가 0으로 돌아간다.
constexpr int kFastFailuresMeaningDisconnect = 3;

// 위 연속 관측 사이에 넣는 짧은 숨. 없으면 끊긴 파이프에 대고 초당 수십만
// 번 ReadFile을 거는 핫 루프가 된다(브리프 원본의 실측: 30초 동안 CPU 한
// 코어를 99% 점유). 감시자는 눈에 띄지 않아야 하는 프로세스다.
constexpr DWORD kFastFailureBackoffMs = 50;

// 원 스펙 §5.2의 마지막 안전망. 파이프는 Maya가 죽는 순간 커널이 닫아 주므로
// (프로세스가 사라지면 핸들도 사라진다) 여기 걸릴 일은 사실상 없다 -- 정말로
// 파이프가 영영 안 끊기는 이상 상황만을 위한 상한이다. 그래서 값이 넉넉해야
// 한다: 이 값이 짧으면 감시자가 멀쩡한 세션 도중에 감시를 그만두게 된다.
constexpr std::uint64_t kMaxSessionLifetimeMs = 12ULL * 60ULL * 60ULL * 1000ULL;

// 기록 파일에 남기는 벽시계 시각. 사람이 읽는 값이라 system_clock이 맞다.
std::uint64_t nowMs() {
    return static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch())
            .count());
}

// [브리프에서 고침] *경과 시간*은 system_clock으로 재면 안 된다. 그 시계는
// NTP 보정이나 사용자의 시각 변경으로 뒤로도 앞으로도 뛴다 -- 감시자가 몇
// 시간짜리 세션을 지키는 동안 한 번 뛰면 그 자리에서 수명이 끝났다고
// 판단하거나(앞으로 뜀) 영영 안 끝났다고 판단한다(뒤로 뜀). 단조 시계로 잰다.
using SteadyClock = std::chrono::steady_clock;

std::uint64_t elapsedMsSince(const SteadyClock::time_point& start) {
    return static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::milliseconds>(SteadyClock::now() - start)
            .count());
}

// 모든 종료 경로에서 핸들을 닫는다는 규율을 코드로 강제한다.
struct ScopedHandle {
    HANDLE handle = nullptr;
    explicit ScopedHandle(HANDLE h) : handle(h) {}
    ~ScopedHandle() {
        if (handle != nullptr) ::CloseHandle(handle);
    }
    ScopedHandle(const ScopedHandle&) = delete;
    ScopedHandle& operator=(const ScopedHandle&) = delete;
};

void markAbnormalExit(const std::filesystem::path& recordPath, std::uint64_t sentinelPid,
                      std::uint64_t ownerPid, std::uint64_t startTimeMs) {
    maro::ipc::SentinelRecord record;
    record.sentinelPid = sentinelPid;
    record.ownerMayaPid = ownerPid;
    record.startTimeMs = startTimeMs;
    record.lastSessionEndedCleanly = false;
    maro::ipc::writeSentinelRecord(recordPath, record);
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 3) {
        std::fprintf(stderr, "usage: maro_sentinel.exe <owner_maya_pid> <book_dir>\n");
        return 1;
    }

    const std::uint64_t ownerPid = std::strtoull(argv[1], nullptr, 10);
    const std::filesystem::path bookDir = argv[2];
    const std::uint64_t sentinelPid = ::GetCurrentProcessId();
    const std::uint64_t startTimeMs = nowMs();

    // 좀비 방지: 명명된 뮤텍스로 단일 인스턴스. 이미 같은 Maya PID의
    // 감시자가 떠 있으면 조용히 종료한다 -- 에러가 아니다.
    maro::ipc::NamedMutexGuard instanceGuard(maro::ipc::mutexName(ownerPid), 1000);
    if (!instanceGuard.isAcquired()) {
        return 0;
    }

    const auto recordPath = maro::ipc::recordFilePath(bookDir, ownerPid);

    maro::ipc::SentinelRecord initialRecord;
    initialRecord.sentinelPid = sentinelPid;
    initialRecord.ownerMayaPid = ownerPid;
    initialRecord.startTimeMs = startTimeMs;
    // lastSessionEndedCleanly는 아직 미설정 -- 판정 전이라는 뜻.
    maro::ipc::writeSentinelRecord(recordPath, initialRecord);

    // job 자가 점검. 지금 이 골격 단계에서는 기록만 남긴다 -- 실제 판단
    // (탈출 실패 시 무엇을 할지)은 플러그인 쪽(Task 9)이 spawn 방식을
    // 고를 때 이미 내렸다. 감시자 자신의 self-check는 "빠져나왔겠지가
    // 아니라 빠져나왔다를 안다"를 만족시키는 확인일 뿐이다.
    const bool inJob = maro::ipc::isCurrentProcessInJob();
    (void)inJob;  // C-1은 이 사실을 파이프로 보고하지 않는다 -- 플러그인이
                  // spawn 성공 여부만으로 이미 판단을 마쳤기 때문이다. 이후
                  // 조각(C-2+)이 진단 용도로 쓸 수 있게 자리는 마련해 둔다.

    // 좀비 방지: 킬 스위치 이벤트. bManualReset=TRUE로 만들어 한 번
    // Set되면 계속 신호 상태로 남게 한다(폴링하는 쪽마다 개별로 리셋할
    // 필요 없음).
    ScopedHandle killEvent(::CreateEventA(nullptr, TRUE, FALSE,
                                          maro::ipc::killEventName(ownerPid).c_str()));

    maro::ipc::NamedPipeServer server(maro::ipc::pipeName(ownerPid));
    if (!server.waitForConnection(kConnectionTimeoutMs)) {
        // 아무도 안 붙었다 -- 좀비로 남지 않고 그냥 종료. 이 세션에 대해
        // 아무것도 몰랐으니 기록을 갱신할 것도 없다.
        return 0;
    }

    bool sawSessionEndClean = false;
    bool disconnected = false;
    bool sawAnyMessage = false;
    int consecutiveFastFailures = 0;
    const auto connectedAt = SteadyClock::now();

    for (;;) {
        if (killEvent.handle != nullptr &&
            ::WaitForSingleObject(killEvent.handle, 0) == WAIT_OBJECT_0) {
            break;  // 킬 스위치 -- 판정 없이 즉시 종료.
        }

        const std::uint64_t elapsedMs = elapsedMsSince(connectedAt);
        if (!sawAnyMessage && elapsedMs > kFirstMessageTimeoutMs) {
            break;  // 붙어 놓고 한 마디도 없다 -- 판정 없이 종료(아래 주석).
        }
        if (elapsedMs > kMaxSessionLifetimeMs) {
            break;  // 절대 수명 -- 판정 없이 종료(아래 주석).
        }

        maro::ipc::Message received;
        const auto callStart = SteadyClock::now();
        if (server.receiveMessage(received, kReceivePollMs)) {
            sawAnyMessage = true;
            consecutiveFastFailures = 0;
            if (received.type == maro::ipc::MessageType::SessionEndClean) {
                sawSessionEndClean = true;
                break;
            }
            // HELLO류 다른 메시지는 계속 루프를 돈다.
            continue;
        }

        // 실패했다. 이 실패가 "끊김"인지 "아직 아무 말이 없음"인지는 위
        // kDidNotWaitMs 주석의 근거대로 *걸린 시간*으로 가른다.
        if (elapsedMsSince(callStart) >= kDidNotWaitMs) {
            // 타임아웃을 제대로 기다렸다 = 파이프는 살아 있고 할 말이 없을
            // 뿐이다. 정상이다.
            consecutiveFastFailures = 0;
            continue;
        }

        if (++consecutiveFastFailures >= kFastFailuresMeaningDisconnect) {
            disconnected = true;
            break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(kFastFailureBackoffMs));
    }

    server.close();

    if (sawSessionEndClean) {
        // 정상 종료 -- 판정을 남길 필요가 없다(SentinelRecord.h의 주석
        // 참고). 기록 파일은 초기 상태(미판정) 그대로 둔다.
        return 0;
    }

    if (disconnected) {
        // SESSION_END_CLEAN 없이 파이프가 끊겼다 -- 원 스펙 §3.2가 말하는
        // 크래시 신호 그 자체다. 추측이 아니라 관측이다.
        markAbnormalExit(recordPath, sentinelPid, ownerPid, startTimeMs);
        return 0;
    }

    // [브리프에서 고침] 남은 경로는 셋이다: 킬 스위치, 첫 메시지 없음,
    // 절대 수명. 브리프 원본은 이 셋도 markAbnormalExit로 떨어뜨렸다
    // (판정을 sawSessionEndClean 하나로만 갈랐고, disconnected는 대입만 하고
    // 읽지 않았다) -- 킬 스위치 갈래에 "판정 없이 즉시 종료"라고 적어 놓고
    // 실제로는 크래시로 기록하는 모순이었다.
    //
    // 셋 다 판정을 남길 *자격*이 없다: 셋 다 파이프가 끊긴 것을 본 적이
    // 없다. 살아 있는 연결에 대해 "비정상 종료였다"를 쓰는 것은 관측이
    // 아니라 지어낸 크래시 보고이며, 설계 §3.2가 "임의의 타임아웃 값이
    // 설계에 들어가지 않는다"고 못박은 이유가 정확히 이것이다. 값이 없다는
    // 것은 "판정할 비정상 종료를 못 봤다"는 뜻이고, 이 셋은 그 상태다.
    return 0;
}
