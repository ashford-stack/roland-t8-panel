import sys
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

path = sys.argv[1]
base = int(sys.argv[2], 16)
out_path = sys.argv[3]

with open(path, "rb") as f:
    data = f.read()

md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
md.detail = False

insns = []
# Simple linear disassembly (Thumb), sweeping the whole file.
# When it hits a byte that does not decode (typically a literal pool
# embedded in the middle of the code), it advances 2 bytes (minimum Thumb
# alignment) and tries to resync — instead of giving up.
offset = 0
while offset < len(data):
    chunk = data[offset:offset + 4096]
    produced = False
    last_end = offset
    for insn in md.disasm(chunk, base + offset):
        insns.append(insn)
        produced = True
        last_end = (insn.address - base) + insn.size
    if not produced or last_end <= offset:
        offset += 2
        continue
    offset = last_end

with open(out_path, "w", encoding="utf-8") as f:
    for insn in insns:
        f.write(f"0x{insn.address:08x}:\t{insn.mnemonic}\t{insn.op_str}\n")

print(f"total instructions: {len(insns)}")
print(f"last address: 0x{insns[-1].address:08x}" if insns else "none")

from collections import Counter
mnem_count = Counter(i.mnemonic for i in insns)
print("\n=== most common mnemonics ===")
for m, c in mnem_count.most_common(20):
    print(f"  {m:10s} {c}")

print("\n=== tbb/tbh occurrences (jump tables / switch) ===")
for i in insns:
    if i.mnemonic in ("tbb", "tbh", "tbb.w", "tbh.w"):
        print(f"0x{i.address:08x}:\t{i.mnemonic}\t{i.op_str}")
