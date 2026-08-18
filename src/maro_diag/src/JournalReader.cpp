#include "maro_diag/JournalReader.h"

#include <fstream>
#include <sstream>
#include <unordered_set>

#include <nlohmann/json.hpp>

#include "maro_diag/Journal.h"
#include "maro_diag/JournalWriter.h"

namespace maro {

std::vector<JournalSession> parseJournal(const std::string& text) {
    std::vector<JournalSession> sessions;
    std::istringstream in(text);
    std::string line;

    while (std::getline(in, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty()) continue;

        // 리뷰 Finding (세 개의 경쟁하는 정의): 이 줄이 세션 시작/종료/레코드/
        // 억제 안내/알 수 없음 중 무엇인지는 classifyJournalLine(Journal.h/
        // .cpp) 하나로 판정한다 -- JournalWriter::rotate()/countSessionOpens()
        // 도 정확히 같은 함수로 같은 판정을 내린다. 예전에는 이 판정 로직이
        // 여기 따로(실제 JSON 파싱으로) 있었고 라이터 쪽은 부분 문자열
        // 검색으로 독립적으로 있었다 -- 우연히 일치했을 뿐, 둘 중 하나만
        // 바뀌어도 조용히 어긋날 수 있었다.
        const JournalLineKind kind = classifyJournalLine(line);
        if (kind == JournalLineKind::SessionOpen) {
            sessions.emplace_back();
            continue;
        }
        if (kind == JournalLineKind::SessionClose) {
            if (!sessions.empty()) sessions.back().endedCleanly = true;
            continue;
        }
        if (kind != JournalLineKind::Record) continue;  // suppressed/Unknown은 레코드가 아니다
        if (sessions.empty()) continue;                 // open 줄 앞의 레코드는 버린다

        nlohmann::json j;
        try {
            j = nlohmann::json::parse(line);
        } catch (...) {
            // classifyJournalLine이 이미 한 번 파싱했지만, 필드 값을 꺼내려면
            // 다시 파싱해야 한다(그쪽은 종류만 돌려주고 파싱된 객체 자체는
            // 넘기지 않는다 -- Journal.h가 nlohmann을 모르는 공개 헤더이기
            // 때문이다). 여기서 실패할 리는 없다(방금 성공적으로 분류됐으므로)
            // 지만, 방어적으로 그대로 건너뛴다.
            continue;
        }

        try {
            JournalRecord rec;
            rec.sequence = j.value("seq", std::uint64_t{0});
            rec.timestampMs = j.value("t", std::uint64_t{0});
            rec.severity = severityFromJournalName(j.value("sev", std::string()));
            rec.siteTag = j.value("tag", std::string());
            rec.message = j.value("msg", std::string());
            sessions.back().records.push_back(std::move(rec));
        } catch (...) {
            // 타입이 어긋난 줄도 그 줄만 버린다.
        }
    }
    return sessions;
}

CrashAdjacency countCrashAdjacentTags(const std::vector<JournalSession>& sessions) {
    CrashAdjacency adjacency;

    for (const JournalSession& session : sessions) {
        if (session.endedCleanly) continue;
        ++adjacency.abnormalSessionCount;

        // 마지막 구간만 본다. 전체가 구간보다 짧으면 전부를 본다.
        const std::size_t total = session.records.size();
        const std::size_t start =
            total > kJournalTailRecordsForSignal ? total - kJournalTailRecordsForSignal : 0;

        // 한 세션은 한 표 -- 세션 안에서 중복을 먼저 없앤다.
        std::unordered_set<std::string> seenInThisSession;
        for (std::size_t i = start; i < total; ++i) {
            const std::string& tag = session.records[i].siteTag;
            if (tag.empty()) continue;  // 신호는 사이트 태그로 지목되는 실패에만 붙는다
            seenInThisSession.insert(tag);
        }
        for (const std::string& tag : seenInThisSession) {
            ++adjacency.appearancesByTag[tag];
        }
    }
    return adjacency;
}

void mergeCrashAdjacency(CrashAdjacency& target, const CrashAdjacency& addition) {
    target.abnormalSessionCount += addition.abnormalSessionCount;
    for (const auto& [tag, count] : addition.appearancesByTag) {
        target.appearancesByTag[tag] += count;
    }
}

CrashAdjacency countCrashAdjacencyAcrossJournalFiles(
    const std::filesystem::path& directory, const ProcessLivenessFn& isProcessAlive) {
    CrashAdjacency aggregate;
    // 파일 하나가 안 읽혀도 나머지를 포기하지 않는다 -- parseJournal이 깨진
    // 줄 하나 때문에 나머지를 버리지 않는 것과 같은 규율이다. 던지지도
    // 않는다: 이 함수의 호출자는 플러그인 로드 경로(BoadMaro::openJournal)다.
    for (const std::filesystem::path& file : JournalWriter::listJournalFiles(directory)) {
        try {
            std::ifstream in(file, std::ios::binary);
            if (!in.is_open()) continue;
            std::ostringstream ss;
            ss << in.rdbuf();

            std::vector<JournalSession> sessions = parseJournal(ss.str());

            // Finding C1(리브니스): 주인이 아직 살아 있으면 이 파일의 마지막
            // 미종료 세션은 크래시가 아니라 진행 중인 세션이다 -- 세지
            // 않는다(JournalReader.h의 자세한 논거 참고). 그 앞의 미종료
            // 세션들은 그대로 둔다: 한 파일에서 "아직 도는 중"일 수 있는
            // 세션은 마지막 하나뿐이다.
            //
            // 이 프로세스 자신의 파일도 같은 규칙이 그대로 적용된다 -- 자기
            // pid는 당연히 살아 있으므로 자기 파일의 마지막 미종료 세션은
            // 자동으로 빠진다. 지금은 그 자리에 (이번 세션의 open 줄을 아직
            // 쓰기 전이라) 아무것도 없는 것이 보통이지만, pid가 재사용되어
            // 옛 화신이 남긴 파일에 이어 쓰는 경우에는 그 옛 크래시 하나를
            // 놓친다 -- 위 pid 재사용 문단이 말하는, 지어내지 않고 놓치는
            // 쪽의 안전한 실패다.
            std::uint64_t ownerPid = 0;
            if (!sessions.empty() && !sessions.back().endedCleanly && isProcessAlive &&
                JournalWriter::processIdFromPath(file, ownerPid) && isProcessAlive(ownerPid)) {
                sessions.pop_back();
            }

            mergeCrashAdjacency(aggregate, countCrashAdjacentTags(sessions));
        } catch (...) {
        }
    }
    return aggregate;
}

}  // namespace maro
