# URDF 볼록 껍질 `<collision>` 구현 계획 (슬라이스 3/3)

> **에이전트 작업자에게:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development(권장)
> 또는 superpowers:executing-plans로 태스크 단위로 구현하라. 단계는 체크박스
> (`- [ ]`) 문법을 쓴다.

**목표:** 모든 링크가 `<collision>`을 갖도록 한다 -- 링크 삼각형의 볼록 껍질을
`<link>_collision.stl`로, 껍질을 만들 수 없는 퇴화 입력은 AABB `<box>`로.

**설계:** `docs/superpowers/specs/2026-09-10-maro-urdf-convex-hull-collision-design.md`

**아키텍처:** 순수 함수 둘(`convexHull`, `axisAlignedBox`)을
`python/maroUrdfExport.py`에 추가하고, `buildUrdfXml`에 `<collision>` 분기를
넣고, 기존 `_writeLinkMeshes` 루프가 시각 STL을 쓰는 바로 그 자리에서
호출한다. 씬 조회 코드는 한 줄도 새로 추가하지 않는다 -- 슬라이스 1·2가
이미 링크별 삼각형을 손에 쥐고 있고, 껍질은 그 삼각형의 정점만 쓴다.

**기술 스택:** 순수 파이썬(numpy 없음), `xml.etree.ElementTree`, 기존
`writeBinaryStl`. mayapy 배치 테스트.

## 전역 제약

- `cmake --build out/build --config Release`는 **C++를 고쳤을 때** 돌린다.
  이 계획은 `.py`와 테스트만 고치므로 빌드가 필요 없다 --
  `tests/maya/*.py` 57개가 전부 `sys.path.insert(0, <repo>/python)`으로
  소스를 직접 import한다(실측 확인). 플러그인 옆 스테이징 사본은 실제 Maya
  런타임용이다. **앞선 슬라이스 문서들이 반대로 적어 두었으니 따르지 마라.**
- `ctest --test-dir out/build -C Release --output-on-failure`가 전부
  통과해야 한다.
- 새 테스트 블록은 `tests/maya/test_urdf_export.py`의
  `maya.standalone.uninitialize()` **바로 앞**에 넣는다. 파일 끝은
  `sys.exit(0)` 뒤라 실행되지 않는다(슬라이스 2에서 RED 단계가 PASS로 나와
  발견한 실측 사실).
- 그 테스트 파일의 기존 이름을 그대로 쓴다: 모듈은 **`urdf`**
  (`import maroUrdfExport as urdf`), ElementTree는 **`ET2`**, struct는
  **`_struct`**. `math`/`tempfile`/`os`/`sys`는 이미 import돼 있고
  **`random`은 없다**(Task 1에서 추가한다).
- `_links` / `_meshDir` / `_byName`은 파일 앞부분이 이미 쓰는 이름이다.
  새 블록은 `_hull` 접두사를 붙여 가린다.
- 새 파이썬 모듈을 만들지 않는다 -- 전부 `python/maroUrdfExport.py` 안.
- `buildUrdfXml`은 순수 함수로 남는다: 파일 쓰기도 씬 조회도 하지 않는다.
- STL 쓰기는 기존 `writeBinaryStl`을 쓴다. 형식을 다시 구현하지 않는다.
- 새 `.py`는 `setStyleSheet()`를 호출하지 않는다.
- URDF 실수 포맷은 기존과 같은 `"{:.6f}"`.
- 퇴화 축 최소 두께는 **0.001**(ROS 미터 = 1mm).
- 껍질 계산은 **ROS 미터로 변환된 뒤의** 정점으로 한다 -- 박스 크기가 URDF에
  직접 들어가므로 미터여야 한다.

## 파일 구조

| 파일 | 책임 | 변경 |
|---|---|---|
| `python/maroUrdfExport.py` | 익스포트 전부 | 수정: `_vecSub`/`_vecCross`/`_vecDot`, `convexHull`, `axisAlignedBox` 추가, `buildUrdfXml`에 `<collision>` 분기, `_writeLinkMeshes` 배선 |
| `tests/maya/test_urdf_export.py` | 배치 테스트 | 수정: 태스크마다 블록 추가(teardown 앞) |

새 파일 없음.

---

### Task 1: `convexHull` -- conflict list QuickHull

**Files:**
- Modify: `python/maroUrdfExport.py` (`def _triangleNormal` 정의 **앞**에 삽입)
- Test: `tests/maya/test_urdf_export.py` (teardown 앞)

**Interfaces:**
- Consumes: 없음(순수 기하).
- Produces:
  - `_vecSub(a, b)`, `_vecCross(a, b)`, `_vecDot(a, b)` -- 3튜플 벡터 헬퍼.
  - `convexHull(points, stats=None) -> [((x,y,z),(x,y,z),(x,y,z)), ...] | None`
    -- 법선이 바깥을 향하는 삼각형 리스트. 점 4개 미만/전부 공선/전부 공면이면
    `None`. `stats`가 dict면 `stats["visibilityChecks"]`를 증가시킨다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/maya/test_urdf_export.py`의 `maya.standalone.uninitialize()` 바로 앞에
삽입:

```python
import random  # noqa: E402

print("[test] convexHull -- 볼록 껍질")

_hullCube = [(x, y, z) for x in (0.0, 1.0) for y in (0.0, 1.0)
             for z in (0.0, 1.0)]
_hullTris = urdf.convexHull(_hullCube)
# 큐브의 껍질은 면 6개 x 삼각형 2개 = 정확히 12개다. 이보다 많으면 같은
# 평면 위 점들을 별개 면으로 쪼갠 것이고(엡실론이 너무 빡빡), 적으면
# 껍질이 닫히지 않은 것이다.
assert _hullTris is not None and len(_hullTris) == 12, _hullTris


def _hullVolume(tris):
    """발산정리 부호 있는 부피. 법선이 바깥이면 양수 -- 슬라이스 1·2가
    와인딩 검증에 쓴 것과 같은 식이다."""
    total = 0.0
    for _a, _b, _c in tris:
        total += urdf._vecDot(_a, urdf._vecCross(_b, _c)) / 6.0
    return total


def _maxOutside(tris, points):
    """어떤 입력 점이 어떤 면의 바깥으로 튀어나온 최대 거리. 진짜 볼록
    껍질이면 0이다(수치 오차 범위 안)."""
    worst = 0.0
    for _a, _b, _c in tris:
        _nrm = urdf._vecCross(urdf._vecSub(_b, _a), urdf._vecSub(_c, _a))
        _scale = math.sqrt(urdf._vecDot(_nrm, _nrm)) or 1.0
        _off = urdf._vecDot(_nrm, _a)
        for _p in points:
            _d = (urdf._vecDot(_nrm, _p) - _off) / _scale
            if _d > worst:
                worst = _d
    return worst


assert abs(_hullVolume(_hullTris) - 1.0) < 1e-9, _hullVolume(_hullTris)
assert _maxOutside(_hullTris, _hullCube) < 1e-9

# 내부 점을 섞어도 껍질은 같아야 한다 -- 내부 점이 면을 만들어내면
# 껍질이 아니다.
_hullRng = random.Random(3)
_hullNoisy = _hullCube + [(_hullRng.uniform(0.2, 0.8),
                           _hullRng.uniform(0.2, 0.8),
                           _hullRng.uniform(0.2, 0.8)) for _ in range(200)]
_hullTris = urdf.convexHull(_hullNoisy)
assert len(_hullTris) == 12, len(_hullTris)
assert abs(_hullVolume(_hullTris) - 1.0) < 1e-9, _hullVolume(_hullTris)
assert _maxOutside(_hullTris, _hullNoisy) < 1e-9

# 중복점이 많아도 사면체 하나가 나와야 한다. 스킨 분할 조각은 이음매에서
# 같은 정점을 여러 번 담고 있으므로 이건 가짜 케이스가 아니다.
_hullDup = ([(0.0, 0.0, 0.0)] * 50 + [(1.0, 0.0, 0.0)] * 50
            + [(0.0, 1.0, 0.0)] * 50 + [(0.0, 0.0, 1.0)] * 50)
_hullTris = urdf.convexHull(_hullDup)
assert len(_hullTris) == 4, len(_hullTris)
assert abs(_hullVolume(_hullTris) - 1.0 / 6.0) < 1e-12, _hullVolume(_hullTris)

# 퇴화 3종은 전부 None -- 호출부는 이걸 보고 박스로 간다.
assert urdf.convexHull([(0, 0, 0), (1, 0, 0), (0, 1, 0)]) is None
assert urdf.convexHull([(float(_x), float(_y), 0.0)
                        for _x in range(5) for _y in range(5)]) is None
assert urdf.convexHull([(float(_i), 0.0, 0.0) for _i in range(10)]) is None
assert urdf.convexHull([]) is None

print("convex hull correctness OK (cube -> 12 tris, degenerates -> None)")
```

- [ ] **Step 2: 실패를 확인한다**

```bash
ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure
```

Expected: FAIL -- `AttributeError: module 'maroUrdfExport' has no attribute 'convexHull'`

**RED를 반드시 눈으로 봐라.** 이 파일은 블록을 잘못된 위치(`sys.exit(0)` 뒤)에
넣으면 조용히 PASS한다 -- 슬라이스 2가 그렇게 한 번 속았다.

- [ ] **Step 3: 구현한다**

`python/maroUrdfExport.py`의 `def _triangleNormal(a, b, c):` 바로 **앞**에
삽입:

```python
def _vecSub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _vecCross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _vecDot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def convexHull(points, stats=None):
    """(x,y,z) 시퀀스의 3D 볼록 껍질을 삼각형 리스트로 돌려준다.

    법선이 바깥을 향하는 와인딩이라 writeBinaryStl에 그대로 넘길 수 있다.
    점이 4개 미만이거나 전부 공선/공면이면 None -- 호출부가 그때 AABB
    박스로 폴백한다(설계 스펙 §4).

    **conflict list를 쓰는 이유**: 점마다 현재 면 전체를 훑는 순진한
    증분식은 볼록한 입력에서 이차식이 된다. 모든 정점이 껍질에 올라 면
    수가 점 수만큼 자라기 때문이다. 실측(원통형 점 집합): 순진한 구현은
    5000점 18.9초 / 20000점 318초, 이 구현은 20000점 0.96초다. 원통·박스·
    캡슐은 로봇 파트에서 예외가 아니라 기본이므로 최악의 경우가 곧 흔한
    경우다.

    각 점은 자기가 보이는 면 **하나**에만 달려 있다. 점을 껍질에 넣을 때는
    그 면에서 시작해 인접 면으로 넓히며 가시 영역을 찾고, 제거되는 면에
    달려 있던 점만 새 면으로 재배정한다.

    stats가 dict면 stats["visibilityChecks"]에 면-점 가시성 검사 횟수를
    누적한다. 성능 테스트가 벽시계 시간 대신 이 값을 본다 -- 시간 임계값은
    머신 부하 때문에 느슨할 수밖에 없고, 느슨한 임계값은 이차식 회귀를
    조용히 통과시킨다.
    """
    pts = [(float(p[0]), float(p[1]), float(p[2])) for p in points]
    n = len(pts)
    if n < 4:
        return None

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    span = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    if span <= 0.0:
        return None
    # 엡실론은 입력 크기에 **상대적**이다. 이 파이프라인은 미터를 다루므로
    # 고정 절대값을 쓰면 작은 파트가 통째로 퇴화로 보인다.
    eps = span * 1e-9

    # 초기 사면체는 극단점에서 시작한다 -- "처음 찾은 서로 다른 점"보다
    # 훨씬 안정적이다. 얇고 긴 씨앗 사면체는 이후 모든 면의 방향 판정을
    # 부정확하게 만든다.
    i0 = min(range(n), key=lambda i: pts[i])
    i1 = max(range(n), key=lambda i: pts[i])
    if i0 == i1:
        return None
    axis = _vecSub(pts[i1], pts[i0])
    i2, best = None, eps
    for i in range(n):
        d = _vecCross(axis, _vecSub(pts[i], pts[i0]))
        m = math.sqrt(_vecDot(d, d))
        if m > best:
            i2, best = i, m
    if i2 is None:
        return None  # 전부 공선
    seedNormal = _vecCross(axis, _vecSub(pts[i2], pts[i0]))
    i3, best = None, eps
    for i in range(n):
        d = abs(_vecDot(seedNormal, _vecSub(pts[i], pts[i0])))
        if d > best:
            i3, best = i, d
    if i3 is None:
        return None  # 전부 공면

    seed = (i0, i1, i2, i3)
    # 사면체의 무게중심은 껍질 안에 **반드시** 있다. 모든 새 면의 방향을
    # 이 점 하나로 결정하므로 horizon 변의 방향을 따지는 것보다 오류가 없다.
    interior = tuple(sum(pts[i][k] for i in seed) / 4.0 for k in range(3))

    faces = {}   # fid -> {"v": (a,b,c), "n": 법선, "off": dot(n,a), "pts": [점 인덱스]}
    edges = {}   # 방향 있는 (i,j) -> 그 변을 가진 fid
    nextId = [0]

    def addFace(a, b, c):
        normal = _vecCross(_vecSub(pts[b], pts[a]), _vecSub(pts[c], pts[a]))
        if _vecDot(normal, _vecSub(interior, pts[a])) > 0.0:
            b, c = c, b
            normal = (-normal[0], -normal[1], -normal[2])
        fid = nextId[0]
        nextId[0] += 1
        faces[fid] = {"v": (a, b, c), "n": normal,
                      "off": _vecDot(normal, pts[a]), "pts": []}
        edges[(a, b)] = fid
        edges[(b, c)] = fid
        edges[(c, a)] = fid
        return fid

    def dropFace(fid):
        a, b, c = faces[fid]["v"]
        for e in ((a, b), (b, c), (c, a)):
            if edges.get(e) == fid:
                del edges[e]
        del faces[fid]

    def visible(fid, pi):
        if stats is not None:
            stats["visibilityChecks"] = stats.get("visibilityChecks", 0) + 1
        f = faces[fid]
        # 법선을 정규화하지 않으므로 문턱도 면 크기에 비례해야 한다.
        scale = math.sqrt(_vecDot(f["n"], f["n"])) or 1.0
        return _vecDot(f["n"], pts[pi]) - f["off"] > eps * scale

    def distance(fid, pi):
        f = faces[fid]
        return _vecDot(f["n"], pts[pi]) - f["off"]

    for tri in ((i0, i1, i2), (i0, i1, i3), (i0, i2, i3), (i1, i2, i3)):
        addFace(*tri)

    seedSet = set(seed)
    for pi in range(n):
        if pi in seedSet:
            continue
        for fid in list(faces):
            if visible(fid, pi):
                faces[fid]["pts"].append(pi)
                break

    work = [fid for fid in faces if faces[fid]["pts"]]
    while work:
        fid = work.pop()
        f = faces.get(fid)
        if f is None or not f["pts"]:
            continue  # 이 면은 그 사이에 제거됐다
        apex = max(f["pts"], key=lambda pi: distance(fid, pi))

        seen = {fid}
        stack = [fid]
        while stack:
            cur = stack.pop()
            a, b, c = faces[cur]["v"]
            for e in ((a, b), (b, c), (c, a)):
                nb = edges.get((e[1], e[0]))
                if nb is None or nb in seen:
                    continue
                if visible(nb, apex):
                    seen.add(nb)
                    stack.append(nb)

        horizon = []
        orphans = []
        for vf in seen:
            a, b, c = faces[vf]["v"]
            for e in ((a, b), (b, c), (c, a)):
                nb = edges.get((e[1], e[0]))
                if nb is None or nb not in seen:
                    horizon.append(e)
            orphans.extend(faces[vf]["pts"])
        for vf in seen:
            dropFace(vf)

        fresh = [addFace(e[0], e[1], apex) for e in horizon]
        for pi in orphans:
            if pi == apex:
                continue
            for nf in fresh:
                if visible(nf, pi):
                    faces[nf]["pts"].append(pi)
                    break
        work.extend(nf for nf in fresh if faces[nf]["pts"])

    return [tuple(pts[i] for i in faces[fid]["v"]) for fid in faces]
```

- [ ] **Step 4: 통과를 확인한다**

```bash
ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure
```

Expected: PASS -- `convex hull correctness OK (cube -> 12 tris, degenerates -> None)`

- [ ] **Step 5: 성능 테스트를 쓴다(가시성 검사 횟수)**

Step 1의 블록 **뒤**, 여전히 teardown 앞에 삽입:

```python
print("[test] convexHull -- 볼록 입력 성능")

# 원통은 이 슬라이스가 겨냥한 최악의 경우다: 모든 점이 껍질에 오른다.
_hullRng = random.Random(11)
_hullCyl = []
for _ in range(2000):
    _t = _hullRng.uniform(0.0, 2.0 * math.pi)
    _hullCyl.append((math.cos(_t), math.sin(_t), _hullRng.uniform(-1.0, 1.0)))

_hullStats = {"visibilityChecks": 0}
_hullTris = urdf.convexHull(_hullCyl, _hullStats)
# 볼록 입력에서 껍질은 단체(simplicial)이므로 면 = 2 x 정점 - 4다.
# 2000점이면 3996 -- 실측으로 정확히 맞는다.
assert _hullTris is not None and len(_hullTris) == 3996, len(_hullTris)
assert _maxOutside(_hullTris, _hullCyl) < 1e-8
assert _hullVolume(_hullTris) > 0.0, _hullVolume(_hullTris)

# 실측: conflict list 구현은 71,638회(점당 35.8회). 점마다 면 전체를 훑는
# 순진한 구현은 약 400만회(점당 2000회)다. 상한 200,000은 그 사이를
# 넉넉히 가르므로 이차식으로 회귀하면 반드시 걸린다. 벽시계 시간이 아니라
# 이 값을 보는 이유는 시간 임계값이 느슨해질 수밖에 없기 때문이다.
assert _hullStats["visibilityChecks"] < 200000, _hullStats["visibilityChecks"]
print("convex-input performance OK (%d visibility checks for 2000 points, "
      "%.1f per point)"
      % (_hullStats["visibilityChecks"],
         _hullStats["visibilityChecks"] / 2000.0))
```

- [ ] **Step 6: 성능 테스트가 통과하는지 확인한다**

```bash
ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure
```

Expected: PASS -- 대략 `71638 visibility checks for 2000 points, 35.8 per point`

이 테스트는 Step 3이 이미 있으므로 RED로 시작하지 않는다. **상한이 진짜로
무는지 확인하려면**: 첫 배정 루프의 `break`를 잠깐 지워 모든 면을 훑게 하면
실패해야 한다. 확인했으면 되돌린다.

- [ ] **Step 7: 커밋**

```bash
git add python/maroUrdfExport.py tests/maya/test_urdf_export.py && git commit -m "feat(urdf): conflict-list QuickHull for collision geometry"
```

---

### Task 2: `axisAlignedBox` 폴백과 `buildUrdfXml`의 `<collision>` 분기

**Files:**
- Modify: `python/maroUrdfExport.py` (`convexHull` 뒤에 `axisAlignedBox`;
  `buildUrdfXml` 안 `<visual>` 블록 뒤에 분기)
- Test: `tests/maya/test_urdf_export.py` (teardown 앞)

**Interfaces:**
- Consumes: Task 1의 `convexHull`(여기서 호출하지는 않는다 -- 배선은 Task 3).
- Produces:
  - `axisAlignedBox(points) -> {"size": (sx,sy,sz), "center": (cx,cy,cz)} | None`
    -- 점이 없으면 `None`. 두께가 0인 축은 0.001로 올린다.
  - `MIN_COLLISION_BOX_EXTENT = 0.001`
  - `buildUrdfXml`이 링크 딕셔너리의 `collisionMesh`(경로 문자열) 또는
    `collisionBox`(위 dict)를 읽어 `<collision>`을 낸다. 둘 다 없으면
    `<collision>` 자체가 없다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

teardown 앞에 삽입:

```python
print("[test] axisAlignedBox와 <collision> 분기")

_hullBox = urdf.axisAlignedBox(
    [(-1.0, 2.0, 0.5), (3.0, 6.0, 2.5), (1.0, 4.0, 1.5)])
assert _hullBox["size"] == (4.0, 4.0, 2.0), _hullBox["size"]
assert _hullBox["center"] == (1.0, 4.0, 1.5), _hullBox["center"]

# 공면 입력: 두께 0인 축이 1mm로 올라가고, 중심은 그 평면 위에 남는다.
_hullFlat = urdf.axisAlignedBox(
    [(0.0, 0.0, 7.0), (2.0, 0.0, 7.0), (2.0, 4.0, 7.0), (0.0, 4.0, 7.0)])
assert _hullFlat["size"] == (2.0, 4.0, 0.001), _hullFlat["size"]
assert _hullFlat["center"] == (1.0, 2.0, 7.0), _hullFlat["center"]

# 점 하나: 세 축 전부 1mm.
_hullSingle = urdf.axisAlignedBox([(5.0, 5.0, 5.0)])
assert _hullSingle["size"] == (0.001, 0.001, 0.001), _hullSingle["size"]
assert urdf.axisAlignedBox([]) is None

_hullXml = urdf.buildUrdfXml("bot", [
    {"name": "meshLink",
     "collisionMesh": "package://bot/meshes/a_collision.stl"},
    {"name": "boxLink",
     "collisionBox": {"size": (0.2, 0.3, 0.4), "center": (0.0, 0.1, -0.2)}},
    {"name": "bareLink"},
], [])

_hullByName = {_el.get("name"): _el for _el in _hullXml.findall("link")}

_hullMeshCol = _hullByName["meshLink"].find("collision")
assert _hullMeshCol is not None
assert _hullMeshCol.find("geometry/mesh").get("filename") \
    == "package://bot/meshes/a_collision.stl"
# 메쉬는 정점을 이미 링크 프레임으로 구웠으므로 원점이 항등이다.
assert _hullMeshCol.find("origin").get("xyz") == "0 0 0", \
    _hullMeshCol.find("origin").get("xyz")

_hullBoxCol = _hullByName["boxLink"].find("collision")
assert _hullBoxCol is not None
assert _hullBoxCol.find("geometry/box").get("size") \
    == "0.200000 0.300000 0.400000", _hullBoxCol.find("geometry/box").get("size")
# 박스는 자기 원점 중심으로 정의되므로 AABB 중심을 <origin>으로 옮겨야
# 한다 -- 메쉬와 달리 여기는 항등이 아니다.
assert _hullBoxCol.find("origin").get("xyz") == "0.000000 0.100000 -0.200000", \
    _hullBoxCol.find("origin").get("xyz")

# 두 필드 다 없으면 <collision> 자체가 없다. 지오메트리가 아예 없는
# 조인트는 에러가 아니다.
assert _hullByName["bareLink"].find("collision") is None

# 기존 호출부(두 키가 아예 없는 링크)도 그대로 동작해야 한다.
assert urdf.buildUrdfXml("bot", [{"name": "L"}], []).find("link").get("name") \
    == "L"

print("axisAlignedBox and <collision> branching OK")
```

- [ ] **Step 2: 실패를 확인한다**

```bash
ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure
```

Expected: FAIL -- `AttributeError: module 'maroUrdfExport' has no attribute 'axisAlignedBox'`

- [ ] **Step 3: `axisAlignedBox`를 구현한다**

`convexHull` 정의 바로 뒤에 삽입:

```python
# 물리 엔진은 크기가 0인 <box>를 거부하거나 정의되지 않은 동작을 한다.
# 1mm는 이 프로젝트의 로봇 스케일에서 무시할 수 있으면서 0이 아니다.
MIN_COLLISION_BOX_EXTENT = 0.001


def axisAlignedBox(points):
    """ROS 미터 점들의 축 정렬 경계상자를 {"size", "center"}로 돌려준다.

    convexHull이 None을 준 링크(점 4개 미만, 전부 공선, 전부 공면)의
    폴백이다. 점이 하나도 없으면 None -- 그 링크는 <collision>을 내지
    않는다.

    두께가 0인 축은 MIN_COLLISION_BOX_EXTENT로 올린다. 중심은 옮기지
    않으므로 부풀린 박스는 원래 평면을 가운데 두고 대칭이다.
    """
    if not points:
        return None
    lo = [min(p[k] for p in points) for k in range(3)]
    hi = [max(p[k] for p in points) for k in range(3)]
    size = tuple(max(hi[k] - lo[k], MIN_COLLISION_BOX_EXTENT) for k in range(3))
    center = tuple((hi[k] + lo[k]) / 2.0 for k in range(3))
    return {"size": size, "center": center}
```

- [ ] **Step 4: `buildUrdfXml`에 분기를 넣는다**

`buildUrdfXml` 안, `ET.SubElement(geometryEl, "mesh", filename=visualMesh)`로
끝나는 `<visual>` 블록 **바로 뒤**(같은 `for link in links:` 루프 안,
`visualMesh = link.get("visualMesh")`와 같은 들여쓰기)에 삽입:

```python
        # 충돌체는 껍질 메쉬이거나 폴백 박스다 -- 둘 다 선택적이고 동시에
        # 오지 않는다(설계 스펙 §2). 둘 다 없으면 <collision>을 내지
        # 않는다: 지오메트리가 아예 없는 조인트는 에러가 아니다.
        collisionMesh = link.get("collisionMesh")
        collisionBox = link.get("collisionBox")
        if collisionMesh:
            collisionEl = ET.SubElement(linkEl, "collision")
            ET.SubElement(collisionEl, "origin", xyz="0 0 0", rpy="0 0 0")
            geometryEl = ET.SubElement(collisionEl, "geometry")
            ET.SubElement(geometryEl, "mesh", filename=collisionMesh)
        elif collisionBox:
            collisionEl = ET.SubElement(linkEl, "collision")
            # 메쉬는 정점을 링크 프레임으로 구워 원점이 항등이지만, <box>는
            # 자기 원점 중심으로 정의되므로 AABB 중심을 여기로 옮겨야 한다.
            bx, by, bz = collisionBox["center"]
            sx, sy, sz = collisionBox["size"]
            ET.SubElement(collisionEl, "origin",
                          xyz="{:.6f} {:.6f} {:.6f}".format(bx, by, bz),
                          rpy="0 0 0")
            geometryEl = ET.SubElement(collisionEl, "geometry")
            ET.SubElement(geometryEl, "box",
                          size="{:.6f} {:.6f} {:.6f}".format(sx, sy, sz))
```

`buildUrdfXml`의 docstring 첫 줄도 새 필드를 반영해 고친다:

```python
    """links: [{"name": str, "visualMesh": str|None(선택),
    "collisionMesh": str|None(선택),
    "collisionBox": {"size": (sx,sy,sz), "center": (cx,cy,cz)}|None(선택)}, ...].
```

- [ ] **Step 5: 통과를 확인한다**

```bash
ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure
```

Expected: PASS -- `axisAlignedBox and <collision> branching OK`

- [ ] **Step 6: 커밋**

```bash
git add python/maroUrdfExport.py tests/maya/test_urdf_export.py && git commit -m "feat(urdf): emit <collision> from hull mesh or AABB box fallback"
```

---

### Task 3: `_writeLinkMeshes` 배선과 통합 테스트

**Files:**
- Modify: `python/maroUrdfExport.py` (`_writeLinkMeshes`의 링크 루프 끝)
- Test: `tests/maya/test_urdf_export.py` (teardown 앞)

**Interfaces:**
- Consumes: Task 1의 `convexHull`, Task 2의 `axisAlignedBox`, 기존
  `mayaTrianglesToRosMeters` / `writeBinaryStl` / `sanitizeMeshFileName`.
  테스트는 Task 1이 정의한 `_hullVolume` / `_maxOutside`를 재사용한다 --
  **이 블록은 Task 1 블록보다 뒤에 와야 한다.**
- Produces: `_writeLinkMeshes`가 링크마다 `<name>_collision.stl`을 쓰고
  `link["collisionMesh"]`를 채운다. 껍질을 못 만들면 대신
  `link["collisionBox"]`를 채운다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

teardown 앞에 삽입:

```python
print("[test] export -- <visual>과 <collision>이 함께 나온다")

cmds.file(new=True, force=True)
cmds.currentUnit(angle="rad")
cmds.currentUnit(linear="cm")

_hullRoot = cmds.polyCube(name="hullBody", width=2.0, height=2.0,
                          depth=2.0)[0]
# 팔은 **오목**해야 한다. 볼록 입력에서는 껍질이 단체가 되어 면 = 2 x 정점
# - 4가 정확히 성립하는데, Maya의 실린더/구/큐브 삼각형 수가 이미 그 값이라
# "껍질이 더 적다"는 주장이 참이 될 수 없다(실측: 실린더 sub20은 시각 76
# 대 껍질 76, 구는 760 대 760, 큐브는 12 대 12로 전부 동수). 토러스는
# 껍질이 가운데 구멍을 메우므로 800 -> 436으로 실제로 줄어든다.
_hullArm = cmds.polyTorus(name="hullArm")[0]
cmds.move(0.0, 5.0, 0.0, _hullArm)

_hullRootAxis = cmds.createNode("maroAxis", name="hullRootAxis",
                                parent=_hullRoot)
_hullArmAxis = cmds.createNode("maroAxis", name="hullArmAxis", parent=_hullArm)
cmds.maroBindAxis(_hullRootAxis, _hullRoot)
cmds.maroBindAxis(_hullArmAxis, _hullArm)
cmds.connectAttr(_hullRootAxis + ".axisOut", _hullArmAxis + ".parentAxis")

_hullOutDir = os.path.join(tempfile.mkdtemp(), "hullbot")
os.makedirs(_hullOutDir)
_hullUrdfPath = os.path.join(_hullOutDir, "hullbot.urdf")
urdf.export(_hullUrdfPath)

_hullLinks = {_el.get("name"): _el
              for _el in ET2.parse(_hullUrdfPath).getroot().findall("link")}
assert len(_hullLinks) == 2, sorted(_hullLinks)

for _name, _el in _hullLinks.items():
    _vis = _el.find("visual/geometry/mesh")
    _col = _el.find("collision/geometry/mesh")
    assert _vis is not None, "%s has no <visual> mesh" % _name
    assert _col is not None, "%s has no <collision> mesh" % _name
    # 충돌 메쉬는 시각 메쉬와 **다른** 파일이어야 한다. 같으면 껍질을
    # 계산하지 않고 경로만 복사한 것이다.
    assert _col.get("filename") != _vis.get("filename"), _col.get("filename")
    assert _col.get("filename").endswith("_collision.stl"), _col.get("filename")


def _readStlTris(path):
    with open(path, "rb") as _fh:
        _fh.seek(80)
        _count = _struct.unpack("<I", _fh.read(4))[0]
        _out = []
        for _ in range(_count):
            _vals = _struct.unpack("<12f", _fh.read(50)[:48])
            _out.append((tuple(_vals[3:6]), tuple(_vals[6:9]),
                         tuple(_vals[9:12])))
    return _out


_hullMeshDir = os.path.join(_hullOutDir, "meshes")
_hullArmVis = _readStlTris(os.path.join(_hullMeshDir, "hullArm.stl"))
_hullArmCol = _readStlTris(os.path.join(_hullMeshDir,
                                        "hullArm_collision.stl"))
# 토러스는 오목하므로 껍질이 구멍을 메우며 면이 줄어든다(실측 800 -> 436).
assert 0 < len(_hullArmCol) < len(_hullArmVis), \
    (len(_hullArmCol), len(_hullArmVis))

# 충돌 껍질은 시각 메쉬를 **감싸야** 한다 -- 안쪽으로 파고들면 그 부분이
# 물리적으로 통과된다. float32로 왕복했으므로 허용 오차는 float64 테스트
# (1e-9)보다 커야 한다.
_hullArmVerts = [_v for _tri in _hullArmVis for _v in _tri]
assert _maxOutside(_hullArmCol, _hullArmVerts) < 1e-5, \
    _maxOutside(_hullArmCol, _hullArmVerts)
assert _hullVolume(_hullArmCol) > 0.0, _hullVolume(_hullArmCol)

print("export emits <visual> + <collision> OK (arm hull %d tris vs visual %d)"
      % (len(_hullArmCol), len(_hullArmVis)))
```

- [ ] **Step 2: 실패를 확인한다**

```bash
ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure
```

Expected: FAIL -- `AssertionError: hullArm has no <collision> mesh`

- [ ] **Step 3: `_writeLinkMeshes`를 배선한다**

`_writeLinkMeshes`의 링크 루프 끝부분, 지금 이렇게 되어 있는 곳:

```python
        fileName = sanitizeMeshFileName(link["name"], usedNames)
        if not os.path.isdir(meshDir):
            os.makedirs(meshDir)
        writeBinaryStl(mayaTrianglesToRosMeters(triangles),
                       os.path.join(meshDir, fileName + ".stl"))
        link["visualMesh"] = "package://{}/meshes/{}.stl".format(robotName, fileName)
```

를 이것으로 바꾼다:

```python
        fileName = sanitizeMeshFileName(link["name"], usedNames)
        if not os.path.isdir(meshDir):
            os.makedirs(meshDir)
        # 변환을 한 번만 하고 껍질도 이 결과로 계산한다 -- 박스 크기가
        # URDF에 직접 들어가므로 ROS 미터여야 한다.
        rosTriangles = mayaTrianglesToRosMeters(triangles)
        writeBinaryStl(rosTriangles, os.path.join(meshDir, fileName + ".stl"))
        link["visualMesh"] = "package://{}/meshes/{}.stl".format(robotName, fileName)

        hullPoints = [corner for tri in rosTriangles for corner in tri]
        hull = convexHull(hullPoints)
        if hull:
            collisionName = fileName + "_collision"
            writeBinaryStl(hull, os.path.join(meshDir, collisionName + ".stl"))
            link["collisionMesh"] = "package://{}/meshes/{}.stl".format(
                robotName, collisionName)
        else:
            # 퇴화 링크(평면 판, 점 몇 개)는 껍질이 없다. 파일을 쓰지 않고
            # URDF 안에 박스로 낸다(설계 스펙 §4).
            link["collisionBox"] = axisAlignedBox(hullPoints)
```

`_writeLinkMeshes`의 docstring 첫 문단도 고친다:

```python
    """각 링크의 메쉬를 STL로 쓰고 link["visualMesh"]에 package:// 경로를
    채운다. 이어서 그 삼각형의 볼록 껍질을 <name>_collision.stl로 쓰고
    link["collisionMesh"]를 채운다 -- 껍질이 퇴화해 만들어지지 않으면
    대신 link["collisionBox"]에 AABB를 채운다. 메쉬가 없거나 삼각형이
    0개인 링크는 건드리지 않는다 -- 그 링크는 <visual>도 <collision>도
    없이 나가며 이는 정상이고 에러가 아니다.
```

- [ ] **Step 4: 통과를 확인한다**

```bash
ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure
```

Expected: PASS -- `export emits <visual> + <collision> OK (arm hull 436 tris vs visual 800)`

- [ ] **Step 5: 전체 스위트를 돌린다**

```bash
ctest --test-dir out/build -C Release --output-on-failure
```

Expected: 전부 PASS. 특히 슬라이스 1·2의 URDF 테스트가 그대로 그린이어야
한다 -- `_writeLinkMeshes`의 시각 경로는 동작이 바뀌지 않았다.

- [ ] **Step 6: 커밋**

```bash
git add python/maroUrdfExport.py tests/maya/test_urdf_export.py && git commit -m "feat(urdf): write per-link convex hull collision meshes"
```

---

## 자체 검토

**스펙 커버리지**

| 스펙 절 | 태스크 |
|---|---|
| §2 부착 지점, `collisionMesh`/`collisionBox` 두 필드, 껍질 함수 계약 | Task 2(필드·XML), Task 3(배선) |
| §2 파일명 `_collision` 접미사, 살균 결과 공유 | Task 3 Step 3(`fileName + "_collision"`이라 일련번호가 자동 일치) |
| §3 QuickHull conflict list, 절차 4단계 | Task 1 Step 3 |
| §4 폴백 3종, 박스 `<origin>` 중심, 1mm 최소 두께, 점 0개 → 없음 | Task 2 Step 3·4 |
| §5 볼록 오버슈트 한계 | 코드 변경 없음(문서화된 수용 한계). Task 3의 토러스 픽스처가 이 한계를 그대로 드러낸다 -- 껍질이 구멍을 메운다 |
| §6 테스트 7종 | 정확성·와인딩·위/안: T1 S1 / 성능: T1 S5 / 폴백 3종: T2 / 분기: T2 / 통합: T3 |
| §7 범위 밖 | 어느 태스크도 볼록 분해·프리미티브 인식·`<inertial>`·numpy를 건드리지 않는다 |

**타입 일관성**: `convexHull`은 삼각형 리스트 또는 `None`(T1) → T3가 truthiness로
분기 → `writeBinaryStl(hull, ...)`가 받는 형태와 동일. `axisAlignedBox`는
`{"size","center"}`(T2) → T3가 `link["collisionBox"]`에 넣고 → `buildUrdfXml`이
같은 두 키로 읽는다(T2). `stats` 키는 `"visibilityChecks"`로 T1 S3·S5 일치.

**블록 순서**: T3의 테스트가 T1이 정의한 `_hullVolume` / `_maxOutside`를 쓴다.
세 블록 모두 teardown 앞 모듈 스코프이고 T1이 먼저이므로 보인다 --
**순서를 뒤집으면 `NameError`가 난다.**

## 계획을 쓰며 실측으로 잡은 함정 2건

1. **볼록 픽스처는 "껍질이 더 작다"를 증명할 수 없다.** 볼록 입력의 껍질은
   단체라 면 = 2 x 정점 - 4이고, Maya 프리미티브의 삼각형 수가 이미 그
   값이다: 실린더 sub20 76=76, 구 760=760, 큐브 12=12. 처음에 실린더로
   쓴 통합 테스트는 반드시 실패했을 것이다. 토러스(800→436)로 바꿨다.
2. **`.py`만 고쳤을 때 `cmake --build`가 필요하다는 전제가 틀렸다.**
   `tests/maya/*.py` 57개가 전부 소스 `python/`을 `sys.path[0]`에 넣고,
   플러그인은 이 모듈을 import하지 않는다(`urdf.__file__`로 실측 확인).

## 남는 한계(코드로 해결하지 않음)

- **오목 파트가 부푼다.** L자 파트는 껍질이 안쪽을 메워 실제보다 큰 충돌체가
  된다. 볼록 근사의 정의이며 볼록 분해가 별도 작업이다(스펙 §5).
- **RViz/Gazebo에서 눈으로 확인**은 이 머신에서 불가능하다 -- ROS 2 설치가
  최소 구성이라 `rviz2`도 `robot_state_publisher`도 없다. 렌더러 없이 검증
  가능한 것(와인딩, 스케일, 껍질이 시각 메쉬를 감싸는지)은 전부 자동화했다.
