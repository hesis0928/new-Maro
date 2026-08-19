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
    } catch (...) {
        return false;
    }
}

}  // namespace maro::ipc
