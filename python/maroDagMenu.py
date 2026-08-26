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
        if not parentMenu or not cmds.popupMenu(parentMenu, exists=True):
            return
        if _nativeMenuSuppressed():
            return
        object_ = _resolveObject()
        if not object_:
            return
        cmds.menuItem(parent=parentMenu, label=MENU_ITEM_LABEL,
                      command=lambda *_args: _onMenuItemClicked(object_))
    except Exception as exc:  # pragma: no cover - UI 경로
        cmds.warning("Maro: failed to add the '{}' menu item: {}"
                     .format(MENU_ITEM_LABEL, exc))


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
            if cmds.objExists(axis):
                cmds.delete(axis)
            cmds.warning("Maro: failed to bind the new axis to '{}': {}"
                         .format(object_, exc))
    finally:
        cmds.undoInfo(closeChunk=True)

    if bindFailed:
        return

    maroSingleObjectNodeEditor.openSingleObjectNodeEditor(axis)
