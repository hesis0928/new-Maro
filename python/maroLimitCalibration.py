"""Limit/TranslationLimit이 공유하는 뷰포트 캘리브레이션 엔진(설계 스펙
2026-09-07 §5). 이 파일의 위쪽 절(axisDirectionFromPoints/
axisBasisEulerXYZ/expandRange/mayaDirectionToRos)은 Maya 씬 상태에
의존하지 않는 순수 함수다 -- maya.api.OpenMaya(om2)는 행렬/벡터 연산
라이브러리로만 쓴다(python/maroUrdfExport.py의 computeRelativeOrigin과
같은 성격). 아래쪽 절(뷰포트 리그/HUD)은 실제 Maya 씬과 Qt에 의존한다.
"""
import math

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from PySide6 import QtCore, QtGui, QtWidgets


def axisDirectionFromPoints(pointA, pointB):
    """pointA/pointB: (x,y,z) 튜플, 뷰포트에서 클릭한 두 월드 좌표점.
    pointA -> pointB 방향의 정규화 벡터를 돌려준다. 두 점이 같으면(길이 0)
    방향을 정의할 수 없으므로 ValueError."""
    vec = om2.MVector(pointB[0] - pointA[0], pointB[1] - pointA[1], pointB[2] - pointA[2])
    length = vec.length()
    if length < 1e-9:
        raise ValueError("axisDirectionFromPoints: pointA and pointB must differ")
    unit = vec.normal()
    return (unit.x, unit.y, unit.z)


def axisBasisEulerXYZ(axisDirection):
    """axisDirection(정규화된 (x,y,z))을 로컬 Z로 갖는 정규직교 기저를
    구성해 (rx, ry, rz) 오일러 각(도, XYZ 고정축 순서)으로 돌려준다.
    X/Y 축의 구체적인 방향은 임의(자유도 1개짜리 계 -- 회전/이동 매니퍼레이터가
    로컬 Z 축 하나만 쓰므로 X/Y가 어느 쪽을 향하든 캘리브레이션 결과에
    영향이 없다)이지만, 항상 같은 규칙(월드 업 벡터 기준)으로 결정해
    호출마다 결과가 안정적이도록 한다. axisDirection이 월드 업과 거의
    평행하면(짐벌 특이점) 월드 X를 참조 벡터로 대신 쓴다."""
    z = om2.MVector(*axisDirection).normal()
    worldUp = om2.MVector(0.0, 1.0, 0.0)
    reference = worldUp if abs(z * worldUp) < 0.999 else om2.MVector(1.0, 0.0, 0.0)
    x = (reference ^ z).normal()   # cross product, MVector의 ^ 연산자
    y = (z ^ x).normal()

    m = om2.MMatrix((
        x.x, x.y, x.z, 0.0,
        y.x, y.y, y.z, 0.0,
        z.x, z.y, z.z, 0.0,
        0.0, 0.0, 0.0, 1.0,
    ))
    euler = om2.MTransformationMatrix(m).rotation(asQuaternion=False)
    euler = euler.reorder(om2.MEulerRotation.kXYZ)
    return (math.degrees(euler.x), math.degrees(euler.y), math.degrees(euler.z))


def expandRange(currentMin, currentMax, sample):
    """collect 한 번: sample을 currentMin/currentMax 범위에 편입시킨
    (newMin, newMax)를 돌려준다. 범위 안의 샘플은 아무 효과가 없다."""
    return (min(currentMin, sample), max(currentMax, sample))


def mayaDirectionToRos(direction):
    """(x,y,z) 방향 벡터를 ROS(REP-103) 프레임으로. 위치 변환
    (maroMayaToRos)과 같은 축 재배치 (x,y,z)->(x,-z,y)이지만, 방향
    벡터는 단위 없는 순수 방향이므로 씬 단위 스케일을 적용하지 않는다."""
    x, y, z = direction
    return (x, -z, y)


# polygon vertex / edge / face의 selection mask 번호. [실측 확인] 값을
# 손으로 짐작하면 안 된다 -- 이 번호를 틀리게 쓴 이전 구현은 예외 대신
# 빈 결과를 돌려받아 "클릭이 먹지 않는" 증상으로만 나타났다. 또한
# selectionMask에 튜플을 주면 filterExpand가 조용히 None을 돌려준다
# (리스트여야 한다) -- 둘 다 실패가 보이지 않는 종류라 실측으로 고정한다.
_COMPONENT_MASKS = [31, 32, 34]


def readAxisPointsFromSelection():
    """지금 선택돼 있는 폴리곤 컴포넌트 두 개의 월드 좌표를 돌려준다.

    캘리브레이션 축 방향을 정하는 입력이다. 전용 tool context(scriptCtx)를
    세워 클릭을 가로채지 않고, 사용자가 Maya 기본 선택 툴로 두 점을 고른 뒤
    패널 버튼을 누르는 흐름을 쓴다 -- 컨스트레인트 생성 등 Maya 자체 기능과
    같은 방식이다. [실측] scriptCtx 방식은 finalCommandScript가 MEL이라
    self를 못 넘기고, 콜백 안에서 다음 컨텍스트를 세우면 Maya가 그 전환을
    되돌리며, 남아 있는 선택이 setAutoComplete를 즉시 재발동시켜 무한루프가
    났다 -- 이 함수는 그 실패 유형 전체를 없앤다.

    선택 순서 추적(selectPref -trackSelectionOrder)이 켜져 있으면 그 순서를
    쓴다(축의 부호가 사용자가 고른 순서를 따른다). 꺼져 있으면 Maya가 주는
    순서를 그대로 쓴다 -- 사용자 환경 설정을 우리가 바꾸지는 않는다.

    두 개가 아니거나 컴포넌트가 아니면 ValueError(메시지는 그대로 사용자에게
    보여줄 수 있는 한국어 안내).
    """
    ordered = cmds.ls(orderedSelection=True, flatten=True) or []
    picked = cmds.filterExpand(ordered, selectionMask=_COMPONENT_MASKS) or []
    if len(picked) != 2:
        selected = cmds.ls(selection=True, flatten=True) or []
        picked = cmds.filterExpand(selected, selectionMask=_COMPONENT_MASKS) or []
    if len(picked) != 2:
        raise ValueError(
            "Maro: 뷰포트에서 축 방향이 될 두 점(버텍스/에지/페이스)을 선택한 뒤 "
            "다시 누르세요 -- 지금 선택된 컴포넌트는 {}개입니다.".format(len(picked)))
    return (_componentCenter(picked[0]), _componentCenter(picked[1]))


def _componentCenter(component):
    """컴포넌트 하나의 월드 좌표 대표점. cmds.pointPosition()은 버텍스/CV만
    받으므로(면/에지에 주면 RuntimeError -- 실측 확인), 어떤 컴포넌트든
    구성 버텍스로 환산해 그 중심을 쓴다. 버텍스는 자기 자신으로 환산되므로
    세 종류가 같은 경로를 탄다."""
    verts = cmds.ls(cmds.polyListComponentConversion(component, toVertex=True),
                    flatten=True) or []
    if not verts:
        raise ValueError(
            "Maro: 선택한 컴포넌트({})에서 좌표를 읽을 수 없습니다.".format(component))
    positions = [cmds.pointPosition(v, world=True) for v in verts]
    count = float(len(positions))
    return tuple(sum(p[i] for p in positions) / count for i in range(3))


_CHANNELS_ROTATE = ("rotateX", "rotateY", "rotateZ")
_CHANNELS_TRANSLATE = ("translateX", "translateY", "translateZ")


class CalibrationSession:
    """Limit(회전)/TranslationLimit(이동) 공유 캘리브레이션 리그.

    start()가 헬퍼 로케이터를 만들어 axisDirection 방향으로 정렬하고,
    대상의 회전(또는 이동) 채널을 DG 커넥션에서 임시로 끊은 뒤 헬퍼
    로케이터 밑에 부모로 넣는다. 사용자는 Maya 네이티브 Rotate(또는
    Move) 툴로 헬퍼 로케이터의 로컬 Z 축만 조작하면 되고, currentValue()는
    그 rotateZ(또는 translateZ)를 그대로 읽는다 -- 별도의 축-각 투영
    수식이 필요 없다(헬퍼 로케이터 자체가 그 축으로 정렬돼 있으므로).

    finish()/cancel()은 항상 같은 _cleanup()을 거쳐 원래 커넥션/부모/값을
    복원한다 -- 어느 경로로 세션이 끝나든(정상 완료, 사용자 취소, HUD
    창을 강제로 닫음, 예외) 반드시 이 복원이 실행되도록 호출부(HUD/패널)가
    try/finally로 감싼다.
    """

    def __init__(self):
        self._helper = None
        self._target = None
        self._channels = None
        self._isLinear = False
        self._originalSources = None   # [str|None, str|None, str|None]
        self._originalParent = None    # str|None
        self._originalValues = None    # [float, float, float]
        self._min = 0.0
        self._max = 0.0
        self._cleaned = True

    def helperLocator(self):
        return self._helper

    def start(self, targetTransform, axisDirection, pivotWorld, isLinear=False):
        if not self._cleaned:
            raise RuntimeError("CalibrationSession.start() called while already active")

        # 대상은 항상 풀 경로로 정규화해서 들고 다닌다. 짧은 이름은 계층이
        # 바뀌어도 Maya가 해소해 주지만 그건 이름이 유일할 때만이고, 아래
        # _reparent()가 만드는 것도 풀 경로다 -- 두 형태를 섞지 않는다.
        self._target = cmds.ls(targetTransform, long=True)[0]
        self._channels = _CHANNELS_TRANSLATE if isLinear else _CHANNELS_ROTATE
        self._isLinear = isLinear
        self._min = 0.0
        self._max = 0.0

        # 아래 씬 변경 전부를 undo 한 덩어리로 묶는다.
        #
        # [설계 검토로 발견] 안 묶으면 로케이터 생성 / 커넥션 끊기 / 재부모화가
        # 각각 별개의 undo 항목이 된다. 캘리브레이션 도중 사용자가 Ctrl+Z를
        # 누르면 그중 하나만 되돌아가는데, 하필 "로케이터 생성"이 되돌아가면
        # **그 밑에 매달린 사용자 오브젝트가 함께 삭제된다.** 한 덩어리로
        # 묶으면 Ctrl+Z 한 번이 셋업 전체를 원자적으로 되돌리므로 그 상태가
        # 애초에 성립하지 않는다. 되돌려진 뒤의 정리 호출은 _cleanup()이
        # 방어한다(_isUnderHelper()/objExists 검사).
        cmds.undoInfo(openChunk=True)
        try:
            self._startInChunk(axisDirection, pivotWorld)
        finally:
            cmds.undoInfo(closeChunk=True)

    def _startInChunk(self, axisDirection, pivotWorld):
        # 1) 원래 커넥션/값을 전부 캡처한다 -- 하나라도 놓치면 복원이
        #    불완전해지므로 세 채널 모두 항상 캡처한다.
        self._originalSources = []
        self._originalValues = []
        for channel in self._channels:
            plug = "{}.{}".format(self._target, channel)
            sources = cmds.listConnections(plug, source=True, destination=False, plugs=True)
            self._originalSources.append(sources[0] if sources else None)
            self._originalValues.append(cmds.getAttr(plug))

        parents = cmds.listRelatives(self._target, parent=True, fullPath=True)
        self._originalParent = parents[0] if parents else None

        # 2) 커넥션을 끊는다(있는 것만) -- 그래야 자유롭게 재배선 가능.
        for channel, source in zip(self._channels, self._originalSources):
            if source is not None:
                cmds.disconnectAttr(source, "{}.{}".format(self._target, channel))

        # 3) 헬퍼 로케이터를 만들어 axisDirection으로 정렬하고 pivotWorld에 둔다.
        self._helper = cmds.ls(cmds.spaceLocator(name="maroCalibHelper#")[0],
                               long=True)[0]
        rx, ry, rz = axisBasisEulerXYZ(axisDirection)
        cmds.setAttr(self._helper + ".rotate", rx, ry, rz, type="double3")
        cmds.xform(self._helper, worldSpace=True, translation=pivotWorld)

        # 4) 대상을 헬퍼 로케이터 밑으로(월드 포즈 보존 -- 커넥션을 이미
        #    끊었으므로 회전/이동 채널이 자유라 이 재배선이 가능하다).
        #
        # [실측으로 잡은 버그] cmds.parent()가 옮기고 나면 **옮기기 전의 풀
        # DAG 경로는 더 이상 존재하지 않는다.** 그런데 이 클래스는 정리
        # 단계에서 self._target으로 다시 parent/setAttr/connectAttr를 한다 --
        # 옛 경로를 그대로 들고 있으면 그 셋이 전부 "No object matches name"으로
        # 실패해서, 대상이 헬퍼 밑에 매달린 채 구동 커넥션도 끊긴 상태로
        # 남는다(= 사용자 리그가 조용히 망가진다). 짧은 이름은 Maya가 계층과
        # 무관하게 해소해 주기 때문에 이 결함이 오래 드러나지 않았는데, 실제
        # 패널(maroCapabilityPanel._onCalibrate)은 cmds.ls(..., long=True)로
        # 정규화한 **풀 경로**를 넘긴다 -- 즉 진짜 사용 경로가 정확히 깨지는
        # 쪽이었다. cmds.parent()가 돌려주는 새 이름과 이미 확정된 새 부모를
        # 조합해 새 풀 경로를 만들어 둔다(maroDagMenu.py가 같은 함정에 대해
        # 이미 쓰고 있는 방식과 동일).
        self._target = self._reparent(self._target, self._helper)

        self._cleaned = False

    def _isUnderHelper(self):
        """대상이 지금도 헬퍼 로케이터 밑에 있는가. 사용자가 셋업을 undo했거나
        직접 계층을 바꾼 뒤라면 False -- 그때 정리가 억지로 parent를 부르면
        멀쩡한 계층을 흔든다."""
        if self._helper is None or not cmds.objExists(self._helper):
            return False
        parents = cmds.listRelatives(self._target, parent=True, fullPath=True) or []
        return bool(parents) and parents[0] == self._helper

    @staticmethod
    def _reparent(target, newParent):
        """target을 newParent(None이면 월드) 밑으로 옮기고 **새 풀 경로**를
        돌려준다. 옮긴 뒤에도 옛 경로를 계속 쓰면 안 되는 이유는 위 주석 참고."""
        if newParent is None:
            moved = cmds.parent(target, world=True)[0]
            return cmds.ls(moved, long=True)[0]
        moved = cmds.parent(target, newParent)[0]
        return newParent + "|" + moved.split("|")[-1]

    def currentValue(self):
        channel = "translateZ" if self._isLinear else "rotateZ"
        return cmds.getAttr("{}.{}".format(self._helper, channel))

    def collect(self):
        sample = self.currentValue()
        self._min, self._max = expandRange(self._min, self._max, sample)
        return (self._min, self._max)

    def rangeSoFar(self):
        return (self._min, self._max)

    def finish(self):
        self._cleanup()
        return (self._min, self._max)

    def cancel(self):
        self._cleanup()

    def _cleanup(self):
        if self._cleaned:
            return
        try:
            # 부모 복원(대상을 헬퍼 로케이터 밖으로) -- 헬퍼를 지우기 전에
            # 반드시 먼저 해야 대상이 함께 삭제되지 않는다.
            #
            # 여기서도 새 경로를 받아 self._target을 갱신한다. 아래 채널
            # 복원 루프가 그 경로를 쓰는데, 옮기고 나면 지금 경로는 또
            # 무효가 되기 때문이다(start()의 같은 함정, 같은 주석 참고).
            #
            # 대상이 이미 헬퍼 밑에 없으면(예: 사용자가 Ctrl+Z로 셋업을
            # 통째로 되돌린 뒤) 옮길 것이 없다 -- 그 경우 억지로 parent를
            # 부르면 오히려 멀쩡한 계층을 흔든다.
            if cmds.objExists(self._target) and self._isUnderHelper():
                self._target = self._reparent(self._target, self._originalParent)
        except Exception:  # noqa: BLE001 -- 정리 경로는 절대 못 넘어가면 안 된다
            import traceback
            traceback.print_exc()

        try:
            if self._helper is not None and cmds.objExists(self._helper):
                cmds.delete(self._helper)
        except Exception:  # noqa: BLE001
            import traceback
            traceback.print_exc()

        if not cmds.objExists(self._target):
            # 대상이 사라졌다(사용자가 지웠거나 셋업 자체가 undo됐다).
            # 복원할 것이 없고, 없는 노드에 setAttr을 시도하면 경고만
            # 쏟아진다. 래치는 반드시 세우고 끝낸다.
            self._cleaned = True
            return

        for channel, value, source in zip(self._channels, self._originalValues,
                                          self._originalSources):
            plug = "{}.{}".format(self._target, channel)
            try:
                if source is None:
                    cmds.setAttr(plug, value)
                else:
                    cmds.connectAttr(source, plug, force=True)
            except Exception as exc:  # noqa: BLE001 -- 복원 실패는 조용히 삼키지 않는다
                cmds.warning(
                    "Maro: failed to restore {} (original source {!r}): {}".format(
                        plug, source, exc))

        self._cleaned = True


class CalibrationHud(QtWidgets.QWidget):
    """캘리브레이션 세션의 작은 실시간 안내 창. 스페이스바는 이 창에
    포커스가 있을 때만 Collect를 트리거한다(QtCore.Qt.WidgetWithChildrenShortcut) --
    Maya 뷰포트의 기본 스페이스바(hotbox) 동작과 절대 충돌하지 않는다.
    """

    def __init__(self, session, unitLabel, onCollect, onFinish, parent=None):
        super().__init__(parent, QtCore.Qt.Tool | QtCore.Qt.WindowStaysOnTopHint)
        self._session = session
        self._onCollectCallback = onCollect
        self._onFinishCallback = onFinish
        self.setWindowTitle("Maro 캘리브레이션")

        layout = QtWidgets.QVBoxLayout(self)
        self._valueLabel = QtWidgets.QLabel("")
        layout.addWidget(self._valueLabel)
        self._rangeLabel = QtWidgets.QLabel("")
        layout.addWidget(self._rangeLabel)

        collectButton = QtWidgets.QPushButton("Collect (Space)")
        collectButton.clicked.connect(self._onCollect)
        layout.addWidget(collectButton)

        finishButton = QtWidgets.QPushButton("완료")
        finishButton.clicked.connect(self._onFinish)
        layout.addWidget(finishButton)

        shortcut = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Space), self)
        shortcut.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self._onCollect)

        self._unitLabel = unitLabel
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(50)
        self._refresh()

    def _refresh(self):
        try:
            value = self._session.currentValue()
            self._valueLabel.setText("현재: {:.3f} {}".format(value, self._unitLabel))
            mn, mx = self._session.rangeSoFar()
            self._rangeLabel.setText("누적 범위: [{:.3f}, {:.3f}] {}".format(
                mn, mx, self._unitLabel))
        except Exception:  # noqa: BLE001 -- QTimer 콜백 경계
            import traceback
            traceback.print_exc()

    def _onCollect(self):
        try:
            self._onCollectCallback()
            self._refresh()
        except Exception:  # noqa: BLE001 -- Qt 콜백 경계
            import traceback
            traceback.print_exc()

    def _onFinish(self):
        try:
            self._timer.stop()
            self._onFinishCallback()
            self.close()
        except Exception:  # noqa: BLE001 -- Qt 콜백 경계
            import traceback
            traceback.print_exc()

    def closeEvent(self, event):
        # 사용자가 완료 버튼이 아니라 창의 X 버튼으로 닫아도 같은 정리가
        # 일어나야 한다 -- onFinishCallback이 세션의 finish()를 부르므로
        # 중복 호출은 CalibrationSession._cleaned 가드가 흡수한다.
        try:
            self._timer.stop()
            self._onFinishCallback()
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
            import traceback
            traceback.print_exc()
        super().closeEvent(event)
