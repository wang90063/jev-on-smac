#!/usr/bin/env python3
"""Run a policy on Mac research SMAC. No StarCraft II install required."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from macsmac.env import StarCraft2Env
from macsmac.maps import MAP_PARAMS, list_maps
from macsmac.snapshot import snapshot


def _closest_policy(map_name, step, snap):
    actions = []
    for i, ally in enumerate(snap["allies"]):
        row = snap["avail"][i]
        if not ally.get("alive"):
            actions.append(0)
            continue
        attack = [j for j, v in enumerate(row) if j >= 6 and v]
        if attack:
            actions.append(attack[0])
            continue
        if len(row) > 1 and row[1]:
            actions.append(1)
        else:
            actions.append(int(max(range(len(row)), key=lambda k: row[k])))
    return actions



def _load_policy(name: str):
    if name == "closest":
        return _closest_policy, None
    if name == "script":
        from jev_smac_policy import ScriptActionPolicy

        pol = ScriptActionPolicy()
        return pol.act, pol
    if name == "jev":
        from jev_smac_policy import JevActionPolicy

        pol = JevActionPolicy()
        return pol.act, pol
    if name == "api":
        from jev_smac_policy import ApiActionPolicy

        pol = ApiActionPolicy()
        return pol.act, pol
    if name == "dummy":
        from jev_smac_policy import DummyActionPolicy

        pol = DummyActionPolicy()
        return pol.act, pol
    if name == "force":
        from jev_smac_policy import ForceActionPolicy

        pol = ForceActionPolicy({"ranged": "peel"})
        return pol.act, pol
    raise ValueError(f"unknown policy {name}")


def run_episode(env: StarCraft2Env, policy, map_name: str) -> dict:
    env.reset()
    ret = 0.0
    steps = 0
    t0 = time.perf_counter()
    terminated = False
    info = {}
    while not terminated:
        snap = snapshot(env)
        actions = policy(map_name, steps, snap)
        reward, terminated, info = env.step(actions)
        ret += float(reward)
        steps += 1
        if steps > env.episode_limit + 5:
            break
    return {
        "win": int(bool(info.get("battle_won"))),
        "return": ret,
        "steps": steps,
        "seconds": time.perf_counter() - t0,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Mac research SMAC (SMAClite engine)")
    p.add_argument("--maps", nargs="+", default=["3m"])
    p.add_argument("--episodes", type=int, default=1)
    p.add_argument("--policy", default="closest", choices=["closest", "jev", "script", "api", "dummy", "force"])
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--list", action="store_true")
    args = p.parse_args(argv)
    if args.list:
        for name, spec in MAP_PARAMS.items():
            print(f"{name:16s} {spec['difficulty']:12s} limit={spec['limit']}")
        return 0
    policy, jev_pol = _load_policy(args.policy)
    rows = []
    for map_name in args.maps:
        if map_name not in MAP_PARAMS:
            print(f"skip unknown map {map_name}", flush=True)
            continue
        print(f"\n===== macsmac {map_name} ({MAP_PARAMS[map_name]['difficulty']}) =====", flush=True)
        env = StarCraft2Env(map_name=map_name, seed=args.seed)
        print("env", env.get_env_info(), flush=True)
        try:
            wins = 0
            for ep in range(args.episodes):
                row = run_episode(env, policy, map_name)
                wins += row["win"]
                print(
                    f"{map_name:16s} {args.policy} ep {ep + 1:02d}/{args.episodes} "
                    f"win={row['win']} ret={row['return']:.2f} steps={row['steps']} "
                    f"{row['seconds']:.1f}s",
                    flush=True,
                )
                rows.append({"map": map_name, "policy": args.policy, **row})
            print(
                f"{map_name:16s} winrate={wins}/{args.episodes} "
                f"({100.0 * wins / max(args.episodes, 1):.0f}%)",
                flush=True,
            )
            if jev_pol is not None and hasattr(jev_pol, "n_calls"):
                print(
                    f"{map_name:16s} jev_calls={jev_pol.n_calls} questions={jev_pol.n_questions} "
                    f"fallback={jev_pol.n_fallback} plans={getattr(jev_pol, 'plan_counts', {})}",
                    flush=True,
                )
        finally:
            env.close()
    out = ROOT / "results" / "macsmac_last.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
