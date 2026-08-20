#include "MaroLidarNode.h"

#include <maya/MFnMessageAttribute.h>
#include <maya/MFnNumericAttribute.h>
#include <maya/MFnStringData.h>
#include <maya/MFnTypedAttribute.h>
#include <maya/MFnUnitAttribute.h>

namespace maro {

MTypeId MaroLidarNode::id(0x00135106);

MObject MaroLidarNode::aVerticalSamples;
MObject MaroLidarNode::aVerticalMinAngle;
MObject MaroLidarNode::aVerticalMaxAngle;
MObject MaroLidarNode::aHorizontalSamples;
MObject MaroLidarNode::aHorizontalMinAngle;
MObject MaroLidarNode::aHorizontalMaxAngle;
MObject MaroLidarNode::aRangeMin;
MObject MaroLidarNode::aRangeMax;
MObject MaroLidarNode::aUpdateRate;
MObject MaroLidarNode::aFrameId;
MObject MaroLidarNode::aTargetMeshes;
MObject MaroLidarNode::aEnabled;

void* MaroLidarNode::creator() { return new MaroLidarNode(); }

MStatus MaroLidarNode::initialize() {
    MFnNumericAttribute numFn;
    MFnUnitAttribute angFn;
    MFnTypedAttribute typedFn;
    MFnMessageAttribute msgFn;
    MFnStringData stringDataFn;

    // setMin(1): 이 두 개의 곱이 곧 한 틱에 Maya 메인 스레드에서 동기로
    // 쏘는 레이 개수다 (MaroPump::collectLidarScans). 0이나 음수는
    // computeRayDirections가 빈 배열로 걸러내지만, 어트리뷰트 에디터에서
    // 아예 못 넣게 막는 쪽이 낫다 -- 상한은 여기서 걸지 않고
    // collectLidarScans가 곱으로 판정한다(둘 다 합법적인 값인데 곱만
    // 터무니없는 경우가 실제 위험이라, 한쪽만 보는 setMax로는 못 막는다).
    aVerticalSamples = numFn.create("verticalSamples", "vts", MFnNumericData::kInt, 4);
    numFn.setKeyable(true);
    numFn.setMin(1);
    addAttribute(aVerticalSamples);

    aVerticalMinAngle = angFn.create("verticalMinAngle", "vmn", MFnUnitAttribute::kAngle, -0.1);
    angFn.setKeyable(true);
    addAttribute(aVerticalMinAngle);

    aVerticalMaxAngle = angFn.create("verticalMaxAngle", "vmx", MFnUnitAttribute::kAngle, 0.1);
    angFn.setKeyable(true);
    addAttribute(aVerticalMaxAngle);

    aHorizontalSamples = numFn.create("horizontalSamples", "hts", MFnNumericData::kInt, 36);
    numFn.setKeyable(true);
    numFn.setMin(1);   // aVerticalSamples 위 주석 참고.
    addAttribute(aHorizontalSamples);

    aHorizontalMinAngle =
        angFn.create("horizontalMinAngle", "hmn", MFnUnitAttribute::kAngle, -3.14159265358979);
    angFn.setKeyable(true);
    addAttribute(aHorizontalMinAngle);

    aHorizontalMaxAngle =
        angFn.create("horizontalMaxAngle", "hmx", MFnUnitAttribute::kAngle, 3.14159265358979);
    angFn.setKeyable(true);
    addAttribute(aHorizontalMaxAngle);

    aRangeMin = numFn.create("rangeMin", "rmn", MFnNumericData::kDouble, 0.1);
    numFn.setKeyable(true);
    addAttribute(aRangeMin);

    aRangeMax = numFn.create("rangeMax", "rmx", MFnNumericData::kDouble, 30.0);
    numFn.setKeyable(true);
    addAttribute(aRangeMax);

    aUpdateRate = numFn.create("updateRate", "upr", MFnNumericData::kDouble, 10.0);
    numFn.setKeyable(true);
    addAttribute(aUpdateRate);

    // 아직 발행 경로가 읽지 않는다 (최종 리뷰 Finding I4, 스펙 §7). 지금
    // PointCloud2의 header.frame_id는 항상 "world"다 -- 히트 좌표가 라이다
    // 로컬이 아니라 월드이기 때문이며, 그것만이 참인 라벨이다. 이 값은
    // 다음 레이어(히트를 로컬 프레임으로 옮기고 world->frameId TF를 함께
    // 발행하는 층)를 위해 예약돼 있다.
    MObject defaultFrameId = stringDataFn.create("lidar_link");
    aFrameId = typedFn.create("frameId", "fri", MFnData::kString, defaultFrameId);
    typedFn.setKeyable(false);
    addAttribute(aFrameId);

    aTargetMeshes = msgFn.create("targetMeshes", "tgm");
    msgFn.setArray(true);
    msgFn.setIndexMatters(true);
    addAttribute(aTargetMeshes);

    aEnabled = numFn.create("enabled", "enb", MFnNumericData::kBoolean, true);
    numFn.setKeyable(true);
    addAttribute(aEnabled);

    return MS::kSuccess;
}

}  // namespace maro
