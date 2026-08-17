#include "maro_diag/JournalWriter.h"

#include <algorithm>
#include <sstream>
#include <vector>

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

void JournalWriter::flushSuppressed(const std::string& siteTag, TagBudget& budget,
                                     std::uint64_t timestampMs) {
    if (budget.suppressed == 0) return;
    // 이 dump()도 writeRecord의 try 안에서만 불린다 -- siteTag(여기서는 억제
    // 키)가 유효하지 않은 UTF-8이면 여기서 던질 수 있고, 그 예외는 writeRecord
    // 전체를 감싸는 catch로 흡수되어야 Maya 콜백까지 새 나가지 않는다.
    nlohmann::json j;
    j["kind"] = "suppressed";
    j["t"] = timestampMs;
    j["tag"] = siteTag;
    j["count"] = budget.suppressed;
    writeLine(j.dump());
    budget.suppressed = 0;
}

void JournalWriter::writeRecord(std::uint64_t sequence, std::uint64_t timestampMs,
                                 DiagSeverity severity, const std::string& siteTag,
                                 const std::string& message) {
    if (!out_.is_open()) return;

    // siteTag와 message는 호출자가 주는 임의의 문자열이다 -- Windows API나
    // ROS 페이로드에서 그대로 올 수 있어 유효한 UTF-8이라는 보장이 없다.
    // BookStore.cpp의 appendToSpill과 같은 모양: 예산 판단부터 JSON 직렬화,
    // 쓰기까지 함수 본문 전체를 하나의 try로 감싼다. dump()가 잘못된
    // UTF-8에서 던지는 예외가 여기서 새 나가면 Maya 콜백까지 뚫고 올라가
    // 세션을 죽인다. 줄 하나를 잃는 것은 괜찮다.
    try {
        // 억제는 태그별로 센다. 태그가 없는 레코드(에러가 아닌 것)는 심각도와
        // 메시지 첫 줄을 키로 삼는다 -- 같은 문장이 반복되는 경고가 실제
        // 억제 대상이기 때문이다.
        std::string key = siteTag;
        if (key.empty()) {
            const std::size_t cut = message.find('\n');
            key = std::string(severityToJournalName(severity)) + ":" +
                  (cut == std::string::npos ? message : message.substr(0, cut));
        }

        TagBudget& budget = budgets_[key];
        if (timestampMs < budget.windowStartMs ||
            timestampMs - budget.windowStartMs >= kJournalSuppressionWindowMs) {
            // 새 창이다. 지난 창에서 생략한 것이 있으면 먼저 알린다.
            flushSuppressed(key, budget, timestampMs);
            budget.windowStartMs = timestampMs;
            budget.written = 0;
        }

        if (budget.written >= kJournalMaxLinesPerTagPerWindow) {
            ++budget.suppressed;
            return;
        }
        ++budget.written;

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

void JournalWriter::rotate(const std::filesystem::path& path) {
    try {
        std::error_code ec;
        if (!std::filesystem::exists(path, ec)) return;

        std::vector<std::string> lines;
        {
            std::ifstream in(path, std::ios::binary);
            if (!in.is_open()) return;
            std::string line;
            while (std::getline(in, line)) {
                if (!line.empty() && line.back() == '\r') line.pop_back();
                lines.push_back(line);
            }
        }

        // 세션의 경계는 open 줄이다. 뒤에서부터 세어 보관 한도째 open 줄을
        // 찾고, 그 앞을 전부 버린다.
        std::vector<std::size_t> openAt;
        for (std::size_t i = 0; i < lines.size(); ++i) {
            if (lines[i].find("\"event\":\"open\"") != std::string::npos) {
                openAt.push_back(i);
            }
        }
        if (openAt.size() <= kJournalSessionsKept) return;

        const std::size_t firstKept = openAt[openAt.size() - kJournalSessionsKept];

        std::ofstream out(path, std::ios::out | std::ios::trunc | std::ios::binary);
        if (!out.is_open()) return;
        for (std::size_t i = firstKept; i < lines.size(); ++i) {
            out << lines[i] << '\n';
        }
    } catch (...) {
        // 회전에 실패해도 진단은 계속된다. 저널이 좀 길어질 뿐이다.
    }
}

}  // namespace maro
