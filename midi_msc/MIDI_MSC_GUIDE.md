# GUIDE — Solder-free USB front: MIDI log + MSC inventory (read-only)

Goal: the T-8 has **a single external connection (USB)** and you have no soldering
equipment. This guide extracts from the USB **the last few meters of documentation**
possible without opening the device:

- **Part A — USB-MIDI log**: records what the T-8 **sends and receives**, with timestamps,
  while you use the pads/dial/sequencer. This documents the observable behavior
  of the App_Main/E4E side — the layer outside the internal protocol we already decompiled.
- **Part B — MSC inventory (read-only)**: catalogs everything the update mode exposes,
  tying the format section of `ANALYSIS.md` to the real numbers on the PC screen.

**Guarantees**: nothing here writes to the device. Reading, listening, and nothing else.
The flash test (`update_teste\T8_UPD.BIN`) is a separate decision and is NOT part of this guide.

---

## Part A — MIDI log over USB

### A1. Installation (once — already done by me on Oct 22)

```
py -m pip install pygame
```

(The script uses **`pygame.midi`**/PortMidi, which ships as a pre-compiled wheel for
Windows/Python 3.13. The original `mido`+`python-rtmidi` route **breaks** in this environment:
`python-rtmidi` only ships source code for 3.13 and requires Visual Studio C++ to
compile — a `meson`/`cl` error recorded on Oct 22. Don't waste time on it.)

### A2. Preparation

1. Close DAWs (Ableton, etc.) and any app that might be holding the T-8's MIDI
   ports — on Windows, MIDI ports are per-process exclusive.
2. Turn on the T-8 normally (normal use mode) and connect the USB-C cable to the PC.

### A3. Run the logger

```
py C:\Users\Vinicius\Desktop\t8_sys_v102\midi_msc\t8_midi_log.py
```

- It detects the ports whose name contains `T-8` and opens the input + output ones.
  On your machine (Oct 22) the real ports showed up as `dev1: T-8` (input) and
  `dev3: T-8` (output) — the output deliberately ignores the "Microsoft MIDI Mapper".
  The `Hello from the pygame community` line at the start is pygame's banner: normal.
- Each message appears as:
  `   3.214  [IN ] T-8  note_on channel=9 note=60 velocity=127  hex=...`
- Everything is also recorded in `midi_msc\logs\midi_log_....log`.
- Commands during the run (to **send** something to the T-8):

  | Command           | What it does                               |
  |-------------------|--------------------------------------------|
  | `n 36 120 9`      | Note On+Off (note 36, vel 120, channel 10) |
  | `c 20 64 1`       | Control Change CC20=64 on channel 1        |
  | `st` / `sp` / `rel` | transport Start / Stop / Continue        |
  | `q`               | quit (writes the log)                      |

### A4. Exploration script (while the logger runs)

Do each item **with a few seconds' pause between them** and **note the approximate time**
loosely — the log timestamp lets you correlate:

| # | Action on the T-8 | What I expect in the log (hypothesis) |
|---|-------------------|---------------------------------------|
| 1 | Hold/release each pad 1–8 | Note On/Off or CC? **we want to know** |
| 2 | Turn the dial slowly (close the dialog first) | continuous CC? |
| 3 | Press REC, Play | transport (start/stop) or notes? |
| 4 | Activate/delete sequencer steps | ? |
| 5 | Switch A/B, Pattern ⇧/⇩, Sound ⇧/⇩ | Program Change? nothing? |
| 6 | Move the slider | CC? |
| 7 | After item 2: `st`, wait 2 s, `sp` | does the T-8 send barred Clock (0xF8)? |
| 8 | `n 36` (kick note on channel 10) | lights up pad 1 / plays the sound? |
| 9 | `n 38`, `n 42`, `n 39` | maps the kit's kick/snare/hat? |
| 10 | Unplug and replug USB | does a system message appear? |

**Visual** observations (LED lit/sound playing) are gold: note them alongside.

### A5. Possible results and what they mean

Update Oct 22: the **ports already exist** (`dev1` input, `dev3` output) — the
"no MIDI in v1.02" hypothesis already fell. What remains is the golden question: **does traffic flow?**

- **Rich log** → we map Note/CC/transport + physical correlation → a new section
  `PROTOCOL_MIDI.md` tying the E4E side to the real device.
- **Ports exist but nothing flows** → the firmware only exchanges MIDI if configured/requested
  (document it that way).
- **No port appears** → the `App_Main` v1.02 does not expose USB-MIDI (or only audio);
  a negative result documented — closes the question for good.

If the script doesn't run (e.g. `mido` not installed), send me the full output.

---

## Part B — MSC inventory (READ-ONLY)

### B1. MSC mode

1. Turn off the T-8.
2. Hold **Shift** and turn it on (the same combo you used to extract the original).
3. The T-8 mounts as USB storage in Explorer.

### B2. Cataloging (nothing beyond looking)

1. Note the **drive letter** and the **volume label**.
2. List the whole tree: in Explorer, or via terminal:

   ```
   tree /f <drive>:\
   dir <drive>: /s /a
   ```

   (paste the entire output back to me)
3. For each file note/screenshot: **name, size, modification date**.
4. Optional screenshot of the drive root as it is.

### B3. Explicit prohibitions (truly read-only)

- ❌ **Do not delete, rename, create a folder, or move ANY file**.
- ❌ **Do NOT paste `update_teste\T8_UPD.BIN` now** — the flash test is another decision,
  for when YOU want it, with its own guide (`T8_UPD.BIN.INFO.txt`).
- ✅ Copying a file from the device **to the PC** is reading and is allowed.
- When done: **safe ejection** of the drive ("Remove hardware" icon) and turn off the T-8.
  Turning it on again without Shift = normal use mode.

### B4. What this ties into the doc

- Confirms whether the MSC mode shows **only** `T8_UPD.BIN` or also configs/settings —
  if there is a settings file, its scheme enters the analysis (no risk).
- Validates real size/name against what we decompiled (`./_tmp/DD010_pnl.bin`,
  `./_tmp/DD010_app.bin`, CRCs etc.).

---

## What to bring back to me

1. The `midi_msc\logs\midi_log_*.log` file(s) (or an excerpt with the times).
2. Your notes from the A4 script (including "nothing happened").
3. The listing/screenshot from Part B.
4. Any strange behavior (audio crash, LED lit for no reason, etc.).

With that I write the "outside view" evidence section in `ANALYSIS.md` and,
if the MIDI pans out, I start `PROTOCOL_MIDI.md`.
