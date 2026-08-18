#include <gtest/gtest.h>

#include <vector>

#include "maro_diag/BookStore.h"
#include "maro_diag/DiagRecord.h"
#include "maro_diag/PanelView.h"
#include "maro_diag/PanelPresenter.h"

namespace {

maro::DiagRecord makeRecord(std::uint64_t seq, std::uint64_t ms,
                             maro::DiagSeverity sev, const std::string& siteTag,
                             const std::string& message) {
    maro::DiagRecord rec;
    rec.sequence = seq;
    rec.timestampMs = ms;
    rec.severity = sev;
    rec.errorHash = siteTag;  // 접기 기준은 해시다 (같은 사이트 = 같은 해시)
    rec.message = message;
    return rec;
}

// errorHash가 비어 있는 레코드. DiagRecord.h의 계약대로 book 해시는 Error
// 심각도에서만 채워지므로, info/warn 레코드는 운영에서 늘 이 모양으로
// collapseKey의 "m:" 대체 경로(심각도 + 메시지 첫 줄)를 탄다.
maro::DiagRecord makeHashlessRecord(std::uint64_t seq, std::uint64_t ms,
                                     maro::DiagSeverity sev, const std::string& message) {
    maro::DiagRecord rec;
    rec.sequence = seq;
    rec.timestampMs = ms;
    rec.severity = sev;
    rec.message = message;
    // rec.errorHash left empty on purpose.
    return rec;
}

}  // namespace

// 병렬 평가에서는 서로 다른 노드의 경고가 번갈아 들어온다. "연속된 같은
// 태그"로 접으면 어느 것도 연속이 아니라 접기가 한 번도 안 걸린다.
TEST(PanelPresenter, CollapsesInterleavedRepeatsByTag) {
    std::vector<maro::DiagRecord> stream;
    for (std::uint64_t i = 0; i < 4; ++i) {
        stream.push_back(makeRecord(i * 2 + 1, 1000 + i * 2,
                                    maro::DiagSeverity::Error, "hashA", "A failed"));
        stream.push_back(makeRecord(i * 2 + 2, 1001 + i * 2,
                                    maro::DiagSeverity::Error, "hashB", "B failed"));
    }

    std::size_t hiddenByFilter = 0;
    std::size_t hiddenByCap = 0;
    const std::vector<maro::PanelRow> rows = maro::buildPanelRows(
        stream, maro::PanelSeverityFilter::All, 500, hiddenByFilter, hiddenByCap);

    ASSERT_EQ(rows.size(), 2u) << "interleaved repeats of two tags must collapse to two rows";
    EXPECT_EQ(rows[0].occurrences, 4u);
    EXPECT_EQ(rows[1].occurrences, 4u);
}

// 접힌 행의 자리는 그 태그의 가장 최근 발생을 따른다.
TEST(PanelPresenter, RowOrderFollowsMostRecentOccurrence) {
    std::vector<maro::DiagRecord> stream;
    stream.push_back(makeRecord(1, 1000, maro::DiagSeverity::Error, "old", "old one"));
    stream.push_back(makeRecord(2, 1001, maro::DiagSeverity::Error, "recent", "recent one"));
    stream.push_back(makeRecord(3, 1002, maro::DiagSeverity::Error, "old", "old again"));

    std::size_t hiddenByFilter = 0;
    std::size_t hiddenByCap = 0;
    const std::vector<maro::PanelRow> rows = maro::buildPanelRows(
        stream, maro::PanelSeverityFilter::All, 500, hiddenByFilter, hiddenByCap);

    ASSERT_EQ(rows.size(), 2u);
    EXPECT_EQ(rows[0].errorHash, "old") << "newest first: 'old' recurred at sequence 3";
    EXPECT_EQ(rows[0].sequence, 3u);
    EXPECT_EQ(rows[0].firstTimestampMs, 1000u);
    EXPECT_EQ(rows[0].lastTimestampMs, 1002u);
    EXPECT_EQ(rows[0].summary, "old again")
        << "summary must track the most recent occurrence, not freeze at the first";
}

// severity도 summary와 마찬가지로 최신 발생을 따라야 한다 (PanelView.h).
// 같은 해시를 공유하는 두 발생의 심각도를 일부러 다르게 둬서 -- collapseKey
// 계산과 무관하게 -- row 갱신 로직만 분리해 확인한다: hash 기반 키는
// 심각도를 키에 포함하지 않으므로 두 발생이 한 행으로 접히고, 그 행의
// severity 필드는 오직 "최근 발생이 무엇을 보고했는가"로만 결정돼야 한다.
TEST(PanelPresenter, SeverityTracksMostRecentOccurrence) {
    std::vector<maro::DiagRecord> stream;
    stream.push_back(makeRecord(1, 1000, maro::DiagSeverity::Warn, "site", "warned first"));
    stream.push_back(makeRecord(2, 1001, maro::DiagSeverity::Error, "site", "escalated"));

    std::size_t hiddenByFilter = 0;
    std::size_t hiddenByCap = 0;
    const std::vector<maro::PanelRow> rows = maro::buildPanelRows(
        stream, maro::PanelSeverityFilter::All, 500, hiddenByFilter, hiddenByCap);

    ASSERT_EQ(rows.size(), 1u);
    EXPECT_EQ(rows[0].severity, "error")
        << "the row must report the latest occurrence's severity, not the first one's";
    EXPECT_EQ(rows[0].summary, "escalated");
}

// 벽시계가 뒤로 가도 순서는 순번을 따른다.
TEST(PanelPresenter, OrderIgnoresBackwardClock) {
    std::vector<maro::DiagRecord> stream;
    stream.push_back(makeRecord(1, 9000, maro::DiagSeverity::Error, "first", "first"));
    stream.push_back(makeRecord(2, 1000, maro::DiagSeverity::Error, "second", "second"));

    std::size_t hiddenByFilter = 0;
    std::size_t hiddenByCap = 0;
    const std::vector<maro::PanelRow> rows = maro::buildPanelRows(
        stream, maro::PanelSeverityFilter::All, 500, hiddenByFilter, hiddenByCap);

    ASSERT_EQ(rows.size(), 2u);
    EXPECT_EQ(rows[0].errorHash, "second")
        << "sequence 2 is newer even though its wall clock reads earlier";
}

// 절단은 필터와 접기 뒤에 온다. 먼저 자르면 연쇄의 시작이 가장 먼저 사라진다.
TEST(PanelPresenter, FiltersAndCollapsesBeforeCapping) {
    std::vector<maro::DiagRecord> stream;
    // 진짜 원인: 가장 오래된 에러 하나.
    stream.push_back(makeRecord(1, 1000, maro::DiagSeverity::Error, "root", "root cause"));
    // 그 뒤로 쏟아진 정보성 잡음 300개.
    for (std::uint64_t i = 0; i < 300; ++i) {
        stream.push_back(makeRecord(2 + i, 1001 + i, maro::DiagSeverity::Info,
                                     "noise", "just noise"));
    }

    std::size_t hiddenByFilter = 0;
    std::size_t hiddenByCap = 0;
    const std::vector<maro::PanelRow> rows = maro::buildPanelRows(
        stream, maro::PanelSeverityFilter::ErrorsOnly, 2, hiddenByFilter, hiddenByCap);

    ASSERT_EQ(rows.size(), 1u);
    EXPECT_EQ(rows[0].errorHash, "root") << "the cascade's origin must survive truncation";
    EXPECT_EQ(hiddenByFilter, 300u);
    EXPECT_EQ(hiddenByCap, 0u) << "collapsing brought it under the cap, so nothing was cut";
}

// 필터로 빠진 것과 상한으로 잘린 것은 다른 사건이다.
TEST(PanelPresenter, ReportsHiddenCountsSeparately) {
    std::vector<maro::DiagRecord> stream;
    for (std::uint64_t i = 0; i < 5; ++i) {
        stream.push_back(makeRecord(i + 1, 1000 + i, maro::DiagSeverity::Error,
                                     "tag" + std::to_string(i), "distinct"));
    }
    stream.push_back(makeRecord(6, 2000, maro::DiagSeverity::Info, "info", "noise"));

    std::size_t hiddenByFilter = 0;
    std::size_t hiddenByCap = 0;
    const std::vector<maro::PanelRow> rows = maro::buildPanelRows(
        stream, maro::PanelSeverityFilter::ErrorsOnly, 3, hiddenByFilter, hiddenByCap);

    ASSERT_EQ(rows.size(), 3u);
    EXPECT_EQ(hiddenByFilter, 1u);
    EXPECT_EQ(hiddenByCap, 2u);
}

// --- 해시 없는 접기 경로 (collapseKey의 "m:" 대체 분기) ---
// 지금까지 모든 픽스처가 makeRecord로 errorHash를 채웠기 때문에 이 분기는
// 한 번도 실행되지 않았다. 그런데 DiagRecord.h가 명시하듯 book 해시는
// Error 심각도에서만 채워지므로, 운영에서 가장 많이 지나가는 info/warn
// 레코드는 전부 이 분기를 탄다.

// 해시가 없고 메시지가 같은 두 info는 한 행으로 접혀야 한다.
TEST(PanelPresenter, HashlessSameMessageCollapsesToOneRow) {
    std::vector<maro::DiagRecord> stream;
    stream.push_back(makeHashlessRecord(1, 1000, maro::DiagSeverity::Info, "steady state"));
    stream.push_back(makeHashlessRecord(2, 1001, maro::DiagSeverity::Info, "steady state"));

    std::size_t hiddenByFilter = 0;
    std::size_t hiddenByCap = 0;
    const std::vector<maro::PanelRow> rows = maro::buildPanelRows(
        stream, maro::PanelSeverityFilter::All, 500, hiddenByFilter, hiddenByCap);

    ASSERT_EQ(rows.size(), 1u)
        << "two hashless info records with the same message must collapse into one row";
    EXPECT_EQ(rows[0].occurrences, 2u);
}

// 해시가 없고 메시지가 다르면 두 행으로 남아야 한다.
TEST(PanelPresenter, HashlessDifferentMessageStaysTwoRows) {
    std::vector<maro::DiagRecord> stream;
    stream.push_back(makeHashlessRecord(1, 1000, maro::DiagSeverity::Info, "steady state"));
    stream.push_back(makeHashlessRecord(2, 1001, maro::DiagSeverity::Info, "different state"));

    std::size_t hiddenByFilter = 0;
    std::size_t hiddenByCap = 0;
    const std::vector<maro::PanelRow> rows = maro::buildPanelRows(
        stream, maro::PanelSeverityFilter::All, 500, hiddenByFilter, hiddenByCap);

    EXPECT_EQ(rows.size(), 2u)
        << "hashless records with different messages must not collapse together";
}

// 해시가 없고 메시지는 같아도 심각도가 다르면 두 행으로 남아야 한다 --
// 심각도는 키의 일부이며, 여기서 접히면 경고가 정보로 오보된다.
TEST(PanelPresenter, HashlessSameMessageDifferentSeverityStaysTwoRows) {
    std::vector<maro::DiagRecord> stream;
    stream.push_back(makeHashlessRecord(1, 1000, maro::DiagSeverity::Info, "same text"));
    stream.push_back(makeHashlessRecord(2, 1001, maro::DiagSeverity::Warn, "same text"));

    std::size_t hiddenByFilter = 0;
    std::size_t hiddenByCap = 0;
    const std::vector<maro::PanelRow> rows = maro::buildPanelRows(
        stream, maro::PanelSeverityFilter::All, 500, hiddenByFilter, hiddenByCap);

    EXPECT_EQ(rows.size(), 2u)
        << "severity is part of the hashless key -- merging warn into info would misreport severity";
}

// 위 두 knownBefore 테스트는 픽스처를 순번 오름차순으로만 먹인다 -- 처리
// 순서가 항상 "가장 최근 것이 마지막에 온다"와 일치하므로, buildPanelRows의
// OR가 "이 레코드가 더 최근인가" 분기(순번을 기준으로 sequence/summary/
// severity를 갱신하는 그 if) 안에 잘못 들어가 있어도(row.knownBefore =
// row.knownBefore || rec.servedFromBook;를 그 if 블록 안으로 옮기는 변형)
// 그 if는 처리 순서상 마지막 레코드에서 항상 참이 되므로 위 두 테스트는
// 여전히 통과한다 -- 결함을 못 잡는다. 이 테스트는 벡터 순서를 일부러
// 순번 오름차순이 아니게 먹여(순번이 더 큰, book에서 오지 않은 레코드를
// 먼저, servedFromBook인 더 작은 순번의 레코드를 나중에) 그 if 조건이
// false인 채로 servedFromBook 레코드가 처리되게 만든다: OR가 제자리(if
// 밖)에 있으면 무조건 반영되지만, if 안에 있으면 조건이 false라 건너뛰어
// knownBefore가 조용히 false로 남는다.
TEST(PanelPresenter, KnownBeforeSurvivesWhenServedOccurrenceArrivesAfterANewerOne) {
    std::vector<maro::DiagRecord> stream;
    stream.push_back(makeRecord(2, 1001, maro::DiagSeverity::Error, "site", "newer, not served"));
    maro::DiagRecord served = makeRecord(1, 1000, maro::DiagSeverity::Error, "site", "older, served");
    served.servedFromBook = true;
    stream.push_back(served);

    std::size_t hiddenByFilter = 0;
    std::size_t hiddenByCap = 0;
    const std::vector<maro::PanelRow> rows = maro::buildPanelRows(
        stream, maro::PanelSeverityFilter::All, 500, hiddenByFilter, hiddenByCap);

    ASSERT_EQ(rows.size(), 1u);
    EXPECT_TRUE(rows[0].knownBefore)
        << "a servedFromBook occurrence with a lower sequence must still mark the row known, "
           "even though it is processed after a higher-sequence occurrence that already took "
           "the 'is this record newer' branch";
}

// --- knownBefore: "이 자리의 발생 중 하나라도 book에서 즉답됐는가" ---

// 여러 발생 중 하나만 servedFromBook이어도 행 전체가 knownBefore여야 한다.
TEST(PanelPresenter, KnownBeforeTrueWhenAnyOccurrenceServedFromBook) {
    std::vector<maro::DiagRecord> stream;
    maro::DiagRecord first = makeRecord(1, 1000, maro::DiagSeverity::Error, "site", "first");
    maro::DiagRecord second = makeRecord(2, 1001, maro::DiagSeverity::Error, "site", "second");
    second.servedFromBook = true;
    maro::DiagRecord third = makeRecord(3, 1002, maro::DiagSeverity::Error, "site", "third");
    stream.push_back(first);
    stream.push_back(second);
    stream.push_back(third);

    std::size_t hiddenByFilter = 0;
    std::size_t hiddenByCap = 0;
    const std::vector<maro::PanelRow> rows = maro::buildPanelRows(
        stream, maro::PanelSeverityFilter::All, 500, hiddenByFilter, hiddenByCap);

    ASSERT_EQ(rows.size(), 1u);
    EXPECT_TRUE(rows[0].knownBefore)
        << "one occurrence served from the book must mark the whole row known";
}

// 어떤 발생도 book에서 즉답되지 않았다면 knownBefore는 false로 남아야 한다.
TEST(PanelPresenter, KnownBeforeFalseWhenNoOccurrenceServedFromBook) {
    std::vector<maro::DiagRecord> stream;
    stream.push_back(makeRecord(1, 1000, maro::DiagSeverity::Error, "site", "first"));
    stream.push_back(makeRecord(2, 1001, maro::DiagSeverity::Error, "site", "second"));

    std::size_t hiddenByFilter = 0;
    std::size_t hiddenByCap = 0;
    const std::vector<maro::PanelRow> rows = maro::buildPanelRows(
        stream, maro::PanelSeverityFilter::All, 500, hiddenByFilter, hiddenByCap);

    ASSERT_EQ(rows.size(), 1u);
    EXPECT_FALSE(rows[0].knownBefore);
}

// --- 경계: maxRows == 0, 빈 스트림 ---

// maxRows가 0이면 접힌 행 전부가 상한에 가려져야 한다. 필터로는 아무것도
// 빠지지 않았으므로 hiddenByFilter는 0, hiddenByCap이 전체를 담아야 한다.
TEST(PanelPresenter, MaxRowsZeroHidesEverythingUnderCap) {
    std::vector<maro::DiagRecord> stream;
    stream.push_back(makeRecord(1, 1000, maro::DiagSeverity::Error, "a", "a failed"));
    stream.push_back(makeRecord(2, 1001, maro::DiagSeverity::Error, "b", "b failed"));
    stream.push_back(makeRecord(3, 1002, maro::DiagSeverity::Error, "c", "c failed"));

    std::size_t hiddenByFilter = 0;
    std::size_t hiddenByCap = 0;
    const std::vector<maro::PanelRow> rows = maro::buildPanelRows(
        stream, maro::PanelSeverityFilter::All, 0, hiddenByFilter, hiddenByCap);

    EXPECT_TRUE(rows.empty());
    EXPECT_EQ(hiddenByFilter, 0u);
    EXPECT_EQ(hiddenByCap, 3u)
        << "everything is hidden by the cap, nothing by the filter";
}

// 빈 스트림은 빈 결과와 0/0 숨김 카운트를 내야 한다.
TEST(PanelPresenter, EmptyStreamProducesNoRowsAndNoHiddenCounts) {
    std::vector<maro::DiagRecord> stream;

    std::size_t hiddenByFilter = 0;
    std::size_t hiddenByCap = 0;
    const std::vector<maro::PanelRow> rows = maro::buildPanelRows(
        stream, maro::PanelSeverityFilter::All, 500, hiddenByFilter, hiddenByCap);

    EXPECT_TRUE(rows.empty());
    EXPECT_EQ(hiddenByFilter, 0u);
    EXPECT_EQ(hiddenByCap, 0u);
}

// 관여가 없어서 빈 것과, 관여는 했는데 못 채운 것은 다른 사실이다.
TEST(PanelPresenter, DistinguishesNotCapturedFromNotApplicable) {
    maro::DiagRecord rec = makeRecord(1, 1000, maro::DiagSeverity::Error,
                                       "hash", "compute failed");
    rec.context.nodeType = "maroAxis";
    rec.context.axisOrTarget = "";       // 워커 스레드라 이름을 못 물었다
    rec.context.nameUnavailable = true;
    rec.context.attributeName = "";      // 이 실패에는 관여한 어트리뷰트가 없다

    const maro::PanelDetail detail = maro::buildPanelDetail(rec, nullptr, false, maro::CrashAdjacency{});

    EXPECT_EQ(detail.nodeType.presence, maro::ContextPresence::Present);
    EXPECT_EQ(detail.nodeType.value, "maroAxis");
    EXPECT_EQ(detail.axisOrTarget.presence, maro::ContextPresence::NotCaptured)
        << "the worker thread could not ask Maya for the name -- that is not 'nothing involved'";
    EXPECT_EQ(detail.attributeName.presence, maro::ContextPresence::NotApplicable);
}

// MaroDeleteWatcher.cpp의 captureFromNode는 nodeType과 axisOrTarget을 같은
// try 블록 안에서, 같은 살아있는 MFnDependencyNode로 얻는다. 그 생성자가
// 던지면(노드가 삭제 도중이라 손상됐을 때) 두 필드가 함께 비고 두 플래그가
// 함께 선다 -- 이 경우를 "관여 없음"으로 그리면 손상된 노드를 다루다 실패한
// 사실 자체가 지워진다.
TEST(PanelPresenter, BothNodeTypeAndNameNotCapturedWhenNodeLookupFailedEntirely) {
    maro::DiagRecord rec = makeRecord(1, 1000, maro::DiagSeverity::Error,
                                       "hash", "delete callback failed");
    rec.context.nodeType = "";
    rec.context.axisOrTarget = "";
    rec.context.typeUnavailable = true;
    rec.context.nameUnavailable = true;

    const maro::PanelDetail detail = maro::buildPanelDetail(rec, nullptr, false, maro::CrashAdjacency{});

    EXPECT_EQ(detail.nodeType.presence, maro::ContextPresence::NotCaptured)
        << "the MFnDependencyNode constructor itself threw -- the type was wanted but not obtained";
    EXPECT_EQ(detail.axisOrTarget.presence, maro::ContextPresence::NotCaptured)
        << "the same failure took the name with it";
}

// book 항목이 있으면 해법 설명이 나온다. 적용 가능 여부는 B-1b까지 항상 거짓이다.
TEST(PanelPresenter, CarriesRemedyTextButOffersNoActionYet) {
    maro::DiagRecord rec = makeRecord(1, 1000, maro::DiagSeverity::Error,
                                       "hash", "bind rejected");
    maro::BookEntry entry;
    entry.analysis = "이 축은 이미 다른 오브젝트에 묶여 있다";
    entry.remedy = "먼저 기존 바인딩을 끊으세요";

    const maro::PanelDetail detail = maro::buildPanelDetail(rec, &entry, true, maro::CrashAdjacency{});

    EXPECT_EQ(detail.remedyText, "먼저 기존 바인딩을 끊으세요");
    EXPECT_FALSE(detail.applyAvailable);
    EXPECT_EQ(detail.applyUnavailableReason, "NoActionRecorded");
}

// 레코드의 priorAnalysis와 book의 현재 analysis는 다를 수 있다 -- 레코드가
// 남은 뒤에 등록된 것을 반영하는 것이 상세 조회의 목적이다.
TEST(PanelPresenter, PrefersTheCurrentBookAnalysisOverTheRecordedOne) {
    maro::DiagRecord rec = makeRecord(1, 1000, maro::DiagSeverity::Error,
                                       "hash", "failed");
    rec.priorAnalysis = "레코드가 남을 때의 분석";
    maro::BookEntry entry;
    entry.analysis = "그 뒤에 갱신된 분석";

    const maro::PanelDetail detail = maro::buildPanelDetail(rec, &entry, true, maro::CrashAdjacency{});

    EXPECT_EQ(detail.priorAnalysis, "그 뒤에 갱신된 분석");
}

// book 항목이 존재하지만 analysis가 빈 문자열이면(예: remedy만 등록되고
// 분석은 아직 안 채워진 경우) 레코드 자신의 priorAnalysis로 돌아가야 한다.
// "!empty()" 가드를 빼면 이 경우 레코드가 들고 있던 분석까지 지워진다.
TEST(PanelPresenter, FallsBackToRecordAnalysisWhenBookEntryAnalysisIsEmpty) {
    maro::DiagRecord rec = makeRecord(1, 1000, maro::DiagSeverity::Error,
                                       "hash", "failed");
    rec.priorAnalysis = "레코드가 남을 때의 분석";
    maro::BookEntry entry;  // entry.analysis left empty on purpose
    entry.remedy = "해법은 있다";

    const maro::PanelDetail detail = maro::buildPanelDetail(rec, &entry, true, maro::CrashAdjacency{});

    EXPECT_EQ(detail.priorAnalysis, "레코드가 남을 때의 분석")
        << "a present-but-empty book analysis must not blank out the record's own analysis";
}

// 같은 이야기를 remedy에 대해서도: book 항목은 있는데 remedy가 비어 있으면
// 레코드의 remedy로 돌아가야 한다.
TEST(PanelPresenter, FallsBackToRecordRemedyWhenBookEntryRemedyIsEmpty) {
    maro::DiagRecord rec = makeRecord(1, 1000, maro::DiagSeverity::Error,
                                       "hash", "failed");
    rec.remedy = "레코드에 실려 온 해법";
    maro::BookEntry entry;  // entry.remedy left empty on purpose
    entry.analysis = "분석은 있다";

    const maro::PanelDetail detail = maro::buildPanelDetail(rec, &entry, true, maro::CrashAdjacency{});

    EXPECT_EQ(detail.remedyText, "레코드에 실려 온 해법")
        << "a present-but-empty book remedy must not blank out a remedy the record was carrying";
}

// book을 못 읽어도 상세는 나온다 -- 진단 경로는 지식 저장소 때문에 죽지 않는다.
TEST(PanelPresenter, WorksWithoutABookEntry) {
    maro::DiagRecord rec = makeRecord(1, 1000, maro::DiagSeverity::Error,
                                       "hash", "failed");
    rec.priorAnalysis = "레코드에 실려 온 분석";

    const maro::PanelDetail detail = maro::buildPanelDetail(rec, nullptr, true, maro::CrashAdjacency{});

    EXPECT_EQ(detail.message, "failed");
    EXPECT_EQ(detail.priorAnalysis, "레코드에 실려 온 분석");
    EXPECT_EQ(detail.remedyText, "");
}

#include "maro_diag/JournalReader.h"

// 문턱 아래에서는 아무 말도 하지 않는다. 1회를 근거로 뭔가 말하는 것은
// 정보가 아니라 소음이다.
TEST(PanelPresenter, SaysNothingBelowTheCrashAdjacencyThreshold) {
    maro::DiagRecord rec = makeRecord(1, 1000, maro::DiagSeverity::Error,
                                       "Site.A", "failed");

    maro::CrashAdjacency onlyOneAbnormal;
    onlyOneAbnormal.abnormalSessionCount = 1;
    onlyOneAbnormal.appearancesByTag["Site.A"] = 1;
    EXPECT_EQ(maro::buildPanelDetail(rec, nullptr, false, onlyOneAbnormal)
                  .crashAdjacencyNote, "")
        << "one abnormal session is not a pattern";

    maro::CrashAdjacency singleAppearance;
    singleAppearance.abnormalSessionCount = 4;
    singleAppearance.appearancesByTag["Site.A"] = 1;
    EXPECT_EQ(maro::buildPanelDetail(rec, nullptr, false, singleAppearance)
                  .crashAdjacencyNote, "")
        << "appearing once out of four is not a pattern either";
}

// 문턱을 넘으면 관측된 사실을 정확한 숫자로 말한다.
TEST(PanelPresenter, ReportsTheObservedCountsAboveTheThreshold) {
    maro::DiagRecord rec = makeRecord(1, 1000, maro::DiagSeverity::Error,
                                       "Site.A", "failed");
    maro::CrashAdjacency adjacency;
    adjacency.abnormalSessionCount = 4;
    adjacency.appearancesByTag["Site.A"] = 3;

    const std::string note =
        maro::buildPanelDetail(rec, nullptr, false, adjacency).crashAdjacencyNote;

    EXPECT_NE(note.find("4"), std::string::npos) << "the denominator must appear";
    EXPECT_NE(note.find("3"), std::string::npos) << "the numerator must appear";
}

// 다른 태그의 집계를 이 레코드에 붙이지 않는다.
TEST(PanelPresenter, DoesNotBorrowAnotherTagsCount) {
    maro::DiagRecord rec = makeRecord(1, 1000, maro::DiagSeverity::Error,
                                       "Site.Quiet", "failed");
    maro::CrashAdjacency adjacency;
    adjacency.abnormalSessionCount = 4;
    adjacency.appearancesByTag["Site.Noisy"] = 3;

    EXPECT_EQ(maro::buildPanelDetail(rec, nullptr, false, adjacency).crashAdjacencyNote, "");
}

// 해시가 없는 레코드(에러가 아닌 것)에는 신호가 붙지 않는다.
TEST(PanelPresenter, NoNoteForARecordWithoutASiteTag) {
    maro::DiagRecord rec = makeRecord(1, 1000, maro::DiagSeverity::Warn, "", "just a warning");
    maro::CrashAdjacency adjacency;
    adjacency.abnormalSessionCount = 4;
    adjacency.appearancesByTag[""] = 3;

    EXPECT_EQ(maro::buildPanelDetail(rec, nullptr, false, adjacency).crashAdjacencyNote, "");
}
