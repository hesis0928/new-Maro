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

}  // namespace maro
