"""Maro 축/capability 에디터 패널 -- Maro Main UI의 editorHost에 임베드된다.

패널은 자체 상태를 갖지 않는다(maroDiagPanel.py와 같은 원칙, 설계 스펙
§9): 씬의 maroAxis/capability 노드가 유일한 진실이고, 이 모듈은
maroListAxisNodes가 돌려준 것을 그리고, 버튼 클릭을 커맨드 호출로
옮기기만 한다.

평탄한 배열을 행으로 되돌리는 부분은 UI를 만들지 않는 순수 함수로 분리해
뒀다 -- mayapy 배치 모드에는 UI가 없어 위젯은 만들 수 없지만 이 부분은
자동 검증된다(maroDiagPanel.py의 sliceRows와 같은 이유).
"""
import maya.cmds as cmds
from PySide6 import QtCore, QtWidgets

# C++ 쪽 계약. 바뀌면 양쪽을 함께 고쳐야 한다(MaroAxisEditorCommands.cpp 참고).
AXIS_FIELDS = 8
CAPABILITY_FIELDS = 5

# maroAddCapability -type/버튼 라벨 쌍. 순서가 패널의 버튼 순서다.
CAPABILITY_TYPES = [
    ("rotation", "+Rotation"),
    ("translation", "+Translation"),
    ("limit", "+Limit"),
    ("translationLimit", "+TranslationLimit"),
    ("sensorDirection", "+SensorDirection"),
    ("sensorRange", "+SensorRange"),
    ("coupling", "+Coupling"),
]


def sliceAxisRows(flat):
    """maroListAxisNodes()의 평탄한 배열을 축 행 딕셔너리 목록으로 되돌린다."""
    if flat is None:
        return []
    if len(flat) % AXIS_FIELDS != 0:
        raise ValueError(
            "axis row array length {} is not a multiple of {}".format(
                len(flat), AXIS_FIELDS))
    rows = []
    for i in range(len(flat) // AXIS_FIELDS):
        f = flat[i * AXIS_FIELDS:(i + 1) * AXIS_FIELDS]
        rows.append({
            "axisFullPath": f[0],
            "jointName": f[1],
            "boundTargetPath": f[2],
            "parentAxisPath": f[3],
            "controlMode": int(f[4]),
            "enabled": f[5] == "1",
            "conventionAxis": int(f[6]),
            "capabilityCount": int(f[7]),
        })
    return rows


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


class AxisPanel(QtWidgets.QWidget):
    """축 목록 + 선택된 축의 capability 스택 + 추가/삭제 버튼.

    setStyleSheet()를 부르지 않는다 -- maroMainWindow.py와 같은 규율
    (설계 스펙 §4.2, tests/maya/test_main_window.py가 grep으로 검사).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selectedAxis = None

        layout = QtWidgets.QHBoxLayout(self)

        axisColumn = QtWidgets.QVBoxLayout()
        self._axisList = QtWidgets.QListWidget()
        self._axisList.setObjectName("maroAxisPanelAxisList")
        self._axisList.itemClicked.connect(self._onAxisRowClicked)
        axisColumn.addWidget(self._axisList)
        self._unbindButton = QtWidgets.QPushButton("Unbind")
        self._unbindButton.setObjectName("maroAxisPanelUnbindButton")
        self._unbindButton.clicked.connect(self._onUnbindClicked)
        axisColumn.addWidget(self._unbindButton)
        layout.addLayout(axisColumn)

        capColumn = QtWidgets.QVBoxLayout()
        self._capList = QtWidgets.QListWidget()
        self._capList.setObjectName("maroAxisPanelCapabilityList")
        capColumn.addWidget(self._capList)

        buttonRow = QtWidgets.QHBoxLayout()
        for typeName, label in CAPABILITY_TYPES:
            button = QtWidgets.QPushButton(label)
            button.setObjectName("maroAxisPanelAdd_" + typeName)
            button.clicked.connect(
                lambda checked=False, t=typeName: self._onAddCapabilityClicked(t))
            buttonRow.addWidget(button)
        capColumn.addLayout(buttonRow)

        self._removeButton = QtWidgets.QPushButton("Remove Selected Capability")
        self._removeButton.setObjectName("maroAxisPanelRemoveCapabilityButton")
        self._removeButton.clicked.connect(self._onRemoveCapabilityClicked)
        capColumn.addWidget(self._removeButton)

        layout.addLayout(capColumn)

        self.refreshAxisList()

    def refreshAxisList(self):
        """씬의 maroAxis 전체를 다시 읽어 왼쪽 목록을 채운다."""
        self._axisList.clear()
        for row in sliceAxisRows(cmds.maroListAxisNodes()):
            item = QtWidgets.QListWidgetItem(
                "{} ({})".format(row["axisFullPath"], row["jointName"] or "-"))
            item.setData(QtCore.Qt.UserRole, row["axisFullPath"])
            self._axisList.addItem(item)

    def selectAxis(self, axisFullPath):
        """다른 곳(씬 선택 등)에서 축이 정해졌을 때 패널을 그 축에 맞춘다.
        Task 9의 SelectionChanged 동기화가 이걸 부른다."""
        self._selectedAxis = axisFullPath
        self._refreshCapabilityList()

    def _refreshCapabilityList(self):
        self._capList.clear()
        if not self._selectedAxis or not cmds.objExists(self._selectedAxis):
            return
        for row in sliceCapabilityRows(
                cmds.maroListAxisNodes(capabilities=self._selectedAxis)):
            item = QtWidgets.QListWidgetItem(
                "[{}] {} ({})".format(
                    row["logicalIndex"], row["capabilityNodeType"],
                    row["capabilityNodeName"] or "disconnected"))
            item.setData(QtCore.Qt.UserRole, row["logicalIndex"])
            self._capList.addItem(item)

    def _onAxisRowClicked(self, item):
        axisFullPath = item.data(QtCore.Qt.UserRole)
        self._selectedAxis = axisFullPath
        self._refreshCapabilityList()
        # 양방향 동기화(설계 스펙 §9): 패널에서 축을 고르면 씬 선택도 바꾼다.
        # 바인딩된 타겟이 있으면 그것을, 없으면 축 자신을 선택한다.
        rows = [r for r in sliceAxisRows(cmds.maroListAxisNodes())
                if r["axisFullPath"] == axisFullPath]
        target = rows[0]["boundTargetPath"] if rows and rows[0]["boundTargetPath"] else axisFullPath
        cmds.select(target, replace=True)

    def _onAddCapabilityClicked(self, typeName):
        if not self._selectedAxis:
            return
        try:
            cmds.maroAddCapability(self._selectedAxis, type=typeName)
        except RuntimeError as error:
            print("Maro: maroAddCapability failed -- {}".format(error))
            return
        self.refreshAxisList()
        self._refreshCapabilityList()

    def _onRemoveCapabilityClicked(self):
        if not self._selectedAxis:
            return
        item = self._capList.currentItem()
        if item is None:
            return
        try:
            cmds.maroDisconnectCapability(self._selectedAxis, index=item.data(QtCore.Qt.UserRole))
        except RuntimeError as error:
            print("Maro: maroDisconnectCapability failed -- {}".format(error))
            return
        self.refreshAxisList()
        self._refreshCapabilityList()

    def _onUnbindClicked(self):
        if not self._selectedAxis:
            return
        try:
            cmds.maroUnbindAxis(self._selectedAxis)
        except RuntimeError as error:
            print("Maro: maroUnbindAxis failed -- {}".format(error))
            return
        self.refreshAxisList()


def buildWidget():
    """maroMainWindow.buildUI()가 editorHost에 임베드할 위젯을 만든다."""
    return AxisPanel()
