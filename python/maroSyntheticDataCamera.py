"""합성 데이터 렌더링에 쓸 카메라를 만들고 조회한다. 평범한 Maya camera에
커스텀 어트리뷰트(outputResolutionWidth/Height, outputDirectory)만 얹는다 --
새 C++ 노드 타입 없음(설계 스펙 §3). 초점거리/필름 백은 Maya 카메라가
이미 가진 기존 어트리뷰트를 그대로 쓴다 -- 중복 어트리뷰트를 새로 만들지
않는다."""
import maya.cmds as cmds

# 이 어트리뷰트가 있다는 것 자체가 "합성 데이터 카메라"라는 마커 역할을
# 한다 -- 별도 불리언 마커 어트리뷰트를 추가하지 않는다.
_MARKER_ATTR = "outputDirectory"


def createSyntheticDataCamera(name=None):
    """합성 데이터 카메라(트랜스폼+셰이프)를 만들고 트랜스폼의 풀패스를
    돌려준다."""
    cameraTransform, _cameraShape = cmds.camera(
        name=name if name else "maroSyntheticDataCam#")
    cameraTransform = cmds.ls(cameraTransform, long=True)[0]
    cmds.addAttr(cameraTransform, longName="outputResolutionWidth",
                 attributeType="long", defaultValue=1920)
    cmds.addAttr(cameraTransform, longName="outputResolutionHeight",
                 attributeType="long", defaultValue=1080)
    cmds.addAttr(cameraTransform, longName=_MARKER_ATTR, dataType="string")
    cmds.setAttr(cameraTransform + "." + _MARKER_ATTR, "", type="string")
    return cameraTransform


def listSyntheticDataCameras():
    """outputDirectory 어트리뷰트를 가진 카메라 트랜스폼을 전부 나열한다."""
    result = []
    for cameraShape in cmds.ls(type="camera", long=True) or []:
        parents = cmds.listRelatives(cameraShape, parent=True, fullPath=True)
        if not parents:
            continue
        transform = parents[0]
        if cmds.attributeQuery(_MARKER_ATTR, node=transform, exists=True):
            result.append(transform)
    return result
