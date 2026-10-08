#!/usr/bin/env python3
from __future__ import annotations
import os, sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "smaclite")]
os.environ["JEV_QUIET"] = "1"

from macsmac.env import StarCraft2Env
from macsmac.maps import MAP_PARAMS
from macsmac.snapshot import snapshot
from jev_smac_policy import (
    DummyActionPolicy,
    legal_plans,
    army_plan,
    ranged_jobs,
    melee_jobs,
    kite_jobs,
    bait_jobs,
    formation_jobs,
    target_rules,
    default_ranged_job,
    default_melee_job,
    default_kite_style,
    default_bait_style,
    default_formation,
    default_target_rule,
    build_job_catalog,
    living,
    _live_tactic,
)

def catalog_open(snap, form, r_job, m_job, rule):
    allies = living(snap["allies"])
    wounded = [a for a in allies if a.get("role") != "heal" and a["hp"] < a["max_hp"] - 1]
    healers = [a for a in allies if a.get("role") == "heal"]
    cat = build_job_catalog(
        snap, formation_jobs(snap), ranged_jobs(snap), melee_jobs(snap),
        target_rules(snap), wounded, healers, form, r_job, m_job, rule,
    )
    return {k: v["options"] for k, v in cat.items()}

def run(map_name, seed=1):
    env = StarCraft2Env(map_name=map_name, seed=seed)
    env.reset()
    pol = DummyActionPolicy()
    t0 = None
    seen = Counter()
    opens = Counter()
    steps = 0
    terminated = False
    info = {}
    ret = 0.0
    while not terminated:
        snap = snapshot(env)
        plans = legal_plans(snap)
        plan = army_plan(snap)
        r_jobs = ranged_jobs(snap)
        m_jobs = melee_jobs(snap)
        k_jobs = kite_jobs(snap)
        b_jobs = bait_jobs(snap)
        f_jobs = formation_jobs(snap)
        rules = target_rules(snap)
        form = default_formation(f_jobs)
        r_job = default_ranged_job(r_jobs, snap)
        m_job = default_melee_job(m_jobs, snap)
        k_job = default_kite_style(k_jobs, snap)
        b_job = default_bait_style(b_jobs, snap)
        rule = default_target_rule(snap)
        tac = _live_tactic(snap)
        tag = (
            f"tac={tac['name']} plan={plan} form={form} "
            f"r={r_job} k={k_job} m={m_job} b={b_job} t={rule}"
        )
        seen[tag] += 1
        cat = catalog_open(snap, form, r_job, m_job, rule)
        if cat:
            opens[",".join(sorted(cat.keys()))] += 1
        if t0 is None:
            t0 = {
                "tactic": tac,
                "plans": plans, "plan": plan,
                "form": (form, f_jobs),
                "ranged": (r_job, r_jobs),
                "kite": (k_job, k_jobs),
                "melee": (m_job, m_jobs),
                "bait": (b_job, b_jobs),
                "target": (rule, rules),
                "exam": list(cat.keys()),
            }
        actions = pol.act(map_name, steps, snap)
        reward, terminated, info = env.step(actions)
        ret += float(reward)
        steps += 1
        if steps > env.episode_limit + 5:
            break
    env.close()
    return {
        "win": int(bool(info.get("battle_won"))),
        "ret": ret,
        "steps": steps,
        "t0": t0,
        "seen": seen.most_common(4),
        "opens": opens.most_common(6),
    }

if __name__ == "__main__":
    maps = sys.argv[1:] or list(MAP_PARAMS)
    for m in maps:
        row = run(m)
        t0 = row["t0"]
        print(
            f"MAP {m} win={row['win']} ret={row['ret']:.2f} steps={row['steps']}",
            flush=True,
        )
        print(
            f"  t0 tactic={t0['tactic']} plan={t0['plan']}{t0['plans']} form={t0['form']} "
            f"r={t0['ranged']} k={t0['kite']} m={t0['melee']} b={t0['bait']} "
            f"t={t0['target']} exam={t0['exam']}",
            flush=True,
        )
        print(f"  modes {row['seen']}", flush=True)
        print(f"  exams {row['opens']}", flush=True)
    print("ALL_DONE", flush=True)
