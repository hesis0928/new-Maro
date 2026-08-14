#pragma once

#include <cstddef>
#include <filesystem>
#include <string>
#include <unordered_map>

#include "maro_diag/DiagRecord.h"

namespace maro {

// book 한 항목. 해시 하나에 원인 분석 한 편과 해법 하나(있다면)가 붙는다.
struct BookEntry {
    std::string analysis;  // 사람이 읽는 원인 설명. 최초 발생 시 boad가 채운다.
    std::string remedy;    // 등록된 해법. 없으면 빈 문자열.
    DgContext context;      // 최초 관측 시점의 DG 컨텍스트. 참고용.
};

// book 파일 하나 = JSON Lines. 한 줄에 레코드 하나.
// {"hash":"...","analysis":"...","remedy":"...","nodeType":"...",
//  "attributeName":"...","activeCommand":"...","axisOrTarget":"..."}
//
// 스필을 이 모양으로 고른 이유(설계 스펙 §5.4): 감시자가 없는 지금, 스필은
// 플러그인이 쓸 수 있는 유일한 통로다. JSON Lines는 항상 append이므로, 쓰는
// 도중 플러그인이 죽어도 그 전에 이미 완결된 줄들은 그대로 유효하다 -- 트리
// 전체를 다시 쓰는 포맷이었다면 그 중간에 죽었을 때 파일 전체가 깨졌을
// 것이다. 단, 죽은 시점에 쓰던 줄 자체는 개행 없이 끝난 조각(fragment)으로
// 남을 수 있다 -- 그 조각은 다음 로드에서 깨진 줄로 건너뛰어진다(의도된
// 동작이며 그대로 유지된다). appendToSpill은 이 조각 위에 새 레코드를 바로
// 이어 붙이지 않도록, 쓰기 전에 파일이 이미 개행으로 끝나는지 확인하고
// 아니면 먼저 개행을 넣는다: 그러지 않으면 조각과 새 레코드가 하나의 파싱
// 불가능한 줄로 합쳐져서, 조각뿐 아니라 방금 쓴 새 레코드까지 함께
// 사라진다 -- 크래시 복구가 바로 이 서브시스템이 존재하는 이유이므로 이
// 손실은 특히 심각하다.
//
// 병합 의미론: 병합은 레코드를 통째로 교체한다, 필드 단위 패치가 아니다.
// 같은 해시에 대해 스필 항목의 컨텍스트가 정본보다 부실해도 스필이 이기면
// 정본의 더 풍부한 컨텍스트는 통째로 사라진다 -- 각 줄이 완결된 레코드이기
// 때문에 생기는 의도된 동작이지만, 필드 단위로 병합될 거라고 오해하기
// 쉽다.
//
// 동시성: 이 클래스 자신(loadMerged/query/appendToSpill)은 스레드 안전을
// 스스로 보장하지 않는다 -- 파일을 열고 읽고 쓰는 정적 함수 모음일 뿐,
// 내부에 락이 없다. 그 대신 유일한 프로덕션 호출부인
// maro::BoadMaro::error()/registerRemedy()(MaroDiag.cpp)가 book 전용
// 뮤텍스(BoadMaro::bookMutex())로 이 클래스에 대한 모든 접근을 직렬화한다
// -- 그래서 이 파일 자체에는 동시성 코드가 없다(Finding I4).
//
// 왜 필요해졌는가: Task 7이 MaroAxisNode::compute, 능력 노드 넷의 compute,
// MaroCommandDeviceNode::compute를 전부 BoadMaro::error()로 옮겼고, Maya
// 2026의 기본 평가 관리자(Parallel Evaluation Manager)는 그 compute()들을
// 서로 다른 워커 스레드에서 동시에 돌릴 수 있다(tests/maya/test_diag_thread.py가
// 워커에서 실제로 스필까지 닿는다는 것을 증명한다). 락 없이 두 스레드가
// 같은 세션에서 동시에 이 클래스를 거치면, appendToSpill의 "마지막 바이트가
// 개행인지 확인한 뒤 아니면 개행을 쓴다"는 검사-후-쓰기(TOCTOU)와, 그
// 뒤의 `ofs << dump() << '\n'`(스트림 삽입 두 번, 한 버퍼에 들어갈 때만
// 원자적)이 서로 겹쳐 스필 파일이 깨질 수 있었다 -- 로더가 깨진 줄을
// 건너뛰므로 겉으로는 "책이 아무 말썽 없이 도는" 것처럼 보이지만, 그건
// 설계가 아니라 운이었다.
//
// 여러 "프로세스"가 동시에 같은 스필에 쓰는 상황(예: 서로 다른 Maya 인스턴스
// 두 개가 같은 MARO_DIAG_BOOK_DIR을 공유)은 여전히 이 락의 범위 밖이다 --
// bookMutex()는 한 프로세스 안의 스레드끼리만 직렬화한다. 그 시나리오까지
// 지원하려면 파일 락(예: OS 레벨 advisory lock) 같은 별도 메커니즘이
// 필요하다.
class BookStore {
public:
    // 정본과 스필을 읽어 병합한다. 둘 다 없으면 빈 스토어를 돌려준다 --
    // 파일이 없는 것은 에러가 아니다 (스펙 §3.6, §5.4: 감시자/정본이 없어도
    // book 조회는 계속 동작해야 한다). 파일이 있는데 파싱할 수 없는 줄은
    // 건너뛰고 나머지는 살린다 -- 깨진 줄 하나가 지식 전체를 지우지 않는다.
    static BookStore loadMerged(const std::filesystem::path& canonicalPath,
                                 const std::filesystem::path& spillPath);

    bool query(const std::string& errorHash, BookEntry& out) const;
    std::size_t size() const { return entries_.size(); }

    // Layer A는 정본에 쓰지 않는다 (스펙 §3.5) -- 스필에 한 줄만 추가한다.
    // 실패해도(디렉터리가 없거나 쓰기 권한이 없거나) 예외를 던지지 않고
    // false를 돌려준다: book이 죽어도 진단은 죽지 않는다.
    static bool appendToSpill(const std::filesystem::path& spillPath,
                               const std::string& errorHash,
                               const BookEntry& entry);

private:
    static void loadFile(const std::filesystem::path& path,
                          std::unordered_map<std::string, BookEntry>& out);

    std::unordered_map<std::string, BookEntry> entries_;
};

}  // namespace maro
