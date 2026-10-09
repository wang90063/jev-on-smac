#!/usr/bin/env python3
"""Render docs/charts.html (the deck's bar charts, English labels) to docs/charts/<id>.png for the README.

  python docs/make_charts.py

Needs Google Chrome. Each chart is opened alone (?c=<id>), shot at 2x, and trimmed to its content.
"""
import subprocess
from pathlib import Path

from PIL import Image, ImageChops

DOCS = Path(__file__).resolve().parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHARTS = ["speed", "step1", "s23", "head", "test6", "ontop", "why", "auc"]
PAD = 24  # pixels of white kept around the content, at 2x


def main():
    out = DOCS / "charts"
    out.mkdir(exist_ok=True)
    for c in CHARTS:
        dest = out / f"{c}.png"
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                        "--window-size=1100,900", f"--screenshot={dest}", f"file://{DOCS / 'charts.html'}?c={c}"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        im = Image.open(dest).convert("RGB")
        box = ImageChops.difference(im, Image.new("RGB", im.size, (255, 255, 255))).getbbox()
        x0, y0, x1, y1 = box
        im.crop((max(0, x0 - PAD), max(0, y0 - PAD), min(im.width, x1 + PAD), min(im.height, y1 + PAD))).save(dest, optimize=True)
        print(dest.relative_to(DOCS.parent), Image.open(dest).size)


if __name__ == "__main__":
    main()
