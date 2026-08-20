#include "maro_lidar/ScanEngine.h"

#include <embree4/rtcore.h>

namespace maro::lidar {

ScanEngine::ScanEngine() {
    device_ = rtcNewDevice(nullptr);
}

ScanEngine::~ScanEngine() {
    if (scene_ != nullptr) rtcReleaseScene(scene_);
    if (device_ != nullptr) rtcReleaseDevice(device_);
}

bool ScanEngine::setMesh(const std::vector<float>& vertices, const std::vector<std::uint32_t>& indices) {
    if (device_ == nullptr) return false;
    if (vertices.empty() || indices.empty()) return false;
    if (vertices.size() % 3 != 0 || indices.size() % 3 != 0) return false;

    const std::size_t vertexCount = vertices.size() / 3;

    // Embree는 인덱스 범위를 검사하지 않는다 -- 범위를 넘는 인덱스는 버퍼 밖을
    // 읽어 크래시로 이어진다. Task 6이 MFnMesh에서 뽑은 값을 그대로 넘길
    // 예정이므로, 잘못된 입력은 여기서 false로 막는다.
    for (const std::uint32_t index : indices) {
        if (static_cast<std::size_t>(index) >= vertexCount) return false;
    }

    // 맨 끝에서 보는 오류 플래그가 이번 호출에서 생긴 것만 반영하도록,
    // device에 남아 있을 수 있는 이전 오류를 먼저 읽어서 지운다
    // (rtcGetDeviceError는 읽으면서 플래그를 RTC_ERROR_NONE으로 되돌린다).
    rtcGetDeviceError(device_);

    // 새 씬을 지역 변수에 완성한 뒤, 전부 성공했을 때만 scene_에 넣는다.
    // 중간에 실패하면 기존 scene_은 손대지 않은 채 그대로 남는다 -- 실패한
    // setMesh()가 이전 지오메트리를 망가뜨리지 않고, 무엇보다 commit되지 않은
    // 씬이 scene_에 들어가는 일이 없다(castRay의 nullptr 검사만으로는
    // "non-null이지만 commit 안 된 씬"을 걸러내지 못한다).
    RTCScene newScene = rtcNewScene(device_);
    if (newScene == nullptr) return false;

    RTCGeometry geom = rtcNewGeometry(device_, RTC_GEOMETRY_TYPE_TRIANGLE);
    if (geom == nullptr) {
        rtcReleaseScene(newScene);
        return false;
    }

    // rtcSetSharedGeometryBuffer가 아니라 rtcSetNewGeometryBuffer를 쓴다:
    // 공유 버퍼는 호출부의 배열이 지오메트리보다 오래 살아 있어야 하는데
    // setMesh()의 인자는 임시 벡터일 수 있다(테스트가 실제로 그렇게 넘긴다).
    // 새 버퍼는 Embree가 소유하고 정렬/패딩도 스스로 처리하므로 값만 복사한다.
    float* vertexBuffer = static_cast<float*>(rtcSetNewGeometryBuffer(
        geom, RTC_BUFFER_TYPE_VERTEX, 0, RTC_FORMAT_FLOAT3, 3 * sizeof(float), vertexCount));
    if (vertexBuffer == nullptr) {
        rtcReleaseGeometry(geom);
        rtcReleaseScene(newScene);
        return false;
    }
    for (std::size_t i = 0; i < vertices.size(); ++i) vertexBuffer[i] = vertices[i];

    const std::size_t triangleCount = indices.size() / 3;
    unsigned int* indexBuffer = static_cast<unsigned int*>(rtcSetNewGeometryBuffer(
        geom, RTC_BUFFER_TYPE_INDEX, 0, RTC_FORMAT_UINT3, 3 * sizeof(unsigned int), triangleCount));
    if (indexBuffer == nullptr) {
        rtcReleaseGeometry(geom);
        rtcReleaseScene(newScene);
        return false;
    }
    for (std::size_t i = 0; i < indices.size(); ++i) {
        indexBuffer[i] = static_cast<unsigned int>(indices[i]);
    }

    rtcCommitGeometry(geom);
    rtcAttachGeometry(newScene, geom);
    rtcReleaseGeometry(geom);  // newScene이 자체적으로 참조를 갖는다.
    rtcCommitScene(newScene);

    if (rtcGetDeviceError(device_) != RTC_ERROR_NONE) {
        rtcReleaseScene(newScene);
        return false;
    }

    if (scene_ != nullptr) rtcReleaseScene(scene_);
    scene_ = newScene;
    return true;
}

RayHit ScanEngine::castRay(const maro::Vec3& origin, const maro::Vec3& direction, double rangeMin,
                            double rangeMax) const {
    RayHit result;
    if (scene_ == nullptr) return result;

    RTCRayHit rayhit;
    rayhit.ray.org_x = static_cast<float>(origin.x);
    rayhit.ray.org_y = static_cast<float>(origin.y);
    rayhit.ray.org_z = static_cast<float>(origin.z);
    rayhit.ray.dir_x = static_cast<float>(direction.x);
    rayhit.ray.dir_y = static_cast<float>(direction.y);
    rayhit.ray.dir_z = static_cast<float>(direction.z);
    rayhit.ray.tnear = static_cast<float>(rangeMin);
    rayhit.ray.tfar = static_cast<float>(rangeMax);
    // RTCRay에는 모션 블러용 time 필드가 있다(rtcore_ray.h:20). 이 플랜은
    // 모션 블러를 쓰지 않지만, 스택에 잡은 구조체를 초기화하지 않고 두면
    // 쓰레기 값이 들어가므로 명시적으로 0을 넣는다.
    rayhit.ray.time = 0.0f;
    rayhit.ray.id = 0;
    rayhit.ray.mask = static_cast<unsigned int>(-1);
    rayhit.ray.flags = 0;
    rayhit.hit.geomID = RTC_INVALID_GEOMETRY_ID;
    rayhit.hit.instID[0] = RTC_INVALID_GEOMETRY_ID;

    rtcIntersect1(scene_, &rayhit);

    if (rayhit.hit.geomID == RTC_INVALID_GEOMETRY_ID) return result;

    // 충돌하면 Embree가 ray.tfar를 충돌 거리로 덮어쓴다(rtcore_ray.h:23의
    // "end of ray segment (set to hit distance)").
    result.hit = true;
    result.position = maro::Vec3{
        origin.x + direction.x * rayhit.ray.tfar,
        origin.y + direction.y * rayhit.ray.tfar,
        origin.z + direction.z * rayhit.ray.tfar,
    };
    return result;
}

}  // namespace maro::lidar
