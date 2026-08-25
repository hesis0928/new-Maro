#include "MaroAxisNode.h"

#include <algorithm>
#include <cmath>

#include <maya/MAngle.h>
#include <maya/MArrayDataHandle.h>
#include <maya/MDataBlock.h>
#include <maya/MDataHandle.h>
#include <maya/MDistance.h>
#include <maya/MFnCompoundAttribute.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MFnEnumAttribute.h>
#include <maya/MFnMatrixAttribute.h>
#include <maya/MFnMessageAttribute.h>
#include <maya/MFnNumericAttribute.h>
#include <maya/MFnTypedAttribute.h>
#include <maya/MFnUnitAttribute.h>
#include <maya/MGlobal.h>
#include <maya/MMatrix.h>
#include <maya/MPlug.h>

#include "MaroDiag.h"

namespace maro {

namespace {

// 리뷰 Finding I3: compute()는 Maya 2026 기본 평가 관리자(Parallel
// Evaluation Manager) 아래에서 워커 스레드 위에 돌 수 있다(MaroDiag.h의
// 스레드 안전성 주석 참고). 그래서 여기서 DgContext를 조립할 때 어떤 필드가
// Maya API 호출을 필요로 하는지를 신중히 가른다:
//   - nodeType은 호출부가 이미 아는 컴파일 타임 상수(등록 이름 문자열)라
//     Maya를 전혀 부르지 않고 항상 채운다 -- 비용도, 위험도 없다.
//   - onfix::activeCommand()는 thread_local 벡터를 읽을 뿐 Maya API가
//     아니므로 이것도 항상 안전하다(test_diag_thread.py가 이미 워커
//     스레드에서 이 경로를 검증한다).
//   - 노드 "이름"(axisOrTarget)은 다르다 -- MFnDependencyNode(thisMObject())
//     로 실제 DG를 조회해야 나오는, 진짜 Maya API 호출이다. 이 파일의 다른
//     compute() 자매 노드들(MaroCapabilityNodes.cpp)과 정책을 통일한다:
//     isMainThread()가 안전을 보장할 때만 채우고, 워커로 판정되면 빈
//     문자열로 둔다. DgContext의 계약("필드가 비어 있으면 그 시점에 관여가
//     없었다는 뜻이지 에러가 아니다")과 맞는 정직한 "모른다"다 -- 이름을
//     아예 얻을 방법이 없는 스레드에서 억지로 채우려다 워커 스레드에서
//     금지된 Maya 호출을 내는 것보다 낫다.
DgContext computeContext(const MPxNode& node, const char* nodeType) {
    DgContext ctx;
    ctx.nodeType = nodeType;
    ctx.activeCommand = onfix::activeCommand();
    if (isMainThread()) {
        // 이 함수 자체가 compute()의 catch 블록 안에서 -- 즉 이미 예외가 한
        // 번 난 상황에서 -- 불린다. MFnDependencyNode 조회가 여기서 또
        // 실패/예외를 내면 그 예외는 compute()를 감싸는 바깥 try가 없으므로
        // 곧장 Maya 콜백 경계를 넘는다 -- 그래서 반드시 그 자체를 한 번 더
        // 감싼다: 실패하면 이름 없이(빈 문자열로) 진행한다.
        try {
            MFnDependencyNode fn(node.thisMObject());
            ctx.axisOrTarget = fn.name().asChar();
        } catch (...) {
            ctx.nameUnavailable = true;
        }
    } else {
        // 워커 스레드다. Maya에 이름을 물을 수 없다 -- 빈칸이지만 "관여
        // 없음"이 아니라 "못 채움"이다.
        ctx.nameUnavailable = true;
    }
    return ctx;
}

}  // namespace

MTypeId MaroAxisNode::id(0x00135100);

MObject MaroAxisNode::aTargetObject;
MObject MaroAxisNode::aParentAxis;
MObject MaroAxisNode::aCapabilityIn;
MObject MaroAxisNode::aCapType;
MObject MaroAxisNode::aCapValue;
MObject MaroAxisNode::aCapEnable;
MObject MaroAxisNode::aCapMin;
MObject MaroAxisNode::aCapMax;
MObject MaroAxisNode::aJointName;
MObject MaroAxisNode::aConventionAxis;
MObject MaroAxisNode::aConventionInvert;
MObject MaroAxisNode::aDisplayName;
MObject MaroAxisNode::aDisplayColor;
MObject MaroAxisNode::aControlMode;
MObject MaroAxisNode::aRosCommand;
MObject MaroAxisNode::aEnabled;
MObject MaroAxisNode::aOutValue;
MObject MaroAxisNode::aOutTransform;
MObject MaroAxisNode::aOutValueLinear;
MObject MaroAxisNode::aDriveIsLinear;

void* MaroAxisNode::creator() {
    return new MaroAxisNode();
}

MStatus MaroAxisNode::initialize() {
    MFnMessageAttribute msgFn;
    MFnNumericAttribute numFn;
    MFnTypedAttribute typFn;
    MFnEnumAttribute enumFn;
    MFnMatrixAttribute matFn;
    MFnUnitAttribute angFn;

    // 바인딩은 이름 문자열이 아니라 message 연결로 맺는다.
    // Maya가 rename/delete/undo를 자동 추적하므로 동기화가 깨지지 않는다.
    aTargetObject = msgFn.create("targetObject", "tgo");
    msgFn.setStorable(true);
    addAttribute(aTargetObject);

    aParentAxis = msgFn.create("parentAxis", "pax");
    msgFn.setStorable(true);
    addAttribute(aParentAxis);

    // 스택 입력은 데이터 복합 어트리뷰트다. message는 데이터를 나르지 않아
    // compute가 플러그를 직접 조회해야 하고, 그러면 DG 더티 전파를 우회해
    // 병렬 평가에서 값이 어긋난다. 능력 노드의 기여를 실제 데이터로 받는다.
    aCapType = numFn.create("capType", "cpt", MFnNumericData::kShort, 0);
    aCapValue = numFn.create("capValue", "cpv", MFnNumericData::kDouble, 0.0);
    aCapEnable = numFn.create("capEnable", "cpe", MFnNumericData::k3Short, 0);
    aCapMin = numFn.create("capMin", "cpn", MFnNumericData::k3Double, 0.0);
    aCapMax = numFn.create("capMax", "cpx", MFnNumericData::k3Double, 0.0);

    MFnCompoundAttribute cmpFn;
    aCapabilityIn = cmpFn.create("capabilityIn", "cpi");
    cmpFn.addChild(aCapType);
    cmpFn.addChild(aCapValue);
    cmpFn.addChild(aCapEnable);
    cmpFn.addChild(aCapMin);
    cmpFn.addChild(aCapMax);
    cmpFn.setStorable(true);
    cmpFn.setArray(true);
    cmpFn.setIndexMatters(true);   // 스택은 인덱스 순서대로 평가된다
    addAttribute(aCapabilityIn);

    aJointName = typFn.create("jointName", "jnm", MFnData::kString);
    typFn.setStorable(true);
    addAttribute(aJointName);

    aConventionAxis = enumFn.create("conventionAxis", "cva", 1);  // 기본 Y
    enumFn.addField("X", 0);
    enumFn.addField("Y", 1);
    enumFn.addField("Z", 2);
    enumFn.setStorable(true);
    enumFn.setKeyable(true);
    addAttribute(aConventionAxis);

    aConventionInvert = numFn.create("conventionInvert", "cvi",
                                     MFnNumericData::kBoolean, 0);
    numFn.setStorable(true);
    numFn.setKeyable(true);
    addAttribute(aConventionInvert);

    aDisplayName = typFn.create("displayName", "dpn", MFnData::kString);
    typFn.setStorable(true);
    addAttribute(aDisplayName);

    aDisplayColor = numFn.createColor("displayColor", "dpc");
    numFn.setStorable(true);
    addAttribute(aDisplayColor);

    aControlMode = enumFn.create("controlMode", "cmd", 0);  // 기본 Manual
    enumFn.addField("Manual", 0);
    enumFn.addField("ROS", 1);
    enumFn.setStorable(true);
    enumFn.setKeyable(true);
    addAttribute(aControlMode);

    // 펌프가 매 프레임 직접 쓰는 값이다. 사용자 구성이 아니므로 씬에 저장하지 않는다.
    aRosCommand = numFn.create("rosCommand", "rcm", MFnNumericData::kDouble, 0.0);
    numFn.setStorable(false);
    numFn.setKeyable(false);
    addAttribute(aRosCommand);

    aEnabled = numFn.create("enabled", "enb", MFnNumericData::kBoolean, 1);
    numFn.setStorable(true);
    numFn.setKeyable(true);
    addAttribute(aEnabled);

    // 네이티브 rotateX류 어트리뷰트로 바로 연결될 수 있는 값이므로 실제
    // 각도 단위로 선언한다. 평범한 double로 두면 그 연결에서 Maya가
    // 라디안 값을 UI 단위(도)로 오인해 잘못된 unitConversion 배율을
    // 끼워 넣는다 (실측: plainVal(1.0 rad 의도) -> rotateX 연결 시
    // conversionFactor 0.0174533로 1도로 둔갑).
    aOutValue = angFn.create("position", "otv", MFnUnitAttribute::kAngle, 0.0);
    angFn.setStorable(false);
    angFn.setWritable(false);
    addAttribute(aOutValue);

    aOutValueLinear = angFn.create("positionLinear", "otvl",
                                   MFnUnitAttribute::kDistance, 0.0);
    angFn.setStorable(false);
    angFn.setWritable(false);
    addAttribute(aOutValueLinear);

    aOutTransform = matFn.create("outTransform", "ott",
                                 MFnMatrixAttribute::kDouble);
    matFn.setStorable(false);
    matFn.setWritable(false);
    addAttribute(aOutTransform);

    aDriveIsLinear = numFn.create("driveIsLinear", "dil", MFnNumericData::kBoolean, false);
    numFn.setStorable(false);
    numFn.setWritable(false);
    addAttribute(aDriveIsLinear);

    // aConventionInvert는 여기서 attributeAffects에 넣지 않는다: compute()가
    // 실제로 읽지 않기 때문이다 (v1에는 반전 보정이 구현되어 있지 않다,
    // MaroAxisNode.h의 선언부 주석 참고). 안 읽는 소스를 영향권에 넣으면
    // 실제로는 아무 것도 안 바뀌는데 더티 전파만 유발해 재계산을 낭비한다.
    for (const MObject& src : {aConventionAxis, aEnabled,
                               aControlMode, aRosCommand}) {
        attributeAffects(src, aOutValue);
        attributeAffects(src, aOutValueLinear);
        attributeAffects(src, aOutTransform);
    }

    // [최종 리뷰 재검증에서 발견] aDriveIsLinear는 aEnabled와
    // aCapabilityIn(1차 구동 타입)에만 의존한다 -- compute()를 보면
    // isLinearDrive는 스택에서 찾은 1차 구동 capType으로만 정해지고,
    // aConventionAxis/aControlMode/aRosCommand는 "어떤 값을 낼지"에만
    // 관여하지 "어느 계열이 구동하는지"에는 영향이 없다. 안 읽는 소스를
    // 영향권에 넣지 않는다는 원칙은 위 aConventionInvert 주석과 같다.
    //
    // 이게 스타일 문제가 아니라 진짜 버그였다: aRosCommand를 여기 넣어
    // 두면, MaroCommandDeviceNode::applyToMatchingAxis()가 (같은
    // compute() 호출 경로 안에서) aDriveIsLinear를 읽은 직후 그 축의
    // aRosCommand에 값을 쓰는 순간 이 노드 자신을 다시 dirty로 만드는
    // pull-then-dirty 순환이 생긴다 -- 델타체크가 막으려는 바로 그
    // 불필요한 재평가를, 델타체크 판정 자체보다 앞서 매번 강제로
    // 일으키는 꼴이다.
    attributeAffects(aEnabled, aDriveIsLinear);
    attributeAffects(aCapabilityIn, aOutValue);
    attributeAffects(aCapabilityIn, aOutValueLinear);
    attributeAffects(aCapabilityIn, aDriveIsLinear);
    attributeAffects(aCapabilityIn, aOutTransform);

    return MS::kSuccess;
}

MStatus MaroAxisNode::compute(const MPlug& plug, MDataBlock& data) {
    try {
        if (plug != aOutValue && plug != aOutValueLinear &&
            plug != aOutTransform && plug != aDriveIsLinear) {
            return MS::kUnknownParameter;
        }

        const bool enabled = data.inputValue(aEnabled).asBool();

        double value = 0.0;
        bool isLinearDrive = false;
        // §3 상호배타 규칙: 커맨드 레벨(Task 6의 maroAddCapability/
        // maroConnectCapability)이 정상적으로는 1차 구동 타입(rotation/
        // translation/coupling)을 축 하나에 하나만 허용하지만, DG 자체는
        // 스크립트로 그 규칙을 우회한 씬도 방어적으로 처리해야 한다 --
        // 먼저 나온(인덱스가 낮은) 1차 구동 타입이 이기고 나머지는 무시한다.
        bool primaryDriverSeen = false;

        if (enabled) {
            // 스택은 capabilityIn 인덱스 순서대로 평가한다.
            const short axisIndex = data.inputValue(aConventionAxis).asShort();
            const unsigned int component =
                (axisIndex == 0) ? 0u : ((axisIndex == 2) ? 2u : 1u);

            // 모드가 기준값의 출처를 정한다. 리밋은 어느 쪽이든 똑같이 적용된다.
            const bool rosDriven = data.inputValue(aControlMode).asShort() == 1;

            MArrayDataHandle stack = data.inputArrayValue(aCapabilityIn);

            for (unsigned int i = 0; i < stack.elementCount(); ++i) {
                stack.jumpToArrayElement(i);
                MDataHandle element = stack.inputValue();

                const short capType = element.child(aCapType).asShort();

                if (capType == 0 || capType == 4 || capType == 6 || capType == 7) {
                    // 1차 구동 타입: rotation(0)/translation(4)/
                    // coupling-각도(6)/coupling-선형(7).
                    if (!primaryDriverSeen) {
                        value = rosDriven ? data.inputValue(aRosCommand).asDouble()
                                          : element.child(aCapValue).asDouble();
                        isLinearDrive = (capType == 4 || capType == 7);
                        primaryDriverSeen = true;
                    }
                } else if (capType == 1 || capType == 5) {
                    // limit(1, 각도 계열) / translationLimit(5, 직선 계열):
                    // value가 어느 쪽 1차 구동 타입에서 왔든 클램프 수식은
                    // 동일하므로 한 분기로 처리한다.
                    const short3& enable = element.child(aCapEnable).asShort3();
                    if (enable[component] != 0) {
                        const double3& lo = element.child(aCapMin).asDouble3();
                        const double3& hi = element.child(aCapMax).asDouble3();
                        value = std::clamp(value,
                                           std::min(lo[component], hi[component]),
                                           std::max(lo[component], hi[component]));
                    }
                }
                // 센서 노드(capType 2, 3)는 구동값에 기여하지 않는다. S4에서 소비한다.
            }
        }

        // NaN/inf를 Maya에 흘리지 않는다.
        if (!std::isfinite(value)) {
            maro::BoadMaro::warn(
                "Maro: axis produced a non-finite value; holding zero.");
            value = 0.0;
        }

        // isLinearDrive가 아닌 쪽 출력은 0으로 clean 처리한다 -- §3의
        // 상호배타 규칙 덕분에 항상 둘 중 하나만 의미 있는 값을 가진다.
        MDataHandle outVal = data.outputValue(aOutValue);
        MDataHandle outValLinear = data.outputValue(aOutValueLinear);
        if (isLinearDrive) {
            outVal.setMAngle(MAngle(0.0, MAngle::kRadians));
            outValLinear.setMDistance(MDistance(value, MDistance::kCentimeters));
        } else {
            outVal.setMAngle(MAngle(value, MAngle::kRadians));
            outValLinear.setMDistance(MDistance(0.0, MDistance::kCentimeters));
        }
        outVal.setClean();
        outValLinear.setClean();

        MDataHandle outDriveLinear = data.outputValue(aDriveIsLinear);
        outDriveLinear.setBool(isLinearDrive);
        outDriveLinear.setClean();

        MDataHandle outXf = data.outputValue(aOutTransform);
        outXf.setMMatrix(MMatrix::identity);
        outXf.setClean();

        return MS::kSuccess;
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroAxisNode.compute.Exception",
                              MString("Maro: maroAxis compute failed: ") + e.what(),
                              computeContext(*this, "maroAxis"));
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroAxisNode.compute.UnknownException",
                              "Maro: maroAxis compute failed with unknown error.",
                              computeContext(*this, "maroAxis"));
        return MS::kFailure;
    }
}

}  // namespace maro
