#include "maro_diag/JournalReader.h"

#include <sstream>

#include <nlohmann/json.hpp>

#include "maro_diag/Journal.h"

namespace maro {

std::vector<JournalSession> parseJournal(const std::string& text) {
    std::vector<JournalSession> sessions;
    std::istringstream in(text);
    std::string line;

    while (std::getline(in, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty()) continue;

        nlohmann::json j;
        try {
            j = nlohmann::json::parse(line);
        } catch (...) {
            // 깨진 줄 하나가 나머지를 포기시키지 않는다.
            continue;
        }

        std::string kind;
        try {
            kind = j.value("kind", std::string());
            if (kind == "session") {
                const std::string event = j.value("event", std::string());
                if (event == "open") {
                    sessions.emplace_back();
                } else if (event == "close" && !sessions.empty()) {
                    sessions.back().endedCleanly = true;
                }
            }
        } catch (...) {
            // kind나 event가 기대한 타입이 아니거나 (예: 숫자) 줄 자체가
            // 객체가 아니면(예: 알몸 스칼라 줄) 이 줄만 버리고 계속한다.
            continue;
        }
        if (kind == "session") continue;
        if (kind != "record") continue;   // suppressed 줄은 레코드가 아니다
        if (sessions.empty()) continue;   // open 줄 앞의 레코드는 버린다

        try {
            JournalRecord rec;
            rec.sequence = j.value("seq", std::uint64_t{0});
            rec.timestampMs = j.value("t", std::uint64_t{0});
            rec.severity = severityFromJournalName(j.value("sev", std::string()));
            rec.siteTag = j.value("tag", std::string());
            rec.message = j.value("msg", std::string());
            sessions.back().records.push_back(std::move(rec));
        } catch (...) {
            // 타입이 어긋난 줄도 그 줄만 버린다.
        }
    }
    return sessions;
}

}  // namespace maro
