#pragma once

#include <maya/MPxCommand.h>

namespace maro {

// 인자 없음. 최상위 Maya 메뉴바에 "Maro" 메뉴를 만든다(이미 있으면 아무것도
// 안 함 -- 멱등). MaroMainWindowCommand/MaroDiagPanelCommand와 정확히 같은
// 모양이며, 파이썬 모듈을 찾아 부르는 일은 셋 다 MaroPythonBridge.h의
// runPluginPythonModule에 맡긴다.
//
// initializePlugin이 로드 끝에서 이 커맨드를 한 번 큐에 넣는다(MGlobal::
// executeCommandOnIdle("maroBuildMenu") -- [최종 리뷰 I5] Maya UI가 아직
// 없을 수 있는 시점(오토로드, 워크스페이스 복원)을 지나 유휴 시점에
// 돌게 하기 위해서다, MaroPluginMain.cpp 참고) -- 그 호출의 실패는
// 플러그인 로드를 막지 않는다: 메뉴는 UI 편의이지 핵심 기능이 아니다.
//
// 배치 모드(mayapy)에는 실제 메인 윈도우가 없어 "MayaWindow" 컨트롤 자체가
// 존재하지 않는다. 실측(2026-08-24, Maya 2026): 그 상태에서도
// cmds.menu(parent="MayaWindow", ...)/cmds.menuItem(...)는 예외를 던지지
// 않고 그냥 아무것도 만들지 않은 채 False를 돌려준다(workspaceControl이
// 배치 모드에서 하는 것과 같다) -- 그래서 python/maroMenu.py는 별도의
// about(batch=True) 가드 없이도 배치 모드에서 안전한 no-op이다. 배치
// 테스트(tests/maya/test_main_menu.py)는 그래서 "메뉴가 실제로 존재한다"가
// 아니라 "커맨드가 예외 없이 끝난다"만 확인한다.
class MaroBuildMenuCommand : public MPxCommand {
public:
    static void* creator();
    MStatus doIt(const MArgList& args) override;
};

}  // namespace maro
