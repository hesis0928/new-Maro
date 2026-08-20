#include <gtest/gtest.h>

#include <windows.h>

#include <chrono>
#include <filesystem>
#include <string>
#include <thread>

#include "maro_ipc/JobEscape.h"
#include "maro_ipc/NamedPipe.h"
#include "maro_ipc/Naming.h"
#include "maro_ipc/SentinelRecord.h"

namespace {

std::filesystem::path freshBookDir(const std::string& name) {
    const std::filesystem::path dir =
        std::filesystem::temp_directory_path() / ("maro_sentinel_process_test_" + name);
    std::error_code ec;
    std::filesystem::remove_all(dir, ec);
    std::filesystem::create_directories(dir, ec);
    return dir;
}

// 빌드 시스템이 정확한 경로를 알려준다. 멀티 컨피그 제너레이터에서는
// maro_ipc_tests와 maro_sentinel이 서로 다른 하위 디렉터리에 놓이므로
// "내 옆에 있겠지"(GetModuleFileNameA + 상대 경로)라는 가정이 성립하지 않는다.
std::string sentinelExePath() { return MARO_SENTINEL_EXE_PATH; }

// gtest 프로세스 자신의 PID를 "소유자 Maya PID"로 사칭한다 -- 실제
// Maya는 필요 없다. 이 프로세스 자신은 확실히 살아 있으므로 명명
// 규칙이 요구하는 PID 하나만 있으면 충분하다.
std::uint64_t fakeMayaPid() { return ::GetCurrentProcessId(); }

PROCESS_INFORMATION spawnSentinel(const std::filesystem::path& bookDir) {
    std::string commandLine =
        "\"" + sentinelExePath() + "\" " + std::to_string(fakeMayaPid()) +
        " \"" + bookDir.string() + "\"";

    STARTUPINFOA startupInfo{};
    startupInfo.cb = sizeof(startupInfo);
    PROCESS_INFORMATION processInfo{};
    const BOOL created = ::CreateProcessA(nullptr, commandLine.data(), nullptr, nullptr,
                                          FALSE, 0, nullptr, nullptr, &startupInfo,
                                          &processInfo);
    EXPECT_TRUE(created) << "could not launch maro_sentinel.exe";
    return processInfo;
}

bool processIsRunning(DWORD pid) {
    HANDLE h = ::OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (h == nullptr) return false;
    DWORD exitCode = 0;
    const bool running = ::GetExitCodeProcess(h, &exitCode) && exitCode == STILL_ACTIVE;
    ::CloseHandle(h);
    return running;
}

// [브리프에서 고침] 브리프 원본은 성공 경로에서만 두 핸들을 닫았다. gtest의
// ASSERT_*는 실패하면 그 자리에서 return하므로, 감시자가 상한 안에 안 죽는
// 바로 그 실패에서 CloseHandle도 TerminateProcess도 실행되지 않는다 -- 즉
// 좀비를 막으려고 만든 플랜의 테스트가 실패할 때마다 좀비를 하나씩 남긴다.
// (실측: 브리프 원본 루프로 돌렸을 때 실패한 감시자가 30초 더 살면서 CPU
// 한 코어를 계속 태웠고, ctest는 그 프로세스가 물려받은 stdout 파이프가
// 닫힐 때까지 30초를 더 기다렸다.) 정리를 소멸자로 옮겨 모든 경로에서
// 강제한다 -- 판정은 이미 각 테스트의 ASSERT가 끝낸 뒤다.
struct SentinelProcessGuard {
    PROCESS_INFORMATION info{};

    explicit SentinelProcessGuard(const PROCESS_INFORMATION& processInfo) : info(processInfo) {}

    ~SentinelProcessGuard() {
        if (info.hProcess == nullptr) return;
        if (processIsRunning(info.dwProcessId)) {
            ::TerminateProcess(info.hProcess, 1);
            ::WaitForSingleObject(info.hProcess, 5000);
        }
        ::CloseHandle(info.hProcess);
        ::CloseHandle(info.hThread);
    }

    SentinelProcessGuard(const SentinelProcessGuard&) = delete;
    SentinelProcessGuard& operator=(const SentinelProcessGuard&) = delete;
};

// 위와 같은 규율을 PID만 아는 경우에 적용한다. 감시자를 우리가 아니라
// 도우미 프로세스가 띄운 경우(아래 SentinelStuckInAJob... 테스트)에는
// PROCESS_INFORMATION이 우리 손에 없고, 감시자 PID는 기록 파일에서
// 읽어 온다. 그 PID로 핸들을 열어 같은 "살아 있으면 죽이고 반드시
// 닫는다"를 보장한다 -- 어느 ASSERT에서 빠져나가든 좀비가 남지 않는다.
struct SentinelPidGuard {
    DWORD pid = 0;

    ~SentinelPidGuard() {
        if (pid == 0) return;
        HANDLE process = ::OpenProcess(PROCESS_TERMINATE | SYNCHRONIZE, FALSE, pid);
        if (process == nullptr) return;  // 이미 죽었다(또는 접근 불가) -- 할 일 없다.
        ::TerminateProcess(process, 1);
        ::WaitForSingleObject(process, 5000);
        ::CloseHandle(process);
    }

    SentinelPidGuard(const SentinelPidGuard&) = delete;
    SentinelPidGuard& operator=(const SentinelPidGuard&) = delete;
};

// 기록 파일이 생기고 온전히 파싱될 때까지 상한 안에서 기다린다.
// writeSentinelRecord는 trunc 후 dump라 원자적이지 않으므로(SentinelRecord.cpp),
// 쓰는 도중에 읽으면 0바이트나 잘린 JSON을 본다 -- 그것은 실패가 아니라
// "아직 쓰는 중"이다(tests/maya/test_sentinel.py의 read_record와 같은 논리).
bool waitForRecord(const std::filesystem::path& recordPath, maro::ipc::SentinelRecord& out,
                   std::uint32_t timeoutMs) {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(timeoutMs);
    for (;;) {
        if (maro::ipc::readSentinelRecord(recordPath, out)) return true;
        if (std::chrono::steady_clock::now() >= deadline) return false;
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
}

// 클라이언트가 붙자마자 닫으면, 감시자가 아직 ConnectNamedPipe를 부르기 전인
// 창(마이크로초 단위지만 실재한다)에 걸릴 수 있다. 그 상태에서
// ConnectNamedPipe는 ERROR_NO_DATA로 떨어지고 waitForConnection이 false를
// 돌려주므로, 감시자는 "아무도 안 붙었다"로 판단해 판정 없이 종료한다. 그러면
// 아래 두 테스트는 각각 엉뚱한 이유로 실패하거나(비정상 시나리오) 더 나쁘게는
// **엉뚱한 이유로 통과한다**(정상 시나리오: 판정이 없는 것이 맞는 답이라
// 감시자가 파이프를 아예 못 받았어도 통과해 버린다).
//
// 이 테스트들이 고정하려는 것은 접속 수락 경쟁이 아니라 그 뒤의 판정이므로,
// 닫기 전에 수락이 끝날 시간을 준다 -- Task 5의 파이프 테스트들이 같은 이유로
// 순서를 강제한 것(tests/ipc/test_named_pipe.cpp의 [I1] 주석)과 같은 조치다.
void letTheSentinelAcceptTheConnection() {
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
}

}  // namespace

TEST(SentinelProcess, CleanSessionEndsAndSentinelExits) {
    const auto bookDir = freshBookDir("clean");
    SentinelProcessGuard sentinel(spawnSentinel(bookDir));

    maro::ipc::NamedPipeClient client;
    ASSERT_TRUE(client.connect(maro::ipc::pipeName(fakeMayaPid()), 5000));
    letTheSentinelAcceptTheConnection();

    maro::ipc::Message hello;
    hello.type = maro::ipc::MessageType::Hello;
    ASSERT_TRUE(client.sendMessage(hello));

    maro::ipc::Message sessionEnd;
    sessionEnd.type = maro::ipc::MessageType::SessionEndClean;
    ASSERT_TRUE(client.sendMessage(sessionEnd));
    client.close();

    const DWORD waitResult = ::WaitForSingleObject(sentinel.info.hProcess, 5000);
    ASSERT_EQ(waitResult, WAIT_OBJECT_0) << "sentinel did not exit after a clean session end";

    maro::ipc::SentinelRecord record;
    const auto recordPath = maro::ipc::recordFilePath(bookDir, fakeMayaPid());
    ASSERT_TRUE(maro::ipc::readSentinelRecord(recordPath, record));
    // 정상 종료는 이 필드에 값을 남길 필요가 없다는 것이 설계 결정이다
    // (SentinelRecord.h 주석 참고) -- 값이 없다는 것 자체가 "판정할 비정상
    // 종료가 없었다"는 뜻이다. 값이 *있으면서* false인 것과 값이 아예 없는
    // 것은 다르다 -- 전자는 감시자가 크래시라고 판정한 것이므로, 이 EXPECT는
    // 정상 종료를 크래시로 오판하지 않는다는 것까지 함께 고정한다.
    EXPECT_FALSE(record.lastSessionEndedCleanly.has_value())
        << "clean session end was judged as an abnormal exit (value = "
        << (record.lastSessionEndedCleanly.value_or(false) ? "true" : "false") << ")";

    // sentinelInJob이 기록 파일에 실제로 남는지 -- Task 9가 파이프 없이
    // 이 필드 하나로 "감시자가 정말 job을 빠져나왔는지"를 판단하려면 이
    // 값이 기본값(false)이 아니라 감시자 자신의 self-check 결과여야 한다.
    // 테스트 프로세스(gtest)와 감시자 서브프로세스는 CreateProcess로
    // 직결된 부모-자식이므로, 둘 다 같은 job 소속 여부를 관측해야 정상이다
    // -- 이 샌드박스 CI 환경은 프로세스 트리 전체가 이미 앰비언트 job
    // 안에 있다는 것이 Task 6에서 확인된 사실이라(그래서 true가 나올
    // 가능성이 높다), 어느 쪽 값이어야 하는지 하드코딩하지 않고 실측값과
    // 비교한다.
    const bool testProcessInJob = maro::ipc::isCurrentProcessInJob();
    EXPECT_EQ(record.sentinelInJob, testProcessInJob)
        << "record's sentinelInJob (" << (record.sentinelInJob ? "true" : "false")
        << ") does not match what isCurrentProcessInJob() reports for this test "
           "process ("
        << (testProcessInJob ? "true" : "false") << ")";
}

TEST(SentinelProcess, DisconnectWithoutSessionEndIsRecordedAsAbnormal) {
    const auto bookDir = freshBookDir("abnormal");
    SentinelProcessGuard sentinel(spawnSentinel(bookDir));

    {
        maro::ipc::NamedPipeClient client;
        ASSERT_TRUE(client.connect(maro::ipc::pipeName(fakeMayaPid()), 5000));
        letTheSentinelAcceptTheConnection();
        maro::ipc::Message hello;
        hello.type = maro::ipc::MessageType::Hello;
        ASSERT_TRUE(client.sendMessage(hello));
        // SESSION_END_CLEAN 없이 바로 닫는다 -- 크래시한 Maya를 흉내낸다.
    }

    // 5초는 넉넉한 상한이 아니라 이 테스트의 주장 자체다: 끊김은 즉시 보여야
    // 한다(Task 5가 receiveMessage 수준에서 이미 고정한 성질 --
    // tests/ipc/test_named_pipe.cpp의 ServerDetectsDisconnectWithoutMessage).
    // 감시자가 끊김을 "언젠가" 알아채는 것으로는 부족하다.
    const auto waitStart = std::chrono::steady_clock::now();
    const DWORD waitResult = ::WaitForSingleObject(sentinel.info.hProcess, 5000);
    const auto noticedMs = std::chrono::duration_cast<std::chrono::milliseconds>(
                               std::chrono::steady_clock::now() - waitStart)
                               .count();
    ASSERT_EQ(waitResult, WAIT_OBJECT_0)
        << "sentinel did not exit after detecting an abnormal disconnect "
           "(still alive after "
        << noticedMs << " ms)";

    maro::ipc::SentinelRecord record;
    const auto recordPath = maro::ipc::recordFilePath(bookDir, fakeMayaPid());
    ASSERT_TRUE(maro::ipc::readSentinelRecord(recordPath, record));
    ASSERT_TRUE(record.lastSessionEndedCleanly.has_value());
    EXPECT_FALSE(*record.lastSessionEndedCleanly);
}

TEST(SentinelProcess, NoConnectionEverArrivesSoSentinelExitsOnItsOwn) {
    // 아무도 접속하지 않으면 감시자가 좀비로 남으면 안 된다 -- 접속 대기
    // 타임아웃 자체가 좀비 방지의 한 축이다.
    const auto bookDir = freshBookDir("no_connection");
    SentinelProcessGuard sentinel(spawnSentinel(bookDir));

    // 감시자의 접속 대기 타임아웃보다 넉넉히 긴 시간을 기다린다.
    const auto waitStart = std::chrono::steady_clock::now();
    const DWORD waitResult = ::WaitForSingleObject(sentinel.info.hProcess, 20000);
    const auto aliveMs = std::chrono::duration_cast<std::chrono::milliseconds>(
                             std::chrono::steady_clock::now() - waitStart)
                             .count();
    ASSERT_EQ(waitResult, WAIT_OBJECT_0)
        << "sentinel became a zombie waiting forever for a connection that never came";

    // 이 테스트가 "다른 이유로 우연히 통과"하지 않는다는 것을 못박는다:
    // 감시자가 접속을 *기다리다가* 타임아웃으로 나간 것이어야지, 시작하자마자
    // 무언가 잘못돼 죽은 것이면 안 된다(예: 인자 파싱 실패로 return 1,
    // 뮤텍스 획득 실패로 즉시 return 0). 그런 조기 종료는 접속 대기 타임아웃에
    // 대해 아무것도 증명하지 못한 채 위 EXPECT만 만족시킨다.
    EXPECT_GE(aliveMs, 10000)
        << "sentinel exited far too early -- it cannot have waited out its "
           "connection timeout, so this test proves nothing about that timeout";

    DWORD exitCode = 1;
    ASSERT_TRUE(::GetExitCodeProcess(sentinel.info.hProcess, &exitCode));
    EXPECT_EQ(exitCode, 0u) << "sentinel did not exit cleanly on the no-connection path";

    // 붙은 적이 없으니 판정도 없어야 한다 -- 감시자는 아무도 안 왔다는 것만
    // 알 뿐, 크래시를 본 적이 없다.
    maro::ipc::SentinelRecord record;
    const auto recordPath = maro::ipc::recordFilePath(bookDir, fakeMayaPid());
    ASSERT_TRUE(maro::ipc::readSentinelRecord(recordPath, record))
        << "sentinel never even wrote its record file -- it died before doing "
           "its startup work, so it cannot have waited for a connection";
    EXPECT_FALSE(record.lastSessionEndedCleanly.has_value())
        << "nobody ever connected, yet the sentinel recorded a verdict";
}

// [최종 리뷰 I1] SentinelRecord::sentinelInJob은 Task 8이 추가했지만, 그것이
// *탈출에 실패한* 감시자에 대해 실제로 true로 기록되는지를 확인하는 테스트가
// 지금까지 하나도 없었다. 위 CleanSessionEndsAndSentinelExits의 EXPECT_EQ는
// 감시자의 값을 gtest 프로세스의 실측값과 비교할 뿐이라, 두 값이 함께
// 잘못돼도(예: 둘 다 기본값 false) 통과한다.
//
// 여기서는 감시자를 breakaway를 불허하는 job 안에 일부러 가둔 뒤 그 job
// 소속 사실이 기록 파일까지 도달하는지를 끝에서 끝까지 고정한다. 위험한 job
// 조작은 도우미 프로세스(sentinel_in_job_helper.cpp)에 격리한다 --
// AssignProcessToJobObject는 되돌릴 수 없고, gtest는 모든 테스트를 한
// 프로세스에서 돌리므로 러너 자신을 job에 넣으면 그 뒤 모든 테스트가
// 영향을 받는다.
//
// 이 테스트가 증명하는 것과 아닌 것: 필드가 끝까지 배선돼 있다는 것을
// 증명한다(회귀를 잡는다). tier 2 승격 로직은 아직 존재하지 않으므로
// (SentinelRecord.h의 sentinelInJob 주석 참고) 그것에 대해서는 아무 말도
// 하지 않는다.
TEST(SentinelProcess, SentinelStuckInAJobRecordsThatItIsInAJob) {
    const auto bookDir = freshBookDir("in_job");

    std::string commandLine = "\"" + std::string(MARO_SENTINEL_IN_JOB_HELPER_EXE_PATH) +
                              "\" " + std::to_string(fakeMayaPid()) + " \"" +
                              bookDir.string() + "\"";

    STARTUPINFOA startupInfo{};
    startupInfo.cb = sizeof(startupInfo);
    PROCESS_INFORMATION helperInfo{};
    const BOOL created = ::CreateProcessA(nullptr, commandLine.data(), nullptr, nullptr,
                                          FALSE, 0, nullptr, nullptr, &startupInfo,
                                          &helperInfo);
    ASSERT_TRUE(created) << "could not launch maro_sentinel_in_job_helper.exe";
    // 도우미도 같은 RAII 규율로 감싼다 -- 아래 어느 ASSERT에서 빠져나가도
    // 핸들이 새거나 좀비가 남지 않는다.
    SentinelProcessGuard helper(helperInfo);

    // 감시자를 띄우고 바로 끝나는 프로세스라 10초는 넉넉한 상한이다.
    const DWORD helperWait = ::WaitForSingleObject(helper.info.hProcess, 10000);
    ASSERT_EQ(helperWait, WAIT_OBJECT_0) << "the in-job helper did not exit within 10s";

    DWORD helperExitCode = 1;
    ASSERT_TRUE(::GetExitCodeProcess(helper.info.hProcess, &helperExitCode));
    if (helperExitCode == 2) {
        GTEST_SKIP() << "helper could not set up its restrictive job on this machine "
                        "(likely a permissions/policy difference) -- not a maro_ipc bug";
    }
    ASSERT_EQ(helperExitCode, 0u)
        << "the helper did not manage to spawn the sentinel inside its job (exit code "
        << helperExitCode << ")";

    // 감시자는 뜨자마자 -- 접속을 기다리기 전에 -- 초기 기록을 쓴다
    // (main.cpp의 initialRecord). 그 파일이 온전히 파싱될 때까지 기다린다.
    maro::ipc::SentinelRecord record;
    const auto recordPath = maro::ipc::recordFilePath(bookDir, fakeMayaPid());
    ASSERT_TRUE(waitForRecord(recordPath, record, 10000))
        << "the sentinel never wrote a readable record file at " << recordPath.string();

    // 감시자 PID를 알았으니 이 시점부터 뒷정리가 보장된다. 아무도 접속하지
    // 않으면 감시자는 15초 뒤 스스로 나가지만, 그때까지 기다릴 이유가 없다.
    SentinelPidGuard sentinel{static_cast<DWORD>(record.sentinelPid)};
    ASSERT_NE(record.sentinelPid, 0u) << "the record file has no sentinel pid";

    // 이것이 이 테스트의 전부다: breakaway를 불허하는 job 안에서 태어난
    // 감시자는 자기가 job 안에 있다는 것을 관측하고 그것을 기록에 남긴다.
    EXPECT_TRUE(record.sentinelInJob)
        << "the sentinel was spawned inside a job that forbids breakaway, so its own "
           "isCurrentProcessInJob() self-check must have reported true -- the record "
           "file says false, which means the field is not actually wired from the "
           "self-check through to disk";
}
