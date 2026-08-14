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
