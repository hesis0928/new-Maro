"""maroDagMenu의 dagMenuProc 체이닝 계약을 배치 모드에서 고정한다.

이 파일이 무엇을 **못** 하는지 먼저 분명히 해 둔다. 배치 mayapy에는 실제
팝업 메뉴가 없으므로 "우클릭했을 때 마킹 메뉴에 항목이 실제로 보이는가"는
여기서 확인할 수 없다 -- 그건 대화형 Maya에서 사람이 봐야 한다
(test_main_menu.py / test_main_window.py와 같은 한계).

여기서 확인할 수 있는 것 -- 그리고 이 태스크에서 가장 위험한 부분이 바로
이것이다: **원본 dagMenuProc의 항목들이 보존되는가.** dagMenuProc는
프로세스 전역 프로시저 하나뿐이라, 체이닝이 잘못되면 이 플러그인만이 아니라
Maya 자신과 다른 모든 플러그인의 오브젝트 우클릭 메뉴가 조용히 사라진다.
그 계약은 UI 없이도 값으로 고정할 수 있다:

  - 플러그인을 로드하면 원본이 `maroDagMenuProcOriginal`로 보존된다.
  - 우리 래퍼가 **원본을 먼저** 부르고 **그 다음에** 우리 항목을 붙인다
    (호출 순서와 인자를 스텁으로 기록해 확인한다).
  - 인자(팝업 메뉴 이름, DAG 경로)가 MEL -> Python으로 그대로 건너간다.
  - 언로드하면 dagMenuProc가 Maya 원본 정의로 되돌아간다(whatIs가 다시
    Maya의 .mel 파일을 가리킨다).
  - 백업 복사본이 지역화 리소스 키를 망가뜨리지 않는다(`uiRes` 실측).

배치 모드에서 dagMenuProc를 **직접 실행**할 수는 없다는 것도 기록해 둔다:
Maya 2026의 dagMenuProc는 2589행에서 `nexCtx`(모델링 툴킷 커맨드, GUI에서만
로드된다)를 부르므로 배치에서는 원본이든 우리 체인이든 똑같이
"Cannot find procedure nexCtx"로 실패한다. 그래서 아래 순서 검증은 백업
프로시저를 기록용 스텁으로 갈아 끼운 뒤에 한다 -- 검증 대상은 원본 본문이
아니라 **우리 래퍼의 체이닝 구조**이기 때문이다.
"""
import os
import sys
import tempfile

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402
import maya.mel as mel  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
pluginName = os.path.splitext(os.path.basename(plugin))[0]
pluginDir = os.path.dirname(plugin)

stagedModule = os.path.join(pluginDir, "maroDagMenu.py")
assert os.path.isfile(stagedModule), (
    f"maroDagMenu.py must be staged next to the plug-in, not found at {stagedModule}"
)
print("module staged next to the plug-in OK")

# 로드 전 상태. dagMenuProc.mel은 첫 우클릭 때 지연 소스되므로 아직
# 소스되지 않았고, whatIs는 "Mel procedure found in: "가 아니라
# "Script found in: "으로 보고한다. 이 사실이 maroDagMenu._originalProcSourceFile()
# 이 두 접두사를 모두 받아야 하는 이유이므로 값으로 고정해 둔다 --
# 한쪽만 보는 구현은 경로를 못 찾고 원본 보존에 실패한다.
pristine = mel.eval('whatIs "dagMenuProc"')
assert pristine.startswith("Script found in: "), (
    f"expected an unsourced dagMenuProc to be reported as 'Script found in: ', "
    f"got {pristine!r} -- maroDagMenu._WHATIS_PREFIXES needs re-checking"
)
assert mel.eval('exists("maroDagMenuProcOriginal")') == 0
print(f"pristine whatIs OK: {pristine!r}")

cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

import maroDagMenu  # noqa: E402  (플러그인 디렉터리가 sys.path에 들어간 뒤)

assert "maroDagMenu" in sys.modules
assert maroDagMenu._INSTALLED is True, "initializePlugin should have installed the chain"
assert mel.eval('exists("maroDagMenuProcOriginal")') == 1, (
    "the original dagMenuProc must be preserved under a backup name"
)
assert mel.eval('exists("dagMenuProc")') == 1
print("install() ran from initializePlugin OK")

# 백업 복사본이 선언 헤더 한 줄만 바꿨는가. 파일 전체를 무조건 치환하면
# uiRes("m_dagMenuProc.*") 리소스 키 200여 개가 함께 망가진다.
with open(maroDagMenu._BACKUP_TEMP_FILE, "rb") as f:
    backupSrc = f.read()
assert backupSrc.count(b"global proc maroDagMenuProcOriginal(") == 1
assert backupSrc.count(b"global proc dagMenuProc(") == 0
assert b'uiRes("m_dagMenuProc.kSelect")' in backupSrc, (
    "localisation resource keys must survive the rename"
)
assert b"m_maroDagMenuProcOriginal" not in backupSrc
# 그리고 헤더 한 줄 말고는 원본과 **바이트 단위로** 같아야 한다. 디코딩을
# 거치면 UTF-8이 아닌 바이트가 조용히 U+FFFD로 바뀔 수 있는데, 그 사본이
# 곧 세션 전체의 우클릭 메뉴가 된다.
with open(maroDagMenu._ORIGINAL_SOURCE_FILE, "rb") as f:
    originalSrc = f.read()
assert (backupSrc.replace(b"global proc maroDagMenuProcOriginal(",
                          b"global proc dagMenuProc(") == originalSrc), (
    "the backup copy must be byte-identical to Maya's file apart from the "
    "renamed declaration header"
)
# 그리고 그 키가 실제로 해소되는지 Maya에게 직접 물어본다.
assert mel.eval('uiRes("m_dagMenuProc.kSelect")') not in ("", None)
# 같은 파일의 다른 전역 프로시저들이 원래 이름 그대로 살아 있는가.
for proc in ("createSelectMenuItems", "showSG", "canMakeLive",
             "dagMenuProc_selectionMask_melToUI"):
    assert mel.eval(f'exists("{proc}")') == 1, f"{proc} must keep its real name"
print("backup copy renames exactly one declaration header OK")

# --- 핵심: 래퍼가 원본을 먼저 부르고 그 다음에 우리 항목을 붙이는가 ------
#
# 백업 프로시저를 기록용 스텁으로 갈아 끼운다(배치에서는 진짜 원본 본문이
# nexCtx 때문에 돌지 않는다 -- 파일 독스트링 참고). 우리 파이썬 훅도
# 기록용으로 바꾼다. 그러면 dagMenuProc 한 번 호출로 순서와 인자를 모두
# 관찰할 수 있다.
calls = []
mel.eval('''
    global proc maroDagMenuProcOriginal(string $parent, string $object)
    {
        python("import maroDagMenu; maroDagMenu._testRecordOriginal()");
    }
''')


def _recordOriginal():
    calls.append(("original",
                  maroDagMenu._melGlobalString(maroDagMenu._MEL_PARENT_VAR),
                  maroDagMenu._melGlobalString(maroDagMenu._MEL_OBJECT_VAR)))


def _recordOurs():
    calls.append(("ours",
                  maroDagMenu._melGlobalString(maroDagMenu._MEL_PARENT_VAR),
                  maroDagMenu._melGlobalString(maroDagMenu._MEL_OBJECT_VAR)))


maroDagMenu._testRecordOriginal = _recordOriginal
realAddMenuItem = maroDagMenu._addMenuItem
maroDagMenu._addMenuItem = _recordOurs

# 스텁 원본은 인자를 못 보므로(전역 변수는 우리 래퍼가 나중에 채운다)
# 원본 호출 시점에는 아직 이전 값이 남아 있을 수 있다. 순서만 본다.
probes = ["|group1|pCube1", "pCube1", "ns:rig|ns:jointA", ""]
for probe in probes:
    calls[:] = []
    mel.eval(f'dagMenuProc("maroProbeMenu", "{probe}")')
    order = [c[0] for c in calls]
    assert order == ["original", "ours"], (
        f"the wrapper must call the preserved original FIRST and add our item "
        f"second; got {order!r} for object {probe!r}"
    )
    # 우리 훅이 받은 인자가 MEL이 받은 것과 같은가 (따옴표/이스케이프 없이
    # MEL 전역 변수로 건너간다).
    assert calls[1][1] == "maroProbeMenu", calls
    assert calls[1][2] == probe, (
        f"DAG path must round-trip MEL -> Python unchanged; "
        f"sent {probe!r} got {calls[1][2]!r}"
    )
print(f"chain order + argument round-trip OK for {probes!r}")

maroDagMenu._addMenuItem = realAddMenuItem

# _addMenuItem은 절대 예외를 밖으로 내보내면 안 된다 -- MEL로 새어 나가면
# 우클릭 메뉴 생성 전체가 에러로 끝난다. 배치에는 팝업 메뉴가 없으므로
# 아래 호출은 popupMenu 가드에 걸려 조용히 아무것도 안 해야 한다.
mel.eval('global string $gMaroDagMenuParent; $gMaroDagMenuParent = "noSuchMenu";')
maroDagMenu._addMenuItem()
print("_addMenuItem is a safe no-op without a real popup menu OK")

# 커서 아래에 아무것도 없을 때(buildObjectMenuItemsNow.mel이 빈 문자열을
# 넘기는 경우) 쓰는 대체 경로. Maya 자신의 dagMenuProc와 같은 질의를 한다.
cube = cmds.polyCube(name="maroDagMenuProbeCube")[0]
cmds.select(cube, replace=True)
assert maroDagMenu._leadObject() != "", "should fall back to the selection"
cmds.select(clear=True)
assert maroDagMenu._leadObject() == "", "empty selection should give an empty string"
print("_leadObject fallback OK")

# 멱등성.
assert maroDagMenu.install() is True
assert mel.eval('exists("maroDagMenuProcOriginal")') == 1
print("install() idempotent OK")

tempCopy = maroDagMenu._BACKUP_TEMP_FILE
assert os.path.isfile(tempCopy)

# --- 언로드하면 Maya 원본으로 되돌아가는가 --------------------------------
cmds.unloadPlugin(pluginName)
assert maroDagMenu._INSTALLED is False, "uninitializePlugin should have uninstalled"
restored = mel.eval('whatIs "dagMenuProc"')
assert restored.startswith("Mel procedure found in: "), restored
assert restored.replace("\\", "/").endswith("others/dagMenuProc.mel"), (
    f"dagMenuProc must point back at Maya's own file after unload, got {restored!r}"
)
assert not os.path.exists(tempCopy), "the temp backup copy must be cleaned up"
# 원본과 함께 다시 소스된 다른 전역 프로시저들도 멀쩡한가.
assert mel.eval('exists("createSelectMenuItems")') == 1
print(f"unload restored Maya's own dagMenuProc OK: {restored!r}")

maroDagMenu.uninstall()  # 멱등
print("uninstall() idempotent OK")

# --- 로드/언로드를 다시 한 번 (세션 안에서 모듈 상태가 남아 있는 경우) ----
cmds.loadPlugin(plugin)
assert maroDagMenu._INSTALLED is True
assert mel.eval('exists("maroDagMenuProcOriginal")') == 1
cmds.unloadPlugin(pluginName)
assert maroDagMenu._INSTALLED is False
assert mel.eval('whatIs "dagMenuProc"').startswith("Mel procedure found in: ")
print("reload cycle OK")

# --- 뷰큐브 등 "노드 컨텍스트 메뉴가 아닌" 메뉴에 새지 않는가 --------------
#
# Maya의 dagMenuProc에는 일반 오브젝트 메뉴를 만들지 않고 곧바로 return하는
# 경로가 셋 있다(2586행 traversal MM, 2591행 모델링 툴킷 RMB-complete,
# 2602-2605행 뷰큐브). 그중 뷰큐브는 `$object`가 노드 이름이 아니라 센티널
# 문자열 "CubeCompass"이고, 기본 뷰포트마다 있으므로 아주 흔하다. 원본이
# 무엇을 했는지와 무관하게 항목을 붙이면 우리 항목이 뷰큐브 메뉴에 낀다.
cube = cmds.polyCube(name="maroDagMenuGuardCube")[0]


def _setMelObject(value):
    mel.eval(f'global string $gMaroDagMenuObject; $gMaroDagMenuObject = "{value}";')


_setMelObject("CubeCompass")
assert maroDagMenu._resolveObject() == "", (
    "the ViewCube sentinel is not a DAG object -- our item must not be added"
)
for sentinel in ("CubeCompass", "notANode", "|no|such|path"):
    _setMelObject(sentinel)
    assert maroDagMenu._resolveObject() == "", sentinel

# ...그리고 진짜 DAG 오브젝트에서는 여전히 붙어야 한다(가드가 정상 경로까지
# 막아 버리면 기능 자체가 사라진다).
cmds.select(clear=True)
_setMelObject(cube)
assert maroDagMenu._resolveObject() == cube, "a real transform must still pass the guard"
shape = cmds.listRelatives(cube, shapes=True, fullPath=True)[0]
_setMelObject(shape)
assert maroDagMenu._resolveObject() == shape, "a real shape must still pass the guard"
_setMelObject(cmds.ls(cube, long=True)[0])
assert maroDagMenu._resolveObject() == cmds.ls(cube, long=True)[0], (
    "a full DAG path must still pass the guard"
)
# 빈 문자열 -> 선택 기반 대체 경로도 가드를 통과해야 한다.
cmds.select(cube, replace=True)
_setMelObject("")
assert maroDagMenu._resolveObject() != "", (
    "the empty-$object selection fallback must still produce our item"
)
cmds.select(clear=True)
_setMelObject("")
assert maroDagMenu._resolveObject() == ""
# 배치에는 traversal MM도 모델링 툴킷도 없으므로 억제되지 않아야 한다
# (억제 판정 자체가 예외를 내지 않는다는 확인도 겸한다).
assert maroDagMenu._nativeMenuSuppressed() is False
cmds.delete(cube)
print("non-DAG sentinels (ViewCube) rejected, real DAG objects still accepted OK")

# --- 시그니처가 다르면 매치되지 않는가 -------------------------------------
#
# 헤더 정규식이 인자 목록을 보지 않으면, 시그니처가 다른 Maya에서도 매치되어
# 인자 두 개짜리 래퍼를 설치한다. 그러면 Maya의 실제 호출자가 다른 인자 수로
# 부르므로 오브젝트를 우클릭할 때마다 MEL "wrong number of arguments" 에러가
# 세션 내내 난다. 예상한 형태가 아니면 매치되지 않고 설치를 포기해야 한다.
with open(maroDagMenu._ORIGINAL_SOURCE_FILE, "rb") as f:
    realSrc = f.read()
assert len(maroDagMenu._PROC_HEADER_RE.findall(realSrc)) == 1, (
    "the tightened header regex must still match Maya's real dagMenuProc.mel "
    "exactly once -- this Maya's signature IS (string $parent, string $object)"
)
assert maroDagMenu._PROC_HEADER_RE.search(
    b"global proc dagMenuProc(string  $a,\tstring $b)") is not None
for bad in (b"global proc dagMenuProc(string $parent, string $object, int $extra)",
            b"global proc dagMenuProc(string $parent)",
            b"global proc dagMenuProc()",
            b"global proc dagMenuProc(string $parent, int $object)",
            b"global proc int dagMenuProc(string $parent, string $object)"):
    assert maroDagMenu._PROC_HEADER_RE.search(bad) is None, (
        f"an unexpected signature must NOT match: {bad!r}"
    )
print("header regex matches Maya's real signature only OK")


# --- 설치 포기 경로: 실패하면 아무것도 바꾸지 않는가 -----------------------
#
# 이 모듈의 핵심 안전 보장이다. 원본을 확실히 보존하지 못하면 install()은
# False를 돌려주고 dagMenuProc를 **건드리지 않는다**. 잘못된 whatIs 문자열
# 하나와 세션 전체의 우클릭 메뉴 파괴 사이에 서 있는 것이 이 분기라서,
# 다른 모든 동작과 같은 수준으로 값으로 고정해 둔다.
assert maroDagMenu._INSTALLED is False
before = mel.eval('whatIs "dagMenuProc"')
realSourceFile = maroDagMenu._originalProcSourceFile


def _assertDeclined(label):
    assert maroDagMenu.install() is False, f"install() must decline when {label}"
    assert maroDagMenu._INSTALLED is False, f"install() must not flip _INSTALLED when {label}"
    after = mel.eval('whatIs "dagMenuProc"')
    assert after == before, (
        f"install() must leave dagMenuProc untouched when {label}; "
        f"whatIs went {before!r} -> {after!r}"
    )
    assert maroDagMenu._BACKUP_TEMP_FILE is None, (
        f"install() must not leave a backup temp file behind when {label}"
    )


# (a) 원본 .mel 경로를 확인할 수 없다 (whatIs가 모르는 문구를 돌려준 경우 등).
maroDagMenu._originalProcSourceFile = lambda: None
try:
    _assertDeclined("the original proc's source file cannot be verified")
finally:
    maroDagMenu._originalProcSourceFile = realSourceFile

# (b) 경로는 있는데 그 파일이 없다.
maroDagMenu._originalProcSourceFile = lambda: os.path.join(
    pluginDir, "noSuchDagMenuProc.mel")
try:
    _assertDeclined("the reported source file does not exist")
finally:
    maroDagMenu._originalProcSourceFile = realSourceFile

# (c) 파일은 있는데 예상한 선언 헤더가 정확히 한 번 나오지 않는다 -- 시그니처가
#     다른 경우가 여기 포함된다(위 정규식 검증과 짝을 이룬다).
for label, body in (
        ("the declaration header is missing",
         b"global proc somethingElse(string $a, string $b) {}\n"),
        ("the declaration has an unexpected signature",
         b"global proc dagMenuProc(string $parent, string $object, int $x) {}\n"),
        ("the declaration header appears more than once",
         b"global proc dagMenuProc(string $a, string $b) {}\n"
         b"global proc dagMenuProc(string $a, string $b) {}\n")):
    fd, fakePath = tempfile.mkstemp(suffix=".mel", prefix="maroDagMenuFake_")
    with os.fdopen(fd, "wb") as f:
        f.write(body)
    assert maroDagMenu._writeBackupCopy(fakePath) is None, label
    maroDagMenu._originalProcSourceFile = lambda p=fakePath: p
    try:
        _assertDeclined(label)
    finally:
        maroDagMenu._originalProcSourceFile = realSourceFile
        os.remove(fakePath)

# 포기 경로를 다 지나온 뒤에도 정상 설치는 여전히 된다.
assert maroDagMenu.install() is True
assert mel.eval('exists("maroDagMenuProcOriginal")') == 1
maroDagMenu.uninstall()
print("install() declines and changes nothing when the original cannot be preserved OK")

# --- [최종 리뷰 I-5] 남의 체인을 덮어쓰지 않는가 ---------------------------
#
# 우리가 로드된 **뒤에** 다른 툴이 우리 래퍼 위에 자기 dagMenuProc를 얹은
# 경우, 우리 uninstall()이 Maya 원본 .mel을 무조건 다시 source하면 그 툴의
# 체인까지 함께 날아간다 -- install() 쪽에서 그토록 조심하는 세션 전역 파괴를
# 언로드 쪽에서 저지르는 것과 같다. 그러지 않는지를 값으로 고정한다.
mayaDagMenuProcMel = maroDagMenu._ORIGINAL_SOURCE_FILE
assert os.path.isfile(mayaDagMenuProcMel), mayaDagMenuProcMel

assert maroDagMenu.install() is True
assert maroDagMenu._melGlobalString(maroDagMenu._MEL_SENTINEL_VAR) == \
    maroDagMenu._SENTINEL_VALUE, "install() must stamp its sentinel"
assert maroDagMenu._wrapperStillOurs() is True

# 다른 툴이 파일에서 자기 dagMenuProc를 source한 상황을 만든다(가장 흔하고
# 가장 확실히 잡히는 형태 -- whatIs가 경로를 가리키게 바뀐다).
fd, foreignPath = tempfile.mkstemp(suffix=".mel", prefix="maroForeignChain_")
with os.fdopen(fd, "wb") as f:
    f.write(b'global proc maroForeignMarker() { }\n'
            b'global proc dagMenuProc(string $parent, string $object)\n'
            b'{\n'
            b'    maroDagMenuProcOriginal($parent, $object);\n'
            b'}\n')
mel.eval('source "{}"'.format(foreignPath.replace("\\", "/")))
foreignWhatIs = mel.eval('whatIs "dagMenuProc"')
assert foreignWhatIs != maroDagMenu._INSTALLED_WHATIS, foreignWhatIs
assert maroDagMenu._wrapperStillOurs() is False, (
    "a dagMenuProc redefined from someone else's file must not look like ours"
)

maroDagMenu.uninstall()
assert mel.eval('whatIs "dagMenuProc"') == foreignWhatIs, (
    "uninstall() must leave the newer chain alone instead of re-sourcing Maya's "
    "own dagMenuProc.mel over the top of it"
)
assert maroDagMenu._INSTALLED is False, "uninstall() must still reset its own state"
assert maroDagMenu._BACKUP_TEMP_FILE is None, (
    "uninstall() must still clean up its temp file even when it declines to restore"
)
print("uninstall() declines to clobber a chain installed after us OK")

# 남의 체인을 치우고 Maya 원본으로 되돌린다 -- 이 테스트가 만든 상황이므로
# 이 테스트가 정리한다(그대로 두면 다음 install()이 우리 임시 파일이 아니라
# 이 가짜 파일을 "원본"으로 삼는다).
mel.eval('source "{}"'.format(mayaDagMenuProcMel.replace("\\", "/")))
os.remove(foreignPath)

# 그 상태에서 다시 설치/해제하면 정상 경로로 돌아온다(위 검사가 모듈을
# 영구히 "설치 불가" 상태로 만들지 않는다는 확인).
assert maroDagMenu.install() is True
assert maroDagMenu._wrapperStillOurs() is True
maroDagMenu.uninstall()
assert mel.eval('whatIs "dagMenuProc"').startswith("Mel procedure found in: ")
assert maroDagMenu._melGlobalString(maroDagMenu._MEL_SENTINEL_VAR) == "", (
    "uninstall() must clear its sentinel so a later check cannot misread it"
)
print("install()/uninstall() still work normally after the decline path OK")

# --- [2026-09-06 실측] idle 워치독: MayaUSD/UFE 쪽이 실제 우클릭 메뉴
# 빌드 도중 dagMenuProc를 원본으로 되돌리는 것이 확인됐다(합성 호출로는
# 재현 안 되고 실제 UI 우클릭에서만 재현 -- 우리 쪽 결함이 아니라 외부
# 동작). dagMenuProc 자체가 그 순간 우리 체인에서 빠지므로 감지/복구
# 로직은 체인 바깥(idle scriptJob)에 있어야 한다. ---------------------

# install()이 워치독을 시작한다(배치에서는 scriptJob이 아무 것도 안
# 만들고 None을 준다 -- maroRosProxy.start()와 동일 실측, tests/maya/
# test_ros_proxy_sync.py:186 참고).
assert maroDagMenu.install() is True
assert maroDagMenu._WATCHDOG_JOB_ID is None
print("install() starts the watchdog (no-op scriptJob id in batch) OK")

# 래퍼가 멀쩡할 때: 워치독 틱은 아무것도 안 바꾼다.
beforeWhatIs = mel.eval('whatIs "dagMenuProc"')
maroDagMenu._watchdogTick()
assert maroDagMenu._INSTALLED is True
assert mel.eval('whatIs "dagMenuProc"') == beforeWhatIs, (
    "a no-op tick must not touch a healthy wrapper"
)
print("_watchdogTick() is a no-op while the wrapper is intact OK")

# 래퍼가 외부에 의해 되돌아간 상황을 재현한다(위 I-5 테스트와 같은
# 수법 -- Maya 원본 .mel을 그대로 다시 source해서 순수 네이티브 상태로
# 만든다. 이번엔 "남의 체인"이 아니라 "완전히 원본으로 리셋된" 경우를
# 재현하는 것이 목적이라, 실측으로 확인된 실제 증상과 더 가깝다).
assert maroDagMenu._wrapperStillOurs() is True
mel.eval('source "{}"'.format(mayaDagMenuProcMel.replace("\\", "/")))
clobberedWhatIs = mel.eval('whatIs "dagMenuProc"')
assert clobberedWhatIs != beforeWhatIs, "the simulated clobbering must actually change dagMenuProc"
assert maroDagMenu._wrapperStillOurs() is False

# 워치독 틱이 스스로 재설치해야 한다.
maroDagMenu._watchdogTick()
assert maroDagMenu._INSTALLED is True, "the watchdog must repair a clobbered wrapper"
assert maroDagMenu._wrapperStillOurs() is True
assert mel.eval('whatIs "dagMenuProc"') != clobberedWhatIs, (
    "after repair, dagMenuProc must be our wrapper again, not the native proc"
)
print("_watchdogTick() detects and repairs an externally-clobbered dagMenuProc OK")

# 틱 자체가 예외를 내지 않아야 한다(idle 콜백 경계 -- maroRosProxy._onIdle()
# 과 같은 규율). 재설치가 원천적으로 불가능한 상태를 만들어서 확인한다.
realSourceFile = maroDagMenu._originalProcSourceFile
mel.eval('source "{}"'.format(mayaDagMenuProcMel.replace("\\", "/")))  # 다시 깨뜨림
maroDagMenu._originalProcSourceFile = lambda: None
try:
    maroDagMenu._watchdogTick()  # 예외가 새어 나오면 이 줄에서 테스트가 죽는다
finally:
    maroDagMenu._originalProcSourceFile = realSourceFile
assert maroDagMenu._INSTALLED is False, (
    "a tick that fails to repair must leave _INSTALLED False so the next tick retries"
)
print("_watchdogTick() never raises even when repair itself fails OK")

# 정상 재설치 + uninstall()이 워치독을 멈춘다.
assert maroDagMenu.install() is True
maroDagMenu.uninstall()
assert maroDagMenu._WATCHDOG_JOB_ID is None, "uninstall() must stop the watchdog"
print("uninstall() stops the watchdog OK")

print("test_dag_menu OK")
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
