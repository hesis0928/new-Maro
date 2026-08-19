#include "maro_ipc/SentinelRecord.h"

#include <fstream>

#include <nlohmann/json.hpp>

namespace maro::ipc {

bool writeSentinelRecord(const std::filesystem::path& path, const SentinelRecord& record) {
    try {
        std::error_code ec;
        std::filesystem::create_directories(path.parent_path(), ec);

        nlohmann::json j;
        j["sentinelPid"] = record.sentinelPid;
        j["ownerMayaPid"] = record.ownerMayaPid;
        j["startTimeMs"] = record.startTimeMs;
        j["sentinelInJob"] = record.sentinelInJob;
        if (record.lastSessionEndedCleanly.has_value()) {
            j["lastSessionEndedCleanly"] = *record.lastSessionEndedCleanly;
        }

        std::ofstream out(path, std::ios::out | std::ios::trunc | std::ios::binary);
        if (!out.is_open()) return false;
        out << j.dump();
        return out.good();
    } catch (...) {
        return false;
    }
}

bool readSentinelRecord(const std::filesystem::path& path, SentinelRecord& out) {
    try {
        std::ifstream in(path, std::ios::binary);
        if (!in.is_open()) return false;

        nlohmann::json j;
        in >> j;

        SentinelRecord record;
        record.sentinelPid = j.at("sentinelPid").get<std::uint64_t>();
        record.ownerMayaPid = j.at("ownerMayaPid").get<std::uint64_t>();
        record.startTimeMs = j.at("startTimeMs").get<std::uint64_t>();
        record.sentinelInJob = j.at("sentinelInJob").get<bool>();
        if (j.contains("lastSessionEndedCleanly")) {
            record.lastSessionEndedCleanly = j.at("lastSessionEndedCleanly").get<bool>();
        }
        out = record;
        return true;
    } catch (...) {
        return false;
    }
}

}  // namespace maro::ipc
