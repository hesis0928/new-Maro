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

# --- buildCalibrationDict: Film Fit fields (2026-09-05 follow-up) ---
# NOTE: the task brief assumed `pixelAspectRatio` was a camera-SHAPE
# attribute like `filmFit`/`overscan` -- empirically verified (mayapy,
# 2026-09-05) that it is NOT: `cmds.attributeQuery("pixelAspectRatio",
# node=camShape, exists=True)` is False. The actual Maya attribute is the
# global `defaultResolution.pixelAspect` (which is what
# `defaultResolution.deviceAspectRatio` is itself derived from), so that's
# what's set/read here instead.
camShape = cmds.listRelatives(cam, shapes=True, fullPath=True)[0]
cmds.setAttr(camShape + ".filmFit", 1)  # Horizontal, per Maya's documented enum order
cmds.setAttr("defaultResolution.pixelAspect", 1.5)
cmds.setAttr(camShape + ".overscan", 1.2)
calibFilmFit = sdr.buildCalibrationDict(cam, cmds.currentTime(query=True))
assert calibFilmFit["filmFit"] in ("horizontal", 1), calibFilmFit["filmFit"]
assert abs(calibFilmFit["pixelAspectRatio"] - 1.5) < 1e-9, calibFilmFit
assert abs(calibFilmFit["overscan"] - 1.2) < 1e-9, calibFilmFit
print("buildCalibrationDict Film Fit fields OK")

# --- defaultResolution sync/restore helpers (2026-09-05, Film Fit real-render
# fix; see .superpowers/sdd/filmfit-task-2-report.md "Important
# side-finding") ---
# Empirically confirmed (see filmfit-task-3-report.md) that
# defaultResolution.deviceAspectRatio does NOT auto-recompute when
# width/height are set -- Arnold/MtoA reads deviceAspectRatio (not the
# width/height passed to cmds.arnoldRender()) to pick the Film-Fit-dependent
# effective aperture, so renderSyntheticFrame() must set all three
# explicitly and restore all three afterward.
cmds.setAttr("defaultResolution.width", 960)
cmds.setAttr("defaultResolution.height", 540)
cmds.setAttr("defaultResolution.deviceAspectRatio", 960.0 / 540.0)

snapshot = sdr._snapshotDefaultResolution()
assert snapshot["width"] == 960, snapshot
assert snapshot["height"] == 540, snapshot
assert abs(snapshot["deviceAspectRatio"] - (960.0 / 540.0)) < 1e-5, snapshot

sdr._applyDefaultResolution(320, 240, 320.0 / 240.0)
assert cmds.getAttr("defaultResolution.width") == 320
assert cmds.getAttr("defaultResolution.height") == 240
assert abs(cmds.getAttr("defaultResolution.deviceAspectRatio") - (320.0 / 240.0)) < 1e-5, (
    "deviceAspectRatio must be set explicitly -- it does not auto-recompute "
    "from width/height (실측 확인됨, filmfit-task-2-report.md)")

sdr._applyDefaultResolution(**snapshot)
assert cmds.getAttr("defaultResolution.width") == 960
assert cmds.getAttr("defaultResolution.height") == 540
assert abs(cmds.getAttr("defaultResolution.deviceAspectRatio") - (960.0 / 540.0)) < 1e-5
print("defaultResolution snapshot/apply OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
