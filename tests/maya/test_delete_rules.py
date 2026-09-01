"""삭제 비대칭성과 고아 능력 노드 규칙."""
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

# 오브젝트를 지우면 축도 사라진다.
cube = cmds.polyCube(name="seg")[0]
axis = cmds.createNode("maroAxis", name="axisA")
cmds.maroBindAxis(axis, cube)
cmds.delete(cube)
assert not cmds.objExists(axis), "axis should be deleted along with its object"
print("cascade delete OK")

# undo 하면 둘 다 돌아온다 (같은 undo 청크).
cmds.undo()
assert cmds.objExists(cube), "object should come back on undo"
assert cmds.objExists(axis), "axis should come back on undo, in the same chunk"
print("cascade undo OK")

# 축을 지워도 오브젝트는 남는다.
cmds.delete(axis)
assert cmds.objExists(cube), "deleting an axis must not delete its object"
print("asymmetry OK")

# 축을 지우면 능력 노드는 남고 고아 세트에 담긴다.
cube2 = cmds.polyCube(name="seg2")[0]
axis2 = cmds.createNode("maroAxis", name="axisB")
cmds.maroBindAxis(axis2, cube2)
rot = cmds.createNode("maroRotation", name="rotB")
cmds.connectAttr(rot + ".capabilityOut", axis2 + ".capabilityIn[0]")

cmds.delete(axis2)
assert cmds.objExists(rot), "capability node must survive axis deletion"
assert cmds.objExists("maroOrphanSet"), "orphan set should exist"
members = cmds.sets("maroOrphanSet", query=True) or []
assert rot in members, f"orphan not registered in set: {members}"
print("orphan OK")

# 오브젝트를 지우면 축이 캐스케이드되고, 축에 물려 있던 능력 노드도
# 고아 세트에 담긴다.
cube3 = cmds.polyCube(name="seg3")[0]
axis3 = cmds.createNode("maroAxis", name="axisC")
cmds.maroBindAxis(axis3, cube3)
rot3 = cmds.createNode("maroRotation", name="rotC")
cmds.connectAttr(rot3 + ".capabilityOut", axis3 + ".capabilityIn[0]")

cmds.delete(cube3)
assert not cmds.objExists(axis3), "axis should cascade-delete with its object"
assert cmds.objExists(rot3), "capability node must survive the cascade"
members = cmds.sets("maroOrphanSet", query=True) or []
assert rot3 in members, f"cascaded axis's capability node not orphaned: {members}"
print("cascade plus orphan OK")

# undo 하면 능력 노드는 복원된 축 스택에만 있어야 하고, 고아 세트에는
# 더 이상 남아 있으면 안 된다. maroOrphanSet이 이미 존재하는 상태에서
# 검증해야 한다 (세트 생성 자체가 undo로 함께 사라지면 버그가 가려진다).
assert cmds.objExists("maroOrphanSet"), "orphan set must already exist for this check"
cmds.undo()
assert cmds.objExists(axis3), "axis should come back on undo"
assert cmds.objExists(cube3), "object should come back on undo"
stack_sources = cmds.listConnections(axis3 + ".capabilityIn[0]", source=True) or []
assert rot3 in stack_sources, "capability node should be back in the restored axis stack"
members = cmds.sets("maroOrphanSet", query=True) or []
assert rot3 not in members, (
    f"capability node still listed in maroOrphanSet after undo restored it "
    f"to the axis stack: {members}"
)
print("undo restores orphan state OK")

# 캐스케이드 삭제 후에는 빈 트랜스폼이 남지 않아야 한다.
cube4 = cmds.polyCube(name="seg4")[0]
axis4 = cmds.createNode("maroAxis", name="axisD")
axis4_parent = cmds.listRelatives(axis4, parent=True, fullPath=True)[0]
cmds.maroBindAxis(axis4, cube4)
cmds.delete(cube4)
assert not cmds.objExists(axis4), "axis should cascade-delete with its object"
assert not cmds.objExists(axis4_parent), (
    "empty parent transform should be deleted along with the axis shape"
)
print("no stray transform OK")

# 부모 트랜스폼에 축 셰이프 말고 다른 자식이 남아 있으면, 캐스케이드 삭제가
# 그 트랜스폼까지 지우면 안 된다 (다른 오브젝트가 함께 딸려 사라지면 안 됨).
cube5 = cmds.polyCube(name="seg5")[0]
axis5 = cmds.createNode("maroAxis", name="axisE")
axis5_parent = cmds.listRelatives(axis5, parent=True, fullPath=True)[0]
sibling = cmds.polyCube(name="seg5Sibling")[0]
sibling = cmds.parent(sibling, axis5_parent)[0]
cmds.maroBindAxis(axis5, cube5)
cmds.delete(cube5)
assert not cmds.objExists(axis5), "axis should still cascade-delete with its object"
assert cmds.objExists(axis5_parent), (
    "parent transform with another child must survive the cascade delete"
)
assert cmds.objExists(sibling), (
    "the other child under the parent transform must not be swept away"
)
print("guard keeps shared parent transform OK")

# --- [최종 리뷰 I-4] maroLidar / maroPointCloud 쌍의 삭제 수명주기 ---------
#
# 회귀 전: MaroDeleteWatcher는 maroAxis와 능력 노드 네 종류만 알았고
# maroLidar/maroPointCloud는 전혀 몰랐다. 그래서 마킹 메뉴가 만든 배치에서
# 탑재 오브젝트를 지우면 -- maroLidar는 그 오브젝트의 DAG 자식이라 함께
# 사라지지만 -- maroPointCloud는 전혀 다른 부모(공유 프록시 그룹) 밑에 있어
# 살아남아 마지막 스캔 스냅샷을 영원히 그리는 고아가 됐다.
import maroDagMenu  # noqa: E402
import maroLidarPanel  # noqa: E402

# 설정 팝업은 QWidget을 만들어 배치 mayapy를 abort시킨다 -- 기록용 스텁으로
# 바꿔친다(tests/maya/test_lidar_menu.py와 같은 이유, 같은 방식).
maroLidarPanel.openLidarPanel = lambda lidar: None

lidarCube = cmds.ls(cmds.polyCube(name="lidarDeleteCube")[0], long=True)[0]
maroDagMenu._onLidarMenuItemClicked(lidarCube)

lidarShape = cmds.ls(type="maroLidar", long=True)
assert len(lidarShape) == 1, f"expected exactly one maroLidar, got {lidarShape}"
lidarShape = lidarShape[0]
lidarCloud = cmds.ls(type="maroPointCloud", long=True)
assert len(lidarCloud) == 1, f"expected exactly one maroPointCloud, got {lidarCloud}"
lidarCloud = lidarCloud[0]

# (a) 탑재 오브젝트를 지우면 라이다도, 짝인 포인트클라우드도 함께 사라진다.
cmds.delete(lidarCube)
assert not cmds.objExists(lidarShape), (
    "the maroLidar shape must go away with the mount object it is parented under")
assert not cmds.objExists(lidarCloud), (
    "the paired maroPointCloud must be cascade-deleted with its source lidar -- "
    "otherwise it lingers under the shared proxy group forever, still drawing its "
    "last scan snapshot (final review I-4)")
print("lidar/point-cloud cascade delete OK")

# (b) 같은 undo 청크다 -- 사용자의 삭제 한 번을 Ctrl+Z 한 번으로 되돌린다.
cmds.undo()
assert cmds.objExists(lidarCube), "the mount object should come back on undo"
assert cmds.objExists(lidarShape), "the lidar should come back on undo"
assert cmds.objExists(lidarCloud), (
    "the point cloud must come back in the SAME undo chunk -- the cascade rides on "
    "the MDGModifier Maya hands the aboutToDelete callback")
print("lidar/point-cloud cascade undo OK")

# (c) 라이다만 직접 지워도 짝은 따라간다.
cmds.delete(lidarShape)
assert not cmds.objExists(lidarCloud), (
    "deleting the maroLidar itself must also take its paired maroPointCloud")
assert cmds.objExists(lidarCube), (
    "deleting a lidar must not delete the object it was mounted on")
print("lidar-only delete still takes the point cloud OK")

# (d) 비대칭 확인: 포인트클라우드만 지우는 것은 "시각화를 끈다"는 뜻이지
#     "센서를 없앤다"는 뜻이 아니다 -- 라이다는 살아남아야 한다.
cmds.undo()   # (c)를 되돌려 쌍을 복구한다
assert cmds.objExists(lidarShape) and cmds.objExists(lidarCloud), (
    "undo should restore both halves of the pair")
cmds.delete(lidarCloud)
assert cmds.objExists(lidarShape), (
    "deleting the point cloud must NOT delete its source lidar (the asymmetry is "
    "deliberate -- see MaroDeleteWatcher.h)")
print("point-cloud-only delete leaves the lidar alone OK")

cmds.file(new=True, force=True)

# Maya는 커스텀 노드 인스턴스가 씬에 남아 있으면 플러그인을 언로드하지 않는다.
cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
