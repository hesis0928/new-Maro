#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>

#include "maro_diag/BookStore.h"

namespace {

// 테스트마다 고유한 임시 디렉터리. gtest의 현재 테스트 이름을 그대로 써서
// 병렬 실행이나 재실행에도 서로 밟지 않는다.
std::filesystem::path tempDirForTest() {
    const auto* info = ::testing::UnitTest::GetInstance()->current_test_info();
    auto dir = std::filesystem::path(::testing::TempDir()) /
               (std::string("maro_book_") + info->test_suite_name() + "_" + info->name());
    std::filesystem::remove_all(dir);
    std::filesystem::create_directories(dir);
    return dir;
}

}  // namespace

TEST(BookStore, MissingFilesYieldEmptyStoreWithoutThrowing) {
    const auto dir = tempDirForTest();
    const auto canonical = dir / "missing_canonical.jsonl";
    const auto spill = dir / "missing_spill.jsonl";

    maro::BookStore store;
    ASSERT_NO_THROW(store = maro::BookStore::loadMerged(canonical, spill));
    EXPECT_EQ(store.size(), 0u);

    maro::BookEntry out;
    EXPECT_FALSE(store.query("anything", out));
}

TEST(BookStore, SpillWinsOverCanonicalForSameHash) {
    const auto dir = tempDirForTest();
    const auto canonical = dir / "canonical.jsonl";
    const auto spill = dir / "spill.jsonl";

    {
        std::ofstream ofs(canonical);
        ofs << R"({"hash":"h1","analysis":"old analysis","remedy":"","nodeType":"","attributeName":"","activeCommand":"","axisOrTarget":""})" << "\n";
    }
    {
        std::ofstream ofs(spill);
        ofs << R"({"hash":"h1","analysis":"new analysis","remedy":"","nodeType":"","attributeName":"","activeCommand":"","axisOrTarget":""})" << "\n";
    }

    const auto store = maro::BookStore::loadMerged(canonical, spill);
    maro::BookEntry out;
    ASSERT_TRUE(store.query("h1", out));
    EXPECT_EQ(out.analysis, "new analysis");
}

TEST(BookStore, CorruptLineIsSkippedNotFatal) {
    const auto dir = tempDirForTest();
    const auto spill = dir / "spill.jsonl";

    {
        std::ofstream ofs(spill);
        ofs << "{ this is not json\n";
        ofs << R"({"hash":"h2","analysis":"still readable","remedy":"","nodeType":"","attributeName":"","activeCommand":"","axisOrTarget":""})" << "\n";
    }

    maro::BookStore store;
    ASSERT_NO_THROW(store = maro::BookStore::loadMerged(dir / "no_canonical.jsonl", spill));

    maro::BookEntry out;
    ASSERT_TRUE(store.query("h2", out));
    EXPECT_EQ(out.analysis, "still readable");
}

TEST(BookStore, AppendToSpillIsReadableAfterReload) {
    const auto dir = tempDirForTest();
    const auto spill = dir / "spill.jsonl";

    maro::BookEntry entry;
    entry.analysis = "first analysis";
    entry.context.nodeType = "maroAxis";
    ASSERT_TRUE(maro::BookStore::appendToSpill(spill, "h3", entry));

    const auto store = maro::BookStore::loadMerged(dir / "no_canonical.jsonl", spill);
    maro::BookEntry out;
    ASSERT_TRUE(store.query("h3", out));
    EXPECT_EQ(out.analysis, "first analysis");
    EXPECT_EQ(out.context.nodeType, "maroAxis");
}

TEST(BookStore, AppendAfterTruncatedFragmentPreservesNewEntry) {
    const auto dir = tempDirForTest();
    const auto spill = dir / "spill.jsonl";

    {
        // Simulate a previous process that died mid-write: a partial JSON
        // line with no trailing newline.
        std::ofstream ofs(spill, std::ios::binary);
        ofs << R"({"hash":"h5","analysis":"trunca)";
    }

    maro::BookEntry entry;
    entry.analysis = "post-crash entry";
    entry.context.nodeType = "maroAxis";
    ASSERT_TRUE(maro::BookStore::appendToSpill(spill, "h6", entry));

    const auto store = maro::BookStore::loadMerged(dir / "no_canonical.jsonl", spill);

    // The old fragment never becomes a valid record -- it stays unparseable
    // and is correctly skipped as corrupt.
    maro::BookEntry unused;
    EXPECT_FALSE(store.query("h5", unused));

    // But the new entry, appended after the fragment, must survive intact --
    // it must not be glued onto the fragment's tail and lost with it.
    maro::BookEntry out;
    ASSERT_TRUE(store.query("h6", out));
    EXPECT_EQ(out.analysis, "post-crash entry");
    EXPECT_EQ(out.context.nodeType, "maroAxis");
}

TEST(BookStore, WrongFieldTypeLineIsSkippedNotFatal) {
    const auto dir = tempDirForTest();
    const auto spill = dir / "spill.jsonl";

    {
        std::ofstream ofs(spill);
        ofs << R"({"hash":"h7","analysis":"valid before","remedy":"","nodeType":"","attributeName":"","activeCommand":"","axisOrTarget":""})" << "\n";
        // Syntactically valid JSON, but "analysis" is a number where a
        // string is expected -- this raises nlohmann::json::type_error,
        // a different exception type than the parse_error a malformed
        // line raises. The corrupt-line handler must catch both.
        ofs << R"({"hash":"h8","analysis":123,"remedy":"","nodeType":"","attributeName":"","activeCommand":"","axisOrTarget":""})" << "\n";
        ofs << R"({"hash":"h9","analysis":"valid after","remedy":"","nodeType":"","attributeName":"","activeCommand":"","axisOrTarget":""})" << "\n";
    }

    maro::BookStore store;
    ASSERT_NO_THROW(store = maro::BookStore::loadMerged(dir / "no_canonical.jsonl", spill));

    maro::BookEntry out;
    ASSERT_TRUE(store.query("h7", out));
    EXPECT_EQ(out.analysis, "valid before");

    EXPECT_FALSE(store.query("h8", out));

    ASSERT_TRUE(store.query("h9", out));
    EXPECT_EQ(out.analysis, "valid after");
}

TEST(BookStore, LatestAppendWinsForRepeatedHash) {
    const auto dir = tempDirForTest();
    const auto spill = dir / "spill.jsonl";

    maro::BookEntry first;
    first.analysis = "first";
    maro::BookEntry second;
    second.analysis = "second";
    second.remedy = "apply the fix";

    ASSERT_TRUE(maro::BookStore::appendToSpill(spill, "h4", first));
    ASSERT_TRUE(maro::BookStore::appendToSpill(spill, "h4", second));

    const auto store = maro::BookStore::loadMerged(dir / "no_canonical.jsonl", spill);
    maro::BookEntry out;
    ASSERT_TRUE(store.query("h4", out));
    EXPECT_EQ(out.analysis, "second");
    EXPECT_EQ(out.remedy, "apply the fix");
}

// analysis/message 원문은 ROS 페이로드나 Windows API에서 오므로 유효한 UTF-8이
// 보장되지 않는다. nlohmann dump()의 strict 기본값은 그런 바이트에서 던지고,
// appendToSpill은 그 예외를 삼켜 false를 돌려줬다 -- 즉 "처음 본 실패"의
// 분석이 book에 영영 남지 않았다. 잘못된 바이트는 U+FFFD로 치환하고 항목은
// 반드시 남긴다. 바이트는 리터럴이 아니라 코드로 만든다(소스 인코딩이
// 리터럴을 조용히 "고칠" 수 있으므로).
TEST(BookStore, InvalidUtf8InEntryIsAppendedWithReplacementChar) {
    const auto dir = tempDirForTest();
    const auto spill = dir / "spill.jsonl";

    maro::BookEntry entry;
    entry.analysis = "before-";
    entry.analysis.push_back(static_cast<char>(0x80));  // lone continuation byte
    entry.analysis += "-after";
    entry.remedy = "clean remedy";

    ASSERT_TRUE(maro::BookStore::appendToSpill(spill, "h10", entry))
        << "an entry with invalid UTF-8 must still be written (bytes replaced)";

    const auto store = maro::BookStore::loadMerged(dir / "no_canonical.jsonl", spill);
    maro::BookEntry out;
    ASSERT_TRUE(store.query("h10", out));
    EXPECT_EQ(out.analysis, "before-\xEF\xBF\xBD-after")
        << "the lone 0x80 must become U+FFFD, not be passed through or truncate the text";
    EXPECT_EQ(out.remedy, "clean remedy");
}
