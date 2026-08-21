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
#include "MaroLidarNode.h"
#include "MaroMainThreadQueue.h"
#include "MaroPanelCommands.h"
#include "MaroRemedyCommands.h"
#include "MaroSentinelClient.h"

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

// 저널/큐와 같은 이유로 가드를 쓴다 -- 이 함수를 어떤 경로로 빠져나가든
// 파이프를 반드시 닫는다.
struct SentinelGuard {
    ~SentinelGuard() { maro::MaroSentinelClient::shutdown(); }
};

// [최종 리뷰 I-2] initializePlugin 전용 되감기 가드. 위 세 가드가
// uninitializePlugin에 대해 하는 일을, 로드가 실패했을 때 initializePlugin에
// 대해 한다.
//
// 핵심 사실: Maya는 initializePlugin이 실패 상태를 반환하면
// uninitializePlugin을 **부르지 않는다**. 그런데 이 함수는 저널을 열고
// 감시자에 접속한 뒤에야 스물몇 개의 registerNode/registerCommand를 하고,
// 그 하나하나가 실패 시 그냥 return status로 빠져나간다. 가드가 없으면 그
// 경로들에서 파이프가 열린 채 남고 SESSION_END_CLEAN도 안 나가므로, 감시자는
// 나중에 파이프가 끊기는 것만 보고 이 세션을 크래시로 기록한다 -- 로드에
// 실패했을 뿐인 세션이 크래시로 오판되는 것이고, 이는 감시자(Layer C-1)가
// 막으려고 존재하는 바로 그 오진이다.
//
// 소멸자가 건드리는 것들은 이 가드가 선언되는 지점에서 이미 무조건
// 실행됐거나(openJournal, connectOrSpawn), 실행된 적이 없어도 부르는 것이
// 안전하다(MaroMainThreadQueue::uninstall()은 s_timerId == 0이면 무동작,
// notifyCleanExit()는 미접속이면 즉시 반환, shutdown()은 무조건 호출해도
// 안전하다). 정리 순서는 uninitializePlugin과 같게 맞춘다
// (감시자 -> 큐 -> 저널, 저널 닫기가 언제나 마지막).
//
// committed는 성공 경로에서만, 마지막 return MS::kSuccess 직전에 세운다 --
// 그 지점보다 앞의 모든 return은 정의상 실패 경로다.
struct InitFailureGuard {
    bool committed = false;
    ~InitFailureGuard() {
        if (committed) return;
        maro::MaroSentinelClient::notifyCleanExit();
        maro::MaroSentinelClient::shutdown();
        maro::MaroMainThreadQueue::uninstall();
        maro::BoadMaro::closeJournal();
    }
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

    // 감시자 spawn/접속은 실패해도 로드를 막지 않는다 -- 함수 내부가
    // 스스로 그 규율을 지킨다(MaroSentinelClient.cpp).
    maro::MaroSentinelClient::connectOrSpawn();

    // 여기서부터 아래의 모든 return은 실패 경로다 -- Maya가 그 경우
    // uninitializePlugin을 부르지 않으므로, 저널/감시자/큐 정리를 이 가드가
    // 대신한다. 성공 경로에서는 맨 아래에서 committed를 세워 무동작이 된다.
    InitFailureGuard rollbackOnFailure;

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

    status = plugin.registerNode("maroLidar", maro::MaroLidarNode::id, &maro::MaroLidarNode::creator,
                                  &maro::MaroLidarNode::initialize, MPxNode::kLocatorNode);
    if (!status) {
        status.perror("Maro: failed to register maroLidar node");
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

    status = plugin.registerCommand("maroDiagRequestRemedy",
                                    maro::MaroDiagRequestRemedyCommand::creator,
                                    maro::MaroDiagRequestRemedyCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroDiagRequestRemedy");
        return status;
    }

    status = plugin.registerCommand("maroApplyRemedy",
                                    maro::MaroApplyRemedyCommand::creator,
                                    maro::MaroApplyRemedyCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroApplyRemedy");
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
    // 로드가 끝까지 성공한 유일한 지점이다. 여기서 가드를 해제해야 정상
    // 로드된 세션의 저널/감시자/큐가 살아남는다 -- 이 줄이 없으면 모든
    // 플러그인 로드가 곧바로 스스로를 정리해 버린다.
    rollbackOnFailure.committed = true;
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

    // 파이프도 같은 규율로 닫는다. 선언 순서 덕분에 소멸은 역순이 되어
    // (감시자 -> 큐 -> 저널) 가장 바깥의 저널 닫기가 언제나 마지막이다.
    const SentinelGuard sentinelGuardOnExit;

    try {
        MFnPlugin plugin(obj);

        // 언로드가 시작됐다는 것 자체가 "정상 종료 경로에 들어왔다"는
        // 뜻이다 -- 아래에서 무엇이 실패하든 이 신호는 이미 보내는 게
        // 맞다. closeJournal()이 그렇듯, 감시자에게도 "이 세션은 의도적
        // 종료였다"를 최대한 일찍 알린다.
        maro::MaroSentinelClient::notifyCleanExit();

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

        // 브리프 Step 5는 이 둘을 maroDiagQueryRemedyAction 바로 위에 놓으라고
        // 했지만, 그 자리는 등록 역순이 아니다 -- 같은 브리프가 등록은
        // maroQueueTestCounter "뒤"에 두라고 했으므로, 역순이라면 이 둘의
        // 해제는 maroQueueTest 두 개보다 "먼저" 와야 한다. 이 파일이 스스로
        // 내건 규율(등록 역순)을 따르는 쪽을 택했다. 해제 순서 자체는
        // 기능적으로 무해하지만, 규율이 한 곳에서 어긋나면 규율이 아니게 된다.
        plugin.deregisterCommand("maroApplyRemedy");
        plugin.deregisterCommand("maroDiagRequestRemedy");

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

        // 브리프 Step 4는 이 dereg 호출을 maroAxis dereg "바로 다음"에 두라고
        // 했지만, 그 자리는 등록 역순이 아니다 -- initializePlugin에서
        // maroLidar는 maroAxis 바로 "다음"에 등록되므로, 이 파일이 스스로
        // 내건 규율(등록 역순 dereg -- 위 라인 328-334의 maroApplyRemedy/
        // maroDiagRequestRemedy 선례와 같은 논리)을 따르면 maroLidar dereg는
        // maroAxis dereg "바로 앞"에 와야 한다(가장 나중에 등록된 것부터
        // 먼저 해제). 여기서도 그 규율을 우선했다.
        MStatus status = plugin.deregisterNode(maro::MaroLidarNode::id);
        if (!status) status.perror("Maro: failed to deregister maroLidar node");

        status = plugin.deregisterNode(maro::MaroAxisNode::id);
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
