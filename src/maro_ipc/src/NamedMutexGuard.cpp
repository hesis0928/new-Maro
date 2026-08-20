#include "maro_ipc/NamedMutexGuard.h"

namespace maro::ipc {

NamedMutexGuard::NamedMutexGuard(const std::string& name, std::uint32_t timeoutMs) {
    // bInitialOwner=FALSE -- 만들자마자 자동으로 갖지 않는다. 아래
    // WaitForSingleObject가 소유권을 얻는 유일한 경로여야 "얻었다"의 의미가
    // 하나로 고정된다.
    handle_ = ::CreateMutexA(nullptr, FALSE, name.c_str());
    if (handle_ == nullptr) {
        acquired_ = false;
        return;
    }

    const DWORD result = ::WaitForSingleObject(handle_, timeoutMs);
    // WAIT_ABANDONED: 이전 소유자가 놓지 않고 죽었다는 뜻이다. 뮤텍스
    // 자체는 여전히 유효한 소유권으로 넘어오므로 획득으로 친다 -- 이
    // 프로젝트가 "죽은 프로세스가 남긴 잠금 때문에 다음 프로세스가 영원히
    // 못 뜨는" 상태를 만들지 않는다는 원칙과 같다.
    acquired_ = (result == WAIT_OBJECT_0 || result == WAIT_ABANDONED);
    if (!acquired_) {
        ::CloseHandle(handle_);
        handle_ = nullptr;
    }
}

NamedMutexGuard::~NamedMutexGuard() {
    if (acquired_ && handle_ != nullptr) {
        ::ReleaseMutex(handle_);
    }
    if (handle_ != nullptr) {
        ::CloseHandle(handle_);
    }
}

}  // namespace maro::ipc
