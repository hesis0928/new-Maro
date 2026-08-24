#include "MaroMenuCommands.h"

#include <maya/MArgList.h>

#include "MaroPythonBridge.h"

namespace maro {

void* MaroBuildMenuCommand::creator() { return new MaroBuildMenuCommand(); }

MStatus MaroBuildMenuCommand::doIt(const MArgList& /*args*/) {
    // 메뉴 이름("maroMainMenu")은 python/maroMenu.py가 정하고,
    // MaroPluginMain.cpp의 uninitializePlugin이 언로드할 때 그 이름을
    // MEL로 다시 부른다 -- 세 곳이 같은 문자열에 묶여 있으므로
    // tests/maya/test_main_menu.py가 그 계약을 값으로 고정한다.
    return runPluginPythonModule("maroMenu", "maroMenu.build()");
}

}  // namespace maro
