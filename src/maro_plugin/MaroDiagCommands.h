#pragma once

#include <maya/MPxCommand.h>
#include <maya/MSyntax.h>

namespace maro {

// 아래 커맨드들은 진단 배관 자체가 아니라, mayapy 테스트가 BoadMaro의 내부
// 상태를 들여다보기 위한 테스트 전용 도구다 (MaroCommands.h의
// MaroBridgeStatsCommand와 같은 이유로 존재한다). 실제 진단 호출부는 이
// 커맨드들을 쓰지 않고 BoadMaro를 C++에서 직접 부른다.

// -severity <info|warn|devInfo|error> -message <string> [-siteTag <string>]
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

// -index <int, 기본 0>. 0 = 가장 최근 레코드. 필드 9개를 순서대로 담은
// 문자열 배열을 돌려준다: severity, message, errorHash, nodeType,
// attributeName, activeCommand, axisOrTarget, remedy, servedFromBook("0"/"1").
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

}  // namespace maro
