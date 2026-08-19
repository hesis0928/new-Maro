"""error()가 받은 RemedyAction이 레코드에 그대로 실리고, 순번으로 다시
찾아지는지 확인한다. maroDiagEmit의 테스트 전용 확장(-remedyAction 등)만
쓴다 -- 실제 실패 자리 배선은 Task 3에서 별도로 검증한다.
"""
import os

import maya.standalone

# 다른 tests/maya/*.py와 같은 관례: MAYA_PLUG_IN_PATH는 이 스위트의 어떤
# CMake 설정에서도 채워지지 않으므로(grep 확인됨), loadPlugin에 이름만
# 넘기면 "not found on MAYA_PLUG_IN_PATH"로 실패한다. MARO_PLUGIN_PATH가
# 들고 있는 빌드 산출물의 전체 경로를 그대로 넘긴다(test_diag_book.py 등).
maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)

# 1) None(기본값) -- 아무 remedy 플래그도 안 주면 이전과 동일해야 한다.
cmds.maroDiagEmit(severity="error", message="m1", siteTag="T.None")
count = cmds.maroDiagCount()
detail = cmds.maroDiagQuery(index=0)
seq1 = int(detail[10])
kind, nodeName, attrName, value, srcPlug, dstPlug = cmds.maroDiagQueryRemedyAction(sequence=seq1)
assert kind == "none", f"expected no remedy, got {kind}"
print("none OK")

# 2) selectNode
cmds.maroDiagEmit(severity="error", message="m2", siteTag="T.Select",
                  remedyAction="selectNode", remedyNode="axisA")
seq2 = int(cmds.maroDiagQuery(index=0)[10])
kind, nodeName, attrName, value, srcPlug, dstPlug = cmds.maroDiagQueryRemedyAction(sequence=seq2)
assert kind == "selectNode", kind
assert nodeName == "axisA", nodeName
print("selectNode capture OK")

# 3) setAttribute
cmds.maroDiagEmit(severity="error", message="m3", siteTag="T.SetAttr",
                  remedyAction="setAttribute", remedyNode="axisA",
                  remedyAttribute="controlMode", remedyValue=0.0)
seq3 = int(cmds.maroDiagQuery(index=0)[10])
kind, nodeName, attrName, value, srcPlug, dstPlug = cmds.maroDiagQueryRemedyAction(sequence=seq3)
assert kind == "setAttribute", kind
assert nodeName == "axisA" and attrName == "controlMode", (nodeName, attrName)
assert float(value) == 0.0, value
print("setAttribute capture OK")

# 4) disconnect
cmds.maroDiagEmit(severity="error", message="m4", siteTag="T.Disconnect",
                  remedyAction="disconnect", remedySourcePlug="cubeA.message",
                  remedyDestPlug="axisA.targetObject")
seq4 = int(cmds.maroDiagQuery(index=0)[10])
kind, nodeName, attrName, value, srcPlug, dstPlug = cmds.maroDiagQueryRemedyAction(sequence=seq4)
assert kind == "disconnect", kind
assert srcPlug == "cubeA.message" and dstPlug == "axisA.targetObject", (srcPlug, dstPlug)
print("disconnect capture OK")

# 5) 존재하지 않는 순번은 실패해야 한다 -- 스테일 선택을 조용히 다른
# 레코드로 대체하면 안 된다는 것이 이 프로젝트의 확립된 규율이다
# (MaroPanelCommands.cpp의 -sequence 규율과 같다).
try:
    cmds.maroDiagQueryRemedyAction(sequence=999999)
    raised = False
except RuntimeError:
    raised = True
assert raised, "an unknown sequence must fail, not silently return a neighbor"
print("unknown sequence fails OK")

# --- 여기부터는 테스트 전용 확장이 아니라 Task 3에서 배선한 실제 실패
# 자리를 직접 유발해 RemedyAction이 진짜로 채워지는지 확인한다. ---

cube = cmds.polyCube()[0]
shape = cmds.listRelatives(cube, shapes=True)[0]
axisA = cmds.createNode("maroAxis", name="axisA")
axisB = cmds.createNode("maroAxis", name="axisB")

# 최종 리뷰 Finding I1 이후로 이 자리들은 전부 짧은 이름이 아니라 모호하지
# 않은 전체 DAG 경로를 담는다(MaroCommands.cpp의 unambiguousNodeName /
# unambiguousPlugName). 짧은 이름은 나중에 Apply를 누르는 시점에 같은 하나를
# 가리킨다는 보장이 없기 때문이다 -- 같은 짧은 이름이 다른 부모 아래 또 있는
# 씬은 지극히 평범하다. 아래 비교는 전부 그 전체 경로 기준이다.
# (maroAxis는 MPxLocatorNode 파생이라 자동 생성된 transform 밑의 shape이다:
#  "axisA"의 전체 경로는 "|transform1|axisA" 꼴이 된다.)
cubePath = cmds.ls(cube, long=True)[0]
axisAPath = cmds.ls(axisA, long=True)[0]

# TargetNotTransform: shape을 바인딩 시도 -> 부모 transform을 selectNode.
try:
    cmds.maroBindAxis(axisA, shape)
    raised = False
except RuntimeError:
    raised = True
assert raised, "binding a shape must fail"
seq = int(cmds.maroDiagQuery(index=0)[10])
kind, nodeName, _, _, _, _ = cmds.maroDiagQueryRemedyAction(sequence=seq)
# MaroCommands.cpp의 TargetNotTransform 자리는 MFnDagNode::fullPathName()으로
# 부모를 담는다 (같은 짧은 이름이 다른 부모 아래 또 있을 수 있어 모호하지
# 않은 전체 DAG 경로가 필요하다) -- cmds.polyCube()가 돌려주는 짧은 이름과는
# "|" 유무만 다르므로 cmds.ls(long=True)로 정규화해 비교한다.
assert kind == "selectNode" and nodeName == cmds.ls(cube, long=True)[0], (
    kind, nodeName)
print("TargetNotTransform remedy OK")

# AxisAlreadyBound: axisA를 cube에 바인딩한 뒤 또 다른 오브젝트에 바인딩
# 시도 -> 기존 연결을 disconnect.
cmds.maroBindAxis(axisA, cube)
cube2 = cmds.polyCube()[0]
try:
    cmds.maroBindAxis(axisA, cube2)
    raised = False
except RuntimeError:
    raised = True
assert raised, "re-binding an already-bound axis must fail"
seq = int(cmds.maroDiagQuery(index=0)[10])
kind, _, _, _, srcPlug, dstPlug = cmds.maroDiagQueryRemedyAction(sequence=seq)
assert kind == "disconnect", kind
assert srcPlug == cubePath + ".message" and dstPlug == axisAPath + ".targetObject", (
    srcPlug, dstPlug)
print("AxisAlreadyBound remedy OK")

# ObjectAlreadyHasAxis: cube는 이미 axisA에 묶여 있다. axisB로도 바인딩
# 시도 -> 기존 연결을 disconnect.
try:
    cmds.maroBindAxis(axisB, cube)
    raised = False
except RuntimeError:
    raised = True
assert raised, "binding an already-claimed object must fail"
seq = int(cmds.maroDiagQuery(index=0)[10])
kind, _, _, _, srcPlug, dstPlug = cmds.maroDiagQueryRemedyAction(sequence=seq)
assert kind == "disconnect", kind
assert dstPlug == axisAPath + ".targetObject", dstPlug
print("ObjectAlreadyHasAxis remedy OK")

# InvalidControlMode: SetAttribute(controlMode, 0).
try:
    cmds.maroSetControlMode(axisA, 5)
    raised = False
except RuntimeError:
    raised = True
assert raised, "an invalid control mode must fail"
seq = int(cmds.maroDiagQuery(index=0)[10])
kind, nodeName, attrName, value, _, _ = cmds.maroDiagQueryRemedyAction(sequence=seq)
assert kind == "setAttribute" and nodeName == axisAPath and attrName == "controlMode", (
    kind, nodeName, attrName)
assert float(value) == 0.0, value
print("InvalidControlMode remedy OK")

# Finding I2: 이 해법은 대상이 진짜 maroAxis일 때만 붙는다. 존재하지 않는
# 이름이나 maroAxis가 아닌 노드에는 controlMode 어트리뷰트 자체가 없으므로,
# 해법을 달면 눌러도 아무 일도 안 일어나는 버튼이 된다. 실패 자체는 그대로
# InvalidControlMode여야 한다 -- 검사 순서는 바뀌지 않았다.
for bogus in ("noSuchNodeAtAll", cube):
    try:
        cmds.maroSetControlMode(bogus, 5)
        raised = False
    except RuntimeError:
        raised = True
    assert raised, "an invalid control mode must still fail for %r" % (bogus,)
    seq = int(cmds.maroDiagQuery(index=0)[10])
    kind, _, _, _, _, _ = cmds.maroDiagQueryRemedyAction(sequence=seq)
    assert kind == "none", (
        "InvalidControlMode must not offer a fix for %r, got %s" % (bogus, kind))
print("InvalidControlMode offers no remedy for a bogus target OK")

# SelfParent / NotMaroAxisNode(둘째 자리): maroConnectAxis 경유.
#
# 참고: cmds.maroConnectAxis(axisA, axisA)로는 이 자리를 실제로 유발할 수
# 없다 -- MSelectionList::add()는 같은 문자열을 두 번 넣어도(실제로는 같은
# 노드로 풀리는 서로 다른 문자열이어도, om1로 직접 확인함) 리스트 길이를
# 1로 합쳐 버리므로, doIt() 맨 앞의 "정확히 두 개" 인자 개수 검사
# (WrongArgCount)에 먼저 걸려 SelfParent 분기(childObj == parentObj)까지
# 도달하지 못한다. 같은 노드를 가리키되 셀렉션 리스트 항목으로는 별개로
# 세어지는 "노드.어트리뷰트" 플러그 표기를 하나 섞어야(getDependNode()는
# 플러그가 속한 노드를 돌려준다) 리스트 길이 2를 유지한 채 같은 노드로
# 풀리게 만들 수 있다 -- "message"는 모든 DG 노드에 있는 표준 어트리뷰트다.
try:
    cmds.maroConnectAxis(axisA + ".message", axisA)
    raised = False
except RuntimeError:
    raised = True
assert raised, "self-parenting must fail"
seq = int(cmds.maroDiagQuery(index=0)[10])
kind, nodeName, _, _, _, _ = cmds.maroDiagQueryRemedyAction(sequence=seq)
assert kind == "selectNode" and nodeName == axisAPath, (kind, nodeName)
print("SelfParent remedy OK")

try:
    cmds.maroConnectAxis(cube, axisA)
    raised = False
except RuntimeError:
    raised = True
assert raised, "connecting a non-axis node must fail"
seq = int(cmds.maroDiagQuery(index=0)[10])
kind, nodeName, _, _, _, _ = cmds.maroDiagQueryRemedyAction(sequence=seq)
assert kind == "selectNode" and nodeName == cubePath, (kind, nodeName)
print("NotMaroAxisNode remedy OK")

# WouldCreateCycle: 의도적으로 해법이 없다.
cmds.maroConnectAxis(axisB, axisA)
try:
    cmds.maroConnectAxis(axisA, axisB)
    raised = False
except RuntimeError:
    raised = True
assert raised, "creating a cycle must fail"
seq = int(cmds.maroDiagQuery(index=0)[10])
kind, _, _, _, _, _ = cmds.maroDiagQueryRemedyAction(sequence=seq)
assert kind == "none", f"WouldCreateCycle must have no structured remedy, got {kind}"
print("WouldCreateCycle has no remedy (by design) OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("test_remedy_capture OK")
