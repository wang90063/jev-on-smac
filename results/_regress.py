#!/usr/bin/env python3
"""Local regression harness. No API calls.

trace:  step-by-step action hashes for dummy / force / default / random clients.
        --compare OLD.json reports the first step where anything differs.
gate:   dummy (and optional force picks) on all maps; exit 1 if any
        baseline win turns into a loss.
force:  per-exam Force(kind=!default) vs dummy, for the menu evidence table.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "smaclite"))
os.environ["JEV_QUIET"] = "1"

from macsmac.env import StarCraft2Env  # noqa: E402
from macsmac.maps import MAP_PARAMS  # noqa: E402
from macsmac.snapshot import snapshot  # noqa: E402
import jev_smac_policy as J  # noqa: E402

SEEDS = [1, 2, 3, 4, 5]
MAPS = list(MAP_PARAMS.keys())


class DefaultClient:
    """Answers nothing per question, so every open exam takes its default."""

    def __init__(self):
        self.n_calls = 0
        self.infer_s = 0.0
        self.last_usage: Dict[str, int] = {}

    def system_one(self, state: Any, questions: Dict[str, Any]) -> Optional[dict]:
        self.n_calls += 1
        return {"answers": {}}


class RandomClient:
    """Uniform pick over each question's options, seeded per episode."""

    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.n_calls = 0
        self.infer_s = 0.0
        self.last_usage: Dict[str, int] = {}

    def system_one(self, state: Any, questions: Dict[str, Any]) -> Optional[dict]:
        self.n_calls += 1
        answers = {}
        for kind in sorted(questions):
            opts = sorted((questions[kind] or {}).get("criteria") or {})
            if opts:
                answers[kind] = {"choice": self.rng.choice(opts)}
        return {"answers": answers}


def make_policy(spec: str, map_name: str, seed: int):
    if spec == "dummy":
        return J.DummyActionPolicy()
    if spec == "default":
        return J.JevActionPolicy(client=DefaultClient(), tag="default")
    if spec == "random":
        h = int(hashlib.md5(f"{map_name}:{seed}".encode()).hexdigest()[:8], 16)
        return J.JevActionPolicy(client=RandomClient(h), tag="random")
    if spec.startswith("force:"):
        picks = dict(kv.split("=", 1) for kv in spec[6:].split(","))
        return J.ForceActionPolicy(picks)
    raise ValueError(spec)


def run(spec: str, map_name: str, seed: int, trace: bool = False) -> Dict[str, Any]:
    pol = make_policy(spec, map_name, seed)
    env = StarCraft2Env(map_name=map_name, seed=seed)
    env.reset()
    ret, steps, done, info = 0.0, 0, False, {}
    h = hashlib.sha1()
    first: List[str] = []
    asked: Dict[str, int] = {}
    try:
        while not done:
            snap = snapshot(env)
            actions = pol.act(map_name, steps, snap)
            if trace:
                rec = json.dumps(
                    [steps, actions, snap.get("_catalog_options"), (snap.get("_live_tactic") or {}).get("name")],
                    sort_keys=True,
                )
                h.update(rec.encode())
                first.append(hashlib.sha1(rec.encode()).hexdigest()[:10])
            for k in snap.get("_catalog_options") or {}:
                asked[k] = asked.get(k, 0) + 1
            reward, done, info = env.step(actions)
            ret += float(reward)
            steps += 1
            if steps > env.episode_limit + 5:
                break
    finally:
        env.close()
    row = {
        "policy": spec,
        "map": map_name,
        "seed": seed,
        "win": int(bool(info.get("battle_won"))),
        "ret": round(ret, 3),
        "steps": steps,
        "open": asked,
        "ov": list(getattr(pol, "overrides", [])[:8]),
    }
    if trace:
        row["hash"] = h.hexdigest()
        row["steps_h"] = first
    return row


def cmd_trace(args):
    rows = {}
    for spec in args.policies:
        for m in args.maps:
            for s in args.seeds:
                r = run(spec, m, s, trace=True)
                rows[f"{spec}|{m}|{s}"] = r
    Path(args.out).write_text(json.dumps(rows, indent=0))
    print(f"wrote {len(rows)} traces -> {args.out}")
    if not args.compare:
        return 0
    old = json.loads(Path(args.compare).read_text())
    bad = 0
    for key, r in rows.items():
        o = old.get(key)
        if o is None:
            print(f"NEW   {key}")
            continue
        if o["hash"] == r["hash"]:
            continue
        bad += 1
        a, b = o["steps_h"], r["steps_h"]
        t = next((i for i in range(min(len(a), len(b))) if a[i] != b[i]), min(len(a), len(b)))
        print(f"DIFF  {key} first step t={t}  win {o['win']}->{r['win']} ret {o['ret']}->{r['ret']}")
    print(f"{bad} differing / {len(rows)}")
    return 1 if bad else 0


def cmd_gate(args):
    base = {}
    if args.baseline and Path(args.baseline).is_file():
        for line in Path(args.baseline).read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                base[(r["policy"], r["map"], int(r["seed"]))] = r
    rows = [run(spec, m, s) for spec in args.policies for m in args.maps for s in args.seeds]
    if args.write:
        with open(args.write, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
    lost = gained = 0
    for r in rows:
        o = base.get((r["policy"], r["map"], r["seed"]))
        if o is None:
            continue
        if o["win"] and not r["win"]:
            lost += 1
            print(f"LOST   {r['policy']} {r['map']} s{r['seed']} ret {o['ret']}->{r['ret']}")
        elif r["win"] and not o["win"]:
            gained += 1
            print(f"GAINED {r['policy']} {r['map']} s{r['seed']} ret {o['ret']}->{r['ret']}")
    by: Dict[str, List[int]] = {}
    for r in rows:
        by.setdefault(r["policy"], []).append(r["win"])
    for p, w in by.items():
        print(f"{p}: {sum(w)}/{len(w)}")
    print(f"lost={lost} gained={gained}")
    return 1 if lost else 0


def cmd_force(args):
    """For each exam kind: on every (map, seed) where it opened under dummy,
    run Force(kind=!default) and compare with dummy."""
    dummy = {(m, s): run("dummy", m, s) for m in args.maps for s in args.seeds}
    out_dir = ROOT / "results" / "force"
    out_dir.mkdir(exist_ok=True)
    summary = {}
    for kind in args.kinds:
        spec = f"force:{kind}=!default"
        rows = []
        for (m, s), d in dummy.items():
            if kind not in d["open"]:
                continue
            f = run(spec, m, s)
            f["dummy_win"], f["dummy_ret"] = d["win"], d["ret"]
            rows.append(f)
        with open(out_dir / f"{kind}.jsonl", "w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        flips = [f"{r['map']}:s{r['seed']}" for r in rows if r["win"] and not r["dummy_win"]]
        losses = [f"{r['map']}:s{r['seed']}" for r in rows if r["dummy_win"] and not r["win"]]
        summary[kind] = {"episodes": len(rows), "beats_dummy": flips, "loses_to_dummy": losses}
        print(f"{kind:10s} n={len(rows):3d} beats={flips} loses={losses}")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    return 0


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("trace", "gate", "force"):
        sp = sub.add_parser(name)
        sp.add_argument("--maps", nargs="+", default=MAPS)
        sp.add_argument("--seeds", nargs="+", type=int, default=SEEDS)
    t = sub.choices["trace"]
    t.add_argument("--policies", nargs="+", default=["dummy", "force:ranged=stutter", "default", "random"])
    t.add_argument("--out", required=True)
    t.add_argument("--compare")
    g = sub.choices["gate"]
    g.add_argument("--policies", nargs="+", default=["dummy"])
    g.add_argument("--baseline", default=str(ROOT / "results" / "gate_baseline.jsonl"))
    g.add_argument("--write")
    f = sub.choices["force"]
    f.add_argument("--kinds", nargs="+", default=list(J.KIND_ORDER))
    args = p.parse_args()
    return {"trace": cmd_trace, "gate": cmd_gate, "force": cmd_force}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
