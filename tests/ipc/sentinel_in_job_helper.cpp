// 스스로 breakaway를 불허하는 job에 들어간 뒤, 진짜 maro_sentinel.exe를
// 평범한 CreateProcess로 띄우는 일회용 도우미. 자식은 job을 상속하므로
// 감시자는 "탈출에 실패한" 상태로 시작한다 -- 그 상태에서 감시자가 기록
// 파일에 sentinelInJob=true를 실제로 남기는지를 test_sentinel_process.cpp의
// SentinelStuckInAJobRecordsThatItIsInAJob이 확인한다.
//
// 왜 gtest 프로세스가 직접 하지 않는가: job_escape_test_helper.cpp가 이미
// 같은 이유를 적어 두었다 -- 위험한 job 조작은 버릴 수 있는 서브프로세스에
// 격리한다. 여기서는 이유가 하나 더 있다. gtest는 한 프로세스에서 모든
// 테스트를 돌리는데, AssignProcessToJobObject는 되돌릴 수 없다. 테스트
// 러너 자신을 job에 넣으면 그 뒤의 모든 테스트가(그리고 그것들이 띄우는
// 모든 자식이) 영구히 그 job 안에서 돌게 된다.
//
// 사용법: maro_sentinel_in_job_helper.exe <owner_maya_pid> <book_dir>
// (감시자 실행 파일 경로는 빌드 시스템이 MARO_SENTINEL_EXE_PATH로 박아 준다 --
//  tests/CMakeLists.txt의 같은 정의를 maro_ipc_tests와 공유한다.)
//
// 종료 코드: 0 = job 안에서 감시자를 띄웠다, 2 = job 설정 자체가 실패
// (이 머신의 권한/정책 문제일 수 있어 테스트가 스킵으로 처리한다),
// 3 = 인자가 모자라다, 4 = job은 만들었는데 감시자 CreateProcess가 실패.
#include <windows.h>

#include <cstdio>
#include <string>

#include "maro_ipc/JobEscape.h"

int main(int argc, char** argv) {
    if (argc < 3) {
        std::fprintf(stderr,
                     "usage: maro_sentinel_in_job_helper.exe <owner_maya_pid> <book_dir>\n");
        return 3;
    }

    HANDLE job = ::CreateJobObjectA(nullptr, nullptr);
    if (job == nullptr) {
        std::fprintf(stderr, "CreateJobObjectA failed: %lu\n", ::GetLastError());
        return 2;
    }

    JOBOBJECT_EXTENDED_LIMIT_INFORMATION info{};
    // job_escape_test_helper.cpp와 같은 규율: LimitFlags를 비워 둔다.
    // 필요한 성질은 "JOB_OBJECT_LIMIT_BREAKAWAY_OK가 없다" 하나뿐이고,
    // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE는 **절대** 걸면 안 된다 -- 걸면
    // 아래 CloseHandle(job)이 이 프로세스를 죽일 뿐 아니라, 이 job의
    // 멤버로 막 태어난 감시자까지 함께 죽는다. 그러면 이 도우미가 존재하는
    // 이유(감시자가 살아서 기록 파일을 쓰는 것)가 사라진다.
    info.BasicLimitInformation.LimitFlags = 0;
    if (!::SetInformationJobObject(job, JobObjectExtendedLimitInformation, &info,
                                   sizeof(info))) {
        std::fprintf(stderr, "SetInformationJobObject failed: %lu\n", ::GetLastError());
        ::CloseHandle(job);
        return 2;
    }

    if (!::AssignProcessToJobObject(job, ::GetCurrentProcess())) {
        std::fprintf(stderr, "AssignProcessToJobObject failed: %lu\n", ::GetLastError());
        ::CloseHandle(job);
        return 2;
    }

    if (!maro::ipc::isCurrentProcessInJob()) {
        std::fprintf(stderr, "isCurrentProcessInJob() false right after joining a job\n");
        ::CloseHandle(job);
        return 2;
    }

    // CREATE_BREAKAWAY_FROM_JOB을 **쓰지 않는다** -- 이 도우미의 목적은
    // 탈출에 실패한 감시자를 만드는 것이다. 평범한 CreateProcess로 띄우면
    // 자식은 이 프로세스의 job을 그대로 물려받는다.
    std::string commandLine = std::string("\"") + MARO_SENTINEL_EXE_PATH + "\" " + argv[1] +
                              " \"" + argv[2] + "\"";

    STARTUPINFOA startupInfo{};
    startupInfo.cb = sizeof(startupInfo);
    PROCESS_INFORMATION processInfo{};
    const BOOL created = ::CreateProcessA(nullptr, commandLine.data(), nullptr, nullptr,
                                          FALSE, 0, nullptr, nullptr, &startupInfo,
                                          &processInfo);
    if (!created) {
        std::fprintf(stderr, "CreateProcessA for the sentinel failed: %lu\n",
                     ::GetLastError());
        ::CloseHandle(job);
        return 4;
    }

    // 감시자를 기다리지도 죽이지도 않는다 -- 자기 수명은 스스로 관리하고,
    // 뒷정리는 테스트 쪽 RAII 가드가 맡는다. 여기서 할 일은 우리 몫의
    // 핸들을 놓아 주는 것뿐이다.
    ::CloseHandle(processInfo.hProcess);
    ::CloseHandle(processInfo.hThread);

    // KILL_ON_JOB_CLOSE가 없으므로 이 핸들을 닫아도 job은 멤버(감시자)가
    // 살아 있는 동안 유지되고, 감시자는 계속 job 안에 있다.
    ::CloseHandle(job);
    return 0;
}
