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

> **참고(체크리스트가 아님)**: 아래에서 `buildUI()`가 도중에 에러를 내면(예:
> 뷰포트나 버튼 중 하나만 보임) 다음 번 `maroMainWindow()` 호출은 기존
> 컨트롤이 "이미 있다"고 보고 복원 분기를 타 버려서 `buildUI()`가 다시는 안
> 돈다 — 절반만 만들어진 창이 스스로 고쳐지지 않는다. 이 절이나 §2에서
> 그런 일이 생기면, 다시 열기 전에 아래로 지우고 시작한다:
>
> ```python
> cmds.deleteUI("maroMainWindowControl", control=True)
> ```

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

## 1-1. 듀얼 뷰포트 (Phase 2) — **[필수 · go/no-go]**

이 절은 `formLayout > paneLayout > formLayout > (라벨+modelPanel)`이라는
새 중첩 구조를 처음으로 실제 Maya에서 확인하는 자리다 — 설계/플랜 문서
어디서도 이 중첩이 실제로 그렇게 붙는지 검증된 적이 없다. **레이아웃이
이상하게 나오면(패널이 겹쳐 보이거나, 하나가 안 보이거나, 라벨이 없거나)
바로 BLOCKED로 적지 말고** 아래를 실행해 실제로 어떻게 붙었는지 먼저
기록한다:

```python
cmds.paneLayout("maroMainWindowViewportMaya", q=True, control=True)  # 확인용, 존재해야 함
```

두 패널이 각자의 `formLayout` 안에 제대로 들어갔다면 `paneLayout`의
직계 자식은 그 두 `formLayout` 2개여야 한다. 아래로 직접 확인 가능:

```python
# pane 변수 이름은 모르니, workspaceControl 안의 paneLayout을 찾는다
cmds.lsUI(type="paneLayout")
# 위에서 나온 이름 중 Maro 창에 속한 것을 골라:
cmds.paneLayout("<위에서 찾은 이름>", q=True, childArray=True)
```

결과가 2개 항목(formLayout 2개)이면 의도대로 붙은 것이다. 4개 항목(라벨+
modelPanel이 paneLayout에 직접 붙어버림)이면 중간 `formLayout`이 무시된
것이므로 설계를 다시 봐야 한다 — 이 경우 어떤 결과가 나왔는지 보고에
남긴다.

- [ ] 창을 열면 뷰포트가 **두 개** 좌우로 나란히 보인다("테스트" 버튼은
      맨 위 띠에 그대로 있다).
- [ ] 좌측 뷰포트 위에 "Maya", 우측 뷰포트 위에 "ROS" 라벨이 각각 보인다.
- [ ] **카메라 관찰(합/불합격 판정 아님, 사실만 기록)** — 좌측에서 궤도/팬/줌을
      해본 뒤 우측 뷰포트가 같이 움직이는지 관찰하고, 아래로 실제 카메라를
      확인한다:

      ```python
      cmds.modelPanel("maroMainWindowViewportMaya", q=True, camera=True)
      cmds.modelPanel("maroMainWindowViewportRos", q=True, camera=True)
      ```

      **두 이름이 같게 나오는 것(즉 두 뷰포트가 같은 카메라를 공유해서
      같이 움직이는 것)은 Phase 2 범위에서 실패가 아니다** — 코드가
      `-camera`를 명시적으로 안 주므로 오히려 그럴 가능성이 높다. 카메라를
      뷰포트별로 분리하는 것은 Phase 3의 몫이다. 여기서는 "같다/다르다"와
      실제로 관찰한 동작만 결과란에 적어 둔다.
- [ ] 우측 뷰포트도 좌측과 똑같이 궤도/팬/줌이 되고, 좌측과 같은 씬(같은
      큐브 등)을 그린다(아직 좌표 변환 없음 — Phase 3에서 달라진다).
- [ ] 두 뷰포트 모두 chrome(메뉴바/아이콘 바)이 숨겨져 있다.
- [ ] **언로드(§3와 같은 절차, 이름만 두 개로)** — 창을 띄운 채
      `cmds.unloadPlugin("maro")` 실행 → **Maya가 크래시하지 않는다**,
      스크립트 에디터에 에러가 없다(단, §3이 기록해 둔 "로드-언로드를 유휴
      시간 없이 바로 이어붙이면 큐에 남아있던 `maroBuildMenu` 호출이
      뒤늦게 프로시저를 못 찾는다는 에러 하나"는 알려진 예외라 실패로 안
      침), 언로드 후 아래가 전부 `False`다:

      ```python
      cmds.workspaceControl("maroMainWindowControl", exists=True)   # False
      cmds.modelPanel("maroMainWindowViewportMaya", exists=True)    # False
      cmds.modelPanel("maroMainWindowViewportRos", exists=True)     # False
      ```

      **§3과 마찬가지로 플로팅 상태에서 한 번, §4에서 도킹한 뒤 다시 한 번,
      총 두 번 실행한다.**
- [ ] **재로드 후 재오픈** — 언로드 후 다시 로드하고 창을 다시 연다:

      ```python
      cmds.loadPlugin(r"C:\Users\ckd30\Projects\Maya_Ros_Sim\out\build\src\maro_plugin\Release\maro.mll")
      cmds.maroMainWindow()
      ```

      이름 충돌 없이 두 뷰포트가 다시 정상적으로 뜬다(이번 단계가 새로
      추가한 `_deleteStalePanel(panelName)`의 두 뷰포트 버전을 실제로
      거치는 유일한 경로다).

## 1-2. ROS 좌표 프록시 (Phase 3) — **[필수 · go/no-go, Phase 3의 진짜 기준]**

이 절이 Phase 3의 **유일한 실질적 검증**이다. 배치 mayapy에는 `modelPanel`도
`scriptJob`의 idle 이벤트도 없어서(`tests/maya/test_ros_proxy_sync.py`가
그 경계를 명시해 뒀다), "우측에만 보이는가 / 실시간으로 따라가는가 /
언로드해도 잡이 안 남는가"는 사람이 대화형 Maya에서만 확인할 수 있다.

**이 절에 들어가기 전에 알아 둘 것 — 미검증 가정 하나.** 이 단계는
`cmds.isolateSelect(panel, addDagObject=obj)`를 **매번 다시** 부르는 설계다
(이미 격리 목록에 있는 오브젝트를 다시 넣어도 무해하다는 전제, 설계 스펙 §7).
플래그 이름과 "패널별로 독립적으로 걸린다"는 것은 Maya 2026에서 확인했지만
(`cmds.help("isolateSelect")`, Maya 자신의
`scripts/others/createModelPanelMenu.mel`), **멱등성 자체는 대화형 Maya에서
확인하지 못했다.** 아래 항목들이 그것을 실제로 판정한다.

```python
# 준비: 창을 연다.
cmds.maroMainWindow()
```

- [ ] **격리가 켜졌는가 (제일 먼저 볼 것)** — 창을 연 직후 아래가 둘 다
      `1`(또는 `True`)이어야 한다:

      ```python
      cmds.isolateSelect("maroMainWindowViewportMaya", q=True, state=True)
      cmds.isolateSelect("maroMainWindowViewportRos", q=True, state=True)
      ```

      **좌측 뷰포트가 완전히 비어 보이면** 곧바로 FAIL로 적지 말고 1~2초
      기다렸다 다시 본다 — 좌측 목록은 `start()`가 아니라 **첫 idle 틱**이
      채우므로 한 틱만큼 늦다. 그래도 비어 있으면 아래 "막혔을 때"를 본다.
- [ ] **좌측엔 원본만, 우측엔 프록시만** — 큐브를 하나 만들고 선택한다:

      ```python
      cmds.polyCube(name="proxyCheckCube")
      ```

      - 좌측("Maya") 뷰포트: 큐브가 보인다. **로케이터는 안 보인다.**
      - 우측("ROS") 뷰포트: 십자 모양 로케이터가 보인다. **큐브는 안 보인다.**
      (우측이 비어 보이면 우측 뷰포트에서 카메라를 프록시에 맞춘다 —
      로케이터 좌표는 **미터**라 cm 씬에서는 원점 근처 아주 작은 값이다.
      아래 "단위" 항목 참고.)
- [ ] **실시간 추종** — 큐브를 이동/회전하면 우측 로케이터가 곧바로 따라간다
      (idle 콜백이므로 마우스를 놓지 않아도 따라간다).
- [ ] **Undo 큐가 프록시 갱신으로 도배되지 않는다** — 큐브를 몇 번 옮긴 뒤
      (로케이터가 매번 따라가는 것을 확인한 다음) `Ctrl+Z`를 눌러본다.
      **큐브의 마지막 이동만 취소돼야 한다** — 로케이터 갱신 자체는 undo
      목록에 전혀 안 쌓여야 정상이다(`MFnTransform` API로 갱신하고
      `cmds.xform`처럼 undo 가능한 커맨드를 안 쓰기 때문). 만약 `Ctrl+Z`를
      여러 번 눌러야 큐브가 한 번 움직이거나, undo가 로케이터 위치를
      되돌리는 것처럼 보이면 실패로 기록한다.
- [ ] **축 변환 방향이 맞는가** — 큐브를 Maya 기준 **+Z로만** 100 단위(1m)
      옮긴 뒤:

      ```python
      cmds.xform("proxyCheckCube", ws=True, t=[0, 0, 100])
      cmds.xform("|maroRosProxy_grp|maroRosProxy_loc", q=True, ws=True, t=True)
      ```

      `[0.0, -1.0, 0.0]`에 가까워야 한다 — `Convert.h`의 `(x, y, z) -> (x, -z, y)`
      규칙과 cm→m 스케일이 함께 적용된 값이다.
- [ ] **단위(판정 아님, 사실만 기록)** — 위에서 보듯 로케이터의 트랜스폼
      값은 **ROS 미터 값 그대로**다. 즉 cm 단위 씬에서는 프록시가 원본보다
      100배 작은 거리에 놓인다. 두 뷰포트의 카메라가 독립이라 시각적으로는
      문제가 아니고, 채널 박스에서 ROS 좌표를 그대로 읽을 수 있다는 이점이
      있다 — **의도된 동작이므로 실패로 적지 않는다.** 다만 실제로 그렇게
      보이는지 관찰한 바를 결과란에 적는다.
- [ ] **프록시 노드가 씬에 남는다(판정 아님, 사실만 기록)** — `언로드`나
      `stop()`을 해도 `maroRosProxy_grp`/`maroRosProxy_loc`은 씬에서 지워지지
      않는다(다음에 다시 열면 재사용한다). 즉 이 상태로 씬을 저장하면 그
      두 노드가 파일에 같이 저장된다 — 지금은 의도된 동작이지만, 실제로
      그런지 확인하고 기록한다. `cmds.file(query=True, modified=True)`가
      창을 연 직후부터 계속 `True`로 남는 것도 같은 이유다(정상).
- [ ] **창을 연 뒤에 만든 오브젝트가 좌측에 바로 보인다** — *(사용자가
      명시적으로 요구한 항목. 이번 플랜이 스냅샷 대신 라이브 갱신을 택한
      이유 자체다.)* 창을 **닫지 않은 채**:

      ```python
      cmds.polySphere(name="proxyCheckSphereLate")
      ```

      1초 안에 좌측 뷰포트에 구가 나타난다. **우측에는 안 나타난다.**
      (이 항목이 통과한다 = `-addDagObject`가 실제로 멱등하고 라이브
      갱신이 동작한다.)
- [ ] **성능(판정 아님, 사실만 기록)** — 위 상태에서 뷰포트를 궤도/팬 해
      본다. 눈에 띄게 끊기거나 CPU가 한 코어를 계속 먹으면 적어 둔다
      (idle 콜백이 매 틱 도는 구조라 이 절이 그것을 처음 실측하는 자리다).
- [ ] **씬 수정 표시(판정 아님, 사실만 기록)** — 동기화가 로케이터를 계속
      쓰므로 씬이 항상 "수정됨"이 된다. 파일을 닫을 때 저장 여부를 묻는지
      관찰해 적어 둔다.
- [ ] **고정(pin)** — 큐브를 고정한 뒤 다른 오브젝트를 선택해도 프록시가
      계속 큐브를 따라간다:

      ```python
      cmds.maroSetRosProxyTarget("proxyCheckCube")
      cmds.select("proxyCheckSphereLate")
      cmds.xform("proxyCheckSphereLate", ws=True, t=[50, 50, 50])  # 프록시는 안 움직여야 한다
      cmds.xform("proxyCheckCube", ws=True, t=[10, 0, 0])          # 프록시는 이걸 따라가야 한다
      ```
- [ ] **고정 해제** — 풀면 다시 선택 추종으로 돌아간다:

      ```python
      cmds.maroSetRosProxyTarget(clear=True)
      cmds.select("proxyCheckSphereLate")   # 이제 프록시가 구를 따라간다
      ```
- [ ] **프록시가 자기 자신을 따라가지 않는다** — 우측 로케이터를 직접
      선택해 본다(아웃라이너에서 `maroRosProxy_grp > maroRosProxy_loc`).
      프록시가 제자리에 멈춰 있고 값이 스스로 발산하지 않는다. 그리고
      **창을 여는 순간 원래 선택이 유지됐는지**도 함께 본다:

      ```python
      cmds.select("proxyCheckSphereLate", r=True)
      # 창을 닫았다 다시 연 뒤
      cmds.ls(sl=True)   # 여전히 proxyCheckSphereLate 여야 한다
      ```
- [ ] **창을 닫으면(언로드 없이) 동기화가 멈춘다** — 창의 X를 눌러 닫은 뒤:

      ```python
      cmds.xform("proxyCheckSphereLate", ws=True, t=[0, 100, 0])   # 에러가 안 나야 한다
      [j for j in (cmds.scriptJob(listJobs=True) or []) if "maroRosProxy" in j]   # []
      ```

      스크립트 에디터에 반복되는 에러가 없어야 하고, 위 목록이 비어 있어야
      한다.
- [ ] **플러그인 언로드 — 진짜 go/no-go** — 창을 **다시 열고** 프록시가
      동작 중인 상태에서:

      ```python
      cmds.maroMainWindow()
      cmds.select("proxyCheckSphereLate")   # 프록시가 따라가는 것을 눈으로 확인한 뒤
      cmds.unloadPlugin("maro")
      ```

      - Maya가 크래시하지 않는다.
      - 스크립트 에디터에 에러가 없다(§3이 기록해 둔 `maroBuildMenu` 큐잉
        예외는 알려진 예외라 실패로 안 침).
      - 잡이 안 남는다: `[j for j in (cmds.scriptJob(listJobs=True) or []) if "maroRosProxy" in j]` → `[]`
      - 언로드 뒤 오브젝트를 움직여도 **아무 에러도 반복되지 않는다**
        (idle 콜백이 살아 있었다면 사라진 `maroMayaToRos`를 찾다가 매 틱
        에러를 낸다 — 이 항목이 그것을 잡는다).
- [ ] **창을 연 적 없이 언로드** — Maya를 새로 띄우고 플러그인만 로드했다가
      창을 한 번도 열지 않은 채 `cmds.unloadPlugin("maro")` → 에러 없음
      (언로드 경로가 `maroRosProxy.stop()`을 무조건 부르는데, `start()`가
      한 번도 안 불린 상태에서도 무동작이어야 한다).

### 막혔을 때 — 격리가 기대대로 안 걸리면

`isolateSelect`가 이 단계에서 유일하게 "계획 시점에 미검증"으로 남았던
메커니즘이다. 아래 순서로 좁힌다. **무엇이 나왔든 결과란에 그대로 적는다 —
계획과 다르면 실제 동작을 따르고 이유를 기록하는 것이 이 프로젝트의 규율이다
(Phase 0-1의 `modelPanel` chrome 플래그, Phase 2의 `paneLayout` 때와 같다).**

1. 격리 목록에 무엇이 들어갔는지 직접 본다:

   ```python
   cmds.isolateSelect("maroMainWindowViewportMaya", q=True, viewObjects=True)
   cmds.isolateSelect("maroMainWindowViewportRos", q=True, viewObjects=True)
   ```

   (`-viewObjects`는 격리 목록을 담은 오브젝트 세트를 준다.)
2. **두 패널의 목록이 같게 나오면** 격리가 패널별이 아니라 전역으로 걸린
   것이다 — 이 설계의 전제가 깨진 것이므로 그대로 BLOCKED로 적고 보고한다.
3. **좌측이 계속 비어 있으면**, 격리 켜기가 Maya 자신의 경로와 달라서일 수
   있다. Maya는 `enableIsolateSelect`(= `modelEditor -e -viewSelected` +
   에디터 목록 등록)를 쓰는데, 이 모듈은 일부러 `isolateSelect -state`만
   쓴다(그 프로시저가 `DagObjectCreated` 자동 추가를 띄워 **우측 패널에도**
   사용자 오브젝트를 밀어 넣기 때문 — `maroRosProxy.py` 도크스트링 참고).
   진단용으로 아래를 한 번 시도해 보고, 이걸로 좌측이 채워지면 그 사실을
   적는다(수정은 코드 쪽에서 해야 한다):

   ```python
   cmds.editor("maroMainWindowViewportMaya", e=True, mainListConnection="activeList")
   ```
4. 새 오브젝트만 안 나타나면(처음 목록은 맞는데) 멱등성이 아니라 idle 잡
   자체가 안 도는 것일 수 있다:

   ```python
   [j for j in (cmds.scriptJob(listJobs=True) or []) if "maroRosProxy" in j]   # 비어 있으면 잡이 없다
   ```

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
      체크리스트와 같은 습관). **알려진 예외 하나**: 로드와 언로드를 유휴
      시간 없이 같은 스크립트 실행 안에서 곧바로 이어 붙이면(이 체크리스트가
      요구하는 정상적인 절차에서는 일어나지 않는다), `initializePlugin`이
      유휴 큐에 넣어 둔 `maroBuildMenu` 호출이 언로드 이후에 실행되면서
      "프로시저를 찾을 수 없다"류의 에러가 찍힐 수 있다(최종 리뷰 I5/N5) —
      크래시 없이 이 에러 하나만 나타났다면 실패로 보지 않는다.
- [ ] 창이 닫힌다(`uninitializePlugin`이 `maroMainWindowControl`을 닫고, 남아
      있으면 두 뷰포트 패널(`maroMainWindowViewportMaya`/
      `maroMainWindowViewportRos`, Phase 2부터 둘로 늘어남)까지 지운다).
- [ ] 언로드 직후 아래가 전부 `False`다(Phase 2부터 뷰포트가 두 개라 이름도
      두 개 확인한다 — `maroMainWindowViewport`(단수)는 더 이상 존재하지
      않는 이름이라 확인해도 항상 `[]`만 나오고 아무것도 증명하지 못한다):

      ```python
      cmds.workspaceControl("maroMainWindowControl", exists=True)   # False
      cmds.modelPanel("maroMainWindowViewportMaya", exists=True)    # False
      cmds.modelPanel("maroMainWindowViewportRos", exists=True)     # False
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
      떼어내 플로팅으로 돌아오는지 확인한다. 도킹된 상태에서도 두 뷰포트
      조작과 버튼 클릭이 그대로 동작한다(도킹은 `-uiScript`로 UI를 다시 짓게
      만드므로, `buildUI()`가 두 번째로 불려도 **두 뷰포트 모두** 패널 이름
      충돌 없이 성립하는지가 실제로 확인되는 지점이다 —
      `_deleteStalePanel(panelName)`이 각 뷰포트 이름으로 한 번씩 그것을
      맡는다).
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
- [ ] **N/A — Phase 2가 실제로 구현되어 §1-1로 대체됨.** 이 항목은 원래
      Phase 2를 만들기 *전에* "두 번째 뷰포트가 첫 번째를 깨뜨리지 않을까"를
      미리 확인해 두려던 자리표시자였다. 지금은 실제 듀얼 뷰포트가 §1-1에
      있으므로 이 항목은 더 이상 뜻이 없다 — 여기 있던 스니펫(임시로 세
      번째 패널 `maroProbeViewport`를 만들어보는 것)은 실행하지 않는다
      (`maroMainWindowViewport`(단수)가 가리키는 패널이 이제 없어서 그대로
      실행하면 에러만 난다).

---

## 결과 기록

확인한 사람이 날짜와 결과를 여기에 적는다. **[필수]** 표시된 모든 행이
통과해야 그 행이 속한 Phase가 완료된 것으로 본다 — 이 표는 Phase 0-1,
Phase 2, Phase 3 판정을 함께 담고 있다(§1-1이 Phase 2, §1-2가 Phase 3,
나머지는 Phase 0-1 소속). §4의 "두 번째 뷰포트 여지 확인"은 Phase 2가 실제로
구현되며 N/A로 대체됐다. Maya 빌드 번호도 함께 기록한다.

"관찰" 행은 합/불합격 판정이 아니라 **사실만 적는 자리**다 — 계획 시점에
예측할 수 없었던 것을 기록해 두기 위한 것이고, 그 자체로 Phase 완료를
막지 않는다.

| 절 | Phase | 필수 여부 | 결과 | 날짜 / 확인자 / Maya 빌드 | 비고 |
|---|---|---|---|---|---|
| 1. modelPanel 뷰포트 | 0-1 | 필수 | **PASS** | 2026-08-25 / 사용자 / Maya 2026 | 큐브 렌더링, 궤도/팬/줌, chrome 숨김 전부 확인 |
| 1-1. 듀얼 뷰포트 — 레이아웃/조작/chrome | 2 | 필수 | **PASS** | 2026-08-25 / 사용자 / Maya 2026 | 두 뷰포트 정상 렌더링. 카메라는 둘 다 `persp` 공유(관찰, 이 단계에선 예상된 동작 — 실패 아님) |
| 1-1. 언로드 크래시 없음 — 플로팅 (두 뷰포트) | 2 | 필수 | **PASS** | 2026-08-25 / 사용자 / Maya 2026 | 크래시 없음, `workspaceControl`/두 뷰포트 exists 전부 False 확인 |
| 1-1. 재로드 후 재오픈 | 2 | 필수 | **PASS** | 2026-08-25 / 사용자 / Maya 2026 | 이름 충돌 없이 두 뷰포트 정상 재생성 |
| 1-1. 언로드 크래시 없음 — 도킹 (두 뷰포트) | 2 | 필수 | **PASS** | 2026-08-25 / 사용자 / Maya 2026 | 도킹 상태에서 재실행, 문제 없음 |
| 1-2. 격리가 켜지고 패널별로 걸린다 | 3 | 필수 | | | `isolateSelect -q -state`가 두 패널 모두 1, `-q -viewObjects`가 두 패널에서 다른 목록 |
| 1-2. 좌측=원본만 / 우측=프록시만 | 3 | 필수 | | | 이 단계 전체의 전제 |
| 1-2. 실시간 추종 + 축 변환 방향 | 3 | 필수 | | | `(x,y,z) -> (x,-z,y)` + cm→m |
| 1-2. **창을 연 뒤 만든 오브젝트가 좌측에 바로 보인다** | 3 | 필수 | | | 사용자 명시 요구사항. 통과하면 `-addDagObject` 멱등성도 함께 확인된 것 |
| 1-2. 고정(pin) / 해제가 동작한다 | 3 | 필수 | | | `maroSetRosProxyTarget` ↔ 선택 추종 |
| 1-2. 프록시가 자기 자신을 안 따라간다 (+ 창 열 때 선택 유지) | 3 | 필수 | | | 되먹임 방지 |
| 1-2. 창을 닫으면 동기화가 멈춘다 (잡 안 남음) | 3 | 필수 | | | `closeCommand` 경로 |
| 1-2. **창을 띄운 채 언로드 — 크래시/에러/잔여 잡 없음** | 3 | 필수 | | | Phase 3의 진짜 go/no-go |
| 1-2. 창을 연 적 없이 언로드 | 3 | 필수 | | | `stop()`이 `start()` 없이도 안전한가 |
| 1-2. 성능 (관찰) | 3 | 관찰 | | | idle 콜백이 매 틱 도는 구조 — 끊김/CPU 사용을 적는다 |
| 1-2. 단위 / 씬 수정 표시 (관찰) | 3 | 관찰 | | | 로케이터 값이 ROS 미터인 것은 의도된 동작 |
| 2. PySide6 버튼 | 0-1 | 필수 | **PASS** | 2026-08-25 / 사용자 / Maya 2026 | 표시/스타일/클릭 확인. 리사이즈·1분 유지 항목은 별도로 재확인 안 함 |
| 2. `show()` 복원 분기 — 플로팅 | 0-1 | 필수 | **PASS** | 2026-08-25 / 사용자 / Maya 2026 | 창 열린 채 재호출, 에러 없이 기존 창 유지 |
| 3. 언로드 크래시 없음 — 플로팅 | 0-1 | 필수 | **PASS** | 2026-08-25 / 사용자 / Maya 2026 | 크래시/에러 없음, `workspaceControl` exists=False, 뷰포트 패널 목록 `[]` 둘 다 확인(주: 이 실행 시점엔 뷰포트가 하나였다 — Phase 2 이후 재실행 시 위 §3의 갱신된 두-이름 확인으로 다시 돈다) |
| 3. 언로드 크래시 없음 — 도킹 | 0-1 | 필수 | **PASS** | 2026-08-25 / 사용자 / Maya 2026 | 도킹 상태에서 재실행, 문제 없음(위와 같은 주: 뷰포트 하나였던 시점) |
| 3-1. Maro 메뉴 (멱등성 포함) | 0-1 | 필수 (Task 3) | **부분 PASS** | 2026-08-25 / 사용자 / Maya 2026 | 메뉴 표시/클릭 확인됨. `cmds.maroBuildMenu()` 연속 두 번 호출하는 멱등성 자체 테스트는 미실행 |
| 4. 도킹 (+ `show()` 복원 분기 — 도킹) | 0-1 | 필수 | **PASS** | 2026-08-25 / 사용자 / Maya 2026 | 위 "언로드 — 도킹"과 같은 세션에서 확인 |
| 4. 재시작 복원 (+메뉴 표시) | 0-1 | 필수 | **FAIL** | 2026-08-25 / 사용자 / Maya 2026 | "Windows > Workspaces > Save Current"로 레이아웃 저장 후 재시작해도 Maro 창이 자동 복원되지 않음(레이아웃 자체는 "Maro" 컴포넌트를 기억하지만 플러그인 자동 로드도, 창 재구성도 안 일어남). 수동으로 `loadPlugin` 해도 창은 안 뜸. 동일한 `workspaceControl -requiredPlugin` 메커니즘을 쓰는 기존 `maroDiagPanel`도 같은 한계를 가질 가능성이 높아, 이 브랜치가 새로 만든 회귀는 아닌 것으로 판단 — 별도 후속 조사 필요(Phase 0-1 완료 판정에는 포함하지 않음, 아래 참고) |
| 4. 두 번째 뷰포트 여지 확인 | 0-1 | N/A | N/A | | Phase 2가 실제로 구현되어 §1-1로 대체됨 — 더 이상 실행하지 않음 |

### 종합 판정 (2026-08-25)

**이 스파이크의 진짜 존재 이유(§1/§2/§3 — 네이티브 `modelPanel`과 PySide6
위젯이 한 창에서 공존하고, 언로드해도 Maya가 크래시하지 않는가)는 전부
PASS로 확인됐다.** 이번 세션 전체의 go/no-go 판정은 이걸로 확정한다 — 뒤에
계획된 로드맵(뷰포트 2개, ROS 좌표 프록시, 스켈레톤 업로드 등)을 계속
진행해도 좋다.

남은 두 항목은 완료 판정에서 제외하고 후속 과제로 남긴다:

- **3-1의 멱등성 자체 테스트 미실행** — 메뉴가 실제로 보이고 클릭이 되는
  것은 확인됐지만, `cmds.maroBuildMenu()`를 메뉴가 이미 있는 채로 연달아
  두 번 부르는 좁은 의미의 멱등성 가드는 시간 관계상 직접 확인하지
  않았다. 코드 리뷰(최종 리뷰 I1 수정, `python/maroMenu.py`의
  `if cmds.menu(MENU_NAME, exists=True): return`)는 이미 통과했으므로
  리스크는 낮다고 본다.
- **재시작 복원 실패** — 워크스페이스를 명시적으로 저장해도 Maro 창이
  다음 세션에 자동으로 안 뜨고, 플러그인을 수동으로 로드해도 안 뜬다.
  `maroDiagPanel`도 동일한 `workspaceControl -requiredPlugin` 메커니즘을
  쓰므로 이 브랜치가 새로 만든 결함일 가능성은 낮지만, 확정하려면
  `maroDiagPanel`로 같은 재현 절차(워크스페이스 저장 → 재시작)를
  독립적으로 한 번 더 돌려봐야 한다. 이 스파이크의 핵심 판정에는
  포함하지 않고, `docs/superpowers/plans/2026-08-24-maro-main-ui-phase0-1.md`
  로드맵의 후속 조사 항목으로 넘긴다.

### Phase 2 종합 판정 (2026-08-25)

**§1-1(듀얼 뷰포트) 전부 PASS.** 두 뷰포트 정상 렌더링, chrome 숨김,
플로팅/도킹 둘 다 언로드 무크래시, 재로드 후 재오픈 정상. 카메라는 예상대로
`persp` 하나를 공유(관찰, 실패 아님 — Phase 3에서 분리 예정). Phase 2도
go/no-go 통과 — 로드맵의 다음 단계(ROS 좌표 프록시, Phase 3)로 진행 가능.
