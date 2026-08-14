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
// "-h"는 Maya에서 관례상 도움말(-help) 짧은형으로 쓰인다. 실측 결과는 아래
// newSyntax()의 addFlag 상태 로그로 남긴다 -- 안전한 쪽인 "-hs"를 쓴다
// (테스트는 항상 "-hash" 긴 이름을 쓰므로 짧은형을 바꿔도 비용이 없다).
const char* kHashFlag = "-hs";
const char* kHashFlagLong = "-hash";
const char* kRemedyFlag = "-r";
const char* kRemedyFlagLong = "-remedy";

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

void* MaroDiagRegisterRemedyCommand::creator() { return new MaroDiagRegisterRemedyCommand(); }

MSyntax MaroDiagRegisterRemedyCommand::newSyntax() {
    MSyntax syntax;
    // 반환 상태를 반드시 확인한다 -- addFlag가 조용히 실패하면(예: 짧은형이
    // Maya 예약 플래그와 충돌) 이 플래그는 syntax에 없는 것과 같아져서, 이후
    // MArgDatabase가 사용자가 준 인자를 "알 수 없는 플래그"로 거부한다. 실측:
    // 이 플러그인의 다른 커맨드로 MEL에서 등록되지 않은 "-h"를 호출하면
    // "Invalid flag '-h'"로 거부됐다 -- Maya가 "-h"를 전역적으로 가로채 도움말을
    // 띄우는 것은 아니었지만, "-h"는 관례상 -help의 짧은형이라 사용자 혼동
    // 소지가 남는다. 테스트는 항상 "-hash" 긴 이름만 쓰므로("hash=..."),
    // 짧은형을 "-hs"로 바꿔 그 위험을 아예 피했다 -- 비용이 없다.
    MStatus hashStatus = syntax.addFlag(kHashFlag, kHashFlagLong, MSyntax::kString);
    if (!hashStatus) {
        MGlobal::displayWarning(
            MString("Maro: maroDiagRegisterRemedy failed to register ") + kHashFlagLong +
            " flag: " + hashStatus.errorString());
    }
    MStatus remedyStatus = syntax.addFlag(kRemedyFlag, kRemedyFlagLong, MSyntax::kString);
    if (!remedyStatus) {
        MGlobal::displayWarning(
            MString("Maro: maroDiagRegisterRemedy failed to register ") + kRemedyFlagLong +
            " flag: " + remedyStatus.errorString());
    }
    return syntax;
}

MStatus MaroDiagRegisterRemedyCommand::doIt(const MArgList& args) {
    try {
        MStatus status;
        MArgDatabase argData(newSyntax(), args, &status);
        if (!status) return status;

        if (!argData.isFlagSet(kHashFlag) || !argData.isFlagSet(kRemedyFlag)) {
            MGlobal::displayError("Maro: maroDiagRegisterRemedy needs -hash and -remedy.");
            return MS::kFailure;
        }

        MString hash;
        MString remedy;
        argData.getFlagArgument(kHashFlag, 0, hash);
        argData.getFlagArgument(kRemedyFlag, 0, remedy);

        BoadMaro::registerRemedy(hash.asChar(), remedy);
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroDiagRegisterRemedy failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroDiagRegisterRemedy failed with unknown error.");
        return MS::kFailure;
    }
}

}  // namespace maro
