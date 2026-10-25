"""Screenshots of the console with the real emulator. Starts play.py itself.

    python console/tests/shoot_real.py PROG1.vsa PROG2.vsa BROKEN.vsa OUTDIR

Play-mode screenshots show the output of finished programs: write OUTDIR outside this repository.
"""
import re
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

t3, t6, bad, outdir = sys.argv[1:5]
outdir = Path(outdir)
play = Path(__file__).resolve().parent.parent / "play.py"


def start(*progs):
    p = subprocess.Popen([sys.executable, "-u", str(play), *progs, "--no-browser"], stdout=subprocess.PIPE, text=True)
    return p, re.search(r"http://\S+/", p.stdout.readline()).group(0)


with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 720})
    msgs = []
    pg.on("console", lambda m: msgs.append(m.text))
    pg.on("pageerror", lambda e: msgs.append("PAGEERROR " + str(e)))
    p, url = start(t3, t6)
    pg.goto(url)
    time.sleep(2.5)
    pg.keyboard.down("ArrowUp")
    time.sleep(1.3)
    pg.screenshot(path=str(outdir / "real-t3-live.png"))
    n1 = pg.evaluate("__vesper.frameNo"); time.sleep(1.0); n2 = pg.evaluate("__vesper.frameNo")
    print("frames per second:", n2 - n1)
    pg.keyboard.up("ArrowUp")
    pg.keyboard.press("2")
    time.sleep(3.0)
    pg.keyboard.down("ArrowDown")
    time.sleep(0.8)
    pg.screenshot(path=str(outdir / "real-t6-live.png"))
    pg.keyboard.up("ArrowDown")
    p.terminate()
    p, url = start(bad)
    pg.goto(url)
    time.sleep(2.5)
    pg.screenshot(path=str(outdir / "real-error.png"))
    p.terminate()
    print("\n".join(msgs) or "no console messages")
    b.close()
