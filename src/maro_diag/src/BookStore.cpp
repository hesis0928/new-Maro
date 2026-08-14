#include "maro_diag/BookStore.h"

#include <fstream>
#include <system_error>

#include <nlohmann/json.hpp>

namespace maro {

namespace {

BookEntry entryFromJson(const nlohmann::json& j) {
    BookEntry e;
    e.analysis = j.value("analysis", std::string());
    e.remedy = j.value("remedy", std::string());
    e.context.nodeType = j.value("nodeType", std::string());
    e.context.attributeName = j.value("attributeName", std::string());
    e.context.activeCommand = j.value("activeCommand", std::string());
    e.context.axisOrTarget = j.value("axisOrTarget", std::string());
    return e;
}

nlohmann::json entryToJson(const std::string& hash, const BookEntry& e) {
    nlohmann::json j;
    j["hash"] = hash;
    j["analysis"] = e.analysis;
    j["remedy"] = e.remedy;
    j["nodeType"] = e.context.nodeType;
    j["attributeName"] = e.context.attributeName;
    j["activeCommand"] = e.context.activeCommand;
    j["axisOrTarget"] = e.context.axisOrTarget;
    return j;
}

}  // namespace

void BookStore::loadFile(const std::filesystem::path& path,
                          std::unordered_map<std::string, BookEntry>& out) {
    if (path.empty()) return;

    std::error_code ec;
    if (!std::filesystem::exists(path, ec) || ec) return;

    std::ifstream ifs(path);
    if (!ifs) return;

    std::string line;
    while (std::getline(ifs, line)) {
        if (line.empty()) continue;
        try {
            const nlohmann::json j = nlohmann::json::parse(line);
            const std::string hash = j.value("hash", std::string());
            if (hash.empty()) continue;
            out[hash] = entryFromJson(j);
        } catch (const nlohmann::json::exception&) {
            // 깨진 줄 하나 때문에 나머지 지식까지 버리지 않는다.
            continue;
        }
    }
}

BookStore BookStore::loadMerged(const std::filesystem::path& canonicalPath,
                                 const std::filesystem::path& spillPath) {
    BookStore store;
    // 정본을 먼저 채우고 스필로 덮어쓴다 -- 같은 해시가 양쪽에 있으면
    // 스필이 이긴다. 스필은 감시자가 아직 흡수하지 못한, 더 최신인 지식이기
    // 때문이다 (스펙 §5.4).
    loadFile(canonicalPath, store.entries_);
    loadFile(spillPath, store.entries_);
    return store;
}

bool BookStore::query(const std::string& errorHash, BookEntry& out) const {
    const auto it = entries_.find(errorHash);
    if (it == entries_.end()) return false;
    out = it->second;
    return true;
}

bool BookStore::appendToSpill(const std::filesystem::path& spillPath,
                               const std::string& errorHash,
                               const BookEntry& entry) {
    if (spillPath.empty()) return false;
    try {
        std::error_code ec;
        std::filesystem::create_directories(spillPath.parent_path(), ec);

        std::ofstream ofs(spillPath, std::ios::app);
        if (!ofs) return false;

        ofs << entryToJson(errorHash, entry).dump() << '\n';
        return static_cast<bool>(ofs);
    } catch (...) {
        // book이 죽어도 진단은 죽지 않는다 (스펙 §3.6).
        return false;
    }
}

}  // namespace maro
