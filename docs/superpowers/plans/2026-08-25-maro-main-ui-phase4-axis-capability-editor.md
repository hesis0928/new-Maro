# Maro Main UI Phase 4 — 노드 바인딩 + capability 에디터 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Maro Main UI에 축(`maroAxis`)/capability 노드를 편집하는 패널을 추가하고, capability 노드 어휘를 회전 전용에서 직선(프리즈매틱)·기어비/연동(선형+비선형 곡선)까지 확장한다.

**Architecture:** 기존 순수-DG 아키텍처(`maroAxis.capabilityIn[]` 스택, capType 태그로 성격이 창발)를 그대로 유지하며 새 capType 4종(translation/translationLimit/coupling-각도/coupling-선형)을 추가한다. 새 undoable 커맨드 5종(`MaroAxisEditorCommands.h/.cpp`, 신규 파일)이 유일한 쓰기 경로다. UI는 `python/maroAxisPanel.py`(PySide6, 순수 함수로 flat-array↔dict 변환 분리)가 그 커맨드들을 호출하는 얇은 뷰이고, 기존 Main UI 창(`python/maroMainWindow.py`)의 레이아웃을 한 겹 더 감싸 붙인다.

**Tech Stack:** Maya C++ API(MPxNode/MPxCommand/MDGModifier), PySide6(`MQtUtil.addWidgetToMayaLayout`), mayapy 배치 테스트(스크립트 스타일, `tests/maya/test_*.py`).

## Global Constraints

- 빌드는 항상 `--config Release`를 명시한다: `cmake --build out/build --config Release`.
- `ctest --test-dir out/build -C Release --output-on-failure`는 매 태스크 후 전부 통과해야 한다(사전 결함 없음).
- 새 `.py`는 `setStyleSheet()`를 호출하지 않는다(`tests/maya/test_main_window.py`가 grep으로 검사).
- 새 커맨드 5종 전부 `MaroBindAxisCommand`(`src/maro_plugin/MaroCommands.cpp:92-288`) 패턴을 그대로 따른다: `doIt`/`redoIt`/`undoIt` 각각에 `maro::ScopedCommandContext ctxMarker("<커맨드이름>")`, `try { ... } catch (const std::exception& e) { ... } catch (...) { ... }` 경계, 실패 시 `maro::BoadMaro::error(siteTag, message, maro::onfix::capture(nodeType, attributeName, axisOrTarget), remedy)`, `isUndoable()`가 `m_stagedChange`를 반영.
- `aCapabilityIn`/`aCurvePoints` 같은 compound 배열은 항상 `evaluateNumElements()` + `elementByPhysicalIndex()`로만 순회한다. `elementByLogicalIndex()` 금지(빈 원소를 만들어내 씬을 변형시킨다).
- 새 노드 3종의 `MTypeId`는 이 계획 작성 시점(`MaroPluginMain.cpp` 등록 목록 기준) 기준 `0x00135107`(`maroTranslation`), `0x00135108`(`maroTranslationLimit`), `0x00135109`(`maroCoupling`)이다. Task 1 시작 시 `src/maro_plugin/*.cpp`에서 `MTypeId(0x00135` 를 grep해 충돌 없는지 재확인한다.
- 등록은 항상 역순으로 해제한다(`MaroPluginMain.cpp`가 이미 지켜온 규율 — 위반 시 언로드 후 죽은 함수 포인터가 전역 레지스트리에 남는다).
- 스펙 문서: `docs/superpowers/specs/2026-08-25-maro-main-ui-phase4-axis-capability-editor-design.md`.

---

## Task 1: `maroTranslation` + `maroTranslationLimit` capability 노드

**Files:**
- Modify: `src/maro_plugin/MaroCapabilityNodes.h`
- Modify: `src/maro_plugin/MaroCapabilityNodes.cpp`
- Modify: `src/maro_plugin/MaroPluginMain.cpp:139-149` (등록), `:556-560` (해제)
- Test: `tests/maya/test_capability_stack.py`

**Interfaces:**
- Produces: `maro::MaroTranslationNode`(`aDistance`, `MTypeId 0x00135107`, `capabilityOut.capType=4`), `maro::MaroTranslationLimitNode`(`aEnableX/Y/Z`, `aMinX/MaxX/MinY/MaxY/MinZ/MaxZ`, `MTypeId 0x00135108`, `capabilityOut.capType=5`). 둘 다 `MaroCapabilityNodes.h`의 기존 `CapabilityOutAttrs`/`createCapabilityOut()`을 재사용한다.

### Step 1: `MaroCapabilityNodes.h`에 두 클래스 선언 추가

`MaroSensorRangeNode` 선언(파일 끝, `}  // namespace maro` 앞) 뒤에 추가:

```cpp
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
```

### Step 2: `MaroCapabilityNodes.cpp`에 구현 추가

파일 끝(`}  // namespace maro` 앞)에 추가:

```cpp
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
```

**주의**: `makeBool`은 이미 `MaroLimitNode::initialize()` 위 익명 네임스페이스(`MaroCapabilityNodes.cpp:140-159`)에 정의돼 있으므로 재정의하지 않는다 — `MaroTranslationLimitNode::initialize()`가 그 기존 헬퍼를 그대로 쓴다. `makeDistance`만 새 익명 네임스페이스 블록(위 코드처럼 `MaroTranslationLimitNode::creator()` 뒤, `initialize()` 앞)에 추가한다. `MaroCapabilityNodes.cpp` 상단에 `#include <maya/MDistance.h>`를 추가한다(현재 없음).

### Step 3: `MaroPluginMain.cpp`에 등록/해제 추가

`kCapabilities[]` 배열(`:139-149`)에 두 항목 추가:

```cpp
const CapabilityRegistration kCapabilities[] = {
    {"maroRotation", maro::MaroRotationNode::id,
     maro::MaroRotationNode::creator, maro::MaroRotationNode::initialize},
    {"maroLimit", maro::MaroLimitNode::id,
     maro::MaroLimitNode::creator, maro::MaroLimitNode::initialize},
    {"maroSensorDirection", maro::MaroSensorDirectionNode::id,
     maro::MaroSensorDirectionNode::creator,
     maro::MaroSensorDirectionNode::initialize},
    {"maroSensorRange", maro::MaroSensorRangeNode::id,
     maro::MaroSensorRangeNode::creator, maro::MaroSensorRangeNode::initialize},
    {"maroTranslation", maro::MaroTranslationNode::id,
     maro::MaroTranslationNode::creator, maro::MaroTranslationNode::initialize},
    {"maroTranslationLimit", maro::MaroTranslationLimitNode::id,
     maro::MaroTranslationLimitNode::creator,
     maro::MaroTranslationLimitNode::initialize},
};
```

해제 블록(`:556`)에서 `deregisterNode(maro::MaroCommandDeviceNode::id);` 바로 **다음**, `deregisterNode(maro::MaroSensorRangeNode::id);` **앞**에 삽입(등록 역순 — 이 둘은 `kCapabilities` 루프 안에서 sensorRange **다음**에 등록되므로 해제는 그보다 먼저):

```cpp
        plugin.deregisterNode(maro::MaroCommandDeviceNode::id);
        plugin.deregisterNode(maro::MaroTranslationLimitNode::id);
        plugin.deregisterNode(maro::MaroTranslationNode::id);
        plugin.deregisterNode(maro::MaroSensorRangeNode::id);
        plugin.deregisterNode(maro::MaroSensorDirectionNode::id);
        plugin.deregisterNode(maro::MaroLimitNode::id);
        plugin.deregisterNode(maro::MaroRotationNode::id);
```

### Step 4: 테스트 추가 (`tests/maya/test_capability_stack.py`)

"disabled OK" 출력(현재 파일 122-125행) 뒤, 단위 계약 절 앞에 추가:

```python
# maroTranslation: 회전과 대칭인 직선 구동값. 단위는 센티미터로 고정해
# 둔다(회전 절이 currentUnit(angle="rad")로 고정한 것과 같은 이유).
cmds.currentUnit(linear="cm")
axisLinear = cmds.createNode("maroAxis", name="axisLinear")
trans = cmds.createNode("maroTranslation", name="trans1")
cmds.connectAttr(trans + ".capabilityOut", axisLinear + ".capabilityIn[0]")
assert cmds.getAttr(trans + ".capabilityOut.capType") == 4, "translation capType"
cmds.setAttr(trans + ".distance", 25.0)
outVal = cmds.getAttr(trans + ".capabilityOut.capValue")
assert abs(outVal - 25.0) < 1e-9, f"translation capValue must carry centimeters (got {outVal})"
print("translation node OK")

# maroTranslationLimit: maroLimit과 대칭인 직선 클램프.
transLim = cmds.createNode("maroTranslationLimit", name="transLim1")
cmds.setAttr(transLim + ".enableY", True)
cmds.setAttr(transLim + ".minY", -5.0)
cmds.setAttr(transLim + ".maxY", 5.0)
assert cmds.getAttr(transLim + ".capabilityOut.capType") == 5, "translationLimit capType"
minY = cmds.getAttr(transLim + ".capabilityOut.capMin")[0][1]
maxY = cmds.getAttr(transLim + ".capabilityOut.capMax")[0][1]
assert abs(minY - (-5.0)) < 1e-9 and abs(maxY - 5.0) < 1e-9, \
    f"translationLimit min/max must carry centimeters (got {minY}, {maxY})"
print("translationLimit node OK")
```

- [ ] Run: `cmake --build out/build --config Release`
- [ ] Run: `ctest --test-dir out/build -C Release -R maya_capability_stack --output-on-failure`
- [ ] Expected: PASS, prints include `translation node OK` / `translationLimit node OK`
- [ ] Commit:

```bash
git add src/maro_plugin/MaroCapabilityNodes.h src/maro_plugin/MaroCapabilityNodes.cpp \
        src/maro_plugin/MaroPluginMain.cpp tests/maya/test_capability_stack.py
git commit -m "feat: add maroTranslation/maroTranslationLimit capability nodes"
```

---

## Task 2: `maroCoupling` capability 노드 (기어비 + 선형/비선형 연동)

**Files:**
- Modify: `src/maro_plugin/MaroCapabilityNodes.h`
- Modify: `src/maro_plugin/MaroCapabilityNodes.cpp`
- Modify: `src/maro_plugin/MaroPluginMain.cpp` (등록/해제)
- Test: `tests/maya/test_capability_stack.py`

**Interfaces:**
- Consumes: `CapabilityOutAttrs`/`createCapabilityOut()`(Task 1 이전부터 존재).
- Produces: `maro::MaroCouplingNode`(`aSourceValue`, `aRatio`, `aOffset`, `aOutputIsLinear`, `aCurvePoints`(`aCurveInput`/`aCurveOutput`), `MTypeId 0x00135109`, `capabilityOut.capType` = 6(각도 출력) 또는 7(선형 출력) — `aOutputIsLinear`로 결정). 이 capType 6/7 구분이 §7의 "coupling이 각도인지 거리인지 axis가 어떻게 아는가" 열린 질문의 해법이다: rotation(0)/translation(4)이 이미 capType 값 자체로 계열을 구분하는 것과 같은 방식을 그대로 확장한다.

### Step 1: `MaroCapabilityNodes.h`에 클래스 선언 추가

Task 1의 두 클래스 뒤에 추가:

```cpp
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
```

### Step 2: `MaroCapabilityNodes.cpp`에 구현 추가

파일 상단 include에 추가: `#include <algorithm>`, `#include <utility>`, `#include <vector>`.

파일 끝에 추가(보간 헬퍼는 첫 번째 무명 네임스페이스, 즉 `computeContext` 옆에 둔다):

```cpp
namespace {

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
```

### Step 3: `MaroPluginMain.cpp`에 등록/해제 추가

`kCapabilities[]`에 Task 1의 두 항목 뒤로 추가:

```cpp
    {"maroCoupling", maro::MaroCouplingNode::id,
     maro::MaroCouplingNode::creator, maro::MaroCouplingNode::initialize},
```

해제 블록에서 Task 1이 추가한 두 줄 앞에 삽입(가장 나중에 등록됐으므로 가장 먼저 해제):

```cpp
        plugin.deregisterNode(maro::MaroCommandDeviceNode::id);
        plugin.deregisterNode(maro::MaroCouplingNode::id);
        plugin.deregisterNode(maro::MaroTranslationLimitNode::id);
        plugin.deregisterNode(maro::MaroTranslationNode::id);
        plugin.deregisterNode(maro::MaroSensorRangeNode::id);
```

### Step 4: 테스트 추가 (`tests/maya/test_capability_stack.py`)

Task 1이 추가한 절 뒤에 추가:

```python
# maroCoupling: ratio/offset 경로 (곡선 없음).
coupling = cmds.createNode("maroCoupling", name="coupling1")
sourceRot = cmds.createNode("maroRotation", name="couplingSource")
cmds.setAttr(sourceRot + ".angle", 1.0)
cmds.connectAttr(sourceRot + ".capabilityOut.capValue", coupling + ".sourceValue")
cmds.setAttr(coupling + ".ratio", 2.0)
cmds.setAttr(coupling + ".offset", 0.5)
capValue = cmds.getAttr(coupling + ".capabilityOut.capValue")
assert abs(capValue - (1.0 * 2.0 + 0.5)) < 1e-9, f"coupling ratio/offset math wrong (got {capValue})"
assert cmds.getAttr(coupling + ".capabilityOut.capType") == 6, "coupling default capType (angular)"
print("coupling ratio/offset OK")

# outputIsLinear가 capType을 7로 바꾼다.
cmds.setAttr(coupling + ".outputIsLinear", True)
assert cmds.getAttr(coupling + ".capabilityOut.capType") == 7, "coupling linear capType"
print("coupling outputIsLinear OK")

# 곡선이 2점 이상이면 ratio/offset을 대체한다. 점: (0,0), (1,10), (2,10)
# -- 0~1 구간은 기울기 10, 1~2 구간은 평평(리밋처럼 동작).
cmds.setAttr(coupling + ".curvePoints[0].curveInput", 0.0)
cmds.setAttr(coupling + ".curvePoints[0].curveOutput", 0.0)
cmds.setAttr(coupling + ".curvePoints[1].curveInput", 1.0)
cmds.setAttr(coupling + ".curvePoints[1].curveOutput", 10.0)
cmds.setAttr(coupling + ".curvePoints[2].curveInput", 2.0)
cmds.setAttr(coupling + ".curvePoints[2].curveOutput", 10.0)

cmds.setAttr(sourceRot + ".angle", 0.5)   # 0~1 구간 중간
mid = cmds.getAttr(coupling + ".capabilityOut.capValue")
assert abs(mid - 5.0) < 1e-9, f"curve interpolation at midpoint wrong (got {mid})"

cmds.setAttr(sourceRot + ".angle", 1.5)   # 1~2 구간(평평)
plateau = cmds.getAttr(coupling + ".capabilityOut.capValue")
assert abs(plateau - 10.0) < 1e-9, f"curve interpolation on plateau wrong (got {plateau})"

cmds.setAttr(sourceRot + ".angle", 5.0)   # 정의역 밖 -- 외삽하지 않고 끝점 고정
clamped = cmds.getAttr(coupling + ".capabilityOut.capValue")
assert abs(clamped - 10.0) < 1e-9, f"out-of-domain must clamp to last point, not extrapolate (got {clamped})"
print("coupling curve interpolation OK")
```

- [ ] Run: `cmake --build out/build --config Release`
- [ ] Run: `ctest --test-dir out/build -C Release -R maya_capability_stack --output-on-failure`
- [ ] Expected: PASS
- [ ] Commit:

```bash
git add src/maro_plugin/MaroCapabilityNodes.h src/maro_plugin/MaroCapabilityNodes.cpp \
        src/maro_plugin/MaroPluginMain.cpp tests/maya/test_capability_stack.py
git commit -m "feat: add maroCoupling capability node (ratio/offset + embedded curve)"
```

---

## Task 3: `maroAxis` 확장 — `outValueLinear` + capType 4/5/6/7 처리

**Files:**
- Modify: `src/maro_plugin/MaroAxisNode.h`
- Modify: `src/maro_plugin/MaroAxisNode.cpp`
- Test: `tests/maya/test_capability_stack.py`

**Interfaces:**
- Consumes: capType 4(translation)/5(translationLimit)/6(coupling-각도)/7(coupling-선형) — Task 1/2가 만든 노드가 이 값을 낸다.
- Produces: `MaroAxisNode::aOutValueLinear`(`MFnUnitAttribute::kDistance`, storable/writable false), `MaroAxisNode::aDriveIsLinear`(bool, storable/writable false) — Task 4(`MaroPump`)가 이 두 어트리뷰트를 읽는다.

### Step 1: `MaroAxisNode.h` 수정

`aCapType` 주석 갱신(`:27`):

```cpp
    static MObject aCapType;        //   short  0=rotation 1=limit 2=sensorDir 3=sensorRange
                                     //          4=translation 5=translationLimit
                                     //          6=coupling(각도출력) 7=coupling(선형출력)
```

`aOutValue`/`aOutTransform` 선언(`:54-55`) 뒤에 추가:

```cpp
    static MObject aOutValueLinear; // MFnUnitAttribute::kDistance (내부: 센티미터) --
                                     // 직선 구동 축(translation/translationLimit/
                                     // coupling-선형)의 출력. aDriveIsLinear가
                                     // true인 축만 이 값이 유효하다.
    static MObject aDriveIsLinear;  // bool -- compute()가 채운다. true면
                                     // aOutValueLinear가, false면 aOutValue가
                                     // 이 틱의 유효한 구동값이다. MaroPump가
                                     // 스택을 다시 훑지 않고 이 플래그 하나로
                                     // 어느 출력을 읽을지 결정한다.
```

### Step 2: `MaroAxisNode.cpp` 수정

파일 상단 include에 `#include <maya/MDistance.h>` 추가(현재 `MAngle.h`만 있음).

정적 멤버 정의(`:87-88` 근처)에 추가:

```cpp
MObject MaroAxisNode::aOutValueLinear;
MObject MaroAxisNode::aDriveIsLinear;
```

`initialize()`에서 `aOutValue` 블록(`:174-177`) 뒤에 추가:

```cpp
    aOutValueLinear = angFn.create("positionLinear", "otvl",
                                   MFnUnitAttribute::kDistance, 0.0);
    angFn.setStorable(false);
    angFn.setWritable(false);
    addAttribute(aOutValueLinear);
```

(`angFn`은 `MFnUnitAttribute`이고 이미 `aOutValue` 생성에 쓰인 것을 재사용한다 — `MaroLimitNode::initialize()`가 `angFn`을 여러 어트리뷰트에 재사용하는 것과 같은 패턴.)

`aOutTransform` 블록(`:179-183`) 뒤에 추가(별도 `MFnNumericAttribute` 필요 — 기존 `numFn` 재사용):

```cpp
    aDriveIsLinear = numFn.create("driveIsLinear", "dil", MFnNumericData::kBoolean, false);
    numFn.setStorable(false);
    numFn.setWritable(false);
    addAttribute(aDriveIsLinear);
```

`attributeAffects` 루프(`:189-196`) 전체를 아래로 교체:

```cpp
    for (const MObject& src : {aConventionAxis, aEnabled,
                               aControlMode, aRosCommand}) {
        attributeAffects(src, aOutValue);
        attributeAffects(src, aOutValueLinear);
        attributeAffects(src, aDriveIsLinear);
        attributeAffects(src, aOutTransform);
    }

    attributeAffects(aCapabilityIn, aOutValue);
    attributeAffects(aCapabilityIn, aOutValueLinear);
    attributeAffects(aCapabilityIn, aDriveIsLinear);
    attributeAffects(aCapabilityIn, aOutTransform);
```

`compute()` 전체(`:201-280`)를 아래로 교체:

```cpp
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
                } else if (capType == 1) {    // limit (각도 계열 클램프, 기존 로직)
                    const short3& enable = element.child(aCapEnable).asShort3();
                    if (enable[component] != 0) {
                        const double3& lo = element.child(aCapMin).asDouble3();
                        const double3& hi = element.child(aCapMax).asDouble3();
                        value = std::clamp(value,
                                           std::min(lo[component], hi[component]),
                                           std::max(lo[component], hi[component]));
                    }
                } else if (capType == 5) {    // translationLimit (직선 계열 클램프, limit과 동일 로직)
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
```

### Step 3: 테스트 추가 (`tests/maya/test_capability_stack.py`)

Task 2가 추가한 절 뒤에 추가:

```python
# maroAxis가 translation을 outValueLinear로 라우팅하고, driveIsLinear가
# 그것을 알린다. 기존 rotation 경로(outValue)는 회귀 없이 그대로 유지돼야
# 한다 -- axis(맨 처음 만든 rotation 전용 축)로 재확인한다.
assert cmds.getAttr(axis + ".driveIsLinear") is False, "rotation axis must report driveIsLinear=False"
assert abs(cmds.getAttr(axis + ".positionLinear")) < 1e-9, "rotation axis outValueLinear must stay 0"
print("rotation axis regression (driveIsLinear/positionLinear) OK")

axisTrans = cmds.createNode("maroAxis", name="axisTrans")
transDrive = cmds.createNode("maroTranslation", name="transDrive1")
cmds.connectAttr(transDrive + ".capabilityOut", axisTrans + ".capabilityIn[0]")
cmds.setAttr(transDrive + ".distance", 12.5)
assert cmds.getAttr(axisTrans + ".driveIsLinear") is True, "translation axis must report driveIsLinear=True"
posLinear = cmds.getAttr(axisTrans + ".positionLinear")
assert abs(posLinear - 12.5) < 1e-9, f"translation axis positionLinear wrong (got {posLinear})"
assert abs(cmds.getAttr(axisTrans + ".position")) < 1e-9, "translation axis outValue(angular) must stay 0"
print("translation axis routing OK")

# translationLimit이 직선 구동값을 클램프한다.
transLimDrive = cmds.createNode("maroTranslationLimit", name="transLimDrive1")
cmds.setAttr(transLimDrive + ".enableY", True)
cmds.setAttr(transLimDrive + ".minY", -5.0)
cmds.setAttr(transLimDrive + ".maxY", 5.0)
cmds.connectAttr(transLimDrive + ".capabilityOut", axisTrans + ".capabilityIn[1]")
clampedLinear = cmds.getAttr(axisTrans + ".positionLinear")
assert abs(clampedLinear - 5.0) < 1e-9, f"translationLimit did not clamp (got {clampedLinear})"
print("translationLimit clamp OK")

# coupling-선형이 다른 축의 outValue를 소스로 받아 axis를 직선 구동한다.
axisCoupled = cmds.createNode("maroAxis", name="axisCoupled")
couplingDrive = cmds.createNode("maroCoupling", name="couplingDrive1")
cmds.setAttr(couplingDrive + ".outputIsLinear", True)
cmds.setAttr(couplingDrive + ".ratio", 3.0)
cmds.connectAttr(axisTrans + ".positionLinear", couplingDrive + ".sourceValue")
cmds.connectAttr(couplingDrive + ".capabilityOut", axisCoupled + ".capabilityIn[0]")
assert cmds.getAttr(axisCoupled + ".driveIsLinear") is True, "coupling-linear axis must report driveIsLinear=True"
coupledLinear = cmds.getAttr(axisCoupled + ".positionLinear")
assert abs(coupledLinear - 5.0 * 3.0) < 1e-9, f"coupling-linear routing wrong (got {coupledLinear})"
print("coupling-linear axis routing OK")

# §3 상호배타 규칙의 DG 레벨 방어: rotation과 translation을 같은 축에
# 억지로(스크립트로, 커맨드 검증을 우회해) 연결해도 죽지 않고 "먼저 나온
# 것이 이긴다"로 조용히 처리된다.
axisConflict = cmds.createNode("maroAxis", name="axisConflict")
rotConflict = cmds.createNode("maroRotation", name="rotConflict")
transConflict = cmds.createNode("maroTranslation", name="transConflict")
cmds.setAttr(rotConflict + ".angle", 0.4)
cmds.setAttr(transConflict + ".distance", 40.0)
cmds.connectAttr(rotConflict + ".capabilityOut", axisConflict + ".capabilityIn[0]")
cmds.connectAttr(transConflict + ".capabilityOut", axisConflict + ".capabilityIn[1]")
assert cmds.getAttr(axisConflict + ".driveIsLinear") is False, \
    "first primary driver (index 0, rotation) must win over a later conflicting one"
assert abs(cmds.getAttr(axisConflict + ".position") - 0.4) < 1e-9, \
    "conflicting stack must still drive from the first primary driver"
print("primary-driver conflict defensive handling OK")
```

- [ ] Run: `cmake --build out/build --config Release`
- [ ] Run: `ctest --test-dir out/build -C Release -R maya_capability_stack --output-on-failure`
- [ ] Expected: PASS(기존 단언 전부 + 위 새 단언 전부)
- [ ] Commit:

```bash
git add src/maro_plugin/MaroAxisNode.h src/maro_plugin/MaroAxisNode.cpp \
        tests/maya/test_capability_stack.py
git commit -m "feat: route translation/coupling axes to outValueLinear, add driveIsLinear"
```

---

## Task 4: `MaroPump::collectSamples`가 직선 구동 축을 미터로 발행

**Files:**
- Modify: `src/maro_plugin/MaroPump.cpp:159-166`
- Test: `tests/maya/test_publish.py`

**Interfaces:**
- Consumes: `MaroAxisNode::aDriveIsLinear`, `MaroAxisNode::aOutValueLinear`(Task 3).

### Step 1: `MaroPump.cpp` 수정

`:159-166`을 아래로 교체:

```cpp
        AxisSample sample;
        sample.jointName = joint.asChar();
        // driveIsLinear가 이 틱에 어느 출력이 유효한지 알려준다 -- 스택을
        // 다시 훑지 않고 MaroAxisNode::compute()가 이미 판정해 둔 플래그
        // 하나만 읽는다(Task 3).
        if (axisFn.findPlug(MaroAxisNode::aDriveIsLinear, false).asBool()) {
            // aOutValueLinear는 MFnUnitAttribute::kDistance다.
            // asMDistance().asMeters()로 읽으면 씬의 내부 선형 단위(Maya는
            // 항상 센티미터)와 무관하게 항상 미터로 받는다 -- aOutValue를
            // asMAngle().asRadians()로 읽는 것과 같은 이유, 같은 관례다.
            sample.value = axisFn.findPlug(MaroAxisNode::aOutValueLinear, false)
                               .asMDistance()
                               .asMeters();
        } else {
            // aOutValue는 MFnUnitAttribute::kAngle이다. asDouble()로 읽으면
            // Maya가 UI 각도 단위(기본 도)로 변환한 값을 돌려줄 수 있어
            // 라디안이 필요한 이 파이프라인에서 값이 어긋난다. asAngle()로
            // 받아 asRadians()로 명시해야 항상 라디안이다.
            sample.value = axisFn.findPlug(MaroAxisNode::aOutValue, false)
                               .asMAngle()
                               .asRadians();
        }
```

### Step 2: 테스트 추가 (`tests/maya/test_publish.py`)

`test_publish.py`의 `main()` 안, 기존 회전축(`axis`/`axisPub`) 설정 블록 뒤·`try:`(브리지 시작) 앞에 두 번째(직선 구동) 축을 추가한다:

```python
    # Task 4: 직선 구동 축도 같은 브리지/피어로 검증한다. 회전축과 별개
    # 이름으로 둬서 피어 출력에서 줄 단위로 구분한다.
    cubeLinear = cmds.polyCube(name="segLinear")[0]
    axisLinear = cmds.createNode("maroAxis", name="axisPubLinear")
    cmds.maroBindAxis(axisLinear, cubeLinear)
    cmds.setAttr(axisLinear + ".jointName", "axisPubLinear", type="string")
    transPub = cmds.createNode("maroTranslation")
    cmds.connectAttr(transPub + ".capabilityOut", axisLinear + ".capabilityIn[0]")
    # currentUnit(linear="cm")이 위에서 이미 고정돼 있다 -- 250cm = 2.5m.
    cmds.setAttr(transPub + ".distance", 250.0)

    EXPECTED_JOINT_LINEAR = "axisPubLinear"
    EXPECTED_VALUE_LINEAR = 2.5  # 미터
```

`try:` 블록 안, 첫 번째 회전축 피어(`listener`) 검증이 끝난 직후(`print(f"publish round trip OK ...")` 다음, `/tf` 검증 전)에 두 번째 피어 검증을 추가한다:

```python
        # Task 4: 두 번째 피어로 직선 구동 축이 라디안이 아니라 "미터"로
        # 발행되는지 확인한다 -- 이름만 맞고 단위가 틀리면(예: 센티미터
        # 그대로 발행) "피어가 뭔가는 받았다"만 보는 테스트는 통과해 버린다.
        linearListener = subprocess.Popen(
            [peer, "echo", "maro", "1", str(PEER_TIMEOUT_SEC)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        peers.append(linearListener)

        linear_out, linear_stats = _wait_for_peer(linearListener, BACKSTOP_SEC)
        print(linear_out)

        assert linearListener.returncode == 0, \
            f"peer never received joint_states for linear axis (timed out); " \
            f"maroBridgeStats={linear_stats}\npeer output:\n{linear_out}"
        assert f"joint {EXPECTED_JOINT_LINEAR} = " in linear_out, \
            f"joint name '{EXPECTED_JOINT_LINEAR}' missing from published message:\n{linear_out}"

        publishedLinear = None
        for line in linear_out.splitlines():
            prefix = f"joint {EXPECTED_JOINT_LINEAR} = "
            if line.startswith(prefix):
                publishedLinear = float(line[len(prefix):].strip())
                break
        assert publishedLinear is not None, \
            f"could not parse published value for '{EXPECTED_JOINT_LINEAR}':\n{linear_out}"
        assert abs(publishedLinear - EXPECTED_VALUE_LINEAR) < 1e-6, \
            f"linear joint published as {publishedLinear}, expected {EXPECTED_VALUE_LINEAR} m " \
            f"(250cm in -> 2.5m out):\n{linear_out}\nmaroBridgeStats={linear_stats}"
        print(f"linear publish round trip OK (joint={EXPECTED_JOINT_LINEAR}, value={publishedLinear})")
```

- [ ] Run: `cmake --build out/build --config Release`
- [ ] Run: `ctest --test-dir out/build -C Release -R maya_publish --output-on-failure`
- [ ] Expected: PASS, 출력에 `linear publish round trip OK` 포함
- [ ] Commit:

```bash
git add src/maro_plugin/MaroPump.cpp tests/maya/test_publish.py
git commit -m "feat: publish linear-driven axes in meters via outValueLinear"
```

---

## Task 5: `maroListAxisNodes` 쿼리 커맨드

**Files:**
- Create: `src/maro_plugin/MaroAxisEditorCommands.h`
- Create: `src/maro_plugin/MaroAxisEditorCommands.cpp`
- Modify: `src/maro_plugin/CMakeLists.txt:24` (SOURCE_FILES에 추가)
- Modify: `tests/CMakeLists.txt:249` (테스트 목록에 추가)
- Modify: `src/maro_plugin/MaroPluginMain.cpp` (등록/해제)
- Test: `tests/maya/test_axis_editor_commands.py` (신규)

**Interfaces:**
- Produces: `maroListAxisNodes` 커맨드. 플래그 없으면 `MStringArray`(축 1개당 `AXIS_FIELDS=8`행: `axisFullPath, jointName, boundTargetPath, parentAxisPath, controlMode, enabled, conventionAxis, capabilityCount`). `-capabilities`/`-cap <axis>`면 그 축의 슬롯별 `CAPABILITY_FIELDS=5`행: `logicalIndex, capabilityNodeName, capabilityNodeType, capType, connected`.
- Produces(Task 6이 재사용): `nextFreeCapabilitySlot(MPlug capabilityInPlug)`, `hasPrimaryDriver(MPlug capabilityInPlug)` — 둘 다 이 파일의 무명 네임스페이스에 정의.

### Step 1: `MaroAxisEditorCommands.h`

```cpp
#pragma once

#include <maya/MPxCommand.h>
#include <maya/MSyntax.h>

namespace maro {

// 씬의 maroAxis 전체 또는 한 축의 capability 스택을 나열한다. 쿼리
// 전용이라 undoable이 아니다.
class MaroListAxisNodesCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
    bool isUndoable() const override { return false; }
};

}  // namespace maro
```

### Step 2: `MaroAxisEditorCommands.cpp`

```cpp
#include "MaroAxisEditorCommands.h"

#include <sstream>

#include <maya/MArgDatabase.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MItDependencyNodes.h>
#include <maya/MPlugArray.h>
#include <maya/MSelectionList.h>
#include <maya/MStringArray.h>

#include "MaroAxisNode.h"
#include "MaroDiag.h"

namespace maro {

namespace {

const char* kCapabilitiesFlag = "-cap";
const char* kCapabilitiesFlagLong = "-capabilities";

// 축 하나에 바인딩된 타겟 트랜스폼의 전체 경로를 돌려준다. 없으면 빈 문자열.
// aTargetObject는 message라 connectedTo로만 얻을 수 있다
// (MaroBindAxisCommand::doIt과 같은 패턴).
MString boundTargetPath(const MFnDependencyNode& axisFn) {
    MPlugArray sources;
    axisFn.findPlug(MaroAxisNode::aTargetObject, false).connectedTo(sources, true, false);
    if (sources.length() == 0) return MString();
    MFnDependencyNode targetFn(sources[0].node());
    MDagPath path;
    if (MDagPath::getAPathTo(sources[0].node(), path) == MS::kSuccess) {
        return path.fullPathName();
    }
    return targetFn.name();
}

MString parentAxisPath(const MFnDependencyNode& axisFn) {
    MPlugArray sources;
    axisFn.findPlug(MaroAxisNode::aParentAxis, false).connectedTo(sources, true, false);
    if (sources.length() == 0) return MString();
    MDagPath path;
    if (MDagPath::getAPathTo(sources[0].node(), path) == MS::kSuccess) {
        return path.fullPathName();
    }
    return MFnDependencyNode(sources[0].node()).name();
}

unsigned int occupiedCapabilityCount(MPlug capabilityInPlug) {
    unsigned int count = 0;
    const unsigned int total = capabilityInPlug.evaluateNumElements();
    for (unsigned int i = 0; i < total; ++i) {
        MPlugArray sources;
        capabilityInPlug.elementByPhysicalIndex(i).connectedTo(sources, true, false);
        if (sources.length() > 0) ++count;
    }
    return count;
}

MStatus listAxes(MStringArray& result) {
    for (MItDependencyNodes it(MFn::kPluginLocatorNode); !it.isDone(); it.next()) {
        MFnDependencyNode axisFn(it.thisNode());
        if (axisFn.typeId() != MaroAxisNode::id) continue;

        MDagPath axisPath;
        MString axisFullPath = axisFn.name();
        if (MDagPath::getAPathTo(it.thisNode(), axisPath) == MS::kSuccess) {
            axisFullPath = axisPath.fullPathName();
        }

        result.append(axisFullPath);
        result.append(axisFn.findPlug(MaroAxisNode::aJointName, false).asString());
        result.append(boundTargetPath(axisFn));
        result.append(parentAxisPath(axisFn));
        result.append(MString() + axisFn.findPlug(MaroAxisNode::aControlMode, false).asShort());
        result.append(axisFn.findPlug(MaroAxisNode::aEnabled, false).asBool() ? "1" : "0");
        result.append(MString() + axisFn.findPlug(MaroAxisNode::aConventionAxis, false).asShort());
        result.append(MString() + static_cast<int>(occupiedCapabilityCount(
            axisFn.findPlug(MaroAxisNode::aCapabilityIn, false))));
    }
    return MS::kSuccess;
}

MStatus listCapabilities(const MString& axisName, MStringArray& result) {
    MSelectionList selection;
    if (!selection.add(axisName)) {
        maro::BoadMaro::error(
            "MaroListAxisNodesCommand.AxisNotFound",
            MString("Maro: cannot find node '") + axisName + "'.",
            maro::onfix::capture("", "", axisName));
        return MS::kFailure;
    }
    MObject axisObj;
    selection.getDependNode(0, axisObj);
    MFnDependencyNode axisFn(axisObj);
    if (axisFn.typeId() != MaroAxisNode::id) {
        maro::BoadMaro::error(
            "MaroListAxisNodesCommand.NotMaroAxisNode",
            MString("Maro: '") + axisName + "' is not a maroAxis node.",
            maro::onfix::capture(axisFn.typeName(), "", axisName));
        return MS::kFailure;
    }

    MPlug capabilityIn = axisFn.findPlug(MaroAxisNode::aCapabilityIn, false);
    const unsigned int total = capabilityIn.evaluateNumElements();
    for (unsigned int i = 0; i < total; ++i) {
        MPlug element = capabilityIn.elementByPhysicalIndex(i);
        MPlugArray sources;
        element.connectedTo(sources, true, false);

        result.append(MString() + static_cast<int>(element.logicalIndex()));
        if (sources.length() > 0) {
            MFnDependencyNode capFn(sources[0].node());
            MDagPath capPath;
            MString capName = capFn.name();
            if (MDagPath::getAPathTo(sources[0].node(), capPath) == MS::kSuccess) {
                capName = capPath.fullPathName();
            }
            result.append(capName);
            result.append(capFn.typeName());
        } else {
            result.append("");
            result.append("");
        }
        result.append(MString() + element.child(MaroAxisNode::aCapType).asShort());
        result.append(sources.length() > 0 ? "1" : "0");
    }
    return MS::kSuccess;
}

}  // namespace

// Task 6이 재사용하는 헬퍼 -- 이 커맨드 파일에 두는 이유는 쿼리(위
// listCapabilities)와 같은 순회 패턴을 공유해서다.
unsigned int nextFreeCapabilitySlot(MPlug capabilityInPlug) {
    const unsigned int count = capabilityInPlug.evaluateNumElements();
    for (unsigned int i = 0; i < count; ++i) {
        MPlug element = capabilityInPlug.elementByPhysicalIndex(i);
        MPlugArray sources;
        element.connectedTo(sources, true, false);
        if (sources.length() == 0) {
            return element.logicalIndex();
        }
    }
    return count;  // 빈 슬롯이 없으면 다음 논리 인덱스에 새로 만든다
}

bool hasPrimaryDriver(MPlug capabilityInPlug) {
    const unsigned int count = capabilityInPlug.evaluateNumElements();
    for (unsigned int i = 0; i < count; ++i) {
        MPlug element = capabilityInPlug.elementByPhysicalIndex(i);
        MPlugArray sources;
        element.connectedTo(sources, true, false);
        if (sources.length() == 0) continue;

        const short existingType = element.child(MaroAxisNode::aCapType).asShort();
        if (existingType == 0 || existingType == 4 ||
            existingType == 6 || existingType == 7) {
            return true;
        }
    }
    return false;
}

void* MaroListAxisNodesCommand::creator() {
    return new MaroListAxisNodesCommand();
}

MSyntax MaroListAxisNodesCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag(kCapabilitiesFlag, kCapabilitiesFlagLong, MSyntax::kString);
    return syntax;
}

MStatus MaroListAxisNodesCommand::doIt(const MArgList& args) {
    maro::ScopedCommandContext ctxMarker("MaroListAxisNodesCommand");
    try {
        MStatus status;
        MArgDatabase argData(syntax(), args, &status);
        if (!status) return status;

        MStringArray result;
        if (argData.isFlagSet(kCapabilitiesFlag)) {
            MString axisName;
            argData.getFlagArgument(kCapabilitiesFlag, 0, axisName);
            status = listCapabilities(axisName, result);
            if (!status) return status;
        } else {
            status = listAxes(result);
            if (!status) return status;
        }

        setResult(result);
        return MS::kSuccess;
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroListAxisNodesCommand.doIt.Exception",
                              MString("Maro: maroListAxisNodes failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroListAxisNodesCommand.doIt.UnknownException",
                              "Maro: maroListAxisNodes failed with unknown error.");
        return MS::kFailure;
    }
}

}  // namespace maro
```

**주의**: `nextFreeCapabilitySlot`/`hasPrimaryDriver`는 (무명 네임스페이스 밖에 두어) `maro::` 네임스페이스에서 다른 `.cpp`가 링크 시점에 볼 수 있게 한다 — Task 6이 이 두 함수를 그대로 호출한다. 헤더에 선언을 추가한다: `MaroAxisEditorCommands.h`의 `namespace maro {` 블록 안, 클래스 선언 뒤에:

```cpp
// Task 6(쓰기 커맨드)이 재사용하는 헬퍼.
unsigned int nextFreeCapabilitySlot(MPlug capabilityInPlug);
bool hasPrimaryDriver(MPlug capabilityInPlug);
```

(`MPlug` 전방 선언 또는 `<maya/MPlug.h>` include가 헤더에 필요 — `#include <maya/MPlug.h>`를 헤더 상단에 추가한다.)

### Step 3: `CMakeLists.txt`/`MaroPluginMain.cpp` 배선

`src/maro_plugin/CMakeLists.txt`의 `SOURCE_FILES`(`:24` 근처, `MaroRosProxyCommands.cpp` 뒤)에 추가:

```cmake
    MaroAxisEditorCommands.cpp
```

`MaroPluginMain.cpp` 상단 include 목록에 `#include "MaroAxisEditorCommands.h"` 추가. `maroSetRosProxyTarget` 등록(`:367-373`) 뒤, `MaroDeleteWatcher::install()`(`:375`) 앞에 추가:

```cpp
    status = plugin.registerCommand("maroListAxisNodes",
                                    maro::MaroListAxisNodesCommand::creator,
                                    maro::MaroListAxisNodesCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroListAxisNodes");
        return status;
    }
```

해제 블록에서 `plugin.deregisterCommand("maroSetRosProxyTarget");`(`:493`) **앞**에 삽입(등록 역순 — 이 커맨드가 그 다음에 등록됐으므로 먼저 해제):

```cpp
        plugin.deregisterCommand("maroListAxisNodes");
        plugin.deregisterCommand("maroSetRosProxyTarget");
```

### Step 4: 테스트 (`tests/maya/test_axis_editor_commands.py`, 신규)

```python
"""새 축 에디터 커맨드: maroListAxisNodes(이번 태스크) + Task 6의 쓰기 커맨드."""
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)
cmds.currentUnit(angle="rad")
cmds.currentUnit(linear="cm")

AXIS_FIELDS = 8
CAPABILITY_FIELDS = 5

# --- maroListAxisNodes, 플래그 없음 ---
axis1 = cmds.createNode("maroAxis", name="listAxis1")
cube1 = cmds.polyCube(name="listCube1")[0]
cmds.maroBindAxis(axis1, cube1)
cmds.setAttr(axis1 + ".jointName", "listAxis1", type="string")

rows = cmds.maroListAxisNodes()
assert len(rows) % AXIS_FIELDS == 0, f"row array length {len(rows)} not a multiple of {AXIS_FIELDS}"
found = None
for i in range(len(rows) // AXIS_FIELDS):
    f = rows[i * AXIS_FIELDS:(i + 1) * AXIS_FIELDS]
    if f[0].endswith("listAxis1"):
        found = f
        break
assert found is not None, "listAxis1 missing from maroListAxisNodes()"
assert found[1] == "listAxis1", f"jointName field wrong: {found[1]}"
assert found[2].endswith("listCube1"), f"boundTargetPath field wrong: {found[2]}"
assert found[3] == "", "unparented axis must have empty parentAxisPath"
assert found[4] == "0", f"controlMode field wrong (default Manual): {found[4]}"
assert found[5] == "1", f"enabled field wrong (default True): {found[5]}"
assert found[7] == "0", f"capabilityCount must be 0 before any capability connected: {found[7]}"
print("maroListAxisNodes (no flag) OK")

# --- capabilityCount가 실제 연결 수를 반영한다 ---
rot1 = cmds.createNode("maroRotation", name="listRot1")
cmds.connectAttr(rot1 + ".capabilityOut", axis1 + ".capabilityIn[0]")
rows = cmds.maroListAxisNodes()
for i in range(len(rows) // AXIS_FIELDS):
    f = rows[i * AXIS_FIELDS:(i + 1) * AXIS_FIELDS]
    if f[0].endswith("listAxis1"):
        assert f[7] == "1", f"capabilityCount must be 1 after one connection: {f[7]}"
        break
print("capabilityCount reflects connections OK")

# --- maroListAxisNodes -capabilities <axis> ---
capRows = cmds.maroListAxisNodes(capabilities=axis1)
assert len(capRows) % CAPABILITY_FIELDS == 0, \
    f"capability row array length {len(capRows)} not a multiple of {CAPABILITY_FIELDS}"
assert len(capRows) // CAPABILITY_FIELDS == 1, \
    f"expected exactly 1 capability row, got {len(capRows) // CAPABILITY_FIELDS}"
logicalIndex, capName, capType, capTypeNum, connected = capRows[0:5]
assert logicalIndex == "0", f"logicalIndex wrong: {logicalIndex}"
assert capName.endswith("listRot1"), f"capabilityNodeName wrong: {capName}"
assert capType == "maroRotation", f"capabilityNodeType wrong: {capType}"
assert capTypeNum == "0", f"capType wrong: {capTypeNum}"
assert connected == "1", f"connected flag wrong: {connected}"
print("maroListAxisNodes -capabilities OK")

# --- 존재하지 않는 축 -> 실패(에러) ---
try:
    cmds.maroListAxisNodes(capabilities="doesNotExist123")
    raised = False
except RuntimeError:
    raised = True
assert raised, "maroListAxisNodes -capabilities on a missing node must raise"
print("maroListAxisNodes -capabilities missing-node error OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
```

`tests/CMakeLists.txt:249`의 `foreach(maya_test ...)` 목록에 `axis_editor_commands` 추가(`ros_proxy_sync` 뒤):

```cmake
                      ros_proxy_commands ros_proxy_sync axis_editor_commands)
```

- [ ] Run: `cmake --build out/build --config Release`
- [ ] Run: `ctest --test-dir out/build -C Release -R maya_axis_editor_commands --output-on-failure`
- [ ] Expected: PASS
- [ ] Commit:

```bash
git add src/maro_plugin/MaroAxisEditorCommands.h src/maro_plugin/MaroAxisEditorCommands.cpp \
        src/maro_plugin/CMakeLists.txt src/maro_plugin/MaroPluginMain.cpp \
        tests/CMakeLists.txt tests/maya/test_axis_editor_commands.py
git commit -m "feat: add maroListAxisNodes query command"
```

---

## Task 6: 쓰기 커맨드 4종 (`maroAddCapability`/`maroConnectCapability`/`maroDisconnectCapability`/`maroUnbindAxis`)

**Files:**
- Modify: `src/maro_plugin/MaroAxisEditorCommands.h`
- Modify: `src/maro_plugin/MaroAxisEditorCommands.cpp`
- Modify: `src/maro_plugin/MaroPluginMain.cpp` (등록/해제)
- Test: `tests/maya/test_axis_editor_commands.py`

**Interfaces:**
- Consumes: `nextFreeCapabilitySlot`/`hasPrimaryDriver`(Task 5).
- Produces: `maroAddCapability -type <rotation|translation|limit|translationLimit|sensorDirection|sensorRange|coupling> <axis>`(undoable, `setResult`로 새 노드 이름 반환), `maroConnectCapability <capabilityNode> <axis> [-index <int>]`(undoable), `maroDisconnectCapability <axis> -index <int>`(undoable), `maroUnbindAxis <axis>`(undoable).

### Step 1: `MaroAxisEditorCommands.h`에 4개 클래스 선언 추가

`MaroListAxisNodesCommand` 선언 뒤에 추가:

```cpp
#include <maya/MDGModifier.h>

// ... (namespace maro 안, 기존 선언들 뒤)

class MaroAddCapabilityCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
    MStatus redoIt() override;
    MStatus undoIt() override;
    bool isUndoable() const override { return m_stagedChange; }

private:
    MDGModifier m_modifier;
    bool m_stagedChange = false;
};

class MaroConnectCapabilityCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
    MStatus redoIt() override;
    MStatus undoIt() override;
    bool isUndoable() const override { return m_stagedChange; }

private:
    MDGModifier m_modifier;
    bool m_stagedChange = false;
};

class MaroDisconnectCapabilityCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
    MStatus redoIt() override;
    MStatus undoIt() override;
    bool isUndoable() const override { return m_stagedChange; }

private:
    MDGModifier m_modifier;
    bool m_stagedChange = false;
};

class MaroUnbindAxisCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
    MStatus redoIt() override;
    MStatus undoIt() override;
    bool isUndoable() const override { return m_stagedChange; }

private:
    MDGModifier m_modifier;
    bool m_stagedChange = false;
};
```

### Step 2: `MaroAxisEditorCommands.cpp`에 구현 추가

상단 include에 `#include <maya/MFnCompoundAttribute.h>`는 불필요(compound 자체는 안 만든다), 대신 `MaroCapabilityNodes.h`는 필요 없다(타입 이름 문자열만 쓴다). 파일 끝(`}  // namespace maro` 앞)에 추가:

```cpp
namespace {

// -type 플래그 문자열 <-> 커맨드로 생성 가능한 capability 노드 타입 이름
// 매핑. isPrimaryDriver가 true인 타입만 §3 상호배타 검사 대상이다.
struct CapabilityTypeInfo {
    const char* flagName;
    bool isPrimaryDriver;
};

const CapabilityTypeInfo kCapabilityTypes[] = {
    {"rotation", true},
    {"translation", true},
    {"limit", false},
    {"translationLimit", false},
    {"sensorDirection", false},
    {"sensorRange", false},
    {"coupling", true},
};

const CapabilityTypeInfo* findCapabilityType(const MString& flagValue) {
    for (const auto& info : kCapabilityTypes) {
        if (flagValue == info.flagName) return &info;
    }
    return nullptr;
}

// axisName을 maroAxis 노드로 해석한다. 실패하면 에러를 남기고 kFailure.
MStatus resolveAxis(const MString& axisName, MObject& outAxis) {
    MSelectionList selection;
    if (!selection.add(axisName)) {
        maro::BoadMaro::error(
            "MaroAxisEditorCommands.AxisNotFound",
            MString("Maro: cannot find node '") + axisName + "'.",
            maro::onfix::capture("", "", axisName));
        return MS::kFailure;
    }
    selection.getDependNode(0, outAxis);
    MFnDependencyNode axisFn(outAxis);
    if (axisFn.typeId() != MaroAxisNode::id) {
        maro::BoadMaro::error(
            "MaroAxisEditorCommands.NotMaroAxisNode",
            MString("Maro: '") + axisName + "' is not a maroAxis node.",
            maro::onfix::capture(axisFn.typeName(), "", axisName));
        return MS::kFailure;
    }
    return MS::kSuccess;
}

}  // namespace

// ============================== maroAddCapability ==============================

void* MaroAddCapabilityCommand::creator() { return new MaroAddCapabilityCommand(); }

MSyntax MaroAddCapabilityCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag("-typ", "-type", MSyntax::kString);
    syntax.setObjectType(MSyntax::kSelectionList, 1, 1);
    return syntax;
}

MStatus MaroAddCapabilityCommand::doIt(const MArgList& args) {
    maro::ScopedCommandContext ctxMarker("MaroAddCapabilityCommand");
    try {
        MStatus status;
        MArgDatabase argData(syntax(), args, &status);
        if (!status) return status;

        if (!argData.isFlagSet("-typ")) {
            maro::BoadMaro::error(
                "MaroAddCapabilityCommand.MissingType",
                "Maro: maroAddCapability requires -type <rotation|translation|"
                "limit|translationLimit|sensorDirection|sensorRange|coupling>.",
                maro::onfix::capture("", "", ""));
            return MS::kFailure;
        }
        MString typeName;
        argData.getFlagArgument("-typ", 0, typeName);
        const CapabilityTypeInfo* info = findCapabilityType(typeName);
        if (info == nullptr) {
            maro::BoadMaro::error(
                "MaroAddCapabilityCommand.UnknownType",
                MString("Maro: unknown capability type '") + typeName + "'.",
                maro::onfix::capture("", "", ""));
            return MS::kFailure;
        }

        MSelectionList axisSelection;
        argData.getObjects(axisSelection);
        if (axisSelection.length() != 1) {
            maro::BoadMaro::error(
                "MaroAddCapabilityCommand.WrongArgCount",
                "Maro: maroAddCapability needs exactly one argument: <axis>.",
                maro::onfix::capture("", "", ""));
            return MS::kFailure;
        }
        MObject axisObj;
        axisSelection.getDependNode(0, axisObj);
        MFnDependencyNode axisFn(axisObj);
        if (axisFn.typeId() != MaroAxisNode::id) {
            maro::BoadMaro::error(
                "MaroAddCapabilityCommand.NotMaroAxisNode",
                MString("Maro: '") + axisFn.name() + "' is not a maroAxis node.",
                maro::onfix::capture(axisFn.typeName(), "", axisFn.name()));
            return MS::kFailure;
        }

        MPlug capabilityIn = axisFn.findPlug(MaroAxisNode::aCapabilityIn, false);
        if (info->isPrimaryDriver && hasPrimaryDriver(capabilityIn)) {
            maro::BoadMaro::error(
                "MaroAddCapabilityCommand.PrimaryDriverConflict",
                MString("Maro: '") + axisFn.name() +
                "' already has a primary drive capability (rotation/translation/"
                "coupling). An axis carries exactly one.",
                maro::onfix::capture(axisFn.typeName(), "capabilityIn", axisFn.name()));
            return MS::kFailure;
        }

        const unsigned int slot = nextFreeCapabilitySlot(capabilityIn);
        MObject capNode = m_modifier.createNode(info->flagName, &status);
        if (!status || capNode.isNull()) {
            maro::BoadMaro::error(
                "MaroAddCapabilityCommand.CreateNodeFailed",
                MString("Maro: failed to create a '") + info->flagName + "' node.",
                maro::onfix::capture(info->flagName, "", axisFn.name()));
            return MS::kFailure;
        }
        MFnDependencyNode capFn(capNode);
        MPlug capOut = capFn.findPlug("capabilityOut", false, &status);
        if (!status) return status;
        MPlug capIn = capabilityIn.elementByLogicalIndex(slot);
        status = m_modifier.connect(capOut, capIn);
        if (!status) return status;

        m_capNodeName = capFn.name();
        m_stagedChange = true;
        status = redoIt();
        if (!status) return status;
        setResult(m_capNodeName);
        return MS::kSuccess;
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroAddCapabilityCommand.doIt.Exception",
                              MString("Maro: maroAddCapability failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroAddCapabilityCommand.doIt.UnknownException",
                              "Maro: maroAddCapability failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroAddCapabilityCommand::redoIt() {
    maro::ScopedCommandContext ctxMarker("MaroAddCapabilityCommand");
    try {
        return m_modifier.doIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroAddCapabilityCommand.redoIt.Exception",
                              MString("Maro: maroAddCapability redo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroAddCapabilityCommand.redoIt.UnknownException",
                              "Maro: maroAddCapability redo failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroAddCapabilityCommand::undoIt() {
    maro::ScopedCommandContext ctxMarker("MaroAddCapabilityCommand");
    try {
        return m_modifier.undoIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroAddCapabilityCommand.undoIt.Exception",
                              MString("Maro: maroAddCapability undo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroAddCapabilityCommand.undoIt.UnknownException",
                              "Maro: maroAddCapability undo failed with unknown error.");
        return MS::kFailure;
    }
}
```

**주의**: 위 `doIt()`은 `m_capNodeName`(`MString`)이라는 멤버를 쓴다 — `MaroAxisEditorCommands.h`의 `MaroAddCapabilityCommand` 선언에 `MString m_capNodeName;` private 멤버를 추가한다(위 Step 1 코드에 누락돼 있었다면 여기서 채운다).

이어서 나머지 세 커맨드를 같은 파일에 추가한다:

```cpp
// ============================== maroConnectCapability ==============================

void* MaroConnectCapabilityCommand::creator() { return new MaroConnectCapabilityCommand(); }

MSyntax MaroConnectCapabilityCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag("-idx", "-index", MSyntax::kLong);
    syntax.setObjectType(MSyntax::kSelectionList, 2, 2);
    return syntax;
}

MStatus MaroConnectCapabilityCommand::doIt(const MArgList& args) {
    maro::ScopedCommandContext ctxMarker("MaroConnectCapabilityCommand");
    try {
        MStatus status;
        MArgDatabase argData(syntax(), args, &status);
        if (!status) return status;

        MSelectionList selection;
        argData.getObjects(selection);
        if (selection.length() != 2) {
            maro::BoadMaro::error(
                "MaroConnectCapabilityCommand.WrongArgCount",
                "Maro: maroConnectCapability needs exactly two arguments: "
                "<capabilityNode> <axis>.",
                maro::onfix::capture("", "", ""));
            return MS::kFailure;
        }
        MObject capNode, axisObj;
        selection.getDependNode(0, capNode);
        selection.getDependNode(1, axisObj);

        MFnDependencyNode axisFn(axisObj);
        if (axisFn.typeId() != MaroAxisNode::id) {
            maro::BoadMaro::error(
                "MaroConnectCapabilityCommand.NotMaroAxisNode",
                MString("Maro: '") + axisFn.name() + "' is not a maroAxis node.",
                maro::onfix::capture(axisFn.typeName(), "", axisFn.name()));
            return MS::kFailure;
        }

        MFnDependencyNode capFn(capNode);
        const CapabilityTypeInfo* info = findCapabilityType(capFn.typeName());
        if (info == nullptr) {
            maro::BoadMaro::error(
                "MaroConnectCapabilityCommand.NotCapabilityNode",
                MString("Maro: '") + capFn.name() + "' is not a capability node type.",
                maro::onfix::capture(capFn.typeName(), "", axisFn.name()));
            return MS::kFailure;
        }
        MPlug capOut = capFn.findPlug("capabilityOut", false, &status);
        if (!status) return status;
        MPlugArray existingDest;
        capOut.connectedTo(existingDest, false, true);
        if (existingDest.length() > 0) {
            maro::RemedyAction remedy;
            remedy.kind = maro::RemedyActionKind::Disconnect;
            remedy.sourcePlug = capOut.name().asChar();
            remedy.destPlug = existingDest[0].name().asChar();
            maro::BoadMaro::error(
                "MaroConnectCapabilityCommand.AlreadyConnected",
                MString("Maro: '") + capFn.name() +
                "' is already connected to another axis. Disconnect it first.",
                maro::onfix::capture(capFn.typeName(), "", axisFn.name()), remedy);
            return MS::kFailure;
        }

        MPlug capabilityIn = axisFn.findPlug(MaroAxisNode::aCapabilityIn, false);
        if (info->isPrimaryDriver && hasPrimaryDriver(capabilityIn)) {
            maro::BoadMaro::error(
                "MaroConnectCapabilityCommand.PrimaryDriverConflict",
                MString("Maro: '") + axisFn.name() +
                "' already has a primary drive capability. An axis carries exactly one.",
                maro::onfix::capture(axisFn.typeName(), "capabilityIn", axisFn.name()));
            return MS::kFailure;
        }

        unsigned int slot;
        if (argData.isFlagSet("-idx")) {
            int requested = 0;
            argData.getFlagArgument("-idx", 0, requested);
            if (requested < 0) {
                maro::BoadMaro::error(
                    "MaroConnectCapabilityCommand.NegativeIndex",
                    "Maro: -index must not be negative.",
                    maro::onfix::capture(axisFn.typeName(), "capabilityIn", axisFn.name()));
                return MS::kFailure;
            }
            slot = static_cast<unsigned int>(requested);
            MPlugArray occupiedCheck;
            capabilityIn.elementByLogicalIndex(slot).connectedTo(occupiedCheck, true, false);
            if (occupiedCheck.length() > 0) {
                maro::BoadMaro::error(
                    "MaroConnectCapabilityCommand.IndexOccupied",
                    MString("Maro: capabilityIn[") + static_cast<int>(slot) +
                    "] is already occupied.",
                    maro::onfix::capture(axisFn.typeName(), "capabilityIn", axisFn.name()));
                return MS::kFailure;
            }
        } else {
            slot = nextFreeCapabilitySlot(capabilityIn);
        }

        status = m_modifier.connect(capOut, capabilityIn.elementByLogicalIndex(slot));
        if (!status) return status;

        m_stagedChange = true;
        return redoIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroConnectCapabilityCommand.doIt.Exception",
                              MString("Maro: maroConnectCapability failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroConnectCapabilityCommand.doIt.UnknownException",
                              "Maro: maroConnectCapability failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroConnectCapabilityCommand::redoIt() {
    maro::ScopedCommandContext ctxMarker("MaroConnectCapabilityCommand");
    try {
        return m_modifier.doIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroConnectCapabilityCommand.redoIt.Exception",
                              MString("Maro: maroConnectCapability redo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroConnectCapabilityCommand.redoIt.UnknownException",
                              "Maro: maroConnectCapability redo failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroConnectCapabilityCommand::undoIt() {
    maro::ScopedCommandContext ctxMarker("MaroConnectCapabilityCommand");
    try {
        return m_modifier.undoIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroConnectCapabilityCommand.undoIt.Exception",
                              MString("Maro: maroConnectCapability undo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroConnectCapabilityCommand.undoIt.UnknownException",
                              "Maro: maroConnectCapability undo failed with unknown error.");
        return MS::kFailure;
    }
}

// ============================== maroDisconnectCapability ==============================

void* MaroDisconnectCapabilityCommand::creator() { return new MaroDisconnectCapabilityCommand(); }

MSyntax MaroDisconnectCapabilityCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag("-idx", "-index", MSyntax::kLong);
    syntax.setObjectType(MSyntax::kSelectionList, 1, 1);
    return syntax;
}

MStatus MaroDisconnectCapabilityCommand::doIt(const MArgList& args) {
    maro::ScopedCommandContext ctxMarker("MaroDisconnectCapabilityCommand");
    try {
        MStatus status;
        MArgDatabase argData(syntax(), args, &status);
        if (!status) return status;

        if (!argData.isFlagSet("-idx")) {
            maro::BoadMaro::error(
                "MaroDisconnectCapabilityCommand.MissingIndex",
                "Maro: maroDisconnectCapability requires -index <int>.",
                maro::onfix::capture("", "", ""));
            return MS::kFailure;
        }

        MSelectionList selection;
        argData.getObjects(selection);
        MObject axisObj;
        MStatus axisStatus;
        MFnDependencyNode axisFn;
        {
            selection.getDependNode(0, axisObj);
            axisStatus = resolveAxis(MFnDependencyNode(axisObj).name(), axisObj);
        }
        if (!axisStatus) return axisStatus;
        axisFn.setObject(axisObj);

        int index = 0;
        argData.getFlagArgument("-idx", 0, index);
        if (index < 0) {
            maro::BoadMaro::error(
                "MaroDisconnectCapabilityCommand.NegativeIndex",
                "Maro: -index must not be negative.",
                maro::onfix::capture(axisFn.typeName(), "capabilityIn", axisFn.name()));
            return MS::kFailure;
        }

        MPlug capabilityIn = axisFn.findPlug(MaroAxisNode::aCapabilityIn, false);
        MPlug element = capabilityIn.elementByLogicalIndex(static_cast<unsigned int>(index));
        MPlugArray sources;
        element.connectedTo(sources, true, false);
        if (sources.length() == 0) {
            maro::BoadMaro::error(
                "MaroDisconnectCapabilityCommand.NotConnected",
                MString("Maro: capabilityIn[") + index + "] is not connected.",
                maro::onfix::capture(axisFn.typeName(), "capabilityIn", axisFn.name()));
            return MS::kFailure;
        }

        status = m_modifier.disconnect(sources[0], element);
        if (!status) return status;

        m_stagedChange = true;
        return redoIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroDisconnectCapabilityCommand.doIt.Exception",
                              MString("Maro: maroDisconnectCapability failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroDisconnectCapabilityCommand.doIt.UnknownException",
                              "Maro: maroDisconnectCapability failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroDisconnectCapabilityCommand::redoIt() {
    maro::ScopedCommandContext ctxMarker("MaroDisconnectCapabilityCommand");
    try {
        return m_modifier.doIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroDisconnectCapabilityCommand.redoIt.Exception",
                              MString("Maro: maroDisconnectCapability redo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroDisconnectCapabilityCommand.redoIt.UnknownException",
                              "Maro: maroDisconnectCapability redo failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroDisconnectCapabilityCommand::undoIt() {
    maro::ScopedCommandContext ctxMarker("MaroDisconnectCapabilityCommand");
    try {
        return m_modifier.undoIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroDisconnectCapabilityCommand.undoIt.Exception",
                              MString("Maro: maroDisconnectCapability undo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroDisconnectCapabilityCommand.undoIt.UnknownException",
                              "Maro: maroDisconnectCapability undo failed with unknown error.");
        return MS::kFailure;
    }
}

// ============================== maroUnbindAxis ==============================

void* MaroUnbindAxisCommand::creator() { return new MaroUnbindAxisCommand(); }

MSyntax MaroUnbindAxisCommand::newSyntax() {
    MSyntax syntax;
    syntax.setObjectType(MSyntax::kSelectionList, 1, 1);
    return syntax;
}

MStatus MaroUnbindAxisCommand::doIt(const MArgList& args) {
    maro::ScopedCommandContext ctxMarker("MaroUnbindAxisCommand");
    try {
        MStatus status;
        MSelectionList selection;
        for (unsigned int i = 0; i < args.length(); ++i) {
            MString name = args.asString(i, &status);
            if (!status) return status;
            if (!selection.add(name)) {
                maro::BoadMaro::error(
                    "MaroUnbindAxisCommand.NodeNotFound",
                    MString("Maro: cannot find node '") + name + "'.",
                    maro::onfix::capture("", "", name));
                return MS::kFailure;
            }
        }
        if (selection.length() != 1) {
            maro::BoadMaro::error(
                "MaroUnbindAxisCommand.WrongArgCount",
                "Maro: maroUnbindAxis needs exactly one argument: <axis>.",
                maro::onfix::capture("", "", ""));
            return MS::kFailure;
        }

        MObject axisObj;
        selection.getDependNode(0, axisObj);
        MFnDependencyNode axisFn(axisObj);
        if (axisFn.typeId() != MaroAxisNode::id) {
            maro::BoadMaro::error(
                "MaroUnbindAxisCommand.NotMaroAxisNode",
                MString("Maro: '") + axisFn.name() + "' is not a maroAxis node.",
                maro::onfix::capture(axisFn.typeName(), "", axisFn.name()));
            return MS::kFailure;
        }

        MPlug axisTarget = axisFn.findPlug(MaroAxisNode::aTargetObject, false);
        MPlugArray sources;
        axisTarget.connectedTo(sources, true, false);
        if (sources.length() == 0) {
            maro::BoadMaro::error(
                "MaroUnbindAxisCommand.NotBound",
                MString("Maro: '") + axisFn.name() + "' is not bound to anything.",
                maro::onfix::capture(axisFn.typeName(), "targetObject", axisFn.name()));
            return MS::kFailure;
        }

        status = m_modifier.disconnect(sources[0], axisTarget);
        if (!status) return status;

        m_stagedChange = true;
        return redoIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroUnbindAxisCommand.doIt.Exception",
                              MString("Maro: maroUnbindAxis failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroUnbindAxisCommand.doIt.UnknownException",
                              "Maro: maroUnbindAxis failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroUnbindAxisCommand::redoIt() {
    maro::ScopedCommandContext ctxMarker("MaroUnbindAxisCommand");
    try {
        return m_modifier.doIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroUnbindAxisCommand.redoIt.Exception",
                              MString("Maro: maroUnbindAxis redo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroUnbindAxisCommand.redoIt.UnknownException",
                              "Maro: maroUnbindAxis redo failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroUnbindAxisCommand::undoIt() {
    maro::ScopedCommandContext ctxMarker("MaroUnbindAxisCommand");
    try {
        return m_modifier.undoIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroUnbindAxisCommand.undoIt.Exception",
                              MString("Maro: maroUnbindAxis undo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroUnbindAxisCommand.undoIt.UnknownException",
                              "Maro: maroUnbindAxis undo failed with unknown error.");
        return MS::kFailure;
    }
}
```

**주의(`MaroDisconnectCapabilityCommand::doIt` 안의 축 인자 파싱)**: `MArgDatabase::getObjects`는 `MSyntax::kSelectionList` 오브젝트 인자를 이미 `MSelectionList`로 준다 — 위 코드의 `resolveAxis(MFnDependencyNode(axisObj).name(), axisObj)` 재해석은 불필요하게 복잡하다. 실제 구현 시 아래처럼 단순화한다(리뷰에서 이 단순화를 반드시 확인):

```cpp
        MSelectionList selection;
        argData.getObjects(selection);
        MObject axisObj;
        selection.getDependNode(0, axisObj);
        MFnDependencyNode axisFn(axisObj);
        if (axisFn.typeId() != MaroAxisNode::id) {
            maro::BoadMaro::error(
                "MaroDisconnectCapabilityCommand.NotMaroAxisNode",
                MString("Maro: '") + axisFn.name() + "' is not a maroAxis node.",
                maro::onfix::capture(axisFn.typeName(), "", axisFn.name()));
            return MS::kFailure;
        }
```

(이 블록이 위 doIt 초안의 `{ selection.getDependNode(...); axisStatus = resolveAxis(...); }` 부분을 대체한다. `resolveAxis` 헬퍼는 `MaroConnectCapabilityCommand`가 안 쓰므로 실제로는 이 커맨드가 유일한 잠재 사용처였는데, 위 단순화로 아예 안 쓰이게 됐다 — `resolveAxis`를 헤더/무명 네임스페이스에서 제거해도 된다. YAGNI.)

### Step 3: `MaroAxisEditorCommands.h`/`.cpp`에서 `resolveAxis`/`MDGModifier` include 정리

Step 2의 "주의" 반영 후 `resolveAxis` 무명 함수는 미사용이 되므로 삭제한다. `MaroAxisEditorCommands.h` 상단에 `#include <maya/MDGModifier.h>`가 있는지 확인(Step 1에서 추가).

### Step 4: `MaroPluginMain.cpp`에 4개 커맨드 등록/해제

`maroListAxisNodes` 등록(Task 5) 바로 뒤에 추가:

```cpp
    status = plugin.registerCommand("maroAddCapability",
                                    maro::MaroAddCapabilityCommand::creator,
                                    maro::MaroAddCapabilityCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroAddCapability");
        return status;
    }

    status = plugin.registerCommand("maroConnectCapability",
                                    maro::MaroConnectCapabilityCommand::creator,
                                    maro::MaroConnectCapabilityCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroConnectCapability");
        return status;
    }

    status = plugin.registerCommand("maroDisconnectCapability",
                                    maro::MaroDisconnectCapabilityCommand::creator,
                                    maro::MaroDisconnectCapabilityCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroDisconnectCapability");
        return status;
    }

    status = plugin.registerCommand("maroUnbindAxis",
                                    maro::MaroUnbindAxisCommand::creator,
                                    maro::MaroUnbindAxisCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroUnbindAxis");
        return status;
    }
```

해제 블록에서 `plugin.deregisterCommand("maroListAxisNodes");`(Task 5) **앞**에 역순으로 삽입:

```cpp
        plugin.deregisterCommand("maroUnbindAxis");
        plugin.deregisterCommand("maroDisconnectCapability");
        plugin.deregisterCommand("maroConnectCapability");
        plugin.deregisterCommand("maroAddCapability");
        plugin.deregisterCommand("maroListAxisNodes");
```

### Step 5: 테스트 추가 (`tests/maya/test_axis_editor_commands.py`)

`teardown` 직전에 추가:

```python
# --- maroAddCapability ---
axisAdd = cmds.createNode("maroAxis", name="addAxis1")
newRot = cmds.maroAddCapability(axisAdd, type="rotation")[0]
assert cmds.nodeType(newRot) == "maroRotation", f"maroAddCapability must create the requested type, got {cmds.nodeType(newRot)}"
caps = cmds.maroListAxisNodes(capabilities=axisAdd)
assert len(caps) // CAPABILITY_FIELDS == 1, "maroAddCapability must connect the new node"
cmds.undo()
caps = cmds.maroListAxisNodes(capabilities=axisAdd)
assert len(caps) == 0 or all(c == "" for c in caps[1:3]), \
    "undo of maroAddCapability must remove the connection"
assert not cmds.objExists(newRot), "undo of maroAddCapability must remove the created node too"
print("maroAddCapability + undo OK")

cmds.maroAddCapability(axisAdd, type="rotation")
try:
    cmds.maroAddCapability(axisAdd, type="translation")
    raised = False
except RuntimeError:
    raised = True
assert raised, "adding a second primary-driver type must be rejected (§3 mutual exclusivity)"
print("maroAddCapability mutual-exclusivity rejection OK")

try:
    cmds.maroAddCapability(axisAdd, type="bogusType")
    raised = False
except RuntimeError:
    raised = True
assert raised, "maroAddCapability with an unknown -type must fail"
print("maroAddCapability unknown-type rejection OK")

# --- maroConnectCapability ---
axisConn = cmds.createNode("maroAxis", name="connAxis1")
freeRot = cmds.createNode("maroRotation", name="connRot1")
cmds.maroConnectCapability(freeRot, axisConn)
caps = cmds.maroListAxisNodes(capabilities=axisConn)
assert caps[1].endswith("connRot1"), "maroConnectCapability must connect the given node"
cmds.undo()
caps = cmds.maroListAxisNodes(capabilities=axisConn)
assert len(caps) == 0 or caps[4] == "0", "undo of maroConnectCapability must disconnect"
print("maroConnectCapability + undo OK")

cmds.maroConnectCapability(freeRot, axisConn)
freeRot2 = cmds.createNode("maroRotation", name="connRot2")
try:
    cmds.maroConnectCapability(freeRot2, axisConn)
    raised = False
except RuntimeError:
    raised = True
assert raised, "connecting a second primary-driver type must be rejected"
print("maroConnectCapability mutual-exclusivity rejection OK")

alreadyBound = cmds.createNode("maroAxis", name="connAxis2")
try:
    cmds.maroConnectCapability(freeRot, alreadyBound)
    raised = False
except RuntimeError:
    raised = True
assert raised, "connecting a capability node that's already connected elsewhere must be rejected"
print("maroConnectCapability already-connected rejection OK")

# --- maroDisconnectCapability ---
cmds.maroDisconnectCapability(axisConn, index=0)
caps = cmds.maroListAxisNodes(capabilities=axisConn)
assert caps[4] == "0", "maroDisconnectCapability must leave the slot disconnected"
cmds.undo()
caps = cmds.maroListAxisNodes(capabilities=axisConn)
assert caps[4] == "1", "undo of maroDisconnectCapability must restore the connection"
print("maroDisconnectCapability + undo OK")

try:
    cmds.maroDisconnectCapability(axisConn, index=99)
    raised = False
except RuntimeError:
    raised = True
assert raised, "disconnecting an unoccupied index must fail"
print("maroDisconnectCapability not-connected rejection OK")

# --- maroUnbindAxis ---
axisUnbind = cmds.createNode("maroAxis", name="unbindAxis1")
cubeUnbind = cmds.polyCube(name="unbindCube1")[0]
cmds.maroBindAxis(axisUnbind, cubeUnbind)
cmds.maroUnbindAxis(axisUnbind)
rows = cmds.maroListAxisNodes()
for i in range(len(rows) // AXIS_FIELDS):
    f = rows[i * AXIS_FIELDS:(i + 1) * AXIS_FIELDS]
    if f[0].endswith("unbindAxis1"):
        assert f[2] == "", f"maroUnbindAxis must clear boundTargetPath (got {f[2]})"
        break
cmds.undo()
rows = cmds.maroListAxisNodes()
for i in range(len(rows) // AXIS_FIELDS):
    f = rows[i * AXIS_FIELDS:(i + 1) * AXIS_FIELDS]
    if f[0].endswith("unbindAxis1"):
        assert f[2].endswith("unbindCube1"), "undo of maroUnbindAxis must restore the binding"
        break
print("maroUnbindAxis + undo OK")

try:
    cmds.maroUnbindAxis(axisUnbind)  # 이미 위 undo로 복구됐다가 다시 unbind 안 한 상태 -- 실제로는 bound 상태
    cmds.maroUnbindAxis(axisUnbind)  # 두 번째 호출은 이미 unbind됨 -> 실패해야 함
    raised = False
except RuntimeError:
    raised = True
assert raised, "maroUnbindAxis on an already-unbound axis must fail"
print("maroUnbindAxis not-bound rejection OK")
```

- [ ] Run: `cmake --build out/build --config Release`
- [ ] Run: `ctest --test-dir out/build -C Release -R maya_axis_editor_commands --output-on-failure`
- [ ] Expected: PASS(Task 5 단언 + 위 전부)
- [ ] Commit:

```bash
git add src/maro_plugin/MaroAxisEditorCommands.h src/maro_plugin/MaroAxisEditorCommands.cpp \
        src/maro_plugin/MaroPluginMain.cpp tests/maya/test_axis_editor_commands.py
git commit -m "feat: add maroAddCapability/maroConnectCapability/maroDisconnectCapability/maroUnbindAxis"
```

---

## Task 7: `maroAxisPanel.py` + 메인 윈도우 레이아웃 재구성 + `teardown()`

**Files:**
- Create: `python/maroAxisPanel.py`
- Modify: `python/maroMainWindow.py`
- Modify: `src/maro_plugin/CMakeLists.txt`(Python 모듈 스테이징 목록)
- Modify: `src/maro_plugin/MaroPluginMain.cpp`(`teardown()` 호출로 교체)
- Test: `tests/maya/test_axis_panel.py`(신규, 순수 함수만), `tests/CMakeLists.txt`

**Interfaces:**
- Consumes: `cmds.maroListAxisNodes()`/`maroListAxisNodes(capabilities=...)`(Task 5), `cmds.maroAddCapability`/`maroConnectCapability`/`maroDisconnectCapability`/`maroUnbindAxis`(Task 6).
- Produces: `maroAxisPanel.sliceAxisRows(flat)`, `maroAxisPanel.sliceCapabilityRows(flat)`(순수 함수, Task 9가 재사용), `maroAxisPanel.buildWidget()`(QWidget 반환), `maroAxisPanel.AXIS_FIELDS=8`, `maroAxisPanel.CAPABILITY_FIELDS=5`.

### Step 1: `python/maroAxisPanel.py` (신규)

```python
"""Maro 축/capability 에디터 패널 -- Maro Main UI의 editorHost에 임베드된다.

패널은 자체 상태를 갖지 않는다(maroDiagPanel.py와 같은 원칙, 설계 스펙
§9): 씬의 maroAxis/capability 노드가 유일한 진실이고, 이 모듈은
maroListAxisNodes가 돌려준 것을 그리고, 버튼 클릭을 커맨드 호출로
옮기기만 한다.

평탄한 배열을 행으로 되돌리는 부분은 UI를 만들지 않는 순수 함수로 분리해
뒀다 -- mayapy 배치 모드에는 UI가 없어 위젯은 만들 수 없지만 이 부분은
자동 검증된다(maroDiagPanel.py의 sliceRows와 같은 이유).
"""
import maya.cmds as cmds
from PySide6 import QtWidgets

# C++ 쪽 계약. 바뀌면 양쪽을 함께 고쳐야 한다(MaroAxisEditorCommands.cpp 참고).
AXIS_FIELDS = 8
CAPABILITY_FIELDS = 5

# maroAddCapability -type/버튼 라벨 쌍. 순서가 패널의 버튼 순서다.
CAPABILITY_TYPES = [
    ("rotation", "+Rotation"),
    ("translation", "+Translation"),
    ("limit", "+Limit"),
    ("translationLimit", "+TranslationLimit"),
    ("sensorDirection", "+SensorDirection"),
    ("sensorRange", "+SensorRange"),
    ("coupling", "+Coupling"),
]


def sliceAxisRows(flat):
    """maroListAxisNodes()의 평탄한 배열을 축 행 딕셔너리 목록으로 되돌린다."""
    if flat is None:
        return []
    if len(flat) % AXIS_FIELDS != 0:
        raise ValueError(
            "axis row array length {} is not a multiple of {}".format(
                len(flat), AXIS_FIELDS))
    rows = []
    for i in range(len(flat) // AXIS_FIELDS):
        f = flat[i * AXIS_FIELDS:(i + 1) * AXIS_FIELDS]
        rows.append({
            "axisFullPath": f[0],
            "jointName": f[1],
            "boundTargetPath": f[2],
            "parentAxisPath": f[3],
            "controlMode": int(f[4]),
            "enabled": f[5] == "1",
            "conventionAxis": int(f[6]),
            "capabilityCount": int(f[7]),
        })
    return rows


def sliceCapabilityRows(flat):
    """maroListAxisNodes(capabilities=axis)의 평탄한 배열을 capability 행
    딕셔너리 목록으로 되돌린다."""
    if flat is None:
        return []
    if len(flat) % CAPABILITY_FIELDS != 0:
        raise ValueError(
            "capability row array length {} is not a multiple of {}".format(
                len(flat), CAPABILITY_FIELDS))
    rows = []
    for i in range(len(flat) // CAPABILITY_FIELDS):
        f = flat[i * CAPABILITY_FIELDS:(i + 1) * CAPABILITY_FIELDS]
        rows.append({
            "logicalIndex": int(f[0]),
            "capabilityNodeName": f[1],
            "capabilityNodeType": f[2],
            "capType": int(f[3]),
            "connected": f[4] == "1",
        })
    return rows


class AxisPanel(QtWidgets.QWidget):
    """축 목록 + 선택된 축의 capability 스택 + 추가/삭제 버튼.

    setStyleSheet()를 부르지 않는다 -- maroMainWindow.py와 같은 규율
    (설계 스펙 §4.2, tests/maya/test_main_window.py가 grep으로 검사).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selectedAxis = None

        layout = QtWidgets.QHBoxLayout(self)

        axisColumn = QtWidgets.QVBoxLayout()
        self._axisList = QtWidgets.QListWidget()
        self._axisList.setObjectName("maroAxisPanelAxisList")
        self._axisList.itemClicked.connect(self._onAxisRowClicked)
        axisColumn.addWidget(self._axisList)
        self._unbindButton = QtWidgets.QPushButton("Unbind")
        self._unbindButton.setObjectName("maroAxisPanelUnbindButton")
        self._unbindButton.clicked.connect(self._onUnbindClicked)
        axisColumn.addWidget(self._unbindButton)
        layout.addLayout(axisColumn)

        capColumn = QtWidgets.QVBoxLayout()
        self._capList = QtWidgets.QListWidget()
        self._capList.setObjectName("maroAxisPanelCapabilityList")
        capColumn.addWidget(self._capList)

        buttonRow = QtWidgets.QHBoxLayout()
        for typeName, label in CAPABILITY_TYPES:
            button = QtWidgets.QPushButton(label)
            button.setObjectName("maroAxisPanelAdd_" + typeName)
            button.clicked.connect(
                lambda checked=False, t=typeName: self._onAddCapabilityClicked(t))
            buttonRow.addWidget(button)
        capColumn.addLayout(buttonRow)

        self._removeButton = QtWidgets.QPushButton("Remove Selected Capability")
        self._removeButton.setObjectName("maroAxisPanelRemoveCapabilityButton")
        self._removeButton.clicked.connect(self._onRemoveCapabilityClicked)
        capColumn.addWidget(self._removeButton)

        layout.addLayout(capColumn)

        self.refreshAxisList()

    def refreshAxisList(self):
        """씬의 maroAxis 전체를 다시 읽어 왼쪽 목록을 채운다."""
        self._axisList.clear()
        for row in sliceAxisRows(cmds.maroListAxisNodes()):
            item = QtWidgets.QListWidgetItem(
                "{} ({})".format(row["axisFullPath"], row["jointName"] or "-"))
            item.setData(1, row["axisFullPath"])
            self._axisList.addItem(item)

    def selectAxis(self, axisFullPath):
        """다른 곳(씬 선택 등)에서 축이 정해졌을 때 패널을 그 축에 맞춘다.
        Task 9의 SelectionChanged 동기화가 이걸 부른다."""
        self._selectedAxis = axisFullPath
        self._refreshCapabilityList()

    def _refreshCapabilityList(self):
        self._capList.clear()
        if not self._selectedAxis or not cmds.objExists(self._selectedAxis):
            return
        for row in sliceCapabilityRows(
                cmds.maroListAxisNodes(capabilities=self._selectedAxis)):
            item = QtWidgets.QListWidgetItem(
                "[{}] {} ({})".format(
                    row["logicalIndex"], row["capabilityNodeType"],
                    row["capabilityNodeName"] or "disconnected"))
            item.setData(1, row["logicalIndex"])
            self._capList.addItem(item)

    def _onAxisRowClicked(self, item):
        axisFullPath = item.data(1)
        self._selectedAxis = axisFullPath
        self._refreshCapabilityList()
        # 양방향 동기화(설계 스펙 §9): 패널에서 축을 고르면 씬 선택도 바꾼다.
        # 바인딩된 타겟이 있으면 그것을, 없으면 축 자신을 선택한다.
        rows = [r for r in sliceAxisRows(cmds.maroListAxisNodes())
                if r["axisFullPath"] == axisFullPath]
        target = rows[0]["boundTargetPath"] if rows and rows[0]["boundTargetPath"] else axisFullPath
        cmds.select(target, replace=True)

    def _onAddCapabilityClicked(self, typeName):
        if not self._selectedAxis:
            return
        try:
            cmds.maroAddCapability(self._selectedAxis, type=typeName)
        except RuntimeError as error:
            print("Maro: maroAddCapability failed -- {}".format(error))
            return
        self.refreshAxisList()
        self._refreshCapabilityList()

    def _onRemoveCapabilityClicked(self):
        if not self._selectedAxis:
            return
        item = self._capList.currentItem()
        if item is None:
            return
        try:
            cmds.maroDisconnectCapability(self._selectedAxis, index=item.data(1))
        except RuntimeError as error:
            print("Maro: maroDisconnectCapability failed -- {}".format(error))
            return
        self.refreshAxisList()
        self._refreshCapabilityList()

    def _onUnbindClicked(self):
        if not self._selectedAxis:
            return
        try:
            cmds.maroUnbindAxis(self._selectedAxis)
        except RuntimeError as error:
            print("Maro: maroUnbindAxis failed -- {}".format(error))
            return
        self.refreshAxisList()


def buildWidget():
    """maroMainWindow.buildUI()가 editorHost에 임베드할 위젯을 만든다."""
    return AxisPanel()
```

### Step 2: `python/maroMainWindow.py` 수정

`buildUI()`(현재 `:132-229`)의 뷰포트 조립 부분(`:142-152`)을 아래로 교체:

```python
    form = cmds.formLayout()

    outerPane = cmds.paneLayout(configuration="vertical2", parent=form)
    viewportPane = cmds.paneLayout(configuration="vertical2", parent=outerPane)
    # 두 호출의 반환값(각 패널의 control 이름)은 여기서 안 쓴다. Phase 3의
    # 격리/동기화는 control 이름이 아니라 **패널 이름**을 쓰기 때문이다.
    _buildLabeledViewport(viewportPane, "Maya", VIEWPORT_NAME_MAYA)
    _buildLabeledViewport(viewportPane, "ROS", VIEWPORT_NAME_ROS)

    # Phase 4: 축/capability 에디터 패널. modelPanel이 아닌 평범한
    # formLayout이라(_buildLabeledViewport의 modelPanel과 달리) 전역 패널
    # 레지스트리에 등록되지 않는다 -- 부모(outerPane/form)가 사라지면 이
    # 레이아웃도 함께 완전히 사라진다. 그래서 _deleteStalePanel 같은 잔여물
    # 정리가 필요 없다.
    editorHost = cmds.formLayout(EDITOR_HOST_NAME, parent=outerPane)
```

`aOutValue` 등 상수 블록(`:41-43`)에 `EDITOR_HOST_NAME` 추가:

```python
CONTROL_NAME = "maroMainWindowControl"
VIEWPORT_NAME_MAYA = "maroMainWindowViewportMaya"
VIEWPORT_NAME_ROS = "maroMainWindowViewportRos"
EDITOR_HOST_NAME = "maroMainWindowEditorHost"
```

테스트 버튼 임베드 블록(`:154-185`) 뒤, `formLayout` attach(`:194-207`) **앞**에 `maroAxisPanel` 위젯 임베드를 추가한다:

```python
    # Phase 4: maroAxisPanel을 editorHost에 임베드한다 -- 테스트 버튼과
    # 완전히 같은 두 단계(MQtUtil.findLayout -> addWidgetToMayaLayout)를
    # 재사용한다. import는 함수 안에서 한다(테스트 버튼 임베드 위
    # maroRosProxy import와 같은 이유 -- 이 모듈의 import 시점과
    # maroAxisPanel이 필요한 시점을 떼어 놓는다).
    import maroAxisPanel
    axisPanelWidget = maroAxisPanel.buildWidget()

    editorHostLayoutPtr = omui.MQtUtil.findLayout(
        cmds.control(editorHost, query=True, fullPathName=True))
    if editorHostLayoutPtr is None:
        raise RuntimeError(
            "maroMainWindow: MQtUtil.findLayout() could not resolve editorHost "
            "{!r} -- cannot embed the axis panel widget.".format(editorHost))
    axisPanelName = omui.MQtUtil.addWidgetToMayaLayout(
        int(shiboken6.getCppPointer(axisPanelWidget)[0]), int(editorHostLayoutPtr))
    if not axisPanelName:
        raise RuntimeError(
            "maroMainWindow: MQtUtil.addWidgetToMayaLayout() returned no UI name "
            "for the axis panel.")
    _EMBEDDED[EDITOR_HOST_NAME] = axisPanelWidget
    cmds.formLayout(
        editorHost, edit=True,
        attachForm=[
            (axisPanelName, "top", 0), (axisPanelName, "left", 0),
            (axisPanelName, "right", 0), (axisPanelName, "bottom", 0),
        ])
```

`formLayout` attach 블록(`:194-207`)의 `pane`을 `outerPane`으로 교체:

```python
    try:
        cmds.formLayout(
            form, edit=True,
            attachForm=[
                (buttonName, "top", 4), (buttonName, "left", 4), (buttonName, "right", 4),
                (outerPane, "left", 0), (outerPane, "right", 0), (outerPane, "bottom", 0),
            ],
            attachControl=[(outerPane, "top", 4, buttonName)])
    except RuntimeError as error:
        raise RuntimeError(
            "maroMainWindow: the native formLayout refused to lay out the "
            "embedded widget ({!r}) next to the dual-viewport pane ({!r}): {} "
            "-- see docs/maro-main-ui-manual-checklist.md".format(
                buttonName, outerPane, error))
```

`maroRosProxy.start(...)` 호출(`:226-227`) 뒤에 `teardown()` 함수를 새로 정의하고 `show()`가 그걸 가리키게 한다. 파일 끝(`show()` 함수)을 아래로 교체:

```python
def teardown():
    """모든 서브시스템의 stop()을 한 곳에서 부른다.

    closeCommand(문자열)와 MaroPluginMain.cpp의 언로드 경로가 각각 이걸
    가리킨다 -- 서브시스템이 늘 때마다(Phase 3의 maroRosProxy, 이번의
    SelectionChanged job) 두 곳을 따로 늘리지 않기 위해서다. 여기서
    부르는 stop()들은 전부 start()가 한 번도 안 불렸어도 안전한
    무동작이어야 한다(maroRosProxy.stop()이 이미 그렇다).
    """
    try:
        import maroRosProxy
        maroRosProxy.stop()
    except Exception:  # noqa: BLE001 -- Maya 콜백/언로드 경계
        import traceback
        traceback.print_exc()


def show():
    """maroMainWindow 커맨드가 부른다."""
    if cmds.workspaceControl(CONTROL_NAME, exists=True):
        cmds.workspaceControl(CONTROL_NAME, edit=True, restore=True)
        return
    cmds.workspaceControl(
        CONTROL_NAME,
        label="Maro",
        retain=False,
        floating=True,
        initialWidth=900,
        initialHeight=600,
        requiredPlugin="maro",
        closeCommand="import maroMainWindow; maroMainWindow.teardown()",
        uiScript="import maroMainWindow; maroMainWindow.buildUI()")
```

**주의**: Task 9가 `teardown()`에 `SelectionChanged` job의 `stop()` 호출을 추가한다 — 지금은 `maroRosProxy.stop()` 하나만 옮긴다(기존 동작 무변경, 리팩터일 뿐). `MaroPluginMain.cpp`의 `runPluginPythonModule("maroRosProxy", "maroRosProxy.stop()")` 호출(`:476` 근처)도 `runPluginPythonModule("maroMainWindow", "maroMainWindow.teardown()")`로 교체한다 — 주석(`:474-476`)이 설명하는 "closeCommand가 안 뛸 경우의 이중 안전장치"라는 성격은 그대로 유지된다.

### Step 3: `CMakeLists.txt` 배선

`src/maro_plugin/CMakeLists.txt`의 Python 모듈 스테이징 목록(`maroMainWindow.py`/`maroRosProxy.py`가 이미 있는 곳 — Task 정황상 `MARO_PLUGIN_PY_MODULES` 같은 변수)에 `maroAxisPanel.py`를 추가한다. 정확한 변수/블록 이름은 파일을 열어 기존 두 파일이 어디 나열돼 있는지 확인하고 같은 목록에 추가한다(빌드 로그의 "Copying maroMainWindow.py next to the plug-in" 메시지를 내는 바로 그 목록).

### Step 4: 테스트 (`tests/maya/test_axis_panel.py`, 신규 — 순수 함수만)

```python
"""maroAxisPanel의 순수 함수(sliceAxisRows/sliceCapabilityRows)만 검증한다.
QWidget 생성은 배치 모드에서 프로세스를 abort시키므로(모듈 도크스트링
참고) 여기서 AxisPanel/buildWidget은 절대 부르지 않는다."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "python"))

import maroAxisPanel  # noqa: E402

# --- sliceAxisRows ---
flat = ["|g|axis1", "shoulder", "|g|cube1", "", "0", "1", "1", "2"]
rows = maroAxisPanel.sliceAxisRows(flat)
assert len(rows) == 1
assert rows[0]["axisFullPath"] == "|g|axis1"
assert rows[0]["jointName"] == "shoulder"
assert rows[0]["boundTargetPath"] == "|g|cube1"
assert rows[0]["parentAxisPath"] == ""
assert rows[0]["controlMode"] == 0
assert rows[0]["enabled"] is True
assert rows[0]["conventionAxis"] == 1
assert rows[0]["capabilityCount"] == 2
print("sliceAxisRows OK")

try:
    maroAxisPanel.sliceAxisRows(["only", "seven", "fields", "not", "eight", "here", "x"])
    raised = False
except ValueError:
    raised = True
assert raised, "sliceAxisRows must reject a length that's not a multiple of AXIS_FIELDS"
print("sliceAxisRows length validation OK")

assert maroAxisPanel.sliceAxisRows(None) == [], "sliceAxisRows(None) must return an empty list"
print("sliceAxisRows(None) OK")

# --- sliceCapabilityRows ---
flatCap = ["0", "|g|rot1", "maroRotation", "0", "1"]
capRows = maroAxisPanel.sliceCapabilityRows(flatCap)
assert len(capRows) == 1
assert capRows[0]["logicalIndex"] == 0
assert capRows[0]["capabilityNodeName"] == "|g|rot1"
assert capRows[0]["capabilityNodeType"] == "maroRotation"
assert capRows[0]["capType"] == 0
assert capRows[0]["connected"] is True
print("sliceCapabilityRows OK")

print("teardown OK")
sys.exit(0)
```

`tests/CMakeLists.txt`에 이 테스트를 위한 별도 항목을 추가한다(mayapy `maya.standalone`이 아니라 순수 파이썬이므로, `foreach(maya_test ...)` 루프가 아니라 `maroDiagPanel.py`의 순수 함수 테스트가 등록된 방식과 같은 자리를 찾아 그 옆에 추가한다 — 플러그인/픽스처가 필요 없는 일반 `add_test(NAME ... COMMAND "${MAYAPY}" ...)` 또는 시스템 파이썬 중 이 리포가 이미 쓰는 쪽을 그대로 따른다).

- [ ] Run: `cmake --build out/build --config Release`
- [ ] Run: `ctest --test-dir out/build -C Release -R maya_axis_panel --output-on-failure` (또는 위에서 확인한 실제 테스트 이름)
- [ ] Expected: PASS
- [ ] Commit:

```bash
git add python/maroAxisPanel.py python/maroMainWindow.py \
        src/maro_plugin/CMakeLists.txt src/maro_plugin/MaroPluginMain.cpp \
        tests/maya/test_axis_panel.py tests/CMakeLists.txt
git commit -m "feat: add maroAxisPanel UI, restructure main window layout, add teardown()"
```

---

## Task 8: `SelectionChanged` 양방향 동기화 + 수동 체크리스트

**Files:**
- Modify: `python/maroAxisPanel.py`
- Modify: `python/maroMainWindow.py`(`teardown()`에 새 `stop()` 추가)
- Modify: `docs/maro-main-ui-manual-checklist.md`

**Interfaces:**
- Produces: `maroAxisPanel.start(panelWidget)`, `maroAxisPanel.stop()` — 생명주기가 `maroRosProxy.start()`/`stop()`과 같은 모양(멱등 시작, force kill 정지).

### Step 1: `python/maroAxisPanel.py`에 동기화 job 추가

파일 상단 상수 블록 뒤에 모듈 전역 추가:

```python
_JOB_ID = None
_PANEL = None
```

`buildWidget()` 함수를 아래로 교체(패널 인스턴스를 모듈이 붙들어 두어야 idle이 아닌 이벤트 콜백에서 그 인스턴스를 갱신할 수 있다):

```python
def buildWidget():
    """maroMainWindow.buildUI()가 editorHost에 임베드할 위젯을 만든다."""
    global _PANEL
    _PANEL = AxisPanel()
    return _PANEL


def _onSceneSelectionChanged():
    """씬 선택 -> 패널 반영(설계 스펙 §9 양방향 동기화의 절반).
    패널 쪽 클릭 -> 씬 선택은 AxisPanel._onAxisRowClicked가 담당한다
    (반대 방향 콜백을 또 만들면 서로가 서로를 트리거하는 무한 루프가
    생기므로, 이 함수는 오직 "씬 -> 패널" 한 방향만 맡는다).
    """
    if _PANEL is None:
        return
    selection = cmds.ls(selection=True, long=True) or []
    if not selection:
        return
    # 선택된 오브젝트가 어느 축에 바인딩됐는지 찾는다. 축 자신이 선택됐을
    # 수도 있으므로 그 경우도 함께 본다.
    for row in sliceAxisRows(cmds.maroListAxisNodes()):
        if row["axisFullPath"] in selection or row["boundTargetPath"] in selection:
            _PANEL.selectAxis(row["axisFullPath"])
            return


def start():
    """maroMainWindow.buildUI()가 axis panel 임베드 직후 부른다. 멱등하다."""
    global _JOB_ID
    if _JOB_ID is not None and cmds.scriptJob(exists=_JOB_ID):
        return
    jobId = cmds.scriptJob(event=["SelectionChanged", _onSceneSelectionChanged],
                           protected=True)
    if isinstance(jobId, int):
        _JOB_ID = jobId
    else:
        _JOB_ID = None
        if not cmds.about(batch=True):
            print("maroAxisPanel: scriptJob() did not return a job id ({!r}) -- "
                  "selection sync will not run.".format(jobId))


def stop():
    """workspaceControl이 닫히거나 플러그인이 언로드될 때 부른다(teardown()).

    maroRosProxy.stop()과 같은 모양: kill이 실제로 성공했을 때만 _JOB_ID를
    지운다 -- 실패 시 무조건 지우면 protected scriptJob이 영구 미아가 될
    수 있다(Phase 3에서 실측으로 잡은 버그와 같은 함정, maroRosProxy.py의
    stop() 도크스트링 참고).
    """
    global _JOB_ID, _PANEL
    killSucceededOrJobGone = True
    try:
        if _JOB_ID is not None and cmds.scriptJob(exists=_JOB_ID):
            cmds.scriptJob(kill=_JOB_ID, force=True)
    except Exception:  # noqa: BLE001 -- 정리 경로
        import traceback
        traceback.print_exc()
        killSucceededOrJobGone = False

    if killSucceededOrJobGone:
        _JOB_ID = None
    _PANEL = None
```

### Step 2: `python/maroMainWindow.py` 배선

`buildUI()`에서 `maroAxisPanel.buildWidget()` 호출 직후(임베드가 성공한 뒤), 파일 맨 끝 `maroRosProxy.start(...)` 호출과 같은 자리(조립이 전부 끝난 뒤)에 추가:

```python
    import maroAxisPanel
    maroAxisPanel.start()
```

(이미 Task 7에서 `import maroAxisPanel; axisPanelWidget = maroAxisPanel.buildWidget()`을 호출한 지점이 있다 — `start()` 호출은 그 지점이 아니라 `maroRosProxy.start(...)` 바로 뒤, `buildUI()`의 맨 끝에 둔다. 이유는 `maroRosProxy.start()`와 같다: 조립 중간에 예외가 나면 idle/이벤트 콜백이 반쪽 창을 붙들지 않게 하려는 것.)

`teardown()`에 `maroAxisPanel.stop()` 추가:

```python
def teardown():
    """모든 서브시스템의 stop()을 한 곳에서 부른다."""
    try:
        import maroRosProxy
        maroRosProxy.stop()
    except Exception:  # noqa: BLE001
        import traceback
        traceback.print_exc()

    try:
        import maroAxisPanel
        maroAxisPanel.stop()
    except Exception:  # noqa: BLE001
        import traceback
        traceback.print_exc()
```

### Step 3: 수동 체크리스트 절 추가 (`docs/maro-main-ui-manual-checklist.md`)

`## 1-2. ROS 좌표 프록시 (Phase 3)` 절 뒤에 새 절을 추가한다:

```markdown
## 1-3. 노드 바인딩 + capability 에디터 (Phase 4) — **[필수 · go/no-go]**

이 절은 대화형 Maya에서만 확인할 수 있다(패널 표시, 버튼 클릭, 양방향
선택 동기화는 배치 mayapy에 UI가 없어 자동 검증 불가).

```python
cmds.maroMainWindow()
```

- [ ] **에디터 패널이 보인다** — 뷰포트 오른쪽(또는 아래, 실제 레이아웃에
      따라)에 축 목록 + capability 스택 + 버튼 7개가 보인다.
- [ ] **축 생성 + 목록 갱신**:

      ```python
      axis = cmds.createNode("maroAxis", name="checklistAxis")
      cube = cmds.polyCube(name="checklistCube")[0]
      cmds.maroBindAxis(axis, cube)
      ```

      패널을 다시 열거나 새로고침하면(구현에 따라 자동/수동) `checklistAxis`가
      왼쪽 목록에 나타난다.
- [ ] **씬 선택 -> 패널 반영**: `cmds.select(cube)`로 큐브를 선택하면
      패널의 축 목록에서 `checklistAxis`가 강조되고 capability 스택이
      갱신된다(아직 비어 있음).
- [ ] **패널 -> 씬 선택 반영**: 패널에서 `checklistAxis` 행을 클릭하면
      씬에서 `checklistCube`가 선택된다(`cmds.ls(sl=True)`로 확인).
- [ ] **capability 추가**: "+Rotation" 버튼을 누르면 `maroRotation` 노드가
      생성·연결되고 스택 목록에 나타난다. `cmds.getAttr(cube + ".rotateY")`를
      새 `maroRotation` 노드의 `.angle`에 직접 `connectAttr`한 뒤 값을 바꾸면
      큐브가 실제로 회전한다(값 연결은 여전히 수동임을 재확인 — 설계 스펙 §7).
- [ ] **상호배타 규칙**: 같은 축에 "+Translation"을 또 누르면 에러가 나고
      (스크립트 에디터에 실패 메시지), 스택에 두 번째 노드가 추가되지 않는다.
- [ ] **capability 삭제**: 스택에서 항목을 선택하고 "Remove Selected
      Capability"를 누르면 연결이 끊기고 목록에서 사라진다. `Ctrl+Z`로
      복구된다.
- [ ] **Unbind**: "Unbind" 버튼을 누르면 큐브와의 바인딩이 끊긴다.
      `Ctrl+Z`로 복구된다.
- [ ] **레이아웃 재구성 회귀 확인**: Phase 2 §1-1(듀얼 뷰포트 렌더링/조작)과
      §3(Maro 메뉴)을 재실행해 새 중첩 `paneLayout` 구조에서도 그대로
      동작하는지 확인한다.
- [ ] **언로드 go/no-go**: 패널이 열리고 축/capability가 존재하는 상태에서
      `cmds.unloadPlugin("maro")` — 크래시 없음, 에러 반복 없음,
      `[j for j in (cmds.scriptJob(listJobs=True) or []) if "maroAxisPanel" in j]`가
      `[]`.

| 절 | Phase | 필수 여부 | 결과 | 날짜 / 확인자 / Maya 빌드 | 비고 |
|---|---|---|---|---|---|
| 1-3. 에디터 패널 표시 + 목록/선택 동기화 | 4 | 필수 | | | 양방향(씬↔패널) |
| 1-3. capability 추가/삭제 + 상호배타 규칙 | 4 | 필수 | | | §3 규칙 |
| 1-3. Unbind + undo | 4 | 필수 | | | |
| 1-3. 레이아웃 재구성 후 Phase 2 §1-1/§3 재확인 | 4 | 필수 | | | 회귀 확인 |
| 1-3. 언로드 go/no-go (패널 + 축 존재 상태) | 4 | 필수 | | | |
```

- [ ] Run: `cmake --build out/build --config Release`
- [ ] Run: `ctest --test-dir out/build -C Release --output-on-failure`
- [ ] Expected: 전체 스위트 PASS(회귀 없음)
- [ ] Commit:

```bash
git add python/maroAxisPanel.py python/maroMainWindow.py \
        docs/maro-main-ui-manual-checklist.md
git commit -m "feat: add bidirectional SelectionChanged sync + Phase 4 manual checklist"
```

---

## Self-Review 결과

**스펙 커버리지**: §3(capType 확장) → Task 3. §4(노드 3종) → Task 1/2. §5(`outValueLinear`/`compute()`) → Task 3. §6(`MaroPump`) → Task 4. §7(`MaroBindAxisCommand` 무변경 + `aOutputIsLinear` 해법) → Task 2/3에서 capType 6/7 분리로 확정. §8(커맨드 5종) → Task 5/6. §9(UI/레이아웃/`teardown()`/동기화) → Task 7/8. §10(테스트 전략) → 각 태스크의 Test 항목. §11(범위 밖 — 곡선 편집 UI, 스플라인, `maroSetCapabilityOrder`, 모션캡쳐 자동화, 자동 값 연결)은 이 계획 어디에도 태스크로 넣지 않았다(의도됨).

**플레이스홀더 스캔**: 없음 — Task 6 Step 2의 "주의" 두 곳(`resolveAxis` 단순화, `m_capNodeName` 멤버 보완)은 TBD가 아니라 실제 코드로 대체할 정확한 지시다.

**타입 일관성 확인**: `hasPrimaryDriver`/`nextFreeCapabilitySlot`의 시그니처(Task 5에서 정의, `MPlug` 인자)가 Task 6의 호출부(`hasPrimaryDriver(capabilityIn)`, `nextFreeCapabilitySlot(capabilityIn)`)와 일치한다. `AXIS_FIELDS=8`/`CAPABILITY_FIELDS=5`가 C++ 쪽 필드 개수(Task 5) 및 Python 쪽 상수(Task 7)에서 동일하다. `aOutValueLinear`/`aDriveIsLinear`(Task 3에서 정의) 이름이 Task 4(`MaroPump.cpp`)의 참조와 일치한다. `EDITOR_HOST_NAME`이 Task 7에서 정의되고 그 안에서만 쓰인다.
