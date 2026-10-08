#!/usr/bin/env python3
"""Q1: Jev as a per-unit actor, paired against attack-move and two action-level controls.

Every policy here outputs raw SMAC actions (0 noop, 1 stop, 2-5 N/S/E/W, 6+j attack enemy j).
  jev_unit      one Jev request per step, one Choice per living unit over that unit's legal actions
  random_legal  a uniformly random legal action per unit (noop excluded)
  closest       SMAC's scripted heuristic: shoot the closest enemy in range, else walk toward it
  focus         same, but shoot the lowest-HP enemy in range
  dummy         attack-move (the floor used everywhere else in the README)

Same maps and seeds for every policy, so results are paired.
  python results/q1_unit_actor.py run --policies closest,focus,random_legal,dummy
  python results/q1_unit_actor.py run --policies jev_unit      # network: one request per step, serial
  python results/q1_unit_actor.py table
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "results"))
sys.path.insert(0, str(ROOT / "src"))
import _regress as R  # noqa: E402

MAPS = ["3m", "8m", "5m_vs_6m", "2s3z", "3s5z", "3s_vs_3z", "10m_vs_11m"]
SEEDS = [1, 2, 3, 4, 5]
OUT = ROOT / "results" / "q1_unit_actor.jsonl"
MOVES = {2: ("north", 0.0, 2.0), 3: ("south", 0.0, -2.0), 4: ("east", 2.0, 0.0), 5: ("west", -2.0, 0.0)}


def _alive(units):
    return [u for u in units if u["alive"]]


def _d(a, b):
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def _in_range(u, e):
    return _d(u, e) <= u["range"] + u["radius"] + e["radius"]


def _legal(snap, i):
    return [a for a, ok in enumerate(snap["avail"][i]) if ok]


class _Base:
    def __init__(self, tag):
        self.tag = tag
        self.n_calls = 0
        self.infer_s = 0.0
        self.n_fallback = 0
        self.overrides = []


class Heuristic(_Base):
    """SMAC's scripted baseline: attack-move toward the closest enemy."""

    def __init__(self, mode):
        super().__init__(mode)
        self.mode = mode

    def act(self, map_name, step, snap):
        enemies = _alive(snap["enemies"])
        out = []
        for i, u in enumerate(snap["allies"]):
            legal = _legal(snap, i)
            if not u["alive"] or not enemies:
                out.append(1 if 1 in legal else legal[0])
                continue
            shoot = [e for e in enemies if 6 + e["id"] in legal and _in_range(u, e)]
            if shoot:
                key = (lambda e: e["hp"] + e["shield"]) if self.mode == "focus" else (lambda e: _d(u, e))
                out.append(6 + min(shoot, key=key)["id"])
                continue
            tgt = min(enemies, key=lambda e: _d(u, e))
            moves = [a for a in legal if a in MOVES]
            if 6 + tgt["id"] in legal:
                out.append(6 + tgt["id"])  # attack order on a visible target walks toward it
            elif moves:
                out.append(min(moves, key=lambda a: math.hypot(u["x"] + MOVES[a][1] - tgt["x"], u["y"] + MOVES[a][2] - tgt["y"])))
            else:
                out.append(legal[0])
        return out


class RandomLegal(_Base):
    def __init__(self, seed):
        super().__init__("random_legal")
        self.rng = random.Random(seed)

    def act(self, map_name, step, snap):
        out = []
        for i, u in enumerate(snap["allies"]):
            legal = _legal(snap, i)
            pool = [a for a in legal if a != 0] or legal
            out.append(self.rng.choice(pool) if u["alive"] else legal[0])
        return out


def _unit_line(u):
    return {
        "id": u["id"], "type": u["name"], "hp": round(u["hp"]), "shield": round(u["shield"]),
        "x": round(u["x"], 1), "y": round(u["y"], 1), "range": u["range"], "speed": u["speed"],
        "damage": u["dmg"], "cooldown_left_s": round(u["cd"], 2),
    }


class JevUnit(_Base):
    """One request per step. One Choice per living unit; options are exactly that unit's legal actions."""

    def __init__(self):
        super().__init__("jev_unit")
        from jev_api import JevClient

        self.client = JevClient()
        self.fallback = Heuristic("closest")

    def _options(self, snap, i, u, enemies):
        near = min(enemies, key=lambda e: _d(u, e)) if enemies else None
        opts = {}
        for a in _legal(snap, i):
            if a == 0:
                continue
            if a == 1:
                opts["stop"] = "Stand still this step."
            elif a in MOVES:
                name, dx, dy = MOVES[a]
                txt = f"Move 2 units {name}."
                if near is not None:
                    after = math.hypot(u["x"] + dx - near["x"], u["y"] + dy - near["y"])
                    txt += f" Distance to the nearest enemy goes from {_d(u, near):.1f} to {after:.1f}."
                opts[f"move_{name}"] = txt
            elif a >= 6:
                e = snap["enemies"][a - 6]
                where = "in range, shoots now if off cooldown" if _in_range(u, e) else "out of range, walks toward it first"
                opts[f"attack_{e['id']}"] = (
                    f"Attack enemy {e['id']} ({e['name']}, {round(e['hp'] + e['shield'])} HP+shield left, "
                    f"distance {_d(u, e):.1f}, {where})."
                )
        return opts

    def act(self, map_name, step, snap):
        enemies = _alive(snap["enemies"])
        base = self.fallback.act(map_name, step, snap)
        questions, keys = {}, {}
        for i, u in enumerate(snap["allies"]):
            if not u["alive"] or not enemies:
                continue
            opts = self._options(snap, i, u, enemies)
            if len(opts) < 2:
                continue
            questions[f"unit_{u['id']}"] = {
                "type": "choice",
                "instructions": (
                    f"You control our unit {u['id']} ({u['name']}) this step (0.5 s). "
                    "Pick the action that helps our side win the battle. A timeout counts as a loss."
                ),
                "criteria": opts,
            }
            keys[f"unit_{u['id']}"] = i
        if not questions:
            return base
        state = {
            "step": step, "limit": snap["limit"],
            "ours": [_unit_line(u) for u in _alive(snap["allies"])],
            "enemies": [_unit_line(e) for e in enemies],
        }
        res = self.client.system_one(state, questions)
        self.n_calls += 1
        self.infer_s = self.client.infer_s
        answers = (res or {}).get("answers") if isinstance(res, dict) else None
        if not isinstance(answers, dict):
            self.n_fallback += 1
            return base
        out = list(base)
        for q, i in keys.items():
            p = answers.get(q)
            pick = p.get("choice") if isinstance(p, dict) else p
            if pick is None and isinstance(p, dict) and isinstance(p.get("probabilities"), dict):
                pick = max(p["probabilities"], key=lambda k: float(p["probabilities"][k] or 0))
            a = _label_to_action(pick)
            if a is not None and a in _legal(snap, i):
                out[i] = a
            else:
                self.n_fallback += 1
        return out


def _label_to_action(label):
    if not isinstance(label, str):
        return None
    if label == "stop":
        return 1
    for a, (name, _, _) in MOVES.items():
        if label == f"move_{name}":
            return a
    if label.startswith("attack_"):
        try:
            return 6 + int(label[7:])
        except ValueError:
            return None
    return None


_orig = R.make_policy


def make_policy(spec, map_name, seed):
    if spec in ("closest", "focus"):
        return Heuristic(spec)
    if spec == "random_legal":
        return RandomLegal(int(hashlib.md5(f"{map_name}:{seed}".encode()).hexdigest()[:8], 16))
    if spec == "jev_unit":
        return JevUnit()
    return _orig(spec, map_name, seed)


R.make_policy = make_policy


def _done():
    seen = set()
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            r = json.loads(line)
            seen.add((r["policy"], r["map"], r["seed"]))
    return seen


def cmd_run(args):
    seen = _done()
    for spec in args.policies.split(","):
        for m in MAPS:
            for s in SEEDS:
                if (spec, m, s) in seen:
                    continue
                t = time.time()
                r = R.run(spec, m, s)
                r["wall_s"] = round(time.time() - t, 1)
                with OUT.open("a") as f:
                    f.write(json.dumps(r) + "\n")
                print(spec, m, s, "win" if r["win"] else "loss", r["steps"], "steps", r["calls"], "calls", r["wall_s"], "s", flush=True)


def cmd_table(args):
    rows = [json.loads(line) for line in OUT.read_text().splitlines()]
    by = {(r["policy"], r["map"], r["seed"]): r for r in rows}
    pols = sorted({r["policy"] for r in rows})
    print("| Map | " + " | ".join(pols) + " |")
    for m in MAPS:
        print(f"| {m} | " + " | ".join(f"{sum(by[(p, m, s)]['win'] for s in SEEDS if (p, m, s) in by)}/5" for p in pols) + " |")
    print("| total | " + " | ".join(str(sum(r["win"] for r in rows if r["policy"] == p)) for p in pols) + " |")
    j = [r for r in rows if r["policy"] == "jev_unit"]
    if j:
        calls = sum(r["calls"] for r in j)
        wall = sum(r["wall_s"] for r in j)
        print(f"jev_unit: {calls} requests, {wall / max(calls, 1):.2f} s/request end to end, {wall / len(j):.1f} s/battle")
        for p in pols:
            if p == "jev_unit":
                continue
            f = sum(1 for r in j if r["win"] and not by.get((p, r["map"], r["seed"]), {}).get("win"))
            l = sum(1 for r in j if not r["win"] and by.get((p, r["map"], r["seed"]), {}).get("win"))
            print(f"jev_unit vs {p}: +{f} / -{l}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("run")
    a.add_argument("--policies", required=True)
    sub.add_parser("table")
    args = ap.parse_args()
    {"run": cmd_run, "table": cmd_table}[args.cmd](args)
