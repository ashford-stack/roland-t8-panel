#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
t8_midi_log.py — Logs EVERYTHING in and out over the Roland T-8 USB-MIDI.

Dependency (once):  py -m pip install pygame
Run:                py t8_midi_log.py

Why pygame.midi: it uses the PortMidi bindings that ship as a pre-compiled WHEEL
for Windows/Python 3.13 (mido's python-rtmidi requires a C++ compiler and breaks
on the user's machine). Original name kept for continuity.

What it does:
  * Enumerates Windows MIDI devices, opens the ones that look like the T-8
    (auto-match "t-8"/"t8"/"aira"/"roland"; otherwise asks).
  * Logs each message with a relative timestamp, device, human text and bytes.
  * Typed commands to send something to the T-8:
        n <note> [vel] [ch]   -> Note On + Off (e.g. n 36 120 9)
        c <cc> <value> [ch]   -> Control Change  (e.g. c 20 64 1)
        st / sp / rel         -> transport 0xFA / 0xFC / 0xFB
        q                     -> quit
  * Records everything in logs/midi_log_YYYYmmdd_HHMMSS.log (UTF-8) and shows it on screen.

An "empty" result (no port / nothing flowing) is ALSO a valid result:
documented as "firmware X does not expose MIDI" in ANALYSIS.md.
"""
import os
import re
import sys
import time
import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
AUTO_MATCH = re.compile(r"t-?8|aira|roland", re.IGNORECASE)

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def note_name(n):
    return "%s%d" % (NOTE_NAMES[n % 12], n // 12 - 1)


def hexbytes(data):
    return " ".join("%02X" % (b & 0xFF) for b in data)


def fmt_event(e3):
    """Converts PortMidi (status, d1, d2, d3) into a human string."""
    st, d1, d2, _ = e3[0], e3[1], e3[2], e3[3]
    typ = st & 0xF0
    ch = st & 0x0F
    if typ == 0x90 and d2 > 0:
        return "note_on  ch=%-2d %3d=%-5s vel=%-3d" % (ch, d1 & 0x7F, note_name(d1 & 0x7F), d2)
    if typ == 0x80 or (typ == 0x90 and d2 == 0):
        return "note_off ch=%-2d %3d=%-5s vel=%-3d" % (ch, d1 & 0x7F, note_name(d1 & 0x7F), d2)
    if typ == 0xA0:
        return "poly_prs ch=%-2d note=%-3d pressure=%d" % (ch, d1, d2)
    if typ == 0xB0:
        return "cc       ch=%-2d cc=%-3d val=%d" % (ch, d1, d2)
    if typ == 0xC0:
        return "pc       ch=%-2d program=%d" % (ch, d1)
    if typ == 0xD0:
        return "chan_prs ch=%-2d pressure=%d" % (ch, d1)
    if typ == 0xE0:
        return "pitch    ch=%-2d lsb=%-3d msb=%d" % (ch, d1, d2)
    if typ == 0xF0:
        real = st & 0x0F
        SYS = {0x8: "clock", 0xA: "start", 0xB: "continue", 0xC: "stop",
               0xE: "active_sensing", 0xF: "sysex_chunk", 0x1: "mtc", 0x2: "songpos",
               0x3: "song_select", 0x6: "tune_request", 0x0: "sysex_start"}
        return SYS.get(real, "sys ch=0x%X d1=%d d2=%d" % (real, d1, d2))
    return "unknown status=0x%02X d1=%d d2=%d" % (st, d1, d2)


def mprint(*out_items):
    logf = out_items[-1] if not isinstance(out_items[-1], str) else None
    items = out_items[:-1] if logf is not None else out_items
    out_line = " ".join(str(x) for x in items)
    try:
        print(out_line)
    except UnicodeEncodeError:
        print(out_line.encode("ascii", "replace").decode())
    if logf is not None:
        logf.write(out_line + "\n")
        logf.flush()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    try:
        import pygame.midi as midi
    except ImportError:
        print("pygame not installed. Run:  py -m pip install pygame")
        sys.exit(1)

    midi.init()
    try:
        n = midi.get_count()
    except Exception as e:
        print("PortMidi failure: %r" % (e,))
        sys.exit(1)

    os.makedirs(LOG_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(LOG_DIR, "midi_log_%s.log" % stamp)
    logf = open(log_path, "w", encoding="utf-8")

    devices = []
    for i in range(n):
        info = midi.get_device_info(i)
        if info is None:
            continue
        interf, name, is_input, is_output, opened = info
        if isinstance(name, bytes):
            name = name.decode("utf-8", "replace")
        if isinstance(interf, bytes):
            interf = interf.decode("utf-8", "replace")
        devices.append({
            "id": i, "name": name, "interf": interf,
            "in": bool(is_input), "out": bool(is_output),
            "open": opened if opened else 0,
        })

    mprint("=== T-8 MIDI logger (pygame.midi/PortMidi) ===", logf)
    for d in devices:
        mprint("  dev %d: %-40s in=%d out=%d open=%s" % (d["id"], d["name"], d["in"], d["out"], bool(d["open"])), logf)

    ins_match = [d for d in devices if d["in"] and not d["open"] and AUTO_MATCH.search(d["name"])]
    outs_match = [d for d in devices if d["out"] and not d["open"] and AUTO_MATCH.search(d["name"])]
    if not ins_match:
        ins_match = [d for d in devices if d["in"] and not d["open"]]
    if not outs_match:
        outs_match = [d for d in devices if d["out"] and not d["open"]]

    mprint("IN  ports:", [d["name"] for d in ins_match], logf)
    mprint("OUT ports:", [d["name"] for d in outs_match], logf)

    opened_in = []
    for d in ins_match:
        try:
            opened_in.append((d["name"], midi.Input(d["id"])))
            mprint("[IN opened ] dev%d %s" % (d["id"], d["name"]), logf)
        except Exception as e:
            mprint("[IN error  ] dev%d %s -> %r" % (d["id"], d["name"], e), logf)
    opened_out = None
    outs_pref = [d for d in outs_match if "mapper" not in d["name"].lower()]
    for d in (outs_pref or outs_match):
        try:
            opened_out = midi.Output(d["id"])
            mprint("[OUT opened] dev%d %s" % (d["id"], d["name"]), logf)
            break
        except Exception as e:
            mprint("[OUT error ] dev%d %s -> %r" % (d["id"], d["name"], e), logf)

    if not opened_in and opened_out is None:
        mprint("No usable MIDI port opened - nothing to monitor. Exiting.", logf)
        mprint("Log saved to: %s" % log_path, logf)
        return

    t0 = time.perf_counter()
    mprint("Commands: n <note> [vel] [ch] | c <cc> <val> [ch] | st/sp/rel | q", logf)
    mprint("--- message log ---", logf)

    running = True
    while running:
        # --- receiving (poll all opened devices) ---
        for name, inp in list(opened_in):
            try:
                while inp.poll():
                    for ev in inp.read(100):
                        # ev = [event_data, timestamp]; event_data=[status,d1,d2,d3]
                        e3 = ev[0]
                        dt = time.perf_counter() - t0
                        mprint("%8.3f  [IN ] %-32s  %-40s  [%s]"
                               % (dt, name[:32], fmt_event(e3), hexbytes(e3)), logf)
            except Exception as e:
                mprint("[IN closed ] %s -> %r" % (name, e), logf)
                try:
                    inp.close()
                except Exception:
                    pass
                opened_in.remove((name, inp))

        # --- keyboard commands ---
        try:
            line = input().strip()
        except (KeyboardInterrupt, EOFError):
            running = False
            break
        if not line:
            continue

        def out_short(status, d1, d2, tag):
            dt = time.perf_counter() - t0
            if opened_out is not None:
                try:
                    opened_out.write_short(status, d1, d2)
                    mprint("%8.3f  [OUT] %-32s  status=0x%02X d1=%-3d d2=%-3d"
                           % (dt, tag[:32], status & 0xFF, d1, d2), logf)
                except Exception as e:
                    mprint("[OUT error] %r" % (e,), logf)
            else:
                mprint("[no OUT port opened] '%s'" % tag, logf)

        try:
            parts = line.split()
            cmd = parts[0].lower()
            if cmd in ("q", "quit", "exit"):
                running = False
            elif cmd == "n":
                note = int(parts[1]) & 0x7F
                vel = int(parts[2]) if len(parts) > 2 else 120
                ch = int(parts[3]) if len(parts) > 3 else 9
                ch &= 0x0F
                out_short(0x90 | ch, note, vel, "cmd n on")
                time.sleep(0.15)
                out_short(0x80 | ch, note, 0, "cmd n off")
            elif cmd == "c":
                cc = int(parts[1]) & 0x7F
                val = int(parts[2]) if len(parts) > 2 else 64
                ch = int(parts[3]) if len(parts) > 3 else 1
                out_short(0xB0 | (ch & 0x0F), cc, val & 0x7F, "cmd c")
            elif cmd == "st":
                out_short(0xFA, 0, 0, "cmd st")
            elif cmd == "sp":
                out_short(0xFC, 0, 0, "cmd sp")
            elif cmd == "rel":
                out_short(0xFB, 0, 0, "cmd rel")
            else:
                mprint("Unknown command: %r" % line, logf)
        except (IndexError, ValueError) as e:
            mprint("Error in command %r : %r" % (line, e), logf)

    for name, inp in opened_in:
        try:
            inp.close()
        except Exception:
            pass
    if opened_out is not None:
        try:
            opened_out.close()
        except Exception:
            pass
    midi.quit()
    mprint("--- end (Ctrl+C / q) ---", logf)
    mprint("Log saved to: %s" % log_path, logf)
    logf.close()
    sys.stdout.flush()


if __name__ == "__main__":
    main()
