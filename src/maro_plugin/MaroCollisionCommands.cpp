#include "MaroCollisionCommands.h"

#include <cstdint>
#include <vector>

#include <maya/MArgDatabase.h>
#include <maya/MDagPath.h>
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

        // getDependNode()로 얻는 bare MObject는 다중 인스턴스/다중 부모
        // 노드에서 어느 인스턴스를 가리키는지 정보를 잃는다 --
        // extractMeshBuffers(MObject)는 내부적으로 MDagPath::getAPathTo()를
        // 호출하는데, 그 함수는 그런 노드에 대해 "첫 번째" 경로만 돌려줘서
        // 호출부(여기)가 실제로 선택한 인스턴스와 다른 인스턴스의 지오메트리를
        // 조용히 평가하게 만들 수 있다(MaroLidarScan.cpp의 같은 함정 문서
        // 참고, 최종 리뷰 Important-4). getDagPath()로 selection list가 이미
        // 확정해 둔 정확한 경로를 그대로 쓴다.
        MDagPath pathA, pathB;
        if (selection.getDagPath(0, pathA) != MS::kSuccess ||
            selection.getDagPath(1, pathB) != MS::kSuccess) {
            // 인자가 DAG 객체가 아니면(예: 의존 그래프 노드) 폴리곤 메쉬로
            // 해석할 수 없다는 뜻이다 -- 이 커맨드가 이미 "판정 불가"로
            // 보고하는 경우와 같은 케이스이므로 커맨드 실패가 아니라
            // "unknown"으로 라우팅한다.
            setResult(MString("unknown"));
            return MS::kSuccess;
        }

        std::vector<float> verticesA, verticesB;
        std::vector<std::uint32_t> indicesA, indicesB;
        if (!extractMeshBuffers(pathA, verticesA, indicesA) ||
            !extractMeshBuffers(pathB, verticesB, indicesB)) {
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
