import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)
cmds.currentUnit(angle="rad")
cmds.currentUnit(linear="cm")

_pythonDir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "python")
if _pythonDir not in sys.path:
    sys.path.insert(0, _pythonDir)

import maroUrdfExport as urdf  # noqa: E402

# --- buildAxisTree ---
threeAxisRows = [
    {"axisFullPath": "|root", "parentAxisPath": "", "jointName": "j_root"},
    {"axisFullPath": "|child1", "parentAxisPath": "|root", "jointName": "j_child1"},
    {"axisFullPath": "|child2", "parentAxisPath": "|root", "jointName": "j_child2"},
]
root, children = urdf.buildAxisTree(threeAxisRows)
assert root == "|root", root
assert children == {"|root": ["|child1", "|child2"]}, children
print("buildAxisTree basic tree OK")

try:
    urdf.buildAxisTree([
        {"axisFullPath": "|a", "parentAxisPath": "", "jointName": "ja"},
        {"axisFullPath": "|b", "parentAxisPath": "", "jointName": "jb"},
    ])
    raise AssertionError("expected ValueError for two roots")
except ValueError as e:
    assert "found 2" in str(e), e
print("buildAxisTree rejects multiple roots OK")

try:
    urdf.buildAxisTree([
        {"axisFullPath": "|a", "parentAxisPath": "|b", "jointName": "ja"},
        {"axisFullPath": "|b", "parentAxisPath": "|a", "jointName": "jb"},
    ])
    raise AssertionError("expected ValueError for zero roots")
except ValueError as e:
    assert "found 0" in str(e), e
print("buildAxisTree rejects zero roots OK")

try:
    urdf.buildAxisTree([
        {"axisFullPath": "|root", "parentAxisPath": "", "jointName": ""},
    ])
    raise AssertionError("expected ValueError for empty jointName")
except ValueError as e:
    assert "|root" in str(e), e
print("buildAxisTree rejects empty jointName OK")

try:
    urdf.buildAxisTree([
        {"axisFullPath": "|root", "parentAxisPath": "", "jointName": "j_root"},
        {"axisFullPath": "|root|child1", "parentAxisPath": "|root", "jointName": "j_child1"},
        {"axisFullPath": "|root|child1|child2", "parentAxisPath": "|root|child1",
         "jointName": ""},
    ])
    raise AssertionError("expected ValueError for empty jointName among multiple axes")
except ValueError as e:
    # only the offending axis should be named -- the list literal has exactly
    # one entry, so this also rules out the two valid axes leaking in.
    assert "missing on: ['|root|child1|child2']" in str(e), e
print("buildAxisTree rejects empty jointName on one axis among many OK")

# --- axisVectorForConvention ---
# axisVectorForConvention()가 실제로 maroMayaToRos와 같은 (x,y,z)->(x,-z,y)
# 재배치를 적용하는지, 값을 다시 베끼는 게 아니라 독립적으로 재확인한다
# (computeRelativeOrigin의 kZYX->kXYZ 발견과 같은 이유 -- "당연해 보이는
# 가정"이 이 계획에서 이미 두 번 틀렸다).
def _mayaToRosVector(v):
    x, y, z = v
    return (x, -z, y)

for conventionAxis, mayaLocal in ((0, (1.0, 0.0, 0.0)),
                                    (1, (0.0, 1.0, 0.0)),
                                    (2, (0.0, 0.0, 1.0))):
    expected = _mayaToRosVector(mayaLocal)
    got = urdf.axisVectorForConvention(conventionAxis)
    assert all(abs(a - b) < 1e-9 for a, b in zip(expected, got)), (
        conventionAxis, expected, got)

try:
    urdf.axisVectorForConvention(3)
    raise AssertionError("expected ValueError for out-of-range conventionAxis")
except ValueError:
    pass
print("axisVectorForConvention applies the maroMayaToRos basis remap OK")

# --- jointType ---
result = urdf.jointType([{"capType": 0}])
assert result == {"type": "continuous", "lower": None, "upper": None, "mimic": None}, result

result = urdf.jointType([
    {"capType": 0},
    {"capType": 1, "enabled": True, "min": -1.0, "max": 1.0},
])
assert result == {"type": "revolute", "lower": -1.0, "upper": 1.0, "mimic": None}, result

# limit 있지만 이 축 성분에서는 꺼져 있으면 continuous로 취급.
result = urdf.jointType([
    {"capType": 0},
    {"capType": 1, "enabled": False, "min": -1.0, "max": 1.0},
])
assert result["type"] == "continuous", result

result = urdf.jointType([{"capType": 4}])
assert result == {"type": "prismatic", "lower": -1.0e6, "upper": 1.0e6, "mimic": None}, result

result = urdf.jointType([
    {"capType": 4},
    {"capType": 5, "enabled": True, "min": 0.0, "max": 0.5},
])
assert result == {"type": "prismatic", "lower": 0.0, "upper": 0.5, "mimic": None}, result

result = urdf.jointType([
    {"capType": 6, "ratio": 2.0, "offset": 0.1, "sourceJointName": "shoulder"},
])
assert result["type"] == "continuous", result
assert result["mimic"] == {"joint": "shoulder", "multiplier": 2.0, "offset": 0.1}, result
assert result["lower"] is None, result
assert result["upper"] is None, result

result = urdf.jointType([
    {"capType": 7, "ratio": 1.5, "offset": 0.0, "sourceJointName": "elbow"},
])
assert result["type"] == "prismatic", result
assert result["mimic"] == {"joint": "elbow", "multiplier": 1.5, "offset": 0.0}, result
assert result["lower"] is None, result
assert result["upper"] is None, result

result = urdf.jointType([])
assert result == {"type": "fixed", "lower": None, "upper": None, "mimic": None}, result

result = urdf.jointType([{"capType": 2}, {"capType": 3}])
assert result["type"] == "fixed", result
print("jointType OK")

import math

import maya.api.OpenMaya as om2

# --- computeRelativeOrigin: 항등/평행이동만 있는 쉬운 경우 ---
xyz, rpy = urdf.computeRelativeOrigin((0, 0, 0), (0, 0, 0, 1), (0, 0, 0), (0, 0, 0, 1))
assert xyz == (0.0, 0.0, 0.0), xyz
assert all(abs(v) < 1e-9 for v in rpy), rpy

xyz, rpy = urdf.computeRelativeOrigin(
    (0, 0, 0), (0, 0, 0, 1), (1.0, 2.0, 3.0), (0, 0, 0, 1))
assert all(abs(a - b) < 1e-9 for a, b in zip(xyz, (1.0, 2.0, 3.0))), xyz
assert all(abs(v) < 1e-9 for v in rpy), rpy
print("computeRelativeOrigin identity/translation OK")

# --- computeRelativeOrigin: 회전이 URDF의 rpy 관례(고정축 X->Y->Z)와
# 실제로 일치하는지 독립 검증 ---
# brief의 최초 가설(kZYX)은 아래 2)의 1차 원리 행렬 비교로 실측 반증됐다
# (최대 성분 오차 ~0.33, 우연한 수치 오차 범위를 훨씬 벗어남). 실제로
# URDF의 고정축 X->Y->Z 관례와 일치하는 것은 kXYZ다(같은 비교에서 최대
# 오차 ~1e-16). 아래 기대값(1차 원리 공식)은 바꾸지 않았다 -- 바뀐 것은
# om2 쪽 재정렬 대상(kZYX -> kXYZ)뿐이다.
roll, pitch, yaw = 0.3, 0.5, 0.7

# 1) om2의 kXYZ로 만든 회전을 자식에 주고, 그걸 다시 computeRelativeOrigin
#    으로 뽑아냈을 때 같은 세 각도가 나오는지(자기 일관성 -- 이것만으로는
#    kXYZ가 URDF와 같다는 것까지는 증명 못 한다, 아래 2)가 그걸 증명한다).
childQuat = om2.MEulerRotation(roll, pitch, yaw, om2.MEulerRotation.kXYZ).asQuaternion()
_, decodedRpy = urdf.computeRelativeOrigin(
    (0, 0, 0), (0, 0, 0, 1), (0, 0, 0), (childQuat.x, childQuat.y, childQuat.z, childQuat.w))
assert abs(decodedRpy[0] - roll) < 1e-9, decodedRpy
assert abs(decodedRpy[1] - pitch) < 1e-9, decodedRpy
assert abs(decodedRpy[2] - yaw) < 1e-9, decodedRpy

# 2) URDF 스펙이 정의하는 "고정축 X->Y->Z" 회전 행렬을 초등 삼각함수
#    공식(R = Rz(yaw) @ Ry(pitch) @ Rx(roll), 열벡터 관례)으로 직접
#    조립해서, om2가 kXYZ로 만든 행렬과 실제로 같은지 확인한다 -- om2
#    라이브러리에 대한 가정이 아니라 URDF 스펙 자체에서 나온 독립적인
#    기준이다.
def _rotX(a):
    c, s = math.cos(a), math.sin(a)
    return [[1, 0, 0], [0, c, -s], [0, s, c]]


def _rotY(a):
    c, s = math.cos(a), math.sin(a)
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]]


def _rotZ(a):
    c, s = math.cos(a), math.sin(a)
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def _matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


expectedColumnVectorMatrix = _matmul(_matmul(_rotZ(yaw), _rotY(pitch)), _rotX(roll))

m = om2.MEulerRotation(roll, pitch, yaw, om2.MEulerRotation.kXYZ).asMatrix()
# om2.MMatrix는 행벡터 관례를 쓴다 -- 열벡터 관례로 만든 위 공식과
# 비교하려면 전치해야 한다.
gotRowVectorMatrix = [[m.getElement(row, col) for col in range(3)] for row in range(3)]
gotColumnVectorMatrix = [[gotRowVectorMatrix[col][row] for col in range(3)] for row in range(3)]

for i in range(3):
    for j in range(3):
        assert abs(expectedColumnVectorMatrix[i][j] - gotColumnVectorMatrix[i][j]) < 1e-9, (
            "row {} col {}: URDF-spec formula gives {}, om2 kXYZ gives {} -- "
            "the reorder() target in computeRelativeOrigin is wrong, fix it "
            "(don't weaken this assertion)".format(
                i, j, expectedColumnVectorMatrix[i][j], gotColumnVectorMatrix[i][j]))
print("computeRelativeOrigin rotation matches URDF rpy convention (independently verified) OK")

# --- buildUrdfXml ---
robotEl = urdf.buildUrdfXml(
    "test_robot",
    links=[{"name": "base"}, {"name": "arm1"}],
    joints=[{
        "name": "j1", "type": "revolute", "parent": "base", "child": "arm1",
        "originXyz": (0.1, 0.2, 0.3), "originRpy": (0.0, 0.0, 0.0),
        "axis": (1.0, 0.0, 0.0), "lower": -1.0, "upper": 1.0, "mimic": None,
    }])
assert robotEl.get("name") == "test_robot"
links = robotEl.findall("link")
assert [l.get("name") for l in links] == ["base", "arm1"], links
joints = robotEl.findall("joint")
assert len(joints) == 1, joints
j = joints[0]
assert j.get("name") == "j1" and j.get("type") == "revolute", j.attrib
assert j.find("parent").get("link") == "base"
assert j.find("child").get("link") == "arm1"
assert j.find("origin").get("xyz") == "0.100000 0.200000 0.300000"
assert j.find("axis").get("xyz") == "1 0 0"
limitEl = j.find("limit")
assert limitEl.get("lower") == "-1.000000" and limitEl.get("upper") == "1.000000"
assert limitEl.get("effort") == "1000" and limitEl.get("velocity") == "10"
assert j.find("mimic") is None
print("buildUrdfXml revolute joint OK")

# fixed 조인트는 axis/limit이 없어야 한다.
robotEl = urdf.buildUrdfXml(
    "test_robot2", links=[{"name": "a"}, {"name": "b"}],
    joints=[{"name": "jf", "type": "fixed", "parent": "a", "child": "b",
             "originXyz": (0, 0, 0), "originRpy": (0, 0, 0),
             "axis": None, "lower": None, "upper": None, "mimic": None}])
jf = robotEl.find("joint")
assert jf.find("axis") is None
assert jf.find("limit") is None
print("buildUrdfXml fixed joint has no axis/limit OK")

# continuous 조인트는 axis는 있지만 limit은 없어야 한다.
robotEl = urdf.buildUrdfXml(
    "test_robot3", links=[{"name": "a"}, {"name": "b"}],
    joints=[{"name": "jc", "type": "continuous", "parent": "a", "child": "b",
             "originXyz": (0, 0, 0), "originRpy": (0, 0, 0),
             "axis": (0.0, 1.0, 0.0), "lower": None, "upper": None, "mimic": None}])
jc = robotEl.find("joint")
assert jc.find("axis") is not None
assert jc.find("limit") is None
print("buildUrdfXml continuous joint has axis but no limit OK")

# mimic이 있으면 <mimic>이 나와야 한다.
robotEl = urdf.buildUrdfXml(
    "test_robot4", links=[{"name": "a"}, {"name": "b"}],
    joints=[{"name": "jm", "type": "revolute", "parent": "a", "child": "b",
             "originXyz": (0, 0, 0), "originRpy": (0, 0, 0),
             "axis": (1.0, 0.0, 0.0), "lower": -1.0, "upper": 1.0,
             "mimic": {"joint": "source_j", "multiplier": 2.0, "offset": 0.1}}])
mimicEl = robotEl.find("joint").find("mimic")
assert mimicEl.get("joint") == "source_j"
assert mimicEl.get("multiplier") == "2.000000"
assert mimicEl.get("offset") == "0.100000"
print("buildUrdfXml mimic joint OK")

# --- 종단 간: 실제 2축 체인을 만들어 export()까지 확인 ---
import tempfile

rootMesh = cmds.polyCube(name="baseLink")[0]
childMesh = cmds.polyCube(name="armLink")[0]
cmds.xform(childMesh, worldSpace=True, translation=(0.0, 10.0, 0.0))

rootAxis = cmds.createNode("maroAxis")
cmds.maroBindAxis(rootAxis, rootMesh)
cmds.setAttr(rootAxis + ".jointName", "base_joint", type="string")
rootAxis = cmds.ls(rootAxis, long=True)[0]
# 루트 축은 origin 계산에 안 쓰이므로(설계 스펙 §3.2 정정) 로케이터
# 위치는 원점 그대로 둬도 무방하다 -- 실제로도 옮기지 않는다.

childAxis = cmds.createNode("maroAxis")
cmds.maroBindAxis(childAxis, childMesh)
cmds.setAttr(childAxis + ".jointName", "arm_joint", type="string")
childAxis = cmds.ls(childAxis, long=True)[0]
# 관절 위치를 실제 childMesh 위치에 맞춰 로케이터를 옮긴다(설계 스펙의
# 새 리깅 관례 -- 로케이터 자신의 위치가 곧 관절 원점).
cmds.xform(cmds.listRelatives(childAxis, parent=True, fullPath=True)[0],
           worldSpace=True, translation=(0.0, 10.0, 0.0))
cmds.setAttr(childAxis + ".conventionAxis", 0)  # X축

cmds.maroConnectAxis(childAxis, rootAxis)
cmds.maroAddCapability(childAxis, type="rotation")

# capType 1(rotation limit) 실측 -- 세션 각도 단위를 일부러 "deg"로 바꾼
# 채로 minX/maxX를 라디안 등가값의 "도" 표현(-57.29578/57.29578 =
# ∓1 rad)으로 넣는다. minX/maxX는 MFnUnitAttribute라 setAttr이 그 순간의
# UI 각도 단위로 해석해 저장하지만, MaroLimitNode::compute는 그걸
# .asAngle().asRadians()로 읽어 "진짜" 라디안 값(-1.0/1.0, 세션과 무관)을
# capMin/capMax(평범한 double)에 쓴다 -- 그래서 cmds.getAttr(capMin)은
# 어느 세션에서 설정했든 항상 -1.0을 돌려준다.
#
# 세션이 rad였다면 om2.MAngle.uiUnit()이 kRadians가 되어, 이미 제거된
# 버그(MAngle(raw, uiUnit()).asRadians())가 부활해도 MAngle(-1.0,
# kRadians).asRadians() == -1.0인 항등 연산이 되어 이 테스트가 절대 못
# 잡는다(이전 라운드에서 실제로 그랬던 결함). deg 세션에서는 그 버그가
# 부활하면 raw(-1.0, 이미 진짜 라디안 값)를 MAngle(-1.0, kDegrees)로
# 잘못 해석해 .asRadians()가 다시 도->라디안 변환을 적용, 기대값(-1.0)의
# 1/57 수준인 ~-0.0175로 벗어난 값이 나온다 -- 그래서 이 세션 설정이
# 실제로 버그를 잡아낼 수 있다. 아래 lower/upper 단정은
# _resolveCapabilityDetails가 capMin/capMax를 감싸지 않고 그대로
# 통과시키는지 확인한다.
cmds.currentUnit(angle="deg")
limitNode = cmds.maroAddCapability(childAxis, type="limit")[0]
cmds.setAttr(limitNode + ".axisDirection", 1, 0, 0, type="double3")
cmds.setAttr(limitNode + ".min", -57.29578)  # -1 rad in degrees
cmds.setAttr(limitNode + ".max", 57.29578)   # +1 rad in degrees

flatAxes = cmds.maroListAxisNodes()
axisRows = urdf.sliceAxisRows(flatAxes)
assert len(axisRows) == 2, axisRows

tmpPath = os.path.join(tempfile.mkdtemp(prefix="maro_urdf_export_test_"),
                        "maro_urdf_export_test.urdf")
result = urdf.export(path=tmpPath)
assert result == tmpPath, result
assert os.path.isfile(tmpPath), tmpPath

import xml.etree.ElementTree as ET2
tree = ET2.parse(tmpPath)
robotEl = tree.getroot()
linkNames = sorted(l.get("name") for l in robotEl.findall("link"))
assert linkNames == sorted(["baseLink", "armLink"]), linkNames
jointEls = robotEl.findall("joint")
assert len(jointEls) == 1, jointEls
j = jointEls[0]
assert j.get("name") == "arm_joint", j.attrib
assert j.get("type") == "revolute", j.attrib  # limit capability가 활성화됐으므로 continuous가 아니다
limitEl = j.find("limit")
assert limitEl is not None, "expected a <limit> element on a revolute joint"
lower = float(limitEl.get("lower"))
upper = float(limitEl.get("upper"))
# capMin/capMax는 항상 라디안이다(단위와 무관, MaroLimitNode::compute가
# 저장 전에 변환) -- _resolveCapabilityDetails가 그대로 통과시켜야 한다.
assert abs(lower - (-1.0)) < 1e-6, lower  # would be ~-0.0175 (57x too small) if the .uiUnit() bug were reintroduced
assert abs(upper - 1.0) < 1e-6, upper
print("end-to-end revolute limit: lower={} upper={} (radians, matches input, not unit-trapped "
      "even under a degrees session)".format(lower, upper))
# 이 케이스가 끝났으니 이 파일의 나머지가 기대하는 라디안 세션으로
# 즉시 되돌린다 -- 안 그러면 아래(또는 이후 실행되는) 라디안 가정
# 단정들이 조용히 깨진다.
cmds.currentUnit(angle="rad")

# conventionAxis=0(X)이므로 conventionInvert가 꺼져 있을 때 axisVectorForConvention의
# 수정(C1) 그대로 "1 0 0"이 나와야 한다.
axisEl = j.find("axis")
assert axisEl is not None, "expected an <axis> element on a revolute joint"
assert axisEl.get("xyz") == "1 0 0", axisEl.get("xyz")
print("end-to-end axis xyz honors the maroMayaToRos remap for conventionAxis=X OK")

originXyz = [float(v) for v in j.find("origin").get("xyz").split()]
# childMesh는 rootMesh 기준 Y로 10cm = 0.1m 위에 있다(Maya 내부 단위는
# 센티미터, ROS는 미터). Y-up(Maya) -> Z-up(ROS) 변환 때문에 정확히 어느
# 성분에 0.1이 나오는지는 mayaToRosPosition의 실제 축 재배치에 달려 있다
# -- 여기서는 "원점이 원점(0,0,0)이 아니고, 크기가 대략 0.1m"라는 것만
# 느슨하게 확인한다(정확한 성분별 값은 수동 체크리스트의 RViz2 확인이
# 담당).
originMagnitude = sum(v * v for v in originXyz) ** 0.5
assert abs(originMagnitude - 0.1) < 1e-3, originXyz
print("end-to-end export() with a real 2-axis chain OK")

# --- conventionInvert(I2): 라이브 ROS 퍼블리시 경로(Convert.cpp의
# axisVectorOf)가 이미 존중하는 플래그를 exporter도 존중해야 한다 --
# 안 그러면 이 플래그를 쓰는 리그는 URDF 조인트가 실제 라이브 동작과
# 반대 방향으로 돈다. 같은 childAxis(conventionAxis=0=X)에 conventionInvert만
# 켜고 다시 내보내서 axis xyz가 "1 0 0" -> "-1 0 0"으로 뒤집히는지 확인한다.
cmds.setAttr(childAxis + ".conventionInvert", True)

tmpPathInvert = os.path.join(tempfile.mkdtemp(prefix="maro_urdf_export_test_invert_"),
                              "maro_urdf_export_test_invert.urdf")
resultInvert = urdf.export(path=tmpPathInvert)
assert resultInvert == tmpPathInvert, resultInvert

treeInvert = ET2.parse(tmpPathInvert)
jointElsInvert = treeInvert.getroot().findall("joint")
assert len(jointElsInvert) == 1, jointElsInvert
axisElInvert = jointElsInvert[0].find("axis")
assert axisElInvert is not None, "expected an <axis> element on a revolute joint"
assert axisElInvert.get("xyz") == "-1 0 0", axisElInvert.get("xyz")
print("end-to-end conventionInvert flips exported axis xyz (1 0 0 -> -1 0 0) OK")

cmds.setAttr(childAxis + ".conventionInvert", False)
os.remove(tmpPathInvert)

os.remove(tmpPath)

# --- 시각 메쉬 (슬라이스 1) ---
# struct를 여기서 다시 import한다 -- Task 1의 테스트 절은 이 파일의 **끝**에
# 붙으므로, 이 지점(374행 근처)에서는 아직 _struct가 정의되지 않았다.
# 재import는 무해하다.
import struct as _struct

# 위 export()가 이미 돌았다. 폴리큐브는 mesh 셰이프를 가지므로 두 링크 다
# <visual>과 STL 파일이 나와야 한다.
_meshDir = os.path.join(os.path.dirname(os.path.abspath(tmpPath)), "meshes")
assert os.path.isdir(_meshDir), _meshDir
for _linkName in ("baseLink", "armLink"):
    _stl = os.path.join(_meshDir, _linkName + ".stl")
    assert os.path.isfile(_stl), _stl
    # 기본 폴리큐브는 6면 * 2 = 12 삼각형이다(실측 확인).
    _count = _struct.unpack("<I", open(_stl, "rb").read()[80:84])[0]
    assert _count == 12, (_linkName, _count)

for _linkEl in robotEl.findall("link"):
    _vis = _linkEl.find("visual")
    assert _vis is not None, "expected <visual> on " + _linkEl.get("name")
    _fn = _vis.find("geometry/mesh").get("filename")
    _expected = "package://{}/meshes/{}.stl".format(
        os.path.splitext(os.path.basename(tmpPath))[0], _linkEl.get("name"))
    assert _fn == _expected, (_fn, _expected)
print("visual meshes exported OK")

# 부모 링크가 자식 링크의 메쉬를 삼키지 않는다.
#
# allDescendents로 훑으면 정확히 이 상황에서 부모가 자식 지오메트리까지
# 가져가 삼각형 수가 24가 된다 -- 조인트 체인에서는 자식 링크가 부모의
# DAG 자손이기 때문이다(스펙 §3).
cmds.file(new=True, force=True)
_pBase = cmds.polyCube(name="pBase")[0]
_pChild = cmds.polyCube(name="pChild")[0]
cmds.parent(_pChild, _pBase)
_aBase = cmds.createNode("maroAxis")
cmds.maroBindAxis(_aBase, _pBase)
cmds.setAttr(_aBase + ".jointName", "j_base", type="string")
_aBase = cmds.ls(_aBase, long=True)[0]
_aChild = cmds.createNode("maroAxis")
cmds.maroBindAxis(_aChild, cmds.ls(_pChild, long=True)[0])
cmds.setAttr(_aChild + ".jointName", "j_child", type="string")
_aChild = cmds.ls(_aChild, long=True)[0]
cmds.maroConnectAxis(_aChild, _aBase)
_nestPath = os.path.join(tempfile.mkdtemp(prefix="maro_urdf_nest_"), "nested.urdf")
assert urdf.export(path=_nestPath) == _nestPath
_nestMeshDir = os.path.join(os.path.dirname(os.path.abspath(_nestPath)), "meshes")
_baseStl = os.path.join(_nestMeshDir, "pBase.stl")
_baseCount = _struct.unpack("<I", open(_baseStl, "rb").read()[80:84])[0]
assert _baseCount == 12, (
    "the parent link swallowed its child's geometry (allDescendents trap): %d"
    % _baseCount)
print("parent link does not swallow child geometry OK")

# 메쉬가 없는 링크는 <visual> 없이 나간다(에러가 아니다).
cmds.file(new=True, force=True)
_bone = cmds.createNode("joint", name="boneOnly")
_aBone = cmds.createNode("maroAxis")
cmds.maroBindAxis(_aBone, _bone)
cmds.setAttr(_aBone + ".jointName", "j_bone", type="string")
_bonePath = os.path.join(tempfile.mkdtemp(prefix="maro_urdf_bone_"), "bone.urdf")
assert urdf.export(path=_bonePath) == _bonePath
_boneRoot = ET2.parse(_bonePath).getroot()
assert _boneRoot.find("link").find("visual") is None, \
    "a mesh-less link must have no <visual>"
assert not os.path.isdir(
    os.path.join(os.path.dirname(os.path.abspath(_bonePath)), "meshes")), \
    "no meshes/ directory should be created when nothing has geometry"
print("mesh-less link exports without <visual> OK")

# --- writeBinaryStl (슬라이스 1) ---
import struct as _struct

_stlDir = tempfile.mkdtemp(prefix="maro_stl_")
_stlPath = os.path.join(_stlDir, "one.stl")
# 반시계 방향(CCW) 삼각형 -- 법선이 +Z여야 한다.
urdf.writeBinaryStl([((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))], _stlPath)
_raw = open(_stlPath, "rb").read()
assert len(_raw) == 84 + 50, len(_raw)
assert _raw[:16] == b"Maro URDF export", _raw[:16]
assert _raw[16:80] == b"\0" * 64, "header must be zero-padded to 80 bytes"
assert _struct.unpack("<I", _raw[80:84])[0] == 1
_vals = _struct.unpack("<12fH", _raw[84:134])
assert _vals[0:3] == (0.0, 0.0, 1.0), _vals[0:3]
assert _vals[3:12] == (0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0), _vals[3:12]
assert _vals[12] == 0, "attribute byte count must be 0"

# 삼각형 0개도 유효한 STL이다(헤더 + 개수 0).
_emptyPath = os.path.join(_stlDir, "empty.stl")
urdf.writeBinaryStl([], _emptyPath)
assert len(open(_emptyPath, "rb").read()) == 84

# 축퇴 삼각형(면적 0)은 법선을 0으로 둔다 -- 0으로 나누면 안 된다.
_degPath = os.path.join(_stlDir, "deg.stl")
urdf.writeBinaryStl([((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))], _degPath)
_degVals = _struct.unpack("<12fH", open(_degPath, "rb").read()[84:134])
assert _degVals[0:3] == (0.0, 0.0, 0.0), _degVals[0:3]
print("writeBinaryStl OK")

# --- mayaTrianglesToRosMeters (슬라이스 1) ---
# Maya 내부 단위는 항상 센티미터다(실측: om2.MDistance.internalUnit() == 6,
# .asMeters() == 0.01). 100 단위 = 1 미터.
_converted = urdf.mayaTrianglesToRosMeters(
    [((100.0, 0.0, 0.0), (0.0, 100.0, 0.0), (0.0, 0.0, 100.0))])
assert len(_converted) == 1
_a, _b, _c = _converted[0]
# 축 재배치 (x,y,z) -> (x,-z,y), 그리고 cm -> m.
assert _a == (1.0, 0.0, 0.0), _a          # maya +X -> ros +X
assert _b == (0.0, 0.0, 1.0), _b          # maya +Y(up) -> ros +Z(up)
assert _c == (0.0, -1.0, 0.0), _c         # maya +Z -> ros -Y

# 와인딩 보존: 이 재배치의 행렬식이 +1(반사가 아닌 회전)이므로, 변환 후
# 삼각형의 법선은 "변환 전 법선을 같은 방식으로 재배치한 것"과 같아야
# 한다. 반사였다면 부호가 뒤집혀 RViz에서 안팎이 뒤집힌 메쉬가 나온다.
_beforeNormal = urdf._triangleNormal(
    (100.0, 0.0, 0.0), (0.0, 100.0, 0.0), (0.0, 0.0, 100.0))
_expectedNormal = (_beforeNormal[0], -_beforeNormal[2], _beforeNormal[1])
_afterNormal = urdf._triangleNormal(_a, _b, _c)
assert all(abs(x - y) < 1e-9 for x, y in zip(_expectedNormal, _afterNormal)), \
    (_expectedNormal, _afterNormal)

assert urdf.mayaTrianglesToRosMeters([]) == []
print("mayaTrianglesToRosMeters OK")

# --- sanitizeMeshFileName (슬라이스 1) ---
_used = set()
assert urdf.sanitizeMeshFileName("baseLink", _used) == "baseLink"
# 네임스페이스가 붙은 노드: _shortName은 "|"로만 쪼개므로 ":"가 그대로
# 남는다. ":"는 Windows 파일명에 쓸 수 없다.
assert urdf.sanitizeMeshFileName("ns:cube", _used) == "ns_cube"
# 살균 결과가 충돌하면 일련번호를 붙인다.
assert urdf.sanitizeMeshFileName("ns/cube", _used) == "ns_cube_1"
assert urdf.sanitizeMeshFileName("", _used) == "link"
assert _used == {"baseLink", "ns_cube", "ns_cube_1", "link"}, _used
print("sanitizeMeshFileName OK")

# --- buildUrdfXml <visual> (슬라이스 1) ---
_visualRobot = urdf.buildUrdfXml(
    "rob",
    [{"name": "withMesh", "visualMesh": "package://rob/meshes/withMesh.stl"},
     {"name": "noMesh", "visualMesh": None},
     {"name": "legacy"}],          # 키 자체가 없는 기존 호출부도 그대로 동작해야 한다
    [])
_byName = {l.get("name"): l for l in _visualRobot.findall("link")}
_v = _byName["withMesh"].find("visual")
assert _v is not None, "a link with visualMesh must emit <visual>"
assert _v.find("geometry/mesh").get("filename") == "package://rob/meshes/withMesh.stl"
# 정점을 이미 링크 프레임으로 구웠으므로 원점은 항등이다.
assert _v.find("origin").get("xyz") == "0 0 0", _v.find("origin").attrib
assert _v.find("origin").get("rpy") == "0 0 0", _v.find("origin").attrib
assert _byName["noMesh"].find("visual") is None
assert _byName["legacy"].find("visual") is None
print("buildUrdfXml <visual> OK")

# --- 최종 리뷰 Finding 1 회귀: 메쉬는 바인딩된 트랜스폼이 아니라
# maroAxis 로케이터의 부모 트랜스폼(=URDF 링크 프레임) 기준으로 구워야
# 한다 ---
#
# 위쪽의 종단 간 픽스처(baseLink/armLink)는 자식 로케이터를 일부러 자식
# 메쉬 위치로 옮겨(306-307행) 두 프레임을 일치시킨다 -- 그래서 이 결함을
# 절대 못 잡는다(디자인 스펙 §4 [정정, 2026-09-07] 참고). 이 픽스처는
# 반대로 로케이터와 바인딩된 트랜스폼을 평행이동과 회전 양쪽에서 일부러
# 어긋나게 둔다 -- 실제 리깅 관례(관절 위치에 로케이터, 메쉬는 자기
# 피벗)를 흉내낸다.
#
# [정정, 2차 수정 파동 Finding B] `cmds.file(new=True, force=True)`는 세션
# 각도 단위를 "deg"로 되돌린다(실측 확인) -- 369행에서 "rad"로 복원해 둔
# 것과 무관하게, 새 씬을 열 때마다 매번 다시 깨진다. 그래서 아래에서
# 명시적으로 다시 "rad"를 설정한다 -- 그래야 다음 xform 호출의
# `math.pi / 2.0`이 실제로 90도가 된다. 이 명시적 호출이 없으면
# `rotation=(0, 0, math.pi/2)`는 "1.5707963도"로 해석돼(180/pi 배 더 작은
# 값) 이 픽스처가 겨누는 회전 오프셋을 57배 약하게만 검증한다 -- 여전히
# 결함을 잡긴 하지만(0을 아니게는 만드니까) 스펙이 실측한 시나리오
# (90도 회전 어긋남)를 전혀 재현하지 못한다.
cmds.file(new=True, force=True)
cmds.currentUnit(angle="rad")

_f1RootMesh = cmds.polyCube(name="f1Base")[0]
_f1RootAxis = cmds.createNode("maroAxis")
cmds.maroBindAxis(_f1RootAxis, _f1RootMesh)
cmds.setAttr(_f1RootAxis + ".jointName", "f1_base_joint", type="string")
_f1RootAxis = cmds.ls(_f1RootAxis, long=True)[0]
# 루트 축은 origin 계산에 안 쓰이므로(기존 e2e 픽스처와 같은 이유) 원점
# 그대로 둔다.

_f1ChildMesh = cmds.polyCube(name="f1Arm")[0]
# "팔 메쉬 피벗 y=20cm" -- 디자인 스펙 §4 [정정]의 실측 시나리오와 같다.
cmds.xform(_f1ChildMesh, worldSpace=True, translation=(0.0, 20.0, 0.0))

_f1ChildAxis = cmds.createNode("maroAxis")
cmds.maroBindAxis(_f1ChildAxis, _f1ChildMesh)
cmds.setAttr(_f1ChildAxis + ".jointName", "f1_arm_joint", type="string")
_f1ChildAxis = cmds.ls(_f1ChildAxis, long=True)[0]
_f1ChildAxisTransform = cmds.listRelatives(_f1ChildAxis, parent=True, fullPath=True)[0]
# 관절(로케이터)은 메쉬 피벗과 다른 y=10cm에 두고, Z축으로 90도 돌려
# 둔다 -- 평행이동과 회전 둘 다에서 두 프레임이 어긋나게 한다. 세션 각도
# 단위는 위(579-580행)에서 이 픽스처 전용으로 명시적으로 "rad"를 다시
# 설정해 뒀으므로 math.pi/2 == 90도다.
cmds.xform(_f1ChildAxisTransform, worldSpace=True, translation=(0.0, 10.0, 0.0),
           rotation=(0.0, 0.0, math.pi / 2.0))

cmds.maroConnectAxis(_f1ChildAxis, _f1RootAxis)

_f1MeshDir = tempfile.mkdtemp(prefix="maro_urdf_f1_")
_f1Path = os.path.join(_f1MeshDir, "f1.urdf")
assert urdf.export(path=_f1Path) == _f1Path

# 기대값은 코드 아래 함수(_linkMeshTriangles/_writeLinkMeshes)를 다시
# 부르지 않고 독립적으로 구한다 -- childMesh는 대칭 큐브이므로 그 월드
# 중심은 자신의 피벗 월드 위치(0, 20, 0)cm와 같다(자기 자신의 회전은
# 손대지 않았으므로 무관하다). 그 점을 로케이터의 부모 트랜스폼(=링크
# 프레임)의 역행렬로 되돌리면 기대하는 링크-로컬 위치가 나온다 -- 이
# 파일의 computeRelativeOrigin 회전 검증과 같은 방식으로 om2를 직접
# 불러 독립 검증한다.
_f1FrameDag = om2.MSelectionList().add(_f1ChildAxisTransform).getDagPath(0)
_f1FrameInverse = _f1FrameDag.inclusiveMatrixInverse()
_f1MeshWorldCentroidMaya = om2.MPoint(0.0, 20.0, 0.0)  # cm
_f1ExpectedLocalMaya = _f1MeshWorldCentroidMaya * _f1FrameInverse
# mayaTrianglesToRosMeters와 같은 식: (x,y,z)->(x,-z,y), cm->m.
_f1ExpectedLocalRos = (
    _f1ExpectedLocalMaya.x * 0.01,
    -_f1ExpectedLocalMaya.z * 0.01,
    _f1ExpectedLocalMaya.y * 0.01,
)
# 정합성 확인: 두 프레임이 실제로 어긋나 있으므로 기대값이 원점이면 안
# 된다(원점이면 이 테스트가 아무것도 구분하지 못한다).
_f1ExpectedMagnitude = sum(v * v for v in _f1ExpectedLocalRos) ** 0.5
assert _f1ExpectedMagnitude > 1e-3, (
    "test setup sanity: locator and bound transform must not be coincident, "
    "got expected local {}".format(_f1ExpectedLocalRos))

_f1MeshFile = os.path.join(_f1MeshDir, "meshes", "f1Arm.stl")
assert os.path.isfile(_f1MeshFile), _f1MeshFile
_f1Raw = open(_f1MeshFile, "rb").read()
_f1Count = _struct.unpack("<I", _f1Raw[80:84])[0]
assert _f1Count == 12, _f1Count
_f1Verts = []
for _f1I in range(_f1Count):
    _f1Vals = _struct.unpack("<12fH", _f1Raw[84 + _f1I * 50: 84 + _f1I * 50 + 50])
    _f1Verts.append(_f1Vals[3:6])
    _f1Verts.append(_f1Vals[6:9])
    _f1Verts.append(_f1Vals[9:12])
_f1Xs = [v[0] for v in _f1Verts]
_f1Ys = [v[1] for v in _f1Verts]
_f1Zs = [v[2] for v in _f1Verts]
# 대칭 큐브의 실제 중심은 바운딩 박스 중심과 같다 -- 삼각화가 정점을
# 균등하지 않게 반복해도(getTriangles) 이 중심 계산에는 영향이 없다.
_f1Centroid = ((min(_f1Xs) + max(_f1Xs)) / 2.0,
               (min(_f1Ys) + max(_f1Ys)) / 2.0,
               (min(_f1Zs) + max(_f1Zs)) / 2.0)
assert all(abs(a - b) < 1e-4 for a, b in zip(_f1Centroid, _f1ExpectedLocalRos)), (
    "mesh baked in the wrong frame -- got centre {} in the link frame, expected "
    "{} (derived independently from the locator's own inverse matrix); if this "
    "is (0, 0, 0) instead, the mesh is still being baked in the bound target's "
    "own frame (final-review Finding 1)".format(_f1Centroid, _f1ExpectedLocalRos))
print("visual mesh baked in the locator's frame, not the bound target's frame "
      "(final-review Finding 1) OK: link-frame centre {}".format(_f1Centroid))

# --- 2차 수정 파동 Finding A 회귀: 로케이터 자신의 스케일이 구운 지오메트리를
# 오염시키면 안 된다 ---
#
# MaroAxisNode는 자체 size/localScale 속성이 없는 순수 MPxLocatorNode다
# (src/maro_plugin/MaroAxisNode.h) -- 로케이터를 뷰포트에서 보이게 만드는
# 유일한 방법은 그 부모 트랜스폼 자체를 스케일하는 것뿐이므로, 이 픽스처는
# 예외적인 리그가 아니라 흔한 리그다. `_gatherAxisWorldTransformRos`는 이미
# 이 트랜스폼에서 평행이동/회전만 읽는데(그 함수의 주석 참고),
# `_linkMeshTriangles`가 그 트랜스폼의 **전체** inclusiveMatrixInverse()
# (스케일/시어까지 포함)로 구우면 로케이터 트랜스폼에 스케일이 조금이라도
# 있을 때 메쉬 프레임과 조인트 프레임이 어긋난다.
#
# 위 최종 리뷰 Finding 1 픽스처와 같은 오프셋+회전 지오메트리(자식 메쉬
# 피벗은 월드 y=20cm, 로케이터는 월드 y=10cm에서 Z축 90도 회전)를 그대로
# 재사용하고, 로케이터의 트랜스폼에만 추가로 2배 스케일을 건다. 메쉬
# 자신은 스케일하지 않는다.
cmds.file(new=True, force=True)
cmds.currentUnit(angle="rad")

_saRootMesh = cmds.polyCube(name="saBase")[0]
_saRootAxis = cmds.createNode("maroAxis")
cmds.maroBindAxis(_saRootAxis, _saRootMesh)
cmds.setAttr(_saRootAxis + ".jointName", "sa_base_joint", type="string")
_saRootAxis = cmds.ls(_saRootAxis, long=True)[0]

_saChildMesh = cmds.polyCube(name="saArm")[0]  # 기본 폴리큐브: 한 변 1cm, 스케일 없음
cmds.xform(_saChildMesh, worldSpace=True, translation=(0.0, 20.0, 0.0))

_saChildAxis = cmds.createNode("maroAxis")
cmds.maroBindAxis(_saChildAxis, _saChildMesh)
cmds.setAttr(_saChildAxis + ".jointName", "sa_arm_joint", type="string")
_saChildAxis = cmds.ls(_saChildAxis, long=True)[0]
_saChildAxisTransform = cmds.listRelatives(_saChildAxis, parent=True, fullPath=True)[0]
cmds.xform(_saChildAxisTransform, worldSpace=True, translation=(0.0, 10.0, 0.0),
           rotation=(0.0, 0.0, math.pi / 2.0))
# 이 픽스처가 겨누는 결함: 로케이터 자신의 트랜스폼에 2배 스케일을 건다.
# 메쉬는 손대지 않는다.
cmds.setAttr(_saChildAxisTransform + ".scaleX", 2.0)
cmds.setAttr(_saChildAxisTransform + ".scaleY", 2.0)
cmds.setAttr(_saChildAxisTransform + ".scaleZ", 2.0)

cmds.maroConnectAxis(_saChildAxis, _saRootAxis)

_saDir = tempfile.mkdtemp(prefix="maro_urdf_scale_")
_saPath = os.path.join(_saDir, "sa.urdf")
assert urdf.export(path=_saPath) == _saPath

_saTree = ET2.parse(_saPath)
_saJointEls = _saTree.getroot().findall("joint")
assert len(_saJointEls) == 1, _saJointEls
_saOriginXyz = [float(v) for v in _saJointEls[0].find("origin").get("xyz").split()]
_saOriginMagnitude = sum(v * v for v in _saOriginXyz) ** 0.5
# 조인트 원점은 _gatherAxisWorldTransformRos가 이미 평행이동/회전만 읽어서
# 만든다 -- 여기서 로케이터에 스케일을 추가로 건다고 값이 달라지면 안
# 된다(스케일 없는 종단 간 픽스처와 같은 ~0.1m, 387행 참고).
assert abs(_saOriginMagnitude - 0.1) < 1e-3, _saOriginXyz

# 기대하는 메쉬 중심을 결함 없이 독립적으로 구한다: om2로 로케이터
# 트랜스폼의 평행이동+회전"만" 읽어 강체(rigid) 역행렬을 손수 만든다 --
# _gatherAxisWorldTransformRos가 읽는 것과 정확히 같은 두 값이다. 일부러
# axisFrameDag.inclusiveMatrixInverse()를 쓰지 않는다 -- 그건 로케이터의
# 2배 스케일까지 그대로 포함해 버려서 겨누는 결함을 그대로 재현해 버린다.
_saFrameDag = om2.MSelectionList().add(_saChildAxisTransform).getDagPath(0)
_saFrameWorld = om2.MTransformationMatrix(_saFrameDag.inclusiveMatrix())
_saFramePos = _saFrameWorld.translation(om2.MSpace.kWorld)
_saFrameQuat = om2.MFnTransform(_saFrameDag).rotation(om2.MSpace.kWorld, asQuaternion=True)
_saRigid = om2.MTransformationMatrix()
_saRigid.setTranslation(_saFramePos, om2.MSpace.kWorld)
_saRigid.setRotation(_saFrameQuat)
_saRigidInverse = _saRigid.asMatrix().inverse()
_saMeshWorldCentroidMaya = om2.MPoint(0.0, 20.0, 0.0)  # cm, saArm 자신의 피벗
_saExpectedLocalMaya = _saMeshWorldCentroidMaya * _saRigidInverse
# mayaTrianglesToRosMeters와 같은 식: (x,y,z)->(x,-z,y), cm->m.
_saExpectedLocalRos = (
    _saExpectedLocalMaya.x * 0.01,
    -_saExpectedLocalMaya.z * 0.01,
    _saExpectedLocalMaya.y * 0.01,
)
_saExpectedMagnitude = sum(v * v for v in _saExpectedLocalRos) ** 0.5
# 정합성 확인: 강체 역행렬 기준 기대값은 스케일 없는 Finding-1 픽스처와
# 같은 지오메트리이므로 ~0.1m여야 한다(원점이면 이 테스트가 아무것도
# 구분하지 못한다).
assert abs(_saExpectedMagnitude - 0.1) < 1e-3, (
    "test setup sanity: expected centre should match the unscaled Finding-1 "
    "geometry (~0.1m), got {}".format(_saExpectedLocalRos))

_saMeshFile = os.path.join(_saDir, "meshes", "saArm.stl")
assert os.path.isfile(_saMeshFile), _saMeshFile
_saRaw = open(_saMeshFile, "rb").read()
_saCount = _struct.unpack("<I", _saRaw[80:84])[0]
assert _saCount == 12, _saCount
_saVerts = []
for _saI in range(_saCount):
    _saVals = _struct.unpack("<12fH", _saRaw[84 + _saI * 50: 84 + _saI * 50 + 50])
    _saVerts.append(_saVals[3:6])
    _saVerts.append(_saVals[6:9])
    _saVerts.append(_saVals[9:12])
_saXs = [v[0] for v in _saVerts]
_saYs = [v[1] for v in _saVerts]
_saZs = [v[2] for v in _saVerts]
_saExtent = (max(_saXs) - min(_saXs), max(_saYs) - min(_saYs), max(_saZs) - min(_saZs))
_saCentre = ((min(_saXs) + max(_saXs)) / 2.0,
             (min(_saYs) + max(_saYs)) / 2.0,
             (min(_saZs) + max(_saZs)) / 2.0)

# 기본 폴리큐브는 한 변 1cm(스케일 없음) -- 로케이터가 2배 스케일이어도
# 내보낸 STL의 한 변은 그대로 0.01m여야 한다(결함이 있으면 로케이터의
# 역스케일 때문에 0.005m로 반토막난다).
for _v in _saExtent:
    assert abs(_v - 0.01) < 1e-4, (
        "locator transform scale leaked into mesh geometry -- expected an "
        "unscaled 0.01m cube edge, got extent {}".format(_saExtent))
assert all(abs(a - b) < 1e-4 for a, b in zip(_saCentre, _saExpectedLocalRos)), (
    "mesh centre displaced by the locator's own scale -- got {}, expected {} "
    "(derived from the locator's rigid translation+rotation only, matching "
    "_gatherAxisWorldTransformRos; second-wave Finding A)".format(
        _saCentre, _saExpectedLocalRos))
print("locator transform scale (2x) does not contaminate baked mesh geometry "
      "OK: extent {} centre {} joint-origin magnitude {}".format(
          _saExtent, _saCentre, _saOriginMagnitude))

# --- 최종 리뷰 Finding 2 회귀: 디포머의 중간 셰이프(...ShapeOrig)가
# 삼각형을 두 배로 만들면 안 된다 ---
cmds.file(new=True, force=True)
_f2Mesh = cmds.polyCube(name="f2Bent")[0]
cmds.select(_f2Mesh, replace=True)
cmds.nonLinear(type="bend")  # 디포머 히스토리가 붙으면 셰이프에 ...ShapeOrig가 생긴다.

_f2Axis = cmds.createNode("maroAxis")
cmds.maroBindAxis(_f2Axis, _f2Mesh)
cmds.setAttr(_f2Axis + ".jointName", "f2_joint", type="string")

_f2Dir = tempfile.mkdtemp(prefix="maro_urdf_f2_")
_f2Path = os.path.join(_f2Dir, "f2.urdf")
assert urdf.export(path=_f2Path) == _f2Path

_f2Stl = os.path.join(_f2Dir, "meshes", "f2Bent.stl")
assert os.path.isfile(_f2Stl), _f2Stl
_f2Count = _struct.unpack("<I", open(_f2Stl, "rb").read()[80:84])[0]
assert _f2Count == 12, (
    "intermediate shape (...ShapeOrig) doubled the geometry -- got {} triangles, "
    "expected the undeformed count 12 (final-review Finding 2)".format(_f2Count))
print("bend-deformed mesh exports the undeformed triangle count, no "
      "intermediate-shape ghost body (final-review Finding 2) OK")

# --- 스킨 분할 귀속 규칙 (슬라이스 2) ---
# weights는 정점수 x influenceCount 평평한 배열이고, 정점 v의 인플루언스 k는
# weights[v * influenceCount + k]다(실측: getWeights가 그 모양을 준다).
_w = [0.9, 0.1,
      0.2, 0.8,
      0.5, 0.5]
assert urdf.dominantInfluence(_w, 0, 2) == (0, 0.9)
assert urdf.dominantInfluence(_w, 1, 2) == (1, 0.8)
# 동점이면 가장 작은 인덱스 -- influenceObjects() 순서상 먼저 오는 쪽이다.
# 임의로 고르면 같은 리그를 다시 내보낼 때 결과가 흔들린다.
assert urdf.dominantInfluence(_w, 2, 2) == (0, 0.5)
print("dominantInfluence OK")

# 다수결: 정점 2개를 가진 링크가 가져간다.
_links = {0: "|A", 1: "|A", 2: "|B"}
_best = {0: 0.9, 1: 0.7, 2: 0.95}
assert urdf.assignTriangleToLink(_links, _best, (0, 1, 2)) == "|A"

# 1:1:1 동점 -- 개별 가중치가 가장 큰 정점의 링크.
_links3 = {0: "|A", 1: "|B", 2: "|C"}
_best3 = {0: 0.4, 1: 0.9, 2: 0.6}
assert urdf.assignTriangleToLink(_links3, _best3, (0, 1, 2)) == "|B"
# 정점 순서를 바꿔도 결과가 같아야 한다 -- 이 성질이 없으면 같은 리그를
# 다시 내보낼 때 삼각형이 다른 링크로 옮겨간다.
assert urdf.assignTriangleToLink(_links3, _best3, (2, 0, 1)) == "|B"
assert urdf.assignTriangleToLink(_links3, _best3, (1, 2, 0)) == "|B"

# 어느 링크에도 안 속하는 정점은 표에서 빠진다(None).
_linksNone = {0: None, 1: None, 2: "|B"}
_bestNone = {0: 0.9, 1: 0.9, 2: 0.3}
# None은 후보가 아니므로 유일한 실제 링크인 |B가 가져간다.
assert urdf.assignTriangleToLink(_linksNone, _bestNone, (0, 1, 2)) == "|B"
# 셋 다 None이면 버린다.
assert urdf.assignTriangleToLink({0: None, 1: None, 2: None},
                                 {0: 1.0, 1: 1.0, 2: 1.0}, (0, 1, 2)) is None
print("assignTriangleToLink OK")

# --- 조상 walk (슬라이스 2) ---
cmds.file(new=True, force=True)
_wj1 = cmds.createNode("joint", name="wj1")
_wj2 = cmds.createNode("joint", name="wj2", parent=_wj1)
_wj3 = cmds.createNode("joint", name="wj3", parent=_wj2)
_wj1 = cmds.ls(_wj1, long=True)[0]
_wj2 = cmds.ls(_wj2, long=True)[0]
_wj3 = cmds.ls(_wj3, long=True)[0]
_walkLinks = {_wj1, _wj2}

assert urdf.influenceToLink(_wj1, _walkLinks) == _wj1, "a link maps to itself"
assert urdf.influenceToLink(_wj2, _walkLinks) == _wj2
# wj3는 링크가 아니다 -- 가장 가까운 조상 링크인 wj2로 접힌다. 캐릭터 리그의
# 손가락 조인트들이 손목 링크 하나로 묶이는 것이 이 경로다.
assert urdf.influenceToLink(_wj3, _walkLinks) == _wj2, "must fold into the nearest bound ancestor"
# 링크가 하나도 없으면 None -- 그 정점은 어느 조각에도 안 들어간다.
assert urdf.influenceToLink(_wj3, set()) is None
# 최상위까지 올라가도 못 찾으면 None(무한루프가 아니라 종료해야 한다).
assert urdf.influenceToLink(_wj3, {"|somethingElse"}) is None
print("influenceToLink OK")

# --- _splitSkinnedMeshes (슬라이스 2) ---
cmds.file(new=True, force=True)
_sj1 = cmds.createNode("joint", name="sj1")
cmds.xform(_sj1, translation=(0, 0, 0))
_sj2 = cmds.createNode("joint", name="sj2", parent=_sj1)
cmds.xform(_sj2, translation=(0, 10, 0))
_sj3 = cmds.createNode("joint", name="sj3", parent=_sj2)
cmds.xform(_sj3, translation=(0, 5, 0))
_skinMesh = cmds.polyCylinder(name="limb", height=20, subdivisionsHeight=6, radius=2)[0]
# 원통이 조인트 체인을 실제로 감싸게 올린다 -- 원점에 두면 y가 -10..10이라
# sj1이 전 영역을 지배해 분할이 아예 일어나지 않는다(실측으로 발견한 함정:
# 그런 픽스처는 "모두 첫 인플루언스로 보내는" 잘못된 구현도 통과시킨다).
cmds.xform(_skinMesh, translation=(0, 10, 0))
cmds.skinCluster(_sj1, _sj2, _sj3, _skinMesh, toSelectedBones=True)

_sj1 = cmds.ls(_sj1, long=True)[0]
_sj2 = cmds.ls(_sj2, long=True)[0]
# sj3는 일부러 링크로 만들지 않는다 -- 조상 walk로 sj2에 접혀야 한다.
_axS1 = cmds.createNode("maroAxis")
cmds.maroBindAxis(_axS1, _sj1)
_axS1 = cmds.ls(_axS1, long=True)[0]
_axS2 = cmds.createNode("maroAxis")
cmds.maroBindAxis(_axS2, _sj2)
_axS2 = cmds.ls(_axS2, long=True)[0]

_splitLinks = [
    {"name": "sj1", "targetPath": _sj1,
     "axisFramePath": urdf._axisParentTransformPath(_axS1)},
    {"name": "sj2", "targetPath": _sj2,
     "axisFramePath": urdf._axisParentTransformPath(_axS2)},
]
_pieces = urdf._splitSkinnedMeshes(_splitLinks, set())

# 두 링크 다 실제로 몫을 받아야 한다 -- 한쪽이 0이면 분할이 안 일어난 것이다.
assert _pieces.get(_sj1), "sj1 got no geometry"
assert _pieces.get(_sj2), "sj2 got no geometry (ancestor walk from sj3 may be broken)"

# 분할 불변식: 조각 삼각형 수의 합이 원본 삼각형 수와 같다(버려진 것 없음 --
# 모든 인플루언스가 링크로 해소되는 리그이므로).
_skinShape = cmds.listRelatives(_skinMesh, shapes=True, fullPath=True, type="mesh")[0]
_selTri = om2.MSelectionList()
_selTri.add(_skinShape)
_, _triIdx = om2.MFnMesh(_selTri.getDagPath(0)).getTriangles()
_originalTris = len(_triIdx) // 3
assert sum(len(v) for v in _pieces.values()) == _originalTris, (
    sum(len(v) for v in _pieces.values()), _originalTris)
print("split invariant OK: %d = %d + %d"
      % (_originalTris, len(_pieces[_sj1]), len(_pieces[_sj2])))

# 소비된 셰이프는 건너뛴다 -- 강체 경로가 이미 가져간 메쉬를 분할이 또
# 나눠 주면 같은 지오메트리가 두 번 나간다(설계 스펙 §3).
assert urdf._splitSkinnedMeshes(_splitLinks, {_skinShape}) == {}
print("consumed shapes are skipped OK")

# 어느 링크와도 연결되지 않은 skinCluster는 결과에 영향이 없다.
_otherJoint = cmds.createNode("joint", name="otherJ")
_otherMesh = cmds.polyCube(name="otherMesh")[0]
cmds.skinCluster(_otherJoint, _otherMesh, toSelectedBones=True)
_piecesAgain = urdf._splitSkinnedMeshes(_splitLinks, set())
assert sorted(_piecesAgain) == sorted(_pieces), "an unrelated skinCluster changed the result"
print("unrelated skinCluster is ignored OK")

# --- 스킨 링크가 실제로 <visual>을 갖는다 (슬라이스 2 통합) ---
cmds.file(new=True, force=True)
_ej1 = cmds.createNode("joint", name="ej1")
cmds.xform(_ej1, translation=(0, 0, 0))
_ej2 = cmds.createNode("joint", name="ej2", parent=_ej1)
cmds.xform(_ej2, translation=(0, 10, 0))
_eMesh = cmds.polyCylinder(name="eLimb", height=20, subdivisionsHeight=6, radius=2)[0]
cmds.xform(_eMesh, translation=(0, 10, 0))
_eSkin = cmds.skinCluster(_ej1, _ej2, _eMesh, toSelectedBones=True)[0]
# 가중치를 **명시적으로** 준다. Maya 기본 스무스 바인드에 맡기면 조인트가
# 둘뿐일 때 루트가 전 정점을 지배해(실측: 140/140) ej2가 받을 것이 없어지고,
# 그러면 이 테스트는 올바른 구현을 고장으로 신고한다. 기본 폴오프 휴리스틱은
# Maya 버전에 따라 달라질 수 있는 값이라 테스트가 기대서는 안 된다 --
# 위쪽 절반은 ej2, 아래쪽 절반은 ej1로 못박는다.
_eVertCount = cmds.polyEvaluate(_eMesh, vertex=True)
_eUpper = []
_eLower = []
for _v in range(_eVertCount):
    _comp = "{}.vtx[{}]".format(_eMesh, _v)
    if cmds.pointPosition(_comp, world=True)[1] > 10.0:
        _eUpper.append(_comp)
    else:
        _eLower.append(_comp)
assert _eUpper and _eLower, (len(_eUpper), len(_eLower))
cmds.skinPercent(_eSkin, _eUpper, transformValue=[(_ej2, 1.0)])
cmds.skinPercent(_eSkin, _eLower, transformValue=[(_ej1, 1.0)])

_eAx1 = cmds.createNode("maroAxis")
cmds.maroBindAxis(_eAx1, _ej1)
cmds.setAttr(_eAx1 + ".jointName", "e_base", type="string")
_eAx1 = cmds.ls(_eAx1, long=True)[0]
_eAx2 = cmds.createNode("maroAxis")
cmds.maroBindAxis(_eAx2, cmds.ls(_ej2, long=True)[0])
cmds.setAttr(_eAx2 + ".jointName", "e_arm", type="string")
_eAx2 = cmds.ls(_eAx2, long=True)[0]
cmds.maroConnectAxis(_eAx2, _eAx1)

_ePath = os.path.join(tempfile.mkdtemp(prefix="maro_urdf_skin_"), "skinned.urdf")
assert urdf.export(path=_ePath) == _ePath
_eRoot = ET2.parse(_ePath).getroot()
_eLinks = {l.get("name"): l for l in _eRoot.findall("link")}
assert set(_eLinks) == {"ej1", "ej2"}, sorted(_eLinks)
for _name, _el in _eLinks.items():
    assert _el.find("visual") is not None, "skinned link %s got no <visual>" % _name

# 두 STL이 각자 몫만 갖는다: 합이 원본 삼각형 수와 같고 어느 쪽도 비어있지 않다.
# `_struct`는 이 파일이 앞에서 이미 들여왔다.
_eMeshDir = os.path.join(os.path.dirname(os.path.abspath(_ePath)), "meshes")
_eCounts = {}
for _name in ("ej1", "ej2"):
    _raw = open(os.path.join(_eMeshDir, _name + ".stl"), "rb").read()
    _eCounts[_name] = _struct.unpack("<I", _raw[80:84])[0]
    assert _eCounts[_name] > 0, "%s got an empty STL" % _name
_eShape = cmds.listRelatives(_eMesh, shapes=True, fullPath=True, type="mesh")[0]
_eSel = om2.MSelectionList()
_eSel.add(_eShape)
_, _eTriIdx = om2.MFnMesh(_eSel.getDagPath(0)).getTriangles()
assert sum(_eCounts.values()) == len(_eTriIdx) // 3, (_eCounts, len(_eTriIdx) // 3)
print("skinned links export split geometry OK:", _eCounts)

# --- 강체가 우선이고, 그 메쉬는 분할에서 빠진다 (슬라이스 2) ---
cmds.file(new=True, force=True)
_rj1 = cmds.createNode("joint", name="rj1")
_rj2 = cmds.createNode("joint", name="rj2", parent=_rj1)
cmds.xform(_rj2, translation=(0, 10, 0))
# rj1의 직속 자식인 큐브를 rj1/rj2 둘로 스킨한다.
_rCube = cmds.polyCube(name="rCube")[0]
cmds.parent(_rCube, _rj1)
_rCube = cmds.ls(_rCube, long=True)[0]
cmds.skinCluster(_rj1, _rj2, _rCube, toSelectedBones=True)

_rAx1 = cmds.createNode("maroAxis")
cmds.maroBindAxis(_rAx1, cmds.ls(_rj1, long=True)[0])
cmds.setAttr(_rAx1 + ".jointName", "r_base", type="string")
_rAx1 = cmds.ls(_rAx1, long=True)[0]
_rAx2 = cmds.createNode("maroAxis")
cmds.maroBindAxis(_rAx2, cmds.ls(_rj2, long=True)[0])
cmds.setAttr(_rAx2 + ".jointName", "r_arm", type="string")
_rAx2 = cmds.ls(_rAx2, long=True)[0]
cmds.maroConnectAxis(_rAx2, _rAx1)

_rPath = os.path.join(tempfile.mkdtemp(prefix="maro_urdf_rigid_"), "rigid.urdf")
assert urdf.export(path=_rPath) == _rPath
_rMeshDir = os.path.join(os.path.dirname(os.path.abspath(_rPath)), "meshes")
# rj1은 직속 메쉬를 통째로 가져간다(기본 폴리큐브 = 12 삼각형).
_rRaw = open(os.path.join(_rMeshDir, "rj1.stl"), "rb").read()
assert _struct.unpack("<I", _rRaw[80:84])[0] == 12, _struct.unpack("<I", _rRaw[80:84])[0]
# rj2는 그 메쉬의 조각을 받으면 안 된다 -- 받았다면 같은 지오메트리가 두 번
# 나간 것이다(설계 스펙 §3의 이중 출력).
assert not os.path.isfile(os.path.join(_rMeshDir, "rj2.stl")),     "rj2 got a piece of a mesh the rigid path already exported whole"
_rRoot = ET2.parse(_rPath).getroot()
_rByName = {l.get("name"): l for l in _rRoot.findall("link")}
assert _rByName["rj1"].find("visual") is not None
assert _rByName["rj2"].find("visual") is None
print("rigid path wins and its mesh is excluded from the split OK")

# --- 법선 방향과 스케일 (RViz 수동 확인의 자동화 가능한 부분) ---
#
# 체크리스트의 RViz 항목이 잡으려는 것은 셋이다: (a) 형상이 보이는가,
# (b) 안팎이 뒤집히지 않았는가, (c) 크기가 Maya 씬과 맞는가. (a)는 렌더러가
# 있어야 하지만 (b)와 (c)는 숫자로 잴 수 있다 -- 그리고 이 머신의 ROS 2는
# 브리지용 최소 설치라 rviz2/robot_state_publisher가 아예 없어서 수동
# 확인 자체가 불가능하다(실측 확인). 그래서 잴 수 있는 둘은 여기서 잰다.
cmds.file(new=True, force=True)
_nCube = cmds.polyCube(name="nCube", width=1, height=1, depth=1)[0]
_nAx = cmds.createNode("maroAxis")
cmds.maroBindAxis(_nAx, _nCube)
cmds.setAttr(_nAx + ".jointName", "n_base", type="string")
_nPath = os.path.join(tempfile.mkdtemp(prefix="maro_urdf_normals_"), "n.urdf")
assert urdf.export(path=_nPath) == _nPath
_nStl = os.path.join(os.path.dirname(os.path.abspath(_nPath)), "meshes", "nCube.stl")
_nRaw = open(_nStl, "rb").read()
_nTris = _struct.unpack("<I", _nRaw[80:84])[0]
assert _nTris == 12, _nTris

_verts = []
for _i in range(_nTris):
    _v = _struct.unpack("<12fH", _nRaw[84 + 50 * _i:84 + 50 * (_i + 1)])
    _verts.append((_v[3:6], _v[6:9], _v[9:12]))

# (b) 법선이 바깥을 향하는가 -- 닫힌 메쉬의 부호 있는 부피로 잰다.
# 발산정리: V = 1/6 * sum(v0 . (v1 x v2)). 와인딩이 바깥이면 양수, 안팎이
# 뒤집혔으면 음수다. RViz에서 "속이 보이는" 증상이 정확히 이 부호다.
_signedVolume = 0.0
for _a, _b, _c in _verts:
    _cx = _b[1] * _c[2] - _b[2] * _c[1]
    _cy = _b[2] * _c[0] - _b[0] * _c[2]
    _cz = _b[0] * _c[1] - _b[1] * _c[0]
    _signedVolume += (_a[0] * _cx + _a[1] * _cy + _a[2] * _cz) / 6.0
assert _signedVolume > 0.0, (
    "exported triangle winding is inverted -- the mesh would render inside-out "
    "in RViz (signed volume %.9f)" % _signedVolume)

# (c) 크기가 Maya 씬과 맞는가. 폭 1의 폴리큐브는 Maya 내부 단위로 1cm이므로
# ROS 미터로 0.01이어야 한다. 단위 스케일이 빠지면 100배로 나온다.
_xs = [v[0] for t in _verts for v in t]
_ys = [v[1] for t in _verts for v in t]
_zs = [v[2] for t in _verts for v in t]
for _axisName, _vals in (("x", _xs), ("y", _ys), ("z", _zs)):
    _extent = max(_vals) - min(_vals)
    assert abs(_extent - 0.01) < 1e-6, (
        "%s extent is %.6f m, expected 0.01 m for a 1-unit cube" % (_axisName, _extent))
# 부피도 같은 이야기를 해야 한다: 0.01^3 = 1e-6 m^3.
assert abs(_signedVolume - 1e-6) < 1e-9, _signedVolume
print("outward normals and metric scale OK (signed volume %.3e m^3)" % _signedVolume)

import random  # noqa: E402

print("[test] convexHull -- 볼록 껍질")

_hullCube = [(x, y, z) for x in (0.0, 1.0) for y in (0.0, 1.0)
             for z in (0.0, 1.0)]
_hullTris = urdf.convexHull(_hullCube)
# 큐브의 껍질은 면 6개 x 삼각형 2개 = 정확히 12개다. 이보다 많으면 같은
# 평면 위 점들을 별개 면으로 쪼갠 것이고(엡실론이 너무 빡빡), 적으면
# 껍질이 닫히지 않은 것이다.
assert _hullTris is not None and len(_hullTris) == 12, _hullTris


def _hullVolume(tris):
    """발산정리 부호 있는 부피. 법선이 바깥이면 양수 -- 슬라이스 1·2가
    와인딩 검증에 쓴 것과 같은 식이다."""
    total = 0.0
    for _a, _b, _c in tris:
        total += urdf._vecDot(_a, urdf._vecCross(_b, _c)) / 6.0
    return total


def _maxOutside(tris, points):
    """어떤 입력 점이 어떤 면의 바깥으로 튀어나온 최대 거리. 진짜 볼록
    껍질이면 0이다(수치 오차 범위 안)."""
    worst = 0.0
    for _a, _b, _c in tris:
        _nrm = urdf._vecCross(urdf._vecSub(_b, _a), urdf._vecSub(_c, _a))
        _scale = math.sqrt(urdf._vecDot(_nrm, _nrm)) or 1.0
        _off = urdf._vecDot(_nrm, _a)
        for _p in points:
            _d = (urdf._vecDot(_nrm, _p) - _off) / _scale
            if _d > worst:
                worst = _d
    return worst


assert abs(_hullVolume(_hullTris) - 1.0) < 1e-9, _hullVolume(_hullTris)
assert _maxOutside(_hullTris, _hullCube) < 1e-9

# 내부 점을 섞어도 껍질은 같아야 한다 -- 내부 점이 면을 만들어내면
# 껍질이 아니다.
_hullRng = random.Random(3)
_hullNoisy = _hullCube + [(_hullRng.uniform(0.2, 0.8),
                           _hullRng.uniform(0.2, 0.8),
                           _hullRng.uniform(0.2, 0.8)) for _ in range(200)]
_hullTris = urdf.convexHull(_hullNoisy)
assert len(_hullTris) == 12, len(_hullTris)
assert abs(_hullVolume(_hullTris) - 1.0) < 1e-9, _hullVolume(_hullTris)
assert _maxOutside(_hullTris, _hullNoisy) < 1e-9

# 중복점이 많아도 사면체 하나가 나와야 한다. 스킨 분할 조각은 이음매에서
# 같은 정점을 여러 번 담고 있으므로 이건 가짜 케이스가 아니다.
_hullDup = ([(0.0, 0.0, 0.0)] * 50 + [(1.0, 0.0, 0.0)] * 50
            + [(0.0, 1.0, 0.0)] * 50 + [(0.0, 0.0, 1.0)] * 50)
_hullTris = urdf.convexHull(_hullDup)
assert len(_hullTris) == 4, len(_hullTris)
assert abs(_hullVolume(_hullTris) - 1.0 / 6.0) < 1e-12, _hullVolume(_hullTris)

# 퇴화 3종은 전부 None -- 호출부는 이걸 보고 박스로 간다.
assert urdf.convexHull([(0, 0, 0), (1, 0, 0), (0, 1, 0)]) is None
assert urdf.convexHull([(float(_x), float(_y), 0.0)
                        for _x in range(5) for _y in range(5)]) is None
assert urdf.convexHull([(float(_i), 0.0, 0.0) for _i in range(10)]) is None
assert urdf.convexHull([]) is None

print("convex hull correctness OK (cube -> 12 tris, degenerates -> None)")


print("[test] convexHull -- 볼록 입력 성능")

# 원통은 이 슬라이스가 겨냥한 최악의 경우다: 모든 점이 껍질에 오른다.
_hullRng = random.Random(11)
_hullCyl = []
for _ in range(2000):
    _t = _hullRng.uniform(0.0, 2.0 * math.pi)
    _hullCyl.append((math.cos(_t), math.sin(_t), _hullRng.uniform(-1.0, 1.0)))

_hullStats = {"visibilityChecks": 0}
_hullTris = urdf.convexHull(_hullCyl, _hullStats)
# 볼록 입력에서 껍질은 단체(simplicial)이므로 면 = 2 x 정점 - 4다.
# 2000점이면 3996 -- 실측으로 정확히 맞는다.
assert _hullTris is not None and len(_hullTris) == 3996, len(_hullTris)
assert _maxOutside(_hullTris, _hullCyl) < 1e-8
assert _hullVolume(_hullTris) > 0.0, _hullVolume(_hullTris)

# 실측: conflict list 구현은 60,664회(점당 30.3회). 가시 영역을 인접
# 면으로 넓히는 대신 매번 면 전체를 훑도록 되돌리면 수백만 회가 되며,
# 상한 200,000이 그 사이를 넉넉히 가른다(이 상한이 실제로 무는지 그
# 변이로 확인했다). 벽시계 시간이 아니라 이 값을 보는 이유는 시간
# 임계값이 머신 부하 때문에 느슨해질 수밖에 없고, 느슨한 임계값은
# 이차식 회귀를 조용히 통과시키기 때문이다.
assert _hullStats["visibilityChecks"] < 200000, _hullStats["visibilityChecks"]
print("convex-input performance OK (%d visibility checks for 2000 points, "
      "%.1f per point)"
      % (_hullStats["visibilityChecks"],
         _hullStats["visibilityChecks"] / 2000.0))


print("[test] axisAlignedBox와 <collision> 분기")

_hullBox = urdf.axisAlignedBox(
    [(-1.0, 2.0, 0.5), (3.0, 6.0, 2.5), (1.0, 4.0, 1.5)])
assert _hullBox["size"] == (4.0, 4.0, 2.0), _hullBox["size"]
assert _hullBox["center"] == (1.0, 4.0, 1.5), _hullBox["center"]

# 공면 입력: 두께 0인 축이 1mm로 올라가고, 중심은 그 평면 위에 남는다.
_hullFlat = urdf.axisAlignedBox(
    [(0.0, 0.0, 7.0), (2.0, 0.0, 7.0), (2.0, 4.0, 7.0), (0.0, 4.0, 7.0)])
assert _hullFlat["size"] == (2.0, 4.0, 0.001), _hullFlat["size"]
assert _hullFlat["center"] == (1.0, 2.0, 7.0), _hullFlat["center"]

# 점 하나: 세 축 전부 1mm.
_hullSingle = urdf.axisAlignedBox([(5.0, 5.0, 5.0)])
assert _hullSingle["size"] == (0.001, 0.001, 0.001), _hullSingle["size"]
assert urdf.axisAlignedBox([]) is None

_hullXml = urdf.buildUrdfXml("bot", [
    {"name": "meshLink",
     "collisionMesh": "package://bot/meshes/a_collision.stl"},
    {"name": "boxLink",
     "collisionBox": {"size": (0.2, 0.3, 0.4), "center": (0.0, 0.1, -0.2)}},
    {"name": "bareLink"},
], [])

_hullByName = {_el.get("name"): _el for _el in _hullXml.findall("link")}

_hullMeshCol = _hullByName["meshLink"].find("collision")
assert _hullMeshCol is not None
assert _hullMeshCol.find("geometry/mesh").get("filename") \
    == "package://bot/meshes/a_collision.stl"
# 메쉬는 정점을 이미 링크 프레임으로 구웠으므로 원점이 항등이다.
assert _hullMeshCol.find("origin").get("xyz") == "0 0 0", \
    _hullMeshCol.find("origin").get("xyz")

_hullBoxCol = _hullByName["boxLink"].find("collision")
assert _hullBoxCol is not None
assert _hullBoxCol.find("geometry/box").get("size") \
    == "0.200000 0.300000 0.400000", _hullBoxCol.find("geometry/box").get("size")
# 박스는 자기 원점 중심으로 정의되므로 AABB 중심을 <origin>으로 옮겨야
# 한다 -- 메쉬와 달리 여기는 항등이 아니다.
assert _hullBoxCol.find("origin").get("xyz") == "0.000000 0.100000 -0.200000", \
    _hullBoxCol.find("origin").get("xyz")

# 두 필드 다 없으면 <collision> 자체가 없다. 지오메트리가 아예 없는
# 조인트는 에러가 아니다.
assert _hullByName["bareLink"].find("collision") is None

# 기존 호출부(두 키가 아예 없는 링크)도 그대로 동작해야 한다.
assert urdf.buildUrdfXml("bot", [{"name": "L"}], []).find("link").get("name") \
    == "L"

print("axisAlignedBox and <collision> branching OK")


maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
