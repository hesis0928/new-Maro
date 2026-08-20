"""플러그인이 감시자를 spawn하고, 정상/비정상 종료를 감시자가 구분해
기록 파일에 남기는지 여러 프로세스로 확인한다.

test_journal.py와 같은 이유로 여러 프로세스다 -- 감시자의 존재 이유가
"프로세스가 죽어도 남는 관측"이므로, 크래시 세션은 정상 종료 줄을 쓰기
전에 스스로를 끊는다.
"""
import json
import os
import subprocess
import sys
import time

import maya.standalone  # noqa: F401 (mayapy 표준 임포트 순서를 따름 -- 실제 사용은 run_as_session에서)

MAYAPY = sys.executable
THIS_FILE = os.path.abspath(__file__)
SESSION_TIMEOUT_SECONDS = 90

# 감시자가 스스로 종료하기를 기다리는 상한. 감시자의 종료는 이 테스트가
# 확인하려는 것(좀비 없음)인 동시에, 아래에서 기록 파일이 확정됐다고
# 판단하는 기준이기도 하다.
SENTINEL_EXIT_TIMEOUT_SECONDS = 10

# [브리프에서 고침] 자식의 PID를 stdout의 *마지막 줄*에서 읽으면 안 된다.
# 실측(mayapy 2026): maya.standalone이 올라간 프로세스에서 os._exit()를 부르면
# ExitProcess -> LdrShutdownProcess로 Maya의 정적 소멸자들이 돌다가 그 안에서
# 죽고, Maya의 치명적 오류 핸들러가 우리 PID 줄 *뒤에* 스택 트레이스와
# "Fatal Error. Attempting to save in ...", CER(senddmp.exe) 실행 실패 줄까지
# 쏟아낸다. 그래서 마지막 줄은 PID가 아니라 그 잡음이고, 브리프 원안의
# int(out.strip().splitlines()[-1])은 ValueError로 터진다(실측). 잡음이
# 얼마나/어떤 순서로 나오든 영향받지 않게 표식을 붙여 찾는다.
PID_MARKER = "MARO_SESSION_PID "


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


def session_pid(label, output):
    for line in output.splitlines():
        if line.startswith(PID_MARKER):
            return int(line[len(PID_MARKER):].strip())
    raise AssertionError(
        f"session {label} never printed its {PID_MARKER!r} line -- output:\n{output}"
    )


def sentinel_record_path(bookDir, pid):
    return os.path.join(bookDir, f"maro_sentinel.{pid}.json")


def read_record(path, timeoutSeconds):
    """기록 파일이 생기고 온전히 파싱될 때까지 기다렸다 돌려준다.

    존재 확인과 파싱을 한 헬퍼로 묶는 이유: writeSentinelRecord는 trunc 후
    dump라 원자적이지 않다(SentinelRecord.cpp). 감시자가 판정을 덧쓰는 바로
    그 순간에 읽으면 0바이트나 잘린 JSON을 볼 수 있다 -- 그것은 실패가 아니라
    "아직 쓰는 중"이므로 다시 읽어야 한다. 파일이 끝내 안 생기거나 끝내 안
    파싱되면 None.
    """
    deadline = time.time() + timeoutSeconds
    while time.time() < deadline:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            time.sleep(0.05)
    return None


def process_is_running(pid):
    # tasklist는 이 저장소가 이미 다른 곳(memo, 리뷰 코멘트)에서 좀비 확인에
    # 쓰는 것과 같은 표준 도구다. PowerShell Get-CimInstance를 여기서 또
    # 부르는 대신 subprocess로 tasklist를 쓰는 이유는 이 파일이 순수
    # Python이라 PowerShell 호출 오버헤드를 피하기 위해서다.
    #
    # [브리프에서 고침] 여기서 text=True로 받으면 안 된다. tasklist가 조건에
    # 맞는 프로세스를 못 찾으면 안내 문구를 내는데, 콘솔이 없는 채로 돌 때
    # (=ctest 밑에서 정확히 그렇다) 그 문구가 OEM 코드페이지(이 머신은 CP949)로
    # 나온다. 그런데 Maya는 PYTHONUTF8=1을 걸어 두므로 파이썬은 그것을 UTF-8로
    # 디코드하려다 UnicodeDecodeError를 낸다. 그 예외가 나는 곳이 하필
    # communicate()의 리더 *스레드*라서, run()은 예외를 올려 보내지 않고
    # returncode=0에 stdout=None인 결과를 조용히 돌려준다 -- 그러면 다음 줄이
    # "argument of type 'NoneType' is not iterable"로 터진다(실측: 손으로
    # 직접 돌릴 때는 콘솔이 붙어 문구가 ASCII 영어로 나와 멀쩡히 통과하고,
    # ctest에서만 실패한다).
    #
    # 그래서 디코드를 아예 안 한다. 우리가 찾는 것은 PID의 ASCII 숫자열뿐이고
    # 그것은 어떤 코드페이지에서도 같은 바이트다. 공백으로 끊은 토큰과 정확히
    # 비교하므로 메모리 사용량("14,432 K") 같은 다른 숫자에 걸리지도 않는다.
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
        capture_output=True,
    )
    # 바이트로 받으면 위의 디코드 사고가 원천적으로 없으므로 stdout이 None일
    # 수 없다. 그래도 확인하는 이유는, 만에 하나 None이 오면 "안 돌고 있다"로
    # 조용히 넘어가는 것이 곧 좀비를 놓치는 통과가 되기 때문이다 -- 이
    # 테스트에서 가장 하면 안 되는 실패 방식이라 시끄럽게 터뜨린다.
    assert result.stdout is not None, (
        f"tasklist returned no captured output for pid {pid} (rc={result.returncode}) -- "
        f"cannot tell whether the sentinel is still running"
    )
    return str(pid).encode("ascii") in result.stdout.split()


def wait_for_process_exit(pid, timeoutSeconds):
    deadline = time.time() + timeoutSeconds
    while time.time() < deadline and process_is_running(pid):
        time.sleep(0.2)
    return not process_is_running(pid)


def settled_record(label, bookDir, childPid):
    """감시자가 죽고 난 뒤의, 더 이상 안 변하는 기록 파일을 돌려준다.

    [브리프에서 고침] 브리프 원안은 기록 파일이 *존재*하자마자 읽고 거기서
    판정을 단언했다. 그런데 감시자는 뜨자마자 판정 없는 초기 기록을 먼저
    쓰고(main.cpp의 initialRecord), 판정은 한참 뒤에 그 파일을 덧쓴다 --
    즉 "파일이 있다"는 "판정이 끝났다"가 전혀 아니다. 그렇게 읽으면 두 단언이
    모두 시점에 휘둘린다: 크래시 세션은 아직 안 쓰인 false를 놓칠 수 있고,
    정상 세션의 "필드가 없어야 한다"는 (notifyCleanExit가 고장 나서 false가
    쓰이는 중이어도) 그 전에 찍은 스냅숏을 보고 통과할 수 있다.

    실측으로는 지금 통과한다 -- 감시자가 판정을 쓰는 시점이 자식 프로세스가
    완전히 죽는 시점보다 *앞선다*(자식의 파이프 핸들은 maro.mll의 정적
    NamedPipeClient 소멸자가 DLL_PROCESS_DETACH에서 닫는데, 그 뒤로도 Maya의
    나머지 종료와 치명적 오류 핸들러가 몇 초를 더 쓴다). 하지만 그 여유는
    Maya의 종료가 느리다는 우연에 기대는 것이라 단언의 근거로 삼을 수 없다.

    대신 감시자 프로세스가 *끝났다*는 것을 먼저 확인한다. 그 순간부터 이
    파일을 쓸 수 있는 주체가 세상에 없으므로(기록 파일은 Maya PID마다 하나고
    명명된 뮤텍스가 그 PID의 감시자를 하나로 묶는다) 그때 읽은 내용이 곧
    최종 판정이다. 좀비가 없다는 확인과 판정이 확정됐다는 근거가 같은
    관측이라는 뜻이기도 하다.
    """
    recordPath = sentinel_record_path(bookDir, childPid)
    # 먼저 감시자 PID를 알아내야 종료를 기다릴 수 있다. sentinelPid는 초기
    # 기록에 이미 들어 있고 이후 절대 안 바뀌므로 지금 읽어도 안전하다.
    early = read_record(recordPath, 10)
    assert early is not None, (
        f"sentinel never wrote a readable record file for the {label} session at "
        f"{recordPath} -- the plugin either never spawned it or it died before "
        f"writing anything"
    )
    sentinelPid = early["sentinelPid"]

    assert wait_for_process_exit(sentinelPid, SENTINEL_EXIT_TIMEOUT_SECONDS), (
        f"sentinel (pid {sentinelPid}) for the {label} session was still running "
        f"{SENTINEL_EXIT_TIMEOUT_SECONDS}s after its Maya was gone -- that is the "
        f"zombie this whole layer exists to prevent"
    )

    final = read_record(recordPath, 5)
    assert final is not None, (
        f"the {label} session's record file stopped being readable after the "
        f"sentinel exited at {recordPath}"
    )
    return sentinelPid, final


def orchestrate():
    env = os.environ.copy()
    bookDir = env["MARO_DIAG_BOOK_DIR"]
    os.makedirs(bookDir, exist_ok=True)

    # --- 정상 세션 ---
    rc1, out1 = run_session("clean", env)
    print("---- clean session ----")
    print(out1)
    assert rc1 == 0, f"clean session failed with exit code {rc1}"

    # 자식이 자기 PID를 stdout에 표식 줄로 남긴다(아래 run_as_session).
    childPid = session_pid("clean", out1)
    sentinelPid, record = settled_record("clean", bookDir, childPid)

    # [최종 리뷰 3j] 이 기록이 정말 *이* 세션의 것인지는 지금까지 파일 이름
    # 규칙(maro_sentinel.<pid>.json)으로만 암묵적으로 보장됐다. 파일 안의
    # ownerMayaPid를 실제 자식 PID와 맞춰 보면, 플러그인이 감시자에게 넘긴
    # 소유자 PID와 감시자가 기록에 남긴 값이 같은 것이라는 사실까지
    # 명시적으로 고정된다 -- 이름은 맞는데 내용이 딴 세션인 기록을 잡는다.
    assert record["ownerMayaPid"] == childPid, (
        f"the clean session's record claims owner pid {record['ownerMayaPid']} but the "
        f"mayapy child that spawned it was {childPid} -- got {record}"
    )

    # 정상 종료의 증거는 "false가 아니다"가 아니라 "필드가 아예 없다"이다.
    # 감시자는 정상 종료 신호를 받으면 판정을 남길 자격이 생기기 전에
    # 종료하므로(SentinelRecord.h), true도 false도 쓰여선 안 된다.
    assert "lastSessionEndedCleanly" not in record, (
        "a clean session must leave the field unset, not write true -- "
        f"got {record}"
    )
    print(f"clean session: sentinel (pid {sentinelPid}) recorded no verdict and "
          f"exited on its own OK")

    # --- 비정상 세션 ---
    rc2, out2 = run_session("crash", env)
    print("---- crash session ----")
    print(out2)
    assert rc2 != 0, "crash session is supposed to die abnormally, not exit cleanly"

    crashChildPid = session_pid("crash", out2)
    crashSentinelPid, crashRecord = settled_record("crash", bookDir, crashChildPid)

    # 정상 세션과 같은 교차 확인(위 [최종 리뷰 3j] 주석 참고).
    assert crashRecord["ownerMayaPid"] == crashChildPid, (
        f"the crash session's record claims owner pid {crashRecord['ownerMayaPid']} but "
        f"the mayapy child that spawned it was {crashChildPid} -- got {crashRecord}"
    )

    assert crashRecord.get("lastSessionEndedCleanly") is False, (
        f"a session that died without SESSION_END_CLEAN must be recorded as "
        f"abnormal, got {crashRecord}"
    )
    # 두 세션이 서로 다른 감시자를 얻었는지도 확인한다 -- 같은 값이면 위
    # 두 단언이 사실은 한 프로세스의 기록 하나를 두 번 본 것이 된다.
    assert crashSentinelPid != sentinelPid, (
        f"both sessions somehow report the same sentinel pid {sentinelPid} -- "
        f"the crash session's verdict would then be about the clean session"
    )
    print(f"crash session: sentinel (pid {crashSentinelPid}) recorded the abnormal "
          f"exit and exited on its own OK")


def run_as_session(label):
    maya.standalone.initialize(name="python")

    import maya.cmds as cmds  # noqa: E402

    plugin = os.environ["MARO_PLUGIN_PATH"]
    cmds.loadPlugin(plugin)
    cmds.file(new=True, force=True)

    # 감시자가 실제로 spawn을 시도할 시간을 준다 -- connectOrSpawn()은
    # initializePlugin 안에서 동기적으로 접속까지 마치므로 이 시점에는
    # 이미 끝나 있어야 정상이지만, 느린 머신을 위한 여유를 조금 둔다.
    time.sleep(0.5)

    ownPid = os.getpid()

    if label == "clean":
        cmds.file(new=True, force=True)
        cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
        maya.standalone.uninitialize()
        # 오케스트레이터가 자기 PID로 감시자 기록 파일을 찾을 수 있게
        # 표식 줄에 PID를 남긴다.
        print(f"{PID_MARKER}{ownPid}")
        return

    if label == "crash":
        # 표식을 os._exit *전에* 찍는다 -- os._exit는 그 뒤의 어떤 출력
        # 기회도 남기지 않는다.
        print(f"{PID_MARKER}{ownPid}")
        sys.stdout.flush()
        os._exit(3)  # uninitializePlugin을 안 돌린다 -- SESSION_END_CLEAN 없음.

    raise ValueError(f"unknown session label {label!r}")


if __name__ == "__main__":
    sessionArg = next((a for a in sys.argv[1:] if a.startswith("--session=")), None)
    if sessionArg is None:
        orchestrate()
        sys.exit(0)
    run_as_session(sessionArg.split("=", 1)[1])
    # "crash" 경로는 os._exit로 여기 도달하지 않는다. "clean" 경로는 이미
    # 위에서 자기 PID를 찍고 return했다 -- 여기 추가로 다시 안 찍는다.
