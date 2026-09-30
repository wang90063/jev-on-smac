"""Can Jev tell a clearly better program from a clearly worse one?

For each held-out scenario, every search macro runs as a constant program on
5 seeds (offline). Where the best and worst macro differ by >= GAP wins, Jev
sees the start state and the two programs (random order, described only by
what they make code do) and picks one. Chance is 50%.

    python jev_probe.py macros test2     # local: constant-macro wins per scenario
    python jev_probe.py ask test2        # TypeSafe API: Jev picks
"""

from __future__ import annotations

import json
import os
import random
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))
os.environ.setdefault("JEV_QUIET", "1")

import scenarios as SC  # noqa: E402
import search as SE  # noqa: E402
import tactic_dsl as T  # noqa: E402

OUT = ROOT / "results" / "jev_probe"
GAP = 3


def _macro_spec(name: str) -> str:
    import forge as F

    prog = SE.MACROS[name]
    if prog is None:
        return "dummy"
    return "prog:" + F._prog_path(dict(prog, name=name))


def _job(a):
    import _regress as R

    name, scen, seed = a
    return name, scen["id"], R.run_scenario(_macro_spec(name), scen, seed)["win"]


def cmd_macros(split: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    scens = SC.load(split)
    jobs = [(m, s, k) for s in scens for m in SE.MACROS for k in (1, 2, 3, 4, 5)]
    with Pool(8) as pool:
        rows = pool.map(_job, jobs, chunksize=4)
    wins = {}
    for m, sid, w in rows:
        wins.setdefault(sid, {}).setdefault(m, 0)
        wins[sid][m] += w
    (OUT / f"{split}_macros.json").write_text(json.dumps(wins, indent=1))
    clear = sum(1 for v in wins.values() if max(v.values()) - min(v.values()) >= GAP)
    print(f"{len(wins)} scenarios, {clear} with a best-worst gap >= {GAP}")


def describe(name: str) -> str:
    prog = SE.MACROS[name]
    if prog is None:
        return "No program: attack-move with the code-default target rule."
    return T.summarize(prog)


def cmd_ask(split: str) -> None:
    import forge as F
    from jev_api import JevClient

    wins = json.loads((OUT / f"{split}_macros.json").read_text())
    scens = {s["id"]: s for s in SC.load(split)}
    client = JevClient()
    rng = random.Random(20260930)
    rows = []
    for sid, w in sorted(wins.items()):
        good = max(w, key=lambda m: (w[m], m == "none"))
        bad = min(w, key=lambda m: (w[m], m != "none"))
        if w[good] - w[bad] < GAP or describe(good) == describe(bad):
            continue
        pair = [good, bad]
        rng.shuffle(pair)
        labels = {"P1": pair[0], "P2": pair[1]}
        state = F.start_state(scens[sid])
        questions = {
            "program": {
                "type": "choice",
                "instructions": (
                    "Which tactic program should the army run for this fight? Each program sets "
                    "exam picks from physical conditions; code moves the units."
                ),
                "criteria": {lab: {"does": describe(m)} for lab, m in labels.items()},
            }
        }
        res = client.system_one(state, questions)
        ans = ((res or {}).get("answers") or {}).get("program") or {}
        pick = ans.get("choice") if isinstance(ans, dict) else ans
        chosen = labels.get(pick)
        rows.append({"id": sid, "good": good, "bad": bad, "gap": w[good] - w[bad], "jev": chosen, "correct": chosen == good})
        print(sid, good, w[good], bad, w[bad], "->", chosen, flush=True)
    (OUT / f"{split}_ask.json").write_text(json.dumps(rows, indent=1))
    n = len([r for r in rows if r["jev"]])
    k = sum(r["correct"] for r in rows)
    from math import comb

    p = sum(comb(n, i) for i in range(k, n + 1)) / 2 ** n if n else 1.0
    print(f"Jev picked the better program {k}/{n}; one-sided p vs chance = {p:.4f}; calls ok {client.n_calls} fail {client.n_fail}")


if __name__ == "__main__":
    cmd, split = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "test2"
    {"macros": cmd_macros, "ask": cmd_ask}[cmd](split)
