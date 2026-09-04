# Maro Arnold Synthetic Data Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Maro-menu-triggered tool that renders the current frame's beauty/depth/normal via Arnold (MtoA), saves them as files with a calibration JSON sidecar, and reprojects the depth image into a Maya-world-space point cloud (PLY file + existing `maroPointCloud` node preview).

**Architecture:** Pure Python, no new C++ code/commands/DG attributes. Four new modules under `python/`: a plain-camera-plus-custom-attributes "synthetic data camera" (no new node type), a pure-math depth-reprojection module (camera intrinsics, PFM parsing via the `oiiotool` CLI already installed alongside Arnold, unprojection, PLY writing, `maroPointCloud` update), an Arnold/MtoA render+AOV module, and a non-modal PySide6 panel tying it together.

**Tech Stack:** Python 3, `maya.cmds`, `maya.api.OpenMaya`, `mtoa` (Arnold's Maya plugin), `oiiotool.exe` (OpenImageIO CLI, vendored with Arnold), PySide6, mayapy batch tests, CMake/CTest.

**Spec:** `docs/superpowers/specs/2026-09-04-maro-arnold-synthetic-data-design.md`

## Global Constraints

- No new C++ code, commands, or DG attributes anywhere in this plan — everything is Python.
- Build/test command for every task (there is no new C++ to compile, but the full suite must still pass — this plan only adds Python files + CMake copy-rules + test registrations, all of which still flow through the existing build):
  ```powershell
  cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
      if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
  }
  cmake --build out/build --config Release
  ctest --test-dir out/build -C Release --output-on-failure
  ```
- New `.py` files never call `setStyleSheet()`.
- `maroPointCloud.points` is always written via `cmds.setAttr(node + ".points", count, *pointTuplesOfFour, type="pointArray")` (each tuple is `(x, y, z, 1.0)`) — this is the existing contract `maroSnapshotLidarScan` already uses; do not invent a different call shape.
- Camera world transforms are always obtained via `maya.api.OpenMaya` (`MSelectionList.getDagPath` + `MDagPath.inclusiveMatrix()`), never `cmds.xform` — this project has hit real bugs from `cmds.xform` respecting the scene's UI unit where internal-unit math was needed (see the LiDAR sensor validation plan's Critical-1 finding); camera world matrices in this plan feed pure linear-algebra unprojection math where unit consistency matters the same way.
- Every new mayapy test file follows the established bootstrap exactly (see `tests/maya/test_settings_panel.py`): `maya.standalone.initialize(name="python")`, `cmds.loadPlugin(os.environ["MARO_PLUGIN_PATH"])`, `cmds.file(new=True, force=True)`, `sys.path.insert(0, <repo>/python)`, teardown `cmds.file(new=True, force=True)` + `cmds.unloadPlugin(...)` + `maya.standalone.uninitialize()`.
- **Two genuine open questions this plan cannot resolve by reasoning alone — both require rendering a real, known scene through Arnold, which is why they are manual-checklist items in Task 4, not automated tests**: (1) whether Arnold's `Z` AOV reports planar depth (distance along the camera's view axis) or radial depth (straight-line camera-to-point distance) — `unprojectDepthToPoints()`'s `planarDepth=True` default is a starting hypothesis, not a confirmed fact; (2) whether this plan's pixel-row/column-to-camera-space sign convention (derived from the standard pinhole model, not from Maya's own camera math) matches Maya/Arnold's actual handedness. Do not treat either as settled until Task 4's manual verification confirms it — if either turns out wrong, fix the responsible function and note it in that task's report, the same way this project has handled every previous "verify, don't assume" coordinate question.
- The exact MtoA Python API surface for AOV/driver setup (Task 3) is written from general MtoA knowledge, not verified against this specific installed version. Before implementing Task 3, open an interactive Maya 2026 session, load `mtoa`, and manually run the `mtoa.aovs`/driver-wiring calls this plan specifies to confirm they exist with these names/signatures — adapt the code if the real API differs, and document any deviation in that task's report (the same discipline this project applied to the `rtcCollide` API surface in the LiDAR sensor validation plan).

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `python/maroSyntheticDataCamera.py` | Create | `createSyntheticDataCamera()`/`listSyntheticDataCameras()` — plain Maya camera + custom attributes, no new node type |
| `python/maroSyntheticDataPointCloud.py` | Create | Camera intrinsics, PFM parsing (via `oiiotool`), depth unprojection, PLY writing, `maroPointCloud` update |
| `python/maroSyntheticDataRender.py` | Create | Arnold/MtoA AOV setup + batch render + calibration JSON |
| `python/maroSyntheticDataPanel.py` | Create | Non-modal PySide6 panel tying the above together |
| `python/maroMenu.py` | Modify | New "합성 데이터 렌더..." menu item |
| `python/maroMainWindow.py` | Modify | Register `maroSyntheticDataPanel.stop()` in `teardown()` |
| `src/maro_plugin/CMakeLists.txt` | Modify | Add the 4 new modules to `MARO_PLUGIN_PY_MODULES` |
| `tests/maya/test_synthetic_data_camera.py` | Create | mayapy tests for Task 1 |
| `tests/maya/test_synthetic_data_point_cloud.py` | Create | mayapy tests for Task 2 |
| `tests/maya/test_synthetic_data_render.py` | Create | mayapy tests for Task 3's pure functions only |
| `tests/CMakeLists.txt` | Modify | Register `synthetic_data_camera`, `synthetic_data_point_cloud`, `synthetic_data_render` |
| `docs/maro-main-ui-manual-checklist.md` | Modify | New manual-verification section (Task 4) |

---

### Task 1: Synthetic data camera

**Files:**
- Create: `python/maroSyntheticDataCamera.py`
- Create: `tests/maya/test_synthetic_data_camera.py`
- Modify: `tests/CMakeLists.txt`
- Modify: `src/maro_plugin/CMakeLists.txt`

**Interfaces:**
- Produces: `createSyntheticDataCamera(name=None) -> str` (returns the camera transform's full path), `listSyntheticDataCameras() -> list[str]`.

- [ ] **Step 1: Write the failing test**

Create `tests/maya/test_synthetic_data_camera.py`:

```python
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

_pythonDir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "python")
if _pythonDir not in sys.path:
    sys.path.insert(0, _pythonDir)

import maroSyntheticDataCamera as sdc  # noqa: E402

assert sdc.listSyntheticDataCameras() == []
print("empty scene has no synthetic data cameras OK")

cam = sdc.createSyntheticDataCamera(name="testSynthCam")
assert cmds.objExists(cam), cam
assert cmds.getAttr(cam + ".outputResolutionWidth") == 1920
assert cmds.getAttr(cam + ".outputResolutionHeight") == 1080
assert cmds.getAttr(cam + ".outputDirectory") == ""
print("createSyntheticDataCamera defaults OK")

found = sdc.listSyntheticDataCameras()
assert found == [cam], found
print("listSyntheticDataCameras finds the new camera OK")

# An ordinary camera (no outputDirectory attribute) must not be listed.
ordinaryCam = cmds.camera(name="plainCam")[0]
foundAfterOrdinary = sdc.listSyntheticDataCameras()
assert foundAfterOrdinary == [cam], (
    "an ordinary camera without outputDirectory must not be listed, got {}".format(
        foundAfterOrdinary))
print("ordinary camera not falsely listed OK")

cam2 = sdc.createSyntheticDataCamera()  # default name
assert cmds.objExists(cam2)
assert cam2 != cam
foundBoth = set(sdc.listSyntheticDataCameras())
assert foundBoth == {cam, cam2}, foundBoth
print("multiple synthetic data cameras + default naming OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_synthetic_data_camera.py
```
Expected: FAIL — module doesn't exist yet.

- [ ] **Step 3: Write `python/maroSyntheticDataCamera.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_synthetic_data_camera.py
```
Expected: all `OK` lines print, exit 0.

- [ ] **Step 5: Register the test and the Python module**

In `tests/CMakeLists.txt`, add `synthetic_data_camera` to the `foreach(maya_test load axis_node binding ...)` list (the "plugin-only" group — same mechanism as every other pure-Python-module test, e.g. `settings_panel`).

In `src/maro_plugin/CMakeLists.txt`, add `maroSyntheticDataCamera` to `MARO_PLUGIN_PY_MODULES` (alphabetical position among the existing entries).

- [ ] **Step 6: Build and run the full suite**

```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure
```

- [ ] **Step 7: Commit**

```bash
git add python/maroSyntheticDataCamera.py tests/maya/test_synthetic_data_camera.py tests/CMakeLists.txt src/maro_plugin/CMakeLists.txt
git commit -m "feat(synthetic-data): add synthetic data camera (plain camera + custom attributes)"
```

---

### Task 2: Depth reprojection module (camera intrinsics, PFM parsing, unprojection, PLY, point cloud update)

**Files:**
- Create: `python/maroSyntheticDataPointCloud.py`
- Create: `tests/maya/test_synthetic_data_point_cloud.py`
- Modify: `tests/CMakeLists.txt`
- Modify: `src/maro_plugin/CMakeLists.txt`

**Interfaces:**
- Consumes: nothing from Task 1 (independent module; Task 4 wires them together).
- Produces:
  - `computeCameraIntrinsics(focalLengthMm, horizontalFilmApertureIn, verticalFilmApertureIn, widthPx, heightPx) -> dict` with keys `fx`, `fy`, `cx`, `cy` (pure).
  - `convertExrToPfm(exrPath, pfmPath, oiiotoolPath="oiiotool") -> None`, raises `RuntimeError` on failure.
  - `parsePfm(path) -> (width, height, data)` where `data` is a flat, top-to-bottom, row-major `list[float]` (pure, file I/O only).
  - `unprojectDepthToPoints(depthData, width, height, intrinsics, cameraWorldMatrixFlat, planarDepth=True, maxValidDepth=1e6) -> list[tuple[float, float, float]]` (pure — no `cmds`, only `maya.api.OpenMaya` math objects, matching this codebase's established definition of "pure" for this reason).
  - `writePly(points, path) -> None` (pure, file I/O only).
  - `updatePointCloudNode(points, pointCloudNode=None) -> str` (Maya-calling; creates a `maroPointCloud` node if `pointCloudNode` is `None` or doesn't exist).

**Before writing code**: confirm `oiiotool` is on `PATH` or locate it at `C:\Program Files\Autodesk\Arnold\Maya2026\bin\oiiotool.exe` (confirmed present on this machine, per the design spec) — Step 1's test needs to invoke it to generate a known-value test EXR without needing Arnold/MtoA at all.

- [ ] **Step 1: Write the failing tests**

First, manually run this once from a terminal to confirm `oiiotool`'s constant-pattern-generation syntax on this installed version before writing it into the test (this project's established practice: verify a vendor CLI's exact flags empirically rather than assume from general knowledge):
```
"C:\Program Files\Autodesk\Arnold\Maya2026\bin\oiiotool.exe" --pattern constant:color=10.0 8x8 1 -d float -o known_depth.exr
```
It should produce an 8x8, single-channel, 32-bit-float EXR where every pixel is `10.0`. If the exact flag names differ on this version, adjust the command below to match what actually works, and note the working form in your task report.

Create `tests/maya/test_synthetic_data_point_cloud.py`:

```python
import os
import subprocess
import sys
import tempfile

import maya.standalone

maya.standalone.initialize(name="python")

import maya.api.OpenMaya as om2  # noqa: E402
import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

_pythonDir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "python")
if _pythonDir not in sys.path:
    sys.path.insert(0, _pythonDir)

import maroSyntheticDataPointCloud as sdpc  # noqa: E402

_OIIOTOOL = r"C:\Program Files\Autodesk\Arnold\Maya2026\bin\oiiotool.exe"

# --- computeCameraIntrinsics ---
intrinsics = sdpc.computeCameraIntrinsics(
    focalLengthMm=35.0, horizontalFilmApertureIn=1.417323,
    verticalFilmApertureIn=0.945512, widthPx=1920, heightPx=1080)
assert abs(intrinsics["fx"] - (35.0 / (1.417323 * 25.4)) * 1920) < 1e-6
assert intrinsics["cx"] == 960.0 and intrinsics["cy"] == 540.0
print("computeCameraIntrinsics OK")

# --- convertExrToPfm + parsePfm round trip (real oiiotool, no Arnold needed) ---
tmpDir = tempfile.mkdtemp(prefix="maro_synth_")
exrPath = os.path.join(tmpDir, "known_depth.exr")
pfmPath = os.path.join(tmpDir, "known_depth.pfm")
subprocess.run(
    [_OIIOTOOL, "--pattern", "constant:color=10.0", "8x8", "1", "-d", "float",
     "-o", exrPath],
    check=True)
sdpc.convertExrToPfm(exrPath, pfmPath, oiiotoolPath=_OIIOTOOL)
width, height, data = sdpc.parsePfm(pfmPath)
assert width == 8 and height == 8, (width, height)
assert len(data) == 64, len(data)
assert all(abs(v - 10.0) < 1e-3 for v in data), (
    "expected every pixel to be ~10.0, got a range of {} to {}".format(
        min(data), max(data)))
print("convertExrToPfm + parsePfm round trip OK")

try:
    sdpc.convertExrToPfm("/no/such/file.exr", pfmPath, oiiotoolPath=_OIIOTOOL)
    raise AssertionError("expected RuntimeError for a missing input file")
except RuntimeError:
    print("convertExrToPfm raises RuntimeError on failure OK")

# --- unprojectDepthToPoints: on-axis point, identity camera transform ---
identityMatrix = list(om2.MMatrix())
onAxisIntrinsics = {"fx": 500.0, "fy": 500.0, "cx": 4.0, "cy": 4.0}
# Single pixel at the image center with depth=10 -- must land exactly on
# the camera's local -Z axis at distance 10 (Maya cameras look down -Z).
centerDepth = [0.0] * 64
centerDepth[4 * 8 + 4] = 10.0  # row=4, col=4 (0.5px off the true center at
                                # 3.5,3.5 for an 8x8 image -- close enough that
                                # the (col+0.5-cx) offset lands within 1px of
                                # the axis; assert with a loose tolerance)
points = sdpc.unprojectDepthToPoints(
    centerDepth, 8, 8, onAxisIntrinsics, identityMatrix, planarDepth=True)
assert len(points) == 1, points
x, y, z = points[0]
assert abs(z - (-10.0)) < 1e-6, (
    "on-axis point at depth=10 with planarDepth=True must have local/world "
    "z == -10.0 (camera looks down -Z), got {}".format(z))
assert abs(x) < 0.02 and abs(y) < 0.02, (
    "a pixel within 1px of the image center should unproject very close to "
    "the camera axis, got x={}, y={}".format(x, y))
print("unprojectDepthToPoints on-axis planarDepth OK")

# --- unprojectDepthToPoints: invalid depths are dropped ---
mixedDepth = [0.0] * 63 + [10.0]  # one valid depth, rest are 0.0 (invalid)
pointsMixed = sdpc.unprojectDepthToPoints(
    mixedDepth, 8, 8, onAxisIntrinsics, identityMatrix, planarDepth=True)
assert len(pointsMixed) == 1, pointsMixed
print("unprojectDepthToPoints drops zero/invalid depths OK")

# --- unprojectDepthToPoints: a non-identity world matrix translates the result ---
translatedMatrix = list(om2.MMatrix([
    1, 0, 0, 0,
    0, 1, 0, 0,
    0, 0, 1, 0,
    100, 200, 300, 1,
]))
pointsTranslated = sdpc.unprojectDepthToPoints(
    centerDepth, 8, 8, onAxisIntrinsics, translatedMatrix, planarDepth=True)
tx, ty, tz = pointsTranslated[0]
assert abs(tx - (x + 100)) < 1e-6
assert abs(ty - (y + 200)) < 1e-6
assert abs(tz - (z + 300)) < 1e-6
print("unprojectDepthToPoints respects the camera world matrix OK")

# --- writePly ---
plyPath = os.path.join(tmpDir, "test.ply")
sdpc.writePly([(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)], plyPath)
with open(plyPath) as f:
    content = f.read()
assert "element vertex 2" in content, content
assert "1.0 2.0 3.0" in content, content
print("writePly OK")

# --- updatePointCloudNode ---
node = sdpc.updatePointCloudNode([(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)])
assert cmds.objExists(node)
readBack = cmds.getAttr(node + ".points")
assert readBack is not None and len(readBack) == 2, readBack
assert abs(readBack[0][0] - 1.0) < 1e-6, readBack
print("updatePointCloudNode creates node and sets points OK")

node2 = sdpc.updatePointCloudNode([], pointCloudNode=node)
assert node2 == node
readBackEmpty = cmds.getAttr(node + ".points")
assert readBackEmpty is None or len(readBackEmpty) == 0, readBackEmpty
print("updatePointCloudNode handles empty points + reuses existing node OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_synthetic_data_point_cloud.py
```
Expected: FAIL — module doesn't exist yet.

- [ ] **Step 3: Write `python/maroSyntheticDataPointCloud.py`**

```python
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
    카메라 내부 파라미터(fx, fy, cx, cy, 전부 픽셀 단위)를 계산한다."""
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
```

- [ ] **Step 4: Run test to verify it passes**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_synthetic_data_point_cloud.py
```
Expected: all `OK` lines print, exit 0. If the on-axis unprojection assertion fails on the exact tolerance, double-check the `(col + 0.5 - cx)` pixel-center convention against what the test's hand-picked row/col actually represent before loosening any tolerance — a real bug here (wrong sign, wrong denominator) must not be papered over with a wider tolerance.

- [ ] **Step 5: Register the test and the Python module**

Add `synthetic_data_point_cloud` to `tests/CMakeLists.txt`'s `foreach(maya_test ...)` list. Add `maroSyntheticDataPointCloud` to `src/maro_plugin/CMakeLists.txt`'s `MARO_PLUGIN_PY_MODULES`.

- [ ] **Step 6: Build and run the full suite**

```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure
```

- [ ] **Step 7: Commit**

```bash
git add python/maroSyntheticDataPointCloud.py tests/maya/test_synthetic_data_point_cloud.py tests/CMakeLists.txt src/maro_plugin/CMakeLists.txt
git commit -m "feat(synthetic-data): add depth-to-point-cloud reprojection module"
```

---

### Task 3: Arnold render + AOV setup + calibration JSON

**Files:**
- Create: `python/maroSyntheticDataRender.py`
- Create: `tests/maya/test_synthetic_data_render.py`
- Modify: `tests/CMakeLists.txt`
- Modify: `src/maro_plugin/CMakeLists.txt`

**Interfaces:**
- Consumes: a synthetic data camera transform (Task 1's contract: has `outputResolutionWidth`/`Height`/`outputDirectory` attributes).
- Produces:
  - `outputPaths(cameraTransform, frame, outputDir) -> dict` with keys `beauty`, `depth`, `normal`, `calibration` (pure — string/path building only, no file I/O, no Maya calls beyond splitting the name).
  - `buildCalibrationDict(cameraTransform, frame) -> dict` (Maya-calling but Arnold-free: reads camera attributes + `MDagPath.inclusiveMatrix()`).
  - `renderSyntheticFrame(cameraTransform, outputDir) -> dict` (paths dict, same shape as `outputPaths()`'s return) — the only function that actually touches Arnold/MtoA; not automated-test-covered (see below).

**Automated-test boundary**: `outputPaths()` and `buildCalibrationDict()` need no Arnold/MtoA at all and are fully mayapy-testable. `renderSyntheticFrame()`'s actual rendering requires a working Arnold license and render context that may not be available in a batch `mayapy` process even with `mtoa` loaded — this plan does not assume it is; Task 4's manual checklist is where `renderSyntheticFrame()` gets its real verification.

- [ ] **Step 1: Write the failing tests for the two pure/Maya-only functions**

Create `tests/maya/test_synthetic_data_render.py`:

```python
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.api.OpenMaya as om2  # noqa: E402
import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

_pythonDir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "python")
if _pythonDir not in sys.path:
    sys.path.insert(0, _pythonDir)

import maroSyntheticDataCamera as sdc  # noqa: E402
import maroSyntheticDataRender as sdr  # noqa: E402

# --- outputPaths ---
paths = sdr.outputPaths("|group1|testCam", 7, "/tmp/out")
assert paths["beauty"].endswith("testCam_0007_beauty.png"), paths["beauty"]
assert paths["depth"].endswith("testCam_0007_depth.exr"), paths["depth"]
assert paths["normal"].endswith("testCam_0007_normal.exr"), paths["normal"]
assert paths["calibration"].endswith("testCam_0007_camera.json"), paths["calibration"]
print("outputPaths naming convention OK")

pathsFrame123 = sdr.outputPaths("|cam", 123, "/tmp/out")
assert "cam_0123_" in pathsFrame123["beauty"], pathsFrame123["beauty"]
print("outputPaths zero-pads the frame number OK")

# --- buildCalibrationDict ---
cam = sdc.createSyntheticDataCamera(name="calibTestCam")
cmds.setAttr(cam + ".translateX", 10.0)
cmds.setAttr(cam + ".translateY", 20.0)
cmds.setAttr(cam + ".translateZ", 30.0)
cmds.currentTime(5)

calib = sdr.buildCalibrationDict(cam, cmds.currentTime(query=True))
assert calib["frame"] == 5, calib
assert calib["resolutionWidth"] == 1920
assert calib["resolutionHeight"] == 1080
assert "focalLength" in calib and "horizontalFilmAperture" in calib
assert len(calib["worldMatrix"]) == 16, calib["worldMatrix"]

# Cross-check the matrix against an independently-obtained one (same
# mechanism, but re-derived here rather than trusting buildCalibrationDict's
# own result) -- this project's established discipline for matrix contracts.
sel = om2.MSelectionList()
sel.add(cam)
expectedMatrix = sel.getDagPath(0).inclusiveMatrix()
for i, expected in enumerate(expectedMatrix):
    assert abs(calib["worldMatrix"][i] - expected) < 1e-9, (i, calib["worldMatrix"][i], expected)
print("buildCalibrationDict OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
```

(`om2.MMatrix` is iterable in API 2.0 and yields its 16 elements in the same row-major order as `[matrix(r, c) for r in range(4) for c in range(4)]` — if this iteration order turns out not to match on this Maya version, replace the loop with the explicit nested-`range(4)` form instead of trusting iteration; verify by printing both once during development.)

- [ ] **Step 2: Run test to verify it fails**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_synthetic_data_render.py
```
Expected: FAIL — module doesn't exist yet.

- [ ] **Step 3: Manually verify the MtoA AOV API before writing `renderSyntheticFrame()`**

Open an interactive Maya 2026 session, run:
```python
import maya.cmds as cmds
cmds.loadPlugin("mtoa")
import mtoa.aovs as aovs
aovInterface = aovs.AOVInterface()
print(aovInterface.getAOVNode("N"))     # expect None before it's added
aovInterface.addAOV("N")
print(aovInterface.getAOVNode("N"))     # expect a node name now
aovInterface.addAOV("Z")
```
Confirm these calls exist and behave as expected on this installed MtoA version. If `mtoa.aovs.AOVInterface` doesn't exist or has different method names, find the actual working equivalent (check `help(aovs)` / `dir(aovs.AOVInterface)`) and use that instead of the code below — document what you found in your task report either way.

- [ ] **Step 4: Write `python/maroSyntheticDataRender.py`**

```python
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
    matrixFlat = [worldMatrix(r, c) for r in range(4) for c in range(4)]

    return {
        "frame": int(frame),
        "resolutionWidth": width,
        "resolutionHeight": height,
        "focalLength": focalLength,
        "horizontalFilmAperture": hFilmAperture,
        "verticalFilmAperture": vFilmAperture,
        "worldMatrix": matrixFlat,
    }


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
    aovInterface = aovs.AOVInterface()
    for aovName in ("N", "Z"):
        if not aovInterface.getAOVNode(aovName):
            aovInterface.addAOV(aovName)

    # AOV별 출력 파일 연결: Task 3 Step 3에서 확인한 실제 API로 각 AOV의
    # 드라이버/파일 경로/포맷을 연결한다. beauty(RGBA)는 PNG, depth(Z)/
    # normal(N)은 32비트 float EXR. 정확한 드라이버 노드 연결 방식은
    # Step 3에서 확인한 실제 MtoA 버전의 API에 맞춰 채운다(예:
    # cmds.setAttr으로 각 AOV 노드의 output 파일 경로를 지정하거나,
    # defaultArnoldDriver류 노드를 AOV별로 복제해 연결하는 방식 등 --
    # 이 계획을 쓰는 시점엔 실제 API가 확인되지 않았으므로 여기서
    # 확정하지 않는다).
    cmds.arnoldRender(width=width, height=height, camera=cameraTransform)

    calibration = buildCalibrationDict(cameraTransform, frame)
    with open(paths["calibration"], "w") as f:
        json.dump(calibration, f, indent=2)

    return paths
```

**Note for the implementer**: the AOV-driver-wiring block in `renderSyntheticFrame()` is intentionally left as a comment describing what must happen, not concrete code — this is the one place in this plan where the exact API was not available to verify in advance. Fill it in using what Step 3's manual investigation found, following this file's existing error-boundary style (no bare `except:`, let genuine failures propagate so the panel's own error handling in Task 4 can catch and display them). This is not a "TBD" left for later — it is this task's actual remaining work, to be completed and tested (per Step 6 below) before the task is done.

- [ ] **Step 5: Run the automated tests to verify they pass**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_synthetic_data_render.py
```
Expected: all `OK` lines print for `outputPaths`/`buildCalibrationDict`. This does not exercise `renderSyntheticFrame()` — that happens in Task 4's manual checklist.

- [ ] **Step 6: Manual smoke check of `renderSyntheticFrame()` (not part of Task 4's checklist — do this now so Task 3 isn't "done" with untested Arnold code)**

In interactive Maya 2026 with Arnold licensed: create a synthetic data camera, aim it at a simple polygon (e.g. `polyCube`), set a small resolution (e.g. 320x240) for a fast test render, call `renderSyntheticFrame(camera, someTempDir)` from the Script Editor, and confirm: the three image files and the calibration JSON actually appear in `someTempDir`, the beauty PNG looks like the scene, and the depth/normal EXRs are non-empty (`os.path.getsize(...) > 0` is a start; visually inspecting them in `oiiotool --info -v <path>` or an image viewer that supports EXR is better). Record what you found (including if the AOV-wiring approach from Step 4 needed adjustment) in this task's report.

- [ ] **Step 7: Register the test and the Python module**

Add `synthetic_data_render` to `tests/CMakeLists.txt`'s `foreach(maya_test ...)` list. Add `maroSyntheticDataRender` to `src/maro_plugin/CMakeLists.txt`'s `MARO_PLUGIN_PY_MODULES`.

- [ ] **Step 8: Build and run the full suite**

```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure
```

- [ ] **Step 9: Commit**

```bash
git add python/maroSyntheticDataRender.py tests/maya/test_synthetic_data_render.py tests/CMakeLists.txt src/maro_plugin/CMakeLists.txt
git commit -m "feat(synthetic-data): add Arnold AOV render + calibration JSON"
```

---

### Task 4: UI panel + Maro menu integration + manual verification

**Files:**
- Create: `python/maroSyntheticDataPanel.py`
- Modify: `python/maroMenu.py`
- Modify: `python/maroMainWindow.py`
- Modify: `src/maro_plugin/CMakeLists.txt`
- Modify: `docs/maro-main-ui-manual-checklist.md`

**Interfaces:**
- Consumes: `maroSyntheticDataCamera.createSyntheticDataCamera`/`listSyntheticDataCameras` (Task 1), `maroSyntheticDataRender.renderSyntheticFrame` (Task 3), `maroSyntheticDataPointCloud.convertExrToPfm`/`parsePfm`/`unprojectDepthToPoints`/`writePly`/`updatePointCloudNode` (Task 2).
- Produces: `show()`/`stop()` module functions (same shape as `maroSettingsPanel.py`).

No automated test for the panel itself (same batch-`mayapy`-has-no-`QApplication` constraint as every PySide6 widget in this project) — verified via the manual checklist added in this task.

- [ ] **Step 1: Read `python/maroSettingsPanel.py` in full**

This is the closest existing precedent: non-modal `QtWidgets.QWidget` subclass, module-level `_OPEN_PANEL` singleton, `show()`/`stop()` module functions, `closeEvent` clearing the singleton only `if _OPEN_PANEL is self`. Match its exact shape.

- [ ] **Step 2: Write `python/maroSyntheticDataPanel.py`**

```python
"""합성 데이터(RGB+Depth+Normal+포인트클라우드) 렌더링 패널. 카메라 선택/
생성, 출력 경로 지정, "렌더 지금" 버튼 하나로 Arnold 렌더 + depth 역투영
전체 흐름을 실행한다. setStyleSheet()를 부르지 않는다."""
import os

import maya.cmds as cmds
from PySide6 import QtCore, QtWidgets

import maroSyntheticDataCamera as sdc
import maroSyntheticDataPointCloud as sdpc
import maroSyntheticDataRender as sdr

_OPEN_PANEL = None


def show():
    """maroMenu.py의 "합성 데이터 렌더..." 항목이 부른다."""
    global _OPEN_PANEL
    if _OPEN_PANEL is not None:
        try:
            _OPEN_PANEL.raise_()
            _OPEN_PANEL.activateWindow()
            return _OPEN_PANEL
        except RuntimeError:
            _OPEN_PANEL = None

    _OPEN_PANEL = MaroSyntheticDataPanel()
    _OPEN_PANEL.show()
    return _OPEN_PANEL


def stop():
    """플러그인 언로드 시 열려 있는 패널을 닫는다. 한 번도 안 열렸어도
    안전한 무동작(maroSettingsPanel.stop()과 같은 이유, 같은 패턴 --
    close()가 closeEvent를 동기 실행해 전역을 먼저 지우므로 로컬 참조를
    먼저 잡아 둔다)."""
    global _OPEN_PANEL
    if _OPEN_PANEL is None:
        return
    panel = _OPEN_PANEL
    try:
        panel.close()
        panel.deleteLater()
    except Exception:  # noqa: BLE001 -- 언로드 정리 경계
        import traceback
        traceback.print_exc()
    _OPEN_PANEL = None


class MaroSyntheticDataPanel(QtWidgets.QWidget):
    """합성 데이터 렌더링 창."""

    def __init__(self, parent=None):
        super().__init__(parent, QtCore.Qt.Window)
        self.setWindowTitle("Maro 합성 데이터 렌더")

        layout = QtWidgets.QVBoxLayout(self)

        cameraRow = QtWidgets.QHBoxLayout()
        self._cameraCombo = QtWidgets.QComboBox()
        cameraRow.addWidget(self._cameraCombo)
        newCameraButton = QtWidgets.QPushButton("새로 만들기")
        newCameraButton.clicked.connect(self._onNewCamera)
        cameraRow.addWidget(newCameraButton)
        layout.addLayout(cameraRow)

        outputRow = QtWidgets.QHBoxLayout()
        self._outputDirField = QtWidgets.QLineEdit()
        outputRow.addWidget(self._outputDirField)
        browseButton = QtWidgets.QPushButton("찾아보기...")
        browseButton.clicked.connect(self._onBrowse)
        outputRow.addWidget(browseButton)
        layout.addLayout(outputRow)

        self._frameLabel = QtWidgets.QLabel()
        layout.addWidget(self._frameLabel)

        renderButton = QtWidgets.QPushButton("렌더 지금")
        renderButton.clicked.connect(self._onRenderNow)
        layout.addWidget(renderButton)

        self._statusLabel = QtWidgets.QLabel("")
        layout.addWidget(self._statusLabel)

        self._refreshCameraList()
        self._refreshFrameLabel()

    def _refreshCameraList(self):
        self._cameraCombo.clear()
        self._cameraCombo.addItems(sdc.listSyntheticDataCameras())

    def _refreshFrameLabel(self):
        self._frameLabel.setText("현재 프레임: {}".format(int(cmds.currentTime(query=True))))

    def _onNewCamera(self):
        try:
            newCam = sdc.createSyntheticDataCamera()
            self._refreshCameraList()
            index = self._cameraCombo.findText(newCam)
            if index >= 0:
                self._cameraCombo.setCurrentIndex(index)
        except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
            self._statusLabel.setText("카메라 생성 실패: {}".format(exc))

    def _onBrowse(self):
        result = cmds.fileDialog2(fileMode=3, caption="출력 디렉터리 선택")
        if result:
            self._outputDirField.setText(result[0])

    def _onRenderNow(self):
        camera = self._cameraCombo.currentText()
        outputDir = self._outputDirField.text()
        if not camera:
            self._statusLabel.setText("카메라를 선택하거나 새로 만드세요.")
            return
        if not outputDir:
            self._statusLabel.setText("출력 디렉터리를 지정하세요.")
            return

        self._statusLabel.setText("렌더링 중...")
        QtWidgets.QApplication.processEvents()
        try:
            paths = sdr.renderSyntheticFrame(camera, outputDir)

            self._statusLabel.setText("Depth 역투영 중...")
            QtWidgets.QApplication.processEvents()

            width = cmds.getAttr(camera + ".outputResolutionWidth")
            height = cmds.getAttr(camera + ".outputResolutionHeight")
            cameraShape = cmds.listRelatives(camera, shapes=True, fullPath=True)[0]
            intrinsics = sdpc.computeCameraIntrinsics(
                focalLengthMm=cmds.getAttr(cameraShape + ".focalLength"),
                horizontalFilmApertureIn=cmds.getAttr(cameraShape + ".horizontalFilmAperture"),
                verticalFilmApertureIn=cmds.getAttr(cameraShape + ".verticalFilmAperture"),
                widthPx=width, heightPx=height)

            pfmPath = os.path.splitext(paths["depth"])[0] + ".pfm"
            sdpc.convertExrToPfm(paths["depth"], pfmPath)
            _w, _h, depthData = sdpc.parsePfm(pfmPath)

            import maya.api.OpenMaya as om2
            sel = om2.MSelectionList()
            sel.add(camera)
            worldMatrix = sel.getDagPath(0).inclusiveMatrix()
            matrixFlat = [worldMatrix(r, c) for r in range(4) for c in range(4)]

            points = sdpc.unprojectDepthToPoints(
                depthData, width, height, intrinsics, matrixFlat)

            plyPath = os.path.splitext(paths["depth"])[0] + "_points.ply"
            sdpc.writePly(points, plyPath)
            sdpc.updatePointCloudNode(points)

            self._statusLabel.setText(
                "완료: {}개 점, {}".format(len(points), plyPath))
        except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
            self._statusLabel.setText("렌더링 실패: {}".format(exc))

    def closeEvent(self, event):
        global _OPEN_PANEL
        if _OPEN_PANEL is self:
            _OPEN_PANEL = None
        super().closeEvent(event)
```

- [ ] **Step 3: Wire the menu item in `python/maroMenu.py`**

Add, following the existing pattern (each item separated by a divider):

```python
    cmds.menuItem(divider=True, parent=MENU_NAME)
    cmds.menuItem(label="합성 데이터 렌더...",
                  command="import maroSyntheticDataPanel\nmaroSyntheticDataPanel.show()",
                  parent=MENU_NAME)
```

- [ ] **Step 4: Register `stop()` in `python/maroMainWindow.py`'s `teardown()`**

Add, following the exact same try/except pattern as the existing `maroSettingsPanel.stop()` block:

```python
    try:
        import maroSyntheticDataPanel
        maroSyntheticDataPanel.stop()
    except Exception:  # noqa: BLE001 -- Maya 콜백/언로드 경계
        import traceback
        traceback.print_exc()
```

- [ ] **Step 5: Add the new module to `src/maro_plugin/CMakeLists.txt`**

Add `maroSyntheticDataPanel` to `MARO_PLUGIN_PY_MODULES`.

- [ ] **Step 6: Build**

```powershell
cmake --build out/build --config Release
```

- [ ] **Step 7: Run the full suite**

```powershell
ctest --test-dir out/build -C Release --output-on-failure
```

- [ ] **Step 8: Write the manual checklist section**

Read `docs/maro-main-ui-manual-checklist.md`'s existing structure to match its exact table/section conventions, then append a new top-level section:

```markdown
## Maro 합성 데이터 렌더 (Arnold)

Arnold가 라이선스된 인터랙티브 Maya 2026에서, `maro.mll`을 로드하고 씬에
카메라가 잘 볼 수 있는 간단한 지오메트리(예: 알려진 위치의 `polyCube`)를
하나 둔 뒤, Maro 메뉴에서 "합성 데이터 렌더..."를 클릭한다.

- [ ] **패널이 뜨고 카메라 드롭다운/출력 경로 필드/렌더 버튼이 보인다.**
- [ ] **"새로 만들기"로 합성 데이터 카메라 생성** — 씬에 새 카메라가
      생기고 드롭다운에 나타나는가.
- [ ] **출력 디렉터리 지정 후 "렌더 지금"** — beauty(.png)/depth(.exr)/
      normal(.exr)/calibration(.json) 4개 파일이 실제로 생성되는가.
      beauty PNG를 열어 씬이 실제로 보이는지 확인한다.
- [ ] **[go/no-go] Depth AOV 규약 확정(설계 스펙 §9, 계획 Global
      Constraints)** — 카메라 정면 정확히 알려진 거리(예: 500 유닛)에
      카메라를 정면으로 바라보는 평면을 두고 렌더한다. 생성된 포인트
      클라우드(PLY 또는 `maroPointCloud`에 반영된 것)를 확인해, 그 평면에
      해당하는 점들의 카메라로부터의 거리가 500에 가까운지 확인한다.
      벗어나면(예: 카메라 각도 때문에 실제 직선 거리가 500보다 커야
      하는데 그대로 500이 나오는 등) `unprojectDepthToPoints()`의
      `planarDepth` 기본값이 틀렸다는 뜻이므로 `False`로 바꾸고 재확인한다.
- [ ] **[go/no-go] 픽셀 부호/방향 규약 확정** — 카메라 정면에서 한쪽으로
      치우친 위치(예: 카메라 기준 오른쪽)에 오브젝트를 두고 렌더 → 역투영된
      포인트클라우드에서 그 오브젝트가 카메라 기준 실제로 같은 쪽(오른쪽)에
      나타나는지 확인한다. 좌우/상하가 뒤집혀 나오면
      `unprojectDepthToPoints()`의 `xCam`/`yCam` 부호를 실측에 맞게 고친다.
- [ ] **`maroPointCloud` 미리보기** — 렌더 완료 후 씬에 `maroPointCloud`
      노드가 생기고(또는 갱신되고), 뷰포트에 포인트가 실제로 그려지는가
      (Phase 5 LiDAR 시각화의 드로우 오버라이드를 그대로 재사용).
- [ ] **PLY 파일** — 생성된 `.ply` 파일을 CloudCompare 등 외부 뷰어로
      열어 포인트클라우드가 씬 지오메트리와 대략 일치하는 형태인지
      확인한다.
- [ ] **에러 처리** — 카메라 미선택/출력 경로 미지정 상태로 "렌더 지금"을
      누르면 Maya가 죽지 않고 상태 라벨에 명확한 메시지가 뜨는가.
- [ ] **패널이 열린 채로 플러그인 언로드** — 크래시 없음.
```

- [ ] **Step 9: Perform the manual checklist yourself as far as this environment allows**

If this environment has interactive Maya with a licensed Arnold available, actually run through the checklist and record results. If not, leave the results column blank and note in your task report that this checklist requires a human with interactive Maya + Arnold license access to complete — do not mark this task DONE by assuming the checklist would pass; report DONE_WITH_CONCERNS with this explicitly noted if you cannot run it yourself.

- [ ] **Step 10: Commit**

```bash
git add python/maroSyntheticDataPanel.py python/maroMenu.py python/maroMainWindow.py src/maro_plugin/CMakeLists.txt docs/maro-main-ui-manual-checklist.md
git commit -m "feat(synthetic-data): add render panel, Maro menu entry, and manual checklist"
```

---

## Self-Review Notes

- **Spec coverage:** §3 (camera) -> Task 1. §4 (Arnold render + AOV + calibration) -> Task 3. §5 (depth reprojection + PLY + point cloud) -> Task 2. §6 (UI panel + menu) -> Task 4. §7 (global constraints: no new C++, `setStyleSheet()` ban, `pointArray` contract, matrix-handling principle) -> this plan's Global Constraints section, repeated in each task's interface notes. §8 (out of scope: ROS publishing, frame-range batching, semantic labeling, scenarios 1/4) -> no task attempts any of these. §9 (testing: pure-function coverage vs. manual-only Arnold verification, the two unresolved geometric-convention questions) -> Task 2's tests establish internal self-consistency only, Task 4's manual checklist is the explicit go/no-go for both open questions, matching the design spec's own framing.
- **Type/name consistency:** `outputPaths()`'s returned dict keys (`beauty`/`depth`/`normal`/`calibration`) are used identically by `renderSyntheticFrame()` (Task 3) and the panel's render flow (Task 4). `unprojectDepthToPoints()`'s signature and `planarDepth`/`maxValidDepth` defaults (Task 2) are called with matching keyword usage in Task 4's panel. `updatePointCloudNode()`'s `pointArray` `setAttr` call shape matches the exact convention this codebase already established for `maroSnapshotLidarScan`.
- **No placeholders:** the one intentionally-incomplete piece (Task 3 Step 4's AOV-driver-wiring block) is explicitly flagged as "this task's actual remaining work" with a concrete verification step (Step 3) preceding it and a concrete manual-verification step (Step 6) following it — not a silent TBD. Every other function in every task has a complete, concrete body.
