<!-- win-dbg-01 Windows › 디버깅 (19개) 2026-09-24 -->

#### ASan

**직관:** AddressSanitizer — 컴파일러가 메모리 접근을 계측해 use-after-free·오버플로를 잡아 주는 검출기. Maro는 `maroPointCloud` 드로우 오버라이드의 UAF를 쫓다가 이 빌드를 만들었다.

**동작:** `/fsanitize=address`로 컴파일하면 힙·스택·전역 접근이 계측되고 `clang_rt.asan_dynamic` 런타임이 `malloc/free`와 `RtlAllocateHeap/RtlFreeHeap`(`windows_hook_rtl_allocators`)을 가로채 red zone·quarantine으로 검출한다. Maya에서 쓰려면 런타임을 **Maya 초기화 전에** 프로세스에 넣어야 한다 — mayapy라면 `maya.standalone.initialize()`보다 먼저 `ctypes.CDLL(...)`. 늦게 로드하면 리포트 없이 그냥 죽는다. `tools/crashtriage/run-asan-tests.ps1`이 그 순서를 자동화한다.

**예시:**
```python
import ctypes
ctypes.CDLL(r"...\clang_rt.asan_dynamic-x86_64.dll")   # 반드시 먼저
import maya.standalone; maya.standalone.initialize()
```

**관련 코드:**
- `CMakeLists.txt:45-60` — `MARO_ASAN` 옵션과 플래그 조정
- `tools/crashtriage/run-asan-tests.ps1` — 선로드 순서 자동화

**증거:**
- §2, §3.2, §9.5, §11.4, §10.10
- F-012, F-232

**함정:** 정작 그 UAF는 ASan이 아니라 콜백 카운터 계측이 잡았다. 도구가 만능이 아니며, 계측 지점을 손으로 넣는 것이 더 빠를 때가 있다.

**교훈:** 도구를 세팅하는 비용과 얻는 정보를 저울질한다. "Maya 초기화 전에 끼어들 수 있는가"가 이 도구의 가능 여부를 갈랐다.

#### 미니덤프

**직관:** Windows가 크래시 시 남기는 압축된 프로세스 스냅샷(`.dmp`). 스레드·모듈·예외·메모리 스트림이 들어 있다.

**동작:** 구조는 `MINIDUMP_HEADER{Signature "MDMP", Version, NumberOfStreams, StreamDirectoryRva, …}` → `MINIDUMP_DIRECTORY[]{StreamType, Location{DataSize, Rva}}` → 스트림별 구조다. `parse_minidump.py`가 `struct`로 직접 읽어 예외 코드·폴트 모듈·읽기/쓰기 대상·`maro.mll` 베이스를 뽑고, 그 결과를 `symbolize.py`에 넘긴다. 디버거 없이 파싱하므로 CI나 사용자 머신에서도 돌릴 수 있다.

**예시:**
```python
MDMP = b"MDMP"
if buf[:4] != MDMP: raise SystemExit("not a minidump")
```

**관련 코드:**
- `tools/crashtriage/parse_minidump.py:8-40` — 시그니처와 헤더 파싱
- `tools/crashtriage/symbolize.py:35-75` — 심볼화 단계

**증거:**
- §2, §9.5, §11.4

**함정:** 미니덤프는 기본적으로 전체 메모리를 담지 않는다. 힙 손상 조사에는 Memory64List가 있는 풀 덤프가 필요할 수 있다.

**교훈:** 덤프 포맷을 직접 파싱할 수 있으면 디버거 없는 환경에서도 1차 분류가 가능하다. 구조는 헤더 → 디렉터리 → 스트림 셋뿐이다.

#### 심볼라이저

**직관:** 주소를 함수명·파일·줄로 바꿔 주는 도구. 덤프에서 뽑은 RVA가 사람이 읽을 수 있는 위치가 되는 단계다.

**동작:** `tools/crashtriage/symbolize.py`가 `dbghelp.dll`을 ctypes로 열어 `SymSetOptions → SymInitialize → SymLoadModuleEx → SymFromAddr/SymGetLineFromAddr64` 순으로 부른다. 덤프의 모듈 크기가 현재 빌드와 같을 때만 결과가 맞다 — 다른 빌드의 PDB로 심볼화하면 엉뚱한 함수가 나온다. 프로세스 안에서 잡는 `boost::stacktrace`와 역할이 다르다(후자는 크래시하지 않은 조용한 실패용).

**예시:**
```bash
python tools/crashtriage/symbolize.py out/build/Release/maro.mll 0x7f3c
# MaroPointCloudNode::draw+0x2a  MaroPointCloudNode.cpp:312
```

**관련 코드:**
- `tools/crashtriage/symbolize.py:1-75` — 전체 흐름
- `tools/crashtriage/parse_minidump.py` — RVA 공급

**증거:**
- §2, §9.5

**함정:** PDB가 빌드와 짝이 맞지 않으면 심볼화가 "성공"하면서 틀린 함수를 준다. 빌드 해시나 모듈 크기로 짝을 확인한다.

**교훈:** 심볼화는 PDB와 바이너리의 짝이 맞을 때만 의미가 있다. 짝을 검증하는 단계를 도구에 넣는다.

#### gflags

**직관:** Windows의 전역 플래그 도구. 레지스트리에 프로세스별 디버깅 설정(힙 검증 등)을 심는다. **시스템 전역**이라 Maro는 쓰지 않는다.

**동작:** `gflags /p /enable maya.exe /full`처럼 켜면 그 이름의 모든 프로세스에 적용된다. 사용자의 Maya 실행 전체가 느려지고, 끄는 것을 잊으면 계속 남는다. Maro는 대신 ASan 전용 빌드 트리(`MARO_ASAN`)와 프로세스 내부 계측(콜백 카운터·스택 트레이스)을 택했다 — 사용자 시스템 설정을 건드리지 않는 방향이다.

**예시:**
```
gflags: 레지스트리(Image File Execution Options)에 설정 → maya.exe 전체에 적용
Maro:   별도 ASan 빌드 + 프로세스 내부 계측 → 이 빌드에서만
```

**관련 코드:**
- `CMakeLists.txt:45-60` — 대신 택한 ASan 빌드 옵션
- `src/maro_plugin/MaroStackTrace.cpp:37-80` — 프로세스 내부 계측

**증거:**
- §3.2, §9.5

**함정:** 전역 설정은 "잠깐 켜고 끄면 된다"고 생각하기 쉽지만, 크래시 조사 중에는 그 잠깐이 며칠이 된다. 잊고 남긴 설정이 다른 문제를 만든다.

**교훈:** 진단 수단은 가능한 한 프로젝트 안에 가둔다. 사용자 시스템을 바꾸는 도구는 마지막 수단이다.

#### PageHeap

**직관:** gflags가 켜 주는 힙 검증 모드. 할당마다 보호 페이지를 붙여 오버런을 즉시 잡지만 메모리·속도 비용이 크다.

**동작:** 전체 PageHeap은 할당마다 가드 페이지를 두므로 Maya처럼 할당이 많은 프로세스에서는 메모리가 폭증한다. 게다가 gflags와 마찬가지로 시스템 전역 설정이라 Maro는 피했다. 같은 목적(UAF·오버런 검출)을 ASan 빌드로 달성하되, 그마저도 Maya 초기화 전 선로드라는 제약이 있었다.

**예시:**
```
PageHeap(full): 할당마다 가드 페이지 → 즉시 검출, 메모리 수 배
ASan:           red zone + quarantine → 검출 + 상대적으로 가벼움(그래도 2~3배)
```

**관련 코드:**
- `CMakeLists.txt:45-60` — ASan 선택
- `tools/crashtriage/README.md` — 도구 선택 기준

**증거:**
- §3.2, §9.5

**함정:** Maya에 PageHeap을 켜면 실행 자체가 불가능할 정도로 느려지거나 메모리 부족으로 죽는다. "켜 보고 판단"이 어려운 도구다.

**교훈:** 검출 도구의 비용은 호스트 프로세스 규모에 비례한다. 큰 호스트에 얹히면 가벼운 도구부터 시도한다.

#### `dumpbin /dependents`

**직관:** MSVC 도구로 PE 파일이 임포트하는 DLL 목록을 출력한다. "이 DLL이 무엇을 요구하는가"를 확인하는 가장 빠른 방법이다.

**동작:** `maro_lidar/CMakeLists.txt`가 configure 단계에서 `dumpbin`을 찾아 `dumpbin /dependents <embree4.dll>`을 `execute_process`로 실행하고, 출력에 `tbb[0-9]*.dll`이 있으면 `FATAL_ERROR`로 빌드를 멈춘다 — TBB 기능이 켜진 Embree는 Maya의 `tbb12.dll`과 충돌해 `ERROR_PROC_NOT_FOUND`를 내기 때문이다(F-003). `dumpbin`이 PATH에 없으면 검사를 건너뛰되 경고를 남긴다.

**예시:**
```powershell
dumpbin /dependents embree4.dll | findstr /i tbb
# 출력이 있으면 잘못된 Embree 빌드 → configure 단계에서 FATAL_ERROR
```

**관련 코드:**
- `src/maro_lidar/CMakeLists.txt:36-60` — 도구 탐색·실행·판정
- `python/maroTechDiag.py:542-575` — 런타임 로드 경로 진단

**증거:**
- §3.3, §5.2, §5.2.1, §10.11
- F-003

**함정:** 런타임에 실제로 로드되는 DLL은 임포트 테이블과 다를 수 있다(지연 로드, `LoadLibrary`). 정적 목록과 실측 로드 경로를 둘 다 본다.

**교훈:** 의존성 사고는 빌드 시점에 검사할 수 있으면 빌드 시점에 막는다. configure 가드가 런타임 미스터리보다 싸다.

#### `0xC0000409` STATUS_STACK_BUFFER_OVERRUN

**직관:** 스택 쿠키 검사 실패나 `__fastfail` 호출 시 나오는 종료 코드(십진 3221226505). 이름과 달리 실제 버퍼 오버런이 아닌 경우가 많다.

**동작:** 레거시 `output.txt`에 `[ros2run]: Process exited with failure 3221226505`가 남아 있다. 같은 코드가 배치 모드에서 `QWidget`을 만들 때 나는 abort에서도 나타난다 — 라이브러리가 치명적 상태를 감지하면 `__fastfail`로 즉시 죽이기 때문이다. 예외 처리·소멸자가 돌지 않으므로 로그가 남지 않고, 저널의 "정상 종료 줄 부재"로만 크래시를 안다.

**예시:**
```
Process exited with failure 3221226505   (0xC0000409)
→ __fastfail 또는 /GS 쿠키 실패. 소멸자·atexit 실행 없음
```

**관련 코드:**
- `output.txt` — 레거시 로그
- `tests/maya/maroQtBatch.py:57-108` — 배치 QWidget abort 재현
- `src/maro_diag/src/JournalWriter.cpp:95-115` — 세션 종료 줄 부재로 판정

**증거:**
- §4.3, §4.3.8, §9.5

**함정:** 코드 이름을 믿고 버퍼 오버런을 찾으면 시간을 잃는다. 대부분은 라이브러리가 의도적으로 부른 `__fastfail`이다.

**교훈:** 종료 코드는 분류일 뿐 원인이 아니다. 같은 코드의 여러 원인을 목록으로 갖고 있어야 한다.

#### `0xC0000005`

**직관:** ACCESS_VIOLATION — 잘못된 주소를 읽거나 쓸 때 나는 가장 흔한 예외 코드. 널 포인터, 댕글링 포인터, 해제된 메모리 접근이 전부 여기로 모인다.

**동작:** 실측 사례: 브리프 원안대로 두 `RTC_GEOMETRY_TYPE_TRIANGLE` 씬에 `rtcCollide()`를 부르자 mayapy가 `0xC0000005`로 죽었다(F-024). Release 빌드라 Embree의 DEBUG 전용 사전조건 검사가 빠져 예외 대신 곧장 AV가 난 것이다. 덤프의 폴트 주소와 모듈을 보면 "누가 어디를 건드렸나"를 알 수 있다.

**예시:**
```
ExceptionCode 0xC0000005, ExceptionInformation[0]=1(쓰기), [1]=폴트 주소
→ 모듈이 embree4.dll이면 라이브러리 계약 위반을 의심
```

**관련 코드:**
- `tools/crashtriage/parse_minidump.py:30-60` — 예외 스트림 파싱
- `src/maro_lidar/src/CollisionEngine.cpp:116-175` — AV를 피해 만든 자체 SAT

**증거:**
- §5.2, §5.2.4, §9.5
- F-024

**함정:** AV의 폴트 주소가 작은 값(0x0~0xFFFF)이면 널 역참조, 임의의 큰 값이면 댕글링일 가능성이 높다. 주소의 "모양"이 첫 힌트다.

**교훈:** 예외 정보의 보조 필드(읽기/쓰기, 폴트 주소)까지 읽는다. 코드 하나보다 훨씬 많은 것을 알려 준다.

#### `dbgeng`

**직관:** Windows 디버거 엔진 — WinDbg의 심장부를 COM 인터페이스로 노출한 라이브러리. 심볼화·스택 워킹을 제공한다.

**동작:** `boost::stacktrace`의 MSVC 기본 백엔드가 이것을 COM으로 부르므로 플러그인이 `dbgeng ole32`를 링크한다. Windows SDK 시스템 라이브러리라 배포할 DLL이 없다. 링크 순서는 `maro_transform → maro_lidar → maro_diag → dbgeng ole32 → maro_ipc`다. 심볼화가 수백 ms 걸리므로 book 락 밖에서 부르고, 메인 스레드에서만 부른다 — Maya 워커에서 COM 아파트먼트를 건드리는 것이 안전하다는 근거가 없기 때문이다.

**예시:**
```cmake
target_link_libraries(${PROJECT_NAME} dbgeng ole32)   # boost::stacktrace의 WinDbg 백엔드
```

**관련 코드:**
- `src/maro_plugin/CMakeLists.txt:82-86` — 링크
- `src/maro_plugin/MaroStackTrace.cpp:60-80` — 메인 스레드·락 밖 정책

**증거:**
- §6.0, §6.7.1, §11.4, §10.1

**함정:** COM 기반이라 호출 스레드의 아파트먼트 상태에 영향을 받는다. 워커 스레드에서 부르면 초기화 상태에 따라 결과가 달라진다.

**교훈:** 심볼화는 비싸고 스레드에 민감하다. "언제·어느 스레드에서" 부를지를 정책으로 정한다.

#### `boost::stacktrace`

**직관:** 헤더 온리로 스택을 캡처·문자열화하는 Boost 라이브러리. 크래시하지 않고 조용히 실패하는 경로에서 "어디서 났는가"를 남긴다.

**동작:** devkit이 Boost 1.85를 `devkitBase/include/boost`로 제공하므로 헤더 온리 + `dbgeng.lib/ole32.lib` 링크만 필요하다. `MaroStackTrace.cpp`가 boost를 보는 **유일한 번역 단위**다. 캡처(`stacktrace()`)는 싸고 문자열화(`to_string`)가 비싸므로, 래치 확인은 락 안에서 하고 심볼화는 락 밖에서 한다. 정책은 세 조건을 모두 만족할 때만 뜨는 것 — 킬 스위치가 꺼져 있지 않고, 메인 스레드이며, 이 `siteTag`가 이번 세션에 아직 안 떴을 때.

**예시:**
```cpp
const boost::stacktrace::stacktrace trace(kSkipFrames, kMaxFrames);   // 캡처: 싸다
const std::string text = boost::stacktrace::to_string(trace);          // 심볼화: 비싸다(락 밖)
```

**관련 코드:**
- `src/maro_plugin/MaroStackTrace.cpp:1-98` — 유일한 TU와 정책
- `src/maro_plugin/CMakeLists.txt:82-86` — 링크

**증거:**
- §6.7, §6.7.1, §6.7.2, §11.4, §10.1

**함정:** 헤더 온리라고 의존성이 없는 것은 아니다 — 백엔드가 `dbgeng`/`ole32`를 요구한다.

**교훈:** 캡처와 심볼화를 분리하면 비싼 부분만 지연·제한할 수 있다. 진단은 그 분리로 실용적이 된다.

#### WinDbg 백엔드(dbgeng, COM)

**직관:** `BOOST_STACKTRACE_USE_WINDBG` — `dbgeng.h`로 심볼화하는 기본 백엔드. 함수명과 파일:줄을 주지만 느리고 COM을 쓴다.

**동작:** 프레임당 수 ms + COM 초기화 비용이 들고, 내부 정적 저장을 뮤텍스로 보호한다. 함수명·파일:줄은 PDB가 있어야 나온다. Maro의 정책 세 조건 중 "메인 스레드일 것"이 바로 이 COM 성격 때문이다. 대안 백엔드(BOOST_STACKTRACE_USE_BACKTRACE 등)는 Windows에서 선택지가 아니다.

**예시:**
```
캡처: 주소 배열 (빠름)
to_string: dbgeng COM 심볼화 (프레임당 수 ms, 메인 스레드에서만)
```

**관련 코드:**
- `src/maro_plugin/MaroStackTrace.cpp:60-90` — 메인 스레드 가드와 래치
- `src/maro_plugin/CMakeLists.txt:82-86` — dbgeng/ole32

**증거:**
- §6.7, §6.7.1, §6.7.2

**함정:** 매 프레임 실패하는 뷰포트 콜백에서 심볼화를 부르면 Maya가 얼어붙는다. `siteTag`당 세션 1회 래치가 그 방어다.

**교훈:** 비싼 진단은 빈도 제한이 필수다. "한 번만 남겨도 원인은 알 수 있다"가 래치의 근거다.

#### CRITICAL FAIL

**직관:** 수동 체크리스트에서 "이 단계에서 Maya가 죽는다"를 기록하는 표기. 2026-09-06 포인트클라우드 항목이 그 상태였다.

**동작:** §6-1 포인트클라우드의 경과: 09-06 CRITICAL FAIL(`createNode` 단독으로 크래시, 덤프 폴트가 ntdll 힙 관리자, 쓰기 대상 모듈이 매번 다름) → 09-07 원인은 `MFnPointArrayData::array()`가 돌려준 참조를 멤버로 들고 있던 댕글링(같은 스코프에서 즉시 소비하는 `boundingBox()`는 멀쩡했다) → 배열을 복사해 저장하도록 고쳐 해결(F-023).

**예시:**
```
09-06: createNode(maroPointCloud) → 크래시 (CRITICAL FAIL)
09-07: MFnPointArrayData::array() 참조 보관 → 복사 저장으로 수정 → PASS
```

**관련 코드:**
- `docs/maro-main-ui-manual-checklist.md` — §6-1 항목
- `src/maro_plugin/MaroPointCloudNode.cpp:241-390` — 수정된 draw 경로

**증거:**
- §9.4
- F-023

**함정:** 힙 손상은 크래시 지점이 버그 지점이 아니다. `createNode`에서 죽었다고 `createNode`를 파면 하루를 잃는다.

**교훈:** 수동 체크리스트에 실패 상태를 그대로 적어 두면 다음 날의 조사 출발점이 된다. "고쳤다"만 적으면 경위가 사라진다.

#### ntdll 힙 관리자 폴트

**직관:** 덤프의 폴트 지점이 `ntdll!RtlpAllocateHeap` 같은 힙 관리자 내부라는 것 — 우리 코드가 아니라 **힙 메타데이터가 이미 손상됐다**는 신호다.

**동작:** 09-06 크래시의 덤프가 정확히 이 모양이었다. 힙 손상은 손상시킨 코드와 터지는 코드가 다르므로, 덤프의 스택만 봐서는 원인을 알 수 없다. 이럴 때의 조사 방향은 "크래시 지점은 버그 지점이 아니다"를 전제로 ASan 빌드를 돌리거나, 최근 바뀐 메모리 수명 코드를 의심하는 것이다. 실제 원인은 `MFnPointArrayData::array()` 참조 보관이었다.

**예시:**
```
폴트 모듈: ntdll.dll (힙 관리자)
→ 우리 코드의 스택 프레임이 없음 → 손상 시점과 터진 시점이 다름
```

**관련 코드:**
- `tools/crashtriage/parse_minidump.py:30-60` — 폴트 모듈 식별
- `src/maro_plugin/MaroPointCloudNode.cpp:241-390` — 실제 원인 지점

**증거:**
- §9.4, §9.5
- F-023

**함정:** ntdll 폴트를 "OS 버그"나 "Maya 버그"로 결론 내리기 쉽다. 거의 항상 우리 쪽 힙 손상이다.

**교훈:** 폴트 모듈이 할당자 내부면 조사 전략을 바꾼다 — 스택 추적이 아니라 수명 검토다.

#### 쓰기 대상 모듈 가변

**직관:** 크래시할 때마다 쓰기 대상 주소가 속한 모듈이 달라지는 현상. 힙 손상의 전형적 지문이다.

**동작:** 09-06 덤프들에서 쓰기 대상이 매번 다른 모듈이었다. 손상된 힙 블록이 어느 할당에 재사용되느냐에 따라 피해자가 바뀌기 때문이다. 이 관측 덕에 "특정 코드의 널 역참조"가 아니라 "힙 손상"으로 방향을 잡을 수 있었다. `parse_minidump.py`가 예외 정보의 읽기/쓰기 구분과 대상 주소를 뽑아 준다.

**예시:**
```
1회차: 쓰기 대상이 Foundation.dll 영역
2회차: 쓰기 대상이 OpenMaya.dll 영역
→ 피해자가 랜덤 = 힙 손상
```

**관련 코드:**
- `tools/crashtriage/parse_minidump.py:30-60` — 예외 정보 파싱
- `docs/maro-main-ui-manual-checklist.md` — 관측 기록

**증거:**
- §9.4, §9.5
- F-023

**함정:** 재현 시도마다 증상이 달라 "환경 문제"로 오인하기 쉽다. 달라지는 것 자체가 단서다.

**교훈:** 증상의 **가변성**도 데이터다. 무엇이 일정하고 무엇이 변하는지를 적어 두면 분류가 좁혀진다.

#### `MayaCrashLog*.dmp`

**직관:** Maya가 크래시 시 사용자 임시 폴더에 남기는 미니덤프 파일. 조사 시작점이다.

**동작:** 파일명 패턴으로 찾아 `parse_minidump.py`에 넘기면 예외 코드·폴트 모듈·`maro.mll` 베이스가 나온다. 베이스를 알아야 폴트 주소에서 RVA를 계산해 `symbolize.py`로 넘길 수 있다. Maya가 자체 크래시 리포터를 띄우므로 사용자가 보고서를 보내면 덤프 경로를 함께 받을 수 있다.

**예시:**
```
%TEMP%\MayaCrashLog_2026.1_*.dmp
python tools/crashtriage/parse_minidump.py <dmp>   → 예외·모듈·베이스
```

**관련 코드:**
- `tools/crashtriage/parse_minidump.py:8-60` — 파싱
- `tools/crashtriage/README.md` — 사용 순서

**증거:**
- §9.5

**함정:** 덤프는 크래시 당시의 빌드와 짝이 맞아야 심볼화된다. 그 사이 다시 빌드했다면 PDB가 달라져 쓸 수 없다.

**교훈:** 크래시 조사는 "덤프 + 그때의 빌드 산출물"이 한 쌍이다. 조사 전에 빌드를 갈아엎지 않는다.

#### MDMP 스트림(ThreadList 3, ModuleList 4, Exception 6, SystemInfo 7, Memory64List 9)

**직관:** 미니덤프 안의 데이터 묶음들. 디렉터리의 StreamType 숫자로 구분하며, 필요한 스트림만 골라 읽으면 된다.

**동작:** ThreadList(3)에서 스레드와 컨텍스트, ModuleList(4)에서 로드된 모듈과 베이스·크기, `Exception`(6)에서 예외 코드·주소·읽기/쓰기, SystemInfo(7)에서 OS·CPU, Memory64List(9)에서 메모리 영역을 얻는다. `parse_minidump.py`는 이 중 ModuleList와 Exception을 주로 쓴다 — 폴트 모듈과 `maro.mll` 베이스가 심볼화에 필요한 전부이기 때문이다.

**예시:**
```
StreamType 4 (ModuleList)  → maro.mll 베이스·크기
StreamType 6 (Exception)   → 0xC0000005, 폴트 주소, 읽기/쓰기
RVA = 폴트주소 - 베이스     → symbolize.py
```

**관련 코드:**
- `tools/crashtriage/parse_minidump.py:8-60` — 디렉터리 순회와 스트림 선택

**증거:**
- §9.5

**함정:** 스트림 번호는 SDK 헤더의 enum 값이다. 헤더 없이 파싱하려면 값을 주석에 적어 둬야 다음 사람이 읽는다.

**교훈:** 바이너리 포맷을 직접 읽을 때는 "무엇을 읽지 않는지"도 정한다. 필요한 스트림만 읽으면 파서가 작아진다.

#### 예외 코드 `0xC0000005`(AV)

**직관:** NTSTATUS 체계의 액세스 위반 코드. 미니덤프의 ExceptionCode 필드에 그대로 들어 있다.

**동작:** `ExceptionInformation[0]`이 0이면 읽기, 1이면 쓰기, 8이면 DEP 위반이고 `[1]`이 폴트 주소다. Embree `rtcCollide` 크래시가 이 코드였다. 파서는 코드와 보조 정보를 함께 출력해 "무엇을 하다가"를 좁힌다.

**예시:**
```
ExceptionCode = 0xC0000005
ExceptionInformation = [1, 0x000001F4A2B30000]   → 쓰기, 그 주소
```

**관련 코드:**
- `tools/crashtriage/parse_minidump.py:30-60` — 코드와 보조 정보

**증거:**
- §9.5, §5.2.4

**함정:** 읽기/쓰기 구분을 무시하면 조사 범위가 두 배가 된다. 보조 정보를 꼭 출력한다.

**교훈:** 예외 코드는 첫 글자일 뿐이다. 함께 오는 정보가 문장을 완성한다.

#### `0xC0000374`(힙 손상)

**직관:** STATUS_HEAP_CORRUPTION — 힙 관리자가 자기 메타데이터의 불일치를 감지해 프로세스를 죽였다는 코드. AV보다 명확한 힙 손상 신호다.

**동작:** 이 코드가 보이면 "크래시 지점은 버그 지점이 아니다"가 확정적이다 — 힙 관리자가 나중에 검사하다 발견한 것이기 때문이다. 조사 방향은 ASan 빌드나 최근 수명 변경 검토이고, gflags/PageHeap은 시스템 전역이라 쓰지 않는다. 09-06 사례처럼 폴트 모듈이 ntdll인 AV(0xC0000005)도 같은 분류로 다룬다.

**예시:**
```
0xC0000374 → 힙 메타데이터 손상 감지 → 손상시킨 코드는 이미 지나감
대응: ASan 빌드로 재현 / 최근 버퍼·수명 변경 리뷰
```

**관련 코드:**
- `tools/crashtriage/parse_minidump.py:30-60` — 코드 분류
- `CMakeLists.txt:45-60` — ASan 빌드 옵션

**증거:**
- §9.5

**함정:** 이 코드는 손상 시점과 무관한 위치에서 나온다. 스택의 최상단 함수를 범인으로 지목하면 틀린다.

**교훈:** "감지 시점"과 "발생 시점"이 다른 오류 종류를 알고 있어야 조사 전략을 바꿀 수 있다.

#### `0xE06D7363`(C++ throw)

**직관:** MSVC가 C++ 예외를 던질 때 쓰는 SEH 코드("msc"의 ASCII가 들어 있다). 덤프에 이 코드가 보이면 크래시가 아니라 처리되지 않은 C++ 예외다.

**동작:** 미니덤프가 이 코드를 담고 있으면 원인은 메모리 오류가 아니라 예외가 경계를 넘어 샌 것이다. Maro는 Maya 콜백 경계마다 `catch(...)`를 두어 이 상황을 막지만, 그 대가로 "어디서 났는지"가 남지 않아 `boost::stacktrace` 진단을 넣었다. `/EHsc`가 없으면 예외 되감기가 없어 RAII 가드가 무의미해지므로 컴파일 옵션에 항상 들어 있다.

**예시:**
```
ExceptionCode = 0xE06D7363 → 처리되지 않은 C++ 예외 (메모리 오류 아님)
→ 어느 경계에서 샜는지 찾는다(콜백·스레드 진입점)
```

**관련 코드:**
- `tools/crashtriage/parse_minidump.py:30-60` — 코드 분류
- `CMakeLists.txt:40-45` — `/EHsc`
- `src/maro_plugin/MaroStackTrace.cpp:1-98` — 삼켜진 예외의 위치 남기기

**증거:**
- §9.5

**함정:** `catch(...)`로 전부 삼키면 이 코드도, 스택도 남지 않는다. 삼키되 기록하는 것이 규칙이다.

**교훈:** 예외를 경계에서 막는 설계는 진단 장치를 함께 요구한다. 조용한 실패가 크래시보다 찾기 어렵다.
