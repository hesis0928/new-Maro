#pragma once

#include <cstddef>
#include <vector>

#include "maro_diag/BookStore.h"
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

// 선택된 레코드 하나의 상세를 만든다.
//
// bookEntry는 **지금** book에서 읽어 온 항목이며 없으면 nullptr다. 레코드가
// 이미 priorAnalysis를 싣고 있는데도 다시 읽는 이유는 I/O를 아끼려는 것이
// 아니라, 레코드가 남은 뒤에 사용자가 등록한 해법을 반영하기 위해서다
// (설계 스펙 §3.4).
//
// targetNodeExists는 호출부가 메인 스레드에서 미리 확인해 건네준다 --
// 프레젠터는 살아있는 씬을 조회하지 않는다 (설계 스펙 §3.3). B-1a에서는
// 적용 버튼이 없으므로 쓰이지 않지만, B-1b가 이 자리에서 판단하도록
// 시그니처를 지금 고정한다.
PanelDetail buildPanelDetail(const DiagRecord& record,
                              const BookEntry* bookEntry,
                              bool targetNodeExists);

}  // namespace maro
