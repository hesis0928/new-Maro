#include "MaroRosContext.h"

#include <mutex>

#include <rclcpp/context.hpp>
#include <rclcpp/init_options.hpp>

namespace maro {
namespace {

std::mutex& contextMutex() {
    static std::mutex m;
    return m;
}

// 세션 하나에 컨텍스트 하나. shutdownRosContext() 뒤에 다시 rosContext()를
// 부르면(브리지 재연결) 여기서 새 컨텍스트를 만든다 -- 한 번 shutdown된
// rclcpp::Context는 되살릴 수 없기 때문이다. 이것이 전역 컨텍스트를 쓰던
// 예전 코드보다 나아진 점이기도 하다: 예전에는 `rclcpp::init()`을
// `if (!rclcpp::ok())`로 감싸 프로세스 전역 컨텍스트를 재초기화하려 했는데,
// 그 경로는 같은 프로세스의 다른 rclcpp 사용자와 정면으로 충돌한다.
std::shared_ptr<rclcpp::Context>& storage() {
    static std::shared_ptr<rclcpp::Context> ctx;
    return ctx;
}

}  // namespace

std::shared_ptr<rclcpp::Context> rosContext() {
    try {
        std::lock_guard<std::mutex> lock(contextMutex());
        std::shared_ptr<rclcpp::Context>& ctx = storage();
        if (ctx && ctx->is_valid()) return ctx;

        auto fresh = std::make_shared<rclcpp::Context>();
        // 인자를 넘기지 않는다 -- Maya의 argv는 ROS 인자가 아니다.
        // ROS_DOMAIN_ID 등 환경변수는 여기서 읽힌다(그래서 설정 패널이
        // 도메인을 바꾸려면 브리지를 내렸다 올려야 한다 --
        // maroSettingsPanel._onConnect의 주석 참고).
        fresh->init(0, nullptr, rclcpp::InitOptions());
        ctx = fresh;
        return ctx;
    } catch (...) {
        // 진단은 호출부가 낸다 -- 이 모듈은 rclcpp만 알고 boad를 모른다.
        return nullptr;
    }
}

bool rosContextOk() {
    try {
        std::lock_guard<std::mutex> lock(contextMutex());
        const std::shared_ptr<rclcpp::Context>& ctx = storage();
        return static_cast<bool>(ctx) && ctx->is_valid();
    } catch (...) {
        return false;
    }
}

void shutdownRosContext(const std::string& reason) {
    try {
        std::shared_ptr<rclcpp::Context> ctx;
        {
            std::lock_guard<std::mutex> lock(contextMutex());
            ctx = storage();
            storage().reset();
        }
        // 락 밖에서 끝낸다. shutdown()은 컨텍스트에 매달린 것들의 정리를
        // 유발할 수 있고, 그 와중에 rosContextOk()를 부르는 코드가 있으면
        // 같은 뮤텍스로 교착한다.
        if (ctx && ctx->is_valid()) {
            ctx->shutdown(reason);
        }
    } catch (...) {
        // 정리 경로 -- 절대 던지지 않는다.
    }
}

}  // namespace maro
