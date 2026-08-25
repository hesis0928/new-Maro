"""SONE -- 싱글 오브젝트 노드 에디터. 축 하나의 capability 스택을 방사형
마킹 메뉴로 편집하는 독립 팝업이다 (설계 스펙 2026-08-25-...-v2 §5).

이 파일의 순수 함수는 Maya에 의존하지 않는다 -- mayapy 배치 모드에서
QWidget 없이 계약을 검증한다 (maroDiagPanel.py의 sliceRows와 같은 이유).
"""
import math

# C++ 쪽 계약. 바뀌면 MaroAxisEditorCommands.cpp의 listCapabilities()도
# 함께 고쳐야 한다.
CAPABILITY_FIELDS = 5


def sliceCapabilityRows(flat):
    """maroListAxisNodes(capabilities=axis)의 평탄한 배열을 capability 행
    딕셔너리 목록으로 되돌린다."""
    if flat is None:
        return []
    if len(flat) % CAPABILITY_FIELDS != 0:
        raise ValueError(
            "capability row array length {} is not a multiple of {}".format(
                len(flat), CAPABILITY_FIELDS))
    rows = []
    for i in range(len(flat) // CAPABILITY_FIELDS):
        f = flat[i * CAPABILITY_FIELDS:(i + 1) * CAPABILITY_FIELDS]
        rows.append({
            "logicalIndex": int(f[0]),
            "capabilityNodeName": f[1],
            "capabilityNodeType": f[2],
            "capType": int(f[3]),
            "connected": f[4] == "1",
        })
    return rows


def computeRadialLayout(centerX, centerY, itemCount, radius):
    """중심(centerX, centerY) 주위로 itemCount개 항목을 원형으로 배치한다.
    첫 항목은 정확히 위쪽(각도 -90도)에서 시작해 시계 방향으로 균등
    분배된다."""
    if itemCount <= 0:
        return []
    positions = []
    step = 2.0 * math.pi / itemCount
    for i in range(itemCount):
        angle = -math.pi / 2.0 + i * step
        x = centerX + radius * math.cos(angle)
        y = centerY + radius * math.sin(angle)
        positions.append((x, y))
    return positions


def hitTestRadialItem(cursorX, cursorY, itemPositions, itemHalfWidth, itemHalfHeight):
    """커서가 어느 항목의 축정렬 박스 안에 있는지. 여러 박스가 겹치면
    먼저 등장한(=itemPositions의 앞) 항목이 이긴다. 없으면 None."""
    for index, (x, y) in enumerate(itemPositions):
        if (abs(cursorX - x) <= itemHalfWidth and
                abs(cursorY - y) <= itemHalfHeight):
            return index
    return None


def indexOfCapabilityToPeel(capabilityRows):
    """Delete(접힌 상태)가 지울 항목의 logicalIndex -- 연결된 행 중
    가장 큰 logicalIndex. 연결된 행이 없으면 None(더 지울 것이 없음,
    이미 undefined)."""
    connectedIndices = [row["logicalIndex"] for row in capabilityRows if row["connected"]]
    if not connectedIndices:
        return None
    return max(connectedIndices)
