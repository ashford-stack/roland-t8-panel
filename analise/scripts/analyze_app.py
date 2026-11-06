import sys, math, struct
from collections import Counter

path = sys.argv[1]
with open(path, "rb") as f:
    data = f.read()

HDRLEN = 64
hdr = data[:HDRLEN]
payload = data[HDRLEN:]

print(f"total file: {len(data)} bytes")
print(f"header (64 bytes): {hdr.hex()}")
name = hdr[0:16].rstrip(b'\x00')
ver = hdr[16:24]
print(f"  name: {name!r}")
print(f"  version: {ver!r}")
f18, f1c, f20, f24, f28 = struct.unpack_from('<IIIII', hdr, 0x18)
f2c, f30 = struct.unpack_from('<II', hdr, 0x2c)
print(f"  field@0x18: 0x{f18:08x}")
print(f"  field@0x1c (size?): 0x{f1c:08x} = {f1c}")
print(f"  field@0x20 (addr?):    0x{f20:08x}")
print(f"  field@0x24 (size2):    0x{f24:08x} = {f24}")
print(f"  field@0x28 (addr2):    0x{f28:08x}")
print(f"  field@0x2c (crc/hash1):0x{f2c:08x}")
print(f"  field@0x30 (crc/hash2):0x{f30:08x}")
print(f"  rest (should be FF):   {hdr[0x34:].hex()}")

print(f"\npayload: {len(payload)} bytes")
print(f"  payload % 16 = {len(payload) % 16}")
print(f"  payload % 8  = {len(payload) % 8}")
print(f"  payload % 4  = {len(payload) % 4}")

# Shannon entropy over the whole payload
cnt = Counter(payload)
total = len(payload)
ent = -sum((c/total) * math.log2(c/total) for c in cnt.values())
print(f"  distinct bytes: {len(cnt)}/256")
print(f"  Shannon entropy: {ent:.4f} bits/byte (max=8.0)")

# most/least frequent block
most = cnt.most_common(5)
print(f"  most frequent bytes: {[(hex(b),c) for b,c in most]}")

# look for repeated 16-byte blocks (hint of ECB)
block_count = Counter()
for i in range(0, len(payload) - 16, 16):
    block_count[payload[i:i+16]] += 1
rep = [(b, c) for b, c in block_count.items() if c > 1]
print(f"\n  repeated 16-byte aligned blocks: {len(rep)}")
for b, c in sorted(rep, key=lambda x: -x[1])[:10]:
    print(f"    {b.hex()}  x{c}")

# last 64 bytes of the payload (look at padding)
print(f"\n  last 64 bytes of the payload: {payload[-64:].hex()}")
print(f"  first 64 bytes of the payload: {payload[:64].hex()}")
