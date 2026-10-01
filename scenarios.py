"""Procedural SMAClite scenarios for held-out evaluation.

A scenario is a spec (unit mix per side, terrain, spawn layout, limit).
`materialize(spec, seed)` writes a map JSON with spawn jitter so different
seeds are different fights. Specs never carry an official map name.

    python scenarios.py build     # generate, filter, split -> results/scenarios/{train,test}.json
"""

from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "smaclite"))
os.environ.setdefault("JEV_QUIET", "1")

OUT = ROOT / "results" / "scenarios"
CACHE = OUT / "maps"

# Rough mineral+gas value, only to keep the two sides in the same weight class.
COST = {
    "MARINE": 50, "MARAUDER": 125, "MEDIVAC": 200, "STALKER": 175, "ZEALOT": 100,
    "COLOSSUS": 400, "ZERGLING": 25, "BANELING": 50, "HYDRALISK": 150,
}
FIGHTERS = ["MARINE", "MARAUDER", "STALKER", "ZEALOT", "COLOSSUS", "ZERGLING", "BANELING", "HYDRALISK"]
CAP = {"COLOSSUS": 3, "MEDIVAC": 2}
SHIELDED = {"STALKER", "ZEALOT", "COLOSSUS"}

# Spawn layouts that are walkable, taken from the engine's own presets.
LAYOUTS = {
    "open": {"terrain": ["ALL_GREEN", "SIMPLE"], "ally": (9, 16), "enemy": (23, 16), "ap": "ally"},
    "wall_gap": {"terrain": ["NARROW"], "ally": (9, 16), "enemy": (23, 16), "ap": "ally"},
    "ravine": {"terrain": ["RAVINE"], "ally": (16, 16), "enemy": (16, 9), "ap": "ally"},
    "octagon": {"terrain": ["OCTAGON"], "ally": (16, 10), "enemy": (16, 22), "ap": "ally"},
    "corridor": {"terrain": ["CORRIDOR"], "ally": (19.04, 19.12), "enemy": (27.91, 28.24), "ap": (4.47, 4.33)},
}
LAYOUT_WEIGHTS = {"open": 5, "wall_gap": 2, "ravine": 1, "octagon": 1, "corridor": 1}
JITTER = 1.5


def _army(rng: random.Random, budget: float) -> Dict[str, int]:
    kinds = rng.sample(FIGHTERS, rng.choice([1, 1, 2, 2, 3]))
    if any(k in kinds for k in ("MARINE", "MARAUDER")) and rng.random() < 0.3:
        kinds.append("MEDIVAC")
    weights = [rng.uniform(0.5, 1.5) for _ in kinds]
    army: Dict[str, int] = {}
    for k, w in zip(kinds, weights):
        share = budget * w / sum(weights)
        n = max(1, int(round(share / COST[k])))
        army[k] = min(n, CAP.get(k, 40))
    return army


def _count(army: Dict[str, int]) -> int:
    return sum(army.values())


def _value(army: Dict[str, int]) -> int:
    return sum(COST[k] * n for k, n in army.items())


def random_spec(rng: random.Random, idx: int, prefix: str = "g") -> Optional[Dict[str, Any]]:
    layout = rng.choices(list(LAYOUT_WEIGHTS), weights=list(LAYOUT_WEIGHTS.values()))[0]
    budget = rng.uniform(300, 2400)
    ally = _army(rng, budget)
    enemy = _army(rng, budget * rng.uniform(0.8, 1.3))
    if not (2 <= _count(ally) <= 30 and 1 <= _count(enemy) <= 40):
        return None
    if set(ally) <= {"MEDIVAC"} or set(enemy) <= {"MEDIVAC"}:
        return None
    return {
        "id": f"{prefix}{idx:04d}",
        "layout": layout,
        "terrain": rng.choice(LAYOUTS[layout]["terrain"]),
        "ally": ally,
        "enemy": enemy,
        "limit": 150 if _count(ally) + _count(enemy) < 40 else 220,
        "value_ratio": round(_value(ally) / max(_value(enemy), 1), 2),
    }


def materialize(spec: Dict[str, Any], seed: int) -> Path:
    """Write the map JSON for (spec, seed); spawns jittered by the seed."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{spec['id']}_s{seed}.json"
    if path.is_file():
        return path
    rng = random.Random(f"{spec['id']}:{seed}")
    lay = LAYOUTS[spec["layout"]]
    jit = 0.0 if seed == 0 else JITTER
    ax, ay = lay["ally"][0] + rng.uniform(-jit, jit), lay["ally"][1] + rng.uniform(-jit, jit)
    ex, ey = lay["enemy"][0] + rng.uniform(-jit, jit), lay["enemy"][1] + rng.uniform(-jit, jit)
    ap = [round(ax, 2), round(ay, 2)] if lay["ap"] == "ally" else list(lay["ap"])
    info = {
        "name": spec["id"],
        "num_allied_units": _count(spec["ally"]),
        "num_enemy_units": _count(spec["enemy"]),
        "groups": [
            {"x": round(ax, 2), "y": round(ay, 2), "faction": "ALLY", "units": spec["ally"]},
            {"x": round(ex, 2), "y": round(ey, 2), "faction": "ENEMY", "units": spec["enemy"]},
        ],
        "attack_point": ap,
        "terrain_preset": spec["terrain"],
        "num_unit_types": 0,
        # The engine's obs divides by max_shield when this flag is on, so it
        # must be all-or-nothing per side. Shields still work in combat.
        "ally_has_shields": all(k in SHIELDED for k in spec["ally"]),
        "enemy_has_shields": all(k in SHIELDED for k in spec["enemy"]),
    }
    path.write_text(json.dumps(info))
    return path


def make_env(spec: Dict[str, Any], seed: int):
    from macsmac.env import StarCraft2Env

    return StarCraft2Env(map_name=spec["id"], map_file=str(materialize(spec, seed)), limit=spec["limit"], seed=seed)


def spawn_ok(spec: Dict[str, Any], seed: int = 1) -> bool:
    """Every unit starts on walkable ground. Terrain rows are T[y][x]."""
    env = make_env(spec, seed)
    try:
        env.reset()
        g = env._gym
        T = g.map_info.terrain
        h, w = len(T), len(T[0])
        for u in g.all_units.values():
            x, y = int(u.pos[0]), int(u.pos[1])
            if not (0 <= x < w and 0 <= y < h):
                return False
            if T[y][x].name == "NONE":
                return False
        return True
    except Exception:
        return False
    finally:
        env.close()


# --- building the split -----------------------------------------------------

SEEDS = [1, 2, 3, 4, 5]


def _probe(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Dummy and a random-answer client, 5 jittered seeds each."""
    sys.path.insert(0, str(ROOT / "results"))
    import _regress as R

    try:
        d = [R.run_scenario("dummy", spec, s)["win"] for s in SEEDS]
        r = [R.run_scenario("random", spec, s)["win"] for s in SEEDS]
    except Exception as exc:  # a crash here is a policy bug worth reading
        import traceback

        return {"id": spec["id"], "error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()[-800:]}
    return {"id": spec["id"], "dummy": sum(d), "random": sum(r)}


def build(n_candidates: int = 900, n_train: int = 60, n_test: int = 40, seed: int = 20260929) -> None:
    from multiprocessing import Pool

    rng = random.Random(seed)
    specs: List[Dict[str, Any]] = []
    i = 0
    while len(specs) < n_candidates:
        spec = random_spec(rng, i)
        i += 1
        if spec is not None:
            specs.append(spec)
    specs = [s for s in specs if spawn_ok(s)]
    print(f"{len(specs)} candidates with clean spawns", flush=True)
    with Pool(8) as pool:
        probes = pool.map(_probe, specs, chunksize=4)
    errors = [p for p in probes if "error" in p]
    if errors:
        (OUT / "probe_errors.json").parent.mkdir(parents=True, exist_ok=True)
        (OUT / "probe_errors.json").write_text(json.dumps(errors, indent=1))
        print(f"{len(errors)} scenarios crashed the policy; see probe_errors.json", flush=True)
    by_id = {p["id"]: p for p in probes if "error" not in p}
    specs = [s for s in specs if s["id"] in by_id]
    # Contested: Dummy does not win every seed, and something wins at least once.
    keep = [s for s in specs if by_id[s["id"]]["dummy"] <= 4 and max(by_id[s["id"]]["dummy"], by_id[s["id"]]["random"]) >= 1]
    for s in keep:
        s["probe"] = {k: by_id[s["id"]][k] for k in ("dummy", "random")}
    rng.shuffle(keep)
    print(f"{len(keep)} contested scenarios", flush=True)
    train, test = keep[:n_train], keep[n_train:n_train + n_test]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "train.json").write_text(json.dumps(train, indent=1))
    (OUT / "test.json").write_text(json.dumps(test, indent=1))
    print(f"train={len(train)} test={len(test)} -> {OUT}")


def build_extra(name: str, n: int, seed: int, prefix: str, n_candidates: int = 700) -> None:
    """A further frozen held-out split, same generator and filter, new ids."""
    from multiprocessing import Pool

    rng = random.Random(seed)
    specs: List[Dict[str, Any]] = []
    i = 0
    while len(specs) < n_candidates:
        spec = random_spec(rng, i, prefix)
        i += 1
        if spec is not None:
            specs.append(spec)
    specs = [s for s in specs if spawn_ok(s)]
    with Pool(8) as pool:
        probes = pool.map(_probe, specs, chunksize=4)
    by_id = {p["id"]: p for p in probes if "error" not in p}
    keep = [s for s in specs if s["id"] in by_id and by_id[s["id"]]["dummy"] <= 4
            and max(by_id[s["id"]]["dummy"], by_id[s["id"]]["random"]) >= 1]
    for s in keep:
        s["probe"] = {k: by_id[s["id"]][k] for k in ("dummy", "random")}
    rng.shuffle(keep)
    out = keep[:n]
    (OUT / f"{name}.json").write_text(json.dumps(out, indent=1))
    print(f"{name}={len(out)} (from {len(keep)} contested) -> {OUT}")


def load(split: str) -> List[Dict[str, Any]]:
    return json.loads((OUT / f"{split}.json").read_text())


if __name__ == "__main__":
    if sys.argv[1:2] == ["build"]:
        build()
    elif sys.argv[1:2] == ["build_test2"]:
        build_extra("test2", 120, seed=20260930, prefix="h")
    elif sys.argv[1:2] == ["build_test4"]:
        build_extra("test4", 200, seed=20261004, prefix="w", n_candidates=1100)
    elif sys.argv[1:2] == ["build_test5"]:
        build_extra("test5", 200, seed=20261005, prefix="x", n_candidates=1100)
    elif sys.argv[1:2] == ["build_val"]:
        build_extra("val", 80, seed=20261001, prefix="v", n_candidates=500)
