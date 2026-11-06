import sys
import re

path = sys.argv[1]
base = int(sys.argv[2], 16)
minlen = int(sys.argv[3]) if len(sys.argv) > 3 else 4

with open(path, "rb") as f:
    data = f.read()

# ASCII strings
pat = re.compile(rb"[\x20-\x7e]{%d,}" % minlen)
print("=== ASCII strings ===")
for m in pat.finditer(data):
    off = m.start()
    s = m.group().decode("ascii", "replace")
    print(f"0x{base+off:08x} (off 0x{off:05x}, len {len(s):3d}): {s!r}")
