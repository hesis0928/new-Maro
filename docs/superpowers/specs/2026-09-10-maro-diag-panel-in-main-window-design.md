# 진단 패널을 MaroUI 안으로 (2026-09-10)

## 1. 배경

메인 UI 로드맵(`2026-08-24-maro-main-ui-phase0-1-design.md` §3-3, §7)은
"우하단 디버그 터미널 — 기존 진단/치료 시스템(`maroDiagPanelRows`/`Detail`/
`RequestRemedy`/`ApplyRemedy`) 재사용"을 Phase 6으로 남겨 뒀다. 미구현이다
(`python/maroTerminal.py`가 없다).

**그 문서가 쓰인 뒤 상황이 바뀌었다.** 로드맵은 2026-08-24이고 Tech Diag는
2026-08-26이다. 로드맵을 쓸 당시 메인 창에는 진단 표면이 하나도 없었지만
지금은 있다:

| 표면 | 보여주는 것 | 어디에 |
|---|---|---|
| `maroDiagPanel` | boad/book 크래시 진단 이력 + remedy 적용 | 별도 workspaceControl. **Maro 메뉴에 없다** |
| `maroTechDiag` | 기구학/ROS 정합성 **능동** 검사 | MaroUI의 좌우 사이드 패널 |
| (로드맵의 디버그 터미널) | 위 첫 줄과 같은 데이터 | 미구현 |

그래도 **공백은 실재한다**: boad/book 진단 이력은 MaroUI에 전혀 없고, 그것을
보여주는 단독 패널은 메뉴에도 없어 커맨드를 직접 쳐야만 열린다.

**사용자가 고른 방향**: 세 번째 진단 표면을 새로 만들지 않고 **기존
`maroDiagPanel`을 MaroUI 안에서 그린다**. 진단 데이터의 출처가 하나로
유지되고, 새 파이썬 모듈이 늘지 않는다. 로그 스트림 형태의 "진짜 터미널"은
범위 밖이다(§7).

## 2. 배치

현재 MaroUI는 이렇다. `paneLayout`의 `vertical2`가 **좌우**라는 것은 Phase 2
수동 체크리스트에서 사람이 직접 확인한 사실이다("뷰포트가 두 개 좌우로
나란히 보인다", `docs/maro-main-ui-manual-checklist.md:146`):

```
form
└── outerPane (vertical2)
    ├── viewportRow  ── TechDiag(Maya) │ 뷰포트 2개 │ TechDiag(ROS)
    └── editorHost   ── ONE/GSON 노드 에디터
```

즉 오른쪽 절반을 노드 에디터가 통째로 쓰고 있고, **로드맵이 말한 "우하단"은
아직 존재하지 않는다.** 오른쪽 칸을 상하로 나누면 그 자리가 생긴다:

```
form
└── outerPane (vertical2)
    ├── viewportRow  ── TechDiag(Maya) │ 뷰포트 2개 │ TechDiag(ROS)
    └── rightPane (horizontal2)                        ← 신규
        ├── editorHost ── ONE/GSON 노드 에디터          (우상단, 기존 그대로)
        └── diagHost   ── 진단 패널                     (우하단, 신규)
```

`editorHost`는 부모가 `outerPane`에서 `rightPane`으로 바뀔 뿐 내부 조립은
그대로다 -- Phase 4가 `viewportPane`을 `viewportRow` 안으로 옮길 때 쓴 것과
같은 수법이다.

## 3. 임베드 방법

`maroDiagPanel.buildUI()`는 **네이티브 Maya UI**를 현재 부모 레이아웃에
그리는 함수다(`workspaceControl`의 `uiScript`가 부른다). 그래서 PySide6
위젯이 타는 두 단계(`MQtUtil.findLayout` → `addWidgetToMayaLayout`)를
**타지 않는다** -- 오히려 더 단순하다.

전역 `cmds.setParent()` 상태에 기대는 대신 **선택적 인자를 하나 더한다**:

```python
def buildUI(parent=None):
    """workspaceControl이 -uiScript로 부른다(인자 없이).
    MaroUI는 자기 레이아웃 이름을 넘겨 같은 패널을 안에 그린다."""
    form = cmds.formLayout() if parent is None else cmds.formLayout(parent=parent)
```

기존 호출부(`show()`의 `uiScript` 문자열)는 인자가 없으므로 그대로 동작한다.

`buildUI()`는 이미 끝에서 `refresh(...)`를 부르고 **form 이름을 돌려준다**.
따라서 임베드한 패널은 열자마자 채워져 있고, 돌려받은 이름을 `formLayout`
attach에 그대로 쓸 수 있다. 이 두 가지는 새로 만들 필요가 없다.

## 4. 두 인스턴스가 동시에 떠 있어도 안전하다

이건 이번에 만드는 성질이 아니라 **이미 그렇게 설계돼 있다**:

- `buildUI()`가 만드는 컨트롤은 **전부 이름 없이**(자동 생성) 만들어진다.
  고정 이름이 하나도 없으므로 충돌할 것이 없다.
- 선택 상태와 행 목록은 모듈 전역이 아니라 **클로저**(`rowsHolder`,
  `selectionHolder`)에 있다. 모듈 자신의 주석이 그 이유를 명시한다 --
  "모듈 전역이면 패널을 두 개 띄웠을 때 서로의 선택을 밟는다".

그래서 단독 창(`show()`)은 **그대로 둔다**. 둘 다 열려 있어도 각자 새로
고치고 각자 선택한다.

## 5. teardown에 넣지 않는다 (그리고 왜인지 적어 둔다)

`maroMainWindow.teardown()`은 서브시스템의 `stop()`을 모아 부른다.
`maroDiagPanel`은 여기에 **넣지 않는다**:

- `scriptJob`이 없다.
- `MTimerMessage`/idle 콜백이 없다.
- 모듈 전역 가변 상태가 없다(상수 `ROW_FIELDS`/`DETAIL_FIELDS`/
  `CONTROL_NAME`/`_PRESENCE_LABEL`뿐).

새로 고침은 사용자가 누를 때만 일어난다. 멈출 것이 없으므로 `stop()`도 없다.

**이 부재를 코드에 주석으로 남긴다.** 이 리포는 Phase 0-1/2/3에서 "주인 없는
콜백"으로 반복해서 물렸고, `teardown()`의 도크스트링이 "서브시스템이 늘 때마다
두 곳을 따로 늘리지 않기 위해서"라고 적고 있다. 그 맥락에서 새 패널만
빠져 있으면 다음 사람은 누락으로 읽는다.

## 6. 테스트 전략

| 대상 | 방식 | 배치 가능 |
|---|---|---|
| `sliceRows`/`formatLocalTime`/`_rowLabel` | 기존 순수 함수 테스트 그대로 | 예(이미 있음) |
| `buildUI(parent=...)` 인자 추가가 기존 호출부를 안 깨는가 | `show()`의 `uiScript` 문자열이 인자 없이 부르는 형태 그대로인지 | 예 |
| 레이아웃 배치, 임베드, 두 인스턴스 공존 | **수동 체크리스트** | 아니오 -- 아래 실측 |

**"배치에서 안 된다"를 이번엔 추측이 아니라 실측으로 적는다.** mayapy 배치에서
`cmds.window`/`formLayout`/`paneLayout`/`textScrollList`는 **예외를 던지지
않는다**. 대신 조회가 전부 `False`를 돌려준다 -- 컨트롤이 실제로는 만들어지지
않는다:

```
cmds.textScrollList(...)                  -> False   (이름 문자열이 아님)
cmds.textScrollList(x, q=True, allItems=True) -> False
cmds.paneLayout(p, q=True, childArray=True)   -> False
```

이게 위험한 이유는 **에러가 안 나기 때문**이다. `buildUI()`를 배치에서 부르고
아무것도 단언하지 않는 테스트는 통과하면서 아무것도 증명하지 않는다 -- 이
리포가 이미 여러 번 물린 유형이다.

**그리고 이건 "Maya 초기화 전에 들어가면 된다"로 뚫리지 않는다.** 이 세션은
같은 수법으로 세 가지 전제를 뒤집었다(Viewport 2.0은 `cmds.ogsRender`로,
QWidget은 `maya.standalone.initialize()` 전에 세운 offscreen QApplication으로,
ASan은 런타임 선로드로). 그래서 이번에도 시도했다 -- `maroQtBatch.bootstrap()`
으로 offscreen QApplication을 먼저 세우고 Maya를 초기화한 뒤에도 결과는
**똑같이 `False`**였다. Maya의 `cmds` UI 계층은 Qt 가용성과 무관하게 배치에서
꺼져 있다.

이것이 `maroCapabilityPanel`(PySide6)은 배치 테스트가 있는데
`maroDiagPanel`(네이티브)은 없는 이유이기도 하다. **다음 사람이 같은 시도를
반복하지 않도록 이 실측을 남긴다.**

수동 체크리스트에 넣을 항목:

1. MaroUI를 열면 오른쪽이 위/아래로 나뉘고 아래에 진단 패널이 보인다.
2. 아래 패널의 목록/상세/심각도 필터/새로 고침이 단독 창과 똑같이 동작한다.
3. 단독 창(`maroDiagPanel` 커맨드)을 **동시에** 띄워도 두 패널의 선택이 서로를
   밟지 않는다.
4. 진단 패널이 보이는 상태로 MaroUI를 닫아도, 이어서 플러그인을 언로드해도
   크래시가 없다.
5. Phase 2/4 회귀 재확인 -- 뷰포트 둘과 노드 에디터가 그대로다(레이아웃이
   바뀌었으므로 필요하다).

## 7. 범위 밖

- **로그 스트림 형태의 터미널** -- boad 이벤트가 시간순으로 흐르는 콘솔.
  표와 다른 정보를 주지만 세 번째 진단 표면이 되고 갱신 경로(폴링/콜백)를
  새로 설계해야 한다. 사용자가 명시적으로 이쪽을 고르지 않았다.
- **Maro 메뉴에 "진단 패널" 항목 추가** -- 접근성 문제는 실재하지만 이
  스펙이 닫는 공백(MaroUI 안에 없다)과는 별개의 결정이다.
- **자동 새로 고침** -- 지금처럼 사용자가 누를 때만 갱신한다. 자동 갱신은
  `teardown()`이 멈춰야 할 것을 만들어 §5를 무효로 만든다.
- **`maroTechDiag`와의 통합/중복 정리** -- 서로 독립된 서브시스템으로 둔다.

## 8. 전역 제약

- 빌드는 `--config Release`. 이 스펙은 `.py`만 고치지만
  **`test_main_window.py`는 스테이징 사본을 import하므로**(2026-09-10 실측)
  `python/maroMainWindow.py`를 고쳤으면 `cmake --build`가 필요하다.
- `ctest --test-dir out/build -C Release --output-on-failure` 전부 통과.
- 새 파이썬 모듈을 만들지 않는다.
- 새/수정 `.py`는 `setStyleSheet()`를 호출하지 않는다.
- `maroMainWindow.buildUI()`는 배치에서 `RuntimeError`를 던지는 기존 가드를
  유지한다.
- 새 레이아웃 이름 상수(`DIAG_HOST_NAME`)는 C++ 계약이 **아니다**.
  `MaroPluginMain.cpp`의 MEL 정리는 `CONTROL_NAME`과 두 뷰포트 이름만
  안다 -- `editorHost`가 그랬듯 새 `formLayout`도 부모가 사라지면 함께
  사라지므로 정리 대상에 넣지 않는다.
