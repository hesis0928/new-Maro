"""maroPointCloud 노드의 어트리뷰트 계약을 배치 모드에서 고정한다.

이 파일이 검증하는 것: 노드가 등록되고, 기본값이 스펙과 일치하고, points를
설정/조회할 수 있고, setStorable(false)가 실제로 걸려 있고(씬에 저장 안
됨), boundingBox()가 빈 배열/채워진 배열 양쪽에서 예외 없이 동작한다는 것.

이 파일이 **못** 하는 것: 실제로 그려지는지, 창을 띄운 채 언로드해도
안전한지는 배치 mayapy로 확인할 수 없다(QApplication이 아니라
QGuiApplication만 있어 QWidget 생성이 프로세스를 abort시키는 것과는 다른
문제지만, Viewport 2.0 렌더링 자체가 실제 GPU 컨텍스트를 필요로 해서
배치에서 원리적으로 불가능하다) -- docs/maro-main-ui-manual-checklist.md의
새 절이 담당한다.
"""
import os

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

node = cmds.createNode("maroPointCloud")
assert cmds.objExists(node)
print("maroPointCloud creation OK")

assert cmds.getAttr(node + ".pointSize") == 2.0
assert cmds.getAttr(node + ".enabled") is True
# color는 MFnNumericAttribute::createColor -- 즉 float32 3개다. getAttr는
# 그것을 파이썬 float(=double)로 넓혀서 돌려주므로 0.2f는
# 0.20000000298023224로 보인다. 리터럴과 == 로 비교하면 반드시 실패한다.
# 돌려받은 쪽을 반올림해서 비교한다(브리프의 round(...)는 기대값이 아니라
# 실측값에 걸렸어야 했다).
color = cmds.getAttr(node + ".color")[0]
assert tuple(round(c, 6) for c in color) == (0.2, 0.8, 1.0), color
print("default values OK")

storable = cmds.attributeQuery("points", node=node, storable=True)
assert storable is False, (
    "points must be non-storable -- scan snapshots must not be saved into .ma files")
print("points non-storable OK")

# sourceLidar는 이 포인트클라우드를 만든 maroLidar를 가리키는 메시지
# 어트리뷰트다. Task 1은 연결하지 않지만, Task 4가 그 이름으로 연결하므로
# 존재와 타입만 여기서 고정해 둔다.
assert cmds.attributeQuery("sourceLidar", node=node, exists=True)
assert cmds.attributeQuery("sourceLidar", node=node, message=True)
print("sourceLidar message attribute OK")

# 빈 배열에서 boundingBox()가 예외 없이, 그리고 "무효" 박스가 아니라
# 폴백 박스(-1..1)를 돌려주는지 먼저 본다.
emptyBbox = cmds.exactWorldBoundingBox(node)
assert emptyBbox == [-1.0, -1.0, -1.0, 1.0, 1.0, 1.0], emptyBbox
print("boundingBox on an empty array OK")

# 점 세 개를 손으로 채워 본다 -- Task 1의 워킹 스켈레톤이 실제로 증명해야
# 하는 것과 같은 데이터 경로다(사람이 뷰포트에서 확인하는 대상).
cmds.setAttr(node + ".points", 3,
             (0.0, 0.0, 0.0, 1.0),
             (1.0, 0.0, 0.0, 1.0),
             (0.0, 1.0, 0.0, 1.0),
             type="pointArray")
readBack = cmds.getAttr(node + ".points")
assert len(readBack) == 3
print("points round-trip OK")

# 브리프의 원래 단언(bbox[3] > bbox[0] and bbox[4] > bbox[1])은 위의 빈 배열
# 폴백 박스(-1..1)도 그대로 통과시킨다 -- 즉 boundingBox()가 points를 아예
# 안 읽어도 초록이 된다. 실제 점 범위 (0,0,0)-(1,1,0)과 맞는지 직접 본다.
bbox = cmds.exactWorldBoundingBox(node)
expected = [0.0, 0.0, 0.0, 1.0, 1.0, 0.0]
assert all(abs(a - b) < 1e-4 for a, b in zip(bbox, expected)), (
    f"boundingBox() must reflect the actual points, got {bbox}")
print("boundingBox reflects points OK")

# 언로드 자체(창 없이)는 최소한 크래시하지 않아야 한다 -- 창을 띄운 채
# 언로드하는 케이스는 배치에서 재현 불가능하므로 수동 체크리스트가 담당한다.
cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
print("unload without an open window OK")
