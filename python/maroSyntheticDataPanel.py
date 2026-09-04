"""합성 데이터(RGB+Depth+Normal+포인트클라우드) 렌더링 패널. 카메라 선택/
생성, 출력 경로 지정, "렌더 지금" 버튼 하나로 Arnold 렌더 + depth 역투영
전체 흐름을 실행한다. setStyleSheet()를 부르지 않는다."""
import os

import maya.cmds as cmds
from PySide6 import QtCore, QtWidgets

import maroSyntheticDataCamera as sdc
import maroSyntheticDataPointCloud as sdpc
import maroSyntheticDataRender as sdr

_OPEN_PANEL = None


def show():
    """maroMenu.py의 "합성 데이터 렌더..." 항목이 부른다."""
    global _OPEN_PANEL
    if _OPEN_PANEL is not None:
        try:
            _OPEN_PANEL.raise_()
            _OPEN_PANEL.activateWindow()
            return _OPEN_PANEL
        except RuntimeError:
            _OPEN_PANEL = None

    _OPEN_PANEL = MaroSyntheticDataPanel()
    _OPEN_PANEL.show()
    return _OPEN_PANEL


def stop():
    """플러그인 언로드 시 열려 있는 패널을 닫는다. 한 번도 안 열렸어도
    안전한 무동작(maroSettingsPanel.stop()과 같은 이유, 같은 패턴 --
    close()가 closeEvent를 동기 실행해 전역을 먼저 지우므로 로컬 참조를
    먼저 잡아 둔다)."""
    global _OPEN_PANEL
    if _OPEN_PANEL is None:
        return
    panel = _OPEN_PANEL
    try:
        panel.close()
        panel.deleteLater()
    except Exception:  # noqa: BLE001 -- 언로드 정리 경계
        import traceback
        traceback.print_exc()
    _OPEN_PANEL = None


class MaroSyntheticDataPanel(QtWidgets.QWidget):
    """합성 데이터 렌더링 창."""

    def __init__(self, parent=None):
        super().__init__(parent, QtCore.Qt.Window)
        self.setWindowTitle("Maro 합성 데이터 렌더")

        layout = QtWidgets.QVBoxLayout(self)

        cameraRow = QtWidgets.QHBoxLayout()
        self._cameraCombo = QtWidgets.QComboBox()
        cameraRow.addWidget(self._cameraCombo)
        newCameraButton = QtWidgets.QPushButton("새로 만들기")
        newCameraButton.clicked.connect(self._onNewCamera)
        cameraRow.addWidget(newCameraButton)
        layout.addLayout(cameraRow)

        outputRow = QtWidgets.QHBoxLayout()
        self._outputDirField = QtWidgets.QLineEdit()
        outputRow.addWidget(self._outputDirField)
        browseButton = QtWidgets.QPushButton("찾아보기...")
        browseButton.clicked.connect(self._onBrowse)
        outputRow.addWidget(browseButton)
        layout.addLayout(outputRow)

        self._frameLabel = QtWidgets.QLabel()
        layout.addWidget(self._frameLabel)

        renderButton = QtWidgets.QPushButton("렌더 지금")
        renderButton.clicked.connect(self._onRenderNow)
        layout.addWidget(renderButton)

        self._statusLabel = QtWidgets.QLabel("")
        layout.addWidget(self._statusLabel)

        self._refreshCameraList()
        self._refreshFrameLabel()

    def _refreshCameraList(self):
        self._cameraCombo.clear()
        self._cameraCombo.addItems(sdc.listSyntheticDataCameras())

    def _refreshFrameLabel(self):
        self._frameLabel.setText("현재 프레임: {}".format(int(cmds.currentTime(query=True))))

    def _onNewCamera(self):
        try:
            newCam = sdc.createSyntheticDataCamera()
            self._refreshCameraList()
            index = self._cameraCombo.findText(newCam)
            if index >= 0:
                self._cameraCombo.setCurrentIndex(index)
        except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
            self._statusLabel.setText("카메라 생성 실패: {}".format(exc))

    def _onBrowse(self):
        result = cmds.fileDialog2(fileMode=3, caption="출력 디렉터리 선택")
        if result:
            self._outputDirField.setText(result[0])

    def _onRenderNow(self):
        camera = self._cameraCombo.currentText()
        outputDir = self._outputDirField.text()
        if not camera:
            self._statusLabel.setText("카메라를 선택하거나 새로 만드세요.")
            return
        if not outputDir:
            self._statusLabel.setText("출력 디렉터리를 지정하세요.")
            return

        self._statusLabel.setText("렌더링 중...")
        QtWidgets.QApplication.processEvents()
        try:
            paths = sdr.renderSyntheticFrame(camera, outputDir)

            self._statusLabel.setText("Depth 역투영 중...")
            QtWidgets.QApplication.processEvents()

            width = cmds.getAttr(camera + ".outputResolutionWidth")
            height = cmds.getAttr(camera + ".outputResolutionHeight")
            cameraShape = cmds.listRelatives(camera, shapes=True, fullPath=True)[0]
            intrinsics = sdpc.computeCameraIntrinsics(
                focalLengthMm=cmds.getAttr(cameraShape + ".focalLength"),
                horizontalFilmApertureIn=cmds.getAttr(cameraShape + ".horizontalFilmAperture"),
                verticalFilmApertureIn=cmds.getAttr(cameraShape + ".verticalFilmAperture"),
                widthPx=width, heightPx=height)

            pfmPath = os.path.splitext(paths["depth"])[0] + ".pfm"
            sdpc.convertExrToPfm(paths["depth"], pfmPath)
            _w, _h, depthData = sdpc.parsePfm(pfmPath)

            import maya.api.OpenMaya as om2
            sel = om2.MSelectionList()
            sel.add(camera)
            worldMatrix = sel.getDagPath(0).inclusiveMatrix()
            # MMatrix isn't callable as matrix(r, c) on this Maya version's
            # API 2.0 (verified in maroSyntheticDataRender.buildCalibrationDict:
            # TypeError: 'OpenMaya.MMatrix' object is not callable) -- it's
            # iterable/indexable instead, yielding its 16 elements in
            # row-major order. The brief's original code used the callable
            # form; fixed here to match the verified-working pattern.
            matrixFlat = list(worldMatrix)

            points = sdpc.unprojectDepthToPoints(
                depthData, width, height, intrinsics, matrixFlat)

            plyPath = os.path.splitext(paths["depth"])[0] + "_points.ply"
            sdpc.writePly(points, plyPath)
            sdpc.updatePointCloudNode(points)

            self._statusLabel.setText(
                "완료: {}개 점, {}".format(len(points), plyPath))
        except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
            self._statusLabel.setText("렌더링 실패: {}".format(exc))

    def closeEvent(self, event):
        global _OPEN_PANEL
        if _OPEN_PANEL is self:
            _OPEN_PANEL = None
        super().closeEvent(event)
