"""maroPointCloud의 드로우 오버라이드가 실제로 점을 그리는지 배치에서 검증한다.

**이 파일이 존재하는 이유**: 2026-09-06 수동 테스트에서 이 노드가 뷰포트에
아무것도 안 그리고 Maya가 간헐적으로 크래시했는데, 원인 규명에 여러 번
실패했다. 그때의 전제는 "드로우 오버라이드는 실제 GPU 컨텍스트가 필요해
배치 mayapy로는 원리적으로 검증 불가능"이었다 -- 그게 틀렸다.
`cmds.ogsRender`는 배치 mayapy에서도 Viewport 2.0 렌더러를 실제로 띄우고
(이 머신에서 OpenGL 4.6으로 초기화되는 것을 확인), 그러면
prepareForDraw/addUIDrawables가 그대로 불린다.

**잡는 버그**: prepareForDraw()가 `MFnPointArrayData::array()`로 점을 읽어
MUserData에 넣었는데, array()는 Maya 내부 데이터를 가리키는 *참조*라 함수가
끝나면 무효가 됐다. 그래서 prepareForDraw는 점 5개를 읽었는데
addUIDrawables에서는 0개였고(아무것도 안 그려짐), 동시에 해제된 Maya
버퍼를 붙들고 있는 use-after-free라 나중에 힙 손상 크래시로 터졌다.
`copyTo()`가 실제 복사를 하는 접근자다.

계측은 플러그인의 MARO_TRACE_DRAW 트레이스를 쓴다(C++ fprintf(stderr)).
파이썬에서 그걸 받으려면 fd 2 자체를 파일로 갈아끼워야 한다 -- sys.stderr
교체로는 C 런타임이 쓰는 fd를 못 잡는다.
"""
import os
import sys
import tempfile

os.environ["MARO_TRACE_DRAW"] = "1"

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

# 렌더 결과 이미지가 사용자의 기본 프로젝트 폴더로 새지 않게 한다.
workdir = tempfile.mkdtemp(prefix="maro-ogs-")
try:
    cmds.workspace(workdir, openWorkspace=True)
except Exception:  # noqa: BLE001 -- 워크스페이스가 없으면 기본값으로 둔다
    pass

node = cmds.createNode("maroPointCloud")
cmds.setAttr(node + ".points", 5,
             (0, 0, 0, 1), (2, 0, 0, 1), (0, 2, 0, 1), (0, 0, 2, 1), (1, 1, 1, 1),
             type="pointArray")
camera = cmds.camera()[0]
cmds.viewFit(camera, all=True)

try:
    cmds.ogsRender(camera=camera, width=160, height=120, currentFrame=True,
                   noRenderView=True)
except Exception as exc:  # noqa: BLE001 -- GPU 없는 환경이면 검증 자체가 불가능
    print("SKIP: Viewport 2.0 unavailable in this batch session (%s)" % exc)
    maya.standalone.uninitialize()
    sys.exit(0)

# 트레이스는 플러그인 언로드(=드로우 오버라이드 해제) 시점에 stderr로 나온다.
tracePath = os.path.join(workdir, "trace.txt")
savedStderr = os.dup(2)
try:
    with open(tracePath, "w") as traceFile:
        os.dup2(traceFile.fileno(), 2)
        cmds.file(new=True, force=True)
        cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
finally:
    os.dup2(savedStderr, 2)
    os.close(savedStderr)

with open(tracePath, "r", errors="replace") as fh:
    trace = fh.read()
print(trace.strip())

assert "[maro-trace]" in trace, (
    "draw-override trace missing -- MARO_TRACE_DRAW not honoured?\n" + trace)
assert "prepareForDraw=0" not in trace, (
    "prepareForDraw was never called -- the draw override is not wired to the "
    "node's classification string\n" + trace)
assert "addUIDrawables=0 " not in trace, (
    "addUIDrawables was never called\n" + trace)
# 이것이 이 파일의 본론이다. 점을 읽어놓고 그리지 못하면 회귀다.
assert "pointsDrawn=5" in trace, (
    "the draw override read the points but drew none -- this is exactly the "
    "MFnPointArrayData::array() dangling-reference regression\n" + trace)
assert "empty=0" in trace, ("addUIDrawables saw an empty point array\n" + trace)
print("maroPointCloud draw override actually drew its points OK")

maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
