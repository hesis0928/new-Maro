#include "MaroSentinelClient.h"

#include <windows.h>

#include <cstdint>
#include <filesystem>
#include <string>

#include "maro_ipc/JobEscape.h"
#include "maro_ipc/Message.h"
#include "maro_ipc/NamedPipe.h"
#include "maro_ipc/Naming.h"

#include "MaroDiag.h"

namespace maro {

namespace {

maro::ipc::NamedPipeClient& clientInstance() {
    static maro::ipc::NamedPipeClient client;
    return client;
}

bool& connectedFlag() {
    static bool connected = false;
    return connected;
}

// 감시자 실행 파일은 플러그인(maro.mll)과 같은 디렉터리에 있다고 가정한다
// (CMake가 그렇게 배치한다, Task 9 Step 4 참고). 그 디렉터리는 이 코드가
// 들어 있는 모듈 자신의 경로에서 얻는다 -- CWD나 PATH가 아니라.
//
// [브리프에서 고침] 브리프 원안은 modulePath를 초기화하지 않은 채로 두고
// GetModuleFileNameA의 반환값도 보지 않았다. 두 호출 중 하나라도 실패하면
// (GetModuleHandleExA는 nullptr 검사가 있었지만 GetModuleFileNameA는 없었다)
// 초기화되지 않은 스택 버퍼를 그대로 경로로 읽는다 -- 널 종결자가 없으면
// 버퍼 밖까지 읽고, 있으면 쓰레기 경로가 된다. 여기서는 버퍼를 0으로
// 초기화하고 반환값 0(실패)을 빈 경로로 돌려준다. 빈 경로를 spawnSentinel이
// 어떻게 다루는지는 그쪽 주석 참고.
std::filesystem::path sentinelExeDirectory() {
    char modulePath[MAX_PATH] = {};
    HMODULE thisModule = nullptr;
    ::GetModuleHandleExA(
        GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCSTR>(&sentinelExeDirectory), &thisModule);
    if (thisModule == nullptr) return {};
    if (::GetModuleFileNameA(thisModule, modulePath, MAX_PATH) == 0) return {};
    return std::filesystem::path(modulePath).parent_path();
}

bool spawnSentinel(std::uint64_t ownerPid, const std::filesystem::path& bookDir) {
    const std::filesystem::path exeDir = sentinelExeDirectory();
    // [브리프에서 고침] 자기 모듈 경로를 못 알아냈으면 여기서 포기한다.
    // 빈 경로에 파일 이름만 이어 붙이면 "maro_sentinel.exe"라는 *상대* 경로가
    // 되고, CreateProcessA는 그것을 현재 작업 디렉터리 기준으로 해석한다 --
    // Maya의 CWD는 사용자가 마지막으로 씬을 연 아무 폴더일 수 있으므로,
    // 거기 우연히(또는 고의로) 놓인 동명의 실행 파일을 감시자로 띄우게 된다.
    // 감시자 없이 진행하는 쪽이 언제나 낫다.
    if (exeDir.empty()) return false;

    const std::filesystem::path exePath = exeDir / "maro_sentinel.exe";
    const std::string args = std::to_string(ownerPid) + " \"" + bookDir.string() + "\"";

    // tier 1: CREATE_BREAKAWAY_FROM_JOB. 성공하면 우리는 자식을 기다리지도
    // 죽이지도 않으므로(감시자는 자기 수명을 스스로 관리한다) 두 핸들을
    // 즉시 닫는다 -- 안 닫으면 플러그인 로드마다 프로세스/스레드 커널
    // 오브젝트가 하나씩 새고, 죽은 감시자의 오브젝트가 계속 살아남는다.
    if (const auto tier1 = maro::ipc::spawnWithBreakaway(exePath.string(), args);
        tier1.has_value()) {
        ::CloseHandle(tier1->hProcess);
        ::CloseHandle(tier1->hThread);
        return true;
    }
    // tier 2: WMI. 이쪽은 PID만 돌려준다 -- 핸들이 아니므로 닫을 것이 없다
    // (PID를 CloseHandle에 넘기는 것은 그 자체로 오류다). 감시자 프로세스는
    // WMI 서비스 밑에서 만들어졌고 우리는 그것에 대한 핸들을 애초에 받은
    // 적이 없다.
    if (const auto tier2 = maro::ipc::spawnViaWmi(exePath.string(), args); tier2.has_value()) {
        return true;
    }
    // tier 3: 포기한다. 파이프 접속도 시도하지 않는다 -- 플러그인은 감시자
    // 없이 그대로 진행한다(기존 저널이 이미 항상 돌고 있다).
    return false;
}

}  // namespace

void MaroSentinelClient::connectOrSpawn() {
    if (connectedFlag()) return;

    try {
        const std::uint64_t ownerPid = ::GetCurrentProcessId();
        // 저널과 정확히 같은 디렉터리를 쓴다 -- BoadMaro::bookDirectory()가
        // journalDirectory()/bookPaths()의 이미 해소된 결과를 그대로
        // 돌려준다(Step 2에서 추가한 공개 접근자). 이 함수가 book 경로
        // 해석 규칙(MARO_DIAG_BOOK_DIR 환경변수 우선, 없으면 internalVar
        // -userAppDir)을 다시 구현하지 않는다 -- 두 곳에서 각자 해석하면
        // 저널이 겪었던 "우연히만 맞아떨어지던 두 번째 정의" 함정이
        // 재발한다. 실환경(테스트가 아닌 실제 사용자 세션)에는
        // MARO_DIAG_BOOK_DIR가 없는 것이 정상이므로, 이 호출이 그 경우도
        // internalVar -userAppDir로 알아서 해소해야 감시자가 테스트
        // 환경에서만 spawn되는 게 아니라 실제로 동작한다.
        const std::filesystem::path bookDir = maro::BoadMaro::bookDirectory();
        if (bookDir.empty()) return;

        if (!spawnSentinel(ownerPid, bookDir)) return;

        if (!clientInstance().connect(maro::ipc::pipeName(ownerPid), 5000)) return;

        maro::ipc::Message hello;
        hello.type = maro::ipc::MessageType::Hello;
        if (!clientInstance().sendMessage(hello)) {
            clientInstance().close();
            return;
        }
        connectedFlag() = true;
    } catch (...) {
        // 감시자 연결 실패는 플러그인 기능을 막지 않는다. 이 catch는
        // 선택이 아니다: 이 함수의 호출부는 initializePlugin(Maya 콜백
        // 경계)이고, 안쪽에는 실제로 던질 수 있는 호출이 여럿 있다 --
        // sendMessage()가 부르는 encodeMessage()의 nlohmann::json::dump()
        // (잘못된 UTF-8이면 type_error.316), spawnViaWmi()의 _bstr_t
        // 생성(할당 실패 시 _com_error), 그리고 모든 경로의 std::string/
        // std::filesystem::path 할당(bad_alloc).
    }
}

void MaroSentinelClient::notifyCleanExit() {
    if (!connectedFlag()) return;
    try {
        maro::ipc::Message sessionEnd;
        sessionEnd.type = maro::ipc::MessageType::SessionEndClean;
        clientInstance().sendMessage(sessionEnd);
    } catch (...) {
        // connectOrSpawn()과 같은 이유 -- 호출부가 uninitializePlugin이다.
        // sendMessage()는 encodeMessage()를 거치므로 던질 수 있다.
    }
}

void MaroSentinelClient::shutdown() {
    try {
        clientInstance().close();
    } catch (...) {
    }
    // 이 대입은 try 밖에 둔다 -- 위에서 무슨 일이 있었든 "이제 접속돼 있지
    // 않다"는 사실은 참이어야 하고, 이 대입 자체는 던질 수 없다(이미
    // 초기화된 정적 bool에의 대입).
    connectedFlag() = false;
}

}  // namespace maro
