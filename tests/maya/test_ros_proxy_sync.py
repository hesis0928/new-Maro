"""maroRosProxy.py 중 배치 모드에서 실제로 검증할 수 있는 부분 전부.

이 파일이 무엇을 **못** 하는지 먼저 분명히 해 둔다. 배치 mayapy에는
modelPanel도 workspaceControl도 없고 scriptJob은 아무 것도 만들지 않고
None만 돌려준다(실측). 따라서 이 태스크의 진짜 목표 --

  - 로케이터가 정말 우측 뷰포트에만 보이는가(isolateSelect가 패널별로 도는가),
  - `-addDagObject`가 정말 멱등한가,
  - 창을 닫거나 플러그인을 언로드하면 idle 잡이 정말 사라지는가

-- 는 여기서 원리적으로 확인할 수 없다. 그것은
docs/maro-main-ui-manual-checklist.md의 "1-2. ROS 좌표 프록시" 절이 사람에게
맡기는 몫이다(test_main_window.py가 같은 이유로 같은 선을 긋는다).

여기서 확인할 수 있는 것은 그 앞단 전부이고, 그게 적지 않다:
  - CMake가 .py를 .mll 옆에 스테이징했는가.
  - C++/Python이 공유하는 optionVar 이름 계약.
  - 프록시 노드를 만들어도 **사용자의 선택이 안 날아가는가** -- 이게 깨지면
    프록시가 자기 자신을 따라가는 되먹임이 생긴다.
  - 대상 결정 규칙(고정 > 선택, 프록시 자신은 제외, 고정 대상이 사라지면
    선택 추종으로 복귀).
  - 변환 -> 로케이터 반영이 실제로 맞는 값을 쓰는가(순수 계산이라
    배치에서 완전히 검증 가능하다).
  - stop()이 start() 없이도, 두 번 불려도 안전한가.
  - 뷰포트가 없을 때 _onIdle()이 스스로 멈추고 아무 것도 안 건드리는가.
  - 언로드 시 정리를 실제로 부르는 C++ 쪽 호출이 소스에 남아 있는가.
"""
import math
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
pluginName = os.path.splitext(os.path.basename(plugin))[0]
pluginDir = os.path.dirname(plugin)

stagedModule = os.path.join(pluginDir, "maroRosProxy.py")
assert os.path.isfile(stagedModule), (
    f"maroRosProxy.py must be staged next to the plug-in, not found at {stagedModule}"
)
print("module staged next to the plug-in OK")

cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

# 스테이징된 사본을 import한다 -- 런타임에 실제로 실행되는 것이 그것이다
# (C++ 브리지가 sys.path에 넣는 디렉터리가 여기다).
sys.path.insert(0, pluginDir)
import maroRosProxy  # noqa: E402

assert os.path.normcase(os.path.abspath(maroRosProxy.__file__)) == \
    os.path.normcase(os.path.abspath(stagedModule)), (
        f"imported the wrong copy: {maroRosProxy.__file__}")
print("imported the staged copy OK")

# --- 설계 스펙 §10: 새 .py는 setStyleSheet()를 부르지 않는다 -------------
with open(stagedModule, encoding="utf-8") as handle:
    moduleSource = handle.read()
assert ".setStyleSheet(" not in moduleSource, (
    "maroRosProxy.py must not call setStyleSheet() (design spec 10)")
print("no setStyleSheet OK")

# --- C++ 커맨드와 공유하는 optionVar 이름 계약 --------------------------
cube = cmds.polyCube(name="proxySyncCube")[0]
cmds.maroSetRosProxyTarget(cube)
assert cmds.optionVar(exists=maroRosProxy.PINNED_OPTIONVAR), (
    f"maroSetRosProxyTarget must write {maroRosProxy.PINNED_OPTIONVAR!r} -- "
    "the Python module reads that exact name")
cmds.maroSetRosProxyTarget(clear=True)
print("optionVar name contract with the C++ command OK")

# --- 프록시 노드 생성이 선택을 안 건드린다 ------------------------------
# 이것이 깨지면(cmds.group()/cmds.spaceLocator()는 실제로 선택을 갈아친다)
# 창을 여는 순간 사용자의 선택이 날아가고, 다음 틱부터 _resolveTarget()이
# 프록시 로케이터 자신을 대상으로 집어 프록시가 자기를 따라간다.
cmds.select(cube, replace=True)
locator = maroRosProxy._ensureProxyLocator()
assert cmds.ls(selection=True, long=True) == cmds.ls(cube, long=True), (
    f"creating the proxy nodes must not change the selection, got "
    f"{cmds.ls(selection=True, long=True)}")
assert locator == "|maroRosProxy_grp|maroRosProxy_loc", locator
assert cmds.objExists(locator)
shapes = cmds.listRelatives(locator, shapes=True, fullPath=True) or []
assert len(shapes) == 1 and cmds.nodeType(shapes[0]) == "locator", shapes
print("proxy node creation preserves the selection OK")

# 두 번 불러도 노드가 늘지 않는다(멱등).
maroRosProxy._ensureProxyLocator()
maroRosProxy._ensureProxyGroup()
assert len(cmds.ls("maroRosProxy_loc", long=True)) == 1
assert len(cmds.ls("maroRosProxy_grp", long=True)) == 1
print("proxy node creation is idempotent OK")

# --- 대상 결정 규칙 ------------------------------------------------------
cmds.select(cube, replace=True)
assert cmds.ls(maroRosProxy._resolveTarget(), long=True) == cmds.ls(cube, long=True)
print("target follows the selection OK")

# 프록시 자신은 절대 대상이 되지 않는다 -- 되먹임 방지.
cmds.select(locator, replace=True)
assert maroRosProxy._resolveTarget() is None, (
    "the proxy locator must never become the sync target")
cmds.select("maroRosProxy_grp", replace=True)
assert maroRosProxy._resolveTarget() is None, (
    "the proxy group must never become the sync target")
print("proxy nodes are excluded from target resolution OK")

# 고정이 선택을 이긴다.
other = cmds.polyCube(name="proxySyncOther")[0]
cmds.maroSetRosProxyTarget(cube)
cmds.select(other, replace=True)
assert cmds.ls(maroRosProxy._resolveTarget(), long=True) == cmds.ls(cube, long=True), (
    "a pinned target must win over the selection")
print("pinned target wins over the selection OK")

# 고정 대상이 씬에서 사라지면 조용히 선택 추종으로 떨어진다(에러를 내지 않는다).
cmds.delete(cube)
cmds.select(other, replace=True)
assert cmds.ls(maroRosProxy._resolveTarget(), long=True) == cmds.ls(other, long=True), (
    "a dangling pinned target must fall back to the selection, not raise")
cmds.maroSetRosProxyTarget(clear=True)
print("dangling pinned target falls back to the selection OK")

# 선택도 고정도 없으면 None.
cmds.select(clear=True)
assert maroRosProxy._resolveTarget() is None
print("no selection and no pin -> no target OK")

# --- 변환 -> 로케이터 반영 ----------------------------------------------
# Convert.h: mayaToRos는 (x, y, z) -> (x, -z, y)이고 cm -> m로 스케일한다.
# Maya에서 z = +1cm는 ROS에서 y = -0.01m가 돼야 한다. 로케이터의 트랜스폼
# 값 자체가 곧 ROS 좌표(미터)다 -- 우측 뷰포트에서 채널 박스를 열면 ROS
# 값을 그대로 읽을 수 있다는 뜻이고, 그것이 이 단계의 목적이다.
cmds.xform(other, worldSpace=True, translation=[0.0, 0.0, 1.0])
cmds.xform(other, worldSpace=True, rotation=[0.0, 0.0, 0.0])
cmds.select(other, replace=True)
maroRosProxy._syncProxy()

got = cmds.xform(locator, query=True, worldSpace=True, translation=True)
assert abs(got[0] - 0.0) < 1e-9, got
assert abs(got[1] - (-0.01)) < 1e-9, got   # -z, cm -> m
assert abs(got[2] - 0.0) < 1e-9, got
gotRot = cmds.xform(locator, query=True, worldSpace=True, rotation=True)
for value in gotRot:
    assert abs(value) < 1e-6, gotRot
print("position conversion reaches the locator OK")

# 회전도 실제로 반영된다. Maya Y축 90도 -> 쿼터니언 (0, sin45, 0, cos45) ->
# ROS 쿼터니언 (0, 0, sin45, cos45) -> 오일러 (0, 0, 90).
cmds.xform(other, worldSpace=True, translation=[0.0, 0.0, 0.0])
cmds.xform(other, worldSpace=True, rotation=[0.0, 90.0, 0.0])
maroRosProxy._syncProxy()
gotRot = cmds.xform(locator, query=True, worldSpace=True, rotation=True)
assert abs(gotRot[0]) < 1e-6, gotRot
assert abs(gotRot[1]) < 1e-6, gotRot
assert abs(gotRot[2] - 90.0) < 1e-6, gotRot
print("rotation conversion reaches the locator OK")

# 부모가 있어도 **월드** 변환을 쓴다(MFnTransform.rotation(kWorld, ...)).
parent = cmds.group(other, name="proxySyncParent")
cmds.xform(parent, worldSpace=True, rotation=[0.0, 0.0, 0.0])
cmds.xform(other, worldSpace=True, rotation=[0.0, 90.0, 0.0])
cmds.xform(parent, worldSpace=True, rotation=[0.0, -90.0, 0.0])
cmds.select(other, replace=True)
worldRot = cmds.xform(other, query=True, worldSpace=True, rotation=True)
maroRosProxy._syncProxy()
gotRot = cmds.xform(locator, query=True, worldSpace=True, rotation=True)
# 부모가 -90도를 되돌렸으므로 자식의 월드 Y 회전은 0에 가까워야 하고,
# 그러면 ROS 쪽 Z 회전도 0이어야 한다. 부모를 무시하고 로컬 회전을 썼다면
# 여기서 90도가 나온다.
assert abs(worldRot[1]) < 1e-6, worldRot
assert abs(gotRot[2]) < 1e-6, (
    f"the sync must use the WORLD rotation, not the local one: {gotRot}")
print("world-space rotation (parented target) OK")

# --- 생명주기: 배치에서 확인 가능한 만큼 ---------------------------------
# start()를 부른 적이 없어도 stop()은 조용히 아무 것도 안 한다. 언로드는
# 창을 연 적이 있든 없든 항상 stop()을 부르므로 이게 성립해야 한다.
maroRosProxy.stop()
maroRosProxy.stop()
assert maroRosProxy._JOB_ID is None
print("stop() without start(), twice, is a safe no-op OK")

# 뷰포트가 없으면 _onIdle()은 스스로 멈추고 isolateSelect를 건드리지
# 않는다(배치에는 modelPanel이 없으므로 _panelsAlive()가 False다) --
# 창이 닫혔는데 closeCommand가 안 뛴 경로에 대한 자가 방어다.
maroRosProxy._MAYA_PANEL = "noSuchPanelMaya"
maroRosProxy._ROS_PANEL = "noSuchPanelRos"
maroRosProxy._onIdle()
assert maroRosProxy._JOB_ID is None
assert maroRosProxy._MAYA_PANEL is None, (
    "_onIdle() must stop() itself when the viewports are gone")
print("_onIdle() self-stops when the viewports are gone OK")

# 언로드 시 정리를 부르는 C++ 쪽 호출이 실제로 소스에 남아 있는가.
# 창의 closeCommand가 `workspaceControl -e -close`에서도 뛰는지는 문서로
# 확정하지 못했으므로, 이 호출은 "있으면 좋은 것"이 아니라 언로드 정리의
# 실질적 담당이다 -- 누가 지워도 대화형 Maya에서 언로드해 보기 전에는
# 드러나지 않으므로 여기서 고정한다(test_main_window.py가 UI 이름 계약을
# 같은 방식으로 고정한다).
_thisDir = os.path.dirname(os.path.abspath(__file__))
_pluginMainCpp = os.path.join(_thisDir, "..", "..", "src", "maro_plugin", "MaroPluginMain.cpp")
with open(_pluginMainCpp, encoding="utf-8") as handle:
    _pluginMainSource = handle.read()
assert 'runPluginPythonModule("maroRosProxy", "maroRosProxy.stop()")' in _pluginMainSource, (
    "MaroPluginMain.cpp must call maroRosProxy.stop() on unload -- otherwise the "
    "idle scriptJob can outlive the plug-in")
print("C++ unload-cleanup call is present OK")

# maroMainWindow가 이 모듈을 실제로 배선했는가(창 열림/닫힘 양쪽).
_windowModule = os.path.join(pluginDir, "maroMainWindow.py")
with open(_windowModule, encoding="utf-8") as handle:
    _windowSource = handle.read()
assert "maroRosProxy.start(" in _windowSource, (
    "maroMainWindow.buildUI() must start the ROS proxy sync")
assert "maroRosProxy.stop()" in _windowSource, (
    "maroMainWindow must stop the ROS proxy sync when the window closes")
assert "closeCommand=" in _windowSource, (
    "the workspaceControl must wire a closeCommand -- otherwise closing the "
    "window leaves the idle scriptJob running")
print("maroMainWindow wiring OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(pluginName)
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
