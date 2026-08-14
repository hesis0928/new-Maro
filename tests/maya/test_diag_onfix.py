"""onfix DG 컨텍스트 포착: 실제 노드 타입·어트리뷰트·커맨드가 기록되는지
확인한다. "값이 무엇인지"를 단언한다 -- "뭔가 기록됐다"가 아니다."""
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

before = cmds.maroDiagCount()

# transform이 아닌 대상에 바인딩을 시도한다 (test_binding.py의 3번 시나리오와 동일).
light = cmds.createNode("pointLight", name="rejectLight")
axis = cmds.createNode("maroAxis", name="rejectAxis")
try:
    cmds.maroBindAxis(axis, light)
    raise AssertionError("binding to a non-transform should have been rejected")
except RuntimeError:
    pass

after = cmds.maroDiagCount()
assert after == before + 1, (
    f"expected exactly one new diagnostic record from the rejection, "
    f"got {after - before}"
)
print("record emitted OK")

rec = cmds.maroDiagQuery(index=0)
severity, message, errorHash, nodeType, attributeName, activeCommand, axisOrTarget, remedy, servedFromBook = rec

assert severity == "error", f"expected severity 'error', got {severity!r}"
assert nodeType == "pointLight", f"expected nodeType 'pointLight', got {nodeType!r}"
assert attributeName == "targetObject", f"expected attributeName 'targetObject', got {attributeName!r}"
assert activeCommand == "MaroBindAxisCommand", (
    f"expected activeCommand 'MaroBindAxisCommand', got {activeCommand!r}"
)
assert axisOrTarget == "rejectAxis", f"expected axisOrTarget 'rejectAxis', got {axisOrTarget!r}"
print("DG context values OK")

# 커맨드 컨텍스트 스택이 doIt 반환 후 확실히 비었는지 -- maroDiagEmit은
# 마커를 설치하지 않는 테스트 도구이므로, 그 에러의 activeCommand가 비어
# 있어야 위 마커가 새지 않고 정확히 pop됐다는 뜻이다.
cmds.maroDiagEmit(severity="error", message="probe", siteTag="Test.Probe")
probe = cmds.maroDiagQuery(index=0)
assert probe[5] == "", f"expected empty activeCommand after doIt returned, got {probe[5]!r}"
print("stack unwound OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
