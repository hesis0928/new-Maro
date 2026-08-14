"""기지 에러 즉답: 같은 에러를 두 번 유발하면 두 번째는 book에서 즉답으로
나오고 재분석(신규 분석 카운트 증가)이 일어나지 않는지 확인한다."""
import os
import sys

import maya.standalone

# 리뷰(carried-forward Minor): 예전에는 여기서 tempfile.mkdtemp()로 자기만의
# book 디렉터리를 만들어 MARO_DIAG_BOOK_DIR을 덮어썼다. 그러면 CMake가 이미
# 이 테스트 전용으로 준 디렉터리(tests/CMakeLists.txt의 MARO_TEST_BOOK_ROOT,
# maya_diag_book_root_reset fixture가 스위트 시작 시 통째로 비운다)를 쓰지
# 않게 되어 그 fixture가 이 테스트에는 무의미해지고, 실행마다 새 임시
# 디렉터리가 하나씩 새서 정리되지 않았다. 이 테스트는 test_diag_degraded.py
# 처럼 "쓸 수 없는 경로" 같은 특수 구조가 필요 없다 -- 그냥 비어 있는 book
# 디렉터리 하나면 충분하므로 CMake가 이미 설정해 둔 MARO_DIAG_BOOK_DIR을
# 그대로 쓴다.
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

# 리뷰 Finding C1: message는 book 히트 여부와 무관하게 언제나 "지금 일어난
# 일"이어야 한다 -- 과거 분석 텍스트로 덮어써서는 안 된다. 이 테스트는 두
# 발생 모두 같은 axis/light를 재사용하므로 옛 구현(과거 분석으로 message를
# 덮어씀)이 만든 문자열과 새 구현(현재 message를 그대로 씀)이 만든 문자열이
# 텍스트로는 우연히 같아 보일 수 있다 -- 그래서 정확히 동일해야 한다는 것과
# (예전처럼 "...book에 있는 과거 분석에서 즉답" 표기가 덧붙지 않는다는 것), 과거 분석은
# 사라지지 않고 priorAnalysis(10번째 필드)로 별도로 남아야 한다는 것을 함께
# 확인한다. 두 노드 이름이 서로 다른 경우까지 잡는 것은 이 테스트의 몫이
# 아니다 -- 그건 test_diag_book_cross_session.py가 한다.
assert second[1] == first[1], (
    f"the second occurrence's message must be the CURRENT rendering (byte-"
    f"identical to the first here, since both occurrences reuse the same "
    f"axis/light), not the old book-analysis text with a cache-hit suffix "
    f"tacked on -- got {second[1]!r}"
)
assert first[9] == "", (
    f"a fresh (cache-miss) occurrence must have no priorAnalysis yet, got {first[9]!r}"
)
assert second[9] == first[1], (
    f"the second occurrence's priorAnalysis must carry the first occurrence's "
    f"message forward -- that is the whole point of keeping it separate from "
    f"message, got {second[9]!r}"
)
print("message stays current, priorAnalysis carries the past forward OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
