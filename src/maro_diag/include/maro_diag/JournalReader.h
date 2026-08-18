#pragma once

#include <cstdint>
#include <filesystem>
#include <functional>
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
//
// 다만 "파일 하나하나가 이미 정확하다"는 것은 **한 파일 안에서 세션 경계와
// 소속이 뒤섞이지 않는다**는 뜻이지, 그 파일의 마지막 세션이 크래시인지까지
// 파일만 보고 알 수 있다는 뜻이 아니다 -- 그 판정에는 파일 밖의 사실(주인
// pid가 아직 사는가)이 필요하다. 아래 countCrashAdjacencyAcrossJournalFiles가
// 그 사실을 물어본 뒤에 이 덧셈을 한다.
void mergeCrashAdjacency(CrashAdjacency& target, const CrashAdjacency& addition);

// pid가 가리키는 프로세스가 **지금** 살아 있는지 묻는 질문.
//
// 리뷰 Finding C1(리브니스): maro_diag는 Maya도 OS도 모른다는 규율이 있으므로
// (그래서 이 판단들이 전부 gtest로 덮인다) 실제 판정은 여기서 하지 않고
// 플러그인 쪽이 주입한다 -- Windows에서는 OpenProcess + WaitForSingleObject
// (MaroDiag.cpp의 isProcessRunning). 이 seam은 테스트를 위한 장식이 아니라
// 계층 경계 그 자체다: 진짜 프로세스를 띄우지 않고 "살아 있는 pid"와 "죽은
// pid" 양쪽 가지를 모두 돌려 볼 수 있는 유일한 방법이기도 하다.
using ProcessLivenessFn = std::function<bool(std::uint64_t processId)>;

// directory 안의 프로세스별 저널 파일을 전부 읽어 지난 세션들의 관측을
// 합친다(파일 하나하나는 mergeCrashAdjacency의 전제대로 서로 독립이다).
//
// 리뷰 Finding C1(리브니스): 파일의 **마지막** 세션이 close 줄 없이 끝나
// 있고 그 파일의 주인 pid가 아직 살아 있으면, 그 세션은 크래시가 아니라
// **아직 도는 중**이다 -- 두 상태는 파일 내용만으로는 완전히 같은 모양이라
// (둘 다 close 줄이 없다) 파일 밖에서 물어보는 수밖에 없다. 그 세션은
// abnormalSessionCount에도 appearancesByTag에도 넣지 않는다. 이것을 안 하면
// 아티스트가 Maya 창을 두 개 띄우는 것만으로 크래시 문턱이 넘어간다:
// 두 번째 창의 openJournal()이 첫 번째 창의(정상적으로 아직 안 닫힌) 파일을
// 읽고 그것을 크래시로 센다.
//
// **마지막** 세션만 봐주는 이유: 한 파일 안에서 아직 도는 중일 수 있는
// 세션은 정의상 마지막 하나뿐이다. 그 앞의 미종료 세션들은 그 pid의 이전
// 화신(化身)이 실제로 죽었기 때문에 남은 것이므로 진짜 크래시다.
//
// pid 재사용: 죽은 프로세스의 pid를 뒤에 다른 프로세스가 물려받았으면 이
// 판정은 "살아 있다"로 나오고, 진짜 크래시 하나를 이번 한 번 놓친다. 그
// 방향이 안전한 쪽이다 -- 이 신호는 인과가 아니라 상관이고(CrashAdjacency
// 주석), 없는 크래시를 지어내면 사용자에게 잘못된 원인을 지목하지만
// 있는 크래시를 한 번 놓치면 다음 크래시에서 다시 세어진다.
CrashAdjacency countCrashAdjacencyAcrossJournalFiles(
    const std::filesystem::path& directory, const ProcessLivenessFn& isProcessAlive);

}  // namespace maro
