#include "MaroLidarCommands.h"

#include <vector>

#include <maya/MArgDatabase.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MFnPointArrayData.h>
#include <maya/MPointArray.h>
#include <maya/MSelectionList.h>

#include "maro_lidar/ScanEngine.h"
#include "maro_transform/Types.h"

#include "MaroDiag.h"
#include "MaroLidarNode.h"
#include "MaroLidarScan.h"
#include "MaroPointCloudNode.h"

namespace maro {

void* MaroSnapshotLidarScanCommand::creator() { return new MaroSnapshotLidarScanCommand(); }

MSyntax MaroSnapshotLidarScanCommand::newSyntax() {
    MSyntax syntax;
    syntax.setObjectType(MSyntax::kSelectionList, 2, 2);
    return syntax;
}

MStatus MaroSnapshotLidarScanCommand::doIt(const MArgList& args) {
    maro::ScopedCommandContext ctxMarker("MaroSnapshotLidarScanCommand");
    try {
        MStatus status;
        MArgDatabase argData(syntax(), args, &status);
        if (!status) return status;

        MSelectionList selection;
        argData.getObjects(selection);
        if (selection.length() != 2) {
            maro::BoadMaro::error(
                "MaroSnapshotLidarScanCommand.WrongArgCount",
                "Maro: maroSnapshotLidarScan needs exactly two arguments: "
                "<lidarNode> <pointCloudNode>.",
                maro::onfix::capture("", "", ""));
            return MS::kFailure;
        }

        MObject lidarObj, pointCloudObj;
        selection.getDependNode(0, lidarObj);
        selection.getDependNode(1, pointCloudObj);

        MFnDependencyNode lidarFn(lidarObj);
        if (lidarFn.typeId() != MaroLidarNode::id) {
            maro::BoadMaro::error(
                "MaroSnapshotLidarScanCommand.NotMaroLidarNode",
                MString("Maro: '") + lidarFn.name() + "' is not a maroLidar node.",
                maro::onfix::capture(lidarFn.typeName(), "", lidarFn.name()));
            return MS::kFailure;
        }
        MFnDependencyNode pointCloudFn(pointCloudObj);
        if (pointCloudFn.typeId() != MaroPointCloudNode::id) {
            maro::BoadMaro::error(
                "MaroSnapshotLidarScanCommand.NotMaroPointCloudNode",
                MString("Maro: '") + pointCloudFn.name() + "' is not a maroPointCloud node.",
                maro::onfix::capture(pointCloudFn.typeName(), "", pointCloudFn.name()));
            return MS::kFailure;
        }

        // 브리지의 공유 ScanEngine과 무관한 자체 인스턴스 -- 이 커맨드는
        // MaroPump/MaroRosRuntime 상태를 전혀 건드리지 않는다.
        maro::lidar::ScanEngine engine;
        std::vector<Vec3> points;
        const LidarScanResult result =
            scanLidarNode(lidarObj, engine, currentSceneUnit(), points);

        if (result != LidarScanResult::kOk) {
            const char* reason = "unknown";
            switch (result) {
                case LidarScanResult::kNoTargetMesh: reason = "no target mesh connected"; break;
                case LidarScanResult::kMeshExtractFailed: reason = "failed to read the target mesh"; break;
                case LidarScanResult::kInvalidConfig: reason = "invalid angle/range configuration"; break;
                case LidarScanResult::kRayCountExceeded: reason = "verticalSamples x horizontalSamples exceeds the per-scan cap"; break;
                default: break;
            }
            maro::BoadMaro::error(
                "MaroSnapshotLidarScanCommand.ScanFailed",
                MString("Maro: scan of '") + lidarFn.name() + "' failed: " + reason + ".",
                maro::onfix::capture(lidarFn.typeName(), "", lidarFn.name()));
            return MS::kFailure;
        }

        MPointArray mayaPoints;
        mayaPoints.setLength(static_cast<unsigned int>(points.size()));
        for (unsigned int i = 0; i < mayaPoints.length(); ++i) {
            mayaPoints[i] = MPoint(points[i].x, points[i].y, points[i].z, 1.0);
        }
        MFnPointArrayData pointArrayDataFn;
        MObject pointsData = pointArrayDataFn.create(mayaPoints);

        MPlug pointsPlug = pointCloudFn.findPlug(MaroPointCloudNode::aPoints, false);
        status = m_modifier.newPlugValue(pointsPlug, pointsData);
        if (!status) {
            maro::BoadMaro::error(
                "MaroSnapshotLidarScanCommand.SetPointsFailed",
                MString("Maro: failed to stage the points update on '") +
                    pointCloudFn.name() + "'.",
                maro::onfix::capture(pointCloudFn.typeName(), "points", pointCloudFn.name()));
            return status;
        }

        m_stagedChange = true;
        return redoIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroSnapshotLidarScanCommand.doIt.Exception",
                              MString("Maro: maroSnapshotLidarScan failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroSnapshotLidarScanCommand.doIt.UnknownException",
                              "Maro: maroSnapshotLidarScan failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroSnapshotLidarScanCommand::redoIt() {
    maro::ScopedCommandContext ctxMarker("MaroSnapshotLidarScanCommand");
    try {
        return m_modifier.doIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroSnapshotLidarScanCommand.redoIt.Exception",
                              MString("Maro: maroSnapshotLidarScan redo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroSnapshotLidarScanCommand.redoIt.UnknownException",
                              "Maro: maroSnapshotLidarScan redo failed with unknown error.");
        return MS::kFailure;
    }
}

MStatus MaroSnapshotLidarScanCommand::undoIt() {
    maro::ScopedCommandContext ctxMarker("MaroSnapshotLidarScanCommand");
    try {
        return m_modifier.undoIt();
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroSnapshotLidarScanCommand.undoIt.Exception",
                              MString("Maro: maroSnapshotLidarScan undo failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroSnapshotLidarScanCommand.undoIt.UnknownException",
                              "Maro: maroSnapshotLidarScan undo failed with unknown error.");
        return MS::kFailure;
    }
}

}  // namespace maro
