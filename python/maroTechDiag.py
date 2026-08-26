"""테크 Diag -- 기구학/ROS 정합성 능동 검증 (설계 스펙 2026-08-26-maro-tech-diag-design.md).

기존 boad/book 디버깅 Diag와 완전히 독립된 서브시스템이다. 새 C++ 커맨드나
DG 어트리뷰트 없이 기존 maroListAxisNodes 조회 + cmds.getAttr만으로 동작한다.
검사 결과는 실행할 때마다 새로 계산되고 저장되지 않는다.

이 파일의 순수 함수는 Maya에 의존하지 않는다 -- mayapy 배치 모드에서 QWidget
없이 계약을 검증한다.
"""

import itertools

import maya.cmds as cmds
from PySide6 import QtWidgets

LIMIT_PROXIMITY_THRESHOLD = 0.9

# C++ 쪽 계약. maroObjectNodeEditor.py/maroSingleObjectNodeEditor.py도 각자
# 독립적으로 같은 값을 선언한다 -- 순환 import를 피하기 위한 이 프로젝트의
# 기존 관례.
AXIS_FIELDS = 10
CAPABILITY_FIELDS = 5


def sliceAxisTechRows(flat):
    """maroListAxisNodes()의 평탄한 배열에서 이 모듈이 필요로 하는 필드만
    뽑아 축 행 딕셔너리 목록으로 되돌린다."""
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
            "enabled": f[5] == "1",
            "conventionAxis": int(f[6]),
            "capabilityCount": int(f[7]),
        })
    return rows


def sliceCapabilityTechRows(flat):
    """maroListAxisNodes(capabilities=axis)의 평탄한 배열에서 이 모듈이
    필요로 하는 필드만 뽑아 capability 행 딕셔너리 목록으로 되돌린다."""
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
            "capType": int(f[3]),
            "connected": f[4] == "1",
        })
    return rows


def checkLimitProximity(axisRows, capabilityRowsByAxis, currentValueByAxis):
    """리밋(capType 1 또는 5)이 있는 축마다, 현재 구동값이 min/max 범위의
    LIMIT_PROXIMITY_THRESHOLD 이상 근접했으면 경고를 낸다. conventionAxis로
    capMin/capMax/capEnable의 X/Y/Z 중 어느 성분이 이 축에 해당하는지 고른다."""
    findings = []
    for axisRow in axisRows:
        axis = axisRow["axisFullPath"]
        currentValue = currentValueByAxis.get(axis)
        if currentValue is None:
            continue
        idx = axisRow["conventionAxis"]
        for capRow in capabilityRowsByAxis.get(axis, []):
            if capRow["capType"] not in (1, 5):
                continue
            if not capRow["capEnable"][idx]:
                continue
            minV = capRow["capMin"][idx]
            maxV = capRow["capMax"][idx]
            span = maxV - minV
            if span <= 0:
                continue
            proximity = (currentValue - minV) / span
            if proximity >= LIMIT_PROXIMITY_THRESHOLD or proximity <= (1.0 - LIMIT_PROXIMITY_THRESHOLD):
                findings.append({
                    "category": "limitProximity",
                    "severity": "warning",
                    "summary": "{}: current value is within {:.0f}% of its limit range".format(
                        axis, (1.0 - LIMIT_PROXIMITY_THRESHOLD) * 100),
                    "axis": axis,
                    "remedy": None,
                })
    return findings


def checkJointStatesIntegrity(axisRows):
    """활성화+바인딩된 축의 jointName 공백/중복, 그리고 활성화됐지만 1차
    구동 capability가 없는 축을 찾는다."""
    findings = []
    seenJointNames = {}
    for row in axisRows:
        if not row["enabled"] or not row["boundTargetPath"]:
            continue
        axis = row["axisFullPath"]
        jointName = row["jointName"]
        if not jointName:
            findings.append({
                "category": "emptyJointName",
                "severity": "warning",
                "summary": "{}: jointName is empty".format(axis),
                "axis": axis,
                "remedy": None,
            })
        else:
            if jointName in seenJointNames:
                findings.append({
                    "category": "duplicateJointName",
                    "severity": "warning",
                    "summary": "{}: jointName '{}' duplicates {}".format(
                        axis, jointName, seenJointNames[jointName]),
                    "axis": axis,
                    "remedy": None,
                })
            else:
                seenJointNames[jointName] = axis
        if row["capabilityCount"] == 0:
            findings.append({
                "category": "noDriverActiveAxis",
                "severity": "warning",
                "summary": "{}: enabled and bound but has no capability driving it".format(axis),
                "axis": axis,
                "remedy": None,
            })
    return findings


def _boxesOverlap(a, b):
    """두 AABB(xmin,ymin,zmin,xmax,ymax,zmax)가 실제로 겹치는지(맞닿기만
    하는 건 제외-- 부등호를 엄격하게 잡는다)."""
    return (a[0] < b[3] and b[0] < a[3] and
            a[1] < b[4] and b[1] < a[4] and
            a[2] < b[5] and b[2] < a[5])


def checkMeshCollisions(boundingBoxesByMesh):
    """모든 메쉬 쌍에 대해 월드 바운딩박스(AABB) 겹침을 검사한다."""
    findings = []
    meshes = sorted(boundingBoxesByMesh.keys())
    for meshA, meshB in itertools.combinations(meshes, 2):
        if _boxesOverlap(boundingBoxesByMesh[meshA], boundingBoxesByMesh[meshB]):
            findings.append({
                "category": "meshCollision",
                "severity": "warning",
                "summary": "{} and {} bounding boxes overlap".format(meshA, meshB),
                "axis": None,
                "meshes": (meshA, meshB),
                "remedy": None,
            })
    return findings


def suggestDisambiguatedJointName(jointName):
    return jointName + "_2"


def suggestJointNameForFill(axis):
    """빈 jointName을 채울 때 제안할 이름 -- 바인딩된 타겟의 짧은 이름."""
    targets = cmds.listConnections(axis + ".targetObject", shapes=False) or []
    if not targets:
        return ""
    return targets[0].split("|")[-1]


def remedyFillEmptyJointName(axis):
    cmds.undoInfo(openChunk=True)
    try:
        cmds.setAttr(axis + ".jointName", suggestJointNameForFill(axis), type="string")
    finally:
        cmds.undoInfo(closeChunk=True)


def remedyRenameDuplicateJointName(axis, suggestedName):
    cmds.undoInfo(openChunk=True)
    try:
        cmds.setAttr(axis + ".jointName", suggestedName, type="string")
    finally:
        cmds.undoInfo(closeChunk=True)


# ---------------------------------------------------------------------------
# 사이드 패널 위젯 (설계 스펙 §5). 위 순수 함수/구제 함수와 같은 파일에
# 둔다 -- maroSingleObjectNodeEditor.py/maroObjectNodeEditor.py가 이미 쓰는
# "서브시스템별로 순수 함수와 그걸 쓰는 위젯을 한 파일에 함께 둔다" 관례를
# 따른다. 배치 mayapy에서는 QWidget 생성 자체가 프로세스를 abort시키므로
# (모듈 도크스트링과 maroMainWindow.py의 도크스트링 참고) 이 아래 클래스/
# 팩토리 함수는 자동 테스트 대상이 아니다 -- 대화형 Maya 수동 체크리스트로만
# 검증한다.
class _CheckSidePanel(QtWidgets.QWidget):
    """Maya측/ROS측 검사 사이드 패널의 공통 뼈대. setStyleSheet()를 부르지
    않는다."""

    def __init__(self, buttonLabel, runCheckFn, parent=None):
        super().__init__(parent)
        self._runCheckFn = runCheckFn
        layout = QtWidgets.QVBoxLayout(self)
        self._runButton = QtWidgets.QPushButton(buttonLabel)
        self._runButton.clicked.connect(self._onRunClicked)
        layout.addWidget(self._runButton)
        self._resultList = QtWidgets.QListWidget()
        layout.addWidget(self._resultList)
        self._findings = []

    def _onRunClicked(self):
        try:
            self._findings = self._runCheckFn()
        except Exception as error:  # noqa: BLE001 -- Qt 콜백 경계, 버튼 클릭마다 도는 코드가 예외를 흘리면 안 됨
            import traceback
            traceback.print_exc()
            self._findings = []
        self._resultList.clear()
        if not self._findings:
            self._resultList.addItem("문제 없음")
            return
        for finding in self._findings:
            item = QtWidgets.QListWidgetItem(finding["summary"])
            self._resultList.addItem(item)
            if finding.get("remedy") is not None:
                applyButton = QtWidgets.QPushButton("적용")
                applyButton.clicked.connect(
                    lambda checked=False, f=finding: self._onApplyRemedy(f))
                itemWidget = QtWidgets.QWidget()
                itemLayout = QtWidgets.QHBoxLayout(itemWidget)
                itemLayout.addWidget(applyButton)
                self._resultList.setItemWidget(item, itemWidget)

    def _onApplyRemedy(self, finding):
        try:
            finding["remedy"]()
        except Exception as error:  # noqa: BLE001 -- 위와 같은 이유
            import traceback
            traceback.print_exc()
            return
        self._onRunClicked()  # 적용 후 다시 검사해서 목록을 갱신


def _runMayaSideChecks():
    axisRows = sliceAxisTechRows(cmds.maroListAxisNodes())
    capsByAxis = {}
    currentValueByAxis = {}
    for row in axisRows:
        axis = row["axisFullPath"]
        capFlat = cmds.maroListAxisNodes(capabilities=axis)
        capRows = []
        for capRow in sliceCapabilityTechRows(capFlat):
            if not capRow["connected"] or capRow["capType"] not in (1, 5):
                continue
            idx = capRow["logicalIndex"]
            capRows.append({
                "logicalIndex": idx,
                "capType": capRow["capType"],
                "capMin": tuple(cmds.getAttr("{}.capabilityIn[{}].capMin".format(axis, idx))[0]),
                "capMax": tuple(cmds.getAttr("{}.capabilityIn[{}].capMax".format(axis, idx))[0]),
                "capEnable": tuple(bool(v) for v in
                                   cmds.getAttr("{}.capabilityIn[{}].capEnable".format(axis, idx))[0]),
            })
        capsByAxis[axis] = capRows
        if row["enabled"] and row["boundTargetPath"]:
            driveIsLinear = cmds.getAttr(axis + ".driveIsLinear")
            currentValueByAxis[axis] = cmds.getAttr(
                axis + (".positionLinear" if driveIsLinear else ".position"))

    findings = checkLimitProximity(axisRows, capsByAxis, currentValueByAxis)

    boundMeshes = [row["boundTargetPath"] for row in axisRows
                   if row["enabled"] and row["boundTargetPath"]]
    boxes = {}
    for mesh in boundMeshes:
        bbox = cmds.exactWorldBoundingBox(mesh)
        boxes[mesh] = tuple(bbox)
    findings += checkMeshCollisions(boxes)
    return findings


def _runRosSideChecks():
    axisRows = sliceAxisTechRows(cmds.maroListAxisNodes())
    findings = checkJointStatesIntegrity(axisRows)
    rowByAxis = {row["axisFullPath"]: row for row in axisRows}
    for finding in findings:
        if finding["category"] == "emptyJointName":
            axis = finding["axis"]
            finding["remedy"] = lambda a=axis: remedyFillEmptyJointName(a)
        elif finding["category"] == "duplicateJointName":
            axis = finding["axis"]
            existingName = rowByAxis[axis]["jointName"]
            suggestion = suggestDisambiguatedJointName(existingName)
            finding["remedy"] = lambda a=axis, s=suggestion: remedyRenameDuplicateJointName(a, s)
    return findings


def buildMayaSidePanel():
    return _CheckSidePanel("Maya 검사 실행", _runMayaSideChecks)


def buildRosSidePanel():
    return _CheckSidePanel("ROS 검사 실행", _runRosSideChecks)
