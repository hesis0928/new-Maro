#include "maro_lidar/PointCloudPacking.h"

#include <cstring>

namespace maro::lidar {

namespace {
constexpr std::uint32_t kPointStep = 16;  // x,y,z,intensity, 전부 float32.
}

PackedPointCloud packPointCloud(const std::vector<maro::Vec3>& points,
                                 const std::vector<float>& intensities) {
    PackedPointCloud result;
    result.pointStep = kPointStep;
    result.width = static_cast<std::uint32_t>(points.size());
    result.data.resize(points.size() * kPointStep);

    for (std::size_t i = 0; i < points.size(); ++i) {
        const float x = static_cast<float>(points[i].x);
        const float y = static_cast<float>(points[i].y);
        const float z = static_cast<float>(points[i].z);
        const float intensity = (i < intensities.size()) ? intensities[i] : 0.0f;

        std::uint8_t* dst = result.data.data() + i * kPointStep;
        std::memcpy(dst + 0, &x, sizeof(float));
        std::memcpy(dst + 4, &y, sizeof(float));
        std::memcpy(dst + 8, &z, sizeof(float));
        std::memcpy(dst + 12, &intensity, sizeof(float));
    }

    return result;
}

}  // namespace maro::lidar
