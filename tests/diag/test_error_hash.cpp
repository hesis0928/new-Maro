#include <gtest/gtest.h>

#include "maro_diag/DiagRecord.h"
#include "maro_diag/ErrorHash.h"

TEST(ErrorHash, PinnedValueForKnownTag) {
    // 실제 FNV-1a-64 구현으로 미리 계산해 둔 값이다(오프셋 0xcbf29ce484222325,
    // 프라임 0x100000001b3, UTF-8 바이트 단위). 이 상수가 바뀌면 book의 기존
    // 항목이 전부 조회되지 않게 되므로, 해시 알고리즘을 바꿀 때는 반드시
    // book 마이그레이션과 함께 다뤄야 한다.
    EXPECT_EQ(maro::hashError("MaroBindAxisCommand.TargetNotTransform"),
              "068895013575db45");
}

TEST(ErrorHash, EmptyTagIsWellDefined) {
    EXPECT_EQ(maro::hashError(""), "cbf29ce484222325");
}

TEST(ErrorHash, DifferentTagsProduceDifferentHashes) {
    const std::string a = maro::hashError("MaroBindAxisCommand.TargetNotTransform");
    const std::string b = maro::hashError("MaroBindAxisCommand.NotMaroAxisNode");
    EXPECT_NE(a, b);
}

TEST(ErrorHash, SameTagIsStableAcrossCalls) {
    // "세션마다 다르지 않다"를 프로세스 안에서 흉내낸다: 같은 태그를 두 번
    // 독립적으로 호출해도 같은 값이 나와야 한다. 포인터나 시각이 섞여
    // 들어갔다면 여기서 흔들렸을 것이다. hashError는 문자열 하나만 받는
    // 시그니처라 애초에 그런 값을 넣을 자리가 없다.
    const std::string tag = "MaroBindAxisCommand.TargetNotTransform";
    EXPECT_EQ(maro::hashError(tag), maro::hashError(tag));
}

TEST(DiagRecordTest, DefaultsAreEmpty) {
    maro::DiagRecord rec;
    EXPECT_EQ(rec.severity, maro::DiagSeverity::Info);
    EXPECT_TRUE(rec.message.empty());
    EXPECT_TRUE(rec.errorHash.empty());
    EXPECT_TRUE(rec.context.nodeType.empty());
    EXPECT_FALSE(rec.servedFromBook);
}
