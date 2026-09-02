"""Maro 환경설정 -- ROS 연결 값(domain ID/robotName)과 Tech Diag 리밋 근접
경고 임계값을 Maya의 optionVar에 영구 저장한다(이 코드베이스 최초의
cmds.optionVar 사용).

아래 읽기/쓰기 함수는 Qt와 무관한 순수 함수다 -- mayapy 배치에서 QWidget
없이 검증 가능하다. UI 클래스(MaroSettingsPanel)는 다음 태스크에서 이
파일에 추가된다.
"""
import maya.cmds as cmds

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
