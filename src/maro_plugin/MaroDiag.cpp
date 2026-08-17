#include "MaroDiag.h"

#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <thread>
#include <utility>

#include <maya/MGlobal.h>

#include "maro_diag/BookStore.h"
#include "maro_diag/ErrorHash.h"

namespace maro {

namespace {

std::atomic<std::size_t> g_freshAnalysisCount{0};

// 레코드 순번. 0은 "안 채워짐"을 뜻하므로 첫 레코드가 1을 받도록 pre-increment
// 한다. 레코드 뮤텍스와 무관하게 워커 스레드에서도 불리므로 atomic이다.
std::atomic<std::uint64_t> g_nextSequence{0};

std::uint64_t nowMs() {
    using namespace std::chrono;
    return static_cast<std::uint64_t>(
        duration_cast<milliseconds>(system_clock::now().time_since_epoch()).count());
}

// 리뷰 Finding 1(2절): 시각만 찍는다. 이 값은 "언제 일어났는가"라는 질문에
// 답할 뿐, "스트림의 어느 자리에 놓이는가"라는 질문과는 무관하다 -- 그래서
// 락을 잡기 한참 전, 함수 진입 직후에 찍어도 안전하다. 순번은 더 이상 여기서
// 찍지 않는다: assignSequenceAndPush() 참고.
void stampTimestamp(DiagRecord& rec) {
    rec.timestampMs = nowMs();
}

// 리뷰 Finding 1(2절): 순번 배정과 스트림 삽입을 같은 락 스코프 안에서,
// 항상 이 순서로 한다. error()는 스탬프와 push_back 사이에 해시/book I/O라는
// 상당한 작업이 끼어 있고, Maya 2026 Parallel Evaluation Manager 아래에서는
// error()가 워커 스레드에서도 불릴 수 있다 -- 그래서 두 번의 error() 호출이
// 순번을 1, 2로 받고도 스트림에는 반대 순서로 들어갈 수 있었다(경합).
// recordAt(0)이 "가장 최근"을 뜻한다는 계약과 패널이 스트림을 위치 순서대로
// 훑으며 그것이 곧 순번 순서라고 가정하는 것, 둘 다 "삽입 위치 순서 ==
// 순번 순서"를 전제하므로, 순번은 반드시 실제로 삽입되는 바로 그 순간(=이
// 락을 쥔 채로) 배정해야 그 전제가 구조적으로 항상 참이 된다. std::atomic은
// 그대로 유지한다 -- 이 락이 어느 경로에서 쥐어지는지와 무관하게 카운터
// 자체의 원자성은 공짜이고, 그 논거에 기대지 않는다.
void assignSequenceAndPush(DiagRecord&& rec, std::vector<DiagRecord>& s) {
    rec.sequence = ++g_nextSequence;
    s.push_back(std::move(rec));
}

// book(스필)에 한 번도 쓸 수 없게 되면 이 세션 동안 한 번만 알린다. devInfo는
// _DEBUG 밖(우리가 빌드/테스트하는 RelWithDebInfo 포함)에서 무연산으로
// 컴파일되므로, 지식 저장소가 조용히 멈춘 상태를 devInfo만으로는 아무도 볼 수
// 없다 (Task 4, Task 5가 남긴 지적). 매 실패마다 경고하면 반복 실패 시
// 스팸이 되므로 래치로 한 번만 warn()을 통해 내보낸다.
std::atomic<bool> g_bookUnwritableWarned{false};

struct BookPaths {
    std::filesystem::path canonical;
    std::filesystem::path spill;
};

// 기본은 원안(Maro_DebugUtility/book_Maro.cpp)과 같은 위치다:
// internalVar -userAppDir. MARO_DIAG_BOOK_DIR이 설정돼 있으면 그것을
// 우선한다 -- 테스트가 매 실행마다 깨끗한 book으로 시작하기 위한 재정의다.
const BookPaths& bookPaths() {
    static const BookPaths paths = [] {
        BookPaths p;
        std::filesystem::path dir;
        if (const char* override_ = std::getenv("MARO_DIAG_BOOK_DIR")) {
            dir = override_;
        } else {
            const MString userAppDir =
                MGlobal::executeCommandStringResult("internalVar -userAppDir");
            if (userAppDir.length() > 0) {
                dir = std::filesystem::path(userAppDir.asChar());
            } else {
                dir = std::filesystem::temp_directory_path();
                // 리뷰 Finding 2: 이 폴백은 이 세션 내내 영구히, 조용히
                // 쓰인다 -- 알리지 않으면 사용자의 지식 저장소가 세션 동안
                // 통째로 보이지 않는데 아무도 그 이유를 모른다. 여기는
                // markMainThread()의 첫 호출(정의상 메인 스레드)이거나
                // 그 뒤의 첫 error()/registerRemedy() 호출이므로, 이 시점엔
                // g_mainThreadKnown이 이미 true다 -- warn()의 화면 에코
                // 가드가 이 경고를 삼키지 않는다.
                BoadMaro::warn(
                    MString("Maro: could not resolve the user app directory "
                            "(internalVar -userAppDir returned empty); using "
                            "the temp directory for the knowledge store "
                            "instead: ") +
                    MString(dir.string().c_str()));
            }
        }
        p.canonical = dir / "maro_knowledge.jsonl";
        p.spill = dir / "maro_knowledge.spill.jsonl";
        return p;
    }();
    return paths;
}

// book(스필)에 쓰기가 실패했을 때 한 번만 warn()으로 알린다. warn()은 자체
// 뮤텍스를 잠그므로, 이 함수는 error()가 자신의 lock_guard를 잡기 *전에만*
// 불러야 한다 -- 그러지 않으면 std::mutex는 재진입 불가이므로 교착 상태에
// 빠진다. boad(BoadMaro::warn)가 진단의 단일 출구라는 설계 불변식을 지키기
// 위해 MGlobal::displayWarning을 직접 부르지 않는다.
void warnBookUnwritableOnce(const std::filesystem::path& spillPath) {
    if (g_bookUnwritableWarned.exchange(true)) return;
    BoadMaro::warn(MString("Maro: 지식 저장소(book)에 쓸 수 없습니다 -- ") +
                   MString(spillPath.string().c_str()) +
                   MString(" -- 이 세션의 진단은 앞으로 book에 저장되지 않습니다. "
                           "디렉터리 권한/경로를 확인하세요."));
}

// 메인 스레드 id. markMainThread()가 한 번 쓰고(메인 스레드), 그 뒤로는
// 아무도 쓰지 않는다. g_mainThreadKnown의 release/acquire 쌍이 이 쓰기를
// 나중에 생기는 워커 스레드들의 읽기보다 앞서게 만든다 -- 워커는 언제나
// markMainThread() 이후에 생기므로 데이터 경합이 없다.
std::thread::id g_mainThreadId;
std::atomic<bool> g_mainThreadKnown{false};

}  // namespace

void markMainThread() {
    g_mainThreadId = std::this_thread::get_id();
    g_mainThreadKnown.store(true, std::memory_order_release);

    // book 경로(정적 지연 초기화)를 여기서 미리 확정한다. bookPaths()는 MEL
    // `internalVar -userAppDir`를 실행할 수 있는데, 그것도 메인 스레드 전용
    // API다 -- 첫 error()가 워커 스레드(compute())에서 터질 때 이 초기화가
    // 거기서 처음 돌면 display*만 막은 가드가 무의미해진다. 경로 계산일
    // 뿐이라 파일은 하나도 건드리지 않는다.
    (void)bookPaths();
}

bool isMainThread() {
    if (!g_mainThreadKnown.load(std::memory_order_acquire)) return true;
    return std::this_thread::get_id() == g_mainThreadId;
}

std::vector<DiagRecord>& BoadMaro::stream() {
    static std::vector<DiagRecord> s_stream;
    return s_stream;
}

std::mutex& BoadMaro::mutex() {
    static std::mutex s_mutex;
    return s_mutex;
}

// Finding I4: book(스필) 파일 I/O와 그것을 거울처럼 비추는 세션 캐시를
// 함께 지키는 전용 뮤텍스. 레코드 뮤텍스(mutex())와는 별개다 -- 그 뮤텍스는
// "MGlobal::display* 동안 쥐지 않는다/devInfo·warn을 부를 때 쥐지 않는다"는
// 엄격한 규율이 이미 있고, book 작업(파일 열기, JSON 파싱, append)은 그
// 규율과 무관한 별개의 관심사라 같은 락에 얹으면 두 규율이 뒤섞인다.
std::mutex& BoadMaro::bookMutex() {
    static std::mutex s_bookMutex;
    return s_bookMutex;
}

// Finding M3: "이 세션에서 book에 있다고 이미 확인된 해시"만 담는다. 캐시에
// 없다고 해서 book에 없다는 뜻은 아니다 -- 그냥 이 세션이 아직 확인 안 했다는
// 뜻이다. 아직 book에 없는(미스인) 해시는 절대 여기 담기지 않는다: 그래야
// book이 쓰기 불가능한 동안의 반복 실패가 매번 정직하게 "새 분석"으로
// 집계된다(test_diag_degraded.py). bookMutex()로 보호된다.
std::unordered_map<std::string, BookEntry>& BoadMaro::bookCache() {
    static std::unordered_map<std::string, BookEntry> s_bookCache;
    return s_bookCache;
}

void BoadMaro::info(const MString& message) {
    DiagRecord rec;
    stampTimestamp(rec);
    rec.severity = DiagSeverity::Info;
    rec.message = message.asChar();
    // 워커 스레드에서는 화면 에코를 건너뛴다 -- 레코드는 그대로 남는다
    // (MaroDiag.h의 스레드 안전성 주석 참고).
    if (isMainThread()) {
        MGlobal::displayInfo(MString("[Maro-Info] ") + message);
    }
    std::lock_guard<std::mutex> lock(mutex());
    assignSequenceAndPush(std::move(rec), stream());
}

void BoadMaro::warn(const MString& message) {
    DiagRecord rec;
    stampTimestamp(rec);
    rec.severity = DiagSeverity::Warn;
    rec.message = message.asChar();
    if (isMainThread()) {
        MGlobal::displayWarning(MString("[Maro-Warn] ") + message);
    }
    std::lock_guard<std::mutex> lock(mutex());
    assignSequenceAndPush(std::move(rec), stream());
}

void BoadMaro::devInfo(const MString& message) {
#ifdef _DEBUG
    DiagRecord rec;
    stampTimestamp(rec);
    rec.severity = DiagSeverity::DevInfo;
    rec.message = message.asChar();
    if (isMainThread()) {
        MGlobal::displayInfo(MString("[Maro-Dev] ") + message);
    }
    std::lock_guard<std::mutex> lock(mutex());
    assignSequenceAndPush(std::move(rec), stream());
#else
    (void)message;
#endif
}

void BoadMaro::error(const std::string& siteTag, const MString& message,
                      const DgContext& context) {
    DiagRecord rec;
    stampTimestamp(rec);
    rec.severity = DiagSeverity::Error;
    rec.context = context;

    // 리뷰 Finding 1: activeCommand는 여기서 항상 채운다. capture()를 거친
    // context는 이미 채워져 있으니 손대지 않는다 -- 이 조건은 호출부가
    // 컨텍스트를 통째로 생략했거나(기본 인자 DgContext{}) capture() 없이
    // 만든 경우에만 걸린다. 그런 호출부는 지금 doIt/redoIt/undoIt의 catch
    // 블록과 postConstructor의 두 catch가 전부다 -- 그 자리들은 살아있는
    // ScopedCommandContext 마커 안에서 도는데도 마커 값이 기록에 닿지
    // 못했다(2절 Finding 1). call site마다 인자를 추가하는 대신 여기 한
    // 곳에서 채워서, 다음에 생기는 catch 블록도 똑같은 함정에 빠지지 않게
    // 한다.
    if (rec.context.activeCommand.empty()) {
        rec.context.activeCommand = onfix::activeCommand();
    }

    // appendToSpill이 false를 돌려주면(book 디렉터리를 쓸 수 없는 등) true가
    // 된다. try/catch 밖, 아직 이 함수가 자신의 lock_guard를 잡기 전에
    // warnBookUnwritableOnce()를 부르기 위해 밖에 선언해 둔다.
    bool bookUnwritable = false;

    try {
        const std::string hash = hashError(siteTag);
        rec.errorHash = hash;

        // Finding I4/M3: book 파일(정본+스필) I/O와 그것을 거울처럼 비추는
        // 세션 캐시를 하나의 book 뮤텍스로 직렬화한다. Task 7 이후
        // compute() 여럿이 워커 스레드에서 동시에 여기 도달할 수 있다
        // (MaroDiag.h 클래스 주석 참고) -- 이 락 없이는 appendToSpill의
        // "마지막 바이트 확인 후 개행 삽입" TOCTOU와 스트림 삽입 두 번
        // (ofs << dump() << '\n')이 서로 다른 스레드 사이에서 겹쳐 book
        // 파일이 깨질 수 있었다. 이 lock_guard는 try 블록 스코프에 묶여
        // 있으므로, 정상 종료든 아래에서 예외가 새 스택이 되감기든 catch
        // 절이 도는 시점에는 이미 풀려 있다 -- catch 블록의 devInfo()가
        // (레코드 뮤텍스를 스스로 잡으므로) book 뮤텍스와 얽힐 일이 없다.
        std::lock_guard<std::mutex> bookLock(bookMutex());

        // 캐시 먼저 본다 -- 있으면 파일을 전혀 건드리지 않는다 (Finding M3:
        // 매 틱 같은 실패를 내는 compute()/onTimer가 매번 병합 읽기 +
        // 스필 append를 하는 것을 막는다). 캐시에 없다고 해서 book에 없다는
        // 뜻은 아니다(다른 프로세스/이 프로세스의 과거 세션이 이미 썼을 수
        // 있다) -- 그래서 캐시 미스는 항상 디스크를 확인한다. 아직 book에
        // 없는(미스인) 해시는 절대 캐시에 담기지 않는다: 그래야 book이 쓰기
        // 불가능한 동안의 반복 실패가 매번 정직하게 "새 분석"으로 집계된다
        // (test_diag_degraded.py) -- 캐시는 파일 I/O만 건너뛸 뿐 회계까지
        // 건너뛰면 안 된다.
        //
        // 알려진 한계 (히트 방향): 한 번 담긴 해시는 이 세션 동안 다시
        // 디스크를 보지 않는다. 이 프로세스가 등록한 해법은 registerRemedy()가
        // 해당 항목을 erase하므로 즉시 반영되지만, *다른* 주체가 공유
        // 파일에 쓴 것은 세션이 끝날 때까지 안 보인다. Layer C의 감시자가
        // 정본 파일에 분석을 써 넣는 것이 바로 그 경우다 -- 두 파일 구조가
        // 존재하는 이유 자체가 그것이므로, 감시자를 붙일 때 이 캐시의
        // 무효화 경로부터 다시 봐야 한다(파일 mtime 확인이든, 감시자가
        // 쓴 뒤 알려 주는 경로든).
        const auto cacheIt = bookCache().find(hash);
        if (cacheIt != bookCache().end()) {
            const BookEntry& entry = cacheIt->second;
            rec.message = message.asChar();
            rec.priorAnalysis = entry.analysis;
            rec.remedy = entry.remedy;
            rec.servedFromBook = true;
        } else {
            const BookPaths& paths = bookPaths();
            const BookStore store = BookStore::loadMerged(paths.canonical, paths.spill);

            BookEntry entry;
            if (store.query(hash, entry)) {
                // 리뷰 Finding C1: 여기서 예전에는 message를 entry.analysis(과거
                // 분석 텍스트)로 덮어썼다. 해시는 실패의 "자리와 종류"만 같음을
                // 보장할 뿐(ErrorHash.h 계약) 이번 발생에 관여한 구체적 노드
                // 이름·값까지 같다고는 보장하지 않으므로, 그건 이번 발생과 무관한
                // (심지어 이미 씬에 없는) 대상을 마치 방금 일어난 일처럼 사용자
                // 눈앞에 내놓는 것이었다. message는 book 히트 여부와 무관하게
                // 언제나 이번 호출이 실제로 넘긴, 지금 일어난 일이다.
                //
                // 과거 분석은 사라지지 않는다 -- priorAnalysis라는 별도 필드에
                // 담아 "지금 무슨 일이 났는지"와 "이 자리에서 과거엔 뭘로
                // 밝혀졌는지"를 한 레코드 안에 나란히 둔다(진단 패널 Layer B가
                // 그대로 읽을 모양). entry.analysis가 비어 있을 수도 있다 --
                // registerRemedy()가 아직 book에 없는 해시에 해법만 등록하면
                // 분석 없는 항목이 만들어진다(사용자가 스스로 고친 뒤 등록하는
                // 경우). 그때 priorAnalysis는 그냥 빈 문자열로 둔다(있는 그대로
                // "과거 분석 없음"). 해법(remedy)과 servedFromBook은 두 경우
                // 모두 그대로 적용한다.
                rec.message = message.asChar();
                rec.priorAnalysis = entry.analysis;
                rec.remedy = entry.remedy;
                rec.servedFromBook = true;
                // 디스크에서 확인된 히트이므로 이 세션 동안은 다시 디스크를
                // 볼 필요가 없다 -- 캐시에 채운다.
                bookCache().emplace(hash, entry);
            } else {
                rec.message = message.asChar();
                rec.servedFromBook = false;

                BookEntry fresh;
                fresh.analysis = rec.message;
                fresh.context = context;
                if (BookStore::appendToSpill(paths.spill, hash, fresh)) {
                    // 쓰기가 실제로 성공했을 때만 캐시한다. 실패했으면(book
                    // 불가) book에는 진짜로 아무 것도 없으므로, 캐시했다가는
                    // 다음 번 동일 실패를 거짓으로 "book 히트"라 답하게 된다
                    // -- test_diag_degraded.py가 요구하는 "book 불가 동안은
                    // 매 발생이 새 분석"이라는 정직성이 바로 이 분기에 달려
                    // 있다.
                    bookCache().emplace(hash, fresh);
                } else {
                    bookUnwritable = true;
                }
                ++g_freshAnalysisCount;
            }
        }
    } catch (const std::exception& e) {
        // book이 죽어도 진단은 죽지 않는다 (스펙 §3.6). 이 실패 자체는
        // 재귀적으로 error()를 부르지 않고 devInfo로만 남긴다.
        //
        // priorAnalysis/remedy도 함께 비운다: 히트 분기가 그 둘을 채운
        // 뒤에 예외가 나면, servedFromBook=false인데 과거 분석은 달려 있는
        // 자기모순 레코드가 남는다.
        rec.message = message.asChar();
        rec.priorAnalysis.clear();
        rec.remedy.clear();
        rec.servedFromBook = false;
        ++g_freshAnalysisCount;
        devInfo(MString("Maro: book 조회/기록 실패, 로컬 기록으로 진행: ") + e.what());
    } catch (...) {
        rec.message = message.asChar();
        rec.priorAnalysis.clear();
        rec.remedy.clear();
        rec.servedFromBook = false;
        ++g_freshAnalysisCount;
        devInfo("Maro: book 조회/기록에서 알 수 없는 오류, 로컬 기록으로 진행.");
    }

    // 반드시 아래 lock_guard보다 먼저 불러야 한다: warn()이 mutex()를 스스로
    // 잠그므로, 이 error()가 이미 락을 쥔 채로 warn()을 부르면 std::mutex는
    // 재진입 불가라 교착 상태가 된다.
    if (bookUnwritable) {
        warnBookUnwritableOnce(bookPaths().spill);
    }

    // 리뷰 Finding I2: rec.remedy는 book 히트에서 채워지지만, 지금까지는
    // maroDiagQuery(테스트 전용 커맨드)로만 읽혔다 -- Layer B 패널이 아직
    // 없는 지금은 어떤 프로덕션 경로도 사용자에게 해법을 보여주지 않았다.
    // 여기서 별도의 displayInfo() 호출로 붙여, 실제로 등록된 해법이 있으면
    // 그 자리에서 바로 보이게 한다.
    //
    // 판단: 에러 문장과 같은 displayError() 호출에 이어 붙이지 않고 별도의
    // displayInfo() 줄로 낸다. 스크립트 에디터는 심각도별로 색이 다르다
    // (에러=빨강, 일반=기본색) -- 한 줄로 합치면 전부 에러색으로 칠해져
    // "해법은 실패의 일부가 아니라 제안"이라는 시각적 구분이 텍스트
    // 마커만으로 흉내 낼 수밖에 없다. 별도 호출로 내면 그 구분이 Maya의
    // 기본 색 규칙에서 공짜로 나온다.
    //
    // priorAnalysis(book에 있는 과거 분석)는 일부러 여기서 에코하지 않는다.
    // Finding C1이 고친 바로 그 문제 -- 과거 발생의 텍스트가 이번 발생의
    // 사실인 것처럼 보이는 것 -- 를, 굵은 글씨나 색 없이 한 줄짜리 스크립트
    // 에디터 에코에 그대로 얹으면 "표기는 고쳤지만 사용자 눈에는 여전히
    // 뒤섞여 보이는" 상태로 되돌아간다. priorAnalysis는 maroDiagQuery의
    // 10번째 필드로 이미 노출되어 있고, "지금 일어난 일"과 "과거엔 뭐였는지"를
    // 나란히, 구분된 자리에 보여주는 것은 정확히 진단 패널(Layer B)의
    // 몫이다 -- 그게 아직 없다고 해서 그 구분을 포기하는 임시 에코를 먼저
    // 내보내지 않는다.
    if (isMainThread()) {
        MGlobal::displayError(MString("[Maro-Error] ") + MString(rec.message.c_str()));
        if (!rec.remedy.empty()) {
            MGlobal::displayInfo(MString("[Maro-Fix] ") + MString(rec.remedy.c_str()));
        }
    }
    std::lock_guard<std::mutex> lock(mutex());
    assignSequenceAndPush(std::move(rec), stream());
}

std::size_t BoadMaro::freshAnalysisCount() { return g_freshAnalysisCount.load(); }

void BoadMaro::registerRemedy(const std::string& errorHash, const MString& remedyText) {
    // Finding I4: error()와 같은 book 뮤텍스로 book 파일 I/O + 캐시를
    // 보호한다. 어느 쪽(error()의 캐시 미스 경로, 여기)이 먼저 book을 만지든
    // 같은 락으로 직렬화되어야, 두 스레드가 스필에 동시에 append하는 경합이
    // 사라진다.
    bool bookUnwritable = false;
    try {
        std::lock_guard<std::mutex> bookLock(bookMutex());

        const BookPaths& paths = bookPaths();
        const BookStore store = BookStore::loadMerged(paths.canonical, paths.spill);

        BookEntry entry;
        store.query(errorHash, entry);  // 없으면 entry는 기본값(빈 분석)으로 남는다.
        entry.remedy = remedyText.asChar();

        // 여기서도 book이 쓰기 불가능할 수 있다 -- error()의 캐시 미스 경로와
        // 같은 래치를 공유해서, 어느 쪽이 먼저 실패를 발견하든 세션당 한 번만
        // 경고한다("book을 쓸 수 없다"는 사실은 호출 경로와 무관한 하나의
        // 사실이다). 실제 warn() 호출은 아래에서, 이 락을 놓은 뒤에 한다.
        if (!BookStore::appendToSpill(paths.spill, errorHash, entry)) {
            bookUnwritable = true;
        }

        // Finding M3: 이 해시의 캐시 항목을 무효화한다. error()가 이전에
        // 이 해시를 채워 뒀을 수 있는데, 그대로 두면 방금 등록한 해법을
        // 캐시된 옛 항목(해법 없음)이 계속 가려서 이번 세션 안에서는 영원히
        // 보이지 않는다. 지우기만 하고 새 값으로 다시 채우지 않는 이유:
        // 위 appendToSpill이 실패했을 수 있고(book 불가), 그 경우 디스크의
        // 실제 상태보다 캐시가 앞서가는 상태를 만들지 않기 위해서다 -- 다음
        // 조회가 디스크를 다시 확인하게 둔다.
        bookCache().erase(errorHash);
    } catch (const std::exception& e) {
        devInfo(MString("Maro: 해법 등록 실패: ") + e.what());
        return;
    } catch (...) {
        devInfo("Maro: 해법 등록에서 알 수 없는 오류.");
        return;
    }

    // error()와 같은 이유로 락 밖에서 부른다: warn()은 레코드 뮤텍스를
    // 스스로 잡는다. book 뮤텍스는 위 try 블록이 끝나며 이미 풀렸으므로
    // 얽히진 않지만, book I/O와 화면/기록 에코라는 두 관심사를 여기서도
    // 명확히 분리해 둔다 (error()와 같은 규율).
    if (bookUnwritable) {
        warnBookUnwritableOnce(bookPaths().spill);
    }
}

bool BoadMaro::lookupBook(const std::string& errorHash, BookEntry& out) {
    try {
        std::lock_guard<std::mutex> bookLock(bookMutex());
        const auto cached = bookCache().find(errorHash);
        if (cached != bookCache().end()) {
            out = cached->second;
            return true;
        }
        const BookPaths& paths = bookPaths();
        const BookStore store = BookStore::loadMerged(paths.canonical, paths.spill);
        BookEntry entry;
        if (!store.query(errorHash, entry)) return false;
        bookCache().emplace(errorHash, entry);
        out = entry;
        return true;
    } catch (...) {
        // book이 죽어도 패널은 죽지 않는다. 해법 없이 상세를 보여줄 뿐이다.
        return false;
    }
}

std::size_t BoadMaro::recordCount() {
    std::lock_guard<std::mutex> lock(mutex());
    return stream().size();
}

DiagRecord BoadMaro::recordAt(std::size_t indexFromEnd) {
    std::lock_guard<std::mutex> lock(mutex());
    return stream().at(stream().size() - 1 - indexFromEnd);
}

std::vector<DiagRecord> BoadMaro::snapshotRecords() {
    // 락을 한 번만 잡고 그 안에서 전체를 복사한다 -- recordCount()+recordAt()
    // 루프처럼 락을 반복해 여닫지 않으므로, 다른 스레드의 push_back이 이
    // 복사 도중에 끼어들 수 없다. 벡터 복사 대입 자체가 이미 오래된 것부터
    // 순서대로다.
    std::lock_guard<std::mutex> lock(mutex());
    return stream();
}

void BoadMaro::resetForTest() {
    // carried-forward Minor finding: 예전에는 레코드 스트림과
    // freshAnalysisCount만 리셋하고 g_bookUnwritableWarned 래치와(이 배치가
    // 추가한) book 캐시는 그대로 남겨 뒀다 -- "테스트 전용 리셋 훅"이라는
    // 이름과 실제 동작이 어긋났다. 지금은 콜러가 없지만(grep 확인됨), 이름이
    // 약속하는 대로 boad 세션 상태 전부를 되돌리는 편이 나중에 누가 이걸
    // 실제로 쓰기 시작했을 때 "일부만 리셋됐다"는 조용한 함정을 남기지
    // 않는다.
    {
        std::lock_guard<std::mutex> lock(mutex());
        stream().clear();
    }
    g_nextSequence.store(0);
    {
        std::lock_guard<std::mutex> bookLock(bookMutex());
        bookCache().clear();
    }
    g_freshAnalysisCount = 0;
    g_bookUnwritableWarned = false;
}

namespace {
// Maya 메인 스레드만 doIt을 부르지만, thread_local로 두면 우연한 재진입도 안전하다.
thread_local std::vector<std::string> g_commandStack;
}  // namespace

ScopedCommandContext::ScopedCommandContext(const char* commandName) {
    g_commandStack.emplace_back(commandName);
}

ScopedCommandContext::~ScopedCommandContext() {
    if (!g_commandStack.empty()) g_commandStack.pop_back();
}

namespace onfix {

std::string activeCommand() {
    return g_commandStack.empty() ? std::string() : g_commandStack.back();
}

DgContext capture(const MString& nodeType, const MString& attributeName,
                   const MString& axisOrTarget) {
    DgContext ctx;
    ctx.nodeType = nodeType.asChar();
    ctx.attributeName = attributeName.asChar();
    ctx.axisOrTarget = axisOrTarget.asChar();
    ctx.activeCommand = activeCommand();
    return ctx;
}

}  // namespace onfix

}  // namespace maro
