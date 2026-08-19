#include <gtest/gtest.h>

#include "maro_ipc/Message.h"

namespace {

TEST(Message, RoundTripsHello) {
    maro::ipc::Message msg;
    msg.type = maro::ipc::MessageType::Hello;

    const std::string encoded = maro::ipc::encodeMessage(msg);
    maro::ipc::Message decoded;
    ASSERT_TRUE(maro::ipc::decodeMessage(encoded, decoded));
    EXPECT_EQ(decoded.type, maro::ipc::MessageType::Hello);
    EXPECT_TRUE(decoded.payload.empty());
}

TEST(Message, RoundTripsSessionEndClean) {
    maro::ipc::Message msg;
    msg.type = maro::ipc::MessageType::SessionEndClean;

    const std::string encoded = maro::ipc::encodeMessage(msg);
    maro::ipc::Message decoded;
    ASSERT_TRUE(maro::ipc::decodeMessage(encoded, decoded));
    EXPECT_EQ(decoded.type, maro::ipc::MessageType::SessionEndClean);
}

// C-2가 태그 붙은 페이로드를 실을 자리 -- 지금은 비워 두지만 왕복은 된다.
TEST(Message, PayloadRoundTrips) {
    maro::ipc::Message msg;
    msg.type = maro::ipc::MessageType::Hello;
    msg.payload = "future breadcrumb data";

    const std::string encoded = maro::ipc::encodeMessage(msg);
    maro::ipc::Message decoded;
    ASSERT_TRUE(maro::ipc::decodeMessage(encoded, decoded));
    EXPECT_EQ(decoded.payload, "future breadcrumb data");
}

// 깨진 바이트열(파이프 오류로 반쪽만 온 경우 등)은 예외 없이 false를 돌려준다.
TEST(Message, DecodeFailsCleanlyOnGarbage) {
    maro::ipc::Message decoded;
    EXPECT_FALSE(maro::ipc::decodeMessage("not json at all {{{", decoded));
}

TEST(Message, DecodeFailsOnUnknownType) {
    maro::ipc::Message decoded;
    EXPECT_FALSE(maro::ipc::decodeMessage(R"({"type":"nonsense","payload":""})", decoded));
}

// JSON이 형식상 맞아도 필드 타입이 맞지 않으면(예: type이 정수) 예외 없이 false를 돌려준다.
TEST(Message, DecodeFailsCleanlyWhenTypeFieldHasWrongJsonType) {
    maro::ipc::Message decoded;
    EXPECT_FALSE(maro::ipc::decodeMessage(R"({"type":123,"payload":""})", decoded));
}

}  // namespace
