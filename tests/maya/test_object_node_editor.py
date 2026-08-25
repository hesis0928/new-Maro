import os
import sys

_pythonDir = os.path.join(os.path.dirname(__file__), "..", "..", "python")
sys.path.insert(0, _pythonDir)

import maroObjectNodeEditor as one

# --- sliceAxisRows ---
flat = ["|axis1", "joint1", "|cube1", "", "0", "1", "1", "2", "Axis One", "0.2,0.6,0.9"]
rows = one.sliceAxisRows(flat)
assert len(rows) == 1, rows
assert rows[0] == {
    "axisFullPath": "|axis1", "jointName": "joint1", "boundTargetPath": "|cube1",
    "parentAxisPath": "", "controlMode": 0, "enabled": True, "conventionAxis": 1,
    "capabilityCount": 2, "displayName": "Axis One",
    "displayColor": (0.2, 0.6, 0.9),
}, rows[0]
assert one.sliceAxisRows(None) == []
try:
    one.sliceAxisRows(["too", "few"])
    assert False, "expected ValueError for a non-multiple-of-10 array"
except ValueError:
    pass
print("sliceAxisRows OK")

# --- computeGsonGridLayout ---
positions = one.computeGsonGridLayout(5, columns=3, cellWidth=100.0, cellHeight=40.0, gap=10.0)
assert len(positions) == 5
assert positions[0] == (0.0, 0.0)
assert positions[1] == (110.0, 0.0)
assert positions[2] == (220.0, 0.0)
assert positions[3] == (0.0, 50.0), "4th item must wrap to the next row"
assert positions[4] == (110.0, 50.0)
assert one.computeGsonGridLayout(0, columns=3, cellWidth=100.0, cellHeight=40.0, gap=10.0) == []
print("computeGsonGridLayout OK")
