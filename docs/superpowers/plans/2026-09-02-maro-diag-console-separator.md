# Maro 진단 콘솔 구분선 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** boad(`BoadMaro::info/warn/devInfo/error`)가 이미 Maya Script Editor로 실시간 에코하는 진단 메시지들 사이에, 진단 이벤트 하나가 끝날 때마다 `------------` 구분선 한 줄을 추가로 찍는다.

**Architecture:** 새 파일·새 커맨드·새 데이터 흐름 없음. `src/maro_plugin/MaroDiag.cpp`의 기존 4개 함수(boad의 단일 콘솔 출구) 각각의 기존 `if (isMainThread()) { ... }` 블록 끝에 `MGlobal::displayInfo(MString("------------"))` 한 줄만 추가하는 순수 부작용 변경.

**Tech Stack:** C++17, Maya devkit(`MGlobal`, `MString`), 기존 CMake/ctest 빌드.

## Global Constraints

- 구분선 문자열은 정확히 `------------`(하이픈 12개)여야 한다(스펙 §2.2).
- `info`/`warn`/`devInfo`/`error` 네 심각도 전부에 동일하게 적용한다 — 일부만 적용하지 않는다(스펙 §2.3).
- 구분선은 레코드 자신의 심각도와 무관하게 항상 `MGlobal::displayInfo(...)`로 찍는다(스펙 §3) — `displayWarning`/`displayError`로 찍지 않는다.
- `error()`는 진단 이벤트 하나(에러 줄 + 있으면 해법 줄)당 구분선을 정확히 한 번만 찍는다 — `displayError`/`displayInfo` 호출마다 찍지 않는다(스펙 §3).
- 기존 `if (isMainThread())` 가드를 그대로 재사용한다 — 워커 스레드에서는 구분선을 포함해 콘솔 에코 전체를 건너뛴다(스펙 §3).
- 새 C++ 커맨드, 새 `.py` 파일, 새 메뉴 항목, 새 옵션(끄고 켜는 설정)을 추가하지 않는다(스펙 §5).
- 빌드는 항상 `--config Release`, 검증은 항상 `ctest --test-dir out/build -C Release --output-on-failure` 전부 통과.

---

### Task 1: boad 콘솔 에코에 구분선 추가 + 회귀 확인 + 수동 체크리스트

**Files:**
- Modify: `src/maro_plugin/MaroDiag.cpp:341-352` (`BoadMaro::info`)
- Modify: `src/maro_plugin/MaroDiag.cpp:354-363` (`BoadMaro::warn`)
- Modify: `src/maro_plugin/MaroDiag.cpp:365-378` (`BoadMaro::devInfo`)
- Modify: `src/maro_plugin/MaroDiag.cpp:574-579` (`BoadMaro::error`의 콘솔 에코 블록)
- Modify: `docs/maro-panel-manual-checklist.md` (수동 확인 절 추가)
- Test: 새 테스트 파일 없음 — 기존 전체 `ctest` 스위트로 회귀 확인(아래 이유 참고)

**Interfaces:**
- Consumes: 기존 `BoadMaro::info(const MString&)` / `warn(const MString&)` / `devInfo(const MString&)` / `error(const std::string&, const MString&, const DgContext&, const RemedyAction&)` 시그니처 — 전부 불변, 이번 태스크에서 바뀌지 않는다.
- Produces: 없음(공개 인터페이스 변경 없음, 이 태스크가 마지막 태스크).

**왜 새 자동 테스트가 없는가**: 이 변경은 `DiagRecord`/인메모리 스트림/저널/book 중 어느 것도 건드리지 않는다 — `MGlobal::displayInfo`로 문자열 한 줄을 더 찍는 순수 부작용뿐이고, `cmds`로 그 화면 출력 자체를 관측할 방법이 없다(스펙 §4가 이미 이렇게 결정하고 사용자가 승인함). 이 4개 함수는 이미 `tests/maya/test_panel_commands.py`, `tests/maya/test_remedy_apply.py`, `tests/maya/test_remedy_availability.py`, `tests/maya/test_journal.py` 등 수십 개의 기존 mayapy 배치 테스트가 매번 경유하는 경로이므로, 전체 스위트가 예외 없이 통과하는 것 자체가 "새 줄 추가가 기존 흐름을 깨지 않았다"는 회귀 증거다. 실제로 화면에 원하는 모양으로 나오는지는 Step 6의 수동 체크리스트가 담당한다.

- [ ] **Step 1: `BoadMaro::info`에 구분선 추가**

`src/maro_plugin/MaroDiag.cpp:341-352`의 현재 내용:

```cpp
void BoadMaro::info(const MString& message) {
    DiagRecord rec;
    stampTimestamp(rec);
    rec.severity = DiagSeverity::Info;
    rec.message = message.asChar();
    // 워커 스레드에서는 화면 에코를 건너뛴다 -- 레코드는 그대로 남는다
    // (MaroDiag.h의 스레드 안전성 주석 참고).
    if (isMainThread()) {
        MGlobal::displayInfo(MString("[Maro-Info] ") + message);
    }
    pushAndJournal(std::move(rec));
}
```

다음으로 교체한다:

```cpp
void BoadMaro::info(const MString& message) {
    DiagRecord rec;
    stampTimestamp(rec);
    rec.severity = DiagSeverity::Info;
    rec.message = message.asChar();
    // 워커 스레드에서는 화면 에코를 건너뛴다 -- 레코드는 그대로 남는다
    // (MaroDiag.h의 스레드 안전성 주석 참고).
    if (isMainThread()) {
        MGlobal::displayInfo(MString("[Maro-Info] ") + message);
        // 연속된 진단 블록을 구분하는 시각적 구분선. 레코드의 심각도와
        // 무관하게 항상 displayInfo로 찍는다 -- 그래야 에러/경고 색이 아닌
        // 기본색으로 나와 "메시지의 일부"가 아니라 "구분자"로 보인다
        // (2026-09-02-maro-diag-console-separator-design.md §3).
        MGlobal::displayInfo(MString("------------"));
    }
    pushAndJournal(std::move(rec));
}
```

- [ ] **Step 2: `BoadMaro::warn`에 구분선 추가**

`src/maro_plugin/MaroDiag.cpp:354-363`의 현재 내용:

```cpp
void BoadMaro::warn(const MString& message) {
    DiagRecord rec;
    stampTimestamp(rec);
    rec.severity = DiagSeverity::Warn;
    rec.message = message.asChar();
    if (isMainThread()) {
        MGlobal::displayWarning(MString("[Maro-Warn] ") + message);
    }
    pushAndJournal(std::move(rec));
}
```

다음으로 교체한다:

```cpp
void BoadMaro::warn(const MString& message) {
    DiagRecord rec;
    stampTimestamp(rec);
    rec.severity = DiagSeverity::Warn;
    rec.message = message.asChar();
    if (isMainThread()) {
        MGlobal::displayWarning(MString("[Maro-Warn] ") + message);
        // 구분선은 항상 displayInfo로 찍는다 -- info()와 같은 이유.
        MGlobal::displayInfo(MString("------------"));
    }
    pushAndJournal(std::move(rec));
}
```

- [ ] **Step 3: `BoadMaro::devInfo`에 구분선 추가**

`src/maro_plugin/MaroDiag.cpp:365-378`의 현재 내용:

```cpp
void BoadMaro::devInfo(const MString& message) {
#ifdef _DEBUG
    DiagRecord rec;
    stampTimestamp(rec);
    rec.severity = DiagSeverity::DevInfo;
    rec.message = message.asChar();
    if (isMainThread()) {
        MGlobal::displayInfo(MString("[Maro-Dev] ") + message);
    }
    pushAndJournal(std::move(rec));
#else
    (void)message;
#endif
}
```

다음으로 교체한다:

```cpp
void BoadMaro::devInfo(const MString& message) {
#ifdef _DEBUG
    DiagRecord rec;
    stampTimestamp(rec);
    rec.severity = DiagSeverity::DevInfo;
    rec.message = message.asChar();
    if (isMainThread()) {
        MGlobal::displayInfo(MString("[Maro-Dev] ") + message);
        // 구분선은 항상 displayInfo로 찍는다 -- info()와 같은 이유. _DEBUG
        // 밖(이 프로젝트의 기본 빌드 구성인 RelWithDebInfo 포함)에서는 이
        // 함수 본문 전체가 무연산이므로 이 줄도 자연히 컴파일되지 않는다.
        MGlobal::displayInfo(MString("------------"));
    }
    pushAndJournal(std::move(rec));
#else
    (void)message;
#endif
}
```

- [ ] **Step 4: `BoadMaro::error`의 콘솔 에코 블록에 구분선 추가**

`src/maro_plugin/MaroDiag.cpp:574-579`의 현재 내용:

```cpp
    if (isMainThread()) {
        MGlobal::displayError(MString("[Maro-Error] ") + MString(rec.message.c_str()));
        if (!rec.remedy.empty()) {
            MGlobal::displayInfo(MString("[Maro-Fix] ") + MString(rec.remedy.c_str()));
        }
    }
```

다음으로 교체한다(에러 줄과, 있으면 해법 줄까지 전부 찍은 **뒤에** 구분선을 정확히 한 번만 찍는다 — `displayError`/`displayInfo` 호출마다가 아니라 이 진단 이벤트 전체에 대해 한 번):

```cpp
    if (isMainThread()) {
        MGlobal::displayError(MString("[Maro-Error] ") + MString(rec.message.c_str()));
        if (!rec.remedy.empty()) {
            MGlobal::displayInfo(MString("[Maro-Fix] ") + MString(rec.remedy.c_str()));
        }
        // 구분선은 항상 displayInfo로 찍는다 -- info()와 같은 이유. 에러
        // 줄과 (있으면) 해법 줄까지 전부 찍은 뒤 이 진단 이벤트 전체에
        // 대해 정확히 한 번만 찍는다.
        MGlobal::displayInfo(MString("------------"));
    }
```

- [ ] **Step 5: 빌드 후 전체 테스트 스위트 실행**

Run:

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure
```

Expected: 빌드 성공(경고/에러 없음), 전체 테스트 스위트가 이전과 동일하게 전부 PASS. 어떤 테스트도 새로 실패하면 안 된다 — 이 4개 함수는 기존 다수 테스트가 경유하는 경로이므로, 실패가 하나라도 나오면 Step 1-4의 변경이 무언가를 깼다는 뜻이다(예: 중괄호 위치 실수로 구분선이 `if (isMainThread())` 바깥으로 나가 워커 스레드에서도 무조건 호출되는 경우 — 이러면 스레드 안전성 관련 기존 테스트가 크래시로 드러난다).

- [ ] **Step 6: 수동 체크리스트에 구분선 확인 절 추가**

`docs/maro-panel-manual-checklist.md`의 마지막 줄(현재 파일 37번째 줄, "확인용 진단을 만들려면: ..." 문단) 뒤에 다음 절을 추가한다:

`````markdown

## 진단 콘솔 구분선

인터랙티브 Maya 2026에서 `maro.mll`을 로드한 뒤 스크립트 에디터에서 아래를
실행해 서로 다른 심각도의 진단을 연달아 두 번 이상 일으킨다:

```python
import maya.cmds as cmds
cmds.maroDiagEmit(severity="info", message="separator check A")
cmds.maroDiagEmit(severity="warn", message="separator check B")
cmds.maroDiagEmit(severity="error", message="separator check C", siteTag="ManualSeparatorCheck")
```

- [ ] **블록이 나뉘어 보인다** — 세 진단 각각의 출력 뒤에 `------------` 줄이
      한 번씩만 보이고, 세 블록이 서로 섞이지 않고 스크롤 상에서 명확히
      구분되는지 확인한다.
- [ ] **구분선은 항상 기본색이다** — `[Maro-Warn]`/`[Maro-Error]` 줄은
      Maya의 경고색/에러색으로 뜨는데, 그 바로 뒤의 `------------` 줄은
      색이 섞이지 않고 기본색(정보색)으로 뜨는지 확인한다.
- [ ] **해법이 있는 에러는 한 블록으로 묶인다** — 이미 book에 해법이
      등록된 에러(예: 기존 "해법 적용과 undo" 절이 만드는 `AxisAlreadyBound`
      진단을 두 번째로 재현)를 일으켜, `[Maro-Error]` 줄과 `[Maro-Fix]`
      줄 사이에는 구분선이 끼지 않고, 그 두 줄 전체 뒤에만 구분선이 한 번
      오는지 확인한다.

`devInfo`(`[Maro-Dev]`)는 이 프로젝트의 기본 빌드 구성(RelWithDebInfo)에서
함수 본문 전체가 컴파일되지 않으므로 이 체크리스트로 확인할 수 없다 --
코드 리뷰로만 검증된 경로임을 기록해 둔다.
`````

- [ ] **Step 7: 커밋**

```bash
git add src/maro_plugin/MaroDiag.cpp docs/maro-panel-manual-checklist.md
git commit -m "feat(diag): add console separator after each boad diagnostic echo"
```
