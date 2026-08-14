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
// 동시성 가정: 스필에 대한 append의 안전성은 OS의 append 원자성에 기댄다.
// 지금은 플러그인 인스턴스가 하나뿐이라 문제되지 않지만, 이 가정은 코드
// 어디에도 명시돼 있지 않았다 -- 여러 프로세스/스레드가 동시에 스필에 쓰는
// 상황을 지원하려면 이 가정부터 다시 검토해야 한다.
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
