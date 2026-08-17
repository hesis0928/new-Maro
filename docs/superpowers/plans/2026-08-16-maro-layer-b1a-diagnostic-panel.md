# Maro Layer B-1a — 진단 패널 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Layer A가 쌓아온 진단을 사용자가 실제로 보게 만든다 — 시각·반복 횟수와 함께 목록으로, 고르면 원인 컨텍스트와 과거 분석이 펼쳐지게.

**Architecture:** 판단은 Maya도 UI도 모르는 순수 C++ 프레젠터(`maro_diag`)가 하고, Maya 커맨드 둘이 그 결과를 평탄한 문자열 배열로 내보내며, Python UI가 `workspaceControl` 안에서 그것을 그린다. 프레젠터가 순수하므로 판단 전체가 gtest로 덮이고, Maya가 필요한 부분만 수동 확인으로 남는다.

**Tech Stack:** C++17, Maya 2026 devkit(OpenMaya/OpenMayaUI), GoogleTest, `mayapy`, CMake + Ninja

설계: `docs/superpowers/specs/2026-08-15-maro-layer-b-diagnostic-panel-design.md` (B-1a 단계)

## Global Constraints

- C++17, 네임스페이스 `maro`, 접두사 `maro`, UTF-8 소스
- **예외는 Maya 콜백을 넘지 않는다** — 하나만 새도 세션이 끝나고 사용자의 미저장 작업이 날아간다
- **진단 경로는 지식 저장소에 닿지 못해서 실패하지 않는다**
- **`boad`가 진단의 단일 출구다**
- **워커 스레드에서 Maya API를 부르지 않는다** — Maya 2026 기본 평가 관리자는 `compute()`를 워커에서 돌린다
- **순서를 정하는 어떤 판단도 시각을 읽지 않는다** — 전부 순번을 본다 (벽시계는 NTP·서머타임으로 뒤로 갈 수 있다)
- Maya 테스트는 `unloadPlugin` 전에 `cmds.file(new=True, force=True)`를 부른다
- 다음 경로는 건드리지 않는다: `src/control_bridge/`, `src/image_bridge/`, `src/Maro_library/`, `MaroCmd.cpp`, `moveTool.cpp`, `rosSimCmd.cpp`, `Maro_DebugUtility/`, `Maro_Management/`
- 새 테스트는 전부 **일부러 구현을 깨서 실패하는 것까지 확인**한다. 이 프로젝트에서 통과하던 테스트가 틀린 구현도 함께 통과시킨 경우가 열 번 있었고 매번 그렇게만 잡혔다
- 빌드 환경: `Launch-VsDevShell.ps1`은 이 머신에서 `vswhere.exe`를 못 찾아 `INCLUDE`/`LIB`를 비운 채 조용히 성공하고 엉뚱한 `basetsd.h` 누락 에러로 나타난다. **빌드와 같은 PowerShell 호출 안에서** `VsDevCmd.bat`를 설정한다

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cd C:\Users\ckd30\Projects\Maya_Ros_Sim
cmake --build out/build
```

빌드가 `LNK1168`로 실패하면 잔존 `mayapy.exe`가 DLL을 잡고 있는 것이다. `taskkill /F`가 안 들으면 `Get-CimInstance Win32_Process -Filter "Name='mayapy.exe'" | Invoke-CimMethod -MethodName Terminate`.

## 범위 밖 (B-1b)

저널, 비정상 종료 감지, 종료 직전 신호, 상시 메인 스레드 큐, 해법 동작 3종과 적용, `book`의 `remedyAction`. 이 플랜의 어떤 태스크도 이것들을 만들지 않는다.

**단, 상세 출력의 필드 개수는 지금 확정한다.** Python이 필드 수로 잘라 재조립하므로, B-1b에서 개수가 바뀌면 UI가 조용히 어긋난다. B-1a에서 `applyAvailable`은 항상 `0`, `applyUnavailableReason`은 항상 `"NoActionRecorded"`다 — 자리는 있고 내용만 나중에 채워진다.

## 파일 구조

| 파일 | 책임 |
|---|---|
| `src/maro_diag/include/maro_diag/PanelView.h` | 프레젠터의 출력 타입. Maya도 Qt도 모른다 |
| `src/maro_diag/include/maro_diag/PanelPresenter.h` | 진입점 둘의 선언 |
| `src/maro_diag/src/PanelPresenter.cpp` | 접기·요약·컨텍스트 표시 판단 |
| `tests/diag/test_panel_presenter.cpp` | 위의 gtest |
| `src/maro_plugin/MaroPanelCommands.h` / `.cpp` | `maroDiagPanelRows`, `maroDiagPanelDetail`, `maroDiagPanel` |
| `python/maroDiagPanel.py` | `workspaceControl` 안의 Maya 네이티브 UI |
| `tests/maya/test_panel_commands.py` | 커맨드 계약과 Python 재조립 함수 |

수정: `DiagRecord.h`(필드 추가), `MaroDiag.cpp`(채우기), `MaroCommandDeviceNode.cpp`/`MaroAxisNode.cpp`/`MaroCapabilityNodes.cpp`(이름 못 얻었음 표시), `MaroDiagCommands.cpp`(`maroDiagQuery`에 2필드 append), `MaroPluginMain.cpp`(등록), 양쪽 `CMakeLists.txt`.

---

### Task 1: `DiagRecord`에 순번과 시각, `DgContext`에 "이름 못 얻음" 표시

지금 레코드는 순서 말고 아무것도 답하지 못한다. 그리고 컨텍스트의 빈 문자열은 "관여 없음"과 "못 채움"을 구분하지 못하는데, `compute()`가 워커 스레드일 때 이름 조회를 건너뛴 자리가 정확히 후자다.

**Files:**
- Modify: `src/maro_diag/include/maro_diag/DiagRecord.h`
- Modify: `src/maro_plugin/MaroDiag.cpp`
- Modify: `src/maro_plugin/MaroAxisNode.cpp`, `src/maro_plugin/MaroCapabilityNodes.cpp`, `src/maro_plugin/MaroCommandDeviceNode.cpp`
- Modify: `src/maro_plugin/MaroDiagCommands.cpp`
- Test: `tests/maya/test_diag_boad.py`

**Interfaces:**
- Produces: `DiagRecord::sequence` (`std::uint64_t`, 1부터 단조 증가), `DiagRecord::timestampMs` (`std::uint64_t`, Unix epoch 밀리초), `DgContext::nameUnavailable` (`bool`)
- Produces: `maroDiagQuery`가 필드 12개를 돌려준다 (기존 10개 뒤에 `sequence`, `timestampMs`를 문자열로 append)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/maya/test_diag_boad.py`의 `cmds.file(new=True, force=True)` 직전에 추가:

```python
# 순번과 시각: 순서를 정하는 판단은 시각이 아니라 순번을 봐야 하므로
# (벽시계는 뒤로 갈 수 있다) 순번이 실제로 단조 증가하는지 값으로 확인한다.
cmds.maroDiagEmit(severity="info", message="seq probe A")
cmds.maroDiagEmit(severity="info", message="seq probe B")

newer = cmds.maroDiagQuery(index=0)
older = cmds.maroDiagQuery(index=1)

assert len(newer) == 12, f"expected 12 fields from maroDiagQuery, got {len(newer)}"

seqNewer = int(newer[10])
seqOlder = int(older[10])
assert seqNewer == seqOlder + 1, (
    f"sequence must increase by exactly one per record, got {seqOlder} -> {seqNewer}"
)

assert int(newer[11]) > 0, f"expected a non-zero epoch-ms timestamp, got {newer[11]!r}"
print("sequence and timestamp OK")
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
ctest --test-dir out/build --output-on-failure -R maya_diag_boad
```

기대: `AssertionError: expected 12 fields from maroDiagQuery, got 10`

- [ ] **Step 3: `DiagRecord.h`에 필드 추가**

`DiagRecord.h` 상단의 `#include <string>` 아래에 `#include <cstdint>`를 추가한다.

`struct DgContext`의 `axisOrTarget` 선언 아래에 추가:

```cpp
    // 위 네 필드가 비어 있는 것은 두 가지 뜻일 수 있다 -- 그 자리에 관여한
    // 것이 애초에 없었거나(관여 없음), 관여는 했는데 그 시점에 알아낼 수
    // 없었거나(못 채움). 후자가 실제로 있다: compute()가 워커 스레드에서
    // 돌 때는 Maya에 노드 이름을 물을 수 없어 axisOrTarget을 비운다.
    // 패널이 둘을 똑같이 빈칸으로 그리면 사용자는 "정보가 없다"와 "이
    // 도구가 고장 났다"를 구분하지 못한다 (설계 스펙 §4.4).
    bool nameUnavailable = false;
```

`struct DiagRecord`의 `priorAnalysis` 선언 아래에 추가:

```cpp
    // 1부터 시작해 레코드마다 1씩 오르는 순번. 정렬·접기의 유일한 기준이다.
    std::uint64_t sequence = 0;
    // Unix epoch 밀리초. 사람에게 보여주기 위한 값이며, 순서를 정하는 어떤
    // 판단도 이것을 읽지 않는다 -- 벽시계는 NTP 보정이나 서머타임으로 뒤로
    // 갈 수 있고, 그때 순서가 흔들리면 연쇄의 앞뒤가 뒤집혀 원인 분석이
    // 통째로 반대가 된다. 형식화는 표시하는 쪽(Python)이 로컬 시간대로 한다.
    std::uint64_t timestampMs = 0;
```

- [ ] **Step 4: `boad`가 채우게 한다**

`src/maro_plugin/MaroDiag.cpp` 상단 include에 추가:

```cpp
#include <atomic>
#include <chrono>
#include <cstdint>
```

익명 네임스페이스(`g_freshAnalysisCount` 선언 근처)에 추가:

```cpp
// 레코드 순번. 0은 "안 채워짐"을 뜻하므로 첫 레코드가 1을 받도록 pre-increment
// 한다. 레코드 뮤텍스와 무관하게 워커 스레드에서도 불리므로 atomic이다.
std::atomic<std::uint64_t> g_nextSequence{0};

std::uint64_t nowMs() {
    using namespace std::chrono;
    return static_cast<std::uint64_t>(
        duration_cast<milliseconds>(system_clock::now().time_since_epoch()).count());
}

void stampRecord(DiagRecord& rec) {
    rec.sequence = ++g_nextSequence;
    rec.timestampMs = nowMs();
}
```

`info`/`warn`/`devInfo`/`error` 각각에서 `DiagRecord rec;` 선언 **직후**에 `stampRecord(rec);`를 한 줄 넣는다. 예를 들어 `info`는 이렇게 된다:

```cpp
void BoadMaro::info(const MString& message) {
    DiagRecord rec;
    stampRecord(rec);
    rec.severity = DiagSeverity::Info;
    rec.message = message.asChar();
```

`resetForTest()`의 `stream().clear();` 아래에 추가:

```cpp
    g_nextSequence.store(0);
```

- [ ] **Step 5: `maroDiagQuery`에 두 필드 append**

`src/maro_plugin/MaroDiagCommands.cpp`의 `MaroDiagQueryCommand::doIt`에서 `result.append(MString(rec.priorAnalysis.c_str()));` 아래에 추가:

```cpp
    // 뒤에 붙인다 -- 기존 테스트들이 위치 인덱스로 읽으므로 0~9는 그대로 둔다.
    result.append(MString(std::to_string(rec.sequence).c_str()));
    result.append(MString(std::to_string(rec.timestampMs).c_str()));
```

같은 파일 상단 include에 `#include <string>`이 없으면 추가한다.

`MaroDiagCommands.h`의 `MaroDiagQueryCommand` 주석에서 "필드 9개"를 "필드 12개"로 고치고, 뒤에 `, priorAnalysis, sequence, timestampMs`를 덧붙인다.

- [ ] **Step 6: `compute()` 헬퍼가 "이름 못 얻음"을 표시하게 한다**

`src/maro_plugin/MaroAxisNode.cpp`의 `computeContext`에서 `if (isMainThread()) {` 블록에 `else`를 단다:

```cpp
    if (isMainThread()) {
        // 이 함수 자체가 compute()의 catch 블록 안에서 -- 즉 이미 예외가 한
        // 번 난 상황에서 -- 불린다. MFnDependencyNode 조회가 여기서 또
        // 실패/예외를 내면 그 예외는 compute()를 감싸는 바깥 try가 없으므로
        // 곧장 Maya 콜백 경계를 넘는다 -- 그래서 반드시 그 자체를 한 번 더
        // 감싼다: 실패하면 이름 없이(빈 문자열로) 진행한다.
        try {
            MFnDependencyNode fn(node.thisMObject());
            ctx.axisOrTarget = fn.name().asChar();
        } catch (...) {
            ctx.nameUnavailable = true;
        }
    } else {
        // 워커 스레드다. Maya에 이름을 물을 수 없다 -- 빈칸이지만 "관여
        // 없음"이 아니라 "못 채움"이다.
        ctx.nameUnavailable = true;
    }
```

`src/maro_plugin/MaroCapabilityNodes.cpp`의 `computeContext`, `src/maro_plugin/MaroCommandDeviceNode.cpp`의 `computeContext`에도 **같은 형태로** `catch (...)` 안과 `else` 절에 `ctx.nameUnavailable = true;`를 넣는다. `MaroCommandDeviceNode.cpp`의 `selfContext`는 메인 스레드 전용이므로 `catch (...)` 안에만 넣는다.

- [ ] **Step 7: 빌드하고 테스트가 통과하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build
```

```bash
ctest --test-dir out/build --output-on-failure
```

기대: 전부 통과. 기존 테스트들은 위치 인덱스 0~9만 읽으므로 영향받지 않는다.

- [ ] **Step 8: 순번이 진짜로 단조 증가하는지 확인**

`stampRecord`의 `rec.sequence = ++g_nextSequence;`를 `rec.sequence = g_nextSequence.load() + 1;`로 바꾼다(증가시키지 않아 모든 레코드가 같은 값을 받게 된다).

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure -R maya_diag_boad
```

기대: `AssertionError: sequence must increase by exactly one per record, got 1 -> 1`. 확인했으면 되돌리고 다시 통과를 본다.

- [ ] **Step 9: 커밋**

```bash
git add src/maro_diag/include/maro_diag/DiagRecord.h src/maro_plugin tests/maya/test_diag_boad.py
git commit -m "feat: give every diagnostic a sequence, a wall-clock time, and an honest empty"
```

---

### Task 2: 프레젠터 — 행 목록과 태그별 접기

같은 사이트 태그가 200번 터지면 목록이 200줄이 되고 그 아래 깔린 다른 실패 — 대개 진짜 원인 — 는 보이지 않는다. 접기는 Maya도 UI도 모르는 순수 판단이므로 전부 gtest로 덮인다.

**Files:**
- Create: `src/maro_diag/include/maro_diag/PanelView.h`
- Create: `src/maro_diag/include/maro_diag/PanelPresenter.h`
- Create: `src/maro_diag/src/PanelPresenter.cpp`
- Create: `tests/diag/test_panel_presenter.cpp`
- Modify: `src/maro_diag/CMakeLists.txt`, `tests/CMakeLists.txt`

**Interfaces:**
- Consumes: `maro::DiagRecord`, `maro::DiagSeverity` (Task 1)
- Produces: `maro::PanelRow`, `maro::PanelSeverityFilter`, `maro::buildPanelRows(const std::vector<DiagRecord>&, PanelSeverityFilter, std::size_t maxRows, std::size_t& hiddenByFilter, std::size_t& hiddenByCap)`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/diag/test_panel_presenter.cpp`:

```cpp
#include <gtest/gtest.h>

#include <vector>

#include "maro_diag/DiagRecord.h"
#include "maro_diag/PanelView.h"
#include "maro_diag/PanelPresenter.h"

namespace {

maro::DiagRecord makeRecord(std::uint64_t seq, std::uint64_t ms,
                             maro::DiagSeverity sev, const std::string& siteTag,
                             const std::string& message) {
    maro::DiagRecord rec;
    rec.sequence = seq;
    rec.timestampMs = ms;
    rec.severity = sev;
    rec.errorHash = siteTag;  // 접기 기준은 해시다 (같은 사이트 = 같은 해시)
    rec.message = message;
    return rec;
}

}  // namespace

// 병렬 평가에서는 서로 다른 노드의 경고가 번갈아 들어온다. "연속된 같은
// 태그"로 접으면 어느 것도 연속이 아니라 접기가 한 번도 안 걸린다.
TEST(PanelPresenter, CollapsesInterleavedRepeatsByTag) {
    std::vector<maro::DiagRecord> stream;
    for (std::uint64_t i = 0; i < 4; ++i) {
        stream.push_back(makeRecord(i * 2 + 1, 1000 + i * 2,
                                    maro::DiagSeverity::Error, "hashA", "A failed"));
        stream.push_back(makeRecord(i * 2 + 2, 1001 + i * 2,
                                    maro::DiagSeverity::Error, "hashB", "B failed"));
    }

    std::size_t hiddenByFilter = 0;
    std::size_t hiddenByCap = 0;
    const std::vector<maro::PanelRow> rows = maro::buildPanelRows(
        stream, maro::PanelSeverityFilter::All, 500, hiddenByFilter, hiddenByCap);

    ASSERT_EQ(rows.size(), 2u) << "interleaved repeats of two tags must collapse to two rows";
    EXPECT_EQ(rows[0].occurrences, 4u);
    EXPECT_EQ(rows[1].occurrences, 4u);
}

// 접힌 행의 자리는 그 태그의 가장 최근 발생을 따른다.
TEST(PanelPresenter, RowOrderFollowsMostRecentOccurrence) {
    std::vector<maro::DiagRecord> stream;
    stream.push_back(makeRecord(1, 1000, maro::DiagSeverity::Error, "old", "old one"));
    stream.push_back(makeRecord(2, 1001, maro::DiagSeverity::Error, "recent", "recent one"));
    stream.push_back(makeRecord(3, 1002, maro::DiagSeverity::Error, "old", "old again"));

    std::size_t hiddenByFilter = 0;
    std::size_t hiddenByCap = 0;
    const std::vector<maro::PanelRow> rows = maro::buildPanelRows(
        stream, maro::PanelSeverityFilter::All, 500, hiddenByFilter, hiddenByCap);

    ASSERT_EQ(rows.size(), 2u);
    EXPECT_EQ(rows[0].errorHash, "old") << "newest first: 'old' recurred at sequence 3";
    EXPECT_EQ(rows[0].sequence, 3u);
    EXPECT_EQ(rows[0].firstTimestampMs, 1000u);
    EXPECT_EQ(rows[0].lastTimestampMs, 1002u);
}

// 벽시계가 뒤로 가도 순서는 순번을 따른다.
TEST(PanelPresenter, OrderIgnoresBackwardClock) {
    std::vector<maro::DiagRecord> stream;
    stream.push_back(makeRecord(1, 9000, maro::DiagSeverity::Error, "first", "first"));
    stream.push_back(makeRecord(2, 1000, maro::DiagSeverity::Error, "second", "second"));

    std::size_t hiddenByFilter = 0;
    std::size_t hiddenByCap = 0;
    const std::vector<maro::PanelRow> rows = maro::buildPanelRows(
        stream, maro::PanelSeverityFilter::All, 500, hiddenByFilter, hiddenByCap);

    ASSERT_EQ(rows.size(), 2u);
    EXPECT_EQ(rows[0].errorHash, "second")
        << "sequence 2 is newer even though its wall clock reads earlier";
}

// 절단은 필터와 접기 뒤에 온다. 먼저 자르면 연쇄의 시작이 가장 먼저 사라진다.
TEST(PanelPresenter, FiltersAndCollapsesBeforeCapping) {
    std::vector<maro::DiagRecord> stream;
    // 진짜 원인: 가장 오래된 에러 하나.
    stream.push_back(makeRecord(1, 1000, maro::DiagSeverity::Error, "root", "root cause"));
    // 그 뒤로 쏟아진 정보성 잡음 300개.
    for (std::uint64_t i = 0; i < 300; ++i) {
        stream.push_back(makeRecord(2 + i, 1001 + i, maro::DiagSeverity::Info,
                                     "noise", "just noise"));
    }

    std::size_t hiddenByFilter = 0;
    std::size_t hiddenByCap = 0;
    const std::vector<maro::PanelRow> rows = maro::buildPanelRows(
        stream, maro::PanelSeverityFilter::ErrorsOnly, 2, hiddenByFilter, hiddenByCap);

    ASSERT_EQ(rows.size(), 1u);
    EXPECT_EQ(rows[0].errorHash, "root") << "the cascade's origin must survive truncation";
    EXPECT_EQ(hiddenByFilter, 300u);
    EXPECT_EQ(hiddenByCap, 0u) << "collapsing brought it under the cap, so nothing was cut";
}

// 필터로 빠진 것과 상한으로 잘린 것은 다른 사건이다.
TEST(PanelPresenter, ReportsHiddenCountsSeparately) {
    std::vector<maro::DiagRecord> stream;
    for (std::uint64_t i = 0; i < 5; ++i) {
        stream.push_back(makeRecord(i + 1, 1000 + i, maro::DiagSeverity::Error,
                                     "tag" + std::to_string(i), "distinct"));
    }
    stream.push_back(makeRecord(6, 2000, maro::DiagSeverity::Info, "info", "noise"));

    std::size_t hiddenByFilter = 0;
    std::size_t hiddenByCap = 0;
    const std::vector<maro::PanelRow> rows = maro::buildPanelRows(
        stream, maro::PanelSeverityFilter::ErrorsOnly, 3, hiddenByFilter, hiddenByCap);

    ASSERT_EQ(rows.size(), 3u);
    EXPECT_EQ(hiddenByFilter, 1u);
    EXPECT_EQ(hiddenByCap, 2u);
}
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
ctest --test-dir out/build --output-on-failure -R PanelPresenter
```

기대: 컴파일 실패 — `maro_diag/PanelView.h`가 없다.

- [ ] **Step 3: `PanelView.h` 작성**

`src/maro_diag/include/maro_diag/PanelView.h`:

```cpp
#pragma once

#include <cstdint>
#include <string>

namespace maro {

// 프레젠터의 출력이다. Maya도 Qt도 Maya 네이티브 위젯도 전제하지 않는다 --
// 어떤 UI 기술로 그릴지는 이 타입이 모른다 (설계 스펙 §3.2). B-2가 Qt판을
// 붙일 때 판단 로직을 한 줄도 다시 쓰지 않게 하는 지점이다.

enum class PanelSeverityFilter {
    All,
    WarnAndAbove,
    ErrorsOnly,
};

// 접힌 행 하나. 같은 사이트(= 같은 errorHash)의 발생들이 한 행으로 모인다.
struct PanelRow {
    std::string errorHash;   // 접기 키. Error가 아닌 레코드는 비어 있을 수 있다
    std::string severity;    // "info" | "warn" | "devInfo" | "error"
    std::string summary;     // 한 줄 요약 (가장 최근 발생의 message 첫 줄)
    // 이 행이 대표하는 가장 최근 발생의 순번. 정렬 기준이자 상세 조회 키다.
    std::uint64_t sequence = 0;
    std::uint64_t firstTimestampMs = 0;  // 형식화는 표시하는 쪽이 로컬 시간대로 한다
    std::uint64_t lastTimestampMs = 0;
    std::size_t occurrences = 1;
    bool knownBefore = false;  // 이 자리의 발생 중 하나라도 book에서 즉답됐는가
};

}  // namespace maro
```

- [ ] **Step 4: `PanelPresenter.h` 작성**

`src/maro_diag/include/maro_diag/PanelPresenter.h`:

```cpp
#pragma once

#include <cstddef>
#include <vector>

#include "maro_diag/DiagRecord.h"
#include "maro_diag/PanelView.h"

namespace maro {

// 레코드 스냅샷을 화면에 나갈 행 목록으로 바꾼다. Maya를 조회하지 않고
// book도 보지 않는다 -- DiagRecord가 servedFromBook을 발생 시점에 이미
// 담고 있으므로 기지 여부는 레코드 자체에서 나온다 (설계 스펙 §3.4).
//
// 순서: 필터 -> 태그별 접기 -> 상한. 이 순서를 뒤집어 먼저 자르면 연쇄의
// 시작 -- 진단에서 가장 중요한 한 줄 -- 이 뒤따라온 수백 개의 반복에 밀려
// 사라진다 (설계 스펙 §5).
//
// hiddenByFilter/hiddenByCap은 따로 돌려준다. 필터로 빠진 것과 상한으로
// 잘린 것은 사용자에게 다른 사건이기 때문이다.
std::vector<PanelRow> buildPanelRows(const std::vector<DiagRecord>& stream,
                                      PanelSeverityFilter filter,
                                      std::size_t maxRows,
                                      std::size_t& hiddenByFilter,
                                      std::size_t& hiddenByCap);

}  // namespace maro
```

- [ ] **Step 5: `PanelPresenter.cpp` 작성**

`src/maro_diag/src/PanelPresenter.cpp`:

```cpp
#include "maro_diag/PanelPresenter.h"

#include <algorithm>
#include <unordered_map>

namespace maro {

namespace {

const char* severityName(DiagSeverity s) {
    switch (s) {
        case DiagSeverity::Info: return "info";
        case DiagSeverity::Warn: return "warn";
        case DiagSeverity::DevInfo: return "devInfo";
        case DiagSeverity::Error: return "error";
    }
    return "unknown";
}

bool passesFilter(DiagSeverity s, PanelSeverityFilter filter) {
    switch (filter) {
        case PanelSeverityFilter::All:
            return true;
        case PanelSeverityFilter::WarnAndAbove:
            return s == DiagSeverity::Warn || s == DiagSeverity::Error;
        case PanelSeverityFilter::ErrorsOnly:
            return s == DiagSeverity::Error;
    }
    return true;
}

std::string firstLine(const std::string& message) {
    const std::size_t cut = message.find('\n');
    return cut == std::string::npos ? message : message.substr(0, cut);
}

// 접기 키. errorHash가 있으면 그것이 사이트를 가리킨다. Error가 아닌
// 레코드는 해시가 없으므로 심각도와 메시지 첫 줄로 키를 만든다 -- 같은
// 문장이 반복되는 경고가 실제 접기 대상이기 때문이다.
std::string collapseKey(const DiagRecord& rec) {
    if (!rec.errorHash.empty()) return "h:" + rec.errorHash;
    return std::string("m:") + severityName(rec.severity) + ":" + firstLine(rec.message);
}

}  // namespace

std::vector<PanelRow> buildPanelRows(const std::vector<DiagRecord>& stream,
                                      PanelSeverityFilter filter,
                                      std::size_t maxRows,
                                      std::size_t& hiddenByFilter,
                                      std::size_t& hiddenByCap) {
    hiddenByFilter = 0;
    hiddenByCap = 0;

    std::vector<PanelRow> rows;
    std::unordered_map<std::string, std::size_t> indexByKey;

    for (const DiagRecord& rec : stream) {
        if (!passesFilter(rec.severity, filter)) {
            ++hiddenByFilter;
            continue;
        }

        const std::string key = collapseKey(rec);
        const auto found = indexByKey.find(key);
        if (found == indexByKey.end()) {
            PanelRow row;
            row.errorHash = rec.errorHash;
            row.severity = severityName(rec.severity);
            row.summary = firstLine(rec.message);
            row.sequence = rec.sequence;
            row.firstTimestampMs = rec.timestampMs;
            row.lastTimestampMs = rec.timestampMs;
            row.occurrences = 1;
            row.knownBefore = rec.servedFromBook;
            indexByKey.emplace(key, rows.size());
            rows.push_back(row);
            continue;
        }

        PanelRow& row = rows[found->second];
        ++row.occurrences;
        row.knownBefore = row.knownBefore || rec.servedFromBook;
        // 행의 자리는 가장 최근 발생을 따른다. 순번으로만 비교한다 --
        // 벽시계는 뒤로 갈 수 있어 순서 판단에 쓰지 않는다.
        if (rec.sequence >= row.sequence) {
            row.sequence = rec.sequence;
            row.lastTimestampMs = rec.timestampMs;
            row.summary = firstLine(rec.message);
            row.severity = severityName(rec.severity);
        }
        if (rec.sequence < row.sequence) {
            row.firstTimestampMs = std::min(row.firstTimestampMs, rec.timestampMs);
        }
    }

    // 최신 순번이 위로.
    std::sort(rows.begin(), rows.end(),
              [](const PanelRow& a, const PanelRow& b) { return a.sequence > b.sequence; });

    if (rows.size() > maxRows) {
        hiddenByCap = rows.size() - maxRows;
        rows.resize(maxRows);
    }
    return rows;
}

}  // namespace maro
```

- [ ] **Step 6: 빌드에 등록**

`src/maro_diag/CMakeLists.txt`의 `add_library(maro_diag STATIC` 목록에 `src/PanelPresenter.cpp`를 추가한다:

```cmake
add_library(maro_diag STATIC
    src/ErrorHash.cpp
    src/BookStore.cpp
    src/PanelPresenter.cpp
)
```

`tests/CMakeLists.txt`의 `add_executable(maro_diag_tests` 목록에 추가:

```cmake
add_executable(maro_diag_tests
    diag/test_error_hash.cpp
    diag/test_book_store.cpp
    diag/test_panel_presenter.cpp
)
```

- [ ] **Step 7: 빌드하고 테스트가 통과하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build
```

```bash
ctest --test-dir out/build --output-on-failure
```

기대: 전부 통과.

- [ ] **Step 8: 접기 기준이 진짜 태그별인지 확인**

`collapseKey`가 연속 판정을 흉내내도록 `PanelPresenter.cpp`의 루프에서 `indexByKey`를 매 레코드마다 비우게 만든다 — `const std::string key = collapseKey(rec);` 바로 위에 `indexByKey.clear();`를 넣는다. 이러면 연속된 것만 접히는(사실상 아무것도 안 접히는) 구현이 된다.

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure -R PanelPresenter
```

기대: `CollapsesInterleavedRepeatsByTag`가 `interleaved repeats of two tags must collapse to two rows` (`rows.size()`가 8)로 **실패**한다. 확인했으면 그 줄을 지우고 다시 통과를 본다.

- [ ] **Step 9: 절단 순서가 진짜로 지켜지는지 확인**

`buildPanelRows`에서 상한 절단 블록을 `for` 루프 **위로** 옮긴다 — 즉 스트림을 먼저 `maxRows`개로 자른 뒤 필터·접기를 하게 만든다. 가장 간단하게는 함수 맨 앞에 다음을 넣고 이후 루프가 `trimmed`를 돌게 한다:

```cpp
    std::vector<DiagRecord> trimmed(stream.end() - std::min(stream.size(), maxRows),
                                     stream.end());
```

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure -R PanelPresenter
```

기대: `FiltersAndCollapsesBeforeCapping`이 `the cascade's origin must survive truncation`으로 **실패**한다(가장 오래된 `root`가 잘려 나가므로). 확인했으면 되돌리고 다시 통과를 본다.

- [ ] **Step 10: 커밋**

```bash
git add src/maro_diag tests/diag/test_panel_presenter.cpp tests/CMakeLists.txt
git commit -m "feat: collapse repeats by tag so the failure underneath stays visible"
```

---

### Task 3: 프레젠터 — 상세와 컨텍스트 표시 판단

빈 컨텍스트를 그냥 빈칸으로 그리면 사용자는 "정보가 없다"와 "이 도구가 고장 났다"를 구분하지 못한다.

**Files:**
- Modify: `src/maro_diag/include/maro_diag/PanelView.h`, `src/maro_diag/include/maro_diag/PanelPresenter.h`, `src/maro_diag/src/PanelPresenter.cpp`
- Modify: `tests/diag/test_panel_presenter.cpp`

**Interfaces:**
- Consumes: `maro::DiagRecord`, `maro::BookEntry` (기존), `maro::PanelRow` (Task 2)
- Produces: `maro::ContextPresence`, `maro::ContextField`, `maro::PanelDetail`, `maro::buildPanelDetail(const DiagRecord&, const BookEntry*, bool targetNodeExists)`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/diag/test_panel_presenter.cpp` 끝에 추가 (`#include "maro_diag/BookStore.h"`를 상단 include에 함께 추가):

```cpp
// 관여가 없어서 빈 것과, 관여는 했는데 못 채운 것은 다른 사실이다.
TEST(PanelPresenter, DistinguishesNotCapturedFromNotApplicable) {
    maro::DiagRecord rec = makeRecord(1, 1000, maro::DiagSeverity::Error,
                                       "hash", "compute failed");
    rec.context.nodeType = "maroAxis";
    rec.context.axisOrTarget = "";       // 워커 스레드라 이름을 못 물었다
    rec.context.nameUnavailable = true;
    rec.context.attributeName = "";      // 이 실패에는 관여한 어트리뷰트가 없다

    const maro::PanelDetail detail = maro::buildPanelDetail(rec, nullptr, false);

    EXPECT_EQ(detail.nodeType.presence, maro::ContextPresence::Present);
    EXPECT_EQ(detail.nodeType.value, "maroAxis");
    EXPECT_EQ(detail.axisOrTarget.presence, maro::ContextPresence::NotCaptured)
        << "the worker thread could not ask Maya for the name -- that is not 'nothing involved'";
    EXPECT_EQ(detail.attributeName.presence, maro::ContextPresence::NotApplicable);
}

// book 항목이 있으면 해법 설명이 나온다. 적용 가능 여부는 B-1b까지 항상 거짓이다.
TEST(PanelPresenter, CarriesRemedyTextButOffersNoActionYet) {
    maro::DiagRecord rec = makeRecord(1, 1000, maro::DiagSeverity::Error,
                                       "hash", "bind rejected");
    maro::BookEntry entry;
    entry.analysis = "이 축은 이미 다른 오브젝트에 묶여 있다";
    entry.remedy = "먼저 기존 바인딩을 끊으세요";

    const maro::PanelDetail detail = maro::buildPanelDetail(rec, &entry, true);

    EXPECT_EQ(detail.remedyText, "먼저 기존 바인딩을 끊으세요");
    EXPECT_FALSE(detail.applyAvailable);
    EXPECT_EQ(detail.applyUnavailableReason, "NoActionRecorded");
}

// 레코드의 priorAnalysis와 book의 현재 analysis는 다를 수 있다 -- 레코드가
// 남은 뒤에 등록된 것을 반영하는 것이 상세 조회의 목적이다.
TEST(PanelPresenter, PrefersTheCurrentBookAnalysisOverTheRecordedOne) {
    maro::DiagRecord rec = makeRecord(1, 1000, maro::DiagSeverity::Error,
                                       "hash", "failed");
    rec.priorAnalysis = "레코드가 남을 때의 분석";
    maro::BookEntry entry;
    entry.analysis = "그 뒤에 갱신된 분석";

    const maro::PanelDetail detail = maro::buildPanelDetail(rec, &entry, true);

    EXPECT_EQ(detail.priorAnalysis, "그 뒤에 갱신된 분석");
}

// book을 못 읽어도 상세는 나온다 -- 진단 경로는 지식 저장소 때문에 죽지 않는다.
TEST(PanelPresenter, WorksWithoutABookEntry) {
    maro::DiagRecord rec = makeRecord(1, 1000, maro::DiagSeverity::Error,
                                       "hash", "failed");
    rec.priorAnalysis = "레코드에 실려 온 분석";

    const maro::PanelDetail detail = maro::buildPanelDetail(rec, nullptr, true);

    EXPECT_EQ(detail.message, "failed");
    EXPECT_EQ(detail.priorAnalysis, "레코드에 실려 온 분석");
    EXPECT_EQ(detail.remedyText, "");
}
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
ctest --test-dir out/build --output-on-failure -R PanelPresenter
```

기대: 컴파일 실패 — `maro::ContextPresence`가 없다.

- [ ] **Step 3: `PanelView.h`에 상세 타입 추가**

`PanelView.h`의 `struct PanelRow` 아래에 추가:

```cpp
// 컨텍스트 한 칸의 표시 상태. 빈 문자열 하나로는 두 사실을 구분할 수 없다.
enum class ContextPresence {
    Present,        // 값이 있다
    NotApplicable,  // 이 자리에 관여한 것이 애초에 없었다
    NotCaptured,    // 관여는 했으나 그 시점에 알아낼 수 없었다
};

struct ContextField {
    std::string value;
    ContextPresence presence = ContextPresence::NotApplicable;
};

// 선택된 행의 상세. 필드 개수는 지금 확정한다 -- Python이 필드 수로 잘라
// 재조립하므로 B-1b에서 개수가 바뀌면 UI가 조용히 어긋난다. B-1a에서
// applyAvailable은 항상 false, applyUnavailableReason은 항상
// "NoActionRecorded"다: 자리는 있고 내용만 나중에 채워진다.
struct PanelDetail {
    ContextField nodeType;
    ContextField attributeName;
    ContextField activeCommand;
    ContextField axisOrTarget;
    std::string message;
    std::string priorAnalysis;
    std::string remedyText;
    bool applyAvailable = false;
    std::string applyUnavailableReason;
};
```

- [ ] **Step 4: `PanelPresenter.h`에 선언 추가**

`PanelPresenter.h` 상단 include에 `#include "maro_diag/BookStore.h"`를 추가하고, `buildPanelRows` 선언 아래에 추가:

```cpp
// 선택된 레코드 하나의 상세를 만든다.
//
// bookEntry는 **지금** book에서 읽어 온 항목이며 없으면 nullptr다. 레코드가
// 이미 priorAnalysis를 싣고 있는데도 다시 읽는 이유는 I/O를 아끼려는 것이
// 아니라, 레코드가 남은 뒤에 사용자가 등록한 해법을 반영하기 위해서다
// (설계 스펙 §3.4).
//
// targetNodeExists는 호출부가 메인 스레드에서 미리 확인해 건네준다 --
// 프레젠터는 살아있는 씬을 조회하지 않는다 (설계 스펙 §3.3). B-1a에서는
// 적용 버튼이 없으므로 쓰이지 않지만, B-1b가 이 자리에서 판단하도록
// 시그니처를 지금 고정한다.
PanelDetail buildPanelDetail(const DiagRecord& record,
                              const BookEntry* bookEntry,
                              bool targetNodeExists);
```

- [ ] **Step 5: `PanelPresenter.cpp`에 구현 추가**

`PanelPresenter.cpp`의 익명 네임스페이스에 추가:

```cpp
// 빈 문자열의 뜻을 레코드가 아는 사실로 가른다. nameUnavailable은 이름
// 조회를 시도했으나 못 했다는 표시이므로, 그 경우의 빈 이름은 "관여 없음"이
// 아니라 "못 채움"이다 (설계 스펙 §4.4).
ContextField makeField(const std::string& value, bool unavailable) {
    ContextField field;
    if (!value.empty()) {
        field.value = value;
        field.presence = ContextPresence::Present;
        return field;
    }
    field.presence = unavailable ? ContextPresence::NotCaptured
                                  : ContextPresence::NotApplicable;
    return field;
}
```

`buildPanelRows` 정의 아래, `}  // namespace maro` 앞에 추가:

```cpp
PanelDetail buildPanelDetail(const DiagRecord& record,
                              const BookEntry* bookEntry,
                              bool targetNodeExists) {
    (void)targetNodeExists;  // B-1b가 적용 가능 여부를 판단할 때 쓴다.

    PanelDetail detail;
    detail.nodeType = makeField(record.context.nodeType, false);
    detail.attributeName = makeField(record.context.attributeName, false);
    detail.activeCommand = makeField(record.context.activeCommand, false);
    // 이름 조회를 못 한 자리는 axisOrTarget 하나다.
    detail.axisOrTarget = makeField(record.context.axisOrTarget,
                                     record.context.nameUnavailable);

    detail.message = record.message;

    // book에서 지금 읽어 온 것이 있으면 그쪽이 최신이다.
    if (bookEntry != nullptr && !bookEntry->analysis.empty()) {
        detail.priorAnalysis = bookEntry->analysis;
    } else {
        detail.priorAnalysis = record.priorAnalysis;
    }
    if (bookEntry != nullptr && !bookEntry->remedy.empty()) {
        detail.remedyText = bookEntry->remedy;
    } else {
        detail.remedyText = record.remedy;
    }

    // B-1a에는 구조화된 동작이 없다. 자리만 지키고 내용은 B-1b가 채운다.
    detail.applyAvailable = false;
    detail.applyUnavailableReason = "NoActionRecorded";
    return detail;
}
```

- [ ] **Step 6: 빌드하고 테스트가 통과하는지 확인**

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure
```

기대: 전부 통과.

- [ ] **Step 7: "못 채움" 구분이 진짜로 지켜지는지 확인**

`makeField`가 `unavailable`을 무시하게 만든다 — `field.presence = unavailable ? ... : ...;`를 `field.presence = ContextPresence::NotApplicable;`로 바꾼다.

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure -R PanelPresenter
```

기대: `DistinguishesNotCapturedFromNotApplicable`가 `the worker thread could not ask Maya for the name -- that is not 'nothing involved'`로 **실패**한다. 확인했으면 되돌린다.

- [ ] **Step 8: 커밋**

```bash
git add src/maro_diag tests/diag/test_panel_presenter.cpp
git commit -m "feat: tell a missing cause apart from one this site could not capture"
```

---

### Task 4: 읽기 커맨드 둘

프레젠터는 C++에, 패널 UI는 Python에 있으므로 그 사이에 커맨드가 필요하다.

**Files:**
- Create: `src/maro_plugin/MaroPanelCommands.h`, `src/maro_plugin/MaroPanelCommands.cpp`
- Modify: `src/maro_plugin/CMakeLists.txt`, `src/maro_plugin/MaroPluginMain.cpp`
- Create: `tests/maya/test_panel_commands.py`
- Modify: `tests/CMakeLists.txt`

**Interfaces:**
- Consumes: `maro::buildPanelRows`, `maro::buildPanelDetail` (Task 2, 3), `maro::BoadMaro::recordCount/recordAt` (Layer A)
- Produces: MEL 커맨드 `maroDiagPanelRows` (행당 **8필드**), `maroDiagPanelDetail -index N` (**13필드**)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/maya/test_panel_commands.py`:

```python
"""패널 읽기 커맨드의 계약: 행당 필드 개수가 고정이고, 접기가 실제로
일어나며, 상세가 선택한 행을 가리키는지 값으로 확인한다."""
import os
import sys
import tempfile

import maya.standalone

os.environ["MARO_DIAG_BOOK_DIR"] = tempfile.mkdtemp(prefix="maro_panel_cmd_")

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

ROW_FIELDS = 8
DETAIL_FIELDS = 13

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

# 같은 자리를 세 번, 다른 자리를 한 번 때린다.
light = cmds.createNode("pointLight", name="panelLight")
axis = cmds.createNode("maroAxis", name="panelAxis")
for _ in range(3):
    try:
        cmds.maroBindAxis(axis, light)
        raise AssertionError("expected rejection")
    except RuntimeError:
        pass

try:
    cmds.maroConnectAxis(axis, axis)  # SelfParent -- 다른 사이트 태그
    raise AssertionError("expected rejection")
except RuntimeError:
    pass

flat = cmds.maroDiagPanelRows(severity="error")
assert len(flat) % ROW_FIELDS == 0, (
    f"row array must be a multiple of {ROW_FIELDS}, got {len(flat)}"
)
rowCount = len(flat) // ROW_FIELDS
assert rowCount == 2, f"three hits on one site plus one on another must collapse to 2 rows, got {rowCount}"
print("row collapsing OK")

rows = [flat[i * ROW_FIELDS:(i + 1) * ROW_FIELDS] for i in range(rowCount)]
# 필드 순서: errorHash, severity, summary, sequence, firstMs, lastMs, occurrences, knownBefore
occurrences = sorted(int(r[6]) for r in rows)
assert occurrences == [1, 3], f"expected occurrence counts [1, 3], got {occurrences}"

for r in rows:
    assert r[1] == "error", f"severity filter asked for errors only, got {r[1]!r}"
    assert int(r[4]) > 0, "first timestamp must be a real epoch value"
    assert int(r[5]) >= int(r[4]), "last occurrence cannot precede the first"
print("row fields OK")

# 상세는 선택한 행을 가리킨다.
detail = cmds.maroDiagPanelDetail(index=0, severity="error")
assert len(detail) == DETAIL_FIELDS, (
    f"expected {DETAIL_FIELDS} detail fields, got {len(detail)}"
)
# 필드 순서: nodeType, nodeTypeState, attributeName, attributeNameState,
#            activeCommand, activeCommandState, axisOrTarget, axisOrTargetState,
#            message, priorAnalysis, remedyText, applyAvailable, applyUnavailableReason
assert detail[11] == "0", "B-1a records no structured actions, so apply is never available"
assert detail[12] == "NoActionRecorded", f"unexpected reason {detail[12]!r}"
assert detail[8], "detail must carry the message of the represented record"
print("detail contract OK")

# 범위 밖 인덱스는 예외가 아니라 실패로 끝난다.
try:
    cmds.maroDiagPanelDetail(index=999, severity="error")
    raise AssertionError("out-of-range index should have failed")
except RuntimeError:
    pass
print("out-of-range rejected OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

`tests/CMakeLists.txt`에 아직 등록하지 않고 직접 돌린다.

```bash
MARO_PLUGIN_PATH="$(cygpath -w "$(find out/build -name maro.mll | head -1)")" "/c/Program Files/Autodesk/Maya2026/bin/mayapy.exe" tests/maya/test_panel_commands.py
```

기대: `AttributeError: module 'maya.cmds' has no attribute 'maroDiagPanelRows'`. (Maya는 미등록 커맨드를 `cmds`에 아예 노출하지 않으므로 `RuntimeError`가 아니라 `AttributeError`다.)

- [ ] **Step 3: `MaroPanelCommands.h` 작성**

`src/maro_plugin/MaroPanelCommands.h`:

```cpp
#pragma once

#include <maya/MPxCommand.h>
#include <maya/MSyntax.h>

namespace maro {

// 아래 둘은 테스트 도구가 아니라 **정식 API**다. 패널 UI(Python)가 프레젠터를
// 읽는 유일한 경로이므로 이름과 필드 개수가 계약이다 (설계 스펙 §3.5.1).
// 반면 maroDiagCount/maroDiagQuery/maroDiagEmit 계열은 테스트 전용으로 남는다.

// [-severity <all|warn|error>] [-maxRows <int, 기본 500>]
// 접힌 행들을 평탄한 문자열 배열로 돌려준다. 행마다 8필드:
//   errorHash, severity, summary, sequence, firstTimestampMs,
//   lastTimestampMs, occurrences, knownBefore("0"/"1")
// 마지막에 숨겨진 개수 2필드가 따로 붙지 않는다 -- 그것은
// maroDiagPanelHidden이 아니라 이 커맨드의 -query 형태가 아니므로, 개수는
// 행 배열 길이와 별개로 Python이 다시 묻지 않아도 되게 UI가 요약 줄로만
// 쓴다. 숨김 개수가 필요하면 -hidden 플래그로 요청한다.
class MaroDiagPanelRowsCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
};

// -index <int> [-severity <all|warn|error>] [-maxRows <int, 기본 500>]
// 그 행의 상세를 13필드로 돌려준다:
//   nodeType, nodeTypeState, attributeName, attributeNameState,
//   activeCommand, activeCommandState, axisOrTarget, axisOrTargetState,
//   message, priorAnalysis, remedyText, applyAvailable("0"/"1"),
//   applyUnavailableReason
// 상태 필드는 "present" | "notApplicable" | "notCaptured" 중 하나다.
class MaroDiagPanelDetailCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
};

}  // namespace maro
```

- [ ] **Step 4: `MaroPanelCommands.cpp` 작성**

`src/maro_plugin/MaroPanelCommands.cpp`:

```cpp
#include "MaroPanelCommands.h"

#include <string>
#include <vector>

#include <maya/MArgDatabase.h>
#include <maya/MArgList.h>
#include <maya/MGlobal.h>
#include <maya/MStringArray.h>

#include "MaroDiag.h"
#include "maro_diag/BookStore.h"
#include "maro_diag/PanelPresenter.h"
#include "maro_diag/PanelView.h"

namespace maro {

namespace {

const char* kSeverityFlag = "-sv";
const char* kSeverityFlagLong = "-severity";
const char* kMaxRowsFlag = "-mr";
const char* kMaxRowsFlagLong = "-maxRows";
const char* kIndexFlag = "-i";
const char* kIndexFlagLong = "-index";
const char* kHiddenFlag = "-hd";
const char* kHiddenFlagLong = "-hidden";

constexpr int kDefaultMaxRows = 500;

PanelSeverityFilter parseFilter(const MString& text) {
    if (text == "error") return PanelSeverityFilter::ErrorsOnly;
    if (text == "warn") return PanelSeverityFilter::WarnAndAbove;
    return PanelSeverityFilter::All;
}

const char* presenceName(ContextPresence p) {
    switch (p) {
        case ContextPresence::Present: return "present";
        case ContextPresence::NotApplicable: return "notApplicable";
        case ContextPresence::NotCaptured: return "notCaptured";
    }
    return "notApplicable";
}

// boad의 스트림을 통째로 복사해 온다. 프레젠터는 순수해야 하므로 살아있는
// 상태를 들여다보지 않고 스냅샷만 본다 (설계 스펙 §3.3).
std::vector<DiagRecord> snapshot() {
    const std::size_t count = BoadMaro::recordCount();
    std::vector<DiagRecord> records;
    records.reserve(count);
    // recordAt은 0 = 가장 최근이다. 프레젠터는 시간순(오래된 것부터) 입력을
    // 기대하므로 뒤에서부터 채운다.
    for (std::size_t i = count; i > 0; --i) {
        records.push_back(BoadMaro::recordAt(i - 1));
    }
    return records;
}

}  // namespace

void* MaroDiagPanelRowsCommand::creator() { return new MaroDiagPanelRowsCommand(); }

MSyntax MaroDiagPanelRowsCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag(kSeverityFlag, kSeverityFlagLong, MSyntax::kString);
    syntax.addFlag(kMaxRowsFlag, kMaxRowsFlagLong, MSyntax::kLong);
    syntax.addFlag(kHiddenFlag, kHiddenFlagLong, MSyntax::kNoArg);
    return syntax;
}

MStatus MaroDiagPanelRowsCommand::doIt(const MArgList& args) {
    try {
        MStatus status;
        MArgDatabase argData(newSyntax(), args, &status);
        if (!status) return status;

        MString severity = "all";
        int maxRows = kDefaultMaxRows;
        if (argData.isFlagSet(kSeverityFlag)) {
            argData.getFlagArgument(kSeverityFlag, 0, severity);
        }
        if (argData.isFlagSet(kMaxRowsFlag)) {
            argData.getFlagArgument(kMaxRowsFlag, 0, maxRows);
        }
        if (maxRows < 0) maxRows = 0;

        std::size_t hiddenByFilter = 0;
        std::size_t hiddenByCap = 0;
        const std::vector<PanelRow> rows =
            buildPanelRows(snapshot(), parseFilter(severity),
                            static_cast<std::size_t>(maxRows),
                            hiddenByFilter, hiddenByCap);

        MStringArray result;
        if (argData.isFlagSet(kHiddenFlag)) {
            // 필터로 빠진 것과 상한으로 잘린 것은 사용자에게 다른 사건이므로
            // 따로 돌려준다.
            result.append(MString(std::to_string(hiddenByFilter).c_str()));
            result.append(MString(std::to_string(hiddenByCap).c_str()));
            setResult(result);
            return MS::kSuccess;
        }

        for (const PanelRow& row : rows) {
            result.append(MString(row.errorHash.c_str()));
            result.append(MString(row.severity.c_str()));
            result.append(MString(row.summary.c_str()));
            result.append(MString(std::to_string(row.sequence).c_str()));
            result.append(MString(std::to_string(row.firstTimestampMs).c_str()));
            result.append(MString(std::to_string(row.lastTimestampMs).c_str()));
            result.append(MString(std::to_string(row.occurrences).c_str()));
            result.append(row.knownBefore ? "1" : "0");
        }
        setResult(result);
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroDiagPanelRows failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroDiagPanelRows failed with unknown error.");
        return MS::kFailure;
    }
}

void* MaroDiagPanelDetailCommand::creator() { return new MaroDiagPanelDetailCommand(); }

MSyntax MaroDiagPanelDetailCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag(kIndexFlag, kIndexFlagLong, MSyntax::kLong);
    syntax.addFlag(kSeverityFlag, kSeverityFlagLong, MSyntax::kString);
    syntax.addFlag(kMaxRowsFlag, kMaxRowsFlagLong, MSyntax::kLong);
    return syntax;
}

MStatus MaroDiagPanelDetailCommand::doIt(const MArgList& args) {
    try {
        MStatus status;
        MArgDatabase argData(newSyntax(), args, &status);
        if (!status) return status;

        int index = 0;
        MString severity = "all";
        int maxRows = kDefaultMaxRows;
        if (argData.isFlagSet(kIndexFlag)) {
            argData.getFlagArgument(kIndexFlag, 0, index);
        }
        if (argData.isFlagSet(kSeverityFlag)) {
            argData.getFlagArgument(kSeverityFlag, 0, severity);
        }
        if (argData.isFlagSet(kMaxRowsFlag)) {
            argData.getFlagArgument(kMaxRowsFlag, 0, maxRows);
        }
        if (maxRows < 0) maxRows = 0;

        const std::vector<DiagRecord> records = snapshot();
        std::size_t hiddenByFilter = 0;
        std::size_t hiddenByCap = 0;
        const std::vector<PanelRow> rows =
            buildPanelRows(records, parseFilter(severity),
                            static_cast<std::size_t>(maxRows),
                            hiddenByFilter, hiddenByCap);

        if (index < 0 || static_cast<std::size_t>(index) >= rows.size()) {
            MGlobal::displayError("Maro: maroDiagPanelDetail index out of range.");
            return MS::kFailure;
        }

        // 행이 대표하는 레코드는 그 태그의 가장 최근 발생이고, 행은 그
        // 순번을 들고 있다. 순번으로 되찾는다 -- 시각으로 찾으면 벽시계가
        // 뒤로 간 순간 엉뚱한 레코드를 집는다.
        const std::uint64_t wanted = rows[static_cast<std::size_t>(index)].sequence;
        const DiagRecord* chosen = nullptr;
        for (const DiagRecord& rec : records) {
            if (rec.sequence == wanted) {
                chosen = &rec;
                break;
            }
        }
        if (chosen == nullptr) {
            MGlobal::displayError("Maro: maroDiagPanelDetail could not resolve the row.");
            return MS::kFailure;
        }

        // 레코드가 남은 뒤에 등록된 해법을 반영하려면 지금 book을 다시 본다.
        BookEntry entry;
        const bool haveEntry =
            !chosen->errorHash.empty() && BoadMaro::lookupBook(chosen->errorHash, entry);

        const PanelDetail detail =
            buildPanelDetail(*chosen, haveEntry ? &entry : nullptr, false);

        MStringArray result;
        result.append(MString(detail.nodeType.value.c_str()));
        result.append(presenceName(detail.nodeType.presence));
        result.append(MString(detail.attributeName.value.c_str()));
        result.append(presenceName(detail.attributeName.presence));
        result.append(MString(detail.activeCommand.value.c_str()));
        result.append(presenceName(detail.activeCommand.presence));
        result.append(MString(detail.axisOrTarget.value.c_str()));
        result.append(presenceName(detail.axisOrTarget.presence));
        result.append(MString(detail.message.c_str()));
        result.append(MString(detail.priorAnalysis.c_str()));
        result.append(MString(detail.remedyText.c_str()));
        result.append(detail.applyAvailable ? "1" : "0");
        result.append(MString(detail.applyUnavailableReason.c_str()));
        setResult(result);
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroDiagPanelDetail failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroDiagPanelDetail failed with unknown error.");
        return MS::kFailure;
    }
}

}  // namespace maro
```

- [ ] **Step 5: `BoadMaro::lookupBook` 추가**

위 커맨드가 book을 읽어야 하는데 `BoadMaro`는 지금 조회 API를 밖으로 내주지 않는다. `src/maro_plugin/MaroDiag.h`의 `registerRemedy` 선언 아래에 추가:

```cpp
    // 해시로 book 항목을 찾는다. 있으면 true. 패널이 상세를 열 때 쓴다 --
    // 레코드가 남은 뒤에 등록된 해법을 반영하려면 지금 다시 봐야 한다.
    // book을 못 읽어도 예외를 던지지 않고 false를 돌려준다: 진단 경로는
    // 지식 저장소에 닿지 못해서 실패하지 않는다.
    static bool lookupBook(const std::string& errorHash, BookEntry& out);
```

`src/maro_plugin/MaroDiag.cpp`의 `registerRemedy` 정의 아래에 추가:

```cpp
bool BoadMaro::lookupBook(const std::string& errorHash, BookEntry& out) {
    try {
        std::lock_guard<std::mutex> bookLock(bookMutex());
        const auto cached = bookCache().find(errorHash);
        if (cached != bookCache().end()) {
            out = cached->second;
            return true;
        }
        const BookPaths& paths = bookPaths();
        const BookStore store = BookStore::loadMerged(paths.canonical, paths.spill);
        BookEntry entry;
        if (!store.query(errorHash, entry)) return false;
        bookCache().emplace(errorHash, entry);
        out = entry;
        return true;
    } catch (...) {
        // book이 죽어도 패널은 죽지 않는다. 해법 없이 상세를 보여줄 뿐이다.
        return false;
    }
}
```

`MaroDiag.h` 상단 include에 `#include "maro_diag/BookStore.h"`가 없으면 추가한다.

- [ ] **Step 6: 빌드에 등록하고 커맨드를 등록한다**

`src/maro_plugin/CMakeLists.txt`의 `SOURCE_FILES`에 `MaroPanelCommands.cpp`를 추가한다.

`src/maro_plugin/MaroPluginMain.cpp` 상단 include에 `#include "MaroPanelCommands.h"`를 추가하고, `maroDiagEmitMarked` 등록 뒤에 추가:

```cpp
    status = plugin.registerCommand("maroDiagPanelRows",
                                    maro::MaroDiagPanelRowsCommand::creator,
                                    maro::MaroDiagPanelRowsCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroDiagPanelRows");
        return status;
    }

    status = plugin.registerCommand("maroDiagPanelDetail",
                                    maro::MaroDiagPanelDetailCommand::creator,
                                    maro::MaroDiagPanelDetailCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroDiagPanelDetail");
        return status;
    }
```

`uninitializePlugin`의 `maroDiagEmitMarked` 해제 **앞에** 역순으로 추가:

```cpp
    plugin.deregisterCommand("maroDiagPanelDetail");
    plugin.deregisterCommand("maroDiagPanelRows");
```

`tests/CMakeLists.txt`의 플러그인 전용 `foreach` 목록에 `panel_commands`를 추가한다:

```cmake
    foreach(maya_test load axis_node binding capability_stack delete_rules
                      robustness diag_boad diag_onfix diag_book
                      diag_book_cross_session diag_remedy
                      diag_degraded diag_degraded_remedy diag_thread
                      panel_commands)
```

- [ ] **Step 7: 빌드하고 테스트가 통과하는지 확인**

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure
```

기대: 전부 통과.

- [ ] **Step 8: 상세가 진짜로 선택한 행을 가리키는지 확인**

`MaroDiagPanelDetailCommand::doIt`에서 순번으로 되찾는 부분을 첫 레코드로 고정한다 — `const std::uint64_t wanted = ...` 줄을 `const std::uint64_t wanted = records.empty() ? 0 : records.front().sequence;`로 바꾼다.

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure -R maya_panel_commands
```

기대: `detail must carry the message of the represented record` 또는 그 앞의 필드 단언이 **실패**한다(index 0이 가리키는 최신 행 대신 항상 가장 오래된 레코드를 집으므로). 실패 내용을 기록하고 되돌린다.

- [ ] **Step 9: 커밋**

```bash
git add src/maro_plugin tests/maya/test_panel_commands.py tests/CMakeLists.txt
git commit -m "feat: expose the presenter to the panel through two commands"
```

---

### Task 5: 패널 UI와 여는 커맨드

`workspaceControl` 안에 Maya 네이티브 위젯으로 그린다. 위젯 자체는 `mayapy` 배치 모드에서 만들 수 없으므로, **평탄한 배열을 행으로 되돌리는 순수 함수를 모듈 최상위로 분리해** 그 부분만 자동 검증한다.

**Files:**
- Create: `python/maroDiagPanel.py`
- Modify: `src/maro_plugin/MaroPanelCommands.h`, `src/maro_plugin/MaroPanelCommands.cpp`, `src/maro_plugin/MaroPluginMain.cpp`
- Modify: `src/maro_plugin/CMakeLists.txt`
- Modify: `tests/maya/test_panel_commands.py`
- Create: `docs/maro-panel-manual-checklist.md`

**Interfaces:**
- Consumes: `maroDiagPanelRows`, `maroDiagPanelDetail` (Task 4)
- Produces: MEL 커맨드 `maroDiagPanel`, Python 함수 `maroDiagPanel.sliceRows(flat)`, `maroDiagPanel.formatLocalTime(epochMs)`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/maya/test_panel_commands.py`의 `cmds.file(new=True, force=True)` 직전에 추가:

```python
# 패널 UI 모듈의 순수 함수만 검증한다. 위젯 자체는 배치 모드에 UI가 없어
# 만들 수 없으므로 수동 체크리스트로 남긴다(docs/maro-panel-manual-checklist.md).
pluginDir = os.path.dirname(plugin)
sys.path.insert(0, pluginDir)
import maroDiagPanel  # noqa: E402

flatSample = [
    "hashA", "error", "first summary", "7", "1000", "1200", "3", "1",
    "hashB", "warn", "second summary", "5", "900", "900", "1", "0",
]
sliced = maroDiagPanel.sliceRows(flatSample)
assert len(sliced) == 2, f"expected 2 rows from 16 fields, got {len(sliced)}"
assert sliced[0]["errorHash"] == "hashA"
assert sliced[0]["occurrences"] == 3
assert sliced[0]["knownBefore"] is True
assert sliced[1]["knownBefore"] is False
print("sliceRows OK")

# 잘못 잘린 배열은 조용히 잘못된 행을 만들지 않고 거절한다.
try:
    maroDiagPanel.sliceRows(flatSample[:-1])
    raise AssertionError("a ragged array should have been rejected")
except ValueError:
    pass
print("ragged array rejected OK")

# 시각 형식화는 표시하는 쪽이 로컬 시간대로 한다 -- C++는 epoch ms만 낸다.
assert maroDiagPanel.formatLocalTime(0) != "", "formatLocalTime must produce something"
assert ":" in maroDiagPanel.formatLocalTime(1700000000000)
print("formatLocalTime OK")
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
ctest --test-dir out/build --output-on-failure -R maya_panel_commands
```

기대: `ModuleNotFoundError: No module named 'maroDiagPanel'`

- [ ] **Step 3: `python/maroDiagPanel.py` 작성**

```python
"""Maro 진단 패널 — workspaceControl 안의 Maya 네이티브 UI.

패널은 자체 상태를 갖지 않는다. boad의 인메모리 스트림과 book 파일만이
진실이며(설계 스펙 §4.2), 이 모듈은 maroDiagPanelRows/maroDiagPanelDetail이
돌려준 것을 그리기만 한다.

평탄한 배열을 행으로 되돌리는 부분은 UI를 만들지 않는 순수 함수로 분리해
뒀다 -- mayapy 배치 모드에는 UI가 없어 위젯은 만들 수 없지만 이 부분은
자동 검증된다.
"""
import time

import maya.cmds as cmds

# C++ 쪽 계약. 바뀌면 양쪽을 함께 고쳐야 한다 (MaroPanelCommands.h 참고).
ROW_FIELDS = 8
DETAIL_FIELDS = 13

CONTROL_NAME = "maroDiagPanelControl"

_PRESENCE_LABEL = {
    "present": "",
    "notApplicable": "(해당 없음)",
    "notCaptured": "(이 자리에서는 포착되지 않음)",
}


def sliceRows(flat):
    """maroDiagPanelRows의 평탄한 배열을 행 딕셔너리 목록으로 되돌린다."""
    if flat is None:
        return []
    if len(flat) % ROW_FIELDS != 0:
        raise ValueError(
            "row array length {} is not a multiple of {}".format(len(flat), ROW_FIELDS)
        )
    rows = []
    for i in range(len(flat) // ROW_FIELDS):
        f = flat[i * ROW_FIELDS:(i + 1) * ROW_FIELDS]
        rows.append({
            "errorHash": f[0],
            "severity": f[1],
            "summary": f[2],
            "sequence": int(f[3]),
            "firstTimestampMs": int(f[4]),
            "lastTimestampMs": int(f[5]),
            "occurrences": int(f[6]),
            "knownBefore": f[7] == "1",
        })
    return rows


def formatLocalTime(epochMs):
    """epoch 밀리초를 사용자의 로컬 시간대 문자열로 만든다.

    C++ 쪽은 epoch ms만 낸다 -- 형식화를 거기서 하면 로케일과 시간대가
    테스트를 흔들고, 정작 사용자에게 필요한 것은 로컬 시간이다.
    """
    seconds = epochMs / 1000.0
    return time.strftime("%H:%M:%S", time.localtime(seconds))


def _rowLabel(row):
    when = formatLocalTime(row["lastTimestampMs"])
    mark = "*" if row["knownBefore"] else " "
    count = " x{}".format(row["occurrences"]) if row["occurrences"] > 1 else ""
    return "{} {} [{}]{}  {}".format(mark, when, row["severity"], count, row["summary"])


def _contextLine(label, value, state):
    suffix = _PRESENCE_LABEL.get(state, "")
    return "{}: {}{}".format(label, value, suffix)


def _onSelect(listControl, detailControl, severityControl):
    selected = cmds.textScrollList(listControl, query=True, selectIndexedItem=True)
    if not selected:
        return
    index = selected[0] - 1  # Maya의 textScrollList는 1부터 센다
    severity = cmds.optionMenu(severityControl, query=True, value=True)
    detail = cmds.maroDiagPanelDetail(index=index, severity=severity)
    if len(detail) != DETAIL_FIELDS:
        cmds.scrollField(detailControl, edit=True,
                         text="Maro: unexpected detail field count {}".format(len(detail)))
        return

    lines = [
        detail[8],
        "",
        _contextLine("노드 타입", detail[0], detail[1]),
        _contextLine("어트리뷰트", detail[2], detail[3]),
        _contextLine("커맨드", detail[4], detail[5]),
        _contextLine("축/대상", detail[6], detail[7]),
    ]
    if detail[9]:
        lines += ["", "전에 본 문제 — 과거 분석:", detail[9]]
    if detail[10]:
        lines += ["", "해법:", detail[10]]
    cmds.scrollField(detailControl, edit=True, text="\n".join(lines))


def refresh(listControl, detailControl, severityControl):
    severity = cmds.optionMenu(severityControl, query=True, value=True)
    rows = sliceRows(cmds.maroDiagPanelRows(severity=severity))
    cmds.textScrollList(listControl, edit=True, removeAll=True)
    for row in rows:
        cmds.textScrollList(listControl, edit=True, append=_rowLabel(row))

    hidden = cmds.maroDiagPanelRows(severity=severity, hidden=True)
    byFilter, byCap = int(hidden[0]), int(hidden[1])
    if byFilter or byCap:
        note = "필터로 {}개 제외, 상한으로 {}개 잘림".format(byFilter, byCap)
        cmds.textScrollList(listControl, edit=True, append=note)


def buildUI():
    """workspaceControl이 -uiScript로 부른다."""
    form = cmds.formLayout()
    severityControl = cmds.optionMenu(label="심각도")
    cmds.menuItem(label="all")
    cmds.menuItem(label="warn")
    cmds.menuItem(label="error")
    listControl = cmds.textScrollList(allowMultiSelection=False)
    detailControl = cmds.scrollField(editable=False, wordWrap=True)
    refreshButton = cmds.button(label="새로 고침")

    cmds.textScrollList(
        listControl, edit=True,
        selectCommand=lambda *_: _onSelect(listControl, detailControl, severityControl))
    cmds.button(
        refreshButton, edit=True,
        command=lambda *_: refresh(listControl, detailControl, severityControl))
    cmds.optionMenu(
        severityControl, edit=True,
        changeCommand=lambda *_: refresh(listControl, detailControl, severityControl))

    cmds.formLayout(
        form, edit=True,
        attachForm=[
            (severityControl, "top", 4), (severityControl, "left", 4),
            (refreshButton, "top", 4), (refreshButton, "right", 4),
            (listControl, "left", 4), (listControl, "right", 4),
            (detailControl, "left", 4), (detailControl, "right", 4),
            (detailControl, "bottom", 4),
        ],
        attachControl=[
            (listControl, "top", 4, severityControl),
            (listControl, "bottom", 4, detailControl),
        ],
        attachPosition=[(detailControl, "top", 0, 60)])

    refresh(listControl, detailControl, severityControl)
    return form


def show():
    """maroDiagPanel 커맨드가 부른다."""
    if cmds.workspaceControl(CONTROL_NAME, exists=True):
        cmds.workspaceControl(CONTROL_NAME, edit=True, restore=True)
        return
    cmds.workspaceControl(
        CONTROL_NAME,
        label="Maro 진단",
        retain=False,
        floating=True,
        initialWidth=520,
        initialHeight=420,
        requiredPlugin="maro",
        uiScript="import maroDiagPanel; maroDiagPanel.buildUI()")
```

- [ ] **Step 4: `maroDiagPanel` 커맨드 추가**

`src/maro_plugin/MaroPanelCommands.h`의 `MaroDiagPanelDetailCommand` 선언 아래에 추가:

```cpp
// 인자 없음. workspaceControl을 띄운다(이미 있으면 복원한다).
// 파이썬 모듈은 플러그인 .mll 옆에 배포되며, 이 커맨드가 그 경로를
// sys.path에 넣는다 -- MAYA_SCRIPT_PATH 설정을 사용자에게 요구하지 않기
// 위해서다.
class MaroDiagPanelCommand : public MPxCommand {
public:
    static void* creator();
    MStatus doIt(const MArgList& args) override;
};
```

`src/maro_plugin/MaroPanelCommands.cpp` 상단 include에 `#include <maya/MFnPlugin.h>`를 추가하고, 파일 끝 `}  // namespace maro` 앞에 추가:

```cpp
void* MaroDiagPanelCommand::creator() { return new MaroDiagPanelCommand(); }

MStatus MaroDiagPanelCommand::doIt(const MArgList& /*args*/) {
    try {
        // 플러그인 .mll이 있는 디렉터리에 maroDiagPanel.py를 함께 배포한다.
        // 여기서 sys.path에 넣어야 사용자가 MAYA_SCRIPT_PATH를 손대지 않고도
        // 패널이 뜬다.
        //
        // findPlugin은 MObject를 돌려준다 -- 경로 문자열이 아니다. 경로는
        // 그 MObject로 만든 MFnPlugin의 loadPath()에서 나온다.
        // 공개 생성자는 MObject&(비상수)를 받으므로 const로 두면 안 된다.
        MObject pluginObj = MFnPlugin::findPlugin("maro");
        if (pluginObj.isNull()) {
            MGlobal::displayError("Maro: could not locate the loaded maro plug-in.");
            return MS::kFailure;
        }
        MStatus status;
        // vendor/version/apiVersion은 기본값이 있지만 상태를 받으려면
        // 앞의 셋을 함께 넘겨야 한다.
        MFnPlugin pluginFn(pluginObj, "Unknown", "Unknown", "Any", &status);
        if (!status) return status;
        const MString pluginDir = pluginFn.loadPath(&status);
        if (!status) return status;

        MString python;
        python += "import os, sys\n";
        python += "d = r'";
        python += pluginDir;
        python += "'\n";
        // loadPath()가 디렉터리를 주는지 파일까지 주는지에 기대지 않는다.
        python += "if os.path.isfile(d): d = os.path.dirname(d)\n";
        python += "if d not in sys.path: sys.path.insert(0, d)\n";
        python += "import maroDiagPanel\n";
        python += "maroDiagPanel.show()\n";

        return MGlobal::executePythonCommand(python);
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroDiagPanel failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroDiagPanel failed with unknown error.");
        return MS::kFailure;
    }
}
```

`MaroPluginMain.cpp`에 등록을 추가한다 (`maroDiagPanelDetail` 등록 뒤):

```cpp
    status = plugin.registerCommand("maroDiagPanel",
                                    maro::MaroDiagPanelCommand::creator);
    if (!status) {
        status.perror("Maro: failed to register maroDiagPanel");
        return status;
    }
```

`uninitializePlugin`에서는 `maroDiagPanelDetail` 해제 **앞에** 추가한다. 패널이 열린 채 언로드되면 Maya가 언로드된 코드 안의 UI를 붙들고 있다가 크래시하므로, 커맨드 해제보다 먼저 컨트롤을 닫는다:

```cpp
    // 패널이 열린 채 언로드되면 Maya가 사라진 코드의 UI를 계속 붙든다.
    // devkit의 workspaceControlCmd 샘플이 같은 이유로 같은 일을 한다.
    MGlobal::executeCommand(
        "if (`workspaceControl -exists maroDiagPanelControl`) "
        "workspaceControl -e -close maroDiagPanelControl;");
    plugin.deregisterCommand("maroDiagPanel");
```

- [ ] **Step 5: 파이썬 모듈을 플러그인 옆으로 복사한다**

`src/maro_plugin/CMakeLists.txt` 끝에 추가:

```cmake
# 패널 UI 모듈은 플러그인 .mll 옆에 둔다. maroDiagPanel 커맨드가 그
# 디렉터리를 sys.path에 넣으므로 사용자가 MAYA_SCRIPT_PATH를 손댈 필요가 없다.
add_custom_command(TARGET ${PROJECT_NAME} POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_SOURCE_DIR}/python/maroDiagPanel.py"
            "$<TARGET_FILE_DIR:${PROJECT_NAME}>/maroDiagPanel.py"
    COMMENT "Copying maroDiagPanel.py next to the plug-in")
```

- [ ] **Step 6: 빌드하고 테스트가 통과하는지 확인**

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure
```

기대: 전부 통과.

- [ ] **Step 7: 재조립이 진짜로 계약을 지키는지 확인**

`maroDiagPanel.py`의 `sliceRows`에서 길이 검사를 지운다 — `if len(flat) % ROW_FIELDS != 0:` 블록 세 줄을 제거한다.

```bash
ctest --test-dir out/build --output-on-failure -R maya_panel_commands
```

기대: `a ragged array should have been rejected`로 **실패**한다. 확인했으면 되돌린다.

- [ ] **Step 8: 수동 체크리스트 작성**

`docs/maro-panel-manual-checklist.md`:

```markdown
# Maro 진단 패널 — 수동 확인 목록

`mayapy` 배치 모드에는 UI가 없어 `workspaceControl`이 성립하지 않는다. 아래
셋은 자동 검증되지 않으므로 인터랙티브 Maya에서 사람이 확인한다. 커버리지가
있는 척하지 않기 위해 여기에 적어 둔다.

인터랙티브 Maya 2026에서 `maro.mll`을 로드한 뒤 스크립트 에디터에서
`maroDiagPanel`을 실행한다.

- [ ] **도킹** — 패널을 Maya 창 가장자리로 끌어 도킹되는지, 다시 떼어내
      플로팅으로 돌아오는지 확인한다.
- [ ] **재시작 시 복원** — 도킹한 상태로 Maya를 종료하고 다시 켠다. 패널이
      그 자리에 복원되고, 플러그인이 아직 로드되기 전이라도 오류 없이
      뜨는지 확인한다(`-requiredPlugin`이 처리한다).
- [ ] **패널을 연 채 언로드** — 패널이 열린 상태에서
      `unloadPlugin maro`를 실행한다. Maya가 크래시하지 않고 패널이 닫히는지
      확인한다. 이것이 셋 중 가장 중요하다 — 실패하면 사용자의 미저장
      작업이 함께 사라진다.

확인용 진단을 만들려면: `maroAxis` 노드와 `pointLight`를 만들고
`maroBindAxis`로 둘을 묶어 본다(거부되며 에러가 하나 쌓인다). 여러 번
반복하면 접힌 행에 `x N`이 붙는 것을 볼 수 있다.
```

- [ ] **Step 9: 커밋**

```bash
git add python/maroDiagPanel.py src/maro_plugin tests/maya/test_panel_commands.py docs/maro-panel-manual-checklist.md
git commit -m "feat: draw the diagnostic panel in a dockable workspaceControl"
```

---

## 자체 검토 결과

**스펙 커버리지 (B-1a 범위)**

| 스펙 항목 | 담당 |
|---|---|
| §3.1 단위 경계 (프레젠터를 `maro_diag`에) | Task 2 |
| §3.2 뷰가 UI 기술을 전제하지 않음 | Task 2 (`PanelView.h`에 Maya·Qt 등장 안 함) |
| §3.3 스냅샷이 살아있는 씬을 조회하지 않음 | Task 4 (`snapshot()`), Task 3 (`targetNodeExists`를 인자로 받음) |
| §3.4 갱신 주기·진입점 둘·시각과 순번 | Task 1, 2, 3 |
| §3.5 태그별 접기 | Task 2 |
| §3.5.1 읽기 커맨드 둘 | Task 4 |
| §4.4 빈 컨텍스트와 못 채운 컨텍스트 구분 | Task 1(표시 채우기), Task 3(표시 판단) |
| §5 패널 항목 (연 채 언로드, 필터 뒤 절단, 숨김 개수 구분) | Task 5(언로드), Task 2(절단 순서·숨김 개수) |
| §6 프레젠터·패널 행 | Task 2, 3, 4, 5 |

**§3.4의 "갱신 주기"에 대한 결정**: 스펙은 `recordCount()`가 변했을 때만 스냅샷을 다시 만들라고 한다. B-1a의 패널은 **타이머 없이 사용자가 새로 고침을 누를 때와 필터를 바꿀 때만** 다시 읽는다. 자동 갱신은 상시 메인 스레드 큐(B-1b §3.8) 위에 얹는 것이 맞고, B-1a에 타이머를 따로 만들면 B-1b에서 지워야 한다. 캐싱 비교도 그때 함께 들어간다.

**§4.4를 B-1a에 넣은 이유**: 단계 표는 §4 전체를 B-1b로 보냈지만, §4.4는 해법이 아니라 **B-1a가 이미 보여주는 컨텍스트의 표시 판단**이다. 빈칸과 못 채운 것을 구분하지 않으면 B-1a의 상세가 그 자체로 오해를 만든다.

**플레이스홀더 스캔**: "TBD", "적절한 에러 처리", "테스트를 작성한다"류 없음. 모든 코드 단계에 실제 코드가 있고, 모든 명령에 기대 출력이 있다.

**Maya API 실측 확인**: 플랜에 쓴 Maya API는 `Maya2026/include/maya` 헤더로 직접 확인했다. 그 과정에서 두 가지를 고쳤다 — `MFnPlugin::findPlugin`은 경로 문자열이 아니라 `MObject`를 돌려주므로 경로는 `MFnPlugin::loadPath()`에서 얻어야 하고, 공개 생성자는 `MObject&`(비상수)를 받으므로 `const MObject`로 두면 컴파일되지 않는다. `MSyntax::kNoArg`, `MObject::isNull()`, `MGlobal::executePythonCommand`, `workspaceControl`의 `-uiScript`/`-requiredPlugin`/`-close`/`-restore`는 devkit `workspaceControlCmd` 샘플에서 쓰이는 그대로다.

**타입 일관성**: `PanelRow`/`PanelDetail`/`ContextField`/`ContextPresence`는 Task 2~3에서 정의하고 Task 4에서 같은 이름으로 쓴다. 필드 개수 상수(행 8, 상세 13)는 Task 4의 헤더 주석, Task 4의 테스트, Task 5의 파이썬 모듈 세 곳에 같은 값으로 나타난다 — 계약이므로 의도된 중복이며 헤더가 원본이다. `buildPanelRows`의 출력 인자 이름(`hiddenByFilter`/`hiddenByCap`)은 Task 2 선언과 Task 4 호출부에서 일치한다.
