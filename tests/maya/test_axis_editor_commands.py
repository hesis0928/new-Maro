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

# --- maroAddCapability ---
axisAdd = cmds.createNode("maroAxis", name="addAxis1")
newRot = cmds.maroAddCapability(axisAdd, type="rotation")[0]
assert cmds.nodeType(newRot) == "maroRotation", f"maroAddCapability must create the requested type, got {cmds.nodeType(newRot)}"
caps = cmds.maroListAxisNodes(capabilities=axisAdd)
assert len(caps) // CAPABILITY_FIELDS == 1, "maroAddCapability must connect the new node"
cmds.undo()
caps = cmds.maroListAxisNodes(capabilities=axisAdd)
assert len(caps) == 0 or all(c == "" for c in caps[1:3]), \
    "undo of maroAddCapability must remove the connection"
assert not cmds.objExists(newRot), "undo of maroAddCapability must remove the created node too"
print("maroAddCapability + undo OK")

cmds.maroAddCapability(axisAdd, type="rotation")
try:
    cmds.maroAddCapability(axisAdd, type="translation")
    raised = False
except RuntimeError:
    raised = True
assert raised, "adding a second primary-driver type must be rejected (§3 mutual exclusivity)"
print("maroAddCapability mutual-exclusivity rejection OK")

try:
    cmds.maroAddCapability(axisAdd, type="bogusType")
    raised = False
except RuntimeError:
    raised = True
assert raised, "maroAddCapability with an unknown -type must fail"
print("maroAddCapability unknown-type rejection OK")

# --- maroConnectCapability ---
axisConn = cmds.createNode("maroAxis", name="connAxis1")
freeRot = cmds.createNode("maroRotation", name="connRot1")
cmds.maroConnectCapability(freeRot, axisConn)
caps = cmds.maroListAxisNodes(capabilities=axisConn)
assert caps[1].endswith("connRot1"), "maroConnectCapability must connect the given node"
cmds.undo()
caps = cmds.maroListAxisNodes(capabilities=axisConn)
assert len(caps) == 0 or caps[4] == "0", "undo of maroConnectCapability must disconnect"
print("maroConnectCapability + undo OK")

cmds.maroConnectCapability(freeRot, axisConn)
freeRot2 = cmds.createNode("maroRotation", name="connRot2")
try:
    cmds.maroConnectCapability(freeRot2, axisConn)
    raised = False
except RuntimeError:
    raised = True
assert raised, "connecting a second primary-driver type must be rejected"
print("maroConnectCapability mutual-exclusivity rejection OK")

alreadyBound = cmds.createNode("maroAxis", name="connAxis2")
try:
    cmds.maroConnectCapability(freeRot, alreadyBound)
    raised = False
except RuntimeError:
    raised = True
assert raised, "connecting a capability node that's already connected elsewhere must be rejected"
print("maroConnectCapability already-connected rejection OK")

# --- maroDisconnectCapability ---
cmds.maroDisconnectCapability(axisConn, index=0)
caps = cmds.maroListAxisNodes(capabilities=axisConn)
assert caps[4] == "0", "maroDisconnectCapability must leave the slot disconnected"
cmds.undo()
caps = cmds.maroListAxisNodes(capabilities=axisConn)
assert caps[4] == "1", "undo of maroDisconnectCapability must restore the connection"
print("maroDisconnectCapability + undo OK")

try:
    cmds.maroDisconnectCapability(axisConn, index=99)
    raised = False
except RuntimeError:
    raised = True
assert raised, "disconnecting an unoccupied index must fail"
print("maroDisconnectCapability not-connected rejection OK")

# --- maroUnbindAxis ---
axisUnbind = cmds.createNode("maroAxis", name="unbindAxis1")
cubeUnbind = cmds.polyCube(name="unbindCube1")[0]
cmds.maroBindAxis(axisUnbind, cubeUnbind)
cmds.maroUnbindAxis(axisUnbind)
rows = cmds.maroListAxisNodes()
for i in range(len(rows) // AXIS_FIELDS):
    f = rows[i * AXIS_FIELDS:(i + 1) * AXIS_FIELDS]
    if f[0].endswith("unbindAxis1"):
        assert f[2] == "", f"maroUnbindAxis must clear boundTargetPath (got {f[2]})"
        break
cmds.undo()
rows = cmds.maroListAxisNodes()
for i in range(len(rows) // AXIS_FIELDS):
    f = rows[i * AXIS_FIELDS:(i + 1) * AXIS_FIELDS]
    if f[0].endswith("unbindAxis1"):
        assert f[2].endswith("unbindCube1"), "undo of maroUnbindAxis must restore the binding"
        break
print("maroUnbindAxis + undo OK")

try:
    cmds.maroUnbindAxis(axisUnbind)  # 이미 위 undo로 복구됐다가 다시 unbind 안 한 상태 -- 실제로는 bound 상태
    cmds.maroUnbindAxis(axisUnbind)  # 두 번째 호출은 이미 unbind됨 -> 실패해야 함
    raised = False
except RuntimeError:
    raised = True
assert raised, "maroUnbindAxis on an already-unbound axis must fail"
print("maroUnbindAxis not-bound rejection OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
