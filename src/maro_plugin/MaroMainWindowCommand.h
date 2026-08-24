#pragma once

#include <maya/MPxCommand.h>

namespace maro {

// 인자 없음. Maro 메인 창(workspaceControl)을 띄운다(이미 있으면 복원한다).
// MaroDiagPanelCommand와 정확히 같은 모양이며, 파이썬 모듈을 찾아 부르는
// 일은 둘 다 MaroPythonBridge.h의 runPluginPythonModule에 맡긴다.
//
// 이 창이 Phase 0-1 스파이크의 본체다: 네이티브 workspaceControl +
// formLayout 안에 cmds.modelPanel()로 만든 진짜 3D 뷰포트 하나와,
// MQtUtil::addWidgetToMayaLayout로 끼워 넣은 PySide6 위젯 하나가 공존한다
// (python/maroMainWindow.py). 이 창을 띄운 채 unloadPlugin해도 Maya가
// 죽지 않는지가 스파이크의 go/no-go 기준이다 --
// docs/maro-main-ui-manual-checklist.md 참고.
class MaroMainWindowCommand : public MPxCommand {
public:
    static void* creator();
    MStatus doIt(const MArgList& args) override;
};

}  // namespace maro
