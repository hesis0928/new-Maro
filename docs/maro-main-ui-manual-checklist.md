# Maro 메인 창 — 수동 확인 목록 (Phase 0-1 스파이크)

`mayapy` 배치 모드에는 UI가 없다. 자동 테스트(`tests/maya/test_main_window.py`,
ctest의 `maya_main_window`)가 확인하는 것은 **커맨드가 등록되고, 부르면
플러그인 디렉터리를 찾아 `maroMainWindow` 모듈을 import하는 데까지 성공하고,
C++/Python이 공유하는 UI 이름 두 개가 일치하고, 배치 모드에서 `buildUI()`가
프로세스를 죽이는 대신 예외를 낸다**는 것뿐이다. 뷰포트가 실제로 그려지는지,
Qt 버튼이 실제로 눌리는지, 창을 띄운 채 언로드해도 Maya가 살아남는지는
원리적으로 배치 모드에서 확인할 수 없다(실측: 배치 mayapy에는 `QApplication`이
아니라 `QGuiApplication`만 있어 `QWidget`을 하나라도 만들면 프로세스가 abort
한다. `workspaceControl`/`modelPanel`은 예외 없이 `False`를 돌려주고 아무
것도 만들지 않는다).

**아래 네 항목은 이 스파이크의 합격 기준 그 자체다.** 하나라도 실패하면 이
태스크는 완료가 아니라 BLOCKED이고, 대안(설계 스펙 §4.3의 Option C — 커스텀
렌더러)을 검토해야 한다. 이 플랜의 나머지 로드맵 전체가 여기에 달려 있다.

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

## 1. `modelPanel`이 실제 뷰포트로 동작하는가

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

## 2. PySide6 버튼이 같은 창 안에 살아 있는가

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

## 3. 창을 띄운 채 언로드 — **이 스파이크의 진짜 go/no-go 기준**

- [ ] 창이 열려 있는 상태에서 다음을 실행한다:

      ```python
      cmds.unloadPlugin("maro")
      ```

- [ ] **Maya가 크래시하지 않는다.** (실패하면 사용자의 미저장 작업이 함께
      사라지는 종류의 결함이다 — `maroDiagPanel`의 체크리스트가 같은 항목을
      가장 중요한 것으로 꼽는 이유와 같다.)
- [ ] 창이 닫힌다(`uninitializePlugin`이 `maroMainWindowControl`을 닫고, 남아
      있으면 `maroMainWindowViewport` 패널까지 지운다).
- [ ] 언로드 직후 아래가 전부 `False`/빈 목록이다:

      ```python
      cmds.workspaceControl("maroMainWindowControl", exists=True)   # False
      [p for p in cmds.getPanel(type="modelPanel") if p == "maroMainWindowViewport"]  # []
      ```

- [ ] 다시 로드하고 다시 열어도 정상이다(패널 이름 충돌이 없다):

      ```python
      cmds.loadPlugin(r"...\maro.mll")
      cmds.maroMainWindow()
      ```

      두 번째로 뜬 창에서도 1번과 2번 항목이 그대로 성립한다.

## 4. `workspaceControl` 통합이 `maroDiagPanel`과 동등한가

- [ ] **도킹** — 창을 Maya 창 가장자리로 끌어 도킹되는지, 다시 떼어내
      플로팅으로 돌아오는지 확인한다. 도킹된 상태에서도 뷰포트 조작과 버튼
      클릭이 그대로 동작한다(도킹은 `-uiScript`로 UI를 다시 짓게 만들므로,
      `buildUI()`가 두 번째로 불려도 패널 이름 충돌 없이 성립하는지가 실제로
      확인되는 지점이다 — `_deleteStalePanel()`이 그것을 맡는다).
- [ ] **재시작 시 복원** — 도킹한 상태로 Maya를 종료하고 다시 켠다. 창이 그
      자리에 복원되고, 플러그인이 아직 로드되기 전이라도 오류 없이 뜬다
      (`-requiredPlugin "maro"`가 처리한다).
- [ ] **두 번째 뷰포트 여지 확인**(설계 스펙 §4.3의 Phase 2 준비) — 창이 열린
      상태에서 아래를 실행해 같은 폼레이아웃 안에 두 번째 `modelPanel`을
      만들어도 첫 번째가 깨지지 않는지 본다. 확인 후 지운다. 이것이
      실패하면 Phase 2(뷰포트 2개)를 다시 설계해야 한다는 뜻이므로, 실패해도
      이 태스크 자체는 BLOCKED가 아니지만 반드시 보고에 남긴다.

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

확인한 사람이 날짜와 결과를 여기에 적는다. 네 절이 모두 통과해야 Task 2가
완료된 것으로 본다.

| 절 | 결과 | 날짜 / 확인자 | 비고 |
|---|---|---|---|
| 1. modelPanel 뷰포트 | 미실행 | | |
| 2. PySide6 버튼 | 미실행 | | |
| 3. 언로드 크래시 없음 | 미실행 | | |
| 4. workspaceControl 통합 | 미실행 | | |
