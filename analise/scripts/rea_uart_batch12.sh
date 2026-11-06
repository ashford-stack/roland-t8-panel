#!/usr/bin/env bash
# Batch 12: config dos timers (periodo do tick TIM1), leitura de pino, callback.
set -u
ANALISE=/mnt/c/Users/Vinicius/Desktop/t8_sys_v102/analise
ELF="$ANALISE/pnl_thumb.elf"
DEST="$ANALISE/pseudo"
ADDRS="0x080037e0 0x0800374c 0x0800158c 0x08000580"
for a in $ADDRS; do
  echo "=== decompiling $a"
  if GHIDRA_INSTALL_DIR=/home/vinicius/ghidra_12.1.4_PUBLIC npx -y rea-agents@latest decompile "$ELF" "$a" --provider ghidra --format json > /tmp/dec.json 2>/tmp/dec.err; then
    python3 "$ANALISE/scripts/extract_pseudo.py" "$DEST/$a.txt"
  else
    echo "FAILED $a"; tail -n 20 /tmp/dec.err; cp /tmp/dec.err "$DEST/$a.err.txt"
  fi
done
echo ALLDONE
