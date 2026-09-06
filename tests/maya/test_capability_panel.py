"""capability 상세 설정 패널: 실제 QWidget 생성 없이 확인 가능한 부분만
자동화한다.

[2026-09-07 실측] mayapy 표준입출력 환경에서 PySide6의 QApplication은
platformName()이 "minimal"(헤드리스 폴백)로 뜨고, 그 상태에서는
QWidget()을 만드는 것 자체가 즉시 크래시한다(Maya GUI가 쓰는 Qt와
mayapy용 PySide6의 플랫폼 플러그인이 안 맞는 것으로 보임 --
QT_QPA_PLATFORM_PLUGIN_PATH를 Maya 자신의 qwindows.dll 경로로 지정해도
동일하게 크래시했다). 이 프로젝트는 원래도 이 한계를 갖고 있었다 --
maroLidarPanel.py/maroSingleObjectNodeEditor.py 둘 다 실제 QWidget을
만드는 자동 테스트가 존재한 적이 없고(test_single_object_node_editor.py는
순수 함수만 검증), Qt 창의 실제 동작은 항상 수동 체크리스트로 확인해 왔다.
이 파일도 그 관례를 따른다 -- 패널을 실제로 열고 필드를 채우고 적용하는
플로우는 docs/maro-main-ui-manual-checklist.md의 수동 체크리스트가
담당한다(Task 8).

여기서 자동화하는 것은 QWidget을 전혀 만들지 않고도 검증 가능한
factory 매핑 계약뿐이다.
"""
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(plugin))))
import maroCapabilityPanel  # noqa: E402

# 모듈 임포트 자체(클래스 정의, PySide6 임포트)는 QApplication/QWidget을
# 만들지 않으므로 안전하다 -- 여기까지 온 것 자체가 그 사실의 증거.
print("module import OK")

# _PANEL_CLASSES 매핑: Task 5부터 maroLimit/maroTranslationLimit도
# 등록되어 7종 전부 매핑된다.
expectedTypes = {
    "maroRotation": maroCapabilityPanel.MaroRotationPanel,
    "maroTranslation": maroCapabilityPanel.MaroTranslationPanel,
    "maroSensorDirection": maroCapabilityPanel.MaroSensorDirectionPanel,
    "maroSensorRange": maroCapabilityPanel.MaroSensorRangePanel,
    "maroCoupling": maroCapabilityPanel.MaroCouplingPanel,
    "maroLimit": maroCapabilityPanel.MaroLimitPanel,
    "maroTranslationLimit": maroCapabilityPanel.MaroTranslationLimitPanel,
}
assert maroCapabilityPanel._PANEL_CLASSES == expectedTypes, maroCapabilityPanel._PANEL_CLASSES
print("_PANEL_CLASSES mapping (all 7 types) OK")

# stop()은 _OPEN_EDITORS가 비어 있어도 안전한 무동작이어야 한다(위젯을
# 하나도 안 만들었으므로 여기서는 그 경로만 확인).
assert len(maroCapabilityPanel._OPEN_EDITORS) == 0
maroCapabilityPanel.stop()
assert len(maroCapabilityPanel._OPEN_EDITORS) == 0
print("stop() no-op when nothing is open OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
