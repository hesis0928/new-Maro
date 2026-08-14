"""워커 스레드 가드: 메인 스레드가 아닌 곳에서 boad로 진단을 내보내도
(1) 프로세스가 살아남고 (2) 레코드는 내용 그대로 스트림에 남는지 확인한다.

왜 필요한가: Task 7이 compute() 안의 진단들(MaroAxisNode 하나 + 능력 노드 넷 +
MaroCommandDeviceNode)을 boad로 옮겼는데, Maya 2026의 기본 평가 관리자
(Parallel Evaluation Manager)는 compute()를 워커 스레드에서 돌릴 수 있다.
boad의 info/warn/error는 안에서 Maya의 display* API를 부르고 그것은 메인
스레드에서만 안전하다. 그래서 boad 안에 메인 스레드 가드를 뒀다 -- 레코드는
언제나 남기고, display* 에코만 워커에서 건너뛴다.

이 테스트가 증명하는 것: 워커에서 들어온 진단이 (a) 실제로 워커로 판정되고
(b) 그럼에도 스트림에 정확한 내용으로 남는다. 즉 "가드가 화면 에코를
건너뛰면서 기록까지 같이 버리지는 않는다".

이 테스트가 증명하지 못하는 것: 가드를 제거했을 때 크래시한다는 것.
mayapy 배치 모드의 display* 경로는 워커 호출을 관대하게 넘길 수 있어서,
가드 제거가 반드시 관측 가능한 실패로 이어지지는 않는다 -- task-7-report.md의
"의도적 파괴" 절에 실제로 시도한 결과를 그대로 적어 두었다. 그래서 이
파일은 "크래시하지 않음"이 아니라 "기록이 남음"을 단언한다.
"""
import os
import sys
import tempfile

import maya.standalone

# error() 경로가 book을 건드리므로 이 테스트 전용 임시 디렉터리로 돌린다
# (test_diag_book.py와 같은 이유). 여기 없으면 사용자의 실제 Maya prefs에
# 스필이 쌓인다.
os.environ["MARO_DIAG_BOOK_DIR"] = tempfile.mkdtemp(prefix="maro_diag_thread_")

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

before = cmds.maroDiagCount()

# 1) warn: book I/O가 없는 경로. 워커에서 들어와도 그대로 기록돼야 한다.
sawWorker = cmds.maroDiagEmitFromThread(severity="warn",
                                        message="worker thread warn")
assert sawWorker == 1, (
    "the emit must actually happen off the main thread -- boad judged the "
    "spawned std::thread to be the main thread, so this test would prove "
    "nothing about the guard"
)
print("emit really ran on a non-main thread OK")

afterWarn = cmds.maroDiagCount()
assert afterWarn == before + 1, (
    f"a diagnostic emitted from a worker thread must still be recorded -- "
    f"expected {before + 1} records, got {afterWarn}"
)

warnRecord = cmds.maroDiagQuery(index=0)
assert warnRecord[0] == "warn", f"expected severity 'warn', got {warnRecord[0]!r}"
assert warnRecord[1] == "worker thread warn", (
    f"the worker's message must survive intact, got {warnRecord[1]!r}"
)
print("worker warn recorded with the right content OK")

# 2) error: book 조회/기록까지 도는 무거운 경로. 워커에서 들어와도
#    프로세스가 살아남고 해시까지 정상적으로 채워져야 한다.
analysisBefore = cmds.maroDiagAnalysisCount()
sawWorker = cmds.maroDiagEmitFromThread(severity="error",
                                        message="worker thread error",
                                        siteTag="Test.WorkerThread")
assert sawWorker == 1, "the error emit must also run off the main thread"

afterError = cmds.maroDiagCount()
assert afterError == afterWarn + 1, (
    f"a worker-thread error must still be recorded -- expected "
    f"{afterWarn + 1} records, got {afterError}"
)

errorRecord = cmds.maroDiagQuery(index=0)
assert errorRecord[0] == "error", f"expected severity 'error', got {errorRecord[0]!r}"
assert "worker thread error" in errorRecord[1], (
    f"the worker's error message must survive intact, got {errorRecord[1]!r}"
)
assert errorRecord[2], "a worker-thread error must still get an error hash"
# 워커에는 커맨드 컨텍스트 스택(thread_local)이 없다 -- doIt의 마커는 메인
# 스레드 스택에만 있으므로 activeCommand는 비어 있는 것이 정답이다.
assert errorRecord[5] == "", (
    f"a worker thread has its own (empty) command stack, so activeCommand "
    f"must be empty, got {errorRecord[5]!r}"
)
print("worker error recorded with hash and empty command context OK")

assert cmds.maroDiagAnalysisCount() == analysisBefore + 1, (
    "the worker-thread error must have reached book like any other fresh error"
)
spillPath = os.path.join(os.environ["MARO_DIAG_BOOK_DIR"],
                         "maro_knowledge.spill.jsonl")
assert os.path.exists(spillPath), (
    f"expected the worker-thread error to reach the spill file at {spillPath}"
)
with open(spillPath, "r", encoding="utf-8") as f:
    assert errorRecord[2] in f.read(), (
        "the worker-thread error's hash must be in the spill file -- book I/O "
        "must work from a worker thread too, not just the display echo"
    )
print("worker error reached book on disk OK")

# 3) 메인 스레드 경로가 가드 때문에 망가지지 않았는지 대조군으로 확인한다.
cmds.maroDiagEmit(severity="warn", message="main thread warn")
mainRecord = cmds.maroDiagQuery(index=0)
assert mainRecord[0] == "warn" and mainRecord[1] == "main thread warn", (
    f"the main-thread path must be unchanged by the guard, got {mainRecord!r}"
)
print("main thread path unaffected OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
