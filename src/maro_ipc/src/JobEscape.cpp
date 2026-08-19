#include "maro_ipc/JobEscape.h"

namespace maro::ipc {

bool isCurrentProcessInJob() {
    BOOL result = FALSE;
    if (!::IsProcessInJob(::GetCurrentProcess(), nullptr, &result)) {
        // 조회 자체가 실패하면 "모른다"를 "아니다"로 취급하지 않는다 --
        // 탈출 여부를 낙관적으로 판단하면 이 검사를 두는 의미가 없다.
        // 대신 "안전하지 않을 수 있다"는 쪽으로 true를 돌려준다.
        return true;
    }
    return result != FALSE;
}

std::optional<PROCESS_INFORMATION> spawnWithBreakaway(const std::string& exePath,
                                                        const std::string& args) {
    STARTUPINFOA startupInfo{};
    startupInfo.cb = sizeof(startupInfo);
    PROCESS_INFORMATION processInfo{};

    std::string commandLine = "\"" + exePath + "\"";
    if (!args.empty()) {
        commandLine += " " + args;
    }

    const BOOL created = ::CreateProcessA(
        exePath.c_str(),
        commandLine.data(),  // CreateProcessA가 이 버퍼를 수정할 수 있다 -- data()는 non-const.
        nullptr, nullptr, FALSE,
        CREATE_BREAKAWAY_FROM_JOB,
        nullptr, nullptr, &startupInfo, &processInfo);

    if (!created) return std::nullopt;
    return processInfo;
}

}  // namespace maro::ipc
