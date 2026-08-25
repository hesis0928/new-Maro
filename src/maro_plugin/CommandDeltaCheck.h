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

// 리뷰 Finding C-2a: 인바운드 명령의 단위 정규화.
//
// sensor_msgs/JointState.position은 revolute 관절에서 라디안, prismatic
// 관절에서 "미터"다. 반면 MaroAxisNode::aRosCommand는 축의 "내부" 단위를
// 나르는 평범한 double이다 -- 회전축은 라디안(그대로 맞다), 직선축은
// 센티미터(capValue/aOutValueLinear와 같은 관례). 그래서 직선 구동
// 축에서만 m -> cm 배율이 걸린다.
//
// 이 판단을 Maya API에서 떼어 낸 순수 함수로 둔 이유는
// shouldSkipUnchangedCommand()와 같다: MPxThreadedDeviceNode의 인바운드
// 경로는 Maya의 유휴 이벤트 큐를 요구해서 배치 모드(mayapy)에서는
// 끝까지 돌려 볼 수 없다(tests/maya/test_contract.py의 SKIP 참고).
// 순수 함수로 빼 두면 그 환경 제약과 무관하게 단위 계약 자체는
// 헤드리스로 못 박을 수 있다.
constexpr double kMetersToCentimeters = 100.0;

constexpr double normalizeInboundCommand(double incoming, bool driveIsLinear) {
    return driveIsLinear ? incoming * kMetersToCentimeters : incoming;
}

}  // namespace maro
