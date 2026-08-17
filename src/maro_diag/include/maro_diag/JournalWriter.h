#pragma once

#include <cstdint>
#include <filesystem>
#include <fstream>
#include <string>

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

    JournalWriter(const JournalWriter&) = delete;
    JournalWriter& operator=(const JournalWriter&) = delete;

private:
    void writeLine(const std::string& json);

    std::ofstream out_;
};

}  // namespace maro
