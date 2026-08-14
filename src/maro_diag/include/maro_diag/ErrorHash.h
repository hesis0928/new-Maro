#pragma once

#include <string>

namespace maro {

// 에러 해시는 실패의 "자리와 종류"에서만 만든다.
//
// 포함: 호출부가 직접 쓰는 사이트 태그 문자열 하나뿐이다. 관례상
// "<클래스 또는 함수>.<사유>" 형태로 쓴다 (예:
// "MaroBindAxisCommand.TargetNotTransform").
//
// 제외: 포인터 주소, 타임스탬프, 노드 인스턴스 이름, 세션마다 달라지는 모든
// 값. 이 함수가 문자열 하나만 받는다는 시그니처 자체가 그것들을 원천
// 차단한다 -- 애초에 넣을 자리가 없다.
//
// 같은 사이트 태그는 항상 같은 해시를 낸다 (같은 프로세스든, 다른 세션이든,
// 다른 머신이든). FNV-1a는 로케일도 포인터도 시각도 관여하지 않는 순수 바이트
// 연산이라 이 성질이 플랫폼에 무관하게 성립한다.
std::string hashError(const std::string& siteTag);

}  // namespace maro
