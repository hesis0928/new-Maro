"""Maro 환경설정 -- ROS 연결 값(domain ID/robotName)과 Tech Diag 리밋 근접
경고 임계값을 Maya의 optionVar에 영구 저장한다(이 코드베이스 최초의
cmds.optionVar 사용).

아래 읽기/쓰기 함수는 Qt와 무관한 순수 함수다 -- mayapy 배치에서 QWidget
없이 검증 가능하다. UI 클래스(MaroSettingsPanel)는 다음 태스크에서 이
파일에 추가된다.
"""
import os

import maya.cmds as cmds
from PySide6 import QtCore, QtWidgets

_ROBOT_NAME_VAR = "maroSettingRosRobotName"
_DOMAIN_OVERRIDE_VAR = "maroSettingRosDomainIdOverride"
_DOMAIN_ID_VAR = "maroSettingRosDomainId"
_TECH_DIAG_THRESHOLD_VAR = "maroSettingTechDiagLimitProximityThreshold"

_DEFAULT_ROBOT_NAME = ""
_DEFAULT_DOMAIN_OVERRIDE = False
_DEFAULT_DOMAIN_ID = 0
_DEFAULT_TECH_DIAG_THRESHOLD = 0.9


def readRosSettings():
    """(robotName, domainIdOverrideEnabled, domainId) 튜플을 optionVar에서
    읽는다. 저장된 적 없으면 각각 기본값을 돌려준다."""
    robotName = (cmds.optionVar(query=_ROBOT_NAME_VAR)
                 if cmds.optionVar(exists=_ROBOT_NAME_VAR) else _DEFAULT_ROBOT_NAME)
    domainOverride = (bool(cmds.optionVar(query=_DOMAIN_OVERRIDE_VAR))
                       if cmds.optionVar(exists=_DOMAIN_OVERRIDE_VAR)
                       else _DEFAULT_DOMAIN_OVERRIDE)
    domainId = (cmds.optionVar(query=_DOMAIN_ID_VAR)
                if cmds.optionVar(exists=_DOMAIN_ID_VAR) else _DEFAULT_DOMAIN_ID)
    return robotName, domainOverride, domainId


def writeRosSettings(robotName, domainIdOverrideEnabled, domainId):
    """세 값을 optionVar에 쓴다."""
    cmds.optionVar(stringValue=(_ROBOT_NAME_VAR, robotName))
    cmds.optionVar(intValue=(_DOMAIN_OVERRIDE_VAR, 1 if domainIdOverrideEnabled else 0))
    cmds.optionVar(intValue=(_DOMAIN_ID_VAR, int(domainId)))


def readTechDiagThreshold():
    """리밋 근접 임계값(0.0-1.0)을 optionVar에서 읽는다. 없으면 0.9."""
    if cmds.optionVar(exists=_TECH_DIAG_THRESHOLD_VAR):
        return cmds.optionVar(query=_TECH_DIAG_THRESHOLD_VAR)
    return _DEFAULT_TECH_DIAG_THRESHOLD


def writeTechDiagThreshold(value):
    """리밋 근접 임계값을 optionVar에 쓴다."""
    cmds.optionVar(floatValue=(_TECH_DIAG_THRESHOLD_VAR, float(value)))


_OPEN_PANEL = None  # 열려 있는 MaroSettingsPanel 인스턴스, 없으면 None


def show():
    """maroMenu.py의 "환경설정..." 항목이 부른다. 이미 열려 있으면 앞으로
    가져온다."""
    global _OPEN_PANEL
    if _OPEN_PANEL is not None:
        try:
            _OPEN_PANEL.raise_()
            _OPEN_PANEL.activateWindow()
            return _OPEN_PANEL
        except RuntimeError:
            _OPEN_PANEL = None

    _OPEN_PANEL = MaroSettingsPanel()
    _OPEN_PANEL.show()
    return _OPEN_PANEL


def stop():
    """플러그인 언로드 시 열려 있는 설정 창을 닫는다. 한 번도 안 열렸어도
    안전한 무동작."""
    global _OPEN_PANEL
    if _OPEN_PANEL is not None:
        try:
            _OPEN_PANEL.close()
            _OPEN_PANEL.deleteLater()
        except Exception:  # noqa: BLE001 -- 언로드 정리 경계
            import traceback
            traceback.print_exc()
        _OPEN_PANEL = None


class MaroSettingsPanel(QtWidgets.QWidget):
    """Maro 환경설정 창. setStyleSheet()를 부르지 않는다."""

    def __init__(self, parent=None):
        super().__init__(parent, QtCore.Qt.Window)
        self.setWindowTitle("Maro 환경설정")

        layout = QtWidgets.QVBoxLayout(self)

        rosGroup = QtWidgets.QGroupBox("ROS 연결")
        rosForm = QtWidgets.QFormLayout(rosGroup)
        self._robotNameField = QtWidgets.QLineEdit()
        rosForm.addRow("robotName", self._robotNameField)
        self._domainOverrideCheck = QtWidgets.QCheckBox("도메인 ID 직접 지정")
        rosForm.addRow(self._domainOverrideCheck)
        self._domainIdField = QtWidgets.QSpinBox()
        self._domainIdField.setRange(0, 232)
        rosForm.addRow("도메인 ID", self._domainIdField)
        self._domainOverrideCheck.toggled.connect(self._domainIdField.setEnabled)
        rosButtons = QtWidgets.QHBoxLayout()
        connectButton = QtWidgets.QPushButton("연결")
        connectButton.clicked.connect(self._onConnect)
        disconnectButton = QtWidgets.QPushButton("연결 해제")
        disconnectButton.clicked.connect(self._onDisconnect)
        rosButtons.addWidget(connectButton)
        rosButtons.addWidget(disconnectButton)
        rosForm.addRow(rosButtons)
        rosForm.addRow(QtWidgets.QLabel("연결 버튼을 누르면 즉시 적용됩니다."))
        layout.addWidget(rosGroup)

        techDiagGroup = QtWidgets.QGroupBox("Tech Diag")
        techDiagForm = QtWidgets.QFormLayout(techDiagGroup)
        self._thresholdField = QtWidgets.QSpinBox()
        self._thresholdField.setRange(0, 100)
        self._thresholdField.setSuffix("%")
        techDiagForm.addRow("리밋 근접 경고 임계값", self._thresholdField)
        saveThresholdButton = QtWidgets.QPushButton("저장")
        saveThresholdButton.clicked.connect(self._onSaveThreshold)
        techDiagForm.addRow(saveThresholdButton)
        techDiagForm.addRow(QtWidgets.QLabel("다음 검사 실행부터 즉시 적용됩니다."))
        layout.addWidget(techDiagGroup)

        self._loadValues()

    def _loadValues(self):
        robotName, domainOverride, domainId = readRosSettings()
        self._robotNameField.setText(robotName)
        self._domainOverrideCheck.setChecked(domainOverride)
        self._domainIdField.setValue(domainId)
        self._domainIdField.setEnabled(domainOverride)
        self._thresholdField.setValue(int(round(readTechDiagThreshold() * 100)))

    def _onConnect(self):
        try:
            robotName = self._robotNameField.text()
            if not robotName:
                cmds.warning("Maro: enter a robot name before connecting.")
                return
            overrideEnabled = self._domainOverrideCheck.isChecked()
            domainId = self._domainIdField.value()
            writeRosSettings(robotName, overrideEnabled, domainId)
            if overrideEnabled:
                os.environ["ROS_DOMAIN_ID"] = str(domainId)
            cmds.maroStartBridge(robotName)
        except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
            cmds.warning("Maro: failed to connect: {}".format(exc))

    def _onDisconnect(self):
        try:
            cmds.maroStopBridge()
        except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
            cmds.warning("Maro: failed to disconnect: {}".format(exc))

    def _onSaveThreshold(self):
        try:
            writeTechDiagThreshold(self._thresholdField.value() / 100.0)
        except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
            cmds.warning("Maro: failed to save Tech Diag threshold: {}".format(exc))

    def closeEvent(self, event):
        global _OPEN_PANEL
        if _OPEN_PANEL is self:
            _OPEN_PANEL = None
        super().closeEvent(event)
