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

TEST(CommandDeltaCheck, CustomEpsilonOverridesDefault) {
    // 기본 epsilon으로는 "변경 없음"으로 잡힐 차이도, 더 엄격한 epsilon을
    // 넘기면 "변경"으로 잡혀야 한다 -- 세 번째 매개변수가 실제로 쓰이는지 확인.
    const double current = 1.2;
    const double incoming = current + maro::kUnchangedCommandEpsilon / 10.0;
    EXPECT_TRUE(maro::shouldSkipUnchangedCommand(current, incoming));
    EXPECT_FALSE(maro::shouldSkipUnchangedCommand(current, incoming, /*epsilon=*/1e-15));
}
