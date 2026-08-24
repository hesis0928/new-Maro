#include "MaroPythonBridge.h"

#include <exception>

// MFnPlugin.h's own docs (and MApiVersion.h) require this: including it in
// more than one translation unit of the same plug-in emits DllMain,
// MhInstPlugin, MApiVersion and ADSK_PLUGIN_SIGNATURE again, which the
// linker then reports as LNK2005 against MaroPluginMain.cpp.obj (the file
// that legitimately owns those symbols). Defining both macros before the
// include keeps this file to just MFnPlugin::findPlugin/loadPath.
//
// (이 주석과 두 매크로는 MaroPanelCommands.cpp에서 옮겨 왔다 -- 이제
// MFnPlugin.h를 포함하는 UI 쪽 번역 단위는 이 파일 하나뿐이다.)
#define MNoPluginEntry
#define MNoVersionString

#include <maya/MFnPlugin.h>
#include <maya/MGlobal.h>
#include <maya/MObject.h>

namespace maro {

MStatus runPluginPythonModule(const MString& moduleName, const MString& callExpression) {
    try {
        // findPlugin은 MObject를 돌려준다 -- 경로 문자열이 아니다. 경로는
        // 그 MObject로 만든 MFnPlugin의 loadPath()에서 나온다.
        // 공개 생성자는 MObject&(비상수)를 받으므로 const로 두면 안 된다.
        MObject pluginObj = MFnPlugin::findPlugin("maro");
        if (pluginObj.isNull()) {
            MGlobal::displayError("Maro: could not locate the loaded maro plug-in.");
            return MS::kFailure;
        }
        MStatus status;
        // vendor/version/apiVersion은 기본값이 있지만 상태를 받으려면
        // 앞의 셋을 함께 넘겨야 한다.
        MFnPlugin pluginFn(pluginObj, "Unknown", "Unknown", "Any", &status);
        if (!status) return status;
        const MString pluginDir = pluginFn.loadPath(&status);
        if (!status) return status;

        MString python;
        python += "import os, sys\n";
        python += "d = r'";
        python += pluginDir;
        python += "'\n";
        // loadPath()가 디렉터리를 주는지 파일까지 주는지에 기대지 않는다.
        python += "if os.path.isfile(d): d = os.path.dirname(d)\n";
        python += "if d not in sys.path: sys.path.insert(0, d)\n";
        python += "import ";
        python += moduleName;
        python += "\n";
        python += callExpression;
        python += "\n";

        return MGlobal::executePythonCommand(python);
    } catch (const std::exception& e) {
        MGlobal::displayError(MString("Maro: ") + moduleName + " failed: " + e.what());
        return MS::kFailure;
    } catch (...) {
        MGlobal::displayError(MString("Maro: ") + moduleName +
                              " failed with unknown error.");
        return MS::kFailure;
    }
}

}  // namespace maro
