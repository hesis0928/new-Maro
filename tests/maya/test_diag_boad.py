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

# Finding 3 (Minor): "> 0"만으로는 하드코딩된 상수도 통과한다. 이미 손에 든
# 두 연속 레코드로, 더 최근 레코드의 시각이 이전 레코드보다 뒤로 가지 않는지
# 확인한다. 주의: 이 역시 상수 시계(예: nowMs()가 항상 같은 고정값을 돌려줌)를
# 잡아내지 못한다 -- ">=" 비교이므로 두 값이 같아도 통과한다. 실제 벽시계가
# 흐르는지까지 확인하려면 더 강한 신호(예: 실제 경과 시간과의 비교)가 필요하다.
assert int(newer[11]) >= int(older[11]), (
    f"newer record's timestamp must not be older than the previous record's, "
    f"got older={older[11]!r} newer={newer[11]!r}"
)
print("sequence and timestamp OK")

# Finding 1 (Important): 스트림의 위치 순서가 순번 순서와 일치한다는 계약을
# 값으로 고정한다. recordAt(0)이 "가장 최근"을 뜻한다는 계약과, 패널이
# 스트림을 위치 순서대로 훑으며 그것이 곧 순번 순서라고 가정하는 것 둘 다
# "삽입 위치 순서 == 순번 순서"에 기댄다. 순번 배정과 스트림 삽입을 같은 락
# 스코프 안에서 하도록 고친 것이 이 불변식을 구조적으로 보장한다.
#
# 주의: 이 어서션은 경합을 강제로 재현하지 못한다 -- 이 테스트는 단일
# 스레드에서 순차적으로 호출하므로, 순번 배정과 스트림 삽입 사이에 다른
# 스레드가 끼어들 여지가 애초에 없다. 이 어서션이 확인하는 것은 "수정이 만든
# 구조적 불변식이 여전히 성립한다"는 것이지, "경합이 더 이상 일어나지
# 않는다"는 것이 아니다.
for i in range(5):
    cmds.maroDiagEmit(severity="info", message=f"order probe {i}")

orderProbeCount = cmds.maroDiagCount()
prevSeq = None
for i in range(min(orderProbeCount, 7)):
    rec = cmds.maroDiagQuery(index=i)
    seq = int(rec[10])
    if prevSeq is not None:
        assert seq < prevSeq, (
            "stream position order must match strictly decreasing sequence "
            f"order walking from index 0 upward; index {i - 1} had sequence "
            f"{prevSeq}, index {i} had sequence {seq}"
        )
    prevSeq = seq
print("stream position order matches sequence order OK")

# 리뷰(carried-forward Minor): 이 파일만 unloadPlugin 전에
# cmds.file(new=True, force=True)가 없었다 -- 프로젝트 전역 제약("Maya
# tests must call cmds.file(new=True, force=True) before unloadPlugin")을
# 다른 diag_* 형제들처럼 지킨다.
cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
