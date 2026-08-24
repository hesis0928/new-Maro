#include "MaroMainWindowCommand.h"

#include <maya/MArgList.h>

#include "MaroPythonBridge.h"

namespace maro {

void* MaroMainWindowCommand::creator() { return new MaroMainWindowCommand(); }

MStatus MaroMainWindowCommand::doIt(const MArgList& /*args*/) {
    // 컨트롤 이름("maroMainWindowControl")과 뷰포트 이름
    // ("maroMainWindowViewport")은 python/maroMainWindow.py가 정하고,
    // MaroPluginMain.cpp의 uninitializePlugin이 언로드할 때 그 두 이름을
    // MEL로 다시 부른다 -- 세 곳이 같은 문자열에 묶여 있으므로
    // tests/maya/test_main_window.py가 그 계약을 값으로 고정한다.
    return runPluginPythonModule("maroMainWindow", "maroMainWindow.show()");
}

}  // namespace maro
