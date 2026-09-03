# Maro LiDAR Sensor Validation + Precise Mesh Collision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the two LiDAR/mesh-collision checks Tech Diag's original spec deferred to "after Phase 5 ships": range/FOV-aware LiDAR sensor validation (via a new multi-mesh-capable scan path and a scene-safe query command) and polygon-level precise mesh collision (via Embree's `rtcCollide`), wired into the existing Maya-side Tech Diag check pipeline.

**Architecture:** C++ changes are confined to `maro_lidar` (a new `CollisionEngine` alongside the existing `ScanEngine`) and `maro_plugin` (a reordered/multi-mesh `scanLidarNode()`, two new query-only commands). Python changes are confined to `python/maroTechDiag.py` (new pure check functions + two Maya-calling collector helpers), following the file's existing "pure function + `_run*Checks()` collector" split.

**Tech Stack:** C++17, Embree 4 (`maro_lidar`), Maya C++ API 2.0/1.0, Python 3, `maya.cmds`, `maya.api.OpenMaya`, mayapy batch tests, CMake/CTest.

**Spec:** `docs/superpowers/specs/2026-09-04-maro-lidar-sensor-validation-design.md`

## Global Constraints

- Build always with `--config Release`; `ctest --test-dir out/build -C Release --output-on-failure` must pass fully (**all** existing tests, not just new ones) before any task is done.
- Build/test command for every task:
  ```powershell
  cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
      if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
  }
  cmake --build out/build --config Release
  ctest --test-dir out/build -C Release --output-on-failure
  ```
- New C++ query commands (`maroQueryLidarScan`, `maroCheckMeshCollision`) are **query-only**: no `MDGModifier`, `isUndoable() const override { return false; }`.
- Every new C++ command follows the existing error-boundary discipline: `maro::ScopedCommandContext ctxMarker("<ClassName>")`, `try { ... } catch (const std::exception&) { ... } catch (...) { ... }`, and `maro::BoadMaro::error(siteTag, message, maro::onfix::capture(...))` on every failure path.
- Tech Diag principle (unchanged, carried from the original Tech Diag plan): checks never mutate the scene; results are recomputed fresh on every "run check" click, never persisted.
- New/modified `.py` code never calls `setStyleSheet()`.
- **Task 1 is the highest-regression-risk task** — it rewrites `scanLidarNode()`, which is live in the real ROS publish path (`MaroPump::collectLidarScans`) and the existing `maroSnapshotLidarScan` command. Its Step "run the full suite" is not optional busywork: `tests/maya/test_lidar_node.py`, `tests/maya/test_lidar_publish.py`, and `tests/maya/test_lidar_commands.py` must all stay green, and any red there blocks the task regardless of whether the new test passes.
- Double values serialized into a Maya command's string result (Task 2) must be written with `std::ostringstream` imbued with `std::locale::classic()` **and** `std::setprecision(std::numeric_limits<double>::max_digits10)` — this codebase already hit a real bug from an un-imbued `ostringstream` splitting a comma-separated field under a non-`.`-decimal locale (`MaroAxisEditorCommands.cpp`'s `colorStream`, see Minor-5 in that file's history); the added precision requirement is new here because this contract carries matrix/position values that must round-trip losslessly for Python's local-frame trigonometry, unlike that earlier 0-1 color contract.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `src/maro_plugin/MaroLidarScan.h` | Modify | Promote `extractMeshBuffers()` to a public declaration; add `LidarGeometry` struct + optional out-param on `scanLidarNode()` |
| `src/maro_plugin/MaroLidarScan.cpp` | Modify | Multi-mesh merge, control-flow reorder, `LidarGeometry` output |
| `tests/maya/test_lidar_multi_mesh.py` | Create | Multi-mesh regression + occlusion + partial-extraction-failure tests |
| `src/maro_plugin/MaroLidarCommands.h` / `.cpp` | Modify | Add `MaroQueryLidarScanCommand` |
| `src/maro_plugin/MaroPluginMain.cpp` | Modify | Register/deregister `maroQueryLidarScan` and `maroCheckMeshCollision` |
| `tests/maya/test_lidar_scan_query.py` | Create | `maroQueryLidarScan` flat-array contract + independent matrix cross-check |
| `python/maroTechDiag.py` | Modify | `parseLidarScanQuery`, 4 new dynamic LiDAR checks, `refineMeshCollisions`, collector helpers, `_runMayaSideChecks()` wiring |
| `tests/maya/test_tech_diag.py` | Modify | Pure-function tests for the 4 new checks + `refineMeshCollisions`, end-to-end integration cases |
| `src/maro_lidar/include/maro_lidar/CollisionEngine.h` | Create | `CollisionEngine` class declaration |
| `src/maro_lidar/src/CollisionEngine.cpp` | Create | `rtcCollide`-based implementation |
| `src/maro_lidar/CMakeLists.txt` | Modify | Add `CollisionEngine.cpp` to `maro_lidar`'s sources |
| `src/maro_plugin/MaroCollisionCommands.h` / `.cpp` | Create | `MaroCheckMeshCollisionCommand` |
| `src/maro_plugin/CMakeLists.txt` | Modify | Add `MaroCollisionCommands.cpp` |
| `tests/maya/test_mesh_collision.py` | Create | `maroCheckMeshCollision` contract (true/false/unknown) |
| `tests/CMakeLists.txt` | Modify | Register `lidar_multi_mesh`, `lidar_scan_query`, `mesh_collision` |
| `docs/maro-main-ui-manual-checklist.md` | Modify | New rows in the existing Tech Diag manual-check table |

---

### Task 1: `scanLidarNode()` multi-mesh support + control-flow reorder

**Files:**
- Modify: `src/maro_plugin/MaroLidarScan.h`
- Modify: `src/maro_plugin/MaroLidarScan.cpp`
- Create: `tests/maya/test_lidar_multi_mesh.py`
- Modify: `tests/CMakeLists.txt`

**Interfaces:**
- Consumes: nothing new (this task only changes `scanLidarNode()`'s internals).
- Produces:
  - `bool extractMeshBuffers(const MObject& meshNode, std::vector<float>& vertices, std::vector<std::uint32_t>& indices)` — now a public `namespace maro` function declared in `MaroLidarScan.h` (previously file-local to `MaroLidarScan.cpp`'s anonymous namespace). Task 4 depends on this exact name/signature.
  - `scanLidarNode()`'s public signature and `LidarScanResult` enum are **unchanged** by this task (Task 2 adds the `LidarGeometry*` out-param later) — only its internal ordering and mesh handling change.

- [ ] **Step 1: Read the current `src/maro_plugin/MaroLidarScan.h` and `.cpp` in full**

Confirm line numbers before editing — this plan quotes the code as last read; if it has drifted, adapt the edits to the actual current content rather than assuming exact line numbers.

- [ ] **Step 2: Write the failing regression test**

Create `tests/maya/test_lidar_multi_mesh.py`:

```python
"""scanLidarNode()의 다중 메쉬 지원을 고정한다 -- 이전에는 targetMeshes[]에서
첫 번째로 연결된 메쉬만 스캔 대상이었다(설계 스펙 §3.1). 이 테스트는 (a) 첫
번째가 아닌 인덱스에 연결된 메쉬도 실제로 스캔되는지, (b) 여러 타겟 메쉬가
레이 경로에 겹칠 때 가장 가까운 히트가 물리적으로 맞게 나오는지, (c) 폴리곤이
아닌 항목이 섞여도 나머지로 스캔이 계속되는지를 확인한다."""
import os

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)
cmds.currentUnit(angle="rad")

# 곧장 아래를 보는 레이 하나(test_lidar_commands.py와 같은 관례:
# computeRayDirections(vertical=-pi/2)는 로컬 (0,-1,0)을 낸다).
lidar = cmds.createNode("maroLidar")
lidar = cmds.ls(lidar, long=True)[0]
cmds.setAttr(lidar + ".verticalSamples", 1)
cmds.setAttr(lidar + ".horizontalSamples", 1)
cmds.setAttr(lidar + ".verticalMinAngle", -1.5707963267948966)
cmds.setAttr(lidar + ".horizontalMinAngle", 0.0)
cmds.setAttr(lidar + ".rangeMin", 0.0)
cmds.setAttr(lidar + ".rangeMax", 5000.0)

pointCloud = cmds.createNode("maroPointCloud")
pointCloud = cmds.ls(pointCloud, long=True)[0]


def _points(lidarName, cloudName):
    cmds.maroSnapshotLidarScan(lidarName, cloudName)
    pts = cmds.getAttr(cloudName + ".points")
    return pts if pts else []


# targetMeshes[0]: 레이 경로 밖(x=2000 근방)에 둬서 절대 안 맞게 한다.
offPathPlane, _ = cmds.polyPlane(
    name="offPathPlane", width=100, height=100, subdivisionsX=1, subdivisionsY=1)
cmds.setAttr(offPathPlane + ".translateX", 2000)
cmds.connectAttr(offPathPlane + ".message", lidar + ".targetMeshes[0]")

before = _points(lidar, pointCloud)
assert len(before) == 0, (
    "sanity check: a target mesh outside the ray path must not be hit, got {}".format(before))
print("off-path-only sanity OK")

# targetMeshes[1] (인덱스 0이 아님): 레이 경로 위, Y=-500.
nearPlane, _ = cmds.polyPlane(
    name="nearPlane", width=2000, height=2000, subdivisionsX=1, subdivisionsY=1)
cmds.setAttr(nearPlane + ".translateY", -500)
cmds.connectAttr(nearPlane + ".message", lidar + ".targetMeshes[1]")

afterSecondIndex = _points(lidar, pointCloud)
assert len(afterSecondIndex) == 1, (
    "expected the ray to hit nearPlane connected at targetMeshes[1] (previously "
    "ignored -- only targetMeshes[0] was ever scanned), got {}".format(afterSecondIndex))
assert abs(afterSecondIndex[0][1] - (-500.0)) < 1e-2, afterSecondIndex
print("second-index target mesh is now scanned OK (regression for the pre-fix bug)")

# targetMeshes[2]: 레이 경로 위, nearPlane보다 더 먼 Y=-800. 가장 가까운
# 히트(-500)가 나와야지, 병합 순서와 무관하게 더 먼 평면에 가려지면 안 된다.
farPlane, _ = cmds.polyPlane(
    name="farPlane", width=2000, height=2000, subdivisionsX=1, subdivisionsY=1)
cmds.setAttr(farPlane + ".translateY", -800)
cmds.connectAttr(farPlane + ".message", lidar + ".targetMeshes[2]")

afterThreeMeshes = _points(lidar, pointCloud)
assert len(afterThreeMeshes) == 1, (
    "expected exactly one nearest hit across three merged target meshes, "
    "got {}".format(afterThreeMeshes))
assert abs(afterThreeMeshes[0][1] - (-500.0)) < 1e-2, (
    "expected the nearest hit (Y=-500, nearPlane) to win over the farther "
    "plane (Y=-800), got {}".format(afterThreeMeshes))
print("nearest-hit occlusion across 3 merged target meshes OK")

# 메쉬가 아닌 트랜스폼이 targetMeshes에 섞여 있어도(설계 스펙 §3.3의 부분
# 실패 관용) 나머지 유효한 메쉬로 스캔이 계속돼야 한다.
nonMeshNode = cmds.createNode("transform", name="notAMesh")
cmds.connectAttr(nonMeshNode + ".message", lidar + ".targetMeshes[3]")
afterNonMesh = _points(lidar, pointCloud)
assert len(afterNonMesh) == 1, (
    "a non-mesh entry in targetMeshes must be skipped, not fail the whole "
    "scan, got {}".format(afterNonMesh))
assert abs(afterNonMesh[0][1] - (-500.0)) < 1e-2, afterNonMesh
print("partial-extraction-failure tolerance (non-mesh target) OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
```

- [ ] **Step 3: Register the test and run it to verify it fails**

In `tests/CMakeLists.txt`, find the `foreach(maya_test load axis_node binding ...)` list (the "plugin-only" group) and add `lidar_multi_mesh` to it, alphabetically near `lidar_menu`/`lidar_node` for readability (exact position doesn't matter — it's a flat list).

```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure -R maya_lidar_multi_mesh
```
Expected: FAIL at the `targetMeshes[1]` assertion (the pre-fix code only ever considers the first connected mesh, which here is `offPathPlane` — zero hits).

- [ ] **Step 4: Promote `extractMeshBuffers()` to a public declaration in `MaroLidarScan.h`**

Add `#include <cstdint>` near the top (needed for `std::uint32_t` in the new declaration), then add this declaration after `SceneUnit currentSceneUnit();` and before `scanLidarNode`'s declaration:

```cpp
// meshNode(트랜스폼 또는 셰이프)에서 월드 좌표 정점/삼각형 인덱스 버퍼를
// 뽑는다. scanLidarNode()의 다중 메쉬 병합과, 별도 파일의 정밀 메쉬 충돌
// 커맨드(CollisionEngine 기반)가 공유한다 -- 트랜스폼에 셰이프가 둘 이상인
// 경우(마킹 메뉴가 LiDAR 로케이터를 타겟 메쉬와 같은 트랜스폼에 올리는 경우
// 등, 최종 리뷰 C-1 참고)와 intermediate object 제외까지 이미 하드닝된
// 로직이므로 같은 문제를 두 번 풀지 않는다. 실패(메쉬를 못 찾음, MFnMesh
// 생성 실패, getPoints/getTriangles 실패)하면 false, vertices/indices는
// 그대로 둔다.
bool extractMeshBuffers(const MObject& meshNode, std::vector<float>& vertices,
                        std::vector<std::uint32_t>& indices);
```

- [ ] **Step 5: Rewrite `MaroLidarScan.cpp`**

Move the existing `extractMeshBuffers()` function (its full body, unchanged) OUT of the anonymous namespace it currently lives in and place it directly under `namespace maro {` (i.e., before the `namespace { ... }` block begins). Only its linkage changes — do not touch its body.

Replace `firstConnectedMesh()` (the function that currently remains in the anonymous namespace) with:

```cpp
// targetMeshes(메시지 배열)에 연결된 소스 노드를 전부 모은다.
// elementByLogicalIndex(0)이 아니라 evaluateNumElements()+
// elementByPhysicalIndex()를 쓴다: 논리 인덱스 접근은 없는 원소를 요구하면
// 데이터블록에 빈 원소를 만들어 넣는다(firstConnectedMesh가 쓰던 것과
// 같은 이유로 유지).
std::vector<MObject> allConnectedMeshes(MPlug meshesPlug) {
    std::vector<MObject> meshes;
    const unsigned int count = meshesPlug.evaluateNumElements();
    for (unsigned int i = 0; i < count; ++i) {
        MPlugArray sources;
        meshesPlug.elementByPhysicalIndex(i).connectedTo(sources, true, false);
        if (sources.length() > 0) meshes.push_back(sources[0].node());
    }
    return meshes;
}
```

Add `#include <cstdint>` to this file's includes if not already present (needed for `std::uint32_t` now that `extractMeshBuffers` is out of the anonymous namespace and this file also builds `mergedIndices` below).

Replace the entire body of `scanLidarNode()` with:

```cpp
LidarScanResult scanLidarNode(const MObject& lidarNode, maro::lidar::ScanEngine& engine,
                               const SceneUnit& unit, std::vector<Vec3>& outPoints) {
    outPoints.clear();
    MFnDependencyNode lidarFn(lidarNode);

    const int verticalSamples =
        lidarFn.findPlug(MaroLidarNode::aVerticalSamples, false).asInt();
    const double verticalMinAngle =
        lidarFn.findPlug(MaroLidarNode::aVerticalMinAngle, false).asMAngle().asRadians();
    const double verticalMaxAngle =
        lidarFn.findPlug(MaroLidarNode::aVerticalMaxAngle, false).asMAngle().asRadians();
    const int horizontalSamples =
        lidarFn.findPlug(MaroLidarNode::aHorizontalSamples, false).asInt();
    const double horizontalMinAngle =
        lidarFn.findPlug(MaroLidarNode::aHorizontalMinAngle, false).asMAngle().asRadians();
    const double horizontalMaxAngle =
        lidarFn.findPlug(MaroLidarNode::aHorizontalMaxAngle, false).asMAngle().asRadians();
    const double rangeMin = lidarFn.findPlug(MaroLidarNode::aRangeMin, false).asDouble();
    const double rangeMax = lidarFn.findPlug(MaroLidarNode::aRangeMax, false).asDouble();

    const double mayaPerMeter = 1.0 / unit.metersPerMayaUnit;
    const double rangeMinMaya = rangeMin * mayaPerMeter;
    const double rangeMaxMaya = rangeMax * mayaPerMeter;

    const double offsetTranslateXMeters =
        lidarFn.findPlug(MaroLidarNode::aOffsetTranslateX, false).asDouble();
    const double offsetTranslateYMeters =
        lidarFn.findPlug(MaroLidarNode::aOffsetTranslateY, false).asDouble();
    const double offsetTranslateZMeters =
        lidarFn.findPlug(MaroLidarNode::aOffsetTranslateZ, false).asDouble();
    const double offsetRotateX =
        lidarFn.findPlug(MaroLidarNode::aOffsetRotateX, false).asMAngle().asRadians();
    const double offsetRotateY =
        lidarFn.findPlug(MaroLidarNode::aOffsetRotateY, false).asMAngle().asRadians();
    const double offsetRotateZ =
        lidarFn.findPlug(MaroLidarNode::aOffsetRotateZ, false).asMAngle().asRadians();

    if (!std::isfinite(verticalMinAngle) || !std::isfinite(verticalMaxAngle) ||
        !std::isfinite(horizontalMinAngle) || !std::isfinite(horizontalMaxAngle) ||
        !std::isfinite(rangeMinMaya) || !std::isfinite(rangeMaxMaya) ||
        !std::isfinite(offsetTranslateXMeters) || !std::isfinite(offsetTranslateYMeters) ||
        !std::isfinite(offsetTranslateZMeters) || !std::isfinite(offsetRotateX) ||
        !std::isfinite(offsetRotateY) || !std::isfinite(offsetRotateZ)) {
        return LidarScanResult::kInvalidConfig;
    }
    // Embree가 문서로 요구하는 전제: 0 <= tnear <= tfar.
    if (rangeMinMaya < 0.0 || rangeMaxMaya < rangeMinMaya) return LidarScanResult::kInvalidConfig;

    // [다중 메쉬 지원] 유효 월드 행렬/원점 계산을 타겟 메쉬 확인보다
    // 앞으로 옮겼다 -- 이 값들은 타겟 메쉬 존재 여부와 무관하게 계산
    // 가능해야, 다음 태스크의 조회 커맨드가 kNoTargetMesh/
    // kMeshExtractFailed/kRayCountExceeded에서도 이 지오메트리를 돌려줄
    // 수 있다(설계 스펙 §3.4/§8).
    MDagPath lidarPath;
    if (MDagPath::getAPathTo(lidarNode, lidarPath) != MS::kSuccess) {
        return LidarScanResult::kInvalidConfig;
    }
    const MMatrix worldMatrix = lidarPath.inclusiveMatrix();

    MTransformationMatrix offsetXform;
    offsetXform.setTranslation(
        MVector(offsetTranslateXMeters * mayaPerMeter, offsetTranslateYMeters * mayaPerMeter,
                offsetTranslateZMeters * mayaPerMeter),
        MSpace::kTransform);
    offsetXform.rotateTo(MEulerRotation(offsetRotateX, offsetRotateY, offsetRotateZ));
    const MMatrix offsetMatrix = offsetXform.asMatrix();
    const MMatrix effectiveWorldMatrix = offsetMatrix * worldMatrix;

    const MVector worldOrigin(MPoint(0, 0, 0) * effectiveWorldMatrix);
    const Vec3 origin{worldOrigin.x, worldOrigin.y, worldOrigin.z};
    if (!isFinite(origin)) return LidarScanResult::kInvalidConfig;

    const long long rayCount = static_cast<long long>(verticalSamples) *
                               static_cast<long long>(horizontalSamples);
    if (rayCount > kMaxRaysPerScan) return LidarScanResult::kRayCountExceeded;

    // [다중 메쉬 지원] targetMeshes[]에 연결된 것 전부를 모아 하나의
    // 버퍼로 병합한다(설계 스펙 §3.2) -- 첫 번째 것만 보던 기존 동작을
    // 대체한다. 일부 메쉬만 추출에 실패해도 나머지로 계속 진행한다(§3.3).
    const std::vector<MObject> meshNodes =
        allConnectedMeshes(lidarFn.findPlug(MaroLidarNode::aTargetMeshes, false));
    if (meshNodes.empty()) return LidarScanResult::kNoTargetMesh;

    std::vector<float> mergedVertices;
    std::vector<std::uint32_t> mergedIndices;
    bool anyExtracted = false;
    for (const MObject& meshNode : meshNodes) {
        std::vector<float> vertices;
        std::vector<std::uint32_t> indices;
        if (!extractMeshBuffers(meshNode, vertices, indices)) continue;
        const std::uint32_t vertexOffset =
            static_cast<std::uint32_t>(mergedVertices.size() / 3);
        mergedVertices.insert(mergedVertices.end(), vertices.begin(), vertices.end());
        for (std::uint32_t index : indices) mergedIndices.push_back(index + vertexOffset);
        anyExtracted = true;
    }
    if (!anyExtracted) return LidarScanResult::kMeshExtractFailed;
    if (!engine.setMesh(mergedVertices, mergedIndices)) return LidarScanResult::kMeshExtractFailed;

    const auto localDirections = maro::lidar::computeRayDirections(
        verticalSamples, verticalMinAngle, verticalMaxAngle, horizontalSamples,
        horizontalMinAngle, horizontalMaxAngle);

    // 방향 벡터에서 평행이동 성분을 제거하기 위해 함께 뺄 기준점.
    const MVector directionBias = MVector(0, 0, 0) * effectiveWorldMatrix;

    for (const Vec3& localDir : localDirections) {
        const MVector localVec(localDir.x, localDir.y, localDir.z);
        const MVector worldDir = (localVec * effectiveWorldMatrix - directionBias).normal();
        const maro::lidar::RayHit hit =
            engine.castRay(origin, Vec3{worldDir.x, worldDir.y, worldDir.z}, rangeMinMaya, rangeMaxMaya);
        if (hit.hit && isFinite(hit.position)) outPoints.push_back(hit.position);
    }
    return LidarScanResult::kOk;
}
```

- [ ] **Step 6: Build and run the new test**

```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure -R maya_lidar_multi_mesh
```
Expected: all `OK` lines print, exit 0.

- [ ] **Step 7: Run the full suite — regression check is the point of this step**

```powershell
ctest --test-dir out/build -C Release --output-on-failure
```
Expected: 100% pass, **including** `maya_lidar_node`, `maya_lidar_publish`, and `maya_lidar_commands` unchanged from before this task. If any of those three regress, do not proceed — the single-target-mesh path (still the only path those tests exercise) must produce bit-identical behavior to before this task, since merging one mesh's buffer with itself is a no-op.

- [ ] **Step 8: Commit**

```bash
git add src/maro_plugin/MaroLidarScan.h src/maro_plugin/MaroLidarScan.cpp tests/maya/test_lidar_multi_mesh.py tests/CMakeLists.txt
git commit -m "feat(lidar): scan all connected target meshes, not just the first"
```

---

### Task 2: New query command `maroQueryLidarScan`

**Files:**
- Modify: `src/maro_plugin/MaroLidarScan.h`
- Modify: `src/maro_plugin/MaroLidarScan.cpp`
- Modify: `src/maro_plugin/MaroLidarCommands.h`
- Modify: `src/maro_plugin/MaroLidarCommands.cpp`
- Modify: `src/maro_plugin/MaroPluginMain.cpp`
- Modify: `python/maroTechDiag.py`
- Create: `tests/maya/test_lidar_scan_query.py`
- Modify: `tests/CMakeLists.txt`

**Interfaces:**
- Consumes: Task 1's reordered `scanLidarNode()` and public `extractMeshBuffers()`.
- Produces:
  - `struct LidarGeometry { double rangeMinMaya, rangeMaxMaya, verticalMinAngle, verticalMaxAngle, horizontalMinAngle, horizontalMaxAngle; MMatrix effectiveWorldMatrix; }` (declared in `MaroLidarScan.h`).
  - `scanLidarNode(..., LidarGeometry* outGeometry = nullptr)` — same signature as Task 1 plus one new optional trailing parameter; existing callers (`MaroPump.cpp`, `MaroSnapshotLidarScanCommand`) are unaffected since they don't pass it.
  - Maya command `maroQueryLidarScan <lidarNode>` returning an `MStringArray` with this exact layout (`LIDAR_QUERY_HEADER_FIELDS = 24` elements before any hit-point data):
    | Index | Field |
    |---|---|
    | 0 | status: `"kOk"`\|`"kNoTargetMesh"`\|`"kMeshExtractFailed"`\|`"kInvalidConfig"`\|`"kRayCountExceeded"` |
    | 1 | `rangeMinMaya` |
    | 2 | `rangeMaxMaya` |
    | 3 | `verticalMinAngle` (rad) |
    | 4 | `verticalMaxAngle` (rad) |
    | 5 | `horizontalMinAngle` (rad) |
    | 6 | `horizontalMaxAngle` (rad) |
    | 7-22 | `effectiveWorldMatrix`, row-major (`matrix(r,c)` at index `7 + r*4 + c`) |
    | 23 | hit count N |
    | 24..24+3N-1 | hit points, x,y,z repeated N times |

    When status is `"kInvalidConfig"`, indices 1-22 are all `"0"` and N is `"0"` (array length exactly 24) — callers must check status before trusting indices 1-22.
  - `python/maroTechDiag.py`: `LIDAR_QUERY_HEADER_FIELDS = 24` and `parseLidarScanQuery(flat) -> dict` with keys `status`, `rangeMinMaya`, `rangeMaxMaya`, `verticalMinAngle`, `verticalMaxAngle`, `horizontalMinAngle`, `horizontalMaxAngle`, `effectiveWorldMatrix` (an `om2.MMatrix`), `hitPoints` (list of `(x, y, z)` tuples).

- [ ] **Step 1: Add `LidarGeometry` and the out-param to `MaroLidarScan.h`**

Add `#include <maya/MMatrix.h>` to the includes, then add above the `scanLidarNode` declaration:

```cpp
// scanLidarNode()가 실제 레이 원점/방향 계산에 쓰는 지오메트리를 호출부에
// 그대로 노출한다. maroQueryLidarScan(다음 스텝)이 Tech Diag의 정적 range/
// FOV 검사에 쓴다 -- Python이 좌표 변환 공식을 다시 유도하지 않고 이
// 행렬의 역행렬만 취하면 되게 하기 위함(설계 스펙 §4.2).
struct LidarGeometry {
    double rangeMinMaya = 0.0;
    double rangeMaxMaya = 0.0;
    double verticalMinAngle = 0.0;
    double verticalMaxAngle = 0.0;
    double horizontalMinAngle = 0.0;
    double horizontalMaxAngle = 0.0;
    MMatrix effectiveWorldMatrix;  // identity by default
};
```

Change the `scanLidarNode` declaration to:

```cpp
LidarScanResult scanLidarNode(const MObject& lidarNode, maro::lidar::ScanEngine& engine,
                               const SceneUnit& unit, std::vector<Vec3>& outPoints,
                               LidarGeometry* outGeometry = nullptr);
```

- [ ] **Step 2: Fill `outGeometry` in `MaroLidarScan.cpp`**

Change the function signature to match Step 1, then insert this block immediately after the existing `if (!isFinite(origin)) return LidarScanResult::kInvalidConfig;` line (i.e., right after `effectiveWorldMatrix`/`origin` are computed, and *before* the ray-count check):

```cpp
    if (outGeometry) {
        outGeometry->rangeMinMaya = rangeMinMaya;
        outGeometry->rangeMaxMaya = rangeMaxMaya;
        outGeometry->verticalMinAngle = verticalMinAngle;
        outGeometry->verticalMaxAngle = verticalMaxAngle;
        outGeometry->horizontalMinAngle = horizontalMinAngle;
        outGeometry->horizontalMaxAngle = horizontalMaxAngle;
        outGeometry->effectiveWorldMatrix = effectiveWorldMatrix;
    }
```

This placement means `outGeometry` is filled for every outcome except `kInvalidConfig` (which returns before reaching this line) — matching the spec §8 skip matrix exactly: `kNoTargetMesh`, `kMeshExtractFailed`, and `kRayCountExceeded` all still populate valid geometry.

- [ ] **Step 3: Write the failing test for the command (before implementing it)**

Create `tests/maya/test_lidar_scan_query.py`:

```python
"""maroQueryLidarScan()의 평탄 배열 계약을 고정한다 -- Tech Diag의 새 LiDAR
동적 검사(다음 태스크)가 이 계약 위에서 동작하므로, 행렬 직렬화 순서가
실제로 Python 쪽 재구성과 맞는지 독립적으로 교차 검증한다(이 프로젝트가
좌표/행렬 계약에서 이미 여러 번 겪은 실수 패턴 -- 손으로 가정하지 않고
실측한다)."""
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.api.OpenMaya as om2  # noqa: E402
import maya.cmds as cmds  # noqa: E402

_pythonDir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "python")
if _pythonDir not in sys.path:
    sys.path.insert(0, _pythonDir)

import maroTechDiag as diag  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)
cmds.currentUnit(angle="rad")
cmds.currentUnit(linear="cm")

# --- kOk: 메쉬 연결 + 히트 있음 ---
lidar = cmds.createNode("maroLidar")
lidar = cmds.ls(lidar, long=True)[0]
cmds.setAttr(lidar + ".verticalSamples", 1)
cmds.setAttr(lidar + ".horizontalSamples", 1)
cmds.setAttr(lidar + ".verticalMinAngle", -1.5707963267948966)
cmds.setAttr(lidar + ".horizontalMinAngle", 0.0)
cmds.setAttr(lidar + ".rangeMin", 0.0)
cmds.setAttr(lidar + ".rangeMax", 5000.0)
ground, _ = cmds.polyPlane(width=2000, height=2000, subdivisionsX=1, subdivisionsY=1)
cmds.setAttr(ground + ".translateY", -500)
cmds.connectAttr(ground + ".message", lidar + ".targetMeshes[0]")

flat = cmds.maroQueryLidarScan(lidar)
parsed = diag.parseLidarScanQuery(flat)
assert parsed["status"] == "kOk", parsed["status"]
assert abs(parsed["rangeMinMaya"] - 0.0) < 1e-6
assert abs(parsed["rangeMaxMaya"] - 5000.0) < 1e-6
assert abs(parsed["verticalMinAngle"] - (-1.5707963267948966)) < 1e-9
assert abs(parsed["horizontalMinAngle"] - 0.0) < 1e-9
assert len(parsed["hitPoints"]) == 1, parsed["hitPoints"]
assert abs(parsed["hitPoints"][0][1] - (-500.0)) < 1e-2, parsed["hitPoints"]
print("kOk parse OK")

identity = om2.MMatrix()
for r in range(4):
    for c in range(4):
        assert abs(parsed["effectiveWorldMatrix"](r, c) - identity(r, c)) < 1e-9, (
            r, c, parsed["effectiveWorldMatrix"])
print("identity-mount matrix OK")

# --- 행렬 계약 교차 검증: 비-identity 마운트 + 오프셋 ---
mount = cmds.createNode("transform", name="scanQueryMount")
cmds.setAttr(mount + ".translate", 300, 50, -20, type="double3")
cmds.setAttr(mount + ".rotateZ", 0.4)
lidar2 = cmds.createNode("maroLidar", parent=mount)
lidar2 = cmds.ls(lidar2, long=True)[0]
cmds.setAttr(lidar2 + ".offsetTranslateX", 1.0)
cmds.setAttr(lidar2 + ".offsetRotateY", 0.2)

flat2 = cmds.maroQueryLidarScan(lidar2)
parsed2 = diag.parseLidarScanQuery(flat2)
assert parsed2["status"] == "kNoTargetMesh", parsed2["status"]
assert len(parsed2["hitPoints"]) == 0

# 독립 재구성: MaroLidarScan.cpp와 같은 합성(오프셋 행렬 * 마운트 월드 행렬)을
# Python om2로 별도로 계산해, 커맨드가 돌려준 행렬과 원소 단위로 대조한다.
sel = om2.MSelectionList()
sel.add(lidar2)
mountWorldMatrix = sel.getDagPath(0).inclusiveMatrix()
mayaPerMeter = 100.0  # cm 씬
offsetXform = om2.MTransformationMatrix()
offsetXform.setTranslation(om2.MVector(1.0 * mayaPerMeter, 0.0, 0.0), om2.MSpace.kTransform)
offsetXform.setRotation(om2.MEulerRotation(0.0, 0.2, 0.0))
expectedMatrix = offsetXform.asMatrix() * mountWorldMatrix
for r in range(4):
    for c in range(4):
        assert abs(parsed2["effectiveWorldMatrix"](r, c) - expectedMatrix(r, c)) < 1e-6, (
            r, c, parsed2["effectiveWorldMatrix"], expectedMatrix)
print("non-identity-mount matrix cross-check OK")

# --- kInvalidConfig: rangeMax < rangeMin ---
cmds.setAttr(lidar2 + ".rangeMin", 100.0)
cmds.setAttr(lidar2 + ".rangeMax", 1.0)
flat3 = cmds.maroQueryLidarScan(lidar2)
parsed3 = diag.parseLidarScanQuery(flat3)
assert parsed3["status"] == "kInvalidConfig", parsed3["status"]
assert parsed3["rangeMinMaya"] == 0.0 and parsed3["rangeMaxMaya"] == 0.0
assert len(parsed3["hitPoints"]) == 0
print("kInvalidConfig zeroed-header OK")

# --- 잘못된 노드 타입 ---
try:
    cmds.maroQueryLidarScan(ground)
    raise AssertionError("expected maroQueryLidarScan to reject a non-maroLidar argument")
except RuntimeError:
    print("rejects non-maroLidar argument OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
```

Register it: add `lidar_scan_query` to `tests/CMakeLists.txt`'s `foreach(maya_test ...)` list.

```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure -R maya_lidar_scan_query
```
Expected: FAIL — `maroQueryLidarScan` and `parseLidarScanQuery` don't exist yet.

- [ ] **Step 4: Add `MaroQueryLidarScanCommand` to `MaroLidarCommands.h`**

```cpp
// <lidarNode>: lidarNode를 즉시 동기 스캔하되 씬을 전혀 바꾸지 않는다 --
// maroPointCloud도, MDGModifier도 없다. Tech Diag의 동적 LiDAR 검사(설계
// 스펙 2026-09-04)가 쓰는 유일한 조회 경로. 결과 형식은
// docs/superpowers/plans/2026-09-04-maro-lidar-sensor-validation.md의
// Task 2 표 참고.
class MaroQueryLidarScanCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
    bool isUndoable() const override { return false; }
};
```

- [ ] **Step 5: Implement it in `MaroLidarCommands.cpp`**

Add these includes at the top: `#include <cstdint>`, `#include <iomanip>`, `#include <limits>`, `#include <locale>`, `#include <sstream>`, `#include <maya/MMatrix.h>` (if not already transitively included).

Add a small anonymous-namespace helper and the command implementation (append to the file, inside `namespace maro { ... }`):

```cpp
namespace {

const char* lidarScanResultName(LidarScanResult result) {
    switch (result) {
        case LidarScanResult::kOk: return "kOk";
        case LidarScanResult::kNoTargetMesh: return "kNoTargetMesh";
        case LidarScanResult::kMeshExtractFailed: return "kMeshExtractFailed";
        case LidarScanResult::kInvalidConfig: return "kInvalidConfig";
        case LidarScanResult::kRayCountExceeded: return "kRayCountExceeded";
    }
    return "kUnknown";
}

void appendDouble(MStringArray& out, std::ostringstream& num, double value) {
    num.str("");
    num.clear();
    num << value;
    out.append(MString(num.str().c_str()));
}

}  // namespace

void* MaroQueryLidarScanCommand::creator() { return new MaroQueryLidarScanCommand(); }

MSyntax MaroQueryLidarScanCommand::newSyntax() {
    MSyntax syntax;
    syntax.setObjectType(MSyntax::kSelectionList, 1, 1);
    return syntax;
}

MStatus MaroQueryLidarScanCommand::doIt(const MArgList& args) {
    maro::ScopedCommandContext ctxMarker("MaroQueryLidarScanCommand");
    try {
        MStatus status;
        MArgDatabase argData(syntax(), args, &status);
        if (!status) return status;

        MSelectionList selection;
        argData.getObjects(selection);
        if (selection.length() != 1) {
            maro::BoadMaro::error(
                "MaroQueryLidarScanCommand.WrongArgCount",
                "Maro: maroQueryLidarScan needs exactly one argument: <lidarNode>.",
                maro::onfix::capture("", "", ""));
            return MS::kFailure;
        }

        MObject lidarObj;
        selection.getDependNode(0, lidarObj);
        MFnDependencyNode lidarFn(lidarObj);
        if (lidarFn.typeId() != MaroLidarNode::id) {
            maro::BoadMaro::error(
                "MaroQueryLidarScanCommand.NotMaroLidarNode",
                MString("Maro: '") + lidarFn.name() + "' is not a maroLidar node.",
                maro::onfix::capture(lidarFn.typeName(), "", lidarFn.name()));
            return MS::kFailure;
        }

        maro::lidar::ScanEngine engine;
        std::vector<Vec3> points;
        LidarGeometry geometry;
        const LidarScanResult result =
            scanLidarNode(lidarObj, engine, currentSceneUnit(), points, &geometry);

        std::ostringstream num;
        num.imbue(std::locale::classic());
        num << std::setprecision(std::numeric_limits<double>::max_digits10);

        MStringArray out;
        out.append(lidarScanResultName(result));

        if (result == LidarScanResult::kInvalidConfig) {
            for (int i = 0; i < 22; ++i) appendDouble(out, num, 0.0);
            out.append("0");
        } else {
            appendDouble(out, num, geometry.rangeMinMaya);
            appendDouble(out, num, geometry.rangeMaxMaya);
            appendDouble(out, num, geometry.verticalMinAngle);
            appendDouble(out, num, geometry.verticalMaxAngle);
            appendDouble(out, num, geometry.horizontalMinAngle);
            appendDouble(out, num, geometry.horizontalMaxAngle);
            for (unsigned int r = 0; r < 4; ++r) {
                for (unsigned int c = 0; c < 4; ++c) {
                    appendDouble(out, num, geometry.effectiveWorldMatrix(r, c));
                }
            }
            out.append(MString() + static_cast<int>(points.size()));
            for (const Vec3& p : points) {
                appendDouble(out, num, p.x);
                appendDouble(out, num, p.y);
                appendDouble(out, num, p.z);
            }
        }

        setResult(out);
        return MS::kSuccess;
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroQueryLidarScanCommand.doIt.Exception",
                              MString("Maro: maroQueryLidarScan failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroQueryLidarScanCommand.doIt.UnknownException",
                              "Maro: maroQueryLidarScan failed with unknown error.");
        return MS::kFailure;
    }
}
```

- [ ] **Step 6: Register the command in `MaroPluginMain.cpp`**

Add, right after the existing `maroSnapshotLidarScan` registration block:

```cpp
    status = plugin.registerCommand("maroQueryLidarScan",
                                    maro::MaroQueryLidarScanCommand::creator,
                                    maro::MaroQueryLidarScanCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroQueryLidarScan");
        return status;
    }
```

Add the matching deregister line in the shutdown block, next to `plugin.deregisterCommand("maroSnapshotLidarScan");` (same file, the reverse-order deregistration section):

```cpp
        plugin.deregisterCommand("maroQueryLidarScan");
```

- [ ] **Step 7: Add `parseLidarScanQuery` to `python/maroTechDiag.py`**

Add near the top, alongside the other C++-contract constants (`AXIS_FIELDS`/`CAPABILITY_FIELDS`/`LIDAR_MAX_RAYS_PER_SCAN`):

```python
# maroQueryLidarScan()의 계약. 계획 문서 2026-09-04-maro-lidar-sensor-
# validation.md의 Task 2 표와 반드시 일치해야 한다.
LIDAR_QUERY_HEADER_FIELDS = 24
```

Add the parser function (place it near `_collectLidarRows`):

```python
def parseLidarScanQuery(flat):
    """maroQueryLidarScan()의 평탄한 문자열 배열을 딕셔너리로 되돌린다.
    hitPoints는 (x,y,z) 튜플 목록. status가 "kInvalidConfig"면 matrix/range/
    FOV 필드는 전부 0이고 hitPoints는 빈 목록이다 -- 호출부는 이 경우 그
    필드들을 쓰면 안 된다(설계 스펙 §8)."""
    if len(flat) < LIDAR_QUERY_HEADER_FIELDS:
        raise ValueError(
            "lidar scan query array length {} is shorter than the header ({})".format(
                len(flat), LIDAR_QUERY_HEADER_FIELDS))
    matrixValues = [float(v) for v in flat[7:23]]
    hitCount = int(flat[23])
    hitTail = flat[LIDAR_QUERY_HEADER_FIELDS:]
    if len(hitTail) != hitCount * 3:
        raise ValueError(
            "lidar scan query hit-point tail length {} does not match "
            "hitCount*3 ({})".format(len(hitTail), hitCount * 3))
    hitPoints = [
        (float(hitTail[i]), float(hitTail[i + 1]), float(hitTail[i + 2]))
        for i in range(0, len(hitTail), 3)
    ]
    return {
        "status": flat[0],
        "rangeMinMaya": float(flat[1]),
        "rangeMaxMaya": float(flat[2]),
        "verticalMinAngle": float(flat[3]),
        "verticalMaxAngle": float(flat[4]),
        "horizontalMinAngle": float(flat[5]),
        "horizontalMaxAngle": float(flat[6]),
        "effectiveWorldMatrix": om2.MMatrix(matrixValues),
        "hitPoints": hitPoints,
    }
```

`om2.MMatrix(...)` is pure math (no live Maya document needed), matching this file's existing precedent that "pure function" means no `cmds`/scene access, not "no `maya.api.OpenMaya`" (see `_readCurrentValue`'s `om2.MAngle`/`om2.MDistance` usage in this same file).

- [ ] **Step 8: Run the test to verify it passes**

```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure -R maya_lidar_scan_query
```
Expected: all `OK` lines print, exit 0. If the matrix cross-check fails, do not weaken the tolerance — it means the C++ serialization order (row-major, `matrix(r,c)` at `7 + r*4 + c`) and Python's `om2.MMatrix(flatList)` reconstruction disagree on element order; fix whichever side is wrong, don't paper over it.

- [ ] **Step 9: Run the full suite**

```powershell
ctest --test-dir out/build -C Release --output-on-failure
```

- [ ] **Step 10: Commit**

```bash
git add src/maro_plugin/MaroLidarScan.h src/maro_plugin/MaroLidarScan.cpp src/maro_plugin/MaroLidarCommands.h src/maro_plugin/MaroLidarCommands.cpp src/maro_plugin/MaroPluginMain.cpp python/maroTechDiag.py tests/maya/test_lidar_scan_query.py tests/CMakeLists.txt
git commit -m "feat(lidar): add scene-safe maroQueryLidarScan query command"
```

---

### Task 3: Tech Diag's 4 new dynamic LiDAR checks

**Files:**
- Modify: `python/maroTechDiag.py`
- Modify: `tests/maya/test_tech_diag.py`

**Interfaces:**
- Consumes: Task 2's `cmds.maroQueryLidarScan`, `parseLidarScanQuery`, and the existing `_collectLidarRows()` (already returns `lidarFullPath`, `enabled`, `targetMeshCount`, etc.).
- Produces:
  - `checkLidarZeroHits(lidarRows, scanByLidar) -> list[Finding]`
  - `checkLidarOutOfRange(lidarRows, scanByLidar, targetMeshBoxesByLidar) -> list[Finding]`
  - `checkLidarOutOfFov(lidarRows, scanByLidar, targetMeshBoxesByLidar) -> list[Finding]`
  - `checkLidarHitBoundsConsistency(lidarRows, scanByLidar) -> list[Finding]`
  - All four are pure (no `cmds`, only `om2`/`math`). `scanByLidar` is `dict[lidarFullPath, parseLidarScanQuery()'s dict]`. `targetMeshBoxesByLidar` is `dict[lidarFullPath, dict[meshPath, (xmin,ymin,zmin,xmax,ymax,zmax)]]`.
  - `_collectLidarScans(lidarRows) -> dict` and `_collectLidarTargetMeshBoxes(lidarRows) -> dict` (Maya-calling collectors, private per this file's `_`-prefix convention).

- [ ] **Step 1: Write the failing pure-function tests**

Append to `tests/maya/test_tech_diag.py` (these run in the pure-function part of the file, before the Maya-standalone bootstrap Task 3 of the original Tech Diag plan inserted — place them alongside the other pure-function tests, i.e. before that bootstrap block):

```python
# --- checkLidarZeroHits ---
lidarRowsZero = [{"lidarFullPath": "|lidarA", "enabled": True, "verticalSamples": 1,
                  "horizontalSamples": 1, "targetMeshCount": 1}]
scanEmpty = {"|lidarA": {"status": "kOk", "hitPoints": []}}
findings = diag.checkLidarZeroHits(lidarRowsZero, scanEmpty)
assert len(findings) == 1 and findings[0]["category"] == "lidarZeroHits", findings
scanNonEmpty = {"|lidarA": {"status": "kOk", "hitPoints": [(0.0, 0.0, 0.0)]}}
assert diag.checkLidarZeroHits(lidarRowsZero, scanNonEmpty) == []
scanFailed = {"|lidarA": {"status": "kMeshExtractFailed", "hitPoints": []}}
assert diag.checkLidarZeroHits(lidarRowsZero, scanFailed) == [], (
    "a non-kOk status must not also be flagged as a zero-hit finding")
lidarRowsNoMesh = [{"lidarFullPath": "|lidarB", "enabled": True, "verticalSamples": 1,
                    "horizontalSamples": 1, "targetMeshCount": 0}]
assert diag.checkLidarZeroHits(lidarRowsNoMesh, {"|lidarB": {"status": "kOk", "hitPoints": []}}) == []
print("checkLidarZeroHits OK")

# --- checkLidarOutOfRange ---
import maya.api.OpenMaya as om2Test
scanInRange = {"|lidarA": {"status": "kOk", "rangeMaxMaya": 100.0,
                           "effectiveWorldMatrix": om2Test.MMatrix()}}
boxesFar = {"|lidarA": {"|meshFar": (200.0, 0.0, 0.0, 210.0, 10.0, 10.0)}}
findings = diag.checkLidarOutOfRange(lidarRowsZero, scanInRange, boxesFar)
assert len(findings) == 1 and findings[0]["category"] == "lidarOutOfRange", findings
boxesNear = {"|lidarA": {"|meshNear": (10.0, 0.0, 0.0, 20.0, 10.0, 10.0)}}
assert diag.checkLidarOutOfRange(lidarRowsZero, scanInRange, boxesNear) == []
print("checkLidarOutOfRange OK")

# --- checkLidarOutOfFov ---
scanNarrowFov = {"|lidarA": {"status": "kOk",
                             "verticalMinAngle": -0.1, "verticalMaxAngle": 0.1,
                             "horizontalMinAngle": -0.1, "horizontalMaxAngle": 0.1,
                             "effectiveWorldMatrix": om2Test.MMatrix()}}
# 로컬 +Z 방향(수직=0, 수평=0)이면 FOV 안. 로컬 +X 방향은 수평 ~pi/2로 밖.
boxesInFov = {"|lidarA": {"|meshInFov": (-1.0, -1.0, 9.0, 1.0, 1.0, 11.0)}}
assert diag.checkLidarOutOfFov(lidarRowsZero, scanNarrowFov, boxesInFov) == []
boxesOutOfFov = {"|lidarA": {"|meshOutOfFov": (9.0, -1.0, -1.0, 11.0, 1.0, 1.0)}}
findings = diag.checkLidarOutOfFov(lidarRowsZero, scanNarrowFov, boxesOutOfFov)
assert len(findings) == 1 and findings[0]["category"] == "lidarOutOfFov", findings
print("checkLidarOutOfFov OK")

# --- checkLidarHitBoundsConsistency ---
scanValidHit = {"|lidarA": {"status": "kOk", "rangeMinMaya": 0.0, "rangeMaxMaya": 100.0,
                            "effectiveWorldMatrix": om2Test.MMatrix(),
                            "hitPoints": [(50.0, 0.0, 0.0)]}}
assert diag.checkLidarHitBoundsConsistency(lidarRowsZero, scanValidHit) == []
scanBadHit = {"|lidarA": {"status": "kOk", "rangeMinMaya": 0.0, "rangeMaxMaya": 100.0,
                          "effectiveWorldMatrix": om2Test.MMatrix(),
                          "hitPoints": [(500.0, 0.0, 0.0)]}}
findings = diag.checkLidarHitBoundsConsistency(lidarRowsZero, scanBadHit)
assert len(findings) == 1 and findings[0]["category"] == "lidarHitOutOfBounds", findings
print("checkLidarHitBoundsConsistency OK")
```

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_tech_diag.py
```
Expected: FAIL — the four functions don't exist yet.

- [ ] **Step 2: Add `import math` and the four check functions to `python/maroTechDiag.py`**

Add `import math` alongside the existing `import itertools` at the top.

Add near the other `checkLidar*` functions:

```python
def checkLidarZeroHits(lidarRows, scanByLidar):
    """enabled + 타겟 메쉬가 연결된 LiDAR가 kOk 스캔에서 히트를 하나도
    못 냈으면 경고. 다른 상태(kNoTargetMesh/kMeshExtractFailed/
    kInvalidConfig/kRayCountExceeded)는 원인이 다른 방식으로 이미 드러나
    있으므로 대상이 아니다."""
    findings = []
    for row in lidarRows:
        if not row["enabled"] or row["targetMeshCount"] == 0:
            continue
        scan = scanByLidar.get(row["lidarFullPath"])
        if scan is None or scan["status"] != "kOk":
            continue
        if len(scan["hitPoints"]) == 0:
            findings.append({
                "category": "lidarZeroHits",
                "severity": "warning",
                "summary": "{}: target mesh(es) connected but the scan detected "
                           "nothing".format(row["lidarFullPath"]),
                "axis": None,
                "remedy": None,
            })
    return findings


# 실제 캐스팅이 있었는지와 무관하게(kMeshExtractFailed/kRayCountExceeded도
# 유효 지오메트리를 준다, 설계 스펙 §8) 범위/FOV 정적 검사는 적용 가능하다.
_LIDAR_GEOMETRY_VALID_STATUSES = ("kOk", "kMeshExtractFailed", "kRayCountExceeded")


def _nearestDistanceToBox(point, box):
    """점에서 AABB(xmin,ymin,zmin,xmax,ymax,zmax)까지의 최단 거리(박스
    안이면 0). 표준 클램프 공식."""
    xmin, ymin, zmin, xmax, ymax, zmax = box
    cx = min(max(point[0], xmin), xmax)
    cy = min(max(point[1], ymin), ymax)
    cz = min(max(point[2], zmin), zmax)
    dx, dy, dz = point[0] - cx, point[1] - cy, point[2] - cz
    return (dx * dx + dy * dy + dz * dz) ** 0.5


def checkLidarOutOfRange(lidarRows, scanByLidar, targetMeshBoxesByLidar):
    """타겟 메쉬 AABB의 LiDAR 유효 원점까지 최근접 거리가 rangeMax를
    넘으면 경고 -- 실제 스캔 여부와 무관한 순수 기하 판정."""
    findings = []
    for row in lidarRows:
        if not row["enabled"]:
            continue
        scan = scanByLidar.get(row["lidarFullPath"])
        if scan is None or scan["status"] not in _LIDAR_GEOMETRY_VALID_STATUSES:
            continue
        origin = om2.MPoint(0, 0, 0) * scan["effectiveWorldMatrix"]
        originTuple = (origin.x, origin.y, origin.z)
        for mesh, box in targetMeshBoxesByLidar.get(row["lidarFullPath"], {}).items():
            if _nearestDistanceToBox(originTuple, box) > scan["rangeMaxMaya"]:
                findings.append({
                    "category": "lidarOutOfRange",
                    "severity": "warning",
                    "summary": "{}: target mesh {} is beyond rangeMax and can never "
                               "be detected".format(row["lidarFullPath"], mesh),
                    "axis": None,
                    "remedy": None,
                })
    return findings


def _localAngles(worldPoint, effectiveWorldMatrix):
    """worldPoint를 LiDAR의 로컬(센서) 프레임으로 옮긴 뒤 RayPattern.cpp와
    같은 각도 규약(vertical=asin(y/|.|), horizontal=atan2(x,z))으로 각도를
    구한다."""
    local = om2.MPoint(worldPoint[0], worldPoint[1], worldPoint[2]) * effectiveWorldMatrix.inverse()
    length = math.sqrt(local.x * local.x + local.y * local.y + local.z * local.z)
    if length < 1e-9:
        return 0.0, 0.0
    vertical = math.asin(max(-1.0, min(1.0, local.y / length)))
    horizontal = math.atan2(local.x, local.z)
    return vertical, horizontal


def checkLidarOutOfFov(lidarRows, scanByLidar, targetMeshBoxesByLidar):
    """타겟 메쉬 AABB 중심이 설정된 수직/수평 FOV 밖이면 경고. 박스 중심
    하나만 보는 근사(설계 스펙 §10의 알려진 한계)."""
    findings = []
    for row in lidarRows:
        if not row["enabled"]:
            continue
        scan = scanByLidar.get(row["lidarFullPath"])
        if scan is None or scan["status"] not in _LIDAR_GEOMETRY_VALID_STATUSES:
            continue
        for mesh, box in targetMeshBoxesByLidar.get(row["lidarFullPath"], {}).items():
            center = ((box[0] + box[3]) / 2.0, (box[1] + box[4]) / 2.0, (box[2] + box[5]) / 2.0)
            vertical, horizontal = _localAngles(center, scan["effectiveWorldMatrix"])
            outOfVertical = not (scan["verticalMinAngle"] <= vertical <= scan["verticalMaxAngle"])
            outOfHorizontal = not (
                scan["horizontalMinAngle"] <= horizontal <= scan["horizontalMaxAngle"])
            if outOfVertical or outOfHorizontal:
                findings.append({
                    "category": "lidarOutOfFov",
                    "severity": "warning",
                    "summary": "{}: target mesh {} is outside the configured "
                               "FOV".format(row["lidarFullPath"], mesh),
                    "axis": None,
                    "remedy": None,
                })
    return findings


def checkLidarHitBoundsConsistency(lidarRows, scanByLidar):
    """kOk 스캔의 히트점이 전부 [rangeMin, rangeMax] 안에 있는지 자체
    검증(방어적 회귀 검사 -- 정상 상황에선 항상 통과해야 한다, ScanEngine::
    castRay의 tnear/tfar 클리핑이 이미 이걸 보장한다)."""
    findings = []
    for row in lidarRows:
        scan = scanByLidar.get(row["lidarFullPath"])
        if scan is None or scan["status"] != "kOk":
            continue
        origin = om2.MPoint(0, 0, 0) * scan["effectiveWorldMatrix"]
        for point in scan["hitPoints"]:
            dx, dy, dz = point[0] - origin.x, point[1] - origin.y, point[2] - origin.z
            distance = (dx * dx + dy * dy + dz * dz) ** 0.5
            if not (scan["rangeMinMaya"] - 1e-6 <= distance <= scan["rangeMaxMaya"] + 1e-6):
                findings.append({
                    "category": "lidarHitOutOfBounds",
                    "severity": "warning",
                    "summary": "{}: a scan hit point is outside [rangeMin, rangeMax] "
                               "(possible regression)".format(row["lidarFullPath"]),
                    "axis": None,
                    "remedy": None,
                })
                break  # 축당 한 번만 보고 -- 점마다 반복 경고는 노이즈
    return findings
```

- [ ] **Step 3: Run the pure-function tests to verify they pass**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_tech_diag.py
```
Expected: the four new `OK` lines print alongside all prior ones.

- [ ] **Step 4: Wire the checks into `_runMayaSideChecks()` and write the end-to-end test**

Add the two collector helpers to `python/maroTechDiag.py`, right before `_runMayaSideChecks`:

```python
def _collectLidarScans(lidarRows):
    """각 maroLidar를 maroQueryLidarScan으로 조회해 parseLidarScanQuery()
    결과를 lidarFullPath별로 모은다. 씬을 바꾸지 않는다."""
    return {row["lidarFullPath"]: parseLidarScanQuery(cmds.maroQueryLidarScan(row["lidarFullPath"]))
            for row in lidarRows}


def _collectLidarTargetMeshBoxes(lidarRows):
    """각 maroLidar가 연결한 타겟 메쉬들의 월드 AABB를 모은다."""
    boxesByLidar = {}
    for row in lidarRows:
        meshes = cmds.listConnections(
            row["lidarFullPath"] + ".targetMeshes", source=True, destination=False) or []
        boxesByLidar[row["lidarFullPath"]] = {
            mesh: tuple(cmds.exactWorldBoundingBox(mesh)) for mesh in meshes
        }
    return boxesByLidar
```

In `_runMayaSideChecks()`, change:

```python
    lidarRows = _collectLidarRows()
    findings += checkLidarTargetMeshes(lidarRows)
    findings += checkLidarRayCount(lidarRows)
    return findings
```

to:

```python
    lidarRows = _collectLidarRows()
    findings += checkLidarTargetMeshes(lidarRows)
    findings += checkLidarRayCount(lidarRows)
    scanByLidar = _collectLidarScans(lidarRows)
    targetMeshBoxesByLidar = _collectLidarTargetMeshBoxes(lidarRows)
    findings += checkLidarZeroHits(lidarRows, scanByLidar)
    findings += checkLidarOutOfRange(lidarRows, scanByLidar, targetMeshBoxesByLidar)
    findings += checkLidarOutOfFov(lidarRows, scanByLidar, targetMeshBoxesByLidar)
    findings += checkLidarHitBoundsConsistency(lidarRows, scanByLidar)
    return findings
```

Append an end-to-end test to `tests/maya/test_tech_diag.py` (in the Maya-standalone section, after Task 3 of the original Tech Diag plan's remedy tests):

```python
# --- end-to-end: _runMayaSideChecks() surfaces a zero-hit + out-of-range LiDAR ---
farMesh = cmds.polyPlane(name="techDiagFarMesh", width=10, height=10,
                          subdivisionsX=1, subdivisionsY=1)[0]
cmds.setAttr(farMesh + ".translateX", 100000)  # 훨씬 rangeMax 밖
lidarNode = cmds.createNode("maroLidar", name="techDiagLidar")
lidarNode = cmds.ls(lidarNode, long=True)[0]
cmds.setAttr(lidarNode + ".verticalSamples", 1)
cmds.setAttr(lidarNode + ".horizontalSamples", 1)
cmds.setAttr(lidarNode + ".rangeMax", 30.0)  # 미터, 훨씬 작음
cmds.connectAttr(farMesh + ".message", lidarNode + ".targetMeshes[0]")

allFindings = diag._runMayaSideChecks()
categories = {f["category"] for f in allFindings}
assert "lidarZeroHits" in categories, categories
assert "lidarOutOfRange" in categories, categories
print("_runMayaSideChecks surfaces lidarZeroHits + lidarOutOfRange OK")
```

- [ ] **Step 5: Run tests and the full suite**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_tech_diag.py
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure
```

- [ ] **Step 6: Commit**

```bash
git add python/maroTechDiag.py tests/maya/test_tech_diag.py
git commit -m "feat(tech-diag): add zero-hit, out-of-range, out-of-FOV, and hit-bounds LiDAR checks"
```

---

### Task 4: `CollisionEngine` + `maroCheckMeshCollision`

**Files:**
- Create: `src/maro_lidar/include/maro_lidar/CollisionEngine.h`
- Create: `src/maro_lidar/src/CollisionEngine.cpp`
- Modify: `src/maro_lidar/CMakeLists.txt`
- Create: `src/maro_plugin/MaroCollisionCommands.h`
- Create: `src/maro_plugin/MaroCollisionCommands.cpp`
- Modify: `src/maro_plugin/CMakeLists.txt`
- Modify: `src/maro_plugin/MaroPluginMain.cpp`
- Create: `tests/maya/test_mesh_collision.py`
- Modify: `tests/CMakeLists.txt`

**Interfaces:**
- Consumes: Task 1's public `extractMeshBuffers()`.
- Produces: Maya command `maroCheckMeshCollision <meshA> <meshB>` returning `"true"`, `"false"`, or `"unknown"` (via `setResult(MString)`).

- [ ] **Step 1: Verify `rtcCollide`'s preconditions before writing the wrapper**

Read `build/vcpkg_installed/x64-windows/include/embree4/rtcore_scene.h`'s comments around `rtcCollide`/`RTCCollision`/`RTCCollideFunc` (already confirmed present at lines 338-343 of that file). The header carries no explicit precondition comment about whether both scenes must share one `RTCDevice` — this is the "implementation risk" the design spec flagged. Resolve it empirically in Step 2's test rather than assuming: if two scenes built from the *same* device don't produce the expected collision callback, that is itself useful information — do not silently switch to two devices without first observing a real failure with one.

- [ ] **Step 2: Write `CollisionEngine.h`**

```cpp
#pragma once

#include <cstdint>
#include <vector>

typedef struct RTCDeviceTy* RTCDevice;
typedef struct RTCSceneTy* RTCScene;

namespace maro::lidar {

// 두 폴리곤 메쉬가 실제로 교차하는지 Embree의 rtcCollide(씬-대-씬 폴리곤
// 단위 충돌 검사)로 판정한다. ScanEngine과 달리 레이캐스팅이 아니라 두
// 지오메트리 자체의 삼각형 쌍 교차를 직접 찾는다.
class CollisionEngine {
public:
    CollisionEngine();
    ~CollisionEngine();

    CollisionEngine(const CollisionEngine&) = delete;
    CollisionEngine& operator=(const CollisionEngine&) = delete;

    // 두 지오메트리를 각각 별도 RTCScene(같은 RTCDevice 위)으로 올린다.
    // 실패(빈 입력, 인덱스 범위 초과, Embree 오류)하면 false.
    bool setMeshes(const std::vector<float>& verticesA, const std::vector<std::uint32_t>& indicesA,
                   const std::vector<float>& verticesB, const std::vector<std::uint32_t>& indicesB);

    // rtcCollide를 호출해 실제 교차 삼각형 쌍이 하나라도 있으면 true.
    // setMeshes()가 실패했거나 아직 안 불렸으면 false.
    bool hasCollision() const;

private:
    RTCDevice device_ = nullptr;
    RTCScene sceneA_ = nullptr;
    RTCScene sceneB_ = nullptr;
    bool meshesSet_ = false;
};

}  // namespace maro::lidar
```

- [ ] **Step 3: Write `CollisionEngine.cpp`**

```cpp
#include "maro_lidar/CollisionEngine.h"

#include <embree4/rtcore.h>

namespace maro::lidar {

namespace {

// 하나의 RTCScene에 삼각형 지오메트리 하나를 올린다. ScanEngine::setMesh()와
// 같은 안전장치(인덱스 범위 검사, 새 버퍼 소유)를 따른다.
RTCScene buildScene(RTCDevice device, const std::vector<float>& vertices,
                     const std::vector<std::uint32_t>& indices) {
    if (vertices.empty() || indices.empty()) return nullptr;
    if (vertices.size() % 3 != 0 || indices.size() % 3 != 0) return nullptr;
    const std::size_t vertexCount = vertices.size() / 3;
    for (const std::uint32_t index : indices) {
        if (static_cast<std::size_t>(index) >= vertexCount) return nullptr;
    }

    RTCScene scene = rtcNewScene(device);
    if (scene == nullptr) return nullptr;

    RTCGeometry geom = rtcNewGeometry(device, RTC_GEOMETRY_TYPE_TRIANGLE);
    if (geom == nullptr) {
        rtcReleaseScene(scene);
        return nullptr;
    }

    float* vertexBuffer = static_cast<float*>(rtcSetNewGeometryBuffer(
        geom, RTC_BUFFER_TYPE_VERTEX, 0, RTC_FORMAT_FLOAT3, 3 * sizeof(float), vertexCount));
    if (vertexBuffer == nullptr) {
        rtcReleaseGeometry(geom);
        rtcReleaseScene(scene);
        return nullptr;
    }
    for (std::size_t i = 0; i < vertices.size(); ++i) vertexBuffer[i] = vertices[i];

    const std::size_t triangleCount = indices.size() / 3;
    unsigned int* indexBuffer = static_cast<unsigned int*>(rtcSetNewGeometryBuffer(
        geom, RTC_BUFFER_TYPE_INDEX, 0, RTC_FORMAT_UINT3, 3 * sizeof(unsigned int), triangleCount));
    if (indexBuffer == nullptr) {
        rtcReleaseGeometry(geom);
        rtcReleaseScene(scene);
        return nullptr;
    }
    for (std::size_t i = 0; i < indices.size(); ++i) {
        indexBuffer[i] = static_cast<unsigned int>(indices[i]);
    }

    rtcCommitGeometry(geom);
    rtcAttachGeometry(scene, geom);
    rtcReleaseGeometry(geom);  // scene이 자체적으로 참조를 갖는다.
    rtcCommitScene(scene);
    return scene;
}

void collideCallback(void* userPtr, RTCCollision* collisions, unsigned int numCollisions) {
    if (numCollisions > 0) *static_cast<bool*>(userPtr) = true;
}

}  // namespace

CollisionEngine::CollisionEngine() {
    device_ = rtcNewDevice(nullptr);
}

CollisionEngine::~CollisionEngine() {
    if (sceneA_ != nullptr) rtcReleaseScene(sceneA_);
    if (sceneB_ != nullptr) rtcReleaseScene(sceneB_);
    if (device_ != nullptr) rtcReleaseDevice(device_);
}

bool CollisionEngine::setMeshes(const std::vector<float>& verticesA,
                                 const std::vector<std::uint32_t>& indicesA,
                                 const std::vector<float>& verticesB,
                                 const std::vector<std::uint32_t>& indicesB) {
    meshesSet_ = false;
    if (device_ == nullptr) return false;

    RTCScene newSceneA = buildScene(device_, verticesA, indicesA);
    if (newSceneA == nullptr) return false;
    RTCScene newSceneB = buildScene(device_, verticesB, indicesB);
    if (newSceneB == nullptr) {
        rtcReleaseScene(newSceneA);
        return false;
    }

    if (sceneA_ != nullptr) rtcReleaseScene(sceneA_);
    if (sceneB_ != nullptr) rtcReleaseScene(sceneB_);
    sceneA_ = newSceneA;
    sceneB_ = newSceneB;
    meshesSet_ = true;
    return true;
}

bool CollisionEngine::hasCollision() const {
    if (!meshesSet_ || sceneA_ == nullptr || sceneB_ == nullptr) return false;
    bool found = false;
    rtcCollide(sceneA_, sceneB_, collideCallback, &found);
    return found;
}

}  // namespace maro::lidar
```

- [ ] **Step 4: Add `CollisionEngine.cpp` to `src/maro_lidar/CMakeLists.txt`**

In the `add_library(maro_lidar STATIC ...)` block, add `src/CollisionEngine.cpp` alongside the existing `src/ScanEngine.cpp` etc.

- [ ] **Step 5: Write the failing command test**

Create `tests/maya/test_mesh_collision.py`:

```python
"""maroCheckMeshCollision의 계약을 고정한다: 실제로 겹치는 폴리곤 쌍은
true, AABB만 겹치고 실제로는 안 닿는 쌍은 false, 폴리곤이 아닌 지오메트리는
unknown."""
import os

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

# 확실히 겹침: 같은 자리에 겹친 두 큐브.
cubeA = cmds.polyCube(name="collideCubeA")[0]
cubeB = cmds.polyCube(name="collideCubeB")[0]
assert cmds.maroCheckMeshCollision(cubeA, cubeB) == "true", "overlapping cubes must collide"
print("overlapping cubes -> true OK")

# 완전히 분리됨.
cmds.setAttr(cubeB + ".translate", 100, 100, 100, type="double3")
assert cmds.maroCheckMeshCollision(cubeA, cubeB) == "false", "separated cubes must not collide"
print("separated cubes -> false OK")

# AABB는 겹치지만 실제 폴리곤 표면은 안 닿는 배치: cubeB를 45도 돌려 대각선
# 코너만 cubeA의 바운딩박스 안에 들어오게 하되, 실제 큐브 면끼리는 안
# 맞닿게 한다. 이 배치가 의도한 조건(AABB 겹침 O, 실제 폴리곤 접촉 X)을
# 실제로 만드는지는 cmds.exactWorldBoundingBox로 먼저 확인하고, 필요하면
# 좌표를 조정한다 -- 손으로 가정하지 않고 이 스텝에서 직접 확인한다.
cmds.setAttr(cubeB + ".translate", 1.9, 1.9, 0, type="double3")
cmds.setAttr(cubeB + ".rotateY", 45)
boxA = cmds.exactWorldBoundingBox(cubeA)
boxB = cmds.exactWorldBoundingBox(cubeB)
aabbOverlap = (boxA[0] < boxB[3] and boxB[0] < boxA[3] and
               boxA[1] < boxB[4] and boxB[1] < boxA[4] and
               boxA[2] < boxB[5] and boxB[2] < boxA[5])
assert aabbOverlap, (
    "test setup error: expected these two cubes' AABBs to overlap, got "
    "{} and {} -- adjust the translate/rotate values above".format(boxA, boxB))
result = cmds.maroCheckMeshCollision(cubeA, cubeB)
assert result == "false", (
    "expected AABB-only overlap (no real polygon contact) to report false, "
    "got {} for boxes {} / {} -- if the geometry above actually does touch, "
    "adjust the translate value further apart".format(result, boxA, boxB))
print("AABB-only overlap -> false OK")

# 폴리곤이 아닌 지오메트리: unknown.
locatorTransform = cmds.spaceLocator(name="notAMeshLocator")[0]
assert cmds.maroCheckMeshCollision(cubeA, locatorTransform) == "unknown", (
    "a non-mesh argument must report unknown, not crash or silently say false")
print("non-mesh argument -> unknown OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
```

Register it: add `mesh_collision` to `tests/CMakeLists.txt`'s `foreach(maya_test ...)` list.

```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure -R maya_mesh_collision
```
Expected: FAIL — `maroCheckMeshCollision` doesn't exist yet.

- [ ] **Step 6: Write `MaroCollisionCommands.h`**

```cpp
#pragma once

#include <maya/MPxCommand.h>
#include <maya/MSyntax.h>

namespace maro {

// <meshA> <meshB>: 두 메쉬가 실제로 폴리곤 단위로 교차하는지 판정한다
// (Embree rtcCollide 기반, maro_lidar::CollisionEngine 참고). 쿼리 전용,
// 씬을 바꾸지 않는다. setResult로 "true"/"false"/"unknown" 중 하나를
// 돌려준다 -- "unknown"은 둘 중 하나라도 폴리곤 메쉬가 아니라 추출에
// 실패한 경우(호출부인 Python이 이 경우 AABB 결과로 폴백한다, 설계 스펙
// §6.4).
class MaroCheckMeshCollisionCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
    bool isUndoable() const override { return false; }
};

}  // namespace maro
```

- [ ] **Step 7: Write `MaroCollisionCommands.cpp`**

```cpp
#include "MaroCollisionCommands.h"

#include <cstdint>
#include <vector>

#include <maya/MArgDatabase.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MSelectionList.h>

#include "maro_lidar/CollisionEngine.h"

#include "MaroDiag.h"
#include "MaroLidarScan.h"  // extractMeshBuffers (Task 1이 공개로 승격)

namespace maro {

void* MaroCheckMeshCollisionCommand::creator() { return new MaroCheckMeshCollisionCommand(); }

MSyntax MaroCheckMeshCollisionCommand::newSyntax() {
    MSyntax syntax;
    syntax.setObjectType(MSyntax::kSelectionList, 2, 2);
    return syntax;
}

MStatus MaroCheckMeshCollisionCommand::doIt(const MArgList& args) {
    maro::ScopedCommandContext ctxMarker("MaroCheckMeshCollisionCommand");
    try {
        MStatus status;
        MArgDatabase argData(syntax(), args, &status);
        if (!status) return status;

        MSelectionList selection;
        argData.getObjects(selection);
        if (selection.length() != 2) {
            maro::BoadMaro::error(
                "MaroCheckMeshCollisionCommand.WrongArgCount",
                "Maro: maroCheckMeshCollision needs exactly two arguments: <meshA> <meshB>.",
                maro::onfix::capture("", "", ""));
            return MS::kFailure;
        }

        MObject meshA, meshB;
        selection.getDependNode(0, meshA);
        selection.getDependNode(1, meshB);

        std::vector<float> verticesA, verticesB;
        std::vector<std::uint32_t> indicesA, indicesB;
        if (!extractMeshBuffers(meshA, verticesA, indicesA) ||
            !extractMeshBuffers(meshB, verticesB, indicesB)) {
            setResult(MString("unknown"));
            return MS::kSuccess;
        }

        maro::lidar::CollisionEngine engine;
        if (!engine.setMeshes(verticesA, indicesA, verticesB, indicesB)) {
            setResult(MString("unknown"));
            return MS::kSuccess;
        }

        setResult(MString(engine.hasCollision() ? "true" : "false"));
        return MS::kSuccess;
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroCheckMeshCollisionCommand.doIt.Exception",
                              MString("Maro: maroCheckMeshCollision failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroCheckMeshCollisionCommand.doIt.UnknownException",
                              "Maro: maroCheckMeshCollision failed with unknown error.");
        return MS::kFailure;
    }
}

}  // namespace maro
```

- [ ] **Step 8: Add the new files to `src/maro_plugin/CMakeLists.txt`**

Add `MaroCollisionCommands.cpp` to the plugin's source list (near the other `MaroLidar*`/`MaroAxisEditorCommands.cpp` entries).

- [ ] **Step 9: Register the command in `MaroPluginMain.cpp`**

Add `#include "MaroCollisionCommands.h"` near the top with the other command headers. Add, after the `maroQueryLidarScan` registration from Task 2:

```cpp
    status = plugin.registerCommand("maroCheckMeshCollision",
                                    maro::MaroCheckMeshCollisionCommand::creator,
                                    maro::MaroCheckMeshCollisionCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroCheckMeshCollision");
        return status;
    }
```

Add the matching deregister line: `plugin.deregisterCommand("maroCheckMeshCollision");`

- [ ] **Step 10: Build and run the test**

```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure -R maya_mesh_collision
```
Expected: all `OK` lines print. If the "AABB-only overlap" assertion trips on the setup-error message rather than the real assertion, adjust the cube translate/rotate values until the printed AABBs genuinely overlap while a visual/manual check confirms the cubes don't actually touch (or use `cmds.polyCube` at reduced scale and larger gaps — the exact numbers are less important than the geometric condition they must produce).

- [ ] **Step 11: Run the full suite**

```powershell
ctest --test-dir out/build -C Release --output-on-failure
```

- [ ] **Step 12: Commit**

```bash
git add src/maro_lidar/include/maro_lidar/CollisionEngine.h src/maro_lidar/src/CollisionEngine.cpp src/maro_lidar/CMakeLists.txt src/maro_plugin/MaroCollisionCommands.h src/maro_plugin/MaroCollisionCommands.cpp src/maro_plugin/CMakeLists.txt src/maro_plugin/MaroPluginMain.cpp tests/maya/test_mesh_collision.py tests/CMakeLists.txt
git commit -m "feat(collision): add CollisionEngine (Embree rtcCollide) + maroCheckMeshCollision command"
```

---

### Task 5: Precise-collision Tech Diag integration + manual checklist

**Files:**
- Modify: `python/maroTechDiag.py`
- Modify: `tests/maya/test_tech_diag.py`
- Modify: `docs/maro-main-ui-manual-checklist.md`

**Interfaces:**
- Consumes: Task 4's `cmds.maroCheckMeshCollision`.
- Produces: `refineMeshCollisions(candidateFindings) -> list[Finding]`, wired into `_runMayaSideChecks()` in place of the raw AABB result.

- [ ] **Step 1: Write the failing pure-ish test**

`refineMeshCollisions` calls `cmds.maroCheckMeshCollision`, so it needs a live Maya session — append this to the Maya-standalone section of `tests/maya/test_tech_diag.py` (after Task 3's remedy tests, alongside Task 3 (this plan)'s end-to-end block):

```python
# --- refineMeshCollisions: confirmed collision kept ---
overlapA = cmds.polyCube(name="refineOverlapA")[0]
overlapB = cmds.polyCube(name="refineOverlapB")[0]
candidateConfirmed = [{"category": "meshCollision", "severity": "warning",
                       "summary": "{} and {} bounding boxes overlap".format(overlapA, overlapB),
                       "axis": None, "meshes": (overlapA, overlapB), "remedy": None}]
refined = diag.refineMeshCollisions(candidateConfirmed)
assert len(refined) == 1 and refined[0]["summary"] == candidateConfirmed[0]["summary"], refined
print("refineMeshCollisions keeps a confirmed polygon collision OK")

# --- refineMeshCollisions: AABB-only overlap dropped ---
separateA = cmds.polyCube(name="refineSeparateA")[0]
separateB = cmds.polyCube(name="refineSeparateB")[0]
cmds.setAttr(separateB + ".translate", 100, 100, 100, type="double3")
candidateFalse = [{"category": "meshCollision", "severity": "warning",
                   "summary": "irrelevant", "axis": None,
                   "meshes": (separateA, separateB), "remedy": None}]
assert diag.refineMeshCollisions(candidateFalse) == [], (
    "an AABB candidate with no real polygon contact must be dropped")
print("refineMeshCollisions drops a false-positive AABB-only pair OK")

# --- refineMeshCollisions: non-mesh geometry falls back to the AABB finding ---
nonMeshLoc = cmds.spaceLocator(name="refineNonMeshLoc")[0]
candidateUnknown = [{"category": "meshCollision", "severity": "warning",
                     "summary": "{} and {} bounding boxes overlap".format(overlapA, nonMeshLoc),
                     "axis": None, "meshes": (overlapA, nonMeshLoc), "remedy": None}]
refined = diag.refineMeshCollisions(candidateUnknown)
assert len(refined) == 1 and "정밀 확인 불가" in refined[0]["summary"], refined
print("refineMeshCollisions falls back to the AABB finding for non-mesh geometry OK")
```

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_tech_diag.py
```
Expected: FAIL — `refineMeshCollisions` doesn't exist yet.

- [ ] **Step 2: Add `refineMeshCollisions` to `python/maroTechDiag.py`**

```python
def refineMeshCollisions(candidateFindings):
    """AABB 1차 필터를 통과한 충돌 후보를 maroCheckMeshCollision으로 정밀
    재검사한다(설계 스펙 §6.4). 실제 폴리곤 교차가 확인된 쌍만 남기고,
    폴리곤이 아니라 판정 불가("unknown")면 AABB 결과를 그대로 유지하되
    메시지에 표시를 덧붙인다. AABB만 겹치고 실제로는 안 닿는("false") 쌍은
    버린다."""
    refined = []
    for finding in candidateFindings:
        meshA, meshB = finding["meshes"]
        result = cmds.maroCheckMeshCollision(meshA, meshB)
        if result == "true":
            refined.append(finding)
        elif result == "unknown":
            degraded = dict(finding)
            degraded["summary"] = finding["summary"] + " (정밀 확인 불가, 바운딩박스 겹침만 확인됨)"
            refined.append(degraded)
    return refined
```

Change `_runMayaSideChecks()`'s existing line:

```python
    findings += filterAdjacentMeshCollisions(checkMeshCollisions(boxes),
                                             adjacentMeshPairs(axisRows))
```

to:

```python
    candidateCollisions = filterAdjacentMeshCollisions(checkMeshCollisions(boxes),
                                                        adjacentMeshPairs(axisRows))
    findings += refineMeshCollisions(candidateCollisions)
```

- [ ] **Step 3: Run tests and the full suite**

```powershell
& "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" tests/maya/test_tech_diag.py
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure
```

- [ ] **Step 4: Add manual checklist rows**

Read `docs/maro-main-ui-manual-checklist.md`'s existing "## 5. Tech Diag 검사" table to match its exact numbering (it currently ends at row 10 — continue from 11). Append:

```markdown
| 11 | 서로 실제로 맞닿는 메쉬 2개(정밀 충돌 확인됨)가 있는 씬에서 Maya측 검사 -> 기존과 동일하게 충돌 경고가 뜬다 | |
| 12 | 바운딩박스만 겹치고 실제 폴리곤은 안 닿는 메쉬 2개가 있는 씬에서 Maya측 검사 -> 더 이상 경고가 뜨지 않는다(v1의 오탐이 사라짐) | |
| 13 | 리밋에 근접하지 않고 타겟 메쉬가 rangeMax 밖에 있는 LiDAR가 있는 씬에서 Maya측 검사 -> "제로-히트"와 "범위 밖" 경고가 함께 뜬다 | |
| 14 | 타겟 메쉬가 설정된 FOV 밖에 있는 LiDAR가 있는 씬에서 Maya측 검사 -> "FOV 밖" 경고가 뜬다 | |
| 15 | 정상적으로 타겟을 감지 중인 LiDAR가 있는 씬에서 Maya측 검사 -> 4개 새 LiDAR 검사 모두 경고 없음 | |
```

- [ ] **Step 5: Commit**

```bash
git add python/maroTechDiag.py tests/maya/test_tech_diag.py docs/maro-main-ui-manual-checklist.md
git commit -m "feat(tech-diag): refine mesh-collision findings with precise polygon-level collision"
```

---

## Self-Review Notes

- **Spec coverage:** §3 (multi-mesh) → Task 1. §4 (query command) → Task 2. §5 (4 dynamic checks + skip matrix, including the `kRayCountExceeded` correction) → Task 3. §6 (`CollisionEngine` + 2-stage pipeline) → Tasks 4-5. §7 (test strategy) → every task's mayapy tests. §8 (error handling / skip matrix) → Task 3's `_LIDAR_GEOMETRY_VALID_STATUSES` and Task 5's `refineMeshCollisions` fallback. §9 (global constraints: query-only commands, no `setStyleSheet`, `--config Release`) → this plan's Global Constraints section, repeated in each task. §10 (known limitations: FOV-center-only, non-mesh fallback) → called out inline in Tasks 3-5's code comments, not silently dropped.
- **Type/name consistency:** `LidarScanResult` enum values (`kOk`/`kNoTargetMesh`/`kMeshExtractFailed`/`kInvalidConfig`/`kRayCountExceeded`) are used identically across Tasks 1-3 (C++ enum, command's string serialization, Python's status-string comparisons). `Finding` dict shape (`category`/`severity`/`summary`/`axis`/`remedy`, `meshes` for collision-shaped findings) matches the existing Tech Diag contract exactly — no new keys invented. `LIDAR_QUERY_HEADER_FIELDS = 24` is declared once (Task 2, Python) and its field layout table is referenced by name (not re-derived) in every later task that touches it.
- **No placeholders:** the one intentionally-open item (Step 1 of Task 4's `rtcCollide` precondition check) is phrased as "resolve empirically in Step 2's test," not left as an unresolved TODO — the task's own TDD cycle (write test, run, observe, fix) is the resolution mechanism, consistent with how this project has handled every other first-of-its-kind Embree/coordinate risk (URDF export's Euler-order verification, the point-cloud draw-override spike).
