# Maro 메인 UI — Phase 0-1 설계 (2026-08-24)

## 1. 배경

지금까지 Maro 플러그인의 유일한 UI는 `maroDiagPanel`(순수 네이티브 Maya `cmds` 위젯, Qt 없음)이다. 사용자는 훨씬 큰 그림을 요청했다: Maya 상단에 "Maro" 메뉴가 생기고, 그 안에서 PySide6로 만든 메인 UI를 열 수 있으며, 이 UI는

1. 좌우로 나뉜 실제 3D 뷰포트 2개(좌 = 마야 씬 그대로, 우 = ROS 좌표계로 변환된 표현)
2. 오브젝트를 "업로드"하면 스켈레톤(본) 뷰로 전환되어 노드 바인딩이 쉬워지는 흐름
3. 바인딩된 오브젝트를 색으로 구분
4. axis/capability 노드를 편집하는 창
5. 기존 진단/치료(remedy) 시스템을 재사용하는 디버그 터미널

로 구성된다. 사용자가 명시적으로 "지금 당장 떠오르는 구상"이라 밝혔고 "더 구체화시켜야 하는 기술적 결정이 있으면 알려달라"고 요청했다.

## 2. 범위: Phase 0-1만 (워킹 스켈레톤)

조사 결과 이 기능의 대부분(노드 바인딩, capability 스택, 디버그 터미널)은 이미 있는 패턴을 그대로 재사용하면 되는 반면, **"실제 3D 뷰포트 2개를 PySide6 창 안에 동시에 띄우고 그중 하나가 다른 좌표계를 보여준다"는 것만 이 프로젝트에 전례가 없는 진짜 기술적 리스크**다. 이 프로젝트가 이번 세션 내내 지켜온 방식(라이다 기능도 4단계 제안을 워킹 스켈레톤으로 축소해 가장 위험한 가정부터 증명) 그대로, 이번에도 그 리스크를 가장 작은 형태로 먼저 증명하는 슬라이스만 지금 계획한다.

**Phase 1은 go/no-go 게이트다.** "네이티브 레이아웃 안에 `modelPanel` 하나 + PySide6 버튼 하나를 같이 띄우고, 플러그인 언로드 시 크래시 없이 정리되는가"만 증명한다. 이게 불안정하면 이후 전체 설계(우측 뷰포트, 프록시 동기화 등)를 재검토해야 하므로, 그 뒤 단계는 지금 태스크로 확정하지 않는다(§7 참고).

## 3. 사용자가 확정한 설계 결정

1. 좌/우 화면은 데이터 뷰가 아니라 **진짜 실시간 3D 뷰포트 2개**.
2. "frame bone 뷰"는 뷰포트 표시 모드 전환이 아니라 **스켈레톤 추출/생성**.
3. 우하단 디버그 터미널은 **기존 진단/치료 시스템(`maroDiagPanelRows`/`Detail`/`RequestRemedy`/`ApplyRemedy`) 재사용**.
4. Maro 메뉴는 **플러그인 로드 후에만** 나타나면 됨(`.mod`/`userSetup.py` 불필요).

## 4. 근거 조사 요약

### 4.1 기존 UI 패턴 확인 결과

- 유일한 기존 UI(`python/maroDiagPanel.py`)는 Qt를 전혀 쓰지 않는다 — `cmds.formLayout`/`cmds.textScrollList`/`cmds.scrollField`/`cmds.button`/`cmds.optionMenu`뿐이다. `cmds.workspaceControl(..., uiScript="import maroDiagPanel; maroDiagPanel.buildUI()")`로 열리며, 수동 새로고침(버튼/드롭다운 클릭)만 있고 타이머/콜백은 없다.
- `MaroPanelCommands.cpp`의 `MaroDiagPanelCommand::doIt`는 `MFnPlugin::findPlugin("maro").loadPath()`로 플러그인이 실제로 설치된 디렉터리를 런타임에 알아내 `sys.path`에 넣은 뒤 `import`한다 — 설치 위치에 무관하게 동작하는 이 패턴을 새 PySide6 모듈들도 그대로 따라야 한다.
- Maya로 노출되는 데이터는 전부 "flat `MStringArray`, 행마다 고정 필드 수, 그 필드 수를 상수로 박아 두고 테스트가 C++/Python 양쪽을 교차 검증"하는 계약이다(`ROW_FIELDS=8`, `DETAIL_FIELDS=14`). 새 커맨드도 JSON이 아니라 이 컨벤션을 따른다.
- `.py` 스테이징: `MARO_DIAG_PANEL_PY_OUT`(`src/maro_plugin/CMakeLists.txt`)이 `.py` 파일 하나당 `OUTPUT` 기반 `add_custom_command`+`add_custom_target`+`add_dependencies(${PROJECT_NAME} ...)`를 요구한다. `$<CONFIG>`를 반드시 출력 경로에 넣어야 한다(이 저장소는 CMake Visual Studio 멀티 컨피그 제너레이터 — 이번 세션에 `$<CONFIG>` 누락이 `maya_panel_commands`의 진짜 원인이었음을 확인하고 고쳤다).

### 4.2 임베딩 기술 확인 결과

Maya devkit은 `MQtUtil`을 정식으로 제공한다(`devkitBase/include/maya/MQtUtil.h:180-195`에서 `findControl`/`findLayout`/`addWidgetToMayaLayout` 시그니처 직접 확인). 두 방향이 있다:

- **네이티브 → Qt**: `findControl`/`findLayout` + `shiboken6.wrapInstance`로 기존 `cmds` 컨트롤의 `QWidget*`를 얻는다.
- **Qt → 네이티브**: `addWidgetToMayaLayout(QWidget* control, QWidget* layout, ...)`로 직접 만든 `QWidget`을 기존 네이티브 레이아웃에 끼워 넣는다.

인터넷에 흔한 방식(`cmds.modelPanel()`을 임시 창에 만든 뒤 통째로 뜯어서 손으로 만든 `QMainWindow`에 옮기기)은 Autodesk가 명시적으로 지원을 보장하지 않는 리페어런팅이다. **이 설계는 반대 방향을 택한다**: 컨테이너 자체를 네이티브로 유지(`cmds.workspaceControl` + `cmds.formLayout`/`cmds.paneLayout`, `maroDiagPanel`과 같은 패턴), `modelPanel`은 그 안에 `cmds.modelPanel()`로 직접 생성(리페어런팅 없음), 커스텀 PySide6 위젯(버튼, 이후 단계의 툴바/노드 에디터/디버그 터미널)만 `addWidgetToMayaLayout`로 같은 레이아웃에 끼워 넣는다.

이 방향은 "기존 mayaUI 디자인과 이질감이 없도록"이라는 요구도 사실상 공짜로 만족시킨다 — Maya의 `cmds` 위젯 자체가 내부적으로 Qt 위젯이고(그래서 `MQtUtil`이 찾을 수 있는 것), 한 프로세스 안의 `QApplication`은 스타일시트/팔레트를 하나만 쓴다. 새로 만드는 PySide6 위젯이 `setStyleSheet()`를 직접 호출하지만 않으면 자동으로 같은 테마를 물려받는다 — 리뷰 시 새 `.py` 파일에서 `setStyleSheet(`를 grep하는 것으로 이 규율을 기계적으로 점검할 수 있다.

### 4.3 우측 "ROS 뷰포트" 스코프 결정 (Phase 3 이후를 위한 기록, Phase 0-1에는 미적용)

씬 전체를 진짜로 Z-up으로 다시 그리는 것은 스킨된 메쉬의 경우 사실상 스켈레톤+skinCluster 전체를 복제해 별도로 변형시키는 것과 같아, 이 기능의 목적(축 바인딩 확인)에 비해 지나치게 크다. 대신 axis/joint/locator 같은 가벼운 프록시 노드만 `mayaToRosPosition`/`mayaToRosRotation`(`src/maro_transform/include/maro_transform/Convert.h`, ROS 발행 파이프라인과 동일 소스)으로 변환해 실시간 동기화하는 쪽으로 스코프를 좁힌다. 사용자가 "ros**축** 화면"이라 표현한 것과도 일치한다. **이 결정 자체는 Phase 3에서 실행되며, Phase 0-1은 우측 뷰포트를 아예 만들지 않는다** — 여기 적어 두는 이유는 Phase 1의 스파이크가 이 방향으로 확장 가능한 형태여야 하기 때문이다(네이티브 컨테이너+`modelPanel` 패턴이 두 번째 `modelPanel`을 추가하는 것을 막지 않는지 확인하는 것도 Phase 1 체크리스트의 일부).

## 5. Phase 0-1 태스크 요약

플랜 문서(`docs/superpowers/plans/2026-08-24-maro-main-ui-phase0-1.md`) 참고. 3개 태스크:

1. CMake: 다중 Python UI 모듈 스테이징을 파일 목록 순회 형태로 일반화 (기존 `maroDiagPanel.py` 동작 불변)
2. 네이티브 컨테이너(`workspaceControl`+`formLayout`) 안에 `modelPanel` 하나 + `addWidgetToMayaLayout`로 끼워 넣은 PySide6 버튼 하나 — 새 커맨드 `maroMainWindow`
3. Maro 메뉴(`cmds.menu(parent="MayaWindow", ...)`) 등록/해제 — 새 커맨드 `maroBuildMenu`, "Maro 창 열기" 1개 + "준비 중" 자리 표시자 2-3개

## 6. 테스트 전략

Task 1, 3은 mayapy 배치 테스트로 검증 가능(파일 스테이징 확인, 메뉴 존재/삭제 확인). **Task 2는 mayapy로 검증할 수 없다** — 실제 뷰포트 렌더링과 Qt 이벤트 루프가 필요하기 때문에, 대화형 Maya 2026에서 수행하는 수동 체크리스트(`docs/maro-main-ui-manual-checklist.md`, `docs/maro-panel-manual-checklist.md`와 같은 형식)가 유일한 검증 수단이다. 가장 중요한 항목은 "창을 띄운 채 `unloadPlugin`을 실행해도 크래시하지 않는가" — 이게 이 스파이크의 진짜 go/no-go 기준이다.

## 7. 범위 밖 (다음 레이어, 별도 계획)

- Phase 2 — 뷰포트 2개(우측은 아직 변환 없음)
- Phase 3 — ROS 좌표 프록시 동기화(§4.3의 스코프 결정이 여기서 실행됨)
- Phase 4 — 업로드 + 스켈레톤 추출/생성(`skinCluster` 인플루언스 추출, 없으면 바운딩박스 중심에 루트 조인트 1개만 생성 — 자동 리깅 아님)
- Phase 5 — 노드 바인딩 + capability 에디터(`maroListAxisNodes`, `maroConnectCapability`, `maroSetCapabilityOrder`, `maroUnbindAxis`, 바인딩 색상)
- Phase 6 — 디버그 터미널(`python/maroTerminal.py`, 기존 4개 진단 커맨드 그대로 재사용)
- Phase 7 — 설정 모달 실제 내용(범위 미정, 추후 별도 브레인스토밍)

## 8. 전역 제약

- 빌드는 항상 `--config Release`를 명시한다(CMake Visual Studio 멀티 컨피그 제너레이터).
- 빌드 환경: `VsDevCmd.bat`를 빌드와 같은 PowerShell 호출 안에서 설정한다.

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64 && set' 2>$null | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
cmake --build out/build --config Release
```

- `ctest --test-dir out/build -C Release --output-on-failure`는 **전부 통과해야 한다** — 이번 세션에 `maya_panel_commands`의 진짜 원인(CMake `$<CONFIG>` 누락)을 고쳤으므로 더 이상 "알려진 사전 결함"이 없다. 하나라도 실패하면 이 플랜이 만든 회귀다.
- Maya 2026(devkit `C:\Users\ckd30\Projects\devkitBase\`)이 PySide6/shiboken6를 제공한다 — 버전 호환 문제 없음.
- 새 `.py` 파일은 `setStyleSheet()`를 호출하지 않는다(Maya 전역 스타일 상속에 의존).
- 새 커맨드는 `MaroDiagPanelCommand::doIt`의 sys.path 주입 패턴을 그대로 따른다.
