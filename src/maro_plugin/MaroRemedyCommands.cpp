#include "MaroRemedyCommands.h"

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

// name이 지금 씬에 있는지. 노드든 "node.attribute" 플러그든 같은 방법으로
// 확인한다 (MaroPanelCommands.cpp의 nameStillExists와 같은 이유 -- 이
// 파일은 그것을 재사용하지 않는다. 그 함수가 익명 네임스페이스 안에
// 있어 다른 번역 단위에서 못 보기 때문이다. 로직이 세 줄이라 중복의
// 비용보다 새 공개 헤더를 만드는 비용이 크다).
bool nameStillExists(const MString& name) {
    if (name.length() == 0) return false;
    MSelectionList sel;
    return sel.add(name) == MS::kSuccess;
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
        switch (remedy.kind) {
            case RemedyActionKind::SelectNode:
            case RemedyActionKind::SetAttribute: {
                const MString nodeName(remedy.nodeName.c_str());
                if (!nameStillExists(nodeName)) {
                    BoadMaro::error("MaroApplyRemedyCommand.TargetVanished",
                                    MString("Maro: '") + nodeName +
                                    "' no longer exists; nothing was changed.");
                    return MS::kFailure;
                }
                break;
            }
            case RemedyActionKind::Disconnect: {
                const MString src(remedy.sourcePlug.c_str());
                const MString dst(remedy.destPlug.c_str());
                if (!nameStillExists(src) || !nameStillExists(dst)) {
                    BoadMaro::error("MaroApplyRemedyCommand.TargetVanished",
                                    MString("Maro: '") + src + "' -> '" + dst +
                                    "' no longer both exist; nothing was changed.");
                    return MS::kFailure;
                }
                MSelectionList sel;
                sel.add(src);
                sel.add(dst);
                MPlug srcPlug, dstPlug;
                sel.getPlug(0, srcPlug);
                sel.getPlug(1, dstPlug);
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
                break;
            }
            case RemedyActionKind::None:
                break;  // 위에서 이미 걸러졌다.
        }

        m_kind = remedy.kind;

        switch (remedy.kind) {
            case RemedyActionKind::SelectNode: {
                m_selectNodeName = MString(remedy.nodeName.c_str());
                MGlobal::getActiveSelectionList(m_previousSelection);
                break;
            }
            case RemedyActionKind::SetAttribute: {
                MSelectionList sel;
                sel.add(MString(remedy.nodeName.c_str()));
                MObject nodeObj;
                sel.getDependNode(0, nodeObj);
                MFnDependencyNode fn(nodeObj);
                MStatus plugStatus;
                MPlug plug = fn.findPlug(MString(remedy.attributeName.c_str()), false,
                                         &plugStatus);
                if (!plugStatus) return plugStatus;
                m_modifier.newPlugValueInt(plug, static_cast<int>(remedy.value));
                break;
            }
            case RemedyActionKind::Disconnect: {
                MSelectionList sel;
                sel.add(MString(remedy.sourcePlug.c_str()));
                sel.add(MString(remedy.destPlug.c_str()));
                MPlug srcPlug, dstPlug;
                sel.getPlug(0, srcPlug);
                sel.getPlug(1, dstPlug);
                m_modifier.disconnect(srcPlug, dstPlug);
                break;
            }
            case RemedyActionKind::None:
                break;
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
            case RemedyActionKind::SelectNode: {
                MSelectionList sel;
                // add()의 상태를 따로 확인하지 않는다. 이 자리에 확인을 넣어
                // 봤더니(초안) 노드가 사라진 경우를 doIt의 재확인 대신 여기서
                // 먼저 잡아, 정작 원 스펙 §5가 요구하는 "실행 직전 재확인"이
                // 있으나 마나 한 코드가 되고 그 재확인을 통째로 지워도
                // test_remedy_apply가 그대로 통과했다 -- 방어를 하나 더 둔 게
                // 아니라 진짜 방어선을 테스트에서 가려 버린 것이었다. 이
                // 경로(undo 뒤 redo 사이에 노드가 사라짐)는 Maya가 새 커맨드
                // 실행 시 redo 스택을 비우므로 실질적으로 도달할 수 없다.
                // 재확인은 doIt 한 곳에만 둔다.
                sel.add(m_selectNodeName);
                return MGlobal::setActiveSelectionList(sel, MGlobal::kReplaceList);
            }
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
