#pragma once

#include <cstdint>
#include <vector>

#include "maro_transform/Types.h"

// Embree 타입을 헤더에 노출하지 않는다 -- 전방 선언으로 포인터만 감싼다.
// 이 헤더를 포함하는 쪽(MaroLidarNode.cpp 등)이 embree4/rtcore.h를 몰라도 되게 한다.
//
// 아래 두 줄은 실제 설치된 헤더와 글자 그대로 같다(확인:
// `include/embree4/rtcore_device.h:11-12`, 같은 typedef가 `rtcore_geometry.h:12`에도
// 중복 선언돼 있다 -- 즉 동일 typedef 재선언은 Embree 자신도 하는 것이라
// 이 헤더와 rtcore.h를 같은 TU에서 함께 포함해도 안전하다).
// 또한 이 설치본은 `EMBREE_API_NAMESPACE`가 정의돼 있지 않아
// (`rtcore_config.h:31`) `RTC_NAMESPACE_BEGIN`이 빈 매크로로 확장된다 --
// Embree API가 전역 네임스페이스에 있으므로 아래 전방 선언도 전역이어야 맞다.
typedef struct RTCDeviceTy* RTCDevice;
typedef struct RTCSceneTy* RTCScene;

namespace maro::lidar {

struct RayHit {
    bool hit = false;
    maro::Vec3 position;
};

// Embree RTCScene을 감싼다. Maya도, 좌표계도 모른다 -- 호출부가 넘기는
// vertices/indices/origin/direction이 어느 좌표계든 그 좌표계로 결과를
// 돌려준다(이 플랜에서는 항상 Maya 좌표계로 쓰인다).
class ScanEngine {
public:
    ScanEngine();
    ~ScanEngine();

    ScanEngine(const ScanEngine&) = delete;
    ScanEngine& operator=(const ScanEngine&) = delete;

    // vertices: xyz가 이어진 배열(정점 개수 * 3). indices: 삼각형 정점
    // 인덱스가 이어진 배열(삼각형 개수 * 3). 다시 불러 기존 지오메트리를
    // 교체할 수 있다. 실패(빈 입력, Embree 오류)하면 false.
    bool setMesh(const std::vector<float>& vertices, const std::vector<std::uint32_t>& indices);

    // origin에서 direction(단위 벡터가 아니어도 되지만, 이 플랜에서는
    // RayPattern이 항상 단위 벡터를 준다) 방향으로 레이를 쏜다.
    // [rangeMin, rangeMax] 밖의 충돌은 무시한다.
    RayHit castRay(const maro::Vec3& origin, const maro::Vec3& direction, double rangeMin,
                   double rangeMax) const;

private:
    RTCDevice device_ = nullptr;
    RTCScene scene_ = nullptr;
};

}  // namespace maro::lidar
