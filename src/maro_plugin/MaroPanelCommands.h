#pragma once

#include <maya/MPxCommand.h>
#include <maya/MSyntax.h>

namespace maro {

// 아래 둘은 테스트 도구가 아니라 **정식 API**다. 패널 UI(Python)가 프레젠터를
// 읽는 유일한 경로이므로 이름과 필드 개수가 계약이다 (설계 스펙 §3.5.1).
// 반면 maroDiagCount/maroDiagQuery/maroDiagEmit 계열은 테스트 전용으로 남는다.

// [-severity <all|warn|error>] [-maxRows <int, 기본 500>] [-hidden]
// 접힌 행들을 평탄한 문자열 배열로 돌려준다. 행마다 8필드:
//   errorHash, severity, summary, sequence, firstTimestampMs,
//   lastTimestampMs, occurrences, knownBefore("0"/"1")
//
// 숨겨진 개수는 이 배열에 섞지 않는다 -- 섞으면 배열 길이가 더 이상 8의
// 배수가 아니게 되어 Python의 재조립이 조용히 어긋난다. 대신 -hidden을
// 주면 행 대신 2필드만 돌려준다: 필터로 빠진 개수, 상한으로 잘린 개수.
// 둘을 나누는 이유는 사용자에게 다른 사건이기 때문이다.
class MaroDiagPanelRowsCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
};

// -index <int> [-severity <all|warn|error>] [-maxRows <int, 기본 500>]
// 그 행의 상세를 13필드로 돌려준다:
//   nodeType, nodeTypeState, attributeName, attributeNameState,
//   activeCommand, activeCommandState, axisOrTarget, axisOrTargetState,
//   message, priorAnalysis, remedyText, applyAvailable("0"/"1"),
//   applyUnavailableReason
// 상태 필드는 "present" | "notApplicable" | "notCaptured" 중 하나다.
class MaroDiagPanelDetailCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
};

// 인자 없음. workspaceControl을 띄운다(이미 있으면 복원한다).
// 파이썬 모듈은 플러그인 .mll 옆에 배포되며, 이 커맨드가 그 경로를
// sys.path에 넣는다 -- MAYA_SCRIPT_PATH 설정을 사용자에게 요구하지 않기
// 위해서다.
class MaroDiagPanelCommand : public MPxCommand {
public:
    static void* creator();
    MStatus doIt(const MArgList& args) override;
};

}  // namespace maro
