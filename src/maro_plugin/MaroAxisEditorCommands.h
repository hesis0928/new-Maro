#pragma once

#include <maya/MPxCommand.h>
#include <maya/MSyntax.h>
#include <maya/MPlug.h>

namespace maro {

// 씬의 maroAxis 전체 또는 한 축의 capability 스택을 나열한다. 쿼리
// 전용이라 undoable이 아니다.
class MaroListAxisNodesCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
    bool isUndoable() const override { return false; }
};

// Task 6(쓰기 커맨드)이 재사용하는 헬퍼.
unsigned int nextFreeCapabilitySlot(MPlug capabilityInPlug);
bool hasPrimaryDriver(MPlug capabilityInPlug);

}  // namespace maro
