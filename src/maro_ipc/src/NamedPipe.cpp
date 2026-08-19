#include "maro_ipc/NamedPipe.h"

#include <chrono>
#include <thread>

namespace maro::ipc {

namespace {

// 파이프 버퍼이자 한 번의 읽기 버퍼 크기. C-1의 메시지는 필드 두 개짜리
// JSON이라 여유가 크다. 이보다 큰 메시지가 오면 ReadFile이 ERROR_MORE_DATA로
// 실패하고 readOneMessage가 false를 돌려준다(나머지 조각은 큐에 남는다) --
// 부스러기 스트림으로 메시지가 커지는 C-2가 이 값을 키우거나 조각 이어붙이기를
// 넣을 자리다.
constexpr DWORD kBufferSize = 8192;

// 쓰기 완료를 기다리는 상한. 읽기와 달리 호출부가 타임아웃을 주지 않는다 --
// 상대가 버퍼를 안 비우는 병리적 경우에도 영원히 매달리지 않기 위한 값이다.
constexpr std::uint32_t kWriteTimeoutMs = 5000;

// 오버랩 I/O 하나를 타임아웃과 함께 기다린다. 성공하면 실제로 옮겨진
// 바이트 수를 outBytes에 채운다. 파이프가 끊겼으면(ERROR_BROKEN_PIPE류)
// false를 돌려준다 -- 이것이 "메시지 없이 연결 끊김"이 최종적으로
// 드러나는 지점이다.
bool waitOverlapped(HANDLE handle, OVERLAPPED& overlapped, std::uint32_t timeoutMs,
                    DWORD& outBytes) {
    const DWORD waitResult = ::WaitForSingleObject(overlapped.hEvent, timeoutMs);
    if (waitResult != WAIT_OBJECT_0) {
        // [브리프에서 고침] CancelIoEx는 취소를 *요청*만 하고 바로 돌아온다.
        // 이 OVERLAPPED와 그 이벤트는 호출부의 스택(ScopedOverlapped)에
        // 있으므로, 취소가 실제로 끝나기 전에 여기서 돌아가면 커널이 이미
        // 사라진 구조체에 완료 결과를 쓰게 된다. 그래서 취소 요청이
        // 받아들여졌을 때만(=정말로 걸려 있던 I/O가 있을 때만) bWait=TRUE로
        // 완료(대개 ERROR_OPERATION_ABORTED)를 확인하고 나간다.
        //
        // CancelIoEx가 실패하면(ERROR_NOT_FOUND: 걸려 있는 I/O가 없다)
        // 기다리지 않는다 -- 그 경우 커널이 건드릴 것이 애초에 없고,
        // 반대로 기다리면 영원히 신호되지 않을 이벤트를 붙잡게 된다.
        if (::CancelIoEx(handle, &overlapped)) {
            DWORD cancelledBytes = 0;
            ::GetOverlappedResult(handle, &overlapped, &cancelledBytes, TRUE);
        }
        return false;
    }
    return ::GetOverlappedResult(handle, &overlapped, &outBytes, FALSE) != 0;
}

// RAII로 오버랩 구조체의 이벤트 핸들을 관리한다 -- 모든 오버랩 호출이
// 자기 이벤트를 새로 만들고 반드시 닫는다는 규율을 코드로 강제한다.
struct ScopedOverlapped {
    OVERLAPPED overlapped{};
    ScopedOverlapped() { overlapped.hEvent = ::CreateEventA(nullptr, TRUE, FALSE, nullptr); }
    ~ScopedOverlapped() {
        if (overlapped.hEvent != nullptr) ::CloseHandle(overlapped.hEvent);
    }
    ScopedOverlapped(const ScopedOverlapped&) = delete;
    ScopedOverlapped& operator=(const ScopedOverlapped&) = delete;
};

// 서버/클라이언트가 똑같이 하는 한 메시지 읽기. 메시지 모드라 한 번의
// ReadFile이 한 메시지 전체를 준다 -- 길이 프리픽스가 필요 없는 이유다.
bool readOneMessage(HANDLE pipe, Message& out, std::uint32_t timeoutMs) {
    ScopedOverlapped scoped;
    if (scoped.overlapped.hEvent == nullptr) return false;

    std::string buffer(kBufferSize, '\0');
    DWORD bytesRead = 0;
    const BOOL immediate = ::ReadFile(pipe, buffer.data(),
                                      static_cast<DWORD>(buffer.size()), &bytesRead,
                                      &scoped.overlapped);
    if (!immediate) {
        const DWORD err = ::GetLastError();
        // 여기 ERROR_BROKEN_PIPE도 포함된다 -- 상대가 이미 닫은 뒤에 읽기를
        // 걸면 대기조차 하지 않고 곧바로 이 갈래로 떨어진다. 이 return이
        // "메시지 없이 끊김"을 타임아웃 없이 즉시 알아채는 경로다.
        if (err != ERROR_IO_PENDING) return false;
        if (!waitOverlapped(pipe, scoped.overlapped, timeoutMs, bytesRead)) return false;
    }

    buffer.resize(bytesRead);
    return decodeMessage(buffer, out);
}

// 서버/클라이언트가 똑같이 하는 한 메시지 쓰기.
bool writeOneMessage(HANDLE pipe, const Message& message) {
    ScopedOverlapped scoped;
    if (scoped.overlapped.hEvent == nullptr) return false;

    const std::string encoded = encodeMessage(message);
    DWORD bytesWritten = 0;
    const BOOL immediate = ::WriteFile(pipe, encoded.data(),
                                       static_cast<DWORD>(encoded.size()), &bytesWritten,
                                       &scoped.overlapped);
    if (immediate) return bytesWritten == encoded.size();

    const DWORD err = ::GetLastError();
    if (err != ERROR_IO_PENDING) return false;
    return waitOverlapped(pipe, scoped.overlapped, kWriteTimeoutMs, bytesWritten) &&
           bytesWritten == encoded.size();
}

}  // namespace

NamedPipeServer::NamedPipeServer(const std::string& pipeName) {
    pipe_ = ::CreateNamedPipeA(
        pipeName.c_str(),
        PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED,
        PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
        1,  // 이 감시자는 자기 Maya 하나만 상대한다 -- §3.1의 1:1 모델.
        kBufferSize, kBufferSize,
        0,  // 기본 타임아웃 -- 실제 대기는 전부 오버랩+WaitForSingleObject로 직접 건다.
        nullptr);
}

NamedPipeServer::~NamedPipeServer() { close(); }

bool NamedPipeServer::waitForConnection(std::uint32_t timeoutMs) {
    if (pipe_ == INVALID_HANDLE_VALUE) return false;

    ScopedOverlapped scoped;
    if (scoped.overlapped.hEvent == nullptr) return false;

    const BOOL immediate = ::ConnectNamedPipe(pipe_, &scoped.overlapped);
    if (immediate) {
        connected_ = true;
        return true;
    }
    const DWORD err = ::GetLastError();
    if (err == ERROR_PIPE_CONNECTED) {
        // 클라이언트가 ConnectNamedPipe를 부르기 전에 이미 붙어 있었다 --
        // 성공으로 친다.
        connected_ = true;
        return true;
    }
    if (err != ERROR_IO_PENDING) return false;

    DWORD bytes = 0;
    connected_ = waitOverlapped(pipe_, scoped.overlapped, timeoutMs, bytes);
    return connected_;
}

bool NamedPipeServer::receiveMessage(Message& out, std::uint32_t timeoutMs) {
    if (pipe_ == INVALID_HANDLE_VALUE || !connected_) return false;
    return readOneMessage(pipe_, out, timeoutMs);
}

bool NamedPipeServer::sendMessage(const Message& message) {
    if (pipe_ == INVALID_HANDLE_VALUE || !connected_) return false;
    return writeOneMessage(pipe_, message);
}

void NamedPipeServer::close() {
    if (pipe_ != INVALID_HANDLE_VALUE) {
        // 주의(실측으로 확인): DisconnectNamedPipe는 상대가 아직 안 읽은
        // 데이터를 버린다(MSDN). 즉 "sendMessage() 직후 close()"는 그 마지막
        // 메시지를 잃을 수 있다 -- 서버가 마지막 말을 전하고 싶으면 상대가
        // 읽고 나갈 때까지(=receiveMessage가 끊김으로 실패할 때까지)
        // 기다렸다 닫아야 한다. 반대 방향(클라이언트가 보내고 바로 닫는
        // SessionEndClean)은 안전하다: 클라이언트의 close()는 CloseHandle
        // 뿐이라 이미 파이프에 들어간 데이터는 서버가 마저 읽는다
        // (tests/ipc/test_named_pipe.cpp의 마지막 두 테스트가 둘 다 고정한다).
        if (connected_) ::DisconnectNamedPipe(pipe_);
        ::CloseHandle(pipe_);
        pipe_ = INVALID_HANDLE_VALUE;
    }
    connected_ = false;
}

NamedPipeClient::~NamedPipeClient() { close(); }

bool NamedPipeClient::connect(const std::string& pipeName, std::uint32_t timeoutMs) {
    // 이미 붙어 있는데 다시 connect()를 부르면 이전 핸들이 샌다.
    close();

    // [브리프에서 고침] GetTickCount는 49.7일마다 0으로 돌아가므로
    // "지금 + 타임아웃"이 넘칠 수 있다(그러면 첫 시도 뒤 바로 포기한다).
    // GetTickCount64는 넘치지 않는다.
    const ULONGLONG deadlineTick = ::GetTickCount64() + timeoutMs;
    for (;;) {
        pipe_ = ::CreateFileA(pipeName.c_str(), GENERIC_READ | GENERIC_WRITE, 0, nullptr,
                              OPEN_EXISTING, FILE_FLAG_OVERLAPPED, nullptr);
        if (pipe_ != INVALID_HANDLE_VALUE) {
            // [브리프에서 고침] CreateFile로 연 클라이언트 핸들은 서버 쪽이
            // 메시지 타입 파이프여도 *바이트* 읽기 모드로 시작한다(MSDN
            // "Named Pipe Client"). 그대로 두면 큐에 두 메시지가 쌓였을 때
            // 한 번의 ReadFile이 둘을 이어 붙여 돌려주고 decodeMessage가
            // 깨진다 -- 이 파일이 길이 프리픽스를 안 쓰는 근거 자체가
            // 무너진다. 서버와 같은 메시지 읽기 모드로 맞춘다.
            DWORD mode = PIPE_READMODE_MESSAGE;
            if (!::SetNamedPipeHandleState(pipe_, &mode, nullptr, nullptr)) {
                close();
                return false;
            }
            return true;
        }

        const DWORD err = ::GetLastError();
        if (err != ERROR_FILE_NOT_FOUND && err != ERROR_PIPE_BUSY) return false;
        if (::GetTickCount64() >= deadlineTick) return false;
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
}

bool NamedPipeClient::sendMessage(const Message& message) {
    if (pipe_ == INVALID_HANDLE_VALUE) return false;
    return writeOneMessage(pipe_, message);
}

bool NamedPipeClient::receiveMessage(Message& out, std::uint32_t timeoutMs) {
    if (pipe_ == INVALID_HANDLE_VALUE) return false;
    return readOneMessage(pipe_, out, timeoutMs);
}

void NamedPipeClient::close() {
    if (pipe_ != INVALID_HANDLE_VALUE) {
        ::CloseHandle(pipe_);
        pipe_ = INVALID_HANDLE_VALUE;
    }
}

}  // namespace maro::ipc
