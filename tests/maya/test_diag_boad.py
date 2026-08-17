"""boad 진단 출구: 인메모리 스트림이 심각도·순서를 정확히 유지하는지 확인한다."""
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)

before = cmds.maroDiagCount()

cmds.maroDiagEmit(severity="info", message="hello info")
cmds.maroDiagEmit(severity="warn", message="hello warn")

after = cmds.maroDiagCount()
assert after == before + 2, f"expected {before + 2} records, got {after}"
print("count OK")

# index 0 = 가장 최근 = warn
latest = cmds.maroDiagQuery(index=0)
assert latest[0] == "warn", f"expected latest severity 'warn', got {latest[0]!r}"
assert latest[1] == "hello warn", f"expected latest message 'hello warn', got {latest[1]!r}"
print("latest record OK")

previous = cmds.maroDiagQuery(index=1)
assert previous[0] == "info"
assert previous[1] == "hello info"
print("previous record OK")

# 순번과 시각: 순서를 정하는 판단은 시각이 아니라 순번을 봐야 하므로
# (벽시계는 뒤로 갈 수 있다) 순번이 실제로 단조 증가하는지 값으로 확인한다.
cmds.maroDiagEmit(severity="info", message="seq probe A")
cmds.maroDiagEmit(severity="info", message="seq probe B")

newer = cmds.maroDiagQuery(index=0)
older = cmds.maroDiagQuery(index=1)

assert len(newer) == 12, f"expected 12 fields from maroDiagQuery, got {len(newer)}"

seqNewer = int(newer[10])
seqOlder = int(older[10])
assert seqNewer == seqOlder + 1, (
    f"sequence must increase by exactly one per record, got {seqOlder} -> {seqNewer}"
)

assert int(newer[11]) > 0, f"expected a non-zero epoch-ms timestamp, got {newer[11]!r}"
print("sequence and timestamp OK")

# 리뷰(carried-forward Minor): 이 파일만 unloadPlugin 전에
# cmds.file(new=True, force=True)가 없었다 -- 프로젝트 전역 제약("Maya
# tests must call cmds.file(new=True, force=True) before unloadPlugin")을
# 다른 diag_* 형제들처럼 지킨다.
cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
