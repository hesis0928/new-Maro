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

## 3. 힙 손상이 의심될 때

폴트 명령이 `ntdll.dll` 안이고 쓰기 접근이며 대상 주소가 매번 달라지면
힙 손상이다 — **크래시 지점은 버그 지점이 아니다.** 그때는 덤프를 더
파지 말고 `maro` 타겟만 `/fsanitize=address`로 빌드해서 손상을 내는
쓰기에서 직접 멈추게 한다(이 VS 설치에 ASan 런타임이 이미 있다).
시스템 전역 설정을 바꾸는 gflags/PageHeap은 쓰지 않는다.
