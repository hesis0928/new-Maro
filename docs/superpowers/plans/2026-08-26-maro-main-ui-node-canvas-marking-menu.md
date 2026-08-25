# Maro 메인 UI — 노드 캔버스 + 방사형 마킹 메뉴 (SONE/ONE) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the list-based `maroAxisPanel.AxisPanel` with a Maya-native marking-menu-driven axis/capability editor: a per-axis popup (**SONE**) opened from Maya's own object right-click menu, and an overview grid of all axes (**ONE**) embedded in MaroUI's bottom pane.

**Architecture:** Three layers — a `dagMenuProc` MEL chain that adds a `Maro node editor` item to Maya's native object marking menu; **SONE** (`maroSingleObjectNodeEditor.py`), a modeless popup scoped to one axis that implements the radial marking-menu interaction against Phase 4's existing commands; **ONE** (`maroObjectNodeEditor.py`), a grid of grouped nodes (GSON) embedded in `maroMainWindow.py`'s `editorHost` that re-opens SONE popups. Two new plain-data attributes (`aDisplayName`/`aDisplayColor`) are added to `MaroAxisNode` for GSON labeling; no new C++ commands are needed.

**Tech Stack:** C++ (Maya OpenMaya API, MSVC via VS2022 dev shell), Python 3 (`maya.cmds`, `PySide6`, `shiboken6`), mayapy batch tests for pure functions, CMake/CTest.

**Spec:** `docs/superpowers/specs/2026-08-25-maro-main-ui-node-canvas-marking-menu-design.md`

## Global Constraints

- Build always with `--config Release`; `ctest --test-dir out/build -C Release --output-on-failure` must pass fully before any task is considered done.
- New/modified `.py` files never call `setStyleSheet()` (grepped by `tests/maya/test_main_window.py`'s existing pattern; mirror it in the new SONE/ONE test files).
- `aDisplayName`/`aDisplayColor` must not participate in `compute()` or `attributeAffects` — they are pure UI bookkeeping, same treatment as the existing non-computed outputs in `MaroAxisNode.cpp`.
- `dagMenuProc` chaining must preserve whatever proc existed before load and restore it exactly on unload — this hook is process-global and shared with other tools.
- `maroObjectNodeEditor.py`'s `buildWidget()` / `start()` / `stop()` entry-point names and no-argument signatures must match exactly what `maroMainWindow.py` already calls (today via `maroAxisPanel`) — only the import name changes.
- `AXIS_FIELDS` grows from 8 to 10 fields — every reader of `maroListAxisNodes()`'s flat array (Python and tests) must be updated in the same task as the C++ change that produces the new field count.
- SONE is a singleton per axis: reopening (native menu or GSON double-click) must raise the existing popup, never create a second one for the same axis.
- Every task's implementer runs the full build+test command from the spec after their change:
  ```powershell
  cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
      if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
  }
  cmake --build out/build --config Release
  ctest --test-dir out/build -C Release --output-on-failure
  ```

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `src/maro_plugin/MaroAxisNode.h` / `.cpp` | Modify | Add `aDisplayName`/`aDisplayColor` |
| `src/maro_plugin/MaroAxisEditorCommands.cpp` | Modify | `maroListAxisNodes` emits the 2 new fields (10 total) |
| `tests/maya/test_axis_editor_commands.py` | Modify | Round-trip + field-count tests for the new attributes |
| `python/maroSingleObjectNodeEditor.py` | Create | SONE: pure layout/hit-test functions + the popup widget |
| `python/maroObjectNodeEditor.py` | Create | ONE: pure grid-layout function + the embedded widget (replaces `maroAxisPanel.py`) |
| `python/maroAxisPanel.py` | Delete | Superseded by `maroObjectNodeEditor.py` |
| `python/maroDagMenu.py` | Create | `dagMenuProc` chaining install/uninstall |
| `python/maroMainWindow.py` | Modify | Import `maroObjectNodeEditor` instead of `maroAxisPanel` |
| `src/maro_plugin/MaroPluginMain.cpp` | Modify | Call `maroDagMenu.install()`/`uninstall()` at load/unload |
| `src/maro_plugin/CMakeLists.txt` | Modify | Add new `.py` modules to `MARO_PLUGIN_PY_MODULES`, remove `maroAxisPanel` |
| `tests/CMakeLists.txt` | Modify | Swap the `maya_axis_panel` test entry for the two new pure-function test files |
| `tests/maya/test_axis_panel.py` | Delete | Superseded by the two new test files below |
| `tests/maya/test_single_object_node_editor.py` | Create | Pure-function tests for SONE |
| `tests/maya/test_object_node_editor.py` | Create | Pure-function tests for ONE |
| `docs/maro-main-ui-manual-checklist.md` | Modify | New manual-verification section for this feature |

---

### Task 1: `MaroAxisNode` — add `aDisplayName`/`aDisplayColor`

**Files:**
- Modify: `src/maro_plugin/MaroAxisNode.h`
- Modify: `src/maro_plugin/MaroAxisNode.cpp`
- Test: `tests/maya/test_axis_editor_commands.py`

**Interfaces:**
- Produces: `MaroAxisNode::aDisplayName` (string, storable), `MaroAxisNode::aDisplayColor` (float3 color, storable). Neither affects `compute()`.

- [ ] **Step 1: Write the failing test**

Append to the end of `tests/maya/test_axis_editor_commands.py` (this file is a plain mayapy script using `assert`, not pytest — follow its existing style):

```python
# --- aDisplayName/aDisplayColor round-trip (Task 1) ---
displayAxis = cmds.createNode("maroAxis", name="displayAxis1")
cmds.setAttr(displayAxis + ".displayName", "My Axis", type="string")
cmds.setAttr(displayAxis + ".displayColor", 0.2, 0.6, 0.9, type="double3")
assert cmds.getAttr(displayAxis + ".displayName") == "My Axis", \
    "displayName did not round-trip"
color = cmds.getAttr(displayAxis + ".displayColor")[0]
assert abs(color[0] - 0.2) < 1e-6 and abs(color[1] - 0.6) < 1e-6 and abs(color[2] - 0.9) < 1e-6, \
    f"displayColor did not round-trip: {color}"
print("aDisplayName/aDisplayColor round-trip OK")
```

- [ ] **Step 2: Run test to verify it fails**

Run (adjust `mayapy.exe` path to the installed Maya version if different):
```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_axis_editor_commands.py
```
Expected: FAIL — `displayName` is not a known attribute of `maroAxis` yet.

- [ ] **Step 3: Add the attributes in `MaroAxisNode.h`**

In the `public:` section, alongside the existing `aJointName`/`aConventionAxis` group (after the "// 설정" comment block), add:

```cpp
    static MObject aDisplayName;    // string -- MaroUI ONE(GSON)/SONE 표시용 라벨.
                                     // jointName(ROS 발행에 실제로 쓰이는 값)과는
                                     // 완전히 별개다.
    static MObject aDisplayColor;   // float3 색상 -- GSON 색. compute()에 관여하지
                                     // 않는 순수 UI 데이터, attributeAffects 대상 아님.
```

- [ ] **Step 4: Define and register them in `MaroAxisNode.cpp`**

Add the static definitions alongside the others near the top (after `MObject MaroAxisNode::aConventionInvert;`):

```cpp
MObject MaroAxisNode::aDisplayName;
MObject MaroAxisNode::aDisplayColor;
```

In `initialize()`, add right after the `aConventionInvert` block (which ends with `addAttribute(aConventionInvert);`):

```cpp
    aDisplayName = typFn.create("displayName", "dpn", MFnData::kString);
    typFn.setStorable(true);
    addAttribute(aDisplayName);

    aDisplayColor = numFn.createColor("displayColor", "dpc");
    numFn.setStorable(true);
    addAttribute(aDisplayColor);
```

Do **not** add either to any `attributeAffects()` call — matching the file's own documented rule for `aConventionInvert` ("안 읽는 소스를 영향권에 넣으면... 재계산을 낭비한다").

- [ ] **Step 5: Build**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```
Expected: builds cleanly.

- [ ] **Step 6: Run test to verify it passes**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_axis_editor_commands.py
```
Expected: prints `aDisplayName/aDisplayColor round-trip OK` and exits 0.

- [ ] **Step 7: Run the full suite**

```powershell
ctest --test-dir out/build -C Release --output-on-failure
```
Expected: all green (no other test reads a fixed `maroAxis` attribute count, so this addition should not break anything else).

- [ ] **Step 8: Commit**

```bash
git add src/maro_plugin/MaroAxisNode.h src/maro_plugin/MaroAxisNode.cpp tests/maya/test_axis_editor_commands.py
git commit -m "feat: add aDisplayName/aDisplayColor to maroAxis for UI labeling"
```

---

### Task 2: `maroListAxisNodes` emits the 2 new fields (AXIS_FIELDS 8 → 10)

**Files:**
- Modify: `src/maro_plugin/MaroAxisEditorCommands.cpp:73-95` (the `listAxes()` function)
- Test: `tests/maya/test_axis_editor_commands.py`

**Interfaces:**
- Consumes: `MaroAxisNode::aDisplayName`, `MaroAxisNode::aDisplayColor` (Task 1).
- Produces: `maroListAxisNodes()` (no-flag mode) now returns a flat array whose length is a multiple of **10**, with `field[8] = displayName` and `field[9] = "r,g,b"` (each channel formatted with the default `MString` double-to-string conversion via `<<`).

- [ ] **Step 1: Write the failing test**

Update the constant near the top of `tests/maya/test_axis_editor_commands.py`:

```python
AXIS_FIELDS = 10
```

Add a new assertion block right after the existing "maroListAxisNodes, 플래그 없음" block (after the `print("maroListAxisNodes (no flag) OK")` line):

```python
# --- displayName/displayColor fields (Task 2) ---
cmds.setAttr(axis1 + ".displayName", "Axis One", type="string")
cmds.setAttr(axis1 + ".displayColor", 0.1, 0.5, 0.8, type="double3")
rows = cmds.maroListAxisNodes()
assert len(rows) % AXIS_FIELDS == 0, f"row array length {len(rows)} not a multiple of {AXIS_FIELDS}"
found = None
for i in range(len(rows) // AXIS_FIELDS):
    f = rows[i * AXIS_FIELDS:(i + 1) * AXIS_FIELDS]
    if f[0].endswith("listAxis1"):
        found = f
        break
assert found is not None, "listAxis1 missing after AXIS_FIELDS change"
assert found[8] == "Axis One", f"displayName field wrong: {found[8]}"
parts = found[9].split(",")
assert len(parts) == 3, f"displayColor field must be 'r,g,b': {found[9]}"
assert abs(float(parts[0]) - 0.1) < 1e-4, f"displayColor r wrong: {found[9]}"
assert abs(float(parts[1]) - 0.5) < 1e-4, f"displayColor g wrong: {found[9]}"
assert abs(float(parts[2]) - 0.8) < 1e-4, f"displayColor b wrong: {found[9]}"
print("displayName/displayColor fields OK")
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_axis_editor_commands.py
```
Expected: FAIL on the `len(rows) % AXIS_FIELDS == 0` assertion (rows still has 8 fields per axis, `AXIS_FIELDS` is now 10, so unless the axis count divides evenly it fails the modulo check; if it happens to divide evenly the later `found[8]` index access will raise `IndexError` instead — either way it fails).

- [ ] **Step 3: Extend `listAxes()` in `MaroAxisEditorCommands.cpp`**

Add two lines right after the existing `result.append(MString() + static_cast<int>(occupiedCapabilityCount(...)));` line inside `listAxes()`:

```cpp
        result.append(axisFn.findPlug(MaroAxisNode::aDisplayName, false).asString());

        MPlug colorPlug = axisFn.findPlug(MaroAxisNode::aDisplayColor, false);
        std::ostringstream colorStream;
        colorStream << colorPlug.child(0).asFloat() << ","
                    << colorPlug.child(1).asFloat() << ","
                    << colorPlug.child(2).asFloat();
        result.append(MString(colorStream.str().c_str()));
```

(`<sstream>` is already included at the top of this file.)

- [ ] **Step 4: Build**

```powershell
cmake --build out/build --config Release
```

- [ ] **Step 5: Run test to verify it passes**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_axis_editor_commands.py
```
Expected: prints `displayName/displayColor fields OK` and all earlier assertions in the file still pass (they were updated to use `AXIS_FIELDS = 10` in Step 1, so index math stays correct).

- [ ] **Step 6: Run the full suite**

```powershell
ctest --test-dir out/build -C Release --output-on-failure
```
Expected: all green. `tests/maya/test_axis_panel.py` (old, still `AXIS_FIELDS = 8` at this point) is expected to now FAIL here — that is fine, it gets deleted in Task 6; do not fix it in this task.

- [ ] **Step 7: Commit**

```bash
git add src/maro_plugin/MaroAxisEditorCommands.cpp tests/maya/test_axis_editor_commands.py
git commit -m "feat: emit displayName/displayColor from maroListAxisNodes (AXIS_FIELDS 8->10)"
```

---

### Task 3: SONE pure functions

**Files:**
- Create: `python/maroSingleObjectNodeEditor.py`
- Test: `tests/maya/test_single_object_node_editor.py`

**Interfaces:**
- Consumes: `cmds.maroListAxisNodes(capabilities=axis)` (5-field flat array, unchanged from Phase 4).
- Produces (all pure, no Maya UI, importable and callable under batch mayapy):
  - `CAPABILITY_FIELDS = 5`
  - `sliceCapabilityRows(flat) -> list[dict]` with keys `logicalIndex`, `capabilityNodeName`, `capabilityNodeType`, `capType`, `connected`.
  - `computeRadialLayout(centerX, centerY, itemCount, radius) -> list[tuple[float, float]]` — one `(x, y)` per item, evenly spaced starting at the top (`-90°`) going clockwise. `itemCount` may be 0 (returns `[]`).
  - `hitTestRadialItem(cursorX, cursorY, itemPositions, itemHalfWidth, itemHalfHeight) -> int | None` — index of the item whose axis-aligned box (centered at its position, half-extents given) contains the cursor point, or `None`.
  - `indexOfCapabilityToPeel(capabilityRows) -> int | None` — the `logicalIndex` of the row with the greatest `logicalIndex` among rows where `connected` is `True`, or `None` if no row is connected. This is the "Delete removes the most-recently-added capability" rule from spec §5.3.

- [ ] **Step 1: Write the failing tests**

Create `tests/maya/test_single_object_node_editor.py` (plain mayapy script, mirrors `test_axis_editor_commands.py`'s style — no pytest, `assert` + `print`, run directly by mayapy):

```python
import math

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
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_single_object_node_editor.py
```
Expected: FAIL with `ModuleNotFoundError: No module named 'maroSingleObjectNodeEditor'` (the file doesn't exist yet). Run it with `python` on the module's directory on `PYTHONPATH`, e.g.:
```powershell
$env:PYTHONPATH = "C:\Users\ckd30\Projects\Maya_Ros_Sim\python"
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_single_object_node_editor.py
```
(Match however the existing `tests/maya/*.py` scripts get `python/` on `sys.path` — check `tests/CMakeLists.txt`'s existing `maya_axis_panel`/`maya_diag_panel` entries for the exact mechanism already in use, e.g. an `ENVIRONMENT` line setting `PYTHONPATH`, and reuse the same pattern rather than inventing a new one.)

- [ ] **Step 3: Write `python/maroSingleObjectNodeEditor.py`** (pure-function section only for this task)

```python
"""SONE -- 싱글 오브젝트 노드 에디터. 축 하나의 capability 스택을 방사형
마킹 메뉴로 편집하는 독립 팝업이다 (설계 스펙 2026-08-25-...-v2 §5).

이 파일의 순수 함수는 Maya에 의존하지 않는다 -- mayapy 배치 모드에서
QWidget 없이 계약을 검증한다 (maroDiagPanel.py의 sliceRows와 같은 이유).
"""
import math

# C++ 쪽 계약. 바뀌면 MaroAxisEditorCommands.cpp의 listCapabilities()도
# 함께 고쳐야 한다.
CAPABILITY_FIELDS = 5


def sliceCapabilityRows(flat):
    """maroListAxisNodes(capabilities=axis)의 평탄한 배열을 capability 행
    딕셔너리 목록으로 되돌린다."""
    if flat is None:
        return []
    if len(flat) % CAPABILITY_FIELDS != 0:
        raise ValueError(
            "capability row array length {} is not a multiple of {}".format(
                len(flat), CAPABILITY_FIELDS))
    rows = []
    for i in range(len(flat) // CAPABILITY_FIELDS):
        f = flat[i * CAPABILITY_FIELDS:(i + 1) * CAPABILITY_FIELDS]
        rows.append({
            "logicalIndex": int(f[0]),
            "capabilityNodeName": f[1],
            "capabilityNodeType": f[2],
            "capType": int(f[3]),
            "connected": f[4] == "1",
        })
    return rows


def computeRadialLayout(centerX, centerY, itemCount, radius):
    """중심(centerX, centerY) 주위로 itemCount개 항목을 원형으로 배치한다.
    첫 항목은 정확히 위쪽(각도 -90도)에서 시작해 시계 방향으로 균등
    분배된다."""
    if itemCount <= 0:
        return []
    positions = []
    step = 2.0 * math.pi / itemCount
    for i in range(itemCount):
        angle = -math.pi / 2.0 + i * step
        x = centerX + radius * math.cos(angle)
        y = centerY + radius * math.sin(angle)
        positions.append((x, y))
    return positions


def hitTestRadialItem(cursorX, cursorY, itemPositions, itemHalfWidth, itemHalfHeight):
    """커서가 어느 항목의 축정렬 박스 안에 있는지. 여러 박스가 겹치면
    먼저 등장한(=itemPositions의 앞) 항목이 이긴다. 없으면 None."""
    for index, (x, y) in enumerate(itemPositions):
        if (abs(cursorX - x) <= itemHalfWidth and
                abs(cursorY - y) <= itemHalfHeight):
            return index
    return None


def indexOfCapabilityToPeel(capabilityRows):
    """Delete(접힌 상태)가 지울 항목의 logicalIndex -- 연결된 행 중
    가장 큰 logicalIndex. 연결된 행이 없으면 None(더 지울 것이 없음,
    이미 undefined)."""
    connectedIndices = [row["logicalIndex"] for row in capabilityRows if row["connected"]]
    if not connectedIndices:
        return None
    return max(connectedIndices)
```

- [ ] **Step 4: Run test to verify it passes**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_single_object_node_editor.py
```
Expected: prints all four `OK` lines and exits 0.

- [ ] **Step 5: Register the test in `tests/CMakeLists.txt`**

Find the existing `maya_axis_panel` (or equivalently-named) standalone mayapy test entry (the one added for the old `maroAxisPanel.py` pure functions, run via mayapy without `maya.standalone`) and add a sibling entry for this new file using the exact same mechanism (working directory, `PYTHONPATH`/environment setup, mayapy invocation). Name it `maya_single_object_node_editor`.

- [ ] **Step 6: Build and run the full suite**

```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure
```
Expected: the new `maya_single_object_node_editor` test appears and passes; nothing else regresses.

- [ ] **Step 7: Commit**

```bash
git add python/maroSingleObjectNodeEditor.py tests/maya/test_single_object_node_editor.py tests/CMakeLists.txt
git commit -m "feat: add SONE pure functions (radial layout, hit-test, capability peel)"
```

---

### Task 4: SONE popup widget

**Files:**
- Modify: `python/maroSingleObjectNodeEditor.py` (add the widget on top of Task 3's pure functions)

**Interfaces:**
- Consumes: `computeRadialLayout`, `hitTestRadialItem`, `sliceCapabilityRows`, `indexOfCapabilityToPeel` (Task 3); `cmds.maroListAxisNodes(capabilities=axis)`, `cmds.maroAddCapability(axis, type=...)`, `cmds.maroDisconnectCapability(axis, index=...)`, `cmds.maroUnbindAxis(axis)` (all pre-existing Phase 4 commands); `cmds.maroListAxisNodes()` for the Coupling source-axis dropdown.
- Produces: `openSingleObjectNodeEditor(axis)` — module-level function. If a SONE for `axis` is already open, raises that window and returns it; otherwise builds a new one. This is the single entry point both `maroDagMenu.py` (Task 8) and `maroObjectNodeEditor.py`'s GSON double-click (Task 6) call.

This task has **no automated test** — a `QWidget` with real mouse/paint event handling cannot be constructed under batch mayapy (`maroMainWindow.py`'s own module docstring: batch mayapy's global application object is `QGuiApplication`, not `QApplication`, and creating a `QWidget` aborts the process). Verification is the manual checklist item added in Task 9. Build only; no `ctest` step changes expected here.

- [ ] **Step 1: Add the widget class to `python/maroSingleObjectNodeEditor.py`**

Append below the pure functions from Task 3:

```python
CAPABILITY_TYPES = [
    ("rotation", "Rotation"),
    ("translation", "Translation"),
    ("limit", "Limit"),
    ("translationLimit", "TranslationLimit"),
    ("sensorDirection", "SensorDirection"),
    ("sensorRange", "SensorRange"),
    ("coupling", "Coupling"),
]

_ITEM_HALF_WIDTH = 55.0
_ITEM_HALF_HEIGHT = 16.0
_MENU_RADIUS = 90.0
_DRAG_THRESHOLD_PX = 6.0

_OPEN_EDITORS = {}  # axisFullPath -> MaroSingleObjectNodeEditor


def openSingleObjectNodeEditor(axis):
    """axis의 SONE를 연다. 이미 열려 있으면 그 창을 앞으로 가져온다.
    (설계 스펙 §2: "SONE는 축마다 유일하게 존재")"""
    existing = _OPEN_EDITORS.get(axis)
    if existing is not None:
        try:
            existing.raise_()
            existing.activateWindow()
            return existing
        except RuntimeError:
            # Qt 쪽 객체가 이미 파괴됨(사용자가 닫음) -- 새로 만든다.
            del _OPEN_EDITORS[axis]

    editor = MaroSingleObjectNodeEditor(axis)
    _OPEN_EDITORS[axis] = editor
    editor.show()
    return editor


class MaroSingleObjectNodeEditor(QtWidgets.QWidget):
    """축 하나의 capability 스택을 방사형 마킹 메뉴로 편집하는 독립
    팝업(모덜리스). setStyleSheet()를 부르지 않는다 -- maroMainWindow.py와
    같은 규율.
    """

    def __init__(self, axis, parent=None):
        super().__init__(parent, QtCore.Qt.Window)
        self._axis = axis
        self._menuStack = []          # [(centerX, centerY, [(label, payload), ...]), ...]
        self._expanded = False        # 능력 2개 이상일 때 드롭다운 펼침 여부
        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)
        self._refreshTitle()

    def closeEvent(self, event):
        if _OPEN_EDITORS.get(self._axis) is self:
            del _OPEN_EDITORS[self._axis]
        super().closeEvent(event)

    def _refreshTitle(self):
        rows = cmds.maroListAxisNodes()
        displayName = self._axis
        for i in range(len(rows) // 10):
            f = rows[i * 10:(i + 1) * 10]
            if f[0] == self._axis and f[8]:
                displayName = f[8]
                break
        self.setWindowTitle(displayName)

    def _capabilityRows(self):
        if not cmds.objExists(self._axis):
            return []
        import maroSingleObjectNodeEditor as _self  # noqa: F401 -- self-import avoided below
        return sliceCapabilityRows(cmds.maroListAxisNodes(capabilities=self._axis))

    def _nodeLabel(self, rows):
        connected = [r for r in rows if r["connected"]]
        if not connected:
            return "undefined", False
        if len(connected) == 1:
            return connected[0]["capabilityNodeType"].replace("maro", ""), False
        return connected[-1]["capabilityNodeType"].replace("maro", "") + " \u25be", True

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        rows = self._capabilityRows()
        label, hasDropdown = self._nodeLabel(rows)
        cx, cy = self.width() / 2.0, self.height() / 2.0
        nodeRect = QtCore.QRectF(cx - 60, cy - 18, 120, 36)
        pen = QtGui.QPen(QtCore.Qt.DashLine if label == "undefined" else QtCore.Qt.SolidLine)
        painter.setPen(pen)
        painter.drawRoundedRect(nodeRect, 6, 6)
        painter.drawText(nodeRect, QtCore.Qt.AlignCenter, label)

        if self._expanded and len(rows) > 0:
            connected = sorted([r for r in rows if r["connected"]], key=lambda r: r["logicalIndex"])
            y = nodeRect.bottom() + 8
            for row in connected:
                itemRect = QtCore.QRectF(cx - 70, y, 140, 22)
                painter.drawRect(itemRect)
                painter.drawText(itemRect, QtCore.Qt.AlignCenter,
                                 "{}. {}".format(row["logicalIndex"], row["capabilityNodeType"]))
                y += 24

        for level, (mcx, mcy, items) in enumerate(self._menuStack):
            opacity = 0.35 if level < len(self._menuStack) - 1 else 1.0
            painter.setOpacity(opacity)
            positions = computeRadialLayout(mcx, mcy, len(items), _MENU_RADIUS)
            for (labelText, _payload), (ix, iy) in zip(items, positions):
                itemRect = QtCore.QRectF(ix - _ITEM_HALF_WIDTH, iy - _ITEM_HALF_HEIGHT,
                                         _ITEM_HALF_WIDTH * 2, _ITEM_HALF_HEIGHT * 2)
                painter.drawRoundedRect(itemRect, 6, 6)
                painter.drawText(itemRect, QtCore.Qt.AlignCenter, labelText)
            painter.setOpacity(1.0)
            if level > 0:
                backRect = QtCore.QRectF(self.width() - 90, mcy - 12, 80, 24)
                painter.drawRoundedRect(backRect, 4, 4)
                painter.drawText(backRect, QtCore.Qt.AlignCenter, "\u25c0 \uc0c1\uc704\ub85c")

    def _leafItems(self):
        return [(label, ("leaf", flagName)) for flagName, label in CAPABILITY_TYPES]

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.RightButton:
            return
        self._pressPos = event.position() if hasattr(event, "position") else event.localPos()
        self._menuStack = [(self._pressPos.x(), self._pressPos.y(), self._leafItems())]
        self.update()

    def mouseMoveEvent(self, event):
        if not self._menuStack:
            return
        pos = event.position() if hasattr(event, "position") else event.localPos()
        moved = math.hypot(pos.x() - self._pressPos.x(), pos.y() - self._pressPos.y())
        if moved < _DRAG_THRESHOLD_PX:
            return
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != QtCore.Qt.RightButton or not self._menuStack:
            return
        pos = event.position() if hasattr(event, "position") else event.localPos()
        moved = math.hypot(pos.x() - self._pressPos.x(), pos.y() - self._pressPos.y())
        if moved < _DRAG_THRESHOLD_PX:
            self._menuStack = []
            self.update()
            return

        mcx, mcy, items = self._menuStack[-1]
        positions = computeRadialLayout(mcx, mcy, len(items), _MENU_RADIUS)
        index = hitTestRadialItem(pos.x(), pos.y(), positions, _ITEM_HALF_WIDTH, _ITEM_HALF_HEIGHT)
        self._menuStack = []
        if index is not None:
            _label, (kind, flagName) = items[index]
            if kind == "leaf":
                self._applyCapability(flagName)
        self.update()

    def _applyCapability(self, flagName):
        try:
            cmds.maroAddCapability(self._axis, type=flagName)
        except RuntimeError as error:
            print("Maro: maroAddCapability failed -- {}".format(error))
            return
        self.update()

    def mouseDoubleClickEvent(self, event):
        rows = self._capabilityRows()
        connected = [r for r in rows if r["connected"]]
        if len(connected) >= 2:
            self._expanded = not self._expanded
            self.update()

    def keyPressEvent(self, event):
        if event.key() != QtCore.Qt.Key_Delete:
            return
        rows = self._capabilityRows()
        target = indexOfCapabilityToPeel(rows)
        if target is None:
            return
        try:
            cmds.maroDisconnectCapability(self._axis, index=target)
        except RuntimeError as error:
            print("Maro: maroDisconnectCapability failed -- {}".format(error))
            return
        self.update()
```

Add these imports at the top of the file (below the existing `import math`):

```python
import maya.cmds as cmds
from PySide6 import QtCore, QtGui, QtWidgets
```

**Note for the implementer:** `mousePressEvent`/`mouseMoveEvent` in PySide6 give `event.position()` on newer Qt6 builds and `event.localPos()` on older ones — the `hasattr` guard above handles both; verify empirically against the Maya-bundled PySide6 version (`python -c "import PySide6.QtCore; print(PySide6.__version__)"` from `mayapy`) before assuming one branch is dead code.

- [ ] **Step 2: Build and run the full suite**

```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure
```
(No C++ changed in this task, but re-run both to confirm nothing else broke, per the Global Constraints' per-task discipline.)

- [ ] **Step 3: Manual smoke check** (interactive Maya, not automated — full checklist entry comes in Task 9)

```python
import maya.cmds as cmds
cmds.loadPlugin("maro")
cube = cmds.polyCube()[0]
axis = cmds.createNode("maroAxis")
cmds.maroBindAxis(axis, cube)
import maroSingleObjectNodeEditor as sone
sone.openSingleObjectNodeEditor(axis)
```
Confirm: popup opens showing `undefined`; right-click-hold-drag opens a ring of 7 items; releasing on `Rotation` applies it and the node label changes; calling `openSingleObjectNodeEditor(axis)` again raises the same window instead of creating a second one.

- [ ] **Step 4: Commit**

```bash
git add python/maroSingleObjectNodeEditor.py
git commit -m "feat: implement the SONE popup widget (radial marking menu, delete, dropdown)"
```

---

### Task 5: ONE pure functions

**Files:**
- Create: `python/maroObjectNodeEditor.py`
- Test: `tests/maya/test_object_node_editor.py`

**Interfaces:**
- Consumes: `cmds.maroListAxisNodes()` (10-field flat array from Task 2).
- Produces:
  - `AXIS_FIELDS = 10`
  - `sliceAxisRows(flat) -> list[dict]` with keys `axisFullPath`, `jointName`, `boundTargetPath`, `parentAxisPath`, `controlMode`, `enabled`, `conventionAxis`, `capabilityCount`, `displayName`, `displayColor` (the last as a `(r, g, b)` float tuple, parsed from the `"r,g,b"` string field).
  - `computeGsonGridLayout(count, columns, cellWidth, cellHeight, gap) -> list[tuple[float, float]]` — top-left `(x, y)` for each of `count` cells, filling left-to-right then wrapping to the next row after `columns` cells.

- [ ] **Step 1: Write the failing tests**

Create `tests/maya/test_object_node_editor.py` (same plain-script style):

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
$env:PYTHONPATH = "C:\Users\ckd30\Projects\Maya_Ros_Sim\python"
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_object_node_editor.py
```
Expected: FAIL — module does not exist yet.

- [ ] **Step 3: Write `python/maroObjectNodeEditor.py`** (pure-function section only for this task)

```python
"""ONE -- 오브젝트 노드 에디터. MaroUI 하단에 임베드되어 지금까지 만들어진
SONE들을 GSON(그루핑된 노드)으로 조망한다 (설계 스펙 2026-08-25-...-v2 §6).
"""
import maya.cmds as cmds

# C++ 쪽 계약. 바뀌면 MaroAxisEditorCommands.cpp의 listAxes()도 함께 고쳐야
# 한다.
AXIS_FIELDS = 10


def sliceAxisRows(flat):
    """maroListAxisNodes()의 평탄한 배열을 축 행 딕셔너리 목록으로
    되돌린다."""
    if flat is None:
        return []
    if len(flat) % AXIS_FIELDS != 0:
        raise ValueError(
            "axis row array length {} is not a multiple of {}".format(
                len(flat), AXIS_FIELDS))
    rows = []
    for i in range(len(flat) // AXIS_FIELDS):
        f = flat[i * AXIS_FIELDS:(i + 1) * AXIS_FIELDS]
        r, g, b = (float(v) for v in f[9].split(","))
        rows.append({
            "axisFullPath": f[0],
            "jointName": f[1],
            "boundTargetPath": f[2],
            "parentAxisPath": f[3],
            "controlMode": int(f[4]),
            "enabled": f[5] == "1",
            "conventionAxis": int(f[6]),
            "capabilityCount": int(f[7]),
            "displayName": f[8],
            "displayColor": (r, g, b),
        })
    return rows


def computeGsonGridLayout(count, columns, cellWidth, cellHeight, gap):
    """count개의 GSON을 생성 순서대로 자동 그리드 배치한다. 각 셀의
    좌상단 (x, y)를 반환. columns개마다 다음 줄로 넘어간다."""
    positions = []
    for i in range(count):
        col = i % columns
        row = i // columns
        x = col * (cellWidth + gap)
        y = row * (cellHeight + gap)
        positions.append((x, y))
    return positions
```

- [ ] **Step 4: Run test to verify it passes**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_object_node_editor.py
```
Expected: both `OK` lines print, exit 0.

- [ ] **Step 5: Register the test in `tests/CMakeLists.txt`**

Add a `maya_object_node_editor` entry next to `maya_single_object_node_editor` (Task 3), same mechanism.

- [ ] **Step 6: Build and run the full suite**

```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure
```

- [ ] **Step 7: Commit**

```bash
git add python/maroObjectNodeEditor.py tests/maya/test_object_node_editor.py tests/CMakeLists.txt
git commit -m "feat: add ONE pure functions (axis row slicing, GSON grid layout)"
```

---

### Task 6: ONE widget, wiring into `maroMainWindow.py`, delete `maroAxisPanel.py`

**Files:**
- Modify: `python/maroObjectNodeEditor.py` (add the widget on top of Task 5's pure functions)
- Modify: `python/maroMainWindow.py:192-212,262-267,288-293` (swap the `maroAxisPanel` import for `maroObjectNodeEditor`)
- Delete: `python/maroAxisPanel.py`
- Delete: `tests/maya/test_axis_panel.py`
- Modify: `src/maro_plugin/CMakeLists.txt` (`MARO_PLUGIN_PY_MODULES` list)
- Modify: `tests/CMakeLists.txt` (remove the old `maya_axis_panel` entry, already added the two new ones in Tasks 3/5)

**Interfaces:**
- Consumes: `sliceAxisRows`, `computeGsonGridLayout` (Task 5), `openSingleObjectNodeEditor` (Task 4).
- Produces: `buildWidget()`, `start()`, `stop()` — same no-argument signatures `maroMainWindow.py` already calls today via `maroAxisPanel`.

No automated test for the widget class itself (same reasoning as Task 4 — real `QWidget` mouse/paint behavior needs an interactive session). This task's test-facing work is the deletions/renames above, verified by the full suite staying green.

- [ ] **Step 1: Add the widget class to `python/maroObjectNodeEditor.py`**

Append below the Task 5 pure functions:

```python
import maya.OpenMayaUI as omui
import shiboken6
from PySide6 import QtCore, QtGui, QtWidgets

import maroSingleObjectNodeEditor

_JOB_ID = None
_PANEL = None

_GRID_COLUMNS = 4
_CELL_WIDTH = 140.0
_CELL_HEIGHT = 50.0
_GRID_GAP = 12.0


class ObjectNodeEditor(QtWidgets.QWidget):
    """GSON 그리드. setStyleSheet()를 부르지 않는다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selectedAxis = None

    def refresh(self):
        self.update()

    def _rows(self):
        return sliceAxisRows(cmds.maroListAxisNodes())

    def _gsonRects(self):
        rows = self._rows()
        positions = computeGsonGridLayout(
            len(rows), _GRID_COLUMNS, _CELL_WIDTH, _CELL_HEIGHT, _GRID_GAP)
        return list(zip(rows, positions))

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        for row, (x, y) in self._gsonRects():
            rect = QtCore.QRectF(x + 4, y + 4, _CELL_WIDTH - 8, _CELL_HEIGHT - 8)
            r, g, b = row["displayColor"]
            painter.setBrush(QtGui.QColor.fromRgbF(r, g, b))
            painter.drawRoundedRect(rect, 6, 6)
            painter.drawText(rect, QtCore.Qt.AlignCenter,
                             row["displayName"] or row["axisFullPath"])

    def _axisAt(self, pos):
        for row, (x, y) in self._gsonRects():
            rect = QtCore.QRectF(x, y, _CELL_WIDTH, _CELL_HEIGHT)
            if rect.contains(pos):
                return row["axisFullPath"], row["boundTargetPath"]
        return None, None

    def mousePressEvent(self, event):
        pos = event.position() if hasattr(event, "position") else event.localPos()
        axis, target = self._axisAt(pos)
        if axis is None:
            return
        self._selectedAxis = axis
        cmds.select(target if target else axis, replace=True)

    def mouseDoubleClickEvent(self, event):
        pos = event.position() if hasattr(event, "position") else event.localPos()
        axis, _target = self._axisAt(pos)
        if axis is not None:
            maroSingleObjectNodeEditor.openSingleObjectNodeEditor(axis)

    def contextMenuEvent(self, event):
        axis, _target = self._axisAt(event.pos())
        if axis is None:
            return
        menu = QtWidgets.QMenu(self)
        renameAction = menu.addAction("Rename")
        recolorAction = menu.addAction("Recolor")
        deleteAction = menu.addAction("Delete")
        chosen = menu.exec(event.globalPos())
        if chosen is renameAction:
            newName, ok = QtWidgets.QInputDialog.getText(self, "Rename", "Display name:")
            if ok:
                cmds.setAttr(axis + ".displayName", newName, type="string")
                self.refresh()
        elif chosen is recolorAction:
            current = [c for r in self._rows() if r["axisFullPath"] == axis
                      for c in [r["displayColor"]]][0]
            color = QtWidgets.QColorDialog.getColor(
                QtGui.QColor.fromRgbF(*current), self)
            if color.isValid():
                cmds.setAttr(axis + ".displayColor",
                             color.redF(), color.greenF(), color.blueF(), type="double3")
                self.refresh()
        elif chosen is deleteAction:
            cmds.delete(axis)
            self.refresh()


def _onSceneSelectionChanged():
    """씬 선택 -> GSON 하이라이트(설계 스펙 §6). 예외가 새어 나가면 안
    된다 -- SelectionChanged 콜백 경계 규율 (maroRosProxy._onIdle과 같은
    이유)."""
    try:
        if _PANEL is None:
            return
        _PANEL.refresh()
    except Exception:  # noqa: BLE001
        import traceback
        traceback.print_exc()


def buildWidget():
    """maroMainWindow.buildUI()가 editorHost에 임베드할 위젯을 만든다."""
    global _PANEL
    _PANEL = ObjectNodeEditor()
    return _PANEL


def start():
    global _JOB_ID
    if _JOB_ID is not None and cmds.scriptJob(exists=_JOB_ID):
        return
    jobId = cmds.scriptJob(event=["SelectionChanged", _onSceneSelectionChanged],
                            protected=True)
    if isinstance(jobId, int):
        _JOB_ID = jobId
    else:
        _JOB_ID = None
        if not cmds.about(batch=True):
            print("maroObjectNodeEditor: scriptJob() did not return a job id "
                  "({!r}) -- selection sync will not run.".format(jobId))


def stop():
    global _JOB_ID, _PANEL
    killSucceededOrJobGone = True
    try:
        if _JOB_ID is not None and cmds.scriptJob(exists=_JOB_ID):
            cmds.scriptJob(kill=_JOB_ID, force=True)
    except Exception:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        killSucceededOrJobGone = False

    if killSucceededOrJobGone:
        _JOB_ID = None
        _PANEL = None
```

Add `import maya.cmds as cmds` at the top of the file, alongside the existing plain imports from Task 5.

- [ ] **Step 2: Delete `python/maroAxisPanel.py` and `tests/maya/test_axis_panel.py`**

```bash
git rm python/maroAxisPanel.py tests/maya/test_axis_panel.py
```

- [ ] **Step 3: Update `python/maroMainWindow.py`**

Replace every `maroAxisPanel` reference with `maroObjectNodeEditor`:

At line ~197 (the `buildUI()` embed section):
```python
    import maroObjectNodeEditor
    axisPanelWidget = maroObjectNodeEditor.buildWidget()
```

At line ~266-267 (the end of `buildUI()`):
```python
    import maroObjectNodeEditor
    maroObjectNodeEditor.start()
```

In `teardown()` (line ~288-293):
```python
    try:
        import maroObjectNodeEditor
        maroObjectNodeEditor.stop()
    except Exception:  # noqa: BLE001 -- Maya 콜백/언로드 경계
        import traceback
        traceback.print_exc()
```

- [ ] **Step 4: Update `src/maro_plugin/CMakeLists.txt`**

In the `MARO_PLUGIN_PY_MODULES` list, remove `maroAxisPanel` and add `maroObjectNodeEditor` and `maroSingleObjectNodeEditor`.

- [ ] **Step 5: Update `tests/CMakeLists.txt`**

Remove the old `maya_axis_panel` entry (superseded by the `maya_single_object_node_editor`/`maya_object_node_editor` entries already added in Tasks 3/5).

- [ ] **Step 6: Update `tests/maya/test_ros_proxy_sync.py` if it references `maroAxisPanel`**

Grep for `maroAxisPanel` across `tests/`:
```powershell
Select-String -Path tests\maya\*.py -Pattern "maroAxisPanel"
```
Update any remaining literal-string assertions (e.g. checks against `teardown()`'s call chain) to reference `maroObjectNodeEditor` instead, following the same pattern `test_ros_proxy_sync.py` already used for the `maroRosProxy` -> `maroMainWindow.teardown()` change (per the Phase 4 history in `.superpowers/sdd/progress.md`).

- [ ] **Step 7: Build**

```powershell
cmake --build out/build --config Release
```

- [ ] **Step 8: Run the full suite**

```powershell
ctest --test-dir out/build -C Release --output-on-failure
```
Expected: all green — no test should still reference the deleted `maroAxisPanel.py`.

- [ ] **Step 9: Manual smoke check** (interactive Maya)

Load the plugin, open MaroUI (`cmds.maroMainWindow()`), confirm the bottom pane shows an (empty) grid area instead of the old list/button row, create an axis via script and confirm a GSON appears after calling `refresh()`/reopening.

- [ ] **Step 10: Commit**

```bash
git add python/maroObjectNodeEditor.py python/maroMainWindow.py src/maro_plugin/CMakeLists.txt tests/CMakeLists.txt
git commit -m "feat: implement ONE widget, wire into MaroUI, remove maroAxisPanel"
```

---

### Task 7: `dagMenuProc` chaining (`python/maroDagMenu.py`)

**Files:**
- Create: `python/maroDagMenu.py`
- Modify: `src/maro_plugin/MaroPluginMain.cpp` (call install/uninstall at load/unload)
- Modify: `src/maro_plugin/CMakeLists.txt` (add `maroDagMenu` to `MARO_PLUGIN_PY_MODULES`)

**Interfaces:**
- Produces: `install()`, `uninstall()` — no-argument, called once each via `runPluginPythonModule` from C++.

This is the highest-risk task in the plan (the spec's own §12 flags it explicitly). **Before writing the chaining logic, the implementer must empirically determine how Maya's installed `dagMenuProc` is structured** — do not assume a specific MEL trick works; verify it against the actual Maya installation first.

- [ ] **Step 1: Investigate the existing `dagMenuProc` empirically**

In an interactive `mayapy` or Script Editor session:
```mel
whatIs dagMenuProc;
```
This reports either `"Mel procedure found in: <path>"` (a real file backs it — read that file to see its exact structure and how it dispatches to node-type-specific menu procs) or `"Command"` / not found. Record the exact finding in the task's report — the chaining strategy in Step 3 below assumes the common case (a MEL-file-backed proc); if the investigation finds something different, stop and escalate rather than forcing the assumed approach.

- [ ] **Step 2: Write the failing manual check** (no automated test is possible here — record the expected manual result before implementing)

Expected behavior once `install()` works: after `cmds.loadPlugin("maro")`, right-clicking any DAG object in the viewport shows the normal Maya marking menu (Select/Select All/.../Material Attributes, as in the user's reference screenshot) **plus** a new `Maro node editor` item. After `cmds.unloadPlugin("maro")`, the item disappears and the original menu is unchanged.

- [ ] **Step 3: Write `python/maroDagMenu.py`**

```python
"""dagMenuProc 체이닝 -- Maya 오브젝트 마킹 메뉴에 'Maro node editor'
항목을 추가한다 (설계 스펙 2026-08-25-...-v2 §3).

dagMenuProc는 프로세스 전역 MEL 프로시저 하나뿐이다. 로드 시 기존 정의를
백업 이름으로 다시 소스해 보존하고, 우리 버전은 그 백업을 먼저 호출한 뒤
우리 항목을 덧붙인다. 언로드 시 원래 정의를 복원한다.
"""
import os
import tempfile

import maya.cmds as cmds
import maya.mel as mel

_BACKUP_PROC_NAME = "maroDagMenuProcOriginal"
_INSTALLED = False


def _originalProcSourceFile():
    """dagMenuProc를 정의한 .mel 파일 경로. 없으면 None."""
    if mel.eval('exists("dagMenuProc")') != 1:
        return None
    info = mel.eval('whatIs "dagMenuProc"')
    prefix = "Mel procedure found in: "
    if not info.startswith(prefix):
        return None
    return info[len(prefix):].strip()


def install():
    """플러그인 로드 시 한 번 부른다. 멱등 -- 이미 설치돼 있으면 아무 것도
    안 한다."""
    global _INSTALLED
    if _INSTALLED:
        return

    sourceFile = _originalProcSourceFile()
    if sourceFile and os.path.isfile(sourceFile):
        with open(sourceFile, "r", encoding="utf-8", errors="replace") as f:
            original = f.read()
        renamed = original.replace("dagMenuProc", _BACKUP_PROC_NAME)
        fd, tempPath = tempfile.mkstemp(suffix=".mel", prefix="maroDagMenuBackup_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(renamed)
        mel.eval('source "{}"'.format(tempPath.replace("\\", "/")))
        os.remove(tempPath)
        hasOriginal = True
    else:
        hasOriginal = False

    if hasOriginal:
        mel.eval('''
            global proc dagMenuProc(string $parentMenu, string $object) {
                %s($parentMenu, $object);
                python("import maroDagMenu; maroDagMenu._addMenuItem('" + $parentMenu + "', '" + $object + "')");
            }
        ''' % _BACKUP_PROC_NAME)
    else:
        mel.eval('''
            global proc dagMenuProc(string $parentMenu, string $object) {
                python("import maroDagMenu; maroDagMenu._addMenuItem('" + $parentMenu + "', '" + $object + "')");
            }
        ''')
    _INSTALLED = True


def uninstall():
    """플러그인 언로드 시 한 번 부른다. 멱등."""
    global _INSTALLED
    if not _INSTALLED:
        return
    if mel.eval('exists("{}")'.format(_BACKUP_PROC_NAME)) == 1:
        mel.eval('''
            global proc dagMenuProc(string $parentMenu, string $object) {
                %s($parentMenu, $object);
            }
        ''' % _BACKUP_PROC_NAME)
    _INSTALLED = False


def _addMenuItem(parentMenu, object_):
    cmds.menuItem(parent=parentMenu, label="Maro node editor",
                 command=lambda *_: _onMenuItemClicked(object_))


def _onMenuItemClicked(object_):
    print("Maro node editor clicked for: {}".format(object_))  # Task 8 replaces this
```

**Note for the implementer:** the exact quoting/escaping of the generated MEL `python(...)` call above is fragile if `$object` ever contains a single quote (unusual for DAG paths but not impossible with certain naming). Verify with a manually-named test object (e.g. one containing an apostrophe is not valid Maya naming, so this is a low-risk edge case, but confirm empirically that standard `|group|pCube1` style paths round-trip correctly through the generated string before considering this step done.

- [ ] **Step 4: Wire into `MaroPluginMain.cpp`**

In `initializePlugin`, after the existing command registrations (near the `MaroMenuCommands`/`maroBuildMenu` idle-queue section), add:

```cpp
    maro::runPluginPythonModule("maroDagMenu", "maroDagMenu.install()");
```

In `uninitializePlugin`, add the mirroring call **before** the existing `maro::runPluginPythonModule("maroMainWindow", "maroMainWindow.teardown()");` line (order does not matter functionally here since the two are independent, but keeping new additions grouped together aids readability):

```cpp
    maro::runPluginPythonModule("maroDagMenu", "maroDagMenu.uninstall()");
```

- [ ] **Step 5: Update `src/maro_plugin/CMakeLists.txt`**

Add `maroDagMenu` to `MARO_PLUGIN_PY_MODULES`.

- [ ] **Step 6: Build and run the full suite**

```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure
```

- [ ] **Step 7: Manual verification** (interactive Maya — this is the acceptance test for this task)

```python
import maya.cmds as cmds
cmds.loadPlugin("maro")
cube = cmds.polyCube()[0]
# Right-click cube in the viewport -- confirm "Maro node editor" appears
# alongside the normal Vertex/Edge/Face/... items, and clicking it prints
# "Maro node editor clicked for: ...".
cmds.unloadPlugin("maro")
# Right-click cube again -- confirm "Maro node editor" is gone and the
# rest of the menu is unchanged from before loading.
```

- [ ] **Step 8: Commit**

```bash
git add python/maroDagMenu.py src/maro_plugin/MaroPluginMain.cpp src/maro_plugin/CMakeLists.txt
git commit -m "feat: chain dagMenuProc to add a Maro node editor item to the native marking menu"
```

---

### Task 8: Axis-creation flow (name/color dialog → create+bind → open SONE)

**Files:**
- Modify: `python/maroDagMenu.py:_onMenuItemClicked` (replace the Task 7 placeholder)

**Interfaces:**
- Consumes: `openSingleObjectNodeEditor` (Task 4), `cmds.maroBindAxis` (pre-existing).
- **Identifier-format constraint (Task 4 review finding, resolved in this task's code below):** `openSingleObjectNodeEditor`'s singleton registry keys on the exact string passed to it. Task 6's GSON double-click always passes `axisFullPath` from `maroListAxisNodes()` (a full DAG path, per `MaroAxisEditorCommands.cpp::listAxes()`). This task's two call sites (`_findBoundAxis`'s existing-axis lookup and the newly-created-axis path) must both normalize to a full DAG path the same way, or the same axis could get two different dictionary keys and two SONE popups. Both code blocks below already include the `cmds.ls(..., long=True)[0]` normalization — do not remove it.

No automated test (Maya dialogs + `maroBindAxis`'s existing coverage already exercises the create/bind commands; this task's own logic is UI orchestration, verified manually).

- [ ] **Step 1: Write the failing manual check**

Expected: right-clicking an unbound cube → `Maro node editor` → a name prompt appears (default = cube's short name) → confirming opens a color picker → confirming both creates a new `maroAxis` bound to the cube with the chosen `displayName`/`displayColor`, and opens its SONE. Right-clicking an already-bound object skips both dialogs and opens its existing SONE directly. Cancelling either dialog creates nothing.

- [ ] **Step 2: Implement `_onMenuItemClicked` in `python/maroDagMenu.py`**

Replace the placeholder from Task 7:

```python
def _findBoundAxis(object_):
    """object_에 이미 바인딩된 maroAxis가 있으면 그 풀 DAG 경로, 없으면 None.

    풀 경로로 정규화하는 이유: openSingleObjectNodeEditor()의 싱글턴
    레지스트리(_OPEN_EDITORS, maroSingleObjectNodeEditor.py)는 넘겨받은
    문자열을 그대로 딕셔너리 키로 쓴다. cmds.listConnections()는 이름
    충돌이 없으면 짧은 이름을 줄 수 있는데, MaroAxisEditorCommands.cpp의
    listAxes()(ONE이 GSON 더블클릭 시 쓰는 경로, Task 6)는 항상
    MDagPath::fullPathName()을 낸다. 두 호출부가 같은 축에 대해 다른
    문자열을 넘기면 싱글턴 검사가 같은 축을 다른 축으로 오판해 SONE
    창이 중복 생성된다 -- 그래서 여기서 항상 풀 경로로 맞춘다.
    """
    for connection in cmds.listConnections(object_, type="maroAxis", plugs=False) or []:
        if cmds.attributeQuery("targetObject", node=connection, exists=True):
            return cmds.ls(connection, long=True)[0]
    return None


def _onMenuItemClicked(object_):
    import maroSingleObjectNodeEditor

    existingAxis = _findBoundAxis(object_)
    if existingAxis is not None:
        maroSingleObjectNodeEditor.openSingleObjectNodeEditor(existingAxis)
        return

    shortName = object_.split("|")[-1]
    result = cmds.promptDialog(
        title="New Maro Axis", message="Display name:",
        text=shortName, button=["OK", "Cancel"],
        defaultButton="OK", cancelButton="Cancel", dismissString="Cancel")
    if result != "OK":
        return
    displayName = cmds.promptDialog(query=True, text=True)

    colorResult = cmds.colorEditor(rgbValue=(0.5, 0.7, 0.9))
    values = colorResult.split()
    if values[-1] != "1":  # colorEditor's last token is 0 on cancel, 1 on OK
        return
    r, g, b = float(values[0]), float(values[1]), float(values[2])

    cmds.undoInfo(openChunk=True)
    try:
        axis = cmds.createNode("maroAxis")
        # 풀 경로로 정규화 -- 위 _findBoundAxis()의 docstring과 같은 이유.
        # createNode()는 이름이 유일하면 짧은 이름을 주므로, 나중에 같은
        # 짧은 이름의 노드가 다른 계층에 생겨도 이 축의 SONE 키는 처음
        # 만들어질 때의 형태에 머물러 있지 않게 항상 여기서 확정한다.
        axis = cmds.ls(axis, long=True)[0]
        cmds.maroBindAxis(axis, object_)
        cmds.setAttr(axis + ".displayName", displayName, type="string")
        cmds.setAttr(axis + ".displayColor", r, g, b, type="double3")
    finally:
        cmds.undoInfo(closeChunk=True)

    maroSingleObjectNodeEditor.openSingleObjectNodeEditor(axis)
```

**Note for the implementer:** verify `cmds.colorEditor(rgbValue=...)`'s exact return-string format empirically (`print(cmds.colorEditor(rgbValue=(0.5, 0.7, 0.9)))` in the Script Editor) before trusting the parsing above — Maya's documented format is `"r g b a"` for RGB dialogs, but confirm the trailing OK/Cancel token position and count on the installed Maya version rather than assuming.

- [ ] **Step 3: Build**

```powershell
cmake --build out/build --config Release
```

- [ ] **Step 4: Manual verification** (interactive Maya)

Walk through the Step 1 scenario exactly, including the cancel-does-nothing cases and the "already bound skips dialogs" case.

- [ ] **Step 5: Run the full suite** (regression check — no logic here should affect existing tests, but confirm)

```powershell
ctest --test-dir out/build -C Release --output-on-failure
```

- [ ] **Step 6: Commit**

```bash
git add python/maroDagMenu.py
git commit -m "feat: wire the native menu item to create+bind a new axis and open its SONE"
```

---

### Task 9: Manual checklist + Coupling dropdown wiring + final verification

**Files:**
- Modify: `python/maroSingleObjectNodeEditor.py` (Coupling source-axis dropdown, deferred from Task 4 to keep that task focused on the core marking-menu loop)
- Modify: `docs/maro-main-ui-manual-checklist.md`

**Interfaces:**
- Consumes: `cmds.maroListAxisNodes()` for the dropdown's axis list; `cmds.connectAttr` for wiring the chosen source.

- [ ] **Step 1: Add the Coupling parameter panel to `MaroSingleObjectNodeEditor`**

In `python/maroSingleObjectNodeEditor.py`, extend `_applyCapability` so that after a successful `coupling` add, a small non-modal parameter form appears (a child `QWidget` with a `QComboBox` populated from `sliceAxisRows`-equivalent axis names). Given SONE does not import `maroObjectNodeEditor` (to avoid a circular import — `maroObjectNodeEditor` imports `maroSingleObjectNodeEditor`, not the reverse), read the axis list directly:

```python
def _showCouplingSourcePicker(self, couplingNodeName):
    picker = QtWidgets.QWidget(self, QtCore.Qt.Popup)
    layout = QtWidgets.QVBoxLayout(picker)
    combo = QtWidgets.QComboBox()
    axisNames = []
    rows = cmds.maroListAxisNodes()
    for i in range(len(rows) // 10):
        f = rows[i * 10:(i + 1) * 10]
        if f[0] == self._axis:
            continue  # 자기 자신은 소스로 고를 수 없다
        axisNames.append(f[0])
        combo.addItem(f[8] if f[8] else f[0], f[0])
    layout.addWidget(combo)
    applyButton = QtWidgets.QPushButton("Connect")
    layout.addWidget(applyButton)

    def _onApply():
        sourceAxis = combo.currentData()
        if not sourceAxis:
            picker.close()
            return
        isLinear = cmds.getAttr(sourceAxis + ".driveIsLinear")
        cmds.undoInfo(openChunk=True)
        try:
            cmds.setAttr(couplingNodeName + ".sourceIsLinear", isLinear)
            if isLinear:
                cmds.connectAttr(sourceAxis + ".positionLinear",
                                 couplingNodeName + ".sourceValueLinear", force=True)
            else:
                cmds.connectAttr(sourceAxis + ".position",
                                 couplingNodeName + ".sourceValue", force=True)
        finally:
            cmds.undoInfo(closeChunk=True)
        picker.close()
        self.update()

    applyButton.clicked.connect(_onApply)
    picker.move(self.mapToGlobal(QtCore.QPoint(int(self.width() / 2), int(self.height() / 2))))
    picker.show()
```

Call it from `_applyCapability` right after a successful `coupling` add:

```python
    def _applyCapability(self, flagName):
        try:
            newNode = cmds.maroAddCapability(self._axis, type=flagName)[0]
        except RuntimeError as error:
            print("Maro: maroAddCapability failed -- {}".format(error))
            return
        if flagName == "coupling":
            self._showCouplingSourcePicker(newNode)
        self.update()
```

(This replaces the earlier `_applyCapability` body from Task 4 — the return value of `maroAddCapability` is `[newNodeName]`, per `MaroAddCapabilityCommand`'s `setResult(MStringArray)` contract.)

- [ ] **Step 2: Build**

```powershell
cmake --build out/build --config Release
```

- [ ] **Step 3: Manual verification of the Coupling flow**

Create two bound axes; on the second one, add `Coupling` via the marking menu, confirm the picker lists the first axis by its display name, pick it, click Connect, and verify with `cmds.listConnections` that `sourceValue` (or `sourceValueLinear`, matching whichever the source axis drives) is now connected from the first axis's output.

- [ ] **Step 4: Write the manual checklist section**

Append to `docs/maro-main-ui-manual-checklist.md` a new section (follow the existing document's numbering/table-row convention — read the file first to match its exact heading and results-table format before inserting):

```markdown
## 1-4. 노드 캔버스 + 마킹 메뉴 (SONE/ONE)

| # | 확인 항목 | 결과 |
|---|---|---|
| 1 | `maroLoadPlugin` 후 아무 오브젝트나 우클릭 -> 기존 Maya 기본 항목(Vertex/Edge/Face/...) 전부 그대로 있고 그 안에 `Maro node editor` 항목 추가로 보임 | |
| 2 | 바인딩 안 된 오브젝트에서 `Maro node editor` 클릭 -> 이름 프롬프트 -> 색상 선택 -> SONE 팝업이 뜨고 새 `maroAxis`가 그 오브젝트에 바인딩됨 | |
| 3 | 두 다이얼로그 중 아무 데서나 취소 -> 아무 노드도 생성되지 않음 | |
| 4 | 이미 바인딩된 오브젝트에서 `Maro node editor` 클릭 -> 다이얼로그 없이 바로 그 축의 SONE가 뜸 | |
| 5 | SONE 안에서 우클릭+홀드+드래그 -> 7개 항목이 방사형으로 펼쳐지고, 하나에서 릴리즈하면 그 능력이 적용됨 | |
| 6 | 능력이 부여된 SONE 노드를 선택하고 Delete -> 노드는 남고 `undefined`로 복귀 | |
| 7 | 능력을 2개 이상 쌓은 뒤 노드를 더블클릭 -> 쌓인 목록이 펼쳐짐, 다시 더블클릭하면 접힘 | |
| 8 | `Coupling` 추가 시 소스 축 드롭다운이 뜨고, 다른 축을 골라 Connect하면 실제로 연결됨 | |
| 9 | MaroUI를 열고 하단 패널에서 만들어진 축마다 GSON이 그리드로 보임, 지정한 이름/색이 그대로 반영됨 | |
| 10 | GSON 더블클릭 -> 해당 SONE가 뜨거나(닫혀 있었으면) 앞으로 옴(열려 있었으면) | |
| 11 | GSON 우클릭 -> Rename/Recolor/Delete 각각 정상 동작, Delete는 축과 그 capability 노드까지 완전히 제거 | |
| 12 | 씬에서 오브젝트 선택 -> GSON 쪽이 갱신됨(반대 방향은 GSON 클릭 시 씬 선택이 바뀜) | |
| 13 | `maroUnloadPlugin` 후 아무 오브젝트나 우클릭 -> `Maro node editor` 항목이 사라지고 나머지 메뉴는 로드 전과 동일 | |
| 14 | MaroUI를 연 채로 플러그인 언로드 -> 크래시 없음, SONE 팝업이 떠 있는 상태로 언로드해도 크래시 없음 | |
| 15 | Phase 2/3의 듀얼 뷰포트(§1-1/§1-2) 재확인 -- 이번 레이아웃 변경으로 회귀 없음 | |
```

- [ ] **Step 5: Run the full suite one final time**

```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure
```
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add python/maroSingleObjectNodeEditor.py docs/maro-main-ui-manual-checklist.md
git commit -m "feat: wire Coupling source-axis picker, add manual verification checklist"
```

---

## Self-Review Notes

- **Spec coverage:** §2 (three layers) -> Tasks 4/6/7. §3 (dagMenuProc) -> Task 7. §4 (name/color -> SONE) -> Task 8. §5 (SONE display/marking-menu/delete/coupling) -> Tasks 3/4/9. §6 (ONE/GSON) -> Tasks 5/6. §7 (new attributes) -> Task 1. §8 (command reuse) -> confirmed no task adds a new C++ command. §9 (file layout) -> Tasks 3-8 collectively create/delete exactly the files §9 lists. §10 (test strategy) -> Tasks 1-3-5 cover the pure-function/field-count parts; Task 9's checklist covers the interactive parts.
- **Type consistency:** `AXIS_FIELDS = 10` and the `f[8]`/`f[9]` field positions are used identically in Task 2's C++ output, Task 5's `sliceAxisRows`, Task 6's `ObjectNodeEditor`, and Task 9's inline dropdown-population snippet. `CAPABILITY_FIELDS = 5` and its field order match between Task 3's `sliceCapabilityRows` and the pre-existing `MaroAxisEditorCommands.cpp::listCapabilities()`. `openSingleObjectNodeEditor(axis)` has the same one-argument signature everywhere it's called (Task 6's double-click handler, Task 8's `_onMenuItemClicked`).
- **No placeholders:** every step above contains complete code; the two "verify empirically before trusting this" notes (Task 7's MEL quoting, Task 8's `colorEditor` return format) are flagged as investigation steps with a concrete command to run, not unresolved TODOs in the shipped code.
