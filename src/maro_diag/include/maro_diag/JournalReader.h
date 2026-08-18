#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "maro_diag/DiagRecord.h"

namespace maro {

// 저널에서 되살린 진단 하나. 인메모리 DiagRecord와 달리 컨텍스트나 book
// 관련 필드를 담지 않는다 -- 저널은 크래시를 건너 무슨 일이 있었는지를
// 보존할 뿐, 그 시점의 분석까지 복원하지는 않는다.
struct JournalRecord {
    std::uint64_t sequence = 0;
    std::uint64_t timestampMs = 0;
    DiagSeverity severity = DiagSeverity::Info;
    std::string siteTag;
    std::string message;
};

struct JournalSession {
    std::vector<JournalRecord> records;
    // 종료 줄로 끝났으면 true. false면 비정상 종료다 -- 다음 open 줄에
    // 밀려 끊겼거나 파일 끝에서 잘렸다는 뜻이고, 후자가 실제 크래시의
    // 가장 흔한 모양이다. 타임아웃을 추측할 필요가 없다는 것이 이 판정의
    // 핵심 이점이다.
    bool endedCleanly = false;
};

// 저널 텍스트를 세션으로 가른다. 세션의 경계는 open 줄이다.
//
// 깨진 줄은 버리되 그 줄 때문에 나머지를 포기하지 않는다 -- 크래시가
// 마지막 줄을 반쯤 쓴 채 끝냈을 수 있고, 그 앞의 온전한 줄들이 정확히
// 알고 싶은 것이기 때문이다.
std::vector<JournalSession> parseJournal(const std::string& text);

}  // namespace maro
