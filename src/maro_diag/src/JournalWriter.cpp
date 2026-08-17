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
    // BookStore.cpp의 appendToSpill과 같은 모양: 직렬화까지 포함해 함수
    // 전체를 하나의 try로 감싼다. dump()는 기본적으로 잘못된 UTF-8에서
    // 던지는데, 그 예외가 여기서 새 나가면 (나중 과제에서) Maya 콜백까지
    // 뚫고 올라가 세션을 죽인다. 줄 하나를 잃는 것은 괜찮다.
    try {
        nlohmann::json j;
        j["kind"] = "session";
        j["event"] = "open";
        j["t"] = timestampMs;
        writeLine(j.dump());
    } catch (...) {
    }
}

void JournalWriter::writeSessionClose(std::uint64_t timestampMs) {
    try {
        nlohmann::json j;
        j["kind"] = "session";
        j["event"] = "close";
        j["t"] = timestampMs;
        writeLine(j.dump());
    } catch (...) {
    }
}

void JournalWriter::writeRecord(std::uint64_t sequence, std::uint64_t timestampMs,
                                 DiagSeverity severity, const std::string& siteTag,
                                 const std::string& message) {
    // siteTag와 message는 호출자가 주는 임의의 문자열이다 -- Windows API나
    // ROS 페이로드에서 그대로 올 수 있어 유효한 UTF-8이라는 보장이 없다.
    try {
        nlohmann::json j;
        j["kind"] = "record";
        j["seq"] = sequence;
        j["t"] = timestampMs;
        j["sev"] = severityToJournalName(severity);
        j["tag"] = siteTag;
        j["msg"] = message;
        // dump()가 개행과 따옴표를 이스케이프하므로 한 줄 = 한 항목이 유지된다.
        writeLine(j.dump());
    } catch (...) {
    }
}

}  // namespace maro
