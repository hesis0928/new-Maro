#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "maro_diag/DiagRecord.h"
#include "maro_diag/Journal.h"
#include "maro_diag/JournalWriter.h"

namespace {

// 테스트마다 자기만의 빈 디렉터리를 쓴다 -- 이전 실행이 남긴 저널이
// 다음 실행의 단언을 바꾸면 안 된다 (Layer A가 book에서 겪은 함정).
std::filesystem::path freshDir(const std::string& name) {
    const std::filesystem::path dir =
        std::filesystem::temp_directory_path() / ("maro_journal_test_" + name);
    std::error_code ec;
    std::filesystem::remove_all(dir, ec);
    std::filesystem::create_directories(dir, ec);
    return dir;
}

std::string readAll(const std::filesystem::path& p) {
    std::ifstream in(p, std::ios::binary);
    std::ostringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

std::size_t countLines(const std::string& text) {
    if (text.empty()) return 0;
    std::size_t n = 0;
    for (const char c : text) {
        if (c == '\n') ++n;
    }
    return n;
}

// text를 개행 기준으로 줄 목록으로 쪼갠다 (각 줄 자체는 한 JSON 값이므로
// 필드 단위로 파싱해 단언하려면 줄을 먼저 떼어내야 한다). 끝의 빈 조각은
// 버린다 -- writeLine이 항상 개행으로 끝내므로 마지막 split 결과는 늘 "".
std::vector<std::string> splitLines(const std::string& text) {
    std::vector<std::string> lines;
    std::size_t start = 0;
    while (start <= text.size()) {
        const std::size_t pos = text.find('\n', start);
        if (pos == std::string::npos) {
            if (start < text.size()) lines.push_back(text.substr(start));
            break;
        }
        lines.push_back(text.substr(start, pos - start));
        start = pos + 1;
    }
    return lines;
}

}  // namespace

TEST(JournalWriter, WritesOneLinePerRecord) {
    const std::filesystem::path dir = freshDir("one_line");
    const std::filesystem::path file = dir / "journal.jsonl";
    {
        maro::JournalWriter writer(file);
        ASSERT_TRUE(writer.isOpen());
        writer.writeSessionOpen(1000);
        writer.writeRecord(1, 1001, maro::DiagSeverity::Error, "Site.A", "first");
        writer.writeRecord(2, 1002, maro::DiagSeverity::Warn, "", "second");
        writer.writeSessionClose(1003);
    }

    const std::string text = readAll(file);
    EXPECT_EQ(countLines(text), 4u) << "open + two records + close";
    EXPECT_NE(text.find("\"kind\":\"session\""), std::string::npos);
    EXPECT_NE(text.find("\"event\":\"open\""), std::string::npos);
    EXPECT_NE(text.find("\"event\":\"close\""), std::string::npos);
    EXPECT_NE(text.find("Site.A"), std::string::npos);

    // 부분 문자열 검색은 tag와 msg가 뒤바뀌거나 sev가 하드코딩돼도 못 잡는다
    // (Finding 2) -- 각 레코드 줄을 JSON으로 파싱해 필드 값을 직접 확인한다.
    const std::vector<std::string> lines = splitLines(text);
    ASSERT_EQ(lines.size(), 4u);

    const nlohmann::json rec1 = nlohmann::json::parse(lines[1]);
    EXPECT_EQ(rec1.at("kind"), "record");
    EXPECT_EQ(rec1.at("seq"), 1u);
    EXPECT_EQ(rec1.at("t"), 1001u);
    EXPECT_EQ(rec1.at("sev"), "error");
    EXPECT_EQ(rec1.at("tag"), "Site.A");
    EXPECT_EQ(rec1.at("msg"), "first");

    const nlohmann::json rec2 = nlohmann::json::parse(lines[2]);
    EXPECT_EQ(rec2.at("kind"), "record");
    EXPECT_EQ(rec2.at("seq"), 2u);
    EXPECT_EQ(rec2.at("t"), 1002u);
    EXPECT_EQ(rec2.at("sev"), "warn");
    EXPECT_EQ(rec2.at("tag"), "");
    EXPECT_EQ(rec2.at("msg"), "second");
}

// 진단 경로는 저널을 못 열어서 실패하지 않는다. 쓸 수 없는 경로를 줘도
// 생성자가 던지지 않고, 이후 호출이 전부 조용히 무시돼야 한다.
TEST(JournalWriter, DegradesWhenTheFileCannotBeOpened) {
    const std::filesystem::path dir = freshDir("unwritable");
    // 파일을 하나 만들어 두고 그 "밑"을 경로로 준다 -- 디렉터리가 될 수
    // 없는 자리라 열기가 반드시 실패한다.
    const std::filesystem::path blocker = dir / "blocker";
    { std::ofstream(blocker) << "x"; }
    const std::filesystem::path impossible = blocker / "nested" / "journal.jsonl";

    maro::JournalWriter writer(impossible);
    EXPECT_FALSE(writer.isOpen());

    // 아래 호출들이 던지면 이 테스트는 그 자리에서 죽는다.
    writer.writeSessionOpen(1000);
    writer.writeRecord(1, 1001, maro::DiagSeverity::Error, "Site.A", "first");
    writer.writeSessionClose(1002);
    SUCCEED() << "a journal that cannot be opened must not throw or crash";
}

// 이어서 쓰는 저널이므로 기존 내용을 절대 지우지 않는다.
TEST(JournalWriter, AppendsInsteadOfTruncating) {
    const std::filesystem::path dir = freshDir("append");
    const std::filesystem::path file = dir / "journal.jsonl";
    {
        maro::JournalWriter writer(file);
        writer.writeSessionOpen(1000);
        writer.writeSessionClose(1001);
    }
    {
        maro::JournalWriter writer(file);
        writer.writeSessionOpen(2000);
        writer.writeSessionClose(2001);
    }

    const std::string text = readAll(file);
    EXPECT_EQ(countLines(text), 4u) << "the second session must not erase the first";
    EXPECT_NE(text.find("1000"), std::string::npos);
    EXPECT_NE(text.find("2000"), std::string::npos);
}

// 메시지에 개행이나 따옴표가 들어가도 한 줄 = 한 항목이 깨지면 안 된다.
TEST(JournalWriter, KeepsOneLinePerEntryWhenTheMessageHasNewlines) {
    const std::filesystem::path dir = freshDir("escaping");
    const std::filesystem::path file = dir / "journal.jsonl";
    {
        maro::JournalWriter writer(file);
        writer.writeSessionOpen(1000);
        writer.writeRecord(1, 1001, maro::DiagSeverity::Error, "Site.A",
                            "line one\nline two \"quoted\"");
        writer.writeSessionClose(1002);
    }

    const std::string text = readAll(file);
    EXPECT_EQ(countLines(text), 3u)
        << "a newline inside the message must be escaped, not split the entry";
}

// siteTag/message are caller-supplied strings that can originate from
// Windows APIs or ROS payloads -- nothing guarantees they are valid UTF-8.
// nlohmann::json::dump() defaults to strict error handling and throws on
// invalid UTF-8. That throw must never reach the caller: JournalWriter's
// callers are eventually Maya callbacks, and an exception escaping one of
// those ends the user's session. The invalid byte is constructed explicitly
// (a lone 0x80 continuation byte with no lead byte) rather than written as a
// literal, since an editor or the build's source encoding could silently
// "fix" a literal invalid byte sequence.
TEST(JournalWriter, InvalidUtf8InRecordDoesNotThrowAndLeavesJournalParseable) {
    const std::filesystem::path dir = freshDir("invalid_utf8");
    const std::filesystem::path file = dir / "journal.jsonl";

    std::string invalidUtf8Tag = "bad-";
    invalidUtf8Tag.push_back(static_cast<char>(0x80));  // lone continuation byte
    invalidUtf8Tag += "-tag";

    {
        maro::JournalWriter writer(file);
        ASSERT_TRUE(writer.isOpen());
        writer.writeRecord(1, 1000, maro::DiagSeverity::Info, "Site.Before", "before");
        // Must return normally even though dump() rejects the invalid UTF-8
        // inside siteTag -- losing this one line is fine, an escaping
        // exception is not.
        EXPECT_NO_THROW(writer.writeRecord(2, 1001, maro::DiagSeverity::Error,
                                            invalidUtf8Tag, "poisoned"));
        writer.writeRecord(3, 1002, maro::DiagSeverity::Info, "Site.After", "after");
    }

    const std::string text = readAll(file);
    const std::vector<std::string> lines = splitLines(text);

    // The poisoned record must simply be absent, not present as a broken or
    // partially-written line that would corrupt parsing of what follows.
    ASSERT_EQ(lines.size(), 2u)
        << "the record whose serialization failed must be dropped whole, "
           "not partially written";

    const nlohmann::json before = nlohmann::json::parse(lines[0]);
    EXPECT_EQ(before.at("seq"), 1u);
    EXPECT_EQ(before.at("tag"), "Site.Before");
    EXPECT_EQ(before.at("msg"), "before");

    const nlohmann::json after = nlohmann::json::parse(lines[1]);
    EXPECT_EQ(after.at("seq"), 3u);
    EXPECT_EQ(after.at("tag"), "Site.After");
    EXPECT_EQ(after.at("msg"), "after");
}

// 같은 태그가 창 안에서 예산을 넘기면 더 쓰지 않고, 창이 닫힐 때 몇 개를
// 생략했는지 한 줄로 남긴다.
TEST(JournalWriter, SuppressesOneTagBeyondItsBudget) {
    const std::filesystem::path dir = freshDir("suppress");
    const std::filesystem::path file = dir / "journal.jsonl";
    {
        maro::JournalWriter writer(file);
        writer.writeSessionOpen(1000);
        // 같은 창(1000~1999) 안에서 같은 태그로 20번.
        for (std::uint64_t i = 0; i < 20; ++i) {
            writer.writeRecord(i + 1, 1000 + i, maro::DiagSeverity::Warn,
                                "Site.Spam", "spam");
        }
        // 창을 넘겨 다음 줄을 쓰면 생략 개수가 나온다.
        writer.writeRecord(100, 3000, maro::DiagSeverity::Warn, "Site.Spam", "after");
        writer.writeSessionClose(3001);
    }

    const std::string text = readAll(file);
    // open + 예산 5줄 + suppressed 1줄 + 창 밖 1줄 + close = 9
    EXPECT_EQ(countLines(text), 9u)
        << "twenty hits on one tag inside one window must not become twenty lines";
    EXPECT_NE(text.find("\"kind\":\"suppressed\""), std::string::npos);
    EXPECT_NE(text.find("\"count\":15"), std::string::npos)
        << "fifteen of the twenty were dropped";
}

// 서로 다른 태그는 서로의 예산을 잡아먹지 않는다. 병렬 평가에서 여러 노드의
// 경고가 번갈아 들어오는 것이 실제 입력이므로, 이것이 깨지면 억제를 넣은
// 이유가 통째로 무너진다.
TEST(JournalWriter, TagsDoNotSpendEachOthersBudget) {
    const std::filesystem::path dir = freshDir("interleaved");
    const std::filesystem::path file = dir / "journal.jsonl";
    {
        maro::JournalWriter writer(file);
        writer.writeSessionOpen(1000);
        // 두 태그를 번갈아 4번씩 -- 각자 예산(5) 안이므로 전부 쓰여야 한다.
        for (std::uint64_t i = 0; i < 4; ++i) {
            writer.writeRecord(i * 2 + 1, 1000 + i, maro::DiagSeverity::Warn,
                                "Site.A", "a");
            writer.writeRecord(i * 2 + 2, 1000 + i, maro::DiagSeverity::Warn,
                                "Site.B", "b");
        }
        writer.writeSessionClose(1500);
    }

    const std::string text = readAll(file);
    EXPECT_EQ(countLines(text), 10u) << "open + 4 A + 4 B + close";
    EXPECT_EQ(text.find("\"kind\":\"suppressed\""), std::string::npos)
        << "neither tag exceeded its own budget, so nothing was suppressed";
}

// 태그가 없는 레코드(에러가 아닌 info/warn/devInfo -- BoadMaro::info/warn/
// devInfo는 siteTag를 받지 않으므로 플러그인의 비-에러 진단은 전부 이 경로를
// 지난다)도 서로 다른 메시지라면 서로의 예산을 잡아먹지 않아야 한다. 키가
// 심각도 하나로 뭉개지면 무관한 두 경고가 서로를 억제하기 시작하는데, 그게
// 바로 태그별 억제가 막으려는 실패 형태다. 위 TagsDoNotSpendEachOthersBudget과
// 같은 모양이지만 태그 없이, 메시지 텍스트만 다르게 준다.
TEST(JournalWriter, UntaggedMessagesDoNotSpendEachOthersBudget) {
    const std::filesystem::path dir = freshDir("untagged_interleaved");
    const std::filesystem::path file = dir / "journal.jsonl";
    {
        maro::JournalWriter writer(file);
        writer.writeSessionOpen(1000);
        // 태그 없는 두 메시지(같은 심각도, 텍스트만 다름)를 번갈아 4번씩 --
        // 각자 예산(5) 안이므로 전부 쓰여야 한다. 억제 키가 심각도 하나로
        // 뭉개지면 여덟 번째 쓰기(둘을 합쳐 5를 넘는 지점)부터 억제가
        // 걸린다.
        for (std::uint64_t i = 0; i < 4; ++i) {
            writer.writeRecord(i * 2 + 1, 1000 + i, maro::DiagSeverity::Warn, "",
                                "alpha message");
            writer.writeRecord(i * 2 + 2, 1000 + i, maro::DiagSeverity::Warn, "",
                                "beta message");
        }
        writer.writeSessionClose(1500);
    }

    const std::string text = readAll(file);
    EXPECT_EQ(countLines(text), 10u) << "open + 4 alpha + 4 beta + close";
    EXPECT_EQ(text.find("\"kind\":\"suppressed\""), std::string::npos)
        << "neither untagged message exceeded its own budget, so nothing was "
           "suppressed";
}

// 창이 지나면 예산이 되살아난다.
TEST(JournalWriter, BudgetRefillsAfterTheWindow) {
    const std::filesystem::path dir = freshDir("refill");
    const std::filesystem::path file = dir / "journal.jsonl";
    {
        maro::JournalWriter writer(file);
        writer.writeSessionOpen(1000);
        for (std::uint64_t i = 0; i < 5; ++i) {
            writer.writeRecord(i + 1, 1000, maro::DiagSeverity::Warn, "Site.A", "a");
        }
        // 창을 훌쩍 넘긴 시각 -- 예산이 되살아나 다시 5줄이 쓰여야 한다.
        for (std::uint64_t i = 0; i < 5; ++i) {
            writer.writeRecord(i + 10, 9000, maro::DiagSeverity::Warn, "Site.A", "a");
        }
        writer.writeSessionClose(9500);
    }

    const std::string text = readAll(file);
    EXPECT_EQ(countLines(text), 12u) << "open + 5 + 5 + close, with nothing suppressed";
}

// budgets_ 맵은 무한히 자라면 안 된다(태그 없는 레코드는 메시지 첫 줄을 키에
// 섞으므로, 동적인 내용을 담은 메시지가 반복되면 키가 계속 새로 생긴다).
// 맵이 kJournalMaxBudgetKeys에 닿으면 창이 이미 닫힌 항목부터 정리되는데,
// 그 정리가 밀린 suppressed 카운트를 조용히 버리면 안 된다 -- 그 카운트는
// "N줄 생략" 안내이고, 그 항목의 키를 다시는 안 쓸 수도 있으므로 지금
// 플러시하지 않으면 사용자는 영영 그 안내를 못 본다.
//
// "victim" 키 하나로 예산(5)을 넘겨 suppressed=1을 만든 뒤, 그 창이 닫힐
// 시각으로 넘어가 서로 다른 새 키를 kJournalMaxBudgetKeys개 채운다. 마지막
// 새 키를 넣는 순간 맵이 상한에 닿아 정리가 돌고, victim의 창은 이미
// 닫혀 있으므로 정리 대상이 된다 -- 그 정리가 victim을 다시 만나기 전에
// "1줄 생략"을 저널에 남겨야 한다. victim은 이후 다시 쓰이지 않으므로,
// 이 줄은 오직 정리 과정 자체에서만 나올 수 있다.
TEST(JournalWriter, SweepFlushesPendingSuppressedCountBeforeDroppingAStaleEntry) {
    const std::filesystem::path dir = freshDir("sweep_flushes");
    const std::filesystem::path file = dir / "journal.jsonl";
    {
        maro::JournalWriter writer(file);
        writer.writeSessionOpen(1000);

        // victim: 태그 없음, 창(1000..1999) 안에서 예산(5)을 넘겨 6번 쓴다
        // -- 마지막 한 번이 suppressed=1을 남긴다.
        for (std::uint64_t i = 0; i < 6; ++i) {
            writer.writeRecord(i + 1, 1000, maro::DiagSeverity::Warn, "",
                                "victim message");
        }

        // victim의 창이 확실히 닫힐 시각으로 넘어간다.
        const std::uint64_t sweepTime = 5000;

        // 서로 다른 새 키를 kJournalMaxBudgetKeys개, 전부 sweepTime에 쓴다
        // (그래서 이 키들 자신의 창은 아직 열려 있어 정리 대상이 아니다).
        // kJournalMaxBudgetKeys번째 새 키를 넣을 때 맵 크기가 상한(victim +
        // 그 앞의 새 키들)에 닿아 정리가 트리거된다.
        for (std::size_t i = 0; i < maro::kJournalMaxBudgetKeys; ++i) {
            writer.writeRecord(1000 + i, sweepTime, maro::DiagSeverity::Warn, "",
                                "filler message " + std::to_string(i));
        }

        writer.writeSessionClose(sweepTime + 100);
    }

    const std::string text = readAll(file);
    const std::vector<std::string> lines = splitLines(text);

    // 정확히 victim에 대한 것 하나만 있어야 한다: 새 키들은 전부 자기
    // 예산(5) 안에서 한 번씩만 쓰였으므로 스스로는 어떤 생략도 만들지 않는다.
    std::vector<nlohmann::json> suppressedLines;
    for (const std::string& line : lines) {
        const nlohmann::json parsed = nlohmann::json::parse(line);
        if (parsed.at("kind") == "suppressed") suppressedLines.push_back(parsed);
    }

    ASSERT_EQ(suppressedLines.size(), 1u)
        << "the victim's pending suppressed count must be flushed exactly "
           "once by the sweep, since victim is never written to again and "
           "so has no other chance to be flushed";
    EXPECT_EQ(suppressedLines[0].at("tag"), "warn:victim message")
        << "the flushed line must name the evicted key, not some other entry";
    EXPECT_EQ(suppressedLines[0].at("count"), 1u)
        << "exactly one write beyond victim's budget of 5 was suppressed";
}

// 회전은 최근 N 세션만 남긴다. 오래된 세션이 통째로 사라지고 최근 것은
// 온전히 남아야 한다.
TEST(JournalWriter, RotateKeepsOnlyTheMostRecentSessions) {
    const std::filesystem::path dir = freshDir("rotate");
    const std::filesystem::path file = dir / "journal.jsonl";
    {
        maro::JournalWriter writer(file);
        // 보관 한도보다 5개 많은 세션을 쓴다. 각 세션은 자기 번호를 담은
        // 레코드를 하나씩 갖는다.
        for (std::uint64_t s = 0; s < maro::kJournalSessionsKept + 5; ++s) {
            writer.writeSessionOpen(1000 + s * 10);
            writer.writeRecord(s + 1, 1001 + s * 10, maro::DiagSeverity::Error,
                                "Site.S" + std::to_string(s), "session marker");
            writer.writeSessionClose(1002 + s * 10);
        }
    }

    maro::JournalWriter::rotate(file);

    const std::string text = readAll(file);
    EXPECT_EQ(text.find("Site.S0"), std::string::npos)
        << "the oldest session must be gone";
    EXPECT_EQ(text.find("Site.S4"), std::string::npos)
        << "everything beyond the keep limit must be gone";
    EXPECT_NE(text.find("Site.S5"), std::string::npos)
        << "the tenth-from-last session must survive";
    EXPECT_NE(text.find("Site.S14"), std::string::npos)
        << "the newest session must survive";
    EXPECT_EQ(countLines(text), maro::kJournalSessionsKept * 3)
        << "each kept session contributes open + record + close";
}

// 보관 한도보다 적으면 아무것도 버리지 않는다.
TEST(JournalWriter, RotateLeavesAShortJournalAlone) {
    const std::filesystem::path dir = freshDir("rotate_short");
    const std::filesystem::path file = dir / "journal.jsonl";
    {
        maro::JournalWriter writer(file);
        writer.writeSessionOpen(1000);
        writer.writeRecord(1, 1001, maro::DiagSeverity::Error, "Site.Only", "only");
        writer.writeSessionClose(1002);
    }
    const std::string before = readAll(file);

    maro::JournalWriter::rotate(file);

    EXPECT_EQ(readAll(file), before) << "nothing to drop, so nothing may change";
}

// 저널이 아예 없어도 회전이 죽지 않는다 -- 첫 실행이 그 상태다.
TEST(JournalWriter, RotateOnAMissingFileIsHarmless) {
    const std::filesystem::path dir = freshDir("rotate_missing");
    const std::filesystem::path file = dir / "journal.jsonl";
    maro::JournalWriter::rotate(file);
    SUCCEED() << "rotating a journal that does not exist must not throw";
}
