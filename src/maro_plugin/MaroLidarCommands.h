#pragma once

#include <maya/MPxCommand.h>
#include <maya/MSyntax.h>
#include <maya/MDGModifier.h>

namespace maro {

// <lidarNode> <pointCloudNode>: lidarNode를 즉시 동기 스캔해 그 결과를
// pointCloudNode.points에 undoable하게 반영한다. maroStartBridge/MaroPump와
// 완전히 독립적이다 -- 브리지가 꺼져 있어도 동작한다.
class MaroSnapshotLidarScanCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
    MStatus redoIt() override;
    MStatus undoIt() override;
    bool isUndoable() const override { return m_stagedChange; }

private:
    MDGModifier m_modifier;
    bool m_stagedChange = false;
};

}  // namespace maro
