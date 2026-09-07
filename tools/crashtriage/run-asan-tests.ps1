# out/build-asan 트리의 배치 테스트를 AddressSanitizer 아래에서 돌린다.
#
# **중요**: ASan 런타임은 Maya가 초기화되기 *전에* 프로세스에 들어가야
# 한다. 테스트 스크립트가 maya.standalone.initialize()보다 먼저
# ctypes.CDLL($env:MARO_ASAN_DLL)을 부르지 않으면, ASan은 리포트도 없이
# 프로세스를 죽인다(실측: 늦게 로드하면 unloadPlugin 근처에서 AV).
#
# 두 가지가 PATH에 있어야 한다:
#   1) clang_rt.asan_dynamic-x86_64.dll (MSVC 툴체인 bin) -- 없으면 maro.mll
#      로드 자체가 실패한다.
#   2) ROS 2/Embree 런타임 DLL -- 이건 ctest가 테스트별로 알아서 넣는다.
#
# 사용법:  .\tools\crashtriage\run-asan-tests.ps1 [-Filter point_cloud]

param([string]$Filter = "")

$msvcBin = Get-ChildItem "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC" -Directory |
    Sort-Object Name -Descending | Select-Object -First 1
$asanDir = Join-Path $msvcBin.FullName "bin\Hostx64\x64"
if (-not (Test-Path (Join-Path $asanDir "clang_rt.asan_dynamic-x86_64.dll"))) {
    throw "ASan runtime not found under $asanDir"
}
$env:PATH = "$asanDir;$env:PATH"
$env:MARO_ASAN_DLL = Join-Path $asanDir "clang_rt.asan_dynamic-x86_64.dll"

# windows_hook_rtl_allocators: Maya는 CRT malloc뿐 아니라 Win32 힙 API도
# 직접 쓴다. 이걸 켜야 RtlAllocateHeap 계열까지 ASan이 가로채서, 우리
# 코드가 Maya가 준 버퍼를 넘겨 쓰는 경우도 잡힌다 -- 이 조사의 핵심 가설이
# 정확히 그것이다.
$env:ASAN_OPTIONS = "windows_hook_rtl_allocators=1:halt_on_error=1:print_stats=0:detect_leaks=0"

$args = @("--test-dir", "out/build-asan", "-C", "Release", "--output-on-failure")
if ($Filter) { $args += @("-R", $Filter) }
ctest @args
