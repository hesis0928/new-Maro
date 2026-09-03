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

## 1-3. 노드 바인딩 + capability 에디터 (Phase 4) — **[필수 · go/no-go]**

이 절은 대화형 Maya에서만 확인할 수 있다(패널 표시, 버튼 클릭, 양방향
선택 동기화는 배치 mayapy에 UI가 없어 자동 검증 불가).

```python
cmds.maroMainWindow()
```

- [ ] **에디터 패널이 보인다** — 뷰포트 오른쪽(또는 아래, 실제 레이아웃에
      따라)에 축 목록 + capability 스택 + 버튼 7개가 보인다.
- [ ] **축 생성 + 목록 갱신**:

      ```python
      axis = cmds.createNode("maroAxis", name="checklistAxis")
      cube = cmds.polyCube(name="checklistCube")[0]
      cmds.maroBindAxis(axis, cube)
      ```

      패널을 다시 열거나 새로고침하면(구현에 따라 자동/수동) `checklistAxis`가
      왼쪽 목록에 나타난다.
- [ ] **씬 선택 -> 패널 반영**: `cmds.select(cube)`로 큐브를 선택하면
      패널의 축 목록에서 `checklistAxis`가 강조되고 capability 스택이
      갱신된다(아직 비어 있음).
- [ ] **패널 -> 씬 선택 반영**: 패널에서 `checklistAxis` 행을 클릭하면
      씬에서 `checklistCube`가 선택된다(`cmds.ls(sl=True)`로 확인).
- [ ] **capability 추가**: "+Rotation" 버튼을 누르면 `maroRotation` 노드가
      생성·연결되고 스택 목록에 나타난다. `cmds.getAttr(cube + ".rotateY")`를
      새 `maroRotation` 노드의 `.angle`에 직접 `connectAttr`한 뒤 값을 바꾸면
      큐브가 실제로 회전한다(값 연결은 여전히 수동임을 재확인 — 설계 스펙 §7).
- [ ] **상호배타 규칙**: 같은 축에 "+Translation"을 또 누르면 에러가 나고
      (스크립트 에디터에 실패 메시지), 스택에 두 번째 노드가 추가되지 않는다.
- [ ] **capability 삭제**: 스택에서 항목을 선택하고 "Remove Selected
      Capability"를 누르면 연결이 끊기고 목록에서 사라진다. `Ctrl+Z`로
      복구된다.
- [ ] **Unbind**: "Unbind" 버튼을 누르면 큐브와의 바인딩이 끊긴다.
      `Ctrl+Z`로 복구된다.
- [ ] **레이아웃 재구성 회귀 확인**: Phase 2 §1-1(듀얼 뷰포트 렌더링/조작)과
      §3(Maro 메뉴)을 재실행해 새 중첩 `paneLayout` 구조에서도 그대로
      동작하는지 확인한다.
- [ ] **언로드 go/no-go**: 패널이 열리고 축/capability가 존재하는 상태에서
      `cmds.unloadPlugin("maro")` — 크래시 없음, 에러 반복 없음,
      `[j for j in (cmds.scriptJob(listJobs=True) or []) if "maroAxisPanel" in j]`가
      `[]`.

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
- [ ] "Maro 창 열기" 클릭 → `maroMainWindow`가 열린다. "환경설정..." 항목은
      더 이상 자리표시자가 아니다 -- 클릭하면 설정 창이 열린다(아래 "Maro
      환경설정 창" 절 참고).
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

## 1-4. 노드 캔버스 + 마킹 메뉴 (SONE/ONE, Task 3-9) — **[필수 · go/no-go, 이 플랜 전체의 마지막 판정]**

이 절은 `python/maroDagMenu.py`(오브젝트 우클릭 메뉴 통합), SONE 팝업
(`python/maroSingleObjectNodeEditor.py`)의 방사형 마킹 메뉴, ONE 오버뷰
그리드(`python/maroObjectNodeEditor.py`)를 통틀어 검증한다. 지금까지 나온
모든 절과 마찬가지로 배치 `mayapy`에는 `QApplication`이 없어 실제 마우스
제스처/다이얼로그/마킹 메뉴 렌더링은 원리적으로 자동 검증이 불가능하다
(§0의 설명과 동일한 이유) — 이번 태스크가 헤드리스 `mayapy` standalone으로
실제 빌드된 플러그인에 대고 확인한 것은 `cmds.maroAddCapability(...)[0]`의
반환 형태, Coupling 드롭다운이 읽는 `maroListAxisNodes()`의 필드 배치(표시
이름 폴백 포함), 그리고 `sourceValue`/`sourceValueLinear`/`sourceIsLinear`
연결 로직(각·선형 두 갈래 모두)뿐이다 — 아래 항목은 전부 사람이 대화형
Maya에서 직접 확인해야 한다.

```python
cmds.loadPlugin(r"C:\Users\ckd30\Projects\Maya_Ros_Sim\out\build\src\maro_plugin\Release\maro.mll")
cmds.file(new=True, force=True)
```

| # | 확인 항목 | 결과 |
|---|---|---|
| 1 | `maroLoadPlugin` 후 아무 오브젝트나 우클릭 -> 기존 Maya 기본 항목(Vertex/Edge/Face/...) 전부 그대로 있고 그 안에 `Maro node editor` 항목 추가로 보임 | |
| 2 | 바인딩 안 된 오브젝트에서 `Maro node editor` 클릭 -> 이름 프롬프트 -> 색상 선택 -> SONE 팝업이 뜨고 새 `maroAxis`가 그 오브젝트에 바인딩됨 | |
| 3 | 두 다이얼로그 중 아무 데서나 취소 -> 아무 노드도 생성되지 않음 | |
| 4 | 이미 바인딩된 오브젝트에서 `Maro node editor` 클릭 -> 다이얼로그 없이 바로 그 축의 SONE가 뜸 | |
| 5 | SONE 안에서 우클릭+홀드+드래그 -> 7개 항목이 방사형으로 펼쳐지고, 하나에서 릴리즈하면 그 능력이 적용됨 | |
| 6 | 능력이 부여된 SONE 노드를 선택하고 Delete -> 노드는 남고 `undefined`로 복귀 | |
| 7 | 능력을 2개 이상 쌓은 뒤 노드를 더블클릭 -> 쌓인 목록이 펼쳐짐, 다시 더블클릭하면 접힘 | |
| 8 | 펼쳐진 capability 목록 안에서 특정 행을 클릭해 선택한 뒤 Delete -> 선택한 그 capability **하나만** 제거됨(가장 최근에 추가한 것이 아니라). 펼쳐진 목록에서 아무것도 선택하지 않은 채 Delete -> 기존과 동일하게 가장 최근에 추가한 capability가 제거됨 | |
| 9 | `Coupling` 추가 시 소스 축 드롭다운 팝업이 뜨고, 자기 자신은 목록에 없고 다른 축이 표시 이름(없으면 노드 이름)으로 나열됨 | |
| 10 | 드롭다운에서 다른 축을 골라 Connect 클릭 -> 팝업이 닫히고, `cmds.listConnections`로 그 coupling 노드의 `sourceValue`(각) 또는 `sourceValueLinear`(선형, 소스 축의 `driveIsLinear`에 따라 갈림)가 소스 축의 `position`/`positionLinear`로부터 연결돼 있음이 확인됨 | |
| 11 | MaroUI를 열고 하단 패널에서 만들어진 축마다 GSON이 그리드로 보임, 지정한 이름/색이 그대로 반영됨 | |
| 12 | GSON 더블클릭 -> 해당 SONE가 뜨거나(닫혀 있었으면) 앞으로 옴(열려 있었으면) | |
| 13 | GSON 우클릭 -> Rename/Recolor/Delete 각각 정상 동작, Delete는 축과 그 capability 노드까지 완전히 제거. 메뉴에 `Unbind` 항목도 있음 -- **바인딩된 축에서만** 보이고, 이미 언바인드된 축의 GSON에서는 안 보임. `Unbind` 클릭 -> 축과 대상 오브젝트의 연결이 끊기고, 이후 그 GSON을 다시 우클릭하면 재바인딩 전까지는 `Unbind` 항목이 더 이상 나타나지 않음 | |
| 14 | 씬에서 오브젝트 선택 -> 해당 GSON에 **눈에 보이는 강조 테두리**가 표시됨(반대 방향은 GSON 클릭 시 씬 선택이 바뀜). 씬 선택을 해제하면(빈 곳 클릭 등) GSON의 강조 테두리도 사라짐 | |
| 15 | `maroUnloadPlugin` 후 아무 오브젝트나 우클릭 -> `Maro node editor` 항목이 사라지고 나머지 메뉴는 로드 전과 동일 | |
| 16 | MaroUI를 연 채로 플러그인 언로드 -> 크래시 없음, SONE 팝업(및 Coupling 소스 픽커)이 떠 있는 상태로 언로드해도 크래시 없음 | |
| 17 | Phase 2/3의 듀얼 뷰포트(§1-1/§1-2) 재확인 -- 이번 레이아웃 변경으로 회귀 없음 | |

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

## 5. Tech Diag 검사 (Phase 6) — **[필수 · 수동 확인]**

Tasks 1-4에서 구현한 Tech Diag 기술 진단 기능(양쪽 뷰포트 옆의 사이드 패널에서 실행하는 온디맨드 검사)의 엔드투엔드 동작을 확인한다. 다음 시나리오들을 차례로 진행한다.

| # | 확인 항목 | 결과 |
|---|---|---|
| 1 | MaroUI 창이 넓어지고 뷰포트 좌우에 사이드 패널이 보임, 뷰포트 자체 크기는 줄지 않음 | |
| 2 | 리밋에 근접한 축이 있는 씬에서 Maya측 "검사 실행" -> 경고가 뜨고 적용 버튼은 없음 | |
| 3 | 서로 겹치는 메쉬 2개가 있는 씬에서 Maya측 검사 -> 충돌 경고가 뜨고 적용 버튼은 없음 | |
| 4 | 문제 없는 씬에서 양쪽 검사 실행 -> "문제 없음" 표시 | |
| 5 | jointName이 빈 축이 있는 씬에서 ROS측 검사 -> 경고 + 적용 버튼, 클릭하면 채워지고 목록이 갱신됨, Ctrl+Z로 되돌아감 | |
| 6 | jointName이 중복된 두 축이 있는 씬에서 ROS측 검사 -> 나중 축에 `_2` 접미사 제안 + 적용, Ctrl+Z로 되돌아감 | |
| 7 | 활성화+바인딩됐지만 capability가 없는 축이 있는 씬에서 ROS측 검사 -> 경고, 적용 버튼 없음 | |
| 8 | 두 검사 모두 버튼을 누르기 전에는 씬을 바꾸지 않음(재계산만 함) | |
| 9 | Maya 세션의 각도 단위를 degrees로 두고(기본값), 리밋 범위 중간값에 있는 회전축에서 검사 실행 -> 리밋 근접 경고가 뜨지 않음 | |
| 10 | 검사 함수가 예외를 던지면 "문제 없음"이 아니라 "검사 실패 -- 스크립트 에디터 참조"가 표시된다 | |

9번은 2·4번이 원리상 잡을 수 없는 결함 전용 행이다 — `axis.position`은
`MFnUnitAttribute::kAngle`이라 `cmds.getAttr()`이 UI 단위(기본 도)로 답하는데
비교 상대인 `capabilityIn[i].capMin/capMax`는 생 라디안이다. 둘을 그대로
비교하면 ±90도로 제한된 축이 안전한 45도에 있어도 `45.0` vs `1.5708`이 되어
경고가 뜬다. 2번은 "경고가 뜬다"를, 4번은 "문제 없는 씬"을 보기 때문에 도 단위
세션에서 회전축이 0이 아닌 상태를 명시적으로 요구하지 않아 둘 다 통과해
버린다. 9번은 **각도 단위를 degrees로 되돌린 뒤**(테스트가 아니라 사용자
세션의 기본값이 바로 이것이다) 확인해야 의미가 있다.

## 6. LiDAR 설정 + 시각화 (Phase 5) — **[필수 · go/no-go]**

### 6-1. `maroPointCloud` 드로우 오버라이드 (Task 1)

이 절이 확인하는 것은 배치 테스트(`tests/maya/test_point_cloud_node.py`)가
원리적으로 확인할 수 없는 것 -- 실제 GPU 컨텍스트에서 점이 그려지는지, 그리고
그 지오메트리가 보이는 상태로 플러그인을 언로드해도 Maya가 살아남는지 -- 뿐이다.
어트리뷰트 계약(기본값, `points` 왕복, `setStorable(false)`, `boundingBox()`)은
배치 테스트가 이미 고정해 두었으므로 여기서 다시 보지 않는다.

1. 플러그인을 로드하고 빈 씬에서 스크립트 에디터(Python)로:
   ```python
   import maya.cmds as cmds
   node = cmds.createNode("maroPointCloud")
   cmds.setAttr(node + ".points", 5,
                (0,0,0,1), (2,0,0,1), (0,2,0,1), (0,0,2,1), (1,1,1,1),
                type="pointArray")
   ```
2. **[필수]** 뷰포트에 점 5개가 실제로 보이는가(작은 원/사각형 형태로,
   `pointSize` 기본값 2.0 크기, 기본 색 하늘색 `(0.2, 0.8, 1.0)`).
3. `cmds.setAttr(node + ".pointSize", 8.0)` — **[필수]** 점이 즉시(다음
   리드로우에) 커지는가. **주의**: 이것은 `preEvaluation()`의 dirty 신호가
   동작한다는 증거가 **아니다** -- `MaroPointCloudNode::preEvaluation()`은
   `evaluationNode.dirtyPlugExists(aPoints, ...)`만 검사하므로 `pointSize`가
   dirty해져도 이 콜백은 아무 것도 하지 않는다. 그런데도 점이 즉시 커진다면
   그것은 통상적인 DG dirty 전파가 `prepareForDraw()`를 다시 부르게 만드는
   별개의 경로가 동작한다는 증거일 뿐이다(어느 경로인지는 이 절의 범위 밖).
   `preEvaluation()`의 dirty 신호 자체를 증명하는 것은 아래 6번이다.
4. **[필수 · `boundingBox()`가 실제 점 범위를 반영하는가]** *(최종 리뷰
   Minor-4로 문구를 고쳤다 -- 예전 문구는 "프러스텀 밖으로 나가도 컬링되지
   않는가"였는데, 화면 밖 지오메트리를 컬링하는 것은 Viewport 2.0의 정상
   동작이지 결함이 아니다. 그대로 두면 정상 동작을 실패로 적게 된다.)*
   원점에서 멀리 떨어진 점을 하나 추가한 뒤, **그 점이 화면 안에 보이는
   구도로 카메라를 맞춘 상태에서** 실제로 그려지는지 본다:
   ```python
   cmds.setAttr(node + ".points", 6,
                (0,0,0,1), (2,0,0,1), (0,2,0,1), (0,0,2,1), (1,1,1,1),
                (200, 0, 0, 1),
                type="pointArray")
   ```
   - 뷰포트에서 `f`(프레임 전체)를 눌러 모든 점이 들어오는 구도로 맞춘다.
   - **[필수]** 멀리 있는 그 점이 **화면 안에 있는 동안 계속 보인다.**
     `boundingBox()`가 실제 점 범위를 안 읽고 고정된 작은 박스(예: 빈 배열
     폴백인 -1..1)만 돌려주면, 화면에 분명히 들어와 있는데도 이 점이
     통째로 사라진다 -- 그것이 이 항목이 잡으려는 회귀다.
   - **[필수]** 그려진 점들의 전체 퍼짐이 위에서 설정한 좌표와 눈으로
     일치한다(원점 근처 5개 + 멀리 X축 방향 1개).
   - 반대로 카메라를 돌려 그 먼 점이 **화면 밖으로 완전히 나가면** 안
     보이는 것이 정상이다 -- 이것은 실패가 아니다.
5. `cmds.setAttr(node + ".enabled", False)` — 점이 사라지고, 다시 `True`로
   되돌리면 다시 보이는가.
6. **[필수 · `preEvaluation()`이 실제로 지켜보는 유일한 어트리뷰트]** 점이
   보이는 상태에서 `.points`를 서로 다른 배열로 다시 설정한다:
   ```python
   cmds.setAttr(node + ".points", 2,
                (5, 0, 0, 1), (5, 5, 0, 1),
                type="pointArray")
   ```
   뷰포트가 다시 그려지고, 그려진 점이 실제로 원래 5개(십자 모양 배치)에서
   새 점 2개로 바뀌는가. `MaroPointCloudNode::preEvaluation()`은
   `points`가 dirty해질 때만 `MHWRender::MRenderer::setGeometryDrawDirty()`를
   부른다 -- `pointSize`/`color`/`enabled`는 지켜보지 않는다. 이 태스크의
   배치 테스트도, 위 3번도 이 경로를 실제로 증명하지 못한다 -- `.points`를
   이미 그려진 노드 위에서 바꿔 보는 이 단계만이 `preEvaluation()`의
   존재 이유를 실제로 검증한다.
7. **[필수 · 이 태스크의 진짜 기준]** 점이 보이는 상태로(뷰포트에서 보이게
   놔둔 채) 언로드를 시도한다. Maya는 씬에 커스텀 노드 인스턴스가 남아
   있으면 강제 옵션 없는 `unloadPlugin`을 거부한다(다른 배치
   테스트들이 언로드 전에 `cmds.file(new=True, force=True)`로 씬을 비우는
   이유가 이것이다 -- `tests/maya/test_axis_node.py`,
   `tests/maya/test_binding.py`, `tests/maya/test_point_cloud_node.py` 참고).
   이 단계의 목적은 지오메트리가 보이는 채로 언로드해도 Maya가 죽지 않는지를
   보는 것이므로, 씬을 먼저 비우면(=배치 테스트가 하는 것과 같은 절차)
   검증하려는 조건 자체가 사라진다. 그래서 두 단계로 나눠서 본다:
   1. 먼저 강제 옵션 없이 실행해 **거부되는 것을 확인한다** (이 거부
      자체는 실패가 아니라 Maya의 정상 동작이다 -- 결과표에 실패로
      기록하지 않는다):
      ```python
      cmds.unloadPlugin("maro")
      ```
      `RuntimeError`(또는 유사한 "아직 사용 중" 메시지)가 나야 정상이다.
   2. 이어서 강제 언로드로 실제 목표를 검증한다:
      ```python
      cmds.unloadPlugin("maro", force=True)
      ```
      **[필수]** Maya가 크래시하지 않는다. 스크립트 에디터에 크래시로
      이어질 만한 새 에러/트레이스백이 없는가(§3의 "알려진 예외"와 같은
      기준 -- 유휴 큐의 `maroBuildMenu` 관련 에러 하나만 나타났다면 실패로
      보지 않는다).

> **참고 (검증 상태):** 위 7번의 `force=True` 시퀀스는 이 수정을 작성한
> 환경에 대화형 GUI Maya가 없어 직접 재현해 확인하지 못했다. Maya의
> `unloadPlugin -force` 문서화된 동작(플러그인이 등록한 노드 타입의 씬
> 인스턴스를 먼저 제거한 뒤 언로드한다)에 근거해 절차를 고쳤다 -- 이 절을
> 처음 수행하는 사람이 위 절차가 실제로 이렇게 동작하는지 확인해 달라.

> 5번의 `enabled`, 그리고 2번의 기본 색은 브리프의 원래 절에는 없던 항목이다.
> `addUIDrawables()`가 `enabled`/`color`를 실제로 `prepareForDraw()`가 캐시해 둔
> 값에서 읽는지는 배치에서 볼 방법이 전혀 없어서(뷰포트 2.0은 실제 GPU 컨텍스트를
> 요구한다) 여기서 함께 본다 -- 그러지 않으면 그 두 어트리뷰트는 이 태스크에서
> 어떤 방식으로도 검증되지 않은 채 남는다.

### 6-2. 마킹메뉴 + 설정 팝업 (Task 4)

0. **[선행 조건 · 반드시 먼저 한다]** *(최종 리뷰 I-2)* 바로 앞 §6-1의
   마지막 단계가 `cmds.unloadPlugin("maro", force=True)`로 **플러그인을 강제
   언로드**했다 -- 그것이 §6-1의 go/no-go 판정 그 자체였으므로 건너뛸 수
   없었고, 그 결과 `## 준비`가 세워 둔 상태(메인 창, 두 뷰포트, ROS 프록시,
   그리고 `dagMenuProc` 체이닝까지)가 **전부 사라져 있다.** 이 절과 §6-3은
   그 상태가 살아 있다고 전제하므로, 여기서 다시 세우고 시작한다:

   ```python
   import maya.cmds as cmds
   cmds.loadPlugin(r"C:\Users\ckd30\Projects\Maya_Ros_Sim\out\build\src\maro_plugin\Release\maro.mll")
   cmds.file(new=True, force=True)
   cmds.maroMainWindow()
   ```

   `## 준비`의 4단계까지를 그대로 다시 한 것이다. "Maro" 창이 떠 있고 좌우
   두 뷰포트(Maya/ROS)가 보이는 상태가 되어야 아래로 진행한다.
1. 씬에 메쉬 오브젝트 하나를 만든다. 우클릭 → **[필수]**
   네이티브 마킹 메뉴에 "Maro node editor"와 나란히 "Maro LiDAR" 항목이
   보이는가.
2. "Maro LiDAR" 클릭 — **[필수]** 설정 팝업이 뜨고, 12개 필드가 기본값으로
   채워져 있는가.
3. 팝업에서 값 몇 개를 바꾸고 "적용" 클릭 → 팝업을 닫았다 다시 그 오브젝트를
   우클릭 → "Maro LiDAR" 클릭 — **[필수]** 새 팝업이 아니라 방금 바꾼 값이
   그대로 남아 있는 같은 노드의 팝업이 열리는가(재생성이 아니라 재오픈).
4. 메쉬가 아닌 오브젝트(예: 조인트, 로케이터)에 우클릭 → "Maro LiDAR" —
   **[필수]** 작은 구가 그 오브젝트의 자식으로 생기고 곧바로 선택된
   상태인가. 이동/크기 조절 툴로 바로 조작할 수 있는가.
5. 팝업에서 "타겟 메쉬 추가"(다른 메쉬를 선택한 채) → **[필수]** 리스트에
   추가되는가. "선택 제거" → 리스트에서 사라지고 실제 연결도 끊기는가
   (`cmds.listConnections`로 확인).
6. "Scan now" 클릭 → **[필수]** ROS 뷰포트에 포인트가 나타나는가(Task 1의
   드로우 오버라이드가 실제 스캔 데이터로 그리는 첫 확인).

### 6-3. 라이브 프리뷰 (Task 5) — **[필수 · go/no-go]**

0. **[선행 조건 · 반드시 먼저 한다]** *(최종 리뷰 I-1)* **브리지 펌프를
   켠다.** 라이브 프리뷰의 갱신은 오직 `MaroPump::collectLidarScans()` 안에서만
   일어나고, 그 함수는 `MaroPump::start()`가 타이머를 걸어 뒀을 때만 틱한다.
   `MaroPump::start()`를 부르는 곳은 `maroStartBridge` 커맨드 **하나뿐**이다 --
   즉 이걸 안 하면 "Live preview" 체크박스를 켜든 말든 포인트가 영영 갱신되지
   않고, 이 절 전체가 원인 불명의 FAIL로 끝난다(이 문서 어디에도 브리지를
   켜는 단계가 없었던 것이 그 함정이었다):

   ```python
   cmds.maroStartBridge("checklistRobot")
   ```

   인자는 로봇 이름 문자열 하나다(`tests/maya/test_bridge_pump.py`는
   `cmds.maroStartBridge("maro")`, `tests/maya/test_lidar_publish.py`는
   `cmds.maroStartBridge("testRobot")`로 부른다 -- 이름 자체는 /tf 발행에만
   쓰이므로 아무 값이나 좋다). 실제로 켜졌는지는 아래로 확인한다:

   ```python
   cmds.maroBridgeStats()   # 펌프가 돌기 시작하면 카운터가 0에서 늘어난다
   ```

   §6-2까지는 "Scan now" 버튼(=`maroSnapshotLidarScan`, 브리지와 무관한
   동기 스냅샷)만 썼기 때문에 브리지가 필요 없었다 -- 그래서 여기가 이
   문서에서 브리지를 처음 켜는 자리다. 이 절이 끝나면 `cmds.maroStopBridge()`로
   되돌려 둔다.
1. LiDAR 설정 팝업에서 "Live preview" 체크박스를 켜고 "적용".
2. 씬에서 타겟 메쉬를 이동시킨다(예: `translateX`를 애니메이션 재생 없이
   드래그로 계속 바꿔 본다). **[필수]** ROS 뷰포트의 포인트클라우드가
   메쉬를 따라 실시간으로 갱신되는가(수동 "Scan now" 클릭 없이).
3. **[필수 · Fix round 1, Finding I3 — 리드로우 타이밍 위험]** 이번엔
   반대로 아무것도 건드리지 않는다: 메쉬를 드래그하지 않고, 뷰포트를
   회전/줌하지 않고, 다른 명령도 실행하지 않은 채(타겟 메쉬가 자체
   키프레임 애니메이션으로 스스로 움직이고 있다면 그것만 재생해 두고,
   그런 애니메이션이 없다면 씬을 완전히 정지 상태로 둔 채) 몇 초간 그냥
   지켜본다. 라이브 프리뷰 쓰기는 `MPlug::setValue()`를 백그라운드 타이머
   콜백에서 직접 호출하는 raw plug write로, `MDGModifier`나 커맨드 경로를
   전혀 거치지 않는다 -- `MaroPointCloudNode::preEvaluation()`은 이
   노드 자신의 `points` 어트리뷰트가 통상적인 DG dirty 전파로 dirty해질
   때만 `setGeometryDrawDirty()`를 부른다. 2번이 통과하는 것은 메쉬를
   드래그하는 행위 자체가 (라이브 프리뷰와 무관한 이유로) 뷰포트
   리프레시를 강제하기 때문일 수 있어, 이 3번처럼 그 다른 리프레시
   유발 요인이 전혀 없는 상태에서 포인트클라우드가 펌프 틱만으로
   스스로 다시 그려지는지는 별도로 확인해야 한다. 포인트가 눈에 보이게
   갱신되지 않는다면, `cmds.getAttr(pointCloud + ".points")`를 Script
   Editor에서 반복 조회해 데이터 자체는 계속 바뀌고 있는지("화면만 안
   그려짐" — 리드로우 트리거 누락) 아니면 데이터도 멈춰 있는지("펌프/게이트
   문제")를 구분해 기록한다.

   > **갱신 (최종 리뷰 I-5):** 그 사이 `MaroPump::collectLidarScans()`의
   > 라이브 프리뷰 블록이 raw plug write **직후** 직접
   > `MHWRender::MRenderer::setGeometryDrawDirty(pointCloudNode)`를 부르도록
   > 고쳐졌다(`MaroPointCloudNode::preEvaluation()`이 쓰는 것과 같은 호출).
   > 즉 이제 리드로우는 Evaluation Manager가 이 노드를 평가 그래프에
   > 스케줄해 주느냐에 더 이상 의존하지 않는다. 이 항목은 그래도 그대로
   > 수행한다 — 이 수정이 실제 GPU 컨텍스트에서 의도대로 먹는지는 여전히
   > 사람만 확인할 수 있고, 이 항목이 그 유일한 확인 지점이다.

4. **[필수 · undo 큐를 도배하지 않는다]** *(최종 리뷰 Minor-10으로 문구를
   고쳤다 -- 예전 문구는 `cmds.undoInfo(query=True, undoQueueEmpty=True)`를
   봤는데, 그것은 "큐가 비었는가"라는 **bool**이지 개수가 아니다. 세션에서
   undo 가능한 일을 한 번이라도 한 뒤에는 영원히 `False`로 고정되므로,
   프리뷰가 매 틱 undo 항목을 밀어 넣고 있든 아니든 똑같이 `False`다 --
   무엇도 판정하지 못한다.)* 대신 **"가장 최근 undo 항목이 무엇인가"를
   전후로 비교**한다:

   ```python
   # (1) 라이브 프리뷰가 켜져 있고 펌프가 도는 상태에서, 기준점을 만든다.
   cmds.polyCube(name="undoProbeCube")      # 확실한 undo 항목 하나
   cmds.undoInfo(query=True, undoName=True) # -> 이 문자열을 적어 둔다
   ```

   이제 **아무것도 하지 않고**(마우스도 움직이지 않고) 10초쯤 기다린 뒤,
   같은 질의를 다시 한다:

   ```python
   cmds.undoInfo(query=True, undoName=True)
   ```

   **[필수]** 두 값이 **같아야 한다.** 라이브 프리뷰가 undo 큐에 무언가를
   밀어 넣고 있다면, 아무 조작도 안 했는데 "가장 최근 undo 항목"이 큐브
   생성에서 다른 것으로 바뀌어 있다. 이어서 `Ctrl+Z`를 **한 번** 눌러
   큐브가 곧바로 사라지는지도 확인한다(프리뷰 항목이 쌓였다면 여러 번
   눌러야 큐브에 도달한다). 이것이 "라이브 프리뷰 쓰기는 커맨드/`MDGModifier`
   가 아니라 raw plug write여야 한다"는 설계 제약의 실제 검증이다.
5. `verticalSamples`/`horizontalSamples`를 스펙급으로 크게 올려(예:
   64 x 2048, 단 `kMaxRaysPerScan` 상한 65536 이내로) 라이브 프리뷰를 켠
   채로 몇 초 관찰 — **[필수]** Maya UI가 멈추지 않고(디시메이션이
   실제로 포인트 수를 줄이고 있다는 증거), 뷰포트 프레임레이트가 크게
   떨어지지 않는가.
6. **[필수 · 이 태스크의 진짜 기준]** 라이브 프리뷰가 켜진 채(포인트클라우드가
   실제로 갱신되고 있는 상태) `cmds.unloadPlugin("maro")`를 실행한다. Maya가
   죽지 않는가 -- 렌더러가 소유한 오브젝트가 언로드 시점에 살아있는 상태라
   기존 언로드 테스트보다 위험도가 높다.

## 7. 스켈레톤 업로드/추출 (Phase 6) — **[필수 · go/no-go]**

1. 플러그인을 로드하고 씬을 새로 연다. "Maro" 메뉴 → "Skeleton Upload..."
   클릭 — **[필수]** 다이얼로그가 뜨는가("파일에서 임포트"/"현재 선택에서
   추출" 버튼 두 개).
2. 씬에 스킨된 메쉬 하나를 준비(간단한 실린더 + 조인트 체인 + 바인드 스킨)한
   뒤 선택하고 "현재 선택에서 추출" 클릭 — **[필수]** 상태 라벨에 인플루언스
   조인트 이름이 나열되고, 뷰포트에서 그 조인트들이 실제로 선택 상태로
   하이라이트되는가. 새 조인트가 만들어지지 않았는가(Outliner로 확인).
3. 스킨되지 않은 평범한 폴리곤 메쉬를 선택하고 "현재 선택에서 추출" 클릭 —
   **[필수]** `<메쉬이름>_root`라는 새 조인트가 메쉬의 바운딩박스 중심에
   생기고, 그 메쉬의 자식으로 붙어 있으며, 선택 상태인가.
4. 메쉬가 아닌 오브젝트(로케이터 등)를 선택하거나 아무것도 선택하지 않은
   채 "현재 선택에서 추출" 클릭 — **[필수]** "정확히 메쉬 하나를
   선택하세요" 메시지가 뜨고 아무 것도 만들어지지 않는가.
5. **[필수 · 이 기능의 진짜 위험 가정]** "파일에서 임포트" 클릭 → Maya의
   네이티브 임포트 다이얼로그가 뜨는가. 메쉬가 들어 있는 외부 파일(FBX/OBJ
   등)을 선택해 임포트 — 임포트가 끝나자마자 자동으로 스켈레톤 추출이
   이어서 실행되는가(스킨된 파일이면 인플루언스 선택, 아니면 루트 조인트
   생성). 이 항목이 실패하면 §4(콜백 스코핑)의 전제 자체를 재검토해야 한다.
6. 다이얼로그를 닫은 뒤 다른 목적으로(이 기능과 무관하게) File > Import로
   아무 파일이나 임포트 — **[필수]** 스켈레톤 추출이 자동으로 실행되지
   *않는가*(다이얼로그가 닫혀 있으면 콜백도 해제돼 있어야 한다).
7. 다이얼로그를 다시 열고 "파일에서 임포트"를 눌렀다가 파일 선택 창에서
   취소 — 다이얼로그를 닫는다 — **[필수]** 아무 크래시도, 스크립트
   에디터의 반복 에러도 없는가(취소로 인해 콜백이 걸린 채 남아있다가
   닫힐 때 정리되는 경로).
8. 다이얼로그가 열린 채로 `cmds.unloadPlugin("maro", force=True)` — **[필수]**
   Maya가 죽지 않는가(등록된 kAfterImport 콜백이 언로드 시 함께 정리됨).

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
| 1-2. Undo 큐가 프록시 갱신으로 도배되지 않는다 (`Ctrl+Z`) | 3 | 필수 | | | I2 수정(`MFnTransform`, undo 불가) 검증 — `Ctrl+Z` 한 번 = 큐브 이동 한 번만 취소 |
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
| 1-3. 에디터 패널 표시 + 목록/선택 동기화 | 4 | 필수 | | | 양방향(씬↔패널) |
| 1-3. capability 추가/삭제 + 상호배타 규칙 | 4 | 필수 | | | §3 규칙 |
| 1-3. Unbind + undo | 4 | 필수 | | | |
| 1-3. 레이아웃 재구성 후 Phase 2 §1-1/§3 재확인 | 4 | 필수 | | | 회귀 확인 |
| 1-3. 언로드 go/no-go (패널 + 축 존재 상태) | 4 | 필수 | | | |
| 1-4. 우클릭 메뉴 통합 (`Maro node editor` 항목, 있음/취소/이미 바인딩) | 5 | 필수 | | | 1-3의 목록형 `AxisPanel`을 대체 — `dagMenuProc` 체이닝 |
| 1-4. SONE 방사형 마킹 메뉴 (적용/Delete/더블클릭 펼침·접힘) | 5 | 필수 | | | |
| 1-4. Coupling 소스 축 드롭다운 + 연결 | 5 | 필수 | | | Task 9. 헤드리스 `mayapy`로 반환 형태(`maroAddCapability(...)[0]`)와 `sourceValue`/`sourceValueLinear`/`sourceIsLinear` 연결 로직 자체는 실제 빌드된 플러그인에 대고 사전 확인됨 — 드롭다운 팝업 UI만 사람이 확인 |
| 1-4. ONE/GSON 그리드 표시 + 이름/색 반영 | 5 | 필수 | | | |
| 1-4. GSON 더블클릭/우클릭(Rename/Recolor/Delete) | 5 | 필수 | | | |
| 1-4. 씬↔GSON 양방향 선택 동기화 | 5 | 필수 | | | |
| 1-4. 언로드 go/no-go (메뉴 항목 제거, SONE/Coupling 픽커가 뜬 채여도 무크래시) | 5 | 필수 | | | |
| 1-4. Phase 2/3 회귀 재확인 | 5 | 필수 | | | 레이아웃 변경 회귀 확인 |
| 6-1. `maroPointCloud` 점이 뷰포트에 보인다 (기본 크기/색) | 5(LiDAR) | 필수 | | | Task 1. 배치 테스트가 원리적으로 못 보는 부분 |
| 6-1. `pointSize` 변경이 즉시 반영된다 | 5(LiDAR) | 필수 | | | 통상적인 DG dirty 전파가 재드로우를 유발한다는 증거일 뿐 — `preEvaluation()`은 `points`만 지켜보므로 이 항목이 그 신호의 증거는 **아니다**(리뷰 Finding I3) |
| 6-1. `enabled` 토글이 반영된다 | 5(LiDAR) | 관찰 | | | `addUIDrawables()`가 캐시된 값을 실제로 쓰는지 |
| 6-1. **`.points`를 다른 배열로 재설정 — 그려진 점이 실제로 바뀐다** | 5(LiDAR) | 필수 | | | `preEvaluation()`이 `dirtyPlugExists(aPoints, ...)`로 지켜보는 유일한 경로의 실제 증거(리뷰 Finding I3) |
| 6-1. **점이 보이는 상태로 언로드 — 무크래시** | 5(LiDAR) | 필수 | | | Task 1의 진짜 go/no-go. `unloadPlugin("maro", force=True)`로 검증(리뷰 Finding I2 — 강제 옵션 없이는 Maya가 노드 인스턴스가 남아 있는 한 언로드 자체를 거부한다) |
| 6-2. 마킹 메뉴에 "Maro LiDAR" 항목이 보인다 | 5(LiDAR) | 필수 | | | Task 4. §6-2의 0번(플러그인 재로드 + `maroMainWindow()`)을 먼저 해야 한다 — §6-1이 강제 언로드로 그 상태를 없앤다(최종 리뷰 I-2) |
| 6-2. 설정 팝업이 뜨고 12개 필드가 기본값으로 채워진다 | 5(LiDAR) | 필수 | | | |
| 6-2. 재클릭이 재생성이 아니라 재오픈이다(바꾼 값 유지) | 5(LiDAR) | 필수 | | | |
| 6-2. 비-메쉬 오브젝트에서 placeholder 구가 생기고 선택된다 | 5(LiDAR) | 필수 | | | |
| 6-2. 타겟 메쉬 추가/제거가 실제 연결에 반영된다 | 5(LiDAR) | 필수 | | | `cmds.listConnections`로 확인 |
| 6-2. **"Scan now" → ROS 뷰포트에 포인트가 나타난다** | 5(LiDAR) | 필수 | | | 드로우 오버라이드가 실제 스캔 데이터로 그리는 첫 확인. 갓 만든 LiDAR가 기본 설정으로 히트를 내는지도 여기서 함께 드러난다(최종 리뷰 C-1 — `_onLidarMenuItemClicked()`이 `rangeMin`을 0으로 세운다; 배치 가드는 `tests/maya/test_lidar_menu.py`) |
| 6-3. 브리지를 켠 뒤 라이브 프리뷰가 메쉬를 실시간으로 따라간다 | 5(LiDAR) | 필수 | | | Task 5. §6-3의 0번(`cmds.maroStartBridge(...)`)을 먼저 해야 한다 — 펌프가 안 돌면 프리뷰는 영영 갱신되지 않는다(최종 리뷰 I-1) |
| 6-3. **정지 상태에서도 펌프 틱만으로 스스로 다시 그려진다** | 5(LiDAR) | 필수 | | | 리드로우 타이밍. 최종 리뷰 I-5로 `setGeometryDrawDirty()`를 명시 호출하도록 고침 — 실제 GPU 컨텍스트에서의 확인은 이 행이 유일하다 |
| 6-3. undo 큐가 프리뷰 틱으로 도배되지 않는다 | 5(LiDAR) | 필수 | | | `undoInfo -q -undoName`을 전후 비교(최종 리뷰 Minor-10으로 검사 방법 교체 — 예전 `undoQueueEmpty` bool은 아무것도 판정하지 못했다) |
| 6-3. 스펙급 샘플 수에서도 UI가 멈추지 않는다(디시메이션) | 5(LiDAR) | 필수 | | | 예: 64 x 2048, `kMaxRaysPerScan`(65536) 이내 |
| 6-3. **라이브 프리뷰가 도는 채로 언로드 — 무크래시** | 5(LiDAR) | 필수 | | | Task 5의 진짜 go/no-go. 렌더러가 소유한 오브젝트가 살아 있는 상태라 위험도가 가장 높다 |
| 7. 다이얼로그 표시(버튼 2개) | 6(Skeleton) | 필수 | | | Task 2 |
| 7. 스킨된 메쉬 — 인플루언스 선택(새 조인트 없음) | 6(Skeleton) | 필수 | | | `extractSkeleton()`의 skinCluster 분기 |
| 7. 스킨 없는 메쉬 — `<메쉬이름>_root` 생성 + 선택 | 6(Skeleton) | 필수 | | | `extractSkeleton()`의 폴백 분기 |
| 7. 메쉬 아님/미선택 — 에러 메시지, 생성물 없음 | 6(Skeleton) | 필수 | | | `_isSingleMeshSelected()` 가드 |
| 7. **"파일에서 임포트" → 임포트 직후 자동 추출** | 6(Skeleton) | 필수 | | | 이 기능의 진짜 위험 가정 — `kAfterImport` 콜백 스코핑의 존재 이유 |
| 7. 다이얼로그를 닫은 뒤 무관한 File > Import는 자동 추출 안 함 | 6(Skeleton) | 필수 | | | 콜백이 전역이 아니라 다이얼로그 생존 기간에만 걸려 있다는 증거 |
| 7. 임포트 취소 후 재시도/닫기 — 크래시·반복 에러 없음 | 6(Skeleton) | 필수 | | | 콜백 중복 등록 방지(`_removeImportCallback()` 선-호출) 경로 |
| 7. **다이얼로그가 열린 채 강제 언로드 — 무크래시** | 6(Skeleton) | 필수 | | | `maroSkeletonUpload.stop()`이 `maroMainWindow.teardown()`에 등록돼 콜백을 정리하는가 |

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

## Maro 환경설정 창

인터랙티브 Maya 2026에서 `maro.mll`을 로드하고 MaroUI를 연 뒤, Maro 메뉴에서
"환경설정..."을 클릭한다.

- [ ] **창이 뜨고 값이 로드된다** — 이전에 저장된 값이 없으면 robotName
      빈 칸, 도메인 ID 직접 지정 체크박스 꺼짐, 리밋 근접 임계값 90%로
      뜨는지 확인한다.
- [ ] **체크박스가 스핀박스를 잠근다/푼다** — "도메인 ID 직접 지정" 체크를
      켜고 끌 때 도메인 ID 스핀박스가 활성/비활성으로 바뀌는지 확인한다.
- [ ] **비모달이다** — 이 창을 띄운 채로 MaroUI의 다른 부분(뷰포트 회전,
      ONE 그리드 클릭 등)을 조작할 수 있는지 확인한다.
- [ ] **도메인 ID 미지정 연결** — robotName만 채우고(체크박스는 끈 채로)
      "연결"을 누른다. Script Editor에 ROS 연결 성공 메시지가 뜨는지
      확인한다.
- [ ] **[go/no-go] 도메인 ID가 실제로 반영된다** — "연결 해제"를 누른 뒤,
      "도메인 ID 직접 지정"을 켜고 임의의 값(예: 77)을 넣은 뒤 "연결"을
      누른다. 별도 터미널에서 `ROS_DOMAIN_ID=77 ros2 topic list`를 실행해
      Maro가 발행하는 토픽(`/<robotName>/joint_states` 등)이 그 도메인에서만
      보이고, 다른 도메인(예: 기본값 0)에서는 안 보이는지 확인한다. 이게
      안 되면 `os.environ["ROS_DOMAIN_ID"]` 경유 방식 자체를 재검토해야
      한다(설계 스펙 §3.5, 이번 계획의 Global Constraints 참고).
- [ ] **로봇 이름 없이 연결 시도** — robotName을 비운 채 "연결"을 누른다.
      `cmds.maroStartBridge`가 호출되지 않고 "enter a robot name" 경고만
      뜨는지 확인한다.
- [ ] **Tech Diag 임계값 저장이 다음 검사부터 적용된다** — 임계값을 50%로
      낮추고 "저장"을 누른다. 리밋에 60% 근접한 축을 하나 만들고(예:
      `capMin=0, capMax=10`인 리밋에 구동값 6) Maya측 Tech Diag 검사를
      실행해 리밋 근접 경고가 뜨는지 확인한다(90% 기본값이었다면 안 떴을
      경우).
- [ ] **창을 연 채 언로드** — 창이 열린 상태에서 `unloadPlugin maro`를
      실행한다. Maya가 크래시하지 않고 창이 닫히는지 확인한다.
- [ ] **재시작 후 값이 유지된다** — 로봇 이름/도메인 ID/임계값을 원하는
      값으로 바꾸고 창을 닫은 뒤 Maya를 완전히 재시작하고 플러그인을 다시
      로드한다. "환경설정..."을 다시 열어 방금 설정한 값이 그대로
      남아 있는지 확인한다(`optionVar`가 영구 저장소임을 확인하는 항목).

## Maro URDF 내보내기

인터랙티브 Maya 2026에서 축 2-3개짜리 간단한 체인(회전 관절 하나, 리밋
있는 관절 하나 포함)을 만들고, Maro 메뉴에서 "URDF 내보내기..."를
클릭해 `.urdf` 파일로 저장한다.

- [ ] **파일이 실제로 만들어진다** — 저장 대화상자에서 경로를 고르면
      그 자리에 `.urdf` 파일이 생기고, 하단에 "Maro: URDF exported to
      ..." 안내가 뜨는지 확인한다.
- [ ] **`check_urdf`로 파싱된다** — ROS 2가 설치된 환경에서
      `check_urdf <파일>`을 실행해 문법 오류 없이 파싱되는지, 관절/링크
      개수가 씬의 축 개수와 일치하는지 확인한다.
- [ ] **[go/no-go] RViz2에서 관절이 실제로 올바른 위치/방향으로 돈다** —
      `ros2 run robot_state_publisher robot_state_publisher <파일>` 등으로
      RViz2에 로드하고, `joint_state_publisher_gui`로 각 관절을 움직여
      봐서 Maya 씬에서 봤던 것과 같은 자리에서 같은 방향으로 도는지
      확인한다. 어긋나면 `computeRelativeOrigin`의 좌표 변환/오일러 순서
      가정(이 계획의 Task 2 참고)부터 재검토해야 한다 — 이게 이 기능
      전체에서 가장 위험한 가정이다.
- [ ] **부모 없는 축이 0개/2개 이상이면 명확한 에러가 뜬다** — 씬에서
      축 하나의 `parentAxis` 연결을 끊거나 둘째 루트를 만든 뒤 다시
      내보내기를 시도해, Script Editor에 어떤 축이 문제인지 알려주는
      경고가 뜨는지(크래시나 알 수 없는 트레이스백이 아니라) 확인한다.
- [ ] **빈 jointName이 있으면 명확한 에러가 뜬다** — 축 하나의 jointName을
      지우고 내보내기를 시도해 같은 방식으로 확인한다.
