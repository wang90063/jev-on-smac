"""Offline tactic forge: DeepSeek writes programs, the simulator judges them.

Per train scenario: R rounds of (propose K programs -> validate -> 5 jittered
seeds each -> feedback). The best program that beats Dummy goes into the
library with its start features. Then every library program is run on every
train scenario so each entry knows where it transfers.

The simulator is used only here, offline. Nothing in play clones state.

    python forge.py forge      # needs DeepSeek (run outside sandbox, no proxy)
    python forge.py transfer   # local only
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))
sys.path.insert(0, str(ROOT / "smaclite"))
os.environ.setdefault("JEV_QUIET", "1")

import scenarios as SC  # noqa: E402
import tactic_dsl as T  # noqa: E402

FORGE_DIR = ROOT / "results" / "forge"
LIB_PATH = ROOT / "kb" / "library" / "programs.json"
PROG_DIR = Path(tempfile.gettempdir()) / "jev_forge_progs"
SEEDS = [1, 2, 3, 4, 5]
ROUNDS = 4
K = 6
UNIT_DIR = ROOT / "smaclite" / "smaclite" / "env" / "units" / "smaclite_units"


# --- evaluation -------------------------------------------------------------

def _prog_path(prog: Dict[str, Any]) -> str:
    PROG_DIR.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(prog, sort_keys=True)
    import hashlib

    path = PROG_DIR / (hashlib.md5(blob.encode()).hexdigest()[:12] + ".json")
    if not path.is_file():
        path.write_text(blob)
    return str(path)


def _episode(job: Tuple[str, Dict[str, Any], int]) -> Dict[str, Any]:
    import _regress as R

    spec, scen, seed = job
    return R.run_scenario(spec, scen, seed)


def evaluate(pool: Pool, specs: List[str], scen: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Run each policy spec on the scenario's seeds. Returns one summary per spec."""
    jobs = [(sp, scen, s) for sp in specs for s in SEEDS]
    rows = pool.map(_episode, jobs, chunksize=1)
    out = []
    for i, sp in enumerate(specs):
        rs = rows[i * len(SEEDS):(i + 1) * len(SEEDS)]
        wins = sum(r["win"] for r in rs)
        margin = sum(r["A"][1] - r["E"][1] for r in rs) / len(rs)
        out.append({"spec": sp, "wins": wins, "margin": round(margin, 1), "rows": rs})
    return out


def score(summary: Dict[str, Any]) -> float:
    return summary["wins"] * 10000 + summary["margin"]


def failure_note(summary: Dict[str, Any]) -> str:
    rs = summary["rows"]
    lost = [r for r in rs if not r["win"]]
    if not lost:
        return "won every seed"
    r = lost[0]
    return (
        f"lost {len(lost)}/{len(rs)}; e.g. after {r['steps']} steps we had {r['A'][0]} units "
        f"({r['A'][1]} hp) left, enemy {r['E'][0]} units ({r['E'][1]} hp)"
    )


# --- scenario description ---------------------------------------------------

def _unit_stats(kinds: List[str]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for k in kinds:
        d = json.loads((UNIT_DIR / f"{k.lower()}.json").read_text())
        out[k.lower()] = {
            key: d.get(key) for key in ("hp", "shield", "armor", "damage", "cooldown", "speed", "attack_range", "bonuses")
            if d.get(key) is not None
        }
    return out


def start_state(scen: Dict[str, Any]) -> Dict[str, Any]:
    """commander_state at tick 0 (seed 0 = no jitter)."""
    import jev_smac_policy as J
    from macsmac.snapshot import snapshot

    env = SC.make_env(scen, 0)
    try:
        env.reset()
        snap = snapshot(env)
        pol = J.DummyActionPolicy()
        pol.act(scen["id"], 0, snap)
        return J.commander_state(0, snap, [], "no_trade_yet")
    finally:
        env.close()


def describe_scenario(scen: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    kinds = sorted(set(scen["ally"]) | set(scen["enemy"]))
    return {
        "our_army": {k.lower(): n for k, n in scen["ally"].items()},
        "enemy_army": {k.lower(): n for k, n in scen["enemy"].items()},
        "unit_stats": _unit_stats(kinds),
        "terrain": {
            "open": "open field",
            "wall_gap": "a wall between the armies with one gap in the middle (a choke)",
            "ravine": "a ravine split by a long wall",
            "octagon": "an enclosed octagon arena",
            "corridor": "a long diagonal corridor; our rally point is far behind us",
        }[scen["layout"]],
        "start_features": T.features(state),
        "situation": state.get("situation"),
    }


# --- the writer ---------------------------------------------------------------

INSTRUCTIONS = (
    "You design tactic programs for a StarCraft II micro-battle simulator. "
    "Code executes all unit movement; a program only decides, tick by tick, which "
    "named pick each exam takes, based on physical features. "
    "Output one JSON object only, no markdown: "
    '{"programs": [{"name": str, "why": str, "rules": [{"when": {...}, "set": {...}}], "else": {...}}]}. '
    "Rules are checked in order; the first rule whose every condition holds is merged over `else`. "
    "Use only the listed features, values and picks. A numeric feature takes a number or "
    '{">=": n} style tests. Keep each program under 6 rules. Make the programs genuinely '
    "different from each other: different ideas, not small variations."
)


def writer_prompt(desc: Dict[str, Any], neighbors: List[Dict[str, Any]], history: List[Dict[str, Any]], k: int) -> str:
    parts = {
        "task": f"Write {k} programs that make our army win this fight.",
        "fight": desc,
        "dsl": {"features": T.FEATURES, "picks": T.pick_meanings(), "notes": T.NOTES},
        "programs_that_won_similar_fights": [
            {"program": n["program"], "won": f"{n['wins']}/5 on its own fight"} for n in neighbors
        ],
        "your_earlier_attempts_on_this_fight": [
            {"program": h["program"], "result": h["note"]} for h in history[-8:]
        ],
    }
    return json.dumps(parts, ensure_ascii=False)


def propose(client, desc, neighbors, history, k: int) -> Tuple[List[Dict[str, Any]], List[str]]:
    reply = client.fill_json(
        INSTRUCTIONS, writer_prompt(desc, neighbors, history, k), timeout=90, max_tokens=4000, temperature=0.8
    )
    progs, errs = [], []
    for raw in (reply or {}).get("programs") or []:
        clean, e = T.validate(raw)
        if e:
            errs.append(f"{(raw or {}).get('name')}: {e[0]}")
        if clean and (clean["rules"] or clean["else"]):
            progs.append(clean)
    if reply is None:
        errs.append("writer returned nothing")
    return progs, errs


# --- commands -----------------------------------------------------------------

def load_lib() -> List[Dict[str, Any]]:
    return json.loads(LIB_PATH.read_text()) if LIB_PATH.is_file() else []


def save_lib(lib: List[Dict[str, Any]]) -> None:
    LIB_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIB_PATH.write_text(json.dumps(lib, indent=1, ensure_ascii=False))


def cmd_forge(limit: Optional[int] = None) -> None:
    from system2_api import System2Client

    client = System2Client(timeout=90)
    FORGE_DIR.mkdir(parents=True, exist_ok=True)
    train = SC.load("train")[:limit] if limit else SC.load("train")
    lib = load_lib()
    with Pool(8) as pool:
        for scen in train:
            out_path = FORGE_DIR / f"{scen['id']}.json"
            if out_path.is_file():
                continue
            state = start_state(scen)
            desc = describe_scenario(scen, state)
            vec = T.feature_vector(T.features(state))
            base = {b["spec"]: b for b in evaluate(pool, ["dummy", "prog:hand_rules"], scen)}
            dummy_w = base["dummy"]["wins"]
            history: List[Dict[str, Any]] = []
            best: Optional[Dict[str, Any]] = None
            log = {"id": scen["id"], "dummy": dummy_w, "hand_rules": base["prog:hand_rules"]["wins"], "rounds": []}
            for rnd in range(ROUNDS):
                neighbors = T.nearest(lib, vec, 3)
                progs, errs = propose(client, desc, neighbors, history, K)
                specs = ["prog:" + _prog_path(p) for p in progs]
                results = evaluate(pool, specs, scen) if specs else []
                rlog = {"round": rnd, "errors": errs, "programs": []}
                for p, r in zip(progs, results):
                    note = failure_note(r)
                    history.append({"program": p, "note": f"{r['wins']}/5 wins; {note}", "score": score(r)})
                    rlog["programs"].append({"program": p, "wins": r["wins"], "margin": r["margin"]})
                    if best is None or score(r) > best["score"]:
                        best = {"program": p, "wins": r["wins"], "margin": r["margin"], "score": score(r)}
                history.sort(key=lambda h: h["score"])
                log["rounds"].append(rlog)
                print(
                    f"{scen['id']} r{rnd} dummy={dummy_w} hand={log['hand_rules']} "
                    f"got={[x['wins'] for x in rlog['programs']]} err={len(errs)} best={best and best['wins']}",
                    flush=True,
                )
                if best and best["wins"] == 5:
                    break
            log["best"] = best
            if best and best["wins"] > dummy_w:
                lib.append({
                    "id": f"L{len(lib):03d}",
                    "program": best["program"],
                    "origin": scen["id"],
                    "wins": best["wins"],
                    "dummy": dummy_w,
                    "feats": T.features(state),
                    "vec": vec,
                    "transfer": {},
                })
                save_lib(lib)
            out_path.write_text(json.dumps(log, indent=1, ensure_ascii=False))
    print(f"library size {len(lib)}; writer calls {client.n_calls} fails {client.n_fail}")


def cmd_transfer() -> None:
    """Run every library program on every train scenario; record wins vs Dummy."""
    lib = load_lib()
    train = SC.load("train")
    with Pool(8) as pool:
        for scen in train:
            specs = ["dummy"] + ["prog:" + _prog_path(e["program"]) for e in lib]
            res = evaluate(pool, specs, scen)
            d = res[0]["wins"]
            for e, r in zip(lib, res[1:]):
                e["transfer"][scen["id"]] = {"wins": r["wins"], "dummy": d}
            print(scen["id"], "dummy", d, "lib", [r["wins"] for r in res[1:]], flush=True)
    save_lib(lib)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "forge":
        cmd_forge(int(sys.argv[2]) if len(sys.argv) > 2 else None)
    elif cmd == "transfer":
        cmd_transfer()
    else:
        print(__doc__)
