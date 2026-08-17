#include <gtest/gtest.h>

#include <vector>

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
