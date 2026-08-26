"""테크 Diag -- 기구학/ROS 정합성 능동 검증 (설계 스펙 2026-08-26-maro-tech-diag-design.md).

기존 boad/book 디버깅 Diag와 완전히 독립된 서브시스템이다. 새 C++ 커맨드나
DG 어트리뷰트 없이 기존 maroListAxisNodes 조회 + cmds.getAttr(+ 단위 변환용
maya.api.OpenMaya의 MAngle/MDistance)만으로 동작한다. 검사 결과는 실행할
때마다 새로 계산되고 저장되지 않는다.

검사/파싱 함수(`sliceAxisTechRows`, `sliceCapabilityTechRows`,
`checkLimitProximity`, `checkJointStatesIntegrity`, `checkMeshCollisions`,
`adjacentMeshPairs`, `filterAdjacentMeshCollisions`,
`suggestDisambiguatedJointName`)는 Maya
호출을 하나도 하지 않는 순수 함수라 mayapy 배치 모드에서 QWidget 없이 계약을
검증할 수 있다. 다만 **모듈 자체**는 순수하지 않다 -- 아래 `_run*Checks`/
구제 함수/사이드 패널이 모듈 스코프에서 `maya.cmds`, `maya.api.OpenMaya`,
`PySide6.QtWidgets`를 import하므로, 이 모듈을 import하는 것만으로도 셋 다
사용 가능해야 한다(= mayapy 안에서만 import된다).
"""

import itertools

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from PySide6 import QtWidgets

LIMIT_PROXIMITY_THRESHOLD = 0.9

# C++ 쪽 계약. maroObjectNodeEditor.py/maroSingleObjectNodeEditor.py도 각자
# 독립적으로 같은 값을 선언한다 -- 순환 import를 피하기 위한 이 프로젝트의
# 기존 관례.
AXIS_FIELDS = 10
CAPABILITY_FIELDS = 5


def sliceAxisTechRows(flat):
    """maroListAxisNodes()의 평탄한 배열에서 이 모듈이 필요로 하는 필드만
    뽑아 축 행 딕셔너리 목록으로 되돌린다."""
    if flat is None:
        return []
    if len(flat) % AXIS_FIELDS != 0:
        raise ValueError(
            "axis row array length {} is not a multiple of {}".format(
                len(flat), AXIS_FIELDS))
    rows = []
    for i in range(len(flat) // AXIS_FIELDS):
        f = flat[i * AXIS_FIELDS:(i + 1) * AXIS_FIELDS]
        rows.append({
            "axisFullPath": f[0],
            "jointName": f[1],
            "boundTargetPath": f[2],
            # f[3]은 부모 축 노드의 full DAG path(없으면 ""). 메쉬 충돌
            # 검사에서 조상/자손 관계인 링크 쌍 전체를 걸러내는 데 쓴다.
            "parentAxisPath": f[3],
            "enabled": f[5] == "1",
            "conventionAxis": int(f[6]),
            "capabilityCount": int(f[7]),
        })
    return rows


def sliceCapabilityTechRows(flat):
    """maroListAxisNodes(capabilities=axis)의 평탄한 배열에서 이 모듈이
    필요로 하는 필드만 뽑아 capability 행 딕셔너리 목록으로 되돌린다."""
    if flat is None:
        return []
    if len(flat) % CAPABILITY_FIELDS != 0:
        raise ValueError(
            "capability row array length {} is not a multiple of {}".format(
                len(flat), CAPABILITY_FIELDS))
    rows = []
    for i in range(len(flat) // CAPABILITY_FIELDS):
        f = flat[i * CAPABILITY_FIELDS:(i + 1) * CAPABILITY_FIELDS]
        rows.append({
            "logicalIndex": int(f[0]),
            "capType": int(f[3]),
            "connected": f[4] == "1",
        })
    return rows


def checkLimitProximity(axisRows, capabilityRowsByAxis, currentValueByAxis):
    """리밋(capType 1 또는 5)이 있는 축마다, 현재 구동값이 min/max 범위의
    LIMIT_PROXIMITY_THRESHOLD 이상 근접했으면 경고를 낸다. conventionAxis로
    capMin/capMax/capEnable의 X/Y/Z 중 어느 성분이 이 축에 해당하는지 고른다."""
    findings = []
    for axisRow in axisRows:
        axis = axisRow["axisFullPath"]
        currentValue = currentValueByAxis.get(axis)
        if currentValue is None:
            continue
        idx = axisRow["conventionAxis"]
        for capRow in capabilityRowsByAxis.get(axis, []):
            if capRow["capType"] not in (1, 5):
                continue
            if not capRow["capEnable"][idx]:
                continue
            minV = capRow["capMin"][idx]
            maxV = capRow["capMax"][idx]
            span = maxV - minV
            if span <= 0:
                continue
            proximity = (currentValue - minV) / span
            nearMax = proximity >= LIMIT_PROXIMITY_THRESHOLD
            nearMin = proximity <= (1.0 - LIMIT_PROXIMITY_THRESHOLD)
            if nearMax or nearMin:
                # 어느 쪽 끝에 붙었는지, 지금 값이 얼마인지, 어느 capability
                # 슬롯이 건 리밋인지를 전부 요약에 담는다. 해법 버튼이 없는
                # "설명만" 항목이라 요약 문자열이 사용자가 받는 정보의
                # 전부이고, 한 축에 리밋 슬롯이 여러 개면 슬롯 인덱스가
                # 없을 경우 결과가 글자 하나 안 틀리고 똑같아진다.
                # 이 함수는 Maya를 부르지 않는다 -- 아래 값들은 전부 인자로
                # 이미 들어와 있다.
                boundLabel = "max" if nearMax else "min"
                boundValue = maxV if nearMax else minV
                findings.append({
                    "category": "limitProximity",
                    "severity": "warning",
                    "summary": (
                        "{}: capability[{}] current value {:.4f} is within {:.0f}% of its "
                        "{} limit {:.4f} (range {:.4f}..{:.4f})".format(
                            axis, capRow["logicalIndex"], currentValue,
                            (1.0 - LIMIT_PROXIMITY_THRESHOLD) * 100,
                            boundLabel, boundValue, minV, maxV)),
                    "axis": axis,
                    "remedy": None,
                })
    return findings


def checkJointStatesIntegrity(axisRows):
    """활성화+바인딩된 축의 jointName 공백/중복, 그리고 활성화됐지만 1차
    구동 capability가 없는 축을 찾는다."""
    findings = []
    seenJointNames = {}
    for row in axisRows:
        if not row["enabled"] or not row["boundTargetPath"]:
            continue
        axis = row["axisFullPath"]
        jointName = row["jointName"]
        if not jointName:
            findings.append({
                "category": "emptyJointName",
                "severity": "warning",
                "summary": "{}: jointName is empty".format(axis),
                "axis": axis,
                "remedy": None,
            })
        else:
            if jointName in seenJointNames:
                findings.append({
                    "category": "duplicateJointName",
                    "severity": "warning",
                    "summary": "{}: jointName '{}' duplicates {}".format(
                        axis, jointName, seenJointNames[jointName]),
                    "axis": axis,
                    "remedy": None,
                })
            else:
                seenJointNames[jointName] = axis
        if row["capabilityCount"] == 0:
            findings.append({
                "category": "noDriverActiveAxis",
                "severity": "warning",
                "summary": "{}: enabled and bound but has no capability driving it".format(axis),
                "axis": axis,
                "remedy": None,
            })
    return findings


def _boxesOverlap(a, b):
    """두 AABB(xmin,ymin,zmin,xmax,ymax,zmax)가 실제로 겹치는지(맞닿기만
    하는 건 제외-- 부등호를 엄격하게 잡는다)."""
    return (a[0] < b[3] and b[0] < a[3] and
            a[1] < b[4] and b[1] < a[4] and
            a[2] < b[5] and b[2] < a[5])


def checkMeshCollisions(boundingBoxesByMesh):
    """모든 메쉬 쌍에 대해 월드 바운딩박스(AABB) 겹침을 검사한다."""
    findings = []
    meshes = sorted(boundingBoxesByMesh.keys())
    for meshA, meshB in itertools.combinations(meshes, 2):
        if _boxesOverlap(boundingBoxesByMesh[meshA], boundingBoxesByMesh[meshB]):
            findings.append({
                "category": "meshCollision",
                "severity": "warning",
                "summary": "{} and {} bounding boxes overlap".format(meshA, meshB),
                "axis": None,
                "meshes": (meshA, meshB),
                "remedy": None,
            })
    return findings


_MAX_ANCESTOR_CHAIN_DEPTH = 1024


def _ancestorAxes(axis, parentByAxis):
    """`axis`의 부모, 조부모, ... 를 뿌리까지 전부 모은 리스트.

    `parentAxisPath` 체인을 한 번만 따라가는 게 아니라 끝까지 걷는다 --
    아래 `adjacentMeshPairs()`의 도크스트링 참고. 씬이 깨져서 부모 체인이
    순환하면(이론상 있어서는 안 되지만, 손상된 씬 파일이 만들 수 있다)
    무한 루프에 빠지지 않도록 방문한 축을 추적해 재방문 시 멈추고, 추가로
    `_MAX_ANCESTOR_CHAIN_DEPTH` 깊이에서도 강제로 멈춘다."""
    ancestors = []
    visited = {axis}
    current = parentByAxis.get(axis)
    depth = 0
    while current and depth < _MAX_ANCESTOR_CHAIN_DEPTH:
        if current in visited:
            break
        ancestors.append(current)
        visited.add(current)
        current = parentByAxis.get(current)
        depth += 1
    return ancestors


def adjacentMeshPairs(axisRows):
    """서로 조상/자손 관계인 축 쌍에 각각 바인딩된 메쉬 쌍의 집합.

    `maroAxis`는 `parentAxis`(message)로 명시적인 축 체인을 갖고, Maya의
    `exactWorldBoundingBox()`는 그 트랜스폼의 DAG 자손을 전부 포함한다 --
    직속 자식 하나만이 아니라 전부다. 그래서 링크 메쉬가 DAG로 중첩된 흔한
    리깅에서는, 3단 체인 조부모->부모->자식이라면 조부모 링크의 월드 AABB가
    부모 링크뿐 아니라 자식 링크까지 통째로 품는다. 인접(직속 부모-자식)
    쌍만 걸러내면 조부모-자식처럼 한 단계 건너뛴 조상/자손 쌍은 그대로
    남아 여전히 잡음 충돌을 낸다 -- N단 체인이면 원래 N(N-1)/2쌍 중
    N-1쌍만 걸러지고 나머지가 그대로 통과한다. 그래서 각 축마다
    `parentAxisPath` 체인을 뿌리까지 전부 따라가(`_ancestorAxes()`) 어느
    조상과도 이루는 쌍을 전부 뽑는다. 이 쌍들을 미리 뽑아
    `filterAdjacentMeshCollisions()`로 걸러낸다.

    Maya를 부르지 않는 순수 함수다(축 행에 이미 들어 있는 필드만 본다)."""
    targetByAxis = {row["axisFullPath"]: row["boundTargetPath"] for row in axisRows}
    parentByAxis = {row["axisFullPath"]: row.get("parentAxisPath") for row in axisRows}
    pairs = set()
    for row in axisRows:
        axis = row["axisFullPath"]
        mesh = row["boundTargetPath"]
        if not mesh:
            continue
        for ancestorAxis in _ancestorAxes(axis, parentByAxis):
            ancestorMesh = targetByAxis.get(ancestorAxis)
            if not ancestorMesh or ancestorMesh == mesh:
                continue
            pairs.add(frozenset((mesh, ancestorMesh)))
    return pairs


def filterAdjacentMeshCollisions(findings, pairs):
    """`checkMeshCollisions()` 결과에서 조상/자손 관계인 메쉬 쌍의 항목을 뺀다.

    필터링을 `checkMeshCollisions()` 안이 아니라 여기에 두는 이유: 그
    함수의 계약("박스들을 주면 겹치는 것을 찾아준다")은 그 자체로 여전히
    옳다 -- 축의 부모 관계를 아는 것은 씬을 읽는 호출자(`_runMayaSideChecks`)
    쪽이다."""
    return [f for f in findings if frozenset(f["meshes"]) not in pairs]


def suggestDisambiguatedJointName(jointName, taken=None):
    """중복된 jointName에 붙일 접미사 제안. `taken`(이미 쓰이는 이름들)이
    주어지면 거기에 없는 이름이 나올 때까지 `_2`, `_3`, ... 로 올린다 --
    같은 이름을 쓰는 축이 셋 이상일 때 제안 자체가 또 다른 충돌을 만드는
    것을 막는다. `taken` 없이 부르면 종전대로 `_2`."""
    takenNames = set(taken) if taken else set()
    suffix = 2
    candidate = "{}_{}".format(jointName, suffix)
    while candidate in takenNames:
        suffix += 1
        candidate = "{}_{}".format(jointName, suffix)
    return candidate


def suggestJointNameForFill(axis):
    """빈 jointName을 채울 때 제안할 이름 -- 바인딩된 타겟의 짧은 이름."""
    targets = cmds.listConnections(axis + ".targetObject", shapes=False) or []
    if not targets:
        return ""
    return targets[0].split("|")[-1]


def remedyFillEmptyJointName(axis):
    cmds.undoInfo(openChunk=True)
    try:
        cmds.setAttr(axis + ".jointName", suggestJointNameForFill(axis), type="string")
    finally:
        cmds.undoInfo(closeChunk=True)


def remedyRenameDuplicateJointName(axis, suggestedName):
    cmds.undoInfo(openChunk=True)
    try:
        cmds.setAttr(axis + ".jointName", suggestedName, type="string")
    finally:
        cmds.undoInfo(closeChunk=True)


# ---------------------------------------------------------------------------
# 사이드 패널 위젯 (설계 스펙 §5). 위 순수 함수/구제 함수와 같은 파일에
# 둔다 -- maroSingleObjectNodeEditor.py/maroObjectNodeEditor.py가 이미 쓰는
# "서브시스템별로 순수 함수와 그걸 쓰는 위젯을 한 파일에 함께 둔다" 관례를
# 따른다. 배치 mayapy에서는 QWidget 생성 자체가 프로세스를 abort시키므로
# (모듈 도크스트링과 maroMainWindow.py의 도크스트링 참고) 이 아래 클래스/
# 팩토리 함수는 자동 테스트 대상이 아니다 -- 대화형 Maya 수동 체크리스트로만
# 검증한다.
class _CheckSidePanel(QtWidgets.QWidget):
    """Maya측/ROS측 검사 사이드 패널의 공통 뼈대. setStyleSheet()를 부르지
    않는다."""

    def __init__(self, buttonLabel, runCheckFn, parent=None):
        super().__init__(parent)
        self._runCheckFn = runCheckFn
        layout = QtWidgets.QVBoxLayout(self)
        self._runButton = QtWidgets.QPushButton(buttonLabel)
        self._runButton.clicked.connect(self._onRunClicked)
        layout.addWidget(self._runButton)
        self._resultList = QtWidgets.QListWidget()
        layout.addWidget(self._resultList)
        self._findings = []

    def _onRunClicked(self):
        try:
            self._findings = self._runCheckFn()
        except Exception:  # noqa: BLE001 -- Qt 콜백 경계, 버튼 클릭마다 도는 코드가 예외를 흘리면 안 됨
            import traceback
            traceback.print_exc()
            # 검사 함수가 터진 것과 "정말 아무 문제도 없었다"를 절대로 같은
            # 화면으로 보여주면 안 된다. 아래 "문제 없음" 분기로 흘려보내지
            # 말고 여기서 끝낸다.
            self._findings = []
            self._resultList.clear()
            self._resultList.addItem("검사 실패 -- 스크립트 에디터 참조")
            return
        self._resultList.clear()
        if not self._findings:
            self._resultList.addItem("문제 없음")
            return
        for finding in self._findings:
            item = QtWidgets.QListWidgetItem(finding["summary"])
            self._resultList.addItem(item)
            if finding.get("remedy") is not None:
                applyButton = QtWidgets.QPushButton("적용")
                applyButton.clicked.connect(
                    lambda checked=False, f=finding: self._onApplyRemedy(f))
                itemWidget = QtWidgets.QWidget()
                itemLayout = QtWidgets.QHBoxLayout(itemWidget)
                itemLayout.addWidget(applyButton)
                self._resultList.setItemWidget(item, itemWidget)

    def _onApplyRemedy(self, finding):
        try:
            finding["remedy"]()
        except Exception:  # noqa: BLE001 -- 위와 같은 이유
            import traceback
            traceback.print_exc()
            # 위 _onRunClicked과 같은 원칙: 해법 적용이 터진 것과 "적용은
            # 잘 됐고 그대로 재검사한 결과"를 같은 화면으로 보여주면 안
            # 된다. 여기서 끝내지 않고 재검사(_onRunClicked)로 흘려보내면
            # 실패 이전의 stale 목록이 아무 표시 없이 그대로 남는다.
            self._resultList.clear()
            self._resultList.addItem("해법 적용 실패 -- 스크립트 에디터 참조")
            return
        self._onRunClicked()  # 적용 후 다시 검사해서 목록을 갱신


def _readCurrentValue(axis, driveIsLinear):
    """축의 현재 구동값을 **데이터블록과 같은 생 단위**(라디안/센티미터)로 읽는다.

    `position`은 `MFnUnitAttribute::kAngle`, `positionLinear`는 `kDistance`라
    `cmds.getAttr()`이 값을 **현재 UI 단위**(각도 기본값 = 도)로 돌려준다.
    반면 비교 상대인 `capabilityIn[i].capMin/capMax`는 평범한
    `MFnNumericData::k3Double`이고, `compute()`가 데이터블록의 생 라디안/
    센티미터 값을 그대로 그 경계에 클램프한다
    (`MaroCapabilityNodes.cpp`, `tests/maya/test_capability_stack.py`의
    "unit contract" 절). 그래서 `cmds.getAttr()` 값을 그대로 쓰면 도 단위
    숫자를 라디안 경계와 비교하게 된다 -- ±pi/2로 제한된 회전축이 안전한
    45도에 있어도 45.0 vs 1.5708로 비교돼 거의 모든 회전축이 경고로 뜬다.

    `cmds.currentUnit()`으로 세션 단위를 바꿔서 해결하지 않는다 -- 설계
    스펙의 "검사는 씬을 바꾸지 않는다" 제약을 어기는 전역 상태 변경이다.
    대신 UI 단위에서 생 단위로 명시적으로 변환한다."""
    attrName = ".positionLinear" if driveIsLinear else ".position"
    raw = cmds.getAttr(axis + attrName)
    if driveIsLinear:
        return om2.MDistance(raw, om2.MDistance.uiUnit()).asCentimeters()
    return om2.MAngle(raw, om2.MAngle.uiUnit()).asRadians()


def _runMayaSideChecks():
    axisRows = sliceAxisTechRows(cmds.maroListAxisNodes())
    capsByAxis = {}
    currentValueByAxis = {}
    for row in axisRows:
        axis = row["axisFullPath"]
        capFlat = cmds.maroListAxisNodes(capabilities=axis)
        capRows = []
        for capRow in sliceCapabilityTechRows(capFlat):
            if not capRow["connected"] or capRow["capType"] not in (1, 5):
                continue
            idx = capRow["logicalIndex"]
            capRows.append({
                "logicalIndex": idx,
                "capType": capRow["capType"],
                "capMin": tuple(cmds.getAttr("{}.capabilityIn[{}].capMin".format(axis, idx))[0]),
                "capMax": tuple(cmds.getAttr("{}.capabilityIn[{}].capMax".format(axis, idx))[0]),
                "capEnable": tuple(bool(v) for v in
                                   cmds.getAttr("{}.capabilityIn[{}].capEnable".format(axis, idx))[0]),
            })
        capsByAxis[axis] = capRows
        if row["enabled"] and row["boundTargetPath"]:
            driveIsLinear = cmds.getAttr(axis + ".driveIsLinear")
            currentValueByAxis[axis] = _readCurrentValue(axis, driveIsLinear)

    findings = checkLimitProximity(axisRows, capsByAxis, currentValueByAxis)

    boundMeshes = [row["boundTargetPath"] for row in axisRows
                   if row["enabled"] and row["boundTargetPath"]]
    boxes = {}
    for mesh in boundMeshes:
        bbox = cmds.exactWorldBoundingBox(mesh)
        boxes[mesh] = tuple(bbox)
    # 부모-자식 축에 물린 메쉬끼리의 겹침은 뺀다(adjacentMeshPairs 도크스트링).
    findings += filterAdjacentMeshCollisions(checkMeshCollisions(boxes),
                                             adjacentMeshPairs(axisRows))
    return findings


def _runRosSideChecks():
    axisRows = sliceAxisTechRows(cmds.maroListAxisNodes())
    findings = checkJointStatesIntegrity(axisRows)
    rowByAxis = {row["axisFullPath"]: row for row in axisRows}
    # 지금 씬에서 실제로 쓰이고 있는 모든 jointName. 제안이 다른 축의 이름과
    # 또 부딪히지 않도록 넘긴다. 이미 낸 제안도 여기에 넣어 둔다 -- 같은
    # 이름을 쓰는 축이 셋이면 두 번째는 `_2`, 세 번째는 `_3`이 돼야지 둘 다
    # `_2`를 제안해서 충돌을 옮기기만 하면 안 된다.
    takenJointNames = {row["jointName"] for row in axisRows if row["jointName"]}
    for finding in findings:
        if finding["category"] == "emptyJointName":
            axis = finding["axis"]
            finding["remedy"] = lambda a=axis: remedyFillEmptyJointName(a)
        elif finding["category"] == "duplicateJointName":
            axis = finding["axis"]
            existingName = rowByAxis[axis]["jointName"]
            suggestion = suggestDisambiguatedJointName(existingName, takenJointNames)
            takenJointNames.add(suggestion)
            finding["remedy"] = lambda a=axis, s=suggestion: remedyRenameDuplicateJointName(a, s)
    return findings


def buildMayaSidePanel():
    return _CheckSidePanel("Maya 검사 실행", _runMayaSideChecks)


def buildRosSidePanel():
    return _CheckSidePanel("ROS 검사 실행", _runRosSideChecks)
