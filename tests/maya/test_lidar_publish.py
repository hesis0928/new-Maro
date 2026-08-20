"""maroLidar가 메쉬를 스캔해 실제로 발행 큐까지 도달하는지 종단으로
확인한다. maroBridgeStats()[1](drainedSampleCount)로 검증한다 -- 이
씬에는 maroAxis가 하나도 없으므로, 그 카운터가 오르는 유일한 원인은
LiDAR 샘플이 드레인된 것뿐이다. 그 전제를 그냥 믿지 않고 마지막에
maroBridgeStats()[0](collectedSampleCount, 축 전용 계수기)이 여전히 0인
것까지 함께 확인한다.

발행된 PointCloud2의 바이트 내용(좌표/frame_id)까지는 검증하지 않는다 --
maro_test_peer에 PointCloud2 구독 모드가 없어서다(브리프 §남는 검증 공백).
"""
import math
import os
import sys
import time

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

# mayapy는 뷰포트가 없는 헤드리스 세션이라 MTimerMessage 콜백(발행 펌프)이
# Qt 이벤트 루프 없이는 한 번도 불리지 않는다. cmds.refresh(force=True)와
# maya.utils.processIdleEvents()는 둘 다 실측에서 이 큐를 건드리지 못했다 --
# test_bridge_pump.py가 같은 이유로 이미 이 우회를 쓰고 있고, 그 파일의
# 주석에 실측 근거가 남아 있다.
from PySide6.QtWidgets import QApplication  # noqa: E402

_qapp = QApplication.instance()

plugin = os.environ["MARO_PLUGIN_PATH"]
name = os.path.splitext(os.path.basename(plugin))[0]

cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)
# 각도 어트리뷰트(MFnUnitAttribute::kAngle)는 내부적으로 라디안이지만
# setAttr/getAttr은 기본적으로 UI 각도 단위(기본값 도)로 변환한다.
# 라디안으로 고정해야 아래 스캔 스펙 각도와 rotateX가 의도한 값이 된다.
cmds.currentUnit(angle="rad")

# 평평한 폴리곤 하나를 스캔 대상으로 놓는다 -- 레이가 확실히 맞을 위치.
# polyPlane은 XZ 평면에 놓이고 노멀이 월드 +Y다(정점 (+-5, 0, +-5)).
plane = cmds.polyPlane(name="scanTarget", width=10, height=10, subdivisionsX=1,
                       subdivisionsY=1)[0]

# createNode는 로케이터 파생 노드의 *셰이프*를 돌려주고 부모 트랜스폼은
# 따로 만든다(실측: 반환값 "testLidar"에는 translateY가 없고 부모가
# "|transform1"이다). 위치/회전은 그 부모에 걸어야 한다.
lidar = cmds.createNode("maroLidar", name="testLidar")
lidar_xform = cmds.listRelatives(lidar, parent=True, fullPath=True)[0]
cmds.setAttr(lidar_xform + ".translateY", 5)  # 평면 위 5 유닛.
# 레이 방향은 컴퓨트되는 로컬 방향 하나뿐이다: 수직/수평 샘플 1개에 각도 0
# -> RayPattern의 로컬 정면인 +Z. 그 +Z가 월드 -Y(평면 쪽)를 보게 하려면
# X축 기준 +90도다(+180도가 아니다 -- 180도는 +Z를 -Z로 보내 평면을 영영
# 빗나간다). 씬 각도 단위가 라디안이므로 pi/2를 그대로 넣는다.
cmds.setAttr(lidar_xform + ".rotateX", math.pi / 2.0)
cmds.setAttr(lidar + ".verticalSamples", 1)
cmds.setAttr(lidar + ".verticalMinAngle", 0)
cmds.setAttr(lidar + ".verticalMaxAngle", 0)
cmds.setAttr(lidar + ".horizontalSamples", 1)
cmds.setAttr(lidar + ".horizontalMinAngle", 0)
cmds.setAttr(lidar + ".horizontalMaxAngle", 0)
# polyPlane이 돌려주는 것은 트랜스폼이다(셰이프가 아니다). test_lidar_node.py가
# 이미 같은 방식으로 바인딩하므로 캡처 쪽이 트랜스폼을 셰이프로 풀어야 한다.
cmds.connectAttr(plane + ".message", lidar + ".targetMeshes[0]")


def wait_until(condition, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        _qapp.processEvents()
        if condition():
            return True
        time.sleep(0.05)
    return False


# 브리지가 켜진 채로 assert가 터지면 스레드가 살아남아 mayapy 좀비가 된다
# (test_bridge_pump.py의 M18 주석 참고). try/finally로 항상 내린다.
try:
    cmds.maroStartBridge("testRobot")

    drained_before = cmds.maroBridgeStats()[1]
    assert wait_until(lambda: cmds.maroBridgeStats()[1] > drained_before, timeout=20), (
        "drainedSampleCount never rose -- the lidar pipeline (capture, scan, "
        "hit, queue, drain) never produced a sample; "
        f"maroBridgeStats={cmds.maroBridgeStats()}"
    )
    print("lidar scan reached the publish queue OK")

    collected, drained, applied, ticks, pub_errors = cmds.maroBridgeStats()
    # 이 씬에는 maroAxis가 없다. collectedSampleCount는 축 전용 계수기이므로
    # 0이어야 하고, 그것이 위 drained 상승이 LiDAR에서만 왔다는 근거다.
    assert collected == 0, (
        "collectedSampleCount rose without any maroAxis in the scene -- the "
        f"drained count is no longer attributable to the lidar (stats={(collected, drained, applied, ticks, pub_errors)})"
    )
    assert pub_errors == 0, (
        "drainAndPublish() threw while publishing the lidar cloud "
        f"(stats={(collected, drained, applied, ticks, pub_errors)})"
    )
    print(f"lidar publish OK (drained={drained}, publishErrors={pub_errors})")

    cmds.maroStopBridge()
    cmds.file(new=True, force=True)
    cmds.unloadPlugin(name)
finally:
    # 위에서 정상적으로 언로드까지 끝났으면 아무 것도 하지 않는다.
    # assert가 터졌을 때만 브리지를 내리고 플러그인을 정리한다.
    if cmds.pluginInfo(name, query=True, loaded=True):
        cmds.maroStopBridge()
        cmds.file(new=True, force=True)
        cmds.unloadPlugin(name)

maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
