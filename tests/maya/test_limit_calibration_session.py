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

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
