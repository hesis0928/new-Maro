#pragma once

#include <cstdint>
#include <memory>
#include <vector>

typedef struct RTCDeviceTy* RTCDevice;
typedef struct RTCSceneTy* RTCScene;

namespace maro::lidar {

// CollisionEngine.cpp의 TU 전용 타입이라 여기서는 불투명 전방 선언만 둔다
// (RTCDevice/RTCScene과 같은 이유). setMeshes()가 rtcCollide용 씬을 빌드한
// 뒤에도 원본 정점/인덱스 버퍼를 계속 들고 있어야 하는 이유는
// CollisionEngine.cpp 상단 주석 참고 -- 요약하면 rtcCollide가
// RTC_GEOMETRY_TYPE_TRIANGLE을 지원하지 않아, 삼각형 하나당 사용자
// 지오메트리 하나로 감싸고 실제 교차 판정은 이 버퍼로 직접 해야 한다.
namespace detail {
struct TriangleBuffers;
}

// 두 폴리곤 메쉬가 실제로 교차하는지 Embree의 rtcCollide(씬-대-씬 폴리곤
// 단위 충돌 검사)로 판정한다. ScanEngine과 달리 레이캐스팅이 아니라 두
// 지오메트리 자체의 삼각형 쌍 교차를 직접 찾는다.
class CollisionEngine {
public:
    CollisionEngine();
    ~CollisionEngine();

    CollisionEngine(const CollisionEngine&) = delete;
    CollisionEngine& operator=(const CollisionEngine&) = delete;

    // 두 지오메트리를 각각 별도 RTCScene(같은 RTCDevice 위)으로 올린다.
    // 실패(빈 입력, 인덱스 범위 초과, Embree 오류)하면 false.
    bool setMeshes(const std::vector<float>& verticesA, const std::vector<std::uint32_t>& indicesA,
                   const std::vector<float>& verticesB, const std::vector<std::uint32_t>& indicesB);

    // rtcCollide를 호출해 실제 교차 삼각형 쌍이 하나라도 있으면 true.
    // setMeshes()가 실패했거나 아직 안 불렸으면 false.
    bool hasCollision() const;

private:
    RTCDevice device_ = nullptr;
    RTCScene sceneA_ = nullptr;
    RTCScene sceneB_ = nullptr;
    bool meshesSet_ = false;

    // 불완전 타입이라 unique_ptr로만 들 수 있다(포인터 크기만 알면 되므로
    // 헤더에서 정의를 요구하지 않는다). setMeshes()가 성공적으로 새 씬을
    // 만든 뒤에만 이 버퍼들을 교체한다 -- bounds 콜백과 hasCollision()의
    // 실제 삼각형-삼각형 교차 판정이 씬이 살아있는 내내 여기를 가리킨다.
    std::unique_ptr<detail::TriangleBuffers> buffersA_;
    std::unique_ptr<detail::TriangleBuffers> buffersB_;
};

}  // namespace maro::lidar
