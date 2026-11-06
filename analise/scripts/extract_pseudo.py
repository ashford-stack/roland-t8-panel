import json
import os
import sys

src = "/tmp/dec.json"
out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/dec.out.txt"

try:
    with open(src, encoding="utf-8", errors="replace") as f:
        d = json.load(f)
    p = d.get("normalized_result") if isinstance(d.get("normalized_result"), str) else None
    if not p:
        p = (d.get("raw_result") or {}).get("value")
    if not isinstance(p, str):
        raise ValueError("no pseudo text; top keys %s" % list(d)[:8] if isinstance(d, dict) else type(d))
except Exception as e:
    try:
        raw = open(src, "rb").read().decode("utf-8", errors="replace")
    except Exception:
        raw = ""
    p = "ERROR %r\n--- fallback: %s" % (e, raw[:2000])

with open(out, "w", encoding="utf-8") as f:
    f.write(p)
print("written", out, len(p))
