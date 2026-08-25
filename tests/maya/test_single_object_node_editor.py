import math
import os
import sys

_pythonDir = os.path.join(os.path.dirname(__file__), "..", "..", "python")
sys.path.insert(0, _pythonDir)

import maroSingleObjectNodeEditor as sone

# --- sliceCapabilityRows ---
flat = ["0", "capNode1", "maroRotation", "0", "1",
        "1", "", "", "1", "0"]
rows = sone.sliceCapabilityRows(flat)
assert len(rows) == 2, f"expected 2 rows, got {len(rows)}"
assert rows[0] == {
    "logicalIndex": 0, "capabilityNodeName": "capNode1",
    "capabilityNodeType": "maroRotation", "capType": 0, "connected": True,
}, rows[0]
assert rows[1] == {
    "logicalIndex": 1, "capabilityNodeName": "",
    "capabilityNodeType": "", "capType": 1, "connected": False,
}, rows[1]
assert sone.sliceCapabilityRows(None) == []
try:
    sone.sliceCapabilityRows(["only", "four", "fields", "here"])
    assert False, "expected ValueError for a non-multiple-of-5 array"
except ValueError:
    pass
print("sliceCapabilityRows OK")

# --- computeRadialLayout ---
positions = sone.computeRadialLayout(100.0, 100.0, 4, 50.0)
assert len(positions) == 4
# First item is straight up from the center (angle -90 degrees).
assert abs(positions[0][0] - 100.0) < 1e-6, positions[0]
assert abs(positions[0][1] - 50.0) < 1e-6, positions[0]
# All items are exactly `radius` away from the center.
for x, y in positions:
    dist = math.hypot(x - 100.0, y - 100.0)
    assert abs(dist - 50.0) < 1e-6, (x, y, dist)
assert sone.computeRadialLayout(0.0, 0.0, 0, 50.0) == []
print("computeRadialLayout OK")

# --- hitTestRadialItem ---
items = [(100.0, 50.0), (150.0, 100.0), (100.0, 150.0), (50.0, 100.0)]
assert sone.hitTestRadialItem(100.0, 50.0, items, 20.0, 10.0) == 0
assert sone.hitTestRadialItem(150.0, 100.0, items, 20.0, 10.0) == 1
assert sone.hitTestRadialItem(0.0, 0.0, items, 20.0, 10.0) is None
# Boundary is inclusive.
assert sone.hitTestRadialItem(120.0, 50.0, items, 20.0, 10.0) == 0
assert sone.hitTestRadialItem(121.0, 50.0, items, 20.0, 10.0) is None
print("hitTestRadialItem OK")

# --- indexOfCapabilityToPeel ---
rowsAllConnected = sone.sliceCapabilityRows([
    "0", "n0", "maroRotation", "0", "1",
    "2", "n2", "maroLimit", "1", "1",
    "1", "n1", "maroSensorRange", "3", "1",
])
assert sone.indexOfCapabilityToPeel(rowsAllConnected) == 2, \
    "must pick the highest logicalIndex among connected rows"
rowsNoneConnected = sone.sliceCapabilityRows(["0", "", "", "0", "0"])
assert sone.indexOfCapabilityToPeel(rowsNoneConnected) is None
assert sone.indexOfCapabilityToPeel([]) is None
print("indexOfCapabilityToPeel OK")
