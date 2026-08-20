#pragma once

#include <cstdint>
#include <string>

#include <windows.h>

namespace maro::ipc {

// 명명된 뮤텍스 하나를 얻고 소멸 시 놓는다. 획득 실패(타임아웃, 이미 다른
// 프로세스가 쥐고 있음)는 예외가 아니라 isAcquired()==false로 나타난다 --
// 호출부가 "못 얻었으니 포기한다"를 스스로 판단하게 한다.
//
// C-1은 이것을 감시자 단일 인스턴스 보호에만 쓴다. C-4(book 정본 쓰기를
// 감시자로 이전)가 새 이름(예: Global\maro_book_write_mutex)으로 같은
// 타입을 재사용해 프로세스 간 book 쓰기를 직렬화할 자리다.
class NamedMutexGuard {
public:
    NamedMutexGuard(const std::string& name, std::uint32_t timeoutMs);
    ~NamedMutexGuard();

    NamedMutexGuard(const NamedMutexGuard&) = delete;
    NamedMutexGuard& operator=(const NamedMutexGuard&) = delete;

    bool isAcquired() const { return acquired_; }

private:
    HANDLE handle_ = nullptr;
    bool acquired_ = false;
};

}  // namespace maro::ipc
