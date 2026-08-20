#include <cstdint>
#include <vector>

#include <gtest/gtest.h>

#include "maro_lidar/ScanEngine.h"

namespace {

// XY 평면에 놓인 한 변 2인 정사각형(원점이 중심), 삼각형 2개.
// z=0 평면, x/y가 [-1, 1] 범위를 덮는다.
std::vector<float> squareVertices() {
    return {
        -1.0f, -1.0f, 0.0f,
         1.0f, -1.0f, 0.0f,
         1.0f,  1.0f, 0.0f,
        -1.0f,  1.0f, 0.0f,
    };
}

std::vector<std::uint32_t> squareIndices() {
    return {0, 1, 2, 0, 2, 3};
}

}  // namespace

TEST(ScanEngine, RayStraightDownHitsTheSquare) {
    maro::lidar::ScanEngine engine;
    ASSERT_TRUE(engine.setMesh(squareVertices(), squareIndices()));

    // z=+5에서 -Z 방향으로 쏘면 z=0의 사각형과 (0,0,0)에서 만나야 한다.
    const auto hit = engine.castRay(maro::Vec3{0.0, 0.0, 5.0}, maro::Vec3{0.0, 0.0, -1.0},
                                     0.0, 100.0);
    ASSERT_TRUE(hit.hit);
    EXPECT_NEAR(hit.position.x, 0.0, 1e-4);
    EXPECT_NEAR(hit.position.y, 0.0, 1e-4);
    EXPECT_NEAR(hit.position.z, 0.0, 1e-4);
}

TEST(ScanEngine, RayMissingTheSquareReportsNoHit) {
    maro::lidar::ScanEngine engine;
    ASSERT_TRUE(engine.setMesh(squareVertices(), squareIndices()));

    // (10,10,5)에서 -Z로 쏘면 사각형([-1,1]x[-1,1])을 벗어난다.
    const auto hit = engine.castRay(maro::Vec3{10.0, 10.0, 5.0}, maro::Vec3{0.0, 0.0, -1.0},
                                     0.0, 100.0);
    EXPECT_FALSE(hit.hit);
}

TEST(ScanEngine, HitBeyondRangeMaxReportsNoHit) {
    maro::lidar::ScanEngine engine;
    ASSERT_TRUE(engine.setMesh(squareVertices(), squareIndices()));

    // 사각형은 원점에서 z=0에 있고 원점은 z=5 -- 거리 5인데 rangeMax를 1로 제한한다.
    const auto hit = engine.castRay(maro::Vec3{0.0, 0.0, 5.0}, maro::Vec3{0.0, 0.0, -1.0},
                                     0.0, 1.0);
    EXPECT_FALSE(hit.hit);
}

TEST(ScanEngine, HitBeforeRangeMinReportsNoHit) {
    maro::lidar::ScanEngine engine;
    ASSERT_TRUE(engine.setMesh(squareVertices(), squareIndices()));

    // rangeMin을 10으로 두면 거리 5인 충돌은 무시돼야 한다.
    const auto hit = engine.castRay(maro::Vec3{0.0, 0.0, 5.0}, maro::Vec3{0.0, 0.0, -1.0},
                                     10.0, 100.0);
    EXPECT_FALSE(hit.hit);
}

TEST(ScanEngine, SetMeshCanBeCalledAgainToReplaceGeometry) {
    maro::lidar::ScanEngine engine;
    ASSERT_TRUE(engine.setMesh(squareVertices(), squareIndices()));
    ASSERT_TRUE(engine.setMesh(squareVertices(), squareIndices()));  // 두 번째 호출도 성공해야 한다.

    const auto hit = engine.castRay(maro::Vec3{0.0, 0.0, 5.0}, maro::Vec3{0.0, 0.0, -1.0},
                                     0.0, 100.0);
    EXPECT_TRUE(hit.hit);
}
