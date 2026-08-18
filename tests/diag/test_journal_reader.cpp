#include <gtest/gtest.h>

#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

#include "maro_diag/Journal.h"
#include "maro_diag/JournalReader.h"
#include "maro_diag/JournalWriter.h"

namespace {

// Finding C1(리브니스) 테스트들이 쓰는 빈 디렉터리 -- 이전 실행이 남긴
// 저널 파일이 다음 실행의 집계를 바꾸면 안 된다
// (test_journal_writer.cpp의 freshDir과 같은 이유, 같은 모양).
std::filesystem::path freshDir(const std::string& name) {
    const std::filesystem::path dir =
        std::filesystem::temp_directory_path() / ("maro_journal_reader_test_" + name);
    std::error_code ec;
    std::filesystem::remove_all(dir, ec);
    std::filesystem::create_directories(dir, ec);
    return dir;
}

}  // namespace

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

namespace {

maro::JournalSession makeSession(bool endedCleanly,
                                  const std::vector<std::string>& tags) {
    maro::JournalSession session;
    session.endedCleanly = endedCleanly;
    std::uint64_t seq = 1;
    for (const std::string& tag : tags) {
        maro::JournalRecord rec;
        rec.sequence = seq++;
        rec.timestampMs = 1000 + seq;
        rec.severity = maro::DiagSeverity::Error;
        rec.siteTag = tag;
        rec.message = "m";
        session.records.push_back(rec);
    }
    return session;
}

}  // namespace

// 정상 종료 세션은 분모에도 분자에도 들어가지 않는다.
TEST(JournalReader, CleanSessionsAreNotCounted) {
    std::vector<maro::JournalSession> sessions;
    sessions.push_back(makeSession(true, {"A", "B"}));
    sessions.push_back(makeSession(true, {"A"}));

    const maro::CrashAdjacency adj = maro::countCrashAdjacentTags(sessions);

    EXPECT_EQ(adj.abnormalSessionCount, 0u);
    EXPECT_TRUE(adj.appearancesByTag.empty());
}

// 한 세션은 한 표다. 한 세션에서 40번 나온 태그도 표는 하나다 -- 안 그러면
// 폭주한 태그 하나가 모든 세션의 표를 독식한다.
TEST(JournalReader, OneSessionIsOneVoteRegardlessOfRepeats) {
    std::vector<std::string> spammy;
    for (int i = 0; i < 15; ++i) spammy.push_back("Spam");
    spammy.push_back("Rare");

    std::vector<maro::JournalSession> sessions;
    sessions.push_back(makeSession(false, spammy));

    const maro::CrashAdjacency adj = maro::countCrashAdjacentTags(sessions);

    EXPECT_EQ(adj.abnormalSessionCount, 1u);
    EXPECT_EQ(adj.appearancesByTag.at("Spam"), 1u)
        << "fifteen hits in one session is still one session";
    EXPECT_EQ(adj.appearancesByTag.at("Rare"), 1u);
}

// 마지막 구간 밖의 태그는 세지 않는다. 구간은 마지막 레코드 20개다.
TEST(JournalReader, OnlyTheTailOfTheSessionCounts) {
    std::vector<std::string> tags;
    tags.push_back("TooEarly");
    for (std::size_t i = 0; i < maro::kJournalTailRecordsForSignal; ++i) {
        tags.push_back("InTail");
    }

    std::vector<maro::JournalSession> sessions;
    sessions.push_back(makeSession(false, tags));

    const maro::CrashAdjacency adj = maro::countCrashAdjacentTags(sessions);

    EXPECT_EQ(adj.appearancesByTag.count("TooEarly"), 0u)
        << "it sits one record before the tail window";
    EXPECT_EQ(adj.appearancesByTag.at("InTail"), 1u);
}

// 구간의 첫 레코드(가장 오래된 쪽 경계)는 반드시 포함되어야 한다. 위 테스트는
// 구간 전체가 같은 태그("InTail")로 채워져 있어서, 구간을 한 칸 좁혀 그
// 첫 레코드를 놓쳐도 "한 세션은 한 표" 중복 제거 때문에 겉으로 드러나지
// 않는다 -- 그 자리에 고유한 태그를 둬서 경계 자체를 고정한다.
TEST(JournalReader, TheOldestRecordOfTheTailWindowIsIncluded) {
    std::vector<std::string> tags;
    tags.push_back("TooEarly");
    tags.push_back("EdgeOfTail");  // 구간의 첫(가장 오래된) 레코드, 유일한 태그
    // 나머지는 구간을 kJournalTailRecordsForSignal개로 채운다:
    // 1(TooEarly) + 1(EdgeOfTail) + (N-1)(Filler) = N+1개 전체, 구간은 마지막 N개.
    for (std::size_t i = 0; i + 1 < maro::kJournalTailRecordsForSignal; ++i) {
        tags.push_back("Filler");
    }

    std::vector<maro::JournalSession> sessions;
    sessions.push_back(makeSession(false, tags));

    const maro::CrashAdjacency adj = maro::countCrashAdjacentTags(sessions);

    EXPECT_EQ(adj.appearancesByTag.count("TooEarly"), 0u);
    EXPECT_EQ(adj.appearancesByTag.at("EdgeOfTail"), 1u)
        << "the tail window is the last kJournalTailRecordsForSignal records, "
           "and this is the oldest one in it";
}

// 세션의 전체 레코드가 구간보다 적으면 전부를 본다.
TEST(JournalReader, AShortSessionIsCountedWhole) {
    std::vector<maro::JournalSession> sessions;
    sessions.push_back(makeSession(false, {"A", "B"}));

    const maro::CrashAdjacency adj = maro::countCrashAdjacentTags(sessions);

    EXPECT_EQ(adj.appearancesByTag.at("A"), 1u);
    EXPECT_EQ(adj.appearancesByTag.at("B"), 1u);
}

// 여러 비정상 세션에 걸쳐 누적된다 -- 이것이 신호의 실체다.
TEST(JournalReader, AccumulatesAcrossAbnormalSessions) {
    std::vector<maro::JournalSession> sessions;
    sessions.push_back(makeSession(false, {"Recurring", "OnceOnly"}));
    sessions.push_back(makeSession(true, {"Recurring"}));   // 정상 -- 세지 않는다
    sessions.push_back(makeSession(false, {"Recurring"}));

    const maro::CrashAdjacency adj = maro::countCrashAdjacentTags(sessions);

    EXPECT_EQ(adj.abnormalSessionCount, 2u);
    EXPECT_EQ(adj.appearancesByTag.at("Recurring"), 2u);
    EXPECT_EQ(adj.appearancesByTag.at("OnceOnly"), 1u);
}

// 레코드가 하나도 없는 비정상 세션(예: 열리자마자, 진단 하나 남기기 전에
// 죽은 경우)도 분모에는 들어가야 한다 -- 그 분모(abnormalSessionCount)는
// 사용자에게 보여주는 모든 비율(N회 중 M회)의 아래쪽 숫자이므로, 여기서
// 빠뜨리면 모든 비율이 실제보다 높게 보인다. countCrashAdjacentTags의
// 루프는 이미 레코드 개수와 무관하게 continue 없이 abnormalSessionCount를
// 먼저 올리므로 이 값 자체는 오늘도 맞게 나온다 -- 그런데 그 결정을 실제로
// 값으로 고정한 테스트가 지금까지 없었다.
TEST(JournalReader, AnAbnormalSessionWithNoRecordsStillCountsInTheDenominator) {
    std::vector<maro::JournalSession> sessions;
    sessions.push_back(makeSession(false, {}));

    const maro::CrashAdjacency adj = maro::countCrashAdjacentTags(sessions);

    EXPECT_EQ(adj.abnormalSessionCount, 1u)
        << "an abnormal session with zero records must still count in the denominator";
    EXPECT_TRUE(adj.appearancesByTag.empty())
        << "no records means no tag can have appeared in the tail";
}

// 태그가 없는 레코드(에러가 아닌 것)는 신호의 대상이 아니다 -- 신호는
// 사이트 태그로 지목되는 실패에 붙는다.
TEST(JournalReader, RecordsWithoutASiteTagAreIgnored) {
    std::vector<maro::JournalSession> sessions;
    sessions.push_back(makeSession(false, {"", "A"}));

    const maro::CrashAdjacency adj = maro::countCrashAdjacentTags(sessions);

    EXPECT_EQ(adj.appearancesByTag.count(""), 0u);
    EXPECT_EQ(adj.appearancesByTag.at("A"), 1u);
}

// Finding C1 -- 저널이 프로세스별 파일로 나뉘므로, 관측을 합치는 것은 여러
// 파일을 각자 파싱한 CrashAdjacency를 더하는 일이 된다. 세션 하나는 정확히
// 자기 파일 안에서만 등장하므로 단순 덧셈이면 충분하다.
TEST(JournalReader, MergeCrashAdjacencyAddsCountsAcrossFiles) {
    maro::CrashAdjacency fileA;
    fileA.abnormalSessionCount = 2;
    fileA.appearancesByTag["Recurring"] = 2;
    fileA.appearancesByTag["OnlyInA"] = 1;

    maro::CrashAdjacency fileB;
    fileB.abnormalSessionCount = 1;
    fileB.appearancesByTag["Recurring"] = 1;
    fileB.appearancesByTag["OnlyInB"] = 1;

    maro::CrashAdjacency total;
    maro::mergeCrashAdjacency(total, fileA);
    maro::mergeCrashAdjacency(total, fileB);

    EXPECT_EQ(total.abnormalSessionCount, 3u);
    EXPECT_EQ(total.appearancesByTag.at("Recurring"), 3u);
    EXPECT_EQ(total.appearancesByTag.at("OnlyInA"), 1u);
    EXPECT_EQ(total.appearancesByTag.at("OnlyInB"), 1u);
}

// Finding C1 -- the pinned regression for the multi-writer case. Under the
// old single-shared-file design, an interleaved journal (session B opens
// while session A is still open, and A's own close line arrives after B's
// open) would misattribute A's close to B and steal A's trailing record into
// B's tail (see the review's own repro, and the now-removed scratch test
// that confirmed it against the pre-fix parser). With per-process files,
// what would have been one interleaved file is physically two independent
// files instead -- so the equivalent pin is: parse each file's text on its
// own, and confirm neither session contaminates or closes the other, even
// though B's open genuinely happened, in wall-clock time, before A's close.
TEST(JournalReader, TwoIndependentJournalFilesAreReadAsTwoIndependentSessionSetsAndNeitherClosesTheOther) {
    // What process A's own file contains: A opens, writes twice (the second
    // write happens temporally *after* B has already opened, in real time --
    // but that fact left no mark in A's file, because B never touched it).
    const std::string fileAText =
        R"({"kind":"session","event":"open","t":1000})" "\n"
        R"({"kind":"record","seq":1,"t":1001,"sev":"error","tag":"A","msg":"a1"})" "\n"
        R"({"kind":"record","seq":2,"t":1003,"sev":"error","tag":"A","msg":"a2"})" "\n"
        R"({"kind":"session","event":"close","t":1005})" "\n";

    // What process B's own file contains: B opens while A is still open (in
    // wall-clock time), writes once, and closes before A does.
    const std::string fileBText =
        R"({"kind":"session","event":"open","t":1002})" "\n"
        R"({"kind":"record","seq":1,"t":1004,"sev":"warn","tag":"B","msg":"b1"})" "\n"
        R"({"kind":"session","event":"close","t":1006})" "\n";

    const std::vector<maro::JournalSession> sessionsA = maro::parseJournal(fileAText);
    const std::vector<maro::JournalSession> sessionsB = maro::parseJournal(fileBText);

    ASSERT_EQ(sessionsA.size(), 1u);
    EXPECT_TRUE(sessionsA[0].endedCleanly)
        << "A's own close, recorded only in A's file, must close A";
    ASSERT_EQ(sessionsA[0].records.size(), 2u)
        << "both of A's records stay in A -- B's file has no way to steal them";
    EXPECT_EQ(sessionsA[0].records[0].siteTag, "A");
    EXPECT_EQ(sessionsA[0].records[1].siteTag, "A");

    ASSERT_EQ(sessionsB.size(), 1u);
    EXPECT_TRUE(sessionsB[0].endedCleanly);
    ASSERT_EQ(sessionsB[0].records.size(), 1u);
    EXPECT_EQ(sessionsB[0].records[0].siteTag, "B");

    // The crash-adjacency observation, merged, must show both sessions
    // ended cleanly -- zero abnormal sessions, nothing crash-adjacent.
    maro::CrashAdjacency adjacency;
    maro::mergeCrashAdjacency(adjacency, maro::countCrashAdjacentTags(sessionsA));
    maro::mergeCrashAdjacency(adjacency, maro::countCrashAdjacentTags(sessionsB));
    EXPECT_EQ(adjacency.abnormalSessionCount, 0u)
        << "neither process crashed, and neither's file can fabricate the other's crash";
}

// 리뷰 Finding C1(리브니스) -- 파일을 프로세스별로 나눈 것은 오귀속을
// 닫았지만, 그 자체로는 이것을 닫지 못한다: 파일 내용만 보면 "아직 close를
// 안 썼다(도는 중)"와 "끝내 close를 못 썼다(크래시)"가 완전히 같은 모양이다.
// 아티스트가 Maya 창을 두 개 띄우면, 두 번째 창의 openJournal()이 첫 번째
// 창의(멀쩡히 살아 있는) 저널을 읽고 그 미종료 세션을 크래시로 센다 --
// 아무도 크래시하지 않았는데 문턱이 넘어간다.
//
// 그래서 집계는 파일 이름의 pid가 지금 살아 있는지를 파일 밖에 물어본다.
// 그 질문은 OS를 아는 계층(MaroDiag.cpp의 isProcessRunning, OpenProcess +
// WaitForSingleObject)이 답하고 여기 seam으로 주입되므로, 이 테스트는 진짜
// 프로세스를 띄우지 않고도 산 pid와 죽은 pid 양쪽 가지를 모두 돌린다.
//
// 두 파일은 내용이 글자 그대로 같은 모양(open + record, close 없음)이다 --
// 판정을 가르는 것은 오직 주인이 살아 있는가뿐이라는 것이 요점이다.
TEST(JournalReader, AStillRunningProcessesUnfinishedSessionIsNotCountedAsACrash) {
    const std::filesystem::path dir = freshDir("liveness");
    const std::uint64_t livePid = 31001;
    const std::uint64_t deadPid = 31002;

    {
        maro::JournalWriter live(maro::JournalWriter::pathForProcess(dir, livePid));
        ASSERT_TRUE(live.isOpen());
        live.writeSessionOpen(1000);
        live.writeRecord(1, 1001, maro::DiagSeverity::Error, "Site.StillRunning", "still working");
        // close 줄이 없다 -- 이 인스턴스는 아직 도는 중이다.
    }
    {
        maro::JournalWriter dead(maro::JournalWriter::pathForProcess(dir, deadPid));
        ASSERT_TRUE(dead.isOpen());
        dead.writeSessionOpen(2000);
        dead.writeRecord(1, 2001, maro::DiagSeverity::Error, "Site.ReallyCrashed", "last words");
        // close 줄이 없다 -- 이 인스턴스는 정말로 죽었다.
    }

    const maro::CrashAdjacency adjacency = maro::countCrashAdjacencyAcrossJournalFiles(
        dir, [livePid](std::uint64_t pid) { return pid == livePid; });

    EXPECT_EQ(adjacency.abnormalSessionCount, 1u)
        << "only the dead process crashed -- the live one's session is unfinished, not lost";
    EXPECT_EQ(adjacency.appearancesByTag.count("Site.StillRunning"), 0u)
        << "a diagnostic from a session that is still running must not be reported as "
           "crash-adjacent -- there is no crash to be adjacent to";
    ASSERT_EQ(adjacency.appearancesByTag.count("Site.ReallyCrashed"), 1u)
        << "the genuinely crashed process's tag must still be counted -- the liveness check "
           "must not swallow real crashes along with the false ones";
    EXPECT_EQ(adjacency.appearancesByTag.at("Site.ReallyCrashed"), 1u);
}

// 살아 있는 주인이라도 봐주는 것은 그 파일의 **마지막** 미종료 세션 하나
// 뿐이다. 한 파일 안에서 아직 도는 중일 수 있는 세션은 정의상 그 하나이고,
// 그 앞의 미종료 세션은 그 pid의 이전 화신이 실제로 죽었기 때문에 남은
// 것이므로 진짜 크래시다 (pid가 재사용되어 같은 이름의 파일에 이어 쓰는
// 경우가 정확히 이 모양이다).
TEST(JournalReader, ALiveProcessesEarlierUnfinishedSessionsAreStillRealCrashes) {
    const std::filesystem::path dir = freshDir("liveness_only_the_tail");
    const std::uint64_t livePid = 31003;

    {
        maro::JournalWriter writer(maro::JournalWriter::pathForProcess(dir, livePid));
        ASSERT_TRUE(writer.isOpen());
        // 이전 화신: 죽었다(close 없이 다음 open에 밀려 끊긴다).
        writer.writeSessionOpen(1000);
        writer.writeRecord(1, 1001, maro::DiagSeverity::Error, "Site.OldCrash", "died here");
        // 지금 도는 세션: 아직 안 끝났을 뿐이다.
        writer.writeSessionOpen(2000);
        writer.writeRecord(2, 2001, maro::DiagSeverity::Error, "Site.StillRunning", "working");
    }

    const maro::CrashAdjacency adjacency = maro::countCrashAdjacencyAcrossJournalFiles(
        dir, [livePid](std::uint64_t pid) { return pid == livePid; });

    EXPECT_EQ(adjacency.abnormalSessionCount, 1u)
        << "the earlier unterminated session really did crash and must still count";
    EXPECT_EQ(adjacency.appearancesByTag.count("Site.OldCrash"), 1u);
    EXPECT_EQ(adjacency.appearancesByTag.count("Site.StillRunning"), 0u)
        << "only the trailing session is spared, and only because its owner is alive";
}
