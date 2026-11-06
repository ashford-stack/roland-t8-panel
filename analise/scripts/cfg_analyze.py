import sys, struct, collections
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from capstone.arm import *
path, base = sys.argv[1], int(sys.argv[2], 16)
d = open(path, "rb").read(); end = base + len(d)
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB); md.detail = True
def rd32(a): return struct.unpack_from("<I", d, a - base)[0] if base <= a <= end - 4 else None
vec = [rd32(base + 4 * i) for i in range(48)]
entries = {}
for i, v in enumerate(vec):
    if i and v and base <= (v & ~1) < end and v & 1: entries.setdefault(v & ~1, []).append(i)
import os
if os.environ.get("PTRS"):
    for o in range(0,len(d)-3,4):
        v=struct.unpack_from("<I",d,o)[0]
        if v&1 and base<=(v&~1)<end and o>=0xC0:
            t=v&~1; i0=next(md.disasm(d[t-base:t-base+4],t),None)
            if i0 and (i0.mnemonic.startswith("push") or i0.mnemonic in("ldr","mov","movs","sub","cmp","ldrb","cbz","b","bx","ldrh","str")): entries.setdefault(t,[]).append(-o)
funcs, seen, insns, calls, lits, periph, tbl = set(entries), set(), {}, collections.defaultdict(set), {}, collections.defaultdict(set), []
work = list(funcs)
while work:
    f = work.pop(); stack = [f]
    while stack:
        a = stack.pop()
        while base <= a < end and a not in seen:
            ins = next(md.disasm(d[a - base:a - base + 4], a), None)
            if not ins: break
            seen.add(a); insns[a] = ins; m = ins.mnemonic
            if m in ("bl", "blx") and ins.operands[0].type == ARM_OP_IMM:
                t = ins.operands[0].imm
                calls[f].add(t)
                if t not in funcs and base <= t < end: funcs.add(t); work.append(t)
            elif m.startswith("b") and m not in ("bic", "bics", "bkpt", "bfi", "bfc", "bl", "blx", "bx", "bxj") and ins.operands and ins.operands[0].type == ARM_OP_IMM:
                t = ins.operands[0].imm; stack.append(t)
                if m in ("b", "b.w", "b.n"):
                    break
            elif m in ("cbz", "cbnz"): stack.append(ins.operands[1].imm)
            if m.startswith("ldr") and ins.operands[-1].type == ARM_OP_MEM and ins.operands[-1].mem.base == ARM_REG_PC:
                la = ((a + 4) & ~3) + ins.operands[-1].mem.disp
                v = rd32(la)
                if v is not None:
                    lits[a] = v
                    if 0x40000000 <= v < 0x60000000: periph[f].add(v)
            if m in ("tbb", "tbh"): tbl.append(a)
            if m in ("bx", "pop", "pop.w") and (m == "bx" and ins.op_str == "lr" or "pc" in ins.op_str): break
            if m == "udf": break
            a += ins.size
print(f"functions: {len(funcs)} | reached instr.: {len(insns)} ({sum(i.size for i in insns.values())}/{len(d)} bytes) | tbb/tbh: {len(tbl)}")
print("\n== vector entries ==")
for a, ix in sorted(entries.items()): print(f"  vec[{ix}] -> {a:#010x}")
inc = collections.Counter(t for s in calls.values() for t in s)
print("\n== functions (approx size, callers, calls, peripherals) ==")
fl = sorted(funcs)
for i, f in enumerate(fl):
    nx = fl[i + 1] if i + 1 < len(fl) else end
    p = sorted(periph.get(f, []))
    print(f"  {f:#010x} ~{nx - f:5d}B in={inc[f]:2d} out={len(calls.get(f, ())):2d} {'['+','.join(f'{x:#x}' for x in p[:6])+']' if p else ''}")
print("\n== peripheral constants (literal pools) ==")
c = collections.Counter(v for v in lits.values() if 0x40000000 <= v < 0x60000000)
for v, n in sorted(c.items()): print(f"  {v:#010x} x{n}")
print("\n== most-used ram/flash 0x2000xxxx ==")
c = collections.Counter(v for v in lits.values() if 0x20000000 <= v < 0x30000000)
for v, n in c.most_common(25): print(f"  {v:#010x} x{n}")
print("\ntbb/tbh em:", [hex(x) for x in tbl])
