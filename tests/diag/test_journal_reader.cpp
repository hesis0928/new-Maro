#include <gtest/gtest.h>

#include <string>
#include <vector>

#include "maro_diag/Journal.h"
#include "maro_diag/JournalReader.h"

TEST(JournalReader, SplitsSessionsAtOpenLines) {
    const std::string text =
        R"({"kind":"session","event":"open","t":1000})" "\n"
        R"({"kind":"record","seq":1,"t":1001,"sev":"error","tag":"A","msg":"first"})" "\n"
        R"({"kind":"session","event":"close","t":1002})" "\n"
        R"({"kind":"session","event":"open","t":2000})" "\n"
        R"({"kind":"record","seq":2,"t":2001,"sev":"warn","tag":"B","msg":"second"})" "\n"
        R"({"kind":"session","event":"close","t":2002})" "\n";

    const std::vector<maro::JournalSession> sessions = maro::parseJournal(text);

    ASSERT_EQ(sessions.size(), 2u);
    EXPECT_TRUE(sessions[0].endedCleanly);
    EXPECT_TRUE(sessions[1].endedCleanly);
    ASSERT_EQ(sessions[0].records.size(), 1u);
    EXPECT_EQ(sessions[0].records[0].siteTag, "A");
    EXPECT_EQ(sessions[0].records[0].message, "first");
    EXPECT_EQ(sessions[0].records[0].sequence, 1u);
    EXPECT_EQ(sessions[0].records[0].severity, maro::DiagSeverity::Error);
    EXPECT_EQ(sessions[0].records[0].timestampMs, 1001u);
    EXPECT_EQ(sessions[1].records[0].siteTag, "B");
    EXPECT_EQ(sessions[1].records[0].severity, maro::DiagSeverity::Warn);
    EXPECT_EQ(sessions[1].records[0].timestampMs, 2001u);
}

// 종료 줄 없이 끝난 세션이 곧 비정상 종료다. 타임아웃을 추측할 필요가 없다.
TEST(JournalReader, ASessionWithoutACloseLineEndedAbnormally) {
    const std::string text =
        R"({"kind":"session","event":"open","t":1000})" "\n"
        R"({"kind":"record","seq":1,"t":1001,"sev":"error","tag":"A","msg":"before the crash"})" "\n"
        R"({"kind":"session","event":"open","t":2000})" "\n"
        R"({"kind":"record","seq":2,"t":2001,"sev":"info","tag":"","msg":"next run"})" "\n"
        R"({"kind":"session","event":"close","t":2002})" "\n";

    const std::vector<maro::JournalSession> sessions = maro::parseJournal(text);

    ASSERT_EQ(sessions.size(), 2u);
    EXPECT_FALSE(sessions[0].endedCleanly)
        << "the first session was cut off by the next open, so it never closed";
    EXPECT_TRUE(sessions[1].endedCleanly);
}

// 파일 끝에서 끊긴 세션도 비정상이다 -- 이것이 가장 흔한 실제 크래시 모양이다.
TEST(JournalReader, ASessionCutOffAtEndOfFileEndedAbnormally) {
    const std::string text =
        R"({"kind":"session","event":"open","t":1000})" "\n"
        R"({"kind":"record","seq":1,"t":1001,"sev":"error","tag":"A","msg":"last words"})" "\n";

    const std::vector<maro::JournalSession> sessions = maro::parseJournal(text);

    ASSERT_EQ(sessions.size(), 1u);
    EXPECT_FALSE(sessions[0].endedCleanly);
    ASSERT_EQ(sessions[0].records.size(), 1u);
    EXPECT_EQ(sessions[0].records[0].message, "last words");
}

// 깨진 줄 하나가 나머지를 포기시키면 안 된다 -- 크래시가 마지막 줄을
// 반쯤 쓴 채 끝냈을 수 있고, 그 앞의 온전한 줄들이 정확히 알고 싶은 것이다.
TEST(JournalReader, SkipsAMalformedLineWithoutLosingTheRest) {
    const std::string text =
        R"({"kind":"session","event":"open","t":1000})" "\n"
        R"({"kind":"record","seq":1,"t":1001,"sev":"error","tag":"A","msg":"good"})" "\n"
        R"({"kind":"record","seq":2,"t":1002,"sev":"err)" "\n"   // 잘린 줄
        R"({"kind":"record","seq":3,"t":1003,"sev":"error","tag":"C","msg":"also good"})" "\n";

    const std::vector<maro::JournalSession> sessions = maro::parseJournal(text);

    ASSERT_EQ(sessions.size(), 1u);
    ASSERT_EQ(sessions[0].records.size(), 2u)
        << "the truncated line is dropped, the two intact ones survive";
    EXPECT_EQ(sessions[0].records[0].siteTag, "A");
    EXPECT_EQ(sessions[0].records[1].siteTag, "C");
}

// 억제 줄은 레코드가 아니다 -- 세지 않는다.
TEST(JournalReader, SuppressedLinesAreNotRecords) {
    const std::string text =
        R"({"kind":"session","event":"open","t":1000})" "\n"
        R"({"kind":"record","seq":1,"t":1001,"sev":"warn","tag":"A","msg":"x"})" "\n"
        R"({"kind":"suppressed","t":1002,"tag":"A","count":15})" "\n"
        R"({"kind":"session","event":"close","t":1003})" "\n";

    const std::vector<maro::JournalSession> sessions = maro::parseJournal(text);

    ASSERT_EQ(sessions.size(), 1u);
    EXPECT_EQ(sessions[0].records.size(), 1u);
}

TEST(JournalReader, AnEmptyJournalYieldsNoSessions) {
    EXPECT_TRUE(maro::parseJournal("").empty());
    EXPECT_TRUE(maro::parseJournal("\n\n").empty());
}

// 유효한 JSON이지만 모양이 어긋난 줄(알몸 스칼라, kind가 문자열이 아닌 경우)도
// 깨진 줄과 똑같이 취급되어야 한다 -- 그 줄만 버리고 나머지는 살아남으며,
// 예외가 parseJournal 밖으로 새 나가면 안 된다(Maya 콜백까지 뚫고 올라간다).
TEST(JournalReader, SkipsAMalformedShapeLineWithoutThrowing) {
    const std::string text =
        R"({"kind":"session","event":"open","t":1000})" "\n"
        R"({"kind":"record","seq":1,"t":1001,"sev":"error","tag":"A","msg":"good"})" "\n"
        R"(null)" "\n"                                            // 알몸 스칼라 줄
        R"({"kind":123,"event":"open"})" "\n"                     // kind가 숫자
        R"({"kind":"record","seq":2,"t":1002,"sev":"error","tag":"C","msg":"also good"})" "\n";

    std::vector<maro::JournalSession> sessions;
    EXPECT_NO_THROW(sessions = maro::parseJournal(text));

    ASSERT_EQ(sessions.size(), 1u);
    ASSERT_EQ(sessions[0].records.size(), 2u)
        << "the malformed-shape lines are dropped, the two intact records survive";
    EXPECT_EQ(sessions[0].records[0].siteTag, "A");
    EXPECT_EQ(sessions[0].records[1].siteTag, "C");
}

// event가 정확히 "close"일 때만 세션이 깨끗하게 끝난 것이다. 오타나 미래의
// 새 이벤트 값처럼 "open"도 "close"도 아닌 값이 세션을 조용히 깨끗한 종료로
// 뒤집으면 안 된다 -- 크래시를 놓치는 가장 위험한 거짓 음성이다.
TEST(JournalReader, AnUnrecognizedSessionEventDoesNotEndTheSessionCleanly) {
    const std::string text =
        R"({"kind":"session","event":"open","t":1000})" "\n"
        R"({"kind":"record","seq":1,"t":1001,"sev":"error","tag":"A","msg":"before something"})" "\n"
        R"({"kind":"session","event":"pause","t":1002})" "\n";

    const std::vector<maro::JournalSession> sessions = maro::parseJournal(text);

    ASSERT_EQ(sessions.size(), 1u);
    EXPECT_FALSE(sessions[0].endedCleanly)
        << "only an event of exactly \"close\" may end a session cleanly";
}
