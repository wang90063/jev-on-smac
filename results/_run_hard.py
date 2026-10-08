#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "smaclite"))
os.environ["JEV_QUIET"] = "1"

from macsmac.env import StarCraft2Env
from macsmac.snapshot import snapshot
from jev_smac_policy import DummyActionPolicy, ForceActionPolicy, JevActionPolicy


REMAINING = ["so_many_baneling", "MMM2", "2m_vs_1z", "6h_vs_8z"]
REGRESS = ["bane_vs_bane", "3s_vs_5z", "3s5z_vs_3s6z", "3m", "MMM"]


def reset_pol(pol):
    pol.asked_counts = {}
    pol.n_override = 0
    pol.overrides = []
    pol.n_calls = 0
    pol.n_asked = 0
    pol.n_fallback = 0
    pol.n_questions = 0
    pol.n_live_prune = 0
    pol.tactic_counts = {}
    if hasattr(pol.client, "n_calls"):
        pol.client.n_calls = 0
    if hasattr(pol.client, "infer_s"):
        pol.client.infer_s = 0.0


def leftover(env):
    allies = [env.get_unit_by_id(i) for i in range(env.n_agents)]
    enemies = [env.enemies.get(i) for i in range(env.n_enemies)]
    a_live = [u for u in allies if u is not None and getattr(u, "hp", 0) > 0]
    e_live = [u for u in enemies if u is not None and getattr(u, "hp", 0) > 0]
    a_hp = sum(float(u.hp) + float(getattr(u, "shield", 0) or 0) for u in a_live)
    e_hp = sum(float(u.hp) + float(getattr(u, "shield", 0) or 0) for u in e_live)
    return len(a_live), a_hp, len(e_live), e_hp


def run(pol, map_name, seed=1):
    env = StarCraft2Env(map_name=map_name, seed=seed)
    env.reset()
    ret = 0.0
    steps = 0
    terminated = False
    info = {}
    t0 = time.perf_counter()
    while not terminated:
        snap = snapshot(env)
        actions = pol.act(map_name, steps, snap)
        reward, terminated, info = env.step(actions)
        ret += float(reward)
        steps += 1
        if steps > env.episode_limit + 5:
            break
    a_n, a_hp, e_n, e_hp = leftover(env)
    env.close()
    jobs = {
        k: v
        for k, v in getattr(pol, "tactic_counts", {}).items()
        if k.startswith(("ranged:", "melee:", "kite:", "bait:", "form:", "tactic:"))
    }
    return {
        "win": int(bool(info.get("battle_won"))),
        "ret": ret,
        "steps": steps,
        "sec": time.perf_counter() - t0,
        "asked": dict(getattr(pol, "asked_counts", {})),
        "ov": getattr(pol, "n_override", 0),
        "calls": getattr(pol, "n_calls", 0),
        "jobs": jobs,
        "A": (a_n, round(a_hp, 1)),
        "E": (e_n, round(e_hp, 1)),
        "overrides": list(getattr(pol, "overrides", [])[:6]),
    }


def show(tag, m, row):
    print(
        f"RESULT {tag} {m} win={row['win']} ret={row['ret']:.2f} "
        f"steps={row['steps']} {row['sec']:.1f}s A={row['A']} E={row['E']} "
        f"calls={row['calls']} asked={row['asked']} ov={row['ov']} jobs={row['jobs']}",
        flush=True,
    )
    if row["overrides"]:
        print(" overrides", row["overrides"], flush=True)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "dummy"
    maps = sys.argv[2:] or (REMAINING + REGRESS)
    if mode == "dummy":
        pol = DummyActionPolicy()
        for m in maps:
            reset_pol(pol)
            show("dummy", m, run(pol, m))
    elif mode == "jev":
        pol = JevActionPolicy()
        for m in maps:
            reset_pol(pol)
            show("jev", m, run(pol, m))
    elif mode.startswith("force"):
        picks = {"ranged": "stutter"}
        if mode == "force_bait2":
            picks = {"bait": "bait_two"}
        elif mode == "force_charge":
            picks = {"melee": "charge"}
        elif mode == "force_stutter_all":
            picks = {"ranged": "stutter", "kite": "all"}
        pol = ForceActionPolicy(picks)
        for m in maps:
            reset_pol(pol)
            show(mode, m, run(pol, m))
    else:
        raise SystemExit(f"unknown mode {mode}")
    print("ALL_DONE", flush=True)
