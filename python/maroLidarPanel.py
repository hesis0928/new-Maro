"""LiDAR 설정 팝업 -- maroLidar 노드 하나를 설정하는 독립 최상위 창(설계
스펙 §5.3).

maroSingleObjectNodeEditor.py(SONE)와 같은 패턴이다: 노드의 풀 DAG 경로를
키로 삼는 _OPEN_EDITORS 싱글톤, stop()이 플러그인 언로드 시 전부 닫음
(maroMainWindow.teardown()에 등록). LiDAR는 ONE에는 참여하지 않는다 -- 축이
아니므로 GSON 그리드에 낄 자리가 없고, 이 팝업 하나로 완결된다.
"""
import maya.cmds as cmds
from PySide6 import QtCore, QtWidgets

# (필드 이름, 표시 라벨, 위젯 종류). "angle" 종류는 cmds.getAttr/setAttr이
# 라디안으로 주고받는다는 것을 그대로 노출한다(변환은 이번 범위 밖).
_ATTRS = [
    ("verticalSamples", "Vertical samples", "int"),
    ("verticalMinAngle", "Vertical min angle (rad)", "float"),
    ("verticalMaxAngle", "Vertical max angle (rad)", "float"),
    ("horizontalSamples", "Horizontal samples", "int"),
    ("horizontalMinAngle", "Horizontal min angle (rad)", "float"),
    ("horizontalMaxAngle", "Horizontal max angle (rad)", "float"),
    ("rangeMin", "Range min (m)", "float"),
    ("rangeMax", "Range max (m)", "float"),
    ("updateRate", "Update rate (Hz)", "float"),
    ("frameId", "Frame id", "string"),
    ("enabled", "Enabled", "bool"),
]

_OPEN_EDITORS = {}  # lidarFullPath -> MaroLidarPanel


def openLidarPanel(lidar):
    """lidar의 설정 팝업을 연다. 이미 열려 있으면 그 창을 앞으로 가져온다."""
    existing = _OPEN_EDITORS.get(lidar)
    if existing is not None:
        try:
            existing.raise_()
            existing.activateWindow()
            return existing
        except RuntimeError:
            del _OPEN_EDITORS[lidar]

    panel = MaroLidarPanel(lidar)
    _OPEN_EDITORS[lidar] = panel
    panel.show()
    return panel


def stop():
    """플러그인 언로드/창 닫힘 시 열려 있는 LiDAR 설정 팝업을 전부 닫는다.
    maroSingleObjectNodeEditor.stop()과 같은 규율로 한 창의 실패가 나머지
    창의 정리를 막지 않게 한다."""
    for panel in list(_OPEN_EDITORS.values()):
        try:
            panel.close()
            panel.deleteLater()
        except Exception:  # noqa: BLE001 -- 언로드 정리 경계
            import traceback
            traceback.print_exc()
    _OPEN_EDITORS.clear()


def _pairedPointCloud(lidar):
    """lidar가 만든(aSourceLidar로 연결된) maroPointCloud, 없으면 None."""
    connections = cmds.listConnections(
        lidar, type="maroPointCloud", plugs=False, shapes=True) or []
    if not connections:
        return None
    return cmds.ls(connections[0], long=True)[0]


class MaroLidarPanel(QtWidgets.QWidget):
    """maroLidar 노드 하나의 설정 폼. setStyleSheet()를 부르지 않는다."""

    def __init__(self, lidar, parent=None):
        super().__init__(parent, QtCore.Qt.Window)
        self._lidar = lidar
        self.setWindowTitle(lidar.split("|")[-1])

        layout = QtWidgets.QFormLayout(self)
        self._fields = {}
        for attrName, label, kind in _ATTRS:
            field = self._makeField(kind)
            layout.addRow(label, field)
            self._fields[attrName] = (field, kind)
        self._loadValues()

        self._meshList = QtWidgets.QListWidget()
        layout.addRow("Target meshes", self._meshList)
        meshButtons = QtWidgets.QHBoxLayout()
        addMeshButton = QtWidgets.QPushButton("타겟 메쉬 추가")
        addMeshButton.clicked.connect(self._onAddTargetMesh)
        removeMeshButton = QtWidgets.QPushButton("선택 제거")
        removeMeshButton.clicked.connect(self._onRemoveTargetMesh)
        meshButtons.addWidget(addMeshButton)
        meshButtons.addWidget(removeMeshButton)
        layout.addRow(meshButtons)
        self._refreshMeshList()

        applyButton = QtWidgets.QPushButton("적용")
        applyButton.clicked.connect(self._onApply)
        layout.addRow(applyButton)

        scanButton = QtWidgets.QPushButton("Scan now")
        scanButton.clicked.connect(self._onScanNow)
        layout.addRow(scanButton)

    def closeEvent(self, event):
        try:
            if _OPEN_EDITORS.get(self._lidar) is self:
                del _OPEN_EDITORS[self._lidar]
        except Exception:  # noqa: BLE001 -- Qt 이벤트 핸들러 경계
            import traceback
            traceback.print_exc()
        super().closeEvent(event)

    def _makeField(self, kind):
        if kind == "bool":
            return QtWidgets.QCheckBox()
        if kind == "int":
            field = QtWidgets.QSpinBox()
            field.setRange(1, 100000)
            return field
        if kind == "string":
            return QtWidgets.QLineEdit()
        field = QtWidgets.QDoubleSpinBox()
        field.setRange(-100000.0, 100000.0)
        field.setDecimals(4)
        return field

    def _loadValues(self):
        if not cmds.objExists(self._lidar):
            return
        for attrName, (field, kind) in self._fields.items():
            plugName = self._lidar + "." + attrName
            if kind == "bool":
                field.setChecked(bool(cmds.getAttr(plugName)))
            elif kind == "string":
                field.setText(cmds.getAttr(plugName) or "")
            else:
                field.setValue(cmds.getAttr(plugName))

    def _onApply(self):
        try:
            cmds.undoInfo(openChunk=True)
            for attrName, (field, kind) in self._fields.items():
                plugName = self._lidar + "." + attrName
                if kind == "bool":
                    cmds.setAttr(plugName, field.isChecked())
                elif kind == "string":
                    cmds.setAttr(plugName, field.text(), type="string")
                else:
                    cmds.setAttr(plugName, field.value())
        except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
            cmds.warning("Maro: failed to apply LiDAR settings: {}".format(exc))
        finally:
            cmds.undoInfo(closeChunk=True)

    def _refreshMeshList(self):
        self._meshList.clear()
        if not cmds.objExists(self._lidar):
            return
        connections = cmds.listConnections(
            self._lidar + ".targetMeshes", source=True, destination=False, shapes=False) or []
        for mesh in connections:
            self._meshList.addItem(cmds.ls(mesh, long=True)[0])

    def _onAddTargetMesh(self):
        # [I-4] _refreshMeshList()는 cmds.objExists/listConnections/ls(...)[0]를
        # 아무 가드 없이 부른다. 예전에는 이 try/except 블록 "밖"에서 호출돼서
        # 거기서 던지는 예외가 Qt 버튼 클릭 콜백 밖으로 그대로 샜다 -- 이
        # 파일의 다른 핸들러(_onApply, _onScanNow)와 같은 "Qt 이벤트 핸들러
        # 경계 밖으로 예외를 절대 내보내지 않는다" 규율을 어기는 것이었다.
        # 그래서 최초의 selection 읽기부터 마지막 _refreshMeshList() 호출까지
        # 함수 본문 전체를 하나의 try/except로 감싼다.
        try:
            cmds.undoInfo(openChunk=True)
            selection = cmds.ls(selection=True, long=True) or []
            if not selection:
                cmds.warning("Maro: select a mesh to add as a LiDAR target first.")
                return
            usedIndices = set(cmds.getAttr(
                self._lidar + ".targetMeshes", multiIndices=True) or [])
            nextIndex = 0
            while nextIndex in usedIndices:
                nextIndex += 1
            cmds.connectAttr(
                selection[0] + ".message",
                "{}.targetMeshes[{}]".format(self._lidar, nextIndex))
        except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
            cmds.warning("Maro: failed to add target mesh: {}".format(exc))
        finally:
            cmds.undoInfo(closeChunk=True)
            # _refreshMeshList() 자신도 무가드로 cmds를 부르므로(위 주석)
            # 별도로 감싼다 -- finally 안에서 새는 예외는 위 except가 못
            # 잡는다(그 except는 try 블록에서 난 예외만 담당한다).
            try:
                self._refreshMeshList()
            except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
                cmds.warning("Maro: failed to refresh target mesh list: {}".format(exc))

    def _onRemoveTargetMesh(self):
        # [I-4] 위 _onAddTargetMesh와 같은 이유로 currentItem()/item.text()
        # 읽기부터 마지막 _refreshMeshList() 호출까지 전체를 감싼다.
        try:
            cmds.undoInfo(openChunk=True)
            item = self._meshList.currentItem()
            if item is None:
                return
            meshFullPath = item.text()
            pairs = cmds.listConnections(
                self._lidar + ".targetMeshes", connections=True, plugs=True,
                source=True, destination=False) or []
            # pairs는 [destPlug0, srcPlug0, destPlug1, srcPlug1, ...] 순서다.
            for i in range(0, len(pairs), 2):
                destPlug, srcPlug = pairs[i], pairs[i + 1]
                sourceNode = cmds.ls(srcPlug.split(".")[0], long=True)[0]
                if sourceNode == meshFullPath:
                    cmds.disconnectAttr(srcPlug, destPlug)
                    break
        except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
            cmds.warning("Maro: failed to remove target mesh: {}".format(exc))
        finally:
            cmds.undoInfo(closeChunk=True)
            # _refreshMeshList() 자신도 무가드로 cmds를 부르므로(위 주석)
            # 별도로 감싼다 -- finally 안에서 새는 예외는 위 except가 못
            # 잡는다(그 except는 try 블록에서 난 예외만 담당한다).
            try:
                self._refreshMeshList()
            except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
                cmds.warning("Maro: failed to refresh target mesh list: {}".format(exc))

    def _onScanNow(self):
        try:
            pointCloud = _pairedPointCloud(self._lidar)
            if pointCloud is None:
                cmds.warning(
                    "Maro: this LiDAR has no connected maroPointCloud to snapshot into.")
                return
            cmds.maroSnapshotLidarScan(self._lidar, pointCloud)
        except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
            cmds.warning("Maro: scan failed: {}".format(exc))
