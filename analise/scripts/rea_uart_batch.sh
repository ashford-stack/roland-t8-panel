#!/usr/bin/env bash
# Decompile the T-8 panel UART/protocol functions via REA (WSL + Ghidra).
# Output: one <addr>.txt per address under analise/pseudo/
set -u
ANALISE=/mnt/c/Users/Vinicius/Desktop/t8_sys_v102/analise
ELF="$ANALISE/pnl_thumb.elf"
DEST="$ANALISE/pseudo"
mkdir -p "$DEST"
ADDRS="0x08003de4 0x08002834 0x08004cc0 0x08003c7a 0x08003d0c 0x08003d28 0x08003984 0x08003a10 0x08003ec8 0x08003d40"
for a in $ADDRS; do
  echo "=== decompiling $a"
  if GHIDRA_INSTALL_DIR=/home/vinicius/ghidra_12.1.4_PUBLIC npx -y rea-agents@latest decompile "$ELF" "$a" --provider ghidra --format json > /tmp/dec.json 2>/tmp/dec.err; then
    python3 -c '
import json, sys
a, dest = sys.argv[1], sys.argv[2]
try:
    d = json.load(open("/tmp/dec.json"))
    p = d.get("normalized_result") if isinstance(d, dict) else None
    if not isinstance(p, str):
        p = (d.get("raw_result") or {}).get("value")
    if not isinstance(p, str):
        raise ValueError("no pseudo text; top keys %s" % list(d)[:8])
except Exception as e:
    try:
        err = open("/tmp/dec.json", "rb").read().decode(errors="replace")
    except Exception:
        err = None
    p = "ERROR %s\n--- fallback: %s" % (e, (err or "")[:2000])
open("%s/%s.txt" % (dest, a), "w").write(p)
print("ok", a, len(p))
' "$a" "$DEST"
  else
    echo "FAILED $a"
    tail -n 20 /tmp/dec.err
    cp /tmp/dec.err "$DEST/$a.err.txt"
  fi
done
echo ALLDONE
