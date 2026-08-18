#include "maro_diag/PanelPresenter.h"

#include <algorithm>
#include <string>
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

// 빈 문자열의 뜻을 레코드가 아는 사실로 가른다. nameUnavailable은 이름
// 조회를 시도했으나 못 했다는 표시이므로, 그 경우의 빈 이름은 "관여 없음"이
// 아니라 "못 채움"이다 (설계 스펙 §4.4).
ContextField makeField(const std::string& value, bool unavailable) {
    ContextField field;
    if (!value.empty()) {
        field.value = value;
        field.presence = ContextPresence::Present;
        return field;
    }
    field.presence = unavailable ? ContextPresence::NotCaptured
                                  : ContextPresence::NotApplicable;
    return field;
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

PanelDetail buildPanelDetail(const DiagRecord& record,
                              const BookEntry* bookEntry,
                              bool targetNodeExists,
                              const CrashAdjacency& crashAdjacency) {
    (void)targetNodeExists;  // B-1b가 적용 가능 여부를 판단할 때 쓴다.

    PanelDetail detail;
    // nodeType과 axisOrTarget은 MaroDeleteWatcher.cpp의 captureFromNode에서
    // 살아있는 Maya 조회로 채워지므로 둘 다 실패할 수 있다 -- 각자의 플래그를
    // 그대로 전달한다. attributeName과 activeCommand는 어떤 경로에서도
    // 실패할 수 있는 조회를 거치지 않는다: compute()/selfContext 계열은
    // nodeType을 컴파일타임 리터럴로 채우고, attributeName·activeCommand는
    // 애초에 실패 가능한 룩업의 결과가 아니다 -- 그래서 이 둘은 항상 false다.
    detail.nodeType = makeField(record.context.nodeType, record.context.typeUnavailable);
    detail.attributeName = makeField(record.context.attributeName, false);
    detail.activeCommand = makeField(record.context.activeCommand, false);
    detail.axisOrTarget = makeField(record.context.axisOrTarget,
                                     record.context.nameUnavailable);

    detail.message = record.message;

    // book에서 지금 읽어 온 것이 있으면 그쪽이 최신이다.
    if (bookEntry != nullptr && !bookEntry->analysis.empty()) {
        detail.priorAnalysis = bookEntry->analysis;
    } else {
        detail.priorAnalysis = record.priorAnalysis;
    }
    if (bookEntry != nullptr && !bookEntry->remedy.empty()) {
        detail.remedyText = bookEntry->remedy;
    } else {
        detail.remedyText = record.remedy;
    }

    // B-1a에는 구조화된 동작이 없다. 자리만 지키고 내용은 B-1b가 채운다.
    detail.applyAvailable = false;
    detail.applyUnavailableReason = "NoActionRecorded";

    // 잡음 문턱: 비정상 종료가 2회 미만이거나 이 태그가 1회만 걸렸으면
    // 아무것도 말하지 않는다.
    detail.crashAdjacencyNote.clear();
    if (!record.errorHash.empty() && crashAdjacency.abnormalSessionCount >= 2) {
        const auto found = crashAdjacency.appearancesByTag.find(record.errorHash);
        if (found != crashAdjacency.appearancesByTag.end() && found->second >= 2) {
            detail.crashAdjacencyNote =
                "지난 비정상 종료 " + std::to_string(crashAdjacency.abnormalSessionCount) +
                "회 중 " + std::to_string(found->second) +
                "회에서 이 진단이 마지막 순간에 있었습니다.";
        }
    }
    return detail;
}

}  // namespace maro
