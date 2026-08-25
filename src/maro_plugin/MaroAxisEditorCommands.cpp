#include "MaroAxisEditorCommands.h"

#include <sstream>

#include <maya/MArgDatabase.h>
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

}  // namespace maro
