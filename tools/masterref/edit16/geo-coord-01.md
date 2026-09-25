<!-- geo-coord-01 기하·수학 › 좌표계·변환 (22개) 2026-09-17 -->

#### Y-up

**직관:** "위"가 +Y인 좌표계 — Maya의 기본. ROS(Z-up)와 다르므로 Maro의 모든 좌표 변환은 이 차이 하나를 다루는 것이다.

**동작:** Maya는 Y-up, 우수좌표계, 씬 단위 cm 기본이다. Maya→ROS 변환의 본질은 X축 −90° 회전: 위치 `(x,y,z)→(x·s, −z·s, y·s)`, 쿼터니언 벡터부도 같은 재배치, `w` 불변, 스케일 `s`는 위치에만. LiDAR 레이 패턴의 방향 벡터 `(cosV·sinH, sinV, cosV·cosH)`도 Y-up 관례(+Y가 위, +Z가 정면)로 정의된다. 변환은 `maro_transform`의 상태 없는 순수 함수로 고립돼 왕복 불변식을 랜덤 테스트한다.

**예시:**
```
Maya (Y-up):  x 오른쪽, y 위, z 앞(카메라 쪽)
ROS  (Z-up):  x 앞,    y 왼쪽, z 위
Maya (0, 100, 0) cm  →  ROS (0, 0, 1) m
```

**관련 코드:**
- `src/maro_transform/include/maro_transform/Convert.h:5-18` — 규칙
- `src/maro_lidar/src/RayPattern.cpp:18-40` — Y-up 구면 좌표
- `tests/transform/test_convert.cpp:29-40` — "MayaUpBecomesRosUp"

**증거:**
- §5.1, §5.2.2, §9.2.1

**함정:** Maya 환경설정에서 Z-up으로 바꿀 수 있지만 Maro는 Y-up을 가정한다. 씬이 Z-up이면 변환이 이중으로 걸려 로봇이 눕는다.

**교훈:** 업 축은 파이프라인 전체의 가정이다. 한 곳(변환 모듈)에 명시하고 다른 곳은 그것을 부른다.

#### Z-up

**직관:** "위"가 +Z인 좌표계 — ROS REP-103의 규약(X 앞, Y 왼쪽, Z 위). Maro가 내보내는 모든 위치·회전·포인트클라우드는 이 좌표계다.

**동작:** `mayaToRosPosition`이 Y-up→Z-up 재배치를 하고, `PointCloud2`·`TFMessage`·URDF 모두 그 결과를 담는다. `maro_lidar`의 `packPointCloud`는 좌표 변환을 하지 않는다 — 입력이 이미 ROS 좌표여야 한다(호출자 `MaroRosRuntime`이 변환 후 넘김). 수신 방향(`joint_commands`)은 각도·거리 스칼라라 축 재배치가 없고 단위 변환만 한다.

**예시:**
```cpp
Vec3 ros = maro::mayaToRosPosition(mayaPoint, unit);   // Z-up, m
auto packed = maro::lidar::packPointCloud(rosPoints, {});  // 변환 없음, ROS 좌표 가정
```

**관련 코드:**
- `src/maro_plugin/MaroRosRuntime.cpp:210-235` — 변환 후 패킹
- `src/maro_lidar/src/PointCloudPacking.cpp:8-30` — 변환하지 않는 패킹

**증거:**
- §5.1, §5.2.5, §9.2.1, §11.3

**함정:** 패킹 함수가 변환하지 않는다는 계약을 잊고 Maya 좌표를 넘기면 포인트클라우드가 옆으로 눕는다. 계약은 함수 주석과 호출부 양쪽에 있다.

**교훈:** "변환하는 층"을 하나로 정하고 그 아래 층은 "이미 변환됐다"를 가정한다. 가정을 주석으로 못 박는다.

#### 우수좌표계(right-handed)

**직관:** 오른손 법칙(X×Y=Z)을 따르는 좌표계. Maya도 ROS도 우수이므로 둘 사이 변환은 반사 없는 순수 회전이다.

**동작:** 두 우수좌표계 사이 변환은 항상 det=+1 회전이다. 그래서 삼각형 와인딩이 보존되고(STL 법선 유지), 쿼터니언은 벡터부만 재배치하면 되며(공액), 방향 벡터·위치·회전이 같은 규칙을 따른다. Maya→ROS는 X축 −90° 회전이라는 것을 `Convert.h` 주석이 "행렬식이 +1이라 우수좌표계가 보존된다"로 적는다.

**예시:**
```
X × Y = Z 확인:
Maya: (1,0,0) × (0,1,0) = (0,0,1) ✓
ROS:  (1,0,0) × (0,1,0) = (0,0,1) ✓   → 둘 다 우수 → 변환은 회전
```

**관련 코드:**
- `src/maro_transform/include/maro_transform/Convert.h:5-8` — 우수 보존 주석
- `tests/maya/test_urdf_export.py:520-530` — 와인딩 보존 근거

**증거:**
- §5.1, §5.1.2

**함정:** DirectX·Unity 같은 좌수 좌표계와 섞이면 반사(det=−1)가 끼어 와인딩·쿼터니언 규칙이 전부 바뀐다. Maro는 좌수 시스템을 다루지 않는다.

**교훈:** 변환 설계의 첫 질문은 "양쪽 손잡이가 같은가"다. 같으면 회전 하나, 다르면 반사까지 처리한다.

#### 행렬식(det) +1

**직관:** 3×3 변환 행렬의 행렬식이 +1이면 방향을 보존하는 회전, −1이면 반사. Maya→ROS 재배치는 +1이다.

**동작:** `(x,y,z)→(x,−z,y)`의 행렬(행: (1,0,0), (0,0,−1), (0,1,0))은 det = 1·(0·0 − (−1)·1) = +1. 이것이 세 가지를 보장한다 — 와인딩 보존(STL 법선), 쿼터니언 벡터부만 재배치, 방향 벡터 규칙 동일. 부호가 실제로 바뀌는 축(Maya +Z→ROS −Y)은 z=0 입력으로는 검증되지 않으므로(−0 == 0) 테스트가 그 축에 값을 넣는다. 상대 변환(origin)과 회전각(limit)은 공액이라 불변, 단일 축 벡터(URDF `<axis>`)만 재배치가 필요하다.

**예시:**
```
R = ( 1  0  0 )
    ( 0  0 -1 )
    ( 0  1  0 )     det(R) = +1  → 회전, 반사 아님
```

**관련 코드:**
- `src/maro_transform/include/maro_transform/Convert.h:5-8` — det 주석
- `tests/transform/test_convert.cpp:64-88` — 부호가 뒤집히는 축 검사
- `tests/maya/test_urdf_export.py:1055-1070` — 와인딩(부피 부호) 검사

**증거:**
- §5.1, §5.1.2, §7.14

**함정:** 왕복 테스트(`rosToMaya(mayaToRos(x)) == x`)는 반사도 통과시킨다 — 반사 두 번은 항등이다. det의 부호는 왕복이 아니라 단방향 부호 검사로 잡는다.

**교훈:** 불변식 하나(왕복)로 모든 오류를 잡을 수 없다. 어떤 오류가 그 불변식을 통과하는지 먼저 생각한다.

#### 공액(conjugation) `R·q·R⁻¹`

**직관:** 기저를 바꾼 회전 = 원래 회전을 새 기저 변환으로 감싼 것. 쿼터니언에서는 벡터부에 R을 적용하는 것과 같아, 위치와 같은 재배치를 벡터부에 하고 `w`는 그대로 두면 된다.

**동작:** 기저 변환 행렬 R에 대해 `R·q_v·R⁻¹` 형태의 공액은 벡터부에 R을 적용하는 것과 동치이고, 스케일은 회전에 영향이 없다. 그래서 `mayaToRosRotation(q) = {q.x, −q.z, q.y, q.w}`다. 같은 원리로 URDF 조인트 `<origin>`(부모 대비 상대 변환 `child·parent⁻¹`)과 회전각(limit)은 공액 아래 불변이지만, `<axis>`처럼 "어느 벡터인가"를 고르는 값은 불변이 아니라 재배치해야 한다.

**예시:**
```cpp
Quat mayaToRosRotation(const Quat& maya) {
    return Quat{maya.x, -maya.z, maya.y, maya.w};   // 벡터부만 재배치, w 불변
}
```

**관련 코드:**
- `src/maro_transform/src/Convert.cpp:18-24` — 벡터부 재배치
- `tests/transform/test_convert.cpp:90-160` — 회전 변환 케이스
- `python/maroUrdfExport.py:60-87` — 공액 불변이 아닌 `<axis>` 재배치

**증거:**
- §5.1, §5.1.2, §10.6

**함정:** "회전은 공액으로 불변"을 "회전과 관련된 모든 것이 불변"으로 넓히면 `<axis>` 버그가 된다. 불변인 것은 변환 자체이고, 벡터 선택은 아니다.

**교훈:** 수학 정리의 적용 범위를 정확히 적는다. "어떤 객체에 대해" 불변인지가 핵심이다.

#### 사영(projection)

**직관:** 벡터를 다른 벡터 방향으로 투영한 길이. 쿼터니언의 벡터부를 관절 축에 사영하면 "그 축 둘레의 회전량"만 남는다.

**동작:** `mayaRotationToJoint(q, conv)`는 관절 축 `axis`를 `AxisConvention`에서 얻고 `sinHalf = q_v · axis`(내적)로 회전축 성분을 부호 있는 `sin(θ/2)`로 뽑는다. `cosHalf = clamp(q.w, −1, 1)`, 각도는 `2·atan2(sinHalf, cosHalf)`로 (−π, π]에서 복원. 축 보정이 다른 축을 가리키면 사영값이 0에 가까워 각도가 0이 된다 — 즉 "이 축의 회전"만 뽑는다.

**예시:**
```cpp
double mayaRotationToJoint(const Quat& maya, const AxisConvention& conv) {
    const Vec3 axis = axisVectorOf(conv);
    const double sinHalf = maya.x * axis.x + maya.y * axis.y + maya.z * axis.z;
    const double cosHalf = std::clamp(maya.w, -1.0, 1.0);
    return 2.0 * std::atan2(sinHalf, cosHalf);
}
```

**관련 코드:**
- `src/maro_transform/src/Convert.cpp:43-52` — 사영과 atan2
- `tests/transform/test_convert.cpp:160-241` — `|angle|>π` 케이스로 asin 구현 배제

**증거:**
- §5.1, §5.1.2

**함정:** `asin(sinHalf)`로 각을 복원하면 ±π/2 너머를 잃는다. `atan2`에 `cosHalf`를 함께 줘야 (−π, π] 전체가 복원된다.

**교훈:** 각도 복원은 항상 `atan2(sin, cos)`. `asin`·`acos` 하나로는 사분면을 잃는다.

#### 내적(dot)

**직관:** 두 벡터의 성분곱 합. 단위 벡터와의 내적은 그 방향 성분의 길이다 — 쿼터니언 벡터부와 관절 축의 내적이 `sin(θ/2)`가 된다.

**동작:** `sinHalf = q.x·a.x + q.y·a.y + q.z·a.z`. 단위 쿼터니언 `q = (axis·sin(θ/2), cos(θ/2))`에서 회전축이 관절 축과 같으면 내적이 정확히 `sin(θ/2)`, 수직이면 0, 반대면 `−sin(θ/2)`. 부호가 살아남으므로 회전 방향이 보존된다. SAT의 축 투영도 같은 내적이다.

**예시:**
```
q = (0, 0, sin(30°), cos(30°))  (Z축 60° 회전)
axis = (0, 0, 1)
sinHalf = 0·0 + 0·0 + sin(30°)·1 = 0.5  →  θ = 2·atan2(0.5, 0.866) = 60°
```

**관련 코드:**
- `src/maro_transform/src/Convert.cpp:48` — 내적 한 줄
- `src/maro_lidar/src/CollisionEngine.cpp:116-175` — SAT 투영의 내적

**증거:**
- §5.1, §5.1.2

**함정:** 정규화되지 않은 축과 내적하면 `sin(θ/2)`가 축 길이만큼 스케일돼 각도가 틀린다. `axisVectorOf`는 단위 벡터를 준다.

**교훈:** 내적을 "성분 추출"로 쓸 때는 기준 벡터가 단위임을 보장한다.

#### BVH(Bounding Volume Hierarchy)

**직관:** 프리미티브를 경계 상자 트리로 묶어 레이-교차 후보를 빠르게 좁히는 가속 구조. Embree가 `rtcCommitScene`에서 빌드하고, 레이 하나가 수만 삼각형이 아니라 트리 깊이만큼만 검사하게 한다.

**동작:** `ScanEngine`은 `rtcCommitGeometry → rtcAttachGeometry → rtcReleaseGeometry`(씬이 참조를 가짐) → `rtcCommitScene`(BVH 빌드) → 오류 확인 → 교체 순서로 씬을 만든다. Embree는 CPU SIMD(SSE/AVX) BVH 트래버설이며 TBB 없이(INTERNAL tasking) 빌드됐으므로 BVH 빌드는 단일 스레드이거나 Embree 내부 태스킹을 쓴다. 완성 전 씬이 `scene_`에 들어가지 않도록 "완성 후 교체" 규율을 지킨다.

**예시:**
```cpp
rtcCommitGeometry(geom);
rtcAttachGeometry(newScene, geom);
rtcReleaseGeometry(geom);           // 씬이 참조를 가짐
rtcCommitScene(newScene);           // BVH 빌드
if (rtcGetDeviceError(device) == RTC_ERROR_NONE) scene_ = newScene;   // 완성 후 교체
```

**관련 코드:**
- `src/maro_lidar/src/ScanEngine.cpp:70-80` — attach/commit 순서
- `src/maro_lidar/CMakeLists.txt` — TBB 부재 가드

**증거:**
- §5.2, §5.2.3

**함정:** 메쉬가 매 프레임 바뀌면 BVH를 매번 다시 빌드해야 한다. 스캔 비용보다 빌드 비용이 클 수 있어 `updateRate` 스로틀이 있다.

**교훈:** 가속 구조는 "빌드 비용 vs 질의 비용"의 거래다. 정적 씬에 유리하고 동적 씬은 갱신 빈도를 조절한다.

#### 구면 좌표

**직관:** 방향을 두 각도 — 수직각 V(위아래), 수평각 H(좌우) — 로 표현하는 것. LiDAR 레이 패턴은 채널(V)×샘플(H) 격자로 정의되므로 구면 좌표에서 단위 벡터로 바꿔야 레이를 쏜다.

**동작:** `computeRayDirections`는 각 (V, H) 쌍에 `(cosV·sinH, sinV, cosV·cosH)`를 계산한다 — Y-up 관례로 (0,0)이 로컬 +Z 정면, 양의 V가 +Y로 기울고, H는 +Z에서 +X 쪽으로 Y축 중심 회전. 각도 간격은 `LaserScan` 관례 `(max−min)/(N−1)`. 결과는 전부 단위 벡터이고 바깥 루프가 수직 채널, 안쪽이 수평 샘플이다.

**예시:**
```cpp
const double cosV = std::cos(vertical), sinV = std::sin(vertical);
dir = { cosV * std::sin(horizontal), sinV, cosV * std::cos(horizontal) };
// (V=0, H=0) → (0, 0, 1) 정면
```

**관련 코드:**
- `src/maro_lidar/src/RayPattern.cpp:18-40` — 변환
- `src/maro_lidar/include/maro_lidar/RayPattern.h:12-20` — 로컬 프레임 관례
- `tests/lidar/test_ray_pattern.cpp` — 단위 벡터·정면·기울기 검증

**증거:**
- §5.2, §5.2.2

**함정:** 수학 교과서의 구면 좌표는 Z-up(극각이 Z에서)이다. Y-up 관례로 바꾸지 않으면 "수직각"이 옆으로 도는 각이 된다.

**교훈:** 구면 좌표는 관례가 여럿이다. 어느 축이 극축인지 코드 주석에 벡터 식과 함께 적는다.

#### `(cosV·sinH, sinV, cosV·cosH)`

**직관:** 수직각 V, 수평각 H에서 Y-up 단위 방향 벡터를 만드는 식. `sinV`가 Y(위) 성분, 나머지 `cosV`를 H로 Z(정면)와 X(옆)에 나눈다.

**동작:** 길이는 `cos²V·sin²H + sin²V + cos²V·cos²H = cos²V + sin²V = 1`이라 항상 단위 벡터다. V=0, H=0이면 (0,0,1) 정면; V=90°면 (0,1,0) 위; H=90°면 (1,0,0) 오른쪽. 레이 패턴 테스트는 정확히 v×h개, 전부 단위, (0,0)→+Z, 양의 V→+Y를 단언한다.

**예시:**
```
V=0°,  H=0°   → (0, 0, 1)   정면
V=0°,  H=90°  → (1, 0, 0)   오른쪽
V=90°, H=임의 → (0, 1, 0)   위 (H 무관)
```

**관련 코드:**
- `src/maro_lidar/src/RayPattern.cpp:28-35` — 식
- `tests/lidar/test_ray_pattern.cpp` — 위 세 케이스

**증거:**
- §5.2, §5.2.2

**함정:** V=±90°에서 H가 무의미해진다(극점 특이). 수직 범위를 ±90° 미만으로 두면 문제없고, 실제 LiDAR도 그렇다.

**교훈:** 식 하나에도 "길이 1 증명"과 "특이점"을 주석으로 붙이면 테스트가 무엇을 확인해야 하는지 드러난다.

#### 11개 축

**직관:** 3D 삼각형-삼각형 SAT의 후보 분리축 개수 — 두 면의 법선 2개 + 변끼리의 외적 3×3=9개. 이 11개 중 하나라도 분리하면 교차하지 않는다.

**동작:** `trianglesIntersect`는 `nA = eA0×eA1`, `nB`, 그리고 `eA_i × eB_j`(i,j∈{0,1,2})를 축으로 두 삼각형 꼭짓점을 투영해 `[min,max]` 구간 겹침을 검사한다. 공면이면 11개 축이 전부 법선과 평행해져(투영 폭 0) 평면 내 분리를 못 구분하므로 2D SAT(각 변의 평면 내 법선 `cross(n, edge)` 6개)로 대체한다. 변×변 축은 법선 축으로는 안 보이는 "모서리끼리 비켜 가는" 분리를 잡는다.

**예시:**
```
축 목록: nA, nB,
         eA0×eB0, eA0×eB1, eA0×eB2,
         eA1×eB0, eA1×eB1, eA1×eB2,
         eA2×eB0, eA2×eB1, eA2×eB2      = 11
```

**관련 코드:**
- `src/maro_lidar/src/CollisionEngine.cpp:116-175` — 축 생성과 투영
- `tests/lidar/test_collision_engine.cpp:131-157` — 변×변 축으로만 분리되는 케이스

**증거:**
- §5.2, §5.2.4

**함정:** 변×변 축을 빼면 대부분의 테스트가 통과한다 — 그 축이 필요한 배치가 드물기 때문이다. 테스트는 그 배치를 일부러 만든다.

**교훈:** 정리가 요구하는 축을 전부 넣고, "이 축이 없으면 틀리는 입력"을 테스트에 둔다.

#### 퇴화 축(degenerate axis)

**직관:** 두 변이 평행해 외적이 0벡터가 되는 축. 길이가 0이라 투영이 무의미하므로 "분리 아님"으로 스킵한다.

**동작:** 각 외적 축에 대해 `길이² < eps²`면 건너뛴다. `eps = scale·1e-6`, `scale = sqrt(max 변 길이²)`로 입력 크기에 상대적이다. 퇴화 축을 "분리"로 잘못 판정하면 실제로 겹치는 삼각형이 비충돌이 되므로 보수적으로 "분리 아님"이다. 테스트 파일 머리주석이 코드에서 읽어 낸 이 규칙(scale, eps, 퇴화 축 처리, coplanar 조건)을 옮겨 적고 각 케이스가 그 규칙에서 손으로 유도한 기댓값을 쓴다.

**예시:**
```cpp
const Vec3d axis = cross(edgesA[i], edgesB[j]);
if (lengthSquared(axis) < eps * eps) continue;    // 퇴화 축: 분리 증거로 쓰지 않는다
```

**관련 코드:**
- `src/maro_lidar/src/CollisionEngine.cpp:120-135` — scale/eps와 퇴화 스킵
- `tests/lidar/test_collision_engine.cpp:9-27` — 규칙을 옮긴 머리주석
- `tests/lidar/test_collision_engine.cpp:158-180` — 공선 삼각형 케이스

**증거:**
- §5.2, §8.2, §8.2.2

**함정:** 퇴화 축을 정규화하려고 길이로 나누면 0 나눗셈 또는 NaN이 나와 이후 비교가 전부 false가 된다. 정규화 없이 길이²로 먼저 거른다.

**교훈:** 수치 기하에서 "0에 가까움"은 분기다. 그 분기의 안전한 기본값(여기서는 "분리 아님")을 정하고 주석에 적는다.

#### `axisDirectionFromPoints(a, b)`

**직관:** 두 점으로 관절 축의 방향을 정하는 함수 — `b − a`를 정규화한다. 사용자가 씬에서 두 로케이터를 찍으면 축 방향이 된다.

**동작:** 리밋 보정 세션이 사용자가 놓은 두 점을 받아 `(b − a).normal()`을 돌려준다. 두 점이 같으면 방향을 정의할 수 없으므로 `ValueError`. 결과는 `axisBasisEulerXYZ`로 넘어가 매니퓰레이터의 로컬 Z가 되고, `mayaDirectionToRos`로 ROS 축 벡터가 된다. `test_limit_calibration_pure.py`가 Maya 없이 이 순수 함수들을 검증한다.

**예시:**
```python
d = axisDirectionFromPoints(MVector(0, 0, 0), MVector(0, 10, 0))   # → (0, 1, 0)
axisDirectionFromPoints(p, p)    # ValueError: pointA and pointB must differ
```

**관련 코드:**
- `python/maroLimitCalibration.py:15-25` — 함수와 ValueError
- `tests/maya/test_limit_calibration_pure.py` — 순수 함수 테스트

**증거:**
- §7.10, §8.3.6

**함정:** 두 점이 "거의" 같으면(1e-12 차이) 정규화가 노이즈 방향을 준다. 같음 판정에 허용오차를 두거나 UI에서 최소 거리를 요구한다.

**교훈:** 입력이 정의역 밖이면 조용히 기본값을 주지 말고 예외로 알린다. 방향 없는 축은 나중에 더 이상한 증상이 된다.

#### 월드 업 참조

**직관:** 방향 벡터 하나로 기저를 만들 때 남는 자유도(Z 둘레 회전)를 "월드 업(+Y)을 가능한 한 로컬 Y에 가깝게"로 고정하는 규칙. 프레임마다 X/Y가 튀지 않게 한다.

**동작:** `axisBasisEulerXYZ(dir)`는 `reference = (0,1,0)`으로 `X = reference × Z`, `Y = Z × X`를 만든다. `dir`이 월드 업과 거의 평행하면(`|dir·up| > 임계`) 외적이 0에 가까워 기저가 무너지므로(짐벌 특이점) `reference = (1,0,0)` 월드 X로 바꾼다. 1자유도 계라 매니퓰레이터는 로컬 Z만 쓰므로 X/Y 선택은 표시 안정성만 좌우한다.

**예시:**
```python
reference = MVector(0, 1, 0)                 # 월드 업
if abs(z * reference) > 0.999:               # 평행 → 특이점
    reference = MVector(1, 0, 0)             # 월드 X로 대체
x = (reference ^ z).normal()
```

**관련 코드:**
- `python/maroLimitCalibration.py:27-60` — 참조 선택
- `tests/maya/test_limit_calibration_pure.py` — 로컬 Z 대조 테스트

**증거:**
- §7.10

**함정:** 임계값 근처(예: 0.9989→0.9991)에서 참조가 바뀌면 매니퓰레이터가 한 번 획 돈다. 축이 거의 수직인 로봇이면 히스테리시스를 두는 것이 낫다.

**교훈:** 특이점 회피는 "어디서 바꾸는가"를 정하는 일이다. 임계를 문서에 적고 실사용 각도 분포를 본다.

#### 무게중심 방향 판정

**직관:** QuickHull에서 새 면의 바깥 방향(정점 순서)을 정하는 기준으로 초기 사면체의 무게중심을 쓴다. 이 점은 껍질 안에 반드시 있으므로 "무게중심이 면 뒤쪽이면 바깥 방향"이 항상 옳다.

**동작:** `addFace(a, b, c)`는 법선 `(b−a)×(c−a)`가 무게중심을 향하면 두 정점을 바꿔 뒤집는다. horizon 변의 방향을 따지는 방법은 인접 면의 순서 규약에 의존해 오류가 나기 쉽지만, 내부 점 하나로 판정하면 국소 규약이 필요 없다. 초기 사면체가 극단점에서 만들어져 무게중심이 안정적이다.

**예시:**
```python
def addFace(a, b, c):
    n = cross(P[b] - P[a], P[c] - P[a])
    if dot(n, centroid - P[a]) > 0:        # 무게중심이 앞쪽 → 뒤집는다
        b, c = c, b; n = -n
    ...
```

**관련 코드:**
- `python/maroUrdfExport.py:1079-1100` — 무게중심과 addFace
- `tests/maya/test_urdf_export.py:1055-1070` — 결과 와인딩(부피 부호) 검증

**증거:**
- §7.14

**함정:** 무게중심을 "현재까지 껍질 정점의 평균"으로 갱신하면 점 분포가 치우칠 때 껍질 밖으로 나갈 수 있다. 사면체 무게중심으로 고정한다.

**교훈:** 방향 판정의 기준점은 "항상 안에 있음"이 증명되는 것을 고른다. 갱신하지 않는 편이 안전하다.

#### `visibilityChecks`

**직관:** QuickHull이 "이 점에서 이 면이 보이는가"를 물은 횟수. 성능 테스트가 벽시계 대신 이 수를 단언해, 머신 속도와 무관하게 이차식 회귀를 잡는다.

**동작:** `convexHull(points, stats)`에 dict를 주면 `visible()`이 호출될 때마다 `stats["visibilityChecks"]`를 올린다. 테스트는 2000점 볼록 입력에서 검사 횟수가 200000 미만(점당 100 미만)임을 단언한다. 순진 증분식은 점당 면 수만큼 검사해 O(n²)로 이 상한을 크게 넘는다. 느슨한 시간 임계값(F-217)은 이차식 회귀를 조용히 통과시켰다.

**예시:**
```python
_hullStats = {"visibilityChecks": 0}
convexHull(convexPoints2000, _hullStats)
assert _hullStats["visibilityChecks"] < 200000, _hullStats["visibilityChecks"]
```

**관련 코드:**
- `python/maroUrdfExport.py:1108-1112` — 카운트
- `tests/maya/test_urdf_export.py:1162-1180` — 상한 단언

**증거:**
- §7.14
- F-217

**함정:** 상한을 너무 넉넉히 잡으면(예: 10⁷) O(n²)도 통과한다. 상한은 "올바른 알고리즘의 실측 × 여유 2~3배"로 잡고 실측값을 출력해 둔다.

**교훈:** 성능 회귀 테스트는 알고리즘의 일 단위를 센다. 시간은 환경의 함수, 횟수는 알고리즘의 함수다.

#### −0 vs 0

**직관:** IEEE 부동소수점에서 −0.0 == 0.0이다. 부호가 뒤집히는 변환을 z=0 입력으로 테스트하면 `−z = −0`이 `0`과 같아 부호 오류를 못 잡는다.

**동작:** 초기 위치 변환 테스트들이 전부 z=0 입력을 써서 `(x,−z,y)`의 `−z` 부호가 틀려도 통과했다. 수정은 부호가 실제로 뒤집히는 축(Maya +Z→ROS −Y)에 0이 아닌 값을 넣는 케이스 `MayaForwardFlipsSignIntoRosY`·`RosLeftFlipsSignIntoMayaZ`를 추가한 것. 회전 테스트도 같은 구조로 `MayaRollFlipsSignIntoRosY`를 갖는다. 플랜 Task 3/4가 부호 뒤집기 변이로 테스트의 방어력을 증명했다.

**예시:**
```cpp
TEST(Position, MayaForwardFlipsSignIntoRosY) {
    // Maya +Z must land on ROS -Y. Earlier tests all used z == 0,
    // where -0 and 0 are indistinguishable.
    const maro::Vec3 maya{0.0, 0.0, 1.0};
    EXPECT_NEAR(maro::mayaToRosPosition(maya, unit).y, -1.0, 1e-9);
}
```

**관련 코드:**
- `tests/transform/test_convert.cpp:64-88` — 부호 축 케이스와 주석
- `tests/transform/test_convert.cpp:114-140` — 회전의 같은 케이스

**증거:**
- §8.2, §8.2.1

**함정:** "0을 넣으면 가장 단순하니까"가 함정이다. 0은 부호·스케일·순서 오류를 모두 숨긴다.

**교훈:** 테스트 입력은 "오류가 결과를 바꾸는 값"이어야 한다. 0·1·항등은 오류를 숨기는 값이다.

#### 반사(reflection, det=−1)

**직관:** 거울처럼 방향을 뒤집는 선형변환. 왕복 테스트는 반사를 잡지 못한다 — 반사 두 번은 항등이기 때문이다.

**동작:** `(x,y,z)→(x,z,y)`(y·z 맞바꿈, det=−1)는 반사인데 `rosToMaya(mayaToRos(x)) == x`를 통과한다. 그래서 단방향 부호 검사(Maya +Z→ROS −Y)가 필요하다. 테스트 주석은 "Task 2에서 위치 변환이 같은 함정에 빠졌던 것과 같은 구조"라고 적는다. 반사가 끼면 와인딩이 뒤집혀 STL 법선이 안쪽을 향하고 쿼터니언 규칙이 깨진다.

**예시:**
```
반사 M = ( 1 0 0 ; 0 0 1 ; 0 1 0 )   det = -1
M·M = I  → 왕복 테스트 통과 (틀렸는데도)
단방향: M·(0,0,1) = (0,1,0) ≠ 기대 (0,-1,0)  → 잡힘
```

**관련 코드:**
- `tests/transform/test_convert.cpp:64-88` — 단방향 부호 검사
- `tests/transform/test_convert.cpp:114-117` — "같은 함정" 주석

**증거:**
- §8.2, §8.2.1, §7.14

**함정:** 반사가 낀 변환은 위치만 보면 "그럴듯하게" 맞는다(축 하나 부호만 다름). 메쉬가 안팎이 뒤집힌 뒤에야 드러난다.

**교훈:** 대칭 변환 테스트에는 대칭을 깨는 케이스가 필요하다. 왕복은 필요조건이지 충분조건이 아니다.

#### 왕복 테스트의 한계

**직관:** `f⁻¹(f(x)) == x`는 f와 f⁻¹이 서로 역이라는 것만 증명한다. 둘이 같은 방식으로 틀리면(둘 다 반사, 둘 다 부호 오류) 통과한다.

**동작:** `RoundTripIsIdentity` 테스트는 랜덤 대량 입력으로 왕복을 확인하지만, 반사(det=−1)와 z=0 부호 오류를 통과시켰다. 그래서 `test_convert.cpp`는 왕복에 더해 (1) 단방향 절대값 케이스(`MayaUpBecomesRosUp`), (2) 부호가 뒤집히는 축 케이스, (3) 스케일 케이스, (4) `|angle|>π`로 `asin` 구현을 배제하는 케이스를 둔다. §8.2의 공통 정신 "틀린 구현이 통과하지 못하게 만드는 테스트 설계"의 첫 사례다.

**예시:**
```
왕복만:      f = 반사, f⁻¹ = 반사  → 통과 (오답)
왕복 + 단방향: f(0,0,1) == (0,-1,0)?  → 반사면 실패 → 잡힘
```

**관련 코드:**
- `tests/transform/test_convert.cpp:52-63` — 왕복
- `tests/transform/test_convert.cpp:29-40` — 단방향 절대값
- `tests/transform/test_convert.cpp:64-88` — 부호 축

**증거:**
- §8.2, §8.2.1

**함정:** 왕복 테스트는 작성하기 쉽고 통과하기 쉬워 "충분히 테스트했다"는 착각을 준다.

**교훈:** 불변식 테스트마다 "이 불변식을 통과하는 오답은 무엇인가"를 묻고, 그 오답을 잡는 케이스를 하나 더 둔다.

#### 닿기만 해도 충돌

**직관:** SAT 구현의 경계 시맨틱 — 변 하나나 꼭짓점 하나만 공유해도 "충돌"이다. 공통점이 있으면 어떤 축에서도 엄격한 분리(양의 간격)가 불가능하기 때문이다.

**동작:** 분리 판정은 "투영 구간이 `eps` 이상 떨어짐"이다. 두 삼각형이 점 하나를 공유하면 모든 축에서 구간이 그 점의 투영을 공유해 간격이 0 ≤ eps라 분리가 아니다. 테스트 `TrianglesSharingExactlyOneEdgeCollide`·`TrianglesSharingExactlyOneVertexCollide`가 이 시맨틱을 고정한다. 자기 충돌 검사에서 인접 삼각형(변 공유)을 걸러야 하는 이유이기도 하다.

**예시:**
```cpp
TEST(CollisionEngine, TrianglesSharingExactlyOneVertexCollide) {
    // 꼭짓점 하나만 공유 → 간격 0 → 엄격 분리 불가 → 충돌
    EXPECT_TRUE(trianglesIntersect(a, b));
}
```

**관련 코드:**
- `tests/lidar/test_collision_engine.cpp:207-240` — 변·꼭짓점 공유 케이스
- `src/maro_lidar/src/CollisionEngine.cpp:116-175` — `eps` 여유 비교

**증거:**
- §8.2, §8.2.2

**함정:** 메쉬 자기 충돌을 이 함수로 그대로 검사하면 이웃 삼각형이 전부 충돌로 나온다. 호출자가 인접 쌍을 제외해야 한다.

**교훈:** 경계 시맨틱("닿음"이 충돌인가)은 구현이 아니라 결정이다. 테스트로 고정하고 호출자에게 알린다.

#### X축 −90° 회전(det=+1)

**직관:** Maya Y-up→ROS Z-up 변환의 정체. X축을 고정하고 Y를 Z로, Z를 −Y로 보내는 90° 회전이며, 반사가 아니다.

**동작:** 회전 행렬 Rx(−90°)는 부호 관례에 따라 `(x,y,z)→(x,−z,y)`가 되며 det=+1. 위치·방향 벡터·쿼터니언 벡터부가 같은 규칙, `w` 불변, 스케일 `metersPerMayaUnit`은 위치에만. §9.2.1이 이 수식을 "확정"으로 기록하고, 플랜 Task 3/4가 부호 뒤집기·`asin` 치환 변이로 테스트가 이를 방어함을 증명했다. §10.6 규칙 표의 첫 줄이다.

**예시:**
```cpp
Vec3 mayaToRosPosition(const Vec3& m, const SceneUnit& u) {
    const double s = u.metersPerMayaUnit;
    return Vec3{m.x * s, -m.z * s, m.y * s};
}
```

**관련 코드:**
- `src/maro_transform/src/Convert.cpp:1-30` — 위치·회전 구현
- `src/maro_transform/include/maro_transform/Convert.h:5-11` — 주석
- `tests/transform/test_convert.cpp` — 변이 방어 케이스

**증거:**
- §5.1, §5.1.2, §9.2.1, §10.6

**함정:** "+90°인가 −90°인가"는 회전 방향 관례에 따라 이름이 바뀐다. 이름보다 `(x,−z,y)`라는 성분 식을 기준으로 삼는다.

**교훈:** 변환은 이름이 아니라 성분 식으로 고정한다. 식 하나가 문서·코드·테스트의 공통 기준이 된다.

#### 강체 프레임(rigid frame)

**직관:** 이동+회전만 있는 좌표 프레임 — 스케일·전단을 의도적으로 버린 것. URDF 링크 프레임과 TF 프레임은 강체여야 하므로 Maya 트랜스폼의 월드 행렬에서 강체 부분만 뽑는다.

**동작:** `_linkFrameWorldRigid(framePath)`는 축 로케이터의 부모 트랜스폼에서 이동과 회전만 읽어 강체 행렬을 만든다. 스케일·전단까지 담으면 이동·회전만 읽는 조인트 원점과 메쉬 정점이 어긋나 같은 강체 프레임을 공유하지 못한다. 메쉬 정점은 이 강체의 역행렬로 링크 프레임에 굽고, 조인트 `<origin>`은 두 강체의 상대 변환이다. 라이브 `/tf`도 같은 강체를 낸다.

**예시:**
```python
def _linkFrameWorldRigid(framePath):
    """링크 프레임의 강체 월드 행렬. 스케일과 전단은 의도적으로 버린다."""
    t = translation(framePath); r = rotation(framePath)
    return composeRigid(t, r)          # 스케일 1, 전단 0
```

**관련 코드:**
- `python/maroUrdfExport.py:397-425` — 강체 추출과 이유 주석
- `python/maroUrdfExport.py:565-580` — 강체 역행렬로 정점 굽기
- `src/maro_plugin/MaroPump.cpp:225-240` — 라이브 TF의 translation/rotation

**증거:**
- §10.6, §11.1

**함정:** 리그에 스케일이 들어간 트랜스폼(예: 미러용 −1)이 있으면 강체 추출이 회전을 잘못 읽는다. 내보내기 전에 스케일을 프리즈하거나 경고를 낸다.

**교훈:** 대상 포맷이 강체를 요구하면 입력에서 강체만 뽑는다. "버린 것"을 주석에 적어 왜 메쉬와 원점이 일치하는지 설명한다.
