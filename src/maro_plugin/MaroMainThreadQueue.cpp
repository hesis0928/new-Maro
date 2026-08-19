#include "MaroMainThreadQueue.h"

#include <deque>
#include <mutex>
#include <vector>

#include <maya/MTimerMessage.h>

#include "MaroDiag.h"

namespace maro {

namespace {

constexpr float kQueueIntervalSeconds = 0.1f;

// 큐 자체의 뮤텍스. MaroDiag.h가 지켜 온 "말단 뮤텍스" 규율을 그대로
// 따른다: 이 락을 쥔 채로 boad(BoadMaro::error 등)를 부르지 않는다 --
// 아래 onTimer는 락을 놓은 뒤에야 task를 실행하므로, task 안에서 boad를
// 불러도 이 락과 얽히지 않는다.
std::mutex& queueMutex() {
    static std::mutex m;
    return m;
}

std::deque<std::function<void()>>& pending() {
    static std::deque<std::function<void()>> q;
    return q;
}

}  // namespace

MCallbackId MaroMainThreadQueue::s_timerId = 0;

MStatus MaroMainThreadQueue::install() {
    if (s_timerId != 0) return MS::kSuccess;
    MStatus status;
    s_timerId = MTimerMessage::addTimerCallback(kQueueIntervalSeconds, onTimer,
                                                nullptr, &status);
    if (!status) {
        s_timerId = 0;
    }
    return status;
}

MStatus MaroMainThreadQueue::uninstall() {
    if (s_timerId != 0) {
        MMessage::removeCallback(s_timerId);
        s_timerId = 0;
    }
    return MS::kSuccess;
}

void MaroMainThreadQueue::enqueue(std::function<void()> task) {
    std::lock_guard<std::mutex> lock(queueMutex());
    pending().push_back(std::move(task));
}

void MaroMainThreadQueue::onTimer(float /*elapsed*/, float /*last*/, void* /*clientData*/) {
    // 락을 쥔 채로 task를 실행하지 않는다 -- 실행 중에 새 enqueue가 들어오면
    // (같은 스레드에서는 안 일어나지만, task가 스스로 또 enqueue할 수는
    // 있다) 재진입 불가능한 std::mutex가 교착한다.
    std::vector<std::function<void()>> toRun;
    {
        std::lock_guard<std::mutex> lock(queueMutex());
        toRun.assign(pending().begin(), pending().end());
        pending().clear();
    }

    for (auto& task : toRun) {
        try {
            task();
        } catch (const std::exception& e) {
            BoadMaro::error("MaroMainThreadQueue.TaskThrew",
                            MString("Maro: a queued task threw: ") + e.what());
        } catch (...) {
            BoadMaro::error("MaroMainThreadQueue.TaskThrew",
                            "Maro: a queued task threw an unknown exception.");
        }
    }
}

}  // namespace maro
