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
