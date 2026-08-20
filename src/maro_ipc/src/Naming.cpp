#include "maro_ipc/Naming.h"

namespace maro::ipc {

std::string pipeName(std::uint64_t pid) {
    return "\\\\.\\pipe\\maro_sentinel_" + std::to_string(pid);
}

std::string mutexName(std::uint64_t pid) {
    return "Global\\maro_sentinel_mutex_" + std::to_string(pid);
}

std::string killEventName(std::uint64_t pid) {
    return "Global\\maro_sentinel_kill_" + std::to_string(pid);
}

std::filesystem::path recordFilePath(const std::filesystem::path& bookDir, std::uint64_t pid) {
    return bookDir / ("maro_sentinel." + std::to_string(pid) + ".json");
}

}  // namespace maro::ipc
