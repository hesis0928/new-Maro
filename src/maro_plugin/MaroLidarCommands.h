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

// <lidarNode>: lidarNode를 즉시 동기 스캔하되 씬을 전혀 바꾸지 않는다 --
// maroPointCloud도, MDGModifier도 없다. Tech Diag의 동적 LiDAR 검사(설계
// 스펙 2026-09-04)가 쓰는 유일한 조회 경로. 결과 형식은
// docs/superpowers/plans/2026-09-04-maro-lidar-sensor-validation.md의
// Task 2 표 참고.
class MaroQueryLidarScanCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
    bool isUndoable() const override { return false; }
};

}  // namespace maro
