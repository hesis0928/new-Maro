#include "MaroDiagCommands.h"

#include <maya/MArgDatabase.h>
#include <maya/MArgList.h>
#include <maya/MGlobal.h>
#include <maya/MStringArray.h>

#include "MaroDiag.h"

namespace maro {

namespace {

const char* kSeverityFlag = "-sv";
const char* kSeverityFlagLong = "-severity";
const char* kMessageFlag = "-msg";
const char* kMessageFlagLong = "-message";
const char* kSiteTagFlag = "-st";
const char* kSiteTagFlagLong = "-siteTag";
const char* kIndexFlag = "-i";
const char* kIndexFlagLong = "-index";

MString severityToString(DiagSeverity s) {
    switch (s) {
        case DiagSeverity::Info: return "info";
        case DiagSeverity::Warn: return "warn";
        case DiagSeverity::DevInfo: return "devInfo";
        case DiagSeverity::Error: return "error";
    }
    return "unknown";
}

}  // namespace

void* MaroDiagEmitCommand::creator() { return new MaroDiagEmitCommand(); }

MSyntax MaroDiagEmitCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag(kSeverityFlag, kSeverityFlagLong, MSyntax::kString);
    syntax.addFlag(kMessageFlag, kMessageFlagLong, MSyntax::kString);
    syntax.addFlag(kSiteTagFlag, kSiteTagFlagLong, MSyntax::kString);
    return syntax;
}

MStatus MaroDiagEmitCommand::doIt(const MArgList& args) {
    try {
        MStatus status;
        MArgDatabase argData(newSyntax(), args, &status);
        if (!status) return status;

        MString severity = "info";
        MString message;
        MString siteTag;
        argData.getFlagArgument(kSeverityFlag, 0, severity);
        argData.getFlagArgument(kMessageFlag, 0, message);
        if (argData.isFlagSet(kSiteTagFlag)) {
            argData.getFlagArgument(kSiteTagFlag, 0, siteTag);
        }

        if (severity == "info") {
            BoadMaro::info(message);
        } else if (severity == "warn") {
            BoadMaro::warn(message);
        } else if (severity == "devInfo") {
            BoadMaro::devInfo(message);
        } else if (severity == "error") {
            if (siteTag.length() == 0) {
                MGlobal::displayError("Maro: maroDiagEmit -severity error requires -siteTag.");
                return MS::kFailure;
            }
            // 이 커맨드 자체는 마커를 설치하지 않는다 (테스트 전용 도구이므로
            // ScopedCommandContext를 두지 않는다) -- capture()는 그저 현재
            // 살아 있는 커맨드 컨텍스트 스택을 있는 그대로 읽어 activeCommand를
            // 채운다. 스택이 비어 있으면 capture("", "", "")는 이전 기본값
            // DgContext{}와 바이트 단위로 동일한 결과를 낸다.
            BoadMaro::error(siteTag.asChar(), message, onfix::capture("", "", ""));
        } else {
            MGlobal::displayError(MString("Maro: unknown severity '") + severity + "'.");
            return MS::kFailure;
        }
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroDiagEmit failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroDiagEmit failed with unknown error.");
        return MS::kFailure;
    }
}

void* MaroDiagCountCommand::creator() { return new MaroDiagCountCommand(); }

MStatus MaroDiagCountCommand::doIt(const MArgList& /*args*/) {
    try {
        setResult(static_cast<int>(BoadMaro::recordCount()));
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroDiagCount failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroDiagCount failed with unknown error.");
        return MS::kFailure;
    }
}

void* MaroDiagQueryCommand::creator() { return new MaroDiagQueryCommand(); }

MSyntax MaroDiagQueryCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag(kIndexFlag, kIndexFlagLong, MSyntax::kLong);
    return syntax;
}

MStatus MaroDiagQueryCommand::doIt(const MArgList& args) {
    try {
        MStatus status;
        MArgDatabase argData(newSyntax(), args, &status);
        if (!status) return status;

        int index = 0;
        if (argData.isFlagSet(kIndexFlag)) {
            argData.getFlagArgument(kIndexFlag, 0, index);
        }

        if (index < 0 || static_cast<std::size_t>(index) >= BoadMaro::recordCount()) {
            MGlobal::displayError("Maro: maroDiagQuery index out of range.");
            return MS::kFailure;
        }

        const DiagRecord& rec = BoadMaro::recordAt(static_cast<std::size_t>(index));

        MStringArray result;
        result.append(severityToString(rec.severity));
        result.append(MString(rec.message.c_str()));
        result.append(MString(rec.errorHash.c_str()));
        result.append(MString(rec.context.nodeType.c_str()));
        result.append(MString(rec.context.attributeName.c_str()));
        result.append(MString(rec.context.activeCommand.c_str()));
        result.append(MString(rec.context.axisOrTarget.c_str()));
        result.append(MString(rec.remedy.c_str()));
        result.append(rec.servedFromBook ? "1" : "0");
        setResult(result);
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroDiagQuery failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroDiagQuery failed with unknown error.");
        return MS::kFailure;
    }
}

void* MaroDiagAnalysisCountCommand::creator() { return new MaroDiagAnalysisCountCommand(); }

MStatus MaroDiagAnalysisCountCommand::doIt(const MArgList& /*args*/) {
    try {
        setResult(static_cast<int>(BoadMaro::freshAnalysisCount()));
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroDiagAnalysisCount failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroDiagAnalysisCount failed with unknown error.");
        return MS::kFailure;
    }
}

}  // namespace maro
