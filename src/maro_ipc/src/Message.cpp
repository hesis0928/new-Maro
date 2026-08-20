#include "maro_ipc/Message.h"

#include <nlohmann/json.hpp>

namespace maro::ipc {

namespace {

const char* typeName(MessageType type) {
    switch (type) {
        case MessageType::Hello: return "hello";
        case MessageType::SessionEndClean: return "sessionEndClean";
    }
    return "unknown";
}

}  // namespace

std::string encodeMessage(const Message& message) {
    nlohmann::json j;
    j["type"] = typeName(message.type);
    j["payload"] = message.payload;
    return j.dump();
}

bool decodeMessage(const std::string& encoded, Message& out) {
    try {
        // Wrap entire function to handle both malformed JSON and type mismatches.
        // j.value<T>() throws type_error if the JSON value is not convertible to T,
        // not just on parse failure. This must never propagate to callers.
        nlohmann::json j = nlohmann::json::parse(encoded);

        // [최종 리뷰 3k] 콜러의 out이 아니라 지역 변수에 먼저 채운다.
        // Message.h가 약속하는 것은 "실패하면 out은 건드리지 않는다"인데,
        // out에 직접 쓰면 그 약속이 깨지는 입력이 실재한다: type은 알아볼 수
        // 있고 payload만 엉뚱한 JSON 타입인 경우, out.type을 대입한 *뒤*
        // j.value("payload", ...)가 type_error.302를 던진다. 그러면 실패를
        // 돌려주면서도 콜러의 type은 이미 바뀐 상태다. 감시자의 수신 루프
        // (src/maro_sentinel/main.cpp)는 같은 Message 객체를 재사용하므로
        // 그 오염이 다음 판정까지 따라간다.
        Message decoded;
        const std::string type = j.value("type", std::string());
        if (type == "hello") {
            decoded.type = MessageType::Hello;
        } else if (type == "sessionEndClean") {
            decoded.type = MessageType::SessionEndClean;
        } else {
            return false;
        }
        decoded.payload = j.value("payload", std::string());

        // 모든 필드를 성공적으로 꺼낸 뒤에야 콜러에게 옮긴다. 이 대입 자체는
        // 던질 수 없다(enum 대입 + std::string의 move 대입).
        out = std::move(decoded);
        return true;
    } catch (...) {
        return false;
    }
}

}  // namespace maro::ipc
