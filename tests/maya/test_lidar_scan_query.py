"""maroQueryLidarScan()의 평탄 배열 계약을 고정한다 -- Tech Diag의 새 LiDAR
동적 검사(다음 태스크)가 이 계약 위에서 동작하므로, 행렬 직렬화 순서가
실제로 Python 쪽 재구성과 맞는지 독립적으로 교차 검증한다(이 프로젝트가
좌표/행렬 계약에서 이미 여러 번 겪은 실수 패턴 -- 손으로 가정하지 않고
실측한다)."""
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.api.OpenMaya as om2  # noqa: E402
import maya.cmds as cmds  # noqa: E402

_pythonDir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "python")
if _pythonDir not in sys.path:
    sys.path.insert(0, _pythonDir)

import maroTechDiag as diag  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)
cmds.currentUnit(angle="rad")
cmds.currentUnit(linear="cm")

# --- kOk: 메쉬 연결 + 히트 있음 ---
lidar = cmds.createNode("maroLidar")
lidar = cmds.ls(lidar, long=True)[0]
cmds.setAttr(lidar + ".verticalSamples", 1)
cmds.setAttr(lidar + ".horizontalSamples", 1)
cmds.setAttr(lidar + ".verticalMinAngle", -1.5707963267948966)
cmds.setAttr(lidar + ".horizontalMinAngle", 0.0)
cmds.setAttr(lidar + ".rangeMin", 0.0)
cmds.setAttr(lidar + ".rangeMax", 5000.0)
ground, _ = cmds.polyPlane(width=2000, height=2000, subdivisionsX=1, subdivisionsY=1)
cmds.setAttr(ground + ".translateY", -500)
cmds.connectAttr(ground + ".message", lidar + ".targetMeshes[0]")

flat = cmds.maroQueryLidarScan(lidar)
parsed = diag.parseLidarScanQuery(flat)
assert parsed["status"] == "kOk", parsed["status"]
# rangeMin/rangeMax attributes are metres (MaroLidarScan.cpp's own contract,
# see test_lidar_commands.py's rangeMin-default comment and
# test_lidar_publish.py's explicit metres regression test); scanLidarNode()
# always converts them to Maya units via mayaPerMeter before handing them to
# Embree, and LidarGeometry.rangeMinMaya/rangeMaxMaya carry that converted
# value (the whole point of exposing them is so Tech Diag's trig doesn't
# have to redo the meters->Maya-units conversion itself). Maya's internal
# linear unit is always centimetres regardless of the scene's UI unit, so
# mayaPerMeter is 100.0 here independent of the currentUnit(linear="cm")
# call above.
mayaPerMeter = 1.0 / om2.MDistance(1.0, om2.MDistance.internalUnit()).asMeters()
assert abs(parsed["rangeMinMaya"] - 0.0 * mayaPerMeter) < 1e-6
assert abs(parsed["rangeMaxMaya"] - 5000.0 * mayaPerMeter) < 1e-6
assert abs(parsed["verticalMinAngle"] - (-1.5707963267948966)) < 1e-9
assert abs(parsed["horizontalMinAngle"] - 0.0) < 1e-9
assert len(parsed["hitPoints"]) == 1, parsed["hitPoints"]
assert abs(parsed["hitPoints"][0][1] - (-500.0)) < 1e-2, parsed["hitPoints"]
print("kOk parse OK")

identity = om2.MMatrix()
for r in range(4):
    for c in range(4):
        # om2.MMatrix (API 2.0) has no __call__ -- unlike the old (API 1.0)
        # OpenMaya.MMatrix, which supports matrix(r, c). Use getElement()
        # instead; this is exactly the kind of matrix-contract mistake this
        # test's own docstring warns about, caught here by actually running
        # this against mayapy rather than assuming the API surface.
        assert abs(parsed["effectiveWorldMatrix"].getElement(r, c) -
                   identity.getElement(r, c)) < 1e-9, (
            r, c, parsed["effectiveWorldMatrix"])
print("identity-mount matrix OK")

# --- 행렬 계약 교차 검증: 비-identity 마운트 + 오프셋 ---
mount = cmds.createNode("transform", name="scanQueryMount")
cmds.setAttr(mount + ".translate", 300, 50, -20, type="double3")
cmds.setAttr(mount + ".rotateZ", 0.4)
lidar2 = cmds.createNode("maroLidar", parent=mount)
lidar2 = cmds.ls(lidar2, long=True)[0]
cmds.setAttr(lidar2 + ".offsetTranslateX", 1.0)
cmds.setAttr(lidar2 + ".offsetRotateY", 0.2)

flat2 = cmds.maroQueryLidarScan(lidar2)
parsed2 = diag.parseLidarScanQuery(flat2)
assert parsed2["status"] == "kNoTargetMesh", parsed2["status"]
assert len(parsed2["hitPoints"]) == 0

# 독립 재구성: MaroLidarScan.cpp와 같은 합성(오프셋 행렬 * 마운트 월드 행렬)을
# Python om2로 별도로 계산해, 커맨드가 돌려준 행렬과 원소 단위로 대조한다.
sel = om2.MSelectionList()
sel.add(lidar2)
mountWorldMatrix = sel.getDagPath(0).inclusiveMatrix()
mayaPerMeter = 100.0  # cm 씬
offsetXform = om2.MTransformationMatrix()
offsetXform.setTranslation(om2.MVector(1.0 * mayaPerMeter, 0.0, 0.0), om2.MSpace.kTransform)
offsetXform.setRotation(om2.MEulerRotation(0.0, 0.2, 0.0))
expectedMatrix = offsetXform.asMatrix() * mountWorldMatrix
for r in range(4):
    for c in range(4):
        assert abs(parsed2["effectiveWorldMatrix"].getElement(r, c) -
                   expectedMatrix.getElement(r, c)) < 1e-6, (
            r, c, parsed2["effectiveWorldMatrix"], expectedMatrix)
print("non-identity-mount matrix cross-check OK")

# --- kInvalidConfig: rangeMax < rangeMin ---
cmds.setAttr(lidar2 + ".rangeMin", 100.0)
cmds.setAttr(lidar2 + ".rangeMax", 1.0)
flat3 = cmds.maroQueryLidarScan(lidar2)
parsed3 = diag.parseLidarScanQuery(flat3)
assert parsed3["status"] == "kInvalidConfig", parsed3["status"]
assert parsed3["rangeMinMaya"] == 0.0 and parsed3["rangeMaxMaya"] == 0.0
assert len(parsed3["hitPoints"]) == 0
print("kInvalidConfig zeroed-header OK")

# --- 잘못된 노드 타입 ---
try:
    cmds.maroQueryLidarScan(ground)
    raise AssertionError("expected maroQueryLidarScan to reject a non-maroLidar argument")
except RuntimeError:
    print("rejects non-maroLidar argument OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
