#include "MaroPythonBridge.h"

#include <exception>
#include <string>

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
namespace {

// [최종 리뷰 M3] 경로를 파이썬 소스에 문자열 리터럴로 심을 때 쓰는
// 이스케이프.
//
// 원래는 `d = r'<pluginDir>'`처럼 raw 리터럴에 경로를 그대로 끼워 넣었다.
// 그 형태는 두 가지 평범한 경로에서 깨진다: 작은따옴표가 든 경로
// (C:\Users\O'Brien\...)는 리터럴을 조기에 닫고, 역슬래시로 끝나는 경로는
// raw 리터럴이 역슬래시로 끝날 수 없다는 파이썬 규칙에 걸린다. 두 경우
// 모두 증상은 "import 실패"가 아니라 어디서 왔는지 알 수 없는
// SyntaxError라 진단이 특히 나쁘다.
//
// 특정 문자를 검사해 거부하는 대신(그러면 다음 문자가 또 남는다) 어떤
// 바이트열이 와도 성립하는 리터럴을 만들어 이 부류를 통째로 없앤다.
//
// UTF-8 안전: 아래에서 특별 취급하는 문자는 전부 ASCII(0x00-0x7F)이고
// UTF-8 멀티바이트 문자의 모든 바이트는 0x80 이상이라, 바이트 단위로
// 훑어도 멀티바이트 문자를 쪼개 잘못 이스케이프할 일이 없다. 비 ASCII
// 바이트는 그대로 통과시키고, 파이썬 3 소스의 기본 인코딩이 UTF-8이므로
// 그대로 해석된다 -- 단, 그러려면 입력도 진짜 UTF-8이어야 한다.
// MString::asChar()는 "현재 로케일 코드페이지"로 인코딩된 바이트를 주지
// UTF-8을 보장하지 않는다(MaroPanelCommands.cpp의 utf8() 헬퍼가 이미
// 같은 이유로 setUTF8()을 쓰는 것과 같은 함정이다) -- CP65001(UTF-8)이
// 아닌 로케일의 Windows에서 경로에 비 ASCII 문자(한글 사용자 폴더 등)가
// 있으면 asChar()가 돌려주는 바이트를 UTF-8로 잘못 해석해 모지바케가
// 난다. asUTF8()/setUTF8()로 시작부터 끝까지 명시적 UTF-8만 다뤄서
// 로케일에 의존하지 않게 한다.
MString toPythonStringLiteral(const MString& value) {
    std::string out;
    out += '"';
    for (const char* cursor = value.asUTF8(); cursor != nullptr && *cursor != '\0'; ++cursor) {
        switch (*cursor) {
            case '\\': out += "\\\\"; break;
            case '"':  out += "\\\""; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:   out += *cursor; break;
        }
    }
    out += '"';
    MString result;
    result.setUTF8(out.c_str());
    return result;
}

}  // namespace

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
        python += "d = ";
        python += toPythonStringLiteral(pluginDir);
        python += "\n";
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
