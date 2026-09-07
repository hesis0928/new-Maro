"""디버거 없이 Windows 미니덤프에서 예외 정보/모듈 목록/크래시 스레드의
스택을 뽑는다. 스택 메모리 안에서 모듈 코드 영역에 들어가는 값을 훑어
'가난한 자의 스택 트레이스'를 만든다 -- 어느 모듈이 관여했는지 판정하는 데
충분하다."""
import struct
import sys

MDMP = b"MDMP"
STREAM_THREAD_LIST = 3
STREAM_MODULE_LIST = 4
STREAM_EXCEPTION = 6
STREAM_SYSTEM_INFO = 7
STREAM_MEMORY64_LIST = 9

EXC_NAMES = {
    0xC0000005: "ACCESS_VIOLATION",
    0xC0000409: "STACK_BUFFER_OVERRUN / __fastfail",
    0xC000001D: "ILLEGAL_INSTRUCTION",
    0xC0000094: "INT_DIVIDE_BY_ZERO",
    0xC0000374: "HEAP_CORRUPTION",
    0x80000003: "BREAKPOINT",
    0xE06D7363: "C++ EXCEPTION (throw)",
}


def readMinidumpString(buf, rva):
    (length,) = struct.unpack_from("<I", buf, rva)
    return buf[rva + 4:rva + 4 + length].decode("utf-16-le", errors="replace")


def parse(path):
    with open(path, "rb") as fh:
        buf = fh.read()
    if buf[:4] != MDMP:
        print("not a minidump:", path)
        return

    signature, version, streamCount, streamRva = struct.unpack_from("<IIII", buf, 0)
    streams = {}
    for i in range(streamCount):
        sType, sSize, sRva = struct.unpack_from("<III", buf, streamRva + i * 12)
        streams[sType] = (sSize, sRva)

    print("=" * 78)
    print("dump:", path)

    # --- modules ---
    modules = []  # (base, size, name)
    if STREAM_MODULE_LIST in streams:
        _, rva = streams[STREAM_MODULE_LIST]
        (count,) = struct.unpack_from("<I", buf, rva)
        off = rva + 4
        for i in range(count):
            base, size, checksum, timestamp, nameRva = struct.unpack_from("<QIIII", buf, off)
            modules.append((base, size, readMinidumpString(buf, nameRva)))
            off += 108  # sizeof(MINIDUMP_MODULE)
        modules.sort()

    def moduleFor(addr):
        for base, size, name in modules:
            if base <= addr < base + size:
                return name.rsplit("\\", 1)[-1], addr - base
        return None, None

    # --- exception ---
    crashTid = None
    if STREAM_EXCEPTION in streams:
        _, rva = streams[STREAM_EXCEPTION]
        # MINIDUMP_EXCEPTION_STREAM: ThreadId(+0) __alignment(+4)
        # MINIDUMP_EXCEPTION starts at +8: Code(+0) Flags(+4) Record(+8)
        # Address(+16) NumberParameters(+24)
        (threadId,) = struct.unpack_from("<I", buf, rva)
        code, flags = struct.unpack_from("<II", buf, rva + 8)
        (excAddr,) = struct.unpack_from("<Q", buf, rva + 8 + 16)
        numParams = struct.unpack_from("<I", buf, rva + 8 + 24)[0]
        params = struct.unpack_from("<%dQ" % min(numParams, 15), buf, rva + 8 + 32)
        crashTid = threadId
        print("exception   : 0x%08X  %s" % (code, EXC_NAMES.get(code, "?")))
        print("crash thread: %d (0x%X)" % (threadId, threadId))
        mod, offset = moduleFor(excAddr)
        if mod:
            print("fault addr  : 0x%016X  ->  %s+0x%X" % (excAddr, mod, offset))
        else:
            print("fault addr  : 0x%016X  (not in any loaded module)" % excAddr)
        if code == 0xC0000005 and len(params) >= 2:
            kind = {0: "read", 1: "write", 8: "execute"}.get(params[0], str(params[0]))
            tmod, toff = moduleFor(params[1])
            where = ("%s+0x%X" % (tmod, toff)) if tmod else "not in any loaded module"
            print("av detail   : %s of 0x%016X  (%s)" % (kind, params[1], where))

    for base, size, name in modules:
        if "maro" in name.lower():
            print("maro module : base=0x%X size=0x%X  %s" % (base, size, name))

    # --- scan every thread's stack for maro frames ---
    if STREAM_THREAD_LIST in streams:
        _, rva = streams[STREAM_THREAD_LIST]
        (count,) = struct.unpack_from("<I", buf, rva)
        off = rva + 4
        print("-- scanning %d threads for maro.mll frames --" % count)
        for i in range(count):
            (tid, suspend, priorityClass, priority, teb,
             stackStart, stackSize, stackRva) = struct.unpack_from("<IIIIQQII", buf, off)
            off += 48
            stack = buf[stackRva:stackRva + stackSize]
            seen = []
            for pos in range(0, len(stack) - 8, 8):
                (val,) = struct.unpack_from("<Q", stack, pos)
                mod, offset2 = moduleFor(val)
                if mod is None:
                    continue
                entry = "%s+0x%X" % (mod, offset2)
                if seen and seen[-1] == entry:
                    continue
                seen.append(entry)
            maroHits = [e for e in seen if e.lower().startswith("maro")]
            if maroHits:
                tag = " <== CRASH THREAD" if tid == crashTid else ""
                print("  thread %d (0x%X)%s -- %d maro frames, %d bytes stack"
                      % (tid, tid, tag, len(maroHits), len(stack)))
                for e in maroHits:
                    print("      ", e)
                # maro 프레임 주변의 흐름을 보기 위해 앞뒤 몇 개도 보여준다.
                idx = seen.index(maroHits[0])
                print("       context:", " | ".join(seen[max(0, idx - 4):idx + 8]))


for p in sys.argv[1:]:
    parse(p)
