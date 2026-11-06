# -*- coding: utf-8 -*-
"""
Smoke test of the T-8 virtual pair: brings up panel + fake app, injects events
from both sides and prints both transcripts. Exit code 0 = script OK.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time

HERE = __file__.rsplit("\\", 1)[0]
PY = sys.executable


def spawn(name, args):
    p = subprocess.Popen([PY, name, *args], cwd=HERE,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True,
                         encoding="utf-8", errors="replace", bufsize=1)
    lines = []

    def reader():
        for line in p.stdout:
            lines.append(line.rstrip())

    threading.Thread(target=reader, daemon=True).start()
    return p, lines


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("=== 1. bring up panel (tcp server) ===")
    panel, pout = spawn("t8_panel_sim.py", ["--tcp-port", "8752"])
    time.sleep(1.0)

    print("=== 2. bring up app (client) ===")
    app, aout = spawn("t8_app_sim.py", ["--tcp-port", "8752"])
    time.sleep(2.5)   # boot presentation + LED/pin demo

    print("=== 3. inject: knob/dial on the panel; ping/sync on the app ===")
    panel.stdin.write("k 3 200\n"); panel.stdin.flush()
    panel.stdin.write("p 5 1\n");  panel.stdin.flush()
    panel.stdin.write("d 5\n");    panel.stdin.flush()   # dial: latch += 5 -> 0x93
    app.stdin.write("ping\n");     app.stdin.flush()
    time.sleep(1.5)
    app.stdin.write("sync\n");     app.stdin.flush()   # 0xFA + 0xFB
    app.stdin.write("led 7 42\n"); app.stdin.flush()   # 0xA0 {07,2A}
    app.stdin.write("ledb 8 5\n"); app.stdin.flush()   # 0xE0 {08,05}
    app.stdin.write("pin 0 1\n");  app.stdin.flush()   # 0xB0 {00,01}
    time.sleep(3.5)   # let 1-2 heartbeats pass (2000 ms each)

    panel.stdin.write("q\n"); panel.stdin.flush()
    app.stdin.write("q\n");   app.stdin.flush()
    try:
        panel.wait(timeout=3)
    except subprocess.TimeoutExpired:
        panel.kill()
    try:
        app.wait(timeout=3)
    except subprocess.TimeoutExpired:
        app.kill()

    print("\n================ PANEL TRANSCRIPT ================")
    for l in pout:
        print(" ", l)
    print("\n================ APP TRANSCRIPT   ================")
    for l in aout:
        print(" ", l)

    # --- minimal script checks ---
    ptxt = "\n".join(pout); atxt = "\n".join(aout)
    rx_ff = any("RX" in l and "[FF]" in l for l in pout)
    rx_fe = any("RX" in l and "[FE]" in l for l in aout)
    checks = [
        ("panel re-presents on receiving 0xFF (code: bit7->fun_08004010)",
         rx_ff and "re-present" in ptxt
         and ptxt.count("[B1 00 01]") >= 2),
        ("panel sent the presentation (0xB1/0xB0/0xB2/UID/0xFF)",
         all(s in ptxt for s in ("[B1 00 01]", "[B0 00 0D]", "[B2 00 00]",
                                  "[C0", "[FF]"))),
        ("panel sent control 0x91 (knob 200 >= 0x80)",
         "[91 03 48]" in ptxt),
        ("panel sent control 0x90 (button 1)",
         "[90 05 01]" in ptxt),
        ("app decoded the full UID (25B as a single frame)",
         "-> UID = 000302070654401c46383644" in atxt),
        ("panel served 0xFA re-publishing LEDs (0x80)",
         "[FA]" in ptxt and "[80 01 11]" in ptxt),
        ("panel served 0xFB re-reporting knob slot 3 (0x91 03 48)",
         "[FB]" in ptxt and ptxt.count("[91 03 48]") >= 2),
        ("panel logged pin 0xB0 {00,01}",
         "[B0 00 01]" in ptxt and "sel=0" in ptxt),
        ("heartbeat 0xFE appears on the app (timer, not a ping response)", rx_fe),
        ("dial position 0x93 appears (~200 ticks cadence)",
         "[93 00" in ptxt),
    ]
    failed = 0
    print("\n================ CHECKS ============================")
    for label, ok in checks:
        print(("  [OK]  " if ok else "  [FAIL]") + label)
        failed += 0 if ok else 1
    print("\nresult:", "PASS" if failed == 0 else f"{failed} failure(s)")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
