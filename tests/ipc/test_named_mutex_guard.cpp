#include <gtest/gtest.h>

#include <thread>

#include "maro_ipc/NamedMutexGuard.h"

namespace {

// 같은 프로세스 안 두 스레드가 같은 이름으로 CreateMutex를 부르면 실제
// Windows API가 같은 커널 객체를 돌려준다 -- 별도 프로세스 없이도 진짜
// 뮤텍스 경합을 테스트할 수 있다.
TEST(NamedMutexGuard, SecondAcquireBlocksUntilFirstReleases) {
    const std::string name =
        "Local\\maro_test_mutex_" + std::to_string(::GetCurrentProcessId());

    maro::ipc::NamedMutexGuard first(name, 1000);
    ASSERT_TRUE(first.isAcquired());

    bool secondAcquiredWhileFirstHeld = false;
    std::thread t([&]() {
        // 첫 번째가 쥐고 있는 동안은 짧은 타임아웃 안에 못 얻어야 한다.
        maro::ipc::NamedMutexGuard second(name, 100);
        secondAcquiredWhileFirstHeld = second.isAcquired();
    });
    t.join();
    EXPECT_FALSE(secondAcquiredWhileFirstHeld);
}

TEST(NamedMutexGuard, AcquiresAfterPriorGuardIsDestroyed) {
    const std::string name =
        "Local\\maro_test_mutex2_" + std::to_string(::GetCurrentProcessId());

    {
        maro::ipc::NamedMutexGuard first(name, 1000);
        ASSERT_TRUE(first.isAcquired());
    }  // 여기서 해제된다.

    maro::ipc::NamedMutexGuard second(name, 1000);
    EXPECT_TRUE(second.isAcquired());
}

}  // namespace
