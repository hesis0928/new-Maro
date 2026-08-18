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

// -sequence <int>
// 그 순번의 레코드 하나를 14필드 상세로 돌려준다:
//   nodeType, nodeTypeState, attributeName, attributeNameState,
//   activeCommand, activeCommandState, axisOrTarget, axisOrTargetState,
//   message, priorAnalysis, remedyText, applyAvailable("0"/"1"),
//   applyUnavailableReason, crashAdjacencyNote
// 상태 필드는 "present" | "notApplicable" | "notCaptured" 중 하나다.
//
// 리뷰 Finding: 예전에는 -index로 화면에 그려진 행 목록의 자리를 받아, 그
// 자리를 클릭 시점에 새로 만든 행 목록에 다시 대입해 레코드를 찾았다.
// 하지만 그 행 목록은 클릭할 때마다 스냅샷을 새로 떠서 다시 계산되므로,
// refresh()가 화면을 그린 시점과 사용자가 실제로 클릭하는 시점 사이에
// 진단이 하나라도 더 들어오면(Maya 2026 Parallel Evaluation Manager 아래
// 워커 스레드가 평가 도중 아무 때나 error()/warn()/info()를 부를 수 있다)
// 같은 자리가 다른 레코드를 가리키게 되어, 사용자가 클릭한 행과 실제로
// 돌아오는 상세가 조용히 어긋난다. sequence는 세션 전역에서 유일하고
// 재사용되지 않으므로, 필터링/절단을 다시 거쳐 자리를 재구성할 필요 없이
// 스냅샷을 그대로 훑어 그 값과 일치하는 레코드 하나를 직접 찾는다 -- 화면이
// 그 사이에 얼마나 바뀌었든 결과는 항상 사용자가 클릭한 바로 그 레코드다.
// 존재한 적 없는 순번이면 엉뚱한 이웃을 대신 돌려주지 않고 실패로 끝낸다.
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
