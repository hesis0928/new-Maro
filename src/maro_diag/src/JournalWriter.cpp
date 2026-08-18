#include "maro_diag/JournalWriter.h"

#include <algorithm>
#include <cctype>
#include <sstream>
#include <vector>

#include <nlohmann/json.hpp>

#include "maro_diag/Journal.h"

namespace maro {

namespace {

// Finding C1: "<stem>.<pid>.jsonl" 모양인지 확인한다. 가운데 조각이 전부
// 숫자여야 한다 -- 그래야 이 디렉터리에 있을 수 있는 다른 파일들
// (maro_knowledge.jsonl류, 임의의 사용자 파일)을 실수로 저널로 집계하거나
// 지우지 않는다.
bool isPerProcessJournalFile(const std::filesystem::path& path) {
    const std::string name = path.filename().string();
    const std::string prefix = std::string(kJournalFileStem) + ".";
    const std::string suffix = ".jsonl";
    if (name.size() <= prefix.size() + suffix.size()) return false;
    if (name.compare(0, prefix.size(), prefix) != 0) return false;
    if (name.compare(name.size() - suffix.size(), suffix.size(), suffix) != 0) return false;

    const std::string middle =
        name.substr(prefix.size(), name.size() - prefix.size() - suffix.size());
    if (middle.empty()) return false;
    return std::all_of(middle.begin(), middle.end(),
                        [](unsigned char c) { return std::isdigit(c) != 0; });
}

// rotate()와 같은 "open 줄 찾기" 규칙을 쓰지만, 위치가 아니라 개수만
// 필요하다(rotateAll()이 파일 전체를 통째로 지울지 판단할 때 쓴다).
std::size_t countSessionOpens(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in.is_open()) return 0;
    std::size_t count = 0;
    std::string line;
    while (std::getline(in, line)) {
        if (line.find("\"event\":\"open\"") != std::string::npos) ++count;
    }
    return count;
}

}  // namespace

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

JournalWriter::~JournalWriter() {
    // Finding I2: writeSessionClose()가 정상적으로 불렸다면 budgets_는 이미
    // 전부 flush되어(suppressed == 0) 아래 루프가 아무것도 쓰지 않는다 --
    // 그러니 이건 오직 writeSessionClose() 없이(재로드 등으로) 이 writer가
    // 소멸되는 경로만을 위한 안전망이다. 소멸자는 절대 던지면 안 된다: 스택
    // 되감기 중에 소멸자가 예외를 내면 std::terminate가 그 자리에서 불린다.
    try {
        flushAllPendingSuppressed(lastTimestampMs_);
    } catch (...) {
    }
}

void JournalWriter::flushAllPendingSuppressed(std::uint64_t timestampMs) {
    for (auto& [key, budget] : budgets_) {
        flushSuppressed(key, budget, timestampMs);
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
    lastTimestampMs_ = timestampMs;
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
    lastTimestampMs_ = timestampMs;
    try {
        // Finding I2: 아직 창이 열린 채로 세션이 끝나면, 그 창의 억제
        // 카운트는 이 close 뒤로는 영영 flush될 기회가 없다(더 쓰지 않으니
        // 같은 키로 또 쓸 일도 없고, 창이 열려 있으니 sweepStaleBudgets도
        // 손대지 않는다). 그런데 그 마지막 창이야말로 크래시 직전 1초일
        // 수 있다 -- 이 서브시스템이 정확히 보존하려는 그 구간이다. close
        // 줄을 쓰기 전에 남은 것을 전부 흘린다.
        flushAllPendingSuppressed(timestampMs);

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

void JournalWriter::sweepStaleBudgets(std::uint64_t timestampMs) {
    // flushSuppressed 자체도 dump()를 부르므로 던질 수 있다 -- 이 함수는
    // writeRecord의 try 안에서만 불려야 한다(그쪽이 흡수한다). 여기서는
    // 따로 감싸지 않는다: 이중으로 감싸면 "무엇이 어디서 흡수되는지"가
    // 흐려진다.
    for (auto it = budgets_.begin(); it != budgets_.end();) {
        TagBudget& budget = it->second;
        const bool windowClosed = timestampMs < budget.windowStartMs ||
                                   timestampMs - budget.windowStartMs >= kJournalSuppressionWindowMs;
        if (windowClosed) {
            // 지우기 전에 밀린 생략 카운트를 먼저 알린다 -- 이 키를 다시는
            // 안 쓸 수도 있으므로, 나중의 창 롤오버에서 플러시되기를 기다릴
            // 수 없다.
            flushSuppressed(it->first, budget, timestampMs);
            it = budgets_.erase(it);
        } else {
            ++it;
        }
    }
}

void JournalWriter::writeRecord(std::uint64_t sequence, std::uint64_t timestampMs,
                                 DiagSeverity severity, const std::string& siteTag,
                                 const std::string& message) {
    if (!out_.is_open()) return;
    lastTimestampMs_ = timestampMs;

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

        // budgets_는 태그(또는 메시지 첫 줄) 하나당 항목 하나다. 에러가
        // 아닌 진단은 메시지 내용을 키에 섞으므로, 동적인 내용(경로, 노드
        // 이름)을 담은 메시지가 반복해서 새 키를 만들며 무한히 자랄 수
        // 있다. 상한에 닿으면 새 키를 더 넣기 전에 창이 닫힌 항목부터
        // 정리한다.
        if (budgets_.size() >= kJournalMaxBudgetKeys) {
            sweepStaleBudgets(timestampMs);
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

std::filesystem::path JournalWriter::pathForProcess(const std::filesystem::path& directory,
                                                      std::uint64_t processId) {
    return directory /
           (std::string(kJournalFileStem) + "." + std::to_string(processId) + ".jsonl");
}

std::vector<std::filesystem::path> JournalWriter::listJournalFiles(
    const std::filesystem::path& directory) {
    std::vector<std::filesystem::path> files;
    try {
        std::error_code ec;
        if (!std::filesystem::exists(directory, ec)) return files;
        for (const auto& entry : std::filesystem::directory_iterator(directory, ec)) {
            if (ec) break;
            std::error_code isFileEc;
            if (!entry.is_regular_file(isFileEc)) continue;
            if (isPerProcessJournalFile(entry.path())) files.push_back(entry.path());
        }
    } catch (...) {
        // 목록을 못 얻어도 던지지 않는다 -- 호출자는 빈 목록을 정상적으로
        // 처리한다(회전은 아무것도 안 하고, 집계는 관측이 비게 될 뿐이다).
    }
    return files;
}

void JournalWriter::rotateAll(const std::filesystem::path& directory) {
    try {
        struct Entry {
            std::filesystem::path path;
            std::filesystem::file_time_type mtime;
        };
        std::vector<Entry> files;
        for (const std::filesystem::path& p : listJournalFiles(directory)) {
            // 파일 하나는 이제 프로세스 하나만 썼다는 전제가 성립하므로,
            // 기존 rotate()를 그대로 재사용해 그 파일 스스로의 세션 상한을
            // 먼저 지킨다.
            rotate(p);
            std::error_code mtimeEc;
            const auto mtime = std::filesystem::last_write_time(p, mtimeEc);
            files.push_back({p, mtimeEc ? std::filesystem::file_time_type::min() : mtime});
        }

        // 최신 수정 순으로 정렬한다 -- "오래됨"을 고르는 이 자리의 의미는
        // JournalWriter.h의 rotateAll() 주석을 참고. 이 파일들 하나하나가
        // 이미 스스로 옳은 세션 경계를 가지고 있으므로, 여기서는 "어느 파일
        // 전체를 지울지"만 정한다.
        std::sort(files.begin(), files.end(), [](const Entry& a, const Entry& b) {
            return a.mtime > b.mtime;
        });

        std::size_t keptSessions = 0;
        for (const Entry& entry : files) {
            if (keptSessions >= kJournalSessionsKept) {
                std::error_code removeEc;
                std::filesystem::remove(entry.path, removeEc);
                // 지우기가 실패해도(예: 그 파일을 소유한 프로세스가 아직
                // 살아 있어 공유 위반이 나는 경우) 삼킨다 -- 다음 번 회전이
                // 다시 시도한다. 활성 프로세스의 파일은 최신 수정 시각
                // 덕분에 애초에 이 분기에 잘 들어오지 않는다.
                continue;
            }
            keptSessions += countSessionOpens(entry.path);
        }
    } catch (...) {
        // 여러 파일에 걸친 회전이 실패해도 진단은 계속된다.
    }
}

}  // namespace maro
