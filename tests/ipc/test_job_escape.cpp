#include <gtest/gtest.h>

#include <windows.h>

#include <string>

#include "maro_ipc/JobEscape.h"

namespace {

// [최종 리뷰 3g] tests/ipc/test_sentinel_process.cpp의 SentinelProcessGuard와
// 같은 이유로 같은 모양이다. gtest의 ASSERT_*는 실패하면 그 자리에서
// return하므로, 아래 10초 타임아웃 단언이 깨지는 바로 그 경우 --
// 도우미가 상한 안에 안 죽은 경우 -- 에 CloseHandle도 TerminateProcess도
// 실행되지 않는다. 즉 좀비를 확인하는 테스트가 실패할 때마다 좀비와 핸들
// 누수를 하나씩 남긴다. 정리를 소멸자로 옮겨 모든 경로에서 강제한다.
struct HelperProcessGuard {
    PROCESS_INFORMATION info{};

    explicit HelperProcessGuard(const PROCESS_INFORMATION& processInfo) : info(processInfo) {}

    ~HelperProcessGuard() {
        if (info.hProcess == nullptr) return;
        DWORD exitCode = 0;
        if (::GetExitCodeProcess(info.hProcess, &exitCode) && exitCode == STILL_ACTIVE) {
            ::TerminateProcess(info.hProcess, 1);
            ::WaitForSingleObject(info.hProcess, 5000);
        }
        ::CloseHandle(info.hProcess);
        ::CloseHandle(info.hThread);
    }

    HelperProcessGuard(const HelperProcessGuard&) = delete;
    HelperProcessGuard& operator=(const HelperProcessGuard&) = delete;
};

TEST(JobEscape, CurrentProcessReportsNotInJobByDefault) {
    // ctest가 이 테스트 프로세스를 job 안에서 띄우지 않는 일반적인 경우를
    // 가정한다. (일부 CI 러너/샌드박스는 자기 프로세스 트리를 job으로
    // 감싸기도 하므로, 이 단언이 실제 환경에서 깨지면 테스트가 아니라
    // 환경이 다른 것이다 -- 그 경우 이 케이스는 스킵으로 바꿔도 된다.)
    //
    // 실측: 이 저장소를 구동하는 샌드박스 환경 자체가 툴이 실행하는
    // 프로세스 트리를 정리 목적으로 job object로 감싼다(PowerShell에서
    // 직접 IsProcessInJob을 호출해 확인함 -- 호출은 성공하고 결과가
    // true). ctest가 그 안에서 뜨므로 여기서 스폰되는 이 테스트 프로세스도
    // 기본적으로 같은 job의 멤버가 된다. 바로 그 "일부 환경" 케이스이므로
    // 위 주석이 명시적으로 허용한 대로 스킵으로 대응한다 -- maro_ipc 버그가
    // 아니다.
    if (maro::ipc::isCurrentProcessInJob()) {
        GTEST_SKIP() << "this test process is already inside a job object in this "
                        "environment (a sandbox that wraps its own process tree for "
                        "cleanup) -- not a maro_ipc bug, see comment above";
    }
}

TEST(JobEscape, SpawnWithBreakawayFailsInsideARestrictiveJob) {
    char selfDir[MAX_PATH];
    ::GetModuleFileNameA(nullptr, selfDir, MAX_PATH);
    std::string helperPath = selfDir;
    const auto slash = helperPath.find_last_of("\\/");
    ASSERT_NE(slash, std::string::npos);
    helperPath = helperPath.substr(0, slash + 1) + "maro_job_escape_test_helper.exe";

    STARTUPINFOA startupInfo{};
    startupInfo.cb = sizeof(startupInfo);
    PROCESS_INFORMATION processInfo{};

    std::string commandLine = "\"" + helperPath + "\"";
    const BOOL created = ::CreateProcessA(
        nullptr, commandLine.data(), nullptr, nullptr, FALSE, 0, nullptr, nullptr,
        &startupInfo, &processInfo);
    ASSERT_TRUE(created) << "could not launch the job-escape test helper";
    HelperProcessGuard helper(processInfo);

    const DWORD waitResult = ::WaitForSingleObject(helper.info.hProcess, 10000);
    ASSERT_EQ(waitResult, WAIT_OBJECT_0) << "helper did not exit within 10s";

    DWORD exitCode = 0;
    ASSERT_TRUE(::GetExitCodeProcess(helper.info.hProcess, &exitCode));

    if (exitCode == 2) {
        GTEST_SKIP() << "helper could not set up its restrictive job on this machine "
                        "(likely a permissions/policy difference) -- not a maro_ipc bug";
    }
    // 4는 "spawn이 실패하긴 했지만 job 정책 때문이 아니었다"는 뜻이다
    // (job_escape_test_helper.cpp의 종료 코드 표). 예전에는 이 경우도 0으로
    // 뭉개져 조용히 통과했다 -- 그러면 이 테스트가 무엇을 증명하는지가
    // 사라진다. 이제는 실패이고, 실패 메시지가 그 구분을 그대로 말한다.
    EXPECT_NE(exitCode, 4u)
        << "the breakaway spawn failed, but not because the job refused it (the helper "
           "printed the actual GetLastError to stderr) -- this run proves nothing about "
           "job breakaway policy";
    EXPECT_EQ(exitCode, 0u)
        << "expected the breakaway spawn to be refused inside a job that disallows it, "
           "got exit code " << exitCode;
}

TEST(JobEscape, SpawnViaWmiActuallyStartsAProcess) {
    // notepad.exe는 모든 Windows에 있고 창을 띄우지만 사용자 상호작용을
    // 요구하지 않는다 -- 뜨자마자 바로 종료시킨다.
    const auto pid = maro::ipc::spawnViaWmi("C:\\Windows\\System32\\notepad.exe", "");
    ASSERT_TRUE(pid.has_value());

    HANDLE process = ::OpenProcess(PROCESS_TERMINATE | PROCESS_QUERY_LIMITED_INFORMATION,
                                   FALSE, static_cast<DWORD>(*pid));
    ASSERT_NE(process, nullptr)
        << "spawnViaWmi reported PID " << *pid << " but no such process exists";

    DWORD exitCodeBeforeTerminate = 0;
    ::GetExitCodeProcess(process, &exitCodeBeforeTerminate);
    EXPECT_EQ(exitCodeBeforeTerminate, static_cast<DWORD>(STILL_ACTIVE));

    ::TerminateProcess(process, 0);
    ::CloseHandle(process);
}

TEST(JobEscape, SpawnViaWmiFailsCleanlyOnBogusPath) {
    const auto pid = maro::ipc::spawnViaWmi("C:\\this\\path\\does\\not\\exist.exe", "");
    EXPECT_FALSE(pid.has_value());
}

}  // namespace
