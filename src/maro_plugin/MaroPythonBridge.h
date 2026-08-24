#pragma once

#include <maya/MStatus.h>
#include <maya/MString.h>

namespace maro {

// 플러그인 .mll이 실제로 놓인 디렉터리를 런타임에 찾아 sys.path에 넣고
// `import <moduleName>`한 뒤 <callExpression>을 실행한다.
//
// 이 로직은 원래 MaroDiagPanelCommand::doIt 안에 있었다. UI 커맨드가
// 둘(maroDiagPanel, maroMainWindow) 이상이 되면서 같은 스무 줄을 복붙하는
// 대신 여기로 뽑았다 -- 세 번째(Task 3의 maroBuildMenu)도 이것을 쓴다.
//
// 하드코딩된 설치 경로를 쓰지 않는 것이 핵심이다: 설계 스펙 §4.1이 요구하는
// 대로 MFnPlugin::findPlugin("maro")->loadPath()로 알아내므로, 사용자가
// MAYA_SCRIPT_PATH를 손대지 않아도, 플러그인을 어디에 설치했든 동작한다.
// (.py 모듈은 CMake가 .mll 옆에 복사해 둔다 -- MARO_PLUGIN_PY_MODULES 참고.)
//
// 실패하면 기존 doIt들과 같은 방식으로 MGlobal::displayError + MS::kFailure.
MStatus runPluginPythonModule(const MString& moduleName, const MString& callExpression);

}  // namespace maro
