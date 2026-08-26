"""maroDagMenu의 "Maro LiDAR" 항목 핸들러(_onLidarMenuItemClicked)가 만드는
노드 그래프를 배치 모드에서 고정한다.

_onMenuItemClicked()(축 생성)와 달리 이 핸들러는 promptDialog/colorEditor
같은 모달 다이얼로그를 쓰지 않으므로 배치에서 직접 호출할 수 있다. 다만
마지막에 여는 설정 팝업(maroLidarPanel.openLidarPanel)은 QWidget을 만들어
배치 mayapy 프로세스를 abort시키므로, 그 함수를 기록용 스텁으로 바꿔치기
한다."""
import os

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
pluginDir = os.path.dirname(plugin)
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

import maroDagMenu  # noqa: E402
import maroLidarPanel  # noqa: E402

openedPanels = []
maroLidarPanel.openLidarPanel = lambda lidar: openedPanels.append(lidar)

# --- 메쉬가 있는 오브젝트 -----------------------------------------------
meshTransform, _ = cmds.polyCube(name="lidarTestCube")
maroDagMenu._onLidarMenuItemClicked(cmds.ls(meshTransform, long=True)[0])

lidars = cmds.ls(type="maroLidar", long=True)
assert len(lidars) == 1, f"expected exactly one maroLidar, got {lidars}"
lidar = lidars[0]

lidarParents = cmds.listRelatives(lidar, parent=True, fullPath=True) or []
assert lidarParents and lidarParents[0] == cmds.ls(meshTransform, long=True)[0], (
    "the LiDAR's transform must be parented under the clicked mesh")
print("lidar mounted under mesh transform OK")

targets = cmds.listConnections(lidar + ".targetMeshes", source=True, destination=False) or []
assert cmds.ls(meshTransform, long=True)[0] in [cmds.ls(t, long=True)[0] for t in targets], (
    "the clicked mesh itself must become the initial target -- no placeholder should be created")
print("mesh used directly as target (no placeholder) OK")

pointClouds = cmds.ls(type="maroPointCloud", long=True)
assert len(pointClouds) == 1
pointCloudParents = cmds.listRelatives(pointClouds[0], parent=True, fullPath=True) or []
import maroRosProxy  # noqa: E402
assert pointCloudParents and pointCloudParents[0] == maroRosProxy._PROXY_GROUP_PATH, (
    "the point cloud must be parented under maroRosProxy_grp for free viewport isolation")
print("point cloud parented under the ROS proxy group OK")

sourceLidarConnections = cmds.listConnections(
    pointClouds[0] + ".sourceLidar", shapes=True) or []
assert sourceLidarConnections and cmds.ls(sourceLidarConnections[0], long=True)[0] == lidar, (
    "the point cloud's sourceLidar must point back at the lidar that created it")
print("sourceLidar back-reference OK")

assert openedPanels == [lidar], f"expected openLidarPanel to be called with {lidar!r}, got {openedPanels}"
print("settings panel opened on creation OK")

# --- 재클릭: 재생성이 아니라 재오픈이어야 한다 ---------------------------
openedPanels.clear()
maroDagMenu._onLidarMenuItemClicked(cmds.ls(meshTransform, long=True)[0])
assert len(cmds.ls(type="maroLidar", long=True)) == 1, (
    "re-clicking a mesh that already has a LiDAR must not create a second one")
assert openedPanels == [lidar]
print("re-click reopens the existing panel instead of duplicating OK")

# --- 메쉬가 없는 오브젝트: placeholder 구 자동 생성 -----------------------
jointObject = cmds.createNode("joint", name="lidarTestJoint")
jointObject = cmds.ls(jointObject, long=True)[0]
cmds.xform(jointObject, worldSpace=True, translation=(10, 3, 0))
openedPanels.clear()
maroDagMenu._onLidarMenuItemClicked(jointObject)

placeholder = cmds.ls("lidarTestJoint_maroLidarTarget", long=True)
assert len(placeholder) == 1, "expected exactly one placeholder mesh to be created"
placeholderParents = cmds.listRelatives(placeholder[0], parent=True, fullPath=True) or []
assert placeholderParents and placeholderParents[0] == jointObject, (
    "the placeholder mesh must be a child of the clicked object")
print("placeholder mesh created as a child OK")

selection = cmds.ls(selection=True, long=True) or []
assert selection == [placeholder[0]], (
    f"expected the placeholder to be selected after creation, got {selection}")
print("placeholder auto-selected OK")

# [빌드 검증 중 실측으로 발견] 여기서 다시 재는 bbox는 방금 만든 placeholder
# 구 자신을 포함한다. `_createPlaceholderTargetMesh`는 구가 생기기 **전**의
# bbox 상단에 구의 중심을 놓으므로(설계 스펙 §5.2 그대로), 그 중심에서 구
# 자신의 반지름(polySphere radius=1.0, 코드에 하드코딩된 값과 같다)만큼 위로
# 더 자란 것이 바로 지금 다시 잰 bbox의 상단이다 -- 그래서 반지름만큼 빼서
# 되짚어야 방금 세팅한 중심과 같아진다. (참고: jointObject 자신은 렌더링되는
# 지오메트리가 없어 bbox가 비어 있다 -- 이 시점에 실제로 bbox를 만드는 것은
# 이미 물려 있는 maroLidar 로케이터 셰이프의 기본 바운딩박스([-1,1]^3)이고,
# 구가 그보다 더 높이 자라 새 상단이 된다.)
sphereRadius = 1.0
bbox = cmds.exactWorldBoundingBox(jointObject)
placeholderPos = cmds.xform(placeholder[0], query=True, worldSpace=True, translation=True)
expectedY = bbox[4] - sphereRadius
assert abs(placeholderPos[1] - expectedY) < 1e-6, (
    f"expected the placeholder centered at the pre-existing bbox top "
    f"(re-measured bbox top={bbox[4]}, radius={sphereRadius} -> expected center "
    f"y={expectedY}), got y={placeholderPos[1]}")
print("placeholder positioned at bounding-box top OK")

secondLidar = [l for l in cmds.ls(type="maroLidar", long=True) if l != lidar]
assert len(secondLidar) == 1
targets2 = cmds.listConnections(secondLidar[0] + ".targetMeshes", source=True, destination=False) or []
assert placeholder[0] in [cmds.ls(t, long=True)[0] for t in targets2]
print("placeholder used as the new lidar's initial target OK")
