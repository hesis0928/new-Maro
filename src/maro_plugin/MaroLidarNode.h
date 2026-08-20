#pragma once

#include <maya/MObject.h>
#include <maya/MPxLocatorNode.h>
#include <maya/MStatus.h>
#include <maya/MTypeId.h>

namespace maro {

// LiDAR 센서 하나의 단일 진실 원천. maroAxis와 같은 패턴(MPxLocatorNode)을
// 따른다 -- 뷰포트에 그려지는 로케이터지만, 이 태스크는 그리기를 구현하지
// 않는다(범위 밖, 워킹 스켈레톤 스펙 §7 참고). compute()도 값을 계산하지
// 않는다 -- 실제 스캔은 MaroPump가 이 노드 인스턴스를 직접 순회하며
// 어트리뷰트를 읽어 주도한다(Task 6).
class MaroLidarNode : public MPxLocatorNode {
public:
    static void* creator();
    static MStatus initialize();

    static MTypeId id;

    static MObject aVerticalSamples;
    static MObject aVerticalMinAngle;
    static MObject aVerticalMaxAngle;
    static MObject aHorizontalSamples;
    static MObject aHorizontalMinAngle;
    static MObject aHorizontalMaxAngle;
    static MObject aRangeMin;
    static MObject aRangeMax;
    static MObject aUpdateRate;
    static MObject aFrameId;
    static MObject aTargetMeshes;
    static MObject aEnabled;
};

}  // namespace maro
