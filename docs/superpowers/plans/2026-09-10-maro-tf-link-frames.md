# TF를 URDF 링크 프레임에 맞추는 구현 계획

> **에이전트 작업자에게:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development(권장)
> 또는 superpowers:executing-plans로 태스크 단위로 구현하라.

**목표:** 런타임 `/tf`가 URDF `<link>`와 **같은 이름**의 프레임을 **같은 자리**에
발행하게 한다.

**설계:** `docs/superpowers/specs/2026-09-10-maro-tf-link-frames-design.md`

**아키텍처:** `AxisSample`에 `linkName`/`enabled` 두 필드를 더하고,
`MaroPump::collectSamples`가 이름은 바인딩 타겟에서, 자세는 maroAxis
로케이터의 부모 트랜스폼에서 읽게 한다. `MaroRosRuntime::drainAndPublish`는
`child_frame_id`에 링크 이름을 쓰고 `/joint_states`만 `enabled`로 거른다.
파이썬 쪽은 링크 이름 검증을 더한다. 프레임은 `world` 아래 평평하게 둔다.

**기술 스택:** Maya C++ API(`MFnTransform`, `MFnDagNode`, `MDagPath`),
rclcpp, mayapy 배치 테스트 + 실제 ROS 2 피어(`tests/peer/maro_test_peer.cpp`).

## 전역 제약

- 빌드는 항상 `--config Release`. **이 계획은 C++를 고치므로 매 단계
  `cmake --build out/build --config Release`가 필수다.**
- `ctest --test-dir out/build -C Release --output-on-failure` 전부 통과.
- VS 환경은 빌드와 **같은 셸 호출** 안에서 잡아야 한다. PowerShell 도구
  호출 사이에는 환경 변수가 유지되지 않는다.
- 새 테스트 블록은 해당 파일의 teardown **바로 앞**에.
- 커맨드/노드 경계의 예외 처리는 기존 `ScopedCommandContext` +
  `try/catch(std::exception)/catch(...)` 패턴을 따른다.
- 새 파이썬 모듈을 만들지 않는다.
- 링크 이름 규칙은 파이썬 `_shortName(fullPath)` = `fullPath.split("|")[-1]`.
  C++ 등가물은 **`MFnDagNode::name()`**이다. `partialPathName()`은 이름이
  모호할 때 경로 조각을 돌려주므로 쓰면 안 된다.
- 회전은 **`MFnTransform::getRotation(q, MSpace::kWorld)`**로만 읽는다.
  `MTransformationMatrix::rotation()`은 전단을 회전으로 흘린다(실측
  32.692도). 이동은 기존 `MTransformationMatrix::getTranslation`이 맞다
  (`kTransform`과 `kWorld`가 같은 값 -- 실측 확인).

## 파일 구조

| 파일 | 변경 |
|---|---|
| `src/maro_plugin/MaroBridgeQueues.h` | `AxisSample`에 `linkName`, `enabled` |
| `src/maro_plugin/MaroPump.cpp` | `collectSamples` -- 이름/자세 출처 변경, `enabled` 조기 skip 제거 |
| `src/maro_plugin/MaroRosRuntime.cpp` | `drainAndPublish` -- `child_frame_id`, joint_states 게이팅 |
| `tests/maya/test_publish.py` | TF 절 재작성 + 계약 테스트 추가 |
| `python/maroUrdfExport.py` | 링크 이름 검증 |
| `tests/maya/test_urdf_export.py` | 검증 테스트 |

새 파일 없음. 피어(`tests/peer/maro_test_peer.cpp`)는 임의 `child_frame_id`
문자열을 받으므로 **변경 불필요**.

---

### Task 1: 런타임이 링크 이름과 로케이터 부모 프레임을 쓴다

**Files:**
- Modify: `src/maro_plugin/MaroBridgeQueues.h` (`struct AxisSample`)
- Modify: `src/maro_plugin/MaroPump.cpp` (`collectSamples`)
- Modify: `src/maro_plugin/MaroRosRuntime.cpp` (`drainAndPublish`의 축 분기)
- Test: `tests/maya/test_publish.py` (TF 절)

**Interfaces:**
- Produces: `AxisSample.linkName`(std::string), `AxisSample.enabled`(bool).
  `/tf`의 `child_frame_id`가 링크 이름이 된다. `/joint_states`는
  `enabled && !jointName.empty()`인 축만 담는다.

- [ ] **Step 1: 테스트 픽스처를 먼저 고쳐 RED를 만든다**

`tests/maya/test_publish.py`에서 **지금 큐브에 걸려 있는 자세를 로케이터의
부모 트랜스폼으로 옮기고, 큐브에는 다른 자세를 준다.** 이게 이 태스크의
핵심 방어선이다 -- 둘을 같은 자세로 두면 자세 출처를 안 고쳐도 통과한다.

`cmds.setAttr(cube + ".translateX", ...)` 세 줄과 `rotateZ` 한 줄을 찾아
그 블록을 통째로 아래로 바꾼다:

```python
    # 프레임 자세는 **로케이터의 부모 트랜스폼**에서 온다(설계 스펙 §2-2).
    # 바인딩된 큐브에는 일부러 **다른** 자세를 준다 -- 둘이 같으면 자세
    # 출처가 틀려도 이 테스트가 통과해 버린다.
    axisFrame = cmds.listRelatives(axis, parent=True, fullPath=True)[0]
    cmds.setAttr(axisFrame + ".translateX", MAYA_POSITION_CM[0])
    cmds.setAttr(axisFrame + ".translateY", MAYA_POSITION_CM[1])
    cmds.setAttr(axisFrame + ".translateZ", MAYA_POSITION_CM[2])
    cmds.setAttr(axisFrame + ".rotateZ", math.radians(MAYA_ROTATE_Z_DEG))

    # 미끼(decoy): 바인딩 타겟을 읽으면 이 값이 나온다 -> 실패해야 한다.
    cmds.setAttr(cube + ".translateX", -5.0)
    cmds.setAttr(cube + ".translateY", 7.0)
    cmds.setAttr(cube + ".translateZ", -11.0)
    cmds.setAttr(cube + ".rotateZ", math.radians(-25.0))
```

그리고 TF가 쓰는 프레임 이름 상수를 더한다. `EXPECTED_JOINT = "axisPub"`
줄 **바로 아래**에 넣고, 그 위 주석의 마지막 문장(`/tf`의 child_frame_id는
sample.jointName 그대로다...)을 아래처럼 고친다:

```python
    # `/tf`의 child_frame_id는 이제 **링크 이름**이다(설계 스펙 §2-1) --
    # jointName이 아니라 바인딩 타겟의 짧은 이름이다. joint_states는
    # 그대로 jointName을 쓰므로 두 이름이 갈린다.
    EXPECTED_JOINT = "axisPub"
    EXPECTED_LINK = "seg"        # cube = cmds.polyCube(name="seg")[0]
```

TF 절에서 피어에 넘기는 이름과 파싱 접두사를 `EXPECTED_JOINT` ->
`EXPECTED_LINK`로 바꾼다(6곳: `subprocess.Popen`의 인자, timeout assert
메시지, `t_prefix`, `r_prefix`, parse assert 메시지, 마지막 `print`).

- [ ] **Step 2: 실패를 확인한다**

```bash
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release -R maya_publish --output-on-failure
```

Expected: FAIL -- 피어가 `child_frame_id == "seg"`인 변환을 못 받고
타임아웃한다(`peer never received a /tf transform for 'seg'`).

- [ ] **Step 3: `AxisSample`에 두 필드를 더한다**

`src/maro_plugin/MaroBridgeQueues.h`의 `struct AxisSample`을 이걸로 바꾼다:

```cpp
struct AxisSample {
    // jointName은 /joint_states의 이름이고, linkName은 /tf의
    // child_frame_id다. 둘은 서로 다른 노드에서 오며 일반적으로 다르다
    // (설계 스펙 §2-1) -- URDF의 <joint name>과 <link name>이 그런 것과
    // 같은 이유다.
    std::string jointName;
    std::string linkName;
    // enabled는 /joint_states만 거른다. 비활성 축도 씬에서 공간을
    // 차지하므로 TF 프레임은 낸다 -- 안 그러면 URDF엔 있는 링크가 TF엔
    // 없어 RViz에 프레임 없는 링크가 생긴다(설계 스펙 §2-3).
    bool enabled = true;
    double value = 0.0;
    Vec3 position;
    Quat rotation;
    AxisConvention convention;
    SceneUnit unit;
};
```

- [ ] **Step 4: `collectSamples`를 고친다**

`src/maro_plugin/MaroPump.cpp` 상단 include에 두 줄을 더한다(알파벳 순서
유지 -- `MFnDependencyNode.h` 앞뒤):

```cpp
#include <maya/MFnDagNode.h>
#include <maya/MFnTransform.h>
```

`collectSamples`의 루프 앞부분에서, 지금 이렇게 되어 있는 곳:

```cpp
        MFnDependencyNode axisFn(it.thisNode());
        if (axisFn.typeId() != MaroAxisNode::id) continue;
        if (!axisFn.findPlug(MaroAxisNode::aEnabled, false).asBool()) continue;

        const MString joint =
            axisFn.findPlug(MaroAxisNode::aJointName, false).asString();
        if (joint.length() == 0) continue;   // 이름 없는 축은 발행하지 않는다

        AxisSample sample;
        sample.jointName = joint.asChar();
```

를 이것으로 바꾼다:

```cpp
        MFnDependencyNode axisFn(it.thisNode());
        if (axisFn.typeId() != MaroAxisNode::id) continue;

        // enabled와 빈 jointName은 더 이상 축을 통째로 건너뛰지 않는다.
        // 둘 다 /joint_states만 거르고 TF 프레임은 낸다 -- 프레임 이름이
        // 이제 jointName이 아니라 링크 이름이라 성립한다(설계 스펙 §2-4).
        AxisSample sample;
        sample.jointName =
            axisFn.findPlug(MaroAxisNode::aJointName, false).asString().asChar();
        sample.enabled = axisFn.findPlug(MaroAxisNode::aEnabled, false).asBool();
```

이어서, 바인딩 타겟을 찾는 기존 블록은 그대로 두되 목적이 바뀌었으므로
주석 첫 문단을 아래로 교체하고, `targetPath`를 얻은 **직후** 링크 이름을
채운다:

```cpp
        // 바인딩 타겟은 이제 링크 **이름**의 출처다(자세의 출처가 아니다 --
        // 그건 아래 로케이터 부모다). targetObject는 message 연결이라
        // 데이터를 나르지 않으므로 MaroBindAxisCommand::doIt과 같은
        // 방식으로만 얻을 수 있다 -- connectedTo(asDst=true)로 소스 쪽을
        // 본다. 바인딩이 없으면 링크 이름을 만들 수 없고, URDF 쪽도 그런
        // 축을 거부하므로(python/maroUrdfExport.py의 검증) 프레임도 내지
        // 않는다.
        MPlugArray targetSources;
        axisFn.findPlug(MaroAxisNode::aTargetObject, false)
            .connectedTo(targetSources, true, false);
        if (targetSources.length() == 0) continue;

        MDagPath targetPath;
        if (MDagPath::getAPathTo(targetSources[0].node(), targetPath) !=
            MS::kSuccess) {
            continue;
        }

        // 링크 이름 규칙은 파이썬 _shortName(fullPath) =
        // fullPath.split("|")[-1]과 **같아야 한다**. name()이 그 등가물이다
        // -- partialPathName()은 이름이 모호할 때 경로 조각을 돌려주므로
        // 파이썬과 갈린다. 네임스페이스는 양쪽 다 남긴다("ns:cube").
        sample.linkName = MFnDagNode(targetPath).name().asChar();
```

그리고 자세를 읽는 블록 -- 지금 `targetPath.inclusiveMatrix()`를 쓰는
부분(주석 "/tf 프레임은 전부 공통 루트..."부터 `sample.rotation = rotation;`
까지)을 통째로 아래로 바꾼다:

```cpp
        // 프레임 **자세**는 maroAxis 로케이터의 부모 트랜스폼이다 --
        // 바인딩 타겟이 아니다. URDF의 조인트 원점·관절축·메쉬 정점이 전부
        // 이 노드 기준으로 계산되므로(python/maroUrdfExport.py의
        // _axisParentTransformPath), 다른 노드를 쓰면 프레임과 메쉬가
        // 통째로 어긋난다 -- 슬라이스 1이 실제로 겪은 100mm 버그와 같은
        // 종류다(설계 스펙 §2-2).
        MDagPath framePath;
        if (MDagPath::getAPathTo(it.thisNode(), framePath) != MS::kSuccess) {
            continue;
        }
        // 셰이프 -> 부모 트랜스폼. 길이 0인 경로에서 pop()이 실패하는
        // 경우가 실제로 있다(MaroDeleteWatcher.cpp:149의 실측 주석).
        if (framePath.pop() != MS::kSuccess) continue;
        if (!framePath.hasFn(MFn::kTransform)) continue;

        MTransformationMatrix xform(framePath.inclusiveMatrix());
        MStatus translationStatus;
        const MVector t =
            xform.getTranslation(MSpace::kTransform, &translationStatus);

        // 회전만은 MFnTransform으로 읽는다. 부모 비균등 스케일과 자식
        // 회전이 만나면 전단이 생기고, 행렬 분해는 그 전단을 회전으로
        // 흘린다 -- 실측 32.692도. MFnTransform::getRotation(kWorld)는 그
        // 경로를 타지 않아 스케일에 0.000000도 흔들린다. 파이썬
        // _linkFrameWorldRigid가 같은 이유로 같은 호출을 쓴다.
        MStatus frameStatus;
        MFnTransform frameFn(framePath, &frameStatus);
        if (!frameStatus) continue;
        MQuaternion q;
        if (frameFn.getRotation(q, MSpace::kWorld) != MS::kSuccess) continue;

        const Vec3 position{t.x, t.y, t.z};
        const Quat rotation{q.x, q.y, q.z, q.w};
        if (!translationStatus || !isFinite(position) || !isFinite(rotation)) {
            continue;
        }

        sample.position = position;
        sample.rotation = rotation;
```

- [ ] **Step 5: `drainAndPublish`를 고친다**

`src/maro_plugin/MaroRosRuntime.cpp`의 축 루프에서, 지금:

```cpp
            for (const AxisSample& sample : samples) {
                joints.name.push_back(sample.jointName);
                joints.position.push_back(sample.value);
```

를 이것으로 바꾼다:

```cpp
            for (const AxisSample& sample : samples) {
                // enabled와 이름은 /joint_states만 거른다 -- TF 프레임은
                // 아래에서 무조건 낸다(설계 스펙 §2-3, §2-4).
                if (sample.enabled && !sample.jointName.empty()) {
                    joints.name.push_back(sample.jointName);
                    joints.position.push_back(sample.value);
                }
```

그리고 같은 루프 안의 `t.child_frame_id = sample.jointName;`을:

```cpp
                // URDF <link name>과 같은 이름이어야 RViz의 RobotModel이
                // 이 프레임을 찾는다(설계 스펙 §2-1).
                t.child_frame_id = sample.linkName;
```

- [ ] **Step 6: 통과를 확인한다**

```bash
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release -R maya_publish --output-on-failure
```

Expected: PASS -- `tf round trip OK (child_frame_id=seg, ...)`이고 값이
로케이터 부모의 자세와 일치한다.

- [ ] **Step 7: 커밋**

```bash
git add src/maro_plugin/ tests/maya/test_publish.py && git commit -m "fix(tf): publish URDF link frames from the locator parent transform"
```

- [ ] **Step 8: 미끼가 실제로 무는지 확인한다 (커밋 뒤에)**

Step 4의 `framePath` 자리를 잠깐 `targetPath`로 되돌려 빌드·실행한다.
Expected: FAIL -- 미끼 자세가 나와 값 비교가 깨진다. 확인 후
`git checkout -- src/maro_plugin/MaroPump.cpp`로 되돌린다.

**반드시 Step 7 커밋 뒤에 하라.** 커밋 전에 `git checkout --`를 쓰면 그
파일의 작업이 통째로 날아간다(이 세션에서 실제로 한 번 겪었다).

---

### Task 2: URDF 링크 이름 검증

**Files:**
- Modify: `python/maroUrdfExport.py` (`buildAxisTree`의 검증 자리)
- Test: `tests/maya/test_urdf_export.py` (teardown 앞)

**Interfaces:**
- Consumes: 없음(Task 1과 독립).
- Produces: `buildAxisTree`가 빈 링크 이름과 중복 링크 이름에 `ValueError`를
  던진다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/maya/test_urdf_export.py`의 `maya.standalone.uninitialize()` 앞에:

```python
print("[test] 링크 이름 검증")

# 바인딩 없는 축 -> <link name=""> -- check_urdf가 거부하는 무효 URDF이고,
# TF 쪽에서는 이름을 만들 수 없어 프레임 자체가 안 나간다.
cmds.file(new=True, force=True)
cmds.currentUnit(angle="rad")
cmds.currentUnit(linear="cm")
_lnCube = cmds.polyCube(name="lnBody")[0]
_lnAxis = cmds.createNode("maroAxis", name="lnAxis", parent=_lnCube)
cmds.setAttr(_lnAxis + ".jointName", "ln_root", type="string")
# maroBindAxis를 일부러 부르지 않는다 -- 바인딩 없는 축이다.
try:
    urdf.export(os.path.join(tempfile.mkdtemp(), "ln.urdf"))
    raise AssertionError("unbound axis should have been rejected")
except ValueError as _e:
    assert "lnAxis" in str(_e), str(_e)

# 링크 이름 중복 -- 같은 짧은 이름을 가진 두 트랜스폼. 무효 URDF이고,
# TF에서는 두 발행자가 같은 프레임을 써서 화면이 떨린다.
cmds.file(new=True, force=True)
cmds.currentUnit(angle="rad")
cmds.currentUnit(linear="cm")
_dupA = cmds.polyCube(name="dupBody")[0]
_dupGrp = cmds.group(empty=True, name="dupGroup")
_dupB = cmds.polyCube(name="dupBody")[0]
_dupB = cmds.parent(_dupB, _dupGrp)[0]
# 두 트랜스폼의 짧은 이름이 실제로 같은지 먼저 확인한다 -- Maya가 이름을
# 자동으로 바꿔 버리면 이 테스트는 아무것도 검증하지 않는다.
assert _dupA.split("|")[-1] == _dupB.split("|")[-1], (_dupA, _dupB)
_axA = cmds.createNode("maroAxis", name="dupAxisA", parent=_dupA)
_axB = cmds.createNode("maroAxis", name="dupAxisB", parent=_dupB)
cmds.maroBindAxis(_axA, _dupA)
cmds.maroBindAxis(_axB, _dupB)
cmds.setAttr(_axA + ".jointName", "dup_root", type="string")
cmds.setAttr(_axB + ".jointName", "dup_child", type="string")
cmds.connectAttr(_axA + ".message", _axB + ".parentAxis")
try:
    urdf.export(os.path.join(tempfile.mkdtemp(), "dup.urdf"))
    raise AssertionError("duplicate link names should have been rejected")
except ValueError as _e:
    assert "dupBody" in str(_e), str(_e)

print("link name validation OK (empty and duplicate both rejected)")
```

- [ ] **Step 2: 실패를 확인한다**

`.py`만 고쳤고 `test_urdf_export.py`는 소스를 직접 import하므로 빌드는
필요 없다.

```bash
ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure
```

Expected: FAIL -- `AssertionError: unbound axis should have been rejected`
(지금은 조용히 빈 이름 링크를 만든다).

- [ ] **Step 3: 검증을 구현한다**

`python/maroUrdfExport.py`의 `buildAxisTree`에서, `jointName`을 검증하는
기존 줄:

```python
    emptyJointNames = [row["axisFullPath"] for row in axisRows if not row["jointName"]]
```

**바로 위**에 링크 이름 검증을 더한다:

```python
    # 링크 이름은 바인딩 타겟의 짧은 이름이다. 비어 있거나 서로 겹치면
    # <link name="">/중복 <link>가 되어 check_urdf가 거부하고, 런타임
    # /tf에서는 프레임이 안 나가거나 두 발행자가 한 프레임을 다투게 된다
    # (설계 스펙 §4).
    unbound = [row["axisFullPath"] for row in axisRows
               if not row.get("boundTargetPath")]
    if unbound:
        raise ValueError(
            "every axis must be bound to a transform before URDF export "
            "(the bound object's short name becomes the <link> name and the "
            "/tf frame id), missing on: {}".format(", ".join(sorted(unbound))))

    seenLinkNames = {}
    for row in axisRows:
        seenLinkNames.setdefault(
            _shortName(row["boundTargetPath"]), []).append(row["axisFullPath"])
    collisions = {n: paths for n, paths in seenLinkNames.items() if len(paths) > 1}
    if collisions:
        raise ValueError(
            "two or more axes resolve to the same <link> name; rename the "
            "bound transforms so their short names differ: {}".format(
                "; ".join("{} from {}".format(n, ", ".join(sorted(p)))
                          for n, p in sorted(collisions.items()))))
```

`_shortName`은 이 함수보다 **아래**에 정의돼 있지만 파이썬은 호출 시점에
이름을 찾으므로 문제없다(같은 모듈 안이다).

- [ ] **Step 4: 통과를 확인한다**

```bash
ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure
```

Expected: PASS -- `link name validation OK (empty and duplicate both rejected)`

- [ ] **Step 5: 커밋**

```bash
git add python/maroUrdfExport.py tests/maya/test_urdf_export.py && git commit -m "fix(urdf): reject empty and duplicate link names at export"
```

---

### Task 3: URDF와 TF가 같은 이름을 쓰는지 계약으로 고정

**Files:**
- Modify: `tests/maya/test_publish.py` (상단 import, 축 체인, TF 절 뒤)

**Interfaces:**
- Consumes: Task 1의 `linkName` 발행, Task 2의 검증.
- Produces: 없음(테스트 전용).

이 태스크가 이 계획의 **회귀 방어선**이다. 두 파이프라인이 다시 갈라지면
여기가 먼저 운다. 기대 프레임 이름을 하드코딩하지 않고 **URDF에서 읽어
온다** -- 그래야 계약 자체를 검사한다.

- [ ] **Step 1: import와 축 체인을 더한다**

`tests/maya/test_publish.py` 상단, `import maya.cmds as cmds` 아래에:

```python
_pythonDir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "python")
if _pythonDir not in sys.path:
    sys.path.insert(0, _pythonDir)

import maroUrdfExport as urdf  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402
```

`import sys` / `import tempfile`이 상단에 없으면 함께 더한다.

`cmds.setAttr(axisLinear + ".jointName", "axisPubLinear", type="string")`
줄 **바로 아래**에:

```python
    # URDF 내보내기는 루트가 정확히 하나인 축 트리를 요구한다. 이 씬은
    # 원래 서로 무관한 축 두 개였다 -- 아래 계약 테스트가 같은 씬에서
    # export를 부르려면 체인이어야 한다. 부모 연결은 발행 경로에 영향을
    # 주지 않는다(각 축은 그대로 자기 값을 낸다).
    cmds.connectAttr(axis + ".message", axisLinear + ".parentAxis")
```

- [ ] **Step 2: 계약 테스트를 더한다**

TF 절의 마지막 `print(f"tf round trip OK ...")` **바로 아래**에:

```python
        # --- 계약: URDF <link name>과 /tf child_frame_id가 통해야 한다.
        # 기대 이름을 하드코딩하지 않고 URDF에서 읽어 온다 -- 두 파이프라인이
        # 갈라지면 여기가 먼저 운다(설계 스펙 §6).
        contractDir = tempfile.mkdtemp(prefix="maro_tf_contract_")
        contractPath = os.path.join(contractDir, "contract.urdf")
        urdf.export(contractPath)
        contractRoot = ET.parse(contractPath).getroot()
        urdfLinks = {el.get("name") for el in contractRoot.findall("link")}
        urdfJoints = {el.get("name") for el in contractRoot.findall("joint")}

        # 피어가 실제로 받은 프레임 이름이 URDF의 링크 이름 중 하나다.
        assert EXPECTED_LINK in urdfLinks, (EXPECTED_LINK, sorted(urdfLinks))
        # 두 번째 축의 링크도 같은 규칙으로 나와야 한다.
        assert "segLinear" in urdfLinks, sorted(urdfLinks)
        # 링크 이름과 조인트 이름이 겹치면 이 계약이 우연히 통과할 수 있다.
        # 이 씬에서는 반드시 서로소여야 한다.
        assert not (urdfLinks & urdfJoints), (sorted(urdfLinks), sorted(urdfJoints))
        print(f"urdf/tf name contract OK (links={sorted(urdfLinks)})")
```

- [ ] **Step 3: 돌린다**

```bash
ctest --test-dir out/build -C Release -R maya_publish --output-on-failure
```

Expected: PASS. Task 1·2가 이미 들어가 있으므로 이 테스트는 RED로
시작하지 않는다.

- [ ] **Step 4: 계약이 실제로 무는지 확인한다**

`MaroRosRuntime.cpp`의 `t.child_frame_id = sample.linkName;`을 잠깐
`sample.jointName`으로 되돌리고 빌드 후 재실행한다.
Expected: FAIL -- TF 왕복이 타임아웃한다. 확인 후
`git checkout -- src/maro_plugin/MaroRosRuntime.cpp`로 되돌린다(이 파일은
Task 1에서 이미 커밋됐으므로 안전하다).

- [ ] **Step 5: 전체 스위트**

```bash
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure
```

Expected: 전부 PASS.

- [ ] **Step 6: 커밋**

```bash
git add tests/maya/test_publish.py && git commit -m "test(tf): pin the URDF link name / tf frame id contract"
```

---

## 자체 검토

**스펙 커버리지**

| 스펙 절 | 태스크 |
|---|---|
| §2-1 프레임 이름 = 링크 이름 | Task 1 Step 4·5 |
| §2-2 자세 = 로케이터 부모, 회전은 MFnTransform | Task 1 Step 4 |
| §2-3 enabled는 joint_states만 | Task 1 Step 3·5 |
| §2-4 발행 조건 | Task 1 Step 4·5 |
| §3 이름 규칙 양쪽 고정 | Task 3(계약 테스트가 그 고정이다) |
| §4 빈 이름 / 중복 검증 | Task 2 |
| §5 joint_states·LiDAR frame_id 불변 | 어느 태스크도 안 건드림 |
| §6 테스트 표 | 자세 출처: T1 Step 8 미끼 / 검증 2종: T2 / 이름 계약: T3 / 나머지 2줄은 아래 참고 |

**§3의 "양쪽을 한 테스트에 고정"을 단위 비교가 아니라 계약 테스트로 푸는
이유**: C++이 계산한 링크 이름을 파이썬에서 직접 읽을 방법이 없다.
`maroListAxisNodes`에 필드를 하나 더하면 되지만 그건 `AXIS_FIELDS`를
바꿔 `sliceAxisRows`와 모든 호출부에 파급된다. Task 3은 대신 실제 계약
(발행된 프레임 이름 == URDF 링크 이름)을 직접 검사하므로 프록시보다 낫다.

**스펙 §6 중 태스크로 만들지 않은 두 줄**, 의도적이다:

- **스케일 오염 없음** -- 실측이 이미 `MFnTransform` 경로가 스케일에
  0.000000도 흔들린다는 것을 보였고, Task 1이 그 호출을 못박았다. 라이브
  브리지 테스트에 비균등 스케일 씬을 더하는 비용이 얻는 것보다 크다.
  **판단이므로 리뷰에서 뒤집혀도 좋다.**
- **`enabled=false` 왕복** -- 같은 이유(라이브 피어 시나리오가 하나 더
  늘어난다). Task 1 Step 5의 분기는 코드 리뷰로 확인 가능하다.

**타입 일관성**: `AxisSample.linkName`(std::string) -- T1 Step 3 정의,
Step 4에서 채움, Step 5에서 `t.child_frame_id`(std::string)에 대입.
`enabled`(bool) -- Step 3 정의, Step 4 채움, Step 5 조건.

**픽스처 함정 점검**: T1 Step 1이 로케이터 부모와 바인딩 타겟에 **다른**
자세를 준다. 이게 없으면 Step 4를 안 고쳐도 통과한다 -- 슬라이스 2의
"원점 실린더" 함정과 같은 구조.

## 알려진 부수 효과 (리뷰에서 명시적으로 확인할 것)

- `test_publish.py`의 씬이 축 두 개짜리 **체인**이 된다(Task 3 Step 1).
  기존 joint_states 검증 두 건은 영향받지 않아야 한다 -- 부모 연결은 각
  축이 자기 값을 내는 것과 무관하다.
- `enabled=false` 축이 이제 TF 프레임을 낸다. 기존 동작 변경이며 의도한
  것이다(설계 스펙 §2-3).
- 빈 `jointName` 축이 이제 TF 프레임을 낸다(전에는 통째로 건너뛰었다).
  `/joint_states`에는 여전히 안 나간다.
- 바인딩 없는 축이 이제 URDF 내보내기를 **실패시킨다**. 전에는 조용히
  무효 URDF가 나갔다.
