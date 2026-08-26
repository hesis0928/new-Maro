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

_pythonDir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "python")
if _pythonDir not in sys.path:
    sys.path.insert(0, _pythonDir)

import maroTechDiag as diag

# --- sliceAxisTechRows ---
flat = ["|axis1", "joint1", "|cube1", "", "0", "1", "1", "2", "Axis One", "0.2,0.6,0.9"]
rows = diag.sliceAxisTechRows(flat)
assert len(rows) == 1, rows
assert rows[0] == {
    "axisFullPath": "|axis1", "jointName": "joint1", "boundTargetPath": "|cube1",
    "enabled": True, "conventionAxis": 1, "capabilityCount": 2,
}, rows[0]
assert diag.sliceAxisTechRows(None) == []
try:
    diag.sliceAxisTechRows(["too", "few"])
    assert False, "expected ValueError for a non-multiple-of-10 array"
except ValueError:
    pass
print("sliceAxisTechRows OK")

# --- sliceCapabilityTechRows ---
capFlat = ["0", "cap1", "maroLimit", "1", "1", "1", "", "", "3", "0"]
capRows = diag.sliceCapabilityTechRows(capFlat)
assert capRows == [
    {"logicalIndex": 0, "capType": 1, "connected": True},
    {"logicalIndex": 1, "capType": 3, "connected": False},
], capRows
print("sliceCapabilityTechRows OK")

# --- checkLimitProximity ---
axisRows = [{"axisFullPath": "|axis1", "jointName": "j1", "boundTargetPath": "|cube1",
             "enabled": True, "conventionAxis": 0, "capabilityCount": 1}]
capsByAxis = {"|axis1": [{"logicalIndex": 0, "capType": 1,
                          "capMin": (0.0, 0.0, 0.0), "capMax": (10.0, 0.0, 0.0),
                          "capEnable": (True, False, False)}]}
# Value at 95% of the [0, 10] range on the X component (conventionAxis=0).
findings = diag.checkLimitProximity(axisRows, capsByAxis, {"|axis1": 9.5})
assert len(findings) == 1, findings
assert findings[0]["axis"] == "|axis1"
assert findings[0]["category"] == "limitProximity"
assert findings[0]["remedy"] is None
# Value safely in the middle -> no finding.
findings = diag.checkLimitProximity(axisRows, capsByAxis, {"|axis1": 5.0})
assert findings == [], findings
# The relevant capEnable component is False -> never flagged regardless of value.
capsByAxisDisabled = {"|axis1": [{"logicalIndex": 0, "capType": 1,
                                  "capMin": (0.0, 0.0, 0.0), "capMax": (10.0, 0.0, 0.0),
                                  "capEnable": (False, True, True)}]}
findings = diag.checkLimitProximity(axisRows, capsByAxisDisabled, {"|axis1": 9.9})
assert findings == [], findings
# Zero-width range is skipped, not a division-by-zero crash.
capsByAxisZero = {"|axis1": [{"logicalIndex": 0, "capType": 1,
                              "capMin": (5.0, 0.0, 0.0), "capMax": (5.0, 0.0, 0.0),
                              "capEnable": (True, False, False)}]}
findings = diag.checkLimitProximity(axisRows, capsByAxisZero, {"|axis1": 5.0})
assert findings == [], findings
print("checkLimitProximity OK")

# --- checkJointStatesIntegrity ---
rowsEmpty = [{"axisFullPath": "|a1", "jointName": "", "boundTargetPath": "|c1",
              "enabled": True, "conventionAxis": 0, "capabilityCount": 1}]
findings = diag.checkJointStatesIntegrity(rowsEmpty)
assert len(findings) == 1 and findings[0]["category"] == "emptyJointName", findings
assert findings[0]["remedy"] is None  # remedies attached by Task 3, not this pure function

rowsDup = [
    {"axisFullPath": "|a1", "jointName": "shoulder", "boundTargetPath": "|c1",
     "enabled": True, "conventionAxis": 0, "capabilityCount": 1},
    {"axisFullPath": "|a2", "jointName": "shoulder", "boundTargetPath": "|c2",
     "enabled": True, "conventionAxis": 0, "capabilityCount": 1},
]
findings = diag.checkJointStatesIntegrity(rowsDup)
assert len(findings) == 1 and findings[0]["category"] == "duplicateJointName", findings
assert findings[0]["axis"] == "|a2", "the later-encountered axis is the one flagged"

rowsNoDriver = [{"axisFullPath": "|a1", "jointName": "elbow", "boundTargetPath": "|c1",
                 "enabled": True, "conventionAxis": 0, "capabilityCount": 0}]
findings = diag.checkJointStatesIntegrity(rowsNoDriver)
assert len(findings) == 1 and findings[0]["category"] == "noDriverActiveAxis", findings

rowsDisabled = [{"axisFullPath": "|a1", "jointName": "", "boundTargetPath": "",
                 "enabled": False, "conventionAxis": 0, "capabilityCount": 0}]
assert diag.checkJointStatesIntegrity(rowsDisabled) == [], "disabled axes are never flagged"

rowsUnbound = [{"axisFullPath": "|a1", "jointName": "", "boundTargetPath": "",
                "enabled": True, "conventionAxis": 0, "capabilityCount": 0}]
assert diag.checkJointStatesIntegrity(rowsUnbound) == [], "unbound axes are never flagged"

print("checkJointStatesIntegrity OK")

# --- checkMeshCollisions ---
boxes = {
    "|cubeA": (0.0, 0.0, 0.0, 2.0, 2.0, 2.0),
    "|cubeB": (1.0, 1.0, 1.0, 3.0, 3.0, 3.0),   # overlaps cubeA
    "|cubeC": (10.0, 10.0, 10.0, 12.0, 12.0, 12.0),  # far away, no overlap
}
findings = diag.checkMeshCollisions(boxes)
assert len(findings) == 1, findings
assert findings[0]["category"] == "meshCollision"
assert findings[0]["axis"] is None
assert set(findings[0]["meshes"]) == {"|cubeA", "|cubeB"}
assert findings[0]["remedy"] is None

# Touching-but-not-overlapping boxes (shared face) must NOT be flagged.
touchingBoxes = {
    "|cubeD": (0.0, 0.0, 0.0, 1.0, 1.0, 1.0),
    "|cubeE": (1.0, 0.0, 0.0, 2.0, 1.0, 1.0),
}
assert diag.checkMeshCollisions(touchingBoxes) == [], "exactly-touching boxes should not count as a collision"

assert diag.checkMeshCollisions({}) == []
assert diag.checkMeshCollisions({"|onlyOne": (0.0, 0.0, 0.0, 1.0, 1.0, 1.0)}) == []
print("checkMeshCollisions OK")

# --- suggestDisambiguatedJointName (pure) ---
assert diag.suggestDisambiguatedJointName("shoulder") == "shoulder_2"
print("suggestDisambiguatedJointName OK")

# --- remedyFillEmptyJointName + undo ---
cube = cmds.polyCube(name="techDiagCube1")[0]
axis = cmds.createNode("maroAxis", name="techDiagAxis1")
cmds.maroBindAxis(axis, cube)
# A freshly-created maroAxis.jointName has no MFnStringData default, so
# cmds.getAttr() on it returns Python None, not "" -- confirmed empirically
# against the built plugin. Accept either as "empty" rather than asserting
# a specific one, since which one Maya gives you here is an implementation
# detail of an unset string attribute, not a contract this module defines.
assert not cmds.getAttr(axis + ".jointName"), "precondition: jointName starts empty"

suggestion = diag.suggestJointNameForFill(axis)
assert suggestion == "techDiagCube1", suggestion

diag.remedyFillEmptyJointName(axis)
assert cmds.getAttr(axis + ".jointName") == "techDiagCube1"
cmds.undo()
assert not cmds.getAttr(axis + ".jointName"), "undo must revert the fill"
print("remedyFillEmptyJointName OK")

# --- remedyRenameDuplicateJointName + undo ---
axis2 = cmds.createNode("maroAxis", name="techDiagAxis2")
cmds.setAttr(axis2 + ".jointName", "shoulder", type="string")
diag.remedyRenameDuplicateJointName(axis2, "shoulder_2")
assert cmds.getAttr(axis2 + ".jointName") == "shoulder_2"
cmds.undo()
assert cmds.getAttr(axis2 + ".jointName") == "shoulder", "undo must revert the rename"
print("remedyRenameDuplicateJointName OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
sys.exit(0)
