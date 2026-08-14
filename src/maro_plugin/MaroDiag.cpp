#include "MaroDiag.h"

#include <utility>

#include <maya/MGlobal.h>

namespace maro {

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
    // book 연동은 Task 5. 지금은 항상 "새 분석"으로 취급하고 스트림에만 남긴다.
    (void)siteTag;
    DiagRecord rec;
    rec.severity = DiagSeverity::Error;
    rec.context = context;
    rec.message = message.asChar();
    MGlobal::displayError(MString("[Maro-Error] ") + message);
    std::lock_guard<std::mutex> lock(mutex());
    stream().push_back(std::move(rec));
}

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
