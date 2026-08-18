#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

#include "maro_diag/DiagRecord.h"

namespace maro {

// 저널 한 줄의 종류. 세션 id는 두지 않는다 -- 세션의 경계는 open 줄 자체이고
// 세션은 close 줄이나 다음 open 줄에서 끝난다. 그래서 고유 id를 만들 필요도,
// 그것이 충돌할 걱정도 없다.
enum class JournalLineKind {
    SessionOpen,
    SessionClose,
    Record,
    Suppressed,  // 태그별 억제로 생략된 개수를 알리는 줄
    Unknown,     // 파싱 실패. 버리되 그 줄 때문에 나머지를 포기하지 않는다
};

// 저널이 보관하는 세션 수. 무한히 자라면 안 되고(Layer A가 인메모리
// 스트림에서 그 함정에 빠졌다), 동시에 크래시 인접 신호가 이 위에서 도므로
// 분모가 될 세션이 몇 개는 남아 있어야 한다. 10이면 최근 작업 맥락 안에
// 머물면서 문턱(비정상 종료 2회)을 넘길 표본이 나온다.
constexpr std::size_t kJournalSessionsKept = 10;

// 태그별 억제 예산. 한 태그가 이 창 안에 이만큼 쓰고 나면 창이 닫힐 때까지
// 더 쓰지 않는다. 서로 다른 태그는 서로의 예산을 잡아먹지 않는다 -- 병렬
// 평가에서 여러 노드의 경고가 번갈아 들어오므로 "연속된 같은 태그"를
// 기준으로 삼으면 억제가 한 번도 안 걸린다.
constexpr std::size_t kJournalMaxLinesPerTagPerWindow = 5;
constexpr std::uint64_t kJournalSuppressionWindowMs = 1000;

// 억제 예산 맵(JournalWriter::budgets_)의 키 상한. 태그가 있는 레코드는
// 호출 지점 수만큼만 키가 생기므로 자연히 유계이지만, 태그 없는 레코드(에러가
// 아닌 info/warn/devInfo)는 심각도 + 메시지 첫 줄을 키로 삼는다 -- 그 메시지가
// 파일 경로나 노드 이름 같은 동적 내용을 담는 경우가 흔하므로, 오래 사는
// writer는 이론상 키를 무한히 쌓을 수 있다. 맵이 이 상한에 닿으면 창이 이미
// 닫힌 항목부터 쓸어낸다(JournalWriter::sweepStaleBudgets) -- MaroDiag.h가
// 기록 벡터에 대해 아직 안 고친 채로 남겨 둔 바로 그 무한 성장 함정을 여기서는
// 만들지 않기 위해서다.
constexpr std::size_t kJournalMaxBudgetKeys = 256;

// 크래시 인접 신호가 보는 "마지막 구간"의 크기. 줄 수로 정의하는 이유는
// 시간으로 정의하면 아이들 상태로 오래 떠 있다가 죽은 세션에서 창이 텅
// 비기 때문이다 -- 진단이 뜸했던 세션일수록 창이 비고, 정작 그 드문 진단이
// 후보에서 빠진다.
constexpr std::size_t kJournalTailRecordsForSignal = 20;

const char* severityToJournalName(DiagSeverity severity);
DiagSeverity severityFromJournalName(const std::string& name);

}  // namespace maro
