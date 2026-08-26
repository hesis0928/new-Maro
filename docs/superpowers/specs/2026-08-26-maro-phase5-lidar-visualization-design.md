# Maro Phase 5 — LiDAR 설정 + 실시간 포인트클라우드 시각화 설계

## 1. 배경

원 로드맵(`wise-kindling-truffle.md` 계획, 2026-08-13 설계에서 파생)이 이미 Phase 5의
기술 방향을 상당히 구체적으로 잡아 뒀다: `maroLidar`(C++/ROS 쪽은 이미 병합됨,
Embree 레이캐스팅으로 메쉬를 스캔해 `sensor_msgs/PointCloud2`를 발행)를 UI에
노출하고, 스캔 결과를 Maya 뷰포트로 되읽어와 실시간으로 그린다.

그 로드맵이 작성된 이후 MaroUI 자체가 완전히 다시 설계됐다 — 축/capability
편집은 이제 네이티브 마킹메뉴(`dagMenuProc` 체이닝) + SONE(싱글 오브젝트 노드
에디터)/ONE(오브젝트 노드 에디터) 조합이고, Tech Diag 검사 터미널이 듀얼
뷰포트 양옆에 사이드 패널로 붙어 있다. 옛 로드맵이 가정한 "Phase 4의 평면
AxisPanel에 LiDAR 패널을 붙인다"는 더 이상 맞지 않는다. 이 설계는 옛 로드맵의
**무엇을 만들 것인가**(포인트클라우드 시각화, 실시간 프리뷰)는 유효한
출발점으로 유지하되, **어디에 어떻게 UI를 붙일 것인가**는 지금의 MaroUI 구조에
맞춰 새로 정했다.

이번 브레인스토밍에서 코드 대조로 재검증한 사실 세 가지 (모두 옛 로드맵의
전제를 뒷받침함):

- `MaroPump::onTimer`(`MaroPump.cpp:116-119`)는 `MTimerMessage` 콜백이라 항상
  메인 스레드에서 불린다. `collectLidarScans`도 그 안에서 불리므로, 스캔
  포인트는 이미 메인 스레드·Maya 월드 좌표로 존재한다 — Maya로 되읽어오는 것
  자체는 스레드 마샬링이 필요 없는 저비용 작업이다.
- 리포 전체에 `MPxDrawOverride`/`MHWRender`/`MDrawRegistry` 사용이 여전히
  전무하다 — 이 기능이 이 코드베이스 최초의 Viewport 2.0 드로우 오버라이드다.
- `maroRosProxy.py`의 격리(isolateSelect) 로직은 옛 로드맵이 가정한 것보다도
  더 확실하게 격리를 보장한다: Maya측 패널은 매 틱 `PROXY_GROUP`을 **명시적으로
  건너뛰고**(`maroRosProxy.py:185-188`) 나머지 모든 최상위 오브젝트를 넣고,
  ROS측 패널은 **오직 `PROXY_GROUP`만** 격리 목록에 넣는다
  (`maroRosProxy.py:335-336`). 즉 `maroRosProxy_grp` 아래 무엇을 두든 그것은
  ROS 뷰포트에만 보이고 Maya 뷰포트에는 자동으로 숨겨진다 — 새 코드 불필요.

## 2. 태스크 개요

| # | 태스크 | LiDAR 의존 여부 | 검증 방법 |
|---|---|---|---|
| 1 | `maroPointCloud` 노드 + `MPxDrawOverride` | 무관 (손으로 채운 버퍼로 증명) | 대화형 Maya 수동 |
| 2 | `MaroPump::collectLidarScans`에서 `scanLidarNode()` 추출 | — | 기존 LiDAR 테스트 그린 유지 |
| 3 | `maroCreateLidar` / `maroSnapshotLidarScan` 커맨드 | 있음, 브리지 독립적 | mayapy 배치 |
| 4 | 네이티브 마킹메뉴 "Maro LiDAR" 항목 + 설정 팝업 | 있음 | 대화형 Maya 수동 |
| 5 | 라이브 프리뷰(`visualize` 게이트, 디시메이션) | 있음 | 대화형 Maya 수동 |
| 6 | Tech Diag 센서 검증 후속(레인지/타겟메쉬 정합성) | 있음 | mayapy 배치 (순수 함수) |

Task 1(드로우 오버라이드)이 가장 큰 미지수라 최우선 — LiDAR와 완전히 무관하게
독립적으로 증명한다. Task 2-3은 브리지와 무관한 데이터 파이프라인을 mayapy로
완전히 테스트 가능한 상태로 만든다. Task 4가 실제 UI 진입점(가장 많은 이번
브레인스토밍 논의가 여기 집중됨)이고, Task 5가 마지막으로 남은 유일한
미지수(갱신 주기)를 닫는다. Task 6은 Task 4가 끝나 LiDAR가 UI에 노출된
**이후에만** 의미가 있으므로 맨 마지막.

## 3. `maroPointCloud` 노드 + 드로우 오버라이드 (Task 1)

새 파일 쌍 `src/maro_plugin/MaroPointCloudNode.h/.cpp`:

- **`maroPointCloud`** (`MPxLocatorNode`, `maroAxis`/`maroLidar`와 같은 패턴이지만
  **classification 문자열과 함께 등록**): `points`(`MFnTypedAttribute`,
  `MFnData::kPointArray`, **`setStorable(false)`** — 스캔 스냅샷을 `.ma`에
  저장하지 않는다), `pointSize`(double), `color`(float3), `enabled`(bool).
  `points`를 세팅하면 노드가 dirty해져 Viewport 2.0이 `prepareForDraw()`를
  다시 부른다.
- **`MaroPointCloudDrawOverride : MHWRender::MPxDrawOverride`**:
  `MPxDrawOverride(obj, NULL, isAlwaysDirty=false)`(null 콜백, dirty 기반).
  `prepareForDraw()`가 `points`를 `MUserData` 서브클래스로 읽어들인다.
  `addUIDrawables()`는 DG를 절대 건드리지 않는다(가장 흔한 Viewport 2.0 크래시
  원인). `beginDrawable()` → `setColor()`/`setPointSize()` →
  `drawManager.mesh(MUIDrawManager::kPoints, positions)` → `endDrawable()`로
  포인트 전체를 **한 번의 배치 호출**로 그린다. `isBounded()`/`boundingBox()`가
  실제 포인트에서 bbox를 계산한다(안 하면 오비트 중 프러스텀 컬링으로 사라져
  "안 그려짐"으로 보인다).
- 등록: `registerNode(..., MPxNode::kLocatorNode, &drawDbClassification)`
  (`drawDbClassification = "drawdb/geometry/maro/pointCloud"`) +
  `MDrawRegistry::registerDrawOverrideCreator(...)`. **언로드 순서**:
  `deregisterDrawOverrideCreator`가 `deregisterNode(maroPointCloud)`보다
  먼저 — 기존 역순 해제 블록에 새로운 종류의 순서 제약이 하나 추가되는 것이므로
  리뷰 시 명시적으로 짚는다.

**완료 기준(LiDAR 무관)**: `cmds.createNode("maroPointCloud")` +
`cmds.setAttr(...points...)`로 손으로 채운 점 몇 개 설정 → 그려짐 확인 → 창을
띄운 채 `cmds.unloadPlugin("maro")` → 크래시 없음.

**미검증으로 남겨 둘 것**: `isolateSelect`가 드로우 오버라이드로 그려지는
로케이터도 일반 DAG 오브젝트와 동일하게 걸러 주는지는 Task 4 시점에 실측
확인한다. 안 되면 `addUIDrawables()` 안에서
`MFrameContext::renderingDestination()`으로 패널명을 직접 검사해 우회한다.

## 4. 데이터 파이프라인 (Task 2-3)

- **`scanLidarNode()`** 추출(`src/maro_plugin/MaroLidarScan.h/.cpp`):
  ```
  MStatus scanLidarNode(const MObject& lidarNode, lidar::ScanEngine&,
                         const SceneUnit&, std::vector<Vec3>& outPointsMayaWorld);
  ```
  `MaroPump::collectLidarScans`와 새 커맨드 둘 다 이걸 부른다. 이미 병합·리뷰된
  코드에 대한 순수 추출이며 기존 `test_lidar_node.py`/`test_lidar_publish.py`로
  회귀를 커버한다.
- **`maroSnapshotLidarScan <lidarNode> [-target <maroPointCloud>]`**:
  `scanLidarNode()`로 자체 `ScanEngine`을 만들어 동기 스캔 후,
  `mayaToRosPosition`(발행 경로와 동일 함수)으로 변환해 `MDGModifier`로 대상의
  `points` 플러그에 undoable하게 반영. 브리지가 꺼져 있어도 동작 → mayapy
  배치 테스트 가능 → `MaroPump`/`MaroRosRuntime` 상태를 안 건드리므로 발행
  경로 회귀 위험 없음.
- **`maroCreateLidar [-name <str>]`**: undoable `MDGModifier::createNode`로
  `maroLidar` 생성. Task 4의 마킹메뉴 핸들러가 부른다.

## 5. UI 진입점: 네이티브 마킹메뉴 "Maro LiDAR" (Task 4)

### 5.1 메뉴 노출과 클릭 동작

"Maro LiDAR" 항목은 **오브젝트 종류와 무관하게 항상** 네이티브 마킹메뉴에
노출된다("Maro node editor"와 나란히). `maroDagMenu.py`의 검증된
`_nativeMenuSuppressed()`(ViewCube/순회 마킹메뉴/Modeling-Toolkit RMB-complete
억제)만 그대로 상속받고, 메쉬 셰이프 유무로 항목 자체를 숨기지는 않는다.

클릭 시 두 갈래로 나뉜다:

1. **이 오브젝트가 이미 어떤 `maroLidar`의 `targetMeshes[]`에 포함돼 있으면** —
   새로 만들지 않고 그 기존 `maroLidar`의 설정 팝업을 다시 연다(SONE이 이미
   바인딩된 축을 재클릭했을 때 재생성 대신 재오픈하는 것과 같은 원칙).
2. **그렇지 않으면** — 항상 새 `maroLidar` 노드를 생성한다. `cmds.createNode("maroLidar")`는
   로케이터형 DAG 셰이프라 Maya가 자동으로 새 트랜스폼을 만든다(축 생성과
   같은 관례, `maroDagMenu.py:515-521`이 이미 그 자동생성 트랜스폼을
   `listRelatives(parent=True)`로 찾아내는 패턴을 갖고 있다). **여기서부터
   축과 달라진다**: 축은 메시지 커넥션(`maroBindAxis`)으로만 바인딩되고
   물리적으로 부모-자식이 되지 않지만, LiDAR는 자신이 탑재된 오브젝트의 월드
   트랜스폼을 그대로 상속받아야 하므로 그 자동생성 트랜스폼을
   `cmds.parent(..., clickedObject)`로 클릭한 오브젝트의 **실제 DAG 자식**으로
   옮긴다. 오브젝트 종류와 무관하게(메쉬든 조인트든 로케이터든) 항상 성공한다.
   초기 `targetMeshes[0]`을 채우는 방식은 5.2 참고.

### 5.2 메쉬가 없는 오브젝트: placeholder 자동 생성

클릭한 오브젝트가 메쉬 셰이프를 갖고 있으면 그 메쉬를 초기 타겟으로 바로
등록한다. **갖고 있지 않으면**(조인트, 로케이터 등을 센서 거치대로 쓰려는
경우), 조건 불충족으로 막지 않고 자동으로 조건을 충족시킨다:

- 작은 **구(sphere)** 프리미티브를 생성한다.
- 이름: `<클릭한오브젝트이름>_maroLidarTarget`.
- 부모: 클릭한 오브젝트의 **자식**으로(오브젝트가 삭제되면 함께 삭제됨).
- 위치: 클릭한 오브젝트의 `cmds.exactWorldBoundingBox()`로 구한 월드
  바운딩박스 **상단(ymax) 중앙**. 바운딩박스가 점에 가까운 조인트/로케이터는
  거의 원점에 생긴다 — 계산 자체는 오브젝트 종류와 무관하게 일관되게
  적용되므로 이는 받아들여지는 동작이다.
- 생성 직후 **이 구를 Maya 선택 상태로 만든다**(`cmds.select`) — 사용자가
  바로 이어서 크기 조절/위치 이동 도구로 다듬을 수 있게.
- 이 구가 새 `maroLidar`의 초기 `targetMeshes[0]`이 된다.

### 5.3 설정 팝업

새 파일 `python/maroLidarPanel.py` — SONE과 같은 패턴(독립 최상위 `QWidget`,
노드의 전체 DAG 경로를 키로 삼는 `_OPEN_EDITORS` 싱글톤 딕셔너리, 플러그인
언로드 시 전부 닫는 `stop()`을 `maroMainWindow.teardown()`에 등록).

- `verticalSamples`/`verticalMinAngle`/`verticalMaxAngle`/`horizontalSamples`/
  `horizontalMinAngle`/`horizontalMaxAngle`/`rangeMin`/`rangeMax`/
  `updateRate`/`frameId`/`enabled` 편집 필드.
- `targetMeshes[]`를 보여주는 리스트 위젯 + "타겟 메쉬 추가"(현재 씬 선택을
  반영) / 개별 제거 버튼.
- **"Scan now" 버튼** — `maroSnapshotLidarScan` 호출(Task 3).
- (Task 5에서 추가) **"라이브 프리뷰"** 체크박스.
- ONE에는 참여하지 않는다 — LiDAR는 축이 아니므로 GSON 그리드에 낄 자리가
  없고, 팝업 하나로 완결된다.

포인트클라우드(`maroPointCloud`) 트랜스폼은 `maroRosProxy_grp` 아래 배치한다
— §1에서 재확인한 대로 ROS 뷰포트에만 자동으로 보이고 Maya 뷰포트에는 자동으로
숨겨진다.

## 6. 라이브 프리뷰 (Task 5)

새 `maroLidar.visualize` bool(또는 `maroSetLidarPreview <lidar> <0|1>`
커맨드)로 게이팅. 켜지면 `MaroPump::onTimer`가 이미 메인 스레드에서 들고 있는
스캔 포인트를 연결된 `maroPointCloud.points`에도 쓴다.

- **`cmds`/`MDGModifier` 없이 직접 plug write** — Phase 3에서 배운 교훈과
  같은 이유(idle 루프에서 `cmds`를 부르면 undo 큐가 매 틱 도배된다).
  `MFnPointArrayData` + `MPlug::setValue`로 raw write.
- **프리뷰 디시메이션** — `updateRate`로 이미 스로틀되지만, 스펙급 센서(6.5만
  레이)가 매 리드로우마다 큰 버퍼를 밀어넣지 않도록 프리뷰 포인트 상한 +
  스트라이드 샘플링을 추가한다.

## 7. Tech Diag 센서 검증 후속 (Task 6)

LiDAR가 UI에 노출된 뒤에야 의미 있는 검사 두 가지를 기존 Tech Diag Maya측
사이드 패널에 추가한다(기존 `checkLimitProximity`/`checkMeshCollisions`와
같은 패턴 — 순수 함수 + present-then-approve 버튼):

1. **타겟메쉬 없음** — `enabled`인 `maroLidar`가 `targetMeshes[]`를 하나도
   갖고 있지 않음(설정은 됐는데 스캔할 대상이 없는 상태).
2. **레이 수 초과** — `verticalSamples * horizontalSamples`가 기존
   `kMaxRaysPerScan` 상한을 넘어서는 구성(레이캐스팅 자체가 거부될 설정).

두 검사 모두 기존 `maroListAxisNodes`류 조회와 달리 `maroLidar` 노드를 직접
순회해야 하므로, 이 모듈이 필요로 하는 좁은 필드만 뽑는 새 순수 함수
(`sliceLidarTechRows` 등)를 `maroTechDiag.py`에 추가한다 — 다른 슬라이스가
따르는 "각 모듈이 자기 필드 상수를 독립적으로 선언한다" 관례를 그대로
따른다.

## 8. 테스트 / 수동 체크리스트

- Task 1, 4, 5는 실제 뷰포트 렌더링/마우스 제스처가 필요해 mayapy 배치로
  검증 불가능 — `docs/maro-main-ui-manual-checklist.md`에 새 절
  ("## 6. LiDAR 설정 + 시각화 (Phase 5)")을 추가해 대화형 Maya에서 사용자가
  직접 검증한다. 특히 창을 열고 ROS 뷰포트에 포인트클라우드가 실제로 그려지는
  중에 언로드하는 케이스는 렌더러가 소유한 오브젝트가 언로드 시점에 살아있는
  상태라 기존 언로드 테스트보다 위험도가 높다 — go/no-go 항목으로 명시한다.
- Task 2, 3, 6은 mayapy 배치로 완전히 테스트 가능(기존 `test_lidar_node.py`
  패턴, `test_axis_editor_commands.py`류의 커맨드 배치 테스트, Tech Diag의
  순수 함수 테스트 패턴).

## 9. 전역 제약

- `maroPointCloud.points`는 반드시 `setStorable(false)` — 스캔 스냅샷을
  `.ma`에 저장하지 않는다.
- `addUIDrawables()`에서 DG를 절대 건드리지 않는다.
- 드로우 오버라이드 언로드 순서: `deregisterDrawOverrideCreator`가
  `deregisterNode`보다 먼저.
- 라이브 프리뷰의 플러그 쓰기는 `cmds`/`MDGModifier`를 거치지 않는다(Phase 3
  idle-loop 교훈).
- placeholder 구 생성은 사용자가 명시적으로 메쉬 없는 오브젝트에 "Maro LiDAR"를
  클릭했을 때만 일어난다 — 그 외 어떤 흐름에서도 씬에 임의로 지오메트리를
  추가하지 않는다.
- Tech Diag 후속 검사는 기존 `boad`/`book` 디버깅 Diag와 완전히 독립적이며,
  Tech Diag 자신의 기존 present-then-approve 모델을 그대로 따른다(이번
  브레인스토밍에서 새로 정하지 않는다).
