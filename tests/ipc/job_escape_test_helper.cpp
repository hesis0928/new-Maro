// 스스로 breakaway를 불허하는 job에 들어간 뒤, spawnWithBreakaway로
// 손자 프로세스를 띄우는 것이 실제로 거부되는지 확인하는 일회용 도우미.
// test_job_escape.cpp가 이것을 서브프로세스로 띄워 종료 코드를 읽는다 --
// 위험한 job 조작을 gtest 프로세스 자신이 아니라 여기에 격리한다.
//
// 종료 코드: 0 = 예상대로 거부됨(탈출 실패), 1 = 예상과 다르게 성공함
// (job이 breakaway를 막았어야 하는데 자식이 spawn됨), 2 = 설정 자체가 실패
// (job 생성/할당 실패 -- 이 머신의 권한 문제일 수 있어 테스트가 이 경우를
// 스킵으로 처리한다).
#include <windows.h>

#include <cstdio>
#include <cstring>

#include "maro_ipc/JobEscape.h"

int main(int argc, char** argv) {
    // 재실행된 손자(--child)는 이 게임에 참여하지 않고 바로 끝난다.
    //
    // 원래 브리프의 주석은 "별도 분기 없이 그대로 둔다"고 했다 -- 손자가
    // 같은 main()을 타서 자기 job을 또 만들고 spawnWithBreakaway를 또
    // 시도하더라도, 부모가 spawn 직후 TerminateProcess로 곧장 정리하니
    // 실질적인 부작용이 없다는 논리였다. Step 8(고의로 breakaway를
    // 허용해 봄)에서 실측한 결과 이 전제가 깨진다: 부모 자신도 자기
    // job에 JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE로 들어가 있어서, spawn 직후
    // CloseHandle(job)이 부모를 비동기로 죽이는 레이스가 TerminateProcess
    // 호출보다 먼저 이기는 경우가 실제로 있었다 -- 그러면 부모는 자기
    // 자식을 정리하지 못한 채 죽고, 고아가 된 자식이 손자를 낳고, 그
    // 손자도 똑같이 고아가 되어 또 손자를 낳는 식으로 프로세스가 끝없이
    // 이어지는 것을 직접 목격했다(수 초 안에 세대가 계속 바뀌며 실행
    // 중인 프로세스가 관찰됨). --child는 그 사슬을 여기서 끊는다.
    if (argc > 1 && std::strcmp(argv[1], "--child") == 0) {
        return 3;
    }

    HANDLE job = ::CreateJobObjectA(nullptr, nullptr);
    if (job == nullptr) {
        std::fprintf(stderr, "CreateJobObjectA failed: %lu\n", ::GetLastError());
        return 2;
    }

    JOBOBJECT_EXTENDED_LIMIT_INFORMATION info{};
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    // 일부러 JOB_OBJECT_LIMIT_BREAKAWAY_OK를 안 건다 -- 이 job은 탈출을 막는다.
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

    bool selfReportsInJob = maro::ipc::isCurrentProcessInJob();
    if (!selfReportsInJob) {
        std::fprintf(stderr, "isCurrentProcessInJob() false right after joining a job\n");
        ::CloseHandle(job);
        return 2;
    }

    char selfPath[MAX_PATH];
    ::GetModuleFileNameA(nullptr, selfPath, MAX_PATH);
    // 자기 자신을 --child로 다시 실행해 손자로 삼는다 -- 존재하는 실행
    // 파일이면 뭐든 되므로 새 바이너리를 안 만들어도 된다.
    const auto childInfo = maro::ipc::spawnWithBreakaway(selfPath, "--child");

    ::CloseHandle(job);

    if (childInfo.has_value()) {
        // 성공적으로 spawn됐다 -- 이 job은 애초에 breakaway를 허용하지
        // 않았으니 이 결과는 예상 밖이다(또는 이 Windows 버전/구성이 이
        // 제한을 다르게 다룬다는 뜻).
        ::TerminateProcess(childInfo->hProcess, 0);
        ::CloseHandle(childInfo->hProcess);
        ::CloseHandle(childInfo->hThread);
        return 1;
    }
    return 0;
}
