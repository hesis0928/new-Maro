# Maro Arnold 합성 데이터 — Film Fit 모드 보정 — 설계

## 1. 배경

2026-09-04, Arnold 합성 데이터 생성기(`docs/superpowers/specs/2026-09-04-maro-arnold-synthetic-data-design.md`)의 최종 브랜치 리뷰가 `python/maroSyntheticDataPointCloud.py`의
`computeCameraIntrinsics()`가 Maya 카메라의 **Film Fit 모드**(필름 백 종횡비와
렌더 해상도 종횡비가 다를 때 Maya가 화각을 어떻게 맞출지 결정하는 설정)를
전혀 반영하지 않는다는 걸 발견했다. 실제 Arnold 렌더로 측정한 결과 한 축에서
~11~19% 기하학적 오차가 났고, 그때는 코드 주석 + 수동 체크리스트 항목으로만
문서화해두고 알고리즘 수정 자체는 범위 밖으로 명시적으로 미뤘다. 이 설계는
그 후속 작업이다.

**이전 최종 리뷰가 실측으로 유도해 둔 사실**(재조사 없이 채택): 카메라의
`filmFit` 속성을 읽고 `deviceAspect > filmAspect`일 때는
`vEff = hAperture/deviceAspect`로, 아니면 `hEff = vAperture*deviceAspect`로
유효 필름 백 치수를 계산한 뒤 기존 fx/fy 공식에 대입하는 규칙이 실측값(320x240
테스트, Y축 평균 88.5)을 정확히 재현한다.

## 2. 범위

### 이번 설계에 포함

1. **Film Fit 4가지 모드 전부**(Fill/Horizontal/Vertical/Overscan) 지원.
2. **일반적인 `pixelAspectRatio`(비정사각 픽셀)** 지원 — 기존에 이미 통용되던
   "보정된 fx=fy" 단순화는 `pixelAspectRatio=1.0`일 때만 성립하는 특수
   케이스였다는 걸 이번에 명확히 하고, 일반형 공식으로 교체한다.
3. `computeCameraIntrinsics()` 시그니처 확장 + `buildCalibrationDict()`/패널
   호출부 전파.

### 명시적 제외

- `unprojectDepthToPoints()`는 변경 없음 — 이미 계산된 intrinsics 딕셔너리만
  받으므로 이번 수정의 영향을 받지 않는다.
- 카메라의 `filmOffset`(필름 백 오프셋), `lensSqueezeRatio` 등 이번에 실측으로
  드러나지 않은 다른 카메라 어트리뷰트는 다루지 않는다.

## 3. 일반 공식 프레임워크

두 핵심 값:
- `filmAspect = horizontalFilmApertureIn / verticalFilmApertureIn`
- `deviceAspect = (widthPx / heightPx) * pixelAspectRatio` (Maya가 Film Fit
  판정에 실제로 쓰는 정의 — 렌더 해상도 자체의 종횡비가 아니라 픽셀종횡비까지
  반영한 값)

`pixelAspectRatio != 1.0`이면 fx와 fy가 단순히 같아지지 않는다 — 등방성
렌즈라도 픽셀이 정사각형이 아니면 fx·fy는 원래 다른 값이어야 정확하다. 각
모드는 "가로/세로 필름 백 중 어느 쪽을 그대로 쓰고 어느 쪽을 다시 계산할지"만
결정하고, 최종 fx/fy는 그 유효 필름 백 치수로 기존 핀홀 공식
(`fx = focalLengthMm/(effectiveHIn*25.4)*widthPx`,
`fy = focalLengthMm/(effectiveVIn*25.4)*heightPx`)을 그대로 적용해 얻는다.

| 모드 | 규칙 |
|---|---|
| **Fill** | `filmAspect < deviceAspect`면 가로 필름 백을 그대로 쓰고 `vEff = hApertureIn / deviceAspect`로 세로를 다시 계산. 반대면 대칭(`hEff = vApertureIn * deviceAspect`). |
| **Horizontal** | 가로 필름 백을 **항상**(종횡비 관계와 무관하게) 그대로 쓰고, `vEff = hApertureIn / deviceAspect`로 세로를 매번 다시 계산. |
| **Vertical** | 세로 필름 백을 **항상** 그대로 쓰고, `hEff = vApertureIn * deviceAspect`로 가로를 매번 다시 계산. |
| **Overscan** | **구현 단계 실측 확정 필수(§7)** — Maya의 `overscan` 어트리뷰트(기본 1.0)가 가로/세로 필름 백 양쪽에 배율로 곱해진다는 가설로 시작하되, 실제 동작을 Maya 문서 + `MFnCamera` 교차 검증 + 실제 렌더로 확정한 뒤 구현한다. 손으로 가정한 채로 출시하지 않는다. |

## 4. API 변경

`computeCameraIntrinsics()`는 순수 함수 성격을 유지하며 파라미터만 확장한다:

```python
def computeCameraIntrinsics(focalLengthMm, horizontalFilmApertureIn, verticalFilmApertureIn,
                             widthPx, heightPx, filmFit="fill", pixelAspectRatio=1.0, overscan=1.0):
```

- `filmFit`은 정규화된 문자열(`"fill"`/`"horizontal"`/`"vertical"`/`"overscan"`)로
  받는다. Maya의 실제 `filmFit` 정수 enum이 어느 값이 어느 모드인지는
  손으로 추측하지 않고 구현 단계에서 `cmds.attributeQuery(..., listEnum=True)`로
  실측 확인한다.
- 기본값(`filmFit="fill", pixelAspectRatio=1.0, overscan=1.0`)은 이 인자들을
  안 넘기는 호출부까지 포함해 **이번 수정으로 처음부터 올바르게 보정된
  Fill 기본 동작**을 하게 만든다 — 이전의 틀린 동작으로 되돌아가는 폴백이
  아니다.
- 인식 못 하는 `filmFit` 값이면 `ValueError`(명확한 메시지) — Maya 버전마다
  enum이 다를 가능성을 열어둔다. `pixelAspectRatio`/`overscan`은 별도 방어
  검증을 추가하지 않는다(Maya 자체 UI가 이미 양수로 제약).

**호출부 전파**:
- `buildCalibrationDict()`(`python/maroSyntheticDataRender.py`)가 카메라의
  `filmFit`/`pixelAspectRatio`/`overscan` 어트리뷰트를 읽어 기존 `focalLength`
  등과 같은 자리에서 계산 JSON에 함께 기록한다.
- `maroSyntheticDataPanel.py`는 이미(2026-09-04 최종 리뷰 수정으로) 계산
  JSON을 읽어 `computeCameraIntrinsics()`를 부르는 구조이므로, 새로 저장된
  세 값을 그대로 전달하기만 하면 된다.

## 5. 테스트/검증 전략

세 단계, 뒤로 갈수록 신뢰도가 높다:

1. **순수 함수 자체 테스트** — 4가지 모드 각각에 대해 손으로 계산한 예상값과
   대조(내부 일관성, mayapy 불필요한 부분은 plain Python으로도 가능).
2. **`maya.api.OpenMaya.MFnCamera` 교차 검증** — Maya의 `MFnCamera`는 Film
   Fit/오버스캔/픽셀종횡비를 이미 전부 반영한 실제 화각을
   `horizontalFieldOfView()`/`verticalFieldOfView()`로 제공한다. 이건 우리가
   재현하려는 계산을 Maya 자신이 이미 하고 있는 것이므로, 손으로 유도한
   공식보다 훨씬 신뢰할 수 있는 독립 대조군이다. 실제 카메라에 각 모드/
   픽셀종횡비/오버스캔 값을 설정하고, 그 화각으로부터 역산한 fx/fy와
   `computeCameraIntrinsics()`의 결과를 대조한다. 카메라의 `aspectRatio`를
   렌더 해상도에 맞춰 명시적으로 설정해야 하는지, Maya가 `defaultResolution`
   에서 자동 동기화하는지는 구현 단계에서 실측 확인한다.
3. **실제 Arnold 렌더 대조** — 이 세션 환경에서 이미 여러 번 확인된 배치
   Arnold 렌더링(Arnold 7.4.2.0/MtoA 5.5.2)으로, 알려진 위치의 평면을 4가지
   모드 각각으로 렌더해 역투영 결과가 실제 거리와 맞는지 최종 확인한다.
   **Overscan은 이 3단계가 사실상 유일한 확정 수단**이므로 반드시 포함한다.

## 6. 전역 제약

- 새 C++ 코드/커맨드/DG 어트리뷰트 없음 — 이번 기능 전체와 동일하게 순수
  Python.
- `unprojectDepthToPoints()`는 변경하지 않는다.
- `computeCameraIntrinsics()`의 기존 호출자(`maroSyntheticDataPanel.py`)가
  새 파라미터를 안 넘겨도 깨지지 않아야 한다(기본값으로 커버).
- 빌드는 항상 `--config Release`, 전체 `ctest` 통과.

## 7. 범위 밖 / 알려진 리스크

- **Overscan 모드의 정확한 공식은 이 스펙 작성 시점에 확정되지 않았다** — §3의
  가설은 구현 착수 전 Maya 공식 문서로, 구현 중 §5의 3단계 검증으로 반드시
  재확인한다. 손으로 가정한 채로 출시하지 않는다.
- `filmOffset`, `lensSqueezeRatio` 등 다른 카메라 렌즈 관련 어트리뷰트는
  다루지 않는다 — 필요해지면 별도 슬라이스.
- `unprojectDepthToPoints()`의 픽셀 부호/평면-깊이 규약(2026-09-04에 이미
  실측 검증 완료)은 이번 변경과 무관, 재검증하지 않는다.
