"""Make console/assets/workbench.webp from the workbench picture, with the handheld painted out.

    python console/assets/make_workbench.py SOURCE.png
The source file is only read. Needs Pillow and numpy.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

src = Image.open(sys.argv[1]).convert("RGB")
w, h = src.size
sx, sy = w / 1672, h / 941
arr = np.asarray(src).astype(float)
# fill: the colour of the empty wall on the left side, row by row
rows = arr[:, : int(400 * sx)].mean(1)
fill = Image.fromarray(np.repeat(rows[:, None, :], w, axis=1).clip(0, 255).astype("uint8"))
poly = [(586, 520), (590, 300), (600, 0), (1672, 0), (1672, 650), (1590, 760),
        (1380, 760), (1100, 675), (900, 610), (700, 595)]
mask = Image.new("L", src.size, 0)
ImageDraw.Draw(mask).polygon([(x * sx, y * sy) for x, y in poly], fill=255)
mask = mask.filter(ImageFilter.GaussianBlur(30 * sx))
out = Image.composite(fill, src, mask).resize((1280, 720), Image.LANCZOS)
dst = Path(__file__).with_name("workbench.webp")
out.save(dst, "WEBP", quality=80, method=6)
print("wrote", dst, dst.stat().st_size, "bytes")
