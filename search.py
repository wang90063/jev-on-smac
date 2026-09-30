"""Offline search ceiling: switch between macro programs with look-ahead.

Every DECIDE steps, each macro is tried on a deep copy of the env and the
policy for HORIZON steps and scored; the best one runs for DECIDE steps.
This clones simulator state, so it is an offline measuring stick and a
teacher for distillation only. Nothing online may do this.

    python search.py train        # ceiling + decision log on train, seeds 1-5
"""

from __future__ import annotations

import copy
import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "smaclite"))
os.environ.setdefault("JEV_QUIET", "1")

import jev_smac_policy as J  # noqa: E402
import scenarios as SC  # noqa: E402
import tactic_dsl as T  # noqa: E402
from macsmac.snapshot import snapshot  # noqa: E402

DECIDE = 5
HORIZON = 12
OUT_DIR = ROOT / "results" / "search"


def _open(st: Dict[str, str]) -> Dict[str, Any]:
    return {"menu": "open", "rules": [], "else": st}


# name -> program; None means the exact Dummy path.
MACROS: Dict[str, Optional[Dict[str, Any]]] = {
    "none": None,
    "stutter": _open({"ranged": "stutter"}),
    "hold": _open({"ranged": "hold", "melee": "hold"}),
    "fall_back": _open({"ranged": "fall_back", "melee": "hold_choke"}),
    "hold_choke": _open({"melee": "hold_choke"}),
    "spread": _open({"formation": "open"}),
    "threat": _open({"target": "threat"}),
    "guns": _open({"target": "guns"}),
    "rotate": _open({"wounded": "rotate"}),
    "concave": _open({"ranged": "concave"}),
    "kite_combo": _open({"ranged": "stutter", "wounded": "rotate", "target": "threat"}),
    "hand": dict(T.HAND_RULES),
}


class MacroPolicy(J.LibraryPolicy):
    """A policy whose macro is set from outside; never picks on its own."""

    def __init__(self):
        super().__init__([], chooser="nearest", fallback=False, tag="search")

    def set_macro(self, name: str) -> None:
        prog = MACROS[name]
        self._run(None if prog is None else {"program": dict(prog, name=name)})

    def act(self, map_name: str, step: int, snap: Dict[str, Any]) -> List[int]:
        return J.JevActionPolicy.act(self, map_name, step, snap)


def _ehp_sum(units) -> float:
    return sum(float(u.hp) + float(getattr(u, "shield", 0) or 0) for u in units if getattr(u, "hp", 0) > 0)


def _value(env, a0: float, e0: float, done: bool, info: Dict[str, Any]) -> float:
    a = _ehp_sum(env._gym.agents.values()) / max(a0, 1.0)
    e = _ehp_sum(env._gym.enemies.values()) / max(e0, 1.0)
    if done:
        return (10.0 + a) if info.get("battle_won") else (-10.0 - e)
    return a - e


def _advance(env, pol, step: int, n: int) -> Tuple[int, bool, Dict[str, Any]]:
    done, info = False, {}
    for _ in range(n):
        acts = pol.act("search", step, snapshot(env))
        _, done, info = env.step(acts)
        step += 1
        if done:
            break
    return step, done, info


def search_episode(job: Tuple[Dict[str, Any], int]) -> Dict[str, Any]:
    scen, seed = job
    env = SC.make_env(scen, seed)
    env.reset()
    pol = MacroPolicy()
    a0, e0 = _ehp_sum(env._gym.agents.values()), _ehp_sum(env._gym.enemies.values())
    step, done, info = 0, False, {}
    log: List[Dict[str, Any]] = []
    try:
        while not done:
            snap = snapshot(env)
            state = J.commander_state(step, dict(snap), list(pol._recent), pol._hp_trend)
            scores = {}
            for name in MACROS:
                e2, p2 = copy.deepcopy(env), copy.deepcopy(pol)
                p2.set_macro(name)
                _, d2, i2 = _advance(e2, p2, step, HORIZON)
                scores[name] = round(_value(e2, a0, e0, d2, i2), 4)
                e2.close()
            # Ties go to "none" so the teacher only departs from Dummy for a reason.
            best = max(MACROS, key=lambda n: (scores[n], n == "none"))
            log.append({"step": step, "feats": T.features(state), "pick": best, "scores": scores})
            pol.set_macro(best)
            step, done, info = _advance(env, pol, step, DECIDE)
    finally:
        env.close()
    return {"id": scen["id"], "seed": seed, "win": int(bool(info.get("battle_won"))), "steps": step, "log": log}


def cmd_train(split: str = "train") -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    scens = SC.load(split)
    jobs = [(s, k) for s in scens for k in (1, 2, 3, 4, 5)]
    with Pool(8) as pool:
        rows = pool.map(search_episode, jobs, chunksize=1)
    (OUT_DIR / f"{split}.json").write_text(json.dumps(rows))
    wins = sum(r["win"] for r in rows)
    picks: Dict[str, int] = {}
    for r in rows:
        for d in r["log"]:
            picks[d["pick"]] = picks.get(d["pick"], 0) + 1
    print(f"search ceiling on {split}: {wins}/{len(rows)}")
    print("macro picks:", dict(sorted(picks.items(), key=lambda kv: -kv[1])))


if __name__ == "__main__":
    cmd_train(sys.argv[2] if len(sys.argv) > 2 else "train") if sys.argv[1:2] == ["train"] else print(__doc__)
