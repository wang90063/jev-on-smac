"""Claude's program vs Grok's program, one per side, on mirror fights.

    python results/duel.py tally                      # every mirror official map + mirror scenario, both seats
    JEV_GIF_CELL=22 JEV_GIF_PAD=1 python results/duel.py gif 1c3s5z 1   # -> docs/duel.gif, Claude blue

The blue side goes through env.step as usual. The red side normally runs the engine's
attack-move; here its program sees a mirrored snapshot (sides swapped, red legal-action
rows built with the engine's own move/target rules) and its answers are written straight
onto the red units' commands before each step. The simulator itself is not changed.
Both programs share one fallback for units they leave alone: attack the nearest enemy
in sight, else walk toward it. Timeout counts as a draw here.
"""
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "smaclite")); sys.path.insert(0, str(ROOT / "results"))
os.environ.setdefault("JEV_QUIET", "1")

import code_policy as CP  # noqa: E402
import scenarios as SC  # noqa: E402
from macsmac.env import StarCraft2Env  # noqa: E402
from macsmac.snapshot import snapshot  # noqa: E402
from smaclite.env.units.unit_command import AttackUnitCommand, MoveCommand, StopCommand  # noqa: E402
from smaclite.env.util.direction import Direction  # noqa: E402

CLAUDE = (ROOT / "kb/library/code/general_claude.py").read_text()
GROK = (ROOT / "kb/library/code/general.py").read_text()
OFFICIAL = ["3m", "8m", "25m", "2s3z", "3s5z", "1c3s5z", "MMM", "bane_vs_bane"]  # the official maps with the same army on both sides
SIGHT = 6  # AGENT_TARGET_RANGE


class Fallback:
    """Same for both sides: shoot the nearest enemy in sight, else close in."""

    def act(self, _map, _step, snap):
        out = []
        for a in snap["allies"]:
            row = snap["avail"][a["id"]]
            if not a.get("alive"):
                out.append(0)
                continue
            foes = [e for e in (snap["allies"] if a.get("role") == "heal" else snap["enemies"])
                    if e.get("alive") and e["id"] != a["id"] and 6 + e["id"] < len(row) and row[6 + e["id"]]]
            if foes:
                key = (lambda e: e["hp"] / max(e["max_hp"], 1)) if a.get("role") == "heal" else (lambda e: math.hypot(e["x"] - a["x"], e["y"] - a["y"]))
                out.append(6 + min(foes, key=key)["id"])
                continue
            live = [e for e in snap["enemies"] if e.get("alive")]
            if not live:
                out.append(1)
                continue
            t = min(live, key=lambda e: math.hypot(e["x"] - a["x"], e["y"] - a["y"]))
            moves = [(math.hypot(a["x"] + 2 * d[0] - t["x"], a["y"] + 2 * d[1] - t["y"]), k)
                     for k, d in CP.DIRS.items() if row[k]]
            out.append(min(moves)[1] if moves else 1)
        return out


def red_view(g, snap):
    """The snapshot as the red side sees it, with red legal-action rows."""
    n = len(snap["avail"][0]) if snap["avail"] else 6 + max(len(snap["allies"]), len(snap["enemies"]))
    n = max(n, 6 + max(len(snap["allies"]), len(snap["enemies"])))
    can_move = g._SMACliteEnv__can_move
    rows = []
    for e in snap["enemies"]:
        row = [0] * n
        u = g.enemies.get(e["id"])
        if u is None or u.hp <= 0:
            row[0] = 1
            rows.append(row)
            continue
        row[1] = 1
        for d in Direction:
            row[2 + d.value] = int(can_move(u, d))
        healer = e.get("role") == "heal"
        pool = g.enemies if healer else g.agents
        for tid, t in pool.items():
            if t is u or t.hp <= 0 or (healer and "HEAL" in t.combat_type.name):
                continue
            row[6 + tid] = int(math.hypot(*(t.pos - u.pos)) <= SIGHT)
        rows.append(row)
    view = dict(snap)
    view.update(allies=snap["enemies"], enemies=snap["allies"], avail=rows, n_agents=snap["n_enemies"], n_enemies=snap["n_agents"])
    return view


def command_red(g, view, actions):
    for e in view["allies"]:
        if not e.get("alive"):
            continue
        u, a = g.enemies.get(e["id"]), actions[e["id"]]
        if u is None or not view["avail"][e["id"]][a] or a == 0:
            continue
        if a == 1:
            u.command = StopCommand()
        elif a <= 5:
            u.command = MoveCommand(u.pos + Direction(a - 2).dx_dy * 2)
        else:
            u.command = AttackUnitCommand((g.enemies if e.get("role") == "heal" else g.agents)[a - 6])


def make_env(name, seed):
    if name[:1].isalpha() and name[1:].isdigit() and len(name) == 5:
        scen = next(s for split in ("train", "train2", "val", "test2", "test3", "test4", "test5", "test6")
                    for s in SC.load(split) if s["id"] == name)
        return SC.make_env(scen, seed)
    return StarCraft2Env(map_name=name, seed=seed)


def fight(name, seed, blue_src, red_src, on_frame=None):
    """-> ('blue' | 'red' | 'draw', steps, blue alive, red alive, n_blue, n_red)"""
    blue, red = CP.CodeActionPolicy(blue_src, "blue", base=Fallback()), CP.CodeActionPolicy(red_src, "red", base=Fallback())
    env = make_env(name, seed)
    env.reset()
    g = env._gym
    nb, nr = len(g.agents), len(g.enemies)
    step, done, info = 0, False, {}
    try:
        while not done:
            if on_frame:
                on_frame(step, g)
            snap = snapshot(env)
            view = red_view(g, snap)
            command_red(g, view, red.act(name, step, view))
            _, done, info = env.step(blue.act(name, step, snap))
            step += 1
        b = sum(u.hp > 0 for u in g.agents.values()); r = sum(u.hp > 0 for u in g.enemies.values())
        if on_frame:
            on_frame(step, g, final=True)
    finally:
        env.close()
    winner = "blue" if b and not r else "red" if r and not b else "draw"
    for p in (blue, red):
        if p.error_rate > 0.1:
            print(f"  ! {p.tag} errors {p.error_rate:.0%}: {p.last_error}")
    return winner, step, b, r, nb, nr


def mirrors():
    names = list(OFFICIAL)
    for split in ("train", "train2", "val"):
        names += [s["id"] for s in SC.load(split) if s["ally"] == s["enemy"]]
    return names


def tally(seeds=(1, 2, 3)):
    score = {"claude": 0, "grok": 0, "draw": 0}
    for name in mirrors():
        for seed in seeds:
            row = []
            for seat in ("blue", "red"):
                srcs = (CLAUDE, GROK) if seat == "blue" else (GROK, CLAUDE)
                w, step, b, r, nb, nr = fight(name, seed, *srcs)
                who = "draw" if w == "draw" else ("claude" if w == seat else "grok")
                score[who] += 1
                row.append(f"claude {seat:4s}: {who:6s} {step:3d} steps  blue {b}/{nb} red {r}/{nr}")
            print(f"{name:16s} s{seed}  " + "  |  ".join(row), flush=True)
    print(score)




def gif(name, seed, out="duel.gif"):
    """One fight, Claude blue vs Grok red, drawn with readme_gif's renderer."""
    os.environ.setdefault("JEV_GIF_ZH", "1")
    sys.argv = sys.argv[:1]  # readme_gif reads its own scenario and seed from argv
    import readme_gif as G
    from PIL import Image

    title = "Claude（蓝）对 Grok（红）"
    frames, n = [], {}

    def on_frame(step, g, final=False):
        b = sum(u.hp > 0 for u in g.agents.values()); r = sum(u.hp > 0 for u in g.enemies.values())
        n.setdefault("b", b); n.setdefault("r", r)  # dead units leave the dicts, so keep the starting sizes
        sub = f"{name} 镜像　第 {step} 步　蓝 {b}　红 {r}"
        banner = None
        if final:
            banner = ((f"Claude 胜 {b}/{n['b']}", (37, 120, 220)) if b and not r else
                      (f"Grok 胜 {r}/{n['r']}", (222, 72, 62)) if r and not b else ("平局", (110, 110, 110)))
        frames.append(G.frame(g, title, sub, banner))

    print(fight(name, seed, CLAUDE, GROK, on_frame))
    pad = G.PAD * G.CELL
    x0 = max(0, min(x for x, _ in G.SEEN) - pad); x1 = min(frames[0].width, max(x for x, _ in G.SEEN) + pad)
    y0 = max(G.HEAD, min(y for _, y in G.SEEN) - pad); y1 = min(frames[0].height, max(y for _, y in G.SEEN) + pad)
    w = max(int(x1 - x0), 560)  # room for the header text
    x0 = max(0, min(x0 - (w - (x1 - x0)) / 2, frames[0].width - w)); x1 = x0 + w
    out_frames = []
    for im in frames:
        c = Image.new("RGB", (int(x1 - x0), int(y1 - y0) + G.HEAD), (255, 255, 255))
        c.paste(im.crop((0, 0, int(x1 - x0), G.HEAD)), (0, 0))
        c.paste(im.crop((int(x0), int(y0), int(x1), int(y1))), (0, G.HEAD))
        if im.info.get("banner"):
            G.stamp(c, im.info["banner"])
        out_frames.append(c.convert("P", palette=Image.ADAPTIVE, colors=64))
    out_frames += [out_frames[-1]] * 10
    dest = ROOT / "docs" / out
    n = len(out_frames)
    out_frames[0].save(dest, save_all=True, append_images=out_frames[1:], duration=[160] * (n - 1) + [2500], loop=0, optimize=True)
    print(dest, f"{dest.stat().st_size / 1e6:.2f} MB", out_frames[0].size, n, "frames")


if __name__ == "__main__":
    if sys.argv[1] == "tally":
        tally()
    else:
        gif(sys.argv[2], int(sys.argv[3]))
