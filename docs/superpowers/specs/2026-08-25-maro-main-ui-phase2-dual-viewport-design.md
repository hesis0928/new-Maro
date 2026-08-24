# Maro 메인 UI Phase 2 — 듀얼 뷰포트 설계 (2026-08-25)

## 1. 배경

Phase 0-1(`docs/superpowers/specs/2026-08-24-maro-main-ui-phase0-1-design.md`)에서 네이티브 `modelPanel`(실제 3D 뷰포트) 하나와 PySide6 위젯이 같은 `workspaceControl` 안에 공존하고, 플러그인을 언로드해도 Maya가 크래시하지 않는다는 것을 대화형 Maya 2026에서 직접 검증했다(`docs/maro-main-ui-manual-checklist.md`, 전부 PASS). 이 검증으로 사용자가 원래 요청한 "좌측엔 마야축 화면, 우측은 ROS축 화면"의 기술적 기반이 확인됐으므로, 이번 단계에서는 뷰포트를 하나에서 둘로 늘린다.

## 2. 범위: 뷰포트 2개, 아직 변환 없음

우측 뷰포트에 ROS 좌표계로 변환된 내용을 실제로 채우는 것은 다음 단계(Phase 3)다. **이번 단계는 두 개의 독립된 `modelPanel`이 한 창 안에 나란히 공존하면서 둘 다 정상적으로 렌더링/조작되는지만 증명한다** — 지금은 우측도 좌측과 똑같은 씬을 별개의 카메라로 보여줄 뿐이다. Phase 0-1과 같은 이유로 스코프를 좁힌다: 코드 하나 없이 껍데기부터 사람이 직접 확인해야 하는 항목을 먼저 확정해 둔다.

## 3. 설계 결정

1. **레이아웃**: `buildUI()`의 루트 `formLayout` 아래, 기존 "테스트" 버튼(전체 폭, 상단 띠)은 그대로 유지 — 스파이크 산출물이지만 `paneLayout`으로 구조가 바뀐 뒤에도 네이티브+Qt 임베딩이 여전히 성립하는지 재확인하는 회귀 검사 역할을 겸한다. 그 아래에 `cmds.paneLayout(configuration="vertical2")`를 두고, 좌/우 각각에 작은 텍스트 라벨(`cmds.text()`)과 `modelPanel`을 하나씩 놓는다.
2. **패널 이름**: 위치(Left/Right)가 아니라 역할로 짓는다 — `VIEWPORT_NAME_MAYA = "maroMainWindowViewportMaya"`, `VIEWPORT_NAME_ROS = "maroMainWindowViewportRos"`. Phase 3가 우측 패널을 좌표 변환 대상으로 지목할 때 이름 자체가 의미를 갖도록 하기 위해서다. 기존 `VIEWPORT_NAME` 단수형은 사라진다.
3. **라벨**: 각 패널 바로 위에 "Maya" / "ROS" 한 줄씩. 아직 기능 차이는 없지만 사용자가 원래 표현한 "마야축 화면"/"ROS축 화면"이라는 구분을 미리 시각적으로 잡아 둔다.
4. **카메라**: 둘 다 Maya 기본값(`persp`), 서로 독립. 동기화는 하지 않는다 — Phase 3에서 우측 콘텐츠 자체가 달라지면 "카메라 동기화"라는 개념 자체가 다르게 정의돼야 하므로, 지금 만들어봐야 버릴 코드다.
5. **chrome 숨김**: 기존 `_hideViewportChrome()`을 두 패널 모두에 그대로 적용(로직 변경 없음, 호출만 두 번).
6. **C++/Python 이름 계약 확장**: `uninitializePlugin`의 언로드 정리(`MaroPluginMain.cpp`)가 지금 `maroMainWindowViewport` 패널 하나만 지우는데, 이제 두 패널을 다 지워야 한다. Phase 0-1의 최종 리뷰(I7)가 지적했던 것과 같은 종류의 계약이므로, `tests/maya/test_main_window.py`의 기존 "C++ 소스를 직접 읽어서 이름이 실제로 있는지 대조" 패턴을 그대로 두 이름에 다 적용한다.

## 4. 테스트 전략

Phase 0-1과 같은 한계가 그대로 적용된다: mayapy 배치 모드로는 "두 패널이 등록되고, 이름이 C++/Python 양쪽에서 일치하고, `buildUI()`가 배치 모드를 여전히 거부하는지"까지만 자동 확인 가능하다. 실제로 두 뷰포트가 각각 렌더링되고 독립적으로 조작되는지, 언로드 시 두 패널이 다 정리되는지는 `docs/maro-main-ui-manual-checklist.md`에 새 섹션을 추가해 대화형 Maya에서 확인한다.

## 5. 범위 밖 (다음 단계)

- 우측 뷰포트의 실제 ROS 좌표 변환 콘텐츠(Phase 3) — `mayaToRosPosition`/`mayaToRosRotation` 재사용, axis/joint/locator 프록시로 스코프 한정(Phase 0-1 설계 스펙 §4.3에 이미 기록된 결정).
- 두 카메라 간 동기화 여부 — Phase 3에서 우측 콘텐츠가 확정된 뒤 재검토.
- 라벨 스타일링/실제 아이콘 등 시각적 다듬기.

## 6. 전역 제약

- 빌드는 항상 `--config Release`를 명시한다.
- `ctest --test-dir out/build -C Release --output-on-failure`는 전부 통과해야 한다(사전 결함 없음).
- 새 `.py`/수정되는 `.py`는 `setStyleSheet()`를 호출하지 않는다.
- 새 커맨드/모듈이 필요해지면 기존 `MaroPythonBridge.h`의 `runPluginPythonModule` 패턴을 그대로 재사용한다(이번 단계는 새 커맨드가 필요 없을 가능성이 높다 — `maroMainWindow` 하나로 충분).
