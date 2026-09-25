# -*- coding: utf-8 -*-
"""work/master.edited.md → docs/maro-master-reference.md (LF, UTF-8 no BOM, 임시 파일 후 원자 교체).
머리말에 편집 이력 한 줄을 없으면 추가한다. 사용: python write_repo.py [--dry]"""
import io, os, pathlib, sys, re
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config as C

NOTE = ("> 가독성 편집(절·소절 `**한 줄 요약:**`, 라벨 블록, §14 항목 블록화, §15를 §13 용어 표에서 재생성) + Obsidian 보관함 "
        "`Master Reference/` 분해: 2026-09-15. 편집 파이프라인은 `tools/masterref/`(이관 예정) — 이 파일이 단일 원천이다.")


def main():
    src = io.open(C.WORK / "master.edited.md", encoding="utf-8").read()
    lines = src.split("\n")
    if not any(l.startswith("> 가독성 편집(") for l in lines[:12]):
        # 머리말 인용 블록(> ...)의 마지막 줄 뒤에 삽입
        j = 0
        while j < 12 and (lines[j].startswith(">") or lines[j].startswith("#") or lines[j].strip() == ""):
            j += 1
        k = max(i for i in range(j) if lines[i].startswith(">")) + 1
        lines.insert(k, NOTE)
    text = "\n".join(lines)
    if not text.endswith("\n"): text += "\n"
    dst = pathlib.Path(C.MASTER_SRC)
    print(f"{dst}: {text.count(chr(10))} lines, {len(text.encode('utf-8')):,} bytes")
    if "--dry" in sys.argv: return
    tmp = dst.with_suffix(".md.tmp")
    io.open(tmp, "w", encoding="utf-8", newline="\n").write(text)
    os.replace(tmp, dst)
    print("written")


if __name__ == "__main__":
    main()
