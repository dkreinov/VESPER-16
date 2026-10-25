#!/usr/bin/env python3
"""Fake emulator for console tests. It knows only the public protocol.

  fake_vesper.py play PROG [--frames N] [--seed N]
      reads one line of button names per frame, writes 64*48*3 RGB bytes per frame.
      A dot starts in the middle and the arrows move it. A, B, START, SELECT change its colour.
      The first row is a bar that grows with the frame number.

  fake_vesper.py run PROG --out DIR [--frames N]
      writes frame_0000.png ... with the dot moving in a circle (for replay tests).

The text inside PROG steers the fake:
  FAKE_ERROR_AT=N    print an error on stderr and exit with code 3 after N frames
  FAKE_BAD           print an error before frame 0 and exit with code 2
  FAKE_END_AT=N      exit with code 0 after N frames
"""
import math
import os
import re
import struct
import sys
import zlib

W, H = 64, 48
COLORS = {"A": (255, 140, 26), "B": (232, 51, 58), "START": (60, 210, 90), "SELECT": (63, 169, 245)}


def read_setting(text, name):
    m = re.search(name + r"=(\d+)", text)
    return int(m.group(1)) if m else None


def draw(x, y, color, n, tint):
    buf = bytearray(W * H * 3)
    for i in range(W * H):  # dark background with a faint checker
        v = 18 if ((i % W) // 4 + (i // W) // 4) % 2 else 26
        buf[i * 3:i * 3 + 3] = bytes((v, v + 2, v + 12))
    for i in range(W):                         # border
        for yy in (0, H - 1):
            buf[(yy * W + i) * 3:(yy * W + i) * 3 + 3] = bytes(tint)
    for j in range(H):
        for xx in (0, W - 1):
            buf[(j * W + xx) * 3:(j * W + xx) * 3 + 3] = bytes(tint)
    for i in range(n % (W - 2)):               # growing bar under the border
        buf[(2 * W + 1 + i) * 3:(2 * W + 1 + i) * 3 + 3] = bytes((168, 176, 184))
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            px, py = x + dx, y + dy
            if 0 <= px < W and 0 <= py < H:
                buf[(py * W + px) * 3:(py * W + px) * 3 + 3] = bytes(color)
    return bytes(buf)


def png(rgb):
    raw = b"".join(b"\x00" + rgb[r * W * 3:(r + 1) * W * 3] for r in range(H))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def play(prog, frames):
    text = open(prog, "r", errors="replace").read()
    tint = (255, 217, 61) if "T6" in os.path.basename(prog).upper() else (63, 169, 245)
    if "FAKE_BAD" in text:
        sys.stderr.write("error: line 1: fake assembler trouble\n")
        sys.stderr.flush()
        return 2
    error_at, end_at = read_setting(text, "FAKE_ERROR_AT"), read_setting(text, "FAKE_END_AT")
    out, inp = sys.stdout.buffer, sys.stdin.buffer
    x, y, n = W // 2, H // 2, 0
    color = (255, 255, 255)
    while True:
        out.write(draw(x, y, color, n, tint))
        out.flush()
        n += 1
        if frames is not None and n > frames:
            return 0
        if error_at is not None and n > error_at:
            sys.stderr.write("runtime error: fake failure at frame %d\n" % n)
            sys.stderr.flush()
            return 3
        if end_at is not None and n > end_at:
            return 0
        line = inp.readline()
        if not line:
            return 0
        held = set(line.decode("ascii", "replace").split())
        x += ("RIGHT" in held) - ("LEFT" in held)
        y += ("DOWN" in held) - ("UP" in held)
        x, y = max(2, min(W - 3, x)), max(2, min(H - 3, y))
        color = (255, 255, 255)
        for b, c in COLORS.items():
            if b in held:
                color = c


def run(prog, out_dir, frames):
    os.makedirs(out_dir, exist_ok=True)
    tint = (255, 217, 61) if "T6" in os.path.basename(prog).upper() else (63, 169, 245)
    for n in range(frames):
        a = n / frames * 2 * math.pi
        x, y = int(W / 2 + 20 * math.cos(a)), int(H / 2 + 14 * math.sin(a))
        with open(os.path.join(out_dir, "frame_%04d.png" % n), "wb") as f:
            f.write(png(draw(x, y, (255, 140, 26), n, tint)))
    return 0


def main(argv):
    if len(argv) < 2 or argv[0] not in ("play", "run"):
        sys.stderr.write("usage: fake_vesper.py play|run PROG [--frames N] [--out DIR]\n")
        return 64
    mode, prog, rest = argv[0], argv[1], argv[2:]
    frames, out_dir = None, None
    for i, a in enumerate(rest):
        if a == "--frames":
            frames = int(rest[i + 1])
        elif a == "--out":
            out_dir = rest[i + 1]
    if mode == "play":
        return play(prog, frames)
    return run(prog, out_dir or "out", frames or 120)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
