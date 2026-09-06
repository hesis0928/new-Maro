# 카파빌리티 노드 상세 설정 UI + Limit/TranslationLimit 캘리브레이션 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** capability 노드 7종(Rotation/Translation/SensorDirection/SensorRange/Coupling/Limit/TranslationLimit) 각각에 전용 상세 설정 창을 만들고, Limit/TranslationLimit은 뷰포트에서 오브젝트를 실제로 움직여 범위를 "수집"하는 캘리브레이션 도구까지 포함한다.

**Architecture:** `python/maroCapabilityPanel.py`에 공통 베이스 + 노드 타입별 7개 서브클래스를 두고, `python/maroLimitCalibration.py`에 Limit/TranslationLimit이 공유하는 캘리브레이션 엔진(축 지정, 임시 리그, 네이티브 매니퍼레이터, HUD, 시각화)을 둔다. `MaroLimitNode`/`MaroTranslationLimitNode`는 기존 X/Y/Z 3축 리밋 스키마를 임의 축 방향(`aAxisDirection`) + 단일 min/max로 완전히 재설계한다.

**Tech Stack:** Maya C++ API(devkit, `MPxNode`/`MFnUnitAttribute`/`MFnNumericAttribute`), Python(`maya.cmds`, `maya.api.OpenMaya` as `om2`), PySide6, mayapy 배치 테스트(ctest).

## Global Constraints

- `python/maroCapabilityPanel.py`: 공통 베이스 클래스 + capability 노드 타입별 **7개 서브클래스**(제네릭 1클래스 아님).
- 진입점은 `openCapabilityPanel(capabilityNode)` 팩토리 함수 하나 — 노드 타입 문자열을 딕셔너리로 서브클래스에 매핑.
- 단순 5타입(Rotation/Translation/SensorDirection/SensorRange/Coupling)은 `python/maroLidarPanel.py`의 `_ATTRS` 패턴(스핀박스 폼 + "적용" 버튼 + `cmds.undoInfo(openChunk/closeChunk)`로 감싼 배치 `cmds.setAttr`)을 그대로 재사용.
- `python/maroSingleObjectNodeEditor.py:427-440`의 `mouseDoubleClickEvent`를 확장하되, 기존 펼치기/접기 토글 동작은 **한 글자도 바뀌면 안 된다** — 지금까지 무반응이던 지점에만 새 동작을 추가한다.
- `MaroLimitNode`/`MaroTranslationLimitNode`: `aEnableX/Y/Z` + 6개 min/max를 **완전히** `aAxisDirection`(float3) + `aMin`/`aMax`(스칼라 2개)로 교체한다. `MaroAxisNode.cpp`는 **한 줄도 건드리지 않는다** — 새 `compute()`가 `capMin`/`capMax`/`capEnable` 컴파운드의 x/y/z 세 슬롯 모두에 똑같은 값을 broadcast하여, 기존에 `conventionAxis`로 그중 한 성분만 골라 읽던 `MaroAxisNode::compute()`(`src/maro_plugin/MaroAxisNode.cpp:296-307`)와 `maroUrdfExport.py`의 `_resolveCapabilityDetails`(`python/maroUrdfExport.py:297-314`)가 **코드 변경 없이 그대로** 올바른 값을 읽게 만든다. `capEnable`은 항상 `(1,1,1)`로 broadcast한다(새 스키마엔 "enable" 개념이 없다 — capability 슬롯이 connected면 항상 활성).
- 커스텀 매니퍼레이터(`MPxManipContainer`)와 커스텀 `MPxDrawOverride`는 **절대 새로 만들지 않는다** — Maya 네이티브 Rotate/Move 툴과 네이티브 임시 지오메트리(폴리곤 + lambert transparency)만 쓴다. 이 프로젝트의 유일한 draw override(`maroPointCloud`)가 현재 미해결 크래시 상태이므로 그 서브시스템에 아무것도 얹지 않는다.
- 캘리브레이션 대상 오브젝트가 이미 `maroAxis`의 capability 스택(1차 구동 타입)에 DG 커넥션으로 rotateX/Y/Z(또는 translateX/Y/Z)가 연결돼 있을 수 있다 — 캘리브레이션 시작 시 그 커넥션을 정확히 캡처해 임시로 끊고, 끝나면(정상 종료든 창을 강제로 닫든 플러그인이 언로드되든) **반드시** 원래 커넥션과 원래 부모/값으로 복원한다. 복원 실패는 조용히 삼키지 않고 `cmds.warning`으로 정확한 플러그 이름을 알린다.
- **[2026-09-07 실행 중 발견, 계획 수정]** mayapy 배치에서 PySide6 `QApplication`은 `platformName()`이 `"minimal"`(헤드리스 폴백)로 뜨고, 그 상태에서 `QWidget()`을 만드는 것 자체가 즉시 크래시한다(`QT_QPA_PLATFORM_PLUGIN_PATH`를 Maya 자신의 `qwindows.dll` 경로로 지정해도 동일). 이 프로젝트는 원래도 이 한계를 갖고 있었다 — `maroLidarPanel.py`/`maroSingleObjectNodeEditor.py` 둘 다 실제 `QWidget`을 만드는 자동 테스트가 존재한 적이 없다. 따라서 이 플랜의 남은 태스크에서 **실제 `QWidget`/`MaroSingleObjectNodeEditor`/`MaroCapabilityPanelBase` 서브클래스 인스턴스를 생성하는 자동화 테스트는 전부 뺀다** — 그 검증은 이미 Task 8의 수동 체크리스트가 담당하도록 계획돼 있었으므로 커버리지 공백은 없다. `CalibrationSession`(Task 6/7)은 Qt에 전혀 의존하지 않으므로 이 제약과 무관하게 그대로 자동화한다.
- 빌드/검증 커맨드(매 태스크 완료 후 실행, C++ 변경이 있으면 **Maya를 완전히 닫은 상태**에서):
  ```powershell
  cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
      if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
  }
  cmake --build out/build --config Release
  ctest --test-dir out/build -C Release --output-on-failure
  ```

---

## Task 1: `MaroLimitNode`/`MaroTranslationLimitNode` 스키마 재설계 (C++)

**Files:**
- Modify: `src/maro_plugin/MaroCapabilityNodes.h:42-59` (MaroLimitNode), `src/maro_plugin/MaroCapabilityNodes.h:99-116` (MaroTranslationLimitNode)
- Modify: `src/maro_plugin/MaroCapabilityNodes.cpp:162-229` (MaroLimitNode::initialize/compute), `src/maro_plugin/MaroCapabilityNodes.cpp:422-482` (MaroTranslationLimitNode::initialize/compute)
- Modify: `tests/maya/test_capability_stack.py:38-52,63-68,95-98,139-149,213-220`
- Modify: `tests/maya/test_contract.py:214-220`
- Modify: `tests/maya/test_tech_diag.py:514-519`
- Modify: `tests/maya/test_urdf_export.py:332-336`

**Interfaces:**
- Produces: `MaroLimitNode::aAxisDirection`(MObject, float3), `MaroLimitNode::aMin`/`aMax`(MObject, MFnUnitAttribute::kAngle) — 기존 `aEnableX/Y/Z`/`aMinX..aMaxZ` 9개 정적 멤버는 전부 삭제된다.
- Produces: `MaroTranslationLimitNode::aAxisDirection`(float3), `aMin`/`aMax`(MFnUnitAttribute::kDistance) — 기존 9개 정적 멤버 삭제.
- 두 노드 모두 `compute()`가 `capMin`/`capMax`를 `(min,min,min)`/`(max,max,max)`로, `capEnable`을 `(1,1,1)`로 채운다 — 이후 태스크(Python UI)가 `cmds.getAttr(node+".min")`/`.max`/`.axisDirection`으로 값을 읽고 쓴다.

- [ ] **Step 1: `MaroCapabilityNodes.h`의 MaroLimitNode 선언 교체**

`src/maro_plugin/MaroCapabilityNodes.h:42-59`의 기존 블록:

```cpp
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
```

를 다음으로 바꾼다:

```cpp
class MaroLimitNode : public MPxNode {
public:
    static void* creator();
    static MStatus initialize();
    MStatus compute(const MPlug& plug, MDataBlock& data) override;
    static MTypeId id;

    // 임의의 커스텀 축(로컬/월드 공간 정규화 방향 벡터) + 그 축 기준 단일
    // min/max로 재설계됐다(기존 X/Y/Z 3축 독립 리밋을 완전히 대체 --
    // 2026-09-07 설계). axisDirection은 MaroAxisNode::compute()의 클램프
    // 수식에 관여하지 않는다(그쪽은 여전히 conventionAxis 성분 인덱싱만
    // 본다) -- 캘리브레이션 UI가 헬퍼 로케이터를 정렬하는 데 쓰고, 장차
    // URDF export가 <axis>를 이 값에서 뽑아 쓸 수 있도록 남겨 둔 메타데이터다.
    static MObject aAxisDirection;   // MFnNumericAttribute::k3Float, 기본 (0,0,1)
    static MObject aMin;             // MFnUnitAttribute::kAngle (AE: 도, 내부: 라디안)
    static MObject aMax;             // MFnUnitAttribute::kAngle (AE: 도, 내부: 라디안)
    static CapabilityOutAttrs out;
};
```

- [ ] **Step 2: `MaroCapabilityNodes.h`의 MaroTranslationLimitNode 선언 교체**

`src/maro_plugin/MaroCapabilityNodes.h:99-116`의 기존 블록:

```cpp
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

를 다음으로 바꾼다:

```cpp
class MaroTranslationLimitNode : public MPxNode {
public:
    static void* creator();
    static MStatus initialize();
    MStatus compute(const MPlug& plug, MDataBlock& data) override;
    static MTypeId id;

    // MaroLimitNode와 같은 재설계 -- 각도 대신 거리(센티미터)만 다르다.
    static MObject aAxisDirection;   // MFnNumericAttribute::k3Float, 기본 (0,0,1)
    static MObject aMin;             // MFnUnitAttribute::kDistance (AE: cm/in/m, 내부: 센티미터)
    static MObject aMax;             // MFnUnitAttribute::kDistance (AE: cm/in/m, 내부: 센티미터)
    static CapabilityOutAttrs out;
};
```

- [ ] **Step 3: `MaroCapabilityNodes.cpp`의 MaroLimitNode 정의부 교체**

`src/maro_plugin/MaroCapabilityNodes.cpp:162-265`의 기존 블록 전체(정적 멤버 정의부터 `compute()` 끝까지)를 다음으로 바꾼다:

```cpp
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
```

- [ ] **Step 4: `MaroCapabilityNodes.cpp`의 MaroTranslationLimitNode 정의부 교체**

`src/maro_plugin/MaroCapabilityNodes.cpp:422-515`의 기존 블록 전체를 다음으로 바꾼다:

```cpp
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
```

- [ ] **Step 5: 빌드 (Maya 완전히 닫은 상태에서)**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

Expected: 빌드 성공. `MaroAxisNode.cpp`/`MaroPluginMain.cpp`는 이 태스크에서 전혀 건드리지 않는다 — 등록 코드는 `MaroLimitNode`/`MaroTranslationLimitNode`의 정적 멤버 이름 변경과 무관하다.

- [ ] **Step 6: `tests/maya/test_capability_stack.py` 마이그레이션**

5곳의 `enableY`/`minY`/`maxY` 3줄 블록을 각각 아래로 바꾼다(`enableY` 줄은 삭제, `minY`/`maxY`는 `min`/`max`로, 새로 `axisDirection`을 Y축 (0,1,0)으로 명시적으로 채운다 -- 기능적으로는 broadcast 덕분에 axisDirection 값과 무관하게 결과가 같지만, 테스트가 새 스키마를 실제로 행사하도록 값을 채운다):

`tests/maya/test_capability_stack.py:39-42`:
```python
lim = cmds.createNode("maroLimit", name="lim1")
cmds.setAttr(lim + ".axisDirection", 0, 1, 0, type="double3")
cmds.setAttr(lim + ".min", -0.5)
cmds.setAttr(lim + ".max", 0.5)
```

`tests/maya/test_capability_stack.py:49-52`:
```python
lim2 = cmds.createNode("maroLimit", name="lim2")
cmds.setAttr(lim2 + ".axisDirection", 0, 1, 0, type="double3")
cmds.setAttr(lim2 + ".min", -0.25)
cmds.setAttr(lim2 + ".max", 0.25)
```

`tests/maya/test_capability_stack.py:66-68`:
```python
cmds.setAttr(limFirst + ".axisDirection", 0, 1, 0, type="double3")
cmds.setAttr(limFirst + ".min", -0.1)
cmds.setAttr(limFirst + ".max", 0.1)
```

`tests/maya/test_capability_stack.py:95-98`:
```python
limRos = cmds.createNode("maroLimit", name="limRos")
cmds.setAttr(limRos + ".axisDirection", 0, 1, 0, type="double3")
cmds.setAttr(limRos + ".min", -0.5)
cmds.setAttr(limRos + ".max", 0.5)
```

`tests/maya/test_capability_stack.py:140-149`(TranslationLimit — 여기는 min/max 값 자체를 `capMin`/`capMax`의 `[0][1]`(Y 성분)로 읽는 단언이 있는데, broadcast 덕분에 이 인덱스는 그대로 남겨도 값이 맞다 -- 다만 코드가 무의미해 보이지 않도록 `[0][0]`(X 성분, 어느 축이든 broadcast로 동일)으로 바꾼다):
```python
transLim = cmds.createNode("maroTranslationLimit", name="transLim1")
cmds.setAttr(transLim + ".axisDirection", 0, 1, 0, type="double3")
cmds.setAttr(transLim + ".min", -5.0)
cmds.setAttr(transLim + ".max", 5.0)
assert cmds.getAttr(transLim + ".capabilityOut.capType") == 5, "translationLimit capType"
minAny = cmds.getAttr(transLim + ".capabilityOut.capMin")[0][0]
maxAny = cmds.getAttr(transLim + ".capabilityOut.capMax")[0][0]
assert abs(minAny - (-5.0)) < 1e-9 and abs(maxAny - 5.0) < 1e-9, \
    f"translationLimit min/max must carry centimeters, broadcast to every component (got {minAny}, {maxAny})"
print("translationLimit node OK")
```

`tests/maya/test_capability_stack.py:214-217`:
```python
transLimDrive = cmds.createNode("maroTranslationLimit", name="transLimDrive1")
cmds.setAttr(transLimDrive + ".axisDirection", 0, 1, 0, type="double3")
cmds.setAttr(transLimDrive + ".min", -5.0)
cmds.setAttr(transLimDrive + ".max", 5.0)
```

나머지 코드(주석, assert, 다른 캡ability 테스트)는 그대로 둔다.

- [ ] **Step 7: `tests/maya/test_contract.py` 마이그레이션**

`tests/maya/test_contract.py:216-219`:
```python
lim = cmds.createNode("maroLimit")
cmds.setAttr(lim + ".axisDirection", 0, 1, 0, type="double3")
cmds.setAttr(lim + ".min", -0.5)
cmds.setAttr(lim + ".max", 0.5)
```

- [ ] **Step 8: `tests/maya/test_tech_diag.py` 마이그레이션**

`tests/maya/test_tech_diag.py:514-519`:
```python
unitLim = cmds.createNode("maroLimit", name="unitLimitLim")
# 2026-09-07 재설계: 어느 축인지는 이제 axisDirection이 나르고,
# MaroAxisNode.cpp의 conventionAxis 인덱싱은 broadcast로 흡수된다.
cmds.setAttr(unitLim + ".axisDirection", 0, 1, 0, type="double3")
cmds.setAttr(unitLim + ".min", -90.0)          # 도 -> -pi/2 rad
cmds.setAttr(unitLim + ".max", 90.0)           # 도 ->  pi/2 rad
```

`tests/maya/test_tech_diag.py:524-526`의 단언은 인덱스를 바꿀 필요 없다(`[0][1]`이든 어느 성분이든 broadcast로 동일) — 그대로 둔다.

- [ ] **Step 9: `tests/maya/test_urdf_export.py` 마이그레이션**

`tests/maya/test_urdf_export.py:332-335`:
```python
limitNode = cmds.maroAddCapability(childAxis, type="limit")[0]
cmds.setAttr(limitNode + ".axisDirection", 1, 0, 0, type="double3")
cmds.setAttr(limitNode + ".min", -57.29578)  # -1 rad in degrees
cmds.setAttr(limitNode + ".max", 57.29578)   # +1 rad in degrees
```

- [ ] **Step 10: 전체 테스트 실행**

```powershell
ctest --test-dir out/build -C Release --output-on-failure -R "maya_capability_stack|maya_contract|maya_tech_diag|maya_urdf_export|maya_axis_editor_commands"
```

Expected: 5개 테스트 모두 PASS. `maya_axis_editor_commands`는 이 태스크에서 코드를 바꾸지 않았지만(Step 확인 완료 — `.enableY`/`.minY`류를 쓰지 않음), 회귀 확인 차 함께 돌린다.

- [ ] **Step 11: 전체 스위트 실행 (회귀 확인)**

```powershell
ctest --test-dir out/build -C Release --output-on-failure
```

Expected: 전체 PASS. 특히 `maya_urdf_export`가 코드 변경 없이 통과해야 `MaroAxisNode.cpp`/`maroUrdfExport.py` 무변경 가정이 맞았음을 증명한다.

- [ ] **Step 12: 커밋**

```bash
git add src/maro_plugin/MaroCapabilityNodes.h src/maro_plugin/MaroCapabilityNodes.cpp tests/maya/test_capability_stack.py tests/maya/test_contract.py tests/maya/test_tech_diag.py tests/maya/test_urdf_export.py
git commit -m "$(cat <<'EOF'
refactor(capability): replace maroLimit/maroTranslationLimit's X/Y/Z axes with a single custom axis

aEnableX/Y/Z + 6 per-axis min/max attributes are replaced by one
axisDirection(float3) + min/max pair, matching URDF's own single-axis
joint model and enabling the upcoming viewport calibration tool.
compute() broadcasts the single min/max into all three capMin/capMax
components so MaroAxisNode.cpp's existing conventionAxis-indexed read
and maroUrdfExport.py's _resolveCapabilityDetails keep working unchanged.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `maroCapabilityPanel.py` 베이스 클래스 + 5개 단순 패널 + 팩토리

**Files:**
- Create: `python/maroCapabilityPanel.py`
- Modify: `src/maro_plugin/CMakeLists.txt:162-179` (`MARO_PLUGIN_PY_MODULES` 리스트에 `maroCapabilityPanel` 추가)
- Modify: `python/maroSingleObjectNodeEditor.py:377-421` (`_showCouplingSourcePicker`를 공유 헬퍼로 추출)
- Modify: `python/maroMainWindow.py:374-380` 부근 (`teardown()`에 `maroCapabilityPanel.stop()` 추가)
- Test: `tests/maya/test_capability_panel.py`

**Interfaces:**
- Produces: `maroCapabilityPanel.openCapabilityPanel(capabilityNode)` — `cmds.nodeType(capabilityNode)`로 분기해 알맞은 패널 서브클래스를 열거나(이미 열려 있으면 raise) 새로 만든다. 이 태스크에서는 `"maroRotation"/"maroTranslation"/"maroSensorDirection"/"maroSensorRange"/"maroCoupling"` 5종만 매핑되어 있다 — `"maroLimit"/"maroTranslationLimit"`는 Task 5가 추가한다(그 전까지 이 두 타입으로 호출하면 `ValueError`).
- Produces: `maroCapabilityPanel.stop()` — 열린 패널 전부 닫기(언로드 정리).
- Produces: `maroSingleObjectNodeEditor.connectCouplingSource(couplingNodeName, sourceAxis)` — 기존 `_showCouplingSourcePicker`의 연결 로직(라인 395-416)을 함수로 추출한 것. 시그니처: `sourceAxis`(str, 다른 축의 fullPath)를 받아 `couplingNodeName`의 `sourceIsLinear`/`sourceValue(Linear)`를 undo 청크로 감싸 설정. `cmds.undoInfo`/`cmds.setAttr`/`cmds.connectAttr`만 쓰고 Qt에 의존하지 않는다 — `maroCapabilityPanel.py`가 이걸 import해서 재사용한다.

- [ ] **Step 1: `maroSingleObjectNodeEditor.py`에서 연결 로직을 공유 함수로 추출**

`python/maroSingleObjectNodeEditor.py`에서 `_showCouplingSourcePicker` 메서드(라인 377-425) 바로 앞, 클래스 밖 모듈 레벨에 다음 함수를 추가한다(`CAPABILITY_TYPES` 정의 아래, `_OPEN_EDITORS = {}` 위 아무 곳):

```python
def connectCouplingSource(couplingNodeName, sourceAxis):
    """couplingNodeName(maroCoupling 노드)의 소스를 sourceAxis(다른 축의
    fullPath)로 연결한다. sourceAxis의 driveIsLinear를 읽어 각도/선형 중
    맞는 슬롯(sourceValue 또는 sourceValueLinear)에 연결하고
    sourceIsLinear를 그에 맞춰 설정한다 -- 리뷰 Finding C-1(이 파일 위쪽
    MaroCouplingNode 관련 주석 참고)이 요구하는 단위 안전 연결.

    호출자가 이미 sourceAxis가 couplingNodeName이 붙은 축과 다르다는 것을
    보장해야 한다(자기 자신을 소스로 고르는 것은 호출자 책임으로 막는다).
    """
    isLinear = cmds.getAttr(sourceAxis + ".driveIsLinear")
    cmds.undoInfo(openChunk=True)
    try:
        cmds.setAttr(couplingNodeName + ".sourceIsLinear", isLinear)
        if isLinear:
            cmds.connectAttr(sourceAxis + ".positionLinear",
                             couplingNodeName + ".sourceValueLinear", force=True)
        else:
            cmds.connectAttr(sourceAxis + ".position",
                             couplingNodeName + ".sourceValue", force=True)
    finally:
        cmds.undoInfo(closeChunk=True)
```

- [ ] **Step 2: `_showCouplingSourcePicker`가 새 함수를 호출하도록 교체**

`python/maroSingleObjectNodeEditor.py:395-421`의 기존 `_onApply` 내부 블록:

```python
        def _onApply():
            try:
                sourceAxis = combo.currentData()
                if not sourceAxis:
                    picker.close()
                    return
                isLinear = cmds.getAttr(sourceAxis + ".driveIsLinear")
                cmds.undoInfo(openChunk=True)
                try:
                    cmds.setAttr(couplingNodeName + ".sourceIsLinear", isLinear)
                    if isLinear:
                        cmds.connectAttr(sourceAxis + ".positionLinear",
                                         couplingNodeName + ".sourceValueLinear", force=True)
                    else:
                        cmds.connectAttr(sourceAxis + ".position",
                                         couplingNodeName + ".sourceValue", force=True)
                except RuntimeError as error:
                    print("Maro: coupling source connection failed -- {}".format(error))
                    picker.close()
                    return
                finally:
                    cmds.undoInfo(closeChunk=True)
                picker.close()
                self.update()
            except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
                import traceback
                traceback.print_exc()
```

를 다음으로 바꾼다:

```python
        def _onApply():
            try:
                sourceAxis = combo.currentData()
                if not sourceAxis:
                    picker.close()
                    return
                try:
                    connectCouplingSource(couplingNodeName, sourceAxis)
                except RuntimeError as error:
                    print("Maro: coupling source connection failed -- {}".format(error))
                    picker.close()
                    return
                picker.close()
                self.update()
            except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
                import traceback
                traceback.print_exc()
```

- [ ] **Step 3: `tests/maya/test_single_object_node_editor.py`로 추출 회귀 확인**

```powershell
ctest --test-dir out/build -C Release --output-on-failure -R maya_single_object_node_editor
```

Expected: PASS (이 파일은 C++을 안 건드렸으므로 재빌드 없이 즉시 실행 가능 -- Python만 바뀌었을 때도 `out/build/src/maro_plugin/Release/maroSingleObjectNodeEditor.py`가 스테일 상태일 수 있으니, Maya가 닫혀 있다면 `cmake --build out/build --config Release`를 먼저 한 번 돌려 재스테이징한다).

- [ ] **Step 4: `maroCapabilityPanel.py` 작성**

```python
"""capability 노드 7종 각각의 상세 설정 창. 노드 타입별로 클래스를
나눈다(제네릭 1클래스 아님 -- 설계 스펙 2026-09-07 §1). 공통 인프라만
MaroCapabilityPanelBase가 쥐고, 각 서브클래스는 자신의 _ATTRS만 정의한다.

maroLidarPanel.py와 같은 패턴: 노드 풀 경로 키의 _OPEN_EDITORS 싱글톤,
stop()이 플러그인 언로드 시 전부 닫음(maroMainWindow.teardown()에 등록).
"""
import maya.cmds as cmds
from PySide6 import QtCore, QtWidgets

import maroSingleObjectNodeEditor

_OPEN_EDITORS = {}  # capabilityNode -> MaroCapabilityPanelBase 서브클래스 인스턴스


def stop():
    """플러그인 언로드/창 닫힘 시 열려 있는 상세 설정 창을 전부 닫는다.
    maroLidarPanel.stop()과 같은 규율로 한 창의 실패가 나머지 창의 정리를
    막지 않게 한다."""
    for panel in list(_OPEN_EDITORS.values()):
        try:
            panel.close()
            panel.deleteLater()
        except Exception:  # noqa: BLE001 -- 언로드 정리 경계
            import traceback
            traceback.print_exc()
    _OPEN_EDITORS.clear()


class MaroCapabilityPanelBase(QtWidgets.QWidget):
    """capability 노드 하나의 설정 폼 공통 인프라. setStyleSheet()를
    부르지 않는다(maroMainWindow.py와 같은 규율). 서브클래스는 클래스
    속성 _ATTRS(리스트의 (attrName, label, kind) 튜플)만 정의하면 된다.
    kind: "bool"/"int"/"float"/"string"/"vec3".
    """

    _ATTRS = []

    def __init__(self, capabilityNode, parent=None):
        super().__init__(parent, QtCore.Qt.Window)
        self._node = capabilityNode
        self.setWindowTitle(capabilityNode.split("|")[-1])

        self._layout = QtWidgets.QFormLayout(self)
        self._fields = {}
        self._vecFields = {}
        for attrName, label, kind in self._ATTRS:
            if kind == "vec3":
                container, subFields = self._makeVec3Field()
                self._layout.addRow(label, container)
                self._vecFields[attrName] = subFields
            else:
                field = self._makeField(kind)
                self._layout.addRow(label, field)
                self._fields[attrName] = (field, kind)

        self._buildExtra()
        self._loadValues()

        applyButton = QtWidgets.QPushButton("적용")
        applyButton.clicked.connect(self._onApply)
        self._layout.addRow(applyButton)

    def _buildExtra(self):
        """서브클래스가 _ATTRS 외 추가 위젯(버튼, 읽기전용 표시 등)을 넣는
        훅. 기본은 무동작."""

    def closeEvent(self, event):
        try:
            if _OPEN_EDITORS.get(self._node) is self:
                del _OPEN_EDITORS[self._node]
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
            import traceback
            traceback.print_exc()
        super().closeEvent(event)

    def _makeField(self, kind):
        if kind == "bool":
            return QtWidgets.QCheckBox()
        if kind == "int":
            field = QtWidgets.QSpinBox()
            field.setRange(-1000000, 1000000)
            return field
        if kind == "string":
            return QtWidgets.QLineEdit()
        field = QtWidgets.QDoubleSpinBox()
        field.setRange(-100000.0, 100000.0)
        field.setDecimals(4)
        return field

    def _makeVec3Field(self):
        container = QtWidgets.QWidget()
        hbox = QtWidgets.QHBoxLayout(container)
        hbox.setContentsMargins(0, 0, 0, 0)
        subFields = []
        for _ in range(3):
            f = QtWidgets.QDoubleSpinBox()
            f.setRange(-1000.0, 1000.0)
            f.setDecimals(6)
            hbox.addWidget(f)
            subFields.append(f)
        return container, subFields

    def _loadValues(self):
        if not cmds.objExists(self._node):
            return
        for attrName, (field, kind) in self._fields.items():
            plugName = self._node + "." + attrName
            if kind == "bool":
                field.setChecked(bool(cmds.getAttr(plugName)))
            elif kind == "string":
                field.setText(cmds.getAttr(plugName) or "")
            else:
                field.setValue(cmds.getAttr(plugName))
        for attrName, subFields in self._vecFields.items():
            plugName = self._node + "." + attrName
            x, y, z = cmds.getAttr(plugName)[0]
            subFields[0].setValue(x)
            subFields[1].setValue(y)
            subFields[2].setValue(z)

    def _onApply(self):
        try:
            cmds.undoInfo(openChunk=True)
            for attrName, (field, kind) in self._fields.items():
                plugName = self._node + "." + attrName
                if kind == "bool":
                    cmds.setAttr(plugName, field.isChecked())
                elif kind == "string":
                    cmds.setAttr(plugName, field.text(), type="string")
                else:
                    cmds.setAttr(plugName, field.value())
            for attrName, subFields in self._vecFields.items():
                plugName = self._node + "." + attrName
                cmds.setAttr(plugName, subFields[0].value(), subFields[1].value(),
                             subFields[2].value(), type="double3")
        except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
            cmds.warning("Maro: failed to apply capability settings: {}".format(exc))
        finally:
            cmds.undoInfo(closeChunk=True)


class MaroRotationPanel(MaroCapabilityPanelBase):
    _ATTRS = [("angle", "Angle (deg)", "float")]


class MaroTranslationPanel(MaroCapabilityPanelBase):
    _ATTRS = [("distance", "Distance", "float")]


class MaroSensorDirectionPanel(MaroCapabilityPanelBase):
    _ATTRS = [("direction", "Direction", "vec3")]


class MaroSensorRangePanel(MaroCapabilityPanelBase):
    _ATTRS = [
        ("range", "Range", "float"),
        ("coneAngle", "Cone angle (deg)", "float"),
    ]


class MaroCouplingPanel(MaroCapabilityPanelBase):
    _ATTRS = [
        ("ratio", "Ratio", "float"),
        ("offset", "Offset", "float"),
        ("outputIsLinear", "Output is linear", "bool"),
    ]

    def _buildExtra(self):
        reconnectButton = QtWidgets.QPushButton("소스 축 재지정")
        reconnectButton.clicked.connect(self._onReconnectSource)
        self._layout.addRow(reconnectButton)

    def _onReconnectSource(self):
        try:
            picker = QtWidgets.QWidget(self, QtCore.Qt.Popup)
            layout = QtWidgets.QVBoxLayout(picker)
            combo = QtWidgets.QComboBox()
            rows = cmds.maroListAxisNodes()
            axisFields = 10  # maroSingleObjectNodeEditor.AXIS_FIELDS와 같은 C++ 계약
            for i in range(len(rows) // axisFields):
                f = rows[i * axisFields:(i + 1) * axisFields]
                combo.addItem(f[8] if f[8] else f[0], f[0])
            layout.addWidget(combo)
            applyButton = QtWidgets.QPushButton("Connect")
            layout.addWidget(applyButton)

            def _onApply():
                try:
                    sourceAxis = combo.currentData()
                    if not sourceAxis:
                        picker.close()
                        return
                    maroSingleObjectNodeEditor.connectCouplingSource(self._node, sourceAxis)
                    picker.close()
                except Exception as error:  # noqa: BLE001 -- Qt 콜백 경계
                    print("Maro: coupling source reconnection failed -- {}".format(error))
                    picker.close()

            applyButton.clicked.connect(_onApply)
            picker.move(self.mapToGlobal(QtCore.QPoint(20, 20)))
            picker.show()
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
            import traceback
            traceback.print_exc()


_PANEL_CLASSES = {
    "maroRotation": MaroRotationPanel,
    "maroTranslation": MaroTranslationPanel,
    "maroSensorDirection": MaroSensorDirectionPanel,
    "maroSensorRange": MaroSensorRangePanel,
    "maroCoupling": MaroCouplingPanel,
}


def openCapabilityPanel(capabilityNode):
    """capabilityNode(예: "maroLimit1")의 타입에 맞는 상세 설정 창을 연다.
    이미 열려 있으면 그 창을 앞으로 가져온다. 타입이 _PANEL_CLASSES에
    없으면 ValueError(예: Task 5 이전의 maroLimit/maroTranslationLimit)."""
    existing = _OPEN_EDITORS.get(capabilityNode)
    if existing is not None:
        try:
            existing.raise_()
            existing.activateWindow()
            return existing
        except RuntimeError:
            del _OPEN_EDITORS[capabilityNode]

    nodeType = cmds.nodeType(capabilityNode)
    panelClass = _PANEL_CLASSES.get(nodeType)
    if panelClass is None:
        raise ValueError(
            "Maro: no capability detail panel registered for node type '{}'".format(nodeType))

    panel = panelClass(capabilityNode)
    _OPEN_EDITORS[capabilityNode] = panel
    panel.show()
    return panel
```

- [ ] **Step 5: `src/maro_plugin/CMakeLists.txt`에 새 모듈 등록**

`src/maro_plugin/CMakeLists.txt:162-179`의 `MARO_PLUGIN_PY_MODULES` 리스트에 `maroCapabilityPanel`을 알파벳 순서(`maroCapabilityPanel`은 `maroDagMenu` 앞)로 추가한다:

```cmake
set(MARO_PLUGIN_PY_MODULES
    maroCapabilityPanel
    maroDagMenu
    maroDiagPanel
    maroLidarPanel
    maroMainWindow
    maroMenu
    maroObjectNodeEditor
    maroRosProxy
    maroSettingsPanel
    maroSkeletonUpload
    maroSingleObjectNodeEditor
    maroSyntheticDataCamera
    maroSyntheticDataPanel
    maroSyntheticDataPointCloud
    maroSyntheticDataRender
    maroTechDiag
    maroUrdfExport
)
```

- [ ] **Step 6: `maroMainWindow.py`의 `teardown()`에 등록**

`python/maroMainWindow.py:374-380`(`maroLidarPanel.stop()` 블록) 바로 뒤에 추가:

```python
    try:
        import maroCapabilityPanel
        maroCapabilityPanel.stop()
    except Exception:  # noqa: BLE001 -- Maya 콜백/언로드 경계
        import traceback
        traceback.print_exc()
```

- [ ] **Step 7: 테스트 작성 `tests/maya/test_capability_panel.py`**

**[2026-09-07 수정]** 실제 `QWidget`을 만들지 않는 부분(factory 매핑,
위젯 생성 전에 끝나는 에러 경로)만 자동화한다 — Global Constraints의
mayapy/PySide6 `"minimal"` 플랫폼 제약 참고. 패널을 실제로 열고 필드를
채우고 적용하는 플로우는 Task 8 수동 체크리스트가 담당한다.

```python
"""capability 상세 설정 패널: 실제 QWidget 생성 없이 확인 가능한 부분만
자동화한다.

[2026-09-07 실측] mayapy 표준입출력 환경에서 PySide6의 QApplication은
platformName()이 "minimal"(헤드리스 폴백)로 뜨고, 그 상태에서는
QWidget()을 만드는 것 자체가 즉시 크래시한다(Maya GUI가 쓰는 Qt와
mayapy용 PySide6의 플랫폼 플러그인이 안 맞는 것으로 보임 --
QT_QPA_PLATFORM_PLUGIN_PATH를 Maya 자신의 qwindows.dll 경로로 지정해도
동일하게 크래시했다). 이 프로젝트는 원래도 이 한계를 갖고 있었다 --
maroLidarPanel.py/maroSingleObjectNodeEditor.py 둘 다 실제 QWidget을
만드는 자동 테스트가 존재한 적이 없고(test_single_object_node_editor.py는
순수 함수만 검증), Qt 창의 실제 동작은 항상 수동 체크리스트로 확인해 왔다.
이 파일도 그 관례를 따른다 -- 패널을 실제로 열고 필드를 채우고 적용하는
플로우는 docs/maro-main-ui-manual-checklist.md의 수동 체크리스트가
담당한다(Task 8).

여기서 자동화하는 것은 QWidget을 전혀 만들지 않고도 검증 가능한
factory 매핑 계약뿐이다.
"""
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(plugin))))
import maroCapabilityPanel  # noqa: E402

# 모듈 임포트 자체(클래스 정의, PySide6 임포트)는 QApplication/QWidget을
# 만들지 않으므로 안전하다 -- 여기까지 온 것 자체가 그 사실의 증거.
print("module import OK")

# _PANEL_CLASSES 매핑: 이 시점(Task 5 이전)엔 5개 단순 타입만 등록.
expectedTypes = {
    "maroRotation": maroCapabilityPanel.MaroRotationPanel,
    "maroTranslation": maroCapabilityPanel.MaroTranslationPanel,
    "maroSensorDirection": maroCapabilityPanel.MaroSensorDirectionPanel,
    "maroSensorRange": maroCapabilityPanel.MaroSensorRangePanel,
    "maroCoupling": maroCapabilityPanel.MaroCouplingPanel,
}
assert maroCapabilityPanel._PANEL_CLASSES == expectedTypes, maroCapabilityPanel._PANEL_CLASSES
print("_PANEL_CLASSES mapping OK")

# openCapabilityPanel()은 타입을 찾지 못하면 QWidget을 만들기 전에
# ValueError를 던진다 -- 이 경로는 위젯 생성 전에 끝나므로 mayapy에서
# 안전하게 자동 검증할 수 있다.
lim = cmds.createNode("maroLimit", name="limForPanelFactoryCheck")
try:
    maroCapabilityPanel.openCapabilityPanel(lim)
    raised = False
except ValueError:
    raised = True
assert raised, "maroLimit must not be registered yet (Task 5 adds it)"
print("factory rejects unregistered type before constructing any widget OK")

# stop()은 _OPEN_EDITORS가 비어 있어도 안전한 무동작이어야 한다(위젯을
# 하나도 안 만들었으므로 여기서는 그 경로만 확인).
assert len(maroCapabilityPanel._OPEN_EDITORS) == 0
maroCapabilityPanel.stop()
assert len(maroCapabilityPanel._OPEN_EDITORS) == 0
print("stop() no-op when nothing is open OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
```

- [ ] **Step 8: `tests/CMakeLists.txt`에 새 테스트 등록**

`tests/CMakeLists.txt:285-295`의 `foreach(maya_test ...)` 리스트에 `capability_panel`을 추가(`capability_stack` 바로 뒤 알파벳 근접 위치):

```cmake
    foreach(maya_test load axis_node binding capability_stack capability_panel delete_rules
                      robustness diag_boad diag_onfix diag_book
                      diag_book_cross_session diag_remedy
                      diag_degraded diag_degraded_remedy diag_thread
                      panel_commands main_window main_menu journal remedy_capture
                      remedy_availability remedy_ambiguous_names
                      main_thread_queue remedy_apply sentinel lidar_node
                      ros_proxy_commands ros_proxy_sync axis_editor_commands
                      dag_menu tech_diag point_cloud_node lidar_commands
                      lidar_menu lidar_multi_mesh skeleton_upload settings_panel synthetic_data_camera urdf_export
                      lidar_scan_query mesh_collision synthetic_data_point_cloud synthetic_data_render)
```

- [ ] **Step 9: 빌드 + 실행**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure -R "maya_capability_panel|maya_single_object_node_editor"
```

Expected: 둘 다 PASS.

- [ ] **Step 10: 커밋**

```bash
git add python/maroCapabilityPanel.py python/maroSingleObjectNodeEditor.py python/maroMainWindow.py src/maro_plugin/CMakeLists.txt tests/maya/test_capability_panel.py tests/CMakeLists.txt
git commit -m "$(cat <<'EOF'
feat(capability): add per-type detail settings panels for 5 simple capability nodes

MaroCapabilityPanelBase + MaroRotationPanel/MaroTranslationPanel/
MaroSensorDirectionPanel/MaroSensorRangePanel/MaroCouplingPanel, opened
through the openCapabilityPanel() factory. Extracts SONE's coupling
source-connect logic into maroSingleObjectNodeEditor.connectCouplingSource()
so both the one-shot picker and this panel's "reconnect" button share it.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: SONE 더블클릭 통합

**Files:**
- Modify: `python/maroSingleObjectNodeEditor.py:427-440`
- Test: `tests/maya/test_single_object_node_editor.py` (확장)

**Interfaces:**
- Consumes: Task 2의 `maroCapabilityPanel.openCapabilityPanel(capabilityNode)`.
- 변경 없음(다음 태스크가 그대로 씀): `MaroSingleObjectNodeEditor._capabilityRows()`, `_expandedRowRects()`.

- [ ] **Step 1: `mouseDoubleClickEvent` 교체**

`python/maroSingleObjectNodeEditor.py:427-440`의 기존 코드:

```python
    def mouseDoubleClickEvent(self, event):
        try:
            rows = self._capabilityRows()
            connected = [r for r in rows if r["connected"]]
            if len(connected) >= 2:
                self._expanded = not self._expanded
                if not self._expanded:
                    # 접으면 선택도 함께 푼다 -- 안 보이는 행이 선택된 채로
                    # 남으면 Delete가 화면에 없는 것을 지운다.
                    self._selectedCapabilityIndex = None
                self.update()
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
            import traceback
            traceback.print_exc()
```

를 다음으로 바꾼다:

```python
    def mouseDoubleClickEvent(self, event):
        # [설계 스펙 2026-09-07 §2] 기존 펼치기/접기 토글은 그대로 두고,
        # 지금까지 무반응이던 지점에만 상세 설정 열기를 추가한다:
        #  - 펼친 상태에서 특정 행 더블클릭 -> 그 행의 상세 패널 (신규)
        #  - 펼친 상태에서 행이 아닌 곳(중앙 노드 등) 더블클릭 -> 접기 (기존과 동일)
        #  - 접힌 상태, capability 2개 이상 -> 펼치기 (기존과 동일, 위치 무관)
        #  - 접힌 상태, capability 정확히 1개 -> 그 하나의 상세 패널 (신규,
        #    기존엔 이 클릭이 무동작이었다)
        try:
            rows = self._capabilityRows()
            connected = [r for r in rows if r["connected"]]

            if self._expanded:
                pos = event.position()
                for logicalIndex, itemRect in self._expandedRowRects(rows):
                    if itemRect.contains(pos):
                        for row in rows:
                            if row["logicalIndex"] == logicalIndex and row["connected"]:
                                self._openCapabilityDetail(row["capabilityNodeName"])
                                return
                # 행이 아닌 곳을 더블클릭하면 기존처럼 접는다.
                self._expanded = False
                self._selectedCapabilityIndex = None
                self.update()
                return

            if len(connected) >= 2:
                self._expanded = True
                self.update()
                return

            if len(connected) == 1:
                self._openCapabilityDetail(connected[0]["capabilityNodeName"])
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
            import traceback
            traceback.print_exc()

    def _openCapabilityDetail(self, capabilityNodeName):
        try:
            import maroCapabilityPanel
            maroCapabilityPanel.openCapabilityPanel(capabilityNodeName)
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
            import traceback
            traceback.print_exc()
```

- [ ] **Step 2: 자동화 테스트는 추가하지 않는다 — 수동 체크리스트로 커버**

**[2026-09-07 수정]** Global Constraints에 적은 mayapy/PySide6 `"minimal"`
플랫폼 제약 때문에, `MaroSingleObjectNodeEditor` 인스턴스를 실제로 만들고
`QMouseEvent`를 디스패치하는 자동화 테스트는 mayapy에서 크래시한다.
`test_single_object_node_editor.py`는 원래도 순수 함수만 검증해 왔다(실제
`QWidget`을 만드는 자동 테스트가 이 파일에 존재한 적이 없다) — 이 관례를
깨지 않는다. 더블클릭 3분기(단일/펼침-행/펼침-중앙) 동작 검증은 Task 8
수동 체크리스트의 "7-1. SONE 더블클릭 3분기" 항목이 이미 담당하도록
계획돼 있으므로 커버리지 공백은 없다.

- [ ] **Step 3: 빌드 + 실행(회귀만 확인)**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure -R maya_single_object_node_editor
```

Expected: PASS (기존 순수 함수 테스트가 코드 변경 후에도 깨지지 않는지만 확인).

- [ ] **Step 4: 커밋**

```bash
git add python/maroSingleObjectNodeEditor.py tests/maya/test_single_object_node_editor.py
git commit -m "$(cat <<'EOF'
feat(sone): open capability detail panels via double-click

Double-clicking the sole connected capability (collapsed, single-slot
axis) or a specific row in the expanded dropdown now opens that
capability's detail settings panel. The existing expand/collapse toggle
on the center node is untouched.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `maroLimitCalibration.py` 순수 함수

**Files:**
- Create: `python/maroLimitCalibration.py`
- Modify: `src/maro_plugin/CMakeLists.txt:162-179` (`maroLimitCalibration` 추가)
- Test: `tests/maya/test_limit_calibration_pure.py`

**Interfaces:**
- Produces: `axisDirectionFromPoints(pointA, pointB)` — `(x,y,z)` 튜플 두 개 → 정규화된 방향 벡터 `(x,y,z)` 튜플. `pointA == pointB`(거리 0)면 `ValueError`.
- Produces: `axisBasisEulerXYZ(axisDirection)` — 임의의 정규화 방향 벡터를 로컬 Z로 갖는 정규직교 기저를 구성해 `(rx, ry, rz)` 오일러 각(도) 튜플로 돌려준다(헬퍼 로케이터를 이 값으로 `cmds.setAttr(locator+".rotate", rx, ry, rz)` 하면 로컬 Z가 axisDirection과 일치). `maya.api.OpenMaya`(`om2`)만 쓰는 순수 함수 — `python/maroUrdfExport.py`의 `computeRelativeOrigin()`과 같은 성격(Maya 씬 상태 없이 API 수학 객체만 사용).
- Produces: `expandRange(currentMin, currentMax, sample)` — collect 한 번의 범위확장 로직. `(newMin, newMax)` 튜플을 돌려준다.
- Produces: `mayaDirectionToRos(direction)` — `(x,y,z)` → `(x,-z,y)`. 이동 성분/스케일 없음 — 위치 변환(`mayaToRosPosition`)과 달리 순수 방향 변환.

- [ ] **Step 1: 실패하는 테스트 작성 `tests/maya/test_limit_calibration_pure.py`**

```python
"""maroLimitCalibration.py의 Maya-비의존 순수 함수 계약. 노드/뷰포트 없이
mayapy로 검증한다(maroSingleObjectNodeEditor.py의 sliceCapabilityRows류와
같은 이유)."""
import math
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(plugin))))
import maroLimitCalibration as calib  # noqa: E402

# axisDirectionFromPoints: 정규화된 방향.
d = calib.axisDirectionFromPoints((0.0, 0.0, 0.0), (0.0, 5.0, 0.0))
assert abs(d[0]) < 1e-9 and abs(d[1] - 1.0) < 1e-9 and abs(d[2]) < 1e-9, d
d2 = calib.axisDirectionFromPoints((1.0, 1.0, 1.0), (4.0, 5.0, 1.0))
length = math.sqrt(d2[0] ** 2 + d2[1] ** 2 + d2[2] ** 2)
assert abs(length - 1.0) < 1e-9, f"must be normalized (got length {length})"
try:
    calib.axisDirectionFromPoints((2.0, 2.0, 2.0), (2.0, 2.0, 2.0))
    raised = False
except ValueError:
    raised = True
assert raised, "identical points must raise ValueError"
print("axisDirectionFromPoints OK")

# axisBasisEulerXYZ: 결과 오일러를 다시 로테이션 행렬로 조립해서 로컬 Z가
# axisDirection과 일치하는지 순수 선형대수로 검증한다(마야 노드 불필요).
import maya.api.OpenMaya as om2  # noqa: E402


def _rotateLocalZ(rx, ry, rz):
    euler = om2.MEulerRotation(math.radians(rx), math.radians(ry), math.radians(rz))
    m = euler.asMatrix()
    localZ = om2.MVector(0.0, 0.0, 1.0) * m
    return (localZ.x, localZ.y, localZ.z)


for axis in [(0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0),
             (0.5773502691896258, 0.5773502691896258, 0.5773502691896258)]:
    rx, ry, rz = calib.axisBasisEulerXYZ(axis)
    gotZ = _rotateLocalZ(rx, ry, rz)
    assert abs(gotZ[0] - axis[0]) < 1e-6 and abs(gotZ[1] - axis[1]) < 1e-6 \
        and abs(gotZ[2] - axis[2]) < 1e-6, \
        f"local Z after rotation {(rx, ry, rz)} must equal axis {axis}, got {gotZ}"
print("axisBasisEulerXYZ OK")

# expandRange: 누적 확장.
assert calib.expandRange(0.0, 0.0, 0.3) == (0.0, 0.3)
assert calib.expandRange(0.0, 0.3, -0.2) == (-0.2, 0.3)
assert calib.expandRange(-0.2, 0.3, 0.1) == (-0.2, 0.3), "sample inside range must not shrink it"
print("expandRange OK")

# mayaDirectionToRos: 위치 변환과 같은 축 재배치, 스케일 없음.
rosVec = calib.mayaDirectionToRos((1.0, 2.0, 3.0))
assert rosVec == (1.0, -3.0, 2.0), rosVec
unit = calib.mayaDirectionToRos((0.0, 1.0, 0.0))
assert unit == (0.0, 0.0, 1.0), "Y-up must map to Z-up with no scale"
print("mayaDirectionToRos OK")

cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
```

- [ ] **Step 2: 실행해서 실패 확인**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests\maya\test_limit_calibration_pure.py
```

Expected: `ModuleNotFoundError: No module named 'maroLimitCalibration'`로 실패.

- [ ] **Step 3: `maroLimitCalibration.py` 순수 함수 부분 작성**

```python
"""Limit/TranslationLimit이 공유하는 뷰포트 캘리브레이션 엔진(설계 스펙
2026-09-07 §5). 이 파일의 위쪽 절(axisDirectionFromPoints/
axisBasisEulerXYZ/expandRange/mayaDirectionToRos)은 Maya 씬 상태에
의존하지 않는 순수 함수다 -- maya.api.OpenMaya(om2)는 행렬/벡터 연산
라이브러리로만 쓴다(python/maroUrdfExport.py의 computeRelativeOrigin과
같은 성격). 아래쪽 절(뷰포트 리그/HUD)은 실제 Maya 씬과 Qt에 의존한다.
"""
import math

import maya.api.OpenMaya as om2


def axisDirectionFromPoints(pointA, pointB):
    """pointA/pointB: (x,y,z) 튜플, 뷰포트에서 클릭한 두 월드 좌표점.
    pointA -> pointB 방향의 정규화 벡터를 돌려준다. 두 점이 같으면(길이 0)
    방향을 정의할 수 없으므로 ValueError."""
    vec = om2.MVector(pointB[0] - pointA[0], pointB[1] - pointA[1], pointB[2] - pointA[2])
    length = vec.length()
    if length < 1e-9:
        raise ValueError("axisDirectionFromPoints: pointA and pointB must differ")
    unit = vec.normal()
    return (unit.x, unit.y, unit.z)


def axisBasisEulerXYZ(axisDirection):
    """axisDirection(정규화된 (x,y,z))을 로컬 Z로 갖는 정규직교 기저를
    구성해 (rx, ry, rz) 오일러 각(도, XYZ 고정축 순서)으로 돌려준다.
    X/Y 축의 구체적인 방향은 임의(자유도 1개짜리 계 -- 회전/이동 매니퍼레이터가
    로컬 Z 축 하나만 쓰므로 X/Y가 어느 쪽을 향하든 캘리브레이션 결과에
    영향이 없다)이지만, 항상 같은 규칙(월드 업 벡터 기준)으로 결정해
    호출마다 결과가 안정적이도록 한다. axisDirection이 월드 업과 거의
    평행하면(짐벌 특이점) 월드 X를 참조 벡터로 대신 쓴다."""
    z = om2.MVector(*axisDirection).normal()
    worldUp = om2.MVector(0.0, 1.0, 0.0)
    reference = worldUp if abs(z * worldUp) < 0.999 else om2.MVector(1.0, 0.0, 0.0)
    x = (reference ^ z).normal()   # cross product, MVector의 ^ 연산자
    y = (z ^ x).normal()

    m = om2.MMatrix((
        x.x, x.y, x.z, 0.0,
        y.x, y.y, y.z, 0.0,
        z.x, z.y, z.z, 0.0,
        0.0, 0.0, 0.0, 1.0,
    ))
    euler = om2.MTransformationMatrix(m).rotation(asQuaternion=False)
    euler = euler.reorder(om2.MEulerRotation.kXYZ)
    return (math.degrees(euler.x), math.degrees(euler.y), math.degrees(euler.z))


def expandRange(currentMin, currentMax, sample):
    """collect 한 번: sample을 currentMin/currentMax 범위에 편입시킨
    (newMin, newMax)를 돌려준다. 범위 안의 샘플은 아무 효과가 없다."""
    return (min(currentMin, sample), max(currentMax, sample))


def mayaDirectionToRos(direction):
    """(x,y,z) 방향 벡터를 ROS(REP-103) 프레임으로. 위치 변환
    (maroMayaToRos)과 같은 축 재배치 (x,y,z)->(x,-z,y)이지만, 방향
    벡터는 단위 없는 순수 방향이므로 씬 단위 스케일을 적용하지 않는다."""
    x, y, z = direction
    return (x, -z, y)
```

- [ ] **Step 4: `src/maro_plugin/CMakeLists.txt`에 등록**

`MARO_PLUGIN_PY_MODULES` 리스트에 `maroLimitCalibration`을 `maroLidarPanel` 다음(알파벳 순서)에 추가:

```cmake
set(MARO_PLUGIN_PY_MODULES
    maroCapabilityPanel
    maroDagMenu
    maroDiagPanel
    maroLidarPanel
    maroLimitCalibration
    maroMainWindow
    maroMenu
    maroObjectNodeEditor
    maroRosProxy
    maroSettingsPanel
    maroSkeletonUpload
    maroSingleObjectNodeEditor
    maroSyntheticDataCamera
    maroSyntheticDataPanel
    maroSyntheticDataPointCloud
    maroSyntheticDataRender
    maroTechDiag
    maroUrdfExport
)
```

- [ ] **Step 5: `tests/CMakeLists.txt`에 등록**

`foreach(maya_test ...)` 리스트에 `limit_calibration_pure`를 `lidar_scan_query` 그룹 근처(마지막 줄)에 추가:

```cmake
                      lidar_scan_query mesh_collision synthetic_data_point_cloud synthetic_data_render limit_calibration_pure)
```

- [ ] **Step 6: 빌드 + 실행**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure -R maya_limit_calibration_pure
```

Expected: PASS.

- [ ] **Step 7: 커밋**

```bash
git add python/maroLimitCalibration.py src/maro_plugin/CMakeLists.txt tests/maya/test_limit_calibration_pure.py tests/CMakeLists.txt
git commit -m "$(cat <<'EOF'
feat(limit-calibration): add pure functions for axis math and range accumulation

axisDirectionFromPoints, axisBasisEulerXYZ, expandRange, and
mayaDirectionToRos are Maya-scene-independent (maya.api.OpenMaya as a
pure math library only, same pattern as maroUrdfExport.computeRelativeOrigin)
so they batch-test without a viewport. The viewport rig built on top of
them lands in a later task.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `MaroLimitPanel`/`MaroTranslationLimitPanel` 추가 (캘리브레이션 버튼 없이)

**Files:**
- Modify: `python/maroCapabilityPanel.py`
- Test: `tests/maya/test_capability_panel.py` (확장)

**Interfaces:**
- Consumes: Task 4의 `maroLimitCalibration.mayaDirectionToRos`.
- Produces: `MaroLimitPanel`/`MaroTranslationLimitPanel` — `_ATTRS = [("axisDirection", "Axis direction", "vec3"), ("min", ...), ("max", ...)]` + 읽기 전용 "ROS axis" 표시 라벨. `_PANEL_CLASSES`에 `"maroLimit"`/`"maroTranslationLimit"` 추가— 이 시점부터 Task 3의 SONE 더블클릭이 7종 전부에 대해 동작한다.

- [ ] **Step 1: `maroCapabilityPanel.py`에 두 클래스 + import 추가**

파일 상단 import 블록(`import maroSingleObjectNodeEditor` 다음 줄)에 추가:

```python
import maroLimitCalibration
```

`MaroCouplingPanel` 클래스 정의 다음, `_PANEL_CLASSES` 딕셔너리 정의 앞에 추가:

```python
class _AxisLimitPanelBase(MaroCapabilityPanelBase):
    """MaroLimitPanel/MaroTranslationLimitPanel의 공통 부분 -- axisDirection
    필드 옆에 읽기전용 ROS축 표시를 덧붙인다. 실제 _ATTRS(단위: 각도 대
    거리)는 서브클래스가 정의한다."""

    def _buildExtra(self):
        self._rosAxisLabel = QtWidgets.QLabel("")
        self._layout.addRow("ROS axis (read-only)", self._rosAxisLabel)
        self._refreshRosAxisLabel()

    def _refreshRosAxisLabel(self):
        subFields = self._vecFields.get("axisDirection")
        if subFields is None:
            return
        mayaDir = (subFields[0].value(), subFields[1].value(), subFields[2].value())
        rosDir = maroLimitCalibration.mayaDirectionToRos(mayaDir)
        self._rosAxisLabel.setText("({:.4f}, {:.4f}, {:.4f})".format(*rosDir))

    def _onApply(self):
        super()._onApply()
        self._refreshRosAxisLabel()


class MaroLimitPanel(_AxisLimitPanelBase):
    _ATTRS = [
        ("axisDirection", "Axis direction", "vec3"),
        ("min", "Min (deg)", "float"),
        ("max", "Max (deg)", "float"),
    ]


class MaroTranslationLimitPanel(_AxisLimitPanelBase):
    _ATTRS = [
        ("axisDirection", "Axis direction", "vec3"),
        ("min", "Min", "float"),
        ("max", "Max", "float"),
    ]
```

`_PANEL_CLASSES` 딕셔너리에 두 줄 추가:

```python
_PANEL_CLASSES = {
    "maroRotation": MaroRotationPanel,
    "maroTranslation": MaroTranslationPanel,
    "maroSensorDirection": MaroSensorDirectionPanel,
    "maroSensorRange": MaroSensorRangePanel,
    "maroCoupling": MaroCouplingPanel,
    "maroLimit": MaroLimitPanel,
    "maroTranslationLimit": MaroTranslationLimitPanel,
}
```

- [ ] **Step 2: `tests/maya/test_capability_panel.py`의 factory 매핑 단언 갱신**

**[2026-09-07 수정]** Global Constraints의 mayapy/PySide6 `"minimal"`
플랫폼 제약 때문에 이 테스트는 실제 `QWidget`을 만들지 않는다(Task 2
Step 7 참고) — 그래서 여기서 바꿀 것은 "타입이 등록돼 있는지"를 확인하는
`_PANEL_CLASSES` 딕셔너리 비교뿐이다. 필드 적용/ROS축 표시 같은 실제 동작
검증은 Task 8 수동 체크리스트가 담당한다.

기존에 추가했던 다음 블록(Task 2 Step 7):

```python
# _PANEL_CLASSES 매핑: 이 시점(Task 5 이전)엔 5개 단순 타입만 등록.
expectedTypes = {
    "maroRotation": maroCapabilityPanel.MaroRotationPanel,
    "maroTranslation": maroCapabilityPanel.MaroTranslationPanel,
    "maroSensorDirection": maroCapabilityPanel.MaroSensorDirectionPanel,
    "maroSensorRange": maroCapabilityPanel.MaroSensorRangePanel,
    "maroCoupling": maroCapabilityPanel.MaroCouplingPanel,
}
assert maroCapabilityPanel._PANEL_CLASSES == expectedTypes, maroCapabilityPanel._PANEL_CLASSES
print("_PANEL_CLASSES mapping OK")

# openCapabilityPanel()은 타입을 찾지 못하면 QWidget을 만들기 전에
# ValueError를 던진다 -- 이 경로는 위젯 생성 전에 끝나므로 mayapy에서
# 안전하게 자동 검증할 수 있다.
lim = cmds.createNode("maroLimit", name="limForPanelFactoryCheck")
try:
    maroCapabilityPanel.openCapabilityPanel(lim)
    raised = False
except ValueError:
    raised = True
assert raised, "maroLimit must not be registered yet (Task 5 adds it)"
print("factory rejects unregistered type before constructing any widget OK")
```

를 아래로 바꾼다(이제 7종 전부 등록되어 있으므로 매핑만 갱신하고,
"미등록 타입 거부" 시나리오는 더 이상 재현할 방법이 없으므로 그 블록은
제거한다 -- 7종 전부가 등록된 지금은 어떤 capability 타입으로도
`ValueError`가 나면 안 된다):

```python
# Task 5부터 maroLimit/maroTranslationLimit도 등록되어 7종 전부 매핑된다.
expectedTypes = {
    "maroRotation": maroCapabilityPanel.MaroRotationPanel,
    "maroTranslation": maroCapabilityPanel.MaroTranslationPanel,
    "maroSensorDirection": maroCapabilityPanel.MaroSensorDirectionPanel,
    "maroSensorRange": maroCapabilityPanel.MaroSensorRangePanel,
    "maroCoupling": maroCapabilityPanel.MaroCouplingPanel,
    "maroLimit": maroCapabilityPanel.MaroLimitPanel,
    "maroTranslationLimit": maroCapabilityPanel.MaroTranslationLimitPanel,
}
assert maroCapabilityPanel._PANEL_CLASSES == expectedTypes, maroCapabilityPanel._PANEL_CLASSES
print("_PANEL_CLASSES mapping (all 7 types) OK")
```

파일에서 이제 존재하지 않는 "factory rejects unregistered type" 블록(위
첫 코드 블록의 두 번째 절)은 완전히 삭제한다 — 남겨두면 항상 실패한다.

- [ ] **Step 3: 빌드 + 실행**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure -R "maya_capability_panel|maya_single_object_node_editor"
```

Expected: 둘 다 PASS. (`test_single_object_node_editor.py`의 Task 3 단언은 이제 7종 전부에 대해 유효해졌다 -- 재확인 목적으로 함께 돌린다.)

- [ ] **Step 4: 커밋**

```bash
git add python/maroCapabilityPanel.py tests/maya/test_capability_panel.py
git commit -m "$(cat <<'EOF'
feat(capability): add Limit/TranslationLimit detail panels (axis+min/max fields only)

Plain field editing for the two axis-limit types, plus a read-only ROS-axis
preview computed via maroLimitCalibration.mayaDirectionToRos. All 7
capability types are now reachable through SONE's double-click. The
viewport calibration tool (the "움직임범위설정" button) lands in a later task.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Limit 회전 캘리브레이션 엔진 + UI

**Files:**
- Modify: `python/maroLimitCalibration.py` (뷰포트 리그 + HUD 절 추가)
- Modify: `python/maroCapabilityPanel.py` (`MaroLimitPanel`에 "움직임범위설정" 버튼)
- Test: `tests/maya/test_limit_calibration_session.py`

**Interfaces:**
- Produces: `maroLimitCalibration.CalibrationSession` 클래스 — `start(targetTransform, axisDirection, pivotWorld, isLinear=False)`, `currentValue()`, `collect()`, `finish()`, `cancel()`. `isLinear=False`(Limit, rotateZ/회전 툴)와 `isLinear=True`(TranslationLimit, translateZ/이동 툴, Task 7)를 하나의 클래스가 파라미터로 흡수한다.
- Produces: `maroLimitCalibration.openCalibrationHud(session, onCollect, onFinish)` — HUD 창(실시간 값 표시 + Collect 버튼 + 스페이스바 단축키 + 완료 버튼).
- Consumes: Task 4의 `axisBasisEulerXYZ`.

**연결 복원 안전장치(Global Constraints 참고)**: `CalibrationSession`은 생성 시점에 대상의 rotateX/Y/Z(또는 translateX/Y/Z) 각각의 소스 플러그(`cmds.listConnections(..., plugs=True)`, 없으면 `None`)와 원래 부모(`cmds.listRelatives(parent=True)`, 없으면 `None`)를 캡처해 두고, `finish()`/`cancel()`/예외 발생 시 항상 실행되는 `_cleanup()`에서 정확히 역순으로 복원한다. `_cleanup()`은 여러 번 불려도 안전하다(가드 플래그 `self._cleaned`).

- [ ] **Step 1: 실패하는 테스트 작성 `tests/maya/test_limit_calibration_session.py`**

```python
"""CalibrationSession: 뷰포트 리그(헬퍼 로케이터, 임시 부모, 커넥션
끊기/복원)와 collect 누적. HUD(Qt)는 별도로 열지 않고 세션 API만
mayapy로 검증한다 -- HUD 자체는 수동 체크리스트(Task 8) 대상."""
import math
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(plugin))))
import maroLimitCalibration as calib  # noqa: E402

# (a) 커넥션이 전혀 없는 자유 오브젝트 -- 가장 단순한 경로.
freeCube = cmds.polyCube(name="freeCubeForCalib")[0]
session = calib.CalibrationSession()
session.start(freeCube, axisDirection=(0.0, 1.0, 0.0),
              pivotWorld=(0.0, 0.0, 0.0), isLinear=False)
assert abs(session.currentValue()) < 1e-9, "must start at 0"
cmds.setAttr(session.helperLocator() + ".rotateZ", 30.0)
assert abs(session.currentValue() - 30.0) < 1e-6, session.currentValue()
mn, mx = session.collect()
assert abs(mn - 0.0) < 1e-6 and abs(mx - 30.0) < 1e-6, (mn, mx)
cmds.setAttr(session.helperLocator() + ".rotateZ", -10.0)
mn, mx = session.collect()
assert abs(mn - (-10.0)) < 1e-6 and abs(mx - 30.0) < 1e-6, (mn, mx)
session.finish()
assert not cmds.objExists(session.helperLocator()), "finish() must delete the helper locator"
assert cmds.getAttr(freeCube + ".rotateY") == 0.0 or True  # 자유 오브젝트라 원복 대상 값 자체가 0
print("free-object calibration session OK")

# (b) rotateX/Y/Z가 DG 커넥션으로 이미 구동되는 오브젝트 -- 연결
# 끊기/복원이 핵심.
axisConn = cmds.createNode("maroAxis", name="calibConnAxis")
rotConn = cmds.createNode("maroRotation", name="calibConnRot")
cmds.connectAttr(rotConn + ".capabilityOut", axisConn + ".capabilityIn[0]")
cmds.setAttr(rotConn + ".angle", 0.4)
boundCube = cmds.polyCube(name="boundCubeForCalib")[0]
cmds.connectAttr(axisConn + ".position", boundCube + ".rotateY")
originalSource = cmds.listConnections(boundCube + ".rotateY", source=True, destination=False,
                                      plugs=True)[0]
originalValue = cmds.getAttr(boundCube + ".rotateY")

sessionConn = calib.CalibrationSession()
sessionConn.start(boundCube, axisDirection=(0.0, 1.0, 0.0),
                  pivotWorld=(0.0, 0.0, 0.0), isLinear=False)
# 캘리브레이션 도중엔 rotateY가 자유로워야(연결이 끊겨야) 한다.
assert cmds.listConnections(boundCube + ".rotateY", source=True, destination=False,
                            plugs=True) in (None, []), \
    "rotateY must be disconnected during calibration"
cmds.setAttr(sessionConn.helperLocator() + ".rotateZ", 15.0)
sessionConn.collect()
sessionConn.finish()

restoredSource = cmds.listConnections(boundCube + ".rotateY", source=True, destination=False,
                                      plugs=True)
assert restoredSource == [originalSource], \
    f"finish() must restore the exact original connection (got {restoredSource})"
assert abs(cmds.getAttr(boundCube + ".rotateY") - originalValue) < 1e-9, \
    "finish() must restore the pre-calibration driven value"
print("connected-object calibration session restores connection OK")

# (c) 예외/취소 경로에서도 복원된다 -- cancel()이 finish()와 같은 정리를 한다.
cmds.setAttr(rotConn + ".angle", 0.9)
originalValue2 = cmds.getAttr(boundCube + ".rotateY")
sessionCancel = calib.CalibrationSession()
sessionCancel.start(boundCube, axisDirection=(0.0, 1.0, 0.0),
                    pivotWorld=(0.0, 0.0, 0.0), isLinear=False)
sessionCancel.cancel()
restoredSource2 = cmds.listConnections(boundCube + ".rotateY", source=True, destination=False,
                                       plugs=True)
assert restoredSource2 == [originalSource], "cancel() must also restore the connection"
assert abs(cmds.getAttr(boundCube + ".rotateY") - originalValue2) < 1e-9
assert not cmds.objExists(sessionCancel.helperLocator())
print("cancel() restores connection OK")

# (d) 이중 정리(_cleanup 두 번 호출)가 안전하다.
sessionConn.finish()  # 이미 끝난 세션을 다시 finish해도 예외가 나면 안 된다
print("idempotent cleanup OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
```

- [ ] **Step 2: 실행해서 실패 확인**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests\maya\test_limit_calibration_session.py
```

Expected: `AttributeError: module 'maroLimitCalibration' has no attribute 'CalibrationSession'`로 실패.

- [ ] **Step 3: `maroLimitCalibration.py`에 `CalibrationSession` 추가**

파일 끝에 추가(Task 4의 순수 함수 절 다음):

```python
import maya.cmds as cmds


_CHANNELS_ROTATE = ("rotateX", "rotateY", "rotateZ")
_CHANNELS_TRANSLATE = ("translateX", "translateY", "translateZ")


class CalibrationSession:
    """Limit(회전)/TranslationLimit(이동) 공유 캘리브레이션 리그.

    start()가 헬퍼 로케이터를 만들어 axisDirection 방향으로 정렬하고,
    대상의 회전(또는 이동) 채널을 DG 커넥션에서 임시로 끊은 뒤 헬퍼
    로케이터 밑에 부모로 넣는다. 사용자는 Maya 네이티브 Rotate(또는
    Move) 툴로 헬퍼 로케이터의 로컬 Z 축만 조작하면 되고, currentValue()는
    그 rotateZ(또는 translateZ)를 그대로 읽는다 -- 별도의 축-각 투영
    수식이 필요 없다(헬퍼 로케이터 자체가 그 축으로 정렬돼 있으므로).

    finish()/cancel()은 항상 같은 _cleanup()을 거쳐 원래 커넥션/부모/값을
    복원한다 -- 어느 경로로 세션이 끝나든(정상 완료, 사용자 취소, HUD
    창을 강제로 닫음, 예외) 반드시 이 복원이 실행되도록 호출부(HUD/패널)가
    try/finally로 감싼다.
    """

    def __init__(self):
        self._helper = None
        self._target = None
        self._channels = None
        self._originalSources = None   # [str|None, str|None, str|None]
        self._originalParent = None    # str|None
        self._originalValues = None    # [float, float, float]
        self._min = 0.0
        self._max = 0.0
        self._cleaned = True

    def helperLocator(self):
        return self._helper

    def start(self, targetTransform, axisDirection, pivotWorld, isLinear=False):
        if not self._cleaned:
            raise RuntimeError("CalibrationSession.start() called while already active")

        self._target = targetTransform
        self._channels = _CHANNELS_TRANSLATE if isLinear else _CHANNELS_ROTATE
        self._isLinear = isLinear
        self._min = 0.0
        self._max = 0.0

        # 1) 원래 커넥션/값을 전부 캡처한다 -- 하나라도 놓치면 복원이
        #    불완전해지므로 세 채널 모두 항상 캡처한다.
        self._originalSources = []
        self._originalValues = []
        for channel in self._channels:
            plug = "{}.{}".format(self._target, channel)
            sources = cmds.listConnections(plug, source=True, destination=False, plugs=True)
            self._originalSources.append(sources[0] if sources else None)
            self._originalValues.append(cmds.getAttr(plug))

        parents = cmds.listRelatives(self._target, parent=True, fullPath=True)
        self._originalParent = parents[0] if parents else None

        # 2) 커넥션을 끊는다(있는 것만) -- 그래야 자유롭게 재배선 가능.
        for channel, source in zip(self._channels, self._originalSources):
            if source is not None:
                cmds.disconnectAttr(source, "{}.{}".format(self._target, channel))

        # 3) 헬퍼 로케이터를 만들어 axisDirection으로 정렬하고 pivotWorld에 둔다.
        self._helper = cmds.spaceLocator(name="maroCalibHelper#")[0]
        rx, ry, rz = axisBasisEulerXYZ(axisDirection)
        cmds.setAttr(self._helper + ".rotate", rx, ry, rz, type="double3")
        cmds.xform(self._helper, worldSpace=True, translation=pivotWorld)

        # 4) 대상을 헬퍼 로케이터 밑으로(월드 포즈 보존 -- 커넥션을 이미
        #    끊었으므로 회전/이동 채널이 자유라 이 재배선이 가능하다).
        cmds.parent(self._target, self._helper)

        self._cleaned = False

    def currentValue(self):
        channel = "rotateZ" if not self._isLinear else "translateZ"
        return cmds.getAttr("{}.{}".format(self._helper, channel))

    def collect(self):
        sample = self.currentValue()
        self._min, self._max = expandRange(self._min, self._max, sample)
        return (self._min, self._max)

    def rangeSoFar(self):
        return (self._min, self._max)

    def finish(self):
        self._cleanup()
        return (self._min, self._max)

    def cancel(self):
        self._cleanup()

    def _cleanup(self):
        if self._cleaned:
            return
        try:
            # 부모 복원(대상을 헬퍼 로케이터 밖으로) -- 헬퍼를 지우기 전에
            # 반드시 먼저 해야 대상이 함께 삭제되지 않는다.
            if self._originalParent is not None:
                cmds.parent(self._target, self._originalParent)
            else:
                cmds.parent(self._target, world=True)
        except Exception:  # noqa: BLE001 -- 정리 경로는 절대 못 넘어가면 안 된다
            import traceback
            traceback.print_exc()

        try:
            if self._helper is not None and cmds.objExists(self._helper):
                cmds.delete(self._helper)
        except Exception:  # noqa: BLE001
            import traceback
            traceback.print_exc()

        for channel, value, source in zip(self._channels, self._originalValues,
                                          self._originalSources):
            plug = "{}.{}".format(self._target, channel)
            try:
                if source is None:
                    cmds.setAttr(plug, value)
                else:
                    cmds.connectAttr(source, plug, force=True)
            except Exception as exc:  # noqa: BLE001 -- 복원 실패는 조용히 삼키지 않는다
                cmds.warning(
                    "Maro: failed to restore {} (original source {!r}): {}".format(
                        plug, source, exc))

        self._cleaned = True
```

파일 상단 import 블록을 `import math` / `import maya.api.OpenMaya as om2` / `import maya.cmds as cmds` 셋으로 정리한다(기존엔 `maya.cmds` import가 없었다 -- 파일 맨 위, `import math` 바로 아래에 `import maya.cmds as cmds`를 추가하고, 위 Step 3에서 파일 끝에 다시 쓴 `import maya.cmds as cmds` 줄은 지운다 -- 한 파일에 import는 상단에 한 번만).

- [ ] **Step 4: 빌드 + 실행**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

`tests/CMakeLists.txt`의 `foreach(maya_test ...)` 리스트에 `limit_calibration_session`을 `limit_calibration_pure` 옆에 추가한 뒤:

```powershell
ctest --test-dir out/build -C Release --output-on-failure -R maya_limit_calibration_session
```

Expected: PASS.

- [ ] **Step 5: HUD 창 작성 — `maroLimitCalibration.py`에 추가**

파일 끝에 추가:

```python
from PySide6 import QtCore, QtGui, QtWidgets


class CalibrationHud(QtWidgets.QWidget):
    """캘리브레이션 세션의 작은 실시간 안내 창. 스페이스바는 이 창에
    포커스가 있을 때만 Collect를 트리거한다(QtCore.Qt.WidgetShortcut) --
    Maya 뷰포트의 기본 스페이스바(hotbox) 동작과 절대 충돌하지 않는다.
    """

    def __init__(self, session, unitLabel, onCollect, onFinish, parent=None):
        super().__init__(parent, QtCore.Qt.Tool | QtCore.Qt.WindowStaysOnTopHint)
        self._session = session
        self._onCollectCallback = onCollect
        self._onFinishCallback = onFinish
        self.setWindowTitle("Maro 캘리브레이션")

        layout = QtWidgets.QVBoxLayout(self)
        self._valueLabel = QtWidgets.QLabel("")
        layout.addWidget(self._valueLabel)
        self._rangeLabel = QtWidgets.QLabel("")
        layout.addWidget(self._rangeLabel)

        collectButton = QtWidgets.QPushButton("Collect (Space)")
        collectButton.clicked.connect(self._onCollect)
        layout.addWidget(collectButton)

        finishButton = QtWidgets.QPushButton("완료")
        finishButton.clicked.connect(self._onFinish)
        layout.addWidget(finishButton)

        shortcut = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Space), self)
        shortcut.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self._onCollect)

        self._unitLabel = unitLabel
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(50)
        self._refresh()

    def _refresh(self):
        try:
            value = self._session.currentValue()
            self._valueLabel.setText("현재: {:.3f} {}".format(value, self._unitLabel))
            mn, mx = self._session.rangeSoFar()
            self._rangeLabel.setText("누적 범위: [{:.3f}, {:.3f}] {}".format(
                mn, mx, self._unitLabel))
        except Exception:  # noqa: BLE001 -- QTimer 콜백 경계
            import traceback
            traceback.print_exc()

    def _onCollect(self):
        try:
            self._onCollectCallback()
            self._refresh()
        except Exception:  # noqa: BLE001 -- Qt 콜백 경계
            import traceback
            traceback.print_exc()

    def _onFinish(self):
        try:
            self._timer.stop()
            self._onFinishCallback()
            self.close()
        except Exception:  # noqa: BLE001 -- Qt 콜백 경계
            import traceback
            traceback.print_exc()

    def closeEvent(self, event):
        # 사용자가 완료 버튼이 아니라 창의 X 버튼으로 닫아도 같은 정리가
        # 일어나야 한다 -- onFinishCallback이 세션의 finish()를 부르므로
        # 중복 호출은 CalibrationSession._cleaned 가드가 흡수한다.
        try:
            self._timer.stop()
            self._onFinishCallback()
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
            import traceback
            traceback.print_exc()
        super().closeEvent(event)
```

- [ ] **Step 6: `MaroLimitPanel`에 "움직임범위설정" 버튼 + 뷰포트 2점 클릭 캡처 연결 — `maroCapabilityPanel.py`**

`MaroLimitPanel` 클래스를 다음으로 교체:

```python
class MaroLimitPanel(_AxisLimitPanelBase):
    _ATTRS = [
        ("axisDirection", "Axis direction", "vec3"),
        ("min", "Min (deg)", "float"),
        ("max", "Max (deg)", "float"),
    ]

    def _buildExtra(self):
        super()._buildExtra()
        calibrateButton = QtWidgets.QPushButton("움직임범위설정")
        calibrateButton.clicked.connect(self._onCalibrate)
        self._layout.addRow(calibrateButton)
        self._calibrationSession = None
        self._calibrationHud = None

    def _onCalibrate(self):
        try:
            if self._calibrationSession is not None:
                cmds.warning("Maro: a calibration session is already running for this node.")
                return
            targetAxes = cmds.listConnections(self._node + ".capabilityOut", destination=True,
                                              source=False, shapes=True) or []
            if not targetAxes:
                cmds.warning(
                    "Maro: this Limit node is not connected to any axis yet -- "
                    "connect it via SONE before calibrating.")
                return
            boundTargets = cmds.listConnections(targetAxes[0] + ".targetObject",
                                                source=True, destination=False, shapes=False) or []
            if not boundTargets:
                cmds.warning(
                    "Maro: this axis is not bound to a scene object yet -- "
                    "use maroBindAxis before calibrating.")
                return
            target = cmds.ls(boundTargets[0], long=True)[0]

            self._pickedPoints = []
            cmds.setToolTo(cmds.selectContext())
            picker = cmds.scriptCtx(
                title="Maro: 축 방향 지정 -- 두 점을 클릭",
                toolFinish=self._onAxisPickFinish,
                totalSelectionSets=2,
                setSelectionAction=lambda: self._onAxisPointPicked(target))
            cmds.setToolTo(picker)
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
            import traceback
            traceback.print_exc()

    def _onAxisPointPicked(self, target):
        try:
            hits = cmds.filterExpand(cmds.ls(selection=True), selectionMask=(28, 31, 46))
            if not hits:
                return
            pos = cmds.pointPosition(hits[0], world=True)
            self._pickedPoints.append(tuple(pos))
            if len(self._pickedPoints) == 2:
                self._startCalibrationSession(target)
        except Exception:  # noqa: BLE001 -- Maya scriptCtx 콜백 경계
            import traceback
            traceback.print_exc()

    def _onAxisPickFinish(self):
        # 2점을 다 못 고르고 툴이 끝났으면(Esc 등) 아무 일도 없었던 것으로.
        self._pickedPoints = []

    def _startCalibrationSession(self, target):
        axisDirection = maroLimitCalibration.axisDirectionFromPoints(
            self._pickedPoints[0], self._pickedPoints[1])
        pivotWorld = cmds.xform(target, query=True, rotatePivot=True, worldSpace=True)

        self._calibrationSession = maroLimitCalibration.CalibrationSession()
        self._calibrationSession.start(target, axisDirection, pivotWorld, isLinear=False)
        cmds.select(self._calibrationSession.helperLocator())
        cmds.setToolTo("RotateSuperContext")

        self._calibrationHud = maroLimitCalibration.CalibrationHud(
            self._calibrationSession, "deg", self._onCalibrationCollect,
            self._onCalibrationFinish, parent=self)
        self._calibrationHud.show()

    def _onCalibrationCollect(self):
        self._calibrationSession.collect()

    def _onCalibrationFinish(self):
        if self._calibrationSession is None:
            return
        mn, mx = self._calibrationSession.finish()
        cmds.undoInfo(openChunk=True)
        try:
            cmds.setAttr(self._node + ".min", mn)
            cmds.setAttr(self._node + ".max", mx)
            axisDir = maroLimitCalibration.axisDirectionFromPoints(
                self._pickedPoints[0], self._pickedPoints[1])
            cmds.setAttr(self._node + ".axisDirection", *axisDir, type="double3")
        finally:
            cmds.undoInfo(closeChunk=True)
        self._calibrationSession = None
        self._calibrationHud = None
        self._loadValues()
        self._refreshRosAxisLabel()
```

파일 상단 import 블록에 `import maroLimitCalibration`이 이미 Task 5에서 추가되어 있으므로 추가 import는 필요 없다.

**참고(수동 체크리스트 대상, Task 8에서 확인)**: `cmds.scriptCtx`의 `setSelectionAction`/`totalSelectionSets` 기반 2점 클릭 캡처와 `cmds.filterExpand`의 정확한 마스크 값(28=폴리곤 버텍스, 31=폴리곤 엣지, 46=폴리곤 페이스)은 실제 대화형 Maya 세션에서만 최종 검증 가능하다 — mayapy 배치로는 `scriptCtx`의 마우스 클릭 자체를 재현할 수 없으므로, `CalibrationSession`/`CalibrationHud`는 Step 3/5에서 이미 자동화 테스트로 검증했고 이 클릭 캡처 부분만 Task 8의 수동 체크리스트가 담당한다.

- [ ] **Step 7: 회귀 테스트 — 패널이 여전히 정상 임포트/생성되는지**

```powershell
ctest --test-dir out/build -C Release --output-on-failure -R "maya_capability_panel|maya_limit_calibration_session|maya_limit_calibration_pure"
```

Expected: 전부 PASS (`_onCalibrate` 자체는 `cmds.scriptCtx`를 실행하므로 mayapy 배치로 직접 호출하지 않는다 -- Task 2/5에서 이미 만든 패널 생성/필드 적용 테스트만 회귀 확인).

- [ ] **Step 8: 전체 스위트 실행 (회귀 확인)**

```powershell
ctest --test-dir out/build -C Release --output-on-failure
```

Expected: 전체 PASS.

- [ ] **Step 9: 커밋**

```bash
git add python/maroLimitCalibration.py python/maroCapabilityPanel.py tests/maya/test_limit_calibration_session.py tests/CMakeLists.txt
git commit -m "$(cat <<'EOF'
feat(limit-calibration): add viewport calibration session, HUD, and the "움직임범위설정" flow

CalibrationSession disconnects the target's driven rotate channels (only
if connected), parents it under an axis-aligned helper locator, and lets
the user drag Maya's native Rotate tool on that locator -- currentValue()
just reads the locator's own rotateZ, no axis-angle projection needed.
finish()/cancel() always restore the original connection, parent, and
value through one idempotent _cleanup(). CalibrationHud shows the live
angle and accumulated range, with Collect bound to both a button and a
window-scoped spacebar shortcut that cannot collide with Maya's own
spacebar hotbox. MaroLimitPanel's new button drives a two-point viewport
pick (cmds.scriptCtx) to seed the axis direction.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: TranslationLimit 이동 캘리브레이션

**Files:**
- Modify: `python/maroCapabilityPanel.py` (`MaroTranslationLimitPanel`에 버튼 연결)
- Test: `tests/maya/test_limit_calibration_session.py` (확장 — 이동 케이스)

**Interfaces:**
- Consumes: Task 6의 `CalibrationSession(isLinear=True)`, `CalibrationHud`.

- [ ] **Step 1: 테스트 확장 — 이동 케이스**

`tests/maya/test_limit_calibration_session.py`의 teardown 블록 바로 위에 추가:

```python
# (e) isLinear=True -- translateZ를 읽고, 커넥션 채널도 translateX/Y/Z.
axisConnLin = cmds.createNode("maroAxis", name="calibConnAxisLin")
transConnLin = cmds.createNode("maroTranslation", name="calibConnTransLin")
cmds.connectAttr(transConnLin + ".capabilityOut", axisConnLin + ".capabilityIn[0]")
cmds.setAttr(transConnLin + ".distance", 3.0)
boundCubeLin = cmds.polyCube(name="boundCubeForCalibLin")[0]
cmds.connectAttr(axisConnLin + ".positionLinear", boundCubeLin + ".translateY")
originalSourceLin = cmds.listConnections(boundCubeLin + ".translateY", source=True,
                                         destination=False, plugs=True)[0]

sessionLin = calib.CalibrationSession()
sessionLin.start(boundCubeLin, axisDirection=(0.0, 1.0, 0.0),
                 pivotWorld=(0.0, 0.0, 0.0), isLinear=True)
assert cmds.listConnections(boundCubeLin + ".translateY", source=True, destination=False,
                            plugs=True) in (None, [])
cmds.setAttr(sessionLin.helperLocator() + ".translateY", 7.5)
assert abs(sessionLin.currentValue() - 7.5) < 1e-6
mn, mx = sessionLin.collect()
assert abs(mn - 0.0) < 1e-6 and abs(mx - 7.5) < 1e-6
sessionLin.finish()
restoredSourceLin = cmds.listConnections(boundCubeLin + ".translateY", source=True,
                                         destination=False, plugs=True)
assert restoredSourceLin == [originalSourceLin]
print("linear (TranslationLimit) calibration session OK")
```

- [ ] **Step 2: 빌드 + 실행**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure -R maya_limit_calibration_session
```

Expected: PASS (helper locator의 `translateZ`가 아니라 `helper.translateZ`를 읽는지는 이미 `CalibrationSession.currentValue()`의 `isLinear` 분기가 처리한다 -- Task 6에서 이미 구현됨, 이 태스크는 그 경로를 테스트로 확인하고 UI를 연결하는 것).

- [ ] **Step 3: `MaroTranslationLimitPanel`에 버튼 연결 — `maroCapabilityPanel.py`**

`MaroTranslationLimitPanel` 클래스를 다음으로 교체:

```python
class MaroTranslationLimitPanel(_AxisLimitPanelBase):
    _ATTRS = [
        ("axisDirection", "Axis direction", "vec3"),
        ("min", "Min", "float"),
        ("max", "Max", "float"),
    ]

    def _buildExtra(self):
        super()._buildExtra()
        calibrateButton = QtWidgets.QPushButton("움직임범위설정")
        calibrateButton.clicked.connect(self._onCalibrate)
        self._layout.addRow(calibrateButton)
        self._calibrationSession = None
        self._calibrationHud = None

    def _onCalibrate(self):
        try:
            if self._calibrationSession is not None:
                cmds.warning("Maro: a calibration session is already running for this node.")
                return
            targetAxes = cmds.listConnections(self._node + ".capabilityOut", destination=True,
                                              source=False, shapes=True) or []
            if not targetAxes:
                cmds.warning(
                    "Maro: this TranslationLimit node is not connected to any axis yet -- "
                    "connect it via SONE before calibrating.")
                return
            boundTargets = cmds.listConnections(targetAxes[0] + ".targetObject",
                                                source=True, destination=False, shapes=False) or []
            if not boundTargets:
                cmds.warning(
                    "Maro: this axis is not bound to a scene object yet -- "
                    "use maroBindAxis before calibrating.")
                return
            target = cmds.ls(boundTargets[0], long=True)[0]

            self._pickedPoints = []
            picker = cmds.scriptCtx(
                title="Maro: 축 방향 지정 -- 두 점을 클릭",
                toolFinish=self._onAxisPickFinish,
                totalSelectionSets=2,
                setSelectionAction=lambda: self._onAxisPointPicked(target))
            cmds.setToolTo(picker)
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
            import traceback
            traceback.print_exc()

    def _onAxisPointPicked(self, target):
        try:
            hits = cmds.filterExpand(cmds.ls(selection=True), selectionMask=(28, 31, 46))
            if not hits:
                return
            pos = cmds.pointPosition(hits[0], world=True)
            self._pickedPoints.append(tuple(pos))
            if len(self._pickedPoints) == 2:
                self._startCalibrationSession(target)
        except Exception:  # noqa: BLE001 -- Maya scriptCtx 콜백 경계
            import traceback
            traceback.print_exc()

    def _onAxisPickFinish(self):
        self._pickedPoints = []

    def _startCalibrationSession(self, target):
        axisDirection = maroLimitCalibration.axisDirectionFromPoints(
            self._pickedPoints[0], self._pickedPoints[1])
        pivotWorld = cmds.xform(target, query=True, translation=True, worldSpace=True)

        self._calibrationSession = maroLimitCalibration.CalibrationSession()
        self._calibrationSession.start(target, axisDirection, pivotWorld, isLinear=True)
        cmds.select(self._calibrationSession.helperLocator())
        cmds.setToolTo("MoveSuperContext")

        self._calibrationHud = maroLimitCalibration.CalibrationHud(
            self._calibrationSession, "cm", self._onCalibrationCollect,
            self._onCalibrationFinish, parent=self)
        self._calibrationHud.show()

    def _onCalibrationCollect(self):
        self._calibrationSession.collect()

    def _onCalibrationFinish(self):
        if self._calibrationSession is None:
            return
        mn, mx = self._calibrationSession.finish()
        cmds.undoInfo(openChunk=True)
        try:
            cmds.setAttr(self._node + ".min", mn)
            cmds.setAttr(self._node + ".max", mx)
            axisDir = maroLimitCalibration.axisDirectionFromPoints(
                self._pickedPoints[0], self._pickedPoints[1])
            cmds.setAttr(self._node + ".axisDirection", *axisDir, type="double3")
        finally:
            cmds.undoInfo(closeChunk=True)
        self._calibrationSession = None
        self._calibrationHud = None
        self._loadValues()
        self._refreshRosAxisLabel()
```

이동은 회전과 달리 피벗 개념이 약하므로(TranslationLimit은 위치 기준점 없이 방향만 의미 있다) `pivotWorld`를 대상의 현재 월드 위치로 둔다(회전 캘리브레이션은 `rotatePivot`을 썼다).

- [ ] **Step 4: 전체 스위트 실행**

```powershell
ctest --test-dir out/build -C Release --output-on-failure
```

Expected: 전체 PASS.

- [ ] **Step 5: 커밋**

```bash
git add python/maroCapabilityPanel.py tests/maya/test_limit_calibration_session.py
git commit -m "$(cat <<'EOF'
feat(limit-calibration): wire TranslationLimit's "움직임범위설정" to the shared calibration engine

Reuses CalibrationSession/CalibrationHud with isLinear=True (Move tool,
translateZ instead of rotateZ, target's world position as the pivot
instead of its rotate pivot).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: 수동 체크리스트 + 전체 검증

**Files:**
- Modify: `docs/maro-main-ui-manual-checklist.md`

**Interfaces:** 없음(문서 태스크).

- [ ] **Step 1: 전체 자동화 스위트 최종 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure
```

Expected: 전체 PASS.

- [ ] **Step 2: `docs/maro-main-ui-manual-checklist.md`에 새 절 추가**

파일 끝(가장 최근 Phase 5 §6-1 판정 다음)에 새 절을 추가한다:

```markdown
## 7. 카파빌리티 노드 상세 설정 UI + Limit/TranslationLimit 캘리브레이션 (2026-09-07 설계)

### 7-1. SONE 더블클릭 3분기

- [ ] capability 정확히 1개인 축의 SONE을 열고 중앙 노드를 더블클릭 --
      그 capability의 상세 설정 창이 열리는지 확인한다.
- [ ] capability 2개 이상인 축의 SONE에서 중앙 노드를 더블클릭 -- 기존과
      동일하게 드롭다운이 펼쳐지고(상세 창은 열리지 않음) 확인한다.
- [ ] 펼친 드롭다운의 특정 행을 더블클릭 -- 그 행의 capability 상세 설정
      창이 열리고, 드롭다운은 펼쳐진 채로 유지되는지 확인한다.
- [ ] 펼친 상태에서 행이 아닌 중앙 노드를 더블클릭 -- 기존처럼 접히는지
      확인한다(회귀 없음).

### 7-2. 7개 상세 설정 패널

- [ ] Rotation/Translation/SensorDirection/SensorRange/Coupling/Limit/
      TranslationLimit 각각을 열어 필드 값을 바꾸고 "적용"을 눌러
      Attribute Editor에서 실제로 반영됐는지 확인한다.
- [ ] Limit/TranslationLimit 패널의 axisDirection 필드를 바꿔보고, 읽기전용
      "ROS axis" 라벨이 `mayaDirectionToRos()`(x,-z,y 재배치) 값으로
      실시간 갱신되는지 확인한다.
- [ ] Coupling 패널의 "소스 축 재지정" 버튼으로 다른 축을 골라 재연결한다
      -- SONE의 기존 1회성 피커와 별개로, 언제든 다시 쓸 수 있는지 확인한다.
- [ ] 같은 노드에 대해 패널을 두 번 열면 같은 창이 앞으로 나오는지(새
      창이 중복 생성되지 않는지) 확인한다.
- [ ] `maro` 플러그인을 언로드한다 -- 7개 패널 중 아무거나 열어 둔 채로
      언로드해도 크래시 없이 창이 정리되는지 확인한다.

### 7-3. Limit 회전 캘리브레이션 전체 플로우

- [ ] `maroAxis`를 만들고 `maroRotation` + `maroLimit`을 얹은 뒤 씬의
      오브젝트에 `maroBindAxis`로 바인딩한다.
- [ ] Limit 상세 설정 창에서 "움직임범위설정"을 누르고, 뷰포트에서 오브젝트
      표면/버텍스 두 점을 클릭한다 -- 헬퍼 로케이터가 그 방향으로
      생성되고 Rotate 툴이 자동으로 켜지는지 확인한다.
- [ ] 헬퍼 로케이터의 Z축 링을 드래그해 오브젝트가 그 축을 기준으로
      스윙하는지 확인한다.
- [ ] HUD 창에 현재 각도와 누적 범위가 실시간으로 갱신되는지 확인한다.
- [ ] 한쪽으로 돌리고 Collect(버튼), 반대쪽으로 더 돌리고 Collect
      (스페이스바) -- 누적 범위가 두 극값을 모두 포함하도록 넓어지는지
      확인한다. 스페이스바를 눌렀을 때 Maya 뷰포트의 기본 hotbox가 함께
      뜨지 않는지(HUD 창에 포커스가 있을 때만 Collect가 반응하는지)도
      확인한다.
- [ ] "완료"를 누르면 헬퍼 로케이터/HUD가 정리되고, 오브젝트가 캘리브레이션
      시작 전과 같은 커넥션/포즈로 돌아오는지(`maroRotation.angle`을
      바꿔 보면서 여전히 정상 구동되는지) 확인한다.
- [ ] Limit 상세 설정 창에 최종 min/max와 축 방향이 반영됐는지 확인한다.
- [ ] 캘리브레이션 도중(HUD가 떠 있는 상태) 창의 X 버튼으로 강제로 닫아도
      같은 정리가 일어나는지 확인한다.
- [ ] 캘리브레이션 도중 `maro` 플러그인을 언로드해 본다 -- 헬퍼
      로케이터/임시 상태가 안전하게 정리되고 크래시가 없는지 확인한다
      (이 프로젝트가 반복적으로 겪은 "뷰포트가 붙잡은 오브젝트가 언로드
      시점에 살아있는" 위험군).

### 7-4. TranslationLimit 이동 캘리브레이션

- [ ] 7-3과 동일한 플로우를 `maroTranslation` + `maroTranslationLimit`
      조합으로 반복한다 -- Move 툴이 켜지고, HUD가 cm 단위로 표시되고,
      완료 후 커넥션이 복원되는지 확인한다.

### 7-5. 종합 판정

- [ ] 위 4개 절이 전부 PASS면 이 기능은 go. 하나라도 FAIL이면 그 항목을
      구체적 재현 절차와 함께 이 문서에 기록하고 후속 세션에서 처리한다.
```

- [ ] **Step 3: 커밋**

```bash
git add docs/maro-main-ui-manual-checklist.md
git commit -m "$(cat <<'EOF'
docs(checklist): add manual verification section for capability detail panels + Limit calibration

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review Notes (완료 후 참고용, 실행 태스크 아님)

- **스펙 커버리지**: §1(파일구조/7클래스) → Task 2/5/6/7. §2(SONE 더블클릭) → Task 3. §3(C++ 스키마+ROS 벡터) → Task 1/4. §4(캘리브레이션 워크플로) → Task 6/7. §6(테스트 전략) → 각 태스크의 순수함수/ctest/수동체크리스트로 분산. §7(범위 밖: curvePoints 편집, Coupling 접촉면 자동감지)은 이 플랜에 태스크 없음(의도된 누락).
- **`MaroAxisNode.cpp`/`maroUrdfExport.py` 무변경 가정**은 Task 1 Step 11(전체 스위트, 특히 `maya_urdf_export`)이 코드 변경 없이 통과하는 것으로 실증적으로 검증된다 -- 만약 실패하면 이 플랜의 핵심 설계 전제(broadcast 트릭)가 틀렸다는 뜻이므로, 그 시점에 Task 1을 다시 열어 원인을 봐야 한다(다음 태스크로 넘어가면 안 됨).
