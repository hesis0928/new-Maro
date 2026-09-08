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

import math
import os
import re
import struct

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
    """links: [{"name": str, "visualMesh": str|None(선택)}, ...].
    joints: [{"name": str, "type": str,
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
        linkEl = ET.SubElement(robot, "link", name=link["name"])
        # .get()으로 읽는다 -- "visualMesh" 키가 아예 없는 기존 호출부와
        # 테스트도 그대로 동작해야 한다(슬라이스 1이 추가한 선택적 필드다).
        visualMesh = link.get("visualMesh")
        if visualMesh:
            visualEl = ET.SubElement(linkEl, "visual")
            # 정점을 이미 링크 프레임으로 구웠으므로 원점은 항등이다 --
            # 변환을 URDF 쪽 <origin>/<scale>로 미루지 않는다(스펙 §6).
            ET.SubElement(visualEl, "origin", xyz="0 0 0", rpy="0 0 0")
            geometryEl = ET.SubElement(visualEl, "geometry")
            ET.SubElement(geometryEl, "mesh", filename=visualMesh)

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


def _axisParentTransformPath(axis):
    """axis(maroAxis 로케이터 셰이프)의 부모 트랜스폼 전체 경로를 돌려준다.

    이 노드가 URDF의 **링크 프레임**을 실제로 정한다(설계 스펙 §4
    [정정, 2026-09-07] -- 최종 전체 브랜치 리뷰 Finding 1). 조인트 원점
    (`_gatherAxisWorldTransformRos`)과 관절 축(`axisVectorForConvention`)이
    이미 이 노드를 프레임으로 쓰므로, 시각 메쉬(`_linkMeshTriangles`)도
    같은 노드를 써야 셋이 같은 프레임에 선다. `maroBindAxis`는 message
    커넥션 하나일 뿐 이 트랜스폼을 바인딩 대상 위로 옮기지 않으므로, 이
    함수와 바인딩된 트랜스폼(`boundTargetPath`)은 일반적으로 다른 노드다."""
    return cmds.listRelatives(axis, parent=True, fullPath=True)[0]


def _gatherAxisWorldTransformRos(axis):
    """axis(maroAxis 로케이터 셰이프)의 부모 트랜스폼의 월드 위치/회전을
    ROS 프레임 (pos, quat) 튜플로 돌려준다.

    maroAxis는 로케이터 **셰이프**다 -- 위치/회전은 실제로 그 부모
    트랜스폼에 있으므로(`createNode("maroAxis")`가 자동으로 만드는 부모),
    `_axisParentTransformPath(axis)`로 먼저 그 트랜스폼을 얻는다.

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
    transformPath = _axisParentTransformPath(axis)
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


def _linkMeshTriangles(linkTransform, axisFramePath):
    """linkTransform의 **직속** mesh 셰이프(중간 셰이프 제외)들에서 삼각형을
    모아 **링크 프레임**(axisFramePath, Maya 내부 단위)으로 돌려준다. 메쉬가
    없으면 빈 리스트.

    **allDescendents를 쓰면 안 된다.** 조인트 체인에서 한 링크의 자손에는
    자식 링크의 메쉬가 들어 있어서, 자손 전체를 훑으면 같은 지오메트리가
    두 링크에 중복으로 들어가고 부모 링크가 로봇 전체를 삼킨다(스펙 §3).
    maroDagMenu._findLidarForMesh가 listRelatives(shapes=True)로 직속만
    보는 것과 같은 이유다.

    [실측, 2026-09-07] 위험한 형태는 정확히 `allDescendents=True, type="mesh"`
    (shapes 플래그 **없이**) 하나다. 같은 씬에서 재 봤다:

        shapes=True                       -> ['|pBase|pBaseShape']
        allDescendents=True, shapes=True  -> ['|pBase|pBaseShape']      (같음!)
        allDescendents=True (shapes 없음) -> ['|pBase|pBaseShape',
                                              '|pBase|pChild|pChildShape']

    즉 `shapes=True`는 `allDescendents`의 재귀를 조용히 무력화한다. 그래서
    "allDescendents를 쓰되 shapes도 남겨 둔" 실수는 우연히 올바르게 동작하고,
    테스트도 (잡을 결함이 없으므로) 통과한다. 회귀 테스트가 실제로 겨누는
    것은 shapes를 뗀 쪽이며, 그 형태로 바꾸면 부모 링크가 삼각형 24개를
    받아 테스트가 실패하는 것을 확인했다.

    **중간 셰이프(intermediate object)는 건너뛴다** [최종 리뷰 Finding 2].
    디포머가 걸린 메쉬는 `...ShapeOrig` 중간 셰이프를 함께 갖는데, 그것까지
    세면 변형된 껍질과 변형 전 껍질이 겹쳐 들어가 삼각형이 두 배가 되고
    RViz에 유령 몸통이 뜬다(실측: bend 디포머를 건 큐브가 12개가 아니라
    24개). `noIntermediate=True`로 막는다 -- `MaroLidarScan.cpp`가 이미 같은
    문제를 `isIntermediateObject()`로 풀어 뒀고, 그 헤더가 "이 문제를 두 번
    풀지 않는다"고 적어 둔 바로 그 자리다.

    [정정, 최종 리뷰 Finding 1] 정점을 되돌리는 역행렬은 linkTransform(메쉬
    셰이프를 찾은 바인딩 대상)이 아니라 axisFramePath(maroAxis 로케이터의
    부모 트랜스폼)에서 가져온다. URDF의 링크 프레임을 실제로 정하는 것은
    조인트 원점(`_gatherAxisWorldTransformRos`)과 관절 축
    (`axisVectorForConvention`)이 이미 쓰는 이 로케이터 프레임이다 --
    `maroBindAxis`는 message 커넥션 하나일 뿐 로케이터를 바인딩 대상 위로
    옮기거나 자세를 맞추지 않으므로, 관절이 팔꿈치에 있고 팔 메쉬 피벗이 그
    위에 있는 흔한 리그에서 두 프레임은 어긋난다(설계 스펙 §4
    [정정, 2026-09-07]). 회전도 로케이터 기준으로 같이 되돌려야 하므로,
    위치/회전을 따로 분해하지 않고 axisFramePath의 inclusiveMatrixInverse()
    하나로 한 번에 되돌린다.
    """
    shapes = cmds.listRelatives(linkTransform, shapes=True, fullPath=True,
                                type="mesh", noIntermediate=True) or []
    if not shapes:
        return []

    frameInverse = om2.MSelectionList().add(axisFramePath).getDagPath(0) \
        .inclusiveMatrixInverse()
    triangles = []
    for shape in shapes:
        meshFn = om2.MFnMesh(om2.MSelectionList().add(shape).getDagPath(0))
        worldPoints = meshFn.getPoints(om2.MSpace.kWorld)
        # getTriangles()는 (면당 삼각형 수, 평평한 정점 인덱스)를 준다 --
        # 인덱스는 세 개씩 한 삼각형이다(실측: 기본 폴리큐브 = 면 6개,
        # 인덱스 36개, 삼각형 12개).
        _counts, indices = meshFn.getTriangles()
        for i in range(0, len(indices), 3):
            corners = []
            for j in range(3):
                p = worldPoints[indices[i + j]] * frameInverse
                corners.append((p.x, p.y, p.z))
            triangles.append(tuple(corners))
    return triangles


def _writeLinkMeshes(links, meshDir, robotName):
    """각 링크의 메쉬를 STL로 쓰고 link["visualMesh"]에 package:// 경로를
    채운다. 메쉬가 없거나 삼각형이 0개인 링크는 건드리지 않는다 -- 그
    링크는 <visual> 없이 나가며 이는 정상이고 에러가 아니다.

    meshDir는 실제로 쓸 것이 생겼을 때만 만든다 -- 지오메트리가 하나도
    없는 씬을 내보내면 빈 meshes/ 디렉터리를 남기지 않는다.

    targetPath(메쉬 셰이프를 찾을 바인딩 대상)와 axisFramePath(정점을 구울
    링크 프레임 -- maroAxis 로케이터의 부모 트랜스폼)는 일반적으로 서로
    다른 노드다(최종 리뷰 Finding 1). 링크 딕셔너리가 둘 다 갖고 있어야
    한다 -- `_buildRobotModel`이 채운다.
    """
    usedNames = set()
    for link in links:
        targetPath = link.get("targetPath")
        axisFramePath = link.get("axisFramePath")
        if not targetPath or not axisFramePath:
            continue
        triangles = _linkMeshTriangles(targetPath, axisFramePath)
        if not triangles:
            continue
        fileName = sanitizeMeshFileName(link["name"], usedNames)
        if not os.path.isdir(meshDir):
            os.makedirs(meshDir)
        writeBinaryStl(mayaTrianglesToRosMeters(triangles),
                       os.path.join(meshDir, fileName + ".stl"))
        link["visualMesh"] = "package://{}/meshes/{}.stl".format(robotName, fileName)


def _buildRobotModel():
    """씬을 조회해 buildUrdfXml에 넘길 (links, joints)를 만든다."""
    axisRows = sliceAxisRows(cmds.maroListAxisNodes())
    if not axisRows:
        raise ValueError("scene has no maroAxis nodes to export")
    root, childrenByParent = buildAxisTree(axisRows)

    rowsByPath = {row["axisFullPath"]: row for row in axisRows}
    # targetPath는 _writeLinkMeshes가 그 링크의 메쉬 셰이프를 찾는 데 쓰고,
    # axisFramePath는 그 메쉬를 구울 링크 프레임(로케이터의 부모 트랜스폼,
    # _gatherAxisWorldTransformRos/axisVectorForConvention과 같은 노드)을
    # 알려준다(최종 리뷰 Finding 1). buildUrdfXml은 이 키들을 무시한다.
    links = [{"name": _shortName(rowsByPath[root]["boundTargetPath"]),
              "targetPath": rowsByPath[root]["boundTargetPath"],
              "axisFramePath": _axisParentTransformPath(root)}]
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

            links.append({"name": _shortName(childRow["boundTargetPath"]),
                          "targetPath": childRow["boundTargetPath"],
                          "axisFramePath": _axisParentTransformPath(childAxis)})
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
        # STL은 .urdf 옆 meshes/ 에 쓴다. abspath를 거치는 이유는 path가
        # 디렉터리 없는 상대 파일명일 때 dirname이 ""이 되어 meshes/가
        # 엉뚱한 곳(프로세스 cwd)에 생기는 것을 막기 위해서다.
        _writeLinkMeshes(
            links,
            os.path.join(os.path.dirname(os.path.abspath(path)), "meshes"),
            robotName)
        robotElement = buildUrdfXml(robotName, links, joints)
        ET.indent(robotElement, space="  ")
        ET.ElementTree(robotElement).write(path, xml_declaration=True, encoding="utf-8")
        cmds.inViewMessage(amg="Maro: URDF exported to <hl>{}</hl>".format(path),
                            pos="topCenter", fade=True)
        return path
    except Exception as exc:  # noqa: BLE001 -- 메뉴 커맨드 문자열 경계
        cmds.warning("Maro: URDF export failed: {}".format(exc))
        return None


# 파일명에 그대로 써도 안전한 문자. 나머지는 "_"로 바꾼다.
_UNSAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9_-]")


def sanitizeMeshFileName(linkName, usedNames):
    """linkName을 파일명으로 쓸 수 있게 살균한다(확장자는 안 붙인다).

    [실측] _shortName()은 DAG 경로를 "|"로만 쪼개므로, 네임스페이스가 붙은
    노드는 링크 이름이 "ns:cube"가 된다. ":"는 Windows 파일명에 쓸 수 없어
    그대로 쓰면 내보내기가 실패한다.

    **URDF 안의 <link name=>은 이 함수를 거치지 않는다.** 그건 이미
    동작하는 기존 계약이고 이번 변경이 건드릴 이유가 없다 -- 링크 이름과
    파일명은 별개이며 <mesh filename=>만 살균된 쪽을 가리킨다.

    usedNames(set)는 이 함수가 갱신한다. 살균 결과가 서로 충돌하면
    ("a:b"와 "a/b"가 둘 다 "a_b"가 되는 경우) 뒤에 일련번호를 붙인다.
    """
    base = _UNSAFE_FILENAME_RE.sub("_", linkName) or "link"
    candidate = base
    suffix = 1
    while candidate in usedNames:
        candidate = "{}_{}".format(base, suffix)
        suffix += 1
    usedNames.add(candidate)
    return candidate


def mayaTrianglesToRosMeters(triangles):
    """Maya 내부 단위(센티미터)의 링크 로컬 삼각형들을 ROS 프레임 미터로.

    축 재배치 (x,y,z) -> (x,-z,y)는 python/maroLimitCalibration.py의
    mayaDirectionToRos와 **같은 식**이다. 다른 점은 스케일뿐이다 --
    방향 벡터는 단위가 없어 스케일을 곱하지 않지만 위치는 곱한다.

    **정점 순서를 바꾸지 않는다.** 그 재배치의 행렬식은 +1이다(X축 +90°
    회전이며 반사가 아니다). 따라서 와인딩이 그대로 보존되어 법선이
    뒤집히지 않는다 -- 반사였다면 삼각형마다 정점 두 개를 맞바꿔야 했고,
    확인하지 않고 넘어갔다면 RViz에서 안팎이 뒤집힌 메쉬가 나왔을 것이다.

    스케일은 메쉬 하나당 한 번만 조회한다(정점마다 om2를 부르지 않는다).
    om2는 UI 선형 단위 계층 아래에서 항상 내부 단위로만 동작하므로
    (_gatherAxisWorldTransformRos의 주석과 같은 이유) 사용자의 UI 단위
    설정이 이 값을 흔들지 않는다.
    """
    scale = om2.MDistance(1.0, om2.MDistance.internalUnit()).asMeters()
    return [
        tuple((v[0] * scale, -v[2] * scale, v[1] * scale) for v in triangle)
        for triangle in triangles
    ]


# 바이너리 STL 헤더. 80바이트까지 \0으로 채운다(설계 스펙 §5).
_STL_HEADER = b"Maro URDF export"


def _triangleNormal(a, b, c):
    """삼각형의 단위 법선. 면적이 0이면 (0,0,0)을 준다 -- 0으로 나누지
    않는다. 대부분의 STL 뷰어는 저장된 법선을 무시하고 다시 계산하지만,
    전부 0으로 두면 형식을 잘못 쓴 것과 구별되지 않으므로 계산해 채운다."""
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length < 1e-12:
        return (0.0, 0.0, 0.0)
    return (nx / length, ny / length, nz / length)


def writeBinaryStl(triangles, path):
    """triangles([((x,y,z),(x,y,z),(x,y,z)), ...])를 바이너리 STL로 쓴다.

    형식(전부 리틀엔디언):
      오프셋 0    80바이트  헤더
      오프셋 80    4바이트  uint32 삼각형 수
      오프셋 84+  50바이트  삼각형당: 법선 3xfloat32, 정점 9xfloat32, uint16 속성

    Maya 내장 익스포터(stlTranslator.mll)가 아니라 직접 쓰는 이유는 설계
    스펙 §5에 있다 -- 좌표/단위 변환을 정점에 바로 적용할 수 있고(익스포터의
    단위 해석에 의존하지 않는다), 순수 함수라 배치 테스트로 왕복 검증이
    된다. maroSyntheticDataPointCloud.writePly와 같은 결이다.

    "<12fH"는 12*4 + 2 = 50바이트다 -- "<"가 정렬 패딩을 끄므로 구조체
    크기가 형식대로 정확히 나온다.
    """
    with open(path, "wb") as f:
        f.write(_STL_HEADER.ljust(80, b"\0"))
        f.write(struct.pack("<I", len(triangles)))
        for a, b, c in triangles:
            nx, ny, nz = _triangleNormal(a, b, c)
            f.write(struct.pack("<12fH", nx, ny, nz,
                                a[0], a[1], a[2],
                                b[0], b[1], b[2],
                                c[0], c[1], c[2], 0))
