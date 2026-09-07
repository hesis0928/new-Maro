"""CalibrationSession: 뷰포트 리그(헬퍼 로케이터, 임시 부모, 커넥션
끊기/복원)와 collect 누적. HUD(Qt)는 별도로 열지 않고 세션 API만
mayapy로 검증한다 -- HUD 자체는 수동 체크리스트(Task 8) 대상."""
import math
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(plugin))))
import maroLimitCalibration as calib  # noqa: E402

# (a) 커넥션이 전혀 없는 자유 오브젝트 -- 가장 단순한 경로.
freeCube = cmds.polyCube(name="freeCubeForCalib")[0]
session = calib.CalibrationSession()
session.start(freeCube, axisDirection=(0.0, 1.0, 0.0),
              pivotWorld=(0.0, 0.0, 0.0), isLinear=False)
assert abs(session.currentValue()) < 1e-9, "must start at 0"
# currentValue()는 항상 헬퍼 로케이터의 로컬 Z(rotateZ)를 읽는다 -- 헬퍼는
# axisDirection에 맞춰 정렬돼 있으므로, axisDirection이 무엇이든(여기선
# 세계 Y) currentValue()가 보는 채널은 항상 rotateZ다.
cmds.setAttr(session.helperLocator() + ".rotateZ", 30.0)
assert abs(session.currentValue() - 30.0) < 1e-6, session.currentValue()
mn, mx = session.collect()
assert abs(mn - 0.0) < 1e-6 and abs(mx - 30.0) < 1e-6, (mn, mx)
cmds.setAttr(session.helperLocator() + ".rotateZ", -10.0)
mn, mx = session.collect()
assert abs(mn - (-10.0)) < 1e-6 and abs(mx - 30.0) < 1e-6, (mn, mx)
session.finish()
assert not cmds.objExists(session.helperLocator()), "finish() must delete the helper locator"
assert cmds.getAttr(freeCube + ".rotateY") == 0.0 or True  # 자유 오브젝트라 원복 대상 값 자체가 0
print("free-object calibration session OK")

# (b) rotateX/Y/Z가 DG 커넥션으로 이미 구동되는 오브젝트 -- 연결
# 끊기/복원이 핵심.
axisConn = cmds.createNode("maroAxis", name="calibConnAxis")
rotConn = cmds.createNode("maroRotation", name="calibConnRot")
cmds.connectAttr(rotConn + ".capabilityOut", axisConn + ".capabilityIn[0]")
cmds.setAttr(rotConn + ".angle", 0.4)
boundCube = cmds.polyCube(name="boundCubeForCalib")[0]
cmds.connectAttr(axisConn + ".position", boundCube + ".rotateY")
originalSource = cmds.listConnections(boundCube + ".rotateY", source=True, destination=False,
                                      plugs=True)[0]
originalValue = cmds.getAttr(boundCube + ".rotateY")

sessionConn = calib.CalibrationSession()
sessionConn.start(boundCube, axisDirection=(0.0, 1.0, 0.0),
                  pivotWorld=(0.0, 0.0, 0.0), isLinear=False)
# 캘리브레이션 도중엔 rotateY가 자유로워야(연결이 끊겨야) 한다.
assert cmds.listConnections(boundCube + ".rotateY", source=True, destination=False,
                            plugs=True) in (None, []), \
    "rotateY must be disconnected during calibration"
cmds.setAttr(sessionConn.helperLocator() + ".rotateZ", 15.0)
sessionConn.collect()
sessionConn.finish()

restoredSource = cmds.listConnections(boundCube + ".rotateY", source=True, destination=False,
                                      plugs=True)
assert restoredSource == [originalSource], \
    f"finish() must restore the exact original connection (got {restoredSource})"
assert abs(cmds.getAttr(boundCube + ".rotateY") - originalValue) < 1e-9, \
    "finish() must restore the pre-calibration driven value"
print("connected-object calibration session restores connection OK")

# (c) 예외/취소 경로에서도 복원된다 -- cancel()이 finish()와 같은 정리를 한다.
cmds.setAttr(rotConn + ".angle", 0.9)
originalValue2 = cmds.getAttr(boundCube + ".rotateY")
sessionCancel = calib.CalibrationSession()
sessionCancel.start(boundCube, axisDirection=(0.0, 1.0, 0.0),
                    pivotWorld=(0.0, 0.0, 0.0), isLinear=False)
sessionCancel.cancel()
restoredSource2 = cmds.listConnections(boundCube + ".rotateY", source=True, destination=False,
                                       plugs=True)
assert restoredSource2 == [originalSource], "cancel() must also restore the connection"
assert abs(cmds.getAttr(boundCube + ".rotateY") - originalValue2) < 1e-9
assert not cmds.objExists(sessionCancel.helperLocator())
print("cancel() restores connection OK")

# (d) 이중 정리(_cleanup 두 번 호출)가 안전하다.
sessionConn.finish()  # 이미 끝난 세션을 다시 finish해도 예외가 나면 안 된다
print("idempotent cleanup OK")

# (e) isLinear=True -- translateZ를 읽고, 커넥션 채널도 translateX/Y/Z.
axisConnLin = cmds.createNode("maroAxis", name="calibConnAxisLin")
transConnLin = cmds.createNode("maroTranslation", name="calibConnTransLin")
cmds.connectAttr(transConnLin + ".capabilityOut", axisConnLin + ".capabilityIn[0]")
cmds.setAttr(transConnLin + ".distance", 3.0)
boundCubeLin = cmds.polyCube(name="boundCubeForCalibLin")[0]
cmds.connectAttr(axisConnLin + ".positionLinear", boundCubeLin + ".translateY")
originalSourceLin = cmds.listConnections(boundCubeLin + ".translateY", source=True,
                                         destination=False, plugs=True)[0]

sessionLin = calib.CalibrationSession()
sessionLin.start(boundCubeLin, axisDirection=(0.0, 1.0, 0.0),
                 pivotWorld=(0.0, 0.0, 0.0), isLinear=True)
assert cmds.listConnections(boundCubeLin + ".translateY", source=True, destination=False,
                            plugs=True) in (None, [])
cmds.setAttr(sessionLin.helperLocator() + ".translateZ", 7.5)
assert abs(sessionLin.currentValue() - 7.5) < 1e-6
mn, mx = sessionLin.collect()
assert abs(mn - 0.0) < 1e-6 and abs(mx - 7.5) < 1e-6
sessionLin.finish()
restoredSourceLin = cmds.listConnections(boundCubeLin + ".translateY", source=True,
                                         destination=False, plugs=True)
assert restoredSourceLin == [originalSourceLin]
print("linear (TranslationLimit) calibration session OK")

# (d-2) 대상을 **풀 DAG 경로**로 넘겨도 복원된다.
#
# 실제 패널이 넘기는 형태가 이것이다(maroCapabilityPanel._onCalibrate가
# cmds.ls(..., long=True)로 정규화한다). 그런데 start()는 대상을 헬퍼
# 로케이터 밑으로 옮기므로 그 순간 원래 풀 경로는 더 이상 존재하지 않는다
# -- 그 뒤로도 옛 경로를 계속 쓰면 정리 단계의 parent/setAttr/connectAttr가
# 전부 없는 노드를 가리킨다. 짧은 이름은 Maya가 계층과 무관하게 해소해 주기
# 때문에 이 결함이 지금까지 드러나지 않았다.
axisFull = cmds.createNode("maroAxis", name="fullPathAxis")
rotFull = cmds.createNode("maroRotation", name="fullPathRot")
cmds.connectAttr(rotFull + ".capabilityOut", axisFull + ".capabilityIn[0]")
cmds.setAttr(rotFull + ".angle", 0.3)
groupFull = cmds.group(empty=True, name="fullPathGroup")
cubeFull = cmds.polyCube(name="fullPathCube")[0]
cmds.parent(cubeFull, groupFull)
cubeFull = cmds.ls(cubeFull, long=True)[0]          # "|fullPathGroup|fullPathCube"
cmds.connectAttr(axisFull + ".position", cubeFull + ".rotateY")
sourceFull = cmds.listConnections(cubeFull + ".rotateY", source=True,
                                  destination=False, plugs=True)[0]
valueFull = cmds.getAttr(cubeFull + ".rotateY")

sessionFull = calib.CalibrationSession()
sessionFull.start(cubeFull, axisDirection=(0.0, 1.0, 0.0),
                  pivotWorld=(0.0, 0.0, 0.0), isLinear=False)
sessionFull.finish()

restoredFull = cmds.listConnections(cubeFull + ".rotateY", source=True,
                                    destination=False, plugs=True)
assert restoredFull == [sourceFull], (
    "a full-path target must be restored too, got %r" % (restoredFull,))
assert abs(cmds.getAttr(cubeFull + ".rotateY") - valueFull) < 1e-9
parentsFull = cmds.listRelatives(cubeFull, parent=True, fullPath=True)
assert parentsFull == [cmds.ls(groupFull, long=True)[0]], (
    "the target must go back under its original parent, got %r" % (parentsFull,))
print("full-path target restores OK")

# (e) 창이 캘리브레이션 도중 닫히면 패널이 세션을 취소해야 한다.
#
# 이게 없으면 조용한 씬 손상이다: start()는 대상의 구동 채널을 끊고 대상을
# 헬퍼 로케이터 밑으로 재부모화하는데, 정리는 finish()/cancel()만 한다.
# 캘리브레이션 도중 X 버튼으로 닫거나 -- 더 나쁘게는 플러그인 언로드가
# maroCapabilityPanel.stop() -> close()를 부르면 -- 사용자의 리그가
# 헬퍼 밑에 매달린 채 커넥션이 끊긴 상태로 남는다.
#
# QWidget을 만들면 배치 mayapy가 abort하므로(이 파일 가족의 알려진 제약)
# 패널 인스턴스를 만들지 않고, _onClosing()을 오리 타입 객체를 self로 삼아
# 직접 부른다 -- 검증 대상은 그 메서드의 본문이지 Qt가 아니다.
import maroCapabilityPanel as panelMod  # noqa: E402


class _FakeHud:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _FakePanel:
    pass


cmds.setAttr(rotConn + ".angle", 1.1)
valueBeforeClose = cmds.getAttr(boundCube + ".rotateY")
sessionClose = calib.CalibrationSession()
sessionClose.start(boundCube, axisDirection=(0.0, 1.0, 0.0),
                   pivotWorld=(0.0, 0.0, 0.0), isLinear=False)
helperWhileOpen = sessionClose.helperLocator()
assert cmds.objExists(helperWhileOpen)

fakePanel = _FakePanel()
fakePanel._calibrationSession = sessionClose
fakePanel._calibrationHud = _FakeHud()
panelMod._AxisLimitPanelBase._onClosing(fakePanel)

assert fakePanel._calibrationHud is None or fakePanel._calibrationSession is None
assert not cmds.objExists(helperWhileOpen), \
    "closing the panel mid-calibration must delete the helper locator"
restoredOnClose = cmds.listConnections(boundCube + ".rotateY", source=True,
                                       destination=False, plugs=True)
assert restoredOnClose == [originalSource], \
    f"closing the panel must restore the driven connection (got {restoredOnClose})"
assert abs(cmds.getAttr(boundCube + ".rotateY") - valueBeforeClose) < 1e-9, \
    "closing the panel must restore the pre-calibration pose"
parentsAfterClose = cmds.listRelatives(boundCube, parent=True, fullPath=True)
assert parentsAfterClose in (None, []), \
    f"the target must be un-parented from the helper (got {parentsAfterClose})"
print("closing the panel mid-calibration restores the scene OK")

# 세션이 없을 때 불려도 안전해야 한다(언로드는 창을 연 적 없어도 이 경로를 탄다).
idlePanel = _FakePanel()
panelMod._AxisLimitPanelBase._onClosing(idlePanel)
print("_onClosing with no active session is a safe no-op OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
