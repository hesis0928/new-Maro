"""maroMainWindow 커맨드가 배치 모드에서 검증할 수 있는 만큼을 검증한다.

이 파일이 무엇을 **못** 하는지 먼저 분명히 해 둔다. mayapy 배치 모드에는 UI가
없어서 workspaceControl도 modelPanel도 만들어지지 않고(둘 다 예외 없이 False를
돌려준다 -- 실측), 전역 애플리케이션 객체가 QApplication이 아니라
QGuiApplication이라 QWidget을 하나라도 만들면 Qt가 프로세스를 abort시킨다
(파이썬 예외가 아니다 -- 종료 코드 9로 프로세스가 통째로 죽는다). 즉 이
태스크의 진짜 목표(뷰포트가 그려지는가, 버튼이 눌리는가, 창을 띄운 채
언로드해도 크래시하지 않는가)는 여기서 **원리적으로** 확인할 수 없다 --
그것은 docs/maro-main-ui-manual-checklist.md가 사람에게 맡기는 몫이고,
maroDiagPanel도 같은 이유로 docs/maro-panel-manual-checklist.md를 갖고 있다.

여기서 확인할 수 있는 것은 그 앞단 전부다:
  - 커맨드가 등록되고, 부르면 예외 없이 끝난다(= C++ 브리지가 플러그인
    디렉터리를 찾아 sys.path에 넣고 모듈을 import하는 데까지 성공했다).
  - 그 import가 실제로 일어났다(sys.modules로 확인) -- CMake 스테이징이
    .py를 .mll 옆에 놓았고 runPluginPythonModule이 그것을 찾았다는 뜻.
  - C++/Python이 공유하는 UI 이름 세 개가 실제로 같다.
  - 배치 모드에서 buildUI()를 부르면 프로세스가 죽는 대신 예외가 난다.
  - 새 모듈이 setStyleSheet()를 부르지 않는다(설계 스펙 §4.2의 규율).
  - 언로드하면 커맨드가 사라진다.
"""
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
pluginName = os.path.splitext(os.path.basename(plugin))[0]
pluginDir = os.path.dirname(plugin)

# CMake가 .py를 .mll 옆에 스테이징했는가(Task 1의 MARO_PLUGIN_PY_MODULES).
stagedModule = os.path.join(pluginDir, "maroMainWindow.py")
assert os.path.isfile(stagedModule), (
    f"maroMainWindow.py must be staged next to the plug-in, not found at {stagedModule}"
)
print("module staged next to the plug-in OK")

cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

registered = cmds.pluginInfo(pluginName, query=True, command=True) or []
assert "maroMainWindow" in registered, (
    f"maroMainWindow must be registered by the plug-in, got {sorted(registered)}"
)
print("command registered OK")

# 배치 모드에는 UI가 없으므로 workspaceControl은 만들어지지 않는다(예외도
# 나지 않는다) -- 따라서 -uiScript가 돌지 않고 buildUI()도 불리지 않는다.
# 이 호출이 실제로 확인하는 것은 C++ 쪽 전부다: findPlugin -> loadPath ->
# sys.path 주입 -> import maroMainWindow -> show(). 그 어느 단계가 깨져도
# 여기서 RuntimeError로 드러난다.
assert "maroMainWindow" not in sys.modules, (
    "the module must not be imported before the command runs -- otherwise the "
    "next assertion proves nothing about the C++ sys.path injection"
)
cmds.maroMainWindow()
assert "maroMainWindow" in sys.modules, (
    "running the command must have imported the staged maroMainWindow module"
)
print("command imports the staged module OK")

# 배치 모드에서는 cmds.workspaceControl()이 아무것도 만들지 않고 False만
# 돌려주므로(workspaceControl(exists=True)도 계속 False), 이 두 번째 호출은
# show()의 "이미 있으면 복원" 분기를 실제로 타지 않는다 -- 재진입해도
# 예외가 안 난다는 것만 증명한다. 복원 분기 자체는 대화형 Maya에서만
# 검증 가능하다(수동 체크리스트 참고).
cmds.maroMainWindow()
print("second invocation OK (re-entrancy only, not the restore branch)")

import maroMainWindow  # noqa: E402

# C++와 공유하는 이름 계약. MaroPluginMain.cpp의 uninitializePlugin이 언로드할
# 때 이 두 문자열을 MEL로 다시 부른다 -- 어긋나면 창을 띄운 채 언로드했을 때
# 정리가 조용히 아무 것도 안 하게 되고, 그 결함은 사람이 대화형 Maya에서
# 크래시로 만나기 전에는 드러나지 않는다. 여기서 값으로 고정한다.
assert maroMainWindow.CONTROL_NAME == "maroMainWindowControl", (
    f"CONTROL_NAME must match the MEL cleanup in MaroPluginMain.cpp, "
    f"got {maroMainWindow.CONTROL_NAME!r}"
)
assert maroMainWindow.VIEWPORT_NAME_MAYA == "maroMainWindowViewportMaya", (
    f"VIEWPORT_NAME_MAYA must match the MEL cleanup in MaroPluginMain.cpp, "
    f"got {maroMainWindow.VIEWPORT_NAME_MAYA!r}"
)
assert maroMainWindow.VIEWPORT_NAME_ROS == "maroMainWindowViewportRos", (
    f"VIEWPORT_NAME_ROS must match the MEL cleanup in MaroPluginMain.cpp, "
    f"got {maroMainWindow.VIEWPORT_NAME_ROS!r}"
)

# [최종 리뷰 I7] 위 두 assert는 Python 쪽 값이 우리가 기대하는 리터럴과
# 같은지만 본다 -- MaroPluginMain.cpp의 MEL 정리 문자열이 나중에 바뀌어도
# 이 테스트는 계속 통과한다(Python 쪽만 보니까). 그러면 어긋남은 사람이
# 대화형 Maya에서 언로드 크래시로 만나기 전에는 드러나지 않는다. C++ 소스
# 자체를 읽어서 두 리터럴이 실제로 거기 있는지 대조해 계약을 양쪽 다
# 고정한다(setStyleSheet 점검이 이미 쓰는 것과 같은 소스-읽기 기법).
_thisDir = os.path.dirname(os.path.abspath(__file__))
_pluginMainCpp = os.path.join(_thisDir, "..", "..", "src", "maro_plugin", "MaroPluginMain.cpp")
with open(_pluginMainCpp, encoding="utf-8") as _handle:
    _pluginMainSource = _handle.read()
assert maroMainWindow.CONTROL_NAME in _pluginMainSource, (
    f"MaroPluginMain.cpp no longer mentions {maroMainWindow.CONTROL_NAME!r} -- "
    "unload cleanup would silently no-op"
)
assert maroMainWindow.VIEWPORT_NAME_MAYA in _pluginMainSource, (
    f"MaroPluginMain.cpp no longer mentions {maroMainWindow.VIEWPORT_NAME_MAYA!r} -- "
    "unload cleanup would silently no-op"
)
assert maroMainWindow.VIEWPORT_NAME_ROS in _pluginMainSource, (
    f"MaroPluginMain.cpp no longer mentions {maroMainWindow.VIEWPORT_NAME_ROS!r} -- "
    "unload cleanup would silently no-op"
)
print("C++/Python UI name contract OK (pinned on both sides, 3 names)")

# 배치 모드에서 buildUI()를 부르면 QWidget 생성으로 프로세스가 abort한다 --
# 가드가 그것을 잡을 수 있는 예외로 바꾼다. 이 테스트가 통과한다는 것 자체가
# (프로세스가 살아서 다음 줄을 출력한다는 것이) 가드가 동작한다는 증거다.
try:
    maroMainWindow.buildUI()
    raise AssertionError("buildUI() must refuse to run in batch mode")
except RuntimeError as e:
    assert "batch" in str(e), f"unexpected refusal message: {e}"
print("batch-mode guard OK")

# 설계 스펙 §4.2: 새 .py는 setStyleSheet()를 부르지 않는다 -- Maya 프로세스
# 전역 QApplication의 팔레트/스타일을 그대로 물려받아야 기존 mayaUI와
# 이질감이 없다. 기계적으로 점검할 수 있는 규율이므로 기계가 점검한다.
#
# 찾는 문자열이 "setStyleSheet("가 아니라 ".setStyleSheet("인 이유: 그 규율을
# 설명하는 주석/도크스트링 자체가 이름을 언급한다(실제로 첫 실행에서 이
# 단언이 그 문장에 걸렸다). 호출은 언제나 어떤 위젯에 대고 하므로 점이
# 앞에 붙는다 -- 규율을 어기는 코드만 걸리고 규율을 적어 둔 산문은 걸리지
# 않는다.
with open(stagedModule, encoding="utf-8") as handle:
    source = handle.read()
assert ".setStyleSheet(" not in source, (
    "maroMainWindow.py must not call setStyleSheet() -- it has to inherit "
    "Maya's global Qt style (design spec 4.2)"
)
print("no setStyleSheet OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(pluginName)
assert not cmds.pluginInfo(pluginName, query=True, loaded=True), (
    "plug-in should be unloaded"
)
try:
    cmds.maroMainWindow()
    raise AssertionError("maroMainWindow must be deregistered after unload")
except (RuntimeError, AttributeError):
    pass
print("deregistered after unload OK")

maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
