#include "MaroCollisionCommands.h"

#include <cstdint>
#include <vector>

#include <maya/MArgDatabase.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MSelectionList.h>

#include "maro_lidar/CollisionEngine.h"

#include "MaroDiag.h"
#include "MaroLidarScan.h"  // extractMeshBuffers (Task 1이 공개로 승격)

namespace maro {

void* MaroCheckMeshCollisionCommand::creator() { return new MaroCheckMeshCollisionCommand(); }

MSyntax MaroCheckMeshCollisionCommand::newSyntax() {
    MSyntax syntax;
    syntax.setObjectType(MSyntax::kSelectionList, 2, 2);
    return syntax;
}

MStatus MaroCheckMeshCollisionCommand::doIt(const MArgList& args) {
    maro::ScopedCommandContext ctxMarker("MaroCheckMeshCollisionCommand");
    try {
        MStatus status;
        MArgDatabase argData(syntax(), args, &status);
        if (!status) return status;

        MSelectionList selection;
        argData.getObjects(selection);
        if (selection.length() != 2) {
            maro::BoadMaro::error(
                "MaroCheckMeshCollisionCommand.WrongArgCount",
                "Maro: maroCheckMeshCollision needs exactly two arguments: <meshA> <meshB>.",
                maro::onfix::capture("", "", ""));
            return MS::kFailure;
        }

        MObject meshA, meshB;
        selection.getDependNode(0, meshA);
        selection.getDependNode(1, meshB);

        std::vector<float> verticesA, verticesB;
        std::vector<std::uint32_t> indicesA, indicesB;
        if (!extractMeshBuffers(meshA, verticesA, indicesA) ||
            !extractMeshBuffers(meshB, verticesB, indicesB)) {
            setResult(MString("unknown"));
            return MS::kSuccess;
        }

        maro::lidar::CollisionEngine engine;
        if (!engine.setMeshes(verticesA, indicesA, verticesB, indicesB)) {
            setResult(MString("unknown"));
            return MS::kSuccess;
        }

        setResult(MString(engine.hasCollision() ? "true" : "false"));
        return MS::kSuccess;
    } catch (const std::exception& e) {
        maro::BoadMaro::error("MaroCheckMeshCollisionCommand.doIt.Exception",
                              MString("Maro: maroCheckMeshCollision failed: ") + e.what());
        return MS::kFailure;
    } catch (...) {
        maro::BoadMaro::error("MaroCheckMeshCollisionCommand.doIt.UnknownException",
                              "Maro: maroCheckMeshCollision failed with unknown error.");
        return MS::kFailure;
    }
}

}  // namespace maro
