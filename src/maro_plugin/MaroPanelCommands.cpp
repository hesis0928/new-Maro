#include "MaroPanelCommands.h"

#include <string>
#include <vector>

#include <maya/MArgDatabase.h>
#include <maya/MArgList.h>
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
const char* kIndexFlag = "-i";
const char* kIndexFlagLong = "-index";
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
    syntax.addFlag(kIndexFlag, kIndexFlagLong, MSyntax::kLong);
    syntax.addFlag(kSeverityFlag, kSeverityFlagLong, MSyntax::kString);
    syntax.addFlag(kMaxRowsFlag, kMaxRowsFlagLong, MSyntax::kLong);
    return syntax;
}

MStatus MaroDiagPanelDetailCommand::doIt(const MArgList& args) {
    try {
        MStatus status;
        MArgDatabase argData(newSyntax(), args, &status);
        if (!status) return status;

        int index = 0;
        MString severity = "all";
        int maxRows = kDefaultMaxRows;
        if (argData.isFlagSet(kIndexFlag)) {
            argData.getFlagArgument(kIndexFlag, 0, index);
        }
        if (argData.isFlagSet(kSeverityFlag)) {
            argData.getFlagArgument(kSeverityFlag, 0, severity);
        }
        if (argData.isFlagSet(kMaxRowsFlag)) {
            argData.getFlagArgument(kMaxRowsFlag, 0, maxRows);
        }
        if (maxRows < 0) maxRows = 0;

        const std::vector<DiagRecord> records = snapshot();
        std::size_t hiddenByFilter = 0;
        std::size_t hiddenByCap = 0;
        const std::vector<PanelRow> rows =
            buildPanelRows(records, parseFilter(severity),
                            static_cast<std::size_t>(maxRows),
                            hiddenByFilter, hiddenByCap);

        if (index < 0 || static_cast<std::size_t>(index) >= rows.size()) {
            MGlobal::displayError("Maro: maroDiagPanelDetail index out of range.");
            return MS::kFailure;
        }

        // 행이 대표하는 레코드는 그 태그의 가장 최근 발생이고, 행은 그
        // 순번을 들고 있다. 순번으로 되찾는다 -- 시각으로 찾으면 벽시계가
        // 뒤로 간 순간 엉뚱한 레코드를 집는다.
        const std::uint64_t wanted = rows[static_cast<std::size_t>(index)].sequence;
        const DiagRecord* chosen = nullptr;
        for (const DiagRecord& rec : records) {
            if (rec.sequence == wanted) {
                chosen = &rec;
                break;
            }
        }
        if (chosen == nullptr) {
            MGlobal::displayError("Maro: maroDiagPanelDetail could not resolve the row.");
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

}  // namespace maro
