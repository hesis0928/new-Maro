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
MObject MaroLidarNode::aVisualize;
MObject MaroLidarNode::aOffsetTranslateX;
MObject MaroLidarNode::aOffsetTranslateY;
MObject MaroLidarNode::aOffsetTranslateZ;
MObject MaroLidarNode::aOffsetRotateX;
MObject MaroLidarNode::aOffsetRotateY;
MObject MaroLidarNode::aOffsetRotateZ;

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

    // 기본값 false -- 명시적으로 켜야만 라이브 갱신이 켜진다. 씬을 열자마자
    // 모든 LiDAR가 매 틱 스캔을 시작하면 안 된다 (Task 5).
    //
    // 짧은 이름은 브리프가 제안한 "vis"가 아니라 "lvp"다: MPxLocatorNode가
    // 상속하는 렌더 통계 어트리뷰트 "primaryVisibility"가 이미 짧은 이름
    // "vis"를 쓰고 있어("vis"는 Maya의 흔한 관례상 "visibility" 계열에
    // 예약돼 있다), "vis"로 create()하면 짧은 이름 충돌로 addAttribute()가
    // 조용히 실패한다(반환값을 안 보면 알 수 없다) -- 결과로 만들어지는
    // 반쯤 등록된 MObject를 나중에 MPlug::asBool()로 읽으면
    // TdataBlockDG::attrMemAddr에서 액세스 위반이 난다(실측: 이 코드를
    // "vis"로 처음 넣었을 때 maya_lidar_publish가 collectLidarScans의 바로
    // 이 줄에서 mayapy를 죽였다). "lvp"는 이 노드 타입의 기존 177개
    // 상속+고유 어트리뷰트 어느 것과도 충돌하지 않는 것을 실측으로 확인했다.
    aVisualize = numFn.create("visualize", "lvp", MFnNumericData::kBoolean, false);
    numFn.setKeyable(true);
    addAttribute(aVisualize);

    // 마운트 지점(이 노드가 얹힌 트랜스폼)과 실제 센서 원점 사이의 로컬
    // 오프셋. 이 노드는 전용 트랜스폼 없이 대상 오브젝트의 트랜스폼에 직접
    // 얹히는 설계라(이전 태스크에서 검증된 결정, 범위 밖) 마운트 지점과
    // 센서가 정확히 일치하지 않는 실제 상황을 표현할 방법이 전혀 없었다 --
    // 이 6개 어트리뷰트가 그 간극을 메운다. MaroLidarScan.cpp가 이 값들로
    // 로컬 오프셋 행렬을 만들어 월드 행렬과 합성한다.
    //
    // rangeMin/rangeMax와 같은 이유로 kDouble(단순 실수)이지 kDistance가
    // 아니다 -- 이 값은 미터 단위이고, 레이캐스팅 코드가 그 자리에서 이미
    // 계산해 둔 mayaPerMeter로 직접 변환한다.
    //
    // 짧은 이름은 "vis"/"lvp" 사례(위 aVisualize 주석)를 교훈 삼아 추측이
    // 아니라 실측으로 골랐다: mayapy 프로브로 이 노드 타입의 (상속 포함)
    // 기존 178개 어트리뷰트 전체의 짧은 이름을 나열한 뒤, "otx"/"oty"/"otz"/
    // "orx"/"ory"/"orz" 중 어느 것도 그 목록에 없음을 확인했다. addAttribute()
    // 이후에도 attributeQuery(..., exists=True)가 6개 모두 True를 돌려주고
    // 어트리뷰트 총수가 정확히 178 -> 184(+6)로 늘어난 것으로 재확인했다
    // (tests/maya/test_lidar_node.py).
    aOffsetTranslateX = numFn.create("offsetTranslateX", "otx", MFnNumericData::kDouble, 0.0);
    numFn.setKeyable(true);
    addAttribute(aOffsetTranslateX);

    aOffsetTranslateY = numFn.create("offsetTranslateY", "oty", MFnNumericData::kDouble, 0.0);
    numFn.setKeyable(true);
    addAttribute(aOffsetTranslateY);

    aOffsetTranslateZ = numFn.create("offsetTranslateZ", "otz", MFnNumericData::kDouble, 0.0);
    numFn.setKeyable(true);
    addAttribute(aOffsetTranslateZ);

    aOffsetRotateX = angFn.create("offsetRotateX", "orx", MFnUnitAttribute::kAngle, 0.0);
    angFn.setKeyable(true);
    addAttribute(aOffsetRotateX);

    aOffsetRotateY = angFn.create("offsetRotateY", "ory", MFnUnitAttribute::kAngle, 0.0);
    angFn.setKeyable(true);
    addAttribute(aOffsetRotateY);

    aOffsetRotateZ = angFn.create("offsetRotateZ", "orz", MFnUnitAttribute::kAngle, 0.0);
    angFn.setKeyable(true);
    addAttribute(aOffsetRotateZ);

    return MS::kSuccess;
}

}  // namespace maro
