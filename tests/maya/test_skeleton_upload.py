"""maroSkeletonUpload의 순수 함수(extractSkeleton/_isSingleMeshSelected/
_findMeshInAssemblies)를 배치 모드에서 검증한다. 이 파일이 만드는 것은 전부
표준 Maya 노드(mesh/joint/skinCluster)뿐이라 Qt를 전혀 건드리지 않는다 --
그래서 이 태스크 전체가 mayapy 배치로 완전히 테스트 가능하다."""
import os

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
pluginDir = os.path.dirname(plugin)

stagedModule = os.path.join(pluginDir, "maroSkeletonUpload.py")
assert os.path.isfile(stagedModule), (
    f"maroSkeletonUpload.py must be staged next to the plug-in, not found at {stagedModule}"
)
print("module staged next to the plug-in OK")

cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

import maroSkeletonUpload  # noqa: E402  (플러그인 디렉터리가 sys.path에 들어간 뒤)

# --- extractSkeleton: skinCluster 있음, 인플루언스 정상 -------------------
mesh, _ = cmds.polyCube(name="skinnedCube")
joint1 = cmds.createNode("joint", name="rootJoint")
joint2 = cmds.createNode("joint", name="childJoint", parent=joint1)
cmds.setAttr(joint2 + ".translateY", 2.0)
scNode = cmds.skinCluster(joint1, joint2, mesh)[0]

result = maroSkeletonUpload.extractSkeleton(mesh)
assert result is not None
resultShort = sorted(r.split("|")[-1] for r in result)
assert resultShort == ["childJoint", "rootJoint"], (
    f"expected both influence joints, got {resultShort}")
selected = set(cmds.ls(selection=True, long=True))
assert set(result) == selected, (
    f"extractSkeleton must select exactly the influence joints, "
    f"expected {set(result)}, got selection={selected}")
newNodeCount = len(cmds.ls(type="joint"))
assert newNodeCount == 2, (
    f"extractSkeleton must not create new joints when a skinCluster exists, "
    f"found {newNodeCount} joints")
print("skinCluster with influences: found+selected existing joints, no new nodes OK")

# --- extractSkeleton: skinCluster 있음, 인플루언스 0개(퇴화) --------------
cmds.skinCluster(scNode, edit=True, removeInfluence=[joint1, joint2])
degenerateResult = maroSkeletonUpload.extractSkeleton(mesh)
assert degenerateResult is None, (
    "a skinCluster with zero influences must not fall back to a generated "
    f"root joint, got {degenerateResult}")
assert len(cmds.ls(type="joint")) == 2, (
    "the degenerate-skinCluster case must not create a new joint either")
print("skinCluster with zero influences: returns None, no fallback OK")

# --- extractSkeleton: skinCluster 없음 -> 루트 조인트 생성 ----------------
cmds.file(new=True, force=True)
plainMesh, _ = cmds.polyCube(name="plainCube")
cmds.setAttr(plainMesh + ".translate", 10, 3, -2, type="double3")

noSkinResult = maroSkeletonUpload.extractSkeleton(plainMesh)
assert noSkinResult is not None and len(noSkinResult) == 1
newJoint = noSkinResult[0]
assert cmds.objectType(newJoint) == "joint"
assert newJoint.split("|")[-1] == "plainCube_root"
parents = cmds.listRelatives(newJoint, parent=True, fullPath=True) or []
assert parents and parents[0] == cmds.ls(plainMesh, long=True)[0], (
    "the generated root joint must be parented under the mesh")
bbox = cmds.exactWorldBoundingBox(plainMesh)
expectedCenter = ((bbox[0] + bbox[3]) / 2.0, (bbox[1] + bbox[4]) / 2.0,
                   (bbox[2] + bbox[5]) / 2.0)
actualPos = cmds.xform(newJoint, query=True, worldSpace=True, translation=True)
for actual, expected in zip(actualPos, expectedCenter):
    assert abs(actual - expected) < 1e-6, (
        f"root joint position {actualPos} does not match bbox center {expectedCenter}")
assert cmds.ls(selection=True, long=True) == [newJoint]
print("no skinCluster: creates one root joint at bbox center, parented, selected OK")

# 재클릭(동일 함수 재호출)해도 같은 방식으로 새 조인트를 또 만든다 -- 이
# 함수 자체는 "이미 만들어졌는지" 기억하지 않는다(그 판단은 이번 범위 밖,
# 다이얼로그 쪽에도 그런 로직이 없다 -- 사용자가 매번 명시적으로 실행하는
# 액션이다). Maya가 이름을 자동으로 고유화하는지만 확인한다.
secondResult = maroSkeletonUpload.extractSkeleton(plainMesh)
assert secondResult[0] != newJoint, "Maya must uniquify the duplicate joint name"
print("re-running on the same mesh creates a second, uniquely-named joint OK")

# --- extractSkeleton: 씬 전체에서(형제가 아니라 완전히 무관한 부모 밑에)
# 생성될 루트 조인트와 같은 짧은 이름을 가진 노드가 이미 있는 경우 --------
# 위 "재클릭" 케이스와는 다른 버그다 -- 거기서는 이름이 겹치는 노드가 같은
# mesh의 이전 자식(형제)이었지만, 여기서는 전혀 무관한 그룹 밑에 있는 별개의
# decoy 노드다. 이 경우에만 cmds.parent()가 짧은 이름이 아니라 부분 경로
# ("<decoy의 부모>|<짧은 이름>")를 돌려준다 -- .split("|")[-1] 없이 그 값을
# 그대로 "meshFullPath + '|' + ..."에 이어붙이면 존재하지 않는 경로가 되어
# 뒤이은 cmds.xform()이 예외를 던진다.
decoyGroup = cmds.group(empty=True, name="decoyGroup")
decoyMesh, _ = cmds.polyCube(name="decoyTargetCube")
cmds.setAttr(decoyMesh + ".translate", 5, 0, 0, type="double3")
decoyJoint = cmds.createNode("joint", name="decoyTargetCube_root", parent=decoyGroup)

collisionResult = maroSkeletonUpload.extractSkeleton(decoyMesh)
assert collisionResult is not None and len(collisionResult) == 1
collisionJoint = collisionResult[0]
assert cmds.objExists(collisionJoint), (
    f"the generated root joint must exist at a valid path, got {collisionJoint}")
assert collisionJoint != decoyJoint
collisionParents = cmds.listRelatives(collisionJoint, parent=True, fullPath=True) or []
assert collisionParents and collisionParents[0] == cmds.ls(decoyMesh, long=True)[0], (
    "the generated root joint must be parented under decoyMesh (not decoyGroup, "
    f"the decoy's unrelated parent), got parents={collisionParents}")
decoyBbox = cmds.exactWorldBoundingBox(decoyMesh)
expectedDecoyCenter = ((decoyBbox[0] + decoyBbox[3]) / 2.0, (decoyBbox[1] + decoyBbox[4]) / 2.0,
                        (decoyBbox[2] + decoyBbox[5]) / 2.0)
actualDecoyPos = cmds.xform(collisionJoint, query=True, worldSpace=True, translation=True)
for actual, expected in zip(actualDecoyPos, expectedDecoyCenter):
    assert abs(actual - expected) < 1e-6, (
        f"root joint position {actualDecoyPos} does not match bbox center {expectedDecoyCenter}")
print("scene-wide short-name collision with an unrelated node: still resolves to a valid, "
      "correctly-parented root joint OK")

# --- _isSingleMeshSelected -------------------------------------------------
assert maroSkeletonUpload._isSingleMeshSelected([cmds.ls(plainMesh, long=True)[0]]) is True
assert maroSkeletonUpload._isSingleMeshSelected([]) is False
assert maroSkeletonUpload._isSingleMeshSelected(
    [cmds.ls(plainMesh, long=True)[0], newJoint]) is False
assert maroSkeletonUpload._isSingleMeshSelected([newJoint]) is False, (
    "a lone joint (no mesh shape) must not count as a single mesh selection")
print("_isSingleMeshSelected true/false cases OK")

# --- _findMeshInAssemblies --------------------------------------------------
cmds.file(new=True, force=True)
group = cmds.group(empty=True, name="importedGroup")
nestedMesh, _ = cmds.polyCube(name="nestedMesh")
cmds.parent(nestedMesh, group)
found = maroSkeletonUpload._findMeshInAssemblies([group])
assert found == cmds.ls(nestedMesh, long=True)[0], (
    f"expected to find the nested mesh transform, got {found}")

emptyGroup = cmds.group(empty=True, name="emptyGroup")
notFound = maroSkeletonUpload._findMeshInAssemblies([emptyGroup])
assert notFound is None, f"expected None for a mesh-free subtree, got {notFound}"

assert maroSkeletonUpload._findMeshInAssemblies([]) is None
print("_findMeshInAssemblies found/not-found/empty cases OK")

# --- [최종 리뷰 I-2] before/after 어셈블리 스냅샷 diff는 반드시 long=True로
# 비교해야 한다 -----------------------------------------------------------
# _onImportClicked/_onAfterImport(다이얼로그, Qt 필요 -- 배치 모드에서
# 인스턴스화 불가)가 쓰는 것과 같은 cmds.ls(assemblies=True) 스냅샷-diff
# 패턴 자체를 여기서 직접 재현한다. cmds.ls(assemblies=True)(long=True 없이)
# 는 "짧은 유일 이름"을 주는데, 그 유일성은 씬 전체 상태에 달려 있다 -- 아예
# 무관한 새 최상위/중첩 오브젝트가 같은 짧은 이름을 가지면, 기존 오브젝트를
# 건드리지 않았어도 그 오브젝트의 짧은 유일 이름이 바뀐다. 그러면
# before-스냅샷의 이름과 after-스냅샷의 이름이 문자열로 달라져서, diff가 그
# 기존 오브젝트를 "새로 생김"으로 잘못 분류한다. long=True로 비교하면 항상
# 풀 경로("|pCube1")라 씬 어디에 새 노드가 생기든 흔들리지 않는다.
cmds.file(new=True, force=True)
preExisting = cmds.polyCube(name="pCube1")[0]
beforeShort = set(cmds.ls(assemblies=True) or [])
beforeLong = set(cmds.ls(assemblies=True, long=True) or [])
assert "pCube1" in beforeShort
assert "|pCube1" in beforeLong

# 무관한 새 그룹 밑에, 기존 최상위 오브젝트와 같은 짧은 이름을 가진 노드를
# 만든다 -- 형제 이름 충돌이 아니라(다른 부모라 Maya가 막지 않는다) 씬
# 전체에서 "pCube1"이라는 짧은 이름 자체가 모호해지는 경우다.
decoyGroup = cmds.group(empty=True, name="decoyGroup")
decoyNested = cmds.createNode("transform", name="pCube1", parent=decoyGroup)

afterShort = set(cmds.ls(assemblies=True) or [])
afterLong = set(cmds.ls(assemblies=True, long=True) or [])
# 기존 최상위 pCube1이 이제는 짧은 이름이 아니라(다른 이름의 pCube1이
# 씬에 생겼으므로) 스스로를 구분할 수 있는 이름으로 보고된다 -- 최상위
# 오브젝트라 그 구분되는 이름은 곧 풀 경로("|pCube1")와 같다. 즉
# beforeShort에 있던 "pCube1"이 afterShort에는 더 이상 없다.
assert "pCube1" not in afterShort, (
    "test setup assumption broken: expected the pre-existing top-level "
    "pCube1's short-unique name to change once a same-named nested node "
    f"appears elsewhere, afterShort={afterShort}")
assert "|pCube1" in afterLong, (
    "the pre-existing object's long name must stay stable across the "
    f"mutation, afterLong={afterLong}")

shortDiff = afterShort - beforeShort
longDiff = afterLong - beforeLong
assert "|pCube1" in shortDiff, (
    "this reproduces the I-2 bug: comparing WITHOUT long=True incorrectly "
    "includes the untouched pre-existing object in the 'newly imported' "
    f"diff, shortDiff={shortDiff}")
assert "|pCube1" not in longDiff, (
    "comparing WITH long=True must exclude the untouched pre-existing "
    f"object from the diff, longDiff={longDiff}")
assert longDiff == {"|decoyGroup"}, (
    f"long=True diff must contain exactly the actually-new top-level "
    f"object, got {longDiff}")
print("assembly snapshot diff: without long=True incorrectly includes a "
      "pre-existing object, with long=True correctly excludes it OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")

import sys  # noqa: E402
sys.exit(0)
