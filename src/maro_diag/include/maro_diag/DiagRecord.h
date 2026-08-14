#pragma once

#include <string>

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
    DgContext context;             // onfix가 채운다. 없으면 전부 빈 문자열.
    std::string remedy;            // book에 등록된 해법. 없으면 빈 문자열.
    bool servedFromBook = false;  // book 캐시로 즉답했으면 true.
    // book 히트일 때 그 항목의 analysis(과거 분석 텍스트). 캐시 미스면 빈
    // 문자열이다. message를 덮어쓰지 않는다 -- 이번 발생의 구체적 사실과
    // 과거 발생의 분석은 서로 다른 발생의 텍스트이므로 뒤섞이면 안 된다.
    std::string priorAnalysis;
};

}  // namespace maro
