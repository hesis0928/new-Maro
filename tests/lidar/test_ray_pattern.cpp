#include <cmath>

#include <gtest/gtest.h>

#include "maro_lidar/RayPattern.h"

namespace {
constexpr double kPi = 3.14159265358979323846;
constexpr double kEps = 1e-9;

double length(const maro::Vec3& v) {
    return std::sqrt(v.x * v.x + v.y * v.y + v.z * v.z);
}
}  // namespace

TEST(RayPattern, ReturnsExactlyVerticalTimesHorizontalCount) {
    const auto rays = maro::lidar::computeRayDirections(
        4, -0.1, 0.1, 8, -kPi, kPi);
    EXPECT_EQ(rays.size(), 4u * 8u);
}

TEST(RayPattern, EveryDirectionIsUnitLength) {
    const auto rays = maro::lidar::computeRayDirections(
        4, -0.2, 0.2, 8, -kPi, kPi);
    for (const auto& r : rays) {
        EXPECT_NEAR(length(r), 1.0, kEps);
    }
}

TEST(RayPattern, ZeroAngleZeroChannelPointsLocalForward) {
    // 채널 1개(수직각 0 고정), 수평 1개(수평각 0 고정) -- 정의상 로컬 +Z.
    const auto rays = maro::lidar::computeRayDirections(1, 0.0, 0.0, 1, 0.0, 0.0);
    ASSERT_EQ(rays.size(), 1u);
    EXPECT_NEAR(rays[0].x, 0.0, kEps);
    EXPECT_NEAR(rays[0].y, 0.0, kEps);
    EXPECT_NEAR(rays[0].z, 1.0, kEps);
}

TEST(RayPattern, PositiveVerticalAngleTiltsTowardLocalUp) {
    const auto rays = maro::lidar::computeRayDirections(1, kPi / 4.0, kPi / 4.0, 1, 0.0, 0.0);
    ASSERT_EQ(rays.size(), 1u);
    EXPECT_GT(rays[0].y, 0.0);
}

TEST(RayPattern, EndpointsSpanTheFullRequestedRange) {
    // 4개 샘플, [-1, 1] 구간이면 첫/마지막 값이 정확히 -1과 1이어야 한다
    // (LaserScan.msg 관례: 양 끝값 포함, 샘플수-1로 나눔).
    const auto rays = maro::lidar::computeRayDirections(1, 0.0, 0.0, 4, -1.0, 1.0);
    ASSERT_EQ(rays.size(), 4u);
    EXPECT_NEAR(rays[0].x, std::sin(-1.0), kEps);
    EXPECT_NEAR(rays[3].x, std::sin(1.0), kEps);
}

TEST(RayPattern, SingleSampleDoesNotDivideByZero) {
    const auto rays = maro::lidar::computeRayDirections(1, 0.3, 0.3, 1, 0.5, 0.5);
    ASSERT_EQ(rays.size(), 1u);
    EXPECT_TRUE(std::isfinite(rays[0].x));
    EXPECT_TRUE(std::isfinite(rays[0].y));
    EXPECT_TRUE(std::isfinite(rays[0].z));
}
