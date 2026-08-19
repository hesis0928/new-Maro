"""maroDiagRequestRemedy -> (큐 틱) -> maroApplyRemedy가 실제로 씬을
고치고, Ctrl+Z로 되돌아가는지 확인한다. 세 동작 종류를 각각 하나씩,
그리고 클릭과 실행 사이에 씬이 바뀌는 경계 조건 하나를 확인한다.
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


# --- Disconnect ---
axisA = cmds.createNode("maroAxis", name="axisA")
cubeA = cmds.polyCube()[0]
cmds.maroBindAxis(axisA, cubeA)
cmds.maroDiagEmit(severity="error", message="m", siteTag="T.Disc",
                  remedyAction="disconnect",
                  remedySourcePlug=cubeA + ".message",
                  remedyDestPlug=axisA + ".targetObject")
seq = int(cmds.maroDiagQuery(index=0)[10])

countBefore = cmds.maroDiagCount()
cmds.maroDiagRequestRemedy(sequence=seq)
assert cmds.isConnected(cubeA + ".message", axisA + ".targetObject"), \
    "requesting a remedy must not apply it synchronously"
assert _pumpUntil(lambda: not cmds.isConnected(cubeA + ".message", axisA + ".targetObject")), \
    "the disconnect remedy never applied"
print("disconnect apply OK")

# 적용 전후를 boad에 기록한다 (원 스펙 §4.3 안전 규칙 4) -- 새 info
# 레코드가 하나 늘고, 그 메시지가 무엇을 바꿨는지 말해야 한다.
assert cmds.maroDiagCount() == countBefore + 1, \
    "applying a remedy must leave a boad record of what changed"
appliedMessage = cmds.maroDiagQuery(index=0)[1]
assert cubeA in appliedMessage and axisA in appliedMessage, appliedMessage
print("apply is recorded in boad OK")

cmds.undo()
assert cmds.isConnected(cubeA + ".message", axisA + ".targetObject"), \
    "undo must restore the connection the remedy removed"
print("disconnect undo OK")

# --- SetAttribute ---
cmds.maroSetControlMode(axisA, 1)  # ROS로 바꿔 둔다 -- 되돌릴 값이 기본값과 달라야 undo를 의미 있게 확인한다.
assert cmds.getAttr(axisA + ".controlMode") == 1
cmds.maroDiagEmit(severity="error", message="m2", siteTag="T.Attr",
                  remedyAction="setAttribute", remedyNode=axisA,
                  remedyAttribute="controlMode", remedyValue=0.0)
seq2 = int(cmds.maroDiagQuery(index=0)[10])
cmds.maroDiagRequestRemedy(sequence=seq2)
assert _pumpUntil(lambda: cmds.getAttr(axisA + ".controlMode") == 0), \
    "the setAttribute remedy never applied"
print("setAttribute apply OK")

cmds.undo()
assert cmds.getAttr(axisA + ".controlMode") == 1, "undo must restore the previous mode"
print("setAttribute undo OK")

# --- SelectNode ---
cmds.select(clear=True)
cmds.maroDiagEmit(severity="error", message="m3", siteTag="T.Select",
                  remedyAction="selectNode", remedyNode=axisA)
seq3 = int(cmds.maroDiagQuery(index=0)[10])
cmds.maroDiagRequestRemedy(sequence=seq3)
assert _pumpUntil(lambda: cmds.ls(selection=True) == [axisA]), \
    "the selectNode remedy never applied"
print("selectNode apply OK")

cmds.undo()
assert cmds.ls(selection=True) == [], "undo must restore the empty prior selection"
print("selectNode undo OK")

# --- 경계 조건: 클릭과 실행 사이에 대상이 사라짐 ---
axisB = cmds.createNode("maroAxis", name="axisB")
cmds.maroDiagEmit(severity="error", message="m4", siteTag="T.Gone",
                  remedyAction="selectNode", remedyNode=axisB)
seq4 = int(cmds.maroDiagQuery(index=0)[10])
cmds.delete(axisB)
try:
    cmds.maroApplyRemedy(sequence=seq4)
    raised = False
except RuntimeError:
    raised = True
assert raised, "applying a remedy whose target vanished must fail cleanly"
print("vanished target fails cleanly OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("test_remedy_apply OK")
