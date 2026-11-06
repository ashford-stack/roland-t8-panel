import sys
import struct
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_ARM

path = sys.argv[1]
base = int(sys.argv[2], 16)       # load address (base_addr) of the payload (after the 64-byte header)
start_off = int(sys.argv[3], 16)  # offset within the payload to start disassembling
count = int(sys.argv[4]) if len(sys.argv) > 4 else 60
mode = sys.argv[5] if len(sys.argv) > 5 else "thumb"

with open(path, "rb") as f:
    data = f.read()

# always show the vector table (first 12 entries) relative to the payload start
print("=== Vectors (first 12 words) ===")
for i in range(12):
    off = i * 4
    (val,) = struct.unpack_from("<I", data, off)
    print(f"  [{i:2d}] off=0x{off:04x} addr=0x{base+off:08x} -> 0x{val:08x}")

cs_mode = CS_MODE_THUMB if mode == "thumb" else CS_MODE_ARM
md = Cs(CS_ARCH_ARM, cs_mode)
md.detail = False

print(f"\n=== Disassembly ({mode}) from offset 0x{start_off:04x} (addr 0x{base+start_off:08x}) ===")
code = data[start_off:start_off + 4096]
n = 0
for insn in md.disasm(code, base + start_off):
    print(f"0x{insn.address:08x}:\t{insn.mnemonic}\t{insn.op_str}")
    n += 1
    if n >= count:
        break
