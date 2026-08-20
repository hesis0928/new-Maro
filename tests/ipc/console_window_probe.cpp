// 콘솔 창이 실제로 뜨는지를 "눈으로 보지 않고" 관측하기 위한 일회용 도우미.
//
// 왜 필요한가: maro_sentinel.exe는 콘솔 서브시스템 실행 파일이고, 그것을
// 띄우는 Maya.exe는 GUI 서브시스템이라 콘솔이 없다. Windows는 콘솔이 없는
// 부모가 콘솔 프로그램을 자식으로 만들면 *새 콘솔 창*을 할당해 보여 준다 --
// 그 창은 감시자가 사는 내내(최대 12시간) 사용자 화면에 남는다. 이걸 막는
// 것이 CREATE_NO_WINDOW다.
//
// 문제는 이 조건을 재현하기가 미묘하다는 점이다. gtest 실행 파일
// (maro_ipc_tests.exe)도, mayapy.exe도 *콘솔 프로그램*이라 이미 콘솔을
// 가지고 있고, 그 밑에서 태어난 자식은 부모 콘솔을 물려받으므로 새 창이
// 아예 뜨지 않는다 -- 플래그가 있든 없든 똑같아 보인다(Task 10의 mayapy
// 종단 테스트가 이 버그를 구조적으로 못 잡는 이유가 바로 이것이다).
//
// 그래서 이 도우미는 두 역할을 한다:
//
//   probe spawn <tier> <outfile>
//       "Maya" 역할. 테스트가 이 모드를 DETACHED_PROCESS로 띄우므로 이
//       프로세스는 콘솔이 전혀 없다 -- GUI 서브시스템인 Maya.exe와 같은
//       상태다. 여기서 maro_ipc의 진짜 spawn 함수(tier 1 = spawnWithBreakaway,
//       tier 2 = spawnViaWmi)로 아래 report 모드를 띄운다. 자기 자신의
//       콘솔 상태는 <outfile>.parent에 적어 두어, 테스트가 "정말 콘솔이
//       없는 부모였는가"라는 전제 자체를 검증할 수 있게 한다.
//
//   probe report <outfile>
//       "maro_sentinel" 역할. 자기 콘솔 상태를 <outfile>에 적고 끝난다.
//       콘솔 프로그램이므로, 콘솔 없는 부모가 플래그 없이 띄우면 여기서
//       새 콘솔이 잡힌다.
//
// 관측 신호는 GetConsoleWindow()다: 이 프로세스에 붙은 콘솔의 창 핸들이며,
// 콘솔 자체가 없으면 NULL이다. 창이 있으면 IsWindowVisible로 실제로 보이는
// 창인지까지 함께 기록한다(CREATE_NO_WINDOW가 "콘솔은 있는데 창만 숨김"인지
// "콘솔 자체가 없음"인지 문서가 모호해서, 추측 대신 실측한다).
//
// 종료 코드(spawn 모드): 0 = spawn 성공, 1 = spawn 실패, 2 = 인자 오류.
#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

#include "maro_ipc/JobEscape.h"

namespace {

// 콘솔 상태 한 줄을 파일로 남긴다. 파이프나 stdout이 아니라 파일인 이유는
// 명확하다: 이 프로세스는 콘솔이 없을 수도 있어(그게 검증하려는 바로 그
// 조건이다) stdout 자체를 신뢰할 수 없다.
bool writeReport(const char* path) {
    const HWND consoleWindow = ::GetConsoleWindow();
    const int visible =
        (consoleWindow != nullptr && ::IsWindowVisible(consoleWindow)) ? 1 : 0;

    std::FILE* file = nullptr;
    if (::fopen_s(&file, path, "wb") != 0 || file == nullptr) return false;
    std::fprintf(file, "pid=%lu console=%llu visible=%d\n", ::GetCurrentProcessId(),
                 static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(consoleWindow)),
                 visible);
    std::fclose(file);
    return true;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 3) {
        return 2;
    }

    if (std::strcmp(argv[1], "report") == 0) {
        return writeReport(argv[2]) ? 0 : 1;
    }

    if (std::strcmp(argv[1], "spawn") != 0 || argc < 4) {
        return 2;
    }

    const std::string tier = argv[2];
    const std::string outPath = argv[3];

    // 부모(=이 프로세스)의 콘솔 상태를 먼저 남긴다. 테스트는 이 파일로
    // "콘솔 없는 부모"라는 전제가 실제로 성립했는지 확인한다 -- 전제가
    // 깨진 채로 통과하는 테스트는 아무것도 증명하지 못한다.
    writeReport((outPath + ".parent").c_str());

    char selfPath[MAX_PATH] = {};
    if (::GetModuleFileNameA(nullptr, selfPath, MAX_PATH) == 0) return 1;

    // 경로에 공백이 있어도 자식의 CRT가 argv를 제대로 나누도록 따옴표를 씌운다.
    const std::string args = "report \"" + outPath + "\"";

    if (tier == "1") {
        const auto info = maro::ipc::spawnWithBreakaway(selfPath, args);
        if (!info.has_value()) return 1;
        ::WaitForSingleObject(info->hProcess, 10000);
        ::CloseHandle(info->hProcess);
        ::CloseHandle(info->hThread);
        return 0;
    }

    if (tier == "2") {
        const auto pid = maro::ipc::spawnViaWmi(selfPath, args);
        if (!pid.has_value()) return 1;
        // WMI로 만든 프로세스는 이쪽 자식이 아니라 WMI 서비스 밑에 생기므로
        // 핸들을 받지 못한다 -- PID로 열어서 끝나기를 기다린다. 열리지
        // 않으면(이미 끝났거나 권한이 없으면) 그냥 넘어간다: 테스트가
        // 결과 파일을 폴링하므로 여기서의 대기는 편의일 뿐이다.
        HANDLE handle = ::OpenProcess(SYNCHRONIZE, FALSE, static_cast<DWORD>(*pid));
        if (handle != nullptr) {
            ::WaitForSingleObject(handle, 10000);
            ::CloseHandle(handle);
        }
        return 0;
    }

    return 2;
}
