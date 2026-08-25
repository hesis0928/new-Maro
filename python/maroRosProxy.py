"""ROS 좌표 프록시 동기화 -- 설계 스펙
docs/superpowers/specs/2026-08-25-maro-main-ui-phase3-ros-proxy-design.md.

Maya 오브젝트 하나(기본: 현재 선택, maroSetRosProxyTarget으로 고정 가능)의
월드 위치/회전을 maroMayaToRos로 변환해 maroRosProxy_grp 안의 로케이터로
반영한다. 같은 idle 콜백이 좌측(Maya) 뷰포트의 isolateSelect 목록도 갱신한다
-- 새로 생긴 오브젝트가 창을 닫았다 열지 않아도 바로 보이게 하기 위해서다
(isolateSelect의 격리 목록은 스냅샷이라 자동으로 안 늘어난다, 설계 스펙 §7).

maroMainWindow.py를 import하지 않는다 -- 그쪽이 이미 이 모듈을 import하므로
순환 참조가 생긴다. 대신 start()가 두 뷰포트 이름을 인자로 받는다.

이 모듈이 쓰는 Maya 커맨드/API 가정은 전부 실측으로 확인했다
(Maya 2026, mayapy 배치, 2026-08-25). 확인한 것과 확인 못 한 것을
.superpowers/sdd/task-2-report.md에 나눠 적어 뒀다. 요약:

  - `isolateSelect`는 **에디터(패널)별**로 걸린다. Maya 자신의
    scripts/others/createModelPanelMenu.mel이 에디터 이름을 키로 격리 상태를
    관리하고(`$gIsolateSelectAutoAddEditors`), `isolateSelect -addDagObject
    $object $editor`처럼 패널 이름을 마지막 인자로 넘긴다. 파이썬 바인딩의
    `cmds.isolateSelect(panel, addDagObject=obj)`가 바로 그 형태다.
    startup/defaultRunTimeCommands.mel의 ToggleIsolateSelect는 `getPanel
    -withFocus`가 준 **modelPanel 이름**을 그대로 넘기므로, 패널 이름을
    에디터 이름 자리에 쓰는 것도 Maya 자신의 관행이다.
  - 플래그 이름은 `cmds.help("isolateSelect")`로 확인했다:
    `-ado/-addDagObject Name`, `-s/-state on|off`.
  - `-addDagObject`의 멱등성(이미 격리된 오브젝트를 다시 넣어도 무해)은
    **대화형 Maya에서 아직 확인하지 못했다.** 격리 목록의 실체가
    에디터별 오브젝트 세트(`*ViewSelectedSet`)라는 점에서 세트 멤버십
    추가 = 무동작일 가능성이 높지만, 최종 판정은 수동 체크리스트의 몫이다.

**Maya 자신의 `enableIsolateSelect` MEL 프로시저는 일부러 쓰지 않는다.**
그것은 `modelEditor -e -viewSelected`를 켜는 김에 그 패널을 Maya의 전역
자동 추가 목록에 등록하고 `DagObjectCreated` scriptJob까지 띄운다
(createModelPanelMenu.mel:332-357). 그러면 사용자가 오브젝트를 만들 때마다
Maya가 **우측(ROS) 패널에도** 그것을 밀어 넣어 이 단계 전체의 목적인
"우측엔 프록시만"이 깨진다. `isolateSelect -state`는 그 기계장치를 끌고
오지 않는 순수한 on/off라서 이쪽을 쓴다.
"""
import traceback

import maya.cmds as cmds
import maya.api.OpenMaya as om2

PROXY_GROUP = "maroRosProxy_grp"
PROXY_LOCATOR = "maroRosProxy_loc"
PROXY_LOCATOR_SHAPE = PROXY_LOCATOR + "Shape"

# 이 문자열은 C++ 커맨드 maroSetRosProxyTarget과의 계약이다
# (MaroRosProxyCommands.cpp). 바꾸면 양쪽을 함께 고쳐야 한다 --
# tests/maya/test_ros_proxy_sync.py가 그 계약을 값으로 고정한다.
PINNED_OPTIONVAR = "maroRosProxyPinnedTarget"

# 프록시 노드의 모호하지 않은 전체 DAG 경로. 사용자가 어딘가에 같은 이름의
# 노드를 만들어 둬도 이 경로는 우리 것만 가리킨다.
_PROXY_GROUP_PATH = "|" + PROXY_GROUP
_PROXY_LOCATOR_PATH = _PROXY_GROUP_PATH + "|" + PROXY_LOCATOR

# _onIdle이 연속으로 이만큼 실패하면 스스로 멈춘다. 이유는 _onIdle의
# 주석에 적어 뒀다.
_MAX_CONSECUTIVE_FAILURES = 5

_JOB_ID = None
_MAYA_PANEL = None
_ROS_PANEL = None

# 좌측 격리 목록을 마지막으로 갱신했을 때의 최상위 오브젝트 목록.
# None이면 "다음 틱에 무조건 다시 훑어라"는 뜻이다.
_LAST_ASSEMBLIES = None

_CONSECUTIVE_FAILURES = 0


# --- 프록시 노드 -------------------------------------------------------

def _ensureProxyGroup():
    """프록시 전용 그룹을 보장하고 그 전체 경로를 돌려준다.

    `cmds.group()`이 아니라 `cmds.createNode(..., skipSelect=True)`를 쓴다.
    실측(Maya 2026): `cmds.group(empty=True, name=...)`도
    `cmds.spaceLocator(name=...)`도 **만든 노드로 선택을 갈아치운다.**
    이 모듈의 기본 동작이 "현재 선택을 따라간다"(_resolveTarget)이므로,
    그대로 두면 창을 여는 순간 사용자의 선택이 날아가고 그 다음 틱부터
    프록시가 자기 자신을 동기화 대상으로 삼는 되먹임이 생긴다(로케이터를
    만든 틱에 선택이 로케이터로 바뀌므로). `-skipSelect`는 선택을 전혀
    건드리지 않는 것을 실측으로 확인했다.
    """
    if not cmds.objExists(_PROXY_GROUP_PATH):
        cmds.createNode("transform", name=PROXY_GROUP, skipSelect=True)
    return _PROXY_GROUP_PATH


def _ensureProxyLocator():
    """프록시 로케이터(트랜스폼 + locator 셰이프)를 보장한다.

    `cmds.spaceLocator()`가 만드는 것과 같은 구조를, 선택을 건드리지 않고
    (위 _ensureProxyGroup 주석 참고) 부모까지 한 번에 만든다 -- 만든 뒤
    `cmds.parent()`로 옮기면 그 사이에 로케이터가 잠시 씬 최상위에 놓여
    좌측 격리 갱신이 그것을 집어갈 수 있다.
    """
    _ensureProxyGroup()
    if not cmds.objExists(_PROXY_LOCATOR_PATH):
        transform = cmds.createNode(
            "transform", name=PROXY_LOCATOR, parent=_PROXY_GROUP_PATH, skipSelect=True)
        cmds.createNode(
            "locator", name=PROXY_LOCATOR_SHAPE, parent=transform, skipSelect=True)
    return _PROXY_LOCATOR_PATH


def _isProxyOwned(name):
    """`name`이 프록시 그룹 자신이거나 그 안의 노드인가.

    동기화 대상이 프록시가 되면 프록시가 자기 자신을 따라가는 되먹임이
    생긴다. 선택 추종(기본값)에서도, 사용자가 실수로 로케이터를 고정해도
    (maroSetRosProxyTarget) 똑같이 막아야 하므로 두 경로 모두 이것을 통과한다.
    """
    for longName in (cmds.ls(name, long=True) or []):
        if longName == _PROXY_GROUP_PATH or longName.startswith(_PROXY_GROUP_PATH + "|"):
            return True
    return False


def _resolveTarget():
    """동기화 대상 트랜스폼의 전체 경로를 돌려준다. 없으면 None.

    고정된 오브젝트가 씬에서 지워졌으면 조용히 선택 추종으로 떨어진다 --
    매 idle 틱마다 에러를 내면 스크립트 에디터가 도배된다.
    """
    if cmds.optionVar(exists=PINNED_OPTIONVAR):
        pinned = cmds.optionVar(query=PINNED_OPTIONVAR)
        if pinned and cmds.objExists(pinned) and not _isProxyOwned(pinned):
            return pinned

    for name in (cmds.ls(selection=True, type="transform", long=True) or []):
        if not _isProxyOwned(name):
            return name
    return None


# --- 격리(isolateSelect) -----------------------------------------------

def _refreshMayaIsolation():
    """좌측 패널 격리 목록에 최상위 오브젝트를 (필요할 때) 다시 추가한다.

    설계 스펙 §7이 요구하는 라이브 갱신이다: 창을 연 뒤에 만든 오브젝트도
    창을 다시 열지 않고 좌측 뷰포트에 바로 나타나야 한다.

    매 틱마다 무조건 전부 다시 넣는 대신 최상위 목록이 **바뀌었을 때만**
    훑는다. idle 이벤트는 초당 수십 번 오는데 오브젝트 하나당 UI 커맨드를
    하나씩 부르면 씬이 조금만 커져도 Maya가 눈에 띄게 느려진다 -- 스펙이
    "워킹 스켈레톤 규모에서는 무시할 만하다"고 본 비용이지만, 목록 비교
    한 번으로 그 가정 자체를 없앨 수 있으므로 그렇게 한다. 요구사항(새
    오브젝트가 바로 보인다)은 그대로다: 오브젝트가 생기면 목록이 달라지고,
    그 틱에 전체를 다시 넣는다.

    _LAST_ASSEMBLIES를 None으로 되돌리는 것이 곧 "다음 틱에 무조건 다시
    넣어라"이며, start()가 그렇게 한다 -- 창을 다시 열면 패널이 새로
    만들어져 격리 목록이 비어 있기 때문에 반드시 필요하다.
    """
    global _LAST_ASSEMBLIES

    _ensureProxyGroup()

    # 우측 패널은 그룹 하나만 보면 되지만, 사용자가 그룹을 지웠다 다시
    # 만들어진 경우(위 _ensureProxyGroup) 격리 목록의 항목은 노드와 함께
    # 사라진 상태다. 한 번 더 넣는 비용이 커맨드 하나뿐이라 매 틱 넣어
    # 스스로 복구되게 한다.
    cmds.isolateSelect(_ROS_PANEL, addDagObject=PROXY_GROUP)

    assemblies = tuple(cmds.ls(assemblies=True) or [])
    if assemblies == _LAST_ASSEMBLIES:
        return

    # cmds.ls(assemblies=True)는 짧은 이름을 준다(최상위 이름은 Maya에서
    # 유일하므로 모호하지 않다) -- isolateSelect에 넘기는 이름은 Maya 자신의
    # MEL이 넘기는 것과 같은 형태로 두고(createModelPanelMenu.mel:327),
    # 전체 경로는 확실히 검증한 xform/om2 쪽에만 쓴다.
    for obj in assemblies:
        if obj == PROXY_GROUP:
            continue
        cmds.isolateSelect(_MAYA_PANEL, addDagObject=obj)
    _LAST_ASSEMBLIES = assemblies


# --- 동기화 -------------------------------------------------------------

def _syncProxy():
    target = _resolveTarget()
    if target is None:
        # 대상이 없으면 마지막 상태를 그대로 둔다(프록시를 지우지 않는다).
        # 설계 스펙 §6은 "지움"이라고 적었지만, 고정 대상 기능이 생긴 뒤로는
        # 선택 해제가 흔한 조작이라 그때마다 로케이터를 지웠다 다시 만들면
        # 우측 뷰포트가 깜빡이고 노드가 계속 새로 생긴다. 남겨 두는 쪽이
        # 조용하고, 다음 선택이 오면 어차피 덮어쓴다.
        return

    pos = cmds.xform(target, query=True, worldSpace=True, translation=True)

    # 월드 회전은 xform으로도 얻을 수 있지만(오일러), 쿼터니언이 필요하고
    # 오일러 회전 순서/짐벌을 거치지 않는 편이 안전하다. 실측으로
    # MFnTransform.rotation(kWorld, asQuaternion=True)이 부모 변환까지 반영한
    # 진짜 월드 회전을 준다는 것을 확인했다(inclusiveMatrix에서 뽑은 값과 일치).
    dagPath = om2.MSelectionList().add(target).getDagPath(0)
    quat = om2.MFnTransform(dagPath).rotation(om2.MSpace.kWorld, asQuaternion=True)

    converted = cmds.maroMayaToRos(
        px=pos[0], py=pos[1], pz=pos[2],
        qx=quat.x, qy=quat.y, qz=quat.z, qw=quat.w)

    # [최종 리뷰 I2] cmds.xform(...)가 아니라 MFnTransform.setTranslation/
    # setRotation을 쓴다. cmds.xform은 undo 가능한 커맨드라서, idle이
    # 초당 수십 번 도는 이 경로에서 그대로 쓰면 몇 초 만에 undo 큐가
    # 이 프록시 갱신으로만 가득 차 사용자의 실제 작업에 대한 Ctrl+Z가
    # 무의미해진다. MFnTransform의 API 호출은 undo 큐에 안 남는다 --
    # 회전도 쿼터니언을 바로 받으므로 오일러/짐벌 변환이 필요 없어져
    # 그만큼 코드도 단순해진다.
    locatorPath = _ensureProxyLocator()
    locatorDagPath = om2.MSelectionList().add(locatorPath).getDagPath(0)
    locatorFn = om2.MFnTransform(locatorDagPath)
    locatorFn.setTranslation(
        om2.MVector(converted[0], converted[1], converted[2]), om2.MSpace.kWorld)
    locatorFn.setRotation(
        om2.MQuaternion(converted[3], converted[4], converted[5], converted[6]),
        om2.MSpace.kWorld)


def _panelsAlive():
    """두 뷰포트가 아직 존재하는가.

    창이 닫혔는데 stop()이 안 불린 경로(workspaceControl의 closeCommand가
    어떤 이유로 안 뛰는 경우)를 이 콜백이 스스로 알아채기 위한 것이다.
    패널이 없으면 격리도 동기화도 의미가 없고, isolateSelect가 사라진 패널
    이름에 대고 매 틱 에러를 낸다.
    """
    if not _MAYA_PANEL or not _ROS_PANEL:
        return False
    return (bool(cmds.modelPanel(_MAYA_PANEL, exists=True))
            and bool(cmds.modelPanel(_ROS_PANEL, exists=True)))


def _onIdle():
    """idle scriptJob의 본체.

    **이 함수에서 예외가 새어 나가면 안 된다.** idle은 초당 여러 번 오므로
    한 번 깨지면 스크립트 에디터가 같은 트레이스백으로 도배되고, 사용자는
    진짜 원인을 찾을 수 없게 된다. 이 프로젝트가 콜백/스레드 정리에 들여 온
    주의와 같은 급으로 다룬다(설계 스펙 §10).

    두 가지 자가 방어를 둔다.
      1. 뷰포트가 사라졌으면 스스로 멈춘다 -- 창이 닫혔는데 closeCommand가
         안 뛴 경우에도 잡이 남지 않는다.
      2. 연속 실패가 _MAX_CONSECUTIVE_FAILURES에 이르면 스스로 멈춘다.
         커맨드가 사라진 뒤(언로드) 같은 영구적 고장은 이걸로 조용해지고,
         한두 틱짜리 일시적 실패는 성공하면 카운터가 0으로 돌아가 그대로
         살아남는다. 트레이스백은 연속 실패의 **첫 틱에만** 찍는다 --
         사람이 원인을 볼 수 있으면서 도배는 안 되는 지점이다.

    [최종 리뷰 I1] 두 자가 방어 다 `stop()`을 **직접** 부르지 않고
    `cmds.evalDeferred(stop)`로 미룬다. scriptJob 콜백 한복판에서 자기
    자신을 `-force -kill`하는 것은 Maya 자신도 하지 않는 패턴이다 --
    `others/dynUpdateDeleteAttrWin.mel`류의 스크립트들이 전부
    `evalDeferred("scriptJob -force -kill " + $job)`로 한 틱 미뤄서
    자기 잡을 죽인다. 이 프로젝트도 같은 관례를 따른다.
    """
    global _CONSECUTIVE_FAILURES

    try:
        # 뷰포트 확인도 try 안에 둔다 -- 이 함수에서 **어떤** 경로로도
        # 예외가 새어 나가면 안 된다는 것이 위 규칙이고, 예외 없이 도는
        # 것으로 믿는 호출까지 밖에 두면 그 규칙에 구멍이 생긴다.
        if not _panelsAlive():
            cmds.evalDeferred(stop)
            return
        _refreshMayaIsolation()
        _syncProxy()
    except Exception:  # noqa: BLE001 -- Maya 콜백 경계, 위 도크스트링 참고
        _CONSECUTIVE_FAILURES += 1
        if _CONSECUTIVE_FAILURES == 1:
            print("maroRosProxy: sync tick failed --")
            traceback.print_exc()
        if _CONSECUTIVE_FAILURES >= _MAX_CONSECUTIVE_FAILURES:
            print("maroRosProxy: {} consecutive failures -- stopping the sync job."
                  .format(_CONSECUTIVE_FAILURES))
            cmds.evalDeferred(stop)
        return

    _CONSECUTIVE_FAILURES = 0


# --- 생명주기 -----------------------------------------------------------

def start(mayaPanelName, rosPanelName):
    """maroMainWindow.buildUI()가 두 뷰포트를 만든 직후 부른다.

    멱등하다: buildUI()는 한 세션에 여러 번 불릴 수 있으므로(도킹/복원/
    플러그인 재로드로 workspaceControl이 -uiScript를 다시 돌린다) 잡이
    중복으로 쌓이면 안 된다. 반대로 격리 설정은 매번 다시 해야 한다 --
    그때마다 패널이 새로 만들어져 격리 상태와 목록이 비어 있기 때문이다.
    """
    global _JOB_ID, _MAYA_PANEL, _ROS_PANEL, _LAST_ASSEMBLIES, _CONSECUTIVE_FAILURES
    _MAYA_PANEL = mayaPanelName
    _ROS_PANEL = rosPanelName
    _CONSECUTIVE_FAILURES = 0
    # 패널이 새로 만들어졌다면 격리 목록은 비어 있다 -- 캐시를 버려
    # 다음 틱이 전체를 다시 넣게 한다(_refreshMayaIsolation 주석 참고).
    _LAST_ASSEMBLIES = None

    _ensureProxyGroup()
    cmds.isolateSelect(_ROS_PANEL, state=True)
    cmds.isolateSelect(_ROS_PANEL, addDagObject=PROXY_GROUP)
    cmds.isolateSelect(_MAYA_PANEL, state=True)

    if _JOB_ID is not None and cmds.scriptJob(exists=_JOB_ID):
        return

    # protected: File > New나 `scriptJob -killAll`이 이 잡을 조용히 죽이면
    # 창은 열려 있는데 동기화만 멈춘 상태가 된다 -- 그건 진단하기 어려운
    # 종류의 고장이다. 대신 stop()이 -force로 죽인다(protected 잡은 force
    # 없이는 안 죽는다).
    jobId = cmds.scriptJob(event=["idle", _onIdle], protected=True)
    if isinstance(jobId, int):
        _JOB_ID = jobId
    else:
        # 배치 mayapy에서는 scriptJob이 아무것도 만들지 않고 None을 준다
        # (실측) -- 거기서는 애초에 창이 없으니 정상이다. 대화형 세션에서
        # 이게 나오면 진짜 문제이므로 알린다.
        _JOB_ID = None
        if not cmds.about(batch=True):
            print("maroRosProxy: scriptJob() did not return a job id ({!r}) -- "
                  "the ROS proxy will not sync.".format(jobId))


def stop():
    """workspaceControl이 닫히거나(closeCommand) 플러그인이 언로드될 때
    (MaroPluginMain.cpp) 부른다.

    멱등하고, start()가 한 번도 안 불렸어도 안전하게 아무 것도 안 한다 --
    언로드는 창을 연 적이 있든 없든 항상 이 함수를 부르기 때문이다.

    어떤 경우에도 예외를 밖으로 내지 않는다. 이 함수의 호출자는 둘 다
    "정리 중"인 경로(창 닫기, 플러그인 언로드)라, 여기서 던지면 그 뒤의
    정리가 통째로 건너뛰어진다 -- MaroPluginMain.cpp가 uninitializePlugin
    전체를 try/catch로 감싸 둔 것과 같은 이유다.

    [최종 리뷰 I1] `_JOB_ID`는 **kill이 실제로 성공했을 때만** 지운다.
    예전에는 `finally`로 무조건 지웠는데, `scriptJob(kill=...)`이 예외를
    내면 잡은 살아있는 채로 그 id만 잃어버린다 -- 이 잡은 `protected=True`로
    만들어서 `-force` 없이는 안 죽으므로, id를 잃으면 이 함수도 다음
    `stop()` 호출도 다시는 그 잡을 못 찾는다. `_onIdle`이 그 죽지 않은
    잡 위에서 매 틱 `stop()`을 다시 부르지만 `_JOB_ID`가 이미 None이라
    아무 일도 안 하는 조용한 무한 루프가 된다 -- "자가 치유"와 "영구
    고장"이 겉보기엔 똑같아 보이는 바로 그 상황이라 이 함수가 막아야
    할 첫 번째 것이다. kill이 실패하면 id를 그대로 둬서 다음 시도가
    같은 잡을 다시 겨눌 수 있게 한다.
    """
    global _JOB_ID, _MAYA_PANEL, _ROS_PANEL, _LAST_ASSEMBLIES, _CONSECUTIVE_FAILURES
    killSucceededOrJobGone = True
    try:
        if _JOB_ID is not None and cmds.scriptJob(exists=_JOB_ID):
            cmds.scriptJob(kill=_JOB_ID, force=True)
    except Exception:  # noqa: BLE001 -- 정리 경로, 위 도크스트링 참고
        traceback.print_exc()
        killSucceededOrJobGone = False

    if killSucceededOrJobGone:
        _JOB_ID = None
    _MAYA_PANEL = None
    _ROS_PANEL = None
    _LAST_ASSEMBLIES = None
    _CONSECUTIVE_FAILURES = 0
