"""스켈레톤 업로드/추출 -- 로드맵 Phase 6(설계 스펙
docs/superpowers/specs/2026-09-02-maro-skeleton-upload-design.md).

순수 Python + 표준 Maya 커맨드로만 구성된다 -- 새 커스텀 노드 타입도, 새
C++ 코드도 필요 없다. skinCluster가 있으면 그 인플루언스 조인트를 찾아
선택해 주고, 없으면 바운딩박스 중심에 루트 조인트 1개를 만든다. 이 기능은
거기까지만 책임진다 -- 만들어진/찾아진 조인트에 maroAxis를 부여하는 것은
여전히 사용자가 각 조인트를 우클릭해 기존 "Maro node editor" 마킹메뉴로
하나씩 한다(자동 리깅 아님).

이 파일의 함수들(extractSkeleton/_isSingleMeshSelected/
_findMeshInAssemblies)은 Maya 커맨드만 쓰는 순수 함수라 mayapy 배치 모드에서
QWidget 없이 계약을 검증할 수 있다. Qt 다이얼로그는 이 파일에 나중에(Task 2)
추가된다 -- maroTechDiag.py와 같은 관례로, 모듈 자체는 PySide6를 import해도
안전하지만(위젯을 실제로 만들지 않는 한) 이 태스크는 아직 위젯을 만들지
않는다.
"""
import maya.cmds as cmds


def extractSkeleton(mesh):
    """mesh(메쉬 셰이프를 가진 오브젝트 하나, 풀 경로 권장)에서 스켈레톤을
    찾거나 만든다.

    skinCluster가 있으면 그 인플루언스 조인트를 그대로 cmds.select()하고
    그 목록을 돌려준다 -- 새 노드는 전혀 만들지 않는다. skinCluster는
    있지만 인플루언스가 하나도 없는 퇴화 상태면 경고만 내고 None을
    돌려준다(아래로 조용히 폴백하지 않는다 -- 그러면 깨진 skinCluster를
    "스킨 없음"으로 오판해 엉뚱한 루트 조인트를 만들게 된다). skinCluster가
    아예 없으면 mesh의 월드 바운딩박스 중심에 새 joint 노드 1개를 만들어
    mesh의 자식으로 붙이고 선택한다.

    호출자가 mesh를 실제 메쉬 셰이프를 가진 단일 오브젝트로 이미 검증했다고
    가정한다 -- 이 함수 자체는 그 검증을 하지 않는다(호출부 두 곳이 각자
    다른 방식으로 후보를 좁히므로 검증 지점을 여기 하나로 모으지 않는다.
    _isSingleMeshSelected/_findMeshInAssemblies 참고).
    """
    skinClusters = cmds.ls(cmds.listHistory(mesh) or [], type="skinCluster")
    if skinClusters:
        influences = cmds.skinCluster(skinClusters[0], query=True, influence=True) or []
        if not influences:
            cmds.warning(
                "Maro: '{}' has a skinCluster ('{}') but it has no influence "
                "joints -- not falling back to a generated root joint, since "
                "that would hide a broken skinCluster.".format(mesh, skinClusters[0]))
            return None
        # [실측으로 발견] cmds.skinCluster(query=True, influence=True)는 이름이
        # 유일하면 짧은 이름("rootJoint")을 준다 -- cmds.ls(..., long=True)로
        # 확정한 다른 분기의 rootJointFullPath와 형태가 안 맞아서, 호출자가
        # cmds.select() 뒤 cmds.ls(selection=True, long=True)로 비교하면
        # (같은 노드인데도) 절대 같은 집합이 되지 않는다. 그래서 select와
        # 반환 둘 다 항상 풀 경로로 정규화한다.
        influences = cmds.ls(influences, long=True)
        cmds.select(influences, replace=True)
        return influences

    bbox = cmds.exactWorldBoundingBox(mesh)
    center = ((bbox[0] + bbox[3]) / 2.0, (bbox[1] + bbox[4]) / 2.0,
              (bbox[2] + bbox[5]) / 2.0)
    shortName = mesh.split("|")[-1]
    # cmds.joint()가 아니라 cmds.createNode("joint")를 쓴다 -- cmds.joint()는
    # 대화형 Joint Tool 커맨드라 현재 선택된 조인트가 있으면 그 자식으로
    # 체인을 이어 버린다(전역 제약 참고). createNode는 그런 부작용 없이
    # 항상 독립된 새 조인트를 만든다.
    rootJoint = cmds.createNode("joint", name=shortName + "_root")
    # [실측으로 발견] cmds.parent() 뒤에는 옮기기 전의 이름(rootJoint)이 더
    # 이상 유효하지 않을 수 있다 -- 같은 mesh에 대해 이 함수를 두 번째로
    # 부르면(테스트의 "재클릭" 케이스) mesh 밑에 이미 같은 이름의 자식
    # ("<mesh>_root")이 있으므로, 새로 옮겨 오는 조인트가 그 자리에서
    # 형제 이름 충돌을 피하려고 Maya가 자동으로 다른 이름("<mesh>_root1")
    # 으로 바꿔 버린다. 그러면 cmds.ls(rootJoint, long=True)는 빈 리스트를
    # 주어 [0]에서 IndexError가 난다(mayapy로 재현 확인). maroDagMenu.py의
    # 여러 곳(_createPlaceholderTargetMesh 등)이 같은 이유로 쓰는 것과 같은
    # 관용구로, cmds.parent()가 돌려주는 새 이름과 이미 알고 있는 새 부모를
    # 조합해 모호하지 않은 새 풀 경로를 직접 구성한다.
    # [Fix round 1] cmds.parent()가 돌려주는 값은 항상 "짧은 이름"이 아니다
    # -- 새로 옮겨진 조인트와 같은 짧은 이름을 가진 노드가 씬 어디에든(새
    # 부모의 형제가 아니어도) 존재하면, Maya는 그 이름이 씬 전체에서
    # 모호해졌다고 보고 대신 부분 경로("<다른부모>|<짧은이름>")를 돌려준다
    # (mayapy로 재현 확인). 그걸 그대로 "|"로 이어 붙이면
    # "<mesh풀경로>|<다른부모>|<짧은이름>" 같은 존재하지 않는 경로가 만들어진다.
    # maroDagMenu.py._createPlaceholderTargetMesh가 이미 쓰는 것과 같은
    # 관용구로, 뒤에 .split("|")[-1]을 붙여 반환값이 짧은 이름이든 부분
    # 경로든 상관없이 항상 마지막 짧은-이름 성분만 뽑아낸다.
    newShortName = cmds.parent(rootJoint, mesh)[0].split("|")[-1]
    meshFullPath = cmds.ls(mesh, long=True)[0]
    rootJointFullPath = meshFullPath + "|" + newShortName
    cmds.xform(rootJointFullPath, worldSpace=True, translation=center)
    cmds.select(rootJointFullPath, replace=True)
    return [rootJointFullPath]


def _isSingleMeshSelected(selection):
    """selection(예: cmds.ls(selection=True, long=True)의 결과)이 메쉬
    셰이프를 가진 오브젝트 정확히 하나인가."""
    if len(selection) != 1:
        return False
    return bool(cmds.listRelatives(selection[0], shapes=True, type="mesh"))


def _findMeshInAssemblies(assemblies):
    """assemblies(최상위 오브젝트 이름 목록, 예: 임포트 직후 새로 생긴
    것들) 전체 서브트리에서 처음 발견되는 메쉬 셰이프의 부모 트랜스폼(풀
    경로). 메쉬가 하나도 없으면 None."""
    if not assemblies:
        return None
    meshShapes = cmds.listRelatives(
        assemblies, allDescendents=True, fullPath=True, type="mesh") or []
    if not meshShapes:
        return None
    return cmds.listRelatives(meshShapes[0], parent=True, fullPath=True)[0]
