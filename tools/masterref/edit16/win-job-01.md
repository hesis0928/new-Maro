<!-- win-job-01 Windows › 프로세스·job object (21개) 2026-09-24 -->

#### crashtriage

**직관:** 크래시를 분류하는 도구 모음(`tools/crashtriage/`). 미니덤프 파싱, 심볼화, ASan 실행 스크립트가 여기 모여 있다.

**동작:** 네 도구가 네 단계를 이룬다 — (1) `parse_minidump.py`가 예외 코드·폴트 모듈·`maro.mll` 베이스를 `struct`로 직접 파싱, (2) `symbolize.py`가 RVA를 dbghelp로 심볼화, (3) 프로세스 안 스택(`boost::stacktrace`)이 조용히 삼켜지는 실패를 잡고, (4) 힙 손상 의심이면 `run-asan-tests.ps1`이 ASan 런타임을 Maya 초기화 **전에** 넣어 돌린다. 다만 "크래시가 아니라 조용한 실패"는 덤프가 없어 이 도구들이 손도 못 대는 유형이며, 2026-09-07에 `maroPointCloud`를 파느라 하루를 쓴 것이 정확히 그것이었다.

**예시:**
```powershell
python tools/crashtriage/parse_minidump.py crash.dmp     # 예외·모듈·베이스
python tools/crashtriage/symbolize.py maro.mll 0x1234    # 함수명:줄
tools/crashtriage/run-asan-tests.ps1                     # ASan 선로드 순서 자동화
```

**관련 코드:**
- `tools/crashtriage/parse_minidump.py` — 덤프 파싱
- `tools/crashtriage/symbolize.py:1-75` — dbghelp 심볼화
- `src/maro_plugin/MaroStackTrace.cpp:1-98` — 프로세스 안 스택

**증거:**
- §2, §3.2, §6.7.2, §8.3.3

**함정:** 덤프가 없는 실패(예외를 `catch(...)`로 삼킨 경로)는 이 도구들의 사각지대다. 그래서 진단 스택 트레이스를 코드에 넣었다.

**교훈:** 크래시 도구는 "크래시했을 때"만 쓸모 있다. 조용한 실패에는 별도 장치가 필요하다.

#### `SetConsoleOutputCP(CP_UTF8)`

**직관:** 콘솔의 출력 코드페이지를 UTF-8로 바꾸는 호출. 한국어 로그가 콘솔에서 깨지지 않게 한다.

**동작:** 레거시 bridge 노드가 시작 직후 `SetConsoleOutputCP(CP_UTF8)`를 불러 콘솔 한글 깨짐을 막았다. 기본 코드페이지는 949(CP949)라 UTF-8 바이트가 그대로 출력되면 모지바케가 된다. 현재 Maro는 콘솔 출력 대신 저널(JSON Lines)과 Maya 스크립트 에디터로 진단을 내보내므로 이 호출이 필요 없다.

**예시:**
```cpp
SetConsoleOutputCP(CP_UTF8);   // 이후 printf("한글")이 콘솔에서 제대로 보인다
```

**관련 코드:**
- `src/image_bridge/src/image_bridge_node.cpp:23` — 호출(레거시)
- `src/maro_diag/src/JournalWriter.cpp:14-22` — 콘솔 대신 쓰는 UTF-8 저널

**증거:**
- §4.3, §4.3.6

**함정:** 코드페이지를 바꿔도 콘솔 폰트가 한글 글리프를 갖고 있지 않으면 네모로 보인다. 인코딩과 글꼴은 별개 문제다.

**교훈:** 콘솔 출력은 인코딩·글꼴·리다이렉션이 얽힌다. 진단을 파일로 내보내면 그 변수들이 사라진다.

#### `IsProcessInJob`

**직관:** 프로세스가 job object에 속해 있는지 묻는 API. 감시자 설계에서 "우리가 탈출해야 하는가"를 판정하는 첫 질문이다.

**동작:** `isCurrentProcessInJob()`은 `IsProcessInJob(GetCurrentProcess(), nullptr, &result)`를 부른다(두 번째 인자 nullptr이면 "아무 job이든"). 감시자는 이 값을 기록 파일의 `sentinelInJob`에 남겨 자가 점검한다. 중요한 실측: 이 개발 샌드박스의 프로세스 트리 자체가 이미 job 안이라(PowerShell에서 true) `test_job_escape.cpp`는 해당 케이스를 `GTEST_SKIP`한다.

**예시:**
```cpp
bool isCurrentProcessInJob() {
    BOOL result = FALSE;
    return ::IsProcessInJob(::GetCurrentProcess(), nullptr, &result) && result;
}
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:10-18` — 판정
- `tests/ipc/test_job_escape.cpp:51-60` — 샌드박스 감지 후 SKIP

**증거:**
- §5.3, §5.3.7, §8.2.3, §8.4, §11.4

**함정:** 개발 환경이 이미 job 안이면 "탈출 성공" 테스트가 환경 때문에 항상 실패한다. 환경을 감지해 건너뛰되, 건너뛴 사실을 메시지로 남긴다.

**교훈:** 환경 의존 테스트는 전제를 코드로 확인하고 스킵 사유를 출력한다. 조용한 스킵은 검증 공백이다.

#### job object

**직관:** 여러 프로세스를 하나의 그룹으로 묶어 제한·회계·일괄 종료를 거는 커널 객체. 자식은 기본으로 부모의 job을 상속한다.

**동작:** 규칙 셋이 설계를 지배한다 — (1) `AssignProcessToJobObject`는 **비가역**(한 번 들어가면 못 나옴), (2) `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`가 걸리면 마지막 핸들이 닫힐 때 전원이 죽고, (3) breakaway는 job 쪽 `JOB_OBJECT_LIMIT_BREAKAWAY_OK` 제한과 자식 생성 시 `CREATE_BREAKAWAY_FROM_JOB` 플래그가 **둘 다** 있어야 한다. Maya가 job 안에서 돌면 감시자도 상속되어 Maya와 함께 죽으므로, Maro는 탈출을 시도한다.

**예시:**
```
Maya (job A) → CreateProcess(감시자)          → 감시자도 job A (Maya와 함께 죽음)
Maya (job A) → CreateProcess(BREAKAWAY 플래그) → 감시자는 job 밖 (살아남음)
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:21-60` — tier 1 탈출
- `tests/ipc/job_escape_test_helper.cpp:55-75` — 제한적 job 구성

**증거:**
- §5.3, §8.4, §11.4

**함정:** job 제한은 상속되지만 우리가 그 job의 소유자가 아니다. 다른 프로그램(CI 러너, 터미널)이 건 제한을 우리가 풀 수 없다.

**교훈:** 프로세스 수명 정책은 부모가 정한다. 그 정책 밖에서 살아야 한다면 생성 시점에 탈출해야 한다.

#### `CREATE_BREAKAWAY_FROM_JOB`

**직관:** 자식 프로세스를 부모의 job에서 분리해 만드는 `CreateProcess` 플래그. 감시자가 Maya보다 오래 살기 위한 tier 1 수단이다.

**동작:** `spawnWithBreakaway(exe, args)`가 `CreateProcessA(..., CREATE_BREAKAWAY_FROM_JOB | CREATE_NO_WINDOW, ...)`를 부른다. 호출 프로세스의 job이 `JOB_OBJECT_LIMIT_BREAKAWAY_OK`를 허용하지 않으면 `CreateProcess` 자체가 실패해 `nullopt`를 돌려주므로, 자식의 보고를 기다릴 필요 없이 즉시 tier 2(WMI)로 넘어간다.

**예시:**
```cpp
::CreateProcessA(nullptr, cmdline.data(), nullptr, nullptr, FALSE,
                 CREATE_BREAKAWAY_FROM_JOB | CREATE_NO_WINDOW, nullptr, nullptr, &si, &pi);
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:21-60` — tier 1
- `src/maro_ipc/src/JobEscape.cpp:160-200` — tier 2 WMI 폴백

**증거:**
- §5.3, §5.3.7, §11.4

**함정:** 이 플래그는 "job이 허용할 때만" 동작한다. 허용하지 않으면 자식이 조용히 job 안에 들어가는 것이 아니라 생성 자체가 실패한다 — 다행히 그 실패가 명확한 신호다.

**교훈:** 실패가 명확한 API는 폴백 설계를 쉽게 만든다. "조용히 잘못된 상태"보다 낫다.

#### `JOB_OBJECT_LIMIT_BREAKAWAY_OK`

**직관:** job 쪽에 걸어 두는 제한 플래그로, 그 안의 프로세스가 자식을 job 밖으로 내보낼 수 있게 허용한다. 없으면 breakaway 시도가 실패한다.

**동작:** breakaway는 두 조건의 논리곱이다 — job이 `BREAKAWAY_OK`(또는 `SILENT_BREAKAWAY_OK`)를 갖고, 자식 생성이 `CREATE_BREAKAWAY_FROM_JOB`을 준다. Maro는 job의 소유자가 아니므로 첫 조건을 통제할 수 없고, 그래서 실패를 전제한 tier 2가 존재한다. 테스트 도우미는 반대로 **불허 job**을 만들어 거부 경로를 검증한다.

**예시:**
```
job에 BREAKAWAY_OK 있음 + 플래그 있음 → 탈출 성공
job에 BREAKAWAY_OK 없음 + 플래그 있음 → CreateProcess 실패 → tier 2
```

**관련 코드:**
- `tests/ipc/job_escape_test_helper.cpp:55-75` — 불허 job 구성
- `src/maro_ipc/src/JobEscape.cpp:21-60` — 실패 시 nullopt

**증거:**
- §5.3, §5.3.7, §11.4

**함정:** `SILENT_BREAKAWAY_OK`는 플래그 없이도 자식이 job 밖에서 생기게 한다. 두 제한을 혼동하면 "플래그를 줬는데 왜 되지/안 되지"가 설명되지 않는다.

**교훈:** 권한은 "요청자"와 "허용자" 양쪽에서 온다. 우리가 통제하는 쪽과 아닌 쪽을 나눠 설계한다.

#### 콘솔 서브시스템 vs GUI 서브시스템

**직관:** PE 헤더에 기록된 서브시스템 종류. 콘솔 서브시스템 exe는 콘솔이 없으면 Windows가 새로 할당해 주고, GUI 서브시스템 exe는 그러지 않는다.

**동작:** 감시자(`maro_sentinel.exe`)는 콘솔 서브시스템이고 Maya.exe는 GUI 서브시스템이라 콘솔이 없다. 콘솔 없는 부모가 콘솔 프로그램을 자식으로 만들면 Windows가 **새 콘솔을 할당하고 그 창을 보여 준다** — 감시자는 최대 12시간을 살므로 사용자 화면에 검은 창이 그만큼 떠 있게 된다. 그래서 tier 1은 `CREATE_NO_WINDOW`, tier 2는 `DETACHED_PROCESS`+`SW_HIDE`를 건다.

**예시:**
```
Maya.exe (GUI, 콘솔 없음) → maro_sentinel.exe (콘솔 서브시스템)
  플래그 없음 → Windows가 새 콘솔 창 생성 (사용자에게 보임, 12시간)
  CREATE_NO_WINDOW → 콘솔 없이 실행
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:36-48` — 이유 주석과 플래그
- `tests/ipc/test_console_window.cpp:7-60` — 재현 테스트

**증거:**
- §5.3, §5.3.7, §8.1, §8.2.3

**함정:** mayapy·gtest는 둘 다 콘솔 프로그램이라 자식이 부모 콘솔을 물려받아 이 문제가 **보이지 않는다**. 개발 중에는 재현되지 않고 실제 Maya에서만 나타난다.

**교훈:** 호스트의 서브시스템이 자식의 동작을 바꾼다. 개발 환경이 호스트와 다르면 그 차이를 테스트가 인위적으로 만들어야 한다.

#### `CREATE_NO_WINDOW`

**직관:** 콘솔 프로그램을 콘솔 창 없이 실행하는 `CreateProcess` 플래그. tier 1 spawn이 이 플래그로 창 튐을 막는다.

**동작:** `CREATE_BREAKAWAY_FROM_JOB | CREATE_NO_WINDOW`로 감시자를 띄운다(F-113, F-116). 실측 주석이 근거를 적는다 — 이 플래그가 없으면 사용자 화면에 콘솔 창이 뜬다. 한편 tier 2(WMI)에서는 이 플래그가 쓸 수 없다: `CreateFlags = CREATE_NO_WINDOW(0x08000000)` 단독은 `Win32_Process.Create`가 ReturnValue 21(Invalid Parameter)로 거부한다(3/3 재현) — 문서의 값 목록에 없어 제공자가 ValueMap으로 검증하기 때문이다.

**예시:**
```cpp
CREATE_BREAKAWAY_FROM_JOB | CREATE_NO_WINDOW        // tier 1: OK
// tier 2(WMI): CreateFlags=0x08000000 → ReturnValue 21 → DETACHED_PROCESS(8) + SW_HIDE 사용
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:36-48` — tier 1 플래그와 이유
- `src/maro_ipc/src/JobEscape.cpp:162-182` — tier 2에서 못 쓰는 근거(실측)

**증거:**
- §5.3, §5.3.7, §11.4, §10.8
- F-113, F-116

**함정:** 같은 상수가 API마다 받아들여지지 않는다. WMI 제공자는 문서화된 값만 허용하므로 Win32 플래그를 그대로 넘길 수 없다.

**교훈:** 같은 개념의 플래그라도 경로(Win32 직접 호출 vs WMI)마다 허용 집합이 다르다. 경로별로 실측한다.

#### `DETACHED_PROCESS`

**직관:** 자식이 부모의 콘솔을 물려받지 않게 하는 플래그. 자식은 콘솔이 아예 없는 상태로 시작한다.

**동작:** tier 2(WMI)에서 `CreateFlags = DETACHED_PROCESS(8)`를 주면 ReturnValue 0이고 자식의 `GetConsoleWindow()`가 NULL이다 — tier 1의 `CREATE_NO_WINDOW`와 관측상 동일하다. `ShowWindow = SW_HIDE` 단독은 콘솔이 생기고 창만 숨으므로 둘 다 건다. 테스트에서는 반대 용도로 쓴다 — 프로브를 `DETACHED_PROCESS`로 띄워 "콘솔 없는 부모"(진짜 Maya 조건)를 인위적으로 만든다. 실측: 플래그를 빼면 자식이 visible로 관측된다.

**예시:**
```
WMI: CreateFlags=DETACHED_PROCESS(8), ShowWindow=SW_HIDE  → ReturnValue 0, 자식 콘솔 없음
테스트: 프로브를 DETACHED_PROCESS로 띄워 "콘솔 없는 부모" 재현
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:162-190` — tier 2 플래그 선택과 실측 근거
- `tests/ipc/test_console_window.cpp:44-60` — 프로브 기동

**증거:**
- §5.3, §5.3.7, §8.2.3, §11.4, §10.8
- F-113

**함정:** `DETACHED_PROCESS`와 새 콘솔 생성 플래그는 함께 쓸 수 없다. 조합 제약은 문서에 있지만 오류가 `ERROR_INVALID_PARAMETER` 하나뿐이라 원인 추적이 어렵다.

**교훈:** "콘솔을 주지 않는" 방법이 API마다 다르다. 관측 신호(`GetConsoleWindow()`)로 동등성을 확인한다.

#### `SW_HIDE`

**직관:** 창을 숨긴 상태로 시작하라는 `STARTUPINFO`/WMI의 표시 모드. 콘솔이 생기더라도 보이지 않게 한다.

**동작:** tier 2는 `DETACHED_PROCESS`와 `SW_HIDE`를 함께 건다 — 전자는 콘솔 자체를 없애고, 후자는 만약 생기더라도 창을 숨긴다(이중 방어). `SW_HIDE` 단독은 콘솔이 생기고 창만 숨는 상태라 `GetConsoleWindow()`가 NULL이 아니다. 설정에 실패해도 spawn은 계속한다(best-effort) — 감시자가 뜨는 것이 창 하나보다 중요하다.

**예시:**
```
SW_HIDE 단독:            콘솔 생성됨, 창만 숨음 (GetConsoleWindow != NULL)
DETACHED_PROCESS 단독:   콘솔 없음        (GetConsoleWindow == NULL)
둘 다:                   안전
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:162-190` — 두 설정과 best-effort 주석

**증거:**
- §5.3, §5.3.7, §11.4, §10.8
- F-113, F-116

**함정:** 창을 숨기는 것과 콘솔을 안 만드는 것은 다르다. 전자는 사용자에게 안 보일 뿐 콘솔 자원은 할당된다.

**교훈:** "보이지 않음"과 "없음"을 구분한다. 관측 신호를 정하면 그 차이가 드러난다.

#### `GetConsoleWindow`

**직관:** 현재 프로세스의 콘솔 창 핸들을 돌려주는 함수. 콘솔이 없으면 NULL이라 "콘솔이 있는가"의 판정에 쓴다.

**동작:** 콘솔 프로브가 `GetConsoleWindow()`와 `IsWindowVisible`을 조합해 `(consoleWindow != nullptr && ::IsWindowVisible(consoleWindow)) ? 1 : 0`을 결과 파일에 적는다. 이 신호로 tier 1/tier 2의 창 억제가 실제로 먹는지, 그리고 테스트의 전제(부모에 콘솔 없음)가 성립했는지를 함께 검증한다.

**예시:**
```cpp
HWND consoleWindow = ::GetConsoleWindow();          // 콘솔 없으면 NULL
const int visible = (consoleWindow && ::IsWindowVisible(consoleWindow)) ? 1 : 0;
```

**관련 코드:**
- `tests/ipc/console_window_probe.cpp:31-55` — 관측
- `src/maro_ipc/src/JobEscape.cpp:162-190` — 이 신호로 검증되는 설정

**증거:**
- §5.3, §5.3.7, §8.2, §11.4

**함정:** 콘솔이 있어도 창이 다른 프로세스 소유일 수 있다(부모 콘솔 공유). 그래서 "부모의 콘솔 상태"를 따로 기록해 전제를 검증한다.

**교훈:** 불리언 하나로 요약되는 관측 신호를 정하면 프로세스 경계를 넘는 검증이 가능해진다.

#### `isProcessRunning(pid)`

**직관:** PID가 가리키는 프로세스가 아직 살아 있는지 판정하는 함수. 저널 회전과 크래시 인접 집계가 이 판정에 기댄다.

**동작:** `MaroDiag.cpp`의 구현은 방어부터 한다 — PID 0은 System Idle이라 저널 파일의 주인일 수 없으므로 false, `DWORD` 범위를 넘는 값도 false. 그 다음 `OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION)`으로 핸들을 열고 `WaitForSingleObject(h, 0) == WAIT_TIMEOUT`이면 살아 있다. 핸들은 `ScopedProcessHandle`이 닫는다. `openJournal()`이 `rotateAll` → `countCrashAdjacencyAcrossJournalFiles(directory, &isProcessRunning)` 순으로 이 함수를 콜백으로 넘긴다.

**예시:**
```cpp
bool isProcessRunning(std::uint64_t processId) {
    if (processId == 0) return false;                 // System Idle
    if (processId > DWORD_MAX) return false;
    ScopedProcessHandle h(::OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, FALSE, (DWORD)processId));
    return h && ::WaitForSingleObject(h.get(), 0) == WAIT_TIMEOUT;
}
```

**관련 코드:**
- `src/maro_plugin/MaroDiag.cpp:224-250` — 구현과 방어
- `src/maro_plugin/MaroDiag.cpp:190-215` — `ScopedProcessHandle`

**증거:**
- §6.7, §6.7.1

**함정:** PID는 재사용된다. 오래된 저널 파일의 PID가 지금은 다른 프로세스일 수 있어 "살아 있음"이 오판이 된다. 파일 mtime과 함께 보는 이유다.

**교훈:** PID만으로는 신원이 확정되지 않는다. 판정에는 시간(생성/수정 시각) 같은 보조 근거를 곁들인다.

#### `OpenProcess(SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION)`

**직관:** 프로세스 핸들을 **최소 권한**으로 여는 호출. 대기(SYNCHRONIZE)와 제한적 조회만 필요하므로 그 이상을 요구하지 않는다.

**동작:** 전체 권한을 요구하면 권한이 낮은 프로세스나 보호된 프로세스에서 실패한다. `PROCESS_QUERY_LIMITED_INFORMATION`은 Vista 이후 도입된 완화된 조회 권한으로 대부분의 프로세스에 열린다. 성공했다고 살아 있는 것은 아니다 — 종료된 프로세스도 누군가 핸들을 들고 있으면 오브젝트가 남아 열린다(F-122). 그래서 `WaitForSingleObject(h, 0)`로 시그널 상태를 본다.

**예시:**
```cpp
HANDLE h = ::OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
const bool alive = h && ::WaitForSingleObject(h, 0) == WAIT_TIMEOUT;
```

**관련 코드:**
- `src/maro_plugin/MaroDiag.cpp:224-250` — 권한 조합
- `src/maro_plugin/MaroDiag.cpp:190-215` — RAII 닫기

**증거:**
- §6.7, §6.7.1, §11.4, §10.8
- F-122

**함정:** 최소 권한으로 열어도 보호된 프로세스(안티바이러스 등)는 실패한다. 실패를 "죽었다"로 해석하면 오판이므로 실패는 별도로 다룬다.

**교훈:** 권한은 필요한 만큼만 요구한다. 그래야 실패가 줄고, 실패했을 때의 의미도 분명해진다.

#### 좀비 핸들

**직관:** 이미 종료된 프로세스의 커널 오브젝트가 누군가의 핸들 때문에 남아 있는 상태. `OpenProcess`가 성공하므로 "살아 있다"는 착각을 만든다.

**동작:** 프로세스 오브젝트는 종료 시 **시그널 상태**가 되므로 `WaitForSingleObject(h, 0)`이 `WAIT_OBJECT_0`이면 죽은 것, `WAIT_TIMEOUT`이면 살아 있는 것이다. 핸들 획득 성공만으로 판정하면 죽은 프로세스를 살아 있다고 보고, 그 결과 저널 회전이 남의 파일을 지우지 않거나 크래시 집계가 어긋난다(F-122). 핸들을 오래 들고 있으면 PID 재사용까지 늦춰 문제가 커진다.

**예시:**
```
프로세스 종료 → 오브젝트는 마지막 핸들이 닫힐 때까지 생존(좀비)
OpenProcess 성공 → 살아 있음? 아니다
WaitForSingleObject(h,0) == WAIT_OBJECT_0 → 죽었음
```

**관련 코드:**
- `src/maro_plugin/MaroDiag.cpp:224-250` — 시그널 판정
- `src/maro_plugin/MaroDiag.cpp:190-215` — 즉시 닫기

**증거:**
- §6.7, §6.7.1
- F-122

**함정:** 테스트에서 자식 핸들을 들고 있으면 그 자식은 영원히 "열린다". 리브니스 테스트가 항상 통과하는 이유가 될 수 있다.

**교훈:** 커널 오브젝트의 수명과 실체의 수명은 다르다. 상태를 묻는 API로 판정한다.

#### 핸들 즉시 닫기

**직관:** `CreateProcess`가 돌려주는 프로세스·스레드 핸들을 쓰임이 끝나면 바로 닫는 규칙. 안 닫으면 로드마다 커널 오브젝트가 샌다.

**동작:** tier 1 `spawnWithBreakaway`가 성공하면 `PROCESS_INFORMATION`의 `hProcess`·`hThread` **두 핸들을 즉시 닫는다** — 감시자를 기다릴 일이 없으므로 들고 있을 이유가 없다. 진단 쪽 `ScopedProcessHandle`도 같은 규칙이다. 파이프의 끊김 신호도 이 규칙에 기댄다 — 프로세스가 죽으면 커널이 핸들을 닫아 상대에게 `ERROR_BROKEN_PIPE`가 즉시 전달된다.

**예시:**
```cpp
if (::CreateProcessA(...)) {
    ::CloseHandle(pi.hThread);
    ::CloseHandle(pi.hProcess);     // 기다릴 일이 없으면 즉시 닫는다
}
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:50-60` — 두 핸들 닫기
- `src/maro_plugin/MaroDiag.cpp:190-215` — RAII 버전

**증거:**
- §6.7, §6.7.3, §5.3.4

**함정:** `hThread`를 잊고 `hProcess`만 닫는 실수가 흔하다. `CreateProcess`는 핸들을 둘 준다.

**교훈:** 리소스를 주는 API는 몇 개를 주는지 센다. 문서의 out 파라미터 개수가 정리 코드의 줄 수다.

#### 콘솔 서브시스템 vs `WIN32_EXECUTABLE`(GUI)

**직관:** CMake에서 `WIN32_EXECUTABLE` 속성을 켜면 GUI 서브시스템 exe가 된다. 콘솔 창 테스트의 프로브는 반대로 **콘솔 서브시스템**이어야 의미가 있다.

**동작:** `tests/CMakeLists.txt:42-69`가 도우미 3종(`maro_job_escape_test_helper`, `maro_sentinel_in_job_helper`, `maro_console_window_probe`)을 만든다. 테스트가 이들을 **경로 문자열로만** 참조하므로 CMake가 의존을 추론하지 못해 명시적 `add_dependencies`가 없으면 도우미가 빌드되지 않은 채 테스트가 돈다. 프로브를 GUI 서브시스템으로 만들면 "콘솔 프로그램을 자식으로 만들 때 창이 뜬다"는 현상 자체가 재현되지 않는다.

**예시:**
```cmake
add_executable(maro_console_window_probe ipc/console_window_probe.cpp)   # 콘솔 서브시스템(기본)
add_dependencies(maro_ipc_tests maro_console_window_probe)               # 경로 참조라 명시 필요
```

**관련 코드:**
- `tests/CMakeLists.txt:42-69` — 도우미 타깃과 `add_dependencies`
- `tests/ipc/console_window_probe.cpp:18-31` — 프로브의 역할 주석

**증거:**
- §8.1, §5.3.7, §8.2.3
- F-035, F-116, F-230, F-235

**함정:** 경로 문자열로 참조하는 실행 파일은 빌드 그래프에 나타나지 않는다. 처음 빌드하는 머신에서만 "파일 없음"으로 실패한다.

**교훈:** 테스트가 다른 실행 파일을 쓰면 의존을 빌드 시스템에 명시한다. 문자열 경로는 의존이 아니다.

#### 평범한 `CreateProcess` job 상속

**직관:** 아무 플래그 없이 `CreateProcess`를 부르면 자식이 부모의 job을 그대로 상속한다. 이것이 감시자가 Maya와 함께 죽는 기본 경로다.

**동작:** 테스트 `SentinelStuckInAJobRecordsThatItIsInAJob`은 이 성질을 일부러 이용한다 — `sentinel_in_job_helper.exe`가 breakaway 불허 job에 들어간 뒤 **평범한 `CreateProcess`**로 감시자를 띄워 job을 상속시키고, 기록 파일의 `record.sentinelInJob == true`가 self-check에서 디스크까지 배선됐는지 고정한다. 정상 시나리오 테스트는 반대로 `EXPECT_EQ(record.sentinelInJob, testProcessInJob)`로 비교한다.

**예시:**
```cpp
::AssignProcessToJobObject(job, ::GetCurrentProcess());       // 도우미가 job에 들어감
::CreateProcessA(sentinel, ..., 0 /* 플래그 없음 */, ...);     // 자식이 job 상속
```

**관련 코드:**
- `tests/ipc/sentinel_in_job_helper.cpp:14-75` — 도우미
- `tests/ipc/test_sentinel_process.cpp:165-185` — 기록 검증

**증거:**
- §8.2, §8.2.3

**함정:** 상속은 조용하다 — 아무 오류도 없고 감시자는 정상으로 보인다. Maya가 죽을 때 함께 죽는 것으로만 드러난다.

**교훈:** 기본 동작이 위험한 경우, 그 기본을 재현하는 테스트를 둬 "탈출이 실제로 필요하다"를 증명한다.

#### `AssignProcessToJobObject` 비가역

**직관:** 프로세스를 job에 넣는 호출. **한 번 들어가면 나올 수 없다** — 탈출은 자식 생성 시점에만 가능하다.

**동작:** 도우미가 `AssignProcessToJobObject(job, GetCurrentProcess())`로 자기를 job에 넣는다. 실패하면 오류를 stderr에 적고 종료 코드로 알린다. 비가역이라는 성질이 Maro 설계의 근거다 — Maya가 이미 job 안이면 감시자를 "나중에 빼낼" 방법이 없으므로, `CreateProcess` 호출 순간에 breakaway 플래그를 주거나 WMI로 우회해야 한다.

**예시:**
```cpp
if (!::AssignProcessToJobObject(job, ::GetCurrentProcess())) {
    std::fprintf(stderr, "AssignProcessToJobObject failed: %lu\n", ::GetLastError());
}
// 이 뒤로 이 프로세스는 job에서 나올 수 없다
```

**관련 코드:**
- `tests/ipc/job_escape_test_helper.cpp:65-80` — 자기 할당
- `src/maro_ipc/src/JobEscape.cpp:21-60` — 생성 시점 탈출

**증거:**
- §8.2, §8.2.3, §11.4

**함정:** "나중에 정리하면 되지"가 통하지 않는 몇 안 되는 API다. 설계 결정을 호출 순간으로 앞당겨야 한다.

**교훈:** 비가역 연산은 설계의 제약이 된다. 되돌릴 수 없는 API 목록을 알고 있어야 순서를 맞출 수 있다.

#### `KILL_ON_JOB_CLOSE` 금지(도우미)

**직관:** job에 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`를 걸면 마지막 job 핸들이 닫힐 때 그 안의 프로세스가 전부 죽는다. 도우미가 자기 job의 유일한 핸들 소유자면 `CloseHandle(job)` 순간 자기가 죽는다.

**동작:** 두 도우미 모두 이 제한을 **절대 걸지 않는다**. 예전에 걸었을 때는 도우미가 job 핸들을 닫는 순간 Windows가 도우미(그리고 감시자)를 결정론적으로 죽였다 — 15/15 추적 실행에서 동일했다. 그러면 종료 코드로 시나리오 결과를 알리는 프로토콜이 무너진다. 도우미 소스 주석이 그 이력을 적어 둔다.

**예시:**
```cpp
// JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE는 절대 걸면 안 된다: 이 프로세스가
// 자기 job의 유일한 핸들 소유자라 CloseHandle(job) 순간 자기가 죽는다.
limits.BasicLimitInformation.LimitFlags = 0;   // BREAKAWAY_OK도 없음(거부 시나리오)
```

**관련 코드:**
- `tests/ipc/job_escape_test_helper.cpp:33-75` — 금지 이유와 이력 주석
- `tests/ipc/test_job_escape.cpp:83-100` — 종료 코드로 판정

**증거:**
- §8.2, §8.2.3

**함정:** 이 제한은 "정리를 자동화해 준다"는 점에서 매력적으로 보인다. 그러나 핸들 소유 구조에 따라 자기 자신을 죽인다.

**교훈:** 자동 정리 기능은 "누가 마지막 소유자인가"를 먼저 따진다. 그 답이 자기 자신이면 자살 장치가 된다.

#### 결정론적 자살 15/15

**직관:** `KILL_ON_JOB_CLOSE`가 걸린 job에서 유일한 핸들 소유자가 핸들을 닫으면 **매번** 죽는다는 실측 — 15회 추적 실행이 모두 같았다.

**동작:** 확률적 경합이 아니라 정의된 동작이므로 재현이 100%다. 그래서 "가끔 테스트가 죽는다"가 아니라 "항상 죽는다"였고, 원인을 좁히기 쉬웠다. 수정은 제한 플래그를 빼는 것이었고, 도우미는 종료 코드(0=job 정책 거부, 4=job과 무관한 실패 등)로 시나리오 결과를 보고한다.

**예시:**
```
KILL_ON_JOB_CLOSE + 유일 핸들 소유자 → CloseHandle(job) → 15/15 자기 종료
플래그 제거 → 도우미가 정상 종료 코드를 남기고 끝남
```

**관련 코드:**
- `tests/ipc/job_escape_test_helper.cpp:33-60` — 이력과 현재 설정
- `tests/ipc/test_job_escape.cpp:83-100` — 종료 코드 해석

**증거:**
- §8.2, §8.2.3

**함정:** 100% 재현되는 실패는 "환경 문제"로 오해되기 쉽다 — 내 코드가 아니라 OS가 죽인 것처럼 보이기 때문이다. 실제로는 우리가 건 플래그가 원인이다.

**교훈:** 재현율 100%는 정의된 동작의 신호다. 확률이 아니라 문서를 본다.

#### `DETACHED_PROCESS` 프로브

**직관:** 콘솔 창 튐을 재현하기 위해 테스트가 만드는 "콘솔 없는 부모". 진짜 Maya(GUI 서브시스템) 조건을 인위적으로 만드는 장치다.

**동작:** 테스트가 `console_window_probe.exe`를 `DETACHED_PROCESS`로 띄운다. 그 프로브 안에서 `maro_ipc`의 진짜 spawn 함수(tier 1/2)로 감시자를 `report` 모드로 띄우고, `GetConsoleWindow()`+`IsWindowVisible` 결과를 파일에 남긴다. 프로브는 자기 콘솔 상태도 `<outfile>.parent`에 적어 전제를 검증한다. tier 2(WMI)는 자식이 WMI 서비스 밑에서 비동기로 생기므로 결과 파일을 100×50ms 폴링한다.

**예시:**
```
테스트 → DETACHED_PROCESS로 프로브 기동(콘솔 없음)
프로브 → tier1/tier2 spawn → 감시자
감시자 → <outfile>에 콘솔 가시성 기록, 프로브는 <outfile>.parent에 전제 기록
```

**관련 코드:**
- `tests/ipc/test_console_window.cpp:44-70` — 프로브 기동과 폴링
- `tests/ipc/console_window_probe.cpp:18-90` — 두 모드와 결과 파일

**증거:**
- §8.2, §8.2.3

**함정:** WMI 경로는 비동기라 결과 파일이 바로 생기지 않는다. 폴링 없이 읽으면 "실패"로 오판한다.

**교훈:** 테스트가 재현해야 하는 것이 환경 조건이라면, 그 조건을 만드는 것부터 테스트의 일부다.
