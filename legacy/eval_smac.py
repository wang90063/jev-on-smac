#!/usr/bin/env python3
"""Zero-shot Laya-MLX vs scripted micro on SMAClite, compared with published SMAC numbers."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))  # core modules live in src/

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from smac_laya_policy import LayaPolicy, ScriptedSquadPolicy
from qwen_smac_policy import QwenPolicy, QwenCentralPolicy, TwoStagePolicy, QwenSquadPolicy, ApiPlanPolicy, ApiQwenExecPolicy
from jev_smac_policy import JevActionPolicy
from central_micro import CentralMicro

import numpy as np
from gymnasium.wrappers import TimeLimit

ROOT = Path(__file__).resolve().parents[1]
MAPS_DIR = ROOT / "legacy" / "maps"
RESULTS_DIR = ROOT / "results"
LAYA_WEIGHTS = ROOT / "local" / "laya-mlx"
# The git clone lives at ROOT/smaclite and would shadow the inner package.
import sys
_pkg_root = ROOT / "smaclite"
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))

# SMAC episode limits (env steps after step_mul=8), from oxwhirl/smac map_params.
MAPS = {
    "3m": {"kind": "gym", "key": "smaclite/3m-v0", "limit": 60, "difficulty": "Easy"},
    "8m": {"kind": "gym", "key": "smaclite/8m-v0", "limit": 120, "difficulty": "Easy"},
    "5m_vs_6m": {
        "kind": "gym",
        "key": "smaclite/5m_vs_6m-v0",
        "limit": 70,
        "difficulty": "Hard",
    },
    "8m_vs_9m": {"kind": "gym", "key": "smaclite/8m_vs_9m-v0", "limit": 120, "difficulty": "Hard"},
    "25m": {"kind": "gym", "key": "smaclite/25m-v0", "limit": 150, "difficulty": "Easy"},
    "2m_vs_1z": {"kind": "gym", "key": "smaclite/2m_vs_1z-v0", "limit": 150, "difficulty": "Easy"},
    "3s_vs_3z": {"kind": "gym", "key": "smaclite/3s_vs_3z-v0", "limit": 150, "difficulty": "Easy"},
    "3s_vs_4z": {"kind": "gym", "key": "smaclite/3s_vs_4z-v0", "limit": 200, "difficulty": "Hard"},
    "1c3s5z": {"kind": "gym", "key": "smaclite/1c3s5z-v0", "limit": 180, "difficulty": "Hard"},
    "6h_vs_8z": {"kind": "gym", "key": "smaclite/6h_vs_8z-v0", "limit": 150, "difficulty": "Super Hard"},
    "so_many_baneling": {"kind": "gym", "key": "smaclite/so_many_baneling-v0", "limit": 100, "difficulty": "Hard"},
    "2s_vs_1sc": {
        "kind": "gym",
        "key": "smaclite/2s_vs_1sc-v0",
        "limit": 300,
        "difficulty": "Easy / alternating fire",
    },
    "2s3z": {
        "kind": "gym",
        "key": "smaclite/2s3z-v0",
        "limit": 120,
        "difficulty": "Easy",
    },
    "3s_vs_5z": {
        "kind": "gym",
        "key": "smaclite/3s_vs_5z-v0",
        "limit": 250,
        "difficulty": "Hard / kiting",
    },
    "10m_vs_11m": {"kind": "gym", "key": "smaclite/10m_vs_11m-v0", "limit": 150, "difficulty": "Hard"},
    "3s5z": {"kind": "gym", "key": "smaclite/3s5z-v0", "limit": 150, "difficulty": "Hard"},
    "MMM": {"kind": "gym", "key": "smaclite/MMM-v0", "limit": 150, "difficulty": "Hard"},
    "MMM2": {"kind": "gym", "key": "smaclite/MMM2-v0", "limit": 180, "difficulty": "Super Hard"},
    "3s5z_vs_3s6z": {"kind": "gym", "key": "smaclite/3s5z_vs_3s6z-v0", "limit": 170, "difficulty": "Super Hard"},
    "27m_vs_30m": {"kind": "gym", "key": "smaclite/27m_vs_30m-v0", "limit": 180, "difficulty": "Super Hard"},
    "corridor": {"kind": "gym", "key": "smaclite/corridor-v0", "limit": 400, "difficulty": "Super Hard"},
    "2c_vs_64zg": {"kind": "gym", "key": "smaclite/2c_vs_64zg-v0", "limit": 400, "difficulty": "Super Hard"},
}

# Published SMAC win rates (official SC2 SMAC, not SMAClite). See report for caveats.
PAPER_BASELINES = {
    "3m": {
        "MAPPO": 100.0,
        "IPPO": 100.0,
        "QMIX": 96.9,
        "source": "Yu et al. MAPPO, median test win %",
    },
    "8m": {
        "QMIX_SMAC-Hard_2M": 80.83,
        "MAPPO_SMAC-Hard_2M": 59.79,
        "source": "SMAC-Hard Table 3, 2M steps (under-trained vs full MAPPO)",
    },
    "5m_vs_6m": {
        "MAPPO": 89.1,
        "IPPO": 87.5,
        "QMIX": 75.8,
        "QMIX_original": 70.0,
        "Heuristic_closest": 0.0,
        "source": "MAPPO paper; original QMIX appendix heuristic=closest enemy",
    },
    "2s_vs_1sc": {
        "MAPPO": 100.0,
        "QMIX": 96.9,
        "QMIX_original": 100.0,
        "Heuristic_closest": 0.0,
        "source": "MAPPO paper + QMIX appendix. Heuristic 0% because alternating fire is required",
    },
    "2s3z": {
        "MAPPO": 100.0,
        "QMIX": 95.3,
        "QMIX_original": 99.0,
        "Heuristic_closest": 90.0,
        "source": "MAPPO paper + QMIX appendix",
    },
    "3s_vs_5z": {
        "QMIX_original": 87.0,
        "Heuristic_closest": 0.0,
        "source": "QMIX appendix Table 9; MAPPO paper did not report this map",
    },
    "3s5z": {
        "MAPPO": 96.9,
        "QMIX": 88.3,
        "QMIX_original": 97.0,
        "Heuristic_closest": 42.0,
        "source": "MAPPO paper + QMIX appendix",
    },
    "10m_vs_11m": {
        "MAPPO": 96.9,
        "QMIX": 95.3,
        "QMIX_original": 97.0,
        "Heuristic_closest": 12.0,
        "source": "MAPPO paper + QMIX appendix",
    },
    "MMM2": {
        "MAPPO": 90.6,
        "QMIX": 87.5,
        "HPN-QMIX": 100.0,
        "source": "MAPPO paper; HPN-QMIX ICLR 2023 (Hard/SuperHard 9/10 maps 100%)",
    },
    "6h_vs_8z": {
        "MAPPO": 88.3,
        "QMIX": 9.4,
        "HPN-QMIX": 98.0,
        "Heuristic_closest": 0.0,
        "source": "MAPPO paper; HPN-QMIX ICLR 2023",
    },
    "corridor": {
        "MAPPO": 100.0,
        "QMIX": 84.4,
        "HPN-QMIX": 100.0,
        "Heuristic_closest": 0.0,
        "source": "MAPPO paper; HPN-QMIX",
    },
    "27m_vs_30m": {
        "MAPPO": 93.8,
        "QMIX": 39.1,
        "HPN-QMIX": 100.0,
        "Heuristic_closest": 0.0,
        "source": "MAPPO paper; HPN-QMIX",
    },
}

ACTION_NAMES = {0: "noop", 1: "stop", 2: "N", 3: "S", 4: "E", 5: "W"}


def short_type(unit) -> str:
    name = getattr(getattr(unit, "type", None), "stats", None)
    raw = getattr(name, "name", None) or str(getattr(unit, "type", "u"))
    return raw.replace("example_custom_unit", "unit")[:3]


def dist(a, b) -> float:
    d = a.pos - b.pos
    return float(math.hypot(float(d[0]), float(d[1])))


def make_env(map_name: str, seed: int):
    import gymnasium as gym
    import smaclite  # noqa: F401

    spec = MAPS[map_name]
    if spec["kind"] == "file":
        env = gym.make(
            "smaclite/custom-v0",
            map_file=str(spec["path"]),
            seed=seed,
            use_cpp_rvo2=False,
            render_mode="rgb_array",
        )
    else:
        env = gym.make(spec["key"], seed=seed, use_cpp_rvo2=False, render_mode="rgb_array")
    return TimeLimit(env, max_episode_steps=spec["limit"])


def pack_unit(u, i: int) -> Dict[str, Any]:
    speed = float(getattr(u, "max_velocity", 0.0) or 0.0)
    rng = float(u.attack_range)
    ctype = str(getattr(getattr(u, "combat_type", None), "name", "") or getattr(u, "combat_type", ""))
    if "HEAL" in ctype.upper():
        role = "heal"
    elif speed < 0.15:
        role = "static"
    elif rng <= 0.6:
        role = "melee"
    else:
        role = "ranged"
    stats = getattr(getattr(u, "type", None), "stats", None)
    name = getattr(stats, "name", None) or short_type(u)
    return {
        "id": i,
        "alive": True,
        "type": short_type(u),
        "name": str(name),
        "role": role,
        "hp": float(u.hp),
        "max_hp": float(u.max_hp),
        "shield": float(u.shield),
        "max_shield": float(getattr(u, "max_shield", 0) or 0),
        "cd": float(u.cooldown),
        "max_cd": float(getattr(u, "max_cooldown", 0.86) or 0.86),
        "x": float(u.pos[0]),
        "y": float(u.pos[1]),
        "range": rng,
        "dmg": float(getattr(u, "damage", 0) or 0),
        "speed": speed,
        "hit": bool(getattr(u, "hit", False)),
    }



def _terrain_ascii(raw, allies, enemies, size: int = 9) -> str:
    terr = getattr(getattr(raw, "map_info", None), "terrain", None)
    if not terr:
        return ""
    H = len(terr)
    W = len(terr[0]) if H else 0
    if not H or not W:
        return ""
    living_u = [u for u in list(allies) + list(enemies) if u.get("alive")]
    if not living_u:
        return ""
    cx = int(round(sum(u["x"] for u in living_u) / len(living_u)))
    cy = int(round(sum(u["y"] for u in living_u) / len(living_u)))
    half = size // 2
    marks = {}
    for a in allies:
        if a.get("alive"):
            marks[(int(round(a["x"])), int(round(a["y"])))] = "A"
    for e in enemies:
        if e.get("alive"):
            marks[(int(round(e["x"])), int(round(e["y"])))] = "E"
    rows = []
    for yy in range(cy + half, cy - half - 1, -1):
        cells = []
        for xx in range(cx - half, cx + half + 1):
            if not (0 <= yy < H and 0 <= xx < W):
                cells.append("@")
                continue
            cell = terr[yy][xx]
            wall = getattr(cell, "value", str(cell))
            if wall in {"X", "C"} or str(cell).endswith("NONE") or str(cell).endswith("CLIFF"):
                ch = "#"
            else:
                ch = "."
            ch = marks.get((xx, yy), ch)
            cells.append(ch)
        rows.append("".join(cells))
    return "\n".join(rows)


def snapshot(env) -> Dict[str, Any]:
    raw = env.unwrapped
    allies = []
    enemies = []
    for i in range(raw.n_agents):
        u = raw.agents.get(i)
        if u is None or u.hp <= 0:
            allies.append({"id": i, "alive": False})
            continue
        allies.append(pack_unit(u, i))
    for i in range(raw.n_enemies):
        u = raw.enemies.get(i)
        if u is None or u.hp <= 0:
            enemies.append({"id": i, "alive": False})
            continue
        enemies.append(pack_unit(u, i))
    avail = raw.get_avail_actions()
    n_actions = raw.n_actions
    last = getattr(raw, "last_actions", None)
    last_ids = []
    if last is not None and len(last) == raw.n_agents * n_actions:
        flat = last.reshape(raw.n_agents, n_actions)
        for i in range(raw.n_agents):
            last_ids.append(int(flat[i].argmax()) if flat[i].sum() > 0 else -1)
    else:
        last_ids = [-1] * raw.n_agents
    width = float(raw.map_info.width)
    height = float(raw.map_info.height)
    cx, cy = width / 2.0, height / 2.0
    attack_point = tuple(getattr(raw.map_info, "attack_point", (cx, cy)))
    return {
        "n_agents": raw.n_agents,
        "n_enemies": raw.n_enemies,
        "attack_point": attack_point,
        "terrain_ascii": _terrain_ascii(raw, allies, enemies),
        "allies": allies,
        "enemies": enemies,
        "avail": [list(map(int, row)) for row in avail],
        "last_action_ids": last_ids,
        "center": (cx, cy),
        "width": width,
        "height": height,
        "sight": 9.0,
        "shoot": 6.0,
        "limit": env.spec.max_episode_steps if env.spec else None,
    }


def action_label(action: int, n_enemies: int, healing: bool = False) -> str:
    if action in ACTION_NAMES:
        return ACTION_NAMES[action]
    idx = action - 6
    if healing:
        return f"healA{idx}"
    return f"atkE{idx}"


def available_labels(avail_row: Sequence[int], n_enemies: int) -> List[Tuple[int, str]]:
    out = []
    for a, ok in enumerate(avail_row):
        if ok:
            out.append((a, action_label(a, n_enemies)))
    return out


def render_state(map_name: str, step: int, snap: Dict[str, Any], agent_id: Optional[int] = None) -> str:
    lines = [
        f"StarCraft micro map {map_name} step {step}. Wipe all enemies.",
        "Prefer focus-firing the lowest-HP enemy already in range. If none in range, move toward the closest living enemy. Do not stand idle if an attack is legal.",
    ]
    a_bits = []
    for a in snap["allies"]:
        if not a["alive"]:
            continue
        mark = "*" if agent_id is not None and a["id"] == agent_id else ""
        sh = f" sh{a['shield']:.0f}" if a.get("max_shield", 0) > 0 else ""
        a_bits.append(
            f"A{a['id']}{mark} {a['type']} hp{a['hp']:.0f}/{a['max_hp']:.0f}{sh} cd{a['cd']:.1f} ({a['x']:.1f},{a['y']:.1f})"
        )
    e_bits = []
    for e in snap["enemies"]:
        if not e["alive"]:
            continue
        sh = f" sh{e['shield']:.0f}" if e.get("shield", 0) > 0 else ""
        e_bits.append(
            f"E{e['id']} {e['type']} hp{e['hp']:.0f}/{e['max_hp']:.0f}{sh} ({e['x']:.1f},{e['y']:.1f})"
        )
    lines.append("Allies: " + "; ".join(a_bits) if a_bits else "Allies: none")
    lines.append("Enemies: " + "; ".join(e_bits) if e_bits else "Enemies: none")
    if agent_id is not None:
        me = next((a for a in snap["allies"] if a["id"] == agent_id), None)
        if me and me["alive"]:
            dlist = []
            for e in snap["enemies"]:
                if not e["alive"]:
                    continue
                d = math.hypot(me["x"] - e["x"], me["y"] - e["y"])
                dlist.append(f"E{e['id']} d={d:.1f}")
            if dlist:
                lines.append("Ranges: " + ", ".join(dlist))
    text = "\n".join(lines)
    # ModernBERT-large English checkpoint is 512 tokens. Keep a hard char cap.
    if len(text) > 1400:
        text = text[:1400]
    return text


def living_enemies(snap) -> List[Dict[str, Any]]:
    return [e for e in snap["enemies"] if e["alive"]]


def living_allies(snap) -> List[Dict[str, Any]]:
    return [a for a in snap["allies"] if a["alive"]]


def closest_enemy(ally, enemies):
    if not enemies:
        return None
    return min(enemies, key=lambda e: math.hypot(ally["x"] - e["x"], ally["y"] - e["y"]))


def lowest_hp_enemy(enemies):
    if not enemies:
        return None
    return min(enemies, key=lambda e: (e["hp"] + e.get("shield", 0), e["id"]))


def move_toward(ally, target, labels: List[Tuple[int, str]]) -> int:
    moves = [(a, lab) for a, lab in labels if lab in {"N", "S", "E", "W"}]
    if not moves:
        for a, lab in labels:
            if lab != "noop":
                return a
        return labels[0][0]
    best_a, best_score = moves[0][0], -1e9
    delta = {"N": (0.0, 2.0), "S": (0.0, -2.0), "E": (2.0, 0.0), "W": (-2.0, 0.0)}
    for a, lab in moves:
        dx, dy = delta[lab]
        nx, ny = ally["x"] + dx, ally["y"] + dy
        cur = math.hypot(ally["x"] - target["x"], ally["y"] - target["y"])
        nxt = math.hypot(nx - target["x"], ny - target["y"])
        score = cur - nxt
        if score > best_score:
            best_score, best_a = score, a
    return best_a


def pick_attack(labels: List[Tuple[int, str]], enemy_id: int) -> Optional[int]:
    want = f"atkE{enemy_id}"
    for a, lab in labels:
        if lab == want:
            return a
    return None


def in_range_enemies(ally, enemies) -> List[Dict[str, Any]]:
    rng = ally.get("range", 5.0) + 0.75
    out = []
    for e in enemies:
        if math.hypot(ally["x"] - e["x"], ally["y"] - e["y"]) <= rng + 0.8:
            out.append(e)
    return out


def heuristic_act(snap: Dict[str, Any], mode: str = "focus") -> List[int]:
    actions = []
    enemies = living_enemies(snap)
    for i, ally in enumerate(snap["allies"]):
        labels = available_labels(snap["avail"][i], snap["n_enemies"])
        if not ally["alive"]:
            actions.append(0)
            continue
        if not enemies:
            actions.append(next((a for a, lab in labels if lab == "stop"), labels[0][0]))
            continue
        attackable = []
        for a, lab in labels:
            if lab.startswith("atkE"):
                eid = int(lab[4:])
                e = next((x for x in enemies if x["id"] == eid), None)
                if e:
                    attackable.append(e)
        if attackable:
            target = lowest_hp_enemy(attackable) if mode == "focus" else closest_enemy(ally, attackable)
            act = pick_attack(labels, target["id"])
            actions.append(act if act is not None else labels[0][0])
            continue
        target = closest_enemy(ally, enemies)
        actions.append(move_toward(ally, target, labels))
    return actions


def random_act(snap: Dict[str, Any], rng: np.random.Generator) -> List[int]:
    actions = []
    for i, ally in enumerate(snap["allies"]):
        labels = available_labels(snap["avail"][i], snap["n_enemies"])
        if not ally["alive"]:
            actions.append(0)
            continue
        non_noop = [(a, lab) for a, lab in labels if lab != "noop"]
        pool = non_noop or labels
        actions.append(int(pool[int(rng.integers(0, len(pool)))][0]))
    return actions


def run_episode(env, policy_name: str, policy, map_name: str, rng) -> Dict[str, Any]:
    obs, info = env.reset()
    done = False
    truncated = False
    ret = 0.0
    steps = 0
    t0 = time.perf_counter()
    while not done and not truncated:
        snap = snapshot(env)
        if policy_name == "random":
            actions = random_act(snap, rng)
        elif policy_name == "heuristic_closest":
            actions = heuristic_act(snap, "closest")
        elif policy_name == "heuristic_focus":
            actions = heuristic_act(snap, "focus")
        elif policy is not None:
            actions = policy.act(map_name, steps, snap)
        else:
            raise ValueError(policy_name)
        obs, reward, done, truncated, info = env.step(actions)
        ret += float(reward)
        steps += 1
    won = bool(info.get("battle_won")) and done and not truncated
    return {
        "win": int(won),
        "return": ret,
        "steps": steps,
        "seconds": time.perf_counter() - t0,
        "truncated": int(bool(truncated)),
    }


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    wins = [r["win"] for r in rows]
    rets = [r["return"] for r in rows]
    steps = [r["steps"] for r in rows]
    secs = [r["seconds"] for r in rows]
    n = len(rows)
    return {
        "n": n,
        "win_rate": float(np.mean(wins)) if n else 0.0,
        "wins": int(np.sum(wins)),
        "return_mean": float(np.mean(rets)) if n else 0.0,
        "return_std": float(np.std(rets)) if n else 0.0,
        "steps_mean": float(np.mean(steps)) if n else 0.0,
        "sec_per_ep": float(np.mean(secs)) if n else 0.0,
    }


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--maps", nargs="+", default=["3m", "5m_vs_6m", "2s_vs_1sc", "2s3z", "3s_vs_5z", "8m"])
    p.add_argument("--policies", nargs="+", default=["random", "heuristic_closest", "heuristic_focus", "laya_commander", "laya_unit"])
    p.add_argument("--episodes", type=int, default=20)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--skip-laya", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    if args.smoke:
        args.maps = ["3m"]
        args.episodes = 2
        args.policies = ["random", "heuristic_focus"] + ([] if args.skip_laya else ["laya_commander"])
    RESULTS_DIR.mkdir(exist_ok=True)

    laya_policies = {}
    if not args.skip_laya:
        for name in args.policies:
            if (name.startswith("laya") or name.startswith("qwen") or name.startswith("squad_") or name in {"micro", "api_plan", "api_qwen", "jev"}) and name not in laya_policies:
                if name == "qwen_commander":
                    print("loading Qwen2.5-1.5B-Instruct-4bit tactic decoder", flush=True)
                    laya_policies[name] = QwenPolicy()
                    print("qwen loaded", flush=True)
                    continue
                if name == "qwen_central":
                    print("loading Qwen2.5-1.5B-Instruct-4bit CENTRAL unit controller", flush=True)
                    laya_policies[name] = QwenCentralPolicy()
                    print("qwen central loaded", flush=True)
                    continue
                if name == "qwen_s2":
                    print("loading Qwen System-1 + API System-2", flush=True)
                    laya_policies[name] = TwoStagePolicy()
                    print("two-stage loaded", flush=True)
                    continue
                if name == "qwen_squad":
                    print("loading Qwen2.5-1.5B-Instruct-4bit SQUAD commander", flush=True)
                    laya_policies[name] = QwenSquadPolicy()
                    print("qwen squad loaded", flush=True)
                    continue
                if name == "api_plan":
                    print("loading LLM gateway DeepSeek-V4-Flash planner (reasoning off)", flush=True)
                    laya_policies[name] = ApiPlanPolicy()
                    print("api planner loaded", flush=True)
                    continue
                if name == "api_qwen":
                    print("loading API planner + Qwen cropped executor", flush=True)
                    laya_policies[name] = ApiQwenExecPolicy()
                    print("api+qwen loaded", flush=True)
                    continue
                if name == "jev":
                    print("loading TypeSafe Jev action policy (direct unit choices)", flush=True)
                    laya_policies[name] = JevActionPolicy()
                    print("jev loaded", flush=True)
                    continue
                if name.startswith("squad_"):
                    cmd = name.split("_", 1)[1].upper()
                    print(f"loading scripted squad cmd={cmd}", flush=True)
                    laya_policies[name] = ScriptedSquadPolicy(cmd)
                    continue
                if name == "micro":
                    print("loading CentralMicro scripted commander", flush=True)
                    laya_policies[name] = CentralMicro()
                    print("micro loaded", flush=True)
                    continue
                style = "commander" if name == "laya_commander" else "unit"
                if name == "laya":
                    style = "commander"
                print(f"loading laya-mlx style={style} from {LAYA_WEIGHTS}", flush=True)
                laya_policies[name] = LayaPolicy(LAYA_WEIGHTS, style=style)
                print("laya loaded", name, flush=True)

    all_results = {
        "env": "SMAClite (no StarCraft II)",
        "note": "Laya-MLX is zero-shot typed decisions, not trained MARL. Paper numbers are official SMAC/SC2.",
        "maps": {},
    }
    rng = np.random.default_rng(args.seed)

    for map_name in args.maps:
        print(f"\n===== map {map_name} =====", flush=True)
        all_results["maps"][map_name] = {
            "meta": {k: (str(v) if isinstance(v, Path) else v) for k, v in MAPS[map_name].items()},
            "paper": PAPER_BASELINES.get(map_name, {}),
            "policies": {},
        }
        for policy_name in args.policies:
            if (policy_name.startswith("laya") or policy_name.startswith("qwen") or policy_name.startswith("squad_") or policy_name in {"micro", "api_plan", "api_qwen", "jev"}) and policy_name not in laya_policies:
                continue
            if policy_name in laya_policies:
                laya_policies[policy_name].tactic_counts = {}
                laya_policies[policy_name].n_guard = 0
                laya_policies[policy_name].n_fallback = 0
                laya_policies[policy_name].n_calls = 0
                laya_policies[policy_name].infer_s = 0.0
            rows = []
            for ep in range(args.episodes):
                env = make_env(map_name, seed=args.seed + 1000 * ep + sum(map(ord, map_name)))
                try:
                    row = run_episode(env, policy_name, laya_policies.get(policy_name), map_name, rng)
                finally:
                    env.close()
                rows.append(row)
                print(
                    f"{map_name:12s} {policy_name:18s} ep {ep+1:02d}/{args.episodes} "
                    f"win={row['win']} ret={row['return']:.2f} steps={row['steps']} "
                    f"{row['seconds']:.2f}s",
                    flush=True,
                )
            summary = summarize(rows)
            pol_obj = laya_policies.get(policy_name)
            if pol_obj is not None:
                summary["laya_calls"] = pol_obj.n_calls
                summary["laya_fallback"] = pol_obj.n_fallback
                summary["laya_guard"] = getattr(pol_obj, "n_guard", 0)
                if getattr(pol_obj, "tactic_counts", None):
                    summary["tactics"] = dict(pol_obj.tactic_counts)
                summary["laya_infer_s"] = pol_obj.infer_s
                if pol_obj.n_calls:
                    summary["laya_ms_per_call"] = 1000.0 * pol_obj.infer_s / pol_obj.n_calls
            all_results["maps"][map_name]["policies"][policy_name] = {
                "summary": summary,
                "episodes": rows,
            }
            print(
                f"SUMMARY {map_name} {policy_name}: win_rate={summary['win_rate']:.3f} "
                f"return={summary['return_mean']:.2f}",
                flush=True,
            )
            out = RESULTS_DIR / "smaclite_laya_eval.json"
            out.write_text(json.dumps(all_results, indent=2))
            write_report(all_results)

    print(f"\nwrote {RESULTS_DIR / 'smaclite_laya_eval.json'}", flush=True)


def write_report(data: dict) -> None:
    lines = []
    lines.append("# Laya-MLX on StarCraft Micro (SMAClite)")
    lines.append("")
    lines.append("Zero-shot `aac6fef/laya-mlx` (English 421M, 512 context) as a typed-decision policy on SMAClite.")
    lines.append("No StarCraft II on this machine, so the runnable env is SMAClite, not official SMAC/SC2.")
    lines.append("Paper columns are **published SMAC win rates** and are not from this run.")
    lines.append("")
    lines.append("## This run")
    lines.append("")
    lines.append("| Map | Policy | n | Win rate | Return | s/ep |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for map_name, block in data["maps"].items():
        for pol, payload in block["policies"].items():
            s = payload["summary"]
            lines.append(
                f"| {map_name} | {pol} | {s['n']} | {100*s['win_rate']:.1f}% | {s['return_mean']:.2f} | {s['sec_per_ep']:.2f} |"
            )
    lines.append("")
    lines.append("## Paper baselines (official SMAC / SC2)")
    lines.append("")
    lines.append("| Map | MAPPO | QMIX | Heuristic closest | HPN-QMIX | Source |")
    lines.append("|---|---:|---:|---:|---:|---|")
    for map_name, nums in PAPER_BASELINES.items():
        def fmt(k):
            v = nums.get(k)
            return "" if v is None else (f"{v:.1f}%" if isinstance(v, float) else str(v))
        qmix = nums.get("QMIX", nums.get("QMIX_original"))
        lines.append(
            f"| {map_name} | {fmt('MAPPO')} | {'' if qmix is None else f'{qmix:.1f}%'} | {fmt('Heuristic_closest')} | {fmt('HPN-QMIX')} | {nums.get('source','')} |"
        )
    lines.append("")
    lines.append("## How to read this")
    lines.append("")
    lines.append("- MARL numbers are after millions of environment steps. Laya here is **untrained on SMAC**.")
    lines.append("- SMAClite preserves SMAC ranking but absolute win rates are not interchangeable with SC2 SMAC.")
    lines.append("- `heuristic_closest` is the SMAC paper's built-in scripted baseline (attack nearest).")
    lines.append("- `heuristic_focus` is a slightly stronger script: lowest-HP in-range, else walk toward nearest.")
    lines.append("- Laya gets a compact English state and one `choice` question per living unit.")
    lines.append("- `qwen_squad` picks an army command (FOCUS/NEAREST/KITE/BAIT/BALL); a dumb adapter issues unit actions.")
    lines.append("- `jev` is TypeSafe Jev: one request per tick, one Choice per living unit over legal SMAC actions.")
    lines.append("- `squad_*` is that adapter with a fixed command, no LLM.")
    path = RESULTS_DIR / "smaclite_laya_eval.md"
    path.write_text("\n".join(lines) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
