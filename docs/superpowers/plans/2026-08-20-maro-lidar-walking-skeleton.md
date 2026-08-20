# maroLidar 워킹 스켈레톤 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Maya 씬의 메쉬 하나를 스캔해 Embree로 레이캐스팅하고, 그 결과를 ROS 2 `PointCloud2`로 발행하는 가장 얇은 종단 파이프라인(워킹 스켈레톤)을 만든다 — 멀티스레딩/더티체크/대량 렌더링 없이, "노드 생성 → 레이 쏘기 → 발행"이 실제로 이어지는지부터 증명한다.

**Architecture:** Embree/레이 방향 계산/PointCloud2 바이너리 패킹은 Maya·ROS 헤더 둘 다 없는 새 라이브러리 `maro_lidar`로 분리해 gtest로 직접 검증한다(`maro_ipc`/`maro_transform`과 같은 패턴). `maro_plugin`은 이 라이브러리를 부르는 얇은 배선만 담당한다 — 메인 스레드(`MaroPump`)가 `MFnMesh`에서 정점/삼각형을 뽑아 순수 배열로 넘기고, 같은 틱 안에서 동기적으로 레이캐스팅해 발행한다(진짜 백그라운드 스레드 풀은 이 플랜의 범위 밖).

**Tech Stack:** C++17, Intel Embree 4.4.0(vcpkg), GoogleTest, rclcpp/sensor_msgs, CMake(Visual Studio 멀티 컨피그 제너레이터), Maya 2026 devkit.

## Global Constraints

- 스펙: `docs/superpowers/specs/2026-08-20-maro-lidar-walking-skeleton-design.md`
- `src/maro_lidar/`는 Maya 헤더도 ROS/rclcpp 헤더도 포함하지 않는다 — `maro_ipc`/`maro_transform`이 이미 지키는 원칙과 같다. `maro_transform`에는 의존해도 된다(둘 다 Maya-free, `Vec3`/`SceneUnit`/`mayaToRosPosition`을 재사용한다).
- **레이캐스팅은 전부 Maya 좌표계(Y-up)에서 일어난다.** 메쉬 정점도, 레이 원점/방향도 변환 없이 그대로 쓴다. **ROS 좌표계(Z-up) 변환은 딱 한 곳, 충돌 지점을 `PointCloud2`에 패킹하기 직전에만** `maro::mayaToRosPosition()`으로 적용한다(`src/maro_transform/include/maro_transform/Convert.h`, 이미 존재).
- `MFnMesh` 데이터(정점/삼각형)는 **메인 스레드에서만** 읽는다(devkit 샘플이 일관되게 보이는 패턴 — Maya devkit 조사 결과, 이 스펙의 근거). 워킹 스켈레톤은 레이캐스팅 자체도 같은 틱 안에서 동기 실행한다 — 진짜 백그라운드 스레드 풀은 범위 밖.
- `PointCloud2` 필드는 `x`/`y`/`z`/`intensity`만(전부 `FLOAT32`) — `sensor_msgs/msg/PointField.msg`의 실제 주석이 "Common PointField names"로 명시한 것과 일치. `ring` 등은 범위 밖.
- `targetMeshes`는 인덱스 0 하나만 쓴다(다중 메쉬는 범위 밖). 바인딩은 기존 `capabilityIn` 패턴과 같이 `connectAttr <mesh>.message <lidar>.targetMeshes[0]`로 직접 연결한다 — 새 바인딩 커맨드를 만들지 않는다.
- 채널/해상도 값은 워킹 스켈레톤 검증 목적으로 작게 잡는다(예: 4채널) — 실제 스펙 스케일(16~64채널)은 범위 밖.
- 빌드는 항상 `--config Release`를 명시한다(이 저장소의 `out/build`는 CMake Visual Studio 멀티 컨피그 제너레이터다).
- 빌드 환경: `Launch-VsDevShell.ps1`이 이 머신에서 `vswhere.exe`를 못 찾아 `INCLUDE`/`LIB`를 비운 채 조용히 성공한다. **빌드와 같은 PowerShell 호출 안에서** `VsDevCmd.bat`를 설정한다:

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cd C:\Users\ckd30\Projects\Maya_Ros_Sim
cmake --build out/build --config Release
```

- `ctest --test-dir out/build -C Release --output-on-failure` 실행 시 `maya_panel_commands` 하나만 실패하는 것이 알려진 사전 결함이다(이 플랜과 무관, `main`에 이미 있음) — 그 외에는 전부 통과해야 한다.
- vcpkg의 Embree 포트(`C:/src/vcpkg/ports/embree/vcpkg.json`)는 버전 `4.4.0`, 패키지 이름은 `embree`(`embree3`가 아니다), `tasking-tbb` 기능이 기본 활성화라 `tbb`가 전이 의존성으로 딸려온다.
- **Embree 4 C API 관련 경고**: 아래 Task 3의 코드는 Embree 4.4.0의 문서화된 API 흐름(`rtcNewDevice`→`rtcNewScene`→`rtcNewGeometry`→`rtcSetSharedGeometryBuffer`→`rtcCommitGeometry`→`rtcAttachGeometry`→`rtcCommitScene`→`rtcIntersect1`)을 반영하지만, 정확한 구조체 필드/함수 시그니처는 **반드시 실제 설치된 헤더**(`vcpkg install` 이후 `C:/src/vcpkg/installed/x64-windows/include/embree4/rtcore.h`, `rtcore_ray.h`, `rtcore_geometry.h`)와 대조해서 확인한다 — Task 3 Step 3에 그 확인이 별도 단계로 들어가 있다. 이 프로젝트가 Embree를 쓰는 첫 사례이므로, 헤더와 다른 부분이 있으면 실제 헤더를 따르고 그 이유를 기록한다(이 플랜의 다른 태스크들이 지금까지 실제로 그래왔던 것과 같은 규율).

## 파일 구조

| 파일 | 책임 |
|---|---|
| `src/maro_plugin/MaroAxisNode.cpp` | (수정) `outValue` 어트리뷰트 롱네임을 `position`으로 변경 |
| `src/maro_lidar/include/maro_lidar/RayPattern.h` / `src/RayPattern.cpp` | 채널/해상도/각도 범위로부터 레이 방향 벡터 목록을 계산하는 순수 함수. Maya/Embree 둘 다 모른다 |
| `src/maro_lidar/include/maro_lidar/ScanEngine.h` / `src/ScanEngine.cpp` | Embree `RTCScene`을 감싼 클래스. 평범한 정점/인덱스 배열을 받아 레이 하나당 충돌 지점을 돌려준다 |
| `src/maro_lidar/include/maro_lidar/PointCloudPacking.h` / `src/PointCloudPacking.cpp` | 충돌 지점 배열(ROS 좌표계로 이미 변환된) → `PointCloud2`의 실제 바이너리 레이아웃(`point_step`/`data`)으로 패킹 |
| `src/maro_plugin/MaroLidarNode.h` / `.cpp` | Maya 노드 — §어트리뷰트 테이블. `compute()`는 값을 계산하지 않는다(메인 스레드 캡처+레이캐스팅은 펌프가 주도) |
| `src/maro_plugin/MaroPump.h` / `.cpp` | (수정) LiDAR 캡처+레이캐스팅을 기존 30Hz 펌프에 추가, 결과를 큐에 push |
| `src/maro_plugin/MaroBridgeQueues.h` | (수정) `LidarSample` 구조체 추가(`AxisSample`과 같은 패턴) |
| `src/maro_plugin/MaroRosRuntime.h` / `.cpp` | (수정) LiDAR 큐 드레인 + 좌표 변환 + `PointCloud2` 퍼블리셔 추가(기존 `drainAndPublish()`와 같은 자리, 백그라운드 스레드) |
| `tests/lidar/test_ray_pattern.cpp`, `test_scan_engine.cpp`, `test_point_cloud_packing.cpp` | `maro_lidar`의 gtest — Maya/mayapy 불필요 |
| `tests/maya/test_lidar_node.py` | `maroLidar` 노드 생성/어트리뷰트 확인(mayapy) |

---

### Task 1: `outValue` → `position` rename

**Files:**
- Modify: `src/maro_plugin/MaroAxisNode.cpp:174`
- Modify: `tests/maya/test_robustness.py`, `tests/maya/test_publish.py`, `tests/maya/test_contract.py`, `tests/maya/test_capability_stack.py`, `tests/maya/test_axis_node.py` (모두 `.outValue`/`"outValue"` 문자열을 `.position`/`"position"`으로)

**Interfaces:**
- Produces: Maya 어트리뷰트 롱네임 `position`(C++ 멤버 이름 `MaroAxisNode::aOutValue`는 그대로 둔다 — Maya 쪽 문자열만 바뀐다)

이 태스크는 새 기능이 아니라 순수 rename이라 새 테스트를 쓰지 않는다 — 기존 5개 mayapy 테스트가 이미 `.outValue`를 검증하고 있으므로, 그 파일들의 문자열을 바꾼 뒤 기존 테스트가 여전히 통과하는 것 자체가 검증이다.

- [ ] **Step 1: `MaroAxisNode.cpp`의 어트리뷰트 롱네임 변경**

`src/maro_plugin/MaroAxisNode.cpp:174`에서:

```cpp
    aOutValue = angFn.create("outValue", "otv", MFnUnitAttribute::kAngle, 0.0);
```

를:

```cpp
    aOutValue = angFn.create("position", "otv", MFnUnitAttribute::kAngle, 0.0);
```

로 바꾼다(short name `otv`는 그대로 — 이미 다른 곳에서 쓰이지 않고, `MTypeId`처럼 안정적인 식별자로 남겨둔다).

- [ ] **Step 2: 5개 mayapy 테스트 파일에서 `.outValue`/`"outValue"`를 `.position`/`"position"`으로 교체**

`tests/maya/test_robustness.py`, `tests/maya/test_publish.py`, `tests/maya/test_contract.py`, `tests/maya/test_capability_stack.py`, `tests/maya/test_axis_node.py` 각 파일에서 `.outValue`(속성 접근, 예: `axis + ".outValue"`)와 문자열 `"outValue"`(예: `attributeQuery(...)`의 인자)를 전부 `.position`/`"position"`으로 바꾼다. 각 파일에서 정확히 다음 grep으로 남은 게 없는지 확인한다:

```bash
grep -n "outValue" tests/maya/test_robustness.py tests/maya/test_publish.py tests/maya/test_contract.py tests/maya/test_capability_stack.py tests/maya/test_axis_node.py
```

기대: 출력 없음(전부 바뀜).

- [ ] **Step 3: 빌드하고 전체 스위트가 통과하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure
```

기대: `maya_panel_commands`(사전 결함) 하나만 빼고 전부 통과. 5개 테스트 파일이 새 이름 `position`으로 여전히 통과하는 것이 이 rename의 검증이다.

- [ ] **Step 4: 커밋**

```bash
git add src/maro_plugin/MaroAxisNode.cpp tests/maya/test_robustness.py tests/maya/test_publish.py tests/maya/test_contract.py tests/maya/test_capability_stack.py tests/maya/test_axis_node.py
git commit -m "refactor: rename maroAxis.outValue to .position, matching JointState.msg"
```

---

### Task 2: `maro_lidar` 라이브러리 골격 + `RayPattern`

**Files:**
- Create: `src/maro_lidar/CMakeLists.txt`, `src/maro_lidar/include/maro_lidar/RayPattern.h`, `src/maro_lidar/src/RayPattern.cpp`
- Create: `tests/lidar/test_ray_pattern.cpp`
- Modify: 최상위 `CMakeLists.txt`, `tests/CMakeLists.txt`

**Interfaces:**
- Consumes: `maro::Vec3`(`maro_transform/Types.h`, 이미 존재 — `{double x, y, z}`)
- Produces: `maro::lidar::computeRayDirections(int verticalSamples, double verticalMinAngle, double verticalMaxAngle, int horizontalSamples, double horizontalMinAngle, double horizontalMaxAngle) -> std::vector<maro::Vec3>`

**설계 메모.** 반환되는 방향 벡터는 LiDAR 노드의 **로컬(오브젝트) 공간** 단위 벡터다 — 월드 변환은 이 함수의 책임이 아니다(Task 6에서 호출부가 노드의 월드 행렬을 곱한다). 로컬 프레임 정의: 로컬 +Z가 `수평각=0, 수직각=0`일 때의 정면, 로컬 +Y가 위(Maya의 월드 업 축과 같은 관례), 수평각은 +Z에서 +X 쪽으로 로컬 Y축을 중심으로 돈다:

```
x = cos(vertical) * sin(horizontal)
y = sin(vertical)
z = cos(vertical) * cos(horizontal)
```

각도 간격은 `sensor_msgs/msg/LaserScan.msg`의 실제 `angle_increment` 관례(`(angle_max - angle_min) / (샘플수 - 1)`, 양 끝값을 포함)를 그대로 따른다 — `verticalSamples`/`horizontalSamples`가 1이면 0으로 나누기를 피해 `MinAngle` 하나만 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/lidar/test_ray_pattern.cpp`(전체 새 파일):

```cpp
#include <cmath>

#include <gtest/gtest.h>

#include "maro_lidar/RayPattern.h"

namespace {
constexpr double kPi = 3.14159265358979323846;
constexpr double kEps = 1e-9;

double length(const maro::Vec3& v) {
    return std::sqrt(v.x * v.x + v.y * v.y + v.z * v.z);
}
}  // namespace

TEST(RayPattern, ReturnsExactlyVerticalTimesHorizontalCount) {
    const auto rays = maro::lidar::computeRayDirections(
        4, -0.1, 0.1, 8, -kPi, kPi);
    EXPECT_EQ(rays.size(), 4u * 8u);
}

TEST(RayPattern, EveryDirectionIsUnitLength) {
    const auto rays = maro::lidar::computeRayDirections(
        4, -0.2, 0.2, 8, -kPi, kPi);
    for (const auto& r : rays) {
        EXPECT_NEAR(length(r), 1.0, kEps);
    }
}

TEST(RayPattern, ZeroAngleZeroChannelPointsLocalForward) {
    // 채널 1개(수직각 0 고정), 수평 1개(수평각 0 고정) -- 정의상 로컬 +Z.
    const auto rays = maro::lidar::computeRayDirections(1, 0.0, 0.0, 1, 0.0, 0.0);
    ASSERT_EQ(rays.size(), 1u);
    EXPECT_NEAR(rays[0].x, 0.0, kEps);
    EXPECT_NEAR(rays[0].y, 0.0, kEps);
    EXPECT_NEAR(rays[0].z, 1.0, kEps);
}

TEST(RayPattern, PositiveVerticalAngleTiltsTowardLocalUp) {
    const auto rays = maro::lidar::computeRayDirections(1, kPi / 4.0, kPi / 4.0, 1, 0.0, 0.0);
    ASSERT_EQ(rays.size(), 1u);
    EXPECT_GT(rays[0].y, 0.0);
}

TEST(RayPattern, EndpointsSpanTheFullRequestedRange) {
    // 4개 샘플, [-1, 1] 구간이면 첫/마지막 값이 정확히 -1과 1이어야 한다
    // (LaserScan.msg 관례: 양 끝값 포함, 샘플수-1로 나눔).
    const auto rays = maro::lidar::computeRayDirections(1, 0.0, 0.0, 4, -1.0, 1.0);
    ASSERT_EQ(rays.size(), 4u);
    EXPECT_NEAR(rays[0].x, std::sin(-1.0), kEps);
    EXPECT_NEAR(rays[3].x, std::sin(1.0), kEps);
}

TEST(RayPattern, SingleSampleDoesNotDivideByZero) {
    const auto rays = maro::lidar::computeRayDirections(1, 0.3, 0.3, 1, 0.5, 0.5);
    ASSERT_EQ(rays.size(), 1u);
    EXPECT_TRUE(std::isfinite(rays[0].x));
    EXPECT_TRUE(std::isfinite(rays[0].y));
    EXPECT_TRUE(std::isfinite(rays[0].z));
}
```

`src/maro_lidar/CMakeLists.txt`(전체 새 파일):

```cmake
add_library(maro_lidar STATIC
    src/RayPattern.cpp
)

target_include_directories(maro_lidar PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(maro_lidar PUBLIC
    maro_transform
)

# Maya 2026 devkit이 플러그인 타깃을 C++17로 강제한다(devkit.cmake). 이 라이브러리는
# 플러그인에 링크되므로 표준을 맞춘다.
target_compile_features(maro_lidar PUBLIC cxx_std_17)
```

최상위 `CMakeLists.txt`의 `add_subdirectory(src/maro_transform)` 아래에 추가:

```cmake
add_subdirectory(src/maro_lidar)
```

`tests/CMakeLists.txt`의 `maro_transform_tests` 등록 블록(`gtest_discover_tests(maro_transform_tests)`) 바로 다음에 추가:

```cmake
add_executable(maro_lidar_tests
    lidar/test_ray_pattern.cpp
)

target_link_libraries(maro_lidar_tests PRIVATE
    maro_lidar
    GTest::gtest
    GTest::gtest_main
)

gtest_discover_tests(maro_lidar_tests)
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

기대: 빌드 실패 — `maro_lidar/RayPattern.h`가 없다.

- [ ] **Step 3: `RayPattern.h`/`.cpp` 작성**

`src/maro_lidar/include/maro_lidar/RayPattern.h`(전체 새 파일):

```cpp
#pragma once

#include <vector>

#include "maro_transform/Types.h"

namespace maro::lidar {

// 채널(수직)/해상도(수평) 스펙으로부터 LiDAR 노드의 로컬(오브젝트) 공간
// 기준 단위 방향 벡터 목록을 계산한다. 월드 변환은 호출부 책임이다.
//
// 로컬 프레임: +Z가 수평각=0/수직각=0일 때의 정면, +Y가 위(Maya 월드 업
// 축과 같은 관례), 수평각은 +Z에서 +X 쪽으로 로컬 Y축을 중심으로 돈다.
// 각도 간격은 sensor_msgs/msg/LaserScan.msg의 실제 angle_increment 관례
// ((max-min)/(샘플수-1), 양 끝값 포함)을 그대로 따른다.
//
// 반환 순서: 바깥쪽이 수직 채널, 안쪽이 수평 샘플(채널0의 수평 전체,
// 채널1의 수평 전체, ...). 채널 인덱스가 나중에 PointCloud2의 ring
// 필드로 쓰일 수 있어(범위 밖, §후속) 이 순서를 명시해 둔다.
std::vector<maro::Vec3> computeRayDirections(int verticalSamples, double verticalMinAngle,
                                              double verticalMaxAngle, int horizontalSamples,
                                              double horizontalMinAngle, double horizontalMaxAngle);

}  // namespace maro::lidar
```

`src/maro_lidar/src/RayPattern.cpp`(전체 새 파일):

```cpp
#include "maro_lidar/RayPattern.h"

#include <cmath>

namespace maro::lidar {

namespace {

// samples가 1이면 0으로 나누기를 피해 minAngle 하나만 쓴다.
double angleAt(int index, int samples, double minAngle, double maxAngle) {
    if (samples <= 1) return minAngle;
    return minAngle + (maxAngle - minAngle) * (static_cast<double>(index) /
                                                 static_cast<double>(samples - 1));
}

}  // namespace

std::vector<maro::Vec3> computeRayDirections(int verticalSamples, double verticalMinAngle,
                                              double verticalMaxAngle, int horizontalSamples,
                                              double horizontalMinAngle, double horizontalMaxAngle) {
    std::vector<maro::Vec3> directions;
    if (verticalSamples <= 0 || horizontalSamples <= 0) return directions;
    directions.reserve(static_cast<std::size_t>(verticalSamples) *
                        static_cast<std::size_t>(horizontalSamples));

    for (int v = 0; v < verticalSamples; ++v) {
        const double vertical = angleAt(v, verticalSamples, verticalMinAngle, verticalMaxAngle);
        const double cosV = std::cos(vertical);
        const double sinV = std::sin(vertical);
        for (int h = 0; h < horizontalSamples; ++h) {
            const double horizontal =
                angleAt(h, horizontalSamples, horizontalMinAngle, horizontalMaxAngle);
            directions.push_back(maro::Vec3{
                cosV * std::sin(horizontal),
                sinV,
                cosV * std::cos(horizontal),
            });
        }
    }
    return directions;
}

}  // namespace maro::lidar
```

- [ ] **Step 4: 테스트가 통과하는지 확인**

```powershell
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R RayPattern
```

기대: 6개 전부 통과.

- [ ] **Step 5: 일부러 깨서 확인**

`angleAt()`의 `samples <= 1` 가드를 임시로 지운다(`if (samples <= 1) return minAngle;` 줄을 주석 처리).

```powershell
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R RayPattern
```

기대: `SingleSampleDoesNotDivideByZero`가 **실패**한다(0/0 = NaN이 되어 `std::isfinite`가 false). 확인했으면 가드를 되돌린다.

```powershell
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R RayPattern
```

기대: 다시 6개 전부 통과.

- [ ] **Step 6: 커밋**

```bash
git add src/maro_lidar tests/lidar/test_ray_pattern.cpp tests/CMakeLists.txt CMakeLists.txt
git commit -m "feat: compute a lidar's local-space ray directions from its channel/fov spec"
```

---

### Task 3: `ScanEngine` (Embree 래퍼)

**Files:**
- Create: `src/maro_lidar/include/maro_lidar/ScanEngine.h`, `src/maro_lidar/src/ScanEngine.cpp`
- Create: `tests/lidar/test_scan_engine.cpp`
- Modify: `vcpkg.json`, `src/maro_lidar/CMakeLists.txt`, `tests/CMakeLists.txt`

**Interfaces:**
- Produces: `maro::lidar::RayHit{bool hit, maro::Vec3 position}`, `class maro::lidar::ScanEngine`(`ScanEngine()`, `~ScanEngine()`, `bool setMesh(const std::vector<float>& vertices, const std::vector<uint32_t>& indices)`, `RayHit castRay(const maro::Vec3& origin, const maro::Vec3& direction, double rangeMin, double rangeMax) const`)

**설계 메모.** `vertices`는 xyz가 이어진 평범한 배열(정점 개수 × 3), `indices`는 삼각형 정점 인덱스가 이어진 배열(삼각형 개수 × 3) — `MFnMesh`도 Embree 타입도 모른다(Task 6에서 `MFnMesh::getPoints()`/`getTriangles()` 결과를 이 형태로 변환해 넘긴다). `origin`/`direction`/결과 `position`은 전부 Maya 좌표계(호출부가 이미 월드 변환까지 마친 상태로 넘긴다) — 이 클래스는 좌표계를 모른다.

이 태스크는 이 플랜에서 가장 위험도가 높다 — Embree는 이 프로젝트가 처음 쓰는 라이브러리다. 아래 코드는 Embree 4.4.0의 문서화된 흐름을 반영하지만, **Step 3을 시작하기 전에 실제 설치된 헤더를 먼저 읽어라** (Step 1에서 vcpkg가 이미 받아둔다). 시그니처가 다르면 헤더를 따르고 무엇이 왜 달랐는지 기록한다.

- [ ] **Step 1: vcpkg에 Embree 추가하고 받기**

`vcpkg.json`의 `dependencies` 배열에 `"embree"`를 추가한다(전체 파일):

```json
{
  "$schema": "https://raw.githubusercontent.com/microsoft/vcpkg-tool/main/docs/vcpkg.schema.json",
  "name": "maya-ros-sim",
  "version-string": "0.1.0",
  "dependencies": [
    "gtest",
    "nlohmann-json",
    "embree"
  ]
}
```

```powershell
C:\src\vcpkg\vcpkg.exe install --triplet x64-windows
```

기대: `embree`와 전이 의존성 `tbb`가 설치된다(수 분 소요 — 이미 설치돼 있으면 빠르게 끝난다). 완료 후 다음 파일이 실제로 있는지 확인한다:

```powershell
Test-Path "C:\src\vcpkg\installed\x64-windows\include\embree4\rtcore.h"
```

기대: `True`.

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/lidar/test_scan_engine.cpp`(전체 새 파일):

```cpp
#include <gtest/gtest.h>

#include "maro_lidar/ScanEngine.h"

namespace {

// XY 평면에 놓인 한 변 2인 정사각형(원점이 중심), 삼각형 2개.
// z=0 평면, x/y가 [-1, 1] 범위를 덮는다.
std::vector<float> squareVertices() {
    return {
        -1.0f, -1.0f, 0.0f,
         1.0f, -1.0f, 0.0f,
         1.0f,  1.0f, 0.0f,
        -1.0f,  1.0f, 0.0f,
    };
}

std::vector<uint32_t> squareIndices() {
    return {0, 1, 2, 0, 2, 3};
}

}  // namespace

TEST(ScanEngine, RayStraightDownHitsTheSquare) {
    maro::lidar::ScanEngine engine;
    ASSERT_TRUE(engine.setMesh(squareVertices(), squareIndices()));

    // z=+5에서 -Z 방향으로 쏘면 z=0의 사각형과 (0,0,0)에서 만나야 한다.
    const auto hit = engine.castRay(maro::Vec3{0.0, 0.0, 5.0}, maro::Vec3{0.0, 0.0, -1.0},
                                     0.0, 100.0);
    ASSERT_TRUE(hit.hit);
    EXPECT_NEAR(hit.position.x, 0.0, 1e-4);
    EXPECT_NEAR(hit.position.y, 0.0, 1e-4);
    EXPECT_NEAR(hit.position.z, 0.0, 1e-4);
}

TEST(ScanEngine, RayMissingTheSquareReportsNoHit) {
    maro::lidar::ScanEngine engine;
    ASSERT_TRUE(engine.setMesh(squareVertices(), squareIndices()));

    // (10,10,5)에서 -Z로 쏘면 사각형([-1,1]x[-1,1])을 벗어난다.
    const auto hit = engine.castRay(maro::Vec3{10.0, 10.0, 5.0}, maro::Vec3{0.0, 0.0, -1.0},
                                     0.0, 100.0);
    EXPECT_FALSE(hit.hit);
}

TEST(ScanEngine, HitBeyondRangeMaxReportsNoHit) {
    maro::lidar::ScanEngine engine;
    ASSERT_TRUE(engine.setMesh(squareVertices(), squareIndices()));

    // 사각형은 원점에서 z=0에 있고 원점은 z=5 -- 거리 5인데 rangeMax를 1로 제한한다.
    const auto hit = engine.castRay(maro::Vec3{0.0, 0.0, 5.0}, maro::Vec3{0.0, 0.0, -1.0},
                                     0.0, 1.0);
    EXPECT_FALSE(hit.hit);
}

TEST(ScanEngine, HitBeforeRangeMinReportsNoHit) {
    maro::lidar::ScanEngine engine;
    ASSERT_TRUE(engine.setMesh(squareVertices(), squareIndices()));

    // rangeMin을 10으로 두면 거리 5인 충돌은 무시돼야 한다.
    const auto hit = engine.castRay(maro::Vec3{0.0, 0.0, 5.0}, maro::Vec3{0.0, 0.0, -1.0},
                                     10.0, 100.0);
    EXPECT_FALSE(hit.hit);
}

TEST(ScanEngine, SetMeshCanBeCalledAgainToReplaceGeometry) {
    maro::lidar::ScanEngine engine;
    ASSERT_TRUE(engine.setMesh(squareVertices(), squareIndices()));
    ASSERT_TRUE(engine.setMesh(squareVertices(), squareIndices()));  // 두 번째 호출도 성공해야 한다.

    const auto hit = engine.castRay(maro::Vec3{0.0, 0.0, 5.0}, maro::Vec3{0.0, 0.0, -1.0},
                                     0.0, 100.0);
    EXPECT_TRUE(hit.hit);
}
```

`src/maro_lidar/CMakeLists.txt`에 Embree 링크 추가(Task 2가 만든 파일 전체를 아래로 교체):

```cmake
find_package(embree 4 CONFIG REQUIRED)

add_library(maro_lidar STATIC
    src/RayPattern.cpp
    src/ScanEngine.cpp
)

target_include_directories(maro_lidar PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(maro_lidar PUBLIC
    maro_transform
)

target_link_libraries(maro_lidar PRIVATE
    embree
)

# Maya 2026 devkit이 플러그인 타깃을 C++17로 강제한다(devkit.cmake). 이 라이브러리는
# 플러그인에 링크되므로 표준을 맞춘다.
target_compile_features(maro_lidar PUBLIC cxx_std_17)
```

(`find_package(embree 4 CONFIG REQUIRED)`의 정확한 타깃 이름 `embree`가 실제로 맞는지는 Step 3에서 `embree-config.cmake`/CMake 출력으로 확인한다 — 다르면 이 블록을 실제 타깃 이름으로 고친다.)

`tests/CMakeLists.txt`의 `maro_lidar_tests` 블록(Task 2가 추가)에 소스와 링크를 추가(전체를 아래로 교체):

```cmake
add_executable(maro_lidar_tests
    lidar/test_ray_pattern.cpp
    lidar/test_scan_engine.cpp
)

target_link_libraries(maro_lidar_tests PRIVATE
    maro_lidar
    GTest::gtest
    GTest::gtest_main
)

gtest_discover_tests(maro_lidar_tests)
```

- [ ] **Step 3: 실제 Embree 헤더 확인 (구현 전 필수)**

```powershell
Get-Content "C:\src\vcpkg\installed\x64-windows\include\embree4\rtcore_ray.h" | Select-String "struct RTCRay|struct RTCHit|struct RTCRayHit" -Context 0,15
Get-Content "C:\src\vcpkg\installed\x64-windows\include\embree4\rtcore_geometry.h" | Select-String "rtcSetSharedGeometryBuffer|RTC_GEOMETRY_TYPE_TRIANGLE" -Context 0,5
Get-Content "C:\src\vcpkg\installed\x64-windows\share\embree4\embree4-config.cmake" | Select-String "add_library|IMPORTED"
```

이 출력으로 `RTCRay`/`RTCHit`/`RTCRayHit`의 실제 필드 이름(`org_x/y/z`, `dir_x/y/z`, `tnear`, `tfar`, `geomID`, `primID`, `Ng_x/y/z` 등으로 예상되지만 확인 필수)과, CMake가 노출하는 실제 임포트 타깃 이름(`embree` 또는 다른 이름일 수 있음)을 확인한다. Step 2에서 만든 CMake 블록의 타깃 이름이 다르면 여기서 고친다.

- [ ] **Step 4: `ScanEngine.h`/`.cpp` 작성**

`src/maro_lidar/include/maro_lidar/ScanEngine.h`(전체 새 파일):

```cpp
#pragma once

#include <cstdint>
#include <vector>

#include "maro_transform/Types.h"

// Embree 타입을 헤더에 노출하지 않는다 -- 전방 선언으로 포인터만 감싼다.
// 이 헤더를 포함하는 쪽(MaroLidarNode.cpp 등)이 embree4/rtcore.h를 몰라도 되게 한다.
typedef struct RTCDeviceTy* RTCDevice;
typedef struct RTCSceneTy* RTCScene;

namespace maro::lidar {

struct RayHit {
    bool hit = false;
    maro::Vec3 position;
};

// Embree RTCScene을 감싼다. Maya도, 좌표계도 모른다 -- 호출부가 넘기는
// vertices/indices/origin/direction이 어느 좌표계든 그 좌표계로 결과를
// 돌려준다(이 플랜에서는 항상 Maya 좌표계로 쓰인다, ScanEngine.h:GlobalConstraints 참고).
class ScanEngine {
public:
    ScanEngine();
    ~ScanEngine();

    ScanEngine(const ScanEngine&) = delete;
    ScanEngine& operator=(const ScanEngine&) = delete;

    // vertices: xyz가 이어진 배열(정점 개수 * 3). indices: 삼각형 정점
    // 인덱스가 이어진 배열(삼각형 개수 * 3). 다시 불러 기존 지오메트리를
    // 교체할 수 있다. 실패(빈 입력, Embree 오류)하면 false.
    bool setMesh(const std::vector<float>& vertices, const std::vector<std::uint32_t>& indices);

    // origin에서 direction(단위 벡터가 아니어도 되지만, 이 플랜에서는
    // RayPattern이 항상 단위 벡터를 준다) 방향으로 레이를 쏜다.
    // [rangeMin, rangeMax] 밖의 충돌은 무시한다.
    RayHit castRay(const maro::Vec3& origin, const maro::Vec3& direction, double rangeMin,
                   double rangeMax) const;

private:
    RTCDevice device_ = nullptr;
    RTCScene scene_ = nullptr;
};

}  // namespace maro::lidar
```

`src/maro_lidar/src/ScanEngine.cpp`(전체 새 파일 — **Step 3에서 확인한 실제 헤더 필드명에 맞춰 아래 코드를 조정할 것**, 이 코드는 Embree 4의 문서화된 흐름을 반영한 출발점이다):

```cpp
#include "maro_lidar/ScanEngine.h"

#include <embree4/rtcore.h>

namespace maro::lidar {

ScanEngine::ScanEngine() {
    device_ = rtcNewDevice(nullptr);
}

ScanEngine::~ScanEngine() {
    if (scene_ != nullptr) rtcReleaseScene(scene_);
    if (device_ != nullptr) rtcReleaseDevice(device_);
}

bool ScanEngine::setMesh(const std::vector<float>& vertices, const std::vector<std::uint32_t>& indices) {
    if (device_ == nullptr) return false;
    if (vertices.empty() || indices.empty()) return false;
    if (vertices.size() % 3 != 0 || indices.size() % 3 != 0) return false;

    if (scene_ != nullptr) {
        rtcReleaseScene(scene_);
        scene_ = nullptr;
    }
    scene_ = rtcNewScene(device_);

    RTCGeometry geom = rtcNewGeometry(device_, RTC_GEOMETRY_TYPE_TRIANGLE);

    const std::size_t vertexCount = vertices.size() / 3;
    float* vertexBuffer = static_cast<float*>(rtcSetNewGeometryBuffer(
        geom, RTC_BUFFER_TYPE_VERTEX, 0, RTC_FORMAT_FLOAT3, 3 * sizeof(float), vertexCount));
    for (std::size_t i = 0; i < vertices.size(); ++i) vertexBuffer[i] = vertices[i];

    const std::size_t triangleCount = indices.size() / 3;
    unsigned int* indexBuffer = static_cast<unsigned int*>(rtcSetNewGeometryBuffer(
        geom, RTC_BUFFER_TYPE_INDEX, 0, RTC_FORMAT_UINT3, 3 * sizeof(unsigned int), triangleCount));
    for (std::size_t i = 0; i < indices.size(); ++i) {
        indexBuffer[i] = static_cast<unsigned int>(indices[i]);
    }

    rtcCommitGeometry(geom);
    rtcAttachGeometry(scene_, geom);
    rtcReleaseGeometry(geom);  // scene_이 자체적으로 참조를 갖는다.
    rtcCommitScene(scene_);

    return true;
}

RayHit ScanEngine::castRay(const maro::Vec3& origin, const maro::Vec3& direction, double rangeMin,
                            double rangeMax) const {
    RayHit result;
    if (scene_ == nullptr) return result;

    RTCRayHit rayhit;
    rayhit.ray.org_x = static_cast<float>(origin.x);
    rayhit.ray.org_y = static_cast<float>(origin.y);
    rayhit.ray.org_z = static_cast<float>(origin.z);
    rayhit.ray.dir_x = static_cast<float>(direction.x);
    rayhit.ray.dir_y = static_cast<float>(direction.y);
    rayhit.ray.dir_z = static_cast<float>(direction.z);
    rayhit.ray.tnear = static_cast<float>(rangeMin);
    rayhit.ray.tfar = static_cast<float>(rangeMax);
    rayhit.ray.mask = static_cast<unsigned int>(-1);
    rayhit.ray.flags = 0;
    rayhit.hit.geomID = RTC_INVALID_GEOMETRY_ID;
    rayhit.hit.instID[0] = RTC_INVALID_GEOMETRY_ID;

    rtcIntersect1(scene_, &rayhit);

    if (rayhit.hit.geomID == RTC_INVALID_GEOMETRY_ID) return result;

    result.hit = true;
    result.position = maro::Vec3{
        origin.x + direction.x * rayhit.ray.tfar,
        origin.y + direction.y * rayhit.ray.tfar,
        origin.z + direction.z * rayhit.ray.tfar,
    };
    return result;
}

}  // namespace maro::lidar
```

- [ ] **Step 5: 빌드하고 실제 헤더와 다른 부분 고치기**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

컴파일 오류가 나면(구조체 필드 이름이 Step 3에서 확인한 것과 다르거나, CMake 타깃 이름이 다른 경우) 실제 헤더/CMake 설정을 따라 고친다 — 무엇을 왜 고쳤는지 Task 보고서에 남긴다.

- [ ] **Step 6: 테스트가 통과하는지 확인**

```bash
ctest --test-dir out/build -C Release --output-on-failure -R ScanEngine
```

기대: 5개 전부 통과.

- [ ] **Step 7: 일부러 깨서 확인**

`castRay()`의 `if (rayhit.hit.geomID == RTC_INVALID_GEOMETRY_ID) return result;` 다음 줄부터 끝까지를 임시로, geomID 값과 무관하게 항상 `result.hit = true;`를 반환하도록 바꾼다(즉 "충돌 없음" 판정 자체를 무력화).

```powershell
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R ScanEngine
```

기대: `RayMissingTheSquareReportsNoHit`, `HitBeyondRangeMaxReportsNoHit`, `HitBeforeRangeMinReportsNoHit`가 **실패**한다(항상 hit=true를 반환하므로). 확인했으면 원래 코드로 되돌린다.

```powershell
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R ScanEngine
```

기대: 다시 5개 전부 통과.

- [ ] **Step 8: 커밋**

```bash
git add vcpkg.json src/maro_lidar tests/lidar/test_scan_engine.cpp tests/CMakeLists.txt
git commit -m "feat: wrap an Embree scene for single-ray mesh intersection"
```

---

### Task 4: `PointCloudPacking`

**Files:**
- Create: `src/maro_lidar/include/maro_lidar/PointCloudPacking.h`, `src/maro_lidar/src/PointCloudPacking.cpp`
- Create: `tests/lidar/test_point_cloud_packing.cpp`
- Modify: `src/maro_lidar/CMakeLists.txt`, `tests/CMakeLists.txt`

**Interfaces:**
- Consumes: `maro::Vec3`(`maro_transform/Types.h`)
- Produces: `maro::lidar::PackedPointCloud{std::vector<std::uint8_t> data, std::uint32_t pointStep, std::uint32_t width}`, `maro::lidar::packPointCloud(const std::vector<maro::Vec3>& points, const std::vector<float>& intensities) -> PackedPointCloud`

**설계 메모.** `points`는 이미 ROS 좌표계로 변환된 값이어야 한다(이 함수는 좌표 변환을 하지 않는다 — Task 6이 `maro::mayaToRosPosition()`으로 변환한 뒤 넘긴다). `points.size() != intensities.size()`면 실패로 취급하지 않고 `intensities`가 부족한 자리는 0.0f로 채운다(단순함 우선 — 워킹 스켈레톤은 강도값을 실제로 계산하지 않고 항상 빈 배열을 넘길 것이므로, 이 규칙이 실질적으로 항상 적용된다). 필드 레이아웃: `x`(offset 0), `y`(offset 4), `z`(offset 8), `intensity`(offset 12), 전부 `float32`, `point_step = 16`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/lidar/test_point_cloud_packing.cpp`(전체 새 파일):

```cpp
#include <cstring>

#include <gtest/gtest.h>

#include "maro_lidar/PointCloudPacking.h"

TEST(PointCloudPacking, PointStepIsSixteenBytes) {
    const auto packed = maro::lidar::packPointCloud({}, {});
    EXPECT_EQ(packed.pointStep, 16u);
}

TEST(PointCloudPacking, EmptyInputProducesZeroWidthAndEmptyData) {
    const auto packed = maro::lidar::packPointCloud({}, {});
    EXPECT_EQ(packed.width, 0u);
    EXPECT_TRUE(packed.data.empty());
}

TEST(PointCloudPacking, WidthMatchesPointCount) {
    const std::vector<maro::Vec3> points = {
        maro::Vec3{1.0, 2.0, 3.0},
        maro::Vec3{4.0, 5.0, 6.0},
    };
    const auto packed = maro::lidar::packPointCloud(points, {0.5f, 0.75f});
    EXPECT_EQ(packed.width, 2u);
    EXPECT_EQ(packed.data.size(), 2u * 16u);
}

TEST(PointCloudPacking, XyzAndIntensityAreCorrectlyPackedAsLittleEndianFloat32) {
    const std::vector<maro::Vec3> points = {maro::Vec3{1.5, -2.5, 3.25}};
    const auto packed = maro::lidar::packPointCloud(points, {0.9f});
    ASSERT_EQ(packed.data.size(), 16u);

    float x = 0.0f, y = 0.0f, z = 0.0f, intensity = 0.0f;
    std::memcpy(&x, packed.data.data() + 0, sizeof(float));
    std::memcpy(&y, packed.data.data() + 4, sizeof(float));
    std::memcpy(&z, packed.data.data() + 8, sizeof(float));
    std::memcpy(&intensity, packed.data.data() + 12, sizeof(float));

    EXPECT_FLOAT_EQ(x, 1.5f);
    EXPECT_FLOAT_EQ(y, -2.5f);
    EXPECT_FLOAT_EQ(z, 3.25f);
    EXPECT_FLOAT_EQ(intensity, 0.9f);
}

TEST(PointCloudPacking, MissingIntensitiesAreFilledWithZero) {
    const std::vector<maro::Vec3> points = {maro::Vec3{1.0, 1.0, 1.0}};
    const auto packed = maro::lidar::packPointCloud(points, {});  // intensities 없음
    ASSERT_EQ(packed.data.size(), 16u);

    float intensity = -1.0f;
    std::memcpy(&intensity, packed.data.data() + 12, sizeof(float));
    EXPECT_FLOAT_EQ(intensity, 0.0f);
}
```

`src/maro_lidar/CMakeLists.txt`의 `add_library(maro_lidar STATIC` 목록에 추가:

```cmake
    src/PointCloudPacking.cpp
```

`tests/CMakeLists.txt`의 `maro_lidar_tests` 소스 목록에 추가:

```cmake
    lidar/test_point_cloud_packing.cpp
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```powershell
cmake --build out/build --config Release
```

기대: 빌드 실패 — `maro_lidar/PointCloudPacking.h`가 없다.

- [ ] **Step 3: `PointCloudPacking.h`/`.cpp` 작성**

`src/maro_lidar/include/maro_lidar/PointCloudPacking.h`(전체 새 파일):

```cpp
#pragma once

#include <cstdint>
#include <vector>

#include "maro_transform/Types.h"

namespace maro::lidar {

// sensor_msgs/msg/PointCloud2의 실제 바이너리 레이아웃(point_step/data)만
// 만든다 -- 메시지 타입 자체(rclcpp/sensor_msgs 헤더)는 모른다. 호출부가
// 이 바이트를 실제 PointCloud2 메시지의 data 필드에 그대로 복사하고,
// fields/point_step/row_step/height/width/is_bigendian/is_dense를 이
// 구조체 값으로 채운다.
struct PackedPointCloud {
    std::vector<std::uint8_t> data;
    std::uint32_t pointStep = 0;
    std::uint32_t width = 0;
};

// points는 이미 ROS 좌표계(Z-up)로 변환된 값이어야 한다 -- 이 함수는
// 좌표 변환을 하지 않는다. 필드 레이아웃: x(offset 0)/y(4)/z(8)/
// intensity(12), 전부 float32, point_step=16.
// intensities가 points보다 짧으면 남는 자리는 0.0f로 채운다.
PackedPointCloud packPointCloud(const std::vector<maro::Vec3>& points,
                                 const std::vector<float>& intensities);

}  // namespace maro::lidar
```

`src/maro_lidar/src/PointCloudPacking.cpp`(전체 새 파일):

```cpp
#include "maro_lidar/PointCloudPacking.h"

#include <cstring>

namespace maro::lidar {

namespace {
constexpr std::uint32_t kPointStep = 16;  // x,y,z,intensity, 전부 float32.
}

PackedPointCloud packPointCloud(const std::vector<maro::Vec3>& points,
                                 const std::vector<float>& intensities) {
    PackedPointCloud result;
    result.pointStep = kPointStep;
    result.width = static_cast<std::uint32_t>(points.size());
    result.data.resize(points.size() * kPointStep);

    for (std::size_t i = 0; i < points.size(); ++i) {
        const float x = static_cast<float>(points[i].x);
        const float y = static_cast<float>(points[i].y);
        const float z = static_cast<float>(points[i].z);
        const float intensity = (i < intensities.size()) ? intensities[i] : 0.0f;

        std::uint8_t* dst = result.data.data() + i * kPointStep;
        std::memcpy(dst + 0, &x, sizeof(float));
        std::memcpy(dst + 4, &y, sizeof(float));
        std::memcpy(dst + 8, &z, sizeof(float));
        std::memcpy(dst + 12, &intensity, sizeof(float));
    }

    return result;
}

}  // namespace maro::lidar
```

- [ ] **Step 4: 테스트가 통과하는지 확인**

```powershell
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R PointCloudPacking
```

기대: 5개 전부 통과.

- [ ] **Step 5: 일부러 깨서 확인**

`packPointCloud()`에서 `x`/`y`/`z`를 쓰는 순서를 임시로 바꾼다(예: `dst + 0`에 `y`를, `dst + 4`에 `x`를 쓰도록 뒤바꾼다).

```powershell
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R PointCloudPacking
```

기대: `XyzAndIntensityAreCorrectlyPackedAsLittleEndianFloat32`가 **실패**한다. 확인했으면 되돌린다.

```powershell
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R PointCloudPacking
```

기대: 다시 5개 전부 통과.

- [ ] **Step 6: 커밋**

```bash
git add src/maro_lidar/include/maro_lidar/PointCloudPacking.h src/maro_lidar/src/PointCloudPacking.cpp src/maro_lidar/CMakeLists.txt tests/lidar/test_point_cloud_packing.cpp tests/CMakeLists.txt
git commit -m "feat: pack ray-hit points into PointCloud2's actual binary layout"
```

---

### Task 5: `MaroLidarNode` (Maya 노드)

**Files:**
- Create: `src/maro_plugin/MaroLidarNode.h`, `src/maro_plugin/MaroLidarNode.cpp`
- Create: `tests/maya/test_lidar_node.py`
- Modify: `src/maro_plugin/CMakeLists.txt`, `src/maro_plugin/MaroPluginMain.cpp`, `tests/CMakeLists.txt`

**Interfaces:**
- Produces: Maya 노드 타입 `"maroLidar"`, `MTypeId 0x00135106`(기존 `maroCommandDevice`의 `0x00135105` 다음 번호), 어트리뷰트 아래 표.

| C++ 멤버 | 롱네임 | 숏네임 | 타입 | 기본값 |
|---|---|---|---|---|
| `aVerticalSamples` | `verticalSamples` | `vts` | int | 4 |
| `aVerticalMinAngle` | `verticalMinAngle` | `vmn` | double | -0.1 |
| `aVerticalMaxAngle` | `verticalMaxAngle` | `vmx` | double | 0.1 |
| `aHorizontalSamples` | `horizontalSamples` | `hts` | int | 36 |
| `aHorizontalMinAngle` | `horizontalMinAngle` | `hmn` | double | -3.14159265358979 |
| `aHorizontalMaxAngle` | `horizontalMaxAngle` | `hmx` | double | 3.14159265358979 |
| `aRangeMin` | `rangeMin` | `rmn` | double | 0.1 |
| `aRangeMax` | `rangeMax` | `rmx` | double | 30.0 |
| `aUpdateRate` | `updateRate` | `upr` | double | 10.0 |
| `aFrameId` | `frameId` | `fri` | string | `"lidar_link"` |
| `aTargetMeshes` | `targetMeshes` | `tgm` | message array | (연결 없음) |
| `aEnabled` | `enabled` | `enb` | bool | true |

이 태스크는 `compute()`가 어떤 값도 계산하지 않는다(레이캐스팅은 Task 6에서 펌프가 주도) — `MaroCommandDeviceNode::aCommandOut`처럼 값 자체가 아니라 존재만 하는 어트리뷰트가 필요 없다(펌프가 이 노드의 인스턴스를 직접 순회하며 어트리뷰트를 읽으므로, dirty 트리거용 출력이 필요 없다 — Task 6에서 확정).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/maya/test_lidar_node.py`(전체 새 파일, `tests/maya/test_axis_node.py`의 패턴을 그대로 따른다):

```python
"""maroLidar 노드가 등록되고 기대한 어트리뷰트/기본값을 갖는지 확인한다."""
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)

cmds.file(new=True, force=True)
lidar = cmds.createNode("maroLidar")
print("created:", lidar)

expected = [
    "verticalSamples",
    "verticalMinAngle",
    "verticalMaxAngle",
    "horizontalSamples",
    "horizontalMinAngle",
    "horizontalMaxAngle",
    "rangeMin",
    "rangeMax",
    "updateRate",
    "frameId",
    "targetMeshes",
    "enabled",
]
for attr in expected:
    assert cmds.attributeQuery(attr, node=lidar, exists=True), f"missing attr: {attr}"
print("attributes OK")

assert cmds.getAttr(lidar + ".verticalSamples") == 4
assert cmds.getAttr(lidar + ".horizontalSamples") == 36
assert cmds.getAttr(lidar + ".rangeMin") == 0.1
assert cmds.getAttr(lidar + ".rangeMax") == 30.0
assert cmds.getAttr(lidar + ".updateRate") == 10.0
assert cmds.getAttr(lidar + ".frameId") == "lidar_link"
assert cmds.getAttr(lidar + ".enabled") is True
print("defaults OK")

# targetMeshes에 실제 메쉬를 연결할 수 있는지 확인한다(capabilityIn과
# 같은 방식 -- 새 바인딩 커맨드 없이 connectAttr로 직접).
cube = cmds.polyCube(name="scanTarget")[0]
cmds.connectAttr(cube + ".message", lidar + ".targetMeshes[0]")
connections = cmds.listConnections(lidar + ".targetMeshes[0]", source=True) or []
assert cube in connections, f"targetMeshes[0] did not connect to {cube}: {connections}"
print("targetMeshes binding OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
```

`tests/CMakeLists.txt`의 `foreach(maya_test load axis_node binding ...)` 목록(§기존 `sentinel`이 이미 들어있는 그 목록)에 `lidar_node`를 추가한다.

- [ ] **Step 2: 테스트가 실패하는지 확인**

```powershell
& "$env:MAYA_LOCATION\bin\mayapy.exe" tests\maya\test_lidar_node.py
```

기대: `RuntimeError` 또는 유사한 오류 — `maroLidar` 노드 타입이 등록돼 있지 않다(아직 `MaroPluginMain.cpp`에 등록 안 됨). `$env:MARO_PLUGIN_PATH` 환경변수를 먼저 설정해야 한다(CMake로 빌드 후 ctest로 돌리면 자동 설정됨 — 손으로 먼저 시도해도 되고, Step 6에서 ctest로 확실히 확인한다).

- [ ] **Step 3: `MaroLidarNode.h`/`.cpp` 작성**

`src/maro_plugin/MaroLidarNode.h`(전체 새 파일):

```cpp
#pragma once

#include <maya/MObject.h>
#include <maya/MPxLocatorNode.h>
#include <maya/MStatus.h>
#include <maya/MTypeId.h>

namespace maro {

// LiDAR 센서 하나의 단일 진실 원천. maroAxis와 같은 패턴(MPxLocatorNode)을
// 따른다 -- 뷰포트에 그려지는 로케이터지만, 이 태스크는 그리기를 구현하지
// 않는다(범위 밖, 워킹 스켈레톤 스펙 §7 참고). compute()도 값을 계산하지
// 않는다 -- 실제 스캔은 MaroPump가 이 노드 인스턴스를 직접 순회하며
// 어트리뷰트를 읽어 주도한다(Task 6).
class MaroLidarNode : public MPxLocatorNode {
public:
    static void* creator();
    static MStatus initialize();

    static MTypeId id;

    static MObject aVerticalSamples;
    static MObject aVerticalMinAngle;
    static MObject aVerticalMaxAngle;
    static MObject aHorizontalSamples;
    static MObject aHorizontalMinAngle;
    static MObject aHorizontalMaxAngle;
    static MObject aRangeMin;
    static MObject aRangeMax;
    static MObject aUpdateRate;
    static MObject aFrameId;
    static MObject aTargetMeshes;
    static MObject aEnabled;
};

}  // namespace maro
```

`src/maro_plugin/MaroLidarNode.cpp`(전체 새 파일):

```cpp
#include "MaroLidarNode.h"

#include <maya/MFnMessageAttribute.h>
#include <maya/MFnNumericAttribute.h>
#include <maya/MFnStringData.h>
#include <maya/MFnTypedAttribute.h>
#include <maya/MFnUnitAttribute.h>

namespace maro {

MTypeId MaroLidarNode::id(0x00135106);

MObject MaroLidarNode::aVerticalSamples;
MObject MaroLidarNode::aVerticalMinAngle;
MObject MaroLidarNode::aVerticalMaxAngle;
MObject MaroLidarNode::aHorizontalSamples;
MObject MaroLidarNode::aHorizontalMinAngle;
MObject MaroLidarNode::aHorizontalMaxAngle;
MObject MaroLidarNode::aRangeMin;
MObject MaroLidarNode::aRangeMax;
MObject MaroLidarNode::aUpdateRate;
MObject MaroLidarNode::aFrameId;
MObject MaroLidarNode::aTargetMeshes;
MObject MaroLidarNode::aEnabled;

void* MaroLidarNode::creator() { return new MaroLidarNode(); }

MStatus MaroLidarNode::initialize() {
    MFnNumericAttribute numFn;
    MFnUnitAttribute angFn;
    MFnTypedAttribute typedFn;
    MFnMessageAttribute msgFn;
    MFnStringData stringDataFn;

    aVerticalSamples = numFn.create("verticalSamples", "vts", MFnNumericData::kInt, 4);
    numFn.setKeyable(true);
    addAttribute(aVerticalSamples);

    aVerticalMinAngle = angFn.create("verticalMinAngle", "vmn", MFnUnitAttribute::kAngle, -0.1);
    angFn.setKeyable(true);
    addAttribute(aVerticalMinAngle);

    aVerticalMaxAngle = angFn.create("verticalMaxAngle", "vmx", MFnUnitAttribute::kAngle, 0.1);
    angFn.setKeyable(true);
    addAttribute(aVerticalMaxAngle);

    aHorizontalSamples = numFn.create("horizontalSamples", "hts", MFnNumericData::kInt, 36);
    numFn.setKeyable(true);
    addAttribute(aHorizontalSamples);

    aHorizontalMinAngle =
        angFn.create("horizontalMinAngle", "hmn", MFnUnitAttribute::kAngle, -3.14159265358979);
    angFn.setKeyable(true);
    addAttribute(aHorizontalMinAngle);

    aHorizontalMaxAngle =
        angFn.create("horizontalMaxAngle", "hmx", MFnUnitAttribute::kAngle, 3.14159265358979);
    angFn.setKeyable(true);
    addAttribute(aHorizontalMaxAngle);

    aRangeMin = numFn.create("rangeMin", "rmn", MFnNumericData::kDouble, 0.1);
    numFn.setKeyable(true);
    addAttribute(aRangeMin);

    aRangeMax = numFn.create("rangeMax", "rmx", MFnNumericData::kDouble, 30.0);
    numFn.setKeyable(true);
    addAttribute(aRangeMax);

    aUpdateRate = numFn.create("updateRate", "upr", MFnNumericData::kDouble, 10.0);
    numFn.setKeyable(true);
    addAttribute(aUpdateRate);

    MObject defaultFrameId = stringDataFn.create("lidar_link");
    aFrameId = typedFn.create("frameId", "fri", MFnData::kString, defaultFrameId);
    typedFn.setKeyable(false);
    addAttribute(aFrameId);

    aTargetMeshes = msgFn.create("targetMeshes", "tgm");
    msgFn.setArray(true);
    msgFn.setIndexMatters(true);
    addAttribute(aTargetMeshes);

    aEnabled = numFn.create("enabled", "enb", MFnNumericData::kBoolean, true);
    numFn.setKeyable(true);
    addAttribute(aEnabled);

    return MS::kSuccess;
}

}  // namespace maro
```

- [ ] **Step 4: 플러그인 등록에 추가**

`src/maro_plugin/CMakeLists.txt`의 `SOURCE_FILES` 목록에 추가:

```cmake
    MaroLidarNode.cpp
```

`src/maro_plugin/MaroPluginMain.cpp`의 `#include` 목록에 추가:

```cpp
#include "MaroLidarNode.h"
```

`initializePlugin`에서 `maroAxis`(`MaroAxisNode`) 등록 바로 다음에 추가(기존 `plugin.registerNode("maroAxis", ...)` 호출과 같은 패턴):

```cpp
    status = plugin.registerNode("maroLidar", maro::MaroLidarNode::id, &maro::MaroLidarNode::creator,
                                  &maro::MaroLidarNode::initialize, MPxNode::kLocatorNode);
    if (!status) {
        status.perror("Maro: failed to register maroLidar node");
        return status;
    }
```

`uninitializePlugin`에서 `maroAxis` 등록 해제 바로 다음(등록의 역순 규율)에 추가:

```cpp
    status = plugin.deregisterNode(maro::MaroLidarNode::id);
    if (!status) status.perror("Maro: failed to deregister maroLidar node");
```

- [ ] **Step 5: `tests/CMakeLists.txt`에 mayapy 테스트 등록**

`foreach(maya_test load axis_node binding ... sentinel)` 목록에 `lidar_node`를 추가(리스트 마지막에):

```cmake
    foreach(maya_test load axis_node binding capability_stack delete_rules
                      robustness diag_boad diag_onfix diag_book
                      diag_book_cross_session diag_remedy
                      diag_degraded diag_degraded_remedy diag_thread
                      panel_commands journal remedy_capture
                      remedy_availability remedy_ambiguous_names
                      main_thread_queue remedy_apply sentinel lidar_node)
```

- [ ] **Step 6: 빌드하고 테스트가 통과하는지 확인**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R maya_lidar_node
```

기대: 통과.

- [ ] **Step 7: 커밋**

```bash
git add src/maro_plugin/MaroLidarNode.h src/maro_plugin/MaroLidarNode.cpp src/maro_plugin/CMakeLists.txt src/maro_plugin/MaroPluginMain.cpp tests/maya/test_lidar_node.py tests/CMakeLists.txt
git commit -m "feat: register the maroLidar node with its scan-spec attributes"
```

---

### Task 6: 발행 배선 — 캡처(`MaroPump`), 스캔, 큐잉, 발행(`MaroRosRuntime`)

**Files:**
- Modify: `src/maro_plugin/MaroBridgeQueues.h`, `src/maro_plugin/MaroRosRuntime.h`, `src/maro_plugin/MaroRosRuntime.cpp`, `src/maro_plugin/MaroPump.h`, `src/maro_plugin/MaroPump.cpp`, `src/maro_plugin/CMakeLists.txt`
- Create: `tests/maya/test_lidar_publish.py`

**Interfaces:**
- Consumes: `maro::lidar::computeRayDirections(...)`(Task 2), `maro::lidar::ScanEngine`(Task 3), `maro::lidar::packPointCloud(...)`(Task 4), `maro::MaroLidarNode`의 어트리뷰트(Task 5), `maro::mayaToRosPosition(const maro::Vec3&, const maro::SceneUnit&)`(기존, `src/maro_transform/include/maro_transform/Convert.h`)

**실제 기존 발행 흐름 (이미 읽어 확인함, `AxisSample`/`joint_states`/`tf` 경로)**: `MaroPump::onTimer()`가 **메인 스레드**에서 30Hz로 불려(`MTimerMessage`), `collectSamples()`가 씬의 `maroAxis`를 순회하며 `AxisSample`(Maya 좌표계 그대로, 좌표 변환 없이)을 만들어 `runtime.publishQueue()`(`BoundedQueue<AxisSample>`)에 push만 한다. **좌표 변환(`mayaToRosPosition`/`mayaToRosRotation`)은 메인 스레드가 아니라 `MaroRosRuntime::drainAndPublish()`(백그라운드 스레드, `spinLoop()`가 5ms마다 부름)에서 일어난다** — 큐를 드레인하며 각 샘플을 ROS 메시지로 바꾸고 `m_impl->jointPub`/`m_impl->tfPub`로 발행한다. 토픽은 `"/" + robotName + "/joint_states"`(절대 경로, 노드 네임스페이스와 무관 — `MaroRosRuntime.cpp:41-43`의 실제 주석이 그렇게 설명한다).

**이 태스크는 이 패턴을 그대로 따른다** — 워킹 스켈레톤 스펙 §Global Constraints의 "좌표 변환은 딱 한 곳"은 어느 스레드냐가 아니라 **몇 번 적용되느냐**를 말한 것이므로, 기존 축 파이프라인과 똑같이 배경 스레드에서 변환해도 그 제약을 어기지 않는다 — 오히려 기존 코드와 다른 자리에서 변환하면 이 프로젝트 안에 좌표 변환 지점이 두 군데(일관성 없음)가 된다.

**1. `MaroBridgeQueues.h`에 `LidarSample` 추가** (기존 `AxisSample` 바로 아래):

```cpp
// 메인 스레드 -> 백그라운드(발행 방향). AxisSample과 같은 이유로 좌표
// 변환 전(Maya 좌표계 그대로) 값을 나른다 -- 변환은 drainAndPublish()가
// 한다. points는 이미 레이캐스팅이 끝난 충돌 지점들(월드 공간, Maya
// 좌표계)이다.
struct LidarSample {
    std::string frameId;
    SceneUnit unit;
    std::vector<Vec3> points;
};
```

**2. `MaroRosRuntime.h`에 큐 접근자 추가** (기존 `publishQueue()` 바로 아래):

```cpp
    BoundedQueue<LidarSample>& lidarQueue() { return m_lidarQueue; }
```

`private:` 섹션의 `BoundedQueue<AxisSample> m_publishQueue;` 바로 아래에 추가:

```cpp
    BoundedQueue<LidarSample> m_lidarQueue;
```

**3. `MaroRosRuntime.cpp` 수정**:

`#include` 목록에 추가:

```cpp
#include <sensor_msgs/msg/point_cloud2.hpp>

#include "maro_lidar/PointCloudPacking.h"
```

`Impl` 구조체(`struct MaroRosRuntime::Impl`)에 추가:

```cpp
    rclcpp::Publisher<sensor_msgs::msg::PointCloud2>::SharedPtr lidarPub;
```

`start()`에서 `m_impl->tfPub = ...` 생성 바로 다음에 추가(같은 `try` 블록 안, 같은 네임스페이스 관례 — `"/" + robotName + "/points"`):

```cpp
        m_impl->lidarPub =
            m_impl->node->create_publisher<sensor_msgs::msg::PointCloud2>(
                "/" + robotName + "/points", 10);
```

같은 `catch` 블록들의 정리 목록에도 추가(`m_impl->tfPub.reset();` 옆에 `m_impl->lidarPub.reset();` — 두 `catch` 블록 모두).

`drainAndPublish()` 맨 끝(`tf.transforms.push_back(t);` 루프가 끝나고 `m_impl->jointPub->publish(joints);`/`m_impl->tfPub->publish(tf);` 호출 이후)에 LiDAR 드레인을 추가:

```cpp
    const std::vector<LidarSample> lidarSamples = m_lidarQueue.drain();
    if (!lidarSamples.empty() && m_impl->lidarPub) {
        m_drainedSamples.fetch_add(lidarSamples.size(), std::memory_order_relaxed);
        for (const LidarSample& sample : lidarSamples) {
            std::vector<Vec3> rosPoints;
            rosPoints.reserve(sample.points.size());
            for (const Vec3& p : sample.points) {
                rosPoints.push_back(mayaToRosPosition(p, sample.unit));
            }
            const maro::lidar::PackedPointCloud packed =
                maro::lidar::packPointCloud(rosPoints, {});

            sensor_msgs::msg::PointCloud2 cloud;
            cloud.header.stamp = m_impl->node->now();
            cloud.header.frame_id = sample.frameId;
            cloud.height = 1;
            cloud.width = packed.width;
            cloud.is_bigendian = false;
            cloud.is_dense = true;
            cloud.point_step = packed.pointStep;
            cloud.row_step = packed.pointStep * packed.width;

            sensor_msgs::msg::PointField fieldX, fieldY, fieldZ, fieldIntensity;
            fieldX.name = "x"; fieldX.offset = 0; fieldX.datatype = sensor_msgs::msg::PointField::FLOAT32; fieldX.count = 1;
            fieldY.name = "y"; fieldY.offset = 4; fieldY.datatype = sensor_msgs::msg::PointField::FLOAT32; fieldY.count = 1;
            fieldZ.name = "z"; fieldZ.offset = 8; fieldZ.datatype = sensor_msgs::msg::PointField::FLOAT32; fieldZ.count = 1;
            fieldIntensity.name = "intensity"; fieldIntensity.offset = 12; fieldIntensity.datatype = sensor_msgs::msg::PointField::FLOAT32; fieldIntensity.count = 1;
            cloud.fields = {fieldX, fieldY, fieldZ, fieldIntensity};

            cloud.data = packed.data;

            m_impl->lidarPub->publish(cloud);
        }
    }
```

(`sensor_msgs::msg::PointField`는 `sensor_msgs/msg/point_cloud2.hpp`가 이미 끌고 들어온다 — 확인 후 안 되면 `#include <sensor_msgs/msg/point_field.hpp>`를 추가한다.)

**4. `MaroPump.cpp` 수정 — LiDAR 캡처**

`#include` 목록에 추가:

```cpp
#include <maya/MFnMesh.h>
#include <maya/MIntArray.h>
#include <maya/MPoint.h>
#include <maya/MPointArray.h>

#include "maro_lidar/RayPattern.h"
#include "maro_lidar/ScanEngine.h"
#include "MaroLidarNode.h"
```

`collectSamples()`가 끝나는 `}` 바로 다음(같은 `namespace maro {` 안, 새 함수)에 추가:

```cpp
namespace {

bool extractMeshBuffers(const MObject& meshObj, std::vector<float>& vertices,
                        std::vector<std::uint32_t>& indices) {
    MStatus status;
    MFnMesh meshFn(meshObj, &status);
    if (!status) return false;

    MPointArray points;
    if (meshFn.getPoints(points, MSpace::kWorld) != MS::kSuccess) return false;
    vertices.clear();
    vertices.reserve(static_cast<std::size_t>(points.length()) * 3);
    for (unsigned int i = 0; i < points.length(); ++i) {
        vertices.push_back(static_cast<float>(points[i].x));
        vertices.push_back(static_cast<float>(points[i].y));
        vertices.push_back(static_cast<float>(points[i].z));
    }

    MIntArray triangleCounts, triangleVertices;
    if (meshFn.getTriangles(triangleCounts, triangleVertices) != MS::kSuccess) return false;
    indices.clear();
    indices.reserve(static_cast<std::size_t>(triangleVertices.length()));
    for (unsigned int i = 0; i < triangleVertices.length(); ++i) {
        indices.push_back(static_cast<std::uint32_t>(triangleVertices[i]));
    }
    return true;
}

}  // namespace

void MaroPump::collectLidarScans(MaroRosRuntime& runtime) {
    const SceneUnit unit = currentSceneUnit();

    for (MItDependencyNodes it(MFn::kPluginLocatorNode); !it.isDone(); it.next()) {
        MFnDependencyNode lidarFn(it.thisNode());
        if (lidarFn.typeId() != MaroLidarNode::id) continue;
        if (!lidarFn.findPlug(MaroLidarNode::aEnabled, false).asBool()) continue;

        MPlugArray meshSources;
        lidarFn.findPlug(MaroLidarNode::aTargetMeshes, false).elementByLogicalIndex(0)
            .connectedTo(meshSources, true, false);
        if (meshSources.length() == 0) continue;

        std::vector<float> vertices;
        std::vector<std::uint32_t> indices;
        if (!extractMeshBuffers(meshSources[0].node(), vertices, indices)) continue;

        maro::lidar::ScanEngine engine;
        if (!engine.setMesh(vertices, indices)) continue;

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
        const MString frameId = lidarFn.findPlug(MaroLidarNode::aFrameId, false).asString();

        const auto localDirections = maro::lidar::computeRayDirections(
            verticalSamples, verticalMinAngle, verticalMaxAngle, horizontalSamples,
            horizontalMinAngle, horizontalMaxAngle);

        MDagPath lidarPath;
        if (MDagPath::getAPathTo(it.thisNode(), lidarPath) != MS::kSuccess) continue;
        const MMatrix worldMatrix = lidarPath.inclusiveMatrix();
        const MVector worldOrigin(MPoint(0, 0, 0) * worldMatrix);

        LidarSample sample;
        sample.frameId = frameId.asChar();
        sample.unit = unit;

        for (const Vec3& localDir : localDirections) {
            const MVector localVec(localDir.x, localDir.y, localDir.z);
            const MVector worldDir = (localVec * worldMatrix - MVector(0, 0, 0) * worldMatrix).normal();
            // 위 식은 방향 벡터에서 평행이동 성분을 제거한다 -- 점이 아니라
            // 벡터를 옮기는 표준 트릭(월드 원점을 함께 빼서 상쇄).

            const maro::lidar::RayHit hit = engine.castRay(
                Vec3{worldOrigin.x, worldOrigin.y, worldOrigin.z},
                Vec3{worldDir.x, worldDir.y, worldDir.z}, rangeMin, rangeMax);
            if (hit.hit) sample.points.push_back(hit.position);
        }

        if (!sample.points.empty()) {
            runtime.lidarQueue().push(std::move(sample));
        }
    }
}
```

`onTimer()`의 `collectSamples(*s_runtime);` 바로 다음 줄에 추가:

```cpp
        collectLidarScans(*s_runtime);
```

(같은 `try` 블록 안 — 이 호출이 던지면 `collectSamples()`와 같은 catch가 잡는다.)

`src/maro_plugin/MaroPump.h`의 `private:` 섹션에 새 정적 메서드 선언을 추가(기존 `static void collectSamples(MaroRosRuntime& runtime);` 바로 아래):

```cpp
    static void collectLidarScans(MaroRosRuntime& runtime);
```

**5. CMake**: `src/maro_plugin/CMakeLists.txt`의 `target_link_libraries(${PROJECT_NAME} maro_transform)` 아래에 추가:

```cmake
target_link_libraries(${PROJECT_NAME} maro_lidar)
```

**검증 전략**: `maro_test_peer`(`tests/peer/maro_test_peer.cpp`)는 지금 `JointState`/`TFMessage`만 구독할 수 있고 `PointCloud2` 구독 모드가 없다 — 그걸 추가하는 건 이 태스크의 선언된 파일 범위를 넘는 별도 작업이라 하지 않는다. 대신 **씬에 `maroLidar` 하나만 두고 `maroAxis`는 하나도 안 만들면**, `maroBridgeStats()[1]`(`drainedSampleCount`, `MaroCommands.cpp:812`가 이미 노출)이 오르는 것 자체가 "이 씬에서 드레인될 수 있는 건 방금 만든 LiDAR 샘플뿐이므로 LiDAR 파이프라인이 캡처→스캔→명중→큐잉→드레인까지 전부 예외 없이 돌았다"는 증거가 된다 — `maro_test_peer`를 건드리지 않고도 정직하게 검증 가능한 선이다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/maya/test_lidar_publish.py`(전체 새 파일):

```python
"""maroLidar가 메쉬를 스캔해 실제로 발행 큐까지 도달하는지 종단으로
확인한다. maroBridgeStats()[1](drainedSampleCount)로 검증한다 -- 이
씬에는 maroAxis가 하나도 없으므로, 그 카운터가 오르는 유일한 원인은
LiDAR 샘플이 드레인된 것뿐이다.
"""
import os
import sys
import time

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)
cmds.currentUnit(angle="rad")

# 평평한 폴리곤 하나를 스캔 대상으로 놓는다 -- 레이가 확실히 맞을 위치.
plane = cmds.polyPlane(name="scanTarget", width=10, height=10, subdivisionsX=1,
                        subdivisionsY=1)[0]
cmds.setAttr(plane + ".translateY", 0)  # 원점, 평면은 기본 로컬 +Y 노멀.

lidar = cmds.createNode("maroLidar", name="testLidar")
cmds.setAttr(lidar + ".translateY", 5)  # 평면 위 5 유닛.
cmds.setAttr(lidar + ".verticalSamples", 1)
cmds.setAttr(lidar + ".verticalMinAngle", 0)
cmds.setAttr(lidar + ".verticalMaxAngle", 0)
cmds.setAttr(lidar + ".horizontalSamples", 1)
cmds.setAttr(lidar + ".horizontalMinAngle", 0)
cmds.setAttr(lidar + ".horizontalMaxAngle", 0)
# 로컬 +Y가 위 관례이므로, 레이를 아래(평면 쪽)로 겨냥하려면 라이다를
# X축 기준 180도 돌려 로컬 +Z가 월드 -Y를 보게 한다.
cmds.setAttr(lidar + ".rotateX", 180)
cmds.connectAttr(plane + ".message", lidar + ".targetMeshes[0]")


def wait_until(condition, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        cmds.refresh(force=True)
        if condition():
            return True
        time.sleep(0.05)
    return False


try:
    cmds.maroStartBridge("testRobot")

    drained_before = cmds.maroBridgeStats()[1]
    assert wait_until(lambda: cmds.maroBridgeStats()[1] > drained_before, timeout=5), (
        "drainedSampleCount never rose -- the lidar pipeline (capture, scan, "
        "hit, queue, drain) never produced a sample; "
        f"maroBridgeStats={cmds.maroBridgeStats()}"
    )
    print("lidar scan reached the publish queue OK")

    cmds.maroStopBridge()
finally:
    if cmds.pluginInfo(os.path.splitext(os.path.basename(plugin))[0], query=True, loaded=True):
        cmds.maroStopBridge()
        cmds.file(new=True, force=True)
        cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])

maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
```

`tests/CMakeLists.txt`의 `foreach(maya_test ...)` 목록(Task 5가 `lidar_node`를 추가한 그 목록)에 `lidar_publish`도 추가한다.

- [ ] **Step 2: 테스트가 실패하는지 확인**

```powershell
& "$env:MAYA_LOCATION\bin\mayapy.exe" tests\maya\test_lidar_publish.py
```

기대: 실패 — `drainedSampleCount`가 절대 안 오른다(아직 LiDAR 캡처 로직 자체가 없다). `$env:MARO_PLUGIN_PATH`를 먼저 설정해야 하며, Step 4의 ctest로 확실히 재확인한다.

- [ ] **Step 3: 위 코드 블록(`1.`~`5.`)을 정확히 명시된 위치에 적용**

적용 전에 각 삽입 지점 주변 몇 줄을 다시 읽어 파일이 이 플랜 작성 시점(Task 1~5 완료 후)과 달라지지 않았는지 확인한다.

- [ ] **Step 4: 빌드하고 테스트 실행**

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R maya_lidar_publish
```

기대: 통과.

- [ ] **Step 5: 일부러 깨서 확인**

`MaroPump::collectLidarScans()`에서 `if (!sample.points.empty())` 줄을 임시로 `if (false)`로 바꾼다(레이가 명중해도 큐에 절대 안 넣도록).

```powershell
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R maya_lidar_publish
```

기대: **실패**한다(`drainedSampleCount`가 5초 동안 안 오름). 확인했으면 `if (!sample.points.empty())`로 되돌린다.

```powershell
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release --output-on-failure -R maya_lidar_publish
```

기대: 다시 통과.

- [ ] **Step 6: 전체 스위트 확인**

```bash
ctest --test-dir out/build -C Release --output-on-failure
```

기대: `maya_panel_commands`(사전 결함) 하나만 빼고 전부 통과.

- [ ] **Step 7: 커밋**

```bash
git add src/maro_plugin/MaroBridgeQueues.h src/maro_plugin/MaroRosRuntime.h src/maro_plugin/MaroRosRuntime.cpp src/maro_plugin/MaroPump.h src/maro_plugin/MaroPump.cpp src/maro_plugin/CMakeLists.txt tests/maya/test_lidar_publish.py tests/CMakeLists.txt
git commit -m "feat: scan bound meshes with Embree and publish the result as PointCloud2"
```

**남는 검증 공백 (다음 태스크/후속 작업 대상, 정직하게 기록)**: 이 태스크는 "샘플이 큐까지 도달했다"만 증명한다 — 발행된 `PointCloud2` 메시지의 실제 바이트 내용(좌표가 정확한지, `frame_id`가 맞는지)은 `maro_test_peer`에 `PointCloud2` 구독 모드를 추가해야 자동 검증할 수 있다(범위 밖). 그 전까지는 §완료 기준의 "좌표 변환은 정확히 한 곳에서만" 등은 코드 리뷰로, RViz 등 대화형 도구로 수동 확인한다.

---

## 완료 기준

- `ctest --test-dir out/build -C Release --output-on-failure` 전부 통과(`maya_panel_commands` 사전 결함 하나만 예외)
- `maroLidar` 노드가 생성되고, 메쉬 하나에 바인딩되고, 레이캐스팅 결과가 실제 `PointCloud2` 메시지로 발행된다
- 좌표 변환은 정확히 한 곳(§Global Constraints)에서만 일어난다
- `MFnMesh` 데이터는 메인 스레드에서만 읽힌다
- 멀티스레딩·더티체크·대량 렌더링·다중 메쉬는 이 플랜이 만들지 않는다(§범위 밖, 워킹 스켈레톤 스펙 §7)
