"""패널 읽기 커맨드의 계약: 행당 필드 개수가 고정이고, 접기가 실제로
일어나며, 상세가 선택한 행을 가리키는지 값으로 확인한다."""
import os
import sys
import tempfile

import maya.standalone

os.environ["MARO_DIAG_BOOK_DIR"] = tempfile.mkdtemp(prefix="maro_panel_cmd_")

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

ROW_FIELDS = 8
DETAIL_FIELDS = 14

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

# 같은 자리를 세 번, 다른 자리를 한 번 때린다.
light = cmds.createNode("pointLight", name="panelLight")
axis = cmds.createNode("maroAxis", name="panelAxis")
for _ in range(3):
    try:
        cmds.maroBindAxis(axis, light)
        raise AssertionError("expected rejection")
    except RuntimeError:
        pass

try:
    cmds.maroConnectAxis(axis, axis)  # SelfParent -- 다른 사이트 태그
    raise AssertionError("expected rejection")
except RuntimeError:
    pass

flat = cmds.maroDiagPanelRows(severity="error")
assert len(flat) % ROW_FIELDS == 0, (
    f"row array must be a multiple of {ROW_FIELDS}, got {len(flat)}"
)
rowCount = len(flat) // ROW_FIELDS
assert rowCount == 2, f"three hits on one site plus one on another must collapse to 2 rows, got {rowCount}"
print("row collapsing OK")

rows = [flat[i * ROW_FIELDS:(i + 1) * ROW_FIELDS] for i in range(rowCount)]
# 필드 순서: errorHash, severity, summary, sequence, firstMs, lastMs, occurrences, knownBefore
occurrences = sorted(int(r[6]) for r in rows)
assert occurrences == [1, 3], f"expected occurrence counts [1, 3], got {occurrences}"

for r in rows:
    assert r[1] == "error", f"severity filter asked for errors only, got {r[1]!r}"
    assert int(r[4]) > 0, "first timestamp must be a real epoch value"
    assert int(r[5]) >= int(r[4]), "last occurrence cannot precede the first"
print("row fields OK")

# buildPanelRows가 내놓는 행 순서 계약을 고정한다: 순번 내림차순, 값 중복 없음.
#
# 이 단언이 무엇을 못 잡는지 분명히 해 둔다 -- 스냅샷이 레코드를 건너뛰거나
# 두 번 읽는 결함은 이걸로 안 잡힌다. buildPanelRows는 errorHash로 접은 뒤
# 순번 내림차순으로 명시적으로 정렬하고, 순번은 세션 전역에서 유일하므로,
# 입력 벡터가 잘리든 중복되든 뒤섞이든 행 수준의 이 불변식은 그대로 성립한다.
# 스냅샷의 원자성은 테스트가 아니라 BoadMaro::snapshotRecords()가 락을 한 번만
# 잡는다는 구조로 보장된다(단일 스레드 mayapy는 그 경합을 만들 수 없다).
sequences = [int(r[3]) for r in rows]
assert sequences == sorted(sequences, reverse=True), (
    f"rows must come back in strictly decreasing sequence order, got {sequences}"
)
assert len(set(sequences)) == len(sequences), (
    f"no sequence value may repeat across rows, got {sequences}"
)
print("row sequence order OK")

# -hidden 경로도 값으로 확인한다. 지금까지 기록된 것은 정보 레코드
# ("plugin loaded") 하나 + 에러 5건(3+1로 접힘)이다: severity=error
# 필터는 그 정보 레코드 딱 하나만 제외하고, 행은 둘뿐이라 기본 상한(500)
# 아래라서 상한으로 잘린 것은 없다. 두 카운트가 서로 다르므로(1 vs 0)
# 필드 순서를 실수로 바꿔도(예: hiddenByCap을 먼저 반환) 여기서 반드시
# 걸린다 -- 이 경로는 그 외 어디에서도 exercised되지 않는다.
hidden = cmds.maroDiagPanelRows(severity="error", hidden=True)
assert len(hidden) == 2, f"expected 2 fields from -hidden, got {len(hidden)}"
assert hidden[0] == "1", (
    f"hiddenByFilter should be 1 (just the plugin-load info record), got {hidden[0]!r}"
)
assert hidden[1] == "0", (
    f"hiddenByCap should be 0 (2 rows is well under the 500 default cap), got {hidden[1]!r}"
)
print("hidden counts OK")

# 상세는 이제 화면 자리(index)가 아니라 순번(sequence)으로 고른다 --
# 위치는 클릭 시점에 새로 스냅샷을 뜬 행 목록이 바뀌면 함께 흔들리지만,
# 순번은 세션 전역에서 유일하고 재사용되지 않으므로 흔들리지 않는다
# (MaroPanelCommands.h/.cpp 리뷰 Finding). rows[i][3]이 그 행의 sequence다.
def _detailFor(rowIndex):
    return cmds.maroDiagPanelDetail(sequence=int(rows[rowIndex][3]))


def _latestSequence(severity="error"):
    """방금 만든 레코드가 최신(=가장 큰 sequence)이라고 가정하고 다시
    조회한 행 목록의 맨 앞(rows[0])에서 그 순번을 읽어 온다."""
    flatNow = cmds.maroDiagPanelRows(severity=severity)
    assert len(flatNow) >= ROW_FIELDS, "expected at least one row to fetch a sequence from"
    return int(flatNow[3])


# 상세는 선택한 행을 가리킨다.
detail = _detailFor(0)
assert len(detail) == DETAIL_FIELDS, (
    f"expected {DETAIL_FIELDS} detail fields, got {len(detail)}"
)
# 필드 순서: nodeType, nodeTypeState, attributeName, attributeNameState,
#            activeCommand, activeCommandState, axisOrTarget, axisOrTargetState,
#            message, priorAnalysis, remedyText, applyAvailable, applyUnavailableReason,
#            crashAdjacencyNote
assert detail[11] == "0", "B-1a records no structured actions, so apply is never available"
assert detail[12] == "NoActionRecorded", f"unexpected reason {detail[12]!r}"
assert detail[8], "detail must carry the message of the represented record"
print("detail contract OK")

# 이 세션은 저널에 비정상 종료 기록이 없으므로 신호 자리는 비어 있어야 한다.
# 문턱 아래에서 뭔가 말하는 것은 정보가 아니라 소음이다.
assert detail[13] == "", (
    f"no abnormal sessions on record, so the crash-adjacency note must be empty, "
    f"got {detail[13]!r}"
)
print("crash adjacency note empty OK")

# --- 프레즌스 문자열 매핑을 그 자체로 고정한다 -----------------------------
# 위 단언들은 detail[8]/[11]/[12]만 확인했다 -- 상태 필드(1,3,5,7) 자체는
# 아직 한 번도 값으로 확인되지 않았다. presenceName()이 무엇을 돌려주든
# (예: 전부 "present"로 하드코딩) 그 단언들만으로는 절대 걸리지 않는다.
#
# rows[0]의 순번으로 조회한 위 detail은 실제로는 maroConnectAxis(axis, axis)의
# WrongArgCount다 -- 위쪽 주석의 의도("SelfParent")와 다르다: MSelectionList
# 가 같은 노드 이름 두 번을 하나로 접어 selection.length() != 2가 되기
# 때문이다(그래도 여전히 bind 거부와는 다른 사이트 태그의 에러 하나이므로
# 2행/occurrences [1,3]은 그대로 성립한다 -- 이 파일 위쪽의 단언은 전부
# 그대로 유효하다). WrongArgCount는 onfix::capture("", "", "")로 기본
# 컨텍스트를 태우므로 nodeType/attributeName/axisOrTarget은 "이 자리에
# 관여한 것이 애초에 없었다" -- notApplicable이어야 하고, activeCommand만
# 살아있는 커맨드 스택에서 채워져 present여야 한다.
assert detail[1] == "notApplicable", f"nodeTypeState should be 'notApplicable', got {detail[1]!r}"
assert detail[3] == "notApplicable", f"attributeNameState should be 'notApplicable', got {detail[3]!r}"
assert detail[5] == "present", f"activeCommandState should be 'present', got {detail[5]!r}"
assert detail[7] == "notApplicable", f"axisOrTargetState should be 'notApplicable', got {detail[7]!r}"
print("presence 'notApplicable' mapping OK")

# rows[1]은 3번 반복된 bind 거부(TargetNotTransform)다: 살아있는 노드 조회를
# 실제로 거쳤으므로 네 필드 모두 값이 채워져 있고 전부 present여야 한다.
presentDetail = _detailFor(1)
assert presentDetail[0] == "pointLight", (
    f"nodeType value should survive, got {presentDetail[0]!r}"
)
assert presentDetail[1] == "present", f"nodeTypeState should be 'present', got {presentDetail[1]!r}"
assert presentDetail[3] == "present", (
    f"attributeNameState should be 'present', got {presentDetail[3]!r}"
)
assert presentDetail[5] == "present", (
    f"activeCommandState should be 'present', got {presentDetail[5]!r}"
)
assert presentDetail[7] == "present", (
    f"axisOrTargetState should be 'present', got {presentDetail[7]!r}"
)
print("presence 'present' mapping OK")

# 존재한 적 없는 순번은 엉뚱한 이웃을 조용히 돌려주지 않고 실패로 끝난다
# -- 이것이 바로 -index를 -sequence로 바꾼 이유(스테일 선택을 잡아내는
# 것)이므로, 예전의 "범위 밖 인덱스" 테스트보다 이쪽이 더 강하게 계약을
# 고정한다. 지금까지 발급된 순번은 전부 이 값보다 한참 작으므로 절대
# 실제로 존재할 수 없다.
try:
    cmds.maroDiagPanelDetail(sequence=999999999)
    raise AssertionError("unknown sequence should have failed")
except RuntimeError:
    pass
print("unknown sequence rejected OK")

# --- "관여했으나 못 채움"(notCaptured) -- 이 태스크가 처음 관측 가능하게 만드는 것
# nameUnavailable/typeUnavailable은 실제로는 워커 스레드의 compute() 실패나
# 손상된 노드의 삭제 콜백(MaroDeleteWatcher.cpp)에서만 서는데, 그 경로는
# mayapy 테스트가 결정적으로 유발할 수 없다. maroDiagEmit의
# -nameUnavailable/-typeUnavailable 확장(테스트 전용, MaroDiagCommands.h
# 참고)으로 그 상태를 직접 재현해, 패널이 이걸 "관여 없음"과 혼동하지 않고
# notCaptured로 정확히 구분해 내놓는지 값으로 확인한다. 이 두 단언이 이
# 태스크가 존재하는 이유(둘째 가용성 플래그가 처음으로 관측 가능해지는
# 지점)를 직접 붙잡는다.
cmds.maroDiagEmit(severity="error", siteTag="Test.PanelPresenceNameUnavailable",
                  message="name unavailable probe", nodeType="probeNodeType",
                  nameUnavailable=True)
nameUnavailableDetail = cmds.maroDiagPanelDetail(sequence=_latestSequence())
assert nameUnavailableDetail[0] == "probeNodeType", (
    f"nodeType value should survive, got {nameUnavailableDetail[0]!r}"
)
assert nameUnavailableDetail[1] == "present", (
    f"nodeTypeState should be 'present' (type was obtained), got {nameUnavailableDetail[1]!r}"
)
assert nameUnavailableDetail[6] == "", (
    f"axisOrTarget value should be empty (name lookup failed), got {nameUnavailableDetail[6]!r}"
)
assert nameUnavailableDetail[7] == "notCaptured", (
    f"axisOrTargetState must be 'notCaptured' -- the name was wanted but not "
    f"obtained, not 'nothing was involved'; got {nameUnavailableDetail[7]!r}"
)
print("presence 'notCaptured' mapping OK (name)")

cmds.maroDiagEmit(severity="error", siteTag="Test.PanelPresenceTypeUnavailable",
                  message="type unavailable probe", axisOrTarget="probeTarget",
                  typeUnavailable=True)
typeUnavailableDetail = cmds.maroDiagPanelDetail(sequence=_latestSequence())
assert typeUnavailableDetail[0] == "", (
    f"nodeType value should be empty (type lookup failed), got {typeUnavailableDetail[0]!r}"
)
assert typeUnavailableDetail[1] == "notCaptured", (
    f"nodeTypeState must be 'notCaptured' -- the type was wanted but not "
    f"obtained; got {typeUnavailableDetail[1]!r}"
)
assert typeUnavailableDetail[6] == "probeTarget", (
    f"axisOrTarget value should survive, got {typeUnavailableDetail[6]!r}"
)
assert typeUnavailableDetail[7] == "present", (
    f"axisOrTargetState should be 'present', got {typeUnavailableDetail[7]!r}"
)
print("presence 'notCaptured' mapping OK (type)")

# 패널 UI 모듈의 순수 함수만 검증한다. 위젯 자체는 배치 모드에 UI가 없어
# 만들 수 없으므로 수동 체크리스트로 남긴다(docs/maro-panel-manual-checklist.md).
pluginDir = os.path.dirname(plugin)
sys.path.insert(0, pluginDir)
import maroDiagPanel  # noqa: E402

# 계약 상수 자체를 값으로 고정한다.
#
# 왜 필요한가: DETAIL_FIELDS는 maroDiagPanel.py 안에서 _onSelect() 하나에만
# 쓰이는데, 그건 UI 콜백이라 mayapy 배치 테스트가 절대 부르지 못한다. 아래의
# flatSample 검증도 sliceRows()를 통해 ROW_FIELDS만 우연히 건드릴 뿐
# DETAIL_FIELDS는 전혀 지나가지 않는다. 실측으로 확인했다: DETAIL_FIELDS를
# 13에서 12로 바꾸고 이 단언 없이 스위트를 돌려 보면 전부 통과한다 -- 계약이
# 어긋나도 아무도 못 잡는다는 뜻이다. 이 두 줄이 그 구멍을 막는다: 값은 이
# 파일 위쪽의 ROW_FIELDS/DETAIL_FIELDS(실제 커맨드 출력을 상대로 이미
# 검증됨)와 MaroPanelCommands.h의 필드 개수 주석에서 가져왔다.
assert maroDiagPanel.ROW_FIELDS == ROW_FIELDS, (
    f"maroDiagPanel.ROW_FIELDS ({maroDiagPanel.ROW_FIELDS}) must match the "
    f"maroDiagPanelRows contract ({ROW_FIELDS} fields/row, MaroPanelCommands.h)"
)
assert maroDiagPanel.DETAIL_FIELDS == DETAIL_FIELDS, (
    f"maroDiagPanel.DETAIL_FIELDS ({maroDiagPanel.DETAIL_FIELDS}) must match "
    f"the maroDiagPanelDetail contract ({DETAIL_FIELDS} fields, MaroPanelCommands.h)"
)
print("field count constants pinned OK")

flatSample = [
    "hashA", "error", "first summary", "7", "1000", "1200", "3", "1",
    "hashB", "warn", "second summary", "5", "900", "900", "1", "0",
]
sliced = maroDiagPanel.sliceRows(flatSample)
assert len(sliced) == 2, f"expected 2 rows from 16 fields, got {len(sliced)}"
assert sliced[0]["errorHash"] == "hashA"
assert sliced[0]["severity"] == "error", f"expected severity 'error', got {sliced[0]['severity']!r}"
assert sliced[0]["summary"] == "first summary", (
    f"expected summary 'first summary', got {sliced[0]['summary']!r}"
)
assert sliced[0]["sequence"] == 7, f"expected sequence 7, got {sliced[0]['sequence']!r}"
assert sliced[0]["firstTimestampMs"] == 1000, (
    f"expected firstTimestampMs 1000, got {sliced[0]['firstTimestampMs']!r}"
)
assert sliced[0]["lastTimestampMs"] == 1200, (
    f"expected lastTimestampMs 1200, got {sliced[0]['lastTimestampMs']!r}"
)
assert sliced[0]["occurrences"] == 3
assert sliced[0]["knownBefore"] is True
assert sliced[1]["errorHash"] == "hashB"
assert sliced[1]["severity"] == "warn", f"expected severity 'warn', got {sliced[1]['severity']!r}"
assert sliced[1]["summary"] == "second summary", (
    f"expected summary 'second summary', got {sliced[1]['summary']!r}"
)
assert sliced[1]["sequence"] == 5, f"expected sequence 5, got {sliced[1]['sequence']!r}"
assert sliced[1]["firstTimestampMs"] == 900, (
    f"expected firstTimestampMs 900, got {sliced[1]['firstTimestampMs']!r}"
)
assert sliced[1]["lastTimestampMs"] == 900, (
    f"expected lastTimestampMs 900, got {sliced[1]['lastTimestampMs']!r}"
)
assert sliced[1]["occurrences"] == 1
assert sliced[1]["knownBefore"] is False
print("sliceRows OK")

# 잘못 잘린 배열은 조용히 잘못된 행을 만들지 않고 거절한다.
try:
    maroDiagPanel.sliceRows(flatSample[:-1])
    raise AssertionError("a ragged array should have been rejected")
except ValueError:
    pass
print("ragged array rejected OK")

# 시각 형식화는 표시하는 쪽이 로컬 시간대로 한다 -- C++는 epoch ms만 낸다.
assert maroDiagPanel.formatLocalTime(0) != "", "formatLocalTime must produce something"
assert ":" in maroDiagPanel.formatLocalTime(1700000000000)
print("formatLocalTime OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
