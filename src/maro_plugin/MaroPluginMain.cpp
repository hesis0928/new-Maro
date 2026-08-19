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
#include "MaroMainThreadQueue.h"
#include "MaroPanelCommands.h"

namespace {
constexpr char kVendor[] = "Maro";
constexpr char kVersion[] = "0.1.0";

// 리뷰 Finding I1: uninitializePlugin은 이 파일 어디에도 try/catch가 없다.
// 그 안에서 뭔가(가장 눈에 띄는 것은 맨 마지막의 BoadMaro::info() 호출, 다만
// 이제 그 자체는 절대 던지지 않는다 -- MaroDiag.cpp의 pushAndJournal 참고)가
// 던지면, closeJournal()이 아예 안 돈다 -- 다음 세션은 이번 세션이 정상
// 종료했는데도 close 줄이 없다는 이유로 크래시로 오판한다(예외 자체가 Maya
// 언로드 콜백 경계를 넘는 것과는 별개의, 그러나 겹쳐서 나쁜 결과다). 이
// 가드는 지역 객체이므로, 아래 uninitializePlugin이 정상 반환하든 예외로
// 스택이 되감기든 소멸자가 항상 불려 closeJournal()을 보장한다.
struct JournalCloseGuard {
    ~JournalCloseGuard() { maro::BoadMaro::closeJournal(); }
};

// 큐도 저널과 같은 이유로 가드를 쓴다 -- 이 함수의 어떤 경로로 빠져나가든
// (정상 반환이든 catch로의 되감김이든) 타이머 콜백을 반드시 뗀다. 안 떼면
// 언로드된 코드의 클로저(task)가 다음 틱에서 불려 크래시한다.
struct MainThreadQueueGuard {
    ~MainThreadQueueGuard() { maro::MaroMainThreadQueue::uninstall(); }
};
}  // namespace

MStatus initializePlugin(MObject obj) {
    // 무엇보다 먼저: 이 함수는 정의상 Maya 메인 스레드에서 돈다. boad가
    // 워커 스레드(Parallel Evaluation Manager 아래의 compute())에서 온
    // 진단을 알아보려면 여기서 기준 스레드를 붙잡아 둬야 한다
    // (MaroDiag.h의 markMainThread() 주석 참고). 아래 등록 단계에서 진단이
    // 나갈 수도 있으므로 제일 앞에 둔다.
    maro::markMainThread();

    // 저널을 연다. markMainThread()가 book 경로를 이미 확정했으므로
    // 저널 경로도 여기서 안전하게 해소된다.
    maro::BoadMaro::openJournal();

    MStatus queueStatus = maro::MaroMainThreadQueue::install();
    if (!queueStatus) {
        queueStatus.perror("Maro: failed to install the main-thread queue");
        return queueStatus;
    }

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

    status = plugin.registerCommand("maroDiagQueryRemedyAction",
                                    maro::MaroDiagQueryRemedyActionCommand::creator,
                                    maro::MaroDiagQueryRemedyActionCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroDiagQueryRemedyAction");
        return status;
    }

    status = plugin.registerCommand("maroQueueTestEnqueueIncrement",
                                    maro::MaroQueueTestEnqueueIncrementCommand::creator);
    if (!status) {
        status.perror("Maro: failed to register maroQueueTestEnqueueIncrement");
        return status;
    }

    status = plugin.registerCommand("maroQueueTestCounter",
                                    maro::MaroQueueTestCounterCommand::creator);
    if (!status) {
        status.perror("Maro: failed to register maroQueueTestCounter");
        return status;
    }

    status = plugin.registerCommand("maroDiagEmitMarked",
                                    maro::MaroDiagEmitMarkedCommand::creator,
                                    maro::MaroDiagEmitMarkedCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroDiagEmitMarked");
        return status;
    }

    status = plugin.registerCommand("maroJournalAbnormalSessions",
                                    maro::MaroJournalAbnormalSessionsCommand::creator);
    if (!status) {
        status.perror("Maro: failed to register maroJournalAbnormalSessions");
        return status;
    }

    status = plugin.registerCommand("maroJournalCrashAdjacentTags",
                                    maro::MaroJournalCrashAdjacentTagsCommand::creator);
    if (!status) {
        status.perror("Maro: failed to register maroJournalCrashAdjacentTags");
        return status;
    }

    status = plugin.registerCommand("maroDiagPanelRows",
                                    maro::MaroDiagPanelRowsCommand::creator,
                                    maro::MaroDiagPanelRowsCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroDiagPanelRows");
        return status;
    }

    status = plugin.registerCommand("maroDiagPanelDetail",
                                    maro::MaroDiagPanelDetailCommand::creator,
                                    maro::MaroDiagPanelDetailCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroDiagPanelDetail");
        return status;
    }

    status = plugin.registerCommand("maroDiagPanel",
                                    maro::MaroDiagPanelCommand::creator);
    if (!status) {
        status.perror("Maro: failed to register maroDiagPanel");
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
    // 리뷰 Finding I1: 이 함수가 무엇을 하든(그 밑의 모든 deregisterX 호출,
    // executeCommand, 맨 아래의 info() 호출) closeJournal()은 반드시 돈다 --
    // 이 지역 객체는 아래에서 정상 반환이 나든 catch(...)로 되감기든 함수를
    // 빠져나가는 순간 항상 소멸자가 불린다. closeJournal()을 이 함수 끝에서
    // 직접 부르는 대신 이 가드 하나로 옮긴 이유가 그것이다.
    const JournalCloseGuard closeJournalOnExit;

    // 큐를 저널보다 먼저 뗀다 -- 정지 순서는 중요하지 않지만(큐 작업이
    // 저널을 부르지 않는다), 상시 인프라를 하나씩 순서대로 내리는 쪽이
    // 나중에 유지보수할 때 더 읽기 쉽다.
    const MainThreadQueueGuard queueGuardOnExit;

    try {
        MFnPlugin plugin(obj);

        maro::shutdownBridge();
        maro::MaroDeleteWatcher::uninstall();

        // 패널이 열린 채 언로드되면 Maya가 사라진 코드의 UI를 계속 붙든다.
        // devkit의 workspaceControlCmd 샘플이 같은 이유로 같은 일을 한다.
        MGlobal::executeCommand(
            "if (`workspaceControl -exists maroDiagPanelControl`) "
            "workspaceControl -e -close maroDiagPanelControl;");
        plugin.deregisterCommand("maroDiagPanel");

        plugin.deregisterCommand("maroDiagPanelDetail");
        plugin.deregisterCommand("maroDiagPanelRows");

        plugin.deregisterCommand("maroJournalCrashAdjacentTags");
        plugin.deregisterCommand("maroJournalAbnormalSessions");

        plugin.deregisterCommand("maroDiagEmitMarked");
        // 브리프 Step 6에는 이 두 테스트 전용 커맨드의 deregister 호출이
        // 없었다 -- 이 파일의 다른 모든 registerCommand는 반드시 짝을 이루는
        // deregisterCommand를 이 함수 안에 갖고 있는데(위아래 블록 전부가
        // 그 규율을 따른다), 이 둘만 빠지면 unloadPlugin 이후에도 Maya의
        // 전역 커맨드 레지스트리가 이미 언로드된 DLL 코드를 가리키는
        // 함수 포인터를 계속 들고 있게 된다 -- 그 상태에서 누가
        // maroQueueTestCounter를 부르면 크래시한다. 브리프의 누락으로 보고
        // 이 파일의 기존 관례(등록 역순 deregister)를 따라 채워 넣었다.
        plugin.deregisterCommand("maroQueueTestCounter");
        plugin.deregisterCommand("maroQueueTestEnqueueIncrement");
        plugin.deregisterCommand("maroDiagQueryRemedyAction");
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

        // closeJournal()은 여기서 직접 부르지 않는다 -- 위 closeJournalOnExit
        // 가드가 이 함수를 벗어나는 순간(정상 반환이든 아래 catch로의 되감김
        // 이든) 항상 부른다.
        maro::BoadMaro::info("Maro: plugin unloaded.");
        return status;
    } catch (...) {
        // 리뷰 Finding I1: 예외가 이 언로드 콜백 경계를 넘으면 안 된다
        // ("Maya 콜백에서 예외가 새면 안 된다"는 이 프로젝트 전역 규율).
        // 여기서 삼키고 실패를 알린다 -- closeJournalOnExit는 이 함수가
        // (이 catch를 거쳐) 반환하는 순간 자기 소멸자를 통해 저널을 닫는다.
        return MS::kFailure;
    }
}
