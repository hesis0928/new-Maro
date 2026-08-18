#include "MaroDiagCommands.h"

#include <atomic>
#include <string>
#include <thread>

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
// maroDiagEmit(-severity error) 전용 테스트 확장. MaroDiagCommands.h 참고.
const char* kNodeTypeFlag = "-nt";
const char* kNodeTypeFlagLong = "-nodeType";
const char* kAxisOrTargetFlag = "-ax";
const char* kAxisOrTargetFlagLong = "-axisOrTarget";
const char* kNameUnavailableFlag = "-nu";
const char* kNameUnavailableFlagLong = "-nameUnavailable";
const char* kTypeUnavailableFlag = "-tu";
const char* kTypeUnavailableFlagLong = "-typeUnavailable";
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
    syntax.addFlag(kNodeTypeFlag, kNodeTypeFlagLong, MSyntax::kString);
    syntax.addFlag(kAxisOrTargetFlag, kAxisOrTargetFlagLong, MSyntax::kString);
    syntax.addFlag(kNameUnavailableFlag, kNameUnavailableFlagLong, MSyntax::kNoArg);
    syntax.addFlag(kTypeUnavailableFlag, kTypeUnavailableFlagLong, MSyntax::kNoArg);
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
            MString nodeType;
            MString axisOrTarget;
            if (argData.isFlagSet(kNodeTypeFlag)) {
                argData.getFlagArgument(kNodeTypeFlag, 0, nodeType);
            }
            if (argData.isFlagSet(kAxisOrTargetFlag)) {
                argData.getFlagArgument(kAxisOrTargetFlag, 0, axisOrTarget);
            }
            DgContext ctx = onfix::capture(nodeType, "", axisOrTarget);
            // NotCaptured 프레즌스를 결정적으로 재현하기 위한 테스트 전용
            // 확장이다 (MaroDiagCommands.h 참고). 지정하지 않으면 둘 다
            // false로 남아 이전 동작과 동일하다.
            ctx.nameUnavailable = argData.isFlagSet(kNameUnavailableFlag);
            ctx.typeUnavailable = argData.isFlagSet(kTypeUnavailableFlag);
            BoadMaro::error(siteTag.asChar(), message, ctx);
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

void* MaroDiagEmitFromThreadCommand::creator() {
    return new MaroDiagEmitFromThreadCommand();
}

MSyntax MaroDiagEmitFromThreadCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag(kSeverityFlag, kSeverityFlagLong, MSyntax::kString);
    syntax.addFlag(kMessageFlag, kMessageFlagLong, MSyntax::kString);
    syntax.addFlag(kSiteTagFlag, kSiteTagFlagLong, MSyntax::kString);
    return syntax;
}

MStatus MaroDiagEmitFromThreadCommand::doIt(const MArgList& args) {
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

        if (severity != "info" && severity != "warn" && severity != "error") {
            MGlobal::displayError(
                MString("Maro: maroDiagEmitFromThread: unknown severity '") +
                severity + "'.");
            return MS::kFailure;
        }
        if (severity == "error" && siteTag.length() == 0) {
            MGlobal::displayError(
                "Maro: maroDiagEmitFromThread -severity error requires -siteTag.");
            return MS::kFailure;
        }

        // MString을 스레드 경계 너머로 그대로 넘기지 않는다 -- devkit은
        // MString의 스레드 간 공유 안전성을 보장하지 않는다. 워커가 쓸
        // 내용은 std::string으로 복사해 두고, 워커 안에서 새 MString을 만든다.
        const std::string severityUtf8(severity.asChar());
        const std::string messageUtf8(message.asChar());
        const std::string siteTagUtf8(siteTag.asChar());

        // 워커가 스스로를 어떻게 판정했는지 되가져온다. join() 뒤에만 읽지만
        // atomic으로 두어 "스레드 경계를 넘는 값"이라는 의도를 남긴다.
        std::atomic<bool> sawNonMainThread{false};
        std::atomic<bool> workerThrew{false};

        // 진짜 std::thread다. 여기서 예외가 워커 밖으로 새면 std::terminate라
        // 프로세스가 죽는다 -- 워커 본문 전체를 catch(...)로 감싼다.
        std::thread worker([&] {
            try {
                sawNonMainThread.store(!isMainThread());
                const MString workerMessage(messageUtf8.c_str());
                if (severityUtf8 == "info") {
                    BoadMaro::info(workerMessage);
                } else if (severityUtf8 == "warn") {
                    BoadMaro::warn(workerMessage);
                } else {
                    BoadMaro::error(siteTagUtf8, workerMessage,
                                    onfix::capture("", "", ""));
                }
            } catch (...) {
                workerThrew.store(true);
            }
        });
        worker.join();

        if (workerThrew.load()) {
            MGlobal::displayError(
                "Maro: maroDiagEmitFromThread: the worker thread threw while "
                "emitting through boad.");
            return MS::kFailure;
        }

        // 1이면 워커에서 isMainThread()가 false로 판정됐다는 뜻 -- 이 커맨드가
        // 실제로 메인 스레드 밖에서 boad를 탔음을 테스트가 확인할 수 있다.
        setResult(sawNonMainThread.load() ? 1 : 0);
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(
            MString("Maro: maroDiagEmitFromThread failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroDiagEmitFromThread failed with unknown error.");
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

        // 리뷰(carried-forward Minor): recordAt()은 값으로 반환한다(뮤텍스
        // 스코프 밖으로 내부 원소 참조가 새는 것을 막으려고 -- MaroDiag.h
        // 참고). 여기서 그 반환값을 const&로 받으면 컴파일은 되지만(임시
        // 객체 수명이 참조 수명까지 늘어난다) 정확히 이 함수가 막으려던
        // "매달린 참조" 패턴과 똑같이 읽혀 오해를 부른다. 값으로 받는다.
        const DiagRecord rec = BoadMaro::recordAt(static_cast<std::size_t>(index));

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
        // 리뷰 Finding C1: 10번째 필드로 덧붙인다. 기존 테스트들이 0~8 인덱스를
        // 위치로 참조하므로 그 사이에 끼워 넣지 않는다 -- 끝에만 붙여야 기존
        // 인덱스가 전부 그대로 유지된다.
        result.append(MString(rec.priorAnalysis.c_str()));
        // 뒤에 붙인다 -- 기존 테스트들이 위치 인덱스로 읽으므로 0~9는 그대로 둔다.
        result.append(MString(std::to_string(rec.sequence).c_str()));
        result.append(MString(std::to_string(rec.timestampMs).c_str()));
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
    // 리뷰(carried-forward Minor): 이 두 경고는 실제 사용자가 해법을
    // 등록하려 할 때 닿을 수 있는 프로덕션 경로다(이 파일의 나머지는 대부분
    // 테스트 전용 도구지만, maroDiagRegisterRemedy는 아니다) -- boad가
    // 진단의 단일 출구라는 불변식을 지키려면 MGlobal::displayWarning을
    // 직접 부르면 안 된다.
    MStatus hashStatus = syntax.addFlag(kHashFlag, kHashFlagLong, MSyntax::kString);
    if (!hashStatus) {
        BoadMaro::warn(
            MString("Maro: maroDiagRegisterRemedy failed to register ") + kHashFlagLong +
            " flag: " + hashStatus.errorString());
    }
    MStatus remedyStatus = syntax.addFlag(kRemedyFlag, kRemedyFlagLong, MSyntax::kString);
    if (!remedyStatus) {
        BoadMaro::warn(
            MString("Maro: maroDiagRegisterRemedy failed to register ") + kRemedyFlagLong +
            " flag: " + remedyStatus.errorString());
    }
    return syntax;
}

MStatus MaroDiagRegisterRemedyCommand::doIt(const MArgList& args) {
    // 리뷰(carried-forward Minor): 이 파일의 나머지 커맨드는 대부분 테스트
    // 전용 도구라 마커를 설치하지 않지만, maroDiagRegisterRemedy는 실제
    // 사용자가 해법을 등록할 때 쓰는 프로덕션 진입점이다. 다른 프로덕션
    // 커맨드들(MaroCommands.cpp)과 같은 관례로 마커를 설치해, 아래 boad::error가
    // activeCommand를 채울 수 있게 한다.
    maro::ScopedCommandContext ctxMarker("MaroDiagRegisterRemedyCommand");
    try {
        MStatus status;
        MArgDatabase argData(newSyntax(), args, &status);
        if (!status) return status;

        if (!argData.isFlagSet(kHashFlag) || !argData.isFlagSet(kRemedyFlag)) {
            // 리뷰(carried-forward Minor): 예전에는 MGlobal::displayError를
            // 직접 불렀다 -- 이 파일이 "boad가 진단의 단일 출구"라는 불변식을
            // boad 자신의 커맨드 구현에서 깨고 있었다. 이 검증 실패는 실제
            // 사용자가 밟을 수 있는 경로이므로(테스트 전용 도구가 아니다)
            // boad를 거친다.
            BoadMaro::error("MaroDiagRegisterRemedyCommand.WrongArgCount",
                            "Maro: maroDiagRegisterRemedy needs -hash and -remedy.",
                            onfix::capture("", "", ""));
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

void* MaroDiagEmitMarkedCommand::creator() { return new MaroDiagEmitMarkedCommand(); }

MSyntax MaroDiagEmitMarkedCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag(kMessageFlag, kMessageFlagLong, MSyntax::kString);
    syntax.addFlag(kSiteTagFlag, kSiteTagFlagLong, MSyntax::kString);
    return syntax;
}

MStatus MaroDiagEmitMarkedCommand::doIt(const MArgList& args) {
    // 리뷰 Finding 1 전용: 이 커맨드 자신을 이름으로 하는 마커를 설치한 채로
    // BoadMaro::error()를 세 번째 인자(컨텍스트) 없이 부른다 -- 기본 인자
    // DgContext{}를 그대로 태우면서도 스택에는 살아있는 마커가 있는 상태를
    // 재현한다. error()가 빈 activeCommand를 g_commandStack에서 채워 넣는지
    // (Finding 1 수정) 여기서 직접 확인할 수 있다.
    maro::ScopedCommandContext ctxMarker("MaroDiagEmitMarkedCommand");
    try {
        MStatus status;
        MArgDatabase argData(newSyntax(), args, &status);
        if (!status) return status;

        MString message;
        MString siteTag;
        argData.getFlagArgument(kMessageFlag, 0, message);
        if (!argData.isFlagSet(kSiteTagFlag)) {
            MGlobal::displayError("Maro: maroDiagEmitMarked requires -siteTag.");
            return MS::kFailure;
        }
        argData.getFlagArgument(kSiteTagFlag, 0, siteTag);

        BoadMaro::error(siteTag.asChar(), message);
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroDiagEmitMarked failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroDiagEmitMarked failed with unknown error.");
        return MS::kFailure;
    }
}

void* MaroJournalAbnormalSessionsCommand::creator() {
    return new MaroJournalAbnormalSessionsCommand();
}

MStatus MaroJournalAbnormalSessionsCommand::doIt(const MArgList& /*args*/) {
    try {
        setResult(static_cast<int>(BoadMaro::crashAdjacency().abnormalSessionCount));
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroJournalAbnormalSessions failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroJournalAbnormalSessions failed with unknown error.");
        return MS::kFailure;
    }
}

void* MaroJournalCrashAdjacentTagsCommand::creator() {
    return new MaroJournalCrashAdjacentTagsCommand();
}

MStatus MaroJournalCrashAdjacentTagsCommand::doIt(const MArgList& /*args*/) {
    try {
        MStringArray result;
        for (const auto& entry : BoadMaro::crashAdjacency().appearancesByTag) {
            result.append(MString(entry.first.c_str()));
        }
        setResult(result);
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroJournalCrashAdjacentTags failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroJournalCrashAdjacentTags failed with unknown error.");
        return MS::kFailure;
    }
}

}  // namespace maro
