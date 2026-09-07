#include "MaroStackTrace.h"

// 이 파일이 boost::stacktrace를 보는 **유일한** 번역 단위다. boost 헤더는
// 무겁고 windows.h/COM을 끌어오므로, 플러그인의 나머지가 그것을 보지 않게
// 여기 가둔다(MaroStackTrace.h는 std::string만 노출한다).
#include <boost/stacktrace.hpp>

#include <cstdlib>
#include <mutex>
#include <sstream>
#include <unordered_set>

#include "MaroDiag.h"

namespace maro {
namespace {

// 스택을 얼마나 깊이 뜰 것인가. 심볼화 비용이 프레임 수에 비례하므로
// 상한을 둔다. 실패 지점 주변 몇 프레임이면 "어디서 났는가"에는 충분하고,
// 그보다 깊은 곳은 Maya/Qt 내부라 우리가 읽을 것이 없다.
constexpr std::size_t kMaxFrames = 24;

// 맨 위 프레임 몇 개는 항상 우리 자신이라 정보가 없다: boost의 캡처
// 함수들과 이 함수. 걷어내고 실제 실패 지점 가까이부터 보여준다.
//
// [실측, Release 빌드] 2로 두면 결과가 이렇게 나온다:
//     0# maro::BoadMaro::error   at MaroDiag.cpp:437   <- 늘 같은 자리(잡음)
//     1# <실제 실패 지점>        at ...                 <- 여기가 알고 싶은 것
// 즉 3으로 올리면 0번이 곧바로 실패 지점이 되어 더 읽기 좋다. 그런데도
// 2로 두는 이유: 프레임 수는 인라이닝에 좌우되고(이 함수가 인라인되면
// 한 칸 줄어든다) 컴파일러/최적화 설정이 바뀌면 같이 바뀐다. 넉넉히
// 건너뛰다가 진짜 실패 지점을 잘라 먹으면 이 기능의 존재 이유가 사라지는데,
// 잡음 한 줄은 그냥 읽고 넘기면 그만이다. 비대칭한 비용이라 보수적인
// 쪽을 고른다.
constexpr std::size_t kSkipFrames = 2;

std::mutex& latchMutex() {
    static std::mutex m;
    return m;
}

std::unordered_set<std::string>& seenSiteTags() {
    static std::unordered_set<std::string> s;
    return s;
}

// 킬 스위치. 한 번만 읽는다 -- 세션 도중 바뀌는 것을 지원할 이유가 없고,
// getenv를 실패 경로마다 부르지 않는 편이 낫다.
bool stackTraceEnabled() {
    static const bool enabled = [] {
        const char* raw = std::getenv("MARO_DIAG_STACKTRACE");
        return !(raw != nullptr && raw[0] == '0' && raw[1] == '\0');
    }();
    return enabled;
}

}  // namespace

std::string captureStackTrace(const std::string& siteTag) {
    try {
        if (!stackTraceEnabled()) return std::string();

        // 워커 스레드에서는 뜨지 않는다 -- 이유는 헤더의 정책 주석 참고.
        // isMainThread()는 markMainThread()가 아직 안 불렸으면 true를
        // 돌려주는데(MaroDiag.h), 그 경우는 initializePlugin 이전이라
        // 정의상 메인 스레드다.
        if (!isMainThread()) return std::string();

        {
            std::lock_guard<std::mutex> lock(latchMutex());
            // 심볼화는 비싸다. 이 자리는 세션당 한 번만 뜬다.
            if (!seenSiteTags().insert(siteTag).second) {
                return std::string();
            }
        }

        // 여기서부터가 비싼 부분이다. 락 밖에서 한다 -- dbgeng COM 호출이
        // 수백 밀리초 걸릴 수 있는데 그동안 다른 스레드의 error()가 이
        // 래치 하나 때문에 막힐 이유가 없다.
        const boost::stacktrace::stacktrace trace(kSkipFrames, kMaxFrames);
        if (trace.empty()) return std::string();

        std::ostringstream os;
        os << trace;
        return os.str();
    } catch (...) {
        // 진단을 풍부하게 하려던 시도가 진단 자체를 깨뜨리면 안 된다.
        // 스택을 못 얻는 것은 빈 문자열로 충분히 표현된다.
        return std::string();
    }
}

void resetStackTraceLatchForTest() {
    std::lock_guard<std::mutex> lock(latchMutex());
    seenSiteTags().clear();
}

}  // namespace maro
