#!/usr/bin/env bash
# Batch 3: UART IRQ/dispatch + queue/curve helpers.
set -u
ANALISE=/mnt/c/Users/Vinicius/Desktop/t8_sys_v102/analise
ELF="$ANALISE/pnl_thumb.elf"
DEST="$ANALISE/pseudo"
mkdir -p "$DEST"
ADDRS="0x08002fb8 0x08004884 0x080038a4 0x08000544 0x08004860"
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
