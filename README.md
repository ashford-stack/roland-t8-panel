# Roland T-8 panel firmware — reverse-engineering notes

Reverse-engineering notes, a decoded serial protocol spec, and a Python simulator for
the **panel microcontroller** of the Roland T-8 (AIRA Compact beat machine).

The goal of this work was to assess whether the device's menu/UX could be reorganized.
The short answer, confirmed by code: the menu logic lives in the encrypted `App_Main`
image, not in the panel MCU — so the realistic route is a **hardware overlay on the
internal UART** rather than a firmware patch. See the analysis for the full reasoning.

## What's here

| Path | Contents |
|---|---|
| [`analise/ANALYSIS.md`](analise/ANALYSIS.md) | The full chronological analysis: update-file format, the 64-byte header, why `App_Panel` is plain ARM Thumb-2 and `App_Main` is encrypted, the STM32G0 identification, tooling, and the code-verified protocol. |
| [`analise/PROTOCOL.md`](analise/PROTOCOL.md) | Clean implementation spec of the panel ↔ App_Main serial protocol (USART1, 115200 8N1): message encoding, TX/RX opcodes, timing, boot handshake, RAM map. |
| [`analise/pseudo/`](analise/pseudo/) | Ghidra pseudo-C for each decompiled function, by address, plus `INDEX.txt` and `proc_addrs.txt`. |
| [`analise/pnl_full.lst`](analise/pnl_full.lst) | Full linear Thumb disassembly of the panel payload. |
| [`analise/cfg_ptrs.txt`](analise/cfg_ptrs.txt) | Control-flow coverage output (functions, peripherals, RAM usage). |
| [`analise/scripts/`](analise/scripts/) | The tooling used: header/entropy analysis, disassembly, ELF/PE packers for Ghidra, REA decompilation batches, pseudo-C extraction. |
| [`sim/`](sim/) | Python simulator of the virtual panel ↔ App_Main pair over TCP (or real serial via pyserial). See [`sim/README.md`](sim/README.md). |
| [`midi_msc/`](midi_msc/) | A solder-free USB-MIDI logger + read-only MSC inventory guide to document the "outside view" of the device. See [`midi_msc/MIDI_MSC_GUIDE.md`](midi_msc/MIDI_MSC_GUIDE.md). |
| [`update_teste/`](update_teste/) | Notes on a prepared (but not flashed) update-route test bundle. |

## Target

- **Device:** Roland T-8 (AIRA Compact), firmware system version v1.02.
- **Panel MCU:** STM32G0 family (Cortex-M0+), most likely G030.
- **Panel ↔ main link:** USART1, 115200 8N1, a compact MIDI-like 1/3-byte protocol.

## Running the simulator

```bash
cd sim
python smoke_test.py            # full validation (~9 s)
```

> **Note:** `sim/t8_proto.py` (the shared framing module) is empty in this snapshot,
> so the simulator does not run as-is until it is restored. The expected interface is
> documented in `sim/README.md`.

## Notes on included files

- The **Roland firmware binaries** (`T8_UPD.BIN`, `DD010_app.bin`, `DD010_pnl.bin`, the
  extracted payload, and the repackaged ELF/PE images) are **not included** — they are
  Roland's proprietary firmware. The analysis, disassembly, pseudo-C and tools here are
  original work derived from examining a device the author owns. Recreate the binary
  inputs from your own device if you want to reproduce the raw-binary steps.
- See [`NOTICE.md`](NOTICE.md) for the legal context.

## Status

Panel side: protocol encoding, framing, TX/RX dispatch, timing and the panel-direction
handshake are code-verified. Open items are App_Main-side business semantics (LED id map,
the physical function of the `0xB0` pins, real device behavior) — all observable with a
UART sniff or the MIDI/MSC front.
