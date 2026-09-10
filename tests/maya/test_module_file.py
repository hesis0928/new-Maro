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
