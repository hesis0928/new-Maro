#pragma once

#include <string>

namespace maro {

// 지금 이 자리의 호출 스택을 함수명 + 파일:줄로 풀어서 돌려준다. 정책상
// 뜨지 않기로 한 경우에는 빈 문자열(그것이 정상이며 에러가 아니다).
//
// 왜 있는가: 이 플러그인에는 예외를 밖으로 못 내보내는 경계가 많다(Maya
// 콜백에서 예외가 새면 Maya가 죽는다). 그래서 그런 자리는 전부
// `catch (...)`로 삼키고 BoadMaro::error()로 메시지만 남기는데, 정작
// **어디서** 났는지는 남지 않는다. 크래시가 아니라 조용한 실패라서 크래시
// 덤프도 안 생긴다 -- tools/crashtriage/의 사후 분석 도구들이 손도 못 대는
// 유형이고, 2026-09-07에 maroPointCloud를 파느라 하루를 쓴 것이 정확히
// 이것이었다.
//
// 구현은 boost::stacktrace(Maya devkit이 devkitBase/include/boost로 Boost
// 1.85를 통째로 들고 있다)다. 헤더 온리이고 dbgeng.lib/ole32.lib 링크만
// 필요하다 -- 디버거 설치도 별도 DLL 배포도 없다. boost 헤더는 이 함수의
// .cpp 하나에만 갇혀 있다(플러그인의 나머지 TU가 boost를 보지 않게).
//
// == 정책: 언제 뜨는가 ==
//
// 스택 "캡처"(주소 수집)는 싸지만 "심볼화"(dbgeng로 이름/줄 찾기)는
// 비싸다 -- 프레임당 수 밀리초에 COM 초기화 비용까지 붙는다. 그래서 아래
// 세 조건을 **전부** 만족할 때만 뜬다:
//
//   1. `MARO_DIAG_STACKTRACE=0`이 아닐 것 (킬 스위치. 사용자 환경에서
//      dbgeng가 말썽이면 코드 수정 없이 끌 수 있어야 한다).
//   2. 메인 스레드일 것. dbgeng 백엔드는 COM을 쓰는데, Maya가 소유한
//      워커 스레드에서 COM 아파트먼트를 건드리는 것이 안전하다는 근거가
//      없다. 이 코드베이스가 MGlobal::display*에 이미 걸어 둔 것과 **같은**
//      가드다(MaroDiag.h 참고). 그 대가로 워커 스레드(Parallel Evaluation
//      Manager 아래의 compute() 등)의 실패는 스택을 못 얻는다 -- 알면서
//      받아들이는 한계이고, 얻더라도 그 스택은 DG 워커 프레임이라 읽을
//      가치가 크지 않다.
//   3. 이 siteTag로 이번 세션에 아직 뜬 적이 없을 것. siteTag는 실패
//      지점마다 고정된 컴파일타임 문자열이므로(ErrorHash.h 계약), 매
//      프레임 실패하는 경로가 있어도 심볼화는 딱 한 번만 일어난다.
//      이 파일의 여러 곳이 이미 쓰고 있는 "세션당 1회 보고" 관용구와
//      같은 원리이며, 뷰포트 콜백에서 Maya가 얼어붙는 것을 막는다.
//
// 절대 던지지 않는다. 호출자가 이미 실패를 처리하는 중이므로, 진단을
// 풍부하게 하려던 시도가 그 처리를 망가뜨리면 안 된다.
std::string captureStackTrace(const std::string& siteTag);

// 테스트 전용. "이 siteTag는 이미 떴다" 래치를 비운다.
void resetStackTraceLatchForTest();

}  // namespace maro
