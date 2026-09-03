#include "maro_lidar/CollisionEngine.h"

#include <algorithm>
#include <cmath>

#include <embree4/rtcore.h>

// [Task 4 실측 발견 -- 이 파일이 브리프의 원안(Step 3)과 다른 이유]
//
// 브리프는 두 지오메트리를 RTC_GEOMETRY_TYPE_TRIANGLE 씬으로 올리고
// rtcCollide()를 그대로 부르면 실제 교차하는 삼각형 쌍에서 콜백이 온다고
// 가정했다. 이 파일의 첫 버전을 정확히 그렇게(브리프 코드 그대로) 짜서
// tests/maya/test_mesh_collision.py를 돌렸더니, 두 겹친 큐브에
// hasCollision()을 부르는 순간 Maya 프로세스가 access violation으로
// 죽었다(mayapy 종료 코드 -1073741819 = 0xC0000005). 단계별로
// MGlobal::displayInfo() 진단을 넣어 추적한 결과 크래시 지점은
// extractMeshBuffers()도, setMeshes()(씬 빌드 자체)도 아니라 정확히
// rtcCollide() 호출 안이었다.
//
// vcpkg가 받아온 원본 소스 아카이브(C:/src/vcpkg/downloads/
// RenderKit-embree-v4.4.0.tar.gz)의 kernels/common/rtcore.cpp:482-485를
// 보면, DEBUG 빌드에서만 켜지는 사전조건 검사가 있다:
//   "scenes must only contain user geometries with a single timestep"
// vcpkg가 배포하는 것은 Release 빌드라 이 검사 자체가 컴파일에서
// 빠진다 -- 그래서 우리 쪽에서는 사전조건 위반이 예외/에러가 아니라 곧장
// 크래시로 나타났다. 같은 소스 트리의 kernels/bvh/bvh4_factory.cpp:810이
// `intersectors.collider`를 지오메트리 타입과 무관하게 무조건
// BVH4ColliderUserGeom으로 고정하는 것도 확인했다: bvh_collider.cpp의
// processLeaf()가 BVH 리프를 항상 사용자 지오메트리 프리미티브 타입인
// `Object*`로 캐스트한다(kernels/bvh/bvh_collider.cpp:118-119) -- 리프가
// 실제로는 삼각형 프리미티브(TriangleM)를 담고 있으면 이 캐스트가 완전히
// 다른 메모리 레이아웃을 잘못 해석해 geomID/primID에 쓰레기 값이 나오고,
// 그 값으로 뒤이어 정점/삼각형 배열을 인덱싱하면서 범위를 벗어나
// 크래시한다. 이건 vcpkg 배포판만의 우연한 결함이 아니라 API 계약 자체다
// -- Embree 공식 문서(같은 아카이브의 doc/src/api/rtcCollide.md)가
// 명시한다: "Currently, only scene entirely composed of user geometries
// are supported... Currently, the only supported type is the user
// geometry type (RTC_GEOMETRY_TYPE_USER)." 이 문장은 벤더링된
// rtcore_scene.h의 rtcCollide 선언부 주석에는 없다(브리프의 Step 1이
// 정확히 짚은 "문서화되지 않은 사전조건"이 이것이었다) -- 헤더가 아니라
// 별도 배포되는 doc/ 트리에만 있다.
//
// 즉 rtcCollide는 "두 삼각형 씬을 통째로 비교해 실제 교차 쌍을 알려주는"
// API가 아니라, "사용자가 제공한 AABB(경계 상자)들의 BVH 리프 단위
// 후보쌍만 골라주는" API다 -- 정확한 삼각형-삼각형 교차 판정은 콜백 안에서
// 호출부가 직접 해야 한다(같은 문서: "the user is expected to implement a
// primitive/primitive intersection to filter out false positives in the
// callback function"). 그래서 아래 구현은 삼각형 하나당 사용자 지오메트리
// 프리미티브 하나로 감싸고(bounds 함수만 필요하다 -- rtcIntersect1/
// rtcOccluded1은 이 씬들에 안 쓰므로 intersect 콜백은 등록하지 않는다),
// rtcCollide가 돌려준 (geomID0,primID0,geomID1,primID1) 후보쌍마다 분리축
// 정리(Separating Axis Theorem)로 정확한 삼각형-삼각형 교차를 직접
// 검사한다. Embree 내부의 실제 삼각형-삼각형 교차 함수
// (kernels/bvh/bvh_collider.cpp의 intersect_triangle_triangle)는 공개
// API로 노출돼 있지 않아 재사용할 수 없다.

namespace maro::lidar {

namespace detail {
// setMeshes()가 성공한 뒤 그 지오메트리가 CollisionEngine에 머무는 동안
// 계속 필요하다 -- Embree의 bounds 콜백(삼각형 하나의 AABB를 매번 다시
// 계산)과 hasCollision()의 정확 교차 판정(rtcCollide가 돌려준 primID로
// 실제 정점 좌표를 다시 읽어야 한다) 둘 다 이 원본 버퍼를 직접 읽는다.
struct TriangleBuffers {
    std::vector<float> vertices;
    std::vector<std::uint32_t> indices;
};
}  // namespace detail

namespace {

struct Vec3d {
    double x = 0.0;
    double y = 0.0;
    double z = 0.0;
};

Vec3d sub(const Vec3d& a, const Vec3d& b) { return {a.x - b.x, a.y - b.y, a.z - b.z}; }
Vec3d cross(const Vec3d& a, const Vec3d& b) {
    return {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x};
}
double dot(const Vec3d& a, const Vec3d& b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
double length2(const Vec3d& a) { return dot(a, a); }

Vec3d triangleVertex(const detail::TriangleBuffers& mesh, unsigned int triIndex, int corner) {
    const std::uint32_t vi = mesh.indices[static_cast<std::size_t>(triIndex) * 3 + corner];
    return Vec3d{mesh.vertices[static_cast<std::size_t>(vi) * 3 + 0],
                 mesh.vertices[static_cast<std::size_t>(vi) * 3 + 1],
                 mesh.vertices[static_cast<std::size_t>(vi) * 3 + 2]};
}

void projectTriangle(const Vec3d tri[3], const Vec3d& axis, double& outMin, double& outMax) {
    const double d0 = dot(tri[0], axis);
    const double d1 = dot(tri[1], axis);
    const double d2 = dot(tri[2], axis);
    outMin = std::min({d0, d1, d2});
    outMax = std::max({d0, d1, d2});
}

// axis가 퇴화(길이 0에 가까움)면 분리축이 될 수 없으므로 false(분리 안 됨).
bool axisSeparates(const Vec3d a[3], const Vec3d b[3], const Vec3d& axis, double axisLenEps, double gapEps) {
    if (length2(axis) < axisLenEps * axisLenEps) return false;
    double aMin, aMax, bMin, bMax;
    projectTriangle(a, axis, aMin, aMax);
    projectTriangle(b, axis, bMin, bMax);
    return aMax < bMin - gapEps || bMax < aMin - gapEps;
}

// 두 삼각형이 실제로(면끼리) 교차/접촉하는지 분리축 정리(SAT)로 정확히
// 판정한다. 일반적인 3D 삼각형-삼각형 SAT은 11개 축(양쪽 법선 2개 + 변끼리
// 외적 9개)이면 충분하지만, 두 삼각형이 (거의) 같은 평면 위에 있을 때는
// 그 11개 축이 전부 평면 법선과 평행해져 버려 평면 안에서의 분리를 전혀
// 구분하지 못한다(두 축 다 법선 방향으로 투영하면 둘 다 폭 0인 같은 점으로
// 겹쳐 보인다). 그런 경우 표준 2D 볼록다각형 SAT(각 변의 평면-내
// 법선축)으로 대체한다.
bool trianglesIntersect(const Vec3d a[3], const Vec3d b[3]) {
    const Vec3d edgesA[3] = {sub(a[1], a[0]), sub(a[2], a[1]), sub(a[0], a[2])};
    const Vec3d edgesB[3] = {sub(b[1], b[0]), sub(b[2], b[1]), sub(b[0], b[2])};
    const Vec3d normalA = cross(edgesA[0], edgesA[1]);
    const Vec3d normalB = cross(edgesB[0], edgesB[1]);

    // 씬 크기에 맞춘(scale-aware) 허용오차 -- Maya 씬은 cm~m 등 단위가
    // 다양하므로 절대 상수 eps는 너무 크거나 작을 수 있다.
    double maxEdgeLen2 = 0.0;
    for (const Vec3d& e : edgesA) maxEdgeLen2 = std::max(maxEdgeLen2, length2(e));
    for (const Vec3d& e : edgesB) maxEdgeLen2 = std::max(maxEdgeLen2, length2(e));
    double scale = std::sqrt(maxEdgeLen2);
    if (scale < 1e-12) scale = 1e-12;
    const double eps = scale * 1e-6;

    const double normalALen = std::sqrt(length2(normalA));
    const double normalBLen = std::sqrt(length2(normalB));
    bool coplanar = false;
    if (normalALen > eps && normalBLen > eps) {
        // 법선이 (거의) 평행한가 -- sin(각도) ~= |cross|/(|n0||n1|).
        const double sinAngle = std::sqrt(length2(cross(normalA, normalB))) / (normalALen * normalBLen);
        if (sinAngle < 1e-6) {
            const double planeDist = std::fabs(dot(normalA, sub(b[0], a[0]))) / normalALen;
            if (planeDist < eps) coplanar = true;
        }
    }

    if (!coplanar) {
        if (axisSeparates(a, b, normalA, eps, eps)) return false;
        if (axisSeparates(a, b, normalB, eps, eps)) return false;
        for (const Vec3d& ea : edgesA) {
            for (const Vec3d& eb : edgesB) {
                if (axisSeparates(a, b, cross(ea, eb), eps, eps)) return false;
            }
        }
        return true;
    }

    // 동일 평면: 각 변의 평면-내 법선(변 x 삼각형 법선)을 분리축으로 쓰는
    // 표준 2D 볼록다각형 SAT.
    for (const Vec3d& ea : edgesA) {
        if (axisSeparates(a, b, cross(normalA, ea), eps, eps)) return false;
    }
    for (const Vec3d& eb : edgesB) {
        if (axisSeparates(a, b, cross(normalB, eb), eps, eps)) return false;
    }
    return true;
}

void boundsFunc(const RTCBoundsFunctionArguments* args) {
    const auto* mesh = static_cast<const detail::TriangleBuffers*>(args->geometryUserPtr);
    const Vec3d v0 = triangleVertex(*mesh, args->primID, 0);
    const Vec3d v1 = triangleVertex(*mesh, args->primID, 1);
    const Vec3d v2 = triangleVertex(*mesh, args->primID, 2);
    RTCBounds& out = *args->bounds_o;
    out.lower_x = static_cast<float>(std::min({v0.x, v1.x, v2.x}));
    out.lower_y = static_cast<float>(std::min({v0.y, v1.y, v2.y}));
    out.lower_z = static_cast<float>(std::min({v0.z, v1.z, v2.z}));
    out.upper_x = static_cast<float>(std::max({v0.x, v1.x, v2.x}));
    out.upper_y = static_cast<float>(std::max({v0.y, v1.y, v2.y}));
    out.upper_z = static_cast<float>(std::max({v0.z, v1.z, v2.z}));
}

// 하나의 RTCScene에 삼각형 메쉬 하나를 "삼각형 개수만큼의 사용자 지오메트리
// 프리미티브"로 올린다(위 파일 상단 주석 참고 -- RTC_GEOMETRY_TYPE_TRIANGLE은
// rtcCollide에서 쓸 수 없다). bounds 함수만 등록한다: 이 씬들에는
// rtcIntersect1/rtcOccluded1을 절대 부르지 않으므로 intersect/occluded
// 콜백은 필요 없다.
RTCScene buildUserScene(RTCDevice device, const detail::TriangleBuffers& mesh) {
    if (mesh.vertices.empty() || mesh.indices.empty()) return nullptr;
    if (mesh.vertices.size() % 3 != 0 || mesh.indices.size() % 3 != 0) return nullptr;
    const std::size_t vertexCount = mesh.vertices.size() / 3;
    for (const std::uint32_t index : mesh.indices) {
        if (static_cast<std::size_t>(index) >= vertexCount) return nullptr;
    }

    const std::size_t triangleCount = mesh.indices.size() / 3;
    if (triangleCount == 0) return nullptr;

    RTCScene scene = rtcNewScene(device);
    if (scene == nullptr) return nullptr;

    RTCGeometry geom = rtcNewGeometry(device, RTC_GEOMETRY_TYPE_USER);
    if (geom == nullptr) {
        rtcReleaseScene(scene);
        return nullptr;
    }

    rtcSetGeometryUserPrimitiveCount(geom, static_cast<unsigned int>(triangleCount));
    rtcSetGeometryUserData(geom, const_cast<void*>(static_cast<const void*>(&mesh)));
    rtcSetGeometryBoundsFunction(geom, boundsFunc, nullptr);

    rtcCommitGeometry(geom);
    rtcAttachGeometry(scene, geom);
    rtcReleaseGeometry(geom);  // scene이 자체적으로 참조를 갖는다.
    rtcCommitScene(scene);
    return scene;
}

struct CollideContext {
    const detail::TriangleBuffers* meshA = nullptr;
    const detail::TriangleBuffers* meshB = nullptr;
    bool found = false;
};

// rtcCollide는 "이 두 프리미티브의 AABB가 겹친다"는 후보쌍만 준다 -- 여기서
// 실제 삼각형-삼각형 교차를 직접 검사해 오탐(AABB만 겹치고 실제 표면은 안
// 닿는 경우)을 걸러낸다.
void collideCallback(void* userPtr, RTCCollision* collisions, unsigned int numCollisions) {
    auto* ctx = static_cast<CollideContext*>(userPtr);
    if (ctx->found) return;
    for (unsigned int i = 0; i < numCollisions; ++i) {
        const Vec3d triA[3] = {
            triangleVertex(*ctx->meshA, collisions[i].primID0, 0),
            triangleVertex(*ctx->meshA, collisions[i].primID0, 1),
            triangleVertex(*ctx->meshA, collisions[i].primID0, 2),
        };
        const Vec3d triB[3] = {
            triangleVertex(*ctx->meshB, collisions[i].primID1, 0),
            triangleVertex(*ctx->meshB, collisions[i].primID1, 1),
            triangleVertex(*ctx->meshB, collisions[i].primID1, 2),
        };
        if (trianglesIntersect(triA, triB)) {
            ctx->found = true;
            return;
        }
    }
}

}  // namespace

CollisionEngine::CollisionEngine() {
    device_ = rtcNewDevice(nullptr);
}

CollisionEngine::~CollisionEngine() {
    if (sceneA_ != nullptr) rtcReleaseScene(sceneA_);
    if (sceneB_ != nullptr) rtcReleaseScene(sceneB_);
    if (device_ != nullptr) rtcReleaseDevice(device_);
}

bool CollisionEngine::setMeshes(const std::vector<float>& verticesA,
                                 const std::vector<std::uint32_t>& indicesA,
                                 const std::vector<float>& verticesB,
                                 const std::vector<std::uint32_t>& indicesB) {
    meshesSet_ = false;
    if (device_ == nullptr) return false;

    // 새 버퍼/씬을 지역 변수에 전부 완성한 뒤 성공했을 때만 멤버에 반영한다
    // -- ScanEngine::setMesh()와 같은 "실패한 호출이 기존 지오메트리를
    // 망가뜨리지 않는다" 규율.
    auto newBuffersA = std::make_unique<detail::TriangleBuffers>();
    newBuffersA->vertices = verticesA;
    newBuffersA->indices = indicesA;
    auto newBuffersB = std::make_unique<detail::TriangleBuffers>();
    newBuffersB->vertices = verticesB;
    newBuffersB->indices = indicesB;

    RTCScene newSceneA = buildUserScene(device_, *newBuffersA);
    if (newSceneA == nullptr) return false;
    RTCScene newSceneB = buildUserScene(device_, *newBuffersB);
    if (newSceneB == nullptr) {
        rtcReleaseScene(newSceneA);
        return false;
    }

    if (sceneA_ != nullptr) rtcReleaseScene(sceneA_);
    if (sceneB_ != nullptr) rtcReleaseScene(sceneB_);
    sceneA_ = newSceneA;
    sceneB_ = newSceneB;
    buffersA_ = std::move(newBuffersA);
    buffersB_ = std::move(newBuffersB);
    meshesSet_ = true;
    return true;
}

bool CollisionEngine::hasCollision() const {
    if (!meshesSet_ || sceneA_ == nullptr || sceneB_ == nullptr) return false;
    CollideContext ctx{buffersA_.get(), buffersB_.get(), false};
    rtcCollide(sceneA_, sceneB_, collideCallback, &ctx);
    return ctx.found;
}

}  // namespace maro::lidar
