# Maro — Maya / ROS 2 Axis Node Plugin

Maro robotizes objects modeled in Maya using Maya's own rigging and Dependency
Graph, and drives them live from ROS 2. Unlike external simulators (Gazebo,
CARLA), the robot lives entirely inside a Maya scene.

Two building blocks compose a robot:

- **Axis** (`maroAxis`) — binds to exactly one Maya object and drives its
  motion. Axes can be chained (`maroConnectAxis`) to form a hierarchy.
- **Capability nodes** — stack onto an axis's `capabilityIn` array. What the
  axis *becomes* (a plain rotating joint, a linear slider, a limited joint, a
  gear-coupled joint, a sensor, a moving sensor, ...) emerges from which
  capabilities are stacked, not from a type chosen up front. Seven types
  exist today: `maroRotation`, `maroTranslation`, `maroLimit`,
  `maroTranslationLimit`, `maroCoupling` (gear ratio / non-linear curve to
  another axis), `maroSensorDirection`, `maroSensorRange`. An axis carries at
  most one *primary drive* capability (rotation/translation/coupling —
  physically, one degree of freedom can't have two drivers at once);
  everything else layers on top of that.

Each axis has a `controlMode`: **Manual** (the user's own rigging/keyframes
drive the axis) or **ROS** (incoming ROS 2 commands drive it instead). A
background bridge (`maroStartBridge`) publishes `/joint_states` and `/tf` from
the live scene and applies inbound `/<robot>/joint_commands` to axes in ROS
mode. A LiDAR node (`maroLidar`) can additionally raycast a mesh (Embree) and
publish `sensor_msgs/PointCloud2`.

## MaroUI — the interactive editor

`maroMainWindow` opens a dockable window with two live 3D viewports side by
side (Maya's own coordinate space on the left, the same scene reprojected
into ROS coordinates on the right via `maroRosProxy`), so you can visually
confirm both spaces move identically once a rig is wired up.

Axis/capability editing itself doesn't happen inside that window — it's
reached the way you'd expect in Maya: **right-click any object in the
viewport**, and Maya's native marking menu gains a `Maro node editor` entry
(installed by chaining the engine's own `dagMenuProc`, restored on unload).
Picking it the first time on an object prompts for a display name and color,
creates a `maroAxis` bound to that object, and opens a small popup — the
**single object node editor (SONE)** — where the same
right-click-hold-drag-release marking-menu gesture applies a capability type
to the axis, Delete peels the most-recently-added one back off, and a
double-click expands a dropdown once two or more are stacked. Every axis
that's been given an editor shows up as a small grouped tile in MaroUI's
**object node editor (ONE)** panel, letting you reopen its SONE, rename/
recolor it, or delete it, without going back to the viewport.

Two more panels flank the dual viewport — MaroUI's **Tech Diag** terminals.
Pressing "검사 실행" on the Maya side re-scans the current scene for axes
sitting near their configured limit and target meshes whose bounding boxes
overlap; the ROS side re-scans for `/joint_states` publish problems (empty or
duplicate joint names, an enabled axis with no primary driver). Fixable
findings get an apply button (an undoable `setAttr`); the rest are
explanation-only, since there's no general fix for "this value is close to
its limit." Nothing runs in the background — every scan is triggered by the
button and reflects only that instant.

This is a separate concern from the plugin's crash/error-debugging
`maroDiagPanel` (below) — Tech Diag validates the *robot*, not the plugin.

## Prerequisites

- Windows, Visual Studio 2022 (MSVC), CMake >= 3.22
- Maya 2026 devkit
- ROS 2 Jazzy, built/installed for the same MSVC toolset
- vcpkg — see `vcpkg.json`. Two packages come from it:
  - **GoogleTest**, used by the transform/lidar unit tests.
  - **Embree 4**, a *runtime* dependency of the Maya plugin (the LiDAR
    raycaster links it, so `embree4.dll` is loaded into the Maya process).
    It **must** be installed without vcpkg's default `tasking-tbb` feature —
    an Embree that imports `tbb12.dll` cannot load inside Maya, because Maya
    already has its own `tbb12.dll` in the process and the Windows loader
    reuses a module by base name. The symptom is `loadPlugin` failing with a
    bare `ERROR_PROC_NOT_FOUND` and no hint at the cause. The configure step
    now checks the resolved DLL's import table and fails loudly instead
    (`src/maro_lidar/CMakeLists.txt`).

> **vcpkg resolution trap:** `vcpkg.json` in this repo pins the feature set
> but does **not** drive resolution for the usual `out/build` tree — that
> tree is configured without `CMAKE_TOOLCHAIN_FILE`, so `find_package(embree)`
> resolves against the **global classic-mode** install tree
> (`C:/src/vcpkg/installed/x64-windows`). Packages must be installed there by
> hand, e.g.:
>
> ```powershell
> vcpkg install "embree[core,filter-function,geometry-curve,geometry-grid,geometry-instance,geometry-point,geometry-quad,geometry-subdivision,geometry-triangle,geometry-user,ray-packets]:x64-windows"
> ```
>
> (that is `vcpkg.json`'s `embree` feature list, with `tasking-tbb` absent —
> keep the two in sync)
>
> Editing `vcpkg.json` alone changes nothing about what the build links.

## Configuring the build

The build needs two absolute paths, exposed as CMake cache variables. They
currently default to one developer's machine — **override both** for any
other environment:

| Cache variable | Purpose | Default |
|---|---|---|
| `DEVKIT_LOCATION` | Root of the Maya devkit (provides `cmake/pluginEntry.cmake`, Maya headers/libs) | `C:/Users/ckd30/Projects/devkitBase` |
| `ROS2_INSTALL` | ROS 2 install prefix (headers, `Lib/`, `bin/`, and the vendor `opt/*/bin` dirs) | `C:/dev/ros2_jazzy/install` |

Other useful options:

- `MARO_BUILD_PLUGIN` (default `ON`) — build the Maya plugin; needs devkit + ROS 2.
- `MARO_BUILD_TESTS` (default `ON`) — build and register the test suite.

Example configure + build from a Visual Studio "x64 Native Tools" (or
`VsDevCmd.bat`-initialized) shell:

```powershell
cmake -S . -B out/build -DDEVKIT_LOCATION=C:/path/to/devkit -DROS2_INSTALL=C:/path/to/ros2_jazzy/install
cmake --build out/build
```

## The PATH requirement (read this before your first `loadPlugin`)

The build stages every ROS 2 runtime DLL (the `libyaml`/`spdlog`/
`console_bridge` vendor DLLs, and `embree4.dll`) next to the built plugin
(`maro.mll`). That is not sufficient by itself: Maya's plugin loader does not open `.mll` files
with `LOAD_WITH_ALTERED_SEARCH_PATH`, so Windows will not automatically search
the plugin's own directory for those dependencies.

**The plugin's output directory must already be on `PATH` before Maya (or
`mayapy`) starts.** If it isn't, `loadPlugin("maro")` fails with a generic
"cannot find dependent DLL" error that gives no hint that this is the actual
cause.

Add the build output directory (e.g. `out/build/src/maro_plugin/Debug`) to
`PATH` in the environment you launch Maya from, then start Maya.

## Running the tests

Tests are registered with CTest — the C++ transform unit tests (GoogleTest)
plus a set of `mayapy`-driven scenario scripts under `tests/maya/`. The
`mayapy`-based tests set their own `PATH`/`MARO_PLUGIN_PATH` via CTest test
properties, so you don't need to do that manually for `ctest` runs.

```powershell
ctest --test-dir out/build --output-on-failure
```

Some tests start a live ROS 2 bridge and talk to a peer process
(`maro_test_peer`); those are marked `RUN_SERIAL` because they share a DDS
domain and would otherwise interfere with each other.

## Registered `maro*` commands

Axis / capability (query-only commands are undo-free; the rest are undoable):

| Command | Purpose |
|---|---|
| `maroBindAxis(axis, targetObject)` / `maroUnbindAxis(axis)` | Bind/unbind a `maroAxis` node to the Maya object it drives. |
| `maroConnectAxis(child, parent)` | Wire one axis as the child of another, building the axis hierarchy. |
| `maroSetControlMode(axis, 0\|1)` | Switch an axis between Manual (0) and ROS (1) control. |
| `maroListAxisNodes([-capabilities axis])` | Query every axis, or one axis's capability stack, as a flat string array (consumed by MaroUI's Python side). |
| `maroAddCapability(-type <name>, axis)` | Create a new capability node and connect it into the axis's next free slot. |
| `maroConnectCapability(capNode, axis, [-index i])` / `maroDisconnectCapability(axis, -index i)` | Connect/disconnect an existing capability node. |

ROS 2 bridge and coordinate proxy:

| Command | Purpose |
|---|---|
| `maroStartBridge(robotName)` / `maroStopBridge()` | Start/stop the ROS 2 bridge: publishes `/<robotName>/joint_states`, `/tf`, and optionally LiDAR scans; subscribes to `/<robotName>/joint_commands`. |
| `maroBridgeStats()` | Diagnostic counters: `[collected, drained, applied, threadTicks, publishErrors, drainedLidarScans]`. |
| `maroMayaToRos(...)` | Pure coordinate-convention conversion (Maya → ROS), used by the dual-viewport proxy and testable without a bridge. |
| `maroSetRosProxyTarget(object)` / `-clear` | Point MaroUI's right-hand viewport's isolation at a specific object. |

UI entry points:

| Command | Purpose |
|---|---|
| `maroMainWindow` | Open MaroUI (dual viewport + ONE + Tech Diag panels). Idempotent — restores if already open. |
| `maroBuildMenu` | Build the top-level "Maro" Maya menu. |
| `maroDiagPanel` | Open the plugin's own crash/error-debugging panel (unrelated to Tech Diag — see MaroUI section above). |

Debugging Diag (`boad`/`book`) — for plugin/Maya errors, independent of the axis system:

| Command | Purpose |
|---|---|
| `maroDiagPanelRows` / `maroDiagPanelDetail` | Query the diagnostic record stream for the panel. |
| `maroDiagRegisterRemedy` / `maroDiagRequestRemedy` / `maroApplyRemedy` | Register a fix for a known error hash, queue it, then apply it (undoable). |

A full flag-by-flag reference (including test-only utilities) isn't
maintained in this README — read the relevant command's `.cpp`/`newSyntax()`
in `src/maro_plugin/`, or the per-feature specs under `docs/superpowers/`.

## Layout

- `src/maro_plugin/` — the Maya plugin: nodes (axis, capability, LiDAR,
  device), commands, the ROS 2 bridge runtime, `dagMenuProc` chaining, and
  the always-on main-thread pump that moves data between Maya and ROS 2.
- `src/maro_transform/` — coordinate/unit conversion library shared by the
  plugin and its unit tests.
- `src/maro_lidar/` — Embree-backed raycasting engine used by `maroLidar`.
- `src/maro_diag/` — Maya-independent presenter/model logic for the
  debugging Diag panel (`boad`/`book`), covered by its own GoogleTest binary.
- `src/maro_ipc/` — the named-pipe/job-object protocol between the plugin
  and the sentinel watchdog.
- `src/maro_sentinel/` — `maro_sentinel.exe`, a separate watchdog process
  that detects whether a Maya session crashed vs. exited cleanly.
- `python/` — everything Qt-facing (MaroUI's window, the SONE/ONE editors,
  `dagMenuProc`'s Python-side handler, Tech Diag, the diagnostic panel, the
  ROS coordinate proxy) — staged next to the built plugin at build time.
- `tests/` — GoogleTest unit tests and `mayapy` scenario tests, wired into
  CTest.
- `docs/superpowers/` — design specs, implementation plans, and task-by-task
  history for every feature slice built through this project's
  subagent-driven-development workflow.
- `docs/maro-main-ui-manual-checklist.md` — the interactive-Maya-only
  verification checklist for everything automated tests can't reach (real
  mouse gestures, real window rendering, unload-while-open safety).
