#include "maro_diag/ErrorHash.h"

#include <cstddef>
#include <cstdint>

namespace maro {

std::string hashError(const std::string& siteTag) {
    // FNV-1a, 64비트. 오프셋과 프라임은 표준 상수다.
    std::uint64_t h = 0xcbf29ce484222325ULL;
    constexpr std::uint64_t kPrime = 0x100000001b3ULL;

    for (unsigned char c : siteTag) {
        h ^= static_cast<std::uint64_t>(c);
        h *= kPrime;
    }

    // 16자리 소문자 16진수로 고정폭 표현한다. book 파일의 JSON 키로 쓰기
    // 좋고, 사람이 눈으로 비교하기도 쉽다.
    static const char kHex[] = "0123456789abcdef";
    std::string out(16, '0');
    for (int i = 15; i >= 0; --i) {
        out[static_cast<std::size_t>(i)] = kHex[h & 0xF];
        h >>= 4;
    }
    return out;
}

}  // namespace maro
