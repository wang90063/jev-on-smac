#!/usr/bin/env python3
"""All official SMAClite maps x seeds. Dummy + Jev. Resume-safe JSONL."""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "smaclite"))
os.environ["JEV_QUIET"] = "1"

from macsmac.env import StarCraft2Env
from macsmac.maps import MAP_PARAMS
from macsmac.snapshot import snapshot
from jev_smac_policy import DummyActionPolicy, JevActionPolicy, OnlinePolicy, ValueOnlinePolicy, WrittenOnlinePolicy

SEEDS = [1, 2, 3, 4, 5]
MAPS = list(MAP_PARAMS.keys())
OUT_DIR = ROOT / "results"
RUN_NAME = os.environ.get("WINRATE_NAME", "winrate_seeds")
JSONL = OUT_DIR / f"{RUN_NAME}.jsonl"
SUMMARY = OUT_DIR / f"{RUN_NAME}.md"


def reset_pol(pol):
    pol.asked_counts = {}
    pol.n_override = 0
    pol.overrides = []
    pol.n_calls = 0
    pol.n_asked = 0
    pol.n_fallback = 0
    pol.n_questions = 0
    pol.n_live_prune = 0
    pol.n_guard = 0
    pol.tactic_counts = {}
    pol.plan_counts = {}
    if hasattr(pol.client, "n_calls"):
        pol.client.n_calls = 0
    if hasattr(pol.client, "infer_s"):
        pol.client.infer_s = 0.0
    if hasattr(pol.client, "n_fail"):
        pol.client.n_fail = 0


def leftover(env):
    allies = [env.get_unit_by_id(i) for i in range(env.n_agents)]
    enemies = [env.enemies.get(i) for i in range(env.n_enemies)]
    a_live = [u for u in allies if u is not None and getattr(u, "hp", 0) > 0]
    e_live = [u for u in enemies if u is not None and getattr(u, "hp", 0) > 0]
    a_hp = sum(float(u.hp) + float(getattr(u, "shield", 0) or 0) for u in a_live)
    e_hp = sum(float(u.hp) + float(getattr(u, "shield", 0) or 0) for u in e_live)
    return len(a_live), round(a_hp, 1), len(e_live), round(e_hp, 1)


def run_episode(pol, map_name, seed):
    env = StarCraft2Env(map_name=map_name, seed=seed)
    env.reset()
    ret = 0.0
    steps = 0
    terminated = False
    info = {}
    t0 = time.perf_counter()
    try:
        while not terminated:
            snap = snapshot(env)
            actions = pol.act(map_name, steps, snap)
            reward, terminated, info = env.step(actions)
            ret += float(reward)
            steps += 1
            if steps > env.episode_limit + 5:
                break
        a_n, a_hp, e_n, e_hp = leftover(env)
    finally:
        env.close()
    jobs = {
        k: v
        for k, v in getattr(pol, "tactic_counts", {}).items()
        if k.startswith(("ranged:", "melee:", "kite:", "bait:", "form:", "tactic:"))
    }
    return {
        "policy": getattr(pol, "tag", "unk"),
        "map": map_name,
        "seed": seed,
        "difficulty": MAP_PARAMS[map_name]["difficulty"],
        "win": int(bool(info.get("battle_won"))),
        "ret": round(ret, 3),
        "steps": steps,
        "sec": round(time.perf_counter() - t0, 2),
        "A": [a_n, a_hp],
        "E": [e_n, e_hp],
        "calls": int(getattr(pol, "n_calls", 0) or 0),
        "asked": dict(getattr(pol, "asked_counts", {})),
        "ov": int(getattr(pol, "n_override", 0) or 0),
        "fallback": int(getattr(pol, "n_fallback", 0) or 0),
        "jobs": jobs,
        "overrides": list(getattr(pol, "overrides", [])[:8]),
    }


def load_done(path: Path):
    done = set()
    rows = []
    if not path.is_file():
        return done, rows
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        done.add((row["policy"], row["map"], int(row["seed"])))
        rows.append(row)
    return done, rows


def append_row(path: Path, row: dict):
    with path.open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()


def summarize(rows):
    by = defaultdict(list)
    for row in rows:
        by[(row["policy"], row["map"])].append(row)
    lines = [
        "# SMAClite win rates",
        "",
        f"Seeds `{SEEDS}`. Env: SMAClite / macsmac. Dummy = attack-move motor. Jev = Choice over legal jobs.",
        "",
        "| Map | Diff | Dummy WR | Jev WR | Dummy ret | Jev ret | Jev asked | Jev ov |",
        "|---|---|---:|---:|---:|---:|---|---:|",
    ]
    dummy_w = jev_w = dummy_n = jev_n = 0
    for map_name, meta in MAP_PARAMS.items():
        d = by.get(("def", map_name), [])
        j = by.get(("jev", map_name), [])
        if not d and not j:
            continue
        d_wr = (100.0 * sum(r["win"] for r in d) / len(d)) if d else None
        j_wr = (100.0 * sum(r["win"] for r in j) / len(j)) if j else None
        d_ret = (sum(r["ret"] for r in d) / len(d)) if d else None
        j_ret = (sum(r["ret"] for r in j) / len(j)) if j else None
        asked = {}
        ov = 0
        for r in j:
            ov += r.get("ov") or 0
            for k, v in (r.get("asked") or {}).items():
                asked[k] = asked.get(k, 0) + v
        if d:
            dummy_w += sum(r["win"] for r in d)
            dummy_n += len(d)
        if j:
            jev_w += sum(r["win"] for r in j)
            jev_n += len(j)
        lines.append(
            "| {map} | {diff} | {dwr} | {jwr} | {dret} | {jret} | {asked} | {ov} |".format(
                map=map_name,
                diff=meta["difficulty"],
                dwr="—" if d_wr is None else f"{d_wr:.0f}% ({sum(r['win'] for r in d)}/{len(d)})",
                jwr="—" if j_wr is None else f"{j_wr:.0f}% ({sum(r['win'] for r in j)}/{len(j)})",
                dret="—" if d_ret is None else f"{d_ret:.1f}",
                jret="—" if j_ret is None else f"{j_ret:.1f}",
                asked="," .join(f"{k}:{v}" for k, v in asked.items()) or "-",
                ov=ov if j else "—",
            )
        )
    lines += [
        "",
        f"Dummy overall: **{(100.0 * dummy_w / dummy_n):.1f}%** ({dummy_w}/{dummy_n})" if dummy_n else "",
        f"Jev overall: **{(100.0 * jev_w / jev_n):.1f}%** ({jev_w}/{jev_n})" if jev_n else "",
        "",
    ]
    # per-seed detail
    lines += ["## Per seed", "", "| Policy | Map | Seed | Win | Return | Steps | A left | E left | Calls | Overrides |", "|---|---|---:|---:|---:|---:|---|---|---:|---|"]
    for row in rows:
        lines.append(
            "| {p} | {m} | {s} | {w} | {r:.2f} | {st} | {A} | {E} | {c} | {ov} |".format(
                p=row["policy"],
                m=row["map"],
                s=row["seed"],
                w=row["win"],
                r=row["ret"],
                st=row["steps"],
                A=row["A"],
                E=row["E"],
                c=row.get("calls", 0),
                ov="; ".join(row.get("overrides") or []) or "-",
            )
        )
    return "\n".join(lines).rstrip() + "\n"


def main():
    modes = sys.argv[1:] or ["dummy", "jev"]
    done, rows = load_done(JSONL)
    print(f"resume {len(done)} episodes already in {JSONL}", flush=True)
    policies = []
    if "dummy" in modes:
        policies.append(DummyActionPolicy())
    if "online" in modes:
        policies.append(WrittenOnlinePolicy())  # the online default since round 15
    if "online_value" in modes:
        policies.append(ValueOnlinePolicy(tag="online_value"))  # default in rounds 8-14
    if "online_nearest" in modes:
        policies.append(OnlinePolicy(tag="online_nearest"))  # previous default
    if "jev" in modes:
        policies.append(JevActionPolicy())
    for pol in policies:
        tag = pol.tag
        for map_name in MAPS:
            for seed in SEEDS:
                key = (tag, map_name, seed)
                if key in done:
                    print(f"SKIP {tag} {map_name} seed={seed}", flush=True)
                    continue
                reset_pol(pol)
                print(f"RUN {tag} {map_name} seed={seed} ({MAP_PARAMS[map_name]['difficulty']})", flush=True)
                try:
                    row = run_episode(pol, map_name, seed)
                except Exception as exc:
                    traceback.print_exc()
                    row = {
                        "policy": tag,
                        "map": map_name,
                        "seed": seed,
                        "difficulty": MAP_PARAMS[map_name]["difficulty"],
                        "win": 0,
                        "ret": 0.0,
                        "steps": 0,
                        "sec": 0.0,
                        "A": [0, 0],
                        "E": [0, 0],
                        "calls": 0,
                        "asked": {},
                        "ov": 0,
                        "fallback": 0,
                        "jobs": {},
                        "overrides": [],
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                append_row(JSONL, row)
                rows.append(row)
                done.add(key)
                print(
                    f"RESULT {tag} {map_name} seed={seed} win={row['win']} "
                    f"ret={row['ret']:.2f} steps={row['steps']} {row['sec']:.1f}s "
                    f"A={row['A']} E={row['E']} calls={row.get('calls')} "
                    f"asked={row.get('asked')} ov={row.get('ov')}",
                    flush=True,
                )
                if row.get("overrides"):
                    print(" overrides", row["overrides"], flush=True)
                SUMMARY.write_text(summarize(rows))
    SUMMARY.write_text(summarize(rows))
    print(SUMMARY.read_text())
    print("ALL_DONE", flush=True)


if __name__ == "__main__":
    main()
