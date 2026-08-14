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

        // 이전 프로세스가 줄 쓰는 도중 죽었다면 파일이 개행 없이 끝나
        // 있을 수 있다. 그 위에 그대로 append하면 남은 조각과 새 레코드가
        // 하나의 파싱 불가능한 줄로 합쳐져 새 레코드까지 함께 사라진다 --
        // 그러므로 파일이 비어 있지 않은데 마지막 바이트가 개행이 아니면
        // 먼저 개행을 하나 써서 새 레코드가 항상 제 줄에서 시작하게 한다.
        std::error_code sizeEc;
        const auto existingSize = std::filesystem::file_size(spillPath, sizeEc);
        if (!sizeEc && existingSize > 0) {
            std::ifstream check(spillPath, std::ios::binary);
            if (check) {
                check.seekg(-1, std::ios::end);
                char lastByte = '\0';
                if (check.get(lastByte) && lastByte != '\n') {
                    std::ofstream fixup(spillPath, std::ios::app | std::ios::binary);
                    if (fixup) {
                        fixup << '\n';
                        fixup.flush();
                    }
                }
            }
        }

        std::ofstream ofs(spillPath, std::ios::app);
        if (!ofs) return false;

        ofs << entryToJson(errorHash, entry).dump() << '\n';
        // 스트림 버퍼에만 앉아 있는 바이트는 디스크에 나간 게 아니다 --
        // 명시적으로 flush하고, flush 이후의 스트림 상태를 돌려줘야 늦은
        // 쓰기 실패가 이미 반환된 true를 뒤집지 못하는 일이 없다.
        ofs.flush();
        return static_cast<bool>(ofs);
    } catch (...) {
        // book이 죽어도 진단은 죽지 않는다 (스펙 §3.6).
        return false;
    }
}

}  // namespace maro
