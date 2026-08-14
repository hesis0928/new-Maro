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

# 커맨드 컨텍스트 스택이 doIt 반환 후 확실히 비었는지 확인한다.
# maroDiagEmit(MaroDiagEmitCommand::doIt)은 스스로 ScopedCommandContext를
# 설치하지 않는다 -- 그 error() 호출은 onfix::capture("", "", "")로 그때
# 살아 있는 스택을 그대로 읽어 activeCommand를 채울 뿐이다. 즉 이 probe는
# maroDiagEmit 자신의 컨텍스트가 아니라, 위에서 실행한 MaroBindAxisCommand의
# 마커가 doIt 반환 시점에 확실히 pop됐는지를 그대로 드러낸다. 스택이 비어
# 있으면 activeCommand는 빈 문자열이어야 한다 -- 위 마커가 샜다면(예: 소멸자가
# no-op이 되면) 여기서 'MaroBindAxisCommand'가 그대로 보인다.
cmds.maroDiagEmit(severity="error", message="probe", siteTag="Test.Probe")
probe = cmds.maroDiagQuery(index=0)
assert probe[5] == "", f"expected empty activeCommand after doIt returned, got {probe[5]!r}"
print("stack unwound OK")

# 서로 다른 실패는 서로 다른 사이트 태그를 가져야 한다.
#
# 왜 이 단언이 있는가: Task 7이 ~37곳의 검증 실패를 boad로 옮기면서 각 자리에
# 고유한 사이트 태그를 붙였다. 그 태그들을 하나로 뭉뚱그려도(예: 전부
# "MaroCommands.Failure") 컴파일되고, 모든 커맨드가 여전히 같은 MStatus를
# 돌려주므로 이 스위트의 나머지는 전부 통과한다 -- 실측으로 확인했다.
# 그런데 그 구현은 book이 "기지 에러 즉답"을 하는 순간 조용히 틀린 답을
# 내놓는다: 두 번째 종류의 실패가 첫 번째 종류의 분석을 "과거 분석에서 즉답"
# 딱지까지 붙여 확신에 차서 제시한다. 그래서 여기서 두 종류의 실패가 실제로
# 다른 해시로 갈리는지 직접 확인한다.
cycleA = cmds.createNode("maroAxis", name="cycleAxisA")
cycleB = cmds.createNode("maroAxis", name="cycleAxisB")
cmds.maroConnectAxis(cycleB, cycleA)
try:
    cmds.maroConnectAxis(cycleA, cycleB)
    raise AssertionError("cycle should have been rejected")
except RuntimeError:
    pass

cycleRec = cmds.maroDiagQuery(index=0)
assert cycleRec[2] != errorHash, (
    f"a cycle rejection and a non-transform binding rejection are different "
    f"failures and must not share an error hash -- both hashed to "
    f"{cycleRec[2]!r}, so book will serve one failure's analysis for the other"
)
assert "cycle" in cycleRec[1], (
    f"the cycle rejection must show its own explanation, not another "
    f"failure's, got {cycleRec[1]!r}"
)
assert cycleRec[5] == "MaroConnectAxisCommand", (
    f"expected activeCommand 'MaroConnectAxisCommand', got {cycleRec[5]!r}"
)
print("distinct failures kept distinct site tags OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
