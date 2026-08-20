# Maro 명령 델타체크 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ROS 2에서 들어온 조인트 명령값이 이전과 실제로 같으면 `MaroCommandDeviceNode`가
`setDouble()` 호출(및 그에 따른 dirty 전파/재평가)을 건너뛰게 한다.

**Architecture:** 비교 판단(값이 바뀌었는지)을 Maya API에 의존하지 않는 순수 함수
`maro::shouldSkipUnchangedCommand()`로 분리하고, `MaroCommandDeviceNode::applyToMatchingAxis()`는
그 함수를 부르는 얇은 배선만 남긴다. 판단 로직은 gtest로 완전히 검증하고, Maya 배선
자체는 코드 리뷰로 검증한다(이유: §전역 제약 참고 — `applyToMatchingAxis()`는 mayapy
배치 모드에서 도달 불가능하다는 것이 이미 별도로 검증돼 있다).

**Tech Stack:** C++17, GoogleTest, CMake(Visual Studio 멀티 컨피그 제너레이터), Maya 2026 devkit.

## Global Constraints

- 스펙: `docs/superpowers/specs/2026-08-20-maro-command-delta-check-design.md`
- 변경/생성 파일은 정확히 다음으로 제한한다: `src/maro_plugin/CommandDeltaCheck.h`(신규),
  `src/maro_plugin/MaroCommandDeviceNode.h`, `src/maro_plugin/MaroCommandDeviceNode.cpp`,
  `tests/plugin/test_command_delta_check.cpp`(신규), `tests/CMakeLists.txt`. 그 외 어떤
  파일도 건드리지 않는다.
- `CommandDeltaCheck.h`는 Maya 헤더를 포함하지 않는다 — `maro_ipc`/`maro_transform`이
  이미 따르는 "Maya 없이 순수 로직" 원칙과 같다.
- **`applyToMatchingAxis()`는 mayapy(배치 모드)에서 절대 실행되지 않는다** —
  `tests/maya/test_contract.py`의 docstring에 이미 검증·기록돼 있다
  (`MPxThreadedDeviceNode`의 인바운드 배선이 Maya 유휴 이벤트 큐에 의존하는데
  배치 모드는 그 큐를 안 돌린다). 이 함수 안의 새 코드에 mayapy 테스트를 시도하지
  않는다 — 반드시 실패하거나, 더 나쁘게는 아무 것도 검증하지 않으면서 통과하는
  거짓 테스트가 된다.
- 기존 진단 카운터(`s_applied`, `s_dropped`, `s_poolExhausted`)와 정확히 같은
  네이밍/메모리 순서(`memory_order_relaxed`) 규칙을 따른다.
- undo 스택 관련 기존 동작(런타임 데이터 흐름이므로 undo에 안 남김)은 그대로
  유지한다 — 이 플랜이 건드리는 부분이 아니다.
- 빌드는 항상 `--config Release`를 명시한다(이 저장소의 `out/build`는 CMake Visual
  Studio 멀티 컨피그 제너레이터다).
- 빌드 환경: `Launch-VsDevShell.ps1`이 이 머신에서 `vswhere.exe`를 못 찾아
  `INCLUDE`/`LIB`를 비운 채 조용히 성공한다. **빌드와 같은 PowerShell 호출 안에서**
  `VsDevCmd.bat`를 설정한다:

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cd C:\Users\ckd30\Projects\Maya_Ros_Sim
cmake --build out/build --config Release
```

- `ctest --test-dir out/build -C Release --output-on-failure` 실행 시 `maya_panel_commands`
  하나만 실패하는 것이 알려진 사전 결함이다(이 플랜과 무관, `main`에 이미 있음) —
  그 외에는 전부 통과해야 한다.

## 파일 구조

| 파일 | 책임 |
|---|---|
| `src/maro_plugin/CommandDeltaCheck.h` | 순수 함수 `shouldSkipUnchangedCommand()`와 상수 `kUnchangedCommandEpsilon`. Maya도 스레드도 모른다. |
| `tests/plugin/test_command_delta_check.cpp` | `CommandDeltaCheck.h`의 gtest — Maya/mayapy 불필요. |
| `src/maro_plugin/MaroCommandDeviceNode.h` | (수정) `skippedUnchangedCount()` 접근자, `s_skippedUnchanged` 카운터 선언 추가. |
| `src/maro_plugin/MaroCommandDeviceNode.cpp` | (수정) `applyToMatchingAxis()`가 `shouldSkipUnchangedCommand()`를 부르도록 배선, `resetStats()`/접근자 갱신. |
| `tests/CMakeLists.txt` | (수정) 새 `maro_plugin_logic_tests` gtest 실행 파일 등록. |

---

### Task 1: 순수 델타체크 함수

**Files:**
- Create: `src/maro_plugin/CommandDeltaCheck.h`
- Create: `tests/plugin/test_command_delta_check.cpp`
- Modify: `tests/CMakeLists.txt`

**Interfaces:**
- Produces: `maro::kUnchangedCommandEpsilon`(`constexpr double`),
  `maro::shouldSkipUnchangedCommand(double current, double incoming, double epsilon = maro::kUnchangedCommandEpsilon) -> bool`(`constexpr`)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/plugin/test_command_delta_check.cpp`(전체 새 파일):

```cpp
#include <gtest/gtest.h>

#include "CommandDeltaCheck.h"

TEST(CommandDeltaCheck, IdenticalValueIsSkipped) {
    EXPECT_TRUE(maro::shouldSkipUnchangedCommand(1.2, 1.2));
}

TEST(CommandDeltaCheck, DifferentValueIsNotSkipped) {
    EXPECT_FALSE(maro::shouldSkipUnchangedCommand(1.2, 1.5));
}

TEST(CommandDeltaCheck, JustOverEpsilonIsNotSkipped) {
    const double current = 1.2;
    const double incoming = current + maro::kUnchangedCommandEpsilon * 10.0;
    EXPECT_FALSE(maro::shouldSkipUnchangedCommand(current, incoming));
}

TEST(CommandDeltaCheck, JustUnderEpsilonIsSkipped) {
    const double current = 1.2;
    const double incoming = current + maro::kUnchangedCommandEpsilon / 10.0;
    EXPECT_TRUE(maro::shouldSkipUnchangedCommand(current, incoming));
}

TEST(CommandDeltaCheck, DirectionDoesNotMatter) {
    // 들어온 값이 현재값보다 작아도 같은 규칙이 적용된다(절댓값 비교).
    EXPECT_TRUE(maro::shouldSkipUnchangedCommand(1.2, 1.2 - maro::kUnchangedCommandEpsilon / 10.0));
    EXPECT_FALSE(maro::shouldSkipUnchangedCommand(1.2, 1.2 - maro::kUnchangedCommandEpsilon * 10.0));
}

TEST(CommandDeltaCheck, CustomEpsilonOverridesDefault) {
    // 기본 epsilon으로는 "변경 없음"으로 잡힐 차이도, 더 엄격한 epsilon을
    // 넘기면 "변경"으로 잡혀야 한다 -- 세 번째 매개변수가 실제로 쓰이는지 확인.
    const double current = 1.2;
    const double incoming = current + maro::kUnchangedCommandEpsilon / 10.0;
    EXPECT_TRUE(maro::shouldSkipUnchangedCommand(current, incoming));
    EXPECT_FALSE(maro::shouldSkipUnchangedCommand(current, incoming, /*epsilon=*/1e-15));
}
```

`tests/CMakeLists.txt`의 `maro_diag_tests`용 `gtest_discover_tests(maro_diag_tests)`
줄(파일 42번째 줄 부근) 바로 다음, `if(MARO_BUILD_PLUGIN)` 블록 시작(44번째 줄 부근)
바로 앞에 추가:

```cmake
add_executable(maro_plugin_logic_tests
    plugin/test_command_delta_check.cpp
)

target_include_directories(maro_plugin_logic_tests PRIVATE
    ${CMAKE_SOURCE_DIR}/src/maro_plugin
)

target_link_libraries(maro_plugin_logic_tests PRIVATE
    GTest::gtest
    GTest::gtest_main
)

gtest_discover_tests(maro_plugin_logic_tests)
```

이 실행 파일은 Maya나 ROS 2에 의존하지 않는다 — `MARO_BUILD_PLUGIN` 조건 밖에
둬서, 그 플래그가 꺼져 있어도(Maya devkit 없이) 항상 빌드되고 돌게 한다.

- [ ] **Step 2: 테스트가 실패하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

기대: 빌드 실패 — `CommandDeltaCheck.h`가 없다(`fatal error: 'CommandDeltaCheck.h' file
not found` 또는 동등한 MSVC 오류).

- [ ] **Step 3: `CommandDeltaCheck.h` 작성**

`src/maro_plugin/CommandDeltaCheck.h`(전체 새 파일):

```cpp
#pragma once

#include <cmath>

namespace maro {

// 라디안 스케일에서 의미 있는 움직임은 절대 걸러지지 않고, 부동소수점
// 표현 오차로 생기는 노이즈만 제거하는 수준. 이 축 시스템은 현재 회전
// (라디안) 조인트만 다룬다 (MaroAxisNode::aOutValue가
// MFnUnitAttribute::kAngle, 내부 라디안).
constexpr double kUnchangedCommandEpsilon = 1e-9;

// 들어온 명령값(incoming)이 현재값(current)과 사실상 같아서 적용(및 그에
// 따른 dirty 전파)을 건너뛰어도 되는지 판단한다. Maya API에 의존하지
// 않는다 -- MaroCommandDeviceNode::applyToMatchingAxis()가 이 판단 결과로
// setDouble() 호출 여부만 가른다.
constexpr bool shouldSkipUnchangedCommand(double current, double incoming,
                                          double epsilon = kUnchangedCommandEpsilon) {
    return std::abs(incoming - current) < epsilon;
}

}  // namespace maro
```

- [ ] **Step 4: 테스트가 통과하는지 확인**

```powershell
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R CommandDeltaCheck
```

기대: 6개 전부 통과.

- [ ] **Step 5: 일부러 깨서 확인**

`CommandDeltaCheck.h`의 `shouldSkipUnchangedCommand()` 본문을 임시로
`return false;`로 바꾼다.

```powershell
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R CommandDeltaCheck
```

기대: `IdenticalValueIsSkipped`, `JustUnderEpsilonIsSkipped`,
`DirectionDoesNotMatter`, `CustomEpsilonOverridesDefault`가 **실패**한다
(`shouldSkipUnchangedCommand`가 뭘 넣어도 `false`만 돌려주므로). 확인했으면
`return std::abs(incoming - current) < epsilon;`으로 되돌린다.

```powershell
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R CommandDeltaCheck
```

기대: 다시 6개 전부 통과.

- [ ] **Step 6: 커밋**

```bash
git add src/maro_plugin/CommandDeltaCheck.h tests/plugin/test_command_delta_check.cpp tests/CMakeLists.txt
git commit -m "feat: judge whether a ROS 2 command actually changed, without touching Maya"
```

---

### Task 2: `MaroCommandDeviceNode` 배선

**Files:**
- Modify: `src/maro_plugin/MaroCommandDeviceNode.h`
- Modify: `src/maro_plugin/MaroCommandDeviceNode.cpp`

**Interfaces:**
- Consumes: `maro::shouldSkipUnchangedCommand(double, double) -> bool`(Task 1)
- Produces: `maro::MaroCommandDeviceNode::skippedUnchangedCount() -> std::uint64_t`

이 태스크는 새 자동화 테스트가 없다 — Global Constraints에 적은 대로
`applyToMatchingAxis()`는 mayapy 배치 모드에서 도달 불가능하다는 것이
`tests/maya/test_contract.py`로 이미 검증돼 있다. 이 태스크가 하는 일은
그 함수 안에서 이미 검증된 순수 함수(Task 1)를 호출하도록 배선하는
것뿐이므로, 빌드 성공 확인 + 아래 Step 5의 코드 리뷰 체크리스트로
검증한다.

- [ ] **Step 1: `MaroCommandDeviceNode.h` 수정**

`static std::uint64_t threadTickCount();` 바로 다음 줄에 추가:

```cpp
    static std::uint64_t skippedUnchangedCount();
```

`static std::atomic<std::uint64_t> s_poolExhausted;    // 버퍼 풀이 꽉 차 버려진 개수`
바로 다음 줄에 추가:

```cpp
    // 델타체크로 건너뛴 개수 -- 값이 실제로 안 바뀌어 setDouble()을 호출하지
    // 않은 경우. s_applied와 합치면 이 노드가 처리한 명령 총수가 된다.
    static std::atomic<std::uint64_t> s_skippedUnchanged;
```

- [ ] **Step 2: `MaroCommandDeviceNode.cpp` 수정**

`#include "MaroAxisNode.h"` 바로 다음 줄에 추가:

```cpp
#include "CommandDeltaCheck.h"
```

`std::atomic<std::uint64_t> MaroCommandDeviceNode::s_poolExhausted{0};` 바로
다음 줄에 추가:

```cpp
std::atomic<std::uint64_t> MaroCommandDeviceNode::s_skippedUnchanged{0};
```

`resetStats()` 안, `s_poolExhausted.store(0);` 바로 다음 줄에 추가:

```cpp
    s_skippedUnchanged.store(0);
```

`std::uint64_t MaroCommandDeviceNode::threadTickCount() { return s_ticks.load(); }`
바로 다음 줄에 추가:

```cpp
std::uint64_t MaroCommandDeviceNode::skippedUnchangedCount() { return s_skippedUnchanged.load(); }
```

`applyToMatchingAxis()` 안의 다음 두 줄을:

```cpp
        // 런타임 데이터 흐름이므로 직접 쓴다. undo 스택에 남기지 않는다.
        axisFn.findPlug(MaroAxisNode::aRosCommand, false).setDouble(value);
        s_applied.fetch_add(1, std::memory_order_relaxed);
```

다음으로 교체한다:

```cpp
        // 값이 실제로 안 바뀌었으면 dirty 전파(및 그에 따른 재평가)를
        // 아예 안 일으킨다 -- setDouble()은 이전 값과 같아도 무조건 dirty를
        // 퍼뜨린다. 판단 자체는 Maya에 의존하지 않는 순수 함수다
        // (CommandDeltaCheck.h) -- 여기서는 플러그를 읽고 그 결과로
        // 쓸지 말지만 가른다.
        const double current = axisFn.findPlug(MaroAxisNode::aRosCommand, false).asDouble();
        if (shouldSkipUnchangedCommand(current, value)) {
            s_skippedUnchanged.fetch_add(1, std::memory_order_relaxed);
            continue;
        }
        // 런타임 데이터 흐름이므로 직접 쓴다. undo 스택에 남기지 않는다.
        axisFn.findPlug(MaroAxisNode::aRosCommand, false).setDouble(value);
        s_applied.fetch_add(1, std::memory_order_relaxed);
```

- [ ] **Step 3: 빌드 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

기대: 빌드 성공, 새 컴파일 경고 없음.

- [ ] **Step 4: 전체 스위트가 여전히 통과하는지 확인**

```bash
ctest --test-dir out/build -C Release --output-on-failure
```

기대: `maya_panel_commands`(사전 결함, 이 플랜과 무관) 하나만 빼고 전부 통과.
Task 1의 `CommandDeltaCheck.*` 6개도 포함해서 여전히 통과해야 한다.

- [ ] **Step 5: 코드 리뷰 체크리스트 (자동화 테스트를 대신함)**

`applyToMatchingAxis()`의 최종 모습을 다음 기준으로 직접 읽어 확인한다:

1. `current`를 읽는 `findPlug(MaroAxisNode::aRosCommand, false)` 호출과
   `setDouble()`을 부르는 `findPlug(MaroAxisNode::aRosCommand, false)` 호출이
   같은 플러그를 가리키는가(둘 다 `axisFn`, 둘 다 `aRosCommand`)?
2. `continue`가 바깥 `for` 루프(씬의 `MaroAxisNode`들을 순회하는 루프)로
   정확히 돌아가는가 — 안쪽에 다른 루프가 새로 생기지 않았는가?
3. `s_applied`와 `s_skippedUnchanged`가 상호 배타적으로 증가하는가(같은
   반복에서 둘 다 늘거나 둘 다 안 느는 경우가 없는가)?
4. `resetStats()`가 `s_skippedUnchanged`도 0으로 되돌리는가(§Global
   Constraints의 "재시작 후 unsigned 언더플로우 방지"와 같은 이유가
   여기 카운터에는 적용되지 않는다는 점도 확인 — `s_skippedUnchanged`는
   `s_lastReportedDropped`처럼 "마지막 보고값과의 차이"를 계산하는 델타
   추적용이 아니라 단순 누적 카운터이므로, 리셋 자체는 필요하지만
   `s_lastReportedDropped` 같은 별도 기준선이 필요하지 않다)?

- [ ] **Step 6: 커밋**

```bash
git add src/maro_plugin/MaroCommandDeviceNode.h src/maro_plugin/MaroCommandDeviceNode.cpp
git commit -m "feat: skip dirty propagation for ROS 2 commands that did not actually change"
```

---
