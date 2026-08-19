#pragma once

#include <cstddef>
#include <functional>

#include <maya/MCallbackIdArray.h>
#include <maya/MStatus.h>

namespace maro {

// 상시로 도는 메인 스레드 큐 (설계 스펙 §3.8). MaroPump와 무관하다 --
// MaroPump는 maroStartBridge/maroStopBridge로 켜고 끄는 발행 펌프이고, 이
// 큐는 플러그인 로드부터 언로드까지 항상 돈다(브리지가 꺼져 있어도 해법
// 적용이 안전한 시점을 얻어야 하기 때문이다 -- 진단은 보통 브리지를 켜기
// 전에 일어난다).
//
// 0.1초 주기는 MTimerMessage::addTimerCallback을 쓴다 -- MaroPump.cpp가
// 이미 같은 API로 30Hz를 돌리는 것과 같은 메커니즘이다. 그 타이머 콜백은
// Maya가 메인 스레드에서만 부르므로, 여기서 실행되는 작업은 DG 평가 중이
// 아님이 보장된 시점에 돈다.
class MaroMainThreadQueue {
public:
    static MStatus install();
    static MStatus uninstall();

    // task는 다음 타이머 틱에서, 큐에 들어간 순서대로 실행된다. task
    // 자신이 예외를 던지면 이 함수를 부른 스레드가 아니라 다음 틱의 타이머
    // 콜백 안에서 삼켜진다 -- 그 경계를 넘으면 Maya가 죽는다는 이 프로젝트
    // 전역 규율 때문이다.
    static void enqueue(std::function<void()> task);

private:
    static void onTimer(float elapsed, float last, void* clientData);

    static MCallbackId s_timerId;
};

}  // namespace maro
