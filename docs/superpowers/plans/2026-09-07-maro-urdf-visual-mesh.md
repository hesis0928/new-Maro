# URDF 시각 메쉬 내보내기 (슬라이스 1) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** URDF 내보내기가 각 링크의 형상을 STL로 함께 내보내고 `<visual>`로 참조하게 한다 — 지금은 기구학만 나가서 RViz에 좌표축만 뜬다.

**Architecture:** 순수 함수 네 개(STL 쓰기, 좌표 변환, 파일명 살균, `<visual>` XML 방출)를 먼저 만들고 마지막 태스크에서 씬 조회와 `export()` 배선을 붙인다. 순수 함수는 Maya 씬 없이 배치에서 검증되고, 씬을 만지는 코드는 `_linkMeshTriangles` 한 함수에 격리된다. 전부 `python/maroUrdfExport.py` 안에 둔다 — 소비자가 이 파일 하나뿐이고 466줄이라 쪼갤 크기가 아니다.

**Tech Stack:** Python (mayapy), `maya.api.OpenMaya`(om2), `struct`, `re`, `math`, `xml.etree.ElementTree`. 새 C++ 코드 없음. 외부 의존성 추가 없음.

## Global Constraints

- 빌드는 항상 `--config Release`. `ctest --test-dir out/build -C Release --output-on-failure`가 전부 통과해야 한다.
- **`.py`만 고쳐도 반드시 `cmake --build`를 돌린다.** 테스트는 플러그인 옆에 스테이징된 사본을 import하므로, 빌드를 건너뛰면 낡은 코드를 검증하게 된다(`src/maro_plugin/CMakeLists.txt`의 `MARO_PLUGIN_PY_MODULES` 복사 규칙).
- 좌표 변환 수식을 다시 구현하지 않는다 — 축 재배치는 `python/maroLimitCalibration.py`의 `mayaDirectionToRos`와 같은 식 `(x,y,z) -> (x,-z,y)`을 쓰고 그 사실을 주석으로 연결한다.
- `buildUrdfXml`은 순수 함수로 남는다 — 파일 I/O도 씬 조회도 하지 않는다.
- 새 파이썬 모듈을 만들지 않는다(이번 슬라이스는 전부 `maroUrdfExport.py` 안). 만들었다면 `MARO_PLUGIN_PY_MODULES`에 반드시 추가해야 한다.
- 새 `.py`는 `setStyleSheet()`를 호출하지 않는다(이번엔 UI가 없지만 규율 유지).
- STL 헤더는 `"Maro URDF export"`를 쓰고 80바이트까지 `\0`으로 채운다.
- URDF 안의 `<link name=>`은 **손대지 않는다**. 살균은 파일명에만 적용한다.

**빌드/테스트 명령(PowerShell):**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] } }
cmake --build out/build --config Release
ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure
```

---

### Task 1: `writeBinaryStl` — 바이너리 STL 쓰기

**Files:**
- Modify: `python/maroUrdfExport.py` (import 블록 17-22행, 그리고 파일 끝에 함수 추가)
- Test: `tests/maya/test_urdf_export.py` (파일 끝에 절 추가)

**Interfaces:**
- Consumes: 없음(이 태스크가 첫 번째다)
- Produces: `writeBinaryStl(triangles, path) -> None`. `triangles`는 `[((x,y,z),(x,y,z),(x,y,z)), ...]` — float 3-튜플 세 개로 된 튜플의 리스트. Task 4가 이것을 부른다. 보조 함수 `_triangleNormal(a, b, c) -> (nx,ny,nz)`도 함께 생기며 Task 2의 테스트가 참조한다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/maya/test_urdf_export.py` 맨 끝(마지막 `print(...)` 다음)에 붙인다:

```python
# --- writeBinaryStl (슬라이스 1) ---
import struct as _struct

_stlDir = tempfile.mkdtemp(prefix="maro_stl_")
_stlPath = os.path.join(_stlDir, "one.stl")
# 반시계 방향(CCW) 삼각형 -- 법선이 +Z여야 한다.
urdf.writeBinaryStl([((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))], _stlPath)
_raw = open(_stlPath, "rb").read()
assert len(_raw) == 84 + 50, len(_raw)
assert _raw[:16] == b"Maro URDF export", _raw[:16]
assert _raw[16:80] == b"\0" * 64, "header must be zero-padded to 80 bytes"
assert _struct.unpack("<I", _raw[80:84])[0] == 1
_vals = _struct.unpack("<12fH", _raw[84:134])
assert _vals[0:3] == (0.0, 0.0, 1.0), _vals[0:3]
assert _vals[3:12] == (0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0), _vals[3:12]
assert _vals[12] == 0, "attribute byte count must be 0"

# 삼각형 0개도 유효한 STL이다(헤더 + 개수 0).
_emptyPath = os.path.join(_stlDir, "empty.stl")
urdf.writeBinaryStl([], _emptyPath)
assert len(open(_emptyPath, "rb").read()) == 84

# 축퇴 삼각형(면적 0)은 법선을 0으로 둔다 -- 0으로 나누면 안 된다.
_degPath = os.path.join(_stlDir, "deg.stl")
urdf.writeBinaryStl([((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))], _degPath)
_degVals = _struct.unpack("<12fH", open(_degPath, "rb").read()[84:134])
assert _degVals[0:3] == (0.0, 0.0, 0.0), _degVals[0:3]
print("writeBinaryStl OK")
```

`tempfile`과 `os`는 이 파일이 이미 import하고 있다(341행 근처에서 쓴다).

- [ ] **Step 2: 실패를 확인한다**

Run: `ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure`

Expected: FAIL — `AttributeError: module 'maroUrdfExport' has no attribute 'writeBinaryStl'`

- [ ] **Step 3: import를 추가한다**

`python/maroUrdfExport.py`의 17행

```python
import os
```

을 이렇게 바꾼다:

```python
import math
import os
import struct
```

(`maya.cmds` / `maya.api.OpenMaya` / `xml.etree.ElementTree` import는 그대로 둔다.)

- [ ] **Step 4: 함수를 구현한다**

`python/maroUrdfExport.py` 맨 끝에 붙인다:

```python
# 바이너리 STL 헤더. 80바이트까지 \0으로 채운다(설계 스펙 §5).
_STL_HEADER = b"Maro URDF export"


def _triangleNormal(a, b, c):
    """삼각형의 단위 법선. 면적이 0이면 (0,0,0)을 준다 -- 0으로 나누지
    않는다. 대부분의 STL 뷰어는 저장된 법선을 무시하고 다시 계산하지만,
    전부 0으로 두면 형식을 잘못 쓴 것과 구별되지 않으므로 계산해 채운다."""
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length < 1e-12:
        return (0.0, 0.0, 0.0)
    return (nx / length, ny / length, nz / length)


def writeBinaryStl(triangles, path):
    """triangles([((x,y,z),(x,y,z),(x,y,z)), ...])를 바이너리 STL로 쓴다.

    형식(전부 리틀엔디언):
      오프셋 0    80바이트  헤더
      오프셋 80    4바이트  uint32 삼각형 수
      오프셋 84+  50바이트  삼각형당: 법선 3xfloat32, 정점 9xfloat32, uint16 속성

    Maya 내장 익스포터(stlTranslator.mll)가 아니라 직접 쓰는 이유는 설계
    스펙 §5에 있다 -- 좌표/단위 변환을 정점에 바로 적용할 수 있고(익스포터의
    단위 해석에 의존하지 않는다), 순수 함수라 배치 테스트로 왕복 검증이
    된다. maroSyntheticDataPointCloud.writePly와 같은 결이다.

    "<12fH"는 12*4 + 2 = 50바이트다 -- "<"가 정렬 패딩을 끄므로 구조체
    크기가 형식대로 정확히 나온다.
    """
    with open(path, "wb") as f:
        f.write(_STL_HEADER.ljust(80, b"\0"))
        f.write(struct.pack("<I", len(triangles)))
        for a, b, c in triangles:
            nx, ny, nz = _triangleNormal(a, b, c)
            f.write(struct.pack("<12fH", nx, ny, nz,
                                a[0], a[1], a[2],
                                b[0], b[1], b[2],
                                c[0], c[1], c[2], 0))
```

- [ ] **Step 5: 빌드하고 통과를 확인한다**

Run:
```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure
```

Expected: PASS, 출력에 `writeBinaryStl OK`

- [ ] **Step 6: 커밋**

```bash
git add python/maroUrdfExport.py tests/maya/test_urdf_export.py
git commit -m "feat(urdf): write binary STL"
```

---

### Task 2: `mayaTrianglesToRosMeters` — 좌표·단위 변환

**Files:**
- Modify: `python/maroUrdfExport.py` (Task 1이 추가한 `_STL_HEADER` 정의 바로 앞)
- Test: `tests/maya/test_urdf_export.py` (Task 1의 절 다음)

**Interfaces:**
- Consumes: Task 1의 `_triangleNormal(a, b, c) -> (nx,ny,nz)` (와인딩 보존 단정에서 쓴다)
- Produces: `mayaTrianglesToRosMeters(triangles) -> list`. 입력은 Maya 내부 단위(센티미터) 링크 로컬 좌표의 삼각형 리스트, 출력은 ROS 프레임 미터의 같은 구조. Task 4가 `writeBinaryStl`에 넘기기 직전에 부른다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/maya/test_urdf_export.py`의 Task 1 절 다음에 붙인다:

```python
# --- mayaTrianglesToRosMeters (슬라이스 1) ---
# Maya 내부 단위는 항상 센티미터다(실측: om2.MDistance.internalUnit() == 6,
# .asMeters() == 0.01). 100 단위 = 1 미터.
_converted = urdf.mayaTrianglesToRosMeters(
    [((100.0, 0.0, 0.0), (0.0, 100.0, 0.0), (0.0, 0.0, 100.0))])
assert len(_converted) == 1
_a, _b, _c = _converted[0]
# 축 재배치 (x,y,z) -> (x,-z,y), 그리고 cm -> m.
assert _a == (1.0, 0.0, 0.0), _a          # maya +X -> ros +X
assert _b == (0.0, 0.0, 1.0), _b          # maya +Y(up) -> ros +Z(up)
assert _c == (0.0, -1.0, 0.0), _c         # maya +Z -> ros -Y

# 와인딩 보존: 이 재배치의 행렬식이 +1(반사가 아닌 회전)이므로, 변환 후
# 삼각형의 법선은 "변환 전 법선을 같은 방식으로 재배치한 것"과 같아야
# 한다. 반사였다면 부호가 뒤집혀 RViz에서 안팎이 뒤집힌 메쉬가 나온다.
_beforeNormal = urdf._triangleNormal(
    (100.0, 0.0, 0.0), (0.0, 100.0, 0.0), (0.0, 0.0, 100.0))
_expectedNormal = (_beforeNormal[0], -_beforeNormal[2], _beforeNormal[1])
_afterNormal = urdf._triangleNormal(_a, _b, _c)
assert all(abs(x - y) < 1e-9 for x, y in zip(_expectedNormal, _afterNormal)), \
    (_expectedNormal, _afterNormal)

assert urdf.mayaTrianglesToRosMeters([]) == []
print("mayaTrianglesToRosMeters OK")
```

- [ ] **Step 2: 실패를 확인한다**

Run: `ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure`

Expected: FAIL — `AttributeError: module 'maroUrdfExport' has no attribute 'mayaTrianglesToRosMeters'`

- [ ] **Step 3: 함수를 구현한다**

`python/maroUrdfExport.py`의 `_STL_HEADER` 정의 **바로 앞**에 붙인다:

```python
def mayaTrianglesToRosMeters(triangles):
    """Maya 내부 단위(센티미터)의 링크 로컬 삼각형들을 ROS 프레임 미터로.

    축 재배치 (x,y,z) -> (x,-z,y)는 python/maroLimitCalibration.py의
    mayaDirectionToRos와 **같은 식**이다. 다른 점은 스케일뿐이다 --
    방향 벡터는 단위가 없어 스케일을 곱하지 않지만 위치는 곱한다.

    **정점 순서를 바꾸지 않는다.** 그 재배치의 행렬식은 +1이다(X축 -90°
    회전이며 반사가 아니다). 따라서 와인딩이 그대로 보존되어 법선이
    뒤집히지 않는다 -- 반사였다면 삼각형마다 정점 두 개를 맞바꿔야 했고,
    확인하지 않고 넘어갔다면 RViz에서 안팎이 뒤집힌 메쉬가 나왔을 것이다.

    스케일은 메쉬 하나당 한 번만 조회한다(정점마다 om2를 부르지 않는다).
    om2는 UI 선형 단위 계층 아래에서 항상 내부 단위로만 동작하므로
    (_gatherAxisWorldTransformRos의 주석과 같은 이유) 사용자의 UI 단위
    설정이 이 값을 흔들지 않는다.
    """
    scale = om2.MDistance(1.0, om2.MDistance.internalUnit()).asMeters()
    return [
        tuple((v[0] * scale, -v[2] * scale, v[1] * scale) for v in triangle)
        for triangle in triangles
    ]
```

- [ ] **Step 4: 빌드하고 통과를 확인한다**

Run:
```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure
```

Expected: PASS, 출력에 `mayaTrianglesToRosMeters OK`

- [ ] **Step 5: 커밋**

```bash
git add python/maroUrdfExport.py tests/maya/test_urdf_export.py
git commit -m "feat(urdf): convert mesh vertices to the ROS frame in metres"
```

---

### Task 3: 파일명 살균 + `buildUrdfXml`의 `<visual>` 방출

**Files:**
- Modify: `python/maroUrdfExport.py` (import 블록, `buildUrdfXml` 192-206행, Task 2 함수 바로 앞에 살균 함수 추가)
- Test: `tests/maya/test_urdf_export.py` (Task 2 절 다음)

**Interfaces:**
- Consumes: 없음
- Produces:
  - `sanitizeMeshFileName(linkName, usedNames) -> str`. `usedNames`는 `set`이며 **이 함수가 갱신한다**(호출자가 같은 set을 반복 전달해 충돌을 피한다). 확장자는 붙이지 않는다.
  - `buildUrdfXml(robotName, links, joints)`의 `links` 원소가 선택적 키 `"visualMesh"`(문자열, 또는 `None`/키 없음)를 받는다. Task 4가 채운다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/maya/test_urdf_export.py`의 Task 2 절 다음에 붙인다:

```python
# --- sanitizeMeshFileName (슬라이스 1) ---
_used = set()
assert urdf.sanitizeMeshFileName("baseLink", _used) == "baseLink"
# 네임스페이스가 붙은 노드: _shortName은 "|"로만 쪼개므로 ":"가 그대로
# 남는다. ":"는 Windows 파일명에 쓸 수 없다.
assert urdf.sanitizeMeshFileName("ns:cube", _used) == "ns_cube"
# 살균 결과가 충돌하면 일련번호를 붙인다.
assert urdf.sanitizeMeshFileName("ns/cube", _used) == "ns_cube_1"
assert urdf.sanitizeMeshFileName("", _used) == "link"
assert _used == {"baseLink", "ns_cube", "ns_cube_1", "link"}, _used
print("sanitizeMeshFileName OK")

# --- buildUrdfXml <visual> (슬라이스 1) ---
_visualRobot = urdf.buildUrdfXml(
    "rob",
    [{"name": "withMesh", "visualMesh": "package://rob/meshes/withMesh.stl"},
     {"name": "noMesh", "visualMesh": None},
     {"name": "legacy"}],          # 키 자체가 없는 기존 호출부도 그대로 동작해야 한다
    [])
_byName = {l.get("name"): l for l in _visualRobot.findall("link")}
_v = _byName["withMesh"].find("visual")
assert _v is not None, "a link with visualMesh must emit <visual>"
assert _v.find("geometry/mesh").get("filename") == "package://rob/meshes/withMesh.stl"
# 정점을 이미 링크 프레임으로 구웠으므로 원점은 항등이다.
assert _v.find("origin").get("xyz") == "0 0 0", _v.find("origin").attrib
assert _v.find("origin").get("rpy") == "0 0 0", _v.find("origin").attrib
assert _byName["noMesh"].find("visual") is None
assert _byName["legacy"].find("visual") is None
print("buildUrdfXml <visual> OK")
```

- [ ] **Step 2: 실패를 확인한다**

Run: `ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure`

Expected: FAIL — `AttributeError: module 'maroUrdfExport' has no attribute 'sanitizeMeshFileName'`

- [ ] **Step 3: `re` import를 추가한다**

Task 1이 만든 import 블록을 이렇게 바꾼다:

```python
import math
import os
import re
import struct
```

- [ ] **Step 4: 살균 함수를 구현한다**

`python/maroUrdfExport.py`의 `mayaTrianglesToRosMeters` **바로 앞**에 붙인다:

```python
# 파일명에 그대로 써도 안전한 문자. 나머지는 "_"로 바꾼다.
_UNSAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9_-]")


def sanitizeMeshFileName(linkName, usedNames):
    """linkName을 파일명으로 쓸 수 있게 살균한다(확장자는 안 붙인다).

    [실측] _shortName()은 DAG 경로를 "|"로만 쪼개므로, 네임스페이스가 붙은
    노드는 링크 이름이 "ns:cube"가 된다. ":"는 Windows 파일명에 쓸 수 없어
    그대로 쓰면 내보내기가 실패한다.

    **URDF 안의 <link name=>은 이 함수를 거치지 않는다.** 그건 이미
    동작하는 기존 계약이고 이번 변경이 건드릴 이유가 없다 -- 링크 이름과
    파일명은 별개이며 <mesh filename=>만 살균된 쪽을 가리킨다.

    usedNames(set)는 이 함수가 갱신한다. 살균 결과가 서로 충돌하면
    ("a:b"와 "a/b"가 둘 다 "a_b"가 되는 경우) 뒤에 일련번호를 붙인다.
    """
    base = _UNSAFE_FILENAME_RE.sub("_", linkName) or "link"
    candidate = base
    suffix = 1
    while candidate in usedNames:
        candidate = "{}_{}".format(base, suffix)
        suffix += 1
    usedNames.add(candidate)
    return candidate
```

- [ ] **Step 5: `buildUrdfXml`이 `<visual>`을 내게 한다**

`python/maroUrdfExport.py`의 204-205행

```python
    for link in links:
        ET.SubElement(robot, "link", name=link["name"])
```

을 이렇게 바꾼다:

```python
    for link in links:
        linkEl = ET.SubElement(robot, "link", name=link["name"])
        # .get()으로 읽는다 -- "visualMesh" 키가 아예 없는 기존 호출부와
        # 테스트도 그대로 동작해야 한다(슬라이스 1이 추가한 선택적 필드다).
        visualMesh = link.get("visualMesh")
        if visualMesh:
            visualEl = ET.SubElement(linkEl, "visual")
            # 정점을 이미 링크 프레임으로 구웠으므로 원점은 항등이다 --
            # 변환을 URDF 쪽 <origin>/<scale>로 미루지 않는다(스펙 §6).
            ET.SubElement(visualEl, "origin", xyz="0 0 0", rpy="0 0 0")
            geometryEl = ET.SubElement(visualEl, "geometry")
            ET.SubElement(geometryEl, "mesh", filename=visualMesh)
```

그리고 같은 함수의 독스트링 첫 줄

```python
    """links: [{"name": str}, ...]. joints: [{"name": str, "type": str,
```

을 이렇게 고친다:

```python
    """links: [{"name": str, "visualMesh": str|None(선택)}, ...].
    joints: [{"name": str, "type": str,
```

- [ ] **Step 6: 빌드하고 통과를 확인한다**

Run:
```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure
```

Expected: PASS, 출력에 `sanitizeMeshFileName OK`와 `buildUrdfXml <visual> OK`

- [ ] **Step 7: 커밋**

```bash
git add python/maroUrdfExport.py tests/maya/test_urdf_export.py
git commit -m "feat(urdf): emit <visual> and sanitise mesh filenames"
```

---

### Task 4: 씬 조회와 `export()` 배선

**Files:**
- Modify: `python/maroUrdfExport.py` (`_buildRobotModel` 391행·429행, `export` 456-458행, `_buildRobotModel` 바로 앞에 새 함수 둘)
- Test: `tests/maya/test_urdf_export.py` (기존 통합 절 끝, 374행 근처 다음)

**Interfaces:**
- Consumes: Task 1의 `writeBinaryStl`, Task 2의 `mayaTrianglesToRosMeters`, Task 3의 `sanitizeMeshFileName`과 `visualMesh` 필드. **주의:** 이 태스크의 테스트 코드는 파일 앞쪽(기존 통합 절 끝, 374행 근처)에 들어가고 Task 1-3의 테스트 절은 파일 **끝**에 붙으므로, 앞쪽에서 뒤쪽 이름(`_struct` 등)을 쓸 수 없다 -- 필요한 import는 이 블록 안에서 다시 한다.
- Produces: 없음(마지막 태스크). 내부 함수 `_linkMeshTriangles(linkTransform) -> list`와 `_writeLinkMeshes(links, meshDir, robotName) -> None`이 생기고, `_buildRobotModel`이 만드는 링크 딕셔너리에 `"targetPath"` 키가 추가된다(`buildUrdfXml`은 이 키를 무시한다).

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/maya/test_urdf_export.py`의 기존 통합 절 마지막 단정(`assert axisEl.get("xyz") == "1 0 0", axisEl.get("xyz")`) **다음**에 붙인다. 그 절이 이미 만들어 둔 씬(`baseLink`/`armLink` 폴리큐브가 축에 바인딩됨)과 변수 `tmpPath`/`robotEl`/`ET2`/`_struct`를 그대로 쓴다:

```python
# --- 시각 메쉬 (슬라이스 1) ---
# struct를 여기서 다시 import한다 -- Task 1의 테스트 절은 이 파일의 **끝**에
# 붙으므로, 이 지점(374행 근처)에서는 아직 _struct가 정의되지 않았다.
# 재import는 무해하다.
import struct as _struct

# 위 export()가 이미 돌았다. 폴리큐브는 mesh 셰이프를 가지므로 두 링크 다
# <visual>과 STL 파일이 나와야 한다.
_meshDir = os.path.join(os.path.dirname(os.path.abspath(tmpPath)), "meshes")
assert os.path.isdir(_meshDir), _meshDir
for _linkName in ("baseLink", "armLink"):
    _stl = os.path.join(_meshDir, _linkName + ".stl")
    assert os.path.isfile(_stl), _stl
    # 기본 폴리큐브는 6면 * 2 = 12 삼각형이다(실측 확인).
    _count = _struct.unpack("<I", open(_stl, "rb").read()[80:84])[0]
    assert _count == 12, (_linkName, _count)

for _linkEl in robotEl.findall("link"):
    _vis = _linkEl.find("visual")
    assert _vis is not None, "expected <visual> on " + _linkEl.get("name")
    _fn = _vis.find("geometry/mesh").get("filename")
    _expected = "package://{}/meshes/{}.stl".format(
        os.path.splitext(os.path.basename(tmpPath))[0], _linkEl.get("name"))
    assert _fn == _expected, (_fn, _expected)
print("visual meshes exported OK")

# 부모 링크가 자식 링크의 메쉬를 삼키지 않는다.
#
# allDescendents로 훑으면 정확히 이 상황에서 부모가 자식 지오메트리까지
# 가져가 삼각형 수가 24가 된다 -- 조인트 체인에서는 자식 링크가 부모의
# DAG 자손이기 때문이다(스펙 §3).
cmds.file(new=True, force=True)
_pBase = cmds.polyCube(name="pBase")[0]
_pChild = cmds.polyCube(name="pChild")[0]
cmds.parent(_pChild, _pBase)
_aBase = cmds.createNode("maroAxis")
cmds.maroBindAxis(_aBase, _pBase)
cmds.setAttr(_aBase + ".jointName", "j_base", type="string")
_aBase = cmds.ls(_aBase, long=True)[0]
_aChild = cmds.createNode("maroAxis")
cmds.maroBindAxis(_aChild, cmds.ls(_pChild, long=True)[0])
cmds.setAttr(_aChild + ".jointName", "j_child", type="string")
_aChild = cmds.ls(_aChild, long=True)[0]
cmds.maroConnectAxis(_aChild, _aBase)
_nestPath = os.path.join(tempfile.mkdtemp(prefix="maro_urdf_nest_"), "nested.urdf")
assert urdf.export(path=_nestPath) == _nestPath
_nestMeshDir = os.path.join(os.path.dirname(os.path.abspath(_nestPath)), "meshes")
_baseStl = os.path.join(_nestMeshDir, "pBase.stl")
_baseCount = _struct.unpack("<I", open(_baseStl, "rb").read()[80:84])[0]
assert _baseCount == 12, (
    "the parent link swallowed its child's geometry (allDescendents trap): %d"
    % _baseCount)
print("parent link does not swallow child geometry OK")

# 메쉬가 없는 링크는 <visual> 없이 나간다(에러가 아니다).
cmds.file(new=True, force=True)
_bone = cmds.createNode("joint", name="boneOnly")
_aBone = cmds.createNode("maroAxis")
cmds.maroBindAxis(_aBone, _bone)
cmds.setAttr(_aBone + ".jointName", "j_bone", type="string")
_bonePath = os.path.join(tempfile.mkdtemp(prefix="maro_urdf_bone_"), "bone.urdf")
assert urdf.export(path=_bonePath) == _bonePath
_boneRoot = ET2.parse(_bonePath).getroot()
assert _boneRoot.find("link").find("visual") is None, \
    "a mesh-less link must have no <visual>"
assert not os.path.isdir(
    os.path.join(os.path.dirname(os.path.abspath(_bonePath)), "meshes")), \
    "no meshes/ directory should be created when nothing has geometry"
print("mesh-less link exports without <visual> OK")
```

- [ ] **Step 2: 실패를 확인한다**

Run: `ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure`

Expected: FAIL — `AssertionError` (meshes 디렉터리가 없다)

- [ ] **Step 3: 씬에서 삼각형을 모으는 함수 둘을 구현한다**

`python/maroUrdfExport.py`의 `def _buildRobotModel():` **바로 앞**에 붙인다:

```python
def _linkMeshTriangles(linkTransform):
    """linkTransform의 **직속** mesh 셰이프들에서 삼각형을 모아 링크 로컬
    프레임(Maya 내부 단위)으로 돌려준다. 메쉬가 없으면 빈 리스트.

    **allDescendents를 쓰면 안 된다.** 조인트 체인에서 한 링크의 자손에는
    자식 링크의 메쉬가 들어 있어서, 자손 전체를 훑으면 같은 지오메트리가
    두 링크에 중복으로 들어가고 부모 링크가 로봇 전체를 삼킨다(스펙 §3).
    maroDagMenu._findLidarForMesh가 listRelatives(shapes=True)로 직속만
    보는 것과 같은 이유다.

    월드 좌표를 링크의 월드 역행렬로 되돌린다 -- 셰이프가 링크의 직속
    자식이면 오브젝트 공간과 같지만(실측 확인), 중간 트랜스폼이 끼어도 이
    경로는 항상 링크 프레임을 준다.
    """
    shapes = cmds.listRelatives(linkTransform, shapes=True, fullPath=True,
                                type="mesh") or []
    if not shapes:
        return []

    linkInverse = om2.MSelectionList().add(linkTransform).getDagPath(0) \
        .inclusiveMatrixInverse()
    triangles = []
    for shape in shapes:
        meshFn = om2.MFnMesh(om2.MSelectionList().add(shape).getDagPath(0))
        worldPoints = meshFn.getPoints(om2.MSpace.kWorld)
        # getTriangles()는 (면당 삼각형 수, 평평한 정점 인덱스)를 준다 --
        # 인덱스는 세 개씩 한 삼각형이다(실측: 기본 폴리큐브 = 면 6개,
        # 인덱스 36개, 삼각형 12개).
        _counts, indices = meshFn.getTriangles()
        for i in range(0, len(indices), 3):
            corners = []
            for j in range(3):
                p = worldPoints[indices[i + j]] * linkInverse
                corners.append((p.x, p.y, p.z))
            triangles.append(tuple(corners))
    return triangles


def _writeLinkMeshes(links, meshDir, robotName):
    """각 링크의 메쉬를 STL로 쓰고 link["visualMesh"]에 package:// 경로를
    채운다. 메쉬가 없거나 삼각형이 0개인 링크는 건드리지 않는다 -- 그
    링크는 <visual> 없이 나가며 이는 정상이고 에러가 아니다.

    meshDir는 실제로 쓸 것이 생겼을 때만 만든다 -- 지오메트리가 하나도
    없는 씬을 내보내면 빈 meshes/ 디렉터리를 남기지 않는다.
    """
    usedNames = set()
    for link in links:
        targetPath = link.get("targetPath")
        if not targetPath:
            continue
        triangles = _linkMeshTriangles(targetPath)
        if not triangles:
            continue
        fileName = sanitizeMeshFileName(link["name"], usedNames)
        if not os.path.isdir(meshDir):
            os.makedirs(meshDir)
        writeBinaryStl(mayaTrianglesToRosMeters(triangles),
                       os.path.join(meshDir, fileName + ".stl"))
        link["visualMesh"] = "package://{}/meshes/{}.stl".format(robotName, fileName)
```

- [ ] **Step 4: `_buildRobotModel`이 링크에 `targetPath`를 싣게 한다**

391행

```python
    links = [{"name": _shortName(rowsByPath[root]["boundTargetPath"])}]
```

을

```python
    # targetPath는 _writeLinkMeshes가 그 링크의 메쉬를 찾는 데 쓴다.
    # buildUrdfXml은 이 키를 무시한다.
    links = [{"name": _shortName(rowsByPath[root]["boundTargetPath"]),
              "targetPath": rowsByPath[root]["boundTargetPath"]}]
```

으로, 그리고 429행

```python
            links.append({"name": _shortName(childRow["boundTargetPath"])})
```

를

```python
            links.append({"name": _shortName(childRow["boundTargetPath"]),
                          "targetPath": childRow["boundTargetPath"]})
```

로 바꾼다.

- [ ] **Step 5: `export()`가 메쉬를 쓰게 한다**

456-458행

```python
        links, joints = _buildRobotModel()
        robotName = os.path.splitext(os.path.basename(path))[0]
        robotElement = buildUrdfXml(robotName, links, joints)
```

을 이렇게 바꾼다:

```python
        links, joints = _buildRobotModel()
        robotName = os.path.splitext(os.path.basename(path))[0]
        # STL은 .urdf 옆 meshes/ 에 쓴다. abspath를 거치는 이유는 path가
        # 디렉터리 없는 상대 파일명일 때 dirname이 ""이 되어 meshes/가
        # 엉뚱한 곳(프로세스 cwd)에 생기는 것을 막기 위해서다.
        _writeLinkMeshes(
            links,
            os.path.join(os.path.dirname(os.path.abspath(path)), "meshes"),
            robotName)
        robotElement = buildUrdfXml(robotName, links, joints)
```

- [ ] **Step 6: 빌드하고 통과를 확인한다**

Run:
```powershell
cmake --build out/build --config Release
ctest --test-dir out/build -C Release -R maya_urdf_export --output-on-failure
```

Expected: PASS, 출력에 `visual meshes exported OK`, `parent link does not swallow child geometry OK`, `mesh-less link exports without <visual> OK`

- [ ] **Step 7: 전체 스위트를 돌린다**

Run: `ctest --test-dir out/build -C Release`

Expected: 전부 통과(환경 스킵 `JobEscape.CurrentProcessReportsNotInJobByDefault` 1건 제외). 이 변경은 URDF 경로에만 닿으므로 `maya_contract`/`maya_publish`/`maya_lidar_publish`가 영향을 받으면 안 된다.

- [ ] **Step 8: 커밋**

```bash
git add python/maroUrdfExport.py tests/maya/test_urdf_export.py
git commit -m "feat(urdf): export per-link visual meshes"
```

---

## 수동 확인 (구현 후)

배치 테스트가 원리적으로 못 보는 것 하나 — **RViz에서 실제로 형상이 제대로 보이는가**(법선 방향, 스케일, 링크별 위치). `docs/maro-main-ui-manual-checklist.md`의 "Maro URDF 내보내기" 절에 다음 항목을 추가한다:

- [ ] 축 두 개짜리 리그를 내보내고, 내보낸 디렉터리에 `package.xml`을 넣어 ROS 패키지로 등록한 뒤 RViz에서 로봇 모델을 띄운다 — 링크마다 형상이 보이고, 안팎이 뒤집힌 면이 없고, 크기가 Maya 씬과 맞는지 확인한다.
