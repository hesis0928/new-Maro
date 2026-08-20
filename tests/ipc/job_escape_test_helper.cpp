// 스스로 breakaway를 불허하는 job에 들어간 뒤, spawnWithBreakaway로
// 손자 프로세스를 띄우는 것이 실제로 거부되는지 확인하는 일회용 도우미.
// test_job_escape.cpp가 이것을 서브프로세스로 띄워 종료 코드를 읽는다 --
// 위험한 job 조작을 gtest 프로세스 자신이 아니라 여기에 격리한다.
//
// 종료 코드: 0 = 예상대로, **job 정책 때문에** 거부됨(탈출 실패), 1 = 예상과
// 다르게 성공함 (job이 breakaway를 막았어야 하는데 자식이 spawn됨), 2 = 설정
// 자체가 실패 (job 생성/할당 실패 -- 이 머신의 권한 문제일 수 있어 테스트가
// 이 경우를 스킵으로 처리한다), 3 = --child로 재실행된 손자가 즉시 빠져나감,
// 4 = spawn이 실패하긴 했는데 **job 정책과 무관한 이유**로 실패했다.
//
// [최종 리뷰 3f] 4번이 새로 생긴 이유: 예전에는 spawnWithBreakaway가
// nullopt를 주면 무조건 0("보안 장치가 제대로 동작했다")을 돌려줬다. 그런데
// nullopt는 CreateProcess가 어떤 이유로 실패하든 나온다 -- 실행 파일 경로가
// 틀렸거나(ERROR_FILE_NOT_FOUND), 메모리가 모자라거나. 그러면 "테스트하려던
// 보안 메커니즘이 동작했다"와 "엉뚱한 데서 사고가 났다"가 같은 통과로
// 뭉개진다. 이제 GetLastError를 보고 job 정책 거부(ERROR_ACCESS_DENIED)일
// 때만 0을 돌려준다.
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
    // 실질적인 부작용이 없다는 논리였다. 이 전제는 예전 버전에서 깨졌다:
    // 그때는 이 job에 JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE가 걸려 있었고,
    // 부모 자신이 그 job의 멤버이면서 유일한 핸들 소유자였다. 그러면
    // CloseHandle(job)이 마지막 핸들을 닫는 순간 Windows가 부모를 반드시
    // 죽인다 -- 레이스가 아니라 결정론적 동작이다(15/15 추적 실행 전부
    // 동일). 부모는 자기 자식을 정리하지 못한 채 죽고, 고아가 된 자식이
    // 손자를 낳는 사슬이 이어졌다. 지금은 아래에서 KILL_ON_JOB_CLOSE를
    // 아예 걸지 않으므로 근본 원인이 사라졌지만, --child 가드는 방어
    // 차원에서 그대로 둔다(비용이 없다).
    if (argc > 1 && std::strcmp(argv[1], "--child") == 0) {
        return 3;
    }

    HANDLE job = ::CreateJobObjectA(nullptr, nullptr);
    if (job == nullptr) {
        std::fprintf(stderr, "CreateJobObjectA failed: %lu\n", ::GetLastError());
        return 2;
    }

    JOBOBJECT_EXTENDED_LIMIT_INFORMATION info{};
    // LimitFlags를 비워 둔다. 이 테스트에 필요한 성질은 단 하나,
    // "JOB_OBJECT_LIMIT_BREAKAWAY_OK가 없다"는 것이다 -- 그것만으로 job은
    // CREATE_BREAKAWAY_FROM_JOB을 거부한다. 특히
    // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE는 절대 걸면 안 된다: 이 프로세스가
    // 자기 job의 멤버이자 그 job의 유일한 핸들 소유자이므로, 그 플래그가
    // 있으면 아래 CloseHandle(job)이 마지막 핸들을 닫는 순간 Windows가 이
    // 프로세스를 죽인다. 그러면 그 뒤의 return 0 / return 1이 둘 다 도달
    // 불가능해지고, job에 죽은 프로세스의 종료 코드는 0이라서 테스트가
    // spawnWithBreakaway의 실제 결과와 무관하게 항상 통과하는 -- 즉 아무것도
    // 검증하지 못하는 -- 테스트가 된다.
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
    // 이 줄은 반드시 위 호출 **바로 다음**이어야 한다. spawnWithBreakaway가
    // nullopt를 돌려주는 경로는 CreateProcessA 실패 하나뿐이고(JobEscape.cpp),
    // 그 실패가 세운 스레드-로컬 last-error를 여기서 읽는다. 사이에 Win32
    // 호출을 하나라도 끼우면(예: 원래 여기 있던 CloseHandle(job)) 그 호출이
    // 값을 덮어써서 아래 판정이 무의미해진다 -- 그래서 CloseHandle을 이
    // 캡처 뒤로 옮겼다.
    const DWORD spawnError = ::GetLastError();

    ::CloseHandle(job);

    if (childInfo.has_value()) {
        // 성공적으로 spawn됐다 -- 이 job은 애초에 breakaway를 허용하지
        // 않았으니 이 결과는 예상 밖이다(또는 이 Windows 버전/구성이 이
        // 제한을 다르게 다룬다는 뜻).
        ::TerminateProcess(childInfo->hProcess, 0);
        ::CloseHandle(childInfo->hProcess);
        ::CloseHandle(childInfo->hThread);
        std::fprintf(stderr, "helper: spawnWithBreakaway UNEXPECTEDLY SUCCEEDED, exiting 1\n");
        return 1;
    }
    // spawn이 실패했다. 그 실패가 이 테스트가 확인하려는 것 -- job 정책에
    // 의한 거부 -- 인지를 last-error로 가른다. job이 CREATE_BREAKAWAY_FROM_JOB을
    // 허용하지 않을 때 CreateProcess가 세우는 값은 ERROR_ACCESS_DENIED다.
    if (spawnError != ERROR_ACCESS_DENIED) {
        std::fprintf(stderr,
                     "helper: spawnWithBreakaway failed for an unexpected reason "
                     "(GetLastError=%lu, not ERROR_ACCESS_DENIED) -- this says nothing "
                     "about job breakaway policy, exiting 4\n",
                     spawnError);
        return 4;
    }

    // 여기까지 왔다는 것 자체가 증거다: 이 프로세스는 CloseHandle(job)에서
    // 죽지 않고 살아남아, 실제 거부를 직접 관측한 뒤 0을 돌려준다.
    std::fprintf(stderr,
                 "helper: spawnWithBreakaway refused by job policy as expected "
                 "(GetLastError=%lu), exiting 0\n",
                 spawnError);
    return 0;
}
