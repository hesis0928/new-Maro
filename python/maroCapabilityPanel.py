"""capability 노드 7종 각각의 상세 설정 창. 노드 타입별로 클래스를
나눈다(제네릭 1클래스 아님 -- 설계 스펙 2026-09-07 §1). 공통 인프라만
MaroCapabilityPanelBase가 쥐고, 각 서브클래스는 자신의 _ATTRS만 정의한다.

maroLidarPanel.py와 같은 패턴: 노드 풀 경로 키의 _OPEN_EDITORS 싱글톤,
stop()이 플러그인 언로드 시 전부 닫음(maroMainWindow.teardown()에 등록).
"""
import maya.cmds as cmds
from PySide6 import QtCore, QtWidgets

import maroLimitCalibration
import maroSingleObjectNodeEditor

_OPEN_EDITORS = {}  # capabilityNode -> MaroCapabilityPanelBase 서브클래스 인스턴스


def stop():
    """플러그인 언로드/창 닫힘 시 열려 있는 상세 설정 창을 전부 닫는다.
    maroLidarPanel.stop()과 같은 규율로 한 창의 실패가 나머지 창의 정리를
    막지 않게 한다."""
    for panel in list(_OPEN_EDITORS.values()):
        try:
            panel.close()
            panel.deleteLater()
        except Exception:  # noqa: BLE001 -- 언로드 정리 경계
            import traceback
            traceback.print_exc()
    _OPEN_EDITORS.clear()


class MaroCapabilityPanelBase(QtWidgets.QWidget):
    """capability 노드 하나의 설정 폼 공통 인프라. setStyleSheet()를
    부르지 않는다(maroMainWindow.py와 같은 규율). 서브클래스는 클래스
    속성 _ATTRS(리스트의 (attrName, label, kind) 튜플)만 정의하면 된다.
    kind: "bool"/"int"/"float"/"string"/"vec3".
    """

    _ATTRS = []

    def __init__(self, capabilityNode, parent=None):
        super().__init__(parent, QtCore.Qt.Window)
        self._node = capabilityNode
        self.setWindowTitle(capabilityNode.split("|")[-1])

        self._layout = QtWidgets.QFormLayout(self)
        self._fields = {}
        self._vecFields = {}
        for attrName, label, kind in self._ATTRS:
            if kind == "vec3":
                container, subFields = self._makeVec3Field()
                self._layout.addRow(label, container)
                self._vecFields[attrName] = subFields
            else:
                field = self._makeField(kind)
                self._layout.addRow(label, field)
                self._fields[attrName] = (field, kind)

        self._buildExtra()
        self._loadValues()

        applyButton = QtWidgets.QPushButton("적용")
        applyButton.clicked.connect(self._onApply)
        self._layout.addRow(applyButton)

    def _buildExtra(self):
        """서브클래스가 _ATTRS 외 추가 위젯(버튼, 읽기전용 표시 등)을 넣는
        훅. 기본은 무동작."""

    def closeEvent(self, event):
        try:
            if _OPEN_EDITORS.get(self._node) is self:
                del _OPEN_EDITORS[self._node]
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
            import traceback
            traceback.print_exc()
        super().closeEvent(event)

    def _makeField(self, kind):
        if kind == "bool":
            return QtWidgets.QCheckBox()
        if kind == "int":
            field = QtWidgets.QSpinBox()
            field.setRange(-1000000, 1000000)
            return field
        if kind == "string":
            return QtWidgets.QLineEdit()
        field = QtWidgets.QDoubleSpinBox()
        field.setRange(-100000.0, 100000.0)
        field.setDecimals(4)
        return field

    def _makeVec3Field(self):
        container = QtWidgets.QWidget()
        hbox = QtWidgets.QHBoxLayout(container)
        hbox.setContentsMargins(0, 0, 0, 0)
        subFields = []
        for _ in range(3):
            f = QtWidgets.QDoubleSpinBox()
            f.setRange(-1000.0, 1000.0)
            f.setDecimals(6)
            hbox.addWidget(f)
            subFields.append(f)
        return container, subFields

    def _loadValues(self):
        if not cmds.objExists(self._node):
            return
        for attrName, (field, kind) in self._fields.items():
            plugName = self._node + "." + attrName
            if kind == "bool":
                field.setChecked(bool(cmds.getAttr(plugName)))
            elif kind == "string":
                field.setText(cmds.getAttr(plugName) or "")
            else:
                field.setValue(cmds.getAttr(plugName))
        for attrName, subFields in self._vecFields.items():
            plugName = self._node + "." + attrName
            x, y, z = cmds.getAttr(plugName)[0]
            subFields[0].setValue(x)
            subFields[1].setValue(y)
            subFields[2].setValue(z)

    def _onApply(self):
        try:
            cmds.undoInfo(openChunk=True)
            for attrName, (field, kind) in self._fields.items():
                plugName = self._node + "." + attrName
                if kind == "bool":
                    cmds.setAttr(plugName, field.isChecked())
                elif kind == "string":
                    cmds.setAttr(plugName, field.text(), type="string")
                else:
                    cmds.setAttr(plugName, field.value())
            for attrName, subFields in self._vecFields.items():
                plugName = self._node + "." + attrName
                cmds.setAttr(plugName, subFields[0].value(), subFields[1].value(),
                             subFields[2].value(), type="double3")
        except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
            cmds.warning("Maro: failed to apply capability settings: {}".format(exc))
        finally:
            cmds.undoInfo(closeChunk=True)


class MaroRotationPanel(MaroCapabilityPanelBase):
    _ATTRS = [("angle", "Angle (deg)", "float")]


class MaroTranslationPanel(MaroCapabilityPanelBase):
    _ATTRS = [("distance", "Distance", "float")]


class MaroSensorDirectionPanel(MaroCapabilityPanelBase):
    _ATTRS = [("direction", "Direction", "vec3")]


class MaroSensorRangePanel(MaroCapabilityPanelBase):
    _ATTRS = [
        ("range", "Range", "float"),
        ("coneAngle", "Cone angle (deg)", "float"),
    ]


class MaroCouplingPanel(MaroCapabilityPanelBase):
    _ATTRS = [
        ("ratio", "Ratio", "float"),
        ("offset", "Offset", "float"),
        ("outputIsLinear", "Output is linear", "bool"),
    ]

    def _buildExtra(self):
        reconnectButton = QtWidgets.QPushButton("소스 축 재지정")
        reconnectButton.clicked.connect(self._onReconnectSource)
        self._layout.addRow(reconnectButton)

    def _onReconnectSource(self):
        try:
            picker = QtWidgets.QWidget(self, QtCore.Qt.Popup)
            layout = QtWidgets.QVBoxLayout(picker)
            combo = QtWidgets.QComboBox()
            rows = cmds.maroListAxisNodes()
            axisFields = 10  # maroSingleObjectNodeEditor.AXIS_FIELDS와 같은 C++ 계약
            for i in range(len(rows) // axisFields):
                f = rows[i * axisFields:(i + 1) * axisFields]
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
                    maroSingleObjectNodeEditor.connectCouplingSource(self._node, sourceAxis)
                    picker.close()
                except Exception as error:  # noqa: BLE001 -- Qt 콜백 경계
                    print("Maro: coupling source reconnection failed -- {}".format(error))
                    picker.close()

            applyButton.clicked.connect(_onApply)
            picker.move(self.mapToGlobal(QtCore.QPoint(20, 20)))
            picker.show()
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
            import traceback
            traceback.print_exc()


class _AxisLimitPanelBase(MaroCapabilityPanelBase):
    """MaroLimitPanel/MaroTranslationLimitPanel의 공통 부분 -- axisDirection
    필드 옆에 읽기전용 ROS축 표시를 덧붙인다. 실제 _ATTRS(단위: 각도 대
    거리)는 서브클래스가 정의한다."""

    def _buildExtra(self):
        self._rosAxisLabel = QtWidgets.QLabel("")
        self._layout.addRow("ROS axis (read-only)", self._rosAxisLabel)
        self._refreshRosAxisLabel()

    def _refreshRosAxisLabel(self):
        subFields = self._vecFields.get("axisDirection")
        if subFields is None:
            return
        mayaDir = (subFields[0].value(), subFields[1].value(), subFields[2].value())
        rosDir = maroLimitCalibration.mayaDirectionToRos(mayaDir)
        self._rosAxisLabel.setText("({:.4f}, {:.4f}, {:.4f})".format(*rosDir))

    def _onApply(self):
        super()._onApply()
        self._refreshRosAxisLabel()


class MaroLimitPanel(_AxisLimitPanelBase):
    _ATTRS = [
        ("axisDirection", "Axis direction", "vec3"),
        ("min", "Min (deg)", "float"),
        ("max", "Max (deg)", "float"),
    ]


class MaroTranslationLimitPanel(_AxisLimitPanelBase):
    _ATTRS = [
        ("axisDirection", "Axis direction", "vec3"),
        ("min", "Min", "float"),
        ("max", "Max", "float"),
    ]


_PANEL_CLASSES = {
    "maroRotation": MaroRotationPanel,
    "maroTranslation": MaroTranslationPanel,
    "maroSensorDirection": MaroSensorDirectionPanel,
    "maroSensorRange": MaroSensorRangePanel,
    "maroCoupling": MaroCouplingPanel,
    "maroLimit": MaroLimitPanel,
    "maroTranslationLimit": MaroTranslationLimitPanel,
}


def openCapabilityPanel(capabilityNode):
    """capabilityNode(예: "maroLimit1")의 타입에 맞는 상세 설정 창을 연다.
    이미 열려 있으면 그 창을 앞으로 가져온다. 타입이 _PANEL_CLASSES에
    없으면 ValueError."""
    existing = _OPEN_EDITORS.get(capabilityNode)
    if existing is not None:
        try:
            existing.raise_()
            existing.activateWindow()
            return existing
        except RuntimeError:
            del _OPEN_EDITORS[capabilityNode]

    nodeType = cmds.nodeType(capabilityNode)
    panelClass = _PANEL_CLASSES.get(nodeType)
    if panelClass is None:
        raise ValueError(
            "Maro: no capability detail panel registered for node type '{}'".format(nodeType))

    panel = panelClass(capabilityNode)
    _OPEN_EDITORS[capabilityNode] = panel
    panel.show()
    return panel
