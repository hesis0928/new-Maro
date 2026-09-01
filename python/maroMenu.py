"""Maro 최상위 메뉴 -- Maya 메인 메뉴바에 "Maro" 메뉴를 만든다.

`build()`는 멱등이다: 이미 메뉴가 있으면 아무것도 하지 않는다(대화형 Maya에서
플러그인을 재로드하거나 -uiScript 경로가 여러 번 도는 경우를 대비한 것 --
maroMainWindow.py의 _deleteStalePanel()과 같은 동기).

**배치 모드(mayapy)에서는 이 함수가 실질적으로 아무것도 만들지 않는다.**
실측(2026-08-24, Maya 2026, tests/maya에서 직접 확인): 배치 모드에는 실제
Maya 메인 윈도우가 없으므로 `MayaWindow`라는 이름의 컨트롤 자체가 존재하지
않는다. 그런데 `cmds.menu(parent="MayaWindow", ...)`와 `cmds.menuItem(...)`
는 그 상황에서 파이썬 예외를 던지지 않는다 -- 그냥 아무것도 만들지 않고
`False`를 돌려준다(workspaceControl이 배치 모드에서 하는 것과 정확히 같은
동작, maroMainWindow.py의 show() 참고). `cmds.menu(..., exists=True)`도
계속 `False`이므로 위 멱등성 가드도 걸리지 않고 매번 끝까지 진행되지만,
매번 아무것도 만들지 않으므로 무해하다.

그래서 이 모듈은 `cmds.about(batch=True)` 가드를 두지 않는다(브리프가 허용한
두 옵션 중 첫 번째를 선택) -- 배치 모드가 이미 스스로 안전하게 no-op이기
때문에 별도 분기가 검증할 것이 없다. `maroBuildMenu` 커맨드도 이 호출
연쇄가 파이썬 예외를 던지지 않는 한 성공을 보고한다(MaroPythonBridge.cpp의
executePythonCommand가 예외 없는 실행을 성공으로 본다) -- 배치 테스트는
그래서 "메뉴가 실제로 존재한다"가 아니라 "커맨드가 예외 없이 끝난다"만
확인한다(tests/maya/test_main_menu.py 참고).
"""
import maya.cmds as cmds

# MaroPluginMain.cpp의 uninitializePlugin이 언로드할 때 이 이름을 MEL로
# 다시 부른다(`menu -exists maroMainMenu` / `deleteUI -menu maroMainMenu`) --
# 두 곳이 같은 문자열에 묶여 있으므로 tests/maya/test_main_menu.py가 그
# 계약을 값으로 고정한다.
MENU_NAME = "maroMainMenu"


def build():
    """maroBuildMenu 커맨드가 부른다. 이미 메뉴가 있으면 아무것도 안 한다."""
    if cmds.menu(MENU_NAME, exists=True):
        return
    cmds.menu(MENU_NAME, parent="MayaWindow", label="Maro", tearOff=False)
    # [최종 리뷰 I6] Maya는 이 문자열을 __main__ 네임스페이스에서 실행한다.
    # cmds가 거기 이미 바인딩돼 있다는 보장이 없다(대화형 세션에서는 보통
    # 되지만, Maya 자신의 코드도 이걸 가정하지 않는다 --
    # maya/app/stereo/cameraSetTool.py처럼 import를 커맨드 문자열 안에
    # 직접 넣는다). 같은 패턴을 따른다.
    cmds.menuItem(label="Maro 창 열기",
                  command="import maya.cmds as cmds\ncmds.maroMainWindow()",
                  parent=MENU_NAME)
    cmds.menuItem(divider=True, parent=MENU_NAME)
    cmds.menuItem(label="Skeleton Upload...",
                  command="import maroSkeletonUpload\nmaroSkeletonUpload.show()",
                  parent=MENU_NAME)
    cmds.menuItem(divider=True, parent=MENU_NAME)
    cmds.menuItem(label="ROS 연결 설정 (준비 중)", enable=False, parent=MENU_NAME)
    cmds.menuItem(label="환경설정 (준비 중)", enable=False, parent=MENU_NAME)
