#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>

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
