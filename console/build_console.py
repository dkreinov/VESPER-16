#!/usr/bin/env python3
"""Build console/console.html from console.src.html and assets/workbench.webp (stdlib only).

    python console/build_console.py
    python console/build_console.py --deck DIR

The background picture is embedded as a data URI. The source image is never touched.

--deck DIR builds one offline file, DIR/VESPER-Console.html, that plays recorded demos
(frames plus the button presses of each frame) and does not need the emulator. It reads
DIR/demos.json:

    {"carts": [{"label": "T3 SQUASH", "rgb": "t3.rgb", "buttons": "t3.buttons.txt"}, ...]}

Each .rgb file holds 64*48*3 bytes per frame (the stdout of `vesper-play play`).
Each buttons file has one line of button names per frame step: line k = held in frame k+1.
Only DIR is written. Nothing from DIR is copied into this repository.
"""
import argparse
import base64
import json
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
MARK = "__WORKBENCH_DATA_URI__"
DECK_MARK = "__DECK_DATA__"
LIMIT = 400 * 1024
FRAME_BYTES = 64 * 48 * 3
BUTTONS = ("UP", "DOWN", "LEFT", "RIGHT", "A", "B", "SELECT", "START")


def page(deck_json):
    img = None
    for name, mime in (("workbench.webp", "image/webp"), ("workbench.jpg", "image/jpeg")):
        if (HERE / "assets" / name).is_file():
            img = (HERE / "assets" / name).read_bytes()
            kind = mime
            break
    if img is None:
        sys.exit("missing console/assets/workbench.webp (or .jpg)")
    if len(img) > LIMIT:
        sys.exit(f"background image is {len(img)} bytes; the limit is {LIMIT}")
    src = (HERE / "console.src.html").read_text(encoding="utf-8")
    for m in (MARK, DECK_MARK):
        if m not in src:
            sys.exit(f"{m} not found in console.src.html")
    uri = f"data:{kind};base64," + base64.b64encode(img).decode("ascii")
    return src.replace(MARK, uri).replace(DECK_MARK, deck_json)


def pack_cart(folder, cart):
    rgb = (folder / cart["rgb"]).read_bytes()
    if not rgb or len(rgb) % FRAME_BYTES:
        sys.exit(f"{cart['rgb']}: size is not a whole number of frames")
    n = len(rgb) // FRAME_BYTES
    lines = (folder / cart["buttons"]).read_text().splitlines()
    masks = bytearray(n)                      # frame f shows the result of line f-1
    for f in range(1, n):
        names = lines[f - 1].split() if f - 1 < len(lines) else []
        for b in names:
            if b not in BUTTONS:
                sys.exit(f"{cart['buttons']}: unknown button {b}")
            masks[f] |= 1 << BUTTONS.index(b)
    delta = bytearray(rgb)                    # frame 0 as it is, then XOR with the frame before
    for f in range(n - 1, 0, -1):
        a, b = f * FRAME_BYTES, (f - 1) * FRAME_BYTES
        delta[a:a + FRAME_BYTES] = bytes(x ^ y for x, y in zip(rgb[a:a + FRAME_BYTES], rgb[b:b + FRAME_BYTES]))
    co = zlib.compressobj(9, zlib.DEFLATED, -15)
    blob = co.compress(bytes(delta) + bytes(masks)) + co.flush()
    return {"label": cart["label"], "frames": n, "data": base64.b64encode(blob).decode("ascii")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--deck", metavar="DIR", help="build DIR/VESPER-Console.html from DIR/demos.json")
    args = ap.parse_args()
    if args.deck:
        folder = Path(args.deck)
        spec = json.loads((folder / "demos.json").read_text(encoding="utf-8"))
        deck = {"carts": [pack_cart(folder, c) for c in spec["carts"]]}
        text = page(json.dumps(deck, separators=(",", ":")))
        out = folder / "VESPER-Console.html"
        out.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {out} ({out.stat().st_size} bytes)")
        return
    out = HERE / "console.html"
    out.write_text(page("null"), encoding="utf-8", newline="\n")
    print(f"wrote console/console.html ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
