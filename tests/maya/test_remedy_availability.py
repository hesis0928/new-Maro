"""maroDiagPanelDetail의 applyAvailable/applyUnavailableReason이 대상
노드의 실제 존재 여부를 반영하는지 확인한다.
"""
import os

import maya.standalone
maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)

axisA = cmds.createNode("maroAxis", name="axisA")

# selectNode 해법: 노드가 살아있는 동안은 적용 가능해야 한다.
cmds.maroDiagEmit(severity="error", message="m", siteTag="T.Avail",
                  remedyAction="selectNode", remedyNode=axisA)
seq = int(cmds.maroDiagQuery(index=0)[10])
detail = cmds.maroDiagPanelDetail(sequence=seq)
assert detail[11] == "1", f"expected applyAvailable, got {detail[11]} ({detail[12]!r})"
assert detail[12] == "", detail[12]
print("available while node exists OK")

# 노드를 지우면 같은 레코드가 이제 적용 불가여야 한다 -- 레코드 자체는
# 안 바뀌지만(해법은 그 순간의 사실이다), 지금 씬에 그 노드가 없다는
# 사실은 조회할 때마다 다시 확인한다.
cmds.delete(axisA)
detail = cmds.maroDiagPanelDetail(sequence=seq)
assert detail[11] == "0", f"expected not applyAvailable after delete, got {detail[11]}"
assert detail[12] == "TargetNodeMissing", detail[12]
print("unavailable after delete OK")

# disconnect 해법: 두 플러그의 노드가 모두 존재해야 적용 가능하다. 하나만
# 지워도 불가여야 한다.
cubeA = cmds.polyCube()[0]
axisB = cmds.createNode("maroAxis", name="axisB")
cmds.maroBindAxis(axisB, cubeA)
cmds.maroDiagEmit(severity="error", message="m2", siteTag="T.Avail2",
                  remedyAction="disconnect",
                  remedySourcePlug=cubeA + ".message",
                  remedyDestPlug=axisB + ".targetObject")
seq2 = int(cmds.maroDiagQuery(index=0)[10])
detail = cmds.maroDiagPanelDetail(sequence=seq2)
assert detail[11] == "1", f"expected applyAvailable for disconnect, got {detail[11]}"

cmds.delete(cubeA)
detail = cmds.maroDiagPanelDetail(sequence=seq2)
assert detail[11] == "0", "deleting one side of a disconnect pair must disable apply"
assert detail[12] == "TargetNodeMissing", detail[12]
print("disconnect availability OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("test_remedy_availability OK")
