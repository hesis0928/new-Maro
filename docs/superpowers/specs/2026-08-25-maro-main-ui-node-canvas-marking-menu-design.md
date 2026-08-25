# Maro 메인 UI — 노드 캔버스 + 방사형 마킹 메뉴 재설계 (2026-08-25, v2)

## 1. 배경

Phase 4(`2026-08-25-maro-main-ui-phase4-axis-capability-editor-design.md`)는 축 목록(`QListWidget`) + capability 스택 목록(`QListWidget`) + 타입별 추가 버튼 7개로 구성된 `maroAxisPanel.AxisPanel`을 구현하고 리뷰까지 마쳤다. 사용자가 대화형 Maya에서 실제 창을 띄워 보니 이 레이아웃이 쓰기 불편했고, 브레인스토밍을 거치며 요구사항이 여러 단계로 확장됐다:

1. (v1) 레이아웃: 뷰포트 상단 / 편집 영역 하단.
2. (v1) capability 추가를 Maya 뷰포트의 vertex/edge/face 마킹 메뉴와 동일한 우클릭-홀드-드래그-릴리즈 방사형 메뉴로.
3. (v1) 캔버스 모델: 모든 축이 한 캔버스에 동시에 보이고, 우클릭으로 그 자리에 축/능력을 만드는 완전한 노드 그래프 에디터.
4. **(v2, 이 개정) 진입점 자체를 MaroUI에서 Maya 네이티브 오브젝트 마킹 메뉴로 옮긴다.** Maro 플러그인이 로드돼 있으면(MaroUI를 열었든 안 열었든) 씬의 아무 오브젝트나 우클릭했을 때 나오는 네이티브 마킹 메뉴(사용자가 캡처해 보여준 Vertex/Edge/Face/Object Mode/UV/Multi 메뉴)에 `Maro node editor` 항목이 추가되고, 그걸 고르면 그 오브젝트 전용 팝업 노드 에디터가 뜬다. 다른 축과의 연결(예: Coupling의 소스 축)은 그 팝업 안의 드롭다운으로 처리한다. MaroUI 안에는 이 모든 팝업을 한눈에 조망하고 다시 열 수 있는 상위 뷰를 남겨 둔다.

이 v2는 v1이 정했던 세부 상호작용(마킹 메뉴 중첩/반투명, Delete가 능력만 지우고 노드는 남기는 것, 2개 이상 쌓이면 드롭다운으로 접히는 것)은 대부분 그대로 재사용하되, **적용 범위를 "캔버스 전체"에서 "축 하나"로 좁히고, 그 결과 캔버스 좌표 저장/빈 캔버스 클릭/`Axis` 메뉴 항목이 전부 불필요해진다.** C++ 쪽은 Phase 4가 만든 커맨드 5종 + 기존 `maroBindAxis`를 그대로 재사용하고, `maroAxis`에 표시용 속성(이름/색상) 2개만 추가한다.

## 2. 세 계층 구조

| 계층 | 약칭 | 위치 | 역할 |
|---|---|---|---|
| 네이티브 마킹 메뉴 진입점 | — | Maya 뷰포트, `dagMenuProc` 확장 | 오브젝트 우클릭 → `Maro node editor` 항목 |
| 싱글 오브젝트 노드 에디터 | **SONE** | 독립 팝업 창(MaroUI와 무관, MaroUI 안 열어도 뜸) | 축 하나의 capability 스택을 마킹 메뉴로 편집 |
| 오브젝트 노드 에디터 | **ONE** | MaroUI 하단 패널(v1 §2 레이아웃 그대로 유지) | 지금까지 만들어진 SONE들을 각각 노드 하나(**GSON**, Grouped Single Object Node)로 그루핑해 조망, 더블클릭으로 해당 SONE 재오픈 |

세 계층의 관계: **SONE이 진짜 편집 화면**이고, **ONE은 SONE들의 목록/재진입 창구**다. 축 하나를 처음 만들 때만 네이티브 메뉴 → 이름/색 지정 → SONE 순서를 거치고, 이후에는 네이티브 메뉴에서 바로 그 SONE가 뜨거나, ONE에서 해당 GSON을 더블클릭해도 같은 SONE가 뜬다(SONE는 축마다 유일하게 존재 — 이미 열려 있으면 새로 만들지 않고 그 창을 앞으로 가져온다, `maroMainWindow.CONTROL_NAME` 싱글턴 패턴과 같은 원리).

## 3. 네이티브 마킹 메뉴 확장

- Maya 오브젝트 마킹 메뉴는 전역 MEL 프로시저 `dagMenuProc` 하나가 만든다 — 이걸 그냥 덮어쓰면 Maya 기본 항목이나 다른 플러그인이 추가한 항목이 사라질 수 있다. 그래서 로드 시 **기존 `dagMenuProc`가 있으면 그 이름을 보존해 두고, 우리 버전은 그 기존 프로시저를 먼저 호출한 뒤 `Maro node editor` 항목 하나를 추가로 붙이는 방식**으로 만든다(체이닝). 언로드 시 원래 프로시저로 되돌린다 — 이 프로젝트가 지금까지 모든 서브시스템에 적용해 온 "언로드하면 흔적 없이 원상복구" 원칙을 여기도 그대로 적용한다.
- 메뉴 항목 클릭 시 그 시점에 마킹 메뉴가 열렸던 오브젝트(`dagMenuProc`에 인자로 들어오는 오브젝트 이름)를 타겟으로 아래 §4 흐름을 시작한다.
- **씬 아무 오브젝트에나 이 항목이 뜬다** — 아직 축이 안 걸린 오브젝트든, 이미 `maroAxis`가 바인딩된 오브젝트든 항목 자체는 항상 보인다(있는 오브젝트마다 다른 항목 이름/조건부 표시를 하지 않는다 — 눌러 보기 전엔 이미 바인딩됐는지 알 필요가 없게, 클릭 이후 로직이 분기).

## 4. 축 생성 — 이름/색 지정 → SONE

`Maro node editor` 클릭 시:

1. 그 오브젝트에 이미 바인딩된 `maroAxis`가 있는지 조회(`connectedTo`로 `targetObject` 역추적, 기존 관례 그대로).
2. **없으면(최초)**: 이름 입력(`cmds.promptDialog`, 기본값은 오브젝트 짧은 이름) + 색상 선택(`cmds.colorEditor`, 기본값은 미리 정해둔 팔레트에서 다음 순번) — 둘 다 Maya 네이티브 다이얼로그를 그대로 쓴다(새 커스텀 Qt 다이얼로그를 만들지 않는다, YAGNI). 확인하면 한 undo 청크(`cmds.undoInfo(openChunk=True/closeChunk=True)`) 안에서 `cmds.createNode("maroAxis")` → `maroBindAxis(axis, object)` → `aDisplayName`/`aDisplayColor` 설정을 실행한다. 취소하면 아무 것도 안 만든다.
3. **있으면**: 이름/색 단계를 건너뛰고 바로 그 축의 SONE를 연다(§5). 이미 그 축의 SONE 창이 떠 있으면 새로 만들지 않고 기존 창을 앞으로 가져온다.

## 5. SONE — 싱글 오브젝트 노드 에디터

독립 최상위 `QWidget` 팝업(모덜리스 — Coupling이 다른 축을 참조할 때 여러 SONE를 동시에 띄워 두고 비교할 수 있어야 하므로). 창 제목에 §4에서 지정한 표시 이름을 쓴다.

### 5.1 표시

팝업 안에는 이 축 하나의 capability 상태를 나타내는 노드가 **하나만** 있다(v1의 다축 캔버스와 달리 여기선 "축 이름 vs capability" 두 영역을 가를 필요도, 여러 축을 구분할 필요도 없다 — 창 자체가 이미 축 하나로 스코프됨). 표시 상태는 v1 §3.1의 capability 상태 표와 동일:

| 상태 | 표시 |
|---|---|
| 비어 있음 | `undefined`(점선 테두리) |
| 능력 1개 | 그 타입 이름 |
| 능력 2개 이상 | 대표 라벨 + 우측 `▾` |

### 5.2 마킹 메뉴 — 우클릭은 팝업 어디서나

팝업 안 **아무 데나** 우클릭한 채로 드래그하면(빈 공간이든 노드 위든 구분 없음 — 창 안에 편집 대상이 이 축 하나뿐이라 클릭 위치를 가릴 이유가 없다) 우클릭 지점을 중심으로 방사형 메뉴가 열린다. 릴리즈한 위치의 항목이 확정된다.

**항목은 7개 고정**(`Rotation`/`Translation`/`Limit`/`TranslationLimit`/`SensorDirection`/`SensorRange`/`Coupling`) — v1에 있던 `Axis` 항목은 **완전히 삭제**한다. 축 식별/바인딩은 이미 §4에서 오브젝트 우클릭으로 끝났으므로, SONE 내부에서 "어느 축인지" 또는 "새 축 만들기"를 다시 물을 이유가 없다.

리프를 골라 릴리즈하면 v1 §3.4와 동일하게 동작:
- `undefined` 상태였다면 `maroAddCapability(axis, type=...)`.
- 이미 능력이 있었다면 같은 커맨드로 다음 빈 슬롯에 추가(중첩).
- 1차 구동값 상호배타 규칙 위반 시 커맨드가 거부 → 팝업 하단에 짧은 오류 텍스트(v1 §3.5 그대로).

하위 옵션이 있는 항목을 위한 중첩/반투명/"◀ 상위로" 메커니즘(v1 §3.3)은 **컴포넌트 자체는 그대로 남겨 둔다**(범용으로 짜 둔 것 그대로) — 지금은 7개 다 리프라 실제로 중첩이 발생하지 않을 뿐, 향후 어떤 capability 타입이 하위 선택지를 가지게 되면 같은 경로를 탄다.

### 5.3 능력 제거/조회 (v1 §3.4 그대로 승계)

- Delete(접힌 상태) → 가장 나중에 추가된 능력 하나만 제거(`maroListAxisNodes(capabilities=axis)`로 최대 `logicalIndex` 조회 후 `maroDisconnectCapability(axis, index=그값)`). 능력이 1개였다면 `undefined`로 복귀.
- `▾` 클릭 또는 노드 더블클릭 → 쌓인 순서 목록 펼침/접힘 토글.
- 펼친 상태에서 개별 항목 선택 후 Delete → 그 항목만 `maroDisconnectCapability(axis, index=그 항목)`로 제거.

### 5.4 다른 축 연결 — Coupling의 소스 축

`Coupling` capability를 추가/펼치면 그 파라미터 편집 영역(속성 폼, 마킹 메뉴가 아닌 일반 위젯)에 **씬의 축 이름 드롭다운**이 있다 — `maroListAxisNodes()`로 조회한 전체 축 목록(표시 이름 우선, 없으면 축 노드 이름)에서 소스 축을 고른다. 고르면 그 축의 `outValue`/`outValueLinear`(축의 `aOutputIsLinear`/`aDriveIsLinear`에 따라 결정, Phase 4 §5/§7 규약 그대로)를 `aSourceValue`/`aSourceValueLinear` + `aSourceIsLinear`에 연결하는 `cmds.connectAttr` 시퀀스를 한 undo 청크로 실행한다. 뷰포트에서 다른 오브젝트를 따로 클릭/피킹하는 모드는 만들지 않는다(사용자 결정) — 축은 이미 이름이 있는 목록형 데이터이므로 드롭다운이 가장 직접적이다.

### 5.5 바인딩

- SONE 안에는 별도의 `Bind` 항목을 두지 않는다 — 바인딩은 §4에서 축 생성과 함께 이미 확정됐다.
- `Unbind`만 작은 메뉴/버튼으로 남긴다(`maroUnbindAxis(axis)`) — 축은 남기고 타겟 연결만 끊는 기존 유스케이스(예: 리깅을 바꾸는 중 임시로 떼어 두기)를 위해서다. 언바인드된 축을 다시 바인딩하려면 그 축이 원래 만들어졌던 것과 같은 경로(새 오브젝트를 우클릭 → `Maro node editor`)가 아니라, **v1처럼 씬 선택 기반 재바인딩 버튼은 이번에 만들지 않는다** — 재바인딩 유스케이스가 실제로 나오면 별도로 추가한다(YAGNI, 최초 흐름과 달리 이건 사용자가 아직 요청한 적 없는 기능).

## 6. ONE — 오브젝트 노드 에디터 (MaroUI 하단)

v1 §2의 MaroUI 레이아웃(메뉴바 + 뷰포트 상단 + 편집 영역 하단)은 그대로 유지한다 — 하단 `editorHost`에 임베드되는 위젯의 **내용**만 "다축 캔버스"에서 "GSON 그리드"로 바뀐다.

- 씬에 바인딩된 축(=SONE가 하나라도 만들어진 축)마다 GSON 노드 하나. 라벨 = `aDisplayName`, 색 = `aDisplayColor`.
- **더블클릭** → 그 GSON에 대응하는 SONE 팝업을 연다(이미 열려 있으면 앞으로 가져오기만).
- 우클릭 → 작은 컨텍스트 메뉴: `Rename`(이름 재입력, `promptDialog`), `Recolor`(`colorEditor`), `Delete`(그 축의 `maroAxis` 노드 자체를 완전히 삭제 — capability 노드까지 포함해 `cmds.delete`. SONE의 Delete 키가 "능력 하나만 제거"였던 것과 달리 이건 **축 전체 제거**이므로 별도 동작으로 명확히 구분한다).
- 레이아웃: GSON은 생성 순서대로 자동 그리드 배치(가로로 채우다 넘치면 다음 줄). **자유 드래그 재배치나 좌표 저장은 이번 범위 밖**(v1이 필요로 했던 캔버스 좌표 시스템 자체가 이 v2 구조에선 없다 — SONE 생성이 항상 뷰포트 오브젝트 우클릭에서 시작되므로 "빈 캔버스의 어디"라는 개념이 사라졌다).
- ONE 자체는 편집 기능이 없다(더블클릭으로 SONE를 열어야 실제 편집) — §2 표의 "조망 및 재진입 창구" 역할 그대로.
- **씬 선택 동기화는 승계한다**: 옛 `maroAxisPanel`의 `SelectionChanged` `scriptJob`(생명주기: `start()`에서 멱등 생성, `teardown()`에서 kill)을 그대로 옮겨 오되, 동작은 "리스트 행 하이라이트"에서 "해당 GSON 하이라이트(+필요하면 스크롤해서 보이게)"로 바뀐다. GSON 클릭 시 씬 선택을 바꾸는 반대 방향도 유지(바인딩된 타겟이 있으면 그것을 선택).

## 7. `MaroAxisNode` 신규 속성

- `aDisplayName` — `MFnTypedAttribute::kString`, `storable(true)`. `jointName`(ROS 조인트 이름, 발행에 실제로 쓰이는 기능적 필드)과는 별개의 순수 UI 라벨이다 — 둘을 합치지 않는 이유: `jointName`을 바꾸면 `/joint_states` 발행이 바뀌는데, GSON 라벨을 바꾸고 싶다고 그 발행까지 바뀌면 안 된다.
- `aDisplayColor` — `MFnNumericAttribute::createColor` (float3), `storable(true)`.
- 둘 다 `compute()`에 관여하지 않는다(v1의 `aCanvasPosX/Y`와 같은 성격 — 순수 UI 부기 데이터, `attributeAffects` 등록 대상 아님). **v1이 제안했던 `aCanvasPosX/Y`는 이번 v2에서 완전히 폐기한다** — ONE에 좌표 저장이 필요 없어졌으므로.
- `maroListAxisNodes`의 `AXIS_FIELDS`가 8 → 10으로 늘어난다(`displayName`, 색상 3개를 한 필드로 합쳐 보낼지 r/g/b 3필드로 나눌지는 구현 시 결정 — 커맨드가 이미 flat 문자열 배열을 쓰고 있으므로 색은 `"r,g,b"` 형식의 문자열 한 필드로 인코딩하는 편이 기존 계약과 더 잘 맞는다, 그러면 8 → 10 그대로).

## 8. 커맨드 재사용 (신규 C++ 커맨드 없음)

Phase 4가 만든 5개(`maroListAxisNodes`/`maroAddCapability`/`maroConnectCapability`/`maroDisconnectCapability`/`maroUnbindAxis`) + 기존 `maroBindAxis`를 그대로 쓴다. 이름/색 설정, 다른 축 연결, GSON 삭제는 전부 `cmds.setAttr`/`cmds.connectAttr`/`cmds.delete`의 조합이라 새 undoable 커맨드가 필요 없다(단순 속성 조작이라 원자성 요구가 낮다는 Phase 4의 기존 판단 그대로 승계, §8 원문 참고).

## 9. `python` 쪽 파일 구성

- `python/maroDagMenu.py`(신규) — `dagMenuProc` 체이닝 등록/해제. 플러그인 로드/언로드 생명주기에 정확히 물린다(`MaroPluginMain.cpp`의 initialize/uninitialize에서 각각 호출).
- `python/maroSingleObjectNodeEditor.py`(신규, SONE) — §5의 마킹 메뉴 상태 기계. v1에서 설계했던 `computeRadialLayout`/`hitTestRadialItem` 순수 함수는 그대로 여기로 옮겨 재사용한다(수학은 축 개수와 무관하므로 바뀔 이유가 없다).
- `python/maroObjectNodeEditor.py`(신규, ONE) — `buildWidget()`/`start()`/`stop()` 진입점 계약 유지, `maroMainWindow.py`의 임베드 코드는 이름만 `maroAxisPanel` → `maroObjectNodeEditor`로 바뀐다.
- `python/maroAxisPanel.py`는 **삭제**한다(리스트 기반 UI 전체가 ONE으로 대체되므로 남겨 둘 이유가 없다 — 죽은 코드를 유지하지 않는다).

## 10. 테스트 전략

- `tests/maya/test_axis_editor_commands.py` — `AXIS_FIELDS` 8→10 갱신, `aDisplayName`/`aDisplayColor` 왕복 케이스 추가.
- SONE/ONE 각각의 순수 함수(`computeRadialLayout`, `hitTestRadialItem`, GSON 그리드 배치 계산)는 mayapy 배치로 테스트. **`QWidget` 생성은 여전히 배치 테스트에서 하지 않는다**(기존 하드 제약 그대로).
- `dagMenuProc` 체이닝은 배치 테스트 불가(진짜 마킹 메뉴 렌더링 필요) — 대화형 수동 체크리스트에 새 절 추가: 로드 전/후 네이티브 메뉴에 항목이 있는지, 다른 플러그인이 추가한 기존 항목이 안 사라졌는지, 언로드 후 항목이 사라지고 원래 `dagMenuProc`으로 복원되는지.
- 대화형 수동 체크리스트: 최초 생성 흐름(이름/색 다이얼로그 → SONE), 재진입 두 경로(네이티브 메뉴 재클릭, ONE의 GSON 더블클릭)가 같은 창을 띄우는지(중복 생성 안 하는지), Coupling 드롭다운으로 다른 축 연결, ONE의 Rename/Recolor/Delete.

## 11. 범위 밖

- ONE 안 GSON의 자유 드래그 재배치/좌표 저장.
- SONE에서 재바인딩(다른 오브젝트로 타겟 교체) UI — Unbind까지만.
- Coupling 소스 축을 뷰포트에서 직접 피킹하는 모드(드롭다운으로 충분).
- `maroSetCapabilityOrder`, 곡선 그래프 편집 UI — Phase 4 §11에서 이미 범위 밖으로 뺀 것 그대로 유지.
- `dagMenuProc`가 없는(순수 커스텀 노드 타입 등) 오브젝트에 대한 처리 — 이번엔 표준 DAG 오브젝트(트랜스폼/셰이프)만 고려.

## 12. 전역 제약

- 빌드는 항상 `--config Release`, `ctest --test-dir out/build -C Release --output-on-failure` 전부 통과.
- 새/수정 `.py`는 `setStyleSheet()`를 호출하지 않는다.
- `aDisplayName`/`aDisplayColor`는 `compute()`에 관여하지 않는다 — `attributeAffects` 등록 대상 아님.
- `dagMenuProc` 체이닝은 로드 시 기존 프로시저를 반드시 보존하고, 언로드 시 반드시 원상복구한다 — 이 훅은 프로세스 전역(다른 플러그인과 공유)이므로 복원 실패가 다른 도구의 마킹 메뉴를 영구히 깨뜨릴 수 있다.
- `maroObjectNodeEditor.py`의 `buildWidget()`/`start()`/`stop()` 진입점 시그니처는 유지한다(`maroMainWindow.py`가 이 계약에 의존).
- `AXIS_FIELDS`가 8→10으로 바뀌므로 이를 참조하는 모든 곳(파이썬/C++ 양쪽 `maroListAxisNodes` 구현, 테스트)을 한 커밋 단위로 함께 고친다.
- SONE는 축마다 유일 인스턴스 — 이미 열려 있으면 재사용(중복 창 금지).
