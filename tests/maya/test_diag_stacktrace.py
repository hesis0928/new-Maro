"""BoadMaro::error()가 실패 지점의 호출 스택을 함께 남기는가.

**왜 있는가**: 이 플러그인에는 예외를 밖으로 못 내보내는 경계가 많아
(Maya 콜백에서 예외가 새면 Maya가 죽는다) 전부 `catch (...)`로 삼키고
메시지만 남긴다. 크래시가 아니라 조용한 실패라서 크래시 덤프도 안 생기고,
`tools/crashtriage/`의 사후 분석 도구가 손도 못 댄다. 2026-09-07에
maroPointCloud의 use-after-free를 쫓느라 하루를 쓴 것이 정확히 그
유형이었다 -- 그래서 Maya devkit이 이미 들고 있는 Boost의
`boost::stacktrace`를 진단 경로에 붙였다.

이 파일이 고정하는 계약:
  * Error 레코드에 실제 **심볼이 풀린** 스택이 담긴다(주소 나열이 아니라
    함수명). 심볼이 안 풀리면 이 기능은 존재 가치가 없으므로 그것까지 본다.
  * 같은 siteTag는 세션에 한 번만 뜬다 -- 심볼화가 비싸서(dbgeng COM) 매
    프레임 실패하는 뷰포트 콜백이 Maya를 얼리면 안 된다.
  * `MARO_DIAG_STACKTRACE=0`이면 아예 안 뜬다(킬 스위치).
  * maroDiagQuery의 평평한 결과에서 stackTrace는 **맨 끝** 필드다.
"""
import os
import subprocess
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)

STACK_FIELD = 12  # maroDiagQuery 결과에서 stackTrace의 위치(맨 끝)

# maroDiagEmit은 임의의 siteTag로 진단을 하나 만드는 디버그 커맨드다
# (기존 diag 테스트들이 쓰는 것과 같은 경로).
cmds.maroDiagEmit(severity="error", message="stacktrace probe",
                  siteTag="StackTraceProbe.First")
rec = cmds.maroDiagQuery(index=0)
assert len(rec) == 13, "maroDiagQuery must expose stackTrace as the last field: %r" % (rec,)
trace = rec[STACK_FIELD]

assert trace, "an Error record on the main thread must carry a stack trace"
# 주소만 나열되면 쓸모가 없다 -- 실제로 심볼이 풀렸는지 본다. 이 호출 스택은
# 반드시 플러그인 자신의 진단 경로를 지난다.
assert "BoadMaro" in trace or "maro::" in trace, (
    "the stack trace must be symbolised, got:\n" + trace)
print("stack trace is captured and symbolised OK")
print(trace.splitlines()[0] if trace.splitlines() else "<empty>")

# 같은 siteTag 두 번째 -- 심볼화 비용 때문에 세션당 1회만 뜬다.
cmds.maroDiagEmit(severity="error", message="stacktrace probe again",
                  siteTag="StackTraceProbe.First")
again = cmds.maroDiagQuery(index=0)
assert again[1] == "stacktrace probe again", again[1]
assert not again[STACK_FIELD], (
    "the same siteTag must not pay for symbolisation twice in a session, got:\n"
    + again[STACK_FIELD])
print("per-siteTag once-a-session latch OK")

# 다른 siteTag는 자기 몫으로 한 번 뜬다.
cmds.maroDiagEmit(severity="error", message="another site",
                  siteTag="StackTraceProbe.Second")
other = cmds.maroDiagQuery(index=0)
assert other[STACK_FIELD], "a different siteTag must get its own trace"
print("a different siteTag gets its own trace OK")

# Error가 아닌 심각도는 스택을 달지 않는다(error()에서만 뜬다).
cmds.maroDiagEmit(severity="warn", message="just a warning",
                  siteTag="StackTraceProbe.Warn")
warn = cmds.maroDiagQuery(index=0)
assert not warn[STACK_FIELD], "non-error severities must not carry a stack trace"
print("warn severity carries no stack trace OK")

# 킬 스위치. 환경변수는 프로세스 시작 시 한 번만 읽으므로 하위 프로세스로 본다.
child = """
import os, sys
import maya.standalone
maya.standalone.initialize(name="python")
import maya.cmds as cmds
cmds.loadPlugin(os.environ["MARO_PLUGIN_PATH"])
cmds.maroDiagEmit(severity="error", message="disabled probe",
                  siteTag="StackTraceProbe.Disabled")
rec = cmds.maroDiagQuery(index=0)
print("CHILD_TRACE_LEN", len(rec[12]))
sys.exit(0)
"""
env = dict(os.environ)
env["MARO_DIAG_STACKTRACE"] = "0"
proc = subprocess.run([sys.executable, "-c", child], env=env,
                      capture_output=True, text=True, timeout=180)
assert "CHILD_TRACE_LEN 0" in proc.stdout, (
    "MARO_DIAG_STACKTRACE=0 must suppress capture entirely.\n"
    "stdout:\n%s\nstderr:\n%s" % (proc.stdout, proc.stderr))
print("MARO_DIAG_STACKTRACE=0 kill switch OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
