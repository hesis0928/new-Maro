# -*- coding: utf-8 -*-
"""work/index.json(build_index 결과, §13 용어 표의 단일 원천) → §15 용어 분류 체계 → edit/c15.md.
transform 단계의 §15(terms-collected 기반, 1,597개)를 대체해 보관함 Maro Note 층과 같은 용어 집합(1,614개)을 리포 파일에도 싣는다.
사용: python sec15.py   (다음에 python assemble_master.py --toc)"""
import io, json, collections, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config as C
from build_index import TOP_ORDER, SUBS


def sec_ref(s): return "§13." + s


def secs_ordered(e):
    """처음 완전 해설된 절(explained_in)을 앞에, 나머지는 등장 순."""
    first = e.get("explained_in") or e["secs"][0]
    return [first] + [s for s in e["secs"] if s != first]


def secs_str(e):
    ss = secs_ordered(e)
    return ", ".join(sec_ref(s) for s in ss[:3]) + (" 외" if len(ss) > 3 else "")


def main():
    idx = json.load(io.open(C.WORK / "index.json", encoding="utf-8"))
    entries = idx["entries"]  # 삽입 순서 = §13 등장 순서
    by_top = collections.OrderedDict((t, collections.OrderedDict()) for t in TOP_ORDER)
    for e in entries.values():
        by_top[e["top"]].setdefault(e["sub"], []).append(e)
    n_terms = len(entries)
    n_deep = sum(1 for e in entries.values() if e["depth"] == "심화")
    n_subs = sum(len(v) for v in by_top.values())

    out = []
    out.append("## 15. 용어 분류 체계 — 카테고리 트리와 종속 사슬\n")
    out.append(f"**한 줄 요약:** §13의 모든 용어 표에서 추출한 **{n_terms:,}개 용어**(심화 {n_deep}개)를 11개 최상위 카테고리 → {n_subs}개 중간 가지 → "
               "용어의 사슬로 정리한 분류 체계입니다 — §11 사전은 한 줄 정의, §13은 문맥·하위지식, §15는 \"이 용어를 이해하려면 어떤 상위 개념과\n"
               "하위 개념이 필요한가\"를 답하며, Obsidian 보관함의 `Maro Note` 층이 이 트리를 폴더 구조로 그대로 옮깁니다.\n")
    out.append(f"§13의 모든 용어 표에서 추출한 **{n_terms}개 용어**(복합 셀은 ` / `로 분리, 백틱·괄호 표기를 정규화해 중복 통합)를 "
               "11개 최상위 카테고리 → 중간 종속 개념 → 용어의 사슬로 정리한다. §11 사전은 한 줄 정의, §13은 문맥·하위지식, §15는 "
               "\"이 용어를 이해하려면 어떤 상위 개념과 하위 개념이 필요한가\"를 답한다.\n")
    out.append("### 15.0 읽는 법\n")
    out.append("**한 줄 요약:** 15.1은 들여쓰기 트리(최상위 → 중간 가지 → 용어, ★=심화), 15.2는 용어별 사슬·필요 하위 개념·해설 위치 표, 15.3은\n"
               "카테고리별 통계이며 카테고리 판정은 §13 용어 표의 `분류` 열에서 기계적으로 유도했습니다.\n")
    out.append("- **15.1 카테고리 트리**: 최상위 → 중간 종속 개념(사슬) → 용어. 각 중간 노드에 `필요 하위 개념`(그 가지의 용어를 이해하는 데 전제되는 개념)을 적는다. "
               "들여쓰기 목록이라 어떤 마크다운 뷰어에서도 읽힌다.\n"
               "- **15.2 용어별 사슬 표**: `용어 | 사슬(최상위 > 중간 > 용어) | 필요 하위 개념 | 해설(깊이)`. 해설 열은 `§13.x.y (심화|개념)` 꼴이며, `심화`인 용어는 해설 위치의 "
               "**하위지식** 블록에 수반 개념이 전부 나열돼 있다. 용어가 여러 절에 나오면 처음 완전 해설된 절을 먼저 적는다.\n"
               "- 카테고리 판정은 §13 용어 표의 `분류` 열에서 기계적으로 유도했으며(예: `Maya·DG` → Maya > DG), 경계 사례는 §13의 문맥을 기준으로 삼는다.\n")
    # 15.1
    out.append("### 15.1 카테고리 트리\n")
    out.append(f"**한 줄 요약:** 11개 최상위 카테고리의 들여쓰기 트리입니다 — 가지마다 사슬과 필요 하위 개념을 적고, 용어마다 처음 완전 해설된 §13 항목을\n"
               "가리키며 ★는 심화(하위지식 블록 있음), ·는 개념(단발 설명)입니다.\n")
    for top in TOP_ORDER:
        subs = by_top[top]
        total = sum(len(v) for v in subs.values())
        out.append(f"#### 15.1.{TOP_ORDER.index(top) + 1} {top} ({total}개)\n")
        out.append(f"- **{top}**")
        for sub, items in subs.items():
            chain, prereq = SUBS.get((top, sub), (sub, ""))
            out.append(f"  - **{sub}** — 사슬: {top} > {chain} · 필요 하위 개념: {prereq}")
            for e in items:
                d = "★" if e["depth"] == "심화" else "·"
                out.append(f"    - {d} {e["term"]} (→ {sec_ref(secs_ordered(e)[0])})")
        out.append("")
    out.append("★ = 심화(해당 §13 항목의 하위지식 블록 참조), · = 개념(단발 설명으로 충분)\n")
    # 15.2
    out.append("### 15.2 용어별 종속 사슬 표\n")
    out.append(f"**한 줄 요약:** {n_terms:,}개 용어 각각의 사슬(최상위 > 중간 > 용어)·필요 하위 개념·해설 위치(깊이)를 한 행씩 적은 표로, 심화 용어는 해설\n"
               "절의 하위지식 블록을 함께 가리킵니다.\n")
    out.append("| 용어 | 사슬 | 필요 하위 개념 | 해설(깊이) |")
    out.append("|---|---|---|---|")
    for top in TOP_ORDER:
        for sub, items in by_top[top].items():
            chain, prereq = SUBS.get((top, sub), (sub, ""))
            for e in items:
                pre = prereq + (f" · **{sec_ref(secs_ordered(e)[0])} 하위지식**" if e["depth"] == "심화" else "")
                term = e["term"].replace("|", "\\|")
                out.append(f"| {term} | {top} > {chain} > 용어 | {pre} | {secs_str(e)} ({e['depth']}) |")
    out.append("")
    # 15.3
    out.append("### 15.3 통계\n")
    out.append(f"**한 줄 요약:** 카테고리별 중간 가지 수·용어 수·심화 용어 수입니다 — 합계 {n_subs} 가지, {n_terms:,} 용어, 심화 {n_deep}개.\n")
    out.append("| 최상위 카테고리 | 중간 가지 수 | 용어 수 | 심화 용어 수 |")
    out.append("|---|---|---|---|")
    for top in TOP_ORDER:
        subs = by_top[top]
        n = sum(len(v) for v in subs.values()); d = sum(1 for v in subs.values() for e in v if e["depth"] == "심화")
        out.append(f"| {top} | {len(subs)} | {n} | {d} |")
    out.append(f"| **합계** | {n_subs} | {n_terms} | {n_deep} |")
    out.append("")
    io.open(C.EDIT / "c15.md", "w", encoding="utf-8", newline="\n").write("\n".join(out))
    print(f"wrote edit/c15.md: {n_terms} terms, {n_subs} branches, {n_deep} deep")


if __name__ == "__main__":
    main()
