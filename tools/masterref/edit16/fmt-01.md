<!-- fmt-01 파일 포맷·인코딩 › 문자 인코딩 + JSON·JSON Lines + 3D·영상 포맷 (25개) 2026-09-24 -->

#### UTF-8 BOM(`﻿`)

**직관:** 파일 첫머리에 붙는 세 바이트 `EF BB BF` — "이 파일은 UTF-8"이라는 표식. JSON 파서와 Python은 무시하지만 셸 스크립트·MEL처럼 첫 줄이 의미를 갖는 곳에서는 문제가 된다.

**동작:** 이 리포에는 Visual Studio가 저장하며 남긴 BOM이 몇 파일에 있다 — `CMakeSettings.json`, `fix_dll.py`, `image_bridge_node.cpp`. 파이썬은 BOM을 무시하므로 문제없고, JSON도 파서가 건너뛴다. 새로 쓰는 소스는 전부 BOM 없는 UTF-8이며 MSVC `/utf-8` 옵션이 그 규칙을 전제한다. 레거시 `.cpp`에는 BOM과 함께 이모지가 "(Robot)" 같은 텍스트로 대체된 흔적이 남아 있다 — CP949 빌드에서 이모지가 깨지던 시절의 수정이다.

**예시:**
```
hexdump -C CMakeSettings.json | head -1
00000000  ef bb bf 7b 0a ...      ← BOM 뒤에 '{'
```

**관련 코드:**
- `CMakeSettings.json` — VS가 남긴 BOM
- `src/image_bridge/src/image_bridge_node.cpp` — 레거시 BOM
- `Maro_DebugUtility/UnicodeUtil.h:8-56` — 출력 파일에 BOM을 붙이던 레거시 유틸

**증거:**
- §3.4, §3.8, §4.4

**함정:** BOM이 붙은 `.mel`을 `source`하면 첫 토큰 앞에 보이지 않는 문자가 붙어 구문 오류가 난다. 편집기가 조용히 붙이는 경우가 있으니 저장 설정을 확인한다.

**교훈:** 인코딩 표식은 "누가 읽는가"에 따라 무해하거나 치명적이다. 소비자 목록을 알고 규칙(BOM 없는 UTF-8)을 하나로 정한다.

#### UTF-8

**직관:** 가변 길이 유니코드 인코딩 — ASCII는 1바이트 그대로, 그 외는 2~4바이트이며 모든 연속 바이트가 0x80 이상이다. 이 프로젝트의 소스·로그·파일 이름 규약이다.

**동작:** 새 소스는 전부 BOM 없는 UTF-8이고 MSVC `/utf-8`이 소스·실행 문자셋을 모두 UTF-8로 고정한다. 그렇게 하지 않으면 MSVC 기본 코드페이지 949로 읽어 한국어 주석이 C4819 경고와 함께 깨진다. Maya API에서는 `asChar()`가 로케일 코드페이지라 한글 사용자 폴더에서 모지바케가 나므로 `asUTF8()`/`setUTF8()`을 쓴다. 진단 JSON은 `nlohmann::json::dump`가 strict UTF-8을 요구하므로 잘못된 바이트를 U+FFFD로 바꾸는 `error_handler_t::replace`를 준다.

**예시:**
```cpp
// MString → UTF-8 → MString, 로케일에 의존하지 않는다
const char* utf8 = value.asUTF8();
MString result; result.setUTF8(out.c_str());
```

**관련 코드:**
- `src/maro_plugin/MaroPythonBridge.cpp:50-67` — `asUTF8`/`setUTF8` 왕복
- `src/maro_diag/src/JournalWriter.cpp:16-22` — strict dump와 replace 핸들러
- `src/maro_plugin/CMakeLists.txt:100-108` — `/utf-8` 컴파일 옵션

**증거:**
- §3.8, §3.2, §4.4, §11.4
- F-014

**함정:** UTF-8이라고 해서 모든 바이트열이 유효한 것은 아니다. Windows API나 ROS 페이로드에서 온 문자열은 유효성 보장이 없어 그대로 JSON에 넣으면 dump가 던진다.

**교훈:** "UTF-8을 쓴다"는 규약에는 "유효하지 않은 입력을 어떻게 할 것인가"가 따라붙어야 한다. 대체(U+FFFD)든 거부든 정해 둔다.

#### CP949(EUC-KR)

**직관:** 한국어 Windows의 레거시 코드페이지. UTF-8 이전에 작성된 이 리포의 옛 소스들이 아직 이 인코딩으로 남아 있다.

**동작:** 루트의 레거시 파일들(`MaroCmd.cpp`, `rosSimCmd.cpp`, `src/ViewportStreamer.*`, 일부 `memo/*.txt`)은 CP949다. 빌드에 들어가지 않으므로 변환하지 않고 방치했고, 읽으려면 `iconv -f cp949 -t utf-8`을 거친다. `/utf-8` 옵션 도입 이전 파일이라는 것이 이들이 CP949인 이유다. 현재 빌드 대상 소스에는 CP949 파일이 없다.

**예시:**
```bash
iconv -f cp949 -t utf-8 memo/260526dev.txt | less
```

**관련 코드:**
- `MaroCmd.cpp` — CP949 레거시
- `src/ViewportStreamer.cpp` — CP949 레거시
- `memo/260526dev.txt` — CP949 메모

**증거:**
- §3.8, §3.2, §11.4
- F-014

**함정:** CP949 파일을 UTF-8로 열면 한글이 깨져 보이지만 편집기가 "고쳐서" 저장하면 원본이 영구히 손상된다. 빌드 밖 파일은 열지 않는 것이 가장 안전하다.

**교훈:** 인코딩이 섞인 리포에서는 "어느 파일이 어느 인코딩인가"를 문서에 적는다. 일괄 변환보다 목록이 싸다.

#### BOM

**직관:** Byte Order Mark — 원래는 UTF-16의 바이트 순서를 알리는 표식인데, UTF-8에서는 순서가 없으므로 "UTF-8입니다"라는 신호로만 쓰인다.

**동작:** 이 리포의 규칙은 "새 소스는 BOM 없는 UTF-8"이다. 예외는 VS가 저장하며 남긴 몇 파일뿐이고 파이썬·JSON 파서가 무시하므로 문제없다. 레거시 `UnicodeUtil.h`는 반대로 출력 파일에 BOM(`EF BB BF`)을 **붙였다** — 당시 뷰어들이 BOM 없는 UTF-8을 CP949로 오인했기 때문이다. 같은 유틸이 `MultiByteToWideChar(CP_UTF8)`로 wide 경로를 만들어 한글 경로에서도 `ofstream`이 열리게 했다.

**예시:**
```
BOM 있음:  EF BB BF  7B 22 ...      (VS가 저장한 JSON)
BOM 없음:            7B 22 ...      (이 프로젝트의 규칙)
```

**관련 코드:**
- `Maro_DebugUtility/UnicodeUtil.h:8-56` — BOM을 붙이고 wide 경로를 여는 레거시
- `CMakeSettings.json` — BOM이 남은 파일

**증거:**
- §3.8, §4.4

**함정:** BOM을 "있으면 좋은 것"으로 여겨 일괄 추가하면 셸·MEL·일부 링커 응답 파일이 깨진다. 소비자가 무시하는 것이 확인된 곳에만 둔다.

**교훈:** UTF-8에서 BOM은 필요가 아니라 취향이고, 취향은 깨지는 소비자가 있는 순간 규칙이 된다.

#### `toPythonStringLiteral()`

**직관:** 임의의 바이트열을 Python 문자열 리터럴로 안전하게 감싸는 함수. C++가 조립해 실행하는 Python 코드에 경로를 끼워 넣을 때 따옴표·역슬래시가 구문을 깨지 않게 한다.

**동작:** `asUTF8()`로 얻은 바이트를 한 바이트씩 훑으며 `\\`, `"`, `\n`, `\r`, `\t`만 이스케이프하고 나머지는 그대로 복사한 뒤 양끝에 `"`를 붙인다. 결과는 `setUTF8()`로 `MString`에 담는다. 플러그인 로드 경로를 `sys.path`에 넣는 코드가 이 함수를 지난다. 최종 리뷰 지적(M3)으로 도입됐다.

**예시:**
```cpp
MString toPythonStringLiteral(const MString& value) {
    std::string out; out += '"';
    for (const char* c = value.asUTF8(); c && *c; ++c)
        switch (*c) { case '\\': out += "\\\\"; break; case '"': out += "\\\""; break;
                      /* \n \r \t ... */ default: out += *c; }
    out += '"'; MString r; r.setUTF8(out.c_str()); return r;
}
```

**관련 코드:**
- `src/maro_plugin/MaroPythonBridge.cpp:50-67` — 함수
- `src/maro_plugin/MaroPythonBridge.cpp:90-93` — 경로를 리터럴로 끼우는 호출부

**증거:**
- §6.9, §6.9.1

**함정:** 작은따옴표로 감싸면 경로 안의 작은따옴표를 또 처리해야 한다. 큰따옴표 하나로 고정하고 그것만 이스케이프하는 편이 규칙이 단순하다.

**교훈:** 코드를 문자열로 만들어 실행할 때는 "값 주입"을 전용 함수 하나로 모은다. 그 함수가 유일한 신뢰 경계다.

#### raw 리터럴 `r'…'` 함정

**직관:** Python raw 문자열은 역슬래시를 그대로 두지만 만능이 아니다 — 끝이 역슬래시인 경로(`r'C:\dir\'`)는 구문 오류이고, 내부 따옴표도 처리하지 못한다. 그래서 경로 주입에 쓸 수 없다.

**동작:** Windows 경로를 Python에 넘길 때 `r'...'`가 쉬워 보이지만 `C:\maro\plug-ins\`처럼 역슬래시로 끝나면 닫는 따옴표를 이스케이프해 버려 `SyntaxError`다. 대안으로 Python 쪽 `repr()`을 쓰는 방법이 있으나 문자열을 만드는 주체가 C++이므로 쓸 수 없다. 결국 자체 이스케이프(`toPythonStringLiteral`)를 택했다.

**예시:**
```python
r'C:\maro\plug-ins\'      # SyntaxError — 끝 역슬래시가 닫는 따옴표를 먹는다
"C:\\maro\\plug-ins\\"    # 자체 이스케이프로 만든 리터럴 (안전)
```

**관련 코드:**
- `src/maro_plugin/MaroPythonBridge.cpp:50-67` — 자체 이스케이프 선택
- `src/maro_plugin/MaroPythonBridge.cpp:84-103` — 조립되는 Python 코드

**증거:**
- §6.9, §6.9.1

**함정:** 개발 PC의 경로에는 끝 역슬래시나 따옴표가 없어 테스트가 통과한다. 사용자 설치 경로에서 처음 터진다.

**교훈:** "대부분의 입력에서 동작하는" 이스케이프는 이스케이프가 아니다. 모든 바이트열에 성립하는 규칙을 고른다.

#### 바이트 단위 이스케이프

**직관:** 문자(코드포인트)가 아니라 바이트 단위로 훑으며 이스케이프하는 것. UTF-8에서는 이것이 안전하다 — 특별 취급할 문자가 전부 ASCII이고 멀티바이트의 모든 바이트는 0x80 이상이기 때문이다.

**동작:** `toPythonStringLiteral`은 `const char*`를 한 바이트씩 본다. `\\`, `"`, `\n`, `\r`, `\t`는 전부 0x7F 이하이고 한글 등 멀티바이트 문자의 어떤 바이트도 이 값과 겹치지 않으므로, 바이트 루프가 문자를 쪼개 이스케이프를 잘못 넣는 일이 없다. 디코딩·재인코딩이 필요 없어 로케일 의존도 사라진다.

**예시:**
```
"가" = EA B0 80   ← 모든 바이트 ≥ 0x80, ASCII 특수문자와 겹치지 않음
따라서 바이트 루프가 '가'를 쪼개도 이스케이프 판정에 영향 없음
```

**관련 코드:**
- `src/maro_plugin/MaroPythonBridge.cpp:53-62` — 바이트 루프
- `python/maroDagMenu.py:102-110` — 같은 이유로 바이트 정규식을 쓰는 MEL 치환

**증거:**
- §6.9, §6.9.1

**함정:** 이 성질은 UTF-8에서만 성립한다. CP949 같은 레거시 인코딩에서는 두 번째 바이트가 ASCII 범위일 수 있어 바이트 루프가 문자를 깨뜨린다.

**교훈:** UTF-8의 자기 동기화 성질(연속 바이트가 ASCII와 겹치지 않음)을 알면 디코딩 없이 안전한 처리가 가능하다. 그 전제를 주석에 적는다.

#### UTF-8 멀티바이트 ≥0x80

**직관:** UTF-8에서 ASCII가 아닌 모든 문자의 모든 바이트는 최상위 비트가 1(0x80 이상)이다. 이 한 가지 성질이 바이트 단위 처리의 안전성을 보장한다.

**동작:** 선행 바이트는 `110xxxxx`/`1110xxxx`/`11110xxx`, 연속 바이트는 `10xxxxxx` — 모두 0x80 이상이다. 그래서 ASCII 구분자(따옴표·역슬래시·개행)를 바이트로 찾아도 멀티바이트 문자 안쪽을 잘못 집지 않는다. `toPythonStringLiteral`과 `_PROC_HEADER_RE`(MEL 헤더 치환) 둘 다 이 성질에 기대며, 코드 주석이 근거를 적는다. 단, 시작부터 끝까지 UTF-8이어야 하므로 `asChar()`(로케일)가 아니라 `asUTF8()`을 쓴다.

**예시:**
```
ASCII  'A'  = 41                      (0x80 미만)
한글   '가' = EA B0 80                 (전부 0x80 이상)
→ 바이트 41("A")을 찾는 검색이 '가'의 일부를 오탐하지 않는다
```

**관련 코드:**
- `src/maro_plugin/MaroPythonBridge.cpp:50-67` — UTF-8 안전 이스케이프
- `python/maroDagMenu.py:107-112` — 바이트 정규식

**증거:**
- §6.9, §6.9.1

**함정:** `asChar()`로 받은 문자열은 로케일 코드페이지라 이 성질이 깨진다. 한글 사용자 폴더에서 경로가 모지바케가 되는 원인이다.

**교훈:** 인코딩 성질에 기대는 최적화는 "입력이 정말 그 인코딩인가"를 먼저 보장해야 한다. 경계에서 UTF-8로 고정한다.

#### `_PROC_HEADER_RE` 바이트 정규식

**직관:** Maya의 `dagMenuProc.mel` 원본에서 프로시저 헤더 한 줄만 찾아 이름을 바꾸는 정규식. 문자열이 아니라 **바이트** 패턴이라 디코딩 없이 동작한다.

**동작:** `_writeBackupCopy()`는 원본 `.mel`을 `open(path, "rb")`로 바이트로 읽고, `rb"^([ \t]*global[ \t]+proc[ \t]+)dagMenuProc"` + 인자 목록 lookahead로 헤더를 정확히 한 번만 매치해 `maroDagMenuProcOriginal`로 치환한 임시 파일을 쓴다. 인자 목록(`string $a, string $b`)까지 확인해 다른 프로시저를 건드리지 않는다. 백업이 실제로 존재함을 확인한 뒤에야 같은 이름의 래퍼를 정의하고, 래퍼는 원본을 먼저 부른 다음 Maro 메뉴 항목을 덧붙인다.

**예시:**
```python
_PROC_HEADER_RE = re.compile(
    rb"^([ \t]*global[ \t]+proc[ \t]+)dagMenuProc"
    rb"(?=[ \t]*\([ \t]*string[ \t]+\$\w+[ \t]*,[ \t]*string[ \t]+\$\w+[ \t]*\))",
    re.MULTILINE)
with open(sourceFile, "rb") as f: data = f.read()
```

**관련 코드:**
- `python/maroDagMenu.py:102-112` — 패턴과 바이트인 이유 주석
- `python/maroDagMenu.py:140-160` — 바이트 읽기·치환·임시 파일

**증거:**
- §7.2

**함정:** 공식 확장 훅 `optionalDagMenuProc`는 플러그인 타입 셰이프에만 걸린다. 일반 `mesh`까지 메뉴를 넣으려면 원본 체이닝이 필요했고, 그래서 이 치환이 존재한다.

**교훈:** 남의 스크립트를 가공할 때는 디코딩하지 말고 바이트로 최소 치환한다. 건드리지 않은 바이트는 절대 깨지지 않는다.

#### `errors="replace"` U+FFFD

**직관:** Python이 디코딩 실패 바이트를 U+FFFD(�)로 바꾸는 모드. 편해 보이지만 그 결과를 다시 파일로 쓰면 원본의 바이트가 영구히 사라진다.

**동작:** `dagMenuProc.mel`을 `errors="replace"`로 디코드해 다루면, UTF-8이 아닌 바이트가 섞인 지역화 설치본에서 MEL 문자열 리터럴이 U+FFFD로 바뀐 사본이 만들어진다. 그리고 그 사본이 곧 세션 전체의 우클릭 메뉴가 되므로 메뉴 라벨이 깨진 상태로 고정된다. 그래서 바이트로 읽고 바이트로 치환한다.

**예시:**
```python
# 위험: 지역화 설치본의 비UTF-8 바이트가 �로 치환된 사본을 source하게 된다
text = open(mel, encoding="utf-8", errors="replace").read()
# 안전: 바이트로 읽고 바이트로 치환
data = open(mel, "rb").read()
```

**관련 코드:**
- `python/maroDagMenu.py:102-106` — 바이트 패턴인 이유
- `python/maroDagMenu.py:140-160` — 바이트 경로

**증거:**
- §7.2

**함정:** `errors="replace"`는 예외를 없애므로 "문제가 해결된" 느낌을 준다. 실제로는 손실을 나중으로 미룰 뿐이다.

**교훈:** 디코딩 오류 정책은 "이 데이터를 다시 쓸 것인가"로 정한다. 다시 쓸 데이터는 디코딩하지 않는다.

#### 잘못된 UTF-8을 코드로 생성

**직관:** 유효하지 않은 UTF-8 바이트를 테스트에 넣을 때 소스 파일에 리터럴로 적으면 안 된다 — 편집기나 컴파일러가 조용히 "고쳐" 버려 테스트가 아무것도 검증하지 못한다. 코드로 바이트를 만들어야 한다.

**동작:** `test_journal_writer.cpp`는 `invalidUtf8Tag.push_back(static_cast<char>(0x80))`로 단독 연속 바이트를 만든다. 주석이 "The invalid byte is constructed explicitly"라고 이유를 적는다. 그 태그를 저널에 쓰면 `dump()`가 U+FFFD로 대체하는지, 통과시키거나 잘라내지 않는지를 단언한다. §8.2의 공통 정신 "틀린 구현이 통과하지 못하게 만드는 테스트 설계"의 한 사례다.

**예시:**
```cpp
std::string invalidUtf8Tag = "tag";
invalidUtf8Tag.push_back(static_cast<char>(0x80));   // lone continuation byte
// 리터럴 "tag\x80"을 소스에 적으면 편집기가 인코딩을 "고칠" 수 있다
```

**관련 코드:**
- `tests/diag/test_journal_writer.cpp:175-215` — 바이트 생성과 단언
- `src/maro_diag/src/JournalWriter.cpp:16-22` — replace 핸들러

**증거:**
- §8.2, §8.2.4

**함정:** 바이너리 픽스처 파일로 두는 방법도 있지만 git 설정(autocrlf, 텍스트 판정)이 바이트를 바꿀 수 있다. 코드 생성이 가장 확실하다.

**교훈:** 테스트 입력이 "저장 과정에서 변질될 수 있는 것"이면 저장하지 말고 실행 중에 만든다.

#### `dump()` strict throw

**직관:** `nlohmann::json::dump()`는 기본이 strict라 유효하지 않은 UTF-8이 들어 있으면 예외를 던진다. 진단 로그를 쓰는 경로에서 그 예외가 새면 Maya 세션이 끝난다.

**동작:** `siteTag`·`message`는 Windows API나 ROS 페이로드 출처라 유효 UTF-8 보장이 없다. 예외를 삼키면 그 레코드가 통째로 사라지는데, 크래시 인접 집계에는 바로 그 레코드가 필요하다. 그래서 `dump(-1, ' ', false, error_handler_t::replace)`로 잘못된 바이트를 U+FFFD로 바꿔 나머지를 온전히 남긴다(nlohmann 공식 옵션). 인자 셋은 `dump()` 기본값과 같게 두고 핸들러만 바꿨다.

**예시:**
```cpp
// dump()의 strict 기본값은 던지고, 예외를 삼키면 레코드가 사라진다.
return j.dump(-1, ' ', false, nlohmann::json::error_handler_t::replace);
```

**관련 코드:**
- `src/maro_diag/src/JournalWriter.cpp:14-22` — 핸들러와 이유 주석
- `tests/diag/test_journal_writer.cpp:175-215` — 0x80 대체 검증

**증거:**
- §8.2, §8.2.4, §10.7, §11.5

**함정:** 던지게 두고 상위에서 잡으면 "로그가 가끔 비는" 증상이 된다. 진단 도구가 진단을 잃는 것이 가장 나쁜 실패다.

**교훈:** 로깅 경로는 "무슨 일이 있어도 한 줄은 남긴다"가 계약이다. 손실이 불가피하면 전부가 아니라 일부(문자 하나)만 잃는 쪽을 고른다.

#### JSON Lines

**직관:** 한 줄에 JSON 하나씩 쓰는 포맷. 항상 append만 하므로 쓰는 도중 프로세스가 죽어도 이미 완결된 줄은 유효하다 — 트리 전체를 다시 쓰는 포맷이면 파일 전체가 깨진다.

**동작:** 진단 book의 스필과 저널이 JSON Lines다. 완결된 줄은 `\n`으로 끝나고, 죽은 시점의 줄은 개행 없는 조각으로 남아 다음 로드에서 건너뛰어진다(의도). 로더는 파싱 실패 줄을 스킵하되 `parse_error`와 `type_error` 둘 다 잡아야 한다 — JSON은 유효한데 필드 타입이 틀린 줄(`"analysis":123`)도 있기 때문이다. 감시자가 없는 지금 플러그인은 정본을 절대 쓰지 않고 스필만 쓰며, 정본은 존재하면 읽기만 한다(Layer A 결정 1).

**예시:**
```
{"hash":"a1b2","message":"..."}\n      ← 완결
{"hash":"c3d4","mess              ← 크래시 조각(개행 없음) → 다음 로드에서 스킵
```

**관련 코드:**
- `src/maro_diag/include/maro_diag/BookStore.h:23-34` — 왜 JSON Lines인가
- `src/maro_diag/src/BookStore.cpp:55-70` — 줄 스킵과 예외 처리
- `src/maro_diag/src/JournalWriter.cpp:283` — `maro_journal.<pid>.jsonl`

**증거:**
- §5.5, §5.5.4, §9.2.2, §11.5

**함정:** 다중 프로세스가 같은 파일에 동시에 append하는 것은 범위 밖이다(파일 락이 필요). 저널 파일 이름에 PID를 넣어 이 문제를 회피한다.

**교훈:** 크래시 내구성은 포맷 선택에서 시작한다. "줄 단위 독립"이면 손실이 한 줄로 제한된다.

#### append-only

**직관:** 파일을 덮어쓰지 않고 끝에 덧붙이기만 하는 쓰기 방식. 이미 쓴 바이트를 건드리지 않으므로 어느 시점에 죽어도 앞부분은 온전하다.

**동작:** 저널 `maro_journal.<pid>.jsonl`은 append-only이며 세션 open/close 줄, 태그 예산(5건/1초) 억제, 10세션 보관 정책을 갖는다. book 스필도 `appendToSpill`로만 커진다. 병합·정리는 별도 단계에서 파일을 새로 쓰는 방식으로 하되, 플러그인이 도는 중에는 하지 않는다.

**예시:**
```
maro_journal.12345.jsonl     ← 이 세션(PID 12345)만 여기에 append
maro_journal.12280.jsonl     ← 이전 세션, 건드리지 않음 (10개까지 보관)
```

**관련 코드:**
- `src/maro_diag/src/JournalWriter.cpp:95-115` — append 경로
- `src/maro_diag/src/BookStore.cpp:90-120` — `appendToSpill`

**증거:**
- §5.5, §11.1

**함정:** append-only 파일은 무한히 자란다. 보관 정책(세션 10개, 태그 예산)이 없으면 사용자 디스크를 채운다.

**교훈:** append-only는 내구성을 주고 용량 문제를 남긴다. 회전·보관 정책을 같은 설계에서 정한다.

#### 잘린 조각(truncated fragment)

**직관:** 크래시로 개행 없이 끝난 마지막 줄. 그 자체는 버려도 되지만, 다음 실행이 그 뒤에 바로 append하면 새 레코드가 조각에 붙어 함께 사라진다.

**동작:** `appendToSpill`은 쓰기 전에 파일의 마지막 바이트를 확인해(`seekg(-1, ios::end)`) `\n`이 아니면 개행을 먼저 쓴다. 테스트 `test_book_store.cpp`는 잘린 조각 뒤에 append해도 새 항목이 살아남는지 단언한다. 이것이 없으면 크래시 직후의 첫 새 레코드가 조용히 유실된다(F-135).

**예시:**
```cpp
check.seekg(-1, std::ios::end);
char lastByte = '\0';
if (check.get(lastByte) && lastByte != '\n') { /* 개행을 먼저 쓴다 */ }
```

**관련 코드:**
- `src/maro_diag/src/BookStore.cpp:105-115` — 마지막 바이트 확인
- `tests/diag/test_book_store.cpp:90-119` — 조각 뒤 append 생존 검증

**증거:**
- §5.5, §8.2.4
- F-135

**함정:** "로더가 깨진 줄을 건너뛰니 괜찮다"는 생각이 함정이다 — 건너뛰는 것은 조각이고, 조각에 붙은 새 레코드도 같이 건너뛰어진다.

**교훈:** append 내구성은 "쓰기 전에 경계를 확인"까지 포함한다. 앞 줄의 상태가 내 줄의 운명을 정한다.

#### TOCTOU

**직관:** Time-Of-Check to Time-Of-Use — 확인한 시점과 사용하는 시점 사이에 상태가 바뀌는 경쟁. "마지막 바이트가 개행인가"를 확인한 뒤 쓰는 사이에 다른 스레드가 쓰면 파일이 깨진다.

**동작:** 두 워커가 같은 스필에 동시에 append하면 (1) 마지막 바이트 확인 후 쓰기와 (2) `ofs << dump() << '\n'`(삽입 두 번)이 겹쳐 줄이 섞인다. 로더가 깨진 줄을 건너뛰므로 겉으로는 멀쩡해 보이지만 "설계가 아니라 운"이다. 그래서 `bookMutex()`가 스필/정본 파일 I/O와 `bookCache()`를 직렬화하고, 디스크·캐시 작업이 끝나 락을 놓은 뒤에야 `warn()`을 부른다(경고 경로가 다시 락을 잡지 않게).

**예시:**
```cpp
std::mutex& BoadMaro::bookMutex() { static std::mutex s_bookMutex; return s_bookMutex; }
// 확인 → 쓰기 전체를 이 뮤텍스가 감싼다 (TOCTOU·이중 삽입 방지)
```

**관련 코드:**
- `src/maro_plugin/MaroDiag.cpp:292-296` — `bookMutex`
- `src/maro_diag/src/BookStore.cpp:90-125` — 확인+쓰기 구간
- `python/maroDagMenu.py:377-424` — 바인딩 TOCTOU 정리 경로

**증거:**
- §5.5, §5.5.4, §6.7, §6.7.1
- F-137

**함정:** 겉으로 멀쩡한 TOCTOU는 발견되지 않는다 — 깨진 줄이 조용히 스킵되기 때문이다. 동시성 문제는 증상이 아니라 설계로 판단한다.

**교훈:** "확인 후 행동"은 원자적이어야 한다. 그 두 단계 사이를 락으로 묶거나, 확인이 필요 없는 API(append 모드)를 쓴다.

#### `writeBinaryStl`

**직관:** 삼각형 리스트를 바이너리 STL로 쓰는 순수 함수. Maya 내장 `stlTranslator.mll`을 쓰지 않는 이유는 좌표·단위 변환을 정점에 바로 적용하고 배치 왕복 검증을 하기 위해서다.

**동작:** 80바이트 헤더 + `uint32` 삼각형 수 + 삼각형마다 `struct.pack("<12fH", ...)` 50바이트(법선 3 + 정점 9 = 12 float + 속성 uint16). `_triangleNormal`은 면적이 0이면 (0,0,0)을 준다 — 전부 0이면 형식을 잘못 쓴 것과 구별할 수 없어서 계산한다. Maya 없이 도는 함수라 테스트가 쓰고 다시 읽어 왕복을 검증한다.

**예시:**
```python
f.write(b"\0" * 80)                         # 80B 헤더
f.write(struct.pack("<I", len(triangles)))  # uint32 삼각형 수
for tri in triangles:
    f.write(struct.pack("<12fH", nx, ny, nz, *flatVertices, 0))   # 50B
```

**관련 코드:**
- `python/maroUrdfExport.py:1217-1242` — 함수
- `python/maroUrdfExport.py:1202-1215` — `_triangleNormal`
- `tests/maya/test_urdf_export.py` — 왕복 검증

**증거:**
- §7.14, §8.3.6
- F-291

**함정:** 법선을 전부 0으로 두는 STL도 규격상 허용되지만, 그러면 "법선을 안 썼다"와 "형식을 잘못 썼다"를 구별할 수 없다. 계산해 넣는 편이 진단에 유리하다.

**교훈:** 바이너리 포맷을 직접 쓰면 변환을 내 손에 둘 수 있고 테스트가 싸진다. 규격이 단순할 때의 합리적 선택이다.

#### 80B 헤더

**직관:** 바이너리 STL의 첫 80바이트 — 내용은 자유(보통 코멘트)이고 파서는 대개 무시한다. 다만 "solid"로 시작하면 ASCII STL로 오인될 수 있다.

**동작:** `writeBinaryStl`은 80바이트를 0으로 채운다. 그 뒤 `uint32` 삼각형 수가 오고 본문이 시작된다. 헤더가 고정 길이라 파일 크기는 `80 + 4 + 50·N`으로 정확히 계산되며, 테스트가 이 식으로 파일 크기를 단언할 수 있다.

**예시:**
```
파일 크기 = 80 + 4 + 50 × 삼각형수
삼각형 1000개 → 80 + 4 + 50000 = 50,084 바이트
```

**관련 코드:**
- `python/maroUrdfExport.py:1217-1230` — 헤더 쓰기
- `tests/maya/test_urdf_export.py` — 크기·개수 검증

**증거:**
- §7.14, §11.5

**함정:** 헤더를 텍스트로 채울 때 "solid"로 시작하면 일부 로더가 ASCII STL로 판단해 파싱에 실패한다. 0으로 채우는 것이 가장 안전하다.

**교훈:** 포맷 판별이 휴리스틱(첫 단어)인 경우가 있다. 자유 필드라도 그 휴리스틱을 건드리지 않게 채운다.

#### uint32

**직관:** 32비트 부호 없는 정수 — 바이너리 STL에서 헤더 다음에 오는 삼각형 개수의 타입이다. 리틀 엔디안으로 4바이트.

**동작:** `struct.pack("<I", count)`로 쓴다. `<`가 리틀 엔디안과 표준 크기를 지정한다. 같은 타입이 메쉬 파이프라인 전반에 쓰인다 — `MFnMesh::getTriangles`가 주는 인덱스 버퍼도 uint32이고, 포인트클라우드 `width`·`point_step`도 uint32다. 최대 약 42억 개라 실용상 제한이 아니다.

**예시:**
```python
f.write(struct.pack("<I", len(triangles)))   # 리틀 엔디안 uint32
```

**관련 코드:**
- `python/maroUrdfExport.py:1230-1240` — 개수 쓰기
- `src/maro_plugin/MaroPointCloudNode.cpp:241-390` — uint32 인덱스 버퍼 사용

**증거:**
- §7.14, §6.8.2, §11.5

**함정:** 플랫폼 기본(`"I"` without `<`)으로 쓰면 정렬 패딩과 네이티브 엔디안이 끼어든다. 파일 포맷에는 항상 명시적 엔디안 접두를 쓴다.

**교훈:** 파일에 나가는 정수는 크기와 엔디안을 포맷이 정한다. 언어의 기본값을 믿지 않는다.

#### `"<12fH"` 50B

**직관:** 바이너리 STL 삼각형 하나의 `struct` 포맷 — float 12개(법선 3 + 정점 3×3)와 uint16 속성 1개 = 4·12 + 2 = 50바이트. `<`가 리틀 엔디안과 "패딩 없음"을 함께 지정한다.

**동작:** `struct.pack("<12fH", nx, ny, nz, v0x, v0y, v0z, v1x, ..., v2z, 0)`. 속성 바이트 2개는 대개 0이며 일부 도구가 색을 넣는다. 50바이트가 정확히 맞아야 파서가 삼각형 경계를 잃지 않는다.

**예시:**
```python
"<12fH" 의 크기 = 50   ('<' 없으면 52 — 정렬 패딩)
```

**관련 코드:**
- `python/maroUrdfExport.py:1228-1242` — 포맷과 주석

**증거:**
- §7.14

**함정:** `H`(uint16) 앞에 정렬 패딩 2바이트가 들어가면 52바이트가 되어 두 번째 삼각형부터 전부 어긋난다. 증상은 "모델이 폭발한 것처럼 보임"이다.

**교훈:** `struct` 포맷 문자열은 크기를 단언하는 테스트를 하나 둔다. 한 줄로 정렬 사고를 막는다.

#### 정렬 패딩

**직관:** C 구조체에서 필드를 자연 경계에 맞추려 컴파일러가 넣는 빈 바이트. 메모리에서는 성능을 위해 필요하지만 파일 포맷에서는 규격을 깨뜨린다.

**동작:** Python `struct`는 접두 문자로 이 동작을 제어한다 — `<`/`>`/`!`/`=`는 표준 크기·패딩 없음, `@`(기본)는 네이티브 크기·패딩 있음. STL은 `<12fH`로 50바이트를 보장한다. C++ 쪽에서도 파일·공유 메모리 구조체는 `#pragma pack`이나 명시적 바이트 조립으로 패딩을 없앤다(`SharedImageHeader` 같은 레거시 구조체가 그 예).

**예시:**
```
"@12fH" (네이티브): 48 + 2 + 패딩 2 = 52 바이트
"<12fH" (표준):     48 + 2          = 50 바이트  ← 규격
```

**관련 코드:**
- `python/maroUrdfExport.py:1228-1232` — `<`가 패딩을 끈다는 주석
- `src/maro_lidar/src/PointCloudPacking.cpp:8-30` — 바이트 단위로 직접 조립

**증거:**
- §7.14

**함정:** 개발 머신에서 우연히 패딩이 없어 통과하다가 다른 컴파일러·아키텍처에서 깨질 수 있다. 크기 단언이 이식성 검사 역할을 한다.

**교훈:** "메모리 구조체 = 파일 레이아웃"이라는 가정은 위험하다. 직렬화는 명시적으로 한다.

#### PFM `"Pf"`/`"PF"`

**직관:** Portable FloatMap — 부동소수 래스터 이미지 포맷. 매직이 `"Pf"`면 단일 채널(그레이스케일), `"PF"`면 3채널(RGB)이다. Arnold depth AOV를 EXR에서 변환해 읽을 때 쓴다.

**동작:** `convertExrToPfm`이 Arnold 번들 `oiiotool.exe`로 EXR을 PFM으로 바꾸고, `parsePfm`이 읽는다. 파서는 `"Pf"`만 지원하며 `"PF"`를 받으면 명시적으로 거부한다 — 3채널을 단일 채널로 오인하면 인터리브된 RGB가 스크램블된 depth로 읽혀 포인트클라우드가 노이즈가 된다. 헤더는 매직, 너비·높이, scale 순의 텍스트 줄이고 그 뒤가 float 바이너리다.

**예시:**
```python
if header not in ("Pf", "PF"): raise ...
if header != "Pf":
    raise RuntimeError("parsePfm은 단일 채널(Pf) PFM만 지원합니다 -- {!r}는 3채널".format(header))
```

**관련 코드:**
- `python/maroSyntheticDataPointCloud.py:189-210` — 매직 검사
- `python/maroSyntheticDataPointCloud.py:165-188` — EXR→PFM 변환

**증거:**
- §7.15, §11.5

**함정:** 3채널을 받아도 파싱은 "성공"한다 — 바이트 수만 맞으면 값이 나온다. 명시적 거부가 없으면 조용히 틀린 깊이를 쓴다.

**교훈:** 포맷 변종은 읽기 전에 거부한다. "읽을 수 있음"과 "의미가 맞음"은 다르다.

#### 아래→위

**직관:** PFM은 이미지의 **아래쪽 줄부터** 저장한다. 대부분의 이미지 포맷(위→아래)과 반대라, 읽은 뒤 뒤집지 않으면 깊이 이미지가 상하 반전된다.

**동작:** `parsePfm`은 float 배열을 읽은 뒤 행 순서를 뒤집어 위→아래로 만든다. 역투영 `unprojectDepthToPoints`는 `yCam = (cy − (row + 0.5))·d/fy`로 위→아래 row 인덱스를 가정하므로, 뒤집지 않으면 y 부호가 통째로 반대가 된다. 이 부호 규약은 Y=+100 큐브를 실제로 렌더해 확정했다.

**예시:**
```
PFM 파일 순서: 마지막 화면 줄 → ... → 첫 화면 줄
parsePfm 반환:  첫 화면 줄 → ... → 마지막 화면 줄   (뒤집음)
```

**관련 코드:**
- `python/maroSyntheticDataPointCloud.py:189-218` — 읽기와 뒤집기
- `python/maroSyntheticDataPointCloud.py:219-250` — row를 위→아래로 가정하는 역투영

**증거:**
- §7.15, §11.5

**함정:** 상하 반전은 대칭적인 장면에서는 눈에 안 띈다. 비대칭 물체(바닥에 놓인 상자)로 확인한다.

**교훈:** 래스터 포맷의 행 순서는 포맷마다 다르다. 읽는 함수에서 한 번 정규화하고 나머지 코드는 하나의 규약만 안다.

#### scale 부호=엔디안

**직관:** PFM 헤더 세 번째 줄의 scale 값은 절대값이 스케일이고 **부호가 엔디안**이다 — 음수면 리틀 엔디안, 양수면 빅 엔디안.

**동작:** `parsePfm`은 `scale = float(f.readline())`을 읽고 `endian = "<" if scale < 0 else ">"`로 이후 float 언패킹의 바이트 순서를 정한다. oiiotool이 쓰는 PFM은 보통 `-1.0`(리틀 엔디안, 스케일 1)이다. 엔디안을 무시하고 네이티브로 읽으면 값이 천문학적 숫자나 0에 가까운 값으로 나와 깊이가 전부 버려진다.

**예시:**
```python
scale = float(f.readline().decode("ascii").strip())   # 예: -1.0
endian = "<" if scale < 0 else ">"                     # 리틀 엔디안
```

**관련 코드:**
- `python/maroSyntheticDataPointCloud.py:209-218` — scale과 엔디안

**증거:**
- §7.15, §11.5

**함정:** x86에서만 테스트하면 리틀 엔디안 경로만 돌아 빅 엔디안 분기가 검증되지 않는다. 생성기(oiiotool)가 항상 리틀을 쓴다면 그 사실을 주석에 적는 편이 정직하다.

**교훈:** 헤더 필드가 두 가지 의미(스케일 + 엔디안)를 겸하는 포맷이 있다. 규격을 읽고 두 의미를 모두 구현한다.

#### `parsePfm`

**직관:** PFM 파일을 읽어 `(floats, width, height)`를 돌려주는 함수. 매직 검사, 크기 파싱, 엔디안 판정, 행 뒤집기를 한 곳에서 한다.

**동작:** 순서는 (1) 매직 `"Pf"` 확인(아니면 거부), (2) `width height` 줄, (3) scale 줄에서 엔디안, (4) `width·height` 개의 float를 엔디안에 맞춰 언패킹, (5) 행 순서 뒤집기. 테스트는 실제 `oiiotool`을 실행해 EXR→PFM 왕복을 검증하고, 변환 실패 시 `RuntimeError`가 나는지도 확인한다(440줄짜리 `test_synthetic_data_point_cloud.py`).

**예시:**
```python
depths, w, h = parsePfm(pfmPath)
points = unprojectDepthToPoints(depths, w, h, intrinsics, camMatrix, planarDepth=True)
```

**관련 코드:**
- `python/maroSyntheticDataPointCloud.py:189-218` — 파서
- `python/maroSyntheticDataPointCloud.py:165-188` — `convertExrToPfm`
- `tests/maya/test_synthetic_data_point_cloud.py` — 실제 oiiotool 왕복

**증거:**
- §7.15, §8.3.6

**함정:** 헤더 줄 구분이 공백일 수도 개행일 수도 있다. `readline` 기반 파싱은 생성기가 바뀌면 깨질 수 있어, 왕복 테스트가 실제 생성기를 쓰는 것이 중요하다.

**교훈:** 외부 도구가 만든 파일을 파싱하는 코드는 그 도구를 실제로 돌리는 테스트를 갖는다. 규격보다 생성기가 진실이다.
