"""강등: 감시자는 애초에 없고(Layer A), book 파일마저 쓸 수 없을 때도 진단이
계속 동작하는지 확인한다 (설계 스펙 §3.6, §5.4). 또한 book이 쓰기 불가능한
상태로 조용히 멈추면 안 되고(_DEBUG 밖에서 devInfo는 무연산이므로, 이 프로젝트가
실제로 빌드/테스트하는 RelWithDebInfo에서는 book 실패가 devInfo만으로는 아무
데도 보이지 않는다), boad(BoadMaro::warn)를 통해 세션당 한 번은 반드시
알려야 한다는 것도 함께 확인한다."""
import os
import sys
import tempfile

import maya.standalone

# 부모가 "디렉터리"가 아니라 평범한 파일이 되게 만들어, book 경로 아래
# create_directories가 항상 실패하게 강제한다.
parentDir = tempfile.mkdtemp(prefix="maro_diag_degraded_")
blockerFile = os.path.join(parentDir, "blocker")
with open(blockerFile, "w") as f:
    f.write("this occupies the path a directory would need")

bookDir = os.path.join(blockerFile, "nested", "book")
os.environ["MARO_DIAG_BOOK_DIR"] = bookDir
expectedSpillPath = os.path.join(bookDir, "maro_knowledge.spill.jsonl")

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

light = cmds.createNode("pointLight", name="degradedLight")
axis = cmds.createNode("maroAxis", name="degradedAxis")

countBefore = cmds.maroDiagCount()
analysisBefore = cmds.maroDiagAnalysisCount()

# book을 쓸 수 없는 상태에서 같은 에러를 두 번 유발한다. 둘 다 정상적으로
# RuntimeError로 거부돼야 한다 -- 여기서 예외가 Maya 콜백 경계를 넘으면 이
# 스크립트 자체가 트레이스백과 함께 죽고 "teardown OK"에 닿지 못한다.
for _ in range(2):
    try:
        cmds.maroBindAxis(axis, light)
        raise AssertionError("expected rejection")
    except RuntimeError:
        pass

countAfter = cmds.maroDiagCount()
analysisAfter = cmds.maroDiagAnalysisCount()

# book을 쓸 수 없으면 BoadMaro::error()는 매번 appendToSpill()의 실패를
# 관측하지만, 그것 자체는 예외가 아니다 -- BookStore::appendToSpill과
# loadFile/loadMerged은 std::error_code 기반이라 디렉터리를 못 만들어도
# 예외를 던지지 않고 false/빈 결과를 돌려준다. 그래서 error()의 try 블록은
# 정상적으로 else(캐시 미스) 분기를 타고, 첫 발생에서 book이 쓰기 불가능함을
# 발견해 warn()을 한 번 내보낸 뒤 error() 자신의 레코드를 남긴다. 두 번째
# 발생은 같은 사실(book이 쓰기 불가능함)을 다시 발견하지만 래치가 이미
# 설정돼 있어 warn()을 또 내보내지 않고 error() 레코드만 남긴다.
# 그래서 새로 늘어난 레코드는 2(warn+error)+1(error) = 3개다.
assert countAfter == countBefore + 3, (
    f"diagnostics must keep flowing even if book can't persist, and book "
    f"unwritable must be announced once via warn() on the first occurrence "
    f"only -- expected {countBefore} -> {countBefore + 3}, got {countAfter}"
)
print("diagnostics kept flowing (including the one-time warn) OK")

# book이 아무것도 저장할 수 없으므로 두 번째 발생도 "새 분석"으로 취급된다
# -- 캐시 히트를 거짓으로 주장하지 않는다는 뜻이다. warn()은 g_freshAnalysisCount를
# 건드리지 않으므로 이 단언은 그대로다.
assert analysisAfter == analysisBefore + 2, (
    f"with book unwritable, every occurrence must be treated as fresh, "
    f"count went {analysisBefore} -> {analysisAfter}"
)
print("no false cache hits under degrade OK")

latest = cmds.maroDiagQuery(index=0)
assert latest[8] == "0", "degraded book must never claim servedFromBook"
print("servedFromBook stayed honest OK")

# 늘어난 3개(가장 최근 3개) 중 정확히 하나가 warn이고, 그 메시지가 쓸 수 없는
# 저장소 경로를 담고 있는지 확인한다. devInfo는 이 빌드 구성(RelWithDebInfo,
# _DEBUG 미정의)에서 무연산이므로, 이 경고가 실제로 boad::warn()을 거쳐
# 나온 유일한 신호다.
newRecords = [cmds.maroDiagQuery(index=i) for i in range(countAfter - countBefore)]
warnRecords = [r for r in newRecords if r[0] == "warn"]
assert len(warnRecords) == 1, (
    f"expected exactly one warn record among the {len(newRecords)} new records, "
    f"got {len(warnRecords)}: severities={[r[0] for r in newRecords]}"
)
warnMessage = warnRecords[0][1]
assert expectedSpillPath in warnMessage, (
    f"the book-unwritable warning must name the unwritable store path so the "
    f"user can act on it -- expected {expectedSpillPath!r} to appear in "
    f"{warnMessage!r}"
)
print("book-unwritable warning named the store path OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
