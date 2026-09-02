# Maro 환경설정 창 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Maro 플러그인에 "환경설정" 창을 처음 추가한다 — ROS 연결(domain ID/robotName) + Tech Diag 리밋 근접 임계값을 `cmds.optionVar`로 영구 저장하고, 지금 없는 "ROS 연결 시작/중지" UI를 함께 제공한다.

**Architecture:** 새 파일 `python/maroSettingsPanel.py` 하나 — Task 1이 Qt와 무관한 optionVar 읽기/쓰기 순수 함수 4개를 만들고, Task 2가 같은 파일에 PySide6 `QWidget` UI 클래스를 추가하며 메뉴/teardown/Tech Diag에 배선한다. 새 C++ 코드는 전혀 없다 — 기존 `maroStartBridge`/`maroStopBridge` 커맨드와 `os.environ["ROS_DOMAIN_ID"]`(파이썬이 쓰면 같은 프로세스의 C++ `std::getenv`가 그대로 봄)만으로 충분하다.

**Tech Stack:** Python, PySide6, `maya.cmds.optionVar`(이 코드베이스 최초 사용).

## Global Constraints

- optionVar 이름은 정확히 이 네 개다: `maroSettingRosRobotName`(string), `maroSettingRosDomainIdOverride`(int, 0/1), `maroSettingRosDomainId`(int), `maroSettingTechDiagLimitProximityThreshold`(float).
- 도메인 ID 스핀박스 범위는 0-232(ROS 2 유효 도메인 범위).
- Tech Diag 임계값 기본값은 기존 하드코딩 값과 동일한 0.9.
- 새 C++ 커맨드/DG 어트리뷰트를 추가하지 않는다.
- 새 `.py`는 `setStyleSheet()`를 호출하지 않는다(이 코드베이스 전역 규율).
- 창은 비모달이다(`QtCore.Qt.Window`) — 열려 있는 동안 MaroUI의 다른 조작을 막지 않는다.
- 진단/book 저장 경로 설정은 이번 스코프에서 완전히 제외한다(스펙 §3.4 — `bookPaths()`가 플러그인 로드 시 1회만 계산되는 정적값이라 이 프로젝트의 optionVar로는 원리적으로 반영할 방법이 없다).
- ROS 연결 상태를 상시 표시하는 상태 표시줄은 두지 않는다 — `maroStartBridge`/`maroStopBridge`가 이미 내는 콘솔 경고(그리고 최근 병합된 진단 구분선)로 충분하다.
- `os.environ["ROS_DOMAIN_ID"]`를 통한 도메인 ID 반영이 실제로 `rclcpp::init()`에 닿는지는 이 프로젝트 관례상 실측 확인이 필요하다 — Task 2의 수동 체크리스트가 go/no-go 항목으로 이걸 검증한다.

---

### Task 1: optionVar 읽기/쓰기 순수 함수

**Files:**
- Create: `python/maroSettingsPanel.py`
- Test: `tests/maya/test_settings_panel.py`
- Modify: `tests/CMakeLists.txt` (새 테스트를 기존 "플러그인만 있으면 되는" 그룹에 등록)

**Interfaces:**
- Produces: `readRosSettings() -> (robotName: str, domainIdOverrideEnabled: bool, domainId: int)`, `writeRosSettings(robotName: str, domainIdOverrideEnabled: bool, domainId: int) -> None`, `readTechDiagThreshold() -> float`, `writeTechDiagThreshold(value: float) -> None`. Task 2는 이 네 함수와, 이 파일 안의 optionVar 이름 상수(`_ROBOT_NAME_VAR` 등)를 그대로 재사용한다.

- [ ] **Step 1: `python/maroSettingsPanel.py` 작성**

```python
"""Maro 환경설정 -- ROS 연결 값(domain ID/robotName)과 Tech Diag 리밋 근접
경고 임계값을 Maya의 optionVar에 영구 저장한다(이 코드베이스 최초의
cmds.optionVar 사용).

아래 읽기/쓰기 함수는 Qt와 무관한 순수 함수다 -- mayapy 배치에서 QWidget
없이 검증 가능하다. UI 클래스(MaroSettingsPanel)는 다음 태스크에서 이
파일에 추가된다.
"""
import maya.cmds as cmds

_ROBOT_NAME_VAR = "maroSettingRosRobotName"
_DOMAIN_OVERRIDE_VAR = "maroSettingRosDomainIdOverride"
_DOMAIN_ID_VAR = "maroSettingRosDomainId"
_TECH_DIAG_THRESHOLD_VAR = "maroSettingTechDiagLimitProximityThreshold"

_DEFAULT_ROBOT_NAME = ""
_DEFAULT_DOMAIN_OVERRIDE = False
_DEFAULT_DOMAIN_ID = 0
_DEFAULT_TECH_DIAG_THRESHOLD = 0.9


def readRosSettings():
    """(robotName, domainIdOverrideEnabled, domainId) 튜플을 optionVar에서
    읽는다. 저장된 적 없으면 각각 기본값을 돌려준다."""
    robotName = (cmds.optionVar(query=_ROBOT_NAME_VAR)
                 if cmds.optionVar(exists=_ROBOT_NAME_VAR) else _DEFAULT_ROBOT_NAME)
    domainOverride = (bool(cmds.optionVar(query=_DOMAIN_OVERRIDE_VAR))
                       if cmds.optionVar(exists=_DOMAIN_OVERRIDE_VAR)
                       else _DEFAULT_DOMAIN_OVERRIDE)
    domainId = (cmds.optionVar(query=_DOMAIN_ID_VAR)
                if cmds.optionVar(exists=_DOMAIN_ID_VAR) else _DEFAULT_DOMAIN_ID)
    return robotName, domainOverride, domainId


def writeRosSettings(robotName, domainIdOverrideEnabled, domainId):
    """세 값을 optionVar에 쓴다."""
    cmds.optionVar(stringValue=(_ROBOT_NAME_VAR, robotName))
    cmds.optionVar(intValue=(_DOMAIN_OVERRIDE_VAR, 1 if domainIdOverrideEnabled else 0))
    cmds.optionVar(intValue=(_DOMAIN_ID_VAR, int(domainId)))


def readTechDiagThreshold():
    """리밋 근접 임계값(0.0-1.0)을 optionVar에서 읽는다. 없으면 0.9."""
    if cmds.optionVar(exists=_TECH_DIAG_THRESHOLD_VAR):
        return cmds.optionVar(query=_TECH_DIAG_THRESHOLD_VAR)
    return _DEFAULT_TECH_DIAG_THRESHOLD


def writeTechDiagThreshold(value):
    """리밋 근접 임계값을 optionVar에 쓴다."""
    cmds.optionVar(floatValue=(_TECH_DIAG_THRESHOLD_VAR, float(value)))
```

- [ ] **Step 2: `tests/maya/test_settings_panel.py` 작성**

이 프로젝트의 기존 순수 함수 테스트 관례(`tests/maya/test_tech_diag.py`)를 그대로 따른다 — `maya.standalone` 초기화 후 `python/` 소스 디렉터리를 `sys.path`에 직접 넣어 모듈을 소스에서 바로 import한다(스테이징된 사본이 아니라 — 스테이징은 Task 2의 CMake 변경 이후에만 존재한다).

```python
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
pluginDir = os.path.dirname(plugin)
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

_pythonDir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "python")
if _pythonDir not in sys.path:
    sys.path.insert(0, _pythonDir)

import maroSettingsPanel as settings  # noqa: E402

_ALL_VARS = [
    "maroSettingRosRobotName",
    "maroSettingRosDomainIdOverride",
    "maroSettingRosDomainId",
    "maroSettingTechDiagLimitProximityThreshold",
]


def _clearAllVars():
    for name in _ALL_VARS:
        if cmds.optionVar(exists=name):
            cmds.optionVar(remove=name)


_clearAllVars()

# --- readRosSettings: 아무것도 저장 안 됐을 때 기본값 ---
robotName, domainOverride, domainId = settings.readRosSettings()
assert robotName == "", robotName
assert domainOverride is False, domainOverride
assert domainId == 0, domainId
print("readRosSettings defaults OK")

# --- writeRosSettings + readRosSettings 왕복 ---
settings.writeRosSettings("myRobot", True, 42)
robotName, domainOverride, domainId = settings.readRosSettings()
assert robotName == "myRobot", robotName
assert domainOverride is True, domainOverride
assert domainId == 42, domainId
print("writeRosSettings/readRosSettings round-trip OK")

# --- 다른 값으로 덮어쓰기 ---
settings.writeRosSettings("otherRobot", False, 7)
robotName, domainOverride, domainId = settings.readRosSettings()
assert robotName == "otherRobot", robotName
assert domainOverride is False, domainOverride
assert domainId == 7, domainId
print("writeRosSettings overwrite OK")

# --- readTechDiagThreshold: 아무것도 저장 안 됐을 때 기본값 ---
_clearAllVars()
assert settings.readTechDiagThreshold() == 0.9, settings.readTechDiagThreshold()
print("readTechDiagThreshold default OK")

# --- writeTechDiagThreshold + readTechDiagThreshold 왕복 ---
settings.writeTechDiagThreshold(0.75)
value = settings.readTechDiagThreshold()
assert abs(value - 0.75) < 1e-6, value
print("writeTechDiagThreshold/readTechDiagThreshold round-trip OK")

_clearAllVars()
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
```

- [ ] **Step 3: `tests/CMakeLists.txt`에 새 테스트 등록**

`tests/CMakeLists.txt`의 `foreach(maya_test load axis_node ... lidar_menu skeleton_upload)` 목록(이 코드베이스에서 "플러그인만 있으면 되는" 테스트 그룹, `tests/CMakeLists.txt:284-293`) 끝에 `settings_panel`을 추가한다:

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
                      lidar_menu skeleton_upload settings_panel)
```

이 그룹의 다른 항목과 동일하게 `MARO_PLUGIN_PATH`/`MARO_DIAG_BOOK_DIR` 격리, `FIXTURES_REQUIRED MaroDiagBookRoot`, `TIMEOUT 240`을 자동으로 받는다(이 foreach 블록이 이미 처리 — 별도 설정 불필요).

- [ ] **Step 4: 빌드 후 새 테스트만 우선 실행**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure -R maya_settings_panel
```

Expected: `maya_settings_panel` PASS, 5개 print 라인 전부 출력(`readRosSettings defaults OK`부터 `teardown OK`까지).

- [ ] **Step 5: 전체 스위트로 회귀 확인**

```powershell
ctest --test-dir out/build -C Release --output-on-failure
```

Expected: 기존 테스트 전부 그대로 PASS(이 태스크는 새 파일 하나만 추가했을 뿐 기존 파일을 하나도 건드리지 않았으므로 회귀가 나오면 안 된다).

- [ ] **Step 6: 커밋**

```bash
git add python/maroSettingsPanel.py tests/maya/test_settings_panel.py tests/CMakeLists.txt
git commit -m "feat(settings): add optionVar read/write pure functions for Maro settings"
```

---

### Task 2: 환경설정 UI + 메뉴/teardown 배선 + Tech Diag 연동

**Files:**
- Modify: `python/maroSettingsPanel.py` (Task 1이 만든 파일에 UI 클래스 + `show()`/`stop()` 추가)
- Modify: `python/maroMenu.py:51-53`
- Modify: `src/maro_plugin/CMakeLists.txt:161-172` (`MARO_PLUGIN_PY_MODULES`에 `maroSettingsPanel` 추가)
- Modify: `python/maroMainWindow.py`의 `teardown()`(374-379번째 줄 부근, `maroLidarPanel.stop()` 블록 바로 다음)
- Modify: `python/maroTechDiag.py:25`(상수 근처), `:86-132`(`checkLimitProximity`), `:459-498`(`_runMayaSideChecks`)
- Modify: `tests/maya/test_settings_panel.py` (Task 1이 만든 파일에 스테이징 확인 추가)
- Modify: `tests/maya/test_tech_diag.py` (threshold 파라미터 회귀 테스트 추가)
- Modify: `docs/maro-main-ui-manual-checklist.md` (새 절 추가)

**Interfaces:**
- Consumes: Task 1의 `readRosSettings`/`writeRosSettings`/`readTechDiagThreshold`/`writeTechDiagThreshold`(같은 파일 안이므로 import 불필요, 그냥 호출).
- Produces: `maroSettingsPanel.show()`(모듈 함수, 인자 없음, 반환값 없음 — 메뉴가 호출), `maroSettingsPanel.stop()`(모듈 함수, 인자 없음 — `teardown()`이 호출). `maroTechDiag.checkLimitProximity(axisRows, capabilityRowsByAxis, currentValueByAxis, threshold=LIMIT_PROXIMITY_THRESHOLD)` — 기존 3-인자 호출은 전부 그대로 동작(새 4번째 인자는 키워드 기본값).

- [ ] **Step 1: `python/maroSettingsPanel.py`에 UI 클래스 추가**

파일 맨 위 import 줄을 다음으로 교체(기존 `import maya.cmds as cmds` 한 줄 위에 추가):

```python
import os

import maya.cmds as cmds
from PySide6 import QtCore, QtWidgets
```

Task 1의 네 함수 정의 뒤(파일 끝)에 다음을 추가한다:

```python
_OPEN_PANEL = None  # 열려 있는 MaroSettingsPanel 인스턴스, 없으면 None


def show():
    """maroMenu.py의 "환경설정..." 항목이 부른다. 이미 열려 있으면 앞으로
    가져온다."""
    global _OPEN_PANEL
    if _OPEN_PANEL is not None:
        try:
            _OPEN_PANEL.raise_()
            _OPEN_PANEL.activateWindow()
            return _OPEN_PANEL
        except RuntimeError:
            _OPEN_PANEL = None

    _OPEN_PANEL = MaroSettingsPanel()
    _OPEN_PANEL.show()
    return _OPEN_PANEL


def stop():
    """플러그인 언로드 시 열려 있는 설정 창을 닫는다. 한 번도 안 열렸어도
    안전한 무동작."""
    global _OPEN_PANEL
    if _OPEN_PANEL is not None:
        try:
            _OPEN_PANEL.close()
            _OPEN_PANEL.deleteLater()
        except Exception:  # noqa: BLE001 -- 언로드 정리 경계
            import traceback
            traceback.print_exc()
        _OPEN_PANEL = None


class MaroSettingsPanel(QtWidgets.QWidget):
    """Maro 환경설정 창. setStyleSheet()를 부르지 않는다."""

    def __init__(self, parent=None):
        super().__init__(parent, QtCore.Qt.Window)
        self.setWindowTitle("Maro 환경설정")

        layout = QtWidgets.QVBoxLayout(self)

        rosGroup = QtWidgets.QGroupBox("ROS 연결")
        rosForm = QtWidgets.QFormLayout(rosGroup)
        self._robotNameField = QtWidgets.QLineEdit()
        rosForm.addRow("robotName", self._robotNameField)
        self._domainOverrideCheck = QtWidgets.QCheckBox("도메인 ID 직접 지정")
        rosForm.addRow(self._domainOverrideCheck)
        self._domainIdField = QtWidgets.QSpinBox()
        self._domainIdField.setRange(0, 232)
        rosForm.addRow("도메인 ID", self._domainIdField)
        self._domainOverrideCheck.toggled.connect(self._domainIdField.setEnabled)
        rosButtons = QtWidgets.QHBoxLayout()
        connectButton = QtWidgets.QPushButton("연결")
        connectButton.clicked.connect(self._onConnect)
        disconnectButton = QtWidgets.QPushButton("연결 해제")
        disconnectButton.clicked.connect(self._onDisconnect)
        rosButtons.addWidget(connectButton)
        rosButtons.addWidget(disconnectButton)
        rosForm.addRow(rosButtons)
        rosForm.addRow(QtWidgets.QLabel("연결 버튼을 누르면 즉시 적용됩니다."))
        layout.addWidget(rosGroup)

        techDiagGroup = QtWidgets.QGroupBox("Tech Diag")
        techDiagForm = QtWidgets.QFormLayout(techDiagGroup)
        self._thresholdField = QtWidgets.QSpinBox()
        self._thresholdField.setRange(0, 100)
        self._thresholdField.setSuffix("%")
        techDiagForm.addRow("리밋 근접 경고 임계값", self._thresholdField)
        saveThresholdButton = QtWidgets.QPushButton("저장")
        saveThresholdButton.clicked.connect(self._onSaveThreshold)
        techDiagForm.addRow(saveThresholdButton)
        techDiagForm.addRow(QtWidgets.QLabel("다음 검사 실행부터 즉시 적용됩니다."))
        layout.addWidget(techDiagGroup)

        self._loadValues()

    def _loadValues(self):
        robotName, domainOverride, domainId = readRosSettings()
        self._robotNameField.setText(robotName)
        self._domainOverrideCheck.setChecked(domainOverride)
        self._domainIdField.setValue(domainId)
        self._domainIdField.setEnabled(domainOverride)
        self._thresholdField.setValue(int(round(readTechDiagThreshold() * 100)))

    def _onConnect(self):
        try:
            robotName = self._robotNameField.text()
            if not robotName:
                cmds.warning("Maro: enter a robot name before connecting.")
                return
            overrideEnabled = self._domainOverrideCheck.isChecked()
            domainId = self._domainIdField.value()
            writeRosSettings(robotName, overrideEnabled, domainId)
            if overrideEnabled:
                os.environ["ROS_DOMAIN_ID"] = str(domainId)
            cmds.maroStartBridge(robotName)
        except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
            cmds.warning("Maro: failed to connect: {}".format(exc))

    def _onDisconnect(self):
        try:
            cmds.maroStopBridge()
        except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
            cmds.warning("Maro: failed to disconnect: {}".format(exc))

    def _onSaveThreshold(self):
        try:
            writeTechDiagThreshold(self._thresholdField.value() / 100.0)
        except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
            cmds.warning("Maro: failed to save Tech Diag threshold: {}".format(exc))

    def closeEvent(self, event):
        global _OPEN_PANEL
        if _OPEN_PANEL is self:
            _OPEN_PANEL = None
        super().closeEvent(event)
```

- [ ] **Step 2: `python/maroMenu.py`의 두 자리표시자를 활성 항목 하나로 교체**

`python/maroMenu.py:51-53`의 현재 내용:

```python
    cmds.menuItem(divider=True, parent=MENU_NAME)
    cmds.menuItem(label="ROS 연결 설정 (준비 중)", enable=False, parent=MENU_NAME)
    cmds.menuItem(label="환경설정 (준비 중)", enable=False, parent=MENU_NAME)
```

다음으로 교체한다:

```python
    cmds.menuItem(divider=True, parent=MENU_NAME)
    cmds.menuItem(label="환경설정...",
                  command="import maroSettingsPanel\nmaroSettingsPanel.show()",
                  parent=MENU_NAME)
```

- [ ] **Step 3: `src/maro_plugin/CMakeLists.txt`에 새 모듈 스테이징 등록**

`src/maro_plugin/CMakeLists.txt:161-172`의 `MARO_PLUGIN_PY_MODULES` 목록:

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

`maroRosProxy`와 `maroSkeletonUpload` 사이에 `maroSettingsPanel`을 추가한다:

```cmake
set(MARO_PLUGIN_PY_MODULES
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
    maroTechDiag
)
```

이게 없으면 `import maroSettingsPanel`이 플러그인 설치 디렉터리에서 파일을 찾지 못해 메뉴 클릭 시 `ImportError`가 난다 — 이 태스크의 가장 흔한 실수 지점이다.

- [ ] **Step 4: `python/maroMainWindow.py`의 `teardown()`에 다섯 번째 서브시스템 등록**

`python/maroMainWindow.py`의 `maroLidarPanel.stop()` 블록(374-379번째 줄) 바로 다음에 추가한다:

```python
    try:
        import maroSettingsPanel
        maroSettingsPanel.stop()
    except Exception:  # noqa: BLE001 -- Maya 콜백/언로드 경계
        import traceback
        traceback.print_exc()
```

- [ ] **Step 5: `python/maroTechDiag.py`에 threshold 파라미터 추가**

`python/maroTechDiag.py:86-89`의 현재 시그니처/독스트링:

```python
def checkLimitProximity(axisRows, capabilityRowsByAxis, currentValueByAxis):
    """리밋(capType 1 또는 5)이 있는 축마다, 현재 구동값이 min/max 범위의
    LIMIT_PROXIMITY_THRESHOLD 이상 근접했으면 경고를 낸다. conventionAxis로
    capMin/capMax/capEnable의 X/Y/Z 중 어느 성분이 이 축에 해당하는지 고른다."""
```

다음으로 교체한다(키워드 인자 하나 추가, 기본값은 기존 상수 — 기존 3-인자 호출부는 전부 그대로 동작한다):

```python
def checkLimitProximity(axisRows, capabilityRowsByAxis, currentValueByAxis,
                         threshold=LIMIT_PROXIMITY_THRESHOLD):
    """리밋(capType 1 또는 5)이 있는 축마다, 현재 구동값이 min/max 범위의
    threshold 이상 근접했으면 경고를 낸다. conventionAxis로
    capMin/capMax/capEnable의 X/Y/Z 중 어느 성분이 이 축에 해당하는지 고른다.
    threshold를 생략하면 LIMIT_PROXIMITY_THRESHOLD(기본 0.9)를 쓴다 --
    이 함수는 여전히 Maya를 부르지 않는 순수 함수다. maroSettingsPanel이
    저장한 사용자 설정값은 이 함수가 아니라 호출자(_runMayaSideChecks)가
    _limitProximityThreshold()로 읽어서 넘긴다."""
```

같은 함수 안, `:108-109`의:

```python
            nearMax = proximity >= LIMIT_PROXIMITY_THRESHOLD
            nearMin = proximity <= (1.0 - LIMIT_PROXIMITY_THRESHOLD)
```

를:

```python
            nearMax = proximity >= threshold
            nearMin = proximity <= (1.0 - threshold)
```

로, `:127`의:

```python
                            (1.0 - LIMIT_PROXIMITY_THRESHOLD) * 100,
```

를:

```python
                            (1.0 - threshold) * 100,
```

로 바꾼다.

- [ ] **Step 6: `_limitProximityThreshold()` 헬퍼 추가, `_runMayaSideChecks()`가 사용하도록 배선**

`python/maroTechDiag.py`의 `_runMayaSideChecks` 함수(459번째 줄) 바로 위에 새 함수를 추가한다:

```python
def _limitProximityThreshold():
    """maroSettingsPanel이 저장한 리밋 근접 임계값을 optionVar에서 읽는다.
    저장된 적 없으면 LIMIT_PROXIMITY_THRESHOLD(기본 0.9). checkLimitProximity()
    자신은 이 함수를 부르지 않는다 -- 그 함수의 "Maya를 부르지 않는다"는
    계약(순수 함수, 기존 mayapy 배치 테스트가 이미 이걸 전제한다)을 지키기
    위해, optionVar를 읽는 이 한 곳만 Maya를 부르고 그 결과를 인자로
    넘긴다."""
    if cmds.optionVar(exists="maroSettingTechDiagLimitProximityThreshold"):
        return cmds.optionVar(query="maroSettingTechDiagLimitProximityThreshold")
    return LIMIT_PROXIMITY_THRESHOLD
```

`:484`의 현재 호출:

```python
    findings = checkLimitProximity(axisRows, capsByAxis, currentValueByAxis)
```

를:

```python
    findings = checkLimitProximity(axisRows, capsByAxis, currentValueByAxis,
                                    threshold=_limitProximityThreshold())
```

로 바꾼다.

- [ ] **Step 7: `tests/maya/test_settings_panel.py`에 스테이징 확인 추가**

Task 1이 만든 파일의 `_clearAllVars()` 첫 호출 **앞**(플러그인 로드 직후)에 다음을 추가한다 — `tests/maya/test_main_menu.py`의 기존 스테이징 확인과 같은 패턴:

```python
# CMake가 .py를 .mll 옆에 스테이징했는가(MARO_PLUGIN_PY_MODULES).
stagedModule = os.path.join(pluginDir, "maroSettingsPanel.py")
assert os.path.isfile(stagedModule), (
    f"maroSettingsPanel.py must be staged next to the plug-in, not found at {stagedModule}"
)
print("module staged next to the plug-in OK")
```

- [ ] **Step 8: `tests/maya/test_tech_diag.py`에 threshold 파라미터 회귀 테스트 추가**

기존 `checkLimitProximity` 테스트 블록(`# --- checkLimitProximity ---`로 시작, `print("checkLimitProximity OK")`로 끝남) 바로 뒤에 추가한다:

```python
# --- checkLimitProximity: threshold 파라미터가 실제로 판정을 바꾼다 ---
# 90%(기본값)로는 안 걸리지만 50%로는 걸리는 값을 고른다.
midRangeAxisRows = [{"axisFullPath": "|axis1", "jointName": "j1", "boundTargetPath": "|cube1",
                      "enabled": True, "conventionAxis": 0, "capabilityCount": 1}]
midRangeCaps = {"|axis1": [{"logicalIndex": 0, "capType": 1,
                            "capMin": (0.0, 0.0, 0.0), "capMax": (10.0, 0.0, 0.0),
                            "capEnable": (True, False, False)}]}
defaultFindings = diag.checkLimitProximity(midRangeAxisRows, midRangeCaps, {"|axis1": 6.0})
assert defaultFindings == [], defaultFindings  # 60%는 기본 90% 임계값 밖
lowThresholdFindings = diag.checkLimitProximity(
    midRangeAxisRows, midRangeCaps, {"|axis1": 6.0}, threshold=0.5)
assert len(lowThresholdFindings) == 1, lowThresholdFindings  # 60% >= 50% 임계값
print("checkLimitProximity threshold parameter OK")

# --- _limitProximityThreshold(): optionVar 왕복 ---
_THRESHOLD_VAR = "maroSettingTechDiagLimitProximityThreshold"
if cmds.optionVar(exists=_THRESHOLD_VAR):
    cmds.optionVar(remove=_THRESHOLD_VAR)
assert diag._limitProximityThreshold() == 0.9, diag._limitProximityThreshold()
cmds.optionVar(floatValue=(_THRESHOLD_VAR, 0.6))
assert abs(diag._limitProximityThreshold() - 0.6) < 1e-6, diag._limitProximityThreshold()
cmds.optionVar(remove=_THRESHOLD_VAR)
print("_limitProximityThreshold OK")
```

- [ ] **Step 9: `docs/maro-main-ui-manual-checklist.md`에 새 절 추가**

파일 끝에 다음 절을 추가한다:

`````markdown

## Maro 환경설정 창

인터랙티브 Maya 2026에서 `maro.mll`을 로드하고 MaroUI를 연 뒤, Maro 메뉴에서
"환경설정..."을 클릭한다.

- [ ] **창이 뜨고 값이 로드된다** — 이전에 저장된 값이 없으면 robotName
      빈 칸, 도메인 ID 직접 지정 체크박스 꺼짐, 리밋 근접 임계값 90%로
      뜨는지 확인한다.
- [ ] **체크박스가 스핀박스를 잠근다/푼다** — "도메인 ID 직접 지정" 체크를
      켜고 끌 때 도메인 ID 스핀박스가 활성/비활성으로 바뀌는지 확인한다.
- [ ] **비모달이다** — 이 창을 띄운 채로 MaroUI의 다른 부분(뷰포트 회전,
      ONE 그리드 클릭 등)을 조작할 수 있는지 확인한다.
- [ ] **도메인 ID 미지정 연결** — robotName만 채우고(체크박스는 끈 채로)
      "연결"을 누른다. Script Editor에 ROS 연결 성공 메시지가 뜨는지
      확인한다.
- [ ] **[go/no-go] 도메인 ID가 실제로 반영된다** — "연결 해제"를 누른 뒤,
      "도메인 ID 직접 지정"을 켜고 임의의 값(예: 77)을 넣은 뒤 "연결"을
      누른다. 별도 터미널에서 `ROS_DOMAIN_ID=77 ros2 topic list`를 실행해
      Maro가 발행하는 토픽(`/<robotName>/joint_states` 등)이 그 도메인에서만
      보이고, 다른 도메인(예: 기본값 0)에서는 안 보이는지 확인한다. 이게
      안 되면 `os.environ["ROS_DOMAIN_ID"]` 경유 방식 자체를 재검토해야
      한다(설계 스펙 §3.5, 이번 계획의 Global Constraints 참고).
- [ ] **로봇 이름 없이 연결 시도** — robotName을 비운 채 "연결"을 누른다.
      `cmds.maroStartBridge`가 호출되지 않고 "enter a robot name" 경고만
      뜨는지 확인한다.
- [ ] **Tech Diag 임계값 저장이 다음 검사부터 적용된다** — 임계값을 50%로
      낮추고 "저장"을 누른다. 리밋에 60% 근접한 축을 하나 만들고(예:
      `capMin=0, capMax=10`인 리밋에 구동값 6) Maya측 Tech Diag 검사를
      실행해 리밋 근접 경고가 뜨는지 확인한다(90% 기본값이었다면 안 떴을
      경우).
- [ ] **창을 연 채 언로드** — 창이 열린 상태에서 `unloadPlugin maro`를
      실행한다. Maya가 크래시하지 않고 창이 닫히는지 확인한다.
- [ ] **재시작 후 값이 유지된다** — 로봇 이름/도메인 ID/임계값을 원하는
      값으로 바꾸고 창을 닫은 뒤 Maya를 완전히 재시작하고 플러그인을 다시
      로드한다. "환경설정..."을 다시 열어 방금 설정한 값이 그대로
      남아 있는지 확인한다(`optionVar`가 영구 저장소임을 확인하는 항목).
`````

- [ ] **Step 10: 빌드 후 전체 테스트 스위트 실행**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure
```

Expected: 빌드 성공, 전체 테스트 스위트가 이전과 동일하게(Task 1이 늘린 1개 포함) 전부 PASS. `maya_settings_panel`이 새 스테이징 확인 줄까지 통과하는지, `maya_tech_diag`가 새 threshold 테스트까지 통과하는지 확인한다.

- [ ] **Step 11: 커밋**

```bash
git add python/maroSettingsPanel.py python/maroMenu.py python/maroMainWindow.py \
        python/maroTechDiag.py src/maro_plugin/CMakeLists.txt \
        tests/maya/test_settings_panel.py tests/maya/test_tech_diag.py \
        docs/maro-main-ui-manual-checklist.md
git commit -m "feat(settings): add Maro settings panel UI, ROS connect/disconnect, Tech Diag threshold wiring"
```
