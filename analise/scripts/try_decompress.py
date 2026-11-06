import sys, zlib, bz2, lzma

path = sys.argv[1]
with open(path, "rb") as f:
    data = f.read()
payload = data[64:]

print(f"payload: {len(payload)} bytes")
print("first 32 bytes:", payload[:32].hex())

def try_zlib_raw(buf, wbits):
    try:
        d = zlib.decompressobj(wbits)
        out = d.decompress(buf, 1_000_000)
        return out, None
    except Exception as e:
        return None, str(e)

for wbits in (15, -15, 31, 47):
    out, err = try_zlib_raw(payload, wbits)
    status = f"OK, {len(out)} bytes" if out else f"failed: {err}"
    print(f"zlib wbits={wbits}: {status}")

try:
    out = bz2.BZ2Decompressor().decompress(payload)
    print(f"bz2: OK, {len(out)} bytes")
except Exception as e:
    print(f"bz2: failed: {e}")

try:
    out = lzma.LZMADecompressor().decompress(payload)
    print(f"lzma: OK, {len(out)} bytes")
except Exception as e:
    print(f"lzma: failed: {e}")

# try various offsets (some formats have a small sub-header before the real stream)
print("\n--- trying zlib raw deflate at various start offsets (0..32) ---")
for off in range(0, 33):
    out, err = try_zlib_raw(payload[off:], -15)
    if out and len(out) > 1000:
        print(f"  offset {off}: OK, {len(out)} bytes!!")
