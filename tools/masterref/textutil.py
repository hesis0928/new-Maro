# -*- coding: utf-8 -*-
"""텍스트 유틸 — 하드 랩 해제(unwrap)와 한국어 문장 분리. emit_vault/build_context/check_authored가 공유한다."""
import re

BLOCK_START = re.compile(r"^(\s*([-*+]|\d+\.)\s+|#{1,6} |\||```|>|\*\*[^*]+:\*\*\s*$)")


def unwrap(lines):
    """하드 랩 해제: 문단/불릿 연속 줄을 한 줄로. 펜스·표·헤딩·빈 줄은 보존."""
    out = []; in_fence = False
    for l in lines:
        if l.strip().startswith("```"):
            in_fence = not in_fence; out.append(l); continue
        if in_fence or l.strip() == "" or l.startswith("|") or l.startswith("#"):
            out.append(l); continue
        if out and out[-1].strip() != "" and not out[-1].startswith(("|", "#", "```")) and not in_fence:
            prev = out[-1]
            is_new_block = bool(BLOCK_START.match(l)) and not re.match(r"^\s{2,}\S", l) or bool(re.match(r"^\s*([-*+]|\d+\.)\s+", l))
            if not is_new_block and not prev.endswith("  "):
                out[-1] = prev.rstrip() + " " + l.strip(); continue
        out.append(l)
    return out


_CODE = re.compile(r"`[^`\n]+`")


def split_sentences(text, max_len=350):
    """코드 스팬을 가린 채 `다.`/`.`/`!`/`?` + 공백에서 문장을 나눈다. 너무 긴 '문장'은 통째로 둔다.
    `§6.6`·소수·`e.g.` 같은 점은 뒤에 공백+비공백이 오지 않거나 코드 스팬 안이라 안 갈린다."""
    masks = []
    def mask(m):
        masks.append(m.group(0)); return f"\x00{len(masks) - 1}\x00"
    t = _CODE.sub(mask, text)
    parts = re.split(r"(?<=[.!?。])\s+(?=\S)", t)
    out = []
    for p in parts:
        p = re.sub(r"\x00(\d+)\x00", lambda m: masks[int(m.group(1))], p).strip()
        if p: out.append(p)
    # 너무 잘게 갈린 조각(예: "1." 번호)은 앞 조각에 붙인다
    merged = []
    for p in out:
        if merged and len(p) < 8:
            merged[-1] = merged[-1] + " " + p
        else:
            merged.append(p)
    return [p if len(p) <= max_len or True else p for p in merged]


def norm_key(s):
    """중복 판정용 정규화: 공백·백틱·강조·구두점 제거, 소문자"""
    return re.sub(r"[\s`*_\-—·,.;:()\[\]\"'“”‘’]", "", s).lower()
