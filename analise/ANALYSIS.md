# Roland T-8 (Beat Machine) firmware analysis — state as of 2026-10-22

## Index & current state (Oct 22, rev. 4)

**What is closed (code-verified):** the complete serial protocol on the panel side
(`DD010_pnl`), right here in `../PROTOCOL.md` (implementation spec). Canonical table:
section *"Canonical panel↔App_Main protocol table"* below. The TX side (opcodes
`0x90/0x91/0x80/0x93/0xFE/0xB0/0xB1/0xB2/0xC0/0xFF`) and the RX side (`0xFA/0xFB/0xFF/0xA0/0xE0/0xB0`)
have pseudo-C for every function in `pseudo/`, including the main loop (`cmd_tree`),
RX parser, LED matrix driver and knob/ADC engine. The edge round (rev. 4) also
closed: **the `0x93` latch writer** (quadrature encoder, `FUN_080048e4`),
**the tick scheduler** (`FUN_080022e4`, TIM1 1 kHz → 2 s heartbeat / 200 ms dial poll)
and **the RX `0xFF` semantics** = re-presentation order (not a ping).

**Still open (not a blocker for the overlay/simulator):** business semantics of
`0x80 {b0,b1}` and `0xB0 {sel,state}`; the App_Main side (`DD010_app.bin` encrypted, key in
the bootloader/hw).

**Document map (chronological):**
1. Context/format/header/tar format — Oct 9
2. cfg analysis + questions — Oct 9
3. REA setup + ELF/Thumb recipe — Oct 22 (usage: `scripts/rea_uart_batch*.sh`)
4. **Canonical protocol table** — Oct 22 (the key section; `PROTOCOL.md` is the clean version)
5. Main loop (cmd_tree), ADC engine, LED paths, method notes — Oct 22
6. Edge round: scheduler/timers, dial encoder, RX `0xFF` — Oct 22 (end of section 5)

**Reproducible tools:**
- `scripts/make_elf_sym.py` — payload → Thumb ELF + symtab (Ghidra now sees the
  functions referenced only by pointer).
- `scripts/rea_uart_batch*.sh` — decompilation batches via REA/WSL (run via
  `wsl -d Ubuntu-24.04 -- bash -lc "sed -e 's/\r$//' … && bash /tmp/…"`).
- `scripts/extract_pseudo.py` — REA JSON → pseudo-C in `pseudo/<addr>.txt`.
- `pseudo/proc_addrs.txt` / `pseudo/INDEX.txt` — procedure inventory.

## Product context

The T-8 is a Roland drum/bass sequencer (AIRA Compact/Boutique line).
According to public coverage of the hardware, it contains:

- a proprietary Roland ASIC called **E4E** (no known public documentation) —
  probably the audio/synthesis/sequencing engine;
- an **STM32** microcontroller ("STM326030", cited as a "low-cost MCU range")
  that probably drives the user interface (buttons, encoders, display).

**User goal:** assess the feasibility of **reorganizing the device's menu/UX** —
today the functions are scattered, with no clear menu/submenu hierarchy.

**Device firmware update mechanism:** there is no PC/Mac updater.
Holding **Shift at power-on**, the T-8 mounts as a **USB mass storage**
device; you drag the `T8_UPD.BIN` file into it, and the **device's own bootloader**
does the parse/decryption/flash. This means all the decryption logic (key + algorithm)
lives **inside the hardware**, not in any PC-runnable software — important for
understanding why one of the two images could not be decrypted (see below).

## Input files

```
C:\Users\Vinicius\Desktop\t8_sys_v102\
├── t8_sys_v102\
│   └── T8_UPD.BIN                  ← original update file (1,095,680 bytes)
└── extraido\_tmp\
    ├── DD010_app.bin                ← "App_Main" (1,095,680 bytes with header; see below)
    └── DD010_pnl.bin                ← "App_Panel" (20,596 bytes with header)
```

### `T8_UPD.BIN` is a tar (USTAR)

Confirmed by the `ustar` signature at offset 257 of the header, and by the embedded
filename `./_tmp/DD010_pnl.bin` — the **`_tmp`** path is a hint that these two
files are exactly what the T-8 bootloader receives/processes when flashing the
update (the folder name matches where the update process leaves them before
flashing).

**Addendum (update-route audit, night of Oct 22):** the tar has **exactly 2
entries** (`pnl` @0x000, `app` @0x5400), the tail (0x110E00..0x113000) is **just
zero padding** — there is no apparent bundle signature nor a third file. Standard
USTAR headers. **The @0x2C field is an IEEE/zlib CRC32 of the payload — confirmed by
recomputation on `App_Panel`: `CRC32(payload_pnl) = 0x53c790fb` = the exact stored
value.** The @0x2C of `App_Main` (0x0bf49f16) is **not** the CRC32 of the encrypted
payload (zlib/jam/~ candidates do not match) — consistent with the CRC having been
computed over the **cleartext** payload before encryption (⚠, impossible to verify
without the key). The @0x30 field `0x00000040`/`0x7c400268` is not a CRC32 of the
header (tested) — ⚠. Implication for the overlay route:
**integrity = recomputable CRC32, no key, no apparent signature**; the only unknown
layer is the E4E bootloader's internal validation (not in the bundle), which can
only be decided empirically with a controlled flash test.

**Test artifact created: `update_teste/T8_UPD.BIN`** (Oct 22 — see
`update_teste/T8_UPD.BIN.INFO.txt`): a clone of the original with **1 inert byte**
changed (VA `0x08005033`, terminal padding outside the code, `00→01`) + **the pnl
payload CRC32 recomputed** (`0x53c790fb → 0x24c0a06d`). Identical size (1,126,400);
`App_Main` untouched byte-for-byte. If the device updates and boots normally → the
loader accepts a recomputable CRC and the **solder-free overlay route is open**; if it
refuses, the bootloader validates something beyond tar + CRC and the physical route
remains the only one. Result pending the physical test. **User decision (Oct 22): do not
run the flash test for now** — a purely operational decision, with no archiving cost: the
bundle and the `INFO.txt` stay intact in `update_teste/` ready to run whenever they want
(same MSC procedure as extracting the original; original preserved as a backup).
Meanwhile, the active front becomes the one that does not require flashing the device
(MIDI-over-USB log + read-only MSC inventory, if the user agrees).

### Read-only MIDI/MSC front (Oct 22 — guide delivered, awaiting user execution)

`midi_msc\` package: `t8_midi_log.py` (logs all USB-MIDI messages
in/out with timestamps + send commands `n`/`c`/`st`/`sp`/`rel`; log in
`logs\midi_log_*.log`) and `MIDI_MSC_GUIDE.md` (installation `py -m pip install
mido python-rtmidi`, exploration script for pads/dial/transport/slider, and the
**read-only** MSC procedure: catalog tree/names/sizes, **zero
writes to the device**, safe ejection, and the reminder that pasting
`update_teste\T8_UPD.BIN` remains a separate user decision).
Requirement/note: DAWs closed (Windows MIDI ports are exclusive).
An empty result is also valid: it documents the answer to "does this firmware expose
USB-MIDI?". Status: awaiting the user to run it and bring back
the logs/listing; then the evidence enters as an "outside view" section in
`ANALYSIS.md` and, if it pans out, a `PROTOCOL_MIDI.md`.

**Tooling update + first evidence (Oct 22):** the
`mido`+`python-rtmidi` route broke on the user's machine — `python-rtmidi` 1.5.8
(publishes only an sdist for cp313; `pip index versions` listed 1.0.0–1.5.8 all
without a wheel) requires a C++/Visual Studio compiler, which is not present there.
Pivot to **`pygame.midi`/PortMidi** (`py -m pip install pygame` → native
`pygame-2.6.1-cp313-win_amd64` wheel). On top of that, the script's smoke run already
brought the **first positive evidence**: on the user's PC, with the T-8 plugged in,
PortMidi enumerates **`dev1: T-8` (input) and `dev3: T-8` (output)** — the App_Main
v1.02 **exports** USB-MIDI ports (the "no MIDI" hypothesis fell). The "Microsoft
MIDI Mapper" is deliberately ignored in the OUT selection. Pending: observe whether
traffic flows (pads/dial/transport) → user's logs.

## 64-byte header format (common to both `.bin` files)

Each image (`DD010_app.bin`, `DD010_pnl.bin`) starts with a fixed 64-byte header,
followed by the real payload:

| offset | field | `DD010_app.bin` (App_Main) | `DD010_pnl.bin` (App_Panel) |
|---|---|---|---|
| 0x00–0x0F | name (ASCII, `\0`-padded) | `App_Main` | `App_Panel` |
| 0x10–0x17 | version (ASCII, 8 bytes) | `1.020057` | `1.010001` |
| 0x18 (u32 LE) | flags/type (hypothesis) | `0x00048040` | `0x00040040` |
| 0x1C (u32 LE) | payload size | `0x0010b7c0` = 1,095,616 | `0x00005034` = 20,532 |
| 0x20 (u32 LE) | address (hypothesis: staging) | `0x60000000` | `0x60000000` |
| 0x24 (u32 LE) | payload size (repeated) | `0x0010b7c0` | `0x00005034` |
| 0x28 (u32 LE) | address (repeated) | `0x60000000` | `0x60000000` |
| 0x2C (u32 LE) | CRC/hash? (hypothesis) | `0x0bf49f16` | `0x53c790fb` |
| 0x30 (u32 LE) | unknown | `0x7c400268` | `0x00000040` |
| 0x34–0x3F | padding | `FF`×12 | `FF`×12 |

**The @0x1C field matches exactly `file_size − 64` in both cases** — this is
confirmed, not a hypothesis.

**Strongest hypothesis: the @0x18 field is a flag, and the `0x8000` bit indicates
"encrypted payload".** `0x00048040` (app, encrypted) vs `0x00040040` (panel, cleartext)
differ exactly by that bit. Not tested/confirmed against a third example.

**The @0x20/@0x28 field = `0x60000000` is identical in both images**, even though the
panel image actually runs at `0x08000000` (STM32 internal flash — confirmed by the
reset vector, see below). This suggests it is **not the final execution address**, but
rather probably a *staging* address (intermediate buffer, e.g. external RAM via the
main board's FMC/FSMC) used by the update process before writing each image to its
real destination.

The @0x2C and @0x30 fields were not decoded — possibly a CRC32 of the payload +
some other field (partial key/nonce, index), but there is not enough data (only 2
samples) to confirm.

## `DD010_pnl.bin` ("App_Panel") — **NOT encrypted**

Payload (after the 64-byte header) = 20,532 bytes of **genuine ARM Cortex-M (Thumb-2)
code**, loaded at `0x08000000` (internal flash, STM32 default).

Confirmed by the valid vector table right at the start of the payload:

```
[0]  initial SP       = 0x20001de8   (RAM, STM32 default)
[1]  Reset_Handler    = 0x080000d9   (thumb bit set; real address = 0x080000d8)
[2]                   = 0x08002933
[3]                   = 0x080028ed
...
[11]                  = 0x08002937
```

Shannon entropy of the payload: **6.72 bits/byte** (nothing abnormal — it is normal
code, not random/encrypted data).

Full disassembly done with **Capstone** (Python), linear sweep in Thumb mode,
with automatic resync when hitting bytes that do not decode (literal pools
embedded in the middle of the code, common in ARMCC/GCC). Result: **9,811 instructions**
decoded, covering the whole file (`0x08000000` to `0x08005032`).

- The `Reset_Handler` (`0x080000d8`) follows the classic CMSIS startup pattern (calls a
  routine via `blx`, then jumps to another via `bx`), followed by compiler runtime
  routines recognizable at a glance (software integer division, `memcpy`/`memset`-style
  loops).
- **No `tbb`/`tbh` instruction** (table branch — the classic signature of a compiled
  `switch(state)`) was found in the linear sweep. This may mean the code uses
  `cmp`/`beq` chains instead of a jump table, **or** that the linear sweep misaligned in
  some stretch (it does not follow real control flow, it just sweeps sequentially) — not
  conclusive without a real control-flow analysis (Ghidra).
- **No readable text string** was found (full ASCII sweep, found only byte sequences of
  code by coincidence). This is expected: the T-8 display is mostly numeric/icons, not
  running text — so the "menu structure" is probably encoded as a state machine in the
  code itself (transitions between screens/parameters), not as a string table.

**Practical conclusion:** this is the file where it makes sense to keep investigating to
understand/reorganize the menu logic — but to go beyond the raw linear disassembly (find
the real state machine, name functions, see the call graph) a disassembler that truly
follows control flow is needed (Ghidra or similar) — see the "Tooling limitation" section
below.

## `DD010_app.bin` ("App_Main") — **encrypted, dead end for now**

Payload (after header) = 1,095,616 bytes. Header indicates loading at `0x60000000`
(but, as discussed, this is probably a staging address, not necessarily the real
execution address — we have not identified this binary's real architecture/ISA, which
may not even be ARM; it could be the firmware of the E4E ASIC itself, of unknown ISA).

Evidence that the payload is **encrypted** (not just compressed):

- **Shannon entropy: 7.9998 bits/byte** (out of a maximum of 8.0) — essentially
  random.
- All 256 byte values present, with near-perfectly uniform frequency
  (~4280 occurrences expected per value across 1,095,616 bytes; observed between ~4447–4515
  for the most frequent ones — no bias that would indicate weak XOR or partially flat data).
- **Zero repeated 16-byte blocks** in the whole file (tested at all 16-aligned offsets)
  — rules out "naive" ECB with repetitive data, consistent with CBC/CTR or a stream cipher.
- The payload size is an **exact multiple of 16** (1,095,616 ÷ 16 = 68,476) — consistent
  with (but not proof of) block-cipher padding (e.g. AES).
- **Tested and ruled out**: zlib (with/without header, raw deflate at various offsets),
  gzip, bz2, lzma — none decodes. Not a standard library compression.

**Why we can't go further:** the key and the decryption algorithm live inside the
device's own bootloader (there is no PC updater to reverse). Extracting this would
require a physical dump of the bootloader flash via **SWD/JTAG**, and production
devices typically have the STM32's read protection (RDP) enabled, which blocks that
dump. **Outside the scope of remote file analysis.**

A web search (Oct 9, 2026) found no prior public work on this specific Roland
update format nor on breaking the encryption on AIRA Compact/Boutique line products.

## ⚠️ Legal note (not legal advice)

Roland's software EULAs for products in the same line (verified on the TR-8S)
expressly prohibit reverse engineering of the software. In some countries (e.g. the US,
DMCA §1201) breaking encryption that controls access to firmware may also carry its own
legal implications, independent of the EULA. This tends to be tolerated in practice when
it is personal modification of a device you own ("right to repair" line), but if the
intent is to **distribute** a modified firmware publicly, it is worth checking this more
carefully — not something I validate here.

## Tooling limitation found in this environment (Windows)

The `rea` MCP (reverse engineering assistant) uses **Ghidra** as its native
disassembly/decompilation engine. On this Windows machine:

- Initially Ghidra was not configured (`GHIDRA_INSTALL_DIR` absent). It was
  added in `C:\Users\Vinicius\.claude.json`, block `mcpServers.rea.env`, pointing
  to `C:\Users\Vinicius\Desktop\ghidra_12.1.4_PUBLIC` (required restarting the Claude
  Code session to pick up the new variable — done, confirmed).
- **Even when configured, REA's Ghidra integration on Windows only accepts x86/x86-64
  targets in PE.** Tested both by packing the `pnl.bin` payload as ELF manually and as PE
  manually (base address `0x08000000`, both in the scripts `scripts/make_elf.py` and
  `scripts/make_pe.py`) — both were rejected with
  `architecture_unsupported` / `target_format_unsupported`. **ARM is blocked in this
  integration regardless of the container used.**
- **Workaround identified, not yet executed:** install **WSL (Windows
  Subsystem for Linux)** — confirmed available on the system (`wsl.exe` exists, but
  no distro installed yet) — and run REA's Ghidra headless from inside
  Linux, where the "x86/x64 only" restriction (specific to REA's "Windows Ghidra P0"
  branch) should not apply. This would unlock full ARM analysis: named
  functions, call graph, xrefs, switch/jump-table detection and,
  possibly, pseudo-C. **Decision pending with the user** (has not yet decided whether
  they want to install it).
- As an alternative without touching the environment, **Capstone** was installed (Python,
  `pip install --user capstone`, version 5.0.9) for manual disassembly — this is what
  produced the `pnl.bin` analysis documented above. It works well for raw disassembly,
  but has no call graph, does not resolve xrefs, does not decompile to C, and does not
  follow real control flow (hence the linear sweep with heuristic resync, which can
  misalign in stretches of embedded data).

## Files in this folder (`analise/`)

- `ANALYSIS.md` — this document.
- `pnl_full.lst` — full Thumb disassembly of `DD010_pnl.bin` (9,811 instructions,
  real addresses `0x08000000`+).
- `DD010_pnl.payload.bin` — the `pnl.bin` payload already without the 64-byte header
  (starts right at the vector table, ready to reopen in a disassembler with base
  `0x08000000`). *(Not included in this repository — Roland firmware binary.)*
- `scripts/`
  - `analyze_app.py` — parses the 64-byte header, computes entropy, looks for
    repeated 16-byte blocks. Usage: `python analyze_app.py <file.bin>`.
  - `try_decompress.py` — tries zlib/gzip/raw-deflate/bz2/lzma against the payload. Usage:
    `python try_decompress.py <file.bin>`.
  - `strings_scan.py` — sweeps ASCII strings with address. Usage:
    `python strings_scan.py <payload.bin> <base_hex> [min_len]`.
  - `disasm.py` — disassembles a specific stretch (shows the vector table + N instructions
    from an offset). Usage:
    `python disasm.py <payload.bin> <base_hex> <offset_hex> [count] [thumb|arm]`.
  - `full_disasm.py` — linear disassembly of the whole file with automatic resync;
    generates a `.lst` and summarizes the most common mnemonics and `tbb`/`tbh` occurrences.
    Usage: `python full_disasm.py <payload.bin> <base_hex> <output.lst>`.
  - `make_elf.py` / `make_pe.py` — pack a raw ARM payload into a minimal ELF/PE with a
    configurable base address and entry point, just to try opening it in Ghidra (both hit
    the "ARM blocked on Windows" limitation described above; they stay here ready for when
    WSL is available, in case the PE/ELF is still needed there — but probably it will not
    be, Ghidra on Linux should open the raw `.bin` directly as a "raw binary" with the
    ARM:Cortex-M language chosen on import).

All scripts depend only on `capstone` (`pip install --user capstone`) and Python's
standard library.

## Next steps (open)

1. **Decide on WSL + Ghidra** to unlock full ARM analysis of `pnl.bin` —
   it is the step that would most increase the quality of the menu-logic investigation
   (named functions, call graph, real switch/state detection).
2. With or without Ghidra: map the GPIO/button-matrix and encoder tables — the most
   likely entry point to understand "which physical button triggers which menu
   transition" is the keyboard scan routine (probably called from a timer
   interrupt).
3. `DD010_app.bin` remains out of reach without physical access to the hardware (SWD/JTAG)
   — there is no pure-software path to decrypt it.

---

## Update 2026-10-09 — control-flow analysis (without Ghidra) of `pnl.bin`

New script `scripts/cfg_analyze.py` (Capstone, recursive descent from the reset/IRQ vector;
with `PTRS=1` it also uses as a root every word in the file that looks like a Thumb function pointer).
Usage: `PTRS=1 python cfg_analyze.py DD010_pnl.payload.bin 0x08000000`. Output in `cfg_ptrs.txt`.
Coverage: **212 functions, 8,054 instructions, 16,858 of 20,532 bytes (~82%)** (vectors only: 22%).
Still **no `tbb`/`tbh`** → the panel does not use table-based `switch`; flow via `cmp`/`beq` and pointer tables.

### MCU identified: STM32G0 family (Cortex-M0+), most likely G030 (matches "STM326030")
Peripheral addresses found in the literal pools: RCC `0x40021000`, FLASH `0x40022000`,
PWR `0x40007000`, GPIO `0x50000000–0x50001400` (A/B/C/D/F), DMA `0x40020000` + DMAMUX `0x40020800`,
ADC `0x40012400`, TIM1 `0x40012c00`, TIM3 `0x40000400`, TIM14 `0x40002000`, TIM16/17, **USART1
`0x40013800`** and **USART2 `0x40004400`**. Flash keys `0x45670123` / `0x4c5d6e7f` (FLASH/option-bytes
unlock on the G0). (The 2 addresses `0x40020000`/`0x40021800` from the 1st pass were pool reuse;
the G0 map above is the consistent one.)

### What this tells us about the menu
- **Panel = interface peripherals**: ADC (potentiometers/knobs), GPIO (button/LED matrix),
  timers (scan/LED PWM), DMA. This confirms what was suspected: the panel reads physical controls.
- **USART1/USART2 = link to App_Main.** The "which screen/menu" logic is decided on the
  encrypted side; the panel probably just reports control events and receives display/LED
  commands over serial. **The menu hierarchy almost certainly lives in App_Main.**
- Panel boot flow (`0x08004ab8`, 31 calls): clock/FLASH init → GPIO/ADC/
  USART/timer init → main loop with a RAM flag (dispatches events from `0x08004b48` onward).
- Routine `0x08003f14`: FLASH/option-bytes unlock at boot (init, not a screen).

### Conclusion/risk
Reorganizing the menu by touching only the panel is probably **infeasible**: the panel does
not seem to contain the menu machine. And a modified `T8_UPD.BIN` would still need a valid
(encrypted) App_Main for the bootloader to accept it. To test the hypothesis without Ghidra,
the next step is to decode the serial protocol (functions at `0x0800275c`, `0x08002808`,
`0x08002fb8`, `0x08003de4`, the ones touching USART1) — the message format shows whether the
panel sends "button X" or "screen state".

### Extra finding: serial-link baud rate
`0x08003de4` (USART/UART init) writes `0xe1 << 9` = **115200** to the baud field of the HAL
handle (STM32CubeHAL style: `huart.Init.BaudRate`, WordLength/StopBits/Parity zeroed = 8N1, `Mode=0xC` = TX+RX).
That is, the panel talks to the rest of the device over UART at **115200 8N1**. If the link is
accessible on the board, the button↔screen traffic can be sniffed (logic analyzer/USB-serial)
to validate the "menu lives in App_Main" hypothesis without opening any encrypted binary.

---

## Update 2026-10-15 — hypothesis CONFIRMED: the panel does not contain the menu

Decoding of the main loop and the UART path (from `pnl_full.lst`, without Ghidra).

**Main loop `0x08004ab8` (CONFIRMED):** after init (clock/GPIO/ADC/UART@115200/timers —
`0x8003604`, `0x800353c`, `0x8003de4`), it enters a loop driven by an ISR flag. On each event,
it tests a bit word and, for each changed control, builds a short message
`{opcode, idx, value}` (value always 0–0x7F, 7 bits) and sends it over UART. Opcodes loaded from
constants (offsets 0xc4/0xa0/0x90/0x6c/0x48): `0x90`/`0xA0` have **MIDI-style note-on/note-off
semantics** (button pressed/released; the release does `value-0x80`).

**TX `0x08003ec8` (CONFIRMED):** copies the buffer (`memcpy` `0x8000120`) and calls `0x08002834` =
`HAL_UART_Transmit_IT` (state 0x21, pData at `[h+0x50]`, count at `[h+0x40+0x14/0x16]`). It is the serial send.

**RX→display (CONFIRMED):** `0x08004cc0` pushes a halfword into a ring of 0x40 slots and triggers an
LED callback; it is called from `0x08003c7a`/`0x08003d0c`/`0x08003d28`, in the region of the UART
reception handlers. That is, bytes received from App_Main drive the LEDs/display.

**Absences (CONFIRMED):** no text string, no `tbb/tbh`, no screen state machine.
The panel is a **control surface over UART** (HID-over-serial, MIDI-like protocol).

### Conclusion
The menu/navigation logic lives in **`App_Main` (the encrypted image)**, not in the panel — before
it was a structural hypothesis, now it is confirmed by code. Implications for an "improved menu":
1. A panel-only mod does NOT reorganize the menu (the logic is not there).
2. Editing firmware + reflashing is BLOCKED by the App_Main encryption (key in the bootloader;
   would require a physical SWD/JTAG dump, probably with RDP enabled).
3. Viable route without breaking the cipher: **hardware overlay on the UART** — interpose an
   external MCU between panel and App_Main and remap the `{opcode,idx,value}` events @115200 8N1
   (shortcuts/combos/modes).

Code references: loop `0x08004ab8`; TX `0x08003ec8`→`0x08002834`; RX/display `0x08004cc0`;
button-event dequeue `0x08003984`; UART init `0x08003de4` (115200 8N1).

---

## Update 2026-10-22 — REA 6.7.0 + WSL: CLEAN Thumb decompilation unblocked

Environment tested on the machine (Windows 10 22H2) with REA installed for OpenCode via MCP
(`~/.config/opencode/opencode.json`, `rea-agents@6.7.0`) and via CLI (npx).

### Setup that became permanent on the machine

- **WSL Ubuntu 24.04.5 LTS** installed in `D:\WSL\Ubuntu-24.04` (`wsl --install Ubuntu-24.04
  --location D:\WSL\Ubuntu-24.04 --no-launch`), default user `vinicius` (sudo NOPASSWD),
  `_tmp` of the `extraido\` folder is the same `_tmp` seen in the `T8_UPD.BIN` tar.
- Inside WSL: **Node 24.22.1**, **OpenJDK 21.0.12.1**, **Ghidra 12.1.4 Linux** in
  `~/ghidra_12.1.4_PUBLIC` (zip SHA-256 verified against the official release:
  `ddac49f9…d4db`, asset `ghidra_12.1.4_PUBLIC_20260921.zip`).
- On Windows: the OpenCode MCP registration got `"environment": {"GHIDRA_INSTALL_DIR":
  "C:\Users\Vinicius\Desktop\ghidra_12.1.4_PUBLIC"}` — after restarting OpenCode, REA's
  MCP uses the native Ghidra directly (no need to restart the Claude Code session used on Oct 9).

### What changed in REA since Oct 9 (the "ARM blocked" block is over, with a caveat)

- **Windows P0 now accepts PE ARMNT (0x01c4)**: `make_pe.py` generated `pnl_armnt.exe`
  (base `0x07fff000` to map payload byte 0 to VA `0x08000000`, entry RVA `0x10d8`) and
  Ghidra 12.1.4 **decompiled pseudo-C** — files `pnl_armnt.exe`/`pnl_thumb.exe` stay in the
  folder. Caveat: the PE-ARMNT loader chooses the **ARM A32** language, so the Thumb code
  comes out garbled (`software_udf`, `unaff_r4`). It might work to use it for
  `DD010_pnl` with manual annotations, but it was not the final route.
- `raw-binary` + `architecture arm` is still **refused on Windows P0** at the multi-target LF:
  "Windows Ghidra P0 accepts native PE and explicitly selected raw 6502 targets only."
  In **WSL/Linux the same command is accepted**, but REA forces `ARM:LE:32:v7` (A32):
  the 6.7.0 release Evidence explicitly says *"Big-endian ARM, **Thumb-only, Cortex-M**, …
  are unsupported in this increment"* — and `decompile --file-offset 0xd8` failed
  (`no procedure at 0x80000d8`, the A32 analysis found no function).

### ✅ The recipe that worked (clean Thumb via ELF + T bit on the entry)

Ghidra's ELF loader (Linux/WSL) with **`e_entry` carrying the Thumb bit** selects Thumb
context — `make_elf.py` with entry `0x080000d9` (the reset vector's own value) makes
Ghidra import `language_id: auto-from-header` in Thumb mode and REA returns clean pseudo-C:

```bash
# inside WSL (Ubuntu-24.04), folder /mnt/c/Users/Vinicius/Desktop/t8_sys_v102/analise
python3 scripts/make_elf.py DD010_pnl.payload.bin pnl_thumb.elf 0x08000000 0x080000d9
GHIDRA_INSTALL_DIR=/home/vinicius/ghidra_12.1.4_PUBLIC \
  npx -y rea-agents@latest decompile pnl_thumb.elf 0x080000d8 --provider ghidra --format json
```

Evidence: `ev_cd950cc5cb09…` (`pnl_thumb.elf`, sha256
`c01e208ecec0f0487d12c3fbb1c76f67c93c1cab8a8537004cdd87fc34f54f21`).

**The Reset_Handler pseudo-C confirms EVERYTHING deduced on Oct 15, now with names and
values straight from the decompiler** (key excerpt of the main loop):

- init in order: `FUN_08003604` (clock?) → `FUN_0800353c` → `FUN_08003de4` (UART 115200 ✓)
  → flash unlock `FUN_08003f14` ✓ → `_DAT_40021038 |= 1` (RCC, enables a peripheral clock).
- loop driven by flag `DAT_20000004` (ISR event toggle) and the event word at
  `0x2000002c`/`0x20000030` (flip between two cells).
- TX: `FUN_08003ec8(&DAT_20001ddc, 3)` — 3-byte message `{opcode, idx, value}` ✓,
  distinct opcodes observed: `0x93` (ADC/knob, with clamp `0..0x7f`), `0x90`/`0x91`
  (control {slot, value}), `0x80` (another control), `0xfe` (1-byte heartbeat/keepalive).
  (**Resolved on Oct 22** via `cmd_tree` `0x08004ab8`: `0x91` is **not "release"** —
  the opcode carries bit7 of the value and the payload is always the value `& 0x7f`;
  the old reading `value±0x80` was an artifact of the composition. See the canonical table below.)
- Calls with the `_1` suffix (`LAB_08003a78_1`) in Ghidra's text indicate a resolved Thumb
  context (two names for the same symbol in the merged listing) — irrelevant in practice.

### Updated next steps

1. **Decompile the remaining UART functions with the same recipe** and consolidate the protocol
   `{opcode, idx, value}` into a canonical table: `0x08003de4` (init, already confirms `0xe1 << 9`),
   `0x08002834` (HAL_UART_Transmit_IT), `0x08004cc0` / `0x08003c7a` / `0x08003d0c` /
   `0x08003d28` (RX→LED/display ring), `0x08003984`/`0x08003a10` (button/ADC dequeue).
2. Support tool in WSL ready: `npx rea-agents … decompile pnl_thumb.elf <addr>`.
   Cheaper batch alternative: `rea search pnl_thumb.elf . --kind procedures` (98
   procedures) + a `decompile` loop generating a reference `.pseudo`.
3. `DD010_app.bin` (encrypted) remains out of reach (key in the bootloader); for
   an "improved menu", the **MCU-overlay-on-UART** route still stands — the decompilation above
   gives exactly the panel side that the overlay needs to imitate/intercept.

---

## Canonical panel↔App_Main protocol table (Oct 22, via REA/Ghidra-WSL)

Symmetric and deliberate on Roland's side: **1 opcode byte `B0`** encodes the size —
if `B0 ∈ 0xF0..0xFF` the message is **1 byte** (no payload); otherwise there follow
**2 payload bytes `B1`, `B2` (each 0x00..0x7F)**. Both directions use the same
scheme (the 3-byte opcodes have bit7=1 but are not `0xF*`).

### Physical path

- **USART1** (`0x40013800`), **115200 8N1** (`FUN_08003de4`, `huart` struct at `0x20000350`),
  clocks/dma `FUN_0800275c` (MspInit: `NVIC_EnableIRQ(USART1_IRQn=27)`).
- **Panel RX**: 1 byte received per IT. `USART1_IRQHandler` (vector 43 → `0x080033cc`) →
  `HAL_UART_IRQHandler` `0x0800248c`; the `HAL_UART_Receive_IT` (wrapper `0x080027d0`) uses
  **ReceiveToIdle** internally (`0x08003124`, ISRs `0x08002cc4/0x08002e7c`). Complete-byte
  callback `FUN_08002808`: re-arms the receive and calls **`FUN_080033dc(byte)`** which inserts
  into the parse ring (struct `0x2000005c`: `[0]`/`[1]` w/r indices, `[2]` mask, `[3]` buffer
  base) and posts event bit 1 (`FUN_0800397a`→`FUN_08003a4c`).
- Main loop (flag bit 1) drains (`FUN_08003e5c`) and assembles messages: state machine
  in **`FUN_08003460`** — opcode `B0 ≥ 0x80` (1 byte if the high nibble is `0xF*`), 7-bit payload in
  `0x20000024/25/26` — and dispatches via **`FUN_08003fc0`**.
- **Panel TX**: the loop composes messages in a [double?] buffer `0x2000043c ± 0x80`
  (`DAT_20000058` alternates) and sends via `FUN_08003ec8` → `HAL_UART_Transmit_IT` (`0x08002834`).

### App_Main → Panel (RX; dispatch `0x08003fc0`)

| Opcode | Format | Handler | Action observed in code |
|---|---|---|---|
| `0xFA` | 1 byte | `FUN_08003cf0` | **full LED sync**: re-publishes the 20 LEDs of the table (ptr at `0x20000080`) into the LED ring (`0x2000131c`) |
| `0xFB` | 1 byte | `FUN_08003ca4` | **control sync**: re-publishes the 20 knob/step values (cache `0x20001454/74` vs config `0x20000088`) into the TX deque |
| `0xFF` | 1 byte | `FUN_08003a4c(0x80)` | posts the **bit7** event → **re-presentation order**: the loop runs the boot path (`FUN_08004010` re-sends `0xB1/B0/B2/UID/0xFF` + clears queues). It is **not** ping→`0xFE` (corrected rev. 4; the old reading was a misinterpretation of the dispatch) |
| `0xA0` | {idx, val}, idx<0x1f | `FUN_08003cd0` | LED/param idx: flash LUT **`0x08004f08`** (idx×3) → `FUN_080039ec` → `FUN_0800415a(0x200010ac, a, b, c, val)`: **double-buffered LED matrix** (row `c×0x18`, mask `base+0x25c`, writes `+0` and `+0x60`) |
| `0xE0` | {idx, val}, idx<0x20 | `FUN_08003e90` | same with flash LUT **`0x08004ea8`** |
| `0xB0` | {sel, state}, sel∈{0,1,2} | `FUN_08003f74` | drives `"power/reset"`: `FUN_08001596(0x50001400 \| 0x50000c00, 1/2/8, state==0)` |

### Panel → App_Main (TX; loop `0x08004ab8`)

| Opcode | Format | Source |
|---|---|---|
| `0x90` / `0x91` | {op, idx, v} (**op encodes bit7 of v**; op `0x90` = v<0x80, `0x91` = v≥0x80) | deque `0x200013cc` (`FUN_08003984`)[b15=valid → `FUN_08004884`] — **unified input**: buttons/scan and knobs/step |
| `0x80` | {0x80, b0, b1} `{id, state}` pairs | LED/event ring at `0x20001320` (`FUN_08003a10` drains; id `0x1f` = special flag) |
| `0x93` | {0x93, 0x00, v} (middle byte fixed 0) v = clamp(latch+0x40, 0..0x7f), only sends if v≠0 | 32-bit latch word `0x2000109c` (`FUN_08003d40`, read-and-clear). **latch = dial/quadrature-encoder position** (`FUN_080048e4`, deltas ±1 per detent, table `0x08004dd0`) |
| `0xFE` | 1 byte | main-loop heartbeat — event **bit6 (`0x40`)** posted by the scheduler `FUN_080022e4` every **2000 ticks** (TIM1 tick = 1 ms → **2 s period**) |
| `0xB1`/`0xB0`/`0xB2` | {op, 0, n} at boot: {0xB1,0,1}, {0xB0,0,0xD}, {0xB2,0,0} | `FUN_08004010` — presentation (event **bit7**; posted at startup and by the RX `0xFF`) |
| `0xC0` | **25-byte frame**: `0xC0` header + 24 nibbles of the 12-byte UID (`0x1FFF7590`) | same boot — device serial number |
| `0xFF` | 1 byte | close of the boot presentation (mirror of the RX `0xFF`?) |

### Main loop (`cmd_tree` `0x08004ab8` — init + loop, decompiled batch 9)

Anatomy confirmed in pseudo-C: init in order `0x080015c0 → 0x08000714(0xf,1) →
0x080007f8 → 0x08003f14 (flash unlock) → 0x08003d58 → 0x08003418 → 0x08003604 →
RCC 0x40021038 |= 1 → NVIC prio(9) → 0x0800353c → 0x08003de4 (UART) → 0x0800374c →
0x080037e0 → timer/RTOS struct `0x20000304..` `FUN_08001f48` → registrations
`FUN_08003530(adc_interp)` / `FUN_08003854(led_set)` → `FUN_08003890(0)` →
`FUN_080034c4` (reset steps) → `FUN_0800351c` (zero LED cache) → `FUN_08003860`
(matrix init) → loop.

Loop: flip `DAT_20000004`, read-and-clear the event word (`0x2000002c + flip*4`) and
dispatch by bit:

| Bit | Consumption in the loop |
|---|---|
| **bit7** (`0x80`) | **boot/re-presentation path**: `FUN_08004010` (TX `0xB1/B0/B2/UID/FF`) + clears deque/LED ring + **re-registers** the matrix callbacks (`FUN_08003eb0(cb_3954)`, `FUN_08003ebc(cb_3970)`, `FUN_08003f08(cb_3a04)`). Posted at startup and by the RX `0xFF` |
| bit0 | `FUN_08003460` — RX parser |
| **bit3** (`0x08`) | TX `0x93 {0x93, 0x00, clamp(latch+0x40)}` if ≠0 — posted by the scheduler (every 200 ticks, if latch≠0) **and** by `cb_3a04` (encoder detent) |
| **bit4** (`0x10`, `cb_3954`) | drains the control deque → TX `0x90`/`0x91` (1st call with flag=1 switches the deque bank) |
| **bit5** (`0x20`, `cb_3970`) | drains the LED/event ring → TX `0x80` |
| **bit6** (`0x40`) | TX `0xFE` heartbeat (1 byte) — posted by the scheduler every 2000 ticks |

*(Correction rev. 4: rev. 3 read the dispatch with the test `(evt << k) < 0` shifted
by one bit — `<<0x1c` tests bit **3**, not 4. The table above comes from the complete
dispatch of `0x08004ab8`.)*

`cb_3954`/`cb_3970`/`cb_3a04` are just **event posters** (`0x10` = bit4,
`0x20` = bit5, `0x08` = bit3) — this is how the matrix scan engine signals
"something changed" to the loop. The matrix's physical engine (base `0x200010ac`,
halfword planes `+0/+0x60/+0xc0/+0x120/+0x180/+0x1e0` per row of `0x18`, mask per `a`
in the table `base+0x25c`):

Per cell (`{a, c, col}` → base `c*0x18 + col*2`): `FUN_08004450(matrix, op 0..4, a,
  c, col)` **turns on plane `op` (P1=`+0xc0`, P2=`+0x120`, P3=`+0x180`, P4=`+0x1e0`) with the
  mask of `a` (`base+0x25c` + `a*8+4`) and clears the other three**; the base planes
  `+0` ("A" = applied) and `+0x60` ("B" = pending) are maintained by `FUN_0800412c`
  (set in both) and `FUN_08004340` (set A / clear B — transition). The RX `val`
  (`0xA0`/`0xE0`) = `{val&0xf:` `0` or default → op phase 0 and **clear** on both base
  planes; `2..5` → op phase `1..4`; `val>>4` = sub-mode (`0` = set-both, `≠0` = set-A/clear-B)}`
  via `FUN_0800415a`.

### Knob/ADC engine (`0x08003a78`, "adc_interp", in=0 — via pointer `0x20000e30`)

- Channel struct @ **`0x20000088`, stride 0xc**: `+0` control id (`0x7f` = skip),
  `+1` curve (0..10) — and `0x3ff` values are the RAW scale.
- Curves: `0` linear (deadzone 10, top ~0x3f5) → 0..0xff; `4`/`6`/`7` steps (detection via
  `FUN_080038a4`: flash table at `0x08004e60…0x08004ea4`, {lo,hi} per step, number of
  steps depends on the type: 1/2/3/5; per-channel state at `0x20001474`, `0xff` = pending);
  `8`/**`9`** **auto-calibration** (real min/max persist at `+4/+8` of the channel, hysteresis ±0x32);
  `10` spring-center: v ∈ [0x1c4..0x23b] → `0x80` (neutral), outside → 1..0x7f/0x81..0xff.
- Output: cache `[0x20001454+channel]` (keyed ± hysteresis) and pushes `FUN_08004884(0x200013cc,
  id, v)` — the same deque as the buttons; special case control id `0x12` publishes `0x1f`\+flag
  (>0xf0) into the LED ring.

### Notes on the LED paths (corrects the Oct 15 hand-analysis)

- `FUN_08003cf0` (RX `0xFA`) contains the **whole** walk: the blocks at `0x08003d0c` and
  `0x08003d28` are **inside** it, not separate functions (the linear listing is misleading).
- `0x08003c50` ("led_set", decompiled via the symtab symbol) is the **incremental update of
  1 LED**, registered as a callback (`FUN_08003854` → ptr `0x20000d3c`): it reads the pair
  `{flag, led_id}` from the table at `idx*2` (skip if id `0x7f`; `flag==1` = inverts the
  requested state), compares with
  the state cache `0x200013ac`, writes the new state and pushes `{led_id, state}` into the ring
  `0x2000131c` via `FUN_08004cc0` (ring base −0x90).
- The LED cache `0x200013ac` (0x20 bytes) is zeroed by `FUN_0800351c`.

**Method note (fine round Oct 22):** `FUN_08004010` (boot TX) confirms the TX opcodes
`0xB1 {0,1}`, `0xB0 {0,0xD}`, `0xB2 {0,0}`, UID frame `0xC0` (header constants in
flash `0x08004108` = `C0 00 00 00…`, UID → nibbles) and `0xFF` beacon — the panel uses the
same opcode family in both directions. The second deque (`0x20001084`, init by
`FUN_08003890`/`FUN_080048a8`) has the counter/latch at `+0x18` (`0x2000109c`) and a
2-pin monitor (states at `+5`, descriptor at `+8/+0xc` and `+0x10/+0x14`); the
posters `cb_3954/3970/3a04` were registered at `0x20001450`/`0x200013a8`/`0x200014e0`.
The physical matrix **scan driver**: `FUN_080045cc` (bit-by-bit composition of the
A/B planes by groups `+0x265`, pins at `+0x240`) → `FUN_08004370` (real output, not
decompiled). **Latch writer found (rev. 4):** `FUN_080048e4` — quadrature
encoder (see the *"Edge round"* section below).

All the addresses above are real Ghidra pseudo-C (REA Evidence),
except the business semantics beyond the code — e.g. which side uses `0xB0`-pin (maybe a
sub-circuit reset) — which still needs a sniff checking the flags. The "function
referenced only by pointer" (in=0 in the cfg) technique was solved by adding `.symtab` to the ELF
(`scripts/make_elf_sym.py`, 23 FUNC symbols — Ghidra creates the procedures from the
STT_FUNC symbols with the Thumb bit). Tools `analise/scripts/rea_uart_batch*.sh` +
`extract_pseudo.py`; pseudo-C of every protocol function in `analise/pseudo/`.

Next steps (rev. Oct 22): (1) sniff the real UART to validate ambiguous semantics
(`0x93`/`0x80`/`0xB0` and the button release); (2) optional: full batch of the 212 functions via
`make_elf_sym`+a `decompile` loop; (3) overlay on the UART as already planned.

---

## Audit / revalidation (night of Oct 22, rev. 5)

User request: review everything and separate what is **code-verified [V]**,
**verified by the image's bytes/vectors [I]**, **validated in the simulator [S]**
and **open inference [⚠]**. Result — 4 silent inferences were caught:
one **overturned by code**, one **vector mix-up**, one that **was ⚠ and became
code-verified**, and one **parser nuance recorded**:

1. **[OVERTURNED] "Presentation on cold boot"** — it was an inference (never marked ⚠ in
   the doc!). Complete inventory: the event word has **a single writer**
   (`FUN_08003a4c`) with **7 call sites** in the `.lst` — scheduler (`0x08`,`0x40`),
   `cb_3954 (0x10)`, `cb_3970 (0x20)`, `FUN_0800397a (0x01, RX byte)`,
   `cb_3a04 (0x08, encoder)` and the RX `0xFF` handler `(0x80)`. **Nobody posts `0x80`
   at startup**. The panel starts mute; first frame = `0xFE` heartbeat @2 s; the
   presentation goes out **only** as a response to the RX `0xFF` (the App opens the conversation).
   Simulator redone to match this behavior → smoke 10/10. [V]
2. **[CORRECTED] "SysTick weak/empty"** — a vector was confused: weak/empty is the **PendSV**
   (vector 14 / `0x08002934`); the SysTick_Handler (vector 15 / `0x08002938`) is a real
   handler that only calls `FUN_080015b0()` (RTOS tick). The protocol tick is still
   TIM1/TIM3 (vectors 29/32 → wrappers `0x08002960/70` → `FUN_0800215c`). [I]
3. **[PROMOTED] Heartbeat/dial period** — was ⚠; now: UART init writes
   **115200 literal** (`0x1c200`) in the BaudRate field + `Mode=0xc` (TX|RX) [V];
   **no** function writes to RCC_CR/PLLCFGR → **HSI 16 MHz** from reset [V];
   TIM1 `15999` → **1 ms/tick** exact (heartbeat = 2 s, dial = 200 ms, workers
   2/4 ms) [V]; TIM3 `0x31ff` → ~1.25 kHz, matrix in 10 phases (round-robin
   `0x20000024`, wrap at 10) [V]. `0x08003604` is **GPIO** init (IOPENR `0x2f` +
   per-port modes), not clock. RTOS soft-timer = **TIM14** (`0x20000304 =
   0x40002000`). The 4 ms worker `FUN_0800392c` = flag `0x20000060` + a 4-B copy
   `0x2000107a → 0x20000208` (outside the protocol, UI purpose ⚠).
4. **[RECORDED] Hard framing rule** — parser re-read: **a byte ≥ 0x80 in the middle
   of B1/B2 is treated as a new opcode** (frame abandoned); unknown RX
   opcodes fall into the void of `FUN_08003fc0` (no default handler). [V]
5. **Anchors re-checked in the image**: delta table `0x08004dd0` = `+1` on
   `01→00`, `−1` on `10→00`, the rest 0 (**detent** scheme: counts only the arrival at
   rest 00) [I]; UID skeleton `0x08004108`: `C0 00…` + embedded pointer `0x1FFF7590` [I].

**Final spec classification (PROTOCOL.md):** physical layer [V/I], framing [V],
RX dispatch [V], TX plan [V], timing [V (clock pipeline already proven inside the
payload)], handshake [V on the panel direction; App_Main ⚠]. Remaining ⚠ are **only**
business semantics outside the code: the map of the 20 LED ids, the physical function
of the 3 `0xB0` pins, the meaning of the boot `0xB0 {0,0xD}`, the real behavior (gifts)
of the App_Main, the device's real UID — all sniffable in round C.

---

## Edge round (afternoon of Oct 22, rev. 4 — REA batches 11/12)

The batch closed the three holes of rev. 3: **who writes the `0x93` latch**, **who posts the
heartbeat bit6** and **the time base**. All code-verified:

### Scheduler (`FUN_080022e4`) — dual dispatch by peripheral base

Called by the IRQ of **two** timers; `*param_1` = peripheral base:

- **`0x40012c00` = TIM1** (tick base — config in `FUN_0800374c`: value **15999**;
  with TIMxCLK = 16 MHz → prescaler 16000 → **tick = 1 ms**). Software counters
  (struct in RAM `0x20000004+`, all `_DAT_`):
  | Field | Threshold | Action |
  |---|---|---|
  | `+0x14` (0x20000018) | −1 clamp | down-counter (consumed by another task) |
  | `+0x18` (0x2000001c) | 4 | `FUN_0800392c` (every 4 ms) |
  | `+0xc` (0x20000010) | 2 | `FUN_08003450` → `FUN_080047c0(&0x20000d3c)` — worker of the registered callbacks (`led_set`, every 2 ms) |
  | `+8` (0x2000000c) | 200 | gate `FUN_0800343c(0) ≠ 0` (dial latch ≠ 0) → **posts `0x08`** → loop → **TX `0x93`** (poll every 200 ms) |
  | `+0x10` (0x20000014) | 2000 | **posts `0x40`** → loop → **TX `0xFE`** (heartbeat = **2 s**) |
- **`0x40000400` = TIM3** (config in `FUN_080037e0`: value **0x31ff** = 12800 →
  ~1.25 kHz): LED matrix scan — alternates `FUN_08003960` (= `FUN_08004516`)
  / `FUN_08003870` (= `FUN_080045cc`) with the round-robin counter `0x20000024` (0..9, 10 phases).

Method note: **PendSV (vector 14) is weak/empty** — the real SysTick_Handler (vector 15 →
`0x08002938`) is the RTOS/HAL's own handler (not to be confused with the protocol tick);
the TIM1/TIM3 IRQs (vectors 29/32 → wrappers `0x08002960`/`0x08002970` →
`FUN_0800215c(handle)`) call `FUN_080022e4` and it is this one that ticks the protocol.
`0x08001f48` is the *start* of the RTOS soft-timer (**TIM14**, base `0x20000304 = 0x40002000`
in the cmd_tree init), not the tick itself.

### Dial/detent encoder — writer of `0x2000109c` (`FUN_080048e4`)

Monitor tick (struct `0x20001084`): reads the 2 quadrature pins (descriptors `+8/+0xc`
and `+0x10/+0x14` — GPIO base + mask; read = `FUN_0800158c`: `(*(base+0x10) & mask)`,
IDR), combines `{old state, new}` into a nibble and indexes the **signed delta table**
in flash `0x08004dd0`:

- `+1` on the `01→00` transition, `−1` on `10→00`, `0` on the other 14 — a **detent** pattern
  (each dial detent = ±1 on the latch).
- `latch(+0x18) += delta`; states `+0x1c/+0x20` (pins), `+0x24` = last delta,
  byte `+5` = state nibble, `+4` = "active" flag.
- On a detent it calls `FUN_08000580(0x00010005, a, b, 0,0)` — an RTOS **SVC** wrapper
  (set-signals: scrapes exception/priv, packs flags `0x00010005` and dispatches via
  `FUN_080005e4`) — the notification path that ends at the poster `cb_3a04` → `0x08`.

Consequence for the protocol: **`0x93` = relative dial position** —
`v = clamp(latch_since_last_read + 0x40, 0..0x7f)`, centered on 64 detents,
sent every ≤200 ms while there is rotation (and v≠0).

### RX `0xFF` = re-presentation (corrects the ⚠ ping→`0xFE`)

The handler `FUN_08003a4c(0x80)` posts **bit7** — the same track as startup. The loop
runs again: clears the queues (deque + ring), re-registers the callbacks and calls
`FUN_08004010` → re-sends `0xB1/0xB0/B2/UID/FF`. That is: **the App asks "present
yourself again"**, plausibly when (re)opening the serial port. The old correlation "RX `0xFF`
→ TX `0xFE`" was a wrong reading of the bit test in the dispatch. Validated in the simulator:
the app receives the full presentation 2× in the smoke test.

### Mirroring in the simulator (`sim/`)

- The panel serializes **all** TX through the single queue (`txq`) — like `FUN_08003ec8`
  (the inline presentation on the RX thread caused real interleaving: `ConnectionAborted`/
  decoder desync on the app — bug reproduced and fixed).
- Tick model: `--tick-ms` (default 1.0 = 1 kHz) → dial poll 200 ticks (200 ms),
  heartbeat 2000 ticks (2 s); the `0x93` gate = latch≠0 and `latch_sent`.
- RX `0xFF`: re-presentation with `queue.clear()` first (mirrors the real clearing).
- The `d <n>` command on the panel's stdin simulates dial detents.
- `smoke_test.py`: **10/10 PASS** (Oct 22, includes the timer heartbeat and `0x93 {0x93,0x00,0x45}`).
