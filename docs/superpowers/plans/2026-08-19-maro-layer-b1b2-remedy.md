# Maro Layer B-1b-2 — 상시 큐와 해법 적용 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 알려진 실패 여섯 곳(예: "축이 이미 다른 오브젝트에 묶여 있다", "control mode 값이 잘못됐다")이 발생하면 진단 패널에 [적용] 버튼이 뜨고, 사용자가 누르면 상시로 도는 메인 스레드 큐를 거쳐 안전한 시점에 `MDGModifier`/선택 변경으로 실제 수정이 일어나며, `Ctrl+Z`로 되돌아간다.

**Architecture:** 구조화된 해법(`RemedyAction`)의 판단·서술은 전부 Maya를 모르는 순수 C++(`maro_diag`)에 두고 gtest로 덮는다. 해법의 **구체적인 값**(어느 노드, 어느 플러그)은 실패가 실제로 일어난 그 순간, 그 자리(`src/maro_plugin/MaroCommands.cpp`)에서 살아있는 씬을 보고 채운다 — `book`에 캐시하지 않는다(아래 "spec에서 의도적으로 벗어난 지점" 참고). 적용은 새로 만드는 `MaroMainThreadQueue`(0.1초 상시 타이머, `MaroPump`와 무관하게 플러그인 로드 시부터 언로드까지 항상 돈다)가 미뤄서, DG 평가 중이 아님이 보장되는 시점에 평범하고 되돌릴 수 있는 `MPxCommand`(`maroApplyRemedy`) 하나를 실행시킨다.

**Tech Stack:** C++17, Maya 2026 devkit (`MDGModifier`, `MSelectionList`, `MTimerMessage`), GoogleTest, `mayapy`, CMake + Ninja

설계: `docs/superpowers/specs/2026-08-15-maro-layer-b-diagnostic-panel-design.md` §3.8, §4 (원 스펙 `2026-08-14-maro-troubleshooting-ecosystem-design.md` §4.3의 안전 규칙을 그 설계가 이어받음)

## spec에서 의도적으로 벗어난 지점 — 반드시 먼저 읽을 것

설계 스펙 §4.1은 `remedyAction`을 **`BookEntry`**(해시 하나에 영구히 붙는 항목)에 두라고 적었다. 이 플랜은 그렇게 하지 **않는다**.

**이유.** `book`의 해시는 실패의 "자리와 종류"만 담을 뿐 이번 발생의 구체적인 노드 이름은 담지 않는다는 것이 `ErrorHash.h`의 계약이고(`DiagRecord.h`의 주석, `MaroDiag.h` 참고), 이 프로젝트는 그 경계를 넘어 book에 구체적인 값을 캐시했다가 실제로 사고를 낸 적이 있다 — Layer A 최종 리뷰의 Critical Finding C1(`.superpowers/sdd/final-fix-batch1-report.md`)이 정확히 이것이다: book이 이전 발생의 노드 이름을 이번 발생의 것처럼 재생했다. `remedyAction`이 구체적인 노드 이름(`selectNode`의 대상, `disconnect`의 두 플러그)을 담아야 하는데 그것을 book(해시별로 하나, 세션을 넘어 영속)에 두면 **같은 버그가 다시** 생긴다: 같은 실패 사이트가 서로 다른 두 노드에서 발생해도 같은 해시를 공유하므로, 두 번째 발생에 첫 번째 발생의 (이미 사라졌을 수도 있는) 노드 이름이 적용 버튼에 걸린다.

**대신 이렇게 한다.** `RemedyAction`은 **`DiagRecord`**(발생 하나마다 새로 만들어지는, 세션 내에서만 사는 레코드)에 둔다. 실패가 일어나는 바로 그 `MPxCommand::doIt` 호출 안에서, 그 순간 살아있는 노드/플러그 이름으로 매번 새로 만든다. `book`은 건드리지 않는다 — `BookEntry`에는 여전히 사람이 읽는 `remedy` 텍스트만 있다(`maroDiagRegisterRemedy`로 사용자가 등록하는 것, 이미 구현돼 있음). 이 설계는 §4.1이 걱정한 것("`remedyAction`은 임의 코드가 아니다")을 그대로 지키면서 스펙이 놓친 staleness 문제를 피한다.

Task 4에서 리뷰어가 이 판단에 동의하지 않으면(예: "book에도 필요하다"), 그것은 사람이 결정할 사안이다 — 구현자는 이 판단을 뒤집지 말고 컨트롤러에게 올린다.

## Global Constraints

- C++17, 네임스페이스 `maro`, 접두사 `maro`, UTF-8 소스
- **`maro_diag`는 Maya 헤더로부터 자유롭게 유지한다** — `RemedyAction`과 그 서술 함수가 여기 들어가며, 그것이 gtest로 덮이는 이유다
- **예외는 Maya 콜백을 넘지 않는다** — `MaroMainThreadQueue`의 타이머 콜백과 `maroApplyRemedy`/`maroDiagRequestRemedy`의 `doIt`이 특히 해당된다
- **진단 경로는 지식 저장소(`book`)에 닿지 못해서 실패하지 않는다** — 이 플랜의 해법 판단은 애초에 book을 보지 않으므로 이 규율은 자동으로 지켜진다
- **`boad`가 진단의 단일 출구다**
- **워커 스레드에서 Maya API를 부르지 않는다** — 이 플랜이 손대는 6개 실패 자리는 전부 `MPxCommand::doIt`이며 Maya 커맨드 디스패치는 항상 메인 스레드이므로 이 플랜에서는 걱정할 필요가 없다(참고용으로 명시)
- **순서를 정하는 어떤 판단도 시각을 읽지 않는다** — 전부 순번(`sequence`)을 본다. `BoadMaro::findRecordBySequence`가 이 규율을 따른다
- Maya 테스트는 `unloadPlugin` 전에 `cmds.file(new=True, force=True)`를 부른다
- 다음 경로는 건드리지 않는다: `src/control_bridge/`, `src/image_bridge/`, `src/Maro_library/`, `MaroCmd.cpp`, `moveTool.cpp`, `rosSimCmd.cpp`, `Maro_DebugUtility/`, `Maro_Management/`
- 새 테스트는 전부 **일부러 구현을 깨서 실패하는 것까지 확인**한다
- **적용은 `MPxCommand` 경유, 안전한 시점에만, 적용 전후 기록** (원 스펙 §4.3 안전 규칙) — `maroDiagRequestRemedy`는 큐에 넣기만 하고, `maroApplyRemedy`가 실제 되돌릴 수 있는 실행이다
- **자동 적용 없음** — 사용자가 [적용]을 눌러야 한다. 이 플랜의 어떤 커맨드도 스스로 트리거되지 않는다
- **필드 개수는 바뀌지 않는다.** `maroDiagPanelDetail`의 14필드, `maroDiagPanelRows`의 8필드는 B-1a/B-1b-1이 이미 확정했고 `applyAvailable`/`applyUnavailableReason`도 B-1a가 이미 예약해 뒀다(`PanelView.h`). 이 플랜은 그 두 필드의 **내용**만 채운다 — Python `DETAIL_FIELDS`/`ROW_FIELDS` 상수도 `tests/maya/test_panel_commands.py`의 교차 검증도 바꾸지 않는다
- 빌드 환경: `Launch-VsDevShell.ps1`은 이 머신에서 `vswhere.exe`를 못 찾아 `INCLUDE`/`LIB`를 비운 채 조용히 성공한다. **빌드와 같은 PowerShell 호출 안에서** `VsDevCmd.bat`를 설정한다

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cd C:\Users\ckd30\Projects\Maya_Ros_Sim
cmake --build out/build --config Release
```

빌드가 `LNK1168`로 실패하면 잔존 `mayapy.exe`가 DLL을 잡고 있는 것이다: `Get-CimInstance Win32_Process -Filter "Name='mayapy.exe'" | Invoke-CimMethod -MethodName Terminate`.

**`--config Release`/`-C Release`를 항상 명시한다.** 이 저장소의 `out/build`는 CMake Visual Studio 제너레이터(멀티 컨피그)라, 컨피그를 안 주면 `cmake --build`가 Debug로 링크를 시도하다가 `LNK2038`(`_ITERATOR_DEBUG_LEVEL` 불일치, `maro_diag`/`maro_transform`이 `src/maro_plugin/CMakeLists.txt`가 여는 devkit의 Debug CRT 오버라이드 스코프 밖에서 먼저 add_subdirectory되기 때문)로 죽는다. Task 5가 이걸 처음 밟고 진단했다 — 저장소 전체에 걸친 기존 버그이고 이 플랜이 만든 게 아니므로 고치지 않는다(아래 "알려진 사전 결함" 참고). Release는 이 불일치를 그냥 비켜 간다.

**알려진, 이 플랜과 무관한 사전 결함 (고치지 않고 기록만 한다):**
1. 위의 Debug 링크 실패 (`src/maro_plugin/CMakeLists.txt`의 devkit 포함이 자기 디렉터리 스코프에만 CRT 플래그를 걺, `main`에도 존재 확인함).
2. `MARO_DIAG_PANEL_PY_OUT`(`src/maro_plugin/CMakeLists.txt`)이 컨피그별 경로가 아니라 `${CMAKE_CURRENT_BINARY_DIR}/maroDiagPanel.py` 고정 경로에 `maroDiagPanel.py`를 놓는데, `.mll`은 항상 `Debug/`나 `Release/` 하위에 있다 -- 어느 컨피그로 빌드해도 `test_panel_commands.py`가 그 파일을 못 찾는다(`ModuleNotFoundError`). `main`에도 동일하게 존재 확인함. 이 실패 하나만 빼고 전체 스위트를 본다: 이 플랜의 완료 기준은 "128/129, 이 사전 결함 하나만 예외"다.

두 결함 모두 `main`에 이미 있고 이 플랜의 어떤 태스크도 `src/maro_plugin/CMakeLists.txt`를 건드리지 않으므로 이 브랜치가 만든 게 아니다. 최종 전체 브랜치 리뷰에서 "왜 129개 중 1개가 실패하냐"고 물으면 이 항목을 가리키면 된다.

## 범위 밖

- **`WouldCreateCycle`에는 구조화된 해법을 달지 않는다.** 원 스펙 §4.2 표는 이것을 `disconnect`로 분류하지만, 실제 호출 자리(`MaroConnectAxisCommand::doIt`, `wouldCreateCycle()` 검사)는 연결이 만들어지기 **전에** 거부하므로 끊을 기존 엣지가 없다 — 순환의 어느 지점을 끊어야 하는지는 `wouldCreateCycle()`의 내부 탐색(부모 체인을 걷는 루프)이 지금 그 엣지를 돌려주지 않아서 알 수 없다. 이 실패는 분석까지만 제공한다(`applyAvailable=false`, 이유는 `"NoActionRecorded"`) — 원 스펙 §4.3이 말하는 "적용 불가가 일급 케이스다"의 정직한 사례다. 나중에 `wouldCreateCycle()`이 걸린 엣지를 돌려주도록 확장되면 별도 작업으로 추가한다
- Qt 위젯판 패널, 첫 로드 안내(B-2) — 계속 범위 밖
- 감시자 프로세스, `offix`, `ghost`, `OSbridge`(Layer C) — 계속 범위 밖
- `RemedyAction`을 사용자가 UI에서 직접 편집/등록하는 기능 — 원 스펙 §4.1이 임의 코드 실행을 막기 위해 구조화된 동작만 허용하는데, 사용자가 구조화된 동작을 타이핑으로 등록하게 하면 그 경계가 다시 뚫린다. 사람이 등록하는 것은 여전히 `remedy`(사람이 읽는 텍스트, `maroDiagRegisterRemedy`)뿐이다

## 파일 구조

| 파일 | 책임 |
|---|---|
| `src/maro_diag/include/maro_diag/RemedyAction.h` / `src/RemedyAction.cpp` | 해법 동작 타입과 사람이 읽는 서술. Maya도 book도 모른다 |
| `src/maro_plugin/MaroMainThreadQueue.h` / `.cpp` | 상시 0.1초 타이머 + 대기 중인 `std::function<void()>` 큐. 플러그인 로드부터 언로드까지 항상 돈다 |
| `src/maro_plugin/MaroRemedyCommands.h` / `.cpp` | `maroDiagRequestRemedy`(큐에 넣기만) / `maroApplyRemedy`(실제 되돌릴 수 있는 실행) |
| `src/maro_plugin/MaroCommands.cpp` | (수정) 6개 실패 자리가 구체적인 `RemedyAction`을 채워 `BoadMaro::error()`에 넘긴다 |
| `src/maro_plugin/MaroDiag.h` / `.cpp` | (수정) `error()`가 `RemedyAction`을 받고, `findRecordBySequence()` 추가 |
| `src/maro_plugin/MaroDiagCommands.h` / `.cpp` | (수정) 테스트 전용 조회/큐 확인 커맨드 추가 |
| `src/maro_diag/include/maro_diag/PanelPresenter.h`(수정 없음) / `src/PanelPresenter.cpp` | (수정) `applyAvailable`/`applyUnavailableReason`/`remedyText` 실제 판단 |
| `src/maro_plugin/MaroPanelCommands.cpp` | (수정) 대상 노드 실존 여부를 실제로 확인해 프레젠터에 건넨다 |
| `python/maroDiagPanel.py` | (수정) [적용] 버튼 |
| `docs/maro-panel-manual-checklist.md` | (수정) 새 수동 확인 항목 |

---

### Task 1: `RemedyAction` 타입과 서술 문구

**Files:**
- Create: `src/maro_diag/include/maro_diag/RemedyAction.h`
- Create: `src/maro_diag/src/RemedyAction.cpp`
- Create: `tests/diag/test_remedy_action.cpp`
- Modify: `src/maro_diag/include/maro_diag/DiagRecord.h`, `src/maro_diag/CMakeLists.txt`, `tests/CMakeLists.txt`

**Interfaces:**
- Produces: `maro::RemedyActionKind`(enum), `maro::RemedyAction`(struct), `maro::describeRemedyAction(const RemedyAction&) -> std::string`. `maro::DiagRecord`에 `RemedyAction remedyAction;` 필드 추가

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/diag/test_remedy_action.cpp`:

```cpp
#include <gtest/gtest.h>

#include "maro_diag/RemedyAction.h"

namespace {

TEST(RemedyAction, NoneKindDescribesAsEmpty) {
    maro::RemedyAction action;
    EXPECT_EQ(action.kind, maro::RemedyActionKind::None);
    EXPECT_EQ(maro::describeRemedyAction(action), "");
}

TEST(RemedyAction, SelectNodeNamesTheNode) {
    maro::RemedyAction action;
    action.kind = maro::RemedyActionKind::SelectNode;
    action.nodeName = "axisA";
    EXPECT_EQ(maro::describeRemedyAction(action), "'axisA' 노드를 선택합니다.");
}

TEST(RemedyAction, SetAttributeNamesNodeAttributeAndValue) {
    maro::RemedyAction action;
    action.kind = maro::RemedyActionKind::SetAttribute;
    action.nodeName = "axisA";
    action.attributeName = "controlMode";
    action.value = 0.0;
    EXPECT_EQ(maro::describeRemedyAction(action),
              "'axisA'.controlMode 값을 0(으)로 설정합니다.");
}

TEST(RemedyAction, DisconnectNamesBothPlugs) {
    maro::RemedyAction action;
    action.kind = maro::RemedyActionKind::Disconnect;
    action.sourcePlug = "cubeA.message";
    action.destPlug = "axisA.targetObject";
    EXPECT_EQ(maro::describeRemedyAction(action),
              "'cubeA.message' -> 'axisA.targetObject' 연결을 끊습니다.");
}

// 정수처럼 보이는 값이 소수점 없이 나오는지 -- 값 부분만 확인한다. 문자열
// 전체에서 '.'이 없는지를 보면 안 된다: "'n'.a" 자체가 노드.어트리뷰트
// 구분자로 마침표를 쓰므로 그 단언은 항상 거짓이 된다 (값과 무관하게).
TEST(RemedyAction, SetAttributeValueHasNoDecimalPoint) {
    maro::RemedyAction action;
    action.kind = maro::RemedyActionKind::SetAttribute;
    action.nodeName = "n";
    action.attributeName = "a";
    action.value = 1.0;
    EXPECT_NE(maro::describeRemedyAction(action).find("값을 1(으)로"), std::string::npos);
}

}  // namespace
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
ctest --test-dir out/build -C Release --output-on-failure -R RemedyAction
```

기대: 컴파일 실패 — `maro_diag/RemedyAction.h`가 없다.

- [ ] **Step 3: `RemedyAction.h` 작성**

`src/maro_diag/include/maro_diag/RemedyAction.h`:

```cpp
#pragma once

#include <string>

namespace maro {

// 해법 동작의 종류. 원 스펙(2026-08-14 설계 §4.1)이 remedyAction을 "임의
// 코드가 아니다"라고 못박은 이유를 그대로 지킨다 -- 여기 없는 동작은 존재하지
// 않는다.
enum class RemedyActionKind {
    None,          // 기계적 해법이 없다. 분석까지만 제공한다.
    SelectNode,    // 씬을 편집하지 않는다. 사용자를 올바른 노드로 데려간다.
    SetAttribute,  // MDGModifier::newPlugValueInt로 적용한다 (현재 유일한
                   // 사용처인 controlMode가 정수 열거값이라 int만 다룬다).
    Disconnect,    // MDGModifier::disconnect(source, dest)로 적용한다.
};

// 실행 가능한 구조화된 해법 하나. DiagRecord에 실려 세션 동안만 산다 --
// book(해시별로 영속)에는 두지 않는다. 이유: book의 해시는 실패의 "자리와
// 종류"만 담을 뿐 이번 발생의 구체적인 노드 이름은 담지 않는다는 것이
// ErrorHash.h의 계약이고, 구체적인 노드 이름을 book에 캐시하면 Layer A
// 최종 리뷰의 Critical Finding C1(다른 발생의 텍스트를 이번 발생인 것처럼
// 재생)과 같은 부류의 버그가 재발한다. 그래서 이 값은 실패가 일어난 바로
// 그 순간, 그 자리에서 살아있는 씬을 보고 매번 새로 만든다 (플랜 서두
// "spec에서 의도적으로 벗어난 지점" 참고).
struct RemedyAction {
    RemedyActionKind kind = RemedyActionKind::None;

    // SelectNode, SetAttribute가 쓴다.
    std::string nodeName;
    // SetAttribute가 쓴다.
    std::string attributeName;
    double value = 0.0;
    // Disconnect가 쓴다. MSelectionList::add가 그대로 받을 수 있는
    // "node.attribute" 모양의 온전한 플러그 이름이다 (MPlug::name() 결과).
    std::string sourcePlug;
    std::string destPlug;
};

// 사람이 읽는 한 문장. book에 등록된 remedy 텍스트가 없을 때 패널이 대신
// 보여주는 설명이다 -- 구조화된 동작이 있는데도 패널에 아무 설명 없이 버튼만
// 뜨면 사용자가 무엇이 바뀌는지 모른 채 누르게 된다.
std::string describeRemedyAction(const RemedyAction& action);

}  // namespace maro
```

- [ ] **Step 4: `RemedyAction.cpp` 작성**

`src/maro_diag/src/RemedyAction.cpp`:

```cpp
#include "maro_diag/RemedyAction.h"

#include <cmath>

namespace maro {

std::string describeRemedyAction(const RemedyAction& action) {
    switch (action.kind) {
        case RemedyActionKind::None:
            return "";
        case RemedyActionKind::SelectNode:
            return "'" + action.nodeName + "' 노드를 선택합니다.";
        case RemedyActionKind::SetAttribute: {
            const long long rounded = std::llround(action.value);
            return "'" + action.nodeName + "'." + action.attributeName +
                   " 값을 " + std::to_string(rounded) + "(으)로 설정합니다.";
        }
        case RemedyActionKind::Disconnect:
            return "'" + action.sourcePlug + "' -> '" + action.destPlug +
                   "' 연결을 끊습니다.";
    }
    return "";
}

}  // namespace maro
```

- [ ] **Step 5: `DiagRecord`에 필드 추가**

`src/maro_diag/include/maro_diag/DiagRecord.h`의 `#include` 목록에 추가:

```cpp
#include "maro_diag/RemedyAction.h"
```

`struct DiagRecord`의 `std::uint64_t timestampMs = 0;` 바로 아래에 추가:

```cpp
    // 이 발생에 대한 구조화된 해법. 없으면 RemedyActionKind::None(기본값).
    // book에서 오지 않는다 -- 위 RemedyAction.h의 주석 참고. 실패가 일어난
    // 자리(MaroCommands.cpp)가 이 발생의 살아있는 씬 상태로 직접 채운다.
    RemedyAction remedyAction;
```

- [ ] **Step 6: 빌드에 등록**

`src/maro_diag/CMakeLists.txt`의 `add_library(maro_diag STATIC` 목록에 `src/RemedyAction.cpp`를 추가:

```cmake
add_library(maro_diag STATIC
    src/ErrorHash.cpp
    src/BookStore.cpp
    src/PanelPresenter.cpp
    src/Journal.cpp
    src/JournalWriter.cpp
    src/JournalReader.cpp
    src/RemedyAction.cpp
)
```

`tests/CMakeLists.txt`의 `add_executable(maro_diag_tests` 목록에 `diag/test_remedy_action.cpp`를 추가:

```cmake
add_executable(maro_diag_tests
    diag/test_error_hash.cpp
    diag/test_book_store.cpp
    diag/test_panel_presenter.cpp
    diag/test_journal_writer.cpp
    diag/test_journal_reader.cpp
    diag/test_remedy_action.cpp
)
```

- [ ] **Step 7: 빌드하고 테스트가 통과하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R RemedyAction
```

기대: 5개 전부 통과.

- [ ] **Step 8: 서술이 진짜로 값을 반영하는지 확인**

`describeRemedyAction`의 `SetAttribute` 분기에서 `action.attributeName`을 빼고 고정 문자열 `"attr"`로 바꾼다.

```bash
cmake --build out/build --config Release && ctest --test-dir out/build -C Release --output-on-failure -R RemedyAction
```

기대: `SetAttributeNamesNodeAttributeAndValue`가 **실패**한다. 확인했으면 되돌린다.

- [ ] **Step 9: 커밋**

```bash
git add src/maro_diag/include/maro_diag/RemedyAction.h src/maro_diag/src/RemedyAction.cpp src/maro_diag/include/maro_diag/DiagRecord.h src/maro_diag/CMakeLists.txt tests/CMakeLists.txt tests/diag/test_remedy_action.cpp
git commit -m "feat: give a diagnostic a structured, describable fix"
```

---

### Task 2: `BoadMaro::error()`가 해법을 받고, 순번으로 레코드를 찾는다

**Files:**
- Modify: `src/maro_plugin/MaroDiag.h`, `src/maro_plugin/MaroDiag.cpp`
- Modify: `src/maro_plugin/MaroDiagCommands.h`, `src/maro_plugin/MaroDiagCommands.cpp` (테스트 전용 조회 커맨드 추가 + `maroDiagEmit` 확장)
- Modify: `src/maro_plugin/MaroPluginMain.cpp` (새 테스트 커맨드 등록/해제)
- Create: `tests/maya/test_remedy_capture.py`
- Modify: `tests/CMakeLists.txt`

**Interfaces:**
- Consumes: `maro::RemedyAction`, `maro::RemedyActionKind` (Task 1)
- Produces: `BoadMaro::error(siteTag, message, context = DgContext{}, remedyAction = RemedyAction{})`(확장), `BoadMaro::findRecordBySequence(std::uint64_t sequence, DiagRecord& out) -> bool`, 테스트 전용 커맨드 `maroDiagQueryRemedyAction -sequence <int>`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/maya/test_remedy_capture.py` (전체 새 파일):

```python
"""error()가 받은 RemedyAction이 레코드에 그대로 실리고, 순번으로 다시
찾아지는지 확인한다. maroDiagEmit의 테스트 전용 확장(-remedyAction 등)만
쓴다 -- 실제 실패 자리 배선은 Task 3에서 별도로 검증한다.
"""
import os

import maya.standalone
maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)

# 1) None(기본값) -- 아무 remedy 플래그도 안 주면 이전과 동일해야 한다.
cmds.maroDiagEmit(severity="error", message="m1", siteTag="T.None")
count = cmds.maroDiagCount()
detail = cmds.maroDiagQuery(index=0)
seq1 = int(detail[10])
kind, nodeName, attrName, value, srcPlug, dstPlug = cmds.maroDiagQueryRemedyAction(sequence=seq1)
assert kind == "none", f"expected no remedy, got {kind}"
print("none OK")

# 2) selectNode
cmds.maroDiagEmit(severity="error", message="m2", siteTag="T.Select",
                  remedyAction="selectNode", remedyNode="axisA")
seq2 = int(cmds.maroDiagQuery(index=0)[10])
kind, nodeName, attrName, value, srcPlug, dstPlug = cmds.maroDiagQueryRemedyAction(sequence=seq2)
assert kind == "selectNode", kind
assert nodeName == "axisA", nodeName
print("selectNode capture OK")

# 3) setAttribute
cmds.maroDiagEmit(severity="error", message="m3", siteTag="T.SetAttr",
                  remedyAction="setAttribute", remedyNode="axisA",
                  remedyAttribute="controlMode", remedyValue=0.0)
seq3 = int(cmds.maroDiagQuery(index=0)[10])
kind, nodeName, attrName, value, srcPlug, dstPlug = cmds.maroDiagQueryRemedyAction(sequence=seq3)
assert kind == "setAttribute", kind
assert nodeName == "axisA" and attrName == "controlMode", (nodeName, attrName)
assert float(value) == 0.0, value
print("setAttribute capture OK")

# 4) disconnect
cmds.maroDiagEmit(severity="error", message="m4", siteTag="T.Disconnect",
                  remedyAction="disconnect", remedySourcePlug="cubeA.message",
                  remedyDestPlug="axisA.targetObject")
seq4 = int(cmds.maroDiagQuery(index=0)[10])
kind, nodeName, attrName, value, srcPlug, dstPlug = cmds.maroDiagQueryRemedyAction(sequence=seq4)
assert kind == "disconnect", kind
assert srcPlug == "cubeA.message" and dstPlug == "axisA.targetObject", (srcPlug, dstPlug)
print("disconnect capture OK")

# 5) 존재하지 않는 순번은 실패해야 한다 -- 스테일 선택을 조용히 다른
# 레코드로 대체하면 안 된다는 것이 이 프로젝트의 확립된 규율이다
# (MaroPanelCommands.cpp의 -sequence 규율과 같다).
try:
    cmds.maroDiagQueryRemedyAction(sequence=999999)
    raised = False
except RuntimeError:
    raised = True
assert raised, "an unknown sequence must fail, not silently return a neighbor"
print("unknown sequence fails OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("test_remedy_capture OK")
```

- [ ] **Step 2: 테스트가 실패하는지 확인 (아직 등록 전)**

이 시점에는 `ctest`에 등록돼 있지 않으므로 직접 실행한다(Step 8에서 CMake 등록 뒤에는 `ctest`로 돌린다):

```powershell
& "$env:MAYA_LOCATION\bin\mayapy.exe" tests\maya\test_remedy_capture.py
```

기대: `AttributeError` 또는 `RuntimeError` — `maroDiagQueryRemedyAction`도 `maroDiagEmit`의 `remedyAction` 플래그도 아직 없다.

(플랜의 다른 mayapy 태스크들과 마찬가지로 `MARO_PLUGIN_PATH`/`PATH`/`MARO_DIAG_BOOK_DIR`는 Step 8에서 CTest가 설정해 준다. 직접 실행 시에는 `MARO_PLUGIN_PATH` 환경변수를 `.mll` 전체 경로로 미리 설정해야 위 스크립트의 `cmds.loadPlugin(plugin)`이 찾는다 — 다른 `tests/maya/*.py`가 이미 이 관례를 따른다. 플러그인 이름 `"maro"`로 바로 부르지 않는 이유는 `MAYA_PLUG_IN_PATH`가 이 저장소 어디서도 설정되지 않기 때문이다.)

- [ ] **Step 3: `MaroDiag.h`에 `error()` 확장과 `findRecordBySequence` 선언 추가**

`MaroDiag.h`의 `#include` 목록에 추가:

```cpp
#include "maro_diag/RemedyAction.h"
```

`error()` 선언을 아래로 교체:

```cpp
    // siteTag: 이 실패의 자리와 종류만 담는 불변 식별자 (maro::hashError
    // 계약, Task 1). context는 Task 4에서 onfix::capture()로 채운다 -- 지금은
    // 항상 기본값(전부 빈 문자열)이다.
    //
    // remedyAction: 이 발생에 대한 구조화된 해법. book에서 오지 않는다 --
    // 호출부가 이 순간 살아있는 씬을 보고 직접 채운다 (RemedyAction.h,
    // 플랜 서두 "spec에서 의도적으로 벗어난 지점" 참고). 기본값
    // RemedyActionKind::None은 "해법 없음"이며 기존 호출부 전부가 이
    // 기본값을 그대로 탄다.
    static void error(const std::string& siteTag, const MString& message,
                       const DgContext& context = DgContext{},
                       const RemedyAction& remedyAction = RemedyAction{});
```

`resetForTest()` 선언 아래, `private:` 앞에 추가:

```cpp
    // sequence로 레코드 하나를 찾는다. 순번은 세션 전역에서 유일하고
    // 재사용되지 않으므로(MaroPanelCommands.cpp가 이미 이 방식으로
    // -sequence를 구현했다), 화면이 그려진 시점과 지금(적용 클릭 시점)
    // 사이에 다른 진단이 더 들어와도 항상 사용자가 실제로 고른 그 레코드를
    // 돌려준다. 찾지 못하면 false -- 존재한 적 없는 순번이나 세션이 리셋된
    // 뒤의 스테일 값을 엉뚱한 이웃으로 대체하지 않는다.
    static bool findRecordBySequence(std::uint64_t sequence, DiagRecord& out);
```

- [ ] **Step 4: `MaroDiag.cpp`에서 `error()`를 확장하고 `findRecordBySequence` 구현**

`error()`의 시그니처를 교체:

```cpp
void BoadMaro::error(const std::string& siteTag, const MString& message,
                      const DgContext& context, const RemedyAction& remedyAction) {
    DiagRecord rec;
    stampTimestamp(rec);
    rec.severity = DiagSeverity::Error;
    rec.context = context;
    // book에서 오지 않는다 -- 항상 이 호출이 준 값 그대로다. 아래 book
    // 캐시 히트 분기가 rec.remedy/rec.priorAnalysis는 book 것으로 덮어써도
    // remedyAction은 절대 덮어쓰지 않는다 (RemedyAction.h 계약).
    rec.remedyAction = remedyAction;
```

(그 아래 `rec.siteTag = siteTag;`부터 함수 끝까지는 그대로 둔다 — book 캐시 히트/미스 분기가 `rec.message`/`rec.priorAnalysis`/`rec.remedy`/`rec.servedFromBook`을 채우는 기존 로직은 손대지 않는다.)

파일 끝, `resetForTest()` 구현 근처(아무 곳이나 클래스 정적 메서드가 모여 있는 자리)에 추가:

```cpp
bool BoadMaro::findRecordBySequence(std::uint64_t sequence, DiagRecord& out) {
    std::lock_guard<std::mutex> lock(mutex());
    for (const DiagRecord& rec : stream()) {
        if (rec.sequence == sequence) {
            out = rec;
            return true;
        }
    }
    return false;
}
```

- [ ] **Step 5: `MaroDiagCommands.h`에 새 테스트 전용 커맨드 선언**

`MaroDiagCommands.h`의 `#include` 목록에 추가:

```cpp
#include "maro_diag/RemedyAction.h"
```

파일 끝, `MaroJournalCrashAdjacentTagsCommand` 선언 아래에 추가:

```cpp
// 테스트 전용. -sequence <int>. 그 레코드의 RemedyAction을 필드 6개로:
// kind("none"|"selectNode"|"setAttribute"|"disconnect"), nodeName,
// attributeName, value(문자열로 변환된 double), sourcePlug, destPlug.
// 존재하지 않는 sequence는 실패한다 (MaroPanelCommands.cpp의 -sequence
// 규율과 같다 -- 스테일 선택을 조용히 다른 레코드로 대체하지 않는다).
class MaroDiagQueryRemedyActionCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
};
```

- [ ] **Step 6: `MaroDiagCommands.cpp`에서 `maroDiagEmit`을 확장하고 새 커맨드 구현**

`MaroDiagEmitCommand::newSyntax()`에 플래그 다섯 개를 추가한다. 파일 상단 익명 네임스페이스의 플래그 상수 목록(`kRemedyFlag`/`kRemedyFlagLong` 아래)에 추가:

```cpp
// maroDiagEmit(-severity error) 전용 테스트 확장. 지정하지 않으면 이전과
// 바이트 단위로 동일하게 동작한다(RemedyActionKind::None).
const char* kRemedyActionFlag = "-ra";
const char* kRemedyActionFlagLong = "-remedyAction";
const char* kRemedyNodeFlag = "-rn";
const char* kRemedyNodeFlagLong = "-remedyNode";
const char* kRemedyAttributeFlag = "-rat";
const char* kRemedyAttributeFlagLong = "-remedyAttribute";
const char* kRemedyValueFlag = "-rv";
const char* kRemedyValueFlagLong = "-remedyValue";
const char* kRemedySourcePlugFlag = "-rsp";
const char* kRemedySourcePlugFlagLong = "-remedySourcePlug";
const char* kRemedyDestPlugFlag = "-rdp";
const char* kRemedyDestPlugFlagLong = "-remedyDestPlug";
const char* kSequenceFlag = "-sq";
const char* kSequenceFlagLong = "-sequence";
```

`MaroDiagEmitCommand::newSyntax()`의 `return syntax;` 앞에 추가:

```cpp
    syntax.addFlag(kRemedyActionFlag, kRemedyActionFlagLong, MSyntax::kString);
    syntax.addFlag(kRemedyNodeFlag, kRemedyNodeFlagLong, MSyntax::kString);
    syntax.addFlag(kRemedyAttributeFlag, kRemedyAttributeFlagLong, MSyntax::kString);
    syntax.addFlag(kRemedyValueFlag, kRemedyValueFlagLong, MSyntax::kDouble);
    syntax.addFlag(kRemedySourcePlugFlag, kRemedySourcePlugFlagLong, MSyntax::kString);
    syntax.addFlag(kRemedyDestPlugFlag, kRemedyDestPlugFlagLong, MSyntax::kString);
```

`MaroDiagEmitCommand::doIt`의 `else if (severity == "error") {` 블록 안, `ctx.typeUnavailable = argData.isFlagSet(kTypeUnavailableFlag);` 바로 아래, `BoadMaro::error(siteTag.asChar(), message, ctx);` 호출을 아래로 교체:

```cpp
            RemedyAction remedy;
            if (argData.isFlagSet(kRemedyActionFlag)) {
                MString kindStr;
                argData.getFlagArgument(kRemedyActionFlag, 0, kindStr);
                if (kindStr == "selectNode") {
                    remedy.kind = RemedyActionKind::SelectNode;
                } else if (kindStr == "setAttribute") {
                    remedy.kind = RemedyActionKind::SetAttribute;
                } else if (kindStr == "disconnect") {
                    remedy.kind = RemedyActionKind::Disconnect;
                } else {
                    MGlobal::displayError(
                        MString("Maro: unknown -remedyAction '") + kindStr + "'.");
                    return MS::kFailure;
                }
                if (argData.isFlagSet(kRemedyNodeFlag)) {
                    MString v;
                    argData.getFlagArgument(kRemedyNodeFlag, 0, v);
                    remedy.nodeName = v.asChar();
                }
                if (argData.isFlagSet(kRemedyAttributeFlag)) {
                    MString v;
                    argData.getFlagArgument(kRemedyAttributeFlag, 0, v);
                    remedy.attributeName = v.asChar();
                }
                if (argData.isFlagSet(kRemedyValueFlag)) {
                    argData.getFlagArgument(kRemedyValueFlag, 0, remedy.value);
                }
                if (argData.isFlagSet(kRemedySourcePlugFlag)) {
                    MString v;
                    argData.getFlagArgument(kRemedySourcePlugFlag, 0, v);
                    remedy.sourcePlug = v.asChar();
                }
                if (argData.isFlagSet(kRemedyDestPlugFlag)) {
                    MString v;
                    argData.getFlagArgument(kRemedyDestPlugFlag, 0, v);
                    remedy.destPlug = v.asChar();
                }
            }
            BoadMaro::error(siteTag.asChar(), message, ctx, remedy);
```

파일 끝(`MaroJournalCrashAdjacentTagsCommand::doIt` 구현 아래)에 새 커맨드 구현을 추가:

```cpp
namespace {
const char* remedyKindName(RemedyActionKind kind) {
    switch (kind) {
        case RemedyActionKind::None: return "none";
        case RemedyActionKind::SelectNode: return "selectNode";
        case RemedyActionKind::SetAttribute: return "setAttribute";
        case RemedyActionKind::Disconnect: return "disconnect";
    }
    return "none";
}
}  // namespace

void* MaroDiagQueryRemedyActionCommand::creator() {
    return new MaroDiagQueryRemedyActionCommand();
}

MSyntax MaroDiagQueryRemedyActionCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag(kSequenceFlag, kSequenceFlagLong, MSyntax::kLong);
    return syntax;
}

MStatus MaroDiagQueryRemedyActionCommand::doIt(const MArgList& args) {
    try {
        MStatus status;
        MArgDatabase argData(newSyntax(), args, &status);
        if (!status) return status;

        if (!argData.isFlagSet(kSequenceFlag)) {
            MGlobal::displayError("Maro: maroDiagQueryRemedyAction requires -sequence.");
            return MS::kFailure;
        }
        int sequenceArg = -1;
        argData.getFlagArgument(kSequenceFlag, 0, sequenceArg);
        if (sequenceArg < 0) {
            MGlobal::displayError(
                "Maro: maroDiagQueryRemedyAction -sequence must not be negative.");
            return MS::kFailure;
        }

        DiagRecord rec;
        if (!BoadMaro::findRecordBySequence(static_cast<std::uint64_t>(sequenceArg), rec)) {
            MGlobal::displayError(
                "Maro: maroDiagQueryRemedyAction could not resolve sequence.");
            return MS::kFailure;
        }

        MStringArray result;
        result.append(remedyKindName(rec.remedyAction.kind));
        result.append(MString(rec.remedyAction.nodeName.c_str()));
        result.append(MString(rec.remedyAction.attributeName.c_str()));
        result.append(MString(std::to_string(rec.remedyAction.value).c_str()));
        result.append(MString(rec.remedyAction.sourcePlug.c_str()));
        result.append(MString(rec.remedyAction.destPlug.c_str()));
        setResult(result);
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(
            MString("Maro: maroDiagQueryRemedyAction failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError(
            "Maro: maroDiagQueryRemedyAction failed with unknown error.");
        return MS::kFailure;
    }
}
```

- [ ] **Step 7: `MaroPluginMain.cpp`에 새 커맨드 등록/해제**

`initializePlugin`의 `maroDiagRegisterRemedy` 등록 블록 바로 뒤에 추가:

```cpp
    status = plugin.registerCommand("maroDiagQueryRemedyAction",
                                    maro::MaroDiagQueryRemedyActionCommand::creator,
                                    maro::MaroDiagQueryRemedyActionCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroDiagQueryRemedyAction");
        return status;
    }
```

`uninitializePlugin`의 `plugin.deregisterCommand("maroDiagRegisterRemedy");` 바로 **위**에 추가(등록의 역순 규율):

```cpp
        plugin.deregisterCommand("maroDiagQueryRemedyAction");
```

- [ ] **Step 8: 빌드에 등록하고 테스트가 통과하는지 확인**

`tests/CMakeLists.txt`의 `foreach(maya_test ...)` 목록에 `remedy_capture`를 추가(기존 `journal` 옆):

```cmake
    foreach(maya_test load axis_node binding capability_stack delete_rules
                      robustness diag_boad diag_onfix diag_book
                      diag_book_cross_session diag_remedy
                      diag_degraded diag_degraded_remedy diag_thread
                      panel_commands journal remedy_capture)
```

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R "remedy_capture|maro_diag_tests"
```

기대: 전부 통과.

- [ ] **Step 9: 알 수 없는 순번이 진짜로 실패하는지 확인**

`MaroDiagQueryRemedyActionCommand::doIt`의 `if (!BoadMaro::findRecordBySequence(...))` 블록 안 `return MS::kFailure;`를 `return MS::kSuccess;`로 바꾼다(찾지 못해도 성공한 것처럼 만든다).

```bash
cmake --build out/build --config Release && ctest --test-dir out/build -C Release --output-on-failure -R remedy_capture
```

기대: `unknown sequence fails` 검증에서 **실패**한다(빈 배열을 6개로 언패킹하다 예외가 나거나 `raised`가 `False`). 확인했으면 되돌린다.

- [ ] **Step 10: 커밋**

```bash
git add src/maro_plugin/MaroDiag.h src/maro_plugin/MaroDiag.cpp src/maro_plugin/MaroDiagCommands.h src/maro_plugin/MaroDiagCommands.cpp src/maro_plugin/MaroPluginMain.cpp tests/maya/test_remedy_capture.py tests/CMakeLists.txt
git commit -m "feat: let a diagnostic carry its own structured fix"
```

---

### Task 3: 알려진 실패 여섯 곳에 구체적인 해법을 채운다

**Files:**
- Modify: `src/maro_plugin/MaroCommands.cpp`
- Modify: `tests/maya/test_remedy_capture.py` (실제 실패 자리 검증 추가)

**Interfaces:**
- Consumes: `maro::RemedyAction`, `maro::RemedyActionKind` (Task 1), `BoadMaro::error()`의 4번째 인자 (Task 2)
- Produces: 없음 (호출부 배선만)

이 태스크는 **여섯 개의 개별 편집**이다. 각 편집은 독립적이므로 순서는 상관없지만, 전부 끝난 뒤 한 번에 빌드/테스트한다.

- [ ] **Step 1: `TargetNotTransform` — 부모 transform을 선택하게 한다**

`MaroCommands.cpp`의 `MaroBindAxisCommand::doIt`에서 아래 블록을 찾는다:

```cpp
        MDagPath targetPath;
        if (!MDagPath::getAPathTo(targetObj, targetPath) ||
            !targetPath.hasFn(MFn::kTransform)) {
            MFnDependencyNode targetFn(targetObj);
            maro::BoadMaro::error(
                "MaroBindAxisCommand.TargetNotTransform",
                MString("Maro: '") + targetFn.name() +
                "' is not a transform, so an axis cannot drive it. "
                "Select the transform node instead of its shape.",
                maro::onfix::capture(targetFn.typeName(), "targetObject", axisFn.name()));
            return MS::kFailure;
        }
```

아래로 교체:

```cpp
        MDagPath targetPath;
        if (!MDagPath::getAPathTo(targetObj, targetPath) ||
            !targetPath.hasFn(MFn::kTransform)) {
            MFnDependencyNode targetFn(targetObj);

            // 선택된 노드가 shape이면(가장 흔한 경우) 그 부모 transform을
            // 골라 선택 대상으로 삼는다 -- shape 자체를 선택해도 사용자가
            // "transform을 대신 선택하라"는 말의 대상을 못 찾는다. 부모를
            // 못 구하면(예: targetObj가 DAG 객체가 아니어서 targetPath 자체가
            // 무효) 해법 없이 분석만 제공한다 -- 억지로 잘못된 노드를
            // 고르는 것보다 정직하다.
            maro::RemedyAction remedy;
            if (targetPath.isValid() && targetPath.length() > 0) {
                MDagPath parentPath = targetPath;
                parentPath.pop();
                if (parentPath.isValid()) {
                    MFnDagNode parentFn(parentPath);
                    remedy.kind = maro::RemedyActionKind::SelectNode;
                    remedy.nodeName = parentFn.fullPathName().asChar();
                }
            }

            maro::BoadMaro::error(
                "MaroBindAxisCommand.TargetNotTransform",
                MString("Maro: '") + targetFn.name() +
                "' is not a transform, so an axis cannot drive it. "
                "Select the transform node instead of its shape.",
                maro::onfix::capture(targetFn.typeName(), "targetObject", axisFn.name()),
                remedy);
            return MS::kFailure;
        }
```

`MaroCommands.cpp` 상단 `#include` 목록에 `<maya/MFnDagNode.h>`가 없으면 추가한다(같은 파일이 이미 `MDagPath`를 쓰므로 `<maya/MDagPath.h>`는 있을 것이다 — 없으면 그것도 추가).

- [ ] **Step 2: `NotMaroAxisNode` (첫 번째 자리, `MaroBindAxisCommand`) — 그 노드를 선택하게 한다**

같은 파일, 같은 함수에서:

```cpp
        MFnDependencyNode axisFn(axisObj);
        if (axisFn.typeId() != MaroAxisNode::id) {
            maro::BoadMaro::error(
                "MaroBindAxisCommand.NotMaroAxisNode",
                MString("Maro: '") + axisFn.name() + "' is not a maroAxis node.",
                maro::onfix::capture(axisFn.typeName(), "", axisFn.name()));
            return MS::kFailure;
        }
```

아래로 교체:

```cpp
        MFnDependencyNode axisFn(axisObj);
        if (axisFn.typeId() != MaroAxisNode::id) {
            maro::RemedyAction remedy;
            remedy.kind = maro::RemedyActionKind::SelectNode;
            remedy.nodeName = axisFn.name().asChar();
            maro::BoadMaro::error(
                "MaroBindAxisCommand.NotMaroAxisNode",
                MString("Maro: '") + axisFn.name() + "' is not a maroAxis node.",
                maro::onfix::capture(axisFn.typeName(), "", axisFn.name()), remedy);
            return MS::kFailure;
        }
```

- [ ] **Step 3: `NotMaroAxisNode` (두 번째 자리, `MaroConnectAxisCommand`) — 진짜 문제인 쪽을 선택하게 한다**

`MaroConnectAxisCommand::doIt`에서:

```cpp
        if (childFn.typeId() != MaroAxisNode::id ||
            parentFn.typeId() != MaroAxisNode::id) {
            const bool childIsOffender = childFn.typeId() != MaroAxisNode::id;
            const MFnDependencyNode& offenderFn = childIsOffender ? childFn : parentFn;
            maro::BoadMaro::error(
                "MaroConnectAxisCommand.NotMaroAxisNode",
                "Maro: maroConnectAxis expects two maroAxis nodes.",
                maro::onfix::capture(offenderFn.typeName(), "", offenderFn.name()));
            return MS::kFailure;
        }
```

아래로 교체:

```cpp
        if (childFn.typeId() != MaroAxisNode::id ||
            parentFn.typeId() != MaroAxisNode::id) {
            const bool childIsOffender = childFn.typeId() != MaroAxisNode::id;
            const MFnDependencyNode& offenderFn = childIsOffender ? childFn : parentFn;
            maro::RemedyAction remedy;
            remedy.kind = maro::RemedyActionKind::SelectNode;
            remedy.nodeName = offenderFn.name().asChar();
            maro::BoadMaro::error(
                "MaroConnectAxisCommand.NotMaroAxisNode",
                "Maro: maroConnectAxis expects two maroAxis nodes.",
                maro::onfix::capture(offenderFn.typeName(), "", offenderFn.name()), remedy);
            return MS::kFailure;
        }
```

- [ ] **Step 4: `SelfParent` — 그 노드를 선택하게 한다**

`MaroConnectAxisCommand::doIt`에서:

```cpp
        if (childObj == parentObj) {
            maro::BoadMaro::error(
                "MaroConnectAxisCommand.SelfParent",
                MString("Maro: '") + childFn.name() + "' cannot be its own parent.",
                maro::onfix::capture(childFn.typeName(), "parentAxis", childFn.name()));
            return MS::kFailure;
        }
```

아래로 교체:

```cpp
        if (childObj == parentObj) {
            maro::RemedyAction remedy;
            remedy.kind = maro::RemedyActionKind::SelectNode;
            remedy.nodeName = childFn.name().asChar();
            maro::BoadMaro::error(
                "MaroConnectAxisCommand.SelfParent",
                MString("Maro: '") + childFn.name() + "' cannot be its own parent.",
                maro::onfix::capture(childFn.typeName(), "parentAxis", childFn.name()),
                remedy);
            return MS::kFailure;
        }
```

- [ ] **Step 5: `InvalidControlMode` — 안전한 기본값(Manual=0)으로 되돌린다**

`MaroSetControlModeCommand::doIt`에서:

```cpp
        if (mode != 0 && mode != 1) {
            maro::BoadMaro::error(
                "MaroSetControlModeCommand.InvalidControlMode",
                "Maro: control mode must be 0 (Manual) or 1 (ROS).",
                maro::onfix::capture("", "controlMode", axisName));
            return MS::kFailure;
        }
```

아래로 교체:

```cpp
        if (mode != 0 && mode != 1) {
            // 안전한 기본값은 Manual(0)이다 -- 잘못된 모드로 인해 사용자가
            // 의도하지 않은 ROS 제어가 걸리는 쪽보다, 아무것도 안 하던
            // Manual로 떨어지는 쪽이 덜 놀랍다.
            maro::RemedyAction remedy;
            remedy.kind = maro::RemedyActionKind::SetAttribute;
            remedy.nodeName = axisName.asChar();
            remedy.attributeName = "controlMode";
            remedy.value = 0.0;
            maro::BoadMaro::error(
                "MaroSetControlModeCommand.InvalidControlMode",
                "Maro: control mode must be 0 (Manual) or 1 (ROS).",
                maro::onfix::capture("", "controlMode", axisName), remedy);
            return MS::kFailure;
        }
```

- [ ] **Step 6: `AxisAlreadyBound` — 기존 바인딩을 끊게 한다**

`MaroBindAxisCommand::doIt`에서:

```cpp
            MFnDependencyNode boundFn(boundObj);
            maro::BoadMaro::error(
                "MaroBindAxisCommand.AxisAlreadyBound",
                MString("Maro: '") + axisFn.name() + "' is already bound to '" +
                boundFn.name() + "'. Disconnect it first before binding it to '" +
                targetFn.name() + "'.",
                maro::onfix::capture(targetFn.typeName(), "targetObject", axisFn.name()));
            return MS::kFailure;
```

아래로 교체:

```cpp
            MFnDependencyNode boundFn(boundObj);
            maro::RemedyAction remedy;
            remedy.kind = maro::RemedyActionKind::Disconnect;
            remedy.sourcePlug = axisSources[0].name().asChar();
            remedy.destPlug = axisTarget.name().asChar();
            maro::BoadMaro::error(
                "MaroBindAxisCommand.AxisAlreadyBound",
                MString("Maro: '") + axisFn.name() + "' is already bound to '" +
                boundFn.name() + "'. Disconnect it first before binding it to '" +
                targetFn.name() + "'.",
                maro::onfix::capture(targetFn.typeName(), "targetObject", axisFn.name()),
                remedy);
            return MS::kFailure;
```

- [ ] **Step 7: `ObjectAlreadyHasAxis` — 기존 바인딩을 끊게 한다**

`MaroBindAxisCommand::doIt`에서:

```cpp
                if (otherFn.typeId() == MaroAxisNode::id) {
                    maro::BoadMaro::error(
                        "MaroBindAxisCommand.ObjectAlreadyHasAxis",
                        MString("Maro: '") + targetFn.name() +
                        "' is already bound to axis '" + otherFn.name() +
                        "'. One object carries exactly one axis.",
                        maro::onfix::capture(targetFn.typeName(), "targetObject",
                                             axisFn.name()));
                    return MS::kFailure;
                }
```

아래로 교체:

```cpp
                if (otherFn.typeId() == MaroAxisNode::id) {
                    maro::RemedyAction remedy;
                    remedy.kind = maro::RemedyActionKind::Disconnect;
                    remedy.sourcePlug = targetMessage.name().asChar();
                    remedy.destPlug = destinations[i].name().asChar();
                    maro::BoadMaro::error(
                        "MaroBindAxisCommand.ObjectAlreadyHasAxis",
                        MString("Maro: '") + targetFn.name() +
                        "' is already bound to axis '" + otherFn.name() +
                        "'. One object carries exactly one axis.",
                        maro::onfix::capture(targetFn.typeName(), "targetObject",
                                             axisFn.name()),
                        remedy);
                    return MS::kFailure;
                }
```

- [ ] **Step 8: `WouldCreateCycle`에는 손대지 않는다 — 이유를 주석으로 남긴다**

`MaroConnectAxisCommand::doIt`에서 `wouldCreateCycle` 검사 바로 위에 주석만 추가한다(로직은 그대로):

```cpp
        // 이 실패에는 구조화된 해법을 달지 않는다 (플랜
        // 2026-08-19-maro-layer-b1b2-remedy.md "범위 밖" 참고): 이 검사는
        // 연결이 만들어지기 *전에* 거부하므로 끊을 기존 엣지가 없고,
        // wouldCreateCycle()의 내부 탐색은 순환의 어느 지점을 끊어야
        // 하는지 돌려주지 않는다. 분석까지만 제공한다.
        if (wouldCreateCycle(childObj, parentObj)) {
```

- [ ] **Step 9: `test_remedy_capture.py`에 실제 자리 검증 추가**

Step 1의 파일 끝, `cmds.file(new=True, force=True)` 호출 **앞**에 삽입(즉 정리 직전):

```python
# --- 여기부터는 테스트 전용 확장이 아니라 Task 3에서 배선한 실제 실패
# 자리를 직접 유발해 RemedyAction이 진짜로 채워지는지 확인한다. ---

cube = cmds.polyCube()[0]
shape = cmds.listRelatives(cube, shapes=True)[0]
axisA = cmds.createNode("maroAxis", name="axisA")
axisB = cmds.createNode("maroAxis", name="axisB")

# TargetNotTransform: shape을 바인딩 시도 -> 부모 transform을 selectNode.
try:
    cmds.maroBindAxis(axisA, shape)
    raised = False
except RuntimeError:
    raised = True
assert raised, "binding a shape must fail"
seq = int(cmds.maroDiagQuery(index=0)[10])
kind, nodeName, _, _, _, _ = cmds.maroDiagQueryRemedyAction(sequence=seq)
# MFnDagNode::fullPathName()이 낸 값이라 선행 "|"가 붙는다 -- 짧은 이름
# 그대로("pCube1")가 아니라 정규 전체 경로("|pCube1")와 비교해야 한다.
assert kind == "selectNode" and nodeName == cmds.ls(cube, long=True)[0], (kind, nodeName)
print("TargetNotTransform remedy OK")

# AxisAlreadyBound: axisA를 cube에 바인딩한 뒤 또 다른 오브젝트에 바인딩
# 시도 -> 기존 연결을 disconnect.
cmds.maroBindAxis(axisA, cube)
cube2 = cmds.polyCube()[0]
try:
    cmds.maroBindAxis(axisA, cube2)
    raised = False
except RuntimeError:
    raised = True
assert raised, "re-binding an already-bound axis must fail"
seq = int(cmds.maroDiagQuery(index=0)[10])
kind, _, _, _, srcPlug, dstPlug = cmds.maroDiagQueryRemedyAction(sequence=seq)
assert kind == "disconnect", kind
assert srcPlug.startswith(cube + ".") and dstPlug == axisA + ".targetObject", (srcPlug, dstPlug)
print("AxisAlreadyBound remedy OK")

# ObjectAlreadyHasAxis: cube는 이미 axisA에 묶여 있다. axisB로도 바인딩
# 시도 -> 기존 연결을 disconnect.
try:
    cmds.maroBindAxis(axisB, cube)
    raised = False
except RuntimeError:
    raised = True
assert raised, "binding an already-claimed object must fail"
seq = int(cmds.maroDiagQuery(index=0)[10])
kind, _, _, _, srcPlug, dstPlug = cmds.maroDiagQueryRemedyAction(sequence=seq)
assert kind == "disconnect", kind
assert dstPlug == axisA + ".targetObject", dstPlug
print("ObjectAlreadyHasAxis remedy OK")

# InvalidControlMode: SetAttribute(controlMode, 0).
try:
    cmds.maroSetControlMode(axisA, 5)
    raised = False
except RuntimeError:
    raised = True
assert raised, "an invalid control mode must fail"
seq = int(cmds.maroDiagQuery(index=0)[10])
kind, nodeName, attrName, value, _, _ = cmds.maroDiagQueryRemedyAction(sequence=seq)
assert kind == "setAttribute" and nodeName == axisA and attrName == "controlMode", (
    kind, nodeName, attrName)
assert float(value) == 0.0, value
print("InvalidControlMode remedy OK")

# SelfParent / NotMaroAxisNode(둘째 자리): maroConnectAxis 경유.
# 같은 이름을 두 번 그대로 주면(cmds.maroConnectAxis(axisA, axisA)) 안 된다 --
# MSelectionList::add()는 문자열이 아니라 풀린 노드 정체성으로 중복을
# 걸러내므로 선택 목록이 길이 1로 줄고, doIt의 length() != 2 검사(WrongArgCount,
# 이 여섯 자리에 안 든다)가 SelfParent 비교보다 먼저 걸려 버린다. 같은
# 노드를 가리키되 문자열이 다른 두 번째 참조(플러그 한정 이름)를 써야
# 선택 목록이 진짜 2개로 남아 SelfParent 분기까지 도달한다.
try:
    cmds.maroConnectAxis(axisA + ".message", axisA)
    raised = False
except RuntimeError:
    raised = True
assert raised, "self-parenting must fail"
seq = int(cmds.maroDiagQuery(index=0)[10])
kind, nodeName, _, _, _, _ = cmds.maroDiagQueryRemedyAction(sequence=seq)
assert kind == "selectNode" and nodeName == axisA, (kind, nodeName)
print("SelfParent remedy OK")

try:
    cmds.maroConnectAxis(cube, axisA)
    raised = False
except RuntimeError:
    raised = True
assert raised, "connecting a non-axis node must fail"
seq = int(cmds.maroDiagQuery(index=0)[10])
kind, nodeName, _, _, _, _ = cmds.maroDiagQueryRemedyAction(sequence=seq)
assert kind == "selectNode" and nodeName == cube, (kind, nodeName)
print("NotMaroAxisNode remedy OK")

# WouldCreateCycle: 의도적으로 해법이 없다.
cmds.maroConnectAxis(axisB, axisA)
try:
    cmds.maroConnectAxis(axisA, axisB)
    raised = False
except RuntimeError:
    raised = True
assert raised, "creating a cycle must fail"
seq = int(cmds.maroDiagQuery(index=0)[10])
kind, _, _, _, _, _ = cmds.maroDiagQueryRemedyAction(sequence=seq)
assert kind == "none", f"WouldCreateCycle must have no structured remedy, got {kind}"
print("WouldCreateCycle has no remedy (by design) OK")
```

- [ ] **Step 10: 빌드하고 테스트가 통과하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R remedy_capture
```

기대: 통과. (이 테스트가 사실상 여섯 자리 전부를 한 번씩 실제로 유발하므로, 하나라도 해법이 안 채워지면 여기서 잡힌다 — 그래서 이 태스크는 자리마다 별도 deliberate-break 대신 이 종단 테스트 하나로 여섯 배선을 함께 못 박는다.)

- [ ] **Step 11: 배선 하나가 진짜로 필요한지 확인 (대표로 하나만)**

`InvalidControlMode` 자리의 `remedy.value = 0.0;`을 `remedy.value = 1.0;`으로 바꾼다.

```bash
cmake --build out/build --config Release && ctest --test-dir out/build -C Release --output-on-failure -R remedy_capture
```

기대: `InvalidControlMode remedy OK` 직전 단언에서 **실패**한다(`float(value) == 0.0`이 거짓). 확인했으면 되돌린다.

- [ ] **Step 12: 커밋**

```bash
git add src/maro_plugin/MaroCommands.cpp tests/maya/test_remedy_capture.py
git commit -m "feat: give six known failures a concrete, live-scene fix"
```

---

### Task 4: 프레젠터가 적용 가능 여부를 실제로 판단한다

**Files:**
- Modify: `src/maro_diag/src/PanelPresenter.cpp`
- Modify: `tests/diag/test_panel_presenter.cpp`

**Interfaces:**
- Consumes: `DiagRecord::remedyAction` (Task 1), `describeRemedyAction()` (Task 1)
- Produces: `buildPanelDetail()`의 `applyAvailable`/`applyUnavailableReason`/`remedyText`가 이제 실제 값을 낸다 (시그니처는 바뀌지 않는다 — `targetNodeExists` 매개변수는 B-1a가 이미 얼려 뒀다)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/diag/test_panel_presenter.cpp` 끝에 추가:

```cpp
// 해법이 없으면(RemedyActionKind::None) targetNodeExists와 무관하게
// 항상 적용 불가다.
TEST(PanelPresenter, NoRemedyMeansNotApplicableRegardlessOfNodeExistence) {
    DiagRecord rec;
    rec.severity = DiagSeverity::Error;
    rec.message = "m";
    const CrashAdjacency adjacency;

    const PanelDetail detail = buildPanelDetail(rec, nullptr, /*targetNodeExists=*/true, adjacency);
    EXPECT_FALSE(detail.applyAvailable);
    EXPECT_EQ(detail.applyUnavailableReason, "NoActionRecorded");
}

// 해법이 있고 대상 노드가 존재하면 적용 가능하다.
TEST(PanelPresenter, RemedyWithExistingTargetIsApplicable) {
    DiagRecord rec;
    rec.severity = DiagSeverity::Error;
    rec.message = "m";
    rec.remedyAction.kind = RemedyActionKind::SelectNode;
    rec.remedyAction.nodeName = "axisA";
    const CrashAdjacency adjacency;

    const PanelDetail detail = buildPanelDetail(rec, nullptr, /*targetNodeExists=*/true, adjacency);
    EXPECT_TRUE(detail.applyAvailable);
    EXPECT_TRUE(detail.applyUnavailableReason.empty());
}

// 해법은 있지만 대상 노드가 사라졌으면 적용 불가 -- 다른 이유로.
TEST(PanelPresenter, RemedyWithMissingTargetIsNotApplicable) {
    DiagRecord rec;
    rec.severity = DiagSeverity::Error;
    rec.message = "m";
    rec.remedyAction.kind = RemedyActionKind::SelectNode;
    rec.remedyAction.nodeName = "axisA";
    const CrashAdjacency adjacency;

    const PanelDetail detail = buildPanelDetail(rec, nullptr, /*targetNodeExists=*/false, adjacency);
    EXPECT_FALSE(detail.applyAvailable);
    EXPECT_EQ(detail.applyUnavailableReason, "TargetNodeMissing");
}

// book/레코드에 사람이 등록한 remedy 텍스트가 없어도, 구조화된 해법이
// 있으면 그것을 서술한 문장이 remedyText에 나온다 -- 사용자가 버튼만 보고
// 뭐가 바뀌는지 모르면 안 된다.
TEST(PanelPresenter, RemedyTextFallsBackToDescriptionWhenNothingIsRegistered) {
    DiagRecord rec;
    rec.severity = DiagSeverity::Error;
    rec.message = "m";
    rec.remedyAction.kind = RemedyActionKind::SelectNode;
    rec.remedyAction.nodeName = "axisA";
    const CrashAdjacency adjacency;

    const PanelDetail detail = buildPanelDetail(rec, nullptr, /*targetNodeExists=*/true, adjacency);
    EXPECT_EQ(detail.remedyText, "'axisA' 노드를 선택합니다.");
}

// 등록된 remedy 텍스트가 있으면 그것이 서술 문구보다 우선한다 -- 사람이
// 쓴 설명이 기계가 만든 기본 서술보다 정보가 많다.
TEST(PanelPresenter, RegisteredRemedyTextWinsOverDescription) {
    DiagRecord rec;
    rec.severity = DiagSeverity::Error;
    rec.message = "m";
    rec.remedyAction.kind = RemedyActionKind::SelectNode;
    rec.remedyAction.nodeName = "axisA";
    BookEntry entry;
    entry.remedy = "the child transform under axisA usually solves this";
    const CrashAdjacency adjacency;

    const PanelDetail detail = buildPanelDetail(rec, &entry, /*targetNodeExists=*/true, adjacency);
    EXPECT_EQ(detail.remedyText, "the child transform under axisA usually solves this");
}
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
ctest --test-dir out/build -C Release --output-on-failure -R PanelPresenter
```

기대: `NoRemedyMeansNotApplicableRegardlessOfNodeExistence`는 이미 통과(기존 하드코딩과 우연히 일치), 나머지 네 개는 **실패**한다(`applyAvailable`가 항상 false, `remedyText`가 항상 비어 있거나 기존 값).

- [ ] **Step 3: `buildPanelDetail`을 교체**

`PanelPresenter.cpp`의 `buildPanelDetail` 시작부, `(void)targetNodeExists;` 줄을 지운다(이제 진짜로 쓴다).

`detail.remedyText` 대입 블록:

```cpp
    if (bookEntry != nullptr && !bookEntry->remedy.empty()) {
        detail.remedyText = bookEntry->remedy;
    } else {
        detail.remedyText = record.remedy;
    }
```

아래로 교체:

```cpp
    if (bookEntry != nullptr && !bookEntry->remedy.empty()) {
        detail.remedyText = bookEntry->remedy;
    } else if (!record.remedy.empty()) {
        detail.remedyText = record.remedy;
    } else {
        // 사람이 등록한 텍스트가 없어도 구조화된 해법이 있으면 그것을
        // 서술한 문장을 대신 보여준다. 빈 채로 버튼만 뜨면 사용자가 뭐가
        // 바뀌는지 모른 채 누르게 된다.
        detail.remedyText = describeRemedyAction(record.remedyAction);
    }
```

`// B-1a에는 구조화된 동작이 없다. 자리만 지키고 내용은 B-1b가 채운다.` 주석과 그 아래 두 줄을 아래로 교체:

```cpp
    if (record.remedyAction.kind == RemedyActionKind::None) {
        detail.applyAvailable = false;
        detail.applyUnavailableReason = "NoActionRecorded";
    } else if (!targetNodeExists) {
        detail.applyAvailable = false;
        detail.applyUnavailableReason = "TargetNodeMissing";
    } else {
        detail.applyAvailable = true;
        detail.applyUnavailableReason.clear();
    }
```

- [ ] **Step 4: 빌드하고 테스트가 통과하는지 확인**

```bash
cmake --build out/build --config Release && ctest --test-dir out/build -C Release --output-on-failure -R PanelPresenter
```

기대: 전부 통과.

- [ ] **Step 5: `targetNodeExists`가 진짜로 갈리는지 확인**

`else if (!targetNodeExists) {` 줄을 `else if (false) {`로 바꾼다.

```bash
cmake --build out/build --config Release && ctest --test-dir out/build -C Release --output-on-failure -R PanelPresenter
```

기대: `RemedyWithMissingTargetIsNotApplicable`이 **실패**한다(`applyAvailable`가 true가 됨). 확인했으면 되돌린다.

- [ ] **Step 6: 커밋**

```bash
git add src/maro_diag/src/PanelPresenter.cpp tests/diag/test_panel_presenter.cpp
git commit -m "feat: let the presenter decide whether a fix can actually be applied"
```

---

### Task 5: 패널 상세 커맨드가 대상 노드의 실존을 실제로 확인한다

**Files:**
- Modify: `src/maro_plugin/MaroPanelCommands.cpp`
- Create: `tests/maya/test_remedy_availability.py`
- Modify: `tests/CMakeLists.txt`

**Interfaces:**
- Consumes: `PanelDetail::applyAvailable`/`applyUnavailableReason` (Task 4), `DiagRecord::remedyAction` (Task 1)
- Produces: 없음 (배선만 — `buildPanelDetail`의 세 번째 인자가 이제 진짜 값이다)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/maya/test_remedy_availability.py` (전체 새 파일):

```python
"""maroDiagPanelDetail의 applyAvailable/applyUnavailableReason이 대상
노드의 실제 존재 여부를 반영하는지 확인한다.
"""
import os

import maya.standalone
maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)

axisA = cmds.createNode("maroAxis", name="axisA")

# selectNode 해법: 노드가 살아있는 동안은 적용 가능해야 한다.
cmds.maroDiagEmit(severity="error", message="m", siteTag="T.Avail",
                  remedyAction="selectNode", remedyNode=axisA)
seq = int(cmds.maroDiagQuery(index=0)[10])
detail = cmds.maroDiagPanelDetail(sequence=seq)
assert detail[11] == "1", f"expected applyAvailable, got {detail[11]} ({detail[12]!r})"
assert detail[12] == "", detail[12]
print("available while node exists OK")

# 노드를 지우면 같은 레코드가 이제 적용 불가여야 한다 -- 레코드 자체는
# 안 바뀌지만(해법은 그 순간의 사실이다), 지금 씬에 그 노드가 없다는
# 사실은 조회할 때마다 다시 확인한다.
cmds.delete(axisA)
detail = cmds.maroDiagPanelDetail(sequence=seq)
assert detail[11] == "0", f"expected not applyAvailable after delete, got {detail[11]}"
assert detail[12] == "TargetNodeMissing", detail[12]
print("unavailable after delete OK")

# disconnect 해법: 두 플러그의 노드가 모두 존재해야 적용 가능하다. 하나만
# 지워도 불가여야 한다.
cubeA = cmds.polyCube()[0]
axisB = cmds.createNode("maroAxis", name="axisB")
cmds.maroBindAxis(axisB, cubeA)
cmds.maroDiagEmit(severity="error", message="m2", siteTag="T.Avail2",
                  remedyAction="disconnect",
                  remedySourcePlug=cubeA + ".message",
                  remedyDestPlug=axisB + ".targetObject")
seq2 = int(cmds.maroDiagQuery(index=0)[10])
detail = cmds.maroDiagPanelDetail(sequence=seq2)
assert detail[11] == "1", f"expected applyAvailable for disconnect, got {detail[11]}"

cmds.delete(cubeA)
detail = cmds.maroDiagPanelDetail(sequence=seq2)
assert detail[11] == "0", "deleting one side of a disconnect pair must disable apply"
assert detail[12] == "TargetNodeMissing", detail[12]
print("disconnect availability OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("test_remedy_availability OK")
```

- [ ] **Step 2: 테스트가 실패하는지 확인 (직접 실행, 아직 CMake 미등록)**

```powershell
& "$env:MAYA_LOCATION\bin\mayapy.exe" tests\maya\test_remedy_availability.py
```

기대: `available while node exists OK`까지도 실패한다 — `MaroDiagPanelDetailCommand::doIt`이 세 번째 인자를 아직 하드코딩 `false`로 넘기기 때문에 첫 단언(`detail[11] == "1"`)부터 어긋난다.

- [ ] **Step 3: 존재 확인 헬퍼와 배선 추가**

`MaroPanelCommands.cpp`의 익명 네임스페이스, `presenceName` 함수 아래에 추가:

```cpp
// name이 "node" 또는 "node.attribute" 모양의 이름을 가진 무언가로
// 존재하면 true. MSelectionList::add가 둘 다 그대로 받으므로 노드
// 하나짜리(selectNode/setAttribute)와 플러그짜리(disconnect)를 같은
// 방법으로 확인할 수 있다 -- 플러그 쪽은 부수적으로 그 노드에 그
// 어트리뷰트가 실제로 있는지까지 확인해 준다.
bool nameStillExists(const std::string& name) {
    if (name.empty()) return false;
    MSelectionList sel;
    return sel.add(MString(name.c_str())) == MS::kSuccess;
}

// 이 해법이 손대는 노드/플러그가 전부 지금 씬에 존재하는가. 프레젠터는
// 살아있는 씬을 조회하지 않으므로(설계 스펙 §3.3) 이 판단은 여기, 메인
// 스레드에서 커맨드가 대신 한다.
bool remedyTargetsExist(const RemedyAction& remedy) {
    switch (remedy.kind) {
        case RemedyActionKind::None:
            return false;  // 해법이 없으면 이 질문 자체가 성립하지 않는다.
        case RemedyActionKind::SelectNode:
        case RemedyActionKind::SetAttribute:
            return nameStillExists(remedy.nodeName);
        case RemedyActionKind::Disconnect:
            return nameStillExists(remedy.sourcePlug) && nameStillExists(remedy.destPlug);
    }
    return false;
}
```

이 파일 상단 `#include` 목록에 `#include <maya/MSelectionList.h>`와 `#include "maro_diag/RemedyAction.h"`를 추가한다.

`MaroDiagPanelDetailCommand::doIt`에서:

```cpp
        const PanelDetail detail =
            buildPanelDetail(*chosen, haveEntry ? &entry : nullptr, false,
                              BoadMaro::crashAdjacency());
```

아래로 교체:

```cpp
        const PanelDetail detail =
            buildPanelDetail(*chosen, haveEntry ? &entry : nullptr,
                              remedyTargetsExist(chosen->remedyAction),
                              BoadMaro::crashAdjacency());
```

- [ ] **Step 4: 빌드에 등록하고 테스트가 통과하는지 확인**

`tests/CMakeLists.txt`의 `foreach(maya_test ...)` 목록에 `remedy_availability`를 추가(Task 2가 넣은 `remedy_capture` 옆):

```cmake
    foreach(maya_test load axis_node binding capability_stack delete_rules
                      robustness diag_boad diag_onfix diag_book
                      diag_book_cross_session diag_remedy
                      diag_degraded diag_degraded_remedy diag_thread
                      panel_commands journal remedy_capture remedy_availability)
```

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R remedy_availability
```

기대: 통과.

- [ ] **Step 5: 실존 확인이 진짜로 걸리는지 확인**

`remedyTargetsExist`를 임시로 항상 `true`를 돌려주게 바꾼다(`return true;`를 함수 맨 앞에 추가).

```bash
cmake --build out/build --config Release && ctest --test-dir out/build -C Release --output-on-failure -R remedy_availability
```

기대: `unavailable after delete OK` 이전 단언에서 **실패**한다(삭제 후에도 `applyAvailable == "1"`). 확인했으면 되돌린다.

- [ ] **Step 6: 커밋**

```bash
git add src/maro_plugin/MaroPanelCommands.cpp tests/maya/test_remedy_availability.py tests/CMakeLists.txt
git commit -m "feat: check whether a remedy's targets actually still exist"
```

---

### Task 6: 상시 메인 스레드 큐 (`MaroMainThreadQueue`)

**Files:**
- Create: `src/maro_plugin/MaroMainThreadQueue.h`, `src/maro_plugin/MaroMainThreadQueue.cpp`
- Modify: `src/maro_plugin/MaroDiagCommands.h`, `src/maro_plugin/MaroDiagCommands.cpp` (테스트 전용 확인 커맨드)
- Modify: `src/maro_plugin/MaroPluginMain.cpp` (설치/해제, 새 커맨드 등록)
- Modify: `src/maro_plugin/CMakeLists.txt`
- Create: `tests/maya/test_main_thread_queue.py`
- Modify: `tests/CMakeLists.txt`

**Interfaces:**
- Produces: `MaroMainThreadQueue::install()/uninstall()/enqueue(std::function<void()>)`

정직하게 남기는 공백: 설계 스펙 §6 검증표는 "브리지를 켜도 발행이 그대로인지"도 요구한다. 이 태스크의 테스트는 브리지를 켜지 않은 채로만 큐를 검증한다 — 살아있는 ROS 2 브리지를 같은 테스트에 끌어들이면 `RUN_SERIAL`과 DDS 도메인 격리가 필요해져(기존 `maya_bridge_pump`가 이미 그렇다) 이 태스크의 범위를 넘어선다. `MaroPump`(발행 펌프)와 이 큐는 완전히 독립된 타이머 콜백이므로 서로의 존재를 모르고, 상호작용할 공유 상태도 없다 — 코드 리뷰로 확인 가능한 사실이며, 실제로 두 타이머가 같은 이벤트 루프에서 함께 도는 것은 기존 `test_bridge_pump.py`(발행 펌프 자체가 이미 그 조건에서 돈다)와 이 태스크의 `test_main_thread_queue.py`가 각자 통과하는 것으로 간접적으로 뒷받침된다. 리뷰에서 이것으로 부족하다고 판단되면 별도 태스크로 두 타이머를 한 테스트에 같이 띄우는 것을 추가한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/maya/test_main_thread_queue.py` (전체 새 파일, `test_bridge_pump.py`의 이벤트 펌프 관용구를 그대로 따른다):

```python
"""MaroMainThreadQueue가 상시로 돌며, enqueue한 작업이 doIt 호출 안이
아니라 다음 타이머 틱에서 실행되는지 확인한다.
"""
import os
import time

import maya.standalone
maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    from PySide2.QtWidgets import QApplication  # noqa: F401

_qapp = QApplication.instance() or QApplication([])

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)

assert cmds.maroQueueTestCounter() == 0, "counter must start at zero"

cmds.maroQueueTestEnqueueIncrement()
# 큐에 넣는 커맨드 자체는 아무것도 실행하지 않는다 -- 다음 타이머 틱을
# 기다려야 한다. 곧바로 읽으면 아직 0이어야 한다.
assert cmds.maroQueueTestCounter() == 0, \
    "enqueue must defer execution, not run inline inside doIt"
print("deferred (not inline) OK")

deadline = time.time() + 5
counter = 0
while time.time() < deadline:
    _qapp.processEvents()
    time.sleep(0.05)
    counter = cmds.maroQueueTestCounter()
    if counter > 0:
        break
assert counter == 1, f"expected the queued task to run exactly once, got {counter}"
print("drained on next tick OK")

# 두 개를 한꺼번에 넣어도 둘 다 돈다.
cmds.maroQueueTestEnqueueIncrement()
cmds.maroQueueTestEnqueueIncrement()
deadline = time.time() + 5
while time.time() < deadline:
    _qapp.processEvents()
    time.sleep(0.05)
    if cmds.maroQueueTestCounter() >= 3:
        break
assert cmds.maroQueueTestCounter() == 3, cmds.maroQueueTestCounter()
print("multiple tasks OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("test_main_thread_queue OK")
```

- [ ] **Step 2: 테스트가 실패하는지 확인 (직접 실행)**

```powershell
& "$env:MAYA_LOCATION\bin\mayapy.exe" tests\maya\test_main_thread_queue.py
```

기대: `AttributeError` — `maroQueueTestCounter`/`maroQueueTestEnqueueIncrement`가 없다.

- [ ] **Step 3: `MaroMainThreadQueue.h` 작성**

`src/maro_plugin/MaroMainThreadQueue.h`:

```cpp
#pragma once

#include <cstddef>
#include <functional>

#include <maya/MCallbackIdArray.h>
#include <maya/MStatus.h>

namespace maro {

// 상시로 도는 메인 스레드 큐 (설계 스펙 §3.8). MaroPump와 무관하다 --
// MaroPump는 maroStartBridge/maroStopBridge로 켜고 끄는 발행 펌프이고, 이
// 큐는 플러그인 로드부터 언로드까지 항상 돈다(브리지가 꺼져 있어도 해법
// 적용이 안전한 시점을 얻어야 하기 때문이다 -- 진단은 보통 브리지를 켜기
// 전에 일어난다).
//
// 0.1초 주기는 MTimerMessage::addTimerCallback을 쓴다 -- MaroPump.cpp가
// 이미 같은 API로 30Hz를 돌리는 것과 같은 메커니즘이다. 그 타이머 콜백은
// Maya가 메인 스레드에서만 부르므로, 여기서 실행되는 작업은 DG 평가 중이
// 아님이 보장된 시점에 돈다.
class MaroMainThreadQueue {
public:
    static MStatus install();
    static MStatus uninstall();

    // task는 다음 타이머 틱에서, 큐에 들어간 순서대로 실행된다. task
    // 자신이 예외를 던지면 이 함수를 부른 스레드가 아니라 다음 틱의 타이머
    // 콜백 안에서 삼켜진다 -- 그 경계를 넘으면 Maya가 죽는다는 이 프로젝트
    // 전역 규율 때문이다.
    static void enqueue(std::function<void()> task);

private:
    static void onTimer(float elapsed, float last, void* clientData);

    static MCallbackId s_timerId;
};

}  // namespace maro
```

- [ ] **Step 4: `MaroMainThreadQueue.cpp` 작성**

`src/maro_plugin/MaroMainThreadQueue.cpp`:

```cpp
#include "MaroMainThreadQueue.h"

#include <deque>
#include <mutex>
#include <vector>

#include <maya/MTimerMessage.h>

#include "MaroDiag.h"

namespace maro {

namespace {

constexpr float kQueueIntervalSeconds = 0.1f;

// 큐 자체의 뮤텍스. MaroDiag.h가 지켜 온 "말단 뮤텍스" 규율을 그대로
// 따른다: 이 락을 쥔 채로 boad(BoadMaro::error 등)를 부르지 않는다 --
// 아래 onTimer는 락을 놓은 뒤에야 task를 실행하므로, task 안에서 boad를
// 불러도 이 락과 얽히지 않는다.
std::mutex& queueMutex() {
    static std::mutex m;
    return m;
}

std::deque<std::function<void()>>& pending() {
    static std::deque<std::function<void()>> q;
    return q;
}

}  // namespace

MCallbackId MaroMainThreadQueue::s_timerId = 0;

MStatus MaroMainThreadQueue::install() {
    if (s_timerId != 0) return MS::kSuccess;
    MStatus status;
    s_timerId = MTimerMessage::addTimerCallback(kQueueIntervalSeconds, onTimer,
                                                nullptr, &status);
    if (!status) {
        s_timerId = 0;
    }
    return status;
}

MStatus MaroMainThreadQueue::uninstall() {
    if (s_timerId != 0) {
        MMessage::removeCallback(s_timerId);
        s_timerId = 0;
    }
    return MS::kSuccess;
}

void MaroMainThreadQueue::enqueue(std::function<void()> task) {
    std::lock_guard<std::mutex> lock(queueMutex());
    pending().push_back(std::move(task));
}

void MaroMainThreadQueue::onTimer(float /*elapsed*/, float /*last*/, void* /*clientData*/) {
    // 락을 쥔 채로 task를 실행하지 않는다 -- 실행 중에 새 enqueue가 들어오면
    // (같은 스레드에서는 안 일어나지만, task가 스스로 또 enqueue할 수는
    // 있다) 재진입 불가능한 std::mutex가 교착한다.
    std::vector<std::function<void()>> toRun;
    {
        std::lock_guard<std::mutex> lock(queueMutex());
        toRun.assign(pending().begin(), pending().end());
        pending().clear();
    }

    for (auto& task : toRun) {
        try {
            task();
        } catch (const std::exception& e) {
            BoadMaro::error("MaroMainThreadQueue.TaskThrew",
                            MString("Maro: a queued task threw: ") + e.what());
        } catch (...) {
            BoadMaro::error("MaroMainThreadQueue.TaskThrew",
                            "Maro: a queued task threw an unknown exception.");
        }
    }
}

}  // namespace maro
```

- [ ] **Step 5: 테스트 전용 확인 커맨드 추가**

`MaroDiagCommands.h` 끝, `MaroDiagQueryRemedyActionCommand` 선언 아래에 추가:

```cpp
// 테스트 전용. 상시 큐에 카운터를 1 올리는 작업을 넣는다. 인자 없음.
class MaroQueueTestEnqueueIncrementCommand : public MPxCommand {
public:
    static void* creator();
    MStatus doIt(const MArgList& args) override;
};

// 테스트 전용. 위 커맨드가 큐를 통해 실제로 올린 누적 횟수.
class MaroQueueTestCounterCommand : public MPxCommand {
public:
    static void* creator();
    MStatus doIt(const MArgList& args) override;
};
```

`MaroDiagCommands.cpp` 상단 `#include` 목록에 `#include "MaroMainThreadQueue.h"`와 `#include <atomic>`(이미 있을 수 있다 — 있으면 중복 추가하지 않는다)을 넣는다. 익명 네임스페이스에 카운터를 추가:

```cpp
std::atomic<int>& queueTestCounter() {
    static std::atomic<int> counter{0};
    return counter;
}
```

파일 끝에 두 커맨드를 구현:

```cpp
void* MaroQueueTestEnqueueIncrementCommand::creator() {
    return new MaroQueueTestEnqueueIncrementCommand();
}

MStatus MaroQueueTestEnqueueIncrementCommand::doIt(const MArgList&) {
    MaroMainThreadQueue::enqueue([]() { queueTestCounter().fetch_add(1); });
    return MS::kSuccess;
}

void* MaroQueueTestCounterCommand::creator() {
    return new MaroQueueTestCounterCommand();
}

MStatus MaroQueueTestCounterCommand::doIt(const MArgList&) {
    setResult(queueTestCounter().load());
    return MS::kSuccess;
}
```

- [ ] **Step 6: 설치/해제와 커맨드 등록을 `MaroPluginMain.cpp`에 배선**

파일 상단 `#include` 목록에 `#include "MaroMainThreadQueue.h"`를 추가.

`initializePlugin`의 `maro::BoadMaro::openJournal();` 바로 아래에 추가:

```cpp
    MStatus queueStatus = maro::MaroMainThreadQueue::install();
    if (!queueStatus) {
        queueStatus.perror("Maro: failed to install the main-thread queue");
        return queueStatus;
    }
```

(이 삽입으로 이 지점 아래 `MFnPlugin plugin(obj, kVendor, kVersion, "Any");` 앞의 지역 변수 이름 `status`와 겹치지 않도록 `queueStatus`라는 별도 이름을 썼다.)

`maroDiagQueryRemedyAction` 등록 블록(Task 2에서 추가) 바로 뒤에 추가:

```cpp
    status = plugin.registerCommand("maroQueueTestEnqueueIncrement",
                                    maro::MaroQueueTestEnqueueIncrementCommand::creator);
    if (!status) {
        status.perror("Maro: failed to register maroQueueTestEnqueueIncrement");
        return status;
    }

    status = plugin.registerCommand("maroQueueTestCounter",
                                    maro::MaroQueueTestCounterCommand::creator);
    if (!status) {
        status.perror("Maro: failed to register maroQueueTestCounter");
        return status;
    }
```

익명 네임스페이스의 `JournalCloseGuard` 아래에 짝을 이루는 가드를 추가:

```cpp
// 큐도 저널과 같은 이유로 가드를 쓴다 -- 이 함수의 어떤 경로로 빠져나가든
// (정상 반환이든 catch로의 되감김이든) 타이머 콜백을 반드시 뗀다. 안 떼면
// 언로드된 코드의 클로저(task)가 다음 틱에서 불려 크래시한다.
struct MainThreadQueueGuard {
    ~MainThreadQueueGuard() { maro::MaroMainThreadQueue::uninstall(); }
};
```

`uninitializePlugin`의 `const JournalCloseGuard closeJournalOnExit;` 바로 아래에 추가:

```cpp
    // 큐를 저널보다 먼저 뗀다 -- 정지 순서는 중요하지 않지만(큐 작업이
    // 저널을 부르지 않는다), 상시 인프라를 하나씩 순서대로 내리는 쪽이
    // 나중에 유지보수할 때 더 읽기 쉽다.
    const MainThreadQueueGuard queueGuardOnExit;
```

- [ ] **Step 7: 빌드에 등록**

`src/maro_plugin/CMakeLists.txt`의 `SOURCE_FILES` 목록에 `MaroMainThreadQueue.cpp`를 추가:

```cmake
set(SOURCE_FILES
    MaroPluginMain.cpp
    MaroAxisNode.cpp
    MaroCapabilityNodes.cpp
    MaroCommands.cpp
    MaroDeleteWatcher.cpp
    MaroRosRuntime.cpp
    MaroPump.cpp
    MaroCommandDeviceNode.cpp
    MaroDiag.cpp
    MaroDiagCommands.cpp
    MaroPanelCommands.cpp
    MaroMainThreadQueue.cpp
)
```

`tests/CMakeLists.txt`의 `foreach(maya_test ...)` 목록에 `main_thread_queue`를 추가:

```cmake
    foreach(maya_test load axis_node binding capability_stack delete_rules
                      robustness diag_boad diag_onfix diag_book
                      diag_book_cross_session diag_remedy
                      diag_degraded diag_degraded_remedy diag_thread
                      panel_commands journal remedy_capture
                      remedy_availability main_thread_queue)
```

- [ ] **Step 8: 빌드하고 테스트가 통과하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R main_thread_queue
```

기대: 통과.

- [ ] **Step 9: 정말로 미뤄지는지 확인 (동기 실행이 아닌지)**

`MaroQueueTestEnqueueIncrementCommand::doIt`을 임시로 아래처럼 바꾼다(큐를 거치지 않고 바로 실행):

```cpp
MStatus MaroQueueTestEnqueueIncrementCommand::doIt(const MArgList&) {
    queueTestCounter().fetch_add(1);
    return MS::kSuccess;
}
```

```bash
cmake --build out/build --config Release && ctest --test-dir out/build -C Release --output-on-failure -R main_thread_queue
```

기대: `deferred (not inline) OK` 직전 단언에서 **실패**한다(`maroQueueTestCounter()`가 곧바로 1). 확인했으면 되돌린다.

- [ ] **Step 10: 커밋**

```bash
git add src/maro_plugin/MaroMainThreadQueue.h src/maro_plugin/MaroMainThreadQueue.cpp src/maro_plugin/MaroDiagCommands.h src/maro_plugin/MaroDiagCommands.cpp src/maro_plugin/MaroPluginMain.cpp src/maro_plugin/CMakeLists.txt tests/maya/test_main_thread_queue.py tests/CMakeLists.txt
git commit -m "feat: run a queue that outlives the publish pump, for safe-timing work"
```

---

### Task 7: 해법 적용 커맨드 (`maroDiagRequestRemedy`, `maroApplyRemedy`)

**Files:**
- Create: `src/maro_plugin/MaroRemedyCommands.h`, `src/maro_plugin/MaroRemedyCommands.cpp`
- Modify: `src/maro_plugin/MaroPluginMain.cpp` (등록/해제)
- Modify: `src/maro_plugin/CMakeLists.txt`
- Create: `tests/maya/test_remedy_apply.py`
- Modify: `tests/CMakeLists.txt`

**Interfaces:**
- Consumes: `MaroMainThreadQueue::enqueue` (Task 6), `BoadMaro::findRecordBySequence` (Task 2), `RemedyAction`/`RemedyActionKind` (Task 1)
- Produces: 커맨드 `maroDiagRequestRemedy -sequence <int>`, `maroApplyRemedy -sequence <int>`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/maya/test_remedy_apply.py` (전체 새 파일):

```python
"""maroDiagRequestRemedy -> (큐 틱) -> maroApplyRemedy가 실제로 씬을
고치고, Ctrl+Z로 되돌아가는지 확인한다. 세 동작 종류를 각각 하나씩,
그리고 클릭과 실행 사이에 씬이 바뀌는 경계 조건 하나를 확인한다.
"""
import os
import time

import maya.standalone
maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    from PySide2.QtWidgets import QApplication  # noqa: F401

_qapp = QApplication.instance() or QApplication([])

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)


def _pumpUntil(predicate, timeoutSeconds=5):
    deadline = time.time() + timeoutSeconds
    while time.time() < deadline:
        _qapp.processEvents()
        time.sleep(0.05)
        if predicate():
            return True
    return False


# --- Disconnect ---
axisA = cmds.createNode("maroAxis", name="axisA")
cubeA = cmds.polyCube()[0]
cmds.maroBindAxis(axisA, cubeA)
cmds.maroDiagEmit(severity="error", message="m", siteTag="T.Disc",
                  remedyAction="disconnect",
                  remedySourcePlug=cubeA + ".message",
                  remedyDestPlug=axisA + ".targetObject")
seq = int(cmds.maroDiagQuery(index=0)[10])

countBefore = cmds.maroDiagCount()
cmds.maroDiagRequestRemedy(sequence=seq)
assert cmds.isConnected(cubeA + ".message", axisA + ".targetObject"), \
    "requesting a remedy must not apply it synchronously"
assert _pumpUntil(lambda: not cmds.isConnected(cubeA + ".message", axisA + ".targetObject")), \
    "the disconnect remedy never applied"
print("disconnect apply OK")

# 적용 전후를 boad에 기록한다 (원 스펙 §4.3 안전 규칙 4) -- 새 info
# 레코드가 하나 늘고, 그 메시지가 무엇을 바꿨는지 말해야 한다.
assert cmds.maroDiagCount() == countBefore + 1, \
    "applying a remedy must leave a boad record of what changed"
appliedMessage = cmds.maroDiagQuery(index=0)[1]
assert cubeA in appliedMessage and axisA in appliedMessage, appliedMessage
print("apply is recorded in boad OK")

cmds.undo()
assert cmds.isConnected(cubeA + ".message", axisA + ".targetObject"), \
    "undo must restore the connection the remedy removed"
print("disconnect undo OK")

# --- SetAttribute ---
cmds.maroSetControlMode(axisA, 1)  # ROS로 바꿔 둔다 -- 되돌릴 값이 기본값과 달라야 undo를 의미 있게 확인한다.
assert cmds.getAttr(axisA + ".controlMode") == 1
cmds.maroDiagEmit(severity="error", message="m2", siteTag="T.Attr",
                  remedyAction="setAttribute", remedyNode=axisA,
                  remedyAttribute="controlMode", remedyValue=0.0)
seq2 = int(cmds.maroDiagQuery(index=0)[10])
cmds.maroDiagRequestRemedy(sequence=seq2)
assert _pumpUntil(lambda: cmds.getAttr(axisA + ".controlMode") == 0), \
    "the setAttribute remedy never applied"
print("setAttribute apply OK")

cmds.undo()
assert cmds.getAttr(axisA + ".controlMode") == 1, "undo must restore the previous mode"
print("setAttribute undo OK")

# --- SelectNode ---
cmds.select(clear=True)
cmds.maroDiagEmit(severity="error", message="m3", siteTag="T.Select",
                  remedyAction="selectNode", remedyNode=axisA)
seq3 = int(cmds.maroDiagQuery(index=0)[10])
cmds.maroDiagRequestRemedy(sequence=seq3)
assert _pumpUntil(lambda: cmds.ls(selection=True) == [axisA]), \
    "the selectNode remedy never applied"
print("selectNode apply OK")

cmds.undo()
assert cmds.ls(selection=True) == [], "undo must restore the empty prior selection"
print("selectNode undo OK")

# --- 경계 조건: 클릭과 실행 사이에 대상이 사라짐 ---
axisB = cmds.createNode("maroAxis", name="axisB")
cmds.maroDiagEmit(severity="error", message="m4", siteTag="T.Gone",
                  remedyAction="selectNode", remedyNode=axisB)
seq4 = int(cmds.maroDiagQuery(index=0)[10])
cmds.delete(axisB)
try:
    cmds.maroApplyRemedy(sequence=seq4)
    raised = False
except RuntimeError:
    raised = True
assert raised, "applying a remedy whose target vanished must fail cleanly"
print("vanished target fails cleanly OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("test_remedy_apply OK")
```

- [ ] **Step 2: 테스트가 실패하는지 확인 (직접 실행)**

```powershell
& "$env:MAYA_LOCATION\bin\mayapy.exe" tests\maya\test_remedy_apply.py
```

기대: `AttributeError` — `maroDiagRequestRemedy`/`maroApplyRemedy`가 없다.

- [ ] **Step 3: `MaroRemedyCommands.h` 작성**

`src/maro_plugin/MaroRemedyCommands.h`:

```cpp
#pragma once

#include <maya/MDGModifier.h>
#include <maya/MPxCommand.h>
#include <maya/MSelectionList.h>
#include <maya/MSyntax.h>

#include "maro_diag/RemedyAction.h"

namespace maro {

// -sequence <int>. 그 레코드가 해법을 가지고 있으면 큐에 넣기만 한다 --
// 씬은 여기서 바뀌지 않는다. 미루는 것은 이 커맨드 안이 아니라 이 커맨드가
// 언제 불리느냐다(원 스펙 §4.3): 실제 편집은 다음 큐 틱에서
// maroApplyRemedy를 통해 일어난다. isUndoable()은 false다 -- 이 커맨드
// 자신은 아무것도 바꾸지 않으므로 undo 큐에 올릴 것이 없다.
class MaroDiagRequestRemedyCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
};

// -sequence <int>. 그 레코드의 RemedyAction을 실제로 적용한다. 평범하고
// 동기적이며 되돌릴 수 있는 커맨드다 -- MaroDiagRequestRemedyCommand가
// 큐를 통해 "언제" 부를지만 정하고, 이 커맨드 자신은 비동기로 동작하지
// 않는다(비동기면 doIt이 아무것도 안 한 채 반환해 undo 큐에 빈 항목이
// 올라간다).
//
// 실행 직전에 대상이 여전히 존재하는지 다시 확인한다(원 스펙 §5) -- 클릭과
// 실행 사이에 씬이 바뀔 수 있기 때문이다. 확인에 실패하면 아무것도 바꾸지
// 않고 실패로 끝난다.
class MaroApplyRemedyCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();

    MStatus doIt(const MArgList& args) override;
    MStatus redoIt() override;
    MStatus undoIt() override;
    bool isUndoable() const override { return m_stagedChange; }

private:
    MDGModifier m_modifier;
    RemedyActionKind m_kind = RemedyActionKind::None;
    MString m_selectNodeName;
    MSelectionList m_previousSelection;
    bool m_stagedChange = false;
};

}  // namespace maro
```

- [ ] **Step 4: `MaroRemedyCommands.cpp` 작성**

`src/maro_plugin/MaroRemedyCommands.cpp`:

```cpp
#include "MaroRemedyCommands.h"

#include <maya/MArgDatabase.h>
#include <maya/MArgList.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MGlobal.h>
#include <maya/MPlug.h>

#include "MaroDiag.h"
#include "MaroMainThreadQueue.h"

namespace maro {

namespace {

const char* kSequenceFlag = "-sq";
const char* kSequenceFlagLong = "-sequence";

// name이 지금 씬에 있는지. 노드든 "node.attribute" 플러그든 같은 방법으로
// 확인한다 (MaroPanelCommands.cpp의 nameStillExists와 같은 이유 -- 이
// 파일은 그것을 재사용하지 않는다. 그 함수가 익명 네임스페이스 안에
// 있어 다른 번역 단위에서 못 보기 때문이다. 로직이 세 줄이라 중복의
// 비용보다 새 공개 헤더를 만드는 비용이 크다).
bool nameStillExists(const MString& name) {
    if (name.length() == 0) return false;
    MSelectionList sel;
    return sel.add(name) == MS::kSuccess;
}

MStatus resolveSequenceArg(const MArgList& args, std::uint64_t& out) {
    MStatus status;
    MSyntax syntax;
    syntax.addFlag(kSequenceFlag, kSequenceFlagLong, MSyntax::kLong);
    MArgDatabase argData(syntax, args, &status);
    if (!status) return status;

    if (!argData.isFlagSet(kSequenceFlag)) {
        MGlobal::displayError("Maro: -sequence is required.");
        return MS::kFailure;
    }
    int sequenceArg = -1;
    argData.getFlagArgument(kSequenceFlag, 0, sequenceArg);
    if (sequenceArg < 0) {
        MGlobal::displayError("Maro: -sequence must not be negative.");
        return MS::kFailure;
    }
    out = static_cast<std::uint64_t>(sequenceArg);
    return MS::kSuccess;
}

}  // namespace

void* MaroDiagRequestRemedyCommand::creator() { return new MaroDiagRequestRemedyCommand(); }

MSyntax MaroDiagRequestRemedyCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag(kSequenceFlag, kSequenceFlagLong, MSyntax::kLong);
    return syntax;
}

MStatus MaroDiagRequestRemedyCommand::doIt(const MArgList& args) {
    try {
        std::uint64_t sequence = 0;
        MStatus status = resolveSequenceArg(args, sequence);
        if (!status) return status;

        DiagRecord rec;
        if (!BoadMaro::findRecordBySequence(sequence, rec)) {
            MGlobal::displayError("Maro: maroDiagRequestRemedy could not resolve sequence.");
            return MS::kFailure;
        }
        if (rec.remedyAction.kind == RemedyActionKind::None) {
            MGlobal::displayError(
                "Maro: maroDiagRequestRemedy: this diagnostic has no recorded fix.");
            return MS::kFailure;
        }

        MaroMainThreadQueue::enqueue([sequence]() {
            MGlobal::executeCommand(
                MString("maroApplyRemedy -sequence ") + MString(std::to_string(sequence).c_str()));
        });
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroDiagRequestRemedy failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroDiagRequestRemedy failed with unknown error.");
        return MS::kFailure;
    }
}

void* MaroApplyRemedyCommand::creator() { return new MaroApplyRemedyCommand(); }

MSyntax MaroApplyRemedyCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag(kSequenceFlag, kSequenceFlagLong, MSyntax::kLong);
    return syntax;
}

MStatus MaroApplyRemedyCommand::doIt(const MArgList& args) {
    try {
        std::uint64_t sequence = 0;
        MStatus status = resolveSequenceArg(args, sequence);
        if (!status) return status;

        DiagRecord rec;
        if (!BoadMaro::findRecordBySequence(sequence, rec)) {
            MGlobal::displayError("Maro: maroApplyRemedy could not resolve sequence.");
            return MS::kFailure;
        }
        const RemedyAction& remedy = rec.remedyAction;
        if (remedy.kind == RemedyActionKind::None) {
            MGlobal::displayError("Maro: maroApplyRemedy: this diagnostic has no recorded fix.");
            return MS::kFailure;
        }

        // 실행 직전 재확인 (원 스펙 §5) -- 클릭과 실행 사이에 씬이 바뀌었을
        // 수 있다. 여기서 걸러내면 아무것도 바꾸지 않고 실패로 끝난다.
        switch (remedy.kind) {
            case RemedyActionKind::SelectNode:
            case RemedyActionKind::SetAttribute: {
                const MString nodeName(remedy.nodeName.c_str());
                if (!nameStillExists(nodeName)) {
                    BoadMaro::error("MaroApplyRemedyCommand.TargetVanished",
                                    MString("Maro: '") + nodeName +
                                    "' no longer exists; nothing was changed.");
                    return MS::kFailure;
                }
                break;
            }
            case RemedyActionKind::Disconnect: {
                const MString src(remedy.sourcePlug.c_str());
                const MString dst(remedy.destPlug.c_str());
                if (!nameStillExists(src) || !nameStillExists(dst)) {
                    BoadMaro::error("MaroApplyRemedyCommand.TargetVanished",
                                    MString("Maro: '") + src + "' -> '" + dst +
                                    "' no longer both exist; nothing was changed.");
                    return MS::kFailure;
                }
                MSelectionList sel;
                sel.add(src);
                sel.add(dst);
                MPlug srcPlug, dstPlug;
                sel.getPlug(0, srcPlug);
                sel.getPlug(1, dstPlug);
                MPlugArray connectedTo;
                dstPlug.connectedTo(connectedTo, true, false);
                bool stillConnected = false;
                for (unsigned int i = 0; i < connectedTo.length(); ++i) {
                    if (connectedTo[i] == srcPlug) {
                        stillConnected = true;
                        break;
                    }
                }
                if (!stillConnected) {
                    BoadMaro::error("MaroApplyRemedyCommand.AlreadyDisconnected",
                                    MString("Maro: '") + src + "' -> '" + dst +
                                    "' is already disconnected; nothing was changed.");
                    return MS::kFailure;
                }
                break;
            }
            case RemedyActionKind::None:
                break;  // 위에서 이미 걸러졌다.
        }

        m_kind = remedy.kind;

        switch (remedy.kind) {
            case RemedyActionKind::SelectNode: {
                m_selectNodeName = MString(remedy.nodeName.c_str());
                MGlobal::getActiveSelectionList(m_previousSelection);
                break;
            }
            case RemedyActionKind::SetAttribute: {
                MSelectionList sel;
                sel.add(MString(remedy.nodeName.c_str()));
                MObject nodeObj;
                sel.getDependNode(0, nodeObj);
                MFnDependencyNode fn(nodeObj);
                MStatus plugStatus;
                MPlug plug = fn.findPlug(MString(remedy.attributeName.c_str()), false,
                                         &plugStatus);
                if (!plugStatus) return plugStatus;
                m_modifier.newPlugValueInt(plug, static_cast<int>(remedy.value));
                break;
            }
            case RemedyActionKind::Disconnect: {
                MSelectionList sel;
                sel.add(MString(remedy.sourcePlug.c_str()));
                sel.add(MString(remedy.destPlug.c_str()));
                MPlug srcPlug, dstPlug;
                sel.getPlug(0, srcPlug);
                sel.getPlug(1, dstPlug);
                m_modifier.disconnect(srcPlug, dstPlug);
                break;
            }
            case RemedyActionKind::None:
                break;
        }

        m_stagedChange = true;
        status = redoIt();
        if (status) {
            BoadMaro::info(MString("Maro: applied remedy for sequence ") +
                          MString(std::to_string(sequence).c_str()) + ": " +
                          MString(describeRemedyAction(remedy).c_str()));
        }
        return status;
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroApplyRemedy failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroApplyRemedy failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroApplyRemedyCommand::redoIt() {
    try {
        switch (m_kind) {
            case RemedyActionKind::SelectNode: {
                MSelectionList sel;
                sel.add(m_selectNodeName);
                return MGlobal::setActiveSelectionList(sel, MGlobal::kReplaceList);
            }
            case RemedyActionKind::SetAttribute:
            case RemedyActionKind::Disconnect:
                return m_modifier.doIt();
            case RemedyActionKind::None:
                return MS::kFailure;
        }
        return MS::kFailure;
    } catch (const std::exception& e) {
        BoadMaro::error("MaroApplyRemedyCommand.redoIt.Exception",
                        MString("Maro: maroApplyRemedy redo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        BoadMaro::error("MaroApplyRemedyCommand.redoIt.UnknownException",
                        "Maro: maroApplyRemedy redo failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroApplyRemedyCommand::undoIt() {
    try {
        switch (m_kind) {
            case RemedyActionKind::SelectNode:
                return MGlobal::setActiveSelectionList(m_previousSelection,
                                                        MGlobal::kReplaceList);
            case RemedyActionKind::SetAttribute:
            case RemedyActionKind::Disconnect:
                return m_modifier.undoIt();
            case RemedyActionKind::None:
                return MS::kFailure;
        }
        return MS::kFailure;
    } catch (const std::exception& e) {
        BoadMaro::error("MaroApplyRemedyCommand.undoIt.Exception",
                        MString("Maro: maroApplyRemedy undo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        BoadMaro::error("MaroApplyRemedyCommand.undoIt.UnknownException",
                        "Maro: maroApplyRemedy undo failed with unknown error.");
        return MS::kFailure;
    }
}

}  // namespace maro
```

`ScopedCommandContext`(`MaroCommands.cpp`의 기존 커맨드들이 쓰는 패턴)를 이 두 커맨드에는 **일부러** 달지 않는다 — `doIt`이 실패하는 경로에서 남기는 `BoadMaro::error()`가 `MaroApplyRemedyCommand.TargetVanished`처럼 이미 그 자체로 무엇이 실패했는지 말하는 사이트 태그를 갖고 있고, 활성 커맨드 이름(`activeCommand`)까지 덧붙이면 "해법 적용 그 자체가 실패했다"는 원인 분석에 잡음만 늘어난다.

- [ ] **Step 5: 등록/해제와 빌드**

`MaroPluginMain.cpp` 상단에 `#include "MaroRemedyCommands.h"` 추가. `maroQueueTestCounter` 등록 블록 뒤에 추가:

```cpp
    status = plugin.registerCommand("maroDiagRequestRemedy",
                                    maro::MaroDiagRequestRemedyCommand::creator,
                                    maro::MaroDiagRequestRemedyCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroDiagRequestRemedy");
        return status;
    }

    status = plugin.registerCommand("maroApplyRemedy",
                                    maro::MaroApplyRemedyCommand::creator,
                                    maro::MaroApplyRemedyCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroApplyRemedy");
        return status;
    }
```

`uninitializePlugin`의 `plugin.deregisterCommand("maroDiagQueryRemedyAction");` 바로 위에 추가(등록 역순):

```cpp
        plugin.deregisterCommand("maroApplyRemedy");
        plugin.deregisterCommand("maroDiagRequestRemedy");
```

`src/maro_plugin/CMakeLists.txt`의 `SOURCE_FILES`에 `MaroRemedyCommands.cpp` 추가:

```cmake
set(SOURCE_FILES
    MaroPluginMain.cpp
    MaroAxisNode.cpp
    MaroCapabilityNodes.cpp
    MaroCommands.cpp
    MaroDeleteWatcher.cpp
    MaroRosRuntime.cpp
    MaroPump.cpp
    MaroCommandDeviceNode.cpp
    MaroDiag.cpp
    MaroDiagCommands.cpp
    MaroPanelCommands.cpp
    MaroMainThreadQueue.cpp
    MaroRemedyCommands.cpp
)
```

`tests/CMakeLists.txt`의 `foreach(maya_test ...)` 목록에 `remedy_apply` 추가:

```cmake
    foreach(maya_test load axis_node binding capability_stack delete_rules
                      robustness diag_boad diag_onfix diag_book
                      diag_book_cross_session diag_remedy
                      diag_degraded diag_degraded_remedy diag_thread
                      panel_commands journal remedy_capture
                      remedy_availability main_thread_queue remedy_apply)
```

- [ ] **Step 6: 빌드하고 테스트가 통과하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R remedy_apply
```

기대: 통과.

- [ ] **Step 7: undo가 진짜로 되돌리는지 확인**

`MaroApplyRemedyCommand::isUndoable()`을 임시로 `return false;`로 바꾼다.

```bash
cmake --build out/build --config Release && ctest --test-dir out/build -C Release --output-on-failure -R remedy_apply
```

기대: `cmds.undo()`가 이 커맨드를 건너뛰어 `disconnect undo OK` 이전 단언(연결이 복원됐는지)에서 **실패**한다. 확인했으면 되돌린다.

- [ ] **Step 8: 실행 직전 재확인이 진짜로 걸리는지 확인**

`MaroApplyRemedyCommand::doIt`의 `SelectNode`/`SetAttribute` 재확인 블록에서 `if (!nameStillExists(nodeName)) {`를 `if (false) {`로 바꾼다.

```bash
cmake --build out/build --config Release && ctest --test-dir out/build -C Release --output-on-failure -R remedy_apply
```

기대: `vanished target fails cleanly OK` 이전 단언에서 **실패**한다(사라진 노드에 대해서도 성공한 것처럼 동작하다 `MSelectionList::add`/`findPlug`가 내부에서 조용히 실패하거나 예외 없이 잘못된 상태로 진행). 확인했으면 되돌린다.

- [ ] **Step 9: 전체 스위트가 여전히 통과하는지 확인**

```bash
ctest --test-dir out/build -C Release --output-on-failure
```

기대: Global Constraints의 사전 결함 #2(`maya_panel_commands`) 하나만 빼고 전부 통과 (이 플랜 시작 시점 117개 + 이 플랜이 추가한 신규 gtest 5개(Task 1) + mayapy 4개(Task 2, 5, 6, 7) = 126개 언저리; 정확한 숫자는 출력으로 확인한다).

- [ ] **Step 10: 커밋**

```bash
git add src/maro_plugin/MaroRemedyCommands.h src/maro_plugin/MaroRemedyCommands.cpp src/maro_plugin/MaroPluginMain.cpp src/maro_plugin/CMakeLists.txt tests/maya/test_remedy_apply.py tests/CMakeLists.txt
git commit -m "feat: apply a recorded fix through an undoable command, deferred to a safe tick"
```

---

### Task 8: 패널에 [적용] 버튼을 연결한다

**Files:**
- Modify: `python/maroDiagPanel.py`
- Modify: `docs/maro-panel-manual-checklist.md`

**Interfaces:**
- Consumes: `maroDiagPanelDetail`의 필드 11/12(`applyAvailable`/`applyUnavailableReason`, 이미 있던 자리 — Task 4/5가 내용을 채웠다), `maroDiagRequestRemedy` (Task 7)
- Produces: 없음 (UI 배선만)

`mayapy` 배치 모드에는 UI가 없어 `workspaceControl`이 성립하지 않으므로(기존 `docs/maro-panel-manual-checklist.md`의 전제) 이 태스크는 자동 테스트가 없다. 수동 확인 항목을 추가하는 것으로 검증을 대신한다 — 커버리지가 있는 척하지 않는다.

- [ ] **Step 1: `_onSelect`가 적용 가능 여부를 들고 있게 한다**

`python/maroDiagPanel.py`의 `_onSelect` 함수 시그니처를 아래로 교체:

```python
def _onSelect(listControl, detailControl, applyButton, rowsHolder, selectionHolder):
```

함수 본문 끝, `cmds.scrollField(detailControl, edit=True, text="\n".join(lines))` **앞**에 삽입:

```python
    applyAvailable = detail[11] == "1"
    selectionHolder["sequence"] = sequence if applyAvailable else None
    cmds.button(applyButton, edit=True, enable=applyAvailable,
               label="적용" if applyAvailable else "적용 불가")
```

`len(detail) != DETAIL_FIELDS`로 일찍 반환하는 분기(이미 있음)에도 버튼을 꺼 둔다 — 그 `return` 앞에 추가:

```python
        cmds.button(applyButton, edit=True, enable=False, label="적용")
        selectionHolder["sequence"] = None
```

- [ ] **Step 2: `refresh`가 선택 해제 시 버튼을 끄게 한다**

`refresh` 함수 시그니처를 아래로 교체:

```python
def refresh(listControl, detailControl, severityControl, noteControl, applyButton, rowsHolder, selectionHolder):
```

함수 본문 맨 앞, `severity = cmds.optionMenu(...)` **앞**에 삽입:

```python
    # 목록이 다시 그려지면 이전 선택은 더 이상 화면의 어느 자리와도
    # 대응하지 않는다 -- 버튼을 꺼서 스테일 sequence로 적용을 누르는 경로를
    # 원천적으로 없앤다.
    cmds.button(applyButton, edit=True, enable=False, label="적용")
    selectionHolder["sequence"] = None
```

- [ ] **Step 3: `buildUI`에 버튼을 추가하고 클로저를 연결**

`buildUI` 함수에서 `refreshButton = cmds.button(label="새로 고침")` 아래에 추가:

```python
    applyButton = cmds.button(label="적용", enable=False)
```

`rowsHolder = {"rows": []}` 아래에 추가:

```python
    # _onSelect가 채우고 applyButton의 클릭 콜백이 읽는다. sequence가
    # None이면 적용할 것이 없다는 뜻 -- 버튼이 꺼져 있으므로 정상적으로는
    # 눌릴 수 없지만, 방어적으로 한 번 더 확인한다.
    selectionHolder = {"sequence": None}
```

기존 `cmds.textScrollList(listControl, edit=True, selectCommand=...)` 호출을 아래로 교체:

```python
    cmds.textScrollList(
        listControl, edit=True,
        selectCommand=lambda *_: _onSelect(listControl, detailControl, applyButton,
                                          rowsHolder, selectionHolder))
```

기존 `cmds.button(refreshButton, edit=True, command=...)` 호출을 아래로 교체:

```python
    cmds.button(
        refreshButton, edit=True,
        command=lambda *_: refresh(listControl, detailControl, severityControl,
                                   noteControl, applyButton, rowsHolder, selectionHolder))
```

기존 `cmds.optionMenu(severityControl, edit=True, changeCommand=...)` 호출을 아래로 교체:

```python
    cmds.optionMenu(
        severityControl, edit=True,
        changeCommand=lambda *_: refresh(listControl, detailControl, severityControl,
                                         noteControl, applyButton, rowsHolder, selectionHolder))
```

버튼 자신의 클릭 콜백을 추가(위 세 `cmds.*(edit=True, ...)` 블록 뒤 아무 곳):

```python
    def _onApply(*_):
        sequence = selectionHolder["sequence"]
        if sequence is None:
            return
        cmds.maroDiagRequestRemedy(sequence=sequence)
        # 적용은 다음 큐 틱에서 일어난다 -- 여기서 화면을 다시 그리면 아직
        # 반영 전인 상태를 보여줄 뿐이다. 기존 UI 모델(선택할 때만 상세를
        # 다시 읽는다)과 같은 이유로, 사용자가 "새로 고침"을 눌러 결과를
        # 본다.
        cmds.text(noteControl, edit=True,
                  label="적용 요청됨 -- 잠시 후 새로 고침을 눌러 결과를 확인하세요.")

    cmds.button(applyButton, edit=True, command=_onApply)
```

`cmds.formLayout(form, edit=True, attachForm=[...])` 목록에 `applyButton`을 추가:

```python
    cmds.formLayout(
        form, edit=True,
        attachForm=[
            (severityControl, "top", 4), (severityControl, "left", 4),
            (applyButton, "top", 4), (applyButton, "right", 4),
            (refreshButton, "top", 4),
            (listControl, "left", 4), (listControl, "right", 4),
            (noteControl, "left", 4), (noteControl, "right", 4),
            (detailControl, "left", 4), (detailControl, "right", 4),
            (detailControl, "bottom", 4),
        ],
        attachControl=[
            (listControl, "top", 4, severityControl),
            (listControl, "bottom", 4, noteControl),
            (noteControl, "bottom", 4, detailControl),
            (refreshButton, "right", 4, applyButton),
        ],
        attachPosition=[(detailControl, "top", 0, 60)])
```

`refresh(listControl, detailControl, severityControl, noteControl, rowsHolder)` 마지막 호출을 아래로 교체:

```python
    refresh(listControl, detailControl, severityControl, noteControl, applyButton,
            rowsHolder, selectionHolder)
```

- [ ] **Step 4: 문법 검사 (mayapy로 import만)**

UI를 실제로 띄울 수는 없지만, 최소한 구문 오류와 이름 오류(정의 안 된 변수 등)는 잡는다:

```powershell
& "$env:MAYA_LOCATION\bin\mayapy.exe" -c "import sys; sys.path.insert(0, 'python'); import maroDiagPanel; print('import OK')"
```

기대: `import OK`. (이 스크립트는 `buildUI()`를 부르지 않으므로 `workspaceControl`이 없어도 통과한다 — `maya.standalone.initialize()` 없이도 `import maya.cmds`가 되는지는 환경에 따라 다르므로, 실패하면 다른 `tests/maya/*.py`처럼 `maya.standalone.initialize(name="python")`을 앞에 추가해 재시도한다.)

- [ ] **Step 5: 수동 확인 항목 추가**

`docs/maro-panel-manual-checklist.md`의 마지막 항목(`x N` 안내 관련) 뒤에 추가:

```markdown
- [ ] **해법 적용과 undo** — `maroBindAxis`로 축 하나를 바인딩한 뒤, 같은
      축을 다른 오브젝트에 다시 바인딩해 `AxisAlreadyBound`를 유발한다.
      패널에서 그 진단을 선택하면 [적용] 버튼이 활성화되고 "연결을
      끊습니다" 문구가 뜨는지 확인한다. 눌러서 잠시 뒤 새로 고침하면 기존
      바인딩이 끊어져 있는지, `Ctrl+Z`로 되돌아가는지 확인한다.
- [ ] **대상이 사라지면 적용 불가로 바뀐다** — 위 진단을 다시 만든 뒤 그
      대상 노드를 지운다. 같은 진단을 다시 선택하면(재선택해야 상세를 다시
      읽는다) 버튼이 "적용 불가"로 바뀌고 눌리지 않는지 확인한다.
```

- [ ] **Step 6: 커밋**

```bash
git add python/maroDiagPanel.py docs/maro-panel-manual-checklist.md
git commit -m "feat: wire an Apply button into the diagnostic panel"
```

---

## 완료 기준

- `ctest --test-dir out/build -C Release --output-on-failure` 전부 통과 — 단, Global Constraints에 적은 사전 결함 #2(`maya_panel_commands`의 `ModuleNotFoundError`)는 `main`에 이미 있고 이 플랜이 만들지 않았으므로 유일한 예외로 인정한다
- 여섯 개 알려진 실패가 각자 올바른 구조화된 해법(또는 `WouldCreateCycle`처럼 의도적으로 없음)을 낸다
- 대상이 사라지면 적용 불가로 정확히 바뀐다
- 적용은 항상 큐를 거쳐 다음 틱에서 일어나고, `Ctrl+Z`로 되돌아간다
- `maroDiagPanelRows`/`maroDiagPanelDetail`의 필드 개수(8/14)가 이 플랜 전후로 바뀌지 않는다
