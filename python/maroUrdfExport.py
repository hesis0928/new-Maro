"""Maro URDF 내보내기 -- maroAxis 체인과 capability 스택으로부터 URDF(XML)를
생성한다(설계 스펙 2026-09-02-maro-urdf-export-design.md).

새 C++ 코드 없음 -- 기존 maroListAxisNodes/cmds.xform/maroMayaToRos만
조합한다. 이 파일 위쪽의 함수들(buildAxisTree/axisVectorForConvention/
jointType/computeRelativeOrigin/buildUrdfXml)은 Maya 씬을 조회하지 않는
순수 함수다 -- mayapy 배치에서 실제 씬 없이 딕셔너리/튜플만으로 검증
가능하다. 씬을 조회하는 부분과 UI 배선은 이 파일 아래쪽(Task 4)에서
추가된다.
"""


def buildAxisTree(axisRows):
    """axisRows: 각 항목이 최소 "axisFullPath"/"parentAxisPath"/"jointName"
    키를 갖는 딕셔너리 목록(maroListAxisNodes()를 슬라이스한 것).

    (rootAxisFullPath, childrenByParent) 튜플을 돌려준다. childrenByParent는
    parentAxisPath -> [axisFullPath, ...] 매핑이다(부모가 없는 축은 이
    매핑에 나타나지 않는다 -- 그게 곧 루트).

    부모가 빈 축이 정확히 하나가 아니면 ValueError. jointName이 빈 축이
    있으면 ValueError(어느 축인지 메시지에 포함).
    """
    roots = [row["axisFullPath"] for row in axisRows if not row["parentAxisPath"]]
    if len(roots) != 1:
        raise ValueError(
            "expected exactly one root axis (no parentAxisPath), found {}: {}".format(
                len(roots), roots))

    emptyJointNames = [row["axisFullPath"] for row in axisRows if not row["jointName"]]
    if emptyJointNames:
        raise ValueError(
            "every axis needs a non-empty jointName before URDF export, missing on: {}".format(
                emptyJointNames))

    childrenByParent = {}
    for row in axisRows:
        parent = row["parentAxisPath"]
        if parent:
            childrenByParent.setdefault(parent, []).append(row["axisFullPath"])

    return roots[0], childrenByParent


_AXIS_VECTORS = {0: (1.0, 0.0, 0.0), 1: (0.0, 1.0, 0.0), 2: (0.0, 0.0, 1.0)}


def axisVectorForConvention(conventionAxis):
    """conventionAxis(0=X 1=Y 2=Z)를 관절 프레임 안에서의 단위 축 벡터로
    바꾼다. origin이 이미 로케이터의 자세를 관절 프레임으로 확정하므로
    별도 좌표 변환이 필요 없다(설계 스펙 §3.3)."""
    if conventionAxis not in _AXIS_VECTORS:
        raise ValueError("conventionAxis must be 0, 1, or 2, got {}".format(conventionAxis))
    return _AXIS_VECTORS[conventionAxis]


def jointType(capabilityRows):
    """capabilityRows: 이 축 하나의 capability 목록. 각 항목은 최소
    "capType"(int, 0=rotation 1=limit 4=translation 5=translationLimit
    6=coupling-각도 7=coupling-선형) 키를 갖는다. capType 1/5 항목은
    추가로 "enabled"(bool, 이 축의 conventionAxis 성분에 대해 이미 해석된
    값)와 "min"/"max"(float, 라디안 또는 미터로 이미 단위 변환된 값)를
    갖는다. capType 6/7 항목은 추가로 "ratio"(float), "offset"(float),
    "sourceJointName"(str)을 갖는다.

    {"type": "revolute"|"continuous"|"prismatic"|"fixed",
     "lower": float|None, "upper": float|None,
     "mimic": {"joint": str, "multiplier": float, "offset": float}|None}
    을 돌려준다. lower/upper는 "type"에 맞는 단위다(revolute/continuous는
    라디안, prismatic은 미터).

    이 함수는 Maya를 부르지 않는다 -- 호출자가 conventionAxis 성분 해석과
    단위 변환을 이미 끝내 둔 순수 데이터만 받는다.
    """
    hasRotation = any(r["capType"] == 0 for r in capabilityRows)
    hasTranslation = any(r["capType"] == 4 for r in capabilityRows)
    couplingRow = next((r for r in capabilityRows if r["capType"] in (6, 7)), None)
    limitRow = next(
        (r for r in capabilityRows if r["capType"] == 1 and r.get("enabled")), None)
    translationLimitRow = next(
        (r for r in capabilityRows if r["capType"] == 5 and r.get("enabled")), None)

    mimic = None
    if couplingRow is not None:
        mimic = {
            "joint": couplingRow["sourceJointName"],
            "multiplier": couplingRow["ratio"],
            "offset": couplingRow["offset"],
        }

    isAngularDriver = hasRotation or (couplingRow is not None and couplingRow["capType"] == 6)
    isLinearDriver = hasTranslation or (couplingRow is not None and couplingRow["capType"] == 7)

    if isAngularDriver:
        if limitRow is not None:
            return {"type": "revolute", "lower": limitRow["min"], "upper": limitRow["max"],
                    "mimic": mimic}
        return {"type": "continuous", "lower": None, "upper": None, "mimic": mimic}

    if isLinearDriver:
        if translationLimitRow is not None:
            return {"type": "prismatic", "lower": translationLimitRow["min"],
                    "upper": translationLimitRow["max"], "mimic": mimic}
        # URDF는 prismatic에 <limit>이 필수다 -- translationLimit이 없으면
        # "사실상 무제한"이라는 관례로 아주 넓은 값을 채운다(설계 스펙 §3.4).
        return {"type": "prismatic", "lower": -1.0e6, "upper": 1.0e6, "mimic": mimic}

    return {"type": "fixed", "lower": None, "upper": None, "mimic": None}
