"""maroLidar 노드가 등록되고 기대한 어트리뷰트/기본값을 갖는지 확인한다."""
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)

cmds.file(new=True, force=True)
lidar = cmds.createNode("maroLidar")
print("created:", lidar)

expected = [
    "verticalSamples",
    "verticalMinAngle",
    "verticalMaxAngle",
    "horizontalSamples",
    "horizontalMinAngle",
    "horizontalMaxAngle",
    "rangeMin",
    "rangeMax",
    "updateRate",
    "frameId",
    "targetMeshes",
    "enabled",
]
for attr in expected:
    assert cmds.attributeQuery(attr, node=lidar, exists=True), f"missing attr: {attr}"
print("attributes OK")

assert cmds.getAttr(lidar + ".verticalSamples") == 4
assert cmds.getAttr(lidar + ".horizontalSamples") == 36
assert cmds.getAttr(lidar + ".rangeMin") == 0.1
assert cmds.getAttr(lidar + ".rangeMax") == 30.0
assert cmds.getAttr(lidar + ".updateRate") == 10.0
assert cmds.getAttr(lidar + ".frameId") == "lidar_link"
assert cmds.getAttr(lidar + ".enabled") is True
print("defaults OK")

# targetMeshes에 실제 메쉬를 연결할 수 있는지 확인한다(capabilityIn과
# 같은 방식 -- 새 바인딩 커맨드 없이 connectAttr로 직접).
cube = cmds.polyCube(name="scanTarget")[0]
cmds.connectAttr(cube + ".message", lidar + ".targetMeshes[0]")
connections = cmds.listConnections(lidar + ".targetMeshes[0]", source=True) or []
assert cube in connections, f"targetMeshes[0] did not connect to {cube}: {connections}"
print("targetMeshes binding OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
