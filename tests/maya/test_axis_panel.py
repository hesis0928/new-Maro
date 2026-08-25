"""maroAxisPanel의 순수 함수(sliceAxisRows/sliceCapabilityRows)만 검증한다.
QWidget 생성은 배치 모드에서 프로세스를 abort시키므로(모듈 도크스트링
참고) 여기서 AxisPanel/buildWidget은 절대 부르지 않는다."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "python"))

import maroAxisPanel  # noqa: E402

# --- sliceAxisRows ---
flat = ["|g|axis1", "shoulder", "|g|cube1", "", "0", "1", "1", "2"]
rows = maroAxisPanel.sliceAxisRows(flat)
assert len(rows) == 1
assert rows[0]["axisFullPath"] == "|g|axis1"
assert rows[0]["jointName"] == "shoulder"
assert rows[0]["boundTargetPath"] == "|g|cube1"
assert rows[0]["parentAxisPath"] == ""
assert rows[0]["controlMode"] == 0
assert rows[0]["enabled"] is True
assert rows[0]["conventionAxis"] == 1
assert rows[0]["capabilityCount"] == 2
print("sliceAxisRows OK")

try:
    maroAxisPanel.sliceAxisRows(["only", "seven", "fields", "not", "eight", "here", "x"])
    raised = False
except ValueError:
    raised = True
assert raised, "sliceAxisRows must reject a length that's not a multiple of AXIS_FIELDS"
print("sliceAxisRows length validation OK")

assert maroAxisPanel.sliceAxisRows(None) == [], "sliceAxisRows(None) must return an empty list"
print("sliceAxisRows(None) OK")

# --- sliceCapabilityRows ---
flatCap = ["0", "|g|rot1", "maroRotation", "0", "1"]
capRows = maroAxisPanel.sliceCapabilityRows(flatCap)
assert len(capRows) == 1
assert capRows[0]["logicalIndex"] == 0
assert capRows[0]["capabilityNodeName"] == "|g|rot1"
assert capRows[0]["capabilityNodeType"] == "maroRotation"
assert capRows[0]["capType"] == 0
assert capRows[0]["connected"] is True
print("sliceCapabilityRows OK")

print("teardown OK")
sys.exit(0)
