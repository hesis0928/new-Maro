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
