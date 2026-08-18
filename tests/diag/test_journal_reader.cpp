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
    EXPECT_EQ(sessions[1].records[0].siteTag, "B");
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
