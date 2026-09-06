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

# maroTechDiag.py는 의도적으로 maroSettingsPanel을 import하지 않는다 --
# AXIS_FIELDS/CAPABILITY_FIELDS(이 파일 33-35번째 줄 주석)와 같은 이유로,
# 파일 간 결합을 늘리지 않기 위해 optionVar 이름 문자열을 각자 독립적으로
# 선언해 둔다(Qt 여부와는 무관하다 -- 이 파일은 이미 PySide6를 쓴다). 그래서
# _limitProximityThreshold()의 optionVar 이름 문자열이
# maroSettingsPanel._TECH_DIAG_THRESHOLD_VAR와 같은 값을 쓰는지 이 소스
# 텍스트 핀으로만 잡을 수 있다. 하나가 바뀌고 다른 하나가 안 바뀌면 이
# assert가 실패한다.
import inspect
import maroSettingsPanel as settingsPanel  # noqa: E402 -- 값만 참조, 값 핀 전용
techDiagSource = inspect.getsource(diag)
assert settingsPanel._TECH_DIAG_THRESHOLD_VAR in techDiagSource, (
    "maroTechDiag.py's hardcoded optionVar name must match "
    "maroSettingsPanel._TECH_DIAG_THRESHOLD_VAR"
)
print("optionVar name contract (maroTechDiag <-> maroSettingsPanel) OK")

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

# --- checkLidarTargetMeshes / checkLidarRayCount (순수 함수) --------------

noTargetRows = [{"lidarFullPath": "|lidar1", "enabled": True, "verticalSamples": 4,
                 "horizontalSamples": 4, "targetMeshCount": 0}]
findings = diag.checkLidarTargetMeshes(noTargetRows)
assert len(findings) == 1 and findings[0]["category"] == "lidarNoTargetMesh"
print("checkLidarTargetMeshes flags an enabled lidar with no target OK")

disabledNoTargetRows = [{"lidarFullPath": "|lidar1", "enabled": False, "verticalSamples": 4,
                         "horizontalSamples": 4, "targetMeshCount": 0}]
assert diag.checkLidarTargetMeshes(disabledNoTargetRows) == []
print("checkLidarTargetMeshes ignores a disabled lidar OK")

hasTargetRows = [{"lidarFullPath": "|lidar1", "enabled": True, "verticalSamples": 4,
                  "horizontalSamples": 4, "targetMeshCount": 1}]
assert diag.checkLidarTargetMeshes(hasTargetRows) == []
print("checkLidarTargetMeshes passes a lidar with a target OK")

overCapRows = [{"lidarFullPath": "|lidar1", "enabled": True, "verticalSamples": 300,
                "horizontalSamples": 300, "targetMeshCount": 1}]
findings = diag.checkLidarRayCount(overCapRows)
assert len(findings) == 1 and findings[0]["category"] == "lidarRayCountExceeded"
print("checkLidarRayCount flags an over-cap configuration OK")

underCapRows = [{"lidarFullPath": "|lidar1", "enabled": True, "verticalSamples": 4,
                 "horizontalSamples": 36, "targetMeshCount": 1}]
assert diag.checkLidarRayCount(underCapRows) == []
print("checkLidarRayCount passes a default-scale configuration OK")

# [최종 리뷰 Minor-11] 경계값 그 자체 -- 곱이 정확히 상한과 같은 설정.
# checkLidarRayCount()는 `>`를 쓰고(`>=`가 아니라), MaroLidarScan.cpp의
# scanLidarNode()도 `if (rayCount > kMaxRaysPerScan) return kRayCountExceeded;`
# 로 같은 부등호를 쓴다. 즉 "정확히 상한"은 **실제로 스캔이 돌아가는**
# 설정이므로 진단이 경고를 띄우면 안 된다. 둘 중 한쪽만 `>=`로 바뀌면
# 진단과 런타임이 어긋나 사용자가 멀쩡히 도는 설정을 경고로 보게 되는데,
# 그 회귀는 이 행이 없으면 어떤 테스트도 잡지 못한다(위 두 케이스는 상한에서
# 90000/144만큼 떨어져 있어 부등호를 바꿔도 그대로 통과한다).
atCapRows = [{"lidarFullPath": "|lidar1", "enabled": True,
              "verticalSamples": 256, "horizontalSamples": 256,
              "targetMeshCount": 1}]
assert 256 * 256 == diag.LIDAR_MAX_RAYS_PER_SCAN, (
    "this boundary case must sit exactly on the cap; if LIDAR_MAX_RAYS_PER_SCAN "
    "changed, update the factors here too")
assert diag.checkLidarRayCount(atCapRows) == [], (
    "a ray count exactly equal to the cap is still scannable (scanLidarNode uses "
    "'>' too) -- it must not be flagged")
print("checkLidarRayCount does not flag a configuration exactly at the cap OK")

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

# 2차 재검토: exactWorldBoundingBox()가 담는 것은 "DAG 자손 전부"이지 직속
# 자식 하나가 아니다. 3단 체인 axP(조부모) -> axC(부모) -> axG(자식)에서는
# bbox(axP)가 bbox(axG)까지 통째로 품는다 -- 그런데 한 단계짜리 필터는
# (axP,axC)와 (axC,axG)만 걸러내고 조부모-자손 쌍인 (axP,axG)는 그대로
# 남겨 진짜 충돌처럼 잡음을 낸다. parentAxisPath 체인을 뿌리까지 전부
# 따라가 조상/자손 관계에 있는 모든 축 쌍을 걸러내야 한다.
grandchainRows = [
    {"axisFullPath": "|axP", "jointName": "p", "boundTargetPath": "|linkP",
     "parentAxisPath": "", "enabled": True, "conventionAxis": 0, "capabilityCount": 1},
    {"axisFullPath": "|axC", "jointName": "c", "boundTargetPath": "|linkC",
     "parentAxisPath": "|axP", "enabled": True, "conventionAxis": 0, "capabilityCount": 1},
    {"axisFullPath": "|axG", "jointName": "g", "boundTargetPath": "|linkG",
     "parentAxisPath": "|axC", "enabled": True, "conventionAxis": 0, "capabilityCount": 1},
]
grandPairs = diag.adjacentMeshPairs(grandchainRows)
assert grandPairs == {
    frozenset(("|linkP", "|linkC")),
    frozenset(("|linkC", "|linkG")),
    frozenset(("|linkP", "|linkG")),
}, grandPairs
print("adjacentMeshPairs three-level ancestor chain OK")

# --- checkLidarZeroHits ---
lidarRowsZero = [{"lidarFullPath": "|lidarA", "enabled": True, "verticalSamples": 1,
                  "horizontalSamples": 1, "targetMeshCount": 1}]
scanEmpty = {"|lidarA": {"status": "kOk", "hitPoints": []}}
findings = diag.checkLidarZeroHits(lidarRowsZero, scanEmpty)
assert len(findings) == 1 and findings[0]["category"] == "lidarZeroHits", findings
scanNonEmpty = {"|lidarA": {"status": "kOk", "hitPoints": [(0.0, 0.0, 0.0)]}}
assert diag.checkLidarZeroHits(lidarRowsZero, scanNonEmpty) == []
scanFailed = {"|lidarA": {"status": "kMeshExtractFailed", "hitPoints": []}}
assert diag.checkLidarZeroHits(lidarRowsZero, scanFailed) == [], (
    "a non-kOk status must not also be flagged as a zero-hit finding")
lidarRowsNoMesh = [{"lidarFullPath": "|lidarB", "enabled": True, "verticalSamples": 1,
                    "horizontalSamples": 1, "targetMeshCount": 0}]
assert diag.checkLidarZeroHits(lidarRowsNoMesh, {"|lidarB": {"status": "kOk", "hitPoints": []}}) == []
print("checkLidarZeroHits OK")

# --- checkLidarOutOfRange ---
import maya.api.OpenMaya as om2Test
scanInRange = {"|lidarA": {"status": "kOk", "rangeMaxMaya": 100.0,
                           "effectiveWorldMatrix": om2Test.MMatrix()}}
boxesFar = {"|lidarA": {"|meshFar": (200.0, 0.0, 0.0, 210.0, 10.0, 10.0)}}
findings = diag.checkLidarOutOfRange(lidarRowsZero, scanInRange, boxesFar)
assert len(findings) == 1 and findings[0]["category"] == "lidarOutOfRange", findings
boxesNear = {"|lidarA": {"|meshNear": (10.0, 0.0, 0.0, 20.0, 10.0, 10.0)}}
assert diag.checkLidarOutOfRange(lidarRowsZero, scanInRange, boxesNear) == []
print("checkLidarOutOfRange OK")

# --- checkLidarOutOfFov ---
scanNarrowFov = {"|lidarA": {"status": "kOk",
                             "verticalMinAngle": -0.1, "verticalMaxAngle": 0.1,
                             "horizontalMinAngle": -0.1, "horizontalMaxAngle": 0.1,
                             "effectiveWorldMatrix": om2Test.MMatrix()}}
# 로컬 +Z 방향(수직=0, 수평=0)이면 FOV 안. 로컬 +X 방향은 수평 ~pi/2로 밖.
boxesInFov = {"|lidarA": {"|meshInFov": (-1.0, -1.0, 9.0, 1.0, 1.0, 11.0)}}
assert diag.checkLidarOutOfFov(lidarRowsZero, scanNarrowFov, boxesInFov) == []
boxesOutOfFov = {"|lidarA": {"|meshOutOfFov": (9.0, -1.0, -1.0, 11.0, 1.0, 1.0)}}
findings = diag.checkLidarOutOfFov(lidarRowsZero, scanNarrowFov, boxesOutOfFov)
assert len(findings) == 1 and findings[0]["category"] == "lidarOutOfFov", findings
print("checkLidarOutOfFov OK")

# --- checkLidarHitBoundsConsistency ---
scanValidHit = {"|lidarA": {"status": "kOk", "rangeMinMaya": 0.0, "rangeMaxMaya": 100.0,
                            "effectiveWorldMatrix": om2Test.MMatrix(),
                            "hitPoints": [(50.0, 0.0, 0.0)]}}
assert diag.checkLidarHitBoundsConsistency(lidarRowsZero, scanValidHit) == []
scanBadHit = {"|lidarA": {"status": "kOk", "rangeMinMaya": 0.0, "rangeMaxMaya": 100.0,
                          "effectiveWorldMatrix": om2Test.MMatrix(),
                          "hitPoints": [(500.0, 0.0, 0.0)]}}
findings = diag.checkLidarHitBoundsConsistency(lidarRowsZero, scanBadHit)
assert len(findings) == 1 and findings[0]["category"] == "lidarHitOutOfBounds", findings
print("checkLidarHitBoundsConsistency OK")

# --- checkLidarOutOfRange: status variations (geometry-valid gate test) ---
# kMeshExtractFailed is in VALID_STATUSES -> should still flag out-of-range mesh
scanMeshExtractFailed = {"|lidarA": {"status": "kMeshExtractFailed", "rangeMaxMaya": 100.0,
                                     "effectiveWorldMatrix": om2Test.MMatrix()}}
findings = diag.checkLidarOutOfRange(lidarRowsZero, scanMeshExtractFailed, boxesFar)
assert len(findings) == 1 and findings[0]["category"] == "lidarOutOfRange", findings
print("checkLidarOutOfRange with kMeshExtractFailed still produces finding OK")

# kRayCountExceeded is in VALID_STATUSES -> should still flag out-of-range mesh
scanRayCountExceeded = {"|lidarA": {"status": "kRayCountExceeded", "rangeMaxMaya": 100.0,
                                    "effectiveWorldMatrix": om2Test.MMatrix()}}
findings = diag.checkLidarOutOfRange(lidarRowsZero, scanRayCountExceeded, boxesFar)
assert len(findings) == 1 and findings[0]["category"] == "lidarOutOfRange", findings
print("checkLidarOutOfRange with kRayCountExceeded still produces finding OK")

# kNoTargetMesh is NOT in VALID_STATUSES -> should NOT flag even with far mesh
scanNoTargetMesh = {"|lidarA": {"status": "kNoTargetMesh", "rangeMaxMaya": 100.0,
                                "effectiveWorldMatrix": om2Test.MMatrix()}}
findings = diag.checkLidarOutOfRange(lidarRowsZero, scanNoTargetMesh, boxesFar)
assert findings == [], "kNoTargetMesh status must skip the check: {}".format(findings)
print("checkLidarOutOfRange with kNoTargetMesh produces no finding OK")

# kInvalidConfig is NOT in VALID_STATUSES -> should NOT flag even with far mesh
scanInvalidConfig = {"|lidarA": {"status": "kInvalidConfig", "rangeMaxMaya": 100.0,
                                 "effectiveWorldMatrix": om2Test.MMatrix()}}
findings = diag.checkLidarOutOfRange(lidarRowsZero, scanInvalidConfig, boxesFar)
assert findings == [], "kInvalidConfig status must skip the check: {}".format(findings)
print("checkLidarOutOfRange with kInvalidConfig produces no finding OK")

# --- checkLidarOutOfFov: status variations (geometry-valid gate test) ---
# kMeshExtractFailed is in VALID_STATUSES -> should still flag out-of-FOV mesh
scanMeshExtractFailedFov = {"|lidarA": {"status": "kMeshExtractFailed",
                                        "verticalMinAngle": -0.1, "verticalMaxAngle": 0.1,
                                        "horizontalMinAngle": -0.1, "horizontalMaxAngle": 0.1,
                                        "effectiveWorldMatrix": om2Test.MMatrix()}}
findings = diag.checkLidarOutOfFov(lidarRowsZero, scanMeshExtractFailedFov, boxesOutOfFov)
assert len(findings) == 1 and findings[0]["category"] == "lidarOutOfFov", findings
print("checkLidarOutOfFov with kMeshExtractFailed still produces finding OK")

# kRayCountExceeded is in VALID_STATUSES -> should still flag out-of-FOV mesh
scanRayCountExceededFov = {"|lidarA": {"status": "kRayCountExceeded",
                                       "verticalMinAngle": -0.1, "verticalMaxAngle": 0.1,
                                       "horizontalMinAngle": -0.1, "horizontalMaxAngle": 0.1,
                                       "effectiveWorldMatrix": om2Test.MMatrix()}}
findings = diag.checkLidarOutOfFov(lidarRowsZero, scanRayCountExceededFov, boxesOutOfFov)
assert len(findings) == 1 and findings[0]["category"] == "lidarOutOfFov", findings
print("checkLidarOutOfFov with kRayCountExceeded still produces finding OK")

# kNoTargetMesh is NOT in VALID_STATUSES -> should NOT flag even with out-of-FOV mesh
scanNoTargetMeshFov = {"|lidarA": {"status": "kNoTargetMesh",
                                   "verticalMinAngle": -0.1, "verticalMaxAngle": 0.1,
                                   "horizontalMinAngle": -0.1, "horizontalMaxAngle": 0.1,
                                   "effectiveWorldMatrix": om2Test.MMatrix()}}
findings = diag.checkLidarOutOfFov(lidarRowsZero, scanNoTargetMeshFov, boxesOutOfFov)
assert findings == [], "kNoTargetMesh status must skip the check: {}".format(findings)
print("checkLidarOutOfFov with kNoTargetMesh produces no finding OK")

# kInvalidConfig is NOT in VALID_STATUSES -> should NOT flag even with out-of-FOV mesh
scanInvalidConfigFov = {"|lidarA": {"status": "kInvalidConfig",
                                    "verticalMinAngle": -0.1, "verticalMaxAngle": 0.1,
                                    "horizontalMinAngle": -0.1, "horizontalMaxAngle": 0.1,
                                    "effectiveWorldMatrix": om2Test.MMatrix()}}
findings = diag.checkLidarOutOfFov(lidarRowsZero, scanInvalidConfigFov, boxesOutOfFov)
assert findings == [], "kInvalidConfig status must skip the check: {}".format(findings)
print("checkLidarOutOfFov with kInvalidConfig produces no finding OK")

# --- checkLidarZeroHits: enabled=False gate test ---
lidarRowsDisabled = [{"lidarFullPath": "|lidarA", "enabled": False, "verticalSamples": 1,
                      "horizontalSamples": 1, "targetMeshCount": 1}]
scanEmpty = {"|lidarA": {"status": "kOk", "hitPoints": []}}
findings = diag.checkLidarZeroHits(lidarRowsDisabled, scanEmpty)
assert findings == [], "disabled lidar must not produce a zero-hits finding: {}".format(findings)
print("checkLidarZeroHits with enabled=False produces no finding OK")

# --- checkLidarOutOfRange: enabled=False gate test ---
findings = diag.checkLidarOutOfRange(lidarRowsDisabled, scanInRange, boxesFar)
assert findings == [], "disabled lidar must not produce an out-of-range finding: {}".format(findings)
print("checkLidarOutOfRange with enabled=False produces no finding OK")

# --- checkLidarOutOfFov: enabled=False gate test ---
findings = diag.checkLidarOutOfFov(lidarRowsDisabled, scanNarrowFov, boxesOutOfFov)
assert findings == [], "disabled lidar must not produce an out-of-FOV finding: {}".format(findings)
print("checkLidarOutOfFov with enabled=False produces no finding OK")

# --- checkLidarHitBoundsConsistency: enabled=False gate test (최종 리뷰
# Minor-1 -- 이 검사만 다른 세 검사와 달리 enabled 게이트가 없었다) ---
findings = diag.checkLidarHitBoundsConsistency(lidarRowsDisabled, scanBadHit)
assert findings == [], (
    "disabled lidar must not produce a hit-out-of-bounds finding even if the "
    "(stale/hypothetical) scan data would otherwise trigger one: {}".format(findings))
print("checkLidarHitBoundsConsistency with enabled=False produces no finding OK")

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
# 2026-09-07 재설계: 어느 축인지는 이제 axisDirection이 나르고,
# MaroAxisNode.cpp의 conventionAxis 인덱싱은 broadcast로 흡수된다.
cmds.setAttr(unitLim + ".axisDirection", 0, 1, 0, type="double3")
cmds.setAttr(unitLim + ".min", -90.0)          # 도 -> -pi/2 rad
cmds.setAttr(unitLim + ".max", 90.0)           # 도 ->  pi/2 rad
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

# --- _collectLidarRows()/(_runMayaSideChecks 경유) 통합 확인 --------------

cmds.file(new=True, force=True)

lidar = cmds.createNode("maroLidar")
lidar = cmds.ls(lidar, long=True)[0]
cmds.setAttr(lidar + ".enabled", True)
cmds.setAttr(lidar + ".verticalSamples", 300)
cmds.setAttr(lidar + ".horizontalSamples", 300)
# targetMeshes를 일부러 비워 둔다 -- 두 검사 모두 걸려야 한다.

mayaFindings = diag._runMayaSideChecks()
categories = {f["category"] for f in mayaFindings}
assert "lidarNoTargetMesh" in categories, categories
assert "lidarRayCountExceeded" in categories, categories
print("_runMayaSideChecks surfaces both new lidar findings OK")

# --- end-to-end: _runMayaSideChecks() surfaces a zero-hit + out-of-range LiDAR ---
farMesh = cmds.polyPlane(name="techDiagFarMesh", width=10, height=10,
                          subdivisionsX=1, subdivisionsY=1)[0]
cmds.setAttr(farMesh + ".translateX", 100000)  # 훨씬 rangeMax 밖
lidarNode = cmds.createNode("maroLidar", name="techDiagLidar")
lidarNode = cmds.ls(lidarNode, long=True)[0]
cmds.setAttr(lidarNode + ".verticalSamples", 1)
cmds.setAttr(lidarNode + ".horizontalSamples", 1)
cmds.setAttr(lidarNode + ".rangeMax", 30.0)  # 미터, 훨씬 작음
cmds.connectAttr(farMesh + ".message", lidarNode + ".targetMeshes[0]")

allFindings = diag._runMayaSideChecks()
categories = {f["category"] for f in allFindings}
assert "lidarZeroHits" in categories, categories
assert "lidarOutOfRange" in categories, categories
print("_runMayaSideChecks surfaces lidarZeroHits + lidarOutOfRange OK")

# --- 최종 리뷰 Critical-1(이 리뷰 웨이브): LiDAR 타겟 메쉬 AABB의 UI 단위 vs
# 내부(cm) 단위 계약 -- 미터 씬 ---
#
# _collectLidarTargetMeshBoxes()는 cmds.exactWorldBoundingBox()를 그대로
# 쓰는데, 그 값은 "현재 UI 선형 단위"로 나온다. 반면 checkLidarOutOfRange/
# checkLidarOutOfFov가 비교하는 scan["rangeMaxMaya"]/scan["effectiveWorldMatrix"]는
# maroQueryLidarScan()이 항상 Maya 내부 단위(센티미터, MDistance::internalUnit())
# 로 돌려준다. 씬이 미터로 작성되면 둘이 100배 어긋난다.
#
# 여기서는 실제로 rangeMax(5m) 밖(10m 거리)에 있는 타겟을 미터 씬에 두고,
# 그게 정말로 lidarOutOfRange로 잡히는지 확인한다. 수정 전 코드는 UI 단위
# (미터, 숫자로 10)를 내부 단위(센티미터, rangeMaxMaya=500) 그대로 비교해
# 10 < 500이라 통과시켜(false negative) 이 검사를 완전히 무력화했다.
cmds.file(new=True, force=True)
prevLinearUnit = cmds.currentUnit(query=True, linear=True)
cmds.currentUnit(linear="m")

meterFarMesh = cmds.polyPlane(name="techDiagMeterFarMesh", width=1, height=1,
                               subdivisionsX=1, subdivisionsY=1)[0]
cmds.setAttr(meterFarMesh + ".translateX", 10.0)  # 10 meters away
meterLidar = cmds.createNode("maroLidar", name="techDiagMeterLidar")
meterLidar = cmds.ls(meterLidar, long=True)[0]
cmds.setAttr(meterLidar + ".verticalSamples", 1)
cmds.setAttr(meterLidar + ".horizontalSamples", 1)
cmds.setAttr(meterLidar + ".rangeMax", 5.0)  # meters -- real target is 2x further than this
cmds.connectAttr(meterFarMesh + ".message", meterLidar + ".targetMeshes[0]")

meterFindings = diag._runMayaSideChecks()
meterCategories = {f["category"] for f in meterFindings}
assert "lidarOutOfRange" in meterCategories, (
    "a target mesh 10m away with rangeMax=5m in a meters-authored scene must be "
    "flagged lidarOutOfRange -- got {} (this is the UI-unit vs internal-cm bug: "
    "exactWorldBoundingBox() returns meters, rangeMaxMaya is always internal cm, "
    "and comparing them unconverted makes a real 10m-away target look like it's "
    "well within a 500 'unit' range)".format(meterCategories))
print("checkLidarOutOfRange meters-scene unit contract OK")

# 대조군: 같은 미터 씬에서 실제로 range 안에 있는 타겟은 여전히 안 걸려야
# 한다 -- 단위 변환이 방향만 맞고 계수가 틀리면(예: 1/100 대신 100을 두
# 번 곱하는 등) 이 대조군이 잡아낸다.
meterNearMesh = cmds.polyPlane(name="techDiagMeterNearMesh", width=1, height=1,
                                subdivisionsX=1, subdivisionsY=1)[0]
cmds.setAttr(meterNearMesh + ".translateX", 2.0)  # 2 meters away, well inside rangeMax=5m
cmds.disconnectAttr(meterFarMesh + ".message", meterLidar + ".targetMeshes[0]")
cmds.connectAttr(meterNearMesh + ".message", meterLidar + ".targetMeshes[0]")
meterNearFindings = diag._runMayaSideChecks()
meterNearCategories = {f["category"] for f in meterNearFindings}
assert "lidarOutOfRange" not in meterNearCategories, (
    "a target mesh 2m away with rangeMax=5m in a meters-authored scene must NOT be "
    "flagged lidarOutOfRange -- got {}".format(meterNearCategories))
print("checkLidarOutOfRange meters-scene in-range control OK")

cmds.currentUnit(linear=prevLinearUnit)
assert cmds.currentUnit(query=True, linear=True) == prevLinearUnit
print("linear unit restored OK")

# --- 최종 리뷰 Important-3a: _collectLidarTargetMeshBoxes()의 메쉬 단위
# 부분 실패 격리 (한 LiDAR 안에서) ---
#
# targetMeshes[] 중 하나가 exactWorldBoundingBox()에서 실패해도 그 메쉬
# 하나만 빠지고 같은 LiDAR의 나머지 유효한 메쉬는 그대로 박스가 수집돼야
# 한다. 실측 결과 cmds.exactWorldBoundingBox()는 놀랍게도 폴리곤이 아닌
# 살아있는 노드(예: multiplyDivide)에는 예외를 던지지 않고 그냥 퇴화된
# 박스([1e20,...,-1e20,...])를 돌려준다 -- 실제로 예외가 나는 경우는
# 이름 해석 실패(대상이 이미 삭제됨 등)뿐이고, listConnections()가 돌려준
# 이름은 정의상 그 시점엔 존재했던 노드다. 그래서 이 실패 모드를 자연스러운
# Maya 조작만으로는 결정론적으로 재현할 수 없다 -- cmds.exactWorldBoundingBox
# 를 감싸서 특정 메쉬 이름 하나만 실패를 시뮬레이션한다(아래 Important-3b와
# 같은 기법).
cmds.file(new=True, force=True)
partialLidar = cmds.createNode("maroLidar", name="techDiagPartialLidar")
partialLidar = cmds.ls(partialLidar, long=True)[0]
cmds.setAttr(partialLidar + ".enabled", True)
goodMesh = cmds.polyCube(name="techDiagPartialGoodMesh")[0]
badMesh = cmds.polyCube(name="techDiagPartialBadMesh")[0]
cmds.connectAttr(goodMesh + ".message", partialLidar + ".targetMeshes[0]")
cmds.connectAttr(badMesh + ".message", partialLidar + ".targetMeshes[1]")

_origExactWorldBoundingBox = cmds.exactWorldBoundingBox

def _fakeExactWorldBoundingBox(node, *args, **kwargs):
    if node == badMesh:
        raise ValueError("simulated exactWorldBoundingBox failure for {}".format(node))
    return _origExactWorldBoundingBox(node, *args, **kwargs)

cmds.exactWorldBoundingBox = _fakeExactWorldBoundingBox
try:
    partialLidarRows = diag._collectLidarRows()
    partialBoxes = diag._collectLidarTargetMeshBoxes(partialLidarRows)
finally:
    cmds.exactWorldBoundingBox = _origExactWorldBoundingBox

# _collectLidarTargetMeshBoxes() keys its per-mesh dict with whatever
# cmds.listConnections() returned -- in this fresh scene that's the short,
# still-unique name, matching `goodMesh`/`badMesh` as returned by polyCube().
lidarBoxes = partialBoxes[partialLidar]
assert len(lidarBoxes) == 1, (
    "the failing target-mesh entry must be dropped, leaving only the good "
    "mesh's box: {}".format(lidarBoxes))
assert goodMesh in lidarBoxes, lidarBoxes
print("_collectLidarTargetMeshBoxes drops one bad mesh, keeps the rest OK")

# --- 최종 리뷰 Important-3b: _collectLidarScans()의 개별 LiDAR 조회 실패
# 격리 (LiDAR 간) ---
#
# maroQueryLidarScan() 호출 하나가 실패해도(RuntimeError -- 실측 확인:
# 노드 타입이 맞지 않는 인자를 주면 실제로 이 예외가 난다. ValueError는
# 이름 해석 실패(예: 조회 시점 직전에 그 LiDAR가 삭제되는 레이스
# 컨디션)에서 실측으로 확인했다 -- _collectLidarScans()는 두 종류를 다
# 잡는다) 그 LiDAR만 결과 dict에서 빠지고, 씬의 다른 정상 LiDAR는 계속
# 조회되어 자기 findings를 내야 한다. 이 두 실패 모두 "정상 maroLidar
# 행에 대해 파이프라인이 한창 도는 도중" 결정론적으로 재현하기 어려워서
# (레이스 컨디션이거나, 애초에 lidarRows에 정상 maroLidar만 들어온다),
# cmds.maroQueryLidarScan을 감싸 특정 LiDAR 하나만 실패를 시뮬레이션한다
# -- 그 외에는 실제 커맨드를 그대로 호출한다.
cmds.file(new=True, force=True)

healthyLidar = cmds.createNode("maroLidar", name="techDiagHealthyLidar")
healthyLidar = cmds.ls(healthyLidar, long=True)[0]
cmds.setAttr(healthyLidar + ".enabled", True)
cmds.setAttr(healthyLidar + ".verticalSamples", 1)
cmds.setAttr(healthyLidar + ".horizontalSamples", 1)
cmds.setAttr(healthyLidar + ".rangeMax", 5.0)
healthyFarMesh = cmds.polyPlane(name="techDiagHealthyFarMesh", width=1, height=1,
                                 subdivisionsX=1, subdivisionsY=1)[0]
cmds.setAttr(healthyFarMesh + ".translateX", 10000.0)
cmds.connectAttr(healthyFarMesh + ".message", healthyLidar + ".targetMeshes[0]")

brokenLidar = cmds.createNode("maroLidar", name="techDiagBrokenLidar")
brokenLidar = cmds.ls(brokenLidar, long=True)[0]
cmds.setAttr(brokenLidar + ".enabled", True)
brokenMesh = cmds.polyCube(name="techDiagBrokenMesh")[0]
cmds.connectAttr(brokenMesh + ".message", brokenLidar + ".targetMeshes[0]")

_origMaroQueryLidarScan = cmds.maroQueryLidarScan

def _fakeMaroQueryLidarScan(lidarPath, *args, **kwargs):
    if lidarPath == brokenLidar:
        raise RuntimeError("simulated maroQueryLidarScan failure for {}".format(lidarPath))
    return _origMaroQueryLidarScan(lidarPath, *args, **kwargs)

cmds.maroQueryLidarScan = _fakeMaroQueryLidarScan
try:
    isolationFindings = diag._runMayaSideChecks()
finally:
    cmds.maroQueryLidarScan = _origMaroQueryLidarScan

isolationCategories = {f["category"] for f in isolationFindings}
assert "lidarOutOfRange" in isolationCategories, (
    "the healthy lidar's own finding must still surface even though the other "
    "lidar's maroQueryLidarScan call raised: {}".format(isolationCategories))
print("_collectLidarScans isolates one failing lidar, keeps the healthy one's findings OK")

# --- refineMeshCollisions: confirmed collision kept ---
overlapA = cmds.polyCube(name="refineOverlapA")[0]
overlapB = cmds.polyCube(name="refineOverlapB")[0]
candidateConfirmed = [{"category": "meshCollision", "severity": "warning",
                       "summary": "{} and {} bounding boxes overlap".format(overlapA, overlapB),
                       "axis": None, "meshes": (overlapA, overlapB), "remedy": None}]
refined = diag.refineMeshCollisions(candidateConfirmed)
assert len(refined) == 1 and refined[0]["summary"] == candidateConfirmed[0]["summary"], refined
print("refineMeshCollisions keeps a confirmed polygon collision OK")

# --- refineMeshCollisions: AABB-only overlap dropped ---
separateA = cmds.polyCube(name="refineSeparateA")[0]
separateB = cmds.polyCube(name="refineSeparateB")[0]
cmds.setAttr(separateB + ".translate", 100, 100, 100, type="double3")
candidateFalse = [{"category": "meshCollision", "severity": "warning",
                   "summary": "irrelevant", "axis": None,
                   "meshes": (separateA, separateB), "remedy": None}]
assert diag.refineMeshCollisions(candidateFalse) == [], (
    "an AABB candidate with no real polygon contact must be dropped")
print("refineMeshCollisions drops a false-positive AABB-only pair OK")

# --- refineMeshCollisions: non-mesh geometry falls back to the AABB finding ---
nonMeshLoc = cmds.spaceLocator(name="refineNonMeshLoc")[0]
candidateUnknown = [{"category": "meshCollision", "severity": "warning",
                     "summary": "{} and {} bounding boxes overlap".format(overlapA, nonMeshLoc),
                     "axis": None, "meshes": (overlapA, nonMeshLoc), "remedy": None}]
refined = diag.refineMeshCollisions(candidateUnknown)
assert len(refined) == 1 and "정밀 확인 불가" in refined[0]["summary"], refined
print("refineMeshCollisions falls back to the AABB finding for non-mesh geometry OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
sys.exit(0)
