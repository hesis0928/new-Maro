# Maro Tech Diag Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add manual, on-demand kinematic/ROS validation to MaroUI — two side panels flanking the dual viewport, each with a "run check" button and a result terminal, checking limit proximity + mesh AABB collisions (Maya side) and `/joint_states` publish integrity (ROS side), with undoable one-click remedies where a remedy is well-defined.

**Architecture:** Pure Python, no new C++ commands or DG attributes. A new module `python/maroTechDiag.py` holds pure check/remedy functions (Maya-independent where possible, mayapy-testable everywhere) plus the two side-panel `QWidget` classes, wired into `python/maroMainWindow.py`'s existing layout.

**Tech Stack:** Python 3, `maya.cmds`, `PySide6`, mayapy batch tests, CMake/CTest.

**Spec:** `docs/superpowers/specs/2026-08-26-maro-tech-diag-design.md`

## Global Constraints

- Build always with `--config Release`; `ctest --test-dir out/build -C Release --output-on-failure` must pass fully before any task is done.
- New `.py` files never call `setStyleSheet()`.
- No new C++ commands or DG attributes — this subsystem is pure `cmds` queries + `cmds.setAttr`.
- Existing `viewportPane` (the `paneLayout` holding the two `modelPanel`s) is not restructured internally — the new side panels wrap around it in a new layout layer.
- Every remedy application is wrapped in `cmds.undoInfo(openChunk=True)`/`closeChunk=True` and never runs before the user clicks its apply button.
- Results are recomputed fresh on every "run check" click — no persisted history.
- Build/test command for every task:
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
| `python/maroTechDiag.py` | Create | Pure check/remedy functions + the two side-panel widgets + `buildMayaSidePanel()`/`buildRosSidePanel()` entry points |
| `python/maroMainWindow.py` | Modify | Wrap `viewportPane` in a new row with the two side panels; widen the window |
| `tests/maya/test_tech_diag.py` | Create | mayapy batch tests for every pure function |
| `tests/CMakeLists.txt` | Modify | Register `maya_tech_diag` |
| `src/maro_plugin/CMakeLists.txt` | Modify | Add `maroTechDiag` to `MARO_PLUGIN_PY_MODULES` |
| `docs/maro-main-ui-manual-checklist.md` | Modify | New manual-verification section |

---

### Task 1: Axis-data checks — limit proximity + joint_states integrity

**Files:**
- Create: `python/maroTechDiag.py`
- Test: `tests/maya/test_tech_diag.py`

**Interfaces:**
- Produces:
  - `LIMIT_PROXIMITY_THRESHOLD = 0.9` (module constant)
  - `Finding` — a plain dict shape (not a class): `{"category": str, "severity": "warning"|"info", "summary": str, "axis": str, "remedy": callable | None}`. `remedy`, when present, is a zero-argument callable that performs the fix and returns nothing (Task 3 supplies these).
  - `checkLimitProximity(axisRows, capabilityRowsByAxis, currentValueByAxis) -> list[Finding]` — pure, no Maya calls. `axisRows` is the output of `sliceAxisTechRows()` below. `capabilityRowsByAxis` is `dict[axisFullPath, list[dict]]` where each dict has `logicalIndex`(int), `capType`(int), `capMin`(tuple of 3 floats), `capMax`(tuple of 3 floats), `capEnable`(tuple of 3 bool). `currentValueByAxis` is `dict[axisFullPath, float]` (the axis's current driven value, already resolved to the right unit by the caller).
  - `checkJointStatesIntegrity(axisRows) -> list[Finding]` — pure, no Maya calls.
  - `sliceAxisTechRows(flat) -> list[dict]` — parses `maroListAxisNodes()`'s flat array (10 fields per axis, established in the node-canvas plan) into dicts with keys `axisFullPath`, `jointName`, `boundTargetPath`, `enabled`(bool), `conventionAxis`(int 0/1/2), `capabilityCount`(int). (Only the fields this module needs — a deliberately narrower slice than `maroObjectNodeEditor.sliceAxisRows`, which is a separate, independent parser per the project's existing pattern of each module owning its own slice of the same flat contract.)
  - `AXIS_FIELDS = 10` (module constant, matches the C++ contract — same value as `maroObjectNodeEditor.AXIS_FIELDS`/`maroSingleObjectNodeEditor.AXIS_FIELDS`, declared independently per that same existing pattern).
  - `CAPABILITY_FIELDS = 5` (module constant, same value as the sibling modules' own copy).
  - `sliceCapabilityTechRows(flat) -> list[dict]` — parses `maroListAxisNodes(capabilities=axis)`'s flat array into dicts with keys `logicalIndex`(int), `capType`(int), `connected`(bool). (Again, this module's own narrow slice — it doesn't need `capabilityNodeName`/`capabilityNodeType`.)

- [ ] **Step 1: Write the failing tests**

Create `tests/maya/test_tech_diag.py` (plain mayapy script — bare `assert` + `print`, matching `tests/maya/test_single_object_node_editor.py`'s style; add the same `sys.path` bootstrap that file uses so `import maroTechDiag` resolves):

```python
import os
import sys

_pythonDir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "python")
if _pythonDir not in sys.path:
    sys.path.insert(0, _pythonDir)

import maroTechDiag as diag

# --- sliceAxisTechRows ---
flat = ["|axis1", "joint1", "|cube1", "", "0", "1", "1", "2", "Axis One", "0.2,0.6,0.9"]
rows = diag.sliceAxisTechRows(flat)
assert len(rows) == 1, rows
assert rows[0] == {
    "axisFullPath": "|axis1", "jointName": "joint1", "boundTargetPath": "|cube1",
    "enabled": True, "conventionAxis": 1, "capabilityCount": 2,
}, rows[0]
assert diag.sliceAxisTechRows(None) == []
try:
    diag.sliceAxisTechRows(["too", "few"])
    assert False, "expected ValueError for a non-multiple-of-10 array"
except ValueError:
    pass
print("sliceAxisTechRows OK")

# --- sliceCapabilityTechRows ---
capFlat = ["0", "cap1", "maroLimit", "1", "1", "1", "", "", "3", "0"]
capRows = diag.sliceCapabilityTechRows(capFlat)
assert capRows == [
    {"logicalIndex": 0, "capType": 1, "connected": True},
    {"logicalIndex": 1, "capType": 3, "connected": False},
], capRows
print("sliceCapabilityTechRows OK")

# --- checkLimitProximity ---
axisRows = [{"axisFullPath": "|axis1", "jointName": "j1", "boundTargetPath": "|cube1",
             "enabled": True, "conventionAxis": 0, "capabilityCount": 1}]
capsByAxis = {"|axis1": [{"logicalIndex": 0, "capType": 1,
                          "capMin": (0.0, 0.0, 0.0), "capMax": (10.0, 0.0, 0.0),
                          "capEnable": (True, False, False)}]}
# Value at 95% of the [0, 10] range on the X component (conventionAxis=0).
findings = diag.checkLimitProximity(axisRows, capsByAxis, {"|axis1": 9.5})
assert len(findings) == 1, findings
assert findings[0]["axis"] == "|axis1"
assert findings[0]["category"] == "limitProximity"
assert findings[0]["remedy"] is None
# Value safely in the middle -> no finding.
findings = diag.checkLimitProximity(axisRows, capsByAxis, {"|axis1": 5.0})
assert findings == [], findings
# The relevant capEnable component is False -> never flagged regardless of value.
capsByAxisDisabled = {"|axis1": [{"logicalIndex": 0, "capType": 1,
                                  "capMin": (0.0, 0.0, 0.0), "capMax": (10.0, 0.0, 0.0),
                                  "capEnable": (False, True, True)}]}
findings = diag.checkLimitProximity(axisRows, capsByAxisDisabled, {"|axis1": 9.9})
assert findings == [], findings
# Zero-width range is skipped, not a division-by-zero crash.
capsByAxisZero = {"|axis1": [{"logicalIndex": 0, "capType": 1,
                              "capMin": (5.0, 0.0, 0.0), "capMax": (5.0, 0.0, 0.0),
                              "capEnable": (True, False, False)}]}
findings = diag.checkLimitProximity(axisRows, capsByAxisZero, {"|axis1": 5.0})
assert findings == [], findings
print("checkLimitProximity OK")

# --- checkJointStatesIntegrity ---
rowsEmpty = [{"axisFullPath": "|a1", "jointName": "", "boundTargetPath": "|c1",
              "enabled": True, "conventionAxis": 0, "capabilityCount": 1}]
findings = diag.checkJointStatesIntegrity(rowsEmpty)
assert len(findings) == 1 and findings[0]["category"] == "emptyJointName", findings
assert findings[0]["remedy"] is None  # remedies attached by Task 3, not this pure function

rowsDup = [
    {"axisFullPath": "|a1", "jointName": "shoulder", "boundTargetPath": "|c1",
     "enabled": True, "conventionAxis": 0, "capabilityCount": 1},
    {"axisFullPath": "|a2", "jointName": "shoulder", "boundTargetPath": "|c2",
     "enabled": True, "conventionAxis": 0, "capabilityCount": 1},
]
findings = diag.checkJointStatesIntegrity(rowsDup)
assert len(findings) == 1 and findings[0]["category"] == "duplicateJointName", findings
assert findings[0]["axis"] == "|a2", "the later-encountered axis is the one flagged"

rowsNoDriver = [{"axisFullPath": "|a1", "jointName": "elbow", "boundTargetPath": "|c1",
                 "enabled": True, "conventionAxis": 0, "capabilityCount": 0}]
findings = diag.checkJointStatesIntegrity(rowsNoDriver)
assert len(findings) == 1 and findings[0]["category"] == "noDriverActiveAxis", findings

rowsDisabled = [{"axisFullPath": "|a1", "jointName": "", "boundTargetPath": "",
                 "enabled": False, "conventionAxis": 0, "capabilityCount": 0}]
assert diag.checkJointStatesIntegrity(rowsDisabled) == [], "disabled axes are never flagged"

rowsUnbound = [{"axisFullPath": "|a1", "jointName": "", "boundTargetPath": "",
                "enabled": True, "conventionAxis": 0, "capabilityCount": 0}]
assert diag.checkJointStatesIntegrity(rowsUnbound) == [], "unbound axes are never flagged"

print("checkJointStatesIntegrity OK")
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
$env:PYTHONPATH = "C:\Users\ckd30\Projects\Maya_Ros_Sim\python"
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_tech_diag.py
```
(Adjust the mayapy path if this machine's Maya install is elsewhere — check `tests/CMakeLists.txt`'s `MAYAPY` variable.) Expected: FAIL — module doesn't exist yet.

- [ ] **Step 3: Write `python/maroTechDiag.py`**

```python
"""테크 Diag -- 기구학/ROS 정합성 능동 검증 (설계 스펙 2026-08-26-maro-tech-diag-design.md).

기존 boad/book 디버깅 Diag와 완전히 독립된 서브시스템이다. 새 C++ 커맨드나
DG 어트리뷰트 없이 기존 maroListAxisNodes 조회 + cmds.getAttr만으로 동작한다.
검사 결과는 실행할 때마다 새로 계산되고 저장되지 않는다.

이 파일의 순수 함수는 Maya에 의존하지 않는다 -- mayapy 배치 모드에서 QWidget
없이 계약을 검증한다.
"""

LIMIT_PROXIMITY_THRESHOLD = 0.9

# C++ 쪽 계약. maroObjectNodeEditor.py/maroSingleObjectNodeEditor.py도 각자
# 독립적으로 같은 값을 선언한다 -- 순환 import를 피하기 위한 이 프로젝트의
# 기존 관례.
AXIS_FIELDS = 10
CAPABILITY_FIELDS = 5


def sliceAxisTechRows(flat):
    """maroListAxisNodes()의 평탄한 배열에서 이 모듈이 필요로 하는 필드만
    뽑아 축 행 딕셔너리 목록으로 되돌린다."""
    if flat is None:
        return []
    if len(flat) % AXIS_FIELDS != 0:
        raise ValueError(
            "axis row array length {} is not a multiple of {}".format(
                len(flat), AXIS_FIELDS))
    rows = []
    for i in range(len(flat) // AXIS_FIELDS):
        f = flat[i * AXIS_FIELDS:(i + 1) * AXIS_FIELDS]
        rows.append({
            "axisFullPath": f[0],
            "jointName": f[1],
            "boundTargetPath": f[2],
            "enabled": f[5] == "1",
            "conventionAxis": int(f[6]),
            "capabilityCount": int(f[7]),
        })
    return rows


def sliceCapabilityTechRows(flat):
    """maroListAxisNodes(capabilities=axis)의 평탄한 배열에서 이 모듈이
    필요로 하는 필드만 뽑아 capability 행 딕셔너리 목록으로 되돌린다."""
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
            "capType": int(f[3]),
            "connected": f[4] == "1",
        })
    return rows


def checkLimitProximity(axisRows, capabilityRowsByAxis, currentValueByAxis):
    """리밋(capType 1 또는 5)이 있는 축마다, 현재 구동값이 min/max 범위의
    LIMIT_PROXIMITY_THRESHOLD 이상 근접했으면 경고를 낸다. conventionAxis로
    capMin/capMax/capEnable의 X/Y/Z 중 어느 성분이 이 축에 해당하는지 고른다."""
    findings = []
    for axisRow in axisRows:
        axis = axisRow["axisFullPath"]
        currentValue = currentValueByAxis.get(axis)
        if currentValue is None:
            continue
        idx = axisRow["conventionAxis"]
        for capRow in capabilityRowsByAxis.get(axis, []):
            if capRow["capType"] not in (1, 5):
                continue
            if not capRow["capEnable"][idx]:
                continue
            minV = capRow["capMin"][idx]
            maxV = capRow["capMax"][idx]
            span = maxV - minV
            if span <= 0:
                continue
            proximity = (currentValue - minV) / span
            if proximity >= LIMIT_PROXIMITY_THRESHOLD or proximity <= (1.0 - LIMIT_PROXIMITY_THRESHOLD):
                findings.append({
                    "category": "limitProximity",
                    "severity": "warning",
                    "summary": "{}: current value is within {:.0f}% of its limit range".format(
                        axis, (1.0 - LIMIT_PROXIMITY_THRESHOLD) * 100),
                    "axis": axis,
                    "remedy": None,
                })
    return findings


def checkJointStatesIntegrity(axisRows):
    """활성화+바인딩된 축의 jointName 공백/중복, 그리고 활성화됐지만 1차
    구동 capability가 없는 축을 찾는다."""
    findings = []
    seenJointNames = {}
    for row in axisRows:
        if not row["enabled"] or not row["boundTargetPath"]:
            continue
        axis = row["axisFullPath"]
        jointName = row["jointName"]
        if not jointName:
            findings.append({
                "category": "emptyJointName",
                "severity": "warning",
                "summary": "{}: jointName is empty".format(axis),
                "axis": axis,
                "remedy": None,
            })
        else:
            if jointName in seenJointNames:
                findings.append({
                    "category": "duplicateJointName",
                    "severity": "warning",
                    "summary": "{}: jointName '{}' duplicates {}".format(
                        axis, jointName, seenJointNames[jointName]),
                    "axis": axis,
                    "remedy": None,
                })
            else:
                seenJointNames[jointName] = axis
        if row["capabilityCount"] == 0:
            findings.append({
                "category": "noDriverActiveAxis",
                "severity": "warning",
                "summary": "{}: enabled and bound but has no capability driving it".format(axis),
                "axis": axis,
                "remedy": None,
            })
    return findings
```

- [ ] **Step 4: Run test to verify it passes**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_tech_diag.py
```
Expected: all four `OK` lines print, exit 0.

- [ ] **Step 5: Register the test in `tests/CMakeLists.txt`**

Find the existing `maya_single_object_node_editor` entry and add a sibling `maya_tech_diag` entry using the identical mechanism (same working directory convention, same `MAYAPY` invocation, no `ENVIRONMENT` needed since the test file does its own `sys.path.insert`).

- [ ] **Step 6: Build and run the full suite**

```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure
```

- [ ] **Step 7: Commit**

```bash
git add python/maroTechDiag.py tests/maya/test_tech_diag.py tests/CMakeLists.txt
git commit -m "feat: add limit-proximity and joint_states-integrity check functions"
```

---

### Task 2: Mesh AABB collision check

**Files:**
- Modify: `python/maroTechDiag.py`
- Test: `tests/maya/test_tech_diag.py`

**Interfaces:**
- Consumes: nothing from Task 1 (independent pure function).
- Produces: `checkMeshCollisions(boundingBoxesByMesh) -> list[Finding]` — pure. `boundingBoxesByMesh` is `dict[meshPath, tuple[float, float, float, float, float, float]]` (each value is `(xmin, ymin, zmin, xmax, ymax, zmax)`, the shape `cmds.exactWorldBoundingBox()` already returns). A `Finding` from this function has `"axis"` set to `None` (collisions involve two meshes, not one axis) and an additional key `"meshes": (meshA, meshB)`.

- [ ] **Step 1: Write the failing test**

Append to `tests/maya/test_tech_diag.py`:

```python
# --- checkMeshCollisions ---
boxes = {
    "|cubeA": (0.0, 0.0, 0.0, 2.0, 2.0, 2.0),
    "|cubeB": (1.0, 1.0, 1.0, 3.0, 3.0, 3.0),   # overlaps cubeA
    "|cubeC": (10.0, 10.0, 10.0, 12.0, 12.0, 12.0),  # far away, no overlap
}
findings = diag.checkMeshCollisions(boxes)
assert len(findings) == 1, findings
assert findings[0]["category"] == "meshCollision"
assert findings[0]["axis"] is None
assert set(findings[0]["meshes"]) == {"|cubeA", "|cubeB"}
assert findings[0]["remedy"] is None

# Touching-but-not-overlapping boxes (shared face) must NOT be flagged.
touchingBoxes = {
    "|cubeD": (0.0, 0.0, 0.0, 1.0, 1.0, 1.0),
    "|cubeE": (1.0, 0.0, 0.0, 2.0, 1.0, 1.0),
}
assert diag.checkMeshCollisions(touchingBoxes) == [], "exactly-touching boxes should not count as a collision"

assert diag.checkMeshCollisions({}) == []
assert diag.checkMeshCollisions({"|onlyOne": (0.0, 0.0, 0.0, 1.0, 1.0, 1.0)}) == []
print("checkMeshCollisions OK")
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_tech_diag.py
```
Expected: FAIL — `checkMeshCollisions` not defined.

- [ ] **Step 3: Add `checkMeshCollisions` to `python/maroTechDiag.py`**

```python
import itertools


def _boxesOverlap(a, b):
    """두 AABB(xmin,ymin,zmin,xmax,ymax,zmax)가 실제로 겹치는지(맞닿기만
    하는 건 제외-- 부등호를 엄격하게 잡는다)."""
    return (a[0] < b[3] and b[0] < a[3] and
            a[1] < b[4] and b[1] < a[4] and
            a[2] < b[5] and b[2] < a[5])


def checkMeshCollisions(boundingBoxesByMesh):
    """모든 메쉬 쌍에 대해 월드 바운딩박스(AABB) 겹침을 검사한다."""
    findings = []
    meshes = sorted(boundingBoxesByMesh.keys())
    for meshA, meshB in itertools.combinations(meshes, 2):
        if _boxesOverlap(boundingBoxesByMesh[meshA], boundingBoxesByMesh[meshB]):
            findings.append({
                "category": "meshCollision",
                "severity": "warning",
                "summary": "{} and {} bounding boxes overlap".format(meshA, meshB),
                "axis": None,
                "meshes": (meshA, meshB),
                "remedy": None,
            })
    return findings
```

Add `import itertools` at the top of the file alongside any other imports.

- [ ] **Step 4: Run test to verify it passes**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_tech_diag.py
```
Expected: `checkMeshCollisions OK` prints along with the earlier four lines.

- [ ] **Step 5: Build and run the full suite**

```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure
```

- [ ] **Step 6: Commit**

```bash
git add python/maroTechDiag.py tests/maya/test_tech_diag.py
git commit -m "feat: add mesh AABB collision check"
```

---

### Task 3: Remedy functions (fill/rename jointName) with undo support

**Files:**
- Modify: `python/maroTechDiag.py`
- Test: `tests/maya/test_tech_diag.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `remedyFillEmptyJointName(axis) -> None` — sets `axis.jointName` to the axis's bound target's short name, wrapped in one undo chunk.
  - `remedyRenameDuplicateJointName(axis, suggestedName) -> None` — sets `axis.jointName` to `suggestedName`, wrapped in one undo chunk.
  - `suggestJointNameForFill(axis) -> str` — pure-ish helper (calls `cmds.listRelatives`/`cmds.ls` for the short name, but does no writes) used by `remedyFillEmptyJointName` and by the UI (Task 4) to preview what will be filled in before the user clicks apply.
  - `suggestDisambiguatedJointName(jointName) -> str` — pure function: returns `jointName + "_2"`. (Kept intentionally simple per spec §5 — the spec only requires a suffix, not collision-checked uniqueness beyond one level; do not add a loop searching for `_3`, `_4`, etc., that is out of scope.)

- [ ] **Step 1: Write the failing test**

Append to `tests/maya/test_tech_diag.py`:

```python
import maya.standalone
maya.standalone.initialize()
import maya.cmds as cmds

# --- suggestDisambiguatedJointName (pure) ---
assert diag.suggestDisambiguatedJointName("shoulder") == "shoulder_2"
print("suggestDisambiguatedJointName OK")

# --- remedyFillEmptyJointName + undo ---
cube = cmds.polyCube(name="techDiagCube1")[0]
axis = cmds.createNode("maroAxis", name="techDiagAxis1")
cmds.maroBindAxis(axis, cube)
assert cmds.getAttr(axis + ".jointName") == "", "precondition: jointName starts empty"

suggestion = diag.suggestJointNameForFill(axis)
assert suggestion == "techDiagCube1", suggestion

diag.remedyFillEmptyJointName(axis)
assert cmds.getAttr(axis + ".jointName") == "techDiagCube1"
cmds.undo()
assert cmds.getAttr(axis + ".jointName") == "", "undo must revert the fill"
print("remedyFillEmptyJointName OK")

# --- remedyRenameDuplicateJointName + undo ---
axis2 = cmds.createNode("maroAxis", name="techDiagAxis2")
cmds.setAttr(axis2 + ".jointName", "shoulder", type="string")
diag.remedyRenameDuplicateJointName(axis2, "shoulder_2")
assert cmds.getAttr(axis2 + ".jointName") == "shoulder_2"
cmds.undo()
assert cmds.getAttr(axis2 + ".jointName") == "shoulder", "undo must revert the rename"
print("remedyRenameDuplicateJointName OK")

maya.standalone.uninitialize()
sys.exit(0)
```

**Note for the implementer:** this file now needs `maya.standalone.initialize()` for this section only, unlike the earlier pure-function sections which ran fine importing only `maroTechDiag`. Place the `import maya.standalone` / `initialize()` calls immediately before this block (not at the top of the file) so the earlier pure-function assertions keep working even if standalone initialization is ever skipped in some other invocation context — match whatever ordering convention `tests/maya/test_dag_menu.py` already established for a file that needs both pure-function and `maya.standalone` sections, since that file solved the identical problem in the previous plan.

- [ ] **Step 2: Run test to verify it fails**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_tech_diag.py
```
Expected: FAIL — the three new functions don't exist yet.

- [ ] **Step 3: Add the remedy functions to `python/maroTechDiag.py`**

```python
import maya.cmds as cmds


def suggestDisambiguatedJointName(jointName):
    return jointName + "_2"


def suggestJointNameForFill(axis):
    """빈 jointName을 채울 때 제안할 이름 -- 바인딩된 타겟의 짧은 이름."""
    targets = cmds.listConnections(axis + ".targetObject", shapes=False) or []
    if not targets:
        return ""
    return targets[0].split("|")[-1]


def remedyFillEmptyJointName(axis):
    cmds.undoInfo(openChunk=True)
    try:
        cmds.setAttr(axis + ".jointName", suggestJointNameForFill(axis), type="string")
    finally:
        cmds.undoInfo(closeChunk=True)


def remedyRenameDuplicateJointName(axis, suggestedName):
    cmds.undoInfo(openChunk=True)
    try:
        cmds.setAttr(axis + ".jointName", suggestedName, type="string")
    finally:
        cmds.undoInfo(closeChunk=True)
```

Add `import maya.cmds as cmds` near the top of the file (this is the first point in the file that needs a live Maya session — the pure functions above it never call `cmds`, so this import only matters once these functions are actually called, consistent with the rest of this codebase's pattern of importing `maya.cmds` at module level even in files with some pure functions, e.g. `maroSingleObjectNodeEditor.py`).

- [ ] **Step 4: Run test to verify it passes**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_tech_diag.py
```
Expected: all seven `OK` lines print, exit 0.

- [ ] **Step 5: Build and run the full suite**

```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure
```

- [ ] **Step 6: Commit**

```bash
git add python/maroTechDiag.py tests/maya/test_tech_diag.py
git commit -m "feat: add undoable jointName remedy functions"
```

---

### Task 4: Side-panel widgets + MaroUI layout integration

**Files:**
- Modify: `python/maroTechDiag.py` (add the two widget classes)
- Modify: `python/maroMainWindow.py` (wrap `viewportPane` with the two side panels, widen the window)

**Interfaces:**
- Consumes: `sliceAxisTechRows`, `sliceCapabilityTechRows`, `checkLimitProximity`, `checkJointStatesIntegrity`, `checkMeshCollisions`, `remedyFillEmptyJointName`, `remedyRenameDuplicateJointName`, `suggestJointNameForFill`, `suggestDisambiguatedJointName` (Tasks 1-3).
- Produces: `buildMayaSidePanel()`, `buildRosSidePanel()` — each returns a `QWidget` ready to embed, matching the exact embedding pattern `maroMainWindow.py` already uses for `maroObjectNodeEditor.buildWidget()` (two-step `MQtUtil.findLayout`/`addWidgetToMayaLayout`).

No automated test for the widgets themselves (same batch-mayapy `QWidget` constraint as every widget in the node-canvas plan) — verified via the manual checklist in Task 5.

- [ ] **Step 1: Read the current `python/maroMainWindow.py` in full**

Its `buildUI()` currently builds (after the node-canvas plan's merge): a `formLayout(form)` containing a menu-bar row with the icon test button, then `outerPane = paneLayout("horizontal2", parent=form)` whose first pane is `viewportPane = paneLayout("vertical2", parent=outerPane)` (the two `modelPanel`s) and whose second pane is `editorHost` (ONE's embed target). Confirm this structure matches what you find before editing — line numbers may have drifted.

- [ ] **Step 2: Add the two side-panel widget classes to `python/maroTechDiag.py`**

```python
from PySide6 import QtWidgets


class _CheckSidePanel(QtWidgets.QWidget):
    """Maya측/ROS측 검사 사이드 패널의 공통 뼈대. setStyleSheet()를 부르지
    않는다."""

    def __init__(self, buttonLabel, runCheckFn, parent=None):
        super().__init__(parent)
        self._runCheckFn = runCheckFn
        layout = QtWidgets.QVBoxLayout(self)
        self._runButton = QtWidgets.QPushButton(buttonLabel)
        self._runButton.clicked.connect(self._onRunClicked)
        layout.addWidget(self._runButton)
        self._resultList = QtWidgets.QListWidget()
        layout.addWidget(self._resultList)
        self._findings = []

    def _onRunClicked(self):
        try:
            self._findings = self._runCheckFn()
        except Exception as error:  # noqa: BLE001 -- Qt 콜백 경계, 버튼 클릭마다 도는 코드가 예외를 흘리면 안 됨
            import traceback
            traceback.print_exc()
            self._findings = []
        self._resultList.clear()
        if not self._findings:
            self._resultList.addItem("문제 없음")
            return
        for finding in self._findings:
            item = QtWidgets.QListWidgetItem(finding["summary"])
            self._resultList.addItem(item)
            if finding.get("remedy") is not None:
                applyButton = QtWidgets.QPushButton("적용")
                applyButton.clicked.connect(
                    lambda checked=False, f=finding: self._onApplyRemedy(f))
                itemWidget = QtWidgets.QWidget()
                itemLayout = QtWidgets.QHBoxLayout(itemWidget)
                itemLayout.addWidget(applyButton)
                self._resultList.setItemWidget(item, itemWidget)

    def _onApplyRemedy(self, finding):
        try:
            finding["remedy"]()
        except Exception as error:  # noqa: BLE001 -- 위와 같은 이유
            import traceback
            traceback.print_exc()
            return
        self._onRunClicked()  # 적용 후 다시 검사해서 목록을 갱신


def _runMayaSideChecks():
    axisRows = sliceAxisTechRows(cmds.maroListAxisNodes())
    capsByAxis = {}
    currentValueByAxis = {}
    for row in axisRows:
        axis = row["axisFullPath"]
        capFlat = cmds.maroListAxisNodes(capabilities=axis)
        capRows = []
        for capRow in sliceCapabilityTechRows(capFlat):
            if not capRow["connected"] or capRow["capType"] not in (1, 5):
                continue
            idx = capRow["logicalIndex"]
            capRows.append({
                "logicalIndex": idx,
                "capType": capRow["capType"],
                "capMin": tuple(cmds.getAttr("{}.capabilityIn[{}].capMin".format(axis, idx))[0]),
                "capMax": tuple(cmds.getAttr("{}.capabilityIn[{}].capMax".format(axis, idx))[0]),
                "capEnable": tuple(bool(v) for v in
                                   cmds.getAttr("{}.capabilityIn[{}].capEnable".format(axis, idx))[0]),
            })
        capsByAxis[axis] = capRows
        if row["enabled"] and row["boundTargetPath"]:
            driveIsLinear = cmds.getAttr(axis + ".driveIsLinear")
            currentValueByAxis[axis] = cmds.getAttr(
                axis + (".positionLinear" if driveIsLinear else ".position"))

    findings = checkLimitProximity(axisRows, capsByAxis, currentValueByAxis)

    boundMeshes = [row["boundTargetPath"] for row in axisRows
                   if row["enabled"] and row["boundTargetPath"]]
    boxes = {}
    for mesh in boundMeshes:
        bbox = cmds.exactWorldBoundingBox(mesh)
        boxes[mesh] = tuple(bbox)
    findings += checkMeshCollisions(boxes)
    return findings


def _runRosSideChecks():
    axisRows = sliceAxisTechRows(cmds.maroListAxisNodes())
    findings = checkJointStatesIntegrity(axisRows)
    rowByAxis = {row["axisFullPath"]: row for row in axisRows}
    for finding in findings:
        if finding["category"] == "emptyJointName":
            axis = finding["axis"]
            finding["remedy"] = lambda a=axis: remedyFillEmptyJointName(a)
        elif finding["category"] == "duplicateJointName":
            axis = finding["axis"]
            existingName = rowByAxis[axis]["jointName"]
            suggestion = suggestDisambiguatedJointName(existingName)
            finding["remedy"] = lambda a=axis, s=suggestion: remedyRenameDuplicateJointName(a, s)
    return findings


def buildMayaSidePanel():
    return _CheckSidePanel("Maya 검사 실행", _runMayaSideChecks)


def buildRosSidePanel():
    return _CheckSidePanel("ROS 검사 실행", _runRosSideChecks)
```

**Note for the implementer:** `_runMayaSideChecks`'s findings never carry a `remedy` (per spec §5, limit proximity and mesh collision have no automated fix) — only `_runRosSideChecks` attaches remedies, and only for the two categories the spec designates as fixable. Confirm `checkJointStatesIntegrity`'s returned dicts have `remedy: None` by default (Task 1) so this function's job is purely to overwrite that field for the two fixable categories, not to construct findings from scratch.

- [ ] **Step 3: Wire the two panels into `python/maroMainWindow.py`'s `buildUI()`**

Replace the block that currently does `viewportPane = cmds.paneLayout(configuration="vertical2", parent=outerPane)` with a wrapping row: a new `formLayout` (call it `viewportRow`, parented where `viewportPane` used to be attached, i.e. as `outerPane`'s first pane) containing three children attached left-to-right via `attachForm`/`attachControl` (the same technique `_buildLabeledViewport` already uses): the Maya side panel (fixed width, e.g. 180), `viewportPane` itself (stretches, unchanged internally), and the ROS side panel (fixed width, e.g. 180). Import `maroTechDiag` inside `buildUI()` (matching this file's existing per-subsystem import-inside-function convention) and embed both side panels with the same two-step `MQtUtil.findLayout`/`addWidgetToMayaLayout` sequence already used for the ONE widget and the test button — read that existing code in the same function to copy the exact call shape rather than re-deriving it.

- [ ] **Step 4: Widen the window**

In `show()`, increase `initialWidth` on the `cmds.workspaceControl(...)` call (e.g. from its current value, add roughly `2 * 180 + margins` to keep the viewports at their current size with the two new fixed-width side panels added). Use your judgment on the exact number — the requirement is only that the viewports don't shrink, not a specific pixel value.

- [ ] **Step 5: Update `src/maro_plugin/CMakeLists.txt`**

Add `maroTechDiag` to `MARO_PLUGIN_PY_MODULES`.

- [ ] **Step 6: Build**

```powershell
cmake --build out/build --config Release
```

- [ ] **Step 7: Run the full suite**

```powershell
ctest --test-dir out/build -C Release --output-on-failure
```

- [ ] **Step 8: Manual smoke check** (interactive Maya, not automated — full checklist entry comes in Task 5)

Open MaroUI, confirm both side panels appear flanking the viewports without shrinking them, click both "검사 실행" buttons on a scene with at least one bound, unbound-jointName axis and confirm a finding with an "적용" button appears; click apply and confirm the jointName gets filled and the list refreshes.

- [ ] **Step 9: Commit**

```bash
git add python/maroTechDiag.py python/maroMainWindow.py src/maro_plugin/CMakeLists.txt
git commit -m "feat: add Maya/ROS tech-diag side panels to MaroUI"
```

---

### Task 5: Manual checklist

**Files:**
- Modify: `docs/maro-main-ui-manual-checklist.md`

- [ ] **Step 1: Read the current file to match its exact table/section conventions**

- [ ] **Step 2: Append a new section**

Following the document's existing numbering convention (the node-canvas plan's own final section used "Phase 5" after "§1-4" occupied Phase 4 — check what the live document actually shows now and continue from there rather than assuming a specific number), add a table covering:

```markdown
| # | 확인 항목 | 결과 |
|---|---|---|
| 1 | MaroUI 창이 넓어지고 뷰포트 좌우에 사이드 패널이 보임, 뷰포트 자체 크기는 줄지 않음 | |
| 2 | 리밋에 근접한 축이 있는 씬에서 Maya측 "검사 실행" -> 경고가 뜨고 적용 버튼은 없음 | |
| 3 | 서로 겹치는 메쉬 2개가 있는 씬에서 Maya측 검사 -> 충돌 경고가 뜨고 적용 버튼은 없음 | |
| 4 | 문제 없는 씬에서 양쪽 검사 실행 -> "문제 없음" 표시 | |
| 5 | jointName이 빈 축이 있는 씬에서 ROS측 검사 -> 경고 + 적용 버튼, 클릭하면 채워지고 목록이 갱신됨, Ctrl+Z로 되돌아감 | |
| 6 | jointName이 중복된 두 축이 있는 씬에서 ROS측 검사 -> 나중 축에 `_2` 접미사 제안 + 적용, Ctrl+Z로 되돌아감 | |
| 7 | 활성화+바인딩됐지만 capability가 없는 축이 있는 씬에서 ROS측 검사 -> 경고, 적용 버튼 없음 | |
| 8 | 두 검사 모두 버튼을 누르기 전에는 씬을 바꾸지 않음(재계산만 함) | |
```

- [ ] **Step 3: Commit**

```bash
git add docs/maro-main-ui-manual-checklist.md
git commit -m "docs: add tech-diag manual verification checklist"
```

---

## Self-Review Notes

- **Spec coverage:** §2 (layout) -> Task 4. §3 (Maya-side checks) -> Tasks 1 (limit proximity) + 2 (mesh collision). §4 (ROS-side checks) -> Task 1. §5 (remedies) -> Task 3 (functions) + Task 4 (wiring, correctly withholding remedies from limit-proximity/collision findings). §6 (architecture, no new C++) -> confirmed no task adds one. §7 (data flow) -> Task 4's `_runMayaSideChecks`/`_runRosSideChecks` implement it directly. §9 (testing) -> Tasks 1-3's mayapy tests + Task 5's manual checklist.
- **Type/name consistency:** `Finding` dict shape (`category`/`severity`/`summary`/`axis`/`remedy`, plus `meshes` for collisions) is used identically across Tasks 1, 2, and 4. `AXIS_FIELDS`/`CAPABILITY_FIELDS` values (10/5) match the established contract from the node-canvas plan. `sliceAxisTechRows`/`sliceCapabilityTechRows` names are deliberately distinct from the sibling modules' `sliceAxisRows`/`sliceCapabilityRows` (different field subsets, avoids confusion about which module owns which parser).
- **No placeholders:** the one piece of dead code flagged in Task 1's snippet is explicitly called out as dead and told to be deleted — not left as an unresolved TODO.
