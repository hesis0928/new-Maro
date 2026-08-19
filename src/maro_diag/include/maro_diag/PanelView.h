#pragma once

#include <cstdint>
#include <string>

namespace maro {

// 프레젠터의 출력이다. Maya도 Qt도 Maya 네이티브 위젯도 전제하지 않는다 --
// 어떤 UI 기술로 그릴지는 이 타입이 모른다 (설계 스펙 §3.2). B-2가 Qt판을
// 붙일 때 판단 로직을 한 줄도 다시 쓰지 않게 하는 지점이다.

enum class PanelSeverityFilter {
    All,
    WarnAndAbove,
    ErrorsOnly,
};

// 접힌 행 하나. 같은 사이트(= 같은 errorHash)의 발생들이 한 행으로 모인다.
struct PanelRow {
    std::string errorHash;   // 접기 키. Error가 아닌 레코드는 비어 있을 수 있다
    std::string severity;    // "info" | "warn" | "devInfo" | "error"
    std::string summary;     // 한 줄 요약 (가장 최근 발생의 message 첫 줄)
    // 이 행이 대표하는 가장 최근 발생의 순번. 정렬 기준이자 상세 조회 키다.
    std::uint64_t sequence = 0;
    // 이 행의 가장 이른 발생의 순번. 최초 시각을 고를 때 쓴다 -- 시각끼리
    // 비교하면 벽시계가 뒤로 간 순간 나중 것이 "최초"로 뽑힌다.
    std::uint64_t firstSequence = 0;
    std::uint64_t firstTimestampMs = 0;  // 형식화는 표시하는 쪽이 로컬 시간대로 한다
    std::uint64_t lastTimestampMs = 0;
    std::size_t occurrences = 1;
    bool knownBefore = false;  // 이 자리의 발생 중 하나라도 book에서 즉답됐는가
};

// 컨텍스트 한 칸의 표시 상태. 빈 문자열 하나로는 두 사실을 구분할 수 없다.
enum class ContextPresence {
    Present,        // 값이 있다
    NotApplicable,  // 이 자리에 관여한 것이 애초에 없었다
    NotCaptured,    // 관여는 했으나 그 시점에 알아낼 수 없었다
};

struct ContextField {
    std::string value;
    ContextPresence presence = ContextPresence::NotApplicable;
};

// 선택된 행의 상세. 필드 개수는 지금 확정한다 -- Python이 필드 수로 잘라
// 재조립하므로 필드가 늘거나 줄면 UI가 조용히 어긋난다. applyAvailable과
// applyUnavailableReason은 B-1a가 자리만 예약해 뒀고("항상 false" /
// "NoActionRecorded"), B-1b-2(PanelPresenter.cpp의 buildPanelDetail)가
// record.remedyAction과 targetNodeExists를 보고 실제 값을 채운다.
struct PanelDetail {
    ContextField nodeType;
    ContextField attributeName;
    ContextField activeCommand;
    ContextField axisOrTarget;
    std::string message;
    std::string priorAnalysis;
    std::string remedyText;
    bool applyAvailable = false;
    std::string applyUnavailableReason;
    // 이 자리가 지난 비정상 종료 직전에 반복해서 나타났다면 그 사실을
    // 담는다. 비어 있으면 말할 것이 없다는 뜻이다.
    //
    // 인과가 아니라 상관이다. 크래시 직전에 있었다는 것이 크래시를
    // 일으켰다는 뜻은 아니므로 문구는 관측된 사실만 말한다.
    std::string crashAdjacencyNote;
};

}  // namespace maro
