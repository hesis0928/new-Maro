# Maro Phase 5 — LiDAR 설정 + 실시간 포인트클라우드 시각화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `maroLidar`를 네이티브 마킹메뉴에서 생성/설정할 수 있게 하고, 스캔 결과를 이 코드베이스 최초의 Viewport 2.0 드로우 오버라이드로 ROS 뷰포트에 실시간 포인트클라우드로 그린다.

**Architecture:** 가장 위험한 가정(임의 포인트 버퍼를 Viewport 2.0에 그리고 언로드해도 안전한가)부터 LiDAR와 완전히 무관하게 증명한 뒤(Task 1), 브리지 독립적인 1회성 스냅샷 파이프라인을 쌓고(Task 2-3), 네이티브 마킹메뉴 형제 항목 + 설정 팝업으로 사용자 진입점을 연결하고(Task 4), 마지막으로 라이브 갱신을 얹는다(Task 5). LiDAR가 UI에 노출된 뒤에야 의미 있는 Tech Diag 후속 검사를 마지막에 붙인다(Task 6).

**Tech Stack:** C++17 / Maya 2026 devkit (`MPxLocatorNode`, `MHWRender::MPxDrawOverride`, `MDrawRegistry`), Embree 4(`maro_lidar`), Python 3 / PySide6(Qt) / `maya.cmds` / `maya.api.OpenMaya`, CMake + CTest(GoogleTest + mayapy 시나리오).

## Global Constraints

- `maroPointCloud.points`는 반드시 `setStorable(false)` — 스캔 스냅샷을 `.ma`에 저장하지 않는다.
- `addUIDrawables()`에서 DG를 절대 건드리지 않는다 — `prepareForDraw()`에서 이미 다 읽어 둔 `MUserData`만 쓴다.
- 드로우 오버라이드 언로드 순서: `MDrawRegistry::deregisterDrawOverrideCreator`가 `plugin.deregisterNode(MaroPointCloudNode::id)`보다 반드시 먼저.
- 라이브 프리뷰의 플러그 쓰기는 `cmds`/`MDGModifier`를 거치지 않는다(Phase 3 idle-loop 교훈 — undo 큐를 매 틱 도배하지 않는다). `MPlug::setValue`로 raw write.
- placeholder sphere 생성은 메쉬 없는 오브젝트에 사용자가 명시적으로 "Maro LiDAR" 마킹메뉴 항목을 클릭했을 때만 일어난다. 다른 어떤 흐름에서도 씬에 임의로 지오메트리를 추가하지 않는다.
- Tech Diag 후속 검사는 기존 `boad`/`book` 디버깅 Diag와 완전히 독립적이며, `maroTechDiag.py`가 이미 쓰는 present-then-approve 패턴(순수 검사 함수 + `_CheckSidePanel`의 "실행" 버튼 + 있으면 "적용" 버튼)을 그대로 따른다.
- 각 태스크 완료 후 반드시 다음을 실행한다(이전 세션에서 필터링된 `ctest -R` 서브셋만 돌려 검증 공백이 생긴 전례가 있다 — 항상 전체 스위트):
  ```powershell
  cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
      if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
  }
  cmake --build out/build --config Release
  ctest --test-dir out/build -C Release --output-on-failure
  ```
- Task 1, 4(마킹메뉴 항목 노출 자체와 설정 팝업 UI), 5는 실제 뷰포트 렌더링/마우스 제스처/QWidget 생성이 필요해 mayapy 배치로 검증 불가능한 부분이 있다 — `docs/maro-main-ui-manual-checklist.md`에 새 절로 대화형 Maya 수동 체크리스트를 추가한다. Task 4의 노드 생성/연결 로직 자체(모달 다이얼로그가 없는 부분)와 Task 2, 3, 6은 mayapy 배치로 완전히 테스트 가능하다.
- 각 Python 모듈은 다른 모듈에서 필요한 상수(예: `AXIS_FIELDS`)를 독립적으로 재선언한다 — 순환 import를 피하기 위한 이 프로젝트의 기존 관례(순환 참조 방지, 별도 이유 설명 불필요).
- 새 Qt 위젯의 모든 이벤트 핸들러(`closeEvent` 등)는 예외를 절대 밖으로 내보내지 않는다 — 이 코드베이스의 "Maya 콜백/Qt 이벤트 핸들러 경계에서 예외를 삼킨다"는 전역 규율(`maroSingleObjectNodeEditor.py`/`maroRosProxy.py`가 이미 따르는 패턴)을 그대로 따른다.
- 새 Qt 위젯은 `setStyleSheet()`를 호출하지 않는다(기존 `maroMainWindow.py`/`maroSingleObjectNodeEditor.py`/`maroTechDiag.py`와 같은 규율).

---

## 사전 조사로 확정한 사실 (구현자가 다시 조사하지 않아도 되도록)

- `MaroPump::onTimer`(`src/maro_plugin/MaroPump.cpp:116`)는 `MTimerMessage` 콜백이라 항상 메인 스레드에서 불린다. `collectLidarScans`도 그 안에서 불리므로 스캔 포인트는 이미 메인 스레드·Maya 월드 좌표로 존재한다.
- 리포 전체에 `MPxDrawOverride`/`MHWRender`/`MDrawRegistry` 사용이 전무하다 — 이 기능이 이 코드베이스 최초의 Viewport 2.0 드로우 오버라이드다. 참고 구현은 devkit 샘플 `C:/Users/ckd30/Projects/devkitBase/devkit/plug-ins/footPrintNode/footPrintNode.cpp`.
- `python/maroRosProxy.py`의 격리(`isolateSelect`) 로직: Maya측 패널(`_MAYA_PANEL`)은 매 틱 `PROXY_GROUP`을 명시적으로 건너뛰고(`maroRosProxy.py:185-188`) 나머지 모든 최상위 오브젝트를 넣고, ROS측 패널(`_ROS_PANEL`)은 오직 `PROXY_GROUP`만 격리 목록에 넣는다(`maroRosProxy.py:335-336`). 즉 `maroRosProxy_grp` 아래 무엇을 두든 ROS 뷰포트에만 자동으로 보인다 — 새 코드 불필요.
- `maroAxis` 바인딩은 물리적 DAG 부모관계가 **아니라** 메시지 커넥션(`cmds.maroBindAxis`)이다(`python/maroDagMenu.py:492-499`). `cmds.createNode("maroAxis")`는 로케이터형 셰이프라 Maya가 자동으로 새 트랜스폼을 만들고, 그 자동생성 트랜스폼은 `cmds.listRelatives(axis, parent=True, fullPath=True)`로 찾는다(`maroDagMenu.py:515-521`). **이 계획의 LiDAR 마운트는 다르다**: LiDAR는 자신이 탑재된 오브젝트의 월드 트랜스폼을 그대로 상속받아야 하므로, 그 자동생성 트랜스폼을 `cmds.parent()`로 클릭한 오브젝트의 실제 DAG 자식으로 옮긴다(Task 4에서 상세).
- `MaroLidarNode`(`src/maro_plugin/MaroLidarNode.h/.cpp`)는 이미 병합돼 있다: `aVerticalSamples`/`aVerticalMinAngle`/`aVerticalMaxAngle`/`aHorizontalSamples`/`aHorizontalMinAngle`/`aHorizontalMaxAngle`/`aRangeMin`/`aRangeMax`/`aUpdateRate`/`aFrameId`/`aTargetMeshes`(메시지 배열, `setIndexMatters(true)`)/`aEnabled`. `MTypeId(0x00135106)`.
- `MaroPump::collectLidarScans`(`MaroPump.cpp:306-486`)이 스캔 로직 전체(어트리뷰트 읽기 → 검증 → 레이 수 상한 체크 → 메쉬 추출 → Embree 레이캐스팅 → 결과 좌표계 변환)를 갖고 있다. 보조 함수 `extractMeshBuffers()`/`firstConnectedMesh()`(둘 다 `MaroPump.cpp:241-302`의 익명 네임스페이스), 상수 `kMaxRaysPerScan = 65536`(`MaroPump.cpp:53`), 헬퍼 `currentSceneUnit()`(`MaroPump.cpp:57-62`)가 이 로직에 딸려 있다.
- 타입 위치: `maro::Vec3`/`maro::SceneUnit`/`maro::isFinite()`는 `src/maro_transform/include/maro_transform/Types.h`. `maro::lidar::ScanEngine`/`RayHit`은 `src/maro_lidar/include/maro_lidar/ScanEngine.h`(`setMesh(vertices, indices)`, `castRay(origin, direction, rangeMin, rangeMax) -> RayHit`). `maro::lidar::computeRayDirections(...)`는 `src/maro_lidar/include/maro_lidar/RayPattern.h`. `maro::LidarSample`(`unit`, `points`)은 `src/maro_plugin/MaroBridgeQueues.h:38`.
- 커맨드 템플릿(모든 새 undoable 커맨드가 그대로 따른다, 예시는 `MaroAddCapabilityCommand`, `src/maro_plugin/MaroAxisEditorCommands.h:25-38`/`.cpp:354-531`): `MDGModifier m_modifier;` 멤버, `bool m_stagedChange = false;`, `isUndoable() { return m_stagedChange; }`, `doIt()`가 `maro::ScopedCommandContext ctxMarker("커맨드이름")`으로 감싸고 `try { ... } catch (const std::exception&) { BoadMaro::error(...) } catch (...) { BoadMaro::error(...) }`로 커맨드 경계를 넘는 예외를 막는다. `redoIt()`/`undoIt()`도 각각 자기 `ScopedCommandContext`를 새로 건다(undo 큐 재진입 시 `doIt()`의 마커가 이미 스택에서 빠졌기 때문).
- `MaroPluginMain.cpp`는 등록 역순으로 해제한다는 명시적 규율을 갖고 있다 — 새 등록을 어디에 넣든 대응하는 해제는 그 반대 순서로 넣는다(파일 안의 여러 주석이 이 규율을 설명한다).
- `python/maroDagMenu.py`의 `_addMenuItem()`이 매 우클릭마다 불려 `cmds.menuItem(parent=parentMenu, label=..., command=...)`으로 항목 하나를 붙인다. `_nativeMenuSuppressed()`(ViewCube/순회 마킹메뉴/Modeling-Toolkit RMB-complete 억제)와 `_resolveObject()`(대상 DAG 오브젝트 결정)는 이미 있고 재사용한다.
- `python/maroTechDiag.py`는 순수 검사 함수(`checkLimitProximity` 등) + `_CheckSidePanel`(실행 버튼 → 결과 리스트 → 있으면 "적용" 버튼) + `_runMayaSideChecks()`/`_runRosSideChecks()`(Maya 조회 담당) + `buildMayaSidePanel()`/`buildRosSidePanel()` 구조다. `_runMayaSideChecks()`에 LiDAR 검사를 추가한다(Task 6).
- `MARO_PLUGIN_PY_MODULES`(`src/maro_plugin/CMakeLists.txt:158-167`)에 새 Python 모듈 파일명만 추가하면 빌드 시 플러그인 옆에 자동 스테이징된다. mayapy 테스트는 `tests/CMakeLists.txt:283-301`의 공유 `foreach(maya_test ...)` 목록에 이름만 추가하면 `MARO_PLUGIN_PATH`/`PATH`/`MARO_DIAG_BOOK_DIR` 격리가 전부 자동으로 붙는다.

---

### Task 1: `maroPointCloud` 노드 + Viewport 2.0 드로우 오버라이드 (LiDAR 무관 워킹 스켈레톤)

**Files:**
- Create: `src/maro_plugin/MaroPointCloudNode.h`
- Create: `src/maro_plugin/MaroPointCloudNode.cpp`
- Modify: `src/maro_plugin/MaroPluginMain.cpp`
- Modify: `src/maro_plugin/CMakeLists.txt`
- Test: `tests/maya/test_point_cloud_node.py`
- Modify: `tests/CMakeLists.txt`
- Modify: `docs/maro-main-ui-manual-checklist.md`

**Interfaces:**
- Produces: `maro::MaroPointCloudNode`(`id`, `aPoints`, `aPointSize`, `aColor`, `aEnabled`, `aSourceLidar`, `kDrawDbClassification`) — Task 4/5가 이 타입 이름과 어트리뷰트 이름을 그대로 쓴다. `aSourceLidar`는 메시지 어트리뷰트로, 이 포인트클라우드를 만든 `maroLidar` 노드를 가리키는 데 쓴다(Task 4가 연결, Task 4의 설정 팝업이 역참조로 찾는 데 씀).
- 등록되는 Maya 노드 타입 이름: `"maroPointCloud"`.

- [ ] **Step 1: `MaroPointCloudNode.h` 작성**

```cpp
#pragma once

#include <maya/MBoundingBox.h>
#include <maya/MDGContext.h>
#include <maya/MEvaluationNode.h>
#include <maya/MObject.h>
#include <maya/MPxLocatorNode.h>
#include <maya/MStatus.h>
#include <maya/MString.h>
#include <maya/MTypeId.h>

namespace maro {

// 스캔 결과 포인트를 Viewport 2.0에 그리는 로케이터. maroAxis/maroLidar와 같은
// MPxLocatorNode 패턴이지만, 그리기 자체는 이 노드가 아니라 짝을 이루는
// MaroPointCloudDrawOverride(같은 .cpp)가 한다 -- registerNode에
// kDrawDbClassification을 함께 주는 것이 그 연결이다.
//
// 이 태스크는 LiDAR와 완전히 무관하다: points를 손으로 채운 값으로 채워도
// 그려지고, 창을 띄운 채 언로드해도 죽지 않는다는 것만 증명한다.
class MaroPointCloudNode : public MPxLocatorNode {
public:
    MaroPointCloudNode() = default;
    ~MaroPointCloudNode() override = default;

    static void* creator();
    static MStatus initialize();

    bool isBounded() const override { return true; }
    MBoundingBox boundingBox() const override;

    // points가 dirty해지면 Viewport 2.0에 다시 그리라고 명시적으로 알린다.
    // MPxDrawOverride(..., isAlwaysDirty=false)는 이 신호 없이는 언제 다시
    // 그려야 하는지 스스로 알지 못한다(devkit footPrintNode.cpp의
    // preEvaluation()과 같은 이유, 같은 패턴).
    MStatus preEvaluation(const MDGContext& context,
                          const MEvaluationNode& evaluationNode) override;

    static MTypeId id;
    static MObject aPoints;
    static MObject aPointSize;
    static MObject aColor;
    static MObject aEnabled;
    // 이 포인트클라우드를 만든 maroLidar를 가리키는 메시지 커넥션(단일,
    // 배열 아님). Task 4가 생성 시점에 연결하고, LiDAR 설정 팝업이
    // "이 lidar에 연결된 포인트클라우드"를 역참조로 찾을 때 쓴다.
    static MObject aSourceLidar;

    // Viewport 2.0 드로우 오버라이드 등록에 쓰는 classification 문자열.
    // registerNode()와 MDrawRegistry::registerDrawOverrideCreator() 양쪽이
    // 정확히 같은 문자열 인스턴스를 참조해야 서로 연결된다.
    static MString kDrawDbClassification;
    static MString kDrawRegistrantId;
};

}  // namespace maro
```

- [ ] **Step 2: `MaroPointCloudNode.cpp` 작성 — 노드 부분**

```cpp
#include "MaroPointCloudNode.h"

#include <algorithm>

#include <maya/MFnMessageAttribute.h>
#include <maya/MFnNumericAttribute.h>
#include <maya/MFnNumericData.h>
#include <maya/MFnPointArrayData.h>
#include <maya/MFnTypedAttribute.h>
#include <maya/MPlug.h>
#include <maya/MPoint.h>
#include <maya/MPointArray.h>

// Viewport 2.0
#include <maya/MDrawContext.h>
#include <maya/MDrawRegistry.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MHWGeometryUtilities.h>
#include <maya/MPxDrawOverride.h>
#include <maya/MUserData.h>

namespace maro {

MTypeId MaroPointCloudNode::id(0x00135108);
MString MaroPointCloudNode::kDrawDbClassification("drawdb/geometry/maro/pointCloud");
MString MaroPointCloudNode::kDrawRegistrantId("MaroPointCloudPlugin");

MObject MaroPointCloudNode::aPoints;
MObject MaroPointCloudNode::aPointSize;
MObject MaroPointCloudNode::aColor;
MObject MaroPointCloudNode::aEnabled;
MObject MaroPointCloudNode::aSourceLidar;

void* MaroPointCloudNode::creator() { return new MaroPointCloudNode(); }

MStatus MaroPointCloudNode::initialize() {
    MFnTypedAttribute typedFn;
    MFnNumericAttribute numFn;
    MFnMessageAttribute msgFn;
    MFnPointArrayData pointArrayDataFn;

    MObject defaultPoints = pointArrayDataFn.create(MPointArray());
    aPoints = typedFn.create("points", "pts", MFnData::kPointArray, defaultPoints);
    // 세션 내 스캔 스냅샷일 뿐 씬 파일에 저장하지 않는다(전역 제약 참고).
    typedFn.setStorable(false);
    typedFn.setKeyable(false);
    addAttribute(aPoints);

    aPointSize = numFn.create("pointSize", "psz", MFnNumericData::kDouble, 2.0);
    numFn.setKeyable(true);
    numFn.setMin(0.1);
    addAttribute(aPointSize);

    aColor = numFn.createColor("color", "clr");
    numFn.setDefault(0.2f, 0.8f, 1.0f);
    numFn.setKeyable(true);
    addAttribute(aColor);

    aEnabled = numFn.create("enabled", "enb", MFnNumericData::kBoolean, true);
    numFn.setKeyable(true);
    addAttribute(aEnabled);

    aSourceLidar = msgFn.create("sourceLidar", "srl");
    addAttribute(aSourceLidar);

    return MS::kSuccess;
}

MBoundingBox MaroPointCloudNode::boundingBox() const {
    MObject thisNode = thisMObject();
    MPlug pointsPlug(thisNode, aPoints);
    MObject pointsData;
    pointsPlug.getValue(pointsData);
    MFnPointArrayData pointArrayDataFn(pointsData);
    MPointArray points = pointArrayDataFn.array();

    // 빈 배열이면 오비트 컬링을 피할 수 있는 작은 기본 박스를 준다 --
    // MBoundingBox()의 기본 생성자는 "무효" 상태라 일부 뷰포트 코드가
    // 놀랄 수 있다.
    if (points.length() == 0) {
        return MBoundingBox(MPoint(-1, -1, -1), MPoint(1, 1, 1));
    }

    MPoint minP = points[0];
    MPoint maxP = points[0];
    for (unsigned int i = 1; i < points.length(); ++i) {
        const MPoint& p = points[i];
        minP.x = std::min(minP.x, p.x);
        minP.y = std::min(minP.y, p.y);
        minP.z = std::min(minP.z, p.z);
        maxP.x = std::max(maxP.x, p.x);
        maxP.y = std::max(maxP.y, p.y);
        maxP.z = std::max(maxP.z, p.z);
    }
    return MBoundingBox(minP, maxP);
}

MStatus MaroPointCloudNode::preEvaluation(const MDGContext& context,
                                          const MEvaluationNode& evaluationNode) {
    if (context.isNormal()) {
        MStatus status;
        if (evaluationNode.dirtyPlugExists(aPoints, &status) && status) {
            MHWRender::MRenderer::setGeometryDrawDirty(thisMObject());
        }
    }
    return MS::kSuccess;
}

}  // namespace maro
```

- [ ] **Step 3: 같은 파일에 `MaroPointCloudUserData` + `MaroPointCloudDrawOverride` 추가**

`MaroPointCloudNode.cpp`의 `namespace maro { ... }` 블록 **밖**(전역 스코프)에 이어서 작성한다 — devkit `footPrintNode.cpp`가 `FootPrintDrawOverride`를 전역 스코프에 두는 것과 같은 배치. `maro::MaroPointCloudNode`를 쓰는 부분만 네임스페이스를 명시한다.

```cpp
namespace {

class MaroPointCloudUserData : public MUserData {
public:
    MaroPointCloudUserData() = default;
    MPointArray points;
    MColor color{0.2f, 0.8f, 1.0f, 1.0f};
    double pointSize = 2.0;
    bool enabled = true;
};

}  // namespace

class MaroPointCloudDrawOverride : public MHWRender::MPxDrawOverride {
public:
    static MHWRender::MPxDrawOverride* creator(const MObject& obj) {
        return new MaroPointCloudDrawOverride(obj);
    }

    ~MaroPointCloudDrawOverride() override = default;

    MHWRender::DrawAPI supportedDrawAPIs() const override {
        return (MHWRender::kOpenGL | MHWRender::kDirectX11 | MHWRender::kOpenGLCoreProfile);
    }

    bool isBounded(const MDagPath& /*objPath*/, const MDagPath& /*cameraPath*/) const override {
        return true;
    }

    MBoundingBox boundingBox(const MDagPath& objPath, const MDagPath& /*cameraPath*/) const override {
        MStatus status;
        MFnDependencyNode nodeFn(objPath.node(&status));
        if (!status) return MBoundingBox();
        auto* node = dynamic_cast<maro::MaroPointCloudNode*>(nodeFn.userNode());
        return node ? node->boundingBox() : MBoundingBox();
    }

    // DG 조회는 여기서만 한다 -- addUIDrawables()는 절대 하지 않는다(전역 제약).
    MUserData* prepareForDraw(const MDagPath& objPath, const MDagPath& /*cameraPath*/,
                              const MHWRender::MFrameContext& /*frameContext*/,
                              MUserData* oldData) override {
        auto* data = dynamic_cast<MaroPointCloudUserData*>(oldData);
        if (!data) data = new MaroPointCloudUserData();

        MStatus status;
        MFnDependencyNode nodeFn(objPath.node(&status));
        if (!status) return data;

        data->enabled = nodeFn.findPlug(maro::MaroPointCloudNode::aEnabled, false).asBool();

        MPlug pointsPlug = nodeFn.findPlug(maro::MaroPointCloudNode::aPoints, false);
        MObject pointsData;
        pointsPlug.getValue(pointsData);
        MFnPointArrayData pointArrayDataFn(pointsData);
        data->points = pointArrayDataFn.array();

        data->pointSize = nodeFn.findPlug(maro::MaroPointCloudNode::aPointSize, false).asDouble();

        MPlug colorPlug = nodeFn.findPlug(maro::MaroPointCloudNode::aColor, false);
        float r = 0.2f, g = 0.8f, b = 1.0f;
        colorPlug.child(0).getValue(r);
        colorPlug.child(1).getValue(g);
        colorPlug.child(2).getValue(b);
        data->color = MColor(r, g, b, 1.0f);

        return data;
    }

    bool hasUIDrawables() const override { return true; }

    void addUIDrawables(const MDagPath& /*objPath*/, MHWRender::MUIDrawManager& drawManager,
                        const MHWRender::MFrameContext& /*frameContext*/,
                        const MUserData* data) override {
        const auto* pointCloudData = dynamic_cast<const MaroPointCloudUserData*>(data);
        if (!pointCloudData || !pointCloudData->enabled || pointCloudData->points.length() == 0) {
            return;
        }
        drawManager.beginDrawable();
        drawManager.setColor(pointCloudData->color);
        drawManager.setPointSize(static_cast<float>(pointCloudData->pointSize));
        drawManager.mesh(MHWRender::MUIDrawManager::kPoints, pointCloudData->points);
        drawManager.endDrawable();
    }

private:
    explicit MaroPointCloudDrawOverride(const MObject& obj)
        : MHWRender::MPxDrawOverride(obj, nullptr, false) {}
};
```

- [ ] **Step 4: `MaroPluginMain.cpp`에 등록/해제 추가**

`#include "MaroLidarNode.h"` 바로 아래에 새 include를 추가한다:
```cpp
#include "MaroPointCloudNode.h"
```
그리고 Viewport 2.0 등록을 위한 include(파일 맨 위 include 블록에 추가):
```cpp
#include <maya/MDrawRegistry.h>
```

`initializePlugin`에서, `maroLidar` 노드 등록 블록(기존 코드의 126-131행) **바로 다음**에 삽입한다(기존 코드를 바꾸지 않고 그 뒤에 새 블록만 추가):

```cpp
    status = plugin.registerNode(
        "maroPointCloud", maro::MaroPointCloudNode::id, &maro::MaroPointCloudNode::creator,
        &maro::MaroPointCloudNode::initialize, MPxNode::kLocatorNode,
        &maro::MaroPointCloudNode::kDrawDbClassification);
    if (!status) {
        status.perror("Maro: failed to register maroPointCloud node");
        return status;
    }

    status = MHWRender::MDrawRegistry::registerDrawOverrideCreator(
        maro::MaroPointCloudNode::kDrawDbClassification,
        maro::MaroPointCloudNode::kDrawRegistrantId,
        MaroPointCloudDrawOverride::creator);
    if (!status) {
        status.perror("Maro: failed to register maroPointCloud draw override");
        return status;
    }
```

`uninitializePlugin`에서, 기존 코드의 656행(`MStatus status = plugin.deregisterNode(maro::MaroLidarNode::id);`) **바로 앞**에 삽입한다(등록 역순 규율: `maroPointCloud`는 `maroLidar` 다음에 등록됐으므로 해제는 그 앞에 온다). **드로우 오버라이드 해제가 노드 해제보다 먼저**(전역 제약):

```cpp
        MStatus pointCloudDrawStatus = MHWRender::MDrawRegistry::deregisterDrawOverrideCreator(
            maro::MaroPointCloudNode::kDrawDbClassification,
            maro::MaroPointCloudNode::kDrawRegistrantId);
        if (!pointCloudDrawStatus) {
            pointCloudDrawStatus.perror("Maro: failed to deregister maroPointCloud draw override");
        }
        MStatus pointCloudStatus = plugin.deregisterNode(maro::MaroPointCloudNode::id);
        if (!pointCloudStatus) {
            pointCloudStatus.perror("Maro: failed to deregister maroPointCloud node");
        }

```
(이 블록 바로 다음 줄이 기존의 `MStatus status = plugin.deregisterNode(maro::MaroLidarNode::id);`다 — 그 줄은 그대로 둔다. 새 지역 변수 이름을 `status`가 아니라 `pointCloudDrawStatus`/`pointCloudStatus`로 둔 것은 그 아래 기존 `MStatus status = ...` 선언과 이름이 겹치지 않게 하기 위해서다.)

- [ ] **Step 5: `src/maro_plugin/CMakeLists.txt`에 새 소스 파일 추가**

`SOURCE_FILES` 목록의 `MaroLidarNode.cpp` 바로 다음 줄에 추가:
```cmake
    MaroPointCloudNode.cpp
```
`LIBRARIES` 목록은 수정하지 않는다 — `OpenMayaRender`가 이미 들어 있다(`src/maro_plugin/CMakeLists.txt:32`).

- [ ] **Step 6: mayapy 배치 테스트 작성 — `tests/maya/test_point_cloud_node.py`**

이 테스트는 노드의 **어트리뷰트 계약**만 검증한다(생성, 기본값, `points` 설정/읽기, `boundingBox()`가 예외 없이 동작). 실제 렌더링/언로드 안전성은 배치에서 검증 불가능(모듈 도크스트링 관례와 같은 이유) — 그건 아래 수동 체크리스트가 담당한다.

```python
"""maroPointCloud 노드의 어트리뷰트 계약을 배치 모드에서 고정한다.

이 파일이 검증하는 것: 노드가 등록되고, 기본값이 스펙과 일치하고, points를
설정/조회할 수 있고, setStorable(false)가 실제로 걸려 있고(씬에 저장 안
됨), boundingBox()가 빈 배열/채워진 배열 양쪽에서 예외 없이 동작한다는 것.

이 파일이 **못** 하는 것: 실제로 그려지는지, 창을 띄운 채 언로드해도
안전한지는 배치 mayapy로 확인할 수 없다(QApplication이 아니라
QGuiApplication만 있어 QWidget 생성이 프로세스를 abort시키는 것과는 다른
문제지만, Viewport 2.0 렌더링 자체가 실제 GPU 컨텍스트를 필요로 해서
배치에서 원리적으로 불가능하다) -- docs/maro-main-ui-manual-checklist.md의
새 절이 담당한다.
"""
import os

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

node = cmds.createNode("maroPointCloud")
assert cmds.objExists(node)
print("maroPointCloud creation OK")

assert cmds.getAttr(node + ".pointSize") == 2.0
assert cmds.getAttr(node + ".enabled") is True
assert cmds.getAttr(node + ".color")[0] == (
    round(0.2, 6), round(0.8, 6), round(1.0, 6))
print("default values OK")

storable = cmds.attributeQuery("points", node=node, storable=True)
assert storable is False, (
    "points must be non-storable -- scan snapshots must not be saved into .ma files")
print("points non-storable OK")

# 점 세 개를 손으로 채워 본다 -- Task 1의 워킹 스켈레톤이 실제로 증명해야
# 하는 것과 같은 데이터 경로다(사람이 뷰포트에서 확인하는 대상).
cmds.setAttr(node + ".points", type="pointArray", 3,
             0.0, 0.0, 0.0, 1.0,
             1.0, 0.0, 0.0, 1.0,
             0.0, 1.0, 0.0, 1.0)
readBack = cmds.getAttr(node + ".points")
assert len(readBack) == 3
print("points round-trip OK")

bbox = cmds.exactWorldBoundingBox(node)
assert bbox[3] > bbox[0] and bbox[4] > bbox[1], (
    f"boundingBox() must reflect the actual points, got {bbox}")
print("boundingBox reflects points OK")

# 언로드 자체(창 없이)는 최소한 크래시하지 않아야 한다 -- 창을 띄운 채
# 언로드하는 케이스는 배치에서 재현 불가능하므로 수동 체크리스트가 담당한다.
cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
print("unload without an open window OK")
```

- [ ] **Step 7: `tests/CMakeLists.txt`에 등록**

`foreach(maya_test load axis_node binding ...)` 목록(약 283-291행)에 `dag_menu tech_diag` 바로 다음에 `point_cloud_node`를 추가한다:
```cmake
    foreach(maya_test load axis_node binding capability_stack delete_rules
                      robustness diag_boad diag_onfix diag_book
                      diag_book_cross_session diag_remedy
                      diag_degraded diag_degraded_remedy diag_thread
                      panel_commands main_window main_menu journal remedy_capture
                      remedy_availability remedy_ambiguous_names
                      main_thread_queue remedy_apply sentinel lidar_node
                      ros_proxy_commands ros_proxy_sync axis_editor_commands
                      dag_menu tech_diag point_cloud_node)
```
이 목록에 이름만 추가하면 `ENVIRONMENT`/`ENVIRONMENT_MODIFICATION`/`FIXTURES_REQUIRED`/`TIMEOUT`이 공유 규칙으로 자동 적용된다(전역 제약과 같은 이유).

- [ ] **Step 8: 빌드 + 전체 테스트**

전역 제약의 빌드+테스트 절차를 그대로 실행한다. `maya_point_cloud_node`가 통과하고 나머지 기존 테스트가 모두 그린인지 확인한다.

- [ ] **Step 9: 수동 체크리스트 새 절 작성**

`docs/maro-main-ui-manual-checklist.md`의 `## 5. Tech Diag 검사 (Phase 6)` 다음에 새 절을 추가한다:

```markdown
## 6. LiDAR 설정 + 시각화 (Phase 5) — **[필수 · go/no-go]**

### 6-1. `maroPointCloud` 드로우 오버라이드 (Task 1)

1. 플러그인을 로드하고 빈 씬에서 스크립트 에디터(Python)로:
   ```python
   import maya.cmds as cmds
   node = cmds.createNode("maroPointCloud")
   cmds.setAttr(node + ".points", type="pointArray", 5,
                0,0,0,1, 2,0,0,1, 0,2,0,1, 0,0,2,1, 1,1,1,1)
   ```
2. **[필수]** 뷰포트에 점 5개가 실제로 보이는가(작은 원/사각형 형태로,
   `pointSize` 기본값 2.0 크기).
3. `cmds.setAttr(node + ".pointSize", 8.0)` — **[필수]** 점이 즉시(다음
   리드로우에) 커지는가. `preEvaluation()`의 dirty 신호가 실제로 동작한다는
   증거다.
4. 뷰를 회전/줌해서 점들이 프러스텀 밖으로 나갔다 들어왔다 해도 컬링되지
   않고 계속 보이는가(`boundingBox()`가 실제 점 범위를 반영한다는 증거).
5. **[필수 · 이 태스크의 진짜 기준]** 점이 보이는 상태로(뷰포트에서 보이게
   놔둔 채) `cmds.unloadPlugin("maro")`를 실행한다. Maya가 죽지 않고,
   스크립트 에디터에 새 크래시 관련 에러가 없는가.
```

---

### Task 2: `MaroPump::collectLidarScans`에서 `scanLidarNode()` 추출

**Files:**
- Create: `src/maro_plugin/MaroLidarScan.h`
- Create: `src/maro_plugin/MaroLidarScan.cpp`
- Modify: `src/maro_plugin/MaroPump.cpp`
- Modify: `src/maro_plugin/CMakeLists.txt`

**Interfaces:**
- Consumes: `maro::lidar::ScanEngine`(`ScanEngine.h`), `maro::lidar::computeRayDirections`(`RayPattern.h`), `maro::Vec3`/`maro::SceneUnit`/`maro::isFinite`(`maro_transform/Types.h`), `MaroLidarNode`의 어트리뷰트(`MaroLidarNode.h`).
- Produces: `maro::currentSceneUnit()`, `maro::kMaxRaysPerScan`(상수, 값 65536 — 값 자체는 바뀌지 않는다, 위치만 이동), `maro::LidarScanResult`(enum: `kOk`/`kNoTargetMesh`/`kMeshExtractFailed`/`kInvalidConfig`/`kRayCountExceeded`), `maro::scanLidarNode(lidarNode, engine, unit, outPoints) -> LidarScanResult`. Task 3의 새 커맨드가 이 함수를 그대로 재사용한다.

**이 태스크는 순수 리팩터다.** 기존 `collectLidarScans()`의 관찰 가능한 동작(발행되는 포인트, 진단 메시지, 스로틀 타이밍)은 바뀌지 않는다 — 이미 병합·리뷰된 코드를 재사용 가능한 형태로 나누는 것뿐이다.

- [ ] **Step 1: `MaroLidarScan.h` 작성**

```cpp
#pragma once

#include <vector>

#include <maya/MObject.h>

#include "maro_transform/Types.h"

namespace maro::lidar {
class ScanEngine;
}

namespace maro {

// MaroPump::collectLidarScans의 예전 상수와 같은 값이다 -- 위치만
// 옮겼다(MaroPump.cpp 익명 네임스페이스 -> 여기, 두 호출부가 공유하도록).
constexpr long long kMaxRaysPerScan = 65536;

enum class LidarScanResult {
    kOk,
    kNoTargetMesh,
    kMeshExtractFailed,
    kInvalidConfig,
    kRayCountExceeded,
};

// Maya의 현재 선형 단위를 미터 배율로 바꾼다. MaroPump::collectSamples()와
// MaroPump::collectLidarScans() 둘 다 필요로 해서(전자는 축 값의 라디안/미터
// 변환에, 후자는 rangeMin/rangeMax의 미터->Maya 단위 변환에) 여기서 한 곳에만
// 둔다.
SceneUnit currentSceneUnit();

// lidarNode의 현재 어트리뷰트를 읽어 즉시 동기 스캔하고, 히트를 Maya 월드
// 좌표(Vec3)로 outPoints에 채운다(호출 전 내용은 지운다). 스로틀
// (updateRate)이나 진단 래치(1회 경고)는 호출자 책임이다 -- 이 함수는 매번
// 무조건 스캔한다. engine은 호출자가 소유한다(재사용 가능 -- setMesh()는
// 반복 호출로 기존 지오메트리를 안전하게 교체한다).
LidarScanResult scanLidarNode(const MObject& lidarNode, maro::lidar::ScanEngine& engine,
                               const SceneUnit& unit, std::vector<Vec3>& outPoints);

}  // namespace maro
```

- [ ] **Step 2: `MaroLidarScan.cpp` 작성**

`MaroPump.cpp`의 다음 세 조각을 그대로(로직 변경 없이) 옮겨 온다: `currentSceneUnit()`(원본 `MaroPump.cpp:57-62`), `extractMeshBuffers()`(원본 `MaroPump.cpp:251-282`), `firstConnectedMesh()`(원본 `MaroPump.cpp:291-302`). 그리고 `collectLidarScans()`의 스캔 본체(원본 `MaroPump.cpp:357-475`, 어트리뷰트 읽기부터 `sample.points.push_back(...)`까지)를 `continue`를 `return LidarScanResult::kX`로 바꿔 가며 옮긴다.

```cpp
#include "MaroLidarScan.h"

#include <cmath>
#include <cstdint>

#include <maya/MAngle.h>
#include <maya/MDagPath.h>
#include <maya/MDistance.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MFnMesh.h>
#include <maya/MIntArray.h>
#include <maya/MMatrix.h>
#include <maya/MPlug.h>
#include <maya/MPlugArray.h>
#include <maya/MPoint.h>
#include <maya/MPointArray.h>
#include <maya/MVector.h>

#include "maro_lidar/RayPattern.h"
#include "maro_lidar/ScanEngine.h"

#include "MaroLidarNode.h"

namespace maro {

SceneUnit currentSceneUnit() {
    SceneUnit unit;
    unit.metersPerMayaUnit = MDistance(1.0, MDistance::internalUnit()).asMeters();
    return unit;
}

namespace {

// meshNode는 targetMeshes에 연결된 노드다. 사용자는 보통 트랜스폼의
// .message를 잇는다 -- MFnMesh는 트랜스폼을 받지 않으므로 여기서 셰이프까지
// 내려간다. MObject가 아니라 MDagPath로 함수 세트를 만드는 것이 중요하다:
// MSpace::kWorld는 경로 컨텍스트가 있어야 조상 체인을 포함한 진짜 월드
// 좌표를 준다.
bool extractMeshBuffers(const MObject& meshNode, std::vector<float>& vertices,
                        std::vector<std::uint32_t>& indices) {
    MDagPath meshPath;
    if (MDagPath::getAPathTo(meshNode, meshPath) != MS::kSuccess) return false;
    if (!meshPath.hasFn(MFn::kMesh)) {
        if (meshPath.extendToShape() != MS::kSuccess) return false;
        if (!meshPath.hasFn(MFn::kMesh)) return false;
    }

    MStatus status;
    MFnMesh meshFn(meshPath, &status);
    if (!status) return false;

    MPointArray points;
    if (meshFn.getPoints(points, MSpace::kWorld) != MS::kSuccess) return false;
    vertices.clear();
    vertices.reserve(static_cast<std::size_t>(points.length()) * 3);
    for (unsigned int i = 0; i < points.length(); ++i) {
        vertices.push_back(static_cast<float>(points[i].x));
        vertices.push_back(static_cast<float>(points[i].y));
        vertices.push_back(static_cast<float>(points[i].z));
    }

    MIntArray triangleCounts, triangleVertices;
    if (meshFn.getTriangles(triangleCounts, triangleVertices) != MS::kSuccess) return false;
    indices.clear();
    indices.reserve(static_cast<std::size_t>(triangleVertices.length()));
    for (unsigned int i = 0; i < triangleVertices.length(); ++i) {
        indices.push_back(static_cast<std::uint32_t>(triangleVertices[i]));
    }
    return true;
}

// targetMeshes(메시지 배열)에서 처음으로 연결된 소스 노드를 찾는다.
// elementByLogicalIndex(0)가 아니라 evaluateNumElements()+
// elementByPhysicalIndex()를 쓴다: 논리 인덱스 접근은 없는 원소를 요구하면
// 데이터블록에 빈 원소를 만들어 넣는다.
bool firstConnectedMesh(MPlug meshesPlug, MObject& meshNode) {
    const unsigned int count = meshesPlug.evaluateNumElements();
    for (unsigned int i = 0; i < count; ++i) {
        MPlugArray sources;
        meshesPlug.elementByPhysicalIndex(i).connectedTo(sources, true, false);
        if (sources.length() > 0) {
            meshNode = sources[0].node();
            return true;
        }
    }
    return false;
}

}  // namespace

LidarScanResult scanLidarNode(const MObject& lidarNode, maro::lidar::ScanEngine& engine,
                               const SceneUnit& unit, std::vector<Vec3>& outPoints) {
    outPoints.clear();
    MFnDependencyNode lidarFn(lidarNode);

    const int verticalSamples =
        lidarFn.findPlug(MaroLidarNode::aVerticalSamples, false).asInt();
    const double verticalMinAngle =
        lidarFn.findPlug(MaroLidarNode::aVerticalMinAngle, false).asMAngle().asRadians();
    const double verticalMaxAngle =
        lidarFn.findPlug(MaroLidarNode::aVerticalMaxAngle, false).asMAngle().asRadians();
    const int horizontalSamples =
        lidarFn.findPlug(MaroLidarNode::aHorizontalSamples, false).asInt();
    const double horizontalMinAngle =
        lidarFn.findPlug(MaroLidarNode::aHorizontalMinAngle, false).asMAngle().asRadians();
    const double horizontalMaxAngle =
        lidarFn.findPlug(MaroLidarNode::aHorizontalMaxAngle, false).asMAngle().asRadians();
    const double rangeMin = lidarFn.findPlug(MaroLidarNode::aRangeMin, false).asDouble();
    const double rangeMax = lidarFn.findPlug(MaroLidarNode::aRangeMax, false).asDouble();

    // rangeMin/rangeMax는 미터다. 레이캐스팅은 Maya 월드 단위에서 돈다 --
    // castRay에 넘긴 값이 그대로 ray.tnear/ray.tfar가 되기 때문이다.
    const double mayaPerMeter = 1.0 / unit.metersPerMayaUnit;
    const double rangeMinMaya = rangeMin * mayaPerMeter;
    const double rangeMaxMaya = rangeMax * mayaPerMeter;

    if (!std::isfinite(verticalMinAngle) || !std::isfinite(verticalMaxAngle) ||
        !std::isfinite(horizontalMinAngle) || !std::isfinite(horizontalMaxAngle) ||
        !std::isfinite(rangeMinMaya) || !std::isfinite(rangeMaxMaya)) {
        return LidarScanResult::kInvalidConfig;
    }
    // Embree가 문서로 요구하는 전제: 0 <= tnear <= tfar.
    if (rangeMinMaya < 0.0 || rangeMaxMaya < rangeMinMaya) return LidarScanResult::kInvalidConfig;

    const long long rayCount = static_cast<long long>(verticalSamples) *
                               static_cast<long long>(horizontalSamples);
    if (rayCount > kMaxRaysPerScan) return LidarScanResult::kRayCountExceeded;

    MObject meshNode;
    if (!firstConnectedMesh(lidarFn.findPlug(MaroLidarNode::aTargetMeshes, false), meshNode)) {
        return LidarScanResult::kNoTargetMesh;
    }

    std::vector<float> vertices;
    std::vector<std::uint32_t> indices;
    if (!extractMeshBuffers(meshNode, vertices, indices)) return LidarScanResult::kMeshExtractFailed;
    if (!engine.setMesh(vertices, indices)) return LidarScanResult::kMeshExtractFailed;

    const auto localDirections = maro::lidar::computeRayDirections(
        verticalSamples, verticalMinAngle, verticalMaxAngle, horizontalSamples,
        horizontalMinAngle, horizontalMaxAngle);

    MDagPath lidarPath;
    if (MDagPath::getAPathTo(lidarNode, lidarPath) != MS::kSuccess) {
        return LidarScanResult::kInvalidConfig;
    }
    const MMatrix worldMatrix = lidarPath.inclusiveMatrix();
    const MVector worldOrigin(MPoint(0, 0, 0) * worldMatrix);
    const Vec3 origin{worldOrigin.x, worldOrigin.y, worldOrigin.z};
    if (!isFinite(origin)) return LidarScanResult::kInvalidConfig;

    // 방향 벡터에서 평행이동 성분을 제거하기 위해 함께 뺄 기준점.
    const MVector directionBias = MVector(0, 0, 0) * worldMatrix;

    for (const Vec3& localDir : localDirections) {
        const MVector localVec(localDir.x, localDir.y, localDir.z);
        const MVector worldDir = (localVec * worldMatrix - directionBias).normal();
        const maro::lidar::RayHit hit =
            engine.castRay(origin, Vec3{worldDir.x, worldDir.y, worldDir.z}, rangeMinMaya, rangeMaxMaya);
        if (hit.hit && isFinite(hit.position)) outPoints.push_back(hit.position);
    }
    return LidarScanResult::kOk;
}

}  // namespace maro
```

- [ ] **Step 3: `MaroPump.cpp`를 새 함수를 쓰도록 수정**

`MaroPump.cpp`에서 다음을 **제거**한다: 익명 네임스페이스 안의 `currentSceneUnit()`(57-62행), `kMaxRaysPerScan` 상수(53행), `extractMeshBuffers()`/`firstConnectedMesh()`(241-302행). `#include "MaroLidarScan.h"`를 기존 `#include "MaroLidarNode.h"` 다음에 추가한다. `#include "maro_lidar/RayPattern.h"`/`#include "maro_lidar/ScanEngine.h"`는 `collectSamples()`가 그 타입을 직접 쓰지 않게 되므로 제거해도 되지만, 다른 곳에서 여전히 필요하면(예: `MaroPump.h`가 전방 선언만 하고 `s_scanEngine`의 완전한 타입이 `.cpp`에서 필요) 유지한다 — `s_scanEngine`이 `std::unique_ptr<maro::lidar::ScanEngine>`이라 소멸자 인스턴스화에 완전한 타입이 여전히 필요하므로 `#include "maro_lidar/ScanEngine.h"`는 남긴다. `#include "maro_lidar/RayPattern.h"`는 제거한다(더 이상 직접 안 씀).

`collectLidarScans()`를 다음으로 교체한다(주석은 원본의 설명을 유지하되 새 함수 호출로 바뀐 부분만 갱신):

```cpp
void MaroPump::collectLidarScans(MaroRosRuntime& runtime) {
    if (!s_scanEngine) return;

    const SceneUnit unit = currentSceneUnit();

    for (auto stateIt = s_lidarNodeState.begin(); stateIt != s_lidarNodeState.end();) {
        if (!stateIt->second.handle.isAlive()) {
            stateIt = s_lidarNodeState.erase(stateIt);
        } else {
            ++stateIt;
        }
    }

    const auto tickNow = std::chrono::steady_clock::now();

    for (MItDependencyNodes it(MFn::kPluginLocatorNode); !it.isDone(); it.next()) {
        const MObject lidarObj = it.thisNode();
        MFnDependencyNode lidarFn(lidarObj);
        if (lidarFn.typeId() != MaroLidarNode::id) continue;
        if (!lidarFn.findPlug(MaroLidarNode::aEnabled, false).asBool()) continue;

        LidarNodeState& state = s_lidarNodeState[MObjectHandle::objectHashCode(lidarObj)];
        if (!state.handle.isValid() || state.handle != lidarObj) {
            state = LidarNodeState{};
            state.handle = MObjectHandle(lidarObj);
        }

        const double updateRate =
            lidarFn.findPlug(MaroLidarNode::aUpdateRate, false).asDouble();
        if (std::isfinite(updateRate) && updateRate > 0.0 && state.hasScanned) {
            const std::chrono::duration<double> sinceLast = tickNow - state.lastScan;
            if (sinceLast.count() < 1.0 / updateRate) continue;
        }

        std::vector<Vec3> points;
        const LidarScanResult result = scanLidarNode(lidarObj, *s_scanEngine, unit, points);

        if (result == LidarScanResult::kRayCountExceeded) {
            if (!state.warnedRayCap) {
                state.warnedRayCap = true;
                const int verticalSamples =
                    lidarFn.findPlug(MaroLidarNode::aVerticalSamples, false).asInt();
                const int horizontalSamples =
                    lidarFn.findPlug(MaroLidarNode::aHorizontalSamples, false).asInt();
                maro::BoadMaro::error(
                    "MaroPump.collectLidarScans.RayCountTooLarge",
                    MString("Maro: maroLidar '") + lidarFn.name() + "' asks for " +
                        verticalSamples + " x " + horizontalSamples +
                        " rays, over the per-tick cap of " +
                        static_cast<int>(kMaxRaysPerScan) +
                        ". The scan is skipped -- lower verticalSamples/"
                        "horizontalSamples.",
                    maro::onfix::capture("maroLidar", "verticalSamples", lidarFn.name()));
            }
            continue;
        }
        // 값이 다시 상한 아래로 내려오면 래치를 푼다.
        state.warnedRayCap = false;

        if (result != LidarScanResult::kOk) continue;

        // 스캔이 실제로 돌았다. 히트가 하나도 없었더라도 이번 틱에 이
        // 노드의 몫은 끝났으므로 스로틀 기준점을 갱신한다.
        state.lastScan = tickNow;
        state.hasScanned = true;

        if (!points.empty()) {
            LidarSample sample;
            sample.unit = unit;
            sample.points = std::move(points);
            runtime.lidarQueue().push(std::move(sample));
        }
    }
}
```

`collectSamples()`(발행 방향, `collectLidarScans`와 다른 함수)의 `const SceneUnit unit = currentSceneUnit();`는 **그대로 둔다** — 이제 이 함수는 `MaroLidarScan.h`가 내보내는 같은 함수를 부르는 것이므로 코드 변경이 필요 없다(단, 위 include 정리로 헤더 경로만 바뀐다).

- [ ] **Step 4: `src/maro_plugin/CMakeLists.txt`에 새 소스 추가**

`SOURCE_FILES` 목록의 `MaroPointCloudNode.cpp` 바로 다음에 추가:
```cmake
    MaroLidarScan.cpp
```

- [ ] **Step 5: 빌드 + 전체 테스트**

전역 제약의 빌드+테스트 절차를 실행한다. **이 태스크의 완료 기준은 기존 `maya_lidar_node`/`maya_lidar_publish` 테스트가 리팩터 전과 동일하게 그린인 것이다** — 새 테스트를 추가하지 않는다(순수 리팩터, 관찰 가능한 동작 불변).

---

### Task 3: `maroSnapshotLidarScan` 커맨드 (브리지 독립적 1회성 스냅샷)

이 태스크는 스펙의 두 커맨드(`maroCreateLidar`/`maroSnapshotLidarScan`) 중 `maroSnapshotLidarScan`만 C++로 만든다. **`maroCreateLidar`는 만들지 않는다** — 조사 결과 축 생성이 이미 전용 C++ 커맨드 없이 `cmds.createNode("maroAxis")`를 Python에서 직접 부르는 패턴이었고(`maroDagMenu.py:492`), `maroLidar` 생성도 검증 로직이 전혀 필요 없는 단순 `createNode`라 같은 패턴을 따르는 것이 이 코드베이스의 실제 관례에 더 맞다(Task 4에서 `cmds.createNode("maroLidar")`를 직접 부른다). 이건 스펙 §2/§4가 명시한 두 커맨드 중 하나를 실제 코드베이스 관례에 맞춰 뺀 것이므로 여기 기록해 둔다 — 기능은 그대로다(노드 생성 자체는 검증이 필요 없어 네이티브 `createNode`로 충분).

**Files:**
- Modify: `src/maro_plugin/MaroAxisEditorCommands.h` (또는 새 `MaroLidarCommands.h/.cpp` — 아래 Step 1 참고)
- Create: `src/maro_plugin/MaroLidarCommands.h`
- Create: `src/maro_plugin/MaroLidarCommands.cpp`
- Modify: `src/maro_plugin/MaroPluginMain.cpp`
- Modify: `src/maro_plugin/CMakeLists.txt`
- Test: `tests/maya/test_lidar_commands.py`
- Modify: `tests/CMakeLists.txt`

**Interfaces:**
- Consumes: `maro::scanLidarNode`/`maro::currentSceneUnit`(Task 2), `maro::MaroLidarNode::id`, `maro::MaroPointCloudNode::id`/`aPoints`(Task 1).
- Produces: Maya 커맨드 `maroSnapshotLidarScan <lidarNode> <pointCloudNode>`(undoable). Task 4의 설정 팝업이 "Scan now" 버튼에서 `cmds.maroSnapshotLidarScan(lidar, pointCloud)`로 부른다.

- [ ] **Step 1: `MaroLidarCommands.h` 작성**

새 파일 쌍으로 둔다 — `MaroAxisEditorCommands.h/.cpp`는 축/capability 전용이고, 이 커맨드는 LiDAR 전용이라 파일을 분리하는 것이 기존 "파일 하나당 명확한 책임 하나" 관례에 맞는다.

```cpp
#pragma once

#include <maya/MPxCommand.h>
#include <maya/MSyntax.h>
#include <maya/MDGModifier.h>

namespace maro {

// <lidarNode> <pointCloudNode>: lidarNode를 즉시 동기 스캔해 그 결과를
// pointCloudNode.points에 undoable하게 반영한다. maroStartBridge/MaroPump와
// 완전히 독립적이다 -- 브리지가 꺼져 있어도 동작한다.
class MaroSnapshotLidarScanCommand : public MPxCommand {
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

}  // namespace maro
```

- [ ] **Step 2: `MaroLidarCommands.cpp` 작성**

`MaroAddCapabilityCommand::doIt`(`MaroAxisEditorCommands.cpp:361-501`)와 정확히 같은 골격(`MArgDatabase` + `MSelectionList` 파싱, `try/catch` 커맨드 경계, `ScopedCommandContext`, `m_modifier`로 스테이징 후 `redoIt()`으로 커밋, 실패 시 롤백)을 따른다.

```cpp
#include "MaroLidarCommands.h"

#include <vector>

#include <maya/MArgDatabase.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MFnPointArrayData.h>
#include <maya/MPointArray.h>
#include <maya/MSelectionList.h>

#include "maro_lidar/ScanEngine.h"
#include "maro_transform/Types.h"

#include "MaroDiag.h"
#include "MaroLidarNode.h"
#include "MaroLidarScan.h"
#include "MaroPointCloudNode.h"

namespace maro {

void* MaroSnapshotLidarScanCommand::creator() { return new MaroSnapshotLidarScanCommand(); }

MSyntax MaroSnapshotLidarScanCommand::newSyntax() {
    MSyntax syntax;
    syntax.setObjectType(MSyntax::kSelectionList, 2, 2);
    return syntax;
}

MStatus MaroSnapshotLidarScanCommand::doIt(const MArgList& args) {
    maro::ScopedCommandContext ctxMarker("MaroSnapshotLidarScanCommand");
    try {
        MStatus status;
        MArgDatabase argData(syntax(), args, &status);
        if (!status) return status;

        MSelectionList selection;
        argData.getObjects(selection);
        if (selection.length() != 2) {
            maro::BoadMaro::error(
                "MaroSnapshotLidarScanCommand.WrongArgCount",
                "Maro: maroSnapshotLidarScan needs exactly two arguments: "
                "<lidarNode> <pointCloudNode>.",
                maro::onfix::capture("", "", ""));
            return MS::kFailure;
        }

        MObject lidarObj, pointCloudObj;
        selection.getDependNode(0, lidarObj);
        selection.getDependNode(1, pointCloudObj);

        MFnDependencyNode lidarFn(lidarObj);
        if (lidarFn.typeId() != MaroLidarNode::id) {
            maro::BoadMaro::error(
                "MaroSnapshotLidarScanCommand.NotMaroLidarNode",
                MString("Maro: '") + lidarFn.name() + "' is not a maroLidar node.",
                maro::onfix::capture(lidarFn.typeName(), "", lidarFn.name()));
            return MS::kFailure;
        }
        MFnDependencyNode pointCloudFn(pointCloudObj);
        if (pointCloudFn.typeId() != MaroPointCloudNode::id) {
            maro::BoadMaro::error(
                "MaroSnapshotLidarScanCommand.NotMaroPointCloudNode",
                MString("Maro: '") + pointCloudFn.name() + "' is not a maroPointCloud node.",
                maro::onfix::capture(pointCloudFn.typeName(), "", pointCloudFn.name()));
            return MS::kFailure;
        }

        // 브리지의 공유 ScanEngine과 무관한 자체 인스턴스 -- 이 커맨드는
        // MaroPump/MaroRosRuntime 상태를 전혀 건드리지 않는다.
        maro::lidar::ScanEngine engine;
        std::vector<Vec3> points;
        const LidarScanResult result =
            scanLidarNode(lidarObj, engine, currentSceneUnit(), points);

        if (result != LidarScanResult::kOk) {
            const char* reason = "unknown";
            switch (result) {
                case LidarScanResult::kNoTargetMesh: reason = "no target mesh connected"; break;
                case LidarScanResult::kMeshExtractFailed: reason = "failed to read the target mesh"; break;
                case LidarScanResult::kInvalidConfig: reason = "invalid angle/range configuration"; break;
                case LidarScanResult::kRayCountExceeded: reason = "verticalSamples x horizontalSamples exceeds the per-scan cap"; break;
                default: break;
            }
            maro::BoadMaro::error(
                "MaroSnapshotLidarScanCommand.ScanFailed",
                MString("Maro: scan of '") + lidarFn.name() + "' failed: " + reason + ".",
                maro::onfix::capture(lidarFn.typeName(), "", lidarFn.name()));
            return MS::kFailure;
        }

        MPointArray mayaPoints;
        mayaPoints.setLength(static_cast<unsigned int>(points.size()));
        for (unsigned int i = 0; i < mayaPoints.length(); ++i) {
            mayaPoints[i] = MPoint(points[i].x, points[i].y, points[i].z, 1.0);
        }
        MFnPointArrayData pointArrayDataFn;
        MObject pointsData = pointArrayDataFn.create(mayaPoints);

        MPlug pointsPlug = pointCloudFn.findPlug(MaroPointCloudNode::aPoints, false);
        status = m_modifier.newPlugValue(pointsPlug, pointsData);
        if (!status) {
            maro::BoadMaro::error(
                "MaroSnapshotLidarScanCommand.SetPointsFailed",
                MString("Maro: failed to stage the points update on '") +
                    pointCloudFn.name() + "'.",
                maro::onfix::capture(pointCloudFn.typeName(), "points", pointCloudFn.name()));
            return status;
        }

        m_stagedChange = true;
        return redoIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroSnapshotLidarScanCommand.doIt.Exception",
                              MString("Maro: maroSnapshotLidarScan failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroSnapshotLidarScanCommand.doIt.UnknownException",
                              "Maro: maroSnapshotLidarScan failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroSnapshotLidarScanCommand::redoIt() {
    maro::ScopedCommandContext ctxMarker("MaroSnapshotLidarScanCommand");
    try {
        return m_modifier.doIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroSnapshotLidarScanCommand.redoIt.Exception",
                              MString("Maro: maroSnapshotLidarScan redo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroSnapshotLidarScanCommand.redoIt.UnknownException",
                              "Maro: maroSnapshotLidarScan redo failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroSnapshotLidarScanCommand::undoIt() {
    maro::ScopedCommandContext ctxMarker("MaroSnapshotLidarScanCommand");
    try {
        return m_modifier.undoIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroSnapshotLidarScanCommand.undoIt.Exception",
                              MString("Maro: maroSnapshotLidarScan undo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroSnapshotLidarScanCommand.undoIt.UnknownException",
                              "Maro: maroSnapshotLidarScan undo failed with unknown error.");
        return MS::kFailure;
    }
}

}  // namespace maro
```

**주의**: `MDGModifier::newPlugValue(MPlug, MObject)`가 `MFnData`로 감싼 데이터를 undoable하게 쓰는 정확한 API인지 확인이 필요하다 — 만약 이 오버로드가 존재하지 않거나 시그니처가 다르면(devkit 헤더 `MDGModifier.h`를 직접 확인), `MFnPointArrayData`로 만든 `pointsData`(MObject)를 그대로 `m_modifier.newPlugValueMObject(pointsPlug, pointsData, /*keepExisting=*/false)` 형태로 바꾼다. 구현자는 이 커맨드를 작성하기 전에 `devkitBase/include/maya/MDGModifier.h`에서 `MObject`를 값으로 받는 오버로드의 정확한 이름을 확인하고, 다른 이름이면 그 이름으로 두 자리(위 코드 한 곳)를 고친다.

- [ ] **Step 3: `MaroPluginMain.cpp`에 등록/해제 추가**

`#include "MaroLidarNode.h"` 다음에 추가:
```cpp
#include "MaroLidarCommands.h"
```

`initializePlugin`에서 `maroUnbindAxis` 등록 블록(415-421행) 바로 다음, `MaroDeleteWatcher::install()` 호출(423행) 바로 전에 삽입:
```cpp
    status = plugin.registerCommand("maroSnapshotLidarScan",
                                    maro::MaroSnapshotLidarScanCommand::creator,
                                    maro::MaroSnapshotLidarScanCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroSnapshotLidarScan");
        return status;
    }
```

`uninitializePlugin`에서 `plugin.deregisterCommand("maroUnbindAxis");`(572행) **바로 앞**에 삽입(등록 역순 규율 — 이 명령은 `maroUnbindAxis` 다음에 등록됐으므로 해제는 그 앞):
```cpp
        plugin.deregisterCommand("maroSnapshotLidarScan");
```

- [ ] **Step 4: `src/maro_plugin/CMakeLists.txt`에 새 소스 추가**

`SOURCE_FILES` 목록의 `MaroLidarScan.cpp` 바로 다음에 추가:
```cmake
    MaroLidarCommands.cpp
```

- [ ] **Step 5: mayapy 배치 테스트 작성 — `tests/maya/test_lidar_commands.py`**

`tests/maya/test_axis_editor_commands.py`와 같은 패턴(`maya.standalone.initialize()`, 플러그인 로드, undo/redo 검증)을 따른다. 씬에 평면 하나(레이가 반드시 맞을 만큼 크게)와 그 위에 놓인 `maroLidar`를 만들어 실제 스캔이 점을 만들어내는지 확인한다.

```python
"""maroSnapshotLidarScan의 undo/redo 계약과 실제 스캔 결과를 배치 모드에서
고정한다. 브리지(rclcpp) 없이 동작해야 한다는 것이 이 커맨드의 핵심
요구사항이므로, maroStartBridge를 전혀 부르지 않는다."""
import os

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

# 레이가 확실히 맞을 큰 평면. 라이다 노드를 그 위 원점에 둔다.
groundTransform, _ = cmds.polyPlane(width=100, height=100, subdivisionsX=1, subdivisionsY=1)
cmds.setAttr(groundTransform + ".translateY", -5)

lidar = cmds.createNode("maroLidar")
lidar = cmds.ls(lidar, long=True)[0]
cmds.connectAttr(groundTransform + ".message", lidar + ".targetMeshes[0]")
# 아래를 보도록: 수직 각도를 -90도 근방으로.
cmds.setAttr(lidar + ".verticalMinAngle", -1.5707963267948966)
cmds.setAttr(lidar + ".verticalMaxAngle", -1.4707963267948966)
cmds.setAttr(lidar + ".verticalSamples", 2)
cmds.setAttr(lidar + ".horizontalSamples", 4)
cmds.setAttr(lidar + ".rangeMax", 100.0)

pointCloud = cmds.createNode("maroPointCloud")
pointCloud = cmds.ls(pointCloud, long=True)[0]

before = cmds.getAttr(pointCloud + ".points")
assert len(before) == 0, f"expected an empty points array before the first scan, got {before}"
print("pre-scan points empty OK")

cmds.maroSnapshotLidarScan(lidar, pointCloud)
after = cmds.getAttr(pointCloud + ".points")
assert len(after) > 0, "expected the scan to find hits on the ground plane"
print(f"scan produced {len(after)} points OK")

cmds.undo()
undone = cmds.getAttr(pointCloud + ".points")
assert len(undone) == 0, f"expected undo to clear points back to empty, got {undone}"
print("undo OK")

cmds.redo()
redone = cmds.getAttr(pointCloud + ".points")
assert len(redone) == len(after), "expected redo to restore the same scan result"
print("redo OK")

# 브리지가 꺼져 있는 상태에서 전부 동작했다는 것이 이 커맨드의 핵심 계약이다.
assert cmds.maroBridgeStats()[0] == 0, "this test must not have started the bridge"
print("bridge-independence OK")

# 잘못된 노드 타입은 거부돼야 한다.
try:
    cmds.maroSnapshotLidarScan(groundTransform, pointCloud)
    raise AssertionError("expected maroSnapshotLidarScan to reject a non-maroLidar first argument")
except RuntimeError:
    print("rejects non-maroLidar first argument OK")
```

- [ ] **Step 6: `tests/CMakeLists.txt`에 등록**

`foreach(maya_test ...)` 목록에 `point_cloud_node` 바로 다음에 `lidar_commands`를 추가한다.

- [ ] **Step 7: 빌드 + 전체 테스트**

전역 제약의 빌드+테스트 절차를 실행한다. `maya_lidar_commands`와 `maya_point_cloud_node`를 포함해 전체 스위트가 그린인지 확인한다.

---

### Task 4: 네이티브 마킹메뉴 "Maro LiDAR" 항목 + 설정 팝업

**Files:**
- Modify: `python/maroDagMenu.py`
- Modify: `python/maroRosProxy.py` (헬퍼 공개)
- Create: `python/maroLidarPanel.py`
- Modify: `python/maroMainWindow.py`
- Modify: `src/maro_plugin/CMakeLists.txt`
- Test: `tests/maya/test_lidar_menu.py`
- Modify: `tests/CMakeLists.txt`
- Modify: `docs/maro-main-ui-manual-checklist.md`

**Interfaces:**
- Consumes: Task 1의 `maroPointCloud`(+ `aSourceLidar`), Task 3의 `maroSnapshotLidarScan`, 기존 `maroDagMenu._nativeMenuSuppressed()`/`_resolveObject()`/`_melGlobalString()`/`_addMenuItem()`(수정 대상), `maroRosProxy.PROXY_GROUP`.
- Produces: `maroDagMenu._onLidarMenuItemClicked(object_)`(마킹메뉴 핸들러, 모달 다이얼로그 없음 — mayapy에서 직접 호출 가능), `maroDagMenu._findLidarForMesh(object_)`, `maroDagMenu._hasMeshShape(object_)`, `maroDagMenu._createPlaceholderTargetMesh(object_)`, `maroRosProxy.ensureProxyGroup()`(공개, 기존 `_ensureProxyGroup()`의 개명), `maroLidarPanel.openLidarPanel(lidar)`/`maroLidarPanel.stop()`.

- [ ] **Step 1: `python/maroRosProxy.py`에서 `_ensureProxyGroup`을 공개 `ensureProxyGroup`으로 개명**

이 함수는 지금 이 모듈 내부에서만 쓰이는 사설(private) 함수지만, 이 태스크가 만드는 새 포인트클라우드를 같은 그룹 아래 둬야 해서(§1의 격리 관찰과 같은 이유) 두 번째 호출자가 생긴다. 밑줄을 떼고 다른 모든 내부 호출부를 갱신한다.

`python/maroRosProxy.py`에서 `def _ensureProxyGroup():`를 `def ensureProxyGroup():`로 바꾸고, 파일 안의 다른 모든 `_ensureProxyGroup(` 호출을 `ensureProxyGroup(`으로 바꾼다(`grep -n "_ensureProxyGroup" python/maroRosProxy.py`로 호출부를 전부 찾아 각각 고친다 — 정의 1곳 + `_refreshMayaIsolation()`/`start()` 안의 호출들).

- [ ] **Step 2: `python/maroDagMenu.py`에 LiDAR 마킹메뉴 항목 추가**

모듈 상단, `MENU_ITEM_LABEL = "Maro node editor"` 바로 다음에 추가:
```python
LIDAR_MENU_ITEM_LABEL = "Maro LiDAR"
```

`_addMenuItem()` 함수(345-365행)를 다음으로 교체 — 기존 축 항목 추가 다음에 LiDAR 항목 추가를 이어 붙인다:
```python
def _addMenuItem():
    """생성한 MEL 래퍼가 부른다. 인자는 MEL 전역 변수에서 읽는다.

    여기서 나는 예외는 절대 밖으로 내보내지 않는다 -- MEL 쪽으로 새어
    나가면 우클릭 메뉴 생성 전체가 에러로 끝난다. (원본은 이미 이 시점에
    호출이 끝나 있으므로 Maya 본래 항목은 어차피 살아 있다.)
    """
    try:
        parentMenu = _melGlobalString(_MEL_PARENT_VAR)
        if not parentMenu or not cmds.popupMenu(parentMenu, exists=True):
            return
        if _nativeMenuSuppressed():
            return
        object_ = _resolveObject()
        if not object_:
            return
        cmds.menuItem(parent=parentMenu, label=MENU_ITEM_LABEL,
                      command=lambda *_args: _onMenuItemClicked(object_))
        # "Maro LiDAR"는 오브젝트 종류와 무관하게 항상 노출된다(설계 스펙
        # §5.1) -- 메쉬가 없어도 클릭 시점에 조건을 자동으로 맞춘다
        # (_onLidarMenuItemClicked/_createPlaceholderTargetMesh 참고).
        cmds.menuItem(parent=parentMenu, label=LIDAR_MENU_ITEM_LABEL,
                      command=lambda *_args: _onLidarMenuItemClicked(object_))
    except Exception as exc:  # pragma: no cover - UI 경로
        cmds.warning("Maro: failed to add the '{}'/'{}' menu items: {}"
                     .format(MENU_ITEM_LABEL, LIDAR_MENU_ITEM_LABEL, exc))
```

파일 끝(`_onMenuItemClicked` 함수 다음)에 새 함수들을 추가한다:

```python
def _findLidarForMesh(object_):
    """object_가 이미 어떤 maroLidar의 targetMeshes[]에 연결돼 있으면 그 풀
    DAG 경로, 없으면 None.

    _findBoundAxis()와 같은 이유로 shapes=True가 필요하다: maroLidar도
    로케이터형 DAG 셰이프 노드라서, 기본값(shapes=False)이면 셰이프 자신이
    아니라 부모 트랜스폼 이름이 돌아온다.
    """
    connections = cmds.listConnections(
        object_, type="maroLidar", plugs=False, shapes=True) or []
    if not connections:
        return None
    return cmds.ls(connections[0], long=True)[0]


def _hasMeshShape(object_):
    """object_ 자신이 메쉬 셰이프를 가진 트랜스폼이거나 메쉬 셰이프 그
    자체인가. maroLidar.targetMeshes는 관례상 메쉬 **트랜스폼**의 .message에
    연결한다(MaroLidarScan.cpp의 extractMeshBuffers와 같은 관례 --
    MFnMesh가 셰이프까지 스스로 내려간다)."""
    if cmds.listRelatives(object_, shapes=True, fullPath=True, type="mesh"):
        return True
    return cmds.objectType(object_) == "mesh"


def _createPlaceholderTargetMesh(object_):
    """object_에 메쉬 셰이프가 없을 때 자동으로 만드는 대체 스캔 타겟
    (설계 스펙 §5.2).

    작은 구를 object_의 자식으로, object_의 월드 바운딩박스 상단(ymax)
    중앙에 놓는다. 바운딩박스가 점에 가까운 조인트/로케이터는 거의 원점에
    생긴다 -- 계산 자체는 오브젝트 종류와 무관하게 일관되게 적용되므로 이는
    받아들여지는 동작이다. 생성 직후 이 구를 선택 상태로 만들어 사용자가
    바로 크기/위치를 다듬을 수 있게 한다.
    """
    shortName = object_.split("|")[-1]
    sphereTransform, _makeNode = cmds.polySphere(name=shortName + "_maroLidarTarget", radius=1.0)
    cmds.parent(sphereTransform, object_)
    sphereFullPath = cmds.ls(sphereTransform, long=True)[0]

    bbox = cmds.exactWorldBoundingBox(object_)
    topCenter = ((bbox[0] + bbox[3]) / 2.0, bbox[4], (bbox[2] + bbox[5]) / 2.0)
    cmds.xform(sphereFullPath, worldSpace=True, translation=topCenter)

    cmds.select(sphereFullPath, replace=True)
    return sphereFullPath


def _onLidarMenuItemClicked(object_):
    """"Maro LiDAR" 마킹메뉴 항목의 핸들러. _onMenuItemClicked()와 달리
    promptDialog/colorEditor 같은 모달 다이얼로그를 전혀 쓰지 않는다 --
    LiDAR는 ONE/GSON 그루핑에 참여하지 않아 이름/색 입력이 필요 없다
    (설계 스펙 §5.3). 그래서 이 함수는 mayapy 배치에서도 안전하게 직접 호출할
    수 있다(tests/maya/test_lidar_menu.py)."""
    import maroLidarPanel
    import maroRosProxy

    existingLidar = _findLidarForMesh(object_)
    if existingLidar is not None:
        maroLidarPanel.openLidarPanel(existingLidar)
        return

    cmds.undoInfo(openChunk=True)
    lidar = None
    try:
        lidar = cmds.createNode("maroLidar")
        lidar = cmds.ls(lidar, long=True)[0]
        # createNode("maroLidar")는 로케이터형 DAG 셰이프라 Maya가 새
        # 트랜스폼을 자동으로 만든다(_onMenuItemClicked의 축 생성과 같은
        # 관례). 축과 달리 여기서는 그 트랜스폼을 클릭한 오브젝트의 실제
        # DAG 자식으로 옮긴다 -- LiDAR는 탑재된 오브젝트의 월드 트랜스폼을
        # 그대로 상속받아야 하기 때문이다(축의 메시지 커넥션 바인딩과
        # 다른 이유).
        lidarParents = cmds.listRelatives(lidar, parent=True, fullPath=True) or []
        if lidarParents:
            cmds.parent(lidarParents[0], object_)
            lidar = cmds.ls(lidar, long=True)[0]

        pointCloud = cmds.createNode("maroPointCloud")
        pointCloud = cmds.ls(pointCloud, long=True)[0]
        pointCloudParents = cmds.listRelatives(pointCloud, parent=True, fullPath=True) or []
        if pointCloudParents:
            cmds.parent(pointCloudParents[0], maroRosProxy.ensureProxyGroup())
            pointCloud = cmds.ls(pointCloud, long=True)[0]
        cmds.connectAttr(lidar + ".message", pointCloud + ".sourceLidar")

        targetMesh = object_ if _hasMeshShape(object_) else _createPlaceholderTargetMesh(object_)
        cmds.connectAttr(targetMesh + ".message", lidar + ".targetMeshes[0]")
    except Exception as exc:  # noqa: BLE001 -- 마킹 메뉴 콜백 경계
        cmds.warning("Maro: failed to create a LiDAR on '{}': {}".format(object_, exc))
        if lidar and cmds.objExists(lidar):
            parents = cmds.listRelatives(lidar, parent=True, fullPath=True) or []
            cmds.delete(lidar)
            for parent in parents:
                if cmds.objExists(parent):
                    cmds.delete(parent)
        return
    finally:
        cmds.undoInfo(closeChunk=True)

    maroLidarPanel.openLidarPanel(lidar)
```

- [ ] **Step 3: `python/maroLidarPanel.py` 작성**

```python
"""LiDAR 설정 팝업 -- maroLidar 노드 하나를 설정하는 독립 최상위 창(설계
스펙 §5.3).

maroSingleObjectNodeEditor.py(SONE)와 같은 패턴이다: 노드의 풀 DAG 경로를
키로 삼는 _OPEN_EDITORS 싱글톤, stop()이 플러그인 언로드 시 전부 닫음
(maroMainWindow.teardown()에 등록). LiDAR는 ONE에는 참여하지 않는다 -- 축이
아니므로 GSON 그리드에 낄 자리가 없고, 이 팝업 하나로 완결된다.
"""
import maya.cmds as cmds
from PySide6 import QtCore, QtWidgets

# (필드 이름, 표시 라벨, 위젯 종류). "angle" 종류는 cmds.getAttr/setAttr이
# 라디안으로 주고받는다는 것을 그대로 노출한다(변환은 이번 범위 밖).
_ATTRS = [
    ("verticalSamples", "Vertical samples", "int"),
    ("verticalMinAngle", "Vertical min angle (rad)", "float"),
    ("verticalMaxAngle", "Vertical max angle (rad)", "float"),
    ("horizontalSamples", "Horizontal samples", "int"),
    ("horizontalMinAngle", "Horizontal min angle (rad)", "float"),
    ("horizontalMaxAngle", "Horizontal max angle (rad)", "float"),
    ("rangeMin", "Range min (m)", "float"),
    ("rangeMax", "Range max (m)", "float"),
    ("updateRate", "Update rate (Hz)", "float"),
    ("frameId", "Frame id", "string"),
    ("enabled", "Enabled", "bool"),
]

_OPEN_EDITORS = {}  # lidarFullPath -> MaroLidarPanel


def openLidarPanel(lidar):
    """lidar의 설정 팝업을 연다. 이미 열려 있으면 그 창을 앞으로 가져온다."""
    existing = _OPEN_EDITORS.get(lidar)
    if existing is not None:
        try:
            existing.raise_()
            existing.activateWindow()
            return existing
        except RuntimeError:
            del _OPEN_EDITORS[lidar]

    panel = MaroLidarPanel(lidar)
    _OPEN_EDITORS[lidar] = panel
    panel.show()
    return panel


def stop():
    """플러그인 언로드/창 닫힘 시 열려 있는 LiDAR 설정 팝업을 전부 닫는다.
    maroSingleObjectNodeEditor.stop()과 같은 규율로 한 창의 실패가 나머지
    창의 정리를 막지 않게 한다."""
    for panel in list(_OPEN_EDITORS.values()):
        try:
            panel.close()
            panel.deleteLater()
        except Exception:  # noqa: BLE001 -- 언로드 정리 경계
            import traceback
            traceback.print_exc()
    _OPEN_EDITORS.clear()


def _pairedPointCloud(lidar):
    """lidar가 만든(aSourceLidar로 연결된) maroPointCloud, 없으면 None."""
    connections = cmds.listConnections(
        lidar, type="maroPointCloud", plugs=False, shapes=True) or []
    if not connections:
        return None
    return cmds.ls(connections[0], long=True)[0]


class MaroLidarPanel(QtWidgets.QWidget):
    """maroLidar 노드 하나의 설정 폼. setStyleSheet()를 부르지 않는다."""

    def __init__(self, lidar, parent=None):
        super().__init__(parent, QtCore.Qt.Window)
        self._lidar = lidar
        self.setWindowTitle(lidar.split("|")[-1])

        layout = QtWidgets.QFormLayout(self)
        self._fields = {}
        for attrName, label, kind in _ATTRS:
            field = self._makeField(kind)
            layout.addRow(label, field)
            self._fields[attrName] = (field, kind)
        self._loadValues()

        self._meshList = QtWidgets.QListWidget()
        layout.addRow("Target meshes", self._meshList)
        meshButtons = QtWidgets.QHBoxLayout()
        addMeshButton = QtWidgets.QPushButton("타겟 메쉬 추가")
        addMeshButton.clicked.connect(self._onAddTargetMesh)
        removeMeshButton = QtWidgets.QPushButton("선택 제거")
        removeMeshButton.clicked.connect(self._onRemoveTargetMesh)
        meshButtons.addWidget(addMeshButton)
        meshButtons.addWidget(removeMeshButton)
        layout.addRow(meshButtons)
        self._refreshMeshList()

        applyButton = QtWidgets.QPushButton("적용")
        applyButton.clicked.connect(self._onApply)
        layout.addRow(applyButton)

        scanButton = QtWidgets.QPushButton("Scan now")
        scanButton.clicked.connect(self._onScanNow)
        layout.addRow(scanButton)

    def closeEvent(self, event):
        try:
            if _OPEN_EDITORS.get(self._lidar) is self:
                del _OPEN_EDITORS[self._lidar]
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
            import traceback
            traceback.print_exc()
        super().closeEvent(event)

    def _makeField(self, kind):
        if kind == "bool":
            return QtWidgets.QCheckBox()
        if kind == "int":
            field = QtWidgets.QSpinBox()
            field.setRange(1, 100000)
            return field
        if kind == "string":
            return QtWidgets.QLineEdit()
        field = QtWidgets.QDoubleSpinBox()
        field.setRange(-100000.0, 100000.0)
        field.setDecimals(4)
        return field

    def _loadValues(self):
        if not cmds.objExists(self._lidar):
            return
        for attrName, (field, kind) in self._fields.items():
            plugName = self._lidar + "." + attrName
            if kind == "bool":
                field.setChecked(bool(cmds.getAttr(plugName)))
            elif kind == "string":
                field.setText(cmds.getAttr(plugName) or "")
            else:
                field.setValue(cmds.getAttr(plugName))

    def _onApply(self):
        try:
            cmds.undoInfo(openChunk=True)
            for attrName, (field, kind) in self._fields.items():
                plugName = self._lidar + "." + attrName
                if kind == "bool":
                    cmds.setAttr(plugName, field.isChecked())
                elif kind == "string":
                    cmds.setAttr(plugName, field.text(), type="string")
                else:
                    cmds.setAttr(plugName, field.value())
        except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
            cmds.warning("Maro: failed to apply LiDAR settings: {}".format(exc))
        finally:
            cmds.undoInfo(closeChunk=True)

    def _refreshMeshList(self):
        self._meshList.clear()
        if not cmds.objExists(self._lidar):
            return
        connections = cmds.listConnections(
            self._lidar + ".targetMeshes", source=True, destination=False, shapes=False) or []
        for mesh in connections:
            self._meshList.addItem(cmds.ls(mesh, long=True)[0])

    def _onAddTargetMesh(self):
        selection = cmds.ls(selection=True, long=True) or []
        if not selection:
            cmds.warning("Maro: select a mesh to add as a LiDAR target first.")
            return
        try:
            cmds.undoInfo(openChunk=True)
            usedIndices = set(cmds.getAttr(
                self._lidar + ".targetMeshes", multiIndices=True) or [])
            nextIndex = 0
            while nextIndex in usedIndices:
                nextIndex += 1
            cmds.connectAttr(
                selection[0] + ".message",
                "{}.targetMeshes[{}]".format(self._lidar, nextIndex))
        except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
            cmds.warning("Maro: failed to add target mesh: {}".format(exc))
        finally:
            cmds.undoInfo(closeChunk=True)
        self._refreshMeshList()

    def _onRemoveTargetMesh(self):
        item = self._meshList.currentItem()
        if item is None:
            return
        meshFullPath = item.text()
        try:
            cmds.undoInfo(openChunk=True)
            pairs = cmds.listConnections(
                self._lidar + ".targetMeshes", connections=True, plugs=True,
                source=True, destination=False) or []
            # pairs는 [destPlug0, srcPlug0, destPlug1, srcPlug1, ...] 순서다.
            for i in range(0, len(pairs), 2):
                destPlug, srcPlug = pairs[i], pairs[i + 1]
                sourceNode = cmds.ls(srcPlug.split(".")[0], long=True)[0]
                if sourceNode == meshFullPath:
                    cmds.disconnectAttr(srcPlug, destPlug)
                    break
        except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
            cmds.warning("Maro: failed to remove target mesh: {}".format(exc))
        finally:
            cmds.undoInfo(closeChunk=True)
        self._refreshMeshList()

    def _onScanNow(self):
        try:
            pointCloud = _pairedPointCloud(self._lidar)
            if pointCloud is None:
                cmds.warning(
                    "Maro: this LiDAR has no connected maroPointCloud to snapshot into.")
                return
            cmds.maroSnapshotLidarScan(self._lidar, pointCloud)
        except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
            cmds.warning("Maro: scan failed: {}".format(exc))
```

- [ ] **Step 4: `python/maroMainWindow.py`의 `teardown()`에 등록**

`teardown()` 함수 안, `maroSingleObjectNodeEditor.stop()` 블록(359-372행) 다음에 추가:
```python
    try:
        import maroLidarPanel
        maroLidarPanel.stop()
    except Exception:  # noqa: BLE001 -- Maya 콜백/언로드 경계
        import traceback
        traceback.print_exc()
```

- [ ] **Step 5: `src/maro_plugin/CMakeLists.txt`에 새 Python 모듈 등록**

`MARO_PLUGIN_PY_MODULES` 목록에 `maroLidarPanel`을 알파벳 순서에 맞게 추가(`maroDagMenu`, `maroDiagPanel`, `maroLidarPanel`, `maroMainWindow`, ...).

- [ ] **Step 6: mayapy 배치 테스트 작성 — `tests/maya/test_lidar_menu.py`**

`_onLidarMenuItemClicked()`는 모달 다이얼로그가 없으므로 직접 호출할 수 있다. `maroLidarPanel.openLidarPanel`을 QWidget을 만들지 않는 스텁으로 바꿔치기해서 QWidget 생성(배치에서 프로세스 abort)을 피한다.

```python
"""maroDagMenu의 "Maro LiDAR" 항목 핸들러(_onLidarMenuItemClicked)가 만드는
노드 그래프를 배치 모드에서 고정한다.

_onMenuItemClicked()(축 생성)와 달리 이 핸들러는 promptDialog/colorEditor
같은 모달 다이얼로그를 쓰지 않으므로 배치에서 직접 호출할 수 있다. 다만
마지막에 여는 설정 팝업(maroLidarPanel.openLidarPanel)은 QWidget을 만들어
배치 mayapy 프로세스를 abort시키므로, 그 함수를 기록용 스텁으로 바꿔치기
한다."""
import os

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
pluginDir = os.path.dirname(plugin)
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

import maroDagMenu  # noqa: E402
import maroLidarPanel  # noqa: E402

openedPanels = []
maroLidarPanel.openLidarPanel = lambda lidar: openedPanels.append(lidar)

# --- 메쉬가 있는 오브젝트 -----------------------------------------------
meshTransform, _ = cmds.polyCube(name="lidarTestCube")
maroDagMenu._onLidarMenuItemClicked(cmds.ls(meshTransform, long=True)[0])

lidars = cmds.ls(type="maroLidar", long=True)
assert len(lidars) == 1, f"expected exactly one maroLidar, got {lidars}"
lidar = lidars[0]

lidarParents = cmds.listRelatives(lidar, parent=True, fullPath=True) or []
assert lidarParents and lidarParents[0] == cmds.ls(meshTransform, long=True)[0], (
    "the LiDAR's transform must be parented under the clicked mesh")
print("lidar mounted under mesh transform OK")

targets = cmds.listConnections(lidar + ".targetMeshes", source=True, destination=False) or []
assert cmds.ls(meshTransform, long=True)[0] in [cmds.ls(t, long=True)[0] for t in targets], (
    "the clicked mesh itself must become the initial target -- no placeholder should be created")
print("mesh used directly as target (no placeholder) OK")

pointClouds = cmds.ls(type="maroPointCloud", long=True)
assert len(pointClouds) == 1
pointCloudParents = cmds.listRelatives(pointClouds[0], parent=True, fullPath=True) or []
import maroRosProxy  # noqa: E402
assert pointCloudParents and pointCloudParents[0] == maroRosProxy._PROXY_GROUP_PATH, (
    "the point cloud must be parented under maroRosProxy_grp for free viewport isolation")
print("point cloud parented under the ROS proxy group OK")

sourceLidarConnections = cmds.listConnections(
    pointClouds[0] + ".sourceLidar", shapes=True) or []
assert sourceLidarConnections and cmds.ls(sourceLidarConnections[0], long=True)[0] == lidar, (
    "the point cloud's sourceLidar must point back at the lidar that created it")
print("sourceLidar back-reference OK")

assert openedPanels == [lidar], f"expected openLidarPanel to be called with {lidar!r}, got {openedPanels}"
print("settings panel opened on creation OK")

# --- 재클릭: 재생성이 아니라 재오픈이어야 한다 ---------------------------
openedPanels.clear()
maroDagMenu._onLidarMenuItemClicked(cmds.ls(meshTransform, long=True)[0])
assert len(cmds.ls(type="maroLidar", long=True)) == 1, (
    "re-clicking a mesh that already has a LiDAR must not create a second one")
assert openedPanels == [lidar]
print("re-click reopens the existing panel instead of duplicating OK")

# --- 메쉬가 없는 오브젝트: placeholder 구 자동 생성 -----------------------
jointObject = cmds.createNode("joint", name="lidarTestJoint")
jointObject = cmds.ls(jointObject, long=True)[0]
cmds.xform(jointObject, worldSpace=True, translation=(10, 3, 0))
openedPanels.clear()
maroDagMenu._onLidarMenuItemClicked(jointObject)

placeholder = cmds.ls("lidarTestJoint_maroLidarTarget", long=True)
assert len(placeholder) == 1, "expected exactly one placeholder mesh to be created"
placeholderParents = cmds.listRelatives(placeholder[0], parent=True, fullPath=True) or []
assert placeholderParents and placeholderParents[0] == jointObject, (
    "the placeholder mesh must be a child of the clicked object")
print("placeholder mesh created as a child OK")

selection = cmds.ls(selection=True, long=True) or []
assert selection == [placeholder[0]], (
    f"expected the placeholder to be selected after creation, got {selection}")
print("placeholder auto-selected OK")

bbox = cmds.exactWorldBoundingBox(jointObject)
placeholderPos = cmds.xform(placeholder[0], query=True, worldSpace=True, translation=True)
expectedY = bbox[4]
assert abs(placeholderPos[1] - expectedY) < 1e-6, (
    f"expected the placeholder at bbox top (y={expectedY}), got y={placeholderPos[1]}")
print("placeholder positioned at bounding-box top OK")

secondLidar = [l for l in cmds.ls(type="maroLidar", long=True) if l != lidar]
assert len(secondLidar) == 1
targets2 = cmds.listConnections(secondLidar[0] + ".targetMeshes", source=True, destination=False) or []
assert placeholder[0] in [cmds.ls(t, long=True)[0] for t in targets2]
print("placeholder used as the new lidar's initial target OK")
```

- [ ] **Step 7: `tests/CMakeLists.txt`에 등록**

`foreach(maya_test ...)` 목록에 `lidar_commands` 바로 다음에 `lidar_menu`를 추가한다.

- [ ] **Step 8: 빌드 + 전체 테스트**

전역 제약의 빌드+테스트 절차를 실행한다.

- [ ] **Step 9: 수동 체크리스트에 `### 6-2` 절 추가**

`docs/maro-main-ui-manual-checklist.md`의 `## 6. LiDAR 설정 + 시각화 (Phase 5)` 안, `### 6-1` 다음에 추가:

```markdown
### 6-2. 마킹메뉴 + 설정 팝업 (Task 4)

1. 플러그인 로드 후 씬에 메쉬 오브젝트 하나를 만든다. 우클릭 → **[필수]**
   네이티브 마킹 메뉴에 "Maro node editor"와 나란히 "Maro LiDAR" 항목이
   보이는가.
2. "Maro LiDAR" 클릭 — **[필수]** 설정 팝업이 뜨고, 12개 필드가 기본값으로
   채워져 있는가.
3. 팝업에서 값 몇 개를 바꾸고 "적용" 클릭 → 팝업을 닫았다 다시 그 오브젝트를
   우클릭 → "Maro LiDAR" 클릭 — **[필수]** 새 팝업이 아니라 방금 바꾼 값이
   그대로 남아 있는 같은 노드의 팝업이 열리는가(재생성이 아니라 재오픈).
4. 메쉬가 아닌 오브젝트(예: 조인트, 로케이터)에 우클릭 → "Maro LiDAR" —
   **[필수]** 작은 구가 그 오브젝트의 자식으로 생기고 곧바로 선택된
   상태인가. 이동/크기 조절 툴로 바로 조작할 수 있는가.
5. 팝업에서 "타겟 메쉬 추가"(다른 메쉬를 선택한 채) → **[필수]** 리스트에
   추가되는가. "선택 제거" → 리스트에서 사라지고 실제 연결도 끊기는가
   (`cmds.listConnections`로 확인).
6. "Scan now" 클릭 → **[필수]** ROS 뷰포트에 포인트가 나타나는가(Task 1의
   드로우 오버라이드가 실제 스캔 데이터로 그리는 첫 확인).
```

---

### Task 5: 라이브 프리뷰

**Files:**
- Modify: `src/maro_plugin/MaroLidarNode.h`
- Modify: `src/maro_plugin/MaroLidarNode.cpp`
- Modify: `src/maro_plugin/MaroPump.cpp`
- Create: `src/maro_lidar/include/maro_lidar/Decimation.h`
- Create: `src/maro_lidar/src/Decimation.cpp`
- Modify: `src/maro_lidar/CMakeLists.txt`
- Modify: `tests/CMakeLists.txt` (GoogleTest, `maro_lidar_tests`)
- Test: `tests/lidar/test_decimation.cpp`
- Modify: `python/maroLidarPanel.py`
- Modify: `docs/maro-main-ui-manual-checklist.md`

**Interfaces:**
- Consumes: Task 2의 `scanLidarNode`/`LidarScanResult`, Task 1의 `MaroPointCloudNode::aPoints`/`aSourceLidar`.
- Produces: `MaroLidarNode::aVisualize`(새 bool 어트리뷰트), `maro::lidar::decimateForPreview(points, maxPoints) -> std::vector<Vec3>`.

- [ ] **Step 1: `MaroLidarNode`에 `visualize` 어트리뷰트 추가**

`MaroLidarNode.h`의 `aEnabled` 선언 다음에 추가:
```cpp
    static MObject aVisualize;
```

`MaroLidarNode.cpp`의 `MObject MaroLidarNode::aEnabled;` 다음에 추가:
```cpp
MObject MaroLidarNode::aVisualize;
```
`initialize()`의 `aEnabled` 등록 블록 다음에 추가:
```cpp
    aVisualize = numFn.create("visualize", "vis", MFnNumericData::kBoolean, false);
    numFn.setKeyable(true);
    addAttribute(aVisualize);
```
(기본값 `false` — 명시적으로 켜야만 라이브 갱신이 켜진다. 씬을 열자마자 모든 LiDAR가 매 틱 스캔을 시작하면 안 된다.)

- [ ] **Step 2: `src/maro_lidar/include/maro_lidar/Decimation.h` 작성**

`RayPattern.h`와 같은 위치/네임스페이스 관례를 따른다.

```cpp
#pragma once

#include <cstddef>
#include <vector>

#include "maro_transform/Types.h"

namespace maro::lidar {

// points가 maxPoints 이하면 그대로 복사해 돌려준다. 넘으면 전체 범위를
// 고르게 커버하는 스트라이드 샘플링으로 정확히 maxPoints개(또는 그
// 이하)로 줄인다. 순서는 보존한다(연속된 스캔 라인이 끊기지 않도록).
std::vector<maro::Vec3> decimateForPreview(const std::vector<maro::Vec3>& points,
                                            std::size_t maxPoints);

}  // namespace maro::lidar
```

- [ ] **Step 3: `src/maro_lidar/src/Decimation.cpp` 작성**

```cpp
#include "maro_lidar/Decimation.h"

namespace maro::lidar {

std::vector<maro::Vec3> decimateForPreview(const std::vector<maro::Vec3>& points,
                                            std::size_t maxPoints) {
    if (maxPoints == 0 || points.empty()) return {};
    if (points.size() <= maxPoints) return points;

    std::vector<maro::Vec3> decimated;
    decimated.reserve(maxPoints);
    const double stride = static_cast<double>(points.size()) / static_cast<double>(maxPoints);
    for (std::size_t i = 0; i < maxPoints; ++i) {
        const auto index = static_cast<std::size_t>(static_cast<double>(i) * stride);
        decimated.push_back(points[index < points.size() ? index : points.size() - 1]);
    }
    return decimated;
}

}  // namespace maro::lidar
```

- [ ] **Step 4: GoogleTest 작성 — `tests/lidar/test_decimation.cpp`**

```cpp
#include "maro_lidar/Decimation.h"

#include <gtest/gtest.h>

using maro::Vec3;
using maro::lidar::decimateForPreview;

TEST(DecimationTest, ReturnsInputUnchangedWhenUnderCap) {
    std::vector<Vec3> points = {{1, 0, 0}, {2, 0, 0}, {3, 0, 0}};
    auto result = decimateForPreview(points, 10);
    EXPECT_EQ(result.size(), 3u);
}

TEST(DecimationTest, ClampsToExactlyMaxPoints) {
    std::vector<Vec3> points;
    for (int i = 0; i < 10000; ++i) points.push_back(Vec3{static_cast<double>(i), 0, 0});
    auto result = decimateForPreview(points, 100);
    EXPECT_EQ(result.size(), 100u);
}

TEST(DecimationTest, PreservesOrderAndCoversFullRange) {
    std::vector<Vec3> points;
    for (int i = 0; i < 1000; ++i) points.push_back(Vec3{static_cast<double>(i), 0, 0});
    auto result = decimateForPreview(points, 10);
    ASSERT_EQ(result.size(), 10u);
    for (std::size_t i = 1; i < result.size(); ++i) {
        EXPECT_LT(result[i - 1].x, result[i].x) << "decimated points must stay in original order";
    }
    // 첫 점은 원본의 시작 근방, 마지막 점은 끝 근방이어야 한다(전체 범위 커버).
    EXPECT_LT(result.front().x, 100.0);
    EXPECT_GT(result.back().x, 900.0);
}

TEST(DecimationTest, EmptyInputReturnsEmpty) {
    std::vector<Vec3> points;
    EXPECT_TRUE(decimateForPreview(points, 100).empty());
}
```

- [ ] **Step 5: `src/maro_lidar/CMakeLists.txt`/`tests/CMakeLists.txt`에 등록**

`src/maro_lidar/CMakeLists.txt`의 `add_library(maro_lidar STATIC ...)` 목록에 `src/Decimation.cpp`를 `src/RayPattern.cpp` 다음에 추가한다.

`tests/CMakeLists.txt`의 `add_executable(maro_lidar_tests ...)` 목록에 `lidar/test_decimation.cpp`를 추가한다.

- [ ] **Step 6: `MaroPump.cpp`에 라이브 갱신 배선**

`#include "maro_lidar/Decimation.h"`을 추가하고, 익명 네임스페이스에 프리뷰 상한 상수를 추가한다:
```cpp
constexpr std::size_t kMaxPreviewPoints = 4096;
```

`collectLidarScans()`에서, `state.hasScanned = true;` 다음(그리고 기존의 `if (!points.empty()) { ... runtime.lidarQueue().push(...) ... }` 블록 **앞 또는 뒤 어느 쪽이든, points가 아직 move되지 않은 시점**)에 추가한다 — `points`가 `std::move`로 큐에 들어가기 **전에** 라이브 프리뷰 갱신을 먼저 해야 한다(그렇지 않으면 프리뷰가 빈 벡터를 읽는다):

```cpp
        if (lidarFn.findPlug(MaroLidarNode::aVisualize, false).asBool()) {
            MPlug messagePlug = lidarFn.findPlug("message", false);
            MPlugArray destinations;
            messagePlug.connectedTo(destinations, false, true);
            for (unsigned int i = 0; i < destinations.length(); ++i) {
                if (destinations[i].attribute() != MaroPointCloudNode::aSourceLidar) continue;
                MFnDependencyNode pointCloudFn(destinations[i].node());
                if (pointCloudFn.typeId() != MaroPointCloudNode::id) continue;

                const auto preview = maro::lidar::decimateForPreview(points, kMaxPreviewPoints);
                MPointArray mayaPoints;
                mayaPoints.setLength(static_cast<unsigned int>(preview.size()));
                for (unsigned int j = 0; j < mayaPoints.length(); ++j) {
                    mayaPoints[j] = MPoint(preview[j].x, preview[j].y, preview[j].z, 1.0);
                }
                MFnPointArrayData pointArrayDataFn;
                MObject pointsData = pointArrayDataFn.create(mayaPoints);
                // 전역 제약: cmds/MDGModifier를 거치지 않는 raw plug write --
                // 이 틱마다 도는 코드가 undo 큐를 도배하면 안 된다(Phase 3
                // idle-loop 교훈과 같은 이유).
                MPlug pointsPlug = pointCloudFn.findPlug(MaroPointCloudNode::aPoints, false);
                pointsPlug.setValue(pointsData);
                break;
            }
        }

        if (!points.empty()) {
            LidarSample sample;
            sample.unit = unit;
            sample.points = std::move(points);
            runtime.lidarQueue().push(std::move(sample));
        }
```

`#include "MaroPointCloudNode.h"`와 `#include <maya/MFnPointArrayData.h>`를 `MaroPump.cpp`의 include 목록에 추가한다.

- [ ] **Step 7: `maroLidarPanel.py`에 "라이브 프리뷰" 체크박스 추가**

`_ATTRS` 목록에 `("enabled", "Enabled", "bool")` 다음 줄로 추가:
```python
    ("visualize", "Live preview", "bool"),
]
```
(`_loadValues()`/`_onApply()`는 이미 `_ATTRS`를 순회하므로 코드 변경이 필요 없다 — 목록에 항목을 추가하는 것만으로 폼에 필드가 생기고 적용/로드가 자동으로 그 필드를 포함한다.)

- [ ] **Step 8: 빌드 + 전체 테스트**

전역 제약의 빌드+테스트 절차를 실행한다. `maro_lidar_tests`(GoogleTest, 새 `DecimationTest` 4건 포함)와 mayapy 스위트 전체가 그린인지 확인한다.

- [ ] **Step 9: 수동 체크리스트에 `### 6-3` 절 추가**

`docs/maro-main-ui-manual-checklist.md`의 `### 6-2` 다음에 추가:

```markdown
### 6-3. 라이브 프리뷰 (Task 5) — **[필수 · go/no-go]**

1. LiDAR 설정 팝업에서 "Live preview" 체크박스를 켜고 "적용".
2. 씬에서 타겟 메쉬를 이동시킨다(예: `translateX`를 애니메이션 재생 없이
   드래그로 계속 바꿔 본다). **[필수]** ROS 뷰포트의 포인트클라우드가
   메쉬를 따라 실시간으로 갱신되는가(수동 "Scan now" 클릭 없이).
3. Script Editor를 열어 둔 채 1-2번을 반복 — **[필수]** `undo` 히스토리가
   매 틱 쌓이지 않는가(`cmds.undoInfo(query=True, undoQueueEmpty=True)`가
   계속 갱신되는 동안에도 사용자가 켠 마지막 실제 undo 지점 이후로 늘지
   않아야 한다 -- 라이브 프리뷰가 undo 큐를 도배하면 이 검사가 실패한다).
4. `verticalSamples`/`horizontalSamples`를 스펙급으로 크게 올려(예:
   64 x 2048, 단 `kMaxRaysPerScan` 상한 65536 이내로) 라이브 프리뷰를 켠
   채로 몇 초 관찰 — **[필수]** Maya UI가 멈추지 않고(디시메이션이
   실제로 포인트 수를 줄이고 있다는 증거), 뷰포트 프레임레이트가 크게
   떨어지지 않는가.
5. **[필수 · 이 태스크의 진짜 기준]** 라이브 프리뷰가 켜진 채(포인트클라우드가
   실제로 갱신되고 있는 상태) `cmds.unloadPlugin("maro")`를 실행한다. Maya가
   죽지 않는가 -- 렌더러가 소유한 오브젝트가 언로드 시점에 살아있는 상태라
   기존 언로드 테스트보다 위험도가 높다.
```

---

### Task 6: Tech Diag 센서 검증 후속 (LiDAR 타겟메쉬/레이수 검사)

**Files:**
- Modify: `python/maroTechDiag.py`
- Modify: `tests/maya/test_tech_diag.py`

**Interfaces:**
- Consumes: `cmds.ls(type="maroLidar")`, `MaroLidarNode`의 `enabled`/`verticalSamples`/`horizontalSamples`/`targetMeshes` 어트리뷰트.
- Produces: `maroTechDiag.checkLidarTargetMeshes(lidarRows)`, `maroTechDiag.checkLidarRayCount(lidarRows)`, `maroTechDiag.LIDAR_MAX_RAYS_PER_SCAN`(파이썬 쪽 독립 선언, C++ `kMaxRaysPerScan`과 값이 반드시 일치해야 함 — 이 프로젝트가 `AXIS_FIELDS`에 이미 쓰는 관례).

이 두 검사는 LiDAR가 UI에 노출된 뒤(Task 4)에야 의미가 있다 — Tech Diag 설계 스펙 §8이 "센서 검증은 이번 범위 밖"이라 명시했던 이유(그때는 LiDAR UI가 없었다)가 이제 해소됐다.

- [ ] **Step 1: `maroTechDiag.py`에 상수 + 순수 검사 함수 추가**

모듈 상단, `LIMIT_PROXIMITY_THRESHOLD = 0.9` 다음에 추가:
```python
# MaroPump.cpp/MaroLidarScan.h의 kMaxRaysPerScan과 반드시 같은 값이어야
# 한다 -- 이 프로젝트가 Python/C++ 경계에서 상수를 공유하는 기존 관례
# (AXIS_FIELDS/CAPABILITY_FIELDS)와 같은 이유로 여기서도 독립적으로
# 선언한다(순환 임포트가 없는 게 아니라,애초에 Python이 C++ 상수를 직접
# 참조할 방법이 없다).
LIDAR_MAX_RAYS_PER_SCAN = 65536
```

`checkMeshCollisions` 함수 다음(파일에서 `_MAX_ANCESTOR_CHAIN_DEPTH` 앞)에 추가:

```python
def checkLidarTargetMeshes(lidarRows):
    """enabled인 maroLidar가 targetMeshes를 하나도 갖고 있지 않으면 경고.

    Maya를 부르지 않는 순수 함수다(lidarRows에 이미 들어 있는 필드만 본다)."""
    findings = []
    for row in lidarRows:
        if not row["enabled"]:
            continue
        if row["targetMeshCount"] == 0:
            findings.append({
                "category": "lidarNoTargetMesh",
                "severity": "warning",
                "summary": "{}: enabled but has no target mesh connected".format(
                    row["lidarFullPath"]),
                "axis": None,
                "remedy": None,
            })
    return findings


def checkLidarRayCount(lidarRows):
    """verticalSamples x horizontalSamples가 LIDAR_MAX_RAYS_PER_SCAN을
    넘는 설정을 찾는다 -- 그 스캔은 레이캐스팅 자체가 매 틱 조용히 거부된다
    (MaroPump.cpp의 RayCountTooLarge 경고와 같은 조건)."""
    findings = []
    for row in lidarRows:
        rayCount = row["verticalSamples"] * row["horizontalSamples"]
        if rayCount > LIDAR_MAX_RAYS_PER_SCAN:
            findings.append({
                "category": "lidarRayCountExceeded",
                "severity": "warning",
                "summary": (
                    "{}: verticalSamples({}) x horizontalSamples({}) = {} exceeds "
                    "the per-scan cap of {}".format(
                        row["lidarFullPath"], row["verticalSamples"],
                        row["horizontalSamples"], rayCount, LIDAR_MAX_RAYS_PER_SCAN)),
                "axis": None,
                "remedy": None,
            })
    return findings
```

- [ ] **Step 2: Maya 조회 글루 추가 + `_runMayaSideChecks()`에 연결**

`_runMayaSideChecks()` 함수 **앞**에 새 헬퍼를 추가한다:

```python
def _collectLidarRows():
    """씬의 모든 maroLidar를 checkLidarTargetMeshes/checkLidarRayCount가
    필요로 하는 좁은 필드로 조회한다. targetMeshCount는 evaluateNumElements가
    아니라 listConnections로 실제 연결 개수를 센다 -- 빈 논리 인덱스를
    materialize하는 함정(MaroLidarScan.cpp의 firstConnectedMesh 도크스트링과
    같은 함정)을 cmds 쪽에서는 elementByLogicalIndex를 직접 안 써서 피한다."""
    rows = []
    for lidar in cmds.ls(type="maroLidar", long=True) or []:
        connectedMeshes = cmds.listConnections(
            lidar + ".targetMeshes", source=True, destination=False) or []
        rows.append({
            "lidarFullPath": lidar,
            "enabled": bool(cmds.getAttr(lidar + ".enabled")),
            "verticalSamples": cmds.getAttr(lidar + ".verticalSamples"),
            "horizontalSamples": cmds.getAttr(lidar + ".horizontalSamples"),
            "targetMeshCount": len(connectedMeshes),
        })
    return rows
```

`_runMayaSideChecks()`의 `return findings` 바로 앞 줄을 다음으로 바꾼다(기존 `return findings`를 대체):
```python
    lidarRows = _collectLidarRows()
    findings += checkLidarTargetMeshes(lidarRows)
    findings += checkLidarRayCount(lidarRows)
    return findings
```

- [ ] **Step 3: `tests/maya/test_tech_diag.py`에 회귀 테스트 추가**

기존 파일의 순수 함수 검증 구역(파일 앞쪽, `maya.standalone` 부트스트랩 이전 섹션)에 다음을 추가한다 — 정확한 삽입 위치는 기존 `checkMeshCollisions`류 테스트 바로 다음:

```python
# --- checkLidarTargetMeshes / checkLidarRayCount (순수 함수) --------------

noTargetRows = [{"lidarFullPath": "|lidar1", "enabled": True, "verticalSamples": 4,
                 "horizontalSamples": 4, "targetMeshCount": 0}]
findings = maroTechDiag.checkLidarTargetMeshes(noTargetRows)
assert len(findings) == 1 and findings[0]["category"] == "lidarNoTargetMesh"
print("checkLidarTargetMeshes flags an enabled lidar with no target OK")

disabledNoTargetRows = [{"lidarFullPath": "|lidar1", "enabled": False, "verticalSamples": 4,
                         "horizontalSamples": 4, "targetMeshCount": 0}]
assert maroTechDiag.checkLidarTargetMeshes(disabledNoTargetRows) == []
print("checkLidarTargetMeshes ignores a disabled lidar OK")

hasTargetRows = [{"lidarFullPath": "|lidar1", "enabled": True, "verticalSamples": 4,
                  "horizontalSamples": 4, "targetMeshCount": 1}]
assert maroTechDiag.checkLidarTargetMeshes(hasTargetRows) == []
print("checkLidarTargetMeshes passes a lidar with a target OK")

overCapRows = [{"lidarFullPath": "|lidar1", "enabled": True, "verticalSamples": 300,
                "horizontalSamples": 300, "targetMeshCount": 1}]
findings = maroTechDiag.checkLidarRayCount(overCapRows)
assert len(findings) == 1 and findings[0]["category"] == "lidarRayCountExceeded"
print("checkLidarRayCount flags an over-cap configuration OK")

underCapRows = [{"lidarFullPath": "|lidar1", "enabled": True, "verticalSamples": 4,
                 "horizontalSamples": 36, "targetMeshCount": 1}]
assert maroTechDiag.checkLidarRayCount(underCapRows) == []
print("checkLidarRayCount passes a default-scale configuration OK")
```

파일의 `maya.standalone`/플러그인 로드 이후 섹션(Maya 의존 부분)에는 다음을 추가한다:

```python
# --- _collectLidarRows()/(_runMayaSideChecks 경유) 통합 확인 --------------

lidar = cmds.createNode("maroLidar")
lidar = cmds.ls(lidar, long=True)[0]
cmds.setAttr(lidar + ".enabled", True)
cmds.setAttr(lidar + ".verticalSamples", 300)
cmds.setAttr(lidar + ".horizontalSamples", 300)
# targetMeshes를 일부러 비워 둔다 -- 두 검사 모두 걸려야 한다.

mayaFindings = maroTechDiag._runMayaSideChecks()
categories = {f["category"] for f in mayaFindings}
assert "lidarNoTargetMesh" in categories, categories
assert "lidarRayCountExceeded" in categories, categories
print("_runMayaSideChecks surfaces both new lidar findings OK")
```

- [ ] **Step 4: 빌드 + 전체 테스트**

전역 제약의 빌드+테스트 절차를 실행한다. `maya_tech_diag`를 포함해 전체 스위트가 그린인지 확인한다.

---

## 이 계획이 끝난 뒤

전 태스크 완료 후 최종 전체 브랜치 리뷰(`superpowers:requesting-code-review`의 `code-reviewer.md`, 가장 강력한 모델)를 거친 뒤 `superpowers:finishing-a-development-branch`로 마무리한다 — 이 세션이 이미 두 번 완주한 것과 같은 절차. 특히 다음을 리뷰어에게 명시적으로 주목시킨다:
- Task 1/4/5의 언로드 순서(드로우 오버라이드 dereg → 노드 dereg)가 실제 코드에서 지켜졌는지.
- Task 3의 `MDGModifier` API(`newPlugValue` 계열)가 구현자가 실제로 확인한 정확한 오버로드로 쓰였는지(Step 2의 주의사항 참고).
- Task 4의 undo 청크(`cmds.undoInfo`)가 실패 경로에서도 항상 닫히는지, 고아 노드 정리가 완전한지.
- Task 5의 라이브 프리뷰가 정말 `cmds`/`MDGModifier`를 거치지 않는 raw plug write인지(전역 제약 위반은 Critical).
