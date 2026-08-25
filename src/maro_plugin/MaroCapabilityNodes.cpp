#include "MaroCapabilityNodes.h"

#include <maya/MAngle.h>
#include <maya/MArrayDataHandle.h>
#include <maya/MDataBlock.h>
#include <maya/MDataHandle.h>
#include <maya/MDistance.h>
#include <maya/MFnCompoundAttribute.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MFnNumericAttribute.h>
#include <maya/MFnUnitAttribute.h>
#include <maya/MGlobal.h>
#include <maya/MPlug.h>

#include <algorithm>
#include <utility>
#include <vector>

#include "MaroDiag.h"

namespace maro {

namespace {

// 리뷰 Finding I3: 이 파일의 네 노드(maroRotation/maroLimit/
// maroSensorDirection/maroSensorRange) 모두 compute()가 Maya 2026 기본
// 평가 관리자 아래 워커 스레드에서 돌 수 있다 -- MaroAxisNode.cpp의
// computeContext()와 정확히 같은 정책이다(그쪽에 전체 근거를 적어 뒀다):
// nodeType과 activeCommand는 Maya 호출 없이 항상 채우고, 노드 "이름"은
// isMainThread()가 안전을 보장할 때만 MFnDependencyNode로 조회한다. 워커면
// 빈 문자열로 둔다.
DgContext computeContext(const MPxNode& node, const char* nodeType) {
    DgContext ctx;
    ctx.nodeType = nodeType;
    ctx.activeCommand = onfix::activeCommand();
    if (isMainThread()) {
        // catch 블록 안에서(이미 예외가 한 번 난 상태에서) 부르므로, 이
        // 조회 자체가 또 실패해도 Maya 콜백 경계를 못 넘게 한 번 더 감싼다.
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

// sortedPoints는 curveInput 오름차순으로 이미 정렬돼 있다고 가정한다
// (compute()가 호출 전에 정렬한다). 2개 미만이면 ratio/offset의 선형
// 관계로 대체한다(§4의 v1 범위 -- 곡선은 선택적 오버라이드). 정의역
// 밖이면 외삽하지 않고 가장 가까운 끝점 값으로 고정한다 -- 관절값이
// 정의역 밖에서 발산하면 안전 문제로 이어질 수 있다.
double interpolateCoupling(double sourceValue,
                           const std::vector<std::pair<double, double>>& sortedPoints,
                           double ratio, double offset) {
    if (sortedPoints.size() < 2) {
        return sourceValue * ratio + offset;
    }
    if (sourceValue <= sortedPoints.front().first) {
        return sortedPoints.front().second;
    }
    if (sourceValue >= sortedPoints.back().first) {
        return sortedPoints.back().second;
    }
    for (std::size_t i = 1; i < sortedPoints.size(); ++i) {
        const auto& lo = sortedPoints[i - 1];
        const auto& hi = sortedPoints[i];
        if (sourceValue <= hi.first) {
            const double span = hi.first - lo.first;
            if (span <= 0.0) return lo.second;  // 중복 curveInput 방어
            const double t = (sourceValue - lo.first) / span;
            return lo.second + t * (hi.second - lo.second);
        }
    }
    return sortedPoints.back().second;  // 이론상 도달하지 않는 방어적 fallback
}

}  // namespace

MStatus createCapabilityOut(CapabilityOutAttrs& attrs) {
    // capValue/capMin/capMax carry radians here on purpose, as plain doubles
    // rather than MFnUnitAttribute::kAngle. This compound is an internal
    // transport between our own nodes (maroRotation/maroLimit -> maroAxis);
    // it is marked non-storable/non-writable and never shown in the
    // Attribute Editor, so there is no UI-unit ambiguity to resolve. Making
    // it a unit type would also require child access through MFnUnitAttribute
    // on every read/write for no user-visible benefit. The angle/limit
    // attributes that a user actually types into keep real units; this
    // compound does not.
    MFnNumericAttribute numFn;
    MFnCompoundAttribute cmpFn;

    attrs.type = numFn.create("capType", "cpt", MFnNumericData::kShort, 0);
    attrs.value = numFn.create("capValue", "cpv", MFnNumericData::kDouble, 0.0);
    attrs.enable = numFn.create("capEnable", "cpe", MFnNumericData::k3Short, 0);
    attrs.minimum = numFn.create("capMin", "cpn", MFnNumericData::k3Double, 0.0);
    attrs.maximum = numFn.create("capMax", "cpx", MFnNumericData::k3Double, 0.0);

    attrs.compound = cmpFn.create("capabilityOut", "cpo");
    cmpFn.addChild(attrs.type);
    cmpFn.addChild(attrs.value);
    cmpFn.addChild(attrs.enable);
    cmpFn.addChild(attrs.minimum);
    cmpFn.addChild(attrs.maximum);
    cmpFn.setStorable(false);
    cmpFn.setWritable(false);

    return MS::kSuccess;
}

MTypeId MaroRotationNode::id(0x00135101);
MObject MaroRotationNode::aAngle;
CapabilityOutAttrs MaroRotationNode::out;

void* MaroRotationNode::creator() { return new MaroRotationNode(); }

MStatus MaroRotationNode::initialize() {
    MFnUnitAttribute angFn;

    // Real angular unit: the Attribute Editor now shows/accepts degrees
    // (Maya's default UI angle unit) while the data block still stores
    // radians internally, same as any native rotate* attribute.
    aAngle = angFn.create("angle", "ang", MFnUnitAttribute::kAngle, 0.0);
    angFn.setStorable(true);
    angFn.setKeyable(true);
    addAttribute(aAngle);

    createCapabilityOut(out);
    addAttribute(out.compound);

    attributeAffects(aAngle, out.compound);
    return MS::kSuccess;
}

MStatus MaroRotationNode::compute(const MPlug& plug, MDataBlock& data) {
    try {
        if (plug != out.compound && plug.parent() != out.compound) {
            return MS::kUnknownParameter;
        }

        MDataHandle handle = data.outputValue(out.compound);
        handle.child(out.type).setShort(0);   // 0 = rotation
        // .asAngle().asRadians() is explicit about the unit; the compound
        // child it feeds (capValue) is a plain double carrying radians.
        handle.child(out.value).setDouble(
            data.inputValue(aAngle).asAngle().asRadians());
        data.setClean(plug);
        return MS::kSuccess;
    } catch (...) {
        maro::BoadMaro::error("MaroRotationNode.compute.UnknownException",
                              "Maro: maroRotation compute failed.",
                              computeContext(*this, "maroRotation"));
        return MS::kFailure;
    }
}

MTypeId MaroLimitNode::id(0x00135102);
MObject MaroLimitNode::aEnableX;
MObject MaroLimitNode::aEnableY;
MObject MaroLimitNode::aEnableZ;
MObject MaroLimitNode::aMinX;
MObject MaroLimitNode::aMaxX;
MObject MaroLimitNode::aMinY;
MObject MaroLimitNode::aMaxY;
MObject MaroLimitNode::aMinZ;
MObject MaroLimitNode::aMaxZ;
CapabilityOutAttrs MaroLimitNode::out;

void* MaroLimitNode::creator() { return new MaroLimitNode(); }

namespace {
MObject makeBool(MFnNumericAttribute& fn, const char* longName,
                 const char* shortName) {
    MObject attr = fn.create(longName, shortName, MFnNumericData::kBoolean, 0);
    fn.setStorable(true);
    fn.setKeyable(true);
    return attr;
}

// Angle unit attributes. The default is expressed via MAngle so the
// intent ("+/-180 degrees") reads directly in code instead of as a
// repeated-digit radian literal.
MObject makeAngle(MFnUnitAttribute& fn, const char* longName,
                  const char* shortName, const MAngle& value) {
    MObject attr = fn.create(longName, shortName, value);
    fn.setStorable(true);
    fn.setKeyable(true);
    return attr;
}
}  // namespace

MStatus MaroLimitNode::initialize() {
    MFnNumericAttribute numFn;
    MFnUnitAttribute angFn;

    aEnableX = makeBool(numFn, "enableX", "enx");
    addAttribute(aEnableX);
    aEnableY = makeBool(numFn, "enableY", "eny");
    addAttribute(aEnableY);
    aEnableZ = makeBool(numFn, "enableZ", "enz");
    addAttribute(aEnableZ);

    aMinX = makeAngle(angFn, "minX", "mnx", MAngle(-180.0, MAngle::kDegrees));
    addAttribute(aMinX);
    aMaxX = makeAngle(angFn, "maxX", "mxx", MAngle(180.0, MAngle::kDegrees));
    addAttribute(aMaxX);
    aMinY = makeAngle(angFn, "minY", "mny", MAngle(-180.0, MAngle::kDegrees));
    addAttribute(aMinY);
    aMaxY = makeAngle(angFn, "maxY", "mxy", MAngle(180.0, MAngle::kDegrees));
    addAttribute(aMaxY);
    aMinZ = makeAngle(angFn, "minZ", "mnz", MAngle(-180.0, MAngle::kDegrees));
    addAttribute(aMinZ);
    aMaxZ = makeAngle(angFn, "maxZ", "mxz", MAngle(180.0, MAngle::kDegrees));
    addAttribute(aMaxZ);

    createCapabilityOut(out);
    addAttribute(out.compound);

    for (const MObject& src : {aEnableX, aEnableY, aEnableZ, aMinX, aMaxX,
                               aMinY, aMaxY, aMinZ, aMaxZ}) {
        attributeAffects(src, out.compound);
    }
    return MS::kSuccess;
}

MStatus MaroLimitNode::compute(const MPlug& plug, MDataBlock& data) {
    try {
        if (plug != out.compound && plug.parent() != out.compound) {
            return MS::kUnknownParameter;
        }

        MDataHandle handle = data.outputValue(out.compound);
        handle.child(out.type).setShort(1);   // 1 = limit

        handle.child(out.enable).set3Short(
            static_cast<short>(data.inputValue(aEnableX).asBool()),
            static_cast<short>(data.inputValue(aEnableY).asBool()),
            static_cast<short>(data.inputValue(aEnableZ).asBool()));

        // .asAngle().asRadians() is explicit about the unit; the compound
        // children they feed (capMin/capMax) are plain doubles carrying
        // radians.
        handle.child(out.minimum).set3Double(
            data.inputValue(aMinX).asAngle().asRadians(),
            data.inputValue(aMinY).asAngle().asRadians(),
            data.inputValue(aMinZ).asAngle().asRadians());
        handle.child(out.maximum).set3Double(
            data.inputValue(aMaxX).asAngle().asRadians(),
            data.inputValue(aMaxY).asAngle().asRadians(),
            data.inputValue(aMaxZ).asAngle().asRadians());

        data.setClean(plug);
        return MS::kSuccess;
    } catch (...) {
        maro::BoadMaro::error("MaroLimitNode.compute.UnknownException",
                              "Maro: maroLimit compute failed.",
                              computeContext(*this, "maroLimit"));
        return MS::kFailure;
    }
}

MTypeId MaroSensorDirectionNode::id(0x00135103);
MObject MaroSensorDirectionNode::aDirection;
CapabilityOutAttrs MaroSensorDirectionNode::out;

void* MaroSensorDirectionNode::creator() { return new MaroSensorDirectionNode(); }

MStatus MaroSensorDirectionNode::initialize() {
    MFnNumericAttribute numFn;

    aDirection = numFn.createPoint("direction", "dir");
    numFn.setStorable(true);
    numFn.setKeyable(true);
    numFn.setDefault(0.0f, 0.0f, 1.0f);
    addAttribute(aDirection);

    createCapabilityOut(out);
    addAttribute(out.compound);

    attributeAffects(aDirection, out.compound);
    return MS::kSuccess;
}

MStatus MaroSensorDirectionNode::compute(const MPlug& plug, MDataBlock& data) {
    try {
        if (plug != out.compound && plug.parent() != out.compound) {
            return MS::kUnknownParameter;
        }

        // 방향은 축의 구동값에 기여하지 않는다. S4가 소비할 수 있도록
        // capMin에 방향 벡터를 실어 두고 타입만 표시한다.
        const float3& dir = data.inputValue(aDirection).asFloat3();

        MDataHandle handle = data.outputValue(out.compound);
        handle.child(out.type).setShort(2);   // 2 = sensorDirection
        handle.child(out.minimum).set3Double(dir[0], dir[1], dir[2]);

        data.setClean(plug);
        return MS::kSuccess;
    } catch (...) {
        maro::BoadMaro::error("MaroSensorDirectionNode.compute.UnknownException",
                              "Maro: maroSensorDirection compute failed.",
                              computeContext(*this, "maroSensorDirection"));
        return MS::kFailure;
    }
}

MTypeId MaroSensorRangeNode::id(0x00135104);
MObject MaroSensorRangeNode::aRange;
MObject MaroSensorRangeNode::aConeAngle;
CapabilityOutAttrs MaroSensorRangeNode::out;

void* MaroSensorRangeNode::creator() { return new MaroSensorRangeNode(); }

MStatus MaroSensorRangeNode::initialize() {
    MFnNumericAttribute numFn;
    MFnUnitAttribute angFn;

    aRange = numFn.create("range", "rng", MFnNumericData::kDouble, 10.0);
    numFn.setStorable(true);
    numFn.setKeyable(true);
    addAttribute(aRange);

    // Real angular unit, same convention as maroRotation.angle and the
    // maroLimit min/max attributes: the Attribute Editor shows/accepts
    // degrees while the data block stores radians. Previously this was a
    // plain double carrying radians, so typing "30" here silently meant 30
    // radians while the adjacent capability nodes meant 30 degrees. Nothing
    // consumes this attribute yet, so there is no behavioral migration risk.
    aConeAngle = angFn.create("coneAngle", "cna", MFnUnitAttribute::kAngle,
                              0.5236);
    angFn.setStorable(true);
    angFn.setKeyable(true);
    addAttribute(aConeAngle);

    createCapabilityOut(out);
    addAttribute(out.compound);

    attributeAffects(aRange, out.compound);
    attributeAffects(aConeAngle, out.compound);
    return MS::kSuccess;
}

MStatus MaroSensorRangeNode::compute(const MPlug& plug, MDataBlock& data) {
    try {
        if (plug != out.compound && plug.parent() != out.compound) {
            return MS::kUnknownParameter;
        }

        MDataHandle handle = data.outputValue(out.compound);
        handle.child(out.type).setShort(3);   // 3 = sensorRange
        // .asAngle().asRadians() is explicit about the unit, same as
        // maroRotation/maroLimit; the compound child it feeds (capMin.y) is
        // a plain double carrying radians.
        handle.child(out.minimum).set3Double(
            data.inputValue(aRange).asDouble(),
            data.inputValue(aConeAngle).asAngle().asRadians(),
            0.0);

        data.setClean(plug);
        return MS::kSuccess;
    } catch (...) {
        maro::BoadMaro::error("MaroSensorRangeNode.compute.UnknownException",
                              "Maro: maroSensorRange compute failed.",
                              computeContext(*this, "maroSensorRange"));
        return MS::kFailure;
    }
}

MTypeId MaroTranslationNode::id(0x00135107);
MObject MaroTranslationNode::aDistance;
CapabilityOutAttrs MaroTranslationNode::out;

void* MaroTranslationNode::creator() { return new MaroTranslationNode(); }

MStatus MaroTranslationNode::initialize() {
    MFnUnitAttribute distFn;

    // maroRotation.angle과 같은 관례: AE는 사용자의 UI 선형 단위(cm/in/m)를
    // 보여주고 받지만, 데이터블록은 항상 센티미터(Maya 내부 선형 단위)로
    // 저장한다.
    aDistance = distFn.create("distance", "dst", MFnUnitAttribute::kDistance, 0.0);
    distFn.setStorable(true);
    distFn.setKeyable(true);
    addAttribute(aDistance);

    createCapabilityOut(out);
    addAttribute(out.compound);

    attributeAffects(aDistance, out.compound);
    return MS::kSuccess;
}

MStatus MaroTranslationNode::compute(const MPlug& plug, MDataBlock& data) {
    try {
        if (plug != out.compound && plug.parent() != out.compound) {
            return MS::kUnknownParameter;
        }

        MDataHandle handle = data.outputValue(out.compound);
        handle.child(out.type).setShort(4);   // 4 = translation
        // .asDistance().asCentimeters()가 단위를 명시한다; 이 컴파운드가
        // 먹이는 자식(capValue)은 센티미터를 나르는 평범한 double이다 --
        // maroRotation이 라디안을 나르는 것과 같은 관례.
        handle.child(out.value).setDouble(
            data.inputValue(aDistance).asDistance().asCentimeters());
        data.setClean(plug);
        return MS::kSuccess;
    } catch (...) {
        maro::BoadMaro::error("MaroTranslationNode.compute.UnknownException",
                              "Maro: maroTranslation compute failed.",
                              computeContext(*this, "maroTranslation"));
        return MS::kFailure;
    }
}

MTypeId MaroTranslationLimitNode::id(0x00135108);
MObject MaroTranslationLimitNode::aEnableX;
MObject MaroTranslationLimitNode::aEnableY;
MObject MaroTranslationLimitNode::aEnableZ;
MObject MaroTranslationLimitNode::aMinX;
MObject MaroTranslationLimitNode::aMaxX;
MObject MaroTranslationLimitNode::aMinY;
MObject MaroTranslationLimitNode::aMaxY;
MObject MaroTranslationLimitNode::aMinZ;
MObject MaroTranslationLimitNode::aMaxZ;
CapabilityOutAttrs MaroTranslationLimitNode::out;

void* MaroTranslationLimitNode::creator() { return new MaroTranslationLimitNode(); }

namespace {
// 거리 단위 어트리뷰트 헬퍼. 위 makeAngle/makeBool과 같은 관례 --
// 의도(기본 범위)가 반복되는 리터럴 대신 named MDistance로 읽힌다.
MObject makeDistance(MFnUnitAttribute& fn, const char* longName,
                     const char* shortName, const MDistance& value) {
    MObject attr = fn.create(longName, shortName, value);
    fn.setStorable(true);
    fn.setKeyable(true);
    return attr;
}
}  // namespace

MStatus MaroTranslationLimitNode::initialize() {
    MFnNumericAttribute numFn;
    MFnUnitAttribute distFn;

    aEnableX = makeBool(numFn, "enableX", "enx");
    addAttribute(aEnableX);
    aEnableY = makeBool(numFn, "enableY", "eny");
    addAttribute(aEnableY);
    aEnableZ = makeBool(numFn, "enableZ", "enz");
    addAttribute(aEnableZ);

    // 기본 범위 +-10cm -- maroLimit의 +-180도와 같은 성격의 "합리적인 전체
    // 범위" 기본값, 특정 로봇 스펙을 반영하지 않는다.
    aMinX = makeDistance(distFn, "minX", "mnx", MDistance(-10.0, MDistance::kCentimeters));
    addAttribute(aMinX);
    aMaxX = makeDistance(distFn, "maxX", "mxx", MDistance(10.0, MDistance::kCentimeters));
    addAttribute(aMaxX);
    aMinY = makeDistance(distFn, "minY", "mny", MDistance(-10.0, MDistance::kCentimeters));
    addAttribute(aMinY);
    aMaxY = makeDistance(distFn, "maxY", "mxy", MDistance(10.0, MDistance::kCentimeters));
    addAttribute(aMaxY);
    aMinZ = makeDistance(distFn, "minZ", "mnz", MDistance(-10.0, MDistance::kCentimeters));
    addAttribute(aMinZ);
    aMaxZ = makeDistance(distFn, "maxZ", "mxz", MDistance(10.0, MDistance::kCentimeters));
    addAttribute(aMaxZ);

    createCapabilityOut(out);
    addAttribute(out.compound);

    for (const MObject& src : {aEnableX, aEnableY, aEnableZ, aMinX, aMaxX,
                               aMinY, aMaxY, aMinZ, aMaxZ}) {
        attributeAffects(src, out.compound);
    }
    return MS::kSuccess;
}

MStatus MaroTranslationLimitNode::compute(const MPlug& plug, MDataBlock& data) {
    try {
        if (plug != out.compound && plug.parent() != out.compound) {
            return MS::kUnknownParameter;
        }

        MDataHandle handle = data.outputValue(out.compound);
        handle.child(out.type).setShort(5);   // 5 = translationLimit

        handle.child(out.enable).set3Short(
            static_cast<short>(data.inputValue(aEnableX).asBool()),
            static_cast<short>(data.inputValue(aEnableY).asBool()),
            static_cast<short>(data.inputValue(aEnableZ).asBool()));

        handle.child(out.minimum).set3Double(
            data.inputValue(aMinX).asDistance().asCentimeters(),
            data.inputValue(aMinY).asDistance().asCentimeters(),
            data.inputValue(aMinZ).asDistance().asCentimeters());
        handle.child(out.maximum).set3Double(
            data.inputValue(aMaxX).asDistance().asCentimeters(),
            data.inputValue(aMaxY).asDistance().asCentimeters(),
            data.inputValue(aMaxZ).asDistance().asCentimeters());

        data.setClean(plug);
        return MS::kSuccess;
    } catch (...) {
        maro::BoadMaro::error("MaroTranslationLimitNode.compute.UnknownException",
                              "Maro: maroTranslationLimit compute failed.",
                              computeContext(*this, "maroTranslationLimit"));
        return MS::kFailure;
    }
}

MTypeId MaroCouplingNode::id(0x00135109);
MObject MaroCouplingNode::aSourceValue;
MObject MaroCouplingNode::aRatio;
MObject MaroCouplingNode::aOffset;
MObject MaroCouplingNode::aOutputIsLinear;
MObject MaroCouplingNode::aCurvePoints;
MObject MaroCouplingNode::aCurveInput;
MObject MaroCouplingNode::aCurveOutput;
CapabilityOutAttrs MaroCouplingNode::out;

void* MaroCouplingNode::creator() { return new MaroCouplingNode(); }

MStatus MaroCouplingNode::initialize() {
    MFnNumericAttribute numFn;
    MFnCompoundAttribute cmpFn;

    // 다른 축의 outValue/outValueLinear에서 connectAttr로만 채워진다 --
    // maroBindAxis가 값 연결을 자동화하지 않는 기존 관례(회전축의
    // outValue -> rotateX 수동 연결)와 같은 이유로 storable/keyable을 끈다.
    aSourceValue = numFn.create("sourceValue", "srv", MFnNumericData::kDouble, 0.0);
    numFn.setStorable(false);
    numFn.setKeyable(false);
    addAttribute(aSourceValue);

    aRatio = numFn.create("ratio", "rat", MFnNumericData::kDouble, 1.0);
    numFn.setStorable(true);
    numFn.setKeyable(true);
    addAttribute(aRatio);

    aOffset = numFn.create("offset", "ofs", MFnNumericData::kDouble, 0.0);
    numFn.setStorable(true);
    numFn.setKeyable(true);
    addAttribute(aOffset);

    aOutputIsLinear = numFn.create("outputIsLinear", "oli", MFnNumericData::kBoolean, false);
    numFn.setStorable(true);
    numFn.setKeyable(true);
    addAttribute(aOutputIsLinear);

    aCurveInput = numFn.create("curveInput", "cvi", MFnNumericData::kDouble, 0.0);
    aCurveOutput = numFn.create("curveOutput", "cvo", MFnNumericData::kDouble, 0.0);
    aCurvePoints = cmpFn.create("curvePoints", "cvp");
    cmpFn.addChild(aCurveInput);
    cmpFn.addChild(aCurveOutput);
    cmpFn.setStorable(true);
    cmpFn.setArray(true);
    cmpFn.setIndexMatters(false);  // curveInput 값으로 정렬해서 보간하므로 논리 인덱스 순서는 무의미
    addAttribute(aCurvePoints);

    createCapabilityOut(out);
    addAttribute(out.compound);

    for (const MObject& src : {aSourceValue, aRatio, aOffset, aOutputIsLinear, aCurvePoints}) {
        attributeAffects(src, out.compound);
    }
    return MS::kSuccess;
}

MStatus MaroCouplingNode::compute(const MPlug& plug, MDataBlock& data) {
    try {
        if (plug != out.compound && plug.parent() != out.compound) {
            return MS::kUnknownParameter;
        }

        const double sourceValue = data.inputValue(aSourceValue).asDouble();
        const double ratio = data.inputValue(aRatio).asDouble();
        const double offset = data.inputValue(aOffset).asDouble();
        const bool outputIsLinear = data.inputValue(aOutputIsLinear).asBool();

        std::vector<std::pair<double, double>> points;
        MArrayDataHandle curveHandle = data.inputArrayValue(aCurvePoints);
        for (unsigned int i = 0; i < curveHandle.elementCount(); ++i) {
            curveHandle.jumpToArrayElement(i);
            MDataHandle element = curveHandle.inputValue();
            points.emplace_back(element.child(aCurveInput).asDouble(),
                                element.child(aCurveOutput).asDouble());
        }
        std::sort(points.begin(), points.end(),
                  [](const std::pair<double, double>& a,
                     const std::pair<double, double>& b) { return a.first < b.first; });

        const double value = interpolateCoupling(sourceValue, points, ratio, offset);

        MDataHandle handle = data.outputValue(out.compound);
        handle.child(out.type).setShort(outputIsLinear ? 7 : 6);
        handle.child(out.value).setDouble(value);
        data.setClean(plug);
        return MS::kSuccess;
    } catch (...) {
        maro::BoadMaro::error("MaroCouplingNode.compute.UnknownException",
                              "Maro: maroCoupling compute failed.",
                              computeContext(*this, "maroCoupling"));
        return MS::kFailure;
    }
}

}  // namespace maro
