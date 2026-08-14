#pragma once

#include <cassert>
#include <cstddef>
#include <string>
#include <vector>

#include <maya/MString.h>

#include "maro_diag/DiagRecord.h"

namespace maro {

// 진단의 단일 출구 (설계 스펙 §4 boad 행). 모든 info/warn/devInfo/error가
// 여기를 거친다. 인메모리 스트림을 스스로 들고 있다 -- 진단 패널(Layer B)은
// 이것과 book 파일만 읽고 자체 상태를 갖지 않는다 (스펙 §4.2).
class BoadMaro {
public:
    static void info(const MString& message);
    static void warn(const MString& message);
    static void devInfo(const MString& message);

    // siteTag: 이 실패의 자리와 종류만 담는 불변 식별자 (maro::hashError
    // 계약, Task 1). context는 Task 4에서 onfix::capture()로 채운다 -- 지금은
    // 항상 기본값(전부 빈 문자열)이다.
    static void error(const std::string& siteTag, const MString& message,
                       const DgContext& context = DgContext{});

    static std::size_t recordCount();
    // indexFromEnd 0 = 가장 최근 레코드.
    static const DiagRecord& recordAt(std::size_t indexFromEnd);

    // 테스트 전용. 프로덕션 코드는 부르지 않는다.
    static void resetForTest();

private:
    static std::vector<DiagRecord>& stream();
};

}  // namespace maro

#ifndef MARO_ASSERT
// 원안(Maro_DebugUtility/boad_Maro.h)에서 이름을 그대로 가져왔다. 실패하면
// boad에 기록하고 assert로 중단한다.
#define MARO_ASSERT(cond, msg)                              \
    do {                                                    \
        if (!(cond)) {                                      \
            maro::BoadMaro::error("ASSERT_FAILED", (msg));  \
            assert(false && (msg));                         \
        }                                                    \
    } while (0)
#endif
