"""Depth EXR -> 포인트클라우드 역투영 순수 함수 + 결과 출력(PLY 파일,
maroPointCloud 노드). oiiotool 서브프로세스로 EXR -> PFM 변환 후 Python
struct 모듈만으로 파싱한다(별도 EXR 라이브러리를 mayapy 환경에 새로
설치할 필요 없음, 설계 스펙 §1).

**구현/사용 시 반드시 알아야 할 것(설계 스펙 §9, 계획 문서 Global
Constraints)**: unprojectDepthToPoints()의 planarDepth 기본값(True)과
픽셀→카메라공간 부호 규약은 표준 핀홀 카메라 모델에서 유도한 가정이지,
Arnold의 실제 Z AOV 규약이나 Maya 카메라의 실제 부호 규약과 대조 검증된
것이 아니다. 이 파일의 자체 테스트는 내부 일관성(왕복 변환, 월드 행렬
반영)만 증명한다 -- 실제 렌더 결과와의 일치 여부는 이 계획의 Task 4
수동 체크리스트에서만 확정된다."""
import math
import os
import shutil
import struct
import subprocess

import maya.api.OpenMaya as om2
import maya.cmds as cmds


def findOiiotool():
    """Arnold가 함께 설치한 oiiotool.exe를 찾는다.

    PATH의 'oiiotool'을 그냥 믿으면 안 된다 -- 실측 확인(2026-09-04):
    MayaUSD(`mayausd.mod`)와 Arnold(`mtoa.mod`) 둘 다 자기 `bin` 디렉터리를
    PATH 앞에 붙이는데, 모듈이 처리되는 순서상 MayaUSD의 bin이 Arnold의
    bin보다 PATH에서 앞에 온다 -- 그 결과 `shutil.which("oiiotool")`/bare
    `"oiiotool"` subprocess 호출은 MayaUSD가 번들한 OpenImageIO 빌드
    (PFM writer 없음, "OpenImageIO could not find a format writer for
    ...pfm" 에러로 실측 확인됨)를 잡고, Arnold의 실제 oiiotool.exe(PFM
    writer 포함)는 잡히지 않는다.

    대신 Arnold의 실제 설치 위치를 mtoa 플러그인 경로 기준으로 찾는다 --
    `cmds.pluginInfo("mtoa", query=True, path=True)`는 mtoa가 아직
    로드/등록되지 않은 상태에서 부르면 (None이 아니라) 예외를 던진다(실측
    확인) -- 로드를 시도한 뒤 조회한다."""
    try:
        if not cmds.pluginInfo("mtoa", query=True, registered=True):
            cmds.loadPlugin("mtoa")
        mtoaPluginPath = cmds.pluginInfo("mtoa", query=True, path=True)
    except RuntimeError:
        mtoaPluginPath = None
    if mtoaPluginPath:
        # mtoaPluginPath는 .../Arnold/Maya2026/plug-ins/mtoa.mll 형태 --
        # 두 단계 위(plug-ins의 부모)가 Arnold 설치 루트이고, 그 밑의
        # bin/oiiotool.exe가 실제로 PFM을 지원하는 바이너리다(실측 확인).
        arnoldRoot = os.path.dirname(os.path.dirname(mtoaPluginPath))
        candidate = os.path.join(arnoldRoot, "bin", "oiiotool.exe")
        if os.path.isfile(candidate):
            return candidate
    found = shutil.which("oiiotool")
    if found:
        return found
    raise RuntimeError("oiiotool.exe를 찾을 수 없습니다 (Arnold 설치를 확인하세요).")


# Maya의 filmFit enum 순서(정수 attribute 값과 대응) -- 문서화된 Maya 카메라
# 관례, cmds.attributeQuery("filmFit", node=<camera>, listEnum=True)로도
# 확인 가능.
_FILM_FIT_MODES = ("fill", "horizontal", "vertical", "overscan")


def _normalizeFilmFit(filmFit):
    """filmFit을 정규화된 소문자 문자열로 바꾼다. 문자열(대소문자 무관)이나
    Maya의 원시 정수 enum 값(0-3) 둘 다 받는다.

    정수 분기는 진짜 `int`만 받는다 -- `float`(예: `1.9`)를 예전처럼
    `int(filmFit)`로 조용히 잘라 받으면(계획의 Global Constraints가 명시적
    으로 금지하는 종류의 불필요한 일반화) 잘못된 입력이 들키지 않고 엉뚱한
    모드로 해석된다. 범위를 벗어난 정수(음수 포함, 예: `-1`)도 명시적으로
    거부한다 -- 그냥 `_FILM_FIT_MODES[int(filmFit)]`에 맡기면 Python의 음수
    인덱스 wraparound 때문에 `filmFit=-1`이 `_FILM_FIT_MODES[-1]`
    (`"overscan"`, Fill의 정반대 기하)로 에러 없이 조용히 풀린다."""
    if isinstance(filmFit, str):
        normalized = filmFit.strip().lower()
    elif isinstance(filmFit, int):
        normalized = (_FILM_FIT_MODES[filmFit]
                      if 0 <= filmFit < len(_FILM_FIT_MODES) else None)
    else:
        normalized = None
    if normalized not in _FILM_FIT_MODES:
        raise ValueError(
            "알 수 없는 filmFit 값: {!r} (지원: {})".format(filmFit, _FILM_FIT_MODES))
    return normalized


def computeCameraIntrinsics(focalLengthMm, horizontalFilmApertureIn, verticalFilmApertureIn,
                             widthPx, heightPx, filmFit="fill", pixelAspectRatio=1.0, overscan=1.0):
    """Maya 카메라의 초점거리(mm)/필름 백(inch)/Film Fit 모드/픽셀종횡비/
    오버스캔과 렌더 해상도로 핀홀 카메라 내부 파라미터(fx, fy, cx, cy, 전부
    픽셀 단위)를 계산한다.

    Film Fit 모드가 필름 백 종횡비와 렌더 해상도 종횡비의 불일치를 어떻게
    보정하는지 반영한다(설계 스펙 2026-09-05-maro-arnold-film-fit-correction-
    design.md §3) -- 2026-09-04 최종 리뷰가 발견한 ~11-19% 기하 오차의
    원인이었던 부분. `filmFit="fill"`(기본값)이 Maya 카메라의 기본 설정과
    일치한다.

    - `filmAspect = horizontalFilmApertureIn / verticalFilmApertureIn`
    - `deviceAspect = (widthPx / heightPx) * pixelAspectRatio` (Maya가 Film
      Fit 판정에 실제로 쓰는 정의 -- 정사각 픽셀이 아니면 단순
      widthPx/heightPx와 다르다)

    Fill: 두 종횡비 중 필름 쪽이 더 좁으면(`filmAspect < deviceAspect`)
    가로를 그대로 쓰고 세로를 다시 계산, 반대면 대칭. Horizontal/Vertical은
    그 중 한쪽을 종횡비 관계와 무관하게 항상 그대로 쓴다.

    Overscan(2026-09-05, Task 2에서 실측 확정): Fill과 **정반대** 분기를
    고른다 -- `filmAspect < deviceAspect`면 Fill은 가로를 그대로 쓰지만
    Overscan은 세로를 그대로 쓰고 가로를 (더 넓게) 다시 계산하며, 반대
    조건이면 그 반대로 동작한다. 즉 Fill이 "두 후보(가로기준/세로기준) 중
    화각이 더 좁아지는 쪽"을 고르는 데 비해 Overscan은 "더 넓어지는 쪽"을
    고른다 -- Maya 카메라 문서의 kOverscanFilmFit 설명("액션 안무를 위해
    프러스텀 바깥까지 볼 수 있게 화각을 넓힌다")과 일치하고,
    `maya.api.OpenMaya.MFnCamera.getViewParameters()`를 독립 오라클로 교차
    검증해 확인했다(`tests/maya/test_synthetic_data_point_cloud.py`의
    회귀 테스트 참고).

    **`overscan` 파라미터(카메라의 `.overscan` 어트리뷰트, 기본 1.0)는 이
    계산에 영향을 주지 않는다** -- 처음 가설("가로/세로 필름 백 양쪽에
    오버스캔 배율을 곱한다")은 실측으로 반증됐다.
    `MFnCamera.getViewParameters(..., applyOverscan=True)`는 실제로 그
    배율을 적용하지만, 이는 **뷰포트 표시 전용**이다(Maya 공식 문서:
    "Overscan 어트리뷰트는 카메라 뷰에서만 장면 크기를 조정하고, 렌더된
    이미지에는 영향을 주지 않는다") -- `filmFit=Overscan`을 골라도 마찬가지
    라는 것까지 실측 확인했다: 이 모듈이 실제로 호출하는
    `MFnCamera.getRenderingFrustum()`(렌더 프러스텀 전용 API, overscan
    인자 자체가 없음)은 overscan 값을 절대 반영하지 않고, 같은 장면을
    `filmFit="overscan"`으로 두고 `overscan=1.0`과 `overscan=2.0` 각각
    실제 Arnold로 렌더한 결과의 depth AOV가 픽셀 단위로 완전히 동일했다
    (2026-09-05, `.superpowers/sdd/filmfit-task-2-report.md`). 파라미터
    자체는 (기존 시그니처와의 호환을 위해, 그리고 카메라가 실제로 이
    어트리뷰트를 갖고 있다는 사실을 반영하기 위해) 계속 받지만 무시한다."""
    mode = _normalizeFilmFit(filmFit)

    filmAspect = horizontalFilmApertureIn / verticalFilmApertureIn
    deviceAspect = (widthPx / float(heightPx)) * pixelAspectRatio

    hEff = horizontalFilmApertureIn
    vEff = verticalFilmApertureIn

    if mode == "horizontal":
        vEff = hEff / deviceAspect
    elif mode == "vertical":
        hEff = vEff * deviceAspect
    elif mode == "overscan":
        # Fill의 정반대 분기 -- 자세한 근거는 위 docstring 참고.
        if filmAspect < deviceAspect:
            hEff = vEff * deviceAspect
        else:
            vEff = hEff / deviceAspect
    else:  # fill
        if filmAspect < deviceAspect:
            vEff = hEff / deviceAspect
        else:
            hEff = vEff * deviceAspect

    fx = (focalLengthMm / (hEff * 25.4)) * widthPx
    fy = (focalLengthMm / (vEff * 25.4)) * heightPx
    return {"fx": fx, "fy": fy, "cx": widthPx / 2.0, "cy": heightPx / 2.0}


def convertExrToPfm(exrPath, pfmPath, oiiotoolPath=None):
    """oiiotool로 exrPath(단일 채널 float EXR)를 pfmPath로 변환한다.
    oiiotool이 실패하거나 입력 파일이 없으면 RuntimeError.

    oiiotoolPath를 안 주면 findOiiotool()로 Arnold의 실제 oiiotool.exe를
    찾는다 -- bare "oiiotool"에 기대 PATH 순서에 맡기면 MayaUSD가 번들한
    (PFM writer 없는) OpenImageIO가 먼저 잡힐 수 있다(findOiiotool()
    도크스트링 참고)."""
    if oiiotoolPath is None:
        oiiotoolPath = findOiiotool()
    try:
        result = subprocess.run(
            [oiiotoolPath, exrPath, "-o", pfmPath],
            capture_output=True, text=True)
    except OSError as exc:
        raise RuntimeError(
            "oiiotool을 실행할 수 없습니다 (경로: {!r}): {}".format(
                oiiotoolPath, exc))
    if result.returncode != 0:
        raise RuntimeError(
            "oiiotool failed converting {} -> {}: {}".format(
                exrPath, pfmPath, result.stderr))


def parsePfm(path):
    """PFM(Portable Float Map) 파일을 (width, height, data) 튜플로 읽는다.
    data는 위->아래(일반적인 래스터 순서) row-major float 리스트다 --
    PFM 자체는 아래->위 순서로 저장하므로 여기서 뒤집어 보정한다.

    단일 채널("Pf") PFM만 지원한다 -- 이 모듈의 모든 호출자가 단일 채널
    depth 데이터를 기대하므로, 컬러("PF", 3채널) PFM을 받으면 그 인터리브된
    RGB 데이터가 조용히 스크램블된 단일 채널 depth처럼 오인될 위험이 있다.
    그런 오인을 만들지 않기 위해 3채널 PFM은 명시적으로 거부한다."""
    with open(path, "rb") as f:
        header = f.readline().decode("ascii").strip()
        if header not in ("Pf", "PF"):
            raise ValueError("not a PFM file (header: {!r})".format(header))
        if header != "Pf":
            raise ValueError(
                "parsePfm은 단일 채널(Pf) PFM만 지원합니다 -- {!r}는 3채널"
                " 컬러 PFM이라 depth 데이터로 쓸 수 없습니다: {}".format(
                    header, path))
        channels = 1
        width, height = (int(v) for v in f.readline().decode("ascii").split())
        scale = float(f.readline().decode("ascii").strip())
        endian = "<" if scale < 0 else ">"
        count = width * height * channels
        values = struct.unpack(endian + str(count) + "f", f.read(count * 4))
    rowSize = width * channels
    rows = [values[r * rowSize:(r + 1) * rowSize] for r in range(height)]
    rows.reverse()
    return width, height, [v for row in rows for v in row]


def unprojectDepthToPoints(depthData, width, height, intrinsics,
                            cameraWorldMatrixFlat, planarDepth=True,
                            maxValidDepth=1e6):
    """depthData(길이 width*height, 위->아래 row-major)를 카메라 공간 3D
    점으로 역투영한 뒤 cameraWorldMatrixFlat(16개 값, row-major,
    om2.MMatrix 규약)으로 월드 공간으로 옮긴다. Maya 카메라는 로컬 -Z를
    바라본다고 가정한다(정면의 점은 로컬 Z가 음수). depth<=0 또는
    depth>=maxValidDepth인 픽셀은 무효로 보고 건너뛴다."""
    fx, fy, cx, cy = (intrinsics["fx"], intrinsics["fy"],
                       intrinsics["cx"], intrinsics["cy"])
    matrix = om2.MMatrix(list(cameraWorldMatrixFlat))
    points = []
    for row in range(height):
        for col in range(width):
            depth = depthData[row * width + col]
            if depth <= 0.0 or depth >= maxValidDepth:
                continue
            xCam = (col + 0.5 - cx) * depth / fx
            yCam = (cy - (row + 0.5)) * depth / fy
            if planarDepth:
                xLocal, yLocal, zLocal = xCam, yCam, -depth
            else:
                planarLength = math.sqrt(xCam * xCam + yCam * yCam + depth * depth)
                scale = depth / planarLength if planarLength > 1e-9 else 0.0
                xLocal, yLocal, zLocal = xCam * scale, yCam * scale, -depth * scale
            localPoint = om2.MPoint(xLocal, yLocal, zLocal)
            worldPoint = localPoint * matrix
            points.append((worldPoint.x, worldPoint.y, worldPoint.z))
    return points


def writePly(points, path):
    """points(리스트 of (x,y,z))를 ASCII PLY로 저장한다."""
    with open(path, "w") as f:
        f.write("ply\nformat ascii 1.0\n")
        f.write("element vertex {}\n".format(len(points)))
        f.write("property float x\nproperty float y\nproperty float z\n")
        f.write("end_header\n")
        for x, y, z in points:
            f.write("{} {} {}\n".format(x, y, z))


def updatePointCloudNode(points, pointCloudNode=None):
    """points를 기존(또는 새로 만든) maroPointCloud 노드의 .points에
    반영한다. maroSnapshotLidarScan이 이미 쓰는 것과 같은 setAttr 형태
    (x,y,z,1.0 튜플 + type="pointArray") -- 새 계약을 발명하지 않는다."""
    if pointCloudNode is None or not cmds.objExists(pointCloudNode):
        pointCloudNode = cmds.createNode("maroPointCloud")
    if points:
        pointTuples = [(x, y, z, 1.0) for x, y, z in points]
        cmds.setAttr(pointCloudNode + ".points", len(points), *pointTuples,
                     type="pointArray")
    else:
        cmds.setAttr(pointCloudNode + ".points", 0, type="pointArray")
    return pointCloudNode
