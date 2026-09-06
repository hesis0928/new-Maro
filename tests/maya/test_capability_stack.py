"""스택 합성: rotation이 값을 만들고 limit들이 순차적으로 클램프한다."""
import math
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

# maroRotation.angle, maroLimit's min/max, and maroAxis.position are all
# MFnUnitAttribute::kAngle now, so cmds.setAttr/getAttr read and write them
# in Maya's *current UI angle unit* (degrees by default), not raw radians.
# Every literal below was written in radians (matching the compute()
# internals and the pre-conversion plain-double behavior), so pin the
# session's working angle unit to radians once, up front, instead of
# converting at every call site. cmds.currentUnit() is the only per-call
# unit-control surface cmds exposes for angle attributes in this Maya
# version -- setAttr's `type="doubleAngle"` is rejected outright ("not the
# name of a recognized type"). The unit contract test near the end of this
# file flips currentUnit to degrees deliberately, to prove the UI-facing
# conversion itself; everywhere else here stays in radians.
cmds.currentUnit(angle="rad")

axis = cmds.createNode("maroAxis", name="axis1")
rot = cmds.createNode("maroRotation", name="rot1")

cmds.connectAttr(rot + ".capabilityOut", axis + ".capabilityIn[0]")
cmds.setAttr(rot + ".angle", 1.0)
assert abs(cmds.getAttr(axis + ".position") - 1.0) < 1e-9, "rotation did not drive position"
print("rotation OK")

# limit을 얹으면 클램프된다. 축 보정 기본값은 Y이므로 Y 리밋을 건다.
lim = cmds.createNode("maroLimit", name="lim1")
cmds.setAttr(lim + ".axisDirection", 0, 1, 0, type="double3")
cmds.setAttr(lim + ".min", -0.5)
cmds.setAttr(lim + ".max", 0.5)
cmds.connectAttr(lim + ".capabilityOut", axis + ".capabilityIn[1]")

assert abs(cmds.getAttr(axis + ".position") - 0.5) < 1e-9, "limit did not clamp"
print("limit OK")

# 두 번째 limit이 더 좁으면 그쪽이 이긴다 (순차 클램프).
lim2 = cmds.createNode("maroLimit", name="lim2")
cmds.setAttr(lim2 + ".axisDirection", 0, 1, 0, type="double3")
cmds.setAttr(lim2 + ".min", -0.25)
cmds.setAttr(lim2 + ".max", 0.25)
cmds.connectAttr(lim2 + ".capabilityOut", axis + ".capabilityIn[2]")

assert abs(cmds.getAttr(axis + ".position") - 0.25) < 1e-9, "second limit did not clamp"
print("stacked limits OK")

# 스택은 노드 종류가 아니라 인덱스 순서로 평가된다.
# 리밋을 회전보다 낮은 인덱스에 두면, 리밋이 먼저 돌아 0을 클램프한 뒤
# 회전이 그 값을 덮어쓴다. 따라서 최종값은 클램프되지 않은 각도여야 한다.
# capType 별로 묶어 평가하는 구현이라면 리밋이 나중에 걸려 이 단언이 깨진다.
axisOrder = cmds.createNode("maroAxis", name="axisOrder")
limFirst = cmds.createNode("maroLimit", name="limFirst")
rotSecond = cmds.createNode("maroRotation", name="rotSecond")

cmds.setAttr(limFirst + ".axisDirection", 0, 1, 0, type="double3")
cmds.setAttr(limFirst + ".min", -0.1)
cmds.setAttr(limFirst + ".max", 0.1)

cmds.connectAttr(limFirst + ".capabilityOut", axisOrder + ".capabilityIn[0]")
cmds.connectAttr(rotSecond + ".capabilityOut", axisOrder + ".capabilityIn[1]")
cmds.setAttr(rotSecond + ".angle", 1.0)

ordered = cmds.getAttr(axisOrder + ".position")
assert abs(ordered - 1.0) < 1e-9, \
    f"stack must evaluate in index order, not grouped by capType (got {ordered})"
print("index ordering OK")

# controlMode 가 ROS 면 기준값이 rotation 이 아니라 rosCommand 에서 온다.
# 리밋은 두 모드 모두에 걸린다.
axisRos = cmds.createNode("maroAxis", name="axisRos")
rotRos = cmds.createNode("maroRotation", name="rotRos")
cmds.connectAttr(rotRos + ".capabilityOut", axisRos + ".capabilityIn[0]")
cmds.setAttr(rotRos + ".angle", 0.3)
cmds.setAttr(axisRos + ".rosCommand", 0.9)

assert abs(cmds.getAttr(axisRos + ".position") - 0.3) < 1e-9, \
    "Manual mode must use the rotation node, not rosCommand"

cmds.setAttr(axisRos + ".controlMode", 1)
assert abs(cmds.getAttr(axisRos + ".position") - 0.9) < 1e-9, \
    "ROS mode must use rosCommand, not the rotation node"
print("control mode source OK")

limRos = cmds.createNode("maroLimit", name="limRos")
cmds.setAttr(limRos + ".axisDirection", 0, 1, 0, type="double3")
cmds.setAttr(limRos + ".min", -0.5)
cmds.setAttr(limRos + ".max", 0.5)
cmds.connectAttr(limRos + ".capabilityOut", axisRos + ".capabilityIn[1]")

assert abs(cmds.getAttr(axisRos + ".position") - 0.5) < 1e-9, \
    "limits must clamp a ROS-driven value too"
print("limit clamps in ros mode OK")

# 센서 노드는 구동값에 기여하지 않지만, 등록되고 올바른 capType 을 실어야 한다.
axisSensor = cmds.createNode("maroAxis", name="axisSensor")
rotSensor = cmds.createNode("maroRotation", name="rotSensor")
sensorDir = cmds.createNode("maroSensorDirection", name="sensorDir")
sensorRange = cmds.createNode("maroSensorRange", name="sensorRange")

cmds.connectAttr(rotSensor + ".capabilityOut", axisSensor + ".capabilityIn[0]")
cmds.connectAttr(sensorDir + ".capabilityOut", axisSensor + ".capabilityIn[1]")
cmds.connectAttr(sensorRange + ".capabilityOut", axisSensor + ".capabilityIn[2]")
cmds.setAttr(rotSensor + ".angle", 0.6)

assert abs(cmds.getAttr(axisSensor + ".position") - 0.6) < 1e-9, \
    "sensor capabilities must not alter the driving value"
assert cmds.getAttr(sensorDir + ".capabilityOut.capType") == 2, "sensorDirection capType"
assert cmds.getAttr(sensorRange + ".capabilityOut.capType") == 3, "sensorRange capType"
print("sensor nodes OK")

# 비활성 축은 구동값을 내지 않는다.
cmds.setAttr(axis + ".enabled", False)
assert abs(cmds.getAttr(axis + ".position")) < 1e-9, "disabled axis must output zero"
print("disabled OK")

# maroTranslation: 회전과 대칭인 직선 구동값. 단위는 센티미터로 고정해
# 둔다(회전 절이 currentUnit(angle="rad")로 고정한 것과 같은 이유).
cmds.currentUnit(linear="cm")
axisLinear = cmds.createNode("maroAxis", name="axisLinear")
trans = cmds.createNode("maroTranslation", name="trans1")
cmds.connectAttr(trans + ".capabilityOut", axisLinear + ".capabilityIn[0]")
assert cmds.getAttr(trans + ".capabilityOut.capType") == 4, "translation capType"
cmds.setAttr(trans + ".distance", 25.0)
outVal = cmds.getAttr(trans + ".capabilityOut.capValue")
assert abs(outVal - 25.0) < 1e-9, f"translation capValue must carry centimeters (got {outVal})"
print("translation node OK")

# maroTranslationLimit: maroLimit과 대칭인 직선 클램프.
transLim = cmds.createNode("maroTranslationLimit", name="transLim1")
cmds.setAttr(transLim + ".axisDirection", 0, 1, 0, type="double3")
cmds.setAttr(transLim + ".min", -5.0)
cmds.setAttr(transLim + ".max", 5.0)
assert cmds.getAttr(transLim + ".capabilityOut.capType") == 5, "translationLimit capType"
minAny = cmds.getAttr(transLim + ".capabilityOut.capMin")[0][0]
maxAny = cmds.getAttr(transLim + ".capabilityOut.capMax")[0][0]
assert abs(minAny - (-5.0)) < 1e-9 and abs(maxAny - 5.0) < 1e-9, \
    f"translationLimit min/max must carry centimeters, broadcast to every component (got {minAny}, {maxAny})"
print("translationLimit node OK")

# maroCoupling: ratio/offset 경로 (곡선 없음).
# 소스는 설계가 문서화한 경로 -- 다른 "축"의 outValue(=position, kAngle) --
# 로 연결한다. maroRotation의 capabilityOut.capValue(평범한 double)를 직접
# 꽂으면 안 된다: 아래 C-1 절에서 실측했듯 Maya가 그 방향에도
# unitConversion(도->라디안, pi/180)을 끼워 넣는다.
couplingSrcAxis = cmds.createNode("maroAxis", name="couplingSourceAxis")
coupling = cmds.createNode("maroCoupling", name="coupling1")
sourceRot = cmds.createNode("maroRotation", name="couplingSource")
cmds.connectAttr(sourceRot + ".capabilityOut", couplingSrcAxis + ".capabilityIn[0]")
cmds.setAttr(sourceRot + ".angle", 1.0)
cmds.connectAttr(couplingSrcAxis + ".position", coupling + ".sourceValue")
cmds.setAttr(coupling + ".ratio", 2.0)
cmds.setAttr(coupling + ".offset", 0.5)
capValue = cmds.getAttr(coupling + ".capabilityOut.capValue")
assert abs(capValue - (1.0 * 2.0 + 0.5)) < 1e-9, f"coupling ratio/offset math wrong (got {capValue})"
assert cmds.getAttr(coupling + ".capabilityOut.capType") == 6, "coupling default capType (angular)"
print("coupling ratio/offset OK")

# outputIsLinear가 capType을 7로 바꾼다.
cmds.setAttr(coupling + ".outputIsLinear", True)
assert cmds.getAttr(coupling + ".capabilityOut.capType") == 7, "coupling linear capType"
print("coupling outputIsLinear OK")

# 곡선이 2점 이상이면 ratio/offset을 대체한다. 점: (0,0), (1,10), (2,10)
# -- 0~1 구간은 기울기 10, 1~2 구간은 평평(리밋처럼 동작).
cmds.setAttr(coupling + ".curvePoints[0].curveInput", 0.0)
cmds.setAttr(coupling + ".curvePoints[0].curveOutput", 0.0)
cmds.setAttr(coupling + ".curvePoints[1].curveInput", 1.0)
cmds.setAttr(coupling + ".curvePoints[1].curveOutput", 10.0)
cmds.setAttr(coupling + ".curvePoints[2].curveInput", 2.0)
cmds.setAttr(coupling + ".curvePoints[2].curveOutput", 10.0)

cmds.setAttr(sourceRot + ".angle", 0.5)   # 0~1 구간 중간
mid = cmds.getAttr(coupling + ".capabilityOut.capValue")
assert abs(mid - 5.0) < 1e-9, f"curve interpolation at midpoint wrong (got {mid})"

cmds.setAttr(sourceRot + ".angle", 1.5)   # 1~2 구간(평평)
plateau = cmds.getAttr(coupling + ".capabilityOut.capValue")
assert abs(plateau - 10.0) < 1e-9, f"curve interpolation on plateau wrong (got {plateau})"

cmds.setAttr(sourceRot + ".angle", 5.0)   # 정의역 밖 -- 외삽하지 않고 끝점 고정
clamped = cmds.getAttr(coupling + ".capabilityOut.capValue")
assert abs(clamped - 10.0) < 1e-9, f"out-of-domain must clamp to last point, not extrapolate (got {clamped})"
print("coupling curve interpolation OK")

# maroAxis가 translation을 outValueLinear로 라우팅하고, driveIsLinear가
# 그것을 알린다. 기존 rotation 경로(outValue)는 회귀 없이 그대로 유지돼야
# 한다 -- axis(맨 처음 만든 rotation 전용 축)로 재확인한다.
assert cmds.getAttr(axis + ".driveIsLinear") is False, "rotation axis must report driveIsLinear=False"
assert abs(cmds.getAttr(axis + ".positionLinear")) < 1e-9, "rotation axis outValueLinear must stay 0"
print("rotation axis regression (driveIsLinear/positionLinear) OK")

axisTrans = cmds.createNode("maroAxis", name="axisTrans")
transDrive = cmds.createNode("maroTranslation", name="transDrive1")
cmds.connectAttr(transDrive + ".capabilityOut", axisTrans + ".capabilityIn[0]")
cmds.setAttr(transDrive + ".distance", 12.5)
assert cmds.getAttr(axisTrans + ".driveIsLinear") is True, "translation axis must report driveIsLinear=True"
posLinear = cmds.getAttr(axisTrans + ".positionLinear")
assert abs(posLinear - 12.5) < 1e-9, f"translation axis positionLinear wrong (got {posLinear})"
assert abs(cmds.getAttr(axisTrans + ".position")) < 1e-9, "translation axis outValue(angular) must stay 0"
print("translation axis routing OK")

# translationLimit이 직선 구동값을 클램프한다.
transLimDrive = cmds.createNode("maroTranslationLimit", name="transLimDrive1")
cmds.setAttr(transLimDrive + ".axisDirection", 0, 1, 0, type="double3")
cmds.setAttr(transLimDrive + ".min", -5.0)
cmds.setAttr(transLimDrive + ".max", 5.0)
cmds.connectAttr(transLimDrive + ".capabilityOut", axisTrans + ".capabilityIn[1]")
clampedLinear = cmds.getAttr(axisTrans + ".positionLinear")
assert abs(clampedLinear - 5.0) < 1e-9, f"translationLimit did not clamp (got {clampedLinear})"
print("translationLimit clamp OK")

# coupling-선형이 다른 축의 outValue를 소스로 받아 axis를 직선 구동한다.
axisCoupled = cmds.createNode("maroAxis", name="axisCoupled")
couplingDrive = cmds.createNode("maroCoupling", name="couplingDrive1")
cmds.setAttr(couplingDrive + ".outputIsLinear", True)
cmds.setAttr(couplingDrive + ".ratio", 3.0)
cmds.setAttr(couplingDrive + ".sourceIsLinear", True)
cmds.connectAttr(axisTrans + ".positionLinear", couplingDrive + ".sourceValueLinear")
cmds.connectAttr(couplingDrive + ".capabilityOut", axisCoupled + ".capabilityIn[0]")
assert cmds.getAttr(axisCoupled + ".driveIsLinear") is True, "coupling-linear axis must report driveIsLinear=True"
coupledLinear = cmds.getAttr(axisCoupled + ".positionLinear")
assert abs(coupledLinear - 5.0 * 3.0) < 1e-9, f"coupling-linear routing wrong (got {coupledLinear})"
print("coupling-linear axis routing OK")

# 리뷰 재검증 Minor 2: 위 coupling-linear 테스트는 currentUnit(linear="cm")
# 아래에서 돌아서 변환 계수가 우연히 1.0이다 -- 각도 쪽 C-1 회귀(위,
# currentUnit(angle="deg"))와 같은 이유로, cm이 아닌 다른 선형 단위에서
# 다시 확인해야 "가려진 통과"가 아니라는 게 증명된다.
prevLinearUnit = cmds.currentUnit(query=True, linear=True)
cmds.currentUnit(linear="m")
axisTransM = cmds.createNode("maroAxis", name="axisTransM")
transM = cmds.createNode("maroTranslation", name="transM1")
cmds.connectAttr(transM + ".capabilityOut", axisTransM + ".capabilityIn[0]")
cmds.setAttr(transM + ".distance", 0.5)          # 미터 -- 내부적으로 50 센티미터
axisCoupledM = cmds.createNode("maroAxis", name="axisCoupledM")
couplingFromAxisM = cmds.createNode("maroCoupling", name="couplingFromAxisM1")
cmds.setAttr(couplingFromAxisM + ".outputIsLinear", True)
cmds.setAttr(couplingFromAxisM + ".sourceIsLinear", True)
cmds.setAttr(couplingFromAxisM + ".ratio", 2.0)
cmds.connectAttr(axisTransM + ".positionLinear", couplingFromAxisM + ".sourceValueLinear")
cmds.connectAttr(couplingFromAxisM + ".capabilityOut", axisCoupledM + ".capabilityIn[0]")
# positionLinear는 실제 kDistance 어트리뷰트라 getAttr이 "현재 UI 단위"로
# 보여준다 -- 내부 저장(센티미터)과 비교하려면 먼저 단위를 되돌려야 한다.
# 위쪽 각도 회귀 테스트가 capabilityOut.capValue(평범한 double, UI 단위와
# 무관)를 읽어서 이 함정을 피해 간 것과 달리, 여기는 진짜 unit-typed
# 출력을 읽으므로 이 순서가 중요하다(실측으로 처음에 놓쳐서 "got 1.0,
# expected 100.0"으로 실패하는 걸 직접 봤다 -- 0.5m UI 표시값의 2배였다).
cmds.currentUnit(linear=prevLinearUnit)
coupledM = cmds.getAttr(axisCoupledM + ".positionLinear")
assert abs(coupledM - 50.0 * 2.0) < 1e-9, \
    ("axis outValueLinear -> coupling.sourceValueLinear must stay in centimeters under a "
     f"non-centimeter UI linear unit (got {coupledM}, expected 100.0)")
print("coupling-linear axis routing under non-cm UI unit OK")

# 리뷰 Finding C-1 회귀: 설계가 문서화한 연결(다른 축의 outValue ->
# coupling.sourceValue)을 "기본 UI 단위(도)"에서 그대로 해 본다. sourceValue가
# 평범한 double이던 시절엔 Maya가 unitConversion을 끼워 넣어 ~57.3배로
# 부풀었다. 단위를 라디안으로 고정해 버그를 감추면 안 되므로 여기서는
# 일부러 도(degrees)로 둔다.
prevAngleUnit = cmds.currentUnit(query=True, angle=True)
cmds.currentUnit(angle="deg")
axisRotSrc = cmds.createNode("maroAxis", name="axisRotSrcC1")
rotSrcC1 = cmds.createNode("maroRotation", name="rotSrcC1")
cmds.connectAttr(rotSrcC1 + ".capabilityOut", axisRotSrc + ".capabilityIn[0]")
cmds.setAttr(rotSrcC1 + ".angle", 90.0)          # 도 -- 내부적으로 pi/2 라디안
couplingFromAxis = cmds.createNode("maroCoupling", name="couplingFromAxisC1")
cmds.setAttr(couplingFromAxis + ".ratio", 2.0)
cmds.setAttr(couplingFromAxis + ".offset", 0.0)
# sourceIsLinear는 기본값 False -- 각도 슬롯을 쓴다.
cmds.connectAttr(axisRotSrc + ".position", couplingFromAxis + ".sourceValue")
c1Value = cmds.getAttr(couplingFromAxis + ".capabilityOut.capValue")
assert abs(c1Value - (math.pi / 2.0) * 2.0) < 1e-9, \
    ("axis outValue -> coupling.sourceValue must stay in radians under a degrees UI unit "
     f"(got {c1Value}, expected {math.pi})")
assert cmds.getAttr(couplingFromAxis + ".capabilityOut.capType") == 6, \
    "angular-source coupling must still report capType 6"

# 실측 결과 문서화(characterization): "평범한 double 소스 -> 단위형
# 목적지"는 안전할 것이라는 예상과 달리, Maya는 이 방향에도
# unitConversion을 끼워 넣는다. 평범한 double을 "UI 단위(도)"로 해석해
# pi/180을 곱해 라디안으로 바꿔 버린다. 즉 maroRotation의
# capabilityOut.capValue(생 라디안)를 coupling.sourceValue에 직접 꽂으면
# 값이 ~57.3배 작아진다. 그래서 위쪽 ratio/offset·곡선 테스트도 축의
# outValue를 경유하도록 바꿨다. 이 단언은 그 제약이 실제로 존재함을
# 고정해 둔다 -- 언젠가 Maya가 동작을 바꾸면 여기서 먼저 깨진다.
rotPlainSrc = cmds.createNode("maroRotation", name="rotPlainSrcC1")
cmds.setAttr(rotPlainSrc + ".angle", 90.0)       # 도 -- 내부적으로 pi/2 라디안
couplingPlain = cmds.createNode("maroCoupling", name="couplingPlainC1")
cmds.setAttr(couplingPlain + ".ratio", 1.0)
cmds.connectAttr(rotPlainSrc + ".capabilityOut.capValue", couplingPlain + ".sourceValue")
plainValue = cmds.getAttr(couplingPlain + ".capabilityOut.capValue")
assert abs(plainValue - (math.pi / 2.0) * (math.pi / 180.0)) < 1e-9, \
    ("a plain-double source into a kAngle destination is NOT conversion-free: Maya reads "
     f"the double as degrees and multiplies by pi/180 (got {plainValue})")
cmds.currentUnit(angle=prevAngleUnit)
print("coupling angular-source unit safety (C-1) OK")

# §3 상호배타 규칙의 DG 레벨 방어: rotation과 translation을 같은 축에
# 억지로(스크립트로, 커맨드 검증을 우회해) 연결해도 죽지 않고 "먼저 나온
# 것이 이긴다"로 조용히 처리된다.
axisConflict = cmds.createNode("maroAxis", name="axisConflict")
rotConflict = cmds.createNode("maroRotation", name="rotConflict")
transConflict = cmds.createNode("maroTranslation", name="transConflict")
cmds.setAttr(rotConflict + ".angle", 0.4)
cmds.setAttr(transConflict + ".distance", 40.0)
cmds.connectAttr(rotConflict + ".capabilityOut", axisConflict + ".capabilityIn[0]")
cmds.connectAttr(transConflict + ".capabilityOut", axisConflict + ".capabilityIn[1]")
assert cmds.getAttr(axisConflict + ".driveIsLinear") is False, \
    "first primary driver (index 0, rotation) must win over a later conflicting one"
assert abs(cmds.getAttr(axisConflict + ".position") - 0.4) < 1e-9, \
    "conflicting stack must still drive from the first primary driver"
print("primary-driver conflict defensive handling OK")

# 단위 계약: MFnUnitAttribute는 데이터블록(항상 라디안)과 cmds/Attribute
# Editor 표면(현재 UI 각도 단위, 기본 도) 사이를 변환한다. 그 변환이 실제로
# 걸려 있는지 끝까지 증명한다 -- rotation을 180 "도"로 설정하고 axis의
# position을 "라디안"으로 읽어 pi가 나오는지 확인한다. cmds.currentUnit()로
# 각 cmds.setAttr/getAttr 호출이 어느 단위로 말하는지 명시적으로 통제한다.
axisUnit = cmds.createNode("maroAxis", name="axisUnitContract")
rotUnit = cmds.createNode("maroRotation", name="rotUnitContract")
cmds.connectAttr(rotUnit + ".capabilityOut", axisUnit + ".capabilityIn[0]")

cmds.currentUnit(angle="deg")
cmds.setAttr(rotUnit + ".angle", 180.0)

cmds.currentUnit(angle="rad")
outRad = cmds.getAttr(axisUnit + ".position")
assert abs(outRad - math.pi) < 1e-9, \
    f"180 degrees in must read back as pi radians out (got {outRad})"
print("unit contract (180 deg in -> pi rad out) OK")

# Maya는 커스텀 노드 인스턴스가 씬에 남아 있으면 플러그인을 언로드하지 않는다.
cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
