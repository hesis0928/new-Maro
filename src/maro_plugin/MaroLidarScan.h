#pragma once

#include <vector>

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

// lidarNode의 현재 어트리뷰트를 읽어 즉시 동기 스캔하고, 히트를 Maya 월드
// 좌표(Vec3)로 outPoints에 채운다(호출 전 내용은 지운다). 스로틀
// (updateRate)이나 진단 래치(1회 경고)는 호출자 책임이다 -- 이 함수는 매번
// 무조건 스캔한다. engine은 호출자가 소유한다(재사용 가능 -- setMesh()는
// 반복 호출로 기존 지오메트리를 안전하게 교체한다).
LidarScanResult scanLidarNode(const MObject& lidarNode, maro::lidar::ScanEngine& engine,
                               const SceneUnit& unit, std::vector<Vec3>& outPoints);

}  // namespace maro
