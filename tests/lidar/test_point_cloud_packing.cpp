#include <cstring>

#include <gtest/gtest.h>

#include "maro_lidar/PointCloudPacking.h"

TEST(PointCloudPacking, PointStepIsSixteenBytes) {
    const auto packed = maro::lidar::packPointCloud({}, {});
    EXPECT_EQ(packed.pointStep, 16u);
}

TEST(PointCloudPacking, EmptyInputProducesZeroWidthAndEmptyData) {
    const auto packed = maro::lidar::packPointCloud({}, {});
    EXPECT_EQ(packed.width, 0u);
    EXPECT_TRUE(packed.data.empty());
}

TEST(PointCloudPacking, WidthMatchesPointCount) {
    const std::vector<maro::Vec3> points = {
        maro::Vec3{1.0, 2.0, 3.0},
        maro::Vec3{4.0, 5.0, 6.0},
    };
    const auto packed = maro::lidar::packPointCloud(points, {0.5f, 0.75f});
    EXPECT_EQ(packed.width, 2u);
    EXPECT_EQ(packed.data.size(), 2u * 16u);
}

TEST(PointCloudPacking, XyzAndIntensityAreCorrectlyPackedAsLittleEndianFloat32) {
    const std::vector<maro::Vec3> points = {maro::Vec3{1.5, -2.5, 3.25}};
    const auto packed = maro::lidar::packPointCloud(points, {0.9f});
    ASSERT_EQ(packed.data.size(), 16u);

    float x = 0.0f, y = 0.0f, z = 0.0f, intensity = 0.0f;
    std::memcpy(&x, packed.data.data() + 0, sizeof(float));
    std::memcpy(&y, packed.data.data() + 4, sizeof(float));
    std::memcpy(&z, packed.data.data() + 8, sizeof(float));
    std::memcpy(&intensity, packed.data.data() + 12, sizeof(float));

    EXPECT_FLOAT_EQ(x, 1.5f);
    EXPECT_FLOAT_EQ(y, -2.5f);
    EXPECT_FLOAT_EQ(z, 3.25f);
    EXPECT_FLOAT_EQ(intensity, 0.9f);
}

TEST(PointCloudPacking, MissingIntensitiesAreFilledWithZero) {
    const std::vector<maro::Vec3> points = {maro::Vec3{1.0, 1.0, 1.0}};
    const auto packed = maro::lidar::packPointCloud(points, {});  // intensities 없음
    ASSERT_EQ(packed.data.size(), 16u);

    float intensity = -1.0f;
    std::memcpy(&intensity, packed.data.data() + 12, sizeof(float));
    EXPECT_FLOAT_EQ(intensity, 0.0f);
}
