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
with open(os.path.join(_pythonDir, "maroObjectNodeEditor.py"), encoding="utf-8") as handle:
    source = handle.read()
assert ".setStyleSheet(" not in source, (
    "maroObjectNodeEditor.py must not call setStyleSheet() -- it has to inherit "
    "Maya's global Qt style (design spec 4.2)"
)
print("no setStyleSheet OK")

print("test_object_node_editor OK")
sys.exit(0)
