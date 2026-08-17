#include "MaroPanelCommands.h"

#include <string>
#include <vector>

// MFnPlugin.h's own docs (and MApiVersion.h) require this: including it in
// more than one translation unit of the same plug-in emits DllMain,
// MhInstPlugin, MApiVersion and ADSK_PLUGIN_SIGNATURE again, which the
// linker then reports as LNK2005 against MaroPluginMain.cpp.obj (the file
// that legitimately owns those symbols). Defining both macros before the
// include keeps this file to just MFnPlugin::findPlugin/loadPath.
#define MNoPluginEntry
#define MNoVersionString

#include <maya/MArgDatabase.h>
#include <maya/MArgList.h>
#include <maya/MFnPlugin.h>
#include <maya/MGlobal.h>
#include <maya/MStringArray.h>

#include "MaroDiag.h"
#include "maro_diag/BookStore.h"
#include "maro_diag/PanelPresenter.h"
#include "maro_diag/PanelView.h"

namespace maro {

namespace {

const char* kSeverityFlag = "-sv";
const char* kSeverityFlagLong = "-severity";
const char* kMaxRowsFlag = "-mr";
const char* kMaxRowsFlagLong = "-maxRows";
const char* kSequenceFlag = "-sq";
const char* kSequenceFlagLong = "-sequence";
const char* kHiddenFlag = "-hd";
const char* kHiddenFlagLong = "-hidden";

constexpr int kDefaultMaxRows = 500;

PanelSeverityFilter parseFilter(const MString& text) {
    if (text == "error") return PanelSeverityFilter::ErrorsOnly;
    if (text == "warn") return PanelSeverityFilter::WarnAndAbove;
    return PanelSeverityFilter::All;
}

const char* presenceName(ContextPresence p) {
    switch (p) {
        case ContextPresence::Present: return "present";
        case ContextPresence::NotApplicable: return "notApplicable";
        case ContextPresence::NotCaptured: return "notCaptured";
    }
    return "notApplicable";
}

// boad의 스트림을 통째로 복사해 온다. 프레젠터는 순수해야 하므로 살아있는
// 상태를 들여다보지 않고 스냅샷만 본다 (설계 스펙 §3.3).
//
// 리뷰 Finding: 예전에는 recordCount()로 개수를 얻은 뒤 recordAt()을 그
// 개수만큼 반복 호출하며 뒤에서부터 채웠다. 그 두 함수는 각자 독립적으로
// 락을 잡았다 놓으므로, 루프 도중 다른 스레드가 push_back하면(Maya 2026
// Parallel Evaluation Manager 아래 워커에서 error()/warn()/info()가 그럴 수
// 있다) recordAt(indexFromEnd)의 인덱스 산법이 루프 시작 시점의 count가 아닌
// 지금 이 순간의 크기를 기준으로 계산돼, 남은 반복 전부가 한 칸씩 밀려
// 레코드를 건너뛰거나 두 번 읽었다 -- 스냅샷이 아니었다. BoadMaro::
// snapshotRecords()는 락을 한 번만 잡고 그 안에서 전체를 복사하므로 그
// 경합이 없고, 이미 오래된 것부터 순번 순서로 저장돼 있으므로(순번 배정이
// push_back과 같은 락 스코프 안에서 일어난다) 뒤집을 필요도 없다.
std::vector<DiagRecord> snapshot() {
    return BoadMaro::snapshotRecords();
}

}  // namespace

void* MaroDiagPanelRowsCommand::creator() { return new MaroDiagPanelRowsCommand(); }

MSyntax MaroDiagPanelRowsCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag(kSeverityFlag, kSeverityFlagLong, MSyntax::kString);
    syntax.addFlag(kMaxRowsFlag, kMaxRowsFlagLong, MSyntax::kLong);
    syntax.addFlag(kHiddenFlag, kHiddenFlagLong, MSyntax::kNoArg);
    return syntax;
}

MStatus MaroDiagPanelRowsCommand::doIt(const MArgList& args) {
    try {
        MStatus status;
        MArgDatabase argData(newSyntax(), args, &status);
        if (!status) return status;

        MString severity = "all";
        int maxRows = kDefaultMaxRows;
        if (argData.isFlagSet(kSeverityFlag)) {
            argData.getFlagArgument(kSeverityFlag, 0, severity);
        }
        if (argData.isFlagSet(kMaxRowsFlag)) {
            argData.getFlagArgument(kMaxRowsFlag, 0, maxRows);
        }
        if (maxRows < 0) maxRows = 0;

        std::size_t hiddenByFilter = 0;
        std::size_t hiddenByCap = 0;
        const std::vector<PanelRow> rows =
            buildPanelRows(snapshot(), parseFilter(severity),
                            static_cast<std::size_t>(maxRows),
                            hiddenByFilter, hiddenByCap);

        MStringArray result;
        if (argData.isFlagSet(kHiddenFlag)) {
            // 필터로 빠진 것과 상한으로 잘린 것은 사용자에게 다른 사건이므로
            // 따로 돌려준다.
            result.append(MString(std::to_string(hiddenByFilter).c_str()));
            result.append(MString(std::to_string(hiddenByCap).c_str()));
            setResult(result);
            return MS::kSuccess;
        }

        for (const PanelRow& row : rows) {
            result.append(MString(row.errorHash.c_str()));
            result.append(MString(row.severity.c_str()));
            result.append(MString(row.summary.c_str()));
            result.append(MString(std::to_string(row.sequence).c_str()));
            result.append(MString(std::to_string(row.firstTimestampMs).c_str()));
            result.append(MString(std::to_string(row.lastTimestampMs).c_str()));
            result.append(MString(std::to_string(row.occurrences).c_str()));
            result.append(row.knownBefore ? "1" : "0");
        }
        setResult(result);
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroDiagPanelRows failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroDiagPanelRows failed with unknown error.");
        return MS::kFailure;
    }
}

void* MaroDiagPanelDetailCommand::creator() { return new MaroDiagPanelDetailCommand(); }

MSyntax MaroDiagPanelDetailCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag(kSequenceFlag, kSequenceFlagLong, MSyntax::kLong);
    return syntax;
}

MStatus MaroDiagPanelDetailCommand::doIt(const MArgList& args) {
    try {
        MStatus status;
        MArgDatabase argData(newSyntax(), args, &status);
        if (!status) return status;

        if (!argData.isFlagSet(kSequenceFlag)) {
            MGlobal::displayError("Maro: maroDiagPanelDetail requires -sequence.");
            return MS::kFailure;
        }
        int sequenceArg = -1;
        argData.getFlagArgument(kSequenceFlag, 0, sequenceArg);
        if (sequenceArg < 0) {
            MGlobal::displayError("Maro: maroDiagPanelDetail -sequence must not be negative.");
            return MS::kFailure;
        }
        const std::uint64_t wanted = static_cast<std::uint64_t>(sequenceArg);

        // 리뷰 Finding: 예전에는 여기서 buildPanelRows로 화면과 같은
        // 필터/상한을 다시 적용한 행 목록을 만들고, 그 안의 -index 자리를
        // 순번으로 옮겨 찾았다. 화면이 그려진 시점과 지금(클릭 시점) 사이에
        // 진단이 하나라도 더 들어오면 그 행 목록의 자리 배치가 바뀌어
        // -index가 가리키는 레코드가 사용자가 실제로 클릭한 레코드와
        // 달라진다. sequence는 세션 전역에서 유일하고 재사용되지 않으므로,
        // 필터링/절단을 다시 거칠 필요 없이 스냅샷을 그대로 훑어 그 값과
        // 일치하는 레코드 하나를 직접 찾는다 -- 화면이 그 사이에 어떻게
        // 바뀌었든 결과는 항상 사용자가 클릭한 바로 그 레코드다. 이 덕분에
        // 행 목록을 다시 만드는 작업도 통째로 사라진다.
        const std::vector<DiagRecord> records = snapshot();
        const DiagRecord* chosen = nullptr;
        for (const DiagRecord& rec : records) {
            if (rec.sequence == wanted) {
                chosen = &rec;
                break;
            }
        }
        if (chosen == nullptr) {
            // 존재한 적 없는 순번(오타, 혹은 세션이 리셋된 뒤의 스테일 선택)
            // 이면 엉뚱한 이웃 레코드를 대신 돌려주지 않고 실패로 끝낸다 --
            // 스테일 선택을 잡아내는 것이 이 커맨드가 -sequence로 바뀐
            // 이유이므로, 조용히 다른 것을 돌려주면 그 존재 이유 자체가
            // 무너진다.
            MGlobal::displayError("Maro: maroDiagPanelDetail could not resolve sequence.");
            return MS::kFailure;
        }

        // 레코드가 남은 뒤에 등록된 해법을 반영하려면 지금 book을 다시 본다.
        BookEntry entry;
        const bool haveEntry =
            !chosen->errorHash.empty() && BoadMaro::lookupBook(chosen->errorHash, entry);

        const PanelDetail detail =
            buildPanelDetail(*chosen, haveEntry ? &entry : nullptr, false);

        MStringArray result;
        result.append(MString(detail.nodeType.value.c_str()));
        result.append(presenceName(detail.nodeType.presence));
        result.append(MString(detail.attributeName.value.c_str()));
        result.append(presenceName(detail.attributeName.presence));
        result.append(MString(detail.activeCommand.value.c_str()));
        result.append(presenceName(detail.activeCommand.presence));
        result.append(MString(detail.axisOrTarget.value.c_str()));
        result.append(presenceName(detail.axisOrTarget.presence));
        result.append(MString(detail.message.c_str()));
        result.append(MString(detail.priorAnalysis.c_str()));
        result.append(MString(detail.remedyText.c_str()));
        result.append(detail.applyAvailable ? "1" : "0");
        result.append(MString(detail.applyUnavailableReason.c_str()));
        setResult(result);
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroDiagPanelDetail failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroDiagPanelDetail failed with unknown error.");
        return MS::kFailure;
    }
}

void* MaroDiagPanelCommand::creator() { return new MaroDiagPanelCommand(); }

MStatus MaroDiagPanelCommand::doIt(const MArgList& /*args*/) {
    try {
        // 플러그인 .mll이 있는 디렉터리에 maroDiagPanel.py를 함께 배포한다.
        // 여기서 sys.path에 넣어야 사용자가 MAYA_SCRIPT_PATH를 손대지 않고도
        // 패널이 뜬다.
        //
        // findPlugin은 MObject를 돌려준다 -- 경로 문자열이 아니다. 경로는
        // 그 MObject로 만든 MFnPlugin의 loadPath()에서 나온다.
        // 공개 생성자는 MObject&(비상수)를 받으므로 const로 두면 안 된다.
        MObject pluginObj = MFnPlugin::findPlugin("maro");
        if (pluginObj.isNull()) {
            MGlobal::displayError("Maro: could not locate the loaded maro plug-in.");
            return MS::kFailure;
        }
        MStatus status;
        // vendor/version/apiVersion은 기본값이 있지만 상태를 받으려면
        // 앞의 셋을 함께 넘겨야 한다.
        MFnPlugin pluginFn(pluginObj, "Unknown", "Unknown", "Any", &status);
        if (!status) return status;
        const MString pluginDir = pluginFn.loadPath(&status);
        if (!status) return status;

        MString python;
        python += "import os, sys\n";
        python += "d = r'";
        python += pluginDir;
        python += "'\n";
        // loadPath()가 디렉터리를 주는지 파일까지 주는지에 기대지 않는다.
        python += "if os.path.isfile(d): d = os.path.dirname(d)\n";
        python += "if d not in sys.path: sys.path.insert(0, d)\n";
        python += "import maroDiagPanel\n";
        python += "maroDiagPanel.show()\n";

        return MGlobal::executePythonCommand(python);
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroDiagPanel failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroDiagPanel failed with unknown error.");
        return MS::kFailure;
    }
}

}  // namespace maro
