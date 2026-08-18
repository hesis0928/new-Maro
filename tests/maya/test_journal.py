"""저널이 크래시를 건너 살아남는지, 그리고 다음 실행이 비정상 종료를
알아채는지 여러 프로세스로 확인한다.

왜 여러 프로세스인가: 저널의 존재 이유가 "프로세스가 죽어도 남는 것"이므로,
한 프로세스 안에서는 인메모리 상태와 구분되지 않는다. 크래시 세션들은 정상
종료 줄을 쓰기 **전에** 스스로를 끊는다 -- 감시자 입장에서 진짜 크래시와
구분되지 않는 신호이며, 컴퓨터를 죽이지 않고 만들 수 있다.

좀비 mayapy.exe 방지: subprocess.run(timeout=...)은 타임아웃 시 자식을
kill()하고 wait()까지 마친 뒤에야 예외를 던진다 -- 각 세션 호출을 그 경계
안에 두는 것만으로 무한 대기도, 죽은 자식이 남는 것도 막힌다.

리뷰 Finding (아직 아무도 신호가 실제로 동작하는 것을 본 적이 없다):
예전에는 이 파일이 비정상 세션을 딱 하나만 만들었다 -- crashAdjacency의
문턱(비정상 종료 2회, 그리고 그중 태그가 2회 이상)에는 절대 닿지 않는
구성이었다. 그래서 "패널이 임계값을 넘겼을 때 정확한 문장을 실제로
내놓는다"는 이 기능의 존재 이유 자체는 어디에서도 값으로 확인된 적이
없었다(hand-built CrashAdjacency 구조체를 쓰는 gtest, "비어 있다"만
확인하는 test_panel_commands.py). 아래 orchestrate()는 이제 같은 사이트
태그로 죽는 세션을 **두 번** 만들고, 세 번째 세션에서 maroJournalAbnormalSessions()
== 2와 maroDiagPanelDetail의 crashAdjacencyNote가 프레젠터가 2/2에 대해
만드는 바로 그 문장인지를 값으로 확인한다."""
import glob
import os
import subprocess
import sys

MAYAPY = sys.executable
THIS_FILE = os.path.abspath(__file__)
SESSION_TIMEOUT_SECONDS = 90

# 두 크래시 세션이 공유하는 사이트 태그. maroBindAxis가 non-transform 대상을
# 거부할 때 항상 이 태그로 에러를 낸다(MaroCommands.cpp) -- 손으로 지어낸
# 태그가 아니라 실제 진단 경로가 실제로 내는 값이다.
TARGET_TAG = "MaroBindAxisCommand.TargetNotTransform"

# PanelPresenter.cpp의 buildPanelDetail이 abnormalSessionCount==2,
# appearancesByTag[tag]==2일 때 그대로 조립하는 문장. 여기서 하드코딩하는
# 이유: 이 테스트가 확인하려는 것이 정확히 "저널에서 실제로 읽어 온 값이 이
# 문장을 만드는가"이므로, 프레젠터가 무엇을 만드는지 별도로 다시 계산하지
# 않고 그 계약(test_panel_presenter.cpp의
# ReportsTheObservedCountsAboveTheThreshold가 같은 형식을 고정한다)을 그대로
# 옮겨 적는다.
EXPECTED_NOTE = "지난 비정상 종료 2회 중 2회에서 이 진단이 마지막 순간에 있었습니다."


def run_session(label, env):
    try:
        completed = subprocess.run(
            [MAYAPY, THIS_FILE, f"--session={label}"],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=SESSION_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(
            f"session {label} did not finish within {SESSION_TIMEOUT_SECONDS}s "
            f"and was killed -- output so far:\n{exc.output or ''}"
        )
    return completed.returncode, completed.stdout


def journal_paths(bookDir):
    # Finding C1: each process now writes its own "maro_journal.<pid>.jsonl"
    # file (MaroDiag.cpp's currentProcessId()/JournalWriter::pathForProcess)
    # instead of one shared "maro_journal.jsonl" -- sharing a single file
    # across processes let one process's session boundary get corrupted by
    # another's interleaved writes. This directory is fresh per ctest
    # invocation (MARO_TEST_BOOK_ROOT), so any per-process file found here
    # belongs to one of this test's own mayapy subprocesses.
    return sorted(glob.glob(os.path.join(bookDir, "maro_journal.*.jsonl")))


def orchestrate():
    env = os.environ.copy()
    bookDir = env["MARO_DIAG_BOOK_DIR"]

    rc1, out1 = run_session("crash1", env)
    print("---- session 1 (dies without closing) ----")
    print(out1)
    assert rc1 != 0, "session 1 is supposed to die abnormally, not exit cleanly"

    paths_after_1 = journal_paths(bookDir)
    assert len(paths_after_1) == 1, (
        f"expected exactly one per-process journal after session 1, found {paths_after_1}"
    )
    with open(paths_after_1[0], encoding="utf-8") as f:
        text1 = f.read()
    assert TARGET_TAG in text1, "the diagnostic raised before the crash must be on disk"
    assert '"event":"close"' not in text1, (
        "session 1 died before writing a close line -- that absence IS the crash signal"
    )
    print("journal survived the crash OK")

    rc2, out2 = run_session("crash2", env)
    print("---- session 2 (also dies without closing, same tag) ----")
    print(out2)
    assert rc2 != 0, "session 2 is supposed to die abnormally, not exit cleanly"

    # Item 1: the whole point of this rewrite is that the counting must see
    # BOTH crashed children's journals, not just the most recent one. Do not
    # just trust the aggregate count session 3 reports below -- confirm at
    # the file-system level, directly, that two INDEPENDENT per-process
    # journal files exist and that each one, on its own, carries the crash
    # evidence. Each crashing mayapy child is a distinct OS process (its own
    # PID), so per JournalWriter::pathForProcess it must have written its
    # own file rather than sharing or clobbering session 1's.
    paths_after_2 = journal_paths(bookDir)
    assert len(paths_after_2) == 2, (
        f"expected two independent per-process journals after two crashing "
        f"children, found {paths_after_2} -- if this is 1, the second child "
        f"overwrote or shared the first child's journal file instead of "
        f"getting its own"
    )
    assert paths_after_1[0] in paths_after_2, (
        "session 1's journal file must still be present, byte-for-byte the same file, "
        "untouched by session 2 writing its own"
    )
    for p in paths_after_2:
        with open(p, encoding="utf-8") as f:
            t = f.read()
        assert TARGET_TAG in t, (
            f"each crashed child's own journal file must carry the diagnostic it raised "
            f"just before dying, missing from {p}"
        )
        assert '"event":"close"' not in t, (
            f"both children died before writing a close line, but {p} has one"
        )
    print("both crashing children wrote independent, uncontaminated journals "
          "carrying the same tag OK -- confirmed by reading each file directly, "
          "not by trusting session 3's aggregate below")

    rc3, out3 = run_session("verify", env)
    print("---- session 3 (reads both crashes' journals, sees the 2-of-2 signal) ----")
    print(out3)
    assert rc3 == 0, f"session 3 failed with exit code {rc3}"

    rc4, out4 = run_session("recount", env)
    print("---- session 4 (a clean exit must not count as abnormal) ----")
    print(out4)
    assert rc4 == 0, f"session 4 failed with exit code {rc4}"

    print("journal crash detection OK")


def _raise_target_not_transform(cmds, suffix):
    """maroBindAxis를 non-transform 대상으로 불러 TARGET_TAG 에러를 낸다.
    실제 진단 경로(BoadMaro::error)를 통해서만 그 사이트 태그가 나온다 --
    테스트가 손으로 지어낸 값이 아니다."""
    light = cmds.createNode("pointLight", name="journalLight" + suffix)
    axis = cmds.createNode("maroAxis", name="journalAxis" + suffix)
    try:
        cmds.maroBindAxis(axis, light)
        raise AssertionError("expected rejection")
    except RuntimeError:
        pass


def run_as_session(label):
    import maya.standalone

    maya.standalone.initialize(name="python")

    import maya.cmds as cmds  # noqa: E402

    plugin = os.environ["MARO_PLUGIN_PATH"]
    cmds.loadPlugin(plugin)
    cmds.file(new=True, force=True)

    if label in ("crash1", "crash2"):
        _raise_target_not_transform(cmds, label)
        print(f"session {label} raised its diagnostic")
        sys.stdout.flush()
        # 정상 종료 경로를 타지 않고 프로세스를 끊는다 -- uninitializePlugin이
        # 돌지 않으므로 종료 줄이 없다. os._exit는 atexit 훅도 건너뛴다.
        os._exit(3)

    elif label == "verify":
        # Item 1: 이 세션이 이 스위트 전체에서 유일하게 "신호가 실제로 동작
        # 한다"를 보여주는 자리다. 앞선 두 세션이 같은 사이트 태그를 남기고
        # 죽었으므로, 두 문턱(비정상 종료 >= 2, 그중 이 태그가 걸린 세션
        # >= 2)을 함께 넘어야 한다.
        count = cmds.maroJournalAbnormalSessions()
        assert count == 2, (
            f"two previous sessions died without closing, so exactly two "
            f"abnormal sessions should be on record, got {count}"
        )
        print("abnormal session count == 2 OK")

        tags = cmds.maroJournalCrashAdjacentTags()
        assert TARGET_TAG in tags, (
            f"the tag raised just before both crashes must be counted, got {tags}"
        )
        print("crash-adjacent tag counted OK")

        # 저널만으로는 부족하다 -- maroDiagPanelDetail은 *이번 세션*의
        # 인메모리 레코드 하나를 골라 그 record.siteTag로 crashAdjacency를
        # 조회한다(PanelPresenter.cpp). 그러니 지금 이 세션에서 같은 진단을
        # 실제로 한 번 더 일으켜, 조회할 살아있는 레코드를 만든다.
        _raise_target_not_transform(cmds, "Verify")

        ROW_FIELDS = 8
        flat = cmds.maroDiagPanelRows(severity="error")
        assert len(flat) >= ROW_FIELDS, "expected at least one error row in this session"
        # 행은 순번 내림차순으로 온다(MaroPanelCommands.h 계약) -- 방금 낸
        # 진단이 이 세션에서 가장 최신이므로 rows[0]이다.
        newestRow = flat[:ROW_FIELDS]
        sequence = int(newestRow[3])

        detail = cmds.maroDiagPanelDetail(sequence=sequence)
        assert detail[13] == EXPECTED_NOTE, (
            f"expected the panel's crash-adjacency note for a 2-of-2 tag to read "
            f"{EXPECTED_NOTE!r}, got {detail[13]!r} -- this is the one assertion in the "
            f"whole suite that would ever show the feature doing its job, not just "
            f"correctly staying silent"
        )
        print("crash-adjacency note reaches the panel for a real journal-backed record OK")

    elif label == "recount":
        # 세션 3(verify)은 정상 종료했다. 종료 줄이 실제로 쓰였다면 비정상
        # 집계는 늘지 않는다 -- 여전히 2여야 한다. 이 세션이 없으면 종료
        # 줄을 아예 안 쓰는 구현도 통과한다(verify는 자기 open 줄을 쓰기
        # 전에 저널을 읽으므로 자기 자신을 못 본다).
        count = cmds.maroJournalAbnormalSessions()
        assert count == 2, (
            f"only the first two sessions died without closing; session 3 (verify) "
            f"exited cleanly and must not be counted as abnormal, got {count}"
        )
        print("clean exit not counted as abnormal OK")
    else:
        raise ValueError(f"unknown session label {label!r}")

    cmds.file(new=True, force=True)
    cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
    maya.standalone.uninitialize()
    print(f"session {label} teardown OK")


if __name__ == "__main__":
    sessionArg = next((a for a in sys.argv[1:] if a.startswith("--session=")), None)
    if sessionArg is None:
        orchestrate()
        sys.exit(0)
    run_as_session(sessionArg.split("=", 1)[1])
    sys.exit(0)
