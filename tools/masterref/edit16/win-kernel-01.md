<!-- win-kernel-01 Windows › 커널 객체·동기화 1/2 (24개) 2026-09-24 -->

#### DLL 로더

**직관:** Windows가 `.mll`(=DLL)과 그 의존 DLL을 찾아 적재하는 메커니즘. 이 프로젝트에서 "플러그인이 안 뜬다"의 원인 대부분이 여기에 있다.

**동작:** 검색 순서는 실행 파일 자신의 디렉터리 → 시스템 디렉터리 → PATH다. 중요한 것은 `LoadLibrary`로 로드되는 플러그인의 경우 **그 DLL 자신의 디렉터리가 검색 경로에 자동 포함되지 않는다**는 점 — `LOAD_WITH_ALTERED_SEARCH_PATH` 플래그가 있을 때만 포함된다. Maya는 그 플래그를 쓰지 않으므로 `maro.mll`은 찾아도 옆에 스테이징한 ROS DLL 154개를 못 찾는다. 해법은 PATH 선행이나 `.mod`의 `PATH +:=`다.

**예시:**
```
Maya가 maro.mll 로드 → 성공
maro.mll이 rclcpp.dll 요구 → .mll 옆 폴더는 검색되지 않음 → PATH에 있어야 함
```

**관련 코드:**
- `src/maro_plugin/CMakeLists.txt:110-130` — DLL 스테이징(POST_BUILD)
- `python/maroTechDiag.py:542-575` — 실제 로드 경로 진단

**증거:**
- §0.3

**함정:** 오류 메시지는 "플러그인을 로드할 수 없습니다"뿐이고 어느 DLL이 없는지 말해 주지 않는다. `dumpbin /dependents`나 진단 패널로 직접 찾아야 한다.

**교훈:** 플러그인 배포는 "내 DLL"이 아니라 "내 DLL의 의존성 전부 + 로더가 그것을 찾는 경로"까지가 범위다.

#### 잡 오브젝트 탈출

**직관:** Maya가 속한 job object의 "부모가 죽으면 자식도 죽인다" 정책에서 감시자 프로세스를 빼내는 것. 감시자는 Maya가 크래시한 **뒤에도** 살아남아 기록을 남겨야 하므로 필수다.

**동작:** 감시자를 띄울 때 `CREATE_BREAKAWAY_FROM_JOB | CREATE_NO_WINDOW` 플래그로 `CreateProcess`를 부른다(tier 1). job이 breakaway를 불허하면 실패하므로 tier 2로 WMI `Win32_Process.Create`를 쓴다 — WMI 서비스가 자식을 만들어 주므로 우리 job을 상속하지 않는다. 기록 파일에는 감시자가 결국 job 안에 있는지(`sentinelInJob`)를 남겨 self-check가 디스크까지 배선됐음을 고정한다.

**예시:**
```cpp
::CreateProcessA(..., CREATE_BREAKAWAY_FROM_JOB | CREATE_NO_WINDOW, ...);   // tier 1
// 실패하면 tier 2: WMI Win32_Process.Create
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:40-60` — tier 1 breakaway
- `tests/ipc/sentinel_in_job_helper.cpp:14-35` — job 안 시나리오 도우미
- `tests/ipc/test_job_escape.cpp` — 두 tier 검증

**증거:**
- §1.4, §10.8

**함정:** 초기 구상은 반대로 job object로 자식 메모리를 제한하려 했다. 실제로는 job이 "함께 죽이는 위험"이 되어 탈출 대상이 됐다.

**교훈:** OS 메커니즘은 목적에 따라 자산이 되기도 장애물이 되기도 한다. 수명 요구사항(누가 누구보다 오래 살아야 하는가)을 먼저 적는다.

#### `ERROR_PROC_NOT_FOUND`(127)

**직관:** "지정된 프로시저를 찾을 수 없음" — DLL 파일은 찾았지만 그 안에 기대한 export 심볼이 없을 때 나는 오류. 이름이 같은 다른 버전의 DLL이 먼저 로드됐다는 신호다.

**동작:** TBB 기능이 켜진 Embree는 `tbb12.dll`을 임포트하는데 Maya가 이미 자기 `tbb12.dll`을 프로세스에 갖고 있다. Windows 로더는 이름이 같으면 이미 로드된 것을 재사용하므로 Embree가 기대하는 심볼이 없어 127로 실패한다. 증상은 원인을 전혀 알려주지 않는 `loadPlugin` 실패뿐이다(F-003). 해법은 TBB 없는(INTERNAL tasking) Embree 빌드이고, configure 단계가 `dumpbin /dependents`로 임포트 테이블을 확인해 가드한다.

**예시:**
```powershell
dumpbin /dependents embree4.dll | findstr tbb     # 출력이 있으면 잘못된 빌드
```

**관련 코드:**
- `src/maro_lidar/CMakeLists.txt` — dumpbin 가드
- `python/maroTechDiag.py:542-575` — 로드된 DLL 실측

**증거:**
- §3.3, §11.4, §10.11
- F-003

**함정:** 같은 이름의 DLL이 둘 있으면 "누가 먼저 로드했는가"가 결과를 정한다. 호스트 프로세스(Maya)가 항상 먼저다.

**교훈:** 호스트에 얹히는 플러그인은 "호스트가 이미 가진 라이브러리"와 이름이 겹치지 않게 빌드한다. 겹치면 우리가 진다.

#### `NOMINMAX`

**직관:** `<windows.h>`가 정의하는 `min`/`max` 매크로를 끄는 전처리 정의. 이 매크로가 있으면 `std::min`/`std::max`와 `std::numeric_limits<T>::max()`가 깨진다.

**동작:** `maro_ipc`는 `target_compile_definitions(maro_ipc PUBLIC NOMINMAX WIN32_LEAN_AND_MEAN)`로 이 정의를 PUBLIC으로 전파한다 — 이 헤더들을 포함하는 모든 TU(플러그인 포함)에 적용된다. 플러그인 쪽도 `NOMINMAX`를 정의하는데, windows.h의 min/max가 rclcpp의 `numeric_limits` 사용과 충돌하기 때문이다. 레거시 `image_bridge_node.cpp`는 파일 맨 위에 `#define NOMINMAX`를 직접 적었다.

**예시:**
```cmake
target_compile_definitions(maro_ipc PUBLIC NOMINMAX WIN32_LEAN_AND_MEAN)
```

**관련 코드:**
- `src/maro_ipc/CMakeLists.txt:30` — PUBLIC 정의
- `src/maro_plugin/CMakeLists.txt:100-108` — 플러그인 쪽 정의

**증거:**
- §4.3, §4.3.1, §5.3, §5.3.1, §6.0

**함정:** 오류 메시지가 `min`/`max` 매크로 확장 결과라 무엇이 문제인지 읽기 어렵다. "`std::numeric_limits<...>::max`에 인자가 너무 많다" 같은 메시지가 전형적이다.

**교훈:** 플랫폼 헤더의 매크로 오염은 빌드 설정으로 한 번 끄고, 그 정의를 의존 타깃에 전파한다.

#### `_HAS_STD_BYTE 0`

**직관:** MSVC 표준 라이브러리에서 `std::byte`를 끄는 매크로. Windows SDK의 `byte` typedef와 `std::byte`가 `using namespace std` 환경에서 충돌하는 것을 피하는 요령이다.

**동작:** 레거시 `image_bridge_node.cpp` 맨 위(`:1-3`)에 `#define NOMINMAX`, `#define _HAS_STD_BYTE 0`이 "매크로 충돌 방지 (무조건 최상단)"라는 주석과 함께 있다. Windows SDK의 rpcndr 헤더가 `typedef unsigned char byte;`를 전역에 두므로, `using namespace std;`가 있으면 `byte`가 모호해진다. 현재 빌드 대상 코드는 `using namespace std`를 쓰지 않아 이 정의가 필요 없다.

**예시:**
```cpp
#define NOMINMAX
#define _HAS_STD_BYTE 0     // Windows SDK의 byte typedef와 std::byte 충돌 회피
#include <windows.h>
```

**관련 코드:**
- `src/image_bridge/src/image_bridge_node.cpp:1-4` — 최상단 정의(레거시)

**증거:**
- §4.3, §4.3.1

**함정:** 이 매크로는 표준 타입을 끄는 것이라 다른 헤더가 `std::byte`를 쓰면 깨진다. 근본 해법은 `using namespace std`를 없애는 것이다.

**교훈:** 이름 충돌의 해법에는 "충돌하는 쪽을 끄기"와 "이름을 안 퍼뜨리기"가 있다. 후자가 영향 범위가 작다.

#### Winsock `WSAStartup`

**직관:** Windows에서 소켓 API를 쓰기 전에 반드시 불러야 하는 초기화 함수. 버전(2.2)을 요청하고 `WSADATA`를 받는다.

**동작:** 레거시 `image_bridge_node.cpp`와 `control_bridge_node.cpp`가 `WSAStartup(MAKEWORD(2, 2), &wsaData)`로 시작한다. 실패하면 즉시 종료한다. 그 뒤 `socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)`으로 TCP 소켓을 만들고 수신기가 켜질 때까지 1초 간격으로 `connect`를 재시도한다(오토 리커넥션의 초기 형태). 현재 Maro는 소켓 대신 명명된 파이프를 쓴다.

**예시:**
```cpp
WSADATA wsaData;
if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) return 1;
SOCKET sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
```

**관련 코드:**
- `src/image_bridge/src/image_bridge_node.cpp:29-35` — 초기화(레거시)
- `src/control_bridge/src/control_bridge_node.cpp:34-40` — 같은 패턴(레거시)

**증거:**
- §4.3, §4.3.6

**함정:** `WSAStartup` 없이 소켓 함수를 부르면 WSANOTINITIALISED로 실패한다. 라이브러리 안에서 소켓을 쓰면 초기화 책임을 누가 지는지 정해야 한다.

**교훈:** 플랫폼 서브시스템에 초기화 함수가 있으면 "프로세스에 한 번"의 주체를 명시한다.

#### `SOCK_STREAM`

**직관:** 소켓 타입 상수 — 연결 지향 바이트 스트림(TCP). 메시지 경계가 없어 길이 헤더를 직접 붙여야 한다.

**동작:** 레거시 뷰포트 스트리머는 `SOCK_STREAM` 소켓으로 헤더 `int[2]{width, height}`를 먼저 보내고 픽셀을 청크로 나눠 `send`했다. 스트림이라 한 번의 `send`가 부분 전송될 수 있어 루프가 필요하다. 현재 Maro의 명명된 파이프는 **메시지 모드**라 경계가 커널 수준에서 보존되며, 이것이 IPC를 훨씬 단순하게 만든 이유다.

**예시:**
```
TCP(SOCK_STREAM): [len][payload]를 직접 정의해야 함, send 부분 전송 루프 필요
메시지 모드 파이프: 한 번의 WriteFile = 한 메시지, 경계 보존
```

**관련 코드:**
- `src/image_bridge/src/image_bridge_node.cpp:32-60` — TCP 청크 전송(레거시)
- `src/maro_ipc/src/NamedPipe.cpp:120-140` — 메시지 모드 파이프

**증거:**
- §4.3, §4.3.6

**함정:** 스트림 위에서 JSON을 줄 단위로 보내면 개행이 페이로드에 들어갈 때 경계가 깨진다. 길이 프리픽스가 안전하다.

**교훈:** 전송 계층이 메시지 경계를 주는지 확인하고, 안 주면 프레이밍을 직접 설계한다.

#### `recvfrom`

**직관:** UDP 소켓에서 데이터그램 하나를 받는 함수 — 송신자 주소도 함께 준다. 레거시 control bridge가 관절 명령을 받던 경로다.

**동작:** `recvfrom(sock, buf, len, 0, (sockaddr*)&from, &fromLen)`은 데이터그램 단위로 읽으며 버퍼가 작으면 나머지를 버린다. UDP라 순서·도착이 보장되지 않아 제어 명령에는 재전송·시퀀스 번호가 필요했다. 현재 Maro는 수신을 DDS(rclcpp 구독)에 맡기고 감시자 IPC만 파이프로 한다.

**예시:**
```cpp
sockaddr_in from; int fromLen = sizeof(from);
int n = recvfrom(sock, buffer, sizeof(buffer), 0, (sockaddr*)&from, &fromLen);
```

**관련 코드:**
- `src/control_bridge/src/control_bridge_node.cpp:34-70` — UDP 수신(레거시)

**증거:**
- §4.3

**함정:** UDP는 데이터그램이 통째로 사라져도 오류가 없다. "가끔 명령이 안 먹는다"의 원인이 되며, 신뢰성이 필요하면 상위에서 만들어야 한다.

**교훈:** 프로토콜 선택은 "무엇을 잃어도 되는가"로 한다. 제어 명령은 잃으면 안 되므로 UDP 직결은 부적절했다.

#### `#pragma comment(lib, "ws2_32.lib")`

**직관:** MSVC 전용 링크 지시자 — 소스 파일 안에서 "이 라이브러리를 링크하라"고 컴파일러에 알린다. CMake 없이 빌드하던 시절의 흔적이다.

**동작:** 레거시 bridge 노드들이 소스 첫머리에 이 pragma를 둬 Winsock 임포트 라이브러리를 링크한다. 이식성이 없고(GCC/Clang는 무시) 빌드 스크립트에서 의존성이 보이지 않는다는 단점이 있다. 현재 코드는 `target_link_libraries`로 CMake에 명시한다 — `kernel32`를 PUBLIC으로 적는 것도 "MSVC는 기본으로도 링크하지만 무엇에 의존하는지 빌드 파일에 남겨 둔다"는 같은 철학이다.

**예시:**
```cpp
#pragma comment(lib, "ws2_32.lib")    // 레거시
// 현재: target_link_libraries(maro_ipc PUBLIC kernel32)
```

**관련 코드:**
- `src/image_bridge/src/image_bridge_node.cpp:4` — pragma(레거시)
- `src/maro_ipc/CMakeLists.txt:23-25` — CMake로 명시하는 현재 방식

**증거:**
- §4.3, §4.3.6, §5.3.1

**함정:** pragma로만 링크되는 라이브러리는 빌드 시스템이 모른다. 의존성 그래프·재빌드 판단·크로스 플랫폼 포팅이 전부 어긋난다.

**교훈:** 의존성은 빌드 파일에 적는다. 컴파일러 확장으로 숨기면 그 정보가 도구에서 사라진다.

#### `__fastfail`

**직관:** 복구 불가능한 상태에서 프로세스를 즉시 죽이는 Windows 내장 함수. 예외 처리나 정리를 건너뛰므로 디버거에 바로 걸린다.

**동작:** 종료 코드 `0xC0000409`(3221226505) `STATUS_STACK_BUFFER_OVERRUN`이 보통 `__fastfail`이나 보안 쿠키 실패를 뜻한다. 레거시 `output.txt`에 `[ros2run]: Process exited with failure 3221226505`가 남아 있다. 같은 코드가 배치 모드에서 `QWidget`을 만들 때 나는 abort에서도 나타난다 — 라이브러리가 치명적 상태를 감지하면 이 경로로 죽이기 때문이다.

**예시:**
```
Process exited with failure 3221226505   (= 0xC0000409, STATUS_STACK_BUFFER_OVERRUN)
```

**관련 코드:**
- `output.txt` — 레거시 실패 로그
- `tests/maya/maroQtBatch.py:57-108` — 배치 QWidget abort 재현

**증거:**
- §4.3, §4.3.8

**함정:** 코드 이름이 "스택 버퍼 오버런"이라 메모리 손상으로 오인하기 쉽지만, 실제로는 라이브러리가 의도적으로 부른 `__fastfail`인 경우가 많다.

**교훈:** 종료 코드는 원인의 분류이지 원인이 아니다. 같은 코드가 전혀 다른 이유에서 나올 수 있다.

#### 보안 쿠키

**직관:** 컴파일러가 스택 프레임에 심어 두는 난수 값(`/GS`). 함수 반환 전에 값이 바뀌었으면 스택이 덮였다는 뜻이라 `__fastfail`로 즉시 죽인다.

**동작:** 검사에 실패하면 `0xC0000409`로 프로세스가 끝난다. 예외 처리가 돌지 않으므로 소멸자·핸들러가 실행되지 않고 로그도 남지 않는다 — 그래서 저널의 "정상 종료 줄 부재"로만 크래시를 알 수 있다. 진단 파이프라인이 미니덤프·`boost::stacktrace`를 함께 두는 이유이기도 하다.

**예시:**
```
스택 쿠키 손상 → __fastfail(FAST_FAIL_STACK_COOKIE_CHECK_FAILURE) → 0xC0000409
→ atexit·소멸자 실행 없음 → 저널에 SESSION_END_CLEAN 없음 → 크래시로 판정
```

**관련 코드:**
- `src/maro_diag/src/JournalWriter.cpp:95-115` — 세션 종료 줄
- `tools/crashtriage/symbolize.py` — 덤프 심볼화

**증거:**
- §4.3, §4.3.8

**함정:** `/GS`를 끄면 이 죽음이 사라지지만 손상은 남아 더 나중에 이상하게 터진다. 끄는 것이 아니라 원인을 찾는다.

**교훈:** 안전장치가 프로세스를 죽이는 것은 기능이다. "죽지 않게" 하지 말고 "왜 걸렸나"를 본다.

#### 잡 오브젝트 메모리 제한(256MB)

**직관:** `JOB_OBJECT_LIMIT_PROCESS_MEMORY`류로 자식 프로세스의 메모리를 제한하려던 초기 구상. 실제로는 job이 "함께 죽이는 위험"으로 뒤집혀 탈출 대상이 됐다.

**동작:** PDF 청사진의 5 Pillars 중 하나가 ghost 프로세스 메모리를 256MB로 제한하는 것이었다. 검토 결과 (1) 감시자는 Maya보다 오래 살아야 하는데 같은 job에 있으면 함께 죽고, (2) 메모리 제한이 실제 문제였던 적이 없어 §5.1의 job 탈출 설계로 방향이 바뀌었다(F-265). E-Core 스레드 선호도·Electron UI와 함께 버려진 구상이다.

**예시:**
```
구상: Maya의 job에 ghost를 넣고 메모리 256MB 제한
실제: job은 "부모와 함께 죽는" 위험 → CREATE_BREAKAWAY_FROM_JOB으로 탈출
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:40-60` — 탈출로 뒤집힌 결과
- `docs/maro-master-reference.md` — §4.4 버린 것 목록

**증거:**
- §4.4
- F-265

**함정:** "리소스를 제한하자"는 아이디어는 안전해 보이지만 수명 정책을 함께 끌고 온다. job object는 둘을 분리할 수 없다.

**교훈:** OS 기능 하나가 여러 정책을 묶어 제공하면, 원하지 않는 정책까지 받게 된다. 묶음을 먼저 확인한다.

#### `MultiByteToWideChar(CP_UTF8)`

**직관:** UTF-8 바이트열을 UTF-16(wide)으로 바꾸는 Win32 API. Windows의 narrow API가 ANSI 코드페이지를 가정하므로, 한글 경로를 다루려면 wide로 올려야 한다.

**동작:** 레거시 `UnicodeUtil.h`가 이 함수로 UTF-8 경로를 UTF-16으로 바꿔 wide 오버로드 `ofstream`을 열었다 — narrow 경로는 ANSI로 해석돼 한글이 깨지기 때문이다. COM 쪽(`BSTR` 변환)에서는 `cchSrc=-1`을 주는데, 이때 반환 길이가 널 종결자를 포함한다는 점이 함정이다. 현재 코드는 경로를 `std::filesystem::path`로 다뤄 이 변환을 라이브러리에 맡긴다.

**예시:**
```cpp
int n = MultiByteToWideChar(CP_UTF8, 0, utf8, -1, nullptr, 0);   // n은 널 포함 길이
std::wstring wide(n, L'\0');
MultiByteToWideChar(CP_UTF8, 0, utf8, -1, wide.data(), n);
```

**관련 코드:**
- `Maro_DebugUtility/UnicodeUtil.h:8-56` — UTF-8→UTF-16과 wide ofstream(레거시)
- `src/maro_ipc/src/JobEscape.cpp:200-240` — WMI BSTR 변환 경로

**증거:**
- §4.4, §5.3.7

**함정:** `cchSrc=-1`로 얻은 길이에는 널이 포함되므로 `BSTR`이나 `std::wstring` 길이 계산에서 1을 빼야 할 때가 있다. 널이 두 번 들어가면 문자열이 잘린다.

**교훈:** Windows 문자열 API는 "길이에 널이 포함되는가"가 인자에 따라 달라진다. 문서의 그 문장을 코드 주석에 옮긴다.

#### Boost.Interprocess 관리자 권한

**직관:** 전역 명명 커널 객체(공유 메모리·뮤텍스)를 만들 때 권한이 필요해 일반 사용자로는 실패하던 문제. colcon 시절 빌드/실행 문제 중 하나였다.

**동작:** `memo/260526dev.txt`가 2026-05-26의 문제 A~E를 기록하는데, 그중 하나가 Boost.Interprocess의 전역 객체 생성이 관리자 권한을 요구한 것이다(F-021). 현재 Maro는 Boost.Interprocess를 쓰지 않고 Win32 명명 객체를 직접 쓰며, 이름에 `Global\` 접두사를 붙이되 권한이 필요 없는 범위에서만 쓴다.

**예시:**
```
Boost.Interprocess 전역 공유 메모리 → 권한 오류(일반 사용자)
현재: CreateMutexA(nullptr, FALSE, "Global\\maro_sentinel_mutex_<pid>")
```

**관련 코드:**
- `memo/260526dev.txt` — 당시 기록
- `src/maro_ipc/src/Naming.cpp:9-16` — 현재의 명명 규칙

**증거:**
- §4.5
- F-021

**함정:** 개발자 머신은 관리자 권한으로 도는 경우가 많아 문제가 사용자 머신에서만 드러난다.

**교훈:** 권한이 필요한 API는 "일반 사용자로 실행"을 테스트 조건에 넣는다.

#### 사전조건 검사(DEBUG 전용)

**직관:** 라이브러리가 `assert`로 두는 입력 검증. Release 빌드에서는 컴파일에서 빠지므로, 잘못된 입력이 예외 대신 곧장 크래시가 된다.

**동작:** Embree의 `kernels/common/rtcore.cpp:482-485`에 DEBUG 빌드에서만 켜지는 검사 "scenes must only contain user geometries with a single timestep"이 있다. vcpkg는 Release로 빌드하므로 이 검사가 없고, 삼각형 씬에 `rtcCollide`를 부르면 곧장 액세스 위반이 났다(F-024). 소스를 직접 열어 이 제약을 확인한 뒤 AABB user geometry + 자체 SAT로 우회했다.

**예시:**
```
DEBUG 빌드:   assert("user geometries only") → 이해 가능한 메시지
Release 빌드: 검사 없음 → rtcCollide 내부에서 AV
```

**관련 코드:**
- `src/maro_lidar/src/CollisionEngine.cpp:116-175` — 자체 SAT 우회
- `src/maro_lidar/include/maro_lidar/CollisionEngine.h` — 제약을 적은 주석

**증거:**
- §5.2, §5.2.4
- F-024

**함정:** Release에서 크래시하는 라이브러리 호출은 "라이브러리 버그"처럼 보이지만 계약 위반인 경우가 많다. 소스나 DEBUG 빌드로 확인해야 알 수 있다.

**교훈:** 서드파티 크래시를 만나면 그 함수의 사전조건을 먼저 찾는다. DEBUG 빌드의 assert가 가장 정확한 문서다.

#### `WIN32_LEAN_AND_MEAN`

**직관:** `<windows.h>`가 끌어오는 하위 헤더(소켓·OLE·MIDI 등)를 줄이는 정의. 컴파일이 빨라지고 이름 충돌도 줄어든다.

**동작:** `maro_ipc`가 `NOMINMAX`와 함께 PUBLIC으로 정의해 의존 타깃 전체에 전파한다. 다만 이 정의가 있으면 `winsock2.h`가 자동 포함되지 않으므로 소켓을 쓰는 TU는 직접 포함해야 한다. Maro의 IPC는 파이프·뮤텍스·이벤트만 쓰므로 문제가 없다.

**예시:**
```cmake
target_compile_definitions(maro_ipc PUBLIC NOMINMAX WIN32_LEAN_AND_MEAN)
```

**관련 코드:**
- `src/maro_ipc/CMakeLists.txt:30` — PUBLIC 정의

**증거:**
- §5.3, §5.3.1

**함정:** LEAN_AND_MEAN과 소켓을 섞으면 winsock과 winsock2 헤더의 이중 포함 오류가 난다. 소켓 TU는 winsock2 헤더를 windows.h보다 먼저 포함한다.

**교훈:** 헤더 슬림화는 "무엇이 빠지는가"를 알고 쓴다. 빠진 것을 쓰는 TU가 직접 포함하는 규칙을 둔다.

#### `kernel32`

**직관:** 프로세스·스레드·파일·동기화 객체 등 Win32 기본 API가 들어 있는 시스템 DLL의 임포트 라이브러리. MSVC는 기본으로 링크한다.

**동작:** `maro_ipc`는 그럼에도 `target_link_libraries(maro_ipc PUBLIC kernel32)`로 명시한다 — 이유는 "MSVC는 기본으로도 링크하지만 무엇에 의존하는지 빌드 파일에 남겨 둔다"는 것이다. 같은 파일에서 `nlohmann_json`은 PRIVATE(`Message.cpp` 내부에서만 쓰므로)로 두어 PUBLIC/PRIVATE 구분도 의존 관계를 표현한다.

**예시:**
```cmake
target_link_libraries(maro_ipc PUBLIC kernel32)          # 명시적 기록
target_link_libraries(maro_ipc PRIVATE nlohmann_json)    # 내부 구현 의존
```

**관련 코드:**
- `src/maro_ipc/CMakeLists.txt:23-28` — 링크와 이유 주석

**증거:**
- §5.3, §5.3.1

**함정:** "기본으로 링크되니 안 적어도 된다"는 다른 컴파일러·다른 빌드 시스템으로 옮길 때 무너진다. 명시가 이식성의 기록이다.

**교훈:** 빌드 파일은 빌드 명령이자 의존성 문서다. 도구가 알아서 해 주는 것도 적어 두면 사람이 읽을 수 있다.

#### `Global\` 접두사

**직관:** 커널 객체 이름 앞에 붙여 그 객체를 **전 세션 공유** 네임스페이스에 만드는 접두사. 없으면 `Local\`(세션별)이 기본이다.

**동작:** 감시자 IPC의 이름들이 `Naming.cpp` 한 곳에 모여 있다 — `pipeName(pid) = "\\\\.\\pipe\\maro_sentinel_<pid>"`, `mutexName(pid) = "Global\\maro_sentinel_mutex_<pid>"`, `killEventName(pid) = "Global\\maro_sentinel_kill_<pid>"`, `recordFilePath = bookDir/"maro_sentinel.<pid>.json"`. `Global\`을 쓰는 이유는 세션 0(서비스)과 충돌하지 않게 하기 위해서다. 이름 규칙을 한 파일에 모은 것은 저널이 겪은 "판정이 writer/reader에 따로 있다가 우연히만 맞아떨어진" 함정의 재발 방지다.

**예시:**
```cpp
std::string mutexName(std::uint64_t pid) {
    return "Global\\maro_sentinel_mutex_" + std::to_string(pid);
}
```

**관련 코드:**
- `src/maro_ipc/src/Naming.cpp:5-20` — 네 이름 전부
- `tests/ipc/test_naming.cpp` — 이름 형식 고정

**증거:**
- §5.3, §5.3.2

**함정:** `Global\` 객체 생성은 권한이 필요한 경우가 있다(세션 0 격리 정책). 뮤텍스·이벤트는 보통 괜찮지만 공유 메모리는 막힐 수 있다.

**교훈:** 프로세스 간 이름은 규칙을 한 함수에 모으고 테스트로 형식을 고정한다. 양쪽이 각자 조립하면 언젠가 어긋난다.

#### 세션 0

**직관:** Windows 서비스가 도는 격리된 세션. 사용자 로그인 세션(1 이상)과 분리돼 있어 UI를 띄울 수 없고 커널 객체 네임스페이스도 다르다.

**동작:** `Local\` 이름은 세션마다 별개이므로 서비스와 사용자 프로세스가 같은 이름을 써도 만나지 못한다. Maro 감시자는 사용자 세션에서만 돌지만, PID 기반 이름에 `Global\`을 붙여 세션 경계를 넘어도 충돌·혼동이 없게 했다. 세션 0 격리는 Vista부터의 정책이다.

**예시:**
```
Local\maro_..._1234   ← 세션 1의 객체
Local\maro_..._1234   ← 세션 0의 동명 객체 (서로 다른 객체!)
Global\maro_..._1234  ← 전 세션에서 같은 하나
```

**관련 코드:**
- `src/maro_ipc/src/Naming.cpp:9-16` — `Global\` 선택

**증거:**
- §5.3, §5.3.2

**함정:** 세션 0에서는 메시지 박스·콘솔 창이 보이지 않는다. 감시자가 거기서 돌면 오류를 사용자가 볼 수 없다.

**교훈:** 프로세스 간 통신 설계에서 "어느 세션에서 도는가"는 이름 공간과 UI 가능성을 함께 정한다.

#### `CreateMutexA(bInitialOwner=FALSE)`

**직관:** 명명 뮤텍스를 만들되 만든 쪽이 소유권을 갖지 않게 하는 호출. "얻었다"의 의미를 하나로 만들기 위한 선택이다.

**동작:** `NamedMutexGuard`는 `::CreateMutexA(nullptr, FALSE, name.c_str())`로 만들고, 그 다음 `WaitForSingleObject(handle_, timeoutMs)`가 소유권을 얻는 **유일한 경로**가 되게 한다. `bInitialOwner=TRUE`였다면 "처음 만든 프로세스는 Wait 없이 소유"와 "나중 프로세스는 Wait로 소유"라는 두 경로가 생겨 획득 판정이 두 곳에 흩어진다. 소멸자는 획득했을 때만 `ReleaseMutex`를 부른다.

**예시:**
```cpp
handle_ = ::CreateMutexA(nullptr, FALSE, name.c_str());   // 소유하지 않고 생성
const DWORD result = ::WaitForSingleObject(handle_, timeoutMs);
acquired_ = (result == WAIT_OBJECT_0 || result == WAIT_ABANDONED);
```

**관련 코드:**
- `src/maro_ipc/src/NamedMutexGuard.cpp:5-22` — 생성과 획득
- `tests/ipc/test_named_mutex_guard.cpp:9-30` — 같은 프로세스 두 스레드로 경합 검증

**증거:**
- §5.3, §5.3.6

**함정:** `bInitialOwner=TRUE`로 만들고 Wait도 부르면 재귀 소유가 되어 `ReleaseMutex`를 두 번 불러야 풀린다. 카운트 불일치가 조용한 교착을 만든다.

**교훈:** 상태 전이의 경로를 하나로 줄이면 판정 코드도 하나가 된다. 생성과 획득을 분리하는 이유다.

#### `WAIT_ABANDONED`

**직관:** 뮤텍스를 쥔 프로세스가 놓지 않고 죽었을 때 다음 대기자가 받는 반환값. 소유권은 유효하게 넘어오지만 "보호하던 상태가 일관적이지 않을 수 있다"는 경고를 겸한다.

**동작:** `NamedMutexGuard`는 이것을 **정상 획득으로 친다**(`acquired_ = (result == WAIT_OBJECT_0 || result == WAIT_ABANDONED)`). 그렇지 않으면 "죽은 프로세스가 남긴 잠금 때문에 다음 프로세스가 영원히 못 뜨는" 상태가 된다. 감시자 설계(C-1)는 이 성질 덕에 자가 점검을 축소할 수 있었다 — 낡은 기록 파일은 저절로 덮어써지므로 킬 이벤트는 만들되 울리는 코드를 두지 않았다.

**예시:**
```cpp
// WAIT_ABANDONED: 이전 소유자가 놓지 않고 죽었다는 뜻이다.
// 뮤텍스 소유권은 유효하게 넘어오므로 획득으로 친다.
acquired_ = (result == WAIT_OBJECT_0 || result == WAIT_ABANDONED);
```

**관련 코드:**
- `src/maro_ipc/src/NamedMutexGuard.cpp:15-22` — 판정과 주석
- `tests/ipc/test_named_mutex_guard.cpp` — 경합 케이스

**증거:**
- §5.3, §5.3.6, §9.2, §9.2.2, §10.8, §11.4
- F-271

**함정:** 일반 상호배제에서는 `WAIT_ABANDONED`를 받으면 보호하던 데이터의 무결성을 의심해야 한다. Maro는 "기록 파일을 통째로 덮어쓴다"는 설계라 안전하다.

**교훈:** 예외 반환값을 정상으로 취급하는 결정에는 "왜 안전한가"를 함께 적는다. 데이터 모델이 그 결정을 뒷받침한다.

#### `ReleaseMutex`

**직관:** 뮤텍스 소유권을 놓는 호출. 소유한 스레드만 부를 수 있고, 안 부르고 죽으면 다음 대기자가 `WAIT_ABANDONED`를 받는다.

**동작:** `NamedMutexGuard`의 소멸자가 `acquired_`일 때만 `::ReleaseMutex(handle_)`을 부르고 핸들을 닫는다. RAII라 예외·조기 return 경로에서도 반드시 실행된다. 획득하지 못했는데 부르면 실패하므로 플래그 검사가 필요하다.

**예시:**
```cpp
~NamedMutexGuard() {
    if (acquired_) ::ReleaseMutex(handle_);
    if (handle_) ::CloseHandle(handle_);
}
```

**관련 코드:**
- `src/maro_ipc/src/NamedMutexGuard.cpp:25-34` — 소멸자

**증거:**
- §5.3

**함정:** 뮤텍스는 스레드 소유다 — 얻은 스레드와 다른 스레드에서 `ReleaseMutex`를 부르면 실패한다. RAII 객체를 스레드 간에 넘기면 안 된다.

**교훈:** 커널 동기화 객체의 소유 단위(스레드/프로세스)를 알고 RAII 범위를 그에 맞춘다.

#### 킬 스위치 이벤트(`CreateEventA(bManualReset=TRUE)`)

**직관:** 이름만 알면 외부에서 감시자를 종료시킬 수 있는 신호 객체. 수동 리셋이라 한 번 Set되면 계속 신호 상태로 남아 폴링하는 쪽마다 리셋할 필요가 없다.

**동작:** 감시자는 시작할 때 `CreateEventA(nullptr, TRUE, FALSE, killEventName(pid))`로 이벤트를 만들고, 수신 루프 한 바퀴마다 `WaitForSingleObject(killEvent, 0)`으로 확인한다. PID를 찾을 필요 없이 이름만으로 즉시 종료시킬 수 있는 장치다. 다만 C-1 결정에서 "킬 이벤트는 만들되 울리는 코드는 없음"으로 정리됐다 — `WAIT_ABANDONED` 처리 덕에 낡은 기록이 저절로 덮어써지기 때문이다.

**예시:**
```cpp
ScopedHandle killEvent(::CreateEventA(nullptr, TRUE, FALSE, killEventName(pid).c_str()));
// 루프마다: if (::WaitForSingleObject(killEvent.get(), 0) == WAIT_OBJECT_0) break;
```

**관련 코드:**
- `src/maro_sentinel/main.cpp:147-160` — 이벤트 생성
- `src/maro_ipc/src/Naming.cpp:13-16` — 이름 규칙

**증거:**
- §5.4, §9.2.2

**함정:** 자동 리셋(`bManualReset=FALSE`) 이벤트는 대기 하나만 깨우고 리셋된다. 여러 곳이 폴링하는 종료 신호에는 수동 리셋이 맞다.

**교훈:** 이벤트의 리셋 모드는 "몇 명이 듣는가"로 정한다. 브로드캐스트 신호는 수동 리셋이다.

#### `WaitForSingleObject(h, 0)`

**직관:** 타임아웃 0으로 부르는 대기 — 블록하지 않고 객체의 현재 시그널 상태만 확인한다. 폴링 루프의 기본 도구다.

**동작:** 두 용도로 쓰인다. (1) 감시자 수신 루프가 킬 이벤트를 확인할 때, (2) 프로세스 리브니스 판정 — 프로세스 오브젝트는 **종료 시 시그널 상태**가 되므로 `WAIT_TIMEOUT`이면 살아 있고 `WAIT_OBJECT_0`이면 죽었다. `OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION)`로 최소 권한 핸들을 열어 쓴다. `OpenProcess`가 성공했다고 살아 있는 것이 아니다 — 누군가 핸들을 들고 있으면 종료된 프로세스의 오브젝트도 열린다(F-122).

**예시:**
```cpp
HANDLE h = ::OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
const bool alive = (h && ::WaitForSingleObject(h, 0) == WAIT_TIMEOUT);
```

**관련 코드:**
- `src/maro_plugin/MaroDiag.cpp:190-215` — `ScopedProcessHandle`과 리브니스
- `src/maro_sentinel/main.cpp:147-175` — 킬 이벤트 폴링
- `src/maro_ipc/src/NamedPipe.cpp:27` — 오버랩 I/O 완료 대기

**증거:**
- §5.4, §6.7, §6.7.1, §11.4, §10.8
- F-122

**함정:** "핸들이 열렸다 = 프로세스가 산다"가 가장 흔한 오해다. 커널 오브젝트의 수명과 프로세스의 수명은 다르다.

**교훈:** 리브니스는 핸들 획득이 아니라 시그널 상태로 판정한다. 그 차이가 PID 재사용 버그를 막는다.
