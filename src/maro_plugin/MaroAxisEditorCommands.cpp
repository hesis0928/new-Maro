#include "MaroAxisEditorCommands.h"

#include <sstream>

#include <maya/MArgDatabase.h>
#include <maya/MArgList.h>
#include <maya/MDagPath.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MItDependencyNodes.h>
#include <maya/MPlugArray.h>
#include <maya/MSelectionList.h>
#include <maya/MStringArray.h>

#include "MaroAxisNode.h"
#include "MaroDiag.h"

namespace maro {

namespace {

const char* kCapabilitiesFlag = "-cap";
const char* kCapabilitiesFlagLong = "-capabilities";

// 축 하나에 바인딩된 타겟 트랜스폼의 전체 경로를 돌려준다. 없으면 빈 문자열.
// aTargetObject는 message라 connectedTo로만 얻을 수 있다
// (MaroBindAxisCommand::doIt과 같은 패턴).
MString boundTargetPath(const MFnDependencyNode& axisFn) {
    MPlugArray sources;
    axisFn.findPlug(MaroAxisNode::aTargetObject, false).connectedTo(sources, true, false);
    if (sources.length() == 0) return MString();
    MFnDependencyNode targetFn(sources[0].node());
    MDagPath path;
    if (MDagPath::getAPathTo(sources[0].node(), path) == MS::kSuccess) {
        return path.fullPathName();
    }
    return targetFn.name();
}

MString parentAxisPath(const MFnDependencyNode& axisFn) {
    MPlugArray sources;
    axisFn.findPlug(MaroAxisNode::aParentAxis, false).connectedTo(sources, true, false);
    if (sources.length() == 0) return MString();
    MDagPath path;
    if (MDagPath::getAPathTo(sources[0].node(), path) == MS::kSuccess) {
        return path.fullPathName();
    }
    return MFnDependencyNode(sources[0].node()).name();
}

// [태스크 리뷰에서 발견] "occupied"의 뜻이 이 함수와 listCapabilities()에서
// 일부러 다르다 -- 여기(축 목록의 요약 필드)는 실제로 연결된 슬롯만 센다.
// listCapabilities()(-capabilities 모드)는 연결 여부와 무관하게 존재하는
// 물리 슬롯을 전부 행으로 낸다(각 행의 "connected" 필드로 구분). 이건
// 사고가 아니라 의도된 설계다: 향후 maroDisconnectCapability(Task 6)는
// 연결만 끊고 배열 원소 자체는 지우지 않기로 결정됐다(재사용/되돌리기
// 단순화를 위해) -- 그 슬롯이 이 요약 카운트에는 안 잡히되
// -capabilities 상세 목록에는 "connected=0"으로 계속 보이는 게 맞는
// 동작이다. 두 값이 다르게 나오는 것 자체가 버그가 아니라는 뜻이며,
// UI(Task 7/8)는 이 요약 카운트를 "지금 실제로 구동에 기여하는 슬롯 수"로
// 표시하면 된다.
unsigned int occupiedCapabilityCount(MPlug capabilityInPlug) {
    unsigned int count = 0;
    const unsigned int total = capabilityInPlug.evaluateNumElements();
    for (unsigned int i = 0; i < total; ++i) {
        MPlugArray sources;
        capabilityInPlug.elementByPhysicalIndex(i).connectedTo(sources, true, false);
        if (sources.length() > 0) ++count;
    }
    return count;
}

MStatus listAxes(MStringArray& result) {
    for (MItDependencyNodes it(MFn::kPluginLocatorNode); !it.isDone(); it.next()) {
        MFnDependencyNode axisFn(it.thisNode());
        if (axisFn.typeId() != MaroAxisNode::id) continue;

        MDagPath axisPath;
        MString axisFullPath = axisFn.name();
        if (MDagPath::getAPathTo(it.thisNode(), axisPath) == MS::kSuccess) {
            axisFullPath = axisPath.fullPathName();
        }

        result.append(axisFullPath);
        result.append(axisFn.findPlug(MaroAxisNode::aJointName, false).asString());
        result.append(boundTargetPath(axisFn));
        result.append(parentAxisPath(axisFn));
        result.append(MString() + axisFn.findPlug(MaroAxisNode::aControlMode, false).asShort());
        result.append(axisFn.findPlug(MaroAxisNode::aEnabled, false).asBool() ? "1" : "0");
        result.append(MString() + axisFn.findPlug(MaroAxisNode::aConventionAxis, false).asShort());
        result.append(MString() + static_cast<int>(occupiedCapabilityCount(
            axisFn.findPlug(MaroAxisNode::aCapabilityIn, false))));
    }
    return MS::kSuccess;
}

// occupiedCapabilityCount()와 "occupied"의 뜻이 다르다 -- 이 함수는 연결
// 여부와 무관하게 존재하는 물리 슬롯을 전부 낸다(각 행의 마지막 필드가
// 연결 여부). occupiedCapabilityCount() 주석 참고 -- 의도된 설계다.
MStatus listCapabilities(const MString& axisName, MStringArray& result) {
    MSelectionList selection;
    if (!selection.add(axisName)) {
        maro::BoadMaro::error(
            "MaroListAxisNodesCommand.AxisNotFound",
            MString("Maro: cannot find node '") + axisName + "'.",
            maro::onfix::capture("", "", axisName));
        return MS::kFailure;
    }
    MObject axisObj;
    selection.getDependNode(0, axisObj);
    MFnDependencyNode axisFn(axisObj);
    if (axisFn.typeId() != MaroAxisNode::id) {
        maro::BoadMaro::error(
            "MaroListAxisNodesCommand.NotMaroAxisNode",
            MString("Maro: '") + axisName + "' is not a maroAxis node.",
            maro::onfix::capture(axisFn.typeName(), "", axisName));
        return MS::kFailure;
    }

    MPlug capabilityIn = axisFn.findPlug(MaroAxisNode::aCapabilityIn, false);
    const unsigned int total = capabilityIn.evaluateNumElements();
    for (unsigned int i = 0; i < total; ++i) {
        MPlug element = capabilityIn.elementByPhysicalIndex(i);
        MPlugArray sources;
        element.connectedTo(sources, true, false);

        result.append(MString() + static_cast<int>(element.logicalIndex()));
        if (sources.length() > 0) {
            MFnDependencyNode capFn(sources[0].node());
            MDagPath capPath;
            MString capName = capFn.name();
            if (MDagPath::getAPathTo(sources[0].node(), capPath) == MS::kSuccess) {
                capName = capPath.fullPathName();
            }
            result.append(capName);
            result.append(capFn.typeName());
        } else {
            result.append("");
            result.append("");
        }
        result.append(MString() + element.child(MaroAxisNode::aCapType).asShort());
        result.append(sources.length() > 0 ? "1" : "0");
    }
    return MS::kSuccess;
}

}  // namespace

// Task 6이 재사용하는 헬퍼 -- 이 커맨드 파일에 두는 이유는 쿼리(위
// listCapabilities)와 같은 순회 패턴을 공유해서다.
unsigned int nextFreeCapabilitySlot(MPlug capabilityInPlug) {
    const unsigned int count = capabilityInPlug.evaluateNumElements();
    for (unsigned int i = 0; i < count; ++i) {
        MPlug element = capabilityInPlug.elementByPhysicalIndex(i);
        MPlugArray sources;
        element.connectedTo(sources, true, false);
        if (sources.length() == 0) {
            return element.logicalIndex();
        }
    }
    return count;  // 빈 슬롯이 없으면 다음 논리 인덱스에 새로 만든다
}

bool hasPrimaryDriver(MPlug capabilityInPlug) {
    const unsigned int count = capabilityInPlug.evaluateNumElements();
    for (unsigned int i = 0; i < count; ++i) {
        MPlug element = capabilityInPlug.elementByPhysicalIndex(i);
        MPlugArray sources;
        element.connectedTo(sources, true, false);
        if (sources.length() == 0) continue;

        const short existingType = element.child(MaroAxisNode::aCapType).asShort();
        if (existingType == 0 || existingType == 4 ||
            existingType == 6 || existingType == 7) {
            return true;
        }
    }
    return false;
}

void* MaroListAxisNodesCommand::creator() {
    return new MaroListAxisNodesCommand();
}

MSyntax MaroListAxisNodesCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag(kCapabilitiesFlag, kCapabilitiesFlagLong, MSyntax::kString);
    return syntax;
}

MStatus MaroListAxisNodesCommand::doIt(const MArgList& args) {
    maro::ScopedCommandContext ctxMarker("MaroListAxisNodesCommand");
    try {
        MStatus status;
        MArgDatabase argData(syntax(), args, &status);
        if (!status) return status;

        MStringArray result;
        if (argData.isFlagSet(kCapabilitiesFlag)) {
            MString axisName;
            argData.getFlagArgument(kCapabilitiesFlag, 0, axisName);
            status = listCapabilities(axisName, result);
            if (!status) return status;
        } else {
            status = listAxes(result);
            if (!status) return status;
        }

        setResult(result);
        return MS::kSuccess;
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroListAxisNodesCommand.doIt.Exception",
                              MString("Maro: maroListAxisNodes failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroListAxisNodesCommand.doIt.UnknownException",
                              "Maro: maroListAxisNodes failed with unknown error.");
        return MS::kFailure;
    }
}

namespace {

// -type 플래그 문자열 <-> 커맨드로 생성 가능한 capability 노드 타입 이름
// 매핑. isPrimaryDriver가 true인 타입만 §3 상호배타 검사 대상이다.
//
// flagName(짧은 이름, 예: "rotation")은 사용자가 -type에 넘기는 값이고,
// nodeTypeName(실제 등록된 Maya 노드 타입, 예: "maroRotation")은
// MDGModifier::createNode()에 넘기는 값이자 기존에 만들어진 capability
// 노드의 MFnDependencyNode::typeName()과 비교하는 값이다. 이 둘은 서로
// 다른 문자열이므로(MaroPluginMain.cpp의 kCapabilities 등록 목록 참고)
// 별도 필드로 갖는다 -- 하나로 합치면 maroConnectCapability가 기존
// 노드의 typeName()("maroRotation")을 -type 짧은 이름("rotation") 목록에서
// 못 찾아 항상 실패한다.
struct CapabilityTypeInfo {
    const char* flagName;
    const char* nodeTypeName;
    bool isPrimaryDriver;
};

const CapabilityTypeInfo kCapabilityTypes[] = {
    {"rotation", "maroRotation", true},
    {"translation", "maroTranslation", true},
    {"limit", "maroLimit", false},
    {"translationLimit", "maroTranslationLimit", false},
    {"sensorDirection", "maroSensorDirection", false},
    {"sensorRange", "maroSensorRange", false},
    {"coupling", "maroCoupling", true},
};

const CapabilityTypeInfo* findCapabilityTypeByFlag(const MString& flagValue) {
    for (const auto& info : kCapabilityTypes) {
        if (flagValue == info.flagName) return &info;
    }
    return nullptr;
}

const CapabilityTypeInfo* findCapabilityTypeByNodeType(const MString& nodeType) {
    for (const auto& info : kCapabilityTypes) {
        if (nodeType == info.nodeTypeName) return &info;
    }
    return nullptr;
}

}  // namespace

// ============================== maroAddCapability ==============================

void* MaroAddCapabilityCommand::creator() { return new MaroAddCapabilityCommand(); }

MSyntax MaroAddCapabilityCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag("-typ", "-type", MSyntax::kString);
    syntax.setObjectType(MSyntax::kSelectionList, 1, 1);
    return syntax;
}

MStatus MaroAddCapabilityCommand::doIt(const MArgList& args) {
    maro::ScopedCommandContext ctxMarker("MaroAddCapabilityCommand");
    try {
        MStatus status;
        MArgDatabase argData(syntax(), args, &status);
        if (!status) return status;

        if (!argData.isFlagSet("-typ")) {
            maro::BoadMaro::error(
                "MaroAddCapabilityCommand.MissingType",
                "Maro: maroAddCapability requires -type <rotation|translation|"
                "limit|translationLimit|sensorDirection|sensorRange|coupling>.",
                maro::onfix::capture("", "", ""));
            return MS::kFailure;
        }
        MString typeName;
        argData.getFlagArgument("-typ", 0, typeName);
        const CapabilityTypeInfo* info = findCapabilityTypeByFlag(typeName);
        if (info == nullptr) {
            maro::BoadMaro::error(
                "MaroAddCapabilityCommand.UnknownType",
                MString("Maro: unknown capability type '") + typeName + "'.",
                maro::onfix::capture("", "", ""));
            return MS::kFailure;
        }

        MSelectionList axisSelection;
        argData.getObjects(axisSelection);
        if (axisSelection.length() != 1) {
            maro::BoadMaro::error(
                "MaroAddCapabilityCommand.WrongArgCount",
                "Maro: maroAddCapability needs exactly one argument: <axis>.",
                maro::onfix::capture("", "", ""));
            return MS::kFailure;
        }
        MObject axisObj;
        axisSelection.getDependNode(0, axisObj);
        MFnDependencyNode axisFn(axisObj);
        if (axisFn.typeId() != MaroAxisNode::id) {
            maro::BoadMaro::error(
                "MaroAddCapabilityCommand.NotMaroAxisNode",
                MString("Maro: '") + axisFn.name() + "' is not a maroAxis node.",
                maro::onfix::capture(axisFn.typeName(), "", axisFn.name()));
            return MS::kFailure;
        }

        MPlug capabilityIn = axisFn.findPlug(MaroAxisNode::aCapabilityIn, false);
        if (info->isPrimaryDriver && hasPrimaryDriver(capabilityIn)) {
            maro::BoadMaro::error(
                "MaroAddCapabilityCommand.PrimaryDriverConflict",
                MString("Maro: '") + axisFn.name() +
                "' already has a primary drive capability (rotation/translation/"
                "coupling). An axis carries exactly one.",
                maro::onfix::capture(axisFn.typeName(), "capabilityIn", axisFn.name()));
            return MS::kFailure;
        }

        const unsigned int slot = nextFreeCapabilitySlot(capabilityIn);
        MObject capNode = m_modifier.createNode(info->nodeTypeName, &status);
        if (!status || capNode.isNull()) {
            maro::BoadMaro::error(
                "MaroAddCapabilityCommand.CreateNodeFailed",
                MString("Maro: failed to create a '") + info->nodeTypeName + "' node.",
                maro::onfix::capture(info->nodeTypeName, "", axisFn.name()));
            return MS::kFailure;
        }
        MFnDependencyNode capFn(capNode);
        MPlug capOut = capFn.findPlug("capabilityOut", false, &status);
        if (!status) return status;
        MPlug capIn = capabilityIn.elementByLogicalIndex(slot);
        status = m_modifier.connect(capOut, capIn);
        if (!status) return status;

        m_stagedChange = true;
        status = redoIt();
        if (!status) return status;

        // capFn.name()은 createNode() 직후가 아니라 doIt()으로 실제
        // dependency graph에 편입된 뒤에 물어봐야 한다 -- createNode()가
        // 반환하는 MObject는 그 시점에 아직 DG에 이름이 등록되지 않은
        // "limbo" 상태라 name()이 빈 문자열을 준다(실측: doIt() 전에
        // 물어보면 setResult가 빈 문자열을 냈다).
        m_capNodeName = capFn.name();
        // setResult(const MString&)는 파이썬 쪽에서 스칼라 문자열로
        // 돌아온다 -- 인터페이스 계약(§"새 노드 이름 반환")과 테스트가
        // cmds.maroAddCapability(...)[0] 형태(리스트)를 기대하므로, 원소
        // 하나짜리 MStringArray로 감싸 setResult한다.
        MStringArray resultArr;
        resultArr.append(m_capNodeName);
        setResult(resultArr);
        return MS::kSuccess;
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroAddCapabilityCommand.doIt.Exception",
                              MString("Maro: maroAddCapability failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroAddCapabilityCommand.doIt.UnknownException",
                              "Maro: maroAddCapability failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroAddCapabilityCommand::redoIt() {
    maro::ScopedCommandContext ctxMarker("MaroAddCapabilityCommand");
    try {
        return m_modifier.doIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroAddCapabilityCommand.redoIt.Exception",
                              MString("Maro: maroAddCapability redo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroAddCapabilityCommand.redoIt.UnknownException",
                              "Maro: maroAddCapability redo failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroAddCapabilityCommand::undoIt() {
    maro::ScopedCommandContext ctxMarker("MaroAddCapabilityCommand");
    try {
        return m_modifier.undoIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroAddCapabilityCommand.undoIt.Exception",
                              MString("Maro: maroAddCapability undo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroAddCapabilityCommand.undoIt.UnknownException",
                              "Maro: maroAddCapability undo failed with unknown error.");
        return MS::kFailure;
    }
}

// ============================== maroConnectCapability ==============================

void* MaroConnectCapabilityCommand::creator() { return new MaroConnectCapabilityCommand(); }

MSyntax MaroConnectCapabilityCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag("-idx", "-index", MSyntax::kLong);
    syntax.setObjectType(MSyntax::kSelectionList, 2, 2);
    return syntax;
}

MStatus MaroConnectCapabilityCommand::doIt(const MArgList& args) {
    maro::ScopedCommandContext ctxMarker("MaroConnectCapabilityCommand");
    try {
        MStatus status;
        MArgDatabase argData(syntax(), args, &status);
        if (!status) return status;

        MSelectionList selection;
        argData.getObjects(selection);
        if (selection.length() != 2) {
            maro::BoadMaro::error(
                "MaroConnectCapabilityCommand.WrongArgCount",
                "Maro: maroConnectCapability needs exactly two arguments: "
                "<capabilityNode> <axis>.",
                maro::onfix::capture("", "", ""));
            return MS::kFailure;
        }
        MObject capNode, axisObj;
        selection.getDependNode(0, capNode);
        selection.getDependNode(1, axisObj);

        MFnDependencyNode axisFn(axisObj);
        if (axisFn.typeId() != MaroAxisNode::id) {
            maro::BoadMaro::error(
                "MaroConnectCapabilityCommand.NotMaroAxisNode",
                MString("Maro: '") + axisFn.name() + "' is not a maroAxis node.",
                maro::onfix::capture(axisFn.typeName(), "", axisFn.name()));
            return MS::kFailure;
        }

        MFnDependencyNode capFn(capNode);
        const CapabilityTypeInfo* info = findCapabilityTypeByNodeType(capFn.typeName());
        if (info == nullptr) {
            maro::BoadMaro::error(
                "MaroConnectCapabilityCommand.NotCapabilityNode",
                MString("Maro: '") + capFn.name() + "' is not a capability node type.",
                maro::onfix::capture(capFn.typeName(), "", axisFn.name()));
            return MS::kFailure;
        }
        MPlug capOut = capFn.findPlug("capabilityOut", false, &status);
        if (!status) return status;
        MPlugArray existingDest;
        capOut.connectedTo(existingDest, false, true);
        if (existingDest.length() > 0) {
            maro::RemedyAction remedy;
            remedy.kind = maro::RemedyActionKind::Disconnect;
            remedy.sourcePlug = capOut.name().asChar();
            remedy.destPlug = existingDest[0].name().asChar();
            maro::BoadMaro::error(
                "MaroConnectCapabilityCommand.AlreadyConnected",
                MString("Maro: '") + capFn.name() +
                "' is already connected to another axis. Disconnect it first.",
                maro::onfix::capture(capFn.typeName(), "", axisFn.name()), remedy);
            return MS::kFailure;
        }

        MPlug capabilityIn = axisFn.findPlug(MaroAxisNode::aCapabilityIn, false);
        if (info->isPrimaryDriver && hasPrimaryDriver(capabilityIn)) {
            maro::BoadMaro::error(
                "MaroConnectCapabilityCommand.PrimaryDriverConflict",
                MString("Maro: '") + axisFn.name() +
                "' already has a primary drive capability. An axis carries exactly one.",
                maro::onfix::capture(axisFn.typeName(), "capabilityIn", axisFn.name()));
            return MS::kFailure;
        }

        unsigned int slot;
        if (argData.isFlagSet("-idx")) {
            int requested = 0;
            argData.getFlagArgument("-idx", 0, requested);
            if (requested < 0) {
                maro::BoadMaro::error(
                    "MaroConnectCapabilityCommand.NegativeIndex",
                    "Maro: -index must not be negative.",
                    maro::onfix::capture(axisFn.typeName(), "capabilityIn", axisFn.name()));
                return MS::kFailure;
            }
            slot = static_cast<unsigned int>(requested);
            MPlugArray occupiedCheck;
            capabilityIn.elementByLogicalIndex(slot).connectedTo(occupiedCheck, true, false);
            if (occupiedCheck.length() > 0) {
                maro::BoadMaro::error(
                    "MaroConnectCapabilityCommand.IndexOccupied",
                    MString("Maro: capabilityIn[") + static_cast<int>(slot) +
                    "] is already occupied.",
                    maro::onfix::capture(axisFn.typeName(), "capabilityIn", axisFn.name()));
                return MS::kFailure;
            }
        } else {
            slot = nextFreeCapabilitySlot(capabilityIn);
        }

        status = m_modifier.connect(capOut, capabilityIn.elementByLogicalIndex(slot));
        if (!status) return status;

        m_stagedChange = true;
        return redoIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroConnectCapabilityCommand.doIt.Exception",
                              MString("Maro: maroConnectCapability failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroConnectCapabilityCommand.doIt.UnknownException",
                              "Maro: maroConnectCapability failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroConnectCapabilityCommand::redoIt() {
    maro::ScopedCommandContext ctxMarker("MaroConnectCapabilityCommand");
    try {
        return m_modifier.doIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroConnectCapabilityCommand.redoIt.Exception",
                              MString("Maro: maroConnectCapability redo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroConnectCapabilityCommand.redoIt.UnknownException",
                              "Maro: maroConnectCapability redo failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroConnectCapabilityCommand::undoIt() {
    maro::ScopedCommandContext ctxMarker("MaroConnectCapabilityCommand");
    try {
        return m_modifier.undoIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroConnectCapabilityCommand.undoIt.Exception",
                              MString("Maro: maroConnectCapability undo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroConnectCapabilityCommand.undoIt.UnknownException",
                              "Maro: maroConnectCapability undo failed with unknown error.");
        return MS::kFailure;
    }
}

// ============================== maroDisconnectCapability ==============================

void* MaroDisconnectCapabilityCommand::creator() { return new MaroDisconnectCapabilityCommand(); }

MSyntax MaroDisconnectCapabilityCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag("-idx", "-index", MSyntax::kLong);
    syntax.setObjectType(MSyntax::kSelectionList, 1, 1);
    return syntax;
}

MStatus MaroDisconnectCapabilityCommand::doIt(const MArgList& args) {
    maro::ScopedCommandContext ctxMarker("MaroDisconnectCapabilityCommand");
    try {
        MStatus status;
        MArgDatabase argData(syntax(), args, &status);
        if (!status) return status;

        if (!argData.isFlagSet("-idx")) {
            maro::BoadMaro::error(
                "MaroDisconnectCapabilityCommand.MissingIndex",
                "Maro: maroDisconnectCapability requires -index <int>.",
                maro::onfix::capture("", "", ""));
            return MS::kFailure;
        }

        // getObjects()는 kSelectionList 오브젝트 인자를 이미 MSelectionList로
        // 준다 -- 이름을 문자열로 다시 뽑아 resolveAxis()로 재해석할 필요가
        // 없다(브리프 리뷰에서 확인된 단순화, YAGNI로 resolveAxis 자체를
        // 삭제했다).
        MSelectionList selection;
        argData.getObjects(selection);
        MObject axisObj;
        selection.getDependNode(0, axisObj);
        MFnDependencyNode axisFn(axisObj);
        if (axisFn.typeId() != MaroAxisNode::id) {
            maro::BoadMaro::error(
                "MaroDisconnectCapabilityCommand.NotMaroAxisNode",
                MString("Maro: '") + axisFn.name() + "' is not a maroAxis node.",
                maro::onfix::capture(axisFn.typeName(), "", axisFn.name()));
            return MS::kFailure;
        }

        int index = 0;
        argData.getFlagArgument("-idx", 0, index);
        if (index < 0) {
            maro::BoadMaro::error(
                "MaroDisconnectCapabilityCommand.NegativeIndex",
                "Maro: -index must not be negative.",
                maro::onfix::capture(axisFn.typeName(), "capabilityIn", axisFn.name()));
            return MS::kFailure;
        }

        MPlug capabilityIn = axisFn.findPlug(MaroAxisNode::aCapabilityIn, false);
        MPlug element = capabilityIn.elementByLogicalIndex(static_cast<unsigned int>(index));
        MPlugArray sources;
        element.connectedTo(sources, true, false);
        if (sources.length() == 0) {
            maro::BoadMaro::error(
                "MaroDisconnectCapabilityCommand.NotConnected",
                MString("Maro: capabilityIn[") + index + "] is not connected.",
                maro::onfix::capture(axisFn.typeName(), "capabilityIn", axisFn.name()));
            return MS::kFailure;
        }

        status = m_modifier.disconnect(sources[0], element);
        if (!status) return status;

        m_stagedChange = true;
        return redoIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroDisconnectCapabilityCommand.doIt.Exception",
                              MString("Maro: maroDisconnectCapability failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroDisconnectCapabilityCommand.doIt.UnknownException",
                              "Maro: maroDisconnectCapability failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroDisconnectCapabilityCommand::redoIt() {
    maro::ScopedCommandContext ctxMarker("MaroDisconnectCapabilityCommand");
    try {
        return m_modifier.doIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroDisconnectCapabilityCommand.redoIt.Exception",
                              MString("Maro: maroDisconnectCapability redo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroDisconnectCapabilityCommand.redoIt.UnknownException",
                              "Maro: maroDisconnectCapability redo failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroDisconnectCapabilityCommand::undoIt() {
    maro::ScopedCommandContext ctxMarker("MaroDisconnectCapabilityCommand");
    try {
        return m_modifier.undoIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroDisconnectCapabilityCommand.undoIt.Exception",
                              MString("Maro: maroDisconnectCapability undo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroDisconnectCapabilityCommand.undoIt.UnknownException",
                              "Maro: maroDisconnectCapability undo failed with unknown error.");
        return MS::kFailure;
    }
}

// ============================== maroUnbindAxis ==============================

void* MaroUnbindAxisCommand::creator() { return new MaroUnbindAxisCommand(); }

MSyntax MaroUnbindAxisCommand::newSyntax() {
    MSyntax syntax;
    syntax.setObjectType(MSyntax::kSelectionList, 1, 1);
    return syntax;
}

MStatus MaroUnbindAxisCommand::doIt(const MArgList& args) {
    maro::ScopedCommandContext ctxMarker("MaroUnbindAxisCommand");
    try {
        MStatus status;
        MSelectionList selection;
        for (unsigned int i = 0; i < args.length(); ++i) {
            MString name = args.asString(i, &status);
            if (!status) return status;
            if (!selection.add(name)) {
                maro::BoadMaro::error(
                    "MaroUnbindAxisCommand.NodeNotFound",
                    MString("Maro: cannot find node '") + name + "'.",
                    maro::onfix::capture("", "", name));
                return MS::kFailure;
            }
        }
        if (selection.length() != 1) {
            maro::BoadMaro::error(
                "MaroUnbindAxisCommand.WrongArgCount",
                "Maro: maroUnbindAxis needs exactly one argument: <axis>.",
                maro::onfix::capture("", "", ""));
            return MS::kFailure;
        }

        MObject axisObj;
        selection.getDependNode(0, axisObj);
        MFnDependencyNode axisFn(axisObj);
        if (axisFn.typeId() != MaroAxisNode::id) {
            maro::BoadMaro::error(
                "MaroUnbindAxisCommand.NotMaroAxisNode",
                MString("Maro: '") + axisFn.name() + "' is not a maroAxis node.",
                maro::onfix::capture(axisFn.typeName(), "", axisFn.name()));
            return MS::kFailure;
        }

        MPlug axisTarget = axisFn.findPlug(MaroAxisNode::aTargetObject, false);
        MPlugArray sources;
        axisTarget.connectedTo(sources, true, false);
        if (sources.length() == 0) {
            maro::BoadMaro::error(
                "MaroUnbindAxisCommand.NotBound",
                MString("Maro: '") + axisFn.name() + "' is not bound to anything.",
                maro::onfix::capture(axisFn.typeName(), "targetObject", axisFn.name()));
            return MS::kFailure;
        }

        status = m_modifier.disconnect(sources[0], axisTarget);
        if (!status) return status;

        m_stagedChange = true;
        return redoIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroUnbindAxisCommand.doIt.Exception",
                              MString("Maro: maroUnbindAxis failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroUnbindAxisCommand.doIt.UnknownException",
                              "Maro: maroUnbindAxis failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroUnbindAxisCommand::redoIt() {
    maro::ScopedCommandContext ctxMarker("MaroUnbindAxisCommand");
    try {
        return m_modifier.doIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroUnbindAxisCommand.redoIt.Exception",
                              MString("Maro: maroUnbindAxis redo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroUnbindAxisCommand.redoIt.UnknownException",
                              "Maro: maroUnbindAxis redo failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroUnbindAxisCommand::undoIt() {
    maro::ScopedCommandContext ctxMarker("MaroUnbindAxisCommand");
    try {
        return m_modifier.undoIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroUnbindAxisCommand.undoIt.Exception",
                              MString("Maro: maroUnbindAxis undo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroUnbindAxisCommand.undoIt.UnknownException",
                              "Maro: maroUnbindAxis undo failed with unknown error.");
        return MS::kFailure;
    }
}

}  // namespace maro
