# Maro Layer B-1b-1 — 크래시를 건너 살아남는 저널 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Maya가 죽어도 그 직전의 진단이 남고, 다음 실행이 비정상 종료를 알아채 그것을 되살리며, 같은 진단이 여러 크래시 직전에 반복해서 나타났다면 그 사실을 말해 준다.

**Architecture:** 저널의 쓰기·읽기·집계는 전부 Maya를 모르는 순수 C++(`maro_diag`)에 두고 gtest로 덮는다. 플러그인 쪽은 배선만 한다 — 경로를 건네고, 세션 시작·종료 줄을 찍고, 로드 시 회전과 복원을 트리거한다. 저널 쓰기는 열어둔 핸들에 한 줄 append하는 것이 전부이며 `fsync`는 하지 않는다.

**Tech Stack:** C++17, `<filesystem>`, nlohmann/json, Maya 2026 devkit, GoogleTest, `mayapy`, CMake + Ninja

설계: `docs/superpowers/specs/2026-08-15-maro-layer-b-diagnostic-panel-design.md` §3.6, §3.7

## Global Constraints

- C++17, 네임스페이스 `maro`, 접두사 `maro`, UTF-8 소스
- **`maro_diag`는 Maya 헤더로부터 자유롭게 유지한다** — 이 플랜이 넣는 저널 로직 전부가 여기 들어가며, 그것이 gtest로 덮이는 이유다
- **예외는 Maya 콜백을 넘지 않는다** — 하나만 새도 세션이 끝나고 사용자의 미저장 작업이 날아간다
- **진단 경로는 지식 저장소에 닿지 못해서 실패하지 않는다** — 저널을 못 열어도 진단은 그대로 돈다
- **`boad`가 진단의 단일 출구다**
- **워커 스레드에서 Maya API를 부르지 않는다**
- **순서를 정하는 어떤 판단도 시각을 읽지 않는다** — 전부 순번을 본다
- Maya 테스트는 `unloadPlugin` 전에 `cmds.file(new=True, force=True)`를 부른다
- 다음 경로는 건드리지 않는다: `src/control_bridge/`, `src/image_bridge/`, `src/Maro_library/`, `MaroCmd.cpp`, `moveTool.cpp`, `rosSimCmd.cpp`, `Maro_DebugUtility/`, `Maro_Management/`
- 새 테스트는 전부 **일부러 구현을 깨서 실패하는 것까지 확인**한다. 이 프로젝트에서 통과하던 테스트가 틀린 구현도 함께 통과시킨 경우가 열 번 있었고, 직전 B-1a는 다섯 태스크가 **전부** 초판에 그런 구멍을 안고 나왔다
- 빌드 환경: `Launch-VsDevShell.ps1`은 이 머신에서 `vswhere.exe`를 못 찾아 `INCLUDE`/`LIB`를 비운 채 조용히 성공하고 엉뚱한 `basetsd.h` 누락 에러로 나타난다. **빌드와 같은 PowerShell 호출 안에서** `VsDevCmd.bat`를 설정한다

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cd C:\Users\ckd30\Projects\Maya_Ros_Sim
cmake --build out/build
```

빌드가 `LNK1168`로 실패하면 잔존 `mayapy.exe`가 DLL을 잡고 있는 것이다: `Get-CimInstance Win32_Process -Filter "Name='mayapy.exe'" | Invoke-CimMethod -MethodName Terminate`.

## 범위 밖 (B-1b-2)

상시 메인 스레드 큐, `BookEntry`의 `remedyAction`, 해법 동작 3종(`selectNode`/`setAttribute`/`disconnect`)과 그 적용 경로. 이 플랜의 어떤 태스크도 그것들을 만들지 않는다. 상세 출력의 `applyAvailable`/`applyUnavailableReason` 두 필드는 B-1a가 예약해 둔 그대로 `"0"`/`"NoActionRecorded"`로 남는다.

Layer C(감시자 프로세스, `offix`, `ghost`, `OSbridge`, 정본 `book` 쓰기)도 그대로 범위 밖이다. 이 저널은 기록을 보존할 뿐 크래시의 원인을 판정하지 않는다 — 스택도, 예외 정보도, 어느 모듈이 죽였는지도 모른다.

## 상세 필드 개수가 13에서 14로 늘어난다

B-1a는 필드 개수를 계약으로 얼리고 `applyAvailable`/`applyUnavailableReason` **두 자리만** 예약했다. §3.7의 크래시 인접 신호 자리는 예약돼 있지 않으므로, 이 플랜에서 개수가 실제로 바뀐다.

세 곳이 **함께** 움직여야 한다. 하나라도 뒤처지면 Python이 잘못된 폭으로 잘라 조용히 엉뚱한 값을 보여준다:

1. `src/maro_plugin/MaroPanelCommands.h`의 문서화된 필드 목록과 `.cpp`의 `append` 순서
2. `python/maroDiagPanel.py`의 `DETAIL_FIELDS`
3. `tests/maya/test_panel_commands.py`의 `DETAIL_FIELDS`

Task 6이 셋을 한 커밋에서 바꾸고, 그 커밋의 테스트가 세 값의 일치를 단언한다.

## 파일 구조

| 파일 | 책임 |
|---|---|
| `src/maro_diag/include/maro_diag/Journal.h` | 저널 줄의 타입과 상수. Maya도 파일도 모른다 |
| `src/maro_diag/include/maro_diag/JournalWriter.h` / `src/JournalWriter.cpp` | 경로 하나를 받아 append·세션 표식·태그별 억제·회전 |
| `src/maro_diag/include/maro_diag/JournalReader.h` / `src/JournalReader.cpp` | 저널 텍스트를 세션으로 파싱하고 크래시 인접 태그를 센다 |
| `tests/diag/test_journal_writer.cpp`, `tests/diag/test_journal_reader.cpp` | 위 둘의 gtest |
| `src/maro_plugin/MaroDiag.{h,cpp}` | 배선: 레코드마다 저널에 흘리고, 경로를 건네고, 복원 결과를 보관 |
| `src/maro_plugin/MaroPluginMain.cpp` | 세션 시작·종료 줄, 로드 시 회전 |
| `tests/maya/test_journal.py` | 두 프로세스로 비정상 종료와 복원을 검증 |

---

### Task 1: 저널 줄 형식과 기본 쓰기

세션은 `open` 줄로 시작한다. **세션 id는 두지 않는다** — 세션의 경계는 `open` 줄 자체이고, 세션은 `close` 줄이나 다음 `open` 줄에서 끝난다. 그래서 고유 id를 만들 필요도, 그것이 충돌할 걱정도 없다.

**Files:**
- Create: `src/maro_diag/include/maro_diag/Journal.h`
- Create: `src/maro_diag/include/maro_diag/JournalWriter.h`
- Create: `src/maro_diag/src/JournalWriter.cpp`
- Create: `tests/diag/test_journal_writer.cpp`
- Modify: `src/maro_diag/CMakeLists.txt`, `tests/CMakeLists.txt`

**Interfaces:**
- Consumes: `maro::DiagSeverity` (`maro_diag/DiagRecord.h`)
- Produces: `maro::JournalWriter` — 생성자 `JournalWriter(const std::filesystem::path&)`, `bool isOpen() const`, `void writeSessionOpen(std::uint64_t timestampMs)`, `void writeSessionClose(std::uint64_t timestampMs)`, `void writeRecord(std::uint64_t sequence, std::uint64_t timestampMs, DiagSeverity, const std::string& siteTag, const std::string& message)`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/diag/test_journal_writer.cpp`:

```cpp
#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>

#include "maro_diag/DiagRecord.h"
#include "maro_diag/Journal.h"
#include "maro_diag/JournalWriter.h"

namespace {

// 테스트마다 자기만의 빈 디렉터리를 쓴다 -- 이전 실행이 남긴 저널이
// 다음 실행의 단언을 바꾸면 안 된다 (Layer A가 book에서 겪은 함정).
std::filesystem::path freshDir(const std::string& name) {
    const std::filesystem::path dir =
        std::filesystem::temp_directory_path() / ("maro_journal_test_" + name);
    std::error_code ec;
    std::filesystem::remove_all(dir, ec);
    std::filesystem::create_directories(dir, ec);
    return dir;
}

std::string readAll(const std::filesystem::path& p) {
    std::ifstream in(p, std::ios::binary);
    std::ostringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

std::size_t countLines(const std::string& text) {
    if (text.empty()) return 0;
    std::size_t n = 0;
    for (const char c : text) {
        if (c == '\n') ++n;
    }
    return n;
}

}  // namespace

TEST(JournalWriter, WritesOneLinePerRecord) {
    const std::filesystem::path dir = freshDir("one_line");
    const std::filesystem::path file = dir / "journal.jsonl";
    {
        maro::JournalWriter writer(file);
        ASSERT_TRUE(writer.isOpen());
        writer.writeSessionOpen(1000);
        writer.writeRecord(1, 1001, maro::DiagSeverity::Error, "Site.A", "first");
        writer.writeRecord(2, 1002, maro::DiagSeverity::Warn, "", "second");
        writer.writeSessionClose(1003);
    }

    const std::string text = readAll(file);
    EXPECT_EQ(countLines(text), 4u) << "open + two records + close";
    EXPECT_NE(text.find("\"kind\":\"session\""), std::string::npos);
    EXPECT_NE(text.find("\"event\":\"open\""), std::string::npos);
    EXPECT_NE(text.find("\"event\":\"close\""), std::string::npos);
    EXPECT_NE(text.find("Site.A"), std::string::npos);
}

// 진단 경로는 저널을 못 열어서 실패하지 않는다. 쓸 수 없는 경로를 줘도
// 생성자가 던지지 않고, 이후 호출이 전부 조용히 무시돼야 한다.
TEST(JournalWriter, DegradesWhenTheFileCannotBeOpened) {
    const std::filesystem::path dir = freshDir("unwritable");
    // 파일을 하나 만들어 두고 그 "밑"을 경로로 준다 -- 디렉터리가 될 수
    // 없는 자리라 열기가 반드시 실패한다.
    const std::filesystem::path blocker = dir / "blocker";
    { std::ofstream(blocker) << "x"; }
    const std::filesystem::path impossible = blocker / "nested" / "journal.jsonl";

    maro::JournalWriter writer(impossible);
    EXPECT_FALSE(writer.isOpen());

    // 아래 호출들이 던지면 이 테스트는 그 자리에서 죽는다.
    writer.writeSessionOpen(1000);
    writer.writeRecord(1, 1001, maro::DiagSeverity::Error, "Site.A", "first");
    writer.writeSessionClose(1002);
    SUCCEED() << "a journal that cannot be opened must not throw or crash";
}

// 이어서 쓰는 저널이므로 기존 내용을 절대 지우지 않는다.
TEST(JournalWriter, AppendsInsteadOfTruncating) {
    const std::filesystem::path dir = freshDir("append");
    const std::filesystem::path file = dir / "journal.jsonl";
    {
        maro::JournalWriter writer(file);
        writer.writeSessionOpen(1000);
        writer.writeSessionClose(1001);
    }
    {
        maro::JournalWriter writer(file);
        writer.writeSessionOpen(2000);
        writer.writeSessionClose(2001);
    }

    const std::string text = readAll(file);
    EXPECT_EQ(countLines(text), 4u) << "the second session must not erase the first";
    EXPECT_NE(text.find("1000"), std::string::npos);
    EXPECT_NE(text.find("2000"), std::string::npos);
}

// 메시지에 개행이나 따옴표가 들어가도 한 줄 = 한 항목이 깨지면 안 된다.
TEST(JournalWriter, KeepsOneLinePerEntryWhenTheMessageHasNewlines) {
    const std::filesystem::path dir = freshDir("escaping");
    const std::filesystem::path file = dir / "journal.jsonl";
    {
        maro::JournalWriter writer(file);
        writer.writeSessionOpen(1000);
        writer.writeRecord(1, 1001, maro::DiagSeverity::Error, "Site.A",
                            "line one\nline two \"quoted\"");
        writer.writeSessionClose(1002);
    }

    const std::string text = readAll(file);
    EXPECT_EQ(countLines(text), 3u)
        << "a newline inside the message must be escaped, not split the entry";
}
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
ctest --test-dir out/build --output-on-failure -R JournalWriter
```

기대: 컴파일 실패 — `maro_diag/Journal.h`가 없다.

- [ ] **Step 3: `Journal.h` 작성**

`src/maro_diag/include/maro_diag/Journal.h`:

```cpp
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

#include "maro_diag/DiagRecord.h"

namespace maro {

// 저널 한 줄의 종류. 세션 id는 두지 않는다 -- 세션의 경계는 open 줄 자체이고
// 세션은 close 줄이나 다음 open 줄에서 끝난다. 그래서 고유 id를 만들 필요도,
// 그것이 충돌할 걱정도 없다.
enum class JournalLineKind {
    SessionOpen,
    SessionClose,
    Record,
    Suppressed,  // 태그별 억제로 생략된 개수를 알리는 줄
    Unknown,     // 파싱 실패. 버리되 그 줄 때문에 나머지를 포기하지 않는다
};

// 저널이 보관하는 세션 수. 무한히 자라면 안 되고(Layer A가 인메모리
// 스트림에서 그 함정에 빠졌다), 동시에 크래시 인접 신호가 이 위에서 도므로
// 분모가 될 세션이 몇 개는 남아 있어야 한다. 10이면 최근 작업 맥락 안에
// 머물면서 문턱(비정상 종료 2회)을 넘길 표본이 나온다.
constexpr std::size_t kJournalSessionsKept = 10;

// 태그별 억제 예산. 한 태그가 이 창 안에 이만큼 쓰고 나면 창이 닫힐 때까지
// 더 쓰지 않는다. 서로 다른 태그는 서로의 예산을 잡아먹지 않는다 -- 병렬
// 평가에서 여러 노드의 경고가 번갈아 들어오므로 "연속된 같은 태그"를
// 기준으로 삼으면 억제가 한 번도 안 걸린다.
constexpr std::size_t kJournalMaxLinesPerTagPerWindow = 5;
constexpr std::uint64_t kJournalSuppressionWindowMs = 1000;

// 크래시 인접 신호가 보는 "마지막 구간"의 크기. 줄 수로 정의하는 이유는
// 시간으로 정의하면 아이들 상태로 오래 떠 있다가 죽은 세션에서 창이 텅
// 비기 때문이다 -- 진단이 뜸했던 세션일수록 창이 비고, 정작 그 드문 진단이
// 후보에서 빠진다.
constexpr std::size_t kJournalTailRecordsForSignal = 20;

const char* severityToJournalName(DiagSeverity severity);
DiagSeverity severityFromJournalName(const std::string& name);

}  // namespace maro
```

- [ ] **Step 4: `JournalWriter.h` 작성**

`src/maro_diag/include/maro_diag/JournalWriter.h`:

```cpp
#pragma once

#include <cstdint>
#include <filesystem>
#include <fstream>
#include <string>

#include "maro_diag/DiagRecord.h"

namespace maro {

// 저널에 한 줄씩 덧붙이는 쓰기 전용 핸들. 경로 하나만 알고 Maya는 모른다 --
// 그래서 억제와 회전 같은 까다로운 판단이 전부 gtest로 덮인다.
//
// fsync는 하지 않는다. 크래시 포렌식에는 필요 없기 때문이다: 파일에 append한
// 내용은 커널 페이지 캐시가 들고 있고 프로세스가 죽어도 OS가 그것을 디스크에
// 쓴다. 잃는 것은 기계 전원이 나갈 때뿐이고 그건 이 서브시스템이 대비하는
// 사건이 아니다. 매 레코드마다 fsync를 부르는 것이야말로 진짜 부담이다.
//
// 열지 못해도 던지지 않는다. 진단 경로는 지식 저장소에 닿지 못해서 실패하지
// 않는다는 규율이 저널에도 그대로 적용된다 -- 보존이 안 될 뿐 진단은 돈다.
class JournalWriter {
public:
    explicit JournalWriter(const std::filesystem::path& path);

    bool isOpen() const { return out_.is_open(); }

    void writeSessionOpen(std::uint64_t timestampMs);
    void writeSessionClose(std::uint64_t timestampMs);
    void writeRecord(std::uint64_t sequence, std::uint64_t timestampMs,
                      DiagSeverity severity, const std::string& siteTag,
                      const std::string& message);

    JournalWriter(const JournalWriter&) = delete;
    JournalWriter& operator=(const JournalWriter&) = delete;

private:
    void writeLine(const std::string& json);

    std::ofstream out_;
};

}  // namespace maro
```

- [ ] **Step 5: `JournalWriter.cpp` 작성**

`src/maro_diag/src/JournalWriter.cpp`:

```cpp
#include "maro_diag/JournalWriter.h"

#include <nlohmann/json.hpp>

#include "maro_diag/Journal.h"

namespace maro {

const char* severityToJournalName(DiagSeverity severity) {
    switch (severity) {
        case DiagSeverity::Info: return "info";
        case DiagSeverity::Warn: return "warn";
        case DiagSeverity::DevInfo: return "devInfo";
        case DiagSeverity::Error: return "error";
    }
    return "unknown";
}

DiagSeverity severityFromJournalName(const std::string& name) {
    if (name == "warn") return DiagSeverity::Warn;
    if (name == "devInfo") return DiagSeverity::DevInfo;
    if (name == "error") return DiagSeverity::Error;
    return DiagSeverity::Info;
}

JournalWriter::JournalWriter(const std::filesystem::path& path) {
    try {
        // 부모 디렉터리가 없으면 만든다. 실패해도 던지지 않는다 -- 아래
        // open이 실패하고 isOpen()이 false로 남을 뿐이다.
        std::error_code ec;
        std::filesystem::create_directories(path.parent_path(), ec);
        out_.open(path, std::ios::out | std::ios::app | std::ios::binary);
    } catch (...) {
        // 삼킨다. 저널을 못 여는 것은 진단을 멈출 이유가 되지 않는다.
    }
}

void JournalWriter::writeLine(const std::string& json) {
    if (!out_.is_open()) return;
    try {
        out_ << json << '\n';
        // flush는 한다 -- 버퍼가 프로세스와 함께 사라지면 크래시 직전
        // 몇 줄을 잃는데, 그 몇 줄이 정확히 알고 싶은 것이다. flush는
        // 커널에 넘기는 것일 뿐 fsync가 아니라서 디스크 대기가 없다.
        out_.flush();
    } catch (...) {
    }
}

void JournalWriter::writeSessionOpen(std::uint64_t timestampMs) {
    nlohmann::json j;
    j["kind"] = "session";
    j["event"] = "open";
    j["t"] = timestampMs;
    writeLine(j.dump());
}

void JournalWriter::writeSessionClose(std::uint64_t timestampMs) {
    nlohmann::json j;
    j["kind"] = "session";
    j["event"] = "close";
    j["t"] = timestampMs;
    writeLine(j.dump());
}

void JournalWriter::writeRecord(std::uint64_t sequence, std::uint64_t timestampMs,
                                 DiagSeverity severity, const std::string& siteTag,
                                 const std::string& message) {
    nlohmann::json j;
    j["kind"] = "record";
    j["seq"] = sequence;
    j["t"] = timestampMs;
    j["sev"] = severityToJournalName(severity);
    j["tag"] = siteTag;
    j["msg"] = message;
    // dump()가 개행과 따옴표를 이스케이프하므로 한 줄 = 한 항목이 유지된다.
    writeLine(j.dump());
}

}  // namespace maro
```

- [ ] **Step 6: 빌드에 등록**

`src/maro_diag/CMakeLists.txt`의 `add_library(maro_diag STATIC` 목록에 `src/JournalWriter.cpp`를 추가한다:

```cmake
add_library(maro_diag STATIC
    src/ErrorHash.cpp
    src/BookStore.cpp
    src/PanelPresenter.cpp
    src/JournalWriter.cpp
)
```

`tests/CMakeLists.txt`의 `add_executable(maro_diag_tests` 목록에 추가:

```cmake
add_executable(maro_diag_tests
    diag/test_error_hash.cpp
    diag/test_book_store.cpp
    diag/test_panel_presenter.cpp
    diag/test_journal_writer.cpp
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

- [ ] **Step 8: 강등이 진짜로 조용한지 확인**

`JournalWriter::writeLine`의 `if (!out_.is_open()) return;`를 지운다.

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure -R JournalWriter
```

기대: `DegradesWhenTheFileCannotBeOpened`가 닫힌 스트림에 쓰다 실패하거나 예외로 죽는다. 확인했으면 되돌린다.

- [ ] **Step 9: 이어쓰기가 진짜인지 확인**

생성자의 `std::ios::app`를 `std::ios::trunc`로 바꾼다.

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure -R JournalWriter
```

기대: `AppendsInsteadOfTruncating`이 `the second session must not erase the first`로 **실패**한다(줄 수가 2). 확인했으면 되돌린다.

- [ ] **Step 10: 커밋**

```bash
git add src/maro_diag tests/diag/test_journal_writer.cpp tests/CMakeLists.txt
git commit -m "feat: give diagnostics a file that outlives the process"
```

---

### Task 2: 태그별 억제와 세션 회전

억제와 회전은 저널이 스스로를 감당하게 만드는 두 규칙이다. 억제가 없으면 매 평가마다 터지는 경고가 초당 수백 줄이 되고, 회전이 없으면 저널이 무한히 자란다.

**Files:**
- Modify: `src/maro_diag/include/maro_diag/JournalWriter.h`, `src/maro_diag/src/JournalWriter.cpp`
- Modify: `tests/diag/test_journal_writer.cpp`

**Interfaces:**
- Consumes: `maro::kJournalMaxLinesPerTagPerWindow`, `maro::kJournalSuppressionWindowMs`, `maro::kJournalSessionsKept` (Task 1)
- Produces: `maro::JournalWriter::rotate()` — 정적 함수 `static void rotate(const std::filesystem::path&)`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/diag/test_journal_writer.cpp` 끝에 추가:

```cpp
// 같은 태그가 창 안에서 예산을 넘기면 더 쓰지 않고, 창이 닫힐 때 몇 개를
// 생략했는지 한 줄로 남긴다.
TEST(JournalWriter, SuppressesOneTagBeyondItsBudget) {
    const std::filesystem::path dir = freshDir("suppress");
    const std::filesystem::path file = dir / "journal.jsonl";
    {
        maro::JournalWriter writer(file);
        writer.writeSessionOpen(1000);
        // 같은 창(1000~1999) 안에서 같은 태그로 20번.
        for (std::uint64_t i = 0; i < 20; ++i) {
            writer.writeRecord(i + 1, 1000 + i, maro::DiagSeverity::Warn,
                                "Site.Spam", "spam");
        }
        // 창을 넘겨 다음 줄을 쓰면 생략 개수가 나온다.
        writer.writeRecord(100, 3000, maro::DiagSeverity::Warn, "Site.Spam", "after");
        writer.writeSessionClose(3001);
    }

    const std::string text = readAll(file);
    // open + 예산 5줄 + suppressed 1줄 + 창 밖 1줄 + close = 9
    EXPECT_EQ(countLines(text), 9u)
        << "twenty hits on one tag inside one window must not become twenty lines";
    EXPECT_NE(text.find("\"kind\":\"suppressed\""), std::string::npos);
    EXPECT_NE(text.find("\"count\":15"), std::string::npos)
        << "fifteen of the twenty were dropped";
}

// 서로 다른 태그는 서로의 예산을 잡아먹지 않는다. 병렬 평가에서 여러 노드의
// 경고가 번갈아 들어오는 것이 실제 입력이므로, 이것이 깨지면 억제를 넣은
// 이유가 통째로 무너진다.
TEST(JournalWriter, TagsDoNotSpendEachOthersBudget) {
    const std::filesystem::path dir = freshDir("interleaved");
    const std::filesystem::path file = dir / "journal.jsonl";
    {
        maro::JournalWriter writer(file);
        writer.writeSessionOpen(1000);
        // 두 태그를 번갈아 4번씩 -- 각자 예산(5) 안이므로 전부 쓰여야 한다.
        for (std::uint64_t i = 0; i < 4; ++i) {
            writer.writeRecord(i * 2 + 1, 1000 + i, maro::DiagSeverity::Warn,
                                "Site.A", "a");
            writer.writeRecord(i * 2 + 2, 1000 + i, maro::DiagSeverity::Warn,
                                "Site.B", "b");
        }
        writer.writeSessionClose(1500);
    }

    const std::string text = readAll(file);
    EXPECT_EQ(countLines(text), 10u) << "open + 4 A + 4 B + close";
    EXPECT_EQ(text.find("\"kind\":\"suppressed\""), std::string::npos)
        << "neither tag exceeded its own budget, so nothing was suppressed";
}

// 창이 지나면 예산이 되살아난다.
TEST(JournalWriter, BudgetRefillsAfterTheWindow) {
    const std::filesystem::path dir = freshDir("refill");
    const std::filesystem::path file = dir / "journal.jsonl";
    {
        maro::JournalWriter writer(file);
        writer.writeSessionOpen(1000);
        for (std::uint64_t i = 0; i < 5; ++i) {
            writer.writeRecord(i + 1, 1000, maro::DiagSeverity::Warn, "Site.A", "a");
        }
        // 창을 훌쩍 넘긴 시각 -- 예산이 되살아나 다시 5줄이 쓰여야 한다.
        for (std::uint64_t i = 0; i < 5; ++i) {
            writer.writeRecord(i + 10, 9000, maro::DiagSeverity::Warn, "Site.A", "a");
        }
        writer.writeSessionClose(9500);
    }

    const std::string text = readAll(file);
    EXPECT_EQ(countLines(text), 12u) << "open + 5 + 5 + close, with nothing suppressed";
}

// 회전은 최근 N 세션만 남긴다. 오래된 세션이 통째로 사라지고 최근 것은
// 온전히 남아야 한다.
TEST(JournalWriter, RotateKeepsOnlyTheMostRecentSessions) {
    const std::filesystem::path dir = freshDir("rotate");
    const std::filesystem::path file = dir / "journal.jsonl";
    {
        maro::JournalWriter writer(file);
        // 보관 한도보다 5개 많은 세션을 쓴다. 각 세션은 자기 번호를 담은
        // 레코드를 하나씩 갖는다.
        for (std::uint64_t s = 0; s < maro::kJournalSessionsKept + 5; ++s) {
            writer.writeSessionOpen(1000 + s * 10);
            writer.writeRecord(s + 1, 1001 + s * 10, maro::DiagSeverity::Error,
                                "Site.S" + std::to_string(s), "session marker");
            writer.writeSessionClose(1002 + s * 10);
        }
    }

    maro::JournalWriter::rotate(file);

    const std::string text = readAll(file);
    EXPECT_EQ(text.find("Site.S0"), std::string::npos)
        << "the oldest session must be gone";
    EXPECT_EQ(text.find("Site.S4"), std::string::npos)
        << "everything beyond the keep limit must be gone";
    EXPECT_NE(text.find("Site.S5"), std::string::npos)
        << "the tenth-from-last session must survive";
    EXPECT_NE(text.find("Site.S14"), std::string::npos)
        << "the newest session must survive";
    EXPECT_EQ(countLines(text), maro::kJournalSessionsKept * 3)
        << "each kept session contributes open + record + close";
}

// 보관 한도보다 적으면 아무것도 버리지 않는다.
TEST(JournalWriter, RotateLeavesAShortJournalAlone) {
    const std::filesystem::path dir = freshDir("rotate_short");
    const std::filesystem::path file = dir / "journal.jsonl";
    {
        maro::JournalWriter writer(file);
        writer.writeSessionOpen(1000);
        writer.writeRecord(1, 1001, maro::DiagSeverity::Error, "Site.Only", "only");
        writer.writeSessionClose(1002);
    }
    const std::string before = readAll(file);

    maro::JournalWriter::rotate(file);

    EXPECT_EQ(readAll(file), before) << "nothing to drop, so nothing may change";
}

// 저널이 아예 없어도 회전이 죽지 않는다 -- 첫 실행이 그 상태다.
TEST(JournalWriter, RotateOnAMissingFileIsHarmless) {
    const std::filesystem::path dir = freshDir("rotate_missing");
    const std::filesystem::path file = dir / "journal.jsonl";
    maro::JournalWriter::rotate(file);
    SUCCEED() << "rotating a journal that does not exist must not throw";
}
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
ctest --test-dir out/build --output-on-failure -R JournalWriter
```

기대: 컴파일 실패 — `JournalWriter::rotate`가 없다.

- [ ] **Step 3: `JournalWriter.h`에 억제 상태와 회전 선언 추가**

`JournalWriter.h`의 `#include` 목록에 `#include <unordered_map>`을 추가하고, `writeRecord` 선언 아래에 추가:

```cpp
    // 최근 N 세션만 남기고 오래된 것부터 버린다. 파일이 없으면 아무 일도
    // 하지 않는다 -- 첫 실행이 그 상태다. 열려 있는 writer와 무관하게
    // 부를 수 있도록 정적이다: 플러그인은 이번 세션의 open 줄을 쓰기
    // **전에** 회전을 돌린다.
    static void rotate(const std::filesystem::path& path);
```

`private:` 아래 `std::ofstream out_;` 앞에 추가:

```cpp
    // 태그별 억제 예산. 창의 시작 시각과 그 창에서 이미 쓴 줄 수를 함께
    // 들고 있다. 서로 다른 태그가 서로의 예산을 잡아먹지 않는 것이
    // 핵심이다 -- 병렬 평가에서는 여러 노드의 경고가 번갈아 들어오므로
    // "연속된 같은 태그"를 기준으로 삼으면 억제가 한 번도 안 걸린다.
    struct TagBudget {
        std::uint64_t windowStartMs = 0;
        std::size_t written = 0;
        std::size_t suppressed = 0;
    };

    void flushSuppressed(const std::string& siteTag, TagBudget& budget,
                          std::uint64_t timestampMs);

    std::unordered_map<std::string, TagBudget> budgets_;
```

- [ ] **Step 4: `JournalWriter.cpp`에 억제와 회전 구현**

`JournalWriter.cpp` 상단 include에 추가:

```cpp
#include <algorithm>
#include <sstream>
#include <vector>
```

`writeRecord`를 아래로 교체:

```cpp
void JournalWriter::flushSuppressed(const std::string& siteTag, TagBudget& budget,
                                     std::uint64_t timestampMs) {
    if (budget.suppressed == 0) return;
    nlohmann::json j;
    j["kind"] = "suppressed";
    j["t"] = timestampMs;
    j["tag"] = siteTag;
    j["count"] = budget.suppressed;
    writeLine(j.dump());
    budget.suppressed = 0;
}

void JournalWriter::writeRecord(std::uint64_t sequence, std::uint64_t timestampMs,
                                 DiagSeverity severity, const std::string& siteTag,
                                 const std::string& message) {
    if (!out_.is_open()) return;

    // 억제는 태그별로 센다. 태그가 없는 레코드(에러가 아닌 것)는 심각도와
    // 메시지 첫 줄을 키로 삼는다 -- 같은 문장이 반복되는 경고가 실제
    // 억제 대상이기 때문이다.
    std::string key = siteTag;
    if (key.empty()) {
        const std::size_t cut = message.find('\n');
        key = std::string(severityToJournalName(severity)) + ":" +
              (cut == std::string::npos ? message : message.substr(0, cut));
    }

    TagBudget& budget = budgets_[key];
    if (timestampMs < budget.windowStartMs ||
        timestampMs - budget.windowStartMs >= kJournalSuppressionWindowMs) {
        // 새 창이다. 지난 창에서 생략한 것이 있으면 먼저 알린다.
        flushSuppressed(key, budget, timestampMs);
        budget.windowStartMs = timestampMs;
        budget.written = 0;
    }

    if (budget.written >= kJournalMaxLinesPerTagPerWindow) {
        ++budget.suppressed;
        return;
    }
    ++budget.written;

    nlohmann::json j;
    j["kind"] = "record";
    j["seq"] = sequence;
    j["t"] = timestampMs;
    j["sev"] = severityToJournalName(severity);
    j["tag"] = siteTag;
    j["msg"] = message;
    writeLine(j.dump());
}

void JournalWriter::rotate(const std::filesystem::path& path) {
    try {
        std::error_code ec;
        if (!std::filesystem::exists(path, ec)) return;

        std::vector<std::string> lines;
        {
            std::ifstream in(path, std::ios::binary);
            if (!in.is_open()) return;
            std::string line;
            while (std::getline(in, line)) {
                if (!line.empty() && line.back() == '\r') line.pop_back();
                lines.push_back(line);
            }
        }

        // 세션의 경계는 open 줄이다. 뒤에서부터 세어 보관 한도째 open 줄을
        // 찾고, 그 앞을 전부 버린다.
        std::vector<std::size_t> openAt;
        for (std::size_t i = 0; i < lines.size(); ++i) {
            if (lines[i].find("\"event\":\"open\"") != std::string::npos) {
                openAt.push_back(i);
            }
        }
        if (openAt.size() <= kJournalSessionsKept) return;

        const std::size_t firstKept = openAt[openAt.size() - kJournalSessionsKept];

        std::ofstream out(path, std::ios::out | std::ios::trunc | std::ios::binary);
        if (!out.is_open()) return;
        for (std::size_t i = firstKept; i < lines.size(); ++i) {
            out << lines[i] << '\n';
        }
    } catch (...) {
        // 회전에 실패해도 진단은 계속된다. 저널이 좀 길어질 뿐이다.
    }
}
```

- [ ] **Step 5: 빌드하고 테스트가 통과하는지 확인**

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure
```

기대: 전부 통과.

- [ ] **Step 6: 억제가 진짜로 태그별인지 확인**

`writeRecord`에서 `TagBudget& budget = budgets_[key];`를 `TagBudget& budget = budgets_["*"];`로 바꾼다(모든 태그가 예산 하나를 공유하게 만든다).

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure -R JournalWriter
```

기대: `TagsDoNotSpendEachOthersBudget`이 `neither tag exceeded its own budget` 또는 줄 수 단언으로 **실패**한다. 확인했으면 되돌린다.

- [ ] **Step 7: 회전이 최근 쪽을 남기는지 확인**

`rotate`의 `openAt[openAt.size() - kJournalSessionsKept]`를 `openAt[kJournalSessionsKept]`로 바꾼다(앞에서부터 세게 만든다).

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure -R JournalWriter
```

기대: `RotateKeepsOnlyTheMostRecentSessions`가 `the newest session must survive` 또는 `Site.S0` 단언으로 **실패**한다. 확인했으면 되돌린다.

- [ ] **Step 8: 커밋**

```bash
git add src/maro_diag tests/diag/test_journal_writer.cpp
git commit -m "feat: keep one noisy tag from drowning the journal, and the journal from growing forever"
```

---

### Task 3: 저널 읽기와 비정상 종료 판정

**Files:**
- Create: `src/maro_diag/include/maro_diag/JournalReader.h`
- Create: `src/maro_diag/src/JournalReader.cpp`
- Create: `tests/diag/test_journal_reader.cpp`
- Modify: `src/maro_diag/CMakeLists.txt`, `tests/CMakeLists.txt`

**Interfaces:**
- Consumes: `maro::JournalLineKind`, `maro::severityFromJournalName` (Task 1)
- Produces: `maro::JournalRecord` (필드 `sequence`, `timestampMs`, `severity`, `siteTag`, `message`), `maro::JournalSession` (필드 `records`, `endedCleanly`), `maro::parseJournal(const std::string& text) -> std::vector<JournalSession>`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/diag/test_journal_reader.cpp`:

```cpp
#include <gtest/gtest.h>

#include <string>
#include <vector>

#include "maro_diag/Journal.h"
#include "maro_diag/JournalReader.h"

TEST(JournalReader, SplitsSessionsAtOpenLines) {
    const std::string text =
        R"({"kind":"session","event":"open","t":1000})" "\n"
        R"({"kind":"record","seq":1,"t":1001,"sev":"error","tag":"A","msg":"first"})" "\n"
        R"({"kind":"session","event":"close","t":1002})" "\n"
        R"({"kind":"session","event":"open","t":2000})" "\n"
        R"({"kind":"record","seq":2,"t":2001,"sev":"warn","tag":"B","msg":"second"})" "\n"
        R"({"kind":"session","event":"close","t":2002})" "\n";

    const std::vector<maro::JournalSession> sessions = maro::parseJournal(text);

    ASSERT_EQ(sessions.size(), 2u);
    EXPECT_TRUE(sessions[0].endedCleanly);
    EXPECT_TRUE(sessions[1].endedCleanly);
    ASSERT_EQ(sessions[0].records.size(), 1u);
    EXPECT_EQ(sessions[0].records[0].siteTag, "A");
    EXPECT_EQ(sessions[0].records[0].message, "first");
    EXPECT_EQ(sessions[0].records[0].sequence, 1u);
    EXPECT_EQ(sessions[1].records[0].siteTag, "B");
}

// 종료 줄 없이 끝난 세션이 곧 비정상 종료다. 타임아웃을 추측할 필요가 없다.
TEST(JournalReader, ASessionWithoutACloseLineEndedAbnormally) {
    const std::string text =
        R"({"kind":"session","event":"open","t":1000})" "\n"
        R"({"kind":"record","seq":1,"t":1001,"sev":"error","tag":"A","msg":"before the crash"})" "\n"
        R"({"kind":"session","event":"open","t":2000})" "\n"
        R"({"kind":"record","seq":2,"t":2001,"sev":"info","tag":"","msg":"next run"})" "\n"
        R"({"kind":"session","event":"close","t":2002})" "\n";

    const std::vector<maro::JournalSession> sessions = maro::parseJournal(text);

    ASSERT_EQ(sessions.size(), 2u);
    EXPECT_FALSE(sessions[0].endedCleanly)
        << "the first session was cut off by the next open, so it never closed";
    EXPECT_TRUE(sessions[1].endedCleanly);
}

// 파일 끝에서 끊긴 세션도 비정상이다 -- 이것이 가장 흔한 실제 크래시 모양이다.
TEST(JournalReader, ASessionCutOffAtEndOfFileEndedAbnormally) {
    const std::string text =
        R"({"kind":"session","event":"open","t":1000})" "\n"
        R"({"kind":"record","seq":1,"t":1001,"sev":"error","tag":"A","msg":"last words"})" "\n";

    const std::vector<maro::JournalSession> sessions = maro::parseJournal(text);

    ASSERT_EQ(sessions.size(), 1u);
    EXPECT_FALSE(sessions[0].endedCleanly);
    ASSERT_EQ(sessions[0].records.size(), 1u);
    EXPECT_EQ(sessions[0].records[0].message, "last words");
}

// 깨진 줄 하나가 나머지를 포기시키면 안 된다 -- 크래시가 마지막 줄을
// 반쯤 쓴 채 끝냈을 수 있고, 그 앞의 온전한 줄들이 정확히 알고 싶은 것이다.
TEST(JournalReader, SkipsAMalformedLineWithoutLosingTheRest) {
    const std::string text =
        R"({"kind":"session","event":"open","t":1000})" "\n"
        R"({"kind":"record","seq":1,"t":1001,"sev":"error","tag":"A","msg":"good"})" "\n"
        R"({"kind":"record","seq":2,"t":1002,"sev":"err)" "\n"   // 잘린 줄
        R"({"kind":"record","seq":3,"t":1003,"sev":"error","tag":"C","msg":"also good"})" "\n";

    const std::vector<maro::JournalSession> sessions = maro::parseJournal(text);

    ASSERT_EQ(sessions.size(), 1u);
    ASSERT_EQ(sessions[0].records.size(), 2u)
        << "the truncated line is dropped, the two intact ones survive";
    EXPECT_EQ(sessions[0].records[0].siteTag, "A");
    EXPECT_EQ(sessions[0].records[1].siteTag, "C");
}

// 억제 줄은 레코드가 아니다 -- 세지 않는다.
TEST(JournalReader, SuppressedLinesAreNotRecords) {
    const std::string text =
        R"({"kind":"session","event":"open","t":1000})" "\n"
        R"({"kind":"record","seq":1,"t":1001,"sev":"warn","tag":"A","msg":"x"})" "\n"
        R"({"kind":"suppressed","t":1002,"tag":"A","count":15})" "\n"
        R"({"kind":"session","event":"close","t":1003})" "\n";

    const std::vector<maro::JournalSession> sessions = maro::parseJournal(text);

    ASSERT_EQ(sessions.size(), 1u);
    EXPECT_EQ(sessions[0].records.size(), 1u);
}

TEST(JournalReader, AnEmptyJournalYieldsNoSessions) {
    EXPECT_TRUE(maro::parseJournal("").empty());
    EXPECT_TRUE(maro::parseJournal("\n\n").empty());
}
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
ctest --test-dir out/build --output-on-failure -R JournalReader
```

기대: 컴파일 실패 — `maro_diag/JournalReader.h`가 없다.

- [ ] **Step 3: `JournalReader.h` 작성**

`src/maro_diag/include/maro_diag/JournalReader.h`:

```cpp
#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "maro_diag/DiagRecord.h"

namespace maro {

// 저널에서 되살린 진단 하나. 인메모리 DiagRecord와 달리 컨텍스트나 book
// 관련 필드를 담지 않는다 -- 저널은 크래시를 건너 무슨 일이 있었는지를
// 보존할 뿐, 그 시점의 분석까지 복원하지는 않는다.
struct JournalRecord {
    std::uint64_t sequence = 0;
    std::uint64_t timestampMs = 0;
    DiagSeverity severity = DiagSeverity::Info;
    std::string siteTag;
    std::string message;
};

struct JournalSession {
    std::vector<JournalRecord> records;
    // 종료 줄로 끝났으면 true. false면 비정상 종료다 -- 다음 open 줄에
    // 밀려 끊겼거나 파일 끝에서 잘렸다는 뜻이고, 후자가 실제 크래시의
    // 가장 흔한 모양이다. 타임아웃을 추측할 필요가 없다는 것이 이 판정의
    // 핵심 이점이다.
    bool endedCleanly = false;
};

// 저널 텍스트를 세션으로 가른다. 세션의 경계는 open 줄이다.
//
// 깨진 줄은 버리되 그 줄 때문에 나머지를 포기하지 않는다 -- 크래시가
// 마지막 줄을 반쯤 쓴 채 끝냈을 수 있고, 그 앞의 온전한 줄들이 정확히
// 알고 싶은 것이기 때문이다.
std::vector<JournalSession> parseJournal(const std::string& text);

}  // namespace maro
```

- [ ] **Step 4: `JournalReader.cpp` 작성**

`src/maro_diag/src/JournalReader.cpp`:

```cpp
#include "maro_diag/JournalReader.h"

#include <sstream>

#include <nlohmann/json.hpp>

#include "maro_diag/Journal.h"

namespace maro {

std::vector<JournalSession> parseJournal(const std::string& text) {
    std::vector<JournalSession> sessions;
    std::istringstream in(text);
    std::string line;

    while (std::getline(in, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty()) continue;

        nlohmann::json j;
        try {
            j = nlohmann::json::parse(line);
        } catch (...) {
            // 깨진 줄 하나가 나머지를 포기시키지 않는다.
            continue;
        }

        const std::string kind = j.value("kind", std::string());
        if (kind == "session") {
            const std::string event = j.value("event", std::string());
            if (event == "open") {
                sessions.emplace_back();
            } else if (event == "close" && !sessions.empty()) {
                sessions.back().endedCleanly = true;
            }
            continue;
        }
        if (kind != "record") continue;   // suppressed 줄은 레코드가 아니다
        if (sessions.empty()) continue;   // open 줄 앞의 레코드는 버린다

        try {
            JournalRecord rec;
            rec.sequence = j.value("seq", std::uint64_t{0});
            rec.timestampMs = j.value("t", std::uint64_t{0});
            rec.severity = severityFromJournalName(j.value("sev", std::string()));
            rec.siteTag = j.value("tag", std::string());
            rec.message = j.value("msg", std::string());
            sessions.back().records.push_back(std::move(rec));
        } catch (...) {
            // 타입이 어긋난 줄도 그 줄만 버린다.
        }
    }
    return sessions;
}

}  // namespace maro
```

- [ ] **Step 5: 빌드에 등록**

`src/maro_diag/CMakeLists.txt`의 `add_library(maro_diag STATIC` 목록에 `src/JournalReader.cpp`를 추가한다:

```cmake
add_library(maro_diag STATIC
    src/ErrorHash.cpp
    src/BookStore.cpp
    src/PanelPresenter.cpp
    src/JournalWriter.cpp
    src/JournalReader.cpp
)
```

`tests/CMakeLists.txt`의 `add_executable(maro_diag_tests` 목록에 `diag/test_journal_reader.cpp`를 추가한다:

```cmake
add_executable(maro_diag_tests
    diag/test_error_hash.cpp
    diag/test_book_store.cpp
    diag/test_panel_presenter.cpp
    diag/test_journal_writer.cpp
    diag/test_journal_reader.cpp
)
```

- [ ] **Step 6: 빌드하고 테스트가 통과하는지 확인**

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure
```

기대: 전부 통과.

- [ ] **Step 7: 비정상 판정이 진짜인지 확인**

`parseJournal`에서 `sessions.emplace_back();`를 실행한 직후 `sessions.back().endedCleanly = true;`를 추가한다(모든 세션을 정상 종료로 만든다).

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure -R JournalReader
```

기대: `ASessionWithoutACloseLineEndedAbnormally`와 `ASessionCutOffAtEndOfFileEndedAbnormally`가 둘 다 **실패**한다. 확인했으면 되돌린다.

- [ ] **Step 8: 깨진 줄 처리가 진짜인지 확인**

`nlohmann::json::parse` 주변의 `catch (...) { continue; }`를 `catch (...) { return sessions; }`로 바꾼다(첫 깨진 줄에서 포기하게 만든다).

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure -R JournalReader
```

기대: `SkipsAMalformedLineWithoutLosingTheRest`가 레코드 수 1로 **실패**한다. 확인했으면 되돌린다.

- [ ] **Step 9: 커밋**

```bash
git add src/maro_diag tests/diag/test_journal_reader.cpp tests/CMakeLists.txt
git commit -m "feat: read a journal back and tell a clean exit from a crash"
```

---

### Task 4: 크래시 직전에 반복해서 나타난 태그 세기

이 신호는 **상관이지 인과가 아니다.** 크래시 직전에 있었다는 것이 크래시를 일으켰다는 뜻은 아니므로, 계산도 문구도 관측된 사실만 말한다.

**Files:**
- Modify: `src/maro_diag/include/maro_diag/JournalReader.h`, `src/maro_diag/src/JournalReader.cpp`
- Modify: `tests/diag/test_journal_reader.cpp`

**Interfaces:**
- Consumes: `maro::JournalSession` (Task 3), `maro::kJournalTailRecordsForSignal` (Task 1)
- Produces: `maro::CrashAdjacency` (필드 `abnormalSessionCount`, `appearancesByTag`), `maro::countCrashAdjacentTags(const std::vector<JournalSession>&) -> CrashAdjacency`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/diag/test_journal_reader.cpp` 끝에 추가:

```cpp
namespace {

maro::JournalSession makeSession(bool endedCleanly,
                                  const std::vector<std::string>& tags) {
    maro::JournalSession session;
    session.endedCleanly = endedCleanly;
    std::uint64_t seq = 1;
    for (const std::string& tag : tags) {
        maro::JournalRecord rec;
        rec.sequence = seq++;
        rec.timestampMs = 1000 + seq;
        rec.severity = maro::DiagSeverity::Error;
        rec.siteTag = tag;
        rec.message = "m";
        session.records.push_back(rec);
    }
    return session;
}

}  // namespace

// 정상 종료 세션은 분모에도 분자에도 들어가지 않는다.
TEST(JournalReader, CleanSessionsAreNotCounted) {
    std::vector<maro::JournalSession> sessions;
    sessions.push_back(makeSession(true, {"A", "B"}));
    sessions.push_back(makeSession(true, {"A"}));

    const maro::CrashAdjacency adj = maro::countCrashAdjacentTags(sessions);

    EXPECT_EQ(adj.abnormalSessionCount, 0u);
    EXPECT_TRUE(adj.appearancesByTag.empty());
}

// 한 세션은 한 표다. 한 세션에서 40번 나온 태그도 표는 하나다 -- 안 그러면
// 폭주한 태그 하나가 모든 세션의 표를 독식한다.
TEST(JournalReader, OneSessionIsOneVoteRegardlessOfRepeats) {
    std::vector<std::string> spammy;
    for (int i = 0; i < 15; ++i) spammy.push_back("Spam");
    spammy.push_back("Rare");

    std::vector<maro::JournalSession> sessions;
    sessions.push_back(makeSession(false, spammy));

    const maro::CrashAdjacency adj = maro::countCrashAdjacentTags(sessions);

    EXPECT_EQ(adj.abnormalSessionCount, 1u);
    EXPECT_EQ(adj.appearancesByTag.at("Spam"), 1u)
        << "fifteen hits in one session is still one session";
    EXPECT_EQ(adj.appearancesByTag.at("Rare"), 1u);
}

// 마지막 구간 밖의 태그는 세지 않는다. 구간은 마지막 레코드 20개다.
TEST(JournalReader, OnlyTheTailOfTheSessionCounts) {
    std::vector<std::string> tags;
    tags.push_back("TooEarly");
    for (std::size_t i = 0; i < maro::kJournalTailRecordsForSignal; ++i) {
        tags.push_back("InTail");
    }

    std::vector<maro::JournalSession> sessions;
    sessions.push_back(makeSession(false, tags));

    const maro::CrashAdjacency adj = maro::countCrashAdjacentTags(sessions);

    EXPECT_EQ(adj.appearancesByTag.count("TooEarly"), 0u)
        << "it sits one record before the tail window";
    EXPECT_EQ(adj.appearancesByTag.at("InTail"), 1u);
}

// 세션의 전체 레코드가 구간보다 적으면 전부를 본다.
TEST(JournalReader, AShortSessionIsCountedWhole) {
    std::vector<maro::JournalSession> sessions;
    sessions.push_back(makeSession(false, {"A", "B"}));

    const maro::CrashAdjacency adj = maro::countCrashAdjacentTags(sessions);

    EXPECT_EQ(adj.appearancesByTag.at("A"), 1u);
    EXPECT_EQ(adj.appearancesByTag.at("B"), 1u);
}

// 여러 비정상 세션에 걸쳐 누적된다 -- 이것이 신호의 실체다.
TEST(JournalReader, AccumulatesAcrossAbnormalSessions) {
    std::vector<maro::JournalSession> sessions;
    sessions.push_back(makeSession(false, {"Recurring", "OnceOnly"}));
    sessions.push_back(makeSession(true, {"Recurring"}));   // 정상 -- 세지 않는다
    sessions.push_back(makeSession(false, {"Recurring"}));

    const maro::CrashAdjacency adj = maro::countCrashAdjacentTags(sessions);

    EXPECT_EQ(adj.abnormalSessionCount, 2u);
    EXPECT_EQ(adj.appearancesByTag.at("Recurring"), 2u);
    EXPECT_EQ(adj.appearancesByTag.at("OnceOnly"), 1u);
}

// 태그가 없는 레코드(에러가 아닌 것)는 신호의 대상이 아니다 -- 신호는
// 사이트 태그로 지목되는 실패에 붙는다.
TEST(JournalReader, RecordsWithoutASiteTagAreIgnored) {
    std::vector<maro::JournalSession> sessions;
    sessions.push_back(makeSession(false, {"", "A"}));

    const maro::CrashAdjacency adj = maro::countCrashAdjacentTags(sessions);

    EXPECT_EQ(adj.appearancesByTag.count(""), 0u);
    EXPECT_EQ(adj.appearancesByTag.at("A"), 1u);
}
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
ctest --test-dir out/build --output-on-failure -R JournalReader
```

기대: 컴파일 실패 — `maro::CrashAdjacency`가 없다.

- [ ] **Step 3: `JournalReader.h`에 집계 타입과 선언 추가**

`JournalReader.h`의 `#include` 목록에 `#include <unordered_map>`을 추가하고, `parseJournal` 선언 아래에 추가:

```cpp
// 비정상 종료 직전에 어떤 사이트 태그가 반복해서 나타났는지에 대한 **관측**.
//
// 인과가 아니다. 크래시 직전에 있었다는 것이 크래시를 일으켰다는 뜻은
// 아니며, 무관한 진단이 우연히 자주 마지막에 있을 수도 있다. 그래서 이
// 구조체는 "몇 번 중 몇 번"이라는 사실만 담고 원인을 단정하지 않는다.
//
// 이것은 ghost가 아니다. ghost의 실제 일 -- 셧다운 신호를 받아 그 시점에
// 파편을 저장하고 다음 기동에 조립하는 것 -- 은 Layer C다. 여기서 하는
// 것은 사후에 저널을 세는 것뿐이고, 프로세스가 죽는 순간에 대해서는
// 아무것도 모른다.
struct CrashAdjacency {
    // 보관 중인 저널에서 비정상으로 끝난 세션의 수. 신호의 분모다.
    std::size_t abnormalSessionCount = 0;
    // 사이트 태그 -> 그 태그가 마지막 구간에 있었던 비정상 세션의 수.
    // 한 세션은 한 표다 -- 한 세션에서 몇 번 나왔는지는 세지 않는다.
    // 안 그러면 폭주한 태그 하나가 모든 세션의 표를 독식한다.
    std::unordered_map<std::string, std::size_t> appearancesByTag;
};

CrashAdjacency countCrashAdjacentTags(const std::vector<JournalSession>& sessions);
```

- [ ] **Step 4: `JournalReader.cpp`에 구현 추가**

`JournalReader.cpp` 상단 include에 `#include <algorithm>`과 `#include <unordered_set>`을 추가하고, `}  // namespace maro` 앞에 추가:

```cpp
CrashAdjacency countCrashAdjacentTags(const std::vector<JournalSession>& sessions) {
    CrashAdjacency adjacency;

    for (const JournalSession& session : sessions) {
        if (session.endedCleanly) continue;
        ++adjacency.abnormalSessionCount;

        // 마지막 구간만 본다. 전체가 구간보다 짧으면 전부를 본다.
        const std::size_t total = session.records.size();
        const std::size_t start =
            total > kJournalTailRecordsForSignal ? total - kJournalTailRecordsForSignal : 0;

        // 한 세션은 한 표 -- 세션 안에서 중복을 먼저 없앤다.
        std::unordered_set<std::string> seenInThisSession;
        for (std::size_t i = start; i < total; ++i) {
            const std::string& tag = session.records[i].siteTag;
            if (tag.empty()) continue;  // 신호는 사이트 태그로 지목되는 실패에만 붙는다
            seenInThisSession.insert(tag);
        }
        for (const std::string& tag : seenInThisSession) {
            ++adjacency.appearancesByTag[tag];
        }
    }
    return adjacency;
}
```

- [ ] **Step 5: 빌드하고 테스트가 통과하는지 확인**

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure
```

기대: 전부 통과.

- [ ] **Step 6: "한 세션은 한 표"가 진짜인지 확인**

`countCrashAdjacentTags`에서 `seenInThisSession` 집합을 쓰지 않고 루프 안에서 바로 `++adjacency.appearancesByTag[tag];`를 하도록 바꾼다.

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure -R JournalReader
```

기대: `OneSessionIsOneVoteRegardlessOfRepeats`가 `fifteen hits in one session is still one session`으로 **실패**한다(값 15). 확인했으면 되돌린다.

- [ ] **Step 7: 마지막 구간 경계가 진짜인지 확인**

`const std::size_t start = ...` 줄을 `const std::size_t start = 0;`로 바꾼다(세션 전체를 보게 만든다).

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure -R JournalReader
```

기대: `OnlyTheTailOfTheSessionCounts`가 `it sits one record before the tail window`로 **실패**한다. 확인했으면 되돌린다.

- [ ] **Step 8: 커밋**

```bash
git add src/maro_diag tests/diag/test_journal_reader.cpp
git commit -m "feat: count which diagnostics keep showing up just before a crash"
```

---

### Task 5: 플러그인 배선 — 저널에 흘리고, 세션을 감싸고, 복원한다

**Files:**
- Modify: `src/maro_plugin/MaroDiag.h`, `src/maro_plugin/MaroDiag.cpp`
- Modify: `src/maro_plugin/MaroPluginMain.cpp`
- Create: `tests/maya/test_journal.py`
- Modify: `tests/CMakeLists.txt`

**Interfaces:**
- Consumes: `maro::JournalWriter`, `maro::JournalWriter::rotate`, `maro::parseJournal`, `maro::countCrashAdjacentTags` (Task 1~4)
- Produces: `maro::BoadMaro::openJournal()`, `maro::BoadMaro::closeJournal()`, `maro::BoadMaro::journalPath()`, `maro::BoadMaro::crashAdjacency()` — 반환 `const CrashAdjacency&`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/maya/test_journal.py`:

```python
"""저널이 크래시를 건너 살아남는지, 그리고 다음 실행이 비정상 종료를
알아채는지 두 프로세스로 확인한다.

왜 두 프로세스인가: 저널의 존재 이유가 "프로세스가 죽어도 남는 것"이므로,
한 프로세스 안에서는 인메모리 상태와 구분되지 않는다. 세션 1은 정상 종료
줄을 쓰기 **전에** 스스로를 끊는다 -- 감시자 입장에서 진짜 크래시와
구분되지 않는 신호이며, 컴퓨터를 죽이지 않고 만들 수 있다.

좀비 mayapy.exe 방지: subprocess.run(timeout=...)은 타임아웃 시 자식을
kill()하고 wait()까지 마친 뒤에야 예외를 던진다 -- 각 세션 호출을 그 경계
안에 두는 것만으로 무한 대기도, 죽은 자식이 남는 것도 막힌다."""
import os
import subprocess
import sys

MAYAPY = sys.executable
THIS_FILE = os.path.abspath(__file__)
SESSION_TIMEOUT_SECONDS = 90


def run_session(label, env):
    try:
        completed = subprocess.run(
            [MAYAPY, THIS_FILE, f"--session={label}"],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=SESSION_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(
            f"session {label} did not finish within {SESSION_TIMEOUT_SECONDS}s "
            f"and was killed -- output so far:\n{exc.output or ''}"
        )
    return completed.returncode, completed.stdout


def journal_path(bookDir):
    return os.path.join(bookDir, "maro_journal.jsonl")


def orchestrate():
    env = os.environ.copy()
    bookDir = env["MARO_DIAG_BOOK_DIR"]

    rc1, out1 = run_session("crash", env)
    print("---- session 1 (dies without closing) ----")
    print(out1)
    assert rc1 != 0, "session 1 is supposed to die abnormally, not exit cleanly"

    path = journal_path(bookDir)
    assert os.path.exists(path), f"expected a journal at {path}"
    with open(path, encoding="utf-8") as f:
        text = f.read()
    assert "MaroBindAxisCommand.TargetNotTransform" in text, (
        "the diagnostic raised before the crash must be on disk"
    )
    assert '"event":"close"' not in text, (
        "session 1 died before writing a close line -- that absence IS the crash signal"
    )
    print("journal survived the crash OK")

    rc2, out2 = run_session("detect", env)
    print("---- session 2 (detects the abnormal end, then exits cleanly) ----")
    print(out2)
    assert rc2 == 0, f"session 2 failed with exit code {rc2}"

    # 세션 3이 있어야 종료 줄이 실제로 무슨 일을 하는지 확인된다. 세션 2는
    # 정상 종료했으므로 비정상 집계에 **더해지면 안 된다** -- 여전히 1이어야
    # 한다. 이 세션이 없으면 종료 줄을 아예 안 쓰는 구현도 통과한다(세션 2는
    # 자기 open 줄을 쓰기 전에 저널을 읽으므로 자기 자신을 못 본다).
    rc3, out3 = run_session("recount", env)
    print("---- session 3 (a clean exit must not count as abnormal) ----")
    print(out3)
    assert rc3 == 0, f"session 3 failed with exit code {rc3}"

    print("journal crash detection OK")


def run_as_session(label):
    import maya.standalone

    maya.standalone.initialize(name="python")

    import maya.cmds as cmds  # noqa: E402

    plugin = os.environ["MARO_PLUGIN_PATH"]
    cmds.loadPlugin(plugin)
    cmds.file(new=True, force=True)

    if label == "crash":
        light = cmds.createNode("pointLight", name="journalLight")
        axis = cmds.createNode("maroAxis", name="journalAxis")
        try:
            cmds.maroBindAxis(axis, light)
            raise AssertionError("expected rejection")
        except RuntimeError:
            pass
        print("session 1 raised its diagnostic")
        sys.stdout.flush()
        # 정상 종료 경로를 타지 않고 프로세스를 끊는다 -- uninitializePlugin이
        # 돌지 않으므로 종료 줄이 없다. os._exit는 atexit 훅도 건너뛴다.
        os._exit(3)

    elif label == "detect":
        count = cmds.maroJournalAbnormalSessions()
        assert count == 1, (
            f"the previous session died without closing, so exactly one abnormal "
            f"session should be on record, got {count}"
        )
        print("abnormal session detected OK")

        tags = cmds.maroJournalCrashAdjacentTags()
        assert "MaroBindAxisCommand.TargetNotTransform" in tags, (
            f"the tag raised just before the crash must be counted, got {tags}"
        )
        print("crash-adjacent tag counted OK")

    elif label == "recount":
        # 세션 2는 정상 종료했다. 종료 줄이 실제로 쓰였다면 비정상 집계는
        # 늘지 않는다 -- 여전히 1이어야 한다.
        count = cmds.maroJournalAbnormalSessions()
        assert count == 1, (
            f"only the first session died without closing; the second exited "
            f"cleanly and must not be counted as abnormal, got {count}"
        )
        print("clean exit not counted as abnormal OK")
    else:
        raise ValueError(f"unknown session label {label!r}")

    cmds.file(new=True, force=True)
    cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
    maya.standalone.uninitialize()
    print(f"session {label} teardown OK")


if __name__ == "__main__":
    sessionArg = next((a for a in sys.argv[1:] if a.startswith("--session=")), None)
    if sessionArg is None:
        orchestrate()
        sys.exit(0)
    run_as_session(sessionArg.split("=", 1)[1])
    sys.exit(0)
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
MARO_DIAG_BOOK_DIR="$(mktemp -d)" MARO_PLUGIN_PATH="$(cygpath -w "$(find out/build -name maro.mll | head -1)")" "/c/Program Files/Autodesk/Maya2026/bin/mayapy.exe" tests/maya/test_journal.py
```

기대: 세션 1에서 `AttributeError: module 'maya.cmds' has no attribute 'maroJournalAbnormalSessions'` — 이 커맨드들이 아직 없다. (Maya는 미등록 커맨드를 `cmds`에 아예 노출하지 않으므로 `RuntimeError`가 아니라 `AttributeError`다.)

- [ ] **Step 3: `MaroDiag.h`에 저널 배선 선언 추가**

`MaroDiag.h` 상단 include에 `#include "maro_diag/JournalReader.h"`를 추가하고, `BoadMaro`의 `resetForTest` 선언 위에 추가:

```cpp
    // 저널을 연다. 플러그인 로드 시 한 번 부르며, 그 전에 오래된 세션을
    // 회전으로 정리하고 지난 세션들의 크래시 인접 집계를 읽어 둔다.
    // 열지 못해도 던지지 않는다 -- 보존이 안 될 뿐 진단은 그대로 돈다.
    static void openJournal();
    // 정상 종료 줄을 쓰고 닫는다. uninitializePlugin에서만 부른다.
    // 이 줄이 없이 끝난 세션이 곧 비정상 종료다.
    static void closeJournal();

    // 로드 시점에 읽어 둔 지난 세션들의 관측. 인과가 아니라 상관이다.
    static const CrashAdjacency& crashAdjacency();
```

- [ ] **Step 4: `MaroDiag.cpp`에 저널 배선 구현**

`MaroDiag.cpp` 상단 include에 추가:

```cpp
#include <fstream>
#include <memory>
#include <sstream>

#include "maro_diag/JournalReader.h"
#include "maro_diag/JournalWriter.h"
```

익명 네임스페이스(`g_nextSequence` 근처)에 추가:

```cpp
// 저널은 book과 같은 디렉터리에 둔다 -- bookPaths()의 해소 결과를
// 재사용하므로 테스트의 MARO_DIAG_BOOK_DIR 재정의도 그대로 따라온다.
std::filesystem::path journalPath() {
    return bookPaths().canonical.parent_path() / "maro_journal.jsonl";
}

// 저널 쓰기를 지키는 전용 뮤텍스. 이 뮤텍스는 **말단**이다 -- 안에서
// boad도 book도 부르지 않으므로 잠금 순서 문제가 생기지 않는다.
std::mutex& journalMutex() {
    static std::mutex m;
    return m;
}

std::unique_ptr<JournalWriter>& journalWriter() {
    static std::unique_ptr<JournalWriter> w;
    return w;
}

CrashAdjacency& crashAdjacencyStorage() {
    static CrashAdjacency adjacency;
    return adjacency;
}

// 레코드 하나를 저널에 흘린다. 실패해도 조용하다.
void journalRecord(const DiagRecord& rec) {
    std::lock_guard<std::mutex> lock(journalMutex());
    if (!journalWriter()) return;
    journalWriter()->writeRecord(rec.sequence, rec.timestampMs, rec.severity,
                                  rec.errorHash.empty() ? std::string() : rec.errorHash,
                                  rec.message);
}
```

`}  // namespace maro` 앞에 추가:

```cpp
void BoadMaro::openJournal() {
    try {
        const std::filesystem::path path = journalPath();

        // 이번 세션의 open 줄을 쓰기 **전에** 회전한다 -- 그래야 보관
        // 한도가 "지난 N 세션"을 뜻하고 이번 세션이 그 한도를 잡아먹지 않는다.
        JournalWriter::rotate(path);

        // 회전 뒤의 저널을 읽어 지난 세션들의 관측을 만들어 둔다. 이후로는
        // 이 값이 바뀌지 않는다 -- 이번 세션은 아직 끝나지 않았으므로
        // 비정상인지 정상인지 판정할 수 없다.
        {
            std::ifstream in(path, std::ios::binary);
            std::ostringstream ss;
            ss << in.rdbuf();
            crashAdjacencyStorage() = countCrashAdjacentTags(parseJournal(ss.str()));
        }

        std::lock_guard<std::mutex> lock(journalMutex());
        journalWriter() = std::make_unique<JournalWriter>(path);
        journalWriter()->writeSessionOpen(nowMs());
    } catch (...) {
        // 저널을 못 열어도 진단은 그대로 돈다.
    }
}

void BoadMaro::closeJournal() {
    try {
        std::lock_guard<std::mutex> lock(journalMutex());
        if (!journalWriter()) return;
        journalWriter()->writeSessionClose(nowMs());
        journalWriter().reset();
    } catch (...) {
    }
}

const CrashAdjacency& BoadMaro::crashAdjacency() { return crashAdjacencyStorage(); }
```

`info`/`warn`/`devInfo`/`error` 각각에서 `assignSequenceAndPush(std::move(rec), stream());` **다음 줄**에 저널 기록을 넣는다. 순번이 배정된 뒤여야 하므로 push 이후이고, 레코드 뮤텍스를 쥔 채로 저널 뮤텍스를 잡지 않도록 락 스코프 **밖**이어야 한다. `info`는 이렇게 된다:

```cpp
void BoadMaro::info(const MString& message) {
    DiagRecord rec;
    stampTimestamp(rec);
    rec.severity = DiagSeverity::Info;
    rec.message = message.asChar();
    if (isMainThread()) {
        MGlobal::displayInfo(MString("[Maro-Info] ") + message);
    }
    DiagRecord journalCopy;
    {
        std::lock_guard<std::mutex> lock(mutex());
        assignSequenceAndPush(std::move(rec), stream());
        journalCopy = stream().back();
    }
    journalRecord(journalCopy);
}
```

`warn`, `devInfo`, `error`도 같은 모양으로 바꾼다 — 락 안에서 방금 넣은 레코드를 복사해 두고, 락을 놓은 뒤 저널에 흘린다.

- [ ] **Step 5: 테스트 전용 조회 커맨드 두 개 추가**

`src/maro_plugin/MaroDiagCommands.h`의 `}  // namespace maro` 앞에 추가:

```cpp
// 테스트 전용. 로드 시점에 읽어 둔 저널에서 비정상 종료로 끝난 세션의 수.
class MaroJournalAbnormalSessionsCommand : public MPxCommand {
public:
    static void* creator();
    MStatus doIt(const MArgList& args) override;
};

// 테스트 전용. 크래시 인접으로 집계된 사이트 태그들을 문자열 배열로.
class MaroJournalCrashAdjacentTagsCommand : public MPxCommand {
public:
    static void* creator();
    MStatus doIt(const MArgList& args) override;
};
```

`src/maro_plugin/MaroDiagCommands.cpp`의 `}  // namespace maro` 앞에 추가:

```cpp
void* MaroJournalAbnormalSessionsCommand::creator() {
    return new MaroJournalAbnormalSessionsCommand();
}

MStatus MaroJournalAbnormalSessionsCommand::doIt(const MArgList& /*args*/) {
    try {
        setResult(static_cast<int>(BoadMaro::crashAdjacency().abnormalSessionCount));
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroJournalAbnormalSessions failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroJournalAbnormalSessions failed with unknown error.");
        return MS::kFailure;
    }
}

void* MaroJournalCrashAdjacentTagsCommand::creator() {
    return new MaroJournalCrashAdjacentTagsCommand();
}

MStatus MaroJournalCrashAdjacentTagsCommand::doIt(const MArgList& /*args*/) {
    try {
        MStringArray result;
        for (const auto& entry : BoadMaro::crashAdjacency().appearancesByTag) {
            result.append(MString(entry.first.c_str()));
        }
        setResult(result);
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroJournalCrashAdjacentTags failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroJournalCrashAdjacentTags failed with unknown error.");
        return MS::kFailure;
    }
}
```

- [ ] **Step 6: 플러그인 진입점에 세션 표식 배선**

`src/maro_plugin/MaroPluginMain.cpp`의 `maro::markMainThread();` 바로 아래에 추가:

```cpp
    // 저널을 연다. markMainThread()가 book 경로를 이미 확정했으므로
    // 저널 경로도 여기서 안전하게 해소된다.
    maro::BoadMaro::openJournal();
```

`maroDiagEmitMarked` 등록 뒤에 두 커맨드 등록을 추가한다:

```cpp
    status = plugin.registerCommand("maroJournalAbnormalSessions",
                                    maro::MaroJournalAbnormalSessionsCommand::creator);
    if (!status) {
        status.perror("Maro: failed to register maroJournalAbnormalSessions");
        return status;
    }

    status = plugin.registerCommand("maroJournalCrashAdjacentTags",
                                    maro::MaroJournalCrashAdjacentTagsCommand::creator);
    if (!status) {
        status.perror("Maro: failed to register maroJournalCrashAdjacentTags");
        return status;
    }
```

`uninitializePlugin`에서는 두 커맨드를 역순으로 해제하고, **모든 해제가 끝난 뒤 맨 마지막에** 저널을 닫는다:

```cpp
    plugin.deregisterCommand("maroJournalCrashAdjacentTags");
    plugin.deregisterCommand("maroJournalAbnormalSessions");
```

그리고 `uninitializePlugin`의 `return status;` 직전에:

```cpp
    // 맨 마지막에 닫는다. 이 줄이 저널에 남아야 다음 실행이 "이 세션은
    // 정상적으로 끝났다"를 안다 -- 없으면 비정상 종료로 판정된다.
    maro::BoadMaro::closeJournal();
```

- [ ] **Step 7: `tests/CMakeLists.txt`에 등록**

플러그인 전용 `foreach` 목록에 `journal`을 추가한다:

```cmake
    foreach(maya_test load axis_node binding capability_stack delete_rules
                      robustness diag_boad diag_onfix diag_book
                      diag_book_cross_session diag_remedy
                      diag_degraded diag_degraded_remedy diag_thread
                      panel_commands journal)
```

- [ ] **Step 8: 빌드하고 테스트가 통과하는지 확인**

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure
```

기대: 전부 통과.

- [ ] **Step 9: 종료 줄의 부재가 진짜 신호인지 확인**

`MaroPluginMain.cpp`의 `maro::BoadMaro::closeJournal();`를 주석 처리한다(정상 종료도 종료 줄을 안 남기게 만든다).

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure -R maya_journal
```

기대: **세션 3**의 `the second exited cleanly and must not be counted as abnormal` 단언이 2를 받아 **실패**한다 — 세션 2가 종료 줄 없이 끝나 비정상으로 세어지기 때문이다.

세션 2의 단언은 이 파손으로 **실패하지 않는다**. 세션 2는 자기 open 줄을 쓰기 전에 저널을 읽으므로 자기 자신을 볼 수 없고, 그 시점에는 여전히 비정상 세션이 하나(세션 1)뿐이다. 세션 3이 있는 이유가 정확히 이것이다 — 확인 후 되돌린다.

- [ ] **Step 10: 저널이 진짜로 디스크를 거치는지 확인**

`journalRecord`의 `journalWriter()->writeRecord(...)` 호출을 주석 처리한다.

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure -R maya_journal
```

기대: `the diagnostic raised before the crash must be on disk`로 **실패**한다. 확인했으면 되돌린다.

- [ ] **Step 11: 커밋**

```bash
git add src/maro_plugin tests/maya/test_journal.py tests/CMakeLists.txt
git commit -m "feat: frame each session in the journal so a missing close means a crash"
```

---

### Task 6: 신호를 패널 상세에 붙인다 (필드 13 → 14)

**Files:**
- Modify: `src/maro_diag/include/maro_diag/PanelView.h`, `src/maro_diag/include/maro_diag/PanelPresenter.h`, `src/maro_diag/src/PanelPresenter.cpp`
- Modify: `tests/diag/test_panel_presenter.cpp`
- Modify: `src/maro_plugin/MaroPanelCommands.h`, `src/maro_plugin/MaroPanelCommands.cpp`
- Modify: `python/maroDiagPanel.py`
- Modify: `tests/maya/test_panel_commands.py`

**Interfaces:**
- Consumes: `maro::CrashAdjacency` (Task 4), `maro::BoadMaro::crashAdjacency()` (Task 5), `maro::PanelDetail` (B-1a)
- Produces: `maro::PanelDetail::crashAdjacencyNote` (`std::string`), `buildPanelDetail`의 넷째 인자 `const CrashAdjacency&`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/diag/test_panel_presenter.cpp` 끝에 추가:

```cpp
#include "maro_diag/JournalReader.h"

// 문턱 아래에서는 아무 말도 하지 않는다. 1회를 근거로 뭔가 말하는 것은
// 정보가 아니라 소음이다.
TEST(PanelPresenter, SaysNothingBelowTheCrashAdjacencyThreshold) {
    maro::DiagRecord rec = makeRecord(1, 1000, maro::DiagSeverity::Error,
                                       "Site.A", "failed");

    maro::CrashAdjacency onlyOneAbnormal;
    onlyOneAbnormal.abnormalSessionCount = 1;
    onlyOneAbnormal.appearancesByTag["Site.A"] = 1;
    EXPECT_EQ(maro::buildPanelDetail(rec, nullptr, false, onlyOneAbnormal)
                  .crashAdjacencyNote, "")
        << "one abnormal session is not a pattern";

    maro::CrashAdjacency singleAppearance;
    singleAppearance.abnormalSessionCount = 4;
    singleAppearance.appearancesByTag["Site.A"] = 1;
    EXPECT_EQ(maro::buildPanelDetail(rec, nullptr, false, singleAppearance)
                  .crashAdjacencyNote, "")
        << "appearing once out of four is not a pattern either";
}

// 문턱을 넘으면 관측된 사실을 정확한 숫자로 말한다.
TEST(PanelPresenter, ReportsTheObservedCountsAboveTheThreshold) {
    maro::DiagRecord rec = makeRecord(1, 1000, maro::DiagSeverity::Error,
                                       "Site.A", "failed");
    maro::CrashAdjacency adjacency;
    adjacency.abnormalSessionCount = 4;
    adjacency.appearancesByTag["Site.A"] = 3;

    const std::string note =
        maro::buildPanelDetail(rec, nullptr, false, adjacency).crashAdjacencyNote;

    EXPECT_NE(note.find("4"), std::string::npos) << "the denominator must appear";
    EXPECT_NE(note.find("3"), std::string::npos) << "the numerator must appear";
}

// 다른 태그의 집계를 이 레코드에 붙이지 않는다.
TEST(PanelPresenter, DoesNotBorrowAnotherTagsCount) {
    maro::DiagRecord rec = makeRecord(1, 1000, maro::DiagSeverity::Error,
                                       "Site.Quiet", "failed");
    maro::CrashAdjacency adjacency;
    adjacency.abnormalSessionCount = 4;
    adjacency.appearancesByTag["Site.Noisy"] = 3;

    EXPECT_EQ(maro::buildPanelDetail(rec, nullptr, false, adjacency).crashAdjacencyNote, "");
}

// 해시가 없는 레코드(에러가 아닌 것)에는 신호가 붙지 않는다.
TEST(PanelPresenter, NoNoteForARecordWithoutASiteTag) {
    maro::DiagRecord rec = makeRecord(1, 1000, maro::DiagSeverity::Warn, "", "just a warning");
    maro::CrashAdjacency adjacency;
    adjacency.abnormalSessionCount = 4;
    adjacency.appearancesByTag[""] = 3;

    EXPECT_EQ(maro::buildPanelDetail(rec, nullptr, false, adjacency).crashAdjacencyNote, "");
}
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
ctest --test-dir out/build --output-on-failure -R PanelPresenter
```

기대: 컴파일 실패 — `buildPanelDetail`이 인자 넷을 받지 않는다.

- [ ] **Step 3: `PanelView.h`에 필드 추가**

`struct PanelDetail`의 `applyUnavailableReason` 아래에 추가:

```cpp
    // 이 자리가 지난 비정상 종료 직전에 반복해서 나타났다면 그 사실을
    // 담는다. 비어 있으면 말할 것이 없다는 뜻이다.
    //
    // 인과가 아니라 상관이다. 크래시 직전에 있었다는 것이 크래시를
    // 일으켰다는 뜻은 아니므로 문구는 관측된 사실만 말한다.
    std::string crashAdjacencyNote;
```

- [ ] **Step 4: `PanelPresenter.h`의 선언 갱신**

`#include "maro_diag/JournalReader.h"`를 include 목록에 추가하고, `buildPanelDetail` 선언을 아래로 교체:

```cpp
// crashAdjacency는 플러그인 로드 시점에 저널에서 읽어 둔 관측이며, 이
// 세션 동안 바뀌지 않는다 -- 이번 세션은 아직 끝나지 않아 정상인지
// 비정상인지 판정할 수 없기 때문이다.
PanelDetail buildPanelDetail(const DiagRecord& record,
                              const BookEntry* bookEntry,
                              bool targetNodeExists,
                              const CrashAdjacency& crashAdjacency);
```

- [ ] **Step 5: `PanelPresenter.cpp`의 구현 갱신**

`buildPanelDetail`의 시그니처를 위와 맞추고, `detail.applyUnavailableReason = "NoActionRecorded";` 아래에 추가:

```cpp
    // 잡음 문턱: 비정상 종료가 2회 미만이거나 이 태그가 1회만 걸렸으면
    // 아무것도 말하지 않는다.
    detail.crashAdjacencyNote.clear();
    if (!record.errorHash.empty() && crashAdjacency.abnormalSessionCount >= 2) {
        const auto found = crashAdjacency.appearancesByTag.find(record.errorHash);
        if (found != crashAdjacency.appearancesByTag.end() && found->second >= 2) {
            detail.crashAdjacencyNote =
                "지난 비정상 종료 " + std::to_string(crashAdjacency.abnormalSessionCount) +
                "회 중 " + std::to_string(found->second) +
                "회에서 이 진단이 마지막 순간에 있었습니다.";
        }
    }
```

`PanelPresenter.cpp` 상단 include에 `#include <string>`이 없으면 추가한다.

- [ ] **Step 6: 커맨드의 필드를 13에서 14로 늘린다**

`src/maro_plugin/MaroPanelCommands.h`의 `MaroDiagPanelDetailCommand` 주석에서 필드 목록 끝에 `crashAdjacencyNote`를 추가하고 "13필드"를 "14필드"로 고친다.

`src/maro_plugin/MaroPanelCommands.cpp`의 `MaroDiagPanelDetailCommand::doIt`에서 `buildPanelDetail` 호출에 넷째 인자를 넘기고:

```cpp
        const PanelDetail detail =
            buildPanelDetail(*chosen, haveEntry ? &entry : nullptr, false,
                              BoadMaro::crashAdjacency());
```

`result.append(MString(detail.applyUnavailableReason.c_str()));` 아래에 추가:

```cpp
        result.append(MString(detail.crashAdjacencyNote.c_str()));
```

- [ ] **Step 7: Python과 Maya 테스트의 필드 수를 함께 올린다**

`python/maroDiagPanel.py`의 `DETAIL_FIELDS = 13`을 `DETAIL_FIELDS = 14`로 바꾸고, `_onSelect`의 `lines` 조립에서 해법 블록 아래에 추가:

```python
    if detail[13]:
        lines += ["", detail[13]]
```

`tests/maya/test_panel_commands.py`의 `DETAIL_FIELDS = 13`을 `DETAIL_FIELDS = 14`로 바꾸고, 상세 계약 단언 근처에 추가:

```python
# 이 세션은 저널에 비정상 종료 기록이 없으므로 신호 자리는 비어 있어야 한다.
# 문턱 아래에서 뭔가 말하는 것은 정보가 아니라 소음이다.
assert detail[13] == "", (
    f"no abnormal sessions on record, so the crash-adjacency note must be empty, "
    f"got {detail[13]!r}"
)
print("crash adjacency note empty OK")
```

- [ ] **Step 8: 빌드하고 테스트가 통과하는지 확인**

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure
```

기대: 전부 통과.

- [ ] **Step 9: 문턱이 진짜로 지켜지는지 확인**

`PanelPresenter.cpp`의 `crashAdjacency.abnormalSessionCount >= 2`를 `>= 1`로, `found->second >= 2`를 `>= 1`로 바꾼다.

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure -R PanelPresenter
```

기대: `SaysNothingBelowTheCrashAdjacencyThreshold`가 두 단언 모두에서 **실패**한다. 확인했으면 되돌린다.

- [ ] **Step 10: 세 곳의 필드 수가 실제로 묶여 있는지 확인**

`python/maroDiagPanel.py`의 `DETAIL_FIELDS`만 `13`으로 되돌린다(C++와 테스트는 14인 채로 둔다).

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure -R maya_panel_commands
```

기대: 파이썬 모듈의 상수와 테스트의 상수를 비교하는 기존 단언이 **실패**한다. 확인했으면 되돌린다.

- [ ] **Step 11: 커밋**

```bash
git add src/maro_diag src/maro_plugin python/maroDiagPanel.py tests
git commit -m "feat: tell the user when this diagnostic kept showing up before crashes"
```

---

## 자체 검토 결과

**스펙 커버리지 (B-1b-1 범위)**

| 스펙 항목 | 담당 |
|---|---|
| §3.6 형식(append-only JSONL, 로드 시 열어 언로드까지) | Task 1 |
| §3.6 위치(`bookPaths()` 재사용 — 테스트 재정의가 따라옴) | Task 5 (`journalPath()`) |
| §3.6 쓰는 시점(발생 즉시, 전용 말단 뮤텍스) | Task 5 (`journalMutex()`, 레코드 락 밖) |
| §3.6 `fsync` 안 함 | Task 1 (`writeLine`의 flush만) |
| §3.6 세션 표식과 "종료 줄 없음 = 비정상" | Task 1(쓰기), Task 3(판정), Task 5(배선) |
| §3.6 태그별 시간 창 억제 (5줄/1초) | Task 2 |
| §3.6 10 세션 회전 | Task 2 |
| §3.6 다음 로드 때 복원 | Task 5 (`openJournal`이 회전 후 집계를 읽는다) |
| §3.7 마지막 20 레코드, 한 세션 한 표 | Task 4 |
| §3.7 문턱(비정상 2회 미만 또는 태그 1회면 침묵) | Task 6 |
| §3.7 인과가 아니라 상관인 문구 | Task 6 |
| §3.7 계산은 프레젠터가(순수, gtest) | Task 4(집계), Task 6(문구) |

**§3.6의 "저널 꼬리를 패널에 복원한다"에 대한 결정**: 스펙은 마지막 세션이 비정상이면 그 꼬리를 **"지난 세션이 비정상 종료했습니다" 항목으로** 패널에 되살리라고 한다. 이 플랜은 그중 **집계(§3.7의 신호)까지만** 한다 — 지난 세션의 레코드들을 이번 세션의 행 목록에 섞어 넣는 것은 `boad`의 인메모리 스트림이 곧 진실이라는 B-1a의 규율(`§3.3`)을 건드리므로, 스트림에 넣을지 별도 영역으로 보여줄지가 먼저 정해져야 한다. B-1b-2 또는 그 뒤에서 다룬다. **이것은 스펙 미커버 항목이며 의도적으로 남긴다.**

**플레이스홀더 스캔**: "TBD", "적절한 에러 처리", "테스트를 작성한다"류 없음. 모든 코드 단계에 실제 코드가 있고 모든 명령에 기대 출력이 있다. 상수 넷(`kJournalSessionsKept`=10, `kJournalMaxLinesPerTagPerWindow`=5, `kJournalSuppressionWindowMs`=1000, `kJournalTailRecordsForSignal`=20)은 전부 `Journal.h` 한곳에 값으로 있다.

**타입 일관성**: `JournalWriter`/`JournalReader`/`JournalRecord`/`JournalSession`/`CrashAdjacency`는 정의한 태스크와 쓰는 태스크에서 같은 이름이다. `buildPanelDetail`의 인자 수가 Task 6에서 3 → 4로 바뀌며, 그 호출부는 `MaroPanelCommands.cpp` 한 곳뿐이라 같은 태스크에서 함께 고친다. 필드 수 상수(상세 14)는 C++ 헤더 주석·`maroDiagPanel.py`·`test_panel_commands.py` 세 곳에 나타나고 Task 6이 한 커밋에서 셋을 함께 바꾼다.
