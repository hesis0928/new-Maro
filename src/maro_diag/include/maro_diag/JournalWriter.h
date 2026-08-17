#pragma once

#include <cstdint>
#include <filesystem>
#include <fstream>
#include <string>
#include <unordered_map>

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
    static void rotate(const std::filesystem::path& path);

    JournalWriter(const JournalWriter&) = delete;
    JournalWriter& operator=(const JournalWriter&) = delete;

private:
    void writeLine(const std::string& json);

    // 태그별 억제 예산. 창의 시작 시각과 그 창에서 이미 쓴 줄 수를 함께
    // 들고 있다. 서로 다른 태그가 서로의 예산을 잡아먹지 않는 것이
    // 핵심이다 -- 병렬 평가에서는 여러 노드의 경고가 번갈아 들어오므로
    // "연속된 같은 태그"를 기준으로 삼으면 억제가 한 번도 안 걸린다.
    struct TagBudget {
        std::uint64_t windowStartMs = 0;
        std::size_t written = 0;
        std::size_t suppressed = 0;
    };

    void flushSuppressed(const std::string& siteTag, TagBudget& budget,
                          std::uint64_t timestampMs);

    std::unordered_map<std::string, TagBudget> budgets_;

    std::ofstream out_;
};

}  // namespace maro
