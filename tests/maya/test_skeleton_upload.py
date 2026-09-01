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

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")

import sys  # noqa: E402
sys.exit(0)
