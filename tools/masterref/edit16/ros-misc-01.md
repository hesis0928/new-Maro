<!-- ros-misc-01 ROS 2 › 생태계·도구 + URDF + TF·좌표 규약(REP) + Windows 통합·빌드 (31개) 2026-09-17 -->

#### Gazebo

**직관:** ROS 생태계의 표준 물리 시뮬레이터. "로봇을 내보내 외부에서 돌린다"는 방식의 대표이며, Maro의 첫 번째 설계 원칙 "로봇은 Maya 씬 안에서 산다"는 이것과의 대비로 정의된다.

**동작:** Gazebo 파이프라인은 URDF/SDF와 플러그인으로 로봇·센서를 기술하고 시뮬레이터가 물리·렌더·센서를 돈다. Maro는 Maya의 디포머·스키닝·키프레임이 그대로 구동원이고 센서(LiDAR)도 Maya 안에서 Embree로 계산한다. 다만 어트리뷰트 이름은 생태계와 맞췄다 — `maroLidar`의 `verticalSamples`·`horizontalSamples`·`rangeMin`·`rangeMax`·`updateRate`는 `urdf_sensor`의 Ray 센서와 Gazebo `<sensor type="gpu_ray">`에서 왔다.

**예시:**
```
Gazebo:  <sensor type="gpu_ray"><ray><scan><horizontal samples="360" .../></scan><range min max/></ray>
Maro:    maroLidar.horizontalSamples / rangeMin / rangeMax / updateRate   (같은 어휘)
```

**관련 코드:**
- `README.md:4-5` — 외부 시뮬레이터와의 대비
- `src/maro_plugin/MaroLidarNode.cpp:48-80` — Gazebo 어휘를 따른 어트리뷰트
- `docs/superpowers/specs/2026-08-20-maro-lidar-walking-skeleton-design.md` — `urdf_sensor` 참조

**증거:**
- §1.2, §11.3

**함정:** "Gazebo로 내보내면 되지 않나"는 리깅 워크플로를 버리자는 말과 같다. 대신 Gazebo의 어휘를 빌려 사용자가 낯설지 않게 했다.

**교훈:** 대안을 택하지 않더라도 그 생태계의 이름 관례는 따른다. 사용자 머릿속의 어휘가 곧 UI다.

#### OpenUSD

**직관:** Pixar의 씬 서술 프레임워크(Universal Scene Description). Maya 2026에 내장돼 있으며, 초기 구상에서 Maya↔ROS를 한 프로세스에 묶지 않는 "투 트랙" 설계의 Track A 운반 수단으로 검토됐다.

**동작:** 투 트랙 구상(F-257)은 저용량 구조 데이터(관절/트랜스폼)를 USD 스테이지의 `TfNotice`로, 고용량 센서 데이터(뷰포트 픽셀)를 OS 공유 메모리 제로카피로 나르자는 것이었다. 실제 구현은 같은 프로세스에 rclcpp를 링크하는 단일 트랙으로 갔고, USD는 쓰지 않는다. 구상은 `Maro_Management` 등 레거시 트리에 흔적으로 남았다.

**예시:**
```
구상(미구현): Maya → USD stage → TfNotice → 별도 ROS 프로세스
실제:         Maya 프로세스 안 maro.mll → rclcpp → DDS
```

**관련 코드:**
- `Maro_Management/` — 투 트랙 시절 레거시(빌드 밖, `COLCON_IGNORE`)
- `src/maro_plugin/MaroRosContext.cpp:29-47` — 실제로 택한 동일 프로세스 링크

**증거:**
- §4.1, §4.2
- F-257

**함정:** USD가 Maya에 있다고 그것이 IPC 수단이 되지는 않는다. `TfNotice`는 프로세스 내 옵저버라 프로세스 경계를 넘지 못한다.

**교훈:** 프레임워크의 "있음"과 "적합함"은 다르다. 구상 단계에서 전송 경계(프로세스 안/밖)를 먼저 확인한다.

#### `TfNotice`

**직관:** OpenUSD `Tf` 라이브러리의 옵저버(알림) 메커니즘 — 스테이지 변경을 구독자에게 통지한다. Track A(관절·트랜스폼 전달)용으로 구상됐고 구현되지 않았다.

**동작:** `TfNotice`는 같은 프로세스 안의 리스너에게 동기적으로 알림을 보내는 C++ 이벤트 버스다. 투 트랙 구상은 Maya가 USD 스테이지를 갱신하면 알림을 받아 ROS로 옮기는 것이었지만, 결국 Maya 프로세스 안에서 직접 rclcpp로 발행하는 편이 단순해 폐기됐다. 현재 코드에는 등장하지 않으며 실패 카탈로그 F-257이 구상과 폐기 이유를 기록한다.

**예시:**
```
구상: TfNotice::Register(listener, &Listener::onStageChanged) → 관절값 → ROS
실제: MaroPump(30Hz 타이머) → BoundedQueue → MaroRosRuntime::publish()
```

**관련 코드:**
- `src/maro_plugin/MaroPump.cpp:52-84` — TfNotice 대신 쓰는 타이머 펌프
- `Maro_Management/` — 구상의 레거시 흔적

**증거:**
- §4.1, §4.2
- F-257

**함정:** 폐기된 구상의 이름이 문서에 남아 "USD 연동이 있나"라는 오해를 만든다. 마스터는 "미구현"을 명시한다.

**교훈:** 버린 설계도 이름과 이유를 남긴다. 그래야 같은 아이디어가 두 번 검토되지 않는다.

#### URDF

**직관:** Unified Robot Description Format — ROS가 로봇의 기구학(링크·조인트 트리)과 형상(시각·충돌 메쉬)을 적는 XML. Maro는 축 트리에서 URDF를 만들어 RViz·`robot_state_publisher`로 라이브 발행을 검증한다.

**동작:** S5 파이프라인 세 슬라이스 — (1) 링크별 시각 메쉬 STL, (2) 스킨 메쉬를 영향 조인트로 분할, (3) 볼록 껍질 `<collision>`. 링크 이름은 바인딩 타겟의 짧은 이름, 자세는 축 로케이터의 부모 트랜스폼 강체다. 조인트 이름(`jointName`)은 `/joint_states`와 URDF `<joint>`의 이름이며 링크 이름과 별개다. 수학의 핵심은 셋 — `<origin>`은 켤레라 자기완결적, `<axis>`는 별개 벡터 선택이라 `(x,y,z)→(x,−z,y)` 재배치 필요, rpy는 Maya `kXYZ` 행벡터 = URDF `Rz·Ry·Rx` 열벡터.

**예시:**
```xml
<robot name="arm">
  <link name="base"/><link name="upper"/>
  <joint name="shoulder" type="revolute">
    <parent link="base"/><child link="upper"/>
    <origin xyz="0 0 0.5" rpy="0 0 0"/><axis xyz="0 0 1"/>
    <limit lower="-1.57" upper="1.57" effort="10" velocity="1"/>
  </joint>
</robot>
```

**관련 코드:**
- `python/maroUrdfExport.py:28-90` — 축 트리와 축 벡터 재배치
- `python/maroUrdfExport.py:196-260` — XML 조립
- `python/maroUrdfExport.py:754-800` — STL·껍질 쓰기
- `tests/maya/test_urdf_export.py` — 세 슬라이스 검증

**증거:**
- §1.3, §11.1, §10.6, §7.14

**함정:** 스펙 §3.3은 "origin이 이미 로케이터 자세를 확정하므로 축 변환 불필요"라 했지만 틀렸다 — 200쌍 검증에서 X축만 우연히 맞았다. 켤레로 불변인 것과 벡터 하나로 재배치가 필요한 것을 구분해야 한다.

**교훈:** 좌표 변환은 "무엇이 켤레로 따라오고 무엇이 명시적 벡터인가"를 나눠 생각한다. 랜덤 대량 검증이 우연한 일치를 걸러 준다.

#### URDF `<robot>/<link>/<joint>/<origin xyz rpy>/<parent>/<child>/<axis>/<limit lower upper effort velocity>/<mimic joint multiplier offset>/<visual>/<collision>/<geometry><mesh filename scale>/<box size>`

**직관:** URDF 문서를 이루는 요소들. `<robot>` 아래 `<link>`와 `<joint>`가 트리를 만들고, 조인트의 `<origin>`·`<axis>`·`<limit>`·`<mimic>`이 운동을, 링크의 `<visual>`·`<collision>` 안 `<geometry>`가 형상을 적는다.

**동작:** `<joint><origin>`은 "부모 링크 프레임 → 조인트 프레임" 변환이고 자식 링크 프레임은 조인트 프레임과 같다. 루트 링크에는 origin이 없다. `<axis xyz>`는 조인트(=자식) 프레임 기준 단위 벡터, 기본 (1,0,0). revolute/prismatic은 `<limit>`(effort·velocity 포함) 필수, continuous는 없음. `<mimic joint multiplier offset>`은 `value = multiplier·other + offset`. `buildUrdfXml`은 `<visual>`에 `<origin xyz="0 0 0">`(정점을 이미 링크 프레임으로 구움), `<collision>`에 `collisionMesh` 또는 `collisionBox`(AABB 중심을 origin으로) 중 하나를 쓴다.

**예시:**
```xml
<link name="upper">
  <visual><origin xyz="0 0 0"/><geometry><mesh filename="package://arm/meshes/upper.stl" scale="1 1 1"/></geometry></visual>
  <collision><origin xyz="0 0 0.2"/><geometry><box size="0.1 0.1 0.4"/></geometry></collision>
</link>
<joint name="wrist2" type="continuous"><mimic joint="wrist1" multiplier="-1" offset="0"/>...</joint>
```

**관련 코드:**
- `python/maroUrdfExport.py:196-260` — 요소별 조립 규칙
- `python/maroUrdfExport.py:60-87` — `<axis>` 벡터 `_AXIS_VECTORS`
- `python/maroUrdfExport.py:90-145` — `<limit>`/`<mimic>` 결정

**증거:**
- §7.14

**함정:** `<box>`는 자기 원점이 중심이라 AABB를 그대로 쓰면 반쪽이 어긋난다. AABB 중심을 `<origin>`으로 옮겨야 한다.

**교훈:** 각 요소의 "기준 프레임"을 표로 적어 두고 조립한다. 요소마다 기준이 다르다.

#### 조인트 타입 `revolute/continuous/prismatic/fixed`(+`floating/planar` 미사용)

**직관:** URDF 조인트의 운동 종류 — 제한 있는 회전, 무제한 회전, 직선, 고정. Maro 축의 capability 조합에서 이 넷 중 하나로 결정하며 floating/planar는 쓰지 않는다.

**동작:** `jointType(capRows)`는 coupling(mimic)을 먼저 본다 — coupling은 limit을 절대 참고하지 않으므로(대칭 기어처럼 제한 없는 mimic) capType 6→`continuous`, 7→`prismatic`. 그 다음 rotation+limit→`revolute`(`lower/upper`를 `min/max`로 정렬해 뒤집힌 리밋을 관용), rotation만→`continuous`, translation+limit→`prismatic`, translation만→`prismatic` with ±1e6(URDF는 prismatic에 `<limit>` 필수), 아니면 `fixed`. C++ compute의 "가장 낮은 인덱스 primary driver"와 의도적으로 다르며 우회 씬에서만 갈린다.

**예시:**
```python
jointType([{"capType": 1, "min": -90, "max": 90}])   # → revolute, lower=-1.571, upper=1.571
jointType([{"capType": 6, ...}])                      # → continuous + mimic
jointType([])                                         # → fixed
```

**관련 코드:**
- `python/maroUrdfExport.py:90-145` — 결정 순서
- `python/maroUrdfExport.py:196-260` — 타입별 `<axis>/<limit>` 유무

**증거:**
- §7.14

**함정:** prismatic에 limit이 없으면 `check_urdf`가 거부한다. ±1e6이라는 "사실상 무한"을 넣는 것이 표준을 만족시키는 방법이다.

**교훈:** 대상 포맷의 필수/금지 규칙을 코드로 옮길 때는 "없음"도 값으로 표현할 방법을 정한다.

#### `package://<robot>/meshes/<name>.stl`

**직관:** ROS 패키지 상대 URI. 절대 경로 대신 "`<robot>` 패키지의 `meshes/` 아래"로 적어 URDF가 어느 머신에서든 같은 문자열로 메쉬를 찾게 한다.

**동작:** `_writeLinkMeshes(links, meshDir, robotName)`는 강체 메쉬를 우선, 없으면 스킨 조각을 STL로 굽고 `link["visualMesh"]`에 `package://<robotName>/meshes/<name>.stl`을 채운다. 껍질은 `<name>_collision.stl`, 퇴화면 `collisionBox`. `meshDir`는 실제로 쓸 것이 생겼을 때만 만든다. RViz에서 보려면 `<robotName>` 이름의 패키지를 AMENT_PREFIX_PATH에 두거나 `package://`를 `file://`로 바꿔 쓴다.

**예시:**
```xml
<mesh filename="package://arm/meshes/upper.stl" scale="1 1 1"/>
<!-- 로컬 확인용: file:///C:/export/arm/meshes/upper.stl -->
```

**관련 코드:**
- `python/maroUrdfExport.py:754-800` — STL 쓰기와 URI 채우기
- `python/maroUrdfExport.py:196-260` — `<mesh filename>` 조립

**증거:**
- §7.14

**함정:** `package://`는 ROS 도구가 해석하는 스킴이라 일반 뷰어는 못 연다. 내보낸 URDF를 바로 열어 보려면 스킴 치환이 필요하다.

**교훈:** 이식성 있는 참조는 "어디서 찾을지"를 소비자에게 맡긴다. 그 대신 소비자의 해석 규칙을 문서에 적는다.

#### `check_urdf`

**직관:** urdfdom이 제공하는 검증 CLI — URDF를 파싱해 링크·조인트 트리를 출력하고 오류가 있으면 거부한다. Maro는 내보낸 파일을 이것으로 먼저 검증한다.

**동작:** `check_urdf robot.urdf`는 루트 링크와 트리를 출력한다. 거부하는 대표 원인은 링크 이름 중복, 빈 링크 이름, 부모 없는 링크 둘 이상, prismatic/revolute의 `<limit>` 누락. `_buildRobotModel()`은 이 규칙을 미리 적용해 축 없음·미바인딩 축·링크 이름 중복이면 `ValueError`로 내보내기를 막는다 — `check_urdf`에서 걸리기 전에 Maya 안에서 사용자에게 알린다.

**예시:**
```bash
check_urdf arm.urdf
# robot name is: arm
# ---------- Successfully Parsed XML ---------------
# root Link: base has 1 child(ren)
```

**관련 코드:**
- `python/maroUrdfExport.py:820-835` — 중복 링크·미바인딩 검사
- `tests/maya/test_urdf_export.py` — 거부 케이스 테스트

**증거:**
- §7.14, §11.3

**함정:** `check_urdf`가 통과해도 `<axis>`가 틀리면 로봇은 엉뚱하게 움직인다. 구문 검증과 의미 검증은 다르다 — 후자는 RViz에서 라이브 `/joint_states`와 비교해야 한다.

**교훈:** 외부 검증기의 규칙을 내보내기 코드에 복제하면 오류가 사용자 가까이에서 난다.

#### 링크 이름 중복 → `ValueError`

**직관:** 두 축의 바인딩 대상이 같은 짧은 이름이면 URDF `<link>`가 중복되고 `/tf`에서 두 발행자가 한 프레임을 다툰다. 내보내기는 이를 `ValueError`로 막는다.

**동작:** `_buildRobotModel()`은 축 없음, 미바인딩 축, 링크 이름 중복을 각각 `ValueError`로 던진다. `buildAxisTree`는 루트가 정확히 하나가 아니거나 빈 `jointName`이 있으면 같은 예외를 던지고 어느 축인지 메시지에 넣는다. Maya에서는 다른 계층의 두 트랜스폼이 같은 짧은 이름을 가질 수 있어(`|a|arm`, `|b|arm`) 링크 이름 충돌이 자연스럽게 생긴다.

**예시:**
```python
try:
    model = _buildRobotModel()
except ValueError as exc:
    cmds.warning(str(exc))     # "duplicate link name 'arm' (|a|arm, |b|arm)"
```

**관련 코드:**
- `python/maroUrdfExport.py:28-50` — 루트·jointName 검사
- `python/maroUrdfExport.py:820-835` — 중복 링크 검사와 `/tf` 충돌 주석

**증거:**
- §7.14

**함정:** 내보내기는 막아도 라이브 `/tf`는 막지 않는다. 같은 이름의 두 프레임이 30Hz로 번갈아 발행되면 RViz에서 링크가 떨린다.

**교훈:** 이름 유일성은 내보내기와 라이브 양쪽의 계약이다. 한쪽에서만 검사하면 다른 쪽에서 증상이 난다.

#### `tf2_msgs/TFMessage`

**직관:** `TransformStamped[]` 배열 — 각 항목이 `header.frame_id`(부모), `child_frame_id`, `translation`, `rotation`(쿼터니언)이다. `/tf` 토픽의 타입이며 전역 토픽이다.

**동작:** tf2는 REP-105의 프레임 트리(earth→map→odom→base_link)를 가정하지만 RViz RobotModel은 링크 프레임의 존재만 요구한다. 그래서 Maro는 모든 링크를 `world` 아래 평평하게 발행한다 — `header.frame_id="world"`, `child_frame_id=linkName`, 자세는 로케이터 부모 강체의 월드 변환. 고정 관절은 `/tf_static`이 관례지만 Maro는 전부 `/tf`로 매 프레임 낸다.

**예시:**
```cpp
geometry_msgs::msg::TransformStamped t;
t.header.frame_id = "world";
t.child_frame_id = sample.linkName;
t.transform.translation = ...; t.transform.rotation = ...;   // 쿼터니언
tfMsg.transforms.push_back(t);
```

**관련 코드:**
- `src/maro_plugin/MaroRosRuntime.cpp:170-180` — TransformStamped 채우기
- `tests/peer/maro_test_peer.cpp:57-80` — tf 모드가 `child_frame_id`로 골라 출력

**증거:**
- §1.6, §12.3, §11.3

**함정:** 평평한 트리는 RViz에는 충분하지만 tf2의 lookupTransform으로 링크 간 상대 변환을 구하는 소비자에게는 부모 정보가 없다. 필요하면 URDF + `robot_state_publisher`가 트리를 만든다.

**교훈:** 메시지의 최소 요구(프레임 존재)와 생태계의 관례(트리·static)를 구분해 지금 필요한 만큼만 발행한다.

#### `/tf`

**직관:** 프레임 변환을 나르는 ROS 2의 전역 토픽. 로봇 이름으로 네임스페이스하지 않으며, 모든 노드가 같은 `/tf`를 보고 하나의 프레임 트리를 만든다.

**동작:** Maro는 축이 바인딩만 되어 있으면(비활성 포함) 매 프레임 `/tf`로 `TFMessage`를 낸다. `enabled`는 `/joint_states`만 거른다 — 비활성 축도 씬에서 공간을 차지하므로 TF 프레임은 내야 URDF엔 있는 링크가 TF엔 없어 RViz에 프레임 없는 링크가 생기는 일이 없다. 발행 경로는 `MaroPump`(30Hz) → `BoundedQueue` → `MaroRosRuntime` 스레드(5ms)다.

**예시:**
```bash
ros2 topic echo /tf          # 로봇 이름 없이 전역
ros2 run tf2_tools view_frames
```

**관련 코드:**
- `src/maro_plugin/MaroRosRuntime.cpp:57` — `"/tf"` 퍼블리셔
- `src/maro_plugin/MaroRosRuntime.cpp:160-180` — enabled와 무관하게 TF 발행
- `src/maro_plugin/MaroPump.cpp:149-155` — "enabled와 빈 jointName은 더 이상 축을 통째로 건너뛰지 않는다"

**증거:**
- §1.6, §1.3, §6.6, §11.3

**함정:** `/tf`에 로봇 접두사를 붙이면 RViz·`robot_state_publisher`가 아무것도 못 받는다. 전역 관례를 깨지 않는다.

**교훈:** 생태계가 "하나"로 기대하는 토픽은 우리 네임스페이스 규칙의 예외로 명시한다.

#### `child_frame_id`

**직관:** `TransformStamped`에서 "이 변환이 정의하는 자식 프레임"의 이름. Maro는 링크 이름(바인딩 타겟 트랜스폼의 짧은 이름)을 쓴다.

**동작:** `AxisSample.linkName`은 축이 바인딩된 트랜스폼의 `MFnDagNode::name()`(짧은 이름)이고 `MaroRosRuntime`이 그대로 `child_frame_id`에 넣는다. `jointName`(`/joint_states`의 이름)과 `linkName`은 서로 다른 노드에서 오며 일반적으로 다르다 — URDF의 `<joint name>`과 `<link name>`이 다른 것과 같은 이유(TF 링크 프레임 스펙 §2-1). URDF 내보내기도 같은 짧은 이름을 `<link name>`으로 써서 RViz RobotModel이 `/tf`의 프레임과 매칭한다.

**예시:**
```
축 노드: shoulderAxis (jointName="shoulder")  → /joint_states name[]="shoulder"
바인딩:  |arm|upper (linkName="upper")       → /tf child_frame_id="upper", URDF <link name="upper">
```

**관련 코드:**
- `src/maro_plugin/MaroRosRuntime.cpp:177` — `t.child_frame_id = sample.linkName`
- `src/maro_plugin/MaroPump.cpp:149-155` — linkName 샘플링
- `python/maroUrdfExport.py:820-835` — 같은 짧은 이름을 `<link name>`으로

**증거:**
- §1.6, §12.3, §6.6.1

**함정:** 링크 이름을 조인트 이름으로 쓰면 URDF `<link>`와 `/tf` 프레임이 어긋나 RViz가 로봇을 못 그린다. 두 이름은 별개 필드다.

**교훈:** 한 객체가 두 생태계 이름(조인트/링크)을 가질 때는 각 이름의 출처 노드를 고정하고 섞지 않는다.

#### REP-103

**직관:** ROS의 단위·좌표 규약 문서 — SI 단위(미터·라디안), 우수좌표계, X 앞/Y 왼쪽/Z 위, 회전은 쿼터니언 우선. Maya(Y-up, cm)와의 변환 규칙이 여기서 나온다.

**동작:** `maro_transform`은 Maya(Y-up, 우수, 씬 단위 cm 기본)와 REP-103(Z-up, X-forward, Y-left, 미터) 사이 변환을 상태 없는 순수 함수로 고립한다 — `mayaToRos: (x,y,z)→(x,−z,y)`, `rosToMaya: (x,y,z)→(x,z,−y)`, 단위는 `SceneUnit`으로 스케일. `mayaToRos(rosToMaya(x)) ≈ x` 왕복 불변식을 랜덤 대량 입력으로 테스트한다. 회전각은 도→라디안, 직선축은 cm→m.

**예시:**
```cpp
// Convert.h
//   mayaToRos: (x, y, z) -> ( x, -z,  y)
//   rosToMaya: (x, y, z) -> ( x,  z, -y)
Vec3 ros = mayaToRosPosition({0, 100, 0}, SceneUnit::cm);   // → (0, 0, 1) m
```

**관련 코드:**
- `src/maro_transform/include/maro_transform/Convert.h:9-18` — 규칙과 시그니처
- `tests/transform/test_convert.cpp` — 왕복 불변식 랜덤 테스트

**증거:**
- §5.1, §11.3

**함정:** 위치는 재배치 하나로 끝나지만 회전축 벡터도 같은 재배치가 필요하다(URDF `<axis>` 버그). 위치만 바꾸고 축을 잊는 것이 가장 흔한 실수다.

**교훈:** 좌표 규약 변환은 한 모듈의 순수 함수로 두고 왕복 불변식으로 지킨다. 그 모듈 밖에서는 변환 코드를 쓰지 않는다.

#### `maro_test_peer` `echo/pub/tf`

**직관:** rclpy와 `ros2` CLI가 없는 환경에서 Maya 발행을 검증하는 rclcpp 상대역 실행 파일. `echo`(joint_states 받기), `pub`(joint_commands 보내기), `tf`(변환 받기) 세 모드다.

**동작:** `echo <robot> <expectedJointCount> <timeoutSec>`는 `/<robot>/joint_states`를 구독해 조인트 수가 기대 이상인 첫 메시지를 `joint <name> = <pos>` 줄로 출력한다 — 테스트가 값을 파싱해 단언한다("뭔가 받았다"가 아니라). `pub`은 `/<robot>/joint_commands`에 JointState를 발행한다. `tf <childFrameId> <timeoutSec>`는 `/tf`에서 해당 프레임을 골라 `translation = x y z` / `rotation = x y z w`로 출력한다. 대기는 `spin_some` + 10ms + `steady_clock` 데드라인. `test_ipc_pipe.cpp`는 레거시(빌드 안 됨)다.

**예시:**
```bash
maro_test_peer echo arm 3 10      # joint shoulder = 0.5236 ...
maro_test_peer tf upper 10        # tf upper translation = 0 0 0.5 / rotation = 0 0 0 1
```

**관련 코드:**
- `tests/peer/maro_test_peer.cpp:25-45` — echo
- `tests/peer/maro_test_peer.cpp:57-95` — tf
- `tests/peer/maro_test_peer.cpp:100-125` — pub
- `tests/maya/test_publish.py:94-101` — Python 테스트가 상대역을 띄우고 파싱

**증거:**
- §8.2, §8.2.7

**함정:** 상대역도 DDS 참가자다. 테스트 밖에서 켜 두면 다른 테스트의 도메인에 끼어든다(RUN_SERIAL의 이유).

**교훈:** 검증 도구가 없으면 최소한의 것을 직접 만든다. 값을 출력하게 만들면 테스트가 그 값을 단언할 수 있다.

#### `/tf` 전역 토픽

**직관:** 상대역의 `tf` 모드에 robotName 인자가 없는 이유 — `/tf`는 로봇 이름으로 네임스페이스되지 않는다. 끼워 넣으면 아무것도 못 받는다.

**동작:** `maro_test_peer tf <childFrameId> <timeoutSec>`는 `"/tf"`를 그대로 구독한다. `MaroRosRuntime::start()`가 `"/tf"`를 그대로 쓰는 관례와 일치하며, 상대역 소스 주석이 이 대칭을 명시한다. 프레임 이름(`child_frame_id`)으로 원하는 링크를 고른다.

**예시:**
```cpp
// maro_test_peer.cpp — "/tf"는 로봇 이름으로 네임스페이스되지 않는다
auto sub = node->create_subscription<tf2_msgs::msg::TFMessage>("/tf", 10, cb);
```

**관련 코드:**
- `tests/peer/maro_test_peer.cpp:57-66` — `"/tf"` 구독과 관례 주석
- `src/maro_plugin/MaroRosRuntime.cpp:57` — 발행 쪽 `"/tf"`

**증거:**
- §8.2, §8.2.7

**함정:** 인자 순서를 `echo`와 같게 착각해 로봇 이름을 첫 인자로 주면 그것이 프레임 이름으로 해석돼 타임아웃한다.

**교훈:** CLI 인자 규칙이 모드마다 다르면 이유를 소스 주석과 사용법 문자열 양쪽에 적는다.

#### 전역 토픽 `/tf`

**직관:** §12.3 계약 표에서 네 토픽 중 유일하게 `/<robotName>/` 접두사가 없는 항목. "전역"은 절대 이름이면서 로봇별 분리를 하지 않는다는 뜻이다.

**동작:** 표: `/<robotName>/joint_states`(enabled ∧ jointName≠""), `/tf`(바인딩만 있으면), `/<robotName>/points`(`updateRate` 스로틀), `/<robotName>/joint_commands`(`controlMode==1` + 델타 체크 + m→cm). 로봇이 둘이면 `/tf`에 두 로봇의 프레임이 함께 실리고 프레임 이름으로 구분된다 — 그래서 링크 이름 유일성이 로봇을 넘어서도 필요하다.

**예시:**
```
/arm/joint_states, /arm/points, /arm/joint_commands   ← arm 전용
/rover/joint_states, ...                               ← rover 전용
/tf                                                    ← 둘 다 여기로, 프레임 이름으로 구분
```

**관련 코드:**
- `src/maro_plugin/MaroRosRuntime.cpp:54-61` — 넷 중 셋만 접두사
- `python/maroUrdfExport.py:820-835` — 링크 이름 유일성 검사

**증거:**
- §12.3, §6.6.4

**함정:** 두 로봇이 같은 링크 이름(`base`)을 쓰면 `/tf`에서 충돌한다. 로봇 이름을 링크 이름에 접두로 넣는 관례를 사용자가 지켜야 한다.

**교훈:** 전역 자원의 이름 공간은 사용자 관례에 기댄다. 그 관례를 문서와 검사기에 적는다.

#### `COLCON_IGNORE`

**직관:** 빈 마커 파일. colcon이 워크스페이스를 훑을 때 이 파일이 있는 디렉터리를 패키지로 취급하지 않게 한다. 이 리포에서는 옛 colcon 시절 트리의 흔적이다.

**동작:** `tests/`, `Maro_DebugUtility/`, `Maro_Management/`에 `COLCON_IGNORE`가 있다. 현재 빌드는 루트 `CMakeLists.txt`가 `add_subdirectory`하는 일곱 디렉터리만이고 colcon은 쓰지 않으므로 이 파일은 기능하지 않는다. 다만 "이 디렉터리가 한때 colcon 워크스페이스 안에 있었다"는 이력의 증거로 남아 §2의 "빌드 밖" 판정에 쓰였다.

**예시:**
```
tests/COLCON_IGNORE               (빈 파일)
Maro_DebugUtility/COLCON_IGNORE   → 레거시 트리, 빌드 밖
```

**관련 코드:**
- `tests/COLCON_IGNORE` — 마커
- `CMakeLists.txt` — 실제 빌드 범위(`add_subdirectory` 목록)

**증거:**
- §2

**함정:** 마커가 있다고 "빌드에서 제외됐다"고 믿으면 안 된다. CMake 빌드는 colcon 마커를 보지 않는다 — 제외 여부는 `add_subdirectory`가 정한다.

**교훈:** 도구별 마커 파일은 그 도구에서만 의미가 있다. 도구를 바꿨으면 마커의 의미도 "이력"으로 격하한다.

#### colcon

**직관:** ROS 2 워크스페이스 빌드 도구 — 패키지 의존 순서로 CMake/ament를 돌린다. Maro는 초기에 colcon으로 플러그인을 빌드했으나 지금은 순수 CMake다.

**동작:** `memo/260526dev.txt`가 colcon 시절 문제 A~E를 기록한다 — Python 버전 충돌(configure 중 PATH 조작), `find_package(Python3 Development)` 실패(수동 include/link), LNK1104(절대 경로 링크), `gtest_discover_tests`, Boost.Interprocess의 관리자 권한 요구. 헤더 끝에 남은 "### 검증 및 빌드 절차 ... colcon build ..." 텍스트는 채팅에서 복사해 넣다 남은 잔재다(F-021). ROS 2 자체는 여전히 colcon으로 소스 빌드했다.

**예시:**
```bash
# ROS 2 소스 빌드(한 번): colcon build --merge-install
# Maro 플러그인(현재):    cmake --preset release && cmake --build out/build --config Release
```

**관련 코드:**
- `memo/260526dev.txt` — colcon 시절 기록
- `package.xml.bak` — ament 매니페스트 잔재
- `CMakeLists.txt` — 현재의 순수 CMake 진입점

**증거:**
- §2, §4.3, §4.3.2, §4.5
- F-021

**함정:** colcon은 ament 매니페스트(`package.xml`)를 요구하고 install 레이아웃을 강제한다. Maya 플러그인처럼 `.mll` 하나를 특정 폴더에 놓는 산출물에는 맞지 않았다.

**교훈:** 생태계의 빌드 도구가 산출물 모양과 맞지 않으면 그 도구를 라이브러리 빌드에만 쓰고 자기 산출물은 직접 만든다.

#### 소스 빌드(from source)

**직관:** 배포 바이너리 대신 소스에서 직접 컴파일. ROS 2 Windows는 공식 바이너리의 컴파일러·CRT가 Maya 플러그인과 일치한다는 보장이 없어, 같은 MSVC로 소스 빌드했다.

**동작:** `ROS2_INSTALL`(기본 `C:/dev/ros2_jazzy/install`)이 CMake 변수로 잡혀 있고 플러그인이 그 트리를 링크한다. 실측으로 소스 빌드 `rclcpp.dll`(28.1.6, 2,714,624 B)과 배포판(같은 28.1.6, 2,541,056 B)은 다른 바이너리였다 — 같은 버전 번호라도 CRT/ABI가 다를 수 있다. 그래서 Release만 존재한다(Debug ROS 2를 따로 빌드하지 않음).

**예시:**
```
ROS2_INSTALL = C:/dev/ros2_jazzy/install   (CMakeLists.txt:24)
rclcpp.dll  소스 빌드 2,714,624 B  vs  배포판 2,541,056 B  ← 같은 28.1.6
```

**관련 코드:**
- `CMakeLists.txt:24` — `ROS2_INSTALL` 기본값
- `src/maro_plugin/CMakeLists.txt:44-56` — install 트리 include/lib
- `python/maroTechDiag.py:542-575` — 로드된 DLL 크기·경로 실측

**증거:**
- §3.1, §3.6

**함정:** 배포판이 PATH 앞에 있으면 빌드는 소스판을 링크했는데 런타임은 배포판을 로드한다. "검증되지 않은 조합"으로 돌면서도 겉으론 동작할 수 있다.

**교훈:** ABI 일치가 필요한 의존성은 같은 컴파일러로 직접 빌드하고, 런타임에 어느 사본이 로드됐는지 진단으로 확인한다.

#### `install/opt/<vendor>/bin`

**직관:** ROS 2 Windows 소스 빌드가 벤더 라이브러리(yaml-cpp, spdlog, console_bridge)를 `install/bin`이 아니라 `install/opt/<vendor>/bin`에 두는 별도 위치. DLL 스테이징이 이 폴더들을 빠뜨리면 로드가 실패한다.

**동작:** 플러그인·상대역의 `POST_BUILD`는 `install/bin/*.dll`에 더해 `opt/libyaml_vendor/bin`, `opt/spdlog_vendor/bin`, `opt/console_bridge_vendor/bin`을 산출 디렉터리로 복사한다(ROS DLL 154개). Maya 로더는 `LOAD_WITH_ALTERED_SEARCH_PATH`를 쓰지 않아 플러그인 옆 DLL을 못 찾으므로 스테이징 폴더가 PATH에 있어야 한다(ctest 주입 / 수동 PATH / `.mod`).

**예시:**
```cmake
add_custom_command(TARGET ${PROJECT_NAME} POST_BUILD
  COMMAND ${CMAKE_COMMAND} -E copy_directory "${ROS2_INSTALL}/opt/libyaml_vendor/bin" "$<TARGET_FILE_DIR:${PROJECT_NAME}>"
  COMMAND ${CMAKE_COMMAND} -E copy_directory "${ROS2_INSTALL}/opt/spdlog_vendor/bin" ...)
```

**관련 코드:**
- `src/maro_plugin/CMakeLists.txt:110-130` — vendor bin 복사와 주석
- `tests/CMakeLists.txt:210-214` — 상대역도 같은 복사

**증거:**
- §3.6

**함정:** `yaml.dll`이 없으면 rcl 파라미터 파싱 초기화에서 죽는데, 오류는 "maro.mll을 로드할 수 없음"뿐이라 원인이 벤더 DLL이라는 걸 알기 어렵다.

**교훈:** 의존성 트리의 "특이한 위치"는 스크립트 주석에 실측 근거와 함께 남긴다.

#### ament

**직관:** ROS 2의 빌드 시스템(CMake 확장 + 패키지 규약). `ament_cmake`가 `package.xml`을 읽고 install 레이아웃·환경 훅을 만든다. Maro 플러그인은 쓰지 않으며 ROS 2 자체를 빌드할 때만 관여했다.

**동작:** ament 패키지는 `package.xml` 매니페스트와 `ament_package()` 호출을 갖고 colcon이 의존 순서로 빌드한다. `package.xml.bak`은 Maro가 ament 패키지였던 시절(`rclcpp`, `std_msgs` 의존)의 잔재다. 현재는 순수 CMake로 install 트리의 헤더·lib를 직접 참조한다.

**예시:**
```xml
<!-- package.xml.bak (레거시) -->
<package format="3"><name>maro</name><depend>rclcpp</depend><depend>std_msgs</depend></package>
```

**관련 코드:**
- `package.xml.bak` — ament 매니페스트 잔재
- `src/maro_plugin/CMakeLists.txt:44-99` — ament 없이 직접 참조

**증거:**
- §4.3, §4.3.9

**함정:** `find_package(rclcpp)`로 ament 타깃을 쓰려면 ament 환경(AMENT_PREFIX_PATH)이 configure 시점에 잡혀 있어야 한다. Maro는 그 대신 절대 경로로 직접 링크해 환경 의존을 없앴다.

**교훈:** 생태계 빌드 시스템의 편의(타깃 자동 해석)와 그 대가(환경 의존)를 저울질한다. 호스트가 다른 곳(Maya)이면 직접 참조가 단순하다.

#### `package.xml`

**직관:** ament 패키지 매니페스트 — 이름·버전·의존성·빌드 타입을 적는 XML. colcon이 이것을 보고 패키지를 인식한다. 리포의 `package.xml.bak`은 옛 시절의 백업이다.

**동작:** 현재 빌드는 매니페스트를 읽지 않는다. `.bak`은 §4.3.9가 "ament 패키지 매니페스트 잔재(`rclcpp`, `std_msgs` 의존)"로 분류했고, `fix_dll.py`·`output.txt`와 함께 루트의 레거시 잔재 목록에 있다. 지우지 않은 이유는 colcon 시절 의존 목록이 곧 초기 설계 기록이기 때문이다.

**예시:**
```
루트 레거시: fix_dll.py, output.txt, package.xml.bak   ← 빌드 밖, 이력 보존
```

**관련 코드:**
- `package.xml.bak` — 잔재

**증거:**
- §4.3, §4.3.9

**함정:** `.bak`을 `package.xml`로 되돌리면 colcon이 이 리포를 패키지로 잡아 다른 워크스페이스 빌드에 끼어든다.

**교훈:** 레거시 파일은 "왜 남겼는가"를 적어 두면 지울지 말지 다음 사람이 판단할 수 있다.

#### nupkg

**직관:** NuGet 패키지 형식(`.nupkg`, 실체는 zip). ROS 2 Windows 의존성 배포가 Chocolatey를 통해 이 형식으로 이뤄지므로, 필요한 DLL 하나를 꺼내기 위해 `.nupkg`를 열었다.

**동작:** URDF 파서(urdfdom)가 쓰는 `tinyxml2.dll`이 소스 빌드 트리에 없어, `ros2/choco-packages` GitHub Releases에서 `tinyxml2.6.0.0.nupkg`를 내려받아 안의 `tinyxml2.dll`을 꺼내 썼다. zip으로 열면 `lib/` 또는 `bin/` 아래 DLL이 있다.

**예시:**
```powershell
Expand-Archive tinyxml2.6.0.0.nupkg -DestinationPath tinyxml2
Copy-Item tinyxml2\bin\tinyxml2.dll <staging>\
```

**관련 코드:**
- `memo/260526dev.txt` — 의존성 해결 기록

**증거:**
- §4.3

**함정:** nupkg 안 DLL은 Chocolatey가 배포하는 특정 MSVC 빌드다. 소스 빌드판과 CRT가 다를 수 있으니 하나만 섞어 넣을 때도 로드 테스트를 한다.

**교훈:** 패키지 형식을 알면 "설치" 없이 파일 하나만 꺼낼 수 있다. 다만 어디서 왔는지 기록한다.

#### choco-packages

**직관:** ROS 2 Windows 설치 안내가 의존하는 Chocolatey 패키지 모음(`ros2/choco-packages` GitHub 저장소). asio, bullet, cunit, eigen, tinyxml2 등을 `.nupkg`로 제공한다.

**동작:** 공식 Windows 설치 절차는 이 릴리스에서 `.nupkg`를 받아 `choco install -s <dir>`로 넣는다. Maro는 Chocolatey 전체 설치 대신 필요한 `tinyxml2.dll` 하나만 `.nupkg`에서 꺼냈다. 소스 빌드 트리에는 vendor 패키지로 대부분이 들어 있어 나머지는 필요 없었다.

**예시:**
```
https://github.com/ros2/choco-packages/releases  →  tinyxml2.6.0.0.nupkg  →  tinyxml2.dll
```

**관련 코드:**
- `memo/260526dev.txt` — 어떤 패키지를 왜 받았는지

**증거:**
- §4.3

**함정:** choco 패키지 버전과 소스 빌드가 기대하는 버전이 다를 수 있다. DLL 이름이 같아도 export가 달라 런타임에 "진입점을 찾을 수 없음"이 난다.

**교훈:** 외부 의존성의 출처 URL과 버전을 메모에 남긴다. 나중에 같은 파일을 다시 구할 수 있어야 한다.

#### `tinyxml2.dll`

**직관:** 경량 XML 파서 라이브러리. urdfdom(URDF 파서)과 `robot_state_publisher`가 이것으로 URDF를 읽는다. Windows 소스 빌드에서 이 DLL이 빠져 별도로 구했다.

**동작:** ROS 2 Windows 빌드는 tinyxml2를 시스템(Chocolatey) 의존으로 가정해 install 트리에 넣지 않는다. Maro는 `ros2/choco-packages`의 `.nupkg`에서 꺼내 스테이징에 두었다. 플러그인 자체는 XML을 Python `ElementTree`로 쓰므로 tinyxml2에 직접 의존하지 않지만, 링크된 ROS 2 DLL 체인이 요구한다.

**예시:**
```
maro.mll → rclcpp.dll → ... → tinyxml2.dll   (체인 어딘가에서 요구; 없으면 로드 실패)
```

**관련 코드:**
- `memo/260526dev.txt` — 해결 기록
- `python/maroTechDiag.py:542-575` — 로드 실패 시 빠진 DLL 진단

**증거:**
- §4.3

**함정:** 빠진 DLL의 이름은 오류 메시지에 나오지 않는다. 의존성 워커(`dumpbin /dependents`)나 진단 패널로 찾아야 한다.

**교훈:** "install 트리에 없는 의존성"의 목록을 문서에 유지한다. 새 머신 셋업의 첫 걸림돌이다.

#### `idl`

**직관:** ROS 2 install 트리의 `include/idl` 디렉터리 — Cyclone DDS의 IDL 컴파일러 헤더가 있는 곳인데, 안에 `string.h` 같은 표준 헤더와 이름이 같은 파일이 있어 include 경로에 넣으면 표준 헤더를 가린다.

**동작:** 플러그인 CMake는 `file(GLOB ... LIST_DIRECTORIES true "${ROS2_INSTALL}/include/*")`로 패키지별 하위 디렉터리를 전부 include 경로에 넣되, 이름이 `idl`·`idlc`이면 제외한다. 안 그러면 `#include <string.h>`가 IDL 헤더로 풀려 컴파일이 이해할 수 없는 오류로 깨진다(F-007). 상대역 CMake도 같은 제외를 한다.

**예시:**
```cmake
foreach(dir ${ROS2_PACKAGE_INCLUDES})
  get_filename_component(name "${dir}" NAME)
  if(NOT name STREQUAL "idl" AND NOT name STREQUAL "idlc")
    list(APPEND INCLUDE_DIRS "${dir}")
  endif()
endforeach()
```

**관련 코드:**
- `src/maro_plugin/CMakeLists.txt:44-54` — 제외 로직과 주석
- `tests/CMakeLists.txt:176` — 상대역의 같은 제외

**증거:**
- §6.0
- F-007

**함정:** 오류가 `string.h` 안의 낯선 심볼에서 나므로 include 경로 순서를 의심하기까지 오래 걸린다. ROS 2 Windows 빌드의 알려진 함정이다.

**교훈:** 글로브로 include 경로를 모을 때는 "무엇을 넣는가"만큼 "무엇을 빼는가"를 명시한다.

#### `idlc` 디렉터리 충돌

**직관:** `idl`과 짝을 이루는 `include/idlc` — 역시 표준 헤더 이름과 충돌하는 파일을 담아 include 경로에서 제외해야 하는 디렉터리.

**동작:** 제외 규칙은 `idl`과 같다. §6.0의 컴파일 정의 `NOMINMAX`(windows.h `min/max`가 rclcpp `numeric_limits`와 충돌), `_SILENCE_CXX17_CODECVT_HEADER_DEPRECATION_WARNING`(ROS 2 헤더의 `<codecvt>`)과 함께 "ROS 2 헤더를 MSVC에서 쓰기 위한 세 가지 손질"을 이룬다. 컨피그마다 `maya-modules/$<CONFIG>` 별도 디렉터리를 쓰는 것도 같은 파일의 이웃 결정이다.

**예시:**
```cmake
target_compile_definitions(${PROJECT_NAME} PRIVATE NOMINMAX _SILENCE_CXX17_CODECVT_HEADER_DEPRECATION_WARNING)
```

**관련 코드:**
- `src/maro_plugin/CMakeLists.txt:44-54` — `idl`/`idlc` 제외
- `src/maro_plugin/CMakeLists.txt:100-108` — 컴파일 정의

**증거:**
- §6.0
- F-007

**함정:** 새 ROS 2 배포판이 비슷한 디렉터리를 추가하면(예: 다른 DDS 벤더) 같은 충돌이 새 이름으로 돌아온다. 제외 목록은 열려 있어야 한다.

**교훈:** 외부 트리의 include를 통째로 넣는 것은 편하지만, 표준 헤더를 가릴 수 있는 디렉터리는 이름으로 걸러야 한다.

#### rosidl typesupport(`*__rosidl_typesupport_cpp`)

**직관:** 메시지 타입별 직렬화 지원 라이브러리. `sensor_msgs__rosidl_typesupport_cpp.lib`처럼 패키지마다 하나씩 있으며, 그 패키지의 메시지를 rmw로 보내고 받기 위해 링크해야 한다.

**동작:** 플러그인은 `rosidl_typesupport_cpp`(공통)와 `sensor_msgs__`, `geometry_msgs__`, `tf2_msgs__`, `builtin_interfaces__`, `statistics_msgs__rosidl_typesupport_cpp`를 절대 경로로 링크한다. 메시지 타입을 하나 더 쓰면 그 패키지의 typesupport도 추가해야 하고, 빠뜨리면 get_message_type_support_handle 미해결 심볼이 링크 단계에서 난다.

**예시:**
```cmake
foreach(ros_lib rclcpp rcl rcutils rcpputils rmw rosidl_runtime_c rosidl_typesupport_cpp
                sensor_msgs__rosidl_typesupport_cpp geometry_msgs__rosidl_typesupport_cpp
                tf2_msgs__rosidl_typesupport_cpp builtin_interfaces__rosidl_typesupport_cpp ...)
```

**관련 코드:**
- `src/maro_plugin/CMakeLists.txt:89-99` — typesupport 링크 목록
- `tests/CMakeLists.txt:187-202` — 상대역의 같은 목록

**증거:**
- §6.0

**함정:** `geometry_msgs`를 직접 쓰지 않아도 `tf2_msgs/TFMessage`가 `TransformStamped`를 담으므로 `geometry_msgs__` typesupport가 필요하다. 메시지의 의존 메시지까지 링크한다.

**교훈:** 메시지 패키지 하나는 lib 하나다. 미해결 심볼의 이름에서 어느 패키지가 빠졌는지 읽어 낸다.

#### `libstatistics_collector`

**직관:** rclcpp의 토픽 통계 기능(`SubscriptionTopicStatistics`)이 끌어오는 라이브러리. 우리가 쓰지 않는 기능인데도 rclcpp 헤더가 참조하므로 링크해야 한다.

**동작:** 브리프의 링크 목록에 없었지만 링크 단계에서 `libstatistics_collector` 미해결 심볼이 났다(F-009). `statistics_msgs__rosidl_typesupport_cpp`와 함께 목록에 추가했고, 상대역 CMake에서도 같은 사건이 반복돼 같은 두 줄을 넣었다. rclcpp 28.x의 구독 템플릿이 통계 수집기를 인스턴스화하기 때문에 구독을 하나라도 만들면 필요하다.

**예시:**
```cmake
# 브리프에 없었지만 rclcpp의 토픽 통계 기능이 끌어와 링크 단계에서
# libstatistics_collector 미해결 심볼로 드러났다.
libstatistics_collector
statistics_msgs__rosidl_typesupport_cpp)
```

**관련 코드:**
- `src/maro_plugin/CMakeLists.txt:95-99` — 추가와 이유 주석
- `tests/CMakeLists.txt:187-202` — 상대역의 같은 추가

**증거:**
- §6.0, §8.1
- F-009

**함정:** "우리는 통계를 안 쓴다"고 빼면 링크가 깨진다. 템플릿 인스턴스화는 사용 여부가 아니라 헤더 참조로 결정된다.

**교훈:** 링크 목록은 "우리가 부르는 것"이 아니라 "헤더가 끌어오는 것"까지다. 미해결 심볼이 목록을 완성해 준다.

#### `statistics_msgs`

**직관:** 토픽 통계 메시지 패키지(MetricsMessage 등). `libstatistics_collector`의 짝으로, 그 typesupport(`statistics_msgs__rosidl_typesupport_cpp`)를 함께 링크해야 한다.

**동작:** `libstatistics_collector`가 `statistics_msgs` 메시지를 발행하므로 그 typesupport가 없으면 다시 미해결 심볼이 난다. 플러그인과 상대역 모두 두 라이브러리를 나란히 링크한다. Maro는 통계 토픽을 켜지 않으므로 런타임에 MetricsMessage가 발행되지는 않는다.

**예시:**
```
링크 짝: libstatistics_collector.lib + statistics_msgs__rosidl_typesupport_cpp.lib
```

**관련 코드:**
- `src/maro_plugin/CMakeLists.txt:98-99` — 두 줄
- `tests/CMakeLists.txt:187-202` — 상대역

**증거:**
- §6.0, §8.1
- F-009

**함정:** 하나만 추가하면 미해결 심볼이 다른 이름으로 다시 난다. 둘은 세트다.

**교훈:** 의존성이 한 층 더 끌어오는 의존성을 "짝"으로 기록해 두면 다음 빌드 스크립트에서 한 번에 넣는다.

#### `install/bin` + `opt/<vendor>/bin`

**직관:** ROS 2 런타임 DLL이 놓이는 두 위치의 합. `install/bin`에 rcl·rclcpp·rmw·메시지 DLL이, `install/opt/<vendor>/bin`에 yaml-cpp·spdlog·console_bridge가 있다. 스테이징은 둘을 합쳐야 완전하다.

**동작:** §10.11 규칙: DLL 스테이징은 `install/bin/*.dll` **과** `opt/libyaml_vendor/bin`, `opt/spdlog_vendor/bin`, `opt/console_bridge_vendor/bin`을 모두 복사한다. 결과는 ROS DLL 154개 + `embree4.dll` + `.py` 사본이 `.mll` 옆에 놓이고, `.mod`의 `PATH +:= .`가 그 폴더를 PATH에 붙인다 — 단, 영구 PATH의 배포판이 앞서면 스테이징이 무시된다는 실측(§3.6)이 있다.

**예시:**
```
out/build/Release/maya-modules/Release/
├─ maro.mll
├─ rclcpp.dll, rcl.dll, rmw_*.dll, sensor_msgs__*.dll ...   ← install/bin
├─ yaml.dll, spdlog.dll, console_bridge.dll                ← install/opt/<vendor>/bin
└─ embree4.dll, maro*.py
```

**관련 코드:**
- `src/maro_plugin/CMakeLists.txt:110-130` — 두 위치 복사
- `python/maroTechDiag.py:542-575` — 실제 로드 경로 진단

**증거:**
- §10.11, §3.6

**함정:** 벤더 DLL을 빠뜨린 스테이징은 "가끔" 된다 — PATH 어딘가에 같은 이름의 다른 DLL이 있으면 그것이 로드돼 버전 불일치로 미묘하게 깨진다.

**교훈:** 스테이징 목록은 "install 트리 전체를 아는 사람"이 한 번 정하고 규칙(§10.11)으로 고정한다.
