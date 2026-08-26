"""테크 Diag -- 기구학/ROS 정합성 능동 검증 (설계 스펙 2026-08-26-maro-tech-diag-design.md).

기존 boad/book 디버깅 Diag와 완전히 독립된 서브시스템이다. 새 C++ 커맨드나
DG 어트리뷰트 없이 기존 maroListAxisNodes 조회 + cmds.getAttr만으로 동작한다.
검사 결과는 실행할 때마다 새로 계산되고 저장되지 않는다.

이 파일의 순수 함수는 Maya에 의존하지 않는다 -- mayapy 배치 모드에서 QWidget
없이 계약을 검증한다.
"""

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
