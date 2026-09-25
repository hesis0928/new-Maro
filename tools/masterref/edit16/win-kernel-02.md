<!-- win-kernel-02 Windows › 커널 객체·동기화 2/2 (24개) 2026-09-24 -->

#### `ole32`

**직관:** COM 런타임이 들어 있는 시스템 라이브러리. `boost::stacktrace`의 Windows 백엔드가 디버깅 엔진(dbgeng)을 COM으로 부르므로 함께 링크해야 한다.

**동작:** 플러그인 CMake가 `target_link_libraries(${PROJECT_NAME} dbgeng ole32)`로 둘을 링크한다. 둘 다 Windows SDK 시스템 라이브러리라 배포할 DLL이 없다. Boost는 devkit이 `devkitBase/include/boost`로 헤더 온리 제공하며, `MaroStackTrace.cpp`가 boost를 보는 유일한 번역 단위다. 라이브러리 링크 순서는 `maro_transform → maro_lidar → maro_diag → dbgeng ole32 → maro_ipc`다.

**예시:**
```cmake
# boost::stacktrace의 MSVC 백엔드가 dbgeng를 COM으로 부른다
target_link_libraries(${PROJECT_NAME} dbgeng ole32)
```

**관련 코드:**
- `src/maro_plugin/CMakeLists.txt:82-86` — 링크와 이유 주석
- `src/maro_plugin/MaroStackTrace.cpp:1-10` — 유일한 boost TU

**증거:**
- §6.0, §6.7.2

**함정:** COM은 스레드마다 초기화(`CoInitializeEx`)가 필요하다. 스택 트레이스를 아무 스레드에서나 뜨면 COM 초기화 상태에 따라 동작이 달라진다.

**교훈:** "헤더 온리 라이브러리"도 링크 의존성을 가질 수 있다. 백엔드가 무엇을 쓰는지 확인한다.

#### 정적 변수 소멸

**직관:** 번역 단위의 정적 객체는 프로세스 종료나 DLL 언로드 시 소멸자가 실행된다. 플러그인에서는 그 시점이 "Maya가 이미 해체를 시작한 뒤"라 위험하다.

**동작:** `uninitializePlugin`이 return하면 Maya가 `FreeLibrary`를 부르고 `DLL_PROCESS_DETACH`에서 이 TU의 정적 변수가 소멸한다. `g_runtime`은 `unique_ptr`이라 그때 `~MaroRosRuntime() → stop() → shutdown()`이 돈다 — 즉 "`reset()`을 안 부르는 것"은 해결이 아니라 "return으로 위장한 지연"일 뿐이다. 그래서 정리는 `uninitializePlugin` 안에서 명시적으로 한다. 같은 이유로 Embree 디바이스도 함수 지역 static이 아니라 명시적 수명으로 관리한다.

**예시:**
```cpp
// uninitializePlugin에서 명시적으로:
if (g_runtime) { g_runtime->stop(); g_runtime.reset(); }
// 안 그러면 DLL_PROCESS_DETACH에서 소멸자가 돌아 rcl이 이미 내려간 뒤 stop()이 불린다
```

**관련 코드:**
- `src/maro_plugin/MaroPluginMain.cpp:530-640` — 명시적 정리
- `src/maro_lidar/include/maro_lidar/ScanEngine.h` — 함수 지역 static을 피한 이유

**증거:**
- §6.1, §6.4

**함정:** DLL 언로드 중에는 다른 DLL이 이미 언로드됐을 수 있다. 소멸자에서 외부 라이브러리를 부르면 이미 사라진 코드를 호출한다.

**교훈:** 플러그인의 정리는 호스트가 정한 시점(`uninitializePlugin`)에 끝낸다. RAII의 "언젠가"에 맡기지 않는다.

#### `ScopedProcessHandle`

**직관:** `OpenProcess`로 연 핸들을 소멸자에서 닫는 RAII 래퍼. 안 닫으면 로드마다 핸들이 새고 죽은 프로세스의 커널 오브젝트를 살려 둔다.

**동작:** `MaroDiag.cpp`의 리브니스 검사가 프로세스 핸들을 열어 `WaitForSingleObject(h, 0)`으로 상태를 보고 바로 닫아야 한다. 핸들을 들고 있으면 프로세스 오브젝트의 참조 카운트가 0이 되지 않아 PID 재사용까지 늦춰진다(F-123). 복사를 `delete`해 실수로 두 번 닫히지 않게 했다.

**예시:**
```cpp
class ScopedProcessHandle {
public:
    explicit ScopedProcessHandle(HANDLE handle) : handle_(handle) {}
    ~ScopedProcessHandle() { if (handle_) ::CloseHandle(handle_); }
    ScopedProcessHandle(const ScopedProcessHandle&) = delete;
};
```

**관련 코드:**
- `src/maro_plugin/MaroDiag.cpp:190-215` — 래퍼와 사용처

**증거:**
- §6.7, §6.7.1
- F-123

**함정:** 핸들 누수는 즉시 증상이 없다. 장시간 세션에서 핸들 수가 늘고 PID 재사용 판정이 어긋나는 형태로 나중에 나타난다.

**교훈:** 커널 핸들은 예외 없이 RAII로 감싼다. 조기 return 하나가 누수를 만든다.

#### `_getpid()` vs `GetCurrentProcessId`

**직관:** 같은 값(현재 프로세스 ID)을 주는 두 함수. CRT의 `_getpid()`는 `<process.h>`만 필요하고, Win32의 `GetCurrentProcessId`는 `<windows.h>`를 끌어온다.

**동작:** `MaroDiag.cpp`는 원래 windows.h 매크로 오염을 피하려 `_getpid()`를 썼다. 그런데 리뷰 Finding C1으로 리브니스 검사(`OpenProcess`/`WaitForSingleObject`)를 넣으면서 결국 windows.h를 포함하게 됐고, 주석이 그 사정을 기록한다 — "이 파일은 이미 windows.h를 포함하지만 `_getpid()`는 MSVC CRT 표준 헤더이고 내부적으로 같은 값을 준다"며 호출은 그대로 뒀다.

**예시:**
```cpp
#include <process.h>   // _getpid() -- Finding C1, see currentProcessId() below
// GetCurrentProcessId()가 아니라 _getpid()를 쓰는 이유는 이 파일이 이미 ...
```

**관련 코드:**
- `src/maro_plugin/MaroDiag.cpp:10-20` — 헤더와 사정 주석
- `src/maro_plugin/MaroDiag.cpp:179-185` — `currentProcessId()`

**증거:**
- §6.7, §6.7.1

**함정:** 두 함수의 반환 타입이 다르다(`int` vs `DWORD`). PID를 `uint64_t`로 정규화해 쓰는 것이 이름 규칙과도 맞는다.

**교훈:** 설계 이유가 나중에 무효가 되면 코드를 바꾸지 않더라도 주석을 갱신한다. "왜 아직 이런가"가 다음 사람의 질문이다.

#### windows.h 매크로 오염

**직관:** `<windows.h>`가 `min`, `max`, `ERROR` 같은 흔한 이름을 매크로로 정의해 사용자 코드와 충돌시키는 문제. 포함 자체를 미루는 것이 가장 간단한 회피책이다.

**동작:** Maro는 두 방향으로 대응한다 — (1) `NOMINMAX`·`WIN32_LEAN_AND_MEAN`을 빌드 정의로 전파, (2) windows.h가 꼭 필요한 파일에만 포함하고 나머지는 CRT 함수로 대체(`_getpid()`). 그럼에도 리브니스 검사 때문에 `MaroDiag.cpp`는 결국 포함하게 됐다. 같은 파일의 `ERROR` 매크로 충돌은 진단 열거형 이름을 다르게 지어 피했다.

**예시:**
```cpp
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include <windows.h>        // 이 순서가 아니면 min/max 매크로가 살아난다
```

**관련 코드:**
- `src/maro_ipc/CMakeLists.txt:30` — 정의 전파
- `src/maro_plugin/MaroDiag.cpp:10-20` — 포함을 미루려던 흔적

**증거:**
- §6.7, §6.7.1

**함정:** 매크로는 전처리 단계라 네임스페이스·`static`이 막아 주지 않는다. 한 헤더가 포함되면 그 TU 전체가 오염된다.

**교훈:** 플랫폼 헤더는 "필요한 TU에서만, 정의를 먼저"라는 두 규칙으로 가둔다.

#### `kMaxFrames=24`

**직관:** 스택 트레이스를 몇 프레임까지 뜰지의 상한. 깊을수록 정보가 많지만 심볼화 비용이 프레임마다 든다.

**동작:** `MaroStackTrace.cpp`가 `boost::stacktrace::stacktrace trace(kSkipFrames, kMaxFrames)`로 24프레임을 뜬다. Windows 기본 백엔드 `BOOST_STACKTRACE_USE_WINDBG`는 dbgeng(COM)로 심볼화하므로 프레임당 수 ms가 들고 COM 초기화 비용도 있다. 캡처(`stacktrace()`)는 싸고 문자열화(`to_string`)가 비싸므로, 래치 확인은 락 안에서 하고 심볼화는 락 밖에서 한다.

**예시:**
```cpp
constexpr std::size_t kMaxFrames = 24;
const boost::stacktrace::stacktrace trace(kSkipFrames, kMaxFrames);
```

**관련 코드:**
- `src/maro_plugin/MaroStackTrace.cpp:21` — 상한 상수
- `src/maro_plugin/MaroStackTrace.cpp:80` — 캡처 호출

**증거:**
- §6.7, §6.7.2

**함정:** 재귀 호출이 깊으면 24프레임이 전부 같은 함수라 원인이 안 보인다. 그런 경우를 위해 덤프도 함께 남긴다.

**교훈:** 진단 정보의 양은 비용과 거래다. 상한을 상수로 두고 왜 그 값인지 주석에 남긴다.

#### `kSkipFrames=2`

**직관:** 스택 트레이스 앞쪽에서 건너뛸 프레임 수 — 트레이스를 뜨는 우리 함수 자신이 보이지 않게 한다. 2로 보수적으로 잡았다.

**동작:** 실측 Release 빌드에서 0번 프레임이 항상 `BoadMaro::error`라 3이 더 읽기 좋았다. 그러나 인라이닝에 따라 프레임 수가 변하므로, 넉넉히 건너뛰다 진짜 실패 지점을 잘라 먹으면 스택 트레이스의 존재 이유가 사라진다. 비용이 비대칭(잘라 먹는 손해 > 한 줄 더 보이는 성가심)이라 2로 정했다.

**예시:**
```cpp
constexpr std::size_t kSkipFrames = 2;   // 3이 더 예쁘지만 인라이닝에 좌우됨
```

**관련 코드:**
- `src/maro_plugin/MaroStackTrace.cpp:35` — 상수와 이유 주석
- `src/maro_plugin/MaroStackTrace.cpp:80` — 사용

**증거:**
- §6.7, §6.7.2

**함정:** Debug 빌드와 Release 빌드의 프레임 수가 다르다. Debug에서 맞춘 skip 값은 Release에서 한 프레임을 더 자른다.

**교훈:** 최적화에 좌우되는 상수는 보수적으로 잡는다. 손해가 비대칭이면 안전한 쪽으로.

#### 인라이닝

**직관:** 컴파일러가 함수 호출을 호출 지점에 펼쳐 넣는 최적화. 스택 프레임이 사라지므로 트레이스의 프레임 수와 내용이 빌드 설정에 따라 달라진다.

**동작:** Release 빌드에서는 작은 함수가 인라인돼 `BoadMaro::error` 아래 래퍼들이 보이지 않을 수 있다. 그래서 `kSkipFrames`를 고정값으로 두는 것이 위험하고, 2라는 보수적 값을 택했다. 같은 이유로 심볼화 결과의 줄 번호도 인라인된 코드에서는 이웃 줄을 가리킬 수 있다.

**예시:**
```
Debug:   error() → logImpl() → capture() → 실패 지점      (프레임 4)
Release: error() → 실패 지점                               (중간이 인라인됨)
```

**관련 코드:**
- `src/maro_plugin/MaroStackTrace.cpp:30-40` — 인라이닝을 언급한 주석
- `tools/crashtriage/symbolize.py:50-75` — 줄 번호가 없거나 부정확할 수 있는 심볼화

**증거:**
- §6.7, §6.7.2

**함정:** 인라인된 프레임은 "없는" 것이 아니라 "합쳐진" 것이다. 스택만 보고 호출 경로를 단정하면 틀릴 수 있다.

**교훈:** 스택 트레이스는 Release에서 근사치다. 그 사실을 아는 사람이 읽어야 하므로 진단 문서에 적는다.

#### `[I1]` 순서 강제

**직관:** 테스트가 검증하려는 경로(클라이언트 종료의 "즉시 감지")가 실제로 실행되도록 이벤트 순서를 강제하는 기법. 순서를 방치하면 절반쯤은 다른 경로로 통과해 버린다.

**동작:** `test_named_pipe.cpp`는 "클라이언트가 핸들을 완전히 닫은 **뒤에** 서버가 읽기를 건다"를 `clientClosed` 플래그로 강제한다(`:107-128`). 강제하지 않으면 읽기가 먼저 걸리는 순서가 나오고, 그 순서에서는 이미 걸린 `ReadFile`이 `ERROR_BROKEN_PIPE`로 완료되며 시간 조건을 그냥 만족한다 — 즉시 감지 경로를 코드에서 지워도 통과한다. `orderingForced` 플래그가 실제로 강제됐는지도 함께 단언한다.

**예시:**
```cpp
std::atomic<bool> clientClosed{false};
std::atomic<bool> orderingForced{false};
std::atomic<long long> detectMs{-1};
// 서버 스레드는 clientClosed가 참이 될 때까지 기다렸다가 읽기를 건다
```

**관련 코드:**
- `tests/ipc/test_named_pipe.cpp:105-130` — 플래그와 순서 강제
- `src/maro_ipc/src/NamedPipe.cpp:190-240` — 검증 대상 감지 경로

**증거:**
- §8.2, §8.2.3
- F-198

**함정:** "가끔 통과하는" 테스트는 플래키가 아니라 **경로가 두 개**라는 신호일 수 있다. 어느 경로를 검증하려는지 명시해야 한다.

**교훈:** 비동기 테스트는 "무엇이 먼저인가"를 코드로 고정한다. 타이밍에 맡기면 검증 대상이 매번 달라진다.

#### `clientClosed`

**직관:** 클라이언트가 파이프 핸들을 완전히 닫았음을 서버 스레드에 알리는 원자 플래그. 테스트의 순서 강제 장치다.

**동작:** 클라이언트 쪽이 `CloseHandle` 후 `clientClosed = true`로 세우고, 서버 스레드는 이 플래그가 참이 될 때까지 기다렸다가 `ReadFile`을 건다. 이렇게 해야 "이미 끊긴 파이프에 새로 거는 읽기"가 즉시 `ERROR_BROKEN_PIPE`를 반환하는 경로를 검증할 수 있다. 플래그가 없으면 읽기가 먼저 걸리는 다른 경로가 섞여 검증이 무의미해진다(F-198).

**예시:**
```cpp
// 클라이언트: 닫은 뒤에 표시
::CloseHandle(clientHandle);
clientClosed.store(true);
// 서버: 표시를 본 뒤에 읽기
while (!clientClosed.load()) std::this_thread::yield();
```

**관련 코드:**
- `tests/ipc/test_named_pipe.cpp:107-128` — 플래그 정의와 사용

**증거:**
- §8.2, §8.2.3
- F-198

**함정:** `bool` 대신 `std::atomic<bool>`이어야 한다. 최적화가 일반 bool 읽기를 루프 밖으로 끌어내면 영원히 기다린다.

**교훈:** 스레드 간 신호는 원자 타입으로. 테스트 코드라고 예외를 두지 않는다.

#### `orderingForced`

**직관:** "순서 강제가 실제로 일어났는가"를 기록하는 플래그. 테스트가 검증하려는 조건뿐 아니라 그 조건의 **전제**까지 단언하게 해 준다.

**동작:** 서버 스레드가 `clientClosed`를 기다렸다가 진행했으면 `orderingForced = true`로 세운다. 테스트는 마지막에 `detectMs < 1000`(즉시 감지)과 함께 `orderingForced`가 참인지도 단언한다 — 순서가 우연히 맞아떨어진 실행에서는 이 플래그가 거짓이라 테스트가 "검증하지 못했음"을 알린다.

**예시:**
```cpp
EXPECT_TRUE(orderingForced.load()) << "순서 강제가 실제로 일어나지 않았다";
EXPECT_LT(detectMs.load(), 1000) << "끊김을 즉시 감지하지 못했다";
```

**관련 코드:**
- `tests/ipc/test_named_pipe.cpp:107-130` — 두 플래그의 단언

**증거:**
- §8.2, §8.2.3
- F-198

**함정:** 전제를 단언하지 않으면 "통과했지만 아무것도 확인 못 한" 실행이 초록으로 보인다. 침묵하는 실패다.

**교훈:** 테스트는 결과뿐 아니라 "검증 조건이 성립했는가"도 단언한다. 전제 검증이 침묵하는 통과를 막는다.

#### `SentinelProcessGuard` 등 RAII

**직관:** 테스트가 띄운 프로세스·PID·도우미를 모든 경로에서 정리하는 RAII 가드들. gtest `ASSERT_*`는 실패 시 그냥 return이므로 그 뒤의 정리 코드가 실행되지 않는다.

**동작:** `SentinelProcessGuard`·`SentinelPidGuard`·`HelperProcessGuard`가 소멸자에서 `CloseHandle`과 필요하면 `TerminateProcess`를 부른다. 브리프 원본은 성공 경로에서만 핸들을 닫았고, 그 결과 "감시자가 상한 안에 안 죽는" 바로 그 실패에서 종료도 안 돌아 좀비가 남았다. `ThreadJoiner`도 같은 이유다 — joinable한 `std::thread`가 소멸하면 `std::terminate`로 프로세스 전체가 죽는다(실측: 200회 중 한 번 실패했을 때 스위트가 exit code 3으로 통째로 끝남).

**예시:**
```cpp
struct SentinelProcessGuard {
    PROCESS_INFORMATION info;
    ~SentinelProcessGuard() {
        if (info.hProcess) { ::TerminateProcess(info.hProcess, 1); ::CloseHandle(info.hProcess); }
    }
    SentinelProcessGuard(const SentinelProcessGuard&) = delete;
};
```

**관련 코드:**
- `tests/ipc/test_sentinel_process.cpp:60-90` — 가드들과 이유 주석
- `tests/ipc/test_named_pipe.cpp:23-28` — `ThreadJoiner`

**증거:**
- §8.2, §8.2.3

**함정:** `ASSERT_*`는 예외를 던지지 않고 return한다. try/finally가 없는 C++에서 정리를 보장하는 유일한 수단이 RAII다.

**교훈:** 프로세스를 띄우는 테스트는 실패 경로가 가장 더럽다. 정리를 소멸자에 두면 모든 경로가 같아진다.

#### 좀비 30초 CPU

**직관:** 실패한 감시자가 종료되지 않아 30초 더 살며 CPU 한 코어를 태우고, ctest는 물려받은 stdout 파이프가 닫힐 때까지 30초를 더 기다린 실측 사례.

**동작:** 정리를 성공 경로에만 뒀을 때 나타났다(F-118). 실패한 테스트가 남긴 감시자가 루프를 돌며 CPU를 쓰고, ctest는 자식의 stdout 파이프가 닫히기를 기다리느라 테스트 하나가 30초 넘게 걸렸다. RAII 가드로 모든 경로에서 `TerminateProcess`를 부르게 고치자 실패 시에도 즉시 끝났다.

**예시:**
```
실패한 감시자: 30초 생존, CPU 1코어 100%
ctest: 물려받은 stdout 파이프가 닫힐 때까지 30초 추가 대기
→ RAII 가드 도입 후 실패해도 즉시 종료
```

**관련 코드:**
- `tests/ipc/test_sentinel_process.cpp:60-90` — 가드 도입
- `tests/CMakeLists.txt:323-352` — 관련 테스트의 RUN_SERIAL

**증거:**
- §8.2, §8.2.3
- F-118

**함정:** 자식이 stdout을 물려받으면 부모가 기다리는 대상이 "자식의 종료"가 아니라 "파이프의 닫힘"이 된다. 손자까지 물려받으면 더 길어진다.

**교훈:** 테스트가 프로세스를 띄우면 정리 실패가 러너 전체를 느리게 만든다. 좀비는 성능 문제이기도 하다.

#### `sentinel_in_job_helper`

**직관:** "감시자가 job 안에 갇힌" 시나리오를 만드는 테스트 도우미 실행 파일. breakaway가 불허된 job에 스스로 들어간 뒤 평범한 `CreateProcess`로 감시자를 띄운다.

**동작:** `maro_sentinel_in_job_helper.exe <owner_maya_pid> <book_dir>`가 breakaway 불허 job을 만들어 자기를 넣고, breakaway 플래그 **없이** 감시자를 생성해 job을 상속시킨다. 그러면 `record.sentinelInJob == true`가 되고, 테스트는 이 값이 self-check에서 디스크(기록 파일)까지 배선됐음을 고정한다. 정상 시나리오 테스트는 반대로 `EXPECT_EQ(record.sentinelInJob, testProcessInJob)`로 비교한다.

**예시:**
```cpp
// 도우미: breakaway 불허 job에 들어간 뒤 평범한 CreateProcess
::AssignProcessToJobObject(job, ::GetCurrentProcess());
::CreateProcessA(sentinelPath, ..., 0 /* breakaway 플래그 없음 */, ...);
```

**관련 코드:**
- `tests/ipc/sentinel_in_job_helper.cpp:14-40` — 도우미
- `tests/ipc/test_sentinel_process.cpp:165-185` — `sentinelInJob` 단언

**증거:**
- §8.2, §8.2.3

**함정:** 도우미에 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`를 걸면 도우미가 끝날 때 감시자까지 죽어 시나리오가 성립하지 않는다. 그래서 job 도우미는 그 플래그를 절대 걸지 않는다.

**교훈:** "나쁜 상황"을 검증하려면 그 상황을 만드는 도우미가 필요하다. 도우미의 설정 하나가 시나리오를 무효화할 수 있다.

#### `IsWindowVisible`

**직관:** 윈도 핸들이 실제로 보이는 상태인지 확인하는 Win32 함수. 감시자를 띄울 때 콘솔 창이 깜빡이지 않는지 검증하는 관측 신호다.

**동작:** 프로브는 `GetConsoleWindow()`(콘솔이 없으면 NULL)와 `IsWindowVisible`을 조합해 `(consoleWindow != nullptr && ::IsWindowVisible(consoleWindow)) ? 1 : 0`을 기록한다. 테스트는 프로브를 `DETACHED_PROCESS`로 띄워 "콘솔 없는 부모"를 인위적으로 만들고, 그 안에서 `maro_ipc`의 진짜 spawn 함수(tier 1/2)로 감시자를 `report` 모드로 띄운다.

**예시:**
```cpp
HWND consoleWindow = ::GetConsoleWindow();
const int visible = (consoleWindow != nullptr && ::IsWindowVisible(consoleWindow)) ? 1 : 0;
```

**관련 코드:**
- `tests/ipc/console_window_probe.cpp:31-55` — 관측 신호
- `tests/ipc/test_console_window.cpp:44-60` — `DETACHED_PROCESS`로 띄우기

**증거:**
- §8.2, §8.2.3

**함정:** 개발자 머신에서 테스트를 콘솔에서 돌리면 부모에 콘솔이 있어 시나리오가 성립하지 않는다. `DETACHED_PROCESS`로 전제를 인위적으로 만들어야 한다.

**교훈:** UI 부작용(창 깜빡임)도 관측 가능한 신호로 바꾸면 테스트할 수 있다. 신호를 먼저 정한다.

#### 결과 파일

**직관:** 콘솔이 없을 수 있는 프로세스의 결과를 stdout이 아니라 **파일**로 남기는 것. 콘솔이 없으면 stdout을 신뢰할 수 없기 때문이다.

**동작:** 콘솔 프로브는 관측 결과를 `<outfile>`에 쓰고, 자기 자신의 콘솔 상태는 `<outfile>.parent`에 남긴다. tier 2(WMI)로 띄운 자식은 WMI 서비스 밑에서 비동기로 생기므로, 테스트가 결과 파일을 100회 × 50ms로 폴링해 기다린다. 파일이라 프로세스가 죽은 뒤에도 읽을 수 있다.

**예시:**
```cpp
writeReport(outPath.c_str());                 // 관측 결과
writeReport((outPath + ".parent").c_str());   // 전제(부모의 콘솔 상태)
// 테스트: 100 × 50ms 폴링으로 파일 생성 대기
```

**관련 코드:**
- `tests/ipc/console_window_probe.cpp:80-90` — 두 파일 쓰기
- `tests/ipc/test_console_window.cpp:50-70` — 폴링 읽기

**증거:**
- §8.2, §8.2.3

**함정:** 파일 쓰기가 끝나기 전에 읽으면 빈 파일이나 잘린 내용을 본다. "없음"과 "아직 쓰는 중"을 구분하는 폴링이 필요하다.

**교훈:** 프로세스 경계를 넘는 관측은 stdout보다 파일이 견고하다. 단, 원자성(쓰는 중)을 함께 다룬다.

#### `.parent` 전제 검증

**직관:** 테스트의 전제("정말 콘솔 없는 부모였는가")를 결과와 함께 파일로 남겨 검증하는 기법. 전제가 깨진 실행은 통과해도 의미가 없다.

**동작:** 프로브는 `report` 모드에서 자기 콘솔 상태를 `<outfile>`에, `spawn` 모드에서 자신(=부모 역할)의 콘솔 상태를 `<outfile>.parent`에 적는다(`:98-104`). 테스트는 `.parent` 파일이 "콘솔 없음"을 말하는지 먼저 확인하고, 그 다음에야 자식의 창 가시성 결과를 단언한다. `orderingForced`와 같은 계열의 "전제까지 단언" 설계다.

**예시:**
```cpp
// 1) 전제: 부모에 콘솔이 없었는가
EXPECT_EQ(readReport(parentPath), 0) << "부모에 콘솔이 있어 시나리오가 성립하지 않음";
// 2) 결과: 자식이 콘솔 창을 띄우지 않았는가
EXPECT_EQ(readReport(outPath), 0);
```

**관련 코드:**
- `tests/ipc/console_window_probe.cpp:80-90` — `.parent` 기록
- `tests/ipc/test_console_window.cpp:50-70` — 전제 먼저 단언

**증거:**
- §8.2, §8.2.3

**함정:** 전제를 주석으로만 적으면 환경이 바뀌었을 때 아무도 모른다. 코드가 확인해야 깨진 순간에 알 수 있다.

**교훈:** "이 테스트는 X를 가정한다"는 문장은 단언으로 바꿀 수 있다. 가정이 깨지면 테스트가 먼저 알려 준다.

#### 공유 감시자 기각 4근거

**직관:** "감시자 하나를 여러 Maya가 공유하자"는 대안을 기각한 네 가지 이유. C-1 결정(08-19)으로 프로세스별 감시자가 확정됐다.

**동작:** 근거는 (1) 공유하면 감시자가 멀티클라이언트 **서버**가 되어 복잡도가 급증, (2) 한 클라이언트의 문제가 다른 클라이언트에 번져 **실패 격리**가 깨짐, (3) 마지막 Maya가 꺼질 때 누가 감시자를 끝내는지 하는 **수명 관리** 문제, (4) 저널이 이미 프로세스별 파일이라 **모양이 일치**. 같은 결정에서 킬 스위치를 PID별로 재해석하고, 자가 점검을 축소했다.

**예시:**
```
공유 감시자: 서버화 + 실패 전파 + 수명 모호
프로세스별:  Global\maro_sentinel_mutex_<pid>, maro_sentinel.<pid>.json, 저널과 같은 모양
```

**관련 코드:**
- `src/maro_ipc/src/Naming.cpp:5-20` — PID별 이름 규칙
- `src/maro_diag/src/JournalWriter.cpp:283` — 프로세스별 저널 파일

**증거:**
- §9.2, §9.2.2

**함정:** "리소스를 아끼자"는 공유 설계는 수명·격리 문제를 대가로 가져온다. 프로세스 하나가 아끼는 비용보다 크다.

**교훈:** 아키텍처 결정은 기각한 대안과 그 이유를 함께 남긴다. 나중에 같은 제안이 다시 나온다.

#### 좀비 mayapy

**직관:** 테스트가 끝나도 살아남은 `mayapy.exe` 프로세스. `maro.mll`을 로드한 채이므로 다음 빌드가 DLL을 쓰지 못해 `LNK1168`로 막힌다.

**동작:** 테스트가 타임아웃되거나 크래시 세션이 제대로 안 끝나면 남는다(F-015). 오케스트레이터가 `subprocess.run(timeout=...)`으로 죽이고 `wait_for_process_exit`로 실제 종료를 확인하는 것이 예방책이다. 이미 생겼으면 `taskkill /F`, 그래도 안 죽으면 WMI `Invoke-CimMethod Terminate`.

**예시:**
```powershell
Get-Process mayapy -ErrorAction SilentlyContinue
taskkill /F /IM mayapy.exe
```

**관련 코드:**
- `tests/maya/test_journal.py:9-12` — 좀비 방지 설계 주석
- `tests/maya/test_sentinel.py:118-160` — 종료 확인 폴링

**증거:**
- §9.3
- F-015

**함정:** 좀비는 빌드 오류(`LNK1168`)로 처음 드러나므로 링커 문제로 오인한다. "누가 파일을 쥐고 있나"를 먼저 본다.

**교훈:** 테스트가 프로세스를 띄우는 환경에서는 "정리 실패"가 빌드 실패로 나타난다. 두 단계를 연결해 생각한다.

#### `taskkill /F`

**직관:** Windows에서 프로세스를 강제 종료하는 CLI. `/F`가 강제, `/IM`이 이미지 이름, `/PID`가 프로세스 ID 지정이다.

**동작:** 좀비 mayapy 정리의 첫 수단이다. 실패하면(액세스 거부, 종료 중 상태) WMI `Invoke-CimMethod Terminate`로 넘어간다 — 같은 2단계 구조가 감시자 spawn의 tier 1/2와 대칭이다. 자동화 스크립트에서는 종료 후 프로세스가 실제로 사라질 때까지 폴링해야 한다.

**예시:**
```powershell
taskkill /F /IM mayapy.exe
# 안 죽으면
Get-CimInstance Win32_Process -Filter "Name='mayapy.exe'" | Invoke-CimMethod -MethodName Terminate
```

**관련 코드:**
- `tests/maya/test_sentinel.py:118-160` — 종료 확인 폴링
- `src/maro_ipc/src/JobEscape.cpp:200-260` — WMI 경로(같은 2단계 구조)

**증거:**
- §9.3
- F-015

**함정:** `taskkill`이 성공을 보고해도 프로세스가 즉시 사라지지는 않는다. 파일 핸들이 풀릴 때까지 기다려야 다음 빌드가 성공한다.

**교훈:** "죽이라고 명령했다"와 "죽었다" 사이에 시간이 있다. 자동화는 그 간극을 폴링으로 메운다.

#### "모든 대기에 타임아웃" 원칙

**직관:** 감시자·IPC 코드의 제1 규칙 — 무기한 블로킹이 한 군데도 없어야 한다. 하나라도 있으면 그 지점이 좀비를 만든다.

**동작:** 명명된 파이프는 오버랩 I/O로 걸고 `WaitForSingleObject(hEvent, timeoutMs)`로 기다린다. 파이프 생성 시 기본 타임아웃은 0으로 두고 "실제 대기는 전부 오버랩+`WaitForSingleObject`로 직접 건다"고 주석에 적는다. 감시자의 상수 표가 곧 설계다 — 접속 대기 15초(좀비 방지), 폴링 500ms(킬 이벤트 확인 주기), 첫 메시지 30초, 끊김 판정은 타임아웃의 1/5도 안 쓰고 돌아온 실패 3연속, 50ms 백오프(핫 루프 CPU 99% 방지), 12시간 절대 수명.

**예시:**
```cpp
constexpr DWORD kReceivePollMs = 500;
constexpr std::uint64_t kDidNotWaitMs = kReceivePollMs / 5;   // 끊김 판정 기준
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:27,131` — 오버랩 대기와 기본 타임아웃 0
- `src/maro_sentinel/main.cpp:25-45` — 상수 표

**증거:**
- §5.3.4, §5.4, §10.8

**함정:** 블로킹 API의 기본값이 "무한 대기"인 경우가 많다(`WaitForSingleObject(h, INFINITE)`, 파이프 기본 타임아웃). 명시하지 않으면 규칙이 깨진다.

**교훈:** "무기한 대기 없음"은 코드 리뷰 체크리스트가 아니라 파일 머리 주석에 적는 원칙이 된다. 예외는 세어서 관리한다.

#### 의도된 예외 2개

**직관:** "모든 대기에 타임아웃" 규칙을 지키지 않는 두 자리. 지우지 말라는 주석과 함께 왜 안전한지가 적혀 있다.

**동작:** 하나는 `CancelIoEx` 뒤의 `GetOverlappedResult(bWait=TRUE)`다 — 여기 도달했다는 것은 취소 대상 I/O가 실제로 걸려 있었고 커널이 반드시 `ERROR_OPERATION_ABORTED`로 완료시킨다는 뜻이라 대기가 **구조적으로 유한**하다. 타임아웃을 넣으면 오히려 아직 쓰이는 `OVERLAPPED`를 스택에서 날려 버릴 수 있다. 다른 하나는 `waitForFlag` 계열이다. 주석 `**"의도된 예외, 지우지 말 것"**`이 그 사정을 적는다.

**예시:**
```cpp
// **의도된 예외, 지우지 말 것**: 아래 bWait=TRUE는 이 저장소에서 "모든 대기에
// 타임아웃" 규칙을 지키지 않는 유일한 자리이고 그것이 맞다.
if (::CancelIoEx(handle, &overlapped)) {
    ::GetOverlappedResult(handle, &overlapped, &bytes, TRUE);
}
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:29-50` — 예외와 근거 주석

**증거:**
- §5.3.4, §10.8

**함정:** 취소 후 `OVERLAPPED`가 스택에 있는데 기다리지 않고 함수를 나가면, 커널이 나중에 그 주소에 쓴다 — 스택 손상이다. 타임아웃이 오히려 위험한 유일한 경우다.

**교훈:** 규칙에는 예외가 있을 수 있다. 예외의 수를 세고, 각각에 "왜 안전한가"를 코드 옆에 적는다.

#### 단조 시계 원칙

**직관:** 경과 시간·데드라인 계산에는 벽시계가 아니라 단조 증가 시계(`GetTickCount64`, `steady_clock`)를 쓴다. 시스템 시간 동기화가 끼어들어도 흔들리지 않는다.

**동작:** `NamedPipe.cpp`는 `const ULONGLONG deadlineTick = ::GetTickCount64() + timeoutMs;`로 데드라인을 잡고 루프에서 `::GetTickCount64() >= deadlineTick`을 확인한다(주석: "GetTickCount64는 넘치지 않는다"). 감시자 `main.cpp`는 `using SteadyClock = std::chrono::steady_clock;`로 같은 원칙을 C++ 쪽에 적용한다. 테스트 상대역도 `steady_clock` 데드라인을 쓴다.

**예시:**
```cpp
const ULONGLONG deadlineTick = ::GetTickCount64() + timeoutMs;
while (...) { if (::GetTickCount64() >= deadlineTick) return false; }
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:203-240` — `GetTickCount64` 데드라인
- `src/maro_sentinel/main.cpp:75` — `SteadyClock` 별칭
- `tests/peer/maro_test_peer.cpp:38-45` — 테스트의 같은 원칙

**증거:**
- §10.8

**함정:** 32비트 `GetTickCount`는 약 49일마다 넘친다. 64비트 버전은 넘치지 않으므로 항상 `GetTickCount64`를 쓴다.

**교훈:** "지금 몇 시인가"와 "얼마나 지났는가"는 다른 시계로 답한다. 후자는 언제나 단조 시계다.

#### Win32 커널 오브젝트 모델(핸들·시그널 상태·명명·보안 디스크립터)

**직관:** 프로세스·스레드·뮤텍스·이벤트·파이프·job이 공유하는 공통 규칙 — 핸들로 참조하고, 참조 카운트가 0이면 파괴되고, 동기화 객체는 시그널/비시그널 상태를 가지며, 이름으로 프로세스 간에 공유된다.

**동작:** 이 모델이 Maro의 IPC 설계 전체를 관통한다. 핸들 누수는 곧 오브젝트 생존이라 `ScopedProcessHandle`·`ScopedHandle` RAII가 필요하고, 프로세스가 종료 시 시그널 상태가 되는 성질이 리브니스 판정의 근거이며, `Global\` 명명이 세션 경계를 넘는 공유를 가능하게 한다. 보안 디스크립터(기본 nullptr)는 생성자 토큰의 기본 DACL을 쓰므로 같은 사용자의 프로세스끼리만 열 수 있다.

**예시:**
```
핸들      → 참조 카운트 (누수 = 오브젝트 생존)
시그널    → 프로세스·스레드는 종료 시, 뮤텍스는 미소유 시, 이벤트는 Set 시
이름      → Global\ / Local\ 네임스페이스로 프로세스 간 공유
보안      → nullptr이면 생성자 토큰의 기본 DACL
```

**관련 코드:**
- `src/maro_ipc/src/NamedMutexGuard.cpp:5-34` — 뮤텍스 수명
- `src/maro_plugin/MaroDiag.cpp:190-215` — 프로세스 핸들과 시그널 판정
- `src/maro_ipc/src/Naming.cpp:5-20` — 명명

**증거:**
- §11.4

**함정:** 오브젝트는 "만든 프로세스"가 아니라 "마지막 핸들"이 죽을 때 사라진다. 만든 쪽이 끝나도 남아 있을 수 있다.

**교훈:** 플랫폼의 객체 모델을 한 번 정리해 두면 개별 API가 규칙의 사례로 읽힌다. 새 API를 만나도 질문이 같아진다.
