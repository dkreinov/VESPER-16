"""Take console screenshots with Playwright (Python). Needs a running play.py with the fake emulator.

    python console/tests/shoot.py http://127.0.0.1:8765/ console/checks
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

url, outdir = sys.argv[1], Path(sys.argv[2])
errurl = sys.argv[3] if len(sys.argv) > 3 else None
outdir.mkdir(parents=True, exist_ok=True)
with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 720})
    msgs = []
    pg.on("console", lambda m: msgs.append(m.text))
    pg.on("pageerror", lambda e: msgs.append("PAGEERROR " + str(e)))
    pg.goto(url)
    time.sleep(0.5)
    pg.keyboard.press("r")
    pg.evaluate("__vesper.splashEnd = 1e12")   # hold the boot splash for the picture
    time.sleep(0.4)
    pg.screenshot(path=str(outdir / "1-boot.png"))
    pg.evaluate("__vesper.splashEnd = 0")
    time.sleep(0.5)
    pg.keyboard.down("ArrowRight"); pg.keyboard.down("ArrowDown"); pg.keyboard.down("z"); pg.keyboard.down("Shift")
    time.sleep(0.5)
    pg.screenshot(path=str(outdir / "2-live-held.png"))
    pg.keyboard.up("ArrowRight"); pg.keyboard.up("ArrowDown"); pg.keyboard.up("z"); pg.keyboard.up("Shift")
    pg.keyboard.press("2")
    time.sleep(0.35)
    pg.screenshot(path=str(outdir / "3-cart-swap.png"))
    time.sleep(2.2)
    pg.screenshot(path=str(outdir / "3b-cart-t6.png"))
    pg.keyboard.press("m")
    pg.keyboard.press("1")
    time.sleep(1.2)
    pg.screenshot(path=str(outdir / "5-motion-off.png"))
    pg.keyboard.press("m")
    pg.keyboard.press("g")
    time.sleep(0.2)
    pg.screenshot(path=str(outdir / "6-lcd-off.png"))
    pg.keyboard.press("g")
    if errurl:
        pg.goto(errurl)
        time.sleep(2.2)
        pg.screenshot(path=str(outdir / "4-error.png"))
    # replay: opened as a file, frames from a PNG folder made by the fake emulator
    import glob
    import subprocess
    import tempfile
    d = tempfile.mkdtemp()
    open(d + "/T3.vsa", "w").write("x")
    subprocess.run([sys.executable, str(Path(__file__).with_name("fake_vesper.py")), "run", d + "/T3.vsa",
                    "--out", d + "/out", "--frames", "90"], check=True)
    pg.goto((Path(__file__).resolve().parent.parent / "console.html").as_uri())
    time.sleep(0.5)
    pg.screenshot(path=str(outdir / "7-replay-empty.png"))
    pg.set_input_files("#fileInput", sorted(glob.glob(d + "/out/frame_*.png")))
    time.sleep(2.0)
    pg.evaluate("__vesper.splashEnd = 0")
    pg.keyboard.press("Space")
    time.sleep(0.3)
    pg.screenshot(path=str(outdir / "8-replay.png"))
    print("\n".join(msgs) or "no console messages")
    b.close()
