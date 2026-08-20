#pragma once

namespace maro {

// 플러그인 쪽에서 감시자와의 관계를 관리하는 정적 클래스. 로드 시
// connectOrSpawn(), 정상 언로드 시 notifyCleanExit() 다음 shutdown()을
// 부른다. 이 클래스의 어떤 실패도 예외를 던지지 않는다 -- 감시자가
// 없어도 플러그인 기능은 그대로 돈다는 설계 스펙 §3.5의 규율.
//
// 이 세 함수의 호출부는 전부 Maya 콜백 경계(initializePlugin/
// uninitializePlugin)다. 그래서 "던지지 않는다"는 것은 편의가 아니라
// 이 프로젝트 전역 규율("예외가 Maya 콜백 경계를 넘으면 안 된다")의
// 일부다 -- 세 함수 모두 본문 전체를 try/catch(...)로 감싼다
// (MaroSentinelClient.cpp).
class MaroSentinelClient {
public:
    // 이미 접속돼 있으면 아무 일도 안 한다. 처음 부르면 3단계 spawn을
    // 시도하고 성공하면 파이프에 접속해 HELLO를 보낸다. 전부 실패해도
    // 아무 예외 없이 조용히 반환한다.
    static void connectOrSpawn();

    // SESSION_END_CLEAN을 보낸다. 접속돼 있지 않으면 아무것도 안 한다.
    static void notifyCleanExit();

    // 파이프를 닫는다. uninitializePlugin 마지막에 부른다.
    static void shutdown();
};

}  // namespace maro
