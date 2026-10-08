#!/usr/bin/env python3
"""One scoreboard: every tactic-level system on the same battles, current code.

  python results/baseline_rerun.py local          # all non-Jev systems, official maps + val (parallel, minutes)
  python results/baseline_rerun.py jev            # Jev exam answers (card 4), official maps + val (serial, network)
  python results/baseline_rerun.py table          # win counts + paired sign tests vs Jev exam answers

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
    {"local": cmd_local, "jev": cmd_jev, "table": cmd_table}[sys.argv[1]]()
