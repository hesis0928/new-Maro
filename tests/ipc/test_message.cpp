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

// [최종 리뷰 3k] Message.h가 약속하는 것은 "false면 out은 건드리지 않는다"이지
// "false면 out의 일부만 건드린다"가 아니다. type은 알아볼 수 있는데 payload가
// 엉뚱한 JSON 타입인 입력이 정확히 그 경계를 찌른다: type을 먼저 대입한 뒤
// payload를 꺼내다 type_error.302가 날아가면, 콜러의 out은 실패했는데도
// 새 type을 갖게 된다. 감시자의 루프(main.cpp)는 같은 Message 객체를 재사용해
// 반복 수신하므로, 그 오염이 다음 판정까지 따라간다.
TEST(Message, DecodeLeavesOutUntouchedWhenPayloadFieldHasWrongJsonType) {
    maro::ipc::Message decoded;
    decoded.type = maro::ipc::MessageType::SessionEndClean;
    decoded.payload = "value from a previous message";

    EXPECT_FALSE(maro::ipc::decodeMessage(R"({"type":"hello","payload":123})", decoded));
    EXPECT_EQ(decoded.type, maro::ipc::MessageType::SessionEndClean)
        << "a failed decode overwrote the caller's type field";
    EXPECT_EQ(decoded.payload, "value from a previous message")
        << "a failed decode overwrote the caller's payload field";
}

}  // namespace
