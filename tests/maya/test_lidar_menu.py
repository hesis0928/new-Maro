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

# [I-3] `_createPlaceholderTargetMesh()`가 실제로 부르는 **순간**(placeholder
# 구가 생기기 직전, 그러나 maroLidar 셰이프는 이미 jointObject 밑에 parent돼
# 있는 시점)의 바운딩박스를 가로채서 "독립적인" 기대값으로 따로 저장해 둔다.
#
# 예전 버전은 이 함수가 끝난 **뒤**(구가 이미 jointObject의 자식으로 들어간
# 뒤)에 jointObject의 bbox를 다시 쟀다. 그런데 그 시점의 bbox 상단은 이미
# 구 자신이 만든 것이므로, "재측정한 bbox 상단 - 반지름"은 결국 구가 실제로
# 놓인 위치를 자기 자신에서 반지름을 더했다 뺐다 한 것과 같다 -- 배치 로직이
# 완전히 깨져서 엉뚱한 좌표(y=999 등)에 구를 놓아도 그 값이 그대로 "기대값"
# 계산에 들어가 버려 항상 통과한다(최종 리뷰 I-3, 자기참조 비교). 그래서
# 구가 만들어지기 **전에** 실제로 배치 계산이 본 bbox를 별도로 가로채 둔다
# -- 이러면 구의 실제 배치 결과와 독립적인 참값이 된다.
#
# (참고: jointObject 홑몸은 렌더링되는 지오메트리가 없어 bbox가 비어 있다
# -- 실측 확인 결과 Maya의 빈 바운딩박스 관례인 [1e20, ..., -1e20]이 나온다.
# `_createPlaceholderTargetMesh()`가 실행되는 시점에 실제로 bbox를 만드는
# 것은 이미 물려 있는 maroLidar 로케이터 셰이프의 기본 바운딩박스([-1,1]^3)
# 이다. 그래서 이 값은 `_onLidarMenuItemClicked()`를 부르기 **전**의
# jointObject bbox와 다르다 -- 바깥에서 통짜로 미리 재면 lidar 셰이프가
# 아직 안 붙어 있어 빈 bbox를 잡게 되므로, 함수 호출 도중 lidar 셰이프가
# 이미 붙은 뒤의 순간을 가로채야 한다.)
capturedPreSphereBboxes = []
_originalCreatePlaceholder = maroDagMenu._createPlaceholderTargetMesh


def _capturingCreatePlaceholder(object_):
    capturedPreSphereBboxes.append(cmds.exactWorldBoundingBox(object_))
    return _originalCreatePlaceholder(object_)


maroDagMenu._createPlaceholderTargetMesh = _capturingCreatePlaceholder
try:
    maroDagMenu._onLidarMenuItemClicked(jointObject)
finally:
    maroDagMenu._createPlaceholderTargetMesh = _originalCreatePlaceholder

assert len(capturedPreSphereBboxes) == 1, (
    "expected _createPlaceholderTargetMesh to run exactly once")
preSphereBbox = capturedPreSphereBboxes[0]

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

# [I-3] preSphereBbox는 구가 존재하기 전에 잡은 값이므로 구 자신의 기여를
# 전혀 포함하지 않는다 -- `_createPlaceholderTargetMesh()`는 구의 중심을
# 그 bbox의 상단(ymax)에 그대로 놓으므로(반지름을 빼지 않는다, 소스의
# `topCenter = (..., bbox[4], ...)` 참고), 기대값은 `preSphereBbox[4]`
# 자체다. 배치 로직이 깨져서 엉뚱한 좌표에 구를 놓으면 이 비교가 실제로
# 실패한다(예전의 자기참조 비교와 달리).
placeholderPos = cmds.xform(placeholder[0], query=True, worldSpace=True, translation=True)
expectedY = preSphereBbox[4]
assert abs(placeholderPos[1] - expectedY) < 1e-6, (
    f"expected the placeholder centered at the pre-existing (pre-sphere) bbox top "
    f"y={expectedY}, got y={placeholderPos[1]}")
print("placeholder positioned at bounding-box top OK")

jointLidars = [l for l in cmds.ls(type="maroLidar", long=True) if l != lidar]
assert len(jointLidars) == 1
jointLidar = jointLidars[0]
targets2 = cmds.listConnections(jointLidar + ".targetMeshes", source=True, destination=False) or []
assert placeholder[0] in [cmds.ls(t, long=True)[0] for t in targets2]
print("placeholder used as the new lidar's initial target OK")

# --- 재클릭 (비-메쉬 오브젝트): I-1 -- placeholder로 탑재된 LiDAR도 재클릭
# 시 재사용해야지, 중복 생성하면 안 된다 ------------------------------------
# [I-1] `_findLidarForMesh()`는 예전에 jointObject 자신의 `.message` 연결
# 만 봤다. 그런데 placeholder를 통해 탑재된 LiDAR는 jointObject 자신이
# targetMeshes에 연결되는 게 아니라 placeholder 구가 연결되므로, 그 검사
# 만으로는 이 LiDAR를 찾지 못했다 -- 그래서 (수정 전에는) 이 재클릭이 기존
# LiDAR를 재사용하지 못하고 두 번째 maroLidar/maroPointCloud를 통째로 새로
# 만들었다. 아래 비교가 그 회귀를 잡는다.
openedPanels.clear()
maroDagMenu._onLidarMenuItemClicked(jointObject)

allLidarsAfterReclick = cmds.ls(type="maroLidar", long=True)
assert sorted(allLidarsAfterReclick) == sorted([lidar, jointLidar]), (
    "re-clicking a non-mesh object that already hosts a LiDAR (via a placeholder "
    f"target mesh) must not create a second maroLidar, got {allLidarsAfterReclick}")

# type="transform"로 걸러야 한다 -- 안 그러면 폴리스피어의 셰이프 자식
# ("...TargetShape")까지 같은 접두사로 잡혀서, 진짜 중복이 하나도 없어도
# 길이가 2로 나온다(트랜스폼 1개 + 그 자신의 셰이프 1개). 이름 없이 exact
# match만 쓰면 되레 진짜 중복을 놓친다 -- C-1 수정 덕분에 중복 시도가 나면
# `cmds.parent()`가 이름 충돌을 피해 "...Target1"로 자동으로 바꿔 붙이므로,
# 정확히 옛 이름만 찾는 질의는 그 중복을 못 본다. 접두사 와일드카드 +
# type=transform 조합이라야 "구 트랜스폼이 몇 개 생겼는가"를 이름 접미사와
# 무관하게 제대로 센다.
placeholdersAfterReclick = cmds.ls(
    "lidarTestJoint_maroLidarTarget*", long=True, type="transform")
assert len(placeholdersAfterReclick) == 1, (
    "re-clicking must not create a second placeholder mesh, got "
    f"{placeholdersAfterReclick}")
assert openedPanels == [jointLidar], (
    f"expected re-click to reopen the existing LiDAR's panel, got {openedPanels}")
print("re-click on a non-mesh (placeholder-mounted) object reopens the existing "
      "panel instead of duplicating OK")
