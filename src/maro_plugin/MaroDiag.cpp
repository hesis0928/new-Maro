#include "MaroDiag.h"

#include <atomic>
#include <cstdlib>
#include <filesystem>
#include <utility>

#include <maya/MGlobal.h>

#include "maro_diag/BookStore.h"
#include "maro_diag/ErrorHash.h"

namespace maro {

namespace {

std::atomic<std::size_t> g_freshAnalysisCount{0};

struct BookPaths {
    std::filesystem::path canonical;
    std::filesystem::path spill;
};

// 기본은 원안(Maro_DebugUtility/book_Maro.cpp)과 같은 위치다:
// internalVar -userAppDir. MARO_DIAG_BOOK_DIR이 설정돼 있으면 그것을
// 우선한다 -- 테스트가 매 실행마다 깨끗한 book으로 시작하기 위한 재정의다.
const BookPaths& bookPaths() {
    static const BookPaths paths = [] {
        BookPaths p;
        std::filesystem::path dir;
        if (const char* override_ = std::getenv("MARO_DIAG_BOOK_DIR")) {
            dir = override_;
        } else {
            const MString userAppDir =
                MGlobal::executeCommandStringResult("internalVar -userAppDir");
            dir = userAppDir.length() > 0 ? std::filesystem::path(userAppDir.asChar())
                                           : std::filesystem::temp_directory_path();
        }
        p.canonical = dir / "maro_knowledge.jsonl";
        p.spill = dir / "maro_knowledge.spill.jsonl";
        return p;
    }();
    return paths;
}

}  // namespace

std::vector<DiagRecord>& BoadMaro::stream() {
    static std::vector<DiagRecord> s_stream;
    return s_stream;
}

std::mutex& BoadMaro::mutex() {
    static std::mutex s_mutex;
    return s_mutex;
}

void BoadMaro::info(const MString& message) {
    DiagRecord rec;
    rec.severity = DiagSeverity::Info;
    rec.message = message.asChar();
    MGlobal::displayInfo(MString("[Maro-Info] ") + message);
    std::lock_guard<std::mutex> lock(mutex());
    stream().push_back(std::move(rec));
}

void BoadMaro::warn(const MString& message) {
    DiagRecord rec;
    rec.severity = DiagSeverity::Warn;
    rec.message = message.asChar();
    MGlobal::displayWarning(MString("[Maro-Warn] ") + message);
    std::lock_guard<std::mutex> lock(mutex());
    stream().push_back(std::move(rec));
}

void BoadMaro::devInfo(const MString& message) {
#ifdef _DEBUG
    DiagRecord rec;
    rec.severity = DiagSeverity::DevInfo;
    rec.message = message.asChar();
    MGlobal::displayInfo(MString("[Maro-Dev] ") + message);
    std::lock_guard<std::mutex> lock(mutex());
    stream().push_back(std::move(rec));
#else
    (void)message;
#endif
}

void BoadMaro::error(const std::string& siteTag, const MString& message,
                      const DgContext& context) {
    DiagRecord rec;
    rec.severity = DiagSeverity::Error;
    rec.context = context;

    try {
        const std::string hash = hashError(siteTag);
        rec.errorHash = hash;

        const BookPaths& paths = bookPaths();
        const BookStore store = BookStore::loadMerged(paths.canonical, paths.spill);

        BookEntry entry;
        if (store.query(hash, entry)) {
            rec.message = entry.analysis + "\n(Maro: book에 있는 과거 분석에서 즉답)";
            rec.remedy = entry.remedy;
            rec.servedFromBook = true;
        } else {
            rec.message = message.asChar();
            rec.servedFromBook = false;

            BookEntry fresh;
            fresh.analysis = rec.message;
            fresh.context = context;
            BookStore::appendToSpill(paths.spill, hash, fresh);
            ++g_freshAnalysisCount;
        }
    } catch (const std::exception& e) {
        // book이 죽어도 진단은 죽지 않는다 (스펙 §3.6). 이 실패 자체는
        // 재귀적으로 error()를 부르지 않고 devInfo로만 남긴다.
        rec.message = message.asChar();
        rec.servedFromBook = false;
        ++g_freshAnalysisCount;
        devInfo(MString("Maro: book 조회/기록 실패, 로컬 기록으로 진행: ") + e.what());
    } catch (...) {
        rec.message = message.asChar();
        rec.servedFromBook = false;
        ++g_freshAnalysisCount;
        devInfo("Maro: book 조회/기록에서 알 수 없는 오류, 로컬 기록으로 진행.");
    }

    MGlobal::displayError(MString("[Maro-Error] ") + MString(rec.message.c_str()));
    std::lock_guard<std::mutex> lock(mutex());
    stream().push_back(std::move(rec));
}

std::size_t BoadMaro::freshAnalysisCount() { return g_freshAnalysisCount.load(); }

std::size_t BoadMaro::recordCount() {
    std::lock_guard<std::mutex> lock(mutex());
    return stream().size();
}

DiagRecord BoadMaro::recordAt(std::size_t indexFromEnd) {
    std::lock_guard<std::mutex> lock(mutex());
    return stream().at(stream().size() - 1 - indexFromEnd);
}

void BoadMaro::resetForTest() {
    std::lock_guard<std::mutex> lock(mutex());
    stream().clear();
    g_freshAnalysisCount = 0;
}

namespace {
// Maya 메인 스레드만 doIt을 부르지만, thread_local로 두면 우연한 재진입도 안전하다.
thread_local std::vector<std::string> g_commandStack;
}  // namespace

ScopedCommandContext::ScopedCommandContext(const char* commandName) {
    g_commandStack.emplace_back(commandName);
}

ScopedCommandContext::~ScopedCommandContext() {
    if (!g_commandStack.empty()) g_commandStack.pop_back();
}

namespace onfix {

std::string activeCommand() {
    return g_commandStack.empty() ? std::string() : g_commandStack.back();
}

DgContext capture(const MString& nodeType, const MString& attributeName,
                   const MString& axisOrTarget) {
    DgContext ctx;
    ctx.nodeType = nodeType.asChar();
    ctx.attributeName = attributeName.asChar();
    ctx.axisOrTarget = axisOrTarget.asChar();
    ctx.activeCommand = activeCommand();
    return ctx;
}

}  // namespace onfix

}  // namespace maro
