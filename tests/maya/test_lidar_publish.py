"""maroLidar가 메쉬를 스캔해 실제로 발행 큐까지 도달하는지 종단으로
확인하고, rangeMin/rangeMax가 "미터"라는 것까지 못박는다.

maroBridgeStats()[5](drainedLidarScanCount)로 검증한다 -- 축 샘플과 섞이지
않는 LiDAR 전용 계수기다(최종 리뷰 Finding M1). 그 전제를 그냥 믿지 않고
maroBridgeStats()[0](collectedSampleCount, 축 전용 계수기)이 여전히 0인
것까지 함께 확인한다.

단위 의미(Finding C1): 씬은 cm로 고정하고 라이다를 평면 위 100 Maya
유닛(= 1 m)에 둔다. 이 거리는 기본 사거리 [0.1 m, 30 m] 안이지만, 만약
rangeMin/rangeMax가 미터가 아니라 Maya 유닛으로 그대로 쓰이면 tfar = 30
유닛 < 100 유닛이라 레이가 영영 평면에 닿지 않는다. 즉 아래 첫 번째
assert는 변환이 없으면 반드시 실패한다. 두 번째는 그 반대 방향이다:
rangeMax = 0.02 m = 2 유닛 < 100 유닛이므로 스캔이 멈춰야 한다 -- 사거리가
그냥 무시되고 있는 것이 아니라는 근거.

마지막으로 updateRate(Finding I3)가 실제로 지켜지는지도 확인한다.

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
# 선형 단위도 명시적으로 고정한다 -- 아래 거리 계산(100 유닛 = 1 m)이
# 사용자 환경설정에 따라 달라지면 이 테스트가 증명하는 것이 없어진다.
cmds.currentUnit(linear="cm")

# 평평한 폴리곤 하나를 스캔 대상으로 놓는다 -- 레이가 확실히 맞을 위치.
# polyPlane은 XZ 평면에 놓이고 노멀이 월드 +Y다(정점 (+-5, 0, +-5)).
plane = cmds.polyPlane(name="scanTarget", width=10, height=10, subdivisionsX=1,
                       subdivisionsY=1)[0]

# createNode는 로케이터 파생 노드의 *셰이프*를 돌려주고 부모 트랜스폼은
# 따로 만든다(실측: 반환값 "testLidar"에는 translateY가 없고 부모가
# "|transform1"이다). 위치/회전은 그 부모에 걸어야 한다.
lidar = cmds.createNode("maroLidar", name="testLidar")
lidar_xform = cmds.listRelatives(lidar, parent=True, fullPath=True)[0]
# 평면 위 100 Maya 유닛 = 1 m. 기본 rangeMin(0.1 m)보다 멀고 기본
# rangeMax(30 m)보다 가깝다 -- 미터로 해석할 때만 그렇다.
LIDAR_HEIGHT_UNITS = 100
cmds.setAttr(lidar_xform + ".translateY", LIDAR_HEIGHT_UNITS)
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

LIDAR_SCANS = 5   # maroBridgeStats()의 drainedLidarScanCount 자리


def wait_until(condition, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        _qapp.processEvents()
        if condition():
            return True
        time.sleep(0.05)
    return False


def pump(seconds):
    """조건 없이 정해진 시간 동안 펌프를 돌린다. "아무 일도 일어나지 않는다"
    를 확인할 때는 기다릴 조건이 없으므로 이 형태가 필요하다."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        _qapp.processEvents()
        time.sleep(0.05)


# 브리지가 켜진 채로 assert가 터지면 스레드가 살아남아 mayapy 좀비가 된다
# (test_bridge_pump.py의 M18 주석 참고). try/finally로 항상 내린다.
try:
    cmds.maroStartBridge("testRobot")

    scans_before = cmds.maroBridgeStats()[LIDAR_SCANS]
    assert wait_until(lambda: cmds.maroBridgeStats()[LIDAR_SCANS] > scans_before,
                      timeout=20), (
        "drainedLidarScanCount never rose -- the lidar pipeline (capture, scan, "
        "hit, queue, drain) never produced a sample. Note the target sits "
        f"{LIDAR_HEIGHT_UNITS} Maya units (1 m) away with the default range of "
        "[0.1, 30] metres, so this also fails if rangeMin/rangeMax are being "
        "consumed as raw Maya units instead of metres (tfar would be 30 units, "
        f"short of the target); maroBridgeStats={cmds.maroBridgeStats()}"
    )
    print("lidar scan reached the publish queue OK")

    collected, drained, applied, ticks, pub_errors, lidar_scans = cmds.maroBridgeStats()
    # 이 씬에는 maroAxis가 없다. collectedSampleCount는 축 전용 계수기이므로
    # 0이어야 하고, drainedSampleCount(축 드레인 전용)도 0이어야 한다 --
    # 그것이 위 상승이 LiDAR에서만 왔다는 근거다.
    assert collected == 0, (
        "collectedSampleCount rose without any maroAxis in the scene "
        f"(stats={cmds.maroBridgeStats()})"
    )
    assert drained == 0, (
        "drainedSampleCount (axis-only) rose without any maroAxis in the scene "
        f"(stats={cmds.maroBridgeStats()})"
    )
    assert pub_errors == 0, (
        "drainAndPublish() threw while publishing the lidar cloud "
        f"(stats={cmds.maroBridgeStats()})"
    )
    print(f"lidar publish OK (lidarScans={lidar_scans}, publishErrors={pub_errors})")

    # --- Finding C1: rangeMin/rangeMax는 미터다 -------------------------
    # 0.02 m = 2 Maya 유닛. 목표는 100 유닛 떨어져 있으므로 사거리 밖이고,
    # 스캔은 히트를 하나도 못 만들어 큐에 아무 것도 넣지 않는다.
    cmds.setAttr(lidar + ".rangeMax", 0.02)
    pump(1.5)   # 이미 큐에 들어가 있던 스캔이 전부 드레인될 때까지 흘려보낸다.
    quiet_baseline = cmds.maroBridgeStats()[LIDAR_SCANS]
    pump(3.0)
    assert cmds.maroBridgeStats()[LIDAR_SCANS] == quiet_baseline, (
        "rangeMax = 0.02 metres (= 2 Maya units) should put the target at "
        f"{LIDAR_HEIGHT_UNITS} units out of range, but scans kept arriving "
        f"(baseline={quiet_baseline}, stats={cmds.maroBridgeStats()})"
    )
    print("out-of-range rangeMax silences the lidar OK")

    # 되돌리면 다시 잡혀야 한다 -- 위 침묵이 "사거리 밖"이 아니라 "노드가
    # 죽었다"였을 가능성을 배제한다.
    cmds.setAttr(lidar + ".rangeMax", 30.0)
    resume_baseline = cmds.maroBridgeStats()[LIDAR_SCANS]
    assert wait_until(lambda: cmds.maroBridgeStats()[LIDAR_SCANS] > resume_baseline,
                      timeout=20), (
        "restoring rangeMax to 30 metres did not bring the scans back "
        f"(baseline={resume_baseline}, stats={cmds.maroBridgeStats()})"
    )
    print("restored rangeMax resumes scanning OK")

    # --- Finding I3: updateRate(Hz)를 실제로 지킨다 ----------------------
    # 0.05 Hz = 20초에 한 번. 방금 스캔이 있었으므로 다음 스캔은 20초 뒤가
    # 되어야 하고, 아래 3초 창에는 하나도 오면 안 된다. 스로틀이 없으면
    # (이 수정 이전처럼) 펌프 틱마다 오므로 수십 개가 들어온다.
    # 초당 몇 번인지를 세지 않는 이유: 헤드리스 mayapy의 MTimerMessage는
    # Qt 이벤트 루프 속도에 좌우돼 30Hz가 안 나온다(실측 ~12Hz) -- 비율
    # 기반 단언은 그래서 흔들린다. "20초 안에는 0개"는 흔들리지 않는다.
    cmds.setAttr(lidar + ".updateRate", 0.05)
    pump(1.0)   # 직전 설정(10Hz)으로 이미 시작된 스캔을 흘려보낸다.
    throttle_baseline = cmds.maroBridgeStats()[LIDAR_SCANS]
    pump(3.0)
    assert cmds.maroBridgeStats()[LIDAR_SCANS] == throttle_baseline, (
        "updateRate = 0.05 Hz means one scan per 20 s, but more scans arrived "
        f"within a 3 s window (baseline={throttle_baseline}, "
        f"stats={cmds.maroBridgeStats()})"
    )
    print("updateRate throttling OK")

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
