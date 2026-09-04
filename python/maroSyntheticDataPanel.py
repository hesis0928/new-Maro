"""합성 데이터(RGB+Depth+Normal+포인트클라우드) 렌더링 패널. 카메라 선택/
생성, 출력 경로 지정, "렌더 지금" 버튼 하나로 Arnold 렌더 + depth 역투영
전체 흐름을 실행한다. setStyleSheet()를 부르지 않는다."""
import json
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

        # 렌더마다 새 maroPointCloud 노드를 만드는 대신 이걸 재사용/갱신한다
        # (updatePointCloudNode()가 None/유효하지 않은 이름을 만나면 알아서
        # 새로 만들어 준다 -- 최초 렌더 전이나 노드가 씬에서 지워진 뒤에도
        # 안전).
        self._pointCloudNode = None

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
        # 사용자가 렌더 버튼을 누르기 전에 타임라인을 스크럽했을 수 있다 --
        # __init__에서만 채워진 라벨은 그동안 낡은 값을 보여준다. 실제로
        # 렌더되는 프레임은 언제나 cmds.currentTime()의 라이브 값이므로(이
        # 갱신이 그 자체를 바꾸지는 않는다), 여기서 다시 그려 라벨을 최신
        # 상태로 맞춘다.
        self._refreshFrameLabel()

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

            # renderSyntheticFrame()이 이미 써 둔 calibration JSON을 다시
            # 읽어 그 값을 그대로 쓴다 -- 렌더 직후 여기까지 오는 사이의
            # processEvents() 호출이 사용자에게 씬(카메라 포함)을 건드릴
            # 여지를 주므로, 여기서 카메라를 다시 조회해 외부 파라미터를
            # 재유도하면 실제로 렌더된 프레임과 어긋나는 값을 쓸 위험이
            # 있다(레이스 컨디션). calibration JSON은 이 기능 자신이 이미
            # 만들어 둔 문서화된 출력물이므로 그것을 그대로 소비하는 것이
            # 맞다(설계 스펙 §7 "다시 유도하지 않고 그대로 씀" 원칙과 동일).
            with open(paths["calibration"]) as f:
                calibration = json.load(f)

            intrinsics = sdpc.computeCameraIntrinsics(
                focalLengthMm=calibration["focalLength"],
                horizontalFilmApertureIn=calibration["horizontalFilmAperture"],
                verticalFilmApertureIn=calibration["verticalFilmAperture"],
                widthPx=calibration["resolutionWidth"],
                heightPx=calibration["resolutionHeight"])

            pfmPath = os.path.splitext(paths["depth"])[0] + ".pfm"
            sdpc.convertExrToPfm(paths["depth"], pfmPath)
            renderedWidth, renderedHeight, depthData = sdpc.parsePfm(pfmPath)

            # parsePfm()이 실제로 읽어 온 이미지 크기가 렌더에 실제로 쓰인
            # (calibration에 기록된) 해상도와 다르면, unprojectDepthToPoints()가
            # depthData[row*width+col]을 다른 모양의 버퍼에 대고 읽어 조용히
            # 스크램블된 포인트클라우드를 만들 수 있다 -- 둘 중 아무 값이나
            # 골라 쓰지 않고 불일치 자체를 에러로 드러낸다.
            if (renderedWidth != calibration["resolutionWidth"] or
                    renderedHeight != calibration["resolutionHeight"]):
                raise RuntimeError(
                    "렌더된 depth 이미지 크기({}x{})가 캘리브레이션에 기록된 "
                    "해상도({}x{})와 다릅니다.".format(
                        renderedWidth, renderedHeight,
                        calibration["resolutionWidth"],
                        calibration["resolutionHeight"]))

            points = sdpc.unprojectDepthToPoints(
                depthData, renderedWidth, renderedHeight, intrinsics,
                calibration["worldMatrix"])

            plyPath = os.path.splitext(paths["depth"])[0] + "_points.ply"
            sdpc.writePly(points, plyPath)
            # 매번 새 maroPointCloud 노드를 만드는 대신 이전 렌더의 노드를
            # 재사용/갱신한다 -- updatePointCloudNode()는 self._pointCloudNode가
            # None이거나 씬에서 지워졌으면 알아서 새로 만든다.
            self._pointCloudNode = sdpc.updatePointCloudNode(
                points, pointCloudNode=self._pointCloudNode)

            self._statusLabel.setText(
                "완료: {}개 점, {}".format(len(points), plyPath))
        except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
            self._statusLabel.setText("렌더링 실패: {}".format(exc))

    def closeEvent(self, event):
        global _OPEN_PANEL
        if _OPEN_PANEL is self:
            _OPEN_PANEL = None
        super().closeEvent(event)
