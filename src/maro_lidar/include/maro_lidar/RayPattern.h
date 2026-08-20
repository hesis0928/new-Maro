#pragma once

#include <vector>

#include "maro_transform/Types.h"

namespace maro::lidar {

// 채널(수직)/해상도(수평) 스펙으로부터 LiDAR 노드의 로컬(오브젝트) 공간
// 기준 단위 방향 벡터 목록을 계산한다. 월드 변환은 호출부 책임이다.
//
// 로컬 프레임: +Z가 수평각=0/수직각=0일 때의 정면, +Y가 위(Maya 월드 업
// 축과 같은 관례), 수평각은 +Z에서 +X 쪽으로 로컬 Y축을 중심으로 돈다.
// 각도 간격은 sensor_msgs/msg/LaserScan.msg의 실제 angle_increment 관례
// ((max-min)/(샘플수-1), 양 끝값 포함)을 그대로 따른다.
//
// 반환 순서: 바깥쪽이 수직 채널, 안쪽이 수평 샘플(채널0의 수평 전체,
// 채널1의 수평 전체, ...). 채널 인덱스가 나중에 PointCloud2의 ring
// 필드로 쓰일 수 있어(범위 밖, §후속) 이 순서를 명시해 둔다.
std::vector<maro::Vec3> computeRayDirections(int verticalSamples, double verticalMinAngle,
                                              double verticalMaxAngle, int horizontalSamples,
                                              double horizontalMinAngle, double horizontalMaxAngle);

}  // namespace maro::lidar
