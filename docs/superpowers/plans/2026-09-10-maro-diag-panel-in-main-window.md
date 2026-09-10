# 진단 패널을 MaroUI 안으로 — 구현 계획

> **에이전트 작업자에게:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development(권장)
> 또는 superpowers:executing-plans로 태스크 단위로 구현하라.

**목표:** 기존 `maroDiagPanel`을 MaroUI 오른쪽 아래 칸에서 그린다. 단독
창은 그대로 남는다.

**설계:** `docs/superpowers/specs/2026-09-10-maro-diag-panel-in-main-window-design.md`

**아키텍처:** `maroDiagPanel.buildUI()`에 선택적 `parent` 인자를 하나 더하고,
`maroMainWindow.buildUI()`가 오른쪽 칸을 `paneLayout(configuration="horizontal2")`
로 감싼 뒤 그 아래쪽에 진단 패널을 그린다. 새 모듈 없음, 새 커맨드 없음,
`teardown()` 변경 없음.

**기술 스택:** Maya 네이티브 UI(`cmds.paneLayout`/`formLayout`), mayapy 배치
테스트(계약 수준만), 수동 체크리스트.

## 전역 제약

- 빌드는 `--config Release`. **이 계획이 고치는 두 `.py` 모두 빌드가
  필요하다** -- `test_main_window.py`와 `test_panel_commands.py` 둘 다
  플러그인 옆 **스테이징 사본**을 import한다(2026-09-10 실측).
  `test_panel_commands.py`는 `sys.path.insert`를 하지만 인자가 `pluginDir`
  이라 소스가 아니다 -- **insert 유무가 아니라 인자를 봐야 한다.**
  안전한 기본값: `.py`를 고쳤으면 그냥 빌드한다.
- VS 환경은 빌드와 **같은 셸 호출** 안에서 잡는다.
- `ctest --test-dir out/build -C Release --output-on-failure` 전부 통과.
- 새 파이썬 모듈을 만들지 않는다.
- 새/수정 `.py`는 `setStyleSheet()`를 호출하지 않는다.
- `maroMainWindow.buildUI()`의 배치 모드 `RuntimeError` 가드를 유지한다.
- `maroDiagPanel.show()`(단독 창)의 동작을 바꾸지 않는다.
- **배치에서 네이티브 UI를 만들려고 시도하지 마라.** `cmds.formLayout` 등은
  예외 없이 `False`를 돌려준다(설계 스펙 §6 실측). `buildUI()`를 배치에서
  부르는 테스트는 아무것도 증명하지 못한다.

## 파일 구조

| 파일 | 변경 |
|---|---|
| `python/maroDiagPanel.py` | `buildUI(parent=None)` |
| `tests/maya/test_diag_panel.py` (없으면 `test_panel_commands.py`) | 계약 테스트 2건 |
| `python/maroMainWindow.py` | 오른쪽 칸을 `horizontal2`로 감싸고 진단 패널 임베드 |
| `docs/maro-main-ui-manual-checklist.md` | 새 절 |

새 파일 없음(테스트 파일은 기존 것에 붙인다 -- Task 1 Step 1 참고).

---

### Task 1: `buildUI`가 부모를 받는다

**Files:**
- Modify: `python/maroDiagPanel.py:150-152`
- Test: 아래 Step 1이 지정하는 기존 테스트 파일의 teardown 앞

**Interfaces:**
- Produces: `maroDiagPanel.buildUI(parent=None) -> str`. `parent`가 None이면
  현재 부모 레이아웃에 그린다(기존 동작 그대로). 문자열이면 그 레이아웃의
  자식으로 그린다. 반환값은 예전과 같이 이 패널의 루트 `formLayout` 이름.

- [ ] **Step 1: 붙일 테스트 파일을 정한다**

```bash
ls tests/maya/ | grep -i "diag_panel\|panel_commands"
```

`maroDiagPanel`의 순수 함수를 이미 테스트하는 파일이 있으면 거기에 붙인다.
없으면 `tests/maya/test_panel_commands.py`에 붙이고, 그것도 없으면
`tests/maya/test_diag_panel.py`를 새로 만들되 **`tests/CMakeLists.txt`의
`maya_test` 목록에 이름을 추가한다**(추가하지 않으면 파일만 있고 ctest가
영영 돌리지 않는다).

- [ ] **Step 2: 실패하는 테스트를 쓴다**

정한 파일의 teardown 바로 앞에:

```python
import inspect  # noqa: E402

print("[test] maroDiagPanel.buildUI parent 인자")

# 임베드 호출부(maroMainWindow)가 부모를 넘길 수 있어야 한다.
_sig = inspect.signature(maroDiagPanel.buildUI)
assert "parent" in _sig.parameters, list(_sig.parameters)
assert _sig.parameters["parent"].default is None, _sig.parameters["parent"].default

# 그리고 단독 창은 여전히 **인자 없이** 부를 수 있어야 한다. workspaceControl은
# uiScript 문자열로 부르므로 시그니처가 깨져도 배치 테스트가 잡아주지 않는다
# -- 대화형 Maya에서 패널을 열 때서야 터진다. 그래서 그 문자열을 직접 본다.
_showSource = inspect.getsource(maroDiagPanel.show)
assert "maroDiagPanel.buildUI()" in _showSource, _showSource

print("buildUI(parent=...) contract OK")
```

이 파일이 `maroDiagPanel`을 아직 import하지 않으면 상단 import 블록에
추가한다. 그 파일이 소스 `python/`을 `sys.path`에 넣는지 확인하고, 안 넣으면
`test_urdf_export.py:19-21`과 같은 4줄을 복사해 넣는다.

- [ ] **Step 3: 실패를 확인한다**

```bash
ctest --test-dir out/build -C Release -R <그 테스트 이름> --output-on-failure
```

Expected: FAIL -- `AssertionError: ['']` 또는 `parent`가 없다는 목록.

- [ ] **Step 4: 구현한다**

`python/maroDiagPanel.py`의 이 두 줄:

```python
def buildUI():
    """workspaceControl이 -uiScript로 부른다."""
    form = cmds.formLayout()
```

을 이것으로 바꾼다:

```python
def buildUI(parent=None):
    """이 패널을 그리고 루트 formLayout 이름을 돌려준다.

    parent가 None이면 현재 부모 레이아웃에 그린다 -- workspaceControl이
    -uiScript로 부를 때가 이 경우다(`show()` 참고). MaroUI는 자기 레이아웃
    이름을 넘겨 **같은 패널을 자기 안에** 그린다.

    두 인스턴스가 동시에 떠 있어도 안전하다: 아래 컨트롤은 전부 이름 없이
    만들어지고(고정 이름 충돌 없음) 선택/행 상태는 모듈 전역이 아니라
    클로저에 있다(rowsHolder/selectionHolder의 주석 참고).
    """
    form = cmds.formLayout() if parent is None else cmds.formLayout(parent=parent)
```

- [ ] **Step 5: 통과를 확인한다**

```bash
ctest --test-dir out/build -C Release -R <그 테스트 이름> --output-on-failure
```

Expected: PASS -- `buildUI(parent=...) contract OK`

- [ ] **Step 6: 커밋**

```bash
git add python/maroDiagPanel.py tests/ && git commit -m "feat(diag): let buildUI draw into a caller-supplied layout"
```

---

### Task 2: MaroUI 오른쪽 칸을 상하로 나누고 진단 패널을 넣는다

**Files:**
- Modify: `python/maroMainWindow.py` (`buildUI()`의 `outerPane`/`editorHost` 부분)
- Modify: `docs/maro-main-ui-manual-checklist.md` (`## Maro 환경설정 창` 바로 앞)

**Interfaces:**
- Consumes: Task 1의 `maroDiagPanel.buildUI(parent=...)`.
- Produces: 없음(새 상수도, 새 커맨드도 만들지 않는다).

**이 태스크는 배치에서 검증할 수 없다.** `maroMainWindow.buildUI()`는 배치에서
`RuntimeError`를 던지고, 네이티브 UI는 배치에서 껍데기다(설계 스펙 §6 실측).
그래서 **RED/GREEN 사이클이 없다** -- 대신 기존 테스트가 계속 통과하는 것을
확인하고, 실제 검증은 Step 4가 쓰는 수동 체크리스트가 맡는다.

- [ ] **Step 1: 오른쪽 칸을 감싼다**

`python/maroMainWindow.py`에서 지금 이렇게 되어 있는 곳:

```python
    editorHost = cmds.formLayout(EDITOR_HOST_NAME, parent=outerPane)
```

을 이것으로 바꾼다:

```python
    # 오른쪽 절반을 위/아래로 나눈다. paneLayout의 vertical2는 **좌우**이고
    # (Phase 2 수동 체크리스트에서 사람이 확인한 사실 -- "뷰포트가 두 개
    # 좌우로 나란히 보인다"), 그래서 outerPane의 두 번째 칸은 지금까지
    # 노드 에디터가 오른쪽 절반을 통째로 쓰고 있었다. horizontal2로 한 겹
    # 감싸면 로드맵이 말한 "우하단"이 처음으로 실제로 생긴다.
    rightPane = cmds.paneLayout(configuration="horizontal2", parent=outerPane)

    # Phase 4: 축/capability 에디터 패널. 부모가 outerPane -> rightPane으로
    # 바뀔 뿐 내부 조립은 그대로다. modelPanel이 아닌 평범한 formLayout이라
    # (_buildLabeledViewport의 modelPanel과 달리) 전역 패널 레지스트리에
    # 등록되지 않는다 -- 부모가 사라지면 이 레이아웃도 함께 완전히 사라진다.
    # 그래서 _deleteStalePanel 같은 잔여물 정리가 필요 없다.
    editorHost = cmds.formLayout(EDITOR_HOST_NAME, parent=rightPane)
```

바로 위에 있던 기존 주석 블록("Phase 4: 축/capability 에디터 패널 ... 필요
없다.")은 위 새 주석이 흡수했으므로 **지운다**(같은 말이 두 번 나오지 않게).

- [ ] **Step 2: 진단 패널을 아래 칸에 그린다**

ONE 위젯을 `editorHost`에 임베드하는 블록(=`_EMBEDDED[EDITOR_HOST_NAME] = ...`
과 그 뒤 `cmds.formLayout(editorHost, edit=True, attachForm=[...])`) **바로
뒤**에 삽입:

```python
    # 우하단: 기존 진단 패널을 **그대로** 그린다(설계 스펙 §3). 네이티브
    # Maya UI라 PySide6 위젯이 타는 두 단계(MQtUtil.findLayout ->
    # addWidgetToMayaLayout)를 타지 않는다 -- rightPane을 부모로 직접 넘기면
    # paneLayout의 두 번째 칸을 그대로 채우므로 formLayout attach도 필요
    # 없다.
    #
    # 단독 창(maroDiagPanel.show())은 그대로 남는다. 둘이 동시에 떠 있어도
    # 안전하다 -- buildUI가 만드는 컨트롤은 전부 무명이고 선택 상태는
    # 클로저에 있다(그 모듈의 주석이 이유를 적어 두었다).
    #
    # teardown()에 아무것도 추가하지 않는다. maroDiagPanel에는 scriptJob도
    # 타이머도 모듈 전역 가변 상태도 없고, 새로 고침은 사용자가 누를 때만
    # 일어난다 -- 멈출 것이 없어서 stop()이 없는 것이지, 빠뜨린 것이
    # 아니다(설계 스펙 §5).
    import maroDiagPanel
    maroDiagPanel.buildUI(parent=rightPane)
```

- [ ] **Step 3: 기존 테스트가 그대로 통과하는지 확인한다**

```bash
cmake --build out/build --config Release
```

```bash
ctest --test-dir out/build -C Release -R maya_main_window --output-on-failure
```

Expected: PASS. 이 테스트는 이름 상수와 스테이징/재진입만 보므로 레이아웃
변경에 영향받지 않아야 한다. **여기서 깨지면 레이아웃이 아니라 이름
계약을 건드린 것이다** -- 되돌아가서 확인하라.

- [ ] **Step 4: 수동 체크리스트 절을 쓴다**

`docs/maro-main-ui-manual-checklist.md`의 `## Maro 환경설정 창` 줄 **바로
앞**에 삽입:

```markdown
## MaroUI 안의 진단 패널 (2026-09-10)

인터랙티브 Maya 2026에서 `maro.mll`을 로드하고 Maro 메뉴 → "Maro 창 열기".

**왜 자동 테스트가 아닌가**: 배치 mayapy에서 `cmds.formLayout`/`paneLayout`/
`textScrollList`는 **예외를 던지지 않고** 조회가 전부 `False`를 돌려준다 --
컨트롤이 실제로 만들어지지 않는다. `maya.standalone.initialize()` 전에
offscreen QApplication을 세워도(이 세션이 QWidget·Viewport 2.0·ASan에서 통했던
그 수법) 결과는 같다. 실측으로 확인했다. 그래서 이 절은 사람이 봐야 한다.

- [ ] 창을 열면 **오른쪽이 위/아래로 나뉘어** 있다. 위는 기존 ONE/GSON 노드
      에디터, 아래는 진단 패널(심각도 드롭다운 + 목록 + 상세 + "새로 고침"/
      "적용" 버튼)이다.
- [ ] 아래 패널의 "새로 고침"을 누르면 목록이 채워진다(진단 기록이 하나도
      없으면 비어 있는 것이 정상이다 -- 그때는 아래 항목으로 기록을 만든다).
- [ ] 진단 기록을 하나 만든다: 이름 없는 `maroAxis`를 만들고
      `cmds.maroStartBridge()`를 시도하는 등 **알려진 실패를 일으킨 뒤**
      "새로 고침"을 누른다. 행이 나타나고, 선택하면 상세가 뜬다.
- [ ] 심각도 드롭다운을 `warn`/`error`로 바꾸면 목록이 필터링된다.
- [ ] **[필수] 단독 창과 동시에 띄워도 서로를 밟지 않는다**: 스크립트
      에디터에서 `cmds.maroDiagPanel()`로 단독 창을 띄운다. 두 패널에서
      **서로 다른 행**을 선택하고, 한쪽에서 "새로 고침"을 눌러도 다른 쪽의
      선택과 상세가 그대로인지 본다.
- [ ] **[필수 · go/no-go] 언로드 무크래시**: 진단 패널이 보이는 상태로
      MaroUI를 닫고, 이어서 `cmds.unloadPlugin("maro")`. 크래시가 없고
      Script Editor에 오류가 없다.
- [ ] **Phase 2/4 회귀 재확인**(레이아웃이 바뀌었으므로 필요하다): 뷰포트
      두 개가 여전히 좌우로 나란하고 각각 궤도/팬/줌이 되며, ONE/GSON 그리드가
      여전히 보이고 씬↔GSON 선택 동기화가 동작한다.

### 종합 판정

| 항목 | 판정 | 날짜/환경 | 비고 |
|---|---|---|---|
| 오른쪽이 상하로 나뉘고 아래에 진단 패널 | | | |
| 목록/상세/필터가 단독 창과 동일 | | | |
| 단독 창과 동시 표시 시 상호 간섭 없음 | | | |
| 언로드 무크래시 | | | |
| Phase 2/4 회귀 없음 | | | |
```

- [ ] **Step 5: 전체 스위트**

```bash
ctest --test-dir out/build -C Release --output-on-failure
```

Expected: 전부 PASS.

- [ ] **Step 6: 커밋**

```bash
git add python/maroMainWindow.py docs/maro-main-ui-manual-checklist.md && git commit -m "feat(ui): draw the diag panel in MaroUI's bottom-right pane"
```

---

## 자체 검토

**스펙 커버리지**

| 스펙 절 | 태스크 |
|---|---|
| §2 배치(오른쪽 칸을 horizontal2로) | Task 2 Step 1 |
| §3 `buildUI(parent=None)`, MQtUtil 경로 안 탐 | Task 1, Task 2 Step 2 |
| §4 두 인스턴스 공존(이미 안전) | 코드 변경 없음. Task 2 Step 4의 필수 항목이 사람으로 확인 |
| §5 teardown에 안 넣음 + 이유를 주석으로 | Task 2 Step 2의 주석 |
| §6 테스트 전략 | Task 1(계약 2건) + Task 2 Step 4(수동 절) |
| §7 범위 밖 | 어느 태스크도 메뉴 항목·자동 새로고침·로그 스트림을 건드리지 않는다 |

**스펙과 달라진 것 1건**: 스펙 §8이 새 이름 상수 `DIAG_HOST_NAME`을 언급했지만
**만들지 않는다**. `EDITOR_HOST_NAME`이 이름을 갖는 이유는 임베드가
`cmds.control(editorHost, query=True, fullPathName=True)`로 그 레이아웃을
찾아야 하기 때문인데, 진단 패널은 네이티브 UI라 그 조회를 하지 않는다.
`rightPane`을 부모로 직접 넘기면 되므로 쓰이지 않을 상수를 만드는 셈이 된다.
C++ 계약이 아니라는 스펙의 판단은 그대로 유효하다.

**타입 일관성**: `buildUI(parent=None) -> str`(Task 1) -> Task 2가 반환값을
쓰지 않고 부모만 넘긴다. `rightPane`은 `cmds.paneLayout`이 돌려준 문자열이며
`cmds.formLayout(parent=...)`이 받는 형태와 같다.

**함정 점검**: 이 계획에는 RED로 시작하는 태스크가 하나뿐이다(Task 1).
Task 2는 배치에서 검증 불가능하므로 **가짜 GREEN을 만들지 않는 것**이
중요하다 -- `buildUI()`를 배치에서 불러 "에러 안 났으니 통과"로 적는 테스트를
쓰지 마라. 그건 통과하면서 아무것도 증명하지 않는다(전역 제약 마지막 항목).

## 알려진 부수 효과 (리뷰에서 확인할 것)

- 노드 에디터가 차지하던 오른쪽 절반이 **위쪽 절반으로 줄어든다**. 의도한
  것이며, 좁아서 못 쓸 정도인지는 Task 2 Step 4의 회귀 항목이 확인한다.
- `maroMainWindow.buildUI()`가 이제 `maroDiagPanel`을 import한다. 함수 안에서
  import하는 기존 관례(`maroRosProxy`/`maroObjectNodeEditor`/`maroTechDiag`와
  같은 이유)를 따른다.
- 진단 패널이 열릴 때 `buildUI()` 끝의 `refresh()`가 `maroDiagPanelRows`를
  한 번 부른다. MaroUI를 열 때마다 진단 커맨드가 한 번 더 불리는 셈이지만,
  단독 창을 열 때 이미 일어나던 것과 같은 호출이다.
