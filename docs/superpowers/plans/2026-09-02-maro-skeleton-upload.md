# Maro 스켈레톤 업로드/추출 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** "Maro" 메뉴에 "Skeleton Upload..." 항목을 추가해, 메쉬 오브젝트(임포트했거나 이미 씬에 있는)에서 skinCluster 인플루언스 조인트를 찾아 선택하거나, 없으면 바운딩박스 중심에 루트 조인트 1개를 만들어 선택하는 기능을 만든다.

**Architecture:** 순수 Python 모듈 하나(`python/maroSkeletonUpload.py`)로 구성한다. 핵심 로직(조인트 찾기/만들기, 선택 검증, 임포트 결과에서 메쉬 찾기)은 Maya 커맨드만 쓰는 순수 함수로 만들어 mayapy 배치로 완전히 테스트하고, 그 위에 SONE/`maroLidarPanel`과 같은 패턴의 독립 QDialog를 얹는다. 새 커스텀 노드 타입이나 C++ 코드는 전혀 필요 없다.

**Tech Stack:** Python 3, PySide6(Qt), `maya.cmds`, `maya.api.OpenMaya`(`MSceneMessage`), `maya.mel`.

## Global Constraints

- 새 C++ 코드/커맨드/노드 타입을 추가하지 않는다 — 표준 Maya 커맨드(`cmds.listHistory`/`cmds.skinCluster`/`cmds.createNode`/`cmds.exactWorldBoundingBox`/`cmds.select`)와 `maya.api.OpenMaya.MSceneMessage`만 쓴다.
- MaroUI의 기존 레이아웃(듀얼 뷰포트, Tech Diag 사이드패널, ONE 그리드)을 건드리지 않는다 — 이 기능은 별도 최상위 다이얼로그다.
- `kAfterImport` 콜백은 다이얼로그가 열려 있는 동안만 살아 있어야 하고, 닫히면(`closeEvent`) 즉시 해제해야 한다. 플러그인이 언로드될 때(다이얼로그가 안 닫힌 채로도) 반드시 정리돼야 한다 — 이 프로젝트가 반복해서 잡아 온 "주인 없는 콜백" 결함 유형과 같은 카테고리다.
- 새 Qt 위젯은 `setStyleSheet()`를 호출하지 않고, 모든 이벤트 핸들러/콜백이 예외를 삼킨다(Maya 콜백 경계를 예외가 넘으면 안 된다는 이 코드베이스의 전역 규율).
- 조인트 생성은 `cmds.joint()`(대화형 Joint Tool 커맨드, 현재 선택된 조인트가 있으면 그 자식으로 체인을 이어 버리는 부작용이 있다)가 아니라 `cmds.createNode("joint")`를 쓴다 — 이 코드베이스의 다른 모든 노드 생성이 `createNode`를 쓰는 것과 같은 이유이자, 그 체이닝 부작용을 원천적으로 피하기 위해서다.
- 각 태스크 완료 후 다음 절차를 실행한다:
  ```powershell
  cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
      if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
  }
  cmake --build out/build --config Release
  ctest --test-dir out/build -C Release --output-on-failure
  ```
  전체(필터 없는) 스위트를 항상 돌린다 — 이 프로젝트에서 필터링된 서브셋만 돌려 검증 공백이 생긴 전례가 있다.
- Task 2의 Qt 다이얼로그/파일 임포트/실제 드래그&드롭 동작은 mayapy 배치로 검증할 수 없다 — `docs/maro-main-ui-manual-checklist.md`에 새 절을 추가해 대화형 Maya에서 go/no-go로 검증한다. Task 1의 순수 함수(`extractSkeleton`/`_isSingleMeshSelected`/`_findMeshInAssemblies`)는 mayapy 배치로 완전히 테스트 가능하다.

---

### Task 1: 스켈레톤 추출 핵심 로직 (순수 함수, Qt 없음)

**Files:**
- Create: `python/maroSkeletonUpload.py`
- Modify: `src/maro_plugin/CMakeLists.txt`
- Test: `tests/maya/test_skeleton_upload.py`
- Modify: `tests/CMakeLists.txt`

**Interfaces:**
- Produces: `maroSkeletonUpload.extractSkeleton(mesh) -> list[str] | None`, `maroSkeletonUpload._isSingleMeshSelected(selection) -> bool`, `maroSkeletonUpload._findMeshInAssemblies(assemblies) -> str | None`. Task 2가 이 세 함수를 그대로 가져다 Qt 다이얼로그의 버튼 핸들러/콜백에서 부른다.

- [ ] **Step 1: `python/maroSkeletonUpload.py` 작성**

```python
"""스켈레톤 업로드/추출 -- 로드맵 Phase 6(설계 스펙
docs/superpowers/specs/2026-09-02-maro-skeleton-upload-design.md).

순수 Python + 표준 Maya 커맨드로만 구성된다 -- 새 커스텀 노드 타입도, 새
C++ 코드도 필요 없다. skinCluster가 있으면 그 인플루언스 조인트를 찾아
선택해 주고, 없으면 바운딩박스 중심에 루트 조인트 1개를 만든다. 이 기능은
거기까지만 책임진다 -- 만들어진/찾아진 조인트에 maroAxis를 부여하는 것은
여전히 사용자가 각 조인트를 우클릭해 기존 "Maro node editor" 마킹메뉴로
하나씩 한다(자동 리깅 아님).

이 파일의 함수들(extractSkeleton/_isSingleMeshSelected/
_findMeshInAssemblies)은 Maya 커맨드만 쓰는 순수 함수라 mayapy 배치 모드에서
QWidget 없이 계약을 검증할 수 있다. Qt 다이얼로그는 이 파일에 나중에(Task 2)
추가된다 -- maroTechDiag.py와 같은 관례로, 모듈 자체는 PySide6를 import해도
안전하지만(위젯을 실제로 만들지 않는 한) 이 태스크는 아직 위젯을 만들지
않는다.
"""
import maya.cmds as cmds


def extractSkeleton(mesh):
    """mesh(메쉬 셰이프를 가진 오브젝트 하나, 풀 경로 권장)에서 스켈레톤을
    찾거나 만든다.

    skinCluster가 있으면 그 인플루언스 조인트를 그대로 cmds.select()하고
    그 목록을 돌려준다 -- 새 노드는 전혀 만들지 않는다. skinCluster는
    있지만 인플루언스가 하나도 없는 퇴화 상태면 경고만 내고 None을
    돌려준다(아래로 조용히 폴백하지 않는다 -- 그러면 깨진 skinCluster를
    "스킨 없음"으로 오판해 엉뚱한 루트 조인트를 만들게 된다). skinCluster가
    아예 없으면 mesh의 월드 바운딩박스 중심에 새 joint 노드 1개를 만들어
    mesh의 자식으로 붙이고 선택한다.

    호출자가 mesh를 실제 메쉬 셰이프를 가진 단일 오브젝트로 이미 검증했다고
    가정한다 -- 이 함수 자체는 그 검증을 하지 않는다(호출부 두 곳이 각자
    다른 방식으로 후보를 좁히므로 검증 지점을 여기 하나로 모으지 않는다.
    _isSingleMeshSelected/_findMeshInAssemblies 참고).
    """
    skinClusters = cmds.ls(cmds.listHistory(mesh) or [], type="skinCluster")
    if skinClusters:
        influences = cmds.skinCluster(skinClusters[0], query=True, influence=True) or []
        if not influences:
            cmds.warning(
                "Maro: '{}' has a skinCluster ('{}') but it has no influence "
                "joints -- not falling back to a generated root joint, since "
                "that would hide a broken skinCluster.".format(mesh, skinClusters[0]))
            return None
        cmds.select(influences, replace=True)
        return influences

    bbox = cmds.exactWorldBoundingBox(mesh)
    center = ((bbox[0] + bbox[3]) / 2.0, (bbox[1] + bbox[4]) / 2.0,
              (bbox[2] + bbox[5]) / 2.0)
    shortName = mesh.split("|")[-1]
    # cmds.joint()가 아니라 cmds.createNode("joint")를 쓴다 -- cmds.joint()는
    # 대화형 Joint Tool 커맨드라 현재 선택된 조인트가 있으면 그 자식으로
    # 체인을 이어 버린다(전역 제약 참고). createNode는 그런 부작용 없이
    # 항상 독립된 새 조인트를 만든다.
    rootJoint = cmds.createNode("joint", name=shortName + "_root")
    cmds.parent(rootJoint, mesh)
    rootJointFullPath = cmds.ls(rootJoint, long=True)[0]
    cmds.xform(rootJointFullPath, worldSpace=True, translation=center)
    cmds.select(rootJointFullPath, replace=True)
    return [rootJointFullPath]


def _isSingleMeshSelected(selection):
    """selection(예: cmds.ls(selection=True, long=True)의 결과)이 메쉬
    셰이프를 가진 오브젝트 정확히 하나인가."""
    if len(selection) != 1:
        return False
    return bool(cmds.listRelatives(selection[0], shapes=True, type="mesh"))


def _findMeshInAssemblies(assemblies):
    """assemblies(최상위 오브젝트 이름 목록, 예: 임포트 직후 새로 생긴
    것들) 전체 서브트리에서 처음 발견되는 메쉬 셰이프의 부모 트랜스폼(풀
    경로). 메쉬가 하나도 없으면 None."""
    if not assemblies:
        return None
    meshShapes = cmds.listRelatives(
        assemblies, allDescendents=True, fullPath=True, type="mesh") or []
    if not meshShapes:
        return None
    return cmds.listRelatives(meshShapes[0], parent=True, fullPath=True)[0]
```

- [ ] **Step 2: `src/maro_plugin/CMakeLists.txt`에 새 Python 모듈 등록**

`MARO_PLUGIN_PY_MODULES` 목록에 `maroRosProxy`와 `maroSingleObjectNodeEditor`
사이(알파벳 순서)에 `maroSkeletonUpload`를 추가한다:
```cmake
set(MARO_PLUGIN_PY_MODULES
    maroDagMenu
    maroDiagPanel
    maroLidarPanel
    maroMainWindow
    maroMenu
    maroObjectNodeEditor
    maroRosProxy
    maroSkeletonUpload
    maroSingleObjectNodeEditor
    maroTechDiag
)
```

- [ ] **Step 3: mayapy 배치 테스트 작성 — `tests/maya/test_skeleton_upload.py`**

```python
"""maroSkeletonUpload의 순수 함수(extractSkeleton/_isSingleMeshSelected/
_findMeshInAssemblies)를 배치 모드에서 검증한다. 이 파일이 만드는 것은 전부
표준 Maya 노드(mesh/joint/skinCluster)뿐이라 Qt를 전혀 건드리지 않는다 --
그래서 이 태스크 전체가 mayapy 배치로 완전히 테스트 가능하다."""
import os

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
pluginDir = os.path.dirname(plugin)

stagedModule = os.path.join(pluginDir, "maroSkeletonUpload.py")
assert os.path.isfile(stagedModule), (
    f"maroSkeletonUpload.py must be staged next to the plug-in, not found at {stagedModule}"
)
print("module staged next to the plug-in OK")

cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

import maroSkeletonUpload  # noqa: E402  (플러그인 디렉터리가 sys.path에 들어간 뒤)

# --- extractSkeleton: skinCluster 있음, 인플루언스 정상 -------------------
mesh, _ = cmds.polyCube(name="skinnedCube")
joint1 = cmds.createNode("joint", name="rootJoint")
joint2 = cmds.createNode("joint", name="childJoint", parent=joint1)
cmds.setAttr(joint2 + ".translateY", 2.0)
scNode = cmds.skinCluster(joint1, joint2, mesh)[0]

result = maroSkeletonUpload.extractSkeleton(mesh)
assert result is not None
resultShort = sorted(r.split("|")[-1] for r in result)
assert resultShort == ["childJoint", "rootJoint"], (
    f"expected both influence joints, got {resultShort}")
selected = set(cmds.ls(selection=True, long=True))
assert set(result) == selected, (
    f"extractSkeleton must select exactly the influence joints, "
    f"expected {set(result)}, got selection={selected}")
newNodeCount = len(cmds.ls(type="joint"))
assert newNodeCount == 2, (
    f"extractSkeleton must not create new joints when a skinCluster exists, "
    f"found {newNodeCount} joints")
print("skinCluster with influences: found+selected existing joints, no new nodes OK")

# --- extractSkeleton: skinCluster 있음, 인플루언스 0개(퇴화) --------------
cmds.skinCluster(scNode, edit=True, removeInfluence=[joint1, joint2])
degenerateResult = maroSkeletonUpload.extractSkeleton(mesh)
assert degenerateResult is None, (
    "a skinCluster with zero influences must not fall back to a generated "
    f"root joint, got {degenerateResult}")
assert len(cmds.ls(type="joint")) == 2, (
    "the degenerate-skinCluster case must not create a new joint either")
print("skinCluster with zero influences: returns None, no fallback OK")

# --- extractSkeleton: skinCluster 없음 -> 루트 조인트 생성 ----------------
cmds.file(new=True, force=True)
plainMesh, _ = cmds.polyCube(name="plainCube")
cmds.setAttr(plainMesh + ".translate", 10, 3, -2, type="double3")

noSkinResult = maroSkeletonUpload.extractSkeleton(plainMesh)
assert noSkinResult is not None and len(noSkinResult) == 1
newJoint = noSkinResult[0]
assert cmds.objectType(newJoint) == "joint"
assert newJoint.split("|")[-1] == "plainCube_root"
parents = cmds.listRelatives(newJoint, parent=True, fullPath=True) or []
assert parents and parents[0] == cmds.ls(plainMesh, long=True)[0], (
    "the generated root joint must be parented under the mesh")
bbox = cmds.exactWorldBoundingBox(plainMesh)
expectedCenter = ((bbox[0] + bbox[3]) / 2.0, (bbox[1] + bbox[4]) / 2.0,
                   (bbox[2] + bbox[5]) / 2.0)
actualPos = cmds.xform(newJoint, query=True, worldSpace=True, translation=True)
for actual, expected in zip(actualPos, expectedCenter):
    assert abs(actual - expected) < 1e-6, (
        f"root joint position {actualPos} does not match bbox center {expectedCenter}")
assert cmds.ls(selection=True, long=True) == [newJoint]
print("no skinCluster: creates one root joint at bbox center, parented, selected OK")

# 재클릭(동일 함수 재호출)해도 같은 방식으로 새 조인트를 또 만든다 -- 이
# 함수 자체는 "이미 만들어졌는지" 기억하지 않는다(그 판단은 이번 범위 밖,
# 다이얼로그 쪽에도 그런 로직이 없다 -- 사용자가 매번 명시적으로 실행하는
# 액션이다). Maya가 이름을 자동으로 고유화하는지만 확인한다.
secondResult = maroSkeletonUpload.extractSkeleton(plainMesh)
assert secondResult[0] != newJoint, "Maya must uniquify the duplicate joint name"
print("re-running on the same mesh creates a second, uniquely-named joint OK")

# --- _isSingleMeshSelected -------------------------------------------------
assert maroSkeletonUpload._isSingleMeshSelected([cmds.ls(plainMesh, long=True)[0]]) is True
assert maroSkeletonUpload._isSingleMeshSelected([]) is False
assert maroSkeletonUpload._isSingleMeshSelected(
    [cmds.ls(plainMesh, long=True)[0], newJoint]) is False
assert maroSkeletonUpload._isSingleMeshSelected([newJoint]) is False, (
    "a lone joint (no mesh shape) must not count as a single mesh selection")
print("_isSingleMeshSelected true/false cases OK")

# --- _findMeshInAssemblies --------------------------------------------------
cmds.file(new=True, force=True)
group = cmds.group(empty=True, name="importedGroup")
nestedMesh, _ = cmds.polyCube(name="nestedMesh")
cmds.parent(nestedMesh, group)
found = maroSkeletonUpload._findMeshInAssemblies([group])
assert found == cmds.ls(nestedMesh, long=True)[0], (
    f"expected to find the nested mesh transform, got {found}")

emptyGroup = cmds.group(empty=True, name="emptyGroup")
notFound = maroSkeletonUpload._findMeshInAssemblies([emptyGroup])
assert notFound is None, f"expected None for a mesh-free subtree, got {notFound}"

assert maroSkeletonUpload._findMeshInAssemblies([]) is None
print("_findMeshInAssemblies found/not-found/empty cases OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")

import sys  # noqa: E402
sys.exit(0)
```

- [ ] **Step 4: `tests/CMakeLists.txt`에 등록**

`foreach(maya_test load axis_node binding ...)` 목록에 `tech_diag point_cloud_node
lidar_commands lidar_menu` 바로 다음에 `skeleton_upload`를 추가한다:
```cmake
    foreach(maya_test load axis_node binding capability_stack delete_rules
                      robustness diag_boad diag_onfix diag_book
                      diag_book_cross_session diag_remedy
                      diag_degraded diag_degraded_remedy diag_thread
                      panel_commands main_window main_menu journal remedy_capture
                      remedy_availability remedy_ambiguous_names
                      main_thread_queue remedy_apply sentinel lidar_node
                      ros_proxy_commands ros_proxy_sync axis_editor_commands
                      dag_menu tech_diag point_cloud_node lidar_commands
                      lidar_menu skeleton_upload)
```

- [ ] **Step 5: 빌드 + 전체 테스트**

전역 제약의 빌드+테스트 절차를 그대로 실행한다. `maya_skeleton_upload`가
통과하고 나머지 기존 테스트가 모두 그린인지 확인한다.

---

### Task 2: 다이얼로그 + 메뉴 진입점 + 임포트 콜백

**Files:**
- Modify: `python/maroSkeletonUpload.py`
- Modify: `python/maroMenu.py`
- Modify: `python/maroMainWindow.py`
- Modify: `docs/maro-main-ui-manual-checklist.md`

**Interfaces:**
- Consumes: Task 1의 `extractSkeleton`/`_isSingleMeshSelected`/`_findMeshInAssemblies`.
- Produces: `maroSkeletonUpload.show()`(다이얼로그를 열거나 이미 열려 있으면 앞으로 가져옴), `maroSkeletonUpload.stop()`(플러그인 언로드/창 닫힘 시 다이얼로그를 닫고 콜백을 해제).

- [ ] **Step 1: `python/maroSkeletonUpload.py`에 다이얼로그 추가**

파일 맨 위 import 블록을 다음으로 바꾼다(기존 `import maya.cmds as cmds` 다음에 추가):
```python
import maya.api.OpenMaya as om2
import maya.cmds as cmds
import maya.mel as mel
from PySide6 import QtCore, QtWidgets
```

파일 끝에 다음을 추가한다:

```python
_OPEN_DIALOG = None


def show():
    """"Maro" 메뉴의 "Skeleton Upload..." 항목이 부른다. 이미 열려 있으면
    그 창을 앞으로 가져온다."""
    global _OPEN_DIALOG
    if _OPEN_DIALOG is not None:
        try:
            _OPEN_DIALOG.raise_()
            _OPEN_DIALOG.activateWindow()
            return _OPEN_DIALOG
        except RuntimeError:
            _OPEN_DIALOG = None

    _OPEN_DIALOG = SkeletonUploadDialog()
    _OPEN_DIALOG.show()
    return _OPEN_DIALOG


def stop():
    """플러그인 언로드/창 닫힘 시 열려 있는 다이얼로그를 닫는다. 다이얼로그의
    closeEvent가 등록돼 있던 kAfterImport 콜백을 먼저 해제한다."""
    global _OPEN_DIALOG
    if _OPEN_DIALOG is None:
        return
    try:
        _OPEN_DIALOG.close()
        _OPEN_DIALOG.deleteLater()
    except Exception:  # noqa: BLE001 -- 언로드 정리 경계
        import traceback
        traceback.print_exc()
    _OPEN_DIALOG = None


class SkeletonUploadDialog(QtWidgets.QWidget):
    """"파일에서 임포트"/"현재 선택에서 추출" 버튼 두 개짜리 독립 최상위
    창. setStyleSheet()를 부르지 않는다."""

    def __init__(self, parent=None):
        super().__init__(parent, QtCore.Qt.Window)
        self.setWindowTitle("Skeleton Upload")
        self._callbackId = None
        self._beforeAssemblies = None

        layout = QtWidgets.QVBoxLayout(self)
        importButton = QtWidgets.QPushButton("파일에서 임포트")
        importButton.clicked.connect(self._onImportClicked)
        layout.addWidget(importButton)
        extractButton = QtWidgets.QPushButton("현재 선택에서 추출")
        extractButton.clicked.connect(self._onExtractFromSelectionClicked)
        layout.addWidget(extractButton)
        self._statusLabel = QtWidgets.QLabel("")
        layout.addWidget(self._statusLabel)

    def closeEvent(self, event):
        try:
            self._removeImportCallback()
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
            import traceback
            traceback.print_exc()
        super().closeEvent(event)

    def _removeImportCallback(self):
        if self._callbackId is not None:
            om2.MMessage.removeCallback(self._callbackId)
            self._callbackId = None

    def _onImportClicked(self):
        try:
            self._beforeAssemblies = set(cmds.ls(assemblies=True) or [])
            # 이전에 임포트를 취소해 콜백이 여전히 걸려 있을 수 있다 --
            # 중복 등록을 피한다.
            self._removeImportCallback()
            self._callbackId = om2.MSceneMessage.addCallback(
                om2.MSceneMessage.kAfterImport, self._onAfterImport)
            mel.eval('FileImport')
        except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
            self._statusLabel.setText("임포트 시작 실패: {}".format(exc))

    def _onAfterImport(self, clientData=None):
        # Maya 콜백 경계 -- 예외를 밖으로 내보내면 안 된다.
        try:
            self._removeImportCallback()
            afterAssemblies = set(cmds.ls(assemblies=True) or [])
            newAssemblies = list(afterAssemblies - (self._beforeAssemblies or set()))
            if not newAssemblies:
                self._statusLabel.setText("임포트된 새 오브젝트를 찾지 못했습니다.")
                return
            mesh = _findMeshInAssemblies(newAssemblies)
            if mesh is None:
                self._statusLabel.setText("임포트한 파일에 메쉬가 없습니다.")
                return
            self._runExtraction(mesh)
        except Exception:  # noqa: BLE001 -- Maya 콜백 경계
            import traceback
            traceback.print_exc()

    def _onExtractFromSelectionClicked(self):
        try:
            selection = cmds.ls(selection=True, long=True) or []
            if not _isSingleMeshSelected(selection):
                self._statusLabel.setText("정확히 메쉬 하나를 선택하세요.")
                return
            self._runExtraction(selection[0])
        except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
            self._statusLabel.setText("추출 실패: {}".format(exc))

    def _runExtraction(self, mesh):
        result = extractSkeleton(mesh)
        if result is None:
            self._statusLabel.setText("추출 실패 -- 스크립트 에디터 참조")
            return
        self._statusLabel.setText("{}개 조인트 선택됨: {}".format(
            len(result), ", ".join(r.split("|")[-1] for r in result)))
```

- [ ] **Step 2: `python/maroMenu.py`에 메뉴 항목 추가**

`build()` 함수의 다음 부분:
```python
    cmds.menuItem(label="Maro 창 열기",
                  command="import maya.cmds as cmds\ncmds.maroMainWindow()",
                  parent=MENU_NAME)
    cmds.menuItem(divider=True, parent=MENU_NAME)
    cmds.menuItem(label="ROS 연결 설정 (준비 중)", enable=False, parent=MENU_NAME)
    cmds.menuItem(label="환경설정 (준비 중)", enable=False, parent=MENU_NAME)
```
를 다음으로 바꾼다(새 항목과 구분용 divider 하나만 끼워 넣는다, 기존 세 줄은
그대로 유지):
```python
    cmds.menuItem(label="Maro 창 열기",
                  command="import maya.cmds as cmds\ncmds.maroMainWindow()",
                  parent=MENU_NAME)
    cmds.menuItem(divider=True, parent=MENU_NAME)
    cmds.menuItem(label="Skeleton Upload...",
                  command="import maroSkeletonUpload\nmaroSkeletonUpload.show()",
                  parent=MENU_NAME)
    cmds.menuItem(divider=True, parent=MENU_NAME)
    cmds.menuItem(label="ROS 연결 설정 (준비 중)", enable=False, parent=MENU_NAME)
    cmds.menuItem(label="환경설정 (준비 중)", enable=False, parent=MENU_NAME)
```

- [ ] **Step 3: `python/maroMainWindow.py`의 `teardown()`에 등록**

`teardown()` 함수 안, `maroLidarPanel.stop()` 블록 다음에 추가:
```python
    try:
        import maroSkeletonUpload
        maroSkeletonUpload.stop()
    except Exception:  # noqa: BLE001 -- Maya 콜백/언로드 경계
        import traceback
        traceback.print_exc()
```

- [ ] **Step 4: 빌드 + 전체 테스트**

전역 제약의 빌드+테스트 절차를 실행한다. Task 1의 `maya_skeleton_upload`를
포함해 전체 스위트가 그린인지 확인한다. 이 태스크에서 새로 추가한 Qt 다이얼로그
자체는 새 mayapy 테스트를 요구하지 않는다 — `SkeletonUploadDialog`는 어디서도
배치 모드에서 인스턴스화되지 않으므로(QApplication 부재로 프로세스가
abort된다, 이 코드베이스의 기존 제약과 같음) 기존 스위트가 그대로 통과하는
것 자체가 이 태스크가 기존 것을 깨지 않았다는 증거다.

- [ ] **Step 5: 수동 체크리스트 새 절 작성**

`docs/maro-main-ui-manual-checklist.md`의 `## 6. LiDAR 설정 + 시각화 (Phase 5)`
다음에 새 절을 추가한다:

```markdown
## 7. 스켈레톤 업로드/추출 (Phase 6) — **[필수 · go/no-go]**

1. 플러그인을 로드하고 씬을 새로 연다. "Maro" 메뉴 → "Skeleton Upload..."
   클릭 — **[필수]** 다이얼로그가 뜨는가("파일에서 임포트"/"현재 선택에서
   추출" 버튼 두 개).
2. 씬에 스킨된 메쉬 하나를 준비(간단한 실린더 + 조인트 체인 + 바인드 스킨)한
   뒤 선택하고 "현재 선택에서 추출" 클릭 — **[필수]** 상태 라벨에 인플루언스
   조인트 이름이 나열되고, 뷰포트에서 그 조인트들이 실제로 선택 상태로
   하이라이트되는가. 새 조인트가 만들어지지 않았는가(Outliner로 확인).
3. 스킨되지 않은 평범한 폴리곤 메쉬를 선택하고 "현재 선택에서 추출" 클릭 —
   **[필수]** `<메쉬이름>_root`라는 새 조인트가 메쉬의 바운딩박스 중심에
   생기고, 그 메쉬의 자식으로 붙어 있으며, 선택 상태인가.
4. 메쉬가 아닌 오브젝트(로케이터 등)를 선택하거나 아무것도 선택하지 않은
   채 "현재 선택에서 추출" 클릭 — **[필수]** "정확히 메쉬 하나를
   선택하세요" 메시지가 뜨고 아무 것도 만들어지지 않는가.
5. **[필수 · 이 기능의 진짜 위험 가정]** "파일에서 임포트" 클릭 → Maya의
   네이티브 임포트 다이얼로그가 뜨는가. 메쉬가 들어 있는 외부 파일(FBX/OBJ
   등)을 선택해 임포트 — 임포트가 끝나자마자 자동으로 스켈레톤 추출이
   이어서 실행되는가(스킨된 파일이면 인플루언스 선택, 아니면 루트 조인트
   생성). 이 항목이 실패하면 §4(콜백 스코핑)의 전제 자체를 재검토해야 한다.
6. 다이얼로그를 닫은 뒤 다른 목적으로(이 기능과 무관하게) File > Import로
   아무 파일이나 임포트 — **[필수]** 스켈레톤 추출이 자동으로 실행되지
   *않는가*(다이얼로그가 닫혀 있으면 콜백도 해제돼 있어야 한다).
7. 다이얼로그를 다시 열고 "파일에서 임포트"를 눌렀다가 파일 선택 창에서
   취소 — 다이얼로그를 닫는다 — **[필수]** 아무 크래시도, 스크립트
   에디터의 반복 에러도 없는가(취소로 인해 콜백이 걸린 채 남아있다가
   닫힐 때 정리되는 경로).
8. 다이얼로그가 열린 채로 `cmds.unloadPlugin("maro", force=True)` — **[필수]**
   Maya가 죽지 않는가(등록된 kAfterImport 콜백이 언로드 시 함께 정리됨).
```

문서 하단 "결과 기록" 표에도 위 8개 항목에 대응하는 행을 추가한다(기존 절의
행 형식을 그대로 따른다).

---

## 이 계획이 끝난 뒤

두 태스크 모두 완료되면 최종 전체 브랜치 리뷰(`superpowers:requesting-code-review`,
가장 강력한 모델)를 거친 뒤 `superpowers:finishing-a-development-branch`로
마무리한다. 리뷰어에게 특히 다음을 명시적으로 주목시킨다:
- `cmds.createNode("joint")`가 정말 `cmds.joint()`의 체이닝 부작용 없이
  독립된 조인트를 만드는지(전역 제약 위반이면 Critical).
- `kAfterImport` 콜백이 다이얼로그의 모든 종료 경로(정상 닫힘, 언로드,
  임포트 취소 후 재시도)에서 누수 없이 정리되는지.
- skinCluster 인플루언스 0개 퇴화 케이스가 정말 "no skinCluster" 경로로
  조용히 폴백하지 않는지.
