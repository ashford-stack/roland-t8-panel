# T-8 simulator — virtual panel ↔ App_Main pair

Python implementation of the decoded protocol (`../analise/PROTOCOL.md`,
rev. 2026-10-22). No hardware: the default transport is TCP loopback, which
behaves like a byte-by-byte serial stream. To go to the real device later,
only the transport changes (`--transport com --port COMx`, needs `pyserial`).

> **Note:** `t8_proto.py` ships empty in this snapshot (the shared framing module
> is missing from the archive). The simulators import from it, so they will not run
> as-is until `t8_proto.py` is restored. It must provide: `Decoder`, `pretty`,
> `encode_1b`, `encode_3b`, `encode_ctl`, `uid_frame`, `RX_OPS`, `TX_OPS`.

## Files

| File | Role |
|---|---|
| `t8_proto.py` | Shared framing: 1 byte if `B0 ≥ 0xF0`, otherwise 3 bytes with 7-bit payloads; **exception: `0xC0` (UID) = single 25-byte frame** (discovered in the simulator). Encoder `encode_ctl` (the opcode carries bit7 of the value). |
| `t8_panel_sim.py` | **Panel** simulator (TCP server). **Does not present at boot** (audit: no bit7 poster at startup) — the first frame is the `0xFE` heartbeat (2000 ticks, `--tick-ms` 1 ms = 2 s); RX `0xFF` → will present (bit7 of the real code); `0xFA` → re-publishes LEDs as `0x80 {id, state}`; `0xFB` → re-reports controls (`0x90/0x91`); `0xA0/0xE0` → LED state; `0xB0` → pin log; dial → `0x93 {0x93, 0, clamp(latch+0x40)}`. **All TX goes through the single queue (`txq`)** — like the firmware's `FUN_08003ec8`; without it the app's decoder desyncs. |
| `t8_app_sim.py` | Fake App_Main (TCP client): opens the conversation by sending `0xFF` (presentation), decodes the UID, LED/pin demo, `0xFF` ping every 5 s. |
| `smoke_test.py` | Automated script: brings up both, injects knob/button/dial on the panel and ping/sync/LED/pin on the app, closes with 10 checks. `result: PASS` = pair OK. |

## Usage

    python smoke_test.py                       # full validation (~9 s)

Two interactive terminals:

    python t8_panel_sim.py                     # panel (waits for peer on 8752)
    python t8_app_sim.py                       # app (connects)

Panel commands: `p <slot> 0|1` (button), `k <slot> <0..255>` (knob),
`d <n>` (dial/encoder: n detents, fires the `0x93`), `l` (LED dump), `q`.
App commands: `ping`, `sync`, `led <idx> <val>`, `ledb <idx> <val>`,
`pin <sel> <state>`, `q`.

## Fidelity notes

- The control value's bit7 travels **in the opcode** (`0x90` = bit7=0, `0x91` = bit7=1);
  the app recomposes `v = b2 | 0x80*op_bit` — exactly as the real panel assembles it
  (`cmd_tree` `0x08004ab8`).
- The dial/encoder: real quadrature with a delta table at `0x08004dd0` (+1 on 01→00,
  −1 on 10→00 = detents); the latch is read and cleared on the 200-tick poll
  (`FUN_0800343c`/"gate"). In the sim, `d <n>` increments the latch and the next poll sends
  `0x93 {0x93, 0, clamp(latch+0x40)}`.
- RX `0xFF` = re-presentation order (the `cmd_tree`'s bit7 path): clears queues and
  re-sends `0xB1/B0/B2/UID/FF`. The `0xFE` is only a timer heartbeat (2 s), never a ping
  response.
- The boot presentation order follows `FUN_08004010` (pseudo `analise/pseudo/0x08004010.txt`).
