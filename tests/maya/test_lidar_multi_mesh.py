"""scanLidarNode()의 다중 메쉬 지원을 고정한다 -- 이전에는 targetMeshes[]에서
첫 번째로 연결된 메쉬만 스캔 대상이었다(설계 스펙 §3.1). 이 테스트는 (a) 첫
번째가 아닌 인덱스에 연결된 메쉬도 실제로 스캔되는지, (b) 여러 타겟 메쉬가
레이 경로에 겹칠 때 가장 가까운 히트가 물리적으로 맞게 나오는지, (c) 폴리곤이
아닌 항목이 섞여도 나머지로 스캔이 계속되는지를 확인한다."""
import os

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)
cmds.currentUnit(angle="rad")

# 곧장 아래를 보는 레이 하나(test_lidar_commands.py와 같은 관례:
# computeRayDirections(vertical=-pi/2)는 로컬 (0,-1,0)을 낸다).
lidar = cmds.createNode("maroLidar")
lidar = cmds.ls(lidar, long=True)[0]
cmds.setAttr(lidar + ".verticalSamples", 1)
cmds.setAttr(lidar + ".horizontalSamples", 1)
cmds.setAttr(lidar + ".verticalMinAngle", -1.5707963267948966)
cmds.setAttr(lidar + ".horizontalMinAngle", 0.0)
cmds.setAttr(lidar + ".rangeMin", 0.0)
cmds.setAttr(lidar + ".rangeMax", 5000.0)

pointCloud = cmds.createNode("maroPointCloud")
pointCloud = cmds.ls(pointCloud, long=True)[0]


def _points(lidarName, cloudName):
    cmds.maroSnapshotLidarScan(lidarName, cloudName)
    pts = cmds.getAttr(cloudName + ".points")
    return pts if pts else []


# targetMeshes[0]: 레이 경로 밖(x=2000 근방)에 둬서 절대 안 맞게 한다.
offPathPlane, _ = cmds.polyPlane(
    name="offPathPlane", width=100, height=100, subdivisionsX=1, subdivisionsY=1)
cmds.setAttr(offPathPlane + ".translateX", 2000)
cmds.connectAttr(offPathPlane + ".message", lidar + ".targetMeshes[0]")

before = _points(lidar, pointCloud)
assert len(before) == 0, (
    "sanity check: a target mesh outside the ray path must not be hit, got {}".format(before))
print("off-path-only sanity OK")

# targetMeshes[1] (인덱스 0이 아님): 레이 경로 위, Y=-500.
nearPlane, _ = cmds.polyPlane(
    name="nearPlane", width=2000, height=2000, subdivisionsX=1, subdivisionsY=1)
cmds.setAttr(nearPlane + ".translateY", -500)
cmds.connectAttr(nearPlane + ".message", lidar + ".targetMeshes[1]")

afterSecondIndex = _points(lidar, pointCloud)
assert len(afterSecondIndex) == 1, (
    "expected the ray to hit nearPlane connected at targetMeshes[1] (previously "
    "ignored -- only targetMeshes[0] was ever scanned), got {}".format(afterSecondIndex))
assert abs(afterSecondIndex[0][1] - (-500.0)) < 1e-2, afterSecondIndex
print("second-index target mesh is now scanned OK (regression for the pre-fix bug)")

# targetMeshes[2]: 레이 경로 위, nearPlane보다 더 먼 Y=-800. 가장 가까운
# 히트(-500)가 나와야지, 병합 순서와 무관하게 더 먼 평면에 가려지면 안 된다.
farPlane, _ = cmds.polyPlane(
    name="farPlane", width=2000, height=2000, subdivisionsX=1, subdivisionsY=1)
cmds.setAttr(farPlane + ".translateY", -800)
cmds.connectAttr(farPlane + ".message", lidar + ".targetMeshes[2]")

afterThreeMeshes = _points(lidar, pointCloud)
assert len(afterThreeMeshes) == 1, (
    "expected exactly one nearest hit across three merged target meshes, "
    "got {}".format(afterThreeMeshes))
assert abs(afterThreeMeshes[0][1] - (-500.0)) < 1e-2, (
    "expected the nearest hit (Y=-500, nearPlane) to win over the farther "
    "plane (Y=-800), got {}".format(afterThreeMeshes))
print("nearest-hit occlusion across 3 merged target meshes OK")

# 메쉬가 아닌 트랜스폼이 targetMeshes에 섞여 있어도(설계 스펙 §3.3의 부분
# 실패 관용) 나머지 유효한 메쉬로 스캔이 계속돼야 한다.
nonMeshNode = cmds.createNode("transform", name="notAMesh")
cmds.connectAttr(nonMeshNode + ".message", lidar + ".targetMeshes[3]")
afterNonMesh = _points(lidar, pointCloud)
assert len(afterNonMesh) == 1, (
    "a non-mesh entry in targetMeshes must be skipped, not fail the whole "
    "scan, got {}".format(afterNonMesh))
assert abs(afterNonMesh[0][1] - (-500.0)) < 1e-2, afterNonMesh
print("partial-extraction-failure tolerance (non-mesh target) OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
