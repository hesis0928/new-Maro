"""maroSnapshotLidarScan의 undo/redo 계약과 실제 스캔 결과를 배치 모드에서
고정한다. 브리지(rclcpp) 없이 동작해야 한다는 것이 이 커맨드의 핵심
요구사항이므로, maroStartBridge를 전혀 부르지 않는다."""
import os

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402
# Task 7 (offsetTranslate/offsetRotate)의 기대값을 독립적으로 유도하는 데만
# 쓴다 -- maya.api.OpenMaya(API 2.0)로 MaroLidarScan.cpp와 같은 행렬 합성을
# Python에서 다시 계산해, C++ 프로덕션 코드를 불러오지 않고도 실제 회전
# 부호/관례와 맞는 기대값을 얻는다(직접 삼각함수로 손으로 부호를 추정하지
# 않는다).
import maya.api.OpenMaya as om2  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)
# 각도 어트리뷰트(MFnUnitAttribute::kAngle)는 내부적으로 라디안이지만
# setAttr/getAttr은 기본 UI 각도 단위(기본값 도)로 값을 해석한다
# (test_lidar_node.py/test_lidar_publish.py와 같은 이유) -- 이걸 빼먹으면
# 아래 라디안 리터럴이 도로 읽혀 verticalMinAngle이 사실상 0에 가까운
# 각도가 되고, 레이가 거의 수평이 되어 아래 평면을 전혀 맞히지 못한다
# (실측: 이 줄 없이 처음 실행했을 때 스캔이 0개의 점을 냈다).
cmds.currentUnit(angle="rad")

# 레이가 확실히 맞을 큰 평면. 라이다 노드를 그 위 원점에 둔다.
groundTransform, _ = cmds.polyPlane(width=100, height=100, subdivisionsX=1, subdivisionsY=1)
cmds.setAttr(groundTransform + ".translateY", -5)

lidar = cmds.createNode("maroLidar")
lidar = cmds.ls(lidar, long=True)[0]
cmds.connectAttr(groundTransform + ".message", lidar + ".targetMeshes[0]")
# 아래를 보도록: 수직 각도를 -90도 근방으로.
cmds.setAttr(lidar + ".verticalMinAngle", -1.5707963267948966)
cmds.setAttr(lidar + ".verticalMaxAngle", -1.4707963267948966)
cmds.setAttr(lidar + ".verticalSamples", 2)
cmds.setAttr(lidar + ".horizontalSamples", 4)
cmds.setAttr(lidar + ".rangeMax", 100.0)
# rangeMin's default (0.1 m) converts to 10 Maya units under the scene's
# default centimeter linear unit (MaroLidarScan.cpp's currentSceneUnit()/
# mayaPerMeter conversion) -- larger than the 5-unit gap to the ground
# plane below, so Embree's near-clip (tnear) would exclude the only
# reachable hit. Empirically confirmed: with the default rangeMin left in
# place, the scan below returns zero points. Force it to 0 so the near
# plane sits at the origin.
cmds.setAttr(lidar + ".rangeMin", 0.0)

pointCloud = cmds.createNode("maroPointCloud")
pointCloud = cmds.ls(pointCloud, long=True)[0]

# cmds.getAttr returns None (not an empty list) for a zero-element
# pointArray attribute -- a Maya quirk for array-typed attributes that
# test_point_cloud_node.py never exercises (it always setAttr's before its
# first getAttr). Empirically confirmed here: treat None as "empty".
before = cmds.getAttr(pointCloud + ".points")
assert before is None or len(before) == 0, (
    f"expected an empty points array before the first scan, got {before}")
print("pre-scan points empty OK")

cmds.maroSnapshotLidarScan(lidar, pointCloud)
after = cmds.getAttr(pointCloud + ".points")
assert after is not None and len(after) > 0, "expected the scan to find hits on the ground plane"
print(f"scan produced {len(after)} points OK")

cmds.undo()
undone = cmds.getAttr(pointCloud + ".points")
assert undone is None or len(undone) == 0, (
    f"expected undo to clear points back to empty, got {undone}")
print("undo OK")

cmds.redo()
redone = cmds.getAttr(pointCloud + ".points")
assert len(redone) == len(after), "expected redo to restore the same scan result"
print("redo OK")

# 브리지가 꺼져 있는 상태에서 전부 동작했다는 것이 이 커맨드의 핵심 계약이다.
assert cmds.maroBridgeStats()[0] == 0, "this test must not have started the bridge"
print("bridge-independence OK")

# 잘못된 노드 타입은 거부돼야 한다.
try:
    cmds.maroSnapshotLidarScan(groundTransform, pointCloud)
    raise AssertionError("expected maroSnapshotLidarScan to reject a non-maroLidar first argument")
except RuntimeError:
    print("rejects non-maroLidar first argument OK")

# ---- Task 7: offsetTranslate/offsetRotate actually move the ray geometry ----
# A fresh, minimal scene: a single ray (verticalSamples=horizontalSamples=1)
# pointed straight down at a large flat ground plane, so the expected hit
# point is exactly derivable rather than eyeballed. computeRayDirections
# (RayPattern.cpp's angleAt) uses only the *min* angle when samples<=1, so
# only verticalMinAngle/horizontalMinAngle matter here.
offsetGround, _ = cmds.polyPlane(
    width=2000, height=2000, subdivisionsX=1, subdivisionsY=1, name="offsetGround")
cmds.setAttr(offsetGround + ".translateY", -1000)

offsetLidar = cmds.createNode("maroLidar")
offsetLidar = cmds.ls(offsetLidar, long=True)[0]
cmds.connectAttr(offsetGround + ".message", offsetLidar + ".targetMeshes[0]")
cmds.setAttr(offsetLidar + ".verticalSamples", 1)
cmds.setAttr(offsetLidar + ".horizontalSamples", 1)
cmds.setAttr(offsetLidar + ".verticalMinAngle", -1.5707963267948966)  # straight down
cmds.setAttr(offsetLidar + ".horizontalMinAngle", 0.0)
cmds.setAttr(offsetLidar + ".rangeMin", 0.0)
cmds.setAttr(offsetLidar + ".rangeMax", 5000.0)

offsetPointCloud = cmds.createNode("maroPointCloud")
offsetPointCloud = cmds.ls(offsetPointCloud, long=True)[0]


def _singleHit(lidarName, cloudName):
    cmds.maroSnapshotLidarScan(lidarName, cloudName)
    points = cmds.getAttr(cloudName + ".points")
    # cmds.getAttr on a pointArray attribute returns a list with one
    # (x, y, z[, w]) tuple per point (confirmed empirically here).
    assert points is not None and len(points) == 1, (
        f"expected exactly one hit point, got {points}")
    return points[0]


baselineHit = _singleHit(offsetLidar, offsetPointCloud)
assert abs(baselineHit[0] - 0.0) < 1e-4
assert abs(baselineHit[1] - (-1000.0)) < 1e-4
assert abs(baselineHit[2] - 0.0) < 1e-4
print(f"offset baseline hit {baselineHit} OK")

# mayaPerMeter: MaroLidarScan.cpp's own conversion, mirrored here
# (MDistance(1.0, internalUnit()).asMeters() -- Maya's internal unit is
# always centimeters, so this is 100.0, matching the rangeMin/rangeMax
# convention documented elsewhere in this file).
mayaPerMeter = 1.0 / om2.MDistance(1.0, om2.MDistance.internalUnit()).asMeters()

# ---- offsetTranslateX: pure local-space translation, ray direction is
# unaffected (translation cancels out of the direction-vector math), so
# only the hit's X should move, by exactly offsetMeters * mayaPerMeter.
offsetMeters = 2.0
cmds.setAttr(offsetLidar + ".offsetTranslateX", offsetMeters)
translatedHit = _singleHit(offsetLidar, offsetPointCloud)
expectedX = offsetMeters * mayaPerMeter
assert abs(translatedHit[0] - expectedX) < 1e-2, (
    f"expected hit x ~= {expectedX} after offsetTranslateX={offsetMeters}m, "
    f"got {translatedHit}")
assert abs(translatedHit[1] - (-1000.0)) < 1e-2
assert abs(translatedHit[2] - 0.0) < 1e-2
print(f"offsetTranslateX OK (expected x={expectedX}, got {translatedHit[0]})")
cmds.setAttr(offsetLidar + ".offsetTranslateX", 0.0)

# ---- offsetRotateX: tilts the (local) straight-down ray direction. Rather
# than deriving the rotation's sign/convention by hand, mirror
# MaroLidarScan.cpp's exact composition (local offset matrix * mount world
# matrix, then apply to the local ray direction and subtract the
# direction-only bias) using maya.api.OpenMaya -- an independent Maya API
# binding computing the same underlying transform math, so this is a real
# cross-check of the production code's matrix composition, not an assumed
# sign eyeballed into a magic constant.
rotateAngle = 0.3  # radians
offsetXform = om2.MTransformationMatrix()
offsetXform.setRotation(om2.MEulerRotation(rotateAngle, 0.0, 0.0))
offsetMatrix = offsetXform.asMatrix()
mountWorldMatrix = om2.MMatrix()  # offsetLidar itself has an identity transform
effectiveMatrix = offsetMatrix * mountWorldMatrix

localDir = om2.MVector(0.0, -1.0, 0.0)  # matches computeRayDirections at vertical=-pi/2
originVec = om2.MPoint(0.0, 0.0, 0.0) * effectiveMatrix
directionBias = om2.MVector(0.0, 0.0, 0.0) * effectiveMatrix
worldDir = (localDir * effectiveMatrix) - directionBias
worldDir.normalize()

groundY = -1000.0
t = (groundY - originVec.y) / worldDir.y
expectedHit = (
    originVec.x + worldDir.x * t,
    originVec.y + worldDir.y * t,
    originVec.z + worldDir.z * t,
)

cmds.setAttr(offsetLidar + ".offsetRotateX", rotateAngle)
rotatedHit = _singleHit(offsetLidar, offsetPointCloud)
for actual, expected, axis in zip(rotatedHit, expectedHit, "xyz"):
    assert abs(actual - expected) < 1e-2, (
        f"offsetRotateX={rotateAngle}: expected hit {axis}~={expected}, "
        f"got {rotatedHit} (full expected {expectedHit})")
print(f"offsetRotateX OK (expected {expectedHit}, got {rotatedHit})")
cmds.setAttr(offsetLidar + ".offsetRotateX", 0.0)

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
