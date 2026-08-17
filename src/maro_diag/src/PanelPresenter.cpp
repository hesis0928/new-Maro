#include "maro_diag/PanelPresenter.h"

#include <algorithm>
#include <unordered_map>

namespace maro {

namespace {

const char* severityName(DiagSeverity s) {
    switch (s) {
        case DiagSeverity::Info: return "info";
        case DiagSeverity::Warn: return "warn";
        case DiagSeverity::DevInfo: return "devInfo";
        case DiagSeverity::Error: return "error";
    }
    return "unknown";
}

bool passesFilter(DiagSeverity s, PanelSeverityFilter filter) {
    switch (filter) {
        case PanelSeverityFilter::All:
            return true;
        case PanelSeverityFilter::WarnAndAbove:
            return s == DiagSeverity::Warn || s == DiagSeverity::Error;
        case PanelSeverityFilter::ErrorsOnly:
            return s == DiagSeverity::Error;
    }
    return true;
}

std::string firstLine(const std::string& message) {
    const std::size_t cut = message.find('\n');
    return cut == std::string::npos ? message : message.substr(0, cut);
}

// 접기 키. errorHash가 있으면 그것이 사이트를 가리킨다. Error가 아닌
// 레코드는 해시가 없으므로 심각도와 메시지 첫 줄로 키를 만든다 -- 같은
// 문장이 반복되는 경고가 실제 접기 대상이기 때문이다.
std::string collapseKey(const DiagRecord& rec) {
    if (!rec.errorHash.empty()) return "h:" + rec.errorHash;
    return std::string("m:") + severityName(rec.severity) + ":" + firstLine(rec.message);
}

}  // namespace

std::vector<PanelRow> buildPanelRows(const std::vector<DiagRecord>& stream,
                                      PanelSeverityFilter filter,
                                      std::size_t maxRows,
                                      std::size_t& hiddenByFilter,
                                      std::size_t& hiddenByCap) {
    hiddenByFilter = 0;
    hiddenByCap = 0;

    std::vector<PanelRow> rows;
    std::unordered_map<std::string, std::size_t> indexByKey;

    for (const DiagRecord& rec : stream) {
        if (!passesFilter(rec.severity, filter)) {
            ++hiddenByFilter;
            continue;
        }

        const std::string key = collapseKey(rec);
        const auto found = indexByKey.find(key);
        if (found == indexByKey.end()) {
            PanelRow row;
            row.errorHash = rec.errorHash;
            row.severity = severityName(rec.severity);
            row.summary = firstLine(rec.message);
            row.sequence = rec.sequence;
            row.firstSequence = rec.sequence;
            row.firstTimestampMs = rec.timestampMs;
            row.lastTimestampMs = rec.timestampMs;
            row.occurrences = 1;
            row.knownBefore = rec.servedFromBook;
            indexByKey.emplace(key, rows.size());
            rows.push_back(row);
            continue;
        }

        PanelRow& row = rows[found->second];
        ++row.occurrences;
        row.knownBefore = row.knownBefore || rec.servedFromBook;
        // 최초·최근은 **순번**으로 고른다. 타임스탬프끼리 min/max를 하면
        // 벽시계가 뒤로 간 순간 나중 발생의 시각이 "최초"로 뽑힌다 --
        // 순서를 정하는 어떤 판단도 시각을 읽지 않는다는 규칙 그대로다.
        if (rec.sequence > row.sequence) {
            row.sequence = rec.sequence;
            row.lastTimestampMs = rec.timestampMs;
            row.summary = firstLine(rec.message);
            row.severity = severityName(rec.severity);
        }
        if (rec.sequence < row.firstSequence) {
            row.firstSequence = rec.sequence;
            row.firstTimestampMs = rec.timestampMs;
        }
    }

    // 최신 순번이 위로.
    std::sort(rows.begin(), rows.end(),
              [](const PanelRow& a, const PanelRow& b) { return a.sequence > b.sequence; });

    if (rows.size() > maxRows) {
        hiddenByCap = rows.size() - maxRows;
        rows.resize(maxRows);
    }
    return rows;
}

}  // namespace maro
