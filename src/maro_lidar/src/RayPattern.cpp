#include "maro_lidar/RayPattern.h"

#include <cmath>

namespace maro::lidar {

namespace {

// samples가 1이면 0으로 나누기를 피해 minAngle 하나만 쓴다.
double angleAt(int index, int samples, double minAngle, double maxAngle) {
    if (samples <= 1) return minAngle;
    return minAngle + (maxAngle - minAngle) * (static_cast<double>(index) /
                                                 static_cast<double>(samples - 1));
}

}  // namespace

std::vector<maro::Vec3> computeRayDirections(int verticalSamples, double verticalMinAngle,
                                              double verticalMaxAngle, int horizontalSamples,
                                              double horizontalMinAngle, double horizontalMaxAngle) {
    std::vector<maro::Vec3> directions;
    if (verticalSamples <= 0 || horizontalSamples <= 0) return directions;
    directions.reserve(static_cast<std::size_t>(verticalSamples) *
                        static_cast<std::size_t>(horizontalSamples));

    for (int v = 0; v < verticalSamples; ++v) {
        const double vertical = angleAt(v, verticalSamples, verticalMinAngle, verticalMaxAngle);
        const double cosV = std::cos(vertical);
        const double sinV = std::sin(vertical);
        for (int h = 0; h < horizontalSamples; ++h) {
            const double horizontal =
                angleAt(h, horizontalSamples, horizontalMinAngle, horizontalMaxAngle);
            directions.push_back(maro::Vec3{
                cosV * std::sin(horizontal),
                sinV,
                cosV * std::cos(horizontal),
            });
        }
    }
    return directions;
}

}  // namespace maro::lidar
