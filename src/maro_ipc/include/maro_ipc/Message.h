#pragma once

#include <string>

namespace maro::ipc {

// 감시자와 플러그인이 주고받는 메시지 종류. C-1은 둘뿐이다. C-2가 부스러기
// 스트림을 위해 새 종류를 추가할 자리이며, payload 필드가 그 확장을 이미
// 받아들일 수 있게 지금부터 있다(지금은 항상 빈 문자열).
enum class MessageType {
    Hello,            // 접속 직후. 프레이밍이 실제로 도는지 확인하는 용도.
    SessionEndClean,  // 정상 종료 신호. 이 메시지 없이 파이프가 끊기면 비정상 종료다.
};

struct Message {
    MessageType type = MessageType::Hello;
    std::string payload;
};

// 메시지 모드 파이프의 한 번의 WriteFile 페이로드로 쓸 문자열을 만든다.
std::string encodeMessage(const Message& message);

// encodeMessage()가 만든 문자열을 되돌린다. 형식이 깨졌거나 type이 모르는
// 값이면 false를 돌려주고 out은 건드리지 않는다 -- 예외를 던지지 않는다.
bool decodeMessage(const std::string& encoded, Message& out);

}  // namespace maro::ipc
