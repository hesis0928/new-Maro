<!-- win-com-01 Windows › COM·WMI (20개) 2026-09-24 -->

#### WMI

**직관:** Windows Management Instrumentation — 시스템 정보 조회와 관리 작업을 COM 인터페이스로 제공하는 프레임워크. Maro는 job 탈출 tier 2로 이것을 쓴다.

**동작:** WMI로 만든 프로세스는 Maya의 자식이 아니라 **WMI 서비스(WinMgmt) 밑에서** 생성되므로 Maya의 job과 무관하다. 호출 순서는 `CoInitializeEx` → `CoCreateInstance(CLSID_WbemLocator)` → `ConnectServer(L"ROOT\\CIMV2")` → `CoSetProxyBlanket(...)` → `GetObject(L"Win32_Process")` → `ExecMethod("Create")`다. tier 1(breakaway)이 실패했을 때만 여기로 오고, 이것도 실패하면 tier 3(저널 폴백)이다.

**예시:**
```
tier 1: CREATE_BREAKAWAY_FROM_JOB → 실패
tier 2: WMI Win32_Process::Create → WinMgmt 밑에서 생성(job 무관)
tier 3: 포기 — 저널이 이미 항상 돌고 있으므로
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:70-272` — `spawnViaWmi` 전체
- `src/maro_plugin/MaroSentinelClient.cpp:41-80` — 3계층 호출자

**증거:**
- §5.3, §5.3.7, §11.1, §11.4, §10.8
- F-113

**함정:** WMI는 서비스에 의존하므로 서비스가 꺼져 있거나 정책으로 막히면 실패한다. tier 3 폴백이 그래서 필요하다.

**교훈:** "부모-자식 관계를 끊는" 방법이 OS마다 하나는 있다. Windows에서는 서비스를 통한 생성이 그 수단이다.

#### `Win32_Process::Create`

**직관:** WMI가 노출하는 프로세스 생성 메서드. 명령줄·작업 디렉터리·시작 옵션 객체를 받아 새 프로세스를 만들고 PID를 돌려준다.

**동작:** `ExecMethod(L"Win32_Process", L"Create", ...)`로 부른다. 출력 파라미터는 `ReturnValue`(0=성공)와 `ProcessId`다. 중요한 실측: `ExecMethod`의 `S_OK`는 "메서드가 실행됐다"는 뜻일 뿐이라, 존재하지 않는 경로로 Create하면 `S_OK`에 `ReturnValue=9`(경로 없음), `ProcessId=VT_NULL`이 온다. 그래서 `ReturnValue == 0`을 명시적으로 검사한다.

**예시:**
```cpp
hr = services->ExecMethod(_bstr_t(L"Win32_Process"), _bstr_t(L"Create"), 0, nullptr,
                          inParams.ptr, &outParams.ptr, nullptr);
// hr == S_OK 여도 ReturnValue를 반드시 확인
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:228-258` — 호출과 결과 검사
- `src/maro_ipc/src/JobEscape.cpp:140-160` — 명령줄 BSTR 구성

**증거:**
- §5.3, §5.3.7, §11.1, §11.4

**함정:** COM의 HRESULT와 메서드의 ReturnValue는 **다른 층의 결과**다. 전자만 보면 실패를 성공으로 읽는다.

**교훈:** 원격 호출 프레임워크는 "전달 성공"과 "동작 성공"을 따로 돌려준다. 둘 다 검사한다.

#### `IWbemLocator`

**직관:** WMI의 COM 진입점 인터페이스. 네임스페이스에 연결해 `IWbemServices`를 얻는 팩토리 역할이다.

**동작:** `CoCreateInstance(CLSID_WbemLocator, nullptr, CLSCTX_INPROC_SERVER, IID_IWbemLocator, ...)`로 만든다. 프로세스 안(in-proc) 객체지만 그 뒤의 `ConnectServer`가 실제 WMI 서비스와의 프록시를 만든다. `ComPtr` 스마트 포인터로 감싸 `Release`를 자동화하되, 그 선언은 `ComUninitGuard` **뒤에** 와야 한다.

**예시:**
```cpp
hr = ::CoCreateInstance(CLSID_WbemLocator, nullptr, CLSCTX_INPROC_SERVER,
                        IID_IWbemLocator, reinterpret_cast<void**>(&locator.ptr));
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:100-108` — 생성
- `src/maro_ipc/src/JobEscape.cpp:92-99` — `ComUninitGuard` 선언 위치

**증거:**
- §5.3, §5.3.7, §11.4

**함정:** `CLSCTX_INPROC_SERVER`라고 해서 전부 프로세스 안에서 도는 것은 아니다. 이후 연결은 서비스와의 RPC다.

**교훈:** COM 객체의 "어디서 도는가"는 인터페이스마다 다르다. 보안 설정이 필요한 이유가 거기 있다.

#### `IWbemServices`

**직관:** 특정 WMI 네임스페이스(`ROOT\CIMV2`)에 연결된 세션 인터페이스. 클래스 조회와 메서드 실행이 여기서 이뤄진다.

**동작:** `locator->ConnectServer(_bstr_t(L"ROOT\\CIMV2"), nullptr, nullptr, nullptr, 0, nullptr, nullptr, &services.ptr)`로 얻는다. 얻은 직후 반드시 `CoSetProxyBlanket`으로 이 프록시의 인증·위임 수준을 설정해야 한다 — 빼먹으면 `ExecMethod`가 `E_ACCESSDENIED`로 거부된다. 그 다음 `GetObject(L"Win32_Process")`로 클래스 정의를 가져와 입력 파라미터 객체를 만든다.

**예시:**
```cpp
hr = locator->ConnectServer(_bstr_t(L"ROOT\\CIMV2"), nullptr, nullptr, nullptr, 0,
                            nullptr, nullptr, &services.ptr);
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:108-120` — 연결과 프록시 설정
- `src/maro_ipc/src/JobEscape.cpp:228-240` — `ExecMethod`

**증거:**
- §5.3, §5.3.7

**함정:** 네임스페이스 문자열의 역슬래시는 C++ 문자열에서 두 번 써야 한다(`L"ROOT\\CIMV2"`). 오타가 나면 연결이 실패한다.

**교훈:** 원격 세션 객체는 "얻은 직후 보안 설정"이 관례다. 순서를 지키지 않으면 나중 호출이 조용히 막힌다.

#### `ExecMethod`

**직관:** WMI 클래스의 메서드를 실행하는 호출. `Win32_Process::Create`가 이것을 통해 불린다.

**동작:** 입력 파라미터 객체(`SpawnInstance` + `Put`)를 만들어 넘기고 출력 객체를 받는다. 두 가지 실측 함정이 있다 — (1) `CoSetProxyBlanket`을 빼먹으면 `E_ACCESSDENIED`로 **조용히** 거부되고(F-115), (2) `S_OK`가 성공을 뜻하지 않아 `ReturnValue`를 따로 봐야 한다(F-114). 두 번째는 존재하지 않는 경로로 Create했을 때 `S_OK` + `ReturnValue=9` + `ProcessId=VT_NULL`이 오는 것으로 확인했다.

**예시:**
```cpp
hr = services->ExecMethod(_bstr_t(L"Win32_Process"), _bstr_t(L"Create"), 0, nullptr,
                          inParams.ptr, &outParams.ptr, nullptr);
if (FAILED(hr)) return std::nullopt;
// 그리고 ReturnValue == 0 과 ProcessId 타입까지 확인
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:228-258` — 호출과 이중 검사
- `src/maro_ipc/src/JobEscape.cpp:114-120` — 프록시 설정(누락 시 거부)

**증거:**
- §5.3, §5.3.7, §9.2.2, §10.8
- F-114, F-115

**함정:** "조용한 거부"가 최악이다 — 오류 메시지가 없고 프로세스만 안 뜬다. 감시자가 없는데도 Maya는 정상으로 보인다.

**교훈:** 프레임워크 호출은 "성공했다"의 정의가 여러 층이다. 층마다 검사 코드를 둔다.

#### `Win32_ProcessStartup`

**직관:** `Win32_Process::Create`에 넘기는 시작 옵션 객체. 창 표시 모드·생성 플래그 등을 담는다.

**동작:** `SpawnInstance`로 인스턴스를 만들고 `CreateFlags`(→ `dwCreationFlags`로 전달)와 `ShowWindow`를 `Put`한 뒤, `QueryInterface(IID_IUnknown)`한 포인터를 `VT_UNKNOWN` VARIANT에 담아 입력 파라미터의 `ProcessStartupInformation`으로 넣는다. 실측으로 `CreateFlags = DETACHED_PROCESS(8)`가 통하고 `CREATE_NO_WINDOW`는 ReturnValue 21로 거부된다.

**예시:**
```cpp
startup->Put(L"CreateFlags", 0, &flagsVariant, 0);    // DETACHED_PROCESS
startup->Put(L"ShowWindow", 0, &showVariant, 0);      // SW_HIDE
// 그리고 VT_UNKNOWN VARIANT로 감싸 inParams에 Put
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:162-226` — 시작 옵션 구성과 실측 주석

**증거:**
- §5.3, §5.3.7

**함정:** `CreateFlags`는 Win32 `dwCreationFlags`와 같은 비트지만 제공자가 허용하는 값 집합이 더 좁다. 같은 상수라도 통하지 않을 수 있다.

**교훈:** 래핑된 API는 원본의 부분집합만 노출하는 경우가 있다. 값별로 실측한다.

#### COM

**직관:** Component Object Model — 인터페이스 포인터와 참조 카운트로 객체를 다루는 Windows의 바이너리 표준. WMI와 dbgeng이 모두 COM이다.

**동작:** Maro에서 COM이 등장하는 곳은 둘이다 — job 탈출의 WMI 경로와 `boost::stacktrace`의 dbgeng 백엔드. 두 곳 모두 수명·스레드 규칙이 까다롭다. 스택 트레이스는 메인 스레드에서만 뜨고(워커에서 COM 아파트먼트를 건드리는 근거가 없음), WMI는 `ComUninitGuard` 선언 순서로 `CoUninitialize` 시점을 보장한다. Embree 디바이스 수명 설계도 "COM 수명에서 겪은 것과 같은 순서 문제"로 설명된다.

**예시:**
```
WMI:    CoInitializeEx → ... → 모든 ComPtr Release → CoUninitialize
dbgeng: 메인 스레드에서만 to_string() 호출
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:70-100` — COM 초기화와 가드
- `src/maro_plugin/MaroStackTrace.cpp:60-80` — 메인 스레드 제한

**증거:**
- §5.3, §5.3.7, §6.0, §6.6.2, §6.7.2, §10.1
- F-029, F-115

**함정:** COM은 "초기화한 스레드에서만" 유효하다. 다른 스레드로 포인터를 넘기면 마샬링이 필요하다.

**교훈:** COM을 쓰는 코드는 스레드와 수명을 먼저 정한다. 그 둘이 대부분의 COM 버그의 원인이다.

#### `CoInitializeEx(COINIT_MULTITHREADED)`

**직관:** 현재 스레드의 COM을 MTA(멀티스레드 아파트먼트)로 초기화하는 호출. WMI 호출 전에 반드시 필요하다.

**동작:** `JobEscape.cpp`는 `::CoInitializeEx(nullptr, COINIT_MULTITHREADED)`를 부르고 결과를 본다. 다른 서브시스템이 이미 STA로 초기화한 스레드라면 `RPC_E_CHANGED_MODE`가 오는데, 이는 "이미 초기화됨"으로 보고 그대로 진행한다. 우리가 초기화했을 때(`weInitialized`)만 `CoUninitialize`를 짝으로 부른다 — 남이 초기화한 것을 우리가 해제하면 그쪽이 망가진다.

**예시:**
```cpp
const HRESULT initResult = ::CoInitializeEx(nullptr, COINIT_MULTITHREADED);
const bool weInitialized = SUCCEEDED(initResult);   // RPC_E_CHANGED_MODE면 false, 진행은 함
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:71-99` — 초기화·가드·조건부 해제

**증거:**
- §5.3, §5.3.7

**함정:** Maya 메인 스레드는 이미 STA로 초기화돼 있을 수 있다. 우리 요청과 다른 모델이어도 실패로 처리하면 안 된다.

**교훈:** 호스트 프로세스에서 COM을 쓸 때는 "이미 초기화됐을 수 있다"를 기본 가정으로 둔다.

#### `RPC_E_CHANGED_MODE`

**직관:** `CoInitializeEx`가 "이 스레드는 이미 다른 아파트먼트 모델로 초기화됐다"고 알리는 HRESULT. 실패가 아니라 상태 보고에 가깝다.

**동작:** 이 값이 오면 COM은 이미 쓸 수 있는 상태이므로 그대로 진행하되, 우리가 초기화한 것이 아니므로 `CoUninitialize`는 부르지 않는다. `weInitialized` 플래그가 그 구분을 담고 `ComUninitGuard`가 그 값에 따라 동작한다. Maya 메인 스레드(STA)에서 WMI 경로가 불릴 수 있으므로 실제로 발생 가능한 경로다.

**예시:**
```cpp
// SUCCEEDED(initResult)가 false여도 RPC_E_CHANGED_MODE면 COM은 사용 가능
if (initResult != RPC_E_CHANGED_MODE && FAILED(initResult)) return std::nullopt;
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:71-99` — 분기와 가드

**증거:**
- §5.3, §5.3.7

**함정:** `FAILED(hr)`로 뭉뚱그리면 이 경우도 실패가 되어 WMI 경로가 통째로 막힌다. HRESULT는 값별로 본다.

**교훈:** "실패 매크로"가 모든 실패를 같게 취급한다. 의미 있는 예외 코드는 따로 분기한다.

#### `CoUninitialize`

**직관:** 스레드의 COM을 해제하는 호출. `CoInitializeEx`와 짝이며, 이 호출 이후에는 그 아파트먼트의 인터페이스 포인터가 전부 무효다.

**동작:** `ComUninitGuard` 소멸자가 `weInitialized`일 때만 부른다. 결정적으로 이 가드를 **`ComPtr`들보다 먼저 선언**해야 한다 — 지역 객체는 선언 역순으로 소멸하므로, 먼저 선언된 가드가 **마지막에** 소멸해 모든 `IWbem*`이 `Release`된 뒤에야 `CoUninitialize`가 불린다. 반대 순서면 `CoUninitialize` 이후의 `Release`가 UB다(아파트가 헐려 프록시 무효, F-029).

**예시:**
```cpp
ComUninitGuard guard{weInitialized};   // 먼저 선언 → 마지막에 소멸
ComPtr<IWbemLocator> locator;          // 나중 선언 → 먼저 소멸(Release)
ComPtr<IWbemServices> services;
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:92-108` — 가드와 ComPtr 선언 순서

**증거:**
- §5.3, §5.3.7, §10.8
- F-029

**함정:** 브리프 원안은 순서가 반대였다. 대부분의 실행에서 겉으로는 멀쩡해 보이므로 코드 리뷰로만 잡힌다.

**교훈:** C++ 지역 객체의 역순 소멸을 수명 설계에 적극적으로 쓴다. 선언 순서가 곧 정리 순서다.

#### 아파트먼트

**직관:** COM의 스레딩 모델 단위 — STA(단일 스레드)와 MTA(멀티스레드). 인터페이스 포인터는 자기 아파트먼트 안에서만 직접 쓸 수 있다.

**동작:** Maro의 WMI 경로는 MTA를 요청하고, 이미 STA면 그대로 진행한다. dbgeng 기반 스택 트레이스는 "메인 스레드에서만"이라는 정책을 둔다 — Maya 워커 스레드의 아파트먼트 상태를 우리가 알 수 없고, 거기서 COM을 건드리는 것이 안전하다는 근거가 없기 때문이다. 아파트먼트를 넘는 포인터 전달은 마샬링이 필요하지만 Maro는 그 경로를 만들지 않는다.

**예시:**
```
Maya 메인 스레드: STA일 수 있음 → RPC_E_CHANGED_MODE
Maro 워커 스레드: 모름 → 여기서는 COM을 쓰지 않는다(정책)
```

**관련 코드:**
- `src/maro_plugin/MaroStackTrace.cpp:60-80` — 메인 스레드 가드
- `src/maro_ipc/src/JobEscape.cpp:71-99` — MTA 요청과 관용

**증거:**
- §5.3, §6.7.2

**함정:** 아파트먼트 규칙을 어겨도 보통은 동작한다 — 마샬링이 필요한 상황에서만 터진다. 재현이 어렵다.

**교훈:** 모르는 스레드에서는 COM을 쓰지 않는다. "안전하다는 근거"가 없으면 쓰지 않는 것이 정책이다.

#### `ComPtr`

**직관:** COM 인터페이스 포인터를 감싸 `Release`를 자동화하는 스마트 포인터. 수동 `Release` 누락과 이중 해제를 막는다.

**동작:** `JobEscape.cpp`는 간단한 자체 `ComPtr` 구조체를 써서 `ptr` 멤버와 소멸자의 `Release`만 갖는다. 선언 순서가 중요하다 — `ComUninitGuard`보다 **뒤에** 선언해야 먼저 소멸해 `CoUninitialize` 전에 `Release`가 끝난다. 출력 파라미터에는 `&x.ptr`을 넘긴다.

**예시:**
```cpp
template <class T> struct ComPtr {
    T* ptr = nullptr;
    ~ComPtr() { if (ptr) ptr->Release(); }
};
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:92-120` — 가드·ComPtr·사용

**증거:**
- §5.3, §5.3.7
- F-029

**함정:** 출력 파라미터로 같은 `ComPtr`을 두 번 쓰면 첫 포인터가 누수된다. 매번 새 객체를 선언한다.

**교훈:** COM에서도 RAII가 답이지만, 해제 순서가 다른 전역 정리(`CoUninitialize`)와 얽힌다는 점이 다르다.

#### `CoSetProxyBlanket`

**직관:** COM 프록시의 인증·위임 수준을 설정하는 호출. WMI에서는 이것을 빼먹으면 메서드 호출이 거부되는 유명한 함정이다.

**동작:** `ConnectServer` 직후 `CoSetProxyBlanket(services.ptr, RPC_C_AUTHN_WINNT, RPC_C_AUTHZ_NONE, nullptr, RPC_C_AUTHN_LEVEL_CALL, RPC_C_IMP_LEVEL_IMPERSONATE, nullptr, EOAC_NONE)`을 부른다. `RPC_C_IMP_LEVEL_IMPERSONATE`가 있어야 WMI 서비스가 우리 신원으로 프로세스를 만들 수 있다. 빼먹으면 `ExecMethod`가 `E_ACCESSDENIED`로 조용히 거부된다(F-115).

**예시:**
```cpp
hr = ::CoSetProxyBlanket(services.ptr, RPC_C_AUTHN_WINNT, RPC_C_AUTHZ_NONE, nullptr,
                         RPC_C_AUTHN_LEVEL_CALL, RPC_C_IMP_LEVEL_IMPERSONATE, nullptr, EOAC_NONE);
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:114-120` — 호출과 이유 주석

**증거:**
- §5.3, §5.3.7, §9.2, §11.4, §10.8
- F-115

**함정:** 이 함수를 빼먹어도 `ConnectServer`까지는 성공한다. 실패가 한 단계 뒤에 나타나 원인이 멀어 보인다.

**교훈:** 프레임워크의 "필수 준비 호출"은 문서의 예제 코드에 있다. 예제를 줄이려다 필수를 빼는 일이 흔하다.

#### `VARIANT`(`VT_UNKNOWN`)

**직관:** COM의 범용 값 컨테이너. `vt` 필드가 타입을, 공용체가 값을 담는다. 인터페이스 포인터를 담을 때는 `VT_UNKNOWN`이다.

**동작:** `Win32_ProcessStartup` 인스턴스를 입력 파라미터에 넣을 때 `QueryInterface(IID_IUnknown)`한 포인터를 `VT_UNKNOWN` VARIANT에 담아 `Put`한다. 순서가 중요하다 — `vt`는 QI가 **성공한 뒤에** 세운다. 실패했는데 `vt = VT_UNKNOWN`이면 `VariantClear`가 쓰레기 포인터를 `Release`한다.

**예시:**
```cpp
VARIANT startupVariant; ::VariantInit(&startupVariant);
if (SUCCEEDED(startup->QueryInterface(IID_IUnknown, (void**)&startupVariant.punkVal))) {
    startupVariant.vt = VT_UNKNOWN;      // QI 성공 뒤에
}
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:205-226` — QI·vt 설정 순서와 주석

**증거:**
- §5.3, §5.3.7

**함정:** `VariantInit` 없이 스택 VARIANT를 쓰면 쓰레기 `vt`가 들어 있어 `VariantClear`가 아무 값이나 해제하려 든다.

**교훈:** 태그 유니온은 "태그를 언제 세우는가"가 안전성을 정한다. 값이 유효해진 뒤에 태그를 세운다.

#### BSTR

**직관:** COM의 문자열 타입 — 길이 접두가 붙은 와이드 문자열이며 `SysAllocString`과 그 짝인 해제 함수로 관리한다.

**동작:** 명령줄을 UTF-8에서 UTF-16으로 바꾼 뒤 `::SysAllocString(wideCommandLine.c_str())`로 BSTR을 만들어 VARIANT에 담는다. 변환은 `MultiByteToWideChar(CP_UTF8, ..., -1, ...)`을 쓰는데, `cchSrc=-1`이면 반환 길이가 **널 종결자를 포함**한다는 점이 함정이다. `_bstr_t` 래퍼는 클래스 이름·메서드 이름 같은 리터럴에 쓴다.

**예시:**
```cpp
commandLineVariant.vt = VT_BSTR;
commandLineVariant.bstrVal = ::SysAllocString(wideCommandLine.c_str());
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:140-160` — 변환과 BSTR 생성
- `src/maro_ipc/src/JobEscape.cpp:228-232` — `_bstr_t` 리터럴

**증거:**
- §5.3, §5.3.7

**함정:** BSTR을 일반 `wchar_t*`처럼 `delete`하면 힙이 깨진다. 반드시 BSTR 전용 해제 함수(또는 `VariantClear`)로 해제한다.

**교훈:** 문자열 타입마다 할당자가 다르다. 경계를 넘는 문자열은 그 타입의 규칙을 따른다.

#### `ReturnValue` 21(Invalid Parameter)

**직관:** `Win32_Process::Create`가 인자를 거부했을 때 주는 결과 코드. `CREATE_NO_WINDOW`를 `CreateFlags`로 넘기면 이 값이 온다(3/3 재현).

**동작:** WMI 제공자는 문서의 ValueMap에 있는 값만 허용하는데 `CREATE_NO_WINDOW`(0x08000000)는 그 목록에 없다. 그래서 tier 2는 `DETACHED_PROCESS`(8)와 `ShowWindow=SW_HIDE`를 쓴다 — 관측 결과가 tier 1의 `CREATE_NO_WINDOW`와 동일하다(자식의 `GetConsoleWindow()`가 NULL). 이 실측이 코드 주석에 근거로 남아 있다.

**예시:**
```
CreateFlags = 0x08000000 (CREATE_NO_WINDOW) → ReturnValue 21 (3/3)
CreateFlags = 8 (DETACHED_PROCESS)          → ReturnValue 0, 콘솔 없음
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:170-190` — 실측 근거 주석과 선택

**증거:**
- §5.3, §5.3.7, §11.4, §10.8
- F-113

**함정:** 문서에 "생성 플래그"라고만 적혀 있으면 Win32의 모든 플래그가 통할 것 같지만 아니다. 제공자의 ValueMap이 상한이다.

**교훈:** 래퍼 API의 허용값은 문서의 표에 있다. 표에 없으면 통하지 않는다고 보고 실측한다.

#### 9(Path not found)

**직관:** `Win32_Process::Create`가 실행 파일 경로를 찾지 못했을 때의 결과 코드. `ExecMethod`는 여전히 `S_OK`다.

**동작:** 존재하지 않는 경로로 Create하면 `S_OK` + `ReturnValue=9` + `ProcessId=VT_NULL`이 온다(실측). 이 조합이 "COM 성공 ≠ 동작 성공"의 구체적 증거이고, `ReturnValue == 0` 검사를 넣은 이유다. 절대 경로를 쓰는 규칙(`sentinelExeDirectory()`)과 합쳐져 이 오류를 애초에 줄인다.

**예시:**
```
ExecMethod → S_OK
outParams["ReturnValue"] = 9        ← 경로 없음
outParams["ProcessId"]  = VT_NULL   ← PID 없음
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:234-258` — 결과 검사
- `src/maro_plugin/MaroSentinelClient.cpp:41-60` — 절대 경로 구성

**증거:**
- §5.3, §5.3.7

**함정:** 결과 코드가 숫자라 로그에 찍혀도 의미를 모르면 지나친다. 코드→의미 매핑을 주석에 적는다.

**교훈:** 원격 API의 오류 코드는 문서의 표를 코드 옆에 요약해 둔다. 조사 시간이 줄어든다.

#### `VT_NULL`

**직관:** VARIANT의 "값 없음" 타입 태그. WMI 메서드가 실패하면 출력 파라미터가 이 타입으로 온다.

**동작:** Create 실패 시 `ProcessId`가 `VT_NULL`이다. 코드는 `ReturnValue == 0`을 먼저 검사하고, 그 다음 `ProcessId`의 `vt`가 정수 타입인지 확인한다. 실측 주석은 "이 제공자에서는 타입 검사만으로도 우연히 nullopt가 나오지만, 그것은 문서가 보장하는 바가 아니므로 `ReturnValue`를 본다"고 적는다 — 우연한 안전에 기대지 않겠다는 선언이다.

**예시:**
```cpp
// ReturnValue 검사를 통과한 뒤에야 ProcessId를 읽는다
if (processIdVariant.vt != VT_I4 && processIdVariant.vt != VT_UI4) return std::nullopt;
```

**관련 코드:**
- `src/maro_ipc/src/JobEscape.cpp:234-262` — 이중 검사와 주석

**증거:**
- §5.3, §5.3.7

**함정:** 타입 검사만으로 걸러지는 것은 "지금 이 제공자에서"다. 다른 Windows 버전에서 다른 타입이 올 수 있다.

**교훈:** 우연히 동작하는 검사를 정식 검사로 착각하지 않는다. 문서가 보장하는 필드를 본다.

#### 3계층 스폰(breakaway → WMI → 포기)

**직관:** 감시자를 띄우는 세 단계 전략. 가장 단순한 방법부터 시도하고, 각 단계의 실패가 명확할 때 다음으로 넘어간다.

**동작:** tier 1 `spawnWithBreakaway`(CreateProcess + breakaway 플래그), 실패하면 tier 2 `spawnViaWmi`(WMI로 job 무관 생성), 그것도 실패하면 tier 3 포기 — 파이프 접속도 시도하지 않는다. 포기가 안전한 이유는 저널이 이미 항상 돌고 있어 크래시 판정의 기본 수단이 살아 있기 때문이다. 또 `spawnSentinel()`은 exeDir이 비면 아예 시작하지 않는다(상대 경로 실행 위험).

**예시:**
```
tier 1 실패(job이 breakaway 불허) → tier 2 WMI → 성공: PID 반환
tier 2도 실패(WMI 서비스 정책)    → tier 3: 감시자 없이 저널만으로 운영
```

**관련 코드:**
- `src/maro_plugin/MaroSentinelClient.cpp:41-90` — 3계층 호출
- `src/maro_ipc/src/JobEscape.cpp:21-60` — tier 1
- `src/maro_ipc/src/JobEscape.cpp:70-272` — tier 2

**증거:**
- §6.7, §6.7.3, §11.1, §10.8

**함정:** 폴백이 많을수록 "어느 경로로 떴는지"가 불분명해진다. 기록 파일의 `sentinelInJob`이 그 관측을 남긴다.

**교훈:** 폴백 체인은 각 단계의 실패가 명확할 때만 쓸 만하다. 조용한 실패가 섞이면 체인 전체가 신뢰를 잃는다.

#### WMI `Invoke-CimMethod Terminate`

**직관:** PowerShell에서 WMI를 통해 프로세스를 종료하는 방법. `taskkill /F`가 듣지 않는 좀비 mayapy에 쓴다.

**동작:** `Get-CimInstance Win32_Process -Filter "Name='mayapy.exe'" | Invoke-CimMethod -MethodName Terminate`. WMI 서비스가 종료를 수행하므로 권한·핸들 상황이 `taskkill`과 다르고, 그래서 듣는 경우가 있다. 좀비 mayapy는 `maro.mll`을 붙들어 다음 빌드를 `LNK1168`로 막으므로 이 명령이 빌드 복구 절차의 일부다(F-015).

**예시:**
```powershell
taskkill /F /IM mayapy.exe
Get-CimInstance Win32_Process -Filter "Name='mayapy.exe'" | Invoke-CimMethod -MethodName Terminate
```

**관련 코드:**
- `tests/maya/test_sentinel.py:118-160` — 종료 확인 폴링(예방책)
- `src/maro_ipc/src/JobEscape.cpp:70-272` — 같은 WMI 경로(생성 쪽)

**증거:**
- §9.3

**함정:** WMI로도 안 죽는 프로세스가 있다(커널 대기 중). 그때는 재부팅이나 핸들을 쥔 프로세스를 먼저 정리해야 한다.

**교훈:** 같은 목적에 여러 경로가 있으면 실패 원인이 다르다. 한 방법이 막히면 다른 층의 방법을 쓴다.
