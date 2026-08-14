# Maro 트러블슈팅 생태계 — Layer A 진단 기반 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 감시자 프로세스도 패널도 없이, 플러그인 하나만으로 세 가지를 사용자에게 준다 — 원인까지 붙은 진단(`onfix`), 같은 에러의 즉답(`book`), 그리고 쓸수록 쌓이는 지식. 이 세 가지는 `boad`라는 단일 출구를 거쳐 나간다.

**Architecture:** `maro_transform`이 세운 전례를 그대로 따른다 — Maya에 의존하지 않는 로직은 `src/maro_diag/`에 두어 gtest로 수 초 안에 검증하고, Maya 없이는 존재할 수 없는 부분(스크립트 에디터 출력, DG 조회, `MPxCommand` 생명주기)만 `src/maro_plugin/`에 둔다. `boad`가 진단의 유일한 출구다: 모든 info/warn/devInfo/error가 여기를 거치고, 에러는 여기서 `book`을 먼저 조회한다. `onfix`는 `MPxCommand::doIt`마다 설치되는 RAII 마커로 "지금 어느 커맨드가 도는가"를 알아내고, 호출부가 건네는 노드·어트리뷰트·축 정보와 합쳐 구조화된 DG 컨텍스트를 만든다. `book`은 정본(향후 감시자 전용 쓰기)과 스필(지금 플러그인이 유일하게 쓸 수 있는 통로)로 나뉘고, 읽을 때는 항상 둘을 병합한다.

**Tech Stack:** C++17, Maya 2026 devkit, CMake + Ninja, vcpkg, GoogleTest, nlohmann-json (book 파일 포맷)

**Scope:** 이 플랜은 스펙 `docs/superpowers/specs/2026-08-14-maro-troubleshooting-ecosystem-design.md`의 세 계층 중 **Layer A(인프로세스 진단 기반)만** 다룬다. 감시자 프로세스, `offix`(크래시 딥디버깅), `ghost`(셧다운 대비·조립), `OSbridge`, 진단 패널(UI), 해법 **적용**(auto-fix)은 전부 별도 플랜(Layer B, C)이다. 이 플랜이 끝나면 사용자는 원인 분석과 즉답과 해법 *제시*를 얻는다 — 해법을 버튼으로 *적용*하는 것은 아니다.

## Global Constraints

설계 스펙의 전 Layer A 요구사항. 모든 태스크에 암묵적으로 적용된다.

- **감시자 없이도 동작 (스펙 §3.6).** 감시자는 Layer A에 아예 없다. 그럼에도 이 원칙은 book에도 적용된다: book 파일에 접근할 수 없어도(없거나, 잠겨 있거나, 디렉터리를 만들 수 없어도) 진단은 계속 나가고 새 지식만 못 쌓인다. 절대 예외로 죽지 않는다.
- **예외는 경계를 넘지 않는다.** 모든 Maya 콜백(`compute`, `doIt`, 노드 메시지 콜백)과 `boad`/`book` 내부 파일 I/O 경계에 catch-all을 둔다. 새는 예외 하나가 Maya 세션 전체와 저장 안 된 작업을 날린다.
- **C++17.** devkit의 `cmake/devkit.cmake`가 플러그인 타깃에 `CMAKE_CXX_STANDARD 17` + `REQUIRED ON`을 하드코딩한다. `maro_diag`도 `maro_plugin`에 링크되므로 같은 표준을 쓴다(`maro_transform`과 동일한 이유, `src/maro_transform/CMakeLists.txt`의 주석 참고).
- **네임스페이스와 접두사는 `maro`/`Maro`.** 옛 `Maro_DebugUtility/`가 쓰던 `namespace MaroPlugin`은 계승하지 않는다 — 지금 프로젝트 전체가 쓰는 `namespace maro`로 통일한다.
- **UTF-8 소스.** 빌드가 이미 MSVC에 `/utf-8`을 넘긴다(루트 `CMakeLists.txt`). 새 파일은 전부 UTF-8로 저장한다 — `Maro_DebugUtility/`가 겪은 CP949 문제를 반복하지 않는다.
- **에러 해시는 세션·머신 불변이어야 한다.** 포인터, 타임스탬프, 노드 인스턴스 이름을 해시 입력에 절대 넣지 않는다. 실패의 "자리와 종류"만 넣는다 (Task 1에서 계약을 정의하고 테스트로 고정한다).
- **범위 밖 (건드리지 않음):** `src/control_bridge/`, `src/image_bridge/`, `src/Maro_library/`, `MaroCmd.cpp`, `moveTool.cpp`, `rosSimCmd.cpp`, `Maro_DebugUtility/`, `Maro_Management/`. 특히 `Maro_DebugUtility/`는 CP949 인코딩에 옛 colcon 트리의 `ViewportStreamer`와 결합돼 있고 `MaroCmd.cpp`/`rosSimCmd.cpp`가 그것을 참조하며 사용자의 미커밋 변경까지 얹혀 있다 — 손대지 않고 `src/maro_diag/`·`src/maro_plugin/`에 새로 짓는다. 통합은 이 플랜이 끝난 뒤의 후속 작업이다(§6 참고).
- **Maya 테스트 주의**: Maya는 커스텀 노드 인스턴스가 씬에 남아 있으면 플러그인을 언로드하지 않는다. 노드를 만든 테스트는 `cmds.unloadPlugin` 앞에 `cmds.file(new=True, force=True)`로 씬을 비운다.
- **빌드 환경 주의**: 이 머신에서 `Launch-VsDevShell.ps1`은 `vswhere.exe`를 못 찾아 `INCLUDE`/`LIB`를 비운 채 조용히 성공한다. 결과는 `basetsd.h`를 못 찾는 엉뚱한 컴파일 에러다. 대신 `VsDevCmd.bat`의 환경을 가져와 쓰고, PowerShell 도구 호출 간에는 환경이 유지되지 않으므로 **빌드와 같은 호출 안에서** 설정한다.

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
```

- **좀비 프로세스 주의**: 빌드가 `LNK1168: cannot open ... for writing`로 실패하면 남은 `mayapy.exe`가 DLL을 붙잡고 있는 것이다. `taskkill /F`로 안 죽으면 WMI `Invoke-CimMethod -MethodName Terminate` 폴백을 쓴다.
- **새 테스트는 전부 고의로 구현을 깨서 실패하는 것까지 확인한다.** 통과하는 테스트가 틀린 구현도 통과시킨 전례가 이 프로젝트에 일곱 번 있었다. 매 태스크에 "prove test can fail" 스텝을 명시적으로 둔다 — 제안이 아니라 절차다.

## 아키텍처 노트 — 이미 정해진 설계 결정 두 가지

### 결정 1 — Layer A에서 `book`을 쓰는 주체

스펙 §3.5는 "쓰기는 감시자만"이라고 못박는다. 하지만 Layer A에는 감시자가 없다. 스펙 §5.4가 이미 답을 정해 놓았다: 감시자가 없을 때 플러그인의 쓰기는 **스필 파일**로 나가고, 감시자가 붙으면 다음 기동 때 흡수해 정본으로 승격한다.

그래서 Layer A는:

- **정본**(`maro_knowledge.jsonl`) — 이 플랜에서 만들지 않는다. 존재하면 읽기만 한다. 감시자(Layer C)가 나타나기 전까지는 빈 채로 남는다.
- **스필**(`maro_knowledge.spill.jsonl`) — 이 플랜이 유일하게 쓰는 파일. `BoadMaro::error()`가 새 실패를 처음 볼 때, 그리고 `BoadMaro::registerRemedy()`가 해법을 등록할 때 한 줄씩 추가한다.
- **읽기**는 항상 정본+스필을 병합한다. 같은 해시가 양쪽에 있으면 스필이 이긴다(더 최신 지식이므로).

여기서 만든 것은 하나도 버려지지 않는다 — Layer C가 감시자를 놓으면 그 감시자는 이미 있는 스필 파일 포맷을 그대로 흡수하면 된다. 스필 포맷을 JSON Lines(줄마다 독립된 JSON 오브젝트)로 고른 것도 이 때문이다: 항상 append이므로 쓰는 도중 플러그인이 죽어도 이미 쓴 줄은 온전하다. 트리 전체를 다시 쓰는 포맷이었다면 그 중간에 죽었을 때 파일 전체가 깨졌을 것이다 — 스펙 §5.1이 저널에 대해 말하는 것과 같은 이유다.

### 결정 2 — `Maro_DebugUtility/`는 그대로 두고 새로 짓는다

`Maro_DebugUtility/boad_Maro.h`, `book_Maro.h`, `onfix_Maro.h`는 CP949로 저장돼 있고, `BoadMaro::dumpState(const ViewportStreamer*)`가 옛 colcon 트리의 클래스에 결합돼 있으며, `COLCON_IGNORE`로 방치돼 새 CMake가 전혀 모른다. 그리고 무엇보다 계약이 이 설계와 다르다 — 읽기/쓰기 분리도, 스필도, 해법도 없다. 517줄을 UTF-8로 변환하고 결합을 풀어 정리하느니, 이름과 개념만 이어받아 새로 쓰는 편이 이 플랜의 범위 안에서 더 안전하다.

**이어받는 것:**

| 옛 이름 (`Maro_DebugUtility`, `namespace MaroPlugin`) | 이 플랜에서 (`namespace maro`) |
|---|---|
| `BoadMaro::info/warn/devInfo/error` | 그대로. Task 3에서 골격, Task 5에서 book 연동까지 완성 |
| `MARO_ASSERT` 매크로 | 그대로. Task 3 |
| `BookMaro::QueryLog` / `SaveLogPermanently` | 이름은 이어받지 않는다 — 아래 설명 |
| Tier 개념 (`boad`=Tier4 출구, `onfix`=Tier1 원인 수집) | 유지. 주석에 남긴다 |
| `OnfixMaro::SaveFragment/Enrich` (디렉터리 인덱싱) | **폐기.** 스펙 §4가 이미 onfix의 의미를 "디렉터리 인덱싱"에서 "DG 컨텍스트 포착"으로 바꿨다. 파일 경로가 아니라 노드/어트리뷰트 관계를 담는다 |

`BookMaro::QueryLog`/`SaveLogPermanently`는 의도적으로 이름을 이어받지 않는다. 옛 API는 조회와 저장을 한 클래스가 갖고 MString(Maya 타입)을 직접 다뤘다 — 이 플랜의 "Maya-free 라이브러리 우선" 원칙과 정면으로 부딪힌다. 대신 저장 엔진은 `src/maro_diag/`의 Maya-free `BookStore`(문자열만 다룸)가 맡고, 조회는 `BoadMaro::error()` 안에 감춰지며(스펙 §4.2 "boad가 에러 시 book을 먼저 조회"), 등록은 `BoadMaro::registerRemedy()`가 맡는다. "book을 아는 것은 boad뿐"이라는 형태가 "boad가 진단의 단일 출구"라는 이 설계의 핵심 원칙과 더 잘 맞는다.

## 파일 구조

```
Maya_Ros_Sim/
├── CMakeLists.txt                                  [수정] add_subdirectory(src/maro_diag)
├── vcpkg.json                                       [수정] nlohmann-json 추가
├── src/maro_diag/                                    Maya-free — book·해시·레코드 타입
│   ├── CMakeLists.txt                                [생성]
│   ├── include/maro_diag/DiagRecord.h                [생성] DiagSeverity/DgContext/DiagRecord
│   ├── include/maro_diag/ErrorHash.h                 [생성] hashError()
│   ├── include/maro_diag/BookStore.h                 [생성] BookEntry/BookStore
│   ├── src/ErrorHash.cpp                             [생성]
│   └── src/BookStore.cpp                             [생성]
├── src/maro_plugin/                                   Maya 의존 — boad/onfix 배선
│   ├── CMakeLists.txt                                [수정] maro_diag 소스·링크 추가
│   ├── MaroPluginMain.cpp                            [수정] 진단 커맨드 6개 등록/해제
│   ├── MaroDiag.h / MaroDiag.cpp                     [생성] BoadMaro, ScopedCommandContext, onfix
│   ├── MaroDiagCommands.h / .cpp                     [생성] 테스트 전용 진단 조회 커맨드
│   └── MaroCommands.cpp                              [수정] onfix 마커 설치 + boad 전환 (Task 4, 7)
│   └── (MaroAxisNode.cpp, MaroCapabilityNodes.cpp, MaroCommandDeviceNode.cpp,
│        MaroDeleteWatcher.cpp, MaroPump.cpp — 전부 Task 7에서 boad로 전환)
└── tests/
    ├── CMakeLists.txt                                [수정] maro_diag_tests + maya_diag_* 등록
    ├── diag/test_error_hash.cpp                      [생성] GTest, Maya 불필요
    ├── diag/test_book_store.cpp                       [생성] GTest, Maya 불필요
    └── maya/test_diag_boad.py                         [생성]
    └── maya/test_diag_onfix.py                        [생성]
    └── maya/test_diag_book.py                         [생성]
    └── maya/test_diag_remedy.py                       [생성]
    └── maya/test_diag_degraded.py                     [생성]
```

---

# Phase A — Maya-free 진단 라이브러리 (`src/maro_diag`)

Maya도 devkit도 없이 도는 코드다. 해시 안정성과 book 병합 규칙의 버그를 여기서 잡는다.

### Task 1: 진단 레코드 타입과 안정 에러 해시

**Files:**
- Create: `src/maro_diag/CMakeLists.txt`
- Create: `src/maro_diag/include/maro_diag/DiagRecord.h`
- Create: `src/maro_diag/include/maro_diag/ErrorHash.h`
- Create: `src/maro_diag/src/ErrorHash.cpp`
- Modify: `CMakeLists.txt` (루트) — `add_subdirectory(src/maro_diag)`
- Modify: `tests/CMakeLists.txt` — `maro_diag_tests` 타깃 추가
- Test: `tests/diag/test_error_hash.cpp`

**Interfaces:**
- Consumes: 없음
- Produces: CMake 타깃 `maro_diag`(정적 라이브러리, Maya-free). `maro_diag/DiagRecord.h`의 `maro::DiagSeverity`, `maro::DgContext`, `maro::DiagRecord`. `maro_diag/ErrorHash.h`의 `std::string maro::hashError(const std::string& siteTag)`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/diag/test_error_hash.cpp`:

```cpp
#include <gtest/gtest.h>

#include "maro_diag/DiagRecord.h"
#include "maro_diag/ErrorHash.h"

TEST(ErrorHash, PinnedValueForKnownTag) {
    // 실제 FNV-1a-64 구현으로 미리 계산해 둔 값이다(오프셋 0xcbf29ce484222325,
    // 프라임 0x100000001b3, UTF-8 바이트 단위). 이 상수가 바뀌면 book의 기존
    // 항목이 전부 조회되지 않게 되므로, 해시 알고리즘을 바꿀 때는 반드시
    // book 마이그레이션과 함께 다뤄야 한다.
    EXPECT_EQ(maro::hashError("MaroBindAxisCommand.TargetNotTransform"),
              "068895013575db45");
}

TEST(ErrorHash, EmptyTagIsWellDefined) {
    EXPECT_EQ(maro::hashError(""), "cbf29ce484222325");
}

TEST(ErrorHash, DifferentTagsProduceDifferentHashes) {
    const std::string a = maro::hashError("MaroBindAxisCommand.TargetNotTransform");
    const std::string b = maro::hashError("MaroBindAxisCommand.NotMaroAxisNode");
    EXPECT_NE(a, b);
}

TEST(ErrorHash, SameTagIsStableAcrossCalls) {
    // "세션마다 다르지 않다"를 프로세스 안에서 흉내낸다: 같은 태그를 두 번
    // 독립적으로 호출해도 같은 값이 나와야 한다. 포인터나 시각이 섞여
    // 들어갔다면 여기서 흔들렸을 것이다. hashError는 문자열 하나만 받는
    // 시그니처라 애초에 그런 값을 넣을 자리가 없다.
    const std::string tag = "MaroBindAxisCommand.TargetNotTransform";
    EXPECT_EQ(maro::hashError(tag), maro::hashError(tag));
}

TEST(DiagRecordTest, DefaultsAreEmpty) {
    maro::DiagRecord rec;
    EXPECT_EQ(rec.severity, maro::DiagSeverity::Info);
    EXPECT_TRUE(rec.message.empty());
    EXPECT_TRUE(rec.errorHash.empty());
    EXPECT_TRUE(rec.context.nodeType.empty());
    EXPECT_FALSE(rec.servedFromBook);
}
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
cmake -S . -B out/build -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_TOOLCHAIN_FILE=C:/src/vcpkg/scripts/buildsystems/vcpkg.cmake -DMARO_BUILD_PLUGIN=OFF
```

기대: 구성 단계에서 `add_subdirectory`/타깃이 아직 없어 테스트 자체가 존재하지 않는다. 이 스텝은 "아직 아무것도 없다"를 확인하는 것으로, Step 3~4의 CMake 배선을 넣은 뒤 `cmake --build out/build`를 돌리면 `'maro_diag/DiagRecord.h' file not found`로 실패해야 정상이다.

- [ ] **Step 3: `maro_diag` CMake 골격과 루트/테스트 배선**

`src/maro_diag/CMakeLists.txt`:

```cmake
add_library(maro_diag STATIC
    src/ErrorHash.cpp
)

target_include_directories(maro_diag PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# Maya devkit이 플러그인 타깃을 C++17로 강제한다(devkit.cmake). 이 라이브러리는
# 플러그인에 링크되므로 표준을 맞춘다 -- maro_transform과 같은 이유
# (src/maro_transform/CMakeLists.txt 참고).
target_compile_features(maro_diag PUBLIC cxx_std_17)
```

`CMakeLists.txt`(루트)에서 `add_subdirectory(src/maro_transform)` 바로 아래에 추가:

```cmake
add_subdirectory(src/maro_diag)
```

`tests/CMakeLists.txt`에서 `gtest_discover_tests(maro_transform_tests)` 바로 아래에 추가:

```cmake
add_executable(maro_diag_tests
    diag/test_error_hash.cpp
)

target_link_libraries(maro_diag_tests PRIVATE
    maro_diag
    GTest::gtest
    GTest::gtest_main
)

gtest_discover_tests(maro_diag_tests)
```

- [ ] **Step 4: `DiagRecord.h` 작성**

`src/maro_diag/include/maro_diag/DiagRecord.h`:

```cpp
#pragma once

#include <string>

namespace maro {

// 진단 심각도. boad가 스크립트 에디터에 어떤 함수로 내보낼지도 이것으로 정해진다.
enum class DiagSeverity {
    Info,
    Warn,
    DevInfo,
    Error,
};

// onfix가 포착하는 DG 컨텍스트. 파일 경로가 아니라 노드·어트리뷰트·커맨드·축의
// 관계를 담는다 (설계 스펙 §4 "onfix가 바뀐 이유"). 필드가 비어 있으면 "그
// 시점에 관여가 없었다"는 뜻이지 에러가 아니다.
struct DgContext {
    std::string nodeType;       // 관여한 노드의 타입 이름. 예: "maroAxis", "pointLight"
    std::string attributeName;  // 관여한 어트리뷰트 롱네임. 예: "targetObject"
    std::string activeCommand;  // 진행 중이던 커맨드 클래스 이름. 예: "MaroBindAxisCommand"
    std::string axisOrTarget;   // 관여한 축 또는 대상 오브젝트의 이름.
};

// boad의 인메모리 진단 스트림 한 칸. 진단 패널(Layer B)이 그대로 읽을 구조이므로
// 지금부터 이 모양으로 고정한다.
struct DiagRecord {
    DiagSeverity severity = DiagSeverity::Info;
    std::string message;          // 실제로 출력된(또는 출력될) 문장.
    std::string errorHash;        // Error 심각도에서만 채워진다. hashError()의 결과.
    DgContext context;             // onfix가 채운다. 없으면 전부 빈 문자열.
    std::string remedy;            // book에 등록된 해법. 없으면 빈 문자열.
    bool servedFromBook = false;  // book 캐시로 즉답했으면 true.
};

}  // namespace maro
```

- [ ] **Step 5: `ErrorHash.h`/`.cpp` 작성**

`src/maro_diag/include/maro_diag/ErrorHash.h`:

```cpp
#pragma once

#include <string>

namespace maro {

// 에러 해시는 실패의 "자리와 종류"에서만 만든다.
//
// 포함: 호출부가 직접 쓰는 사이트 태그 문자열 하나뿐이다. 관례상
// "<클래스 또는 함수>.<사유>" 형태로 쓴다 (예:
// "MaroBindAxisCommand.TargetNotTransform").
//
// 제외: 포인터 주소, 타임스탬프, 노드 인스턴스 이름, 세션마다 달라지는 모든
// 값. 이 함수가 문자열 하나만 받는다는 시그니처 자체가 그것들을 원천
// 차단한다 -- 애초에 넣을 자리가 없다.
//
// 같은 사이트 태그는 항상 같은 해시를 낸다 (같은 프로세스든, 다른 세션이든,
// 다른 머신이든). FNV-1a는 로케일도 포인터도 시각도 관여하지 않는 순수 바이트
// 연산이라 이 성질이 플랫폼에 무관하게 성립한다.
std::string hashError(const std::string& siteTag);

}  // namespace maro
```

`src/maro_diag/src/ErrorHash.cpp`:

```cpp
#include "maro_diag/ErrorHash.h"

#include <cstddef>
#include <cstdint>

namespace maro {

std::string hashError(const std::string& siteTag) {
    // FNV-1a, 64비트. 오프셋과 프라임은 표준 상수다.
    std::uint64_t h = 0xcbf29ce484222325ULL;
    constexpr std::uint64_t kPrime = 0x100000001b3ULL;

    for (unsigned char c : siteTag) {
        h ^= static_cast<std::uint64_t>(c);
        h *= kPrime;
    }

    // 16자리 소문자 16진수로 고정폭 표현한다. book 파일의 JSON 키로 쓰기
    // 좋고, 사람이 눈으로 비교하기도 쉽다.
    static const char kHex[] = "0123456789abcdef";
    std::string out(16, '0');
    for (int i = 15; i >= 0; --i) {
        out[static_cast<std::size_t>(i)] = kHex[h & 0xF];
        h >>= 4;
    }
    return out;
}

}  // namespace maro
```

- [ ] **Step 6: 빌드하고 테스트가 통과하는지 확인**

```bash
cmake --build out/build
```

```bash
ctest --test-dir out/build --output-on-failure
```

기대: `ErrorHash.*` 4개, `DiagRecordTest.DefaultsAreEmpty` 1개, 기존 `Harness.*`/`Position.*`/`Rotation.*`/`AxisConventionTest.*` 전체 통과. Maya가 관여하지 않으므로 수 초 내에 끝난다.

- [ ] **Step 7: 해시가 실제로 값을 지키는지 확인**

통과를 본 것만으로는 부족하다. 상수를 일부러 틀리게 바꿔 pinned 테스트가 잡는지 본다.

`ErrorHash.cpp`의 `kPrime`을 `0x100000001b1ULL`(마지막 자리만 다름)로 바꾸고 빌드·실행한다.

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure
```

기대: `ErrorHash.PinnedValueForKnownTag`가 **실패**한다. 실패 출력을 확인했으면 `kPrime`을 `0x100000001b3ULL`로 되돌리고 다시 빌드해 전체 통과를 본다.

실패하지 않는다면 pinned 테스트가 알고리즘을 지키지 못하고 있는 것이므로, 되돌리기 전에 테스트를 고친다.

- [ ] **Step 8: 커밋**

```bash
git add CMakeLists.txt src/maro_diag tests/CMakeLists.txt tests/diag/test_error_hash.cpp
git commit -m "feat: add diagnostic record types and a stable error hash"
```

---

### Task 2: `book` 파일 포맷 — 정본·스필 읽기/병합/쓰기와 해법 필드

**Files:**
- Create: `src/maro_diag/include/maro_diag/BookStore.h`
- Create: `src/maro_diag/src/BookStore.cpp`
- Modify: `src/maro_diag/CMakeLists.txt` — `BookStore.cpp` 추가, `nlohmann_json` 링크
- Modify: `vcpkg.json` — `nlohmann-json` 의존성 추가
- Modify: `tests/CMakeLists.txt` — `maro_diag_tests`에 소스 추가
- Test: `tests/diag/test_book_store.cpp`

**Interfaces:**
- Consumes: `maro::DgContext` (Task 1)
- Produces: `maro::BookEntry`(분석·해법·컨텍스트), `maro::BookStore`(정적 `loadMerged`/`appendToSpill`, 인스턴스 `query`/`size`)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/diag/test_book_store.cpp`:

```cpp
#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>

#include "maro_diag/BookStore.h"

namespace {

// 테스트마다 고유한 임시 디렉터리. gtest의 현재 테스트 이름을 그대로 써서
// 병렬 실행이나 재실행에도 서로 밟지 않는다.
std::filesystem::path tempDirForTest() {
    const auto* info = ::testing::UnitTest::GetInstance()->current_test_info();
    auto dir = std::filesystem::path(::testing::TempDir()) /
               (std::string("maro_book_") + info->test_suite_name() + "_" + info->name());
    std::filesystem::remove_all(dir);
    std::filesystem::create_directories(dir);
    return dir;
}

}  // namespace

TEST(BookStore, MissingFilesYieldEmptyStoreWithoutThrowing) {
    const auto dir = tempDirForTest();
    const auto canonical = dir / "missing_canonical.jsonl";
    const auto spill = dir / "missing_spill.jsonl";

    maro::BookStore store;
    ASSERT_NO_THROW(store = maro::BookStore::loadMerged(canonical, spill));
    EXPECT_EQ(store.size(), 0u);

    maro::BookEntry out;
    EXPECT_FALSE(store.query("anything", out));
}

TEST(BookStore, SpillWinsOverCanonicalForSameHash) {
    const auto dir = tempDirForTest();
    const auto canonical = dir / "canonical.jsonl";
    const auto spill = dir / "spill.jsonl";

    {
        std::ofstream ofs(canonical);
        ofs << R"({"hash":"h1","analysis":"old analysis","remedy":"","nodeType":"","attributeName":"","activeCommand":"","axisOrTarget":""})" << "\n";
    }
    {
        std::ofstream ofs(spill);
        ofs << R"({"hash":"h1","analysis":"new analysis","remedy":"","nodeType":"","attributeName":"","activeCommand":"","axisOrTarget":""})" << "\n";
    }

    const auto store = maro::BookStore::loadMerged(canonical, spill);
    maro::BookEntry out;
    ASSERT_TRUE(store.query("h1", out));
    EXPECT_EQ(out.analysis, "new analysis");
}

TEST(BookStore, CorruptLineIsSkippedNotFatal) {
    const auto dir = tempDirForTest();
    const auto spill = dir / "spill.jsonl";

    {
        std::ofstream ofs(spill);
        ofs << "{ this is not json\n";
        ofs << R"({"hash":"h2","analysis":"still readable","remedy":"","nodeType":"","attributeName":"","activeCommand":"","axisOrTarget":""})" << "\n";
    }

    maro::BookStore store;
    ASSERT_NO_THROW(store = maro::BookStore::loadMerged(dir / "no_canonical.jsonl", spill));

    maro::BookEntry out;
    ASSERT_TRUE(store.query("h2", out));
    EXPECT_EQ(out.analysis, "still readable");
}

TEST(BookStore, AppendToSpillIsReadableAfterReload) {
    const auto dir = tempDirForTest();
    const auto spill = dir / "spill.jsonl";

    maro::BookEntry entry;
    entry.analysis = "first analysis";
    entry.context.nodeType = "maroAxis";
    ASSERT_TRUE(maro::BookStore::appendToSpill(spill, "h3", entry));

    const auto store = maro::BookStore::loadMerged(dir / "no_canonical.jsonl", spill);
    maro::BookEntry out;
    ASSERT_TRUE(store.query("h3", out));
    EXPECT_EQ(out.analysis, "first analysis");
    EXPECT_EQ(out.context.nodeType, "maroAxis");
}

TEST(BookStore, LatestAppendWinsForRepeatedHash) {
    const auto dir = tempDirForTest();
    const auto spill = dir / "spill.jsonl";

    maro::BookEntry first;
    first.analysis = "first";
    maro::BookEntry second;
    second.analysis = "second";
    second.remedy = "apply the fix";

    ASSERT_TRUE(maro::BookStore::appendToSpill(spill, "h4", first));
    ASSERT_TRUE(maro::BookStore::appendToSpill(spill, "h4", second));

    const auto store = maro::BookStore::loadMerged(dir / "no_canonical.jsonl", spill);
    maro::BookEntry out;
    ASSERT_TRUE(store.query("h4", out));
    EXPECT_EQ(out.analysis, "second");
    EXPECT_EQ(out.remedy, "apply the fix");
}
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
cmake --build out/build
```

기대: 컴파일 실패. `'maro_diag/BookStore.h' file not found`.

- [ ] **Step 3: `nlohmann-json` 의존성 배선**

`vcpkg.json`의 `dependencies`에 추가:

```json
  "dependencies": [
    "gtest",
    "nlohmann-json"
  ]
```

`src/maro_diag/CMakeLists.txt`를 아래로 교체:

```cmake
find_package(nlohmann_json CONFIG REQUIRED)

add_library(maro_diag STATIC
    src/ErrorHash.cpp
    src/BookStore.cpp
)

target_include_directories(maro_diag PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# BookStore.cpp 내부에서만 쓴다. 헤더가 nlohmann/json.hpp를 노출하지 않으므로
# PRIVATE로 충분하고, maro_plugin이 이 의존성을 몰라도 된다.
target_link_libraries(maro_diag PRIVATE nlohmann_json::nlohmann_json)

target_compile_features(maro_diag PUBLIC cxx_std_17)
```

`cmake -S . -B out/build ...` 재구성이 필요하다(새 vcpkg 의존성).

```bash
cmake -S . -B out/build -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_TOOLCHAIN_FILE=C:/src/vcpkg/scripts/buildsystems/vcpkg.cmake -DMARO_BUILD_PLUGIN=OFF
```

- [ ] **Step 4: `BookStore.h` 작성**

`src/maro_diag/include/maro_diag/BookStore.h`:

```cpp
#pragma once

#include <cstddef>
#include <filesystem>
#include <string>
#include <unordered_map>

#include "maro_diag/DiagRecord.h"

namespace maro {

// book 한 항목. 해시 하나에 원인 분석 한 편과 해법 하나(있다면)가 붙는다.
struct BookEntry {
    std::string analysis;  // 사람이 읽는 원인 설명. 최초 발생 시 boad가 채운다.
    std::string remedy;    // 등록된 해법. 없으면 빈 문자열.
    DgContext context;      // 최초 관측 시점의 DG 컨텍스트. 참고용.
};

// book 파일 하나 = JSON Lines. 한 줄에 레코드 하나.
// {"hash":"...","analysis":"...","remedy":"...","nodeType":"...",
//  "attributeName":"...","activeCommand":"...","axisOrTarget":"..."}
//
// 스필을 이 모양으로 고른 이유(설계 스펙 §5.4): 감시자가 없는 지금, 스필은
// 플러그인이 쓸 수 있는 유일한 통로다. JSON Lines는 항상 append이므로 쓰는
// 도중 플러그인이 죽어도 이미 쓴 줄은 그대로 유효하다 -- 트리 전체를 다시
// 쓰는 포맷이었다면 그 중간에 죽었을 때 파일 전체가 깨졌을 것이다.
class BookStore {
public:
    // 정본과 스필을 읽어 병합한다. 둘 다 없으면 빈 스토어를 돌려준다 --
    // 파일이 없는 것은 에러가 아니다 (스펙 §3.6, §5.4: 감시자/정본이 없어도
    // book 조회는 계속 동작해야 한다). 파일이 있는데 파싱할 수 없는 줄은
    // 건너뛰고 나머지는 살린다 -- 깨진 줄 하나가 지식 전체를 지우지 않는다.
    static BookStore loadMerged(const std::filesystem::path& canonicalPath,
                                 const std::filesystem::path& spillPath);

    bool query(const std::string& errorHash, BookEntry& out) const;
    std::size_t size() const { return entries_.size(); }

    // Layer A는 정본에 쓰지 않는다 (스펙 §3.5) -- 스필에 한 줄만 추가한다.
    // 실패해도(디렉터리가 없거나 쓰기 권한이 없거나) 예외를 던지지 않고
    // false를 돌려준다: book이 죽어도 진단은 죽지 않는다.
    static bool appendToSpill(const std::filesystem::path& spillPath,
                               const std::string& errorHash,
                               const BookEntry& entry);

private:
    static void loadFile(const std::filesystem::path& path,
                          std::unordered_map<std::string, BookEntry>& out);

    std::unordered_map<std::string, BookEntry> entries_;
};

}  // namespace maro
```

- [ ] **Step 5: `BookStore.cpp` 작성**

`src/maro_diag/src/BookStore.cpp`:

```cpp
#include "maro_diag/BookStore.h"

#include <fstream>
#include <system_error>

#include <nlohmann/json.hpp>

namespace maro {

namespace {

BookEntry entryFromJson(const nlohmann::json& j) {
    BookEntry e;
    e.analysis = j.value("analysis", std::string());
    e.remedy = j.value("remedy", std::string());
    e.context.nodeType = j.value("nodeType", std::string());
    e.context.attributeName = j.value("attributeName", std::string());
    e.context.activeCommand = j.value("activeCommand", std::string());
    e.context.axisOrTarget = j.value("axisOrTarget", std::string());
    return e;
}

nlohmann::json entryToJson(const std::string& hash, const BookEntry& e) {
    nlohmann::json j;
    j["hash"] = hash;
    j["analysis"] = e.analysis;
    j["remedy"] = e.remedy;
    j["nodeType"] = e.context.nodeType;
    j["attributeName"] = e.context.attributeName;
    j["activeCommand"] = e.context.activeCommand;
    j["axisOrTarget"] = e.context.axisOrTarget;
    return j;
}

}  // namespace

void BookStore::loadFile(const std::filesystem::path& path,
                          std::unordered_map<std::string, BookEntry>& out) {
    if (path.empty()) return;

    std::error_code ec;
    if (!std::filesystem::exists(path, ec) || ec) return;

    std::ifstream ifs(path);
    if (!ifs) return;

    std::string line;
    while (std::getline(ifs, line)) {
        if (line.empty()) continue;
        try {
            const nlohmann::json j = nlohmann::json::parse(line);
            const std::string hash = j.value("hash", std::string());
            if (hash.empty()) continue;
            out[hash] = entryFromJson(j);
        } catch (const nlohmann::json::exception&) {
            // 깨진 줄 하나 때문에 나머지 지식까지 버리지 않는다.
            continue;
        }
    }
}

BookStore BookStore::loadMerged(const std::filesystem::path& canonicalPath,
                                 const std::filesystem::path& spillPath) {
    BookStore store;
    // 정본을 먼저 채우고 스필로 덮어쓴다 -- 같은 해시가 양쪽에 있으면
    // 스필이 이긴다. 스필은 감시자가 아직 흡수하지 못한, 더 최신인 지식이기
    // 때문이다 (스펙 §5.4).
    loadFile(canonicalPath, store.entries_);
    loadFile(spillPath, store.entries_);
    return store;
}

bool BookStore::query(const std::string& errorHash, BookEntry& out) const {
    const auto it = entries_.find(errorHash);
    if (it == entries_.end()) return false;
    out = it->second;
    return true;
}

bool BookStore::appendToSpill(const std::filesystem::path& spillPath,
                               const std::string& errorHash,
                               const BookEntry& entry) {
    if (spillPath.empty()) return false;
    try {
        std::error_code ec;
        std::filesystem::create_directories(spillPath.parent_path(), ec);

        std::ofstream ofs(spillPath, std::ios::app);
        if (!ofs) return false;

        ofs << entryToJson(errorHash, entry).dump() << '\n';
        return static_cast<bool>(ofs);
    } catch (...) {
        // book이 죽어도 진단은 죽지 않는다 (스펙 §3.6).
        return false;
    }
}

}  // namespace maro
```

`tests/CMakeLists.txt`의 `maro_diag_tests` 소스 목록에 추가:

```cmake
add_executable(maro_diag_tests
    diag/test_error_hash.cpp
    diag/test_book_store.cpp
)
```

- [ ] **Step 6: 빌드하고 테스트가 통과하는지 확인**

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure
```

기대: `BookStore.*` 5개 포함 전체 통과.

- [ ] **Step 7: "스필이 이긴다"를 테스트가 실제로 지키는지 확인**

`BookStore.cpp`의 `loadMerged`에서 두 줄의 순서를 바꿔 정본이 스필을 덮어쓰게 만든다(`loadFile(spillPath, ...)`를 먼저, `loadFile(canonicalPath, ...)`를 나중에).

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure
```

기대: `BookStore.SpillWinsOverCanonicalForSameHash`가 **실패**한다. 확인했으면 순서를 원래대로(정본 먼저, 스필 나중) 되돌리고 다시 빌드해 전체 통과를 본다.

- [ ] **Step 8: 커밋**

```bash
git add vcpkg.json src/maro_diag tests/CMakeLists.txt tests/diag/test_book_store.cpp
git commit -m "feat: add book file format with canonical+spill merge and remedy fields"
```

---

# Phase B — Maya 플러그인 진단 배선 (`src/maro_plugin`)

이제부터는 Maya 없이는 검증할 수 없다. `mayapy`로 돈다.

### Task 3: `boad` 진단 출구 골격과 CMake 배선

`BoadMaro`를 세운다: info/warn/devInfo와 인메모리 진단 스트림. 아직 book도 onfix도 붙지 않는다 — "출력하고 기록한다"만 증명한다. mayapy 테스트가 내부 상태를 볼 수 있도록 테스트 전용 커맨드 3개(`maroDiagEmit`, `maroDiagCount`, `maroDiagQuery`)를 함께 둔다. 이 셋은 `maroBridgeStats`(`src/maro_plugin/MaroCommands.h`)와 같은 이유로 존재한다 — 진단 배관 자체가 아니라 그것을 들여다보는 창이다.

**Files:**
- Create: `src/maro_plugin/MaroDiag.h`
- Create: `src/maro_plugin/MaroDiag.cpp`
- Create: `src/maro_plugin/MaroDiagCommands.h`
- Create: `src/maro_plugin/MaroDiagCommands.cpp`
- Modify: `src/maro_plugin/CMakeLists.txt` — 소스 2개 추가, `maro_diag` 링크
- Modify: `src/maro_plugin/MaroPluginMain.cpp` — 커맨드 3개 등록/해제
- Test: `tests/maya/test_diag_boad.py`
- Modify: `tests/CMakeLists.txt` — `maya_diag_boad` 등록

**Interfaces:**
- Consumes: `maro::DiagRecord`, `maro::DgContext` (Task 1)
- Produces: `maro::BoadMaro::info/warn/devInfo`, `recordCount()`, `recordAt()`, `resetForTest()`. `MARO_ASSERT` 매크로. MEL 커맨드 `maroDiagEmit`/`maroDiagCount`/`maroDiagQuery`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/maya/test_diag_boad.py`:

```python
"""boad 진단 출구: 인메모리 스트림이 심각도·순서를 정확히 유지하는지 확인한다."""
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)

before = cmds.maroDiagCount()

cmds.maroDiagEmit(severity="info", message="hello info")
cmds.maroDiagEmit(severity="warn", message="hello warn")

after = cmds.maroDiagCount()
assert after == before + 2, f"expected {before + 2} records, got {after}"
print("count OK")

# index 0 = 가장 최근 = warn
latest = cmds.maroDiagQuery(index=0)
assert latest[0] == "warn", f"expected latest severity 'warn', got {latest[0]!r}"
assert latest[1] == "hello warn", f"expected latest message 'hello warn', got {latest[1]!r}"
print("latest record OK")

previous = cmds.maroDiagQuery(index=1)
assert previous[0] == "info"
assert previous[1] == "hello info"
print("previous record OK")

cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
"/c/Program Files/Autodesk/Maya2026/bin/mayapy.exe" -c "print('placeholder')"
```

아직 `maroDiagEmit`/`maroDiagCount`/`maroDiagQuery`가 존재하지 않으므로, 현재 빌드된 `maro.mll`로 위 스크립트를 돌리면 `cmds.maroDiagCount()`에서 `RuntimeError: Unknown Maya command 'maroDiagCount'`로 실패한다. (아직 `tests/CMakeLists.txt`에 등록하지 않았으므로 Step 6 빌드 후 수동으로 한 번 실행해 이 실패를 직접 본다.)

- [ ] **Step 3: `MaroDiag.h` 작성**

`src/maro_plugin/MaroDiag.h`:

```cpp
#pragma once

#include <cassert>
#include <cstddef>
#include <string>

#include <maya/MString.h>

#include "maro_diag/DiagRecord.h"

namespace maro {

// 진단의 단일 출구 (설계 스펙 §4 boad 행). 모든 info/warn/devInfo/error가
// 여기를 거친다. 인메모리 스트림을 스스로 들고 있다 -- 진단 패널(Layer B)은
// 이것과 book 파일만 읽고 자체 상태를 갖지 않는다 (스펙 §4.2).
class BoadMaro {
public:
    static void info(const MString& message);
    static void warn(const MString& message);
    static void devInfo(const MString& message);

    // siteTag: 이 실패의 자리와 종류만 담는 불변 식별자 (maro::hashError
    // 계약, Task 1). context는 Task 4에서 onfix::capture()로 채운다 -- 지금은
    // 항상 기본값(전부 빈 문자열)이다.
    static void error(const std::string& siteTag, const MString& message,
                       const DgContext& context = DgContext{});

    static std::size_t recordCount();
    // indexFromEnd 0 = 가장 최근 레코드.
    static const DiagRecord& recordAt(std::size_t indexFromEnd);

    // 테스트 전용. 프로덕션 코드는 부르지 않는다.
    static void resetForTest();

private:
    static std::vector<DiagRecord>& stream();
};

}  // namespace maro

#ifndef MARO_ASSERT
// 원안(Maro_DebugUtility/boad_Maro.h)에서 이름을 그대로 가져왔다. 실패하면
// boad에 기록하고 assert로 중단한다.
#define MARO_ASSERT(cond, msg)                              \
    do {                                                    \
        if (!(cond)) {                                      \
            maro::BoadMaro::error("ASSERT_FAILED", (msg));  \
            assert(false && (msg));                         \
        }                                                    \
    } while (0)
#endif
```

`<vector>`가 필요하므로 include 목록에 `#include <vector>`를 추가한다.

- [ ] **Step 4: `MaroDiag.cpp` 작성**

`src/maro_plugin/MaroDiag.cpp`:

```cpp
#include "MaroDiag.h"

#include <utility>

#include <maya/MGlobal.h>

namespace maro {

std::vector<DiagRecord>& BoadMaro::stream() {
    static std::vector<DiagRecord> s_stream;
    return s_stream;
}

void BoadMaro::info(const MString& message) {
    DiagRecord rec;
    rec.severity = DiagSeverity::Info;
    rec.message = message.asChar();
    MGlobal::displayInfo(MString("[Maro-Info] ") + message);
    stream().push_back(std::move(rec));
}

void BoadMaro::warn(const MString& message) {
    DiagRecord rec;
    rec.severity = DiagSeverity::Warn;
    rec.message = message.asChar();
    MGlobal::displayWarning(MString("[Maro-Warn] ") + message);
    stream().push_back(std::move(rec));
}

void BoadMaro::devInfo(const MString& message) {
#ifdef _DEBUG
    DiagRecord rec;
    rec.severity = DiagSeverity::DevInfo;
    rec.message = message.asChar();
    MGlobal::displayInfo(MString("[Maro-Dev] ") + message);
    stream().push_back(std::move(rec));
#else
    (void)message;
#endif
}

void BoadMaro::error(const std::string& siteTag, const MString& message,
                      const DgContext& context) {
    // book 연동은 Task 5. 지금은 항상 "새 분석"으로 취급하고 스트림에만 남긴다.
    (void)siteTag;
    DiagRecord rec;
    rec.severity = DiagSeverity::Error;
    rec.context = context;
    rec.message = message.asChar();
    MGlobal::displayError(MString("[Maro-Error] ") + message);
    stream().push_back(std::move(rec));
}

std::size_t BoadMaro::recordCount() { return stream().size(); }

const DiagRecord& BoadMaro::recordAt(std::size_t indexFromEnd) {
    return stream().at(stream().size() - 1 - indexFromEnd);
}

void BoadMaro::resetForTest() { stream().clear(); }

}  // namespace maro
```

- [ ] **Step 5: 테스트 전용 진단 조회 커맨드 작성**

`src/maro_plugin/MaroDiagCommands.h`:

```cpp
#pragma once

#include <maya/MPxCommand.h>
#include <maya/MSyntax.h>

namespace maro {

// 아래 커맨드들은 진단 배관 자체가 아니라, mayapy 테스트가 BoadMaro의 내부
// 상태를 들여다보기 위한 테스트 전용 도구다 (MaroCommands.h의
// MaroBridgeStatsCommand와 같은 이유로 존재한다). 실제 진단 호출부는 이
// 커맨드들을 쓰지 않고 BoadMaro를 C++에서 직접 부른다.

// -severity <info|warn|devInfo|error> -message <string> [-siteTag <string>]
class MaroDiagEmitCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
};

// 인자 없음. 현재 스트림에 쌓인 레코드 수.
class MaroDiagCountCommand : public MPxCommand {
public:
    static void* creator();
    MStatus doIt(const MArgList& args) override;
};

// -index <int, 기본 0>. 0 = 가장 최근 레코드. 필드 9개를 순서대로 담은
// 문자열 배열을 돌려준다: severity, message, errorHash, nodeType,
// attributeName, activeCommand, axisOrTarget, remedy, servedFromBook("0"/"1").
class MaroDiagQueryCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
};

}  // namespace maro
```

`src/maro_plugin/MaroDiagCommands.cpp`:

```cpp
#include "MaroDiagCommands.h"

#include <maya/MArgDatabase.h>
#include <maya/MArgList.h>
#include <maya/MGlobal.h>
#include <maya/MStringArray.h>

#include "MaroDiag.h"

namespace maro {

namespace {

const char* kSeverityFlag = "-sv";
const char* kSeverityFlagLong = "-severity";
const char* kMessageFlag = "-msg";
const char* kMessageFlagLong = "-message";
const char* kSiteTagFlag = "-st";
const char* kSiteTagFlagLong = "-siteTag";
const char* kIndexFlag = "-i";
const char* kIndexFlagLong = "-index";

MString severityToString(DiagSeverity s) {
    switch (s) {
        case DiagSeverity::Info: return "info";
        case DiagSeverity::Warn: return "warn";
        case DiagSeverity::DevInfo: return "devInfo";
        case DiagSeverity::Error: return "error";
    }
    return "unknown";
}

}  // namespace

void* MaroDiagEmitCommand::creator() { return new MaroDiagEmitCommand(); }

MSyntax MaroDiagEmitCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag(kSeverityFlag, kSeverityFlagLong, MSyntax::kString);
    syntax.addFlag(kMessageFlag, kMessageFlagLong, MSyntax::kString);
    syntax.addFlag(kSiteTagFlag, kSiteTagFlagLong, MSyntax::kString);
    return syntax;
}

MStatus MaroDiagEmitCommand::doIt(const MArgList& args) {
    try {
        MStatus status;
        MArgDatabase argData(newSyntax(), args, &status);
        if (!status) return status;

        MString severity = "info";
        MString message;
        MString siteTag;
        argData.getFlagArgument(kSeverityFlag, 0, severity);
        argData.getFlagArgument(kMessageFlag, 0, message);
        if (argData.isFlagSet(kSiteTagFlag)) {
            argData.getFlagArgument(kSiteTagFlag, 0, siteTag);
        }

        if (severity == "info") {
            BoadMaro::info(message);
        } else if (severity == "warn") {
            BoadMaro::warn(message);
        } else if (severity == "devInfo") {
            BoadMaro::devInfo(message);
        } else if (severity == "error") {
            if (siteTag.length() == 0) {
                MGlobal::displayError("Maro: maroDiagEmit -severity error requires -siteTag.");
                return MS::kFailure;
            }
            BoadMaro::error(siteTag.asChar(), message);
        } else {
            MGlobal::displayError(MString("Maro: unknown severity '") + severity + "'.");
            return MS::kFailure;
        }
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroDiagEmit failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroDiagEmit failed with unknown error.");
        return MS::kFailure;
    }
}

void* MaroDiagCountCommand::creator() { return new MaroDiagCountCommand(); }

MStatus MaroDiagCountCommand::doIt(const MArgList& /*args*/) {
    setResult(static_cast<int>(BoadMaro::recordCount()));
    return MS::kSuccess;
}

void* MaroDiagQueryCommand::creator() { return new MaroDiagQueryCommand(); }

MSyntax MaroDiagQueryCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag(kIndexFlag, kIndexFlagLong, MSyntax::kLong);
    return syntax;
}

MStatus MaroDiagQueryCommand::doIt(const MArgList& args) {
    try {
        MStatus status;
        MArgDatabase argData(newSyntax(), args, &status);
        if (!status) return status;

        int index = 0;
        if (argData.isFlagSet(kIndexFlag)) {
            argData.getFlagArgument(kIndexFlag, 0, index);
        }

        if (index < 0 || static_cast<std::size_t>(index) >= BoadMaro::recordCount()) {
            MGlobal::displayError("Maro: maroDiagQuery index out of range.");
            return MS::kFailure;
        }

        const DiagRecord& rec = BoadMaro::recordAt(static_cast<std::size_t>(index));

        MStringArray result;
        result.append(severityToString(rec.severity));
        result.append(MString(rec.message.c_str()));
        result.append(MString(rec.errorHash.c_str()));
        result.append(MString(rec.context.nodeType.c_str()));
        result.append(MString(rec.context.attributeName.c_str()));
        result.append(MString(rec.context.activeCommand.c_str()));
        result.append(MString(rec.context.axisOrTarget.c_str()));
        result.append(MString(rec.remedy.c_str()));
        result.append(rec.servedFromBook ? "1" : "0");
        setResult(result);
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroDiagQuery failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroDiagQuery failed with unknown error.");
        return MS::kFailure;
    }
}

}  // namespace maro
```

- [ ] **Step 6: CMake·플러그인 진입점 배선**

`src/maro_plugin/CMakeLists.txt`의 `SOURCE_FILES`에 추가:

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
)
```

`target_link_libraries(${PROJECT_NAME} maro_transform)` 바로 아래에 추가:

```cmake
target_link_libraries(${PROJECT_NAME} maro_diag)
```

`src/maro_plugin/MaroPluginMain.cpp` 상단 include에 추가:

```cpp
#include "MaroDiagCommands.h"
```

`initializePlugin`의 `maro::MaroDeleteWatcher::install()` 호출 앞에 추가:

```cpp
    status = plugin.registerCommand("maroDiagEmit", maro::MaroDiagEmitCommand::creator,
                                    maro::MaroDiagEmitCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroDiagEmit");
        return status;
    }

    status = plugin.registerCommand("maroDiagCount", maro::MaroDiagCountCommand::creator);
    if (!status) {
        status.perror("Maro: failed to register maroDiagCount");
        return status;
    }

    status = plugin.registerCommand("maroDiagQuery", maro::MaroDiagQueryCommand::creator,
                                    maro::MaroDiagQueryCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroDiagQuery");
        return status;
    }
```

`uninitializePlugin`의 `maro::MaroDeleteWatcher::uninstall();` 바로 아래에 추가(등록의 역순):

```cpp
    plugin.deregisterCommand("maroDiagQuery");
    plugin.deregisterCommand("maroDiagCount");
    plugin.deregisterCommand("maroDiagEmit");
```

`tests/CMakeLists.txt`의 "플러그인만 있으면 되는 테스트" `foreach` 목록에 `diag_boad`를 추가:

```cmake
    foreach(maya_test load axis_node binding capability_stack delete_rules
                      robustness diag_boad)
```

- [ ] **Step 7: 빌드하고 테스트가 통과하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake -S . -B out/build -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_TOOLCHAIN_FILE=C:/src/vcpkg/scripts/buildsystems/vcpkg.cmake -DMARO_BUILD_PLUGIN=ON
cmake --build out/build
```

```bash
ctest --test-dir out/build --output-on-failure -R maya_diag_boad
```

기대: `maya_diag_boad` 통과. `ctest --test-dir out/build --output-on-failure`로 나머지 기존 테스트도 전부 여전히 통과하는지 확인한다.

- [ ] **Step 8: 스트림 순서 보장을 테스트가 실제로 지키는지 확인**

`MaroDiag.cpp`의 `recordAt`에서 `-1`을 빼먹은 버그를 흉내낸다:

```cpp
const DiagRecord& BoadMaro::recordAt(std::size_t indexFromEnd) {
    return stream().at(stream().size() - indexFromEnd);
}
```

```bash
cmake --build out/build
```

```bash
ctest --test-dir out/build --output-on-failure -R maya_diag_boad
```

기대: `index 0`이 `stream().at(size())`를 가리켜 범위를 벗어나므로 `MaroDiagQueryCommand::doIt`이 예외를 잡아 `MS::kFailure`를 내고, Python 쪽 `cmds.maroDiagQuery(index=0)` 호출이 `RuntimeError`를 던져 테스트가 트레이스백과 함께 **실패**한다. 확인했으면 `-1`을 되돌리고 다시 빌드해 통과를 본다.

- [ ] **Step 9: 커밋**

```bash
git add src/maro_plugin tests/CMakeLists.txt tests/maya/test_diag_boad.py
git commit -m "feat: add boad diagnostic sink with an in-memory record stream"
```

---

### Task 4: `onfix` DG 컨텍스트 포착과 커맨드 컨텍스트 스택

원인 분석의 핵심이다. `ScopedCommandContext`(RAII 마커)를 `MaroBindAxisCommand::doIt` 진입 시 설치하고, "transform이 아닌 대상에 바인딩" 거부 경로 하나를 `BoadMaro::error`로 옮겨 실제 노드 타입·어트리뷰트·커맨드·축 값이 기록되는지 값으로 단언한다. 나머지 71개 호출부의 전면 전환은 Task 7이다 — 여기서는 메커니즘 하나가 옳다는 것부터 증명한다.

**Files:**
- Modify: `src/maro_plugin/MaroDiag.h` / `.cpp` — `ScopedCommandContext`, `onfix::activeCommand()`, `onfix::capture()`
- Modify: `src/maro_plugin/MaroCommands.cpp` — `MaroBindAxisCommand::doIt`에 마커 설치 + `TargetNotTransform` 사이트 전환
- Test: `tests/maya/test_diag_onfix.py`
- Modify: `tests/CMakeLists.txt` — `maya_diag_onfix` 등록

**Interfaces:**
- Consumes: `maro::BoadMaro::error` (Task 3)
- Produces: `maro::ScopedCommandContext`, `maro::onfix::activeCommand()`, `maro::onfix::capture(nodeType, attributeName, axisOrTarget)`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/maya/test_diag_onfix.py`:

```python
"""onfix DG 컨텍스트 포착: 실제 노드 타입·어트리뷰트·커맨드가 기록되는지
확인한다. "값이 무엇인지"를 단언한다 -- "뭔가 기록됐다"가 아니다."""
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

before = cmds.maroDiagCount()

# transform이 아닌 대상에 바인딩을 시도한다 (test_binding.py의 3번 시나리오와 동일).
light = cmds.createNode("pointLight", name="rejectLight")
axis = cmds.createNode("maroAxis", name="rejectAxis")
try:
    cmds.maroBindAxis(axis, light)
    raise AssertionError("binding to a non-transform should have been rejected")
except RuntimeError:
    pass

after = cmds.maroDiagCount()
assert after == before + 1, (
    f"expected exactly one new diagnostic record from the rejection, "
    f"got {after - before}"
)
print("record emitted OK")

rec = cmds.maroDiagQuery(index=0)
severity, message, errorHash, nodeType, attributeName, activeCommand, axisOrTarget, remedy, servedFromBook = rec

assert severity == "error", f"expected severity 'error', got {severity!r}"
assert nodeType == "pointLight", f"expected nodeType 'pointLight', got {nodeType!r}"
assert attributeName == "targetObject", f"expected attributeName 'targetObject', got {attributeName!r}"
assert activeCommand == "MaroBindAxisCommand", (
    f"expected activeCommand 'MaroBindAxisCommand', got {activeCommand!r}"
)
assert axisOrTarget == "rejectAxis", f"expected axisOrTarget 'rejectAxis', got {axisOrTarget!r}"
print("DG context values OK")

# 커맨드 컨텍스트 스택이 doIt 반환 후 확실히 비었는지 -- maroDiagEmit은
# 마커를 설치하지 않는 테스트 도구이므로, 그 에러의 activeCommand가 비어
# 있어야 위 마커가 새지 않고 정확히 pop됐다는 뜻이다.
cmds.maroDiagEmit(severity="error", message="probe", siteTag="Test.Probe")
probe = cmds.maroDiagQuery(index=0)
assert probe[5] == "", f"expected empty activeCommand after doIt returned, got {probe[5]!r}"
print("stack unwound OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

`tests/CMakeLists.txt`에는 아직 등록하지 않고, Task 3까지의 빌드로 직접 돌려 본다.

```bash
MARO_PLUGIN_PATH="$(cygpath -w "$(find out/build -name maro.mll | head -1)")" "/c/Program Files/Autodesk/Maya2026/bin/mayapy.exe" tests/maya/test_diag_onfix.py
```

기대: `nodeType` 등 컨텍스트 필드가 전부 빈 문자열(`MaroBindAxisCommand::doIt`이 아직 `BoadMaro::error`를 안 부르므로 이 거부는 스트림에 레코드를 전혀 남기지 않는다)이라 `after == before + 1` 단언에서 **실패**한다.

- [ ] **Step 3: `ScopedCommandContext`와 `onfix` 추가**

`MaroDiag.h`에 `class BoadMaro { ... };` 선언 뒤, `MARO_ASSERT` 매크로 앞에 추가:

```cpp
// 진행 중인 커맨드 이름의 스택. MPxCommand::doIt 진입 시 설치되고 함수가
// 반환하면 자동으로 해제된다. onfix가 "어느 커맨드가 관여했는지"를 아는
// 유일한 경로다 (설계 스펙 §4 onfix 행 "커맨드").
class ScopedCommandContext {
public:
    explicit ScopedCommandContext(const char* commandName);
    ~ScopedCommandContext();

    ScopedCommandContext(const ScopedCommandContext&) = delete;
    ScopedCommandContext& operator=(const ScopedCommandContext&) = delete;
};

namespace onfix {

// 현재 활성 커맨드 이름. 스택이 비어 있으면 빈 문자열.
std::string activeCommand();

// 에러 시점의 DG 컨텍스트를 조립한다. 노드 타입·어트리뷰트·축/대상은
// 호출부가 건넨다 -- boad/onfix는 Maya 씬을 스스로 훑지 않는다. 사건이
// 일어난 그 자리에서만 정확히 안다(감시자가 Maya 주소공간을 못 보는 것과
// 같은 이유로, 포착은 항상 발생지에서 한다는 원칙을 여기서도 지킨다).
// activeCommand는 항상 여기서 스택으로부터 채운다 -- 호출부가 직접 쓰지 않는다.
DgContext capture(const MString& nodeType, const MString& attributeName,
                   const MString& axisOrTarget);

}  // namespace onfix
```

`MaroDiag.cpp`에서 `namespace maro {` 선언부 끝(파일 맨 아래, `}  // namespace maro` 앞)에 추가:

```cpp
namespace {
// Maya 메인 스레드만 doIt을 부르지만, thread_local로 두면 우연한 재진입도 안전하다.
thread_local std::vector<std::string> g_commandStack;
}  // namespace

ScopedCommandContext::ScopedCommandContext(const char* commandName) {
    g_commandStack.emplace_back(commandName);
}

ScopedCommandContext::~ScopedCommandContext() {
    if (!g_commandStack.empty()) g_commandStack.pop_back();
}

namespace onfix {

std::string activeCommand() {
    return g_commandStack.empty() ? std::string() : g_commandStack.back();
}

DgContext capture(const MString& nodeType, const MString& attributeName,
                   const MString& axisOrTarget) {
    DgContext ctx;
    ctx.nodeType = nodeType.asChar();
    ctx.attributeName = attributeName.asChar();
    ctx.axisOrTarget = axisOrTarget.asChar();
    ctx.activeCommand = activeCommand();
    return ctx;
}

}  // namespace onfix
```

- [ ] **Step 4: `MaroBindAxisCommand::doIt`에 마커 설치와 사이트 전환**

`src/maro_plugin/MaroCommands.cpp`의 `MaroBindAxisCommand::doIt` 시작부를 아래로 교체:

```cpp
MStatus MaroBindAxisCommand::doIt(const MArgList& args) {
    maro::ScopedCommandContext ctxMarker("MaroBindAxisCommand");
    // 예외는 경계를 넘지 않는다. 커맨드에서 던지면 Maya가 죽는다.
    try {
        MStatus status;
```

"transform이 아닌 대상" 거부 블록을 아래로 교체:

```cpp
        // 규칙: 회전 가능한 transform에만 바인딩한다.
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

`MaroCommands.cpp` 상단 include에 `#include "MaroDiag.h"`를 추가한다.

`tests/CMakeLists.txt`의 "플러그인만 있으면 되는 테스트" `foreach` 목록에 `diag_onfix`를 추가:

```cmake
    foreach(maya_test load axis_node binding capability_stack delete_rules
                      robustness diag_boad diag_onfix)
```

- [ ] **Step 5: 빌드하고 테스트가 통과하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build
```

```bash
ctest --test-dir out/build --output-on-failure -R maya_diag_onfix
```

기대: `maya_diag_onfix` 통과. 전체 스위트도 회귀 없이 통과하는지 `ctest --test-dir out/build --output-on-failure`로 확인한다.

- [ ] **Step 6: 컨텍스트 값이 실제로 지켜지는지 확인**

`MaroCommands.cpp`의 `onfix::capture(...)` 호출에서 `axisFn.name()`과 `targetFn.name()`을 바꿔치기해 `axisOrTarget` 자리에 대상 오브젝트 이름이 들어가게 만든다.

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure -R maya_diag_onfix
```

기대: `axisOrTarget == "rejectAxis"` 단언이 `"rejectLight"`를 받아 **실패**한다. 확인했으면 원래대로(`axisFn.name()`) 되돌리고 다시 빌드해 통과를 본다.

- [ ] **Step 7: 커밋**

```bash
git add src/maro_plugin tests/CMakeLists.txt tests/maya/test_diag_onfix.py
git commit -m "feat: capture DG context via onfix and a command context stack"
```

---

### Task 5: `book` 연동 — 기지 에러 즉답과 스필 쓰기

`BoadMaro::error()`를 완성한다: 해시를 계산하고, 정본+스필을 병합 조회해서 있으면 캐시로 즉답하고, 없으면 새로 기록해 스필에 남긴다. book 파일 경로는 실제 사용자 디렉터리(`internalVar -userAppDir`)를 기본으로 쓰되, 테스트가 매 실행마다 깨끗한 book으로 시작할 수 있도록 `MARO_DIAG_BOOK_DIR` 환경변수로 재정의할 수 있게 한다 — 안 그러면 `ctest`를 두 번 돌렸을 때 첫 실행이 남긴 지식 때문에 두 번째 실행의 "새 분석" 단언이 항상 깨진다.

**Files:**
- Modify: `src/maro_plugin/MaroDiag.h` / `.cpp` — `bookPaths()`, book 연동, `freshAnalysisCount()`
- Modify: `src/maro_plugin/MaroDiagCommands.h` / `.cpp` — `MaroDiagAnalysisCountCommand`
- Modify: `src/maro_plugin/MaroPluginMain.cpp` — 커맨드 등록/해제
- Test: `tests/maya/test_diag_book.py`
- Modify: `tests/CMakeLists.txt` — `maya_diag_book` 등록

**Interfaces:**
- Consumes: `maro::BookStore`(Task 2), `maro::onfix`(Task 4)
- Produces: `maro::BoadMaro::freshAnalysisCount()`, MEL 커맨드 `maroDiagAnalysisCount`, 환경변수 `MARO_DIAG_BOOK_DIR`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/maya/test_diag_book.py`:

```python
"""기지 에러 즉답: 같은 에러를 두 번 유발하면 두 번째는 book에서 즉답으로
나오고 재분석(신규 분석 카운트 증가)이 일어나지 않는지 확인한다."""
import os
import sys
import tempfile

import maya.standalone

# book 파일을 이 테스트 전용 임시 디렉터리로 돌린다. 실제
# internalVar -userAppDir를 쓰면 반복 실행마다 지식이 쌓여 재현이 안 된다.
os.environ["MARO_DIAG_BOOK_DIR"] = tempfile.mkdtemp(prefix="maro_diag_book_")

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

light = cmds.createNode("pointLight", name="rejectLight")
axis = cmds.createNode("maroAxis", name="rejectAxis")

analysisBefore = cmds.maroDiagAnalysisCount()

# 1회차: book에 없으므로 새로 분석하고 스필에 남긴다.
try:
    cmds.maroBindAxis(axis, light)
    raise AssertionError("expected rejection")
except RuntimeError:
    pass

analysisAfterFirst = cmds.maroDiagAnalysisCount()
assert analysisAfterFirst == analysisBefore + 1, "first occurrence should trigger fresh analysis"

first = cmds.maroDiagQuery(index=0)
assert first[8] == "0", "first occurrence must not claim it was served from book"
print("first occurrence OK")

# 2회차: 완전히 같은 사이트(같은 노드 타입/커맨드)이므로 해시가 같다.
try:
    cmds.maroBindAxis(axis, light)
    raise AssertionError("expected rejection")
except RuntimeError:
    pass

analysisAfterSecond = cmds.maroDiagAnalysisCount()
assert analysisAfterSecond == analysisAfterFirst, (
    f"second occurrence must NOT trigger a new analysis, "
    f"count went {analysisAfterFirst} -> {analysisAfterSecond}"
)

second = cmds.maroDiagQuery(index=0)
assert second[8] == "1", "second occurrence must be served from book"
assert second[2] == first[2], "same failure must hash the same both times"
assert first[1] in second[1], "the cached message should carry the original analysis text forward"
print("second occurrence served from book OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
MARO_PLUGIN_PATH="$(cygpath -w "$(find out/build -name maro.mll | head -1)")" "/c/Program Files/Autodesk/Maya2026/bin/mayapy.exe" tests/maya/test_diag_book.py
```

기대: `cmds.maroDiagAnalysisCount()`에서 `RuntimeError: Unknown Maya command 'maroDiagAnalysisCount'`로 실패.

- [ ] **Step 3: `BoadMaro::error()`에 book 연동**

`MaroDiag.h`의 `BoadMaro` 클래스에 추가:

```cpp
    // book에서 실제로 새로 분석한(캐시 미스) 횟수. "기지 에러 즉답" 검증에 쓴다.
    static std::size_t freshAnalysisCount();
```

`MaroDiag.h` 상단 include에 `#include "maro_diag/BookStore.h"`와 `#include "maro_diag/ErrorHash.h"`를 추가한다.

`MaroDiag.cpp`를 아래로 갱신한다. `#include <cstdlib>`와 `#include <filesystem>`을 상단에 추가하고, 익명 네임스페이스에 `bookPaths()`를 추가하며, `error()`를 book 연동 버전으로 교체한다.

```cpp
namespace {

std::size_t g_freshAnalysisCount = 0;

struct BookPaths {
    std::filesystem::path canonical;
    std::filesystem::path spill;
};

// 기본은 원안(Maro_DebugUtility/book_Maro.cpp)과 같은 위치다:
// internalVar -userAppDir. MARO_DIAG_BOOK_DIR이 설정돼 있으면 그것을
// 우선한다 -- 테스트가 매 실행마다 깨끗한 book으로 시작하기 위한 재정의다.
const BookPaths& bookPaths() {
    static const BookPaths paths = [] {
        BookPaths p;
        std::filesystem::path dir;
        if (const char* override_ = std::getenv("MARO_DIAG_BOOK_DIR")) {
            dir = override_;
        } else {
            const MString userAppDir =
                MGlobal::executeCommandStringResult("internalVar -userAppDir");
            dir = userAppDir.length() > 0 ? std::filesystem::path(userAppDir.asChar())
                                           : std::filesystem::temp_directory_path();
        }
        p.canonical = dir / "maro_knowledge.jsonl";
        p.spill = dir / "maro_knowledge.spill.jsonl";
        return p;
    }();
    return paths;
}

}  // namespace
```

`error()`를 아래로 교체:

```cpp
void BoadMaro::error(const std::string& siteTag, const MString& message,
                      const DgContext& context) {
    DiagRecord rec;
    rec.severity = DiagSeverity::Error;
    rec.context = context;

    try {
        const std::string hash = hashError(siteTag);
        rec.errorHash = hash;

        const BookPaths& paths = bookPaths();
        const BookStore store = BookStore::loadMerged(paths.canonical, paths.spill);

        BookEntry entry;
        if (store.query(hash, entry)) {
            rec.message = entry.analysis + "\n(Maro: book에 있는 과거 분석에서 즉답)";
            rec.remedy = entry.remedy;
            rec.servedFromBook = true;
        } else {
            rec.message = message.asChar();
            rec.servedFromBook = false;

            BookEntry fresh;
            fresh.analysis = rec.message;
            fresh.context = context;
            BookStore::appendToSpill(paths.spill, hash, fresh);
            ++g_freshAnalysisCount;
        }
    } catch (const std::exception& e) {
        // book이 죽어도 진단은 죽지 않는다 (스펙 §3.6). 이 실패 자체는
        // 재귀적으로 error()를 부르지 않고 devInfo로만 남긴다.
        rec.message = message.asChar();
        rec.servedFromBook = false;
        ++g_freshAnalysisCount;
        devInfo(MString("Maro: book 조회/기록 실패, 로컬 기록으로 진행: ") + e.what());
    } catch (...) {
        rec.message = message.asChar();
        rec.servedFromBook = false;
        ++g_freshAnalysisCount;
        devInfo("Maro: book 조회/기록에서 알 수 없는 오류, 로컬 기록으로 진행.");
    }

    MGlobal::displayError(MString("[Maro-Error] ") + MString(rec.message.c_str()));
    stream().push_back(std::move(rec));
}

std::size_t BoadMaro::freshAnalysisCount() { return g_freshAnalysisCount; }
```

`resetForTest()`에 카운터 초기화를 추가:

```cpp
void BoadMaro::resetForTest() {
    stream().clear();
    g_freshAnalysisCount = 0;
}
```

- [ ] **Step 4: `maroDiagAnalysisCount` 커맨드 추가**

`MaroDiagCommands.h`에 추가:

```cpp
// 인자 없음. book 캐시 미스로 실제 새 분석을 기록한 누적 횟수.
class MaroDiagAnalysisCountCommand : public MPxCommand {
public:
    static void* creator();
    MStatus doIt(const MArgList& args) override;
};
```

`MaroDiagCommands.cpp`의 `MaroDiagQueryCommand::doIt` 정의 뒤에 추가:

```cpp
void* MaroDiagAnalysisCountCommand::creator() { return new MaroDiagAnalysisCountCommand(); }

MStatus MaroDiagAnalysisCountCommand::doIt(const MArgList& /*args*/) {
    setResult(static_cast<int>(BoadMaro::freshAnalysisCount()));
    return MS::kSuccess;
}
```

`MaroPluginMain.cpp`의 `maroDiagQuery` 등록 뒤에 추가:

```cpp
    status = plugin.registerCommand("maroDiagAnalysisCount",
                                    maro::MaroDiagAnalysisCountCommand::creator);
    if (!status) {
        status.perror("Maro: failed to register maroDiagAnalysisCount");
        return status;
    }
```

`uninitializePlugin`의 `maroDiagQuery` 해제 앞에 추가:

```cpp
    plugin.deregisterCommand("maroDiagAnalysisCount");
```

`tests/CMakeLists.txt`의 `foreach` 목록에 `diag_book`을 추가:

```cmake
    foreach(maya_test load axis_node binding capability_stack delete_rules
                      robustness diag_boad diag_onfix diag_book)
```

- [ ] **Step 5: 빌드하고 테스트가 통과하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build
```

```bash
ctest --test-dir out/build --output-on-failure -R maya_diag_book
```

기대: `maya_diag_book` 통과. 두 번 연속 돌려도(book 디렉터리를 매번 새로 만드므로) 결과가 같은지 확인한다.

- [ ] **Step 6: "재분석하지 않는다"를 테스트가 실제로 지키는지 확인**

`error()`의 `if (store.query(hash, entry))` 분기 안에서도 `++g_freshAnalysisCount;`가 실행되도록(캐시 히트에서도 카운터를 올리는 버그를 흉내내어) 그 줄을 임시로 추가한다.

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure -R maya_diag_book
```

기대: `analysisAfterSecond == analysisAfterFirst` 단언이 `analysisAfterFirst + 1`을 받아 **실패**한다. 확인했으면 추가한 줄을 지우고 다시 빌드해 통과를 본다.

- [ ] **Step 7: 커밋**

```bash
git add src/maro_plugin tests/CMakeLists.txt tests/maya/test_diag_book.py
git commit -m "feat: wire boad's error path to book for instant answers on repeat errors"
```

---

### Task 6: 해법 등록·제시와 감시자 없는 강등

`BoadMaro::registerRemedy()`를 추가한다 — 사용자가 스스로 고친 방법을 book에 등록하면, 같은 에러가 다시 났을 때 제시된다(적용은 Layer B). 그리고 book 파일 자체를 쓸 수 없는 상황(디렉터리를 만들 수 없음)에서도 진단이 절대 죽지 않고, 다만 지식이 못 쌓일 뿐이라는 것을 별도 프로세스로 증명한다.

**Files:**
- Modify: `src/maro_plugin/MaroDiag.h` / `.cpp` — `registerRemedy()`
- Modify: `src/maro_plugin/MaroDiagCommands.h` / `.cpp` — `MaroDiagRegisterRemedyCommand`
- Modify: `src/maro_plugin/MaroPluginMain.cpp` — 커맨드 등록/해제
- Test: `tests/maya/test_diag_remedy.py`, `tests/maya/test_diag_degraded.py`
- Modify: `tests/CMakeLists.txt` — 두 테스트 등록

**Interfaces:**
- Consumes: `maro::BoadMaro::error`(Task 5), `maro::BookStore`(Task 2)
- Produces: `maro::BoadMaro::registerRemedy(errorHash, remedyText)`, MEL 커맨드 `maroDiagRegisterRemedy`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/maya/test_diag_remedy.py`:

```python
"""해법 등록: 사용자가 스스로 해결한 방법을 등록하면 같은 에러 재발 시
제시되는지 확인한다."""
import os
import sys
import tempfile

import maya.standalone

os.environ["MARO_DIAG_BOOK_DIR"] = tempfile.mkdtemp(prefix="maro_diag_remedy_")

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

light = cmds.createNode("pointLight", name="remedyLight")
axis = cmds.createNode("maroAxis", name="remedyAxis")

try:
    cmds.maroBindAxis(axis, light)
    raise AssertionError("expected rejection")
except RuntimeError:
    pass

firstRecord = cmds.maroDiagQuery(index=0)
errorHash = firstRecord[2]
assert errorHash, "expected a non-empty error hash"
assert firstRecord[7] == "", "no remedy should exist yet"
print("no remedy before registration OK")

cmds.maroDiagRegisterRemedy(hash=errorHash, remedy="Select the transform, not its shape.")
print("remedy registered OK")

try:
    cmds.maroBindAxis(axis, light)
    raise AssertionError("expected rejection")
except RuntimeError:
    pass

secondRecord = cmds.maroDiagQuery(index=0)
assert secondRecord[7] == "Select the transform, not its shape.", (
    f"expected the registered remedy on recurrence, got {secondRecord[7]!r}"
)
assert secondRecord[8] == "1", "recurrence with a registered remedy is served from book"
print("remedy offered on recurrence OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
```

`tests/maya/test_diag_degraded.py`:

```python
"""강등: 감시자는 애초에 없고(Layer A), book 파일마저 쓸 수 없을 때도 진단이
계속 동작하는지 확인한다 (설계 스펙 §3.6, §5.4)."""
import os
import sys
import tempfile

import maya.standalone

# 부모가 "디렉터리"가 아니라 평범한 파일이 되게 만들어, book 경로 아래
# create_directories가 항상 실패하게 강제한다.
parentDir = tempfile.mkdtemp(prefix="maro_diag_degraded_")
blockerFile = os.path.join(parentDir, "blocker")
with open(blockerFile, "w") as f:
    f.write("this occupies the path a directory would need")

os.environ["MARO_DIAG_BOOK_DIR"] = os.path.join(blockerFile, "nested", "book")

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

light = cmds.createNode("pointLight", name="degradedLight")
axis = cmds.createNode("maroAxis", name="degradedAxis")

countBefore = cmds.maroDiagCount()
analysisBefore = cmds.maroDiagAnalysisCount()

# book을 쓸 수 없는 상태에서 같은 에러를 두 번 유발한다. 둘 다 정상적으로
# RuntimeError로 거부돼야 한다 -- 여기서 예외가 Maya 콜백 경계를 넘으면 이
# 스크립트 자체가 트레이스백과 함께 죽고 "teardown OK"에 닿지 못한다.
for _ in range(2):
    try:
        cmds.maroBindAxis(axis, light)
        raise AssertionError("expected rejection")
    except RuntimeError:
        pass

countAfter = cmds.maroDiagCount()
analysisAfter = cmds.maroDiagAnalysisCount()

assert countAfter == countBefore + 2, "diagnostics must keep flowing even if book can't persist"
print("diagnostics kept flowing OK")

# book이 아무것도 저장할 수 없으므로 두 번째 발생도 "새 분석"으로 취급된다
# -- 캐시 히트를 거짓으로 주장하지 않는다는 뜻이다.
assert analysisAfter == analysisBefore + 2, (
    f"with book unwritable, every occurrence must be treated as fresh, "
    f"count went {analysisBefore} -> {analysisAfter}"
)
print("no false cache hits under degrade OK")

latest = cmds.maroDiagQuery(index=0)
assert latest[8] == "0", "degraded book must never claim servedFromBook"
print("servedFromBook stayed honest OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
MARO_PLUGIN_PATH="$(cygpath -w "$(find out/build -name maro.mll | head -1)")" "/c/Program Files/Autodesk/Maya2026/bin/mayapy.exe" tests/maya/test_diag_remedy.py
```

기대: `cmds.maroDiagRegisterRemedy(...)`에서 `RuntimeError: Unknown Maya command 'maroDiagRegisterRemedy'`로 실패. `test_diag_degraded.py`는 이 단계에서는 이미 통과할 수도 있다(등록 커맨드를 안 쓰므로) — Task 6의 진짜 새 동작은 `registerRemedy`이므로 그 실패로 충분하다.

- [ ] **Step 3: `BoadMaro::registerRemedy()` 구현**

`MaroDiag.h`의 `BoadMaro` 클래스에 추가:

```cpp
    // 실패 해시에 해법을 등록한다. 이미 book에 있는 항목이면 분석은 남기고
    // 해법만 갱신한다. 아직 없는 해시면 분석 없이 해법만 있는 항목을 새로
    // 만든다 (사용자가 스스로 고친 뒤 등록하는 경우 -- 스펙 §4.3 "해법이
    // 없는 에러는 ... 사용자가 등록할 수 있게 한다").
    static void registerRemedy(const std::string& errorHash, const MString& remedyText);
```

`MaroDiag.cpp`의 `freshAnalysisCount()` 정의 뒤에 추가:

```cpp
void BoadMaro::registerRemedy(const std::string& errorHash, const MString& remedyText) {
    try {
        const BookPaths& paths = bookPaths();
        const BookStore store = BookStore::loadMerged(paths.canonical, paths.spill);

        BookEntry entry;
        store.query(errorHash, entry);  // 없으면 entry는 기본값(빈 분석)으로 남는다.
        entry.remedy = remedyText.asChar();

        BookStore::appendToSpill(paths.spill, errorHash, entry);
    } catch (const std::exception& e) {
        devInfo(MString("Maro: 해법 등록 실패: ") + e.what());
    } catch (...) {
        devInfo("Maro: 해법 등록에서 알 수 없는 오류.");
    }
}
```

- [ ] **Step 4: `maroDiagRegisterRemedy` 커맨드 추가**

`MaroDiagCommands.h`에 추가:

```cpp
// -hash <string> -remedy <string>
class MaroDiagRegisterRemedyCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
};
```

`MaroDiagCommands.cpp`의 익명 네임스페이스에 플래그 상수를 추가:

```cpp
const char* kHashFlag = "-h";
const char* kHashFlagLong = "-hash";
const char* kRemedyFlag = "-r";
const char* kRemedyFlagLong = "-remedy";
```

파일 끝(`}  // namespace maro` 앞)에 추가:

```cpp
void* MaroDiagRegisterRemedyCommand::creator() { return new MaroDiagRegisterRemedyCommand(); }

MSyntax MaroDiagRegisterRemedyCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag(kHashFlag, kHashFlagLong, MSyntax::kString);
    syntax.addFlag(kRemedyFlag, kRemedyFlagLong, MSyntax::kString);
    return syntax;
}

MStatus MaroDiagRegisterRemedyCommand::doIt(const MArgList& args) {
    try {
        MStatus status;
        MArgDatabase argData(newSyntax(), args, &status);
        if (!status) return status;

        if (!argData.isFlagSet(kHashFlag) || !argData.isFlagSet(kRemedyFlag)) {
            MGlobal::displayError("Maro: maroDiagRegisterRemedy needs -hash and -remedy.");
            return MS::kFailure;
        }

        MString hash;
        MString remedy;
        argData.getFlagArgument(kHashFlag, 0, hash);
        argData.getFlagArgument(kRemedyFlag, 0, remedy);

        BoadMaro::registerRemedy(hash.asChar(), remedy);
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroDiagRegisterRemedy failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroDiagRegisterRemedy failed with unknown error.");
        return MS::kFailure;
    }
}
```

`MaroPluginMain.cpp`의 `maroDiagAnalysisCount` 등록 뒤에 추가:

```cpp
    status = plugin.registerCommand("maroDiagRegisterRemedy",
                                    maro::MaroDiagRegisterRemedyCommand::creator,
                                    maro::MaroDiagRegisterRemedyCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroDiagRegisterRemedy");
        return status;
    }
```

`uninitializePlugin`의 `maroDiagAnalysisCount` 해제 앞에 추가:

```cpp
    plugin.deregisterCommand("maroDiagRegisterRemedy");
```

`tests/CMakeLists.txt`의 `foreach` 목록에 `diag_remedy`와 `diag_degraded`를 추가:

```cmake
    foreach(maya_test load axis_node binding capability_stack delete_rules
                      robustness diag_boad diag_onfix diag_book diag_remedy
                      diag_degraded)
```

- [ ] **Step 5: 빌드하고 테스트가 통과하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build
```

```bash
ctest --test-dir out/build --output-on-failure -R "maya_diag_remedy|maya_diag_degraded"
```

기대: 둘 다 통과.

- [ ] **Step 6: 해법 등록과 강등 검사가 실제로 지켜지는지 확인**

두 가지를 순서대로 깬다.

(a) 해법 등록: `BoadMaro::registerRemedy()`에서 `BookStore::appendToSpill(...)` 호출을 주석 처리해 등록을 무의미하게 만든다.

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure -R maya_diag_remedy
```

기대: `secondRecord[7] == "Select the transform, not its shape."` 단언이 빈 문자열을 받아 **실패**한다. 확인했으면 되돌린다.

(b) 강등: `error()`의 catch 블록에서 `++g_freshAnalysisCount;`를 지워, book 쓰기가 실패했는데도 분석이 일어난 것으로 계수하지 않게(즉 카운트가 정체되게) 만든다.

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure -R maya_diag_degraded
```

기대: `analysisAfter == analysisBefore + 2` 단언이 `analysisBefore`(증가 없음)를 받아 **실패**한다. 확인했으면 되돌리고 두 테스트 모두 다시 통과하는지 본다.

- [ ] **Step 7: 커밋**

```bash
git add src/maro_plugin tests/CMakeLists.txt tests/maya/test_diag_remedy.py tests/maya/test_diag_degraded.py
git commit -m "feat: add remedy registration and verify graceful degrade without book access"
```

---

### Task 7: 기존 72개 진단 호출과 나머지 커맨드의 `boad`/`onfix` 전환

Task 1~6이 메커니즘을 세우고 `MaroBindAxisCommand`의 사이트 하나로 증명했다. 이 태스크는 그 메커니즘을 `src/maro_plugin/*.cpp`의 나머지로 넓힌다 — `MGlobal::display{Info,Warning,Error}` 72곳 전부, 그리고 아직 마커가 없는 `MPxCommand::doIt` 5곳.

**대상 확정**: `MGlobal::display` 호출은 정확히 72곳이다(아래로 재확인 가능). `status.perror(...)` 호출(주로 `MaroPluginMain.cpp`의 "failed to register X" 13곳)은 이 72개에 **포함되지 않는다** — 스펙이 말하는 것은 `display*` 계열이고, `perror`는 플러그인 등록 단계의 별도 관용구다. 이 태스크에서 건드리지 않는다.

```bash
grep -rc "MGlobal::display" src/maro_plugin/MaroAxisNode.cpp src/maro_plugin/MaroCapabilityNodes.cpp src/maro_plugin/MaroCommandDeviceNode.cpp src/maro_plugin/MaroCommands.cpp src/maro_plugin/MaroDeleteWatcher.cpp src/maro_plugin/MaroPluginMain.cpp src/maro_plugin/MaroPump.cpp
```

기대 (이관 전): `MaroAxisNode.cpp:3`, `MaroCapabilityNodes.cpp:4`, `MaroCommandDeviceNode.cpp:11`, `MaroCommands.cpp:45`, `MaroDeleteWatcher.cpp:5`, `MaroPluginMain.cpp:2`, `MaroPump.cpp:2` (합 72).

**Files:**
- Modify: `src/maro_plugin/MaroAxisNode.cpp`, `MaroCapabilityNodes.cpp`, `MaroCommandDeviceNode.cpp`, `MaroCommands.cpp`, `MaroDeleteWatcher.cpp`, `MaroPluginMain.cpp`, `MaroPump.cpp`
- Test: 기존 `tests/maya/*.py` 전체(신규 파일 없음) — 이 태스크는 동작을 보존하는 리팩터링이므로 새 시나리오가 아니라 회귀 부재를 증명한다.

**Interfaces:**
- Consumes: `maro::BoadMaro::info/warn/error`, `maro::ScopedCommandContext`, `maro::onfix::capture`(Task 3~5)
- Produces: 없음(신규 API 없음) — 72개 호출부와 5개 `doIt`의 내부 구현만 바뀐다. 모든 커맨드의 `MStatus` 리턴값과 사용자 관측 동작(스크립트 에디터에 뭔가 뜬다, `cmds.xxx()`가 실패 시 `RuntimeError`를 던진다)은 그대로다 — `boad`가 무엇을 하는지가 바뀔 뿐 커맨드가 무엇을 돌려주는지는 안 바뀐다.

**전환 규칙 (기계적, 세 가지)**

- **규칙 A — catch 블록의 예외 로그.** `catch (const std::exception& e) { MGlobal::displayError(MString("Maro: X failed: ") + e.what()); }` / `catch (...) { MGlobal::displayError("Maro: X failed with unknown error."); }` 형태는 각각 `maro::BoadMaro::error("<Class>.<Method>.Exception", ...)` / `"<Class>.<Method>.UnknownException"`로 바꾼다. 이 두 사이트 태그만으로 함수당 카테고리가 갈린다 — 노드/축 정보가 없는 자리이므로 `onfix::capture("", "", "")`로 `activeCommand`만 채운다(빈 문자열도 유효한 값이다, Task 1 `DgContext` 설계).
- **규칙 B — 정보/경고 로그(에러가 아닌 것).** `MGlobal::displayInfo(X)` → `maro::BoadMaro::info(X)`, `MGlobal::displayWarning(X)` → `maro::BoadMaro::warn(X)`. 순수 개명이다 — 시그니처가 문자열 하나뿐이라 book/사이트 태그가 필요 없다. 주변의 "상태 변화 시 1회만" 같은 가드 로직은 그대로 둔다.
- **규칙 C — 검증 실패로 `MS::kFailure`를 반환하는 자리(주로 `MaroCommands.cpp`).** `maro::BoadMaro::error("<Class>.<ShortReason>", <같은 MString 표현식>, maro::onfix::capture(nodeType, attribute, axisOrTarget))`로 바꾼다. 아직 노드를 못 찾은 인자 검증 단계(예: 인자 개수 오류)에는 `onfix::capture("", "", "")`를 쓴다. **모든 `MPxCommand::doIt`은 진입 시 `maro::ScopedCommandContext ctxMarker("<ClassName>")`을 설치한다** — Task 4가 `MaroBindAxisCommand`에 설치한 것과 동일하게, 아직 없는 `MaroSetControlModeCommand`, `MaroConnectAxisCommand`, `MaroStartBridgeCommand`, `MaroStopBridgeCommand`, `MaroBridgeStatsCommand`에도 설치한다.

**완전히 검증된 예시 (그대로 적용)**

`MaroPluginMain.cpp` — 규칙 B, 2곳:

```cpp
    maro::BoadMaro::info("Maro: plugin loaded.");   // 기존: MGlobal::displayInfo("Maro: plugin loaded.");
    ...
    maro::BoadMaro::info("Maro: plugin unloaded."); // 기존: MGlobal::displayInfo("Maro: plugin unloaded.");
```

`#include "MaroDiag.h"`를 추가한다.

`MaroPump.cpp` — 규칙 A, 2곳(`onTimer`의 catch 블록):

```cpp
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroPump.onTimer.Exception",
                              MString("Maro: pump tick failed: ") + e.what());
    } catch (...) {
        maro::BoadMaro::error("MaroPump.onTimer.UnknownException",
                              "Maro: pump tick failed with unknown error.");
    }
```

`MaroDeleteWatcher.cpp` — 규칙 A 3곳 + 규칙 B 2곳:

```cpp
void MaroDeleteWatcher::onNodeAdded(MObject& node, void* /*clientData*/) {
    try {
        ...
    } catch (...) {
        // 콜백에서 예외가 새면 Maya가 죽는다.
        maro::BoadMaro::error("MaroDeleteWatcher.onNodeAdded.UnknownException",
                              "Maro: failed to attach delete callback.");
    }
}

void MaroDeleteWatcher::onObjectAboutToDelete(MObject& node, MDGModifier& modifier,
                                              void* /*clientData*/) {
    try {
        ...
            maro::BoadMaro::info(
                MString("Maro: deleting axis '") + otherFn.name() +
                "' because its bound object was deleted.");
        ...
    } catch (...) {
        maro::BoadMaro::error("MaroDeleteWatcher.onObjectAboutToDelete.UnknownException",
                              "Maro: cascade delete failed.");
    }
}

void MaroDeleteWatcher::onAxisAboutToDelete(MObject& node, MDGModifier& modifier,
                                            void* /*clientData*/) {
    try {
        ...
        if (haveSet) {
            maro::BoadMaro::info("Maro: capability nodes moved to maroOrphanSet for reuse.");
        }
    } catch (...) {
        maro::BoadMaro::error("MaroDeleteWatcher.onAxisAboutToDelete.UnknownException",
                              "Maro: orphan handling failed.");
    }
}
```

`#include "MaroDiag.h"`를 추가한다. 이 세 콜백은 `MPxCommand::doIt`이 아니므로 `ScopedCommandContext`를 설치하지 않는다 — `onfix`가 아는 "커맨드"라는 개념 자체가 없는 자리다.

`MaroAxisNode.cpp` — 규칙 A 2곳(`compute`) + 규칙 B 1곳(비유한값 경고):

```cpp
        if (!std::isfinite(value)) {
            maro::BoadMaro::warn("Maro: axis produced a non-finite value; holding zero.");
            value = 0.0;
        }
        ...
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroAxisNode.compute.Exception",
                              MString("Maro: maroAxis compute failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroAxisNode.compute.UnknownException",
                              "Maro: maroAxis compute failed with unknown error.");
        return MS::kFailure;
    }
```

**동일 패턴을 반복 적용하는 나머지 자리**

`MaroCapabilityNodes.cpp`의 `MaroRotationNode`/`MaroLimitNode`/`MaroSensorDirectionNode`/`MaroSensorRangeNode` — 네 `compute()` 모두 `catch (...) { MGlobal::displayError("Maro: X compute failed."); }` 하나씩이다. 위 `MaroAxisNode.cpp` 규칙 A와 같은 방식으로, 사이트 태그만 `"MaroRotationNode.compute.UnknownException"` 식으로 클래스명을 바꿔 4곳 모두 적용한다.

`MaroCommandDeviceNode.cpp`의 11곳은 세 가지로 갈린다: 소멸자·`postConstructor`의 catch 블록(규칙 A, `MaroCommandDeviceNode.destroyMemoryPools.Exception` 등), `createMemoryPools` 실패 시의 단발성 에러(규칙 C와 비슷하지만 커맨드가 아니라 노드 콜백이므로 `ScopedCommandContext` 없이 `onfix::capture("", "", "")`만 붙여 규칙 A와 같이 처리), 그리고 반복 경고 가드가 걸린 `displayWarning` 2곳(규칙 B, 가드 로직 유지). `MaroCommandDeviceNode::postConstructor`, 소멸자는 `MPxNode` 콜백이지 `MPxCommand::doIt`이 아니므로 마커를 설치하지 않는다.

`MaroCommands.cpp`의 45곳 중, `MaroBindAxisCommand`는 Task 4가 `TargetNotTransform` 한 곳을 이미 옮겼다 — 이 태스크에서 같은 클래스의 나머지(이미 바인딩됨, 이미 다른 오브젝트에 바인딩됨, 오브젝트당 축 하나 위반, `redoIt`/`undoIt`의 catch 블록)를 규칙 A/C로 마저 옮긴다. 두 번째로 완전히 검증된 예시로 `MaroConnectAxisCommand::doIt` 전체를 이관한다:

```cpp
MStatus MaroConnectAxisCommand::doIt(const MArgList& args) {
    maro::ScopedCommandContext ctxMarker("MaroConnectAxisCommand");
    // 예외는 경계를 넘지 않는다. 커맨드에서 던지면 Maya가 죽는다.
    try {
        MStatus status;

        MSelectionList selection;
        for (unsigned int i = 0; i < args.length(); ++i) {
            MString name = args.asString(i, &status);
            if (!status) return status;
            if (!selection.add(name)) {
                maro::BoadMaro::error("MaroConnectAxisCommand.NodeNotFound",
                                      MString("Maro: cannot find node '") + name + "'.",
                                      maro::onfix::capture("", "", name));
                return MS::kFailure;
            }
        }

        if (selection.length() != 2) {
            maro::BoadMaro::error(
                "MaroConnectAxisCommand.WrongArgCount",
                "Maro: maroConnectAxis needs exactly two arguments: <child> <parent>.",
                maro::onfix::capture("", "", ""));
            return MS::kFailure;
        }

        MObject childObj;
        MObject parentObj;
        selection.getDependNode(0, childObj);
        selection.getDependNode(1, parentObj);

        MFnDependencyNode childFn(childObj);
        MFnDependencyNode parentFn(parentObj);

        if (childFn.typeId() != MaroAxisNode::id ||
            parentFn.typeId() != MaroAxisNode::id) {
            maro::BoadMaro::error(
                "MaroConnectAxisCommand.NotMaroAxisNode",
                "Maro: maroConnectAxis expects two maroAxis nodes.",
                maro::onfix::capture(childFn.typeName(), "", childFn.name()));
            return MS::kFailure;
        }

        if (childObj == parentObj) {
            maro::BoadMaro::error(
                "MaroConnectAxisCommand.SelfParent",
                MString("Maro: '") + childFn.name() + "' cannot be its own parent.",
                maro::onfix::capture(childFn.typeName(), "parentAxis", childFn.name()));
            return MS::kFailure;
        }

        if (wouldCreateCycle(childObj, parentObj)) {
            maro::BoadMaro::error(
                "MaroConnectAxisCommand.WouldCreateCycle",
                MString("Maro: connecting '") + childFn.name() + "' under '" +
                parentFn.name() + "' would create a cycle in the axis chain.",
                maro::onfix::capture(childFn.typeName(), "parentAxis", childFn.name()));
            return MS::kFailure;
        }

        MPlug parentMessage = parentFn.findPlug("message", false, &status);
        if (!status) return status;
        MPlug childParent = childFn.findPlug(MaroAxisNode::aParentAxis, false, &status);
        if (!status) return status;

        MPlugArray existing;
        childParent.connectedTo(existing, true, false);
        for (unsigned int i = 0; i < existing.length(); ++i) {
            status = m_modifier.disconnect(existing[i], childParent);
            if (!status) return status;
        }

        status = m_modifier.connect(parentMessage, childParent);
        if (!status) return status;

        return redoIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroConnectAxisCommand.doIt.Exception",
                              MString("Maro: maroConnectAxis failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroConnectAxisCommand.doIt.UnknownException",
                              "Maro: maroConnectAxis failed with unknown error.");
        return MS::kFailure;
    }
}
```

`MaroSetControlModeCommand::doIt`, `MaroStartBridgeCommand::doIt`, `MaroStopBridgeCommand::doIt`, `MaroBridgeStatsCommand::doIt`은 같은 두 규칙(마커 설치 + A/C 전환)을 그대로 적용한다 — 내용을 여기서 다시 옮겨 적지 않는다. 이 넷은 위 두 완전한 예시(`MaroBindAxisCommand`, `MaroConnectAxisCommand`)가 다루는 패턴(인자 검증 실패, 타입 불일치, 이미 존재/중복, catch 블록)의 부분집합이므로 새로운 판단이 필요 없다. 정확히 얼마나 옮겼는지는 아래 검증이 객관적으로 답한다 — 손으로 센 숫자를 믿지 않는다.

- [ ] **Step 1: 위 완전 검증 예시(`MaroPluginMain.cpp`, `MaroPump.cpp`, `MaroDeleteWatcher.cpp`, `MaroAxisNode.cpp`, `MaroConnectAxisCommand`, `MaroBindAxisCommand` 나머지) 적용**

각 파일에 `#include "MaroDiag.h"`를 추가하고 위 코드로 교체한다.

- [ ] **Step 2: `MaroCapabilityNodes.cpp`, `MaroCommandDeviceNode.cpp` 적용**

규칙 A/B를 위 설명대로 4곳, 11곳에 적용한다. 두 파일 모두 `#include "MaroDiag.h"`를 추가한다.

- [ ] **Step 3: `MaroCommands.cpp`의 나머지 커맨드(`MaroSetControlModeCommand`, `MaroStartBridgeCommand`, `MaroStopBridgeCommand`, `MaroBridgeStatsCommand`) 적용**

각 `doIt` 진입부에 `maro::ScopedCommandContext ctxMarker("<ClassName>")`을 설치하고, 본문의 `MGlobal::displayError`를 규칙 A/C로 바꾼다.

- [ ] **Step 4: 잔여 호출과 마커 설치 개수를 기계적으로 검증**

```bash
grep -rn "MGlobal::display" src/maro_plugin/MaroAxisNode.cpp src/maro_plugin/MaroCapabilityNodes.cpp src/maro_plugin/MaroCommandDeviceNode.cpp src/maro_plugin/MaroCommands.cpp src/maro_plugin/MaroDeleteWatcher.cpp src/maro_plugin/MaroPluginMain.cpp src/maro_plugin/MaroPump.cpp
```

기대: 출력 없음(0곳). `MaroDiag.cpp` 자신은 이 목록에 없으므로 거기서 계속 `MGlobal::display*`를 부르는 것은 정상이다 — `boad`가 실제로 화면에 찍는 유일한 자리이기 때문이다.

```bash
grep -c "ScopedCommandContext" src/maro_plugin/MaroCommands.cpp
```

기대: `6` (Bind, SetControlMode, ConnectAxis, StartBridge, StopBridge, BridgeStats — `MPxCommand` 파생 클래스 6개 전부).

- [ ] **Step 5: 빌드하고 전체 스위트가 회귀 없이 통과하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build
```

```bash
ctest --test-dir out/build --output-on-failure
```

기대: `maro_transform_tests`, `maro_diag_tests`, 그리고 `maya_load`부터 `maya_diag_degraded`까지 이 플랜 이전부터 있던 테스트를 포함해 전부 통과. 이 태스크는 동작을 하나도 바꾸지 않는 리팩터링이므로, 기존 `test_binding.py`/`test_capability_stack.py`/`test_delete_rules.py`/`test_robustness.py` 등이 전부 예전과 동일하게 통과해야 한다 — 실패하면 어딘가에서 `MStatus` 리턴값이나 사용자 관측 동작이 바뀐 것이다.

- [ ] **Step 6: 이관이 실제로 마커를 설치하는지 확인**

`MaroConnectAxisCommand::doIt`에서 `maro::ScopedCommandContext ctxMarker("MaroConnectAxisCommand");` 줄을 임시로 지운다.

```bash
cmake --build out/build && ctest --test-dir out/build --output-on-failure -R maya_diag_onfix
```

`test_diag_onfix.py`는 `MaroBindAxisCommand`만 건드리므로 이 삭제로는 직접 실패하지 않는다 — 대신 `MaroConnectAxisCommand`의 순환 거부 시나리오를 쓰는 `test_binding.py`로 확인한다:

```bash
MARO_PLUGIN_PATH="$(cygpath -w "$(find out/build -name maro.mll | head -1)")" "/c/Program Files/Autodesk/Maya2026/bin/mayapy.exe" -c "
import os, sys
import maya.standalone
maya.standalone.initialize(name='python')
import maya.cmds as cmds
plugin = os.environ['MARO_PLUGIN_PATH']
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)
a = cmds.createNode('maroAxis'); b = cmds.createNode('maroAxis')
c1 = cmds.polyCube()[0]; c2 = cmds.polyCube()[0]
cmds.maroBindAxis(a, c1); cmds.maroBindAxis(b, c2)
cmds.maroConnectAxis(b, a)
try:
    cmds.maroConnectAxis(a, b)
except RuntimeError:
    pass
rec = cmds.maroDiagQuery(index=0)
print('activeCommand:', repr(rec[5]))
assert rec[5] == 'MaroConnectAxisCommand', 'marker did not leave a trace'
"
```

기대: `AssertionError: marker did not leave a trace`로 **실패**한다(activeCommand가 빈 문자열이 됐으므로). 확인했으면 지운 줄을 되돌리고 `ctest --test-dir out/build --output-on-failure`로 전체 통과를 다시 본다.

- [ ] **Step 7: 커밋**

```bash
git add src/maro_plugin
git commit -m "refactor: migrate all 72 MGlobal::display* call sites to boad, install onfix markers everywhere"
```

---

## 자체 검토 결과

**스펙 커버리지**

| 스펙 항목 | 담당 태스크 |
|---|---|
| §1 세 가지 제품 약속 (원인 분석, 즉답, 축적) | Task 4, 5, 6 |
| §3.5 book 읽기/쓰기 분리 | Task 2 (엔진), Task 5 (연동) |
| §3.6 감시자 없이도 동작 | Task 6 (`test_diag_degraded.py`), 전 태스크의 Global Constraint |
| §4 boad 행 (단일 출구, 스크립트 에디터 + book 우선 조회) | Task 3, 5 |
| §4 book 행 (해시→분석, 파일 기반, 양쪽 읽기) | Task 2 |
| §4 onfix 행 (DG 컨텍스트 포착) | Task 4 |
| §4.1 3분할 파편의 onfix 몫 (모양만) | Task 4 — `DgContext`가 담는 필드가 곧 onfix 몫의 모양이다. 실제 파편 저장·조립은 Layer C |
| §5.4 강등 중 지식 DB 분리(스필) | 아키텍처 노트 결정 1, Task 2, Task 5 |
| §6 기존 코드 정리 | 아키텍처 노트 결정 2 (건드리지 않는 이유 명시, 통합은 후속) |
| §7 원인 분석 내용 | Task 4 (`test_diag_onfix.py`) |
| §7 기지 에러 즉답 | Task 5 (`test_diag_book.py`) |
| §7 해법 등록 (저장·제시) | Task 6 (`test_diag_remedy.py`) |
| §7 강등 | Task 6 (`test_diag_degraded.py`) |
| 72개 `MGlobal::display*` 전환 | Task 7 |

**미커버 항목 (Layer B/C로 의도적 이연)**

- **진단 패널(UI)** — 스펙 §4.2. `workspaceControl` 기반 도킹 패널은 이 플랜에 없다. Layer A는 패널이 읽을 데이터(`BoadMaro`의 인메모리 스트림, `book` 파일)만 준비한다. 패널이 "자체 상태를 갖지 않는다"는 스펙 제약을 지키기 쉽도록 `recordCount()`/`recordAt()`을 이미 그 형태로 설계했다.
- **해법 적용(auto-fix)** — 스펙 §4.3. `MPxCommand` 경유 적용, undo 연동, `MaroPump` 타이밍으로 미루기, 적용 전후 기록은 전부 Layer B다. Layer A는 해법을 저장·조회만 한다(Task 6) — 버튼을 누르는 사용자도, 누른 뒤 씬을 고치는 코드도 없다.
- **감시자 프로세스, 파이프, 하트비트, job object 탈출, 좀비 방지** — 스펙 §3.1~§3.3, §5.1, §5.2, §5.3. 전부 Layer C. Layer A는 감시자가 영원히 없다고 가정하고 동작한다(강등이 예외가 아니라 기본 모드다).
- **`offix`(크래시 딥디버깅), `ghost`(셧다운 대비·3분할 파편 조립), `OSbridge`(Windows 이벤트 로그)** — 스펙 §4, §4.1, §7의 관련 행. 전부 Layer C. `Task 4`가 만든 `DgContext`의 필드 이름(`nodeType`/`attributeName`/`activeCommand`/`axisOrTarget`)은 Layer C가 훗날 onfix 몫 파편으로 그대로 직렬화할 수 있게 골랐지만, 파편 파일 쓰기·병렬 3분할·조립 자체는 만들지 않았다.
- **`book` 정본 쓰기** — 스펙 §3.5. 이 플랜은 정본을 절대 쓰지 않는다(오직 읽는다). 정본에 쓰는 것은 Layer C의 감시자뿐이다. Layer A가 쌓은 스필은 감시자가 나타나는 순간 흡수 대상이 된다 — 흡수 로직 자체는 Layer C의 몫이다.
- **`maroLidar`(S4)와의 연동** — 스펙 §8. 이 생태계 위에서 LiDAR 에러가 진단되는 것은 이 플랜이 세운 `boad` 출구가 이미 범용이므로 자동으로 가능해지지만, LiDAR 쪽 코드를 `boad`로 옮기는 작업 자체는 이 플랜에 없다(애초에 `maroLidar`가 아직 없다).

**타입/이름 일관성 확인**

- `maro::DiagSeverity`, `maro::DgContext`, `maro::DiagRecord` — Task 1에서 정의, Task 3~7에서 동일 이름으로 사용
- `maro::hashError` — Task 1에서 정의(FNV-1a-64, 16자리 hex), `BoadMaro::error`가 Task 5부터 내부에서만 호출(호출부는 사이트 태그 문자열만 다룬다)
- `maro::BookEntry`, `maro::BookStore::loadMerged/query/appendToSpill` — Task 2에서 정의, Task 5~6에서 `BoadMaro::error`/`registerRemedy` 내부에서 사용
- `maro::BoadMaro::info/warn/devInfo/error/registerRemedy/recordCount/recordAt/freshAnalysisCount/resetForTest` — Task 3, 5, 6에 걸쳐 점진적으로 완성, Task 7이 최종 형태를 전 플러그인에 적용
- `maro::ScopedCommandContext`, `maro::onfix::activeCommand/capture` — Task 4에서 정의, Task 7에서 `MaroCommands.cpp`의 6개 커맨드 전부에 적용
- MEL 커맨드 5개(`maroDiagEmit`, `maroDiagCount`, `maroDiagQuery`, `maroDiagAnalysisCount`, `maroDiagRegisterRemedy`) — 전부 테스트 전용, `maroBridgeStats`와 같은 성격이라 프로덕션 진단 경로에는 등장하지 않는다
- 환경변수 `MARO_DIAG_BOOK_DIR` — Task 5에서 도입, Task 6의 두 시나리오(정상 등록, 강등)가 서로 다른 값으로 재사용

