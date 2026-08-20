# Maro Layer C-1 — 감시자 프로세스 골격 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 플러그인이 자기 감시자 프로세스(`maro_sentinel.exe`)를 띄우고, 명명된 파이프로 붙고, 정상 종료 신호의 유무로 크래시를 판정한다. 그 신호를 가지고 하는 일(분석/셧다운 대응/시스템 로그)은 없다 — 인프라가 살아남는지만 증명한다.

**Architecture:** Maya 프로세스 1개 : 감시자 1개, 전부 Maya PID로 키를 잡은 이름(파이프/뮤텍스/이벤트/기록 파일). 새 공유 라이브러리 `maro_ipc`(Windows 전용, Maya는 모름)가 파이프·프레이밍·명명된 뮤텍스·job 탈출·기록 파일을 담고, `maro_plugin`과 새 실행 파일 `maro_sentinel`이 그것을 함께 링크한다.

**Tech Stack:** C++17, Win32(named pipe, job object, WMI/COM), nlohmann/json, GoogleTest, `mayapy`, CMake + Visual Studio 제너레이터(멀티 컨피그)

설계: `docs/superpowers/specs/2026-08-19-maro-layer-c1-sentinel-skeleton-design.md` (전체), 선행 `docs/superpowers/specs/2026-08-14-maro-troubleshooting-ecosystem-design.md` §3, §5

## Global Constraints

- C++17, 네임스페이스 `maro`, 접두사 `maro`, UTF-8 소스
- **`maro_ipc`는 Maya 헤더로부터 자유롭게 유지한다** — `maro_diag`와 같은 자리. `maro_plugin`과 `maro_sentinel` 양쪽이 링크한다
- **모든 명명 자원은 Maya PID로 키를 잡는다** — 파이프 `\\.\pipe\maro_sentinel_<PID>`, 뮤텍스 `Global\maro_sentinel_mutex_<PID>`, 킬 이벤트 `Global\maro_sentinel_kill_<PID>`, 기록 파일 `<book 디렉터리>/maro_sentinel.<PID>.json`. 이름을 만드는 함수는 `maro_ipc/Naming.h` 한 곳에서만 정의한다(두 곳에서 각자 만들면 저널이 겪었던 "우연히 맞아떨어지던 두 번째 정의" 함정이 재발한다)
- **예외는 Maya 콜백을 넘지 않는다.** `maro_sentinel.exe`는 Maya 콜백이 아니지만, `MaroPluginMain.cpp`에 들어가는 배선 코드는 이 규율을 그대로 따른다
- **감시자 spawn/접속 실패는 플러그인 로드를 막지 않는다** — book/저널이 못 열릴 때와 같은 규율
- **모든 대기에 타임아웃을 건다.** `WaitForSingleObject`/`WaitForMultipleObjects`에 `INFINITE`를 쓰지 않는다(딱 한 곳 예외: Task 5의 gtest 안에서 스레드 간 통신에 쓰는, 테스트 스스로 정한 타임아웃)
- **컨피그를 항상 명시한다.** 이 저장소의 `out/build`는 CMake Visual Studio 제너레이터(멀티 컨피그)다. `cmake --build out/build --config Release`, `ctest --test-dir out/build -C Release`처럼 컨피그 없이 부르지 않는다
- 새 테스트는 전부 **일부러 구현을 깨서 실패하는 것까지 확인**한다
- 다음 경로는 건드리지 않는다: `src/control_bridge/`, `src/image_bridge/`, `src/Maro_library/`, `MaroCmd.cpp`, `moveTool.cpp`, `rosSimCmd.cpp`, `Maro_DebugUtility/`, `Maro_Management/`
- **book 정본 쓰기, `offix`/`ghost`/`OSbridge`, 부스러기 스트림은 이 플랜의 범위 밖이다.** 감시자가 비정상 종료를 감지했을 때 하는 일은 기록 파일에 상태 필드 하나를 쓰는 것뿐이다

빌드 환경: `Launch-VsDevShell.ps1`은 이 머신에서 `vswhere.exe`를 못 찾아 `INCLUDE`/`LIB`를 비운 채 조용히 성공한다. **빌드와 같은 PowerShell 호출 안에서** `VsDevCmd.bat`를 설정한다.

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cd C:\Users\ckd30\Projects\Maya_Ros_Sim
cmake --build out/build --config Release
```

`ctest --test-dir out/build -C Release --output-on-failure` 실행 시 `maya_panel_commands` 하나만 실패하는 것이 알려진 사전 결함이다(이 플랜과 무관, `main`에 이미 있음) — 그 외에는 전부 통과해야 한다.

빌드가 `LNK1168`로 실패하면 잔존 `mayapy.exe`가 DLL을 잡고 있는 것이다: `Get-CimInstance Win32_Process -Filter "Name='mayapy.exe'" | Invoke-CimMethod -MethodName Terminate`. `maro_sentinel.exe`가 좀비로 남아 있어도 같은 방식으로 확인·정리한다: `Get-CimInstance Win32_Process -Filter "Name='maro_sentinel.exe'"`.

## 파일 구조

| 파일 | 책임 |
|---|---|
| `src/maro_ipc/include/maro_ipc/Message.h` / `src/Message.cpp` | 메시지 타입(`Hello`/`SessionEndClean`)과 인코딩/디코딩. Maya도 파이프도 모른다 |
| `src/maro_ipc/include/maro_ipc/Naming.h` / `src/Naming.cpp` | PID로부터 파이프/뮤텍스/이벤트 이름과 기록 파일 경로를 만드는 단일 정의 |
| `src/maro_ipc/include/maro_ipc/SentinelRecord.h` / `src/SentinelRecord.cpp` | PID 기록 파일의 읽기/쓰기(JSON) |
| `src/maro_ipc/include/maro_ipc/NamedMutexGuard.h` / `src/NamedMutexGuard.cpp` | 명명된 뮤텍스 RAII (C-4가 book 쓰기 직렬화에 재사용할 자리) |
| `src/maro_ipc/include/maro_ipc/NamedPipe.h` / `src/NamedPipe.cpp` | 메시지 모드 명명된 파이프 서버/클라이언트 |
| `src/maro_ipc/include/maro_ipc/JobEscape.h` / `src/JobEscape.cpp` | `IsProcessInJob` 자가 점검, `CREATE_BREAKAWAY_FROM_JOB` spawn, WMI `Win32_Process::Create` spawn |
| `src/maro_sentinel/main.cpp` | 감시자 진입점 — 위 조각을 전부 조립 |
| `src/maro_plugin/MaroSentinelClient.h` / `.cpp` | 플러그인 쪽 배선: spawn 지휘(3단계), 접속, `HELLO`/`SESSION_END_CLEAN` |
| `src/maro_plugin/MaroPluginMain.cpp` | (수정) `SentinelGuard` 추가, 로드/언로드 훅 |
| `src/maro_plugin/MaroDiag.h` / `.cpp` | (수정) `BoadMaro::bookDirectory()` 공개 접근자 추가 — 기존 `journalDirectory()`의 이미 해소된 결과를 노출해, 감시자에게 넘길 book 디렉터리를 `MaroSentinelClient`가 다시 해석하지 않게 한다 |
| `tests/ipc/*.cpp` | gtest — 메시지, 명명 규칙, 기록 파일, 뮤텍스, 파이프 |
| `tests/ipc/job_escape_test_helper.cpp` | gtest가 서브프로세스로 띄우는 작은 도우미 실행 파일 — 스스로 제한적인 job에 들어간 뒤 tier 1/2 탈출을 시도하고 결과를 종료 코드로 보고 |
| `tests/maya/test_sentinel.py` | 종단 통합 테스트(mayapy, 여러 프로세스) |

---

### Task 1: 메시지 타입과 프레이밍

**Files:**
- Create: `src/maro_ipc/include/maro_ipc/Message.h`, `src/maro_ipc/src/Message.cpp`
- Create: `tests/ipc/test_message.cpp`
- Modify: `src/maro_ipc/CMakeLists.txt`(신규), `tests/CMakeLists.txt`, 최상위 `CMakeLists.txt`

**Interfaces:**
- Produces: `maro::ipc::MessageType`(enum: `Hello`, `SessionEndClean`), `maro::ipc::Message`(`type`, `std::string payload` — C-1은 항상 빈 문자열, C-2의 부스러기 확장 자리), `maro::ipc::encodeMessage(const Message&) -> std::string`, `maro::ipc::decodeMessage(const std::string&, Message& out) -> bool`

메시지 모드 명명된 파이프(Task 5)는 한 번의 `WriteFile`이 한 번의 논리적 메시지가 되도록 Windows가 경계를 보존해 준다 — 그래서 이 계층은 길이 프리픽스를 직접 관리할 필요 없이, 페이로드 문자열 하나(JSON 한 줄)만 만들면 된다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/ipc/test_message.cpp`:

```cpp
#include <gtest/gtest.h>

#include "maro_ipc/Message.h"

namespace {

TEST(Message, RoundTripsHello) {
    maro::ipc::Message msg;
    msg.type = maro::ipc::MessageType::Hello;

    const std::string encoded = maro::ipc::encodeMessage(msg);
    maro::ipc::Message decoded;
    ASSERT_TRUE(maro::ipc::decodeMessage(encoded, decoded));
    EXPECT_EQ(decoded.type, maro::ipc::MessageType::Hello);
    EXPECT_TRUE(decoded.payload.empty());
}

TEST(Message, RoundTripsSessionEndClean) {
    maro::ipc::Message msg;
    msg.type = maro::ipc::MessageType::SessionEndClean;

    const std::string encoded = maro::ipc::encodeMessage(msg);
    maro::ipc::Message decoded;
    ASSERT_TRUE(maro::ipc::decodeMessage(encoded, decoded));
    EXPECT_EQ(decoded.type, maro::ipc::MessageType::SessionEndClean);
}

// C-2가 태그 붙은 페이로드를 실을 자리 -- 지금은 비워 두지만 왕복은 된다.
TEST(Message, PayloadRoundTrips) {
    maro::ipc::Message msg;
    msg.type = maro::ipc::MessageType::Hello;
    msg.payload = "future breadcrumb data";

    const std::string encoded = maro::ipc::encodeMessage(msg);
    maro::ipc::Message decoded;
    ASSERT_TRUE(maro::ipc::decodeMessage(encoded, decoded));
    EXPECT_EQ(decoded.payload, "future breadcrumb data");
}

// 깨진 바이트열(파이프 오류로 반쪽만 온 경우 등)은 예외 없이 false를 돌려준다.
TEST(Message, DecodeFailsCleanlyOnGarbage) {
    maro::ipc::Message decoded;
    EXPECT_FALSE(maro::ipc::decodeMessage("not json at all {{{", decoded));
}

TEST(Message, DecodeFailsOnUnknownType) {
    maro::ipc::Message decoded;
    EXPECT_FALSE(maro::ipc::decodeMessage(R"({"type":"nonsense","payload":""})", decoded));
}

}  // namespace
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
ctest --test-dir out/build -C Release --output-on-failure -R Message
```

기대: 컴파일 실패 — `maro_ipc/Message.h`가 없다.

- [ ] **Step 3: `Message.h` 작성**

`src/maro_ipc/include/maro_ipc/Message.h`:

```cpp
#pragma once

#include <string>

namespace maro::ipc {

// 감시자와 플러그인이 주고받는 메시지 종류. C-1은 둘뿐이다. C-2가 부스러기
// 스트림을 위해 새 종류를 추가할 자리이며, payload 필드가 그 확장을 이미
// 받아들일 수 있게 지금부터 있다(지금은 항상 빈 문자열).
enum class MessageType {
    Hello,            // 접속 직후. 프레이밍이 실제로 도는지 확인하는 용도.
    SessionEndClean,  // 정상 종료 신호. 이 메시지 없이 파이프가 끊기면 비정상 종료다.
};

struct Message {
    MessageType type = MessageType::Hello;
    std::string payload;
};

// 메시지 모드 파이프의 한 번의 WriteFile 페이로드로 쓸 문자열을 만든다.
std::string encodeMessage(const Message& message);

// encodeMessage()가 만든 문자열을 되돌린다. 형식이 깨졌거나 type이 모르는
// 값이면 false를 돌려주고 out은 건드리지 않는다 -- 예외를 던지지 않는다.
bool decodeMessage(const std::string& encoded, Message& out);

}  // namespace maro::ipc
```

- [ ] **Step 4: `Message.cpp` 작성**

`src/maro_ipc/src/Message.cpp`:

```cpp
#include "maro_ipc/Message.h"

#include <nlohmann/json.hpp>

namespace maro::ipc {

namespace {

const char* typeName(MessageType type) {
    switch (type) {
        case MessageType::Hello: return "hello";
        case MessageType::SessionEndClean: return "sessionEndClean";
    }
    return "unknown";
}

}  // namespace

std::string encodeMessage(const Message& message) {
    nlohmann::json j;
    j["type"] = typeName(message.type);
    j["payload"] = message.payload;
    return j.dump();
}

bool decodeMessage(const std::string& encoded, Message& out) {
    nlohmann::json j;
    try {
        j = nlohmann::json::parse(encoded);
    } catch (...) {
        return false;
    }

    const std::string type = j.value("type", std::string());
    if (type == "hello") {
        out.type = MessageType::Hello;
    } else if (type == "sessionEndClean") {
        out.type = MessageType::SessionEndClean;
    } else {
        return false;
    }
    out.payload = j.value("payload", std::string());
    return true;
}

}  // namespace maro::ipc
```

- [ ] **Step 5: `maro_ipc` 라이브러리 CMake 작성**

`src/maro_ipc/CMakeLists.txt` (신규 파일):

```cmake
find_package(nlohmann_json CONFIG REQUIRED)

add_library(maro_ipc STATIC
    src/Message.cpp
)

target_include_directories(maro_ipc PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# Message.cpp 내부에서만 쓴다 -- maro_diag/CMakeLists.txt와 같은 이유로 PRIVATE.
target_link_libraries(maro_ipc PRIVATE nlohmann_json::nlohmann_json)

# maro_plugin에 링크되므로 그 타깃이 강제하는 표준을 맞춘다
# (maro_diag/CMakeLists.txt와 같은 이유).
target_compile_features(maro_ipc PUBLIC cxx_std_17)

# 이 라이브러리 전체가 Windows 전용이다(다음 태스크들이 명명된 파이프/뮤텍스/
# job object를 쓴다). 지금 당장은 이 파일에 Windows API 호출이 없지만, 이후
# 태스크들이 여기 소스를 추가하므로 정의를 미리 걸어 둔다.
target_compile_definitions(maro_ipc PUBLIC NOMINMAX WIN32_LEAN_AND_MEAN)
```

최상위 `CMakeLists.txt`의 `add_subdirectory(src/maro_diag)` 아래에 추가:

```cmake
add_subdirectory(src/maro_ipc)
```

`tests/CMakeLists.txt`의 맨 위, `find_package(nlohmann_json CONFIG REQUIRED)` 아래에 추가:

```cmake
add_executable(maro_ipc_tests
    ipc/test_message.cpp
)

target_link_libraries(maro_ipc_tests PRIVATE
    maro_ipc
    GTest::gtest
    GTest::gtest_main
)

gtest_discover_tests(maro_ipc_tests)
```

- [ ] **Step 6: 빌드하고 테스트가 통과하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R Message
```

기대: 5개 전부 통과.

- [ ] **Step 7: 알 수 없는 타입이 진짜로 거부되는지 확인**

`decodeMessage`의 `else { return false; }`를 `else { out.type = MessageType::Hello; }`로 바꾼다(모르는 타입을 Hello로 얼버무린다).

```bash
cmake --build out/build --config Release && ctest --test-dir out/build -C Release --output-on-failure -R Message
```

기대: `DecodeFailsOnUnknownType`이 **실패**한다. 확인했으면 되돌린다.

- [ ] **Step 8: 커밋**

```bash
git add src/maro_ipc CMakeLists.txt tests/CMakeLists.txt tests/ipc/test_message.cpp
git commit -m "feat: give the sentinel and plugin a message format to agree on"
```

---

### Task 2: 명명 규칙

**Files:**
- Create: `src/maro_ipc/include/maro_ipc/Naming.h`, `src/maro_ipc/src/Naming.cpp`
- Create: `tests/ipc/test_naming.cpp`
- Modify: `src/maro_ipc/CMakeLists.txt`, `tests/CMakeLists.txt`

**Interfaces:**
- Produces: `maro::ipc::pipeName(std::uint64_t pid) -> std::string`, `maro::ipc::mutexName(std::uint64_t pid) -> std::string`, `maro::ipc::killEventName(std::uint64_t pid) -> std::string`, `maro::ipc::recordFilePath(const std::filesystem::path& bookDir, std::uint64_t pid) -> std::filesystem::path`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/ipc/test_naming.cpp`:

```cpp
#include <gtest/gtest.h>

#include "maro_ipc/Naming.h"

namespace {

TEST(Naming, PipeNameEmbedsPid) {
    EXPECT_EQ(maro::ipc::pipeName(1234), "\\\\.\\pipe\\maro_sentinel_1234");
}

TEST(Naming, MutexNameEmbedsPid) {
    EXPECT_EQ(maro::ipc::mutexName(1234), "Global\\maro_sentinel_mutex_1234");
}

TEST(Naming, KillEventNameEmbedsPid) {
    EXPECT_EQ(maro::ipc::killEventName(1234), "Global\\maro_sentinel_kill_1234");
}

TEST(Naming, RecordFilePathEmbedsPid) {
    const auto path = maro::ipc::recordFilePath("C:/some/book/dir", 1234);
    EXPECT_EQ(path.filename().string(), "maro_sentinel.1234.json");
}

// 서로 다른 PID는 서로 다른 이름을 낸다 -- 이 플랜의 핵심 불변식.
TEST(Naming, DifferentPidsGiveDifferentNames) {
    EXPECT_NE(maro::ipc::pipeName(1), maro::ipc::pipeName(2));
    EXPECT_NE(maro::ipc::mutexName(1), maro::ipc::mutexName(2));
    EXPECT_NE(maro::ipc::killEventName(1), maro::ipc::killEventName(2));
    EXPECT_NE(maro::ipc::recordFilePath("C:/dir", 1),
              maro::ipc::recordFilePath("C:/dir", 2));
}

}  // namespace
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
ctest --test-dir out/build -C Release --output-on-failure -R Naming
```

기대: 컴파일 실패 — `maro_ipc/Naming.h`가 없다.

- [ ] **Step 3: `Naming.h` 작성**

`src/maro_ipc/include/maro_ipc/Naming.h`:

```cpp
#pragma once

#include <cstdint>
#include <filesystem>
#include <string>

namespace maro::ipc {

// 아래 넷은 전부 이 파일 한 곳에서만 정의한다. 두 곳에서 각자 이름을
// 만들면(예: 플러그인 쪽이 pipeName을 한 번 더 손으로 짓는다면) 저널이
// 겪었던 "세션-open 판정이 writer/reader에 따로 있다가 우연히만 맞아떨어진"
// 함정이 재발한다.

// 파이프 이름. \\.\pipe\maro_sentinel_<pid> 모양.
std::string pipeName(std::uint64_t pid);

// 명명된 뮤텍스 이름. Global\ 접두사로 세션 0(서비스)과도 충돌하지 않는다.
std::string mutexName(std::uint64_t pid);

// 킬 스위치 이벤트 이름.
std::string killEventName(std::uint64_t pid);

// PID·시작 시각 기록 파일 경로. bookDir는 이미 존재를 보장받은 디렉터리라고
// 가정한다(호출부가 만든다) -- 이 함수는 경로만 계산하고 디스크를 건드리지 않는다.
std::filesystem::path recordFilePath(const std::filesystem::path& bookDir, std::uint64_t pid);

}  // namespace maro::ipc
```

- [ ] **Step 4: `Naming.cpp` 작성**

`src/maro_ipc/src/Naming.cpp`:

```cpp
#include "maro_ipc/Naming.h"

namespace maro::ipc {

std::string pipeName(std::uint64_t pid) {
    return "\\\\.\\pipe\\maro_sentinel_" + std::to_string(pid);
}

std::string mutexName(std::uint64_t pid) {
    return "Global\\maro_sentinel_mutex_" + std::to_string(pid);
}

std::string killEventName(std::uint64_t pid) {
    return "Global\\maro_sentinel_kill_" + std::to_string(pid);
}

std::filesystem::path recordFilePath(const std::filesystem::path& bookDir, std::uint64_t pid) {
    return bookDir / ("maro_sentinel." + std::to_string(pid) + ".json");
}

}  // namespace maro::ipc
```

- [ ] **Step 5: 빌드에 등록**

`src/maro_ipc/CMakeLists.txt`의 `add_library(maro_ipc STATIC` 목록에 추가:

```cmake
add_library(maro_ipc STATIC
    src/Message.cpp
    src/Naming.cpp
)
```

`tests/CMakeLists.txt`의 `add_executable(maro_ipc_tests` 목록에 추가:

```cmake
add_executable(maro_ipc_tests
    ipc/test_message.cpp
    ipc/test_naming.cpp
)
```

- [ ] **Step 6: 빌드하고 테스트가 통과하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R Naming
```

기대: 5개 전부 통과.

- [ ] **Step 7: PID가 진짜로 이름에 들어가는지 확인**

`pipeName`을 임시로 `return "\\\\.\\pipe\\maro_sentinel_fixed";`로 바꾼다(PID를 무시).

```bash
cmake --build out/build --config Release && ctest --test-dir out/build -C Release --output-on-failure -R Naming
```

기대: `PipeNameEmbedsPid`와 `DifferentPidsGiveDifferentNames`가 **실패**한다. 확인했으면 되돌린다.

- [ ] **Step 8: 커밋**

```bash
git add src/maro_ipc tests/CMakeLists.txt tests/ipc/test_naming.cpp
git commit -m "feat: name every sentinel resource after the Maya process it belongs to"
```

---

### Task 3: PID 기록 파일

**Files:**
- Create: `src/maro_ipc/include/maro_ipc/SentinelRecord.h`, `src/maro_ipc/src/SentinelRecord.cpp`
- Create: `tests/ipc/test_sentinel_record.cpp`
- Modify: `src/maro_ipc/CMakeLists.txt`, `tests/CMakeLists.txt`

**Interfaces:**
- Consumes: `maro::ipc::recordFilePath` (Task 2)
- Produces: `maro::ipc::SentinelRecord`(`sentinelPid`, `ownerMayaPid`, `startTimeMs`, `lastSessionEndedCleanly` — `optional<bool>`, 아직 판정 전이면 `nullopt`), `maro::ipc::writeSentinelRecord(path, record) -> bool`, `maro::ipc::readSentinelRecord(path, SentinelRecord& out) -> bool`

`lastSessionEndedCleanly`가 이 태스크의 핵심 확장 자리다 — Task 8(감시자 메인 루프)이 비정상 종료를 감지한 순간 이 필드를 `false`로 써서, C-1이 "가지고 무엇을 하는지"의 유일한 관측 가능한 산출물로 삼는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/ipc/test_sentinel_record.cpp`:

```cpp
#include <gtest/gtest.h>

#include <filesystem>

#include "maro_ipc/SentinelRecord.h"

namespace {

std::filesystem::path freshDir(const std::string& name) {
    const std::filesystem::path dir =
        std::filesystem::temp_directory_path() / ("maro_sentinel_record_test_" + name);
    std::error_code ec;
    std::filesystem::remove_all(dir, ec);
    std::filesystem::create_directories(dir, ec);
    return dir;
}

TEST(SentinelRecord, WriteThenReadRoundTrips) {
    const auto path = freshDir("roundtrip") / "record.json";
    maro::ipc::SentinelRecord record;
    record.sentinelPid = 111;
    record.ownerMayaPid = 222;
    record.startTimeMs = 1700000000000ULL;

    ASSERT_TRUE(maro::ipc::writeSentinelRecord(path, record));

    maro::ipc::SentinelRecord read;
    ASSERT_TRUE(maro::ipc::readSentinelRecord(path, read));
    EXPECT_EQ(read.sentinelPid, 111u);
    EXPECT_EQ(read.ownerMayaPid, 222u);
    EXPECT_EQ(read.startTimeMs, 1700000000000ULL);
    EXPECT_FALSE(read.lastSessionEndedCleanly.has_value());
}

TEST(SentinelRecord, CleanlyFlagRoundTrips) {
    const auto path = freshDir("clean_flag") / "record.json";
    maro::ipc::SentinelRecord record;
    record.sentinelPid = 1;
    record.ownerMayaPid = 2;
    record.startTimeMs = 1;
    record.lastSessionEndedCleanly = false;

    ASSERT_TRUE(maro::ipc::writeSentinelRecord(path, record));
    maro::ipc::SentinelRecord read;
    ASSERT_TRUE(maro::ipc::readSentinelRecord(path, read));
    ASSERT_TRUE(read.lastSessionEndedCleanly.has_value());
    EXPECT_FALSE(*read.lastSessionEndedCleanly);
}

TEST(SentinelRecord, ReadMissingFileFailsCleanly) {
    maro::ipc::SentinelRecord out;
    EXPECT_FALSE(maro::ipc::readSentinelRecord(
        freshDir("missing") / "nope.json", out));
}

TEST(SentinelRecord, WriteCreatesParentDirectory) {
    const auto dir = freshDir("parent_create");
    const auto path = dir / "nested" / "record.json";
    maro::ipc::SentinelRecord record;
    record.sentinelPid = 1;
    record.ownerMayaPid = 2;
    record.startTimeMs = 3;
    EXPECT_TRUE(maro::ipc::writeSentinelRecord(path, record));
    EXPECT_TRUE(std::filesystem::exists(path));
}

}  // namespace
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
ctest --test-dir out/build -C Release --output-on-failure -R SentinelRecord
```

기대: 컴파일 실패 — `maro_ipc/SentinelRecord.h`가 없다.

- [ ] **Step 3: `SentinelRecord.h` 작성**

`src/maro_ipc/include/maro_ipc/SentinelRecord.h`:

```cpp
#pragma once

#include <cstdint>
#include <filesystem>
#include <optional>

namespace maro::ipc {

// PID 기록 파일 한 장. 사람이 손으로 감시자를 찾을 때 헤매지 않게 하고,
// 다음 플러그인 로드의 자가 점검이 이 정보로 낡은 감시자를 알아본다.
struct SentinelRecord {
    std::uint64_t sentinelPid = 0;
    std::uint64_t ownerMayaPid = 0;
    std::uint64_t startTimeMs = 0;

    // C-1이 관측 가능한 결과를 내는 유일한 자리. 세션이 끝나기 전에는
    // nullopt("아직 모른다"), 감시자가 SESSION_END_CLEAN 없이 파이프가
    // 끊긴 것을 본 순간 false로 쓴다. true는 이 플랜에서 실제로 쓰지
    // 않는다 -- 정상 종료 시 감시자는 판정을 남길 필요 없이 그냥 종료하므로
    // (§3.4 "절대 수명" 참고), 이 필드가 있는데 값이 없으면 "아직 세션
    // 진행 중이거나 판정 전에 파일이 남았다"는 뜻이다.
    std::optional<bool> lastSessionEndedCleanly;
};

// 실패해도 예외를 던지지 않는다. 부모 디렉터리가 없으면 만든다.
bool writeSentinelRecord(const std::filesystem::path& path, const SentinelRecord& record);

// 파일이 없거나 형식이 깨졌으면 false. out은 그때 건드리지 않는다.
bool readSentinelRecord(const std::filesystem::path& path, SentinelRecord& out);

}  // namespace maro::ipc
```

- [ ] **Step 4: `SentinelRecord.cpp` 작성**

`src/maro_ipc/src/SentinelRecord.cpp`:

```cpp
#include "maro_ipc/SentinelRecord.h"

#include <fstream>

#include <nlohmann/json.hpp>

namespace maro::ipc {

bool writeSentinelRecord(const std::filesystem::path& path, const SentinelRecord& record) {
    try {
        std::error_code ec;
        std::filesystem::create_directories(path.parent_path(), ec);

        nlohmann::json j;
        j["sentinelPid"] = record.sentinelPid;
        j["ownerMayaPid"] = record.ownerMayaPid;
        j["startTimeMs"] = record.startTimeMs;
        if (record.lastSessionEndedCleanly.has_value()) {
            j["lastSessionEndedCleanly"] = *record.lastSessionEndedCleanly;
        }

        std::ofstream out(path, std::ios::out | std::ios::trunc | std::ios::binary);
        if (!out.is_open()) return false;
        out << j.dump();
        return out.good();
    } catch (...) {
        return false;
    }
}

bool readSentinelRecord(const std::filesystem::path& path, SentinelRecord& out) {
    try {
        std::ifstream in(path, std::ios::binary);
        if (!in.is_open()) return false;

        nlohmann::json j;
        in >> j;

        SentinelRecord record;
        record.sentinelPid = j.at("sentinelPid").get<std::uint64_t>();
        record.ownerMayaPid = j.at("ownerMayaPid").get<std::uint64_t>();
        record.startTimeMs = j.at("startTimeMs").get<std::uint64_t>();
        if (j.contains("lastSessionEndedCleanly")) {
            record.lastSessionEndedCleanly = j.at("lastSessionEndedCleanly").get<bool>();
        }
        out = record;
        return true;
    } catch (...) {
        return false;
    }
}

}  // namespace maro::ipc
```

- [ ] **Step 5: 빌드에 등록**

`src/maro_ipc/CMakeLists.txt`의 `add_library(maro_ipc STATIC` 목록과 `tests/CMakeLists.txt`의 `add_executable(maro_ipc_tests` 목록에 각각 추가:

```cmake
    src/SentinelRecord.cpp
```
```cmake
    ipc/test_sentinel_record.cpp
```

- [ ] **Step 6: 빌드하고 테스트가 통과하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R SentinelRecord
```

기대: 4개 전부 통과.

- [ ] **Step 7: `lastSessionEndedCleanly`가 진짜로 왕복하는지 확인**

`writeSentinelRecord`에서 `if (record.lastSessionEndedCleanly.has_value())` 블록 전체를 지운다(그 필드를 절대 안 쓴다).

```bash
cmake --build out/build --config Release && ctest --test-dir out/build -C Release --output-on-failure -R SentinelRecord
```

기대: `CleanlyFlagRoundTrips`가 **실패**한다(`has_value()`가 false). 확인했으면 되돌린다.

- [ ] **Step 8: 커밋**

```bash
git add src/maro_ipc tests/CMakeLists.txt tests/ipc/test_sentinel_record.cpp
git commit -m "feat: give the sentinel a record file people and the next load can read"
```

---

### Task 4: 명명된 뮤텍스 RAII

**Files:**
- Create: `src/maro_ipc/include/maro_ipc/NamedMutexGuard.h`, `src/maro_ipc/src/NamedMutexGuard.cpp`
- Create: `tests/ipc/test_named_mutex_guard.cpp`
- Modify: `src/maro_ipc/CMakeLists.txt`, `tests/CMakeLists.txt`

**Interfaces:**
- Produces: `maro::ipc::NamedMutexGuard`(생성자 `NamedMutexGuard(const std::string& name, std::uint32_t timeoutMs)`, `bool isAcquired() const`, 소멸자가 해제)

이 태스크가 C-4(book 정본 쓰기 직렬화)가 그대로 재사용할 자리다 — 지금은 이름 하나(§3.1의 단일 인스턴스 뮤텍스)에만 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/ipc/test_named_mutex_guard.cpp`:

```cpp
#include <gtest/gtest.h>

#include <thread>

#include "maro_ipc/NamedMutexGuard.h"

namespace {

// 같은 프로세스 안 두 스레드가 같은 이름으로 CreateMutex를 부르면 실제
// Windows API가 같은 커널 객체를 돌려준다 -- 별도 프로세스 없이도 진짜
// 뮤텍스 경합을 테스트할 수 있다.
TEST(NamedMutexGuard, SecondAcquireBlocksUntilFirstReleases) {
    const std::string name =
        "Local\\maro_test_mutex_" + std::to_string(::GetCurrentProcessId());

    maro::ipc::NamedMutexGuard first(name, 1000);
    ASSERT_TRUE(first.isAcquired());

    bool secondAcquiredWhileFirstHeld = false;
    std::thread t([&]() {
        // 첫 번째가 쥐고 있는 동안은 짧은 타임아웃 안에 못 얻어야 한다.
        maro::ipc::NamedMutexGuard second(name, 100);
        secondAcquiredWhileFirstHeld = second.isAcquired();
    });
    t.join();
    EXPECT_FALSE(secondAcquiredWhileFirstHeld);
}

TEST(NamedMutexGuard, AcquiresAfterPriorGuardIsDestroyed) {
    const std::string name =
        "Local\\maro_test_mutex2_" + std::to_string(::GetCurrentProcessId());

    {
        maro::ipc::NamedMutexGuard first(name, 1000);
        ASSERT_TRUE(first.isAcquired());
    }  // 여기서 해제된다.

    maro::ipc::NamedMutexGuard second(name, 1000);
    EXPECT_TRUE(second.isAcquired());
}

}  // namespace
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
ctest --test-dir out/build -C Release --output-on-failure -R NamedMutexGuard
```

기대: 컴파일 실패 — `maro_ipc/NamedMutexGuard.h`가 없다.

- [ ] **Step 3: `NamedMutexGuard.h` 작성**

`src/maro_ipc/include/maro_ipc/NamedMutexGuard.h`:

```cpp
#pragma once

#include <cstdint>
#include <string>

#include <windows.h>

namespace maro::ipc {

// 명명된 뮤텍스 하나를 얻고 소멸 시 놓는다. 획득 실패(타임아웃, 이미 다른
// 프로세스가 쥐고 있음)는 예외가 아니라 isAcquired()==false로 나타난다 --
// 호출부가 "못 얻었으니 포기한다"를 스스로 판단하게 한다.
//
// C-1은 이것을 감시자 단일 인스턴스 보호에만 쓴다. C-4(book 정본 쓰기를
// 감시자로 이전)가 새 이름(예: Global\maro_book_write_mutex)으로 같은
// 타입을 재사용해 프로세스 간 book 쓰기를 직렬화할 자리다.
class NamedMutexGuard {
public:
    NamedMutexGuard(const std::string& name, std::uint32_t timeoutMs);
    ~NamedMutexGuard();

    NamedMutexGuard(const NamedMutexGuard&) = delete;
    NamedMutexGuard& operator=(const NamedMutexGuard&) = delete;

    bool isAcquired() const { return acquired_; }

private:
    HANDLE handle_ = nullptr;
    bool acquired_ = false;
};

}  // namespace maro::ipc
```

- [ ] **Step 4: `NamedMutexGuard.cpp` 작성**

`src/maro_ipc/src/NamedMutexGuard.cpp`:

```cpp
#include "maro_ipc/NamedMutexGuard.h"

namespace maro::ipc {

NamedMutexGuard::NamedMutexGuard(const std::string& name, std::uint32_t timeoutMs) {
    // bInitialOwner=FALSE -- 만들자마자 자동으로 갖지 않는다. 아래
    // WaitForSingleObject가 소유권을 얻는 유일한 경로여야 "얻었다"의 의미가
    // 하나로 고정된다.
    handle_ = ::CreateMutexA(nullptr, FALSE, name.c_str());
    if (handle_ == nullptr) {
        acquired_ = false;
        return;
    }

    const DWORD result = ::WaitForSingleObject(handle_, timeoutMs);
    // WAIT_ABANDONED: 이전 소유자가 놓지 않고 죽었다는 뜻이다. 뮤텍스
    // 자체는 여전히 유효한 소유권으로 넘어오므로 획득으로 친다 -- 이
    // 프로젝트가 "죽은 프로세스가 남긴 잠금 때문에 다음 프로세스가 영원히
    // 못 뜨는" 상태를 만들지 않는다는 원칙과 같다.
    acquired_ = (result == WAIT_OBJECT_0 || result == WAIT_ABANDONED);
    if (!acquired_) {
        ::CloseHandle(handle_);
        handle_ = nullptr;
    }
}

NamedMutexGuard::~NamedMutexGuard() {
    if (acquired_ && handle_ != nullptr) {
        ::ReleaseMutex(handle_);
    }
    if (handle_ != nullptr) {
        ::CloseHandle(handle_);
    }
}

}  // namespace maro::ipc
```

- [ ] **Step 5: 빌드에 등록**

`src/maro_ipc/CMakeLists.txt`의 `add_library(maro_ipc STATIC` 목록과 `tests/CMakeLists.txt`의 `add_executable(maro_ipc_tests` 목록에 각각 추가:

```cmake
    src/NamedMutexGuard.cpp
```
```cmake
    ipc/test_named_mutex_guard.cpp
```

- [ ] **Step 6: 빌드하고 테스트가 통과하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R NamedMutexGuard
```

기대: 2개 전부 통과.

- [ ] **Step 7: 경합이 진짜인지 확인**

`WaitForSingleObject`의 결과 판정을 임시로 `acquired_ = true;`(타임아웃과 무관하게 항상 획득한 것으로)로 바꾼다.

```bash
cmake --build out/build --config Release && ctest --test-dir out/build -C Release --output-on-failure -R NamedMutexGuard
```

기대: `SecondAcquireBlocksUntilFirstReleases`가 **실패**한다(`secondAcquiredWhileFirstHeld`가 true). 확인했으면 되돌린다.

- [ ] **Step 8: 커밋**

```bash
git add src/maro_ipc tests/CMakeLists.txt tests/ipc/test_named_mutex_guard.cpp
git commit -m "feat: add a named-mutex RAII guard, for single-instance protection now and book-write serialization later"
```

---

### Task 5: 메시지 모드 명명된 파이프

**Files:**
- Create: `src/maro_ipc/include/maro_ipc/NamedPipe.h`, `src/maro_ipc/src/NamedPipe.cpp`
- Create: `tests/ipc/test_named_pipe.cpp`
- Modify: `src/maro_ipc/CMakeLists.txt`, `tests/CMakeLists.txt`

**Interfaces:**
- Consumes: `maro::ipc::Message`, `encodeMessage`, `decodeMessage` (Task 1)
- Produces: `maro::ipc::NamedPipeServer`(생성자 `explicit NamedPipeServer(const std::string& pipeName)`, `bool waitForConnection(std::uint32_t timeoutMs)`, `bool receiveMessage(Message& out, std::uint32_t timeoutMs)`, `bool sendMessage(const Message&)`, `void close()`), `maro::ipc::NamedPipeClient`(`bool connect(const std::string& pipeName, std::uint32_t timeoutMs)`, `bool sendMessage(const Message&)`, `bool receiveMessage(Message& out, std::uint32_t timeoutMs)`, `void close()`)

**설계 메모.** `CreateNamedPipeA`를 `PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE`로 열면 한 번의 `WriteFile`이 한 번의 `ReadFile`로 그대로 도착한다(파이프가 스트림이 아니라 메시지 경계를 보존) — Task 1이 길이 프리픽스를 직접 관리하지 않아도 되는 이유다. 타임아웃은 오버랩(비동기) I/O로 만든다: `FILE_FLAG_OVERLAPPED`로 핸들을 열고, `ReadFile`/`ConnectNamedPipe`가 `ERROR_IO_PENDING`을 돌려주면 `GetOverlappedResultEx`(또는 이벤트에 대고 `WaitForSingleObject`)로 타임아웃을 건다. 이 프로젝트의 "모든 대기에 타임아웃" 규율이 파이프에도 그대로 적용된다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/ipc/test_named_pipe.cpp`:

```cpp
#include <gtest/gtest.h>

#include <atomic>
#include <thread>

#include "maro_ipc/NamedPipe.h"

namespace {

std::string uniquePipeName(const char* suffix) {
    return "\\\\.\\pipe\\maro_ipc_test_" + std::string(suffix) + "_" +
           std::to_string(::GetCurrentProcessId());
}

// 서버를 별도 스레드에서 띄우고 메인 스레드가 클라이언트로 접속한다 --
// 명명된 파이프는 스레드 경계와 무관하게 동작하므로 별도 프로세스 없이도
// 실제 파이프 I/O를 검증할 수 있다.
TEST(NamedPipe, ClientAndServerExchangeHello) {
    const std::string name = uniquePipeName("hello");
    std::atomic<bool> serverGotHello{false};
    std::atomic<bool> serverSentBack{false};

    std::thread serverThread([&]() {
        maro::ipc::NamedPipeServer server(name);
        ASSERT_TRUE(server.waitForConnection(2000));

        maro::ipc::Message received;
        ASSERT_TRUE(server.receiveMessage(received, 2000));
        serverGotHello = (received.type == maro::ipc::MessageType::Hello);

        maro::ipc::Message reply;
        reply.type = maro::ipc::MessageType::Hello;
        serverSentBack = server.sendMessage(reply);
        server.close();
    });

    // 서버가 CreateNamedPipeA를 부를 시간을 준다 -- 클라이언트의 connect가
    // 그 전에 오면 ERROR_FILE_NOT_FOUND로 실패한다. connect() 자체가
    // 짧은 재시도 루프를 갖는 이유가 이것이다(Step 3 구현 참고).
    maro::ipc::NamedPipeClient client;
    ASSERT_TRUE(client.connect(name, 2000));

    maro::ipc::Message hello;
    hello.type = maro::ipc::MessageType::Hello;
    ASSERT_TRUE(client.sendMessage(hello));

    maro::ipc::Message reply;
    ASSERT_TRUE(client.receiveMessage(reply, 2000));
    EXPECT_EQ(reply.type, maro::ipc::MessageType::Hello);

    client.close();
    serverThread.join();
    EXPECT_TRUE(serverGotHello);
    EXPECT_TRUE(serverSentBack);
}

// 크래시 신호의 핵심: 메시지 없이 클라이언트가 그냥 닫히면 서버의
// receiveMessage는 "메시지가 옴"이 아니라 "연결이 끊김"을 구분해서
// 돌려줘야 한다. 이 구분이 없으면 감시자가 정상/비정상을 가릴 수 없다.
TEST(NamedPipe, ServerDetectsDisconnectWithoutMessage) {
    const std::string name = uniquePipeName("disconnect");
    std::atomic<bool> disconnectDetected{false};

    std::thread serverThread([&]() {
        maro::ipc::NamedPipeServer server(name);
        ASSERT_TRUE(server.waitForConnection(2000));

        maro::ipc::Message received;
        // 클라이언트가 아무 메시지도 안 보내고 닫으므로 이건 실패해야
        // 하고, 그 실패가 "메시지 없이 끊김"이어야 한다.
        const bool got = server.receiveMessage(received, 2000);
        disconnectDetected = !got;
        server.close();
    });

    {
        maro::ipc::NamedPipeClient client;
        ASSERT_TRUE(client.connect(name, 2000));
        client.close();  // 메시지 없이 바로 닫는다 -- SESSION_END_CLEAN이 아니다.
    }

    serverThread.join();
    EXPECT_TRUE(disconnectDetected);
}

TEST(NamedPipe, ConnectFailsCleanlyWhenNoServerListening) {
    maro::ipc::NamedPipeClient client;
    EXPECT_FALSE(client.connect(uniquePipeName("nobody_home"), 200));
}

}  // namespace
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
ctest --test-dir out/build -C Release --output-on-failure -R NamedPipe
```

기대: 컴파일 실패 — `maro_ipc/NamedPipe.h`가 없다.

- [ ] **Step 3: `NamedPipe.h` 작성**

`src/maro_ipc/include/maro_ipc/NamedPipe.h`:

```cpp
#pragma once

#include <cstdint>
#include <string>

#include <windows.h>

#include "maro_ipc/Message.h"

namespace maro::ipc {

// 메시지 모드 명명된 파이프의 서버 쪽(감시자가 만든다).
class NamedPipeServer {
public:
    explicit NamedPipeServer(const std::string& pipeName);
    ~NamedPipeServer();

    NamedPipeServer(const NamedPipeServer&) = delete;
    NamedPipeServer& operator=(const NamedPipeServer&) = delete;

    // 클라이언트 접속을 기다린다. 파이프를 못 만들었으면 즉시 false.
    bool waitForConnection(std::uint32_t timeoutMs);

    // 한 메시지를 받는다. 상대가 메시지 없이 연결을 끊으면(크래시 신호)
    // false를 돌려준다 -- 이 반환값 하나가 "정상 메시지 실패"와 "연결
    // 끊김"을 구분하지 않는 것처럼 보이지만, 감시자의 실제 판정(Task 8)은
    // 이 함수가 false를 돌려준 시점 자체가 아니라 그 *마지막으로 받은
    // 메시지가 SessionEndClean이었는가*로 정상/비정상을 가른다 -- 그래서
    // receiveMessage 자체는 성공/실패만 알면 충분하다.
    bool receiveMessage(Message& out, std::uint32_t timeoutMs);

    bool sendMessage(const Message& message);

    void close();

private:
    HANDLE pipe_ = INVALID_HANDLE_VALUE;
    bool connected_ = false;
};

// 메시지 모드 명명된 파이프의 클라이언트 쪽(플러그인이 붙는다).
class NamedPipeClient {
public:
    NamedPipeClient() = default;
    ~NamedPipeClient();

    NamedPipeClient(const NamedPipeClient&) = delete;
    NamedPipeClient& operator=(const NamedPipeClient&) = delete;

    // 서버가 아직 CreateNamedPipeA를 안 불렀을 수 있으므로(막 spawn된
    // 직후) timeoutMs 안에서 짧은 간격으로 재시도한다.
    bool connect(const std::string& pipeName, std::uint32_t timeoutMs);

    bool sendMessage(const Message& message);
    bool receiveMessage(Message& out, std::uint32_t timeoutMs);

    void close();

private:
    HANDLE pipe_ = INVALID_HANDLE_VALUE;
};

}  // namespace maro::ipc
```

- [ ] **Step 4: `NamedPipe.cpp` 작성**

`src/maro_ipc/src/NamedPipe.cpp`:

```cpp
#include "maro_ipc/NamedPipe.h"

#include <thread>

namespace maro::ipc {

namespace {

constexpr DWORD kBufferSize = 8192;

// 오버랩 I/O 하나를 타임아웃과 함께 기다린다. 성공하면 실제로 옮겨진
// 바이트 수를 outBytes에 채운다. 파이프가 끊겼으면(ERROR_BROKEN_PIPE류)
// false를 돌려준다 -- 이것이 "메시지 없이 연결 끊김"이 최종적으로
// 드러나는 지점이다.
bool waitOverlapped(HANDLE handle, OVERLAPPED& overlapped, std::uint32_t timeoutMs,
                     DWORD& outBytes) {
    const DWORD waitResult = ::WaitForSingleObject(overlapped.hEvent, timeoutMs);
    if (waitResult != WAIT_OBJECT_0) {
        ::CancelIoEx(handle, &overlapped);
        return false;
    }
    return ::GetOverlappedResult(handle, &overlapped, &outBytes, FALSE) != 0;
}

// RAII로 오버랩 구조체의 이벤트 핸들을 관리한다 -- 모든 오버랩 호출이
// 자기 이벤트를 새로 만들고 반드시 닫는다는 규율을 코드로 강제한다.
struct ScopedOverlapped {
    OVERLAPPED overlapped{};
    ScopedOverlapped() { overlapped.hEvent = ::CreateEventA(nullptr, TRUE, FALSE, nullptr); }
    ~ScopedOverlapped() {
        if (overlapped.hEvent != nullptr) ::CloseHandle(overlapped.hEvent);
    }
    ScopedOverlapped(const ScopedOverlapped&) = delete;
    ScopedOverlapped& operator=(const ScopedOverlapped&) = delete;
};

}  // namespace

NamedPipeServer::NamedPipeServer(const std::string& pipeName) {
    pipe_ = ::CreateNamedPipeA(
        pipeName.c_str(),
        PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED,
        PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
        1,  // 이 감시자는 자기 Maya 하나만 상대한다 -- §3.1의 1:1 모델.
        kBufferSize, kBufferSize,
        0,  // 기본 타임아웃 -- 실제 대기는 전부 오버랩+WaitForSingleObject로 직접 건다.
        nullptr);
}

NamedPipeServer::~NamedPipeServer() { close(); }

bool NamedPipeServer::waitForConnection(std::uint32_t timeoutMs) {
    if (pipe_ == INVALID_HANDLE_VALUE) return false;

    ScopedOverlapped scoped;
    if (scoped.overlapped.hEvent == nullptr) return false;

    const BOOL immediate = ::ConnectNamedPipe(pipe_, &scoped.overlapped);
    if (immediate) {
        connected_ = true;
        return true;
    }
    const DWORD err = ::GetLastError();
    if (err == ERROR_PIPE_CONNECTED) {
        // 클라이언트가 ConnectNamedPipe를 부르기 전에 이미 붙어 있었다 --
        // 성공으로 친다.
        connected_ = true;
        return true;
    }
    if (err != ERROR_IO_PENDING) return false;

    DWORD bytes = 0;
    connected_ = waitOverlapped(pipe_, scoped.overlapped, timeoutMs, bytes);
    return connected_;
}

bool NamedPipeServer::receiveMessage(Message& out, std::uint32_t timeoutMs) {
    if (pipe_ == INVALID_HANDLE_VALUE || !connected_) return false;

    ScopedOverlapped scoped;
    if (scoped.overlapped.hEvent == nullptr) return false;

    std::string buffer(kBufferSize, '\0');
    DWORD bytesRead = 0;
    const BOOL immediate = ::ReadFile(pipe_, buffer.data(),
                                      static_cast<DWORD>(buffer.size()), &bytesRead,
                                      &scoped.overlapped);
    if (!immediate) {
        const DWORD err = ::GetLastError();
        if (err != ERROR_IO_PENDING) return false;  // 여기 ERROR_BROKEN_PIPE도 포함.
        if (!waitOverlapped(pipe_, scoped.overlapped, timeoutMs, bytesRead)) return false;
    }

    buffer.resize(bytesRead);
    return decodeMessage(buffer, out);
}

bool NamedPipeServer::sendMessage(const Message& message) {
    if (pipe_ == INVALID_HANDLE_VALUE || !connected_) return false;

    ScopedOverlapped scoped;
    if (scoped.overlapped.hEvent == nullptr) return false;

    const std::string encoded = encodeMessage(message);
    DWORD bytesWritten = 0;
    const BOOL immediate = ::WriteFile(pipe_, encoded.data(),
                                       static_cast<DWORD>(encoded.size()), &bytesWritten,
                                       &scoped.overlapped);
    if (immediate) return bytesWritten == encoded.size();

    const DWORD err = ::GetLastError();
    if (err != ERROR_IO_PENDING) return false;
    return waitOverlapped(pipe_, scoped.overlapped, 5000, bytesWritten) &&
           bytesWritten == encoded.size();
}

void NamedPipeServer::close() {
    if (pipe_ != INVALID_HANDLE_VALUE) {
        if (connected_) ::DisconnectNamedPipe(pipe_);
        ::CloseHandle(pipe_);
        pipe_ = INVALID_HANDLE_VALUE;
    }
    connected_ = false;
}

NamedPipeClient::~NamedPipeClient() { close(); }

bool NamedPipeClient::connect(const std::string& pipeName, std::uint32_t timeoutMs) {
    const DWORD deadlineTick = ::GetTickCount() + timeoutMs;
    for (;;) {
        pipe_ = ::CreateFileA(pipeName.c_str(), GENERIC_READ | GENERIC_WRITE, 0, nullptr,
                              OPEN_EXISTING, FILE_FLAG_OVERLAPPED, nullptr);
        if (pipe_ != INVALID_HANDLE_VALUE) return true;

        const DWORD err = ::GetLastError();
        if (err != ERROR_FILE_NOT_FOUND && err != ERROR_PIPE_BUSY) return false;
        if (::GetTickCount() >= deadlineTick) return false;
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
}

bool NamedPipeClient::sendMessage(const Message& message) {
    if (pipe_ == INVALID_HANDLE_VALUE) return false;

    ScopedOverlapped scoped;
    if (scoped.overlapped.hEvent == nullptr) return false;

    const std::string encoded = encodeMessage(message);
    DWORD bytesWritten = 0;
    const BOOL immediate = ::WriteFile(pipe_, encoded.data(),
                                       static_cast<DWORD>(encoded.size()), &bytesWritten,
                                       &scoped.overlapped);
    if (immediate) return bytesWritten == encoded.size();

    const DWORD err = ::GetLastError();
    if (err != ERROR_IO_PENDING) return false;
    return waitOverlapped(pipe_, scoped.overlapped, 5000, bytesWritten) &&
           bytesWritten == encoded.size();
}

bool NamedPipeClient::receiveMessage(Message& out, std::uint32_t timeoutMs) {
    if (pipe_ == INVALID_HANDLE_VALUE) return false;

    ScopedOverlapped scoped;
    if (scoped.overlapped.hEvent == nullptr) return false;

    std::string buffer(kBufferSize, '\0');
    DWORD bytesRead = 0;
    const BOOL immediate = ::ReadFile(pipe_, buffer.data(),
                                      static_cast<DWORD>(buffer.size()), &bytesRead,
                                      &scoped.overlapped);
    if (!immediate) {
        const DWORD err = ::GetLastError();
        if (err != ERROR_IO_PENDING) return false;
        if (!waitOverlapped(pipe_, scoped.overlapped, timeoutMs, bytesRead)) return false;
    }

    buffer.resize(bytesRead);
    return decodeMessage(buffer, out);
}

void NamedPipeClient::close() {
    if (pipe_ != INVALID_HANDLE_VALUE) {
        ::CloseHandle(pipe_);
        pipe_ = INVALID_HANDLE_VALUE;
    }
}

}  // namespace maro::ipc
```

- [ ] **Step 5: 빌드에 등록**

`src/maro_ipc/CMakeLists.txt`의 `add_library(maro_ipc STATIC` 목록과 `tests/CMakeLists.txt`의 `add_executable(maro_ipc_tests` 목록에 각각 추가:

```cmake
    src/NamedPipe.cpp
```
```cmake
    ipc/test_named_pipe.cpp
```

`src/maro_ipc/CMakeLists.txt`의 `target_compile_features` 아래에 Windows 링크 라이브러리를 추가(명명된 파이프/이벤트 API):

```cmake
target_link_libraries(maro_ipc PUBLIC kernel32)
```

- [ ] **Step 6: 빌드하고 테스트가 통과하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R NamedPipe
```

기대: 3개 전부 통과.

- [ ] **Step 7: 끊김 감지가 진짜인지 확인**

`NamedPipeServer::receiveMessage`의 `if (!immediate) { ... if (err != ERROR_IO_PENDING) return false; ...}` 블록에서 `return false;`를 지우고 그냥 지나가게 만든다(끊김을 무시하고 빈 버퍼로 `decodeMessage`를 계속 시도).

```bash
cmake --build out/build --config Release && ctest --test-dir out/build -C Release --output-on-failure -R NamedPipe
```

기대: `ServerDetectsDisconnectWithoutMessage`가 멈추거나(무한 대기) 다르게 실패한다 — 어느 쪽이든 실패를 확인했으면 되돌린다. (이 단계는 붙어 있는 시간이 짧을 수 있으니 CI 타임아웃 안에서 실패로 끝나는지 확인하고, 5분을 넘기면 강제 중단 후 되돌린다.)

- [ ] **Step 8: 커밋**

```bash
git add src/maro_ipc tests/CMakeLists.txt tests/ipc/test_named_pipe.cpp
git commit -m "feat: talk over a message-mode named pipe, with every wait bounded"
```

---

### Task 6: job object 자가 점검과 1단계 탈출(breakaway)

**Files:**
- Create: `src/maro_ipc/include/maro_ipc/JobEscape.h`, `src/maro_ipc/src/JobEscape.cpp`
- Create: `tests/ipc/job_escape_test_helper.cpp` (새 실행 파일 타깃)
- Create: `tests/ipc/test_job_escape.cpp`
- Modify: `src/maro_ipc/CMakeLists.txt`, `tests/CMakeLists.txt`

**Interfaces:**
- Produces: `maro::ipc::isCurrentProcessInJob() -> bool`, `maro::ipc::spawnWithBreakaway(const std::string& exePath, const std::string& args) -> std::optional<PROCESS_INFORMATION>`(실패하면 `nullopt` — job이 breakaway를 막으면 `CreateProcess` 자체가 실패하므로 이 함수 수준에서 이미 tier 1의 성패가 갈린다)

**설계 메모.** `IsProcessInJob(GetCurrentProcess(), nullptr, &result)`으로 자기 상태를 묻는다. `CREATE_BREAKAWAY_FROM_JOB`은 호출한 프로세스(=플러그인=Maya)의 job이 `JOB_OBJECT_LIMIT_BREAKAWAY_OK`를 허용하지 않으면 `CreateProcess` 자체가 실패한다 — 그래서 "빠져나왔겠지"가 아니라 `CreateProcess`의 성패와 자식의 `IsProcessInJob` 자가 보고 둘 다로 "빠져나왔다"를 안다.

job object에 현재 테스트 프로세스 자신을 넣는 것은 위험하다(ctest가 띄운 프로세스 트리 전체에 영향을 줄 수 있다). 그래서 이 테스트는 **별도의 작은 도우미 실행 파일**을 만들어, 그 도우미가 스스로 제한적인 job(breakaway 불허)에 들어간 뒤 `spawnWithBreakaway`로 손자 프로세스를 띄우려 시도하고 결과를 종료 코드로 보고하게 한다. gtest는 이 도우미를 서브프로세스로 띄우고 종료 코드를 확인한다 — 위험한 job 조작이 gtest 프로세스 자체가 아니라 일회용 도우미 안에 격리된다.

- [ ] **Step 1: 도우미 실행 파일 작성**

`tests/ipc/job_escape_test_helper.cpp` (전체 새 파일):

```cpp
// 스스로 breakaway를 불허하는 job에 들어간 뒤, spawnWithBreakaway로
// 손자 프로세스를 띄우는 것이 실제로 거부되는지 확인하는 일회용 도우미.
// test_job_escape.cpp가 이것을 서브프로세스로 띄워 종료 코드를 읽는다 --
// 위험한 job 조작을 gtest 프로세스 자신이 아니라 여기에 격리한다.
//
// 종료 코드: 0 = 예상대로 거부됨(탈출 실패), 1 = 예상과 다르게 성공함
// (job이 breakaway를 막았어야 하는데 자식이 spawn됨), 2 = 설정 자체가 실패
// (job 생성/할당 실패 -- 이 머신의 권한 문제일 수 있어 테스트가 이 경우를
// 스킵으로 처리한다).
#include <windows.h>

#include <cstdio>

#include "maro_ipc/JobEscape.h"

int main() {
    HANDLE job = ::CreateJobObjectA(nullptr, nullptr);
    if (job == nullptr) {
        std::fprintf(stderr, "CreateJobObjectA failed: %lu\n", ::GetLastError());
        return 2;
    }

    JOBOBJECT_EXTENDED_LIMIT_INFORMATION info{};
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    // 일부러 JOB_OBJECT_LIMIT_BREAKAWAY_OK를 안 건다 -- 이 job은 탈출을 막는다.
    if (!::SetInformationJobObject(job, JobObjectExtendedLimitInformation, &info,
                                   sizeof(info))) {
        std::fprintf(stderr, "SetInformationJobObject failed: %lu\n", ::GetLastError());
        ::CloseHandle(job);
        return 2;
    }

    if (!::AssignProcessToJobObject(job, ::GetCurrentProcess())) {
        std::fprintf(stderr, "AssignProcessToJobObject failed: %lu\n", ::GetLastError());
        ::CloseHandle(job);
        return 2;
    }

    bool selfReportsInJob = maro::ipc::isCurrentProcessInJob();
    if (!selfReportsInJob) {
        std::fprintf(stderr, "isCurrentProcessInJob() false right after joining a job\n");
        ::CloseHandle(job);
        return 2;
    }

    char selfPath[MAX_PATH];
    ::GetModuleFileNameA(nullptr, selfPath, MAX_PATH);
    // 자기 자신을 --child로 다시 실행해 손자로 삼는다 -- 존재하는 실행
    // 파일이면 뭐든 되므로 새 바이너리를 안 만들어도 된다.
    const auto childInfo = maro::ipc::spawnWithBreakaway(selfPath, "--child");

    ::CloseHandle(job);

    if (childInfo.has_value()) {
        // 성공적으로 spawn됐다 -- 이 job은 애초에 breakaway를 허용하지
        // 않았으니 이 결과는 예상 밖이다(또는 이 Windows 버전/구성이 이
        // 제한을 다르게 다룬다는 뜻).
        ::TerminateProcess(childInfo->hProcess, 0);
        ::CloseHandle(childInfo->hProcess);
        ::CloseHandle(childInfo->hThread);
        return 1;
    }
    return 0;
}
```

이 파일이 `--child`로 재실행되는 경로도 처리해야 한다(위 `main`은 인자를 안 보므로 재실행된 손자도 그냥 같은 `main`을 돈다 — 그 손자는 job에 스스로 들어가지 않았으므로 `CreateJobObjectA`부터 다시 시도해 자기 job을 만들 뿐이고, 부모가 곧바로 `TerminateProcess`로 정리하므로 실질적인 부작용은 없다. 별도 분기 없이 그대로 둔다).

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/ipc/test_job_escape.cpp`:

```cpp
#include <gtest/gtest.h>

#include <windows.h>

#include <string>

#include "maro_ipc/JobEscape.h"

namespace {

TEST(JobEscape, CurrentProcessReportsNotInJobByDefault) {
    // ctest가 이 테스트 프로세스를 job 안에서 띄우지 않는 일반적인 경우를
    // 가정한다. (일부 CI 러너는 자기 프로세스 트리를 job으로 감싸기도
    // 하므로, 이 단언이 실제 환경에서 깨지면 테스트가 아니라 환경이
    // 다른 것이다 -- 그 경우 이 케이스는 스킵으로 바꿔도 된다.)
    EXPECT_FALSE(maro::ipc::isCurrentProcessInJob());
}

TEST(JobEscape, SpawnWithBreakawayFailsInsideARestrictiveJob) {
    char selfDir[MAX_PATH];
    ::GetModuleFileNameA(nullptr, selfDir, MAX_PATH);
    std::string helperPath = selfDir;
    const auto slash = helperPath.find_last_of("\\/");
    ASSERT_NE(slash, std::string::npos);
    helperPath = helperPath.substr(0, slash + 1) + "maro_job_escape_test_helper.exe";

    STARTUPINFOA startupInfo{};
    startupInfo.cb = sizeof(startupInfo);
    PROCESS_INFORMATION processInfo{};

    std::string commandLine = "\"" + helperPath + "\"";
    const BOOL created = ::CreateProcessA(
        nullptr, commandLine.data(), nullptr, nullptr, FALSE, 0, nullptr, nullptr,
        &startupInfo, &processInfo);
    ASSERT_TRUE(created) << "could not launch the job-escape test helper";

    const DWORD waitResult = ::WaitForSingleObject(processInfo.hProcess, 10000);
    ASSERT_EQ(waitResult, WAIT_OBJECT_0) << "helper did not exit within 10s";

    DWORD exitCode = 0;
    ::GetExitCodeProcess(processInfo.hProcess, &exitCode);
    ::CloseHandle(processInfo.hProcess);
    ::CloseHandle(processInfo.hThread);

    if (exitCode == 2) {
        GTEST_SKIP() << "helper could not set up its restrictive job on this machine "
                        "(likely a permissions/policy difference) -- not a maro_ipc bug";
    }
    EXPECT_EQ(exitCode, 0u)
        << "expected the breakaway spawn to be refused inside a job that disallows it, "
           "got exit code " << exitCode;
}

}  // namespace
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

```bash
ctest --test-dir out/build -C Release --output-on-failure -R JobEscape
```

기대: 컴파일 실패 — `maro_ipc/JobEscape.h`가 없다.

- [ ] **Step 4: `JobEscape.h` 작성**

`src/maro_ipc/include/maro_ipc/JobEscape.h`:

```cpp
#pragma once

#include <optional>
#include <string>

#include <windows.h>

namespace maro::ipc {

// 지금 이 프로세스가 job object 안에 있는가. 원 스펙 §5.1의 "빠져나왔겠지가
// 아니라 빠져나왔다를 안다"의 근거 -- 감시자가 기동 직후 이것으로 자기
// 상태를 확인해 파이프로 보고한다(Task 8).
bool isCurrentProcessInJob();

// CREATE_BREAKAWAY_FROM_JOB으로 spawn한다. 호출한 프로세스(플러그인)의
// job이 JOB_OBJECT_LIMIT_BREAKAWAY_OK를 허용하지 않으면 CreateProcess
// 자체가 실패해 nullopt를 돌려준다 -- "실패했다"를 알아내는 데 자식의
// 보고를 기다릴 필요가 없다. 성공하면 호출부가 handle을 닫을 책임을 진다
// (PROCESS_INFORMATION::hProcess/hThread).
std::optional<PROCESS_INFORMATION> spawnWithBreakaway(const std::string& exePath,
                                                        const std::string& args);

}  // namespace maro::ipc
```

- [ ] **Step 5: `JobEscape.cpp` 작성**

`src/maro_ipc/src/JobEscape.cpp`:

```cpp
#include "maro_ipc/JobEscape.h"

namespace maro::ipc {

bool isCurrentProcessInJob() {
    BOOL result = FALSE;
    if (!::IsProcessInJob(::GetCurrentProcess(), nullptr, &result)) {
        // 조회 자체가 실패하면 "모른다"를 "아니다"로 취급하지 않는다 --
        // 탈출 여부를 낙관적으로 판단하면 이 검사를 두는 의미가 없다.
        // 대신 "안전하지 않을 수 있다"는 쪽으로 true를 돌려준다.
        return true;
    }
    return result != FALSE;
}

std::optional<PROCESS_INFORMATION> spawnWithBreakaway(const std::string& exePath,
                                                        const std::string& args) {
    STARTUPINFOA startupInfo{};
    startupInfo.cb = sizeof(startupInfo);
    PROCESS_INFORMATION processInfo{};

    std::string commandLine = "\"" + exePath + "\"";
    if (!args.empty()) {
        commandLine += " " + args;
    }

    const BOOL created = ::CreateProcessA(
        exePath.c_str(),
        commandLine.data(),  // CreateProcessA가 이 버퍼를 수정할 수 있다 -- data()는 non-const.
        nullptr, nullptr, FALSE,
        CREATE_BREAKAWAY_FROM_JOB,
        nullptr, nullptr, &startupInfo, &processInfo);

    if (!created) return std::nullopt;
    return processInfo;
}

}  // namespace maro::ipc
```

- [ ] **Step 6: 빌드에 등록**

`src/maro_ipc/CMakeLists.txt`의 `add_library(maro_ipc STATIC` 목록에 추가:

```cmake
    src/JobEscape.cpp
```

`tests/CMakeLists.txt`에서, `maro_ipc_tests`를 정의하는 블록 뒤에 도우미 실행 파일과 그것을 쓰는 테스트를 추가(gtest 스위트가 아니라 별도 실행 파일이므로 `add_executable`을 따로 쓴다):

```cmake
add_executable(maro_job_escape_test_helper ipc/job_escape_test_helper.cpp)
target_link_libraries(maro_job_escape_test_helper PRIVATE maro_ipc)
```

`add_executable(maro_ipc_tests` 목록에 추가:

```cmake
    ipc/test_job_escape.cpp
```

`test_job_escape.cpp`가 도우미를 자기 실행 파일과 같은 디렉터리에서 찾으므로(`GetModuleFileNameA` 기준 상대 경로), `maro_ipc_tests`가 `maro_job_escape_test_helper`보다 먼저 빌드되지 않아도 되지만 같은 출력 디렉터리에 있어야 한다 — 둘 다 `tests/CMakeLists.txt`에서 정의되므로 기본적으로 같은 디렉터리에 놓인다. 추가 설정 불필요.

- [ ] **Step 7: 빌드하고 테스트가 통과하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R JobEscape
```

기대: 2개 전부 통과(또는 이 머신의 권한 정책에 따라 두 번째가 스킵 — 그것도 정상이다, Step 2의 도우미 코드 참고).

- [ ] **Step 8: 탈출 거부가 진짜인지 확인**

`job_escape_test_helper.cpp`에서 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`만 걸고 `JOB_OBJECT_LIMIT_BREAKAWAY_OK`도 함께 거는 것처럼 바꾼다(`info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_BREAKAWAY_OK;`).

```bash
cmake --build out/build --config Release && ctest --test-dir out/build -C Release --output-on-failure -R JobEscape
```

기대: `SpawnWithBreakawayFailsInsideARestrictiveJob`이 **실패**한다(도우미가 종료 코드 1을 내며 tier 1이 성공해 버린다 — 정확히 그 job이 이제 탈출을 허용하므로). 확인했으면 되돌린다.

- [ ] **Step 9: 커밋**

```bash
git add src/maro_ipc tests/CMakeLists.txt tests/ipc/job_escape_test_helper.cpp tests/ipc/test_job_escape.cpp
git commit -m "feat: know for certain whether the sentinel escaped Maya's job object"
```

---

### Task 7: WMI 우회 생성 (2단계 탈출)

**Files:**
- Modify: `src/maro_ipc/include/maro_ipc/JobEscape.h`, `src/maro_ipc/src/JobEscape.cpp`
- Modify: `tests/ipc/test_job_escape.cpp`

**Interfaces:**
- Produces: `maro::ipc::spawnViaWmi(const std::string& exePath, const std::string& args) -> std::optional<std::uint64_t>` (성공하면 생성된 프로세스의 PID)

**설계 메모.** 이것이 이 플랜에서 가장 위험도가 높은 태스크다 — COM/WMI는 이 프로젝트가 지금까지 한 번도 쓴 적 없는 API 계열이다. `CoInitializeEx` → `CoCreateInstance(CLSID_WbemLocator)` → `IWbemLocator::ConnectServer("ROOT\\CIMV2")` → `CoSetProxyBlanket`(호출 권한 설정, 이걸 빼먹으면 `ExecMethod`가 조용히 거부된다) → `IWbemServices::GetObject("Win32_Process")` → `GetMethod("Create")`로 in-parameter 클래스 얻기 → `SpawnInstance`로 파라미터 인스턴스 만들고 `CommandLine` 프로퍼티 채우기 → `ExecMethod("Create", ...)` → 결과 객체에서 `ProcessId`와 `ReturnValue` 꺼내기. 리뷰에서 이 태스크는 반드시 실제로 프로세스가 뜨는지(PID로 `OpenProcess`) 확인하고, `ReturnValue != 0`(WMI 호출은 성공했지만 프로세스 생성 자체는 실패한 경우)을 놓치지 않는지 특히 주의 깊게 봐야 한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/ipc/test_job_escape.cpp` 끝에 추가:

```cpp
TEST(JobEscape, SpawnViaWmiActuallyStartsAProcess) {
    // notepad.exe는 모든 Windows에 있고 창을 띄우지만 사용자 상호작용을
    // 요구하지 않는다 -- 뜨자마자 바로 종료시킨다.
    const auto pid = maro::ipc::spawnViaWmi("C:\\Windows\\System32\\notepad.exe", "");
    ASSERT_TRUE(pid.has_value());

    HANDLE process = ::OpenProcess(PROCESS_TERMINATE | PROCESS_QUERY_LIMITED_INFORMATION,
                                   FALSE, static_cast<DWORD>(*pid));
    ASSERT_NE(process, nullptr)
        << "spawnViaWmi reported PID " << *pid << " but no such process exists";

    DWORD exitCodeBeforeTerminate = 0;
    ::GetExitCodeProcess(process, &exitCodeBeforeTerminate);
    EXPECT_EQ(exitCodeBeforeTerminate, static_cast<DWORD>(STILL_ACTIVE));

    ::TerminateProcess(process, 0);
    ::CloseHandle(process);
}

TEST(JobEscape, SpawnViaWmiFailsCleanlyOnBogusPath) {
    const auto pid = maro::ipc::spawnViaWmi("C:\\this\\path\\does\\not\\exist.exe", "");
    EXPECT_FALSE(pid.has_value());
}
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
ctest --test-dir out/build -C Release --output-on-failure -R JobEscape
```

기대: 컴파일 실패 — `spawnViaWmi`가 없다.

- [ ] **Step 3: `JobEscape.h`에 선언 추가**

`src/maro_ipc/include/maro_ipc/JobEscape.h`의 `#include` 목록에 `#include <cstdint>`와 `#include <optional>`(이미 있음)을 확인하고, `spawnWithBreakaway` 선언 아래에 추가:

```cpp
// WMI Win32_Process::Create로 우회 생성한다. 이 경로로 만들어진 프로세스는
// Maya의 자식이 아니라 WMI 서비스(WinMgmt) 밑에서 만들어지므로 Maya의 job과
// 무관하다 -- CREATE_BREAKAWAY_FROM_JOB이 막혔을 때의 2단계 폴백. 같은
// 사용자 프로세스라 관리자 권한이 필요 없다. 실패(경로가 없거나, 생성
// 자체가 거부되거나)하면 nullopt.
std::optional<std::uint64_t> spawnViaWmi(const std::string& exePath, const std::string& args);
```

- [ ] **Step 4: `JobEscape.cpp`에 WMI 구현 추가**

`JobEscape.cpp` 상단에 추가:

```cpp
#include <comdef.h>
#include <wbemidl.h>

#pragma comment(lib, "wbemuuid.lib")
```

파일 끝에 추가:

```cpp
namespace {

// COM 인터페이스 포인터를 스코프 끝에서 자동으로 Release한다.
template <typename T>
struct ComPtr {
    T* ptr = nullptr;
    ~ComPtr() {
        if (ptr != nullptr) ptr->Release();
    }
    T** addressOf() { return &ptr; }
    T* operator->() const { return ptr; }
};

}  // namespace

std::optional<std::uint64_t> spawnViaWmi(const std::string& exePath, const std::string& args) {
    // CoInitializeEx를 이미 호출한 스레드(예: 다른 서브시스템이 COM을
    // 쓰는 경우)에서 다시 부르면 RPC_E_CHANGED_MODE가 날 수 있다 --
    // 그 경우도 "이미 초기화됨"으로 보고 계속 진행한다. 그 외 실패는
    // 진짜 실패다.
    const HRESULT initResult = ::CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    const bool weInitialized = SUCCEEDED(initResult);
    if (FAILED(initResult) && initResult != RPC_E_CHANGED_MODE) {
        return std::nullopt;
    }

    auto cleanupCom = [&]() {
        if (weInitialized) ::CoUninitialize();
    };

    ComPtr<IWbemLocator> locator;
    HRESULT hr = ::CoCreateInstance(CLSID_WbemLocator, nullptr, CLSCTX_INPROC_SERVER,
                                    IID_IWbemLocator,
                                    reinterpret_cast<LPVOID*>(locator.addressOf()));
    if (FAILED(hr)) {
        cleanupCom();
        return std::nullopt;
    }

    ComPtr<IWbemServices> services;
    hr = locator->ConnectServer(_bstr_t(L"ROOT\\CIMV2"), nullptr, nullptr, nullptr, 0,
                                nullptr, nullptr, services.addressOf());
    if (FAILED(hr)) {
        cleanupCom();
        return std::nullopt;
    }

    // 호출 권한을 명시적으로 설정한다 -- 이걸 빼먹으면 ExecMethod가
    // E_ACCESSDENIED로 조용히 거부되는 경우가 흔하다(잘 알려진 WMI 함정).
    hr = ::CoSetProxyBlanket(services.ptr, RPC_C_AUTHN_WINNT, RPC_C_AUTHZ_NONE, nullptr,
                             RPC_C_AUTHN_LEVEL_CALL, RPC_C_IMP_LEVEL_IMPERSONATE, nullptr,
                             EOAC_NONE);
    if (FAILED(hr)) {
        cleanupCom();
        return std::nullopt;
    }

    ComPtr<IWbemClassObject> processClass;
    hr = services->GetObject(_bstr_t(L"Win32_Process"), 0, nullptr,
                             processClass.addressOf(), nullptr);
    if (FAILED(hr)) {
        cleanupCom();
        return std::nullopt;
    }

    ComPtr<IWbemClassObject> inParamsDefinition;
    hr = processClass->GetMethod(L"Create", 0, inParamsDefinition.addressOf(), nullptr);
    if (FAILED(hr)) {
        cleanupCom();
        return std::nullopt;
    }

    ComPtr<IWbemClassObject> inParams;
    hr = inParamsDefinition->SpawnInstance(0, inParams.addressOf());
    if (FAILED(hr)) {
        cleanupCom();
        return std::nullopt;
    }

    std::string commandLine = "\"" + exePath + "\"";
    if (!args.empty()) commandLine += " " + args;

    // std::string(UTF-8/ANSI)를 WMI가 요구하는 BSTR(UTF-16)로 바꾼다.
    const int wideLen =
        ::MultiByteToWideChar(CP_UTF8, 0, commandLine.c_str(), -1, nullptr, 0);
    std::wstring wideCommandLine(wideLen, L'\0');
    ::MultiByteToWideChar(CP_UTF8, 0, commandLine.c_str(), -1, wideCommandLine.data(), wideLen);

    VARIANT commandLineVariant;
    ::VariantInit(&commandLineVariant);
    commandLineVariant.vt = VT_BSTR;
    commandLineVariant.bstrVal = ::SysAllocString(wideCommandLine.c_str());
    hr = inParams->Put(L"CommandLine", 0, &commandLineVariant, 0);
    ::VariantClear(&commandLineVariant);
    if (FAILED(hr)) {
        cleanupCom();
        return std::nullopt;
    }

    ComPtr<IWbemClassObject> outParams;
    hr = services->ExecMethod(_bstr_t(L"Win32_Process"), _bstr_t(L"Create"), 0, nullptr,
                              inParams.ptr, outParams.addressOf(), nullptr);
    if (FAILED(hr)) {
        cleanupCom();
        return std::nullopt;
    }

    // ExecMethod 자체의 성공은 "메서드가 실행됐다"는 뜻일 뿐이다.
    // ReturnValue가 진짜 결과다 -- 0이 아니면 프로세스 생성 자체가
    // 거부된 것이고(예: 경로 없음), 여기서 놓치면 존재하지 않는 PID를
    // "성공"으로 돌려주는 조용한 오판이 된다.
    VARIANT returnValue;
    ::VariantInit(&returnValue);
    hr = outParams->Get(L"ReturnValue", 0, &returnValue, nullptr, nullptr);
    const bool createSucceeded = SUCCEEDED(hr) && returnValue.vt == VT_I4 &&
                                 returnValue.lVal == 0;
    ::VariantClear(&returnValue);
    if (!createSucceeded) {
        cleanupCom();
        return std::nullopt;
    }

    VARIANT pidVariant;
    ::VariantInit(&pidVariant);
    hr = outParams->Get(L"ProcessId", 0, &pidVariant, nullptr, nullptr);
    std::optional<std::uint64_t> pid;
    if (SUCCEEDED(hr) && pidVariant.vt == VT_I4) {
        pid = static_cast<std::uint64_t>(pidVariant.lVal);
    }
    ::VariantClear(&pidVariant);

    cleanupCom();
    return pid;
}
```

- [ ] **Step 5: 빌드하고 테스트가 통과하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R JobEscape
```

기대: 4개 전부 통과(3번째 태스크의 두 번째 케이스는 여전히 스킵될 수 있음).

- [ ] **Step 6: `ReturnValue` 확인이 진짜로 걸리는지 확인**

`createSucceeded` 계산을 임시로 `const bool createSucceeded = SUCCEEDED(hr);`로 바꾼다(ReturnValue 값 자체는 무시).

```bash
cmake --build out/build --config Release && ctest --test-dir out/build -C Release --output-on-failure -R JobEscape
```

기대: `SpawnViaWmiFailsCleanlyOnBogusPath`가 **실패**한다(존재하지 않는 경로인데도 `pid.has_value()`가 true가 되려다 `ProcessId` 조회가 없어 어긋나거나, 최소한 이 테스트가 기대하는 nullopt가 깨진다). 확인했으면 되돌린다. 이 단계에서 예상과 다른 동작이 보이면(예: `ExecMethod` 자체가 이미 실패해서 이 변경이 아무 차이를 못 만드는 경우) 그 사실을 기록하고 `createSucceeded`의 원래 형태가 실질적으로 무엇을 막는지 주석으로 명확히 남긴다.

- [ ] **Step 7: 커밋**

```bash
git add src/maro_ipc tests/ipc/test_job_escape.cpp
git commit -m "feat: fall back to WMI process creation when job breakaway is blocked"
```

---

### Task 8: `maro_sentinel.exe` 메인 루프

**Files:**
- Create: `src/maro_sentinel/main.cpp`
- Create: `src/maro_sentinel/CMakeLists.txt`
- Modify: 최상위 `CMakeLists.txt`
- Create: `tests/ipc/test_sentinel_process.cpp`
- Modify: `tests/CMakeLists.txt`

**Interfaces:**
- Consumes: 이 플랜의 모든 이전 태스크(`Message`, `Naming`, `SentinelRecord`, `NamedMutexGuard`, `NamedPipeServer`, `isCurrentProcessInJob`)
- Produces: `maro_sentinel.exe` — 커맨드라인 인자로 소유자 Maya PID를 받는다(`maro_sentinel.exe <maya_pid>`)

**동작:**
1. 인자로 받은 Maya PID로 자기 이름들(파이프/뮤텍스/킬 이벤트/기록 파일)을 계산한다
2. `NamedMutexGuard`로 단일 인스턴스를 확보한다 — 못 얻으면 이미 같은 Maya PID의 감시자가 떠 있다는 뜻이므로 즉시 종료(코드 0)
3. `isCurrentProcessInJob()`을 확인해 기록 파일에 남긴다(이 정보는 Task 9에서 플러그인이 파이프로 물어보지 않고 기록 파일을 통해 비동기로 확인한다 — 접속 전에도 상태를 알 수 있게)
4. `SentinelRecord`를 쓴다(`sentinelPid`, `ownerMayaPid`, `startTimeMs`, `lastSessionEndedCleanly`는 아직 미설정)
5. `NamedPipeServer`를 열고 접속을 기다린다(타임아웃 있음 — 아무도 안 붙으면 좀비가 되지 않고 종료)
6. `HELLO`를 받는다
7. 메시지 루프: `SESSION_END_CLEAN`을 받거나, 연결이 끊기거나(메시지 없이), 킬 이벤트가 신호되거나, 절대 수명 타임아웃에 닿을 때까지 반복해서 `receiveMessage`를 짧은 타임아웃으로 부른다
8. 끝난 이유에 따라 `lastSessionEndedCleanly`를 기록 파일에 갱신하고 종료한다

**킬 스위치는 별도 스레드로 감시한다** — `receiveMessage`가 파이프에 블로킹하는 동안에도 킬 이벤트를 즉시 반응하려면, 파이프 대기와 킬 이벤트 대기를 같은 루프의 각 반복마다 짧은 타임아웃으로 번갈아 확인하는 것으로 충분하다(둘 다 몇백 ms 단위 폴링이면 충분히 빠르고, `WaitForMultipleObjects`로 파이프의 오버랩 이벤트와 킬 이벤트를 동시에 기다리는 것보다 `NamedPipeServer`의 기존 인터페이스를 그대로 쓸 수 있어 더 간단하다).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/ipc/test_sentinel_process.cpp` — 실제 `maro_sentinel.exe`를 서브프로세스로 띄워 정상/비정상 시나리오를 확인한다. mayapy가 필요 없다(플러그인 배선은 Task 9), 순수 클라이언트 역할만 gtest 프로세스가 직접 한다.

```cpp
#include <gtest/gtest.h>

#include <windows.h>

#include <chrono>
#include <filesystem>
#include <string>
#include <thread>

#include "maro_ipc/NamedPipe.h"
#include "maro_ipc/Naming.h"
#include "maro_ipc/SentinelRecord.h"

namespace {

std::filesystem::path freshBookDir(const std::string& name) {
    const std::filesystem::path dir =
        std::filesystem::temp_directory_path() / ("maro_sentinel_process_test_" + name);
    std::error_code ec;
    std::filesystem::remove_all(dir, ec);
    std::filesystem::create_directories(dir, ec);
    return dir;
}

std::string sentinelExePath() {
    char selfDir[MAX_PATH];
    ::GetModuleFileNameA(nullptr, selfDir, MAX_PATH);
    std::string path = selfDir;
    const auto slash = path.find_last_of("\\/");
    return path.substr(0, slash + 1) + "maro_sentinel.exe";
}

// gtest 프로세스 자신의 PID를 "소유자 Maya PID"로 사칭한다 -- 실제
// Maya는 필요 없다. 이 프로세스 자신은 확실히 살아 있으므로 명명
// 규칙이 요구하는 PID 하나만 있으면 충분하다.
std::uint64_t fakeMayaPid() { return ::GetCurrentProcessId(); }

PROCESS_INFORMATION spawnSentinel(const std::filesystem::path& bookDir) {
    std::string commandLine =
        "\"" + sentinelExePath() + "\" " + std::to_string(fakeMayaPid()) +
        " \"" + bookDir.string() + "\"";

    STARTUPINFOA startupInfo{};
    startupInfo.cb = sizeof(startupInfo);
    PROCESS_INFORMATION processInfo{};
    const BOOL created = ::CreateProcessA(nullptr, commandLine.data(), nullptr, nullptr,
                                          FALSE, 0, nullptr, nullptr, &startupInfo,
                                          &processInfo);
    EXPECT_TRUE(created) << "could not launch maro_sentinel.exe";
    return processInfo;
}

bool processIsRunning(DWORD pid) {
    HANDLE h = ::OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (h == nullptr) return false;
    DWORD exitCode = 0;
    const bool running = ::GetExitCodeProcess(h, &exitCode) && exitCode == STILL_ACTIVE;
    ::CloseHandle(h);
    return running;
}

}  // namespace

TEST(SentinelProcess, CleanSessionEndsAndSentinelExits) {
    const auto bookDir = freshBookDir("clean");
    PROCESS_INFORMATION sentinel = spawnSentinel(bookDir);

    maro::ipc::NamedPipeClient client;
    ASSERT_TRUE(client.connect(maro::ipc::pipeName(fakeMayaPid()), 5000));

    maro::ipc::Message hello;
    hello.type = maro::ipc::MessageType::Hello;
    ASSERT_TRUE(client.sendMessage(hello));

    maro::ipc::Message sessionEnd;
    sessionEnd.type = maro::ipc::MessageType::SessionEndClean;
    ASSERT_TRUE(client.sendMessage(sessionEnd));
    client.close();

    const DWORD waitResult = ::WaitForSingleObject(sentinel.hProcess, 5000);
    ASSERT_EQ(waitResult, WAIT_OBJECT_0) << "sentinel did not exit after a clean session end";

    maro::ipc::SentinelRecord record;
    const auto recordPath = maro::ipc::recordFilePath(bookDir, fakeMayaPid());
    ASSERT_TRUE(maro::ipc::readSentinelRecord(recordPath, record));
    // 정상 종료는 이 필드에 값을 남길 필요가 없다는 것이 설계 결정이다
    // (SentinelRecord.h 주석 참고) -- 값이 없다는 것 자체가 "판정할 비정상
    // 종료가 없었다"는 뜻이다.
    EXPECT_FALSE(record.lastSessionEndedCleanly.has_value());

    ::CloseHandle(sentinel.hProcess);
    ::CloseHandle(sentinel.hThread);
}

TEST(SentinelProcess, DisconnectWithoutSessionEndIsRecordedAsAbnormal) {
    const auto bookDir = freshBookDir("abnormal");
    PROCESS_INFORMATION sentinel = spawnSentinel(bookDir);

    {
        maro::ipc::NamedPipeClient client;
        ASSERT_TRUE(client.connect(maro::ipc::pipeName(fakeMayaPid()), 5000));
        maro::ipc::Message hello;
        hello.type = maro::ipc::MessageType::Hello;
        ASSERT_TRUE(client.sendMessage(hello));
        // SESSION_END_CLEAN 없이 바로 닫는다 -- 크래시한 Maya를 흉내낸다.
    }

    const DWORD waitResult = ::WaitForSingleObject(sentinel.hProcess, 5000);
    ASSERT_EQ(waitResult, WAIT_OBJECT_0)
        << "sentinel did not exit after detecting an abnormal disconnect";

    maro::ipc::SentinelRecord record;
    const auto recordPath = maro::ipc::recordFilePath(bookDir, fakeMayaPid());
    ASSERT_TRUE(maro::ipc::readSentinelRecord(recordPath, record));
    ASSERT_TRUE(record.lastSessionEndedCleanly.has_value());
    EXPECT_FALSE(*record.lastSessionEndedCleanly);

    ::CloseHandle(sentinel.hProcess);
    ::CloseHandle(sentinel.hThread);
}

TEST(SentinelProcess, NoConnectionEverArrivesSoSentinelExitsOnItsOwn) {
    // 아무도 접속하지 않으면 감시자가 좀비로 남으면 안 된다 -- 접속 대기
    // 타임아웃 자체가 좀비 방지의 한 축이다.
    const auto bookDir = freshBookDir("no_connection");
    PROCESS_INFORMATION sentinel = spawnSentinel(bookDir);

    // 감시자의 접속 대기 타임아웃보다 넉넉히 긴 시간을 기다린다.
    const DWORD waitResult = ::WaitForSingleObject(sentinel.hProcess, 20000);
    EXPECT_EQ(waitResult, WAIT_OBJECT_0)
        << "sentinel became a zombie waiting forever for a connection that never came";

    if (waitResult != WAIT_OBJECT_0) {
        ::TerminateProcess(sentinel.hProcess, 1);  // 테스트 스스로 뒷정리.
    }
    ::CloseHandle(sentinel.hProcess);
    ::CloseHandle(sentinel.hThread);
}
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
ctest --test-dir out/build -C Release --output-on-failure -R SentinelProcess
```

기대: 빌드 실패 — `maro_sentinel.exe` 타깃이 없다.

- [ ] **Step 3: `src/maro_sentinel/main.cpp` 작성**

```cpp
#include <windows.h>

#include <chrono>
#include <cstdio>
#include <filesystem>
#include <string>

#include "maro_ipc/JobEscape.h"
#include "maro_ipc/NamedMutexGuard.h"
#include "maro_ipc/NamedPipe.h"
#include "maro_ipc/Naming.h"
#include "maro_ipc/SentinelRecord.h"

namespace {

// 접속을 기다리는 시간. 이 안에 아무도 안 붙으면 좀비로 남지 않고
// 스스로 종료한다(원 스펙 §5.2 "절대 수명").
constexpr DWORD kConnectionTimeoutMs = 15000;
// 메시지 루프 한 바퀴의 대기 시간. 짧게 잡아 킬 이벤트 확인 주기를
// 촘촘히 유지한다 -- 이것이 "모든 대기에 타임아웃"을 만족시키는 지점이다.
constexpr DWORD kReceivePollMs = 500;
// 접속된 뒤 아무 메시지도 안 오는 채로(HELLO도 없이) 버틸 수 있는 최대
// 시간 -- 붙기만 하고 죽은 클라이언트에 대한 안전망.
constexpr DWORD kIdleAfterConnectMs = 30000;

std::uint64_t nowMs() {
    return static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch())
            .count());
}

void markAbnormalExit(const std::filesystem::path& recordPath, std::uint64_t sentinelPid,
                      std::uint64_t ownerPid, std::uint64_t startTimeMs) {
    maro::ipc::SentinelRecord record;
    record.sentinelPid = sentinelPid;
    record.ownerMayaPid = ownerPid;
    record.startTimeMs = startTimeMs;
    record.lastSessionEndedCleanly = false;
    maro::ipc::writeSentinelRecord(recordPath, record);
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 3) {
        std::fprintf(stderr, "usage: maro_sentinel.exe <owner_maya_pid> <book_dir>\n");
        return 1;
    }

    const std::uint64_t ownerPid = std::strtoull(argv[1], nullptr, 10);
    const std::filesystem::path bookDir = argv[2];
    const std::uint64_t sentinelPid = ::GetCurrentProcessId();
    const std::uint64_t startTimeMs = nowMs();

    // 좀비 방지: 명명된 뮤텍스로 단일 인스턴스. 이미 같은 Maya PID의
    // 감시자가 떠 있으면 조용히 종료한다 -- 에러가 아니다.
    maro::ipc::NamedMutexGuard instanceGuard(maro::ipc::mutexName(ownerPid), 1000);
    if (!instanceGuard.isAcquired()) {
        return 0;
    }

    const auto recordPath = maro::ipc::recordFilePath(bookDir, ownerPid);

    maro::ipc::SentinelRecord initialRecord;
    initialRecord.sentinelPid = sentinelPid;
    initialRecord.ownerMayaPid = ownerPid;
    initialRecord.startTimeMs = startTimeMs;
    // lastSessionEndedCleanly는 아직 미설정 -- 판정 전이라는 뜻.
    maro::ipc::writeSentinelRecord(recordPath, initialRecord);

    // job 자가 점검. 지금 이 골격 단계에서는 기록만 남긴다 -- 실제 판단
    // (탈출 실패 시 무엇을 할지)은 플러그인 쪽(Task 9)이 spawn 방식을
    // 고를 때 이미 내렸다. 감시자 자신의 self-check는 "빠져나왔겠지가
    // 아니라 빠져나왔다를 안다"를 만족시키는 확인일 뿐이다.
    const bool inJob = maro::ipc::isCurrentProcessInJob();
    (void)inJob;  // C-1은 이 사실을 파이프로 보고하지 않는다 -- 플러그인이
                  // spawn 성공 여부만으로 이미 판단을 마쳤기 때문이다. 이후
                  // 조각(C-2+)이 진단 용도로 쓸 수 있게 자리는 마련해 둔다.

    // 좀비 방지: 킬 스위치 이벤트. bManualReset=TRUE로 만들어 한 번
    // Set되면 계속 신호 상태로 남게 한다(폴링하는 쪽마다 개별로 리셋할
    // 필요 없음).
    HANDLE killEvent = ::CreateEventA(nullptr, TRUE, FALSE,
                                      maro::ipc::killEventName(ownerPid).c_str());

    maro::ipc::NamedPipeServer server(maro::ipc::pipeName(ownerPid));
    if (!server.waitForConnection(kConnectionTimeoutMs)) {
        // 아무도 안 붙었다 -- 좀비로 남지 않고 그냥 종료. 이 세션에 대해
        // 아무것도 몰랐으니 기록을 갱신할 것도 없다.
        if (killEvent != nullptr) ::CloseHandle(killEvent);
        return 0;
    }

    bool sawSessionEndClean = false;
    bool disconnected = false;
    const std::uint64_t connectedAtMs = nowMs();

    for (;;) {
        if (killEvent != nullptr &&
            ::WaitForSingleObject(killEvent, 0) == WAIT_OBJECT_0) {
            break;  // 킬 스위치 -- 판정 없이 즉시 종료.
        }

        maro::ipc::Message received;
        if (server.receiveMessage(received, kReceivePollMs)) {
            if (received.type == maro::ipc::MessageType::SessionEndClean) {
                sawSessionEndClean = true;
                break;
            }
            // HELLO류 다른 메시지는 계속 루프를 돈다.
            continue;
        }

        // receiveMessage가 false를 돌려주는 두 가지 경우: (1) 타임아웃 안에
        // 아무 메시지도 안 옴(연결은 살아 있음), (2) 연결이 끊김. 이 둘을
        // 구분하는 것은 이 골격 단계에서 절대 수명 타임아웃의 몫이다 --
        // 파이프가 끊겼으면 다음 receiveMessage 시도도 즉시 실패를
        // 반복하므로, 짧은 폴링 간격 자체가 사실상의 구분자가 된다. 다만
        // 오탐(살아있는데 계속 타임아웃)을 크래시로 잘못 판정하지 않기
        // 위해, 최대 유휴 시간을 넘겼을 때만 "연결 끊김"으로 취급한다.
        if (nowMs() - connectedAtMs > kIdleAfterConnectMs) {
            disconnected = true;
            break;
        }
        // 아직 유휴 한도 안이면 이 실패가 진짜 끊김인지 그냥 타임아웃인지
        // 다음 반복에서 다시 시도해 가른다 -- 진짜 끊김이면 이후 모든
        // 시도가 즉시 실패하므로 결국 위 유휴 한도에 걸린다. 단, 파이프가
        // 확실히 끊긴 상태(재시도해도 즉시 실패)라면 그 사실 자체를 더
        // 빨리 알아채는 편이 낫다 -- receiveMessage 내부에서 파이프
        // 핸들이 이미 무효가 되었는지까지는 이 골격이 구분하지 않는다.
    }

    if (killEvent != nullptr) ::CloseHandle(killEvent);
    server.close();

    if (sawSessionEndClean) {
        // 정상 종료 -- 판정을 남길 필요가 없다(SentinelRecord.h의 주석
        // 참고). 기록 파일은 초기 상태(미판정) 그대로 둔다.
        return 0;
    }

    // 여기 도달하면 SESSION_END_CLEAN 없이 연결이 끝났다(끊김이든 유휴
    // 한도 초과든) -- 감시자 입장에서 진짜 크래시와 구분되지 않는 신호다.
    markAbnormalExit(recordPath, sentinelPid, ownerPid, startTimeMs);
    return 0;
}
```

- [ ] **Step 4: `src/maro_sentinel/CMakeLists.txt` 작성**

```cmake
add_executable(maro_sentinel main.cpp)

target_link_libraries(maro_sentinel PRIVATE maro_ipc)
```

최상위 `CMakeLists.txt`의 `add_subdirectory(src/maro_ipc)` 아래에 추가:

```cmake
add_subdirectory(src/maro_sentinel)
```

- [ ] **Step 5: 테스트에 등록**

`tests/CMakeLists.txt`의 `add_executable(maro_ipc_tests` 목록에 추가:

```cmake
    ipc/test_sentinel_process.cpp
```

`maro_ipc_tests`가 `maro_sentinel.exe`의 경로를 찾으려면(`sentinelExePath()`) 둘이 같은 출력 디렉터리에 있어야 한다. 이 프로젝트가 멀티 컨피그 제너레이터이므로 `$<TARGET_FILE_DIR:target>`은 컨피그마다 다른 디렉터리를 가리킨다 — `maro_ipc_tests`와 `maro_sentinel`이 각자 다른 하위 디렉터리(예: `tests/Release/`와 `src/maro_sentinel/Release/`)에 놓이므로 **같은 디렉터리라는 가정이 성립하지 않는다.** `maro_ipc_tests` 타깃에 감시자 실행 파일 경로를 컴파일 타임 매크로로 넘긴다:

`tests/CMakeLists.txt`에서 `maro_ipc_tests` 정의 뒤에 추가:

```cmake
target_compile_definitions(maro_ipc_tests PRIVATE
    MARO_SENTINEL_EXE_PATH="$<TARGET_FILE:maro_sentinel>")
```

`test_sentinel_process.cpp`의 `sentinelExePath()` 함수를 아래로 교체:

```cpp
std::string sentinelExePath() { return MARO_SENTINEL_EXE_PATH; }
```

(이 교체는 Step 1에서 처음 작성한 버전을 고치는 것이다 — `GetModuleFileNameA` 기반 상대 경로 추정 대신 빌드 시스템이 정확한 경로를 알려주는 쪽이 멀티 컨피그에서 안전하다.)

- [ ] **Step 6: 빌드하고 테스트가 통과하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R SentinelProcess
```

기대: 3개 전부 통과. 실행 후 `Get-CimInstance Win32_Process -Filter "Name='maro_sentinel.exe'"`로 좀비가 없는지 확인한다.

- [ ] **Step 7: 비정상 판정이 진짜인지 확인**

`main.cpp`에서 `markAbnormalExit(...)` 호출을 지운다(비정상 종료를 감지해도 기록을 안 남긴다).

```bash
cmake --build out/build --config Release && ctest --test-dir out/build -C Release --output-on-failure -R SentinelProcess
```

기대: `DisconnectWithoutSessionEndIsRecordedAsAbnormal`이 **실패**한다(`readSentinelRecord`가 여전히 `has_value()==false`인 초기 기록을 읽음). 확인했으면 되돌린다.

- [ ] **Step 8: 커밋**

```bash
git add src/maro_sentinel CMakeLists.txt tests/CMakeLists.txt tests/ipc/test_sentinel_process.cpp
git commit -m "feat: assemble the sentinel's main loop from the pieces built so far"
```

---

### Task 9: 플러그인 배선

**Files:**
- Create: `src/maro_plugin/MaroSentinelClient.h`, `src/maro_plugin/MaroSentinelClient.cpp`
- Modify: `src/maro_plugin/MaroPluginMain.cpp`, `src/maro_plugin/MaroDiag.h`, `src/maro_plugin/MaroDiag.cpp`, `src/maro_plugin/CMakeLists.txt`

**Interfaces:**
- Consumes: `maro::ipc::NamedPipeClient`, `Message`, `Naming`, `spawnWithBreakaway`, `spawnViaWmi` (이전 태스크)
- Produces: `maro::MaroSentinelClient`(`static void connectOrSpawn()`, `static void notifyCleanExit()`, `static void shutdown()`), `maro::BoadMaro::bookDirectory() -> std::filesystem::path`(새 공개 접근자)

**spawn 3단계는 플러그인이 지휘한다(설계 스펙 §3.3):**
1. `CREATE_BREAKAWAY_FROM_JOB`으로 `maro_sentinel.exe`를 spawn(`spawnWithBreakaway`). 이 골격 단계에서는 **spawn 성공 자체를 tier 1 성공으로 친다** — `CreateProcess`가 breakaway를 거부하면 실패로 돌아오므로 그것으로 충분한 신호로 본다. (원래 근거였던 "감시자가 `inJob` 정보를 기록 파일에 남기지 않는다"는 이제 사실이 아니다: Task 8이 `SentinelRecord::sentinelInJob`을 추가해 감시자가 자기 self-check 결과를 실제로 기록한다. 그래도 **플러그인은 그 값을 읽지 않는다** — 필드는 있지만 소비하지 않는 것이 이 조각의 의도적 축소다.) 이 축소가 놓치는 경우는 하나다: 중첩 job에서 breakaway가 직속 job에 대해서만 성공하면 `CreateProcess`는 성공하는데 감시자는 여전히 바깥 조상 job 안에 남는다. 그 경우를 알아내려면 기록 파일의 `sentinelInJob`을 읽어 tier 2(WMI)로 승격해야 하며, 그 승격 로직은 이 플랜의 범위 밖이다
2. tier 1이 실패하면 `spawnViaWmi`
3. 그마저 실패하면 spawn을 포기한다. 파이프 접속도 시도하지 않는다 — 플러그인은 감시자 없이 그대로 진행한다(기존 저널이 이미 항상 돌고 있다)

**이 태스크는 "플러그인 로드 시 자가 점검"(설계 스펙 §3.4, 낡은 PID 기록 파일을 보고 정리하거나 킬 스위치를 울리는 것)을 구현하지 않는다 — 의도적 축소다, 빠뜨린 게 아니다.** Task 8의 `NamedMutexGuard`가 `WAIT_ABANDONED`를 정상 획득으로 취급하므로(옛 감시자가 뮤텍스를 놓지 않고 죽어도 새 감시자가 정상적으로 얻어 낡은 기록 파일을 그냥 덮어쓴다), 이미 죽은 프로세스의 낡은 파일은 자가 점검 없이도 안전하게 정리된다. 킬 스위치가 실제로 필요한 경우(같은 PID가 재사용됐는데 다른 감시자가 진짜로 살아 있는, 극히 드문 경우)도 지금 상태(새 spawn 시도가 뮤텍스를 못 얻어 조용히 물러남)로 안전하다 — 최적은 아니지만 위험하지 않다. `killEventName`과 감시자의 폴링(Task 8)은 다음 조각이 쓸 수 있는 인프라로 남겨 둔다. (스펙 §3.4에 이 결정을 기록해 뒀다.)

- [ ] **Step 1: `MaroSentinelClient.h` 작성**

```cpp
#pragma once

namespace maro {

// 플러그인 쪽에서 감시자와의 관계를 관리하는 정적 클래스. 로드 시
// connectOrSpawn(), 정상 언로드 시 notifyCleanExit() 다음 shutdown()을
// 부른다. 이 클래스의 어떤 실패도 예외를 던지지 않는다 -- 감시자가
// 없어도 플러그인 기능은 그대로 돈다는 설계 스펙 §3.5의 규율.
class MaroSentinelClient {
public:
    // 이미 접속돼 있으면 아무 일도 안 한다. 처음 부르면 3단계 spawn을
    // 시도하고 성공하면 파이프에 접속해 HELLO를 보낸다. 전부 실패해도
    // 아무 예외 없이 조용히 반환한다.
    static void connectOrSpawn();

    // SESSION_END_CLEAN을 보낸다. 접속돼 있지 않으면 아무것도 안 한다.
    static void notifyCleanExit();

    // 파이프를 닫는다. uninitializePlugin 마지막에 부른다.
    static void shutdown();
};

}  // namespace maro
```

- [ ] **Step 2: `MaroDiag`에 book 디렉터리 공개 접근자 추가**

`MaroSentinelClient`가 감시자에게 넘길 book 디렉터리를 알아야 하는데, 그 해석 로직(`journalDirectory()`/`bookPaths()`)은 지금 `MaroDiag.cpp`의 익명 네임스페이스 안에 갇혀 있다 — 이미 저널이 정확히 같은 디렉터리를 재사용하려고 `journalDirectory()`를 만들어 둔 바로 그 자리다. 이 로직을 또 다른 곳에서 다시 구현하면(예: `MaroSentinelClient.cpp`가 `MARO_DIAG_BOOK_DIR` 환경변수를 직접 읽고 그걸로 끝내면) 실제 사용자 세션(그 환경변수가 없는 게 정상인 환경)에서는 조용히 아무 디렉터리도 못 찾아 감시자가 테스트 환경 밖에서는 절대 안 뜨는 결함이 된다. 그래서 이미 있는 해석 결과를 공개 접근자 하나로 노출한다.

`src/maro_plugin/MaroDiag.h`의 `static void resetForTest();` 선언 위에 추가:

```cpp
    // 이 세션이 book/저널에 쓰는 디렉터리. journalDirectory()(MaroDiag.cpp)의
    // 이미 해소된 결과를 그대로 돌려준다 -- MARO_DIAG_BOOK_DIR 환경변수
    // 해석이든 internalVar -userAppDir 해석이든 여기서 다시 하지 않는다.
    // 감시자를 spawn할 때 같은 디렉터리를 넘겨야 하는 MaroSentinelClient.cpp를
    // 위해 존재한다. 실패할 수 없다 -- markMainThread()가 이미 지연
    // 초기화를 끝내 둔 값을 읽을 뿐이다.
    static std::filesystem::path bookDirectory();
```

`MaroDiag.h`의 `#include` 목록에 `#include <filesystem>`이 없으면 추가한다.

`src/maro_plugin/MaroDiag.cpp`의 `journalDirectory()` 함수 정의 아래에 추가:

```cpp
std::filesystem::path BoadMaro::bookDirectory() {
    return journalDirectory();
}
```

- [ ] **Step 3: `MaroSentinelClient.cpp` 작성**

```cpp
#include "MaroSentinelClient.h"

#include <windows.h>

#include <filesystem>
#include <string>

#include "maro_ipc/JobEscape.h"
#include "maro_ipc/Message.h"
#include "maro_ipc/NamedPipe.h"
#include "maro_ipc/Naming.h"

#include "MaroDiag.h"

namespace maro {

namespace {

maro::ipc::NamedPipeClient& clientInstance() {
    static maro::ipc::NamedPipeClient client;
    return client;
}

bool& connectedFlag() {
    static bool connected = false;
    return connected;
}

// 저널과 같은 디렉터리를 쓴다 -- MaroDiag.cpp의 bookPaths()가 이미
// 해소해 둔 경로를 그대로 물려받는다. 감시자 실행 파일은 플러그인
// (maro.mll)과 같은 디렉터리에 있다고 가정한다(CMake가 그렇게 배치한다,
// Task 9 Step 4 참고).
std::filesystem::path sentinelExeDirectory() {
    char modulePath[MAX_PATH];
    HMODULE thisModule = nullptr;
    ::GetModuleHandleExA(
        GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCSTR>(&sentinelExeDirectory), &thisModule);
    if (thisModule == nullptr) return {};
    ::GetModuleFileNameA(thisModule, modulePath, MAX_PATH);
    return std::filesystem::path(modulePath).parent_path();
}

bool spawnSentinel(std::uint64_t ownerPid, const std::filesystem::path& bookDir) {
    const std::filesystem::path exePath = sentinelExeDirectory() / "maro_sentinel.exe";
    const std::string args = std::to_string(ownerPid) + " \"" + bookDir.string() + "\"";

    if (const auto tier1 = maro::ipc::spawnWithBreakaway(exePath.string(), args);
        tier1.has_value()) {
        ::CloseHandle(tier1->hProcess);
        ::CloseHandle(tier1->hThread);
        return true;
    }
    if (const auto tier2 = maro::ipc::spawnViaWmi(exePath.string(), args); tier2.has_value()) {
        return true;
    }
    return false;
}

}  // namespace

void MaroSentinelClient::connectOrSpawn() {
    if (connectedFlag()) return;

    try {
        const std::uint64_t ownerPid = ::GetCurrentProcessId();
        // 저널과 정확히 같은 디렉터리를 쓴다 -- BoadMaro::bookDirectory()가
        // journalDirectory()/bookPaths()의 이미 해소된 결과를 그대로
        // 돌려준다(Step 2에서 추가한 공개 접근자). 이 함수가 book 경로
        // 해석 규칙(MARO_DIAG_BOOK_DIR 환경변수 우선, 없으면 internalVar
        // -userAppDir)을 다시 구현하지 않는다 -- 두 곳에서 각자 해석하면
        // 저널이 겪었던 "우연히만 맞아떨어지던 두 번째 정의" 함정이
        // 재발한다. 실환경(테스트가 아닌 실제 사용자 세션)에는
        // MARO_DIAG_BOOK_DIR가 없는 것이 정상이므로, 이 호출이 그 경우도
        // internalVar -userAppDir로 알아서 해소해야 감시자가 테스트
        // 환경에서만 spawn되는 게 아니라 실제로 동작한다.
        const std::filesystem::path bookDir = maro::BoadMaro::bookDirectory();
        if (bookDir.empty()) return;

        if (!spawnSentinel(ownerPid, bookDir)) return;

        if (!clientInstance().connect(maro::ipc::pipeName(ownerPid), 5000)) return;

        maro::ipc::Message hello;
        hello.type = maro::ipc::MessageType::Hello;
        if (!clientInstance().sendMessage(hello)) {
            clientInstance().close();
            return;
        }
        connectedFlag() = true;
    } catch (...) {
        // 감시자 연결 실패는 플러그인 기능을 막지 않는다.
    }
}

void MaroSentinelClient::notifyCleanExit() {
    if (!connectedFlag()) return;
    try {
        maro::ipc::Message sessionEnd;
        sessionEnd.type = maro::ipc::MessageType::SessionEndClean;
        clientInstance().sendMessage(sessionEnd);
    } catch (...) {
    }
}

void MaroSentinelClient::shutdown() {
    try {
        clientInstance().close();
    } catch (...) {
    }
    connectedFlag() = false;
}

}  // namespace maro
```

- [ ] **Step 4: 빌드에 등록**

`src/maro_plugin/CMakeLists.txt`의 `SOURCE_FILES` 목록에 추가:

```cmake
    MaroSentinelClient.cpp
```

`build_plugin()` 호출 뒤의 `target_link_libraries(${PROJECT_NAME} maro_diag)` 아래에 추가:

```cmake
target_link_libraries(${PROJECT_NAME} maro_ipc)
```

**감시자 실행 파일을 플러그인 옆에 배치한다.** `MaroSentinelClient.cpp`의 `sentinelExeDirectory()`가 플러그인과 같은 디렉터리에서 `maro_sentinel.exe`를 찾으므로, `src/maro_plugin/CMakeLists.txt`의 python 패널 스테이징 블록(`MARO_DIAG_PANEL_PY_OUT`) 아래에 같은 방식으로 추가한다:

```cmake
# 감시자 실행 파일을 플러그인 옆에 둔다. MaroSentinelClient.cpp가 자기
# 모듈(.mll) 경로 기준으로 그 디렉터리에서 maro_sentinel.exe를 찾는다.
# 위 maroDiagPanel.py 스테이징과 같은 이유로 add_custom_command(OUTPUT ...)
# + add_dependencies를 쓴다 -- POST_BUILD 대신 써야 컨피그가 바뀌어도
# (Debug/Release) 매번 정확한 위치에 복사된다.
set(MARO_SENTINEL_EXE_OUT "$<TARGET_FILE_DIR:${PROJECT_NAME}>/maro_sentinel.exe")
add_custom_command(
    TARGET ${PROJECT_NAME} POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "$<TARGET_FILE:maro_sentinel>" "${MARO_SENTINEL_EXE_OUT}"
    COMMENT "Copying maro_sentinel.exe next to the plug-in")
add_dependencies(${PROJECT_NAME} maro_sentinel)
```

**주의:** 이 `POST_BUILD` 방식은 `maro_sentinel.cpp`만 바뀌고 플러그인 쪽 소스가 안 바뀌면 relink가 안 일어나 복사도 스킵될 수 있다(이 파일이 이미 겪은 "I9" 함정과 같은 모양). 이 플랜에서는 두 타깃이 거의 항상 같은 태스크들 안에서 함께 바뀌므로 당장은 허용하되, 최종 리뷰에서 이 스테일 배포 위험을 반드시 짚는다.

- [ ] **Step 5: `MaroPluginMain.cpp`에 `SentinelGuard`와 훅 추가**

`#include` 목록에 추가:

```cpp
#include "MaroSentinelClient.h"
```

`MainThreadQueueGuard` 구조체 아래에 추가:

```cpp
// 저널/큐와 같은 이유로 가드를 쓴다 -- 이 함수를 어떤 경로로 빠져나가든
// 파이프를 반드시 닫는다.
struct SentinelGuard {
    ~SentinelGuard() { maro::MaroSentinelClient::shutdown(); }
};
```

`initializePlugin`의 `maro::BoadMaro::openJournal();` 바로 아래에 추가:

```cpp
    // 감시자 spawn/접속은 실패해도 로드를 막지 않는다 -- 함수 내부가
    // 스스로 그 규율을 지킨다(MaroSentinelClient.cpp).
    maro::MaroSentinelClient::connectOrSpawn();
```

`uninitializePlugin`의 `const MainThreadQueueGuard queueGuardOnExit;` 바로 아래에 추가:

```cpp
    const SentinelGuard sentinelGuardOnExit;
```

`uninitializePlugin`의 `try` 블록 맨 앞(`MFnPlugin plugin(obj);` 바로 다음)에 추가:

```cpp
        // 언로드가 시작됐다는 것 자체가 "정상 종료 경로에 들어왔다"는
        // 뜻이다 -- 아래에서 무엇이 실패하든 이 신호는 이미 보내는 게
        // 맞다. closeJournal()이 그렇듯, 감시자에게도 "이 세션은 의도적
        // 종료였다"를 최대한 일찍 알린다.
        maro::MaroSentinelClient::notifyCleanExit();
```

- [ ] **Step 6: 빌드가 되는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

이 태스크는 새 gtest가 없다 — 다음 태스크(mayapy 종단 테스트)가 이 배선을 실제로 검증한다. 빌드 성공과 `out/build/src/maro_plugin/Release/maro_sentinel.exe`가 실제로 생겼는지 확인한다.

```powershell
Test-Path "out/build/src/maro_plugin/Release/maro_sentinel.exe"
```

기대: `True`.

- [ ] **Step 7: 커밋**

```bash
git add src/maro_plugin/MaroSentinelClient.h src/maro_plugin/MaroSentinelClient.cpp src/maro_plugin/MaroDiag.h src/maro_plugin/MaroDiag.cpp src/maro_plugin/MaroPluginMain.cpp src/maro_plugin/CMakeLists.txt
git commit -m "feat: have the plugin spawn, talk to, and cleanly release its own sentinel"
```

---

### Task 10: 종단 mayapy 통합 테스트

**Files:**
- Create: `tests/maya/test_sentinel.py`
- Modify: `tests/CMakeLists.txt`

**Interfaces:**
- Consumes: 이 플랜의 전체 배선 (Task 9)

**시나리오 (`test_journal.py`의 여러-프로세스 오케스트레이션 패턴을 그대로 따른다):**
1. **정상 세션**: mayapy 자식 하나가 플러그인을 로드(감시자 spawn 확인)하고 정상 언로드한다. 오케스트레이터가 그 자식의 기록 파일을 읽어 감시자 PID를 얻고, 자식이 끝난 뒤 그 PID가 더 이상 안 돈다는 것을 확인한다
2. **비정상 세션**: mayapy 자식이 플러그인을 로드한 뒤 `os._exit()`로 끊는다(`test_journal.py`의 crash1과 같은 패턴). 오케스트레이터가 기록 파일의 `lastSessionEndedCleanly == false`를 확인하고, 감시자 프로세스도 좀비로 안 남는 것을 확인한다
3. **좀비 없음**: 전체 스위트 종료 후 `maro_sentinel.exe` 프로세스가 하나도 안 남는지 확인한다

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/maya/test_sentinel.py` (전체 새 파일):

```python
"""플러그인이 감시자를 spawn하고, 정상/비정상 종료를 감시자가 구분해
기록 파일에 남기는지 여러 프로세스로 확인한다.

test_journal.py와 같은 이유로 여러 프로세스다 -- 감시자의 존재 이유가
"프로세스가 죽어도 남는 관측"이므로, 크래시 세션은 정상 종료 줄을 쓰기
전에 스스로를 끊는다.
"""
import json
import os
import subprocess
import sys
import time

import maya.standalone  # noqa: F401 (mayapy 표준 임포트 순서를 따름 -- 실제 사용은 run_as_session에서)

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


def sentinel_record_path(bookDir, pid):
    return os.path.join(bookDir, f"maro_sentinel.{pid}.json")


def wait_for_file(path, timeoutSeconds):
    deadline = time.time() + timeoutSeconds
    while time.time() < deadline:
        if os.path.exists(path):
            return True
        time.sleep(0.1)
    return False


def process_is_running(pid):
    # tasklist는 이 저장소가 이미 다른 곳(memo, 리뷰 코멘트)에서 좀비 확인에
    # 쓰는 것과 같은 표준 도구다. PowerShell Get-CimInstance를 여기서 또
    # 부르는 대신 subprocess로 tasklist를 쓰는 이유는 이 파일이 순수
    # Python이라 PowerShell 호출 오버헤드를 피하기 위해서다.
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
        capture_output=True, text=True,
    )
    return str(pid) in result.stdout


def orchestrate():
    env = os.environ.copy()
    bookDir = env["MARO_DIAG_BOOK_DIR"]
    os.makedirs(bookDir, exist_ok=True)

    # --- 정상 세션 ---
    rc1, out1 = run_session("clean", env)
    print("---- clean session ----")
    print(out1)
    assert rc1 == 0, f"clean session failed with exit code {rc1}"

    # 자식이 자기 PID를 stdout에 마지막 줄로 남긴다(아래 run_as_session).
    childPid = int(out1.strip().splitlines()[-1])
    recordPath = sentinel_record_path(bookDir, childPid)
    assert wait_for_file(recordPath, 10), (
        f"sentinel never wrote its record file at {recordPath}"
    )
    with open(recordPath, encoding="utf-8") as f:
        record = json.load(f)
    assert "lastSessionEndedCleanly" not in record, (
        "a clean session must leave the field unset, not write true -- "
        f"got {record}"
    )
    sentinelPid = record["sentinelPid"]

    # 감시자가 정상 종료 신호를 받으면 스스로 종료한다 -- 자식 프로세스가
    # 이미 끝났으므로(run_session이 기다렸다) 감시자도 곧 뒤따라 종료해야
    # 한다. 약간의 여유를 준다.
    deadline = time.time() + 10
    while time.time() < deadline and process_is_running(sentinelPid):
        time.sleep(0.2)
    assert not process_is_running(sentinelPid), (
        f"sentinel (pid {sentinelPid}) did not exit after its Maya's clean shutdown"
    )
    print("clean session: sentinel recorded no verdict and exited on its own OK")

    # --- 비정상 세션 ---
    rc2, out2 = run_session("crash", env)
    print("---- crash session ----")
    print(out2)
    assert rc2 != 0, "crash session is supposed to die abnormally, not exit cleanly"

    crashChildPid = int(out2.strip().splitlines()[-1])
    crashRecordPath = sentinel_record_path(bookDir, crashChildPid)
    assert wait_for_file(crashRecordPath, 10), (
        f"sentinel never wrote its record file for the crashed session at {crashRecordPath}"
    )
    with open(crashRecordPath, encoding="utf-8") as f:
        crashRecord = json.load(f)
    assert crashRecord.get("lastSessionEndedCleanly") is False, (
        f"a session that died without SESSION_END_CLEAN must be recorded as "
        f"abnormal, got {crashRecord}"
    )
    crashSentinelPid = crashRecord["sentinelPid"]

    deadline = time.time() + 10
    while time.time() < deadline and process_is_running(crashSentinelPid):
        time.sleep(0.2)
    assert not process_is_running(crashSentinelPid), (
        f"sentinel (pid {crashSentinelPid}) became a zombie after detecting the crash"
    )
    print("crash session: sentinel recorded the abnormal exit and exited on its own OK")


def run_as_session(label):
    maya.standalone.initialize(name="python")

    import maya.cmds as cmds  # noqa: E402

    plugin = os.environ["MARO_PLUGIN_PATH"]
    cmds.loadPlugin(plugin)
    cmds.file(new=True, force=True)

    # 감시자가 실제로 spawn을 시도할 시간을 준다 -- connectOrSpawn()은
    # initializePlugin 안에서 동기적으로 접속까지 마치므로 이 시점에는
    # 이미 끝나 있어야 정상이지만, 느린 머신을 위한 여유를 조금 둔다.
    time.sleep(0.5)

    ownPid = os.getpid()

    if label == "clean":
        cmds.file(new=True, force=True)
        cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
        maya.standalone.uninitialize()
        # 오케스트레이터가 자기 PID로 감시자 기록 파일을 찾을 수 있게
        # 마지막 줄에 PID를 남긴다.
        print(ownPid)
        return

    if label == "crash":
        sys.stdout.flush()
        os._exit(3)  # uninitializePlugin을 안 돌린다 -- SESSION_END_CLEAN 없음.

    raise ValueError(f"unknown session label {label!r}")


if __name__ == "__main__":
    sessionArg = next((a for a in sys.argv[1:] if a.startswith("--session=")), None)
    if sessionArg is None:
        orchestrate()
        sys.exit(0)
    run_as_session(sessionArg.split("=", 1)[1])
    # "crash" 경로는 os._exit로 여기 도달하지 않는다. "clean" 경로는 이미
    # 위에서 자기 PID를 찍고 return했다 -- 여기 추가로 다시 안 찍는다.
```

**주의: `os._exit(3)` 직전에도 자식의 PID를 오케스트레이터가 알아야 한다.** 위 스케치는 "clean" 경로에서만 PID를 stdout에 찍는데, "crash" 경로는 `os._exit()`가 그 출력 기회를 없앤다. `run_as_session`의 `"crash"` 분기를 아래로 교체해서 **os._exit 전에** PID를 찍는다:

```python
    if label == "crash":
        print(ownPid)
        sys.stdout.flush()
        os._exit(3)
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```powershell
& "$env:MAYA_LOCATION\bin\mayapy.exe" tests\maya\test_sentinel.py
```

기대: `MARO_PLUGIN_PATH` 등 환경변수가 없어 바로 실패하거나(직접 실행 시), CMake에 등록하기 전이라 ctest로는 아직 안 돈다. 이 태스크의 코드 자체는 Task 9까지 끝나 있으면 이미 동작할 수 있는 배선이므로, "실패"는 주로 "아직 CMake 테스트 목록에 없다"는 뜻이다 — 목적은 이 스크립트를 처음 직접 실행했을 때 위 세 단언이 실제로 통과하는지 손으로 먼저 확인하는 것이다. `MARO_PLUGIN_PATH`, `MARO_DIAG_BOOK_DIR`를 직접 설정하고 실행해본다.

- [ ] **Step 3: CMake에 등록**

`tests/CMakeLists.txt`의 `foreach(maya_test ...)` 목록에 `sentinel`을 추가:

```cmake
    foreach(maya_test load axis_node binding capability_stack delete_rules
                      robustness diag_boad diag_onfix diag_book
                      diag_book_cross_session diag_remedy
                      diag_degraded diag_degraded_remedy diag_thread
                      panel_commands journal remedy_capture
                      remedy_availability remedy_ambiguous_names
                      main_thread_queue remedy_apply sentinel)
```

- [ ] **Step 4: 빌드하고 테스트가 통과하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R maya_sentinel
```

기대: 통과.

- [ ] **Step 5: 비정상 판정이 종단으로 진짜인지 확인**

`MaroSentinelClient.cpp`의 `notifyCleanExit()` 본문을 임시로 비운다(정상 종료 신호를 절대 안 보내게 만든다 — "clean" 세션이 실제로는 비정상으로 잘못 기록되는지 보는 역파괴 테스트다).

```bash
cmake --build out/build --config Release && ctest --test-dir out/build -C Release --output-on-failure -R maya_sentinel
```

기대: `clean session` 검증에서 **실패**한다(`"lastSessionEndedCleanly" not in record` 단언이 깨짐 — 이제 false가 기록됨). 확인했으면 되돌린다.

- [ ] **Step 6: 전체 스위트가 여전히 통과하는지 확인, 좀비 확인**

```bash
ctest --test-dir out/build -C Release --output-on-failure
```

기대: `maya_panel_commands`(사전 결함) 하나만 빼고 전부 통과.

```powershell
Get-CimInstance Win32_Process -Filter "Name='maro_sentinel.exe'"
```

기대: 빈 결과.

- [ ] **Step 7: 커밋**

```bash
git add tests/maya/test_sentinel.py tests/CMakeLists.txt
git commit -m "test: prove the sentinel survives real load/unload and crash across processes"
```

## 완료 기준

- `ctest --test-dir out/build -C Release --output-on-failure` 전부 통과(`maya_panel_commands` 사전 결함 하나만 예외)
- 정상 종료 시 감시자가 판정 없이 스스로 종료한다
- `SESSION_END_CLEAN` 없이 연결이 끊기면 감시자가 그것을 기록 파일에 남기고 스스로 종료한다
- 감시자가 없거나 spawn에 실패해도 플러그인 로드는 절대 막히지 않는다
- 각 테스트 종료 후 `maro_sentinel.exe`가 하나도 안 남는다
- `book`/`offix`/`ghost`/`OSbridge`/부스러기 스트림은 이 플랜의 어떤 태스크도 만들지 않는다
