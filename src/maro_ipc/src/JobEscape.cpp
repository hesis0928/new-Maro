#include "maro_ipc/JobEscape.h"

#include <comdef.h>
#include <wbemidl.h>

#pragma comment(lib, "wbemuuid.lib")

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
        // CREATE_NO_WINDOW가 없으면 사용자 화면에 콘솔 창이 뜬다. 감시자
        // (maro_sentinel.exe)는 콘솔 서브시스템 실행 파일이고 이것을 띄우는
        // Maya.exe는 GUI 서브시스템이라 콘솔이 없다 -- 콘솔 없는 부모가 콘솔
        // 프로그램을 자식으로 만들면 Windows가 *새 콘솔을 할당하고 그 창을
        // 보여 준다*. 그 창은 감시자가 사는 내내(최대 12시간,
        // kMaxSessionLifetimeMs) 화면에 남는다.
        //
        // 이 함수를 mayapy나 gtest에서 호출하면 이 문제가 보이지 않는다:
        // 둘 다 콘솔 프로그램이라 자식이 부모 콘솔을 물려받아 새 창이 아예
        // 안 뜨기 때문이다. 그래서 tests/ipc/test_console_window.cpp는
        // DETACHED_PROCESS로 콘솔 없는 부모를 일부러 만들어 진짜 Maya 조건을
        // 재현한다(실측: 이 플래그를 빼면 자식이 visible=1인 콘솔 창을 얻는다).
        CREATE_BREAKAWAY_FROM_JOB | CREATE_NO_WINDOW,
        nullptr, nullptr, &startupInfo, &processInfo);

    if (!created) return std::nullopt;
    return processInfo;
}

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
    if (FAILED(initResult) && initResult != RPC_E_CHANGED_MODE) {
        return std::nullopt;
    }
    const bool weInitialized = SUCCEEDED(initResult);

    // CoUninitialize를 RAII로 건다. 이 가드를 아래 ComPtr들보다 *먼저*
    // 선언하는 것이 핵심이다: 지역 객체는 선언의 역순으로 소멸하므로 이
    // 가드가 가장 마지막에 소멸한다 -- 즉 모든 IWbem* 인터페이스가
    // Release된 *뒤에야* CoUninitialize가 불린다. COM 인터페이스를
    // CoUninitialize 이후에 Release하는 것은 정의되지 않은 동작이다(아파트가
    // 이미 헐려 프록시가 무효화된 상태이므로). 브리프 원안은 각 return 직전에
    // cleanupCom()을 명시적으로 불렀는데, 그러면 CoUninitialize가 ComPtr
    // 소멸자(=Release)보다 *먼저* 실행되어 이 UB에 정확히 걸린다 -- 그래서
    // RAII 가드로 순서를 강제한다. weInitialized가 false면(RPC_E_CHANGED_MODE로
    // 이미 다른 동시성 모델로 초기화돼 있었던 경우) 우리가 초기화한 것이
    // 아니므로 CoUninitialize도 부르지 않는다(활성 조건).
    struct ComUninitGuard {
        bool active;
        ~ComUninitGuard() {
            if (active) ::CoUninitialize();
        }
    } comUninitGuard{weInitialized};

    ComPtr<IWbemLocator> locator;
    HRESULT hr = ::CoCreateInstance(CLSID_WbemLocator, nullptr, CLSCTX_INPROC_SERVER,
                                    IID_IWbemLocator,
                                    reinterpret_cast<LPVOID*>(locator.addressOf()));
    if (FAILED(hr)) {
        return std::nullopt;
    }

    ComPtr<IWbemServices> services;
    hr = locator->ConnectServer(_bstr_t(L"ROOT\\CIMV2"), nullptr, nullptr, nullptr, 0,
                                nullptr, nullptr, services.addressOf());
    if (FAILED(hr)) {
        return std::nullopt;
    }

    // 호출 권한을 명시적으로 설정한다 -- 이걸 빼먹으면 ExecMethod가
    // E_ACCESSDENIED로 조용히 거부되는 경우가 흔하다(잘 알려진 WMI 함정).
    hr = ::CoSetProxyBlanket(services.ptr, RPC_C_AUTHN_WINNT, RPC_C_AUTHZ_NONE, nullptr,
                             RPC_C_AUTHN_LEVEL_CALL, RPC_C_IMP_LEVEL_IMPERSONATE, nullptr,
                             EOAC_NONE);
    if (FAILED(hr)) {
        return std::nullopt;
    }

    ComPtr<IWbemClassObject> processClass;
    hr = services->GetObject(_bstr_t(L"Win32_Process"), 0, nullptr,
                             processClass.addressOf(), nullptr);
    if (FAILED(hr)) {
        return std::nullopt;
    }

    ComPtr<IWbemClassObject> inParamsDefinition;
    hr = processClass->GetMethod(L"Create", 0, inParamsDefinition.addressOf(), nullptr);
    if (FAILED(hr)) {
        return std::nullopt;
    }

    ComPtr<IWbemClassObject> inParams;
    hr = inParamsDefinition->SpawnInstance(0, inParams.addressOf());
    if (FAILED(hr)) {
        return std::nullopt;
    }

    std::string commandLine = "\"" + exePath + "\"";
    if (!args.empty()) commandLine += " " + args;

    // std::string(UTF-8/ANSI)를 WMI가 요구하는 BSTR(UTF-16)로 바꾼다.
    // cchSrc=-1이므로 반환값 wideLen은 널 종결자를 포함한 길이다.
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
        return std::nullopt;
    }

    // 콘솔 창 억제 -- tier 1(spawnWithBreakaway)의 CREATE_NO_WINDOW에 대응하는
    // WMI 쪽 장치다. 이 경로로 만든 프로세스도 콘솔 창을 얻는다는 것을 실측으로
    // 확인했다(tests/ipc/test_console_window.cpp, 수정 전 결과 console!=0,
    // visible=1) -- tier 1과 별개의 코드 경로지만 구멍은 똑같았다.
    //
    // Win32_Process::Create는 선택 인자 ProcessStartupInformation으로
    // Win32_ProcessStartup 인스턴스를 받고, 그 CreateFlags가 CreateProcess의
    // dwCreationFlags로 전달된다.
    //
    // 왜 CREATE_NO_WINDOW가 아니라 DETACHED_PROCESS인가 (실측 근거):
    //   - CreateFlags = CREATE_NO_WINDOW(0x08000000) 단독 -> Create가
    //     ReturnValue 21(Invalid Parameter)로 *거부*된다(3/3 재현). 이 값은
    //     Win32_ProcessStartup 문서의 CreateFlags 값 목록에 없다 -- 제공자가
    //     자기 ValueMap으로 검증한다. 그대로 넣었으면 tier 2 폴백 자체가
    //     통째로 망가졌을 것이다.
    //   - CreateFlags = DETACHED_PROCESS(8) -> ReturnValue 0, 그리고 자식의
    //     GetConsoleWindow()가 NULL(console=0). 문서에 있는 값이고, 결과는
    //     tier 1의 CREATE_NO_WINDOW와 관측상 동일하다.
    //   - ShowWindow = SW_HIDE 단독 -> 콘솔은 그대로 생기고(console!=0) 창만
    //     숨겨진다(visible=0). 그래서 이것만으로는 부족하다고 보고, 아래처럼
    //     둘 다 건다: 어떤 제공자가 CreateFlags를 무시하더라도 창은 숨는다.
    //
    // 감시자에게 콘솔이 없어도 되는 이유: src/maro_sentinel/main.cpp가
    // 콘솔에 쓰는 곳은 인자 개수가 틀렸을 때의 usage 한 줄(stderr)뿐이고,
    // 플러그인은 항상 올바른 인자로 띄운다.
    //
    // 실패해도 spawn 자체는 계속 진행한다(best-effort). 창이 보이는 감시자는
    // 나쁘지만, 감시자가 아예 없는 것보다는 낫다.
    ComPtr<IWbemClassObject> startupClass;
    ComPtr<IWbemClassObject> startupInstance;
    if (SUCCEEDED(services->GetObject(_bstr_t(L"Win32_ProcessStartup"), 0, nullptr,
                                      startupClass.addressOf(), nullptr)) &&
        SUCCEEDED(startupClass->SpawnInstance(0, startupInstance.addressOf()))) {
        // CIM uint32/uint16은 둘 다 VARIANT VT_I4로 넘긴다.
        VARIANT createFlagsVariant;
        ::VariantInit(&createFlagsVariant);
        createFlagsVariant.vt = VT_I4;
        createFlagsVariant.lVal = static_cast<LONG>(DETACHED_PROCESS);
        startupInstance->Put(L"CreateFlags", 0, &createFlagsVariant, 0);
        ::VariantClear(&createFlagsVariant);

        VARIANT showWindowVariant;
        ::VariantInit(&showWindowVariant);
        showWindowVariant.vt = VT_I4;
        showWindowVariant.lVal = SW_HIDE;
        startupInstance->Put(L"ShowWindow", 0, &showWindowVariant, 0);
        ::VariantClear(&showWindowVariant);

        // 내장 객체(embedded object) 인자를 넘기는 WMI 규약: IID_IUnknown으로
        // QueryInterface한 포인터를 VT_UNKNOWN VARIANT에 담아 Put한다. Put은
        // 객체를 *복사*하므로 이 뒤에 startupInstance를 더 고쳐도 소용없다.
        // QueryInterface가 올린 참조는 아래 VariantClear가 되돌린다 --
        // startupInstance 자신의 참조는 ComPtr이 스코프 끝에서 따로 놓아준다.
        VARIANT startupVariant;
        ::VariantInit(&startupVariant);
        if (SUCCEEDED(startupInstance->QueryInterface(
                IID_IUnknown, reinterpret_cast<void**>(&startupVariant.punkVal)))) {
            // vt는 QI가 성공한 뒤에 세운다. 실패했는데 VT_UNKNOWN으로
            // 표시해 두면 VariantClear가 쓰레기 포인터를 Release한다.
            startupVariant.vt = VT_UNKNOWN;
            inParams->Put(L"ProcessStartupInformation", 0, &startupVariant, 0);
        }
        ::VariantClear(&startupVariant);
    }

    ComPtr<IWbemClassObject> outParams;
    hr = services->ExecMethod(_bstr_t(L"Win32_Process"), _bstr_t(L"Create"), 0, nullptr,
                              inParams.ptr, outParams.addressOf(), nullptr);
    if (FAILED(hr)) {
        return std::nullopt;
    }

    // ExecMethod 자체의 성공은 "메서드가 실행됐다"는 뜻일 뿐이다.
    // ReturnValue가 진짜 결과다 -- 0이 아니면 프로세스 생성 자체가
    // 거부된 것이고(예: 경로 없음), 여기서 놓치면 존재하지 않는 PID를
    // "성공"으로 돌려주는 조용한 오판이 된다.
    //
    // 실측(Step 6, 이 머신의 WMI 제공자): 존재하지 않는 경로로 Create하면
    // ExecMethod는 S_OK, ReturnValue는 VT_I4=9(거부), ProcessId는 VT_NULL로
    // 온다. 즉 이 제공자에서는 실패 시 ProcessId가 정수(VT_I4)가 아니어서
    // 아래 `pidVariant.vt == VT_I4` 타입 검사만으로도 우연히 nullopt가 나온다
    // -- 그래서 이 ReturnValue==0 검사를 SUCCEEDED(hr)로 무력화해도 bogus-path
    // 테스트가 눈에 띄게 깨지지는 않았다. 하지만 그것은 "실패 시 ProcessId가
    // NULL"이라는 문서화되지 않은 제공자 동작에 기댄 것이고, ReturnValue==0은
    // Create 성공의 *계약상* 신호다. 다른 제공자/실패 모드가 ReturnValue!=0
    // 인데도 ProcessId를 VT_I4(예: 0)로 채우면, 이 검사가 없으면 PID 0(System
    // Idle) 같은 존재하지 않는 프로세스를 "성공"으로 돌려주게 된다. 이
    // 검사가 막는 것이 바로 그 경우다 -- 아래 타입 검사는 방어선일 뿐이다.
    VARIANT returnValue;
    ::VariantInit(&returnValue);
    hr = outParams->Get(L"ReturnValue", 0, &returnValue, nullptr, nullptr);
    const bool createSucceeded = SUCCEEDED(hr) && returnValue.vt == VT_I4 &&
                                 returnValue.lVal == 0;
    ::VariantClear(&returnValue);
    if (!createSucceeded) {
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

    // return 후 스코프 종료 시: 위 ComPtr들이 먼저 Release되고, 그
    // 다음 comUninitGuard가 CoUninitialize를 부른다(순서 보장은 위 주석).
    return pid;
}

}  // namespace maro::ipc
