#pragma once

#include <cstddef>
#include <vector>

#include "maro_diag/DiagRecord.h"
#include "maro_diag/PanelView.h"

namespace maro {

// 레코드 스냅샷을 화면에 나갈 행 목록으로 바꾼다. Maya를 조회하지 않고
// book도 보지 않는다 -- DiagRecord가 servedFromBook을 발생 시점에 이미
// 담고 있으므로 기지 여부는 레코드 자체에서 나온다 (설계 스펙 §3.4).
//
// 순서: 필터 -> 태그별 접기 -> 상한. 이 순서를 뒤집어 먼저 자르면 연쇄의
// 시작 -- 진단에서 가장 중요한 한 줄 -- 이 뒤따라온 수백 개의 반복에 밀려
// 사라진다 (설계 스펙 §5).
//
// hiddenByFilter/hiddenByCap은 따로 돌려준다. 필터로 빠진 것과 상한으로
// 잘린 것은 사용자에게 다른 사건이기 때문이다.
std::vector<PanelRow> buildPanelRows(const std::vector<DiagRecord>& stream,
                                      PanelSeverityFilter filter,
                                      std::size_t maxRows,
                                      std::size_t& hiddenByFilter,
                                      std::size_t& hiddenByCap);

}  // namespace maro
