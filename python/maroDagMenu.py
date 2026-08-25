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

# 원본 dagMenuProc를 보존할 이름. 우리 래퍼가 가장 먼저 부른다.
_BACKUP_PROC_NAME = "maroDagMenuProcOriginal"

# MEL -> Python으로 인자를 넘기는 전역 변수 이름. 생성한 MEL 소스 안에
# 사용자 데이터(메뉴 이름/DAG 경로)를 문자열로 끼워 넣지 않기 위한 것이다 --
# 따옴표/이스케이프 문제를 만들 여지 자체를 없앤다.
_MEL_PARENT_VAR = "gMaroDagMenuParent"
_MEL_OBJECT_VAR = "gMaroDagMenuObject"

# whatIs가 MEL 스크립트를 보고할 때 쓰는 두 접두사. 위 모듈 독스트링 참고 --
# 소스 전/후로 문구가 다르다.
_WHATIS_PREFIXES = ("Mel procedure found in: ", "Script found in: ")

# `global proc dagMenuProc(...)` 선언 헤더. 시그니처가 Maya 버전에 따라
# 달라져도 걸리도록 인자 목록은 보지 않는다.
#
# **바이트 패턴이다.** 원본 .mel을 디코드해서 다루면(errors="replace")
# UTF-8이 아닌 바이트가 섞인 지역화 설치본에서 문자열 리터럴이 조용히
# U+FFFD로 바뀐 사본을 source하게 된다 -- 그 사본이 곧 세션 전체의 우클릭
# 메뉴가 되므로 허용할 수 없는 종류의 손상이다. 바이트로 읽고 바이트로
# 치환해서 헤더 한 줄 말고는 원본과 바이트 단위로 동일한 복사본을 만든다.
_PROC_HEADER_RE = re.compile(rb"^([ \t]*global[ \t]+proc[ \t]+)dagMenuProc(?=[ \t]*\()",
                             re.MULTILINE)

_INSTALLED = False
_ORIGINAL_SOURCE_FILE = None
_BACKUP_TEMP_FILE = None


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
    global _INSTALLED, _ORIGINAL_SOURCE_FILE, _BACKUP_TEMP_FILE
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

    _ORIGINAL_SOURCE_FILE = sourceFile
    # 임시 파일은 세션 동안 남겨 두고 uninstall에서 지운다. MEL은 source
    # 시점에 파일 전체를 메모리로 컴파일하므로 곧바로 지워도 동작하지만,
    # 파일 스코프 지역 프로시저(setUpArtisanSkinContext 등)의 해소가 파일
    # 경로에 전혀 의존하지 않는다는 것까지 보장할 근거가 없어서 굳이
    # 모험하지 않는다. 비용은 세션당 임시 파일 하나다.
    _BACKUP_TEMP_FILE = tempPath
    _INSTALLED = True
    return True


def uninstall():
    """플러그인 언로드 시 한 번 부른다. 멱등.

    원본 .mel을 다시 source해서 Maya 본래 정의를 그대로 되돌린다 -- 얇은
    래퍼를 남기는 것보다 깨끗하다(whatIs도 원래 경로를 가리키게 된다).
    다시 source하지 못하면 백업을 그대로 호출하는 래퍼로 대신한다.
    """
    global _INSTALLED, _BACKUP_TEMP_FILE
    if not _INSTALLED:
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

    if _BACKUP_TEMP_FILE:
        _removeQuietly(_BACKUP_TEMP_FILE)
        _BACKUP_TEMP_FILE = None
    _INSTALLED = False


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
        object_ = _melGlobalString(_MEL_OBJECT_VAR)
        if not parentMenu or not cmds.popupMenu(parentMenu, exists=True):
            return
        if not object_:
            # buildObjectMenuItemsNow.mel은 커서 아래에 아무것도 없으면 빈
            # 문자열을 넘긴다. Maya 자신의 dagMenuProc와 같은 방식으로
            # 선택/하이라이트 목록에서 대상을 고른다.
            object_ = _leadObject()
        cmds.menuItem(parent=parentMenu, label=MENU_ITEM_LABEL,
                      command=lambda *_args: _onMenuItemClicked(object_))
    except Exception as exc:  # pragma: no cover - UI 경로
        cmds.warning("Maro: failed to add the '{}' menu item: {}"
                     .format(MENU_ITEM_LABEL, exc))


def _leadObject():
    for kwargs in ({"selection": True}, {"hilite": True}):
        found = cmds.ls(tail=1, type=("transform", "shape"), **kwargs) or []
        if found:
            return found[0]
    return ""


def _onMenuItemClicked(object_):
    # Task 8이 이 자리를 openSingleObjectNodeEditor(object_) 호출로 바꾼다.
    print("Maro node editor clicked for: {}".format(object_))
