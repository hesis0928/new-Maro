"""저널이 크래시를 건너 살아남는지, 그리고 다음 실행이 비정상 종료를
알아채는지 두 프로세스로 확인한다.

왜 두 프로세스인가: 저널의 존재 이유가 "프로세스가 죽어도 남는 것"이므로,
한 프로세스 안에서는 인메모리 상태와 구분되지 않는다. 세션 1은 정상 종료
줄을 쓰기 **전에** 스스로를 끊는다 -- 감시자 입장에서 진짜 크래시와
구분되지 않는 신호이며, 컴퓨터를 죽이지 않고 만들 수 있다.

좀비 mayapy.exe 방지: subprocess.run(timeout=...)은 타임아웃 시 자식을
kill()하고 wait()까지 마친 뒤에야 예외를 던진다 -- 각 세션 호출을 그 경계
안에 두는 것만으로 무한 대기도, 죽은 자식이 남는 것도 막힌다."""
import os
import subprocess
import sys

MAYAPY = sys.executable
THIS_FILE = os.path.abspath(__file__)
SESSION_TIMEOUT_SECONDS = 90


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


def journal_path(bookDir):
    return os.path.join(bookDir, "maro_journal.jsonl")


def orchestrate():
    env = os.environ.copy()
    bookDir = env["MARO_DIAG_BOOK_DIR"]

    rc1, out1 = run_session("crash", env)
    print("---- session 1 (dies without closing) ----")
    print(out1)
    assert rc1 != 0, "session 1 is supposed to die abnormally, not exit cleanly"

    path = journal_path(bookDir)
    assert os.path.exists(path), f"expected a journal at {path}"
    with open(path, encoding="utf-8") as f:
        text = f.read()
    assert "MaroBindAxisCommand.TargetNotTransform" in text, (
        "the diagnostic raised before the crash must be on disk"
    )
    assert '"event":"close"' not in text, (
        "session 1 died before writing a close line -- that absence IS the crash signal"
    )
    print("journal survived the crash OK")

    rc2, out2 = run_session("detect", env)
    print("---- session 2 (detects the abnormal end, then exits cleanly) ----")
    print(out2)
    assert rc2 == 0, f"session 2 failed with exit code {rc2}"

    # 세션 3이 있어야 종료 줄이 실제로 무슨 일을 하는지 확인된다. 세션 2는
    # 정상 종료했으므로 비정상 집계에 **더해지면 안 된다** -- 여전히 1이어야
    # 한다. 이 세션이 없으면 종료 줄을 아예 안 쓰는 구현도 통과한다(세션 2는
    # 자기 open 줄을 쓰기 전에 저널을 읽으므로 자기 자신을 못 본다).
    rc3, out3 = run_session("recount", env)
    print("---- session 3 (a clean exit must not count as abnormal) ----")
    print(out3)
    assert rc3 == 0, f"session 3 failed with exit code {rc3}"

    print("journal crash detection OK")


def run_as_session(label):
    import maya.standalone

    maya.standalone.initialize(name="python")

    import maya.cmds as cmds  # noqa: E402

    plugin = os.environ["MARO_PLUGIN_PATH"]
    cmds.loadPlugin(plugin)
    cmds.file(new=True, force=True)

    if label == "crash":
        light = cmds.createNode("pointLight", name="journalLight")
        axis = cmds.createNode("maroAxis", name="journalAxis")
        try:
            cmds.maroBindAxis(axis, light)
            raise AssertionError("expected rejection")
        except RuntimeError:
            pass
        print("session 1 raised its diagnostic")
        sys.stdout.flush()
        # 정상 종료 경로를 타지 않고 프로세스를 끊는다 -- uninitializePlugin이
        # 돌지 않으므로 종료 줄이 없다. os._exit는 atexit 훅도 건너뛴다.
        os._exit(3)

    elif label == "detect":
        count = cmds.maroJournalAbnormalSessions()
        assert count == 1, (
            f"the previous session died without closing, so exactly one abnormal "
            f"session should be on record, got {count}"
        )
        print("abnormal session detected OK")

        tags = cmds.maroJournalCrashAdjacentTags()
        assert "MaroBindAxisCommand.TargetNotTransform" in tags, (
            f"the tag raised just before the crash must be counted, got {tags}"
        )
        print("crash-adjacent tag counted OK")

    elif label == "recount":
        # 세션 2는 정상 종료했다. 종료 줄이 실제로 쓰였다면 비정상 집계는
        # 늘지 않는다 -- 여전히 1이어야 한다.
        count = cmds.maroJournalAbnormalSessions()
        assert count == 1, (
            f"only the first session died without closing; the second exited "
            f"cleanly and must not be counted as abnormal, got {count}"
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
