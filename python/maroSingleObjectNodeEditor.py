"""SONE -- 싱글 오브젝트 노드 에디터. 축 하나의 capability 스택을 방사형
마킹 메뉴로 편집하는 독립 팝업이다 (설계 스펙 2026-08-25-...-v2 §5).

이 파일의 순수 함수는 Maya에 의존하지 않는다 -- mayapy 배치 모드에서
QWidget 없이 계약을 검증한다 (maroDiagPanel.py의 sliceRows와 같은 이유).
"""
import math

import maya.cmds as cmds
from PySide6 import QtCore, QtGui, QtWidgets

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


CAPABILITY_TYPES = [
    ("rotation", "Rotation"),
    ("translation", "Translation"),
    ("limit", "Limit"),
    ("translationLimit", "TranslationLimit"),
    ("sensorDirection", "SensorDirection"),
    ("sensorRange", "SensorRange"),
    ("coupling", "Coupling"),
]

_ITEM_HALF_WIDTH = 55.0
_ITEM_HALF_HEIGHT = 16.0
_MENU_RADIUS = 90.0
_DRAG_THRESHOLD_PX = 6.0

_OPEN_EDITORS = {}  # axisFullPath -> MaroSingleObjectNodeEditor


def openSingleObjectNodeEditor(axis):
    """axis의 SONE를 연다. 이미 열려 있으면 그 창을 앞으로 가져온다.
    (설계 스펙 §2: "SONE는 축마다 유일하게 존재")"""
    existing = _OPEN_EDITORS.get(axis)
    if existing is not None:
        try:
            existing.raise_()
            existing.activateWindow()
            return existing
        except RuntimeError:
            # Qt 쪽 객체가 이미 파괴됨(사용자가 닫음) -- 새로 만든다.
            del _OPEN_EDITORS[axis]

    editor = MaroSingleObjectNodeEditor(axis)
    _OPEN_EDITORS[axis] = editor
    editor.show()
    return editor


class MaroSingleObjectNodeEditor(QtWidgets.QWidget):
    """축 하나의 capability 스택을 방사형 마킹 메뉴로 편집하는 독립
    팝업(모덜리스). setStyleSheet()를 부르지 않는다 -- maroMainWindow.py와
    같은 규율.
    """

    def __init__(self, axis, parent=None):
        super().__init__(parent, QtCore.Qt.Window)
        self._axis = axis
        self._menuStack = []          # [(centerX, centerY, [(label, payload), ...]), ...]
        self._expanded = False        # 능력 2개 이상일 때 드롭다운 펼침 여부
        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)
        # QWidget의 기본 focusPolicy는 Qt.NoFocus다 -- 계획 초안에는 이
        # 줄이 없어서, 이 창을 띄운 채 Delete를 눌러도 keyPressEvent가
        # 아예 호출되지 않는다(포커스가 없는 위젯에는 Qt가 키 이벤트를
        # 배달하지 않는다). Delete로 최근 추가 capability를 지우는 것이
        # 이 태스크의 핵심 요구사항이라 여기서 명시적으로 켠다.
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self._refreshTitle()

    def closeEvent(self, event):
        if _OPEN_EDITORS.get(self._axis) is self:
            del _OPEN_EDITORS[self._axis]
        super().closeEvent(event)

    def _refreshTitle(self):
        rows = cmds.maroListAxisNodes()
        displayName = self._axis
        for i in range(len(rows) // 10):
            f = rows[i * 10:(i + 1) * 10]
            if f[0] == self._axis and f[8]:
                displayName = f[8]
                break
        self.setWindowTitle(displayName)

    def _capabilityRows(self):
        if not cmds.objExists(self._axis):
            return []
        return sliceCapabilityRows(cmds.maroListAxisNodes(capabilities=self._axis))

    def _nodeLabel(self, rows):
        connected = [r for r in rows if r["connected"]]
        if not connected:
            return "undefined", False
        if len(connected) == 1:
            return connected[0]["capabilityNodeType"].replace("maro", ""), False
        return connected[-1]["capabilityNodeType"].replace("maro", "") + " ▾", True

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        rows = self._capabilityRows()
        label, hasDropdown = self._nodeLabel(rows)
        cx, cy = self.width() / 2.0, self.height() / 2.0
        nodeRect = QtCore.QRectF(cx - 60, cy - 18, 120, 36)
        pen = QtGui.QPen(QtCore.Qt.DashLine if label == "undefined" else QtCore.Qt.SolidLine)
        painter.setPen(pen)
        painter.drawRoundedRect(nodeRect, 6, 6)
        painter.drawText(nodeRect, QtCore.Qt.AlignCenter, label)

        if self._expanded and len(rows) > 0:
            connected = sorted([r for r in rows if r["connected"]], key=lambda r: r["logicalIndex"])
            y = nodeRect.bottom() + 8
            for row in connected:
                itemRect = QtCore.QRectF(cx - 70, y, 140, 22)
                painter.drawRect(itemRect)
                painter.drawText(itemRect, QtCore.Qt.AlignCenter,
                                 "{}. {}".format(row["logicalIndex"], row["capabilityNodeType"]))
                y += 24

        for level, (mcx, mcy, items) in enumerate(self._menuStack):
            opacity = 0.35 if level < len(self._menuStack) - 1 else 1.0
            painter.setOpacity(opacity)
            positions = computeRadialLayout(mcx, mcy, len(items), _MENU_RADIUS)
            for (labelText, _payload), (ix, iy) in zip(items, positions):
                itemRect = QtCore.QRectF(ix - _ITEM_HALF_WIDTH, iy - _ITEM_HALF_HEIGHT,
                                         _ITEM_HALF_WIDTH * 2, _ITEM_HALF_HEIGHT * 2)
                painter.drawRoundedRect(itemRect, 6, 6)
                painter.drawText(itemRect, QtCore.Qt.AlignCenter, labelText)
            painter.setOpacity(1.0)
            if level > 0:
                backRect = QtCore.QRectF(self.width() - 90, mcy - 12, 80, 24)
                painter.drawRoundedRect(backRect, 4, 4)
                painter.drawText(backRect, QtCore.Qt.AlignCenter, "◀ 상위로")

    def _leafItems(self):
        return [(label, ("leaf", flagName)) for flagName, label in CAPABILITY_TYPES]

    # event.position()만 쓴다 -- 계획 초안은 hasattr(event, "position")로
    # 구버전 Qt6의 event.localPos()까지 가드했지만, 이 플러그인이 실제로
    # 묶이는 Maya 2026의 mayapy로 실측한 결과(PySide6 6.5.3) QMouseEvent는
    # 두 메서드를 다 갖고 있어 hasattr 분기가 항상 True로 떨어진다 --
    # localPos() 쪽은 이 설치본에서 절대 실행되지 않는 죽은 코드이고, 굳이
    # 부르면 DeprecationWarning만 낸다(Qt6에서 QPointF 기반 position()으로
    # 대체됨). README가 명시하는 지원 대상이 Maya 2026 devkit 하나뿐이므로
    # 가드를 남겨 둘 이유가 없다.
    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.RightButton:
            return
        self._pressPos = event.position()
        self._menuStack = [(self._pressPos.x(), self._pressPos.y(), self._leafItems())]
        self.update()

    def mouseMoveEvent(self, event):
        if not self._menuStack:
            return
        pos = event.position()
        moved = math.hypot(pos.x() - self._pressPos.x(), pos.y() - self._pressPos.y())
        if moved < _DRAG_THRESHOLD_PX:
            return
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != QtCore.Qt.RightButton or not self._menuStack:
            return
        pos = event.position()
        moved = math.hypot(pos.x() - self._pressPos.x(), pos.y() - self._pressPos.y())
        if moved < _DRAG_THRESHOLD_PX:
            self._menuStack = []
            self.update()
            return

        mcx, mcy, items = self._menuStack[-1]
        positions = computeRadialLayout(mcx, mcy, len(items), _MENU_RADIUS)
        index = hitTestRadialItem(pos.x(), pos.y(), positions, _ITEM_HALF_WIDTH, _ITEM_HALF_HEIGHT)
        self._menuStack = []
        if index is not None:
            _label, (kind, flagName) = items[index]
            if kind == "leaf":
                self._applyCapability(flagName)
        self.update()

    def _applyCapability(self, flagName):
        try:
            newNode = cmds.maroAddCapability(self._axis, type=flagName)[0]
        except RuntimeError as error:
            print("Maro: maroAddCapability failed -- {}".format(error))
            return
        if flagName == "coupling":
            self._showCouplingSourcePicker(newNode)
        self.update()

    def _showCouplingSourcePicker(self, couplingNodeName):
        """Coupling capability는 다른 축의 출력값을 소스로 물려야 동작한다
        (ratio * source + offset). 방금 추가한 coupling 노드 이름을 받아
        다른 축들의 목록을 보여주고 고른 축의 position(Linear)을
        sourceValue(Linear)에 연결한다."""
        picker = QtWidgets.QWidget(self, QtCore.Qt.Popup)
        layout = QtWidgets.QVBoxLayout(picker)
        combo = QtWidgets.QComboBox()
        rows = cmds.maroListAxisNodes()
        for i in range(len(rows) // 10):
            f = rows[i * 10:(i + 1) * 10]
            if f[0] == self._axis:
                continue  # 자기 자신은 소스로 고를 수 없다
            combo.addItem(f[8] if f[8] else f[0], f[0])
        layout.addWidget(combo)
        applyButton = QtWidgets.QPushButton("Connect")
        layout.addWidget(applyButton)

        def _onApply():
            sourceAxis = combo.currentData()
            if not sourceAxis:
                picker.close()
                return
            isLinear = cmds.getAttr(sourceAxis + ".driveIsLinear")
            cmds.undoInfo(openChunk=True)
            try:
                cmds.setAttr(couplingNodeName + ".sourceIsLinear", isLinear)
                if isLinear:
                    cmds.connectAttr(sourceAxis + ".positionLinear",
                                     couplingNodeName + ".sourceValueLinear", force=True)
                else:
                    cmds.connectAttr(sourceAxis + ".position",
                                     couplingNodeName + ".sourceValue", force=True)
            finally:
                cmds.undoInfo(closeChunk=True)
            picker.close()
            self.update()

        applyButton.clicked.connect(_onApply)
        picker.move(self.mapToGlobal(QtCore.QPoint(int(self.width() / 2), int(self.height() / 2))))
        picker.show()

    def mouseDoubleClickEvent(self, event):
        rows = self._capabilityRows()
        connected = [r for r in rows if r["connected"]]
        if len(connected) >= 2:
            self._expanded = not self._expanded
            self.update()

    def keyPressEvent(self, event):
        if event.key() != QtCore.Qt.Key_Delete:
            return
        rows = self._capabilityRows()
        target = indexOfCapabilityToPeel(rows)
        if target is None:
            return
        try:
            cmds.maroDisconnectCapability(self._axis, index=target)
        except RuntimeError as error:
            print("Maro: maroDisconnectCapability failed -- {}".format(error))
            return
        self.update()
