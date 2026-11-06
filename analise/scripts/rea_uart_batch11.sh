#!/usr/bin/env bash
# Batch 11: tick chain (SysTick -> scheduler -> tarefas) + gate do encoder (0x93).
set -u
ANALISE=/mnt/c/Users/Vinicius/Desktop/t8_sys_v102/analise
ELF="$ANALISE/pnl_thumb.elf"
DEST="$ANALISE/pseudo"
ADDRS="0x08002934 0x080022e4 0x0800343c 0x08003450 0x08003960"
for a in $ADDRS; do
  echo "=== decompiling $a"
  if GHIDRA_INSTALL_DIR=/home/vinicius/ghidra_12.1.4_PUBLIC npx -y rea-agents@latest decompile "$ELF" "$a" --provider ghidra --format json > /tmp/dec.json 2>/tmp/dec.err; then
    python3 "$ANALISE/scripts/extract_pseudo.py" "$DEST/$a.txt"
  else
    echo "FAILED $a"; tail -n 20 /tmp/dec.err; cp /tmp/dec.err "$DEST/$a.err.txt"
  fi
done
echo ALLDONE
