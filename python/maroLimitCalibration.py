"""Limit/TranslationLimit이 공유하는 뷰포트 캘리브레이션 엔진(설계 스펙
2026-09-07 §5). 이 파일의 위쪽 절(axisDirectionFromPoints/
axisBasisEulerXYZ/expandRange/mayaDirectionToRos)은 Maya 씬 상태에
의존하지 않는 순수 함수다 -- maya.api.OpenMaya(om2)는 행렬/벡터 연산
라이브러리로만 쓴다(python/maroUrdfExport.py의 computeRelativeOrigin과
같은 성격). 아래쪽 절(뷰포트 리그/HUD)은 실제 Maya 씬과 Qt에 의존한다.
"""
import math

import maya.api.OpenMaya as om2


def axisDirectionFromPoints(pointA, pointB):
    """pointA/pointB: (x,y,z) 튜플, 뷰포트에서 클릭한 두 월드 좌표점.
    pointA -> pointB 방향의 정규화 벡터를 돌려준다. 두 점이 같으면(길이 0)
    방향을 정의할 수 없으므로 ValueError."""
    vec = om2.MVector(pointB[0] - pointA[0], pointB[1] - pointA[1], pointB[2] - pointA[2])
    length = vec.length()
    if length < 1e-9:
        raise ValueError("axisDirectionFromPoints: pointA and pointB must differ")
    unit = vec.normal()
    return (unit.x, unit.y, unit.z)


def axisBasisEulerXYZ(axisDirection):
    """axisDirection(정규화된 (x,y,z))을 로컬 Z로 갖는 정규직교 기저를
    구성해 (rx, ry, rz) 오일러 각(도, XYZ 고정축 순서)으로 돌려준다.
    X/Y 축의 구체적인 방향은 임의(자유도 1개짜리 계 -- 회전/이동 매니퍼레이터가
    로컬 Z 축 하나만 쓰므로 X/Y가 어느 쪽을 향하든 캘리브레이션 결과에
    영향이 없다)이지만, 항상 같은 규칙(월드 업 벡터 기준)으로 결정해
    호출마다 결과가 안정적이도록 한다. axisDirection이 월드 업과 거의
    평행하면(짐벌 특이점) 월드 X를 참조 벡터로 대신 쓴다."""
    z = om2.MVector(*axisDirection).normal()
    worldUp = om2.MVector(0.0, 1.0, 0.0)
    reference = worldUp if abs(z * worldUp) < 0.999 else om2.MVector(1.0, 0.0, 0.0)
    x = (reference ^ z).normal()   # cross product, MVector의 ^ 연산자
    y = (z ^ x).normal()

    m = om2.MMatrix((
        x.x, x.y, x.z, 0.0,
        y.x, y.y, y.z, 0.0,
        z.x, z.y, z.z, 0.0,
        0.0, 0.0, 0.0, 1.0,
    ))
    euler = om2.MTransformationMatrix(m).rotation(asQuaternion=False)
    euler = euler.reorder(om2.MEulerRotation.kXYZ)
    return (math.degrees(euler.x), math.degrees(euler.y), math.degrees(euler.z))


def expandRange(currentMin, currentMax, sample):
    """collect 한 번: sample을 currentMin/currentMax 범위에 편입시킨
    (newMin, newMax)를 돌려준다. 범위 안의 샘플은 아무 효과가 없다."""
    return (min(currentMin, sample), max(currentMax, sample))


def mayaDirectionToRos(direction):
    """(x,y,z) 방향 벡터를 ROS(REP-103) 프레임으로. 위치 변환
    (maroMayaToRos)과 같은 축 재배치 (x,y,z)->(x,-z,y)이지만, 방향
    벡터는 단위 없는 순수 방향이므로 씬 단위 스케일을 적용하지 않는다."""
    x, y, z = direction
    return (x, -z, y)
