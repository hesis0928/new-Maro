#pragma once

#include <cstdint>
#include <string>

#include "maro_diag/RemedyAction.h"

namespace maro {

// 진단 심각도. boad가 스크립트 에디터에 어떤 함수로 내보낼지도 이것으로 정해진다.
enum class DiagSeverity {
    Info,
    Warn,
    DevInfo,
    Error,
};

// onfix가 포착하는 DG 컨텍스트. 파일 경로가 아니라 노드·어트리뷰트·커맨드·축의
// 관계를 담는다 (설계 스펙 §4 "onfix가 바뀐 이유"). 필드가 비어 있으면 "그
// 시점에 관여가 없었다"는 뜻이지 에러가 아니다.
struct DgContext {
    std::string nodeType;       // 관여한 노드의 타입 이름. 예: "maroAxis", "pointLight"
    std::string attributeName;  // 관여한 어트리뷰트 롱네임. 예: "targetObject"
    std::string activeCommand;  // 진행 중이던 커맨드 클래스 이름. 예: "MaroBindAxisCommand"
    std::string axisOrTarget;   // 관여한 축 또는 대상 오브젝트의 이름.

    // 위 네 필드가 비어 있는 것은 두 가지 뜻일 수 있다 -- 그 자리에 관여한
    // 것이 애초에 없었거나(관여 없음), 관여는 했는데 그 시점에 알아낼 수
    // 없었거나(못 채움). 후자가 실제로 있다: compute()가 워커 스레드에서
    // 돌 때는 Maya에 노드 이름을 물을 수 없어 axisOrTarget을 비운다.
    // 패널이 둘을 똑같이 빈칸으로 그리면 사용자는 "정보가 없다"와 "이
    // 도구가 고장 났다"를 구분하지 못한다 (설계 스펙 §4.4).
    //
    // 플래그가 둘인 이유: 이름 조회와 타입 조회는 서로 다른 실패 지점이다.
    // MaroDeleteWatcher.cpp의 captureFromNode는 둘 다 같은 try 블록 안에서
    // 살아있는 MFnDependencyNode로 얻는다 -- 그 생성자가 던지면(노드가
    // 삭제 도중이라 너무 손상돼 이름을 붙일 수 없는, 바로 이 기능이
    // 존재하는 이유가 되는 경우) nodeType과 axisOrTarget이 함께 비게
    // 된다. 하나의 플래그로 둘을 같이 표시하면 "타입은 원래 없었는데
    // 이름만 못 채운" 경우(예: compute() 워커 스레드 경로, nodeType은
    // 컴파일타임 리터럴이라 실패할 수 없다)와 "둘 다 못 채운" 경우를
    // 구분할 수 없다. 그래서 각 필드가 자신의 조회 실패만 표시하도록
    // 나눈다.
    bool nameUnavailable = false;  // axisOrTarget을 원했지만 얻지 못했다.
    bool typeUnavailable = false;  // nodeType을 원했지만 얻지 못했다.
};

// boad의 인메모리 진단 스트림 한 칸. 진단 패널(Layer B)이 그대로 읽을 구조이므로
// 지금부터 이 모양으로 고정한다.
//
// message와 priorAnalysis는 절대 서로를 덮어쓰지 않는다 (리뷰 Finding C1).
// book의 해시는 실패의 "자리와 종류"만 담을 뿐 이번 발생의 구체적인 노드
// 이름·값은 담지 않으므로(ErrorHash.h 계약), 과거 분석 텍스트를 이번 발생의
// message로 그대로 재생하면 이번 발생과 무관한(심지어 이미 씬에 없는) 노드
// 이름이 "방금 일어난 일"인 것처럼 나온다. 그래서 이 둘을 분리한다:
//   - message는 언제나 "지금 이 순간 실제로 일어난 일"이다 (이번 호출에
//     넘어온 문장 그대로, book 히트 여부와 무관하게).
//   - priorAnalysis는 book 히트일 때만, "이 자리에서 과거에 있었던 분석"을
//     참고용으로 함께 들고 있다. 캐시 미스(최초 발생)면 빈 문자열이다.
struct DiagRecord {
    DiagSeverity severity = DiagSeverity::Info;
    std::string message;          // 실제로 출력된(또는 출력될) 문장. 언제나 "지금" 일어난 일.
    std::string errorHash;        // Error 심각도에서만 채워진다. hashError()의 결과.
    // Error 심각도에서만 채워진다. hashError()에 넘긴 원문 사이트 태그
    // (errorHash는 그 다이제스트일 뿐이다 -- ErrorHash.h 계약). 저널이
    // 저장/복원하는 것과 같은 원문 문자열이므로, 지난 비정상 종료들의
    // 관측(CrashAdjacency::appearancesByTag, 사이트 태그 원문으로 키가
    // 잡힌다)에 대고 이 레코드를 찾을 때는 반드시 이 필드로 조회해야 한다.
    // errorHash로 조회하면 다이제스트 대 원문이라 절대 맞아떨어지지 않는다.
    std::string siteTag;
    DgContext context;             // onfix가 채운다. 없으면 전부 빈 문자열.
    std::string remedy;            // book에 등록된 해법. 없으면 빈 문자열.
    bool servedFromBook = false;  // book 캐시로 즉답했으면 true.
    // book 히트일 때 그 항목의 analysis(과거 분석 텍스트). 캐시 미스면 빈
    // 문자열이다. message를 덮어쓰지 않는다 -- 이번 발생의 구체적 사실과
    // 과거 발생의 분석은 서로 다른 발생의 텍스트이므로 뒤섞이면 안 된다.
    std::string priorAnalysis;
    // 1부터 시작해 레코드마다 1씩 오르는 순번. 정렬·접기의 유일한 기준이다.
    std::uint64_t sequence = 0;
    // Unix epoch 밀리초. 사람에게 보여주기 위한 값이며, 순서를 정하는 어떤
    // 판단도 이것을 읽지 않는다 -- 벽시계는 NTP 보정이나 서머타임으로 뒤로
    // 갈 수 있고, 그때 순서가 흔들리면 연쇄의 앞뒤가 뒤집혀 원인 분석이
    // 통째로 반대가 된다. 형식화는 표시하는 쪽(Python)이 로컬 시간대로 한다.
    std::uint64_t timestampMs = 0;
    // 이 발생에 대한 구조화된 해법. 없으면 RemedyActionKind::None(기본값).
    // book에서 오지 않는다 -- 위 RemedyAction.h의 주석 참고. 실패가 일어난
    // 자리(MaroCommands.cpp)가 이 발생의 살아있는 씬 상태로 직접 채운다.
    RemedyAction remedyAction;
};

}  // namespace maro
