"""Arnold(MtoA)로 beauty/depth/normal AOV를 배치 렌더링하고 캘리브레이션
메타데이터를 JSON으로 저장한다. 실제 렌더링(renderSyntheticFrame)은
Arnold 라이선스+렌더 컨텍스트가 필요해 mayapy 배치로 자동화할 수 없다
(설계 스펙 §9) -- 파일 경로 구성(outputPaths)과 캘리브레이션 딕셔너리
빌드(buildCalibrationDict)만 Arnold와 무관한 순수/Maya-only 함수로 분리해
mayapy로 검증한다."""
import json
import os

import maya.api.OpenMaya as om2
import maya.cmds as cmds


def outputPaths(cameraTransform, frame, outputDir):
    """이 카메라/프레임의 beauty/depth/normal/calibration 파일 경로를
    돌려준다(파일을 만들지 않는다 -- 순수 함수)."""
    cameraName = cameraTransform.split("|")[-1]
    stem = "{}_{:04d}".format(cameraName, int(frame))
    return {
        "beauty": os.path.join(outputDir, stem + "_beauty.png"),
        "depth": os.path.join(outputDir, stem + "_depth.exr"),
        "normal": os.path.join(outputDir, stem + "_normal.exr"),
        "calibration": os.path.join(outputDir, stem + "_camera.json"),
    }


def buildCalibrationDict(cameraTransform, frame):
    """카메라 내부/외부 파라미터를 딕셔너리로 만든다(파일에 쓰지 않는다 --
    Maya 호출은 있지만 Arnold는 건드리지 않는다)."""
    cameraShape = cmds.listRelatives(cameraTransform, shapes=True, fullPath=True)[0]
    width = cmds.getAttr(cameraTransform + ".outputResolutionWidth")
    height = cmds.getAttr(cameraTransform + ".outputResolutionHeight")
    focalLength = cmds.getAttr(cameraShape + ".focalLength")
    hFilmAperture = cmds.getAttr(cameraShape + ".horizontalFilmAperture")
    vFilmAperture = cmds.getAttr(cameraShape + ".verticalFilmAperture")

    sel = om2.MSelectionList()
    sel.add(cameraTransform)
    worldMatrix = sel.getDagPath(0).inclusiveMatrix()
    # MMatrix isn't callable as matrix(r, c) on this Maya version's API 2.0
    # (verified: TypeError: 'OpenMaya.MMatrix' object is not callable) --
    # it's iterable/indexable instead, yielding its 16 elements in row-major
    # order (confirmed by comparing list(m) against a matrix built from a
    # known flat list).
    matrixFlat = list(worldMatrix)

    return {
        "frame": int(frame),
        "resolutionWidth": width,
        "resolutionHeight": height,
        "focalLength": focalLength,
        "horizontalFilmAperture": hFilmAperture,
        "verticalFilmAperture": vFilmAperture,
        "worldMatrix": matrixFlat,
    }


def _wireAovToDedicatedDriver(aovInterface, aovName, driverName, filePath, fileFormat):
    """`aovName` (예: "Z", "N")을 이 AOV 전용의 `aiAOVDriver` 노드에 연결해
    독립된 파일로 저장되게 한다.

    이 함수의 API는 이 태스크(Task 3)에서 실제 설치된 MtoA(Arnold 7.4.2.0,
    MtoA 5.5.2, mayapy 배치로 라이선스 워터마크는 붙지만 렌더 자체는 성공)를
    대상으로 직접 실측 검증했다 -- 계획서(브리프) 작성 시점엔 이 API가
    확인되지 않은 상태였다:

    - `mtoa.aovs.AOVInterface.getAOVNode(aovName, layerName)`은 브리프의
      추측과 달리 `layerName`이 **필수** 위치 인자다(레이어를 안 쓰면
      `None`을 명시적으로 넘긴다) -- 실측: 누락 시
      `TypeError: getAOVNode() missing 1 required positional argument`.
    - `addAOV(aovName)`이 만드는 `aiAOV` 노드는 기본적으로
      `outputs[0].driver`가 `defaultArnoldDriver`(단일 공용 드라이버)에
      연결된다 -- beauty/depth/normal을 각각 다른 파일/포맷으로 뽑으려면
      AOV별로 전용 `aiAOVDriver` 노드를 만들어 그 연결을 다시 잡아줘야
      한다(아래 `cmds.connectAttr(..., force=True)`).
    - `aiAOVDriver` 노드의 `.prefix`는 **확장자를 뺀** 경로다 --
      `.aiTranslator`(예: "exr", "png")가 확장자를 결정한다. 실측:
      `prefix="...\\stem"` + `aiTranslator="exr"` -> 정확히
      `...\\stem.exr` 파일이 생성됨(추가 접미사 없음, `<RenderPass>`
      토큰 없이도 AOV별 전용 드라이버라면 경고만 뜨고 정상 동작).
    - `.mergeAOVs = 0`으로 각 드라이버가 자기 AOV만 단독으로 쓰게 한다
      (합쳐서 멀티채널 EXR을 만들지 않는다 -- 이 태스크는 별도 파일을
      원한다).
    """
    node = aovInterface.getAOVNode(aovName, None)
    if not node:
        # addAOV() returns a SceneAOV object, not a node-name string like
        # getAOVNode() does (verified: connectAttr with the SceneAOV object
        # itself raises TypeError) -- pull its .node attribute.
        node = aovInterface.addAOV(aovName).node

    driver = driverName if cmds.objExists(driverName) else cmds.createNode(
        "aiAOVDriver", name=driverName, skipSelect=True)
    cmds.setAttr(driver + ".aiTranslator", fileFormat, type="string")
    cmds.setAttr(driver + ".mergeAOVs", 0)
    prefixNoExt = os.path.splitext(filePath)[0]
    cmds.setAttr(driver + ".prefix", prefixNoExt, type="string")
    cmds.connectAttr(driver + ".message", node + ".outputs[0].driver", force=True)


def renderSyntheticFrame(cameraTransform, outputDir):
    """현재 프레임을 렌더링해 beauty/depth/normal + calibration JSON을
    outputDir에 쓴다. mtoa가 로드돼 있지 않으면 로드를 시도한다. 반환값은
    outputPaths()와 같은 형태의 딕셔너리."""
    if not cmds.pluginInfo("mtoa", query=True, loaded=True):
        cmds.loadPlugin("mtoa")

    if not os.path.isdir(outputDir):
        os.makedirs(outputDir)

    frame = cmds.currentTime(query=True)
    paths = outputPaths(cameraTransform, frame, outputDir)
    width = cmds.getAttr(cameraTransform + ".outputResolutionWidth")
    height = cmds.getAttr(cameraTransform + ".outputResolutionHeight")

    import mtoa.aovs as aovs
    import mtoa.core as core

    # defaultArnoldRenderOptions/defaultArnoldDriver/defaultArnoldFilter
    # only exist once something has initialized Arnold as the active
    # render setup (e.g. opening Render Settings with Arnold selected).
    # createOptions() creates them if missing -- verified idempotent (safe
    # to call even when they already exist).
    core.createOptions()

    aovInterface = aovs.AOVInterface()

    # Depth(Z)/normal(N) AOVs: each gets its own EXR driver so they land in
    # their own files instead of defaultArnoldDriver's shared beauty output.
    _wireAovToDedicatedDriver(
        aovInterface, "Z", "maroSyntheticDataDepthDriver", paths["depth"], "exr")
    _wireAovToDedicatedDriver(
        aovInterface, "N", "maroSyntheticDataNormalDriver", paths["normal"], "exr")

    # Beauty (RGBA) is Arnold's built-in main render pass, not something
    # AOVInterface manages -- it goes through defaultArnoldDriver directly.
    cmds.setAttr("defaultArnoldDriver.aiTranslator", "png", type="string")
    cmds.setAttr("defaultArnoldDriver.mergeAOVs", 0)
    cmds.setAttr("defaultArnoldDriver.prefix",
                 os.path.splitext(paths["beauty"])[0], type="string")

    cmds.arnoldRender(width=width, height=height, camera=cameraTransform)

    calibration = buildCalibrationDict(cameraTransform, frame)
    with open(paths["calibration"], "w") as f:
        json.dump(calibration, f, indent=2)

    return paths
