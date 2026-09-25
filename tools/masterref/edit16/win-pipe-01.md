<!-- win-pipe-01 Windows › 명명된 파이프·I/O (27개) 2026-09-24 -->

#### 커널 객체(파이프/뮤텍스/잡 오브젝트/이벤트)

**직관:** 핸들로 참조하는 OS 자원의 총칭. 이름을 붙이면 프로세스 간에 공유할 수 있고(`Global\`, `\\.\pipe\`), 마지막 핸들이 닫히면 사라진다.

**동작:** Maro의 감시자 체계는 네 종류를 함께 쓴다 — 명명된 파이프(IPC 채널), 명명 뮤텍스(단일 인스턴스), 명명 이벤트(킬 스위치), job object(수명 격리). 이름에는 PID를 넣어 Maya 인스턴스를 구분한다. 핸들은 `CloseHandle`로 해제하고, 동기화 객체는 `WaitForSingleObject`/`WaitForMultipleObjects`로 신호를 기다린다. 레거시 공유 메모리(`windows_shared_memory`)도 페이지 파일 백드 섹션 객체라 프로세스가 죽으면 자동 소멸한다 — POSIX shm과 달리 파일이 남지 않는다.

**예시:**
```
\\.\pipe\maro_sentinel_<pid>        파이프
Global\maro_sentinel_mutex_<pid>    뮤텍스
Global\maro_sentinel_kill_<pid>     이벤트
(job object는 이름 없이 핸들로만)
```

**관련 코드:**
- `src/maro_ipc/src/Naming.cpp:5-20` — 네 이름 규칙
- `src/maro_ipc/src/NamedPipe.cpp:112-140` — 파이프 생성
- `src/maro_ipc/src/NamedMutexGuard.cpp:5-34` — 뮤텍스

**증거:**
- §0.3, §4.3.1, §5.3.4

**함정:** 핸들을 안 닫으면 객체가 살아남아 같은 이름으로 새로 만들려는 쪽이 "이미 있음"을 만난다. 수명은 생성자가 아니라 핸들 수가 정한다.

**교훈:** OS 자원을 종류별로 익히기보다 "핸들·이름·신호·수명"이라는 공통 모델로 익히면 새 API도 같은 질문으로 읽힌다.

#### 명명된 파이프

**직관:** `\\.\pipe\name`으로 식별되는 커널 IPC 채널. NPFS(Named Pipe File System) 커널 객체이며 파일 API(`ReadFile`/`WriteFile`)로 읽고 쓴다.

**동작:** 감시자와 Maya는 PID별 파이프 하나로 통신한다. 서버(감시자)는 `CreateNamedPipeA`로 메시지 모드·오버랩·첫 인스턴스 플래그를 걸어 만들고, 클라이언트(Maya)는 `CreateFileA`로 연다. 메시지 두 종류(HELLO, SessionEndClean)만 오가며 JSON으로 직렬화된다. 프로세스가 죽으면 커널이 핸들을 닫아 상대에게 `ERROR_BROKEN_PIPE`가 즉시 전달되므로, 임의의 타임아웃 값이 설계에 들어가지 않는다.

**예시:**
```cpp
// 서버
pipe_ = ::CreateNamedPipeA(name.c_str(), PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED | FILE_FLAG_FIRST_PIPE_INSTANCE,
                           PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT, 1, kBufferSize, kBufferSize, 0, nullptr);
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:112-140` — 서버 생성
- `src/maro_ipc/src/NamedPipe.cpp:200-240` — 클라이언트 접속
- `src/maro_ipc/src/Naming.cpp:5-8` — `\\.\pipe\maro_sentinel_<pid>`

**증거:**
- §1.4, §5.3, §5.3.4, §11.4

**함정:** 레거시 `test_ipc_pipe.cpp`는 이름만 비슷할 뿐 현재 `maro_ipc`와 무관하다(빌드 밖). 이름이 겹치는 옛 코드는 혼동을 만든다.

**교훈:** 로컬 IPC에는 소켓보다 명명된 파이프가 낫다 — 메시지 경계·즉시 끊김 신호·권한 모델을 커널이 준다.

#### 논블로킹

**직관:** 호출이 완료를 기다리지 않고 바로 돌아오는 I/O. Windows에서는 오버랩 I/O + 이벤트 대기 + 타임아웃 조합으로 구현한다.

**동작:** Maro의 파이프는 `FILE_FLAG_OVERLAPPED`로 열려 `ReadFile`/`WriteFile`이 즉시 반환하고 `ERROR_IO_PENDING`을 남긴다. 그 뒤 `WaitForSingleObject(hEvent, timeoutMs)`로 완료를 기다리고, 타임아웃이면 `CancelIoEx`로 취소한다. 이렇게 해야 "모든 대기에 타임아웃"이라는 제1 규칙을 지킬 수 있다 — 블로킹 `ReadFile`은 상대가 영영 안 보내면 영원히 멈춘다.

**예시:**
```cpp
if (!::ReadFile(pipe, buf, n, &read, &ov) && ::GetLastError() == ERROR_IO_PENDING) {
    if (::WaitForSingleObject(ov.hEvent, timeoutMs) != WAIT_OBJECT_0) { /* CancelIoEx */ }
}
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:20-58` — 오버랩 읽기·취소
- `src/maro_ipc/src/NamedPipe.cpp:70-92` — `readOneMessage`

**증거:**
- §1.4, §5.3.4

**함정:** 오버랩 핸들에 블로킹 호출 관례(동기 반환 기대)를 섞으면 `OVERLAPPED` 없이 호출해 정의되지 않은 동작이 된다. 한 핸들에 한 방식.

**교훈:** 비동기 I/O의 목적은 속도가 아니라 **취소 가능성**이다. 취소할 수 있어야 좀비가 생기지 않는다.

#### `\\.\pipe\`

**직관:** 로컬 명명된 파이프의 경로 접두사. `\\.\`는 로컬 머신, `pipe\`는 NPFS 장치를 가리키며 그 뒤가 파이프 이름이다.

**동작:** `pipeName(pid)`가 `"\\\\.\\pipe\\maro_sentinel_" + pid`를 만든다(C++ 문자열이라 역슬래시가 두 배). 원격이라면 `\\<host>\pipe\name`이 되지만 Maro는 로컬만 쓴다. 이름은 대소문자를 구분하지 않으며 NPFS 네임스페이스는 평평하다(하위 경로처럼 보이는 `\`는 이름의 일부).

**예시:**
```cpp
std::string pipeName(std::uint64_t pid) {
    return "\\\\.\\pipe\\maro_sentinel_" + std::to_string(pid);
}
```

**관련 코드:**
- `src/maro_ipc/src/Naming.cpp:5-8` — 이름 조립
- `tests/ipc/test_naming.cpp` — 형식 고정

**증거:**
- §5.3, §5.3.2, §11.4

**함정:** 파이프 이름은 세션 격리가 없다 — 같은 머신의 다른 사용자도 이름을 알면 접속을 시도할 수 있다. 그래서 첫 인스턴스 플래그와 SQOS가 필요하다.

**교훈:** 네임스페이스가 평평하고 전역이면 이름 자체가 보안 경계가 아니다. 플래그로 막는다.

#### 메시지 모드(`PIPE_TYPE_MESSAGE|PIPE_READMODE_MESSAGE`) vs 바이트 모드

**직관:** 메시지 모드 파이프는 한 번의 `WriteFile`이 한 번의 `ReadFile`로 경계까지 그대로 전달된다. 바이트 모드는 스트림이라 경계가 사라져 길이 프리픽스가 필요하다.

**동작:** Maro는 서버를 `PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT`로 만든다. 그래서 `readOneMessage()`는 한 번의 `ReadFile`로 JSON 한 개를 통째로 받고 **길이 프리픽스가 필요 없다**. 버퍼는 `kBufferSize = 8192`이며, 이를 넘는 메시지는 `ERROR_MORE_DATA`로 실패하고 나머지 조각이 큐에 남는다.

**예시:**
```
메시지 모드: WriteFile("{...}")  →  ReadFile → "{...}"  (경계 보존)
바이트 모드: WriteFile 두 번     →  ReadFile 한 번에 둘이 붙어 옴 → 파싱 실패
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:112-140` — 모드 플래그
- `src/maro_ipc/src/NamedPipe.cpp:70-92` — 한 번의 읽기 = 한 메시지
- `src/maro_ipc/src/NamedPipe.cpp:10-16` — `kBufferSize` 주석

**증거:**
- §5.3, §5.3.4, §10.8

**함정:** 서버가 메시지 타입이어도 `CreateFile`로 연 **클라이언트는 바이트 읽기 모드로 시작**한다. 그대로 두면 큐에 쌓인 두 메시지가 한 번에 붙어 온다.

**교훈:** 경계 보존은 양쪽 핸들의 모드가 모두 메시지일 때만 성립한다. 서버 설정만으로는 부족하다.

#### `PIPE_ACCESS_DUPLEX`

**직관:** 파이프를 양방향으로 여는 접근 플래그. 서버와 클라이언트가 서로 읽고 쓸 수 있다.

**동작:** 감시자 프로토콜은 Maya가 HELLO를 보내고 감시자가 응답하는 왕복이 있어 양방향이 필요하다. `CreateNamedPipeA`의 첫 모드 인자에 `PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED | FILE_FLAG_FIRST_PIPE_INSTANCE`를 준다. 단방향이 필요하면 INBOUND/OUTBOUND 접근 모드를 쓴다.

**예시:**
```cpp
::CreateNamedPipeA(name, PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED | FILE_FLAG_FIRST_PIPE_INSTANCE, ...);
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:112-140` — 플래그 조합
- `src/maro_ipc/src/NamedPipe.cpp:173-177` — 서버의 응답 전송

**증거:**
- §5.3, §5.3.4

**함정:** 접근 모드와 파이프 타입 플래그는 서로 다른 인자다(열기 모드 vs 파이프 모드). 섞어 넣으면 `ERROR_INVALID_PARAMETER`가 난다.

**교훈:** 플래그가 많은 API는 인자별로 묶어 주석을 단다. 한 줄에 몰아 쓰면 어느 인자에 속하는지 알 수 없다.

#### `PIPE_WAIT`

**직관:** 파이프를 블로킹 모드로 두는 플래그. 오버랩 I/O와 함께 쓰면 "핸들은 블로킹이지만 요청은 비동기"가 되어, 대기는 우리가 `WaitForSingleObject`로 직접 통제한다.

**동작:** 파이프 모드 인자에 `PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT`를 준다. 반대인 NOWAIT 모드는 레거시 호환용으로 권장되지 않으며 `ERROR_NO_DATA` 폴링을 강요한다. Maro는 `FILE_FLAG_OVERLAPPED`로 비동기를 얻고 `PIPE_WAIT`를 유지한다.

**예시:**
```cpp
PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT   // 오버랩과 조합
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:112-140` — 파이프 모드
- `src/maro_ipc/src/NamedPipe.cpp:20-58` — 우리가 직접 거는 대기

**증거:**
- §5.3, §5.3.4

**함정:** NOWAIT 모드를 비동기 I/O로 착각하기 쉽다. 진짜 비동기는 `FILE_FLAG_OVERLAPPED`이고 NOWAIT는 즉시 실패를 주는 옛 방식이다.

**교훈:** 이름이 비슷한 두 메커니즘이 있으면 "권장되는 쪽"을 문서에서 확인하고 주석에 적는다.

#### `nMaxInstances=1`

**직관:** 같은 이름으로 만들 수 있는 파이프 인스턴스 수를 1로 제한하는 인자. Maya 하나에 감시자 하나라는 1:1 모델의 표현이다.

**동작:** `CreateNamedPipeA(..., 1, kBufferSize, kBufferSize, 0, nullptr)`. 두 번째 서버가 같은 이름으로 만들려 하면 실패한다. 보안 속성은 기본 DACL을 쓴다 — 명시 DACL은 심층 방어로 의미가 있지만 실제 공격 경로는 `FILE_FLAG_FIRST_PIPE_INSTANCE`와 클라이언트 쪽 SQOS가 닫는다.

**예시:**
```cpp
::CreateNamedPipeA(name, openMode, pipeMode, /* nMaxInstances */ 1,
                   kBufferSize, kBufferSize, /* default timeout */ 0, /* SA */ nullptr);
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:112-140` — 인스턴스 수와 버퍼
- `src/maro_ipc/src/Naming.cpp:5-8` — PID별 이름이라 인스턴스 1로 충분

**증거:**
- §5.3, §5.3.4

**함정:** 인스턴스 1은 "동시에 한 클라이언트"를 뜻하지 "평생 한 번"이 아니다. `DisconnectNamedPipe` 후 다시 `ConnectNamedPipe`할 수 있다.

**교훈:** 동시성 상한은 프로토콜의 모델(1:1)에서 나온다. 모델을 정하면 숫자가 따라온다.

#### `FILE_FLAG_OVERLAPPED`

**직관:** 핸들에 비동기 I/O를 켜는 플래그. 이 플래그가 있어야 `ReadFile`/`WriteFile`이 `OVERLAPPED`를 받아 즉시 반환한다.

**동작:** 서버는 `CreateNamedPipeA`의 열기 모드에, 클라이언트는 `CreateFileA`의 플래그 인자에 이 플래그를 준다. 그 덕에 `ConnectNamedPipe`·`ReadFile`·`WriteFile` 모두 타임아웃을 걸 수 있다. §10.8 규칙 표는 이 플래그를 `PIPE_TYPE_MESSAGE|PIPE_READMODE_MESSAGE`·`FILE_FLAG_FIRST_PIPE_INSTANCE`·클라이언트의 `SECURITY_SQOS_PRESENT|SECURITY_IDENTIFICATION`과 한 묶음으로 적는다.

**예시:**
```cpp
pipe_ = ::CreateFileA(name.c_str(), GENERIC_READ | GENERIC_WRITE, 0, nullptr, OPEN_EXISTING,
                      FILE_FLAG_OVERLAPPED | SECURITY_SQOS_PRESENT | SECURITY_IDENTIFICATION, nullptr);
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:112-140` — 서버
- `src/maro_ipc/src/NamedPipe.cpp:206-225` — 클라이언트와 SQOS 주석

**증거:**
- §5.3, §5.3.4, §11.4, §10.8

**함정:** 오버랩 핸들에 `OVERLAPPED` 없이 `ReadFile`을 부르면 동작이 정의되지 않는다. 모든 호출에 구조체를 넘겨야 한다.

**교훈:** 플래그 하나가 핸들의 호출 규약 전체를 바꾼다. 핸들을 만드는 곳과 쓰는 곳의 규약을 같이 본다.

#### `OVERLAPPED`

**직관:** 비동기 I/O 요청의 상태를 담는 구조체. 커널이 완료 시 이 구조체에 결과를 쓰므로, 요청이 끝날 때까지 살아 있어야 한다.

**동작:** `ScopedOverlapped`가 `hEvent`를 만들어 담고 소멸자에서 닫는다. 중요한 제약은 수명이다 — `CancelIoEx`는 취소를 **요청만** 하고 바로 돌아오므로, `OVERLAPPED`가 스택에 있는데 취소 완료 전에 함수를 벗어나면 커널이 이미 사라진 구조체에 결과를 쓴다(use-after-free, F-026). 그래서 `CancelIoEx`가 성공했을 때만 `GetOverlappedResult(..., bWait=TRUE)`로 완료를 기다린다.

**예시:**
```cpp
struct ScopedOverlapped {
    OVERLAPPED overlapped{};
    ScopedOverlapped() { overlapped.hEvent = ::CreateEventA(nullptr, TRUE, FALSE, nullptr); }
    ~ScopedOverlapped() { if (overlapped.hEvent) ::CloseHandle(overlapped.hEvent); }
};
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:56-66` — `ScopedOverlapped`
- `src/maro_ipc/src/NamedPipe.cpp:26-52` — 취소·완료 대기

**증거:**
- §5.3, §5.3.4
- F-026

**함정:** "취소했으니 끝났다"는 틀렸다. 취소는 비동기이고 커널은 나중에 `ERROR_OPERATION_ABORTED`로 완료시킨다.

**교훈:** 커널이 쓰는 메모리는 커널이 다 쓸 때까지 살려 둔다. 비동기 API의 수명 규칙은 문서의 한 문장에 있다.

#### `hEvent`(manual-reset)

**직관:** `OVERLAPPED.hEvent`에 넣는 완료 신호 이벤트. 수동 리셋이라 한 번 신호되면 우리가 확인할 때까지 유지된다.

**동작:** `::CreateEventA(nullptr, TRUE, FALSE, nullptr)` — 두 번째 인자 TRUE가 수동 리셋이다. `ReadFile`이 `ERROR_IO_PENDING`을 주면 `WaitForSingleObject(overlapped.hEvent, timeoutMs)`로 기다리고, 타임아웃이면 `CancelIoEx`로 취소한다. 이벤트는 요청마다 새로 만들고 `ScopedOverlapped` 소멸자가 닫는다.

**예시:**
```cpp
const DWORD waitResult = ::WaitForSingleObject(overlapped.hEvent, timeoutMs);
if (waitResult != WAIT_OBJECT_0) { /* 취소 경로 */ }
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:27` — 대기
- `src/maro_ipc/src/NamedPipe.cpp:60` — 이벤트 생성

**증거:**
- §5.3, §5.3.4

**함정:** 같은 이벤트를 여러 요청에 재사용하면 이전 요청의 신호가 남아 새 요청이 즉시 완료된 것처럼 보인다. 요청마다 새 이벤트가 안전하다.

**교훈:** 신호 객체의 재사용은 리셋 책임을 만든다. 수명이 짧으면 새로 만드는 편이 단순하다.

#### `ERROR_IO_PENDING`

**직관:** "요청을 받았고 아직 진행 중"이라는 오류 코드. 비동기 호출에서는 실패가 아니라 정상 경로다.

**동작:** `ReadFile`이 FALSE를 돌려줄 때 `GetLastError()`가 `ERROR_IO_PENDING`이면 대기로 진행하고, **그 외의 오류라면 대기조차 없이 false**를 돌려준다. 그 "그 외"에 `ERROR_BROKEN_PIPE`가 포함된다 — 상대가 이미 닫은 뒤에 읽기를 걸면 즉시 이 오류가 나므로 타임아웃 없이 끊김을 알아챈다. 감시자의 `kDidNotWaitMs`(폴링 주기의 1/5) 판정이 이 성질에 기댄다.

**예시:**
```cpp
if (!::ReadFile(pipe, buf, n, &read, &ov)) {
    const DWORD err = ::GetLastError();
    if (err != ERROR_IO_PENDING) return false;   // ERROR_BROKEN_PIPE 포함 → 즉시 끊김 판정
}
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:78-86` — 분기와 주석
- `src/maro_sentinel/main.cpp:42` — `kDidNotWaitMs`

**증거:**
- §5.3, §5.3.4, §11.4

**함정:** `ERROR_IO_PENDING`을 실패로 처리하면 비동기 경로가 통째로 죽고 모든 읽기가 실패한다. 오류 코드의 의미를 확인하지 않은 전형적 버그다.

**교훈:** 비동기 API에서는 "실패 반환 + 특정 오류 코드 = 성공"인 규약이 흔하다. 코드값으로 분기한다.

#### `GetOverlappedResult`

**직관:** 비동기 요청의 결과(전송 바이트 수, 완료 여부)를 회수하는 함수. `bWait`가 TRUE면 완료될 때까지 기다린다.

**동작:** 두 자리에서 쓴다 — (1) 대기가 성공한 뒤 결과 회수(`bWait=FALSE`), (2) `CancelIoEx` 성공 뒤 취소 완료 대기(`bWait=TRUE`). (2)가 저장소에서 "모든 대기에 타임아웃" 규칙의 유일한 예외이며, 커널이 반드시 `ERROR_OPERATION_ABORTED`로 완료시키므로 구조적으로 유한하다(F-026).

**예시:**
```cpp
if (::CancelIoEx(handle, &overlapped)) {
    DWORD bytes = 0;
    ::GetOverlappedResult(handle, &overlapped, &bytes, TRUE);   // 의도된 예외
}
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:29-52` — 취소 후 완료 대기와 주석
- `src/maro_ipc/src/NamedPipe.cpp:33-38` — 결과 회수

**증거:**
- §5.3, §5.3.4, §11.4, §10.8
- F-026

**함정:** `bWait=FALSE`로 부르고 완료 전이면 IO_INCOMPLETE 오류가 온다. 그것을 실패로 처리하면 정상 흐름이 끊긴다.

**교훈:** 결과 회수 함수의 대기 인자는 "지금 결과가 있는가"와 "끝날 때까지 기다릴까"를 가른다. 호출 맥락에 맞게 고른다.

#### `CancelIoEx`

**직관:** 지정한 핸들의 대기 중 I/O를 취소해 달라고 커널에 **요청**하는 함수. 즉시 돌아오며 실제 취소는 나중에 완료된다.

**동작:** 타임아웃이 나면 `CancelIoEx(handle, &overlapped)`를 부른다. 성공하면 `GetOverlappedResult(bWait=TRUE)`로 완료를 기다려 `OVERLAPPED`의 수명을 지킨다. 실패하고 `ERROR_NOT_FOUND`면(걸린 I/O가 없음) 기다리지 않는다 — 영원히 신호되지 않을 이벤트를 붙잡게 되기 때문이다. 이 두 분기가 use-after-free와 무한 대기를 동시에 막는다.

**예시:**
```cpp
if (::CancelIoEx(handle, &overlapped)) {
    ::GetOverlappedResult(handle, &overlapped, &bytes, TRUE);
}   // ERROR_NOT_FOUND면 기다리지 않는다
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:29-52` — 취소·대기·예외 분기

**증거:**
- §5.3, §5.3.4, §11.4
- F-026

**함정:** 브리프 원본은 `CancelIoEx`가 동기라고 가정했다. 문서를 다시 읽고서야 "요청만 한다"는 것이 드러났고, 그 가정이 바로 use-after-free였다.

**교훈:** "취소"는 대부분 비동기다. 취소 이후의 완료까지가 한 트랜잭션이다.

#### `ERROR_OPERATION_ABORTED`

**직관:** 취소된 I/O가 완료될 때 커널이 주는 상태 코드. "실패"가 아니라 "취소가 끝났다"는 뜻이다.

**동작:** `CancelIoEx` 뒤 `GetOverlappedResult(bWait=TRUE)`가 반드시 이 코드로 완료된다는 보장이 있어 그 대기가 구조적으로 유한하다. 그래서 그 자리에 타임아웃을 넣지 않는 것이 맞고, 코드 주석이 `**"의도된 예외, 지우지 말 것"**`으로 그 판단을 고정한다.

**예시:**
```
ReadFile → ERROR_IO_PENDING → 타임아웃 → CancelIoEx → 커널이 ERROR_OPERATION_ABORTED로 완료
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:40-52` — 예외 주석과 대기

**증거:**
- §5.3, §5.3.4

**함정:** 이 코드를 일반 오류로 로그에 남기면 정상적인 타임아웃마다 오류가 찍혀 진짜 문제가 묻힌다.

**교훈:** 오류 코드 중에는 "설계된 결과"가 있다. 로그 레벨을 그에 맞춰 나눈다.

#### `ERROR_NOT_FOUND`

**직관:** `CancelIoEx`가 취소할 I/O를 찾지 못했다는 뜻. 요청이 이미 완료됐거나 애초에 걸려 있지 않았다는 신호다.

**동작:** 이 경우 `GetOverlappedResult(bWait=TRUE)`를 부르면 **영원히 신호되지 않을 이벤트**를 기다리게 되므로 부르지 않는다. 코드가 `CancelIoEx`의 반환값으로 분기해 이 상황을 걸러 낸다. 타임아웃과 완료가 경합하는 순간에 실제로 발생할 수 있는 경로다.

**예시:**
```cpp
if (!::CancelIoEx(handle, &overlapped)) {
    // ERROR_NOT_FOUND: 걸린 I/O 없음 → 기다리지 않는다
}
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:36-44` — 분기와 주석

**증거:**
- §5.3, §5.3.4

**함정:** "취소를 불렀으니 무조건 기다린다"는 코드가 이 경로에서 교착한다. 경합 구간이 좁아 테스트로 잡기 어렵다.

**교훈:** 경합이 만드는 드문 경로는 반환값 분기로 미리 막는다. 재현이 어려울수록 코드로 닫아 둔다.

#### `SetNamedPipeHandleState`

**직관:** 이미 열린 파이프 핸들의 모드를 바꾸는 함수. 클라이언트가 읽기 모드를 메시지로 전환할 때 쓴다.

**동작:** `CreateFile`로 연 클라이언트 핸들은 서버가 메시지 타입이어도 **바이트 읽기 모드**로 시작한다(F-110). 그대로 두면 큐에 두 메시지가 쌓였을 때 한 번의 `ReadFile`이 둘을 이어 붙여 돌려주고 `decodeMessage`가 깨진다. 그래서 접속 직후 `DWORD mode = PIPE_READMODE_MESSAGE; ::SetNamedPipeHandleState(pipe_, &mode, nullptr, nullptr);`를 부른다 — 길이 프리픽스를 쓰지 않는 근거가 여기서 완성된다.

**예시:**
```cpp
DWORD mode = PIPE_READMODE_MESSAGE;
if (!::SetNamedPipeHandleState(pipe_, &mode, nullptr, nullptr)) { /* 실패 처리 */ }
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:228-236` — 모드 전환과 실패 처리
- `src/maro_ipc/src/Message.cpp` — 경계가 보존돼야 하는 `decodeMessage`

**증거:**
- §5.3, §5.3.4
- F-110

**함정:** 메시지가 하나씩만 오가는 동안에는 바이트 모드여도 멀쩡히 동작한다. 두 개가 쌓이는 순간에만 깨져 뒤늦게 드러난다.

**교훈:** "기본값이 내 기대와 같은가"를 문서에서 확인한다. 서버 설정이 클라이언트에 전파된다는 보장은 없다.

#### `ERROR_BROKEN_PIPE`

**직관:** 상대가 파이프를 닫았다는 오류. 프로세스가 죽으면 커널이 핸들을 닫으므로 크래시도 이 신호로 전달된다.

**동작:** 읽기가 즉시 이 오류로 실패하면 감시자는 "메시지 없이 끊김"으로 판정한다 — Windows가 주는 신호라 임의의 타임아웃 값이 설계에 들어가지 않는다. 테스트는 `clientClosed`/`orderingForced` 플래그로 "클라이언트가 닫은 **뒤에** 서버가 읽기를 건다"는 순서를 강제해 이 즉시 감지 경로를 검증한다(F-198). 한 번의 관측으로 단정하지 않고 빠른 실패 3연속(`kFastFailuresMeaningDisconnect`)을 요구한다.

**예시:**
```cpp
// 상대가 닫은 뒤의 ReadFile → 즉시 FALSE, GetLastError() == ERROR_BROKEN_PIPE
// → 대기 없이 false 반환 → 감시자가 "끊김"으로 카운트
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:78-86` — 즉시 실패 경로
- `src/maro_sentinel/main.cpp:42-50` — 3연속 판정 상수
- `tests/ipc/test_named_pipe.cpp:104-130` — 순서 강제 검증

**증거:**
- §5.3, §5.3.4, §8.2, §8.2.3, §11.4
- F-198

**함정:** 깨진 메시지나 8KB 초과(`ERROR_MORE_DATA`)도 즉시 false를 준다. 한 번의 빠른 실패를 끊김으로 단정하면 오판한다.

**교훈:** OS가 주는 신호는 믿되, 같은 증상을 내는 다른 원인을 세어 본다. 3연속이 그 방어다.

#### `ERROR_PIPE_CONNECTED`

**직관:** `ConnectNamedPipe`가 "이미 클라이언트가 붙어 있다"고 알리는 코드. 실패가 아니라 성공으로 처리해야 한다.

**동작:** 서버가 `ConnectNamedPipe(pipe_, &overlapped)`를 부르기 전에 클라이언트가 먼저 `CreateFile`로 붙었을 수 있다. 그때 호출은 FALSE를 돌려주고 `GetLastError()`가 `ERROR_PIPE_CONNECTED`가 된다. 코드는 이 경우를 접속 성공으로 간주하고 `connected_ = true`로 표시한다.

**예시:**
```cpp
const BOOL immediate = ::ConnectNamedPipe(pipe_, &scoped.overlapped);
if (!immediate && ::GetLastError() == ERROR_PIPE_CONNECTED) { connected_ = true; return true; }
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:149-162` — 분기와 주석

**증거:**
- §5.3, §5.3.4

**함정:** 이 코드를 오류로 처리하면 "클라이언트가 빨랐을 때만 접속 실패"라는 타이밍 의존 버그가 된다.

**교훈:** 경합이 있는 API는 "상대가 먼저였을 때"의 반환을 문서에서 찾아 성공 경로에 넣는다.

#### `ERROR_FILE_NOT_FOUND`

**직관:** 클라이언트가 파이프를 열려는데 서버가 아직 만들지 않았다는 오류. 재시도로 해결되는 일시적 상태다.

**동작:** Maya가 감시자를 띄운 직후 접속을 시도하면 감시자가 아직 `CreateNamedPipe`를 부르기 전일 수 있다. 클라이언트는 `ERROR_FILE_NOT_FOUND`와 `ERROR_PIPE_BUSY`만 재시도 대상으로 보고 20ms 간격으로 다시 시도하며, 그 외 오류는 즉시 false를 돌려준다. 전체 접속 대기 상한은 15초(좀비 방지)다.

**예시:**
```cpp
if (err != ERROR_FILE_NOT_FOUND && err != ERROR_PIPE_BUSY) return false;   // 재시도 대상 아님
std::this_thread::sleep_for(std::chrono::milliseconds(20));
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:236-246` — 재시도 조건
- `tests/ipc/test_named_pipe.cpp:221-227` — 서버 없을 때 깔끔히 실패

**증거:**
- §5.3, §5.3.4, §11.4

**함정:** 모든 오류를 재시도하면 "서버가 영영 없음"과 "아직 없음"을 구분하지 못해 15초를 항상 소모한다. 재시도 대상을 좁혀야 빨리 실패한다.

**교훈:** 재시도 정책은 오류 코드별로 정한다. "일시적"과 "영구적"을 나누는 것이 정책의 핵심이다.

#### `ERROR_PIPE_BUSY`

**직관:** 파이프 인스턴스가 이미 다른 클라이언트에 물려 있다는 오류. 인스턴스 수가 1이므로 동시 접속 시 나타난다.

**동작:** `ERROR_FILE_NOT_FOUND`와 같은 취급을 받아 20ms 간격 재시도 대상이다. 대기 전용 API로 기다리는 방법도 있지만, Maro는 자체 재시도 루프로 통일해 "모든 대기에 타임아웃" 규칙 아래 둔다. PID별 파이프라 실제로는 거의 나지 않는다.

**예시:**
```
클라이언트 A 접속 중 → 클라이언트 B가 CreateFile → ERROR_PIPE_BUSY → 20ms 뒤 재시도
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:236-246` — 재시도 분기

**증거:**
- §5.3, §5.3.4

**함정:** 대기 전용 API의 타임아웃은 파이프 생성 시 준 기본 타임아웃과 얽힌다. 자체 루프가 더 예측 가능하다.

**교훈:** 라이브러리가 제공하는 대기 함수보다 "우리가 통제하는 대기"가 규칙을 지키기 쉽다.

#### `ERROR_MORE_DATA`

**직관:** 메시지가 읽기 버퍼보다 커서 일부만 읽혔다는 오류. 나머지 조각은 큐에 남는다.

**동작:** `kBufferSize = 8192`가 파이프 버퍼이자 한 번의 읽기 버퍼다. JSON 메시지가 이보다 크면 `readOneMessage`가 false를 돌려주고 나머지가 큐에 남는다 — 버퍼를 키우거나 이어붙이기를 넣을 자리로 남겨 뒀다(C-2). 감시자는 이 실패도 "빠른 실패"로 세므로 3연속 규칙이 오판을 막는다.

**예시:**
```cpp
// kBufferSize = 8192; 그보다 큰 메시지는 ERROR_MORE_DATA로 실패하고
// 나머지 조각은 큐에 남는다(C-2가 키우거나 이어붙이기를 넣을 자리)
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:10-16` — 버퍼 크기와 주석
- `src/maro_sentinel/main.cpp:50` — 3연속 판정

**증거:**
- §5.3, §5.3.4, §5.4

**함정:** 조각이 큐에 남으므로 다음 읽기가 잘린 JSON을 받아 계속 실패한다. 복구하려면 남은 조각을 비우거나 재접속해야 한다.

**교훈:** 버퍼 상한은 프로토콜의 상한이다. 초과 시의 상태(조각이 남음)까지 문서에 적는다.

#### `DisconnectNamedPipe`

**직관:** 서버가 클라이언트 연결을 강제로 끊는 함수. **상대가 아직 읽지 않은 데이터를 버린다**는 것이 핵심 성질이다.

**동작:** `NamedPipeServer::close()`가 `connected_`일 때 이 함수를 부른다. 그래서 "`sendMessage()` 직후 `close()`"는 그 마지막 답장을 잃을 수 있다 — 실측 200회 중 86회째에 클라이언트 `receiveMessage`가 false였다(F-109). 규칙은 "서버는 상대가 파이프를 닫을 때까지 기다린 뒤 닫는다"이며, 감시자가 실제로 그렇게 한다. 반대 방향(클라이언트가 보내고 바로 닫기)은 안전하다 — 클라이언트 `close()`는 `CloseHandle`뿐이라 이미 들어간 데이터는 서버가 마저 읽는다.

**예시:**
```cpp
void NamedPipeServer::close() {
    // 주의(실측): DisconnectNamedPipe는 상대가 아직 안 읽은 데이터를 버린다(MSDN)
    if (connected_) ::DisconnectNamedPipe(pipe_);
    ...
}
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:178-193` — `close()`와 함정 주석
- `tests/ipc/test_named_pipe.cpp:174-215` — 마지막 메시지 보존 검증

**증거:**
- §5.3, §5.3.4, §8.2.3, §8.4, §11.4, §10.8
- F-109

**함정:** 이 손실은 확률적이다. 한 번 테스트해 보고 "괜찮다"고 결론 내리면 200번째쯤에 사용자에게서 드러난다.

**교훈:** 확률적 손실은 반복 실행으로만 보인다. MSDN의 한 문장을 읽었다면 반복 테스트로 확인한다.

#### `FlushFileBuffers`

**직관:** 파이프에 쓴 데이터를 상대가 다 읽을 때까지 기다리는 함수. `DisconnectNamedPipe` 전에 부르면 손실을 줄일 수 있다.

**동작:** MSDN이 권하는 순서는 `FlushFileBuffers` → `DisconnectNamedPipe`다. 다만 이 함수는 상대가 읽을 때까지 **무기한** 기다리므로 "모든 대기에 타임아웃" 규칙과 충돌한다. Maro는 대신 "서버는 상대가 닫을 때까지 기다렸다가 닫는다"는 프로토콜 규칙으로 문제를 해결해 무기한 대기를 들이지 않았다.

**예시:**
```
MSDN 권장: FlushFileBuffers(pipe) → DisconnectNamedPipe(pipe)
Maro 선택: 상대가 close 할 때까지 읽기 루프 → 그 뒤 close   (무기한 대기 없음)
```

**관련 코드:**
- `src/maro_ipc/src/NamedPipe.cpp:178-193` — 대안 규칙을 적은 `close()`
- `src/maro_sentinel/main.cpp:147-200` — 상대가 닫을 때까지 도는 수신 루프

**증거:**
- §5.3

**함정:** `FlushFileBuffers`에 타임아웃이 없다는 점이 좀비의 원인이 될 수 있다. 편리해 보이는 API가 규칙을 깨는 경우다.

**교훈:** 라이브러리의 권장 순서가 우리 제약(무기한 대기 금지)과 부딪히면 프로토콜로 우회한다.

#### `DisconnectNamedPipe` 데이터 손실 86/200

**직관:** "서버가 답장 직후 끊으면 답장이 사라질 수 있다"를 200회 반복 실행으로 실측한 수치 — 86회째에 처음 재현됐다.

**동작:** 테스트는 서버가 `sendMessage` 직후 `close()`하는 시나리오를 반복해 클라이언트의 `receiveMessage`가 false가 되는 순간을 찾았다. 확률적이라 한두 번으로는 안 보인다. 이 실측이 §10.8 규칙 "서버는 답장 직후 `close()`하지 않는다"의 근거이고, 현재 서버는 상대가 닫을 때까지 기다린다.

**예시:**
```
200회 반복 → 86회째에 클라이언트 receiveMessage == false
→ 규칙: 서버는 sendMessage 직후 close 하지 않는다
```

**관련 코드:**
- `tests/ipc/test_named_pipe.cpp:174-215` — 마지막 메시지 보존 테스트
- `src/maro_ipc/src/NamedPipe.cpp:178-193` — 그 결과를 적은 주석

**증거:**
- §8.2, §8.2.3, §8.4, §10.8
- F-109

**함정:** 실패율이 낮은 경합은 CI에서 간헐 실패로 나타나 "플래키"로 치부되기 쉽다. 실제로는 진짜 손실이다.

**교훈:** 확률적 결함은 횟수로 증명한다. "200회 중 86회째"라는 숫자가 규칙보다 설득력이 있다.

#### 상대가 닫을 때까지 대기

**직관:** 서버 종료 규칙 — 답장을 보낸 뒤 바로 끊지 않고, 클라이언트가 파이프를 닫는 것을 확인한 다음에 닫는다.

**동작:** 감시자의 수신 루프는 킬 이벤트·첫 메시지 타임아웃·절대 수명(12시간)을 확인하며 `receiveMessage(500ms)`를 반복한다. 클라이언트가 닫으면 읽기가 `ERROR_BROKEN_PIPE`로 즉시 실패하고, 그 빠른 실패가 3연속이면 끊김으로 판정해 루프를 나간다. 그때 비로소 `close()`가 불리므로 `DisconnectNamedPipe`가 버릴 데이터가 없다.

**예시:**
```
서버: sendMessage(reply) → 계속 read → BROKEN_PIPE 3연속 → 종료 → close()
클라이언트: read(reply) → close()
```

**관련 코드:**
- `src/maro_sentinel/main.cpp:147-205` — 수신 루프와 종료 조건
- `src/maro_ipc/src/NamedPipe.cpp:178-193` — 그 순서를 전제한 `close()`

**증거:**
- §8.2, §8.2.3, §10.8
- F-109

**함정:** "빨리 정리하자"는 본능이 이 규칙을 깬다. 리소스를 늦게 놓는 것이 옳은 드문 경우다.

**교훈:** 종료 순서는 프로토콜의 일부다. 누가 먼저 닫는지를 규칙으로 정해 양쪽 코드에 적는다.

#### 물려받은 stdout 파이프

**직관:** 자식 프로세스가 부모의 stdout 핸들을 물려받으면, 부모(또는 테스트 러너)는 그 파이프가 닫힐 때까지 읽기를 마치지 못한다. 좀비가 러너를 붙잡는 경로다.

**동작:** 실측 사례 — 실패한 감시자가 30초 더 살며 CPU 한 코어를 태웠고, ctest는 물려받은 stdout 파이프가 닫힐 때까지 30초를 더 기다렸다(F-118). 원인은 정리를 성공 경로에만 뒀던 것이고, `SentinelProcessGuard` 등 RAII 가드로 모든 경로에서 `TerminateProcess`·`CloseHandle`을 부르게 고쳤다. 감시자 자체는 콘솔 없이(`CREATE_NO_WINDOW`) 띄워 이 문제를 줄인다.

**예시:**
```
ctest → 테스트 프로세스 → 감시자(stdout 상속)
테스트가 끝나도 감시자가 살아 있으면 파이프가 안 닫혀 ctest가 대기
```

**관련 코드:**
- `tests/ipc/test_sentinel_process.cpp:60-90` — RAII 가드
- `src/maro_ipc/src/JobEscape.cpp:40-60` — `CREATE_NO_WINDOW` spawn

**증거:**
- §8.2, §8.2.3
- F-118

**함정:** 핸들 상속은 기본이 켜져 있는 경우가 많다(`bInheritHandles=TRUE`). 필요 없으면 끄는 것이 좀비 영향을 줄인다.

**교훈:** 자식에게 무엇을 물려주는지가 부모의 종료 시점을 정한다. 상속 목록을 의식적으로 정한다.
