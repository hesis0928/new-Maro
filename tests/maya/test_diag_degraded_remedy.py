"""강등(해법 등록 경로): book(스필)을 쓸 수 없다는 사실을 registerRemedy()가
먼저 발견하는 경우도 error()가 발견하는 경우와 마찬가지로 boad(BoadMaro::warn)를
통해 세션당 한 번은 반드시 알려야 한다 (설계 스펙 §3.6, §5.4, Task 6).

test_diag_degraded.py는 같은 사실을 error()가 먼저 발견하는 경로만 검증한다.
경고 래치(g_bookUnwritableWarned)는 프로세스 전체에 한 번만 걸리는
std::atomic<bool>이므로, 같은 프로세스 안에서 error()를 먼저 태우면 그
래치를 소비해 버려 registerRemedy() 쪽의 경고를 더는 관찰할 수 없다. 그래서
이 파일은 별도 프로세스(별도 mayapy.exe, 따라서 별도의 깨끗한 래치)에서
error()를 전혀 건드리지 않고 registerRemedy()만으로 book-불가를 최초로
발견시킨다."""
import os
import sys
import tempfile

import maya.standalone

# 부모가 "디렉터리"가 아니라 평범한 파일이 되게 만들어, book 경로 아래
# create_directories가 항상 실패하게 강제한다 (test_diag_degraded.py와 동일 기법).
parentDir = tempfile.mkdtemp(prefix="maro_diag_degraded_remedy_")
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

countBefore = cmds.maroDiagCount()

# 에러를 하나도 유발하지 않은 채, 해법만 등록한다 -- registerRemedy()가
# appendToSpill() 실패를 관측하는 첫(그리고 유일한) 코드 경로가 되도록 한다.
# 해시는 임의 값이면 된다: registerRemedy()는 이 해시로 book을 조회/기록만
# 할 뿐, error()처럼 siteTag로부터 계산하지 않는다.
cmds.maroDiagRegisterRemedy(hash="deadbeefcafef00d",
                             remedy="Reboot the ROS bridge before retrying.")

countAfter = cmds.maroDiagCount()
# error()가 book-불가를 발견하면 warn 1개 + error 1개(총 2개)가 남지만,
# registerRemedy()에는 남길 error 레코드 자체가 없다 -- 여기서는 warn
# 하나만 새로 생겨야 한다.
assert countAfter == countBefore + 1, (
    f"registerRemedy() discovering an unwritable book must emit exactly one "
    f"new record (a warn -- there is no accompanying error record on this "
    f"path) -- expected {countBefore} -> {countBefore + 1}, got {countAfter}"
)
print("registerRemedy discovered the unwritable book and warned once OK")

latest = cmds.maroDiagQuery(index=0)
assert latest[0] == "warn", (
    f"the record registerRemedy() left behind must be a warn, got severity "
    f"{latest[0]!r}"
)
assert expectedSpillPath in latest[1], (
    f"the book-unwritable warning discovered via registerRemedy() must name "
    f"the unwritable spill path so the user can act on it -- expected "
    f"{expectedSpillPath!r} to appear in {latest[1]!r}"
)
print("book-unwritable warning (via registerRemedy) named the store path OK")

# 같은 해시로 다시 등록해도 book은 여전히 쓸 수 없다. 래치가 이미 걸려
# 있으므로 이번에는 새 레코드가 전혀 생기면 안 된다 -- 매 실패마다 경고하는
# 회귀(래치 무력화)라면 여기서 걸린다.
cmds.maroDiagRegisterRemedy(hash="deadbeefcafef00d",
                             remedy="Reboot the ROS bridge before retrying.")
countAfterSecond = cmds.maroDiagCount()
assert countAfterSecond == countAfter, (
    f"the book-unwritable warn latch fires once per process, not once per "
    f"call -- a second registerRemedy() failure must not add another record, "
    f"expected count to stay at {countAfter}, got {countAfterSecond}"
)
print("second registerRemedy failure did not re-warn (latch holding) OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
