#pragma once

#include <memory>
#include <string>

namespace rclcpp {
class Context;
}

namespace maro {

// Maro 전용 rclcpp 컨텍스트.
//
// **왜 전역 기본 컨텍스트를 안 쓰는가**: `rclcpp::init()`/`rclcpp::shutdown()`은
// 프로세스 전역의 기본 컨텍스트를 건드린다. Maya는 플러그인이 여럿 사는
// 프로세스이므로, 같은 Maya에 rclcpp를 쓰는 다른 플러그인이 있으면 Maro의
// 언로드가 **그쪽 컨텍스트까지 끝내 버린다**(반대로 그쪽 언로드가 우리를
// 끊을 수도 있다). 어느 쪽이든 남의 노드/퍼블리셔가 살아 있는 채로 밑에서
// 컨텍스트가 사라지는 것이라, 조용한 오작동이나 크래시로 이어진다.
//
// rclcpp는 이 상황을 위해 컨텍스트를 값으로 다루는 길을 열어 두었다:
// 자기 `rclcpp::Context`를 만들어 `NodeOptions::context()`와
// `ExecutorOptions::context`로 넘기면, 그 컨텍스트에 매달린 것만 우리 것이
// 되고 `shutdown()`도 우리 것만 끝낸다. 이 모듈이 그 하나뿐인 컨텍스트를
// 소유한다.
//
// 이 플러그인 안에서 rclcpp 컨텍스트를 만드는 곳은 여기 하나다 --
// MaroRosRuntime(발행)과 MaroCommandDeviceNode(수신)가 같은 컨텍스트를
// 공유해야, MaroCommands.cpp의 shutdownBridge()가 지키는 종료 순서
// ("수신 스레드가 멈춘 뒤에야 컨텍스트를 끊는다")가 의미를 갖는다.

// 컨텍스트를 얻는다. 아직 없으면 만들어서 init한다. 실패하면 nullptr.
// 절대 던지지 않는다.
std::shared_ptr<rclcpp::Context> rosContext();

// 지금 컨텍스트가 살아 있는가. 전역 `rclcpp::ok()`의 대응물이며, 컨텍스트가
// 아직 만들어지지 않았으면 false.
bool rosContextOk();

// 컨텍스트를 끝낸다. 전역 `rclcpp::shutdown()`의 대응물이지만 **우리
// 컨텍스트만** 끝낸다. 멱등이고 절대 던지지 않는다.
void shutdownRosContext(const std::string& reason);

}  // namespace maro
