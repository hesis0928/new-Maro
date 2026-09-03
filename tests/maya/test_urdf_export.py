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

result = urdf.jointType([
    {"capType": 7, "ratio": 1.5, "offset": 0.0, "sourceJointName": "elbow"},
])
assert result["type"] == "prismatic", result
assert result["mimic"] == {"joint": "elbow", "multiplier": 1.5, "offset": 0.0}, result

result = urdf.jointType([])
assert result == {"type": "fixed", "lower": None, "upper": None, "mimic": None}, result

result = urdf.jointType([{"capType": 2}, {"capType": 3}])
assert result["type"] == "fixed", result
print("jointType OK")

maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
