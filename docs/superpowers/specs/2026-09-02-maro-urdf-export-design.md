# Maro URDF 내보내기 설계 (S5 워킹 스켈레톤) (2026-09-02)

## 1. 배경

원 설계 문서(`2026-08-13-maya-ros2-axis-node-robotization-design.md`)는 S5를 "파이프라인 통합(URDF/USD 상호운용)"으로 로드맵에서 제외해 뒀고, 유일한 텍스트는 "축 체인과 능력 노드 스택으로부터 URDF를 생성한다. 본 설계의 데이터 모델이 URDF 생성에 필요한 정보를 담고 있어야 한다"는 한 문장이었다. 기술 설계가 전혀 없었다.

이번 브레인스토밍에서 확인한 핵심 사실: **`maroAxis` 노드 자신의 DAG 위치는 관절의 실제 공간적 원점과 무관하다.** `aTargetObject`/`aParentAxis`는 둘 다 message-only 연결(값을 나르지 않는 순수 식별용)이고, `maroDagMenu.py`가 새 축을 만들 때도 월드 원점 근처에 독립적으로 생성할 뿐 타겟 위치로 옮기지 않는다. URDF의 각 `<joint>`는 부모 링크 프레임 기준 `<origin>`이 반드시 필요한데, 지금 데이터 모델에는 그 정보가 없다. 이번 스펙은 사용자가 확정한 대로 **새 어트리뷰트를 추가하지 않고, 축 로케이터 자신의 실제 위치/방향을 그 정보로 쓰는 새 리깅 관례**를 도입해 이 문제를 해결한다.

## 2. 사용자가 확정한 결정

1. **관절 원점(origin) 출처**: 축 로케이터 자신의 실제 월드 위치/회전. 리거가 축을 만들 때 관절이 실제로 있어야 할 자리에 배치+회전시킨다(새 어트리뷰트 없음).
2. **관절 축 방향 기준**: `conventionAxis`(X/Y/Z)는 그 축 로케이터 **자신의 로컬** 축을 가리킨다. 로케이터를 배치할 때 위치뿐 아니라 회전도 그 관절이 실제로 도는/미끄러지는 방향에 맞춰야 한다.
3. **첫 슬라이스 범위**: 관절 구조(`<link>`/`<joint>`의 origin/axis/type/limit)만 맞춘다. 시각/충돌 메쉬(`<visual>`/`<collision>`)는 범위 밖 — 별도 후속 슬라이스.
4. **트리거**: Maro 메뉴의 새 항목 "URDF 내보내기..." → 클릭 즉시 `cmds.fileDialog2`로 저장 경로를 묻고 내보낸다. 별도 창/미리보기 없음.

## 3. 설계

### 3.1 아키텍처 — 새 C++ 코드 없음

새 파일 `python/maroUrdfExport.py` 하나. 이 세션이 Tech Diag/스켈레톤 업로드에서 반복해 온 패턴 그대로, 이미 있는 조회 수단만 조합한다:

- **`maroListAxisNodes()`**(양방향 쿼리, 이미 있음) — 전체 축과 각 축의 `parentAxisPath`/`boundTargetPath`/`jointName`/`conventionAxis`/`driveIsLinear` 조회.
- **`maroListAxisNodes(capabilities=axis)`**(이미 있음) — 각 축의 capability 스택(`capType`/`capMin`/`capMax`/`capEnable` 등) 조회.
- **`cmds.xform(axis, query=True, worldSpace=True, translation=True)`** + **`maya.api.OpenMaya.MFnTransform(dagPath).rotation(om2.MSpace.kWorld, asQuaternion=True)`** — 각 축의 월드 위치/회전. 후자는 이 코드베이스가 이미 실측으로 검증해 둔 방식이다(`python/maroRosProxy.py:204-211`의 기존 주석 — `MFnTransform.rotation(kWorld, asQuaternion=True)`이 부모 변환까지 반영한 진짜 월드 회전이고 `inclusiveMatrix`에서 뽑은 값과 일치함을 확인했다고 적혀 있음). 이번 작업이 그 결론을 그대로 재사용한다.
- **`cmds.maroMayaToRos(px= py= pz= qx= qy= qz= qw=)`**(이미 있음, `MaroRosRuntime.cpp`의 실제 ROS 발행 경로와 같은 소스) — 위에서 얻은 Maya 월드 위치/쿼터니언을 ROS(Z-up, 미터) 위치/쿼터니언으로 변환.

메뉴 배선: `python/maroMenu.py`에 항목 하나 추가(`import maroUrdfExport\nmaroUrdfExport.export()`), `src/maro_plugin/CMakeLists.txt`의 `MARO_PLUGIN_PY_MODULES`에 `maroUrdfExport` 추가.

### 3.2 관절 원점(`<origin>`) 계산

각 축의 (ROS 프레임 위치, ROS 프레임 쿼터니언)을 4x4 변환 행렬로 조립한다(`om2.MTransformationMatrix`로 translation+rotation을 넣고 `.asMatrix()`). 축 A(부모)와 축 B(자식, `parentAxisPath == A`)가 있을 때:

```
relative = inverse(A_rosMatrix) * B_rosMatrix
```

`relative`를 다시 `om2.MTransformationMatrix`로 분해해 translation(미터, URDF `<origin xyz=>`)과 회전(라디안, XYZ 고정축 오일러 — URDF의 `rpy`도 같은 관례라 추가 변환이 필요 없다)을 얻는다.

**정정(자체 검토 중 발견)**: 루트 축에는 이 계산을 적용하지 않는다. URDF 자체에는 루트 링크의 "월드 기준 위치"를 담는 필드가 없다 — `<origin>`은 오직 `<joint>` 안에서 "부모 링크 → 이 조인트 프레임"의 상대 변환을 표현할 뿐이고, 루트 링크(`base_link`)는 어떤 조인트로도 부모에 연결되지 않으므로 `<origin>` 자체가 존재하지 않는다(실제 월드 배치는 URDF 밖에서, 예를 들어 스폰 시점의 정적 tf나 시뮬레이터 설정으로 다뤄지는 게 표준 관례다). 그래서 이 도구는 루트 축에 대해서는 `<origin>` 계산을 아예 건너뛰고, 루트의 `<link>` 요소만(조인트 없이) 만든다.

### 3.3 관절 축(`<axis>`) 계산 — 별도 변환이 필요 없다

`<origin>`이 이미 "부모 기준 이 축 로케이터의 자세"를 URDF 관절 프레임으로 그대로 확정하므로, `conventionAxis`가 가리키는 로케이터의 로컬 축은 **그 관절 프레임 안에서 이미** X=(1,0,0), Y=(0,1,0), Z=(0,0,1)이다. 별도 회전/변환이 필요 없다 — `conventionAxis` 값 하나를 그대로 세 단위벡터 중 하나로 매핑하면 끝이다.

(참고: Maya↔ROS 변환이 순수 회전(핸디니스를 보존하는 변환)이라는 전제가 이 단순화의 근거다 — `maro_transform::mayaToRosRotation`이 이미 검증된 회전 변환이므로, 부모·자식 양쪽에 동일하게 적용된 뒤 상대 변환을 취하면 로컬 기저벡터의 축 대응 관계 자체는 바뀌지 않는다.)

### 3.4 관절 타입 매핑

| capability 스택 | URDF `type` | 비고 |
|---|---|---|
| rotation only | `continuous` | 무제한 회전 |
| rotation + limit(해당 축 enable) | `revolute` | `<limit lower= upper=>`를 `capMin`/`capMax`에서 채움 |
| translation only | `prismatic` | URDF는 `<limit>` 필수 — limit 없으면 아주 넓은 값(예: ±1e6미터)으로 채우고 주석으로 "무제한 관례" 명시 |
| translation + translationLimit(해당 축 enable) | `prismatic` | `<limit>`을 `capMin`/`capMax`에서 채움(센티미터→미터 변환) |
| coupling(각도, capType 6) | `continuous` + `<mimic joint="{소스 축의 jointName}" multiplier="{ratio}" offset="{offset}">` | **정정(구현 단계 태스크 리뷰에서 발견)**: 애초 이 표는 "revolute"라고 적었으나, mimic 관절이라고 해서 반드시 각도 제한이 있는 건 아니다(예: 대칭 기어). rotation-only 관절과 같은 원칙 그대로 취급한다 — coupling 자체는 `limit` capability를 절대 참고하지 않고 항상 `continuous`/`prismatic` + `mimic`으로 확정한다(리밋이 있는 mimic 관절이 필요해지면 별도 후속 설계). 소스 축은 `cmds.listConnections(couplingNode + ".sourceValue"/".sourceValueLinear", source=True)`로 역추적한다 — 기존에 재사용할 헬퍼가 없어 이번에 새로 작성해야 하는 부분이지만(확인함), `maroLidarPanel._pairedPointCloud()`가 이미 같은 방식(`listConnections`로 메시지/값 연결을 역추적)을 쓰고 있어 이 코드베이스의 낯선 패턴은 아니다 |
| coupling(선형, capType 7) | `prismatic` + 같은 `<mimic>` | |
| 없음, 또는 sensorDirection/sensorRange만 | `fixed` | 센서 축은 로봇 관절이 아니라 좌표 프레임으로만 표현 |

`effort`/`velocity`(URDF `<limit>`의 나머지 필수 속성)는 이 데이터 모델에 대응 값이 없으므로 관례적 상수(예: `effort="1000" velocity="10"`)로 채우고, 실제 물리 한계를 표현하지 않는다는 점을 스펙에 명시해 둔다 — 나중에 필요해지면 별도 어트리뷰트 추가를 검토.

### 3.5 링크/조인트 이름, 트리 검증

- **link 이름**: 각 축의 `boundTargetPath`의 짧은 이름(마지막 `|` 이후). 새 필드 불필요. **알려진 한계**: Maya는 짧은 이름의 유일성을 형제 노드 사이에서만 보장한다 — 씬 전체에서 서로 다른 계층에 있는 두 오브젝트가 같은 짧은 이름을 가질 수 있고, 그러면 URDF가 요구하는 "링크 이름 전역 유일" 조건이 깨진다. 이번 슬라이스는 이 충돌을 감지/해결하지 않는다(발생하면 잘못된 URDF가 조용히 만들어질 수 있음) — 실제로 문제가 되면 별도 검사를 추가할 후속 과제로 남긴다.
- **joint 이름**: 각 축의 `jointName`을 그대로 사용. 비어 있으면 내보내기를 거부하고 어느 축인지 에러로 알린다(Tech Diag의 "빈 jointName" 검사와 같은 문제를 이 도구도 독립적으로 검사한다 — 두 시스템은 서로 다른 목적이므로 코드/상태 공유 없음, 사용자에게는 "Tech Diag로 먼저 확인하라"고 안내만 한다).
- **트리 검증**: `parentAxisPath`가 빈 축이 정확히 하나여야 루트로 인정한다. 0개(모든 축이 서로를 참조하는 순환 — `maroConnectAxis`가 생성 시점에 이미 막고 있으므로 실제로는 "루트가 아예 없다"는 다른 원인, 예: 씬에 축이 하나도 없음)나 2개 이상(여러 독립된 체인)이면 내보내기를 거부하고 어느 축들이 후보인지 나열하는 에러를 낸다. 여러 체인을 하나의 URDF로 합치거나 별개 파일로 나누는 것은 범위 밖.
- **같은 `boundTargetPath`에 축이 둘 이상 바인딩된 경우**: 나올 수 없다 — `maroBindAxis`가 이미 "오브젝트 하나에는 축 하나만" 규칙을 커맨드 레벨에서 강제한다(기존 코드 확인, 별도 처리 불필요).

### 3.6 파일 출력

`cmds.fileDialog2(fileMode=0, fileFilter="URDF (*.urdf)")`로 저장 경로를 물은 뒤, 표준 라이브러리 `xml.etree.ElementTree`로 `<robot name="...">` 트리를 조립해 `ElementTree.write(path, xml_declaration=True, encoding="utf-8")`로 저장한다. `<robot name=>`은 씬 이름(확장자 제거) 또는 사용자가 고른 파일 이름(확장자 제거)에서 따온다 — 후자가 항상 존재가 보장되므로 그걸 쓴다.

## 4. 테스트 전략

- 트리 구성(루트 판정, 부모-자식 매핑), origin/axis 계산(순수 행렬 연산, Maya 의존 부분과 분리 가능), 관절 타입 매핑, XML 조립은 전부 **입력을 파이썬 딕셔너리/튜플로 받는 순수 함수**로 분리한다 — 이 프로젝트의 기존 관례(`maroTechDiag.py`의 `check*` 함수들과 동일 원칙)를 그대로 따라 mayapy 배치 테스트가 Qt/실제 씬 없이도 로직을 검증할 수 있게 한다.
- 월드 트랜스폼 조회(`cmds.xform`/`MFnTransform`/`maroMayaToRos` 호출)만 담당하는 얇은 조합 함수 하나(`_gatherAxisWorldTransforms()`류)가 순수 함수들과 실제 씬 사이의 유일한 경계가 된다 — mayapy 배치에서 실제 축 2-3개짜리 작은 체인을 만들어 이 경계 함수까지 포함한 종단 간 테스트도 가능(파일 다이얼로그만 빼면 나머지는 전부 배치 테스트 가능하다).
- `cmds.fileDialog2` 호출 자체(실제 파일 저장 대화상자)는 mayapy 배치로 검증 불가능 — 메뉴 클릭부터 실제 파일이 디스크에 쓰이는지까지는 대화형 Maya 수동 체크리스트로 확인한다. 체크리스트의 go/no-go 항목은 **내보낸 URDF를 실제 `check_urdf`(ROS 2 CLI 도구) 또는 RViz2로 로드해 관절이 시각적으로 제자리에서 올바른 방향으로 돌아가는지** — 이 프로젝트가 반복해 온 "추측 대신 실측" 원칙을 좌표계/축 변환처럼 틀리기 쉬운 부분에 그대로 적용한다.

## 5. 범위 밖

- 시각/충돌 메쉬(`<visual>`/`<collision>`) — §1에서 사용자가 명시적으로 다음 슬라이스로 미룸.
- 다중 루트(독립된 여러 체인)를 하나의 URDF로 합치거나 여러 파일로 나누는 처리 — 에러로 거부만 한다.
- USD 내보내기, xacro, `ros2_control` 하드웨어 인터페이스 태그, Gazebo `<gazebo>` 확장.
- 센서 capability(sensorDirection/sensorRange)의 URDF `<sensor>` 요소 매핑 — 이번엔 fixed 조인트로만 표현되고, 실제 센서 스펙(예: LiDAR FOV) 변환은 하지 않는다.
- `effort`/`velocity` 물리 한계의 실제 값 반영 — 관례적 상수로만 채운다.
- URDF → Maya 역방향 가져오기(임포트) — 이번은 내보내기 단방향만.
