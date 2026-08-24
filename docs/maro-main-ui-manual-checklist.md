# Maro 메인 창 — 수동 확인 목록 (Phase 0-1 스파이크)

`mayapy` 배치 모드에는 UI가 없다. 자동 테스트(`tests/maya/test_main_window.py`,
`tests/maya/test_main_menu.py`)가 확인하는 것은 **커맨드가 등록되고, 부르면
플러그인 디렉터리를 찾아 모듈을 import하는 데까지 성공하고, C++/Python이
공유하는 UI 이름들이 (Python 리터럴 값 그리고 C++ 소스 문자열 둘 다) 서로
일치하고, 배치 모드에서 `buildUI()`가 프로세스를 죽이는 대신 예외를 낸다**는
것뿐이다. 뷰포트가 실제로 그려지는지, Qt 버튼이 실제로 눌리는지, 창을 띄운 채
언로드해도 Maya가 살아남는지, 메뉴가 실제로 멱등한지는 원리적으로 배치
모드에서 확인할 수 없다(실측: 배치 mayapy에는 `QApplication`이 아니라
`QGuiApplication`만 있어 `QWidget`을 하나라도 만들면 프로세스가 abort한다.
`workspaceControl`/`modelPanel`/`menu`는 예외 없이 `False`를 돌려주고 아무
것도 만들지 않는다).

**이 문서의 절은 두 종류다.** 표시를 잘 구분해서 읽는다:

- **[필수 · go/no-go]** — 실패하면 그 태스크는 완료가 아니라 BLOCKED다.
  §1/§2/§3은 이 스파이크 전체(Phase 0-1)의 존재 이유 그 자체이므로, 이 셋
  중 하나라도 실패하면 이 플랜의 나머지 로드맵 전체를 재검토해야 한다(대안:
  설계 스펙 §4.3의 Option C — 커스텀 렌더러). §3-1은 Task 3(메뉴)만의
  go/no-go다 — 실패해도 §1-3이 이미 통과했다면 로드맵 전체를 막지는 않지만,
  Task 3 자체는 완료로 볼 수 없다.
- **[정보성 · 기록만]** — 실패해도 BLOCKED가 아니다. 다음 단계 설계에 참고할
  사실을 모으는 항목이다. §4의 도킹/재시작 복원은 필수고, 두 번째 뷰포트
  여지 확인만 정보성이다 — 각 항목에 다시 표시해 둔다.

## 준비

1. `maro.mll`이 놓인 빌드 출력 디렉터리를 PATH에 넣은 상태로 인터랙티브
   Maya 2026을 띄운다(README의 요구사항과 같다):
   `C:\Users\ckd30\Projects\Maya_Ros_Sim\out\build\src\maro_plugin\Release`
2. 플러그인을 로드한다. 스크립트 에디터(Python 탭)에서:

   ```python
   import maya.cmds as cmds
   cmds.loadPlugin(r"C:\Users\ckd30\Projects\Maya_Ros_Sim\out\build\src\maro_plugin\Release\maro.mll")
   ```

3. 씬에 눈에 보이는 것을 하나 만들어 둔다(뷰포트가 "정말 그리고 있는지"를
   빈 그리드만으로 판정하지 않기 위해서다):

   ```python
   cmds.file(new=True, force=True)
   cmds.polyCube()
   ```

4. 창을 연다:

   ```python
   cmds.maroMainWindow()
   ```

   "Maro"라는 이름의 플로팅 `workspaceControl`이 떠야 한다(초기 900x600).

---

## 1. `modelPanel`이 실제 뷰포트로 동작하는가 — **[필수 · go/no-go]**

- [ ] 창 안에 3D 뷰포트가 보이고, 3번 단계에서 만든 큐브가 그 안에 그려진다.
      (그리드만 보이고 큐브가 없으면 카메라가 엉뚱한 곳을 보고 있는 것일 수
      있다 — 뷰포트에 마우스를 올린 채 `f`를 눌러 프레임해 본다.)
- [ ] 뷰포트 안에서 카메라 조작 세 가지가 전부 된다:
      **궤도**(Alt+좌클릭 드래그), **팬**(Alt+가운데클릭 드래그),
      **줌**(Alt+우클릭 드래그 또는 휠).
- [ ] 뷰포트 위쪽에 패널 메뉴바(View/Shading/Lighting/...)와 아이콘 툴바가
      **보이지 않는다**(`-menuBarVisible off` + `-barLayout` frameLayout
      접기가 의도대로 먹었는지 — 아이콘 바가 접힌 얇은 띠로 남아 있으면
      그것은 합격이다. 아이콘들이 그대로 보이면 불합격이고,
      `maroMainWindow.py`의 `_hideViewportChrome()`을 고쳐야 한다).
- [ ] 씬에서 큐브를 지우면 뷰포트가 그것을 즉시 반영한다(뷰포트가 살아 있는
      진짜 패널이지, 한 장 찍힌 그림이 아니라는 확인):

      ```python
      cmds.delete("pCube1")
      ```

**만약 이 절이 실패하면(뷰포트가 아예 안 그려짐)**: 바로 BLOCKED로 결론
내리기 전에, `modelPanel`을 지금처럼 `formLayout`에 직접 두는 대신 Maya의
다른 패널들처럼 `paneLayout`으로 한 번 감싸 보는 것을 첫 번째 대안으로
시도한다(설계 스펙 §4.3의 Option C — 커스텀 렌더러 — 로 가는 것보다 훨씬
작은 후퇴다).

## 2. PySide6 버튼이 같은 창 안에 살아 있는가 — **[필수 · go/no-go]**

- [ ] 뷰포트 위쪽 좁은 띠에 "테스트"라고 쓰인 버튼이 보인다.
- [ ] 그 버튼의 생김새가 Maya의 다른 네이티브 버튼과 이질감이 없다(색/모서리/
      글꼴). 다르게 보인다면 전역 스타일 상속이 깨진 것이다 —
      `setStyleSheet()`를 아무도 부르지 않는 것이 그 전제였다(설계 스펙 §4.2).
- [ ] 버튼을 누르면 스크립트 에디터 출력에
      `Maro main window: button clicked` 가 찍힌다.
- [ ] 창 크기를 바꾼다(모서리 드래그). 버튼은 위쪽에 얇게 남고 뷰포트가
      나머지를 전부 차지하도록 같이 늘어난다 — 즉 네이티브 `formLayout`이
      끼워 넣은 Qt 위젯을 다른 네이티브 컨트롤과 똑같이 다룬다.
- [ ] 창을 열어 둔 채 1분쯤 다른 작업을 하고(노드 몇 개 만들고 지우고)
      다시 버튼을 누른다 — 여전히 찍힌다(파이썬 GC가 임베드된 위젯을
      걷어가지 않는다는 확인).
- [ ] **`show()`의 복원 분기** — 창을 닫지 않은 채(플로팅 상태 그대로)
      다시 실행한다:

      ```python
      cmds.maroMainWindow()
      ```

      기존 창이 그대로 앞으로 올라와야 한다(두 번째 `modelPanel`/버튼이
      새로 생기거나 에러가 나면 안 된다). 배치 테스트는 이 분기를
      절대 타지 않으므로(배치의 `workspaceControl`은 매번 아무것도 안
      만들어서 `exists=True`가 늘 `False`다) 여기서만 확인 가능하다.

## 3. 창을 띄운 채 언로드 — **[필수 · go/no-go, 이 스파이크의 진짜 기준]**

**플로팅 상태에서 한 번, §4에서 도킹한 뒤 다시 한 번 — 총 두 번 실행한다.**
도킹된 `workspaceControl`은 저장된 워크스페이스가 소유하므로, 플러그인
코드가 사라진 뒤에도 UI 참조를 붙들고 있을 위험이 플로팅보다 크다. 두
상태 모두에서 통과해야 이 절이 합격이다(아래 결과표에 두 줄로 각각 기록).

- [ ] 창이 열려 있는 상태에서 다음을 실행한다:

      ```python
      cmds.unloadPlugin("maro")
      ```

- [ ] **Maya가 크래시하지 않는다.** (실패하면 사용자의 미저장 작업이 함께
      사라지는 종류의 결함이다 — `maroDiagPanel`의 체크리스트가 같은 항목을
      가장 중요한 것으로 꼽는 이유와 같다.)
- [ ] **스크립트 에디터에 트레이스백/에러가 찍히지 않는다.** 크래시하지
      않았어도 언로드 도중 에러가 조용히 삼켜졌다면 그것은 진짜 합격이
      아니다 — 나중에 크래시로 이어질 수 있는 상태다(`maroDiagPanel`
      체크리스트와 같은 습관).
- [ ] 창이 닫힌다(`uninitializePlugin`이 `maroMainWindowControl`을 닫고, 남아
      있으면 `maroMainWindowViewport` 패널까지 지운다).
- [ ] 언로드 직후 아래가 전부 `False`/빈 목록이다:

      ```python
      cmds.workspaceControl("maroMainWindowControl", exists=True)   # False
      [p for p in cmds.getPanel(type="modelPanel") if p == "maroMainWindowViewport"]  # []
      ```

- [ ] **버그 시 복구**: `buildUI()`가 도중에 에러를 내면(예: 창을 다시 열었을
      때 뷰포트나 버튼 중 하나만 보임) 다음 번 `maroMainWindow()` 호출은
      기존 컨트롤이 "이미 있다"고 보고 복원 분기를 타 버려서 `buildUI()`가
      다시는 안 돈다 — 절반만 만들어진 창이 스스로 고쳐지지 않는다. 다시
      열기 전에 아래로 지우고 시작한다:

      ```python
      cmds.deleteUI("maroMainWindowControl", control=True)
      ```

- [ ] 다시 로드하고 다시 열어도 정상이다(패널 이름 충돌이 없다):

      ```python
      cmds.loadPlugin(r"...\maro.mll")
      cmds.maroMainWindow()
      ```

      두 번째로 뜬 창에서도 1번과 2번 항목이 그대로 성립한다.

## 3-1. Maro 메뉴 (Task 3) — **[필수 · go/no-go, Task 3 자체의 완료 기준]**

`tests/maya/test_main_menu.py`는 mayapy 배치 모드에서 `cmds.menu(...)`가
아무것도 만들지 않고 조용히 `False`만 돌려준다는 것을 확인했을 뿐이다 —
`python/maroMenu.py`의 `build()`가 실제로 멱등한지(메뉴가 이미 있는 상태에서
두 번째로 불려도 아무 일도 안 하는지)는 대화형 Maya에서만 확인 가능하다.

- [ ] Maya 상단 메뉴바에 "Maro" 메뉴가 정확히 하나만 보인다(중복 없음).
- [ ] "Maro 창 열기" 클릭 → `maroMainWindow`가 열린다. "준비 중" 항목 2개는
      비활성(회색, 클릭 안 됨) 상태다.
- [ ] **진짜 멱등성 확인** — 메뉴가 이미 떠 있는 상태에서 커맨드를 직접 두
      번 연달아 호출한다:

      ```python
      cmds.maroBuildMenu()
      cmds.maroBuildMenu()
      ```

      메뉴바에 "Maro"가 여전히 **정확히 하나**만 있어야 한다. (참고:
      `loadPlugin`을 이미 로드된 플러그인에 다시 호출해도 `initializePlugin`이
      재실행되지 않고, `unloadPlugin` 후 `loadPlugin`은 메뉴가 지워진 뒤라
      매번 생성 분기만 타므로, 둘 다 `build()`의 멱등성 가드
      [`if cmds.menu(MENU_NAME, exists=True): return`] 자체는 검증하지
      못한다 — 위처럼 메뉴가 존재하는 채로 직접 호출해야 한다.)
- [ ] `unloadPlugin` 후 "Maro" 메뉴가 메뉴바에서 사라진다.

## 4. `workspaceControl` 통합이 `maroDiagPanel`과 동등한가

- [ ] **[필수]** **도킹** — 창을 Maya 창 가장자리로 끌어 도킹되는지, 다시
      떼어내 플로팅으로 돌아오는지 확인한다. 도킹된 상태에서도 뷰포트 조작과
      버튼 클릭이 그대로 동작한다(도킹은 `-uiScript`로 UI를 다시 짓게
      만드므로, `buildUI()`가 두 번째로 불려도 패널 이름 충돌 없이 성립하는지가
      실제로 확인되는 지점이다 — `_deleteStalePanel()`이 그것을 맡는다).
      **도킹한 채로 §3의 언로드 테스트를 한 번 더 실행한다** — §3의 결과표
      "도킹" 행이 바로 이 실행 결과다.
      복원 분기도 도킹 상태에서 한 번 더 확인한다: 도킹된 채로
      `cmds.maroMainWindow()`를 다시 호출해 기존 창이 정상적으로
      앞으로 올라오는지 본다(§2의 플로팅 상태 확인과 짝).
- [ ] **[필수]** **재시작 시 복원** — 도킹한 상태로 Maya를 종료하고 다시
      켠다. 창이 그 자리에 복원되고, 플러그인이 아직 로드되기 전이라도 오류
      없이 뜬다(`-requiredPlugin "maro"`가 처리한다). **이 세션에도 Maro
      메뉴가 보이는지 함께 확인한다** — `initializePlugin`이 메뉴 생성을
      `executeCommandOnIdle`로 미뤄 두므로(최종 리뷰 I5), 플러그인이
      Maya UI 구성 전에 오토로드되는 이 상황에서 메뉴가 실제로 나타나는지
      확인하는 유일한 지점이다. 안 보이면 이 항목은 실패로 기록한다.
- [ ] **[정보성 · 실패해도 비차단]** **두 번째 뷰포트 여지 확인**(설계 스펙
      §4.3의 Phase 2 준비) — 창이 열린 상태에서 아래를 실행해 같은
      폼레이아웃 안에 두 번째 `modelPanel`을 만들어도 첫 번째가 깨지지
      않는지 본다. **주의**: 아래 코드는 새 패널의 위치를 지정하지 않으므로
      기본적으로 왼쪽 위에 생겨 첫 번째 뷰포트와 겹친다 — 겹치는 것 자체는
      실패가 아니다, 확인할 것은 오직 "첫 번째 뷰포트가 여전히 그려지고
      조작되는가"뿐이다. 실패하면 Phase 2(뷰포트 2개)를 다시 설계해야
      한다는 뜻이지만, 이 태스크 자체를 BLOCKED로 만들지는 않는다 — 반드시
      보고에는 남긴다.

      ```python
      import maya.cmds as cmds
      panelControl = cmds.modelPanel("maroMainWindowViewport", q=True, control=True)
      form = cmds.control(panelControl, q=True, parent=True)
      probe = cmds.modelPanel("maroProbeViewport", parent=form)
      # 첫 뷰포트가 여전히 그리고 조작되는지 눈으로 확인한 뒤:
      cmds.deleteUI("maroProbeViewport", panel=True)
      ```

---

## 결과 기록

확인한 사람이 날짜와 결과를 여기에 적는다. **[필수]** 표시된 모든 행이
통과해야 Phase 0-1이 완료된 것으로 본다(§4의 "두 번째 뷰포트 여지 확인"은
정보성이라 이 판정에 포함되지 않는다). Maya 빌드 번호도 함께 기록한다.

| 절 | 필수 여부 | 결과 | 날짜 / 확인자 / Maya 빌드 | 비고 |
|---|---|---|---|---|
| 1. modelPanel 뷰포트 | 필수 | 미실행 | | |
| 2. PySide6 버튼 (복원 분기 포함) | 필수 | 미실행 | | |
| 3. 언로드 크래시 없음 — 플로팅 | 필수 | 미실행 | | |
| 3. 언로드 크래시 없음 — 도킹 | 필수 | 미실행 | | |
| 3-1. Maro 메뉴 (멱등성 포함) | 필수 (Task 3) | 미실행 | | |
| 4. 도킹/재시작 복원 (+메뉴 표시) | 필수 | 미실행 | | |
| 4. 두 번째 뷰포트 여지 확인 | 정보성 | 미실행 | | 겹침 여부도 기록 |
