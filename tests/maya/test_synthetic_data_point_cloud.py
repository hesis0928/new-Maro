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

# --- findOiiotool() + convertExrToPfm's NEW default resolver (final-review Fix 1) ---
# This is the shipped default the panel's _onRenderNow() actually calls
# (convertExrToPfm(exrPath, pfmPath) with no oiiotoolPath) -- the previous
# bare "oiiotool" default relied on PATH order and, verified empirically,
# resolved to MayaUSD's bundled OpenImageIO (no PFM writer) instead of
# Arnold's, because both mayausd.mod and mtoa.mod prepend their own bin/ to
# PATH and MayaUSD's wins. findOiiotool() resolves Arnold's actual
# oiiotool.exe via the loaded mtoa plugin's own path instead of trusting
# PATH. This test exercises that NEW default end-to-end -- it must not use
# the hardcoded _OIIOTOOL absolute path the tests above use, since the
# whole point is to catch a regression in the resolver itself.
resolvedOiiotool = sdpc.findOiiotool()
assert os.path.isfile(resolvedOiiotool), resolvedOiiotool
assert "arnold" in resolvedOiiotool.lower(), (
    "findOiiotool() must resolve Arnold's oiiotool.exe, not MayaUSD's or "
    "anything else on PATH, got {}".format(resolvedOiiotool))
print("findOiiotool resolves Arnold's oiiotool.exe OK:", resolvedOiiotool)

defaultResolverPfmPath = os.path.join(tmpDir, "known_depth_default_resolver.pfm")
sdpc.convertExrToPfm(exrPath, defaultResolverPfmPath)  # no oiiotoolPath -- the real shipped default
defaultWidth, defaultHeight, defaultData = sdpc.parsePfm(defaultResolverPfmPath)
assert defaultWidth == 8 and defaultHeight == 8, (defaultWidth, defaultHeight)
assert all(abs(v - 10.0) < 1e-3 for v in defaultData), (
    "expected every pixel to be ~10.0 via the default resolver, got a range "
    "of {} to {}".format(min(defaultData), max(defaultData)))
print("convertExrToPfm with the NEW default resolver (no oiiotoolPath) succeeds OK")

# --- parsePfm: row order must be top->bottom, not reversed/scrambled ---
# A uniform-value image (as above) can't distinguish correct row order from
# a reversed, doubled-reversed, or omitted row-flip -- every row looks the
# same. Build a row-dependent image instead: a constant base of 5.0 with the
# bottom half (oiiotool's y=4..7, raster convention: y=0 is the top row)
# overwritten to 15.0 via --fill. If parsePfm's rows.reverse() were removed
# or the flip logic were otherwise broken, the returned top-to-bottom data
# would report the top rows as ~15.0 instead of ~5.0 (or some other
# non-top/bottom split), so the per-row assertions below would fail.
rowExrPath = os.path.join(tmpDir, "row_gradient.exr")
rowPfmPath = os.path.join(tmpDir, "row_gradient.pfm")
subprocess.run(
    [_OIIOTOOL, "--pattern", "constant:color=5.0", "8x8", "1", "-d", "float",
     "--fill:color=15.0", "8x4+0+4", "-o", rowExrPath],
    check=True)
sdpc.convertExrToPfm(rowExrPath, rowPfmPath, oiiotoolPath=_OIIOTOOL)
rowWidth, rowHeight, rowData = sdpc.parsePfm(rowPfmPath)
assert rowWidth == 8 and rowHeight == 8, (rowWidth, rowHeight)
assert len(rowData) == 64, len(rowData)
for r in range(rowHeight):
    rowValues = rowData[r * rowWidth:(r + 1) * rowWidth]
    expected = 5.0 if r < 4 else 15.0
    assert all(abs(v - expected) < 1e-3 for v in rowValues), (
        "row {} expected all values ~{} (top->bottom order), got {}".format(
            r, expected, rowValues))
print("parsePfm returns rows in top->bottom order OK")

# --- parsePfm rejects 3-channel (color, "PF" header) PFM (final-review Fix 7.2) ---
# Every current caller wants single-channel depth data -- a 3-channel PFM's
# interleaved RGB would otherwise be silently misinterpreted as scrambled
# single-channel data (no channel count in the (width, height, data) return).
colorExrPath = os.path.join(tmpDir, "color.exr")
colorPfmPath = os.path.join(tmpDir, "color.pfm")
subprocess.run(
    [_OIIOTOOL, "--pattern", "constant:color=1,2,3", "8x8", "3", "-d", "float",
     "-o", colorExrPath],
    check=True)
subprocess.run([_OIIOTOOL, colorExrPath, "-o", colorPfmPath], check=True)
try:
    sdpc.parsePfm(colorPfmPath)
    raise AssertionError("expected ValueError for a 3-channel (PF) PFM")
except ValueError:
    print("parsePfm rejects 3-channel PFM OK")

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
