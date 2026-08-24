#pragma once

#include <maya/MPxCommand.h>
#include <maya/MSyntax.h>

namespace maro {

// Maya(Y-up) 위치+쿼터니언을 ROS(Z-up, 미터) 위치+쿼터니언으로 변환한다.
// maro_transform::mayaToRosPosition/mayaToRosRotation을 그대로 감싸는
// 순수 계산 -- 실제 ROS 발행 파이프라인(MaroRosRuntime.cpp)과 같은 소스를
// 쓴다. DG를 편집하지 않으므로 undo 불필요.
class MaroMayaToRosCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
};

// python/maroRosProxy.py의 idle 콜백이 매 틱 확인하는 "동기화 대상 고정"
// 상태를 설정/해제한다. 상태는 optionVar 하나(maroRosProxyPinnedTarget)에
// 저장한다 -- Python 쪽이 매 틱 optionVar를 읽기만 하면 되므로 C++/Python
// 사이에 별도 통신 채널이 필요 없다.
class MaroSetRosProxyTargetCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
};

}  // namespace maro
