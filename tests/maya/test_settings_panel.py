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
