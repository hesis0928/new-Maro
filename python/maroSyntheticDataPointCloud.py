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
import struct
import subprocess

import maya.api.OpenMaya as om2
import maya.cmds as cmds


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
    - 필름 종횡비 ≠ 렌더 해상도 종횡비인 경우(매우 흔함 — 예: 기본 35mm 필름 백
      `~1.499` vs 1920x1080 해상도 `~1.778`), 두 방향(x, y) 중 한 방향에서
      ~11-12% 기하학적 오차가 발생한다(실제 Arnold 렌더로 측정됨, 2026-09-04).
      Maya의 기본 Film Fit 모드는 "Fill"로, 렌더 해상도의 더 넓은 차원을 우선
      보존하므로, 보통 세로(Y/fy) 방향이 이 오차를 "흡수"한다.
    - 필름 종횡비 = 렌더 해상도 종횡비인 경우(테스트용 임의의 해상도 선택 시
      우연히 일치하는 경우)는 오차가 거의 없다.

    향후 고정을 위해서는 카메라의 `filmFit` 속성(Fill/Fit/Overscan/Horizontal/
    Vertical 중 하나)을 읽고, 필름 종횡비 ≠ 렌더 종횡비인 경우 Maya의 카메라
    모델(또는 MtoA) 문서에 따라 fx/fy 중 하나를 scale하는 로직이 필요하다.
    현재로선 이 계산 로직을 독립적으로 검증하기 위해(픽셀 부호 규약 검증처럼)
    배치 mayapy + Arnold 실측을 통해 Film Fit 보정을 적용했을 때의 개선을 수량화
    할 필요가 있다. 자세한 배경과 측정 결과는
    `.superpowers/sdd/arnold-task-4-report.md` (2026-09-04 Precision caveat 섹션)
    참고.
    """
    fx = (focalLengthMm / (horizontalFilmApertureIn * 25.4)) * widthPx
    fy = (focalLengthMm / (verticalFilmApertureIn * 25.4)) * heightPx
    return {"fx": fx, "fy": fy, "cx": widthPx / 2.0, "cy": heightPx / 2.0}


def convertExrToPfm(exrPath, pfmPath, oiiotoolPath="oiiotool"):
    """oiiotool로 exrPath(단일 채널 float EXR)를 pfmPath로 변환한다.
    oiiotool이 실패하거나 입력 파일이 없으면 RuntimeError."""
    result = subprocess.run(
        [oiiotoolPath, exrPath, "-o", pfmPath],
        capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "oiiotool failed converting {} -> {}: {}".format(
                exrPath, pfmPath, result.stderr))


def parsePfm(path):
    """PFM(Portable Float Map) 파일을 (width, height, data) 튜플로 읽는다.
    data는 위->아래(일반적인 래스터 순서) row-major float 리스트다 --
    PFM 자체는 아래->위 순서로 저장하므로 여기서 뒤집어 보정한다."""
    with open(path, "rb") as f:
        header = f.readline().decode("ascii").strip()
        if header not in ("Pf", "PF"):
            raise ValueError("not a PFM file (header: {!r})".format(header))
        channels = 1 if header == "Pf" else 3
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
