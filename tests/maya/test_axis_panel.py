"""maroAxisPanel의 순수 함수(sliceAxisRows/sliceCapabilityRows)만 검증한다.
QWidget 생성은 배치 모드에서 프로세스를 abort시키므로(모듈 도크스트링
참고) 여기서 AxisPanel/buildWidget은 절대 부르지 않는다."""
import os
import sys

_pythonDir = os.path.join(os.path.dirname(__file__), "..", "..", "python")
sys.path.insert(0, _pythonDir)

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

# 설계 스펙 §4.2: 새 .py는 setStyleSheet()를 부르지 않는다 -- Maya 프로세스
# 전역 QApplication의 팔레트/스타일을 그대로 물려받아야 기존 mayaUI와
# 이질감이 없다(test_main_window.py의 같은 점검과 같은 이유, 같은 기법).
#
# 찾는 문자열이 "setStyleSheet("가 아니라 ".setStyleSheet("인 이유도 같다:
# 그 규율을 설명하는 주석/도크스트링 자체가 이름을 언급하므로, 점이 앞에
# 붙는 실제 호출만 걸리고 규율을 적어 둔 산문은 걸리지 않는다.
_axisPanelSource = os.path.join(_pythonDir, "maroAxisPanel.py")
with open(_axisPanelSource, encoding="utf-8") as _handle:
    _source = _handle.read()
assert ".setStyleSheet(" not in _source, (
    "maroAxisPanel.py must not call setStyleSheet() -- it has to inherit "
    "Maya's global Qt style (design spec 4.2)"
)
print("no setStyleSheet OK")

print("teardown OK")
sys.exit(0)
