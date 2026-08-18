#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

#include "maro_diag/DiagRecord.h"

namespace maro {

// 저널 한 줄의 종류. 세션 id는 두지 않는다 -- 세션의 경계는 open 줄 자체이고
// 세션은 close 줄이나 다음 open 줄에서 끝난다. 그래서 고유 id를 만들 필요도,
// 그것이 충돌할 걱정도 없다.
//
// 리뷰 Finding C1: 위 문단은 "쓰는 이가 하나"일 때만 참이다. 두 Maya 프로세스가
// (아티스트가 창을 두 개 띄우거나, Maya와 mayapy 배치가 동시에 이 플러그인을
// 물면) 파일 하나를 공유해 append하면, 한쪽의 open 줄이 다른 쪽이 아직
// 안 끝난 세션 한가운데 끼어든다 -- open 줄이 세션 경계라는 이 파일의 위치
// 기반 규칙이 그 순간 깨진다: 먼저 연 세션이 나중 세션의 close에 밀려 끊긴
// 것처럼 보이고(실제로는 멀쩡히 자기 close를 썼는데도), 그 사이에 낀 레코드도
// 엉뚱한 세션의 꼬리로 집계된다(JournalReader.cpp 참고). 세션 id를 새로
// 두는 대신, 프로세스마다 자기 저널 파일을 따로 쓰는 쪽을 골랐다
// (JournalWriter::pathForProcess) -- 그러면 파일 하나 안에서는 "쓰는 이가
// 하나"라는 이 문단의 전제가 다시 정확히 성립하고, 회전이 파일을 통째로
// 트렁케이트하는 동안 다른 프로세스가 같은 파일에 쓰는 경합도 함께 없어진다
// (파일을 안 나눴다면 세션 id를 둬도 그 경합은 남았을 것이다). 대가는 저널
// 파일이 여러 개로 늘어난다는 것 -- 그래서 전체 보관 상한도 파일 하나가
// 아니라 전체 파일 집합을 대상으로 다시 정의해야 한다(JournalWriter::rotateAll).
enum class JournalLineKind {
    SessionOpen,
    SessionClose,
    Record,
    Suppressed,  // 태그별 억제로 생략된 개수를 알리는 줄
    Unknown,     // 파싱 실패. 버리되 그 줄 때문에 나머지를 포기하지 않는다
};

// 리뷰 Finding (세 개의 경쟁하는 정의): 저널 한 줄이 어떤 종류인지 판정하는
// 유일한 정의. 예전에는 이 판정을 두 곳이 각자 따로 했다 -- JournalWriter::
// rotate()/countSessionOpens()(회전이 세션 경계를 찾을 때)는 리터럴 부분
// 문자열 "\"event\":\"open\""을 줄에서 찾았고, JournalReader::parseJournal()은
// 실제로 JSON을 파싱해 kind/event 필드를 봤다. 이 둘이 지금까지 일치했던
// 것은 dump()를 인자 없이 호출하면(JournalWriter.cpp) nlohmann의 기본 객체
// 타입(std::map)이 키를 항상 같은 순서로, 공백 없이 내놓기 때문일 뿐이다 --
// 그 우연이 깨지면(공백이 하나라도 섞이는 pretty-print, 혹은 필드 이름 자체가
// 바뀌는 변경) 회전 쪽은 세션 시작을 하나도 못 찾아 조용히 일찍 반환하고,
// 저널은 회전이 막으려는 바로 그 무한 성장에 빠진다. 이 함수 하나를 양쪽이
// 공유하면 그런 우연에 기대지 않는다 -- 구현은 Journal.cpp에 있다(nlohmann
// 의존은 .cpp 전용이며 이 헤더는 여전히 nlohmann을 모른다).
//
// 세션 id가 없는 이유는 여전히 위 문단(회전과 무관)과 같다: 세션의 경계는
// open 줄 자체다.
JournalLineKind classifyJournalLine(const std::string& rawLine);

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

// 프로세스별 저널 파일 이름의 공통 어간. 실제 파일 이름은
// "<stem>.<pid>.jsonl"이다(JournalWriter::pathForProcess). 리더가 한 디렉터리
// 안의 저널 파일들을 모으려면(JournalWriter::listJournalFiles) 이 접두사로
// 골라내야 하므로, 쓰기와 읽기 양쪽이 이 상수 하나를 공유한다.
constexpr const char* kJournalFileStem = "maro_journal";

const char* severityToJournalName(DiagSeverity severity);
DiagSeverity severityFromJournalName(const std::string& name);

}  // namespace maro
