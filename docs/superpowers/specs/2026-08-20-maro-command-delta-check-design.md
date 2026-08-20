# Maro 명령 델타체크 설계 (2026-08-20)

## 1. 배경

사용자가 제안한 "Maro Core Kernel"(4개 기둥: 중앙 디스패처, zero-copy 공유메모리,
DG 평가 캐싱, 비동기 텔레메트리) 문서를 검토하는 과정에서, 실제 코드베이스를
확인해보니 문서의 전제와 실제 상태가 상당히 달랐다:

| 기둥 | 문서의 전제 | 실제 상태 |
|---|---|---|
| 1. 중앙 디스패처 | 구현 필요 | 대부분 이미 존재 (`MaroRosRuntime`/`MaroPump`/`MaroMainThreadQueue`/`BoundedQueue`가 이미 역할별로 분리돼 있음) |
| 2. Zero-copy 공유메모리 | 리팩터링 필요 | 절반이 죽은 코드 (`ViewportStreamer.h/.cpp`가 어떤 CMakeLists.txt에도 안 걸려 빌드 안 됨, 인코딩 깨짐 + 이물질 텍스트 포함) |
| 3. DG 평가 캐싱 | 구현 필요 | **실제로 없음** — `MaroAxisNode`/`MaroCommandDeviceNode` 어디에도 델타체크가 없다 |
| 4. 비동기 텔레메트리 | 구현 필요 | **실제로 없음** — `maro_diag`는 전부 호출 스레드에서 동기 기록 |

"커널"을 하나의 큰 리팩터링으로 한 번에 설계하는 대신, 실제로 비어있는 자리에
이 프로젝트의 기존 방식(작고 단일 책임을 가진 모듈, 좁은 인터페이스)대로
하나씩 좁게 추가하기로 했다. 이 문서는 그중 **3번(DG 평가 캐싱)의 가장 좁은
조각** — 값이 실제로 안 바뀐 명령이 불필요한 dirty 전파를 일으키는 문제 —
만 다룬다.

4번(비동기 텔레메트리), 2번(zero-copy 파이프라인 정리), 그리고 3번의 나머지
절반(명령마다 씬 전체를 순회하는 O(N) 스캔 문제)은 **의도적으로 이 스펙의
범위 밖**이다 — 각각 별도의 브레인스토밍/스펙 사이클을 거쳐야 한다.

## 2. 문제

`MaroCommandDeviceNode::applyToMatchingAxis()`(`src/maro_plugin/MaroCommandDeviceNode.cpp:249`)가
ROS 2에서 조인트 값이 들어올 때마다 하는 일:

```cpp
axisFn.findPlug(MaroAxisNode::aRosCommand, false).setDouble(value);
```

값이 이전과 완전히 같아도 **무조건** `setDouble()`을 호출한다. Maya는
`MPlug::setDouble()`이 이전 값과 같은지 확인해서 dirty 전파를 건너뛰어 주지
않는다 — 호출하면 무조건 dirty가 전파되고 재평가가 예약된다. 고빈도로
동일한 값을 반복 발행하는 ROS 2 퍼블리셔(예: 정지 상태를 유지하며 계속
같은 조인트 상태를 쏘는 경우)가 있으면, 실제로는 아무 것도 안 바뀌는데도
Maya가 매번 재평가를 한다.

## 3. 설계

### 3.1 메커니즘

`applyToMatchingAxis()`에서 `setDouble()` 호출 직전에 현재 값을 먼저 읽어
비교한다:

```cpp
const double current = axisFn.findPlug(MaroAxisNode::aRosCommand, false).asDouble();
if (std::abs(value - current) < kUnchangedEpsilon) {
    s_skippedUnchanged.fetch_add(1, std::memory_order_relaxed);
    continue;
}
axisFn.findPlug(MaroAxisNode::aRosCommand, false).setDouble(value);
s_applied.fetch_add(1, std::memory_order_relaxed);
```

**새로운 캐시 저장소를 만들지 않는다.** `aRosCommand` 플러그 자체가 이미
"마지막으로 적용된 값"을 들고 있으므로, 그 값을 `getDouble()`(`asDouble()`)로
읽어 비교하면 충분하다. 별도의 `unordered_map<jointName, lastValue>` 같은
캐시를 만들면 (a) 문자열 키 조회 비용이 추가되고 (b) `compute()`가
Parallel Evaluation Manager 하에서 워커 스레드에 돌 수 있다는
`applyToMatchingAxis()` 자신의 기존 주석(§3.3 참고) 때문에 뮤텍스 보호가
필요해진다 — 아무 이득 없이 복잡도만 늘어난다.

### 3.2 epsilon

```cpp
constexpr double kUnchangedEpsilon = 1e-9;
```

이 축 시스템은 현재 회전(라디안) 조인트만 다룬다(`MaroAxisNode::aOutValue`가
`MFnUnitAttribute::kAngle`, 내부 라디안 — 선형/프리즈매틱 조인트 흔적 없음).
`1e-9`는 라디안 스케일에서 의미 있는 움직임은 절대 걸러지지 않고, 부동소수점
표현 오차로 생기는 노이즈만 제거하는 수준이다.

**사용자가 조정 가능한 어트리뷰트로 만들지 않는다.** 이 스펙의 목적은
"눈에 안 보이는 떨림까지 의도적으로 무시해서 성능을 더 아끼는 것"이
아니라 "이미 똑같은 값을 다시 쓰지 않는 것"이다. 전자는 범위 밖이다 —
필요해지면 별도 스펙으로 다룬다.

### 3.3 스레드 안전성

`applyToMatchingAxis()`의 기존 주석이 이미 경고하듯, Maya 2026 기본값인
Parallel Evaluation Manager 하에서는 `compute()`가 워커 스레드에서 돌 수
있다(이 노드는 지금까지 Serial 평가를 가정하고 짜여 있고, 이 스펙에서
그 가정을 바꾸지 않는다). §3.1에서 새 상태를 만들지 않기로 한 결정이
여기서 중요하다 — 읽고 비교하는 `aRosCommand` 플러그 자체가 이미 Maya의
데이터블록이 관리하는 상태이므로, 이 변경은 기존 `setDouble()` 호출과
정확히 같은 스레드 안전성 특성을 가진다. 새로 생기는 위험이 없다.

### 3.4 가시성 (카운터)

`MaroCommandDeviceNode`의 기존 진단 카운터 패턴(`s_applied`, `s_dropped`,
`s_poolExhausted`)을 그대로 따라 추가한다:

```cpp
static std::atomic<std::uint64_t> s_skippedUnchanged;
```

- 공개 접근자 `skippedUnchangedCount()` 추가(`appliedCommandCount()`와
  같은 패턴).
- `resetStats()`가 이 카운터도 0으로 되돌리도록 포함시킨다(기존 카운터들과
  같은 이유 — 재시작 후 unsigned 언더플로우 방지).

이 카운터는 두 가지 목적이다: (1) §4의 테스트가 이 동작을 직접 검증할 수
있게 하고, (2) 나중에 진단/텔레메트리(§1의 4번 기둥, 범위 밖)가 쓸 수 있는
자리를 마련해 둔다.

## 4. 테스트

기존 `tests/maya/test_axis_node.py`(마야파이 기반, 실제 Maya DG 동작을
검증하는 이 프로젝트의 기존 패턴)에 시나리오를 추가한다:

1. **같은 값을 두 번 보낸다.** 두 번째 호출 후 `skippedUnchangedCount()`가
   1 늘고, `appliedCommandCount()`는 첫 번째 호출 이후로 그대로인지 확인한다.
2. **회귀 방지**: 값이 실제로 다르면 여전히 `appliedCommandCount()`가
   늘고 축 플러그 값이 실제로 갱신되는지 확인한다(델타체크가 진짜로
   변경을 놓치지 않는지).
3. **경계값**: epsilon보다 아주 살짝 큰 차이(예: `kUnchangedEpsilon * 10`)는
   여전히 "변경"으로 취급되는지 확인한다.

이 프로젝트의 기존 TDD 규율(모든 새 테스트는 구현을 일부러 깨서 실패하는
것까지 확인)에 따라, 구현 단계에서 `setDouble()` 호출을 원래대로(조건 없이)
되돌려 위 1번 테스트가 실제로 실패하는지 확인한 뒤 되돌린다.

## 5. 범위 밖 (의도적)

- **O(N) 씬 전체 순회** — 명령 하나당 씬의 모든 `MaroAxisNode`를 순회하는
  문제. 델타체크와는 독립적인 별도 성능 이슈이며, 별도 스펙에서 다룬다.
- **`MaroCapabilityNodes` 쪽 캐싱** — 능력 노드(회전/제한 등)는 정적 설정값을
  담고 있어 애초에 자주 안 바뀐다. 이번 델타체크 대상이 아니다.
- **사용자 조정 가능 epsilon** — §3.2 참고.
- **"Core Kernel" 문서의 나머지 3개 기둥** (중앙 디스패처 통합, zero-copy
  공유메모리, 비동기 텔레메트리) — 전부 별도의 브레인스토밍/스펙 사이클
  대상이다.

## 6. 전역 제약

- 변경 파일: `src/maro_plugin/MaroCommandDeviceNode.h`,
  `src/maro_plugin/MaroCommandDeviceNode.cpp`,
  `tests/maya/test_axis_node.py`. 그 외 어떤 파일도 건드리지 않는다.
- 기존 카운터(`s_applied`, `s_dropped`, `s_poolExhausted`)와 정확히 같은
  네이밍/메모리 순서(`memory_order_relaxed`) 규칙을 따른다.
- undo 스택 관련 기존 동작(런타임 데이터 흐름이므로 undo에 안 남김)은
  그대로 유지한다 — 이 스펙이 건드리는 부분이 아니다.
