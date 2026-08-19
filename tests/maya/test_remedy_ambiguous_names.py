"""최종 리뷰 Finding I1: 실패 시점에 담은 이름이 Apply 시점에도 여전히
**같은 하나**를 가리켜야 한다.

Maya 씬에서 같은 짧은 이름이 다른 부모 아래 또 있는 것은 지극히 평범하다
(그룹 둘에 각각 dupCube). 그런데 MSelectionList::add는 엄격한 조회가 아니라
`ls`와 같은 패턴 매치다 -- devkit 시그니처의 인자 이름부터가 matchString이다.
실측(Maya 2026)으로 확인한 동작:

    add("dupCube")          -> kInvalidParameter      (모호한 노드 이름은 거절)
    add("dupCube.message")  -> kSuccess, length()==2  (모호한 플러그 이름은 통과!)

즉 플러그 이름 쪽은 모호해도 "성공"하면서 매치를 전부 담는다. 예전 적용
경로는 리스트 하나에 src와 dst를 차례로 넣고 getPlug(0)/getPlug(1)로 위치를
집었으므로, src가 모호하면 getPlug(1)이 dst가 아니라 **src의 두 번째 매치**를
돌려주고 -- 사용자가 지목한 적도 없는 노드의 연결을 끊게 된다.

이 파일은 그 성질을 두 방향에서 확인한다:
  A. 실제 실패 자리가 담는 이름이 모호하지 않아, 중복 짧은 이름이 있는 씬에서
     Apply가 **올바른** 쪽을 정확히 골라 고치고 다른 쪽은 건드리지 않는다.
  B. 그럼에도 모호한 이름이 레코드에 들어온 경우(스테일 레코드, 이름 변경 등)
     패널은 "적용 가능"이라 말하지 않고, 적용은 아무것도 바꾸지 않은 채
     진단을 남기며 깨끗이 실패한다.

기존 테스트 어느 것도 중복 짧은 이름 씬을 만들지 않아 이 부류를 잡지 못했다.
"""
import os
import time

import maya.standalone
maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    from PySide2.QtWidgets import QApplication  # noqa: F401

_qapp = QApplication.instance() or QApplication([])

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)


def _pumpUntil(predicate, timeoutSeconds=5):
    deadline = time.time() + timeoutSeconds
    while time.time() < deadline:
        _qapp.processEvents()
        time.sleep(0.05)
        if predicate():
            return True
    return False


# --- 중복 짧은 이름을 가진 씬을 만든다 ---
#
# 두 번째 dupCube를 만들기 *전에* 첫 번째의 전체 경로를 잡아 둔다 -- 만든
# 뒤에는 짧은 이름 "dupCube"가 이미 모호해 cmds.ls가 둘을 다 돌려준다.
g1 = cmds.group(empty=True, name="g1")
g2 = cmds.group(empty=True, name="g2")

cubeOne = cmds.parent(cmds.polyCube(name="dupCube")[0], g1)[0]
cubeOnePath = cmds.ls(cubeOne, long=True)[0]
cubeTwo = cmds.parent(cmds.polyCube(name="dupCube")[0], g2)[0]
cubeTwoPath = cmds.listRelatives(g2, children=True, fullPath=True)[0]

assert cubeOnePath != cubeTwoPath, (cubeOnePath, cubeTwoPath)
assert cubeOnePath.rsplit("|", 1)[-1] == cubeTwoPath.rsplit("|", 1)[-1] == "dupCube", (
    "이 테스트의 전제 자체가 깨졌다: 두 노드의 짧은 이름이 같아야 한다")
assert len(cmds.ls("dupCube", long=True)) == 2, cmds.ls("dupCube", long=True)
print("ambiguous short name scene OK")

# 축 둘. 짧은 이름은 유일하게 둔다 -- 이 테스트가 보려는 모호함은 오직
# 소스 플러그(dupCube.message) 쪽이다.
axisOne = cmds.createNode("maroAxis", name="axisOne")
axisTwo = cmds.createNode("maroAxis", name="axisTwo")
axisOnePath = cmds.ls(axisOne, long=True)[0]

cmds.maroBindAxis(axisOne, cubeOnePath)
cmds.maroBindAxis(axisTwo, cubeTwoPath)
assert cmds.isConnected(cubeOnePath + ".message", axisOnePath + ".targetObject")
assert cmds.isConnected(cubeTwoPath + ".message", cmds.ls(axisTwo, long=True)[0] +
                        ".targetObject")
print("both axes bound OK")


# ---------------------------------------------------------------------------
# A. 실제 실패 자리가 담는 이름은 모호하지 않다 -> Apply가 올바른 쪽을 고친다
# ---------------------------------------------------------------------------
# AxisAlreadyBound를 유발한다: axisOne은 이미 cubeOne에 묶여 있는데 또 다른
# 오브젝트에 묶으려 하면 "기존 연결을 끊어라"는 Disconnect 해법이 기록된다.
spare = cmds.polyCube(name="spareCube")[0]
try:
    cmds.maroBindAxis(axisOne, spare)
    raised = False
except RuntimeError:
    raised = True
assert raised, "re-binding an already-bound axis must fail"

seq = int(cmds.maroDiagQuery(index=0)[10])
kind, _, _, _, srcPlug, dstPlug = cmds.maroDiagQueryRemedyAction(sequence=seq)
assert kind == "disconnect", kind

# 여기가 이 테스트의 심장이다: 담긴 이름이 짧은 이름("dupCube.message")이면
# 지금 이 씬에서 둘 중 어느 쪽인지 알 수 없다.
assert srcPlug == cubeOnePath + ".message", (
    "the recorded source plug must be an unambiguous full DAG path, got %r "
    "(a short name cannot tell the two dupCube nodes apart)" % (srcPlug,))
assert dstPlug == axisOnePath + ".targetObject", dstPlug
print("capture records an unambiguous full path OK")

# 패널은 이것을 적용 가능이라고 말해야 한다.
detail = cmds.maroDiagPanelDetail(sequence=seq)
assert detail[11] == "1", (
    "an unambiguous remedy must be applicable, got %r (%r)" % (detail[11], detail[12]))

# 적용한다. 올바른 쪽(axisOne <- cubeOne)만 끊기고, 다른 쪽(axisTwo <-
# cubeTwo)은 그대로여야 한다.
cmds.maroDiagRequestRemedy(sequence=seq)
assert _pumpUntil(lambda: not cmds.isConnected(cubeOnePath + ".message",
                                               axisOnePath + ".targetObject")), \
    "the disconnect remedy never applied to the node it named"
assert cmds.isConnected(cubeTwoPath + ".message",
                        cmds.ls(axisTwo, long=True)[0] + ".targetObject"), \
    "applying the remedy broke a connection on the OTHER node that shares the short name"
print("apply acted on the correct duplicate-named node OK")

cmds.undo()
assert cmds.isConnected(cubeOnePath + ".message", axisOnePath + ".targetObject"), \
    "undo must restore the connection the remedy removed"
print("undo OK")


# ---------------------------------------------------------------------------
# B. 모호한 이름이 레코드에 들어와도 조용히 엉뚱한 것을 건드리지 않는다
# ---------------------------------------------------------------------------
# maroDiagEmit의 테스트 전용 확장으로 짧은(=모호한) 소스 플러그 이름을 직접
# 밀어 넣는다 -- 이름이 바뀐 뒤의 스테일 레코드가 실제로 이 모양이 된다.
cmds.maroDiagEmit(severity="error", message="ambiguous", siteTag="T.Ambiguous",
                  remedyAction="disconnect",
                  remedySourcePlug="dupCube.message",
                  remedyDestPlug=axisOnePath + ".targetObject")
ambiguousSeq = int(cmds.maroDiagQuery(index=0)[10])

# 1) 패널이 "적용 가능"이라 말하면 안 된다. 예전 remedyTargetsExist는
#    add()의 상태만 봤고, "dupCube.message"는 length()==2로 성공하므로
#    죽은 버튼을 내주었다.
detail = cmds.maroDiagPanelDetail(sequence=ambiguousSeq)
assert detail[11] == "0", (
    "an ambiguous name must not be reported as applicable, got %r" % (detail[11],))
assert detail[12] == "TargetNodeMissing", detail[12]
print("panel refuses an ambiguous remedy OK")

# 2) 그래도 적용이 불려 오면(패널 조회와 클릭 사이의 경합을 흉내낸다)
#    아무것도 바꾸지 않고, 진단을 남기며 실패해야 한다.
countBefore = cmds.maroDiagCount()
try:
    cmds.maroApplyRemedy(sequence=ambiguousSeq)
    raised = False
except RuntimeError:
    raised = True
assert raised, "applying an ambiguous remedy must fail rather than guess"

assert cmds.isConnected(cubeOnePath + ".message", axisOnePath + ".targetObject"), \
    "a refused apply must leave the first node's connection alone"
assert cmds.isConnected(cubeTwoPath + ".message",
                        cmds.ls(axisTwo, long=True)[0] + ".targetObject"), \
    "a refused apply must leave the second node's connection alone"

assert cmds.maroDiagCount() > countBefore, \
    "a refused apply must record why -- the queue calls it with displayEnabled=false, " \
    "so an unrecorded failure is completely invisible to the user"
refusal = cmds.maroDiagQuery(index=0)[1]
assert "dupCube.message" in refusal and "matches" in refusal, refusal
print("ambiguous apply fails cleanly with a recorded reason OK")


# ---------------------------------------------------------------------------
# C. selectNode 쪽에도 같은 규율이 걸린다
# ---------------------------------------------------------------------------
# 노드 이름은(플러그와 달리) 모호하면 add() 자체가 실패하므로 예전에도
# 씬을 망가뜨리지는 않았다. 그래도 패널이 그것을 적용 가능이라 말하지
# 않는지, 적용이 깨끗이 실패하는지 같은 규율로 확인한다.
cmds.maroDiagEmit(severity="error", message="ambiguous select", siteTag="T.AmbSelect",
                  remedyAction="selectNode", remedyNode="dupCube")
selSeq = int(cmds.maroDiagQuery(index=0)[10])
detail = cmds.maroDiagPanelDetail(sequence=selSeq)
assert detail[11] == "0", detail[11]

cmds.select(clear=True)
try:
    cmds.maroApplyRemedy(sequence=selSeq)
    raised = False
except RuntimeError:
    raised = True
assert raised, "selecting via an ambiguous name must fail rather than select both"
assert cmds.ls(selection=True) == [], \
    "a refused selectNode remedy must not change the selection"
print("ambiguous selectNode refused OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("test_remedy_ambiguous_names OK")
