"""배치 mayapy에서 실제 QWidget을 만들 수 있게 하는 부트스트랩.

**이 파일을 import하는 것만으로는 안 된다 -- `maya.standalone.initialize()`
보다 먼저 `bootstrap()`을 불러야 한다.** 그것이 이 모듈의 전부이자 핵심이다.

## 왜 필요한가

이 저장소의 스펙/플랜/체크리스트 여러 곳이 "배치 mayapy로는 Qt UI를 검증할
수 없다"를 전제로 깔고, 그래서 UI 관련 항목이 전부 수동 체크리스트로
빠져 있었다. 근거는 실제 증상이었다: `maya.standalone.initialize()` 뒤에
QWidget을 하나라도 만들면 프로세스가 즉시 abort한다(0xC0000409).

2026-09-07에 실측으로 원인을 갈랐다. 문제는 두 가지가 겹친 것이다:

  1. `maya.standalone.initialize()`는 **QApplication이 아니라
     QGuiApplication**을 만든다. QWidget은 QtWidgets 쪽 앱 객체를 요구하므로
     이 상태에서는 성립할 수 없다.
  2. 그때 선택되는 플랫폼 플러그인은 `minimal`인데, 이건 위젯 스택을
     받쳐주지 않는다. `QT_QPA_PLATFORM=offscreen`을 환경변수로만 걸어도
     소용없다 -- Maya가 자기 앱을 만들면서 덮어쓰는 것을 실측으로 확인했다
     (`envonly` 모드도 platformName()이 그대로 `minimal`이었다).

둘 다 "Maya가 자기 앱 객체를 만들기 전에" 우리가 먼저 만들어 두면 해결된다.
Qt는 이미 존재하는 QCoreApplication 인스턴스가 있으면 그것을 그대로 쓴다.
그래서 `bootstrap()`은 QApplication을 offscreen 플랫폼으로 먼저 세운다.
이후 `maya.standalone.initialize()`는 그 인스턴스를 재사용하고,
`QApplication.instance()`가 진짜 QApplication, `platformName()`이 `offscreen`이
되며, QWidget/레이아웃/시그널-슬롯이 전부 정상 동작한다(실측).

같은 세션에서 확인한 다른 두 건과 정확히 같은 형태의 교훈이다: ASan
런타임도 Maya 초기화 **전에** 프로세스에 넣어야 동작하고, Viewport 2.0도
"배치엔 없다"가 아니라 `cmds.ogsRender`로 띄울 수 있었다. 이 코드베이스에서
"배치라서 원리적으로 불가능"이라는 문장은 일단 의심하고 재보는 편이 맞다.

## 한계

offscreen 플랫폼은 실제 화면에 그리지 않는다. 즉 위젯의 **구성/상태/로직**
(필드 값 왕복, 시그널 연결, 생성·소멸 시 정리 동작)은 검증되지만, 실제로
사람 눈에 어떻게 보이는지, 도킹/포커스/핫키가 Maya의 진짜 창 계층에서
어떻게 도는지는 여전히 수동 체크리스트의 몫이다.

## 사용법

    import maroQtBatch
    maroQtBatch.bootstrap()          # 반드시 maya.standalone보다 먼저

    import maya.standalone
    maya.standalone.initialize(name="python")
"""
import os
import sys

# Maya 자신의 플랫폼 플러그인 디렉터리. devkit의 Qt 폴더에도 같은 플러그인이
# 있지만 그쪽을 쓰면 Qt6Core가 프로세스에 두 벌 로드될 위험이 있다 --
# 런타임과 같은 것을 쓴다.
_PLATFORM_PLUGIN_DIR = os.path.join(
    os.environ.get("MAYA_LOCATION", r"C:\Program Files\Autodesk\Maya2026"),
    "plugins", "platforms")

_app = None  # 앱 객체를 모듈에 붙들어 둔다 -- GC되면 Qt가 무너진다.


def bootstrap():
    """offscreen QApplication을 세운다. 멱등. 세운(또는 이미 있던) 앱을 반환.

    반드시 `maya.standalone.initialize()` **전에** 부를 것.
    """
    global _app
    if _app is not None:
        return _app

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", _PLATFORM_PLUGIN_DIR)

    from PySide6 import QtWidgets

    existing = QtWidgets.QApplication.instance()
    if existing is not None:
        # 이미 누가 앱을 만들었다. 그것이 QApplication이 아니면 이 시점에는
        # 되돌릴 방법이 없다 -- 조용히 넘어가면 곧 QWidget에서 프로세스가
        # abort하므로, 원인을 알 수 있는 자리에서 크게 실패한다.
        if not isinstance(existing, QtWidgets.QApplication):
            raise RuntimeError(
                "maroQtBatch.bootstrap() was called too late: a {} already "
                "exists. Call bootstrap() before maya.standalone.initialize()."
                .format(type(existing).__name__))
        _app = existing
        return _app

    _app = QtWidgets.QApplication(sys.argv[:1])
    return _app


def assertWidgetsUsable():
    """부트스트랩이 실제로 먹었는지 확인한다. 각 테스트 맨 앞에서 부르면
    나중에 위젯 생성에서 프로세스가 죽는 대신 여기서 명확히 실패한다."""
    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance()
    if not isinstance(app, QtWidgets.QApplication):
        raise AssertionError(
            "no QApplication -- maroQtBatch.bootstrap() must run before "
            "maya.standalone.initialize() (got {})".format(type(app).__name__))
    if app.platformName() != "offscreen":
        raise AssertionError(
            "platform is {!r}, expected 'offscreen' -- widgets will abort"
            .format(app.platformName()))
    return app
