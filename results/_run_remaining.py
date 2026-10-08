#!/usr/bin/env python3
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "smaclite"))

from macsmac.env import StarCraft2Env
from macsmac.maps import MAP_PARAMS
from macsmac.snapshot import snapshot
from jev_smac_policy import JevActionPolicy

MAPS = [
    "so_many_baneling",
    "1c3s5z",
    "8m_vs_9m",
    "10m_vs_11m",
    "27m_vs_30m",
    "2c_vs_64zg",
    "2s_vs_1sc",
    "3s_vs_3z",
    "8m",
    "3m",
    "25m",
]


def reset_stats(pol: JevActionPolicy) -> None:
    pol.n_calls = 0
    pol.n_fallback = 0
    pol.n_guard = 0
    pol.n_questions = 0
    pol.infer_s = 0.0
    pol.tactic_counts = {}
    pol.plan_counts = {}
    pol.n_override = 0
    pol.overrides = []
    pol.n_asked = 0
    pol.asked_counts = {}
    pol.n_live_prune = 0
    if hasattr(pol.client, "n_calls"):
        pol.client.n_calls = 0
    if hasattr(pol.client, "infer_s"):
        pol.client.infer_s = 0.0


def run_episode(env, pol, map_name):
    env.reset()
    ret = 0.0
    steps = 0
    t0 = time.perf_counter()
    terminated = False
    info = {}
    while not terminated:
        snap = snapshot(env)
        actions = pol.act(map_name, steps, snap)
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


def main():
    pol = JevActionPolicy()
    for map_name in MAPS:
        diff = MAP_PARAMS[map_name]["difficulty"]
        print(f"\n##### {map_name} ({diff}) #####", flush=True)
        reset_stats(pol)
        env = StarCraft2Env(map_name=map_name, seed=1)
        try:
            row = run_episode(env, pol, map_name)
            print(
                f"=== {map_name} win={row['win']} ret={row['return']:.2f} "
                f"steps={row['steps']} {row['seconds']:.1f}s "
                f"calls={pol.n_calls} asked={pol.asked_counts} "
                f"override={pol.n_override} fallback={pol.n_fallback}",
                flush=True,
            )
            print("overrides", pol.overrides[:8], flush=True)
            print("tactics", pol.tactic_counts, flush=True)
        except Exception:
            traceback.print_exc()
            print(f"=== {map_name} CRASH", flush=True)
        finally:
            env.close()
    print("ALL_DONE", flush=True)


if __name__ == "__main__":
    main()
