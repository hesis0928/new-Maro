# Maro URDF 내보내기 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `maroAxis` 체인과 capability 스택으로부터 URDF(`<link>`/`<joint>`)를 생성해 파일로 내보내는 도구를 Maro 메뉴에 추가한다.

**Architecture:** 새 파일 `python/maroUrdfExport.py` 하나. 새 C++ 코드 없음 — 기존 `maroListAxisNodes`/`cmds.xform`/`maroMayaToRos`만 조합한다. 순수 로직(트리 구성, 관절 타입 매핑, origin 행렬 계산, XML 조립)과 씬 조회(capability 값/월드 트랜스폼 읽기)를 파일 안에서 명확히 분리해, 앞쪽 로직은 mayapy 배치에서 딕셔너리/튜플만으로 검증한다.

**Tech Stack:** Python, `maya.api.OpenMaya`(순수 행렬/쿼터니언 연산 라이브러리로만 사용), `xml.etree.ElementTree`.

## Global Constraints

- 새 C++ 커맨드/DG 어트리뷰트를 추가하지 않는다.
- 관절 원점(`<origin>`)은 축 로케이터 자신의 실제 월드 트랜스폼에서, 관절 축(`<axis>`)은 `conventionAxis`가 가리키는 로케이터의 **로컬** 축에서 가져온다 — 별도 좌표 변환 없이 그대로 X=(1,0,0)/Y=(0,1,0)/Z=(0,0,1) 중 하나로 매핑한다(설계 스펙 §3.3).
- 부모 없는 축이 정확히 하나가 아니면(0개 또는 2개 이상) 내보내기를 거부하고 후보 축 목록을 담은 에러를 낸다.
- `jointName`이 빈 축이 있으면 내보내기를 거부하고 어느 축인지 에러로 알린다.
- 루트 축에는 `<origin>`을 계산하지 않는다 — 루트는 조인트 없는 `<link>`만 만든다(URDF 자체에 루트 링크의 월드 배치를 담는 필드가 없다, 설계 스펙 §3.2 정정 참고).
- `capabilityIn[].capMin`/`capMax`(각도·거리 어트리뷰트)는 `cmds.getAttr`이 **현재 UI 단위**로 답한다 — 반드시 `MAngle.uiUnit()`/`MDistance.uiUnit()`으로 감싸 라디안/미터로 명시 변환한 뒤에만 순수 함수에 넘긴다(Tech Diag가 이미 겪은 것과 같은 함정, `2026-08-26-maro-tech-diag-design.md` §3.1의 선례).
- 관절 타입별 URDF 요소: `fixed`는 `<axis>`/`<limit>` 둘 다 안 낸다. `continuous`는 `<axis>`만 내고 `<limit>`은 안 낸다. `revolute`/`prismatic`은 `<axis>`와 `<limit>` 둘 다 낸다. `translationLimit`이 없는 `prismatic`은 `lower=-1.0e6 upper=1.0e6`(무제한 관례)로 채운다. `effort`/`velocity`는 항상 관례적 상수(`1000`/`10`)다.
- 첫 슬라이스는 시각/충돌 메쉬(`<visual>`/`<collision>`)를 만들지 않는다 — `<link>`는 이름만 있는 빈 요소다.
- 트리거는 Maro 메뉴의 새 항목 "URDF 내보내기..." → 클릭 즉시 `cmds.fileDialog2`로 저장 경로를 묻는다. 별도 창/미리보기 없음.

---

### Task 1: 축 트리 구성 + 관절 타입 매핑 (순수 함수)

**Files:**
- Create: `python/maroUrdfExport.py`
- Test: `tests/maya/test_urdf_export.py`
- Modify: `tests/CMakeLists.txt` (새 테스트를 "플러그인만 있으면 되는" 그룹에 등록)

**Interfaces:**
- Produces: `buildAxisTree(axisRows) -> (rootAxisFullPath: str, childrenByParent: dict[str, list[str]])`, `axisVectorForConvention(conventionAxis: int) -> tuple[float, float, float]`, `jointType(capabilityRows: list[dict]) -> dict`(`{"type": str, "lower": float|None, "upper": float|None, "mimic": dict|None}`). Task 4가 이 세 함수를 그대로 가져다 쓴다.

- [ ] **Step 1: `python/maroUrdfExport.py` 작성 (Task 1 부분)**

```python
"""Maro URDF 내보내기 -- maroAxis 체인과 capability 스택으로부터 URDF(XML)를
생성한다(설계 스펙 2026-09-02-maro-urdf-export-design.md).

새 C++ 코드 없음 -- 기존 maroListAxisNodes/cmds.xform/maroMayaToRos만
조합한다. 이 파일 위쪽의 함수들(buildAxisTree/axisVectorForConvention/
jointType/computeRelativeOrigin/buildUrdfXml)은 Maya 씬을 조회하지 않는
순수 함수다 -- mayapy 배치에서 실제 씬 없이 딕셔너리/튜플만으로 검증
가능하다. 씬을 조회하는 부분과 UI 배선은 이 파일 아래쪽(Task 4)에서
추가된다.
"""


def buildAxisTree(axisRows):
    """axisRows: 각 항목이 최소 "axisFullPath"/"parentAxisPath"/"jointName"
    키를 갖는 딕셔너리 목록(maroListAxisNodes()를 슬라이스한 것).

    (rootAxisFullPath, childrenByParent) 튜플을 돌려준다. childrenByParent는
    parentAxisPath -> [axisFullPath, ...] 매핑이다(부모가 없는 축은 이
    매핑에 나타나지 않는다 -- 그게 곧 루트).

    부모가 빈 축이 정확히 하나가 아니면 ValueError. jointName이 빈 축이
    있으면 ValueError(어느 축인지 메시지에 포함).
    """
    roots = [row["axisFullPath"] for row in axisRows if not row["parentAxisPath"]]
    if len(roots) != 1:
        raise ValueError(
            "expected exactly one root axis (no parentAxisPath), found {}: {}".format(
                len(roots), roots))

    emptyJointNames = [row["axisFullPath"] for row in axisRows if not row["jointName"]]
    if emptyJointNames:
        raise ValueError(
            "every axis needs a non-empty jointName before URDF export, missing on: {}".format(
                emptyJointNames))

    childrenByParent = {}
    for row in axisRows:
        parent = row["parentAxisPath"]
        if parent:
            childrenByParent.setdefault(parent, []).append(row["axisFullPath"])

    return roots[0], childrenByParent


_AXIS_VECTORS = {0: (1.0, 0.0, 0.0), 1: (0.0, 1.0, 0.0), 2: (0.0, 0.0, 1.0)}


def axisVectorForConvention(conventionAxis):
    """conventionAxis(0=X 1=Y 2=Z)를 관절 프레임 안에서의 단위 축 벡터로
    바꾼다. origin이 이미 로케이터의 자세를 관절 프레임으로 확정하므로
    별도 좌표 변환이 필요 없다(설계 스펙 §3.3)."""
    if conventionAxis not in _AXIS_VECTORS:
        raise ValueError("conventionAxis must be 0, 1, or 2, got {}".format(conventionAxis))
    return _AXIS_VECTORS[conventionAxis]


def jointType(capabilityRows):
    """capabilityRows: 이 축 하나의 capability 목록. 각 항목은 최소
    "capType"(int, 0=rotation 1=limit 4=translation 5=translationLimit
    6=coupling-각도 7=coupling-선형) 키를 갖는다. capType 1/5 항목은
    추가로 "enabled"(bool, 이 축의 conventionAxis 성분에 대해 이미 해석된
    값)와 "min"/"max"(float, 라디안 또는 미터로 이미 단위 변환된 값)를
    갖는다. capType 6/7 항목은 추가로 "ratio"(float), "offset"(float),
    "sourceJointName"(str)을 갖는다.

    {"type": "revolute"|"continuous"|"prismatic"|"fixed",
     "lower": float|None, "upper": float|None,
     "mimic": {"joint": str, "multiplier": float, "offset": float}|None}
    을 돌려준다. lower/upper는 "type"에 맞는 단위다(revolute/continuous는
    라디안, prismatic은 미터).

    이 함수는 Maya를 부르지 않는다 -- 호출자가 conventionAxis 성분 해석과
    단위 변환을 이미 끝내 둔 순수 데이터만 받는다.
    """
    hasRotation = any(r["capType"] == 0 for r in capabilityRows)
    hasTranslation = any(r["capType"] == 4 for r in capabilityRows)
    couplingRow = next((r for r in capabilityRows if r["capType"] in (6, 7)), None)
    limitRow = next(
        (r for r in capabilityRows if r["capType"] == 1 and r.get("enabled")), None)
    translationLimitRow = next(
        (r for r in capabilityRows if r["capType"] == 5 and r.get("enabled")), None)

    mimic = None
    if couplingRow is not None:
        mimic = {
            "joint": couplingRow["sourceJointName"],
            "multiplier": couplingRow["ratio"],
            "offset": couplingRow["offset"],
        }

    isAngularDriver = hasRotation or (couplingRow is not None and couplingRow["capType"] == 6)
    isLinearDriver = hasTranslation or (couplingRow is not None and couplingRow["capType"] == 7)

    if isAngularDriver:
        if limitRow is not None:
            return {"type": "revolute", "lower": limitRow["min"], "upper": limitRow["max"],
                    "mimic": mimic}
        return {"type": "continuous", "lower": None, "upper": None, "mimic": mimic}

    if isLinearDriver:
        if translationLimitRow is not None:
            return {"type": "prismatic", "lower": translationLimitRow["min"],
                    "upper": translationLimitRow["max"], "mimic": mimic}
        # URDF는 prismatic에 <limit>이 필수다 -- translationLimit이 없으면
        # "사실상 무제한"이라는 관례로 아주 넓은 값을 채운다(설계 스펙 §3.4).
        return {"type": "prismatic", "lower": -1.0e6, "upper": 1.0e6, "mimic": mimic}

    return {"type": "fixed", "lower": None, "upper": None, "mimic": None}
```

- [ ] **Step 2: `tests/maya/test_urdf_export.py` 작성 (Task 1 부분)**

이 프로젝트의 순수 함수 테스트 관례를 따른다(`tests/maya/test_tech_diag.py`와 동일 형식 — `maya.standalone` 초기화, 플러그인 로드는 이번 태스크에선 안 씀, 소스 디렉터리를 `sys.path`에 넣고 직접 import).

```python
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

_pythonDir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "python")
if _pythonDir not in sys.path:
    sys.path.insert(0, _pythonDir)

import maroUrdfExport as urdf  # noqa: E402

# --- buildAxisTree ---
threeAxisRows = [
    {"axisFullPath": "|root", "parentAxisPath": "", "jointName": "j_root"},
    {"axisFullPath": "|child1", "parentAxisPath": "|root", "jointName": "j_child1"},
    {"axisFullPath": "|child2", "parentAxisPath": "|root", "jointName": "j_child2"},
]
root, children = urdf.buildAxisTree(threeAxisRows)
assert root == "|root", root
assert children == {"|root": ["|child1", "|child2"]}, children
print("buildAxisTree basic tree OK")

try:
    urdf.buildAxisTree([
        {"axisFullPath": "|a", "parentAxisPath": "", "jointName": "ja"},
        {"axisFullPath": "|b", "parentAxisPath": "", "jointName": "jb"},
    ])
    raise AssertionError("expected ValueError for two roots")
except ValueError as e:
    assert "found 2" in str(e), e
print("buildAxisTree rejects multiple roots OK")

try:
    urdf.buildAxisTree([
        {"axisFullPath": "|a", "parentAxisPath": "|b", "jointName": "ja"},
        {"axisFullPath": "|b", "parentAxisPath": "|a", "jointName": "jb"},
    ])
    raise AssertionError("expected ValueError for zero roots")
except ValueError as e:
    assert "found 0" in str(e), e
print("buildAxisTree rejects zero roots OK")

try:
    urdf.buildAxisTree([
        {"axisFullPath": "|root", "parentAxisPath": "", "jointName": ""},
    ])
    raise AssertionError("expected ValueError for empty jointName")
except ValueError as e:
    assert "|root" in str(e), e
print("buildAxisTree rejects empty jointName OK")

# --- axisVectorForConvention ---
assert urdf.axisVectorForConvention(0) == (1.0, 0.0, 0.0)
assert urdf.axisVectorForConvention(1) == (0.0, 1.0, 0.0)
assert urdf.axisVectorForConvention(2) == (0.0, 0.0, 1.0)
try:
    urdf.axisVectorForConvention(3)
    raise AssertionError("expected ValueError for out-of-range conventionAxis")
except ValueError:
    pass
print("axisVectorForConvention OK")

# --- jointType ---
result = urdf.jointType([{"capType": 0}])
assert result == {"type": "continuous", "lower": None, "upper": None, "mimic": None}, result

result = urdf.jointType([
    {"capType": 0},
    {"capType": 1, "enabled": True, "min": -1.0, "max": 1.0},
])
assert result == {"type": "revolute", "lower": -1.0, "upper": 1.0, "mimic": None}, result

# limit 있지만 이 축 성분에서는 꺼져 있으면 continuous로 취급.
result = urdf.jointType([
    {"capType": 0},
    {"capType": 1, "enabled": False, "min": -1.0, "max": 1.0},
])
assert result["type"] == "continuous", result

result = urdf.jointType([{"capType": 4}])
assert result == {"type": "prismatic", "lower": -1.0e6, "upper": 1.0e6, "mimic": None}, result

result = urdf.jointType([
    {"capType": 4},
    {"capType": 5, "enabled": True, "min": 0.0, "max": 0.5},
])
assert result == {"type": "prismatic", "lower": 0.0, "upper": 0.5, "mimic": None}, result

result = urdf.jointType([
    {"capType": 6, "ratio": 2.0, "offset": 0.1, "sourceJointName": "shoulder"},
])
assert result["type"] == "continuous", result
assert result["mimic"] == {"joint": "shoulder", "multiplier": 2.0, "offset": 0.1}, result

result = urdf.jointType([
    {"capType": 7, "ratio": 1.5, "offset": 0.0, "sourceJointName": "elbow"},
])
assert result["type"] == "prismatic", result
assert result["mimic"] == {"joint": "elbow", "multiplier": 1.5, "offset": 0.0}, result

result = urdf.jointType([])
assert result == {"type": "fixed", "lower": None, "upper": None, "mimic": None}, result

result = urdf.jointType([{"capType": 2}, {"capType": 3}])
assert result["type"] == "fixed", result
print("jointType OK")

maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
```

- [ ] **Step 3: `tests/CMakeLists.txt`에 새 테스트 등록**

`tests/CMakeLists.txt`의 `foreach(maya_test ...)` 목록(플러그인만 있으면 되는 그룹) 끝에 `urdf_export`를 추가한다:

```cmake
    foreach(maya_test load axis_node binding capability_stack delete_rules
                      robustness diag_boad diag_onfix diag_book
                      diag_book_cross_session diag_remedy
                      diag_degraded diag_degraded_remedy diag_thread
                      panel_commands main_window main_menu journal remedy_capture
                      remedy_availability remedy_ambiguous_names
                      main_thread_queue remedy_apply sentinel lidar_node
                      ros_proxy_commands ros_proxy_sync axis_editor_commands
                      dag_menu tech_diag point_cloud_node lidar_commands
                      lidar_menu skeleton_upload settings_panel urdf_export)
```

이 태스크는 실제로는 플러그인을 로드하지 않지만(순수 함수만 테스트), 이 그룹에 넣어도 무해하다 — 다른 항목들과 같은 `MARO_PLUGIN_PATH`/`MARO_DIAG_BOOK_DIR` 격리를 받을 뿐 강제로 쓰지 않아도 된다. 다음 태스크(Task 4)가 이 파일에 실제 플러그인 로드 코드를 추가하면 이 격리가 그때부터 의미를 갖는다.

- [ ] **Step 4: 빌드 후 새 테스트만 실행**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure -R maya_urdf_export
```

Expected: PASS, 모든 `print(...)` 라인 출력.

- [ ] **Step 5: 전체 스위트로 회귀 확인**

```powershell
ctest --test-dir out/build -C Release --output-on-failure
```

Expected: 기존 테스트 전부 그대로 PASS.

- [ ] **Step 6: 커밋**

```bash
git add python/maroUrdfExport.py tests/maya/test_urdf_export.py tests/CMakeLists.txt
git commit -m "feat(urdf): add axis-tree building and joint-type mapping (pure functions)"
```

---

### Task 2: 관절 원점(origin) 계산 — 순수 행렬 연산

**⚠️ 이 태스크는 이 계획에서 가장 틀리기 쉬운 부분이다.** URDF의 `<origin rpy="r p y">`는 "고정축(월드/부모 기준) X 다음 Y 다음 Z" 순서(extrinsic XYZ)로 정의된다. 이건 오일러각 동치 관계상 intrinsic Z-Y-X(먼저 몸체 Z, 그다음 새 Y, 그다음 새 X)와 수학적으로 같은 세 각도를 낸다. `maya.api.OpenMaya`의 `MEulerRotation`/`MTransformationMatrix`는 기본적으로 이 순서를 안 쓰므로, **`kZYX`로 명시적으로 재정렬해야 한다** — 이 문서에 적힌 코드를 그대로 베끼지 말고, 아래 Step 2의 독립 검증 테스트가 실제로 통과하는지 반드시 확인할 것. 통과하지 않으면 이 문서의 가정(`kZYX`)이 틀린 것이니, `kXYZ`나 다른 조합을 시도해 **독립 검증 쪽(표준 회전 행렬 공식)이 요구하는 값**에 맞을 때까지 구현을 고친다. 절대로 독립 검증 테스트의 기대값 쪽을 약화시키지 말 것 — 그 공식은 URDF 스펙과 초등 삼각함수에서 직접 유도한 것이라 흔들릴 이유가 없다.

**Files:**
- Modify: `python/maroUrdfExport.py` (Task 1 코드 아래에 추가)
- Modify: `tests/maya/test_urdf_export.py` (Task 1 테스트 아래에 추가)

**Interfaces:**
- Consumes: 없음(독립).
- Produces: `computeRelativeOrigin(parentPosRos: tuple[float,float,float], parentQuatRos: tuple[float,float,float,float], childPosRos: tuple, childQuatRos: tuple) -> tuple[tuple[float,float,float], tuple[float,float,float]]`(반환값은 `(xyz, rpy)`, xyz는 미터, rpy는 라디안). Task 4가 이 함수를 그대로 가져다 쓴다.

- [ ] **Step 1: `computeRelativeOrigin` 추가**

`python/maroUrdfExport.py` 맨 위, 기존 내용 앞에 import를 추가하고(파일 맨 위 한 줄):

```python
import maya.api.OpenMaya as om2
```

Task 1의 함수들 뒤에 추가한다:

```python
def computeRelativeOrigin(parentPosRos, parentQuatRos, childPosRos, childQuatRos):
    """parentPosRos/childPosRos: (x, y, z) 미터. parentQuatRos/childQuatRos:
    (x, y, z, w) -- 전부 이미 ROS 프레임으로 변환된 값(cmds.maroMayaToRos의
    출력, 호출자가 이미 변환해 넘긴다).

    부모 기준 자식의 상대 변환을 (xyz, rpy) 튜플로 돌려준다 -- xyz는 미터,
    rpy는 라디안(URDF의 <origin xyz= rpy=>가 그대로 받는 값, 고정축
    X->Y->Z 순서). 이 함수는 Maya 씬을 조회하지 않는다 -- maya.api.OpenMaya를
    순수 4x4 행렬/쿼터니언 연산 라이브러리로만 쓴다(설계 스펙 §3.2).
    """
    def _matrix(pos, quat):
        t = om2.MTransformationMatrix()
        t.setTranslation(om2.MVector(*pos), om2.MSpace.kWorld)
        t.setRotation(om2.MQuaternion(*quat))
        return t.asMatrix()

    parentMatrix = _matrix(parentPosRos, parentQuatRos)
    childMatrix = _matrix(childPosRos, childQuatRos)
    # Maya는 행벡터 관례(v' = v * M, 왼쪽에서 오른쪽으로 적용)를 쓴다 --
    # "부모 기준 자식"은 자식을 먼저 적용한 뒤 부모의 역변환을 적용한
    # 것이다.
    relative = childMatrix * parentMatrix.inverse()

    relativeXform = om2.MTransformationMatrix(relative)
    xyz = relativeXform.translation(om2.MSpace.kWorld)

    euler = relativeXform.rotation(asQuaternion=False)
    euler = euler.reorder(om2.MEulerRotation.kZYX)
    rpy = (euler.x, euler.y, euler.z)

    return (xyz.x, xyz.y, xyz.z), rpy
```

- [ ] **Step 2: 독립 검증 테스트 추가**

`tests/maya/test_urdf_export.py`의 `maya.standalone.uninitialize()` 호출 **앞**(Task 1이 만든 마지막 검증 줄, `print("jointType OK")` 뒤)에 추가한다:

```python
import math

import maya.api.OpenMaya as om2

# --- computeRelativeOrigin: 항등/평행이동만 있는 쉬운 경우 ---
xyz, rpy = urdf.computeRelativeOrigin((0, 0, 0), (0, 0, 0, 1), (0, 0, 0), (0, 0, 0, 1))
assert xyz == (0.0, 0.0, 0.0), xyz
assert all(abs(v) < 1e-9 for v in rpy), rpy

xyz, rpy = urdf.computeRelativeOrigin(
    (0, 0, 0), (0, 0, 0, 1), (1.0, 2.0, 3.0), (0, 0, 0, 1))
assert all(abs(a - b) < 1e-9 for a, b in zip(xyz, (1.0, 2.0, 3.0))), xyz
assert all(abs(v) < 1e-9 for v in rpy), rpy
print("computeRelativeOrigin identity/translation OK")

# --- computeRelativeOrigin: 회전이 URDF의 rpy 관례(고정축 X->Y->Z)와
# 실제로 일치하는지 독립 검증 ---
# 이 테스트가 실패하면 구현의 kZYX 가정이 틀렸다는 뜻이다 -- 아래 기대값을
# 바꾸지 말고, computeRelativeOrigin 안의 재정렬 순서(kZYX)를 다른 조합으로
# 바꿔서 이 테스트를 통과시켜라.
roll, pitch, yaw = 0.3, 0.5, 0.7

# 1) om2의 kZYX(intrinsic Z->Y->X)로 만든 회전을 자식에 주고, 그걸 다시
#    computeRelativeOrigin으로 뽑아냈을 때 같은 세 각도가 나오는지(자기
#    일관성 -- 이것만으로는 kZYX가 URDF와 같다는 것까지는 증명 못 한다,
#    아래 2)가 그걸 증명한다).
childQuat = om2.MEulerRotation(roll, pitch, yaw, om2.MEulerRotation.kZYX).asQuaternion()
_, decodedRpy = urdf.computeRelativeOrigin(
    (0, 0, 0), (0, 0, 0, 1), (0, 0, 0), (childQuat.x, childQuat.y, childQuat.z, childQuat.w))
assert abs(decodedRpy[0] - roll) < 1e-9, decodedRpy
assert abs(decodedRpy[1] - pitch) < 1e-9, decodedRpy
assert abs(decodedRpy[2] - yaw) < 1e-9, decodedRpy

# 2) URDF 스펙이 정의하는 "고정축 X->Y->Z" 회전 행렬을 초등 삼각함수
#    공식(R = Rz(yaw) @ Ry(pitch) @ Rx(roll), 열벡터 관례)으로 직접
#    조립해서, om2가 kZYX로 만든 행렬과 실제로 같은지 확인한다 -- om2
#    라이브러리에 대한 가정이 아니라 URDF 스펙 자체에서 나온 독립적인
#    기준이다.
def _rotX(a):
    c, s = math.cos(a), math.sin(a)
    return [[1, 0, 0], [0, c, -s], [0, s, c]]


def _rotY(a):
    c, s = math.cos(a), math.sin(a)
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]]


def _rotZ(a):
    c, s = math.cos(a), math.sin(a)
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def _matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


expectedColumnVectorMatrix = _matmul(_matmul(_rotZ(yaw), _rotY(pitch)), _rotX(roll))

m = om2.MEulerRotation(roll, pitch, yaw, om2.MEulerRotation.kZYX).asMatrix()
# om2.MMatrix는 행벡터 관례를 쓴다 -- 열벡터 관례로 만든 위 공식과
# 비교하려면 전치해야 한다.
gotRowVectorMatrix = [[m.getElement(row, col) for col in range(3)] for row in range(3)]
gotColumnVectorMatrix = [[gotRowVectorMatrix[col][row] for col in range(3)] for row in range(3)]

for i in range(3):
    for j in range(3):
        assert abs(expectedColumnVectorMatrix[i][j] - gotColumnVectorMatrix[i][j]) < 1e-9, (
            "row {} col {}: URDF-spec formula gives {}, om2 kZYX gives {} -- "
            "the reorder() target in computeRelativeOrigin is wrong, fix it "
            "(don't weaken this assertion)".format(
                i, j, expectedColumnVectorMatrix[i][j], gotColumnVectorMatrix[i][j]))
print("computeRelativeOrigin rotation matches URDF rpy convention (independently verified) OK")
```

- [ ] **Step 3: 빌드 후 새 테스트 실행, 특히 독립 검증 부분 주목**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure -R maya_urdf_export
```

Expected: `computeRelativeOrigin rotation matches URDF rpy convention (independently verified) OK`가 출력된다. **이 줄이 안 뜨거나 assert가 실패하면, `computeRelativeOrigin`의 `euler.reorder(om2.MEulerRotation.kZYX)`를 다른 순서 상수(`kXYZ`, `kZXY` 등)로 바꿔 가며 이 테스트가 통과할 때까지 반복하라.** 통과할 때까지 이 태스크를 완료로 표시하지 말 것.

- [ ] **Step 4: 전체 스위트로 회귀 확인**

```powershell
ctest --test-dir out/build -C Release --output-on-failure
```

- [ ] **Step 5: 커밋**

```bash
git add python/maroUrdfExport.py tests/maya/test_urdf_export.py
git commit -m "feat(urdf): add relative-origin matrix computation, independently verified against URDF's rpy convention"
```

---

### Task 3: URDF XML 조립 (순수 함수)

**Files:**
- Modify: `python/maroUrdfExport.py` (Task 1/2 코드 아래에 추가)
- Modify: `tests/maya/test_urdf_export.py`

**Interfaces:**
- Consumes: 없음(독립 — 이미 계산된 링크/조인트 딕셔너리만 받는다).
- Produces: `buildUrdfXml(robotName: str, links: list[dict], joints: list[dict]) -> xml.etree.ElementTree.Element`. Task 4가 이 함수를 그대로 가져다 쓴다. `links`의 각 항목은 `{"name": str}`. `joints`의 각 항목은 `{"name": str, "type": str, "parent": str, "child": str, "originXyz": tuple[float,float,float], "originRpy": tuple[float,float,float], "axis": tuple[float,float,float]|None, "lower": float|None, "upper": float|None, "mimic": dict|None}`.

- [ ] **Step 1: `buildUrdfXml` 추가**

`python/maroUrdfExport.py` 맨 위에 import 한 줄 추가(기존 `import maya.api.OpenMaya as om2` 아래):

```python
import xml.etree.ElementTree as ET
```

Task 2의 `computeRelativeOrigin` 뒤에 추가한다:

```python
def buildUrdfXml(robotName, links, joints):
    """links: [{"name": str}, ...]. joints: [{"name": str, "type": str,
    "parent": str, "child": str, "originXyz": (x,y,z), "originRpy": (r,p,y),
    "axis": (x,y,z)|None, "lower": float|None, "upper": float|None,
    "mimic": {"joint": str, "multiplier": float, "offset": float}|None}, ...].

    <robot name=robotName>를 루트로 하는 xml.etree.ElementTree.Element를
    돌려준다 -- 파일 쓰기는 호출자 몫이다(이 함수는 트리만 조립하는 순수
    함수). "fixed" 타입은 <axis>/<limit>을 안 낸다. "continuous" 타입은
    <axis>는 내지만 <limit>은 안 낸다.
    """
    robot = ET.Element("robot", name=robotName)
    for link in links:
        ET.SubElement(robot, "link", name=link["name"])

    for joint in joints:
        jointEl = ET.SubElement(robot, "joint", name=joint["name"], type=joint["type"])
        ET.SubElement(jointEl, "parent", link=joint["parent"])
        ET.SubElement(jointEl, "child", link=joint["child"])
        ox, oy, oz = joint["originXyz"]
        orr, orp, ory = joint["originRpy"]
        ET.SubElement(jointEl, "origin",
                      xyz="{:.6f} {:.6f} {:.6f}".format(ox, oy, oz),
                      rpy="{:.6f} {:.6f} {:.6f}".format(orr, orp, ory))
        if joint["type"] != "fixed":
            ax, ay, az = joint["axis"]
            ET.SubElement(jointEl, "axis", xyz="{:.0f} {:.0f} {:.0f}".format(ax, ay, az))
        if joint["type"] in ("revolute", "prismatic"):
            ET.SubElement(jointEl, "limit",
                          lower="{:.6f}".format(joint["lower"]),
                          upper="{:.6f}".format(joint["upper"]),
                          effort="1000", velocity="10")
        if joint["mimic"] is not None:
            ET.SubElement(jointEl, "mimic", joint=joint["mimic"]["joint"],
                          multiplier="{:.6f}".format(joint["mimic"]["multiplier"]),
                          offset="{:.6f}".format(joint["mimic"]["offset"]))
    return robot
```

- [ ] **Step 2: 테스트 추가**

`tests/maya/test_urdf_export.py`의 `maya.standalone.uninitialize()` 앞에 추가한다:

```python
# --- buildUrdfXml ---
robotEl = urdf.buildUrdfXml(
    "test_robot",
    links=[{"name": "base"}, {"name": "arm1"}],
    joints=[{
        "name": "j1", "type": "revolute", "parent": "base", "child": "arm1",
        "originXyz": (0.1, 0.2, 0.3), "originRpy": (0.0, 0.0, 0.0),
        "axis": (1.0, 0.0, 0.0), "lower": -1.0, "upper": 1.0, "mimic": None,
    }])
assert robotEl.get("name") == "test_robot"
links = robotEl.findall("link")
assert [l.get("name") for l in links] == ["base", "arm1"], links
joints = robotEl.findall("joint")
assert len(joints) == 1, joints
j = joints[0]
assert j.get("name") == "j1" and j.get("type") == "revolute", j.attrib
assert j.find("parent").get("link") == "base"
assert j.find("child").get("link") == "arm1"
assert j.find("origin").get("xyz") == "0.100000 0.200000 0.300000"
assert j.find("axis").get("xyz") == "1 0 0"
limitEl = j.find("limit")
assert limitEl.get("lower") == "-1.000000" and limitEl.get("upper") == "1.000000"
assert limitEl.get("effort") == "1000" and limitEl.get("velocity") == "10"
assert j.find("mimic") is None
print("buildUrdfXml revolute joint OK")

# fixed 조인트는 axis/limit이 없어야 한다.
robotEl = urdf.buildUrdfXml(
    "test_robot2", links=[{"name": "a"}, {"name": "b"}],
    joints=[{"name": "jf", "type": "fixed", "parent": "a", "child": "b",
             "originXyz": (0, 0, 0), "originRpy": (0, 0, 0),
             "axis": None, "lower": None, "upper": None, "mimic": None}])
jf = robotEl.find("joint")
assert jf.find("axis") is None
assert jf.find("limit") is None
print("buildUrdfXml fixed joint has no axis/limit OK")

# continuous 조인트는 axis는 있지만 limit은 없어야 한다.
robotEl = urdf.buildUrdfXml(
    "test_robot3", links=[{"name": "a"}, {"name": "b"}],
    joints=[{"name": "jc", "type": "continuous", "parent": "a", "child": "b",
             "originXyz": (0, 0, 0), "originRpy": (0, 0, 0),
             "axis": (0.0, 1.0, 0.0), "lower": None, "upper": None, "mimic": None}])
jc = robotEl.find("joint")
assert jc.find("axis") is not None
assert jc.find("limit") is None
print("buildUrdfXml continuous joint has axis but no limit OK")

# mimic이 있으면 <mimic>이 나와야 한다.
robotEl = urdf.buildUrdfXml(
    "test_robot4", links=[{"name": "a"}, {"name": "b"}],
    joints=[{"name": "jm", "type": "revolute", "parent": "a", "child": "b",
             "originXyz": (0, 0, 0), "originRpy": (0, 0, 0),
             "axis": (1.0, 0.0, 0.0), "lower": -1.0, "upper": 1.0,
             "mimic": {"joint": "source_j", "multiplier": 2.0, "offset": 0.1}}])
mimicEl = robotEl.find("joint").find("mimic")
assert mimicEl.get("joint") == "source_j"
assert mimicEl.get("multiplier") == "2.000000"
assert mimicEl.get("offset") == "0.100000"
print("buildUrdfXml mimic joint OK")
```

- [ ] **Step 3: 빌드 후 새 테스트 실행**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure -R maya_urdf_export
```

- [ ] **Step 4: 전체 스위트로 회귀 확인**

```powershell
ctest --test-dir out/build -C Release --output-on-failure
```

- [ ] **Step 5: 커밋**

```bash
git add python/maroUrdfExport.py tests/maya/test_urdf_export.py
git commit -m "feat(urdf): add pure URDF XML assembly"
```

---

### Task 4: 씬 조회 + 오케스트레이션 + 메뉴 배선

**Files:**
- Modify: `python/maroUrdfExport.py` (Task 1-3 코드 아래에 추가)
- Modify: `python/maroMenu.py`
- Modify: `src/maro_plugin/CMakeLists.txt` (`MARO_PLUGIN_PY_MODULES`에 `maroUrdfExport` 추가)
- Modify: `tests/maya/test_urdf_export.py` (실제 씬을 만드는 종단 간 테스트 추가, 플러그인 로드 추가)
- Modify: `docs/maro-main-ui-manual-checklist.md`

**Interfaces:**
- Consumes: Task 1의 `buildAxisTree`/`axisVectorForConvention`/`jointType`, Task 2의 `computeRelativeOrigin`, Task 3의 `buildUrdfXml` — 전부 같은 파일 안이므로 import 불필요.
- Produces: `export(path=None) -> str|None`(모듈 함수, 메뉴가 인자 없이 호출; 성공하면 쓴 파일 경로, 실패/취소하면 `None`).

- [ ] **Step 1: 씬 조회 함수 추가**

`python/maroUrdfExport.py` 맨 위에 import 두 줄 추가(기존 `import maya.api.OpenMaya as om2` 근처):

```python
import os

import maya.cmds as cmds
```

파일 맨 끝에 추가한다:

```python
AXIS_FIELDS = 10
CAPABILITY_FIELDS = 5


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
        rows.append({
            "axisFullPath": f[0],
            "jointName": f[1],
            "boundTargetPath": f[2],
            "parentAxisPath": f[3],
            "conventionAxis": int(f[6]),
        })
    return rows


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
            "capType": int(f[3]),
            "connected": f[4] == "1",
        })
    return rows


def _resolveCapabilityDetails(axis, capRow, conventionAxis):
    """capRow(logicalIndex/capabilityNodeName/capType)에 jointType()이 바로
    쓸 수 있는 값(min/max/enabled 또는 ratio/offset/sourceJointName)을
    채운다. 이 함수만 실제 씬을 조회한다(cmds.getAttr/listConnections).
    capMin/capMax는 현재 UI 단위로 오므로 MAngle/MDistance로 감싸 라디안/
    미터로 명시 변환한다(Tech Diag가 이미 겪은 단위 함정과 같은 이유)."""
    capType = capRow["capType"]
    idx = capRow["logicalIndex"]
    result = {"capType": capType}
    if capType == 1:
        enable = cmds.getAttr("{}.capabilityIn[{}].capEnable".format(axis, idx))[0]
        minRaw = cmds.getAttr("{}.capabilityIn[{}].capMin".format(axis, idx))[0]
        maxRaw = cmds.getAttr("{}.capabilityIn[{}].capMax".format(axis, idx))[0]
        result["enabled"] = bool(enable[conventionAxis])
        result["min"] = om2.MAngle(minRaw[conventionAxis], om2.MAngle.uiUnit()).asRadians()
        result["max"] = om2.MAngle(maxRaw[conventionAxis], om2.MAngle.uiUnit()).asRadians()
    elif capType == 5:
        enable = cmds.getAttr("{}.capabilityIn[{}].capEnable".format(axis, idx))[0]
        minRaw = cmds.getAttr("{}.capabilityIn[{}].capMin".format(axis, idx))[0]
        maxRaw = cmds.getAttr("{}.capabilityIn[{}].capMax".format(axis, idx))[0]
        result["enabled"] = bool(enable[conventionAxis])
        result["min"] = om2.MDistance(minRaw[conventionAxis], om2.MDistance.uiUnit()).asMeters()
        result["max"] = om2.MDistance(maxRaw[conventionAxis], om2.MDistance.uiUnit()).asMeters()
    elif capType in (6, 7):
        # aRatio/aOffset은 MFnUnitAttribute가 아니라 평범한 double이다
        # (MaroCapabilityNodes.h 확인) -- 단위 변환이 필요 없다.
        node = capRow["capabilityNodeName"]
        result["ratio"] = cmds.getAttr(node + ".ratio")
        result["offset"] = cmds.getAttr(node + ".offset")
        sourcePlugName = "sourceValue" if capType == 6 else "sourceValueLinear"
        sources = cmds.listConnections(
            node + "." + sourcePlugName, source=True, destination=False, plugs=False) or []
        if not sources:
            raise ValueError(
                "coupling node '{}' has no {} source connection".format(node, sourcePlugName))
        sourceAxis = cmds.ls(sources[0], long=True)[0]
        result["sourceJointName"] = cmds.getAttr(sourceAxis + ".jointName")
    return result


def _gatherAxisWorldTransformRos(axis):
    """axis(maroAxis 로케이터 셰이프)의 부모 트랜스폼의 월드 위치/회전을
    ROS 프레임 (pos, quat) 튜플로 돌려준다.

    maroAxis는 로케이터 **셰이프**다 -- 위치/회전은 실제로 그 부모
    트랜스폼에 있으므로(`createNode("maroAxis")`가 자동으로 만드는 부모),
    `cmds.listRelatives(axis, parent=True)`로 먼저 그 트랜스폼을 얻는다.

    위치는 `cmds.xform`이 아니라 `dagPath.inclusiveMatrix()` +
    `MTransformationMatrix.translation()`으로 얻는다 -- `cmds.xform`은
    **현재 UI 선형 단위**(사용자가 in/m 등으로 바꿀 수 있음)로 값을
    돌려주는데, `maroMayaToRos`(`MaroRosProxyCommands.cpp`)는 입력이
    Maya **내부** 단위(`MDistance::internalUnit()`, 항상 센티미터)라고
    전제한다 -- 두 단위가 다르면 사용자의 UI 단위 설정에 따라 조용히
    틀린 위치가 나온다. `maya.api.OpenMaya`는 이 UI 단위 계층 아래에서
    항상 내부 단위로만 동작하므로 이 함정 자체가 성립하지 않는다
    (`_resolveCapabilityDetails`가 `MAngle`/`MDistance`로 반대 방향
    함정 -- getAttr이 UI 단위로 주는 것 -- 을 막는 것과 쌍을 이룬다).

    회전은 MFnTransform.rotation(kWorld, asQuaternion=True)로 얻는다 --
    부모 변환까지 반영한 진짜 월드 회전임을 이 코드베이스가 이미
    실측으로 검증해 둔 방식이다(python/maroRosProxy.py의 같은 호출과
    그 옆 주석 참고)."""
    transformPath = cmds.listRelatives(axis, parent=True, fullPath=True)[0]
    dagPath = om2.MSelectionList().add(transformPath).getDagPath(0)
    worldMatrix = om2.MTransformationMatrix(dagPath.inclusiveMatrix())
    pos = worldMatrix.translation(om2.MSpace.kWorld)
    quat = om2.MFnTransform(dagPath).rotation(om2.MSpace.kWorld, asQuaternion=True)
    converted = cmds.maroMayaToRos(px=pos.x, py=pos.y, pz=pos.z,
                                    qx=quat.x, qy=quat.y, qz=quat.z, qw=quat.w)
    return (converted[0], converted[1], converted[2]), \
        (converted[3], converted[4], converted[5], converted[6])


def _shortName(fullPath):
    return fullPath.split("|")[-1]


def _buildRobotModel():
    """씬을 조회해 buildUrdfXml에 넘길 (links, joints)를 만든다."""
    axisRows = sliceAxisRows(cmds.maroListAxisNodes())
    if not axisRows:
        raise ValueError("scene has no maroAxis nodes to export")
    root, childrenByParent = buildAxisTree(axisRows)

    rowsByPath = {row["axisFullPath"]: row for row in axisRows}
    links = [{"name": _shortName(rowsByPath[root]["boundTargetPath"])}]
    joints = []

    def _visit(parentAxis):
        for childAxis in childrenByParent.get(parentAxis, []):
            childRow = rowsByPath[childAxis]
            capFlat = cmds.maroListAxisNodes(capabilities=childAxis)
            capRows = [
                _resolveCapabilityDetails(childAxis, row, childRow["conventionAxis"])
                for row in sliceCapabilityRows(capFlat)
            ]
            jt = jointType(capRows)

            parentPos, parentQuat = _gatherAxisWorldTransformRos(parentAxis)
            childPos, childQuat = _gatherAxisWorldTransformRos(childAxis)
            xyz, rpy = computeRelativeOrigin(parentPos, parentQuat, childPos, childQuat)

            links.append({"name": _shortName(childRow["boundTargetPath"])})
            joints.append({
                "name": childRow["jointName"],
                "type": jt["type"],
                "parent": _shortName(rowsByPath[parentAxis]["boundTargetPath"]),
                "child": _shortName(childRow["boundTargetPath"]),
                "originXyz": xyz,
                "originRpy": rpy,
                "axis": (axisVectorForConvention(childRow["conventionAxis"])
                         if jt["type"] != "fixed" else None),
                "lower": jt["lower"],
                "upper": jt["upper"],
                "mimic": jt["mimic"],
            })
            _visit(childAxis)

    _visit(root)
    return links, joints


def export(path=None):
    """Maro 메뉴의 "URDF 내보내기..." 항목이 부른다. path가 없으면
    cmds.fileDialog2로 저장 경로를 묻는다(path를 직접 주면 대화상자 없이
    그 경로에 바로 쓴다 -- 테스트/스크립트용). 성공하면 쓴 경로, 취소/
    실패하면 None을 돌려준다."""
    if path is None:
        results = cmds.fileDialog2(fileMode=0, fileFilter="URDF (*.urdf)",
                                    caption="Export URDF")
        if not results:
            return None
        path = results[0]
    try:
        links, joints = _buildRobotModel()
        robotName = os.path.splitext(os.path.basename(path))[0]
        robotElement = buildUrdfXml(robotName, links, joints)
        ET.indent(robotElement, space="  ")
        ET.ElementTree(robotElement).write(path, xml_declaration=True, encoding="utf-8")
        cmds.inViewMessage(amg="Maro: URDF exported to <hl>{}</hl>".format(path),
                            pos="topCenter", fade=True)
        return path
    except Exception as exc:  # noqa: BLE001 -- 메뉴 커맨드 문자열 경계
        cmds.warning("Maro: URDF export failed: {}".format(exc))
        return None
```

- [ ] **Step 2: `python/maroMenu.py`에 메뉴 항목 추가**

`python/maroMenu.py`에서 `"Skeleton Upload..."` 메뉴 항목 뒤, 다음 구분선 앞(현재 "ROS 연결 설정"/"환경설정" 자리였다가 설정 모달 작업으로 "환경설정..." 하나로 바뀐 그 구분선 앞)에 새 항목을 추가한다. 실제 파일을 열어 정확한 현재 위치(구분선과 "환경설정..." 항목의 순서)를 확인한 뒤, "Skeleton Upload..." 항목과 "환경설정..." 항목 사이에 구분선과 함께 삽입한다:

```python
    cmds.menuItem(divider=True, parent=MENU_NAME)
    cmds.menuItem(label="URDF 내보내기...",
                  command="import maroUrdfExport\nmaroUrdfExport.export()",
                  parent=MENU_NAME)
```

- [ ] **Step 3: `src/maro_plugin/CMakeLists.txt`에 새 모듈 스테이징 등록**

`MARO_PLUGIN_PY_MODULES` 목록에 `maroUrdfExport`를 추가한다(알파벳 순서상 `maroTechDiag`와 `maroSkeletonUpload` 근처, 정확한 위치는 크게 중요하지 않다 — 이 리포는 이미 완전한 알파벳 순서가 아니다):

```cmake
set(MARO_PLUGIN_PY_MODULES
    maroDagMenu
    maroDiagPanel
    maroLidarPanel
    maroMainWindow
    maroMenu
    maroObjectNodeEditor
    maroRosProxy
    maroSettingsPanel
    maroSkeletonUpload
    maroSingleObjectNodeEditor
    maroTechDiag
    maroUrdfExport
)
```

- [ ] **Step 4: 종단 간 테스트 추가 — 실제 2축 체인을 만들어 내보내기까지 확인**

`tests/maya/test_urdf_export.py` 맨 위(현재 `maya.standalone.initialize(name="python")` 직후, `_pythonDir` sys.path 삽입 앞)에 플러그인 로드를 추가한다:

```python
import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)
cmds.currentUnit(angle="rad")
cmds.currentUnit(linear="cm")
```

파일 맨 끝, `maya.standalone.uninitialize()` 앞에 추가한다:

```python
# --- 종단 간: 실제 2축 체인을 만들어 export()까지 확인 ---
import tempfile

rootMesh = cmds.polyCube(name="baseLink")[0]
childMesh = cmds.polyCube(name="armLink")[0]
cmds.xform(childMesh, worldSpace=True, translation=(0.0, 10.0, 0.0))

rootAxis = cmds.createNode("maroAxis")
cmds.maroBindAxis(rootAxis, rootMesh)
cmds.setAttr(rootAxis + ".jointName", "base_joint", type="string")
rootAxis = cmds.ls(rootAxis, long=True)[0]
# 루트 축은 origin 계산에 안 쓰이므로(설계 스펙 §3.2 정정) 로케이터
# 위치는 원점 그대로 둬도 무방하다 -- 실제로도 옮기지 않는다.

childAxis = cmds.createNode("maroAxis")
cmds.maroBindAxis(childAxis, childMesh)
cmds.setAttr(childAxis + ".jointName", "arm_joint", type="string")
childAxis = cmds.ls(childAxis, long=True)[0]
# 관절 위치를 실제 childMesh 위치에 맞춰 로케이터를 옮긴다(설계 스펙의
# 새 리깅 관례 -- 로케이터 자신의 위치가 곧 관절 원점).
cmds.xform(cmds.listRelatives(childAxis, parent=True, fullPath=True)[0],
           worldSpace=True, translation=(0.0, 10.0, 0.0))
cmds.setAttr(childAxis + ".conventionAxis", 0)  # X축

cmds.maroConnectAxis(childAxis, rootAxis)
cmds.maroAddCapability(childAxis, type="rotation")

flatAxes = cmds.maroListAxisNodes()
axisRows = urdf.sliceAxisRows(flatAxes)
assert len(axisRows) == 2, axisRows

tmpPath = os.path.join(tempfile.gettempdir(), "maro_urdf_export_test.urdf")
result = urdf.export(path=tmpPath)
assert result == tmpPath, result
assert os.path.isfile(tmpPath), tmpPath

import xml.etree.ElementTree as ET2
tree = ET2.parse(tmpPath)
robotEl = tree.getroot()
linkNames = sorted(l.get("name") for l in robotEl.findall("link"))
assert linkNames == sorted(["baseLink", "armLink"]), linkNames
jointEls = robotEl.findall("joint")
assert len(jointEls) == 1, jointEls
j = jointEls[0]
assert j.get("name") == "arm_joint", j.attrib
assert j.get("type") == "continuous", j.attrib  # rotation만 있고 limit 없음
originXyz = [float(v) for v in j.find("origin").get("xyz").split()]
# childMesh는 rootMesh 기준 Y로 10cm = 0.1m 위에 있다(Maya 내부 단위는
# 센티미터, ROS는 미터). Y-up(Maya) -> Z-up(ROS) 변환 때문에 정확히 어느
# 성분에 0.1이 나오는지는 mayaToRosPosition의 실제 축 재배치에 달려 있다
# -- 여기서는 "원점이 원점(0,0,0)이 아니고, 크기가 대략 0.1m"라는 것만
# 느슨하게 확인한다(정확한 성분별 값은 수동 체크리스트의 RViz2 확인이
# 담당).
originMagnitude = sum(v * v for v in originXyz) ** 0.5
assert abs(originMagnitude - 0.1) < 1e-3, originXyz
print("end-to-end export() with a real 2-axis chain OK")

os.remove(tmpPath)
```

- [ ] **Step 5: `docs/maro-main-ui-manual-checklist.md`에 새 절 추가**

파일 끝에 추가한다:

`````markdown

## Maro URDF 내보내기

인터랙티브 Maya 2026에서 축 2-3개짜리 간단한 체인(회전 관절 하나, 리밋
있는 관절 하나 포함)을 만들고, Maro 메뉴에서 "URDF 내보내기..."를
클릭해 `.urdf` 파일로 저장한다.

- [ ] **파일이 실제로 만들어진다** — 저장 대화상자에서 경로를 고르면
      그 자리에 `.urdf` 파일이 생기고, 하단에 "Maro: URDF exported to
      ..." 안내가 뜨는지 확인한다.
- [ ] **`check_urdf`로 파싱된다** — ROS 2가 설치된 환경에서
      `check_urdf <파일>`을 실행해 문법 오류 없이 파싱되는지, 관절/링크
      개수가 씬의 축 개수와 일치하는지 확인한다.
- [ ] **[go/no-go] RViz2에서 관절이 실제로 올바른 위치/방향으로 돈다** —
      `ros2 run robot_state_publisher robot_state_publisher <파일>` 등으로
      RViz2에 로드하고, `joint_state_publisher_gui`로 각 관절을 움직여
      봐서 Maya 씬에서 봤던 것과 같은 자리에서 같은 방향으로 도는지
      확인한다. 어긋나면 `computeRelativeOrigin`의 좌표 변환/오일러 순서
      가정(이 계획의 Task 2 참고)부터 재검토해야 한다 — 이게 이 기능
      전체에서 가장 위험한 가정이다.
- [ ] **부모 없는 축이 0개/2개 이상이면 명확한 에러가 뜬다** — 씬에서
      축 하나의 `parentAxis` 연결을 끊거나 둘째 루트를 만든 뒤 다시
      내보내기를 시도해, Script Editor에 어떤 축이 문제인지 알려주는
      경고가 뜨는지(크래시나 알 수 없는 트레이스백이 아니라) 확인한다.
- [ ] **빈 jointName이 있으면 명확한 에러가 뜬다** — 축 하나의 jointName을
      지우고 내보내기를 시도해 같은 방식으로 확인한다.
`````

- [ ] **Step 6: 빌드 후 전체 테스트 스위트 실행**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
ctest --test-dir out/build -C Release --output-on-failure
```

Expected: 빌드 성공, 전체 테스트 스위트가 이전과 동일하게(Task 1이 늘린 1개 포함) 전부 PASS, `maya_urdf_export`가 종단 간 테스트까지 통과.

- [ ] **Step 7: 커밋**

```bash
git add python/maroUrdfExport.py python/maroMenu.py src/maro_plugin/CMakeLists.txt \
        tests/maya/test_urdf_export.py docs/maro-main-ui-manual-checklist.md
git commit -m "feat(urdf): wire scene queries, export() orchestration, and Maro menu entry"
```
