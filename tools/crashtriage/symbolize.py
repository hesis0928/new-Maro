"""maro.mll의 RVA를 PDB로 함수명+파일:줄로 푼다. 디버거 설치 없이
Windows에 항상 있는 dbghelp.dll을 ctypes로 직접 쓴다.

usage: python symbolize.py <maro.mll> <rva-hex> [<rva-hex> ...]
"""
import ctypes
import ctypes.wintypes as wt
import sys

dbghelp = ctypes.WinDLL("dbghelp.dll")
FAKE_PROC = ctypes.c_void_p(0x1000)
BASE = 0x10000000


class SYMBOL_INFO(ctypes.Structure):
    _fields_ = [
        ("SizeOfStruct", wt.ULONG), ("TypeIndex", wt.ULONG),
        ("Reserved", ctypes.c_ulonglong * 2), ("Index", wt.ULONG),
        ("Size", wt.ULONG), ("ModBase", ctypes.c_ulonglong),
        ("Flags", wt.ULONG), ("Value", ctypes.c_ulonglong),
        ("Address", ctypes.c_ulonglong), ("Register", wt.ULONG),
        ("Scope", wt.ULONG), ("Tag", wt.ULONG), ("NameLen", wt.ULONG),
        ("MaxNameLen", wt.ULONG), ("Name", ctypes.c_char * 2000),
    ]


class IMAGEHLP_LINE64(ctypes.Structure):
    _fields_ = [
        ("SizeOfStruct", wt.DWORD), ("Key", ctypes.c_void_p),
        ("LineNumber", wt.DWORD), ("FileName", ctypes.c_char_p),
        ("Address", ctypes.c_ulonglong),
    ]


dbghelp.SymSetOptions(0x00000002 | 0x00000004 | 0x00000010)  # UNDNAME|DEFERRED|LOAD_LINES
if not dbghelp.SymInitialize(FAKE_PROC, None, False):
    raise SystemExit("SymInitialize failed: %d" % ctypes.get_last_error())

image = sys.argv[1]
dbghelp.SymLoadModuleEx.restype = ctypes.c_ulonglong
dbghelp.SymLoadModuleEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p,
                                    ctypes.c_char_p, ctypes.c_ulonglong, wt.DWORD,
                                    ctypes.c_void_p, wt.DWORD]
loaded = dbghelp.SymLoadModuleEx(FAKE_PROC, None, image.encode(), None,
                                 BASE, 0, None, 0)
if not loaded:
    raise SystemExit("SymLoadModuleEx failed: %d" % ctypes.GetLastError())
print("loaded %s at 0x%X" % (image, loaded))

dbghelp.SymFromAddr.argtypes = [ctypes.c_void_p, ctypes.c_ulonglong,
                                ctypes.POINTER(ctypes.c_ulonglong),
                                ctypes.POINTER(SYMBOL_INFO)]
dbghelp.SymGetLineFromAddr64.argtypes = [ctypes.c_void_p, ctypes.c_ulonglong,
                                         ctypes.POINTER(wt.DWORD),
                                         ctypes.POINTER(IMAGEHLP_LINE64)]

for arg in sys.argv[2:]:
    rva = int(arg, 16)
    addr = ctypes.c_ulonglong(BASE + rva)
    sym = SYMBOL_INFO()
    sym.SizeOfStruct = 88
    sym.MaxNameLen = 1999
    disp = ctypes.c_ulonglong(0)
    line = IMAGEHLP_LINE64()
    line.SizeOfStruct = ctypes.sizeof(IMAGEHLP_LINE64)
    lineDisp = wt.DWORD(0)

    name = "<unresolved>"
    if dbghelp.SymFromAddr(FAKE_PROC, addr, ctypes.byref(disp), ctypes.byref(sym)):
        name = "%s +0x%X" % (sym.Name.decode(errors="replace"), disp.value)
    where = ""
    if dbghelp.SymGetLineFromAddr64(FAKE_PROC, addr, ctypes.byref(lineDisp), ctypes.byref(line)):
        fn = line.FileName.decode(errors="replace") if line.FileName else "?"
        where = "   [%s:%d]" % (fn.rsplit("\\", 1)[-1], line.LineNumber)
    print("  RVA 0x%-8X  %s%s" % (rva, name, where))
