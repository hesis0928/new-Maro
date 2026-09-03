import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

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
assert urdf.axisVectorForConvention(0) == (1.0, 0.0, 0.0)
assert urdf.axisVectorForConvention(1) == (0.0, 1.0, 0.0)
assert urdf.axisVectorForConvention(2) == (0.0, 0.0, 1.0)
try:
    urdf.axisVectorForConvention(3)
    raise AssertionError("expected ValueError for out-of-range conventionAxis")
except ValueError:
    pass
print("axisVectorForConvention OK")

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

maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
