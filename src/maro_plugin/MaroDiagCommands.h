#pragma once

#include <maya/MPxCommand.h>
#include <maya/MSyntax.h>

namespace maro {

// 아래 커맨드들은 진단 배관 자체가 아니라, mayapy 테스트가 BoadMaro의 내부
// 상태를 들여다보기 위한 테스트 전용 도구다 (MaroCommands.h의
// MaroBridgeStatsCommand와 같은 이유로 존재한다). 실제 진단 호출부는 이
// 커맨드들을 쓰지 않고 BoadMaro를 C++에서 직접 부른다.

// -severity <info|warn|devInfo|error> -message <string> [-siteTag <string>]
// [-nodeType <string>] [-axisOrTarget <string>] [-nameUnavailable] [-typeUnavailable]
//
// 뒤의 네 플래그는 severity=error에서만 쓰이며, 지정하지 않으면 이전과
// 바이트 단위로 동일하게 동작한다(capture("", "", "") + 두 플래그 false).
// 존재 이유: DgContext::nameUnavailable/typeUnavailable("관여했으나 못
// 채움")은 실제로는 워커 스레드의 compute() 실패나 손상된 노드의 삭제
// 콜백(MaroDeleteWatcher.cpp)에서만 서는데, 그 경로들은 mayapy 테스트가
// 결정적으로 유발할 방법이 없다. 패널 상세 커맨드(maroDiagPanelDetail)가
// ContextPresence::NotCaptured를 올바른 문자열로 내놓는지 검증하려면 이
// 상태를 직접 지정할 수 있는 도구가 필요하다 -- maroDiagEmitFromThread가
// "워커 스레드에서 왔다"는 사실을 재현하기 위해 존재하는 것과 같은 이유다.
class MaroDiagEmitCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
};

// 인자 없음. 현재 스트림에 쌓인 레코드 수.
class MaroDiagCountCommand : public MPxCommand {
public:
    static void* creator();
    MStatus doIt(const MArgList& args) override;
};

// -index <int, 기본 0>. 0 = 가장 최근 레코드. 필드 12개를 순서대로 담은
// 문자열 배열을 돌려준다: severity, message, errorHash, nodeType,
// attributeName, activeCommand, axisOrTarget, remedy, servedFromBook("0"/"1"),
// priorAnalysis, sequence, timestampMs.
class MaroDiagQueryCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
};

// 인자 없음. book 캐시 미스로 실제 새 분석을 기록한 누적 횟수.
class MaroDiagAnalysisCountCommand : public MPxCommand {
public:
    static void* creator();
    MStatus doIt(const MArgList& args) override;
};

// -severity <info|warn|error> -message <string> [-siteTag <string>]
// maroDiagEmit과 같은 일을 하되, 반드시 새로 만든 std::thread 위에서 한 번
// 발동시키고 조인한다 -- 즉 진짜 워커 스레드에서 boad로 들어간다. Maya 2026의
// Parallel Evaluation Manager가 compute()를 워커에서 돌리는 상황을 테스트가
// 결정적으로 재현할 수단이 달리 없어서 존재한다(평가 관리자에게 "지금 워커로
// 돌려라"라고 시킬 방법이 없다). 테스트 전용 도구다.
class MaroDiagEmitFromThreadCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
};

// -hash <string> -remedy <string>. 위 세 커맨드와 달리 이건 테스트 전용
// 도구가 아니다 -- 사용자가 스스로 고친 해법을 book에 등록하는 실제 진입점.
class MaroDiagRegisterRemedyCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
};

// 리뷰 Finding 1 전용 테스트 도구. maroDiagEmit과 달리 이 커맨드는 자기
// 이름으로 된 ScopedCommandContext 마커를 스스로 설치한 채로
// BoadMaro::error()를 **세 번째 인자(컨텍스트) 없이** 부른다 -- capture()를
// 거치지 않는, 즉 error()의 기본 인자 DgContext{}를 그대로 타는 유일한 진짜
// 에러 경로다. doIt/redoIt/undoIt의 catch 블록들이 실제로 겪는 상황(마커는
// 살아 있는데 컨텍스트는 안 채워 옴)을 그대로 재현해, error() 자신이
// g_commandStack에서 activeCommand를 채우는지를 테스트가 결정적으로 확인할
// 수 있게 한다.
// -siteTag <string> -message <string>
class MaroDiagEmitMarkedCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
};

}  // namespace maro
