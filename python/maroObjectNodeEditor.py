"""ONE -- 오브젝트 노드 에디터. MaroUI 하단에 임베드되어 지금까지 만들어진
SONE들을 GSON(그루핑된 노드)으로 조망한다 (설계 스펙 2026-08-25-...-v2 §6).
"""
import maya.cmds as cmds

# C++ 쪽 계약. 바뀌면 MaroAxisEditorCommands.cpp의 listAxes()도 함께 고쳐야
# 한다.
AXIS_FIELDS = 10


def sliceAxisRows(flat):
    """maroListAxisNodes()의 평탄한 배열을 축 행 딕셔너리 목록으로
    되돌린다."""
    if flat is None:
        return []
    if len(flat) % AXIS_FIELDS != 0:
        raise ValueError(
            "axis row array length {} is not a multiple of {}".format(
                len(flat), AXIS_FIELDS))
    rows = []
    for i in range(len(flat) // AXIS_FIELDS):
        f = flat[i * AXIS_FIELDS:(i + 1) * AXIS_FIELDS]
        r, g, b = (float(v) for v in f[9].split(","))
        rows.append({
            "axisFullPath": f[0],
            "jointName": f[1],
            "boundTargetPath": f[2],
            "parentAxisPath": f[3],
            "controlMode": int(f[4]),
            "enabled": f[5] == "1",
            "conventionAxis": int(f[6]),
            "capabilityCount": int(f[7]),
            "displayName": f[8],
            "displayColor": (r, g, b),
        })
    return rows


def computeGsonGridLayout(count, columns, cellWidth, cellHeight, gap):
    """count개의 GSON을 생성 순서대로 자동 그리드 배치한다. 각 셀의
    좌상단 (x, y)를 반환. columns개마다 다음 줄로 넘어간다."""
    positions = []
    for i in range(count):
        col = i % columns
        row = i // columns
        x = col * (cellWidth + gap)
        y = row * (cellHeight + gap)
        positions.append((x, y))
    return positions
