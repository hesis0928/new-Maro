<!-- ros-rclcpp-01 ROS 2 › rclcpp·클라이언트 계층 (15개) 2026-09-17 -->

#### rclcpp

**직관:** ROS 2의 C++ 클라이언트 라이브러리 — 노드·퍼블리셔·구독·executor·Context가 전부 여기 있다. Maro는 별도 브리지 프로세스가 아니라 `maro.mll` 안에 rclcpp를 직접 링크해 Maya 프로세스 자체가 ROS 노드가 된다.

**동작:** 발행 방향은 `MaroRosRuntime`이 자기 노드를 만들어 `JointState`·`TFMessage`·`PointCloud2` 퍼블리셔 3개를 갖고 백그라운드 스레드에서 `publish()`한다. 수신 방향은 `MaroCommandDeviceNode`가 Maya 워커 스레드에서 구독 노드와 `SingleThreadedExecutor`를 돌린다. 둘 다 전역 `rclcpp::init` 대신 Maro 소유 `rclcpp::Context`에 매달린다. rmw/DDS 계층이 발견·전송을 맡고, `ROS_DOMAIN_ID` 같은 환경변수는 Context 초기화 시점에 읽힌다.

**예시:**
```cpp
auto ctx = maro::rosContext();
auto node = rclcpp::Node::make_shared(robotName, rclcpp::NodeOptions().context(ctx));
auto pub = node->create_publisher<sensor_msgs::msg::JointState>("/" + robotName + "/joint_states", 10);
pub->publish(msg);   // 퍼블리셔만이면 spin 없이 바로 나간다
```

**관련 코드:**
- `src/maro_plugin/MaroRosRuntime.cpp:40-60` — 노드·퍼블리셔 3개 생성
- `src/maro_plugin/MaroCommandDeviceNode.cpp:348-430` — 구독 노드와 executor
- `src/maro_plugin/MaroRosContext.cpp:29-78` — Maro 소유 Context
- `src/maro_plugin/CMakeLists.txt` — rclcpp·메시지 패키지 링크

**증거:**
- §1.1, §11.3, §10.1

**함정:** Maya는 플러그인이 여럿 사는 프로세스다. rclcpp를 "프로세스에 하나"로 여기고 전역 init/shutdown을 쓰면 같은 Maya의 다른 ROS 플러그인과 서로의 컨텍스트를 끊는다.

**교훈:** 라이브러리를 호스트 프로세스 안에 링크하면 "프로세스 전역"을 건드리는 API는 모두 의심한다. rclcpp는 Context를 값으로 다루는 길을 열어 두었고, Maro는 그 길만 쓴다.

#### `rclcpp::Context`

**직관:** rclcpp의 초기화 단위이자 노드·퍼블리셔·executor·가드 컨디션이 매달리는 공유 상태. Maro는 전역 컨텍스트 대신 "우리 것" 하나를 만들어 다른 rclcpp 사용자와 격리한다.

**동작:** `rclcpp::init(argc, argv)`는 프로세스 전역 기본 컨텍스트를 초기화하고 SIGINT 핸들러까지 설치하지만, `std::make_shared<rclcpp::Context>()` 뒤 `Context::init()`은 핸들러를 설치하지 않는다. `MaroRosContext.cpp`의 `rosContext()`는 뮤텍스 아래 저장된 컨텍스트가 유효하면 돌려주고, 아니면 새로 만들어 `init(0, nullptr, InitOptions())`한다. `rclcpp::ok(ctx)`/`ctx->shutdown()`도 컨텍스트 단위다. 발행·수신 두 방향이 같은 컨텍스트를 공유하며, 파생 엔티티가 살아 있는 채 컨텍스트를 부수면 UB이므로 종료 순서(수신 스레드 정지 → 퍼블리셔 → 노드 → 컨텍스트)가 정해져 있다.

**예시:**
```cpp
std::shared_ptr<rclcpp::Context> rosContext() {
    std::lock_guard<std::mutex> lock(contextMutex());
    auto& ctx = storage();
    if (ctx && ctx->is_valid()) return ctx;
    auto fresh = std::make_shared<rclcpp::Context>();
    fresh->init(0, nullptr, rclcpp::InitOptions());
    return ctx = fresh;
}
```

**관련 코드:**
- `src/maro_plugin/MaroRosContext.cpp:29-47` — 지연 생성과 유효성 검사
- `src/maro_plugin/MaroRosContext.h` — 왜 전역 init을 안 쓰는지 적은 헤더 주석
- `src/maro_plugin/MaroRosRuntime.cpp:90-112` — 퍼블리셔→노드→컨텍스트 순 정리

**증거:**
- §1.4, §6.6, §6.6.3
- F-087

**함정:** 한 번 shutdown된 Context는 되살릴 수 없다. 옛 코드의 `if (!rclcpp::ok()) rclcpp::init()` 같은 "재초기화"는 전역 컨텍스트를 건드려 다른 사용자와 충돌했고, 자기 컨텍스트라도 재연결은 새 객체로 해야 한다.

**교훈:** 공유 상태의 소유자를 분명히 하라. "누가 만들고 누가 끝내는가"가 정해지면 다른 플러그인과의 공존은 따라온다.

#### `SingleThreadedExecutor`

**직관:** 구독 콜백을 "지금 이 스레드에서" 처리해 주는 가장 단순한 rclcpp 실행기. 노드를 붙이고 `spin_some()`을 부르면 대기 중인 콜백이 호출자 스레드에서 동기적으로 돈다.

**동작:** `MaroCommandDeviceNode::threadHandler`는 Maya 워커 스레드 시작 시 `ExecutorOptions.context = rosCtx`로 executor 하나를 만들고 `add_node(node)`한 뒤 루프에서 `spin_some()`을 반복한다. 구독 콜백은 이 스레드 위에서 불리므로 콜백 안에서 Maya API를 부르지 않고 메모리 풀에 레코드만 쌓는다. 스레드가 끝날 때 `remove_node`. executor 생성은 rcl wait set·가드 컨디션 할당을 동반하므로 스레드 수명 동안 하나만 만든다.

**예시:**
```cpp
rclcpp::ExecutorOptions opts; opts.context = rosCtx;
rclcpp::executors::SingleThreadedExecutor executor(opts);
executor.add_node(node);
while (running) { executor.spin_some(); /* 콜백은 여기서 동기 호출 */ }
executor.remove_node(node);
```

**관련 코드:**
- `src/maro_plugin/MaroCommandDeviceNode.cpp:348-360` — 옵션과 executor 생성
- `src/maro_plugin/MaroCommandDeviceNode.cpp:388-430` — add_node / spin_some 루프 / remove_node

**증거:**
- §1.4, §6.6.5

**함정:** 콜백이 호출자 스레드에서 돈다는 것은 콜백이 느리면 `spin_some()`이 그만큼 막힌다는 뜻이다. 콜백은 복사·큐잉만 하고 무거운 일은 밖에서 한다.

**교훈:** 실행기의 종류는 "콜백이 어느 스레드에서 도는가"의 선언이다. 단일 스레드 실행기를 고르면 스레드 안전 문제는 콜백 밖으로 밀려난다.

#### `spin_some`

**직관:** "지금 도착해 있는 것만 처리하고 바로 돌아와라". `spin()`처럼 영원히 기다리지 않으므로 루프 안에서 다른 조건(정지 요청·컨텍스트 유효성)과 섞어 쓸 수 있다.

**동작:** executor 멤버 `spin_some()`은 wait set을 한 번 훑어 준비된 콜백을 모두 실행하고 반환한다. 수신 노드는 `while (!stop && rosContextOk()) executor.spin_some();` 패턴으로 Maya의 정지 신호와 컨텍스트 종료 양쪽에 반응한다. 발행 전용 노드(`MaroRosRuntime`)는 콜백이 없으니 `spin_some`을 아예 부르지 않는다 — `publish()`는 spin 없이 바로 나간다. 테스트 상대역(`maro_test_peer`)은 `spin_some` + 10ms sleep + `steady_clock` 데드라인으로 결정적 대기를 만든다.

**예시:**
```cpp
while (rclcpp::ok() && !satisfied && std::chrono::steady_clock::now() < deadline) {
    rclcpp::spin_some(node);
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
}
```

**관련 코드:**
- `src/maro_plugin/MaroCommandDeviceNode.cpp:403` — 수신 루프의 spin_some
- `src/maro_plugin/MaroRosRuntime.cpp:124-130` — 퍼블리셔 전용이라 spin_some 불필요 주석
- `tests/peer/maro_test_peer.cpp:38-45` — 데드라인 폴링

**증거:**
- §1.4, §6.6.4, §6.6.5

**함정:** 자유 함수 `rclcpp::spin_some(node)`는 호출마다 executor를 새로 만든다. 프레임 레이트로 부르는 루프에서는 멤버 `spin_some()`을 써야 한다(M12).

**교훈:** "한 번만 처리하고 반환"하는 API는 루프의 주도권을 호출자에게 준다. 종료 조건을 우리가 쥐어야 하는 곳에서는 항상 이런 형태를 고른다.

#### `NodeOptions::context()`

**직관:** 노드를 만들 때 "이 컨텍스트에 매달려라"를 지정하는 옵션. 이것을 넘기지 않으면 노드는 전역 기본 컨텍스트에 붙어 Maro의 격리가 깨진다.

**동작:** `rclcpp::Node::make_shared(name, rclcpp::NodeOptions().context(ctx))`로 노드를 만들면 그 노드의 퍼블리셔·구독·타이머가 모두 `ctx`에 매달린다. 발행 노드(`MaroRosRuntime`)와 수신 노드(`MaroCommandDeviceNode`)가 같은 `maro::rosContext()`를 넘겨 두 방향이 한 컨텍스트를 공유한다. `shutdownRosContext()`가 그 컨텍스트만 끝내므로 같은 프로세스의 다른 rclcpp 노드는 영향을 받지 않는다.

**예시:**
```cpp
auto context = maro::rosContext();
m_impl->node = rclcpp::Node::make_shared(robotName, rclcpp::NodeOptions().context(context));
```

**관련 코드:**
- `src/maro_plugin/MaroRosRuntime.cpp:42-46` — 발행 노드
- `src/maro_plugin/MaroCommandDeviceNode.cpp:369` — 수신 노드 `robotName + "_cmd_rx"`

**증거:**
- §6.6, §6.6.3
- F-087

**함정:** 노드에는 컨텍스트를 넘겼는데 executor에는 안 넘기면(`ExecutorOptions.context` 누락) executor만 전역에 매달려 우리 컨텍스트가 끝나도 `spin_some()`이 모른다. 둘은 짝이다.

**교훈:** 격리는 "만드는 모든 것"에 일관되게 적용해야 한다. 한 군데만 기본값을 쓰면 격리가 조용히 새어 나간다.

#### `ExecutorOptions::context`

**직관:** executor가 어느 컨텍스트의 종료를 감시할지 정하는 옵션. 노드의 `NodeOptions::context()`와 반드시 같은 컨텍스트를 준다.

**동작:** `rclcpp::ExecutorOptions executorOptions; executorOptions.context = rosCtx;`로 만든 executor는 그 컨텍스트가 shutdown되면 `spin_some()`이 즉시 반환하거나 예외로 알린다. 지정하지 않으면 전역 기본 컨텍스트에 매달려 Maro 컨텍스트가 끝나도 계속 spin을 시도하고, 살아 있는 노드가 없는 컨텍스트 밑에서 UB로 간다. 수신 스레드의 executor는 이 옵션으로 만들어진다.

**예시:**
```cpp
auto rosCtx = maro::rosContext();
rclcpp::ExecutorOptions executorOptions;
executorOptions.context = rosCtx;      // 안 넘기면 전역 컨텍스트에 매달린다
rclcpp::executors::SingleThreadedExecutor executor(executorOptions);
```

**관련 코드:**
- `src/maro_plugin/MaroCommandDeviceNode.cpp:353-360` — 옵션 설정과 그 이유 주석

**증거:**
- §6.6, §6.6.3, §6.6.5

**함정:** 이 옵션은 컴파일러도 rclcpp도 강제하지 않는다. 빠뜨려도 평소엔 잘 돌고, 언로드·재연결 때만 이상해져서 원인을 찾기 어렵다.

**교훈:** "선택적 옵션"이 사실은 필수인 경우가 있다. 격리 설계라면 옵션을 넘기는 코드에 왜 필수인지 주석을 남긴다.

#### `Context::init(0, nullptr, InitOptions())`

**직관:** 명령줄 인자 없이 컨텍스트를 초기화한다. Maya의 argv는 ROS 인자가 아니므로 넘길 것이 없고, 환경변수(`ROS_DOMAIN_ID` 등)는 이 호출에서 읽힌다.

**동작:** `rosContext()`가 새 컨텍스트를 만들면 `fresh->init(0, nullptr, rclcpp::InitOptions())`을 부른다. 이 시점에 rcl이 환경을 읽어 도메인·rmw 구현을 정하므로, 설정 패널에서 도메인 ID를 바꾸면 브리지를 내렸다 올려 컨텍스트를 새로 만들어야 반영된다. `InitOptions` 기본값은 시그널 핸들러를 설치하지 않는다.

**예시:**
```cpp
auto fresh = std::make_shared<rclcpp::Context>();
// 인자를 넘기지 않는다 -- Maya의 argv는 ROS 인자가 아니다.
fresh->init(0, nullptr, rclcpp::InitOptions());
```

**관련 코드:**
- `src/maro_plugin/MaroRosContext.cpp:35-41` — init 호출과 환경변수 주석
- `python/maroSettingsPanel.py:27-30` — 도메인 ID 변경이 재연결을 요구하는 이유

**증거:**
- §6.6, §6.6.3

**함정:** 컨텍스트가 이미 살아 있을 때 환경변수를 바꿔도 아무 일도 안 일어난다. "설정을 바꿨는데 안 먹는다"의 원인은 대개 init 시점이 지났기 때문이다.

**교훈:** 초기화가 환경을 읽는 시점을 알아 두면 "언제 재시작해야 하는가"가 명확해진다. 그 사실을 설정 UI 주석에 적어 둔다.

#### `shutdown()` 비가역

**직관:** 컨텍스트는 한 번 끝내면 되살릴 수 없다. 재연결은 "다시 init"이 아니라 "새 컨텍스트"다.

**동작:** `ctx->shutdown(reason)` 뒤 `is_valid()`는 영원히 false다. `rosContext()`는 저장된 컨텍스트가 무효면 새로 만들어 돌려주므로, `shutdownRosContext()` 뒤 다시 `rosContext()`를 부르면 자연스럽게 새 컨텍스트가 생긴다. 옛 코드는 `if (!rclcpp::ok()) rclcpp::init()`으로 전역 컨텍스트를 재초기화했는데, 이는 같은 프로세스의 다른 rclcpp 사용자와 정면 충돌했다.

**예시:**
```cpp
maro::shutdownRosContext("Maro bridge stopped");   // 이 컨텍스트는 끝
auto again = maro::rosContext();                    // 새 객체가 온다
```

**관련 코드:**
- `src/maro_plugin/MaroRosContext.cpp:16-18` — "세션 하나에 컨텍스트 하나" 주석
- `src/maro_plugin/MaroRosContext.cpp:29-34` — 무효면 새로 만드는 분기

**증거:**
- §6.6, §6.6.3

**함정:** 옛 컨텍스트의 `shared_ptr`을 노드·퍼블리셔가 붙들고 있으면 새 컨텍스트를 만들어도 그것들은 죽은 컨텍스트에 매달린 채다. 재연결 전에 파생 엔티티를 전부 reset해야 한다.

**교훈:** 비가역 상태 전이는 "재사용"이 아니라 "재생성"으로 설계한다. 지연 생성 함수 하나가 그 규칙을 캡슐화한다.

#### 락 밖 shutdown

**직관:** 컨텍스트를 저장소에서 꺼내는 것은 뮤텍스 안에서, 실제 `shutdown()` 호출은 뮤텍스 밖에서. shutdown이 촉발하는 정리 코드가 같은 뮤텍스를 다시 잡으려 하면 교착하기 때문이다.

**동작:** `shutdownRosContext()`는 락 아래에서 `storage()`의 포인터를 지역 변수로 옮기고 저장소를 비운 뒤, 락을 놓고 나서 `ctx->shutdown(reason)`을 부른다. shutdown은 컨텍스트에 매달린 가드 컨디션·executor의 정리를 유발하고, 그 경로에서 `rosContextOk()`(같은 뮤텍스를 잡음)를 부르는 코드가 있으면 락 안에서 shutdown할 경우 자기 자신을 기다리는 교착이 된다.

**예시:**
```cpp
std::shared_ptr<rclcpp::Context> ctx;
{
    std::lock_guard<std::mutex> lock(contextMutex());
    ctx = storage();
    storage().reset();
}
if (ctx && ctx->is_valid()) ctx->shutdown(reason);   // 락 밖
```

**관련 코드:**
- `src/maro_plugin/MaroRosContext.cpp:59-75` — 락 범위와 그 이유 주석

**증거:**
- §6.6, §6.6.3
- F-088

**함정:** "락 안에서 끝내야 원자적이지 않나"라는 직관이 함정이다. 저장소 갱신만 원자적이면 되고, 외부 콜백을 부를 수 있는 호출은 락 밖이어야 한다.

**교훈:** 뮤텍스 아래에서는 "내 코드"만 부른다. 콜백을 유발할 수 있는 라이브러리 호출은 락을 놓고 한다.

#### 퍼블리셔→노드→컨텍스트 순 `reset`

**직관:** 정리는 만든 순서의 역순 — 퍼블리셔를 먼저, 노드를 그 다음, 컨텍스트를 마지막에 놓는다. 이 순서를 어겼을 때 DDS 참가자가 살아남아 Maya가 30초 넘게 안 끝나는 결함이 있었다.

**동작:** `MaroRosRuntime::stop()`은 발행 스레드를 join한 뒤 `lidarPub.reset(); tfPub.reset(); jointPub.reset(); node.reset();` 순으로 놓고 마지막에 `shutdownRosContext()`와 `context.reset()`을 한다. 퍼블리셔가 노드보다 오래 살면 노드의 DDS 참가자가 해제되지 못해 프로세스 종료가 막힌다. 수신 쪽 `MaroCommandDeviceNode`도 같은 컨텍스트를 쓰므로 그 스레드가 완전히 멈춘 뒤에만 이 정리에 들어와야 하며, 순서 보장은 호출자 `shutdownBridge()`의 몫이다.

**예시:**
```cpp
m_impl->lidarPub.reset();
m_impl->tfPub.reset();
m_impl->jointPub.reset();
m_impl->node.reset();
maro::shutdownRosContext("Maro bridge stopped");
m_impl->context.reset();
```

**관련 코드:**
- `src/maro_plugin/MaroRosRuntime.cpp:90-112` — 역순 reset과 30초 결함 주석
- `src/maro_plugin/MaroCommands.cpp:479` — 수신 정지 → 발행 정지 순서를 지키는 `shutdownBridge`

**증거:**
- §6.6, §6.6.4

**함정:** `shared_ptr` 멤버는 소멸자에서 선언 역순으로 자동 해제되므로 "알아서 되겠지" 싶지만, 스레드 join과 컨텍스트 shutdown이 중간에 끼면 자동 순서로는 부족하다. 명시적으로 reset한다.

**교훈:** 리소스 정리 순서가 곧 정확성인 경우엔 RAII에만 맡기지 말고 순서를 코드로 적는다. 그리고 왜 그 순서인지 주석에 결함 이력을 남긴다.

#### `spin_some()` 불필요(퍼블리셔 전용)

**직관:** 콜백이 없는 노드는 executor가 필요 없다. `publish()`는 spin과 무관하게 즉시 DDS로 나간다.

**동작:** `MaroRosRuntime`의 노드는 퍼블리셔 3개만 갖고 구독이 없다. 그래서 `spinLoop()`는 `while (!stop && rosContextOk()) drainAndPublish();`만 반복하고 `rclcpp::spin_some()`을 부르지 않는다. 구독은 `MaroCommandDeviceNode`의 별도 노드가 자기 executor로 처리한다. 노드 생성이 실패하면 퍼블리셔·노드를 전부 reset하고 false를 돌려 예외가 Maya 쪽으로 새지 않게 한다.

**예시:**
```cpp
while (!m_stopRequested.load() && maro::rosContextOk()) {
    try { drainAndPublish(); }      // publish()는 spin 없이 바로 나간다
    catch (...) { /* 이 틱만 건너뛴다 */ }
}
```

**관련 코드:**
- `src/maro_plugin/MaroRosRuntime.cpp:115-135` — spinLoop와 "spin_some을 부를 필요가 없다" 주석
- `src/maro_plugin/MaroRosRuntime.cpp:60-80` — 실패 시 reset·false, 성공 시 스레드 시작

**증거:**
- §6.6, §6.6.4

**함정:** 퍼블리셔 전용 노드에도 서비스·파라미터 콜백이 붙으면 그때부터는 spin이 필요하다. 지금 필요 없다는 것은 "구독이 없어서"이지 "발행 노드라서"가 아니다.

**교훈:** executor는 콜백을 위한 것이다. 콜백이 없으면 만들지 않는 것이 비용도 복잡도도 줄인다.

#### `SingleThreadedExecutor` 재사용

**직관:** executor는 스레드가 시작할 때 하나 만들고, 스레드가 끝날 때까지 그것만 쓴다. 매 틱 새로 만들면 wait set·가드 컨디션 할당이 프레임 레이트로 반복된다(M12).

**동작:** `threadHandler`는 executor를 지역 객체로 한 번 만들고 `add_node` 뒤 루프에서 멤버 `spin_some()`만 부른다. 종료 시 `remove_node`하고 지역 객체가 소멸한다. 자유 함수 `rclcpp::spin_some(node)`는 내부에서 `SingleThreadedExecutor`를 만들고 `add_node → spin_some → 소멸`을 매번 반복하므로 `frameRate` Hz 루프에서는 쓰지 않는다.

**예시:**
```cpp
rclcpp::executors::SingleThreadedExecutor executor(executorOptions);   // 스레드당 하나
executor.add_node(node);
while (running) executor.spin_some();
executor.remove_node(node);
```

**관련 코드:**
- `src/maro_plugin/MaroCommandDeviceNode.cpp:348-360` — M12 주석과 생성
- `src/maro_plugin/MaroCommandDeviceNode.cpp:388-430` — 루프와 remove_node

**증거:**
- §6.6, §6.6.5

**함정:** executor를 함수 밖 static이나 멤버로 올리면 소멸 시점이 `.mll` 언로드 이후로 밀려 rcl이 이미 내려간 뒤 소멸자가 돈다. 스레드 함수의 지역 객체가 수명이 가장 명확하다.

**교훈:** 비싼 객체는 "루프 밖에서 한 번". 그리고 그 객체의 수명은 그것을 쓰는 스레드의 수명과 같게 둔다.

#### `spin_some(node)` 자유 함수 비용

**직관:** 편의 함수 한 줄 뒤에 executor 생성·wait set 할당·가드 컨디션 생성·소멸이 숨어 있다. 한 번 부르는 스크립트엔 괜찮지만 프레임마다 부르는 루프엔 부적절하다.

**동작:** `rclcpp::spin_some(node_ptr)`의 구현은 `SingleThreadedExecutor exec; exec.add_node(node); exec.spin_some(); exec.remove_node(node);`다. executor 생성은 rcl wait set과 인터럽트 가드 컨디션을 할당하고, 소멸은 그것을 해제한다. 수신 노드가 `frameRate` Hz로 이것을 불렀다면 초당 수십 번 할당/해제가 반복됐을 것이고, M12 리뷰에서 멤버 executor 재사용으로 바꿨다. 테스트 상대역(`maro_test_peer`)은 한 번 기다리는 용도라 자유 함수를 그대로 쓴다.

**예시:**
```cpp
// 매 틱 이렇게 부르면 executor를 매번 만든다
rclcpp::spin_some(node);
// 대신: 스레드당 executor 하나를 만들어 executor.spin_some()
```

**관련 코드:**
- `src/maro_plugin/MaroCommandDeviceNode.cpp:348-351` — 자유 함수의 비용을 적은 M12 주석
- `tests/peer/maro_test_peer.cpp:43` — 일회성 대기라 자유 함수를 쓰는 곳

**증거:**
- §6.6, §6.6.5

**함정:** 편의 함수는 "무엇을 하는가"만 보이고 "무엇을 만드는가"는 숨긴다. 핫 루프에 들어가는 호출은 구현을 한 번 열어 본다.

**교훈:** 라이브러리의 편의 API는 일회성 사용을 가정한다. 반복 호출 경로에서는 그 안의 객체를 밖으로 꺼내 재사용한다.

#### `spin_some`+`steady_clock`

**직관:** 테스트 상대역이 "메시지가 올 때까지, 단 N초까지만" 기다리는 방법 — `spin_some`으로 콜백을 돌리고 10ms 쉬고, `steady_clock` 데드라인으로 끊는다. `ros2 topic echo` 같은 CLI보다 결정적이다.

**동작:** `maro_test_peer`는 구독 콜백이 `satisfied = true`를 세우게 하고, `while (ok && !satisfied && now < deadline) { spin_some(node); sleep_for(10ms); }`로 폴링한다. 데드라인은 `steady_clock::now() + timeoutSec`로 계산하므로 벽시계 변경에 영향받지 않는다. 대기와 타임아웃을 테스트 코드가 직접 통제하니 실패 시 "몇 초 안에 안 왔다"가 명확히 남는다.

**예시:**
```cpp
const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(int(timeoutSec * 1000));
while (rclcpp::ok() && !satisfied && std::chrono::steady_clock::now() < deadline) {
    rclcpp::spin_some(node);
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
}
```

**관련 코드:**
- `tests/peer/maro_test_peer.cpp:38-45` — joint_states 대기 루프
- `tests/peer/maro_test_peer.cpp:87-95` — 두 번째 토픽의 같은 패턴
- `tests/maya/test_publish.py:94-101` — 상대역을 띄우고 결과를 읽는 Python 쪽

**증거:**
- §8.2, §8.2.7

**함정:** `system_clock`으로 데드라인을 잡으면 CI 머신의 시간 동기화가 끼어들어 타임아웃이 튄다. 경과 시간 측정은 항상 `steady_clock`.

**교훈:** 비동기 시스템의 테스트는 "기다림"을 코드로 소유해야 한다. 폴링+데드라인은 단순하지만 결정적이다.

#### ROS 2 계층(rmw/DDS → rcl → rclcpp/rclpy → 메시지 패키지 → 도구)

**직관:** ROS 2는 아래부터 미들웨어 추상화(rmw)와 DDS 구현, C 클라이언트(rcl), C++/Python 클라이언트(rclcpp/rclpy), 그 위에 `sensor_msgs` 같은 메시지 패키지, 맨 위에 `ros2` CLI·RViz 같은 도구가 쌓인다. Maro는 rclcpp 층에 붙고 메시지 패키지를 링크하며, 도구 층은 검증에 쓴다.

**동작:** 발견·전송은 rmw 아래 DDS(Fast DDS 등)가 하고 `ROS_DOMAIN_ID`로 격리된다. rcl이 컨텍스트·노드·wait set을 C로 제공하고, rclcpp가 그것을 `Context`·`Node`·`Executor`로 감싼다. `sensor_msgs::msg::JointState`·`PointCloud2`·`tf2_msgs::msg::TFMessage`는 rosidl이 생성한 C++ 구조체다. Maro는 이 스택을 소스 빌드한 ROS 2 Jazzy(같은 MSVC)에서 가져와 `.mll`에 링크하고, 스테이징으로 DLL을 함께 배포한다. 검증은 `maro_test_peer`(rclcpp)와 `ros2 topic`·RViz(도구 층)로 한다.

**예시:**
```
도구:      ros2 topic echo /arm/joint_states, RViz, robot_state_publisher
메시지:    sensor_msgs/JointState, PointCloud2, tf2_msgs/TFMessage
클라이언트: rclcpp (Maro가 링크) / rclpy
C 계층:    rcl
미들웨어:  rmw → Fast DDS (ROS_DOMAIN_ID로 격리)
```

**관련 코드:**
- `src/maro_plugin/CMakeLists.txt` — 링크하는 패키지 목록
- `src/maro_plugin/MaroRosRuntime.cpp:40-60` — 메시지 타입 3종 퍼블리셔
- `tests/peer/maro_test_peer.cpp` — 도구 대신 쓰는 rclcpp 상대역

**증거:**
- §11.3, §1.1

**함정:** 층마다 바이너리 호환 조건이 다르다. rclcpp를 MSVC로 빌드했다면 rmw·DDS·메시지 패키지도 같은 컴파일러 산출물이어야 하고, 바이너리 배포판과 섞으면 링크는 되어도 런타임에 죽는다.

**교훈:** 스택을 층으로 이해하면 "어디를 링크하고 어디를 도구로 쓰는가"가 정해진다. Maro는 rclcpp 층 하나에만 결합하고, 그 위아래는 계약으로 다룬다.
