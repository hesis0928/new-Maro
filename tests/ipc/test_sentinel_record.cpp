#include <gtest/gtest.h>

#include <filesystem>

#include "maro_ipc/SentinelRecord.h"

namespace {

std::filesystem::path freshDir(const std::string& name) {
    const std::filesystem::path dir =
        std::filesystem::temp_directory_path() / ("maro_sentinel_record_test_" + name);
    std::error_code ec;
    std::filesystem::remove_all(dir, ec);
    std::filesystem::create_directories(dir, ec);
    return dir;
}

TEST(SentinelRecord, WriteThenReadRoundTrips) {
    const auto path = freshDir("roundtrip") / "record.json";
    maro::ipc::SentinelRecord record;
    record.sentinelPid = 111;
    record.ownerMayaPid = 222;
    record.startTimeMs = 1700000000000ULL;

    ASSERT_TRUE(maro::ipc::writeSentinelRecord(path, record));

    maro::ipc::SentinelRecord read;
    ASSERT_TRUE(maro::ipc::readSentinelRecord(path, read));
    EXPECT_EQ(read.sentinelPid, 111u);
    EXPECT_EQ(read.ownerMayaPid, 222u);
    EXPECT_EQ(read.startTimeMs, 1700000000000ULL);
    EXPECT_FALSE(read.lastSessionEndedCleanly.has_value());
}

TEST(SentinelRecord, CleanlyFlagRoundTrips) {
    const auto path = freshDir("clean_flag") / "record.json";
    maro::ipc::SentinelRecord record;
    record.sentinelPid = 1;
    record.ownerMayaPid = 2;
    record.startTimeMs = 1;
    record.lastSessionEndedCleanly = false;

    ASSERT_TRUE(maro::ipc::writeSentinelRecord(path, record));
    maro::ipc::SentinelRecord read;
    ASSERT_TRUE(maro::ipc::readSentinelRecord(path, read));
    ASSERT_TRUE(read.lastSessionEndedCleanly.has_value());
    EXPECT_FALSE(*read.lastSessionEndedCleanly);
}

TEST(SentinelRecord, ReadMissingFileFailsCleanly) {
    maro::ipc::SentinelRecord out;
    EXPECT_FALSE(maro::ipc::readSentinelRecord(
        freshDir("missing") / "nope.json", out));
}

TEST(SentinelRecord, WriteCreatesParentDirectory) {
    const auto dir = freshDir("parent_create");
    const auto path = dir / "nested" / "record.json";
    maro::ipc::SentinelRecord record;
    record.sentinelPid = 1;
    record.ownerMayaPid = 2;
    record.startTimeMs = 3;
    EXPECT_TRUE(maro::ipc::writeSentinelRecord(path, record));
    EXPECT_TRUE(std::filesystem::exists(path));
}

}  // namespace
