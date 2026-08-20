# maroLidar 워킹 스켈레톤 설계 (2026-08-20)

## 1. 배경

`maroLidar`는 원래 `docs/superpowers/specs/2026-08-14-maro-troubleshooting-ecosystem-design.md`의 범위 제외 목록에 "S4 — 독립 서브시스템, 별도 스펙"으로만 표시돼 있었고, 지금까지 실제 스펙이 쓰인 적이 없다. 사용자가 브레인스토밍 중 가져온 4단계 제안(노드 설계 → Embree 레이트레이싱 → 멀티스레드 레이캐스팅 → PointCloud2 발행)을 실제 코드베이스, 업로드된 ROS 2 Jazzy 소스(`C:\dev\ros2_jazzy\src\ros2-sourcecode\`), Maya devkit(`C:\Users\ckd30\Projects\devkitBase\`)와 대조해 검증한 뒤 이 스펙을 작성했다.

**핵심 문제**: `sensor_msgs/PointCloud2`는 초당 수만~수백만 포인트를 나른다. Maya의 기존 DG `compute()` 경로(`maroAxis`류가 쓰는, 가벼운 스칼라 상태 전용)로 이 데이터를 흘리면 즉시 병목이 생긴다. 대량 데이터는 DG 평가 루프를 완전히 우회해 메모리를 직접 다뤄야 한다.

## 2. 범위: 워킹 스켈레톤 (Walking Skeleton)

이 4단계는 코어 커널 브레인스토밍 때의 "4개 기둥"과 다르다 — 각 단계가 독립적으로 가치있는 게 아니라 하나의 파이프라인을 이루는 층이라, Phase 1만 만들면 아무 것도 안 나오고 Phase 4 없이는 ROS 2로 아무 것도 안 나간다.

그래서 이 스펙은 **"제일 얇지만 처음부터 끝까지 이어지는" 버전**만 다룬다 — 성능/스케일은 신경 쓰지 않고, 씬 하나(메쉬 1개)를 대상으로 "노드 생성 → Embree에 메쉬 하나 올리기 → 싱글스레드로 레이 몇 개 쏘기 → PointCloud2 발행까지" RViz 등에서 실제로 점이 찍히는 걸 확인하는 것이 유일한 목표다.

**이렇게 자르는 이유**: 이 파이프라인에서 "직접 결과를 보지 않으면 틀렸는지도 모르는" 위험한 가정이 네 가지 있다 — 좌표계 변환(Maya Y-up ↔ ROS Z-up)이 맞는지, 레이 방향 벡터 계산 공식이 맞는지, Embree API를 제대로 쓰고 있는지(Scene commit이 유효한 BVH를 만드는지), PointCloud2 바이너리 패킹이 실제 ROS 2 도구에서 읽히는지. 이 네 가지를 최소 형태로 먼저 관통시켜 없앤 뒤에만, 멀티스레딩·더티체크·대량 렌더링 같은 "이미 검증된 파이프라인 위에 성능을 얹는" 안전한 작업을 층별로 진행한다(§7 범위 밖 참고, 각각 별도 스펙 대상).

## 3. 근거 조사 요약

### 3.1 실제 ROS 2 소스 확인 결과 (`C:\dev\ros2_jazzy\src\ros2-sourcecode\`)

- `sensor_msgs/msg/PointField.msg`: `x`,`y`,`z`,`intensity`,`rgb`,`rgba`가 "Common PointField names"로 명시. **`ring`은 이 소스 트리에 없다** — Velodyne/Ouster 드라이버가 각자 추가한 관례이지 순정 ROS 2엔 없다(이 체크아웃엔 Velodyne/Ouster 관련 코드가 전혀 없음).
- `urdfdom_headers/include/urdf_sensor/sensor.h`의 실제 `Ray` 클래스 멤버: `horizontal_samples`, `horizontal_resolution`, `horizontal_min_angle`, `horizontal_max_angle`, `vertical_samples`, `vertical_resolution`, `vertical_min_angle`, `vertical_max_angle`. 기반 `Sensor` 클래스: `name`, `update_rate`, `origin`, `parent_link_name`.
- 실제 Gazebo `<sensor type="gpu_ray">` 인스턴스(`ros2/demos/dummy_robot/dummy_robot_bringup/launch/single_rrbot.urdf:210-245`)가 위 헤더와 일치: `update_rate`(40), `<horizontal><samples>720</samples>`, `<min_angle>`/`<max_angle>`(±1.570796), `<range><min>0.10</min><max>30.0</max></range>`.
- `robot_state_publisher.cpp` 실소스: 발행되는 TF의 `frame_id`/`child_frame_id`는 URDF의 `parent`/`child` link 이름이 그대로 나간다 — LiDAR가 어디 붙어있는지 RViz가 알려면 `frame_id`가 필수.
- `ros2_control`/`controller_manager` 패키지는 이 체크아웃에 **전혀 없다** — `controlMode`(수동/ROS)에 대응하는 실제 ROS 2 용어는 존재하지 않는다.
- `JointState.msg`: `name`, `position`, `velocity`, `effort` — `position`이 실제 필드명(라디안 또는 미터).

### 3.2 Maya devkit 확인 결과 (`C:\Users\ckd30\Projects\devkitBase\`)

- `MPxLocatorNode::draw()`(직접 OpenGL)는 **Maya 2024부터 deprecated**. `MPxDrawOverride`/`MPxGeometryOverride`/`MPxSubSceneOverride`는 상속이 아니라 classification 문자열로 노드와 묶는 별도 클래스(`devkit/plug-ins/footPrintNode/footPrintNode.cpp`가 정확한 예시). 수만 개 렌더 아이템엔 devkit 문서가 `MPxSubSceneOverride`를 명시적으로 권장.
- "메쉬가 실제로 변형됐는지" 감지하는 Maya API는 **존재하지 않는다**. devkit 샘플도 노드 어트리뷰트로 직접 dirty 플래그를 만드는 패턴을 쓴다.
- devkit의 스레딩 문서 자체는 일부 모순되지만(`MPxGeometryOverride.h`가 인용하는 `MVertexBuffer`/`MIndexBuffer`의 스레드 안전성 문서가 실제 헤더엔 없음), **devkit 샘플 코드는 예외 없이** "메인 스레드에서 `MFnMesh` 데이터를 뽑은 뒤, 순수 배열만 워커 스레드로 넘기는" 패턴을 쓴다(`threadedBoundingBox.cpp`). 이 스펙은 이 패턴을 그대로 따른다.
- `MMeshIntersector`는 레이 교차 기능이 아예 없다(가장 가까운 점 찾기만 지원) — Embree 도입의 타당성이 오히려 더 명확해졌다.
- `MFnMesh::getTriangles(triangleCounts, triangleVertices)`가 삼각화된 인덱스 버퍼를 얻는 실제 API.

## 4. `maroLidar` 노드

### 4.1 기반 클래스와 등록

`MPxLocatorNode` 상속(`maroAxis`와 같은 패턴 — devkit의 legacy `draw()` 사용 안 함, 뷰포트 드로잉은 §7에서 별도 스펙으로 다룸). `MTypeId`는 기존 할당 구간(`0x00135100`~`0x00135105`) 다음 번호를 씀.

### 4.2 어트리뷰트 (실제 확인된 근거 기반)

| 어트리뷰트 | 타입 | 근거 |
|---|---|---|
| `verticalSamples` | int | `urdf_sensor/sensor.h`의 `vertical_samples` |
| `verticalMinAngle`/`verticalMaxAngle` | double, 라디안 | 같은 헤더의 `vertical_min_angle`/`vertical_max_angle` |
| `horizontalSamples` | int | 같은 헤더의 `horizontal_samples`, 실제 SDF `<horizontal><samples>`와 일치 |
| `horizontalMinAngle`/`horizontalMaxAngle` | double, 라디안 | 같은 헤더 + 실제 SDF `<min_angle>`/`<max_angle>` |
| `rangeMin`/`rangeMax` | double, 미터 | 실제 SDF `<range><min>/<max>` — 원안에 없던 필수 항목 |
| `updateRate` | double, Hz | `update_rate` — 실제 SDF/헤더 양쪽에서 확인. 원안의 `rpm`은 Velodyne 고유 용어라 이 참조 기준으론 확인 불가 |
| `frameId` | string | `robot_state_publisher.cpp` — TF/PointCloud2 헤더에 필수 |
| `targetMeshes` | message array | 스캔 대상 메쉬 바인딩(씬 전체 검색 방지). 워킹 스켈레톤은 인덱스 0 하나만 사용 |
| `enabled` | bool, 기본 true | `maroAxis.enabled`와 같은 패턴 |

바인딩은 `capabilityIn`이 이미 쓰는 방식과 동일하게 `connectAttr <mesh>.message <lidar>.targetMeshes[0]`로 직접 연결한다 — 새 바인딩 커맨드를 만들지 않는다(`maroBindAxis`와 달리, 이건 단순 message 연결이라 별도 검증/RemedyAction이 필요한 관계가 아니다).

### 4.3 기존 축 체계 변경사항

`MaroAxisNode::aOutValue`(long name `outValue`) → **`position`으로 rename**. 근거: `JointState.msg`의 실제 필드명이 `position`(라디안 또는 미터)인데, `outValue`는 이름만 봐선 의미가 불분명하다. 나머지 축/능력 노드 이름(`capabilityIn`/`Out`, `controlMode`, `maroAxis` 자체)은 그대로 유지한다 — `docs/superpowers/specs/2026-08-13-maya-ros2-axis-node-robotization-design.md`가 이미 "조인트보다 넓은 축+능력 합성" 개념을 의도적으로 설계했고(§3, 42-62행), `controlMode`에 대응하는 실제 ROS 2 용어는 위 3.1에서 확인했듯 존재하지 않는다 — 없는 표준을 억지로 갖다붙이지 않는다.

**주의**: `outValue`는 조사 결과 74곳(소스 3 + 테스트 40 + 문서 31)에서 참조된다(이전 브레인스토밍 세션의 인벤토리 조사 결과). 이 rename은 이번 워킹 스켈레톤과 별개로, **별도 태스크로 먼저 처리**하고 이 스펙이 그 위에 얹힌다(순서는 계획 단계에서 정한다).

## 5. Maya-free `maro_lidar` 라이브러리

`maro_ipc`/`maro_diag`/`maro_transform`과 같은 패턴 — Embree/레이캐스팅/PointCloud2 패킹 로직을 Maya 헤더 없이 순수 C++로 분리한다. 이렇게 하면 이 스펙에서 가장 위험한 네 가지 가정(§2) 중 세 가지(레이 방향 계산, Embree 사용법, PointCloud2 패킹)를 **gtest로 직접 검증**할 수 있다 — mayapy를 거칠 필요가 없다(이전 델타체크 스펙에서 mayapy 배치 모드가 특정 경로를 절대 못 도는 걸 발견한 것과 같은 이유로, Maya API 의존이 없는 로직은 처음부터 분리하는 게 이 프로젝트의 검증된 패턴이다).

- `src/maro_lidar/include/maro_lidar/RayPattern.h`: `verticalSamples`/`horizontalSamples`/각도 범위로부터 레이 방향 벡터 목록을 계산하는 순수 함수. Maya/Embree 둘 다 모름.
- `src/maro_lidar/include/maro_lidar/ScanEngine.h`: Embree `RTCScene`을 감싸는 클래스. 입력은 평범한 정점/인덱스 배열(`std::vector<float>`/`std::vector<uint32_t>` — `MFnMesh`가 아니라), 출력은 충돌 지점 배열. Embree Scene commit, `rtcIntersect1`(워킹 스켈레톤은 싱글스레드라 `rtcIntersect1M` 불필요 — §7에서 성능 레이어로 이월) 호출을 감싼다.
- `src/maro_lidar/include/maro_lidar/PointCloudPacking.h`: 충돌 지점 배열 + `frameId` → `sensor_msgs::msg::PointCloud2`의 실제 바이너리 레이아웃(`point_step`/`row_step`/`data`)으로 패킹하는 순수 함수. `x`/`y`/`z`/`intensity` 필드(§3.1에서 확인된 "common" 필드만 — `ring`은 워킹 스켈레톤 범위 밖).

이 세 헤더는 `maro_ipc`가 지금까지 지켜온 원칙과 같다: Maya 헤더 없음, `vcpkg.json`에 `embree3`(또는 사용 가능한 최신 포트명 — 계획 단계에서 `C:/src/vcpkg/ports/embree/`의 정확한 버전 확인) 추가.

## 6. `maro_plugin` 배선 (Maya 글루)

- **`MaroLidarNode`** (`src/maro_plugin/MaroLidarNode.h`/`.cpp`): §4의 어트리뷰트. `compute()`는 워킹 스켈레톤에선 값을 계산하지 않는다 — 실제 스캔은 아래 펌프가 주도한다(devkit이 확인해준 "메인 스레드는 캡처만" 원칙).
- **`MaroPump` 확장**: 기존 30Hz 발행 펌프에 LiDAR 캡처를 추가한다(또는 별도 저빈도 타이머 — 계획 단계에서 결정). 매 틱마다 `targetMeshes[0]`에 연결된 메쉬의 `MFnMesh::getPoints()`/`getTriangles()`를 **메인 스레드에서** 호출해 평범한 배열로 뽑고(devkit 패턴 그대로, 더티체크 없이 매번 — §7로 이월), `maro_lidar::ScanEngine`에 넘긴다. 레이캐스팅 자체는 워킹 스켈레톤에선 싱글스레드로 같은 틱 안에서 동기 실행(진짜 백그라운드 스레드 풀은 §7로 이월 — 파이프라인이 맞는지부터 확인하는 게 우선이므로, 스레딩은 나중에 추가해도 안전한 "레이어"다).
- **발행**: 기존 `MaroRosRuntime`과 같은 rclcpp 노드에서 `sensor_msgs::msg::PointCloud2` 퍼블리셔를 하나 추가한다(토픽 이름은 기존 `<robotName>/...` 관례를 따른다 — 계획 단계에서 정확한 이름 확정).

## 7. 범위 밖 (다음 레이어, 별도 스펙)

- 멀티스레드 레이캐스팅 풀, `rtcIntersect1M`로 전환
- 더티체크(트랜스폼만 변경 vs 버텍스 변형/스키닝) — Maya API가 없어 직접 설계 필요
- `MPxSubSceneOverride` 기반 대량 포인트 뷰포트 드로잉(devkit이 권장하는 방식, 워킹 스켈레톤은 그리기 자체를 생략하거나 최소한의 디버그 출력만)
- `targetMeshes` 다중 메쉬 지원(워킹 스켈레톤은 인덱스 0 하나)
- 실제 스펙 스케일(16~64채널, 1024~2048 해상도) — 워킹 스켈레톤은 검증 목적의 작은 값(예: 4채널) 사용
- `ring`/`intensity` 외 추가 PointCloud2 필드, 가우시안 노이즈 모델(`<noise>`, 실제 SDF에서 확인됨 — 나중에 추가 가치 있음)
- `rpm` 파라미터 병기 여부
- 라이다 로컬 프레임 + `world`→`frameId` TF: `maroLidar.frameId` 어트리뷰트는 노드에 있지만 발행 경로가 아직 읽지 않는다. 히트 좌표가 월드 좌표라 `PointCloud2.header.frame_id`는 항상 `"world"`다 — `frameId`를 실제로 쓰려면 히트를 라이다 로컬 프레임으로 옮기고 `world`→`frameId` TF를 함께 발행하는 층이 필요하다.

## 8. 테스트 전략

- `maro_lidar`(Maya-free): gtest로 `RayPattern`(알려진 채널/각도 입력 → 예상 방향 벡터 개수/범위 확인), `ScanEngine`(합성 삼각형 메쉬 하나에 레이를 쏴서 알려진 교차점이 나오는지), `PointCloudPacking`(알려진 포인트 배열 → 정확한 `point_step`/바이트 레이아웃이 나오는지) 각각 독립 검증. Maya/mayapy 불필요 — `maro_plugin_logic_tests`와 같은 패턴으로 별도 무-Maya 실행 파일.
- `maro_plugin` 배선: mayapy 종단 테스트로 `maroLidar` 노드 생성 + `targetMeshes` 연결 + 실제 발행까지 확인(가능하다면 — 이전 델타체크 스펙에서 `MPxThreadedDeviceNode`의 인바운드 배선이 배치 모드에서 막힌 전례가 있으므로, 계획 단계에서 이 펌프 경로가 mayapy에서 실제로 도는지 먼저 확인이 필요하다. `MaroPump`는 기존에 이미 mayapy 테스트로 검증되고 있으므로 `MaroCommandDeviceNode`와 달리 이 경로는 도달 가능할 가능성이 높다 — 확인 후 진행).

## 9. 전역 제약

- Maya-free 코드(`maro_lidar/`)는 Maya 헤더를 포함하지 않는다.
- `vcpkg.json`에 Embree 포트 추가(정확한 이름/버전은 계획 단계에서 `C:/src/vcpkg/ports/embree/`를 직접 확인).
- 메인 스레드(`MaroPump`)는 `MFnMesh` 데이터를 뽑아 순수 배열로 넘기는 역할만 한다 — 레이캐스팅/발행은 devkit이 확인해준 스레드 경계를 넘지 않는다(워킹 스켈레톤 단계에선 같은 틱 안 동기 실행이라도, `MFnMesh` 호출 자체는 항상 메인 스레드).
- PointCloud2 필드는 `x`/`y`/`z`/`intensity`만(§7, `ring` 등은 범위 밖).
- `outValue`→`position` rename은 별도 태스크로 먼저 처리(§4.3).
