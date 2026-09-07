"""capability 상세 설정 패널을 **실제 QWidget으로** 배치에서 검증한다.

이 파일이 가능해진 경위는 tests/maya/maroQtBatch.py의 독스트링에 있다 --
요약하면 "배치 mayapy에서는 Qt UI를 못 만든다"는 이 저장소의 오래된 전제가
틀렸고, QApplication을 maya.standalone보다 먼저 offscreen으로 세우면 된다.

기존 tests/maya/test_capability_panel.py는 그 전제 아래 쓰여서 위젯을 절대
만들지 않고 팩토리 매핑/생성 전 에러 경로만 봤다. 이 파일은 그 위에
**실제로 창을 만들어야만 볼 수 있는 것**을 얹는다:

  * 7종 패널이 각자의 _ATTRS대로 필드를 만들고 노드 값을 읽어오는가
  * "적용"이 그 값을 노드에 되돌려 쓰는가
  * 싱글톤(_OPEN_EDITORS)이 같은 노드에 두 창을 안 만드는가
  * **캘리브레이션 진행 중 창을 닫으면 씬이 원복되는가** -- 진짜
    closeEvent 경로로. (test_limit_calibration_session.py는 QWidget을 못
    만든다는 전제 때문에 오리 타입 객체로 _onClosing()만 직접 불렀다.
    여기서는 실제 패널의 close()가 그 경로에 닿는지까지 확인한다.)
  * stop()이 열린 창을 전부 닫는가(플러그인 언로드 경로)

offscreen이라 화면에 실제로 어떻게 보이는지는 여전히 수동 확인 대상이다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import maroQtBatch  # noqa: E402

# 반드시 maya.standalone보다 먼저.
maroQtBatch.bootstrap()

import maya.standalone  # noqa: E402

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

maroQtBatch.assertWidgetsUsable()
print("offscreen QApplication is live -- widgets are usable in batch")

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(plugin))))
import maroCapabilityPanel as panelMod  # noqa: E402

# --- (a) 7종 전부 실제로 열리고 노드 값을 읽어온다 -------------------------
NODE_TYPES = [
    "maroRotation", "maroTranslation", "maroLimit", "maroTranslationLimit",
    "maroSensorDirection", "maroSensorRange", "maroCoupling",
]
opened = {}
for nodeType in NODE_TYPES:
    node = cmds.createNode(nodeType, name=nodeType + "ForPanel")
    node = cmds.ls(node, long=True)[0]
    panel = panelMod.openCapabilityPanel(node)
    assert panel is not None, nodeType
    opened[nodeType] = (node, panel)
    # 각 패널은 자기 _ATTRS만큼 필드를 갖는다.
    fieldCount = len(panel._fields) + len(panel._vecFields)
    assert fieldCount == len(type(panel)._ATTRS), (
        nodeType, fieldCount, type(panel)._ATTRS)
print("all 7 capability panels constructed with their declared fields OK")

# --- (b) 값 왕복: 노드 -> 위젯 -> 노드 ------------------------------------
rotNode, rotPanel = opened["maroRotation"]
cmds.setAttr(rotNode + ".angle", 0.75)
rotPanel._loadValues()
field, _kind = rotPanel._fields["angle"]
assert abs(field.value() - 0.75) < 1e-6, field.value()
field.setValue(-0.25)
rotPanel._onApply()
assert abs(cmds.getAttr(rotNode + ".angle") - (-0.25)) < 1e-6, cmds.getAttr(rotNode + ".angle")
print("value round-trip through the real widget OK")

# vec3 필드도 같은 계약인지 본다(스칼라와 코드 경로가 다르다).
dirNode, dirPanel = opened["maroSensorDirection"]
cmds.setAttr(dirNode + ".direction", 0.0, 1.0, 0.0, type="double3")
dirPanel._loadValues()
subFields = dirPanel._vecFields["direction"]
assert abs(subFields[1].value() - 1.0) < 1e-6, [f.value() for f in subFields]
subFields[0].setValue(1.0)
subFields[1].setValue(0.0)
dirPanel._onApply()
assert cmds.getAttr(dirNode + ".direction")[0] == (1.0, 0.0, 0.0), cmds.getAttr(dirNode + ".direction")
print("vec3 round-trip OK")

# --- (c) 싱글톤 --------------------------------------------------------------
again = panelMod.openCapabilityPanel(rotNode)
assert again is rotPanel, "openCapabilityPanel must reuse the open window"
print("singleton reuse OK")

# --- (d) Limit 패널의 ROS 축 라벨이 실시간으로 따라오는가 --------------------
limNode, limPanel = opened["maroLimit"]
limSubFields = limPanel._vecFields["axisDirection"]
limSubFields[0].setValue(0.0)
limSubFields[1].setValue(0.0)
limSubFields[2].setValue(1.0)
# maya (0,0,1) -> ros (x,-z,y) = (0,-1,0)
labelText = limPanel._rosAxisLabel.text()
assert "-1.0000" in labelText, labelText
print("ROS axis label live update OK:", labelText)

# --- (e) 캘리브레이션 도중 창을 닫으면 씬이 원복된다 (진짜 closeEvent) -------
#
# 이것이 이 파일의 본론이다. 세션이 하는 일은 씬을 크게 바꾼다: 대상의 구동
# 채널을 끊고, 헬퍼 로케이터를 만들고, 대상을 그 밑으로 재부모화한다.
# 정리를 못 하면 사용자의 리그가 망가진 채 남는다.
import maroLimitCalibration as calib  # noqa: E402

axis = cmds.createNode("maroAxis", name="panelCalibAxis")
rot = cmds.createNode("maroRotation", name="panelCalibRot")
cmds.connectAttr(rot + ".capabilityOut", axis + ".capabilityIn[0]")
cube = cmds.polyCube(name="panelCalibCube")[0]
cmds.connectAttr(axis + ".position", cube + ".rotateY")
originalSource = cmds.listConnections(cube + ".rotateY", source=True, destination=False,
                                      plugs=True)[0]

session = calib.CalibrationSession()
session.start(cube, axisDirection=(0.0, 1.0, 0.0), pivotWorld=(0.0, 0.0, 0.0),
              isLinear=False)
helper = session.helperLocator()
assert cmds.objExists(helper)
assert cmds.listConnections(cube + ".rotateY", source=True, destination=False,
                            plugs=True) in (None, [])

limPanel._calibrationSession = session
limPanel._calibrationHud = None
limPanel.close()  # <- 진짜 Qt closeEvent 경로

assert not cmds.objExists(helper), "closing the window must delete the helper locator"
restored = cmds.listConnections(cube + ".rotateY", source=True, destination=False, plugs=True)
assert restored == [originalSource], (
    "closing the window mid-calibration must restore the driven connection, got %r" % (restored,))
assert cmds.listRelatives(cube, parent=True, fullPath=True) in (None, []), \
    "the target must be un-parented from the helper locator"
assert limNode not in panelMod._OPEN_EDITORS, "close() must drop the singleton entry"
print("closing the real window mid-calibration restores the scene OK")

# --- (f) stop(): 언로드 경로가 남은 창을 전부 닫는다 -------------------------
assert panelMod._OPEN_EDITORS, "some panels should still be open at this point"
panelMod.stop()
assert panelMod._OPEN_EDITORS == {}, panelMod._OPEN_EDITORS
print("stop() closed every remaining panel OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
