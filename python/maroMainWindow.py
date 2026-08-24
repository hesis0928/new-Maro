"""Maro 메인 창 — 네이티브 컨테이너 안에 modelPanel + PySide6 위젯 (Phase 0-1 스파이크).

이 모듈이 증명하려는 것 하나: **컨테이너를 끝까지 네이티브로 유지한 채**
(workspaceControl + formLayout, maroDiagPanel과 같은 패턴) 그 안에
`cmds.modelPanel()`로 진짜 3D 뷰포트를 직접 만들고, 커스텀 PySide6 위젯만
`MQtUtil.addWidgetToMayaLayout()`로 같은 폼레이아웃에 끼워 넣어도, 둘이
공존하고 플러그인을 언로드해도 Maya가 죽지 않는다는 것(설계 스펙 §4.2).

인터넷에 흔한 반대 방향(모델패널을 만든 뒤 Maya가 만든 부모에서 뜯어내
손으로 만든 QMainWindow에 옮겨 붙이기)은 Autodesk가 안정성을 보장하지 않는
리페어런팅이다. 여기서는 리페어런팅을 하지 않는다.

`setStyleSheet()`를 부르지 않는다 — 한 프로세스의 QApplication은 팔레트/
스타일을 하나만 쓰므로, 아무 것도 안 하는 것이 곧 "기존 mayaUI와 이질감이
없다"이다(설계 스펙 §4.2). 이 규율은 grep으로 기계적으로 점검할 수 있고,
tests/maya/test_main_window.py가 실제로 그렇게 점검한다.

**배치 모드(mayapy)에서는 이 파일의 buildUI()를 절대 부르면 안 된다.**
실측(2026-08-24, Maya 2026): 배치 mayapy의 전역 애플리케이션 객체는
QApplication이 아니라 QGuiApplication이라, QWidget을 하나라도 생성하는
순간 Qt가 프로세스를 abort시킨다(파이썬 예외가 아니라 종료 코드 9로
프로세스가 통째로 죽는다 -- 잡을 수 없다). 그래서 buildUI()는 맨 앞에서
배치 모드를 명시적으로 거절한다: 프로세스 abort 대신 잡을 수 있는 예외로
바꿔 두는 것이 이 가드의 전부다. 실제로는 배치 모드에 UI가 없어
workspaceControl 자체가 만들어지지 않으므로(-uiScript가 돌지 않는다)
show() 경로로는 여기 도달하지 않는다.
"""
import maya.cmds as cmds
import maya.OpenMayaUI as omui
import shiboken6
from PySide6 import QtWidgets

# 이 세 이름은 C++와의 계약이다. MaroPluginMain.cpp의 uninitializePlugin이
# 언로드할 때 이 이름들을 MEL로 다시 부른다(창을 띄운 채 언로드하면 Maya가
# 사라진 코드의 UI를 계속 붙들기 때문 -- maroDiagPanel과 같은 이유, 같은
# 처리). 바꾸면 양쪽을 함께 고쳐야 한다.
CONTROL_NAME = "maroMainWindowControl"
VIEWPORT_NAME_MAYA = "maroMainWindowViewportMaya"
VIEWPORT_NAME_ROS = "maroMainWindowViewportRos"

# 끼워 넣은 PySide6 위젯을 컨트롤 이름별로 하나씩만 붙들어 둔다.
#
# 왜: addWidgetToMayaLayout는 위젯을 네이티브 레이아웃의 QWidget 아래로
# 리페어런트한다 -- 그 순간 소유권이 C++로 넘어가므로 파이썬 래퍼가 GC돼도
# C++ 객체는 살아 있다. 그래도 참조를 하나 남기는 이유는 "리페어런트가
# 끝나기 전에 GC가 먼저 돌 수 있다"는 창 하나를 아예 없애기 위해서다(Maya
# Qt 코드의 관행이기도 하다). 컨트롤 이름을 키로 덮어쓰므로 창을 여러 번
# 다시 만들어도 자라지 않는다. 언로드로 C++ 위젯이 지워지면 여기 남은
# 래퍼는 shiboken이 무효화하고, 우리는 그 뒤로 이것을 다시 만지지 않는다.
_EMBEDDED = {}


def _onTestButtonClicked():
    """스파이크의 확인 지점 -- 클릭이 파이썬까지 도달했는지만 본다.

    (모듈 수준 함수로 둔다: 위젯을 캡처하는 클로저를 시그널에 매달면 창이
    사라진 뒤에도 그 위젯을 붙들게 된다.)
    """
    print("Maro main window: button clicked")


def _hideViewportChrome(panel):
    """뷰포트의 메뉴바와 아이콘 바를 접는다.

    플래그 이름은 추측하지 않고 실제로 확인했다(`help modelPanel`,
    Maya 2026): 메뉴바는 `-menuBarVisible`(-mbv), 아이콘 바는 그 자체가
    별도 컨트롤이라 숨기는 플래그가 없고 `-barLayout`(-bl) 질의로 이름을
    얻어 frameLayout으로 접어야 한다. 아래 세 줄은 Autodesk 자신의
    toggleModelEditorBarsInAllPanels.mel이 하는 것과 같다(그 스크립트가
    Maya 설치본 scripts/others/에 있다) -- exists 가드까지 그대로 옮겼다.
    """
    cmds.modelPanel(panel, edit=True, menuBarVisible=False)
    bar = cmds.modelPanel(panel, query=True, barLayout=True)
    if bar and cmds.frameLayout(bar, query=True, exists=True):
        cmds.frameLayout(bar, edit=True, collapse=True)


def _deleteStalePanel(panelName):
    """같은 이름의 modelPanel이 남아 있으면 지운다.

    modelPanel은 부모 레이아웃의 자식이면서 동시에 Maya의 전역 패널
    레지스트리에 등록되는 객체다 -- 부모가 사라져도 등록이 남아 있을 수
    있고, 그러면 다음 buildUI()의 생성이 이름 충돌로 실패한다.
    workspaceControl은 -uiScript로 재생성되므로(도킹/복원/플러그인 재로드)
    buildUI()는 한 세션에 여러 번 불릴 수 있다. 뷰포트가 두 개(Phase 2)라
    호출하는 쪽에서 이름을 넘긴다.
    """
    if cmds.modelPanel(panelName, exists=True):
        cmds.deleteUI(panelName, panel=True)


def _buildLabeledViewport(parent, label, panelName):
    """`parent`(paneLayout의 한 칸) 안에 라벨 한 줄 + modelPanel 하나를 쌓는다.

    Phase 0-1의 단일 뷰포트 조립을 두 번 반복하는 대신 함수로 뽑았다 --
    Maya/ROS 두 뷰포트가 라벨 문구만 다르고 나머지 조립(스테일 패널 정리,
    chrome 숨김, formLayout attach)은 완전히 같기 때문이다. 반환값은
    formLayout attach에 쓸 수 있는 패널의 **컨트롤** 이름이다(패널 이름
    자체가 아니다 -- Phase 0-1의 같은 주석 참고).
    """
    side = cmds.formLayout(parent=parent)
    labelControl = cmds.text(label=label, parent=side)

    _deleteStalePanel(panelName)
    panel = cmds.modelPanel(panelName, parent=side)
    _hideViewportChrome(panel)
    panelControl = cmds.modelPanel(panel, query=True, control=True) or panel

    cmds.formLayout(
        side, edit=True,
        attachForm=[
            (labelControl, "top", 2), (labelControl, "left", 2), (labelControl, "right", 2),
            (panelControl, "left", 0), (panelControl, "right", 0), (panelControl, "bottom", 0),
        ],
        attachControl=[(panelControl, "top", 2, labelControl)])
    return panelControl


def buildUI():
    """workspaceControl이 -uiScript로 부른다."""
    # 모듈 도크스트링 참고: 배치 모드에서 QWidget을 만들면 프로세스가
    # abort한다. 잡을 수 있는 예외로 바꿔 둔다.
    if cmds.about(batch=True):
        raise RuntimeError(
            "maroMainWindow.buildUI() needs an interactive Maya session -- "
            "batch mayapy has no QApplication, so creating a QWidget there "
            "aborts the process.")

    form = cmds.formLayout()

    pane = cmds.paneLayout(configuration="vertical2", parent=form)
    mayaPanelControl = _buildLabeledViewport(pane, "Maya", VIEWPORT_NAME_MAYA)
    rosPanelControl = _buildLabeledViewport(pane, "ROS", VIEWPORT_NAME_ROS)

    # --- 여기부터가 이 스파이크의 핵심 두 줄 -----------------------------
    # MQtUtil의 파이썬 바인딩은 QWidget*를 **정수 포인터**로 주고받는다.
    # 실측으로 확인했다(Maya 2026):
    #   - findLayout(name)  -> int(포인터) 또는 None(못 찾음)
    #   - addWidgetToMayaLayout(long control, long layout) -> str
    #     (문자열/QWidget 객체를 주면 "Expected argument of type long")
    # 그래서 플랜이 적어 둔 shiboken6.wrapInstance는 필요 없다 --
    # findLayout이 돌려준 정수를 그대로 두 번째 인자로 넘긴다. 위젯 쪽만
    # shiboken6.getCppPointer(w)[0]으로 정수 포인터를 뽑는다.
    #
    # 돌려받는 문자열은 끼워 넣은 위젯의 **Maya UI 이름**이다 -- 그래서
    # 아래 formLayout attach에 네이티브 컨트롤과 똑같이 쓸 수 있다. 이것이
    # "컨테이너는 네이티브로 유지한다"는 결정이 실제로 성립하는 지점이다.
    button = QtWidgets.QPushButton("테스트")
    button.setObjectName("maroMainWindowTestButton")
    button.clicked.connect(_onTestButtonClicked)

    layoutPtr = omui.MQtUtil.findLayout(cmds.control(form, query=True, fullPathName=True))
    if layoutPtr is None:
        raise RuntimeError(
            "maroMainWindow: MQtUtil.findLayout() could not resolve the root "
            "formLayout {!r} -- cannot embed the PySide6 widget.".format(form))
    # int()로 감싸는 것은 devkit 자신의 파이썬 예제가 하는 그대로다
    # (devkit/pythonScripts/dockableWorkspaceWidget.py:66) -- 바인딩이
    # 버전에 따라 int가 아닌 정수형 객체를 줄 수 있어서다.
    buttonName = omui.MQtUtil.addWidgetToMayaLayout(
        int(shiboken6.getCppPointer(button)[0]), int(layoutPtr))
    if not buttonName:
        raise RuntimeError(
            "maroMainWindow: MQtUtil.addWidgetToMayaLayout() returned no UI name.")
    _EMBEDDED[CONTROL_NAME] = button
    # ---------------------------------------------------------------------

    # 버튼은 위쪽 좁은 띠, 뷰포트가 나머지 전부. 정확한 비율은 스파이크
    # 목적상 중요하지 않다 -- 중요한 것은 네이티브 attachForm/attachControl이
    # 끼워 넣은 Qt 위젯을 다른 네이티브 컨트롤과 똑같이 다룬다는 사실이다.
    #
    # 이 한 줄이 이 설계 전체가 성립하는지를 가르는 지점이라 실패를 그냥
    # 흘려보내지 않는다: 사람이 수동 체크리스트를 돌리다 여기서 막히면
    # 원래 Maya 오류만으로는 무엇이 문제인지 알기 어렵다.
    try:
        cmds.formLayout(
            form, edit=True,
            attachForm=[
                (buttonName, "top", 4), (buttonName, "left", 4), (buttonName, "right", 4),
                (pane, "left", 0), (pane, "right", 0), (pane, "bottom", 0),
            ],
            attachControl=[(pane, "top", 4, buttonName)])
    except RuntimeError as error:
        raise RuntimeError(
            "maroMainWindow: the native formLayout refused to lay out the "
            "embedded widget ({!r}) next to the dual-viewport pane ({!r}): {} "
            "-- see docs/maro-main-ui-manual-checklist.md".format(
                buttonName, pane, error))
    return form


def show():
    """maroMainWindow 커맨드가 부른다."""
    if cmds.workspaceControl(CONTROL_NAME, exists=True):
        cmds.workspaceControl(CONTROL_NAME, edit=True, restore=True)
        return
    cmds.workspaceControl(
        CONTROL_NAME,
        label="Maro",
        retain=False,
        floating=True,
        initialWidth=900,
        initialHeight=600,
        requiredPlugin="maro",
        uiScript="import maroMainWindow; maroMainWindow.buildUI()")
