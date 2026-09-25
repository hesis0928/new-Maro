<!-- proc-test-01 개발 프로세스 › 테스트 설계·변이 검증 1/2 (22개) 2026-09-24 -->

#### `resetForTest()` 전부 리셋

**직관:** 테스트 사이에 진단 서브시스템의 상태를 초기화하는 훅. "전부"가 핵심이다 — 반쪽만 리셋해 두 번 퇴행한 기록이 있다.

**동작:** `BoadMaro::resetForTest()`가 스트림·순번·캐시·카운터·래치·저널 writer·crashAdjacency·스택 트레이스 래치를 **전부** 되돌린다. 이름이 "테스트 전용 리셋 훅"이므로 일부만 되돌리면 이름이 거짓말이 된다. 새 상태(래치·카운터)를 추가할 때마다 이 함수에 줄을 추가하는 것이 규율이다.

**예시:**
```cpp
void BoadMaro::resetForTest() {
    // 스트림·순번·캐시·카운터·래치·저널 writer·crashAdjacency·스택 래치 전부
}
```

**관련 코드:**
- `src/maro_plugin/MaroDiag.cpp:705-740` — 리셋 본체와 주석

**증거:**
- §6.7, §6.7.1

**함정:** 리셋을 빠뜨린 상태가 남으면 테스트 순서에 따라 결과가 달라진다 — 단독 실행은 통과하고 전체 실행은 실패한다.

**교훈:** 상태를 추가하면 리셋도 추가한다. 그 짝을 강제하는 것은 이름과 리뷰뿐이다.

#### 178→184 어트리뷰트 프로브

**직관:** 노드 타입의 어트리뷰트 짧은 이름 충돌을 "추측이 아니라 실측으로" 확인하는 방법. 상속 계층 전체의 이름을 전수 나열한다.

**동작:** 어트리뷰트 이름 공간은 상속 계층(`MPxLocatorNode`→`MPxSurfaceShape`→…→`dagNode`→`dependNode`) 전체를 공유하므로 `create("visualize", "vis", …)`는 성공해도 `addAttribute`가 충돌로 실패할 수 있다(F-025). 그래서 mayapy 프로브로 상속 포함 178개 어트리뷰트의 짧은 이름을 나열해 충돌이 없음을 확인하고, 6개를 추가한 뒤 총수가 178→184가 되는지 재확인한다.

**예시:**
```python
attrs = cmds.attributeInfo("maroLidar1", allAttributes=True)   # 상속 포함
short = [cmds.attributeQuery(a, node="maroLidar1", shortName=True) for a in attrs]
assert len(short) == 184 and len(set(short)) == 184
```

**관련 코드:**
- `tests/maya/test_lidar_node.py` — 전수 프로브
- `src/maro_plugin/MaroLidarNode.cpp:110-112` — `"vis"`→`"lvp"` 회피

**증거:**
- §6.8, §6.8.1
- F-025

**함정:** 짧은 이름 충돌은 노드 등록 시점에 실패해 "플러그인이 안 뜬다"로만 보인다. 어느 이름인지 메시지가 알려 주지 않는다.

**교훈:** 이름 공간이 상속을 타는 API는 전수 나열로 확인한다. 세 글자 약어는 특히 겹치기 쉽다.

#### `TIMEOUT 240/360`

**직관:** ctest 테스트의 시간 상한. Maya를 띄우는 테스트는 240초, 상대역까지 필요한 테스트는 360초다.

**동작:** `tests/CMakeLists.txt`의 그룹별 설정 — 플러그인만 필요한 52개는 `MARO_PLUGIN_PATH`·PATH·book 디렉터리와 `TIMEOUT 240`, 피어가 필요한 그룹(`publish`, `contract`)은 `MARO_PEER_PATH`를 더하고 `TIMEOUT 360`. `tech_diag`는 원래 "순수 함수" 구역에 60초로 있었으나 Maya가 필요해지면서 옮겼다. 상한이 짧으면 콜드 머신에서 DLL 로드만으로 타임아웃한다(F-222).

**예시:**
```cmake
set_tests_properties(${maya_test} PROPERTIES ENVIRONMENT "..." TIMEOUT 240)
```

**관련 코드:**
- `tests/CMakeLists.txt:285-352` — 그룹별 타임아웃

**증거:**
- §8.1
- F-222

**함정:** 타임아웃을 넉넉히 주면 진짜 교착도 240초를 기다린다. 짧으면 느린 머신에서 오탐이다 — 그룹별로 다르게 잡는 이유다.

**교훈:** 시간 상한은 "가장 느린 정상 실행"보다 조금 위다. 그 값을 그룹별로 구한다.

#### 콜드 머신

**직관:** DLL 캐시가 없는 첫 실행 환경. ROS DLL 154개를 처음 로드하는 비용이 테스트 시간에 더해진다.

**동작:** 첫 실행에서는 OS 파일 캐시가 비어 있어 DLL 로드만으로 수십 초가 걸릴 수 있다. 이 때문에 타임아웃이 60초였던 테스트가 CI 첫 실행에서 실패했고 240초로 올렸다(F-222). 같은 이유로 "두 번째 실행은 빠르다"가 성능 측정을 왜곡하므로, 성능 테스트는 시간이 아니라 연산 횟수를 센다.

**예시:**
```
콜드: maro.mll + ROS DLL 154개 첫 로드 → 수십 초
웜:   파일 캐시 적중 → 수 초
```

**관련 코드:**
- `tests/CMakeLists.txt:285-308` — 240초 상한
- `src/maro_plugin/CMakeLists.txt:110-130` — 로드 대상 DLL 스테이징

**증거:**
- §8.1
- F-222

**함정:** 개발자 머신은 항상 웜이라 이 비용이 안 보인다. CI의 첫 실행에서만 드러난다.

**교훈:** 시간 기반 판정은 캐시 상태에 좌우된다. 상한을 잡을 때 콜드 케이스를 기준으로 한다.

#### `memcpy` 리틀엔디언 오프셋 0/4/8/12

**직관:** PointCloud2 바이트 레이아웃을 검증하는 방법 — 패킹된 버퍼에서 오프셋 0/4/8/12의 float32를 직접 꺼내 값이 맞는지 본다.

**동작:** `test_point_cloud_packing.cpp`는 `pointStep == 16`을 확인하고, `std::memcpy(&x, packed.data.data() + 0, sizeof(float))`처럼 네 필드를 각각 읽어 x/y/z/intensity가 제자리에 있는지 단언한다. 빈 입력이면 width 0, intensity가 없으면 0으로 채워지는지도 본다. 구조체 캐스팅이 아니라 memcpy를 쓰는 것은 정렬 가정을 만들지 않기 위해서다.

**예시:**
```cpp
std::memcpy(&x, packed.data.data() + 0, sizeof(float));
std::memcpy(&y, packed.data.data() + 4, sizeof(float));
EXPECT_FLOAT_EQ(x, 1.0f);
```

**관련 코드:**
- `tests/lidar/test_point_cloud_packing.cpp:30-50` — 오프셋 검증
- `src/maro_lidar/src/PointCloudPacking.cpp:8-30` — 패킹

**증거:**
- §8.2, §8.2.2

**함정:** 구조체로 캐스팅해 검증하면 컴파일러 패딩이 끼어 "통과하는데 실제 바이트는 다른" 상황이 된다. 바이트로 검증한다.

**교훈:** 바이너리 레이아웃은 바이트 오프셋으로 단언한다. 그것이 소비자가 보는 것과 같은 시선이다.

#### 순서 보존 + 전체 범위 커버

**직관:** 데시메이션(점 솎기) 테스트의 단언 — 결과가 입력 순서를 지키고, 입력 전 구간에서 골고루 뽑혔는지 본다. "앞부분만 자르는" 구현을 배제한다.

**동작:** `test_decimation.cpp`는 상한 미만이면 원본 그대로, 정확히 `maxPoints`로 클램프되는지 확인하고, 1000점을 솎았을 때 첫 점이 100 미만·마지막 점이 900 초과인지 단언한다. 단순히 "개수가 맞다"만 보면 `resize(maxPoints)` 같은 구현도 통과하는데, 그것은 뒤쪽 공간을 통째로 잃는다.

**예시:**
```cpp
EXPECT_LT(out.front().x, 100.0);    // 앞에서만 뽑지 않았다
EXPECT_GT(out.back().x, 900.0);     // 뒤 구간도 대표된다
```

**관련 코드:**
- `tests/lidar/test_decimation.cpp:20-38` — 세 단언
- `src/maro_lidar/src/Decimation.cpp` — 구현

**증거:**
- §8.2, §8.2.2

**함정:** "개수 단언"은 가장 쉽고 가장 약하다. 분포를 보지 않으면 잘못된 샘플링을 놓친다.

**교훈:** 요약 연산(샘플링·집계)의 테스트는 결과의 **분포**를 단언한다. 개수는 필요조건일 뿐이다.

#### eps 경계 회귀 그물(`d=eps/2` vs `2·eps`)

**직관:** 허용오차 상수의 경계 양쪽을 한 쌍으로 단언해 두는 테스트. 상수 하나가 두 문턱을 동시에 통제한다는 사실을 고정한다.

**동작:** SAT 테스트 케이스 8은 같은 삼각형을 법선 방향으로 `d = eps/2` 옮기면 coplanar로 재분류돼 2D SAT에서 완전 일치 → 충돌, `d = 2·eps`면 3D 분기에서 법선 축 분리 → 비충돌임을 단언한다. 두 기댓값은 임의로 정한 것이 아니라 코드의 eps 정의에서 역산했다.

**예시:**
```cpp
EXPECT_TRUE (trianglesIntersect(a, shift(a, n * (eps / 2))));   // coplanar 경로
EXPECT_FALSE(trianglesIntersect(a, shift(a, n * (2 * eps))));   // 3D 분리 경로
```

**관련 코드:**
- `tests/lidar/test_collision_engine.cpp:233-285` — 경계 쌍
- `src/maro_lidar/src/CollisionEngine.cpp:122-140` — eps 정의

**증거:**
- §8.2, §8.2.2

**함정:** 경계 한쪽만 단언하면 상수를 키우거나 줄이는 변경이 반만 잡힌다. 양쪽이 그물이 된다.

**교훈:** 임계값이 있는 코드는 "바로 아래"와 "바로 위"를 쌍으로 테스트한다.

#### 워커에서 `ASSERT_*` 금지

**직관:** gtest의 `ASSERT_*`는 실패 시 **현재 함수에서 return**할 뿐이다. 워커 스레드의 람다 안에서 쓰면 그 람다만 빠져나오고 테스트는 실패하지 않는다.

**동작:** `test_named_pipe.cpp`는 워커 스레드 안에서 `ASSERT_*`를 쓰지 않는다(`:114-116`). 대신 결과를 전부 `atomic`으로 넘기고 판정은 메인 스레드가 한다. 더 나쁜 경우도 있다 — `ASSERT_*`로 조기 return하면 `join()`을 건너뛰어 joinable한 `std::thread`가 소멸하고, 그것은 `std::terminate`로 프로세스 전체를 죽인다(실측: 200회 중 1회 실패에서 스위트가 exit code 3).

**예시:**
```cpp
// 워커: 판정하지 않고 기록만
detectMs.store(elapsed);
received.store(ok);
// 메인: 판정
EXPECT_TRUE(received.load());
```

**관련 코드:**
- `tests/ipc/test_named_pipe.cpp:110-165` — atomic 전달과 메인 판정
- `tests/ipc/test_named_pipe.cpp:23-28` — `ThreadJoiner`

**증거:**
- §8.2, §8.2.3

**함정:** 워커에서 쓴 `ASSERT_*`는 "테스트가 통과"하게 만든다 — 실패가 삼켜지기 때문이다. 가장 조용한 종류의 거짓 통과다.

**교훈:** 단언은 테스트 프레임워크가 보는 스레드에서만 한다. 다른 스레드는 데이터를 돌려준다.

#### `atomic` 결과 전달

**직관:** 워커 스레드의 관측을 메인 스레드로 넘기는 수단. 판정은 메인에서 하므로 값만 안전하게 옮기면 된다.

**동작:** `std::atomic<bool>`·`std::atomic<long long>`로 `clientClosed`·`orderingForced`·`detectMs`·수신 여부 플래그 등을 주고받는다. 원자 타입이라 데이터 경쟁이 없고, 루프의 종료 조건으로도 쓸 수 있다(일반 bool은 최적화로 루프 밖에 캐시될 수 있다). 같은 패턴이 레거시 공유 메모리 헤더의 `atomic frame_index`에도 쓰였다.

**예시:**
```cpp
std::atomic<bool> received{false};
std::atomic<long long> detectMs{-1};
```

**관련 코드:**
- `tests/ipc/test_named_pipe.cpp:105-130` — 원자 변수들
- `src/ViewportStreamer.h` — 레거시 `atomic frame_index`

**증거:**
- §8.2, §8.2.3, §8.2.6

**함정:** `atomic`은 개별 변수의 원자성만 준다. 두 변수의 조합이 일관돼야 하면 순서를 정하거나 락이 필요하다.

**교훈:** 스레드 간 관측 전달은 원자 변수로 최소화한다. 복잡해지면 설계가 잘못된 신호다.

#### 시간 조건이 곧 주장 (`detectMs<1000`)

**직관:** "즉시 감지"를 검증하려면 시간 조건을 단언에 넣어야 한다. 결과만 보면 타임아웃으로 느리게 도달한 구현도 통과한다.

**동작:** 파이프 끊김 테스트에서 `EXPECT_FALSE(got)`만 쓰면, 끊김을 못 알아채고 기다리기만 하는 구현도 결국 타임아웃으로 false를 주므로 통과한다(F-199). 그래서 `detectMs < 1000`을 함께 단언해 "즉시"를 고정했다. 시간을 주장으로 쓰되 넉넉한 상한(1초)을 잡아 머신 속도에 덜 민감하게 했다.

**예시:**
```cpp
EXPECT_FALSE(received.load());
EXPECT_LT(detectMs.load(), 1000) << "끊김을 즉시 감지하지 못했다(타임아웃 폴백)";
```

**관련 코드:**
- `tests/ipc/test_named_pipe.cpp:159-165` — 시간 단언
- `src/maro_ipc/src/NamedPipe.cpp:78-92` — 즉시 감지 경로

**증거:**
- §8.2, §8.2.3
- F-199

**함정:** 시간 단언은 느린 머신에서 플래키가 될 수 있다. 상한을 "정상 경로의 10배" 정도로 잡으면 구분력은 유지하면서 안정적이다.

**교훈:** "빠르게"가 요구사항이면 테스트에도 시간이 들어가야 한다. 결과만으로는 경로를 구분할 수 없다.

#### `fakeMayaPid()`

**직관:** 감시자 테스트에서 "살아 있는 소유자 PID"가 필요할 때 gtest 자신의 PID를 쓰는 요령. 진짜 Maya를 띄울 필요가 없다.

**동작:** `std::uint64_t fakeMayaPid() { return ::GetCurrentProcessId(); }`. 감시자는 명명 규칙에 PID를 쓰고 소유자 생존을 확인하므로, 테스트 프로세스 자신이 그 역할을 하면 충분하다. 덕분에 감시자 프로세스 테스트가 Maya 없이 gtest 안에서 돈다.

**예시:**
```cpp
std::uint64_t fakeMayaPid() { return ::GetCurrentProcessId(); }
const std::string cmd = "\"" + sentinelExePath() + "\" " + std::to_string(fakeMayaPid()) + " ...";
```

**관련 코드:**
- `tests/ipc/test_sentinel_process.cpp:34-40` — 정의와 사용

**증거:**
- §8.2, §8.2.3

**함정:** 테스트가 끝나면 그 PID의 소유자도 사라진다. 감시자가 그 뒤에 살아 있으면 "주인 없는 감시자"가 되므로 RAII 가드로 정리한다.

**교훈:** 의존 대상이 "어떤 성질"만 필요하면 그 성질을 가진 가장 싼 것을 쓴다. 여기서는 "살아 있는 PID"였다.

#### 200ms 접속 대기

**직관:** 클라이언트가 붙자마자 닫으면 감시자가 아직 `ConnectNamedPipe` 전일 수 있다. 그 마이크로초 창을 피하려고 200ms 기다린다.

**동작:** `letTheSentinelAcceptTheConnection()`이 200ms를 쉰다. 이것이 없으면 감시자가 `ERROR_NO_DATA`로 판정 없이 종료해 정상 시나리오가 **엉뚱한 이유로 통과**한다(F-131). 즉 이 대기는 성능 조정이 아니라 "검증하려는 경로를 실제로 타게 하는" 장치다.

**예시:**
```cpp
ASSERT_TRUE(client.connect(maro::ipc::pipeName(fakeMayaPid()), 5000));
letTheSentinelAcceptTheConnection();   // 200ms — 감시자가 수락할 시간을 준다
client.close();
```

**관련 코드:**
- `tests/ipc/test_sentinel_process.cpp:133-150` — 대기 함수와 사용

**증거:**
- §8.2, §8.2.3
- F-131

**함정:** "sleep은 나쁘다"는 일반론이 여기서는 맞지 않는다. 상대의 준비 상태를 관측할 수단이 없으면 대기가 가장 단순한 해법이다.

**교훈:** 대기가 필요한 이유를 주석에 적으면 그 sleep은 정당화된다. 이유 없는 sleep만 나쁘다.

#### `ERROR_NO_DATA`

**직관:** 파이프에 아직 데이터가 없을 때의 오류. 감시자가 접속 수락 전에 클라이언트가 닫으면 이 코드로 조기 종료한다.

**동작:** 이 경로로 감시자가 나가면 **판정 없이** 끝나므로 기록 파일이 안 생기고, 테스트는 "정상 시나리오"가 다른 이유로 통과한 상태가 된다(F-131). 200ms 대기가 그 창을 닫는다. 같은 오류 코드가 §11.4의 파이프 오류 목록에 `ERROR_IO_PENDING`·`ERROR_BROKEN_PIPE`·`ERROR_FILE_NOT_FOUND`와 함께 실려 있다.

**예시:**
```
클라이언트 connect → 즉시 close
감시자: 아직 ConnectNamedPipe 전 → ERROR_NO_DATA → 조기 종료(판정 없음)
```

**관련 코드:**
- `tests/ipc/test_sentinel_process.cpp:133-150` — 회피 대기
- `src/maro_sentinel/main.cpp:147-205` — 수신 루프

**증거:**
- §8.2, §8.2.3, §11.4
- F-131

**함정:** 조기 종료는 종료 코드만 보면 정상처럼 보인다. 기록 파일의 존재까지 확인해야 경로를 구분할 수 있다.

**교훈:** "무엇이 남았는가"까지 단언하면 경로 혼동이 드러난다. 종료 코드는 약한 신호다.

#### `waitForRecord` 비원자 쓰기

**직관:** 감시자의 기록 파일 쓰기는 truncate 후 dump라 원자적이지 않다. 읽는 쪽이 중간에 끼면 0바이트나 잘린 JSON을 본다.

**동작:** `waitForRecord`는 그것을 실패가 아니라 "아직 쓰는 중"으로 취급해 재시도한다. 파싱 실패를 즉시 실패로 처리하면 타이밍에 따라 간헐 실패가 된다. 같은 비원자성 문제가 저널 회전에서도 나타나 "남의 파일은 재작성하지 않는다"는 규칙을 낳았다.

**예시:**
```cpp
bool waitForRecord(const std::filesystem::path& p, SentinelRecord& out, int timeoutMs) {
    // 0바이트/파싱 실패 = 아직 쓰는 중 → 재시도
}
```

**관련 코드:**
- `tests/ipc/test_sentinel_process.cpp:112-132` — 폴링 읽기
- `src/maro_ipc/src/SentinelRecord.cpp` — trunc+dump 쓰기

**증거:**
- §8.2, §8.2.3, §8.2.4

**함정:** 원자적 쓰기(임시 파일 + rename)로 바꾸면 이 폴링이 필요 없다. 지금은 읽는 쪽이 감수한다.

**교훈:** 비원자 쓰기를 남겨 둘 거면 읽는 쪽에 "미완성 상태"의 정의를 준다.

#### `aliveMs ≥ 10000`

**직관:** "감시자가 접속을 기다리다가 타임아웃으로 나갔다"를 고정하는 단언. 그냥 종료 코드만 보면 조기 종료와 구분되지 않는다.

**동작:** `NoConnectionEverArrivesSoSentinelExitsOnItsOwn` 테스트는 감시자를 띄우고 아무도 접속하지 않은 채 종료를 기다린 뒤, 생존 시간이 10초 이상이었는지 단언한다. 인자 파싱 실패 같은 조기 종료는 대기 타임아웃에 대해 아무것도 증명하지 못한 채 통과할 수 있기 때문이다 — 접속 대기 상한이 15초라는 설계가 이 단언으로 검증된다.

**예시:**
```cpp
EXPECT_GE(aliveMs, 10000) << "접속 대기 없이 조기 종료한 것으로 보인다";
```

**관련 코드:**
- `tests/ipc/test_sentinel_process.cpp:223-260` — 생존 시간 단언
- `src/maro_sentinel/main.cpp:25-45` — 15초 접속 대기 상수

**증거:**
- §8.2, §8.2.3

**함정:** "프로세스가 끝났다"는 여러 이유로 참이다. 어떤 이유였는지를 시간·기록으로 좁혀야 한다.

**교훈:** 종료를 검증할 때는 "왜 끝났는가"를 구분하는 관측을 함께 단언한다.

#### 줄을 JSON으로 재파싱

**직관:** 저널 테스트에서 출력 줄을 부분 문자열로 찾지 않고 **JSON으로 다시 파싱해** 필드 값을 단언하는 기법.

**동작:** 부분 문자열 검색은 tag와 msg가 뒤바뀌거나 severity가 하드코딩돼도 통과한다(Finding 2). 재파싱하면 `{"sev":"error","tag":"...","msg":"..."}`의 각 필드를 정확히 단언할 수 있다. 저널이 JSON Lines라 줄 단위 파싱이 자연스럽다.

**예시:**
```cpp
const auto j = nlohmann::json::parse(line);
EXPECT_EQ(j.at("sev"), "error");
EXPECT_EQ(j.at("tag"), "MaroBindAxisCommand.TargetNotTransform");
```

**관련 코드:**
- `tests/diag/test_journal_writer.cpp:60-120` — 재파싱 단언
- `src/maro_diag/src/JournalWriter.cpp:14-22` — 쓰기 쪽

**증거:**
- §8.2, §8.2.4

**함정:** 재파싱은 "형식이 유효한가"도 함께 검증한다. 부분 문자열은 깨진 JSON도 통과시킨다.

**교훈:** 구조화된 출력은 구조로 단언한다. 문자열 검색은 마지막 수단이다.

#### 부분 문자열 검색의 한계

**직관:** 로그 테스트에서 `contains("error")` 같은 검색은 필드 위치가 바뀌거나 값이 하드코딩돼도 통과한다. 통과의 이유가 약하다.

**동작:** 저널 테스트 Finding 2가 이 문제를 지적했다 — tag/msg가 뒤바뀌거나 sev가 하드코딩된 구현도 부분 문자열 단언을 통과한다. 대응이 JSON 재파싱이다. 같은 논리가 프레젠터 테스트에도 적용돼 문장 전체를 `EXPECT_EQ`로 고정한다.

**예시:**
```cpp
// 약함: EXPECT_NE(line.find("error"), std::string::npos);
// 강함: EXPECT_EQ(nlohmann::json::parse(line).at("sev"), "error");
```

**관련 코드:**
- `tests/diag/test_journal_writer.cpp:60-120` — 개선된 단언
- `tests/diag/test_panel_presenter.cpp` — 문장 전체 비교

**증거:**
- §8.2, §8.2.4

**함정:** 부분 문자열은 쓰기 쉬워서 기본값이 되기 쉽다. "어떤 틀린 구현이 통과하는가"를 물으면 약함이 드러난다.

**교훈:** 단언의 강도는 "통과하는 틀린 구현의 수"로 잰다. 적을수록 강하다.

#### `makeRecord`/`makeHashlessRecord`/`makeErrorRecordWithSiteTag`

**직관:** 프레젠터 테스트의 헬퍼 세 개. 어떤 헬퍼를 쓰느냐가 곧 "어떤 계약을 테스트하는가"를 뜻한다.

**동작:** `makeRecord`는 원문을 `errorHash`에 직접 넣어 접기 키(collapseKey) 동작을 테스트하고, `makeHashlessRecord`는 info/warn 경로(`"m:"` 대체)를 테스트하며, `makeErrorRecordWithSiteTag`는 `errorHash`에 다이제스트·`siteTag`에 원문을 넣어 `error()`가 실제로 만드는 모양을 재현한다. 즉 다이제스트와 원문을 구분하는 것이 이 헬퍼들의 존재 이유다.

**예시:**
```cpp
maro::DiagRecord makeRecord(std::uint64_t seq, std::uint64_t ms, ...);              // 접기 키용
maro::DiagRecord makeHashlessRecord(std::uint64_t seq, std::uint64_t ms, ...);      // info/warn
maro::DiagRecord makeErrorRecordWithSiteTag(...);                                    // 실제 error() 모양
```

**관련 코드:**
- `tests/diag/test_panel_presenter.cpp:13-45` — 세 헬퍼와 구분 주석
- `src/maro_diag/src/PanelPresenter.cpp` — 검증 대상

**증거:**
- §8.2, §8.2.4

**함정:** 헬퍼 하나로 모든 케이스를 만들면 "실제 코드가 만드는 모양"과 다른 입력으로만 테스트하게 된다.

**교훈:** 테스트 헬퍼의 분화는 계약의 분화를 반영한다. 헬퍼 이름이 계약 이름이 된다.

#### 절단은 필터·접기 뒤

**직관:** 진단 패널의 행 목록을 상한으로 자를 때, 필터와 접기(collapse)를 **먼저** 적용한 뒤에 잘라야 한다. 먼저 자르면 연쇄의 시작이 사라진다.

**동작:** 프레젠터 계약은 — 접기는 태그로(연속이 아니어도, 병렬 평가에서 번갈아 들어오므로), 행 자리는 최신 발생, severity도 최신 발생, 벽시계 역행은 무시(순번 기준), **절단은 필터·접기 뒤**, 필터/상한은 그 다음. 순서가 바뀌면 같은 데이터가 다른 화면을 만든다.

**예시:**
```
입력 100행 → 필터(error만) 40행 → 접기(태그별) 12행 → 절단(상한 10) 10행
잘못된 순서: 절단(10) → 필터 → 접기 → 3행 (연쇄 시작이 사라짐)
```

**관련 코드:**
- `src/maro_diag/src/PanelPresenter.cpp` — 파이프라인 순서
- `tests/diag/test_panel_presenter.cpp` — 순서 단언

**증거:**
- §8.2, §8.2.4

**함정:** 성능을 위해 "먼저 자르자"는 최적화가 의미를 바꾼다. 데이터 양이 적으면 정확성이 우선이다.

**교훈:** 파이프라인 단계의 순서는 의미의 일부다. 순서를 테스트로 고정한다.

#### `knownBefore` 순서 무관

**직관:** "이 해시를 전에 본 적 있는가"를 판정하는 입력이 **정렬돼 있지 않아도** 같은 결과를 내야 한다. 테스트가 오름차순 순번만 주면 그 가정이 숨는다.

**동작:** 프레젠터·book 테스트는 순번이 뒤섞인 입력으로도 같은 판정이 나오는지 확인한다. 픽스처 함정 목록에 "순번 오름차순만"이 들어 있는 이유다 — 병렬 평가에서는 레코드가 번갈아 들어오므로 실제 입력이 정렬돼 있지 않다.

**예시:**
```
입력 순번: 5, 3, 9, 1  → knownBefore 판정은 입력 순서와 무관해야 함
```

**관련 코드:**
- `tests/diag/test_panel_presenter.cpp` — 뒤섞인 순번 케이스
- `src/maro_diag/src/PanelPresenter.cpp` — 순번 기반 정렬

**증거:**
- §8.2, §8.2.2, §8.2.3

**함정:** 정렬된 픽스처는 만들기 쉽고 현실과 다르다. 실제 입력의 무질서를 픽스처에 반영해야 한다.

**교훈:** "입력이 정렬돼 있다"는 가정은 명시하거나 깨뜨려 본다. 둘 중 하나는 해야 한다.

#### 문장 전체 `EXPECT_EQ`(7/2)

**직관:** 사용자에게 보이는 한국어 문장을 부분 검색이 아니라 **전체 일치**로 고정하는 방식. 조사·띄어쓰기까지 계약이 된다.

**동작:** `test_remedy_action.cpp`는 `describeRemedyAction`이 만드는 문장을 통째로 비교한다. 정수형 값은 소수점 없이 표기해야 하므로 "값을 1(으)로"가 기대값이고, 7이면 "7(으)로", 2면 "2(으)로"다. 주의 — "문자열 전체에 마침표가 없는지"를 보는 검사는 틀렸다. `'n'.a` 같은 표기 자체에 마침표가 있을 수 있기 때문이다.

**예시:**
```cpp
EXPECT_EQ(describeRemedyAction(a), "maroAxis1.controlMode 값을 1(으)로 바꾸세요");
```

**관련 코드:**
- `tests/diag/test_remedy_action.cpp` — 문장 고정
- `src/maro_diag/src/RemedyAction.cpp` — 문장 생성

**증거:**
- §8.2, §8.2.3, §8.2.4

**함정:** 문장을 고정하면 문구를 바꿀 때마다 테스트를 고쳐야 한다. 그것이 의도다 — 사용자에게 보이는 문구는 리뷰 대상이다.

**교훈:** UI 문구는 계약이다. 전체 일치로 고정하면 변경이 눈에 띈다.

#### `print("… OK")` 체크포인트

**직관:** Maya 배치 테스트에서 각 단계 끝에 성공 표시를 출력하는 관례. 실패했을 때 로그의 마지막 OK로 지점을 바로 찾는다.

**동작:** 배치 테스트의 판정은 **종료 코드**다 — 프로세스가 0으로 끝나면 통과, 안 끝나면 그 자체가 teardown 결함(스레드·퍼블리셔 누수)이다. 그래서 단계별 `print("<단계> OK")`가 유일한 진행 로그다. 58개 스크립트가 같은 뼈대(`standalone.initialize` → `loadPlugin` → `file(new)` → 단언 → `file(new)` → `unloadPlugin` → `uninitialize` → `sys.exit(0)`)를 쓴다.

**예시:**
```python
print("plugin load OK")
print("axis create OK")
print("publish OK")
sys.exit(0)
```

**관련 코드:**
- `tests/maya/test_publish.py:94-101` — 체크포인트 사용
- `tests/maya/test_load.py` — 뼈대와 독스트링

**증거:**
- §8.3, §8.3.0, §8.3.2

**함정:** 체크포인트를 너무 촘촘히 두면 로그가 잡음이 된다. 단계 경계에만 둔다.

**교훈:** 종료 코드로 판정하는 테스트에는 진행 로그가 진단의 전부다. 단계 이름을 사람이 읽을 수 있게 적는다.
