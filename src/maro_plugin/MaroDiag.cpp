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

}  // namespace maro
