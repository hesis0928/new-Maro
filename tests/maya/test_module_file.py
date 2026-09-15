"""생성된 maro.mod가 실제로 Maya에게 플러그인을 **이름으로** 찾게 해 주는가.

이 파일이 지키는 회귀는 UI가 아니라 배포 경로다. `workspaceControl
-requiredPlugin "maro"`는 플러그인을 이름으로 로드하는데, 이름은
MAYA_PLUG_IN_PATH로만 해석된다. 이 저장소의 빌드 트리는 거기 없어서
도킹한 Maro 창이 Maya 재시작 후 복원되지 않았다(2026-09-10 원인 규명,
docs/maro-main-ui-manual-checklist.md의 "재시작 복원" 항목).

**이 테스트는 다른 maya 테스트들과 환경이 다르다.** 나머지는 ctest가
MARO_PLUGIN_PATH(전체 경로)와 PATH 선행을 넣어 주지만, 여기서는 둘 다
일부러 주지 않는다 -- .mod가 그 두 가지를 스스로 해내는지가 검증 대상이기
때문이다. MAYA_MODULE_PATH만 받는다.

실측으로 확인한 것(2026-09-10): 스테이징 디렉터리는 maro.mll과 ROS 2 DLL
154개와 파이썬 모듈이 **평평하게** 한 곳에 있다. 그래서 .mod의 세 경로가
전부 "."이고, Maya의 기본 <base>/plug-ins 규약을 따르지 않는다. PATH 줄이
빠지면 Maya는 maro.mll을 찾고도 의존 DLL을 못 찾아 로드에 실패한다.

두 번째 회귀(2026-09-15): 로드 성공만으로는 "스테이징된 DLL이 로드됐다"가
보장되지 않는다. .mod의 PATH 줄은 PATH 끝에 붙어서, 앞쪽에 같은 이름의
DLL이 있으면 그것이 이긴다. 그래서 GetModuleFileNameW로 실제 로드 경로가
스테이징 디렉터리인지까지 단언한다.
"""
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

modulePath = os.environ["MAYA_MODULE_PATH"]
print("MAYA_MODULE_PATH =", modulePath)

# ctest가 준 것은 .mod가 든 디렉터리다. 그 안에 실제로 파일이 있어야 한다 --
# 없으면 아래 loadPlugin 실패가 "생성이 안 됐다"인지 ".mod 내용이 틀렸다"
# 인지 구별되지 않는다.
modFile = os.path.join(modulePath.split(os.pathsep)[0], "maro.mod")
assert os.path.isfile(modFile), (
    "maro.mod was not generated at {!r} -- check the file(GENERATE) block in "
    "src/maro_plugin/CMakeLists.txt".format(modFile))
with open(modFile, "r", encoding="utf-8") as fh:
    modText = fh.read()
print(modText.strip())

# 세 줄이 전부 있어야 한다. 하나라도 빠지면 이름 로드가 조용히 다른 이유로
# 실패하므로 여기서 값으로 고정한다.
for required in ("plug-ins: .", "scripts: .", "PATH +:= ."):
    assert required in modText, (required, modText)
print("maro.mod generated with all three path lines OK")

# 이 테스트의 본론. MARO_PLUGIN_PATH도 PATH 선행도 없이, 오직 .mod만으로
# 이름 로드가 성공해야 한다 -- 이것이 -requiredPlugin이 실제로 하는 일이다.
assert "MARO_PLUGIN_PATH" not in os.environ, (
    "this test must run without MARO_PLUGIN_PATH -- it exists to prove the "
    ".mod alone is enough")
cmds.loadPlugin("maro")
print("loadPlugin by name OK (no full path, no PATH prepend)")

# 이름 로드가 성공했다는 것만으로는 부족하다(2026-09-15 실측). .mod의
# `PATH +:= .`는 PATH의 **끝**에 붙으므로, 시스템 PATH 앞쪽에 같은 이름의
# DLL이 있으면(당시 이 머신: ROS 2 바이너리 배포판 bin, 전역 vcpkg bin)
# 로더는 그쪽을 바인딩하고 스테이징 사본은 열리지도 않는다 -- 로드는 되지만
# 빌드가 링크한 것과 다른 바이너리로 돈다. 그래서 프로세스에 실제로 올라온
# 모듈의 경로를 스테이징 디렉터리와 대조한다. 이 검사가 의미 있는 것은 이
# 테스트가 PATH 선행 없이 도는 유일한 maya 테스트이기 때문이다.
import ctypes  # noqa: E402

kernel32 = ctypes.windll.kernel32
# 기본 반환 타입(int)은 x64 HMODULE을 32비트로 잘라 이후 호출이 무효 핸들로
# 실패한다 -- 핸들/포인터를 돌려주는 Win32 함수는 restype을 반드시 지정.
kernel32.GetModuleHandleW.restype = ctypes.c_void_p
kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
kernel32.GetModuleFileNameW.argtypes = [
    ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]


def loadedFrom(moduleName):
    handle = kernel32.GetModuleHandleW(moduleName)
    assert handle, "%s is not loaded in this process" % moduleName
    buf = ctypes.create_unicode_buffer(1024)
    assert kernel32.GetModuleFileNameW(handle, buf, 1024) > 0, moduleName
    return buf.value


stagingDir = os.path.normcase(os.path.dirname(
    cmds.pluginInfo("maro", query=True, path=True)))
# 직접 임포트(rclcpp/rcl/embree4)와 2차 의존(yaml은 install/opt/<vendor>/bin
# 출신)을 섞는다 -- 두 부류가 서로 다른 경로로 가려질 수 있다.
for dll in ("maro.mll", "rclcpp.dll", "rcl.dll", "embree4.dll", "yaml.dll"):
    loadedPath = loadedFrom(dll)
    assert os.path.normcase(os.path.dirname(loadedPath)) == stagingDir, (
        "%s was loaded from %r, not from the staging directory %r -- something "
        "earlier on PATH shadows the staged copy (docs/maro-master-reference.md "
        "section 3.6)" % (dll, loadedPath, stagingDir))
    print("  %-12s <- %s" % (dll, loadedPath))
print("all checked DLLs loaded from the staging directory OK")

# 찾기만 하고 초기화가 안 됐으면 반쪽이다. 커맨드가 실제로 등록됐는지 본다.
registered = cmds.pluginInfo("maro", query=True, command=True) or []
assert "maroMainWindow" in registered, sorted(registered)
assert "maroDiagPanel" in registered, sorted(registered)
print("plug-in initialised through the module file OK (%d commands)"
      % len(registered))

cmds.unloadPlugin("maro")
print("unload OK")

maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
