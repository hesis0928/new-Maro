#pragma once

#include <cstdint>
#include <optional>
#include <string>

#include <windows.h>

namespace maro::ipc {

// 지금 이 프로세스가 job object 안에 있는가. 원 스펙 §5.1의 "빠져나왔겠지가
// 아니라 빠져나왔다를 안다"의 근거 -- 감시자가 기동 직후 이것으로 자기
// 상태를 확인해 파이프로 보고한다(Task 8).
bool isCurrentProcessInJob();

// CREATE_BREAKAWAY_FROM_JOB으로 spawn한다. 호출한 프로세스(플러그인)의
// job이 JOB_OBJECT_LIMIT_BREAKAWAY_OK를 허용하지 않으면 CreateProcess
// 자체가 실패해 nullopt를 돌려준다 -- "실패했다"를 알아내는 데 자식의
// 보고를 기다릴 필요가 없다. 성공하면 호출부가 handle을 닫을 책임을 진다
// (PROCESS_INFORMATION::hProcess/hThread).
std::optional<PROCESS_INFORMATION> spawnWithBreakaway(const std::string& exePath,
                                                        const std::string& args);

// WMI Win32_Process::Create로 우회 생성한다. 이 경로로 만들어진 프로세스는
// Maya의 자식이 아니라 WMI 서비스(WinMgmt) 밑에서 만들어지므로 Maya의 job과
// 무관하다 -- CREATE_BREAKAWAY_FROM_JOB이 막혔을 때의 2단계 폴백. 같은
// 사용자 프로세스라 관리자 권한이 필요 없다. 실패(경로가 없거나, 생성
// 자체가 거부되거나)하면 nullopt.
std::optional<std::uint64_t> spawnViaWmi(const std::string& exePath, const std::string& args);

}  // namespace maro::ipc
