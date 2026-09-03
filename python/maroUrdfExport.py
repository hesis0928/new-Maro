"""Maro URDF 내보내기 -- maroAxis 체인과 capability 스택으로부터 URDF(XML)를
생성한다(설계 스펙 2026-09-02-maro-urdf-export-design.md).

새 C++ 코드 없음 -- 기존 maroListAxisNodes/maroMayaToRos와
maya.api.OpenMaya(내부 단위로만 동작)만 조합한다. **cmds.xform은 쓰지
않는다** -- cmds.xform은 사용자가 바꿀 수 있는 현재 UI 선형 단위로 값을
돌려주는데 maroMayaToRos는 입력이 항상 Maya 내부 단위(센티미터)라고
전제하므로, 그 자리에 cmds.xform을 쓰면 UI 단위 설정에 따라 조용히 틀린
위치가 나온다(_gatherAxisWorldTransformRos의 주석 참고). 이 파일
위쪽의 함수들(buildAxisTree/axisVectorForConvention/
jointType/computeRelativeOrigin/buildUrdfXml)은 Maya 씬을 조회하지 않는
순수 함수다 -- mayapy 배치에서 실제 씬 없이 딕셔너리/튜플만으로 검증
가능하다. 씬을 조회하는 부분과 UI 배선은 이 파일 아래쪽(Task 4)에서
추가된다.
"""

import os

import maya.cmds as cmds
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


_AXIS_VECTORS = {0: (1.0, 0.0, 0.0), 1: (0.0, 0.0, 1.0), 2: (0.0, -1.0, 0.0)}


def axisVectorForConvention(conventionAxis):
    """conventionAxis(0=X 1=Y 2=Z, Maya-로컬 축 인덱스)를 URDF <axis xyz=>에
    쓸 ROS 프레임 단위 축 벡터로 바꾼다.

    설계 스펙 §3.3은 원래 "origin이 이미 로케이터 자세를 관절 프레임으로
    확정하므로 별도 좌표 변환이 필요 없다"고 주장했으나, 이는 틀렸다(최종
    전체 브랜치 리뷰에서 발견). <origin>의 위치/자세는 실제로 맞다 --
    computeRelativeOrigin이 부모/자식 로케이터를 각각 이미 ROS 프레임으로
    변환한 뒤(_gatherAxisWorldTransformRos가 cmds.maroMayaToRos로) 상대
    변환을 켤레(conjugation)로 계산하기 때문에, 그 켤레 연산 자체가
    자기완결적으로 일관된다(따로 검증됨).

    하지만 axisVectorForConvention은 그 켤레와 무관한 별개의 값 -- "이
    관절이 로컬 X/Y/Z 중 어느 축으로 도는가"를 conventionAxis라는
    Maya-로컬 인덱스에서 뽑아 ROS 프레임 벡터로 직접 내보낸다. 이 축
    "선택" 자체에도 코드베이스 전역에서 쓰는 것과 똑같은 Maya->ROS
    재배치를 적용해야 한다 -- maroMayaToRos/mayaToRosRotation
    (src/maro_transform/src/Convert.cpp)의 (x,y,z)->(x,-z,y) 재배치는 X만
    고정하고 Y/Z는 서로 뒤바뀌므로(Y->Z, Z->-Y), origin 켤레가 알아서
    "고쳐주는" 게 아니다. 그래서 _AXIS_VECTORS는 conventionAxis별 raw
    Maya 로컬 단위 벡터가 아니라 그 벡터에 (x,y,z)->(x,-z,y)를 미리 적용해
    둔 결과다: X(1,0,0)->(1,0,0), Y(0,1,0)->(0,0,1), Z(0,0,1)->(0,-1,0)."""
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
    # coupling(mimic)을 rotation/translation보다 먼저 확인한다 -- 이는
    # MaroAxisNode::compute()의 C++ 순서("가장 낮은 인덱스의 primary
    # driver가 이긴다")와 의도적으로 다르다. 커맨드 계층의 "축당 driver
    # 하나" 규칙을 우회하는 씬에서만 두 순서가 갈리며, 이 exporter는
    # 그런 씬에서도 항상 coupling을 우선하기로 의도적으로 선택했다.
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
            lower, upper = limitRow["min"], limitRow["max"]
            # MaroAxisNode.cpp 자신도 minX > maxX인 씬을 std::min/std::max로
            # 클램프해 관용적으로 받아들인다 -- 여기서도 같은 관용을 지켜
            # 뒤집힌 limit이 lower > upper인 무효 URDF(check_urdf가 거부)로
            # 새는 걸 막는다. 이미 올바른 순서인 흔한 경우는 그대로다.
            lower, upper = min(lower, upper), max(lower, upper)
            return {"type": "revolute", "lower": lower, "upper": upper, "mimic": None}
        return {"type": "continuous", "lower": None, "upper": None, "mimic": None}

    if hasTranslation:
        if translationLimitRow is not None:
            lower, upper = translationLimitRow["min"], translationLimitRow["max"]
            lower, upper = min(lower, upper), max(lower, upper)
            return {"type": "prismatic", "lower": lower,
                    "upper": upper, "mimic": None}
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


AXIS_FIELDS = 10
CAPABILITY_FIELDS = 5


def sliceAxisRows(flat):
    """maroListAxisNodes()의 평탄한 배열을 축 행 딕셔너리 목록으로
    되돌린다."""
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
            "parentAxisPath": f[3],
            "conventionAxis": int(f[6]),
        })
    return rows


def sliceCapabilityRows(flat):
    """maroListAxisNodes(capabilities=axis)의 평탄한 배열을 capability 행
    딕셔너리 목록으로 되돌린다."""
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
            "capabilityNodeName": f[1],
            "capType": int(f[3]),
            "connected": f[4] == "1",
        })
    return rows


def _resolveCapabilityDetails(axis, capRow, conventionAxis):
    """capRow(logicalIndex/capabilityNodeName/capType)에 jointType()이 바로
    쓸 수 있는 값(min/max/enabled 또는 ratio/offset/sourceJointName)을
    채운다. 이 함수만 실제 씬을 조회한다(cmds.getAttr/listConnections).

    capMin/capMax는 MFnUnitAttribute가 아니라 평범한 MFnNumericData::k3Double
    이다(MaroAxisNode.cpp) -- cmds.getAttr은 이 값에 UI 단위 변환을 절대
    적용하지 않는다(cmds.currentUnit()과 무관). 대신 MaroCapabilityNodes.cpp의
    MaroLimitNode::compute가 자기 쪽의 진짜 unit-typed 속성(각도는 degrees로
    표시)을 이 평범한 double 컴파운드에 쓰기 **전에** 고정 단위로 변환해
    둔다 -- capType 1은 항상 라디안(.asRadians() 후 저장), capType 5는 항상
    센티미터(.asCentimeters() 후 저장), 세션 단위 설정과 무관하게 항상
    그렇다. python/maroTechDiag.py가 이미 이 정확한 결론에 도달해 캡처했고
    (capMin/capMax를 순수 cmds.getAttr로만 읽는다), 여기서도 같은 방식을
    따른다 -- capType 1은 감싸지 않고 그대로 쓰고, capType 5만 고정
    kCentimeters 소스 단위로 MDistance 변환한다(.uiUnit()이 아니다)."""
    capType = capRow["capType"]
    idx = capRow["logicalIndex"]
    result = {"capType": capType}
    if capType == 1:
        enable = cmds.getAttr("{}.capabilityIn[{}].capEnable".format(axis, idx))[0]
        minRaw = cmds.getAttr("{}.capabilityIn[{}].capMin".format(axis, idx))[0]
        maxRaw = cmds.getAttr("{}.capabilityIn[{}].capMax".format(axis, idx))[0]
        result["enabled"] = bool(enable[conventionAxis])
        # 이미 라디안이다(MaroLimitNode::compute가 저장 전에 변환) --
        # MAngle.uiUnit() 감싸기 금지.
        result["min"] = minRaw[conventionAxis]
        result["max"] = maxRaw[conventionAxis]
    elif capType == 5:
        enable = cmds.getAttr("{}.capabilityIn[{}].capEnable".format(axis, idx))[0]
        minRaw = cmds.getAttr("{}.capabilityIn[{}].capMin".format(axis, idx))[0]
        maxRaw = cmds.getAttr("{}.capabilityIn[{}].capMax".format(axis, idx))[0]
        result["enabled"] = bool(enable[conventionAxis])
        # 이미 센티미터다(MaroCapabilityNodes.cpp가 저장 전에 변환) --
        # 고정 kCentimeters 소스 단위로만 변환한다(.uiUnit() 아님).
        result["min"] = om2.MDistance(minRaw[conventionAxis], om2.MDistance.kCentimeters).asMeters()
        result["max"] = om2.MDistance(maxRaw[conventionAxis], om2.MDistance.kCentimeters).asMeters()
    elif capType in (6, 7):
        # aRatio/aOffset은 MFnUnitAttribute가 아니라 평범한 double이다
        # (MaroCapabilityNodes.h 확인) -- 단위 변환이 필요 없다.
        node = capRow["capabilityNodeName"]
        if not node:
            # connected가 False였다는 뜻 -- capabilityNodeName이 빈
            # 문자열이면 아래 cmds.getAttr(node + ".ratio")가
            # "No object matches name: .ratio"라는 알아보기 힘든 Maya
            # 에러로 새어나간다. sourceValue(Linear) 커넥션이 없을 때
            # 이미 던지는 형제 ValueError와 같은 명확함으로 여기서 먼저
            # 잡는다.
            raise ValueError(
                "axis '{}' capability slot {} (capType {}) has no connected "
                "coupling node -- capabilityNodeName is empty".format(
                    axis, idx, capType))
        result["ratio"] = cmds.getAttr(node + ".ratio")
        result["offset"] = cmds.getAttr(node + ".offset")
        sourcePlugName = "sourceValue" if capType == 6 else "sourceValueLinear"
        sources = cmds.listConnections(
            node + "." + sourcePlugName, source=True, destination=False, plugs=False) or []
        if not sources:
            raise ValueError(
                "coupling node '{}' has no {} source connection".format(node, sourcePlugName))
        sourceAxis = cmds.ls(sources[0], long=True)[0]
        result["sourceJointName"] = cmds.getAttr(sourceAxis + ".jointName")
    return result


def _gatherAxisWorldTransformRos(axis):
    """axis(maroAxis 로케이터 셰이프)의 부모 트랜스폼의 월드 위치/회전을
    ROS 프레임 (pos, quat) 튜플로 돌려준다.

    maroAxis는 로케이터 **셰이프**다 -- 위치/회전은 실제로 그 부모
    트랜스폼에 있으므로(`createNode("maroAxis")`가 자동으로 만드는 부모),
    `cmds.listRelatives(axis, parent=True)`로 먼저 그 트랜스폼을 얻는다.

    위치는 `cmds.xform`이 아니라 `dagPath.inclusiveMatrix()` +
    `MTransformationMatrix.translation()`으로 얻는다 -- `cmds.xform`은
    **현재 UI 선형 단위**(사용자가 in/m 등으로 바꿀 수 있음)로 값을
    돌려주는데, `maroMayaToRos`(`MaroRosProxyCommands.cpp`)는 입력이
    Maya **내부** 단위(`MDistance::internalUnit()`, 항상 센티미터)라고
    전제한다 -- 두 단위가 다르면 사용자의 UI 단위 설정에 따라 조용히
    틀린 위치가 나온다. `maya.api.OpenMaya`는 이 UI 단위 계층 아래에서
    항상 내부 단위로만 동작하므로 이 함정 자체가 성립하지 않는다
    (`_resolveCapabilityDetails`가 `MAngle`/`MDistance`로 반대 방향
    함정 -- getAttr이 UI 단위로 주는 것 -- 을 막는 것과 쌍을 이룬다).

    회전은 MFnTransform.rotation(kWorld, asQuaternion=True)로 얻는다 --
    부모 변환까지 반영한 진짜 월드 회전임을 이 코드베이스가 이미
    실측으로 검증해 둔 방식이다(python/maroRosProxy.py의 같은 호출과
    그 옆 주석 참고). (`_resolveCapabilityDetails`의 capMin/capMax는 이와는
    별개 문제다 -- 그쪽은 애초에 UI 단위가 전혀 개입하지 않는 평범한
    double이라 감싸면 안 되는 값이었다.)"""
    transformPath = cmds.listRelatives(axis, parent=True, fullPath=True)[0]
    dagPath = om2.MSelectionList().add(transformPath).getDagPath(0)
    worldMatrix = om2.MTransformationMatrix(dagPath.inclusiveMatrix())
    pos = worldMatrix.translation(om2.MSpace.kWorld)
    quat = om2.MFnTransform(dagPath).rotation(om2.MSpace.kWorld, asQuaternion=True)
    converted = cmds.maroMayaToRos(px=pos.x, py=pos.y, pz=pos.z,
                                    qx=quat.x, qy=quat.y, qz=quat.z, qw=quat.w)
    return (converted[0], converted[1], converted[2]), \
        (converted[3], converted[4], converted[5], converted[6])


def _shortName(fullPath):
    return fullPath.split("|")[-1]


def _buildRobotModel():
    """씬을 조회해 buildUrdfXml에 넘길 (links, joints)를 만든다."""
    axisRows = sliceAxisRows(cmds.maroListAxisNodes())
    if not axisRows:
        raise ValueError("scene has no maroAxis nodes to export")
    root, childrenByParent = buildAxisTree(axisRows)

    rowsByPath = {row["axisFullPath"]: row for row in axisRows}
    links = [{"name": _shortName(rowsByPath[root]["boundTargetPath"])}]
    joints = []

    def _visit(parentAxis):
        for childAxis in childrenByParent.get(parentAxis, []):
            childRow = rowsByPath[childAxis]
            capFlat = cmds.maroListAxisNodes(capabilities=childAxis)
            capRows = [
                _resolveCapabilityDetails(childAxis, row, childRow["conventionAxis"])
                for row in sliceCapabilityRows(capFlat)
            ]
            jt = jointType(capRows)

            parentPos, parentQuat = _gatherAxisWorldTransformRos(parentAxis)
            childPos, childQuat = _gatherAxisWorldTransformRos(childAxis)
            xyz, rpy = computeRelativeOrigin(parentPos, parentQuat, childPos, childQuat)

            axisVector = None
            if jt["type"] != "fixed":
                axisVector = axisVectorForConvention(childRow["conventionAxis"])
                # conventionInvert는 라이브 ROS 퍼블리시 경로(Convert.cpp의
                # axisVectorOf, MaroPump.cpp가 findPlug로 읽음)가 이미
                # 존중하는 플래그다 -- 여기서 안 읽으면 이 플래그를 쓰는
                # 리그는 URDF 조인트가 실제 라이브 동작과 반대 방향으로
                # 돈다. Maya->ROS 재배치는 선형 사상이므로 재배치 이후에
                # 부호를 뒤집어도 재배치 이전에 뒤집는 것과 결과가 같다
                # (M*(-v) == -(M*v)).
                if cmds.getAttr(childAxis + ".conventionInvert"):
                    # 0.0을 곧이곧대로 부호만 뒤집으면 -0.0이 나와
                    # "{:.0f}".format(-0.0) == "-0"으로 URDF에 그대로
                    # 새어나간다(수치적으로는 0과 같지만 보기 흉하다) --
                    # 0 성분은 0.0으로 정규화해 둔다.
                    axisVector = tuple(0.0 if v == 0.0 else -v for v in axisVector)

            links.append({"name": _shortName(childRow["boundTargetPath"])})
            joints.append({
                "name": childRow["jointName"],
                "type": jt["type"],
                "parent": _shortName(rowsByPath[parentAxis]["boundTargetPath"]),
                "child": _shortName(childRow["boundTargetPath"]),
                "originXyz": xyz,
                "originRpy": rpy,
                "axis": axisVector,
                "lower": jt["lower"],
                "upper": jt["upper"],
                "mimic": jt["mimic"],
            })
            _visit(childAxis)

    _visit(root)
    return links, joints


def export(path=None):
    """Maro 메뉴의 "URDF 내보내기..." 항목이 부른다. path가 없으면
    cmds.fileDialog2로 저장 경로를 묻는다(path를 직접 주면 대화상자 없이
    그 경로에 바로 쓴다 -- 테스트/스크립트용). 성공하면 쓴 경로, 취소/
    실패하면 None을 돌려준다."""
    if path is None:
        results = cmds.fileDialog2(fileMode=0, fileFilter="URDF (*.urdf)",
                                    caption="Export URDF")
        if not results:
            return None
        path = results[0]
    try:
        links, joints = _buildRobotModel()
        robotName = os.path.splitext(os.path.basename(path))[0]
        robotElement = buildUrdfXml(robotName, links, joints)
        ET.indent(robotElement, space="  ")
        ET.ElementTree(robotElement).write(path, xml_declaration=True, encoding="utf-8")
        cmds.inViewMessage(amg="Maro: URDF exported to <hl>{}</hl>".format(path),
                            pos="topCenter", fade=True)
        return path
    except Exception as exc:  # noqa: BLE001 -- 메뉴 커맨드 문자열 경계
        cmds.warning("Maro: URDF export failed: {}".format(exc))
        return None
