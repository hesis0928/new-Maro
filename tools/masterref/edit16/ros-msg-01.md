<!-- ros-msg-01 ROS 2 › 메시지·토픽·QoS (26개) 2026-09-17 -->

#### ROS 2 Jazzy

**직관:** 2024년 ROS 2 LTS 배포판. Maro가 링크하는 ROS 2 버전이며, 이 프로젝트에서는 바이너리 배포판이 아니라 **같은 MSVC로 소스 빌드한** 트리(`C:/dev/ros2_jazzy/install`, 최소 144패키지)를 쓴다.

**동작:** 플러그인 CMake가 소스 빌드 install 트리의 include·lib를 절대 경로로 잡아 `rclcpp`·`sensor_msgs`·`tf2_msgs` 등 14개 `.lib`를 링크하고, 런타임 DLL은 스테이징 폴더로 복사해 `.mod`가 PATH에 붙인다. 실측으로 이 머신의 영구 PATH에는 `C:/dev/ros2/bin`(Jazzy 20241223 바이너리 배포판)이 앞에 있어, PATH 선행 조치 없이는 스테이징 사본이 아니라 바이너리판 DLL이 로드된다는 것이 `GetModuleFileNameW`로 확인됐다.

**예시:**
```
소스 빌드:   C:/dev/ros2_jazzy/install   (MSVC 동일, Maro가 링크)
바이너리판:  C:/dev/ros2/bin             (영구 PATH 선행 — 섞이면 위험)
```

**관련 코드:**
- `src/maro_plugin/CMakeLists.txt` — ROS 2 install 트리 include/lib 절대 경로
- `tests/peer/maro_test_peer.cpp` — 같은 트리로 빌드하는 상대역
- `python/maroTechDiag.py:542-575` — 로드된 DLL 경로를 보여 주는 진단

**증거:**
- §1.1, §3.6

**함정:** 소스 빌드판과 바이너리 배포판은 같은 "Jazzy"라도 컴파일러·CRT·DDS 빌드가 달라 DLL이 섞이면 링크는 되고 런타임에 죽는다. 어느 사본이 로드됐는지는 진단으로 실측한다.

**교훈:** 배포판 이름은 호환성을 보장하지 않는다. "어떤 컴파일러로 누가 빌드했는가"까지가 버전이다.

#### CARLA

**직관:** 자율주행용 외부 시뮬레이터. Gazebo와 함께 "Maya에서 내보내 외부에서 돌리는" 방식의 대표이며, Maro가 **택하지 않은** 길을 설명할 때 등장한다.

**동작:** CARLA·Gazebo 파이프라인은 씬을 URDF/SDF로 내보내고 시뮬레이터가 물리를 돈다. Maro는 반대로 로봇이 Maya 씬 안에서 살며 디포머·스키닝·키프레임이 그대로 구동원이고, ROS 2는 같은 프로세스에 링크된 rclcpp로 실시간 연결된다. URDF 내보내기는 RViz·`robot_state_publisher` 검증용이지 시뮬레이터 이전용이 아니다.

**예시:**
```
외부 시뮬레이터 방식: Maya → URDF/SDF export → Gazebo/CARLA가 물리·센서
Maro 방식:            Maya 씬이 곧 로봇 → maro.mll 안 rclcpp → /joint_states, /tf, /points
```

**관련 코드:**
- `README.md:4-5` — "외부 시뮬레이터(Gazebo, CARLA)와 달리 로봇은 전적으로 Maya 씬 안에서 산다"
- `python/maroUrdfExport.py:913-935` — 검증용 URDF 내보내기

**증거:**
- §1.2

**함정:** "왜 Gazebo로 안 보내나"라는 질문에 답이 없으면 설계가 흔들린다. 답은 애니메이터의 리깅 워크플로를 그대로 로봇 구동에 쓰기 위해서다.

**교훈:** 택하지 않은 대안을 이름으로 적어 두면 설계의 경계가 분명해진다.

#### `PointCloud2`

**직관:** ROS 2의 포인트클라우드 메시지. 점을 구조체 배열로 담지 않고 바이너리 blob + 레이아웃 서술(`fields`)로 담아, 어떤 필드 조합이든 한 타입으로 실어 나른다.

**동작:** Maro LiDAR는 Embree 레이캐스팅 결과를 `mayaToRosPosition`으로 변환한 뒤 `packPointCloud`로 x/y/z/intensity FLOAT32 16바이트 스텝의 blob을 만들고, `MaroRosRuntime`이 `height=1, width=N, is_bigendian=false, is_dense=true, point_step=16, frame_id="world"`를 채워 `/<robotName>/points`로 발행한다. 패킹은 Maya 무의존 라이브러리 `maro_lidar`에 있어 gtest로 검증된다.

**예시:**
```cpp
auto packed = maro::lidar::packPointCloud(rosPoints, {});
cloud.header.frame_id = "world";
cloud.height = 1; cloud.width = packed.pointCount;
cloud.is_bigendian = false; cloud.is_dense = true;
cloud.point_step = packed.pointStep;   // 16
```

**관련 코드:**
- `src/maro_lidar/src/PointCloudPacking.cpp:8-30` — 16바이트 스텝 패킹
- `src/maro_plugin/MaroRosRuntime.cpp:210-235` — 메시지 헤더·플래그 채우기
- `tests/lidar/test_point_cloud_packing.cpp` — 레이아웃 검증

**증거:**
- §1.3, §6.6.4, §5.2

**함정:** `is_dense=true`는 "NaN 점이 없다"는 약속이다. 미스 레이를 NaN으로 넣으면서 dense를 켜면 소비자가 NaN을 안 거르고 계산한다. Maro는 미스를 아예 넣지 않아 dense가 참이다.

**교훈:** 자기 서술형 메시지는 서술과 실제가 일치해야 한다. 플래그 하나가 소비자의 검사 여부를 바꾼다.

#### 기구학 체인(kinematic chain)

**직관:** 축(조인트)들이 부모-자식으로 이어진 트리. Maro에서는 `parentAxis` 연결이 이 트리를 만들고, URDF의 조인트 트리와 "순환 금지" 규칙의 근거가 된다.

**동작:** 각 `maroAxis`는 `parentAxis` 플러그로 부모 축을 가리킨다. 커맨드가 부모를 붙일 때 조상 방향으로 거슬러 올라가 자식을 만나면 순환으로 거부한다(축 개수만큼만 돌아 이미 순환이 있는 씬에서도 멈춤). URDF 내보내기는 `parentAxisPath`가 빈 축을 루트로 잡고 정확히 하나여야 하며, 트리를 따라 `<joint>`의 parent/child 링크를 쓴다.

**예시:**
```python
# 루트 하나, 나머지는 parentAxisPath로 이어진 트리
roots = [r["axisFullPath"] for r in axisRows if not r["parentAxisPath"]]
assert len(roots) == 1
```

**관련 코드:**
- `src/maro_plugin/MaroCommands.cpp:290-310` — 순환 검사
- `python/maroUrdfExport.py:29-45` — 루트 축 하나 규칙
- `python/maroSkeletonUpload.py:142-233` — 스켈레톤에서 체인 생성

**증거:**
- §1.5

**함정:** Maya DAG 계층과 축 체인은 다른 트리다. 트랜스폼이 부모-자식이어도 축의 `parentAxis`가 안 이어져 있으면 URDF에서는 별개 로봇이 된다.

**교훈:** 로봇의 구조는 "축의 연결"이라는 별도 그래프로 명시한다. 씬 계층에서 추론하지 않는다.

#### 토픽(topic)

**직관:** ROS 2 pub/sub의 통신 단위 이름. 같은 이름과 타입으로 발행자와 구독자가 만나며, 노드 이름은 관여하지 않는다.

**동작:** Maro는 네 토픽을 쓴다 — 발행 `/<robotName>/joint_states`(JointState, enabled ∧ jointName 있는 축), `/tf`(TFMessage, 바인딩된 모든 축), `/<robotName>/points`(PointCloud2, 라이다 있을 때); 구독 `/<robotName>/joint_commands`(JointState, controlMode==ROS 축만). 토픽 통계 기능 때문에 `libstatistics_collector`·`statistics_msgs` 링크가 필요하다는 것을 링크 단계 미해결 심볼로 알게 됐다.

**예시:**
```bash
ros2 topic list
# /arm/joint_states  /arm/points  /arm/joint_commands  /tf
ros2 topic echo /arm/joint_states
```

**관련 코드:**
- `src/maro_plugin/MaroRosRuntime.cpp:54-61` — 발행 토픽 3개
- `src/maro_plugin/MaroCommandDeviceNode.cpp:370-371` — 구독 토픽
- `src/maro_plugin/CMakeLists.txt` — 토픽 통계가 끌어온 추가 `.lib`

**증거:**
- §1.6, §6.0, §6.6.4, §12.3

**함정:** 상대 이름(`"joint_states"`)은 노드 네임스페이스 아래로 풀리므로 로봇별 분리가 안 된다. Maro는 항상 `"/" + robotName + "/..."` 절대 이름을 쓴다.

**교훈:** 토픽 이름은 계약이다. 방향·타입·게이트 조건까지 표(§12.3)로 고정해 두면 상대역 테스트가 그 표를 그대로 검증한다.

#### 발행(publish)

**직관:** 메시지를 토픽으로 내보내는 것. Maro에서는 Maya 메인 스레드가 직접 발행하지 않고, 30Hz 펌프가 샘플을 큐에 넣으면 백그라운드 스레드가 꺼내 발행한다.

**동작:** `MaroPump`(메인 스레드, 30Hz)가 축·LiDAR를 훑어 `AxisSample`/`LidarSample`을 `BoundedQueue`에 넣는다. 샘플에는 변환에 필요한 컨텍스트(씬 단위, 축 규약)가 함께 실린다 — 발행 스레드는 Maya에 되물을 수 없기 때문이다. `MaroRosRuntime`의 스레드가 5ms마다 큐를 비워 JointState·TF·PointCloud2로 변환해 `publish()`한다. 펌프는 발행 전담이며 상시 큐(`MaroMainThreadQueue`)와 합치지 않는다.

**예시:**
```
메인 스레드 30Hz: MaroPump → AxisSample{jointName, value, unit, convention} → BoundedQueue
발행 스레드 5ms:  drainAndPublish() → JointState / TFMessage / PointCloud2 → publish()
```

**관련 코드:**
- `src/maro_plugin/MaroPump.cpp:140-160` — 샘플에 컨텍스트를 실어 큐잉
- `src/maro_plugin/MaroRosRuntime.cpp:160-235` — 큐를 비워 세 메시지로 변환·발행
- `tests/maya/test_bridge_pump.py:40-133` — 펌프→큐→발행 통합 검증

**증거:**
- §1.6, §10.1, §10.2

**함정:** 발행 스레드에서 "값 하나만 더" Maya에 물어보고 싶은 유혹이 가장 위험하다. Maya API는 메인 스레드 전용이므로 필요한 것은 전부 샘플에 담아 보낸다.

**교훈:** 스레드 경계를 넘는 데이터는 자기 완결적이어야 한다. "나중에 물어보면 되지"는 크래시의 시작이다.

#### 구독(subscribe)

**직관:** 토픽에 콜백을 등록해 메시지를 받는 것. Maro는 `/<robotName>/joint_commands`를 구독해 ROS 쪽 명령을 축에 반영한다.

**동작:** `MaroCommandDeviceNode`(Maya `MPxThreadedDeviceNode`)의 워커 스레드가 `robotName + "_cmd_rx"` 노드를 만들고 `"/" + robotName + "/joint_commands"`를 depth 10으로 `create_subscription`한다. 콜백은 `spin_some()` 안에서 그 스레드 위에서 동기적으로 불리며, `name.size() != position.size()`면 무시, 비유한 값은 건너뛰고, 이름이 63자를 넘으면 `s_dropped++`, 아니면 메모리 풀의 `pending`에 쌓는다. 메인 스레드가 그것을 꺼내 `controlMode == ROS`인 축에만 `applyToMatchingAxis`로 적용한다.

**예시:**
```cpp
sub = node->create_subscription<sensor_msgs::msg::JointState>(
    "/" + robotName + "/joint_commands", 10,
    [](sensor_msgs::msg::JointState::SharedPtr msg) {
        if (msg->name.size() != msg->position.size()) return;
        /* 풀에 복사만 */
    });
```

**관련 코드:**
- `src/maro_plugin/MaroCommandDeviceNode.cpp:365-390` — 구독 생성과 콜백 검증
- `src/maro_plugin/MaroCommandDeviceNode.cpp:262-290` — 메인 스레드에서 축에 적용
- `tests/peer/maro_test_peer.cpp:100-125` — 상대역이 joint_commands를 발행

**증거:**
- §1.6, §6.6.5, §8.2.7

**함정:** 콜백에서 Maya 플러그를 직접 쓰면 워커 스레드에서 Maya API를 부르는 것이 된다. 콜백은 복사만, 적용은 메인 스레드.

**교훈:** 구독 콜백은 "받았다"까지만 책임진다. 해석과 적용은 소유 스레드로 넘긴다.

#### `sensor_msgs/JointState`

**직관:** 관절 상태를 나르는 표준 메시지 — `header` + `name[]`·`position[]`·`velocity[]`·`effort[]`. 네 배열은 같은 길이거나 비어 있어야 하며, position 단위는 관절 타입에 따라 라디안(revolute) 또는 미터(prismatic)다.

**동작:** Maro는 발행 시 `name`과 `position`만 채운다(허용됨). 각도축은 Maya 도(degree)를 라디안으로, 직선축은 씬 단위(cm)를 미터로 변환해 넣는다. 수신 시에는 이름으로 축을 찾아(`applyToMatchingAxis`) 반대 변환(m→cm)을 하고 델타 체크 뒤 적용한다. 상대역 테스트는 `joint <name> = <pos>` 줄로 값을 출력해 테스트가 **값**을 파싱해 단언한다.

**예시:**
```cpp
sensor_msgs::msg::JointState joints;
joints.name.push_back(sample.jointName);
joints.position.push_back(radians);     // velocity/effort는 비워 둔다
```

**관련 코드:**
- `src/maro_plugin/MaroRosRuntime.cpp:160-180` — name/position 채우기와 단위 변환
- `src/maro_plugin/MaroCommandDeviceNode.cpp:262-290` — 이름 매칭·m→cm
- `tests/peer/maro_test_peer.cpp:25-45` — 값을 출력하는 echo 모드

**증거:**
- §1.6, §11.3, §12.3

**함정:** `name`과 `position` 길이가 다르면 표준 위반이라 소비자가 버린다. 수신 콜백도 같은 이유로 길이 불일치 메시지를 무시한다.

**교훈:** 표준 메시지는 "채우지 않아도 되는 필드"와 "채우면 지켜야 하는 규칙"이 있다. 둘 다 코드 주석에 적는다.

#### `sensor_msgs/PointCloud2`

**직관:** 점 배열을 바이너리 blob으로 나르되, `fields[]`(`PointField` 이름·오프셋·타입)가 레이아웃을 서술하는 메시지. 소비자는 fields를 읽어 blob을 해석한다.

**동작:** Maro의 레이아웃은 `fields=[x,y,z,intensity]` 전부 FLOAT32, offset 0/4/8/12, `point_step=16`, `row_step=16N`, `height=1, width=N`(비정렬), `is_bigendian=false`, `is_dense=true`, `header.frame_id="world"`. `/<robotName>/points`로 `updateRate` 스로틀을 거쳐 발행된다. Velodyne 드라이버의 `ring` 필드는 순정 메시지에 없어 넣지 않는다.

**예시:**
```
fields: x@0 FLOAT32, y@4 FLOAT32, z@8 FLOAT32, intensity@12 FLOAT32
point_step: 16   row_step: 16 * width   height: 1
```

**관련 코드:**
- `src/maro_lidar/src/PointCloudPacking.cpp:8-30` — 필드 오프셋과 16바이트 스텝
- `src/maro_plugin/MaroRosRuntime.cpp:210-235` — 메시지 조립
- `tests/lidar/test_point_cloud_packing.cpp` — 오프셋·크기 검증

**증거:**
- §1.6, §11.3, §12.3

**함정:** RViz는 `x/y/z` 필드 이름을 정확히 요구한다. 오프셋을 맞춰도 이름이 다르면 아무것도 안 보인다.

**교훈:** blob 메시지의 정확성은 서술(fields)이 결정한다. 패킹 함수와 fields 선언을 같은 파일에 두고 테스트로 묶는다.

#### 네임스페이스 `/<robotName>/…`

**직관:** 토픽 이름 앞에 로봇 이름을 붙여 같은 도메인의 여러 로봇을 분리하는 접두사. 노드 이름과는 무관하고, `/tf`만 관례상 전역이다.

**동작:** 발행 `/<robotName>/joint_states`·`/<robotName>/points`, 구독 `/<robotName>/joint_commands`는 모두 `"/" + robotName + "/..."`로 조립한 절대 이름이다. `/tf`는 `robot_state_publisher`·RViz가 전역 토픽으로 기대하므로 접두사를 붙이지 않는다 — 상대역 `tf` 모드에 robotName 인자가 없는 이유다. 한 Maya에 로봇이 둘이면 각각 자기 접두사로 나란히 선다.

**예시:**
```
/arm/joint_states   /arm/points   /arm/joint_commands      ← 로봇별
/tf                                                         ← 전역
```

**관련 코드:**
- `src/maro_plugin/MaroRosRuntime.cpp:47-61` — 절대 경로 관례 주석과 세 토픽
- `tests/peer/maro_test_peer.cpp:80-95` — robotName 없는 tf 모드

**증거:**
- §1.6, §12.3, §11.3

**함정:** `/tf`에 접두사를 붙이면 문법상 유효하지만 아무 도구도 구독하지 않는다. "전역이어야 하는 토픽"은 관례를 따른다.

**교훈:** 네임스페이스는 "누가 구독할 것인가"를 보고 정한다. 우리만 쓰는 토픽은 분리하고, 생태계가 기대하는 토픽은 관례대로.

#### `LaserScan` `angle_increment` 관례

**직관:** 각도 범위를 N개 샘플로 나눌 때 간격은 `(max−min)/(N−1)` — 양 끝값을 모두 포함하는 방식. `sensor_msgs/LaserScan`의 `angle_increment` 정의에서 온 관례다.

**동작:** `RayPattern.cpp`의 `angleAt(index, samples, min, max)`는 `min + (max−min)·index/(samples−1)`을 돌려주고, `samples<=1`이면 0 나눗셈을 피해 `min`만 쓴다. `computeRayDirections`는 수직 채널 바깥 루프·수평 샘플 안쪽 루프로 정확히 v×h개 단위 벡터를 만들며, 로컬 프레임은 +Z 정면·+Y 위, 방향 벡터 `(cosV·sinH, sinV, cosV·cosH)`다.

**예시:**
```cpp
double angleAt(int index, int samples, double minAngle, double maxAngle) {
    if (samples <= 1) return minAngle;
    return minAngle + (maxAngle - minAngle) * (double(index) / double(samples - 1));
}
```

**관련 코드:**
- `src/maro_lidar/include/maro_lidar/RayPattern.h:12-20` — 관례와 로컬 프레임 주석
- `src/maro_lidar/src/RayPattern.cpp:8-16` — angleAt
- `tests/lidar/test_ray_pattern.cpp` — 양 끝값·개수·단위 벡터 검증

**증거:**
- §5.2.2, §8.2.2

**함정:** `(max−min)/N`으로 나누면 마지막 샘플이 max에 못 미친다. 실제 센서 드라이버와 각도가 어긋나 비교 검증이 실패한다.

**교훈:** 이산화 관례는 표준 메시지 정의를 따른다. 우리가 정한 게 아니라 `.msg` 주석이 정한 것이다.

#### `ring` 필드

**직관:** Velodyne·Ouster 드라이버가 PointCloud2에 붙이는 "몇 번째 수직 채널에서 온 점인가" 필드. 순정 ROS 2 메시지 정의에는 없고 드라이버 관례일 뿐이다.

**동작:** Maro는 아직 `ring`을 넣지 않지만, `computeRayDirections`의 반환 순서(바깥 루프 수직 채널, 안쪽 수평 샘플)를 헤더에 명시해 나중에 채널 인덱스를 `ring`으로 쓸 수 있게 자리를 남겼다. 넣게 되면 fields에 `ring UINT16`을 추가하고 `point_step`이 바뀐다.

**예시:**
```
현재 fields: x y z intensity (16B)
미래 fields: x y z intensity ring(UINT16) → point_step 18 또는 패딩 20
```

**관련 코드:**
- `src/maro_lidar/include/maro_lidar/RayPattern.h:16-19` — 반환 순서와 ring 언급
- `src/maro_lidar/src/PointCloudPacking.cpp:8-30` — 현재 레이아웃(ring 없음)

**증거:**
- §5.2.2, §11.3

**함정:** `ring`이 있어야 도는 알고리즘(채널별 지면 추정 등)도 있다. 없다고 잘못은 아니지만, 소비자가 기대하면 문서에 "없음"을 적어야 한다.

**교훈:** 미래 필드는 코드가 아니라 "순서 보장" 같은 불변식으로 예약한다. 그러면 지금 비용 없이 나중 확장이 열린다.

#### 전역 기본 컨텍스트

**직관:** `rclcpp::init()`이 만드는 프로세스에 하나뿐인 컨텍스트. 인자 없이 만든 노드·executor가 모두 여기 매달린다. Maya처럼 플러그인이 여럿 사는 프로세스에서는 이것을 건드리면 안 된다.

**동작:** 전역 컨텍스트는 `rclcpp::init(argc, argv)`로 초기화되고 SIGINT 핸들러가 설치되며 `rclcpp::shutdown()`으로 끝난다. 같은 Maya에 rclcpp를 쓰는 다른 플러그인이 있으면 Maro의 언로드가 그쪽 컨텍스트까지 끝내 버린다(반대도). 그래서 Maro는 2026-09-07 정정으로 자기 `rclcpp::Context`를 만들어 `NodeOptions::context()`·`ExecutorOptions::context`로 넘기고, 전역 컨텍스트는 아예 초기화하지 않는다.

**예시:**
```cpp
// 금지 (프로세스 전역)
rclcpp::init(0, nullptr);  ...  rclcpp::shutdown();
// Maro
auto ctx = maro::rosContext();   // 우리 것만 만들고 우리 것만 끝낸다
```

**관련 코드:**
- `src/maro_plugin/MaroRosContext.h:12-30` — 왜 전역을 안 쓰는가
- `src/maro_plugin/MaroRosContext.cpp:29-47` — 자기 컨텍스트 생성

**증거:**
- §6.6, §6.6.3
- F-087

**함정:** 전역 컨텍스트를 안 만들면 `rclcpp::ok()`(인자 없음)는 항상 false다. 상태 확인은 `rosContextOk()`처럼 우리 컨텍스트로 해야 한다.

**교훈:** "프로세스 전역"은 프로세스를 우리가 소유할 때만 안전하다. 호스트에 얹혀 사는 코드는 자기 몫만 만든다.

#### 절대 토픽 이름(`"/"+robot+"/joint_states"`)

**직관:** 슬래시로 시작하는 토픽 이름은 노드 네임스페이스와 무관하게 그대로 쓰인다. Maro는 로봇 이름을 문자열로 앞에 붙여 절대 이름을 만든다.

**동작:** `MaroRosRuntime::start()`는 `"/" + robotName + "/joint_states"`·`"/tf"`·`"/" + robotName + "/points"`로 퍼블리셔를 만든다. 수신 쪽이 먼저 `"/" + robotName + "/joint_commands"`를 썼으므로 발행 쪽도 같은 관례를 따라 두 방향이 같은 `/<robotName>/` 아래 나란히 선다. `/joint_states`의 `jointName`과 `/tf`의 `child_frame_id`(링크 이름)는 서로 다른 노드에서 오며 일반적으로 다르다 — URDF의 `<joint name>`·`<link name>`이 다른 것과 같은 이유.

**예시:**
```cpp
m_impl->jointPub = node->create_publisher<sensor_msgs::msg::JointState>(
    "/" + robotName + "/joint_states", 10);
```

**관련 코드:**
- `src/maro_plugin/MaroRosRuntime.cpp:47-61` — 절대 경로 관례 주석
- `src/maro_plugin/MaroRosRuntime.cpp:170-180` — `child_frame_id = sample.linkName`

**증거:**
- §6.6, §6.6.1, §6.6.4

**함정:** robotName에 슬래시나 공백이 들어가면 토픽 이름이 무효가 된다. 커맨드가 로봇 이름을 검증하는 이유 중 하나다.

**교훈:** 이름 조립은 한 곳의 관례로 통일한다. 한쪽은 절대, 한쪽은 상대면 같은 로봇의 토픽이 다른 곳에 생긴다.

#### 네임스페이스 해석

**직관:** 상대 토픽 이름은 "노드의 네임스페이스" 아래로 풀린다 — 노드 **이름**이 아니라. 노드 이름을 `arm`으로 지어도 `"joint_states"`는 `/arm/joint_states`가 아니라 `/joint_states`가 된다.

**동작:** 노드 네임스페이스는 `NodeOptions`나 리매핑으로 정해지며 기본은 `/`다. Maro는 네임스페이스를 따로 주지 않고 절대 이름을 직접 조립하므로 해석 규칙에 기대지 않는다. 이 사실은 `MaroRosRuntime.cpp:47-52` 주석에 명시돼 있다.

**예시:**
```
노드 이름 "arm", 네임스페이스 "/"  + 상대 "joint_states" → /joint_states   (로봇별 아님)
절대 "/arm/joint_states"                                  → /arm/joint_states
```

**관련 코드:**
- `src/maro_plugin/MaroRosRuntime.cpp:47-52` — 해석 규칙 주석

**증거:**
- §6.6, §6.6.4

**함정:** "노드 이름을 로봇 이름으로 했으니 토픽도 분리되겠지"가 가장 흔한 오해다. 노드 이름은 토픽 해석에 전혀 관여하지 않는다.

**교훈:** 프레임워크의 이름 해석 규칙에 기대지 말고 원하는 이름을 명시적으로 만든다.

#### QoS depth 10

**직관:** 퍼블리셔가 아직 전달 못 한 메시지를 최대 10개까지 들고 있는 히스토리 깊이(KEEP_LAST 10). `create_publisher(topic, 10)`의 그 `10`이다.

**동작:** Maro의 퍼블리셔 3개와 구독 1개는 모두 depth 10을 쓴다. 30Hz 발행에서 구독자가 잠깐 늦어도 10개(약 0.3초)까지 버퍼링되고 그 이상은 오래된 것부터 버려진다. 정수 하나를 넘기면 rclcpp가 `rclcpp::QoS(KeepLast(10))`로 해석하며 신뢰성·내구성은 기본값(reliable, volatile)이다.

**예시:**
```cpp
node->create_publisher<tf2_msgs::msg::TFMessage>("/tf", 10);   // KEEP_LAST 10
```

**관련 코드:**
- `src/maro_plugin/MaroRosRuntime.cpp:54-61` — 세 퍼블리셔의 depth 10
- `src/maro_plugin/MaroCommandDeviceNode.cpp:370-371` — 구독 depth 10

**증거:**
- §6.6.4

**함정:** 퍼블리셔와 구독자의 QoS가 호환되지 않으면(예: 구독이 transient-local 요구) 연결 자체가 안 된다. 깊이보다 신뢰성·내구성 불일치가 "왜 아무것도 안 오나"의 흔한 원인이다.

**교훈:** 정수 하나로 QoS를 쓰면 나머지 정책은 기본값이다. 소비자가 무엇을 기대하는지 확인하고 명시적 프로파일이 필요하면 바꾼다.

#### `publish()` 동기

**직관:** `publish()`는 호출한 스레드에서 바로 rmw로 내려가 DDS에 전달된다. executor나 spin이 관여하지 않으므로 퍼블리셔만 있는 노드는 spin 없이 동작한다.

**동작:** 발행 스레드의 `drainAndPublish()`는 큐를 비워 메시지를 만들고 `publish()`를 부른다. 이 호출은 동기적으로 직렬화·전송을 마치고 돌아온다. 수신 쪽은 반대로 콜백이 `spin_some()` 안에서 동기 호출되므로 발행/수신 메커니즘이 비대칭이다 — 수신 쪽 큐·뮤텍스·스로틀·시작/정지를 Maya `MPxThreadedDeviceNode`가 네이티브로 제공해 우리가 만든 동기화 코드가 없다.

**예시:**
```cpp
// 발행: spin 없음
m_impl->jointPub->publish(joints);
// 수신: 콜백은 executor.spin_some() 안에서 이 스레드 위에서 불린다
```

**관련 코드:**
- `src/maro_plugin/MaroRosRuntime.cpp:124-135` — spin 없이 publish만 하는 루프
- `src/maro_plugin/MaroCommandDeviceNode.cpp:373-403` — 콜백이 동기로 불리는 spin_some

**증거:**
- §6.6, §6.6.4, §6.6.5

**함정:** `publish()`가 동기라는 것은 DDS 쪽이 막히면 발행 스레드도 막힌다는 뜻이다. 그래서 발행은 메인 스레드가 아니라 전용 스레드에서 한다.

**교훈:** "동기"는 편리함과 위험을 함께 준다. 동기 호출을 어느 스레드에 두는가가 UI 응답성을 결정한다.

#### `_ORIGINAL_ROS_DOMAIN_ID` 모듈 로드 시 캡처

**직관:** 설정 패널 모듈이 import될 때 `ROS_DOMAIN_ID` 환경변수의 원래 값을 한 번 저장해 두는 상수. "도메인 직접 지정"을 껐을 때 되돌릴 기준점이다.

**동작:** `maroSettingsPanel.py` 최상위에서 `_ORIGINAL_ROS_DOMAIN_ID = os.environ.get("ROS_DOMAIN_ID")`로 캡처한다. 연결 시 override가 켜져 있으면 `os.environ["ROS_DOMAIN_ID"] = str(domainId)`, 꺼져 있으면 원래 값이 있었으면 그 값으로, 없었으면 `pop`으로 지운다. 이렇게 해야 "이전 연결이 남긴 값"이 아니라 Maya가 시작될 때의 환경으로 돌아간다.

**예시:**
```python
_ORIGINAL_ROS_DOMAIN_ID = os.environ.get("ROS_DOMAIN_ID")   # 모듈 로드 시 1회
...
elif _ORIGINAL_ROS_DOMAIN_ID is not None:
    os.environ["ROS_DOMAIN_ID"] = _ORIGINAL_ROS_DOMAIN_ID
else:
    os.environ.pop("ROS_DOMAIN_ID", None)
```

**관련 코드:**
- `python/maroSettingsPanel.py:27-30` — 캡처와 이유 주석
- `python/maroSettingsPanel.py:165-172` — 복원 분기

**증거:**
- §7.12

**함정:** 모듈이 reload되면 캡처가 다시 일어나 "그 시점의 값"(이전 override)이 원본으로 오인된다. 개발 중 reload 뒤에는 Maya를 재시작해야 원본이 맞다.

**교훈:** 환경을 바꾸는 코드는 되돌릴 기준을 가장 이른 시점에 저장한다. 되돌림이 없는 변경은 누적된다.

#### `os.environ`

**직관:** Python이 보는 프로세스 환경변수 딕셔너리. 여기에 쓰면 같은 프로세스에서 이후 실행되는 C++ 코드(rcl의 `getenv`)도 그 값을 본다.

**동작:** 설정 패널이 `os.environ["ROS_DOMAIN_ID"]`를 쓰고, 그 뒤 브리지를 올리면 `Context::init`이 환경을 읽어 도메인이 반영된다. 테스트 CMake는 모든 Maya 테스트에 `MARO_DIAG_BOOK_DIR`을 환경으로 넘겨 진단 book이 사용자의 진짜 Maya prefs를 더럽히지 않게 한다. `ROS_DOMAIN_ID`용 명령줄 플래그는 환경변수 경로만 구현하고 go/no-go 결과에 따라 보류됐다(F-299).

**예시:**
```python
os.environ["ROS_DOMAIN_ID"] = "7"    # 이후 rosContext()가 새로 init될 때 읽힌다
```

**관련 코드:**
- `python/maroSettingsPanel.py:165-172` — 도메인 ID 쓰기/복원
- `tests/CMakeLists.txt:236-255` — `MARO_DIAG_BOOK_DIR` 환경 주입
- `src/maro_plugin/MaroRosContext.cpp:35-41` — 환경이 읽히는 시점

**증거:**
- §7.12, §8.1, §12.4
- F-299

**함정:** `os.environ` 변경은 Python의 `putenv`를 거쳐 C 런타임 환경에도 반영되지만, 이미 초기화된 라이브러리는 다시 읽지 않는다. "언제 읽히는가"를 알아야 효과가 있다.

**교훈:** 환경변수는 프로세스 전체에 대한 전역 상태다. 쓰는 곳·읽는 시점·되돌리는 규칙을 한 모듈에 모은다.

#### `setRange(0, 232)`

**직관:** 도메인 ID 스핀박스의 허용 범위. DDS 도메인 ID의 이론적 상한 232까지 열어 두되, ROS 2 문서가 권장하는 0–101과는 다르다는 것을 알고 정한 값이다.

**동작:** 설정 패널의 `_domainIdField.setRange(0, 232)`. DDS는 도메인 ID로 UDP 포트를 계산하므로 232를 넘으면 포트가 범위를 벗어난다. ROS 2가 0–101을 권장하는 이유는 큰 ID가 참가자 수에 따라 임시 포트 범위와 겹칠 수 있어서다. UI는 물리적 상한을 쓰고 권장 범위는 문서에 둔다.

**예시:**
```python
self._domainIdField.setRange(0, 232)    # DDS 상한; ROS 2 권장은 0–101
```

**관련 코드:**
- `python/maroSettingsPanel.py:122` — 범위 설정

**증거:**
- §7.12

**함정:** 232 근처 도메인은 Windows에서 다른 서비스 포트와 충돌해 "아무것도 안 보이는" 상황을 만들 수 있다. 문제 재현이 안 되면 도메인을 낮춰 본다.

**교훈:** UI 한계값은 "가능한 값"과 "권장 값" 중 무엇인지 주석으로 밝힌다.

#### `RUN_SERIAL TRUE`

**직관:** ctest에 "이 테스트는 다른 테스트와 동시에 돌리지 마라"고 알리는 속성. 실제 rclcpp 컨텍스트(DDS 도메인)를 띄우는 테스트에 붙인다.

**동작:** `bridge_pump`·`lidar_publish`·`publish`·`contract`는 진짜 컨텍스트로 발행·수신하므로 같은 도메인에서 동시에 돌면 서로의 메시지를 받아 간섭한다. `set_tests_properties(... RUN_SERIAL TRUE)`로 ctest가 이들을 순차 실행한다. `lidar_publish`는 브리프가 일반 그룹에 넣으라 했지만 그 그룹의 전제(RUN_SERIAL 없음)를 깨는 대신 `bridge_pump`와 같은 모양으로 따로 등록했다.

**예시:**
```cmake
set_tests_properties(maya_bridge_pump PROPERTIES RUN_SERIAL TRUE)
```

**관련 코드:**
- `tests/CMakeLists.txt:323-352` — RUN_SERIAL 등록과 이유 주석

**증거:**
- §8.1

**함정:** `ctest -j8`로 병렬을 켜면 RUN_SERIAL이 없는 DDS 테스트는 간헐 실패한다. 플래키로 오인하기 쉽지만 원인은 도메인 공유다.

**교훈:** 외부 공유 자원(네트워크 도메인)을 쓰는 테스트는 격리를 테스트 러너에 선언한다.

#### DDS 도메인 간섭

**직관:** 같은 `ROS_DOMAIN_ID`의 참가자는 서로를 발견하고 메시지를 주고받는다. 두 테스트가 같은 도메인에서 동시에 같은 토픽을 쓰면 서로의 메시지를 받아 결과가 뒤섞인다.

**동작:** 테스트 상대역이 `/arm/joint_states`를 기다리는데 다른 테스트의 Maya가 같은 이름으로 발행하면 엉뚱한 값을 받는다. 해법은 두 가지 — 도메인을 나누거나 순차 실행. Maro는 `RUN_SERIAL TRUE`로 순차 실행을 택했다. 같은 이유로 개발자가 별도 터미널에서 `ros2 topic echo`를 켜 두면 테스트에 참가자가 하나 더 생긴다.

**예시:**
```
테스트 A (도메인 0): Maya → /arm/joint_states
테스트 B (도메인 0): peer가 /arm/joint_states 대기 → A의 메시지를 받아 오판
```

**관련 코드:**
- `tests/CMakeLists.txt:323-352` — 간섭 방지 등록
- `tests/peer/maro_test_peer.cpp:25-45` — 첫 메시지를 받으면 만족하는 상대역

**증거:**
- §8.1

**함정:** 로컬에서는 통과하고 CI에서만 깨진다면 CI가 병렬로 돌리거나 다른 잡이 같은 도메인을 쓰는지 본다.

**교훈:** 발견 기반 미들웨어는 "격리"가 기본이 아니다. 테스트마다 무엇을 공유하는지 명시한다.

#### 양 끝값 포함(endpoint-inclusive)

**직관:** 범위 `[min, max]`를 N개로 샘플링할 때 첫 샘플이 min, 마지막이 max가 되게 `(N−1)`로 나누는 방식. 레이 패턴의 각도 샘플링 규칙이다.

**동작:** `test_ray_pattern.cpp`는 `computeRayDirections(vCount, vMin, vMax, hCount, hMin, hMax)`가 정확히 v×h개, 전부 단위 벡터, (0,0)이 로컬 +Z, 양의 수직각이 +Y로 기울며, 첫/마지막 샘플이 각각 min/max 각도라는 것과 샘플 1개일 때 0 나눗셈이 없다는 것을 검증한다.

**예시:**
```
N=5, [−10°, +10°] → −10, −5, 0, +5, +10   (간격 20/(5−1) = 5°)
```

**관련 코드:**
- `src/maro_lidar/src/RayPattern.cpp:8-16` — `(samples−1)` 나눗셈
- `tests/lidar/test_ray_pattern.cpp` — 끝값·개수·단위 벡터 단언

**증거:**
- §8.2.2, §5.2.2

**함정:** 끝값 포함은 "간격 × N ≠ 범위"라는 뜻이다. 간격으로 개수를 역산하는 코드가 있으면 하나 어긋난다.

**교훈:** 샘플링 규칙은 예제 숫자(N=5면 간격 5°)로 테스트에 박아 둔다. 말로 적은 규칙은 다르게 읽힌다.

#### `LaserScan.msg` 관례

**직관:** `sensor_msgs/LaserScan` 메시지 정의의 `angle_increment` 주석이 정한 규칙 — 샘플 간 각도는 `(angle_max − angle_min)/(N−1)`. Maro는 2D 스캔 메시지를 쓰지 않지만 각도 이산화 규칙만 빌려 왔다.

**동작:** `RayPattern.h` 주석이 "각도 간격은 sensor_msgs/msg/LaserScan.msg의 실제 angle_increment 관례"라고 출처를 밝히고, `angleAt`이 그 공식을 구현한다. 실제 LiDAR 드라이버와 각도가 일치해야 시뮬레이션 포인트클라우드를 실측과 비교할 수 있기 때문이다. 상대역의 `tf` 모드가 robotName을 받지 않는 것처럼, 생태계 관례를 따르는 결정은 근거를 주석에 남긴다.

**예시:**
```
# LaserScan.msg
float32 angle_increment   # angular distance between measurements [rad]
# → N개 측정이면 increment = (max − min) / (N − 1)
```

**관련 코드:**
- `src/maro_lidar/include/maro_lidar/RayPattern.h:12-16` — 출처 주석
- `src/maro_lidar/src/RayPattern.cpp:8-16` — 구현

**증거:**
- §8.2, §8.2.2, §8.2.7

**함정:** 3D LiDAR 드라이버 중에는 수평각을 `(max−min)/N`으로 도는 것도 있다. 비교 대상 센서의 규칙을 확인하고 필요하면 옵션으로 연다.

**교훈:** 관례를 빌릴 때는 출처를 코드 주석에 적는다. "왜 N−1인가"를 다음 사람이 묻지 않게.

#### 토픽 네임스페이스

**직관:** `/<ns>/<name>` 형태로 토픽을 묶는 접두사 체계. Maro는 네 토픽 중 셋을 로봇 이름으로 네임스페이스하고 `/tf`만 전역으로 둔다.

**동작:** §12.3 계약 표: `/<robotName>/joint_states`(발행, `enabled ∧ jointName≠""`), `/tf`(발행, 바인딩된 축 전부), `/<robotName>/points`(발행, `updateRate` 스로틀), `/<robotName>/joint_commands`(구독, `controlMode==1` + 델타 체크 + m→cm). 발행 조건 열이 곧 계약이라 상대역 테스트가 이 표를 검증한다. 피어의 `tf` 모드에 robotName이 없는 것도 이 표에서 나온다.

**예시:**
```
| 토픽                         | 방향 | 타입         | 조건                         |
| /<robot>/joint_states        | 발행 | JointState  | enabled ∧ jointName≠""       |
| /tf                          | 발행 | TFMessage   | 바인딩된 축 전부              |
| /<robot>/points              | 발행 | PointCloud2 | updateRate 스로틀             |
| /<robot>/joint_commands      | 구독 | JointState  | controlMode==ROS, m→cm        |
```

**관련 코드:**
- `src/maro_plugin/MaroRosRuntime.cpp:54-61` — 발행 셋
- `src/maro_plugin/MaroCommandDeviceNode.cpp:370-371` — 구독 하나
- `tests/maya/test_publish.py:94-101` — 표대로 검증하는 테스트

**증거:**
- §12.3, §6.6.4

**함정:** 표를 코드와 따로 두면 어긋난다. 토픽 이름 문자열은 §12.3과 코드 두 곳뿐이고, 테스트가 둘을 잇는다.

**교훈:** 통신 계약은 표 하나로 고정하고 테스트가 그 표를 읽게 한다.

#### QoS(KEEP_LAST 10)

**직관:** 퍼블리셔 히스토리 정책 — 최근 10개만 유지. `/tf_static`이 쓰는 transient-local(늦게 온 구독자에게도 마지막 메시지를 전달)과는 다른, 휘발성(volatile) 기본 프로파일이다.

**동작:** Maro의 모든 퍼블리셔는 `KEEP_LAST 10` + reliable + volatile이다. 30Hz로 계속 발행되는 `/joint_states`·`/tf`는 늦게 붙은 구독자도 다음 프레임을 곧 받으므로 transient-local이 필요 없다. 정적 변환(`/tf_static`)은 발행하지 않는다 — 모든 프레임이 매 프레임 `/tf`로 나간다.

**예시:**
```cpp
// 정수 10 == rclcpp::QoS(rclcpp::KeepLast(10)) : reliable, volatile
node->create_publisher<sensor_msgs::msg::PointCloud2>("/" + robotName + "/points", 10);
```

**관련 코드:**
- `src/maro_plugin/MaroRosRuntime.cpp:54-61` — 퍼블리셔 QoS
- `src/maro_plugin/MaroRosRuntime.cpp:170-180` — 매 프레임 `/tf` 발행(정적 분리 없음)

**증거:**
- §12.3, §6.6.4

**함정:** 나중에 `/tf_static`을 추가하면 transient-local QoS를 써야 RViz가 늦게 켜져도 프레임을 본다. 기본 정수 QoS를 그대로 쓰면 "가끔 프레임이 없다"가 된다.

**교훈:** QoS는 토픽의 성격(연속 스트림 vs 한 번 발행)에 따라 정한다. 지금은 전부 스트림이라 기본값이 맞다.
