# T-8 serial protocol: Panel ↔ App_Main — implementation spec

**Rev. 2026-10-22 (spec rev. 2 — encoding/TX/RX/timing code-verified in the
edge round)** · Source: REA/Ghidra decompilation of the panel firmware
(`DD010_pnl`, 20,532-byte payload, base `0x08000000` — evidence in `analise/pseudo/`).
Panel side: **100% code**. App_Main side: inferred from the behavior the panel expects
(items marked ⚠️ are hypotheses — validate with sniff/simulator).

## 1. Physical layer

| Item | Value |
|---|---|
| UART | STM32 G030 USART1 (`0x40013800`) |
| Speed | **115200**, **8N1** |
| Panel RX output | 1 byte per reception (internal `ReceiveToIdle`, buffer `0x20000000`) |
| Panel TX output | blocking, double buffer `0x2000043c ± 0x80` |

## 2. Message encoding (both directions)

A message is:

- **1 byte** if `B0 ∈ 0xF0..0xFF` ("control" opcodes);
- **3 bytes** `{B0, B1, B2}` otherwise. **B0 has bit7=1** (it is in `0x80..0xEF`),
  and **B1/B2 are always 7 bits** (`0x00..0x7F`) — 8-bit values are split:
  the **bit 7 of the value is carried by the opcode** (see `0x90/0x91` below).

There is no checksum, explicit length, or address byte. The RX parser tolerates noise: a
byte `< 0x80` out of context resets the machine's state.

> ⚠️ **Length exception (discovered in the simulator, rev. 2026-10-22):** the TX frame
> `0xC0` (UID) is **25 fixed bytes** — the rule "3 bytes for every opcode with bit7"
> applies to the *panel's* RX parser; a consumer on the App_Main side needs a
> **per-opcode length table** (`{0xC0: 25}`), otherwise the UID frame breaks
> into loose nibbles (~22 garbage "1-byte messages").

> ⚠️ Implication: any continuous data stream needs breathing room (IDLE); the panel
> side uses `ReceiveToIdle` and processes byte-by-byte — messages may stick to the next
> byte with no frame-separator pattern on the wire. Parser detail
> (`FUN_08003460`, re-verified in the audit): **a byte ≥ 0x80 dropped in the middle of B1/B2 is
> treated as a new opcode** (the current frame is abandoned) — the 7-bit payloads
> are mandatory, not just a convention. Unknown RX opcodes (`0xFC/0xFD/0xFE` etc.)
> fall into the void of the dispatcher `FUN_08003fc0` (no action).

## 3. Panel → App_Main (TX)

Composed in the main loop (`cmd_tree`/`0x08004ab8`) — drains queues and sends via
`FUN_08003ec8(buf, len)` → `HAL_UART_Transmit_IT`:

| Opcode | Frame | Semantics | Evidence |
|---|---|---|---|
| `0x90` | `{0x90, slot, v&0x7f}` | control (button/knob) `slot` changed to the 8-bit value `v` (bit7=0) | deque `0x200013cc` |
| `0x91` | `{0x91, slot, v&0x7f}` | same — `0x91` appears when `v ≥ 0x80` (**the opcode encodes bit7**, it is not "release") | same |
| `0x80` | `{0x80, b0, b1}` | `{id, state}` pair from the LED/event ring — LED id `0x1f` = special flag | ring `0x20001320` |
| `0x93` | `{0x93, 0x00, v}` | **relative dial/encoder position**: `v = clamp(latch+0x40, 0..0x7f)` (centered on 64 detents); sends only if `v ≠ 0`; latch accumulated by quadrature (`FUN_080048e4`, delta table `0x08004dd0`) and polled **every ≥200 ms** while rotating | latch `0x2000109c` |
| `0xFE` | 1 byte | heartbeat **every 2000 ticks = 2 s** | event bit6 (`0x40`), posted by the scheduler `FUN_080022e4` |
| `0xB1` | `{0xB1, 0x00, 0x01}` | **boot presentation** | `FUN_08004010` |
| `0xB0` | `{0xB0, 0x00, 0x0D}` | same (announces capabilities?) ⚠️ | same |
| `0xB2` | `{0xB2, 0x00, 0x00}` | same | same |
| `0xC0` | **25 bytes**: `0xC0` + 24 nibbles of the UID (12 B at `0x1FFF7590`) | instrument serial number | same |
| `0xFF` | 1 byte | close of the presentation ⚠️ | same |

Observed boot order: `0xB1..` → `0xB0..` → `0xB2..` → UID → `0xFF`.

### Timing (code-verified, edge round)

- Base tick = **TIM1** (`0x40012c00`), prescaler 15999 @ **HSI 16 MHz** → **1 ms/tick**
  (`FUN_0800374c`; value 15999 is the prescaler and the firmware **does not write to RCC_CR/PLL
  in any function** → reset clock 16 MHz). `FUN_08003604` = GPIO init (IOPENR
  and per-port modes), not clock.
- Dial poll: every 200 ticks (200 ms), gate latch≠0 → posts `0x08` → TX `0x93`.
- Heartbeat `0xFE`: every 2000 ticks (**2 s**) → posts `0x40`. **The panel's first frame
  on the wire is this heartbeat** — the presentation does not go out spontaneously.
- LED matrix: TIM3 (`0x40000400`, value 0x31ff → ~1.25 kHz), scan in 10 phases
  (round-robin `0x20000024`), fast workers every 2/4 ticks.

### Boot handshake (code-verified, rev. 2)

0. Panel powers on → init (incl. UART) → loop. **It does not send the presentation** — the
   complete inventory of the 7 call sites of `FUN_08003a4c` (the sole writer of the event word)
   shows that **nobody posts `0x80` at startup**; the posters are: scheduler
   (`0x08` dial-poll, `0x40` heartbeat), `cb_3954 (0x10)`, `cb_3970 (0x20)`,
   `FUN_0800397a (0x01, RX byte)`, `cb_3a04 (0x08, encoder)` and the RX `0xFF` handler.
1. The panel starts talking on its own only with the **`0xFE` heartbeat every 2 s**;
2. ⚠️ App_Main (on opening the port) sends `0xFF` → the panel posts bit7, clears queues,
   re-registers callbacks and **re-sends** `{0xB1}{0xB0}{0xB2}[UID 25B]{0xFF}`;
3. `0xFE` is only a heartbeat — never a ping response. The App syncs with `0xFA`/`0xFB`
   and sends the initial LED state (`0xA0`/`0xE0`).

## 4. App_Main → Panel (RX)

Parser (`FUN_080033dc`→ring→`FUN_08003460`→`FUN_08003fc0`):

| Opcode | Frame | Action on the panel | Evidence |
|---|---|---|---|
| `0xFA` | 1 byte | **LED sync**: re-publishes the 20 LEDs of the display table (ptr `0x20000080`), one at a time into the ring `0x2000131c` | `FUN_08003cf0` |
| `0xFB` | 1 byte | **control sync**: re-reports a snapshot of the 20 knobs/steps into the TX deque | `FUN_08003ca4` |
| `0xFF` | 1 byte | **re-presentation order** — posts bit7: the panel clears queues, re-registers callbacks and re-sends `0xB1/B0/B2/UID/FF`. *Corrected in spec rev. 2: it is not a ping and does not generate `0xFE`* | `FUN_08003a4c(0x80)` |
| `0xA0` | `{0xA0, idx, val}` idx<0x1f | **LED/param idx → val** via flash LUT `0x08004f08` (idx×3 {a,b,c}) → writes to the double-buffered LED matrix (`FUN_0800415a`) | `FUN_08003cd0` |
| `0xE0` | `{0xE0, idx, val}` idx<0x20 | same via the second LUT `0x08004ea8` | `FUN_08003e90` |
| `0xB0` | `{0xB0, sel, state}` sel∈{0,1,2} | drives 1 of 3 pins (`0x50001400`/`0x50000c00`, pin `1`/`2`/`8`, level `state==0`) — ⚠️ physical function unknown (display power/reset?) | `FUN_08003f74` |

### Semantics of `val` in the `0xA0`/`0xE0` opcodes

`val` describes **how to write** into the LED matrix (structure `0x200010ac`, pseudo in
`pseudo/0x0800415a.txt`):

- `val & 0xf` = **scan phase** (op): `0` or `1` → re-applies op 0; `2..5` → op `1..4`.
  `FUN_08004450(matrix, op, a, c, col)` **turns on plane `op` and clears the others** (planes
  `+0xc0/+0x120/+0x180/+0x1e0` per cell `c*0x18+col*2`, mask per `a` at `base+0x25c+a*8+4`).
- `val >> 4` = application on planes "A" (`+0`) and "B" (`+0x60`): `0` = **set in both**;
  `≠0` = **set A / clear B** (pending transition).
- `a/b/c` from the LUT: a = mask index (0..0xb; number of active groups in `+0x265`),
  b = not used directly in the write (passed through), c = destination row/cell.
  ⚠️ reading from decompilation.

## 5. Knob/ADC engine (`0x08003a78`, "adc_interp")

Called via pointer `0x20000e30`; caller not located — probably the DMA/ADC ISR.
Per-channel config at `0x20000088` stride 12:

| Offset | Content |
|---|---|
| `+0` | control id (0..0x1e; `0x7f` = disabled slot) |
| `+1` | **curve** (0..10) |
| `+4` | calibration min (used/written by curves 8/9) |
| `+8` | calibration max (same) |

Curves:

| Curve | Behavior |
|---|---|
| `0` (and default) | linear: input `0..10` → 0; `≥0x3f5` → 0xff; the rest scales to 0..0xff |
| `4..7` | **steps** with hysteresis via `FUN_080038a4` — table of {lo,hi} pairs in flash (`0x08004e60..ea4`), number of steps depends on the type (1/2/3/5); per-channel state at `0x20001474` (`0xff` = pending); a change publishes into the TX deque |
| `8`/`9` | **auto-calibration** of min/max with hysteresis ±0x32 (50) — persists in fields `+4/+8` |
| `10` | **spring-center** (joystick-like): value in `0x1c4..0x23b` → `0x80` (neutral); below 1..0x7f, above 0x81..0xff |

Output: cache `0x20001454+channel`; pushes into the unified deque `FUN_08004884(0x200013cc, id, v)`
(the same queue as the buttons). Step cache at `0x20001474`. Special control id `0x12`:
publishes `{0x1f, flag(v>0xf0)}` into the LED ring — goes out as TX `{0x80, 0x1f, flag}`.
⚠️ business semantics (LED "big"/exception/pad?) to confirm in the sniff.

## 6. Useful RAM map (panel-side implementation)

| Address | Content |
|---|---|
| `0x20000000` | 1-byte RX buffer |
| `0x20000024/25/26` | RX message under construction `{B0,B1,B2}` |
| `0x20000008` | RX parser state |
| `0x2000002c`/`0x20000030` | event words (flip `0x20000004`) |
| `0x2000005c` | RX parse ring struct {w, r, mask, base} |
| `0x20000080` | ptr to the LED table {flag, led_id} ×0x20 |
| `0x20000088` | ADC channel config (0..0x1f ×12 bytes) |
| `0x20001084` | **dial quadrature encoder** (states `+5`; GPIO descriptors `+8/+0xc`/`+0x10/+0x14`; latch `+0x18` = `0x2000109c` of the `0x93`) |
| `0x200010ac` | LED matrix (planes A `+0` / B `+0x60`, mask `+0x25c`, number of groups `+0x265`) |
| `0x2000131c` | LED/event ring (buffer `0x20001320`; w `0x200013a0`; r `0x200013a4`) |
| `0x200013ac` | LED state cache (0x20 bytes) |
| `0x200013cc` | control deque (2 banks ×32 halfwords, bit15 = valid) |
| `0x20001454`/`0x20001474` | value / step cache per ADC channel |

## 7. What is NOT in the protocol (and what to do)

- **No CRC** — for the overlay/simulator, losing/delaying bytes between messages is recoverable:
  the parser discards and resyncs on the next byte ≥0x80.
- **No timestamps** — the `0xFE` heartbeat (every 2 s) is the only "I'm alive"; the `0xFF` is
  a re-presentation request, not a keepalive.

## 8. Simulator implementation notes

For the **panel simulator** (replacing the MCU on the UART):

1. Listen at 115200 8N1. **Never talk first** (fidelity: there is no bit7 poster at boot);
   the first TX is the `{0xFE}` heartbeat every 2 s — it is what proves the link to the peer;
2. On receiving `0xFF`: **present yourself** — clear queues and send
   `{0xB1,0,1}{0xB0,0,0xD}{0xB2,0,0}[UID 25B]{0xFF}` (same as the firmware's bit7 path);
3. Autonomous `0xFE` heartbeat every 2 s (1 ms tick model: `--tick-ms 1.0` of the sim);
4. Buttons: push `{0x90|0x91, slot, v&0x7f}` (control slots 0..0x1f);
   knobs: values 0..255 likewise (on the real panel the curves map the ADC);
   dial: `d <n>` in the sim increments the latch → `0x93 {0x93,0,clamp(latch+0x40)}`;
5. LEDs: on receiving `0xA0/0xE0 {idx,val}` — the minimal functional response is to log/echo
   (the real panel's LED matrix has planes/phases; to simulate the UI you only need the `idx`+`val`);
6. `0xFA`/`0xFB` = request for the full listing/state; satisfy it by re-publishing the current state
   serially (`0x80 {id, state}` / deque `0x90/0x91`);
7. `0xB0 {sel, state}`: register/log it (affects physical pins on the real device).
8. **On the App side replacing App_Main:** open the port and send `0xFF` first;
   wait for the presentation before assuming the panel is "alive" (the `0xFE` arrives on its own).
