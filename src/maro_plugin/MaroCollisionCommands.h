#pragma once

#include <maya/MPxCommand.h>
#include <maya/MSyntax.h>

namespace maro {

// <meshA> <meshB>: 두 메쉬가 실제로 폴리곤 단위로 교차하는지 판정한다
// (Embree rtcCollide 기반, maro_lidar::CollisionEngine 참고). 쿼리 전용,
// 씬을 바꾸지 않는다. setResult로 "true"/"false"/"unknown" 중 하나를
// 돌려준다 -- "unknown"은 둘 중 하나라도 폴리곤 메쉬가 아니라 추출에
// 실패한 경우(호출부인 Python이 이 경우 AABB 결과로 폴백한다, 설계 스펙
// §6.4).
class MaroCheckMeshCollisionCommand : public MPxCommand {
public:
    static void* creator();
    static MSyntax newSyntax();
    MStatus doIt(const MArgList& args) override;
    bool isUndoable() const override { return false; }
};

}  // namespace maro
