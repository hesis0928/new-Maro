#pragma once

#include <cstdint>
#include <filesystem>
#include <string>

namespace maro::ipc {

// 아래 넷은 전부 이 파일 한 곳에서만 정의한다. 두 곳에서 각자 이름을
// 만들면(예: 플러그인 쪽이 pipeName을 한 번 더 손으로 짓는다면) 저널이
// 겪었던 "세션-open 판정이 writer/reader에 따로 있다가 우연히만 맞아떨어진"
// 함정이 재발한다.

// 파이프 이름. \\.\pipe\maro_sentinel_<pid> 모양.
std::string pipeName(std::uint64_t pid);

// 명명된 뮤텍스 이름. Global\ 접두사로 세션 0(서비스)과도 충돌하지 않는다.
std::string mutexName(std::uint64_t pid);

// 킬 스위치 이벤트 이름.
std::string killEventName(std::uint64_t pid);

// PID·시작 시각 기록 파일 경로. bookDir는 이미 존재를 보장받은 디렉터리라고
// 가정한다(호출부가 만든다) -- 이 함수는 경로만 계산하고 디스크를 건드리지 않는다.
std::filesystem::path recordFilePath(const std::filesystem::path& bookDir, std::uint64_t pid);

}  // namespace maro::ipc
