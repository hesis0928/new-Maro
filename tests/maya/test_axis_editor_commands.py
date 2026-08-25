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

rowsBeforeBadIndex = cmds.maroListAxisNodes(capabilities=axisConn)
try:
    cmds.maroDisconnectCapability(axisConn, index=99)
    raised = False
except RuntimeError:
    raised = True
assert raised, "disconnecting an unoccupied index must fail"
print("maroDisconnectCapability not-connected rejection OK")

# --- 리뷰 Finding I-3: 잘못된 -index가 유령 슬롯을 만들면 안 된다 ---
# 커맨드가 raise했다는 것만 확인하면 부작용을 놓친다 -- 반드시 다시
# 조회해서 확인한다. (실측 메모: 리뷰가 예상한 증상 자체는 Maya 2026에서
# 재현되지 않았다. 값도 연결도 없는 원소는 evaluateNumElements()에 안
# 잡힌다. 이 단언은 그 동작에 의존하지 않겠다는 계약을 못 박는 것이다.)
rowsAfterBadIndex = cmds.maroListAxisNodes(capabilities=axisConn)
assert len(rowsAfterBadIndex) == len(rowsBeforeBadIndex), (
    "a rejected -index must not materialize a new capabilityIn element; "
    f"rows went from {len(rowsBeforeBadIndex) // CAPABILITY_FIELDS} to "
    f"{len(rowsAfterBadIndex) // CAPABILITY_FIELDS}"
)
phantomIndices = [rowsAfterBadIndex[i * CAPABILITY_FIELDS]
                  for i in range(len(rowsAfterBadIndex) // CAPABILITY_FIELDS)]
assert "99" not in phantomIndices, (
    f"a phantom capabilityIn[99] row appeared after a rejected -index: {phantomIndices}"
)
print("maroDisconnectCapability bad -index leaves no phantom slot (I-3) OK")

# --- 리뷰 Finding I-1: 각도/선형 능력을 한 축에 섞을 수 없다 ---
# (a) 직선 구동 축에 각도 리밋(maroLimit, +-pi 라디안)을 얹으면 25cm가
#     조용히 3.14로 잘린다. 막아야 한다.
axisFamLin = cmds.createNode("maroAxis", name="famLinearAxis")
cmds.maroAddCapability(axisFamLin, type="translation")
try:
    cmds.maroAddCapability(axisFamLin, type="limit")
    raised = False
except RuntimeError:
    raised = True
assert raised, "an angular limit on a translation-driven axis must be rejected (I-1)"

# (b) 반대 방향. 회전축에 +-10cm 리밋은 +-10라디안(=+-573도)이라 사실상
#     아무 일도 안 하는데, 그게 "동작한다"로 오해되기 쉽다.
axisFamRot = cmds.createNode("maroAxis", name="famRotAxis")
cmds.maroAddCapability(axisFamRot, type="rotation")
try:
    cmds.maroAddCapability(axisFamRot, type="translationLimit")
    raised = False
except RuntimeError:
    raised = True
assert raised, "a linear limit on a rotation-driven axis must be rejected (I-1)"

# (c) 올바른 짝은 그대로 붙는다 (회귀 확인).
cmds.maroAddCapability(axisFamLin, type="translationLimit")
cmds.maroAddCapability(axisFamRot, type="limit")
assert len(cmds.maroListAxisNodes(capabilities=axisFamLin)) // CAPABILITY_FIELDS == 2, \
    "translation + translationLimit must still be allowed"
assert len(cmds.maroListAxisNodes(capabilities=axisFamRot)) // CAPABILITY_FIELDS == 2, \
    "rotation + limit must still be allowed"

# (d) 센서는 계열 중립 -- 어느 축에나 붙는다.
cmds.maroAddCapability(axisFamLin, type="sensorRange")
cmds.maroAddCapability(axisFamRot, type="sensorDirection")
assert len(cmds.maroListAxisNodes(capabilities=axisFamLin)) // CAPABILITY_FIELDS == 3, \
    "sensors are family-neutral and must attach to a linear axis"
assert len(cmds.maroListAxisNodes(capabilities=axisFamRot)) // CAPABILITY_FIELDS == 3, \
    "sensors are family-neutral and must attach to an angular axis"
print("maroAddCapability angular/linear family check (I-1) OK")

# (e) maroConnectCapability도 같은 규칙을 따른다. 이쪽은 표의 기본값이
#     아니라 노드가 실제로 내는 capabilityOut.capType을 읽는다.
axisFamConn = cmds.createNode("maroAxis", name="famConnAxis")
cmds.maroAddCapability(axisFamConn, type="rotation")
freeTransLim = cmds.createNode("maroTranslationLimit", name="famFreeTransLim")
try:
    cmds.maroConnectCapability(freeTransLim, axisFamConn)
    raised = False
except RuntimeError:
    raised = True
assert raised, "maroConnectCapability must apply the same family check (I-1)"

# maroCoupling은 outputIsLinear에 따라 capType 6/7로 갈린다 -- 연결 경로가
# 표의 기본값이 아니라 실제 capType을 읽는지 증명한다.
axisFamCoupleLin = cmds.createNode("maroAxis", name="famCoupleLinAxis")
cmds.maroAddCapability(axisFamCoupleLin, type="translation")
couplingLinear = cmds.createNode("maroCoupling", name="famCouplingLinear")
cmds.setAttr(couplingLinear + ".outputIsLinear", True)   # capType 7 = 선형
assert cmds.getAttr(couplingLinear + ".capabilityOut.capType") == 7
# 계열은 맞지만(선형+선형) 이미 primary driver가 있으므로 상호배타로 막힌다.
try:
    cmds.maroConnectCapability(couplingLinear, axisFamCoupleLin)
    raised = False
except RuntimeError:
    raised = True
assert raised, "a second primary driver must still be rejected"

# 같은 선형 coupling을 각도 축에 붙이면 계열 불일치로 막혀야 한다.
axisFamCoupleRot = cmds.createNode("maroAxis", name="famCoupleRotAxis")
limOnlyRot = cmds.createNode("maroLimit", name="famLimOnlyRot")
cmds.maroConnectCapability(limOnlyRot, axisFamCoupleRot)   # capType 1, 각도
try:
    cmds.maroConnectCapability(couplingLinear, axisFamCoupleRot)
    raised = False
except RuntimeError:
    raised = True
assert raised, "a linear coupling (capType 7) must be rejected on an angular axis (I-1)"
print("maroConnectCapability angular/linear family check (I-1) OK")

# --- 리뷰 Finding I-4: 상호배타 검사가 "연결을 통해 끌어온 실제 값"을 ---
# --- 읽는다는 증거. aCapType의 어트리뷰트 기본값이 0인데 0은 동시에    ---
# --- "rotation"(primary driver)이기도 하다. 기존 테스트는 전부 회전을  ---
# --- 스택 맨 앞에 놓아서, 만약 asShort()가 연결값이 아니라 미평가       ---
# --- 기본값을 돌려줘도 우연히 통과한다.                                 ---
# (a) primary driver가 아닌 maroLimit(capType 1)을 슬롯 0에 먼저 꽂은 뒤
#     rotation을 추가한다 -- 반드시 "성공"해야 한다. 기본값 0을 읽고
#     있었다면 "이미 primary driver가 있다"고 잘못 거절했을 것이다.
axisBlind = cmds.createNode("maroAxis", name="blindSpotAxis")
limFirstBlind = cmds.createNode("maroLimit", name="blindSpotLim")
cmds.connectAttr(limFirstBlind + ".capabilityOut", axisBlind + ".capabilityIn[0]")
assert cmds.getAttr(axisBlind + ".capabilityIn[0].capType") == 1, \
    "slot 0 must actually carry capType 1 (limit), pulled through the connection"
cmds.maroAddCapability(axisBlind, type="rotation")   # 거절되면 여기서 raise
assert len(cmds.maroListAxisNodes(capabilities=axisBlind)) // CAPABILITY_FIELDS == 2, \
    "adding a rotation after a non-primary-driver limit must succeed"
print("mutual-exclusivity reads the real connected capType, not the default (I-4a) OK")

# (b) 회전이 아닌 translation을 먼저 놓고 coupling을 시도한다 -- 기존
#     테스트가 다루지 않던 교차 조합이다.
axisBlind2 = cmds.createNode("maroAxis", name="blindSpotAxis2")
transFirstBlind = cmds.createNode("maroTranslation", name="blindSpotTrans")
cmds.connectAttr(transFirstBlind + ".capabilityOut", axisBlind2 + ".capabilityIn[0]")
assert cmds.getAttr(axisBlind2 + ".capabilityIn[0].capType") == 4, \
    "slot 0 must actually carry capType 4 (translation)"
try:
    cmds.maroAddCapability(axisBlind2, type="coupling")
    raised = False
except RuntimeError:
    raised = True
assert raised, "translation-then-coupling must be rejected too (I-4b)"
print("mutual-exclusivity translation-then-coupling rejection (I-4b) OK")

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

# --- 리뷰 Finding C-2b: maroSetControlMode의 Manual->ROS 시딩이 직선축을 ---
# --- 0으로 스냅시키던 버그. 순수 DG 경로로(브리지 없이) 확인한다.      ---
axisSeed = cmds.createNode("maroAxis", name="seedLinearAxis")
transSeed = cmds.createNode("maroTranslation", name="seedTrans")
cmds.connectAttr(transSeed + ".capabilityOut", axisSeed + ".capabilityIn[0]")
cmds.setAttr(transSeed + ".distance", 17.5)   # 센티미터 (파일 상단에서 고정)
assert cmds.getAttr(axisSeed + ".driveIsLinear") is True, \
    "translation-driven axis must report driveIsLinear=True"
beforeSwitch = cmds.getAttr(axisSeed + ".positionLinear")
assert abs(beforeSwitch - 17.5) < 1e-9, f"linear axis setup wrong (got {beforeSwitch})"

cmds.maroSetControlMode(axisSeed, 1)
seededCmd = cmds.getAttr(axisSeed + ".rosCommand")
assert abs(seededCmd - 17.5) < 1e-9, (
    "Manual->ROS seeding must read outValueLinear (centimeters) for a linear "
    f"axis, not the always-zero angular outValue; rosCommand={seededCmd}"
)
afterSwitch = cmds.getAttr(axisSeed + ".positionLinear")
assert abs(afterSwitch - beforeSwitch) < 1e-9, (
    f"linear axis snapped on mode switch; before={beforeSwitch}, after={afterSwitch}"
)

# 회전축은 회귀 없이 각도 경로 그대로여야 한다.
axisSeedRot = cmds.createNode("maroAxis", name="seedRotAxis")
rotSeed = cmds.createNode("maroRotation", name="seedRot")
cmds.connectAttr(rotSeed + ".capabilityOut", axisSeedRot + ".capabilityIn[0]")
cmds.setAttr(rotSeed + ".angle", 0.75)        # 라디안 (파일 상단에서 고정)
cmds.maroSetControlMode(axisSeedRot, 1)
seededRot = cmds.getAttr(axisSeedRot + ".rosCommand")
assert abs(seededRot - 0.75) < 1e-9, (
    f"angular seeding regressed; rosCommand={seededRot}"
)
print("maroSetControlMode linear seeding (C-2b) OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
