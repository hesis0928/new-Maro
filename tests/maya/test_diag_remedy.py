"""해법 등록: 사용자가 스스로 해결한 방법을 등록하면 같은 에러 재발 시
제시되는지 확인한다. 또한, 아직 한 번도 에러가 난 적 없는 해시에 먼저 해법만
등록해도(분석 없는 항목) 그 자리에서 실제로 에러가 났을 때 원래 에러 메시지가
지워지지 않고 해법만 붙어 나오는지 확인한다 (해법-only book 항목 경로)."""
import os
import sys
import tempfile

import maya.standalone

os.environ["MARO_DIAG_BOOK_DIR"] = tempfile.mkdtemp(prefix="maro_diag_remedy_")

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

light = cmds.createNode("pointLight", name="remedyLight")
axis = cmds.createNode("maroAxis", name="remedyAxis")

countBeforeFirst = cmds.maroDiagCount()
try:
    cmds.maroBindAxis(axis, light)
    raise AssertionError("expected rejection")
except RuntimeError:
    pass

# 이 book은 실제로 쓸 수 있는 임시 디렉터리를 가리킨다 (맨 위에서
# MARO_DIAG_BOOK_DIR을 tempdir로 설정). 건강한(쓰기 가능한) book에서
# 최초 발생(캐시 미스)이 조용히 book-불가 경고까지 함께 내보내면 안 된다
# -- 그런 버그는 "쓰기 실패 여부"가 아니라 "캐시 미스였는지"로 경고를
# 잘못 판단하는, 겉보기엔 그럴듯한 구현에서 나올 수 있다. 그 버그는
# maroDiagQuery(index=0)만 보면 안 잡힌다(경고가 있어도 없어도 index=0은
# 여전히 방금 밀어넣은 error 레코드이므로) -- 그래서 레코드 총수 증가분을
# 직접 세어야 한다.
countAfterFirst = cmds.maroDiagCount()
assert countAfterFirst == countBeforeFirst + 1, (
    f"a healthy, writable book must not emit a book-unwritable warning -- "
    f"expected exactly 1 new record (the error itself) from the first "
    f"(fresh-analysis) rejection, got {countAfterFirst - countBeforeFirst}"
)
print("no spurious book-unwritable warning on a healthy book OK")

firstRecord = cmds.maroDiagQuery(index=0)
errorHash = firstRecord[2]
assert errorHash, "expected a non-empty error hash"
assert firstRecord[7] == "", "no remedy should exist yet"
print("no remedy before registration OK")

cmds.maroDiagRegisterRemedy(hash=errorHash, remedy="Select the transform, not its shape.")
print("remedy registered OK")

try:
    cmds.maroBindAxis(axis, light)
    raise AssertionError("expected rejection")
except RuntimeError:
    pass

secondRecord = cmds.maroDiagQuery(index=0)
assert secondRecord[7] == "Select the transform, not its shape.", (
    f"expected the registered remedy on recurrence, got {secondRecord[7]!r}"
)
assert secondRecord[8] == "1", "recurrence with a registered remedy is served from book"
print("remedy offered on recurrence OK")

# --- 해법-only book 항목: 한 번도 에러가 난 적 없는 해시에 먼저 해법만
# 등록한 뒤, 그 자리에서 실제로 에러가 나면 원래 메시지가 지워지지 않아야
# 한다. error()가 book 히트를 처리할 때 entry.analysis가 비어 있으면
# 무조건 message를 빈 문자열 뒤에 붙은 "(Maro: book에 있는 과거 분석에서
# 즉답)" 표기로 덮어써 버리는 회귀를 여기서 잡는다.
#
# 사이트 태그의 해시는 C++(src/maro_diag/src/ErrorHash.cpp)와 완전히
# 동일한 FNV-1a-64를 파이썬으로 재구현해 직접 계산한다 -- 그래야 이
# 단언이 파이썬/C++ 두 구현이 실제로 합의하는지까지 함께 검증한다.
def fnv1a64(site_tag: str) -> str:
    h = 0xcbf29ce484222325
    prime = 0x100000001b3
    mask = (1 << 64) - 1
    for byte in site_tag.encode("utf-8"):
        h ^= byte
        h = (h * prime) & mask
    return format(h, "016x")


remedyOnlySiteTag = "Test.RemedyOnly"
remedyOnlyHash = fnv1a64(remedyOnlySiteTag)
remedyOnlyRemedy = "Reconnect the ROS topic before retrying."

cmds.maroDiagRegisterRemedy(hash=remedyOnlyHash, remedy=remedyOnlyRemedy)
print("remedy-only registration (no prior analysis) OK")

cmds.maroDiagEmit(severity="error", message="probe message", siteTag=remedyOnlySiteTag)
remedyOnlyRecord = cmds.maroDiagQuery(index=0)
(severity, message, errorHash2, nodeType, attributeName, activeCommand,
 axisOrTarget, remedy, servedFromBook, priorAnalysis) = remedyOnlyRecord

assert errorHash2 == remedyOnlyHash, (
    f"C++ hashError() and the python FNV-1a-64 reimplementation disagree: "
    f"expected {remedyOnlyHash!r}, got {errorHash2!r}"
)
assert "probe message" in message, (
    f"a remedy-only book entry (empty analysis) must not erase the real error "
    f"message, got {message!r}"
)
assert remedy == remedyOnlyRemedy, f"expected the registered remedy, got {remedy!r}"
assert servedFromBook == "1", (
    "a remedy-only book entry is still a book hit -- servedFromBook must stay true"
)
# 리뷰 Finding C1: 이 항목은 registerRemedy()가 해법만 등록해 만든 것이라
# entry.analysis는 애초에 비어 있다 -- priorAnalysis도 그대로 빈 문자열이어야
# 한다("과거 분석 없음"을 정직하게 반영). message는 message대로 지금 이
# 호출이 넘긴 "probe message"를 그대로 담아야 한다 (위에서 이미 확인).
assert priorAnalysis == "", (
    f"a remedy-only entry has no recorded analysis, so priorAnalysis must "
    f"stay empty, got {priorAnalysis!r}"
)
print("remedy-only entry preserved the error message OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
