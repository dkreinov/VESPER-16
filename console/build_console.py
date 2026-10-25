#!/usr/bin/env python3
"""Build console/console.html from console.src.html and assets/workbench.webp (stdlib only).

    python console/build_console.py

The background picture is embedded as a data URI. The source image is never touched.
"""
import base64
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MARK = "__WORKBENCH_DATA_URI__"
LIMIT = 400 * 1024


def main():
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
    if MARK not in src:
        sys.exit(f"{MARK} not found in console.src.html")
    uri = f"data:{kind};base64," + base64.b64encode(img).decode("ascii")
    (HERE / "console.html").write_text(src.replace(MARK, uri), encoding="utf-8", newline="\n")
    print(f"wrote console/console.html ({len(src) + len(uri)} bytes)")


if __name__ == "__main__":
    main()
