#pragma once

#include <cassert>
#include <cstddef>
#include <filesystem>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

#include <maya/MString.h>

#include "maro_diag/BookStore.h"
#include "maro_diag/DiagRecord.h"
#include "maro_diag/JournalReader.h"
#include "maro_diag/RemedyAction.h"

namespace maro {

// Maya 메인 스레드를 기억해 둔다. initializePlugin()에서 딱 한 번 부른다 --
// 그 함수는 정의상 메인 스레드에서 돈다.
//
// 왜 스레드 id를 직접 붙잡는가: Maya 2026 devkit 헤더에는 "지금이 메인
// 스레드인가"를 묻는 공식 술어가 없다. MGlobal.h, MThreadUtils.h, MSpinLock.h,
// MThreadAsync.h, MThreadPool.h, MAtomic.h를 전부 확인했고 isMainThread()류의
// API는 존재하지 않는다 (있는 것은 executeCommandOnIdle/executeTaskOnIdle처럼
// "메인 스레드로 넘기는" 수단뿐이다). 공식 수단이 없으므로 표준 라이브러리로
// 판정한다.
//
// 이 함수는 book 경로 확인도 함께 미리 끝내 둔다. 그 지연 초기화는 내부에서
// MEL `internalVar -userAppDir`를 한 번 실행하는데(MaroDiag.cpp의 bookPaths()
// 참고), 첫 error()가 워커 스레드에서 터지면 그 MEL 실행도 워커에서 일어난다
// -- display*만 막고 이쪽을 열어 두면 가드가 반쪽짜리가 된다.
void markMainThread();

// markMainThread()가 아직 불리지 않았다면 true를 돌려준다. 즉 "모른다"는
// 지금까지와 똑같이(=가드 이전 동작) 취급한다 -- 등록 전에 진단이 나가는
// 경로는 플러그인 안에 없지만, 판정 불능이 조용한 침묵으로 바뀌지 않게 한다.
bool isMainThread();

// 진단의 단일 출구 (설계 스펙 §4 boad 행). 모든 info/warn/devInfo/error가
// 여기를 거친다. 인메모리 스트림을 스스로 들고 있다 -- 진단 패널(Layer B)은
// 이것과 book 파일만 읽고 자체 상태를 갖지 않는다 (스펙 §4.2).
//
// 스레드 안전성: 레코드 벡터는 뮤텍스로 보호되어 동시 push_back/조회이 벡터
// 자체를 깨뜨리지는 않는다. 그리고 Task 7이 compute() 안의 진단들(MaroAxisNode
// 하나 + 능력 노드 넷 + MaroCommandDeviceNode)을 이리로 옮기면서, Maya 2026의
// 기본값인 Parallel Evaluation Manager가 compute()를 워커 스레드에서 돌릴 수
// 있다는 사실이 실제로 이 경로에 닿았다 -- MGlobal::display*는 메인
// 스레드에서만 안전하므로 그대로 두면 안 되는 상태였다.
//
// 그래서 info/warn/devInfo/error는 전부 메인 스레드 가드를 거친다:
//   - 레코드는 언제나 남긴다 (뮤텍스로 보호된 인메모리 스트림). 진단
//     패널(Layer B)이 읽는 것은 이 스트림이므로 사용자가 볼 내용은 하나도
//     사라지지 않는다.
//   - MGlobal::display* 호출(스크립트 에디터 즉시 에코)만 메인 스레드가
//     아닐 때 건너뛴다. 워커에서는 애초에 안전하지 않았던 유일한 부분이다.
// 이 가드는 72곳이 아니라 여기 한 곳에만 있다 -- boad가 진단의 단일 출구이기
// 때문에 가능한 배치다.
//
// 메인 스레드 판정은 아래 markMainThread()/isMainThread()가 한다.
//
// 무한 성장: 레코드 벡터에는 상한도 축출(eviction)도 없다. 지금은 문제
// 없지만, 실제 진단들이 (재생 중 매 프레임 발동하는 것들을 포함해) 여기로
// 몰리기 시작하면 끝없이 자란다 -- 아직 대응되어 있지 않다.
//
// 락 두 개, 각자 다른 것을 지킨다 (Finding I4):
//   - mutex()(레코드 뮤텍스): stream()(인메모리 진단 벡터)만 보호한다. 이미
//     엄격한 규율이 있다 -- MGlobal::display* 호출 동안 절대 쥐고 있지
//     않고, devInfo()/warn()이 스스로 이 락을 잡으므로 그 함수들을 부를 때도
//     쥐고 있지 않는다(재진입 불가능한 std::mutex이므로 안 지키면 교착).
//   - bookMutex()(book 뮤텍스): book(스필/정본) 파일 I/O와 그것을 거울처럼
//     비추는 세션 캐시(bookCache())를 함께 보호한다. Task 7 이후
//     compute()들이 워커 스레드에서 동시에 boad로 들어올 수 있으므로, 두
//     스레드가 같은 스필 파일에 동시에 append하는 경합(체크-후-쓰기 TOCTOU,
//     그리고 스트림 삽입 두 번은 원자적이지 않음)을 이 락으로 직렬화한다.
//     book 작업 중에는 절대 레코드 뮤텍스를 재진입하지 않고(별개 뮤텍스라
//     교착 위험은 없지만, 두 락이 섞이면 향후 유지보수가 헷갈리므로 book
//     뮤텍스는 항상 disk/cache 작업이 끝나면 놓은 뒤에야 warn()/devInfo()를
//     부른다 -- error()의 기존 "warn()은 락 밖에서" 규율과 같은 이유).
// 이 두 뮤텍스를 동시에 쥐는 코드 경로는 없다 -- 락 순서 역전에 의한 교착이
// 애초에 성립하지 않는다.
class BoadMaro {
public:
    static void info(const MString& message);
    static void warn(const MString& message);
    static void devInfo(const MString& message);

    // siteTag: 이 실패의 자리와 종류만 담는 불변 식별자 (maro::hashError
    // 계약, Task 1). context는 Task 4에서 onfix::capture()로 채운다 -- 지금은
    // 항상 기본값(전부 빈 문자열)이다.
    //
    // remedyAction: 이 발생에 대한 구조화된 해법. book에서 오지 않는다 --
    // 호출부가 이 순간 살아있는 씬을 보고 직접 채운다 (RemedyAction.h,
    // 플랜 서두 "spec에서 의도적으로 벗어난 지점" 참고). 기본값
    // RemedyActionKind::None은 "해법 없음"이며 기존 호출부 전부가 이
    // 기본값을 그대로 탄다.
    static void error(const std::string& siteTag, const MString& message,
                       const DgContext& context = DgContext{},
                       const RemedyAction& remedyAction = RemedyAction{});

    static std::size_t recordCount();
    // indexFromEnd 0 = 가장 최근 레코드. 값으로 반환한다 -- 뮤텍스로 보호된
    // 벡터라도 내부 원소로의 참조를 락 스코프 밖으로 내보내면 다른 스레드의
    // push_back(재할당 포함)과 경합하는 매달린 참조가 될 수 있다.
    static DiagRecord recordAt(std::size_t indexFromEnd);

    // 스트림 전체를 락 한 번으로 복사한다 (리뷰 Finding: snapshot()이 스냅샷이
    // 아니었다). recordCount()로 개수를 얻고 recordAt()을 그 개수만큼 반복
    // 호출하는 루프는 매 호출이 독립적으로 락을 잡았다 놓으므로 스냅샷이
    // 아니다 -- 루프 도중 다른 스레드가 push_back하면(Maya 2026 Parallel
    // Evaluation Manager 아래 워커의 error()/warn()/info()가 그럴 수 있다)
    // recordAt(indexFromEnd)은 루프 시작 시점에 캡처해 둔 count가 아니라
    // *지금 이 순간의* stream().size()를 기준으로 인덱스를 계산하므로, 그
    // 시점 이후의 모든 반복이 한 칸씩 밀린 자리를 읽는다 -- 레코드 하나를
    // 조용히 건너뛰거나 다른 레코드를 두 번 읽는다. 스트림이 줄어들지 않으니
    // 예외나 크래시로는 드러나지 않고, 그 갱신 한 번의 패널 출력만 조용히
    // 어긋난 채 다음 갱신에서 저절로 맞아떨어진다.
    //
    // 이 메서드는 그 경합이 성립할 자리가 없다: 락을 쥔 채로 벡터 전체를
    // 한 번에 복사하므로 다른 스레드가 끼어들 틈이 없다. 반환값은 스트림에
    // 저장된 순서 그대로(오래된 것부터, sequence 오름차순)다 -- 순번 배정이
    // 이미 push_back과 같은 락 스코프 안에서 일어나므로(assignSequenceAndPush,
    // MaroDiag.cpp) 삽입 순서와 순번 순서는 언제나 같다. 호출부가 뒤집을
    // 필요가 없다.
    static std::vector<DiagRecord> snapshotRecords();

    // book에서 실제로 새로 분석한(캐시 미스) 횟수. "기지 에러 즉답" 검증에 쓴다.
    static std::size_t freshAnalysisCount();

    // 실패 해시에 해법을 등록한다. 이미 book에 있는 항목이면 분석은 남기고
    // 해법만 갱신한다. 아직 없는 해시면 분석 없이 해법만 있는 항목을 새로
    // 만든다 (사용자가 스스로 고친 뒤 등록하는 경우 -- 스펙 §4.3 "해법이
    // 없는 에러는 ... 사용자가 등록할 수 있게 한다").
    static void registerRemedy(const std::string& errorHash, const MString& remedyText);

    // 해시로 book 항목을 찾는다. 있으면 true. 패널이 상세를 열 때 쓴다 --
    // 레코드가 남은 뒤에 등록된 해법을 반영하려면 지금 다시 봐야 한다.
    // book을 못 읽어도 예외를 던지지 않고 false를 돌려준다: 진단 경로는
    // 지식 저장소에 닿지 못해서 실패하지 않는다.
    static bool lookupBook(const std::string& errorHash, BookEntry& out);

    // 저널을 연다. 플러그인 로드 시 한 번 부르며, 그 전에 오래된 세션을
    // 회전으로 정리하고 지난 세션들의 크래시 인접 집계를 읽어 둔다.
    // 열지 못해도 던지지 않는다 -- 보존이 안 될 뿐 진단은 그대로 돈다.
    //
    // 리뷰 Finding C1(리브니스): 그 집계는 지금 동시에 살아 있는 다른
    // Maya/mayapy 인스턴스의 저널을 크래시로 세지 않는다 -- 그 파일들도
    // 아직 close 줄이 없지만 그건 아직 도는 중이라는 뜻이기 때문이다.
    // 판정은 파일 이름의 pid가 살아 있는지를 OS에 직접 묻는다(MaroDiag.cpp의
    // isProcessRunning; 집계 로직 자체는 maro_diag 안에 있고 이 판정만
    // seam으로 주입된다).
    static void openJournal();
    // 정상 종료 줄을 쓰고 닫는다. uninitializePlugin에서만 부른다.
    // 이 줄이 없이 끝난 세션이 곧 비정상 종료다.
    static void closeJournal();

    // 로드 시점에 읽어 둔 지난 세션들의 관측. 인과가 아니라 상관이다.
    //
    // 뮤텍스로 지키지 않는다 -- 이래도 안전한 이유: 이 값은
    // initializePlugin() 중 openJournal()이 메인 스레드에서 쓰고 그 뒤로는
    // (resetForTest() 밖에서는) 다시 쓰이지 않는다. 이 값을 읽는 쪽은 전부
    // MPxCommand::doIt(MaroDiagCommands.cpp의 디버그 커맨드,
    // MaroPanelCommands.cpp의 패널 상세 커맨드)이며, Maya는 doIt을 메인
    // 스레드에서만 부른다. 즉 쓰기와 읽기가 겹칠 스레드 경합이 애초에
    // 존재하지 않는다.
    //
    // 두 번째 쓰기: resetForTest()도 이 값을 기본값으로 되돌린다(테스트
    // 전용 훅이 boad 세션 상태를 전부 되돌려야 하므로 -- resetForTest()
    // 주석 참고). 그래도 위의 안전 논거는 그대로 성립한다: resetForTest()
    // 역시 언제나 메인 스레드에서, 테스트 셋업/해체 코드가 다른 doIt 호출과
    // 절대 겹치지 않게 순차적으로만 부른다 -- "쓰기가 정확히 한 번"이라는
    // 문장은 더 이상 참이 아니지만 "쓰기와 읽기가 동시에 겹치지 않는다"는
    // 실제 불변식은 그대로다.
    //
    // 이 불변식이 깨지는 경우: (1) 위 두 곳(openJournal(), resetForTest())
    // 이외에 이 저장소를 다시 쓰는 코드가 생기되 그 호출이 doIt/테스트
    // 셋업과 겹칠 수 있게 되거나, (2) doIt이 아닌 경로(예: compute()류
    // 워커 스레드)에서 crashAdjacency()를 부르게 되는 경우 -- 그때는
    // journalMutex()처럼 전용 뮤텍스가 필요해진다.
    static const CrashAdjacency& crashAdjacency();

    // 테스트 전용. 프로덕션 코드는 부르지 않는다. boad 세션 상태(레코드
    // 스트림, 신규분석 카운터, book-불가 경고 래치, book 캐시, 저널
    // writer, crashAdjacency 저장소) 전부를 초기 상태로 되돌린다 -- 콜러가
    // 없다고 절반만 리셋되는 상태로 방치하면 "테스트 전용 리셋 훅"이라는
    // 이름이 거짓말이 된다 (carried-forward Minor finding -- 이 배치가
    // 저널 writer/crashAdjacency 저장소를 새로 더했는데도 여기 반영하지
    // 않았다면 정확히 같은 함정이 재발했을 것이다).
    // 이 세션이 book/저널에 쓰는 디렉터리. journalDirectory()(MaroDiag.cpp)의
    // 이미 해소된 결과를 그대로 돌려준다 -- MARO_DIAG_BOOK_DIR 환경변수
    // 해석이든 internalVar -userAppDir 해석이든 여기서 다시 하지 않는다.
    // 감시자를 spawn할 때 같은 디렉터리를 넘겨야 하는 MaroSentinelClient.cpp를
    // 위해 존재한다. 실패할 수 없다 -- markMainThread()가 이미 지연
    // 초기화를 끝내 둔 값을 읽을 뿐이다.
    static std::filesystem::path bookDirectory();

    static void resetForTest();

    // sequence로 레코드 하나를 찾는다. 순번은 세션 전역에서 유일하고
    // 재사용되지 않으므로(MaroPanelCommands.cpp가 이미 이 방식으로
    // -sequence를 구현했다), 화면이 그려진 시점과 지금(적용 클릭 시점)
    // 사이에 다른 진단이 더 들어와도 항상 사용자가 실제로 고른 그 레코드를
    // 돌려준다. 찾지 못하면 false -- 존재한 적 없는 순번이나 세션이 리셋된
    // 뒤의 스테일 값을 엉뚱한 이웃으로 대체하지 않는다.
    static bool findRecordBySequence(std::uint64_t sequence, DiagRecord& out);

private:
    static std::vector<DiagRecord>& stream();
    static std::mutex& mutex();

    // 리뷰 Finding I1: info/warn/devInfo/error 네 진입점이 공유하는 마지막
    // 동작 -- 순번 배정 + 스트림 삽입 + 저널 기록 -- 을 한 곳에 모은다.
    // 이 함수는 절대 던지지 않는다(내부에서 전부 삼킨다): 호출자는 정확히
    // "여기서 새면 Maya가 죽는다"는 catch(...) 블록들(MaroDeleteWatcher.cpp,
    // MaroAxisNode.cpp)이거나 uninitializePlugin의 마지막 info() 호출이다.
    static void pushAndJournal(DiagRecord&& rec);

    // book 뮤텍스와 그것이 지키는 세션 캐시. 캐시는 "이 세션에서 이미 book에
    // 있다고 확인된 해시 -> 항목"만 담는다(Finding M3). 아직 book에 없는
    // (미스인) 해시는 캐시하지 않는다 -- 그래야 book이 쓰기 불가능한 동안의
    // 반복 실패가 매번 "새 분석"으로 정직하게 집계된다
    // (test_diag_degraded.py). registerRemedy()는 항목을 갱신할 때마다 해당
    // 해시를 캐시에서 지운다(무효화) -- 안 그러면 세션 중간에 등록한 해법을
    // 이미 캐시된 옛 항목이 계속 가려 버린다.
    static std::mutex& bookMutex();
    static std::unordered_map<std::string, BookEntry>& bookCache();
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
//
// siteTag를 반드시 받는다 (carried-forward Minor finding). 원래는
// "ASSERT_FAILED" 하나로 모든 호출 지점을 뭉갰는데, 사이트 태그는 해시
// 입력이므로(ErrorHash.h 계약) 그러면 미래의 assert 호출 지점 전부가 book
// 항목 하나를 공유해, 가장 먼저 실패한 지점의 분석/해법이 나머지 전부에
// 잘못 서빙된다 -- test_diag_onfix.py가 서로 다른 실패는 서로 다른 해시를
// 가져야 한다고 못박은 바로 그 문제다. 이 매크로는 지금 호출 지점이 0곳이라
// (grep 확인됨) 시그니처를 바꿔도 기존 코드에 영향이 없다.
#define MARO_ASSERT(siteTag, cond, msg)                      \
    do {                                                     \
        if (!(cond)) {                                       \
            maro::BoadMaro::error((siteTag), (msg));         \
            assert(false && (msg));                          \
        }                                                     \
    } while (0)
#endif
