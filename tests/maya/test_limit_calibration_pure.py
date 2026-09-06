"""maroLimitCalibration.py의 Maya-비의존 순수 함수 계약. 노드/뷰포트 없이
mayapy로 검증한다(maroSingleObjectNodeEditor.py의 sliceCapabilityRows류와
같은 이유)."""
import math
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(plugin))))
import maroLimitCalibration as calib  # noqa: E402

# axisDirectionFromPoints: 정규화된 방향.
d = calib.axisDirectionFromPoints((0.0, 0.0, 0.0), (0.0, 5.0, 0.0))
assert abs(d[0]) < 1e-9 and abs(d[1] - 1.0) < 1e-9 and abs(d[2]) < 1e-9, d
d2 = calib.axisDirectionFromPoints((1.0, 1.0, 1.0), (4.0, 5.0, 1.0))
length = math.sqrt(d2[0] ** 2 + d2[1] ** 2 + d2[2] ** 2)
assert abs(length - 1.0) < 1e-9, f"must be normalized (got length {length})"
try:
    calib.axisDirectionFromPoints((2.0, 2.0, 2.0), (2.0, 2.0, 2.0))
    raised = False
except ValueError:
    raised = True
assert raised, "identical points must raise ValueError"
print("axisDirectionFromPoints OK")

# axisBasisEulerXYZ: 결과 오일러를 다시 로테이션 행렬로 조립해서 로컬 Z가
# axisDirection과 일치하는지 순수 선형대수로 검증한다(마야 노드 불필요).
import maya.api.OpenMaya as om2  # noqa: E402


def _rotateLocalZ(rx, ry, rz):
    euler = om2.MEulerRotation(math.radians(rx), math.radians(ry), math.radians(rz))
    m = euler.asMatrix()
    localZ = om2.MVector(0.0, 0.0, 1.0) * m
    return (localZ.x, localZ.y, localZ.z)


for axis in [(0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0),
             (0.5773502691896258, 0.5773502691896258, 0.5773502691896258)]:
    rx, ry, rz = calib.axisBasisEulerXYZ(axis)
    gotZ = _rotateLocalZ(rx, ry, rz)
    assert abs(gotZ[0] - axis[0]) < 1e-6 and abs(gotZ[1] - axis[1]) < 1e-6 \
        and abs(gotZ[2] - axis[2]) < 1e-6, \
        f"local Z after rotation {(rx, ry, rz)} must equal axis {axis}, got {gotZ}"
print("axisBasisEulerXYZ OK")

# expandRange: 누적 확장.
assert calib.expandRange(0.0, 0.0, 0.3) == (0.0, 0.3)
assert calib.expandRange(0.0, 0.3, -0.2) == (-0.2, 0.3)
assert calib.expandRange(-0.2, 0.3, 0.1) == (-0.2, 0.3), "sample inside range must not shrink it"
print("expandRange OK")

# mayaDirectionToRos: 위치 변환과 같은 축 재배치, 스케일 없음.
rosVec = calib.mayaDirectionToRos((1.0, 2.0, 3.0))
assert rosVec == (1.0, -3.0, 2.0), rosVec
unit = calib.mayaDirectionToRos((0.0, 1.0, 0.0))
assert unit == (0.0, 0.0, 1.0), "Y-up must map to Z-up with no scale"
print("mayaDirectionToRos OK")

cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
