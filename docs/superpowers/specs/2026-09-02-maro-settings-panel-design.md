# Maro 환경설정 창 설계 (2026-09-02)

## 1. 배경

원 설계 문서(`2026-08-24-maro-main-ui-phase0-1-design.md` §7)는 "Phase 7 — 설정 모달 실제 내용(범위 미정, 추후 별도 브레인스토밍)"을 로드맵 항목으로 남겨 뒀다. `python/maroMenu.py`에는 이미 비활성 자리표시자 두 개가 있다(`enable=False`): `"ROS 연결 설정 (준비 중)"`과 `"환경설정 (준비 중)"`. 이 문서는 그 둘을 하나로 채우는 설계다.

조사 결과 이 플러그인에는 영구 저장되는 사용자 설정이 지금 전혀 없다(`cmds.optionVar` 사용 전무, 전체 리포 grep 확인) — 이번 작업이 그 저장소를 처음 도입한다. 또한 `maroStartBridge`(ROS 연결을 실제로 시작하는 유일한 진입점)가 지금 MaroUI 어디에도 연결돼 있지 않다는 것도 함께 확인됐다 — Script Editor에서 `cmds.maroStartBridge("robotName")`을 직접 쳐야만 ROS 연결이 시작된다. 그래서 이번 "환경설정" 창은 설정 저장 UI이면서 동시에, 지금 없는 "ROS 연결 시작/중지" UI를 처음 만드는 작업이기도 하다.

## 2. 사용자가 확정한 결정

1. **설정 대상**: ROS 연결 값(domain ID, robotName)과 Tech Diag 검증 임계값(리밋 근접 90%) 두 가지. 진단/book 저장 경로는 **이번 스코프에서 제외**(아래 §3.4 이유 참고).
2. **메뉴 구조**: `"ROS 연결 설정"`과 `"환경설정"` 두 자리표시자를 하나로 합친다.
3. **영속성**: `cmds.optionVar`로 영구 저장(Maya 재시작 후에도 유지).
4. **모달 여부**: 비모달 창 — 열려 있는 동안도 MaroUI의 다른 조작(뷰포트, ONE 그리드 등)을 막지 않는다.
5. **ROS 연결 시작/중지 UI**: 지금 없는 이 UI를 이번 작업에 함께 포함한다.
6. 세 값 중 적용 시점이 서로 다르다는 것(즉시 적용 vs 그렇지 않음)을 감추지 않고, 각 섹션에 안내 문구로 명시한다.

## 3. 설계

### 3.1 아키텍처

새 파일 `python/maroSettingsPanel.py` 하나만 추가한다. `python/maroLidarPanel.py`와 같은 패턴을 그대로 따른다: `QtWidgets.QWidget(parent, QtCore.Qt.Window)`, 모듈 전역 싱글턴 참조(패널이 이미 열려 있으면 새로 만들지 않고 앞으로 가져옴), `stop()`이 열려 있으면 닫고 참조를 지움. `setStyleSheet()`를 호출하지 않는다(이 코드베이스 전역 규율).

새 C++ 코드는 전혀 필요 없다 — `maroStartBridge`/`maroStopBridge`는 이미 존재하고, "이미 연결됨" 같은 상태 피드백도 이미 그 커맨드들이 스스로 `BoadMaro::warn`/`info`로 낸다(그리고 방금 병합된 콘솔 구분선 덕에 Script Editor에서 한 블록으로 잘 보인다). 그래서 이 패널은 별도 상태 표시줄을 두지 않는다 — 연결/연결 해제 버튼을 누른 결과는 Script Editor의 기존 진단 메시지가 알려준다.

### 3.2 메뉴 변경

`python/maroMenu.py`의 다음 두 줄:

```python
cmds.menuItem(label="ROS 연결 설정 (준비 중)", enable=False, parent=MENU_NAME)
cmds.menuItem(label="환경설정 (준비 중)", enable=False, parent=MENU_NAME)
```

을 활성 항목 하나로 교체한다:

```python
cmds.menuItem(label="환경설정...",
              command="import maroSettingsPanel\nmaroSettingsPanel.show()",
              parent=MENU_NAME)
```

### 3.3 저장소: `cmds.optionVar` (이 코드베이스 최초 사용)

다른 도구의 optionVar와 충돌하지 않도록 `maroSetting` 접두사를 쓴다:

| optionVar 이름 | 타입 | 기본값(없을 때) | 의미 |
|---|---|---|---|
| `maroSettingRosRobotName` | string | `""` | `maroStartBridge`에 넘길 로봇 이름 |
| `maroSettingRosDomainIdOverride` | int(bool로 사용) | `0`(꺼짐) | 켜져 있을 때만 도메인 ID를 직접 지정 |
| `maroSettingRosDomainId` | int | `0` | 체크박스가 켜져 있을 때만 의미 있음, 범위 0-232(ROS 2 유효 도메인 범위) |
| `maroSettingTechDiagLimitProximityThreshold` | float | `0.9` | 리밋 근접 경고 임계값(0.0-1.0) |

읽기/쓰기는 Qt와 무관한 순수 함수로 분리한다(§4 테스트 전략의 전제):

```python
def readRosSettings():
    """(robotName, domainIdOverrideEnabled, domainId) 튜플을 optionVar에서 읽는다."""

def writeRosSettings(robotName, domainIdOverrideEnabled, domainId):
    """세 값을 optionVar에 쓴다."""

def readTechDiagThreshold():
    """리밋 근접 임계값(0.0-1.0)을 optionVar에서 읽는다. 없으면 0.9."""

def writeTechDiagThreshold(value):
    """리밋 근접 임계값을 optionVar에 쓴다."""
```

### 3.4 왜 진단/book 저장 경로는 뺐는가

`src/maro_plugin/MaroDiag.cpp`의 `bookPaths()`는 함수-지역 정적 변수로, 플러그인이 로드되는 시점(`initializePlugin` → `markMainThread()`)에 **딱 한 번만** 계산되고 그 뒤로 절대 다시 계산되지 않는다(코드로 확인함). `MARO_DIAG_BOOK_DIR`은 OS 프로세스 환경변수라서, 이 계산이 일어나기 **전에** 이미 설정돼 있어야 한다.

이 프로젝트는 `.mod`/`userSetup.py`(Maya가 켜질 때 자동 실행되는 스크립트)를 의도적으로 쓰지 않기로 이미 결정해 두었다(Phase 0-1 설계 §3.4). 그래서 `optionVar`에 경로를 저장해도, 그걸 실제 OS 환경변수로 "승격"시켜 줄 자동 실행 지점이 이 프로젝트엔 없다 — Maya를 재시작해도 적용되지 않는다(다음 세션에서도 `initializePlugin`이 여전히 사용자가 설정 창을 열기 전에 먼저 실행되기 때문). 이걸 진짜로 동작하게 만들려면 (a) 이 프로젝트가 지금까지 피해 온 자동 실행 지점을 새로 만들거나, (b) `bookPaths()`의 정적-1회-계산 구조 자체를 재설계해야 한다 — 둘 다 이번 작업의 범위를 크게 넘는다. 그래서 이번 스코프에서 완전히 제외한다.

### 3.5 UI 구성

창 제목 "Maro 환경설정", `QtWidgets.QFormLayout` 위에 `QGroupBox` 두 개.

**ROS 연결** 섹션:
- `robotName` — `QLineEdit`
- `도메인 ID 직접 지정` — `QCheckBox`
- `도메인 ID` — `QSpinBox`(범위 0-232), 체크박스가 꺼져 있으면 비활성화(`setEnabled`)
- `연결` / `연결 해제` — `QPushButton` 두 개
- 안내 라벨: "연결 버튼을 누르면 즉시 적용됩니다."

`연결` 버튼 핸들러:
```python
def _onConnect(self):
    try:
        cmds.undoInfo(openChunk=True)
        robotName = self._robotNameField.text()
        overrideEnabled = self._domainOverrideCheck.isChecked()
        domainId = self._domainIdField.value()
        writeRosSettings(robotName, overrideEnabled, domainId)
        if overrideEnabled:
            os.environ["ROS_DOMAIN_ID"] = str(domainId)
        cmds.maroStartBridge(robotName)
    except Exception as exc:  # noqa: BLE001 -- Qt 콜백 경계
        cmds.warning("Maro: failed to connect: {}".format(exc))
    finally:
        cmds.undoInfo(closeChunk=True)
```

`os.environ["ROS_DOMAIN_ID"] = ...`가 이 프로세스 안에서 `rclcpp::init()`이 나중에 읽는 `ROS_DOMAIN_ID`에 실제로 반영되는지(파이썬과 C++이 같은 프로세스의 같은 OS 환경 블록을 공유한다는 전제)는 이 설계가 근거로 삼는 통상적인 OS/ROS 2 동작이지만, 이 프로젝트의 관례(추측 대신 실측 확인)에 따라 **구현 단계에서 실제로 도메인이 바뀌는지 확인**한다(§5 범위 밖 참고 — 확인 실패 시 이 메커니즘 자체를 재검토해야 함을 명시해 둔다).

`연결 해제` 버튼은 단순히 `cmds.maroStopBridge()`를 부른다(같은 try/finally 경계).

**Tech Diag** 섹션:
- `리밋 근접 경고 임계값 (%)` — `QSpinBox`(범위 0-100, 기본 90)
- `저장` — `QPushButton`, 클릭 시 `writeTechDiagThreshold(value/100.0)`
- 안내 라벨: "다음 검사 실행부터 즉시 적용됩니다."

### 3.6 `maroTechDiag.py` 연동 변경

`python/maroTechDiag.py:25`의 하드코딩 상수:

```python
LIMIT_PROXIMITY_THRESHOLD = 0.9
```

를, 검사 시점마다 다시 읽는 함수로 교체한다:

```python
_DEFAULT_LIMIT_PROXIMITY_THRESHOLD = 0.9


def _limitProximityThreshold():
    """maroSettingsPanel이 저장한 값을 읽는다. 없으면 기존 기본값."""
    if cmds.optionVar(exists="maroSettingTechDiagLimitProximityThreshold"):
        return cmds.optionVar(query="maroSettingTechDiagLimitProximityThreshold")
    return _DEFAULT_LIMIT_PROXIMITY_THRESHOLD
```

`LIMIT_PROXIMITY_THRESHOLD`를 참조하던 기존 두 자리(`checkLimitProximity` 안의 `nearMax`/`nearMin` 계산)를 `_limitProximityThreshold()` 호출로 바꾼다. 검사 버튼을 누를 때마다 새로 읽으므로 별도 캐시/무효화가 필요 없다.

### 3.7 `maroMainWindow.teardown()` 등록

기존 4개 서브시스템(`maroRosProxy`, `maroObjectNodeEditor`, `maroSingleObjectNodeEditor`, `maroLidarPanel`)과 같은 자리에, 같은 try/except 경계로 다섯 번째를 추가한다:

```python
try:
    import maroSettingsPanel
    maroSettingsPanel.stop()
except Exception:  # noqa: BLE001 -- Maya 콜백/언로드 경계
    import traceback
    traceback.print_exc()
```

## 4. 테스트 전략

- `readRosSettings`/`writeRosSettings`/`readTechDiagThreshold`/`writeTechDiagThreshold`는 Qt와 무관하게 `cmds.optionVar`만 감싸므로, mayapy 배치 테스트로 왕복(쓰고 다시 읽어서 같은 값인지) 검증 가능하다. optionVar가 세션 전역 상태이므로 테스트는 시작/종료 시 관련 optionVar를 지워 다른 테스트를 오염시키지 않는다(`cmds.optionVar(remove=...)`).
- `maroTechDiag._limitProximityThreshold()`는 optionVar 존재/부재 두 경로 모두 mayapy 배치로 검증 가능 — 기존 `test_tech_diag.py`와 같은 관례.
- 창을 열고 체크박스로 스핀박스를 활성/비활성화하는 것, 버튼 클릭이 실제로 `maroStartBridge`/`maroStopBridge`를 부르는 것, `ROS_DOMAIN_ID` 환경변수가 실제로 `rclcpp::init()`에 반영되는지는 Qt/실제 rclcpp 컨텍스트가 필요해 mayapy 배치로 검증 불가능 — `docs/maro-main-ui-manual-checklist.md`에 새 절을 추가해 대화형 Maya에서 검증한다. 도메인 ID 반영 여부는 이 체크리스트의 go/no-go 항목으로 표시한다(§3.5의 실측 필요 사항).

## 5. 범위 밖

- 진단/book 저장 경로 설정(§3.4에서 이유와 함께 명시적으로 제외).
- ROS 연결 상태를 상시 표시하는 상태 표시줄/인디케이터 — 기존 커맨드의 콘솔 경고로 대체.
- `maroStartBridge`/`maroStopBridge` 외의 새 C++ 커맨드.
- 도메인 ID를 `os.environ` 대신 C++ 쪽에서 직접 받는 방식(예: `maroStartBridge`에 `-domainId` 플래그 추가) — 환경변수 경유가 실측에서 동작하지 않는 것으로 밝혀지면 이 대안을 별도로 재검토한다.
- 다른 서브시스템(예: LiDAR 프리뷰 디시메이션 상한, 축 리밋 등)의 값을 이 설정 창으로 옮기는 것 — 이번엔 사용자가 명시적으로 고른 두 가지(ROS 연결, Tech Diag 임계값)만 다룬다.
