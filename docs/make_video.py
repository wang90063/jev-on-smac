#!/usr/bin/env python3
"""Narrated video of docs/deck.html: one still per slide, macOS TTS for the voice.

  python docs/make_video.py            # writes docs/deck.mp4
  python docs/make_video.py --rate 190 # words per minute for `say`

Needs macOS `say` (voice Tingting), Google Chrome and ffmpeg.
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

DOCS = Path(__file__).resolve().parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
WORK = Path("/tmp/deckvideo")
PAD = 0.6  # seconds of silence after each slide's narration
# Animated images to play over their still frame: slide -> (file, x, y, w, h) in 1920x1080 pixels (inside the border).
OVERLAY = {12: ("fight.gif", 110, 230, 1700, 476)}


def sections(path: Path) -> dict[int, str]:
    parts = re.split(r"^## (\d+)\s*$", path.read_text(), flags=re.M)
    return {int(n): " ".join(t.split()) for n, t in zip(parts[1::2], parts[2::2])}


def run(*cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         check=True, capture_output=True, text=True).stdout
    return float(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate", type=int, default=0, help="say -r rate; 0 = the voice default (about 180), clearest")
    ap.add_argument("--voice", default="Tingting")
    ap.add_argument("--out", default=str(DOCS / "deck.mp4"))
    args = ap.parse_args()

    WORK.mkdir(exist_ok=True)
    text = sections(DOCS / "deck_narration.md")
    segs = []
    for n in sorted(text):
        shot, still, audio, seg = (WORK / f"{n:02d}{s}" for s in ("_raw.png", ".png", ".aiff", ".mp4"))
        # The headless viewport is 87 px shorter than the window; this makes it exactly 1920x1080.
        run(CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1920,1167",
            "--virtual-time-budget=4000", f"--screenshot={shot}", f"file://{DOCS / 'deck.html'}?video#{n}")
        run("ffmpeg", "-y", "-i", str(shot), "-vf", "crop=1920:1080:0:0", str(still))
        say = ["say", "-v", args.voice, "-o", str(audio)] + (["-r", str(args.rate)] if args.rate else []) + [text[n]]
        run(*say)
        length = duration(audio) + PAD
        video = ["-loop", "1", "-framerate", "30", "-i", str(still)]
        if n in OVERLAY:
            gif, x, y, w, h = OVERLAY[n]
            video += ["-ignore_loop", "0", "-i", str(DOCS / gif)]
            vf = ["-filter_complex", f"[1:v]scale={w}:{h}[g];[0:v][g]overlay={x}:{y}[v]", "-map", "[v]", "-map", "2:a"]
        else:
            vf = ["-map", "0:v", "-map", "1:a"]
        run("ffmpeg", "-y", *video, "-i", str(audio), *vf,
            "-af", f"apad=pad_dur={PAD}", "-t", f"{length:.2f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", str(seg))
        segs.append(seg)
        print(f"slide {n:2d}  {length:5.1f} s  {len(text[n])} chars", flush=True)

    listing = WORK / "list.txt"
    listing.write_text("".join(f"file '{s}'\n" for s in segs))
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", "-movflags", "+faststart", args.out)
    print(f"{args.out}  {duration(Path(args.out)) / 60:.1f} min")


if __name__ == "__main__":
    main()
