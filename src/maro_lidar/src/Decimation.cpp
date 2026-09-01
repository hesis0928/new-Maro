#include "maro_lidar/Decimation.h"

namespace maro::lidar {

std::vector<maro::Vec3> decimateForPreview(const std::vector<maro::Vec3>& points,
                                            std::size_t maxPoints) {
    if (maxPoints == 0 || points.empty()) return {};
    if (points.size() <= maxPoints) return points;

    std::vector<maro::Vec3> decimated;
    decimated.reserve(maxPoints);
    // 끝점 포함(endpoint-inclusive) 스트라이드: i*stride를 count 기준으로
    // 나누면(= points.size()/maxPoints) 마지막 인덱스가 항상 (maxPoints-1)*stride로
    // 끝나 원본 마지막 근방에 못 미칠 수 있다(예: size=1000, maxPoints=10이면
    // 마지막 인덱스가 정확히 900, 원본 끝 999와 거리가 남는다). 대신 인덱스
    // 범위(points.size()-1)를 (maxPoints-1) 구간으로 나눠, i=0은 항상 첫
    // 점을, i=maxPoints-1은 항상 마지막 점을 가리키게 한다 -- "전체 범위를
    // 고르게 커버"를 끝점까지 포함해 만족시킨다.
    const double lastIndex = static_cast<double>(points.size() - 1);
    const double denom = static_cast<double>(maxPoints > 1 ? maxPoints - 1 : 1);
    for (std::size_t i = 0; i < maxPoints; ++i) {
        const auto index = static_cast<std::size_t>(static_cast<double>(i) * lastIndex / denom);
        decimated.push_back(points[index < points.size() ? index : points.size() - 1]);
    }
    return decimated;
}

}  // namespace maro::lidar
