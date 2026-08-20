#include <gtest/gtest.h>

#include "maro_ipc/Naming.h"

namespace {

TEST(Naming, PipeNameEmbedsPid) {
    EXPECT_EQ(maro::ipc::pipeName(1234), "\\\\.\\pipe\\maro_sentinel_1234");
}

TEST(Naming, MutexNameEmbedsPid) {
    EXPECT_EQ(maro::ipc::mutexName(1234), "Global\\maro_sentinel_mutex_1234");
}

TEST(Naming, KillEventNameEmbedsPid) {
    EXPECT_EQ(maro::ipc::killEventName(1234), "Global\\maro_sentinel_kill_1234");
}

TEST(Naming, RecordFilePathEmbedsPid) {
    const auto path = maro::ipc::recordFilePath("C:/some/book/dir", 1234);
    EXPECT_EQ(path.filename().string(), "maro_sentinel.1234.json");
}

// 서로 다른 PID는 서로 다른 이름을 낸다 -- 이 플랜의 핵심 불변식.
TEST(Naming, DifferentPidsGiveDifferentNames) {
    EXPECT_NE(maro::ipc::pipeName(1), maro::ipc::pipeName(2));
    EXPECT_NE(maro::ipc::mutexName(1), maro::ipc::mutexName(2));
    EXPECT_NE(maro::ipc::killEventName(1), maro::ipc::killEventName(2));
    EXPECT_NE(maro::ipc::recordFilePath("C:/dir", 1),
              maro::ipc::recordFilePath("C:/dir", 2));
}

}  // namespace
