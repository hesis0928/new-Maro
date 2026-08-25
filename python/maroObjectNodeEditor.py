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


import maya.OpenMayaUI as omui
import shiboken6
from PySide6 import QtCore, QtGui, QtWidgets

import maroSingleObjectNodeEditor

_JOB_ID = None
_PANEL = None

_GRID_COLUMNS = 4
_CELL_WIDTH = 140.0
_CELL_HEIGHT = 50.0
_GRID_GAP = 12.0


class ObjectNodeEditor(QtWidgets.QWidget):
    """GSON 그리드. setStyleSheet()를 부르지 않는다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selectedAxis = None

    def refresh(self):
        self.update()

    def _rows(self):
        return sliceAxisRows(cmds.maroListAxisNodes())

    def _gsonRects(self):
        rows = self._rows()
        positions = computeGsonGridLayout(
            len(rows), _GRID_COLUMNS, _CELL_WIDTH, _CELL_HEIGHT, _GRID_GAP)
        return list(zip(rows, positions))

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        for row, (x, y) in self._gsonRects():
            rect = QtCore.QRectF(x + 4, y + 4, _CELL_WIDTH - 8, _CELL_HEIGHT - 8)
            r, g, b = row["displayColor"]
            painter.setBrush(QtGui.QColor.fromRgbF(r, g, b))
            painter.drawRoundedRect(rect, 6, 6)
            painter.drawText(rect, QtCore.Qt.AlignCenter,
                             row["displayName"] or row["axisFullPath"])

    def _axisAt(self, pos):
        for row, (x, y) in self._gsonRects():
            rect = QtCore.QRectF(x, y, _CELL_WIDTH, _CELL_HEIGHT)
            if rect.contains(pos):
                return row["axisFullPath"], row["boundTargetPath"]
        return None, None

    def mousePressEvent(self, event):
        pos = event.position() if hasattr(event, "position") else event.localPos()
        axis, target = self._axisAt(pos)
        if axis is None:
            return
        self._selectedAxis = axis
        cmds.select(target if target else axis, replace=True)

    def mouseDoubleClickEvent(self, event):
        pos = event.position() if hasattr(event, "position") else event.localPos()
        axis, _target = self._axisAt(pos)
        if axis is not None:
            maroSingleObjectNodeEditor.openSingleObjectNodeEditor(axis)

    def contextMenuEvent(self, event):
        axis, _target = self._axisAt(event.pos())
        if axis is None:
            return
        menu = QtWidgets.QMenu(self)
        renameAction = menu.addAction("Rename")
        recolorAction = menu.addAction("Recolor")
        deleteAction = menu.addAction("Delete")
        chosen = menu.exec(event.globalPos())
        if chosen is renameAction:
            newName, ok = QtWidgets.QInputDialog.getText(self, "Rename", "Display name:")
            if ok:
                cmds.setAttr(axis + ".displayName", newName, type="string")
                self.refresh()
        elif chosen is recolorAction:
            current = [c for r in self._rows() if r["axisFullPath"] == axis
                      for c in [r["displayColor"]]][0]
            color = QtWidgets.QColorDialog.getColor(
                QtGui.QColor.fromRgbF(*current), self)
            if color.isValid():
                cmds.setAttr(axis + ".displayColor",
                             color.redF(), color.greenF(), color.blueF(), type="double3")
                self.refresh()
        elif chosen is deleteAction:
            cmds.delete(axis)
            self.refresh()


def _onSceneSelectionChanged():
    """씬 선택 -> GSON 하이라이트(설계 스펙 §6). 예외가 새어 나가면 안
    된다 -- SelectionChanged 콜백 경계 규율 (maroRosProxy._onIdle과 같은
    이유)."""
    try:
        if _PANEL is None:
            return
        _PANEL.refresh()
    except Exception:  # noqa: BLE001
        import traceback
        traceback.print_exc()


def buildWidget():
    """maroMainWindow.buildUI()가 editorHost에 임베드할 위젯을 만든다."""
    global _PANEL
    _PANEL = ObjectNodeEditor()
    return _PANEL


def start():
    global _JOB_ID
    if _JOB_ID is not None and cmds.scriptJob(exists=_JOB_ID):
        return
    jobId = cmds.scriptJob(event=["SelectionChanged", _onSceneSelectionChanged],
                            protected=True)
    if isinstance(jobId, int):
        _JOB_ID = jobId
    else:
        _JOB_ID = None
        if not cmds.about(batch=True):
            print("maroObjectNodeEditor: scriptJob() did not return a job id "
                  "({!r}) -- selection sync will not run.".format(jobId))


def stop():
    global _JOB_ID, _PANEL
    killSucceededOrJobGone = True
    try:
        if _JOB_ID is not None and cmds.scriptJob(exists=_JOB_ID):
            cmds.scriptJob(kill=_JOB_ID, force=True)
    except Exception:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        killSucceededOrJobGone = False

    if killSucceededOrJobGone:
        _JOB_ID = None
        _PANEL = None
