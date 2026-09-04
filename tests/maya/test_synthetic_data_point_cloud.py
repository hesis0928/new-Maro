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

# --- computeCameraIntrinsics: Film Fit modes (2026-09-05 follow-up) ---
import math as _math  # noqa: E402

# Fill, filmAspect < deviceAspect (the 1920x1080 default case, pixelAspectRatio=1):
# horizontal is the "narrower" side and stays raw; vertical is recomputed.
hAp, vAp, w, h = 1.417323, 0.945512, 1920, 1080
filmAspect = hAp / vAp
deviceAspect = w / float(h)
assert filmAspect < deviceAspect, "test premise: expected filmAspect < deviceAspect here"
fillWide = sdpc.computeCameraIntrinsics(35.0, hAp, vAp, w, h, filmFit="fill")
expectedFxRaw = (35.0 / (hAp * 25.4)) * w
expectedVEff = hAp / deviceAspect
expectedFyCorrected = (35.0 / (expectedVEff * 25.4)) * h
assert abs(fillWide["fx"] - expectedFxRaw) < 1e-6, fillWide
assert abs(fillWide["fy"] - expectedFyCorrected) < 1e-6, fillWide
assert abs(fillWide["fy"] - ((35.0 / (vAp * 25.4)) * h)) > 1.0, (
    "sanity: the corrected fy must differ meaningfully from the naive "
    "(uncorrected) formula, or this test can't tell a real fix from a no-op")
print("computeCameraIntrinsics Fill (filmAspect<deviceAspect) OK")

# Fill, filmAspect > deviceAspect (the original 320x240 bug-report case):
# vertical is the "narrower" side and stays raw; horizontal is recomputed.
hAp2, vAp2, w2, h2 = 1.417323, 0.945512, 320, 240
filmAspect2 = hAp2 / vAp2
deviceAspect2 = w2 / float(h2)
assert filmAspect2 > deviceAspect2, "test premise: expected filmAspect > deviceAspect here"
fillNarrow = sdpc.computeCameraIntrinsics(35.0, hAp2, vAp2, w2, h2, filmFit="fill")
expectedFyRaw2 = (35.0 / (vAp2 * 25.4)) * h2
expectedHEff2 = vAp2 * deviceAspect2
expectedFxCorrected2 = (35.0 / (expectedHEff2 * 25.4)) * w2
assert abs(fillNarrow["fy"] - expectedFyRaw2) < 1e-6, fillNarrow
assert abs(fillNarrow["fx"] - expectedFxCorrected2) < 1e-6, fillNarrow
print("computeCameraIntrinsics Fill (filmAspect>deviceAspect) OK")

# Horizontal: horizontal aperture is ALWAYS kept raw, regardless of which
# way the aspect ratio comparison goes -- use the SAME inputs as the
# filmAspect>deviceAspect Fill case above (320x240), where Fill would have
# corrected fx (not fy). Horizontal must behave differently from Fill here:
# fx stays raw, fy gets corrected instead.
horiz = sdpc.computeCameraIntrinsics(35.0, hAp2, vAp2, w2, h2, filmFit="horizontal")
expectedFxRawH = (35.0 / (hAp2 * 25.4)) * w2
expectedVEffH = hAp2 / deviceAspect2
expectedFyCorrectedH = (35.0 / (expectedVEffH * 25.4)) * h2
assert abs(horiz["fx"] - expectedFxRawH) < 1e-6, horiz
assert abs(horiz["fy"] - expectedFyCorrectedH) < 1e-6, horiz
assert abs(horiz["fx"] - fillNarrow["fx"]) > 1.0, (
    "sanity: Horizontal must genuinely differ from Fill for these inputs, "
    "since Fill corrected fx here but Horizontal must keep fx raw instead")
print("computeCameraIntrinsics Horizontal OK")

# Vertical: mirror of Horizontal -- vertical aperture always kept raw. Use
# the filmAspect<deviceAspect inputs (1920x1080), where Fill kept fx raw;
# Vertical must instead keep fy raw and correct fx.
vert = sdpc.computeCameraIntrinsics(35.0, hAp, vAp, w, h, filmFit="vertical")
expectedFyRawV = (35.0 / (vAp * 25.4)) * h
expectedHEffV = vAp * deviceAspect
expectedFxCorrectedV = (35.0 / (expectedHEffV * 25.4)) * w
assert abs(vert["fy"] - expectedFyRawV) < 1e-6, vert
assert abs(vert["fx"] - expectedFxCorrectedV) < 1e-6, vert
assert abs(vert["fx"] - fillWide["fx"]) > 1.0, (
    "sanity: Vertical must genuinely differ from Fill for these inputs")
print("computeCameraIntrinsics Vertical OK")

# pixelAspectRatio: a non-1.0 value changes deviceAspect and can flip which
# branch Fill takes. At 1920x1080 with pixelAspectRatio=1.0, deviceAspect
# (~1.778) > filmAspect (~1.499) -- Fill's "if" branch. Pick a
# pixelAspectRatio that pushes deviceAspect below filmAspect instead, and
# confirm Fill's OTHER branch fires (proving pixelAspectRatio is actually
# read, not ignored).
paRatio = 0.7  # deviceAspect = (1920/1080)*0.7 ~= 1.244, now < filmAspect ~1.499
deviceAspectPA = (w / float(h)) * paRatio
assert deviceAspectPA < filmAspect, "test premise: pixelAspectRatio must flip the comparison here"
fillPA = sdpc.computeCameraIntrinsics(35.0, hAp, vAp, w, h, filmFit="fill", pixelAspectRatio=paRatio)
expectedFyRawPA = (35.0 / (vAp * 25.4)) * h
expectedHEffPA = vAp * deviceAspectPA
expectedFxCorrectedPA = (35.0 / (expectedHEffPA * 25.4)) * w
assert abs(fillPA["fy"] - expectedFyRawPA) < 1e-6, fillPA
assert abs(fillPA["fx"] - expectedFxCorrectedPA) < 1e-6, fillPA
print("computeCameraIntrinsics pixelAspectRatio affects the Fill branch decision OK")

# Overscan (2026-09-05, Task 2): the exact MIRROR of Fill's branch choice --
# where Fill picks whichever of {keep-H-raw, keep-V-raw} SHRINKS the other
# side, Overscan picks whichever ENLARGES it (confirmed against the
# independent MFnCamera.getViewParameters() oracle below and a real Arnold
# render -- see .superpowers/sdd/filmfit-task-2-report.md). Use the SAME two
# aspect regimes as the Fill tests above to prove Overscan takes the
# opposite branch in each.
# 1920x1080 (filmAspect<deviceAspect): Fill kept H raw (shrinking V).
# Overscan must instead keep V raw and enlarge H.
overscanWide = sdpc.computeCameraIntrinsics(35.0, hAp, vAp, w, h, filmFit="overscan")
expectedHEffOvWide = vAp * deviceAspect
expectedFxOvWide = (35.0 / (expectedHEffOvWide * 25.4)) * w
expectedFyOvWide = (35.0 / (vAp * 25.4)) * h  # V raw
assert abs(overscanWide["fy"] - expectedFyOvWide) < 1e-6, overscanWide
assert abs(overscanWide["fx"] - expectedFxOvWide) < 1e-6, overscanWide
assert abs(overscanWide["fx"] - fillWide["fx"]) > 1.0, (
    "sanity: Overscan must genuinely differ from Fill here (opposite branch)")
print("computeCameraIntrinsics Overscan (filmAspect<deviceAspect, mirrors Fill) OK")

# 320x240 (filmAspect>deviceAspect): Fill kept V raw (shrinking H).
# Overscan must instead keep H raw and enlarge V.
overscanNarrow = sdpc.computeCameraIntrinsics(35.0, hAp2, vAp2, w2, h2, filmFit="overscan")
expectedVEffOvNarrow = hAp2 / deviceAspect2
expectedFyOvNarrow = (35.0 / (expectedVEffOvNarrow * 25.4)) * h2
expectedFxOvNarrow = (35.0 / (hAp2 * 25.4)) * w2  # H raw
assert abs(overscanNarrow["fx"] - expectedFxOvNarrow) < 1e-6, overscanNarrow
assert abs(overscanNarrow["fy"] - expectedFyOvNarrow) < 1e-6, overscanNarrow
assert abs(overscanNarrow["fy"] - fillNarrow["fy"]) > 1.0, (
    "sanity: Overscan must genuinely differ from Fill here (opposite branch)")
print("computeCameraIntrinsics Overscan (filmAspect>deviceAspect, mirrors Fill) OK")

# The `overscan` scalar attribute itself must NOT affect fx/fy in any mode --
# empirically confirmed (real Arnold render, byte-identical depth AOVs for
# overscan=1.0 vs overscan=3.0 with filmFit="overscan") that Maya's
# `.overscan` camera attribute only affects the VIEWPORT display gate, never
# the actual rendered/ray-traced geometry, even when filmFit IS Overscan.
overscanScaled = sdpc.computeCameraIntrinsics(35.0, hAp, vAp, w, h, filmFit="overscan", overscan=5.0)
assert abs(overscanScaled["fx"] - overscanWide["fx"]) < 1e-9, overscanScaled
assert abs(overscanScaled["fy"] - overscanWide["fy"]) < 1e-9, overscanScaled
print("computeCameraIntrinsics overscan scalar has no effect on fx/fy (matches real render) OK")

# Unrecognized filmFit value.
try:
    sdpc.computeCameraIntrinsics(35.0, hAp, vAp, w, h, filmFit="diagonal")
    raise AssertionError("expected ValueError for an unrecognized filmFit value")
except ValueError:
    print("computeCameraIntrinsics rejects an unrecognized filmFit value OK")

# Integer enum form (Maya's raw attribute value) must work the same as the
# string form -- 0=Fill, 1=Horizontal, 2=Vertical, 3=Overscan.
fillFromInt = sdpc.computeCameraIntrinsics(35.0, hAp, vAp, w, h, filmFit=0)
assert abs(fillFromInt["fx"] - fillWide["fx"]) < 1e-6
assert abs(fillFromInt["fy"] - fillWide["fy"]) < 1e-6
horizFromInt = sdpc.computeCameraIntrinsics(35.0, hAp2, vAp2, w2, h2, filmFit=1)
assert abs(horizFromInt["fx"] - horiz["fx"]) < 1e-6
assert abs(horizFromInt["fy"] - horiz["fy"]) < 1e-6
print("computeCameraIntrinsics integer filmFit enum form OK")

# --- computeCameraIntrinsics: independent MFnCamera oracle cross-check
# (2026-09-05, Task 2) ---
# Maya's own MFnCamera already implements Film Fit/pixelAspectRatio/overscan
# internally -- this is a genuinely independent authority (not a hand-derived
# expected value written by the same person implementing the formula), so a
# real mismatch here means computeCameraIntrinsics() itself is wrong.
#
# `MFnCamera.horizontalFieldOfView()`/`verticalFieldOfView()` (combined with
# `setAspectRatio()`) were tried FIRST and found to be the WRONG mechanism --
# empirically, they ignore `filmFit` entirely (always compute as if in
# Vertical fit, regardless of what `filmFit` is set to), so cross-checking
# against them silently "confirmed" a wrong formula. The correct,
# filmFit-aware oracle is `MFnCamera.getViewParameters(windowAspect,
# applyOverscan, applySqueeze, applyPanZoom) -> (apertureX, apertureY,
# offsetX, offsetY)` -- this returns the actual EFFECTIVE film-back
# dimensions (in inches) Maya's own camera model uses for the given device
# aspect, from which fx/fy follow via the same pinhole relation
# computeCameraIntrinsics() itself uses. `applyOverscan=False` matches this
# module's contract (overscan the scalar attribute is confirmed, via a real
# Arnold render -- see above and the task report -- to affect only the
# viewport display gate, never the rendered/ray-traced image).
_oracleCam = cmds.camera()[1]
_oracleFn = om2.MFnCamera(om2.MSelectionList().add(_oracleCam).getDagPath(0))
_oracleFocalLength = 35.0
_oracleHAp, _oracleVAp = 1.417323, 0.945512
cmds.setAttr(_oracleCam + ".focalLength", _oracleFocalLength)
cmds.setAttr(_oracleCam + ".horizontalFilmAperture", _oracleHAp)
cmds.setAttr(_oracleCam + ".verticalFilmAperture", _oracleVAp)

_oracleModeMap = {
    "fill": om2.MFnCamera.kFillFilmFit,
    "horizontal": om2.MFnCamera.kHorizontalFilmFit,
    "vertical": om2.MFnCamera.kVerticalFilmFit,
    "overscan": om2.MFnCamera.kOverscanFilmFit,
}
# At least 3-4 distinct (filmFit, resolution, pixelAspectRatio) combinations
# per mode, including pixelAspectRatio != 1.0, per the task brief.
_oracleCases = [
    (1920, 1080, 1.0),
    (320, 240, 1.0),
    (1280, 720, 1.0),
    (1920, 1080, 0.7),
    (640, 480, 1.5),
]
_oracleMismatches = []
for _mode in ("fill", "horizontal", "vertical", "overscan"):
    for _w, _h, _pa in _oracleCases:
        for _overscanVal in (1.0, 2.5):  # overscan value must never matter
            _deviceAspect = (_w / float(_h)) * _pa
            _oracleFn.filmFit = _oracleModeMap[_mode]
            _oracleFn.overscan = _overscanVal
            _apX, _apY, _offX, _offY = _oracleFn.getViewParameters(_deviceAspect, False, False, False)
            _oracleFx = _oracleFocalLength / (_apX * 25.4) * _w
            _oracleFy = _oracleFocalLength / (_apY * 25.4) * _h
            _codeResult = sdpc.computeCameraIntrinsics(
                _oracleFocalLength, _oracleHAp, _oracleVAp, _w, _h,
                filmFit=_mode, pixelAspectRatio=_pa, overscan=_overscanVal)
            if (abs(_oracleFx - _codeResult["fx"]) > 0.05 or
                    abs(_oracleFy - _codeResult["fy"]) > 0.05):
                _oracleMismatches.append(
                    (_mode, _w, _h, _pa, _overscanVal,
                     (_oracleFx, _oracleFy), (_codeResult["fx"], _codeResult["fy"])))
assert not _oracleMismatches, (
    "computeCameraIntrinsics() disagrees with the independent MFnCamera "
    "oracle for: {}".format(_oracleMismatches))
print("computeCameraIntrinsics matches the independent MFnCamera oracle "
      "across {} mode x resolution x pixelAspectRatio x overscan combinations OK"
      .format(4 * len(_oracleCases) * 2))
cmds.delete(cmds.listRelatives(_oracleCam, parent=True, fullPath=True)[0])

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
