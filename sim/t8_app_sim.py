# -*- coding: utf-8 -*-
"""
Fake T-8 App_Main — internal virtual pair.

Expected contract (analise/PROTOCOL.md, App_Main side and hypothesis):
 - receives the panel boot presentation: 0xB1 {0,1}, 0xB0 {0,0xD},
   0xB2 {0,0}, UID frame 0xC0 (25B), 0xFF;
 - periodic 0xFF ping (expects 0xFE back);
 - 0xFA/0xFB: sync requests (LEDs / controls);
 - 0xA0/0xE0 {idx,val}: commands LEDs; 0xB0 {sel,state}: pins;
 - receives/logs the panel's original TX: 0x90/0x91 (controls), 0x80 (LED report),
   0x93 (latch), 0xF (heartbeat).

Keyboard commands:
  ping                 -> sends 0xFF
  sync                 -> 0xFA (LEDs) followed by 0xFB (controls)
  led <idx> <val>      -> 0xA0 {idx,val}
  ledb <idx> <val>     -> 0xE0 {idx,val}
  pin <sel> <state>    -> 0xB0 {sel,state}
  q                    -> quit
"""
from __future__ import annotations

import argparse
import queue
import socket
import sys
import threading
import time

from t8_proto import Decoder, pretty, encode_1b, encode_3b
import t8_panel_sim as lnkmod   # reuses the Link class


class AppSim:
    def __init__(self, link: lnkmod.Link, ping_s: float):
        self.link = link
        self.ping_s = ping_s
        self.decoder = Decoder()
        self.txq: "queue.Queue[bytes]" = queue.Queue()
        self.running = True
        self.uid_ok = False
        self.leds = {}

    def log(self, tag, frame, extra: str = ""):
        try:
            print(f"{tag} {pretty(frame):40s} {extra}"
                  if extra else f"{tag} {pretty(frame)}")
        except (ValueError, OSError):
            pass  # stdout closing

    def handle(self, frame: bytes):
        b0 = frame[0]
        if len(frame) == 1:
            if b0 == 0xFF:
                self.log("RX ", frame, "(end of boot presentation)")
            elif b0 == 0xFE:
                self.log("RX ", frame, "(panel pong/heartbeat)")
            else:
                self.log("RX ", frame, "(1B unknown)")
            return
        b1, b2 = frame[1], frame[2]
        if b0 in (0xB1, 0xB0, 0xB2):
            self.log("RX ", frame, "(boot presentation OK)")
        elif b0 == 0xC0 and len(frame) == 25:
            nib = frame[1:]
            uid = bytes((nib[i] << 4) | nib[i + 1] for i in range(0, 24, 2))
            self.uid_ok = True
            self.log("RX ", frame, f"-> UID = {uid.hex()}")
        elif b0 in (0x90, 0x91):
            v = b2 | (0x80 if b0 == 0x91 else 0)   # bit7 comes back from the opcode
            self.log("RX ", frame, f"-> CONTROL slot={b1} value={v:02X}")
        elif b0 == 0x80:
            self.log("RX ", frame, f"-> LED_REPORT id={b1:02X} state={b2}")
        elif b0 == 0x93:
            self.log("RX ", frame, f"-> LATCH v={b2} (middle byte={b1:02X}, expected 0)")
        else:
            self.log("RX ", frame)

    def rx_thread(self):
        while self.running:
            data = self.link.read()
            if data:
                for frame in self.decoder.feed(data):
                    self.handle(frame)

    def tx_thread(self):
        # Verified handshake: the panel does not present itself on cold boot.
        # When opening the port, the App asks for 0xFF (referenced presentation
        # via path bit7) and then it is its heartbeat that proves the link.
        self.log("TX ", encode_1b(0xFF), "(enable the panel)")
        self.link.send(encode_1b(0xFF))
        next_ping = time.time() + self.ping_s
        demo_done = False
        while self.running:
            now = time.time()
            if not demo_done and now > 2.5:
                # demo: ping LEDs and pins
                for idx, val in ((0x01, 0x11), (0x02, 0x22), (0x1F, 0x01)):
                    self.log("TX ", encode_3b(0xA0, idx, val & 0x7F),
                             "(rgb demo)")
                    self.link.send(encode_3b(0xA0, idx, val & 0x7F))
                self.log("TX ", encode_3b(0xB0, 1, 0), "(pin demo)")
                self.link.send(encode_3b(0xB0, 1, 0))
                demo_done = True
            if now >= next_ping:
                self.log("TX ", encode_1b(0xFF), "(ping)")
                self.link.send(encode_1b(0xFF))
                next_ping = now + self.ping_s

    def stdin_thread(self):
        print("\n-- commands: ping | sync | led <idx> <val> ... | q --")
        for line in sys.stdin:
            line = line.strip()
            parts = line.split()
            if not parts:
                continue
            try:
                if parts[0] == "ping":
                    self.link.send(encode_1b(0xFF)); self.log("TX ", b"\xff")
                elif parts[0] == "sync":
                    self.link.send(encode_1b(0xFA)); self.link.send(encode_1b(0xFB))
                    self.log("TX ", b"\xfa"); self.log("TX ", b"\xfb")
                elif parts[0] in ("led", "ledb"):
                    b0 = 0xA0 if parts[0] == "led" else 0xE0
                    f = encode_3b(b0, int(parts[1]) & 0x7F, int(parts[2]) & 0x7F)
                    self.link.send(f); self.log("TX ", f)
                elif parts[0] == "pin":
                    f = encode_3b(0xB0, int(parts[1]), int(parts[2]) & 0x7F)
                    self.link.send(f); self.log("TX ", f)
                elif parts[0] == "q":
                    break
            except (IndexError, ValueError) as e:
                print(f"error: {e}")
        self.running = False

    def run(self):
        self.link.connect()
        print(f"[app ] conectado ({self.link.transport})")
        self.threads = [threading.Thread(target=self.rx_thread, daemon=True),
                        threading.Thread(target=self.tx_thread, daemon=True)]
        for t in self.threads:
            t.start()
        self.stdin_thread()
        self.running = False
        for t in getattr(self, "threads", ()):
            t.join(timeout=0.5)
        self.link.close()


def main():
    ap = argparse.ArgumentParser(description="Fake T-8 App_Main")
    ap.add_argument("--transport", choices=["tcp", "com"], default="tcp")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--tcp-port", type=int, default=8752)
    ap.add_argument("--port", default=None)
    ap.add_argument("--ping-s", type=float, default=5.0)
    ap.add_argument("--connect", action="store_true", default=True)
    args = ap.parse_args()
    app = AppSim(lnkmod.Link(args.transport, args.port, args.host, args.tcp_port),
                 args.ping_s)
    try:
        app.run()
    except (ConnectionRefusedError, ConnectionResetError, OSError) as e:
        print(f"[app ] connection failure: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
