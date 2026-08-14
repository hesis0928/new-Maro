#include <maya/MFnPlugin.h>
#include <maya/MGlobal.h>
#include <maya/MStatus.h>

#include "MaroAxisNode.h"
#include "MaroCapabilityNodes.h"
#include "MaroCommandDeviceNode.h"
#include "MaroCommands.h"
#include "MaroDeleteWatcher.h"
#include "MaroDiag.h"
#include "MaroDiagCommands.h"

namespace {
constexpr char kVendor[] = "Maro";
constexpr char kVersion[] = "0.1.0";
}  // namespace

MStatus initializePlugin(MObject obj) {
    // 무엇보다 먼저: 이 함수는 정의상 Maya 메인 스레드에서 돈다. boad가
    // 워커 스레드(Parallel Evaluation Manager 아래의 compute())에서 온
    // 진단을 알아보려면 여기서 기준 스레드를 붙잡아 둬야 한다
    // (MaroDiag.h의 markMainThread() 주석 참고). 아래 등록 단계에서 진단이
    // 나갈 수도 있으므로 제일 앞에 둔다.
    maro::markMainThread();

    MFnPlugin plugin(obj, kVendor, kVersion, "Any");

    MStatus status = plugin.registerNode(
        "maroAxis",
        maro::MaroAxisNode::id,
        maro::MaroAxisNode::creator,
        maro::MaroAxisNode::initialize,
        MPxNode::kLocatorNode);
    if (!status) {
        status.perror("Maro: failed to register maroAxis");
        return status;
    }

    struct CapabilityRegistration {
        const char* name;
        MTypeId id;
        MCreatorFunction creator;
        MInitializeFunction initialize;
    };

    const CapabilityRegistration kCapabilities[] = {
        {"maroRotation", maro::MaroRotationNode::id,
         maro::MaroRotationNode::creator, maro::MaroRotationNode::initialize},
        {"maroLimit", maro::MaroLimitNode::id,
         maro::MaroLimitNode::creator, maro::MaroLimitNode::initialize},
        {"maroSensorDirection", maro::MaroSensorDirectionNode::id,
         maro::MaroSensorDirectionNode::creator,
         maro::MaroSensorDirectionNode::initialize},
        {"maroSensorRange", maro::MaroSensorRangeNode::id,
         maro::MaroSensorRangeNode::creator, maro::MaroSensorRangeNode::initialize},
    };

    for (const auto& cap : kCapabilities) {
        status = plugin.registerNode(cap.name, cap.id, cap.creator, cap.initialize);
        if (!status) {
            status.perror(MString("Maro: failed to register ") + cap.name);
            return status;
        }
    }

    status = plugin.registerCommand(
        "maroBindAxis",
        maro::MaroBindAxisCommand::creator,
        maro::MaroBindAxisCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroBindAxis");
        return status;
    }

    status = plugin.registerCommand(
        "maroSetControlMode",
        maro::MaroSetControlModeCommand::creator,
        maro::MaroSetControlModeCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroSetControlMode");
        return status;
    }

    status = plugin.registerCommand(
        "maroConnectAxis",
        maro::MaroConnectAxisCommand::creator,
        maro::MaroConnectAxisCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroConnectAxis");
        return status;
    }

    status = plugin.registerNode(
        "maroCommandDevice",
        maro::MaroCommandDeviceNode::id,
        maro::MaroCommandDeviceNode::creator,
        maro::MaroCommandDeviceNode::initialize,
        MPxNode::kThreadedDeviceNode);
    if (!status) {
        status.perror("Maro: failed to register maroCommandDevice");
        return status;
    }

    status = plugin.registerCommand("maroStartBridge",
                                    maro::MaroStartBridgeCommand::creator,
                                    maro::MaroStartBridgeCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroStartBridge");
        return status;
    }

    status = plugin.registerCommand("maroStopBridge",
                                    maro::MaroStopBridgeCommand::creator);
    if (!status) {
        status.perror("Maro: failed to register maroStopBridge");
        return status;
    }

    status = plugin.registerCommand("maroBridgeStats",
                                    maro::MaroBridgeStatsCommand::creator);
    if (!status) {
        status.perror("Maro: failed to register maroBridgeStats");
        return status;
    }

    status = plugin.registerCommand("maroDiagEmit", maro::MaroDiagEmitCommand::creator,
                                    maro::MaroDiagEmitCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroDiagEmit");
        return status;
    }

    status = plugin.registerCommand("maroDiagEmitFromThread",
                                    maro::MaroDiagEmitFromThreadCommand::creator,
                                    maro::MaroDiagEmitFromThreadCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroDiagEmitFromThread");
        return status;
    }

    status = plugin.registerCommand("maroDiagCount", maro::MaroDiagCountCommand::creator);
    if (!status) {
        status.perror("Maro: failed to register maroDiagCount");
        return status;
    }

    status = plugin.registerCommand("maroDiagQuery", maro::MaroDiagQueryCommand::creator,
                                    maro::MaroDiagQueryCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroDiagQuery");
        return status;
    }

    status = plugin.registerCommand("maroDiagAnalysisCount",
                                    maro::MaroDiagAnalysisCountCommand::creator);
    if (!status) {
        status.perror("Maro: failed to register maroDiagAnalysisCount");
        return status;
    }

    status = plugin.registerCommand("maroDiagRegisterRemedy",
                                    maro::MaroDiagRegisterRemedyCommand::creator,
                                    maro::MaroDiagRegisterRemedyCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroDiagRegisterRemedy");
        return status;
    }

    status = maro::MaroDeleteWatcher::install();
    if (!status) {
        status.perror("Maro: failed to install delete watcher");
        return status;
    }

    maro::BoadMaro::info("Maro: plugin loaded.");
    return MS::kSuccess;
}

MStatus uninitializePlugin(MObject obj) {
    MFnPlugin plugin(obj);

    maro::shutdownBridge();
    maro::MaroDeleteWatcher::uninstall();

    plugin.deregisterCommand("maroDiagRegisterRemedy");
    plugin.deregisterCommand("maroDiagAnalysisCount");
    plugin.deregisterCommand("maroDiagQuery");
    plugin.deregisterCommand("maroDiagCount");
    plugin.deregisterCommand("maroDiagEmitFromThread");
    plugin.deregisterCommand("maroDiagEmit");

    plugin.deregisterCommand("maroBridgeStats");
    plugin.deregisterCommand("maroStopBridge");
    plugin.deregisterCommand("maroStartBridge");
    plugin.deregisterCommand("maroConnectAxis");
    plugin.deregisterCommand("maroSetControlMode");
    plugin.deregisterCommand("maroBindAxis");

    plugin.deregisterNode(maro::MaroCommandDeviceNode::id);
    plugin.deregisterNode(maro::MaroSensorRangeNode::id);
    plugin.deregisterNode(maro::MaroSensorDirectionNode::id);
    plugin.deregisterNode(maro::MaroLimitNode::id);
    plugin.deregisterNode(maro::MaroRotationNode::id);

    MStatus status = plugin.deregisterNode(maro::MaroAxisNode::id);
    if (!status) {
        status.perror("Maro: failed to deregister maroAxis");
    }

    maro::BoadMaro::info("Maro: plugin unloaded.");
    return status;
}
