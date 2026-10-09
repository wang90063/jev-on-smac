#!/usr/bin/env python3
"""One scoreboard: every tactic-level system on the same battles, current code.

  python results/baseline_rerun.py local          # all non-Jev systems, official maps + val (parallel, minutes)
  python results/baseline_rerun.py jev            # Jev exam answers (card 4), official maps + val (serial, network)
  python results/baseline_rerun.py table          # win counts + paired sign tests vs Jev exam answers
  python results/baseline_rerun.py force          # pin each exam option for the whole battle (menu headroom)
  python results/baseline_rerun.py headroom       # best pin in hindsight per battle, official vs val
  python results/baseline_rerun.py relax          # lift the evidence gate: pin each closed kind, random answers

Rows go to results/rerun/{official,val}.jsonl. The Jev run resumes where it stopped.
Run Jev with the proxy variables unset (see AGENTS.md).
"""
from __future__ import annotations

import json
import sys
import time
from math import comb
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "results"))
sys.path.insert(0, str(ROOT / "src"))
import _regress as R  # noqa: E402
import scenarios as SC  # noqa: E402

OUT = ROOT / "results" / "rerun"
LOCAL = ["dummy", "random", "prog:hand_rules", "online", "value_online", "written_online_grok", "written_online"]
NAMES = {
    "dummy": "Attack-move",
    "random": "Random exam answers",
    "jev": "Jev exam answers",
    "prog:hand_rules": "Hand rules",
    "online": "Lookup (library + nearest cluster)",
    "value_online": "Value switching",
    "written_online_grok": "Grok program",
    "written_online": "Claude program",
}


def _jobs(policies):
    jobs = [("official", (p, None, (m, s))) for p in policies for m in R.MAPS for s in R.SEEDS]
    jobs += [("val", (p, sc, s)) for p in policies for sc in SC.load("val") for s in R.SEEDS]
    return jobs


def _write(bench, row):
    OUT.mkdir(exist_ok=True)
    with (OUT / f"{bench}.jsonl").open("a") as f:
        f.write(json.dumps(row) + "\n")


def _load(bench):
    path = OUT / f"{bench}.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    return {(r["policy"], r["map"], r["seed"]): r for r in rows}


def cmd_local():
    jobs = _jobs(LOCAL)
    have = {b: _load(b) for b in ("official", "val")}
    todo = [(b, j) for b, j in jobs if (j[0], j[1]["id"] if j[1] else j[2][0], j[2] if j[1] else j[2][1]) not in have[b]]
    with Pool(8) as pool:
        rows = pool.map(R._holdout_job, [j for _, j in todo], chunksize=1)
    for (b, j), r in zip(todo, rows):
        r["policy"] = j[0]
        _write(b, r)


def cmd_jev():
    have = {b: _load(b) for b in ("official", "val")}
    for b, (p, sc, s) in _jobs(["jev"]):
        key = ("jev", sc["id"], s) if sc else ("jev", s[0], s[1])
        if key in have[b]:
            continue
        t = time.time()
        r = R._holdout_job((p, sc, s))
        r["policy"], r["wall_s"] = "jev", round(time.time() - t, 1)
        _write(b, r)
        print(b, key[1], key[2], r["win"], r["calls"], r["wall_s"], flush=True)


# Every option Jev's exams could move away from the code default (EXAM_EVIDENCE kinds).
PINS = [
    "force:ranged=!default", "force:melee=!default", "force:bar=!default", "force:wing=!default",
    "force:tie=!default", "force:heal=!default",
] + [f"force:target={r}" for r in ("frontline", "weakest_in_range", "clump", "heaviest", "guns", "healer")]


def cmd_force():
    jobs = _jobs(PINS)
    have = {b: _load(f"force_{b}") for b in ("official", "val")}
    todo = [(b, j) for b, j in jobs if (j[0], j[1]["id"] if j[1] else j[2][0], j[2] if j[1] else j[2][1]) not in have[b]]
    with Pool(8) as pool:
        rows = pool.map(R._holdout_job, [j for _, j in todo], chunksize=4)
    for (b, j), r in zip(todo, rows):
        r["policy"] = j[0]
        _write(f"force_{b}", r)


# Kinds the evidence gate closed (EXAM_EVIDENCE comment), pinned with the gate lifted.
CLOSED = [
    "forceopen:formation=keep", "forceopen:formation=open", "forceopen:kite=all", "forceopen:kite=bait_one",
    "forceopen:bait=bait_one", "forceopen:bait=bait_two", "forceopen:stand=shoot", "forceopen:stand=step",
    "forceopen:mark=!default",
    # Nested kinds open only under a parent pick: kite and stand under ranged=stutter, bait under melee=snipe.
    "forceopen:ranged=stutter", "forceopen:ranged=stutter,kite=all", "forceopen:ranged=stutter,kite=bait_one",
    "forceopen:ranged=stutter,stand=shoot", "forceopen:ranged=stutter,stand=step",
    "forceopen:melee=snipe", "forceopen:melee=snipe,bait=bait_one", "forceopen:melee=snipe,bait=bait_two",
]


def cmd_relax():
    jobs = _jobs(CLOSED + ["random_open"])
    have = {b: _load(f"relax_{b}") for b in ("official", "val")}
    todo = [(b, j) for b, j in jobs if (j[0], j[1]["id"] if j[1] else j[2][0], j[2] if j[1] else j[2][1]) not in have[b]]
    with Pool(8) as pool:
        rows = pool.map(R._holdout_job, [j for _, j in todo], chunksize=4)
    for (b, j), r in zip(todo, rows):
        r["policy"] = j[0]
        _write(f"relax_{b}", r)


def cmd_headroom():
    for bench in ("official", "val"):
        rows = {**_load(bench), **_load(f"force_{bench}"), **_load(f"relax_{bench}")}
        by = {}
        for (p, m, s), r in rows.items():
            by.setdefault(p, {})[(m, s)] = r["win"]
        keys = list(by["dummy"])
        oracle = {k: by["dummy"][k] or any(by[p].get(k) for p in PINS if p in by) for k in keys}
        best_fixed = max((p for p in PINS if p in by), key=lambda p: sum(by[p].values()))
        print(f"\n{bench} ({len(keys)} battles)")
        print(f"  attack-move                         {sum(by['dummy'].values())}")
        print(f"  best single pin for every battle    {sum(by[best_fixed].values())}  ({best_fixed})")
        print(f"  best pin per battle (hindsight)     {sum(oracle.values())}")
        closed = [p for p in CLOSED if p in by]
        if closed:
            both = {k: oracle[k] or any(by[p].get(k) for p in closed) for k in keys}
            print(f"  ... with the closed kinds too       {sum(both.values())}")
            for p in closed:
                f = sum(1 for k in keys if by[p].get(k) and not by["dummy"][k])
                l = sum(1 for k in keys if by["dummy"][k] and not by[p].get(k))
                print(f"    {p:34s}{sum(by[p].values()):4d}  +{f} -{l}")
            if "random_open" in by:
                print(f"  random answers, gate lifted         {sum(by['random_open'].values())}")
        for p in ("random", "jev", "prog:hand_rules"):
            if p in by:
                print(f"  {NAMES[p]:36s}{sum(by[p].values())}")


def _p(f, l):
    n, k = f + l, min(f, l)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n) if n else 1.0


def cmd_table():
    for bench in ("official", "val"):
        rows = _load(bench)
        by = {}
        for (p, m, s), r in rows.items():
            by.setdefault(p, {})[(m, s)] = r["win"]
        print(f"\n{bench}")
        jev = by.get("jev", {})
        for p in ["dummy", "random", "jev", "prog:hand_rules", "online", "value_online", "written_online_grok", "written_online"]:
            if p not in by:
                continue
            line = f"  {NAMES[p]:36s} {sum(by[p].values()):4d}/{len(by[p])}"
            if jev and p != "jev":
                f = sum(1 for k in jev if jev[k] and not by[p].get(k))
                l = sum(1 for k in jev if not jev[k] and by[p].get(k))
                line += f"   Jev exams vs this: +{f} -{l} net {f - l:+d} p={_p(f, l):.3f}"
            print(line)
        calls = [r for (p, _, _), r in rows.items() if p == "jev"]
        if calls:
            n = sum(r["calls"] for r in calls)
            print(f"  Jev: {n} requests, {n / len(calls):.1f} per battle")


if __name__ == "__main__":
    {"local": cmd_local, "jev": cmd_jev, "table": cmd_table, "force": cmd_force, "headroom": cmd_headroom, "relax": cmd_relax}[sys.argv[1]]()
