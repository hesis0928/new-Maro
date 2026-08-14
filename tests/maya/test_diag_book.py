"""기지 에러 즉답: 같은 에러를 두 번 유발하면 두 번째는 book에서 즉답으로
나오고 재분석(신규 분석 카운트 증가)이 일어나지 않는지 확인한다."""
import os
import sys
import tempfile

import maya.standalone

# book 파일을 이 테스트 전용 임시 디렉터리로 돌린다. 실제
# internalVar -userAppDir를 쓰면 반복 실행마다 지식이 쌓여 재현이 안 된다.
os.environ["MARO_DIAG_BOOK_DIR"] = tempfile.mkdtemp(prefix="maro_diag_book_")

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

light = cmds.createNode("pointLight", name="rejectLight")
axis = cmds.createNode("maroAxis", name="rejectAxis")

analysisBefore = cmds.maroDiagAnalysisCount()

# 1회차: book에 없으므로 새로 분석하고 스필에 남긴다.
try:
    cmds.maroBindAxis(axis, light)
    raise AssertionError("expected rejection")
except RuntimeError:
    pass

analysisAfterFirst = cmds.maroDiagAnalysisCount()
assert analysisAfterFirst == analysisBefore + 1, "first occurrence should trigger fresh analysis"

first = cmds.maroDiagQuery(index=0)
assert first[8] == "0", "first occurrence must not claim it was served from book"
print("first occurrence OK")

# book이 인메모리 캐시로 몰래 바뀌어도 이 테스트가 안 흔들리려면, 1회차
# 분석이 실제로 디스크의 스필 파일에 남았는지부터 확인해야 한다 -- 이게
# 없으면 아래 2회차 즉답은 "같은 프로세스가 기억한다"만 증명할 뿐 "book이
# 세션을 넘어 살아남는다"는 증명하지 못한다.
spillPath = os.path.join(os.environ["MARO_DIAG_BOOK_DIR"], "maro_knowledge.spill.jsonl")
assert os.path.exists(spillPath), (
    f"expected spill file at {spillPath} after first occurrence, but it does not exist"
)
with open(spillPath, "r", encoding="utf-8") as f:
    spillContents = f.read()
assert first[2] in spillContents, (
    f"expected spill file at {spillPath} to contain the error hash {first[2]!r} "
    f"recorded by the first occurrence, but it was not found in: {spillContents!r}"
)
print("first occurrence reached disk OK")

# 2회차: 완전히 같은 사이트(같은 노드 타입/커맨드)이므로 해시가 같다.
try:
    cmds.maroBindAxis(axis, light)
    raise AssertionError("expected rejection")
except RuntimeError:
    pass

analysisAfterSecond = cmds.maroDiagAnalysisCount()
assert analysisAfterSecond == analysisAfterFirst, (
    f"second occurrence must NOT trigger a new analysis, "
    f"count went {analysisAfterFirst} -> {analysisAfterSecond}"
)

second = cmds.maroDiagQuery(index=0)
assert second[8] == "1", "second occurrence must be served from book"
assert second[2] == first[2], "same failure must hash the same both times"
assert first[1] in second[1], "the cached message should carry the original analysis text forward"
print("second occurrence served from book OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
