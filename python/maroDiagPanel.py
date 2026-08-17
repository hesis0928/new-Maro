"""Maro 진단 패널 — workspaceControl 안의 Maya 네이티브 UI.

패널은 자체 상태를 갖지 않는다. boad의 인메모리 스트림과 book 파일만이
진실이며(설계 스펙 §4.2), 이 모듈은 maroDiagPanelRows/maroDiagPanelDetail이
돌려준 것을 그리기만 한다.

평탄한 배열을 행으로 되돌리는 부분은 UI를 만들지 않는 순수 함수로 분리해
뒀다 -- mayapy 배치 모드에는 UI가 없어 위젯은 만들 수 없지만 이 부분은
자동 검증된다.
"""
import time

import maya.cmds as cmds

# C++ 쪽 계약. 바뀌면 양쪽을 함께 고쳐야 한다 (MaroPanelCommands.h 참고).
ROW_FIELDS = 8
DETAIL_FIELDS = 13

CONTROL_NAME = "maroDiagPanelControl"

_PRESENCE_LABEL = {
    "present": "",
    "notApplicable": "(해당 없음)",
    "notCaptured": "(이 자리에서는 포착되지 않음)",
}


def sliceRows(flat):
    """maroDiagPanelRows의 평탄한 배열을 행 딕셔너리 목록으로 되돌린다."""
    if flat is None:
        return []
    if len(flat) % ROW_FIELDS != 0:
        raise ValueError(
            "row array length {} is not a multiple of {}".format(len(flat), ROW_FIELDS)
        )
    rows = []
    for i in range(len(flat) // ROW_FIELDS):
        f = flat[i * ROW_FIELDS:(i + 1) * ROW_FIELDS]
        rows.append({
            "errorHash": f[0],
            "severity": f[1],
            "summary": f[2],
            "sequence": int(f[3]),
            "firstTimestampMs": int(f[4]),
            "lastTimestampMs": int(f[5]),
            "occurrences": int(f[6]),
            "knownBefore": f[7] == "1",
        })
    return rows


def formatLocalTime(epochMs):
    """epoch 밀리초를 사용자의 로컬 시간대 문자열로 만든다.

    C++ 쪽은 epoch ms만 낸다 -- 형식화를 거기서 하면 로케일과 시간대가
    테스트를 흔들고, 정작 사용자에게 필요한 것은 로컬 시간이다.
    """
    seconds = epochMs / 1000.0
    return time.strftime("%H:%M:%S", time.localtime(seconds))


def _rowLabel(row):
    when = formatLocalTime(row["lastTimestampMs"])
    mark = "*" if row["knownBefore"] else " "
    count = " x{}".format(row["occurrences"]) if row["occurrences"] > 1 else ""
    return "{} {} [{}]{}  {}".format(mark, when, row["severity"], count, row["summary"])


def _contextLine(label, value, state):
    suffix = _PRESENCE_LABEL.get(state, "")
    return "{}: {}{}".format(label, value, suffix)


def _onSelect(listControl, detailControl, rowsHolder):
    """목록에서 고른 자리를 refresh()가 마지막으로 그린 행의 sequence로
    바꿔 상세를 받아 온다.

    -index가 아니라 -sequence로 상세를 조회하는 것만으로는 부족하다 --
    여기서 클릭된 *자리*를 여전히 지금 이 순간의 새 스냅샷에 대고 풀면
    똑같은 문제가 재발한다. rowsHolder는 refresh()가 화면에 실제로 그린
    행 목록을 그대로 들고 있으므로, 그 목록에서 클릭된 자리의 sequence를
    읽어 커맨드에 넘긴다 -- refresh() 이후 새 진단이 들어와도 화면에 보이는
    자리와 sequence의 대응은 다음 refresh() 전까지 바뀌지 않는다.
    """
    selected = cmds.textScrollList(listControl, query=True, selectIndexedItem=True)
    if not selected:
        return
    index = selected[0] - 1  # Maya의 textScrollList는 1부터 센다
    rows = rowsHolder["rows"]
    if index < 0 or index >= len(rows):
        return
    sequence = rows[index]["sequence"]
    detail = cmds.maroDiagPanelDetail(sequence=sequence)
    if len(detail) != DETAIL_FIELDS:
        cmds.scrollField(detailControl, edit=True,
                         text="Maro: unexpected detail field count {}".format(len(detail)))
        return

    lines = [
        detail[8],
        "",
        _contextLine("노드 타입", detail[0], detail[1]),
        _contextLine("어트리뷰트", detail[2], detail[3]),
        _contextLine("커맨드", detail[4], detail[5]),
        _contextLine("축/대상", detail[6], detail[7]),
    ]
    if detail[9]:
        lines += ["", "전에 본 문제 — 과거 분석:", detail[9]]
    if detail[10]:
        lines += ["", "해법:", detail[10]]
    cmds.scrollField(detailControl, edit=True, text="\n".join(lines))


def refresh(listControl, detailControl, severityControl, noteControl, rowsHolder):
    severity = cmds.optionMenu(severityControl, query=True, value=True)
    rows = sliceRows(cmds.maroDiagPanelRows(severity=severity))
    rowsHolder["rows"] = rows
    cmds.textScrollList(listControl, edit=True, removeAll=True)
    for row in rows:
        cmds.textScrollList(listControl, edit=True, append=_rowLabel(row))

    # 숨긴 개수 안내는 실제 행이 아니다 -- textScrollList에 같이 넣으면
    # 선택 가능한 자리가 하나 더 생겨, 사용자가 그 줄을 클릭하는 순간
    # _onSelect가 rowsHolder 범위 밖 자리를 받게 된다(리뷰 Finding). 별도
    # text 컨트롤에 쓴다: 선택할 수 없으니 이 문제 자체가 성립하지 않는다.
    # 필터로 빠진 것과 상한으로 잘린 것은 사용자에게 다른 사건이므로 숫자를
    # 하나로 합치지 않고 계속 따로 보여준다.
    hidden = cmds.maroDiagPanelRows(severity=severity, hidden=True)
    byFilter, byCap = int(hidden[0]), int(hidden[1])
    note = ""
    if byFilter or byCap:
        note = "필터로 {}개 제외, 상한으로 {}개 잘림".format(byFilter, byCap)
    cmds.text(noteControl, edit=True, label=note)


def buildUI():
    """workspaceControl이 -uiScript로 부른다."""
    form = cmds.formLayout()
    severityControl = cmds.optionMenu(label="심각도")
    cmds.menuItem(label="all")
    cmds.menuItem(label="warn")
    cmds.menuItem(label="error")
    listControl = cmds.textScrollList(allowMultiSelection=False)
    noteControl = cmds.text(label="", align="left")
    detailControl = cmds.scrollField(editable=False, wordWrap=True)
    refreshButton = cmds.button(label="새로 고침")

    # refresh()가 화면에 그린 행을 _onSelect()가 다시 볼 수 있게 담아 두는
    # 자리. 클로저로 두 콜백이 공유한다 -- 모듈 전역이면 패널을 두 개 띄웠을
    # 때 서로의 선택을 밟는다.
    rowsHolder = {"rows": []}

    cmds.textScrollList(
        listControl, edit=True,
        selectCommand=lambda *_: _onSelect(listControl, detailControl, rowsHolder))
    cmds.button(
        refreshButton, edit=True,
        command=lambda *_: refresh(listControl, detailControl, severityControl, noteControl, rowsHolder))
    cmds.optionMenu(
        severityControl, edit=True,
        changeCommand=lambda *_: refresh(listControl, detailControl, severityControl, noteControl, rowsHolder))

    cmds.formLayout(
        form, edit=True,
        attachForm=[
            (severityControl, "top", 4), (severityControl, "left", 4),
            (refreshButton, "top", 4), (refreshButton, "right", 4),
            (listControl, "left", 4), (listControl, "right", 4),
            (noteControl, "left", 4), (noteControl, "right", 4),
            (detailControl, "left", 4), (detailControl, "right", 4),
            (detailControl, "bottom", 4),
        ],
        attachControl=[
            (listControl, "top", 4, severityControl),
            (listControl, "bottom", 4, noteControl),
            (noteControl, "bottom", 4, detailControl),
        ],
        attachPosition=[(detailControl, "top", 0, 60)])

    refresh(listControl, detailControl, severityControl, noteControl, rowsHolder)
    return form


def show():
    """maroDiagPanel 커맨드가 부른다."""
    if cmds.workspaceControl(CONTROL_NAME, exists=True):
        cmds.workspaceControl(CONTROL_NAME, edit=True, restore=True)
        return
    cmds.workspaceControl(
        CONTROL_NAME,
        label="Maro 진단",
        retain=False,
        floating=True,
        initialWidth=520,
        initialHeight=420,
        requiredPlugin="maro",
        uiScript="import maroDiagPanel; maroDiagPanel.buildUI()")
