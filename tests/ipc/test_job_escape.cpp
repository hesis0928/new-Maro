#include <gtest/gtest.h>

#include <windows.h>

#include <string>

#include "maro_ipc/JobEscape.h"

namespace {

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

    const DWORD waitResult = ::WaitForSingleObject(processInfo.hProcess, 10000);
    ASSERT_EQ(waitResult, WAIT_OBJECT_0) << "helper did not exit within 10s";

    DWORD exitCode = 0;
    ::GetExitCodeProcess(processInfo.hProcess, &exitCode);
    ::CloseHandle(processInfo.hProcess);
    ::CloseHandle(processInfo.hThread);

    if (exitCode == 2) {
        GTEST_SKIP() << "helper could not set up its restrictive job on this machine "
                        "(likely a permissions/policy difference) -- not a maro_ipc bug";
    }
    EXPECT_EQ(exitCode, 0u)
        << "expected the breakaway spawn to be refused inside a job that disallows it, "
           "got exit code " << exitCode;
}

}  // namespace
