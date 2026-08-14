"""C1 회귀(cross-session): 완전히 별개인 두 mayapy 프로세스가 하나의
MARO_DIAG_BOOK_DIR을 공유한다.

왜 다른 diag_book 테스트로는 부족한가: test_diag_book.py는 한 프로세스
안에서 같은 axis/light를 재사용해 두 번 실패시킨다. 그러면 "book이 과거
발생의 message를 그대로 재생한다"는 버그(Finding C1)와 "지금 발생을 다시
정확히 렌더링했다"는 정상 동작이 바이트 단위로 똑같은 문자열을 만들어낸다 --
같은 프로세스, 같은 노드 이름이므로 구별할 수가 없다. 이 버그를 실제로
잡으려면 두 번째 발생이 첫 번째 발생과 절대 같은 이름을 쓰지 않는, 완전히
별개의 프로세스여야 한다.

이 테스트는 또한 book이 세션 경계를 실제로 넘어 살아남는지 증명하는 유일한
테스트이기도 하다: BoadMaro::error()는 매 호출마다 BookStore::loadMerged()로
스필 파일을 디스크에서 다시 읽는다. 인메모리 캐시(예: 정적 std::unordered_map을
한 번만 채우고 그 뒤로는 디스크를 다시 안 보는 구현)로 바꿔도 한 프로세스
안에서 도는 다른 모든 book 테스트는 여전히 통과한다 -- 그 프로세스가 살아있는
동안은 메모리 캐시나 디스크 재조회나 결과가 같기 때문이다. 하지만 그 구현은
두 번째 프로세스가 시작될 때 빈 메모리에서 출발하므로 여기서만 조용히
깨진다.

구조: 이 파일 자체가 오케스트레이터다. 인자 없이 실행되면(ctest가 부르는
방식) 자기 자신을 --session=1, --session=2로 두 번 자식 프로세스로 띄운다.
각 자식은 독립된 mayapy.exe이자 독립된 Maya 씬/프로세스 힙이다.

좀비 mayapy.exe 방지: 이 프로젝트는 남은 mayapy.exe가 다음 빌드의 DLL
쓰기를 막는 사고(LNK1168)를 반복해서 겪었다. subprocess.run(timeout=...)은
타임아웃 시 자식을 kill()하고 wait()까지 마친 뒤에야 TimeoutExpired를
던진다(파이썬 표준 라이브러리 문서에 명시된 동작) -- 그래서 각 세션 호출을
그 경계 안에 두는 것만으로 무한 대기도, 죽은 자식이 남는 것도 막힌다."""
import os
import subprocess
import sys

MAYAPY = sys.executable
THIS_FILE = os.path.abspath(__file__)
# 세션 하나가 정상적으로 끝나기에 넉넉한 시간. maya.standalone.initialize()
# 자체가 몇 초 걸리므로 여유를 둔다 -- 그래도 무한대는 아니다(좀비 방지).
# CMakeLists.txt가 이 테스트 전체에 주는 CTest TIMEOUT(다른 diag_* 형제들과
# 같은 240s)보다 두 세션의 합이 항상 작아야 한다: 그래야 정상적인 경우
# ctest 자신의 타임아웃 킬 경로를 아예 타지 않는다 -- 이 프로세스 트리(부모
# 오케스트레이터 + 자식 mayapy)를 ctest가 온전히 정리해 준다는 보장에
# 기대지 않기 위해서다.
SESSION_TIMEOUT_SECONDS = 90


def run_session(session_label, env):
    """이 파일을 --session=<label>로 자식 mayapy 프로세스로 띄우고 끝까지
    기다린다. 반환: (returncode, 합쳐진 stdout+stderr 문자열).

    타임아웃이 나면 subprocess.run이 이미 자식을 죽이고 정리했으므로, 여기서
    다시 kill/wait를 반복할 필요가 없다 -- 그 사실 자체를 실패 메시지에
    남긴다."""
    try:
        completed = subprocess.run(
            [MAYAPY, THIS_FILE, f"--session={session_label}"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=SESSION_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        output = (exc.output or "")
        raise AssertionError(
            f"session {session_label} did not finish within "
            f"{SESSION_TIMEOUT_SECONDS}s and was killed (subprocess.run's "
            f"timeout kills+waits the child automatically, so no zombie "
            f"mayapy.exe is left behind) -- output so far:\n{output}"
        )
    return completed.returncode, completed.stdout


def orchestrate():
    # 두 세션이 공유할 book 디렉터리는 CMake가 MARO_DIAG_BOOK_DIR로 이미
    # 건네준다(빌드 트리 밑, maya_diag_book_root_reset 픽스처가 매 실행 전에
    # 비운다). 여기서 따로 mkdtemp를 하면 그 픽스처를 무력화하고 실행마다
    # 디렉터리를 하나씩 흘리게 된다. 자식 세션들은 os.environ.copy()로
    # 그대로 물려받는다.
    env = os.environ.copy()

    rc1, out1 = run_session("1", env)
    print("---- session 1 (fresh analysis) output ----")
    print(out1)
    assert rc1 == 0, f"session 1 failed with exit code {rc1}"

    rc2, out2 = run_session("2", env)
    print("---- session 2 (cross-session book hit) output ----")
    print(out2)
    assert rc2 == 0, f"session 2 failed with exit code {rc2}"

    print("cross-session book replay OK")


def run_as_session(session_label):
    import maya.standalone

    maya.standalone.initialize(name="python")

    import maya.cmds as cmds  # noqa: E402

    plugin = os.environ["MARO_PLUGIN_PATH"]
    cmds.loadPlugin(plugin)
    cmds.file(new=True, force=True)

    if session_label == "1":
        # 이 프로세스만 아는 이름들. 세션 2는 이 이름을 전혀 만들지 않는다 --
        # 그래서 세션 2의 message에 이 이름이 나오면 그건 book이 이 세션의
        # 텍스트를 잘못 재생한 것일 수밖에 없다.
        light = cmds.createNode("pointLight", name="lightA")
        axis = cmds.createNode("maroAxis", name="axisA")

        try:
            cmds.maroBindAxis(axis, light)
            raise AssertionError("expected rejection")
        except RuntimeError:
            pass

        rec = cmds.maroDiagQuery(index=0)
        message = rec[1]
        servedFromBook = rec[8]
        assert "lightA" in message, (
            f"session 1's own message must name lightA, got {message!r}"
        )
        assert servedFromBook == "0", (
            "session 1 is the first ever occurrence of this site tag in a "
            "brand-new book directory -- it must be a fresh analysis, not a "
            "book hit"
        )
        print(f"session 1 message: {message!r}")
        print("session 1 fresh analysis OK")

    elif session_label == "2":
        # 세션 1과 겹치지 않는, 이 프로세스만의 이름들.
        light = cmds.createNode("pointLight", name="lightB")
        axis = cmds.createNode("maroAxis", name="axisB")

        analysisBefore = cmds.maroDiagAnalysisCount()
        try:
            cmds.maroBindAxis(axis, light)
            raise AssertionError("expected rejection")
        except RuntimeError:
            pass
        analysisAfter = cmds.maroDiagAnalysisCount()

        rec = cmds.maroDiagQuery(index=0)
        (severity, message, errorHash, nodeType, attributeName,
         activeCommand, axisOrTarget, remedy, servedFromBook,
         priorAnalysis) = rec

        assert servedFromBook == "1", (
            f"session 2 triggers the exact same rejection site as session 1 "
            f"(same site tag -> same hash), and that entry was written to "
            f"disk by session 1's spill append -- a fresh process reading "
            f"the book off disk must recognize it as a book hit, got "
            f"servedFromBook={servedFromBook!r}"
        )
        assert analysisAfter == analysisBefore, (
            f"a book hit must not trigger a fresh analysis -- count went "
            f"{analysisBefore} -> {analysisAfter}"
        )

        # 이게 핵심 단언이다 (Finding C1): message는 이번 발생이 실제로
        # 만든 문장이어야 한다 -- session 1의 저장된 분석 텍스트를 그대로
        # 재생한 것이면 안 된다.
        assert "lightB" in message, (
            f"session 2's message must name ITS OWN object (lightB), got "
            f"{message!r}"
        )
        assert "lightA" not in message, (
            f"session 2's message must NOT name session 1's object (lightA) "
            f"-- if it does, boad replayed a different process's rendered "
            f"text as if it were this occurrence's fact, which is exactly "
            f"Finding C1 (the book must never overwrite the CURRENT message "
            f"with a stale prior occurrence's text). got {message!r}"
        )

        # priorAnalysis는 반대로 session 1의 텍스트를 담고 있어야 한다 --
        # 그게 이 필드가 존재하는 이유다: "과거엔 뭐였는지"를 잃지 않으면서
        # "지금 무슨 일이 났는지"와 뒤섞지 않는 것.
        assert "lightA" in priorAnalysis, (
            f"session 2's priorAnalysis must carry session 1's message "
            f"forward (read from disk, not from any in-process memory -- "
            f"this process never created lightA), got {priorAnalysis!r}"
        )

        print(f"session 2 message: {message!r}")
        print(f"session 2 priorAnalysis: {priorAnalysis!r}")
        print(
            "session 2 cross-session book hit named its own object, kept "
            "session 1's analysis separate, and did not trigger a fresh "
            "analysis OK"
        )
    else:
        raise ValueError(f"unknown session label {session_label!r}")

    cmds.file(new=True, force=True)
    cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
    maya.standalone.uninitialize()
    print(f"session {session_label} teardown OK")


if __name__ == "__main__":
    session_arg = None
    for arg in sys.argv[1:]:
        if arg.startswith("--session="):
            session_arg = arg.split("=", 1)[1]

    if session_arg is None:
        # ctest가 부르는 경로: 오케스트레이터로 동작한다. 이 프로세스 자체는
        # maya.standalone을 한 번도 초기화하지 않는다 -- 순수하게 두 자식
        # 세션을 순서대로 띄우고 결과만 검사한다.
        orchestrate()
        sys.exit(0)
    else:
        # 자식 프로세스 경로: 실제 Maya 세션 하나를 맡는다.
        run_as_session(session_arg)
        sys.exit(0)
