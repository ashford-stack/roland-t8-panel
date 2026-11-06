#!/usr/bin/env bash
# Batch 2: RX-side UART functions (dispatcher, registrars, ring consumer).
set -u
ANALISE=/mnt/c/Users/Vinicius/Desktop/t8_sys_v102/analise
ELF="$ANALISE/pnl_thumb.elf"
DEST="$ANALISE/pseudo"
mkdir -p "$DEST"
ADDRS="0x08003a78 0x08003530 0x08003854 0x0800497c 0x08003a4c 0x08003a64 0x08003c44 0x0800275c"
for a in $ADDRS; do
  echo "=== decompiling $a"
  if GHIDRA_INSTALL_DIR=/home/vinicius/ghidra_12.1.4_PUBLIC npx -y rea-agents@latest decompile "$ELF" "$a" --provider ghidra --format json > /tmp/dec.json 2>/tmp/dec.err; then
    python3 /mnt/c/Users/Vinicius/Desktop/t8_sys_v102/analise/scripts/extract_pseudo.py "$DEST/$a.txt"
  else
    echo "FAILED $a"
    tail -n 20 /tmp/dec.err
    cp /tmp/dec.err "$DEST/$a.err.txt"
  fi
done
echo ALLDONE
