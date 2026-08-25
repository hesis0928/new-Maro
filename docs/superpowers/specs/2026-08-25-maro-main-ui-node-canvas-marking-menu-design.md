# Maro 메인 UI — 노드 캔버스 + 방사형 마킹 메뉴 재설계 (2026-08-25)

## 1. 배경

Phase 4(`2026-08-25-maro-main-ui-phase4-axis-capability-editor-design.md`)는 축 목록(`QListWidget`) + capability 스택 목록(`QListWidget`) + 타입별 추가 버튼 7개로 구성된 `maroAxisPanel.AxisPanel`을 구현하고 리뷰까지 마쳤다. 사용자가 대화형 Maya에서 실제 창을 띄워 보니 이 레이아웃이 쓰기 불편했고("UI 배치가 너무 이상해"), 브레인스토밍을 거치며 요구사항이 세 차례 확장됐다:

1. 레이아웃: 뷰포트를 상단에, 편집 영역을 하단에.
2. capability 추가를: 서랍식 세로 리스트 → Maya 뷰포트의 vertex/edge/face 마킹 메뉴와 동일한 우클릭-홀드-드래그-릴리즈 방사형 메뉴로.
3. 캔버스 모델 자체를: "리스트에서 고르기" → "캔버스 위 노드를 우클릭해서 그 자리를 중심으로 능력을 부여하고, 노드끼리 체인/중첩으로 스택을 표현"하는 완전한 노드 그래프 에디터로.

이 문서는 Phase 4가 이미 구현한 C++ 커맨드 5종(`maroListAxisNodes`/`maroAddCapability`/`maroConnectCapability`/`maroDisconnectCapability`/`maroUnbindAxis`)과 기존 `maroBindAxis`를 그대로 재사용하고, **`python/maroAxisPanel.py`의 내부 구현(위젯)만 완전히 새로 짠다.** C++ 쪽 변경은 캔버스 좌표 저장을 위한 속성 2개 추가뿐이다.

## 2. 레이아웃 재구성

```
workspaceControl
└── formLayout(form)
    ├── formLayout(menuBar)                 ← 신규, 얇은 띠
    │   └── [테스트 아이콘 버튼 (QToolButton, hover 시 "test" 툴팁)]
    └── paneLayout("horizontal2") outerPane  ← vertical2 → horizontal2로 변경(좌우 분할 → 상하 분할)
        ├── paneLayout("vertical2") viewportPane  ← 기존 그대로(내부 불변, Maya/ROS 좌우)
        └── formLayout editorHost                 ← 기존 그대로, 안의 위젯만 교체
            └── [MaroNodeCanvas 위젯, MQtUtil로 임베드 — 기존과 동일한 임베드 두 단계 재사용]
```

- `outerPane`의 `configuration`만 `"vertical2"`에서 `"horizontal2"`로 바꾼다(Maya `paneLayout`에서 `vertical2`는 좌우 분할, `horizontal2`는 상하 분할 — 이름이 분할 방향이 아니라 분할선의 방향을 가리키는 Maya의 기존 관례). `viewportPane`은 내부 구성을 그대로 유지하므로 `_buildLabeledViewport` 호출부는 손대지 않는다.
- 테스트 버튼: 지금의 `QPushButton("테스트")`(가로 전체 폭)를 `QToolButton`으로 바꾸고 고정 크기(24x24 정도)로 축소, `setToolTip("test")`. `menuBar` formLayout은 이 버튼 하나만 왼쪽에 붙인 얇은 띠(높이 28px 고정)로, `form`의 맨 위에 attachForm, `outerPane`이 그 아래에 attachControl — 지금 `buildUI()`의 마지막 `formLayout(form, edit=True, attachForm=[...])` 블록 구조를 그대로 재사용하되 `buttonName` 자리에 새 아이콘 버튼 이름이 들어간다.
- `_onTestButtonClicked`는 이름과 동작 그대로 유지 — 이 버튼은 Phase 0-1 스파이크의 카나리아이자 수동 체크리스트가 참조하는 오브젝트라 로직은 안 건드리고 모양만 바꾼다.

## 3. 노드 캔버스 — 상호작용 모델

### 3.1 기본 개념

캔버스에는 축(axis)마다 정확히 **노드 하나**가 있다. 노드는 위아래 두 영역으로 나뉜 하나의 박스다 — 이 구분은 §3.6의 "축 이름 영역만 따로 우클릭" 동작이 성립하는 전제다:

- **상단(축 이름 영역)**: `jointName`이 있으면 그 값, 없으면 축 노드 이름(예: `axis1`). 항상 표시.
- **하단(capability 상태 영역)**: 세 가지 표시 상태 중 하나.

| capability 상태 | 표시 | capabilityIn 연결 수 |
|---|---|---|
| 비어 있음 | `undefined`(점선 테두리) | 0 |
| 능력 1개 | 그 capability 타입 이름(예: `Rotation`) | 1 |
| 능력 2개 이상 | 대표 라벨 + 우측 `▾` | 2개 이상 |

**체인으로 옆에 박스가 이어지는 형태(v1 브레인스토밍 초안)는 폐기됐다** — 능력이 여러 개 쌓여도 캔버스 위 노드 개수는 늘지 않고, 그 노드 하나가 접혔다 펼쳐졌다 할 뿐이다. 이는 초기 "체인" 아이디어보다 캔버스가 축 개수만큼만 자라서 다축 상황에서 캔버스가 옆으로 무한히 늘어나는 걸 막는다.

### 3.2 노드 생성 — 빈 캔버스 우클릭

- **우클릭 후 그 자리에서 바로 릴리즈**(드래그 없음, 클릭에 가까움) → 그 정확한 좌표에 새 축(`maroAxis` 신규 생성) + 빈 `undefined` 노드가 생긴다.
- **우클릭한 채로 드래그**(릴리즈 안 함) → §3.3의 1단계 방사형 메뉴가 그 우클릭 지점을 중심으로 즉시 펼쳐진다. 이 메뉴에서 `Axis`가 아닌 capability 타입 하나를 골라 릴리즈하면, 그 지점에 새 축이 생성되는 동시에 그 capability까지 바로 부여된다(빈 `undefined` 상태를 거치지 않고 한 제스처로 완료).
- 두 경우 모두 "그 우클릭 지점"이 새 축 노드의 캔버스 좌표가 된다. 중첩 메뉴를 몇 단계 거쳤어도(예: `Axis` → `+ 새 축`) 기준점은 항상 **최초 우클릭 지점**이다 — 중첩 메뉴 자체는 그 지점 주변에 겹쳐 뜰 뿐, 새로운 기준점을 만들지 않는다.
- **바인딩 시점**: 새 축이 생성되는 바로 그 순간(우클릭 즉시 릴리즈든, 방사형 메뉴에서 릴리즈든), 그 시점에 Maya 씬에 선택된 오브젝트가 하나라도 있으면 그것을 타겟으로 `maroBindAxis(axis, selection[0])`를 같은 동작 안에서 자동 호출한다. 선택이 없으면 unbound로 남고, 나중에 §3.6의 수동 `Bind`로 연결한다. 선택이 여러 개면 `selection[0]`(가장 먼저 선택된 것, `cmds.ls(selection=True)` 순서) 하나만 쓴다 — 다중 선택으로 축 여러 개를 한 번에 만드는 기능은 이번 범위 밖.

### 3.3 방사형 마킹 메뉴

**호출**: 캔버스 위 임의의 노드(또는 빈 공간)를 우클릭한 채로 드래그하면, 우클릭 지점을 중심으로 원형으로 항목이 펼쳐진다(Maya 뷰포트의 vertex/edge/face 마킹 메뉴와 동일 제스처). 항목 쪽으로 커서를 이동한 뒤 릴리즈하면 그 항목이 확정된다. 드래그 없이 그냥 릴리즈하면 메뉴는 취소된다(아무 것도 적용 안 함) — 단, 빈 캔버스에서의 "그 자리 즉시 릴리즈"(§3.2)만 예외로 노드를 만든다.

**1단계 항목(최대 8개)**:
- `Axis` — **오직 그 노드가 아직 `undefined`(능력 0개)일 때만** 나타난다. 이미 능력이 하나라도 있는 노드에는 나오지 않는다(축은 이미 정해졌으므로).
- `Rotation` / `Translation` / `Limit` / `TranslationLimit` / `SensorDirection` / `SensorRange` / `Coupling` — 항상 나타난다.

**`Axis` 하위 메뉴**: `Axis`로 커서를 올리면(릴리즈 전) 그 항목을 새 중심으로 2단계 메뉴가 펼쳐지고, 1단계 메뉴는 반투명(대략 opacity 0.35)해진다:
- 기존 축 이름들("axis1로 이동", "axis2로 이동", ...) — 릴리즈하면 **아무 것도 만들거나 바꾸지 않고** 캔버스 뷰를 그 축의 기존 노드로 팬/센터링만 한다(다축 상황에서 캔버스를 스크롤해서 찾을 필요 없이 빠르게 이동하는 용도).
- `+ 새 축` — 릴리즈하면 §3.2에서 말한 "최초 우클릭 지점"에 새 축을 만든다.

**하위 항목이 있는 모든 노드는 이 규칙을 따른다**: 상위 항목을 새 중심으로 다음 단계 메뉴가 펼쳐지고, 그 이전 단계는 반투명해진다. 몇 단계든 중첩 가능. 이번 7개 capability 타입 자체는 하위 메뉴가 없는 리프(leaf)이므로 지금은 `Axis`만 2단계를 갖지만, 이 상호작용은 특정 타입에 종속되지 않은 범용 컴포넌트로 짠다(향후 capability 타입이 하위 옵션을 가지게 되어도 같은 코드 경로를 탄다).

**2단계 이후 메뉴에는 우측에 작은 "◀ 상위로" 버튼**이 있어 릴리즈 전에 이전 단계로 돌아갈 수 있다.

**1차 구동값 상호배타 규칙**(Phase 4 §3, 기존): rotation(0)/translation(4)/coupling(6) 중 이미 하나가 스택에 있는 축에 나머지 두 타입 중 하나를 고르면 `maroAddCapability`가 거부한다(`BoadMaro::error`). 메뉴 자체에서 그 항목을 미리 숨기거나 비활성화하지 않는다(YAGNI — 서버 쪽이 이미 검증하므로 클라이언트가 규칙을 중복으로 알 필요가 없고, 실패 시 아래 §3.5의 에러 표시로 충분하다).

### 3.4 능력 적용/중첩/제거

- 리프 항목(7개 capability 타입 중 하나)에서 릴리즈 → 그 노드가 `undefined`였다면 `maroAddCapability(axis, type=...)`; 이미 능력이 있었다면 같은 커맨드가 다음 빈 논리 인덱스에 새 capability를 추가(중첩) — Phase 4가 이미 구현한 `nextFreeCapabilitySlot()` 그대로 재사용, 새 커맨드 불필요.
- **Delete 키**(노드가 접힌/펼치지 않은 상태에서 선택된 채로): 가장 나중에 추가된 능력 하나만 제거한다. 구현은 `maroListAxisNodes(capabilities=axis)`로 현재 스택을 조회해 가장 큰 `logicalIndex`를 찾고 `maroDisconnectCapability(axis, index=그값)`을 호출 — 새 C++ 커맨드 불필요, 파이썬 쪽 로직만으로 충분. 능력이 1개였다면 이 한 번으로 `undefined`로 돌아간다.
- **드롭다운(`▾`) 펼친 상태에서 개별 항목을 선택하고 Delete**: 그 항목만 `maroDisconnectCapability(axis, index=그 항목의 logicalIndex)`로 제거(스택 중간을 뽑아도 되는 기존 커맨드 계약 그대로).
- `▾` 클릭 또는 노드 더블클릭 → 같은 동작(드롭다운 펼치기/접기 토글). 펼쳐진 목록은 `1. Rotation` / `2. Limit` / ... 식으로 `logicalIndex` 오름차순.

### 3.5 실패 처리

`maroAddCapability`/`maroConnectCapability`가 상호배타 규칙 위반 등으로 `RuntimeError`를 던지면, 마킹 메뉴는 이미 닫힌 뒤이므로(릴리즈 시점에 커맨드를 부르므로) 노드는 원래 상태 그대로 두고 캔버스 하단에 짧은 오류 텍스트를 잠깐 표시한다(기존 `AxisPanel._onAddCapabilityClicked`의 `print()` 처리보다 한 단계 나은 최소한의 사용자 피드백 — 새 위젯이라 이 정도 개선은 자연스럽다).

### 3.6 축 노드 자체 조작

축 이름이 표시된 부분(캔버스 노드의 라벨 영역, capability 표시와는 별개 클릭 영역)을 우클릭하면 별도의 작은 메뉴가 뜬다(방사형이 아니어도 됨 — 항목이 1~2개뿐이라 과함):
- 바인딩 안 된 축(§3.2의 자동 바인딩이 생성 시점에 선택이 없어서 안 걸렸거나, Unbind 후 다시 연결하고 싶은 경우) → `Bind`(그 시점의 씬 선택을 타겟으로 `maroBindAxis(axis, selection[0])` 호출 — §3.2의 자동 바인딩과 완전히 같은 로직을 수동으로 다시 트리거하는 것뿐이라 별도 구현 없이 같은 헬퍼 함수를 재사용한다)
- 바인딩된 축 → `Unbind`(`maroUnbindAxis(axis)`)
- 다른 타겟으로 바꾸고 싶을 땐 `Unbind` 후 새 오브젝트를 선택하고 다시 `Bind` — 둘을 합친 "Rebind" 항목은 만들지 않는다(YAGNI, 두 번의 명시적 조작이 실수로 잘못된 타겟에 재연결하는 사고를 줄인다).

### 3.7 캔버스 좌표 저장 — `MaroAxisNode` 신규 속성

이 프로젝트의 기존 철학("Maya DG가 유일한 진실")을 그대로 따라, 캔버스 위치를 별도 파일/사이드카에 저장하지 않고 `maroAxis` 노드 자체에 얹는다:

- `aCanvasPosX`, `aCanvasPosY` — `MFnNumericAttribute::kDouble`, `storable(true)`, `keyable(false)`, `hidden(true)`(Attribute Editor의 일반 채널에는 안 보이게). `compute()`에 관여하지 않는 순수 UI 부기 데이터 — 노드 트랜스폼의 `translateX`/`translateY`가 지오메트리 데이터이면서 계산에 안 쓰이는 것과 같은 성격.
- `maroAddCapability`로 새 축이 이번 흐름에서 생성될 때(§3.2)는 캔버스 쪽에서 `cmds.createNode("maroAxis")` 직후 `cmds.setAttr`로 두 값을 바로 써넣는다 — 새 C++ 커맨드는 필요 없다(단순 속성 2개 설정이라 undo 원자성 요구가 없음, Phase 4가 이미 확립한 "불필요한 커맨드를 만들지 않는다" 관례).
- `maroListAxisNodes`의 `AXIS_FIELDS`에 이 두 값을 추가해야 캔버스가 매번 씬을 다시 읽을 때 저장된 위치를 복원할 수 있다 — **기존 8필드 계약이 10필드로 바뀌는 breaking change**이므로 `python/maroAxisPanel.py`와 `tests/maya/test_axis_editor_commands.py`의 관련 부분을 함께 고친다.

## 4. `python/maroAxisPanel.py` 재작성

모듈 이름과 `buildWidget()`/`start()`/`stop()` 진입점 계약은 그대로 유지한다(`maroMainWindow.py`가 이 세 이름만 알면 되므로 임베드 코드는 변경 없음). 내부만 완전히 새로 짠다:

- **`MaroNodeCanvas(QtWidgets.QWidget)`** — `paintEvent`로 노드/커넥터/마킹 메뉴를 직접 그리고, `mousePressEvent`/`mouseMoveEvent`/`mouseReleaseEvent`/`mouseDoubleClickEvent`로 §3의 상호작용 상태 기계를 구현한다. `QGraphicsView`/`QGraphicsScene`을 쓰지 않는 이유: 마킹 메뉴는 노드 그래프 아이템이 아니라 임시 오버레이이고, 우클릭-홀드-드래그-릴리즈 제스처 판정(눌린 지점에서 일정 픽셀 이상 움직였는지로 "메뉴 열기" vs "그 자리 클릭"을 가른다)이 커스텀 페인팅 쪽이 `QGraphicsScene` 아이템 계층보다 직접적이다.
- 내부 상태: `_axisNodes`(축별 위치/표시 상태 캐시, `maroListAxisNodes` 결과로 매번 갱신), `_menuStack`(현재 열린 마킹 메뉴의 단계별 중심점+항목 목록, 비어 있으면 메뉴 없음).
- 씬 쪽 진짜 데이터(어떤 축에 어떤 capability가 몇 개 있는지)는 항상 커맨드 조회로 다시 읽는다 — 캔버스 위젯은 좌표만 자체 캐시하고 capability 내용은 캐시하지 않는다(`AxisPanel`이 지금도 따르는 "패널은 자체 상태를 갖지 않는다" 원칙, §9 그대로 계승).
- **순수 함수 분리 유지**: `sliceAxisRows`/`sliceCapabilityRows`(필드 수만 8→10, 5는 그대로)는 그대로 두고 mayapy 배치 테스트로 계약을 검증하는 기존 패턴을 유지한다. 새로 추가되는 순수 함수: `computeRadialLayout(centerX, centerY, itemCount, radius)`(각 항목의 화면 좌표 계산, Qt 없이 테스트 가능), `hitTestRadialItem(cursorX, cursorY, items)`(드래그 중 어느 항목 위에 있는지 판정).
- `QToolButton`/`QListWidget` 등 기존 위젯 트리는 전부 제거된다 — 하지만 `setStyleSheet()` 금지 규율(§4.2, `test_main_window.py`의 grep 검사)은 새 캔버스 위젯에도 그대로 적용된다. 캔버스의 색/테두리는 `QPainter`로 직접 그리므로 스타일시트 자체가 필요 없다(오히려 이 규율을 지키기 쉬워짐).
- 씬 선택 ↔ 캔버스 양방향 동기화는 개념적으로 동일하게 유지: 캔버스에서 축 노드를 클릭하면 바인딩된 타겟(없으면 축 자신)을 `cmds.select`, `SelectionChanged` 콜백은 선택된 오브젝트가 속한 축의 노드를 캔버스에서 하이라이트 + 필요하면 뷰를 그쪽으로 팬. `start()`/`stop()`의 `scriptJob` 생명주기 코드(§9 원 설계)는 변경 없이 그대로 가져온다.

## 5. 캔버스 팬(pan)

축이 여러 개면 한 화면에 다 안 들어올 수 있으므로 최소한의 팬은 필요하다(§3.3의 "axis1로 이동"이 의미를 가지려면). 마우스 휠 드래그(중간 버튼) 또는 빈 캔버스 좌클릭 드래그로 뷰를 이동한다. **줌은 이번 범위 밖**(YAGNI — 축 개수가 아주 많아지는 상황은 아직 안 다가온 문제이고, 필요해지면 별도로 추가).

## 6. 테스트 전략

- `tests/maya/test_axis_editor_commands.py` — 기존 필드 수 검증(8/5)을 10/5로 갱신, `aCanvasPosX/Y` 왕복(설정→`maroListAxisNodes` 조회) 케이스 추가.
- `tests/maya/test_axis_panel.py`(모듈명은 유지, 내용 대체) — `computeRadialLayout`/`hitTestRadialItem`/`sliceAxisRows`/`sliceCapabilityRows` 전부 순수 함수라 mayapy 배치로 완전히 테스트 가능. **`QWidget` 생성은 여전히 하지 않는다**(기존 하드 제약 그대로 — 배치 mayapy는 QGuiApplication이라 QWidget 생성 시 프로세스가 abort함, `maroMainWindow.py` 모듈 docstring 참고).
- 마킹 메뉴의 실제 마우스 제스처, 반투명 렌더링, 팬/더블클릭은 대화형 Maya 수동 체크리스트로만 검증 가능 — `docs/maro-main-ui-manual-checklist.md`에 새 절 추가(1단/2단 메뉴 열기, Axis 항목의 노출 조건, Delete 동작 두 가지, 드롭다운 펼치기, Bind/Unbind, 레이아웃 재구성 후 Phase 2/3 회귀 재확인).

## 7. 범위 밖

- 캔버스 줌.
- 노드 자유 드래그 재배치(현재는 생성 시점의 우클릭 좌표로 고정 — 재배치가 필요해지면 드래그-이동 제스처를 별도로 추가할 수 있으나 이번엔 안 함).
- capability 타입 자체가 하위 옵션을 갖는 경우(§3.3에서 인터랙션 컴포넌트는 범용으로 짜 두지만, 실제 그런 타입은 아직 없음).
- `maroSetCapabilityOrder`(스택 재배열) — Phase 4에서 이미 범위 밖으로 뺀 것 그대로 유지.
- 곡선 그래프 편집 UI — Phase 4 §11 그대로 유지.

## 8. 전역 제약

- 빌드는 항상 `--config Release`, `ctest --test-dir out/build -C Release --output-on-failure` 전부 통과.
- 새/수정 `.py`는 `setStyleSheet()`를 호출하지 않는다.
- `aCanvasPosX/Y`는 `compute()`에 관여하지 않는다 — `attributeAffects` 등록 대상이 아니다.
- `maroAxisPanel.py`의 `buildWidget()`/`start()`/`stop()` 진입점 시그니처는 유지한다(`maroMainWindow.py`가 이 계약에 의존).
- `AXIS_FIELDS`가 8→10으로 바뀌므로 이를 참조하는 모든 곳(파이썬/C++ 양쪽 `maroListAxisNodes` 구현, 테스트)을 한 커밋 단위로 함께 고친다 — 필드 수가 어긋난 채 절반만 배포되면 배열 파싱이 조용히 깨진다.
