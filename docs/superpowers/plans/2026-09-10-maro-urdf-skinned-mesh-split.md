# URDF 스킨 메쉬 분할 (슬라이스 2) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 스킨된 메쉬 하나를 skinCluster 인플루언스에 따라 조각내어, 링크마다 자기 몫의 지오메트리를 `<visual>`로 내보내게 한다 — 지금은 스킨 캐릭터를 내보내면 모든 링크가 형상 없이 나간다.

**Architecture:** 귀속 규칙(정점→인플루언스, 삼각형→링크)을 씬과 무관한 순수 함수로 먼저 만들고, 그 위에 조상 walk와 씬 조회를 얹는다. 마지막에 슬라이스 1의 `_writeLinkMeshes` 루프 앞에 사전 계산 한 번을 끼워 넣는다. 전부 `python/maroUrdfExport.py` 안이고, 프레임·단위·STL 경로는 슬라이스 1 것을 그대로 재사용한다.

**Tech Stack:** Python (mayapy), `maya.api.OpenMaya`(om2), **`maya.api.OpenMayaAnim`(oma2, 새 import)**, `maya.cmds`. 새 C++ 코드 없음. 외부 의존성 추가 없음.

## Global Constraints

- 빌드는 항상 `--config Release`. `ctest --test-dir out/build -C Release --output-on-failure`가 전부 통과해야 한다.
- **`.py`만 고쳐도 반드시 `cmake --build`를 돌린다.** 테스트는 플러그인 옆에 스테이징된 사본을 import하므로, 빌드를 건너뛰면 낡은 코드를 검증하게 된다.
- 링크 프레임 읽기는 `_linkFrameWorldRigid`를 쓴다. 그 네 줄을 다시 쓰지 않는다 — 슬라이스 1이 그 중복 때문에 두 번 물렸고(100mm, 50~200mm) 그래서 한 곳으로 모았다.
- `buildUrdfXml`은 순수 함수로 남는다 — 파일 I/O도 씬 조회도 하지 않는다.
- 새 파이썬 모듈을 만들지 않는다(전부 `maroUrdfExport.py` 안). 만들었다면 `MARO_PLUGIN_PY_MODULES`에 반드시 추가한다.
- 새 `.py`는 `setStyleSheet()`를 호출하지 않는다.
- 강체 경로가 소비한 메쉬 셰이프는 분할이 **건너뛴다** — 안 그러면 같은 지오메트리가 두 번 나간다(스펙 §3).
- 훑는 skinCluster는 **링크에서 도달 가능한 것만** — 씬 전체가 아니다(스펙 §6).

**빌드/테스트 명령(PowerShell):**

```powershell
cd C:\Users\ckd30\Projects\Maya_Ros_Sim
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] } }
cmake --build out/build --config Release
ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure
```

`--output-on-failure`는 통과 시 stdout을 숨긴다. 테스트의 `print()`를 보려면 `-V`를 붙인다.

---

### Task 1: 귀속 규칙 (순수 함수)

**Files:**
- Modify: `python/maroUrdfExport.py` (`_linkFrameWorldRigid` 정의 바로 뒤에 함수 두 개 추가)
- Test: `tests/maya/test_urdf_export.py` (파일 끝에 절 추가)

**Interfaces:**
- Consumes: 없음(씬도 om2도 안 쓴다 — 리스트와 튜플만 받는다)
- Produces:
  - `dominantInfluence(weights, vertexIndex, influenceCount) -> (index, weight)`. `weights`는 `정점수 × influenceCount` 평평한 시퀀스. 동점이면 가장 작은 인덱스.
  - `assignTriangleToLink(vertexLinks, vertexWeights, corners) -> str | None`. `vertexLinks[v]`는 정점 v의 링크 경로(또는 `None`), `vertexWeights[v]`는 그 정점의 지배 가중치, `corners`는 정점 인덱스 3-튜플.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/maya/test_urdf_export.py` 맨 끝(마지막 `print(...)` 다음)에 붙인다:

```python
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
```

- [ ] **Step 2: 실패를 확인한다**

Run: `ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure`

Expected: FAIL — `AttributeError: module 'maroUrdfExport' has no attribute 'dominantInfluence'`

- [ ] **Step 3: 함수를 구현한다**

`python/maroUrdfExport.py`에서 `_linkFrameWorldRigid` 함수가 끝나는 지점 **바로 뒤**에 붙인다:

```python
def dominantInfluence(weights, vertexIndex, influenceCount):
    """정점 하나를 지배하는 인플루언스의 (인덱스, 가중치).

    `weights`는 `정점수 x influenceCount` 평평한 시퀀스이고 정점 `v`의
    인플루언스 `k`는 `weights[v * influenceCount + k]`다 -- 실측으로 확인한
    `MFnSkinCluster.getWeights()`의 모양이며, `k`의 순서는
    `influenceObjects()`가 주는 순서와 같다.

    동점이면 **가장 작은 인덱스**를 준다. 임의로 고르면 같은 리그를 다시
    내보낼 때 정점이 다른 링크로 옮겨가는데, 그건 진단하기 어려운 종류의
    불안정성이다.
    """
    base = vertexIndex * influenceCount
    bestIndex = 0
    bestWeight = weights[base]
    for k in range(1, influenceCount):
        w = weights[base + k]
        if w > bestWeight:
            bestIndex = k
            bestWeight = w
    return (bestIndex, bestWeight)


def assignTriangleToLink(vertexLinks, vertexWeights, corners):
    """삼각형 하나가 갈 링크 경로. 어디에도 못 가면 None.

    `vertexLinks[v]`는 정점 v가 속한 링크 경로(또는 None), `vertexWeights[v]`는
    그 정점의 지배 가중치, `corners`는 정점 인덱스 3-튜플이다.

    규칙(설계 스펙 §4.3): 정점 3개 중 **2개 이상**을 가진 링크가 가져간다.
    세 정점이 전부 다른 링크면(1:1:1 동점) **개별 가중치가 가장 큰 정점**의
    링크로 보낸다 -- 첫 정점을 고르면 결과가 메쉬의 정점 순서에 의존하게
    되고, 같은 리그를 다시 내보냈을 때 삼각형이 다른 링크로 옮겨간다.

    None인 정점은 후보에서 빠진다. 셋 다 None이면 그 삼각형은 버린다.
    """
    counts = {}
    for v in corners:
        link = vertexLinks[v]
        if link is None:
            continue
        counts[link] = counts.get(link, 0) + 1
    if not counts:
        return None

    bestLink = None
    bestCount = 0
    for link, count in counts.items():
        if count > bestCount:
            bestLink, bestCount = link, count
    if bestCount >= 2:
        return bestLink

    # 1:1:1 -- 가중치가 가장 큰 정점이 이긴다. None인 정점은 후보가 아니다.
    bestWeight = -1.0
    winner = None
    for v in corners:
        if vertexLinks[v] is None:
            continue
        if vertexWeights[v] > bestWeight:
            bestWeight = vertexWeights[v]
            winner = vertexLinks[v]
    return winner
```

- [ ] **Step 4: 빌드하고 통과를 확인한다**

Run:
```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure
```

Expected: PASS, 출력(`-V`)에 `dominantInfluence OK`와 `assignTriangleToLink OK`

- [ ] **Step 5: 커밋**

```bash
git add python/maroUrdfExport.py tests/maya/test_urdf_export.py
git commit -m "feat(urdf): skin split attribution rules"
```

---

### Task 2: 조상 walk — 인플루언스를 링크로

**Files:**
- Modify: `python/maroUrdfExport.py` (Task 1이 추가한 `dominantInfluence` 바로 앞)
- Test: `tests/maya/test_urdf_export.py` (Task 1 절 다음)

**Interfaces:**
- Consumes: 없음
- Produces: `influenceToLink(influencePath, linkPaths) -> str | None`. `linkPaths`는 링크의 `targetPath` 전체 경로 `set`. 자기 자신이 링크면 자신을, 아니면 가장 가까운 DAG 조상 중 링크인 것을, 끝까지 없으면 `None`.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/maya/test_urdf_export.py`의 Task 1 절 다음에 붙인다:

```python
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
```

- [ ] **Step 2: 실패를 확인한다**

Run: `ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure`

Expected: FAIL — `AttributeError: module 'maroUrdfExport' has no attribute 'influenceToLink'`

- [ ] **Step 3: 함수를 구현한다**

`python/maroUrdfExport.py`의 `dominantInfluence` **바로 앞**에 붙인다:

```python
def influenceToLink(influencePath, linkPaths):
    """인플루언스 조인트가 속할 링크의 전체 경로. 없으면 None.

    자기 자신이 링크면 자신을, 아니면 DAG 조상을 거슬러 올라가 링크인 첫
    조상을 준다.

    조상 walk가 필요한 이유(설계 스펙 §4.2): 캐릭터 리그는 URDF 관절보다
    조인트가 훨씬 많다 -- 손가락 20개를 손목 링크 하나로 묶는 식이 정상이다.
    walk가 없으면 바인딩 안 된 조인트가 지배하는 영역이 통째로 비어 RViz에
    구멍으로 보인다.

    `linkPaths`는 전체 DAG 경로의 set이어야 한다 -- 짧은 이름과 섞이면
    같은 노드인데도 절대 매치되지 않는다(maroSkeletonUpload.extractSkeleton이
    같은 함정을 실측으로 기록해 두었다).
    """
    node = influencePath
    while node:
        if node in linkPaths:
            return node
        parents = cmds.listRelatives(node, parent=True, fullPath=True)
        node = parents[0] if parents else None
    return None
```

- [ ] **Step 4: 빌드하고 통과를 확인한다**

Run:
```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure
```

Expected: PASS, 출력(`-V`)에 `influenceToLink OK`

- [ ] **Step 5: 커밋**

```bash
git add python/maroUrdfExport.py tests/maya/test_urdf_export.py
git commit -m "feat(urdf): map skin influences to links by ancestor walk"
```

---

### Task 3: `_splitSkinnedMeshes` — 씬 조회와 조각 만들기

**Files:**
- Modify: `python/maroUrdfExport.py` (import 블록에 `oma2` 추가; `_linkMeshTriangles` 앞에 헬퍼 두 개 + 분할 함수 추가; `_linkMeshTriangles`가 새 헬퍼를 쓰게 수정)
- Test: `tests/maya/test_urdf_export.py` (Task 2 절 다음)

**Interfaces:**
- Consumes: Task 1의 `dominantInfluence`, `assignTriangleToLink`; Task 2의 `influenceToLink`; 슬라이스 1의 `_linkFrameWorldRigid(framePath) -> (MVector, MQuaternion)`
- Produces:
  - `_linkFrameInverseMatrix(framePath) -> om2.MMatrix` — 링크 프레임의 **강체** 역행렬. `_linkMeshTriangles`와 `_splitSkinnedMeshes`가 공유한다.
  - `_splitSkinnedMeshes(links, consumedShapes) -> dict`. 키는 링크의 `targetPath`, 값은 `[((x,y,z),(x,y,z),(x,y,z)), ...]`(Maya 내부 단위, 그 링크의 프레임 로컬) — `_linkMeshTriangles`와 같은 계약이다. `consumedShapes`는 강체 경로가 이미 가져간 메쉬 셰이프 전체 경로의 `set`.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/maya/test_urdf_export.py`의 Task 2 절 다음에 붙인다:

```python
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
```

`om2`는 이 파일이 이미 152행에서 `import maya.api.OpenMaya as om2`로 들여온다(확인함). 새 블록은 파일 끝(820행 이후)에 붙으므로 그대로 쓸 수 있다 -- 다시 import하지 않는다.

- [ ] **Step 2: 실패를 확인한다**

Run: `ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure`

Expected: FAIL — `AttributeError: module 'maroUrdfExport' has no attribute '_splitSkinnedMeshes'`

- [ ] **Step 3: `oma2` import를 추가한다**

`python/maroUrdfExport.py`의 import 블록

```python
import maya.cmds as cmds
import maya.api.OpenMaya as om2
import xml.etree.ElementTree as ET
```

을 이렇게 바꾼다:

```python
import maya.cmds as cmds
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import xml.etree.ElementTree as ET
```

- [ ] **Step 4: 프레임 역행렬을 공유 헬퍼로 뽑는다**

`python/maroUrdfExport.py`의 `_linkMeshTriangles` **바로 앞**에 붙인다:

```python
def _linkFrameInverseMatrix(framePath):
    """링크 프레임의 **강체** 역행렬(om2.MMatrix).

    스케일과 전단을 버리는 이유는 `_linkFrameWorldRigid`의 주석에 있다 --
    조인트 원점이 이동과 회전만 읽으므로 메쉬도 같아야 하고, 그러지 않으면
    스케일이 개입하는 순간 둘이 어긋난다(실측: 로케이터 2배에서 50mm,
    비균일 그룹에서 200mm).

    강체 경로(`_linkMeshTriangles`)와 스킨 분할(`_splitSkinnedMeshes`)이
    이 함수를 공유한다 -- 조립을 두 군데서 따로 하면 슬라이스 1이 이미 두 번
    겪은 "두 소비자가 프레임을 다르게 읽는" 실패가 그대로 재현된다.
    """
    framePos, frameQuat = _linkFrameWorldRigid(framePath)
    frameRigid = om2.MTransformationMatrix()
    frameRigid.setTranslation(framePos, om2.MSpace.kWorld)
    frameRigid.setRotation(frameQuat)
    return frameRigid.asMatrix().inverse()
```

그리고 `_linkMeshTriangles` 안의

```python
    framePos, frameQuat = _linkFrameWorldRigid(axisFramePath)
    frameRigid = om2.MTransformationMatrix()
    frameRigid.setTranslation(framePos, om2.MSpace.kWorld)
    frameRigid.setRotation(frameQuat)
    frameInverse = frameRigid.asMatrix().inverse()
```

를 한 줄로 바꾼다(앞뒤 주석은 그대로 둔다):

```python
    frameInverse = _linkFrameInverseMatrix(axisFramePath)
```

- [ ] **Step 5: 분할 함수를 구현한다**

`python/maroUrdfExport.py`의 `_linkFrameInverseMatrix` **바로 뒤**에 붙인다:

```python
def _splitSkinnedMeshes(links, consumedShapes):
    """스킨된 메쉬를 인플루언스에 따라 조각내어 {링크 targetPath: [삼각형]}로.

    삼각형은 Maya 내부 단위이고 **그 링크의 프레임 로컬**이다 --
    `_linkMeshTriangles`와 같은 계약이라 호출부가 둘을 구분하지 않아도 된다.

    `consumedShapes`는 강체 경로가 이미 가져간 메쉬 셰이프의 전체 경로
    set이다. 그 셰이프는 건너뛴다 -- 안 그러면 링크 A의 직속 메쉬가 A·B로
    스킨돼 있을 때 M의 B 영역이 두 번 나간다(A의 사본 안에 한 번, B의
    조각으로 한 번; 설계 스펙 §3).

    훑는 skinCluster는 **링크에서 도달 가능한 것만**이다. 씬 전체를 훑으면
    로봇과 무관한 스킨 메쉬(배경 캐릭터, 참조 모델)의 가중치까지 읽는데,
    결과는 어차피 버려지므로 정점 수만 개짜리 메쉬에서는 순전히 낭비다.

    가중치는 skinCluster마다 **한 번만** 읽는다. 링크 루프 안에서 읽으면
    O(링크 x 정점)이 된다.
    """
    linkByTarget = {}
    for link in links:
        targetPath = link.get("targetPath")
        axisFramePath = link.get("axisFramePath")
        if targetPath and axisFramePath:
            linkByTarget[targetPath] = axisFramePath
    if not linkByTarget:
        return {}

    linkPaths = set(linkByTarget)
    clusters = set()
    for targetPath in linkPaths:
        for cluster in cmds.listConnections(targetPath, type="skinCluster") or []:
            clusters.add(cluster)

    frameInverses = {t: _linkFrameInverseMatrix(f) for t, f in linkByTarget.items()}
    pieces = {}

    for cluster in sorted(clusters):
        clusterSel = om2.MSelectionList()
        clusterSel.add(cluster)
        skinFn = oma2.MFnSkinCluster(clusterSel.getDependNode(0))
        # 인플루언스 인덱스 -> 링크. getWeights()의 stride 순서가
        # influenceObjects()의 순서와 같다(실측 확인).
        indexToLink = [influenceToLink(p.fullPathName(), linkPaths)
                       for p in skinFn.influenceObjects()]

        for shape in cmds.skinCluster(cluster, query=True, geometry=True) or []:
            shapePath = cmds.ls(shape, long=True)[0]
            if shapePath in consumedShapes:
                continue
            shapeSel = om2.MSelectionList()
            shapeSel.add(shapePath)
            shapeDag = shapeSel.getDagPath(0)
            meshFn = om2.MFnMesh(shapeDag)
            vertexCount = meshFn.numVertices

            componentFn = om2.MFnSingleIndexedComponent()
            component = componentFn.create(om2.MFn.kMeshVertComponent)
            componentFn.setCompleteData(vertexCount)
            weights, influenceCount = skinFn.getWeights(shapeDag, component)

            vertexLinks = {}
            vertexWeights = {}
            for v in range(vertexCount):
                index, weight = dominantInfluence(weights, v, influenceCount)
                vertexLinks[v] = indexToLink[index]
                vertexWeights[v] = weight

            worldPoints = meshFn.getPoints(om2.MSpace.kWorld)
            _counts, indices = meshFn.getTriangles()
            for i in range(0, len(indices), 3):
                corners = (indices[i], indices[i + 1], indices[i + 2])
                target = assignTriangleToLink(vertexLinks, vertexWeights, corners)
                if target is None:
                    continue
                frameInverse = frameInverses[target]
                triangle = []
                for v in corners:
                    p = worldPoints[v] * frameInverse
                    triangle.append((p.x, p.y, p.z))
                pieces.setdefault(target, []).append(tuple(triangle))

    return pieces
```

- [ ] **Step 6: 빌드하고 통과를 확인한다**

Run:
```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure
```

Expected: PASS. `-V`로 보면 `split invariant OK: 276 = 158 + 118` 같은 줄이 나온다(정확한 수는 Maya의 기본 스무스 바인드 가중치에 달렸으므로 **테스트가 그 값을 하드코딩하지 않는다** — 합이 원본과 같은지와 양쪽 다 0이 아닌지만 본다).

- [ ] **Step 7: 커밋**

```bash
git add python/maroUrdfExport.py tests/maya/test_urdf_export.py
git commit -m "feat(urdf): split skinned meshes into per-link pieces"
```

---

### Task 4: `_writeLinkMeshes` 배선과 소비된 셰이프 제외

**Files:**
- Modify: `python/maroUrdfExport.py` (`_linkMeshTriangles` 안의 셰이프 조회를 헬퍼로 분리; `_writeLinkMeshes` 루프 수정)
- Test: `tests/maya/test_urdf_export.py` (Task 3 절 다음)

**Interfaces:**
- Consumes: Task 3의 `_splitSkinnedMeshes(links, consumedShapes)`
- Produces: `_linkDirectMeshShapes(linkTransform) -> list` — 링크의 직속 mesh 셰이프 전체 경로 목록. `_linkMeshTriangles`와 `_writeLinkMeshes`가 공유한다("이 링크의 셰이프가 무엇인가"의 단일 출처).

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/maya/test_urdf_export.py`의 Task 3 절 다음에 붙인다:

```python
# --- 스킨 링크가 실제로 <visual>을 갖는다 (슬라이스 2 통합) ---
cmds.file(new=True, force=True)
_ej1 = cmds.createNode("joint", name="ej1")
cmds.xform(_ej1, translation=(0, 0, 0))
_ej2 = cmds.createNode("joint", name="ej2", parent=_ej1)
cmds.xform(_ej2, translation=(0, 10, 0))
_eMesh = cmds.polyCylinder(name="eLimb", height=20, subdivisionsHeight=6, radius=2)[0]
cmds.xform(_eMesh, translation=(0, 10, 0))
cmds.skinCluster(_ej1, _ej2, _eMesh, toSelectedBones=True)

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
# `_struct`는 이 파일이 486행에서 이미 들여왔다(확인함) -- 새 블록은 파일
# 끝에 붙으므로 그대로 쓸 수 있다.
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
assert not os.path.isfile(os.path.join(_rMeshDir, "rj2.stl")), \
    "rj2 got a piece of a mesh the rigid path already exported whole"
_rRoot = ET2.parse(_rPath).getroot()
_rByName = {l.get("name"): l for l in _rRoot.findall("link")}
assert _rByName["rj1"].find("visual") is not None
assert _rByName["rj2"].find("visual") is None
print("rigid path wins and its mesh is excluded from the split OK")
```

- [ ] **Step 2: 실패를 확인한다**

Run: `ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure`

Expected: FAIL — 스킨 링크에 `<visual>`이 없다는 `AssertionError` (`skinned link ej1 got no <visual>`)

- [ ] **Step 3: 셰이프 조회를 헬퍼로 분리한다**

`python/maroUrdfExport.py`의 `_linkMeshTriangles` **바로 앞**에 붙인다:

```python
def _linkDirectMeshShapes(linkTransform):
    """링크의 **직속** mesh 셰이프 전체 경로 목록. 없으면 빈 리스트.

    "이 링크의 셰이프가 무엇인가"의 단일 출처다 -- `_linkMeshTriangles`가
    삼각형을 뽑을 때와, `_writeLinkMeshes`가 "강체 경로가 소비한 셰이프"
    집합을 만들 때 같은 답을 써야 한다. 두 곳에서 따로 조회하면 조건이
    어긋나 같은 메쉬가 강체로도 조각으로도 나갈 수 있다.

    `allDescendents`를 쓰지 않고 `noIntermediate=True`를 주는 이유는
    `_linkMeshTriangles`의 주석에 있다.
    """
    return cmds.listRelatives(linkTransform, shapes=True, fullPath=True,
                              type="mesh", noIntermediate=True) or []
```

그리고 `_linkMeshTriangles` 안의

```python
    shapes = cmds.listRelatives(linkTransform, shapes=True, fullPath=True,
                                type="mesh", noIntermediate=True) or []
```

를 이렇게 바꾼다:

```python
    shapes = _linkDirectMeshShapes(linkTransform)
```

- [ ] **Step 4: `_writeLinkMeshes`가 분할을 쓰게 한다**

`python/maroUrdfExport.py`의 `_writeLinkMeshes` 안

```python
    usedNames = set()
    for link in links:
        targetPath = link.get("targetPath")
        axisFramePath = link.get("axisFramePath")
        if not targetPath or not axisFramePath:
            continue
        triangles = _linkMeshTriangles(targetPath, axisFramePath)
        if not triangles:
            continue
```

을 이렇게 바꾼다:

```python
    # 강체 경로가 가져갈 셰이프를 **먼저** 모은다. 스킨 분할은 그 셰이프를
    # 건너뛰어야 한다 -- 안 그러면 링크 A의 직속 메쉬가 A와 B로 스킨돼
    # 있을 때 그 메쉬의 B 영역이 두 번 나간다(A의 통째 사본 안에 한 번,
    # B의 조각으로 한 번; 설계 스펙 §3).
    consumedShapes = set()
    for link in links:
        targetPath = link.get("targetPath")
        if targetPath:
            consumedShapes.update(_linkDirectMeshShapes(targetPath))

    # 가중치는 씬당 한 번만 읽는다 -- 링크 루프 안에서 읽으면
    # O(링크 x 정점)이 된다(설계 스펙 §3).
    skinnedByLink = _splitSkinnedMeshes(links, consumedShapes)

    usedNames = set()
    for link in links:
        targetPath = link.get("targetPath")
        axisFramePath = link.get("axisFramePath")
        if not targetPath or not axisFramePath:
            continue
        triangles = _linkMeshTriangles(targetPath, axisFramePath)
        if not triangles:
            # 직속 메쉬가 없는 링크(스킨된 캐릭터의 조인트)는 분할 조각을
            # 받는다. 강체가 우선이므로 이 순서를 뒤집으면 안 된다.
            triangles = skinnedByLink.get(targetPath) or []
        if not triangles:
            continue
```

- [ ] **Step 5: 빌드하고 통과를 확인한다**

Run:
```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure
```

Expected: PASS, `-V` 출력에 `skinned links export split geometry OK: {...}`와 `rigid path wins and its mesh is excluded from the split OK`

- [ ] **Step 6: 전체 스위트를 돌린다**

Run: `ctest --test-dir out/build -C Release`

Expected: 전부 통과(환경 스킵 `JobEscape.CurrentProcessReportsNotInJobByDefault` 1건 제외). 이 변경은 URDF 경로에만 닿으므로 `maya_contract`/`maya_publish`/`maya_lidar_publish`가 영향을 받으면 안 된다.

- [ ] **Step 7: 커밋**

```bash
git add python/maroUrdfExport.py tests/maya/test_urdf_export.py
git commit -m "feat(urdf): give skinned links their share of the mesh"
```

---

## 수동 확인 (구현 후)

`docs/maro-main-ui-manual-checklist.md`의 "Maro URDF 내보내기 > 시각 메쉬" 절에 다음을 추가한다:

- [ ] 스킨된 캐릭터(조인트 여러 개 + 메쉬 하나)에서 인플루언스 일부에만 축을
      바인딩하고 내보낸 뒤 RViz에서 띄운다 — 링크마다 자기 영역의 형상이
      보이고, 축을 바인딩하지 않은 조인트의 영역이 **구멍이 아니라** 가장
      가까운 조상 링크에 붙어 나오는지 확인한다. 관절을 움직이면 이음매가
      벌어지는 것은 정상이다(강체 링크로 스킨을 근사하는 데서 오는 한계).
