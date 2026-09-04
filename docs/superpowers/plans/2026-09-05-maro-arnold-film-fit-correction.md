# Maro Arnold Film Fit Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `computeCameraIntrinsics()` (in the Arnold synthetic-data generator) correctly account for Maya's camera Film Fit mode (Fill/Horizontal/Vertical/Overscan) and general `pixelAspectRatio`, closing the ~11-19% geometric error the 2026-09-04 final review found and explicitly deferred.

**Architecture:** Pure Python, no new C++ code. One function (`computeCameraIntrinsics`) grows new parameters with mode-specific branching; two call sites (`buildCalibrationDict`, the panel) grow to read and pass through the camera's real `filmFit`/`pixelAspectRatio`/`overscan` attributes instead of assuming Fill/1.0/1.0.

**Tech Stack:** Python 3, `maya.cmds`, `maya.api.OpenMaya` (`MFnCamera` as an independent cross-check oracle), mayapy batch tests, real Arnold batch renders (confirmed working in this environment as of 2026-09-04).

**Spec:** `docs/superpowers/specs/2026-09-05-maro-arnold-film-fit-correction-design.md`

## Global Constraints

- No new C++ code, commands, or DG attributes.
- `unprojectDepthToPoints()` in `python/maroSyntheticDataPointCloud.py` is NOT touched by this plan — it only ever consumes an already-computed `{fx, fy, cx, cy}` dict, so nothing about it needs to change.
- `computeCameraIntrinsics()`'s new parameters (`filmFit`, `pixelAspectRatio`, `overscan`) all have defaults (`"fill"`, `1.0`, `1.0`) so the existing call in `tests/maya/test_synthetic_data_point_cloud.py` (which doesn't pass them) keeps working — **verify this explicitly in Task 1, don't just assume it**: at that test's exact inputs (1920x1080, `hApertureIn=1.417323`, `vApertureIn=0.945512`), `filmAspect (~1.499) < deviceAspect (~1.778)`, which lands in Fill's "keep horizontal" branch — meaning `fx` comes out **numerically identical** to the old, uncorrected formula, and the existing test's `fx` assertion must keep passing unmodified. If your implementation makes that assertion fail, the branch logic is inverted — fix the logic, do not weaken the test.
- Do not ship a guessed Overscan formula as if it were confirmed. If Task 2's empirical investigation can't fully pin it down before the plan needs to be considered done, that itself is a valid `NEEDS_CONTEXT`/`BLOCKED` outcome to report honestly — matching this project's established discipline (the same standard applied to `rtcCollide`'s undocumented preconditions and MtoA's AOV-driver API in earlier plans this session).
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
| `python/maroSyntheticDataPointCloud.py` | Modify | `computeCameraIntrinsics()` gains Film Fit / pixelAspectRatio / (Task 2) Overscan support |
| `tests/maya/test_synthetic_data_point_cloud.py` | Modify | New pure self-consistency cases for Fill/Horizontal/Vertical/pixelAspectRatio (Task 1), Overscan (Task 2) |
| `python/maroSyntheticDataRender.py` | Modify | `buildCalibrationDict()` reads and records `filmFit`/`pixelAspectRatio`/`overscan` (Task 3) |
| `tests/maya/test_synthetic_data_render.py` | Modify | Extend `buildCalibrationDict()` test for the 3 new fields (Task 3) |
| `python/maroSyntheticDataPanel.py` | Modify | `_onRenderNow()` passes the 3 new calibration fields through to `computeCameraIntrinsics()` (Task 3) |
| `docs/maro-main-ui-manual-checklist.md` | Modify | New go/no-go item: Overscan mode real-render confirmation (Task 3) |

---

### Task 1: Fill / Horizontal / Vertical modes + `pixelAspectRatio` (pure self-consistency)

**Files:**
- Modify: `python/maroSyntheticDataPointCloud.py`
- Modify: `tests/maya/test_synthetic_data_point_cloud.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `computeCameraIntrinsics(focalLengthMm, horizontalFilmApertureIn, verticalFilmApertureIn, widthPx, heightPx, filmFit="fill", pixelAspectRatio=1.0, overscan=1.0) -> dict` (same `{"fx", "fy", "cx", "cy"}` shape as before). `filmFit` accepts either a normalized string (`"fill"`/`"horizontal"`/`"vertical"`/`"overscan"`, case-insensitive) or Maya's raw integer enum value (0-3, in that same Fill/Horizontal/Vertical/Overscan order — this ordering is Maya's own documented `filmFit` enum and does not need re-verification, but if you have a moment to confirm it via `cmds.attributeQuery("filmFit", node=<any camera shape>, listEnum=True)` while you're in Maya for this task anyway, do so and note the result in your report). Calling with `filmFit="overscan"` (or `3`) raises `NotImplementedError` in this task — Task 2 adds real Overscan support after empirical investigation; shipping a guessed formula now would violate this project's verify-before-shipping discipline.

- [ ] **Step 1: Write the failing tests**

Add to `tests/maya/test_synthetic_data_point_cloud.py`, right after the existing `computeCameraIntrinsics` test block (do not remove or alter the existing block — it must keep passing unmodified, see Global Constraints):

```python
# --- computeCameraIntrinsics: Film Fit modes (2026-09-05 follow-up) ---
import math as _math  # noqa: E402

# Fill, filmAspect < deviceAspect (the 1920x1080 default case, pixelAspectRatio=1):
# horizontal is the "narrower" side and stays raw; vertical is recomputed.
hAp, vAp, w, h = 1.417323, 0.945512, 1920, 1080
filmAspect = hAp / vAp
deviceAspect = w / float(h)
assert filmAspect < deviceAspect, "test premise: expected filmAspect < deviceAspect here"
fillWide = sdpc.computeCameraIntrinsics(35.0, hAp, vAp, w, h, filmFit="fill")
expectedFxRaw = (35.0 / (hAp * 25.4)) * w
expectedVEff = hAp / deviceAspect
expectedFyCorrected = (35.0 / (expectedVEff * 25.4)) * h
assert abs(fillWide["fx"] - expectedFxRaw) < 1e-6, fillWide
assert abs(fillWide["fy"] - expectedFyCorrected) < 1e-6, fillWide
assert abs(fillWide["fy"] - ((35.0 / (vAp * 25.4)) * h)) > 1.0, (
    "sanity: the corrected fy must differ meaningfully from the naive "
    "(uncorrected) formula, or this test can't tell a real fix from a no-op")
print("computeCameraIntrinsics Fill (filmAspect<deviceAspect) OK")

# Fill, filmAspect > deviceAspect (the original 320x240 bug-report case):
# vertical is the "narrower" side and stays raw; horizontal is recomputed.
hAp2, vAp2, w2, h2 = 1.417323, 0.945512, 320, 240
filmAspect2 = hAp2 / vAp2
deviceAspect2 = w2 / float(h2)
assert filmAspect2 > deviceAspect2, "test premise: expected filmAspect > deviceAspect here"
fillNarrow = sdpc.computeCameraIntrinsics(35.0, hAp2, vAp2, w2, h2, filmFit="fill")
expectedFyRaw2 = (35.0 / (vAp2 * 25.4)) * h2
expectedHEff2 = vAp2 * deviceAspect2
expectedFxCorrected2 = (35.0 / (expectedHEff2 * 25.4)) * w2
assert abs(fillNarrow["fy"] - expectedFyRaw2) < 1e-6, fillNarrow
assert abs(fillNarrow["fx"] - expectedFxCorrected2) < 1e-6, fillNarrow
print("computeCameraIntrinsics Fill (filmAspect>deviceAspect) OK")

# Horizontal: horizontal aperture is ALWAYS kept raw, regardless of which
# way the aspect ratio comparison goes -- use the SAME inputs as the
# filmAspect>deviceAspect Fill case above (320x240), where Fill would have
# corrected fx (not fy). Horizontal must behave differently from Fill here:
# fx stays raw, fy gets corrected instead.
horiz = sdpc.computeCameraIntrinsics(35.0, hAp2, vAp2, w2, h2, filmFit="horizontal")
expectedFxRawH = (35.0 / (hAp2 * 25.4)) * w2
expectedVEffH = hAp2 / deviceAspect2
expectedFyCorrectedH = (35.0 / (expectedVEffH * 25.4)) * h2
assert abs(horiz["fx"] - expectedFxRawH) < 1e-6, horiz
assert abs(horiz["fy"] - expectedFyCorrectedH) < 1e-6, horiz
assert abs(horiz["fx"] - fillNarrow["fx"]) > 1.0, (
    "sanity: Horizontal must genuinely differ from Fill for these inputs, "
    "since Fill corrected fx here but Horizontal must keep fx raw instead")
print("computeCameraIntrinsics Horizontal OK")

# Vertical: mirror of Horizontal -- vertical aperture always kept raw. Use
# the filmAspect<deviceAspect inputs (1920x1080), where Fill kept fx raw;
# Vertical must instead keep fy raw and correct fx.
vert = sdpc.computeCameraIntrinsics(35.0, hAp, vAp, w, h, filmFit="vertical")
expectedFyRawV = (35.0 / (vAp * 25.4)) * h
expectedHEffV = vAp * deviceAspect
expectedFxCorrectedV = (35.0 / (expectedHEffV * 25.4)) * w
assert abs(vert["fy"] - expectedFyRawV) < 1e-6, vert
assert abs(vert["fx"] - expectedFxCorrectedV) < 1e-6, vert
assert abs(vert["fx"] - fillWide["fx"]) > 1.0, (
    "sanity: Vertical must genuinely differ from Fill for these inputs")
print("computeCameraIntrinsics Vertical OK")

# pixelAspectRatio: a non-1.0 value changes deviceAspect and can flip which
# branch Fill takes. At 1920x1080 with pixelAspectRatio=1.0, deviceAspect
# (~1.778) > filmAspect (~1.499) -- Fill's "if" branch. Pick a
# pixelAspectRatio that pushes deviceAspect below filmAspect instead, and
# confirm Fill's OTHER branch fires (proving pixelAspectRatio is actually
# read, not ignored).
paRatio = 0.7  # deviceAspect = (1920/1080)*0.7 ~= 1.244, now < filmAspect ~1.499
deviceAspectPA = (w / float(h)) * paRatio
assert deviceAspectPA < filmAspect, "test premise: pixelAspectRatio must flip the comparison here"
fillPA = sdpc.computeCameraIntrinsics(35.0, hAp, vAp, w, h, filmFit="fill", pixelAspectRatio=paRatio)
expectedFyRawPA = (35.0 / (vAp * 25.4)) * h
expectedHEffPA = vAp * deviceAspectPA
expectedFxCorrectedPA = (35.0 / (expectedHEffPA * 25.4)) * w
assert abs(fillPA["fy"] - expectedFyRawPA) < 1e-6, fillPA
assert abs(fillPA["fx"] - expectedFxCorrectedPA) < 1e-6, fillPA
print("computeCameraIntrinsics pixelAspectRatio affects the Fill branch decision OK")

# Overscan: not implemented yet in this task -- must raise, not guess.
try:
    sdpc.computeCameraIntrinsics(35.0, hAp, vAp, w, h, filmFit="overscan")
    raise AssertionError("expected NotImplementedError for filmFit='overscan' in this task")
except NotImplementedError:
    print("computeCameraIntrinsics overscan raises NotImplementedError (Task 2 will implement) OK")

# Unrecognized filmFit value.
try:
    sdpc.computeCameraIntrinsics(35.0, hAp, vAp, w, h, filmFit="diagonal")
    raise AssertionError("expected ValueError for an unrecognized filmFit value")
except ValueError:
    print("computeCameraIntrinsics rejects an unrecognized filmFit value OK")

# Integer enum form (Maya's raw attribute value) must work the same as the
# string form -- 0=Fill, 1=Horizontal, 2=Vertical, 3=Overscan.
fillFromInt = sdpc.computeCameraIntrinsics(35.0, hAp, vAp, w, h, filmFit=0)
assert abs(fillFromInt["fx"] - fillWide["fx"]) < 1e-6
assert abs(fillFromInt["fy"] - fillWide["fy"]) < 1e-6
horizFromInt = sdpc.computeCameraIntrinsics(35.0, hAp2, vAp2, w2, h2, filmFit=1)
assert abs(horizFromInt["fx"] - horiz["fx"]) < 1e-6
assert abs(horizFromInt["fy"] - horiz["fy"]) < 1e-6
print("computeCameraIntrinsics integer filmFit enum form OK")
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_synthetic_data_point_cloud.py
```
Expected: FAIL — `computeCameraIntrinsics()` doesn't accept `filmFit`/`pixelAspectRatio`/`overscan` yet.

- [ ] **Step 3: Rewrite `computeCameraIntrinsics()` in `python/maroSyntheticDataPointCloud.py`**

Replace the existing function (keep everything else in the file — `findOiiotool`, `convertExrToPfm`, `parsePfm`, `unprojectDepthToPoints`, `writePly`, `updatePointCloudNode` — completely unchanged) with:

```python
# Maya의 filmFit enum 순서(정수 attribute 값과 대응) -- 문서화된 Maya 카메라
# 관례, cmds.attributeQuery("filmFit", node=<camera>, listEnum=True)로도
# 확인 가능.
_FILM_FIT_MODES = ("fill", "horizontal", "vertical", "overscan")


def _normalizeFilmFit(filmFit):
    """filmFit을 정규화된 소문자 문자열로 바꾼다. 문자열(대소문자 무관)이나
    Maya의 원시 정수 enum 값(0-3) 둘 다 받는다."""
    if isinstance(filmFit, str):
        normalized = filmFit.strip().lower()
    else:
        try:
            normalized = _FILM_FIT_MODES[int(filmFit)]
        except (ValueError, IndexError, TypeError):
            normalized = None
    if normalized not in _FILM_FIT_MODES:
        raise ValueError(
            "알 수 없는 filmFit 값: {!r} (지원: {})".format(filmFit, _FILM_FIT_MODES))
    return normalized


def computeCameraIntrinsics(focalLengthMm, horizontalFilmApertureIn, verticalFilmApertureIn,
                             widthPx, heightPx, filmFit="fill", pixelAspectRatio=1.0, overscan=1.0):
    """Maya 카메라의 초점거리(mm)/필름 백(inch)/Film Fit 모드/픽셀종횡비/
    오버스캔과 렌더 해상도로 핀홀 카메라 내부 파라미터(fx, fy, cx, cy, 전부
    픽셀 단위)를 계산한다.

    Film Fit 모드가 필름 백 종횡비와 렌더 해상도 종횡비의 불일치를 어떻게
    보정하는지 반영한다(설계 스펙 2026-09-05-maro-arnold-film-fit-correction-
    design.md §3) -- 2026-09-04 최종 리뷰가 발견한 ~11-19% 기하 오차의
    원인이었던 부분. `filmFit="fill"`(기본값)이 Maya 카메라의 기본 설정과
    일치한다.

    - `filmAspect = horizontalFilmApertureIn / verticalFilmApertureIn`
    - `deviceAspect = (widthPx / heightPx) * pixelAspectRatio` (Maya가 Film
      Fit 판정에 실제로 쓰는 정의 -- 정사각 픽셀이 아니면 단순
      widthPx/heightPx와 다르다)

    Fill: 두 종횡비 중 필름 쪽이 더 좁으면(`filmAspect < deviceAspect`)
    가로를 그대로 쓰고 세로를 다시 계산, 반대면 대칭. Horizontal/Vertical은
    그 중 한쪽을 종횡비 관계와 무관하게 항상 그대로 쓴다. Overscan은 아직
    지원하지 않는다(`NotImplementedError`) -- 정확한 동작이 실측으로
    확정되지 않은 채 추측으로 구현하지 않는다(계획 문서 Task 2)."""
    mode = _normalizeFilmFit(filmFit)
    if mode == "overscan":
        raise NotImplementedError(
            "filmFit='overscan'은 아직 지원되지 않습니다 -- 정확한 보정 공식이 "
            "실측으로 확정된 뒤 추가될 예정입니다.")

    filmAspect = horizontalFilmApertureIn / verticalFilmApertureIn
    deviceAspect = (widthPx / float(heightPx)) * pixelAspectRatio

    hEff = horizontalFilmApertureIn
    vEff = verticalFilmApertureIn

    if mode == "horizontal":
        vEff = hEff / deviceAspect
    elif mode == "vertical":
        hEff = vEff * deviceAspect
    else:  # fill
        if filmAspect < deviceAspect:
            vEff = hEff / deviceAspect
        else:
            hEff = vEff * deviceAspect

    fx = (focalLengthMm / (hEff * 25.4)) * widthPx
    fy = (focalLengthMm / (vEff * 25.4)) * heightPx
    return {"fx": fx, "fy": fy, "cx": widthPx / 2.0, "cy": heightPx / 2.0}
```

- [ ] **Step 4: Run test to verify it passes**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_synthetic_data_point_cloud.py
```
Expected: every `OK` line prints, including the **original**, untouched `computeCameraIntrinsics OK` line near the top of the file — if that one fails, the branch logic is backwards (see Global Constraints).

- [ ] **Step 5: Build and run the full suite**

```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure
```

- [ ] **Step 6: Commit**

```bash
git add python/maroSyntheticDataPointCloud.py tests/maya/test_synthetic_data_point_cloud.py
git commit -m "feat(synthetic-data): add Film Fit (Fill/Horizontal/Vertical) + pixelAspectRatio to computeCameraIntrinsics"
```

---

### Task 2: Overscan mode + independent `MFnCamera` verification + real Arnold render confirmation

**Files:**
- Modify: `python/maroSyntheticDataPointCloud.py`
- Modify: `tests/maya/test_synthetic_data_point_cloud.py`

**Interfaces:**
- Consumes: Task 1's `computeCameraIntrinsics()`/`_normalizeFilmFit()`/`_FILM_FIT_MODES`.
- Produces: `computeCameraIntrinsics(..., filmFit="overscan", ...)` now returns real values instead of raising.

This is the highest-uncertainty task in this plan — the design spec (§3, §7) explicitly does not commit to an Overscan formula. Do the investigation for real; do not implement from memory.

- [ ] **Step 1: Investigate Maya's actual Overscan behavior**

In an interactive or batch Maya session with the `mtoa` plugin loaded (this environment has confirmed working batch Arnold — see `.superpowers/sdd/arnold-task-4-report.md` and `arnold-final-review-fix-report.md` from 2026-09-04 for the established pattern), read:
```python
cmds.help("camera")  # or the Maya documentation's camera node reference for "overscan"
```
and/or Autodesk's Maya camera node documentation for the `overscan` attribute's exact effect when `filmFit="overscan"`. Working hypothesis to start from (not yet confirmed): Overscan scales BOTH `horizontalFilmApertureIn` and `verticalFilmApertureIn` by the `overscan` factor uniformly, and then applies the *same* logic as Fill mode using the scaled apertures (since scaling both by the same factor doesn't change `filmAspect`, the "which side is narrower" decision Fill makes is unaffected — only the absolute FOV widens uniformly, which is consistent with Overscan's purpose of capturing extra margin around the nominal frame for post-effects/stabilization safety). Confirm or refute this against Maya's actual documented behavior before writing code.

- [ ] **Step 2: Build the independent `MFnCamera` cross-check — the real verification oracle for this whole plan**

Write a standalone or committed mayapy test (your judgment on which, per Step 5) that, for each of Fill/Horizontal/Vertical (already implemented in Task 1) AND your Overscan hypothesis:
1. Creates a real Maya camera (`cmds.camera()`), sets its `filmFit`, `horizontalFilmAperture`, `verticalFilmAperture`, `focalLength`, and (for Overscan) `overscan` attributes to known values.
2. Uses `maya.api.OpenMaya.MFnCamera` on that camera's shape to call `setAspectRatio(deviceAspect)` (where `deviceAspect = (widthPx/heightPx) * pixelAspectRatio` for your target render resolution) followed by `horizontalFieldOfView()`/`verticalFieldOfView()` (both in radians). **Verify this `setAspectRatio()` call is actually what controls the FOV computation** (not silently overridden by Maya's own `defaultResolution`) — do this by first calling it with a deviceAspect matching whatever `defaultResolution` currently has (sanity check: FOV should match `cmds.camera(cameraShape, query=True, ...)`-derived expectations) and then with a deliberately different deviceAspect, confirming the returned FOV actually changes accordingly. Document what you find; if `setAspectRatio()` isn't the right mechanism, find the one that is (e.g., temporarily setting `defaultResolution.width`/`.height`/`.deviceAspectRatio` and restoring them afterward) rather than assuming.
3. Converts the returned FOV to expected fx/fy via the standard relation `fx = widthPx / (2 * tan(horizontalFOV / 2))`, `fy = heightPx / (2 * tan(verticalFOV / 2))`.
4. Compares against `computeCameraIntrinsics()`'s own output for the same inputs, with a tight tolerance (this is an independent authoritative source, not a hand-derived one — a real mismatch here means the shipped formula is wrong, not that the tolerance needs loosening).

Run this for at least 3-4 distinct (filmFit, resolution, pixelAspectRatio) combinations per mode, including at least one where `pixelAspectRatio != 1.0`.

- [ ] **Step 3: Reconcile any mismatches**

If Fill/Horizontal/Vertical (Task 1's already-shipped formulas) disagree with the `MFnCamera` oracle, that is a real bug in Task 1's work — fix `computeCameraIntrinsics()` accordingly (not the oracle, and not by loosening tolerances) and note this clearly in your report, since it means Task 1's review should be considered incomplete. If only Overscan disagrees with your Step 1 hypothesis, refine the Overscan formula until it matches the oracle.

- [ ] **Step 4: Implement the confirmed Overscan formula**

Replace the `NotImplementedError` branch for `mode == "overscan"` in `computeCameraIntrinsics()` with the real, oracle-confirmed formula. Update the function's docstring to describe it (matching the existing style for Fill/Horizontal/Vertical) instead of saying "not yet supported."

- [ ] **Step 5: Commit the `MFnCamera` oracle as a permanent regression test**

Whatever form your Step 2 investigation script took, distill it into a committed addition to `tests/maya/test_synthetic_data_point_cloud.py` (or a clearly-named new test file if you judge that cleaner given it needs a live Maya camera rather than pure math — your call, but register any new file in `tests/CMakeLists.txt`'s `foreach(maya_test ...)` list and `src/maro_plugin/CMakeLists.txt` is NOT needed since this is test-only, no new production module). This test is valuable permanent regression coverage — a future change to any mode's formula should be caught by disagreement with Maya's own `MFnCamera`, not just by re-deriving expected values by hand again.

- [ ] **Step 6: Real Arnold render confirmation (go/no-go for Overscan specifically)**

Using the same methodology already established in `.superpowers/sdd/arnold-task-4-report.md` (synthetic data camera + `renderSyntheticFrame()` + the depth reprojection pipeline against a plane/cube at a known position), render at least one scene with `filmFit="overscan"` and a non-1.0 `overscan` value, and confirm the reprojected point cloud's geometry matches the known real-world placement (within the same kind of tolerance used in that report). This is the final, most authoritative confirmation for the one mode this plan couldn't derive with full confidence up front. Record the exact numbers in your report, the same way the 2026-09-04 tasks did.

- [ ] **Step 7: Run the full suite**

```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure
```

- [ ] **Step 8: Commit**

```bash
git add python/maroSyntheticDataPointCloud.py tests/maya/test_synthetic_data_point_cloud.py tests/CMakeLists.txt
git commit -m "feat(synthetic-data): add Overscan Film Fit mode, verified against MFnCamera + a real render"
```

If Step 1-3 genuinely cannot pin down a confirmed Overscan formula within reasonable effort, report **NEEDS_CONTEXT** or **BLOCKED** with a precise description of what was tried and what's still ambiguous — do not ship a formula that only passed because its own test was written to match it.

---

### Task 3: Wire `filmFit`/`pixelAspectRatio`/`overscan` through the calibration pipeline

**Files:**
- Modify: `python/maroSyntheticDataRender.py`
- Modify: `tests/maya/test_synthetic_data_render.py`
- Modify: `python/maroSyntheticDataPanel.py`
- Modify: `docs/maro-main-ui-manual-checklist.md`

**Interfaces:**
- Consumes: Task 1+2's completed `computeCameraIntrinsics()`.
- Produces: `buildCalibrationDict()`'s returned dict gains three new keys: `filmFit` (string, normalized the same way `computeCameraIntrinsics` accepts — store it as whatever `_normalizeFilmFit`-compatible form is simplest, your call, but be consistent), `pixelAspectRatio`, `overscan`.

- [ ] **Step 1: Read the current `buildCalibrationDict()` and the panel's `_onRenderNow()` in full**

Confirm they still match what's quoted below before editing (both were touched by the 2026-09-04 final-review fix wave, so re-confirm current line numbers/exact content rather than assuming this plan's snapshot is still byte-exact).

- [ ] **Step 2: Write the failing test for the calibration dict's new fields**

Add to `tests/maya/test_synthetic_data_render.py`, extending the existing `buildCalibrationDict` test block (find it via the `calib = sdr.buildCalibrationDict(...)` call):

```python
# --- buildCalibrationDict: Film Fit fields (2026-09-05 follow-up) ---
cmds.setAttr(cam + ".filmFit", 1)  # Horizontal, per Maya's documented enum order
camShape = cmds.listRelatives(cam, shapes=True, fullPath=True)[0]
cmds.setAttr(camShape + ".pixelAspectRatio", 1.5)
cmds.setAttr(camShape + ".overscan", 1.2)
calibFilmFit = sdr.buildCalibrationDict(cam, cmds.currentTime(query=True))
assert calibFilmFit["filmFit"] in ("horizontal", 1), calibFilmFit["filmFit"]
assert abs(calibFilmFit["pixelAspectRatio"] - 1.5) < 1e-9, calibFilmFit
assert abs(calibFilmFit["overscan"] - 1.2) < 1e-9, calibFilmFit
print("buildCalibrationDict Film Fit fields OK")
```

(Adjust `calibFilmFit["filmFit"] in ("horizontal", 1)` to match whatever exact form you chose in Task 3 Step 3 below — the point of this assertion is that the stored value round-trips correctly through `computeCameraIntrinsics()`'s `_normalizeFilmFit()`, not that it's literally the string `"horizontal"`.)

Note: confirm `cmds.setAttr(cam + ".filmFit", 1)` works on the transform name or whether it needs the shape (`camShape + ".filmFit"`) — `filmFit`/`pixelAspectRatio`/`overscan` are camera SHAPE attributes, and `buildCalibrationDict()`'s existing code already does `cameraShape = cmds.listRelatives(cameraTransform, shapes=True, fullPath=True)[0]` for `focalLength` etc. — verify empirically and fix the test snippet above if the transform-level `setAttr` doesn't work (Maya sometimes allows querying/setting shape attributes through the transform as a convenience, but don't assume it here without checking).

- [ ] **Step 3: Run test to verify it fails**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_synthetic_data_render.py
```

- [ ] **Step 4: Extend `buildCalibrationDict()` in `python/maroSyntheticDataRender.py`**

Add three new `cmds.getAttr` reads (same pattern as the existing `focalLength`/`hFilmAperture`/`vFilmAperture` reads) and three new keys in the returned dict:

```python
    filmFit = cmds.getAttr(cameraShape + ".filmFit")
    pixelAspectRatio = cmds.getAttr(cameraShape + ".pixelAspectRatio")
    overscan = cmds.getAttr(cameraShape + ".overscan")
```

and add `"filmFit": filmFit, "pixelAspectRatio": pixelAspectRatio, "overscan": overscan,` to the returned dict (alongside the existing keys — don't remove or rename anything already there, this is purely additive).

- [ ] **Step 5: Run test to verify it passes**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_synthetic_data_render.py
```

- [ ] **Step 6: Update `python/maroSyntheticDataPanel.py`'s `_onRenderNow()`**

Find the existing `computeCameraIntrinsics()` call:

```python
            intrinsics = sdpc.computeCameraIntrinsics(
                focalLengthMm=calibration["focalLength"],
                horizontalFilmApertureIn=calibration["horizontalFilmAperture"],
                verticalFilmApertureIn=calibration["verticalFilmAperture"],
                widthPx=calibration["resolutionWidth"],
                heightPx=calibration["resolutionHeight"])
```

and add the three new keyword arguments so it reads:

```python
            intrinsics = sdpc.computeCameraIntrinsics(
                focalLengthMm=calibration["focalLength"],
                horizontalFilmApertureIn=calibration["horizontalFilmAperture"],
                verticalFilmApertureIn=calibration["verticalFilmAperture"],
                widthPx=calibration["resolutionWidth"],
                heightPx=calibration["resolutionHeight"],
                filmFit=calibration["filmFit"],
                pixelAspectRatio=calibration["pixelAspectRatio"],
                overscan=calibration["overscan"])
```

No other change to the panel is needed — it already reads `calibration` from the JSON file `renderSyntheticFrame()` wrote (per the 2026-09-04 final-review fix), so the three new keys flow through automatically once `buildCalibrationDict()` (Step 4) writes them.

- [ ] **Step 7: Add a manual checklist item**

Read `docs/maro-main-ui-manual-checklist.md`'s existing "Maro 합성 데이터 렌더 (Arnold)" section (added 2026-09-04) to match its exact format, and add a new go/no-go item alongside the existing ones (e.g. near the "픽셀 부호/방향 규약 확정" item):

```markdown
- [ ] **[go/no-go] Film Fit 모드 4종 + 오버스캔 실측 확정** — 합성 데이터
      카메라의 `filmFit`을 Fill/Horizontal/Vertical/Overscan 각각으로
      바꿔가며(오버스캔은 `overscan` 값도 1.0이 아닌 값으로) 알려진 위치의
      평면/오브젝트를 렌더 → 역투영 결과가 실제 거리/위치와 일치하는지
      확인한다. 2026-09-05에 `MFnCamera` 교차 검증과 최소 1회 실제 렌더로
      이미 확인됐지만(계획: `2026-09-05-maro-arnold-film-fit-correction.md`),
      이 항목은 그 결과를 인터랙티브 세션에서 다시 한번 사람이 눈으로
      확인하는 자리다.
```

Also update the earlier Film Fit-related note this section may already carry (the one added 2026-09-04 documenting the limitation as "알려진 제한 사항, 미수정") to reflect that it's now fixed — read the current text first and correct it rather than leaving stale "미수정" wording next to a "확정" checklist item that would contradict it.

- [ ] **Step 8: Build and run the full suite**

```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure
```

- [ ] **Step 9: Commit**

```bash
git add python/maroSyntheticDataRender.py tests/maya/test_synthetic_data_render.py python/maroSyntheticDataPanel.py docs/maro-main-ui-manual-checklist.md
git commit -m "feat(synthetic-data): wire Film Fit/pixelAspectRatio/overscan through calibration JSON to the panel"
```

---

## Self-Review Notes

- **Spec coverage:** §3 (per-mode formulas) → Task 1 (Fill/Horizontal/Vertical) + Task 2 (Overscan). §4 (API expansion + propagation) → Task 1 (signature) + Task 3 (`buildCalibrationDict`/panel wiring). §5 (3-tier verification: self-consistency, `MFnCamera` cross-check, real render) → Task 1 Step 1 (tier 1), Task 2 Steps 2-3 (tier 2, applied retroactively to Task 1's modes too) and Step 6 (tier 3). §6 (global constraints: no new C++, backward compatibility) → this plan's Global Constraints section. §7 (Overscan uncertainty, must not ship a guess) → Task 2's explicit investigate-before-implement structure and its `NEEDS_CONTEXT`/`BLOCKED` escape hatch.
- **Type/name consistency:** `_FILM_FIT_MODES` tuple order (fill/horizontal/vertical/overscan, indices 0-3) is defined once in Task 1 and referenced (not re-declared) by Task 2's Overscan work and Task 3's calibration round-trip test. `computeCameraIntrinsics()`'s parameter names (`filmFit`, `pixelAspectRatio`, `overscan`) are used identically in `buildCalibrationDict()`'s new dict keys (Task 3) and the panel's call site (Task 3) — no renaming across the handoff.
- **No placeholders:** the one deliberately-incomplete piece (Overscan raising `NotImplementedError` at the end of Task 1) is explicitly a real, tested behavior for that task's scope — not a silent TODO — and Task 2's entire structure exists specifically to replace it with a real, verified implementation, with an honest escape hatch if verification doesn't converge.
