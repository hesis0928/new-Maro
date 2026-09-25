<!-- geo-hull-01 기하·수학 › 계산기하 (12개) 2026-09-17 -->

#### 볼록 껍질(convex hull) collision

**직관:** 점 집합을 감싸는 가장 작은 볼록 다면체를 충돌체로 쓰는 것. 실제 메쉬는 오목하고 복잡해도 물리 엔진은 볼록체를 훨씬 빨리 다루므로, URDF `<collision>`에는 시각 메쉬 대신 껍질을 넣는다.

**동작:** URDF 파이프라인 슬라이스 3 — 슬라이스 1·2가 만든 링크별 삼각형(강체 메쉬 또는 스킨 조각)의 정점을 `convexHull`에 넣어 껍질 삼각형을 얻고 `<name>_collision.stl`로 굽는다. 껍질이 퇴화하면(점이 4개 미만, 한 평면 위, 0 두께) 폴백으로 AABB `<box>`를 쓰고 0 두께 축은 1mm를 준다. scipy가 없어 QuickHull을 직접 구현했다.

**예시:**
```python
tris = mayaTrianglesToRosMeters(linkTriangles)
hull = convexHull([v for t in tris for v in t])
if hull is None:
    link["collisionBox"] = aabb(tris)       # 퇴화 폴백
else:
    writeStl(meshDir, name + "_collision.stl", hull)
```

**관련 코드:**
- `python/maroUrdfExport.py:1015-1175` — `convexHull`
- `python/maroUrdfExport.py:754-800` — 껍질 STL 쓰기와 `<box>` 폴백
- `tests/maya/test_urdf_export.py:1050-1180` — 껍질 부피·와인딩·성능 검증

**증거:**
- §1.3, §7.14, §9.2.6

**함정:** 오목한 파트(컵, ㄷ자 브래킷)는 껍질이 빈 공간을 채워 실제보다 크게 부딪힌다. 정밀 충돌이 필요하면 파트를 볼록 조각으로 나눠야 하는데 이는 범위 밖이다.

**교훈:** 충돌체는 "정확한 형상"이 아니라 "엔진이 다룰 수 있는 근사"다. 근사의 한계를 문서에 적는다.

#### 기저 변환(change of basis)

**직관:** 같은 점을 다른 좌표축으로 다시 적는 선형변환. Maya(Y-up)와 ROS(Z-up) 사이 변환은 X축 기준 −90° 회전 한 번이며, 행렬식이 +1이라 반사가 없다.

**동작:** `mayaToRos: (x,y,z)→(x,−z,y)`, 역은 `(x,z,−y)`. 두 우수좌표계 사이 변환은 항상 회전(det=+1)이므로 삼각형 와인딩이 보존되고 쿼터니언은 벡터부만 재배치하면 된다 — `R·q_v·R⁻¹` 공액이 벡터부에 R을 적용하는 것과 같다. 위치·회전·방향벡터는 같은 재배치를 받지만, 상대 변환(origin)과 회전각(limit)은 공액이라 불변이고 단일 축 벡터(URDF `<axis>`)만 재배치가 필요하다. 부호가 바뀌는 축(Maya +Z→ROS −Y)은 z=0 입력으로는 검증되지 않으므로(−0 == 0) 테스트는 그 축에 값을 넣는다.

**예시:**
```cpp
// Convert.h — X축 기준 -90도 회전, 행렬식 +1
//   mayaToRos: (x, y, z) -> ( x, -z,  y)
//   rosToMaya: (x, y, z) -> ( x,  z, -y)
```

**관련 코드:**
- `src/maro_transform/include/maro_transform/Convert.h:5-11` — 규칙과 행렬식 주석
- `tests/transform/test_convert.cpp` — 왕복 불변식과 부호 축 검증
- `python/maroUrdfExport.py:60-87` — 축 벡터 재배치 `_AXIS_VECTORS`

**증거:**
- §5.1, §5.1.2, §10.6

**함정:** "origin을 바꿨으니 axis도 따라온다"는 착각이 기본 리그 전부의 축을 틀리게 내보냈다. 공액으로 불변인 것과 명시 벡터로 재배치할 것을 구분한다.

**교훈:** 기저 변환에서 "무엇이 저절로 따라오고 무엇을 직접 바꿔야 하는가"를 수식으로 한 번 적고 테스트로 못 박는다.

#### SAT(분리축 정리)

**직관:** 두 볼록체가 겹치지 않으면 둘을 가르는 축(평면)이 반드시 있다는 정리. 후보 축마다 두 도형을 투영해 구간이 떨어지면 "분리", 모든 축에서 겹치면 "교차"다.

**동작:** `trianglesIntersect()`는 후보 축 11개 — 두 법선 `nA`·`nB`, 변×변 외적 9개 — 에 두 삼각형 꼭짓점을 투영해 `[min,max]` 구간이 `eps` 이상 떨어지면 분리로 반환한다. 공면(법선 평행 ∧ 평면 거리 < eps)이면 3D 축이 모두 법선과 평행해 폭 0이라 구분이 안 되므로 2D 볼록다각형 SAT(각 변의 평면 내 법선 `cross(n, edge)` 6개)로 전환한다. 접촉(간격 0)은 충돌로 취급하고, 퇴화 축(길이² < eps²)은 스킵한다. `eps`는 입력 스케일에 비례(`scale·1e-6`). Embree `rtcCollide`가 삼각형 씬에서 크래시해(F-024) 자체 SAT로 우회했다.

**예시:**
```cpp
bool trianglesIntersect(const Vec3d a[3], const Vec3d b[3]) {
    // 축: normalA, normalB, edgesA[i] x edgesB[j] (9)
    // 각 축에서 투영 구간이 eps 이상 떨어지면 분리 → false
    // 공면이면 2D SAT: cross(normal, edge) 6개
}
```

**관련 코드:**
- `src/maro_lidar/src/CollisionEngine.cpp:116-175` — 11축 + 공면 2D 분기
- `tests/lidar/test_collision_engine.cpp:57-240` — 축 종류별 케이스

**증거:**
- §5.2, §5.2.4, §11.5
- F-024

**함정:** 엄격 부등호(`<`)로 분리를 판정하면 정확히 맞닿은 삼각형이 "분리"가 된다. 접촉을 충돌로 보려면 `eps` 여유를 둔 비교여야 한다.

**교훈:** 기하 판정은 "이론적 정리"에 "수치 오차 정책(eps·퇴화·접촉)"을 더해야 코드가 된다. 정책을 주석으로 남긴다.

#### 정규직교 기저

**직관:** 서로 수직이고 길이가 1인 세 벡터 — 로컬 좌표계의 축. 방향 벡터 하나만 있을 때 그것을 로컬 Z로 삼는 기저를 만들어 오일러 각으로 바꾸면, 매니퓰레이터를 그 방향으로 놓을 수 있다.

**동작:** `axisBasisEulerXYZ(dir)`는 `dir`을 정규화해 Z로 두고, 월드 업(Y)을 참조로 `X = up × Z`, `Y = Z × X`를 만든 뒤 3×3 행렬을 XYZ 오일러(도)로 바꾼다. X/Y는 임의(1자유도 계라 매니퓰레이터가 로컬 Z만 씀)지만 항상 월드 업 기준으로 결정해 안정적이다. `dir`이 월드 업과 거의 평행하면 외적이 0에 가까워지므로(짐벌 특이점) 월드 X를 참조로 대신 쓴다.

**예시:**
```python
z = axisDirection.normal()
reference = MVector(0, 1, 0)                    # 월드 업
if abs(z * reference) > 0.999: reference = MVector(1, 0, 0)   # 평행 → X 참조
x = (reference ^ z).normal(); y = z ^ x
```

**관련 코드:**
- `python/maroLimitCalibration.py:27-60` — 기저 구성과 특이점 처리
- `tests/maya/test_limit_calibration_session.py` — 보정 세션 테스트

**증거:**
- §7.10

**함정:** 참조 벡터를 고정하지 않고 "아무 수직 벡터"를 쓰면 프레임마다 X/Y가 튀어 매니퓰레이터가 회전하는 것처럼 보인다.

**교훈:** 자유도가 남는 문제는 "임의"를 "결정적 임의"로 만든다. 참조를 고정하고 특이점만 예외 처리한다.

#### `convexHull(points, stats)`

**직관:** 3D 점 리스트에서 볼록 껍질 삼각형 리스트를 돌려주는 순수 Python QuickHull. `stats` dict를 주면 가시성 검사 횟수를 세어 성능 테스트가 벽시계 대신 그 수를 단언한다.

**동작:** (1) 축별 극점 6개에서 가장 멀리 떨어진 넷으로 초기 사면체, (2) 나머지 점을 "자기를 보는 면 하나"에 매달기(conflict list), (3) 어떤 면의 conflict 점 중 가장 먼 점 `p`를 골라 그 면에서 인접 면으로 BFS해 가시 영역, (4) 경계 변(horizon)과 `p`로 새 면, (5) 제거된 면의 conflict 점만 새 면에 재배정. `eps = span·1e-9`(상대). 모든 새 면의 방향은 사면체 무게중심 하나로 결정한다. 순진 증분식 O(n²)(원통 20000점 318s) → conflict list 0.96s.

**예시:**
```python
stats = {"visibilityChecks": 0}
hull = convexHull(points, stats)
assert stats["visibilityChecks"] < 200000     # 2000점 볼록 입력 상한
```

**관련 코드:**
- `python/maroUrdfExport.py:1015-1175` — 본체와 설계 주석
- `python/maroUrdfExport.py:1108-1112` — `visible()`과 stats 카운트
- `tests/maya/test_urdf_export.py:1162-1180` — 검사 횟수 상한 테스트

**증거:**
- §7.14, §9.2.6, §11.5

**함정:** 성능을 시간으로 재면 CI 머신에 따라 임계값이 느슨해져 이차식 회귀가 조용히 통과한다. 알고리즘의 일 단위(가시성 검사)를 세야 회귀가 잡힌다.

**교훈:** 알고리즘 성능 테스트는 "몇 초"가 아니라 "몇 번"을 단언한다. 그 수는 머신과 무관하다.

#### conflict list

**직관:** 아직 껍질에 안 들어간 점들을 "그 점을 볼 수 있는 면 하나"에 매달아 두는 자료구조. 새 정점을 넣을 때 전체 점을 다시 훑지 않고 영향받은 면의 점만 다시 배정하게 해 준다.

**동작:** 순진 증분식은 점마다 모든 면을 스캔해 볼록 입력에서 O(n²)가 된다(원통 5000점 18.9s, 20000점 318s). conflict list에서는 각 면이 자기 conflict 점 목록을 갖고, 각 점은 정확히 한 면에만 달린다. 면이 제거되면 그 면의 점들만 새 면들에 재배정하고, 어느 새 면에서도 안 보이면 내부로 확정해 폐기한다. 이 규칙이 O(n log n) 기대 시간을 만든다(0.96s). 플랜의 변이 지시("첫 배정 루프 break 제거")는 상한을 못 넘겨 무의미했고, 볼록 픽스처는 "껍질이 더 작다"를 증명할 수 없어 토러스(800→436)로 바꿨다.

**예시:**
```
면 F1: [p3, p7]     ← p3, p7은 F1 위쪽에서 F1을 본다
면 F2: [p5]
F1 제거 → p3, p7만 새 면들에 재배정 (p5는 건드리지 않음)
```

**관련 코드:**
- `python/maroUrdfExport.py:1020-1035` — "conflict list를 쓰는 이유" 주석
- `python/maroUrdfExport.py:1120-1175` — 배정·재배정 루프

**증거:**
- §7.14, §9.2.6, §11.5

**함정:** 한 점을 여러 면에 매달면 재배정에서 중복 처리되고 폐기 판정이 어긋난다. "정확히 한 면"이 불변식이다.

**교훈:** 증분 알고리즘의 성능은 "무엇을 다시 계산하지 않는가"에서 나온다. 그 불변식을 자료구조로 강제한다.

#### horizon 변

**직관:** 새 점에서 보이는 면 집합의 경계 — 보이는 면과 안 보이는 면 사이의 변들. 이 변들과 새 점을 이어 새 면을 만들면 껍질이 새 점을 감싸도록 자란다.

**동작:** 가시 영역을 BFS로 모은 뒤, 가시 면의 변 중 이웃 면이 비가시인 변을 horizon으로 모은다. 각 horizon 변 `(a, b)`와 apex `p`로 `addFace(a, b, p)`. 새 면의 방향(법선이 바깥을 향하도록 정점 순서)은 horizon 변의 방향을 따지지 않고 초기 사면체 무게중심(껍질 안에 반드시 있음)을 기준으로 정한다 — 그 편이 오류가 없다. 가시성은 "면 평면 위쪽 `> eps`"로 판정하며 `eps = span·1e-9`.

**예시:**
```python
horizon = []
for fid in visibleFaces:
    for e in edgesOf(fid):
        if neighbor(fid, e) not in visibleFaces:
            horizon.append(e)
fresh = [addFace(e[0], e[1], apex) for e in horizon]
```

**관련 코드:**
- `python/maroUrdfExport.py:1145-1165` — 가시 영역 BFS와 horizon 수집
- `python/maroUrdfExport.py:1079-1081` — 무게중심으로 면 방향 결정

**증거:**
- §7.14

**함정:** horizon 변의 방향으로 새 면의 와인딩을 정하려 하면 인접 면 순서 규약이 조금만 틀려도 안팎이 뒤집힌다. 내부 점 하나로 판정하는 편이 견고하다.

**교훈:** 방향 판정에 "확실히 안에 있는 점" 같은 전역 기준이 있으면 국소 규약보다 안전하다.

#### 가시 면

**직관:** 점 `p`가 면의 평면 바깥쪽(법선 방향)에 있으면 그 면은 `p`에서 "보인다". 보이는 면은 `p`를 넣으면 껍질 안으로 들어가므로 제거 대상이다.

**동작:** `visible(fid, p)`는 면 법선과 `p − 면의 한 점`의 내적이 `eps`보다 크면 참이다. 정점 삽입 시 `p`가 달린 면에서 시작해 인접 면으로 넓혀 가며 보이는 면 집합을 만든다(가시 영역은 연결돼 있으므로 BFS면 충분). 각 점은 자기가 보이는 면 하나에만 달리고, 제거된 면의 점만 새 면에 대해 다시 `visible`을 검사한다. `stats["visibilityChecks"]`가 이 호출 횟수를 센다.

**예시:**
```python
def visible(fid, pi):
    stats["visibilityChecks"] += 1
    n, p0 = faceNormal[fid], faceOrigin[fid]
    return dot(n, points[pi] - p0) > eps
```

**관련 코드:**
- `python/maroUrdfExport.py:1108-1112` — `visible`
- `python/maroUrdfExport.py:1145-1152` — 인접 면 BFS

**증거:**
- §7.14

**함정:** `eps`를 절대값(예: 1e-6 m)으로 두면 밀리미터 크기 파트에서 모든 점이 "보이지 않음"이 돼 껍질이 사면체에서 멈춘다. 입력 span에 비례시킨다.

**교훈:** 기하 판정의 임계값은 입력 스케일에 상대적이어야 한다. 단위가 바뀌는 파이프라인에서는 특히.

#### 극단점 초기 사면체

**직관:** QuickHull의 씨앗 — 축별 최소·최대 6점 중 서로 가장 멀리 떨어진 넷으로 첫 사면체를 만든다. 크고 균형 잡힌 씨앗이어야 이후 모든 면 방향 판정이 정확하다.

**동작:** x/y/z 각각의 min/max 점 6개에서 가장 먼 두 점(변), 그 변에서 가장 먼 점(삼각형), 그 평면에서 가장 먼 점(사면체)을 고른다. 어느 단계에서 거리가 `eps` 이하면 퇴화(점·선·평면)로 판정해 `None`을 돌려주고 호출자가 `<box>` 폴백을 쓴다. 사면체 무게중심은 껍질 안에 반드시 있으므로 이후 모든 새 면의 바깥 방향을 이 점으로 결정한다. 얇고 긴 씨앗은 면 방향 판정을 부정확하게 만든다.

**예시:**
```python
extremes = [argmin_x, argmax_x, argmin_y, argmax_y, argmin_z, argmax_z]
a, b = farthestPair(extremes)
c = farthestFromLine(points, a, b)
d = farthestFromPlane(points, a, b, c)
if d is None: return None          # 퇴화 → 호출자가 collisionBox
centroid = (P[a] + P[b] + P[c] + P[d]) / 4
```

**관련 코드:**
- `python/maroUrdfExport.py:1051-1081` — eps, 극단점 선택, 무게중심
- `python/maroUrdfExport.py:754-800` — 퇴화 시 `<box>` 폴백

**증거:**
- §7.14

**함정:** 첫 네 점을 "리스트의 처음 넷"으로 잡으면 거의 공면인 씨앗이 나와 법선이 불안정하고, 이후 가시성 판정이 뒤집힌다.

**교훈:** 반복 알고리즘의 초기값은 "아무거나"가 아니다. 이후 판정의 정확도를 결정하는 씨앗은 극단에서 고른다.

#### `mayaTrianglesToRosMeters`

**직관:** Maya 삼각형 정점을 ROS 좌표·미터로 바꾸는 함수 — `(x,−z,y)·scale`. 정점 순서는 그대로 둔다.

**동작:** 각 정점에 기저 재배치와 씬 단위 스케일을 적용한다. 재배치의 행렬식이 +1(X축 +90° 회전, 반사 아님)이라 삼각형 와인딩이 보존되어 법선이 뒤집히지 않는다. 그래서 정점 순서를 바꾸지 않아도 STL 법선이 바깥을 향한다. `test_urdf_export.py`는 발산정리로 부피 `V = 1/6·Σ v0·(v1×v2)`가 양수임을 확인해 와인딩을 검증한다.

**예시:**
```python
def mayaTrianglesToRosMeters(triangles):
    s = sceneUnitToMeters()
    return [tuple((x * s, -z * s, y * s) for (x, y, z) in tri) for tri in triangles]
```

**관련 코드:**
- `python/maroUrdfExport.py:973-1000` — 변환
- `tests/maya/test_urdf_export.py:520-530` — 와인딩 보존 주석
- `tests/maya/test_urdf_export.py:1055-1070` — 발산정리 부피 검사

**증거:**
- §7.14, §8.3.6

**함정:** 만약 변환에 반사가 있었다면(예: 좌수→우수) 정점 순서를 뒤집어야 한다. det의 부호를 확인하지 않고 "좌표만 바꾸면 된다"고 가정하면 안팎이 뒤집힌 STL이 나온다.

**교훈:** 좌표 변환 함수는 행렬식의 부호를 주석에 적는다. 와인딩을 건드릴지 말지가 거기서 결정된다.

#### 와인딩 보존

**직관:** 삼각형의 정점 순서(시계/반시계)가 변환 후에도 유지되는 것. 회전(det=+1)은 보존하고 반사(det=−1)는 뒤집는다. Maya→ROS 변환은 회전이므로 보존된다.

**동작:** STL 법선은 정점 순서에서 계산되므로 와인딩이 뒤집히면 메쉬가 안팎이 바뀌어 RViz에서 뒤집혀 보이거나 충돌체가 반전된다. 테스트는 내보낸 껍질의 부호 있는 부피(발산정리)가 양수임을 단언하고, 실패 메시지는 "exported triangle winding is inverted — the mesh would render inside-out"이다. 볼록 껍질 함수는 새 면의 방향을 무게중심으로 결정해 처음부터 바깥 와인딩을 보장한다.

**예시:**
```python
# 발산정리: V = 1/6 * sum(v0 . (v1 x v2)) — 바깥 와인딩이면 양수
assert signedVolume(hull) > 0, "exported triangle winding is inverted"
```

**관련 코드:**
- `tests/maya/test_urdf_export.py:1055-1070` — 부호 있는 부피 검사
- `python/maroUrdfExport.py:1079-1081` — 껍질 면 방향 결정
- `src/maro_transform/include/maro_transform/Convert.h:5-8` — det=+1 주석

**증거:**
- §7.14

**함정:** 뷰어에 따라 양면 렌더링이 기본이라 뒤집힌 메쉬가 정상처럼 보인다. 눈이 아니라 부호 있는 부피로 검증한다.

**교훈:** 방향성 불변식은 시각 확인이 아니라 수치(부호)로 테스트한다.

#### SAT 축 종류별 분기

**직관:** SAT 구현의 각 축 종류(면 법선, 변×변, 공면 2D, 퇴화)가 실제로 분리·교차를 결정하는 케이스를 하나씩 만들어 Maya 없이 gtest로 검증하는 테스트 설계.

**동작:** `test_collision_engine.cpp`(285줄)의 케이스: 공면 삼각형이 실제로 겹치면 충돌, 멀리 떨어지면 비충돌, 비공면 관통이면 충돌, **변×변 축으로만 분리가 증명되는** 배치는 비충돌(법선 축만으로는 겹쳐 보임), 퇴화(공선) 삼각형은 크래시 없이 비충돌, 점 삼각형이 정상 삼각형 안에 있으면 충돌, 변 하나·정점 하나만 공유해도 충돌(접촉=충돌). 각 케이스가 코드의 한 분기를 겨냥한다.

**예시:**
```cpp
TEST(CollisionEngine, SeparationOnlyProvableByEdgeCrossAxisReportsNoCollision) {
    // 두 법선 축에서는 투영이 겹치지만 edgeA x edgeB 축에서 분리되는 배치
    EXPECT_FALSE(trianglesIntersect(a, b));
}
```

**관련 코드:**
- `tests/lidar/test_collision_engine.cpp:57-240` — 분기별 케이스
- `src/maro_lidar/src/CollisionEngine.cpp:116-175` — 겨냥된 분기

**증거:**
- §8.2, §8.2.2

**함정:** 변×변 축 케이스는 만들기 어렵다 — 대충 놓으면 법선 축에서 이미 분리돼 9개 외적 축이 실행조차 안 된다. 그 축이 "유일한 증거"인 배치를 일부러 구성해야 한다.

**교훈:** 분기가 많은 알고리즘은 "각 분기가 결론을 바꾸는 입력"을 테스트로 갖는다. 커버리지가 아니라 결정력이 기준이다.
