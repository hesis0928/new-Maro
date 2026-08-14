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
// 플러그인이 쓸 수 있는 유일한 통로다. JSON Lines는 항상 append이므로 쓰는
// 도중 플러그인이 죽어도 이미 쓴 줄은 그대로 유효하다 -- 트리 전체를 다시
// 쓰는 포맷이었다면 그 중간에 죽었을 때 파일 전체가 깨졌을 것이다.
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
