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


def computeCameraIntrinsics(focalLengthMm, horizontalFilmApertureIn,
                             verticalFilmApertureIn, widthPx, heightPx):
    """Maya 카메라의 초점거리(mm)/필름 백(inch)과 렌더 해상도로 핀홀
    카메라 내부 파라미터(fx, fy, cx, cy, 전부 픽셀 단위)를 계산한다.

    **제한 사항 — Film Fit 모드 미지원**: 이 함수는 카메라의 raw 필름 백 크기
    (horizontalFilmApertureIn, verticalFilmApertureIn)를 렌더 해상도(widthPx,
    heightPx)와 직접 대응시켜 fx/fy를 계산한다. Maya의 카메라 Film Fit 모드
    (Fill/Fit/Overscan/Horizontal/Vertical)는 필름 백 종횡비와 렌더 해상도의
    종횡비가 일치하지 않을 때 화각을 조정하는데, 이 함수는 그 보정을 반영하지
    않는다. 따라서:
    - 필름 종횡비 ≠ 렌더 해상도 종횡비인 경우(매우 흔함), 오차 배율은
      `max(filmAspect/deviceAspect, deviceAspect/filmAspect)`로 일반화된다
      (filmAspect = horizontalFilmApertureIn/verticalFilmApertureIn,
      deviceAspect = widthPx/heightPx). **이 배율은 해상도마다 다르다** —
      아래 두 실측 사례가 서로 다른 크기/방향을 보이는 이유가 바로 이것이다:
      - 320x240(테스트 해상도, deviceAspect `~1.333` < filmAspect `~1.499`):
        배율 `~1.124` → **~12% 오차, 실제 Arnold 렌더로 측정 결과 세로(Y/fy)
        방향이 흡수함**(2026-09-04, `arnold-task-4-report.md`).
      - 1920x1080(이 모듈의 실제 기본 해상도, `maroSyntheticDataCamera.
        createSyntheticDataCamera()`, deviceAspect `~1.778` > filmAspect
        `~1.499` — 320x240과 부등호 방향이 뒤집힘): 배율 `~1.186` → **~19%
        오차**. 320x240과 종횡비 부등호가 반대이므로 Fill 모드가 오차를
        흡수하는 축도 뒤집힐 가능성이 높다(가로/X가 흡수) — 하지만 **이
        축 판정은 320x240에서만 실측됐고 1920x1080에서 직접 렌더로
        확인된 적은 없다**. "Y가 흡수한다"는 일반 사실이 아니라 320x240
        한정 관측이므로, 다른 해상도에서 어느 축이 오차를 흡수하는지는
        매번 실측해야 한다.
    - 필름 종횡비 = 렌더 해상도 종횡비인 경우(우연히 일치하는 경우)는 오차가
      거의 없다.

    향후 고정을 위해서는 카메라의 `filmFit` 속성(Fill/Fit/Overscan/Horizontal/
    Vertical 중 하나)을 읽고, 필름 종횡비 ≠ 렌더 종횡비인 경우 Maya의 카메라
    모델(또는 MtoA) 문서에 따라 fx/fy 중 하나를 scale하는 로직이 필요하다 —
    이 함수는 의도적으로 그 보정을 구현하지 않는다(범위 밖). 자세한 배경과
    측정 결과는 `.superpowers/sdd/arnold-task-4-report.md`(2026-09-04
    Precision caveat 섹션) 및 최종 리뷰 수정 보고서
    (`.superpowers/sdd/arnold-final-review-fix-report.md`, Fix 5) 참고.
    """
    fx = (focalLengthMm / (horizontalFilmApertureIn * 25.4)) * widthPx
    fy = (focalLengthMm / (verticalFilmApertureIn * 25.4)) * heightPx
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
