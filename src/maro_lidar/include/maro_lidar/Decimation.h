#pragma once

#include <cstddef>
#include <vector>

#include "maro_transform/Types.h"

namespace maro::lidar {

// points가 maxPoints 이하면 그대로 복사해 돌려준다. 넘으면 전체 범위를
// 고르게 커버하는 스트라이드 샘플링으로 정확히 maxPoints개(또는 그
// 이하)로 줄인다. 순서는 보존한다(연속된 스캔 라인이 끊기지 않도록).
std::vector<maro::Vec3> decimateForPreview(const std::vector<maro::Vec3>& points,
                                            std::size_t maxPoints);

}  // namespace maro::lidar
