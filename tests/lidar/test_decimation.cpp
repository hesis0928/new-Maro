#include "maro_lidar/Decimation.h"

#include <gtest/gtest.h>

using maro::Vec3;
using maro::lidar::decimateForPreview;

TEST(DecimationTest, ReturnsInputUnchangedWhenUnderCap) {
    std::vector<Vec3> points = {{1, 0, 0}, {2, 0, 0}, {3, 0, 0}};
    auto result = decimateForPreview(points, 10);
    EXPECT_EQ(result.size(), 3u);
}

TEST(DecimationTest, ClampsToExactlyMaxPoints) {
    std::vector<Vec3> points;
    for (int i = 0; i < 10000; ++i) points.push_back(Vec3{static_cast<double>(i), 0, 0});
    auto result = decimateForPreview(points, 100);
    EXPECT_EQ(result.size(), 100u);
}

TEST(DecimationTest, PreservesOrderAndCoversFullRange) {
    std::vector<Vec3> points;
    for (int i = 0; i < 1000; ++i) points.push_back(Vec3{static_cast<double>(i), 0, 0});
    auto result = decimateForPreview(points, 10);
    ASSERT_EQ(result.size(), 10u);
    for (std::size_t i = 1; i < result.size(); ++i) {
        EXPECT_LT(result[i - 1].x, result[i].x) << "decimated points must stay in original order";
    }
    // 첫 점은 원본의 시작 근방, 마지막 점은 끝 근방이어야 한다(전체 범위 커버).
    EXPECT_LT(result.front().x, 100.0);
    EXPECT_GT(result.back().x, 900.0);
}

TEST(DecimationTest, EmptyInputReturnsEmpty) {
    std::vector<Vec3> points;
    EXPECT_TRUE(decimateForPreview(points, 100).empty());
}
