# Maro 메인 UI Phase 3 — ROS 좌표 프록시 설계 (2026-08-25)

## 1. 배경

Phase 2(`docs/superpowers/specs/2026-08-25-maro-main-ui-phase2-dual-viewport-design.md`)에서 좌/우 뷰포트 두 개가 한 창 안에 공존하고, 언로드해도 안전하다는 것까지 대화형 Maya에서 검증했다(전부 PASS). 지금까지 우측 뷰포트는 좌측과 똑같은 씬을 다른 카메라로 보여줄 뿐, 실제 ROS 좌표계 콘텐츠는 없다. 이번 단계에서 처음으로 "우측 뷰포트가 실제로 ROS 좌표계를 보여준다"는 가정을 검증한다.

## 2. 문제: Maya 씬은 하나뿐이다

Maya 세션에는 씬(DAG)이 하나뿐이고, 두 `modelPanel`은 그 하나의 씬을 다른 카메라로 비추는 창일 뿐이다. 씬에 오브젝트를 만들면 두 뷰포트 모두에 나타난다. 좌측엔 원본만, 우측엔 ROS 프록시만 보이게 하려면 뷰포트별로 "무엇을 보여줄지" 필터가 필요하다.

## 3. 해결책: 그룹 분리 + 패널별 `isolateSelect`

씬을 물리적으로 두 개로 나눌 수는 없지만, 한 씬 안에 "칸막이"를 쳐서 사용자가 원한 "두 개의 방" 경험을 만든다:

1. 프록시 로케이터들은 전용 그룹(`maroRosProxy_grp`) 안에만 생긴다. 원본 오브젝트는 그대로 씬에 있던 자리에 둔다.
2. 좌측(Maya) 뷰포트는 `cmds.isolateSelect`로 `maroRosProxy_grp`를 뷰포트 격리 목록에서 제외해 원본만 보이게 하고, 우측(ROS) 뷰포트는 `maroRosProxy_grp`의 자식들만 격리해서 보이게 한다.
3. 그룹으로 분리해 둔 덕분에 나중에 동기화 대상이 여러 개로 늘어나도(Phase 5) 격리 대상은 "그룹 하나"로 단순하게 유지된다.

**이 메커니즘 자체가 이번 단계의 진짜 리스크다** — `isolateSelect`가 패널별로 정말 독립적으로 걸리는지, 정확한 플래그/동작이 이 계획 작성 시점엔 실제 Maya 2026에서 검증되지 않았다. 구현 중 직접 확인하고, 계획과 다르면 실제 동작을 따르고 그 이유를 기록한다(Phase 0-1의 `modelPanel` chrome 플래그, Phase 2의 `paneLayout` 때와 같은 규율).

## 4. 동기화 대상 결정: 기본은 선택 추종, 필요하면 고정

아직 오브젝트 업로드/바인딩 UI가 없다(Phase 4/5). 이번 단계는 딱 하나의 오브젝트만 동기화한다:

- **기본값**: idle 콜백이 매번 "지금 Maya에서 선택된 첫 번째 트랜스폼이 뭐지?"를 확인해서 그것을 동기화 대상으로 삼는다. 새 커맨드 없이 바로 테스트 가능(오브젝트를 선택하기만 하면 우측에 프록시가 뜬다).
- **고정 지정**: `maroSetRosProxyTarget <오브젝트>`를 부르면 그 뒤로는 선택이 바뀌어도 그 오브젝트만 계속 동기화한다. `maroSetRosProxyTarget -clear`로 고정을 풀면 다시 선택 추종으로 돌아간다. 고정 상태는 Maya `optionVar`(문자열 하나, `maroRosProxyPinnedTarget`)에 저장한다 — 세션 내내 유지되는 단순한 상태 하나면 충분하고, 이 프로젝트가 이미 여러 곳에서 쓰는 저장 방식이다.

## 5. 새 C++ 커맨드

- **`maroMayaToRos`**: `mayaToRosPosition`/`mayaToRosRotation`(`src/maro_transform/include/maro_transform/Convert.h`, 이미 존재, 실제 ROS 발행 파이프라인과 동일 소스)을 얇게 감싼다. 위치 3개(x,y,z) + 쿼터니언 4개(x,y,z,w)를 받아 변환된 7개 값을 평평한 배열로 돌려준다. 씬 단위는 커맨드 내부에서 `MDistance(1.0, MDistance::internalUnit()).asMeters()`로 직접 구한다(`MaroPump.cpp`의 `currentSceneUnit()`과 같은 패턴) — 호출하는 Python 쪽이 씬 단위를 몰라도 된다.
- **`maroRosToMaya`는 이번엔 만들지 않는다** — 로드맵 문서에 이름만 있었지만, 이번 단계는 Maya→ROS 단방향 시각화만 필요하고 역방향을 쓰는 곳이 없다(YAGNI). 실제로 필요해지면 그때 추가한다.
- **`maroSetRosProxyTarget`**: `<objectName>` 위치 인자 하나 또는 `-clear`/`-c` 플래그. 오브젝트를 지정하면 `optionVar -sv maroRosProxyPinnedTarget <objectName>`, `-clear`면 `optionVar -remove`.

두 커맨드 다 `MaroCommands.cpp`처럼 새 파일(`MaroRosProxyCommands.h`/`.cpp`)로 분리한다 — 기존 axis 바인딩 커맨드들과 성격이 다르다(DG 편집이 아니라 순수 계산 + optionVar 설정).

## 6. Python 동기화 루프 (`python/maroRosProxy.py`)

- **`start(mayaPanelName, rosPanelName)`**: 두 뷰포트 이름을 인자로 받는다(모듈 전역에 저장) — `maroRosProxy.py`가 격리 갱신(§7)까지 같이 맡으므로 어느 패널이 Maya/ROS인지 알아야 하는데, `maroMainWindow.py`를 import해서 상수를 가져오면 두 모듈이 서로 import하는 순환 참조가 생기므로 인자로 전달받는다. 격리 초기 설정(우측 패널에 프록시 그룹 추가, 두 패널 `isolateSelect(state=True)`)을 한 번 하고, `cmds.scriptJob(event=["idle", _onIdle], protected=True)`로 idle 콜백을 건다. 이미 돌고 있으면(모듈 전역에 잡 ID 저장) 중복 등록하지 않는다 — `maroMainWindow.py`의 `_deleteStalePanel()`이 패널 재생성 충돌을 막는 것과 같은 이유로, `buildUI()`가 여러 번 불려도(도킹/복원/재로드) 잡이 중복으로 쌓이지 않아야 한다.
- `stop()`: 걸어 둔 scriptJob을 `cmds.scriptJob(kill=..., force=True)`로 확실히 뗀다. `start()`가 한 번도 안 불렸으면(모듈 전역 잡 ID가 없으면) 아무 것도 안 하고 조용히 반환한다 — 플러그인 언로드 시 창을 연 적이 없어도 항상 이 함수를 부르기 때문이다.
- **생명주기**: `maroMainWindow.buildUI()`가 두 뷰포트를 만든 직후 `maroRosProxy.start(VIEWPORT_NAME_MAYA, VIEWPORT_NAME_ROS)`를 부르고, `workspaceControl`이 닫히거나(`-closeCommand`) 플러그인이 언로드될 때(`MaroPluginMain.cpp`) `maroRosProxy.stop()`을 반드시 부른다. Phase 0-1/2에서 그렇게 조심했던 "언로드 후에도 살아있는 콜백/스레드"가 여기서도 최우선 위험이다 — `_onIdle`이 언로드된 뒤에도 불리면 사라진 커맨드(`maroMayaToRos` 등)를 찾다가 에러를 내거나, 최악의 경우 Maya가 불안정해질 수 있다. 두 경로(창 닫기, 플러그인 언로드) 모두에서 `stop()`을 부르는 이중 안전장치를 둔다(둘 다 불려도 멱등이라 무해).
- **`_onIdle()`**: 좌측 격리 목록 갱신(§7) → 대상 결정(§4) → 대상이 없으면(선택도 없고 고정도 없음) 아무 것도 안 함(기존 프록시가 있으면 지움) → 있으면 `cmds.xform(target, q=True, ws=True, translation=True)`로 위치를, `maya.api.OpenMaya`(`om2.MFnTransform.rotation(om2.MSpace.kWorld, asQuaternion=True)`)로 월드 회전 쿼터니언을 얻음 → `maroMayaToRos` 호출 → `maroRosProxy_grp` 안의 로케이터(없으면 생성)에 결과를 적용.

## 7. 격리(`isolateSelect`) 설정 — 라이브 갱신

`isolateSelect`의 격리 목록은 스냅샷이다(씬이 바뀐다고 자동으로 안 늘어난다). 그런데 사용자는 "창을 연 뒤에 오브젝트를 만들어도 좌측에 바로 보여야 한다"고 요구했으므로, 격리 목록을 **매 idle 틱마다 갱신**한다 — 마침 프록시 동기화용으로 idle 콜백을 하나 두기로 했으니(§6), 그 콜백이 좌측 격리 목록 갱신도 같이 맡는다(스크립트잡을 하나 더 만들지 않는다).

- **우측(ROS) 패널**: `maroRosProxy_grp` 하나만 격리 목록에 넣는다 — 이 그룹 이름은 고정이라 `start()` 시점에 한 번만 추가하면 된다.
- **좌측(Maya) 패널**: 매 idle 틱마다 `cmds.ls(assemblies=True)`(씬의 최상위 오브젝트 전부)를 훑어서, `maroRosProxy_grp`를 제외한 나머지를 전부 `isolateSelect(mayaPanel, addDagObject=obj)`로 추가한다. 이미 격리 목록에 있는 오브젝트를 다시 추가해도 무해(멱등)하므로, 매번 새로 생긴 것만 골라내는 대신 전체를 다시 훑어도 안전하다 — 씬 오브젝트 수가 워킹 스켈레톤 규모에서는 이 반복 비용이 무시할 만하다(나중에 오브젝트가 많아지면 `DagObjectCreated` 콜백 등으로 바꿀 수 있음, 지금은 범위 밖).

```python
# maroRosProxy.py의 idle 콜백 안 (의사코드, 정확한 isolateSelect 플래그는 구현 중 확인)
def _onIdle():
    _refreshMayaIsolation()  # 좌측: 프록시 그룹만 빼고 매번 다시 추가
    _syncProxy()             # §6의 변환+로케이터 갱신
```

**scriptJob 소유권**: 이 idle 콜백(격리 갱신 + 프록시 동기화 둘 다)은 `maroRosProxy.py`가 소유한다. `maroMainWindow.py`는 `maroRosProxy.start(mayaPanelName, rosPanelName)`를 두 뷰포트 이름과 함께 부르기만 하고, `maroRosProxy.stop()`으로 멈춘다 — 두 모듈이 서로를 import하는 순환 참조를 피하기 위해 패널 이름은 하드코딩 문자열 중복 없이 인자로 전달한다.

## 8. 테스트 전략

Phase 0-1/2와 같은 한계: mayapy 배치 모드로는 "커맨드가 등록되고 계산 결과가 맞는지"까지만 자동 확인 가능하다. `maroMayaToRos`의 변환 로직 자체는 이미 `maro_transform`의 gtest(`test_convert.cpp`)로 검증돼 있으므로, 새 커맨드 테스트는 "커맨드가 그 이미 검증된 함수를 올바른 인자로 부르는지"만 확인하면 된다(배치에서 실행 가능 — DG 편집이 아니라 순수 계산이므로 `modelPanel`과 달리 배치 모드 제약이 없다). `isolateSelect`가 실제로 패널별로 독립 작동하는지, 로케이터가 실제로 우측에만 보이는지는 대화형 Maya 수동 체크리스트로 확인한다.

## 9. 범위 밖 (다음 단계)

- 여러 오브젝트 동시 동기화(Phase 5 노드 바인딩과 함께).
- `maroRosToMaya`(역방향 변환) — 필요해지면 추가.
- 프록시 로케이터를 실제 조인트 계층 구조로 표현(Phase 4 스켈레톤 업로드와 연결).
- 동기화 주기 최적화(지금은 idle 콜백, 필요하면 `MDagMessage::addWorldMatrixModifiedCallback`로 전환 — Phase 0-1 설계 스펙 §1.3에 이미 기록된 대안).

## 10. 전역 제약

- 빌드는 항상 `--config Release`를 명시한다.
- `ctest --test-dir out/build -C Release --output-on-failure`는 전부 통과해야 한다(사전 결함 없음).
- 새 `.py`는 `setStyleSheet()`를 호출하지 않는다(이번 단계는 UI 위젯을 안 만들지만, 규율은 유지).
- scriptJob은 `maroMainWindow`의 열림/닫힘, 플러그인 로드/언로드와 생명주기를 정확히 맞춘다 — 이 프로젝트가 지금까지 콜백/스레드 정리에 기울여 온 주의와 같은 수준으로 다룬다.
- `maroMayaToRos`는 `maro_transform`의 기존 순수 함수를 그대로 재사용한다 — 변환 수식을 다시 구현하지 않는다.
