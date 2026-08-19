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
        CREATE_BREAKAWAY_FROM_JOB,
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
