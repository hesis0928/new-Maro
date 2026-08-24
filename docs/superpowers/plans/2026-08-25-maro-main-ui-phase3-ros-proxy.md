# Maro 메인 UI Phase 3 (ROS 좌표 프록시) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 우측("ROS") 뷰포트가 처음으로 실제 콘텐츠를 보여준다 — 선택된(또는 고정 지정된) 오브젝트의 위치/회전을 `maro_transform`의 실제 ROS 발행 파이프라인과 같은 함수로 변환해서, 우측 뷰포트에만 보이는 로케이터로 실시간 반영한다.

**Architecture:** 새 C++ 커맨드 두 개(`maroMayaToRos` — 순수 변환, `maroSetRosProxyTarget` — 동기화 대상 고정/해제)가 `maro_transform::mayaToRosPosition`/`mayaToRosRotation`을 그대로 재사용한다. 새 Python 모듈 `python/maroRosProxy.py`가 idle 콜백 하나로 (1) 좌측 뷰포트의 `isolateSelect` 격리 목록을 매 틱 갱신하고 (2) 프록시 로케이터를 갱신한다. `maroMainWindow.py`는 두 뷰포트 이름을 넘기며 이 모듈을 시작/정지하기만 한다.

**Tech Stack:** C++17(MSyntax/MArgDatabase, `maro_transform` 재사용), Python(`maya.cmds`, `maya.api.OpenMaya`).

## Global Constraints

- 스펙: `docs/superpowers/specs/2026-08-25-maro-main-ui-phase3-ros-proxy-design.md`
- `maroMayaToRos`는 `mayaToRosPosition(const Vec3&, const SceneUnit&)`/`mayaToRosRotation(const Quat&)`(`src/maro_transform/include/maro_transform/Convert.h`, 이미 존재)를 그대로 부른다 — 변환 수식을 다시 구현하지 않는다. `Vec3{x,y,z}`, `Quat{x,y,z,w}`(ROS 순서), `SceneUnit{metersPerMayaUnit}` — 전부 이미 있는 순수 구조체(`src/maro_transform/include/maro_transform/Types.h`).
- `BoadMaro::error`의 정확한 시그니처: `static void error(const std::string& siteTag, const MString& message, const DgContext& context = DgContext{}, const RemedyAction& remedyAction = RemedyAction{});`. `DgContext`는 `maro::onfix::capture(const MString& nodeType, const MString& attributeName, const MString& axisOrTarget)`로 만든다(`src/maro_plugin/MaroDiag.h`).
- 새 커맨드는 `MArgDatabase`+`MSyntax::addFlag`로 플래그를 받는다 — `MaroPanelCommands.cpp`의 `MaroDiagPanelRowsCommand::newSyntax()`/`doIt()`가 이 패턴의 기존 예시다.
- `isolateSelect`의 정확한 플래그 동작(패널별로 정말 독립적으로 걸리는지, `addDagObject`가 정말 멱등인지)은 이 플랜 작성 시점에 실제 Maya 2026에서 검증되지 않았다 — Task 2에서 구현 중 직접 확인하고, 계획과 다르면 실제 동작을 따르고 그 이유를 기록한다.
- scriptJob의 생명주기는 `maroMainWindow`의 창 열림/닫힘, 플러그인 로드/언로드와 정확히 맞아야 한다 — 언로드 후에도 살아있는 idle 콜백은 사라진 커맨드를 찾다가 에러를 내거나 Maya를 불안정하게 만들 수 있다. `start()`/`stop()` 둘 다 멱등해야 하고(중복 호출 안전), 두 개의 독립된 경로(창 `closeCommand`, 플러그인 언로드)에서 둘 다 `stop()`을 부른다.
- 빌드는 항상 `--config Release`를 명시한다.
- 빌드 환경: `VsDevCmd.bat`를 빌드와 같은 PowerShell 호출 안에서 설정한다:

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cd C:\Users\ckd30\Projects\Maya_Ros_Sim
cmake --build out/build --config Release
```

- `ctest --test-dir out/build -C Release --output-on-failure`는 **전부 통과해야 한다** — 사전 결함이 없다.
- Task 1(새 커맨드)은 순수 계산 + optionVar 설정이라 mayapy 배치 테스트로 완전히 검증 가능하다. Task 2(scriptJob, isolateSelect, 로케이터 생성)는 대화형 Maya가 필요한 부분이 있다 — Phase 0-1/2와 같은 한계.

## 파일 구조

| 파일 | 책임 |
|---|---|
| `src/maro_plugin/MaroRosProxyCommands.h` / `.cpp` | (신규) `maroMayaToRos`, `maroSetRosProxyTarget` 커맨드 |
| `src/maro_plugin/MaroPluginMain.cpp` | (수정) 새 커맨드 2개 등록/해제, 언로드 시 `maroRosProxy.stop()` 호출 |
| `src/maro_plugin/CMakeLists.txt` | (수정) 새 `.cpp` 소스 추가 |
| `tests/maya/test_ros_proxy_commands.py` | (신규) 두 커맨드의 mayapy 배치 테스트 |
| `python/maroRosProxy.py` | (신규) idle 콜백 — 격리 갱신 + 프록시 동기화 |
| `python/maroMainWindow.py` | (수정) `buildUI()`에서 `maroRosProxy.start(...)` 호출, `show()`의 `closeCommand`에서 `stop()` 호출 |
| `docs/maro-main-ui-manual-checklist.md` | (수정) ROS 프록시 수동 확인 섹션 추가 |

---

### Task 1: `maroMayaToRos` / `maroSetRosProxyTarget` 커맨드

**Files:**
- Create: `src/maro_plugin/MaroRosProxyCommands.h`
- Create: `src/maro_plugin/MaroRosProxyCommands.cpp`
- Modify: `src/maro_plugin/MaroPluginMain.cpp`
- Modify: `src/maro_plugin/CMakeLists.txt`
- Create: `tests/maya/test_ros_proxy_commands.py`
- Modify: `tests/CMakeLists.txt` (mayapy 테스트 목록에 `ros_proxy_commands` 추가)

**Interfaces:**
- Produces: Maya 커맨드 `maroMayaToRos -px -py -pz -qx -qy -qz -qw`(전부 필수 double 플래그) → 변환된 `[x, y, z, qx, qy, qz, qw]` 7개짜리 `MDoubleArray`를 결과로 돌려줌(ROS 좌표계, 미터 단위).
- Produces: Maya 커맨드 `maroSetRosProxyTarget <objectName>` 또는 `maroSetRosProxyTarget -clear`(`-c`) → optionVar `maroRosProxyPinnedTarget`을 설정/삭제.
- Consumes: `maro::mayaToRosPosition`, `maro::mayaToRosRotation`(`maro_transform`, 이미 링크돼 있음), `maro::BoadMaro::error`, `maro::onfix::capture`(이미 존재).

- [ ] **Step 1: 헤더 작성**

`src/maro_plugin/MaroRosProxyCommands.h`:

```cpp
#pragma once

#include <maya/MPxCommand.h>
#include <maya/MSyntax.h>

namespace maro {

// Maya(Y-up) 위치+쿼터니언을 ROS(Z-up, 미터) 위치+쿼터니언으로 변환한다.
// maro_transform::mayaToRosPosition/mayaToRosRotation을 그대로 감싸는
// 순수 계산 -- 실제 ROS 발행 파이프라인(MaroRosRuntime.cpp)과 같은 소스를
// 쓴다. DG를 편집하지 않으므로 undo 불필요.
class MaroMayaToRosCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
};

// python/maroRosProxy.py의 idle 콜백이 매 틱 확인하는 "동기화 대상 고정"
// 상태를 설정/해제한다. 상태는 optionVar 하나(maroRosProxyPinnedTarget)에
// 저장한다 -- Python 쪽이 매 틱 optionVar를 읽기만 하면 되므로 C++/Python
// 사이에 별도 통신 채널이 필요 없다.
class MaroSetRosProxyTargetCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
};

}  // namespace maro
```

- [ ] **Step 2: 실패하는 테스트부터 작성**

`tests/maya/test_ros_proxy_commands.py`:

```python
"""maroMayaToRos / maroSetRosProxyTarget 커맨드 -- 둘 다 순수 계산 +
optionVar 설정이라 mayapy 배치 모드에서 완전히 검증 가능하다(modelPanel과
달리 UI가 전혀 필요 없다).
"""
import math
import os

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

# --- maroMayaToRos ---------------------------------------------------
# Maya (0, 0, 1)(앞쪽, cm 단위 1cm)이 ROS로는 (0, -1, 0)이 돼야 한다
# (Convert.h 주석: mayaToRos: (x, y, z) -> (x, -z, y)). 위치는 미터로도
# 바뀐다 -- 기본 씬 단위가 cm이면 1 Maya 단위 = 0.01미터.
result = cmds.maroMayaToRos(px=0.0, py=0.0, pz=1.0, qx=0.0, qy=0.0, qz=0.0, qw=1.0)
assert len(result) == 7, f"expected 7 values, got {len(result)}: {result}"
assert abs(result[0] - 0.0) < 1e-9, result
assert abs(result[1] - (-0.01)) < 1e-9, result  # -z, cm -> m
assert abs(result[2] - 0.0) < 1e-9, result
# 항등 회전은 항등 회전으로 남는다 (Convert.h: 스칼라부 w는 불변).
assert abs(result[6] - 1.0) < 1e-9, result
print("maroMayaToRos basic conversion OK")

# 필수 플래그 하나라도 빠지면 실패해야 한다(예외가 아니라 kFailure).
try:
    cmds.maroMayaToRos(px=0.0, py=0.0, pz=0.0, qx=0.0, qy=0.0, qz=0.0)
    raise AssertionError("maroMayaToRos must fail when -qw is missing")
except RuntimeError:
    pass
print("maroMayaToRos missing-flag guard OK")

# --- maroSetRosProxyTarget --------------------------------------------
cube = cmds.polyCube(name="rosProxyTestCube")[0]

assert not cmds.optionVar(exists="maroRosProxyPinnedTarget")
cmds.maroSetRosProxyTarget(cube)
assert cmds.optionVar(exists="maroRosProxyPinnedTarget")
assert cmds.optionVar(query="maroRosProxyPinnedTarget") == cube
print("maroSetRosProxyTarget pin OK")

cmds.maroSetRosProxyTarget(clear=True)
assert not cmds.optionVar(exists="maroRosProxyPinnedTarget")
print("maroSetRosProxyTarget clear OK")

# 존재하지 않는 오브젝트를 지정하면 실패해야 한다.
try:
    cmds.maroSetRosProxyTarget("thisObjectDoesNotExist")
    raise AssertionError("maroSetRosProxyTarget must fail for a nonexistent object")
except RuntimeError:
    pass
print("maroSetRosProxyTarget nonexistent-object guard OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

이 시점엔 커맨드가 등록조차 안 됐으므로, 아래 실행은 `maroMayaToRos`가 없다는 에러로 실패해야 한다. `tests/CMakeLists.txt`의 `foreach(maya_test ...)` 목록에 `ros_proxy_commands`를 추가한 뒤:

```powershell
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release -R maya_ros_proxy_commands --output-on-failure
```

기대: 실패(`Unknown command "maroMayaToRos"` 류의 에러).

- [ ] **Step 4: 구현**

`src/maro_plugin/MaroRosProxyCommands.cpp`:

```cpp
#include "MaroRosProxyCommands.h"

#include <exception>

#include <maya/MArgDatabase.h>
#include <maya/MDistance.h>
#include <maya/MDoubleArray.h>
#include <maya/MGlobal.h>
#include <maya/MSelectionList.h>
#include <maya/MStringArray.h>

#include "MaroDiag.h"
#include "maro_transform/Convert.h"
#include "maro_transform/Types.h"

namespace maro {
namespace {

// 짧은/긴 플래그 이름을 따로 둔다 -- MaroPanelCommands.cpp의
// kSeverityFlag/kSeverityFlagLong과 같은 이 코드베이스의 기존 관례
// (짧은 이름과 긴 이름에 같은 문자열을 재사용하는 전례가 없다).
constexpr char kPx[] = "-px", kPxLong[] = "-positionX";
constexpr char kPy[] = "-py", kPyLong[] = "-positionY";
constexpr char kPz[] = "-pz", kPzLong[] = "-positionZ";
constexpr char kQx[] = "-qx", kQxLong[] = "-rotationX";
constexpr char kQy[] = "-qy", kQyLong[] = "-rotationY";
constexpr char kQz[] = "-qz", kQzLong[] = "-rotationZ";
constexpr char kQw[] = "-qw", kQwLong[] = "-rotationW";
constexpr char kClearFlag[] = "-c", kClearFlagLong[] = "-clear";
constexpr char kPinnedTargetOptionVar[] = "maroRosProxyPinnedTarget";

// 필수 double 플래그 하나를 읽는다. 없으면 BoadMaro::error를 남기고
// kFailure를 돌려준다 -- 예외가 아니라 정상적인 커맨드 실패 경로다.
MStatus requireDoubleFlag(const MArgDatabase& argData, const char* flag, double& out) {
    if (!argData.isFlagSet(flag)) {
        BoadMaro::error(
            "MaroMayaToRosCommand.MissingFlag",
            MString("Maro: maroMayaToRos is missing required flag ") + flag,
            onfix::capture("", "", ""));
        return MS::kFailure;
    }
    MStatus status;
    out = argData.flagArgumentDouble(flag, 0, &status);
    return status;
}

}  // namespace

void* MaroMayaToRosCommand::creator() { return new MaroMayaToRosCommand(); }

MSyntax MaroMayaToRosCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag(kPx, kPxLong, MSyntax::kDouble);
    syntax.addFlag(kPy, kPyLong, MSyntax::kDouble);
    syntax.addFlag(kPz, kPzLong, MSyntax::kDouble);
    syntax.addFlag(kQx, kQxLong, MSyntax::kDouble);
    syntax.addFlag(kQy, kQyLong, MSyntax::kDouble);
    syntax.addFlag(kQz, kQzLong, MSyntax::kDouble);
    syntax.addFlag(kQw, kQwLong, MSyntax::kDouble);
    return syntax;
}

MStatus MaroMayaToRosCommand::doIt(const MArgList& args) {
    try {
        MStatus status;
        MArgDatabase argData(newSyntax(), args, &status);
        if (!status) return status;

        Vec3 mayaPos;
        Quat mayaRot;
        if (!(status = requireDoubleFlag(argData, kPx, mayaPos.x))) return status;
        if (!(status = requireDoubleFlag(argData, kPy, mayaPos.y))) return status;
        if (!(status = requireDoubleFlag(argData, kPz, mayaPos.z))) return status;
        if (!(status = requireDoubleFlag(argData, kQx, mayaRot.x))) return status;
        if (!(status = requireDoubleFlag(argData, kQy, mayaRot.y))) return status;
        if (!(status = requireDoubleFlag(argData, kQz, mayaRot.z))) return status;
        if (!(status = requireDoubleFlag(argData, kQw, mayaRot.w))) return status;

        // MaroPump.cpp의 currentSceneUnit()과 같은 방식 -- 호출부가
        // 씬 단위를 몰라도 되게 커맨드 내부에서 직접 구한다.
        SceneUnit unit;
        unit.metersPerMayaUnit =
            MDistance(1.0, MDistance::internalUnit()).asMeters();

        const Vec3 rosPos = mayaToRosPosition(mayaPos, unit);
        const Quat rosRot = mayaToRosRotation(mayaRot);

        MDoubleArray result;
        result.append(rosPos.x);
        result.append(rosPos.y);
        result.append(rosPos.z);
        result.append(rosRot.x);
        result.append(rosRot.y);
        result.append(rosRot.z);
        result.append(rosRot.w);
        setResult(result);
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: maroMayaToRos failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError("Maro: maroMayaToRos failed with unknown error.");
        return MS::kFailure;
    }
}

void* MaroSetRosProxyTargetCommand::creator() { return new MaroSetRosProxyTargetCommand(); }

MSyntax MaroSetRosProxyTargetCommand::newSyntax() {
    MSyntax syntax;
    syntax.addFlag(kClearFlag, kClearFlagLong, MSyntax::kNoArg);
    syntax.setObjectType(MSyntax::kStringObjects, 0, 1);
    return syntax;
}

MStatus MaroSetRosProxyTargetCommand::doIt(const MArgList& args) {
    try {
        MStatus status;
        MArgDatabase argData(newSyntax(), args, &status);
        if (!status) return status;

        const bool clearRequested = argData.isFlagSet(kClearFlagLong);
        MStringArray objects;
        argData.getObjects(objects);

        if (clearRequested) {
            if (objects.length() > 0) {
                BoadMaro::error(
                    "MaroSetRosProxyTargetCommand.ClearWithObject",
                    "Maro: maroSetRosProxyTarget -clear does not take an object name.",
                    onfix::capture("", "", ""));
                return MS::kFailure;
            }
            MGlobal::executeCommand(
                MString("optionVar -remove ") + kPinnedTargetOptionVar + ";");
            return MS::kSuccess;
        }

        if (objects.length() != 1) {
            BoadMaro::error(
                "MaroSetRosProxyTargetCommand.WrongArgCount",
                "Maro: maroSetRosProxyTarget needs exactly one object name, or -clear.",
                onfix::capture("", "", ""));
            return MS::kFailure;
        }

        MSelectionList sel;
        if (!sel.add(objects[0])) {
            BoadMaro::error(
                "MaroSetRosProxyTargetCommand.ObjectNotFound",
                MString("Maro: maroSetRosProxyTarget could not find object ") + objects[0],
                onfix::capture("", "", ""));
            return MS::kFailure;
        }

        MGlobal::executeCommand(
            MString("optionVar -sv ") + kPinnedTargetOptionVar + " \"" + objects[0] + "\";");
        return MS::kSuccess;
    } catch (const std::exception& e) {
        MGlobal::displayError(
            MString("Maro: maroSetRosProxyTarget failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError(
            "Maro: maroSetRosProxyTarget failed with unknown error.");
        return MS::kFailure;
    }
}

}  // namespace maro
```

- [ ] **Step 5: 등록/해제 배선**

`src/maro_plugin/CMakeLists.txt`의 `SOURCE_FILES`에 `MaroRosProxyCommands.cpp` 추가.

`src/maro_plugin/MaroPluginMain.cpp`: `maroBuildMenu` 등록(`:350-354` 근방) 바로 다음에:

```cpp
    status = plugin.registerCommand("maroMayaToRos",
                                    maro::MaroMayaToRosCommand::creator,
                                    maro::MaroMayaToRosCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroMayaToRos");
        return status;
    }

    status = plugin.registerCommand("maroSetRosProxyTarget",
                                    maro::MaroSetRosProxyTargetCommand::creator,
                                    maro::MaroSetRosProxyTargetCommand::newSyntax);
    if (!status) {
        status.perror("Maro: failed to register maroSetRosProxyTarget");
        return status;
    }
```

파일 위쪽 `#include` 목록에 `#include "MaroRosProxyCommands.h"` 추가(알파벳 순서 등 기존 정렬 방식이 있으면 맞춘다).

해제는 등록 역순 규율에 따라 `maroBuildMenu` 해제(`:452` 근방) **바로 앞에**(가장 나중에 등록된 것부터 먼저 해제):

```cpp
        plugin.deregisterCommand("maroSetRosProxyTarget");
        plugin.deregisterCommand("maroMayaToRos");
```

- [ ] **Step 6: 빌드하고 테스트 통과 확인**

```powershell
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release -R maya_ros_proxy_commands --output-on-failure
```

기대: 통과. 전체 스위트도 돌려 회귀 확인:

```bash
ctest --test-dir out/build -C Release --output-on-failure
```

기대: 전부 통과.

- [ ] **Step 7: 커밋**

```bash
git add src/maro_plugin/MaroRosProxyCommands.h src/maro_plugin/MaroRosProxyCommands.cpp \
        src/maro_plugin/MaroPluginMain.cpp src/maro_plugin/CMakeLists.txt \
        tests/maya/test_ros_proxy_commands.py tests/CMakeLists.txt
git commit -m "feat: add maroMayaToRos and maroSetRosProxyTarget commands"
```

---

### Task 2: `maroRosProxy.py` 동기화 루프 + 격리 배선 + 생명주기

**Files:**
- Create: `python/maroRosProxy.py`
- Modify: `python/maroMainWindow.py`
- Modify: `src/maro_plugin/MaroPluginMain.cpp`
- Modify: `src/maro_plugin/CMakeLists.txt` (`MARO_PLUGIN_PY_MODULES`에 `maroRosProxy` 추가)
- Modify: `docs/maro-main-ui-manual-checklist.md`

**Interfaces:**
- Consumes: Task 1의 `maroMayaToRos`, `maroSetRosProxyTarget` 커맨드. `maroMainWindow.py`의 `VIEWPORT_NAME_MAYA`/`VIEWPORT_NAME_ROS` 상수(값으로, import 없이 인자로 전달받음).
- Produces: `maroRosProxy.start(mayaPanelName, rosPanelName)`, `maroRosProxy.stop()` — `maroMainWindow.py`가 부르는 유일한 진입점 두 개.

이 태스크는 scriptJob 생명주기가 창 열림/닫힘/언로드 세 지점에 걸쳐 있어 쪼개면 검증 불가능한 중간 상태가 생긴다 — 하나로 묶는다.

- [ ] **Step 1: `python/maroRosProxy.py` 작성**

```python
"""ROS 좌표 프록시 동기화 -- 설계 스펙
2026-08-25-maro-main-ui-phase3-ros-proxy-design.md.

Maya 오브젝트 하나(기본: 현재 선택, maroSetRosProxyTarget으로 고정 가능)의
월드 위치/회전을 maroMayaToRos로 변환해 maroRosProxy_grp 안의 로케이터로
반영한다. 같은 idle 콜백이 좌측(Maya) 뷰포트의 isolateSelect 목록도 매
틱 갱신한다 -- 새로 생긴 오브젝트가 창을 닫았다 열지 않아도 바로 보이게
하기 위해서다(isolateSelect의 격리 목록은 스냅샷이라 자동으로 안 늘어난다).

maroMainWindow.py를 import하지 않는다 -- 그쪽이 이미 이 모듈을 import하므로
순환 참조가 생긴다. 대신 start()가 두 뷰포트 이름을 인자로 받는다.
"""
import math

import maya.cmds as cmds
import maya.api.OpenMaya as om2

PROXY_GROUP = "maroRosProxy_grp"
PROXY_LOCATOR = "maroRosProxy_loc"
PINNED_OPTIONVAR = "maroRosProxyPinnedTarget"

_JOB_ID = None
_MAYA_PANEL = None
_ROS_PANEL = None


def _ensureProxyGroup():
    if not cmds.objExists(PROXY_GROUP):
        cmds.group(empty=True, name=PROXY_GROUP)
    return PROXY_GROUP


def _ensureProxyLocator():
    _ensureProxyGroup()
    if not cmds.objExists(PROXY_LOCATOR):
        loc = cmds.spaceLocator(name=PROXY_LOCATOR)[0]
        cmds.parent(loc, PROXY_GROUP)
    return PROXY_LOCATOR


def _resolveTarget():
    """동기화 대상 트랜스폼 이름을 돌려준다. 없으면 None.

    고정된 오브젝트가 씬에서 지워졌으면 조용히 선택 추종으로 떨어진다 --
    매 idle 틱마다 에러를 내면 스크립트 에디터가 도배된다.
    """
    if cmds.optionVar(exists=PINNED_OPTIONVAR):
        pinned = cmds.optionVar(query=PINNED_OPTIONVAR)
        if pinned and cmds.objExists(pinned):
            return pinned
    selection = cmds.ls(selection=True, type="transform") or []
    return selection[0] if selection else None


def _refreshMayaIsolation():
    """좌측 패널 격리 목록에 최상위 오브젝트를 매 틱 다시 추가한다.

    이미 격리 목록에 있는 항목을 다시 addDagObject해도 무해(멱등)하다는
    전제다 -- 구현 중 실제로 확인한다. 워킹 스켈레톤 규모에서는 매 틱
    전체를 다시 훑는 비용이 무시할 만하다(범위 밖: DagObjectCreated
    콜백으로 바꿔 증분 갱신).
    """
    proxyGroup = _ensureProxyGroup()
    for obj in (cmds.ls(assemblies=True) or []):
        if obj == proxyGroup:
            continue
        cmds.isolateSelect(_MAYA_PANEL, addDagObject=obj)


def _syncProxy():
    target = _resolveTarget()
    if target is None:
        return

    pos = cmds.xform(target, query=True, worldSpace=True, translation=True)

    dagPath = om2.MSelectionList().add(target).getDagPath(0)
    quat = om2.MFnTransform(dagPath).rotation(om2.MSpace.kWorld, asQuaternion=True)

    converted = cmds.maroMayaToRos(
        px=pos[0], py=pos[1], pz=pos[2],
        qx=quat.x, qy=quat.y, qz=quat.z, qw=quat.w)

    locator = _ensureProxyLocator()
    cmds.xform(locator, worldSpace=True, translation=converted[0:3])
    eulerRad = om2.MQuaternion(converted[3], converted[4], converted[5], converted[6]).asEulerRotation()
    cmds.xform(
        locator, worldSpace=True,
        rotation=[math.degrees(eulerRad.x), math.degrees(eulerRad.y), math.degrees(eulerRad.z)])


def _onIdle():
    _refreshMayaIsolation()
    _syncProxy()


def start(mayaPanelName, rosPanelName):
    """maroMainWindow.buildUI()가 두 뷰포트를 만든 직후 부른다."""
    global _JOB_ID, _MAYA_PANEL, _ROS_PANEL
    _MAYA_PANEL = mayaPanelName
    _ROS_PANEL = rosPanelName

    proxyGroup = _ensureProxyGroup()
    cmds.isolateSelect(_ROS_PANEL, state=True)
    cmds.isolateSelect(_ROS_PANEL, addDagObject=proxyGroup)
    cmds.isolateSelect(_MAYA_PANEL, state=True)

    if _JOB_ID is not None and cmds.scriptJob(exists=_JOB_ID):
        return
    _JOB_ID = cmds.scriptJob(event=["idle", _onIdle], protected=True)


def stop():
    """workspaceControl이 닫히거나(closeCommand) 플러그인이 언로드될 때
    (MaroPluginMain.cpp) 부른다. start()가 한 번도 안 불렸어도 안전하게
    아무 것도 안 한다 -- 언로드는 창을 연 적이 있든 없든 항상 이 함수를
    부르기 때문이다.
    """
    global _JOB_ID
    if _JOB_ID is not None and cmds.scriptJob(exists=_JOB_ID):
        cmds.scriptJob(kill=_JOB_ID, force=True)
    _JOB_ID = None
```

- [ ] **Step 2: `maroMainWindow.py` 배선**

`buildUI()`에서 두 뷰포트를 만든 직후(현재 두 `_buildLabeledViewport(...)` 호출 바로 다음):

```python
    import maroRosProxy
    maroRosProxy.start(VIEWPORT_NAME_MAYA, VIEWPORT_NAME_ROS)
```

`show()`의 `cmds.workspaceControl(...)` 호출에 `closeCommand`를 추가한다:

```python
def _onWorkspaceControlClosed():
    import maroRosProxy
    maroRosProxy.stop()


def show():
    """maroMainWindow 커맨드가 부른다."""
    if cmds.workspaceControl(CONTROL_NAME, exists=True):
        cmds.workspaceControl(CONTROL_NAME, edit=True, restore=True)
        return
    cmds.workspaceControl(
        CONTROL_NAME,
        label="Maro",
        retain=False,
        floating=True,
        initialWidth=900,
        initialHeight=600,
        requiredPlugin="maro",
        closeCommand=_onWorkspaceControlClosed,
        uiScript="import maroMainWindow; maroMainWindow.buildUI()")
```

(`_onWorkspaceControlClosed`는 모듈 최상위 함수로 둔다 — `show()` 안의 클로저로 두면 창이 사라진 뒤에도 그 스코프를 붙드는 문제가 생길 수 있다는, 이 파일이 `_onTestButtonClicked`에 이미 적어 둔 이유와 같다.)

- [ ] **Step 3: `MaroPluginMain.cpp` 언로드 시 이중 안전장치**

`uninitializePlugin`의 `maroMainWindow` 정리 블록(`maroBuildMenu` deregister 직후, `maroMainWindowControl`을 닫는 `MGlobal::executeCommand` 바로 앞)에 추가:

```cpp
        // 창의 closeCommand가 이미 maroRosProxy.stop()을 부르지만,
        // uninitializePlugin이 workspaceControl -e -close를 거치지 않고
        // (예: 창이 이미 닫혀 있던 상태) 곧바로 여기 도달하는 경로도
        // 있으므로 한 번 더 부른다 -- stop()은 멱등이라 두 번 불려도
        // 무해하다.
        maro::runPluginPythonModule("maroRosProxy", "maroRosProxy.stop()");
```

`MaroPluginMain.cpp` 위쪽에 `#include "MaroPythonBridge.h"`가 없으면 추가한다(이미 있을 가능성이 높다 — Task 3의 `maroBuildMenu`가 같은 헤더를 쓴다).

- [ ] **Step 4: CMake 배선**

`src/maro_plugin/CMakeLists.txt`의 `MARO_PLUGIN_PY_MODULES`에 `maroRosProxy` 추가.

- [ ] **Step 5: 빌드 + 전체 테스트**

```powershell
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure
```

기대: 전부 통과(이 태스크는 새 mayapy 테스트를 추가하지 않는다 — `isolateSelect`/`scriptJob`/`modelPanel` 전부 배치 모드에서 의미 있게 검증할 수 없는 것들이라 억지로 배치 테스트를 만들지 않는다. 대신 Step 6의 수동 체크리스트가 이 태스크의 유일한 실질적 검증이다).

- [ ] **Step 6: `docs/maro-main-ui-manual-checklist.md`에 ROS 프록시 확인 섹션 추가**

새 섹션(예: `## 1-2. ROS 좌표 프록시 (Phase 3)`)을 추가한다. 반드시 포함할 것:

- 큐브를 만들고 선택한 뒤, 우측(ROS) 뷰포트에만 로케이터가 나타나는지(좌측엔 안 보여야 함).
- 큐브를 이동/회전하면 로케이터가 실시간으로 따라가는지(값이 `mayaToRosPosition`의 축 변환 규칙 — `(x,y,z) -> (x,-z,y)` — 과 대략 맞는 방향인지 눈으로 확인).
- **창을 연 뒤에 새 오브젝트를 만들어도 좌측 뷰포트에 바로 보이는지**(이번 플랜이 스냅샷 대신 라이브 갱신을 택한 이유 — 사용자가 명시적으로 요구한 항목).
- `cmds.maroSetRosProxyTarget(<오브젝트>)`로 고정한 뒤 다른 오브젝트를 선택해도 프록시가 안 바뀌는지, `-clear`로 풀면 다시 선택 추종으로 돌아가는지.
- **창을 닫으면(언로드 없이) 동기화가 멈추는지** — 창을 닫고 오브젝트를 움직여도 에러가 안 나고(스크립트 에디터 확인), `cmds.scriptJob(listJobs=True)`에 `maroRosProxy` 관련 잡이 안 남아 있는지.
- **플러그인 언로드 — 진짜 go/no-go**: 창이 열려 있고 프록시가 동작 중인 상태에서 `cmds.unloadPlugin("maro")` → 크래시 없음, 에러 없음, `cmds.scriptJob(listJobs=True)`에 잡 안 남음.

결과 기록 표에도 행을 추가한다.

- [ ] **Step 7: 커밋**

```bash
git add python/maroRosProxy.py python/maroMainWindow.py src/maro_plugin/MaroPluginMain.cpp \
        src/maro_plugin/CMakeLists.txt docs/maro-main-ui-manual-checklist.md
git commit -m "feat: sync a selected/pinned object to a ROS-space proxy locator, isolated per viewport"
```
