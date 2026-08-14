#pragma once

#include <cassert>
#include <cstddef>
#include <mutex>
#include <string>
#include <vector>

#include <maya/MString.h>

#include "maro_diag/DiagRecord.h"

namespace maro {

// 진단의 단일 출구 (설계 스펙 §4 boad 행). 모든 info/warn/devInfo/error가
// 여기를 거친다. 인메모리 스트림을 스스로 들고 있다 -- 진단 패널(Layer B)은
// 이것과 book 파일만 읽고 자체 상태를 갖지 않는다 (스펙 §4.2).
//
// 스레드 안전성: 레코드 벡터는 뮤텍스로 보호되어 동시 push_back/조회이 벡터
// 자체를 깨뜨리지는 않는다. 하지만 info/warn/devInfo/error가 내부에서 부르는
// MGlobal::display*는 여전히 메인 스레드에서만 안전하다 -- Maya API는 워커
// 스레드 호출을 보장하지 않는다. 지금은 이 클래스를 메인 스레드 밖에서 부르는
// 곳이 없어 우연히 문제가 없을 뿐이다. 72곳의 기존 MGlobal::display* 호출을
// 이리로 옮기는 작업이 compute() 내부(워커 스레드에서 돌 수 있음, Maya 2026
// Parallel Evaluation Manager 기본값)의 자리를 건드리게 되면, 그 자리는 이
// display* 경로를 안전하게 쓸 수 없다는 뜻이므로 마이그레이션 시 반드시 별도
// 처리가 필요하다.
//
// 무한 성장: 레코드 벡터에는 상한도 축출(eviction)도 없다. 지금은 문제
// 없지만, 실제 진단들이 (재생 중 매 프레임 발동하는 것들을 포함해) 여기로
// 몰리기 시작하면 끝없이 자란다 -- 아직 대응되어 있지 않다.
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
    // indexFromEnd 0 = 가장 최근 레코드. 값으로 반환한다 -- 뮤텍스로 보호된
    // 벡터라도 내부 원소로의 참조를 락 스코프 밖으로 내보내면 다른 스레드의
    // push_back(재할당 포함)과 경합하는 매달린 참조가 될 수 있다.
    static DiagRecord recordAt(std::size_t indexFromEnd);

    // book에서 실제로 새로 분석한(캐시 미스) 횟수. "기지 에러 즉답" 검증에 쓴다.
    static std::size_t freshAnalysisCount();

    // 실패 해시에 해법을 등록한다. 이미 book에 있는 항목이면 분석은 남기고
    // 해법만 갱신한다. 아직 없는 해시면 분석 없이 해법만 있는 항목을 새로
    // 만든다 (사용자가 스스로 고친 뒤 등록하는 경우 -- 스펙 §4.3 "해법이
    // 없는 에러는 ... 사용자가 등록할 수 있게 한다").
    static void registerRemedy(const std::string& errorHash, const MString& remedyText);

    // 테스트 전용. 프로덕션 코드는 부르지 않는다.
    static void resetForTest();

private:
    static std::vector<DiagRecord>& stream();
    static std::mutex& mutex();
};

// 진행 중인 커맨드 이름의 스택. MPxCommand::doIt 진입 시 설치되고 함수가
// 반환하면 자동으로 해제된다. onfix가 "어느 커맨드가 관여했는지"를 아는
// 유일한 경로다 (설계 스펙 §4 onfix 행 "커맨드").
class ScopedCommandContext {
public:
    explicit ScopedCommandContext(const char* commandName);
    ~ScopedCommandContext();

    ScopedCommandContext(const ScopedCommandContext&) = delete;
    ScopedCommandContext& operator=(const ScopedCommandContext&) = delete;
};

namespace onfix {

// 현재 활성 커맨드 이름. 스택이 비어 있으면 빈 문자열.
std::string activeCommand();

// 에러 시점의 DG 컨텍스트를 조립한다. 노드 타입·어트리뷰트·축/대상은
// 호출부가 건넨다 -- boad/onfix는 Maya 씬을 스스로 훑지 않는다. 사건이
// 일어난 그 자리에서만 정확히 안다(감시자가 Maya 주소공간을 못 보는 것과
// 같은 이유로, 포착은 항상 발생지에서 한다는 원칙을 여기서도 지킨다).
// activeCommand는 항상 여기서 스택으로부터 채운다 -- 호출부가 직접 쓰지 않는다.
DgContext capture(const MString& nodeType, const MString& attributeName,
                   const MString& axisOrTarget);

}  // namespace onfix

}  // namespace maro

#ifndef MARO_ASSERT
// 원안(Maro_DebugUtility/boad_Maro.h)에서 이름을 그대로 가져왔다. 실패하면
// boad에 기록한다. 중단은 assert에 맡기는데, 이 프로젝트가 빌드/테스트에
// 쓰는 CMake 기본 구성인 RelWithDebInfo는 MSVC에서 NDEBUG를 정의하므로
// assert는 무연산(no-op)으로 컴파일된다 -- 즉 이 구성에서는 기록만 하고
// 중단하지 않는다.
#define MARO_ASSERT(cond, msg)                              \
    do {                                                    \
        if (!(cond)) {                                      \
            maro::BoadMaro::error("ASSERT_FAILED", (msg));  \
            assert(false && (msg));                         \
        }                                                    \
    } while (0)
#endif
