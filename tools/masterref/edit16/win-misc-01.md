<!-- win-misc-01 Windows › 로더·DLL + 파일 시스템·시간 + 보안 (23개) 2026-09-24 -->

#### 임포트 테이블

**직관:** PE 파일이 로드 시 요구하는 DLL과 심볼의 목록. "이 바이너리가 무엇에 의존하는가"의 정적 답이다.

**동작:** `maro_lidar`의 configure 단계가 해석된 `embree4.dll`의 임포트 테이블을 `dumpbin /dependents`로 검사해 `tbb12.dll`류가 있으면 빌드를 멈춘다. TBB 기능이 켜진 Embree는 그 DLL을 임포트하는데 Maya가 이미 자기 `tbb12.dll`을 갖고 있어 로더가 그것을 재사용하고, 기대한 심볼이 없어 `ERROR_PROC_NOT_FOUND`가 난다. 임포트 테이블 검사가 그 사고를 빌드 시점으로 앞당긴다.

**예시:**
```powershell
dumpbin /dependents embree4.dll
#   tbb12.dll   ← 이 줄이 있으면 잘못된 빌드
```

**관련 코드:**
- `src/maro_lidar/CMakeLists.txt:36-60` — 임포트 테이블 가드
- `python/maroTechDiag.py:542-575` — 런타임 실측 진단

**증거:**
- §3.3, §5.2.1

**함정:** 지연 로드(`/DELAYLOAD`)나 `LoadLibrary` 호출은 임포트 테이블에 안 나온다. 정적 목록이 전부가 아니다.

**교훈:** 의존성은 정적(임포트 테이블)과 동적(런타임 로드) 둘 다 본다. 검사도 두 층에 둔다.

#### `LOAD_WITH_ALTERED_SEARCH_PATH`

**직관:** `LoadLibraryEx`의 플래그로, 로드되는 DLL **자신의** 디렉터리를 의존 DLL 검색의 첫 후보로 만든다. Maya의 플러그인 로더는 이 플래그를 쓰지 않는다.

**동작:** 그래서 Maya가 `maro.mll`을 찾아 로드해도, `.mll`이 임포트하는 ROS DLL 154개는 `.mll` 옆 폴더에서 찾아지지 않는다(F-005). 해결 경로는 셋이다 — ctest가 환경에 PATH를 주입, 사용자가 수동으로 PATH 설정, `.mod` 파일의 `PATH +:=`. 테스트 CMake는 `$<TARGET_FILE:...>`로 도우미 경로를 컴파일 타임 상수화하고 PATH를 테스트 환경에 주입한다.

**예시:**
```
LoadLibraryEx(path, LOAD_WITH_ALTERED_SEARCH_PATH)  → path의 폴더가 검색 1순위
Maya의 플러그인 로드                                  → 그 플래그 없음 → PATH 필요
```

**관련 코드:**
- `src/maro_plugin/CMakeLists.txt:110-130` — DLL 스테이징
- `tests/CMakeLists.txt:217-234` — 테스트용 PATH 주입

**증거:**
- §3.6, §8.1, §11.4
- F-005

**함정:** 개발자가 이미 PATH에 ROS를 넣어 둔 머신에서는 문제가 보이지 않는다. 깨끗한 머신에서만 드러난다.

**교훈:** 호스트가 우리 DLL을 어떻게 로드하는지가 배포 설계를 정한다. 플래그 하나가 PATH 전략을 강제한다.

#### 표준 DLL 검색 순서

**직관:** Windows가 DLL을 찾는 고정된 순서 — 실행 파일 디렉터리 → 시스템 디렉터리 → 16비트 시스템 → Windows 디렉터리 → 현재 디렉터리(SafeDllSearchMode에 따라) → PATH.

**동작:** 중요한 점은 "실행 파일 디렉터리"가 **프로세스 실행 파일**(`maya.exe`/`mayapy.exe`)의 폴더이지 우리 `.mll`의 폴더가 아니라는 것이다. 그래서 `maro.mll`이 임포트하는 154개 DLL을 찾을 때 플러그인 자신의 디렉터리는 아예 후보가 아니며, PATH만이 우리가 끼어들 수 있는 자리다.

**예시:**
```
maya.exe (C:\Program Files\Autodesk\Maya2026\bin)
  → maro.mll (D:\maro\plug-ins)  임포트 rclcpp.dll
검색: Maya bin → System32 → ... → PATH        (D:\maro\plug-ins는 없음)
```

**관련 코드:**
- `src/maro_plugin/CMakeLists.txt:110-130` — 스테이징(PATH 전제)
- `tests/CMakeLists.txt:217-234` — PATH 주입

**증거:**
- §3.6, §8.1

**함정:** "현재 디렉터리"는 SafeDllSearchMode(기본 켜짐)에서 순서가 뒤로 밀린다. CWD에 DLL을 두는 방식은 신뢰할 수 없다.

**교훈:** 검색 순서를 외우기보다 "우리가 통제할 수 있는 항목이 무엇인가"로 읽는다. 여기서는 PATH뿐이다.

#### `FreeLibrary`

**직관:** 로드된 DLL의 참조를 하나 줄이고, 0이 되면 언로드하는 함수. Maya가 플러그인을 내릴 때 부른다.

**동작:** `uninitializePlugin`이 return하면 Maya가 `FreeLibrary`를 부르고 그 과정에서 `DLL_PROCESS_DETACH`가 TU의 정적 변수들을 소멸시킨다. 그래서 `g_runtime`(`unique_ptr`)을 "그냥 두는" 것은 정리를 피하는 것이 아니라 **가장 나쁜 시점으로 미루는 것**이다 — 그때는 rcl·Maya가 이미 해체를 시작한 뒤다. 정리는 `uninitializePlugin` 안에서 명시적으로 끝낸다.

**예시:**
```
uninitializePlugin() return → Maya가 FreeLibrary → DLL_PROCESS_DETACH
→ 정적 unique_ptr 소멸 → ~MaroRosRuntime() → stop() → 너무 늦은 shutdown()
```

**관련 코드:**
- `src/maro_plugin/MaroPluginMain.cpp:530-640` — 명시적 정리
- `src/maro_lidar/include/maro_lidar/ScanEngine.h` — 함수 지역 static 회피

**증거:**
- §6.1, §6.4

**함정:** 언로드 중에는 다른 DLL이 이미 내려갔을 수 있다. 소멸자에서 외부 API를 부르면 사라진 코드를 호출한다.

**교훈:** 호스트가 정한 정리 시점(`uninitializePlugin`)을 정리의 마감으로 삼는다. RAII의 "언젠가"에 맡기지 않는다.

#### `DLL_PROCESS_DETACH`

**직관:** DLL이 언로드되거나 프로세스가 끝날 때 `DllMain`에 전달되는 알림. C++ 정적 객체의 소멸자가 이 시점에 돈다.

**동작:** 이 시점에는 로더 락이 잡혀 있어 할 수 있는 일이 매우 제한된다 — 스레드 생성·동기화 대기·다른 DLL 호출이 모두 위험하다. Maro의 `~MaroRosRuntime()`이 여기서 돌면 `stop()`이 스레드 join을 시도해 교착할 수 있다. 그래서 "return으로 위장한 지연"을 금지하고 명시적 정리를 둔다.

**예시:**
```cpp
// 위험: DLL_PROCESS_DETACH에서 도는 정리
static std::unique_ptr<MaroRosRuntime> g_runtime;   // 소멸자가 스레드 join
// 안전: uninitializePlugin에서 g_runtime->stop(); g_runtime.reset();
```

**관련 코드:**
- `src/maro_plugin/MaroPluginMain.cpp:530-640` — 명시적 정리
- `src/maro_plugin/MaroRosRuntime.cpp:90-112` — join을 포함한 stop

**증거:**
- §6.1, §6.4

**함정:** 로더 락 아래의 스레드 join은 전형적인 교착 패턴이다. 증상은 "Maya가 종료되지 않음"이다.

**교훈:** 프로세스/DLL 종료 콜백은 "거의 아무것도 하지 않는" 곳이다. 무거운 정리는 그 전에 끝낸다.

#### `GetModuleHandleExA(FROM_ADDRESS|UNCHANGED_REFCOUNT)`

**직관:** 함수 주소를 주면 그 코드가 속한 모듈의 핸들을 돌려주는 호출. "내가 속한 DLL이 어디 있나"를 CWD·PATH에 기대지 않고 알아내는 방법이다.

**동작:** `sentinelExeDirectory()`가 자기 함수의 주소(`&sentinelExeDirectory`)를 넘겨 `maro.mll`의 핸들을 얻고 `GetModuleFileNameA`로 경로를 구한 뒤 부모 디렉터리를 돌려준다. `UNCHANGED_REFCOUNT`는 참조 카운트를 올리지 않아 `FreeLibrary` 짝이 필요 없다는 뜻이다. 감시자 exe가 `.mll` 옆에 스테이징되므로 이 경로가 곧 실행 파일 위치다.

**예시:**
```cpp
char modulePath[MAX_PATH] = {};
HMODULE thisModule = nullptr;
::GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                     reinterpret_cast<LPCSTR>(&sentinelExeDirectory), &thisModule);
```

**관련 코드:**
- `src/maro_plugin/MaroSentinelClient.cpp:41-60` — 자기 모듈 경로
- `src/maro_ipc/src/JobEscape.cpp:21-60` — 그 경로로 spawn

**증거:**
- §6.7, §6.7.3

**함정:** `UNCHANGED_REFCOUNT` 없이 부르면 참조가 하나 늘어 DLL이 영영 언로드되지 않는다. 플러그인에서는 치명적이다.

**교훈:** "내 위치"는 CWD나 PATH가 아니라 모듈 핸들로 묻는다. 그래야 호스트가 어디서 실행하든 맞는다.

#### `GetModuleFileNameA` `>= MAX_PATH` 잘림

**직관:** 버퍼가 모자라면 이 함수는 0이 아니라 **버퍼 크기(nSize)를 그대로** 돌려주고 경로를 잘라 넣는다. 성공으로 오인하기 쉬운 실패 신호다.

**동작:** `sentinelExeDirectory()`는 버퍼를 0으로 초기화하고, 반환값이 0이거나 `>= MAX_PATH`면 실패로 처리한다(최종 리뷰 3e). 예전 코드는 `GetModuleHandleExA`의 nullptr만 보고 `GetModuleFileNameA`의 반환값을 보지 않아, 긴 경로에서 잘린 문자열로 감시자를 찾으려 했다. 실패하면 감시자를 띄우지 않고 저널 폴백으로 간다.

**예시:**
```cpp
const DWORD n = ::GetModuleFileNameA(thisModule, modulePath, MAX_PATH);
if (n == 0 || n >= MAX_PATH) return {};   // 잘림도 실패로 본다
```

**관련 코드:**
- `src/maro_plugin/MaroSentinelClient.cpp:35-60` — 반환값 검사와 이력 주석

**증거:**
- §6.7, §6.7.3

**함정:** 경로가 짧은 개발 머신에서는 영원히 재현되지 않는다. 사용자의 깊은 폴더 구조에서만 나타난다.

**교훈:** Win32 함수의 "실패"는 0만이 아니다. 문서의 반환값 표를 읽고 경계값을 검사한다.

#### DLL 검색 순서

**직관:** `LoadLibrary("x.dll")`가 x.dll을 찾는 순서. 직접 실행되는 exe는 자기 디렉터리가 1순위지만, `LoadLibrary`로 로드된 `.mll`은 그렇지 않다.

**동작:** SafeDllSearchMode 기본에서 순서는 앱(실행 파일) 디렉터리 → 시스템 디렉터리 → 16비트 시스템 → Windows 디렉터리 → 현재 디렉터리 → PATH다. 여기서 "앱 디렉터리"는 프로세스 실행 파일의 폴더이므로 `maya.exe`의 bin이다. 그래서 테스트 도우미 exe들은 자기 폴더의 DLL을 자동으로 찾지만, `maro.mll`은 PATH가 필요하다 — 같은 스테이징 폴더인데 결과가 다른 이유다.

**예시:**
```
maro_test_peer.exe (직접 실행)  → 자기 폴더의 ROS DLL 자동 검색  ✓
maro.mll (Maya가 LoadLibrary)   → Maya bin이 앱 디렉터리 → PATH 필요
```

**관련 코드:**
- `tests/CMakeLists.txt:210-234` — 도우미 DLL 복사와 PATH 주입
- `src/maro_plugin/CMakeLists.txt:110-130` — `.mll` 옆 스테이징

**증거:**
- §8.1, §3.6

**함정:** 같은 폴더에 있는데 exe는 되고 mll은 안 되는 현상이 "빌드가 잘못됐나"라는 오해를 만든다. 로딩 주체가 다를 뿐이다.

**교훈:** DLL 문제를 볼 때 "누가 로드하는가"를 먼저 묻는다. 주체가 검색 기준점을 정한다.

#### 실행 파일 디렉터리

**직관:** DLL 검색의 1순위 — 프로세스를 시작시킨 exe의 폴더. 플러그인 DLL의 폴더가 아니다.

**동작:** mayapy로 도는 테스트에서는 `mayapy.exe`의 폴더가, Maya GUI에서는 `maya.exe`의 폴더가 1순위다. 우리 스테이징 폴더는 어느 쪽도 아니므로 PATH로 넣는다. 반대로 `maro_test_peer.exe`·`maro_sentinel.exe`처럼 직접 실행되는 것들은 자기 폴더가 1순위라 옆에 DLL을 복사해 두면 그만이다 — `tests/CMakeLists.txt`의 `POST_BUILD` 복사가 그 전제다.

**예시:**
```
프로세스 = mayapy.exe → 앱 디렉터리 = Maya\bin
프로세스 = maro_test_peer.exe → 앱 디렉터리 = 테스트 산출 폴더 (ROS DLL 복사해 둠)
```

**관련 코드:**
- `tests/CMakeLists.txt:205-215` — 상대역 옆 DLL 복사
- `tests/CMakeLists.txt:217-234` — mayapy용 PATH 주입

**증거:**
- §8.1

**함정:** 테스트가 통과한다고 Maya에서도 된다는 보장이 없다. 두 로딩 경로의 검색 기준이 다르기 때문이다.

**교훈:** 실행 주체마다 배포 전략이 갈린다. exe는 "옆에 두기", 플러그인은 "PATH".

#### PATH

**직관:** DLL 검색의 마지막 후보이자, 플러그인이 의존 DLL을 찾게 하는 유일한 통제 수단. 순서가 앞선 항목이 이기므로 "무엇이 먼저인가"가 중요하다.

**동작:** 세 경로로 주입한다 — ctest가 테스트 환경에 주입, 사용자가 수동 설정, `.mod`의 `PATH +:=`(맨 뒤에 붙음). 실측으로 이 머신의 영구 PATH에 ROS 2 바이너리 배포판이 앞서 있어, `.mod`의 뒤 붙임만으로는 스테이징 사본이 로드되지 않았다 — 어느 사본이 실제로 로드됐는지는 `GetModuleFileNameW`로 확인했다.

**예시:**
```
.mod:  PATH +:= .            (맨 뒤에 추가)
영구 PATH 앞쪽: C:\dev\ros2\bin (바이너리 배포판)  → 이쪽이 이김
```

**관련 코드:**
- `tests/CMakeLists.txt:217-234` — 테스트 PATH 주입
- `python/maroTechDiag.py:542-575` — 로드된 DLL 경로 실측

**증거:**
- §8.1, §3.6

**함정:** PATH는 사용자 환경이라 우리가 완전히 통제할 수 없다. "앞에 넣었다"고 가정하지 말고 실측 진단을 남긴다.

**교훈:** 전역 환경 변수에 기대는 배포는 검증 수단을 함께 제공해야 한다. 진단이 곧 지원 비용을 줄인다.

#### wide `ofstream`

**직관:** 와이드 문자 경로로 파일을 여는 방식. Windows에서 narrow 경로는 ANSI 코드페이지로 해석되므로 한글 경로가 깨진다.

**동작:** 레거시 `UnicodeUtil.h`가 `MultiByteToWideChar(CP_UTF8)`로 UTF-8 경로를 UTF-16으로 바꾸고 `std::ofstream`의 wide 오버로드(MSVC 확장)로 연다. 이것이 한글 경로 문제의 표준 해법이었다. 현재 코드는 `std::filesystem::path`를 쓰므로 변환이 라이브러리 안에서 처리된다 — `JournalWriter`·`BookStore`가 모두 `std::filesystem::path`를 받는다.

**예시:**
```cpp
// 레거시
std::wstring wpath = toWide(utf8Path);
std::ofstream out(wpath.c_str());      // MSVC 확장: wide 경로 오버로드
// 현재
std::ofstream out(std::filesystem::path(utf8Path));
```

**관련 코드:**
- `Maro_DebugUtility/UnicodeUtil.h:8-56` — 변환과 wide 열기(레거시)
- `src/maro_diag/src/JournalWriter.cpp:95-115` — `std::filesystem::path` 사용

**증거:**
- §4.4

**함정:** `std::filesystem::path`도 `std::string`에서 만들면 플랫폼 기본 인코딩을 가정한다. UTF-8 문자열은 u8path류 팩토리나 명시적 변환이 필요할 수 있다.

**교훈:** 경로는 문자열이 아니라 경로 타입으로 다룬다. 인코딩 변환을 라이브러리에 맡길 수 있다.

#### `GetTickCount64` vs `GetTickCount`

**직관:** 부팅 후 경과 밀리초를 주는 두 함수. 32비트판은 49.7일마다 0으로 돌아가고, 64비트판은 사실상 넘치지 않는다.

**동작:** `NamedPipe.cpp`의 데드라인 계산이 `GetTickCount64`를 쓴다(브리프에서 고침) — `GetTickCount`였다면 "지금 + 타임아웃"이 랩어라운드 경계에서 과거가 되어 즉시 타임아웃하거나 영원히 안 끝난다. 주석이 "GetTickCount64는 넘치지 않는다"로 근거를 적는다. C++ 쪽은 `std::chrono::steady_clock`으로 같은 원칙을 따른다.

**예시:**
```cpp
const ULONGLONG deadlineTick = ::GetTickCount64() + timeoutMs;   // 랩어라운드 없음
while (...) { if (::GetTickCount64() >= deadlineTick) return false; }
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:200-240` — 데드라인
- `src/maro_sentinel/main.cpp:75` — `steady_clock` 별칭

**증거:**
- §5.3, §5.3.4

**함정:** 49.7일은 "우리 세션에선 안 올 일"처럼 보이지만, 워크스테이션은 몇 달씩 켜져 있다. 부팅 후 경과이므로 프로세스 수명과 무관하다.

**교훈:** 랩어라운드 있는 카운터는 넓은 타입으로 바꾸는 것이 가장 싼 해결이다.

#### `GetLastError()` 즉시 읽기

**직관:** 마지막 오류 코드는 **스레드별 값**이며 성공하는 호출도 덮어쓸 수 있다. 실패 직후 다른 호출 없이 즉시 읽어 지역 변수에 보관해야 한다.

**동작:** `job_escape_test_helper.cpp`는 `spawnWithBreakaway` 실패 직후 **바로** `GetLastError()`를 읽는다. 사이에 `CloseHandle(job)` 하나만 끼어도 last-error가 덮여 `ERROR_ACCESS_DENIED`(job 정책 거부) 판정이 무의미해진다(F-120). 이 도우미는 그 값을 종료 코드로 바꿔 부모 테스트에 알린다.

**예시:**
```cpp
const auto info = spawnWithBreakaway(exe, args);
const DWORD err = ::GetLastError();      // 즉시 — 사이에 아무 호출도 없이
::CloseHandle(job);                      // 이 호출이 last-error를 덮는다
```

**관련 코드:**
- `tests/ipc/job_escape_test_helper.cpp:15-25` — 이유 주석
- `tests/ipc/job_escape_test_helper.cpp:85-100` — 즉시 읽기와 종료 코드

**증거:**
- §8.2, §8.2.3, §10.8
- F-120

**함정:** 디버그용 로그 한 줄(`fprintf`)을 사이에 넣는 것만으로도 값이 바뀔 수 있다. 진단이 진단 대상을 망친다.

**교훈:** 전역/스레드 로컬 상태로 결과를 돌려주는 API는 "읽는 시점"이 계약의 일부다. 변수에 즉시 복사한다.

#### 스레드 로컬 last-error

**직관:** `GetLastError()`가 스레드마다 별도 값을 갖는다는 성질. 다른 스레드의 실패는 보이지 않고, 같은 스레드의 다음 호출은 덮어쓴다.

**동작:** 이 성질 때문에 (1) 실패 직후 즉시 읽고, (2) 비동기 경로에서는 완료 시점의 스레드에서 읽어야 한다. 오버랩 I/O에서 `GetOverlappedResult`가 오류를 따로 주는 이유이기도 하다. Maro는 실패 판정이 필요한 곳마다 지역 `const DWORD err = ::GetLastError();`를 둔다.

**예시:**
```
스레드 A: ReadFile 실패 → last-error = ERROR_BROKEN_PIPE
스레드 B: GetLastError() → A의 값이 아니라 B 자신의 마지막 값
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:78-92` — 즉시 읽기 패턴
- `tests/ipc/job_escape_test_helper.cpp:85-100` — 같은 패턴

**증거:**
- §8.2
- F-120

**함정:** 래퍼 함수가 내부에서 여러 API를 부르면 호출자가 보는 last-error는 마지막 것이다. 래퍼는 오류를 반환값으로 넘겨야 한다.

**교훈:** 오류 전달은 반환값이 가장 안전하다. 스레드 로컬 전역은 래퍼를 넘으면 의미를 잃는다.

#### mtime을 `rotate()` 전에 읽기

**직관:** 파일 회전에서 "가장 오래된 것부터 지운다"를 판단하려면 수정 시각을 **재작성 전에** 샘플링해야 한다. 재작성된 파일은 mtime이 "지금"으로 갱신돼 가장 최신으로 보인다.

**동작:** `rotateAll(directory, pid)`은 각 저널 파일의 `mtime`을 먼저 모은 뒤 `rotate()`를 적용한다. 순서를 뒤집으면 방금 재작성한 자기 파일이 최신이 되어, 진짜 최신 파일(실제 크래시 기록)이 대신 삭제된다. 파일당 세션 하나짜리 픽스처로는 절대 안 드러나므로, 테스트가 상한을 넘게 채워 실제로 재작성이 일어나는 상황을 만든다.

**예시:**
```cpp
// 먼저 수집
std::filesystem::file_time_type mtime = std::filesystem::last_write_time(path);
// 그 다음 rotate() — 재작성이 mtime을 갱신하므로 순서가 중요
```

**관련 코드:**
- `src/maro_diag/src/JournalWriter.cpp:333-370` — `rotateAll`과 mtime 샘플링
- `tests/diag/test_journal_reader.cpp` — 상한 초과 픽스처

**증거:**
- §8.2, §8.2.4, §10.8

**함정:** 회전 로직의 버그는 "오래된 로그가 남고 새 로그가 사라지는" 형태라 눈에 안 띈다. 조사할 때가 되어서야 없어진 것을 안다.

**교훈:** 정렬 기준이 되는 값이 작업 중에 변한다면, 작업 전에 스냅샷을 찍는다.

#### 남의 파일 재작성 금지

**직관:** 저널은 프로세스별 파일이고, 다른 프로세스가 주인인 파일은 **읽기와 통째 삭제만** 한다. 재작성(읽고 트렁케이트해 다시 쓰기)은 금지다.

**동작:** MSVC `ofstream`은 공유 모드를 허용해 같은 파일을 두 프로세스가 열 수 있다. 그래서 "읽고 자르고 다시 쓰기" 중에 주인이 새 줄을 추가하면 그 줄이 사라진다. 반면 `std::filesystem::remove()`는 주인이 열어 둔 파일에 대해 Windows에서 그냥 실패하므로 "반쯤 지워진 상태"가 생기지 않는다 — 실패가 안전한 쪽이다.

**예시:**
```
내 파일:   rotate()로 재작성 OK
남의 파일: 읽기 OK, remove() OK(실패해도 안전), 재작성 금지
```

**관련 코드:**
- `src/maro_diag/src/JournalWriter.cpp:333-370` — 소유자 구분
- `tests/diag/test_journal_reader.cpp` — 재작성 금지 검증

**증거:**
- §8.2, §8.2.4, §10.8

**함정:** "잠깐 여는 것뿐인데"가 손실을 만든다. 공유 모드가 열려 있으면 OS가 막아 주지 않는다.

**교훈:** 멀티 프로세스 파일에는 소유권 규칙을 둔다. 소유자만 쓰고, 남은 읽거나 통째로 지운다.

#### ofstream 공유 모드

**직관:** MSVC의 `std::ofstream`이 파일을 열 때 다른 프로세스의 열기를 막지 않는다는 성질. POSIX와 비슷하지만 Windows의 기본 파일 API와는 다르다.

**동작:** `CreateFile`로 직접 열면 공유 모드 인자로 공유를 통제할 수 있지만 `ofstream`은 그 제어를 노출하지 않는다. 그래서 저널 설계가 "동시 열기는 일어난다"를 전제로 세워졌다 — 프로세스별 파일, append-only, 남의 파일 재작성 금지. 이 성질을 모르고 "파일 잠금이 알아서 되겠지"라고 가정하면 조용한 데이터 손실이 난다.

**예시:**
```
프로세스 A: ofstream(journal.123.jsonl, app)  ← 열림
프로세스 B: ofstream(journal.123.jsonl, trunc) ← 막히지 않음! A의 줄이 날아감
```

**관련 코드:**
- `src/maro_diag/src/JournalWriter.cpp:95-115` — append-only 쓰기
- `src/maro_diag/src/BookStore.cpp:90-125` — 락으로 직렬화하는 스필

**증거:**
- §8.2, §8.2.4, §10.8

**함정:** 단일 프로세스 테스트에서는 절대 재현되지 않는다. 두 Maya를 동시에 띄워야 드러난다.

**교훈:** 표준 라이브러리의 파일 열기는 플랫폼 잠금 의미를 감춘다. 동시성이 있으면 그 의미를 확인한다.

#### `remove()` 실패 원자성

**직관:** Windows에서 다른 프로세스가 열어 둔 파일의 `std::filesystem::remove()`는 **그냥 실패한다** — 반쯤 지워지거나 내용이 잘리는 중간 상태가 없다.

**동작:** 이 성질 덕에 회전 로직이 단순해진다. 남의 파일을 지우려다 실패하면 그 파일은 그대로 남고, 다음 세션이 다시 시도한다. 잘못된 상태가 없으므로 실패를 무시해도 안전하다. 반대로 재작성은 중간 상태(잘린 파일)를 만들 수 있어 금지된다.

**예시:**
```cpp
std::error_code ec;
std::filesystem::remove(path, ec);   // 주인이 열어 뒀으면 실패 — 파일은 온전
```

**관련 코드:**
- `src/maro_diag/src/JournalWriter.cpp:333-370` — 통째 삭제 경로
- `tests/diag/test_journal_reader.cpp` — 삭제 실패 시 온전성

**증거:**
- §8.2, §8.2.4

**함정:** POSIX에서는 열린 파일도 unlink되어 이름만 사라진다. 플랫폼 간 동작이 달라 이식할 때 가정이 깨진다.

**교훈:** "실패가 안전한 연산"을 찾아 그것으로 설계한다. 중간 상태가 없으면 복구 코드도 없다.

#### `FILE_FLAG_FIRST_PIPE_INSTANCE`

**직관:** 같은 이름의 **첫 번째** 파이프 인스턴스가 아니면 생성을 실패시키는 플래그. 이름 선점 공격을 막는다.

**동작:** 파이프 이름이 `\\.\pipe\maro_sentinel_<pid>`로 완전히 예측 가능하므로, 아무 로컬 프로세스나 진짜 감시자보다 먼저 같은 이름을 선점할 수 있다(F-238). 이 플래그가 없으면 감시자의 `CreateNamedPipe`가 두 번째 인스턴스로 **조용히 성공**해 아무도 이상을 눈치채지 못하고, Maya는 가짜와 통신하게 된다. 최종 리뷰 I3에서 추가됐다.

**예시:**
```cpp
::CreateNamedPipeA(name, PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED | FILE_FLAG_FIRST_PIPE_INSTANCE, ...);
// 이미 누가 그 이름을 갖고 있으면 → 생성 실패(조용한 성공 방지)
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:112-140` — 플래그와 리뷰 주석

**증거:**
- §5.3, §5.3.4, §10.8
- F-238

**함정:** "로컬 IPC는 안전하다"는 가정이 이 공격을 놓치게 한다. 같은 머신의 다른 사용자·프로세스도 이름 공간을 공유한다.

**교훈:** 예측 가능한 이름을 쓰는 IPC는 선점 방어가 필요하다. 플래그 하나로 조용한 실패가 명시적 실패가 된다.

#### `SECURITY_SQOS_PRESENT|SECURITY_IDENTIFICATION`

**직관:** 클라이언트가 파이프를 열 때 "서버가 내 신원을 어디까지 쓸 수 있는가"를 제한하는 플래그. 가장 낮은 수준(식별만)으로 고정한다.

**동작:** 클라이언트가 SQOS를 지정하지 않으면 서버 쪽에 `SecurityImpersonation`이 기본으로 주어진다 — 파이프 반대편이 `ImpersonateNamedPipeClient()`로 Maya 사용자 행세를 할 수 있다는 뜻이다(F-239). `SECURITY_IDENTIFICATION`은 서버가 클라이언트의 신원을 **확인**할 수는 있지만 그 토큰으로 행동할 수는 없게 한다. 최종 리뷰 I3의 지적으로 추가됐고, "선택이 아니다"라고 주석에 적혀 있다.

**예시:**
```cpp
::CreateFileA(name, GENERIC_READ | GENERIC_WRITE, 0, nullptr, OPEN_EXISTING,
              FILE_FLAG_OVERLAPPED | SECURITY_SQOS_PRESENT | SECURITY_IDENTIFICATION, nullptr);
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:200-225` — 클라이언트 플래그와 리뷰 주석

**증거:**
- §5.3, §5.3.4, §10.8
- F-239

**함정:** 기본값이 가장 관대한 쪽(`SecurityImpersonation`)이다. 명시하지 않으면 권한을 넘겨주는 셈이다.

**교훈:** 보안 관련 기본값은 대개 편의를 위해 관대하다. 명시적으로 최소 권한을 고른다.

#### 사칭(impersonation)

**직관:** 서버가 클라이언트의 토큰을 빌려 그 사용자 권한으로 행동하는 Windows 메커니즘. 편리하지만 파이프 반대편이 악의적이면 권한 상승 경로가 된다.

**동작:** 명명된 파이프 서버는 `ImpersonateNamedPipeClient()`로 연결된 클라이언트를 사칭할 수 있다. Maya가 아무 SQOS 없이 파이프를 열면 그 권한이 서버에 주어지므로, 가짜 감시자가 Maya 사용자로서 파일을 읽고 쓸 수 있다. Maro는 클라이언트 쪽에서 `SECURITY_IDENTIFICATION`으로 상한을 낮춰 이 경로를 닫는다 — 서버 쪽 코드를 우리가 통제하더라도 **가짜 서버**가 있을 수 있기 때문이다.

**예시:**
```
클라이언트가 SQOS 미지정 → 서버가 ImpersonateNamedPipeClient() 가능 → Maya 사용자 행세
클라이언트가 IDENTIFICATION → 서버는 신원 확인만, 행동 불가
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:200-225` — 상한 지정
- `src/maro_ipc/src/NamedPipe.cpp:112-140` — 첫 인스턴스 선점 방어

**증거:**
- §5.3, §5.3.4
- F-239

**함정:** "내 서버만 붙을 텐데"라는 전제가 위험하다. 이름이 예측 가능하면 남의 서버가 먼저 붙을 수 있다.

**교훈:** 권한 위임은 클라이언트가 상한을 정한다. 서버를 신뢰할 수 없는 모델에서는 클라이언트가 방어선이다.

#### `ImpersonateNamedPipeClient`

**직관:** 파이프 서버가 클라이언트 토큰으로 스레드를 전환하는 API. SQOS 수준이 `SecurityImpersonation` 이상일 때만 성공한다.

**동작:** Maro 감시자는 이 API를 쓰지 않는다 — 사칭이 필요 없기 때문이다. 방어는 클라이언트 쪽에서 한다: `SECURITY_IDENTIFICATION`을 주면 가짜 서버가 이 호출을 해도 실패하거나 식별 수준 토큰만 얻어 파일 접근에 쓸 수 없다. 이 API의 존재가 "왜 SQOS가 선택이 아닌가"의 답이다.

**예시:**
```cpp
// 가짜 서버가 시도할 수 있는 것:
::ImpersonateNamedPipeClient(pipe);   // 클라이언트가 IDENTIFICATION이면 권한 행사 불가
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:200-225` — 클라이언트 방어

**증거:**
- §5.3, §5.3.4

**함정:** 우리 서버가 이 API를 안 쓴다고 위험이 없는 것이 아니다. 위험은 "다른 서버가 쓸 수 있다"에서 온다.

**교훈:** 위협 모델은 "우리 코드가 무엇을 하는가"가 아니라 "상대가 무엇을 할 수 있는가"로 세운다.

#### 상대 경로 + `CreateProcessA` CWD 해석

**직관:** `CreateProcessA`에 상대 경로를 주면 현재 작업 디렉터리 기준으로 해석된다. Maya의 CWD는 "마지막으로 씬을 연 폴더"라 예측할 수 없다.

**동작:** 감시자 exe 경로가 비어 있거나 상대 경로면, 사용자가 마지막으로 연 씬 폴더에 같은 이름의 exe가 있을 때 그것이 실행될 수 있다. 그래서 `sentinelExeDirectory()`가 `GetModuleHandleExA`로 자기 모듈 경로를 구해 **절대 경로**를 만들고, 경로 획득에 실패하면 감시자를 아예 띄우지 않는다(저널 폴백).

**예시:**
```
CWD = D:\projects\shot010 (마지막 씬 폴더)
CreateProcessA("maro_sentinel.exe", ...) → D:\projects\shot010\maro_sentinel.exe 실행 위험
→ 절대 경로만 사용
```

**관련 코드:**
- `src/maro_plugin/MaroSentinelClient.cpp:41-60` — 절대 경로 구성
- `src/maro_ipc/src/JobEscape.cpp:21-60` — 절대 경로로 spawn

**증거:**
- §6.7, §6.7.1

**함정:** 개발 중에는 CWD가 빌드 폴더라 우연히 맞는다. 사용자 환경에서만 엉뚱한 exe가 실행된다.

**교훈:** 프로세스를 띄울 때는 절대 경로를 쓴다. CWD는 우리가 정하지 않은 값이다.
