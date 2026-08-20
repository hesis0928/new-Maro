#pragma once

#include <cstdint>
#include <string>

#include <windows.h>

#include "maro_ipc/Message.h"

namespace maro::ipc {

// 메시지 모드 명명된 파이프의 서버 쪽(감시자가 만든다).
class NamedPipeServer {
public:
    explicit NamedPipeServer(const std::string& pipeName);
    ~NamedPipeServer();

    NamedPipeServer(const NamedPipeServer&) = delete;
    NamedPipeServer& operator=(const NamedPipeServer&) = delete;

    // 클라이언트 접속을 기다린다. 파이프를 못 만들었으면 즉시 false.
    bool waitForConnection(std::uint32_t timeoutMs);

    // 한 메시지를 받는다. 상대가 메시지 없이 연결을 끊으면(크래시 신호)
    // false를 돌려준다 -- 이 반환값 하나가 "정상 메시지 실패"와 "연결
    // 끊김"을 구분하지 않는 것처럼 보이지만, 감시자의 실제 판정(Task 8)은
    // 이 함수가 false를 돌려준 시점 자체가 아니라 그 *마지막으로 받은
    // 메시지가 SessionEndClean이었는가*로 정상/비정상을 가른다 -- 그래서
    // receiveMessage 자체는 성공/실패만 알면 충분하다.
    bool receiveMessage(Message& out, std::uint32_t timeoutMs);

    bool sendMessage(const Message& message);

    // 주의: 서버의 close()는 DisconnectNamedPipe를 부르고, 그것은 상대가
    // **아직 읽지 않은 데이터를 버린다**(MSDN). 즉 sendMessage() 직후에
    // close()를 부르면 그 마지막 메시지가 사라질 수 있다. 마지막 말을
    // 반드시 전하고 싶으면 상대가 읽고 나갈 때까지(=receiveMessage가
    // 끊김으로 실패할 때까지) 기다렸다 닫아야 한다. 자세한 근거와 실측은
    // NamedPipe.cpp의 close() 구현 주석 참고.
    void close();

private:
    HANDLE pipe_ = INVALID_HANDLE_VALUE;
    bool connected_ = false;
};

// 메시지 모드 명명된 파이프의 클라이언트 쪽(플러그인이 붙는다).
class NamedPipeClient {
public:
    NamedPipeClient() = default;
    ~NamedPipeClient();

    NamedPipeClient(const NamedPipeClient&) = delete;
    NamedPipeClient& operator=(const NamedPipeClient&) = delete;

    // 서버가 아직 CreateNamedPipeA를 안 불렀을 수 있으므로(막 spawn된
    // 직후) timeoutMs 안에서 짧은 간격으로 재시도한다.
    bool connect(const std::string& pipeName, std::uint32_t timeoutMs);

    bool sendMessage(const Message& message);
    bool receiveMessage(Message& out, std::uint32_t timeoutMs);

    void close();

private:
    HANDLE pipe_ = INVALID_HANDLE_VALUE;
};

}  // namespace maro::ipc
