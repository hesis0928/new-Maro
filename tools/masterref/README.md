# masterref — 마스터 레퍼런스 → Obsidian 보관함 파이프라인

`docs/maro-master-reference.md`(마스터)를 파싱해 Obsidian 보관함
`C:\Users\ckd30\OneDrive\Documents\Maro Project\Master Reference`(3,965 노트)를 생성·게시한다.
2026-09-24에 임시 스크래치패드에서 이곳으로 옮겼다 — 임시 폴더 정리로 스크립트가 통째로
날아간 적이 있어 저장소 안으로 들였다.

## 배치 집필 루프 (§16 용어 / §14 실패)

```bash
cd tools/masterref
python status.py                                   # 다음 가지와 진행률
python branches.py "<카테고리>"                     # 카테고리별 남은 가지
python dump_material.py "<카테고리>" "<가지>" work/tNN.txt   # 집필 재료 덤프
# edit16/<배치>.md 작성 (7필드: 직관·동작·예시·관련 코드·증거·함정·교훈)
python build_symbols.py                            # 리포 식별자 색인(검사용)
python check_authored.py edit16/<배치>.md           # OK 나올 때까지 — ERROR 0이어야 함
python assemble_terms.py --toc && python check_master.py && python write_repo.py
python parse_master.py && python build_index.py && python build_context.py
python emit_vault.py --clean && python validate_vault.py staging
python publish_vault.py && python validate_vault.py live
```

`LEDGER.md`에 배치 행과 진행률을 기록한다.

## 레이아웃

| 경로 | 내용 | git |
|---|---|---|
| `*.py` | 파이프라인 스크립트 | 추적 |
| `build_taxonomy.py` | 용어 분류(카테고리·가지) — `config.SCRATCH`가 이 폴더를 가리킨다 | 추적 |
| `edit16/` | 집필 배치 원본(§16 용어) | 추적 |
| `LEDGER.md` | 배치 원장·진행률 | 추적 |
| `archive/` | 일회성 마이그레이션·패치 스크립트(이력 보존, 재실행 금지) | 추적 |
| `work/` | 중간 산출물(model/index/context/symbols json, `master.edited.md`, 덤프) | 무시 |
| `out/` | 스테이징 보관함(게시 전 검증 대상) | 무시 |
| `reports/` | 검사 리포트 | 무시 |

## 규칙

- **`transform_master.py`는 절대 재실행하지 않는다.** 마스터 1회 변환용이며 지금 다시 돌리면
  이후의 모든 집필이 덮인다. `archive/`의 스크립트도 마찬가지로 재실행 금지.
- `work/master.v1.md`는 `check_master.py`의 기준선(사실 보존 비교용)이다. 현재 파일은 원래의
  변환 산출물이 아니라 **마지막 검증본 스냅샷**이다(원본은 2026-09-24 스크래치패드 소실 때 유실).
- 배치 파일의 코드 펜스 안에 `#`/`##`/`###`로 시작하는 줄을 두지 않는다 — `parse_master.py`가
  그 줄에서 절을 잘라 뒤쪽 블록을 조용히 버린다(2026-09-24에 한 번 겪음).
- **2MB가 넘는 마크다운 파일을 보관함 안에 두지 않는다.** Obsidian 렌더러가 인덱싱 중
  기가바이트 단위로 메모리를 먹고 ~3.5MB에서 V8 힙 상한에 부딪혀 죽는다(창만 남아 회색 화면).
  마스터 원본(`docs/maro-master-reference.md`)과 `work/master.v1.md`는 보관함 밖에만 둔다 —
  Obsidian의 '제외된 파일' 설정은 검색·그래프에서만 빼고 인덱싱은 그대로 하므로 소용없다(2026-09-26).
- 게시 전후로 `validate_vault.py`가 staging·live 모두 ALL OK여야 한다.
- 파이프라인을 고친 뒤에는 `emit_vault.py --clean` 결과를 라이브와 `diff -rq`로 비교해
  차이 0을 확인한다(이 폴더로 옮긴 뒤 그렇게 검증했다).

## 경로 설정

`config.py`가 유일한 경로 원천이다. `MASTER_SRC`는 저장소 루트에서 유도하고,
`VAULT_ROOT`(OneDrive 보관함)만 절대 경로다 — 다른 머신에서 쓰려면 그 줄을 바꾼다.
