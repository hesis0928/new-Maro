#include "maro_diag/Journal.h"

#include <nlohmann/json.hpp>

namespace maro {

// 리뷰 Finding: 예전에는 이 두 함수가 JournalWriter.cpp에 정의되어 있었다 --
// JournalReader.cpp는 severityFromJournalName()을 부르므로, 리더의 번역
// 단위가 라이터의 번역 단위에 링크되어야 했다. 저널 파일 하나를 놓고 "쓰는
// 쪽 어휘"와 "읽는 쪽 어휘"가 서로 다른 소유자에게 매여 있는 것은 어색한
// 결합이었다 -- 이 둘은 어느 한쪽의 것이 아니라 저널 형식 자체의 어휘다.
// Journal.h가 이미 그 형식의 다른 상수들(kJournalFileStem 등)을 담는
// 자리이므로, 구현도 여기 Journal.cpp로 옮긴다.
const char* severityToJournalName(DiagSeverity severity) {
    switch (severity) {
        case DiagSeverity::Info: return "info";
        case DiagSeverity::Warn: return "warn";
        case DiagSeverity::DevInfo: return "devInfo";
        case DiagSeverity::Error: return "error";
    }
    return "unknown";
}

DiagSeverity severityFromJournalName(const std::string& name) {
    if (name == "warn") return DiagSeverity::Warn;
    if (name == "devInfo") return DiagSeverity::DevInfo;
    if (name == "error") return DiagSeverity::Error;
    return DiagSeverity::Info;
}

// Journal.h의 선언 주석 참고: JournalWriter의 회전과 JournalReader의 파싱이
// 공유하는 유일한 "이 줄이 무엇인가" 판정. 실제로 JSON을 파싱한다 -- 부분
// 문자열 검색과 달리 키 순서나 공백 같은 서식에 영향받지 않는다.
JournalLineKind classifyJournalLine(const std::string& rawLine) {
    nlohmann::json j;
    try {
        j = nlohmann::json::parse(rawLine);
    } catch (...) {
        return JournalLineKind::Unknown;
    }

    try {
        const std::string kind = j.value("kind", std::string());
        if (kind == "session") {
            const std::string event = j.value("event", std::string());
            if (event == "open") return JournalLineKind::SessionOpen;
            if (event == "close") return JournalLineKind::SessionClose;
            // "open"도 "close"도 아닌 event 값(오타, 미래의 새 값)은 세션을
            // 조용히 깨끗한 종료로도, 새 세션의 시작으로도 뒤집으면 안 된다.
            return JournalLineKind::Unknown;
        }
        if (kind == "record") return JournalLineKind::Record;
        if (kind == "suppressed") return JournalLineKind::Suppressed;
    } catch (...) {
        // kind/event가 기대한 타입이 아니거나(예: 숫자) 줄 자체가 객체가
        // 아니면(예: 알몸 스칼라 줄, j.value()가 그때 타입 예외를 던진다)
        // 이 줄만 Unknown으로 버린다.
        return JournalLineKind::Unknown;
    }
    return JournalLineKind::Unknown;
}

}  // namespace maro
