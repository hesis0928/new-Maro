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

# --- 최종 리뷰 Finding I2 ---
#
# setAttribute 해법의 "존재한다"는 노드가 아니라 **노드와 그 어트리뷰트**를
# 뜻해야 한다. 예전에는 노드 이름만 확인했으므로, 그 노드에 그 어트리뷰트가
# 아예 없어도 패널이 Apply를 내주었다 -- 그리고 적용은 findPlug에서 아무런
# 기록 없이 실패했다(큐가 displayEnabled=false로 부르므로 스크립트
# 에디터에도 아무것도 안 뜬다). 사용자에게는 "버튼이 영원히 아무 일도 안
# 한다"로만 보였다.
plainCube = cmds.polyCube(name="plainCube")[0]
assert not cmds.attributeQuery("controlMode", node=plainCube, exists=True), \
    "이 테스트의 전제: 평범한 transform에는 controlMode가 없다"

cmds.maroDiagEmit(severity="error", message="m3", siteTag="T.AttrMissing",
                  remedyAction="setAttribute", remedyNode=plainCube,
                  remedyAttribute="controlMode", remedyValue=0.0)
seq3 = int(cmds.maroDiagQuery(index=0)[10])

detail = cmds.maroDiagPanelDetail(sequence=seq3)
assert detail[11] == "0", (
    "a setAttribute remedy whose attribute does not exist on the node must not be "
    "offered as applicable, got %r (%r)" % (detail[11], detail[12]))
assert detail[12] == "TargetNodeMissing", detail[12]
print("setAttribute availability checks the attribute, not just the node OK")

# 패널 조회와 클릭 사이의 경합을 흉내내어 적용을 직접 부른다. 실패하는 것은
# 예전에도 그랬지만, 이제는 **왜** 실패했는지가 boad에 남아야 한다.
countBefore = cmds.maroDiagCount()
try:
    cmds.maroApplyRemedy(sequence=seq3)
    raised = False
except RuntimeError:
    raised = True
assert raised, "applying a setAttribute remedy for a missing attribute must fail"
assert cmds.maroDiagCount() > countBefore, \
    "that failure must be recorded -- an unrecorded failure is invisible to the user"
refusal = cmds.maroDiagQuery(index=0)[1]
assert "controlMode" in refusal and plainCube in refusal, refusal
print("missing-attribute apply fails with a recorded reason OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("test_remedy_availability OK")
