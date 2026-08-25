# Maro 메인 UI Phase 4 — 노드 바인딩 + capability 에디터 설계 (2026-08-25)

## 1. 배경

Phase 3(`2026-08-25-maro-main-ui-phase3-ros-proxy-design.md`)에서 우측 뷰포트가 실제 ROS 좌표계 프록시를 보여주는 것까지 코드 완료됐다(사용자 수동 체크리스트 진행 중). 지금 유일한 축/capability 편집 방법은 `cmds.createNode("maroRotation")` + `cmds.connectAttr(...)` 수작업뿐이다 — Maro Main UI에 이걸 대체할 authoring 패널을 추가하는 것이 이번 단계다.

원 설계 문서(`2026-08-13-maya-ros2-axis-node-robotization-design.md`)가 S3(노드 그래프 에디터)라고 부른 것이 로드맵상 이 Phase로 흡수됐다. 브레인스토밍 중 사용자가 "capability 노드 종류를 늘려서 정밀한 움직임까지 합성 가능하게 하자"는 방향을 명확히 해서, 이번 단계는 원래 계획(기존 4종 편집 UI만)보다 범위가 커졌다 — 새 capability 노드 3종(직선 관절, 직선 리밋, 기어비/연동)이 이번에 함께 추가된다.

**장기 동기(참고, 이번 범위 아님)**: 사용자는 앞으로 모션캡쳐/애니메이션 데이터에서 동작을 읽어 자동으로 capability 노드를 배치하는 기능을 구상 중이다. 이게 `maroCoupling`의 비선형 곡선을 외부 Maya 커브 노드에 위임하지 않고 자체 데이터로 내장하기로 한 이유다(자동화 파이프라인이 우리 노드 데이터에 직접 쓸 수 있어야 함).

## 2. 이번 단계가 증명하는 것

지금까지 이 축·capability 시스템(S1)은 순수 DG 데이터 계약으로만 존재했고, 그걸 조작하는 유일한 방법은 스크립트 수작업이었다. 이번 단계는 그 데이터 계약을 그대로 유지한 채(설계 철학: "Maya DG가 유일한 진실") 위에 얇은 편집 UI를 얹어도 되는지 증명한다. 동시에 capability 타입 자체를 확장해서(회전만 되던 걸 직선/기어비까지) 이 아키텍처(축 하나 = 자유도 하나, capability 스택으로 성격 결정)가 실제로 확장 가능한지도 검증한다.

## 3. capType 확장

`maroAxis.aCapabilityIn`의 `capType`(short)이 지금 0~3(rotation/limit/sensorDirection/sensorRange)인데, 이번에 3개를 더한다:

| capType | 이름 | 역할 | 1차 구동값인가 |
|---|---|---|---|
| 4 | translation | 직선 구동값 | 예 |
| 5 | translationLimit | 직선 리밋 | 아니오(클램프만) |
| 6 | coupling | 기어비/연동(선형+비선형) | 예 |

**1차 구동값 상호배타 규칙(신규)**: 한 축의 capability 스택에 rotation(0)/translation(4)/coupling(6) 중 **정확히 하나만** 있을 수 있다(0개도 허용 — 아직 구동 안 하는 축). 물리적으로 축 하나는 자유도 하나이므로 두 개의 "1차 구동값"이 동시에 존재하면 모순이다. `maroAddCapability`/`maroConnectCapability`가 이 규칙을 검증하고 위반 시 거부한다(`BoadMaro::error`).

## 4. 새 capability 노드 3종

`MaroCapabilityNodes.h/.cpp`에 추가한다(기존 4종과 같은 파일 — 전부 "축에 쌓이는 능력 노드"라는 같은 성격이고, 공유 `CapabilityOutAttrs` 구조체를 그대로 재사용하므로 별도 파일로 가를 이유가 없다).

### `MaroTranslationNode`
- `aDistance` — `MFnUnitAttribute::kDistance`(AE: cm/m 등 UI 단위, 내부: 씬 단위가 아니라 센티미터 고정 — Maya의 `kDistance` 내부 단위 규약을 그대로 따름). `MaroRotationNode.aAngle`과 정확히 같은 역할, 단위만 각도→거리.
- `capabilityOut.capType = 4`, `capValue = aDistance`(내부 단위 그대로 double로 전달 — `MaroRotationNode`가 라디안을 그대로 전달하는 것과 같은 관례).

### `MaroTranslationLimitNode`
- `aMinX/aMaxX/aMinY/aMaxY/aMinZ/aMaxZ` — 전부 `MFnUnitAttribute::kDistance`(`MaroLimitNode`와 완전히 같은 구조, 단위만 각도→거리). **`MaroLimitNode`를 재사용하지 않는 이유**: 그 노드의 min/max 필드가 이미 `kAngle`로 고정돼 있어서, 직선 리밋에 그대로 쓰면 Attribute Editor에 입력한 숫자가 도(degree)로 오인된다.
- `aEnableX/aEnableY/aEnableZ` — `MaroLimitNode`와 동일.
- `capabilityOut.capType = 5`.

### `MaroCouplingNode`
> **[2026-08-25 최종 리뷰 수정 후 정정]** 아래 `aSourceValue`를 "double"로 적었던
> 최초 설계는 실제로는 unit-safe하지 않다는 게 최종 리뷰(C-1)에서 밝혀졌다 —
> unit 타입 어트리뷰트(`outValue`/`outValueLinear`)와 평범한 double 사이를
> connectAttr로 이으면 Maya가 현재 UI 단위 기준으로 자동 변환을 끼워 넣어
> (양방향 다 마찬가지) 각도 축 연결 시 ~57배 오차가 났다(실측 확인).
> 구현은 `aSourceValue`를 `MFnUnitAttribute::kAngle`로 재선언하고,
> `aSourceValueLinear`(`kDistance`) + `aSourceIsLinear`(bool, `aOutputIsLinear`와
> 같은 패턴)를 추가해 계열별로 분리하는 쪽으로 수정됐다(`MaroCapabilityNodes.h`
> 참고 — as-built 소스가 최신이다). 그 결과 **`capabilityOut.capValue`(평범한
> double)는 더 이상 `sourceValue`의 유효한 연결 소스가 아니다** — 반드시
> 축의 실제 `outValue`/`outValueLinear`에서 연결해야 한다.
- `aSourceValue`(double) — 다른 축의 `outValue` 또는 `outValueLinear`에 사용자가 직접 `connectAttr`로 연결(§6 참고 — `maroBindAxis`가 값 연결을 자동화하지 않는 기존 관례를 그대로 따름).
- `aRatio`(double, 기본 1.0), `aOffset`(double, 기본 0.0) — 곡선이 없을 때 `capValue = aSourceValue * aRatio + aOffset`.
- `aCurvePoints`(compound array: `aCurveInput` double, `aCurveOutput` double, `setStorable(true)`, `setIndexMatters(false)` — 순서가 아니라 `curveInput` 값으로 정렬해서 보간하므로 논리 인덱스 순서는 의미 없음) — **2개 이상 있으면 곡선 보간이 ratio/offset을 대체**한다.
  - 보간: `compute()`에서 `curveInput` 기준 오름차순 정렬 후 piecewise-linear. `aSourceValue`가 곡선 범위 밖이면 가장 가까운 끝점 값으로 고정(외삽 안 함 — 로봇 관절값이 정의역 밖에서 발산하면 안전 문제로 이어지므로).
  - v1은 piecewise-linear만 지원한다(스플라인/탄젠트 없음) — 곡선 편집 UI 자체가 이번 범위 밖(§9)이라 스크립트로 점을 넣는 지금 단계에서 탄젠트까지 다루는 건 과합.
- `capabilityOut.capType = 6`.

### 새 `MTypeId`
설계 시점(`MaroPluginMain.cpp` 등록 목록 기준) 다음 미사용 ID는 `0x00135107`부터다. 구현 시점에 다시 확인한다(그 사이 다른 브랜치가 병합됐을 수 있음 — 이 프로젝트의 기존 규율).
- `MaroTranslationNode::id = 0x00135107`
- `MaroTranslationLimitNode::id = 0x00135108`
- `MaroCouplingNode::id = 0x00135109`

## 5. `maroAxis` 변경

### 새 출력 `aOutValueLinear`
`aOutValue`(`MFnUnitAttribute::kAngle`)는 일부러 각도 타입으로 고정돼 있다(`rotateX` 같은 네이티브 어트리뷰트에 연결할 때 Maya가 라디안을 UI 단위로 오인하는 사고를 막기 위해, `MaroAxisNode.cpp:169-173` 주석 참고). 직선 구동값을 같은 어트리뷰트에 담으면 정반대 방향의 같은 사고가 난다(거리를 각도로 오인). 그래서 새 출력을 추가한다:

- `aOutValueLinear` — `MFnUnitAttribute::kDistance`, `storable(false)`, `writable(false)` — `aOutValue`와 완전히 같은 성격, 단위만 다름.

### `compute()` 확장
현재 루프(capType 순서대로 스택을 훑으며 `value`를 갱신)를 그대로 유지하고 분기만 늘린다:

```cpp
if (capType == 0) {            // rotation (기존)
    value = rosDriven ? aRosCommand : capValue;
    isLinearDrive = false;
} else if (capType == 4) {     // translation (신규)
    value = rosDriven ? aRosCommand : capValue;
    isLinearDrive = true;
} else if (capType == 6) {     // coupling (신규) -- ratio/curve는 노드 자신의 compute()가 이미 계산해서 capValue로 넘겨준다
    value = capValue;
    isLinearDrive = /* 연결된 sourceValue가 outValueLinear에서 왔는지로 판단 -- 구현 중 확정,
                        가장 간단한 방법은 coupling 노드에 outputIsLinear(bool) 플래그를
                        capabilityOut에 추가해서 명시적으로 전달하는 것 (아래 §7 열린 질문) */
} else if (capType == 1) {     // limit (기존, 회전 계열 클램프)
    ...(기존 그대로)
} else if (capType == 5) {     // translationLimit (신규, 직선 계열 클램프)
    ...(limit과 동일 로직, min/max만 다른 필드에서 읽음)
}
```

마지막에 `isLinearDrive`에 따라 `aOutValue` 또는 `aOutValueLinear` 중 실제로 구동된 쪽에만 값을 쓰고, 나머지 하나는 0으로 clean 처리한다(§3의 상호배타 규칙 덕분에 항상 둘 중 하나만 의미 있는 값을 가짐).

**`aCapabilityIn` 상호배타 규칙 위반이 이미 씬에 존재하는 경우**(예: 스크립트로 직접 `connectAttr`해서 규칙을 우회한 경우) — `compute()`는 이걸 에러로 취급하지 않고 "먼저 나온 1차 구동 타입이 이긴다"로 조용히 처리한다(커맨드 레벨 검증은 새 커맨드로 편집할 때만 막을 수 있고, DG 자체는 항상 방어적으로 짜여 있어야 한다는 이 프로젝트의 기존 원칙).

## 6. `MaroPump::collectSamples` 변경

`/joint_states` 발행 시 지금은 무조건 `aOutValue`(라디안)를 읽는다. 축이 직선 구동이면 `aOutValueLinear`를 읽어서 미터로 변환(`SceneUnit`, 기존 `mayaToRosPosition`이 쓰는 것과 같은 변환 상수) 후 발행하도록 분기를 추가한다. `sensor_msgs/JointState.position`은 조인트 타입 무관하게 같은 필드를 쓰므로(라디안이든 미터든), 메시지 스키마 변경은 없다 — 어느 쪽 출력을 읽을지 판단하는 분기만 추가된다.

## 7. `MaroBindAxisCommand`는 변경 없음

값 연결(`outValue`/`outValueLinear` → `rotateX`/`translateX` 등)은 지금도 사용자가 수동 `connectAttr`로 하는 방식이고(`maroBindAxis`는 `targetObject` message 연결만 담당, `aOutValue`를 자동으로 아무 데도 연결하지 않는다 — `MaroCommands.cpp` 확인됨), `maroTranslation`/`maroCoupling`도 같은 관례를 그대로 따른다. 자동 배선 커맨드는 이번에 만들지 않는다(YAGNI — 필요해지면 별도 계획).

**열린 구현 세부사항 — 해결됨**: `maroCoupling`이 `outValue`(각도)에서 왔는지 `outValueLinear`(거리)에서 왔는지는 `aOutputIsLinear`(bool)로 명시적으로 알려주는 방식으로 확정됐다(§4 그대로). 다만 그 과정에서 최종 리뷰(C-1)가 입력 쪽(`aSourceValue`)도 같은 문제(unit 안전성)를 가지고 있음을 발견해, **입력도 출력과 대칭으로** `aSourceValue`(kAngle)/`aSourceValueLinear`(kDistance)/`aSourceIsLinear`(bool)로 분리했다 — 위 §4 정정 박스 참고.

## 8. 새 커맨드 (`src/maro_plugin/MaroAxisEditorCommands.h/.cpp`, 신규 파일 쌍)

`MaroCommands.cpp`에 합치지 않는다 — 이미 그 파일은 크고, 이 프로젝트는 서브시스템당 파일 쌍 하나 관례를 지킨다(`MaroRosProxyCommands`, `MaroPanelCommands`, `MaroRemedyCommands`와 같은 이유).

- **`maroListAxisNodes`** — 쿼리 전용. 플래그 없으면 축 1개당 1행(`AXIS_FIELDS = 8`: `axisFullPath, jointName, boundTargetPath, parentAxisPath, controlMode, enabled, conventionAxis, capabilityCount`). `-capabilities <axis>`면 그 축의 capability 슬롯별 1행(`CAPABILITY_FIELDS = 5`: `logicalIndex, capabilityNodeName, capabilityNodeType, capType, connected`).
  - `MItDependencyNodes(MFn::kPluginLocatorNode)` + `typeId() == MaroAxisNode::id` 필터로 순회.
  - `aCapabilityIn`은 `evaluateNumElements()` + `elementByPhysicalIndex()`로만 순회(`elementByLogicalIndex()`는 빈 원소를 만들어내 쿼리가 씬을 변형시킨다).
  - `aTargetObject`는 message라 `connectedTo(sources, asDst=true, false)`로 역추적.
- **`maroAddCapability -type <rotation|translation|limit|translationLimit|sensorDirection|sensorRange|coupling> <axis>`** — undoable. `createNode`+`connect`를 한 `MDGModifier`로. §3의 상호배타 규칙 검증. 새 노드 이름을 `setResult`.
- **`maroConnectCapability <capabilityNode> <axis> [-index <int>]`** — undoable. 기존 capability 노드를 연결(§3 규칙도 동일 적용). `maroAddCapability`와 `nextFreeCapabilitySlot()` 헬퍼 공유.
- **`maroDisconnectCapability <axis> -index <int>`** — undoable, 직접 역연산.
- **`maroUnbindAxis <axis>`** — undoable, `maroBindAxis`의 역연산(`targetObject` message 커넥션 disconnect).

다섯 커맨드 전부 `MaroBindAxisCommand` 템플릿(`ScopedCommandContext`, `try/catch` 경계, `BoadMaro::error(siteTag, message, onfix::capture(...), remedy)`, `isUndoable()`가 `m_stagedChange` 반영) 그대로 따른다.

**곡선 점 편집은 커맨드를 만들지 않는다** — `aCurvePoints`는 그냥 데이터 배열이라 특별한 원자성/검증이 필요 없다. 일반 `cmds.setAttr("coupling1.curvePoints[0].curveInput", 0.5)` 같은 표준 Maya 편집으로 충분하다(불필요한 커맨드를 만들지 않는 이 프로젝트 관례).

**이번 범위에서 뺀 것**: `maroSetCapabilityOrder`(리오더링 — 전체 연결 셋을 원자적으로 재배선해야 해서 더 어렵고, 루프를 닫는 데 필수가 아님).

수정 파일: `MaroPluginMain.cpp`(신규 노드 3종 + 커맨드 5종 등록/역순 해제), `src/maro_plugin/CMakeLists.txt`, `tests/CMakeLists.txt`.

## 9. Python UI

### `python/maroAxisPanel.py` (신규)

PySide6 위젯(capability 스택은 트리/리스트가 필요해서 `cmds.textScrollList`로는 부족). `maroDiagPanel.py`처럼 flat-array→dict 변환은 순수 함수(`sliceAxisRows`/`sliceCapabilityRows`)로 분리해 mayapy 배치 테스트로 계약 검증. `setStyleSheet()` 금지(기존 규율).

- 축 목록(왼쪽) — `maroListAxisNodes` 결과. 행 클릭 시:
  - 그 축의 capability 스택을 오른쪽에 표시(`maroListAxisNodes -capabilities`).
  - **씬 선택도 같이 바뀐다**(바인딩된 타겟 오브젝트를 `cmds.select`) — 양방향 동기화.
- capability 스택(오른쪽) — 각 행에 삭제 버튼(`maroDisconnectCapability` 호출).
- "+Rotation / +Translation / +Limit / +TranslationLimit / +SensorDirection / +SensorRange / +Coupling" 버튼 7개 — 각각 `maroAddCapability -type ... <선택된 축>` 호출.
- 축 목록에 unbind 버튼(`maroUnbindAxis`).

### `python/maroMainWindow.py` 레이아웃 재구성

`vertical3`로 가지 않고 바깥 pane으로 한 겹 감싼다:

```
formLayout(form)
├── PySide6 테스트 버튼 (그대로, 이번에 안 건드림)
└── paneLayout("vertical2") outerPane          ← 신규, form의 자식이 pane 대신 이걸로 바뀜
    ├── paneLayout("vertical2") viewportPane   ← 기존 `pane` 그대로, 내부 불변
    │   ├── Maya 뷰포트
    │   └── ROS 뷰포트
    └── formLayout editorHost                  ← 신규
        └── [maroAxisPanel 위젯, MQtUtil로 임베드]
```

`_buildLabeledViewport`는 `viewportPane`을 받는 것 말고는 코드가 안 바뀐다. 임베드는 이미 증명된 두 단계(`MQtUtil.findLayout` → `addWidgetToMayaLayout` → `attachForm` 4면)를 그대로 재사용.

### `maroMainWindow.teardown()` 도입

지금은 `closeCommand` 문자열과 `MaroPluginMain.cpp`가 각각 `maroRosProxy.stop()`을 따로 부른다. 새 서브시스템(이번엔 선택 동기화 job)마다 이 두 곳을 또 늘리지 않도록, 모든 서브시스템의 `stop()`을 모아 부르는 `teardown()`을 만들고 `closeCommand`(문자열 형태 유지)와 C++ 언로드 경로 둘 다 이걸 가리키게 한다. **Phase 3 수동 체크리스트 통과 이후에 적용한다**(리뷰 세 번 거친 Phase 3 코드에 대한 애디티브 수정이므로) — 단, 이번 세션은 사용자가 "테스트는 나중에 한 번에" 결정을 이미 내렸으므로, 실제 적용 순서는 구현 순서와 무관하게 진행하고 최종 수동 검증에서 Phase 3+4를 함께 확인한다.

### `SelectionChanged` 동기화 job

`maroRosProxy`의 idle job과 별개로 새 `scriptJob(event=["SelectionChanged", callback], protected=True)`를 둔다(초당 수십 번 도는 idle에 얹지 않고, 선택이 바뀔 때만 도는 게 맞는 이벤트이므로). `start()`에서 멱등, `teardown()`에서 kill, 두 경로(창 닫기/언로드) 모두에서 도달 가능해야 한다(Phase 0-1/2/3이 매번 겪은 "주인 없는 콜백" 실패 유형을 반복하지 않는다).

## 10. 테스트 전략

- `tests/maya/test_axis_editor_commands.py` (신규) — 완전 배치 테스트 가능(DG 편집 + 쿼리, `modelPanel` 불필요):
  - `maroListAxisNodes` 양쪽 모드
  - `maroAddCapability` 7종 전부 + undo/redo
  - §3 상호배타 규칙 위반 거부(rotation 있는 축에 translation 추가 시도 등, 6가지 조합)
  - `maroConnectCapability`/`maroDisconnectCapability`/`maroUnbindAxis` + undo/redo
  - `maroCoupling`의 ratio/offset 수식 정확성, 곡선 보간 정확성(2점/3점 이상, 정의역 밖 클램프)
  - `maroTranslation` 축의 `aOutValueLinear` 라우팅(값이 `aOutValue`가 아니라 여기로 감)
- `MaroPump`의 `/joint_states` 발행 분기(직선축 → `outValueLinear` 읽기) — 기존 `test_publish.py`/`test_lidar_publish.py` 근처에 케이스 추가.
- `maroAxisPanel.py`의 순수 함수(`sliceAxisRows`/`sliceCapabilityRows`) 테스트.
- 대화형 Maya 수동 체크리스트(신규 절) — 패널 표시, 버튼 클릭, 양방향 선택 동기화, 레이아웃 재구성 후 Phase 2 §1-1/§3 재확인(사용자 결정에 따라 Phase 3 체크리스트와 함께 한 번에 실행).

## 11. 범위 밖 (다음 단계)

- **곡선 그래프 편집 UI**(드래그로 점 추가/삭제, 실시간 미리보기) — 사용자가 명시적으로 분리 결정. `aCurvePoints`는 이번에 스크립트/`setAttr`로만 편집 가능.
- **비선형 곡선의 스플라인/탄젠트 지원** — v1은 piecewise-linear만.
- **`maroSetCapabilityOrder`**(capability 재배열).
- **모션캡쳐/애니메이션에서 자동으로 축·capability를 추출·배치하는 기능** — 장기 방향(§1 참고), 이번엔 그 데이터 모델(자체 내장 곡선)만 준비해 둔다.
- **자동 값 연결 커맨드**(`outValue`→네이티브 트랜스폼 채널 자동 배선) — 지금처럼 수동 `connectAttr` 유지.

## 12. 전역 제약

- 빌드는 항상 `--config Release`를 명시한다.
- `ctest --test-dir out/build -C Release --output-on-failure`는 전부 통과해야 한다(사전 결함 없음).
- 새 `.py`는 `setStyleSheet()`를 호출하지 않는다.
- 새 커맨드 5종 전부 `MaroBindAxisCommand`의 undoable 패턴(`MDGModifier`, `ScopedCommandContext`, `BoadMaro::error`)을 그대로 따른다.
- `aCapabilityIn` 순회는 항상 `elementByPhysicalIndex()`만 쓴다(`elementByLogicalIndex()` 금지 — 쿼리가 씬을 변형시키는 사고 방지).
- scriptJob(선택 동기화)은 `maroMainWindow`의 열림/닫힘, 플러그인 로드/언로드와 생명주기를 정확히 맞춘다.
- 새 노드 3종의 `MTypeId`는 구현 시작 시 `MaroPluginMain.cpp`의 실제 등록 목록을 다시 확인해서 충돌 없는 값을 쓴다(§4의 값은 설계 시점 기준 참고값).
