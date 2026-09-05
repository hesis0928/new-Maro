"""dagMenuProc 체이닝 -- Maya 오브젝트 마킹 메뉴에 "Maro node editor" 항목을
추가한다 (설계 스펙 §3, 계획 Task 7).

`dagMenuProc`는 프로세스 전역 MEL 프로시저 **하나**다. Maya 자신과 다른 모든
플러그인이 오브젝트 우클릭 메뉴를 만들 때 부르는 유일한 진입점이므로, 여기서
실수하면 이 플러그인만이 아니라 세션 전체의 우클릭 메뉴가 조용히 망가진다.
그래서 이 모듈의 규율은 하나다: **원본을 확실히 보존했다는 것을 확인하기
전에는 절대로 `dagMenuProc`를 덮어쓰지 않는다.**

실측 조사 결과 (2026-08-26, Maya 2026 / apiVersion 20260100, mayapy):

  * `whatIs "dagMenuProc"`는 **아직 소스되지 않았을 때**
    `'Script found in: C:/Program Files/Autodesk/Maya2026/scripts/others/dagMenuProc.mel'`
    를 돌려준다. `source dagMenuProc` 뒤에야
    `'Mel procedure found in: ...'`로 바뀐다.
    `dagMenuProc.mel`은 첫 우클릭 때 지연 소스되므로 플러그인 로드 시점에는
    보통 전자다 -- `"Mel procedure found in: "` 접두사 **하나만** 보는 구현은
    경로를 못 찾고 "원본 없음" 경로로 빠진다. 그래서 두 접두사를 모두 받는다.

  * `dagMenuProc`는 그 파일의 **마지막** 프로시저(2564-2915행)이고, 파일
    스코프 지역 프로시저(`proc setUpArtisanSkinContext`,
    `proc optionalDagMenuProc`)를 부른다. 실측으로
    `exists("setUpArtisanSkinContext") == 0`(소스 후에도)임을 확인했다.
    즉 프로시저 본문만 잘라 따로 소스하는 방식은 성립하지 않는다 --
    지역 프로시저가 같은 파일 안에 함께 있어야 한다. 파일 전체를 복사해서
    소스해야 하는 이유가 이것이다.

  * 그래서 이름 치환은 **프로시저 선언 헤더 한 줄에만** 한다. 파일 전체에
    대해 `"dagMenuProc"`를 무조건 치환하면 `uiRes("m_dagMenuProc.kSelect")`
    같은 지역화 리소스 키 200여 개와 `dagMenuProc_selectionMask_melToUI`,
    그리고 1745행의 `eval "source dagMenuProc"` 문자열까지 함께 망가진다.

Maya가 제공하는 **공식** 확장 훅도 확인했다: `optionalDagMenuProc`(같은 파일
63행)는 셰이프의 API 타입이 `kPlugin*`으로 시작할 때 `<nodeType>DagMenuProc`
프로시저를 부른다. 하지만 그것은 "셰이프가 플러그인 노드인 오브젝트"에만
걸린다 -- 우리 요구사항은 평범한 `mesh` 셰이프를 포함한 **모든** DAG
오브젝트이므로 이 훅으로는 덮을 수 없다. 체이닝이 불가피한 이유다.
"""
import os
import re
import tempfile

import maya.cmds as cmds
import maya.mel as mel

MENU_ITEM_LABEL = "Maro node editor"
LIDAR_MENU_ITEM_LABEL = "Maro LiDAR"

# 원본 dagMenuProc를 보존할 이름. 우리 래퍼가 가장 먼저 부른다.
_BACKUP_PROC_NAME = "maroDagMenuProcOriginal"

# MEL -> Python으로 인자를 넘기는 전역 변수 이름. 생성한 MEL 소스 안에
# 사용자 데이터(메뉴 이름/DAG 경로)를 문자열로 끼워 넣지 않기 위한 것이다 --
# 따옴표/이스케이프 문제를 만들 여지 자체를 없앤다.
_MEL_PARENT_VAR = "gMaroDagMenuParent"
_MEL_OBJECT_VAR = "gMaroDagMenuObject"

# [최종 리뷰 I-5] 우리가 설치한 래퍼가 **아직도** 현재의 dagMenuProc인지
# 판정하기 위한 흔적. install()이 세우고 uninstall()이 확인한다.
#
# 막으려는 것: 우리가 로드된 **뒤에** 다른 툴이 우리 래퍼 위에 자기 체인을
# 얹었는데, 우리 언로드가 Maya 원본 .mel을 무조건 다시 source해 버리는 상황.
# 그러면 그 툴의 체인까지 함께 날아간다 -- 이 모듈이 반대 방향(우리가 남의
# 것을 덮어쓰는 방향)에 대해 그토록 조심하는 바로 그 세션 전역 파괴를,
# 언로드 쪽에서 저지르는 셈이다.
#
# 판정 재료 두 가지를 실측으로 확인한 뒤 골랐다(mayapy, Maya 2026):
#
#  * `whatIs "dagMenuProc"`는 파일에서 온 정의면 경로를, mel.eval로 들어온
#    정의면 `'Mel procedure entered interactively.'`를 준다. 즉 **파일에서
#    다시 정의된 경우**(다른 툴이 자기 .mel을 source한 경우, 또는 누군가
#    Maya 원본을 이미 되돌린 경우)는 install 시점에 기록해 둔 문자열과
#    달라져서 확실히 잡힌다.
#  * MEL 전역 문자열은 설정해 두면 그대로 남고, 설정된 적 없으면 빈
#    문자열로 읽힌다. 새 씬/파일 로드로 MEL 환경이 초기화되는 등으로 흔적이
#    사라진 경우를 잡는다.
#
# 남는 한계를 정직하게 적어 둔다: 다른 툴이 **똑같이 mel.eval로** 자기
# 래퍼를 얹으면 whatIs는 양쪽 다 'entered interactively.'라서 구별되지
# 않는다(실측 확인). MEL은 프로시저 본문을 되읽는 수단을 주지 않으므로 이
# 경우까지 값싸게 가려낼 방법이 없다. 그래도 가장 흔하고 가장 파괴적인
# 경우(파일 기반 재정의)는 이 검사로 막힌다.
_MEL_SENTINEL_VAR = "gMaroDagMenuInstalledVersion"
_SENTINEL_VALUE = "maroDagMenu/1"

# whatIs가 MEL 스크립트를 보고할 때 쓰는 두 접두사. 위 모듈 독스트링 참고 --
# 소스 전/후로 문구가 다르다.
_WHATIS_PREFIXES = ("Mel procedure found in: ", "Script found in: ")

# `global proc dagMenuProc(string $parent, string $object)` 선언 헤더.
#
# 인자 목록까지 **정확히** 본다. 예전에는 "Maya 버전이 바뀌어 시그니처가
# 달라져도 걸리도록" 인자 목록을 무시했는데, 그건 여기서만큼은 느슨한 매칭이
# 안전한 쪽이 아니라 위험한 쪽이다: 시그니처가 다른 Maya에서도 헤더는 매치되고,
# 그러면 우리가 인자 두 개짜리 래퍼를 설치해 버린다. Maya의 실제 호출자
# (`dagObjectHit -mn` -> buildObjectMenuItemsNow.mel)는 그 버전의 인자 수로
# 부르므로 오브젝트를 우클릭할 때마다 MEL "wrong number of arguments" 에러가
# 나고, 그게 세션 내내 계속된다 -- 이 모듈이 막으려는 바로 그 실패다.
# 예상한 형태가 아니면 매치되지 않고(count == 0), 호출자의 "설치 포기" 경로로
# 떨어지는 것이 옳다.
#
# **바이트 패턴이다.** 원본 .mel을 디코드해서 다루면(errors="replace")
# UTF-8이 아닌 바이트가 섞인 지역화 설치본에서 문자열 리터럴이 조용히
# U+FFFD로 바뀐 사본을 source하게 된다 -- 그 사본이 곧 세션 전체의 우클릭
# 메뉴가 되므로 허용할 수 없는 종류의 손상이다. 바이트로 읽고 바이트로
# 치환해서 헤더 한 줄 말고는 원본과 바이트 단위로 동일한 복사본을 만든다.
_PROC_HEADER_RE = re.compile(
    rb"^([ \t]*global[ \t]+proc[ \t]+)dagMenuProc"
    rb"(?=[ \t]*\([ \t]*string[ \t]+\$\w+[ \t]*,[ \t]*string[ \t]+\$\w+[ \t]*\))",
    re.MULTILINE)

_INSTALLED = False
_ORIGINAL_SOURCE_FILE = None
_BACKUP_TEMP_FILE = None
# install()이 래퍼를 설치한 직후의 `whatIs "dagMenuProc"` 값. 위
# _MEL_SENTINEL_VAR 주석 참고.
_INSTALLED_WHATIS = None

# [2026-09-06 실측] MayaUSD가 로드된 세션에서 실제 우클릭으로 오브젝트
# 마킹 메뉴가 처음 완전히 빌드될 때(정확히는 그 이후에 도는 LookdevX/
# mayaUsd 콜백 어딘가에서), `dagMenuProc`가 우리 래퍼에서 Maya 원본으로
# 조용히 되돌아가는 것이 확인됐다 -- 우리 코드를 직접 호출하는 합성
# 테스트로는 재현되지 않고 실제 UI 우클릭에서만 재현되므로, 우리 쪽
# 로직의 결함이 아니라 외부(Autodesk 컴파일 바이너리, 문자열 참조가
# DataModel.dll 안에서만 발견됨)가 되돌리는 것으로 결론지었다. 정확한
# 트리거는 폐쇄 소스라 알 수 없고, 실측상 세션당 한 번(첫 실제 메뉴
# 빌드 시점)만 일어난다.
#
# `dagMenuProc` 자체가 그 순간 우리 체인에서 빠지므로, 그 이후 우클릭에서
# 우리 코드는 아예 안 불린다 -- 즉 "이 되돌림을 감지해서 스스로 복구하는
# 로직"은 dagMenuProc 체인 **바깥**에 있어야만 동작한다. idle scriptJob
# 워치독을 쓴다(maroRosProxy.py의 idle 콜백과 동일한 패턴/보수성).
_WATCHDOG_JOB_ID = None


def _originalProcSourceFile():
    """dagMenuProc를 정의한 .mel 파일의 절대 경로. 찾지 못하면 None."""
    if mel.eval('exists("dagMenuProc")') != 1:
        return None
    info = mel.eval('whatIs "dagMenuProc"')
    if not isinstance(info, str):
        return None
    for prefix in _WHATIS_PREFIXES:
        if info.startswith(prefix):
            path = info[len(prefix):].strip()
            return path if path else None
    # "Command", "Unknown", 또는 우리가 모르는 문구. 파일이 없으므로
    # 원본을 보존할 방법이 없다 -- 호출자가 설치를 포기한다.
    return None


def _writeBackupCopy(sourceFile):
    """`sourceFile`을 통째로 복사하되 `global proc dagMenuProc` 선언 헤더만
    `_BACKUP_PROC_NAME`으로 바꾼 임시 .mel을 만들어 경로를 돌려준다.
    헤더를 정확히 한 번 바꾸지 못하면 None."""
    with open(sourceFile, "rb") as f:
        original = f.read()

    renamed, count = _PROC_HEADER_RE.subn(
        rb"\g<1>" + _BACKUP_PROC_NAME.encode("ascii"), original)
    if count != 1:
        # 0이면 우리가 아는 선언 형태가 아니고, 2 이상이면 파일 구조가
        # 예상과 다르다. 어느 쪽이든 추측으로 밀어붙이지 않는다.
        return None

    fd, tempPath = tempfile.mkstemp(suffix=".mel", prefix="maroDagMenuBackup_")
    with os.fdopen(fd, "wb") as f:
        f.write(renamed)
    return tempPath


def _melPath(path):
    """MEL 문자열 리터럴에 넣을 수 있는 경로. Windows 역슬래시를 슬래시로
    바꾸고 큰따옴표를 이스케이프한다."""
    return path.replace("\\", "/").replace('"', '\\"')


def install():
    """플러그인 로드 시 한 번 부른다. 멱등 -- 이미 설치돼 있으면 아무것도
    하지 않는다.

    원본을 백업 이름으로 보존하는 데 실패하면 **아무것도 바꾸지 않고**
    돌아온다. 우리 항목이 안 보이는 것은 불편일 뿐이지만, 원본 없이
    dagMenuProc를 덮어쓰면 세션 전체의 우클릭 메뉴가 사라진다.
    """
    global _INSTALLED, _ORIGINAL_SOURCE_FILE, _BACKUP_TEMP_FILE, _INSTALLED_WHATIS
    if _INSTALLED:
        return True

    sourceFile = _originalProcSourceFile()
    if not sourceFile or not os.path.isfile(sourceFile):
        cmds.warning("Maro: could not locate Maya's dagMenuProc.mel "
                     "(whatIs said {!r}); leaving the object marking menu "
                     "untouched.".format(mel.eval('whatIs "dagMenuProc"')))
        return False

    tempPath = _writeBackupCopy(sourceFile)
    if tempPath is None:
        cmds.warning("Maro: dagMenuProc.mel does not have the expected "
                     "'global proc dagMenuProc(' declaration; leaving the "
                     "object marking menu untouched.")
        return False

    try:
        mel.eval('source "{}"'.format(_melPath(tempPath)))
    except Exception as exc:  # pragma: no cover - 환경 의존
        cmds.warning("Maro: failed to source the dagMenuProc backup copy "
                     "({}); leaving the object marking menu untouched."
                     .format(exc))
        _removeQuietly(tempPath)
        return False

    # 여기가 안전장치의 핵심이다. 백업이 실제로 존재할 때에만 덮어쓴다.
    if mel.eval('exists("{}")'.format(_BACKUP_PROC_NAME)) != 1:
        cmds.warning("Maro: the dagMenuProc backup copy did not define {}; "
                     "leaving the object marking menu untouched."
                     .format(_BACKUP_PROC_NAME))
        _removeQuietly(tempPath)
        return False

    # 우리 래퍼. 원본을 **먼저** 부른다 -- 우리 쪽이 어떤 이유로 실패해도
    # Maya 본래 항목들은 이미 다 붙어 있다.
    #
    # 메뉴 이름과 DAG 경로는 MEL 전역 변수로 넘긴다. 생성한 소스 안에
    # 문자열로 끼워 넣으면 따옴표/역슬래시 이스케이프 문제가 생길 수 있는데,
    # 전역 변수를 거치면 그런 경로 자체가 없다.
    mel.eval('''
        global proc dagMenuProc(string $parent, string $object)
        {{
            {backup}($parent, $object);
            global string ${parentVar};
            global string ${objectVar};
            ${parentVar} = $parent;
            ${objectVar} = $object;
            python("import maroDagMenu; maroDagMenu._addMenuItem()");
        }}
    '''.format(backup=_BACKUP_PROC_NAME,
               parentVar=_MEL_PARENT_VAR,
               objectVar=_MEL_OBJECT_VAR))

    # [최종 리뷰 I-5] "지금의 dagMenuProc가 아직 우리 것인가"를 언로드 때
    # 판정하기 위한 흔적 두 개를 남긴다. 위 _MEL_SENTINEL_VAR 주석 참고.
    mel.eval('global string ${0}; ${0} = "{1}";'.format(
        _MEL_SENTINEL_VAR, _SENTINEL_VALUE))
    whatIsNow = mel.eval('whatIs "dagMenuProc"')
    _INSTALLED_WHATIS = whatIsNow if isinstance(whatIsNow, str) else None

    _ORIGINAL_SOURCE_FILE = sourceFile
    # 임시 파일은 세션 동안 남겨 두고 uninstall에서 지운다. MEL은 source
    # 시점에 파일 전체를 메모리로 컴파일하므로 곧바로 지워도 동작하지만,
    # 파일 스코프 지역 프로시저(setUpArtisanSkinContext 등)의 해소가 파일
    # 경로에 전혀 의존하지 않는다는 것까지 보장할 근거가 없어서 굳이
    # 모험하지 않는다. 비용은 세션당 임시 파일 하나다.
    _BACKUP_TEMP_FILE = tempPath
    _INSTALLED = True
    _startWatchdog()
    return True


def _watchdogTick():
    """idle scriptJob의 본체 -- 매 틱, `dagMenuProc`가 여전히 우리 래퍼인지
    확인하고 아니면 조용히 재설치한다. 위 `_WATCHDOG_JOB_ID` 주석에 적은
    MayaUSD/UFE 쪽 되돌림에 대한 방어다.

    `maroRosProxy._onIdle()`과 같은 규율을 따른다: 이 함수에서 예외가 새어
    나가면 idle이 초당 여러 번 오므로 스크립트 에디터가 도배된다. 재설치
    자체가 실패해도(`install()`이 이미 경고를 내고 `False`를 돌려주므로)
    여기서는 조용히 다음 틱을 기다린다 -- 매 틱 재시도이므로 일시적 실패는
    스스로 회복된다.
    """
    global _INSTALLED
    try:
        if not _INSTALLED:
            return
        if _wrapperStillOurs():
            return
        _INSTALLED = False
        install()
    except Exception:  # noqa: BLE001 -- idle 콜백 경계, 절대 새어나가면 안 됨
        import traceback
        traceback.print_exc()


def _startWatchdog():
    """idle 워치독을 시작한다. 멱등 -- 이미 돌고 있으면 아무것도 안 한다."""
    global _WATCHDOG_JOB_ID
    if _WATCHDOG_JOB_ID is not None and cmds.scriptJob(exists=_WATCHDOG_JOB_ID):
        return
    jobId = cmds.scriptJob(event=["idle", _watchdogTick], protected=True)
    if isinstance(jobId, int):
        _WATCHDOG_JOB_ID = jobId
    else:
        # 배치 mayapy에서는 scriptJob이 아무것도 만들지 않고 None을 준다
        # (maroRosProxy.start()와 동일 실측) -- 거기서는 우클릭 UI 자체가
        #없으니 워치독이 지킬 것도 없어 정상이다.
        _WATCHDOG_JOB_ID = None
        if not cmds.about(batch=True):
            print("maroDagMenu: scriptJob() did not return a job id ({!r}) -- "
                  "the dagMenuProc watchdog will not run.".format(jobId))


def _stopWatchdog():
    """idle 워치독을 멈춘다. 멱등, 실패해도 예외를 밖으로 내지 않는다
    (uninstall()의 두 종료 경로 모두에서 부르므로 그 정리를 막으면 안 됨).

    `maroRosProxy.stop()`과 같은 이유로, kill이 실제로 성공했을 때에만
    `_WATCHDOG_JOB_ID`를 지운다 -- 실패한 채로 지우면 이 잡은 `protected=True`
    라 다시는 못 찾고 영원히 남는다.
    """
    global _WATCHDOG_JOB_ID
    if _WATCHDOG_JOB_ID is None:
        return
    try:
        if cmds.scriptJob(exists=_WATCHDOG_JOB_ID):
            cmds.scriptJob(kill=_WATCHDOG_JOB_ID, force=True)
        _WATCHDOG_JOB_ID = None
    except Exception:  # noqa: BLE001 -- 정리 경로
        import traceback
        traceback.print_exc()


def uninstall():
    """플러그인 언로드 시 한 번 부른다. 멱등.

    원본 .mel을 다시 source해서 Maya 본래 정의를 그대로 되돌린다 -- 얇은
    래퍼를 남기는 것보다 깨끗하다(whatIs도 원래 경로를 가리키게 된다).
    다시 source하지 못하면 백업을 그대로 호출하는 래퍼로 대신한다.

    [최종 리뷰 I-5] 단, **지금의 dagMenuProc가 아직 우리 것일 때에만**
    복원한다. 우리가 로드된 뒤에 다른 툴이 우리 래퍼 위에 자기 체인을
    얹었다면, 여기서 Maya 원본을 무조건 다시 source하는 것은 그 툴의 체인을
    말없이 지우는 짓이다 -- 이 모듈이 install() 쪽에서 그토록 조심하는
    "세션 전역 우클릭 메뉴 파괴"를 언로드 쪽에서 저지르는 것과 같다. 흔적이
    남아 있지 않으면 복원을 건너뛰고 경고만 한다. 그 경우 남는 것은 남의
    체인 안에 우리 파이썬 호출이 하나 낀 상태인데, 그건 _addMenuItem()이
    스스로 방어한다(모듈이 없거나 커맨드가 없으면 cmds.warning만 내고
    조용히 돌아온다) -- 남의 메뉴를 통째로 날리는 쪽보다 훨씬 낫다.
    """
    global _INSTALLED, _BACKUP_TEMP_FILE, _INSTALLED_WHATIS
    if not _INSTALLED:
        return

    if not _wrapperStillOurs():
        cmds.warning(
            "Maro: dagMenuProc has been redefined by something else since Maro "
            "installed its wrapper -- leaving it alone instead of clobbering "
            "the newer chain. Maro's menu item may linger until Maya restarts.")
        _stopWatchdog()
        if _BACKUP_TEMP_FILE:
            _removeQuietly(_BACKUP_TEMP_FILE)
            _BACKUP_TEMP_FILE = None
        _INSTALLED = False
        _INSTALLED_WHATIS = None
        # 흔적을 지운다 -- 이 경로는 복원하지 않고 돌아가지만, 다른 모든
        # 종료 경로와 같은 정리 규율(설치 흔적을 남기지 않는다)을 지킨다.
        mel.eval('global string ${0}; ${0} = "";'.format(_MEL_SENTINEL_VAR))
        return

    restored = False
    if _ORIGINAL_SOURCE_FILE and os.path.isfile(_ORIGINAL_SOURCE_FILE):
        try:
            mel.eval('source "{}"'.format(_melPath(_ORIGINAL_SOURCE_FILE)))
            restored = True
        except Exception:
            restored = False

    if not restored and mel.eval('exists("{}")'.format(_BACKUP_PROC_NAME)) == 1:
        mel.eval('''
            global proc dagMenuProc(string $parent, string $object)
            {{
                {backup}($parent, $object);
            }}
        '''.format(backup=_BACKUP_PROC_NAME))
        restored = True

    if not restored:
        cmds.warning("Maro: could not restore Maya's original dagMenuProc. "
                     "Restart Maya to get the default object marking menu back.")

    _stopWatchdog()
    if _BACKUP_TEMP_FILE:
        _removeQuietly(_BACKUP_TEMP_FILE)
        _BACKUP_TEMP_FILE = None
    _INSTALLED = False
    _INSTALLED_WHATIS = None
    # 흔적을 지운다 -- 남겨 두면 다음 install() 전에 누가 이 값을 보고
    # "아직 설치돼 있다"로 오판할 수 있다.
    mel.eval('global string ${0}; ${0} = "";'.format(_MEL_SENTINEL_VAR))


def _wrapperStillOurs():
    """지금의 dagMenuProc가 install()이 설치한 우리 래퍼 그대로인가.

    판정에 쓰는 두 재료와 그 한계는 위 _MEL_SENTINEL_VAR 주석에 정리했다.
    판정 자체가 예외를 내면 **복원하지 않는 쪽**으로 기운다 -- 언로드
    경로에서 확신이 없을 때는 아무것도 안 하는 것이 남의 체인을 날리는
    것보다 안전하다(install()이 "원본을 확실히 보존하지 못하면 아무것도
    바꾸지 않는다"고 정한 것과 같은 방향의 보수성이다).
    """
    try:
        if _melGlobalString(_MEL_SENTINEL_VAR) != _SENTINEL_VALUE:
            return False
        if _INSTALLED_WHATIS is None:
            return False
        return mel.eval('whatIs "dagMenuProc"') == _INSTALLED_WHATIS
    except Exception:  # noqa: BLE001 -- 언로드 경계
        import traceback
        traceback.print_exc()
        return False


def _removeQuietly(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _melGlobalString(name):
    """MEL 전역 문자열 변수를 읽는다. maya.mel.eval은 전역 스코프에서
    돌지만 변수 자체를 식으로 줄 수는 없어서, 임시 변수에 대입한 값을
    받는 관용구를 쓴다(`$gMainWindow`를 읽을 때와 같은 방식)."""
    value = mel.eval('global string ${0}; $maroTmp = ${0};'.format(name))
    return value if isinstance(value, str) else ""


def _addMenuItem():
    """생성한 MEL 래퍼가 부른다. 인자는 MEL 전역 변수에서 읽는다.

    여기서 나는 예외는 절대 밖으로 내보내지 않는다 -- MEL 쪽으로 새어
    나가면 우클릭 메뉴 생성 전체가 에러로 끝난다. (원본은 이미 이 시점에
    호출이 끝나 있으므로 Maya 본래 항목은 어차피 살아 있다.)
    """
    try:
        parentMenu = _melGlobalString(_MEL_PARENT_VAR)
        if not parentMenu or not cmds.popupMenu(parentMenu, exists=True):
            return
        if _nativeMenuSuppressed():
            return
        object_ = _resolveObject()
        if not object_:
            return
        cmds.menuItem(parent=parentMenu, label=MENU_ITEM_LABEL,
                      command=lambda *_args: _onMenuItemClicked(object_))
        # "Maro LiDAR"는 오브젝트 종류와 무관하게 항상 노출된다(설계 스펙
        # §5.1) -- 메쉬가 없어도 클릭 시점에 조건을 자동으로 맞춘다
        # (_onLidarMenuItemClicked/_createPlaceholderTargetMesh 참고).
        cmds.menuItem(parent=parentMenu, label=LIDAR_MENU_ITEM_LABEL,
                      command=lambda *_args: _onLidarMenuItemClicked(object_))
    except Exception as exc:  # pragma: no cover - UI 경로
        cmds.warning("Maro: failed to add the '{}'/'{}' menu items: {}"
                     .format(MENU_ITEM_LABEL, LIDAR_MENU_ITEM_LABEL, exc))


def _resolveObject():
    """항목을 붙일 대상 DAG 오브젝트. 붙이면 안 되는 상황이면 빈 문자열.

    Maya의 dagMenuProc에는 **일반 오브젝트 메뉴를 만들지 않고** 곧바로
    return하는 경로가 있다. 그중 하나가 뷰큐브다(2602-2605행):

        if ($object == "CubeCompass") { createViewCubeMenuItems($parent); return; }

    `"CubeCompass"`는 노드 이름이 아니라 센티널 문자열이고, 기본 뷰포트마다
    뷰큐브가 있으므로 이 경로는 아주 흔하다. 원본이 무엇을 했는지와 무관하게
    항목을 붙이면 노드 컨텍스트 메뉴가 전혀 아닌 메뉴에 우리 항목이 끼어든다.
    이 기능의 범위는 표준 DAG 오브젝트(transform/shape)뿐이므로, 실재하는
    노드가 아니면 아무것도 하지 않는 것이 맞다.
    """
    object_ = _melGlobalString(_MEL_OBJECT_VAR)
    if not object_:
        # buildObjectMenuItemsNow.mel은 커서 아래에 아무것도 없으면 빈
        # 문자열을 넘긴다. Maya 자신의 dagMenuProc와 같은 방식으로
        # 선택/하이라이트 목록에서 대상을 고른다.
        object_ = _leadObject()
    if not object_ or not cmds.objExists(object_):
        return ""
    return object_


def _nativeMenuSuppressed():
    """Maya의 dagMenuProc가 오브젝트 메뉴를 만들지 않고 return하는 나머지 두
    경로(2579-2592행: traversal 마킹 메뉴, 모델링 툴킷 RMB-complete)에
    해당하는가.

    뷰큐브와 달리 이 둘은 `$object`가 멀쩡한 DAG 경로라서 `_resolveObject()`의
    실재 검사로는 걸러지지 않는다. 판정에 실패하면 **억제하지 않는다** --
    잘못 판정해서 우리 항목이 하나 더 붙는 쪽이, 판정 코드가 예외를 내서
    우클릭 경로를 흔드는 쪽보다 낫다.

    질의는 전부 `exists(...)`로 감싼다. Maya 자신은 2589행에서 `nexCtx`를
    그냥 부르지만(GUI에서는 모델링 툴킷이 늘 로드돼 있다), 우리 쪽에서는
    없는 커맨드를 부르면 우클릭할 때마다 스크립트 에디터에 MEL 에러가 찍힌다.
    `catchQuiet`로는 못 막는다 -- 존재하지 않는 커맨드는 런타임 에러가 아니라
    **구문 에러**라서 eval 자체가 컴파일에 실패한다(실측). 배치에서
    `modelingTookitActive()`가 1을 돌려주면서 `exists("nexCtx") == 0`인 조합이
    실제로 나오므로 커맨드 존재 확인이 반드시 필요하다.
    """
    try:
        if mel.eval('exists("hasTraversalMM")') == 1 and mel.eval("hasTraversalMM()"):
            # 임시 변수 이름은 _melGlobalString의 $maroTmp와 일부러 다르게
            # 둔다 -- 같은 이름을 string/int로 번갈아 쓰면 MEL 타입 충돌이
            # 날 여지가 있다.
            if mel.eval("global int $gTraversal; $maroTraversalTmp = $gTraversal;"):
                return True
        if mel.eval('exists("modelingTookitActive")') == 1 \
                and mel.eval('exists("nexCtx")') == 1 \
                and mel.eval("modelingTookitActive()") \
                and mel.eval("nexCtx -q -rmbComplete"):
            return True
    except Exception:
        return False
    return False


def _leadObject():
    for kwargs in ({"selection": True}, {"hilite": True}):
        found = cmds.ls(tail=1, type=("transform", "shape"), **kwargs) or []
        if found:
            return found[0]
    return ""


def _findBoundAxis(object_):
    """object_에 이미 바인딩된 maroAxis가 있으면 그 풀 DAG 경로, 없으면 None.

    풀 경로로 정규화하는 이유: openSingleObjectNodeEditor()의 싱글턴
    레지스트리(_OPEN_EDITORS, maroSingleObjectNodeEditor.py)는 넘겨받은
    문자열을 그대로 딕셔너리 키로 쓴다. cmds.listConnections()는 이름
    충돌이 없으면 짧은 이름을 줄 수 있는데, MaroAxisEditorCommands.cpp의
    listAxes()(ONE이 GSON 더블클릭 시 쓰는 경로, Task 6)는 항상
    MDagPath::fullPathName()을 낸다. 두 호출부가 같은 축에 대해 다른
    문자열을 넘기면 싱글턴 검사가 같은 축을 다른 축으로 오판해 SONE
    창이 중복 생성된다 -- 그래서 여기서 항상 풀 경로로 맞춘다.

    `shapes=True`가 반드시 필요하다 (실측으로 발견): maroAxis는 로케이터형
    DAG 셰이프 노드라서, cmds.listConnections()는 기본값(shapes=False)일 때
    셰이프 자신이 아니라 그 부모 트랜스폼 이름을 돌려준다. type="maroAxis"
    필터는 셰이프 기준으로 올바르게 매치하지만, 결과로 나오는 이름은
    부모 트랜스폼("transform1" 같은 평범한 이름)이라 그 다음
    attributeQuery("targetObject", node=connection, ...)가 targetObject가
    없는 트랜스폼을 조회하게 되어 항상 False -> 이미 바인딩된 축을 절대
    못 찾는다(매번 "축 없음" 경로로 빠져 새 축이 중복 생성된다). mayapy로
    직접 재현: shapes=True 없이는 ['transform1']을, 있으면 실제 셰이프
    ['maroAxis1']을 돌려줌을 확인했다.
    """
    for connection in cmds.listConnections(
            object_, type="maroAxis", plugs=False, shapes=True) or []:
        if cmds.attributeQuery("targetObject", node=connection, exists=True):
            return cmds.ls(connection, long=True)[0]
    return None


def _onMenuItemClicked(object_):
    import maroSingleObjectNodeEditor

    existingAxis = _findBoundAxis(object_)
    if existingAxis is not None:
        maroSingleObjectNodeEditor.openSingleObjectNodeEditor(existingAxis)
        return

    shortName = object_.split("|")[-1]
    result = cmds.promptDialog(
        title="New Maro Axis", message="Display name:",
        text=shortName, button=["OK", "Cancel"],
        defaultButton="OK", cancelButton="Cancel", dismissString="Cancel")
    if result != "OK":
        return
    displayName = cmds.promptDialog(query=True, text=True)

    colorResult = cmds.colorEditor(rgbValue=(0.5, 0.7, 0.9))
    values = colorResult.split()
    if values[-1] != "1":  # colorEditor's last token is 0 on cancel, 1 on OK
        return
    r, g, b = float(values[0]), float(values[1]), float(values[2])

    cmds.undoInfo(openChunk=True)
    bindFailed = False
    try:
        axis = cmds.createNode("maroAxis")
        # 풀 경로로 정규화 -- 위 _findBoundAxis()의 docstring과 같은 이유.
        # createNode()는 이름이 유일하면 짧은 이름을 주므로, 나중에 같은
        # 짧은 이름의 노드가 다른 계층에 생겨도 이 축의 SONE 키는 처음
        # 만들어질 때의 형태에 머물러 있지 않게 항상 여기서 확정한다.
        axis = cmds.ls(axis, long=True)[0]
        try:
            cmds.maroBindAxis(axis, object_)
            cmds.setAttr(axis + ".displayName", displayName, type="string")
            cmds.setAttr(axis + ".displayColor", r, g, b, type="double3")
        except Exception as exc:
            # maroBindAxis는 대상이 transform이 아니거나 이미 축이 바인딩돼
            # 있으면(위 _findBoundAxis 검사와의 TOCTOU 경합 포함) 예외를
            # 던질 수 있다. 이 시점에 axis 노드는 이미 만들어져 있으므로
            # 그대로 두면 바인딩도 안 되고 이름/색도 없는 고아 노드가
            # 씬에 남는다 -- 지운다. 예외는 _addMenuItem과 같은 규율로
            # cmds.warning으로만 알리고 밖으로 내보내지 않는다.
            bindFailed = True
            # [최종 리뷰 Minor-4] 정리 자체도 실패할 수 있다(예: 그 사이에
            # 다른 경로가 이미 지웠거나, 삭제가 거부되는 상태). 여기서 raw
            # 예외가 새면 이 콜백의 규율이 깨지므로 따로 감싼다.
            #
            # 그리고 셰이프만 지우면 빈 부모 트랜스폼이 남는다 --
            # createNode("maroAxis")는 로케이터형 DAG 셰이프라 Maya가 부모
            # 트랜스폼을 자동으로 만들고, 셰이프 삭제로는 그것이 사라지지
            # 않는다(실측 확인, maroObjectNodeEditor._deleteAxis()의
            # 도크스트링과 같은 근거). 고아를 안 남기는 것이 이 블록의
            # 존재 이유이므로 부모까지 함께 지운다.
            try:
                parents = cmds.listRelatives(axis, parent=True, fullPath=True) or []
                if cmds.objExists(axis):
                    cmds.delete(axis)
                for parent in parents:
                    if cmds.objExists(parent):
                        cmds.delete(parent)
            except Exception as deleteExc:  # noqa: BLE001 -- 마킹 메뉴 콜백 경계
                cmds.warning("Maro: failed to clean up the orphaned axis '{}': {}"
                             .format(axis, deleteExc))
            cmds.warning("Maro: failed to bind the new axis to '{}': {}"
                         .format(object_, exc))
    finally:
        cmds.undoInfo(closeChunk=True)

    if bindFailed:
        return

    # [최종 리뷰 Minor-7] ONE에 새 축이 생겼음을 **명시적으로** 알린다.
    # 그전에는 createNode()가 마침 씬 선택을 바꾸고, 그것이 마침
    # SelectionChanged scriptJob을 깨워 refresh()에 닿는 우연한 경로에
    # 기대고 있었다. ONE이 안 열려 있으면 무동작이다.
    try:
        import maroObjectNodeEditor
        maroObjectNodeEditor.refreshIfOpen()
    except Exception as exc:  # noqa: BLE001 -- 마킹 메뉴 콜백 경계
        cmds.warning("Maro: could not refresh the object node editor: {}".format(exc))

    maroSingleObjectNodeEditor.openSingleObjectNodeEditor(axis)


def _findLidarForMesh(object_):
    """object_에 이미 묶여 있는 maroLidar가 있으면 그 풀 DAG 경로, 없으면
    None.

    [I-1] 두 가지 경로를 모두 확인해야 한다:

      (a) object_ 자신이 어떤 maroLidar의 targetMeshes[]에 .message로 연결돼
          있는 경우 -- 메쉬를 직접 클릭해서 그 메쉬 자신이 타겟이 된 경우
          (또는 설정 팝업에서 나중에 타겟으로 추가된 임의의 메쉬).

      (b) object_ 자신이 maroLidar 셰이프를 직속 자식으로 "탑재"하고 있는
          경우 -- _onLidarMenuItemClicked()는 메쉬가 있든 없든 항상 lidar
          셰이프를 `cmds.parent(lidar, object_, relative=True, shape=True)`로
          object_ 밑에 옮긴다. 메쉬가 없어서 placeholder 구가 대신 타겟이
          된 경우, object_ 자신은 targetMeshes 연결에 전혀 나타나지 않으므로
          (a)만으로는 못 찾는다 -- 조인트/로케이터 같은 비-메쉬 오브젝트에
          두 번째로 우클릭하면 기존 LiDAR를 못 찾고 완전한 중복(두 번째
          maroLidar + maroPointCloud)을 만들던 버그가 이것이었다. (a)가
          이미 다루는 메쉬 케이스는 그대로 두고, listRelatives로 이 구멍만
          메운다.

    _findBoundAxis()와 같은 이유로 shapes=True/listRelatives(shapes=True)가
    필요하다: maroLidar도 로케이터형 DAG 셰이프 노드라서, 기본값이면 셰이프
    자신이 아니라 부모 트랜스폼 이름이 돌아온다.
    """
    mounted = cmds.listRelatives(
        object_, shapes=True, fullPath=True, type="maroLidar") or []
    if mounted:
        return cmds.ls(mounted[0], long=True)[0]

    connections = cmds.listConnections(
        object_, type="maroLidar", plugs=False, shapes=True) or []
    if not connections:
        return None
    return cmds.ls(connections[0], long=True)[0]


def _hasMeshShape(object_):
    """object_ 자신이 메쉬 셰이프를 가진 트랜스폼이거나 메쉬 셰이프 그
    자체인가. maroLidar.targetMeshes는 관례상 메쉬 **트랜스폼**의 .message에
    연결한다(MaroLidarScan.cpp의 extractMeshBuffers와 같은 관례 --
    MFnMesh가 셰이프까지 스스로 내려간다)."""
    if cmds.listRelatives(object_, shapes=True, fullPath=True, type="mesh"):
        return True
    return cmds.objectType(object_) == "mesh"


def _createPlaceholderTargetMesh(object_):
    """object_에 메쉬 셰이프가 없을 때 자동으로 만드는 대체 스캔 타겟
    (설계 스펙 §5.2).

    작은 구를 object_의 자식으로, object_의 월드 바운딩박스 상단(ymax)
    중앙에 놓는다. 바운딩박스가 점에 가까운 조인트/로케이터는 거의 원점에
    생긴다 -- 계산 자체는 오브젝트 종류와 무관하게 일관되게 적용되므로 이는
    받아들여지는 동작이다. 생성 직후 이 구를 선택 상태로 만들어 사용자가
    바로 크기/위치를 다듬을 수 있게 한다.
    """
    # [Fix round 2] object_의 바운딩박스는 반드시 구를 만들고 그 밑에
    # 매달기 **전에** 측정해야 한다. cmds.exactWorldBoundingBox()는 모든 DAG
    # 자손을 포함하므로, 구를 먼저 parent()해 버리면(새 구는 항상 월드 원점
    # (0,0,0)에서 시작하고, cmds.parent()의 기본 동작은 월드 위치를
    # 보존한다) 그 시점의 bbox 측정값이 "아직 배치되지 않은 구 자신의 원점
    # 위치"에 오염된다 -- object_가 원점에서 먼 곳에 있을수록 측정된 중심이
    # 원점 쪽으로 끌려간다. 실측: 조인트가 월드 (10, 3, 0)에 있을 때 스펙상
    # 정답은 (10.0, 4.0, 0.0)인데, 구를 먼저 옮기고 나서 bbox를 재던 예전
    # 코드는 (5.0, 4.0, 0.0)을 냈다(X가 원점 쪽으로 오염됨; 이 케이스는
    # 우연히 Y만 맞았을 뿐, 조인트가 (10, -5, 0)이면 정답 -4.0 대신 구 자신의
    # 반지름인 1.0이 나와 Y도 틀린다). 그래서 bbox와 topCenter는 구를 만들기
    # 전, object_가 아직 그대로인 상태에서 먼저 계산한다.
    bbox = cmds.exactWorldBoundingBox(object_)
    topCenter = ((bbox[0] + bbox[3]) / 2.0, bbox[4], (bbox[2] + bbox[5]) / 2.0)

    shortName = object_.split("|")[-1]
    sphereTransform, _makeNode = cmds.polySphere(name=shortName + "_maroLidarTarget", radius=1.0)
    # [I-2b] polySphere가 이미 씬에 노드를 만든 뒤이므로, 아래에서 무엇이든
    # 실패하면(parent/xform/select) 이 함수 자신이 만든 것을 지우고 나서
    # 다시 던진다. 호출부(_onLidarMenuItemClicked)의 실패 정리 로직은 이
    # 함수가 값을 **정상적으로 반환한 뒤에야** 생성된 구를 알게 되므로, 반환
    # 전에 예외가 나면 그쪽은 이 구의 존재 자체를 모른다 -- 정리 책임을
    # 여기서 스스로 지는 것이 가장 간단하고 확실하다.
    sphereFullPath = None
    try:
        # [C-1] cmds.parent()가 옮긴 뒤에는 옮기기 전의 이름(sphereTransform)이
        # 더 이상 유효하지 않을 수 있다 -- 씬에 같은 짧은 이름의 노드가 이미
        # 존재하면(예: 같은 오브젝트에 두 번째로 우클릭해서 placeholder를 다시
        # 만들려는 경우) polySphere가 "|shortName" 같은 경로-한정 이름을 돌려주고,
        # cmds.parent() 뒤에는 그 경로가 더는 아무것도 가리키지 않아
        # cmds.ls(sphereTransform, long=True)가 빈 리스트를 주어 [0]에서
        # IndexError가 난다(실측 확인). _onLidarMenuItemClicked이 lidar 셰이프에
        # 대해 이미 쓰는 것과 같은 방식으로, cmds.parent()가 돌려주는 새 이름과
        # 이미 알고 있는 새 부모(object_)를 조합해 모호하지 않은 새 풀 경로를
        # 직접 구성한다.
        newShortName = cmds.parent(sphereTransform, object_)[0].split("|")[-1]
        sphereFullPath = object_ + "|" + newShortName

        cmds.xform(sphereFullPath, worldSpace=True, translation=topCenter)
        cmds.select(sphereFullPath, replace=True)
    except Exception:
        # parent()가 성공한 뒤라면 sphereFullPath가 살아 있는 이름이고
        # sphereTransform 쪽은 [C-1] 사유로 이미 죽은 이름일 수 있다. parent()
        # 자체가 실패했다면 반대로 sphereFullPath는 아직 None이고
        # sphereTransform이 여전히 유효하다. 그래서 sphereFullPath를 먼저
        # 확인하고, 없으면 sphereTransform으로 대체한다.
        orphan = sphereFullPath if sphereFullPath and cmds.objExists(sphereFullPath) else sphereTransform
        # [최종 리뷰 Minor-8] 정리 자체도 실패할 수 있다(그 사이 다른 경로가
        # 이미 지웠거나, 삭제가 거부되는 상태). 여기서 cmds.delete()가 던지면
        # 그 예외가 원래 예외를 **대체**해 버려서, 호출부와 사용자는 진짜
        # 원인("parent/xform/select 중 무엇이 왜 실패했는가")을 영영 못 본다.
        # 고아 하나가 남는 것보다 원인을 잃는 쪽이 나쁘므로, 정리 실패는
        # 경고로만 알리고 원래 예외를 그대로 올려보낸다
        # (_onMenuItemClicked의 축 롤백 블록과 같은 규율).
        try:
            if orphan and cmds.objExists(orphan):
                cmds.delete(orphan)
        except Exception as deleteExc:  # noqa: BLE001 -- 정리 경로
            cmds.warning("Maro: failed to clean up the orphaned placeholder mesh "
                         "'{}': {}".format(orphan, deleteExc))
        raise

    return sphereFullPath


def _onLidarMenuItemClicked(object_):
    """"Maro LiDAR" 마킹메뉴 항목의 핸들러. _onMenuItemClicked()와 달리
    promptDialog/colorEditor 같은 모달 다이얼로그를 전혀 쓰지 않는다 --
    LiDAR는 ONE/GSON 그루핑에 참여하지 않아 이름/색 입력이 필요 없다
    (설계 스펙 §5.3). 그래서 이 함수는 mayapy 배치에서도 안전하게 직접 호출할
    수 있다(tests/maya/test_lidar_menu.py)."""
    import maroLidarPanel
    import maroRosProxy

    existingLidar = _findLidarForMesh(object_)
    if existingLidar is not None:
        maroLidarPanel.openLidarPanel(existingLidar)
        return

    cmds.undoInfo(openChunk=True)
    lidar = None
    lidarAutoTransform = None
    pointCloud = None
    pointCloudAutoTransform = None
    # [I-2] 메쉬가 없어서 _createPlaceholderTargetMesh()가 만든 구도 이
    # 함수가 만든 노드다 -- 그 뒤에 실패하면(예: connectAttr) 다른 노드들과
    # 같은 규율로 지워야 고아로 남지 않는다.
    placeholderSphere = None
    try:
        lidar = cmds.createNode("maroLidar")
        lidar = cmds.ls(lidar, long=True)[0]
        # createNode("maroLidar")는 로케이터형 DAG 셰이프라 Maya가 새
        # 트랜스폼을 자동으로 만든다(_onMenuItemClicked의 축 생성과 같은
        # 관례). 축과 달리 여기서는 이 셰이프를 클릭한 오브젝트의 실제
        # DAG 자식으로 옮긴다 -- LiDAR는 탑재된 오브젝트의 월드 트랜스폼을
        # 그대로 상속받아야 하기 때문이다(축의 메시지 커넥션 바인딩과
        # 다른 이유).
        #
        # [빌드 검증 중 실측으로 발견] 자동 생성된 트랜스폼을 통째로
        # `object_` 밑으로 옮기면(`cmds.parent(transform, object_)`)
        # 셰이프와 `object_` 사이에 항등(identity) 트랜스폼이 하나 더
        # 끼는 중간 계층이 생긴다 -- 셰이프의 직속 부모가 `object_`가 아니라
        # 그 중간 트랜스폼이 된다. 이 태스크의 계약(및 그것을 고정하는
        # tests/maya/test_lidar_menu.py)은 "LiDAR 셰이프의 부모가 곧
        # 클릭한 오브젝트 자신"이라는 더 강한 형태를 요구한다. 그래서
        # `-shape -relative`로 **셰이프만** `object_` 밑으로 옮긴다(다른
        # 셰이프에 흔히 쓰는 "인스턴스 셰이프 추가" 관용구와 같다) --
        # 그러면 원래 자동 생성된 트랜스폼은 셰이프를 잃고 빈 채로 남으므로
        # 곧바로 지워서 씬에 쓸모없는 트랜스폼이 남지 않게 한다.
        #
        # 그리고 `cmds.parent()`가 노드를 옮기고 나면 옮기기 **전의** 풀 DAG
        # 경로는 더 이상 유효하지 않다. 옮기기 전에 구해 둔 풀 경로를 그대로
        # 다시 `cmds.ls(..., long=True)`에 넣으면 그 경로는 이미 존재하지
        # 않는 노드를 가리키므로 빈 리스트가 돌아와 `[0]`에서 IndexError가
        # 난다(실측 확인). `cmds.parent()`가 돌려주는 짧은 이름과, 옮긴
        # 곳의 부모가 이미 확정돼 있다는 사실(=`object_`)을 조합해 모호하지
        # 않은 새 풀 경로를 직접 구성한다.
        lidarParents = cmds.listRelatives(lidar, parent=True, fullPath=True) or []
        if lidarParents:
            lidarAutoTransform = lidarParents[0]
            newShortName = cmds.parent(lidar, object_, relative=True, shape=True)[0]
            lidar = object_ + "|" + newShortName
            if cmds.objExists(lidarAutoTransform):
                cmds.delete(lidarAutoTransform)
            lidarAutoTransform = None

        # [최종 리뷰 C-1] 이 생성 경로에 한해 rangeMin을 0으로 내린다.
        #
        # maroLidar의 클래스 기본값 rangeMin은 0.1 **미터**다(MaroLidarNode.cpp).
        # 씬의 기본 선형 단위는 센티미터라 mayaPerMeter = 100이고, 따라서
        # scanLidarNode()가 Embree에 넘기는 tnear는 10 Maya 단위가 된다
        # (MaroLidarScan.cpp의 rangeMinMaya 변환). 그런데 이 마킹메뉴 경로가
        # 만드는 배치는 센서 원점과 타겟 사이 거리가 **항상 그보다 훨씬
        # 짧다**:
        #
        #   * 메쉬 케이스 -- 클릭한 메쉬 자신이 targetMeshes[0]가 되고, LiDAR
        #     셰이프는 그 메쉬의 트랜스폼에 그대로 물린다. 즉 센서 원점이
        #     메쉬의 피벗이다. 기본 polyCube는 반폭이 1이라 모든 레이가
        #     ~1 단위에서 맞는다.
        #   * placeholder 케이스 -- 반지름 1짜리 구를 object_의 기존 bbox
        #     상단에 놓는데, 그 시점의 bbox는 이미 물려 있는 LiDAR 로케이터
        #     자신의 기본 [-1,1]^3다. 결국 구 표면이 0~2 단위 사이에 온다.
        #
        # 둘 다 10 단위 tnear 안쪽이라, 고치지 않으면 **갓 만든 LiDAR는 기본
        # 설정으로 단 한 점도 못 맞힌다**. tests/maya/test_lidar_commands.py가
        # 이미 같은 함정을 독립적으로 만나 rangeMin = 0.0으로 우회해 두었지만
        # (그 파일의 주석 참고) 그 발견이 사용자 경로로 옮겨온 적은 없었다.
        #
        # 노드 자신의 클래스 기본값(0.1)은 일부러 그대로 둔다 -- 타겟을
        # 의도적으로 멀리 배치하는 스크립트/프로그램 경로에서는 근거리
        # 클리핑이 있는 쪽이 실제 LiDAR에 가깝고 합리적인 기본값이다.
        # 문제인 것은 "거리 0에 자동 탑재하는" 이 마킹메뉴 경로뿐이다.
        cmds.setAttr(lidar + ".rangeMin", 0.0)

        pointCloud = cmds.createNode("maroPointCloud")
        pointCloud = cmds.ls(pointCloud, long=True)[0]
        pointCloudParents = cmds.listRelatives(pointCloud, parent=True, fullPath=True) or []
        if pointCloudParents:
            pointCloudAutoTransform = pointCloudParents[0]
            proxyGroup = maroRosProxy.ensureProxyGroup()
            newShortName = cmds.parent(pointCloud, proxyGroup, relative=True, shape=True)[0]
            pointCloud = proxyGroup + "|" + newShortName
            if cmds.objExists(pointCloudAutoTransform):
                cmds.delete(pointCloudAutoTransform)
            pointCloudAutoTransform = None
        cmds.connectAttr(lidar + ".message", pointCloud + ".sourceLidar")

        if _hasMeshShape(object_):
            targetMesh = object_
        else:
            targetMesh = placeholderSphere = _createPlaceholderTargetMesh(object_)
        cmds.connectAttr(targetMesh + ".message", lidar + ".targetMeshes[0]")
    except Exception as exc:  # noqa: BLE001 -- 마킹 메뉴 콜백 경계
        cmds.warning("Maro: failed to create a LiDAR on '{}': {}".format(object_, exc))
        # 항상 "이 함수가 만든 셰이프/트랜스폼 자체"만 지운다 -- 실패 시점에
        # lidar/pointCloud가 이미 object_/프록시 그룹 밑으로 옮겨져 있을 수
        # 있으므로, "지금 lidar의 부모가 누구인지"를 다시 물어서 그 부모를
        # 지우면 object_(사용자가 우클릭한 오브젝트)나 공유 프록시 그룹까지
        # 지워 버리는 사고가 난다. 셰이프 자신을 지우는 것과, 아직 셰이프를
        # 옮기기 전 단계에서 실패했을 때를 위해 자동 생성 트랜스폼을 따로
        # 지우는 것은 서로 배타적이지 않다(성공적으로 옮긴 뒤에는
        # lidarAutoTransform/pointCloudAutoTransform을 이미 None으로
        # 되돌려 뒀으므로 이중 삭제 시도가 없다).
        # [I-2] placeholderSphere는 생성 직후 cmds.select()로 선택돼 있을 수
        # 있다. 지워지는 노드는 Maya가 알아서 선택 목록에서 걷어내므로(축
        # 생성 실패 롤백에서도 별도 처리 없이 같은 방식에 기대는 것과 동일)
        # 따로 선택을 손대지 않는다.
        if placeholderSphere and cmds.objExists(placeholderSphere):
            cmds.delete(placeholderSphere)
        if lidar and cmds.objExists(lidar):
            cmds.delete(lidar)
        if lidarAutoTransform and cmds.objExists(lidarAutoTransform):
            cmds.delete(lidarAutoTransform)
        if pointCloud and cmds.objExists(pointCloud):
            cmds.delete(pointCloud)
        if pointCloudAutoTransform and cmds.objExists(pointCloudAutoTransform):
            cmds.delete(pointCloudAutoTransform)
        return
    finally:
        cmds.undoInfo(closeChunk=True)

    maroLidarPanel.openLidarPanel(lidar)
