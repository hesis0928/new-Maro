"""Maro URDF 내보내기 -- maroAxis 체인과 capability 스택으로부터 URDF(XML)를
생성한다(설계 스펙 2026-09-02-maro-urdf-export-design.md).

새 C++ 코드 없음 -- 기존 maroListAxisNodes/cmds.xform/maroMayaToRos만
조합한다. 이 파일 위쪽의 함수들(buildAxisTree/axisVectorForConvention/
jointType/computeRelativeOrigin/buildUrdfXml)은 Maya 씬을 조회하지 않는
순수 함수다 -- mayapy 배치에서 실제 씬 없이 딕셔너리/튜플만으로 검증
가능하다. 씬을 조회하는 부분과 UI 배선은 이 파일 아래쪽(Task 4)에서
추가된다.
"""

import maya.api.OpenMaya as om2
import xml.etree.ElementTree as ET


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
    couplingRow = next((r for r in capabilityRows if r["capType"] in (6, 7)), None)
    if couplingRow is not None:
        # coupling(mimic) 관절은 limit capability를 절대 참고하지 않는다 --
        # mimic 관절이라고 반드시 각도/거리 제한이 있는 건 아니므로(예:
        # 대칭 기어), rotation-only/translation-only와 같은 원칙 그대로
        # 항상 continuous/prismatic로 확정한다(설계 스펙 §3.4 정정 참고).
        mimic = {
            "joint": couplingRow["sourceJointName"],
            "multiplier": couplingRow["ratio"],
            "offset": couplingRow["offset"],
        }
        jointKind = "continuous" if couplingRow["capType"] == 6 else "prismatic"
        return {"type": jointKind, "lower": None, "upper": None, "mimic": mimic}

    hasRotation = any(r["capType"] == 0 for r in capabilityRows)
    hasTranslation = any(r["capType"] == 4 for r in capabilityRows)
    limitRow = next(
        (r for r in capabilityRows if r["capType"] == 1 and r.get("enabled")), None)
    translationLimitRow = next(
        (r for r in capabilityRows if r["capType"] == 5 and r.get("enabled")), None)

    if hasRotation:
        if limitRow is not None:
            return {"type": "revolute", "lower": limitRow["min"], "upper": limitRow["max"],
                    "mimic": None}
        return {"type": "continuous", "lower": None, "upper": None, "mimic": None}

    if hasTranslation:
        if translationLimitRow is not None:
            return {"type": "prismatic", "lower": translationLimitRow["min"],
                    "upper": translationLimitRow["max"], "mimic": None}
        # URDF는 prismatic에 <limit>이 필수다 -- translationLimit이 없으면
        # "사실상 무제한"이라는 관례로 아주 넓은 값을 채운다(설계 스펙 §3.4).
        return {"type": "prismatic", "lower": -1.0e6, "upper": 1.0e6, "mimic": None}

    return {"type": "fixed", "lower": None, "upper": None, "mimic": None}


def computeRelativeOrigin(parentPosRos, parentQuatRos, childPosRos, childQuatRos):
    """parentPosRos/childPosRos: (x, y, z) 미터. parentQuatRos/childQuatRos:
    (x, y, z, w) -- 전부 이미 ROS 프레임으로 변환된 값(cmds.maroMayaToRos의
    출력, 호출자가 이미 변환해 넘긴다).

    부모 기준 자식의 상대 변환을 (xyz, rpy) 튜플로 돌려준다 -- xyz는 미터,
    rpy는 라디안(URDF의 <origin xyz= rpy=>가 그대로 받는 값, 고정축
    X->Y->Z 순서). 이 함수는 Maya 씬을 조회하지 않는다 -- maya.api.OpenMaya를
    순수 4x4 행렬/쿼터니언 연산 라이브러리로만 쓴다(설계 스펙 §3.2).
    """
    def _matrix(pos, quat):
        t = om2.MTransformationMatrix()
        t.setTranslation(om2.MVector(*pos), om2.MSpace.kWorld)
        t.setRotation(om2.MQuaternion(*quat))
        return t.asMatrix()

    parentMatrix = _matrix(parentPosRos, parentQuatRos)
    childMatrix = _matrix(childPosRos, childQuatRos)
    # Maya는 행벡터 관례(v' = v * M, 왼쪽에서 오른쪽으로 적용)를 쓴다 --
    # "부모 기준 자식"은 자식을 먼저 적용한 뒤 부모의 역변환을 적용한
    # 것이다.
    relative = childMatrix * parentMatrix.inverse()

    relativeXform = om2.MTransformationMatrix(relative)
    xyz = relativeXform.translation(om2.MSpace.kWorld)

    euler = relativeXform.rotation(asQuaternion=False)
    # 실측 검증 결과(tests/maya/test_urdf_export.py의 독립 1차 원리 행렬
    # 비교): om2.MEulerRotation(r, p, y, kXYZ).asMatrix()를 전치(행벡터 ->
    # 열벡터)한 것이 URDF rpy 공식 R = Rz(yaw) @ Ry(pitch) @ Rx(roll)와
    # 수치적으로 일치한다 -- brief의 kZYX 가설은 틀렸다(반증됨, 최대 오차
    # ~0.33). kXYZ가 맞다.
    euler = euler.reorder(om2.MEulerRotation.kXYZ)
    rpy = (euler.x, euler.y, euler.z)

    return (xyz.x, xyz.y, xyz.z), rpy


def buildUrdfXml(robotName, links, joints):
    """links: [{"name": str}, ...]. joints: [{"name": str, "type": str,
    "parent": str, "child": str, "originXyz": (x,y,z), "originRpy": (r,p,y),
    "axis": (x,y,z)|None, "lower": float|None, "upper": float|None,
    "mimic": {"joint": str, "multiplier": float, "offset": float}|None}, ...].

    <robot name=robotName>를 루트로 하는 xml.etree.ElementTree.Element를
    돌려준다 -- 파일 쓰기는 호출자 몫이다(이 함수는 트리만 조립하는 순수
    함수). "fixed" 타입은 <axis>/<limit>을 안 낸다. "continuous" 타입은
    <axis>는 내지만 <limit>은 안 낸다.
    """
    robot = ET.Element("robot", name=robotName)
    for link in links:
        ET.SubElement(robot, "link", name=link["name"])

    for joint in joints:
        jointEl = ET.SubElement(robot, "joint", name=joint["name"], type=joint["type"])
        ET.SubElement(jointEl, "parent", link=joint["parent"])
        ET.SubElement(jointEl, "child", link=joint["child"])
        ox, oy, oz = joint["originXyz"]
        orr, orp, ory = joint["originRpy"]
        ET.SubElement(jointEl, "origin",
                      xyz="{:.6f} {:.6f} {:.6f}".format(ox, oy, oz),
                      rpy="{:.6f} {:.6f} {:.6f}".format(orr, orp, ory))
        if joint["type"] != "fixed":
            ax, ay, az = joint["axis"]
            ET.SubElement(jointEl, "axis", xyz="{:.0f} {:.0f} {:.0f}".format(ax, ay, az))
        if joint["type"] in ("revolute", "prismatic"):
            ET.SubElement(jointEl, "limit",
                          lower="{:.6f}".format(joint["lower"]),
                          upper="{:.6f}".format(joint["upper"]),
                          effort="1000", velocity="10")
        if joint["mimic"] is not None:
            ET.SubElement(jointEl, "mimic", joint=joint["mimic"]["joint"],
                          multiplier="{:.6f}".format(joint["mimic"]["multiplier"]),
                          offset="{:.6f}".format(joint["mimic"]["offset"]))
    return robot
