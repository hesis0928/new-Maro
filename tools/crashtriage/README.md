# 크래시 덤프 분류 도구 (디버거 설치 불필요)

Maya가 죽으면 `%TEMP%\MayaCrashLog<날짜>.<시각>.dmp`에 미니덤프가 남는다.
WinDbg/cdb가 없는 환경에서도 여기까지는 알아낼 수 있다.

## 1. 예외 종류와 폴트 위치

```powershell
python tools/crashtriage/parse_minidump.py "$env:TEMP\MayaCrashLog260906.1709.dmp"
```

출력: 예외 코드(`ACCESS_VIOLATION` 등), 폴트를 낸 명령이 있는 모듈,
읽기/쓰기 구분과 그 대상 주소가 어느 모듈에 속하는지, `maro.mll`의
로드 베이스/크기, 그리고 스레드 스택에서 발견되는 모듈 주소들.

**스택 스캔 결과는 근거로 쓰지 말 것.** 스택 메모리에서 모듈 범위에
들어가는 값을 전부 긁어모으는 방식이라 vtable 포인터·스필된 데이터·
오래전에 끝난 호출의 잔재가 섞인다. 진짜 콜스택이 아니다.

## 2. RVA를 함수명으로

덤프의 `maro.mll` **크기가 지금 빌드와 같을 때만** 의미가 있다
(`parse_minidump.py`가 찍는 `size=`와 현재 `SizeOfImage`를 비교).
다르면 다른 빌드라 RVA가 안 맞는다 — 현재 빌드로 재현부터 해야 한다.

```powershell
python tools/crashtriage/symbolize.py out/build/src/maro_plugin/Release/maro.mll 1A2B3 4C5D6
```

`dbghelp.dll`을 ctypes로 직접 써서 옆에 있는 `maro.pdb`를 읽는다.
`<unresolved>`가 나오면 그 RVA가 코드 영역이 아니거나 PDB가 안 맞는 것이다.

## 3. 프로세스 안에서 직접 스택 뜨기 (boost::stacktrace)

위 1/2번은 **이미 죽은 뒤**에 하는 사후 분석이다. 죽지 않고 조용히
삼켜지는 실패 -- 이 코드베이스에는 그런 자리가 많다(Maya 콜백 경계의
`catch (...)`가 예외를 밖으로 못 내보내므로 메시지만 남기고 넘어간다) --
는 덤프가 아예 안 생기므로 저 도구들로는 손도 못 댄다.

Maya devkit이 Boost 1.85를 통째로 들고 있고(`devkitBase/include/boost`),
거기 `boost/stacktrace`가 들어 있다. **이 환경에서 실제로 동작하는 것을
확인했다** -- 헤더 온리에 `dbgeng.lib ole32.lib` 링크만 추가하면 되고,
디버거 설치도 별도 DLL도 필요 없다. 함수명 + 파일:줄까지 나온다:

```
 2# innerFrame at ...\spike.cpp:7
 3# middleFrame at ...\spike.cpp:10
 4# main at ...\spike.cpp:13
```

`devkitBase/include`는 `pluginEntry.cmake`가 이미 include 경로에 넣으므로
`#include <boost/stacktrace.hpp>` 한 줄이면 잡힌다.

**적용됨(2026-09-07).** `BoadMaro::error()`가 실패 지점의 스택을 함께
남긴다. 구현은 `src/maro_plugin/MaroStackTrace.h/.cpp`(boost 헤더는 그 .cpp
하나에만 갇혀 있다), 계약은 `tests/maya/test_diag_stacktrace.py`가 고정한다.

읽는 법: `cmds.maroDiagQuery(index=0)[12]` (평평한 결과의 **맨 끝** 필드).
실제로 이렇게 나온다 --

```
 0# maro::BoadMaro::error at ...\MaroDiag.cpp:437     <- 늘 같은 자리(잡음)
 1# maro::MaroDiagEmitCommand::doIt at ...\MaroDiagCommands.cpp:181
 2# THcommandObject::doIt in OpenMaya
```

**뜨는 조건**(전부 만족해야 함 -- 심볼화가 비싸서 무조건 뜨면 안 된다):

  * `MARO_DIAG_STACKTRACE=0`이 아닐 것 (킬 스위치)
  * 메인 스레드일 것 -- dbgeng는 COM을 쓰는데 Maya 소유 워커 스레드에서
    COM 아파트먼트를 건드리는 게 안전하다는 근거가 없다. `MGlobal::display*`에
    이미 걸려 있는 것과 같은 가드다. 대가로 워커 스레드(Parallel Evaluation
    Manager 아래 compute() 등)의 실패는 스택을 못 얻는다.
  * 그 `siteTag`로 이번 세션에 아직 안 떴을 것 -- siteTag는 실패 지점마다
    고정된 상수라, 매 프레임 실패하는 뷰포트 콜백이 있어도 심볼화는 딱
    한 번이다. Maya가 얼어붙는 것을 막는 장치다.

저널에는 안 나간다(`JournalWriter::writeRecord`는 DiagRecord의 부분집합만
받는 계약이고 `DgContext`도 같은 이유로 인메모리 전용이다) -- 세션 안에서
패널이 읽는 용도다.

## 4. 힙 손상이 의심될 때

폴트 명령이 `ntdll.dll` 안이고 쓰기 접근이며 대상 주소가 매번 달라지면
힙 손상이다 — **크래시 지점은 버그 지점이 아니다.** 그때는 덤프를 더
파지 말고 `maro` 타겟만 `/fsanitize=address`로 빌드해서 손상을 내는
쓰기에서 직접 멈추게 한다(이 VS 설치에 ASan 런타임이 이미 있다).
시스템 전역 설정을 바꾸는 gflags/PageHeap은 쓰지 않는다.
