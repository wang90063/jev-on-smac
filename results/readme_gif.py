"""Side-by-side GIF of one test6 fight for the README: baseline vs the online default.

    python results/readme_gif.py [scenario_id] [seed]      # default y0810 seed 4
    -> docs/fight.gif
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "smaclite")); sys.path.insert(0, str(ROOT / "results"))
os.environ.setdefault("JEV_QUIET", "1")

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import _regress as R  # noqa: E402
import scenarios as SC  # noqa: E402
from macsmac.snapshot import snapshot  # noqa: E402

SID = sys.argv[1] if len(sys.argv) > 1 else "y0810"
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 4
PANELS = [("dummy", "Scripted baseline (attack-move)"),
          ("code:kb/library/code/general_claude.py", "LLM-synthesized program (Claude)")]
CELL = 26
HEAD = 54
BG, GROUND, WALL = (250, 250, 248), (236, 238, 233), (92, 98, 108)
OURS, THEIRS, LINE = (37, 120, 220), (222, 72, 62), (90, 90, 90)
ABBR = {"STALKER": "S", "HYDRALISK": "H", "MARINE": "m", "MARAUDER": "M", "ZEALOT": "Z", "ZERGLING": "z",
        "BANELING": "B", "COLOSSUS": "C", "MEDIVAC": "+"}


def font(size):
    for p in ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/SFNS.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


F_TITLE, F_SUB, F_UNIT, F_BIG = font(16), font(13), font(13), font(34)
SEEN = []  # unit pixel positions over both fights, for a shared crop


def frame(g, title, sub, banner=None):
    T = g.map_info.terrain
    h, w = len(T), len(T[0])
    img = Image.new("RGB", (w * CELL, h * CELL + HEAD), BG)
    d = ImageDraw.Draw(img)
    for y in range(h):
        for x in range(w):
            name = T[y][x].name
            col = GROUND if name == "NORMAL" else WALL
            Y = HEAD + (h - 1 - y) * CELL
            d.rectangle([x * CELL, Y, x * CELL + CELL - 1, Y + CELL - 1], fill=col)

    def px(p):
        return float(p[0]) * CELL, HEAD + (h - float(p[1])) * CELL

    units = [u for u in g.all_units.values() if u.hp > 0]
    for u in units:
        if u.target is not None and u.target.hp > 0:
            d.line([px(u.pos), px(u.target.pos)], fill=OURS if u.faction.name == "ALLY" else THEIRS, width=1)
    for u in units:
        cx, cy = px(u.pos)
        SEEN.append((cx, cy))
        r = max(u.radius * CELL, 6)
        col = OURS if u.faction.name == "ALLY" else THEIRS
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255), outline=col, width=2)
        tot = u.max_hp + (u.max_shield or 0)
        frac = (u.hp + (u.shield or 0)) / tot if tot else 0
        top = cy + r - 2 * r * frac
        inner = Image.new("L", img.size, 0)
        ImageDraw.Draw(inner).ellipse([cx - r + 2, cy - r + 2, cx + r - 2, cy + r - 2], fill=255)
        clip = Image.new("L", img.size, 0)
        ImageDraw.Draw(clip).rectangle([cx - r, top, cx + r, cy + r], fill=255)
        from PIL import ImageChops
        img.paste(col, mask=ImageChops.multiply(inner, clip))
        d = ImageDraw.Draw(img)
        d.text((cx, cy), ABBR.get(u.type.stats.name.upper(), "?"), fill=(20, 20, 20), font=F_UNIT, anchor="mm")
    d.rectangle([0, 0, img.width, HEAD - 1], fill=(255, 255, 255))
    d.text((10, 9), title, fill=(25, 25, 25), font=F_TITLE)
    d.text((10, 31), sub, fill=(110, 110, 110), font=F_SUB)
    img.info["banner"] = banner
    return img


def stamp(img, banner):
    text, col = banner
    ImageDraw.Draw(img).text((img.width / 2, HEAD + 34), text, fill=col, font=F_BIG, anchor="mm",
                             stroke_width=4, stroke_fill=(255, 255, 255))


def play(spec, title):
    scen = next(s for s in SC.load("test6") if s["id"] == SID)
    pol = R.make_policy(spec, SID, SEED)
    env = SC.make_env(scen, SEED)
    env.reset()
    g = env._gym
    frames, step, done, info = [], 0, False, {}
    alive = lambda us: sum(u.hp > 0 for u in us)  # noqa: E731
    try:
        while not done:
            frames.append(frame(g, title, f"step {step:3d}   ours {alive(g.agents.values())}   theirs {alive(g.enemies.values())}"))
            _, done, info = env.step(pol.act(SID, step, snapshot(env)))
            step += 1
        won = bool(info.get("battle_won"))
        a, n = alive(g.agents.values()), len(g.agents)
        sub = f"step {step:3d}   ours {a}   theirs {alive(g.enemies.values())}"
        frames.append(frame(g, title, sub, (f"WIN  {a}/{n} alive" if won else "LOSS", (30, 140, 70) if won else (200, 50, 45))))
    finally:
        env.close()
    print(spec, "won" if won else "lost", "steps", step)
    return frames


def main():
    runs = [play(spec, title) for spec, title in PANELS]
    pad = 4 * CELL
    x0 = max(0, min(x for x, _ in SEEN) - pad); x1 = min(runs[0][0].width, max(x for x, _ in SEEN) + pad)
    y0 = max(HEAD, min(y for _, y in SEEN) - pad); y1 = min(runs[0][0].height, max(y for _, y in SEEN) + pad)

    def crop(im):
        out = Image.new("RGB", (int(x1 - x0), int(y1 - y0) + HEAD), (255, 255, 255))
        out.paste(im.crop((0, 0, int(x1 - x0), HEAD)), (0, 0))
        out.paste(im.crop((int(x0), int(y0), int(x1), int(y1))), (0, HEAD))
        if im.info.get("banner"):
            stamp(out, im.info["banner"])
        return out

    runs = [[crop(f) for f in r] for r in runs]
    hold = 10
    n = max(len(r) for r in runs) + hold
    gap = 8
    w = sum(r[0].width for r in runs) + gap * (len(runs) - 1)
    out = []
    for i in range(n):
        canvas = Image.new("RGB", (w, runs[0][0].height), (255, 255, 255))
        x = 0
        for r in runs:
            canvas.paste(r[min(i, len(r) - 1)], (x, 0))
            x += r[0].width + gap
        out.append(canvas.convert("P", palette=Image.ADAPTIVE, colors=64))
    dest = ROOT / "docs" / "fight.gif"
    dest.parent.mkdir(exist_ok=True)
    out[0].save(dest, save_all=True, append_images=out[1:], duration=[160] * (n - 1) + [2500], loop=0, optimize=True)
    print(dest, f"{dest.stat().st_size / 1e6:.2f} MB", out[0].size, len(out), "frames")


if __name__ == "__main__":
    main()
