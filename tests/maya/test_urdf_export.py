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

tmpPath = os.path.join(tempfile.gettempdir(), "maro_urdf_export_test.urdf")
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

tmpPathInvert = os.path.join(tempfile.gettempdir(), "maro_urdf_export_test_invert.urdf")
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

maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
