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

# --- AXIS_FIELDS는 C++ listAxes()의 필드 수와 같아야 한다 (최종 리뷰 I-3) ---
# 이 모듈은 창 제목/Coupling 소스 목록을 위해 maroListAxisNodes()의 무플래그
# 출력을 직접 자른다. maroObjectNodeEditor.py에도 같은 값의 독립 상수가 있고
# (순환 import를 피하려 일부러 나눠 뒀다), 둘이 어긋나면 파싱이 조용히
# 어긋나므로 값으로 고정해 둔다.
assert sone.AXIS_FIELDS == 10, sone.AXIS_FIELDS
print("AXIS_FIELDS OK")

# 설계 스펙 §4.2: 새 .py는 setStyleSheet()를 부르지 않는다 -- Maya 프로세스
# 전역 QApplication의 팔레트/스타일을 그대로 물려받아야 기존 mayaUI와
# 이질감이 없다. 기계적으로 점검할 수 있는 규율이므로 기계가 점검한다.
# (삭제된 tests/maya/test_axis_panel.py가 갖고 있던 검사를 승계한다.)
#
# 찾는 문자열이 "setStyleSheet("가 아니라 ".setStyleSheet("인 이유: 그 규율을
# 설명하는 주석/도크스트링 자체가 이름을 언급한다. 호출은 언제나 어떤 위젯에
# 대고 하므로 점이 앞에 붙는다 -- 규율을 어기는 코드만 걸리고 규율을 적어 둔
# 산문은 걸리지 않는다. (tests/maya/test_main_window.py의 같은 검사와 동일한
# 관용구다.)
with open(os.path.join(_pythonDir, "maroSingleObjectNodeEditor.py"),
          encoding="utf-8") as handle:
    source = handle.read()
assert ".setStyleSheet(" not in source, (
    "maroSingleObjectNodeEditor.py must not call setStyleSheet() -- it has to "
    "inherit Maya's global Qt style (design spec 4.2)"
)
print("no setStyleSheet OK")

print("test_single_object_node_editor OK")
sys.exit(0)
