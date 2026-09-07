"""readAxisPointsFromSelection(): 캘리브레이션 축 방향을 "지금 선택돼
있는 컴포넌트 두 개"에서 읽는다. 전용 tool context(scriptCtx)를 세우지
않으므로 -- 그게 이 함수가 존재하는 이유다 -- 대화형 Maya 없이 mayapy
배치로 완전히 검증된다."""
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(plugin))))
import maroLimitCalibration as calib  # noqa: E402

cube = cmds.polyCube(name="axisPickCube", width=4, height=1, depth=2)[0]


def expectRejected(what):
    try:
        calib.readAxisPointsFromSelection()
    except ValueError:
        return
    raise AssertionError("must reject: " + what)


# (a) 버텍스 두 개 -- 가장 흔한 경로.
cmds.select([cube + ".vtx[0]", cube + ".vtx[1]"], replace=True)
pA, pB = calib.readAxisPointsFromSelection()
expectedA = cmds.pointPosition(cube + ".vtx[0]", world=True)
expectedB = cmds.pointPosition(cube + ".vtx[1]", world=True)
assert {tuple(round(v, 6) for v in pA), tuple(round(v, 6) for v in pB)} == {
    tuple(round(v, 6) for v in expectedA), tuple(round(v, 6) for v in expectedB)}, (pA, pB)
# 두 점이 서로 달라야 axisDirectionFromPoints가 방향을 낼 수 있다.
direction = calib.axisDirectionFromPoints(pA, pB)
assert abs(sum(c * c for c in direction) - 1.0) < 1e-6, direction
print("two vertices OK:", pA, pB, direction)

# (b) 페이스+에지 혼합 -- 컴포넌트 종류가 섞여도 각각의 대표 좌표를 쓴다.
cmds.select([cube + ".f[0]", cube + ".e[5]"], replace=True)
pA, pB = calib.readAxisPointsFromSelection()
assert len(pA) == 3 and len(pB) == 3, (pA, pB)
print("face+edge OK:", pA, pB)

# (c) 거부해야 하는 선택들. scriptCtx 시절엔 이 경우들이 전부 무한루프나
#     조용한 오작동으로 나타났다 -- 이제는 전부 ValueError 한 지점으로 모인다.
cmds.select(clear=True)
expectRejected("empty selection")

cmds.select(cube + ".vtx[0]", replace=True)
expectRejected("only one component")

cmds.select([cube + ".vtx[0]", cube + ".vtx[1]", cube + ".vtx[2]"], replace=True)
expectRejected("three components")

cmds.select(cube, replace=True)
expectRejected("whole object, not a component")

locator = cmds.spaceLocator(name="notAMeshComponent")[0]
cmds.select([locator, cube], replace=True)
expectRejected("two objects, neither a component")
print("rejection paths OK")

# (d) 같은 컴포넌트를 두 번 골랐다면 방향이 정의되지 않는다 --
#     axisDirectionFromPoints의 ValueError로 이어지는지까지 확인.
cmds.select([cube + ".vtx[0]", cube + ".vtx[0]"], replace=True)
try:
    calib.readAxisPointsFromSelection()
except ValueError:
    pass  # flatten 후 1개로 줄어 거부되는 것도 정당하다.
else:
    raise AssertionError("duplicate component selection must not yield an axis")
print("duplicate component OK")

print("readAxisPointsFromSelection OK")
