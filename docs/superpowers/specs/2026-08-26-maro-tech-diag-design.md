# Maro 테크 Diag — 기구학/ROS 정합성 검증 터미널 설계 (2026-08-26)

## 1. 배경

방금 병합된 노드 캔버스 + 마킹 메뉴 에디터(SONE/ONE)로 축·capability를 편집하는 흐름은 완성됐지만, "이렇게 만든 로봇화 오브젝트가 실제로 말이 되는 움직임을 내는가"를 확인할 방법이 MaroUI 안에 없다. 이 문서는 그 확인을 담당하는 새 서브시스템 "테크 Diag"를 설계한다.

**기존 `boad`/`book`/`onfix`/`offix`/`ghost` 디버깅 Diag 생태계(`2026-08-14-maro-troubleshooting-ecosystem-design.md`, `2026-08-15-maro-layer-b-diagnostic-panel-design.md`)와는 목적과 실행 방식이 완전히 다르다:**

| | 기존 디버깅 Diag | 테크 Diag(이 문서) |
|---|---|---|
| 목적 | 플러그인/Maya 크래시 대비, 에러 원인·해법 신속 전달 | 로봇화 오브젝트의 기구학적/ROS 데이터 타당성 검증 |
| 실행 위치 | 백그라운드(감시자 프로세스 + 상시 스트림) | **MaroUI 안에서만**, 사용자가 버튼을 눌러야 실행 |
| 트리거 | 에러가 실제로 발생했을 때 | 에러 유무와 무관하게 **사용자가 원할 때 능동적으로 지금 상태를 검사** |
| 데이터 수명 | 세션/저널을 넘어 누적(`book`) | 검사 버튼을 누를 때마다 새로 계산, 누적 이력 없음 |
| 구현 표면 | C++(`boad`/`book`/`onfix`) + Python 패널 | **새 C++ 커맨드 없이 Python 순수 함수** |

두 시스템은 완전히 독립적이며, 코드도 데이터도 공유하지 않는다.

## 2. 레이아웃

MaroUI(현재: 메뉴바 / Maya·ROS 듀얼 뷰포트 / ONE 오브젝트 노드 그리드) 창의 **폭을 늘려서** 듀얼 뷰포트 좌우 바깥쪽에 세로로 긴 사이드 패널을 하나씩 추가한다:

```
[메뉴바]
[Maya검사/Diag 패널] [Maya 뷰포트] [ROS 뷰포트] [ROS검사/Diag 패널]
[ONE 오브젝트 노드 그리드]  (전체 폭, 변경 없음)
```

- 뷰포트 폭은 그대로 유지한다(사이드 패널이 뷰포트를 침범하지 않고 창 전체 폭이 늘어남).
- 각 사이드 패널은 위에서부터: `검사 실행` 버튼 → 그 아래 결과 목록(MaroDiag 터미널)으로 구성된다.
- 기존 `viewportPane`(Maya/ROS 두 `modelPanel`을 담은 `paneLayout`) 내부는 손대지 않는다 — 새 사이드 패널은 그 바깥을 감싸는 새 레이아웃 계층에서 추가한다.
- ONE 그리드 영역은 이번 변경과 무관하다.

## 3. Maya측 검사 — "애니메이팅 관점"

버튼을 누르면 씬을 순회하며 두 가지를 계산한다.

### 3.1 리밋 근접 경고
`Limit`/`TranslationLimit` capability가 있는 축마다, 현재 구동값이 그 capability의 min/max 범위 중 어느 한쪽 끝에 **90%**(기본 임계값) 이상 근접했으면 경고를 낸다. `Coupling`으로 간접 구동되는 축도 포함한다 — 판정 기준은 그 축의 최종 구동값(coupling이 계산해 넘긴 값)이지, coupling의 `ratio`/`offset` 원본 파라미터가 아니다.

이미 커맨드 레벨에서 막고 있는 것(1차 구동값 상호배타, 각도/선형 계열 불일치)과는 다른 문제다 — 저건 "애초에 만들 수 없는 조합"을 막는 것이고, 이건 "만들 수는 있지만 지금 값이 위험 구간에 있다"는 사전 경고다.

### 3.2 메쉬 충돌(바운딩박스) 검사
씬에 바인딩된 모든 타겟 메쉬 쌍에 대해, 현재 포즈에서의 월드 바운딩박스(`cmds.exactWorldBoundingBox()`)가 서로 겹치는지 축정렬(AABB) 기준으로 검사한다. **v1은 폴리곤 단위 정밀 충돌이 아니라 바운딩박스 겹침만 본다** — 계산이 가볍고, "이 근처에서 뭔가 부딪힐 수 있다"는 1차 경고로 충분하다는 판단. 정밀 검사(예: 이미 LiDAR가 쓰는 Embree 엔진 재사용)는 이번 범위 밖(§8).

## 4. ROS측 검사 — "로보틱스 관점"

`/joint_states` 발행에 실제로 나가는 데이터의 정합성만 검사한다(maroLidar/센서 검증은 §8에서 범위 밖으로 명시).

- **빈 `jointName`**: 활성화되고 바인딩된 축인데 `jointName`이 비어 있음.
- **`jointName` 중복**: 서로 다른 두 축이 같은 `jointName`을 씀(ROS `joint_states`는 조인트 이름이 유일해야 함).
- **구동값 없는 활성 축**: `enabled=true`고 바인딩까지 됐는데 1차 구동 capability(rotation/translation/coupling)가 하나도 없어서, 사실상 의미 없는 상수값이 발행됨.

## 5. 결과 표시 + 해법/자동 보정

버튼을 누른 시점의 스캔 결과를 그 자리에서 목록으로 보여준다(과거 스캔 이력 누적 없음, 매번 새로 계산). 각 항목은 문제 설명 + (있으면) 해법 버튼을 갖는다:

| 검사 항목 | 해법 버튼 | 이유 |
|---|---|---|
| 리밋 근접 경고 | 없음, 설명만 | "값을 어떻게 바꿔야 안전한지"는 사용자의 창작 의도에 달려 있어 일반해가 없다 |
| 메쉬 충돌 | 없음, 어느 축이 관여하는지만 안내 | 충돌을 없애려면 어떤 축을 어떻게 바꿔야 하는지도 일반해가 없다 |
| 빈 `jointName` | **있음** — 오브젝트 짧은 이름으로 채움 | 구조화된 단순 `setAttr`, 부작용 없음 |
| `jointName` 중복 | **있음** — 나중에 발견된 쪽에 접미사(`_2`)를 붙여 재명명 | 마찬가지로 단순 `setAttr` |
| 구동값 없는 활성 축 | 없음, 설명만 | "능력을 추가해라" 또는 "비활성화해라" 둘 다 사용자 판단 영역 |

해법 적용은 기존 디버깅 Diag의 안전 규칙(§4.3, `2026-08-14-...design.md`)과 동일한 모델을 그대로 따른다 — **제시가 기본, 적용은 사용자가 버튼을 눌러야 함, undoable 커맨드 경유(Ctrl+Z로 되돌릴 수 있음), 씬을 말없이 고치지 않음.** 단, 구현 자체는 기존 `boad`/`book`/`maroApplyRemedy`와 완전히 독립적이다(코드 재사용 없음, §1의 표 참고) — 안전 원칙만 같은 것을 반복 채택한다.

## 6. 아키텍처 — 새 C++ 커맨드 없음

이 검사들은 새로운 DG 데이터나 undo가 필요한 씬 변형이 아니라 **이미 존재하는 상태를 그때그때 다시 읽어 계산**하는 것이다. 그래서:

- 검사 로직(`checkLimitProximity`, `checkMeshCollisions`, `checkJointStatesIntegrity`)은 새 파일 `python/maroTechDiag.py`에 순수 함수로 작성한다. 입력은 `cmds.maroListAxisNodes()`/`cmds.maroListAxisNodes(capabilities=axis)`(기존 커맨드)와 `cmds.exactWorldBoundingBox()`/`cmds.getAttr()`(표준 Maya 커맨드) 결과이고, 출력은 이 파일 자체가 정의하는 단순한 결과 레코드 리스트다(기존 `boad`의 `DiagRecord`/`book`의 `BookEntry`와 이름·구조 모두 다른, 완전히 별개의 데이터 형).
- 해법 적용(`jointName` 채우기/재명명)은 `cmds.setAttr` 한두 번으로 끝나는 단순 조작이라, 이 세션이 축·capability 에디터에서 이미 여러 번 확인한 관례대로 새 undoable C++ 커맨드 없이 `cmds.undoInfo(openChunk=True/closeChunk=True)`로 감싼 파이썬 스크립트로 충분하다.
- Maya에 의존하지 않는 부분(리밋 근접 판정의 비율 계산, AABB 겹침 판정, 중복 이름 탐지)은 순수 함수로 분리해 mayapy 배치 테스트로 검증한다 — 이번 세션의 `computeRadialLayout`/`hitTestRadialItem` 등과 같은 원칙.
- 두 사이드 패널 위젯(Maya측/ROS측)도 같은 파일에 두되, 위젯 자체의 실제 마우스/버튼 동작은 이 프로젝트가 반복 확인한 제약(배치 mayapy는 `QGuiApplication`이라 `QWidget` 생성 시 프로세스가 abort) 때문에 대화형 Maya에서만 수동 검증 가능하다.

## 7. 데이터 흐름 요약

```
[검사 실행] 버튼 클릭
  → cmds.maroListAxisNodes() 전체 축 조회
  → 각 축의 capabilities 조회(maroListAxisNodes(capabilities=axis))
  → (Maya측) 리밋 근접 계산 + 바인딩된 메쉬들 exactWorldBoundingBox 겹침 계산
  → (ROS측) jointName 공백/중복/무구동 계산
  → 결과 레코드 리스트를 그 자리에서 렌더링(과거 결과 폐기)
  → 사용자가 해법 버튼 클릭 시: undo 청크 안에서 setAttr 실행 → 목록 갱신
```

## 8. 범위 밖

- **센서/LiDAR 검증**(레인지 내 미탐지 장애물, LiDAR 레이캐스팅 정합성) — `maroLidar`가 아직 UI에 노출되지 않은 상태(별도 로드맵 Phase 5, 미착수)라 이번 범위에서 제외. Phase 5 완료 후 이 문서의 후속으로 별도 브레인스토밍.
- **폴리곤 단위 정밀 메쉬 충돌**(Embree 재사용) — v1은 AABB 겹침까지만. 필요해지면 별도 슬라이스로 정밀도를 높인다.
- **리밋 근접/메쉬 충돌의 자동 보정** — §5에서 이미 명시한 대로 일반해가 없어 이번 범위에서 제외.
- **기존 디버깅 Diag와의 통합/재사용** — 의도적으로 완전히 분리된 별개 시스템(§1).
- **검사 결과 이력 저장** — 매 실행마다 새로 계산, 저장/추적 없음.

## 9. 테스트 전략

- `python/maroTechDiag.py`의 순수 함수(리밋 근접 비율 계산, AABB 겹침 판정, `jointName` 공백/중복/무구동 탐지)는 새 mayapy 배치 테스트 `tests/maya/test_tech_diag.py`로 검증 — 이번 세션의 `test_single_object_node_editor.py`/`test_object_node_editor.py`와 같은 관례(평범한 assert/print 스크립트, `maya.standalone` 없이 mayapy로 직접 실행).
- 해법 적용(`jointName` 채우기/재명명)의 undo 가능 여부는 mayapy 배치로 검증 가능(실제 `cmds.setAttr` + `cmds.undo()` 왕복).
- 사이드 패널 위젯의 실제 버튼 클릭/렌더링은 대화형 Maya 수동 체크리스트로만 검증 — `docs/maro-main-ui-manual-checklist.md`에 새 절 추가.

## 10. 전역 제약

- 빌드는 항상 `--config Release`, `ctest --test-dir out/build -C Release --output-on-failure` 전부 통과.
- 새 `.py`는 `setStyleSheet()`를 호출하지 않는다(기존 전 파일 공통 규율).
- 새 C++ 커맨드/DG 어트리뷰트를 추가하지 않는다 — 이 서브시스템은 순수 조회 + `cmds.setAttr` 조합으로 완성한다.
- 기존 `viewportPane`(Maya/ROS `modelPanel` 페어) 내부 구조는 변경하지 않는다 — 사이드 패널은 그 바깥을 감싸는 새 레이아웃 계층에서 추가한다.
- 해법 적용은 항상 `cmds.undoInfo(openChunk=True)`/`closeChunk=True`로 감싸 Ctrl+Z로 되돌릴 수 있어야 하고, 사용자가 버튼을 누르기 전에는 씬을 바꾸지 않는다.
