#!/usr/bin/env python3
"""Jev on official SMAC (StarCraft II), not SMAClite."""

from __future__ import annotations

import argparse
import os
import time
from typing import Any, Dict, List

import numpy as np

os.environ.setdefault("SC2PATH", "/Applications/StarCraft II")

from jev_smac_policy import JevActionPolicy  # noqa: E402


def _unit_name(unit, env) -> str:
    ut = int(getattr(unit, "unit_type", 0) or 0)
    mapping = {
        getattr(env, "marine_id", None): "marine",
        getattr(env, "marauder_id", None): "marauder",
        getattr(env, "medivac_id", None): "medivac",
        getattr(env, "stalker_id", None): "stalker",
        getattr(env, "zealot_id", None): "zealot",
        getattr(env, "colossus_id", None): "colossus",
        getattr(env, "zergling_id", None): "zergling",
        getattr(env, "baneling_id", None): "baneling",
        getattr(env, "hydralisk_id", None): "hydralisk",
        getattr(env, "spine_id", None): "spine",
    }
    return mapping.get(ut) or f"u{ut}"


def _role(unit, env) -> str:
    name = _unit_name(unit, env)
    if name in {"medivac"}:
        return "heal"
    if name in {"zealot", "zergling", "baneling"}:
        return "melee"
    if name in {"spine"}:
        return "static"
    return "ranged"


def _pack(unit, i: int, env) -> Dict[str, Any]:
    hp = float(getattr(unit, "health", 0) or 0)
    if hp <= 0:
        return {"id": i, "alive": False}
    pos = getattr(unit, "pos", None)
    x = float(getattr(pos, "x", 0.0) or 0.0)
    y = float(getattr(pos, "y", 0.0) or 0.0)
    name = _unit_name(unit, env)
    return {
        "id": i,
        "alive": True,
        "type": name[:3],
        "name": name,
        "role": _role(unit, env),
        "hp": hp,
        "max_hp": float(getattr(unit, "health_max", hp) or hp),
        "shield": float(getattr(unit, "shield", 0) or 0),
        "max_shield": float(getattr(unit, "shield_max", 0) or 0),
        "cd": float(getattr(unit, "weapon_cooldown", 0) or 0),
        "max_cd": 0.86,
        "x": x,
        "y": y,
        "range": 6.0 if _role(unit, env) != "melee" else 0.1,
        "dmg": 0.0,
        "speed": 0.0 if _role(unit, env) == "static" else 2.25,
        "hit": False,
    }


def snapshot_smac(env) -> Dict[str, Any]:
    n_agents = int(env.n_agents)
    n_enemies = int(env.n_enemies)
    allies = []
    enemies = []
    for i in range(n_agents):
        u = env.get_unit_by_id(i)
        allies.append(_pack(u, i, env) if u is not None else {"id": i, "alive": False})
    for i in range(n_enemies):
        u = env.enemies.get(i)
        enemies.append(_pack(u, i, env) if u is not None else {"id": i, "alive": False})
    avail = env.get_avail_actions()
    last_ids = [-1] * n_agents
    last = getattr(env, "last_action", None)
    if last is not None:
        arr = np.asarray(last)
        if arr.ndim == 2:
            for i in range(min(n_agents, arr.shape[0])):
                last_ids[i] = int(arr[i].argmax()) if arr[i].sum() > 0 else -1
    return {
        "n_agents": n_agents,
        "n_enemies": n_enemies,
        "attack_point": (16.0, 16.0),
        "terrain_ascii": "",
        "allies": allies,
        "enemies": enemies,
        "avail": [list(map(int, row)) for row in avail],
        "last_action_ids": last_ids,
        "center": (16.0, 16.0),
        "width": 32.0,
        "height": 32.0,
        "sight": 9.0,
        "shoot": 6.0,
        "limit": int(getattr(env, "episode_limit", 0) or 0),
    }


def run_episode(env, policy, map_name: str) -> Dict[str, Any]:
    env.reset()
    ret = 0.0
    steps = 0
    t0 = time.perf_counter()
    terminated = False
    info: Dict[str, Any] = {}
    while not terminated:
        snap = snapshot_smac(env)
        actions = policy.act(map_name, steps, snap)
        reward, terminated, info = env.step(actions)
        ret += float(reward)
        steps += 1
        if steps > int(getattr(env, "episode_limit", 400) or 400) + 5:
            break
    won = bool(info.get("battle_won"))
    return {
        "win": int(won),
        "return": ret,
        "steps": steps,
        "seconds": time.perf_counter() - t0,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--maps", nargs="+", default=["3m"])
    p.add_argument("--episodes", type=int, default=1)
    p.add_argument("--difficulty", default="7")
    args = p.parse_args()

    from smac.env import StarCraft2Env

    print("SC2PATH", os.environ.get("SC2PATH"), flush=True)
    policy = JevActionPolicy()
    for map_name in args.maps:
        print(f"\n===== official SMAC {map_name} =====", flush=True)
        env = StarCraft2Env(map_name=map_name, difficulty=args.difficulty, window_size_x=640, window_size_y=480)
        try:
            for ep in range(args.episodes):
                row = run_episode(env, policy, map_name)
                print(
                    f"{map_name:12s} jev ep {ep+1:02d}/{args.episodes} "
                    f"win={row['win']} ret={row['return']:.2f} steps={row['steps']} "
                    f"{row['seconds']:.1f}s",
                    flush=True,
                )
        finally:
            env.close()


if __name__ == "__main__":
    main()
