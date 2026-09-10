# Maro — Maya / ROS 2 축 노드 플러그인

Maro는 Maya에서 모델링한 오브젝트를 Maya 자신의 리깅과 Dependency Graph를
이용해 로보틱스화하고, ROS 2로 실시간 구동한다. 외부 시뮬레이터(Gazebo,
CARLA)와 달리 로봇은 전적으로 Maya 씬 안에서 산다.

로봇은 두 개의 조립 단위로 구성된다:

- **Axis** (`maroAxis`) — 정확히 하나의 Maya 오브젝트에 바인딩되어 그 움직임을
  구동한다. 축은 체인으로 연결(`maroConnectAxis`)되어 계층 구조를 이룰 수 있다.
- **Capability 노드** — 축의 `capabilityIn` 배열에 스택으로 쌓인다. 그 축이
  *무엇이 되는지*(단순 회전 조인트, 리니어 슬라이더, 제한된 조인트, 기어로
  커플링된 조인트, 센서, 움직이는 센서, ...)는 어떤 capability가 쌓였는지에서
  나오는 것이지, 미리 고른 타입에서 나오지 않는다. 현재 일곱 가지 타입이
  존재한다: `maroRotation`, `maroTranslation`, `maroLimit`,
  `maroTranslationLimit`, `maroCoupling`(다른 축과의 기어비/비선형 커브),
  `maroSensorDirection`, `maroSensorRange`. 축 하나는 최대 하나의 *주 구동*
  capability(rotation/translation/coupling — 물리적으로 자유도 하나는 동시에
  두 개의 구동원을 가질 수 없다)만 가질 수 있으며, 나머지는 전부 그 위에
  얹힌다.

축마다 `controlMode`가 있다: **Manual**(사용자 자신의 리깅/키프레임이 축을
구동)과 **ROS**(들어오는 ROS 2 명령이 대신 구동). 백그라운드 브리지
(`maroStartBridge`)가 살아있는 씬으로부터 `/joint_states`와 `/tf`를 발행하고,
ROS 모드인 축에는 들어오는 `/<robot>/joint_commands`를 적용한다. LiDAR 노드
(`maroLidar`)는 여기에 더해 메쉬를 레이캐스팅(Embree)하고
`sensor_msgs/PointCloud2`를 발행할 수 있다.

## MaroUI — 대화형 에디터

`maroMainWindow`는 나란히 배치된 두 개의 실시간 3D 뷰포트를 가진 도킹 가능한
창을 연다(왼쪽은 Maya 고유 좌표 공간, 오른쪽은 `maroRosProxy`를 통해 같은
씬을 ROS 좌표로 재투영한 것) — 그래서 리그를 연결한 뒤 두 공간이 동일하게
움직이는지 시각적으로 확인할 수 있다.

축/capability 편집 자체는 그 창 안에서 이뤄지지 않는다 — Maya에서 기대할
법한 방식 그대로 접근한다: **뷰포트의 아무 오브젝트나 우클릭**하면, Maya의
네이티브 마킹 메뉴에 `Maro node editor` 항목이 추가돼 있다(엔진 자신의
`dagMenuProc`을 체이닝해 설치하며, 언로드 시 복원된다). 어떤 오브젝트에서
처음 이 항목을 고르면 표시 이름과 색상을 물은 뒤 그 오브젝트에 바인딩된
`maroAxis`를 만들고 작은 팝업 — **싱글 오브젝트 노드 에디터(SONE)** — 를
연다. 이 팝업에서는 같은 우클릭-홀드-드래그-릴리즈 마킹 메뉴 제스처로 축에
capability 타입을 부여하고, Delete는 가장 최근에 추가한 것을 하나씩 벗겨내며,
두 개 이상 쌓이면 더블클릭으로 드롭다운이 펼쳐진다. 에디터가 한 번이라도
열린 축은 모두 MaroUI의 **오브젝트 노드 에디터(ONE)** 패널에 작게 그루핑된
타일로 나타나서, 뷰포트로 돌아가지 않고도 그 축의 SONE을 다시 열거나
이름/색상을 바꾸거나 삭제할 수 있다.

듀얼 뷰포트 양옆에는 패널 두 개가 더 붙어 있다 — MaroUI의 **Tech Diag**
검사 터미널이다. Maya 쪽에서 "검사 실행"을 누르면 현재 씬을 다시 스캔해
설정된 한계에 가까이 있는 축과, 바운딩 박스가 겹치는 타겟 메쉬들을 찾아낸다.
ROS 쪽은 `/joint_states` 발행 문제(빈 이름/중복된 조인트 이름, 주 구동이
없는 활성화된 축)를 다시 스캔한다. 고칠 수 있는 발견 사항에는 적용 버튼
(undoable한 `setAttr`)이 붙고, 나머지는 설명만 제공한다 — "이 값이 한계에
가깝다" 같은 문제엔 일반적인 해법이 없기 때문이다. 백그라운드에서 도는 것은
아무것도 없다 — 모든 스캔은 버튼으로 트리거되고 그 순간만을 반영한다.

이것은 플러그인 자체의 충돌/오류 디버깅용 `maroDiagPanel`(아래)과는 별개의
관심사다 — Tech Diag는 *플러그인*이 아니라 *로봇*을 검증한다.

## 사전 준비물

- Windows, Visual Studio 2022(MSVC), CMake >= 3.22
- Maya 2026 devkit
- ROS 2 Jazzy, 같은 MSVC 툴셋으로 빌드/설치된 것
- vcpkg — `vcpkg.json` 참고. 여기서 오는 패키지는 두 개다:
  - **GoogleTest** — transform/lidar 단위 테스트가 사용.
  - **Embree 4** — Maya 플러그인의 *런타임* 의존성(LiDAR 레이캐스터가
    링크하므로 `embree4.dll`이 Maya 프로세스에 로드된다). vcpkg의 기본
    `tasking-tbb` 기능 **없이** 설치해야 한다 — `tbb12.dll`을 임포트하는
    Embree는 Maya 안에서 로드될 수 없다. Maya가 이미 자신의 `tbb12.dll`을
    프로세스에 갖고 있고, Windows 로더가 같은 베이스 이름의 모듈을
    재사용하기 때문이다. 증상은 원인을 전혀 알려주지 않는 맨
    `ERROR_PROC_NOT_FOUND`로 실패하는 `loadPlugin`이다. 지금은 configure
    단계가 해석된 DLL의 임포트 테이블을 확인해 조용히 넘어가지 않고 크게
    실패하도록 되어 있다(`src/maro_lidar/CMakeLists.txt`).

> **vcpkg 해석 함정:** 이 저장소의 `vcpkg.json`은 기능 집합을 고정할 뿐
> 일반적인 `out/build` 트리의 해석에는 관여하지 **않는다** — 그 트리는
> `CMAKE_TOOLCHAIN_FILE` 없이 구성되므로, `find_package(embree)`는 **전역
> classic-mode** 설치 트리(`C:/src/vcpkg/installed/x64-windows`)를 대상으로
> 해석된다. 패키지는 그곳에 직접 설치해야 한다. 예:
>
> ```powershell
> vcpkg install "embree[core,filter-function,geometry-curve,geometry-grid,geometry-instance,geometry-point,geometry-quad,geometry-subdivision,geometry-triangle,geometry-user,ray-packets]:x64-windows"
> ```
>
> (이것이 `vcpkg.json`의 `embree` 기능 목록에서 `tasking-tbb`만 뺀 것이다 —
> 둘을 서로 맞춰 둔다)
>
> `vcpkg.json`만 고쳐서는 실제로 빌드가 링크하는 내용이 바뀌지 않는다.

## 빌드 설정

빌드에는 절대 경로 두 개가 필요하며, CMake 캐시 변수로 노출된다. 지금은
개발자 한 명의 머신을 기본값으로 두고 있으므로 — 다른 환경에서는 **둘 다
override**해야 한다:

| 캐시 변수 | 용도 | 기본값 |
|---|---|---|
| `DEVKIT_LOCATION` | Maya devkit의 루트(`cmake/pluginEntry.cmake`, Maya 헤더/라이브러리 제공) | `C:/Users/ckd30/Projects/devkitBase` |
| `ROS2_INSTALL` | ROS 2 설치 prefix(헤더, `Lib/`, `bin/`, 그리고 벤더 `opt/*/bin` 디렉터리) | `C:/dev/ros2_jazzy/install` |

그 외 유용한 옵션:

- `MARO_BUILD_PLUGIN`(기본 `ON`) — Maya 플러그인을 빌드; devkit + ROS 2 필요.
- `MARO_BUILD_TESTS`(기본 `ON`) — 테스트 스위트를 빌드하고 등록.

Visual Studio "x64 Native Tools"(또는 `VsDevCmd.bat`으로 초기화한) 셸에서
구성 + 빌드하는 예:

```powershell
cmake -S . -B out/build -DDEVKIT_LOCATION=C:/path/to/devkit -DROS2_INSTALL=C:/path/to/ros2_jazzy/install
cmake --build out/build
```

## PATH 요구 사항 (첫 `loadPlugin` 전에 꼭 읽을 것)

빌드는 ROS 2 런타임 DLL 전부(`libyaml`/`spdlog`/`console_bridge` 벤더 DLL,
그리고 `embree4.dll`)를 빌드된 플러그인(`maro.mll`) 옆에 스테이징한다. 그것만으로는
충분하지 않다 — Maya의 플러그인 로더는 `.mll` 파일을 `LOAD_WITH_ALTERED_SEARCH_PATH`로
열지 않으므로, Windows가 그 의존성들을 찾으려고 플러그인 자신의 디렉터리를
자동으로 뒤지지 않는다.

**Maya(또는 `mayapy`)가 시작하기 전에 플러그인의 출력 디렉터리가 이미
`PATH`에 있어야 한다.** 그렇지 않으면 `loadPlugin("maro")`이 원인을 전혀
알려주지 않는 일반적인 "종속 DLL을 찾을 수 없음" 오류로 실패한다.

빌드 출력 디렉터리(예: `out/build/src/maro_plugin/Debug`)를 Maya를 실행하는
환경의 `PATH`에 추가한 뒤 Maya를 시작한다.

### 권장: Maya 모듈 파일(`.mod`)로 한 번에 해결

빌드가 `out/build/src/maro_plugin/maya-modules/<CONFIG>/maro.mod`를 생성한다.
이 파일 하나가 위의 `PATH` 요구를 없애고, 덤으로 **도킹한 Maro 창의 재시작
복원**까지 고친다.

설치는 디렉터리 하나를 만들고 복사하는 것이다. **`modules` 디렉터리는 기본으로
존재하지 않는다** -- Maya는 없어도 `MAYA_MODULE_PATH`에 넣어 두지만 만들어
주지는 않는다. 아래는 **리포지터리 루트에서** 실행한다(PowerShell은 슬래시
경로를 그대로 받으므로 백슬래시 이스케이프를 신경 쓸 필요가 없다.
`Documents` 경로는 이 머신 실측 기준 -- OneDrive로 리다이렉트돼 있다):

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE/OneDrive/Documents/maya/2026/modules" | Out-Null
```

```powershell
copy ./out/build/src/maro_plugin/maya-modules/Release/maro.mod "$env:USERPROFILE/OneDrive/Documents/maya/2026/modules/"
```

Maya가 시작할 때 이 모듈을 읽어 플러그인 경로 / `PATH` / 스크립트 경로를
한꺼번에 잡아 준다. 확인:

```python
import maya.cmds as cmds
cmds.loadPlugin("maro")   # 전체 경로 없이 이름만으로
```

**왜 재시작 복원까지 고쳐지나.** `workspaceControl -requiredPlugin "maro"`는
Maya에게 플러그인을 **이름으로** 로드하게 하는데, 그 이름은
`MAYA_PLUG_IN_PATH`로만 해석된다. 빌드 트리는 거기 없어서, 저장된 레이아웃이
Maro 창을 기억해도 플러그인 자동 로드가 일어나지 않았다(2026-09-10 실측 --
`docs/maro-main-ui-manual-checklist.md`의 "재시작 복원" 항목).

`.mod` 안의 경로는 **생성 당시 빌드 디렉터리의 절대 경로**다. 빌드 트리를
옮기거나 지웠다면 다시 복사해야 한다. 회귀는 `maya_module_file` 테스트가
지킨다 -- 그 테스트는 `MARO_PLUGIN_PATH`도 `PATH` 선행도 없이 오직 이 `.mod`
만으로 이름 로드가 되는지 확인한다.

## 테스트 실행

테스트는 CTest에 등록되어 있다 — C++ transform 단위 테스트(GoogleTest)와
`tests/maya/` 아래의 `mayapy` 기반 시나리오 스크립트 묶음. `mayapy` 기반
테스트는 CTest 테스트 속성으로 자기 자신의 `PATH`/`MARO_PLUGIN_PATH`를
설정하므로, `ctest` 실행을 위해 수동으로 그럴 필요가 없다.

```powershell
ctest --test-dir out/build --output-on-failure
```

일부 테스트는 실제 ROS 2 브리지를 띄우고 별도 프로세스(`maro_test_peer`)와
통신한다 — 이런 테스트는 같은 DDS 도메인을 공유해 서로 간섭할 수 있으므로
`RUN_SERIAL`로 표시되어 있다.

## 등록된 `maro*` 커맨드

축 / capability(조회 전용 커맨드는 undo 없음; 나머지는 undoable):

| 커맨드 | 용도 |
|---|---|
| `maroBindAxis(axis, targetObject)` / `maroUnbindAxis(axis)` | `maroAxis` 노드를 그것이 구동할 Maya 오브젝트에 바인딩/해제. |
| `maroConnectAxis(child, parent)` | 한 축을 다른 축의 자식으로 연결해 축 계층을 구성. |
| `maroSetControlMode(axis, 0\|1)` | 축을 Manual(0)과 ROS(1) 제어 사이에서 전환. |
| `maroListAxisNodes([-capabilities axis])` | 모든 축, 또는 한 축의 capability 스택을 평탄한 문자열 배열로 조회(MaroUI의 Python 쪽이 소비). |
| `maroAddCapability(-type <name>, axis)` | 새 capability 노드를 만들어 축의 다음 빈 슬롯에 연결. |
| `maroConnectCapability(capNode, axis, [-index i])` / `maroDisconnectCapability(axis, -index i)` | 기존 capability 노드를 연결/연결 해제. |

ROS 2 브리지와 좌표 프록시:

| 커맨드 | 용도 |
|---|---|
| `maroStartBridge(robotName)` / `maroStopBridge()` | ROS 2 브리지 시작/정지: `/<robotName>/joint_states`, `/tf`, 그리고 선택적으로 LiDAR 스캔을 발행하고, `/<robotName>/joint_commands`를 구독. |
| `maroBridgeStats()` | 진단 카운터: `[collected, drained, applied, threadTicks, publishErrors, drainedLidarScans]`. |
| `maroMayaToRos(...)` | 순수 좌표 변환 규약(Maya → ROS). 듀얼 뷰포트 프록시가 사용하며 브리지 없이도 테스트 가능. |
| `maroSetRosProxyTarget(object)` / `-clear` | MaroUI 오른쪽 뷰포트의 격리 대상을 특정 오브젝트로 지정. |

UI 진입점:

| 커맨드 | 용도 |
|---|---|
| `maroMainWindow` | MaroUI를 연다(듀얼 뷰포트 + ONE + Tech Diag 패널). 이미 열려 있으면 복원하는 멱등 동작. |
| `maroBuildMenu` | 최상위 "Maro" Maya 메뉴를 구성. |
| `maroDiagPanel` | 플러그인 자체의 충돌/오류 디버깅 패널을 연다(Tech Diag와는 무관 — 위 MaroUI 절 참고). |

디버깅 Diag(`boad`/`book`) — 축 시스템과 독립적인, 플러그인/Maya 오류용:

| 커맨드 | 용도 |
|---|---|
| `maroDiagPanelRows` / `maroDiagPanelDetail` | 패널을 위한 진단 레코드 스트림을 조회. |
| `maroDiagRegisterRemedy` / `maroDiagRequestRemedy` / `maroApplyRemedy` | 알려진 오류 해시에 대한 해법을 등록하고, 큐에 넣은 뒤, 적용(undoable). |

플래그 하나하나까지 다루는 전체 레퍼런스(테스트 전용 유틸리티 포함)는 이
README에서 관리하지 않는다 — 해당 커맨드의 `.cpp`/`newSyntax()`
(`src/maro_plugin/` 안)나, 기능별 스펙(`docs/superpowers/` 아래)을 읽는다.

## 레이아웃

- `src/maro_plugin/` — Maya 플러그인: 노드(axis, capability, LiDAR, device),
  커맨드, ROS 2 브리지 런타임, `dagMenuProc` 체이닝, 그리고 Maya와 ROS 2
  사이에서 데이터를 옮기는 항상 켜져 있는 메인 스레드 펌프.
- `src/maro_transform/` — 플러그인과 그 단위 테스트가 공유하는 좌표/단위
  변환 라이브러리.
- `src/maro_lidar/` — `maroLidar`가 쓰는 Embree 기반 레이캐스팅 엔진.
- `src/maro_diag/` — 디버깅 Diag 패널(`boad`/`book`)을 위한, Maya에
  독립적인 프레젠터/모델 로직. 자체 GoogleTest 바이너리로 커버됨.
- `src/maro_ipc/` — 플러그인과 센티널 워치독 사이의 네임드 파이프/잡
  오브젝트 프로토콜.
- `src/maro_sentinel/` — `maro_sentinel.exe`, Maya 세션이 크래시했는지
  정상 종료했는지를 감지하는 별도의 워치독 프로세스.
- `python/` — Qt와 맞닿은 모든 것(MaroUI의 창, SONE/ONE 에디터,
  `dagMenuProc`의 Python 쪽 핸들러, Tech Diag, 진단 패널, ROS 좌표
  프록시) — 빌드 시점에 빌드된 플러그인 옆에 스테이징된다.
- `tests/` — GoogleTest 단위 테스트와 `mayapy` 시나리오 테스트, CTest에
  연결됨.
- `docs/superpowers/` — 이 프로젝트의 subagent-driven-development
  워크플로로 만들어진 기능 슬라이스마다의 설계 스펙, 구현 계획, 태스크별
  이력.
- `docs/maro-main-ui-manual-checklist.md` — 자동화된 테스트가 닿을 수 없는
  모든 것(실제 마우스 제스처, 실제 창 렌더링, 열린 채 언로드 안전성)을 위한
  대화형 Maya 전용 검증 체크리스트.
