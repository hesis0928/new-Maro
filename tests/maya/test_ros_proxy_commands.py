"""maroMayaToRos / maroSetRosProxyTarget 커맨드 -- 둘 다 순수 계산 +
optionVar 설정이라 mayapy 배치 모드에서 완전히 검증 가능하다(modelPanel과
달리 UI가 전혀 필요 없다).
"""
import math
import os

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

# --- maroMayaToRos ---------------------------------------------------
# Maya (0, 0, 1)(앞쪽, cm 단위 1cm)이 ROS로는 (0, -1, 0)이 돼야 한다
# (Convert.h 주석: mayaToRos: (x, y, z) -> (x, -z, y)). 위치는 미터로도
# 바뀐다 -- 기본 씬 단위가 cm이면 1 Maya 단위 = 0.01미터.
result = cmds.maroMayaToRos(px=0.0, py=0.0, pz=1.0, qx=0.0, qy=0.0, qz=0.0, qw=1.0)
assert len(result) == 7, f"expected 7 values, got {len(result)}: {result}"
assert abs(result[0] - 0.0) < 1e-9, result
assert abs(result[1] - (-0.01)) < 1e-9, result  # -z, cm -> m
assert abs(result[2] - 0.0) < 1e-9, result
# 항등 회전은 항등 회전으로 남는다 (Convert.h: 스칼라부 w는 불변).
assert abs(result[6] - 1.0) < 1e-9, result
print("maroMayaToRos basic conversion OK")

# 필수 플래그 하나라도 빠지면 실패해야 한다(예외가 아니라 kFailure).
try:
    cmds.maroMayaToRos(px=0.0, py=0.0, pz=0.0, qx=0.0, qy=0.0, qz=0.0)
    raise AssertionError("maroMayaToRos must fail when -qw is missing")
except RuntimeError:
    pass
print("maroMayaToRos missing-flag guard OK")

# --- maroSetRosProxyTarget --------------------------------------------
cube = cmds.polyCube(name="rosProxyTestCube")[0]

assert not cmds.optionVar(exists="maroRosProxyPinnedTarget")
cmds.maroSetRosProxyTarget(cube)
assert cmds.optionVar(exists="maroRosProxyPinnedTarget")
assert cmds.optionVar(query="maroRosProxyPinnedTarget") == cube
print("maroSetRosProxyTarget pin OK")

cmds.maroSetRosProxyTarget(clear=True)
assert not cmds.optionVar(exists="maroRosProxyPinnedTarget")
print("maroSetRosProxyTarget clear OK")

# 존재하지 않는 오브젝트를 지정하면 실패해야 한다.
try:
    cmds.maroSetRosProxyTarget("thisObjectDoesNotExist")
    raise AssertionError("maroSetRosProxyTarget must fail for a nonexistent object")
except RuntimeError:
    pass
print("maroSetRosProxyTarget nonexistent-object guard OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
