#pragma once

#include <cstdint>
#include <vector>

#include "maro_transform/Types.h"

namespace maro::lidar {

// sensor_msgs/msg/PointCloud2의 실제 바이너리 레이아웃(point_step/data)만
// 만든다 -- 메시지 타입 자체(rclcpp/sensor_msgs 헤더)는 모른다. 호출부가
// 이 바이트를 실제 PointCloud2 메시지의 data 필드에 그대로 복사하고,
// fields/point_step/row_step/height/width/is_bigendian/is_dense를 이
// 구조체 값으로 채운다.
struct PackedPointCloud {
    std::vector<std::uint8_t> data;
    std::uint32_t pointStep = 0;
    std::uint32_t width = 0;
};

// points는 이미 ROS 좌표계(Z-up)로 변환된 값이어야 한다 -- 이 함수는
// 좌표 변환을 하지 않는다. 필드 레이아웃: x(offset 0)/y(4)/z(8)/
// intensity(12), 전부 float32, point_step=16.
// intensities가 points보다 짧으면 남는 자리는 0.0f로 채운다.
PackedPointCloud packPointCloud(const std::vector<maro::Vec3>& points,
                                 const std::vector<float>& intensities);

}  // namespace maro::lidar
