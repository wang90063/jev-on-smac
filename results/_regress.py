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
from typing import Any, Dict, List, Optional, Tuple

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
    if spec.startswith("prog:"):
        import tactic_dsl as T
        name = spec[5:]
        prog = T.HAND_RULES if name == "hand_rules" else json.loads(Path(name).read_text())
        return J.ProgramActionPolicy(prog)
    if spec.startswith("jevswitch"):
        # jevswitch:<picker>:<delta>, picker jev|random
        _, picker, delta = spec.split(":")
        h = int(hashlib.md5(f"{map_name}:{seed}".encode()).hexdigest()[:8], 16)
        return J.JevSwitchPolicy(delta=float(delta), picker=picker, seed=h, tag=spec)
    if spec.startswith("knn:"):
        # knn:<k>:<tau>
        _, k, tau = spec.split(":")
        return J.KnnSwitchPolicy(k=int(k), tau=float(tau), tag=spec)
    if spec == "value_online":
        return J.ValueOnlinePolicy(tag=spec)
    if spec.startswith("switchh2:"):
        # history-feature model after one DAgger round with its own driver
        import value as V

        return J.SwitchPolicy(model=V.load_model(V.ROOT / "kb" / "library" / "value_model_hist2.pkl"),
                              tau=float(spec.split(":", 1)[1]), tag=spec)
    if spec.startswith("switchh:"):
        # value policy with the history-feature model
        import value as V

        return J.SwitchPolicy(model=V.load_model(V.HIST_MODEL_PATH), tau=float(spec.split(":", 1)[1]), tag=spec)
    if spec.startswith("switch"):
        # switch = base policy B (nearest cluster re-picked every 5 steps);
        # switch:<tau> = value policy leaving default when predicted advantage > tau.
        if ":" not in spec:
            return J.SwitchPolicy(tag=spec)
        import value as V

        return J.SwitchPolicy(model=V.load_model(), tau=float(spec.split(":", 1)[1]), tag=spec)
    if spec.startswith("online"):
        # The online default (nearest cluster) or another chooser on the same library.
        # online[:chooser[:k<int>n<int>]], e.g. online:jev2:k5n8
        parts = spec.split(":")
        chooser = parts[1] if len(parts) > 1 else "nearest"
        k, nn = 4, 5
        if len(parts) > 2:
            import re as _re

            m = _re.fullmatch(r"k(\d+)n(\d+)", parts[2])
            k, nn = int(m.group(1)), int(m.group(2))
        # online@outcome:... picks from the round-6 outcome library instead of lib3.
        library = parts[0].split("@", 1)[1] if "@" in parts[0] else "lib3"
        h = int(hashlib.md5(f"{map_name}:{seed}".encode()).hexdigest()[:8], 16)
        return J.OnlinePolicy(chooser=chooser, seed=h, tag=spec, k=k, n_neighbors=nn, library=library)
    if spec.startswith("dist:"):
        lib = json.loads((ROOT / "kb" / "library" / "distilled_programs.json").read_text())
        return J.ProgramActionPolicy(next(e["program"] for e in lib if e["id"] == spec[5:]), tag=spec)
    if spec.startswith(("lib3:", "lib3h:", "lib4:")):
        # Round 3: cluster library with the Dummy fallback. lib3 = forged only,
        # lib3h = forged + hand rules that passed the same gate.
        # Round 4: lib4 = forged with offline-search hints, forged only.
        kind, chooser = spec.split(":", 1)
        name = "hinted_programs.json" if kind == "lib4" else "cluster_programs.json"
        lib = json.loads((ROOT / "kb" / "library" / name).read_text())
        if kind in ("lib3", "lib4"):
            lib = [e for e in lib if e.get("source") != "hand"]
        clusters = json.loads((ROOT / "kb" / "library" / "clusters.json").read_text())
        h = int(hashlib.md5(f"{map_name}:{seed}".encode()).hexdigest()[:8], 16)
        return J.LibraryPolicy(lib, chooser=chooser, seed=h, clusters=clusters, fallback=True, tag=spec)
    if spec.startswith("lib:"):
        lib = json.loads((ROOT / "kb" / "library" / "programs.json").read_text())
        h = int(hashlib.md5(f"{map_name}:{seed}".encode()).hexdigest()[:8], 16)
        return J.LibraryPolicy(lib, chooser=spec[4:], seed=h)
    if spec.startswith("force:"):
        picks = dict(kv.split("=", 1) for kv in spec[6:].split(","))
        return J.ForceActionPolicy(picks)
    raise ValueError(spec)


def run(spec: str, map_name: str, seed: int, trace: bool = False, scenario: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    pol = make_policy(spec, map_name, seed)
    if scenario is not None:
        import scenarios as SC

        env = SC.make_env(scenario, seed)
    else:
        env = StarCraft2Env(map_name=map_name, seed=seed)
    env.reset()
    ret, steps, done, info = 0.0, 0, False, {}
    h = hashlib.sha1()
    ha = hashlib.sha1()
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
                ha.update(json.dumps([steps, actions]).encode())
                first.append(hashlib.sha1(rec.encode()).hexdigest()[:10])
            for k in snap.get("_catalog_options") or {}:
                asked[k] = asked.get(k, 0) + 1
            reward, done, info = env.step(actions)
            ret += float(reward)
            steps += 1
            if steps > env.episode_limit + 5:
                break
        a_live = [u for u in env._gym.agents.values() if getattr(u, "hp", 0) > 0]
        e_live = [u for u in env._gym.enemies.values() if getattr(u, "hp", 0) > 0]
        left = {
            "A": [len(a_live), round(sum(u.hp + getattr(u, "shield", 0) for u in a_live), 1)],
            "E": [len(e_live), round(sum(u.hp + getattr(u, "shield", 0) for u in e_live), 1)],
        }
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
        **left,
        "ov": list(getattr(pol, "overrides", [])[:8]),
    }
    if trace:
        row["hash"] = h.hexdigest()
        row["act_hash"] = ha.hexdigest()
        row["steps_h"] = first
    return row


def run_scenario(spec: str, scenario: Dict[str, Any], seed: int, trace: bool = False) -> Dict[str, Any]:
    """Same as run() on a generated scenario (scenarios.py)."""
    return run(spec, scenario["id"], seed, trace=trace, scenario=scenario)


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
    field = "act_hash" if args.actions_only else "hash"
    for key, r in rows.items():
        o = old.get(key)
        if o is None:
            print(f"NEW   {key}")
            continue
        if o[field] == r[field]:
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
    """For each exam kind (or kind=option): on every (map, seed) where it
    opened under dummy, run Force and compare with dummy."""
    dummy = {(m, s): run("dummy", m, s) for m in args.maps for s in args.seeds}
    out_dir = ROOT / "results" / "force"
    out_dir.mkdir(exist_ok=True)
    summary = {}
    for item in args.kinds:
        kind, opt = item.split("=", 1) if "=" in item else (item, "!default")
        spec = f"force:{kind}={opt}"
        rows = []
        for (m, s), d in dummy.items():
            if kind not in d["open"]:
                continue
            f = run(spec, m, s)
            f["dummy_win"], f["dummy_ret"] = d["win"], d["ret"]
            rows.append(f)
        name = kind if opt == "!default" else f"{kind}__{opt}"
        with open(out_dir / f"{name}.jsonl", "w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        flips = [f"{r['map']}:s{r['seed']}" for r in rows if r["win"] and not r["dummy_win"]]
        losses = [f"{r['map']}:s{r['seed']}" for r in rows if r["dummy_win"] and not r["win"]]
        summary[name] = {"episodes": len(rows), "beats_dummy": flips, "loses_to_dummy": losses}
        print(f"{name:24s} n={len(rows):3d} beats={flips} loses={losses}")
    path = out_dir / "summary.json"
    old = json.loads(path.read_text()) if path.is_file() else {}
    old.update(summary)
    path.write_text(json.dumps(old, indent=1, sort_keys=True))
    return 0


def _holdout_job(job):
    spec, scen, seed = job
    if scen is None:
        return run(spec, seed[0], seed[1])
    return run_scenario(spec, scen, seed)


def cmd_holdout(args):
    """Policies on the frozen test scenarios (and, for reference, official maps)."""
    from multiprocessing import Pool

    import scenarios as SC

    test = SC.load(args.split)
    jobs = [(p, sc, s) for p in args.policies for sc in test for s in args.seeds]
    if args.official:
        jobs += [(p, None, (m, s)) for p in args.policies for m in MAPS for s in args.seeds]
    # Jev calls go over the network; keep them serial-ish.
    with Pool(4 if any((p.split(":")[1:2] and p.split(":")[1].startswith("jev")) or p.endswith("jev") for p in args.policies) else 8) as pool:
        rows = pool.map(_holdout_job, jobs, chunksize=1)
    out = Path(args.write)
    with out.open("w") as f:
        for (p, sc, s), r in zip(jobs, rows):
            r["policy"] = p
            r["set"] = "official" if sc is None else args.split
            f.write(json.dumps(r) + "\n")
    table: Dict[Tuple[str, str], List[int]] = {}
    for (p, sc, s), r in zip(jobs, rows):
        table.setdefault((p, r["set"]), []).append(r["win"])
    for (p, st), w in sorted(table.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        print(f"{st:9s} {p:22s} {sum(w):4d}/{len(w)}")
    return 0


def _sign_test_p(a: int, b: int) -> float:
    """Two-sided exact binomial (McNemar) p-value for a flips vs b losses."""
    from math import comb

    n = a + b
    if n == 0:
        return 1.0
    k = min(a, b)
    tail = sum(comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def cmd_paired(args):
    """Pair every policy with the base on the same (set, fight, seed)."""
    rows: Dict[Tuple[str, str, str, int], int] = {}
    for fn in args.files:
        for line in Path(fn).read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                rows[(r["policy"], r.get("set", "?"), r["map"], int(r["seed"]))] = r["win"]
    policies = sorted({k[0] for k in rows})
    for st in sorted({k[1] for k in rows}):
        print(f"== {st}  (base {args.base})")
        for p in policies:
            if p == args.base:
                continue
            flip = lose = n = 0
            for (pp, s2, m, seed), w in rows.items():
                if pp != p or s2 != st:
                    continue
                b = rows.get((args.base, st, m, seed))
                if b is None:
                    continue
                n += 1
                flip += int(w and not b)
                lose += int(b and not w)
            if n:
                print(f"  {p:22s} n={n:4d} flips(+)={flip:3d} losses(-)={lose:3d} net={flip - lose:+4d} p={_sign_test_p(flip, lose):.3f}")
    return 0


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("trace", "gate", "force", "holdout"):
        sp = sub.add_parser(name)
        sp.add_argument("--maps", nargs="+", default=MAPS)
        sp.add_argument("--seeds", nargs="+", type=int, default=SEEDS)
    t = sub.choices["trace"]
    t.add_argument("--policies", nargs="+", default=["dummy", "force:ranged=stutter", "default", "random"])
    t.add_argument("--out", required=True)
    t.add_argument("--compare")
    t.add_argument("--actions-only", action="store_true", help="ignore exam bookkeeping, compare actions")
    g = sub.choices["gate"]
    g.add_argument("--policies", nargs="+", default=["dummy"])
    g.add_argument("--baseline", default=str(ROOT / "results" / "gate_baseline.jsonl"))
    g.add_argument("--write")
    f = sub.choices["force"]
    f.add_argument("--kinds", nargs="+", default=list(J.KIND_ORDER))
    h = sub.choices["holdout"]
    h.add_argument("--policies", nargs="+", default=["dummy", "prog:hand_rules", "lib:nearest", "lib:random"])
    h.add_argument("--split", default="test")
    h.add_argument("--official", action="store_true")
    h.add_argument("--write", required=True)
    pr = sub.add_parser("paired")
    pr.add_argument("--files", nargs="+", required=True)
    pr.add_argument("--base", default="dummy")
    args = p.parse_args()
    return {"trace": cmd_trace, "gate": cmd_gate, "force": cmd_force, "holdout": cmd_holdout, "paired": cmd_paired}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
