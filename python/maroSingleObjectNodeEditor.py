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

# C++ 쪽 계약. 바뀌면 MaroAxisEditorCommands.cpp의 listAxes()도 함께 고쳐야
# 한다. maroObjectNodeEditor.py에 같은 값의 AXIS_FIELDS가 하나 더 있고,
# 여기서 그것을 import하지 않는 것은 의도다 -- 그쪽이 이 모듈을 import하므로
# 되받아 import하면 순환 참조가 된다. 두 상수는 같은 C++ 계약을 가리키는
# 독립 선언이고, 계약이 바뀌면 셋(C++/여기/ONE)을 함께 고친다.
AXIS_FIELDS = 10


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
# 펼친 드롭다운에서 "고른 행"을 구분하는 테두리 굵기(px).
_SELECTION_PEN_WIDTH = 2.5


def connectCouplingSource(couplingNodeName, sourceAxis):
    """couplingNodeName(maroCoupling 노드)의 소스를 sourceAxis(다른 축의
    fullPath)로 연결한다. sourceAxis의 driveIsLinear를 읽어 각도/선형 중
    맞는 슬롯(sourceValue 또는 sourceValueLinear)에 연결하고
    sourceIsLinear를 그에 맞춰 설정한다 -- 리뷰 Finding C-1(이 파일 위쪽
    MaroCouplingNode 관련 주석 참고)이 요구하는 단위 안전 연결.

    호출자가 이미 sourceAxis가 couplingNodeName이 붙은 축과 다르다는 것을
    보장해야 한다(자기 자신을 소스로 고르는 것은 호출자 책임으로 막는다).
    """
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


def stop():
    """플러그인 언로드/창 닫힘 시 열려 있는 SONE를 전부 닫는다.

    [최종 리뷰 C-1] SONE는 MaroUI와 무관한 독립 최상위 팝업이라(설계 스펙
    §5) workspaceControl을 닫는 것으로는 함께 닫히지 않는다. 열린 채로
    플러그인이 언로드되면 paintEvent/keyPressEvent가 리페인트/키 입력마다
    이미 deregister된 maroListAxisNodes 등을 계속 불러 스크립트 에디터가
    같은 트레이스백으로 도배된다(그리고 창 자체도 끝까지 남는다).
    maroMainWindow.teardown()이 다른 서브시스템 stop()들과 같은 자리에서
    이것을 부른다 -- 그 시점은 MaroPluginMain.cpp의 uninitializePlugin이
    커맨드를 하나라도 deregister하기 **전**이다.

    maroObjectNodeEditor.stop()과 같은 규율으로 한 창의 실패가 나머지 창의
    정리를 막지 않게 한다(창마다 개별 try).
    """
    for editor in list(_OPEN_EDITORS.values()):
        try:
            editor.close()
            editor.deleteLater()
        except Exception:  # noqa: BLE001 -- 언로드 정리 경계
            import traceback
            traceback.print_exc()
    _OPEN_EDITORS.clear()


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
        # [최종 리뷰 I-1(d)] 펼친 드롭다운에서 클릭으로 고른 행의
        # logicalIndex. None이면 "고른 행 없음"이고, 그때 Delete는 기존대로
        # 가장 나중에 추가된 능력을 벗겨 낸다(설계 스펙 §5.3의 두 동작).
        # 접을 때마다 비운다 -- 안 보이는 행이 선택된 채로 남아 있으면
        # Delete가 화면에 없는 것을 지운다.
        self._selectedCapabilityIndex = None
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
        # 이 핸들러는 stop()(언로드 정리)에서도 불린다 -- 여기서 예외가
        # 새면 나머지 창의 정리까지 함께 끊긴다. 다른 이벤트 핸들러와 같은
        # 규율로 삼킨다.
        try:
            if _OPEN_EDITORS.get(self._axis) is self:
                del _OPEN_EDITORS[self._axis]
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
            import traceback
            traceback.print_exc()
        super().closeEvent(event)

    def _refreshTitle(self):
        rows = cmds.maroListAxisNodes()
        displayName = self._axis
        for i in range(len(rows) // AXIS_FIELDS):
            f = rows[i * AXIS_FIELDS:(i + 1) * AXIS_FIELDS]
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

    def _nodeRect(self):
        cx, cy = self.width() / 2.0, self.height() / 2.0
        return QtCore.QRectF(cx - 60, cy - 18, 120, 36)

    def _expandedRowRects(self, rows):
        """펼친 드롭다운의 각 행에 대한 (logicalIndex, QRectF) 목록.

        paintEvent(그리기)와 mousePressEvent(행 선택 히트테스트)가 **같은**
        기하를 봐야 하므로 한 곳에서만 계산한다 -- 두 곳에 같은 수식을
        복사해 두면 한쪽만 고쳐졌을 때 "보이는 행과 눌리는 행이 다른"
        종류의 버그가 조용히 생긴다.
        """
        if not self._expanded:
            return []
        nodeRect = self._nodeRect()
        cx = self.width() / 2.0
        connected = sorted([r for r in rows if r["connected"]],
                           key=lambda r: r["logicalIndex"])
        rects = []
        y = nodeRect.bottom() + 8
        for row in connected:
            rects.append((row["logicalIndex"], QtCore.QRectF(cx - 70, y, 140, 22)))
            y += 24
        return rects

    def paintEvent(self, event):
        # paintEvent는 리페인트마다 Maya 커맨드를 부른다(_capabilityRows()).
        # 노드가 리페인트 도중에 사라지거나 속성 값이 예상 밖이면 여기서
        # 예외가 나는데, 그걸 밖으로 내보내면 Qt가 다시 그릴 때마다 같은
        # 트레이스백이 무한히 반복된다 -- 이 코드베이스의 Maya 콜백 경계
        # 규율(maroRosProxy._onIdle, maroDagMenu._addMenuItem)을 Qt 이벤트
        # 핸들러에도 그대로 적용한다.
        try:
            painter = QtGui.QPainter(self)
            rows = self._capabilityRows()
            label, hasDropdown = self._nodeLabel(rows)
            nodeRect = self._nodeRect()
            pen = QtGui.QPen(QtCore.Qt.DashLine if label == "undefined" else QtCore.Qt.SolidLine)
            # 굵은 테두리에 쓸 색을 **루프 밖에서** 한 번만 잡는다.
            # painter.pen()을 루프 안에서 읽으면 직전 반복이 세워 둔 굵은 펜의
            # 색을 다시 읽게 되어 상태가 반복마다 흘러간다.
            selectionPen = QtGui.QPen(pen.color(), _SELECTION_PEN_WIDTH)
            painter.setPen(pen)
            painter.drawRoundedRect(nodeRect, 6, 6)
            painter.drawText(nodeRect, QtCore.Qt.AlignCenter, label)

            for logicalIndex, itemRect in self._expandedRowRects(rows):
                if logicalIndex == self._selectedCapabilityIndex:
                    # 고른 행은 굵은 테두리로 구분한다(설계 스펙 §5.3의
                    # "펼친 상태에서 개별 항목 선택"). 색은 지정하지 않는다 --
                    # setStyleSheet를 안 쓰는 것과 같은 이유로 팔레트를
                    # 그대로 쓴다.
                    painter.setPen(selectionPen)
                else:
                    painter.setPen(pen)
                painter.drawRect(itemRect)
                capType = ""
                for row in rows:
                    if row["logicalIndex"] == logicalIndex:
                        capType = row["capabilityNodeType"]
                        break
                painter.drawText(itemRect, QtCore.Qt.AlignCenter,
                                 "{}. {}".format(logicalIndex, capType))
            painter.setPen(pen)

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
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계, 위 주석 참고
            import traceback
            traceback.print_exc()

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
        # Qt 이벤트 핸들러 경계 -- paintEvent의 주석 참고. 여기는 Maya
        # 커맨드(_capabilityRows)도 부르므로 같은 이유가 그대로 적용된다.
        try:
            if event.button() == QtCore.Qt.LeftButton:
                # [최종 리뷰 I-1(d)] 펼친 드롭다운 안을 좌클릭하면 그 행을
                # 고른다(설계 스펙 §5.3). 행 밖을 누르면 선택을 푼다 --
                # 그러면 Delete가 다시 "가장 나중 능력 벗기기"로 돌아간다.
                if self._expanded:
                    pos = event.position()
                    self._selectedCapabilityIndex = None
                    for logicalIndex, itemRect in self._expandedRowRects(
                            self._capabilityRows()):
                        if itemRect.contains(pos):
                            self._selectedCapabilityIndex = logicalIndex
                            break
                    self.update()
                return
            if event.button() != QtCore.Qt.RightButton:
                return
            self._pressPos = event.position()
            self._menuStack = [(self._pressPos.x(), self._pressPos.y(), self._leafItems())]
            self.update()
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
            import traceback
            traceback.print_exc()

    def mouseMoveEvent(self, event):
        try:
            if not self._menuStack:
                return
            pos = event.position()
            moved = math.hypot(pos.x() - self._pressPos.x(), pos.y() - self._pressPos.y())
            if moved < _DRAG_THRESHOLD_PX:
                return
            self.update()
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
            import traceback
            traceback.print_exc()

    def mouseReleaseEvent(self, event):
        try:
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
            index = hitTestRadialItem(pos.x(), pos.y(), positions,
                                      _ITEM_HALF_WIDTH, _ITEM_HALF_HEIGHT)
            self._menuStack = []
            if index is not None:
                _label, (kind, flagName) = items[index]
                if kind == "leaf":
                    self._applyCapability(flagName)
            self.update()
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
            import traceback
            traceback.print_exc()

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
        for i in range(len(rows) // AXIS_FIELDS):
            f = rows[i * AXIS_FIELDS:(i + 1) * AXIS_FIELDS]
            if f[0] == self._axis:
                continue  # 자기 자신은 소스로 고를 수 없다
            combo.addItem(f[8] if f[8] else f[0], f[0])
        layout.addWidget(combo)
        applyButton = QtWidgets.QPushButton("Connect")
        layout.addWidget(applyButton)

        def _onApply():
            try:
                sourceAxis = combo.currentData()
                if not sourceAxis:
                    picker.close()
                    return
                try:
                    connectCouplingSource(couplingNodeName, sourceAxis)
                except RuntimeError as error:
                    print("Maro: coupling source connection failed -- {}".format(error))
                    picker.close()
                    return
                picker.close()
                self.update()
            except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
                import traceback
                traceback.print_exc()

        applyButton.clicked.connect(_onApply)
        picker.move(self.mapToGlobal(QtCore.QPoint(int(self.width() / 2), int(self.height() / 2))))
        picker.show()

    def mouseDoubleClickEvent(self, event):
        try:
            rows = self._capabilityRows()
            connected = [r for r in rows if r["connected"]]
            if len(connected) >= 2:
                self._expanded = not self._expanded
                if not self._expanded:
                    # 접으면 선택도 함께 푼다 -- 안 보이는 행이 선택된 채로
                    # 남으면 Delete가 화면에 없는 것을 지운다.
                    self._selectedCapabilityIndex = None
                self.update()
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
            import traceback
            traceback.print_exc()

    def keyPressEvent(self, event):
        try:
            if event.key() != QtCore.Qt.Key_Delete:
                return
            rows = self._capabilityRows()
            # [최종 리뷰 I-1(d)] 설계 스펙 §5.3은 Delete에 두 동작을 준다:
            #  - 접힌 상태(또는 고른 행이 없을 때) -> 가장 나중에 추가된
            #    능력 하나만 벗긴다.
            #  - 펼친 상태에서 개별 항목을 고른 뒤 -> 그 항목만 지운다.
            # 선택 인덱스가 아직 실제로 연결돼 있는지 다시 확인한다 --
            # 고른 뒤 다른 경로(다른 SONE, 스크립트)로 그 슬롯이 끊겼을 수
            # 있고, 그때는 조용히 "가장 나중" 경로로 되돌아가는 편이
            # 없는 인덱스에 대고 커맨드를 부르는 것보다 낫다.
            target = None
            if self._expanded and self._selectedCapabilityIndex is not None:
                for row in rows:
                    if (row["logicalIndex"] == self._selectedCapabilityIndex
                            and row["connected"]):
                        target = self._selectedCapabilityIndex
                        break
            if target is None:
                target = indexOfCapabilityToPeel(rows)
            if target is None:
                return
            try:
                cmds.maroDisconnectCapability(self._axis, index=target)
            except RuntimeError as error:
                print("Maro: maroDisconnectCapability failed -- {}".format(error))
                return
            if self._selectedCapabilityIndex == target:
                self._selectedCapabilityIndex = None
            self.update()
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
            import traceback
            traceback.print_exc()
