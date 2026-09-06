# 카파빌리티 노드 상세 설정 UI 설계

## 배경

`python/maroSingleObjectNodeEditor.py`(SONE)는 축 하나의 capability 스택에
타입 추가/교체/삭제(방사형 마킹 메뉴)만 지원한다. capability 노드 7종
(Rotation/Translation/Limit/TranslationLimit/SensorDirection/SensorRange/
Coupling)의 실제 속성값을 편집하는 전용 UI는 없다 — Coupling의 소스 축
피커(`_showCouplingSourcePicker`, 생성 직후 1회성)를 빼면 전부 Maya 기본
Attribute Editor/Channel Box로 직접 만져야 한다.

이 스펙은 그 공백을 메우는 상세 설정 UI를 정의한다. 브레인스토밍 중 범위가
"패널 하나"에서 "Limit/TranslationLimit의 뷰포트 인터랙티브 캘리브레이션
도구"까지 크게 늘어났다 — 사용자가 명시적으로 "일단 하나의 큰 스펙으로
만들고 테스트 구동 후 필요하면 나누자"고 결정했으므로, 이 문서는 그 결정을
그대로 반영한 단일 스펙이다.

## 현재 capability 노드 속성 (`src/maro_plugin/MaroCapabilityNodes.h`)

| 타입 | 속성 |
|---|---|
| Rotation | `angle` (각도, kAngle) |
| Translation | `distance` (거리, kDistance) |
| Limit | `enableX/Y/Z`(bool) + `minX/maxX/minY/maxY/minZ/maxZ`(각도, 6개) — **이 스펙에서 재설계 대상** |
| TranslationLimit | `enableX/Y/Z`(bool) + `minX/maxX/minY/maxY/minZ/maxZ`(거리, 6개) — **이 스펙에서 재설계 대상** |
| SensorDirection | `direction` (float3) |
| SensorRange | `range`(거리) + `coneAngle`(각도) |
| Coupling | `sourceValue`/`sourceValueLinear`/`sourceIsLinear`/`ratio`/`offset`/`outputIsLinear` + `curvePoints`(가변 배열, 이번 범위 밖) |

## 1. 파일 구조 & 클래스 분리

- **`python/maroCapabilityPanel.py`** — 공통 베이스 클래스
  `MaroCapabilityPanelBase(QtWidgets.QWidget)`와 **노드 타입별 7개
  서브클래스**:
  - `MaroRotationPanel`, `MaroTranslationPanel`, `MaroSensorDirectionPanel`,
    `MaroSensorRangePanel`, `MaroCouplingPanel` — 단순 스핀박스 폼.
  - `MaroLimitPanel`, `MaroTranslationLimitPanel` — 위 5개와 같은 폼 뼈대에
    "움직임범위설정" 버튼이 추가되고, 그 버튼이 `maroLimitCalibration.py`의
    캘리브레이션 엔진을 연다.
  - 베이스 클래스가 공유하는 것: `_OPEN_EDITORS` 싱글톤(노드 풀 경로 키,
    `maroLidarPanel.py`/SONE과 동일 패턴), `stop()`(언로드 정리),
    "적용" 버튼 + `cmds.undoInfo(openChunk/closeChunk)`로 감싼 배치
    `cmds.setAttr` (커스텀 undoable 커맨드가 아니라 Maya 네이티브 undo에
    의존 — 값 수정은 노드 생성/연결과 달리 조합 undo가 필요 없음).
  - 진입점은 `openCapabilityPanel(capabilityNode)` 팩토리 함수 하나 —
    `cmds.nodeType(capabilityNode)`로 분기해 알맞은 서브클래스를 연다.
- **`python/maroLimitCalibration.py`** — Limit·TranslationLimit이 공유하는
  캘리브레이션 엔진(축 지정, 매니퍼레이터, 임시 시각화, HUD, collect).
  회전(각도)/이동(거리) 차이는 파라미터로 흡수.

## 2. SONE 더블클릭 통합

[maroSingleObjectNodeEditor.py:427-440](../../../python/maroSingleObjectNodeEditor.py)의
기존 `mouseDoubleClickEvent`는 capability 2개 이상일 때 위치 무관하게
펼치기/접기를 토글한다. 이 동작은 그대로 두고, 지금까지 아무 반응이 없던
지점에만 새 동작을 추가한다:

- **접힌 상태**(capability 정확히 1개)에서 중앙 노드 더블클릭 → 그 유일한
  capability의 상세 패널 열기. (지금은 이 클릭이 무동작.)
- **펼친 상태**에서 드롭다운의 특정 행 더블클릭 → 그 행의 capability 상세
  패널 열기. (신규)
- **펼친 상태**에서 행이 아닌 중앙 노드 더블클릭 → 기존처럼 접기. (변경 없음)
- capability 2개 이상, 아직 접힌 상태에서 중앙 노드 더블클릭 → 기존처럼
  펼치기. (변경 없음, 상세 패널은 열지 않음 — 어느 것을 열지 애매하므로)

## 3. 단순 5타입 패널

Rotation/Translation/SensorDirection/SensorRange/Coupling은
`maroLidarPanel.py`의 `_ATTRS`(attrName, label, kind) 패턴을 그대로
재사용한 스핀박스 폼 + 적용 버튼이다.

Coupling만 예외: `ratio`/`offset`/`outputIsLinear` 필드에 더해 "소스 축
재지정" 버튼을 두고, 클릭 시
[maroSingleObjectNodeEditor.py:377-421](../../../python/maroSingleObjectNodeEditor.py)의
`_showCouplingSourcePicker` 로직을 공유 헬퍼로 추출해 재사용한다(생성
직후 1회성이던 것을 "언제든 재연결" 가능하게 확장). `curvePoints` 배열
편집은 이번 범위 밖 — 후속 증분으로 미룬다.

## 4. `MaroLimitNode`/`MaroTranslationLimitNode` 스키마 재설계 (C++)

기존 X/Y/Z 3축 독립 구조(`aEnableX/Y/Z` + 6개 min/max)를 **완전히
교체**한다:

- `aAxisDirection` (float3, Maya 로컬/월드 공간의 정규화 방향 벡터)
- `aMin`, `aMax` (스칼라 — Limit은 각도/kAngle, TranslationLimit은
  거리/kDistance)

`compute()`를 "월드 회전(또는 이동)을 `aAxisDirection` 기준으로 투영한
값"을 `aMin`/`aMax`로 클램프하는 axis-angle(또는 axis-projection) 수식으로
재작성한다. 하나의 조인트를 여러 축에 동시에 제한하던 기존 방식(X도 걸고
Y도 거는 것)은 더 이상 불가능하다 — 그런 씬/테스트가 있다면 마이그레이션이
필요하다(정확한 개수는 플랜 작성 시 grep으로 집계).

**왜 이게 퇴보가 아닌가**: [python/maroUrdfExport.py](../../../python/maroUrdfExport.py)가
이 두 노드를 읽어 URDF `<limit>`을 만드는데, URDF 조인트 자체가 원래
"축 하나 + `lower`/`upper` 하나" 구조다. 기존 3축 동시 제한 모델은 애초에
URDF와 억지로 맞추던 것에 가까웠고, 이 재설계가 오히려 URDF 개념과
자연스럽게 일치한다.

### Maya→ROS 축 벡터 변환

이 프로젝트의 기존 좌표 변환 `(x,y,z) → (x,-z,y)`는 행렬식 +1인 순수
회전(반사 아님)이라, **회전각 자체는 이 변환에 불변**이다(직교변환에 의한
켤레는 각도를 보존한다: `R·Rot(A,θ)·R⁻¹ = Rot(R(A),θ)`). 따라서:

- `aMin`/`aMax`(각도 라디안 값)는 ROS로 넘길 때 변환이 **필요 없다**.
- `aAxisDirection`은 Maya 공간 벡터로 노드에 저장해두고, ROS/URDF로
  내보낼 때 위치 벡터와 같은 원리(이동 성분 없는 회전만 적용)의 변환을
  거쳐야 한다. 기존 `mayaToRosPosition`류 함수 옆에 방향 벡터 전용 변환
  헬퍼를 추가한다(이동 성분이 없다는 점만 다름).

## 5. 캘리브레이션 워크플로 (Limit 기준 — TranslationLimit은 회전↔이동만 교체)

1. 상세 패널에서 "움직임범위설정" 클릭 → **축 지정 모드** 진입: 뷰포트에서
   메쉬 표면/버텍스 두 점을 클릭 → 그 방향이 `aAxisDirection`으로 설정되고,
   그 방향으로 정렬된 헬퍼 로케이터가 생성된다.
2. 헬퍼 로케이터를 기준으로 **Maya 네이티브 회전 툴**(TranslationLimit은
   이동 툴)이 자동으로 켜진다. 새 `MPxManipContainer`는 만들지 않는다 —
   기존 Maya 매니퍼레이터를 헬퍼 로케이터 기준으로 쓸 뿐이다.
3. 별도의 **작은 HUD 창**이 떠서 원점(0) 기준 현재 각도/거리를 실시간
   표시한다(Limit은 "몇 도", TranslationLimit은 "몇 cm").
4. 뷰포트엔 원점→현재값까지의 범위가 **반투명 파란색**으로 실시간
   표시된다 — Maya 네이티브 임시 지오메트리(Limit은 부채꼴 팬 메쉬,
   TranslationLimit은 축 방향 막대/박스 메쉬) + lambert transparency,
   idle 콜백마다 버텍스 재생성. 커스텀 `MPxDrawOverride`는 쓰지 않는다 —
   이 프로젝트의 유일한 draw override 구현(`maroPointCloud`)이 현재
   미해결 크래시를 겪고 있으므로, 그 서브시스템에 새로 얹지 않는다.
5. **Collect**(HUD 버튼 또는 스페이스바 단축키) → 현재값을 샘플링해
   `min = min(min, 현재값)`, `max = max(max, 현재값)`로 누적. 양쪽으로
   여러 번 움직이고 collect하면 범위가 자연스럽게 넓어진다. 진행 중인
   스윕(옅은 파랑)과 이미 확정된 누적 범위(진한 파랑)를 시각적으로
   구분한다.
6. HUD의 "완료" 버튼 → 헬퍼 로케이터/임시 메쉬/HUD 정리, 원래 매니퍼레이터
   툴로 원복, 상세 패널에 최종 `aMin`/`aMax`(및 `aAxisDirection`) 반영.

**Coupling된 오브젝트의 접촉면 자동 축 감지는 이번 스펙의 후속 태스크로
분리한다** — MVP는 Coupling 여부와 무관하게 항상 수동 2점 클릭으로 축을
지정한다.

## 6. 테스트 전략

**자동화 (mayapy 배치, Qt 없이 순수 함수 검증):**
- 축 벡터 계산(두 점 → 정규화 방향)
- Maya→ROS 방향 벡터 변환(이동 성분 없는 회전 적용)
- "축 기준 현재값" 계산(axis-angle 투영)
- collect의 범위확장(`min(min,x)`/`max(max,x)`) 로직
- 위 전부 `maroLimitCalibration.py`의 Maya 비의존 순수 함수로 분리

**자동화 (ctest, C++):**
- `MaroLimitNode`/`MaroTranslationLimitNode`의 새 `compute()`에 대해
  축/값 조합 몇 개를 손으로 계산한 기대값과 대조
- `test_urdf_export.py` — 새 스키마(단일 축+min/max) 대응 확장

**수동 체크리스트 (뷰포트/Qt 상호작용, 배치 불가):**
- SONE 더블클릭 3가지 분기(단일/펼침-행/펼침-중앙) 동작
- 7개 패널 개별 열기/닫기/적용/언로드 정리
- Limit 캘리브레이션 전체 플로우: 2점 축지정 → 네이티브 회전툴 →
  HUD 실시간 각도 → 파란 부채꼴 렌더 → collect 누적(양방향 여러 번) →
  완료 시 정리 → 패널/노드에 값 반영
- TranslationLimit의 이동툴/선형 바 버전, 동일 플로우
- 캘리브레이션 도중 플러그인 언로드 시 임시 로케이터/메쉬/HUD가 안전하게
  정리되는지(크래시 없음) — 이 프로젝트가 반복적으로 겪은 "렌더러/뷰포트가
  붙잡고 있는 오브젝트가 언로드 시점에 살아있는" 위험군

## 7. 이번 스펙 범위 밖 (후속 과제)

- Coupling `curvePoints` 배열 편집 UI
- Coupling된 오브젝트의 접촉면 자동 축 감지
- 기존 X/Y/Z 3축 동시 제한 씬의 정확한 마이그레이션 절차(플랜 단계에서
  grep으로 영향 범위 집계 후 결정)

## 8. 예상 태스크 규모

대략 8개 태스크: (1) C++ 스키마 재설계, (2) URDF export 대응,
(3) 단순 5타입 패널+팩토리, (4) SONE 더블클릭 배선, (5) 캘리브레이션 엔진
순수함수, (6) Limit 회전 캘리브레이션 UI(매니퍼레이터+HUD+웨지),
(7) TranslationLimit 이동 버전, (8) 수동 체크리스트+검증. 정확한 분할은
`writing-plans` 단계에서 확정한다.
