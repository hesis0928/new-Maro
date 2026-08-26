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


from PySide6 import QtCore, QtGui, QtWidgets

import maroSingleObjectNodeEditor

_JOB_ID = None
_PANEL = None

_GRID_COLUMNS = 4
_CELL_WIDTH = 140.0
_CELL_HEIGHT = 50.0
_GRID_GAP = 12.0


# 씬에서 선택된 오브젝트에 대응하는 GSON을 구분하는 테두리 굵기(px).
_SELECTION_PEN_WIDTH = 2.5

# GSON 채움색이 밝은지 어두운지 가르는 상대 휘도 문턱. 계수는 표준 sRGB
# 휘도 가중치(ITU-R BT.601)다.
_LUMINANCE_THRESHOLD = 0.5


def _textColorFor(r, g, b):
    """채움색 위에 읽히는 글자색. [최종 리뷰 I-4] paintEvent가 브러시만
    세우고 펜을 안 세우면 축 이름이 테마 기본 전경색으로 그려져서, 사용자가
    고른 임의의 채움색과 대비가 거의 없을 수 있다(밝은 테마 + 밝은 노랑,
    어두운 테마 + 진한 남색 등). 채움색의 휘도로 흑/백을 고른다."""
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return QtCore.Qt.black if luminance > _LUMINANCE_THRESHOLD else QtCore.Qt.white


class ObjectNodeEditor(QtWidgets.QWidget):
    """GSON 그리드. setStyleSheet()를 부르지 않는다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selectedAxis = None

    def refresh(self):
        self.update()

    def selectAxis(self, axisFullPath):
        """씬 선택 -> GSON 하이라이트(설계 스펙 §6). 옛 maroAxisPanel의
        같은 이름 메서드를 승계한다 -- 거기서는 리스트 행 하이라이트였고
        여기서는 GSON 테두리 강조다."""
        self._selectedAxis = axisFullPath
        self.update()

    def _rows(self):
        return sliceAxisRows(cmds.maroListAxisNodes())

    def _gsonRects(self):
        rows = self._rows()
        positions = computeGsonGridLayout(
            len(rows), _GRID_COLUMNS, _CELL_WIDTH, _CELL_HEIGHT, _GRID_GAP)
        return list(zip(rows, positions))

    def paintEvent(self, event):
        # paintEvent는 리페인트마다 Maya 커맨드를 부른다(_rows()). 축이
        # 리페인트 도중 사라지거나 displayColor가 예상 밖의 값이면 여기서
        # 예외가 나는데, 밖으로 내보내면 Qt가 다시 그릴 때마다 같은
        # 트레이스백이 무한히 반복된다 -- 이 코드베이스의 Maya 콜백 경계
        # 규율(_onSceneSelectionChanged, maroRosProxy._onIdle)을 Qt 이벤트
        # 핸들러에도 그대로 적용한다.
        try:
            painter = QtGui.QPainter(self)
            defaultPen = painter.pen()
            highlight = self.palette().color(QtGui.QPalette.Highlight)
            for row, (x, y) in self._gsonRects():
                rect = QtCore.QRectF(x + 4, y + 4, _CELL_WIDTH - 8, _CELL_HEIGHT - 8)
                r, g, b = row["displayColor"]
                painter.setBrush(QtGui.QColor.fromRgbF(r, g, b))
                if row["axisFullPath"] == self._selectedAxis:
                    # [최종 리뷰 I-1(a)] 씬에서 선택된 오브젝트에 대응하는
                    # GSON을 굵은 강조색 테두리로 구분한다(설계 스펙 §6).
                    painter.setPen(QtGui.QPen(highlight, _SELECTION_PEN_WIDTH))
                else:
                    painter.setPen(defaultPen)
                painter.drawRoundedRect(rect, 6, 6)
                # 테두리와 글자는 서로 다른 색이다 -- 테두리를 그린 뒤에
                # 글자용 펜으로 바꾼다.
                painter.setPen(QtGui.QPen(QtGui.QColor(_textColorFor(r, g, b))))
                painter.drawText(rect, QtCore.Qt.AlignCenter,
                                 row["displayName"] or row["axisFullPath"])
            painter.setPen(defaultPen)
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계, 위 주석 참고
            import traceback
            traceback.print_exc()

    def _axisAt(self, pos):
        for row, (x, y) in self._gsonRects():
            rect = QtCore.QRectF(x, y, _CELL_WIDTH, _CELL_HEIGHT)
            if rect.contains(pos):
                return row["axisFullPath"], row["boundTargetPath"]
        return None, None

    # event.position()만 쓴다 -- maroSingleObjectNodeEditor.py의 같은 자리
    # 주석 참고: 실측(Maya 2026 / PySide6 6.5.3)으로 QMouseEvent가 두 메서드를
    # 다 갖고 있어 hasattr(event, "position") 분기는 항상 True로 떨어지고
    # localPos() 쪽은 절대 실행되지 않는 죽은 코드다.
    def mousePressEvent(self, event):
        try:
            axis, target = self._axisAt(event.position())
            if axis is None:
                return
            self._selectedAxis = axis
            cmds.select(target if target else axis, replace=True)
            self.update()
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
            import traceback
            traceback.print_exc()

    def mouseDoubleClickEvent(self, event):
        try:
            axis, _target = self._axisAt(event.position())
            if axis is not None:
                maroSingleObjectNodeEditor.openSingleObjectNodeEditor(axis)
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
            import traceback
            traceback.print_exc()

    def contextMenuEvent(self, event):
        try:
            self._showContextMenu(event)
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
            import traceback
            traceback.print_exc()

    def _showContextMenu(self, event):
        axis, _target = self._axisAt(event.pos())
        if axis is None:
            return
        row = None
        for candidate in self._rows():
            if candidate["axisFullPath"] == axis:
                row = candidate
                break
        if row is None:
            return

        menu = QtWidgets.QMenu(self)
        renameAction = menu.addAction("Rename")
        recolorAction = menu.addAction("Recolor")
        # [최종 리뷰 I-1(b)] 설계 스펙 §5.5/§6이 요구하는 Unbind. 축은 남기고
        # 타겟 연결만 끊는다("리깅을 바꾸는 중 임시로 떼어 두기") -- 삭제된
        # maroAxisPanel의 Unbind 버튼에서 승계한 기능이다. 바인딩된 타겟이
        # 없으면 의미가 없으므로 그때는 항목을 아예 내지 않는다.
        unbindAction = menu.addAction("Unbind") if row["boundTargetPath"] else None
        deleteAction = menu.addAction("Delete")
        chosen = menu.exec(event.globalPos())
        if chosen is renameAction:
            newName, ok = QtWidgets.QInputDialog.getText(self, "Rename", "Display name:")
            if ok:
                cmds.setAttr(axis + ".displayName", newName, type="string")
                self.refresh()
        elif chosen is recolorAction:
            color = QtWidgets.QColorDialog.getColor(
                QtGui.QColor.fromRgbF(*row["displayColor"]), self)
            if color.isValid():
                cmds.setAttr(axis + ".displayColor",
                             color.redF(), color.greenF(), color.blueF(), type="double3")
                self.refresh()
        elif unbindAction is not None and chosen is unbindAction:
            try:
                cmds.maroUnbindAxis(axis)
            except RuntimeError as error:
                print("Maro: maroUnbindAxis failed -- {}".format(error))
                return
            self.refresh()
        elif chosen is deleteAction:
            self._deleteAxis(axis)
            self.refresh()

    def _deleteAxis(self, axis):
        """[최종 리뷰 I-1(c)] GSON의 Delete = **축 전체 제거**(설계 스펙 §6:
        "capability 노드까지 포함해 cmds.delete"). SONE의 Delete 키가 능력
        하나만 벗기는 것과 의도적으로 구분되는 동작이다.

        `cmds.delete(axis)` 한 줄로는 두 가지가 남는다 -- 실측(mayapy,
        Maya 2026)으로 둘 다 확인했다:

        1. **부모 트랜스폼.** `createNode("maroAxis")`는 로케이터형 DAG
           셰이프라 Maya가 부모 트랜스폼(`|transform1`)을 자동으로 만든다.
           셰이프만 지우면 그 빈 트랜스폼이 씬에 남는다(실측: 셰이프 삭제
           후에도 `objExists("|transform1") == True`). 반대로 부모 트랜스폼을
           지우면 셰이프도 함께 사라진다 -- 그래서 여기서는 셰이프를 먼저
           지운 뒤, 그래도 남아 있으면 부모를 지운다(둘 다 명시적으로).
        2. **capability 노드.** MaroDeleteWatcher는 축이 사라질 때 능력
           노드를 지우지 않고 `maroOrphanSet`으로 옮겨 재사용을 위해
           살려 둔다(2026-08-13 스펙 §8 "고아 능력 노드"). 그건 축이
           "어쩌다" 사라지는 일반 경로의 규율이고, 여기 GSON의 Delete는
           사용자가 명시적으로 "이 축을 통째로 없애 달라"고 한 경로라
           2026-08-25 스펙 §6이 능력 노드까지 함께 지우라고 못박는다.
           그래서 축보다 **먼저** 지운다 -- 축을 먼저 지우면 감시자가 그
           노드들을 고아 세트로 옮겨 버려 이름으로 다시 찾기 어려워진다.

        전부 한 undo 청크로 묶는다 -- 사용자가 보기엔 한 번의 삭제이므로
        Ctrl+Z 한 번으로 통째로 되돌아와야 한다(2026-08-13 스펙 §8의
        "삭제 전파는 반드시 사용자의 삭제와 같은 undo 청크" 규율).
        """
        cmds.undoInfo(openChunk=True)
        try:
            capabilityNodes = []
            try:
                capabilityNodes = [
                    r["capabilityNodeName"]
                    for r in maroSingleObjectNodeEditor.sliceCapabilityRows(
                        cmds.maroListAxisNodes(capabilities=axis))
                    if r["connected"] and r["capabilityNodeName"]]
            except (RuntimeError, ValueError) as error:
                # 능력 목록을 못 읽었다고 축 삭제 자체를 포기하지는 않는다 --
                # 사용자가 요청한 주된 동작은 축 제거다.
                print("Maro: could not list capabilities of {} -- {}".format(axis, error))

            parents = cmds.listRelatives(axis, parent=True, fullPath=True) or []
            # [최종 리뷰 재검토] 자동 생성된 부모 트랜스폼(위 도크스트링의
            # 경우 1)은 축 하나만 자식으로 가진다는 것이 전제다. 사용자가
            # 축을 수동으로 다른(형제가 있는) 트랜스폼 밑으로 재부모시킨
            # 드문 경우까지 지우면 그 형제와 무관한 노드를 함께 날리게
            # 되므로, 축을 지우기 전에 "그 부모의 유일한 자식이 이 축인가"
            # 를 먼저 확인해 둔다.
            soleChildParents = [
                parent for parent in parents
                if cmds.listRelatives(parent, children=True, fullPath=True) == [axis]]
            try:
                if capabilityNodes:
                    cmds.delete(capabilityNodes)
                cmds.delete(axis)
                for parent in soleChildParents:
                    if cmds.objExists(parent):
                        cmds.delete(parent)
            except RuntimeError as error:
                print("Maro: failed to delete axis {} -- {}".format(axis, error))
        finally:
            cmds.undoInfo(closeChunk=True)


def _onSceneSelectionChanged():
    """씬 선택 -> GSON 하이라이트(설계 스펙 §6). 예외가 새어 나가면 안
    된다 -- SelectionChanged 콜백 경계 규율 (maroRosProxy._onIdle과 같은
    이유).

    [최종 리뷰 I-1(a)] 예전에는 refresh()만 불러서 실제로 하이라이트되는
    것이 없었다. 삭제된 maroAxisPanel._onSceneSelectionChanged가 하던
    역방향 조회를 그대로 승계한다: 선택 목록을 축 행들과 맞춰 보되, 축
    자신이 선택됐을 수도 있으므로 axisFullPath와 boundTargetPath를 둘 다
    본다. 선택이 비었거나 어느 축에도 안 걸리면 하이라이트를 푼다.

    반대 방향(GSON 클릭 -> 씬 선택)은 ObjectNodeEditor.mousePressEvent가
    맡는다 -- 여기서 다시 씬 선택을 건드리지 않는 이유이자, 두 방향이 서로를
    무한히 트리거하지 않는 이유다.
    """
    try:
        if _PANEL is None:
            return
        selection = cmds.ls(selection=True, long=True) or []
        selected = None
        if selection:
            for row in sliceAxisRows(cmds.maroListAxisNodes()):
                if (row["axisFullPath"] in selection
                        or (row["boundTargetPath"]
                            and row["boundTargetPath"] in selection)):
                    selected = row["axisFullPath"]
                    break
        _PANEL.selectAxis(selected)
    except Exception:  # noqa: BLE001
        import traceback
        traceback.print_exc()


def refreshIfOpen():
    """ONE이 열려 있으면 다시 그린다. 안 열려 있으면 무동작.

    [최종 리뷰 Minor-7] maroDagMenu._onMenuItemClicked()가 새 축을 만든 뒤
    부른다. 그 전에는 새 축이 ONE에 나타나는 것이 **우연**에 기대고 있었다:
    createNode()가 마침 씬 선택을 바꾸고, 그것이 마침 SelectionChanged
    scriptJob을 깨우고, 그 콜백이 마침 refresh()를 부르는 경로였다. 셋 중
    하나라도 (Maya 버전 차이든 향후 수정이든) 달라지면 새 축이 조용히 안
    보이게 된다. 명시적으로 알리는 진입점 하나를 두는 편이 싸고 확실하다.
    """
    try:
        if _PANEL is None:
            return
        _PANEL.refresh()
    except Exception:  # noqa: BLE001 -- 호출자(마킹 메뉴 콜백) 경계
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
