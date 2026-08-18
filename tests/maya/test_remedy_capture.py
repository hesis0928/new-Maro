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

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("test_remedy_capture OK")
