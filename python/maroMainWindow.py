"""Maro 메인 창 — 네이티브 컨테이너 안에 modelPanel 두 개 + PySide6 위젯.

Phase 0-1 스파이크(설계 스펙 §4.2)가 증명한 것: **컨테이너를 끝까지 네이티브로
유지한 채**(workspaceControl + formLayout, maroDiagPanel과 같은 패턴) 그 안에
`cmds.modelPanel()`로 진짜 3D 뷰포트를 직접 만들고, 커스텀 PySide6 위젯만
`MQtUtil.addWidgetToMayaLayout()`로 같은 폼레이아웃에 끼워 넣어도, 둘이
공존하고 플러그인을 언로드해도 Maya가 죽지 않는다는 것. Phase 2(현재)는 그
결론 위에 뷰포트를 하나 더 놓는다 — `paneLayout(configuration="vertical2")`
안에 좌("Maya")/우("ROS") 뷰포트를 각각 라벨과 함께 배치한다(설계 스펙
`2026-08-25-maro-main-ui-phase2-dual-viewport-design.md`). 우측은 아직 좌표
변환 없이 좌측과 같은 씬을 별개 카메라로 보여줄 뿐이다.

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
EDITOR_HOST_NAME = "maroMainWindowEditorHost"

# Tech Diag(Task 4) 사이드 패널 -- C++와의 계약은 아니다(위 네 이름과 달리
# MaroPluginMain.cpp가 참조하지 않는다), _EMBEDDED 딕셔너리의 키로만 쓴다.
MAYA_SIDE_PANEL_NAME = "maroMainWindowMayaSidePanel"
ROS_SIDE_PANEL_NAME = "maroMainWindowRosSidePanel"
SIDE_PANEL_WIDTH = 180

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
    자체가 아니다 -- `modelPanel`은 패널 레지스트리의 이름이지 레이아웃이
    아니라서 `formLayout`의 attachForm/attachControl이 그 이름을 못 받는다.
    그 패널을 담고 있는 컨트롤(`modelPanel -q -control`)이 진짜 붙일 수
    있는 대상이다).
    """
    side = cmds.formLayout(parent=parent)
    labelControl = cmds.text(label=label, parent=side)

    _deleteStalePanel(panelName)
    panel = cmds.modelPanel(panelName, parent=side)
    _hideViewportChrome(panel)
    # [대화형 Maya 수동 검증에서 발견] cmds.modelPanel()로 새로 만든 패널은
    # 사용자의 전역 셰이딩 설정을 상속하지 않고 wireframe으로 떨어진다
    # (네이티브 modelPanel4는 smoothShaded인데 이 둘만 wireframe으로 나온
    # 것을 실측으로 확인). 그리드는 원래도 켜져 있었다 -- 화면에 안 보인
    # 건 줌 배율 때문이었다. 셰이딩만 명시적으로 맞춘다.
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded")
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

    outerPane = cmds.paneLayout(configuration="vertical2", parent=form)

    # Tech Diag(Task 4): 듀얼 뷰포트를 Maya측/ROS측 사이드 패널로 좌우에서
    # 감싼다. viewportRow는 outerPane의 첫 번째 칸에 들어가는 새 formLayout
    # 이고, viewportPane(및 그 내부의 두 modelPanel)은 그 안 가운데 칸으로
    # 옮겨진다 -- 내부 조립은 그대로다. _buildLabeledViewport가 이미 쓰는
    # 기법(formLayout + attachForm/attachControl)을 그대로 재사용한다.
    viewportRow = cmds.formLayout(parent=outerPane)
    viewportPane = cmds.paneLayout(configuration="vertical2", parent=viewportRow)
    # 두 호출의 반환값(각 패널의 control 이름)은 여기서 안 쓴다. Phase 3의
    # 격리/동기화는 control 이름이 아니라 **패널 이름**을 쓰기 때문이다.
    _buildLabeledViewport(viewportPane, "Maya", VIEWPORT_NAME_MAYA)
    _buildLabeledViewport(viewportPane, "ROS", VIEWPORT_NAME_ROS)

    # Tech Diag 사이드 패널 두 개를 viewportRow에 끼워 넣는다 -- 테스트
    # 버튼/ONE 위젯과 똑같은 두 단계(MQtUtil.findLayout ->
    # addWidgetToMayaLayout)를 재사용한다. import를 함수 안에서 하는 것은
    # 이 파일의 기존 관례(ONE/maroRosProxy와 같은 이유)를 따른다.
    import maroTechDiag
    mayaSidePanelWidget = maroTechDiag.buildMayaSidePanel()
    rosSidePanelWidget = maroTechDiag.buildRosSidePanel()

    viewportRowLayoutPtr = omui.MQtUtil.findLayout(
        cmds.control(viewportRow, query=True, fullPathName=True))
    if viewportRowLayoutPtr is None:
        raise RuntimeError(
            "maroMainWindow: MQtUtil.findLayout() could not resolve viewportRow "
            "{!r} -- cannot embed the tech-diag side panels.".format(viewportRow))
    mayaSidePanelName = omui.MQtUtil.addWidgetToMayaLayout(
        int(shiboken6.getCppPointer(mayaSidePanelWidget)[0]), int(viewportRowLayoutPtr))
    if not mayaSidePanelName:
        raise RuntimeError(
            "maroMainWindow: MQtUtil.addWidgetToMayaLayout() returned no UI name "
            "for the Maya-side tech-diag panel.")
    rosSidePanelName = omui.MQtUtil.addWidgetToMayaLayout(
        int(shiboken6.getCppPointer(rosSidePanelWidget)[0]), int(viewportRowLayoutPtr))
    if not rosSidePanelName:
        raise RuntimeError(
            "maroMainWindow: MQtUtil.addWidgetToMayaLayout() returned no UI name "
            "for the ROS-side tech-diag panel.")
    _EMBEDDED[MAYA_SIDE_PANEL_NAME] = mayaSidePanelWidget
    _EMBEDDED[ROS_SIDE_PANEL_NAME] = rosSidePanelWidget

    # 좌: 고정 폭 Maya 패널, 가운데: 뷰포트(늘어남), 우: 고정 폭 ROS 패널.
    # attachForm만으로 폭을 고정하는 두 변(top/bottom/left 또는
    # top/bottom/right)만 붙이고 반대쪽 변은 attachControl로 가운데
    # viewportPane에 맡긴다 -- 그러면 formLayout이 두 사이드 패널의 폭을
    # cmds.control(width=...)로 명시한 값 그대로 유지하고 나머지 공간을
    # viewportPane에 전부 준다.
    cmds.control(mayaSidePanelName, edit=True, width=SIDE_PANEL_WIDTH)
    cmds.control(rosSidePanelName, edit=True, width=SIDE_PANEL_WIDTH)
    cmds.formLayout(
        viewportRow, edit=True,
        attachForm=[
            (mayaSidePanelName, "top", 0), (mayaSidePanelName, "bottom", 0),
            (mayaSidePanelName, "left", 0),
            (rosSidePanelName, "top", 0), (rosSidePanelName, "bottom", 0),
            (rosSidePanelName, "right", 0),
            (viewportPane, "top", 0), (viewportPane, "bottom", 0),
        ],
        attachControl=[
            (viewportPane, "left", 0, mayaSidePanelName),
            (viewportPane, "right", 0, rosSidePanelName),
        ])

    # 오른쪽 절반을 위/아래로 나눈다. paneLayout의 vertical2는 **좌우**이고
    # (Phase 2 수동 체크리스트에서 사람이 확인한 사실 -- "뷰포트가 두 개
    # 좌우로 나란히 보인다"), 그래서 outerPane의 두 번째 칸은 지금까지
    # 노드 에디터가 오른쪽 절반을 통째로 쓰고 있었다. horizontal2로 한 겹
    # 감싸면 로드맵이 말한 "우하단"이 처음으로 실제로 생긴다.
    rightPane = cmds.paneLayout(configuration="horizontal2", parent=outerPane)

    # Phase 4: 축/capability 에디터 패널. 부모가 outerPane -> rightPane으로
    # 바뀔 뿐 내부 조립은 그대로다. modelPanel이 아닌 평범한 formLayout이라
    # (_buildLabeledViewport의 modelPanel과 달리) 전역 패널 레지스트리에
    # 등록되지 않는다 -- 부모가 사라지면 이 레이아웃도 함께 완전히 사라진다.
    # 그래서 _deleteStalePanel 같은 잔여물 정리가 필요 없다.
    editorHost = cmds.formLayout(EDITOR_HOST_NAME, parent=rightPane)

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

    # Phase 4: maroObjectNodeEditor(ONE)를 editorHost에 임베드한다 -- 테스트
    # 버튼과 완전히 같은 두 단계(MQtUtil.findLayout -> addWidgetToMayaLayout)를
    # 재사용한다. import는 함수 안에서 한다(테스트 버튼 임베드 위
    # maroRosProxy import와 같은 이유 -- 이 모듈의 import 시점과
    # maroObjectNodeEditor가 필요한 시점을 떼어 놓는다).
    import maroObjectNodeEditor
    objectNodeEditorWidget = maroObjectNodeEditor.buildWidget()

    editorHostLayoutPtr = omui.MQtUtil.findLayout(
        cmds.control(editorHost, query=True, fullPathName=True))
    if editorHostLayoutPtr is None:
        raise RuntimeError(
            "maroMainWindow: MQtUtil.findLayout() could not resolve editorHost "
            "{!r} -- cannot embed the object node editor (ONE) widget.".format(editorHost))
    objectNodeEditorName = omui.MQtUtil.addWidgetToMayaLayout(
        int(shiboken6.getCppPointer(objectNodeEditorWidget)[0]), int(editorHostLayoutPtr))
    if not objectNodeEditorName:
        raise RuntimeError(
            "maroMainWindow: MQtUtil.addWidgetToMayaLayout() returned no UI name "
            "for the object node editor (ONE).")
    _EMBEDDED[EDITOR_HOST_NAME] = objectNodeEditorWidget
    cmds.formLayout(
        editorHost, edit=True,
        attachForm=[
            (objectNodeEditorName, "top", 0), (objectNodeEditorName, "left", 0),
            (objectNodeEditorName, "right", 0), (objectNodeEditorName, "bottom", 0),
        ])

    # 우하단: 기존 진단 패널을 **그대로** 그린다(설계 스펙 §3). 네이티브
    # Maya UI라 PySide6 위젯이 타는 두 단계(MQtUtil.findLayout ->
    # addWidgetToMayaLayout)를 타지 않는다 -- rightPane을 부모로 직접 넘기면
    # paneLayout의 두 번째 칸을 그대로 채우므로 formLayout attach도 필요
    # 없다.
    #
    # 단독 창(maroDiagPanel.show())은 그대로 남는다. 둘이 동시에 떠 있어도
    # 안전하다 -- buildUI가 만드는 컨트롤은 전부 무명이고 선택 상태는
    # 클로저에 있다(그 모듈의 주석이 이유를 적어 두었다).
    #
    # teardown()에 아무것도 추가하지 않는다. maroDiagPanel에는 scriptJob도
    # 타이머도 모듈 전역 가변 상태도 없고, 새로 고침은 사용자가 누를 때만
    # 일어난다 -- 멈출 것이 없어서 stop()이 없는 것이지, 빠뜨린 것이
    # 아니다(설계 스펙 §5).
    import maroDiagPanel
    maroDiagPanel.buildUI(parent=rightPane)

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
                (outerPane, "left", 0), (outerPane, "right", 0), (outerPane, "bottom", 0),
            ],
            attachControl=[(outerPane, "top", 4, buttonName)])
    except RuntimeError as error:
        raise RuntimeError(
            "maroMainWindow: the native formLayout refused to lay out the "
            "embedded widget ({!r}) next to the dual-viewport pane ({!r}): {} "
            "-- see docs/maro-main-ui-manual-checklist.md".format(
                buttonName, outerPane, error))

    # Phase 3: 좌/우 뷰포트 격리 + ROS 프록시 동기화(설계 스펙 §6/§7).
    #
    # 브리프는 이 호출을 두 _buildLabeledViewport() 바로 다음에 두라고 했다.
    # 여기(조립이 전부 끝난 뒤)로 옮겼다: 그 자리와 여기 사이에는 일부러
    # RuntimeError를 던지는 지점이 셋 있다(findLayout 실패,
    # addWidgetToMayaLayout이 이름을 안 줌, formLayout attach 실패). 거기서
    # 던지면 창은 반쪽으로 남는데 idle scriptJob은 이미 돌고 있는 상태가
    # 된다 -- "주인이 없어진 콜백이 계속 산다"는, 이 프로젝트가 Phase 0-1과
    # 2에서 반복해서 잡아 온 바로 그 결함 유형이다. 마지막에 걸면 조립이
    # 끝까지 성공했을 때만 잡이 생긴다. 격리/동기화는 두 패널이 존재하기만
    # 하면 되므로 이 위치 변경으로 잃는 것은 없다.
    #
    # 함수 안에서 import하는 것은 순환 참조를 피하기 위해서가 아니라
    # (maroRosProxy는 이쪽을 import하지 않는다) 이 모듈의 import 시점과
    # maroRosProxy가 필요한 시점을 떼어 놓기 위해서다: 이 모듈은 C++
    # 브리지가 sys.path를 손본 뒤에 import되고, 그 sys.path에
    # maroRosProxy.py도 함께 스테이징돼 있다(MARO_PLUGIN_PY_MODULES).
    import maroRosProxy
    maroRosProxy.start(VIEWPORT_NAME_MAYA, VIEWPORT_NAME_ROS)

    # Phase 4: 씬 선택 <-> 패널 양방향 동기화(설계 스펙 §9). maroRosProxy.start()
    # 바로 뒤, buildUI() 조립이 전부 끝난 이 자리에 두는 이유는 위 주석과
    # 같다 -- 조립 중간에 예외가 나면 이 scriptJob도 주인 없는 콜백으로
    # 남으면 안 되므로, 조립이 끝까지 성공했을 때만 잡이 생기게 한다.
    import maroObjectNodeEditor
    maroObjectNodeEditor.start()

    return form


def teardown():
    """모든 서브시스템의 stop()을 한 곳에서 부른다.

    closeCommand(문자열)와 MaroPluginMain.cpp의 언로드 경로가 각각 이걸
    가리킨다 -- 서브시스템이 늘 때마다(Phase 3의 maroRosProxy, 이번의
    SelectionChanged job) 두 곳을 따로 늘리지 않기 위해서다. 여기서
    부르는 stop()들은 전부 start()가 한 번도 안 불렸어도 안전한
    무동작이어야 한다(maroRosProxy.stop()이 이미 그렇다).
    """
    try:
        import maroRosProxy
        maroRosProxy.stop()
    except Exception:  # noqa: BLE001 -- Maya 콜백/언로드 경계
        import traceback
        traceback.print_exc()

    try:
        import maroObjectNodeEditor
        maroObjectNodeEditor.stop()
    except Exception:  # noqa: BLE001 -- Maya 콜백/언로드 경계
        import traceback
        traceback.print_exc()

    # [최종 리뷰 C-1] SONE 팝업은 MaroUI와 무관한 독립 최상위 창이라
    # workspaceControl을 닫아도, MaroPluginMain.cpp의 언로드 정리가
    # maroMainWindowControl을 닫아도 함께 닫히지 않는다. 열린 채로 언로드되면
    # paintEvent/keyPressEvent가 이미 deregister된 커맨드를 리페인트/키
    # 입력마다 계속 부른다. **이 호출은 커맨드 deregister보다 먼저 일어나야
    # 한다** -- MaroPluginMain.cpp의 uninitializePlugin에서 이 teardown()
    # 호출(runPluginPythonModule)이 모든 deregisterCommand보다 위에 있다는
    # 것을 확인했다.
    try:
        import maroSingleObjectNodeEditor
        maroSingleObjectNodeEditor.stop()
    except Exception:  # noqa: BLE001 -- Maya 콜백/언로드 경계
        import traceback
        traceback.print_exc()

    try:
        import maroLidarPanel
        maroLidarPanel.stop()
    except Exception:  # noqa: BLE001 -- Maya 콜백/언로드 경계
        import traceback
        traceback.print_exc()

    try:
        import maroCapabilityPanel
        maroCapabilityPanel.stop()
    except Exception:  # noqa: BLE001 -- Maya 콜백/언로드 경계
        import traceback
        traceback.print_exc()

    try:
        import maroSettingsPanel
        maroSettingsPanel.stop()
    except Exception:  # noqa: BLE001 -- Maya 콜백/언로드 경계
        import traceback
        traceback.print_exc()

    try:
        import maroSyntheticDataPanel
        maroSyntheticDataPanel.stop()
    except Exception:  # noqa: BLE001 -- Maya 콜백/언로드 경계
        import traceback
        traceback.print_exc()

    # Skeleton Upload(Phase 6) 다이얼로그도 SONE/LiDAR 팝업과 같은 이유로
    # MaroUI와 무관한 독립 최상위 창이다. 열린 채로 언로드되면 등록된
    # kAfterImport 콜백이 이미 사라진 파이썬 모듈을 계속 가리키게 되므로,
    # 이 stop() 호출은 커맨드 deregister보다 먼저 일어나야 한다(위 SONE
    # 주석과 같은 순서 보장 -- MaroPluginMain.cpp의 uninitializePlugin에서
    # 확인됨).
    try:
        import maroSkeletonUpload
        maroSkeletonUpload.stop()
    except Exception:  # noqa: BLE001 -- Maya 콜백/언로드 경계
        import traceback
        traceback.print_exc()


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
        # Tech Diag(Task 4)가 뷰포트 양옆에 고정폭(SIDE_PANEL_WIDTH=180)
        # 사이드 패널 두 개를 추가했다 -- 기존 900에 2*180 + 여유 마진을
        # 더해 뷰포트 자체는 줄어들지 않게 한다.
        initialWidth=900 + 2 * SIDE_PANEL_WIDTH + 40,
        initialHeight=600,
        requiredPlugin="maro",
        closeCommand="import maroMainWindow; maroMainWindow.teardown()",
        uiScript="import maroMainWindow; maroMainWindow.buildUI()")
