"""합성 데이터 렌더 패널(maroSyntheticDataPanel)을 실제 QWidget으로 검증한다.

**왜 이제야 생겼나**: 이 저장소의 18개 파이썬 모듈 중 유일하게 테스트가
전혀 없던 모듈이다. "배치 mayapy에서는 QWidget을 만들 수 없다"는 전제 때문에
Qt 패널은 전부 수동 확인으로 밀려 있었는데, 그 전제가 틀렸다는 것이
2026-09-07에 드러났다 -- tests/maya/maroQtBatch.py의 독스트링 참고.

**무엇을 보고 무엇을 안 보나**: 실제 Arnold 렌더는 라이선스와 긴 시간이
필요하므로 여기서 돌리지 않는다. 대신 렌더 호출 자체를 스텁으로 바꿔치기해
(tests/maya/test_lidar_menu.py가 쓰는 것과 같은 관례) 그 주변의 **패널
로직**만 본다: 창 생명주기, 카메라 목록, 렌더 버튼의 가드 분기, 그리고
무엇보다 **Qt 콜백 경계가 예외를 절대 밖으로 내보내지 않는지**. 렌더
파이프라인 자체의 정확성은 test_synthetic_data_render.py와
test_synthetic_data_point_cloud.py가 이미 맡고 있다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import maroQtBatch  # noqa: E402

# 반드시 maya.standalone보다 먼저 -- 이 한 줄이 이 파일을 가능하게 한다.
maroQtBatch.bootstrap()

import maya.standalone  # noqa: E402

maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

maroQtBatch.assertWidgetsUsable()

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)
cmds.file(new=True, force=True)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(plugin))))
import maroSyntheticDataPanel as panelMod  # noqa: E402
import maroSyntheticDataCamera as sdc  # noqa: E402

# --- (a) show()/stop() 생명주기 -------------------------------------------
assert panelMod._OPEN_PANEL is None, "no panel should exist before show()"
panelMod.stop()   # 한 번도 안 열렸어도 안전한 무동작이어야 한다(언로드 경로)
print("stop() before any show() is a safe no-op OK")

panel = panelMod.show()
assert panel is not None
assert panelMod._OPEN_PANEL is panel
again = panelMod.show()
assert again is panel, "show() must reuse the open panel, not build a second one"
print("show() singleton OK")

# --- (b) 카메라 목록 -------------------------------------------------------
# 새 씬이므로 합성 데이터 카메라는 아직 없다.
assert panel._cameraCombo.count() == 0, [
    panel._cameraCombo.itemText(i) for i in range(panel._cameraCombo.count())]

cam = sdc.createSyntheticDataCamera()
panel._refreshCameraList()
listed = [panel._cameraCombo.itemText(i) for i in range(panel._cameraCombo.count())]
assert listed == sdc.listSyntheticDataCameras(), (listed, sdc.listSyntheticDataCameras())
assert cam in listed, (cam, listed)
print("camera list refresh OK:", listed)

# "새로 만들기"는 카메라를 만들고 **그것을 선택까지** 해야 한다.
panel._onNewCamera()
assert panel._cameraCombo.count() == 2, panel._cameraCombo.count()
assert panel._cameraCombo.currentText() in sdc.listSyntheticDataCameras()
assert panel._cameraCombo.currentText() != "", "the new camera must be selected"
print("new-camera button creates and selects OK:", panel._cameraCombo.currentText())

# --- (c) 프레임 라벨이 현재 시간을 따라간다 --------------------------------
cmds.currentTime(7)
panel._refreshFrameLabel()
assert "7" in panel._frameLabel.text(), panel._frameLabel.text()
print("frame label OK:", panel._frameLabel.text())

# --- (d) 렌더 버튼의 가드 분기 (Arnold를 부르지 않는 경로) -----------------
panel._outputDirField.setText("")
panel._onRenderNow()
assert "출력 디렉터리" in panel._statusLabel.text(), panel._statusLabel.text()
print("missing output dir is refused OK:", panel._statusLabel.text())

panel._cameraCombo.clear()
panel._outputDirField.setText(os.environ.get("TEMP", "."))
panel._onRenderNow()
assert "카메라" in panel._statusLabel.text(), panel._statusLabel.text()
print("missing camera is refused OK:", panel._statusLabel.text())

# 렌더 버튼을 누르면 프레임 라벨이 **다시 그려져야** 한다 -- 사용자가 창을
# 연 뒤 타임라인을 스크럽했을 수 있고, 실제 렌더는 언제나 라이브
# currentTime()을 쓰기 때문이다(모듈 주석이 명시한 동작).
cmds.currentTime(21)
panel._onRenderNow()          # 카메라가 없어 즉시 반환하지만 라벨은 갱신된다
assert "21" in panel._frameLabel.text(), panel._frameLabel.text()
print("render button refreshes the frame label first OK")

# --- (e) Qt 콜백 경계: 렌더가 터져도 예외가 새면 안 된다 -------------------
#
# 이 패널에서 가장 중요한 계약이다. _onRenderNow()는 Arnold 렌더, 파일 I/O,
# PFM 파싱, 역투영까지 부르는데 그중 무엇이 실패해도 예외가 Qt로 새면 Maya가
# 불안정해진다. 실제 렌더 대신 스텁을 세워 그 경로를 강제한다
# (test_lidar_menu.py가 QWidget 팝업에 대해 쓰는 것과 같은 관례).
import maroSyntheticDataRender as sdr  # noqa: E402

_originalRender = sdr.renderSyntheticFrame
calls = []


def _explodingRender(camera, outputDir):
    calls.append((camera, outputDir))
    raise RuntimeError("simulated Arnold failure")


sdr.renderSyntheticFrame = _explodingRender
try:
    panel._refreshCameraList()
    panel._cameraCombo.setCurrentIndex(0)
    panel._outputDirField.setText(os.environ.get("TEMP", "."))
    panel._onRenderNow()          # 던지면 이 줄에서 테스트가 실패한다
finally:
    sdr.renderSyntheticFrame = _originalRender

assert calls, "the render path was never reached -- the guards rejected it first"
assert "렌더링 실패" in panel._statusLabel.text(), panel._statusLabel.text()
assert "simulated Arnold failure" in panel._statusLabel.text(), panel._statusLabel.text()
print("a failing render is reported, not raised OK:", panel._statusLabel.text())

# --- (f) stop()이 창을 닫고 전역을 비운다 (언로드 경로) --------------------
panelMod.stop()
assert panelMod._OPEN_PANEL is None, panelMod._OPEN_PANEL
print("stop() closes the panel and clears the singleton OK")

# 닫힌 뒤 다시 열면 새 인스턴스가 나온다.
reopened = panelMod.show()
assert reopened is not panel, "show() after stop() must build a fresh panel"
reopened.close()
assert panelMod._OPEN_PANEL is None, "closeEvent must clear the singleton"
print("closeEvent clears the singleton OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("teardown OK")
sys.exit(0)
