#pragma once

#include <cstdint>
#include <string>
#include <unordered_map>
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

// 비정상 종료 직전에 어떤 사이트 태그가 반복해서 나타났는지에 대한 **관측**.
//
// 인과가 아니다. 크래시 직전에 있었다는 것이 크래시를 일으켰다는 뜻은
// 아니며, 무관한 진단이 우연히 자주 마지막에 있을 수도 있다. 그래서 이
// 구조체는 "몇 번 중 몇 번"이라는 사실만 담고 원인을 단정하지 않는다.
//
// 이것은 ghost가 아니다. ghost의 실제 일 -- 셧다운 신호를 받아 그 시점에
// 파편을 저장하고 다음 기동에 조립하는 것 -- 은 Layer C다. 여기서 하는
// 것은 사후에 저널을 세는 것뿐이고, 프로세스가 죽는 순간에 대해서는
// 아무것도 모른다.
struct CrashAdjacency {
    // 보관 중인 저널에서 비정상으로 끝난 세션의 수. 신호의 분모다.
    std::size_t abnormalSessionCount = 0;
    // 사이트 태그 -> 그 태그가 마지막 구간에 있었던 비정상 세션의 수.
    // 한 세션은 한 표다 -- 한 세션에서 몇 번 나왔는지는 세지 않는다.
    // 안 그러면 폭주한 태그 하나가 모든 세션의 표를 독식한다.
    std::unordered_map<std::string, std::size_t> appearancesByTag;
};

CrashAdjacency countCrashAdjacentTags(const std::vector<JournalSession>& sessions);

// 리뷰 Finding C1: 저널이 프로세스별로 여러 파일로 나뉘므로(JournalWriter::
// pathForProcess), 지난 세션들의 관측은 그 파일들을 각각 파싱한 결과를 합쳐야
// 전체 그림이 된다. 파일 하나하나는 이미 "쓰는 이가 하나"라는 전제 위에서
// 정확하므로 합치는 것은 단순 덧셈이다 -- 세션 하나는 정확히 자기 파일
// 안에서만 등장하므로 두 파일에 걸쳐 같은 세션이 중복 집계될 일이 없다.
void mergeCrashAdjacency(CrashAdjacency& target, const CrashAdjacency& addition);

}  // namespace maro
