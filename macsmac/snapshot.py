from __future__ import annotations

from typing import Any, Dict, List


def short_type(unit) -> str:
    name = getattr(getattr(unit, "type", None), "stats", None)
    raw = getattr(name, "name", None) or str(getattr(unit, "type", "u"))
    return raw.replace("example_custom_unit", "unit")[:3]


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
    tname = type(getattr(u, "targeter", None)).__name__

    def _label(val):
        return getattr(val, "value", None) or getattr(val, "name", None) or str(val).split(".")[-1]

    attrs = [_label(a) for a in (getattr(u, "attributes", None) or [])]
    raw_bonuses = getattr(u, "bonuses", None) or {}
    bonuses = {_label(k): float(v) for k, v in dict(raw_bonuses).items()}
    plane = _label(getattr(u, "plane", None) or "GROUND")
    raw_vt = getattr(u, "valid_targets", None) or ["GROUND"]
    valid_targets = [_label(v) for v in raw_vt]
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
        "radius": float(getattr(u, "radius", 0.4) or 0.4),
        "armor": float(getattr(u, "armor", 0) or 0),
        "attacks": int(getattr(u, "attacks", 1) or 1),
        "dmg": float(getattr(u, "damage", 0) or 0),
        "bonuses": bonuses,
        "attributes": attrs,
        "speed": speed,
        "hit": bool(getattr(u, "hit", False)),
        "kamikaze": "Kamikaze" in tname,
        "splash": ("Laser" in tname) or ("Kamikaze" in tname),
        "splash_radius": float(getattr(getattr(u, "targeter", None), "radius", 0) or 0) if "Kamikaze" in tname else 0.0,
        "beam_width": float(getattr(getattr(u, "targeter", None), "width", 0) or 0),
        "beam_height": float(getattr(getattr(u, "targeter", None), "height", 0) or 0),
        "energy": float(getattr(u, "energy", 0) or 0),
        "plane": plane,
        "valid_targets": valid_targets,
    }


def snapshot(env) -> Dict[str, Any]:
    allies: List[Dict[str, Any]] = []
    enemies: List[Dict[str, Any]] = []
    for i in range(env.n_agents):
        u = env.get_unit_by_id(i)
        if u is None or getattr(u, "hp", 0) <= 0:
            allies.append({"id": i, "alive": False})
        else:
            allies.append(pack_unit(u, i))
    for i in range(env.n_enemies):
        u = env.enemies.get(i)
        if u is None or getattr(u, "hp", 0) <= 0:
            enemies.append({"id": i, "alive": False})
        else:
            enemies.append(pack_unit(u, i))
    avail = env.get_avail_actions()
    last_ids = [-1] * env.n_agents
    last = env.last_action
    if last is not None:
        arr = last
        if getattr(arr, "ndim", 0) == 2:
            for i in range(min(env.n_agents, arr.shape[0])):
                last_ids[i] = int(arr[i].argmax()) if arr[i].sum() > 0 else -1
    mi = env._gym.map_info
    walkable = []
    terrain = getattr(mi, "terrain", None) or []
    for row in terrain:
        walkable.append([
            1 if getattr(cell, "value", cell) in ("_", "NORMAL") or str(cell).endswith("NORMAL") else 0
            for cell in row
        ])
    return {
        "n_agents": env.n_agents,
        "n_enemies": env.n_enemies,
        "attack_point": tuple(getattr(mi, "attack_point", (16.0, 16.0))),
        "terrain_ascii": "",
        "allies": allies,
        "enemies": enemies,
        "avail": avail,
        "last_action_ids": last_ids,
        "center": (float(mi.width) / 2.0, float(mi.height) / 2.0),
        "width": float(mi.width),
        "height": float(mi.height),
        "sight": 9.0,
        "shoot": 6.0,
        "limit": int(env.episode_limit),
        "walkable": walkable,
    }
