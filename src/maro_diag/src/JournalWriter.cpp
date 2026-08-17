#include "maro_diag/JournalWriter.h"

#include <nlohmann/json.hpp>

#include "maro_diag/Journal.h"

namespace maro {

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

JournalWriter::JournalWriter(const std::filesystem::path& path) {
    try {
        // 부모 디렉터리가 없으면 만든다. 실패해도 던지지 않는다 -- 아래
        // open이 실패하고 isOpen()이 false로 남을 뿐이다.
        std::error_code ec;
        std::filesystem::create_directories(path.parent_path(), ec);
        out_.open(path, std::ios::out | std::ios::app | std::ios::binary);
    } catch (...) {
        // 삼킨다. 저널을 못 여는 것은 진단을 멈출 이유가 되지 않는다.
    }
}

void JournalWriter::writeLine(const std::string& json) {
    if (!out_.is_open()) return;
    try {
        out_ << json << '\n';
        // flush는 한다 -- 버퍼가 프로세스와 함께 사라지면 크래시 직전
        // 몇 줄을 잃는데, 그 몇 줄이 정확히 알고 싶은 것이다. flush는
        // 커널에 넘기는 것일 뿐 fsync가 아니라서 디스크 대기가 없다.
        out_.flush();
    } catch (...) {
    }
}

void JournalWriter::writeSessionOpen(std::uint64_t timestampMs) {
    nlohmann::json j;
    j["kind"] = "session";
    j["event"] = "open";
    j["t"] = timestampMs;
    writeLine(j.dump());
}

void JournalWriter::writeSessionClose(std::uint64_t timestampMs) {
    nlohmann::json j;
    j["kind"] = "session";
    j["event"] = "close";
    j["t"] = timestampMs;
    writeLine(j.dump());
}

void JournalWriter::writeRecord(std::uint64_t sequence, std::uint64_t timestampMs,
                                 DiagSeverity severity, const std::string& siteTag,
                                 const std::string& message) {
    nlohmann::json j;
    j["kind"] = "record";
    j["seq"] = sequence;
    j["t"] = timestampMs;
    j["sev"] = severityToJournalName(severity);
    j["tag"] = siteTag;
    j["msg"] = message;
    // dump()가 개행과 따옴표를 이스케이프하므로 한 줄 = 한 항목이 유지된다.
    writeLine(j.dump());
}

}  // namespace maro
