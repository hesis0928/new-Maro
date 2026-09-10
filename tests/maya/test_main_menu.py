"""maroBuildMenu 커맨드가 배치 모드에서 검증할 수 있는 만큼을 검증한다.

이 파일이 무엇을 **못** 하는지 먼저 분명히 해 둔다. 실측(2026-08-24,
Maya 2026, mayapy 배치에서 cmds.menu/cmds.menuItem을 직접 호출해 확인):
배치 모드에는 실제 Maya 메인 윈도우가 없어 "MayaWindow"라는 이름의 컨트롤
자체가 존재하지 않는다. 그런데 `cmds.menu(parent="MayaWindow", ...)`와
`cmds.menuItem(...)`는 그 상황에서 파이썬 예외를 던지지 않는다 -- 그냥
아무것도 만들지 않고 False를 돌려준다(workspaceControl이 배치 모드에서
하는 것과 정확히 같은 동작 -- test_main_window.py 참고). `cmds.menu(...,
exists=True)`도 계속 False이므로 python/maroMenu.py의 멱등성 가드는 매번
통과하지 못하고 매번 끝까지 실행되지만, 매번 아무것도 만들지 않으므로
무해하다.

즉 이 태스크의 진짜 목표(메뉴가 실제로 Maya 메인 메뉴바에 나타나는가, 클릭이
Maro 창을 여는가)는 여기서 **원리적으로** 확인할 수 없다 -- 대화형 Maya
2026에서 사람이 확인해야 한다(maroMainWindow/maroDiagPanel과 같은 한계).

여기서 확인할 수 있는 것:
  - 커맨드가 등록되고, 부르면 예외 없이 끝난다(= C++ 브리지가 플러그인
    디렉터리를 찾아 sys.path에 넣고 모듈을 import하는 데까지 성공했다).
  - 그 import가 실제로 일어났다(sys.modules로 확인).
  - `cmds.menu("maroMainMenu", exists=True)`는 배치 모드에서 계속 False다
    (실제로 만들어지지 않았다는 사실을 값으로 고정한다 -- 이게 True로
    바뀌는 순간 이 파일의 위 전제 자체가 깨진 것이므로 재검토가 필요하다).
  - 재진입(두 번째 호출)도 예외 없이 끝난다.
  - 언로드하면 커맨드가 사라진다(uninitializePlugin의 `menu -exists
    maroMainMenu` 가드도 배치 모드에서 항상 False이므로 예외 없이 지나간다).
"""
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
pluginName = os.path.splitext(os.path.basename(plugin))[0]
pluginDir = os.path.dirname(plugin)

# CMake가 .py를 .mll 옆에 스테이징했는가(MARO_PLUGIN_PY_MODULES).
stagedModule = os.path.join(pluginDir, "maroMenu.py")
assert os.path.isfile(stagedModule), (
    f"maroMenu.py must be staged next to the plug-in, not found at {stagedModule}"
)
print("module staged next to the plug-in OK")

# 배치 모드에는 애초에 "MayaWindow"가 없다 -- 이 파일 위쪽 전제를 그 자체로
# 값으로 고정해 둔다.
assert cmds.window("MayaWindow", exists=True) is False, (
    "batch mode should have no MayaWindow control -- if this ever becomes "
    "True, the whole premise of this test file (and maroMenu.py's lack of "
    "an about(batch=True) guard) needs re-checking"
)
print("no MayaWindow in batch mode OK (premise check)")

cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

registered = cmds.pluginInfo(pluginName, query=True, command=True) or []
assert "maroBuildMenu" in registered, (
    f"maroBuildMenu must be registered by the plug-in, got {sorted(registered)}"
)
print("command registered OK")

# [최종 리뷰 I5 반영] initializePlugin은 이제 maroBuildMenu를 즉시 부르지
# 않고 MGlobal::executeCommandOnIdle로 유휴 큐에 넣기만 한다
# (MaroPluginMain.cpp 참고) -- 그리고 배치 mayapy는 그 유휴 큐를 돌리지
# 않으므로, loadPlugin() 시점에는 이 큐잉이 실제로 실행됐을 수도 안 됐을
# 수도 있다(계약이 아니라 구현 세부사항). 그래서 아래에서 직접 한 번 더
# 부르는 것으로 결정론적으로 만든다.
#
# 배치 모드에는 UI가 없으므로 실제 메뉴는 만들어지지 않는다(예외도 나지
# 않는다). 이 호출이 실제로 확인하는 것은 C++ 쪽 전부다: findPlugin ->
# loadPath -> sys.path 주입 -> import maroMenu -> build(). 그 어느 단계가
# 깨져도 여기서 RuntimeError로 드러난다.
#
# test_main_window.py와 달리 "아직 import 안 됐다"는 전제할 수 없다 --
# 위에서 설명한 큐잉이 loadPlugin() 시점에 이미 실행됐을 수도 있어서
# maroMenu가 먼저 sys.modules에 들어가 있을 가능성을 배제할 수 없다.
# 그래서 아래에서는 "이제는 import돼 있다"만 확인한다.
cmds.maroBuildMenu()
assert "maroMenu" in sys.modules, (
    "running the command must have imported the staged maroMenu module"
)
print("command imports the staged module OK")

# 배치 모드에서는 cmds.menu()가 아무것도 만들지 않고 False만 돌려주므로
# (exists=True도 계속 False), 이 두 번째 호출은 build()의 "이미 있으면
# 리턴" 분기를 실제로 타지 않는다 -- 재진입해도 예외가 안 난다는 것만
# 증명한다. 멱등 분기 자체는 대화형 Maya에서만 검증 가능하다.
cmds.maroBuildMenu()
print("second invocation OK (re-entrancy only, not the idempotency branch)")

import maroMenu  # noqa: E402

# C++와 공유하는 이름 계약. MaroPluginMain.cpp의 uninitializePlugin이 언로드할
# 때 이 문자열을 MEL로 다시 부른다 -- 어긋나면 메뉴 정리가 조용히 아무 것도
# 안 하게 된다. 여기서 값으로 고정한다.
assert maroMenu.MENU_NAME == "maroMainMenu", (
    f"MENU_NAME must match the MEL cleanup in MaroPluginMain.cpp, "
    f"got {maroMenu.MENU_NAME!r}"
)

# [최종 리뷰 I7] 위 assert는 Python 쪽 값만 본다 -- MaroPluginMain.cpp의 MEL
# 정리 문자열이 나중에 바뀌어도 이 테스트는 계속 통과한다. C++ 소스를 직접
# 읽어서 계약을 양쪽 다 고정한다(test_main_window.py의 같은 점검, 그리고
# 원래 setStyleSheet 점검이 쓰는 것과 같은 소스-읽기 기법).
_thisDir = os.path.dirname(os.path.abspath(__file__))
_pluginMainCpp = os.path.join(_thisDir, "..", "..", "src", "maro_plugin", "MaroPluginMain.cpp")
with open(_pluginMainCpp, encoding="utf-8") as _handle:
    _pluginMainSource = _handle.read()
assert maroMenu.MENU_NAME in _pluginMainSource, (
    f"MaroPluginMain.cpp no longer mentions {maroMenu.MENU_NAME!r} -- "
    "unload cleanup would silently no-op"
)
print("C++/Python menu name contract OK (pinned on both sides)")

# 배치 모드에서는 메뉴가 실제로 만들어지지 않는다 -- 이 파일 도크스트링의
# 핵심 주장을 값으로 고정한다.
assert cmds.menu(maroMenu.MENU_NAME, exists=True) is False, (
    "batch mode has no MayaWindow, so cmds.menu(parent='MayaWindow', ...) "
    "must not have created a real menu -- if this is ever True, maroMenu.py "
    "needs an about(batch=True) guard after all"
)
print("menu not actually created in batch mode OK (documents the batch-mode limit)")

cmds.file(new=True, force=True)
cmds.unloadPlugin(pluginName)
assert not cmds.pluginInfo(pluginName, query=True, loaded=True), (
    "plug-in should be unloaded"
)
try:
    cmds.maroBuildMenu()
    raise AssertionError("maroBuildMenu must be deregistered after unload")
except (RuntimeError, AttributeError):
    pass
print("deregistered after unload OK")

print("[test] build()의 멱등성 가드 (cmds 스텁)")

# 배치 모드에서는 cmds.menu(exists=True)가 항상 False라 위 두 번째 호출이
# 멱등 분기를 **타지 않는다**(이 파일 상단 도크스트링 참고). 하지만 가드
# 자체는 Maya 메뉴 시스템이 아니라 분기 로직이므로, cmds를 스텁해 직접
# 검증할 수 있다. 대화형 Maya를 기다릴 이유가 없다.


class _MenuSpy(object):
    """maroMenu가 쓰는 cmds 표면만 흉내낸다."""

    def __init__(self, menuExists):
        self._menuExists = menuExists
        self.created = []
        self.items = []

    def menu(self, *args, **kwargs):
        if kwargs.get("exists"):
            return self._menuExists
        self.created.append(args[0] if args else None)
        return args[0] if args else None

    def menuItem(self, *args, **kwargs):
        self.items.append(kwargs.get("label", "(divider)"))
        return kwargs.get("label")


_realCmds = maroMenu.cmds
try:
    # 메뉴가 이미 있다 -> 아무것도 만들지 않고 즉시 리턴해야 한다.
    _spyExisting = _MenuSpy(menuExists=True)
    maroMenu.cmds = _spyExisting
    maroMenu.build()
    assert _spyExisting.created == [], _spyExisting.created
    assert _spyExisting.items == [], _spyExisting.items

    # 메뉴가 없다 -> 실제로 만든다. 이 대조가 없으면 위 단언이 "스텁이
    # 애초에 아무것도 안 불렸다"는 이유로 공허하게 통과할 수 있다.
    _spyFresh = _MenuSpy(menuExists=False)
    maroMenu.cmds = _spyFresh
    maroMenu.build()
    assert _spyFresh.created == [maroMenu.MENU_NAME], _spyFresh.created
    assert len(_spyFresh.items) > 0, _spyFresh.items
finally:
    maroMenu.cmds = _realCmds

print("build() idempotency guard OK (existing -> %d items, fresh -> %d items)"
      % (len(_spyExisting.items), len(_spyFresh.items)))


maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
