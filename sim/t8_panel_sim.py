# -*- coding: utf-8 -*-
"""
T-8 PANEL simulator (STM32 side) — internal virtual pair.

Behaves like the decompiled firmware (analise/PROTOCOL.md):
 - at boot: sends presentation {0xB1,0,1}{0xB0,0,0xD}{0xB2,0,0}[UID 25B]{0xFF}
 - periodic 0xFE heartbeat (bit7 event of the tick)
 - RX 0xFF -> re-presents (clears queues and re-sends the presentation)
 - RX 0xFA -> re-publishes the LED table as TX {0x80 id state}
 - RX 0xFB -> re-reports the control snapshot as TX 0x90/0x91
 - RX 0xA0/0xE0 {idx,val} -> writes LED state and logs
 - RX 0xB0 {sel,state}    -> logs (physical pins on the real device)

Keyboard commands (once connected):
  p <slot> 0|1      -> button (press/release)
  k <slot> <0..255> -> knob/control value
  l                 -> dump the LEDs
  q                 -> quit

Transports:
  --transport tcp                     (default; pure virtual pair)
  --transport com --port COMx         (real hardware via pyserial; optional)
"""
from __future__ import annotations

import argparse
import queue
import socket
import sys
import threading
import time

from t8_proto import (Decoder, RX_OPS, TX_OPS, encode_1b, encode_3b, encode_ctl,
                      pretty, uid_frame)

N_LEDS = 0x20        # LED table (cache 0x200013ac)
N_CTLS = 0x20        # control channels (id 0..0x1e)
LATCH_MAX = 0x3F     # saturation of the 0x93 "latch" (value + 0x40 clamp 0..0x7f)


class Link:
    """Common interface: tcp (virtual pair) or com (pyserial, optional)."""

    def __init__(self, transport: str, port: str, host: str, tcp_port: int,
                 server: bool = False):
        self.transport = transport
        self.port = port
        self.host = host
        self.tcp_port = tcp_port
        self.server = server
        self.sock = None
        self.ser = None

    def connect(self):
        if self.transport == "tcp":
            if self.server:
                srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                srv.bind((self.host, self.tcp_port))
                srv.listen(1)
                print(f"[tcp ] waiting for peer at {self.host}:{self.tcp_port}…")
                conn, addr = srv.accept()
                self.sock = conn
            else:
                self.sock = socket.create_connection((self.host, self.tcp_port),
                                                     timeout=10)
        else:
            import serial  # pyserial; optional
            self.ser = serial.Serial(self.port, 115200, timeout=0.05)

    def send(self, data: bytes):
        if self.transport == "tcp":
            self.sock.sendall(data)
        else:
            self.ser.write(data)

    def read(self, n: int = 256) -> bytes:
        if self.transport == "tcp":
            self.sock.settimeout(0.05)
            try:
                return self.sock.recv(n)
            except (socket.timeout, ConnectionResetError):
                return b""
        else:
            return self.ser.read(n)

    def close(self):
        try:
            if self.sock:
                self.sock.close()
            if self.ser:
                self.ser.close()
        except OSError:
            pass


class PanelSim:
    def __init__(self, link: Link, tick_ms: float):
        self.link = link
        self.tick_ms = tick_ms
        self.decoder = Decoder()
        self.txq: "queue.Queue[bytes]" = queue.Queue()
        self.leds = {}      # idx -> (val, phase, submode)
        self.ctl = {}       # id -> 8-bit value (snapshot for 0xFB)
        self.latch = 0      # 0x93 "counter" (in the real hw: 0x2000109c)
        self.latch_sent = True
        self.running = True
        self.lock = threading.Lock()

    # --- TX ---------------------------------------------------------------
    def enqueue(self, frame: bytes):
        self.txq.put(frame)

    def presentation_frames(self):
        """Boot sequence (order of FUN_08004010). Everything goes through the TX
        queue — the firmware never sends from two threads (FUN_08003ec8/double bank)."""
        return [
            encode_3b(0xB1, 0x00, 0x01),
            encode_3b(0xB0, 0x00, 0x0D),
            encode_3b(0xB2, 0x00, 0x00),
            uid_frame(),
            encode_1b(0xFF),
        ]

    def do_heartbeat(self):
        self.enqueue(encode_1b(0xFE))

    def drain_queues(self):
        """Mirrors the loop: bit5 -> 0x90/0x91; bit6 -> 0x80; bit4 -> 0x93."""
        # (the control queue and LED ring are drained by the keyboard/latch below)
        if not self.latch_sent:
            v = self.latch + 0x40
            v = 0 if v < 0 else 0x7F if v > 0x7F else v
            if v != 0:
                self.log("TX ", encode_3b(0x93, 0x00, v))
            self.latch_sent = True

    # --- RX ----------------------------------------------------------------
    def handle(self, frame: bytes):
        b0 = frame[0]
        if len(frame) == 1:
            if b0 == 0xFF:
                # Real code: posts bit7 -> cmd_tree boot/status path
                # (sends 0xB1/0xB0/0xB2/UID/0xFF again; it is NOT a ping->0xFE).
                self.log("RX ", frame, "-> re-presentation (clears queues)")
                self.txq.queue.clear()          # empties ring/queue (FUN_08003a64/3c44)
                for f in self.presentation_frames():
                    self.txq.put(f)
            elif b0 == 0xFA:
                self.log("RX ", frame, "-> re-publish LEDs")
                with self.lock:
                    items = sorted(self.leds.items())
                for idx, (val, _phase, _sm) in items:
                    self.enqueue(encode_3b(0x80, idx & 0x7F, val & 0x7F))
            elif b0 == 0xFB:
                self.log("RX ", frame, "-> re-report controls")
                with self.lock:
                    items = sorted(self.ctl.items())
                for cid, v in items:
                    self.enqueue(encode_ctl(cid, v))
            else:
                self.log("RX ", frame, "(1B unknown)")
            return
        _, b1, b2 = frame
        if b0 in (0xA0, 0xE0):
            with self.lock:
                self.leds[b1] = (b2, b2 & 0xF, b2 >> 4)
            self.log("RX ", frame, f"-> LED idx={b1:02X} val={b2:02X} "
                                   f"(phase={b2 & 0xF} sub={b2 >> 4})")
        elif b0 == 0xB0:
            pin = {0: 1, 1: 2, 2: 8}.get(b1)
            level = "high" if b2 == 0 else "low"
            self.log("RX ", frame, f"-> PIN sel={b1} (pin {pin}) level={level}")
        else:
            self.log("RX ", frame, "(3B unknown)")

    # --- infra --------------------------------------------------------------
    def log(self, tag, frame, extra: str = ""):
        try:
            print(f"{tag} {pretty(frame):40s} {extra}" if extra else f"{tag} {pretty(frame)}")
        except (ValueError, OSError):
            pass  # stdout closing

    def rx_thread(self):
        while self.running:
            data = self.link.read()
            if data:
                for frame in self.decoder.feed(data):
                    self.handle(frame)

    def shutdown(self):
        self.running = False
        for t in getattr(self, "threads", ()):
            t.join(timeout=0.5)
        self.link.close()
        try:
            sys.stdout.flush()
        except (ValueError, OSError):
            pass

    def tx_thread(self):
        # firmware cadence (FUN_080022e4): timer 0x40012c00 (TIM1) ticks;
        # dial poll every 200 ticks, heartbeat every 2000 ticks.
        tick = self.tick_ms / 1000.0
        now = time.time()
        next_dial = now + 200 * tick
        next_hb = now + 2000 * tick
        while self.running:
            now = time.time()
            if now >= next_dial:
                if not self.latch_sent:          # gate = FUN_0800343c != 0
                    self.drain_queues()
                next_dial = now + 200 * tick
            if now >= next_hb:
                self.do_heartbeat()
                next_hb = now + 2000 * tick
            try:
                f = self.txq.get(timeout=0.02)
                self.log("TX ", f)
                self.link.send(f)
            except queue.Empty:
                pass

    def stdin_thread(self):
        print("\n-- commands: p <slot> 0|1 | k <slot> <0..255> | l | q --")
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                if line.startswith("p "):
                    _, s, v = line.split()
                    self.enqueue(encode_ctl(int(s), int(v)))          # button 0/1
                elif line.startswith("k "):
                    _, s, v = line.split()
                    self.enqueue(encode_ctl(int(s), int(v)))          # knob
                    with self.lock:
                        self.ctl[int(s)] = int(v)
                elif line == "l":
                    with self.lock:
                        print("LEDs:", {f"0x{i:02X}": (v, p, s)
                                        for i, (v, p, s) in sorted(self.leds.items())})
                elif line.startswith("d "):
                    # dial/encoder: delta in detents (in the real hw: quadrature with
                    # a +1/-1 table at 0x08004dd0; tick posts event 0x08
                    # every 200 ticks -> TX 0x93)
                    _, v = line.split()
                    self.latch += int(v)
                    self.latch_sent = False
                    print(f"[dial ] latch={self.latch:+d}")
                elif line == "q":
                    self.running = False
                    break
            except (ValueError, KeyError) as e:
                print(f"error: {e}")

    def run(self):
        self.link.connect()
        print(f"[panel] connected ({self.link.transport})")
        # Verify (audit 22/Oct): NO preamble post bit7 in init (FUN_08003a4c is
        # only referenced in schematic + 6 posters; none posts 0x80). The panel
        # only presents when the App sends 0xFF; the first TX is the 0xFE
        # heartbeat (2000 ticks).
        self.threads = [threading.Thread(target=self.rx_thread, daemon=True),
                        threading.Thread(target=self.tx_thread, daemon=True)]
        for t in self.threads:
            t.start()
        self.stdin_thread()
        self.shutdown()


def main():
    ap = argparse.ArgumentParser(description="T-8 panel simulator")
    ap.add_argument("--transport", choices=["tcp", "com"], default="tcp")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--tcp-port", type=int, default=8752)
    ap.add_argument("--port", default=None, help="COM port (transport=com)")
    ap.add_argument("--tick-ms", type=float, default=1.0,
                    help="TIM1 tick period in ms (starting point; 200 ticks = dial poll, 2000 = heartbeat)")
    args = ap.parse_args()
    panel = PanelSim(Link(args.transport, args.port, args.host, args.tcp_port,
                          server=(args.transport == "tcp")),
                     args.tick_ms)
    try:
        panel.run()
    except (ConnectionRefusedError, ConnectionResetError, OSError) as e:
        print(f"[panel] connection failure: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
