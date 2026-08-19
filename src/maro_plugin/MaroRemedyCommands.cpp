#include "MaroRemedyCommands.h"

#include <cmath>
#include <cstdint>
#include <exception>
#include <string>

#include <maya/MArgDatabase.h>
#include <maya/MArgList.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MGlobal.h>
#include <maya/MPlug.h>
// 브리프의 include 목록에는 없었다. 아래 재확인 블록이 MPlugArray를 값으로
// 선언하므로(연결이 아직 살아있는지 보는 connectedTo) 완전한 타입이 필요하다
// -- MPlug.h가 그것을 전이적으로 끌어온다는 보장은 없다.
#include <maya/MPlugArray.h>

#include "MaroDiag.h"
#include "MaroMainThreadQueue.h"

namespace maro {

namespace {

const char* kSequenceFlag = "-sq";
const char* kSequenceFlagLong = "-sequence";

// 이름 하나를 지금 씬에서 **정확히 하나**의 대상으로 푼다. 성공하면 out은
// 그 하나만 담은 리스트다 -- 호출자는 인덱스 0을 쓰면 된다.
//
// 최종 리뷰 Finding I1: 예전에는 add()의 상태만 보는 nameStillExists()가
// 있었고, 그 뒤 스테이징이 `sel.add(src); sel.add(dst); getPlug(0); getPlug(1)`
// 처럼 리스트 하나를 이름 둘로 채운 뒤 위치로 집었다. MSelectionList::add의
// 인자는 devkit 시그니처에서조차 이름이 matchString이다 -- 엄격한 조회가
// 아니라 `ls`와 같은 패턴 매치라서 모호한 이름은 매치를 **전부** 담는다.
//
// 실측(Maya 2026, mayapy)으로 확인한 실제 동작:
//   add("pCube1")          -> kInvalidParameter        (모호한 노드 이름은 거절)
//   add("pCube1.message")  -> kSuccess, length()==2    (모호한 플러그 이름은 통과!)
//
// 그래서 src가 "pCube1.message"처럼 모호하면 리스트는 [src매치1, src매치2,
// dst]가 되고, getPlug(1)은 dst가 아니라 **src의 두 번째 매치**를 돌려준다 --
// 그 상태로 disconnect(getPlug(0), getPlug(1))를 하면 사용자가 지목한 적도
// 없는 노드의 연결을 조용히 끊는다. 이름마다 새 리스트를 쓰고 length()==1을
// 강제하는 것이 그 부류를 통째로 없애는 방법이다.
//
// 실패는 그 자리에서 boad에 남긴다 -- 이 파일의 기존 관례이고, 남기지 않으면
// (enqueue가 displayEnabled=false로 부르므로) 사용자에게는 "버튼이 아무 일도
// 안 한다"로만 보인다.
MStatus resolveUniqueOrRecord(const MString& name, MSelectionList& out) {
    out.clear();
    if (name.length() == 0 || out.add(name) != MS::kSuccess || out.length() == 0) {
        BoadMaro::error("MaroApplyRemedyCommand.TargetVanished",
                        MString("Maro: '") + name +
                        "' no longer exists; nothing was changed.");
        return MS::kFailure;
    }
    if (out.length() != 1) {
        BoadMaro::error("MaroApplyRemedyCommand.TargetAmbiguous",
                        MString("Maro: '") + name + "' now matches " +
                        MString(std::to_string(out.length()).c_str()) +
                        " objects, so it no longer identifies one thing; nothing was "
                        "changed. Give the node a unique name (or a full DAG path) "
                        "and reproduce the failure to record a fresh fix.");
        return MS::kFailure;
    }
    return MS::kSuccess;
}

// MString(const char*) 기본 생성자는 "로케일의 네이티브 멀티바이트 인코딩"을
// 가정한다(devkit의 MString.h 자체 문서) -- UTF-8이 아니다.
// describeRemedyAction()이 돌려주는 문자열은 한국어를 담은 UTF-8이므로(이
// 프로젝트 소스 전체가 UTF-8이고 최상위 CMakeLists.txt가 /utf-8까지 켠다),
// 기본 생성자로 MString을 만들면 코드페이지가 UTF-8이 아닌 Windows에서 그
// 바이트열이 잘못 해석돼 boad 레코드에 모지바케로 들어간다.
// MaroPanelCommands.cpp가 같은 이유로 같은 헬퍼를 두고 있다.
MString utf8(const std::string& s) {
    MString result;
    result.setUTF8(s.c_str());
    return result;
}

MStatus resolveSequenceArg(const MArgList& args, std::uint64_t& out) {
    MStatus status;
    MSyntax syntax;
    syntax.addFlag(kSequenceFlag, kSequenceFlagLong, MSyntax::kLong);
    MArgDatabase argData(syntax, args, &status);
    if (!status) return status;

    if (!argData.isFlagSet(kSequenceFlag)) {
        MGlobal::displayError("Maro: -sequence is required.");
        return MS::kFailure;
    }
    int sequenceArg = -1;
    argData.getFlagArgument(kSequenceFlag, 0, sequenceArg);
    if (sequenceArg < 0) {
        MGlobal::displayError("Maro: -sequence must not be negative.");
        return MS::kFailure;
    }
    out = static_cast<std::uint64_t>(sequenceArg);
    return MS::kSuccess;
}

}  // namespace

void* MaroDiagRequestRemedyCommand::creator() { return new MaroDiagRequestRemedyCommand(); }

MSyntax MaroDiagRequestRemedyCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag(kSequenceFlag, kSequenceFlagLong, MSyntax::kLong);
    return syntax;
}

MStatus MaroDiagRequestRemedyCommand::doIt(const MArgList& args) {
    try {
        std::uint64_t sequence = 0;
        MStatus status = resolveSequenceArg(args, sequence);
        if (!status) return status;

        DiagRecord rec;
        if (!BoadMaro::findRecordBySequence(sequence, rec)) {
            MGlobal::displayError("Maro: maroDiagRequestRemedy could not resolve sequence.");
            return MS::kFailure;
        }
        if (rec.remedyAction.kind == RemedyActionKind::None) {
            MGlobal::displayError(
                "Maro: maroDiagRequestRemedy: this diagnostic has no recorded fix.");
            return MS::kFailure;
        }

        MaroMainThreadQueue::enqueue([sequence]() {
            // 브리프는 인자 하나짜리 executeCommand를 썼다. 그 오버로드의
            // 기본값은 displayEnabled=false, undoEnabled=false다
            // (devkit MGlobal.h) -- undoEnabled가 false면 maroApplyRemedy는
            // 실행은 되지만 undo 큐에 전혀 올라가지 않는다. 그러면 이
            // 태스크의 존재 이유("Ctrl+Z로 되돌릴 수 있는 해법 적용")가
            // 통째로 무너지고, 사용자가 Ctrl+Z를 눌렀을 때 해법이 아니라
            // 그 앞의 엉뚱한 커맨드가 되돌아간다. undoEnabled를 명시한다.
            MGlobal::executeCommand(
                MString("maroApplyRemedy -sequence ") + MString(std::to_string(sequence).c_str()),
                /*displayEnabled=*/false, /*undoEnabled=*/true);
        });
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroDiagRequestRemedy failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroDiagRequestRemedy failed with unknown error.");
        return MS::kFailure;
    }
}

void* MaroApplyRemedyCommand::creator() { return new MaroApplyRemedyCommand(); }

MSyntax MaroApplyRemedyCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag(kSequenceFlag, kSequenceFlagLong, MSyntax::kLong);
    return syntax;
}

MStatus MaroApplyRemedyCommand::doIt(const MArgList& args) {
    try {
        std::uint64_t sequence = 0;
        MStatus status = resolveSequenceArg(args, sequence);
        if (!status) return status;

        DiagRecord rec;
        if (!BoadMaro::findRecordBySequence(sequence, rec)) {
            MGlobal::displayError("Maro: maroApplyRemedy could not resolve sequence.");
            return MS::kFailure;
        }
        const RemedyAction& remedy = rec.remedyAction;
        if (remedy.kind == RemedyActionKind::None) {
            MGlobal::displayError("Maro: maroApplyRemedy: this diagnostic has no recorded fix.");
            return MS::kFailure;
        }

        // 실행 직전 재확인 (원 스펙 §5) -- 클릭과 실행 사이에 씬이 바뀌었을
        // 수 있다. 여기서 걸러내면 아무것도 바꾸지 않고 실패로 끝난다.
        //
        // 최종 리뷰의 Minor Finding: 예전에는 재확인 블록과 스테이징 블록이
        // switch 두 개로 나뉘어 있어 **같은 이름을 두 번** 풀었다. 두 해석
        // 사이에 씬이 또 바뀌면 확인한 대상과 실제로 손대는 대상이 달라질 수
        // 있고(그 창이 아무리 좁아도 재확인의 존재 이유가 바로 그 창이다),
        // 애초에 같은 일을 두 번 하는 것이기도 하다. switch 하나로 합쳐
        // 이름마다 정확히 한 번 풀고, 그렇게 얻은 MPlug/MObject를 그대로
        // MDGModifier에 넘긴다.
        m_kind = remedy.kind;

        switch (remedy.kind) {
            case RemedyActionKind::SelectNode: {
                MSelectionList resolved;
                status = resolveUniqueOrRecord(MString(remedy.nodeName.c_str()), resolved);
                if (!status) return status;
                // 푼 결과를 그대로 들고 간다 -- redoIt이 이름을 다시 풀지
                // 않도록. 선택은 씬을 편집하지 않으므로 모호한 이름이 여기서
                // 일으키는 피해는 "엉뚱한 것까지 함께 선택된다" 정도지만,
                // 같은 규율을 세 종류 모두에 두는 편이 이 파일을 읽는 다음
                // 사람에게 예외를 설명할 필요가 없어 낫다.
                m_selectTarget = resolved;
                MGlobal::getActiveSelectionList(m_previousSelection);
                break;
            }
            case RemedyActionKind::SetAttribute: {
                const MString nodeName(remedy.nodeName.c_str());
                MSelectionList resolved;
                status = resolveUniqueOrRecord(nodeName, resolved);
                if (!status) return status;
                MObject nodeObj;
                if (!resolved.getDependNode(0, nodeObj) || nodeObj.isNull()) {
                    BoadMaro::error("MaroApplyRemedyCommand.TargetVanished",
                                    MString("Maro: '") + nodeName +
                                    "' no longer resolves to a node; nothing was changed.");
                    return MS::kFailure;
                }
                const MString attrName(remedy.attributeName.c_str());
                MFnDependencyNode fn(nodeObj);
                MStatus plugStatus;
                MPlug plug = fn.findPlug(attrName, false, &plugStatus);
                if (!plugStatus || plug.isNull()) {
                    // 최종 리뷰 Finding I2: 예전에는 여기서 아무 기록 없이
                    // plugStatus만 돌려줬다. 이 커맨드는 큐가
                    // displayEnabled=false로 부르므로 스크립트 에디터에도
                    // 아무것도 안 뜬다 -- 사용자에게는 "버튼을 눌렀는데
                    // 영원히 아무 일도 안 일어난다"로만 보였다. 이 파일의
                    // 다른 실패 경로는 전부 boad에 남긴다.
                    BoadMaro::error("MaroApplyRemedyCommand.AttributeMissing",
                                    MString("Maro: '") + nodeName + "' has no '" +
                                    attrName + "' attribute; nothing was changed.");
                    return MS::kFailure;
                }
                // Round the same way describeRemedyAction() does so the record cannot
                // claim a different number was applied than what actually was.
                m_modifier.newPlugValueInt(plug, static_cast<int>(std::llround(remedy.value)));
                break;
            }
            case RemedyActionKind::Disconnect: {
                const MString src(remedy.sourcePlug.c_str());
                const MString dst(remedy.destPlug.c_str());
                // 이름마다 **따로** 리스트를 쓴다. 하나에 둘을 담고 위치로
                // 집던 예전 방식이 Finding I1 그 자체다 (resolveUniqueOrRecord
                // 주석 참고).
                MSelectionList srcSel;
                status = resolveUniqueOrRecord(src, srcSel);
                if (!status) return status;
                MSelectionList dstSel;
                status = resolveUniqueOrRecord(dst, dstSel);
                if (!status) return status;

                MPlug srcPlug, dstPlug;
                if (!srcSel.getPlug(0, srcPlug) || srcPlug.isNull() ||
                    !dstSel.getPlug(0, dstPlug) || dstPlug.isNull()) {
                    // 이름은 하나로 풀렸지만 플러그가 아니다(노드 이름만 남은
                    // 스테일 레코드 등). 조용히 넘어가면 아래 disconnect가
                    // 널 플러그를 받는다.
                    BoadMaro::error("MaroApplyRemedyCommand.TargetNotAPlug",
                                    MString("Maro: '") + src + "' -> '" + dst +
                                    "' does not resolve to a pair of plugs; nothing "
                                    "was changed.");
                    return MS::kFailure;
                }

                MPlugArray connectedTo;
                dstPlug.connectedTo(connectedTo, true, false);
                bool stillConnected = false;
                for (unsigned int i = 0; i < connectedTo.length(); ++i) {
                    if (connectedTo[i] == srcPlug) {
                        stillConnected = true;
                        break;
                    }
                }
                if (!stillConnected) {
                    BoadMaro::error("MaroApplyRemedyCommand.AlreadyDisconnected",
                                    MString("Maro: '") + src + "' -> '" + dst +
                                    "' is already disconnected; nothing was changed.");
                    return MS::kFailure;
                }
                m_modifier.disconnect(srcPlug, dstPlug);
                break;
            }
            case RemedyActionKind::None:
                break;  // 위에서 이미 걸러졌다.
        }

        m_stagedChange = true;
        status = redoIt();
        if (status) {
            BoadMaro::info(MString("Maro: applied remedy for sequence ") +
                          MString(std::to_string(sequence).c_str()) + ": " +
                          utf8(describeRemedyAction(remedy)));
        }
        return status;
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroApplyRemedy failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroApplyRemedy failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroApplyRemedyCommand::redoIt() {
    try {
        switch (m_kind) {
            case RemedyActionKind::SelectNode:
                // 이름을 다시 풀지 않는다. doIt이 이미 정확히 하나로 풀어
                // 검증한 리스트를 그대로 재생한다 -- 여기에 이름 해석을 또
                // 두면(초안) 노드가 사라진 경우를 doIt의 재확인 대신 여기서
                // 먼저 잡아, 정작 원 스펙 §5가 요구하는 "실행 직전 재확인"이
                // 있으나 마나 한 코드가 되고 그 재확인을 통째로 지워도
                // test_remedy_apply가 그대로 통과했다 -- 방어를 하나 더 둔 게
                // 아니라 진짜 방어선을 테스트에서 가려 버린 것이었다. 이
                // 경로(undo 뒤 redo 사이에 노드가 사라짐)는 Maya가 새 커맨드
                // 실행 시 redo 스택을 비우므로 실질적으로 도달할 수 없다.
                // 재확인은 doIt 한 곳에만 둔다.
                return MGlobal::setActiveSelectionList(m_selectTarget, MGlobal::kReplaceList);
            case RemedyActionKind::SetAttribute:
            case RemedyActionKind::Disconnect:
                return m_modifier.doIt();
            case RemedyActionKind::None:
                return MS::kFailure;
        }
        return MS::kFailure;
    } catch (const std::exception& e) {
        BoadMaro::error("MaroApplyRemedyCommand.redoIt.Exception",
                        MString("Maro: maroApplyRemedy redo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        BoadMaro::error("MaroApplyRemedyCommand.redoIt.UnknownException",
                        "Maro: maroApplyRemedy redo failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroApplyRemedyCommand::undoIt() {
    try {
        switch (m_kind) {
            case RemedyActionKind::SelectNode:
                return MGlobal::setActiveSelectionList(m_previousSelection,
                                                        MGlobal::kReplaceList);
            case RemedyActionKind::SetAttribute:
            case RemedyActionKind::Disconnect:
                return m_modifier.undoIt();
            case RemedyActionKind::None:
                return MS::kFailure;
        }
        return MS::kFailure;
    } catch (const std::exception& e) {
        BoadMaro::error("MaroApplyRemedyCommand.undoIt.Exception",
                        MString("Maro: maroApplyRemedy undo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        BoadMaro::error("MaroApplyRemedyCommand.undoIt.UnknownException",
                        "Maro: maroApplyRemedy undo failed with unknown error.");
        return MS::kFailure;
    }
}

}  // namespace maro
