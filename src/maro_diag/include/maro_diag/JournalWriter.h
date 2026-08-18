#pragma once

#include <cstdint>
#include <filesystem>
#include <fstream>
#include <string>
#include <unordered_map>
#include <vector>

#include "maro_diag/DiagRecord.h"

namespace maro {

// 저널에 한 줄씩 덧붙이는 쓰기 전용 핸들. 경로 하나만 알고 Maya는 모른다 --
// 그래서 억제와 회전 같은 까다로운 판단이 전부 gtest로 덮인다.
//
// fsync는 하지 않는다. 크래시 포렌식에는 필요 없기 때문이다: 파일에 append한
// 내용은 커널 페이지 캐시가 들고 있고 프로세스가 죽어도 OS가 그것을 디스크에
// 쓴다. 잃는 것은 기계 전원이 나갈 때뿐이고 그건 이 서브시스템이 대비하는
// 사건이 아니다. 매 레코드마다 fsync를 부르는 것이야말로 진짜 부담이다.
//
// 열지 못해도 던지지 않는다. 진단 경로는 지식 저장소에 닿지 못해서 실패하지
// 않는다는 규율이 저널에도 그대로 적용된다 -- 보존이 안 될 뿐 진단은 돈다.
class JournalWriter {
public:
    explicit JournalWriter(const std::filesystem::path& path);
    // Finding I2: 세션이 close 줄 없이(재로드, 또는 애초에 close를 안 부르는
    // 호출부의 실수로) 소멸되어도 그 순간까지 밀린 억제 카운트를 잃지 않는다
    // -- writeSessionClose()가 이미 같은 일을 하지만, 소멸자가 없으면 그건
    // "닫으면 플러시된다"는 보장일 뿐 "닫히지 않아도 플러시된다"는 보장이
    // 아니다. 예외가 소멸자를 빠져나가면 스택 되감기 중에는 std::terminate가
    // 불리므로 반드시 삼킨다.
    ~JournalWriter();

    bool isOpen() const { return out_.is_open(); }

    void writeSessionOpen(std::uint64_t timestampMs);
    void writeSessionClose(std::uint64_t timestampMs);
    void writeRecord(std::uint64_t sequence, std::uint64_t timestampMs,
                      DiagSeverity severity, const std::string& siteTag,
                      const std::string& message);

    // 최근 N 세션만 남기고 오래된 것부터 버린다. 파일이 없으면 아무 일도
    // 하지 않는다 -- 첫 실행이 그 상태다. 열려 있는 writer와 무관하게
    // 부를 수 있도록 정적이다: 플러그인은 이번 세션의 open 줄을 쓰기
    // **전에** 회전을 돌린다.
    //
    // 이 함수의 "세션 최근 N개" 의미는 파일 하나가 정말로 한 프로세스만의
    // 것일 때만 성립한다(Finding C1) -- 두 프로세스가 이 경로에 동시에
    // append하며 이 함수가 std::ios::trunc로 다시 쓰면, 그 사이에 다른
    // 프로세스가 쓴 내용이 통째로 사라진다. pathForProcess()로 파일을
    // 나누면 그 전제가 다시 성립한다.
    //
    // 리뷰 Finding I2: 그래서 이 함수는 **자기 파일에만** 불러야 한다.
    // 예전에는 rotateAll()이 디렉터리 안의 모든 파일에 이것을 불렀는데,
    // 그건 위 전제를 스스로 깨는 일이었다 -- 남의 파일을 트렁케이트하는
    // 순간 "그 파일을 트렁케이트하는 것은 그 파일의 주인뿐"이라는 보장이
    // 사라지고, 주인이 살아서 append하는 중이라면 읽기와 트렁케이트 사이에
    // 들어온 줄이 조용히 사라진다(MSVC의 ofstream 공유 모드는 그 동시 열기를
    // 막지 않는다). 지금은 rotateAll()이 ownProcessId의 파일에만 이것을
    // 부른다.
    static void rotate(const std::filesystem::path& path);

    // Finding C1: 이 프로세스가 써야 할 저널 파일 경로. directory 안에
    // "<stem>.<processId>.jsonl" 모양의 이름을 만든다. 서로 다른 프로세스는
    // (정의상 동시에 살아 있는 동안은) 서로 다른 processId를 받으므로 절대
    // 같은 파일에 동시에 쓰지 않는다 -- 그래서 한 파일 안에서는 "쓰는 이가
    // 하나"라는 rotate()/parseJournal의 원래 전제가 다시 정확히 성립한다.
    // (같은 pid가 한참 뒤에 재사용되어 같은 이름을 다시 쓰는 것은 안전하다
    // -- 그때는 원래 쓰던 프로세스가 이미 죽어 있으므로 동시 쓰기가 아니라
    // AppendsInsteadOfTruncating과 같은 모양의 순차적 재사용일 뿐이다.)
    static std::filesystem::path pathForProcess(const std::filesystem::path& directory,
                                                 std::uint64_t processId);

    // pathForProcess()의 역함수. path의 파일 이름이 "<stem>.<pid>.jsonl"
    // 모양이면 그 pid를 processIdOut에 넣고 true를, 아니면(그 모양이
    // 아니거나 숫자가 uint64에 안 들어가면) processIdOut을 건드리지 않고
    // false를 돌려준다.
    //
    // 리뷰 Finding C1(리브니스): 파일 이름의 pid는 단순한 이름표가 아니라
    // "이 파일의 마지막 미종료 세션이 크래시인가, 아직 도는 중인가"를 가르는
    // 유일한 단서다 -- 파일 내용만으로는 그 둘이 완전히 같은 모양이기
    // 때문이다(둘 다 close 줄이 없다). 그 판정을 하려면 이름에서 pid를 도로
    // 꺼낼 수 있어야 한다(JournalReader의 countCrashAdjacencyAcrossJournalFiles
    // 참고). listJournalFiles()가 파일을 고르는 판정도 이 함수 하나를 쓴다 --
    // "저널 파일인가"와 "그 저널 파일의 pid는 무엇인가"가 서로 다른 규칙을
    // 갖게 되면, 집계 대상인데 pid를 못 읽는(=리브니스 판정을 조용히 건너뛰는)
    // 파일이 생긴다.
    static bool processIdFromPath(const std::filesystem::path& path,
                                   std::uint64_t& processIdOut);

    // directory 안에서 kJournalFileStem으로 시작하는 프로세스별 저널 파일을
    // 전부 나열한다. 읽는 쪽(집계)과 rotateAll()이 이 목록을 공유한다.
    // directory가 없으면 빈 목록을 돌려준다 -- 첫 실행이 그 상태다.
    static std::vector<std::filesystem::path> listJournalFiles(
        const std::filesystem::path& directory);

    // Finding C1: directory 안의 프로세스별 저널 파일 전체에 걸쳐 보관
    // 총량을 kJournalSessionsKept "세션"만큼으로 되돌린다 -- 파일을
    // 나눴다고 해서 예전의 "보관 한도 10세션"이 "파일마다 10세션"으로
    // 슬그머니 불어나면 안 되기 때문이다(파일이 여러 개면 그건 더 이상
    // 유계가 아니다). ownProcessId(=이 프로세스)의 파일은 먼저 rotate()로
    // 스스로의 세션 상한을 지키고(그 판단은 파일 안 open/close 줄 위치만
    // 본다, 시각을 읽지 않는다), 그다음 파일들을 마지막 수정 시각 기준으로
    // 최신 순으로 훑으며 세션을 누적해 한도를 넘기는 지점부터는 파일을
    // 통째로 지운다.
    //
    // 리뷰 Finding I2 -- 이 함수가 남의 파일에 하는 일의 계약: **파일을
    // 읽거나(세션 수 세기) 통째로 지우는 것뿐이다. 내용을 다시 쓰지
    // 않는다.** 트렁케이트 후 재작성(rotate())은 오직 자기 파일에만 한다 --
    // 살아 있는 다른 프로세스가 append 중인 파일을 읽고-트렁케이트-재작성하면
    // 그 사이에 들어온 줄이 조용히 사라지기 때문이다. 통째 삭제는 이 경합이
    // 없다: Windows에서 살아 있는 주인이 그 파일을 열어 둔 채면(공유 모드에
    // FILE_SHARE_DELETE가 없으므로) remove()가 그냥 실패하고, 그 error_code는
    // 아래 구현이 삼킨다 -- 반쯤 지워진 파일 같은 중간 상태가 없다.
    //
    // 그래서 남의 파일이 자기 세션 상한(kJournalSessionsKept)을 넘겨도 이
    // 함수는 그 파일을 잘라 주지 않는다. 그 파일은 다음에 그 주인이 자기
    // openJournal()에서 스스로 자를 것이고, 주인이 다시는 안 돌아오면 이
    // 함수의 총량 한도가 언젠가 그 파일을 통째로 지운다 -- 어느 쪽이든
    // 유계이며, 그 대가로 남의 데이터를 잃을 수 있는 창이 사라진다.
    //
    // 마지막 수정 시각을 쓰는 것은 진단 레코드/세션의 정상·비정상 판정이나
    // 순서에 쓰는 그 "타임스탬프를 읽지 않는다"는 규율과는 다른 자리다:
    // 그 규율은 한 세션 안에서 레코드가 어느 순서인지, 어느 세션이 닫혔는지
    // 같은 진단적 결론을 지킨다(그건 여기서도 여전히 open/close 줄 위치와
    // sequence만 본다, 이 함수가 손대는 파일 각각의 내용은 그대로 둔다).
    // 여기서 고르는 것은 그런 결론이 이미 확정된 "파일 전체"를 지울지
    // 말지일 뿐이다 -- 시계가 조금 어긋나 있어도 최악의 경우 지울 파일을
    // 하나 잘못 고르는 정도이지, 남는 파일들의 진단 결론이 틀리게 되지는
    // 않는다.
    //
    // 리뷰 Finding I1: 그 마지막 수정 시각은 rotate()를 부르기 **전에**
    // 읽는다. rotate()가 실제로 다시 쓴 파일은 그 순간 mtime이 "지금"이
    // 되므로, 뒤에 읽으면 방금 잘린 오래된 파일이 진짜 최신 파일보다 앞으로
    // 정렬되어 -- 살려야 할 최신 파일이 대신 지워진다. 위 문단의 "최악의
    // 경우 하나 잘못 고르는 정도"는 시계가 어긋난 경우를 말하는 것이지,
    // 우리 스스로 mtime을 뒤집어 놓고 그것을 읽는 경우가 아니다.
    static void rotateAll(const std::filesystem::path& directory,
                           std::uint64_t ownProcessId);

    JournalWriter(const JournalWriter&) = delete;
    JournalWriter& operator=(const JournalWriter&) = delete;

private:
    void writeLine(const std::string& json);

    // Finding I2: writeSessionClose()와 소멸자가 공유하는 실제 작업 -- 남아
    // 있는 모든 태그의 밀린 억제 카운트를 지금 이 시각으로 흘린다.
    void flushAllPendingSuppressed(std::uint64_t timestampMs);

    // 태그별 억제 예산. 창의 시작 시각과 그 창에서 이미 쓴 줄 수를 함께
    // 들고 있다. 서로 다른 태그가 서로의 예산을 잡아먹지 않는 것이
    // 핵심이다 -- 병렬 평가에서는 여러 노드의 경고가 번갈아 들어오므로
    // "연속된 같은 태그"를 기준으로 삼으면 억제가 한 번도 안 걸린다.
    struct TagBudget {
        std::uint64_t windowStartMs = 0;
        std::size_t written = 0;
        std::size_t suppressed = 0;
    };

    // budgetKey는 budgets_의 키다 -- 태그가 있는 레코드는 사이트 태그
    // 원문이지만, 태그 없는 레코드는 심각도+메시지 첫 줄이다(writeRecord
    // 참고). 이름을 siteTag가 아니라 budgetKey로 둔 것 자체가 계약이다:
    // 이 값을 record 줄의 "tag" 필드와 같은 JSON 키로 실으면(예전에 실제로
    // "tag"였다) 두 서로 다른 뜻이 같은 이름을 쓰게 된다.
    void flushSuppressed(const std::string& budgetKey, TagBudget& budget,
                          std::uint64_t timestampMs);

    // budgets_가 kJournalMaxBudgetKeys에 닿으면 호출된다. 창이 이미 닫힌
    // (timestampMs 기준으로 더 이상 새 줄을 억제할 이유가 없는) 항목을 지운다.
    // 지우기 전에 그 항목에 밀린 suppressed 카운트가 있으면 반드시 flush한다
    // -- 그렇지 않으면 "N줄 생략" 안내가 사용자에게 영영 전달되지 않는다
    // (그 항목의 키를 다시는 안 쓸 수도 있으므로, 다음 번 그 키로 쓸 때
    // 플러시되기를 기다릴 수 없다). 아직 창이 열려 있는 항목은 지우지
    // 않는다 -- 지우면 그 태그의 억제가 조용히 리셋되어 예산을 다시 받는
    // 것과 같아지기 때문이다.
    void sweepStaleBudgets(std::uint64_t timestampMs);

    // 태그(또는 태그 없는 레코드의 심각도+메시지) -> 억제 예산. 상한은
    // kJournalMaxBudgetKeys(Journal.h)이고, 거기 닿으면 sweepStaleBudgets가
    // 창이 닫힌 항목부터 정리한다. 그래도 동시에 활성 상태(창이 아직 열린)인
    // 키가 상한보다 많으면 그 순간만큼은 맵이 상한을 넘을 수 있다 -- 활성
    // 예산을 지우는 것은 억제 자체를 무너뜨리므로 그 경우엔 지우지 않는다.
    //
    // 이 초과는 시간으로 유계다: 상한 위로 맵을 밀어올린 그 활성 키들도
    // 각자 자신의 창(kJournalSuppressionWindowMs, 1초) 하나가 닫히고 나면
    // "창이 닫힌 항목"이 되어 다음 sweepStaleBudgets 기회(=다음 새 키가
    // 다시 상한을 건드리는 시점)에서 정리 대상이 된다 -- 즉 맵이 상한 위에
    // 머무는 기간은 그 초과를 만든 키들의 억제 창 하나만큼이 최대치다.
    // MaroDiag.h가 기록 벡터에 대해 안고 있는, 시간과 무관하게 계속 자라는
    // 무한 성장과는 다른 종류의(그리고 훨씬 얌전한) 초과다.
    std::unordered_map<std::string, TagBudget> budgets_;

    // Finding I2: 소멸자가 마지막으로 흘리는 억제 줄에 쓸 "t"값. 소멸자는
    // 호출자가 시각을 넘겨줄 방법이 없으므로(닫는 쪽이 부르는 게 아니라
    // 스코프를 벗어나며 저절로 불린다), open/record/close 중 가장 최근에
    // 실제로 받은 timestampMs를 재사용한다 -- 새 시각을 읽어오지 않는다
    // (그건 벽시계를 이 라이브러리 안으로 끌어들이는 것이고, 이 값은 어떤
    // 순서 판단에도 쓰이지 않고 오직 마지막 안내 줄의 표시용 필드로만
    // 쓰인다).
    std::uint64_t lastTimestampMs_ = 0;

    std::ofstream out_;
};

}  // namespace maro
