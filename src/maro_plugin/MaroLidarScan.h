#pragma once

#include <cstdint>
#include <vector>

#include <maya/MDagPath.h>
#include <maya/MMatrix.h>
#include <maya/MObject.h>

#include "maro_transform/Types.h"

namespace maro::lidar {
class ScanEngine;
}

namespace maro {

// 한 LiDAR 노드가 한 번의 스캔에 쏠 수 있는 레이 개수의 상한.
//
// MaroPump::collectLidarScans의 예전 상수와 같은 값이다 -- 위치만
// 옮겼다(MaroPump.cpp 익명 네임스페이스 -> 여기, 두 호출부가 공유하도록).
//
// [최종 리뷰 Minor-7] 추출 과정에서 사라진 근거를 되살려 둔다: 이 숫자는
// **성능 목표가 아니다.** 레이는 전부 Maya 메인 스레드에서 이 호출 안에
// 동기로 돌기 때문에, 어트리뷰트 에디터에 실수로 큰 값을 타이핑한 것 하나가
// Maya를 통째로 멈추게 할 수 있다 -- 그것만 막는 것이 유일한 목적이다.
// 값의 자리: 워킹 스켈레톤의 기본값(4 x 36 = 144)보다는 한참 위이고, 스펙이
// 말하는 실제 스케일(64 x 2048 = 131072)보다는 아래다. 진짜 스케일은
// 멀티스레드 레이어(스펙 §7)가 온 뒤에 이 상한과 함께 다시 본다.
constexpr long long kMaxRaysPerScan = 65536;

enum class LidarScanResult {
    kOk,
    kNoTargetMesh,
    kMeshExtractFailed,
    kInvalidConfig,
    kRayCountExceeded,
};

// Maya의 현재 선형 단위를 미터 배율로 바꾼다. MaroPump::collectSamples()와
// MaroPump::collectLidarScans() 둘 다 필요로 해서(전자는 축 값의 라디안/미터
// 변환에, 후자는 rangeMin/rangeMax의 미터->Maya 단위 변환에) 여기서 한 곳에만
// 둔다.
SceneUnit currentSceneUnit();

// meshNode(트랜스폼 또는 셰이프)에서 월드 좌표 정점/삼각형 인덱스 버퍼를
// 뽑는다. scanLidarNode()의 다중 메쉬 병합과, 별도 파일의 정밀 메쉬 충돌
// 커맨드(CollisionEngine 기반)가 공유한다 -- 트랜스폼에 셰이프가 둘 이상인
// 경우(마킹 메뉴가 LiDAR 로케이터를 타겟 메쉬와 같은 트랜스폼에 올리는 경우
// 등, 최종 리뷰 C-1 참고)와 intermediate object 제외까지 이미 하드닝된
// 로직이므로 같은 문제를 두 번 풀지 않는다. 실패(메쉬를 못 찾음, MFnMesh
// 생성 실패, getPoints/getTriangles 실패)하면 false, vertices/indices는
// 그대로 둔다.
bool extractMeshBuffers(const MObject& meshNode, std::vector<float>& vertices,
                        std::vector<std::uint32_t>& indices);

// meshPath가 이미 확정된 DAG 경로일 때(예: 인스턴스/다중 부모를 가진
// 노드에서 특정 인스턴스를 가리키는 경로) 이 오버로드를 쓴다 -- 위
// MObject 버전은 내부적으로 MDagPath::getAPathTo()를 호출하는데, 그
// 함수는 다중 인스턴스 노드에 대해 "첫 번째" 경로만 돌려줘서 호출부가
// 실제로 가리키려던 인스턴스와 다른 인스턴스의 지오메트리를 조용히
// 평가하게 만들 수 있다(이 파일의 다른 곳에 문서화된 것과 같은 함정,
// 최종 리뷰 Important-4). MaroCheckMeshCollisionCommand가 selection
// list에서 직접 얻은 MDagPath를 여기로 넘긴다.
bool extractMeshBuffers(const MDagPath& meshPath, std::vector<float>& vertices,
                        std::vector<std::uint32_t>& indices);

// scanLidarNode()가 실제 레이 원점/방향 계산에 쓰는 지오메트리를 호출부에
// 그대로 노출한다. maroQueryLidarScan(다음 스텝)이 Tech Diag의 정적 range/
// FOV 검사에 쓴다 -- Python이 좌표 변환 공식을 다시 유도하지 않고 이
// 행렬의 역행렬만 취하면 되게 하기 위함(설계 스펙 §4.2).
struct LidarGeometry {
    double rangeMinMaya = 0.0;
    double rangeMaxMaya = 0.0;
    double verticalMinAngle = 0.0;
    double verticalMaxAngle = 0.0;
    double horizontalMinAngle = 0.0;
    double horizontalMaxAngle = 0.0;
    MMatrix effectiveWorldMatrix;  // identity by default
};

// lidarNode의 현재 어트리뷰트를 읽어 즉시 동기 스캔하고, 히트를 Maya 월드
// 좌표(Vec3)로 outPoints에 채운다(호출 전 내용은 지운다). 스로틀
// (updateRate)이나 진단 래치(1회 경고)는 호출자 책임이다 -- 이 함수는 매번
// 무조건 스캔한다. engine은 호출자가 소유한다(재사용 가능 -- setMesh()는
// 반복 호출로 기존 지오메트리를 안전하게 교체한다).
LidarScanResult scanLidarNode(const MObject& lidarNode, maro::lidar::ScanEngine& engine,
                               const SceneUnit& unit, std::vector<Vec3>& outPoints,
                               LidarGeometry* outGeometry = nullptr);

}  // namespace maro
