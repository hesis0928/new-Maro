# -*- coding: utf-8 -*-
"""리포 소스의 식별자·경로·줄수 → work/symbols.json (HEAD 해시로 캐시). check_authored.py가 집필문의 증거를 대조할 때 쓴다.
사용: python build_symbols.py [--force]"""
import io, re, sys, json, pathlib, subprocess, collections
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config as C

REPO = C.MASTER_SRC.parents[1]
TEXT_EXT = {".h", ".hpp", ".cpp", ".c", ".py", ".txt", ".cmake", ".json", ".md", ".ps1", ".mel", ".yml", ".yaml", ".xml", ".bat", ".ini", ".cfg", ".toml", ".mod"}
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
JOINED = re.compile(r"[A-Za-z_][\w]*(?:(?:::|\.)[A-Za-z_][\w]*)+")


def git(*args):
    return subprocess.run(["git", *args], cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def main():
    head = git("rev-parse", "HEAD").strip()
    out_path = C.WORK / "symbols.json"
    if out_path.exists() and "--force" not in sys.argv:
        old = json.load(io.open(out_path, encoding="utf-8"))
        if old.get("head") == head:
            print(f"symbols.json up to date (HEAD {head[:7]}): {len(old['idents'])} idents, {len(old['files'])} files"); return
    files = [f for f in git("ls-files").split("\n") if f.strip()]
    idents = set(); joined = set(); finfo = {}
    for f in files:
        p = REPO / f
        if p.suffix.lower() not in TEXT_EXT and p.name != "CMakeLists.txt": continue
        try:
            txt = io.open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        finfo[f] = txt.count("\n") + 1
        idents.update(IDENT.findall(txt)); joined.update(JOINED.findall(txt))
    data = {"head": head, "files": finfo, "idents": sorted(idents), "joined": sorted(joined)}
    io.open(out_path, "w", encoding="utf-8").write(json.dumps(data, ensure_ascii=False))
    print(f"symbols.json: HEAD {head[:7]}, {len(finfo)} text files, {len(idents)} idents, {len(joined)} joined")


if __name__ == "__main__":
    main()
