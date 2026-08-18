#include <gtest/gtest.h>

#include "maro_diag/RemedyAction.h"

namespace {

TEST(RemedyAction, NoneKindDescribesAsEmpty) {
    maro::RemedyAction action;
    EXPECT_EQ(action.kind, maro::RemedyActionKind::None);
    EXPECT_EQ(maro::describeRemedyAction(action), "");
}

TEST(RemedyAction, SelectNodeNamesTheNode) {
    maro::RemedyAction action;
    action.kind = maro::RemedyActionKind::SelectNode;
    action.nodeName = "axisA";
    EXPECT_EQ(maro::describeRemedyAction(action), "'axisA' 노드를 선택합니다.");
}

TEST(RemedyAction, SetAttributeNamesNodeAttributeAndValue) {
    maro::RemedyAction action;
    action.kind = maro::RemedyActionKind::SetAttribute;
    action.nodeName = "axisA";
    action.attributeName = "controlMode";
    action.value = 0.0;
    EXPECT_EQ(maro::describeRemedyAction(action),
              "'axisA'.controlMode 값을 0(으)로 설정합니다.");
}

TEST(RemedyAction, DisconnectNamesBothPlugs) {
    maro::RemedyAction action;
    action.kind = maro::RemedyActionKind::Disconnect;
    action.sourcePlug = "cubeA.message";
    action.destPlug = "axisA.targetObject";
    EXPECT_EQ(maro::describeRemedyAction(action),
              "'cubeA.message' -> 'axisA.targetObject' 연결을 끊습니다.");
}

// 정수처럼 보이는 값이 소수점 없이 나오는지 -- 값 부분만 확인한다. 문자열
// 전체에서 '.'이 없는지를 보면 안 된다: "'n'.a" 자체가 노드.어트리뷰트
// 구분자로 마침표를 쓰므로 그 단언은 항상 거짓이 된다 (값과 무관하게).
TEST(RemedyAction, SetAttributeValueHasNoDecimalPoint) {
    maro::RemedyAction action;
    action.kind = maro::RemedyActionKind::SetAttribute;
    action.nodeName = "n";
    action.attributeName = "a";
    action.value = 1.0;
    EXPECT_NE(maro::describeRemedyAction(action).find("값을 1(으)로"), std::string::npos);
}

}  // namespace
