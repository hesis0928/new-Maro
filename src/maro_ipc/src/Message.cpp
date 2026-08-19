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
    nlohmann::json j;
    try {
        j = nlohmann::json::parse(encoded);
    } catch (...) {
        return false;
    }

    const std::string type = j.value("type", std::string());
    if (type == "hello") {
        out.type = MessageType::Hello;
    } else if (type == "sessionEndClean") {
        out.type = MessageType::SessionEndClean;
    } else {
        return false;
    }
    out.payload = j.value("payload", std::string());
    return true;
}

}  // namespace maro::ipc
