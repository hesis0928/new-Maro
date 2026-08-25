#include <gtest/gtest.h>

#include "CommandDeltaCheck.h"

TEST(CommandDeltaCheck, IdenticalValueIsSkipped) {
    EXPECT_TRUE(maro::shouldSkipUnchangedCommand(1.2, 1.2));
}

TEST(CommandDeltaCheck, DifferentValueIsNotSkipped) {
    EXPECT_FALSE(maro::shouldSkipUnchangedCommand(1.2, 1.5));
}

TEST(CommandDeltaCheck, JustOverEpsilonIsNotSkipped) {
    const double current = 1.2;
    const double incoming = current + maro::kUnchangedCommandEpsilon * 10.0;
    EXPECT_FALSE(maro::shouldSkipUnchangedCommand(current, incoming));
}

TEST(CommandDeltaCheck, JustUnderEpsilonIsSkipped) {
    const double current = 1.2;
    const double incoming = current + maro::kUnchangedCommandEpsilon / 10.0;
    EXPECT_TRUE(maro::shouldSkipUnchangedCommand(current, incoming));
}

TEST(CommandDeltaCheck, DirectionDoesNotMatter) {
    // 들어온 값이 현재값보다 작아도 같은 규칙이 적용된다(절댓값 비교).
    EXPECT_TRUE(maro::shouldSkipUnchangedCommand(1.2, 1.2 - maro::kUnchangedCommandEpsilon / 10.0));
    EXPECT_FALSE(maro::shouldSkipUnchangedCommand(1.2, 1.2 - maro::kUnchangedCommandEpsilon * 10.0));
}

// --- 리뷰 Finding C-2a: 인바운드 명령의 단위 정규화 ---

TEST(InboundCommandUnits, AngularAxisPassesRadiansThroughUntouched) {
    // revolute 관절의 JointState.position은 이미 라디안이다 -- 손대면 안 된다.
    EXPECT_DOUBLE_EQ(maro::normalizeInboundCommand(1.2, /*driveIsLinear=*/false), 1.2);
    EXPECT_DOUBLE_EQ(maro::normalizeInboundCommand(-0.75, /*driveIsLinear=*/false), -0.75);
    EXPECT_DOUBLE_EQ(maro::normalizeInboundCommand(0.0, /*driveIsLinear=*/false), 0.0);
}

TEST(InboundCommandUnits, LinearAxisConvertsMetersToCentimeters) {
    // prismatic 관절의 JointState.position은 미터다. aRosCommand는 축의
    // 내부 단위(센티미터)를 나른다.
    EXPECT_DOUBLE_EQ(maro::normalizeInboundCommand(0.5, /*driveIsLinear=*/true), 50.0);
    EXPECT_DOUBLE_EQ(maro::normalizeInboundCommand(1.0, /*driveIsLinear=*/true), 100.0);
    EXPECT_DOUBLE_EQ(maro::normalizeInboundCommand(-0.25, /*driveIsLinear=*/true), -25.0);
    EXPECT_DOUBLE_EQ(maro::normalizeInboundCommand(0.0, /*driveIsLinear=*/true), 0.0);
}

TEST(InboundCommandUnits, DeltaCheckComparesConvertedValues) {
    // 변환은 델타 비교보다 먼저 와야 한다. 축에 이미 50cm가 들어 있는데
    // 0.5m가 또 들어오면 "변경 없음"으로 걸러져야 한다 -- 변환 전 값
    // (0.5)으로 비교하면 50과 0.5를 견주게 돼 잘못 적용된다.
    const double current = 50.0;  // 센티미터
    const double incoming = 0.5;  // 미터
    EXPECT_FALSE(maro::shouldSkipUnchangedCommand(current, incoming));
    EXPECT_TRUE(maro::shouldSkipUnchangedCommand(
        current, maro::normalizeInboundCommand(incoming, /*driveIsLinear=*/true)));
}

TEST(CommandDeltaCheck, CustomEpsilonOverridesDefault) {
    // 기본 epsilon으로는 "변경 없음"으로 잡힐 차이도, 더 엄격한 epsilon을
    // 넘기면 "변경"으로 잡혀야 한다 -- 세 번째 매개변수가 실제로 쓰이는지 확인.
    const double current = 1.2;
    const double incoming = current + maro::kUnchangedCommandEpsilon / 10.0;
    EXPECT_TRUE(maro::shouldSkipUnchangedCommand(current, incoming));
    EXPECT_FALSE(maro::shouldSkipUnchangedCommand(current, incoming, /*epsilon=*/1e-15));
}
