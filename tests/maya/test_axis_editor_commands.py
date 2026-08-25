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
