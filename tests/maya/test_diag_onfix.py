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
# 딱지까지 붙여 확신에 차서 제시한다.
#
# 리뷰 Finding 4: A/B 두 해시만 비교하면 "전부 하나로 뭉갬"은 잡지만, 부분
# 뭉갬 -- 예를 들어 NotMaroAxisNode/SelfParent/WouldCreateCycle 세 가지가
# 서로 하나로 접히는 경우 -- 은 여전히 통과한다. 태그 목록을 테스트에
# 복제하지 않으면서 이걸 잡으려면, N개의 서로 다른 거부를 한 번의 실행에서
# 유발하고 각 레코드의 해시가 실제로 N개 다 다른지 직접 세어 확인해야 한다.
rejections = []  # [(label, errorHash, message, activeCommand), ...]


def trigger_rejection(label, invoke):
    """invoke()가 RuntimeError로 거부되는지 확인하고 그 직후 최신 레코드를 모은다."""
    try:
        invoke()
        raise AssertionError(f"{label} should have been rejected")
    except RuntimeError:
        pass
    rec = cmds.maroDiagQuery(index=0)
    rejections.append((label, rec[2], rec[1], rec[5]))


cycleA = cmds.createNode("maroAxis", name="cycleAxisA")
cycleB = cmds.createNode("maroAxis", name="cycleAxisB")
plainCube = cmds.polyCube(name="plainCubeForConnect")[0]
cmds.maroConnectAxis(cycleB, cycleA)  # cycleB의 부모 = cycleA

trigger_rejection(
    "connect: not a maroAxis node",
    lambda: cmds.maroConnectAxis(plainCube, cycleA))
trigger_rejection(
    "connect: self-parent",
    lambda: cmds.maroConnectAxis(cycleA, cycleA))
trigger_rejection(
    "connect: would create a cycle",
    lambda: cmds.maroConnectAxis(cycleA, cycleB))
trigger_rejection(
    "bind: not a maroAxis node",
    lambda: cmds.maroBindAxis(light, plainCube))

hashes = [h for _, h, _, _ in rejections]
labels = [label for label, _, _, _ in rejections]
assert len(set(hashes)) == len(rejections), (
    f"expected {len(rejections)} distinct error hashes, one per rejection "
    f"{labels}, but only got {len(set(hashes))} distinct hashes back -- some "
    f"of these rejections share a site tag, so book will serve one "
    f"failure's stored analysis and remedy for a different failure"
)

by_label = {label: (h, msg, active) for label, h, msg, active in rejections}

cycle_hash, cycle_message, cycle_active_command = by_label["connect: would create a cycle"]
assert cycle_hash != errorHash, (
    f"a cycle rejection and a non-transform binding rejection are different "
    f"failures and must not share an error hash -- both hashed to "
    f"{cycle_hash!r}, so book will serve one failure's analysis for the other"
)
assert "cycle" in cycle_message, (
    f"the cycle rejection must show its own explanation, not another "
    f"failure's, got {cycle_message!r}"
)
assert cycle_active_command == "MaroConnectAxisCommand", (
    f"expected activeCommand 'MaroConnectAxisCommand', got {cycle_active_command!r}"
)
print(
    f"distinct failures kept distinct site tags OK "
    f"({len(rejections)} rejections, {len(set(hashes))} distinct hashes)"
)

# 리뷰 Finding 1: redoIt/undoIt(그리고 doIt의 예외 경로)에 설치된 마커는
# capture()를 거치지 않고 BoadMaro::error()를 기본 컨텍스트(DgContext{})로
# 부른다. 위의 검증-거부 시나리오들은 전부 onfix::capture()를 거쳐
# activeCommand가 채워지므로 이 경로에는 닿지 않는다. maroDiagEmitMarked는
# 그 기본-컨텍스트 경로를 재현하는 테스트 전용 도구다: 자기 이름의 마커를
# 설치한 채로 error()를 세 번째 인자 없이 부른다. error()가
# g_commandStack에서 activeCommand를 채워 넣지 않으면 이 값은 빈 문자열로
# 남는다 -- 바로 그게 Finding 1이 지적한, 수정 전 상태다.
before_marked = cmds.maroDiagCount()
cmds.maroDiagEmitMarked(siteTag="Test.MarkedProbe", message="marked probe")
after_marked = cmds.maroDiagCount()
assert after_marked == before_marked + 1, (
    f"expected exactly one new diagnostic record from maroDiagEmitMarked, "
    f"got {after_marked - before_marked}"
)
markedRec = cmds.maroDiagQuery(index=0)
assert markedRec[5] == "MaroDiagEmitMarkedCommand", (
    f"expected activeCommand 'MaroDiagEmitMarkedCommand' filled in by "
    f"BoadMaro::error() from the live marker stack (the default-context "
    f"path exercised by doIt/redoIt/undoIt catch blocks), got {markedRec[5]!r}"
)
print("default-context activeCommand fill-in OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
