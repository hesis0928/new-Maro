#pragma once

#include <string>

namespace maro {

// 해법 동작의 종류. 원 스펙(2026-08-14 설계 §4.1)이 remedyAction을 "임의
// 코드가 아니다"라고 못박은 이유를 그대로 지킨다 -- 여기 없는 동작은 존재하지
// 않는다.
enum class RemedyActionKind {
    None,          // 기계적 해법이 없다. 분석까지만 제공한다.
    SelectNode,    // 씬을 편집하지 않는다. 사용자를 올바른 노드로 데려간다.
    SetAttribute,  // MDGModifier::newPlugValueInt로 적용한다 (현재 유일한
                   // 사용처인 controlMode가 정수 열거값이라 int만 다룬다).
    Disconnect,    // MDGModifier::disconnect(source, dest)로 적용한다.
};

// 실행 가능한 구조화된 해법 하나. DiagRecord에 실려 세션 동안만 산다 --
// book(해시별로 영속)에는 두지 않는다. 이유: book의 해시는 실패의 "자리와
// 종류"만 담을 뿐 이번 발생의 구체적인 노드 이름은 담지 않는다는 것이
// ErrorHash.h의 계약이고, 구체적인 노드 이름을 book에 캐시하면 Layer A
// 최종 리뷰의 Critical Finding C1(다른 발생의 텍스트를 이번 발생인 것처럼
// 재생)과 같은 부류의 버그가 재발한다. 그래서 이 값은 실패가 일어난 바로
// 그 순간, 그 자리에서 살아있는 씬을 보고 매번 새로 만든다 (플랜 서두
// "spec에서 의도적으로 벗어난 지점" 참고).
struct RemedyAction {
    RemedyActionKind kind = RemedyActionKind::None;

    // SelectNode, SetAttribute가 쓴다.
    std::string nodeName;
    // SetAttribute가 쓴다.
    std::string attributeName;
    double value = 0.0;
    // Disconnect가 쓴다. MSelectionList::add가 그대로 받을 수 있는
    // "node.attribute" 모양의 온전한 플러그 이름이다 (MPlug::name() 결과).
    std::string sourcePlug;
    std::string destPlug;
};

// 사람이 읽는 한 문장. book에 등록된 remedy 텍스트가 없을 때 패널이 대신
// 보여주는 설명이다 -- 구조화된 동작이 있는데도 패널에 아무 설명 없이 버튼만
// 뜨면 사용자가 무엇이 바뀌는지 모른 채 누르게 된다.
std::string describeRemedyAction(const RemedyAction& action);

}  // namespace maro
