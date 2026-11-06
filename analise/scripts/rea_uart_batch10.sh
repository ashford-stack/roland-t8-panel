#!/usr/bin/env bash
# Batch 10: matrix init, 0x08003890, callback registrars, boot status TX.
set -u
ANALISE=/mnt/c/Users/Vinicius/Desktop/t8_sys_v102/analise
ELF="$ANALISE/pnl_thumb.elf"
DEST="$ANALISE/pseudo"
mkdir -p "$DEST"
ADDRS="0x08003860 0x08003890 0x08003eb0 0x08003ebc 0x08003f08 0x08004010"
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
