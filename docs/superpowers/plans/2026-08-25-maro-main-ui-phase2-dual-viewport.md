# Maro 메인 UI Phase 2 (듀얼 뷰포트) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `maroMainWindow`의 뷰포트를 하나에서 둘로 늘린다 — `paneLayout(configuration="vertical2")` 안에 라벨+`modelPanel` 쌍을 좌("Maya")/우("ROS") 각각 놓는다. 우측은 아직 좌표 변환 없이 좌측과 같은 씬을 별개 카메라로 보여줄 뿐이다.

**Architecture:** 기존 `python/maroMainWindow.py`의 `buildUI()`를 확장한다 — 새 C++ 커맨드는 필요 없다(`maroMainWindow` 커맨드 하나로 충분, `maro::runPluginPythonModule`도 안 바뀐다). 패널 이름을 위치가 아니라 역할로 지어(`VIEWPORT_NAME_MAYA`/`VIEWPORT_NAME_ROS`) Phase 3가 우측을 변환 대상으로 지목할 때 이름 자체가 의미를 갖게 한다. `MaroPluginMain.cpp`의 언로드 정리 MEL 문자열과 `tests/maya/test_main_window.py`의 이름 계약 대조를 세 이름(컨트롤 1개 + 뷰포트 2개) 전부로 확장한다 — Phase 0-1의 최종 리뷰(I7)가 지적했던 것과 같은 종류의 계약이다.

**Tech Stack:** Python(PySide6, `maya.cmds`, `maya.OpenMayaUI`), C++17(변경 없음, MEL 문자열만 수정).

## Global Constraints

- 스펙: `docs/superpowers/specs/2026-08-25-maro-main-ui-phase2-dual-viewport-design.md`
- 패널 이름은 위치(Left/Right)가 아니라 역할(Maya/Ros)로 짓는다: `VIEWPORT_NAME_MAYA = "maroMainWindowViewportMaya"`, `VIEWPORT_NAME_ROS = "maroMainWindowViewportRos"`. 기존 단수형 `VIEWPORT_NAME`은 완전히 사라진다(남기지 않는다 — 죽은 이름이 계약 대조 코드에 남으면 오히려 혼란을 준다).
- 기존 "테스트" 버튼(Qt 임베딩 스파이크 산출물)은 유지한다. 위치만 `paneLayout` 전체 위 상단 띠로 옮긴다.
- 두 뷰포트 모두 기존 `_hideViewportChrome()`을 그대로 적용한다(로직 변경 없음, 호출만 두 번).
- 각 뷰포트 위에 작은 텍스트 라벨("Maya"/"ROS")을 단다.
- `setStyleSheet()`를 호출하지 않는다(기존 규율 유지).
- Maya 명령 플래그(`paneLayout`이 자식으로 임의 레이아웃을 받는지, `configuration="vertical2"`의 정확한 동작)는 이 플랜 작성 시점에 실제 Maya 2026에서 전부 확인하지 않았다 — Task 1 Step 5에서 구현 중 직접 확인하고, 문서와 다르면 실제 동작을 따르고 그 이유를 기록한다(Phase 0-1이 `modelPanel` chrome 플래그에 대해 지켰던 것과 같은 규율).
- 빌드는 항상 `--config Release`를 명시한다.
- 빌드 환경: `VsDevCmd.bat`를 빌드와 같은 PowerShell 호출 안에서 설정한다:

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cd C:\Users\ckd30\Projects\Maya_Ros_Sim
cmake --build out/build --config Release
```

- `ctest --test-dir out/build -C Release --output-on-failure`는 **전부 통과해야 한다** — 사전 결함이 없다(이번 세션에 진짜 원인을 이미 고침).
- 이 태스크는 mayapy 배치 테스트로 "두 뷰포트가 실제로 렌더링/조작되는지"까지는 검증할 수 없다(Phase 0-1과 같은 한계) — 대화형 Maya 수동 체크리스트가 그 몫을 맡는다.

## 파일 구조

| 파일 | 책임 |
|---|---|
| `python/maroMainWindow.py` | (수정) `buildUI()`를 듀얼 뷰포트로 재구성, `VIEWPORT_NAME` → `VIEWPORT_NAME_MAYA`/`VIEWPORT_NAME_ROS`, `_deleteStalePanel()` 파라미터화 |
| `src/maro_plugin/MaroPluginMain.cpp` | (수정) 언로드 정리 MEL 문자열이 뷰포트 패널 두 개를 다 지우도록 |
| `tests/maya/test_main_window.py` | (수정) 이름 계약 대조를 세 이름으로 확장 |
| `docs/maro-main-ui-manual-checklist.md` | (수정) 듀얼 뷰포트 수동 확인 섹션 추가 |

---

### Task 1: 듀얼 뷰포트 레이아웃 + 이름 계약 확장

**Files:**
- Modify: `python/maroMainWindow.py`
- Modify: `src/maro_plugin/MaroPluginMain.cpp:454-458`
- Modify: `tests/maya/test_main_window.py`
- Modify: `docs/maro-main-ui-manual-checklist.md`

**Interfaces:**
- Produces: `python/maroMainWindow.py`의 `VIEWPORT_NAME_MAYA = "maroMainWindowViewportMaya"`, `VIEWPORT_NAME_ROS = "maroMainWindowViewportRos"` (모듈 상수, 기존 `CONTROL_NAME`과 같은 자리). `CONTROL_NAME`/`show()`/`buildUI()`/`_hideViewportChrome()`/`_onTestButtonClicked()`의 시그니처는 변경 없음.
- Consumes: 없음(이 태스크로 이 기능이 완결됨 — 새 커맨드도, 다른 태스크의 산출물도 필요 없음).

이 태스크는 Python/C++/테스트가 한 계약(세 개의 UI 이름)으로 묶여 있어 쪼개면 "절반만 통과하는 상태"가 생긴다 — 하나의 태스크로 묶는다.

- [ ] **Step 1: 테스트를 먼저 새 계약에 맞게 고친다(실패하는 상태로)**

`tests/maya/test_main_window.py`에서 아래 블록을 찾는다:

```python
assert maroMainWindow.CONTROL_NAME == "maroMainWindowControl", (
    f"CONTROL_NAME must match the MEL cleanup in MaroPluginMain.cpp, "
    f"got {maroMainWindow.CONTROL_NAME!r}"
)
assert maroMainWindow.VIEWPORT_NAME == "maroMainWindowViewport", (
    f"VIEWPORT_NAME must match the MEL cleanup in MaroPluginMain.cpp, "
    f"got {maroMainWindow.VIEWPORT_NAME!r}"
)
```

다음으로 바꾼다:

```python
assert maroMainWindow.CONTROL_NAME == "maroMainWindowControl", (
    f"CONTROL_NAME must match the MEL cleanup in MaroPluginMain.cpp, "
    f"got {maroMainWindow.CONTROL_NAME!r}"
)
assert maroMainWindow.VIEWPORT_NAME_MAYA == "maroMainWindowViewportMaya", (
    f"VIEWPORT_NAME_MAYA must match the MEL cleanup in MaroPluginMain.cpp, "
    f"got {maroMainWindow.VIEWPORT_NAME_MAYA!r}"
)
assert maroMainWindow.VIEWPORT_NAME_ROS == "maroMainWindowViewportRos", (
    f"VIEWPORT_NAME_ROS must match the MEL cleanup in MaroPluginMain.cpp, "
    f"got {maroMainWindow.VIEWPORT_NAME_ROS!r}"
)
```

바로 아래 소스-읽기 대조 블록:

```python
assert maroMainWindow.CONTROL_NAME in _pluginMainSource, (
    f"MaroPluginMain.cpp no longer mentions {maroMainWindow.CONTROL_NAME!r} -- "
    "unload cleanup would silently no-op"
)
assert maroMainWindow.VIEWPORT_NAME in _pluginMainSource, (
    f"MaroPluginMain.cpp no longer mentions {maroMainWindow.VIEWPORT_NAME!r} -- "
    "unload cleanup would silently no-op"
)
print("C++/Python UI name contract OK (pinned on both sides)")
```

다음으로 바꾼다:

```python
assert maroMainWindow.CONTROL_NAME in _pluginMainSource, (
    f"MaroPluginMain.cpp no longer mentions {maroMainWindow.CONTROL_NAME!r} -- "
    "unload cleanup would silently no-op"
)
assert maroMainWindow.VIEWPORT_NAME_MAYA in _pluginMainSource, (
    f"MaroPluginMain.cpp no longer mentions {maroMainWindow.VIEWPORT_NAME_MAYA!r} -- "
    "unload cleanup would silently no-op"
)
assert maroMainWindow.VIEWPORT_NAME_ROS in _pluginMainSource, (
    f"MaroPluginMain.cpp no longer mentions {maroMainWindow.VIEWPORT_NAME_ROS!r} -- "
    "unload cleanup would silently no-op"
)
print("C++/Python UI name contract OK (pinned on both sides, 3 names)")
```

파일 맨 위 docstring의 "C++/Python이 공유하는 UI 이름 두 개가 실제로 같다" 문장도 "UI 이름 세 개"로 고친다(사소하지만 다음 사람이 읽을 때 숫자가 맞아야 한다).

- [ ] **Step 2: 테스트가 실패하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
ctest --test-dir out/build -C Release -R maya_main_window --output-on-failure
```

기대: `AttributeError: module 'maroMainWindow' has no attribute 'VIEWPORT_NAME_MAYA'`로 실패(아직 Python 쪽을 안 고쳤으므로).

- [ ] **Step 3: `python/maroMainWindow.py`의 `buildUI()`를 듀얼 뷰포트로 재구성**

`VIEWPORT_NAME = "maroMainWindowViewport"` 줄을 지우고 그 자리에:

```python
VIEWPORT_NAME_MAYA = "maroMainWindowViewportMaya"
VIEWPORT_NAME_ROS = "maroMainWindowViewportRos"
```

`_deleteStalePanel()`을 파라미터화한다 — 기존:

```python
def _deleteStalePanel():
    """같은 이름의 modelPanel이 남아 있으면 지운다.
    ...
    """
    if cmds.modelPanel(VIEWPORT_NAME, exists=True):
        cmds.deleteUI(VIEWPORT_NAME, panel=True)
```

다음으로:

```python
def _deleteStalePanel(panelName):
    """같은 이름의 modelPanel이 남아 있으면 지운다.

    modelPanel은 부모 레이아웃의 자식이면서 동시에 Maya의 전역 패널
    레지스트리에 등록되는 객체다 -- 부모가 사라져도 등록이 남아 있을 수
    있고, 그러면 다음 buildUI()의 생성이 이름 충돌로 실패한다.
    workspaceControl은 -uiScript로 재생성되므로(도킹/복원/플러그인 재로드)
    buildUI()는 한 세션에 여러 번 불릴 수 있다. 뷰포트가 두 개(Phase 2)라
    호출하는 쪽에서 이름을 넘긴다.
    """
    if cmds.modelPanel(panelName, exists=True):
        cmds.deleteUI(panelName, panel=True)
```

`buildUI()` 본문에서 `_deleteStalePanel()` 단독 호출과 `panel = cmds.modelPanel(VIEWPORT_NAME, parent=form)` 한 줄짜리 뷰포트 생성 블록(현재 Step 100-108 부근, `form = cmds.formLayout()` 다음, `# --- 여기부터가 이 스파이크의 핵심 두 줄 ---` 앞)을 통째로 아래로 바꾼다:

```python
    form = cmds.formLayout()

    pane = cmds.paneLayout(configuration="vertical2", parent=form)
    mayaPanelControl = _buildLabeledViewport(pane, "Maya", VIEWPORT_NAME_MAYA)
    rosPanelControl = _buildLabeledViewport(pane, "ROS", VIEWPORT_NAME_ROS)
```

그리고 `buildUI()` 위에 새 헬퍼를 추가한다(`_deleteStalePanel()` 바로 아래, `buildUI()` 정의 바로 위):

```python
def _buildLabeledViewport(parent, label, panelName):
    """`parent`(paneLayout의 한 칸) 안에 라벨 한 줄 + modelPanel 하나를 쌓는다.

    Phase 0-1의 단일 뷰포트 조립을 두 번 반복하는 대신 함수로 뽑았다 --
    Maya/ROS 두 뷰포트가 라벨 문구만 다르고 나머지 조립(스테일 패널 정리,
    chrome 숨김, formLayout attach)은 완전히 같기 때문이다. 반환값은
    formLayout attach에 쓸 수 있는 패널의 **컨트롤** 이름이다(패널 이름
    자체가 아니다 -- Phase 0-1의 같은 주석 참고).
    """
    side = cmds.formLayout(parent=parent)
    labelControl = cmds.text(label=label, parent=side)

    _deleteStalePanel(panelName)
    panel = cmds.modelPanel(panelName, parent=side)
    _hideViewportChrome(panel)
    panelControl = cmds.modelPanel(panel, query=True, control=True) or panel

    cmds.formLayout(
        side, edit=True,
        attachForm=[
            (labelControl, "top", 2), (labelControl, "left", 2), (labelControl, "right", 2),
            (panelControl, "left", 0), (panelControl, "right", 0), (panelControl, "bottom", 0),
        ],
        attachControl=[(panelControl, "top", 2, labelControl)])
    return panelControl
```

마지막으로, 버튼을 붙이는 기존 `formLayout(form, edit=True, attachForm=[...], attachControl=[...])` 호출에서 `panelControl`을 참조하던 자리를 `pane`(두 뷰포트를 담은 `paneLayout` 전체)으로 바꾼다:

```python
    try:
        cmds.formLayout(
            form, edit=True,
            attachForm=[
                (buttonName, "top", 4), (buttonName, "left", 4), (buttonName, "right", 4),
                (pane, "left", 0), (pane, "right", 0), (pane, "bottom", 0),
            ],
            attachControl=[(pane, "top", 4, buttonName)])
    except RuntimeError as error:
        raise RuntimeError(
            "maroMainWindow: the native formLayout refused to lay out the "
            "embedded widget ({!r}) next to the dual-viewport pane ({!r}): {} "
            "-- see docs/maro-main-ui-manual-checklist.md".format(
                buttonName, pane, error))
    return form
```

(에러 메시지의 `panelControl` 표현을 `pane`으로 바꾼 것 외엔 이 블록의 나머지 — 버튼 생성, `MQtUtil` 임베딩 두 줄 — 는 그대로 둔다.)

- [ ] **Step 4: `src/maro_plugin/MaroPluginMain.cpp`의 언로드 정리를 두 패널 다 지우도록 수정**

`MaroPluginMain.cpp:454-458`:

```cpp
        MGlobal::executeCommand(
            "if (`workspaceControl -exists maroMainWindowControl`) "
            "workspaceControl -e -close maroMainWindowControl;"
            "if (`modelPanel -exists maroMainWindowViewport`) "
            "deleteUI -panel maroMainWindowViewport;");
        plugin.deregisterCommand("maroMainWindow");
```

를:

```cpp
        MGlobal::executeCommand(
            "if (`workspaceControl -exists maroMainWindowControl`) "
            "workspaceControl -e -close maroMainWindowControl;"
            "if (`modelPanel -exists maroMainWindowViewportMaya`) "
            "deleteUI -panel maroMainWindowViewportMaya;"
            "if (`modelPanel -exists maroMainWindowViewportRos`) "
            "deleteUI -panel maroMainWindowViewportRos;");
        plugin.deregisterCommand("maroMainWindow");
```

로 바꾼다. 그 위 주석(`:440-444` 부근, "두 이름은 python/maroMainWindow.py의 CONTROL_NAME/VIEWPORT_NAME과 같은 문자열이어야 하며")도 "세 이름은... CONTROL_NAME/VIEWPORT_NAME_MAYA/VIEWPORT_NAME_ROS와"로 고친다.

- [ ] **Step 5: 빌드하고 테스트가 통과하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release -R maya_main_window --output-on-failure
```

기대: 통과. 만약 `cmds.paneLayout`/`cmds.text`/`cmds.formLayout(parent=...)` 호출 방식이 실제 Maya 2026 동작과 다르다면(예: `paneLayout`이 두 개보다 많은 자식을 받으면 에러를 내는지, `configuration="vertical2"` 대신 다른 문자열이 필요한지), 배치 모드에서는 어차피 이 코드 경로가 실행되지 않으므로(`cmds.about(batch=True)`가 먼저 막는다) 이 시점엔 드러나지 않는다 — Step 6의 수동 확인에서 실제로 검증한다. 다만 Maya 2026 커맨드 레퍼런스로 `paneLayout`/`text` 플래그를 미리 한 번 대조해 두면 수동 확인 단계에서 삽질을 줄일 수 있다.

전체 스위트도 돌려 회귀가 없는지 확인한다:

```bash
ctest --test-dir out/build -C Release --output-on-failure
```

기대: 전부 통과(사전 결함 없음).

- [ ] **Step 6: `docs/maro-main-ui-manual-checklist.md`에 듀얼 뷰포트 확인 섹션 추가**

기존 "## 1. `modelPanel`이 실제 뷰포트로 동작하는가" 섹션 다음에(또는 적절한 자리에) 새 섹션을 추가한다:

```markdown
## 1-1. 듀얼 뷰포트 (Phase 2) — **[필수 · go/no-go]**

- [ ] 창을 열면 뷰포트가 **두 개** 좌우로 나란히 보인다("테스트" 버튼은
      맨 위 띠에 그대로 있다).
- [ ] 좌측 뷰포트 위에 "Maya", 우측 뷰포트 위에 "ROS" 라벨이 각각 보인다.
- [ ] 좌측 뷰포트에서 씬을 조작(궤도/팬/줌)해도 **우측 뷰포트의 카메라는
      바뀌지 않는다**(두 뷰포트는 서로 독립된 카메라를 가진다 — 아직은
      의도적으로 동기화하지 않는다).
- [ ] 우측 뷰포트도 좌측과 똑같이 궤도/팬/줌이 되고, 좌측과 같은 씬(같은
      큐브 등)을 그린다(아직 좌표 변환 없음 — Phase 3에서 달라진다).
- [ ] 두 뷰포트 모두 chrome(메뉴바/아이콘 바)이 숨겨져 있다.
- [ ] 창을 띄운 채 `cmds.unloadPlugin("maro")` 실행 → **Maya가 크래시하지
      않는다**, 스크립트 에디터에 에러가 없다, 언로드 후 아래가 전부
      `False`/빈 목록이다:

      ```python
      cmds.workspaceControl("maroMainWindowControl", exists=True)   # False
      cmds.modelPanel("maroMainWindowViewportMaya", exists=True)    # False
      cmds.modelPanel("maroMainWindowViewportRos", exists=True)     # False
      ```
```

결과 기록 표에도 행을 하나 추가한다:

```markdown
| 1-1. 듀얼 뷰포트 (독립 조작 + 언로드) | 필수 | 미실행 | | |
```

- [ ] **Step 7: 커밋**

```bash
git add python/maroMainWindow.py src/maro_plugin/MaroPluginMain.cpp \
        tests/maya/test_main_window.py docs/maro-main-ui-manual-checklist.md
git commit -m "feat: add second modelPanel viewport (Maya/ROS, no transform yet)"
```
