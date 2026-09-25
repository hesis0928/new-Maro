# mr_vault LEDGER — 마스터 레퍼런스 가독성 편집 + Obsidian 분해

계획: C:\Users\ckd30\.claude\plans\wise-kindling-truffle.md (승인 2026-09-12)
원천: C:\Users\ckd30\Projects\Maya_Ros_Sim\docs\maro-master-reference.md (10,494줄, LF)
라이브 보관함: C:\Users\ckd30\OneDrive\Documents\Maro Project\Master Reference\  (vault root = Maro Project\)
스크립트: 이 디렉터리(`tools/masterref/`, 2026-09-24 이전 — 옛 이름 mr_vault). work/ = 중간 산출, edit16/ = 집필 배치, out/ = 스테이징, reports/ = 검사 보고.


> **[2026-09-24] 파이프라인 이전**: 스크립트·`edit16/`·이 원장을 임시 스크래치패드에서 `tools/masterref/`(저장소 안)로 옮겼다. 일회성 마이그레이션 스크립트는 `archive/`. `work/`·`out/`·`reports/`는 생성물이라 `.gitignore`에 넣었다. 이전 후 `emit_vault.py --clean` 결과를 라이브와 대조해 차이 0을 확인했다. 사용법은 `README.md`.

## 고정된 결정 (P0 스모크 테스트에서 확정 — 사용자 확인 전까지 "가정")
- 층 폴더: `Maro Reference` / `Maro Note` / `Maro Failure` (기존 `Camera`/`Maya Note`에 대응). 루트 허브 `Intro Master Reference.md`.
- 프론트매터 있음(type/title/tags/source + 타입별). 허브 끝에 하위 목록. 장·절 번호 접두사.
- 링크: 모든 등장(HUB_STOPLIST만 노트당 1회). 인라인 코드 안 식별자는 `[[Target|`x`]]` (가정: 백틱 별칭 렌더링 OK — P0 확인 필요).
- 파일명 금지 문자 → 전각 치환 (가정: 탐색기/퀵 스위처에서 문제 없음 — P0 확인 필요).
- 자연 정렬 `10.2` < `10.10` (가정 — P0 확인 필요; 실패 시 PAD_MINOR=True로 `10.02`).

## 단계 상태
- [x] P0 표본 8개 생성. 사용자 미확인("몰라") → 보수적 가정 채택: CODE_ALIAS_STYLE=plain, 전각 치환+aliases 유지, PAD_MINOR=False(허브 목록으로 순서 보장; 문제 시 플래그), LINK_MODE=all. P6에서 재확인
- [x] P1 transform_master.py (master.v0.md 12,486줄; S3 36건 번호 부여, S4 304 블록, S6 2표; check_master 기준선 ALL OK) → work/master.v0.md + check_master 기준선
- [x] P2 파일럿: edit/c06d.md(§6.6+13.6.6) → assemble → check_master ALL OK → parse/index/linkify/emit(--only 6.6) 129 노트 → validate(partial) ALL OK → 라이브 게시(2026-09-12 20:30). 템플릿 동결(사용자 검토 대기, 진행 계속).
  - 스크립트 완성: transform_master / assemble_master / check_master / parse_master / build_index / linkify / emit_vault / validate_vault / publish_vault (전부 mr_vault/). 패치 파일 patch1~3.py는 적용 완료(재실행 금지).
  - 결정: 코드 별칭 plain, 용어 파일명 = 식별자 머리(strip_trailing_group), 한글 표면형 ≥3자, HUB_STOPLIST 첫 등장만, 행 뜻은 ' / '로 용어 수만큼 분배, explained_in = 가장 긴 심화 뜻의 절.
  - §15는 P4에서 index.json 기반으로 재생성 예정(현재 v0의 §15는 terms-collected 기반 — 용어 수 1,597 vs index 1,614 불일치 → sec15 렌더러 필요).
- [x] P3 수작업 chunk 전부 완료 (아래 표; check_master 104 블록 ALL OK, 2026-09-15)
- [x] P4 리포 파일 확정 (2026-09-15: sec15.py로 §15 재생성 1,624 용어·72 가지·심화 516; S9 표 코드 스팬 `|` 이스케이프 16건; check_master ALL OK 109 블록; docs/maro-master-reference.md 12,902줄 교체 — 원본 백업 work/master.orig.bak; §14 419→2,406줄)
- [x] P5 보관함 생성·게시·검증 (2026-09-15 03:48: emit --clean 2,205 노트 = Reference 177 + Note 1,708 + Failure 319 + 루트 1; 링크 20,632 미해석 0; validate staging/live ALL OK; robocopy /MIR 게시). 수정: linkify 대괄호 인접 표면형 미링크 + 표 행 위키링크 별칭 `\|` 이스케이프(table_pipes); validate 보강 참조 검사 줄머리 한정.
- [ ] P6 사용자 점검·마감 — 사용자가 Obsidian에서 확인할 것: 전각 파일명(`5.5 src／maro_diag／`), 표 안 `[[X\|Y]]` 렌더, `10.2`<`10.10` 정렬, 프론트매터. 스크립트 리포 이관(`tools/masterref/`) 제안 대기. — 사용자가 Obsidian에서 확인할 것: 전각 파일명(`5.5 src／maro_diag／`), 표 안 `[[X\|Y]]` 렌더, `10.2`<`10.10` 정렬, 프론트매터. 스크립트 리포 이관(`tools/masterref/`) 제안 대기. — 사용자가 Obsidian에서 확인할 것: 전각 파일명(`5.5 src／maro_diag／`), 표 안 `[[X\|Y]]` 렌더, `10.2`<`10.10` 정렬, 프론트매터. 스크립트 리포 이관(`tools/masterref/`) 제안 대기. — 사용자가 Obsidian에서 확인할 것: 전각 파일명(`5.5 src／maro_diag／`), 표 안 `[[X\|Y]]` 렌더, `10.2`<`10.10` 정렬, 프론트매터. 스크립트 리포 이관(`tools/masterref/`) 제안 대기.

## chunk 표 (P3)
| chunk | §0–12 범위 | §13 항목 | 상태 | check_master |
|---|---|---|---|---|
| c00-02 | §0–§2 | 13.0.1–13.2 | done | OK |
| c03 | §3 | 13.3.1–13.3.8 | done | OK |
| c04 | §4 | 13.4.1–13.4.5 | done | OK |
| c05a | §5.1–5.2 | 13.5.1–13.5.2 | done | OK |
| c05b | §5.3–5.4 | 13.5.3–13.5.4 | done | OK |
| c05c | §5.5 | 13.5.5 | done | OK |
| c06a | §6.0–6.1 | 13.6.0–13.6.1 | done | OK |
| c06b | §6.2–6.3 | 13.6.2–13.6.3 | done | OK |
| c06c | §6.4–6.5 | 13.6.4–13.6.5 | done | OK |
| c06d | §6.6 | 13.6.6 | done | OK |
| c06e | §6.7 | 13.6.7 | done | OK |
| c06f | §6.8–6.9 | 13.6.8–13.6.9 | done | OK |
| c07a | §7.1–7.2 | 13.7.1–13.7.2 | done | OK |
| c07b | §7.3–7.9 | 13.7.3–13.7.9 | done | OK |
| c07c | §7.10–7.15 | 13.7.10–13.7.15 | done | OK |
| c08a | §8.0–8.2 | 13.8.0–13.8.2 | done | OK |
| c08b | §8.3–8.4 | 13.8.3–13.8.4 | done | OK |
| c09 | §9 | 13.9.0–13.9.5 | done | OK |
| c10 | §10 | 13.10.1–13.10.11 | done | OK |
| c11-12 | §11–§12 | 13.11–13.12 | done | OK |
| c-hubs | 장 한 줄 요약(0·1·3·13·14; 나머지는 각 chunk에 포함) | - | done | OK |

## 미해결 / 메모
- 기존 vault 예약 이름: Maya Ver-2026.1/**/Intro *.md 47개 (naming.py가 로드해 충돌 검사).
- §14 잘못된 행 2개(`|` 미이스케이프) — transform 단계에서 수정.

## 재실행 규칙 (P4 이후)
- `docs/maro-master-reference.md` 가 이제 편집본 자체다. **transform_master.py 를 다시 돌리지 말 것**(S5가 §15를 옛 terms-collected로 되돌리고 S3/S8이 이미 적용된 본문을 재가공).
- 이후 수정은 리포 파일을 직접 고친 뒤: `copy docs/... → work/master.edited.md` → `parse_master.py` → `build_index.py` → (`sec15.py` + 수동 §15 교체가 필요하면 assemble 대신 직접 붙여넣기) → `emit_vault.py --clean` → `validate_vault.py staging` → `publish_vault.py` → `validate_vault.py live`.
- edit/ chunk 파일과 work/master.v0.md 는 이력 보관용(원본 백업: work/master.orig.bak).

## 노트 보강(2026-09-16 계획: 기계 발췌 + 전 노트 집필) — 계획 파일 `C:\Users\ckd30\.claude\plans\wise-kindling-truffle.md`
- 기준선: work/master.v1.md (2026-09-16 리포 마스터 동결, 12,916줄). check_master 기본 base.
- [x] P-A 기계 발췌(2026-09-16): textutil.py / parse_master(다중 행 F-필드·§16·outro) / build_symbols.py / build_context.py(2,062 유닛; 용어 발췌 0건 163, 실패 0건 11) / linkify(form_at·mode, ASCII 경계에 한글 조사 허용 → 링크 20,632→37,418) / emit_vault(새 골격) / validate_vault(골격·authored·길이) / check_master(--base, §14 원본 필드 동일, §16) / assemble_failures.py / assemble_terms.py / check_authored.py / status.py. 스테이징·라이브 ALL OK, 게시 완료.
- [x] P-B 파일럿 집필·게시(2026-09-16): edit14/b00-pilot.md(F-001~010, check_authored 0 err/4 warn) + edit16/pilot-01.md(브리지 런타임 10개, 0 err/3 warn) → 마스터 13,174줄 → 보관함 재게시 ALL OK. 사용자 검토 결과: 서사·라벨 만족, 2건 수정 요청 → P-B2.
- [x] P-B2 피드백 반영·골격 동결(2026-09-16): (1) 용어 집필 필드 7종 `AUTHORED_T=(직관,동작,예시,관련 코드,증거,함정,교훈)`; pilot-01에 예시·관련 코드 추가(0 err/17 warn; check_authored는 `예시` 필드의 소문자 가명 식별자를 WARN으로 강등) → 마스터 13,330줄. (2) 발췌 층 분리 `Maro Excerpt/`(용어/<cat>/<가지>/<용어> 발췌.md · 실패/<분류>/<F> 발췌.md · Intro Maro Excerpt.md): 용어·실패 노트는 `## 발췌`(출처 링크 + 상세 링크)만 두고 본문은 발췌 노트로; 프론트매터 `excerpt_note`; 발췌 노트 끝 **돌아가기**. validate: TERM_H2/FAIL_H2/EXC_H2, coverage excerpt(=context 발췌≥1), (5) 왕복 링크, 고아 계산에서 발췌 노트 링크 제외. 결과: 노트 3,965(=2,205+1,759+1), 링크 52,122, 미해석 0, 고아 0, 라이브 ALL OK. **골격 동결 — 이후는 집필만.**
- [x] P-C 실패 집필 b01~b08(2026-09-16, 304/304) · [ ] P-D 용어 집필(가지 순, Maro 고유부터)

### 보강 상태
failures 304/304 (완료) · terms 1624/1624 · P-D 완료(전 카테고리 집필 완료) · next: P-D 다음 가지(status.py)

| batch | 범위 | 수 | check_authored err/warn | assembled | published | 날짜 | 메모 |
|---|---|---|---|---|---|---|---|
| b01 | F-001~040 | 40 | 0/18 | ✓ | ✓ | 2026-09-16 | F-001~010은 b00-pilot 승계(파일 삭제); BLD 나머지 + CRA 전부 + UNIT 앞 4개 |
| b02 | F-041~080 | 40 | 0/9 | ✓ | ✓ | 2026-09-16 | UNIT 나머지(041~062) + DG 앞부분(063~080); 마스터 14,202줄 |
| b03 | F-081~120 | 40 | 0/18 | ✓ | ✓ | 2026-09-16 | DG 나머지(081~086) + BRG 전부(087~108) + IPC 앞부분(109~120); 마스터 14,691줄 |
| b04 | F-121~160 | 40 | 0/6 | ✓ | ✓ | 2026-09-16 | IPC 나머지(121~132) + DIAG 앞부분(133~160) |
| b05 | F-161~200 | 40 | 0/7 | ✓ | ✓ | 2026-09-16 | DIAG 나머지(161~164) + UI 전부(165~194) + TST 앞부분(195~200) |
| b06 | F-201~240 | 40 | 0/8 | ✓ | ✓ | 2026-09-16 | TST 나머지(201~228) + PLT 전부(229~237) + SEC 앞부분(238~240) |
| b07 | F-241~280 | 40 | 0/3 | ✓ | ✓ | 2026-09-16 | HYP 반증 가설(241~256) + DROP 폐기(257~280) |
| b08 | F-281~304 | 24 | 0/4 | ✓ | ✓ | 2026-09-16 | DROP 나머지(281~294) + OPEN 미해결(295~304, 해결책=현재 상태+제안) — **P-C 완료** |
| maro-history-01 | Maro 고유›역사·폐기·미해결 39개 | 39 | 0/12 | ✓ | ✓ | 2026-09-16 | 첫 P-D 배치; validate 펜스-링크 검사를 줄 기반으로 수정(닫는 펜스 뒤 링크 오탐) |
| maro-nodecontract-01 | Maro 고유›노드·어트리뷰트 계약 43개 | 43 | 0/39 | ✓ | ✓ | 2026-09-16 | |
| maro-ui-01 | Maro 고유›UI(MaroUI·SONE·ONE·패널) 46개 | 46 | 0/42 | ✓ | ✓ | 2026-09-16 | |
| maro-diag-01 | Maro 고유›진단 생태계 1/2 | 45 | 0/33 | ✓ | ✓ | 2026-09-16 | |
| maro-diag-02 | Maro 고유›진단 생태계 2/2 | 45 | 0/30 | ✓ | ✓ | 2026-09-16 | |
| maro-diag-01 | Maro 고유›진단 생태계 1/2 | 45 | 0/33 | ✓ | ✓ | 2026-09-16 | |
| maro-diag-02 | Maro 고유›진단 생태계 2/2 | 45 | 0/30 | ✓ | ✓ | 2026-09-16 | |
| maro-diag-01 | Maro 고유›진단 생태계 1/2 | 45 | 0/33 | ✓ | ✓ | 2026-09-16 | |
| maro-diag-02 | Maro 고유›진단 생태계 2/2 | 45 | 0/30 | ✓ | ✓ | 2026-09-16 | |
| maro-diag-01 | Maro 고유›진단 생태계 1/2 | 45 | 0/33 | ✓ | ✓ | 2026-09-16 | |
| maro-diag-02 | Maro 고유›진단 생태계 2/2 | 45 | 0/30 | ✓ | ✓ | 2026-09-16 | |
| maro-bridge-02 | Maro 고유›브리지 런타임 잔여 | 27 | 0/20 | ✓ | ✓ | 2026-09-16 | |
| maro-lidar-01 | Maro 고유›LiDAR·포인트클라우드·충돌 | 31 | 0/32 | ✓ | ✓ | 2026-09-16 | |
| maro-testinfra-01 | Maro 고유›테스트 인프라 | 19 | 0/10 | ✓ | ✓ | 2026-09-16 | |
| maro-contract-01 | Maro 고유›계약·상수·이름 | 26 | 0/23 | ✓ | ✓ | 2026-09-16 | |
| maro-urdf-01 | Maro 고유›URDF·합성 데이터 1/2 | 25 | 0/49 | ✓ | ✓ | 2026-09-16 | |
| maro-urdf-02 | Maro 고유›URDF·합성 데이터 2/2 | 22 | 0/42 | ✓ | ✓ | 2026-09-16 | |
| cs-concurrency-01 | 컴퓨터과학 일반›동시성 | 20 | 0/11 | ✓ | ✓ | 2026-09-16 | |
| cs-os-01 | 컴퓨터과학 일반›운영체제·프로세스 | 23 | 0/9 | ✓ | ✓ | 2026-09-16 | |
| cs-design-01 | 컴퓨터과학 일반›소프트웨어 설계 원칙 1/2 | 27 | 0/16 | ✓ | ✓ | 2026-09-16 | |
| cs-design-02 | 컴퓨터과학 일반›소프트웨어 설계 원칙 2/2 | 25 | 0/15 | ✓ | ✓ | 2026-09-16 | |
| cs-ds-01 | 컴퓨터과학 일반›자료구조·알고리즘 | 16 | 0/31 | ✓ | ✓ | 2026-09-16 | |
| cs-misc-01 | 컴퓨터과학 일반›IPC·네트워크·보안 | 6 | 0/4 | ✓ | ✓ | 2026-09-16 | |
| cpp-thirdparty-01 | C++›서드파티 라이브러리 1/2 | 27 | 0/33 | ✓ | ✓ | 2026-09-17 | |
| cpp-thirdparty-02 | C++›서드파티 라이브러리 2/2 | 22 | 0/26 | ✓ | ✓ | 2026-09-17 | |
| cpp-std-01 | C++›표준 라이브러리 | 12 | 0/11 | ✓ | ✓ | 2026-09-17 | |
| cpp-core-01 | C++›언어 핵심(RAII·수명·예외) | 29 | 0/32 | ✓ | ✓ | 2026-09-17 | |
| cpp-idiom-01 | C++›관용구·패턴 | 15 | 0/21 | ✓ | ✓ | 2026-09-17 | |
| build-ctest-01 | 빌드›CTest·스테이징·vcpkg | 22 | 0/37 | ✓ | ✓ | 2026-09-17 | |
| build-cmake-01 | 빌드›CMake 1/2 | 20 | 0/41 | ✓ | ✓ | 2026-09-17 | |
| build-cmake-02 | 빌드›CMake 2/2 | 20 | 0/32 | ✓ | ✓ | 2026-09-17 | |
| build-msvc-01 | 빌드›MSVC·MSBuild 1/2 | 18 | 0/25 | ✓ | ✓ | 2026-09-17 | |
| build-msvc-02 | 빌드›MSVC·MSBuild 2/2 | 18 | 0/19 | ✓ | ✓ | 2026-09-17 | |
| build-devenv-01 | 빌드›개발 환경 | 16 | 0/27 | ✓ | ✓ | 2026-09-17 | |
| maya-small-01 | Maya›배치 모드·리깅·설정·PEM | 23 | 0/19 | ✓ | ✓ | 2026-09-17 | |
| maya-vp2-01 | Maya›Viewport 2.0 | 22 | 0/24 | ✓ | ✓ | 2026-09-17 | |
| maya-api-01 | Maya›C++ API 1/3 | 27 | 0/20 | ✓ | ✓ | 2026-09-17 | |
| maya-api-02 | Maya›C++ API 2/3 | 26 | 0/10 | ✓ | ✓ | 2026-09-17 | |
| maya-api-03 | Maya›C++ API 3/3 | 25 | 0/27 | ✓ | ✓ | 2026-09-17 | |
| maya-dg-01 | Maya›DG 1/2 | 32 | 0/30 | ✓ | ✓ | 2026-09-17 | |
| maya-dg-02 | Maya›DG 2/2 | 31 | 0/29 | ✓ | ✓ | 2026-09-17 | |
| maya-plugin-01 | Maya›플러그인 아키텍처 | 24 | 0/20 | ✓ | ✓ | 2026-09-17 | |
| maya-cmd-01 | Maya›커맨드·undo | 16 | 0/21 | ✓ | ✓ | 2026-09-17 | |
| maya-arnold-01 | Maya›카메라·렌더링(Arnold) | 26 | 0/35 | ✓ | ✓ | 2026-09-17 | |
| maya-qt-01 | Maya›Qt 통합 | 18 | 0/16 | ✓ | ✓ | 2026-09-17 | |
| maya-dag-01 | Maya›DAG | 24 | 0/26 | ✓ | ✓ | 2026-09-17 | |
| maya-mod-01 | Maya›배포(모듈 파일) | 14 | 0/12 | ✓ | ✓ | 2026-09-17 | |
| maya-ui-01 | Maya›UI 컨트롤 1/2 | 17 | 0/12 | ✓ | ✓ | 2026-09-17 | |
| maya-ui-02 | Maya›UI 컨트롤 2/2 | 17 | 0/19 | ✓ | ✓ | 2026-09-17 | |
| maya-py-01 | Maya›Python 층 1/2 | 29 | 0/19 | ✓ | ✓ | 2026-09-17 | |
| maya-py-02 | Maya›Python 층 2/2 | 22 | 0/21 | ✓ | ✓ | 2026-09-17 | |
| maya-mel-01 | Maya›MEL | 22 | 0/17 | ✓ | ✓ | 2026-09-17 | |
| maya-unit-01 | Maya›단위 체계 | 18 | 0/10 | ✓ | ✓ | 2026-09-17 | |
| pyqt-pyside-01 | Python·Qt›PySide6/Qt 1/2 | 27 | 0/22 | ✓ | ✓ | 2026-09-17 | |
| pyqt-pyside-02 | Python·Qt›PySide6/Qt 2/2 | 25 | 0/21 | ✓ | ✓ | 2026-09-17 | |
| pyqt-py-01 | Python·Qt›Python 언어·표준 라이브러리 | 30 | 0/11 | ✓ | ✓ | 2026-09-17 | |
| ros-rclcpp-01 | ROS 2›rclcpp·클라이언트 계층 | 15 | 0/8 | ✓ | ✓ | 2026-09-17 | |
| ros-msg-01 | ROS 2›메시지·토픽·QoS | 26 | 0/10 | ✓ | ✓ | 2026-09-17 | |
| ros-misc-01 | ROS 2›생태계·도구+URDF+TF·REP+Windows 통합·빌드 | 31 | 0/12 | ✓ | ✓ | 2026-09-17 | |
| ros-misc-01 | ROS 2›생태계·도구+URDF+TF·REP+Windows 통합·빌드 | 31 | 0/12 | ✓ | ✓ | 2026-09-17 | |
| ros-misc-01 | ROS 2›생태계·도구+URDF+TF·REP+Windows 통합·빌드 | 31 | 0/12 | ✓ | ✓ | 2026-09-17 | |
| ros-misc-01 | ROS 2›생태계·도구+URDF+TF·REP+Windows 통합·빌드 | 31 | 0/12 | ✓ | ✓ | 2026-09-17 | |
| geo-hull-01 | 기하·수학›계산기하 | 12 | 0/5 | ✓ | ✓ | 2026-09-17 | |
| geo-coord-01 | 기하·수학›좌표계·변환 | 22 | 0/23 | ✓ | ✓ | 2026-09-17 | |
| geo-misc-01 | 기하·수학›색·영상+회전 표현+카메라 모델+수치 | 24 | 0/21 | ✓ | ✓ | 2026-09-24 | |
| fmt-01 | 파일 포맷·인코딩(전체) | 25 | 0/10 | ✓ | ✓ | 2026-09-24 | |
| win-kernel-01 | Windows›커널 객체·동기화 1/2 | 24 | 0/8 | ✓ | ✓ | 2026-09-24 | |
| win-kernel-02 | Windows›커널 객체·동기화 2/2 | 24 | 0/2 | ✓ | ✓ | 2026-09-24 | 파이프라인 스크립트 temp 삭제 → 트랜스크립트에서 복구, 라이브 대조 0 diff |
| win-pipe-01 | Windows›명명된 파이프·I/O | 27 | 0/5 | ✓ | ✓ | 2026-09-24 | |
| win-job-01 | Windows›프로세스·job object | 21 | 0/0 | ✓ | ✓ | 2026-09-24 | |
| win-dbg-01 | Windows›디버깅 | 19 | 0/2 | ✓ | ✓ | 2026-09-24 | |
| win-misc-01 | Windows›로더·DLL+파일시스템·시간+보안 | 23 | 0/1 | ✓ | ✓ | 2026-09-24 | |
| win-com-01 | Windows›COM·WMI | 20 | 0/4 | ✓ | ✓ | 2026-09-24 | Windows 카테고리 완료 |
| proc-sdd-01 | 개발 프로세스›SDD·리뷰 흐름+문서 관례 | 29 | 0/11 | ✓ | ✓ | 2026-09-24 | 배치 예시 펜스에 `##`/`###` 줄을 두면 parse_master가 절을 잘라 먹음(들여쓰기로 회피) |
| proc-test-01 | 개발 프로세스›테스트 설계·변이 검증 1/2 | 22 | 0/1 | ✓ | ✓ | 2026-09-24 | |
| proc-test-02 | 개발 프로세스›테스트 설계 2/2+디버깅 절차+관찰 | 31 | 0/2 | ✓ | ✓ | 2026-09-24 | **P-D 완료: 1624/1624** |
| maro-history-01 | Maro 고유›역사·폐기·미해결 39개 | 39 | 0/12 | ✓ | ✓ | 2026-09-16 | 첫 P-D 배치; validate 펜스-링크 검사를 줄 기반으로 수정(닫는 펜스 뒤 링크 오탐) |
| maro-history-01 | Maro 고유›역사·폐기·미해결 39개 | 39 | 0/12 | ✓ | ✓ | 2026-09-16 | 첫 P-D 배치; validate 펜스-링크 검사를 줄 기반으로 수정(닫는 펜스 뒤 링크 오탐) |
| maro-history-01 | Maro 고유›역사·폐기·미해결 39개 | 39 | 0/12 | ✓ | ✓ | 2026-09-16 | 첫 P-D 배치; validate 펜스-링크 검사를 줄 기반으로 수정(닫는 펜스 뒤 링크 오탐) |
| pilot-01 | Maro 고유›브리지 런타임 10개 | 10 | 0/17 | ✓ | ✓ | 2026-09-16 | 파일럿; 예시·관련 코드 포함(7필드) |

### 세션 절차(집필)
1. `python status.py` → 다음 배치 확인. 재료: 마스터 F-블록/§13 항목 + `work/context.json` 발췌 + 필요 시 리포 소스
2. 배치 파일 작성(edit14/bNN.md 또는 edit16/<cat>-<branch>-NN.md; 헤딩 + 집필 필드만). 용어는 7필드 전부: 예시(사용 장면·코드 펜스), 관련 코드(`- path:줄 — 역할` 불릿, 테스트 포함). 예시의 씬 오브젝트 가명은 소문자 시작으로(WARN만).
3. `python build_symbols.py && python check_authored.py <batch>` → 오류 0
4. `python assemble_failures.py --toc` 또는 `python assemble_terms.py --toc` → `python check_master.py` → `python write_repo.py`
5. `python parse_master.py && python build_index.py && python build_context.py && python emit_vault.py --clean && python validate_vault.py staging && python publish_vault.py && python validate_vault.py live`
6. 이 표와 보강 상태 줄 갱신. 히어독은 백슬래시를 망가뜨리므로 배치 파일은 Write 도구로 쓴다.

## 재실행 규칙 (P4 이후)
- `docs/maro-master-reference.md` 가 이제 편집본 자체다. **transform_master.py 를 다시 돌리지 말 것**(S5가 §15를 옛 terms-collected로 되돌리고 S3/S8이 이미 적용된 본문을 재가공).
- 이후 수정은 리포 파일을 직접 고친 뒤: `copy docs/... → work/master.edited.md` → `parse_master.py` → `build_index.py` → (`sec15.py` + 수동 §15 교체가 필요하면 assemble 대신 직접 붙여넣기) → `emit_vault.py --clean` → `validate_vault.py staging` → `publish_vault.py` → `validate_vault.py live`.
- edit/ chunk 파일과 work/master.v0.md 는 이력 보관용(원본 백업: work/master.orig.bak).

## 노트 보강(2026-09-16 계획: 기계 발췌 + 전 노트 집필) — 계획 파일 C:\Users\ckd30\.claude\plans\wise-kindling-truffle.md
- 기준선: work/master.v1.md (2026-09-16 리포 마스터 동결, 12,916줄). check_master 기본 base.
- [x] P-A 기계 발췌(2026-09-16): textutil.py / parse_master(다중 행 F-필드·§16·outro) / build_symbols.py / build_context.py(2,062 유닛; 용어 발췌 0건 163, 실패 0건 11) / linkify(form_at·mode, ASCII 경계에 한글 조사 허용 → 링크 20,632→37,418) / emit_vault(새 골격) / validate_vault(골격·authored·길이) / check_master(--base, §14 원본 필드 동일, §16) / assemble_failures.py / assemble_terms.py / check_authored.py / status.py. 스테이징·라이브 ALL OK, 게시 완료.
- [ ] P-B 파일럿: edit14/b00-pilot.md(F-001~010) + edit16/pilot-01.md(브리지 런타임 10개) → 사용자 Obsidian 검토 → 골격 동결
- [ ] P-C 실패 집필 b01~b08 · [ ] P-D 용어 집필(가지 순, Maro 고유부터)

### 보강 상태
failures 0/304 · terms 0/1624 · next: b00-pilot

| batch | 범위 | 수 | check_authored err/warn | assembled | published | 날짜 | 메모 |
|---|---|---|---|---|---|---|---|

### 세션 절차(집필)
1. `python status.py` → 다음 배치 확인. 재료: 마스터 F-블록/§13 항목 + `work/context.json` 발췌 + 필요 시 리포 소스
2. 배치 파일 작성(edit14/bNN.md 또는 edit16/<cat>-<branch>-NN.md; 헤딩 + 집필 필드만)
3. `python build_symbols.py && python check_authored.py <batch>` → 오류 0
4. `python assemble_failures.py --toc` 또는 `python assemble_terms.py --toc` → `python check_master.py` → `python write_repo.py`
5. `python parse_master.py && python build_index.py && python build_context.py && python emit_vault.py --clean && python validate_vault.py staging && python publish_vault.py && python validate_vault.py live`
6. 이 표와 보강 상태 줄 갱신

## 재실행 규칙 (P4 이후)
- `docs/maro-master-reference.md` 가 이제 편집본 자체다. **transform_master.py 를 다시 돌리지 말 것**(S5가 §15를 옛 terms-collected로 되돌리고 S3/S8이 이미 적용된 본문을 재가공).
- 이후 수정은 리포 파일을 직접 고친 뒤: `copy docs/... → work/master.edited.md` → `parse_master.py` → `build_index.py` → (`sec15.py` + 수동 §15 교체가 필요하면 assemble 대신 직접 붙여넣기) → `emit_vault.py --clean` → `validate_vault.py staging` → `publish_vault.py` → `validate_vault.py live`.
- edit/ chunk 파일과 work/master.v0.md 는 이력 보관용(원본 백업: work/master.orig.bak).

## 노트 보강(2026-09-16 계획: 기계 발췌 + 전 노트 집필) — 계획 파일 C:\Users\ckd30\.claude\plans\wise-kindling-truffle.md
- 기준선: work/master.v1.md (2026-09-16 리포 마스터 동결, 12,916줄). check_master 기본 base.
- [x] P-A 기계 발췌(2026-09-16): textutil.py / parse_master(다중 행 F-필드·§16·outro) / build_symbols.py / build_context.py(2,062 유닛; 용어 발췌 0건 163, 실패 0건 11) / linkify(form_at·mode, ASCII 경계에 한글 조사 허용 → 링크 20,632→37,418) / emit_vault(새 골격) / validate_vault(골격·authored·길이) / check_master(--base, §14 원본 필드 동일, §16) / assemble_failures.py / assemble_terms.py / check_authored.py / status.py. 스테이징·라이브 ALL OK, 게시 완료.
- [ ] P-B 파일럿: edit14/b00-pilot.md(F-001~010) + edit16/pilot-01.md(브리지 런타임 10개) → 사용자 Obsidian 검토 → 골격 동결
- [ ] P-C 실패 집필 b01~b08 · [ ] P-D 용어 집필(가지 순, Maro 고유부터)

### 보강 상태
failures 0/304 · terms 0/1624 · next: b00-pilot

| batch | 범위 | 수 | check_authored err/warn | assembled | published | 날짜 | 메모 |
|---|---|---|---|---|---|---|---|

### 세션 절차(집필)
1. `python status.py` → 다음 배치 확인. 재료: 마스터 F-블록/§13 항목 + `work/context.json` 발췌 + 필요 시 리포 소스
2. 배치 파일 작성(edit14/bNN.md 또는 edit16/<cat>-<branch>-NN.md; 헤딩 + 집필 필드만)
3. `python build_symbols.py && python check_authored.py <batch>` → 오류 0
4. `python assemble_failures.py --toc` 또는 `python assemble_terms.py --toc` → `python check_master.py` → `python write_repo.py`
5. `python parse_master.py && python build_index.py && python build_context.py && python emit_vault.py --clean && python validate_vault.py staging && python publish_vault.py && python validate_vault.py live`
6. 이 표와 보강 상태 줄 갱신

## 재실행 규칙 (P4 이후)
- `docs/maro-master-reference.md` 가 이제 편집본 자체다. **transform_master.py 를 다시 돌리지 말 것**(S5가 §15를 옛 terms-collected로 되돌리고 S3/S8이 이미 적용된 본문을 재가공).
- 이후 수정은 리포 파일을 직접 고친 뒤: `copy docs/... → work/master.edited.md` → `parse_master.py` → `build_index.py` → (`sec15.py` + 수동 §15 교체가 필요하면 assemble 대신 직접 붙여넣기) → `emit_vault.py --clean` → `validate_vault.py staging` → `publish_vault.py` → `validate_vault.py live`.
- edit/ chunk 파일과 work/master.v0.md 는 이력 보관용(원본 백업: work/master.orig.bak).

## 노트 보강(2026-09-16 계획: 기계 발췌 + 전 노트 집필) — 계획 파일 C:\Users\ckd30\.claude\plans\wise-kindling-truffle.md
- 기준선: work/master.v1.md (2026-09-16 리포 마스터 동결, 12,916줄). check_master 기본 base.
- [x] P-A 기계 발췌(2026-09-16): textutil.py / parse_master(다중 행 F-필드·§16·outro) / build_symbols.py / build_context.py(2,062 유닛; 용어 발췌 0건 163, 실패 0건 11) / linkify(form_at·mode, ASCII 경계에 한글 조사 허용 → 링크 20,632→37,418) / emit_vault(새 골격) / validate_vault(골격·authored·길이) / check_master(--base, §14 원본 필드 동일, §16) / assemble_failures.py / assemble_terms.py / check_authored.py / status.py. 스테이징·라이브 ALL OK, 게시 완료.
- [ ] P-B 파일럿: edit14/b00-pilot.md(F-001~010) + edit16/pilot-01.md(브리지 런타임 10개) → 사용자 Obsidian 검토 → 골격 동결
- [ ] P-C 실패 집필 b01~b08 · [ ] P-D 용어 집필(가지 순, Maro 고유부터)

### 보강 상태
failures 0/304 · terms 0/1624 · next: b00-pilot

| batch | 범위 | 수 | check_authored err/warn | assembled | published | 날짜 | 메모 |
|---|---|---|---|---|---|---|---|

### 세션 절차(집필)
1. `python status.py` → 다음 배치 확인. 재료: 마스터 F-블록/§13 항목 + `work/context.json` 발췌 + 필요 시 리포 소스
2. 배치 파일 작성(edit14/bNN.md 또는 edit16/<cat>-<branch>-NN.md; 헤딩 + 집필 필드만)
3. `python build_symbols.py && python check_authored.py <batch>` → 오류 0
4. `python assemble_failures.py --toc` 또는 `python assemble_terms.py --toc` → `python check_master.py` → `python write_repo.py`
5. `python parse_master.py && python build_index.py && python build_context.py && python emit_vault.py --clean && python validate_vault.py staging && python publish_vault.py && python validate_vault.py live`
6. 이 표와 보강 상태 줄 갱신
