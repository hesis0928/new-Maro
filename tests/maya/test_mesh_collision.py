"""maroCheckMeshCollision의 계약을 고정한다: 실제로 겹치는 폴리곤 쌍은
true, AABB만 겹치고 실제로는 안 닿는 쌍은 false, 폴리곤이 아닌 지오메트리는
unknown."""
import os

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

# 확실히 겹침: 같은 자리에 겹친 두 큐브.
cubeA = cmds.polyCube(name="collideCubeA")[0]
cubeB = cmds.polyCube(name="collideCubeB")[0]
assert cmds.maroCheckMeshCollision(cubeA, cubeB) == "true", "overlapping cubes must collide"
print("overlapping cubes -> true OK")

# 완전히 분리됨.
cmds.setAttr(cubeB + ".translate", 100, 100, 100, type="double3")
assert cmds.maroCheckMeshCollision(cubeA, cubeB) == "false", "separated cubes must not collide"
print("separated cubes -> false OK")

# AABB는 겹치지만 실제 폴리곤 표면은 안 닿는 배치: cubeB를 Y축으로 45도
# 돌리면 XZ 평면에서 정사각형이 마름모(다이아몬드)가 된다 -- 마름모의
# 꼭짓점은 그 축정렬 바운딩박스의 "변 중점"에 닿을 뿐, 바운딩박스의
# "모서리(코너)" 영역에는 실제 표면이 전혀 없다. cubeB를 XZ 대각선 방향
# (X와 Z를 똑같이)으로 옮기면, 두 큐브의 바운딩박스는 정확히 그 빈
# 코너 영역에서 겹치게 된다 -- 즉 바운딩박스는 겹치지만 마름모 표면은
# cubeA에 닿지 않는다. 이 배치가 의도한 조건(AABB 겹침 O, 실제 폴리곤
# 접촉 X)을 실제로 만드는지는 cmds.exactWorldBoundingBox로 먼저 확인하고,
# 필요하면 좌표를 조정한다 -- 손으로 가정하지 않고 이 스텝에서 직접
# 확인한다.
#
# (브리프가 준 최초 값 translate=(1.9,1.9,0)/rotateY=45는 실측 결과 AABB가
# 아예 겹치지 않았다(Y축으로 너무 멀리 떨어짐) -- 대신 X/Z 대각선 방향
# translate=(0.9,0,0.9)로 위 마름모-코너 배치를 실측 스크립트로 직접 찾아
# 확인했다: 0.9는 AABB 겹침 O / 실제 접촉 X를 만들고, 0.85 이하로 좁히면
# 실제로 닿기 시작한다(margin 확인됨).)
cmds.setAttr(cubeB + ".translate", 0.9, 0, 0.9, type="double3")
cmds.setAttr(cubeB + ".rotateY", 45)
boxA = cmds.exactWorldBoundingBox(cubeA)
boxB = cmds.exactWorldBoundingBox(cubeB)
aabbOverlap = (boxA[0] < boxB[3] and boxB[0] < boxA[3] and
               boxA[1] < boxB[4] and boxB[1] < boxA[4] and
               boxA[2] < boxB[5] and boxB[2] < boxA[5])
assert aabbOverlap, (
    "test setup error: expected these two cubes' AABBs to overlap, got "
    "{} and {} -- adjust the translate/rotate values above".format(boxA, boxB))
result = cmds.maroCheckMeshCollision(cubeA, cubeB)
assert result == "false", (
    "expected AABB-only overlap (no real polygon contact) to report false, "
    "got {} for boxes {} / {} -- if the geometry above actually does touch, "
    "adjust the translate value further apart".format(result, boxA, boxB))
print("AABB-only overlap -> false OK")

# 폴리곤이 아닌 지오메트리: unknown.
locatorTransform = cmds.spaceLocator(name="notAMeshLocator")[0]
assert cmds.maroCheckMeshCollision(cubeA, locatorTransform) == "unknown", (
    "a non-mesh argument must report unknown, not crash or silently say false")
print("non-mesh argument -> unknown OK")

# --- 최종 리뷰 Important-4: 다중 인스턴스 노드에서 정확한 DAG 경로를
# 쓰는지 (getDependNode()+getAPathTo() 함정 회귀) ---
#
# 예전 구현은 selection.getDependNode()로 bare MObject를 얻은 뒤
# extractMeshBuffers(MObject)가 내부적으로 MDagPath::getAPathTo()를 불렀다.
# 그 함수는 다중 인스턴스 노드에 대해 "첫 번째" 경로만 돌려준다.
#
# 중요: Maya에서 인스턴싱은 **셰이프**에 걸리지, 트랜스폼에는 걸리지 않는다
# -- 각 인스턴스는 자기만의 유일한 트랜스폼을 갖지만, 그 밑의 셰이프
# 노드(MObject) 자체는 모든 인스턴스가 공유한다. 그래서 이 함정을 실제로
# 재현하려면 **트랜스폼 이름이 아니라 공유되는 셰이프의 정확한 인스턴스
# 경로**를 커맨드 인자로 넘겨야 한다 -- 트랜스폼 이름을 넘기면 트랜스폼
# 자체는 인스턴싱되지 않으므로 getAPathTo()가 항상 유일한 정답을 준다
# (실측으로 확인: 트랜스폼 이름으로는 이 버그가 재현되지 않았다).
#
# 원본 셰이프 경로(월드 원점)와 그 인스턴스 셰이프 경로(x=5로 옮김)가 서로
# 다른 위치에 있게 만들고, 딱 그 인스턴스 위치에만 겹치는 프로브 메쉬로
# 실제 어느 경로가 평가됐는지 구분한다.
cmds.file(new=True, force=True)

instSource = cmds.polyCube(name="instSourceCube")[0]  # world origin
instancePath = cmds.instance(instSource)[0]
cmds.setAttr(instancePath + ".translateX", 5.0)

origShapePath = cmds.listRelatives(instSource, shapes=True, fullPath=True)[0]
instShapePath = cmds.listRelatives(instancePath, shapes=True, fullPath=True)[0]
assert origShapePath != instShapePath, (origShapePath, instShapePath)

probeMesh = cmds.polyCube(name="instProbeMesh")[0]
cmds.setAttr(probeMesh + ".translateX", 5.0)  # overlaps only the moved instance

# Sanity check: confirm the two instance shape paths really sit in
# different, non-overlapping places -- otherwise this test cannot
# distinguish them at all.
assert cmds.maroCheckMeshCollision(probeMesh, origShapePath) == "false", (
    "test setup error: the original (unmoved) instance shape path must NOT "
    "collide with a probe mesh placed 5 units away -- otherwise this test "
    "can't tell the two instances apart")
print("instance test setup: original instance shape path does not collide with the probe OK")

# The exact instance shape path named in the command (moved to x=5,
# overlapping the probe) must be the one evaluated -- not whichever
# instance MDagPath::getAPathTo() happens to consider "first" (empirically
# confirmed to be the original, unmoved instance).
result = cmds.maroCheckMeshCollision(probeMesh, instShapePath)
assert result == "true", (
    "expected the exact instance shape path passed ({}) -- which sits at "
    "x=5, overlapping the probe mesh -- to be evaluated; a 'false' here "
    "means the command silently fell back to a different instance (the "
    "original, at x=0, which does not overlap the probe): got {}".format(
        instShapePath, result))
print("maroCheckMeshCollision resolves the exact named instance path OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
