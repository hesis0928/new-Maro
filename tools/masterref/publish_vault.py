# -*- coding: utf-8 -*-
"""스테이징 out/Master Reference → 라이브(OneDrive) 미러. robocopy /MIR (라이브에만 있는 파일은 삭제된다)."""
import subprocess, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config as C

C.LIVE_DIR.mkdir(parents=True, exist_ok=True)
cmd = ["robocopy", str(C.OUT), str(C.LIVE_DIR), "/MIR", "/R:3", "/W:2", "/NFL", "/NDL", "/NJH", "/NP", "/XD", ".obsidian"]
r = subprocess.run(cmd, capture_output=True, text=True, encoding="cp949", errors="replace")
print(r.stdout[-1500:])
# robocopy 종료 코드: <8 성공
print("robocopy exit", r.returncode, "OK" if r.returncode < 8 else "FAIL")
n = sum(1 for _ in C.LIVE_DIR.rglob("*.md"))
print("live notes", n)
