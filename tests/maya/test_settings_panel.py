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


# CMake가 .py를 .mll 옆에 스테이징했는가(MARO_PLUGIN_PY_MODULES).
stagedModule = os.path.join(pluginDir, "maroSettingsPanel.py")
assert os.path.isfile(stagedModule), (
    f"maroSettingsPanel.py must be staged next to the plug-in, not found at {stagedModule}"
)
print("module staged next to the plug-in OK")

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

# 설계 스펙 §4.2: setStyleSheet()를 부르지 않는다 -- Maya 프로세스 전역
# QApplication의 팔레트/스타일을 그대로 물려받아야 기존 mayaUI와 이질감이
# 없다. test_main_window.py/test_object_node_editor.py/test_ros_proxy_sync.py/
# test_single_object_node_editor.py와 같은 관례를 이 모듈에도 적용한다.
with open(stagedModule, encoding="utf-8") as handle:
    source = handle.read()
assert ".setStyleSheet(" not in source, (
    "maroSettingsPanel.py must not call setStyleSheet() -- it has to inherit "
    "Maya's global Qt style (design spec 4.2)"
)
print("no setStyleSheet OK")

_clearAllVars()
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
