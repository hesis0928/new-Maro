#pragma once

#include <maya/MPxNode.h>
#include <maya/MTypeId.h>

namespace maro {

// 능력 노드는 축에 쌓여 그 축의 성격을 만든다.
// 타입을 미리 고르는 게 아니라 무엇을 쌓았는지로 성격이 창발한다.

// 모든 능력 노드가 같은 모양의 복합 출력을 낸다. 축은 이걸 데이터블록으로
// 읽으므로 종류가 늘어도 축의 평가 루프는 그대로다.
//
// value/minimum/maximum은 라디안을 나르지만 일부러 MFnUnitAttribute가 아닌
// 평범한 double이다. 이 컴파운드는 우리 노드끼리만 잇는 내부 전달용이라
// storable/writable이 꺼져 있고 Attribute Editor에도 노출되지 않으므로
// UI 단위 모호성이 애초에 없다. 사용자가 직접 값을 입력하는 angle/limit
// 어트리뷰트만 실제 단위를 갖는다.
struct CapabilityOutAttrs {
    MObject compound;   // capabilityOut
    MObject type;       // capType   short
    MObject value;      // capValue  double, 라디안 (내부 전달용, 단위 없음)
    MObject enable;     // capEnable short3
    MObject minimum;    // capMin    double3, 라디안 (내부 전달용, 단위 없음)
    MObject maximum;    // capMax    double3, 라디안 (내부 전달용, 단위 없음)
};

// 능력 노드의 initialize()에서 공통 출력을 만들어 붙인다.
MStatus createCapabilityOut(CapabilityOutAttrs& attrs);

class MaroRotationNode : public MPxNode {
public:
    static void* creator();
    static MStatus initialize();
    MStatus compute(const MPlug& plug, MDataBlock& data) override;
    static MTypeId id;

    static MObject aAngle;           // MFnUnitAttribute::kAngle (AE: 도, 내부: 라디안)
    static CapabilityOutAttrs out;
};

class MaroLimitNode : public MPxNode {
public:
    static void* creator();
    static MStatus initialize();
    MStatus compute(const MPlug& plug, MDataBlock& data) override;
    static MTypeId id;

    static MObject aEnableX;
    static MObject aEnableY;
    static MObject aEnableZ;
    static MObject aMinX;            // MFnUnitAttribute::kAngle (AE: 도, 내부: 라디안)
    static MObject aMaxX;            // MFnUnitAttribute::kAngle (AE: 도, 내부: 라디안)
    static MObject aMinY;            // MFnUnitAttribute::kAngle (AE: 도, 내부: 라디안)
    static MObject aMaxY;            // MFnUnitAttribute::kAngle (AE: 도, 내부: 라디안)
    static MObject aMinZ;            // MFnUnitAttribute::kAngle (AE: 도, 내부: 라디안)
    static MObject aMaxZ;            // MFnUnitAttribute::kAngle (AE: 도, 내부: 라디안)
    static CapabilityOutAttrs out;
};

class MaroSensorDirectionNode : public MPxNode {
public:
    static void* creator();
    static MStatus initialize();
    MStatus compute(const MPlug& plug, MDataBlock& data) override;
    static MTypeId id;

    static MObject aDirection;       // float3
    static CapabilityOutAttrs out;
};

class MaroSensorRangeNode : public MPxNode {
public:
    static void* creator();
    static MStatus initialize();
    MStatus compute(const MPlug& plug, MDataBlock& data) override;
    static MTypeId id;

    static MObject aRange;           // double
    static MObject aConeAngle;       // MFnUnitAttribute::kAngle (내부: 라디안) --
                                      // maroRotation.angle/maroLimit min/max와
                                      // 같은 관례. 예전엔 plain double(라디안)
                                      // 이라 Attribute Editor에 30을 입력하면
                                      // 30도가 아니라 30라디안으로 저장됐다.
    static CapabilityOutAttrs out;
};

class MaroTranslationNode : public MPxNode {
public:
    static void* creator();
    static MStatus initialize();
    MStatus compute(const MPlug& plug, MDataBlock& data) override;
    static MTypeId id;

    static MObject aDistance;        // MFnUnitAttribute::kDistance (AE: cm/in/m 등, 내부: 센티미터)
    static CapabilityOutAttrs out;
};

class MaroTranslationLimitNode : public MPxNode {
public:
    static void* creator();
    static MStatus initialize();
    MStatus compute(const MPlug& plug, MDataBlock& data) override;
    static MTypeId id;

    static MObject aEnableX;
    static MObject aEnableY;
    static MObject aEnableZ;
    static MObject aMinX;            // MFnUnitAttribute::kDistance (AE: cm/in/m, 내부: 센티미터)
    static MObject aMaxX;
    static MObject aMinY;
    static MObject aMaxY;
    static MObject aMinZ;
    static MObject aMaxZ;
    static CapabilityOutAttrs out;
};

class MaroCouplingNode : public MPxNode {
public:
    static void* creator();
    static MStatus initialize();
    MStatus compute(const MPlug& plug, MDataBlock& data) override;
    static MTypeId id;

    static MObject aSourceValue;     // double, 다른 축의 outValue/outValueLinear에 connectAttr로 연결
    static MObject aRatio;           // double, 기본 1.0
    static MObject aOffset;          // double, 기본 0.0
    static MObject aOutputIsLinear;  // bool, 기본 false -- capType 6(각도)/7(선형) 결정
    static MObject aCurvePoints;     // compound array: curveInput/curveOutput. 2개 이상이면
                                      // ratio/offset 대신 이 곡선으로 piecewise-linear 보간.
    static MObject aCurveInput;
    static MObject aCurveOutput;
    static CapabilityOutAttrs out;
};

}  // namespace maro
