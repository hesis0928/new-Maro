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
struct DiagRecord {
    DiagSeverity severity = DiagSeverity::Info;
    std::string message;          // 실제로 출력된(또는 출력될) 문장.
    std::string errorHash;        // Error 심각도에서만 채워진다. hashError()의 결과.
    DgContext context;             // onfix가 채운다. 없으면 전부 빈 문자열.
    std::string remedy;            // book에 등록된 해법. 없으면 빈 문자열.
    bool servedFromBook = false;  // book 캐시로 즉답했으면 true.
};

}  // namespace maro
