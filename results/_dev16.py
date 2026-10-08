"""Round 16 dev harness: Claude writes the micro program, the simulator judges it.

    python results/_dev16.py run  <prog.py|empty> --splits train,train2 --seeds 1,2
    python results/_dev16.py cmp  <base.py|empty> <new.py> --splits train,train2 --seeds 1,2

Episodes are cached by (program hash, scenario id, seed) in results/dev16/cache.jsonl,
so re-running the baseline is free. `empty` is the program that overrides nothing
(= ValueOnlinePolicy). Only train / train2 / val are allowed here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "smaclite"))
os.environ.setdefault("JEV_QUIET", "1")

import scenarios as SC  # noqa: E402

DEV = ROOT / "results" / "dev16"
CACHE = DEV / "cache2.jsonl"
EMPTY = "def act(obs, mem):\n    return {}\n"
ALLOWED = {"train", "train2", "val"}
RANGED = {"MARINE", "MARAUDER", "STALKER", "HYDRALISK", "COLOSSUS"}
MELEE = {"ZEALOT", "ZERGLING", "BANELING"}


def _src(path: str) -> str:
    return EMPTY if path == "empty" else Path(path).read_text()


def _h(src: str) -> str:
    return hashlib.md5(src.encode()).hexdigest()[:12]


def _frac(units) -> float:
    tot = sum(u.max_hp + getattr(u, "max_shield", 0) for u in units)
    cur = sum(max(u.hp, 0) + max(getattr(u, "shield", 0), 0) for u in units if u.hp > 0)
    return cur / tot if tot else 0.0


def _kinds(units) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for u in units:
        if u.hp > 0:
            out[u.type.stats.name] = out.get(u.type.stats.name, 0) + 1
    return out


def episode(job: Tuple[str, Dict[str, Any], int]) -> Dict[str, Any]:
    from macsmac.snapshot import snapshot

    import code_policy as CP

    src, scen, seed = job
    env = SC.make_env(scen, seed)
    env.reset()
    pol = CP.CodeActionPolicy(src)
    step, done, info = 0, False, {}
    try:
        while not done:
            _, done, info = env.step(pol.act("dev", step, snapshot(env)))
            step += 1
        ours, theirs = list(env._gym.agents.values()), list(env._gym.enemies.values())
        row = {"h": _h(src), "id": scen["id"], "seed": seed, "win": int(bool(info.get("battle_won"))), "steps": step,
               "ours": round(_frac(ours), 3), "theirs": round(_frac(theirs), 3),
               "a_left": _kinds(ours), "e_left": _kinds(theirs),
               "err": round(pol.error_rate, 3), "ov": pol.overrides, "last_error": pol.last_error}
    finally:
        env.close()
    return row


def _load_cache() -> Dict[Tuple[str, str, int], Dict[str, Any]]:
    out = {}
    if CACHE.is_file():
        for line in CACHE.read_text().splitlines():
            r = json.loads(line)
            out[(r["h"], r["id"], r["seed"])] = r
    return out


def run(path: str, splits: List[str], seeds: List[int]) -> Dict[Tuple[str, int], Dict[str, Any]]:
    assert set(splits) <= ALLOWED, f"dev harness only runs {sorted(ALLOWED)}"
    src = _src(path)
    h = _h(src)
    scens = [s for sp in splits for s in SC.load(sp)]
    cache = _load_cache()
    todo = [(src, s, k) for s in scens for k in seeds if (h, s["id"], k) not in cache]
    if todo:
        DEV.mkdir(parents=True, exist_ok=True)
        with Pool(9) as pool, CACHE.open("a") as f:
            for r in pool.imap_unordered(episode, todo, chunksize=1):
                f.write(json.dumps(r) + "\n")
                f.flush()
                cache[(h, r["id"], r["seed"])] = r
    return {(s["id"], k): cache[(h, s["id"], k)] for s in scens for k in seeds}


def category(s: Dict[str, Any]) -> str:
    ours = set(s["ally"]) - {"MEDIVAC"}
    if ours <= MELEE:
        mine = "our-melee"
    elif ours <= RANGED:
        mine = "our-ranged"
    else:
        mine = "our-mixed"
    th = set(s["enemy"]) - {"MEDIVAC"}
    if "BANELING" in th:
        theirs = "vs-bane"
    elif th & MELEE:
        theirs = "vs-melee"
    else:
        theirs = "vs-ranged"
    return f"{mine}/{theirs}"


def sign_p(a: int, b: int) -> float:
    n, k = a + b, min(a, b)
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def cmp(base: str, new: str, splits: List[str], seeds: List[int]) -> None:
    A, B = run(base, splits, seeds), run(new, splits, seeds)
    scens = {s["id"]: s for sp in splits for s in SC.load(sp)}
    by: Dict[str, List[int]] = {}
    tot = [0, 0, 0, 0]  # base wins, new wins, flips, losses
    dm = 0.0
    for key, a in A.items():
        b = B[key]
        c = by.setdefault(category(scens[key[0]]), [0, 0, 0, 0, 0])
        c[0] += 1
        c[1] += a["win"]
        c[2] += b["win"]
        c[3] += int(b["win"] and not a["win"])
        c[4] += int(a["win"] and not b["win"])
        tot[0] += a["win"]
        tot[1] += b["win"]
        tot[2] += int(b["win"] and not a["win"])
        tot[3] += int(a["win"] and not b["win"])
        dm += (b["ours"] - b["theirs"]) - (a["ours"] - a["theirs"])
    n = len(A)
    print(f"{Path(new).name} vs {Path(base).name} on {'+'.join(splits)} seeds {seeds}: n={n}")
    print(f"  wins {tot[0]} -> {tot[1]} (net {tot[1] - tot[0]:+d}; flips {tot[2]} / losses {tot[3]}; p={sign_p(tot[2], tot[3]):.3f}); "
          f"mean hp-margin delta {dm / n:+.3f}")
    errs = max(r["err"] for r in B.values())
    print(f"  max error rate {errs}; mean overrides/episode {sum(r['ov'] for r in B.values()) / n:.0f}")
    for k in sorted(by):
        c = by[k]
        print(f"  {k:22s} n={c[0]:4d}  {c[1]:4d} -> {c[2]:4d}  (+{c[3]} / -{c[4]})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "cmp"])
    ap.add_argument("progs", nargs="+")
    ap.add_argument("--splits", default="train,train2")
    ap.add_argument("--seeds", default="1,2")
    a = ap.parse_args()
    splits = a.splits.split(",")
    seeds = [int(x) for x in a.seeds.split(",")]
    if a.cmd == "run":
        for p in a.progs:
            rows = run(p, splits, seeds)
            print(p, sum(r["win"] for r in rows.values()), "/", len(rows))
    else:
        cmp(a.progs[0], a.progs[1], splits, seeds)


if __name__ == "__main__":
    main()
