#pragma once

namespace maro {

// 라디안 스케일에서 의미 있는 움직임은 절대 걸러지지 않고, 부동소수점
// 표현 오차로 생기는 노이즈만 제거하는 수준. 이 축 시스템은 현재 회전
// (라디안) 조인트만 다룬다 (MaroAxisNode::aOutValue가
// MFnUnitAttribute::kAngle, 내부 라디안).
constexpr double kUnchangedCommandEpsilon = 1e-9;

// 들어온 명령값(incoming)이 현재값(current)과 사실상 같아서 적용(및 그에
// 따른 dirty 전파)을 건너뛰어도 되는지 판단한다. Maya API에 의존하지
// 않는다 -- MaroCommandDeviceNode::applyToMatchingAxis()가 이 판단 결과로
// setDouble() 호출 여부만 가른다.
constexpr bool shouldSkipUnchangedCommand(double current, double incoming,
                                          double epsilon = kUnchangedCommandEpsilon) {
    const double delta = incoming - current;
    return (delta < 0 ? -delta : delta) < epsilon;
}

}  // namespace maro
