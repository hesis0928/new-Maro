#include <maya/MFnPlugin.h>
#include <maya/MGlobal.h>
#include <maya/MStatus.h>

#include "MaroAxisNode.h"
#include "MaroCapabilityNodes.h"
#include "MaroCollisionCommands.h"
#include "MaroCommandDeviceNode.h"
#include "MaroCommands.h"
#include "MaroDeleteWatcher.h"
#include "MaroDiag.h"
#include "MaroDiagCommands.h"
#include "MaroLidarCommands.h"
#include "MaroLidarNode.h"
#include "MaroMainThreadQueue.h"
#include "MaroMainWindowCommand.h"
#include "MaroMenuCommands.h"
#include "MaroPanelCommands.h"
#include "MaroPointCloudNode.h"
#include "MaroPythonBridge.h"
#include "MaroRemedyCommands.h"
#include "MaroRosProxyCommands.h"
#include "MaroAxisEditorCommands.h"
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

    // maroPointCloud는 Viewport 2.0 드로우 오버라이드를 가진 첫 노드다.
    // registerNode()에 넘기는 classification 문자열과 아래
    // registerPointCloudDrawOverride()가 등록에 쓰는 문자열이 같은 정적 멤버
    // (MaroPointCloudNode::kDrawDbClassification)여야 둘이 서로 연결된다.
    status = plugin.registerNode(
        "maroPointCloud", maro::MaroPointCloudNode::id, &maro::MaroPointCloudNode::creator,
        &maro::MaroPointCloudNode::initialize, MPxNode::kLocatorNode,
        &maro::MaroPointCloudNode::kDrawDbClassification);
    if (!status) {
        status.perror("Maro: failed to register maroPointCloud node");
        return status;
    }

    status = maro::registerPointCloudDrawOverride();
    if (!status) {
        status.perror("Maro: failed to register maroPointCloud draw override");
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
        {"maroTranslation", maro::MaroTranslationNode::id,
         maro::MaroTranslationNode::creator, maro::MaroTranslationNode::initialize},
        {"maroTranslationLimit", maro::MaroTranslationLimitNode::id,
         maro::MaroTranslationLimitNode::creator,
         maro::MaroTranslationLimitNode::initialize},
        {"maroCoupling", maro::MaroCouplingNode::id,
         maro::MaroCouplingNode::creator, maro::MaroCouplingNode::initialize},
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

    status = plugin.registerCommand("maroMainWindow",
                                    maro::MaroMainWindowCommand::creator);
    if (!status) {
        status.perror("Maro: failed to register maroMainWindow");
        return status;
    }

    status = plugin.registerCommand("maroBuildMenu",
                                    maro::MaroBuildMenuCommand::creator);
    if (!status) {
        status.perror("Maro: failed to register maroBuildMenu");
        return status;
    }

    status = plugin.registerCommand("maroMayaToRos",
                                    maro::MaroMayaToRosCommand::creator,
                                    maro::MaroMayaToRosCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroMayaToRos");
        return status;
    }

    status = plugin.registerCommand("maroSetRosProxyTarget",
                                    maro::MaroSetRosProxyTargetCommand::creator,
                                    maro::MaroSetRosProxyTargetCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroSetRosProxyTarget");
        return status;
    }

    status = plugin.registerCommand("maroListAxisNodes",
                                    maro::MaroListAxisNodesCommand::creator,
                                    maro::MaroListAxisNodesCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroListAxisNodes");
        return status;
    }

    status = plugin.registerCommand("maroAddCapability",
                                    maro::MaroAddCapabilityCommand::creator,
                                    maro::MaroAddCapabilityCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroAddCapability");
        return status;
    }

    status = plugin.registerCommand("maroConnectCapability",
                                    maro::MaroConnectCapabilityCommand::creator,
                                    maro::MaroConnectCapabilityCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroConnectCapability");
        return status;
    }

    status = plugin.registerCommand("maroDisconnectCapability",
                                    maro::MaroDisconnectCapabilityCommand::creator,
                                    maro::MaroDisconnectCapabilityCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroDisconnectCapability");
        return status;
    }

    status = plugin.registerCommand("maroUnbindAxis",
                                    maro::MaroUnbindAxisCommand::creator,
                                    maro::MaroUnbindAxisCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroUnbindAxis");
        return status;
    }

    status = plugin.registerCommand("maroSnapshotLidarScan",
                                    maro::MaroSnapshotLidarScanCommand::creator,
                                    maro::MaroSnapshotLidarScanCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroSnapshotLidarScan");
        return status;
    }

    status = plugin.registerCommand("maroQueryLidarScan",
                                    maro::MaroQueryLidarScanCommand::creator,
                                    maro::MaroQueryLidarScanCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroQueryLidarScan");
        return status;
    }

    status = plugin.registerCommand("maroCheckMeshCollision",
                                    maro::MaroCheckMeshCollisionCommand::creator,
                                    maro::MaroCheckMeshCollisionCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroCheckMeshCollision");
        return status;
    }

    status = maro::MaroDeleteWatcher::install();
    if (!status) {
        status.perror("Maro: failed to install delete watcher");
        return status;
    }

    // 최상위 "Maro" 메뉴를 만든다 -- UI 편의일 뿐 핵심 기능이 아니므로 이
    // 단계의 실패는 플러그인 로드를 막지 않는다(MaroSentinelClient::
    // connectOrSpawn()과 같은 규율, 위 주석 참고).
    //
    // [최종 리뷰 I5] 이 호출은 executeCommand가 아니라
    // executeCommandOnIdle이어야 한다. initializePlugin은 이 플러그인의
    // 코드 중 "Maya의 메인 윈도우가 아직 없을 수도 있는" 유일한 지점이다:
    // 플러그인 매니저의 "Auto load"가 켜져 있거나, 저장된 워크스페이스의
    // -requiredPlugin "maro"가 시작 중에 이 플러그인을 끌어오면(수동
    // 체크리스트 4절의 재시작-복원 항목이 정확히 그 상황을 만든다) 여기가
    // Maya UI 구성보다 먼저 돈다. 그 상태에서 python/maroMenu.py의
    // cmds.menu(parent="MayaWindow", ...)는 예외도 내지 않고 조용히
    // 아무것도 만들지 않으므로(실측(2026-08-24, Maya 2026): "MayaWindow"
    // 컨트롤이 없는 배치 모드에서 cmds.menu가 예외 없이 False만 돌려주는
    // 것과 같은 동작), 사용자는 그 세션 내내 Maro 메뉴 없이 지내면서 이유를
    // 알 방법이 없다. 유휴 큐에 넣으면 UI가 다 만들어진 뒤에 돈다
    // (MGlobal.h 선언: executeCommandOnIdle(const MString&,
    // bool displayEnabled = false)).
    //
    // 대가 두 가지를 알고 쓴다.
    //  - 돌아오는 MStatus는 이제 "큐에 넣는 데 성공했는가"만 말한다. 메뉴
    //    빌드 자체의 실패(예: 메뉴 이름 충돌)는 나중에 유휴 시점에
    //    일어나므로 여기서는 알 수 없고 스크립트 에디터에만 남는다. 어느
    //    쪽이든 로드를 막지 않는다는 성격은 그대로이므로 warn만 하는 형태를
    //    유지하되, 문구를 실제로 확인한 것(큐잉)에 맞춘다.
    //  - 유휴 큐를 돌리지 않는 환경(배치 mayapy)에서는 이 커맨드가 아예
    //    실행되지 않는다. 배치 모드에서는 원래도 메뉴가 만들어지지 않았고
    //    (위 문단), tests/maya/test_main_menu.py는 커맨드를 스스로 직접
    //    부르므로 검증 범위는 달라지지 않는다.
    const MStatus menuStatus = MGlobal::executeCommandOnIdle("maroBuildMenu");
    if (!menuStatus) {
        maro::BoadMaro::warn(
            "Maro: failed to queue the Maro menu build (non-fatal -- UI convenience only).");
    }

    // 오브젝트 우클릭(마킹) 메뉴에 "Maro node editor" 항목을 붙인다.
    // 위 maroBuildMenu와 달리 유휴 큐를 쓰지 않는다: dagMenuProc 체이닝은
    // Maya 메인 윈도우가 아니라 MEL 전역 프로시저 테이블만 건드리므로
    // UI 구성 완료를 기다릴 이유가 없다(그리고 배치 mayapy에서도 그대로
    // 성립해서 tests/maya가 검증할 수 있다).
    //
    // 실패해도 로드를 막지 않는다 -- 메뉴 항목이 안 붙는 것은 불편일 뿐이고,
    // maroDagMenu.install()은 원본 dagMenuProc를 확실히 보존하지 못하면
    // 아무것도 바꾸지 않고 돌아오도록 설계돼 있다(python/maroDagMenu.py의
    // 모듈 독스트링 참고).
    maro::runPluginPythonModule("maroDagMenu", "maroDagMenu.install()");

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

        // dagMenuProc를 Maya 원본 정의로 되돌린다. initializePlugin의
        // install()과 짝이며, 둘 다 멱등이라 install이 실패해서 아무것도
        // 바꾸지 않았어도 여기서 하는 일이 없다.
        //
        // **이 복원을 빠뜨리면 언로드 뒤에도 세션 전체의 오브젝트 우클릭
        // 메뉴가 사라진 플러그인의 파이썬 코드를 계속 부른다** -- 이 파일의
        // 다른 어떤 정리보다 파급이 넓은 항목이라 언로드 정리의 맨 앞에 둔다.
        //
        // 실패해도 언로드를 막지 않는다 -- runPluginPythonModule은 예외를
        // 삼키고 MStatus로만 알린다(그리고 이 블록 전체가 try/catch 안이다).
        maro::runPluginPythonModule("maroDagMenu", "maroDagMenu.uninstall()");

        // 모든 서브시스템(ROS 프록시의 idle scriptJob 등)을 뗀다. 창의
        // closeCommand가 이미 maroMainWindow.teardown()을 부르지만, 그것만
        // 으로는 세 경로 중 하나만 덮인다:
        //   (1) 사용자가 창을 닫음(언로드 없음) -> closeCommand가 처리.
        //   (2) 창이 열린 채 언로드 -> 아래 workspaceControl -e -close가
        //       closeCommand를 실제로 부르는지 Autodesk 문서로 확정하지
        //       못했다. 부른다면 이 호출은 무해한 중복이고, 안 부른다면
        //       이 호출이 유일한 정리다.
        //   (3) 창을 연 적이 없거나 이미 닫힌 상태에서 언로드 ->
        //       closeCommand 자체가 존재하지 않는다. teardown()이 부르는
        //       stop()들은 전부 start()가 한 번도 안 불렸어도 안전한
        //       무동작이다(멱등).
        // 즉 이것은 "있으면 좋은" 이중 안전장치가 아니라 (2)/(3)을 실제로
        // 책임지는 경로다.
        //
        // **위치가 중요하다.** 브리프는 이 호출을 maroBuildMenu 해제 뒤에
        // 두라고 했지만, 그 자리는 이미 maroMayaToRos를 deregister한
        // 다음이다 -- idle 콜백의 본체가 부르는 바로 그 커맨드다. 그 사이에
        // 유휴 틱이 한 번이라도 돌면(아래 deleteUI가 위젯을 지우며 Qt
        // 이벤트를 돌릴 수 있다) 콜백이 사라진 커맨드를 찾는다. 콜백을
        // 먼저 죽이고 나서 커맨드를 걷어내는 순서가 그 창을 아예 없앤다.
        //
        // 실패해도 언로드를 막지 않는다 -- runPluginPythonModule은 예외를
        // 삼키고 MStatus로만 알린다(그리고 이 블록 전체가 try/catch 안이다).
        //
        // [최종 리뷰 C-1] teardown()은 이제 SONE 팝업(독립 최상위 창이라
        // 아래 workspaceControl -e -close로는 닫히지 않는다)도 함께 닫는다.
        // 그 창들의 paintEvent/keyPressEvent가 부르는 커맨드들
        // (maroListAxisNodes 등)의 deregister는 전부 이 줄 **아래**에 있다 --
        // 순서가 뒤집히면 닫히는 도중의 리페인트가 사라진 커맨드를 찾는다.
        maro::runPluginPythonModule("maroMainWindow", "maroMainWindow.teardown()");

        // 패널이 열린 채 언로드되면 Maya가 사라진 코드의 UI를 계속 붙든다.
        // devkit의 workspaceControlCmd 샘플이 같은 이유로 같은 일을 한다.
        //
        // 메인 창은 여기에 한 가지를 더 한다: 그 안의 modelPanel은 부모
        // 레이아웃의 자식이면서 동시에 Maya의 전역 패널 레지스트리에 등록된
        // 객체라, 컨트롤을 닫아도 등록이 남을 수 있다. 남으면 다음 로드에서
        // 같은 이름으로 다시 만들 때 충돌한다(python 쪽 _deleteStalePanel()이
        // 같은 것을 반대편에서 막는다). 세 이름은 python/maroMainWindow.py의
        // CONTROL_NAME/VIEWPORT_NAME_MAYA/VIEWPORT_NAME_ROS와 같은 문자열이어야
        // 하며, tests/maya/test_main_window.py가 그 계약을 값으로 고정한다.
        // maroBuildMenu는 initializePlugin에서 maroMainWindow "다음"에
        // 등록되므로, 이 파일의 등록 역순 해제 규율에 따라 그 해제는
        // maroMainWindow 블록보다 "먼저" 온다(가장 나중에 등록된 것부터
        // 먼저 해제) -- 위 maroLidar/maroAxis, maroApplyRemedy/
        // maroDiagRequestRemedy 선례와 같은 논리.
        plugin.deregisterCommand("maroCheckMeshCollision");
        plugin.deregisterCommand("maroQueryLidarScan");
        plugin.deregisterCommand("maroSnapshotLidarScan");
        plugin.deregisterCommand("maroUnbindAxis");
        plugin.deregisterCommand("maroDisconnectCapability");
        plugin.deregisterCommand("maroConnectCapability");
        plugin.deregisterCommand("maroAddCapability");
        plugin.deregisterCommand("maroListAxisNodes");
        plugin.deregisterCommand("maroSetRosProxyTarget");
        plugin.deregisterCommand("maroMayaToRos");

        MGlobal::executeCommand(
            "if (`menu -exists maroMainMenu`) deleteUI -menu maroMainMenu;");
        plugin.deregisterCommand("maroBuildMenu");

        MGlobal::executeCommand(
            "if (`workspaceControl -exists maroMainWindowControl`) "
            "workspaceControl -e -close maroMainWindowControl;"
            "if (`modelPanel -exists maroMainWindowViewportMaya`) "
            "deleteUI -panel maroMainWindowViewportMaya;"
            "if (`modelPanel -exists maroMainWindowViewportRos`) "
            "deleteUI -panel maroMainWindowViewportRos;");
        plugin.deregisterCommand("maroMainWindow");

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
        plugin.deregisterNode(maro::MaroCouplingNode::id);
        plugin.deregisterNode(maro::MaroTranslationLimitNode::id);
        plugin.deregisterNode(maro::MaroTranslationNode::id);
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

        // maroPointCloud는 maroLidar "다음"에 등록되므로 등록 역순 규율에 따라
        // 그 앞에서 해제한다. 그리고 그 안에서도 **드로우 오버라이드 해제가
        // 노드 해제보다 먼저**여야 한다(전역 제약) -- 반대로 하면 Maya가 아직
        // 살아 있는 드로우 오버라이드 인스턴스를 통해 이미 사라진 노드 타입을
        // 건드릴 수 있어 언로드 시 크래시 위험이 있다.
        MStatus pointCloudDrawStatus = maro::deregisterPointCloudDrawOverride();
        if (!pointCloudDrawStatus) {
            pointCloudDrawStatus.perror("Maro: failed to deregister maroPointCloud draw override");
        }
        MStatus pointCloudStatus = plugin.deregisterNode(maro::MaroPointCloudNode::id);
        if (!pointCloudStatus) {
            pointCloudStatus.perror("Maro: failed to deregister maroPointCloud node");
        }

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
