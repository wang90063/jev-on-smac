#!/usr/bin/env python3
"""Narrated video of docs/deck.html: one still per slide, macOS TTS for the voice.

  python docs/make_video.py                              # writes video/deck.mp4, online voice
  python docs/make_video.py --voice Tingting --rate 190  # macOS `say` instead, offline

Voices named like zh-CN-YunxiNeural go through edge-tts (online: the narration text is sent to
Microsoft's speech service); any other name goes to macOS `say`. Needs Google Chrome and ffmpeg.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

DOCS = Path(__file__).resolve().parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
WORK = Path("/tmp/deckvideo")
PAD = 0.6  # seconds of silence after each slide's narration
# Animated images to play over their still frame: slide -> [(file, x, y, w, h)] in 1920x1080 pixels (inside the border).
OVERLAY = {13: [("fight_zoom.gif", 110, 218, 816, 702), ("duel.gif", 990, 780, 312, 208)]}


def sections(path: Path) -> dict[int, str]:
    parts = re.split(r"^## (\d+)\s*$", path.read_text(), flags=re.M)
    return {int(n): " ".join(t.split()) for n, t in zip(parts[1::2], parts[2::2])}


def run(*cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def speak(text: str, voice: str, rate: int, out: Path):
    if "Neural" not in voice:
        run("say", "-v", voice, "-o", str(out), *(["-r", str(rate)] if rate else []), text)
        return
    env = {k: v for k, v in os.environ.items() if "proxy" not in k.lower()}
    cmd = [sys.executable, "-m", "edge_tts", "--voice", voice, "--rate", f"{rate:+d}%", "--text", text, "--write-media", str(out)]
    for attempt in range(3):  # the service now and then returns no audio; one request at a time, with a pause
        if subprocess.run(cmd, env=env, capture_output=True).returncode == 0 and out.stat().st_size > 0:
            return
        time.sleep(5)
    raise RuntimeError(f"edge-tts gave no audio for {out.name}")


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         check=True, capture_output=True, text=True).stdout
    return float(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="zh-CN-YunxiNeural")
    ap.add_argument("--rate", type=int, default=0,
                    help="edge-tts: percent faster (+) or slower (-); say: words per minute, 0 = the voice default")
    ap.add_argument("--out", default=str(DOCS.parent / "video" / "deck.mp4"))
    args = ap.parse_args()

    WORK.mkdir(exist_ok=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    text = sections(DOCS / "deck_narration.md")
    segs = []
    for n in sorted(text):
        ext = ".mp3" if "Neural" in args.voice else ".aiff"
        shot, still, audio, seg = (WORK / f"{n:02d}{s}" for s in ("_raw.png", ".png", ext, ".mp4"))
        # The headless viewport is 87 px shorter than the window; this makes it exactly 1920x1080.
        run(CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1920,1167",
            "--virtual-time-budget=4000", f"--screenshot={shot}", f"file://{DOCS / 'deck.html'}?video#{n}")
        run("ffmpeg", "-y", "-i", str(shot), "-vf", "crop=1920:1080:0:0", str(still))
        speak(text[n], args.voice, args.rate, audio)
        length = duration(audio) + PAD
        video = ["-loop", "1", "-framerate", "30", "-i", str(still)]
        gifs = OVERLAY.get(n, [])
        chain, last = [], "0:v"
        for i, (gif, x, y, w, h) in enumerate(gifs, 1):
            video += ["-ignore_loop", "0", "-i", str(DOCS / gif)]
            chain += [f"[{i}:v]scale={w}:{h}[g{i}]", f"[{last}][g{i}]overlay={x}:{y}[v{i}]"]
            last = f"v{i}"
        if gifs:
            vf = ["-filter_complex", ";".join(chain), "-map", f"[{last}]", "-map", f"{len(gifs) + 1}:a"]
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
