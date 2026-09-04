# Maro Arnold 합성 데이터 생성기 (RGB+Depth+Normal → 포인트클라우드) — 설계

## 1. 배경

2026-09-02, 사용자가 Arnold(MtoA)를 Maro에 통합해 합성 센서 데이터를 만드는
아이디어를 4가지 시나리오로 제안했었다: (1) 파장 정확도 있는 IR LiDAR
시뮬레이션, (2) RGB+Depth+Normal AOV → ROS2 이미지/포인트클라우드, (3)
Object-ID/Albedo를 통한 시맨틱 포인트클라우드, (4) LiDAR 포인트클라우드 →
3D 재구성 → Arnold 재임포트. 기술 검토 후 사용자가 "일단 계획으로만
남겨둬"라고 해서 파킹됐고, 이번에 사용자가 다시 꺼냈다.

**파킹 당시 이미 끝낸 결론(재검토 없이 그대로 채택)**:
- 시나리오 1은 이대로 실현 불가능 — Arnold의 셰이딩은 가시광선 카메라
  이미지 형성을 모델링하지 IR 반사율 물리를 모델링하지 않고, 레이트레이싱도
  `maroLidar`의 Embree 엔진보다 몇 자릿수 느려 실시간 펌프 루프에 못 들어간다.
- **시나리오 2가 유일하게 현실적으로 다룰 수 있는 부분** — 포토리얼
  RGB+정확한 Z-depth/normal AOV는 Arnold의 원래 용도이고, 본질적으로
  오프라인/배치 작업이라 `maroLidar`의 실시간 제약과 충돌하지 않는다.
- 시나리오 3(시맨틱 라벨)은 시나리오 2의 자연스러운 확장 — 이번 설계는
  그 중 "depth를 포인트클라우드로 역투영"하는 부분까지만 다루고, Object-ID/
  Albedo 라벨링 자체는 범위 밖(§8)으로 남긴다.
- 시나리오 4는 완전히 무관한 별개 과제 — 이번 설계와 무관.

**확인된 사실** (파일시스템 직접 확인, 가정 아님):
- Arnold/MtoA가 이 머신에 설치·등록돼 있다(`C:\Program Files\Autodesk\
  Arnold\Maya2026`, `mtoa.mod`가 Maya 2026 모듈 검색 경로에 존재).
- Arnold와 함께 `oiiotool.exe`(OpenImageIO CLI)가 설치돼 있다
  (`C:\Program Files\Autodesk\Arnold\Maya2026\bin\oiiotool.exe`) — depth
  EXR에서 픽셀 값을 읽어오는 데 별도 Python EXR 라이브러리를 mayapy
  환경에 새로 설치할 필요가 없다는 뜻이다. 이번 설계의 가장 위험한 가정
  하나가 이걸로 해소됐다.
- 이 프로젝트는 지금까지 `sensor_msgs/msg::Image`/`CameraInfo`를 발행해
  본 적이 없다(`JointState`/`PointCloud2`만 있음) — 그러나 이번 설계는
  ROS2 발행을 아예 하지 않으므로(§2) 무관하다.

## 2. 범위

### 이번 설계에 포함 (워킹 스켈레톤)

1. **합성 데이터 카메라** — 평범한 Maya `camera` + 커스텀 어트리뷰트
   (`outputResolutionWidth`/`Height`, `outputDirectory`). 새 C++ 노드 없음.
2. **Arnold 렌더 + AOV 3종** — beauty(PNG), depth(EXR, Arnold 내장 `Z`
   AOV), normal(EXR, Arnold 내장 `N` AOV). 현재 프레임 1개만.
3. **캘리브레이션 메타데이터** — 카메라 내부/외부 파라미터를 JSON 사이드카로
   저장.
4. **Depth → 포인트클라우드 역투영** — `oiiotool`로 EXR을 PFM으로 변환,
   순수 Python으로 픽셀→카메라공간→월드공간 역투영, 결과를 PLY 파일 +
   기존 `maroPointCloud` 노드에 반영.
5. **Maro 메뉴에 새 항목** — 비모달 PySide6 패널(카메라 선택, 출력 경로,
   "렌더 지금" 버튼).

### 명시적 제외 (이번 슬라이스, §8에 상세)

- ROS2 토픽 발행(파일로만 출력).
- 프레임 범위 배치 렌더(현재 프레임 1개만).
- Object-ID/Albedo 시맨틱 라벨링(시나리오 3의 나머지 절반).
- 시나리오 1, 4는 이번 기능과 완전히 무관 — 애초에 논의 대상이 아님.

## 3. 합성 데이터 카메라

`python/maroSyntheticDataCamera.py`(신규)의 `createSyntheticDataCamera(name=None) -> str`
(카메라 트랜스폼 풀패스를 반환):

```python
cameraTransform, cameraShape = cmds.camera(name=name or "maroSyntheticDataCam#")
cmds.addAttr(cameraTransform, longName="outputResolutionWidth",
             attributeType="long", defaultValue=1920)
cmds.addAttr(cameraTransform, longName="outputResolutionHeight",
             attributeType="long", defaultValue=1080)
cmds.addAttr(cameraTransform, longName="outputDirectory", dataType="string")
cmds.setAttr(cameraTransform + ".outputDirectory", "", type="string")
```

초점거리(`focalLength`)/필름 백(`horizontalFilmAperture`/`verticalFilmAperture`)은
Maya 카메라가 이미 갖고 있는 기존 어트리뷰트를 그대로 쓴다 — 중복 어트리뷰트를
새로 만들지 않는다. 씬의 "합성 데이터 카메라"를 찾는 조회 함수
`listSyntheticDataCameras() -> list[str]`는 `outputDirectory` 어트리뷰트
존재 여부로 판별한다(별도 마커 어트리뷰트 불필요 — 이 어트리뷰트 조합
자체가 마커 역할을 한다).

## 4. Arnold 렌더 + AOV

`python/maroSyntheticDataRender.py`(신규)의 `renderSyntheticFrame(cameraTransform, outputDir=None) -> dict`:

1. `mtoa.aovs`로 AOV 3개 준비: `RGBA`(beauty, Arnold 기본 제공),
   `N`(normal), `Z`(depth) — 씬에 없으면 추가, 있으면 재사용(멱등).
2. 각 AOV에 출력 드라이버 연결: beauty → PNG 드라이버, depth/normal →
   EXR 드라이버(32비트 float).
3. `cmds.arnoldRender(width=.., height=.., camera=..)`로 배치 렌더 —
   해상도는 카메라의 `outputResolutionWidth`/`Height`에서 읽는다.
4. 출력 파일명: `<outputDir>/<cameraName>_<frame:04d>_<aov>.<ext>`
   (`_beauty.png`, `_depth.exr`, `_normal.exr`). `<frame>`은 현재
   `cmds.currentTime(query=True)`.
5. 캘리브레이션 JSON `<outputDir>/<cameraName>_<frame:04d>_camera.json`에
   기록: `focalLength`, `horizontalFilmAperture`, `verticalFilmAperture`,
   `resolutionWidth`, `resolutionHeight`, 카메라의 월드 트랜스폼(4x4 행렬,
   `om2.MDagPath.inclusiveMatrix()`로 얻은 16개 값 — 이 프로젝트가 LiDAR
   센서 검증 설계에서 이미 확립한 "행렬은 커맨드/모듈이 그대로 넘기고
   호출부가 다시 유도하지 않는다"는 원칙과 같은 이유로, §5의 역투영이
   같은 값을 그대로 재사용한다).

반환값: `{"beauty": path, "depth": path, "normal": path, "calibration": path}`.

## 5. Depth → 포인트클라우드 역투영

`python/maroSyntheticDataPointCloud.py`(신규)의
`reprojectDepthToPointCloud(depthExrPath, calibrationJsonPath) -> list[tuple[float,float,float]]`
(Maya 월드 좌표):

1. `oiiotool <depthExrPath> -o <임시>.pfm`을 서브프로세스로 호출.
2. PFM 파일을 순수 Python(`struct` 모듈)으로 파싱 — 헤더(포맷 태그, 폭/높이,
   바이트 순서) + `width × height`개의 float32.
3. 카메라 내부 파라미터: `fx = (focalLength_mm / (horizontalFilmAperture_inch × 25.4)) × width_px`,
   `fy`는 세로 필름 백 기준 동일 공식, `cx = width/2`, `cy = height/2`.
4. **[구현 단계 필수 검증 — §9]** Arnold의 `Z` AOV가 카메라 광축 기준
   평면 거리(planar)인지 카메라-점 직선 거리(radial)인지 실측으로 확정한
   뒤, 그에 맞는 공식으로 픽셀 `(u,v)` + depth 값을 카메라 공간 3D 점으로
   역투영.
5. §4에서 저장한 카메라 월드 트랜스폼 행렬로 카메라 공간 → Maya 월드
   공간 변환.
6. 유효하지 않은 depth(배경/미스, Arnold가 채우는 특수값)는 걸러낸다.

**출력**: `writePly(points, path)` — ASCII PLY. 그리고
`updatePointCloudNode(points, pointCloudNode=None) -> str`(없으면
`cmds.createNode("maroPointCloud")`로 생성) — `cmds.setAttr(node + ".points",
len(points), *points, type="pointArray")`로 반영, `maroSnapshotLidarScan`이
이미 쓰는 것과 같은 메커니즘(§7의 Global Constraints에 정확한 호출 형태
명시).

## 6. Maro 메뉴 + UI 패널

`python/maroSyntheticDataPanel.py`(신규) — 비모달 PySide6 패널
(`maroSettingsPanel.py`와 같은 패턴: `QtCore.Qt.Window`, 모듈 싱글턴
`_OPEN_PANEL`, `setStyleSheet()` 안 씀, `show()`/`stop()` 모듈 함수):

- 씬의 합성 데이터 카메라 드롭다운(`listSyntheticDataCameras()`) + "새로
  만들기" 버튼(§3의 `createSyntheticDataCamera()` 호출).
- 출력 디렉터리 필드 + `cmds.fileDialog2` 찾아보기 버튼.
- 현재 프레임 표시(읽기 전용 라벨).
- "렌더 지금" 버튼 → §4의 `renderSyntheticFrame()` → §5의
  `reprojectDepthToPointCloud()`/`writePly()`/`updatePointCloudNode()`를
  순서대로 실행, 상태 라벨에 진행 상황/완료/에러 표시.

`python/maroMenu.py`에 "합성 데이터 렌더..." 항목 추가.

## 7. 전역 제약

- 새 C++ 코드/커맨드/DG 어트리뷰트 없음 — 전부 순수 Python.
- 새 `.py`는 `setStyleSheet()`를 호출하지 않는다.
- `updatePointCloudNode()`가 `.points`를 쓸 때 반드시 `cmds.setAttr(node + ".points",
  len(points), *points, type="pointArray")` 형태를 쓴다(`maroSnapshotLidarScan`의
  기존 계약과 동일 — 새 계약을 발명하지 않는다).
- 카메라 월드 트랜스폼은 `maya.api.OpenMaya`(`MDagPath.inclusiveMatrix()`)로
  얻고, JSON에 16개 값(row-major)으로 저장 — §5가 이 값을 다시 유도하지
  않고 그대로 씀(이 프로젝트가 LiDAR 센서 검증 설계에서 확립한 원칙과
  동일).
- 에러 처리: Arnold 라이선스 없음/MtoA 미로드/렌더 실패/`oiiotool.exe`
  못 찾음/카메라 미선택/출력 경로 쓰기 권한 없음 — 전부 예외를 잡아
  상태 라벨에 구체적 메시지로 표시하고 중단. Maya는 크래시하지 않는다
  (이 프로젝트의 견고성 원칙 3 그대로).
- 빌드는 항상 `--config Release`, `ctest --test-dir out/build -C Release
  --output-on-failure` 전부 통과(순수 Python 기능이라 새 C++ 빌드 대상은
  없지만, 전체 스위트 회귀는 그대로 확인).

## 8. 범위 밖

- **Object-ID/Albedo 시맨틱 라벨링**(시나리오 3의 나머지 절반) — 필요해지면
  별도 슬라이스.
- **프레임 범위 배치 렌더** — 이번엔 현재 프레임 1개만. 필요해지면 별도
  슬라이스(파일명 규약은 이미 프레임 번호를 포함하므로 확장 시 마찰 적음).
- **ROS2 토픽 발행**(`sensor_msgs/Image`/`CameraInfo`) — 이번 기능 전체에서
  제외, 파일로만 출력.
- **여러 합성 데이터 카메라 일괄 렌더** — 패널은 한 번에 카메라 하나만
  다룬다.
- **시나리오 1(파장 정확도 IR LiDAR 시뮬레이션)**, **시나리오 4(포인트
  클라우드 → 3D 재구성 → Arnold 재임포트)** — 파킹 당시 이미 결론 낸 대로
  이 프로젝트 아키텍처와 무관, 이번 설계와도 무관.
- **PLY 바이너리 포맷** — 이번엔 ASCII만(디버깅 용이성 우선). 포인트 수가
  많아지면 바이너리로 전환 고려.

## 9. 테스트 전략

- **순수 함수**(카메라 내부 파라미터 계산, PFM 파싱, 픽셀→카메라공간→
  월드공간 역투영, PLY 쓰기)는 가짜 depth 배열/가짜 캘리브레이션 JSON으로
  mayapy 또는 plain Python 단위 테스트 가능 — Arnold 전혀 불필요.
- **Arnold `Z` AOV의 평면/직선 거리 규약**(§5의 4번) — 반드시 실측으로
  확정한다. 카메라 정면 정확히 알려진 거리(예: 500 유닛)에 카메라를 정면으로
  바라보는 평면을 두고 렌더 → depth 값이 그 거리와 일치하는지 확인하는
  절차를 구현 태스크에 명시(둘 중 어느 공식이 맞는지 손으로 가정하지
  않는다 — 이 프로젝트가 URDF 내보내기/LiDAR 센서 검증에서 이미 세 번
  이상 검증한 것과 같은 이유).
- **실제 렌더+역투영 전체 파이프라인**(Arnold 라이선스+렌더 컨텍스트 필요)은
  mayapy 배치로 자동화 불가능 — 대화형 Maya 수동 체크리스트로 검증.
  "알려진 거리 평면 렌더 → depth 값 일치 확인"이 이 기능의 진짜 go/no-go.
- UI 패널 자체(버튼 클릭, 파일 다이얼로그)도 배치 `mayapy`에 `QApplication`이
  없어 자동 검증 불가 — 수동 체크리스트.
