# Maro 메인 UI Phase 0-1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Maya 상단에 "Maro" 메뉴가 생기고, 그 메뉴에서 여는 새 PySide6 메인 창 안에 네이티브 `modelPanel`(실제 3D 뷰포트) 하나와 PySide6 위젯 하나가 같은 레이아웃 안에 공존하며, 플러그인을 언로드해도 크래시하지 않는다는 것을 증명하는 워킹 스켈레톤. 이후 단계(뷰포트 2개, ROS 좌표 프록시, 스켈레톤 업로드, 노드 바인딩, 디버그 터미널)는 이 스파이크가 통과한 뒤 별도 계획으로 다시 쓴다.

**Architecture:** 컨테이너는 끝까지 네이티브로 유지한다 — `cmds.workspaceControl` + `cmds.formLayout`로 만들고, `modelPanel`도 그 안에 `cmds.modelPanel()`로 직접 생성한다(리페어런팅 없음). 커스텀 PySide6 위젯만 `MQtUtil.addWidgetToMayaLayout()`으로 같은 네이티브 레이아웃에 끼워 넣는다. 새 커맨드가 플러그인 디렉터리를 찾아 Python 모듈을 import하는 로직은 기존 `MaroDiagPanelCommand::doIt`에 이미 있던 것을 공용 헬퍼로 뽑아 세 번째 커맨드부터 재사용한다.

**Tech Stack:** C++17, Maya 2026 devkit(PySide6/shiboken6, `MQtUtil`), CMake(Visual Studio 멀티 컨피그 제너레이터).

## Global Constraints

- 스펙: `docs/superpowers/specs/2026-08-24-maro-main-ui-phase0-1-design.md`
- 새 커맨드는 `MaroDiagPanelCommand::doIt`가 하던 것과 정확히 같은 방식으로 플러그인 디렉터리를 찾는다: `MFnPlugin::findPlugin("maro")` → `MFnPlugin(pluginObj, "Unknown", "Unknown", "Any", &status)` → `loadPath(&status)` → `sys.path`에 없으면 삽입 → `import <module>` → 호출. 하드코딩된 설치 경로를 쓰지 않는다.
- 이 로직은 Task 2에서 공용 헬퍼로 추출한다(`src/maro_plugin/MaroPythonBridge.h`/`.cpp`, 새 파일) — Task 2와 Task 3이 각자 새 커맨드를 추가하면서 세 번째로 복붙하지 않기 위함. 기존 `MaroDiagPanelCommand::doIt`도 이 헬퍼를 쓰도록 리팩터링한다(동작은 바뀌지 않아야 하며, `tests/maya/test_panel_commands.py`가 회귀를 잡는다).
- 새 `.py` 파일은 `setStyleSheet()`를 호출하지 않는다 — Maya 프로세스 전역 `QApplication` 스타일을 그대로 물려받아야 "기존 mayaUI 디자인과 이질감이 없도록" 요구를 만족한다.
- Maya 명령 플래그(`modelPanel`의 chrome 최소화 플래그 등)는 이 플랜의 문서화 시점에 정확한 이름을 전부 확인하지 않았다 — Task 2 구현 중 Maya 2026 커맨드 레퍼런스(또는 `mel help modelPanel`)로 실제 플래그명을 확인하고, 문서와 다르면 실제 동작을 따르고 그 이유를 기록한다(이 프로젝트가 Embree/ROS 헤더 대조 때 지켜온 것과 같은 규율).
- 빌드는 항상 `--config Release`를 명시한다.
- 빌드 환경: `VsDevCmd.bat`를 빌드와 같은 PowerShell 호출 안에서 설정한다:

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cd C:\Users\ckd30\Projects\Maya_Ros_Sim
cmake --build out/build --config Release
```

- `ctest --test-dir out/build -C Release --output-on-failure`는 **전부 통과해야 한다** — `maya_panel_commands`의 진짜 원인(CMake `$<CONFIG>` 누락)이 이번 세션에 고쳐졌으므로 더 이상 "알려진 사전 결함"이 없다. 하나라도 실패하면 이 플랜이 만든 회귀다.
- Task 2는 mayapy 배치 테스트로 검증할 수 없다(실제 뷰포트 렌더링과 Qt 이벤트 루프 필요) — 대화형 Maya 2026에서 수행하는 수동 체크리스트가 유일한 검증 수단이며, 태스크 완료 기준에 명시한다.

## 파일 구조

| 파일 | 책임 |
|---|---|
| `src/maro_plugin/CMakeLists.txt` | (수정) `.py` 모듈 스테이징을 파일 목록 순회 형태로 일반화 |
| `src/maro_plugin/MaroPythonBridge.h` / `.cpp` | (신규) 플러그인 디렉터리를 찾아 Python 모듈을 import+호출하는 공용 헬퍼 |
| `src/maro_plugin/MaroPanelCommands.cpp` | (수정) `MaroDiagPanelCommand::doIt`가 새 헬퍼를 쓰도록 리팩터링 |
| `python/maroMainWindow.py` | (신규) `modelPanel` + PySide6 버튼을 같은 네이티브 레이아웃에 올리는 `buildUI()`/`show()` |
| `src/maro_plugin/MaroMainWindowCommand.h` / `.cpp` | (신규) `maroMainWindow` 커맨드 |
| `python/maroMenu.py` | (신규) Maro 메뉴 생성/존재 확인 |
| `src/maro_plugin/MaroMenuCommands.h` / `.cpp` | (신규) `maroBuildMenu` 커맨드 |
| `src/maro_plugin/MaroPluginMain.cpp` | (수정) 새 커맨드 3개 등록/해제, `initializePlugin` 끝에서 `maroBuildMenu` 호출, `uninitializePlugin`에서 메뉴 삭제 |
| `docs/maro-main-ui-manual-checklist.md` | (신규) Task 2 수동 검증 체크리스트 |
| `tests/maya/test_main_menu.py` | (신규) 메뉴 존재/삭제 mayapy 테스트 |

---

### Task 1: CMake — 다중 Python UI 모듈 스테이징 일반화

**Files:**
- Modify: `src/maro_plugin/CMakeLists.txt`

**Interfaces:**
- Produces: `MARO_PLUGIN_PY_MODULES` 같은 CMake 리스트 변수(파일명만, 예: `maroDiagPanel;maroMainWindow;maroMenu`) — Task 2, 3에서 새 `.py`를 추가할 때 이 리스트에 이름만 더하면 되도록.

`MARO_DIAG_PANEL_PY_SRC`/`MARO_DIAG_PANEL_PY_OUT`/`add_custom_command`/`add_custom_target(maro_diag_panel_py ...)`/`add_dependencies` 블록(현재 `maroDiagPanel.py` 하나만 처리)을 `foreach(pyModule IN LISTS MARO_PLUGIN_PY_MODULES)` 루프로 바꿔, 각 모듈마다 독립된 `add_custom_command`(OUTPUT 기반, `$<CONFIG>` 포함)와 독립된 `add_custom_target(maro_py_${pyModule} ALL DEPENDS ...)`를 만들고 각각 `add_dependencies(${PROJECT_NAME} maro_py_${pyModule})`한다. 기존 `MARO_SENTINEL_EXE_OUT` 블록(같은 파일, exe 버전)의 `$<CONFIG>` 처리 방식과 "OUTPUT 자리엔 타깃 조회가 필요 없는 것만" 이유를 그대로 따른다 — 그 블록의 주석을 새로 만드는 루프에도 요약해 남긴다.

- [ ] **Step 1: 리스트 변수 도입 + 루프로 변환**

`MARO_PLUGIN_PY_MODULES`를 `maroDiagPanel` 하나만 담아 선언하고, 기존 단일 블록을 이 리스트를 순회하는 `foreach`로 재작성한다. 이 시점에는 아직 `maroMainWindow`/`maroMenu`를 리스트에 넣지 않는다(Task 2, 3에서 각자 추가) — Task 1은 순수 리팩터링이라 동작이 바뀌면 안 된다.

- [ ] **Step 2: 빌드하고 회귀 확인**

```powershell
cmake --build out/build --config Release
```

`out/build/src/maro_plugin/Release/maroDiagPanel.py`가 여전히 존재하는지 확인.

```bash
ctest --test-dir out/build -C Release -R "maya_panel_commands|maya_load" --output-on-failure
```

기대: 둘 다 통과(순수 리팩터링이므로 동작 불변).

- [ ] **Step 3: 커밋**

```bash
git add src/maro_plugin/CMakeLists.txt
git commit -m "refactor(cmake): generalize python UI module staging to a list loop"
```

---

### Task 2: 네이티브 컨테이너 + `modelPanel` + PySide6 버튼 스파이크

**Files:**
- Create: `python/maroMainWindow.py`
- Create: `src/maro_plugin/MaroPythonBridge.h` / `.cpp`
- Create: `src/maro_plugin/MaroMainWindowCommand.h` / `.cpp`
- Modify: `src/maro_plugin/MaroPanelCommands.cpp` (리팩터링, `MaroDiagPanelCommand::doIt`가 새 헬퍼 사용)
- Modify: `src/maro_plugin/CMakeLists.txt` (`MARO_PLUGIN_PY_MODULES`에 `maroMainWindow` 추가, 신규 `.cpp` 소스 추가)
- Modify: `src/maro_plugin/MaroPluginMain.cpp` (`maroMainWindow` 커맨드 등록/해제)
- Create: `docs/maro-main-ui-manual-checklist.md`

**Interfaces:**
- Produces: Maya 커맨드 `maroMainWindow` (인자 없음, `MaroDiagPanelCommand`와 같은 형태 — 열거나 이미 있으면 복원)
- Produces: `src/maro_plugin/MaroPythonBridge.h`의 `MStatus maro::runPluginPythonModule(const MString& moduleName, const MString& callExpression)` — 플러그인 디렉터리를 찾아 `sys.path`에 넣고 `import <moduleName>`한 뒤 `callExpression`을 실행. 실패 시 기존 `doIt`들과 같은 방식으로 `MGlobal::displayError` + `MS::kFailure`.
- Consumes: `MFnPlugin::findPlugin`/`loadPath`, `MGlobal::executePythonCommand` (기존 `MaroDiagPanelCommand::doIt`, `MaroPanelCommands.cpp:293-334`가 원본 — 이 로직을 그대로 옮긴다)

**Step 1: 공용 Python 브리지 헬퍼 추출**

`src/maro_plugin/MaroPythonBridge.h`/`.cpp`를 새로 만들고, `MaroPanelCommands.cpp:293-334`의 `MaroDiagPanelCommand::doIt` 본문(try/catch, `findPlugin`, `MFnPlugin` 생성, `loadPath`, python 문자열 조립, `executePythonCommand`)을 `runPluginPythonModule(moduleName, callExpression)`로 옮긴다. `moduleName`이 `import <moduleName>\n`을, `callExpression`이 마지막 줄을 이룬다. `MaroDiagPanelCommand::doIt`를 `return maro::runPluginPythonModule("maroDiagPanel", "maroDiagPanel.show()");` 한 줄로 줄인다.

- [ ] **Step 1 검증**: `ctest -R maya_panel_commands` 통과(리팩터링 전후 동작 동일해야 함).

**Step 2: `maroMainWindow` 커맨드**

`src/maro_plugin/MaroMainWindowCommand.h`/`.cpp`를 `MaroPanelCommands.h`/`.cpp`의 `MaroDiagPanelCommand`와 같은 모양으로 새로 만든다. `doIt()`는 `return maro::runPluginPythonModule("maroMainWindow", "maroMainWindow.show()");`.

**Step 3: `python/maroMainWindow.py`**

`maroDiagPanel.py`의 `show()`/`CONTROL_NAME` 패턴을 그대로 따르되 새 컨트롤 이름(`maroMainWindowControl`)과 새 `uiScript`(`"import maroMainWindow; maroMainWindow.buildUI()"`)를 쓴다. `buildUI()`:

1. `cmds.formLayout()` 루트 생성.
2. `cmds.modelPanel(parent=root)`로 뷰포트 생성. Chrome을 최소화하는 정확한 edit 플래그(메뉴바/툴바 숨김 등)는 Maya 2026 커맨드 레퍼런스로 실제 플래그명을 확인해서 적용 — 이 플랜 작성 시점엔 확정하지 않았다(Global Constraints 참고).
3. `omui.MQtUtil.findLayout(root)`로 루트 레이아웃의 Qt 포인터를 얻고 `shiboken6.wrapInstance`로 `QWidget`화(필요하면 — `addWidgetToMayaLayout`는 레이아웃 이름 문자열이 아니라 `QWidget*`를 받으므로 확인 필요).
4. `QPushButton("테스트")` 하나를 만들고 클릭 시 `print("Maro main window: button clicked")`만 하는 슬롯 연결.
5. `omui.MQtUtil.addWidgetToMayaLayout(shiboken6.getCppPointer(button)[0], layoutPtr)`로 버튼을 같은 폼레이아웃에 끼워 넣는다.
6. `cmds.formLayout(root, edit=True, attachForm=[...])`로 `modelPanel`과 버튼의 상대 배치를 잡는다(버튼은 상단 좁은 띠, `modelPanel`이 나머지 전부 — 정확한 비율은 스파이크 목적상 중요하지 않음).

`setStyleSheet()`를 호출하지 않는다(Global Constraints).

**Step 4: 커맨드 등록/해제**

`src/maro_plugin/MaroPluginMain.cpp`: `maroDiagPanel` 등록 직후(`:334-339` 근방)에 `maroMainWindow` 등록을 추가한다(같은 에러 처리 패턴, `status.perror("Maro: failed to register maroMainWindow")`). 해제는 기존 `workspaceControl` 정리 줄(`:386-389` 근방, `maroDiagPanelControl` 닫기 + `deregisterCommand("maroDiagPanel")`) 바로 옆에, 같은 방식으로 `maroMainWindowControl`을 닫는 `executeCommand` + `deregisterCommand("maroMainWindow")`를 추가한다(등록 역순 규율 유지).

**Step 5: CMake 배선**

`MARO_PLUGIN_PY_MODULES`에 `maroMainWindow` 추가, 신규 `.cpp` 2개(`MaroPythonBridge.cpp`, `MaroMainWindowCommand.cpp`)를 플러그인 타깃 소스 목록에 추가.

**Step 6: 수동 체크리스트 작성 + 실행**

`docs/maro-main-ui-manual-checklist.md`를 `docs/maro-panel-manual-checklist.md`와 같은 형식으로 새로 쓰고, 다음을 대화형 Maya 2026에서 직접 수행해 기록한다:

- [ ] `maroMainWindow` 실행 → `modelPanel`이 씬을 렌더링하고 궤도/줌/팬 조작이 되는가.
- [ ] PySide6 버튼이 같은 창에 보이고 클릭 시 Script Editor에 print가 찍히는가.
- [ ] 창을 띄운 채 `unloadPlugin("maro")` 실행 → Maya가 크래시하지 않는가. **(이 스파이크의 진짜 go/no-go 기준)**
- [ ] `workspaceControl` 독/플로팅 전환, 레이아웃 저장 후 Maya 재시작 시 복원 동작이 `maroDiagPanel`과 동등한가.

체크리스트의 네 항목이 전부 통과해야 이 태스크가 완료된 것으로 본다. 하나라도 실패(특히 언로드 크래시)하면 BLOCKED로 보고하고 대안(예: `modelPanel` 대신 커스텀 렌더러, 스펙 §4.3의 Option C)을 컨트롤러에게 에스컬레이션한다 — 이 플랜의 나머지 로드맵 전체가 이 결과에 달려 있다.

- [ ] **Step 7: 커밋**

```bash
git add src/maro_plugin/MaroPythonBridge.h src/maro_plugin/MaroPythonBridge.cpp \
        src/maro_plugin/MaroMainWindowCommand.h src/maro_plugin/MaroMainWindowCommand.cpp \
        src/maro_plugin/MaroPanelCommands.cpp src/maro_plugin/MaroPluginMain.cpp \
        src/maro_plugin/CMakeLists.txt python/maroMainWindow.py \
        docs/maro-main-ui-manual-checklist.md
git commit -m "feat: add maroMainWindow spike (native modelPanel + embedded PySide6 button)"
```

---

### Task 3: Maro 메뉴 등록/해제

**Files:**
- Create: `python/maroMenu.py`
- Create: `src/maro_plugin/MaroMenuCommands.h` / `.cpp`
- Modify: `src/maro_plugin/CMakeLists.txt` (`MARO_PLUGIN_PY_MODULES`에 `maroMenu` 추가, 신규 `.cpp` 추가)
- Modify: `src/maro_plugin/MaroPluginMain.cpp` (`maroBuildMenu` 등록/해제, `initializePlugin` 끝에서 호출)
- Create: `tests/maya/test_main_menu.py`

**Interfaces:**
- Produces: Maya 커맨드 `maroBuildMenu` (인자 없음) — `maro::runPluginPythonModule("maroMenu", "maroMenu.build()")` 한 줄.
- Produces: `python/maroMenu.py`의 `build()` — 이미 있으면 아무것도 안 함(멱등), `cmds.menu(parent="MayaWindow", label="Maro")` 아래 메뉴 아이템들을 만듦.
- Consumes: Task 2에서 만든 `MaroPythonBridge.h`의 `runPluginPythonModule`.

**Step 1: `python/maroMenu.py`**

```python
MENU_NAME = "maroMainMenu"

def build():
    if cmds.menu(MENU_NAME, exists=True):
        return
    cmds.menu(MENU_NAME, parent="MayaWindow", label="Maro", tearOff=False)
    cmds.menuItem(label="Maro 창 열기", command="cmds.maroMainWindow()", parent=MENU_NAME)
    cmds.menuItem(divider=True, parent=MENU_NAME)
    cmds.menuItem(label="ROS 연결 설정 (준비 중)", enable=False, parent=MENU_NAME)
    cmds.menuItem(label="환경설정 (준비 중)", enable=False, parent=MENU_NAME)
```

(정확한 문자열/플래그는 구현 중 Maya 2026 `cmds.menu`/`cmds.menuItem` 레퍼런스로 재확인 — `command=` 인자가 문자열인지 콜러블인지는 MEL 프록시 커맨드(`maroMainWindow`)를 부르는 것이므로 문자열 형태(`"cmds.maroMainWindow()"` 또는 `functools.partial`)로 확인한다.)

**Step 2: `maroBuildMenu` 커맨드**

`src/maro_plugin/MaroMenuCommands.h`/`.cpp`, `MaroMainWindowCommand`와 같은 모양. `doIt()`: `return maro::runPluginPythonModule("maroMenu", "maroMenu.build()");`.

**Step 3: `MaroPluginMain.cpp` 배선**

`initializePlugin`에서 `maroBuildMenu` 등록 후, 함수 맨 끝(`maro::BoadMaro::info("Maro: plugin loaded.")` 직전)에서 `MGlobal::executeCommand("maroBuildMenu")` 호출을 추가한다 — **이 호출의 실패는 플러그인 로드를 막지 않는다**(리턴값을 버리거나 `BoadMaro::warn`류로만 기록; 메뉴는 UI 편의이지 핵심 기능이 아니다). `uninitializePlugin`에서 기존 `workspaceControl` 닫기 줄(`:386-389`) 근처에 메뉴 삭제를 추가한다:

```cpp
MGlobal::executeCommand(
    "if (`menu -exists maroMainMenu`) deleteUI -menu maroMainMenu;");
```

등록/해제는 이 파일의 기존 규율(등록 역순 해제)을 따른다.

**Step 4: `tests/maya/test_main_menu.py`**

`tests/maya/test_panel_commands.py`와 같은 mayapy 배치 구조. `loadPlugin` 후 `cmds.menu("maroMainMenu", exists=True)`가 True인지, `unloadPlugin` 후 False인지 확인. (배치 모드에도 `cmds.menu`/`MayaWindow`가 존재하는지는 구현 중 직접 확인 필요 — 배치 모드엔 실제 메인 윈도우가 없을 수 있으므로, 만약 `parent="MayaWindow"`가 배치 모드에서 실패한다면 `initializePlugin`의 메뉴 생성 호출을 `about(batch=True)`로 건너뛰게 하거나, 테스트 쪽에서 이 제약을 문서화하고 존재 확인 대신 "예외 없이 반환"만 확인하는 형태로 낮춘다 — 어느 쪽이든 발견한 사실과 선택을 보고서에 남긴다.)

- [ ] **Step 5: 빌드 + 전체 테스트**

```powershell
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure
```

기대: 전부 통과(사전 결함 없음).

- [ ] **Step 6: 커밋**

```bash
git add src/maro_plugin/MaroMenuCommands.h src/maro_plugin/MaroMenuCommands.cpp \
        src/maro_plugin/MaroPluginMain.cpp src/maro_plugin/CMakeLists.txt \
        python/maroMenu.py tests/maya/test_main_menu.py
git commit -m "feat: add Maro top-level menu (maroBuildMenu), loaded after plugin init"
```
