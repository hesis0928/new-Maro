#pragma once

#include <maya/MDGModifier.h>
#include <maya/MPxCommand.h>
#include <maya/MSelectionList.h>
#include <maya/MSyntax.h>

#include "maro_diag/RemedyAction.h"

namespace maro {

// -sequence <int>. 그 레코드가 해법을 가지고 있으면 큐에 넣기만 한다 --
// 씬은 여기서 바뀌지 않는다. 미루는 것은 이 커맨드 안이 아니라 이 커맨드가
// 언제 불리느냐다(원 스펙 §4.3): 실제 편집은 다음 큐 틱에서
// maroApplyRemedy를 통해 일어난다. isUndoable()은 false다 -- 이 커맨드
// 자신은 아무것도 바꾸지 않으므로 undo 큐에 올릴 것이 없다.
class MaroDiagRequestRemedyCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
};

// -sequence <int>. 그 레코드의 RemedyAction을 실제로 적용한다. 평범하고
// 동기적이며 되돌릴 수 있는 커맨드다 -- MaroDiagRequestRemedyCommand가
// 큐를 통해 "언제" 부를지만 정하고, 이 커맨드 자신은 비동기로 동작하지
// 않는다(비동기면 doIt이 아무것도 안 한 채 반환해 undo 큐에 빈 항목이
// 올라간다).
//
// 실행 직전에 대상이 여전히 존재하는지 다시 확인한다(원 스펙 §5) -- 클릭과
// 실행 사이에 씬이 바뀔 수 있기 때문이다. 확인에 실패하면 아무것도 바꾸지
// 않고 실패로 끝난다.
class MaroApplyRemedyCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();

    MStatus doIt(const MArgList& args) override;
    MStatus redoIt() override;
    MStatus undoIt() override;
    bool isUndoable() const override { return m_stagedChange; }

private:
    MDGModifier m_modifier;
    RemedyActionKind m_kind = RemedyActionKind::None;
    // SelectNode가 고를 대상. 이름이 아니라 doIt이 이미 "정확히 하나"로
    // 풀어 검증한 결과를 들고 있다 (최종 리뷰 Finding I1) -- redoIt이 이름을
    // 다시 풀면 그 사이에 이름이 가리키는 것이 달라졌을 때 doIt이 검증한
    // 것과 다른 대상을 고르게 된다.
    MSelectionList m_selectTarget;
    MSelectionList m_previousSelection;
    bool m_stagedChange = false;
};

}  // namespace maro
