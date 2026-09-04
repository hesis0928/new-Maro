# Maro Tech Diag — LiDAR 센서 검증 + 정밀 메쉬 충돌 — 설계

## 1. 배경

`docs/superpowers/specs/2026-08-26-maro-tech-diag-design.md` §8(범위 밖)이 명시적으로
다음 두 항목을 후속으로 예고해 두었다:

> - **센서/LiDAR 검증**(레인지 내 미탐지 장애물, LiDAR 레이캐스팅 정합성) —
>   `maroLidar`가 아직 UI에 노출되지 않은 상태(별도 로드맵 Phase 5, 미착수)라
>   이번 범위에서 제외. Phase 5 완료 후 이 문서의 후속으로 별도 브레인스토밍.
> - **폴리곤 단위 정밀 메쉬 충돌**(Embree 재사용) — v1은 AABB 겹침까지만.
>   필요해지면 별도 슬라이스로 정밀도를 높인다.

Phase 5(LiDAR 시각화 — `maroPointCloud` 노드 + `MPxDrawOverride`, `maroCreateLidar`/
`maroSnapshotLidarScan` 커맨드, 라이브 프리뷰)가 이 문서 이전에 이미 완료·머지됐다.
이 설계는 위 두 항목을 하나로 묶어 다룬다 — 둘 다 이 프로젝트가 이미 링크한
Embree 4를 재사용하고, Tech Diag의 같은 사이드 패널 파이프라인에 들어가기 때문이다.

**참고**: Tech Diag에는 이미 `checkLidarTargetMeshes`(타겟 메쉬 미연결 경고)와
`checkLidarRayCount`(레이 수 상한 초과 경고)가 있다(Phase 5 Task 6). 이 둘은
**정적 설정 검사**로, 실제 스캔을 돌리지 않는다. 이 설계가 다루는 두 항목은
**실제 스캔 결과가 필요한 동적 검사**로, 기존 두 검사와 겹치지 않는다.

## 2. 범위

### 이번 설계에 포함

1. **`scanLidarNode()` 다중 메쉬 지원** — 지금은 `targetMeshes[]`에 연결된 것 중
   첫 번째 메쉬만 스캔 대상이다(2026-08-20 워킹 스켈레톤 설계가 명시적으로 이월한
   제한, §7). 이후 Phase 5의 LiDAR 설정 팝업이 "타겟 메쉬 추가/제거" 리스트
   위젯을 이미 노출해서, 사용자는 여러 메쉬를 등록할 수 있어 보이지만 실제
   레이캐스팅은 첫 번째만 본다 — 이 간극을 이번에 고친다. 실제 ROS 발행 경로
   (`MaroPump::collectLidarScans`)에도 영향을 준다.
2. **새 조회 전용 커맨드 `maroQueryLidarScan`** — Tech Diag가 씬을 바꾸지 않고
   LiDAR를 동기 스캔해 상태/기하/히트점을 읽을 수 있는 유일한 경로.
3. **Tech Diag 동적 검사 4종** (Maya측 검사 파이프라인에 추가): 제로-히트 경고,
   범위 밖 지오메트리 경고, FOV 밖 지오메트리 경고, 히트점 range 경계 자체 검증.
4. **정밀 메쉬 충돌** — 새 `CollisionEngine`(Embree `rtcCollide` 래핑) + 새 조회
   커맨드 `maroCheckMeshCollision` + 기존 AABB 충돌 검사 뒤에 붙는 2단계 정밀
   재검사.

### 명시적 제외 (§7. 범위 밖 참고)

- FOV 밖 검사는 메쉬 AABB 중심 하나만 본다(부분적으로 FOV에 걸친 큰 메쉬는
  이번 범위 밖).
- 정밀 충돌은 폴리곤 메쉬 쌍에만 적용(NURBS 등은 AABB 폴백 유지).
- 애니메이션 전체 구간 검증(현재 프레임 하나만 봄) — 기존 Tech Diag와 동일한
  기존 한계, 이번에 안 바꿈.
- ROS측 검사(`_runRosSideChecks`)로의 확장 — 이번 4개 검사는 전부 Maya측.

## 3. `scanLidarNode()` 다중 메쉬 지원

### 3.1 현재 동작과 문제

`MaroLidarScan.cpp`의 `firstConnectedMesh()`가 `targetMeshes[]`를
`evaluateNumElements()` + `elementByPhysicalIndex()`로 순회하되 **첫 번째로
연결된 소스 노드 하나에서 멈춘다.** 결과적으로 두 번째 이후 타겟 메쉬는
`extractMeshBuffers()`에도, 레이캐스팅에도 전혀 참여하지 않는다.

### 3.2 수정: 버퍼 병합

`firstConnectedMesh()`를 **`allConnectedMeshes()`**로 바꾼다 — 같은 순회 방식
(빈 논리 인덱스를 만들어내는 `elementByLogicalIndex()` 함정을 피하는 기존 관례
그대로)으로 연결된 소스 노드를 전부 모은다.

각 메쉬에 대해 기존 `extractMeshBuffers()`를 그대로 호출해 정점/삼각형 버퍼를
얻은 뒤, 다음과 같이 병합한다:

- 정점 배열: 단순 이어붙이기.
- 삼각형 인덱스 배열: 메쉬 순서대로 이어붙이되, 두 번째 메쉬부터는 인덱스에
  이전까지 누적된 정점 개수만큼 오프셋을 더한다(메쉬 A가 정점 100개면 메쉬 B의
  인덱스는 전부 +100).

병합된 버퍼 하나를 기존과 동일하게 `engine.setMesh(vertices, indices)`에 한 번
전달한다 — `ScanEngine`/`castRay` 자체의 API/구현은 전혀 바뀌지 않는다. 레이
하나가 여러 타겟 메쉬 중 무엇에 맞든, 메쉬끼리 서로를 가리는 경우까지 "가장
가까운 히트"가 물리적으로 정확하게 나온다(합쳐진 지오메트리 하나에 레이캐스트
하는 것과 동일).

### 3.3 부분 실패 처리

연결된 메쉬 중 일부가 `extractMeshBuffers()`에서 실패하면(셰이프 삭제됨, 폴리곤이
아닌 지오메트리 등) — 전체 스캔을 실패시키지 않고 **그 메쉬만 건너뛰고 나머지로
계속 진행**한다. `targetMeshes[]`에 유효하지 않은 참조 하나가 섞였다고 나머지
정상 메쉬까지 스캔이 막히는 것은 과도한 실패 모드다. 연결된 메쉬가 하나도
없으면 기존과 동일하게 `kNoTargetMesh`, 연결은 있지만 **전부** 추출에 실패하면
`kMeshExtractFailed`(유효한 지오메트리가 결과적으로 하나도 없으므로).

### 3.4 순서 변경 — §4에서 필요한 선행 작업

지금 `scanLidarNode()`는 유효 월드 행렬/range/FOV 계산(§7의 offset 적용 포함)보다
**먼저** 타겟 메쉬 연결을 확인한다(현재 189~203행 순서). §4의 정적 기하 검사(범위
밖/FOV 밖)는 타겟 메쉬가 있든 없든 LiDAR 자체 설정만으로 계산 가능해야 하므로,
이 함수 내부 순서를 **"설정값 유효성 검사 → 유효 월드 행렬/range/FOV 계산 →
레이 수 상한 검사 → 타겟 메쉬 확인 → 실제 추출/캐스팅"** 순으로 바꾼다.
반환값의 의미(`LidarScanResult` 각 항목)는 그대로다 — 계산 순서만 바뀐다.
레이 수 상한 검사(`kRayCountExceeded`)를 행렬/range/FOV 계산 **뒤로** 옮기는
이유도 같다 — 레이 수가 넘쳐 실제 캐스팅을 건너뛰더라도, 그 사실이 range/FOV
자체를 무효로 만들지는 않으므로 §5의 검사 2/3은 이 경우에도 여전히 유효하게
동작해야 한다.

### 3.5 회귀 영향 범위

이 함수는 실제 ROS 발행 경로(`MaroPump::collectLidarScans`)와
`maroSnapshotLidarScan` 커맨드 양쪽에서 쓰인다. 타겟 메쉬가 1개뿐인 기존
사용 사례(지금까지 유일하게 테스트된 경로)는 "메쉬 1개 병합"이 항등 연산이므로
동작이 완전히 동일해야 한다 — 기존 `test_lidar_node.py`/`test_lidar_publish.py`가
그린으로 남는 것이 1차 회귀 검증이고, 여기에 메쉬 2개 이상(서로 가리는 배치
포함)인 새 테스트를 추가한다.

## 4. 새 조회 커맨드 `maroQueryLidarScan`

### 4.1 왜 새 커맨드가 필요한가

기존 `maroSnapshotLidarScan <lidarNode> <pointCloudNode>`는 **기존
`maroPointCloud` 노드가 있어야 하고**, `MDGModifier`로 그 노드의 `points`
플러그를 실제로(undoable하게) 바꾼다 — Tech Diag의 "검사는 씬을 바꾸지 않는다"
원칙과 정면으로 어긋난다. 새 검사 4종(§5)이 자동으로(사용자가 "검사 실행"을
누를 때마다) 돌면서 씬에 흔적을 남기면 안 된다.

### 4.2 계약

`maroQueryLidarScan <lidarNode>` — `MPxCommand`, **쿼리 전용**
(`MDGModifier` 없음, `isUndoable() == false`). `scanLidarNode()`를
`MaroSnapshotLidarScanCommand`와 공유하되(로직 중복 없음), 자체 `ScanEngine`
인스턴스를 써서 브리지/`MaroPump` 상태와 완전히 독립적으로 동작한다(기존
`maroSnapshotLidarScan`과 같은 원칙).

돌려주는 정보(정확한 필드 배치·순서는 계획 단계에서 이 코드베이스의 기존
"이름 붙은 상수 + flat array" 관례(`AXIS_FIELDS`/`CAPABILITY_FIELDS`류)를 따라
확정한다):

- 스캔 상태 코드(`kOk`/`kNoTargetMesh`/`kMeshExtractFailed`/`kInvalidConfig`/
  `kRayCountExceeded`에 대응하는 정수 또는 문자열).
- 이미 Maya 단위로 환산된 `rangeMin`/`rangeMax`(§3.4의 순서 변경 덕분에
  `kNoTargetMesh`여도 계산 가능). **여기서 "Maya 단위"는 항상 Maya의
  내부 단위(센티미터, `MDistance::internalUnit()`)를 말하며, 씬의 현재 UI
  선형 단위(사용자가 `cmds.currentUnit(linear=...)`로 바꿀 수 있는 값,
  기본은 cm이 아닐 수 있다)와는 다르다.** `effectiveWorldMatrix`도 마찬가지로
  항상 내부 단위 기준이다. 이 데이터를 `cmds.exactWorldBoundingBox()`처럼
  **UI 단위로 값을 돌려주는 API**의 결과와 비교하는 코드는 반드시 먼저
  단위를 맞춰야 한다 -- 안 그러면 씬이 cm이 아닌 단위(예: 미터)로
  작성됐을 때 100배 어긋난다(최종 리뷰 Critical-1, §5 구현에서 실제로
  이 실수가 있었다).
- 수직/수평 FOV 경계 4개, 라디안 그대로(도 단위 변환 없음).
- LiDAR의 **유효 월드 행렬**(마운트 트랜스폼 + `offsetTranslate`/`offsetRotate`
  까지 반영된, `scanLidarNode`가 실제 레이 원점/방향 계산에 쓰는 바로 그 행렬)
  16개 값.
- 히트 포인트 개수 + 각 점의 Maya 월드 좌표(x,y,z 반복).

이 설계에서 유효 월드 행렬/range/FOV를 Python이 다시 유도하지 않고 커맨드가
그대로 돌려주는 이유: 이 프로젝트는 지금까지 좌표/단위 변환 공식을 두 곳에서
따로 구현했다가 어긋난 사례(URDF 내보내기의 `axisVectorForConvention` Critical
버그 등)를 여러 번 겪었다. Python은 `maya.api.OpenMaya`(`om2.MMatrix`)로 받은
행렬의 역행렬만 취해 순수 선형대수만 하면 되므로, 좌표 변환 공식 자체를
Python 쪽에서 다시 도출할 필요가 없다.

## 5. Tech Diag 동적 검사 4종 (Maya측)

**범위**: `targetMeshes[]`에 **이미 연결된** 메쉬만 대상(§2 참고 — 씬의 아무
메쉬나 다 훑지 않음).

`enabled`인 각 `maroLidar`에 대해 `maroQueryLidarScan`을 한 번 호출하고, 연결된
각 타겟 메쉬의 월드 AABB(`cmds.exactWorldBoundingBox`, 기존 메쉬 충돌 검사와
같은 API)를 가져온다. **주의**: `maroQueryLidarScan`이 돌려주는 `rangeMax`/
`effectiveWorldMatrix`는 §4.2에서 밝힌 대로 항상 Maya 내부 단위(센티미터)인
반면 `cmds.exactWorldBoundingBox()`는 씬의 현재 UI 선형 단위로 값을 준다 --
이 둘을 같은 좌표계에서 비교하려면(검사 2/3이 하는 일이 정확히 이것이다)
AABB 쪽을 내부 단위(cm)로 먼저 변환해야 한다. 이 변환을 빠뜨리면 cm이 아닌
단위로 작성된 씬(미터 등)에서 검사 2/3이 100배 어긋난 값을 비교하게 된다.

| # | 검사 | 조건 | 비고 |
|---|---|---|---|
| 1 | 제로-히트 경고 | 상태 `kOk` + 연결된 메쉬 있음 + 히트점 0개 | `kNoTargetMesh`/`kMeshExtractFailed`/`kInvalidConfig`일 땐 원인이 이미 다른 방식으로 드러나므로(기존 검사 또는 아래 2/3번) 이 경고는 안 띄운다 |
| 2 | 범위 밖 지오메트리 경고 | 메쉬 AABB에서 LiDAR 유효 원점까지의 최근접점 거리(박스-점 최단거리, 표준 클램프 공식) > `rangeMax` | 스캔을 안 돌려도 판정 가능한 순수 기하 검사 |
| 3 | FOV 밖 지오메트리 경고 | 메쉬 AABB 중심을 유효 월드 행렬의 역행렬로 로컬 좌표로 옮긴 뒤 `vertical = asin(clamp(local.y / \|local\|, -1, 1))`, `horizontal = atan2(local.x, local.z)`(`RayPattern.cpp`와 같은 각도 규약)가 `[verticalMinAngle, verticalMaxAngle]` 또는 `[horizontalMinAngle, horizontalMaxAngle]` 밖 | 박스 중심 하나만 보는 근사(§2의 알려진 한계) |
| 4 | 히트점 range 경계 자체 검증 | 상태 `kOk`인 히트점 중 유효 원점까지 거리가 `[rangeMin, rangeMax]`(쿼리 커맨드가 이미 Maya 단위로 환산해 돌려준 값) 밖인 것이 하나라도 있음 | Embree의 `castRay`가 범위 밖 충돌을 이미 무시하므로 정상 상황에선 항상 통과해야 함 — 통과하지 않으면 그 자체가 회귀 신호(방어적 검사) |

**빈 씬**: `cmds.ls(type="maroLidar")`가 비면 4개 검사 모두 findings 없이 조용히
통과(기존 `checkLidarTargetMeshes`/`checkLidarRayCount`와 동일).

**통합 위치**: `_runMayaSideChecks()`에 새 순수 함수
(`checkLidarZeroHits`/`checkLidarOutOfRange`/`checkLidarOutOfFov`/
`checkLidarHitBoundsConsistency`)로 추가 — "미리 모은 데이터만 보는 순수 함수 +
Maya를 부르는 헬퍼가 그 데이터를 모은다"는 기존 관례 그대로.

## 6. 정밀 메쉬 충돌

### 6.1 `CollisionEngine`

새 클래스 `maro::lidar::CollisionEngine`(`ScanEngine`과 같은 `maro_lidar`
모듈 — 이미 Embree를 링크하고 있어 새 빌드 타겟 불필요):

```cpp
class CollisionEngine {
public:
    CollisionEngine();
    ~CollisionEngine();
    // 두 지오메트리를 각각 별도 RTCScene으로 올린다. 실패 시 false.
    bool setMeshes(const std::vector<float>& verticesA, const std::vector<std::uint32_t>& indicesA,
                   const std::vector<float>& verticesB, const std::vector<std::uint32_t>& indicesB);
    // rtcCollide를 호출하고, 콜백에서 실제 교차 삼각형 쌍이 하나라도 나오면 true.
    bool hasCollision() const;
private:
    RTCDevice device_ = nullptr;   // 두 씬은 같은 디바이스에 있어야 한다(계획 단계에서
                                    // rtcCollide의 정확한 전제조건을 devkit/문서로 재확인 —
                                    // 구현 리스크로 기록해 둔다).
    RTCScene sceneA_ = nullptr;
    RTCScene sceneB_ = nullptr;
};
```

### 6.2 메쉬 버퍼 추출 공유

`MaroLidarScan.cpp`의 익명 네임스페이스 안에 있는 `extractMeshBuffers()`(트랜스폼에
셰이프가 여럿인 경우, intermediate object 제외 등 이미 하드닝된 로직, 최종 리뷰
C-1에서 실측으로 발견된 함정까지 반영된 코드)를 공개 헤더로 옮겨 새 커맨드와
공유한다 — 같은 "메쉬 → 삼각형 버퍼" 문제를 두 번째로 다시 풀지 않는다.

### 6.3 새 커맨드

`maroCheckMeshCollision <meshA> <meshB>` — 쿼리 전용(`MDGModifier` 없음). 두
메쉬를 각각 추출해 `CollisionEngine`에 넣고 `setResult(bool)`로 실제 교차
여부만 돌려준다. 둘 중 하나라도 `extractMeshBuffers()`가 실패하면(폴리곤
메쉬가 아님) 에러가 아니라 "판정 불가"를 구분해서 돌려준다(예: 별도 상태 코드
또는 예외 — 계획 단계에서 확정, 호출부인 §6.4가 이 경우를 AABB 폴백으로
처리해야 하므로 명확히 구분 가능해야 한다).

### 6.4 Tech Diag 통합 — 2단계 파이프라인

기존 `checkMeshCollisions`/`adjacentMeshPairs`/`filterAdjacentMeshCollisions`는
변경 없이 그대로 두고, 뒤에 한 단계를 추가한다:

1. 기존 AABB 겹침으로 후보 쌍을 거른다(빠른 1차 필터, 변경 없음).
2. 인접(부모-자식) 쌍 필터링도 기존 그대로.
3. **새 단계**: 살아남은 각 후보 쌍에 대해 `maroCheckMeshCollision`을 호출한다.
   - 실제 교차가 **확인된** 쌍만 최종 findings에 남긴다.
   - 두 메쉬 중 하나라도 폴리곤 메쉬가 아니라 판정 불가면, 정밀 검사를
     건너뛰고 **기존 AABB 결과를 그대로 유지**하되 메시지에 "(정밀 확인 불가,
     바운딩박스 겹침만 확인됨)"을 덧붙인다 — 크래시도 무시도 아닌 완전한
     열화(이 프로젝트의 견고성 원칙 3).

**효과**: AABB는 겹치지만 실제 폴리곤은 안 닿는 흔한 오탐(여유 있는 바운딩박스가
스치듯 겹치지만 실제 지오메트리는 안 닿는 경우)이 사라진다 — 경고 개수는
줄고, 남는 경고는 전부 확인된 폴리곤 교차이거나 명시적으로 "정밀 확인 불가"로
표시된다.

## 7. 테스트 전략

기존 3단계 관례 그대로:

- **순수 함수**: `checkLidarZeroHits`/`checkLidarOutOfRange`/`checkLidarOutOfFov`/
  `checkLidarHitBoundsConsistency`, 다중 메쉬 버퍼 병합 로직 — mayapy 불필요한
  부분은 Python 단위 테스트, Maya 필요한 부분은 mayapy 배치.
- **C++ 계약 테스트**: `scanLidarNode()`의 다중 메쉬 회귀(메쉬 2개, 서로 가리는
  배치에서 nearest-hit이 물리적으로 맞는지), `CollisionEngine::hasCollision()`의
  알려진 교차/비교차 케이스(mayapy로 알려진 두 큐브 쌍 — 확실히 겹침 / AABB만
  겹치고 실제로는 안 닿음 / 완전히 분리).
- **통합**: `tests/maya/test_tech_diag.py`에 새 검사 4종 + 정밀 충돌 2단계
  파이프라인 케이스 추가. `tests/maya/test_lidar_node.py`/`test_lidar_publish.py`가
  다중 메쉬 수정 이후에도 그린으로 남는지가 1차 회귀 검증.
- 사이드 패널 버튼 클릭 자체(기존과 동일)는 `docs/maro-main-ui-manual-checklist.md`의
  기존 "Tech Diag 검사" 절에 새 케이스를 추가하는 방식으로 대화형 수동 확인.

## 8. 에러 처리 원칙

기존 Tech Diag 원칙 3(실패는 크래시도 무시도 아닌 비활성화) 그대로:

- 상태별 스킵 범위는 균일하지 않다 — 검사 2/3(범위 밖/FOV 밖)은 실제 스캔
  결과가 아니라 LiDAR 자체 기하(유효 월드 행렬/range/FOV, §3.4의 순서 변경
  덕분에 타겟 메쉬 추출 성공 여부와 무관하게 계산됨)와 타겟 메쉬 AABB만
  있으면 되고, 검사 1/4(제로-히트/히트점 범위 검증)만 실제 히트점이 필요하다:
  - `kInvalidConfig`(각도/range 자체가 무효): 행렬/range/FOV 자체를 계산할 수
    없으므로 4개 검사 **전부** findings 없이 스킵.
  - `kMeshExtractFailed`(연결된 메쉬는 있으나 전부 추출 실패, §3.3) 또는
    `kRayCountExceeded`(레이 수 상한 초과로 실제 캐스팅 자체를 건너뜀):
    두 경우 다 행렬/range/FOV는 여전히 유효하게 계산되므로 검사 2/3은
    정상 수행하고, 검사 1/4만 스킵(히트점 자체가 없음).
  - `kNoTargetMesh`: 검사 4는 `status == "kOk"`만 보므로 자연스럽게
    findings가 비고, 검사 1(제로-히트)은 `targetMeshCount == 0` 게이트로
    걸러진다. **검사 2/3은 다르다** — 실제 구현(`_LIDAR_GEOMETRY_VALID_STATUSES`
    튜플, `("kOk", "kMeshExtractFailed", "kRayCountExceeded")`)이
    `kNoTargetMesh`를 이 튜플에서 의도적으로 제외해 두 검사 모두 명시적으로
    스킵한다 — 연결된 메쉬가 없으니 `targetMeshBoxesByLidar`를 순회해도
    항목이 없어 어차피 결과는 같겠지만(빈 순회), 실제 코드는 "순회할 게
    없어서 자연히 비는 것"이 아니라 상태값 자체로 명시적으로 걸러낸다.
    (이 문단은 원래 "스킵이 아니라 자연스럽게 findings가 비는 것"이라고
    적었는데, 그건 검사 1/4에만 맞는 설명이었다 — 최종 리뷰가 지적한
    스펙-코드 드리프트를 여기서 바로잡는다.)
  이 스킵/공백은 findings 리스트가 비는 것으로만 나타나며, `_CheckSidePanel`의
  "검사 실패" 경로(예외 발생 시 "검사 실패 -- 스크립트 에디터 참조")와는
  다르다 — 이 둘을 같은 화면으로 절대 섞지 않는다는 기존 원칙 그대로.
- 정밀 충돌 커맨드가 예외를 던지면(Embree 초기화 실패 등) 그 쌍은 AABB 결과로
  폴백한다(§6.4에 이미 명시).

## 9. 전역 제약

- 빌드는 항상 `--config Release`, `ctest --test-dir out/build -C Release
  --output-on-failure` 전부 통과.
- 새 C++ 코드는 기존 에러 경계 규율(`ScopedCommandContext`, `try/catch`,
  `BoadMaro::error` + `onfix::capture`) 그대로 따른다.
- 새 쿼리 커맨드 2개(`maroQueryLidarScan`, `maroCheckMeshCollision`) 모두
  `MDGModifier` 없음, `isUndoable() == false`.
- Tech Diag 원칙("검사는 씬을 바꾸지 않는다", "이력 저장 없음") 그대로 유지 —
  새 검사도 전부 매번 재계산, 결과 저장/추적 없음.
- 새 `.py`는 `setStyleSheet()`를 호출하지 않는다(기존 전 파일 공통 규율).

## 10. 범위 밖 (알려진 한계, 지금 손대지 않음)

- FOV 밖 검사는 메쉬 AABB **중심** 하나만 본다 — 큰 메쉬가 일부만 FOV에 걸쳐
  있으면 "안 걸림"으로 오판할 수 있다.
- FOV 밖 검사(`checkLidarOutOfFov`)는 `atan2()`가 돌려주는 `(-π, π]` 범위의
  각도를 `horizontalMinAngle`/`horizontalMaxAngle` 경계와 각도 랩(wrap)
  정규화 없이 그대로 비교한다. 경계가 `-π..π` 안에 들어오는 보통의 설정
  (이 프로젝트가 배포하는 기본값 포함)에서는 문제가 없지만, 사용자가
  전체 360도 또는 `-π..π` 경계를 넘나드는(wrap-spanning) FOV를 설정하면
  (`RayPattern.cpp`의 레이 생성 자체는 이런 설정을 지원한다) 실제로는
  FOV 안에 있는 타겟이 각도 랩 때문에 밖으로 오판돼 스퓨리어스(허위)
  경고가 날 수 있다. 지금 범위 밖 — 필요해지면 별도로 다룬다.
- 정밀 충돌은 폴리곤 메쉬 쌍에만 적용된다(NURBS 등은 AABB 폴백 유지).
- 여전히 씬의 한 "순간"만 검사한다 — 애니메이션 전체 구간에 대한 검증은
  범위 밖(기존 Tech Diag와 동일한 기존 한계).
- ROS측 검사(`_runRosSideChecks`)로의 확장은 하지 않는다 — 이번 4개 검사는
  전부 Maya측(브리지 없이 동작 가능해야 하므로).
- 이 설계가 `maro_lidar` 모듈에 LiDAR와 무관한 `CollisionEngine`을 추가하면서
  모듈 이름이 내용을 완전히 설명하지 못하게 된다. 이름 변경/재구성은 이번
  범위 밖(관련 없는 리팩터를 끼워 넣지 않는다는 원칙) — 필요해지면 별도로
  다룬다.
