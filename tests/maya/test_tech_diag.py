import math
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
flat = ["|axis1", "joint1", "|cube1", "|axis0", "0", "1", "1", "2", "Axis One", "0.2,0.6,0.9"]
rows = diag.sliceAxisTechRows(flat)
assert len(rows) == 1, rows
assert rows[0] == {
    "axisFullPath": "|axis1", "jointName": "joint1", "boundTargetPath": "|cube1",
    "parentAxisPath": "|axis0",
    "enabled": True, "conventionAxis": 1, "capabilityCount": 2,
}, rows[0]
# 부모가 없는 축은 빈 문자열을 그대로 들고 온다.
unparented = diag.sliceAxisTechRows(
    ["|axisR", "j", "|cubeR", "", "0", "1", "1", "0", "", "0,0,0"])
assert unparented[0]["parentAxisPath"] == "", unparented[0]
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

# 최종 리뷰 Important-7: 요약에 현재값/접근한 경계/슬롯 인덱스가 들어가야
# 한다. (a) 설명만 있는 항목이라 요약이 사용자가 받는 정보의 전부이고,
# (b) 한 축에 리밋 슬롯이 둘이면 요약이 글자 하나 안 틀리고 같아진다.
summaryFindings = diag.checkLimitProximity(axisRows, capsByAxis, {"|axis1": 9.5})
summary = summaryFindings[0]["summary"]
assert "9.5" in summary, summary            # 현재값
assert "max" in summary, summary            # 어느 쪽 끝에 붙었는지
assert "10.0" in summary, summary           # 그 경계값
assert "capability[0]" in summary, summary  # 어느 슬롯이 건 리밋인지
lowFindings = diag.checkLimitProximity(axisRows, capsByAxis, {"|axis1": 0.5})
assert len(lowFindings) == 1, lowFindings
assert "min" in lowFindings[0]["summary"], lowFindings[0]["summary"]

twoSlots = {"|axis1": [
    {"logicalIndex": 0, "capType": 1, "capMin": (0.0, 0.0, 0.0),
     "capMax": (10.0, 0.0, 0.0), "capEnable": (True, False, False)},
    {"logicalIndex": 3, "capType": 1, "capMin": (0.0, 0.0, 0.0),
     "capMax": (10.0, 0.0, 0.0), "capEnable": (True, False, False)},
]}
twoFindings = diag.checkLimitProximity(axisRows, twoSlots, {"|axis1": 9.5})
assert len(twoFindings) == 2, twoFindings
assert twoFindings[0]["summary"] != twoFindings[1]["summary"], \
    "findings from two different limit slots must be distinguishable"
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

# --- adjacentMeshPairs / filterAdjacentMeshCollisions (pure) ---
chainRows = [
    {"axisFullPath": "|axP", "jointName": "p", "boundTargetPath": "|linkP",
     "parentAxisPath": "", "enabled": True, "conventionAxis": 0, "capabilityCount": 1},
    {"axisFullPath": "|axC", "jointName": "c", "boundTargetPath": "|linkC",
     "parentAxisPath": "|axP", "enabled": True, "conventionAxis": 0, "capabilityCount": 1},
    {"axisFullPath": "|axU", "jointName": "u", "boundTargetPath": "|linkU",
     "parentAxisPath": "", "enabled": True, "conventionAxis": 0, "capabilityCount": 1},
]
pairs = diag.adjacentMeshPairs(chainRows)
assert pairs == {frozenset(("|linkP", "|linkC"))}, pairs
# 부모 축이 아무것도 바인딩하지 않았으면 걸러낼 쌍 자체가 없다.
assert diag.adjacentMeshPairs([
    {"axisFullPath": "|axP", "jointName": "p", "boundTargetPath": "",
     "parentAxisPath": "", "enabled": True, "conventionAxis": 0, "capabilityCount": 1},
    {"axisFullPath": "|axC", "jointName": "c", "boundTargetPath": "|linkC",
     "parentAxisPath": "|axP", "enabled": True, "conventionAxis": 0, "capabilityCount": 1},
]) == set()

rawCollisions = diag.checkMeshCollisions({
    "|linkP": (0.0, 0.0, 0.0, 4.0, 4.0, 4.0),
    "|linkC": (1.0, 1.0, 1.0, 2.0, 2.0, 2.0),   # DAG 자손이라 부모 AABB 안에 들어감
    "|linkU": (1.5, 1.5, 1.5, 6.0, 6.0, 6.0),   # 무관한 축, 둘 다와 진짜 겹침
})
assert len(rawCollisions) == 3, rawCollisions
filtered = diag.filterAdjacentMeshCollisions(rawCollisions, pairs)
assert {frozenset(f["meshes"]) for f in filtered} == {
    frozenset(("|linkP", "|linkU")), frozenset(("|linkC", "|linkU"))}, filtered
print("adjacentMeshPairs/filterAdjacentMeshCollisions OK")

# --- suggestDisambiguatedJointName (pure) ---
assert diag.suggestDisambiguatedJointName("shoulder") == "shoulder_2"
# 최종 리뷰 Important-4: 이미 쓰이는 이름을 알려주면 충돌을 옮기지 않고 피한다.
assert diag.suggestDisambiguatedJointName("shoulder", set()) == "shoulder_2"
assert diag.suggestDisambiguatedJointName("shoulder", {"shoulder"}) == "shoulder_2"
assert diag.suggestDisambiguatedJointName("shoulder", {"shoulder", "shoulder_2"}) == "shoulder_3"
assert diag.suggestDisambiguatedJointName(
    "shoulder", {"shoulder", "shoulder_2", "shoulder_3"}) == "shoulder_4"
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

# ---------------------------------------------------------------------------
# 여기서부터는 순수 함수가 아니라 Maya 통합 계층(_runMayaSideChecks /
# _runRosSideChecks) 자체를 실제 씬에 대고 돌린다. 최종 리뷰가 지적한
# "이 계층은 아무 테스트도 없다"는 공백을 메운다.
# ---------------------------------------------------------------------------

# --- 최종 리뷰 Critical-1: 도(degrees) 세션에서의 리밋 근접 단위 계약 ---
#
# axis.position은 MFnUnitAttribute::kAngle이라 cmds.getAttr()이 "현재 UI 각도
# 단위"(사용자 세션 기본값 = 도)로 돌려주는데, 비교 상대인
# capabilityIn[i].capMin/capMax는 평범한 k3Double이고 compute()가 거기에
# 데이터블록의 생 라디안 값을 클램프한다(test_capability_stack.py의 "unit
# contract" 절이 이 계약을 이미 고정해 둔다). 그래서 cmds.getAttr() 값을 그대로
# 쓰면 45.0(도)을 ±1.5708(라디안)과 비교하게 되고, 0이 아닌 회전축은 거의 전부
# 경고로 뜬다. 이 파일 위쪽 부트스트랩은 angle="rad"로 고정돼 있으므로 -- 그
# 상태에서는 버그가 드러나지 않는다 -- 이 블록 안에서만 "deg"로 바꿨다가
# 끝에서 되돌린다.
cmds.file(new=True, force=True)
prevAngleUnit = cmds.currentUnit(query=True, angle=True)
cmds.currentUnit(angle="deg")

unitCube = cmds.polyCube(name="unitLimitCube")[0]
unitAxis = cmds.createNode("maroAxis", name="unitLimitAxis")
cmds.maroBindAxis(unitAxis, unitCube)
unitRot = cmds.createNode("maroRotation", name="unitLimitRot")
cmds.connectAttr(unitRot + ".capabilityOut", unitAxis + ".capabilityIn[0]")
cmds.setAttr(unitRot + ".angle", 45.0)          # 도 세션 -> 데이터블록엔 pi/4 rad
unitLim = cmds.createNode("maroLimit", name="unitLimitLim")
# conventionAxis 기본값이 Y(1)이므로 Y 성분에 리밋을 건다.
cmds.setAttr(unitLim + ".enableY", True)
cmds.setAttr(unitLim + ".minY", -90.0)          # 도 -> -pi/2 rad
cmds.setAttr(unitLim + ".maxY", 90.0)           # 도 ->  pi/2 rad
cmds.connectAttr(unitLim + ".capabilityOut", unitAxis + ".capabilityIn[1]")

# 전제 고정: 두 표면이 정말로 다른 단위로 말한다.
assert abs(cmds.getAttr(unitAxis + ".position") - 45.0) < 1e-6, \
    "precondition: cmds.getAttr on a kAngle attr speaks the UI unit (degrees here)"
assert abs(cmds.getAttr(unitAxis + ".capabilityIn[1].capMax")[0][1]
           - (math.pi / 2.0)) < 1e-9, \
    "precondition: capMax is a plain double carrying raw radians"

# 수정의 핵심: UI 단위 값을 생 라디안으로 명시 변환해 읽는다.
assert abs(diag._readCurrentValue(unitAxis, False) - (math.pi / 4.0)) < 1e-9, \
    "_readCurrentValue must return raw radians, not the UI-unit number"

mayaFindings = diag._runMayaSideChecks()
limitFindings = [f for f in mayaFindings if f["category"] == "limitProximity"]
assert limitFindings == [], (
    "a rotary axis at a safe 45 deg inside a +/-90 deg limit must NOT be flagged in a "
    "degrees-unit session: {}".format(limitFindings))

# 대조군: 같은 세션/같은 단위에서 정말로 리밋에 붙으면 여전히 잡힌다.
cmds.setAttr(unitRot + ".angle", 89.0)          # 도 -> 리밋(90도)의 99.4% 지점
nearFindings = [f for f in diag._runMayaSideChecks()
                if f["category"] == "limitProximity"]
assert len(nearFindings) == 1, nearFindings
assert "max" in nearFindings[0]["summary"], nearFindings[0]["summary"]

cmds.currentUnit(angle=prevAngleUnit)
assert cmds.currentUnit(query=True, angle=True) == prevAngleUnit
print("_runMayaSideChecks limit-proximity unit contract (degrees session) OK")

# --- 최종 리뷰 Important-6: 부모-자식 축의 메쉬는 충돌로 세지 않는다 ---
#
# exactWorldBoundingBox()는 DAG 자손을 전부 포함하고, 링크 메쉬를 DAG로
# 중첩하는 것은 흔한 리깅이다. 그러면 부모 링크의 AABB가 자식 것을 항상
# 품으므로 인접 조인트 쌍마다 "충돌"이 하나씩 나온다 -- 잡음이다.
cmds.file(new=True, force=True)

parentCube = cmds.polyCube(name="chainParentLink")[0]
childCube = cmds.polyCube(name="chainChildLink")[0]
cmds.setAttr(childCube + ".scale", 0.5, 0.5, 0.5)   # 부모 박스 안에 완전히 들어감
axisParent = cmds.createNode("maroAxis", name="chainParentAxis")
axisChild = cmds.createNode("maroAxis", name="chainChildAxis")
cmds.maroBindAxis(axisParent, parentCube)
cmds.maroBindAxis(axisChild, childCube)
cmds.maroConnectAxis(axisChild, axisParent)         # 첫 인자의 부모가 두 번째
assert cmds.isConnected(axisParent + ".message", axisChild + ".parentAxis")

# 부모-자식이 아닌, 서로 겹치는 두 축(대조군). 위 체인과는 멀리 떨어뜨린다.
loneCubeA = cmds.polyCube(name="loneLinkA")[0]
loneCubeB = cmds.polyCube(name="loneLinkB")[0]
cmds.setAttr(loneCubeA + ".translateX", 100.0)
cmds.setAttr(loneCubeB + ".translateX", 100.3)
axisLoneA = cmds.createNode("maroAxis", name="loneAxisA")
axisLoneB = cmds.createNode("maroAxis", name="loneAxisB")
cmds.maroBindAxis(axisLoneA, loneCubeA)
cmds.maroBindAxis(axisLoneB, loneCubeB)

collisionPairs = {frozenset(f["meshes"]) for f in diag._runMayaSideChecks()
                  if f["category"] == "meshCollision"}
shortPairs = {frozenset(m.split("|")[-1] for m in pair) for pair in collisionPairs}
assert frozenset(("chainParentLink", "chainChildLink")) not in shortPairs, (
    "a parent/child axis pair whose meshes nest must not be reported as a collision: "
    "{}".format(shortPairs))
assert frozenset(("loneLinkA", "loneLinkB")) in shortPairs, (
    "two unrelated axes with overlapping meshes must still be reported: "
    "{}".format(shortPairs))
print("_runMayaSideChecks parent/child mesh-adjacency filtering OK")

# --- 최종 리뷰 Important-4: 세 축이 같은 이름이면 제안이 서로 겹치지 않는다 ---
cmds.file(new=True, force=True)
dupAxes = []
for i in range(3):
    dupCube = cmds.polyCube(name="dupCube{}".format(i))[0]
    dupAxis = cmds.createNode("maroAxis", name="dupAxis{}".format(i))
    cmds.setAttr(dupCube + ".translateX", i * 10.0)   # 메쉬 충돌은 끼어들지 않게
    cmds.maroBindAxis(dupAxis, dupCube)
    cmds.setAttr(dupAxis + ".jointName", "shoulder", type="string")
    dupAxes.append(dupAxis)

rosFindings = diag._runRosSideChecks()
dupFindings = [f for f in rosFindings if f["category"] == "duplicateJointName"]
assert len(dupFindings) == 2, dupFindings
for finding in dupFindings:
    finding["remedy"]()
appliedNames = sorted(cmds.getAttr(a + ".jointName") for a in dupAxes)
assert appliedNames == ["shoulder", "shoulder_2", "shoulder_3"], (
    "applying every duplicate-name remedy must leave three distinct names, not two "
    "axes both renamed to shoulder_2: {}".format(appliedNames))
assert [f for f in diag._runRosSideChecks()
        if f["category"] == "duplicateJointName"] == [], \
    "re-running the check after the remedies must find no duplicates left"
print("_runRosSideChecks duplicate-name remedy collision avoidance OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
sys.exit(0)
