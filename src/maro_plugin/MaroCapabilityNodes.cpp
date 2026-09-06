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
MObject MaroLimitNode::aAxisDirection;
MObject MaroLimitNode::aMin;
MObject MaroLimitNode::aMax;
CapabilityOutAttrs MaroLimitNode::out;

void* MaroLimitNode::creator() { return new MaroLimitNode(); }

namespace {
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

    // 2026-09-07 재설계: 캘리브레이션 UI(뷰포트 2점 클릭)가 이 방향을
    // 채운다. 기본값 (0,0,1)은 "아직 캘리브레이션되지 않음"을 뜻하는
    // 플레이스홀더일 뿐 어떤 특정 관례도 아니다.
    aAxisDirection = numFn.createPoint("axisDirection", "axd");
    numFn.setStorable(true);
    numFn.setKeyable(true);
    numFn.setDefault(0.0f, 0.0f, 1.0f);
    addAttribute(aAxisDirection);

    aMin = makeAngle(angFn, "min", "mn", MAngle(-180.0, MAngle::kDegrees));
    addAttribute(aMin);
    aMax = makeAngle(angFn, "max", "mx", MAngle(180.0, MAngle::kDegrees));
    addAttribute(aMax);

    createCapabilityOut(out);
    addAttribute(out.compound);

    for (const MObject& src : {aAxisDirection, aMin, aMax}) {
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

        // 2026-09-07 재설계: 이 노드는 더 이상 "어느 축"인지 모른다(임의의
        // 커스텀 축 하나뿐이다). MaroAxisNode::compute()는 여전히
        // conventionAxis로 capMin/capMax/capEnable의 x/y/z 중 한 성분만
        // 골라 읽는다(src/maro_plugin/MaroAxisNode.cpp:296-307) -- 그
        // 코드를 한 글자도 바꾸지 않기 위해, 세 성분 모두에 똑같은 값을
        // broadcast한다. capEnable도 항상 (1,1,1)이다: 새 스키마엔 "축별
        // enable" 개념이 없다 -- capability 슬롯이 connected면 항상 활성.
        handle.child(out.enable).set3Short(1, 1, 1);

        // .asAngle().asRadians() is explicit about the unit; the compound
        // children they feed (capMin/capMax) are plain doubles carrying
        // radians.
        const double minRad = data.inputValue(aMin).asAngle().asRadians();
        const double maxRad = data.inputValue(aMax).asAngle().asRadians();
        handle.child(out.minimum).set3Double(minRad, minRad, minRad);
        handle.child(out.maximum).set3Double(maxRad, maxRad, maxRad);

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
MObject MaroTranslationLimitNode::aAxisDirection;
MObject MaroTranslationLimitNode::aMin;
MObject MaroTranslationLimitNode::aMax;
CapabilityOutAttrs MaroTranslationLimitNode::out;

void* MaroTranslationLimitNode::creator() { return new MaroTranslationLimitNode(); }

namespace {
// 거리 단위 어트리뷰트 헬퍼. 위 makeAngle과 같은 관례.
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

    aAxisDirection = numFn.createPoint("axisDirection", "axd");
    numFn.setStorable(true);
    numFn.setKeyable(true);
    numFn.setDefault(0.0f, 0.0f, 1.0f);
    addAttribute(aAxisDirection);

    // 기본 범위 +-10cm -- maroLimit의 +-180도와 같은 성격의 "합리적인 전체
    // 범위" 기본값, 특정 로봇 스펙을 반영하지 않는다.
    aMin = makeDistance(distFn, "min", "mn", MDistance(-10.0, MDistance::kCentimeters));
    addAttribute(aMin);
    aMax = makeDistance(distFn, "max", "mx", MDistance(10.0, MDistance::kCentimeters));
    addAttribute(aMax);

    createCapabilityOut(out);
    addAttribute(out.compound);

    for (const MObject& src : {aAxisDirection, aMin, aMax}) {
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

        // MaroLimitNode::compute()와 같은 broadcast 이유(위 주석 참고).
        handle.child(out.enable).set3Short(1, 1, 1);

        const double minCm = data.inputValue(aMin).asDistance().asCentimeters();
        const double maxCm = data.inputValue(aMax).asDistance().asCentimeters();
        handle.child(out.minimum).set3Double(minCm, minCm, minCm);
        handle.child(out.maximum).set3Double(maxCm, maxCm, maxCm);

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
MObject MaroCouplingNode::aSourceValueLinear;
MObject MaroCouplingNode::aSourceIsLinear;
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
    MFnUnitAttribute unitFn;

    // 다른 축의 outValue/outValueLinear에서 connectAttr로만 채워진다 --
    // maroBindAxis가 값 연결을 자동화하지 않는 기존 관례(회전축의
    // outValue -> rotateX 수동 연결)와 같은 이유로 storable/keyable을 끈다.
    //
    // 리뷰 Finding C-1: 소스 쪽도 각도/선형으로 나눈다. 평범한 double이면
    // 단위형 소스 플러그(outValue=kAngle, outValueLinear=kDistance)를
    // 연결할 때 Maya가 UI 단위 기반 unitConversion을 끼워 넣어 값이
    // 왜곡된다(도 단위 씬에서 ~57.3배).
    aSourceValue = unitFn.create("sourceValue", "srv", MFnUnitAttribute::kAngle, 0.0);
    unitFn.setStorable(false);
    unitFn.setKeyable(false);
    addAttribute(aSourceValue);

    aSourceValueLinear =
        unitFn.create("sourceValueLinear", "srl", MFnUnitAttribute::kDistance, 0.0);
    unitFn.setStorable(false);
    unitFn.setKeyable(false);
    addAttribute(aSourceValueLinear);

    // 어느 소스 슬롯이 실제로 연결됐는지는 사용자가 지정한다
    // (aOutputIsLinear와 같은 성격의 플래그).
    aSourceIsLinear = numFn.create("sourceIsLinear", "sli", MFnNumericData::kBoolean, false);
    numFn.setStorable(true);
    numFn.setKeyable(true);
    addAttribute(aSourceIsLinear);

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

    for (const MObject& src : {aSourceValue, aSourceValueLinear, aSourceIsLinear, aRatio,
                               aOffset, aOutputIsLinear, aCurvePoints}) {
        attributeAffects(src, out.compound);
    }
    return MS::kSuccess;
}

MStatus MaroCouplingNode::compute(const MPlug& plug, MDataBlock& data) {
    try {
        if (plug != out.compound && plug.parent() != out.compound) {
            return MS::kUnknownParameter;
        }

        // 단위형 슬롯에서 명시적으로 내부 단위(라디안/센티미터)로 읽는다 --
        // UI 단위와 무관하다.
        const bool sourceIsLinear = data.inputValue(aSourceIsLinear).asBool();
        const double sourceValue =
            sourceIsLinear ? data.inputValue(aSourceValueLinear).asDistance().asCentimeters()
                           : data.inputValue(aSourceValue).asAngle().asRadians();
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
