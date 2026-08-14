#include "MaroDiag.h"

#include <atomic>
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
            dir = userAppDir.length() > 0 ? std::filesystem::path(userAppDir.asChar())
                                           : std::filesystem::temp_directory_path();
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

void BoadMaro::info(const MString& message) {
    DiagRecord rec;
    rec.severity = DiagSeverity::Info;
    rec.message = message.asChar();
    // 워커 스레드에서는 화면 에코를 건너뛴다 -- 레코드는 그대로 남는다
    // (MaroDiag.h의 스레드 안전성 주석 참고).
    if (isMainThread()) {
        MGlobal::displayInfo(MString("[Maro-Info] ") + message);
    }
    std::lock_guard<std::mutex> lock(mutex());
    stream().push_back(std::move(rec));
}

void BoadMaro::warn(const MString& message) {
    DiagRecord rec;
    rec.severity = DiagSeverity::Warn;
    rec.message = message.asChar();
    if (isMainThread()) {
        MGlobal::displayWarning(MString("[Maro-Warn] ") + message);
    }
    std::lock_guard<std::mutex> lock(mutex());
    stream().push_back(std::move(rec));
}

void BoadMaro::devInfo(const MString& message) {
#ifdef _DEBUG
    DiagRecord rec;
    rec.severity = DiagSeverity::DevInfo;
    rec.message = message.asChar();
    if (isMainThread()) {
        MGlobal::displayInfo(MString("[Maro-Dev] ") + message);
    }
    std::lock_guard<std::mutex> lock(mutex());
    stream().push_back(std::move(rec));
#else
    (void)message;
#endif
}

void BoadMaro::error(const std::string& siteTag, const MString& message,
                      const DgContext& context) {
    DiagRecord rec;
    rec.severity = DiagSeverity::Error;
    rec.context = context;

    // appendToSpill이 false를 돌려주면(book 디렉터리를 쓸 수 없는 등) true가
    // 된다. try/catch 밖, 아직 이 함수가 자신의 lock_guard를 잡기 전에
    // warnBookUnwritableOnce()를 부르기 위해 밖에 선언해 둔다.
    bool bookUnwritable = false;

    try {
        const std::string hash = hashError(siteTag);
        rec.errorHash = hash;

        const BookPaths& paths = bookPaths();
        const BookStore store = BookStore::loadMerged(paths.canonical, paths.spill);

        BookEntry entry;
        if (store.query(hash, entry)) {
            // entry.analysis가 비어 있을 수 있다 -- registerRemedy()가 아직
            // book에 없는 해시에 해법만 등록하면 분석 없는 항목이 만들어진다
            // (사용자가 스스로 고친 뒤 등록하는 경우). 그 경우 빈 문자열로
            // 실제 에러 메시지를 덮어써서 사용자에게 아무 내용도 안 보여주면
            // 안 되므로, 분석이 있을 때만 book 표기를 붙이고 없으면 원래
            // message를 그대로 쓴다. 해법(remedy)과 servedFromBook은 두
            // 경우 모두 그대로 적용한다.
            rec.message = !entry.analysis.empty()
                              ? entry.analysis + "\n(Maro: book에 있는 과거 분석에서 즉답)"
                              : message.asChar();
            rec.remedy = entry.remedy;
            rec.servedFromBook = true;
        } else {
            rec.message = message.asChar();
            rec.servedFromBook = false;

            BookEntry fresh;
            fresh.analysis = rec.message;
            fresh.context = context;
            if (!BookStore::appendToSpill(paths.spill, hash, fresh)) {
                bookUnwritable = true;
            }
            ++g_freshAnalysisCount;
        }
    } catch (const std::exception& e) {
        // book이 죽어도 진단은 죽지 않는다 (스펙 §3.6). 이 실패 자체는
        // 재귀적으로 error()를 부르지 않고 devInfo로만 남긴다.
        rec.message = message.asChar();
        rec.servedFromBook = false;
        ++g_freshAnalysisCount;
        devInfo(MString("Maro: book 조회/기록 실패, 로컬 기록으로 진행: ") + e.what());
    } catch (...) {
        rec.message = message.asChar();
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

    if (isMainThread()) {
        MGlobal::displayError(MString("[Maro-Error] ") + MString(rec.message.c_str()));
    }
    std::lock_guard<std::mutex> lock(mutex());
    stream().push_back(std::move(rec));
}

std::size_t BoadMaro::freshAnalysisCount() { return g_freshAnalysisCount.load(); }

void BoadMaro::registerRemedy(const std::string& errorHash, const MString& remedyText) {
    try {
        const BookPaths& paths = bookPaths();
        const BookStore store = BookStore::loadMerged(paths.canonical, paths.spill);

        BookEntry entry;
        store.query(errorHash, entry);  // 없으면 entry는 기본값(빈 분석)으로 남는다.
        entry.remedy = remedyText.asChar();

        // 여기서도 book이 쓰기 불가능할 수 있다 -- error()의 캐시 미스 경로와
        // 같은 래치를 공유해서, 어느 쪽이 먼저 실패를 발견하든 세션당 한 번만
        // 경고한다("book을 쓸 수 없다"는 사실은 호출 경로와 무관한 하나의
        // 사실이다).
        if (!BookStore::appendToSpill(paths.spill, errorHash, entry)) {
            warnBookUnwritableOnce(paths.spill);
        }
    } catch (const std::exception& e) {
        devInfo(MString("Maro: 해법 등록 실패: ") + e.what());
    } catch (...) {
        devInfo("Maro: 해법 등록에서 알 수 없는 오류.");
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

void BoadMaro::resetForTest() {
    std::lock_guard<std::mutex> lock(mutex());
    stream().clear();
    g_freshAnalysisCount = 0;
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
