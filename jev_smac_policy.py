"""Jev commands official SMAClite; code executes.

Code owns mask, range, cooldown, attack-move, and illegal physics.
Jev never picks NESW. Dummy is attack-move / charge / keep.

A job is legal when the army can physically do it. Whenever two legal
jobs remain, Jev's Choice is the decision. Code compiles the pick.
Dummy keeps the attack-move default. There is no override gate.

Question bank: formation, ranged, kite, melee, bait, target, tie, heal.
Ranged jobs: stack = attack-move, stutter = kite, concave = fan then kite.
"""

from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional, Tuple

from jev_api import JevClient
from smac_laya_policy import hypot, last_action_name, living, _group_away_lab

# ----------------------------------------------------------------------
# Physics: geometry, range, speed, chokes
# ----------------------------------------------------------------------

WALK = {
    2: ("walk_north", "north", (0.0, 2.0)),
    3: ("walk_south", "south", (0.0, -2.0)),
    4: ("walk_east", "east", (2.0, 0.0)),
    5: ("walk_west", "west", (-2.0, 0.0)),
}


def _ready(unit: Dict[str, Any]) -> bool:
    return float(unit.get("cd") or 0) <= 0.08


def _soon(unit: Dict[str, Any]) -> bool:
    """Cooldown will hit 0 during this env step (0.5s)."""
    return float(unit.get("cd") or 0) <= 0.55


def _can_target(snap: Dict[str, Any], ally: Dict[str, Any], target_id: int) -> bool:
    i = ally["id"]
    row = snap["avail"][i] if i < len(snap["avail"]) else []
    idx = 6 + target_id
    return idx < len(row) and bool(row[idx])


def _radius(unit: Dict[str, Any]) -> float:
    r = unit.get("radius")
    if r is not None:
        return float(r)
    if unit.get("role") == "melee":
        return 0.5
    if unit.get("role") == "static":
        return 0.5
    rng = float(unit.get("range") or 5.0)
    return 0.625 if rng >= 5.0 else 0.375


def _weapon_reach(ally: Dict[str, Any], enemy: Dict[str, Any]) -> float:
    return float(ally.get("range") or 5.0) + _radius(ally) + _radius(enemy)


def _in_weapon_range(ally: Dict[str, Any], enemy: Dict[str, Any]) -> bool:
    return hypot(ally, enemy) <= _weapon_reach(ally, enemy) + 0.05


def _ehp(unit: Dict[str, Any]) -> float:
    return float(unit["hp"]) + float(unit.get("shield") or 0)


def _hp_key(unit: Dict[str, Any]):
    return (_ehp(unit), unit["id"])


def _damage_enemies(snap: Dict[str, Any]) -> List[Dict[str, Any]]:
    enemies = living(snap["enemies"])
    dmg = [e for e in enemies if e.get("role") != "heal"]
    return dmg or enemies


def _front_enemy(snap: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Nearest living damage enemy to the allied centroid. Healers come last."""
    enemies = [e for e in _hittable_enemies(snap) if e.get("role") != "heal"] or _hittable_enemies(snap)
    if not enemies:
        enemies = _damage_enemies(snap)
    allies = living(snap["allies"])
    if not enemies:
        return None
    if not allies:
        return min(enemies, key=_hp_key)
    ax, ay = _centroid(allies)
    return min(
        enemies,
        key=lambda e: ((e["x"] - ax) ** 2 + (e["y"] - ay) ** 2, _ehp(e), e["id"]),
    )


def _can_hit(ally: Dict[str, Any], enemy: Dict[str, Any]) -> bool:
    plane = str(enemy.get("plane") or "GROUND")
    valid = ally.get("valid_targets") or ["GROUND"]
    return plane in set(valid)


def _hittable_enemies(snap: Dict[str, Any], ally: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    enemies = living(snap["enemies"])
    if ally is not None:
        return [e for e in enemies if _can_hit(ally, e)]
    shooters = [a for a in living(snap["allies"]) if a.get("role") != "heal"]
    if not shooters:
        return []
    return [e for e in enemies if any(_can_hit(a, e) for a in shooters)]


def _walkable_at(snap: Dict[str, Any], x: float, y: float) -> bool:
    grid = snap.get("walkable") or []
    if not grid:
        return True
    xi = int(round(x))
    yi = int(round(y))
    if yi < 0 or yi >= len(grid) or xi < 0 or xi >= len(grid[yi]):
        return False
    return bool(grid[yi][xi])


def _passage_width(snap: Dict[str, Any], x: float, y: float, dest: Tuple[float, float]) -> float:
    hx, hy = dest[0] - x, dest[1] - y
    n = (hx * hx + hy * hy) ** 0.5
    if n < 1e-6:
        return 99.0
    px, py = -hy / n, hx / n

    def ray(dx: float, dy: float) -> float:
        t = 0.0
        while t < 18.0:
            t += 0.5
            if not _walkable_at(snap, x + dx * t, y + dy * t):
                return t
        return 18.0

    if not snap.get("walkable"):
        return 99.0
    return ray(px, py) + ray(-px, -py)


def _rally_point(snap: Dict[str, Any]) -> Tuple[float, float]:
    return tuple(snap.get("attack_point") or snap.get("center") or (0.0, 0.0))


def _funnel_metrics(snap: Dict[str, Any], x: float, y: float) -> Tuple[float, float, float]:
    ap = _rally_point(snap)
    width = _passage_width(snap, x, y, ap)
    hx, hy = ap[0] - x, ap[1] - y
    n = (hx * hx + hy * hy) ** 0.5
    if n < 1e-6:
        return width, 99.0, width
    dx, dy = 2.0 * hx / n, 2.0 * hy / n
    ahead = _passage_width(snap, x + dx, y + dy, ap)
    behind = _passage_width(snap, x - dx, y - dy, ap)
    return width, ahead, behind


def _in_neck_at(snap: Dict[str, Any], x: float, y: float) -> bool:
    width, _ahead, _behind = _funnel_metrics(snap, x, y)
    return width <= 6.5


def _in_pocket_at(snap: Dict[str, Any], x: float, y: float) -> bool:
    """Far side of a neck: walls cover the rear, not the wide mouth or the deep hall."""
    width, ahead, behind = _funnel_metrics(snap, x, y)
    return behind <= 6.5 and width <= 8.0 and (width <= 6.5 or ahead > width)


def _too_deep_at(snap: Dict[str, Any], x: float, y: float) -> bool:
    width, _ahead, behind = _funnel_metrics(snap, x, y)
    return behind <= 6.5 and width > 8.0


def _army_xy(snap: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    allies = living(snap["allies"])
    if not allies:
        return None
    return _centroid(allies)


def _in_pocket(snap: Dict[str, Any]) -> bool:
    xy = _army_xy(snap)
    return False if xy is None else _in_pocket_at(snap, xy[0], xy[1])


def _too_deep(snap: Dict[str, Any]) -> bool:
    xy = _army_xy(snap)
    return False if xy is None else _too_deep_at(snap, xy[0], xy[1])


def _in_choke(snap: Dict[str, Any]) -> bool:
    """True when the blob should stop running and brawl: past the neck, rear covered."""
    return _in_pocket(snap)


def _pocket_label(snap: Dict[str, Any]) -> str:
    xy = _army_xy(snap)
    if xy is None:
        return "open"
    width, _ahead, behind = _funnel_metrics(snap, xy[0], xy[1])
    if _in_pocket_at(snap, xy[0], xy[1]):
        return "in_pocket"
    if _too_deep_at(snap, xy[0], xy[1]):
        return "past_pocket"
    if width <= 6.5 and behind > 6.5:
        return "at_mouth"
    if width <= 6.5:
        return "in_neck"
    return "open"


def _army_toward_key(snap: Dict[str, Any], dest: Tuple[float, float]) -> Optional[str]:
    xy = _army_xy(snap)
    if xy is None:
        return None
    return _walk_toward_key({"x": xy[0], "y": xy[1]}, dest)


def _shot_damage(ally: Dict[str, Any], enemy: Dict[str, Any]) -> float:
    raw = float(ally.get("dmg") or 0)
    enemy_attrs = set(enemy.get("attributes") or [])
    for attr, bonus in (ally.get("bonuses") or {}).items():
        if attr in enemy_attrs:
            raw += float(bonus)
    raw *= max(1, int(ally.get("attacks") or 1))
    shield = float(enemy.get("shield") or 0)
    if shield <= 0:
        return max(0.0, raw - float(enemy.get("armor") or 0))
    if raw <= shield:
        return raw
    return shield + max(0.0, raw - shield - float(enemy.get("armor") or 0))


def _weakest_in_shot(snap: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    allies = living(snap["allies"])
    enemies = [e for e in _hittable_enemies(snap) if e.get("role") != "heal"] or _hittable_enemies(snap)
    in_shot = []
    for e in enemies:
        for a in allies:
            if a.get("role") == "heal":
                continue
            if _can_hit(a, e) and _in_weapon_range(a, e) and _can_target(snap, a, e["id"]):
                in_shot.append(e)
                break
    if not in_shot:
        return None
    return min(in_shot, key=_hp_key)


def _weakest_any(snap: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return _weakest_in_shot(snap) or (
        min(living(snap["enemies"]), key=_hp_key) if living(snap["enemies"]) else None
    )


def _nearest(unit: Dict[str, Any], others: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not others:
        return None
    return min(others, key=lambda o: hypot(unit, o))


def _speed_advantage(snap: Dict[str, Any]) -> float:
    allies = [a for a in living(snap["allies"]) if a.get("role") == "ranged"]
    melee = [e for e in living(snap["enemies"]) if e.get("role") == "melee"]
    if not allies or not melee:
        return 0.0
    return min(float(a.get("speed") or 0) for a in allies) - max(
        float(e.get("speed") or 0) for e in melee
    )


def _range_advantage(snap: Dict[str, Any]) -> float:
    allies = [a for a in living(snap["allies"]) if a.get("role") == "ranged"]
    melee = [e for e in living(snap["enemies"]) if e.get("role") == "melee"]
    if not allies or not melee:
        return 0.0
    return min(float(a.get("range") or 0) for a in allies) - max(
        float(e.get("range") or 0) for e in melee
    )


def _centroid(units: List[Dict[str, Any]]) -> Tuple[float, float]:
    return (
        sum(u["x"] for u in units) / len(units),
        sum(u["y"] for u in units) / len(units),
    )


def _rally_is_behind(snap: Dict[str, Any]) -> bool:
    allies = living(snap["allies"])
    enemies = living(snap["enemies"])
    if not allies or not enemies:
        return False
    ap = snap.get("attack_point") or snap.get("center") or (0.0, 0.0)
    ax, ay = _centroid(allies)
    ex, ey = _centroid(enemies)
    return (ex - ax) * (ap[0] - ax) + (ey - ay) * (ap[1] - ay) < 0


def _densest_enemy(snap: Dict[str, Any], radius: float = 2.4) -> Optional[Dict[str, Any]]:
    enemies = living(snap["enemies"])
    if not enemies:
        return None

    def key(e):
        n = sum(1 for o in enemies if hypot(e, o) <= radius)
        return (-n, _ehp(e), e["id"])

    return min(enemies, key=key)


def _walk_toward_key(ally: Dict[str, Any], dest: Tuple[float, float]) -> Optional[str]:
    best, best_d = None, 1e18
    for _act, (key, _heading, (dx, dy)) in WALK.items():
        d = (ally["x"] + dx - dest[0]) ** 2 + (ally["y"] + dy - dest[1]) ** 2
        if d < best_d:
            best, best_d = key, d
    return best


def _heavy_count(units: List[Dict[str, Any]]) -> int:
    return sum(1 for u in units if u.get("role") != "heal" and _body_band(u) == "heavy")


def _kami_pack_radius() -> float:
    return 2.8


def _kami_neighbors(unit: Dict[str, Any], kami: List[Dict[str, Any]]) -> int:
    r = _kami_pack_radius()
    return sum(1 for o in kami if o["id"] != unit["id"] and hypot(unit, o) <= r)


def _isolated_kami(snap: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    kami = [e for e in living(snap["enemies"]) if e.get("kamikaze")]
    if not kami:
        return None
    return min(kami, key=lambda e: (_kami_neighbors(e, kami), _ehp(e), e["id"]))


def _packed_kami(snap: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Suicide wad: the bomb whose explosion hits the most other bombs."""
    kami = [e for e in living(snap["enemies"]) if e.get("kamikaze")]
    if not kami:
        return None
    return max(kami, key=lambda e: (_kami_neighbors(e, kami), -_ehp(e), -e["id"]))


def _snipe_bomb(snap: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Packed bombs friendly-fire. Bait the wad; only pick off a true straggler."""
    if _kami_pack_live(snap):
        return _packed_kami(snap)
    return _isolated_kami(snap)


def _kami_pack_live(snap: Dict[str, Any]) -> bool:
    kami = [e for e in living(snap["enemies"]) if e.get("kamikaze")]
    if len(kami) < 2:
        return False
    best = min(kami, key=lambda e: (_kami_neighbors(e, kami), _ehp(e), e["id"]))
    return _kami_neighbors(best, kami) > 0


def _static_enemies(snap: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [e for e in living(snap["enemies"]) if e.get("role") == "static"]


def _cycle_out(ally: Dict[str, Any], snap: Dict[str, Any]) -> bool:
    """Cooling inside a building's range is dominated by walking out."""
    static = _static_enemies(snap)
    if not static or any(e.get("role") == "melee" for e in living(snap["enemies"])):
        return False
    if _ready(ally):
        return False
    building = _nearest(ally, static)
    if building is None:
        return False
    if hypot(ally, building) > _weapon_reach(building, ally) + 0.05:
        return False
    guns = [a for a in living(snap["allies"]) if a.get("role") != "heal"]
    volley = sum(_shot_damage(a, building) for a in guns)
    if _ehp(building) <= volley + 8:
        return False
    return True


def _cycle_may_enter(ally: Dict[str, Any], snap: Dict[str, Any]) -> bool:
    """Only the closest gun walks into a building's range; others wait until engaged."""
    static = _static_enemies(snap)
    if not static or any(e.get("role") == "melee" for e in living(snap["enemies"])):
        return True
    building = _nearest(ally, static)
    if building is None:
        return True
    allies = [a for a in living(snap["allies"]) if a.get("role") != "heal"]
    others = [a for a in allies if a["id"] != ally["id"]]
    spine_reach = _weapon_reach(building, ally)
    our_reach = _weapon_reach(ally, building)
    d = hypot(ally, building)
    partner_engaged = any(hypot(a, building) <= spine_reach + 0.4 for a in others)
    closest = min(allies, key=lambda a: (hypot(a, building), a["id"]))
    last_man = len(allies) == 1
    volley = sum(_shot_damage(a, building) for a in allies)
    skip_stagger = last_man or _ehp(building) <= volley * 3 + 8
    fragile = _ehp(ally) <= _shot_damage(building, ally) + 1
    speed = max(float(ally.get("speed") or 0.0), 0.1)
    time_to_range = max(0.0, d - our_reach) / speed
    ready_enough = float(ally.get("cd") or 0) <= time_to_range + 0.05
    if last_man:
        return _ready(ally)
    if fragile and others:
        return False
    return (skip_stagger or closest["id"] == ally["id"] or partner_engaged) and (
        _ready(ally) or ready_enough
    )


def _allowed_walk_keys(
    ally: Dict[str, Any],
    snap: Dict[str, Any],
    options: Optional[List[Tuple[int, str, Dict[str, Any]]]] = None,
) -> Optional[set]:
    if options is not None:
        keys = {k for _a, k, _m in options if str(k).startswith("walk_")}
        return keys
    avail = snap.get("avail") or []
    i = ally.get("id")
    if i is None or i >= len(avail):
        return None
    row = avail[i]
    return {WALK[a][0] for a, ok in enumerate(row) if ok and a in WALK}


def _close_walk_key(
    ally: Dict[str, Any],
    snap: Dict[str, Any],
    dest: Tuple[float, float],
    options: Optional[List[Tuple[int, str, Dict[str, Any]]]] = None,
) -> Optional[str]:
    """Step toward dest on walkable, available tiles. Attack-move often stalls a tile short."""
    allowed = _allowed_walk_keys(ally, snap, options)
    best, best_d = None, 1e18
    for _act, (key, _heading, (dx, dy)) in WALK.items():
        if allowed is not None and key not in allowed:
            continue
        nx, ny = ally["x"] + dx, ally["y"] + dy
        if not _walkable_at(snap, nx, ny):
            continue
        d = (nx - dest[0]) ** 2 + (ny - dest[1]) ** 2
        if d < best_d:
            best, best_d = key, d
    if best is not None:
        return best
    return _walk_toward_key(ally, _rally_point(snap))


# ----------------------------------------------------------------------
# Plans and target rules
# ----------------------------------------------------------------------

def legal_plans(snap: Dict[str, Any]) -> List[str]:
    """Physics mask over army plans. Never a map name."""
    allies = living(snap["allies"])
    enemies = living(snap["enemies"])
    if not allies or not enemies:
        return ["commit"]
    if any(e.get("role") == "static" for e in enemies):
        return ["cycle"]
    if any(a.get("kamikaze") for a in allies) or any(e.get("kamikaze") for e in enemies):
        return ["detonate"]
    plans = ["commit"]
    melee_a = [a for a in allies if a.get("role") == "melee"]
    melee_e = [e for e in enemies if e.get("role") == "melee"]
    ranged_a = [a for a in allies if a.get("role") == "ranged"]
    if (
        melee_a
        and melee_e
        and not ranged_a
        and len(enemies) > len(allies)
        and (
            _rally_is_behind(snap)
            or _in_pocket(snap)
            or _in_choke(snap)
        )
    ):
        # Choke exists: charge and hold_choke are both legal. Dummy charges.
        plans.append("funnel")
        return plans
    ranged_e = [e for e in enemies if e.get("role") == "ranged"]
    if ranged_a and melee_e and not melee_a and not ranged_e:
        has_laser = any(a.get("splash") and not a.get("kamikaze") for a in allies)
        if not has_laser:
            plans.append("kite")
    return plans


def army_plan(snap: Dict[str, Any]) -> str:
    """Script default is attack-move (commit). Kite is a ranged job, not a plan default."""
    plans = legal_plans(snap)
    forced = snap.get("_plan")
    if forced in plans:
        return forced
    for pref in ("detonate", "cycle", "commit", "funnel", "kite"):
        if pref in plans:
            return pref
    return plans[0]


def default_target_rule(snap: Dict[str, Any]) -> str:
    """Dummy default: splash weapons hit the pack, everyone else focus-fires the weakest in shot."""
    rules = target_rules(snap)
    if any(a.get("kamikaze") or a.get("splash") for a in living(snap["allies"])) and "clump" in rules:
        return "clump"
    if "weakest_in_range" in rules:
        return "weakest_in_range"
    return rules[0] if rules else "frontline"


def target_rules(snap: Dict[str, Any]) -> List[str]:
    enemies = _damage_enemies(snap)
    rules = ["frontline", "weakest_in_range"]
    if any(a.get("splash") for a in living(snap["allies"])):
        rules.append("clump")
    dmg = [e for e in enemies if e.get("role") != "heal"]
    if any(_body_band(e) == "heavy" for e in dmg) and any(_body_band(e) != "heavy" for e in dmg):
        # Body class, not current HP. A chipped marauder is still the tank.
        rules.append("heaviest")
    if any(e.get("role") == "ranged" for e in dmg) and any(e.get("role") == "melee" for e in dmg):
        rules.append("guns")
    heals = [e for e in living(snap["enemies"]) if e.get("role") == "heal"]
    if heals:
        medic = heals[0]
        if any(_can_hit(a, medic) for a in living(snap["allies"]) if a.get("role") != "heal"):
            rules.append("healer")
    if snap.get("_open_menu") and dmg:
        rules.append("threat")
    return rules


def _must_break_extra_tank(snap: Dict[str, Any]) -> bool:
    """They have extra heavy bodies and lights. Split fire on lights loses the trade.
    A living enemy healer undoes tank-focus; holding lights back is then dominated
    by walking the whole ball in."""
    allies = living(snap["allies"])
    enemies = living(snap["enemies"])
    if any(a.get("kamikaze") for a in allies) or any(e.get("kamikaze") for e in enemies):
        return False
    if any(e.get("role") == "heal" for e in enemies):
        return False
    if any(a.get("role") == "melee" for a in allies) and any(e.get("role") == "melee" for e in enemies):
        return False
    lights = any(e.get("role") != "heal" and _body_band(e) != "heavy" for e in enemies)
    return lights and _heavy_count(enemies) > _heavy_count(allies) and _heavy_count(enemies) > 0


def _focus_coverage(snap: Dict[str, Any], focus: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    guns = [a for a in living(snap["allies"]) if a.get("role") != "heal"]
    if focus is None:
        return {"focus": "none", "guns_that_can_shoot_it": 0, "ready_guns_on_it": 0, "ready_guns_total": 0}
    can = [
        a
        for a in guns
        if _can_hit(a, focus) and _in_weapon_range(a, focus) and _can_target(snap, a, focus["id"])
    ]
    ready_on = [a for a in can if _ready(a)]
    return {
        "focus": f"E{focus['id']}",
        "body": _body_band(focus),
        "guns_that_can_shoot_it": len(can),
        "ready_guns_on_it": len(ready_on),
        "ready_guns_total": sum(1 for a in guns if _ready(a)),
        "extra_tank_alive": _must_break_extra_tank(snap),
    }


def _surplus_gun(ally: Dict[str, Any], snap: Dict[str, Any], target: Optional[Dict[str, Any]]) -> bool:
    """True if other ready guns already deal enough damage to kill target this tick."""
    if target is None or not _ready(ally):
        return False
    if not (
        _can_hit(ally, target)
        and _in_weapon_range(ally, target)
        and _can_target(snap, ally, target["id"])
    ):
        return False
    ready = []
    for a in living(snap["allies"]):
        if a.get("role") == "heal" or not _ready(a):
            continue
        if (
            _can_hit(a, target)
            and _in_weapon_range(a, target)
            and _can_target(snap, a, target["id"])
        ):
            ready.append(a)
    ready.sort(key=lambda a: a["id"])
    acc = 0.0
    needed = set()
    for a in ready:
        needed.add(a["id"])
        acc += _shot_damage(a, target)
        if acc >= _ehp(target) - 0.05:
            break
    return ally["id"] not in needed


def _can_shoot(ally: Dict[str, Any], enemy: Dict[str, Any], snap: Dict[str, Any]) -> bool:
    return (
        _can_hit(ally, enemy)
        and _in_weapon_range(ally, enemy)
        and _can_target(snap, ally, enemy["id"])
    )


def _ranged_shot_plan(snap: Dict[str, Any]) -> Dict[int, int]:
    """Ready guns cover the weakest enemy they can hit, then the next.
    A gun is not spent on a body other guns already kill this tick."""
    cached = snap.get("_shot_plan")
    if isinstance(cached, dict):
        return cached
    guns = [
        a
        for a in living(snap["allies"])
        if a.get("role") == "ranged" and not a.get("splash") and not a.get("kamikaze")
    ]
    enemies = [e for e in living(snap["enemies"]) if e.get("role") != "heal" and not e.get("kamikaze")]
    can: Dict[int, List[Dict[str, Any]]] = {}
    visible: Dict[int, Dict[str, Any]] = {}
    for gun in guns:
        hits = [e for e in enemies if _can_shoot(gun, e, snap)]
        can[gun["id"]] = hits
        for enemy in hits:
            visible[enemy["id"]] = enemy
    assigned: Dict[int, int] = {}
    order = sorted(visible.values(), key=_hp_key)
    prefer = snap.get("_tie_prefer")
    if prefer is not None:
        for i in range(len(order) - 1):
            low, high = order[i], order[i + 1]
            if high["id"] != prefer:
                continue
            both = [
                gun for gun in guns
                if _ready(gun)
                and any(e["id"] == low["id"] for e in can[gun["id"]])
                and any(e["id"] == high["id"] for e in can[gun["id"]])
            ]
            gap = _ehp(high) - _ehp(low)
            if both and 0 <= gap <= max(_shot_damage(gun, low) for gun in both) + 0.05:
                order[i], order[i + 1] = high, low
            break
    for enemy in order:
        need = _ehp(enemy) - 0.05
        acc = 0.0
        pool = [
            gun
            for gun in guns
            if gun["id"] not in assigned and _ready(gun) and any(e["id"] == enemy["id"] for e in can[gun["id"]])
        ]
        while pool and acc < need:
            pool.sort(key=lambda gun: (len(can[gun["id"]]), gun["id"]))
            gun = pool.pop(0)
            assigned[gun["id"]] = enemy["id"]
            acc += _shot_damage(gun, enemy)
        if acc >= need:
            continue
        cooling = [
            gun
            for gun in guns
            if gun["id"] not in assigned and not _ready(gun) and any(e["id"] == enemy["id"] for e in can[gun["id"]])
        ]
        cooling.sort(key=lambda gun: (len(can[gun["id"]]), gun["id"]))
        for gun in cooling:
            assigned[gun["id"]] = enemy["id"]
            acc += _shot_damage(gun, enemy)
            if acc >= need:
                break
    for gun in guns:
        if gun["id"] in assigned or not can[gun["id"]]:
            continue
        assigned[gun["id"]] = min(can[gun["id"]], key=_hp_key)["id"]
    snap["_shot_plan"] = assigned
    return assigned


def _tie_pair_count(snap: Dict[str, Any]) -> int:
    """How many disjoint one-shot ties a ready gun can see. Melee enemies stay out."""
    if any(e.get("role") == "melee" for e in living(snap["enemies"])):
        return 0
    guns = [
        a for a in living(snap["allies"])
        if a.get("role") == "ranged" and not a.get("splash") and not a.get("kamikaze") and _ready(a)
    ]
    enemies = [e for e in living(snap["enemies"]) if e.get("role") != "heal" and not e.get("kamikaze")]
    can = {}
    visible = {}
    for gun in guns:
        hits = [e for e in enemies if _can_shoot(gun, e, snap)]
        can[gun["id"]] = hits
        for enemy in hits:
            visible[enemy["id"]] = enemy
    order = sorted(visible.values(), key=_hp_key)
    n = 0
    i = 0
    while i < len(order) - 1:
        low, high = order[i], order[i + 1]
        both = [
            gun for gun in guns
            if any(e["id"] == low["id"] for e in can[gun["id"]])
            and any(e["id"] == high["id"] for e in can[gun["id"]])
        ]
        gap = _ehp(high) - _ehp(low) if both else 99.0
        if both and 0 <= gap <= max(_shot_damage(gun, low) for gun in both) + 0.05:
            n += 1
            i += 2
        else:
            i += 1
    return n


def _one_shot_pair(snap: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Two enemies one gun can shoot, with health within that gun's shot.
    Empty unless the shot plan itself cannot separate them. Not used against melee."""
    if any(e.get("role") == "melee" for e in living(snap["enemies"])):
        return []
    guns = [
        a for a in living(snap["allies"])
        if a.get("role") == "ranged" and not a.get("splash") and not a.get("kamikaze") and _ready(a)
    ]
    enemies = [e for e in living(snap["enemies"]) if e.get("role") != "heal" and not e.get("kamikaze")]
    visible: Dict[int, Dict[str, Any]] = {}
    can: Dict[int, List[Dict[str, Any]]] = {}
    for gun in guns:
        hits = [e for e in enemies if _can_shoot(gun, e, snap)]
        can[gun["id"]] = hits
        for enemy in hits:
            visible[enemy["id"]] = enemy
    order = sorted(visible.values(), key=_hp_key)
    for i in range(len(order) - 1):
        low, high = order[i], order[i + 1]
        both = [
            gun for gun in guns
            if any(e["id"] == low["id"] for e in can[gun["id"]])
            and any(e["id"] == high["id"] for e in can[gun["id"]])
        ]
        if not both:
            continue
        gap = _ehp(high) - _ehp(low)
        if 0 <= gap <= max(_shot_damage(gun, low) for gun in both) + 0.05:
            return [low, high]
    return []


def _planned_shot(
    ally: Dict[str, Any], snap: Dict[str, Any], shootable: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    if ally.get("role") != "ranged" or ally.get("splash") or ally.get("kamikaze"):
        return None
    # Enemy blades are in contact range. Splitting shots across them lets the
    # nearest one arrive. Gunfights are where the lethal split wins.
    if any(e.get("role") == "melee" for e in living(snap["enemies"])):
        return None
    enemy_id = _ranged_shot_plan(snap).get(ally["id"])
    if enemy_id is None:
        return None
    return next((enemy for enemy in shootable if enemy["id"] == enemy_id), None)


def _laser_allies(snap: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        a
        for a in living(snap["allies"])
        if a.get("splash") and not a.get("kamikaze") and float(a.get("beam_width") or 0) > 0
    ]


def _beam_hits(origin: Dict[str, Any], target: Dict[str, Any], enemies: List[Dict[str, Any]]) -> int:
    """How many bodies the laser's perpendicular bar touches. Same geometry as the engine."""
    width = float(origin.get("beam_width") or 0)
    height = float(origin.get("beam_height") or 0)
    if width <= 0 or not enemies:
        return 0
    dx = float(target["x"]) - float(origin["x"])
    dy = float(target["y"]) - float(origin["y"])
    ratio = dy / dx if abs(dx) >= 1e-9 else (1e12 if dy >= 0 else -1e12)
    # Level shot (dy == 0): the engine's numpy divide gives -inf -> -pi/2.
    theta = math.atan(-1.0 / ratio) if abs(ratio) >= 1e-12 else -math.pi / 2
    c, s = math.cos(theta), math.sin(theta)

    def xf(x: float, y: float) -> Tuple[float, float]:
        return (x * c + y * s, -x * s + y * c)

    tx, ty = xf(float(target["x"]), float(target["y"]))
    offx, offy = width / 2.0, height / 2.0
    n = 0
    for enemy in enemies:
        ex, ey = xf(float(enemy["x"]), float(enemy["y"]))
        ddx = max(0.0, abs(tx - ex) - offx)
        ddy = max(0.0, abs(ty - ey) - offy)
        rad = float(enemy.get("radius") or 0.4)
        if ddx * ddx + ddy * ddy <= rad * rad + 1e-6:
            n += 1
    return n


def _laser_focus(snap: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Aim a laser at the bar that touches the most bodies. Circle-clump is a different weapon."""
    lasers = _laser_allies(snap)
    enemies = [e for e in living(snap["enemies"]) if e.get("role") != "heal"]
    if not lasers or not enemies:
        return None
    origin = min(lasers, key=lambda a: a["id"])
    best = None
    best_key = None
    for enemy in enemies:
        key = (_beam_hits(origin, enemy, enemies), -_ehp(enemy), -enemy["id"])
        if best_key is None or key > best_key:
            best_key = key
            best = enemy
    return best


def _bar_pair(snap: Dict[str, Any]):
    """Circle-clump and the laser bar, when they are different bodies. None if either is missing or they match."""
    if not _laser_allies(snap):
        return None
    pack = _densest_enemy(snap)
    bar = _laser_focus(snap)
    if pack is None or bar is None or pack["id"] == bar["id"]:
        return None
    return pack, bar


def _threat(e: Dict[str, Any]) -> float:
    """Damage per second per remaining effective HP. Kill order for a trade."""
    dps = float(e.get("dmg") or 0) * max(1, int(e.get("attacks") or 1)) / max(float(e.get("max_cd") or 0.86), 0.1)
    if e.get("splash"):
        dps *= 2.0
    return dps / max(_ehp(e), 1.0)


def resolve_focus(rule: str, snap: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if rule == "threat":
        pool = [e for e in _hittable_enemies(snap) if e.get("role") != "heal"] or [
            e for e in living(snap["enemies"]) if e.get("role") != "heal"
        ]
        return max(pool, key=lambda e: (_threat(e), -e["id"])) if pool else None
    if rule == "weakest_in_range":
        return _weakest_in_shot(snap) or _front_enemy(snap)
    if rule == "clump":
        return _densest_enemy(snap) or _front_enemy(snap)
    if rule == "heaviest":
        dmg = [e for e in _hittable_enemies(snap) if e.get("role") != "heal"] or _hittable_enemies(snap)
        if not dmg:
            return None
        heavies = [e for e in dmg if _body_band(e) == "heavy"] or dmg
        allies = living(snap["allies"])
        if not allies:
            return max(heavies, key=lambda e: (_ehp(e), -e["id"]))
        ax, ay = _centroid(allies)
        # Same ehp: the extra tank in the fight, not the backline copy with a bigger id.
        return max(
            heavies,
            key=lambda e: (
                _ehp(e),
                -((e["x"] - ax) ** 2 + (e["y"] - ay) ** 2),
                -e["id"],
            ),
        )
    if rule == "guns":
        guns = [e for e in _hittable_enemies(snap) if e.get("role") == "ranged"] or [
            e for e in living(snap["enemies"]) if e.get("role") == "ranged"
        ]
        if not guns:
            return _front_enemy(snap)
        shot = [e for e in guns if any(
            _in_weapon_range(a, e) and _can_hit(a, e)
            for a in living(snap["allies"])
            if a.get("role") != "heal"
        )]
        pool = shot or guns
        return min(pool, key=lambda e: (_ehp(e), e["id"]))
    if rule == "healer":
        heals = [e for e in living(snap["enemies"]) if e.get("role") == "heal"]
        if not heals:
            return None
        allies = living(snap["allies"])
        if not allies:
            return min(heals, key=lambda e: (_ehp(e), e["id"]))
        ax, ay = _centroid(allies)
        return min(
            heals,
            key=lambda e: (
                (e["x"] - ax) ** 2 + (e["y"] - ay) ** 2,
                _ehp(e),
                e["id"],
            ),
        )
    return _front_enemy(snap) or _weakest_any(snap)


def _unique_coverage(unit: Dict[str, Any], snap: Dict[str, Any]) -> int:
    shooters = [a for a in living(snap["allies"]) if a.get("role") != "heal" and a["id"] != unit["id"]]
    n = 0
    for e in living(snap["enemies"]):
        if _can_hit(unit, e) and not any(_can_hit(a, e) for a in shooters):
            n += 1
    return n


def _coverage_value(unit: Dict[str, Any], snap: Dict[str, Any]) -> int:
    """Prefer units that can hit enemies some allies cannot (marines vs air)."""
    others = [a for a in living(snap["allies"]) if a.get("role") != "heal" and a["id"] != unit["id"]]
    unique = 0
    special = 0
    for e in living(snap["enemies"]):
        if not _can_hit(unit, e):
            continue
        if not any(_can_hit(a, e) for a in others):
            unique += 1
        elif any(not _can_hit(a, e) for a in others):
            special += 1
    return unique * 10 + special


def _aa_label(unit: Dict[str, Any], snap: Dict[str, Any]) -> str:
    if "AIR" not in set(unit.get("valid_targets") or []):
        return "ground_only"
    if any(e.get("plane") == "AIR" for e in living(snap["enemies"])):
        if _unique_coverage(unit, snap) > 0:
            return "last_anti_air"
        return "anti_air"
    return "ground_only"


def _heal_target(snap: Dict[str, Any], healer: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Lowest HP-ratio wounded ally. Do not prefer whoever happens to be in max range;
    sitting at spawn on a scratched neighbour is a missed tank."""
    allies = [a for a in living(snap["allies"]) if a.get("role") != "heal"]
    wounded = [u for u in allies if u["hp"] < u["max_hp"] - 1]
    forced = snap.get("_heal_id")
    if forced is not None:
        hit = next((u for u in wounded if u["id"] == forced), None)
        if hit is not None:
            return hit
        hit = next((u for u in allies if u["id"] == forced), None)
        if hit is not None:
            return hit
    if not wounded:
        return None

    def key(u):
        ratio = u["hp"] / max(float(u["max_hp"]), 1e-6)
        d = hypot(healer, u) if healer is not None else 0.0
        return (ratio, d, u["hp"], u["id"])

    return min(wounded, key=key)


def _heal_cover(snap: Dict[str, Any], healer: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Who the healer should be on. Wounded first; else the body about to take fire."""
    target = _heal_target(snap, healer)
    if target is not None:
        return target
    allies = [a for a in living(snap["allies"]) if a.get("role") != "heal"]
    if not allies:
        return None
    enemies = living(snap["enemies"])
    if enemies:
        return min(
            allies,
            key=lambda a: (hypot(a, _nearest(a, enemies)), -_ehp(a), a["id"]),
        )
    return max(allies, key=lambda a: (_ehp(a), -a["id"]))


def _heal_leash(healer: Dict[str, Any], target: Dict[str, Any]) -> float:
    """Comfortable heal distance. Max range stands at spawn; glue inside this."""
    return max(2.6, _weapon_reach(healer, target) - 2.2)


def _heal_comfortable(healer: Dict[str, Any], target: Dict[str, Any]) -> bool:
    return hypot(healer, target) <= _heal_leash(healer, target) + 0.05


def _healer_would_overtake(healer: Dict[str, Any], target: Dict[str, Any], snap: Dict[str, Any]) -> bool:
    """Do not fly past the tank into their guns."""
    enemies = [e for e in living(snap["enemies"]) if e.get("role") != "heal"]
    if not enemies:
        return False
    nearest = _nearest(healer, enemies)
    if nearest is None:
        return False
    return hypot(healer, nearest) + 0.5 < hypot(target, nearest)


def _matchup(snap: Dict[str, Any]) -> str:
    return army_plan(snap)


def _unit_matchup(ally: Dict[str, Any], snap: Dict[str, Any]) -> str:
    plan = army_plan(snap)
    if ally.get("role") == "heal":
        return "heal"
    if plan == "cycle":
        return "immobile"
    if plan == "funnel":
        return "funnel"
    if plan == "detonate":
        if ally.get("kamikaze"):
            return "detonate"
        # Same-speed melee cannot outrun suicide units. Running as a clump chains the blast.
        if ally.get("role") == "melee":
            return "melee_brawl"
        return "evade_kami"
    if plan == "kite":
        return "kite"
    if plan == "fade":
        return "fade"
    if ally.get("role") == "melee":
        return "melee_brawl"
    return "ranged_trade"


def _hold_behind_tank(ally: Dict[str, Any], snap: Dict[str, Any], target: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Squishy ranged units do not overtake a tankier shooter of the same target."""
    if target is None or ally.get("role") != "ranged":
        return target
    # Ranged heavies with no allied melee always attack-move. If they hold,
    # lights walk past them. Mixed stalker+zealot still sits guns behind blades.
    if _body_band(ally) == "heavy" and not any(
        a.get("role") == "melee" for a in living(snap["allies"])
    ):
        return target
    tanks = [
        a
        for a in living(snap["allies"])
        if a["id"] != ally["id"]
        and a.get("role") != "heal"
        and _can_hit(a, target)
        and (_ehp(a) > _ehp(ally) + 20 or a.get("role") == "melee")
    ]
    if not tanks:
        return target
    tank = max(tanks, key=lambda a: (_ehp(a), a.get("range") or 0, -a["id"]))
    if hypot(ally, target) > _weapon_reach(ally, target) + 1.5:
        return target
    if hypot(ally, target) + 0.4 < hypot(tank, target):
        return None
    return target


def _tank_id(snap: Dict[str, Any]) -> Optional[int]:
    allies = living(snap["allies"])
    if not allies:
        return None
    return max(allies, key=lambda a: (a["hp"] + float(a.get("shield") or 0), -a["id"]))["id"]


def _edge_penalty(x: float, y: float, width: float, height: float) -> float:
    pen = 0.0
    if x < 3.5 or y < 3.5 or x > width - 3.5 or y > height - 3.5:
        pen -= 10
    if x < 1.6 or y < 1.6 or x > width - 1.6 or y > height - 1.6:
        pen -= 40
    return pen


def _group_away_key(snap: Dict[str, Any]) -> Optional[str]:
    """Walk away from melee as a blob, but do not kite into the map edge."""
    allies = living(snap["allies"])
    threats = [e for e in living(snap["enemies"]) if e.get("role") == "melee"] or living(snap["enemies"])
    if not allies or not threats:
        return None
    threat = {
        "x": sum(e["x"] for e in threats) / len(threats),
        "y": sum(e["y"] for e in threats) / len(threats),
    }
    width = float(snap.get("width") or 32)
    height = float(snap.get("height") or 32)
    best_key, best = None, -1e18
    for _act, (key, _heading, (dx, dy)) in WALK.items():
        score = 0.0
        runways = []
        for a in allies:
            nx = a["x"] + dx
            ny = a["y"] + dy
            score += ((nx - threat["x"]) ** 2 + (ny - threat["y"]) ** 2) ** 0.5
            score += _edge_penalty(nx, ny, width, height)
            if dx < 0:
                runways.append(nx)
            elif dx > 0:
                runways.append(width - nx)
            elif dy < 0:
                runways.append(ny)
            else:
                runways.append(height - ny)
        min_run = min(runways) if runways else 99.0
        if min_run < 8.0:
            score -= (8.0 - min_run) * 12.0
        if score > best:
            best, best_key = score, key
    return best_key


def _enemy_has_splash(snap: Dict[str, Any]) -> bool:
    return any(e.get("kamikaze") or e.get("splash") for e in living(snap["enemies"]))


def _unique_chase_target(ally: Dict[str, Any], snap: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Lane-assign melee so they do not reconverge into splash."""
    enemies = _hittable_enemies(snap, ally) or living(snap["enemies"])
    allies = [a for a in living(snap["allies"]) if a.get("role") != "heal"]
    if not enemies or not allies:
        return None
    ax, ay = _centroid(allies)
    ex, ey = _centroid(enemies)
    fx, fy = ex - ax, ey - ay
    n = (fx * fx + fy * fy) ** 0.5 or 1.0
    px, py = -fy / n, fx / n
    allies_s = sorted(allies, key=lambda u: (u["x"] * px + u["y"] * py, u["id"]))
    enemies_s = sorted(enemies, key=lambda u: (u["x"] * px + u["y"] * py, u["id"]))
    i = next((k for k, u in enumerate(allies_s) if u["id"] == ally["id"]), 0)
    if len(allies_s) == 1:
        return enemies_s[0]
    j = int(round(i * (len(enemies_s) - 1) / (len(allies_s) - 1)))
    return enemies_s[j]


def _should_spread(snap: Dict[str, Any]) -> bool:
    """Spread only vs enemy suicide units, and only if we have no bombs of our own."""
    if any(a.get("kamikaze") for a in living(snap["allies"])):
        return False
    return any(e.get("kamikaze") for e in living(snap["enemies"]))


def _min_ally_dist(snap: Dict[str, Any]) -> float:
    allies = living(snap["allies"])
    if len(allies) < 2:
        return 99.0
    return min(hypot(a, b) for i, a in enumerate(allies) for b in allies[i + 1 :])


def _ally_spacing(ally: Dict[str, Any], snap: Dict[str, Any]) -> float:
    others = [
        a
        for a in living(snap["allies"])
        if a["id"] != ally["id"] and a.get("role") != "heal"
    ]
    if not others:
        return 99.0
    return min(hypot(ally, o) for o in others)


def _spread_key(ally: Dict[str, Any], snap: Dict[str, Any]) -> Optional[str]:
    """Fan onto a perpendicular line vs suicide splash. Do not march the blob in."""
    if not _should_spread(snap):
        return None
    allies = [a for a in living(snap["allies"]) if a.get("role") != "heal"]
    enemies = living(snap["enemies"])
    if len(allies) < 2 or not enemies:
        return None
    if _ally_spacing(ally, snap) >= 4.0:
        return None
    width = float(snap.get("width") or 32)
    height = float(snap.get("height") or 32)
    kami = [e for e in enemies if e.get("kamikaze")] or enemies
    ax, ay = _centroid(allies)
    ex, ey = _centroid(kami)
    fx, fy = ex - ax, ey - ay
    fn = (fx * fx + fy * fy) ** 0.5 or 1.0
    ux, uy = fx / fn, fy / fn
    px, py = -uy, ux
    ordered = sorted(allies, key=lambda u: (u["x"] * px + u["y"] * py, u["id"]))
    i = next((k for k, u in enumerate(ordered) if u["id"] == ally["id"]), 0)
    n = len(ordered)
    gap = 4.0
    offset = (i - (n - 1) / 2.0) * gap
    # Stay on the current army line. Walking the whole blob forward chains the blast.
    tx = ax + offset * px
    ty = ay + offset * py
    tx = min(max(tx, 3.0), width - 3.0)
    ty = min(max(ty, 3.0), height - 3.0)
    return _walk_to_xy(ally, snap, tx, ty)


def _bomb_default(snap: Dict[str, Any]) -> Optional[str]:
    """step or hold when a non-suicide melee unit is within 0.6 of a bomb's safe line.
    None when the distance is already clear. Our own bombs do not open this."""
    if any(a.get("kamikaze") for a in living(snap["allies"])):
        return None
    bombs = [e for e in living(snap["enemies"]) if e.get("kamikaze")]
    allies = [a for a in living(snap["allies"]) if a.get("role") == "melee" and not a.get("kamikaze")]
    if not bombs or not allies:
        return None
    found = False
    step = False
    for ally in allies:
        bomb = _nearest(ally, bombs)
        if bomb is None:
            continue
        safe = _kami_safe_dist(ally, bomb)
        dist = hypot(ally, bomb)
        if abs(dist - safe) > 0.6:
            continue
        found = True
        if dist < safe:
            step = True
    if not found:
        return None
    return "step" if step else "hold"


def _melee_arrival(ally: Dict[str, Any], snap: Dict[str, Any]) -> Optional[float]:
    """Seconds until the nearest enemy melee reaches this unit. None if it cannot close."""
    melee = [e for e in living(snap["enemies"]) if e.get("role") == "melee"]
    nearest = _nearest(ally, melee)
    if nearest is None:
        return None
    speed = float(nearest.get("speed") or 0.0)
    if speed <= 0.05:
        return None
    gap = hypot(ally, nearest) - _weapon_reach(nearest, ally)
    return gap / speed


def _stand_default(snap: Dict[str, Any]) -> Optional[str]:
    """shoot or step when a gun's stand is within 0.15s of the 0.5s shot window.
    None when the decision is already clear. Default matches the current motor."""
    if _speed_advantage(snap) < 0.5:
        return None
    # Allied melee is the tank. Stepping the guns is a different fight, and Jev
    # doing it dropped a won mixed army to 1/5. Pure gun lines still get the window.
    if snap.get("_block_stand") or any(a.get("role") == "melee" for a in living(snap["allies"])):
        return None
    guns = [a for a in living(snap["allies"]) if a.get("role") == "ranged" and _ready(a)]
    found = False
    step = False
    for gun in guns:
        arrival = _melee_arrival(gun, snap)
        if arrival is None or not (0.35 <= arrival <= 0.65):
            continue
        nearest = _nearest(gun, [e for e in living(snap["enemies"]) if e.get("role") == "melee"])
        if nearest is not None and hypot(gun, nearest) <= _weapon_reach(nearest, gun) + 0.05:
            continue
        found = True
        if arrival <= 0.5:
            step = True
    if not found:
        return None
    return "step" if step else "shoot"


def _blade_pair(snap: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Two enemies in the same melee reach, distances within half a step."""
    allies = [a for a in living(snap["allies"]) if a.get("role") == "melee" and not a.get("kamikaze")]
    enemies = [e for e in living(snap["enemies"]) if e.get("role") != "heal"]
    for ally in allies:
        close = [
            e for e in enemies
            if _can_hit(ally, e) and hypot(ally, e) <= _weapon_reach(ally, e) + 0.05
        ]
        if len(close) < 2:
            continue
        close.sort(key=lambda e: (hypot(ally, e), e["id"]))
        if hypot(ally, close[1]) - hypot(ally, close[0]) <= 1.0:
            return [close[0], close[1]]
    return []


def _mark_pair(snap: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Equal-speed guns, two enemy melee within one shot. Kite maps keep their own jobs."""
    if _speed_advantage(snap) >= 0.5:
        return []
    if any(a.get("splash") for a in living(snap["allies"])):
        return []
    guns = [
        a for a in living(snap["allies"])
        if a.get("role") == "ranged" and not a.get("splash") and _ready(a)
    ]
    melee = [e for e in living(snap["enemies"]) if e.get("role") == "melee"]
    if len(guns) < 1 or len(melee) < 2:
        return []
    visible = []
    for enemy in melee:
        if any(_can_shoot(a, enemy, snap) for a in guns):
            visible.append(enemy)
    visible.sort(key=_hp_key)
    for i in range(len(visible) - 1):
        low, high = visible[i], visible[i + 1]
        both = [
            gun for gun in guns
            if _can_shoot(gun, low, snap) and _can_shoot(gun, high, snap)
        ]
        if not both:
            continue
        gap = _ehp(high) - _ehp(low)
        if 0 <= gap <= max(_shot_damage(gun, low) for gun in both) + 0.05:
            return [low, high]
    return []


def _shot_lets_melee_in(ally: Dict[str, Any], snap: Dict[str, Any]) -> bool:
    """True if standing 0.5s to fire lets any enemy melee connect."""
    melee = [e for e in living(snap["enemies"]) if e.get("role") == "melee"]
    if not melee:
        return False
    for enemy in melee:
        d = hypot(ally, enemy)
        their_reach = _weapon_reach(enemy, ally)
        their_speed = float(enemy.get("speed") or 0.0)
        if d - their_speed * 0.5 <= their_reach + 0.05:
            return True
    return False


def _peel_stand_ok(snap: Dict[str, Any], line: Optional[List[Dict[str, Any]]] = None) -> bool:
    """Peel is a blob: if any gun's stand lets blades in, nobody stands."""
    line = list(line) if line is not None else _fighters(snap, "ranged")
    line = [a for a in line if a.get("alive", True) and a.get("role") != "heal"]
    if not line:
        return False
    if _bucket_contact(snap, line) == "melee_on_us":
        return False
    melee = [e for e in living(snap["enemies"]) if e.get("role") == "melee"]
    if melee and any(_shot_lets_melee_in(a, snap) for a in line):
        return False
    return True


def _escape_key(ally: Dict[str, Any], snap: Dict[str, Any]) -> Optional[str]:
    """Walk the NESW step that most increases distance to nearest melee, not into the edge."""
    melee = [e for e in living(snap["enemies"]) if e.get("role") == "melee"]
    if not melee:
        return None
    nearest = _nearest(ally, melee)
    if nearest is None:
        return None
    width = float(snap.get("width") or 32)
    height = float(snap.get("height") or 32)
    cur = hypot(ally, nearest)
    best_key, best = None, -1e18
    for _act, (key, _heading, (dx, dy)) in WALK.items():
        nx, ny = ally["x"] + dx, ally["y"] + dy
        if not _walkable_at(snap, nx, ny):
            continue
        nd = ((nx - nearest["x"]) ** 2 + (ny - nearest["y"]) ** 2) ** 0.5
        score = nd - cur
        score += 0.15 * _edge_penalty(nx, ny, width, height)
        if dx < 0:
            run = nx
        elif dx > 0:
            run = width - nx
        elif dy < 0:
            run = ny
        else:
            run = height - ny
        if run < 8.0:
            score -= (8.0 - run) * 0.6
        if nx < 4 or ny < 4 or nx > width - 4 or ny > height - 4:
            score -= 3
        if score > best:
            best, best_key = score, key
    return best_key


def _walk_to_xy(ally: Dict[str, Any], snap: Dict[str, Any], tx: float, ty: float) -> Optional[str]:
    width = float(snap.get("width") or 32)
    height = float(snap.get("height") or 32)
    best_key, best = None, -1e18
    for _act, (key, _heading, (dx, dy)) in WALK.items():
        nx = ally["x"] + dx
        ny = ally["y"] + dy
        if not _walkable_at(snap, nx, ny):
            continue
        score = -((nx - tx) ** 2 + (ny - ty) ** 2)
        score += _edge_penalty(nx, ny, width, height)
        if nx < 5 or ny < 5 or nx > width - 5 or ny > height - 5:
            score -= 6
        if (ally["x"] < 6 and dx < 0) or (ally["y"] < 6 and dy < 0) or (
            ally["x"] > width - 6 and dx > 0
        ) or (ally["y"] > height - 6 and dy > 0):
            score -= 12
        if score > best:
            best, best_key = score, key
    return best_key


def _ring_slot_key(ally: Dict[str, Any], snap: Dict[str, Any]) -> Optional[str]:
    """Equal-speed kite walk.

    Two guns: orbit opposite sides of the blade they are fighting.
    A larger line: concave on the far side of the melee blob.
    In blades, step tangent (running straight away is equal-speed suicide).
    """
    melee = [e for e in living(snap["enemies"]) if e.get("role") == "melee"]
    guns = [a for a in living(snap["allies"]) if a.get("role") == "ranged"]
    if not melee or not guns:
        return None
    nearest = _nearest(ally, melee)
    if nearest is None:
        return None
    d = hypot(ally, nearest)
    desired = _weapon_reach(ally, nearest) - 0.2
    their_reach = _weapon_reach(nearest, ally)
    ax = ally["x"] - nearest["x"]
    ay = ally["y"] - nearest["y"]
    nrm = (ax * ax + ay * ay) ** 0.5 or 1.0
    ux, uy = ax / nrm, ay / nrm
    guns_s = sorted(guns, key=lambda a: a["id"])
    i = next(k for k, a in enumerate(guns_s) if a["id"] == ally["id"])
    n = len(guns_s)
    width = float(snap.get("width") or 32)
    height = float(snap.get("height") or 32)
    if n <= 2:
        sign = -1.0 if i == 0 else 1.0
        px, py = -uy * sign, ux * sign
        err = d - desired
        # Equal-speed radial away is matched by chase; only a tangent orbit
        # changes the heading so one gun is not the perpetual front.
        if err > 0.8:
            # Spiral in from opposite sides. Straight-in keeps both guns on one blade.
            wx, wy = -0.55 * ux + 0.85 * px, -0.55 * uy + 0.85 * py
        else:
            wx, wy = 0.08 * ux + 0.92 * px, 0.08 * uy + 0.92 * py
        best_key, best = None, -1e18
        for _act, (key, _heading, (dx, dy)) in WALK.items():
            nx = ally["x"] + dx
            ny = ally["y"] + dy
            if not _walkable_at(snap, nx, ny):
                continue
            score = dx * wx + dy * wy
            score += _edge_penalty(nx, ny, width, height)
            if nx < 5 or ny < 5 or nx > width - 5 or ny > height - 5:
                score -= 6
            if (ally["x"] < 6 and dx < 0) or (ally["y"] < 6 and dy < 0) or (
                ally["x"] > width - 6 and dx > 0
            ) or (ally["y"] > height - 6 and dy > 0):
                score -= 12
            if score > best:
                best, best_key = score, key
        return best_key
    mx, my = _centroid(melee)
    gx, gy = _centroid(guns)
    base = math.atan2(gy - my, gx - mx)
    span = min(math.pi, 0.55 * (n - 1))
    off = -span / 2 + span * i / max(n - 1, 1)
    ang = base + off
    return _walk_to_xy(ally, snap, mx + desired * math.cos(ang), my + desired * math.sin(ang))


# ----------------------------------------------------------------------
# Motor: job executors (code walks, Jev never does)
# ----------------------------------------------------------------------

def _pick_fire(pick, snap: Dict[str, Any]) -> Optional[int]:
    fid = snap.get("_focus_id")
    if fid is not None:
        act = pick(lambda k, _m: k == f"fire_E{fid}")
        if act is not None:
            return act
    return pick(lambda k, _m: k.startswith("fire_"))


def _equal_kite_act(ally, snap, pick):
    """Equal-speed move delta is speed*0.5, same as melee. Grid peel does not
    open a gap and skips shots; attack-move wins that trade. Keep closed."""
    return None



def _walk_stutter(ally: Dict[str, Any], snap: Dict[str, Any], pick):
    away = _group_away_key(snap)
    act = pick(lambda k, m: away is not None and k == away and not _walk_hits_edge(m))
    if act is None:
        ring = _ring_slot_key(ally, snap)
        act = pick(lambda k, m: ring is not None and k == ring and not _walk_hits_edge(m))
    if act is None:
        kite = _kite_walk_key(ally, snap)
        act = pick(lambda k, m: kite is not None and k == kite and not _walk_hits_edge(m))
    if act is None:
        esc = _escape_key(ally, snap)
        act = pick(lambda k, m: esc is not None and k == esc and not _walk_hits_edge(m))
    if act is None:
        act = pick(
            lambda k, m: k.startswith("walk_")
            and _rel(m) == "farther"
            and not _walk_hits_edge(m)
        )
    if act is None:
        act = pick(lambda k, _m: k == "hold")
    return act


def _execute_fade(ally: Dict[str, Any], snap: Dict[str, Any], pick) -> Optional[int]:
    """Extra-tank bio: heavies attack-move, lights hold the gun ring behind them."""
    fid = snap.get("_focus_id")
    target = next((e for e in living(snap["enemies"]) if e["id"] == fid), None) if fid is not None else None
    if target is None:
        target = resolve_focus("heaviest", snap) or _front_enemy(snap)
    if _body_band(ally) == "heavy":
        return None
    if (
        target is not None
        and _ready(ally)
        and _can_hit(ally, target)
        and _in_weapon_range(ally, target)
        and _can_target(snap, ally, target["id"])
    ):
        act = _pick_fire(pick, snap)
        if act is not None:
            return act
    if _hold_behind_tank(ally, snap, target) is None:
        away = _group_away_key(snap)
        act = pick(lambda k, m: away is not None and k == away and not _walk_hits_edge(m))
        if act is not None:
            return act
        return pick(lambda k, _m: k == "hold")
    if target is not None and not _in_weapon_range(ally, target):
        return pick(lambda k, _m: k == "hold")
    return pick(lambda k, _m: k == "hold")


def _execute_tanks_first(ally: Dict[str, Any], snap: Dict[str, Any], pick) -> Optional[int]:
    """Extra-tank bio: heavies attack-move, lights walk in but do not overtake."""
    fid = snap.get("_focus_id")
    target = next((e for e in living(snap["enemies"]) if e["id"] == fid), None) if fid is not None else None
    if target is None:
        target = resolve_focus("heaviest", snap) or _front_enemy(snap)
    if _body_band(ally) == "heavy":
        return None
    act = _pick_fire(pick, snap)
    if act is not None:
        return act
    if _hold_behind_tank(ally, snap, target) is None:
        return pick(lambda k, _m: k == "hold")
    act = pick(lambda k, _m: k.startswith("chase_"))
    if act is not None:
        return act
    return pick(lambda k, _m: k == "hold")


def _execute_stutter(ally: Dict[str, Any], snap: Dict[str, Any], pick) -> Optional[int]:
    """Kite compiler. Style comes from the kite exam; code only compiles it."""
    melee = [e for e in living(snap["enemies"]) if e.get("role") == "melee"]
    if not melee:
        return None
    nearest = _nearest(ally, melee)
    if nearest is None:
        return None
    in_blades = hypot(ally, nearest) <= _weapon_reach(nearest, ally) + 0.05
    in_range = _in_weapon_range(ally, nearest)
    d = hypot(ally, nearest)
    reach = _weapon_reach(ally, nearest)
    jobs = kite_jobs(snap)
    style = snap.get("_kite_style") or default_kite_style(jobs, snap)
    call = snap.get("_stand_call")
    arrival = _melee_arrival(ally, snap)
    if (
        call in {"shoot", "step"}
        and style not in {"bait_one", "peel_tagged"}
        and arrival is not None
        and 0.35 <= arrival <= 0.65
        and not in_blades
    ):
        if call == "shoot" and _ready(ally) and in_range:
            act = _pick_fire(pick, snap)
            if act is not None:
                return act
        if call == "step":
            walked = _walk_stutter(ally, snap, pick)
            if walked is not None:
                return walked
    if style == "bait_one":
        guns = [a for a in living(snap["allies"]) if a.get("role") == "ranged"]
        if len(guns) >= 2:
            bait = min(guns, key=lambda a: (hypot(a, nearest), a["id"]))
            if ally["id"] == bait["id"]:
                return _walk_stutter(ally, snap, pick)
    if style == "peel_tagged":
        stand_unsafe = in_blades
        cooling_unsafe = False
    elif style == "bait_one":
        stand_unsafe = in_blades
        keep = _if_we_keep_standing(snap, [ally])
        cooling_unsafe = (not _ready(ally)) and keep in {
            "already_in_blades",
            "melee_arrives_before_next_shot",
        }
    else:
        stand_unsafe = in_blades or _shot_lets_melee_in(ally, snap)
        keep = _if_we_keep_standing(snap, [ally])
        cooling_unsafe = (not _ready(ally)) and keep in {
            "already_in_blades",
            "melee_arrives_before_next_shot",
        }
    if _ready(ally) and in_range and not stand_unsafe:
        act = _pick_fire(pick, snap)
        if act is not None:
            return act
    if d > reach + 0.4 and not in_blades:
        act = pick(lambda k, _m: k.startswith("chase_"))
        if act is not None:
            return act
    if stand_unsafe or cooling_unsafe:
        return _walk_stutter(ally, snap, pick)
    return pick(lambda k, _m: k == "hold") or _walk_stutter(ally, snap, pick)


def _execute_concave(ally: Dict[str, Any], snap: Dict[str, Any], pick) -> Optional[int]:
    """Fan guns onto the far-side ring, then stutter-fire."""
    melee = [e for e in living(snap["enemies"]) if e.get("role") == "melee"]
    if not melee:
        return _execute_stutter(ally, snap, pick)
    nearest = _nearest(ally, melee)
    if nearest is None:
        return None
    in_blades = hypot(ally, nearest) <= _weapon_reach(nearest, ally) + 0.05
    enemy_guns = any(e.get("role") == "ranged" for e in living(snap["enemies"]))
    stand_unsafe = in_blades or (
        (not enemy_guns) and _shot_lets_melee_in(ally, snap)
    )
    if _ready(ally) and _in_weapon_range(ally, nearest) and not stand_unsafe:
        act = _pick_fire(pick, snap)
        if act is not None:
            return act
    ring = _ring_slot_key(ally, snap)
    act = pick(lambda k, m: ring is not None and k == ring and not _walk_hits_edge(m))
    if act is not None:
        return act
    return _walk_stutter(ally, snap, pick)


def _hold_range_key(ally: Dict[str, Any], snap: Dict[str, Any]) -> Optional[str]:
    """Walk onto our weapon-range ring vs melee. Does not attack-move (that overshoots)."""
    melee = [e for e in living(snap["enemies"]) if e.get("role") == "melee"]
    if not melee:
        return None
    nearest = _nearest(ally, melee)
    if nearest is None:
        return None
    d = hypot(ally, nearest)
    our_reach = _weapon_reach(ally, nearest)
    their_reach = _weapon_reach(nearest, ally)
    their_speed = float(nearest.get("speed") or 0.0)
    # Hug max gun range. Inward of that, equal-speed melee eats the 0.5s stand.
    desired = our_reach - 0.25
    safe = their_reach + their_speed * 0.55 + 0.35
    if desired < safe:
        desired = our_reach - 0.12
    ax = ally["x"] - nearest["x"]
    ay = ally["y"] - nearest["y"]
    n = (ax * ax + ay * ay) ** 0.5 or 1.0
    ux, uy = ax / n, ay / n
    allies = living(snap["allies"])
    cx, cy = _centroid(allies)
    cross = (ally["x"] - cx) * uy - (ally["y"] - cy) * ux
    sign = 1.0 if cross > 1e-6 else (-1.0 if cross < -1e-6 else (1.0 if ally["id"] % 2 == 0 else -1.0))
    px, py = -uy * sign, ux * sign
    err = d - desired
    # Grid steps are 2 units and melee also closes this tick. Do not walk in
    # if that overshoots the gun ring into blades.
    step_in = 2.0 + their_speed * 0.5
    if err > 0.7 and d - step_in >= desired - 0.45:
        wx, wy = -0.85 * ux + 0.15 * px, -0.85 * uy + 0.15 * py
    elif err < -0.35:
        wx, wy = 0.75 * ux + 0.25 * px, 0.75 * uy + 0.25 * py
    else:
        wx, wy = 0.05 * ux + 0.95 * px, 0.05 * uy + 0.95 * py
    width = float(snap.get("width") or 32)
    height = float(snap.get("height") or 32)
    best_key, best = None, -1e18
    for _act, (key, _heading, (dx, dy)) in WALK.items():
        nx = ally["x"] + dx
        ny = ally["y"] + dy
        score = dx * wx + dy * wy
        score += _edge_penalty(nx, ny, width, height)
        if nx < 5 or ny < 5 or nx > width - 5 or ny > height - 5:
            score -= 6
        if (ally["x"] < 6 and dx < 0) or (ally["y"] < 6 and dy < 0) or (
            ally["x"] > width - 6 and dx > 0
        ) or (ally["y"] > height - 6 and dy > 0):
            score -= 12
        if score > best:
            best, best_key = score, key
    return best_key


def _kite_walk_key(ally: Dict[str, Any], snap: Dict[str, Any]) -> Optional[str]:
    """Speed advantage: back up as a blob. Equal speed: orbit, do not run in a line."""
    threats = [e for e in living(snap["enemies"]) if e.get("role") == "melee"] or living(snap["enemies"])
    if not threats:
        return None
    nearest = _nearest(ally, threats)
    if nearest is None:
        return None
    ax = ally["x"] - nearest["x"]
    ay = ally["y"] - nearest["y"]
    n = (ax * ax + ay * ay) ** 0.5 or 1.0
    ux, uy = ax / n, ay / n
    allies = living(snap["allies"])
    cx, cy = _centroid(allies)
    cross = (ally["x"] - cx) * uy - (ally["y"] - cy) * ux
    if len(allies) <= 3:
        sign = 1.0 if ally["id"] % 2 == 0 else -1.0
    else:
        sign = 1.0 if cross > 1e-6 else (-1.0 if cross < -1e-6 else (1.0 if ally["id"] % 2 == 0 else -1.0))
    px, py = -uy * sign, ux * sign
    d = hypot(ally, nearest)
    reach = _weapon_reach(ally, nearest)
    if _speed_advantage(snap) >= 0.5:
        wx, wy = ux, uy
    else:
        # Equal speed: stay on a ring at weapon range and orbit. Do not run to the map edge.
        desired = max(2.6, reach - 0.35)
        err = d - desired
        if err > 1.0:
            wx, wy = -0.75 * ux + 0.25 * px, -0.75 * uy + 0.25 * py
        elif err < -0.5:
            wx, wy = 0.65 * ux + 0.35 * px, 0.65 * uy + 0.35 * py
        else:
            wx, wy = 0.1 * ux + 0.9 * px, 0.1 * uy + 0.9 * py
    width = float(snap.get("width") or 32)
    height = float(snap.get("height") or 32)
    best_key, best = None, -1e18
    for _act, (key, _heading, (dx, dy)) in WALK.items():
        nx = ally["x"] + dx
        ny = ally["y"] + dy
        score = dx * wx + dy * wy
        score += _edge_penalty(nx, ny, width, height)
        if nx < 5 or ny < 5 or nx > width - 5 or ny > height - 5:
            score -= 6
        # Do not walk further into an edge when already near it.
        if (ally["x"] < 6 and dx < 0) or (ally["y"] < 6 and dy < 0) or (
            ally["x"] > width - 6 and dx > 0
        ) or (ally["y"] > height - 6 and dy > 0):
            score -= 12
        if score > best:
            best, best_key = score, key
    return best_key


def _band(ally: Dict[str, Any], enemy: Dict[str, Any]) -> str:
    d = hypot(ally, enemy)
    reach = _weapon_reach(ally, enemy)
    melee_d = 1.35 + _radius(ally) + _radius(enemy)
    if d <= melee_d:
        return "melee"
    if d <= reach:
        return "in_weapon_range"
    if d <= reach + 1.6:
        return "almost"
    return "far"


def _walk_effect(
    ally: Dict[str, Any],
    enemies: List[Dict[str, Any]],
    dx: float,
    dy: float,
    ctx: Dict[str, Any],
) -> Dict[str, Any]:
    matchup = ctx["matchup"]
    melee = [e for e in enemies if e.get("role") == "melee"]
    static = [e for e in enemies if e.get("role") == "static"]
    kami = [e for e in enemies if e.get("kamikaze")]
    if matchup == "evade_kami":
        focus = _nearest(ally, kami) or _nearest(ally, enemies)
    elif matchup == "immobile":
        focus = _nearest(ally, static) or _nearest(ally, enemies)
    else:
        focus = _nearest(ally, melee or static or enemies)
    out: Dict[str, Any] = {"step": 2, "matchup": matchup, "tank": ctx.get("tank")}
    nx = float(ally["x"]) + dx
    ny = float(ally["y"]) + dy
    width = float(ctx.get("width") or 32)
    height = float(ctx.get("height") or 32)
    hits_edge = nx < 1.4 or ny < 1.4 or nx > width - 1.4 or ny > height - 1.4
    dest = ctx.get("rally")
    if dest is not None:
        cur_r = ((ally["x"] - dest[0]) ** 2 + (ally["y"] - dest[1]) ** 2) ** 0.5
        nxt_r = ((nx - dest[0]) ** 2 + (ny - dest[1]) ** 2) ** 0.5
        rel_r = "closer" if nxt_r + 0.15 < cur_r else ("farther" if nxt_r > cur_r + 0.15 else "sideways")
        out["vs_rally"] = rel_r
        snap = ctx.get("snap")
        if snap is not None:
            out["stays_pocket"] = _in_pocket_at(snap, nx, ny)
    if focus is None:
        out["vs_nearest"] = "no living enemy"
        return out
    cur = hypot(ally, focus)
    nxt = ((nx - focus["x"]) ** 2 + (ny - focus["y"]) ** 2) ** 0.5
    if nxt + 0.15 < cur:
        rel = "closer"
    elif nxt > cur + 0.15:
        rel = "farther"
    else:
        rel = "sideways"
    if matchup == "ranged_trade" and rel == "farther":
        verdict = "Bad in an equal-range trade: you skip the next shot."
    elif matchup == "ranged_trade" and rel == "closer":
        verdict = "Closes remaining distance. Useful only if this unit cannot shoot yet."
    elif matchup == "kite" and rel == "farther":
        verdict = "Good kite: you are faster than melee, this opens a gap."
    elif matchup == "kite" and rel == "closer":
        verdict = "Bad kite: walks into zealot/zergling range."
    elif matchup == "melee_brawl" and rel == "farther":
        verdict = "Leaves the brawl. Bad unless peeling."
    elif matchup == "melee_brawl" and rel == "closer":
        verdict = "Closes into melee."
    elif matchup == "immobile" and rel == "farther":
        verdict = "Leaves the building's range."
    elif matchup == "immobile" and rel == "closer":
        verdict = "Walks toward the building."
    elif matchup == "evade_kami" and rel == "farther":
        verdict = "Away from the exploding unit."
    elif matchup == "evade_kami" and rel == "closer":
        verdict = "Walks into the explosion."
    else:
        verdict = "Side step."
    if hits_edge:
        verdict = verdict + " This step hits the map edge; melee can pin you here."
    out["vs_nearest"] = {
        "id": f"E{focus['id']}",
        "role": focus.get("role"),
        "from": round(cur, 1),
        "to": round(nxt, 1),
        "relation": rel,
        "edge": hits_edge,
        "verdict": verdict,
    }
    return out


def _rel(meta: Dict[str, Any]) -> str:
    vs = meta.get("vs_nearest")
    if isinstance(vs, dict):
        return str(vs.get("relation") or "")
    return ""



def _melee_dist(unit: Dict[str, Any], snap: Dict[str, Any]) -> float:
    melee = [e for e in living(snap["enemies"]) if e.get("role") == "melee"]
    if not melee:
        return 99.0
    return min(hypot(unit, e) for e in melee)


def _blob_span(snap: Dict[str, Any]) -> float:
    ranged = [a for a in living(snap["allies"]) if a.get("role") == "ranged"]
    if len(ranged) < 2:
        return 0.0
    ds = [_melee_dist(a, snap) for a in ranged]
    return round(max(ds) - min(ds), 1)


def _group_volley_ready(snap: Dict[str, Any]) -> bool:
    ranged = [a for a in living(snap["allies"]) if a.get("role") == "ranged"]
    melee = [e for e in living(snap["enemies"]) if e.get("role") == "melee"]
    if not ranged or not melee:
        return True
    in_range = []
    for a in ranged:
        nearest = _nearest(a, melee)
        if nearest is not None and hypot(a, nearest) <= _weapon_reach(a, nearest) + 0.05:
            in_range.append(a)
    if not in_range:
        return True
    return all(_ready(a) for a in in_range)


def _prune_options(options: List[Tuple[int, str, Dict[str, Any]]], ctx: Dict[str, Any]):
    if len(options) <= 1:
        return options
    matchup = ctx["matchup"]
    has_fire = any(k.startswith("fire_") for _, k, _ in options)
    has_chase = any(k.startswith("chase_") for _, k, _ in options)
    has_aim = any(k.startswith("hold_aim_") or k.startswith("stand_cooling_") for _, k, _ in options)
    need_heal = any(k.startswith("heal_") and m.get("needs_heal") for _, k, m in options)
    keep = []
    for act, key, meta in options:
        rel = _rel(meta)
        drop = False
        if matchup == "heal":
            if key.startswith("heal_"):
                drop = (need_heal and not meta.get("needs_heal")) or (not need_heal)
            elif need_heal and (key == "hold" or key.startswith("chase_") or key.startswith("fire_")):
                drop = True
            elif key.startswith("walk_") and (not ctx.get("wounded") or rel == "farther"):
                drop = True
            elif (not ctx.get("wounded")) and key.startswith("chase_"):
                drop = True
        elif matchup == "melee_brawl":
            spread = ctx.get("spread_key")
            spread_ok = bool(spread) and any(k == spread for _, k, _ in options)
            if ctx.get("must_spread") and spread_ok:
                drop = key != spread
            elif has_fire and not key.startswith("fire_"):
                drop = True
            elif spread_ok and not has_fire:
                drop = key != spread
            elif (not has_fire) and has_aim and not (
                key.startswith("hold_aim_") or key.startswith("stand_cooling_")
            ):
                drop = True
            elif (not has_fire) and (not has_aim) and has_chase and not key.startswith("chase_"):
                drop = True
        elif matchup == "ranged_trade":
            if has_fire and not key.startswith("fire_"):
                drop = True
            elif (not has_fire) and has_aim and not (
                key.startswith("hold_aim_") or key.startswith("stand_cooling_")
            ):
                drop = True
            elif (
                (not has_fire)
                and (not has_aim)
                and ctx.get("outrange_melee")
                and not ctx.get("allied_melee")
            ):
                d_melee = float(ctx.get("d_melee") or 99)
                reach = float(ctx.get("weapon_reach") or 6)
                if d_melee <= reach + 0.8:
                    drop = key.startswith("chase_") or key.startswith("walk_")
                elif has_chase:
                    drop = not key.startswith("chase_")
            elif (not has_fire) and (not has_aim) and has_chase:
                drop = not key.startswith("chase_")
        elif matchup in {"kite", "fade"}:
            edge = isinstance(meta.get("vs_nearest"), dict) and bool(meta["vs_nearest"].get("edge"))
            d_melee = float(ctx.get("d_melee") or 99)
            reach = float(ctx.get("weapon_reach") or 6)
            speed_ok = float(ctx.get("speed_adv") or 0) >= 0.5
            almost = d_melee <= reach + 2.0
            too_close = d_melee <= 2.2
            away = ctx.get("group_away")
            away_ok = bool(away) and any(k == away for _, k, _ in options)
            group_d = float(ctx.get("group_d_melee") or d_melee)
            group_almost = group_d <= reach + 2.0
            if speed_ok:
                if ctx["ready"] and has_fire:
                    drop = not key.startswith("fire_")
                elif not ctx["ready"]:
                    threat_close = bool(ctx.get("this_in_shot")) or d_melee <= 6.8
                    if threat_close:
                        if key == "hold" or key.startswith("hold_aim_") or key.startswith("chase_") or key.startswith("stand_cooling_"):
                            drop = True
                        if key.startswith("walk_") and (rel != "farther" or edge):
                            drop = True
                        if key.startswith("walk_") and away_ok and key != away:
                            drop = True
                    else:
                        drop = key.startswith("walk_") or (key == "hold" and (has_aim or has_chase))
                else:
                    drop = key.startswith("hold_aim_") or (key.startswith("walk_") and rel == "farther") or (
                        key == "hold" and has_chase
                    )
            else:
                threat = float(ctx.get("threat_reach") or 1.0)
                too_far = d_melee > reach + 3.2
                group_in_melee = group_d <= threat + 0.02
                blob_apart = float(ctx.get("blob_span") or 0.0) > 2.0
                volley = bool(ctx.get("group_ready"))
                if blob_apart and d_melee > threat + 0.02:
                    if too_far and has_chase:
                        drop = not key.startswith("chase_")
                    else:
                        drop = key.startswith("fire_") or key.startswith("chase_") or key.startswith("walk_")
                elif group_in_melee:
                    if key.startswith("fire_") or key.startswith("chase_") or key.startswith("hold_aim_") or key.startswith("stand_cooling_") or key == "hold":
                        drop = True
                    if key.startswith("walk_") and away_ok and key != away:
                        drop = True
                    if key.startswith("walk_") and edge:
                        drop = True
                elif volley and has_fire and d_melee > threat + 0.02:
                    drop = not key.startswith("fire_")
                elif too_far:
                    if has_chase:
                        drop = not key.startswith("chase_")
                    else:
                        drop = key.startswith("walk_") or (key == "hold" and has_aim)
                elif d_melee > threat + 0.02 and not ctx.get("this_in_shot") and volley:
                    drop = key.startswith("fire_") or key.startswith("chase_") or key.startswith("walk_")
                else:
                    if key.startswith("fire_") or key.startswith("chase_") or key.startswith("hold_aim_") or key.startswith("stand_cooling_") or key == "hold":
                        drop = True
                    if key.startswith("walk_") and away_ok and key != away:
                        drop = True
                    if key.startswith("walk_") and edge:
                        drop = True
        elif matchup == "immobile":
            if ctx.get("finish_now"):
                if has_fire:
                    drop = not key.startswith("fire_")
                elif has_aim:
                    drop = not (key.startswith("hold_aim_") or key.startswith("stand_cooling_"))
                elif has_chase:
                    drop = not key.startswith("chase_")
                else:
                    drop = key.startswith("walk_") and rel == "farther"
            elif ctx["ready"] and has_fire:
                drop = not key.startswith("fire_")
            elif (not ctx["ready"]) and ctx.get("this_in_shot"):
                if ctx.get("safe"):
                    drop = key.startswith("walk_") or key.startswith("chase_")
                else:
                    drop = not (key.startswith("walk_") and rel == "farther")
            elif ctx.get("may_approach") and has_chase:
                drop = not key.startswith("chase_")
            else:
                drop = key.startswith("walk_") or key.startswith("chase_")
        elif matchup == "funnel":
            toward = ctx.get("toward_rally")
            toward_ok = bool(toward) and any(k == toward for _, k, _ in options)
            back = ctx.get("toward_enemy")
            back_ok = bool(back) and any(k == back for _, k, _ in options)
            near = bool(ctx.get("near_rally"))
            too_deep = bool(ctx.get("too_deep"))
            if has_fire:
                drop = not key.startswith("fire_")
            elif near:
                drop = not (
                    key.startswith("fire_")
                    or key.startswith("hold_aim_")
                    or key.startswith("stand_cooling_")
                    or key == "hold"
                )
            elif too_deep:
                drop = not (key.startswith("walk_") and (not back_ok or key == back))
            elif toward_ok:
                drop = key != toward
            else:
                drop = not (key.startswith("walk_") and meta.get("vs_rally") == "closer")
        elif matchup == "detonate":
            if has_fire:
                drop = not key.startswith("fire_")
            elif has_chase:
                drop = not key.startswith("chase_")
        elif matchup == "evade_kami":
            d_kami = float(ctx.get("d_kami") or 99)
            if d_kami <= 6.5:
                drop = not (key.startswith("walk_") and rel == "farther")
            else:
                drop = key.startswith("chase_") or key.startswith("fire_") or key.startswith("walk_")
        if not drop:
            keep.append((act, key, meta))
    if not keep and matchup == "funnel":
        keep = [(a, k, m) for a, k, m in options if k == "hold"] or [
            (a, k, m) for a, k, m in options if k.startswith("walk_")
        ]
    if not keep and matchup in {"kite", "fade"}:
        keep = [
            (a, k, m)
            for a, k, m in options
            if k.startswith("walk_")
            and _rel(m) == "farther"
            and not (isinstance(m.get("vs_nearest"), dict) and m["vs_nearest"].get("edge"))
        ]
    return keep or options


def legal_options(ally: Dict[str, Any], snap: Dict[str, Any], prune: bool = True) -> List[Tuple[int, str, Dict[str, Any]]]:
    enemies = living(snap["enemies"])
    allies = living(snap["allies"])
    row = snap["avail"][ally["id"]]
    ready = _ready(ally)
    healer = ally.get("role") == "heal"
    focus = _weakest_in_shot(snap)
    matchup = _unit_matchup(ally, snap)
    tank = _tank_id(snap)
    this_in_shot = any(_in_weapon_range(ally, e) for e in enemies if ally.get("role") != "heal")
    static_e = [e for e in enemies if e.get("role") == "static"]
    nearest_static = _nearest(ally, static_e)
    d_static = hypot(ally, nearest_static) if nearest_static else 99.0
    our_reach = _weapon_reach(ally, nearest_static) if nearest_static else 6.0
    spine_reach = (
        float(nearest_static.get("range") or 7.0) + _radius(ally) + _radius(nearest_static)
        if nearest_static
        else 8.0
    )
    weakest_e = min(enemies, key=_hp_key) if enemies else None
    wounded = [u for u in allies if u["id"] != ally["id"] and u["hp"] < u["max_hp"] - 1]
    kami_e = [e for e in enemies if e.get("kamikaze")]
    densest = _densest_enemy(snap)
    ap = tuple(snap.get("attack_point") or snap.get("center") or (16.0, 16.0))
    partner_engaged = False
    may_approach = ready
    if matchup == "immobile" and nearest_static is not None:
        others = [a for a in allies if a["id"] != ally["id"]]
        partner_engaged = any(hypot(a, nearest_static) <= spine_reach + 0.4 for a in others)
        closest = min(allies, key=lambda a: (hypot(a, nearest_static), a["id"]))
        is_approach_tank = closest["id"] == ally["id"]
        speed = max(float(ally.get("speed") or 0.0), 0.1)
        time_to_range = max(0.0, d_static - our_reach) / speed
        ready_enough = float(ally.get("cd") or 0) <= time_to_range + 0.05
        last_man = len(allies) == 1
        my_shot = _shot_damage(ally, nearest_static)
        spine_shot = _shot_damage(nearest_static, ally)
        building_ehp = _ehp(nearest_static)
        volley = sum(_shot_damage(a, nearest_static) for a in allies if a.get("role") != "heal")
        skip_stagger = last_man or building_ehp <= volley * 3 + 8
        fragile = _ehp(ally) <= spine_shot + 1
        if last_man:
            may_approach = ready
        elif fragile and others:
            may_approach = False
        else:
            may_approach = (skip_stagger or is_approach_tank or partner_engaged) and (
                ready or ready_enough
            )
    finish_now = False
    if nearest_static is not None:
        my_shot = _shot_damage(ally, nearest_static)
        ehp = _ehp(nearest_static)
        finish_now = ready and ehp <= my_shot + 0.5
    in_pocket = _in_pocket(snap)
    too_deep = _too_deep(snap)
    brawl_flag = snap.get("_brawl_now")
    # Physics owns the mouth: never brawl in the wide room. Jev may only brawl once rear is covered.
    near_rally = in_pocket
    if brawl_flag is True and _pocket_label(snap) in {"in_pocket", "in_neck"}:
        near_rally = True
    enemy_xy = _centroid(enemies) if enemies else None
    ctx = {
        "matchup": matchup,
        "tank": None if tank is None else f"U{tank}",
        "is_tank": tank == ally["id"],
        "anyone_in_shot": focus is not None,
        "this_in_shot": this_in_shot,
        "ready": ready,
        "soon": _soon(ally),
        "dead_zone": matchup == "immobile"
        and (our_reach + 0.05 < d_static <= spine_reach + 0.35)
        and not this_in_shot,
        "safe": matchup == "immobile" and d_static > spine_reach + 0.05,
        "near_rally": near_rally,
        "too_deep": too_deep and not near_rally,
        "d_static": round(d_static, 1),
        "may_approach": may_approach,
        "finish_now": finish_now,
        "group_away": (
            _group_away_key(snap)
        )
        if matchup in {"kite", "fade"}
        or (
            matchup == "ranged_trade"
            and _range_advantage(snap) >= 2.0
            and not any(a.get("role") == "melee" for a in allies)
            and _speed_advantage(snap) >= -0.2
        )
        else None,
        "spread_key": _spread_key(ally, snap) if matchup == "melee_brawl" else None,
        "must_spread": bool(
            matchup == "melee_brawl"
            and _should_spread(snap)
            and _min_ally_dist(snap) < 5.0
        ),
        "speed_adv": _speed_advantage(snap),
        "outrange_melee": _range_advantage(snap) >= 2.0,
        "allied_melee": any(a.get("role") == "melee" for a in allies),
        "d_melee": round(
            min((hypot(ally, e) for e in enemies if e.get("role") == "melee"), default=99.0), 1
        ),
        "threat_reach": round(
            (
                _weapon_reach(
                    min(
                        (e for e in enemies if e.get("role") == "melee"),
                        key=lambda e: hypot(ally, e),
                    ),
                    ally,
                )
                if any(e.get("role") == "melee" for e in enemies)
                else 1.0
            ),
            2,
        ),
        "blob_span": _blob_span(snap),
        "group_ready": _group_volley_ready(snap),
        "group_d_melee": round(
            min(
                (
                    hypot(a, e)
                    for a in allies
                    for e in enemies
                    if e.get("role") == "melee"
                ),
                default=99.0,
            ),
            1,
        ),
        "d_any": round(min((hypot(ally, e) for e in enemies), default=99.0), 1),
        "d_kami": round(min((hypot(ally, e) for e in kami_e), default=99.0), 1),
        "width": snap.get("width") or 32,
        "height": snap.get("height") or 32,
        "wounded": bool(wounded),
        "healer": healer,
        "weapon_reach": round(
            _weapon_reach(ally, _nearest(ally, enemies)) if enemies else our_reach, 1
        ),
        "rally": ap,
        "snap": snap,
        "toward_rally": _army_toward_key(snap, ap),
        "toward_enemy": None if enemy_xy is None else _army_toward_key(snap, enemy_xy),
    }

    forced_focus = None
    fid = snap.get("_focus_id")
    if fid is not None:
        forced_focus = next((e for e in enemies if e["id"] == fid), None)
    shootable = [
        e
        for e in enemies
        if (not healer)
        and _can_hit(ally, e)
        and _in_weapon_range(ally, e)
        and _can_target(snap, ally, e["id"])
    ]
    shot_target = None
    planned = None
    laser_body = None
    lid = snap.get("_laser_id")
    if (
        lid is not None
        and ally.get("splash")
        and not ally.get("kamikaze")
        and float(ally.get("beam_width") or 0) > 0
    ):
        laser_body = next((e for e in enemies if e["id"] == lid), None)
    splash_melee = matchup == "melee_brawl" and _should_spread(snap)
    pick_bomb = (
        (not ally.get("kamikaze"))
        and any(e.get("kamikaze") for e in enemies)
        and not any(a.get("kamikaze") for a in allies)
    )
    isolated_bomb = _isolated_kami(snap) if pick_bomb else None
    if shootable:
        if laser_body is not None and any(e["id"] == laser_body["id"] for e in shootable):
            shot_target = laser_body
        elif ally.get("kamikaze"):
            if densest is not None and any(e["id"] == densest["id"] for e in shootable):
                shot_target = densest
            else:
                shot_target = min(shootable, key=lambda e: (hypot(ally, e), e["id"]))
        elif pick_bomb:
            kami_shot = [e for e in shootable if e.get("kamikaze")]
            bomb = _snipe_bomb(snap)
            if bomb is not None and any(e["id"] == bomb["id"] for e in shootable):
                shot_target = bomb
            elif isolated_bomb is not None and any(e["id"] == isolated_bomb["id"] for e in shootable):
                shot_target = isolated_bomb
            elif kami_shot:
                shot_target = min(kami_shot, key=lambda e: (hypot(ally, e), e["id"]))
            else:
                shot_target = min(shootable, key=lambda e: (hypot(ally, e), e["id"]))
        elif splash_melee:
            shot_target = min(shootable, key=lambda e: (hypot(ally, e), e["id"]))
        elif ally.get("role") == "melee" and not ally.get("kamikaze") and snap.get("_blade_prefer") is not None and any(
            e["id"] == snap.get("_blade_prefer") for e in shootable
        ):
            shot_target = next(e for e in shootable if e["id"] == snap.get("_blade_prefer"))
        elif (planned := _planned_shot(ally, snap, shootable)) is not None:
            shot_target = planned
        elif forced_focus is not None and any(e["id"] == forced_focus["id"] for e in shootable):
            shot_target = forced_focus
        elif focus is not None and any(e["id"] == focus["id"] for e in shootable):
            shot_target = focus
        else:
            shot_target = min(shootable, key=_hp_key)
        if (
            shot_target is not None
            and planned is None
            and _surplus_gun(ally, snap, shot_target)
            and not splash_melee
            and not ally.get("kamikaze")
            and laser_body is None
        ):
            others = [e for e in shootable if e["id"] != shot_target["id"]]
            if others:
                shot_target = min(others, key=_hp_key)
    chase_target = None
    hittable = _hittable_enemies(snap, ally)
    chase_pool = hittable or enemies
    if laser_body is not None and not _in_weapon_range(ally, laser_body):
        chase_target = _hold_behind_tank(ally, snap, laser_body)
    elif matchup == "detonate":
        chase_target = densest or _nearest(ally, enemies) or weakest_e
    elif pick_bomb:
        chase_target = _snipe_bomb(snap) or isolated_bomb or _nearest(ally, [e for e in chase_pool if e.get("kamikaze")]) or _nearest(ally, chase_pool)
    elif matchup == "funnel" and ctx.get("near_rally"):
        chase_target = None
    elif splash_melee:
        chase_target = _unique_chase_target(ally, snap) or _nearest(ally, chase_pool)
    elif matchup == "ranged_trade" and not shootable:
        cand = forced_focus if forced_focus is not None and _can_hit(ally, forced_focus) else None
        cand = cand or (focus if focus is not None and _can_hit(ally, focus) else None)
        cand = cand or _nearest(ally, chase_pool)
        chase_target = _hold_behind_tank(ally, snap, cand)
    elif matchup not in {"evade_kami", "funnel", "heal"}:
        cand = forced_focus if forced_focus is not None and _can_hit(ally, forced_focus) else None
        chase_target = cand or (focus if focus is not None and _can_hit(ally, focus) else None) or _front_enemy(snap)
        if chase_target is not None and not _can_hit(ally, chase_target):
            chase_target = _nearest(ally, chase_pool)
        chase_target = _hold_behind_tank(ally, snap, chase_target)
    preferred_heal = _heal_cover(snap, ally) if healer else None

    out: List[Tuple[int, str, Dict[str, Any]]] = []
    for a, ok in enumerate(row):
        if not ok or a == 0:
            continue
        if a == 1:
            out.append(
                (
                    1,
                    "hold",
                    {
                        "does": "Stand still without an attack command. Deals 0, and will not shoot when the cooldown finishes.",
                        "verdict": "Correct only if nobody should be firing, chasing, or kiting.",
                    },
                )
            )
            continue
        if a in WALK:
            key, heading, (dx, dy) = WALK[a]
            effect = _walk_effect(ally, enemies, dx, dy, ctx)
            if healer:
                tgt = _nearest(ally, wounded or [u for u in allies if u["id"] != ally["id"]])
                if tgt is not None:
                    cur = hypot(ally, tgt)
                    nxt = ((ally["x"] + dx - tgt["x"]) ** 2 + (ally["y"] + dy - tgt["y"]) ** 2) ** 0.5
                    effect["vs_wounded_ally"] = {
                        "id": f"U{tgt['id']}",
                        "relation": "closer"
                        if nxt + 0.15 < cur
                        else ("farther" if nxt > cur + 0.15 else "sideways"),
                    }
            out.append(
                (
                    a,
                    key,
                    {
                        "does": f"Walk {heading} about 2 units. Does not shoot this tick.",
                        **effect,
                    },
                )
            )
            continue
        tid = a - 6
        if healer:
            tgt = next((u for u in allies if u["id"] == tid), None)
            if tgt is None:
                continue
            if preferred_heal is not None and tgt["id"] != preferred_heal["id"]:
                continue
            missing = tgt["hp"] < tgt["max_hp"] - 1
            out.append(
                (
                    a,
                    f"heal_U{tid}",
                    {
                        "does": "Heal this allied unit this tick."
                        if ready
                        else "Heal command while cooling: stands and heals 0 this tick.",
                        "target": f"U{tid}",
                        "hp": round(tgt["hp"], 1),
                        "hp_max": round(tgt["max_hp"], 1),
                        "needs_heal": missing,
                        "weapon": "ready" if ready else "cooling",
                        "verdict": "Correct if this ally is wounded."
                        if missing
                        else "This ally is already full health.",
                    },
                )
            )
            continue
        enemy = next((e for e in enemies if e["id"] == tid), None)
        if enemy is None:
            continue
        in_range = _in_weapon_range(ally, enemy)
        tgt = f"E{tid} {enemy.get('name', enemy['type'])} {enemy.get('role')}"
        hp = round(_ehp(enemy), 1)
        band = _band(ally, enemy)
        dmg = round(_shot_damage(ally, enemy), 1)
        if ready and in_range:
            if shot_target is None or enemy["id"] != shot_target["id"]:
                continue
            out.append(
                (
                    a,
                    f"fire_E{tid}",
                    {
                        "does": "Shoot NOW. In weapon range, weapon READY. Deals damage this tick.",
                        "target": tgt,
                        "hp": hp,
                        "band": band,
                        "shot_damage": dmg,
                        "kills": hp <= dmg,
                        "lowest_hp_currently_shootable": bool(focus and focus["id"] == enemy["id"]),
                        "verdict": "Default whenever a shot is available.",
                    },
                )
            )
        elif in_range:
            if shot_target is None or enemy["id"] != shot_target["id"]:
                continue
            out.append(
                (
                    a,
                    f"hold_aim_E{tid}",
                    {
                        "does": "Stand and keep the attack command. Cooling: 0 damage this tick, fires when cooldown hits 0.",
                        "target": tgt,
                        "hp": hp,
                        "band": band,
                        "lowest_hp_currently_shootable": bool(focus and focus["id"] == enemy["id"]),
                        "verdict": "Correct in a DPS trade. Vs faster-kite, walk farther instead.",
                    },
                )
            )
        else:
            if chase_target is None or enemy["id"] != chase_target["id"]:
                continue
            out.append(
                (
                    a,
                    f"chase_E{tid}",
                    {
                        "does": "Attack-move: walk toward this enemy and shoot when you enter range. NOT a shot this tick.",
                        "target": tgt,
                        "hp": hp,
                        "band": band,
                        "lowest_hp_currently_shootable": False,
                        "verdict": "Use to close from outside range.",
                    },
                )
            )
    return _prune_options(out, ctx) if prune else out


def _unit_record(unit: Dict[str, Any], snap: Dict[str, Any], prefix: str) -> Dict[str, Any]:
    rec = {
        "id": f"{prefix}{unit['id']}",
        "kind": unit.get("name") or unit["type"],
        "role": unit.get("role"),
        "hp": round(float(unit["hp"]), 1),
        "hp_max": round(float(unit["max_hp"]), 1),
        "pos": [round(float(unit["x"]), 1), round(float(unit["y"]), 1)],
    }
    sh = float(unit.get("shield") or 0)
    if float(unit.get("max_shield") or 0) > 0:
        rec["shield"] = round(sh, 1)
    if prefix == "U":
        rec["weapon"] = "ready" if _ready(unit) else "cooling"
        rec["last"] = last_action_name(snap, unit["id"])
        rec["hit"] = bool(unit.get("hit"))
    else:
        rec["immobile"] = unit.get("role") == "static"
        rec["hit"] = bool(unit.get("hit"))
        rec["kamikaze"] = bool(unit.get("kamikaze"))
    return rec


# ----------------------------------------------------------------------
# Exam criteria text
# ----------------------------------------------------------------------

MATCHUP_RULES = {
    "ranged_trade": (
        "Equal-range trade. If fire_* is listed, pick it. "
        "If cooling in range, pick hold_aim_*. If nobody is in range, pick chase_* on the focus. Do not walk away."
    ),
    "melee_brawl": "Melee brawl. Pick fire_* or chase_*. Do not walk away from the fight.",
    "kite": (
        "Kite melee. If fire_* is listed, pick it. If a walk is listed, take it. "
        "Do not chase once they are near weapon range: that overshoots into melee."
    ),
    "fade": (
        "Outnumbered equal-range. If fire_* is listed, pick it. "
        "If cooling in range, walk farther as a group. If out of range, chase the focus."
    ),
    "immobile": (
        "Immobile building that outranges you. If fire_* is listed, pick it. "
        "If cooling in its range, walk farther. If the gun will be ready this step, chase back in."
    ),
    "funnel": (
        "Outnumbered melee. Walk as one blob toward the rally until the pocket is on the far side of the neck. "
        "If fire_* is listed, a melee unit is already on you: take it. Do not stop at the wide mouth."
    ),
    "detonate": "Suicide unit. Chase the densest clump and fire_* to explode.",
    "evade_kami": "Enemy suicide units are alive. Walk farther from them. Do not crash the clump.",
    "heal": "Healer. Pick heal_* on a wounded ally. If nobody is wounded, stay near the army.",
}


PLAN_CRITERIA = {
    "commit": (
        "Attack-move the whole army onto one focus. Correct for equal-range trades "
        "and for mixed armies that include your own melee, because kiting would abandon those melee. "
        "Wrong if you are a faster ranged army with NO allied melee against slower melee: you will stand in their range and die. "
        "Wrong if you are a tiny all-melee pack against a huge melee swarm in the open."
    ),
    "kite": (
        "You are ranged, you outrange or outrun their melee, and have no allied melee to abandon. "
        "Fire only at the edge of range. If they are already close, walk; do not chase into melee. "
        "If you are faster, back up as a blob. If speeds are even, the whole blob fires together "
        "then walks away together while melee swings; do not orbit and do not stand in melee. "
        "Wrong if both sides are ranged, or if you have melee of your own."
    ),
    "cycle": (
        "The enemy is an immobile building that outranges you. Fire when ready, walk out of its range while cooling, "
        "walk back in when the gun is about to be ready. If the building is almost dead, stand and finish instead of walking out."
    ),
    "funnel": (
        "You are all melee and badly outnumbered, and a rally/choke sits behind you. "
        "Run through the neck to the far pocket so the swarm has to funnel. Do not stop at the mouth "
        "and do not keep walking into the wide hall past the pocket. "
        "Wrong if numbers are even or you already outnumber them."
    ),
    "detonate": (
        "Suicide units are on the field. Allied suicide units dive the densest clump and explode. "
        "Non-suicide allies walk away from enemy suicide units. Do not clump into the blast."
    ),
}

STANCE_CRITERIA = {
    "shoot": {
        "covers": "Ready guns fire now. They will walk closer during the 0.5s stand; that is the trade. Peel only after they are already swinging.",
        "not_for": "Peeling or charging. Do not skip a shot just because melee would get closer — at equal speed that skip never opens a gap.",
        "examples": ["Someone can shoot and enemy melee is not yet in blade range."],
    },
    "aim": {
        "covers": "Stand with the attack command while guns cool. 0 damage this tick; the next shot is queued.",
        "not_for": "A kite. Aim stands still the same 0.5s as shoot.",
        "examples": ["An equal-range gunfight while weapons are cooling."],
    },
    "close": {
        "covers": "Attack-move onto the focus so the fight can start. Use this while the enemy is still outside blade range and outside a 0.5s melee catch.",
        "not_for": "Peeling from melee that is already hitting, or charging a packed blob into suicide explosions (that is spread).",
        "examples": [
            "Enemy is still far outside our weapon range.",
            "Enemy is almost in range and we need to enter it.",
        ],
    },
    "withdraw": {
        "covers": "Peel because melee is already swinging (`physics.contact` is melee_on_us). They stand to attack, we walk, the gap opens. Also peel when we are faster and `physics.if_we_withdraw` is we_open_a_gap.",
        "not_for": "A fight that has not started (far / almost_in_range). Not a substitute for shooting at equal speed: if `physics.if_we_withdraw` is gap_stays_they_chase, walking away only skips damage.",
        "examples": [
            "Melee is already in blade range of the blob.",
            "We are faster than melee and already in our own gun range.",
        ],
    },
    "spread": {
        "covers": "Open space because `physics.suicide_blast` is would_chain. One explosion would hit several allies.",
        "not_for": "A blob that already has space (`physics.suicide_blast` is isolated or none). Then close or shoot. Not a focus-fire order.",
        "examples": ["Allies are packed and the enemy has suicide units, even if those units are still far."],
    },
    "funnel": {
        "covers": "Walk as one blob toward the rally/choke so a huge melee swarm has to come through a neck.",
        "not_for": "Spreading out or kiting in the open.",
        "examples": ["They outnumber us badly and a choke sits behind us."],
    },
    "evade": {
        "covers": "Walk away from enemy suicide units. Do not crash the clump.",
        "not_for": "Allied suicide units, which should close and explode.",
        "examples": ["Ranged units facing incoming bombs."],
    },
}

TARGET_CRITERIA = {
    "frontline": "Focus the nearest damage-dealer to the army. Healers come last.",
    "weakest_in_range": "Focus the lowest-hp enemy that someone can already shoot.",
    "heaviest": "Focus the highest-hp damage-dealer.",
    "healer": "Focus the enemy healer. Guns that cannot hit that healer keep their other target.",
    "clump": "Focus the enemy with the most neighbors, so splash or a detonation hits the pack.",
    "guns": "Focus an enemy ranged unit rather than an enemy melee unit.",
    "threat": "Focus the enemy with the most damage per second per point of remaining health.",
}

FORMATION_CRITERIA = {
    "open": {
        "does": "Increase space between allies before fighting.",
    },
    "keep": {
        "does": "Keep the current spacing and fight.",
    },
}

RANGED_JOB_CRITERIA = {
    "stutter": {
        "does": (
            "Kite. A ready gun shoots only if standing 0.5s does not let enemy melee reach it. "
            "Otherwise that gun walks."
        ),
    },
    "stack": {
        "does": "Attack-move. A ready gun shoots. Otherwise it chases or aims. It does not walk away.",
    },
    "concave": {
        "does": "Guns fan onto a ring around the enemy, then use the stutter rule.",
        "when": "At least three guns, and no enemy gun is still alive.",
    },
    "hold": {
        "does": "Stand ground. Shoot whatever walks into range; never step forward to chase.",
    },
    "fall_back": {
        "does": "Walk back to the rally point or choke, then hold there and shoot what comes in.",
    },
}

KITE_STYLE_CRITERIA = {
    "all": {
        "does": "Every gun uses the stutter rule: shoot if the 0.5s stand is safe, otherwise walk.",
    },
    "bait_one": {
        "does": "The gun closest to enemy melee always walks. The other guns shoot if their stand is safe.",
        "when": "At least two guns, and no enemy gun is still alive.",
    },
    "peel_tagged": {
        "does": "Only a gun already inside enemy melee range walks. The other guns attack-move.",
    },
}

MELEE_JOB_CRITERIA = {
    "charge": {
        "does": "Melee attack-moves into the enemy. Ranged allies keep their own job.",
    },
    "hold_choke": {
        "does": "Melee holds its position at the rally or choke instead of walking forward.",
    },
    "hold": {
        "does": "Melee stands where it is and hits only what comes into reach.",
    },
    "snipe": {
        "does": "The closest melee walks into the enemy suicide units. The rest hold outside the blast.",
    },
}

BAIT_CRITERIA = {
    "bait_one": {
        "does": "The closest melee walks into the densest suicide group. The rest hold outside the blast.",
    },
    "bait_two": {
        "does": "The two closest melee walk into the suicide group. The rest hold outside the blast.",
    },
}

JOB_TO_INTENT = {
    "stutter": "stutter",
    "stack": "shoot",
    "concave": "concave",
    "charge": "close",
    "hold_choke": "funnel",
    "hold": "aim",
    "fall_back": "funnel",
    "open": "spread",
    "snipe": "snipe",
}

KIND_ORDER = ("formation", "ranged", "kite", "melee", "bait", "target", "bar", "wing", "tie", "stand", "mark", "heal", "wounded")



def _fighters(snap: Dict[str, Any], role: Optional[str] = None) -> List[Dict[str, Any]]:
    allies = living(snap["allies"])
    if role is None:
        return [a for a in allies if a.get("role") != "heal"]
    return [a for a in allies if a.get("role") == role]


def _bucket_contact(snap: Dict[str, Any], allies: Optional[List[Dict[str, Any]]] = None) -> str:
    allies = living(snap["allies"]) if allies is None else [a for a in allies if a.get("alive", True)]
    enemies = living(snap["enemies"])
    if not allies or not enemies:
        return "none"
    melee = [e for e in enemies if e.get("role") == "melee"]
    if melee:
        d_melee = min(hypot(a, e) for a in allies for e in melee)
        nearest_a = min(allies, key=lambda a: min(hypot(a, e) for e in melee))
        nearest_e = min(melee, key=lambda e: hypot(nearest_a, e))
        if d_melee <= _weapon_reach(nearest_e, nearest_a) + 0.05:
            return "melee_on_us"
    shooters = [a for a in allies if a.get("role") != "heal"]
    if _line_can_shoot(snap, shooters):
        return "we_can_shoot"
    dmin = min(hypot(a, e) for a in allies for e in enemies)
    if dmin <= 8.0:
        return "almost_in_range"
    return "far"


INTENT_ORDER = ["shoot", "aim", "close", "withdraw", "spread", "funnel", "evade"]


def _walk_hits_edge(meta: Dict[str, Any]) -> bool:
    vs = meta.get("vs_nearest")
    return isinstance(vs, dict) and bool(vs.get("edge"))


def _if_we_stand_to_shoot(
    snap: Dict[str, Any], allies: Optional[List[Dict[str, Any]]] = None
) -> str:
    """Fact: if this line stands 0.5s to fire, does enemy melee reach it."""
    if allies is None:
        allies = [a for a in living(snap["allies"]) if a.get("role") != "heal"]
    else:
        allies = [a for a in allies if a.get("alive", True)]
    melee = [e for e in living(snap["enemies"]) if e.get("role") == "melee"]
    if not allies or not melee:
        return "no_enemy_melee"
    dmin = 1e18
    nearest_a = allies[0]
    nearest_e = melee[0]
    for a in allies:
        for e in melee:
            d = hypot(a, e)
            if d < dmin:
                dmin = d
                nearest_a, nearest_e = a, e
    their_reach = _weapon_reach(nearest_e, nearest_a)
    their_speed = float(nearest_e.get("speed") or 0.0)
    d_after = dmin - their_speed * 0.5
    if d_after <= their_reach + 0.05:
        return "melee_reaches_us"
    return "gap_holds"


def _if_we_keep_standing(
    snap: Dict[str, Any], allies: Optional[List[Dict[str, Any]]] = None
) -> str:
    """If this line keeps standing to shoot, when does enemy melee arrive."""
    if allies is None:
        allies = [a for a in living(snap["allies"]) if a.get("role") != "heal"]
    else:
        allies = [a for a in allies if a.get("alive", True)]
    melee = [e for e in living(snap["enemies"]) if e.get("role") == "melee"]
    if not allies or not melee:
        return "no_enemy_melee"
    dmin = 1e18
    nearest_a = allies[0]
    nearest_e = melee[0]
    for a in allies:
        for e in melee:
            d = hypot(a, e)
            if d < dmin:
                dmin = d
                nearest_a, nearest_e = a, e
    their_reach = _weapon_reach(nearest_e, nearest_a)
    their_speed = float(nearest_e.get("speed") or 0.0)
    gap = dmin - their_reach
    if gap <= 0.05:
        return "already_in_blades"
    if their_speed <= 0.05:
        return "gap_holds"
    t_arrive = gap / their_speed
    period = max(float(a.get("max_cd") or 0.86) for a in allies)
    if t_arrive <= period + 0.15:
        return "melee_arrives_before_next_shot"
    if t_arrive <= period * 2.0 + 0.3:
        return "melee_arrives_within_two_shots"
    return "gap_holds"


def _suicide_blast(snap: Dict[str, Any]) -> str:
    enemies = living(snap["enemies"])
    allies = living(snap["allies"])
    if not any(e.get("kamikaze") for e in enemies):
        return "none"
    if any(a.get("kamikaze") for a in allies):
        return "our_bombs"
    # Pack living is not itself a chain on us. Only our clump chains the blast.
    if _min_ally_dist(snap) < 4.0:
        return "would_chain"
    return "isolated"


def _withdraw_edge_risk(snap: Dict[str, Any]) -> str:
    away = _group_away_key(snap)
    if away is None:
        return "none"
    delta = None
    for _act, (key, _heading, xy) in WALK.items():
        if key == away:
            delta = xy
            break
    if delta is None:
        return "none"
    dx, dy = delta
    width = float(snap.get("width") or 32)
    height = float(snap.get("height") or 32)
    allies = living(snap["allies"])
    if not allies:
        return "none"
    hits = 0
    for a in allies:
        nx, ny = a["x"] + dx, a["y"] + dy
        if nx < 1.4 or ny < 1.4 or nx > width - 1.4 or ny > height - 1.4:
            hits += 1
    if hits >= max(1, (len(allies) + 1) // 2):
        return "would_hit_edge"
    return "clear"


def _situation(snap: Dict[str, Any]) -> str:
    contact = _bucket_contact(snap)
    stand = _if_we_stand_to_shoot(snap)
    blast = _suicide_blast(snap)
    bits = []
    if contact == "far":
        bits.append("The enemy is still far outside our weapon range.")
    elif contact == "almost_in_range":
        bits.append("The enemy is almost in our weapon range.")
    elif contact == "we_can_shoot":
        bits.append("Someone on our side can shoot this tick.")
    elif contact == "melee_on_us":
        bits.append("Enemy melee is already in blade range of our blob.")
    if stand == "melee_reaches_us":
        bits.append("If we stand 0.5s to fire, melee will reach us.")
    elif stand == "gap_holds":
        bits.append("If we stand 0.5s to fire, melee still does not reach us.")
    if blast == "would_chain":
        bits.append("Allies are packed tight enough that one suicide explosion would hit several.")
    elif blast == "isolated":
        bits.append("Enemy suicide units are alive, but allies currently have space.")
    elif blast == "our_bombs":
        bits.append("We have our own suicide units.")
    edge = _withdraw_edge_risk(snap)
    if edge == "would_hit_edge":
        bits.append("Walking away as a blob would hit the map edge.")
    ranged = _fighters(snap, "ranged")
    melee = _fighters(snap, "melee")
    if ranged and melee:
        bits.append("Allied melee is still alive and tanking.")
        bits.append(
            "Ranged line contact is "
            + _bucket_contact(snap, ranged)
            + "; melee line contact is "
            + _bucket_contact(snap, melee)
            + "."
        )
    elif ranged and not melee:
        bits.append("No allied melee left; the remaining guns are on their own.")
    wd = _if_we_withdraw(snap, ranged or None)
    if wd == "they_stand_we_open_gap":
        bits.append("If we walk away now, they stand to swing and the gap opens.")
    elif wd == "gap_stays_they_chase":
        bits.append("If we walk away now at equal speed they chase; the gap does not open.")
    elif wd == "we_open_a_gap":
        bits.append("We are faster, so walking away opens a gap.")
    elif wd == "they_catch_us":
        bits.append("They are faster, so walking away does not escape.")
    return " ".join(bits) if bits else "No special contact."


def _guns_status(snap: Dict[str, Any], allies: Optional[List[Dict[str, Any]]] = None) -> str:
    if allies is None:
        guns = [a for a in living(snap["allies"]) if a.get("role") != "heal"]
    else:
        guns = [a for a in allies if a.get("role") != "heal"]
    if not guns:
        return "none"
    if any(_ready(a) for a in guns):
        return "some_ready"
    return "all_cooling"


def _if_we_withdraw(
    snap: Dict[str, Any], allies: Optional[List[Dict[str, Any]]] = None
) -> str:
    """Fact: what walking away does, given speed and whether melee is swinging."""
    enemies = living(snap["enemies"])
    if not any(e.get("role") == "melee" for e in enemies):
        return "no_enemy_melee"
    if _bucket_contact(snap, allies) == "melee_on_us":
        return "they_stand_we_open_gap"
    spd = _speed_advantage(snap)
    if spd >= 0.5:
        return "we_open_a_gap"
    if spd <= -0.5:
        return "they_catch_us"
    return "gap_stays_they_chase"


def _withdraw_ok(snap: Dict[str, Any]) -> bool:
    """Walking away is a real option for a ranged-only army vs melee.

    Contact is Jev's to judge; code only hides withdraw when the army cannot
    kite (allied melee/bombs, or no enemy melee).
    """
    allies = living(snap["allies"])
    enemies = living(snap["enemies"])
    if any(a.get("role") == "melee" for a in allies):
        return False
    if not any(e.get("role") == "melee" for e in enemies):
        return False
    if any(a.get("kamikaze") for a in allies):
        return False
    return True


def _option_intent(
    key: str, meta: Dict[str, Any], ally: Dict[str, Any], snap: Dict[str, Any]
) -> Optional[str]:
    if key.startswith("fire_"):
        return "shoot"
    if key.startswith("heal_"):
        return "heal"
    if key.startswith("chase_"):
        return "close"
    if key.startswith("hold_aim_") or key.startswith("stand_cooling_"):
        return "aim"
    if not key.startswith("walk_"):
        return None
    if _walk_hits_edge(meta):
        return None
    if _should_spread(snap):
        spread = _spread_key(ally, snap)
        if spread and key == spread:
            return "spread"
        if spread is None and key == "hold":
            return "spread"
    kami_e = any(e.get("kamikaze") for e in living(snap["enemies"]))
    kami_a = any(a.get("kamikaze") for a in living(snap["allies"]))
    if kami_e and not kami_a and _rel(meta) == "farther" and ally.get("role") != "melee":
        return "evade"
    away = _group_away_key(snap)
    if away and key == away and _withdraw_ok(snap):
        return "withdraw"
    if "funnel" in legal_plans(snap):
        toward = _army_toward_key(snap, _rally_point(snap))
        if toward and key == toward:
            return "funnel"
    return None


def army_intents(snap: Dict[str, Any]) -> List[str]:
    found = set()
    for ally in living(snap["allies"]):
        if ally.get("role") == "heal":
            continue
        for _act, key, meta in legal_options(ally, snap, prune=False):
            intent = _option_intent(key, meta, ally, snap)
            if intent and intent != "heal":
                found.add(intent)
    contact = _bucket_contact(snap)
    wd = _if_we_withdraw(snap)
    guns = _guns_status(snap)
    blast = _suicide_blast(snap)
    melee_e = any(e.get("role") == "melee" for e in living(snap["enemies"]))
    # Aim vs melee is standing still while blades walk in. Not a real stance.
    if melee_e:
        found.discard("aim")
    # Spread only while a blast would still chain. Isolated means the job is done.
    if blast == "would_chain":
        found.add("spread")
    else:
        found.discard("spread")
    # Withdraw if walking away changes something, or we cannot shoot vs melee.
    useful_wd = False
    if _withdraw_ok(snap):
        if wd in {"they_stand_we_open_gap", "we_open_a_gap"}:
            useful_wd = True
        elif guns == "all_cooling" and contact in {"we_can_shoot", "melee_on_us", "almost_in_range"}:
            useful_wd = True
        elif contact in {"far", "almost_in_range"}:
            useful_wd = True
    if useful_wd:
        found.add("withdraw")
    else:
        found.discard("withdraw")
    if contact in {"far", "almost_in_range"}:
        found.add("close")
    if not found:
        found.add("close")
    return [name for name in INTENT_ORDER if name in found]


def _line_can_shoot(snap: Dict[str, Any], line: List[Dict[str, Any]]) -> bool:
    enemies = living(snap["enemies"])
    for a in line:
        if a.get("role") == "heal":
            continue
        for e in enemies:
            if (
                _can_hit(a, e)
                and _in_weapon_range(a, e)
                and _can_target(snap, a, e["id"])
            ):
                return True
    return False


def _can_kite_line(snap: Dict[str, Any], line: List[Dict[str, Any]]) -> bool:
    """True if this gun line is physically allowed to kite."""
    if not line:
        return False
    if any(a.get("role") == "melee" for a in line):
        return False
    if any(a.get("kamikaze") for a in line):
        return False
    if any(a.get("splash") and not a.get("kamikaze") for a in line):
        return False
    return True


# ----------------------------------------------------------------------
# Menus: physics decides which jobs are legal
# ----------------------------------------------------------------------

# Program mode (snap["_open_menu"]): every job the motor can execute is legal;
# the offline simulator, not these gates, decides whether it is any good.
# Dummy and Jev never set the flag, so their menus are unchanged.


def formation_jobs(snap: Dict[str, Any]) -> List[str]:
    if snap.get("_open_menu"):
        return ["open", "keep"]
    if _suicide_blast(snap) == "none":
        return []
    return ["open", "keep"]


def ranged_jobs(snap: Dict[str, Any]) -> List[str]:
    line = _fighters(snap, "ranged")
    if not line:
        return []
    if snap.get("_open_menu"):
        return ["stack", "stutter", "hold", "fall_back"] + (["concave"] if len(line) >= 3 else [])
    jobs: List[str] = ["stack"]
    melee_e = any(e.get("role") == "melee" for e in living(snap["enemies"]))
    static = any(e.get("role") == "static" for e in living(snap["enemies"]))
    # Buildings do not chase. Equal speed does not open a gap, so kite is not legal.
    if static or not melee_e or not _can_kite_line(snap, line):
        return jobs
    # Our own melee is tanking. Kiting the guns pulls them off the tanks.
    if any(a.get("role") == "melee" and not a.get("kamikaze") for a in living(snap["allies"])):
        return jobs
    if _speed_advantage(snap) < 0.5:
        return jobs
    jobs.append("stutter")
    # A fan wins only after their guns are gone. While a gun can still shoot, the fan lost.
    enemy_guns = any(e.get("role") == "ranged" for e in living(snap["enemies"]))
    if len(line) >= 3 and not enemy_guns:
        jobs.append("concave")
    return jobs


def kite_jobs(snap: Dict[str, Any]) -> List[str]:
    """Who walks while stuttering. Peel never won. Bait loses while an enemy gun is alive."""
    if "stutter" not in ranged_jobs(snap):
        return []
    line = _fighters(snap, "ranged")
    if snap.get("_open_menu"):
        return ["all", "bait_one"] if len(line) >= 2 else ["all"]
    jobs = ["all"]
    enemy_guns = any(e.get("role") == "ranged" for e in living(snap["enemies"]))
    if len(line) >= 2 and not enemy_guns:
        jobs.append("bait_one")
    return jobs


def default_kite_style(jobs: List[str], snap: Dict[str, Any]) -> str:
    if "all" in jobs:
        return "all"
    return jobs[0] if jobs else "all"


def bait_jobs(snap: Dict[str, Any]) -> List[str]:
    """How many blades walk into a suicide wad. Empty unless snipe is legal."""
    if "snipe" not in melee_jobs(snap):
        return []
    line = _fighters(snap, "melee")
    if snap.get("_open_menu"):
        return ["bait_one", "bait_two"] if len(line) >= 2 else ["bait_one"]
    kami = [e for e in living(snap["enemies"]) if e.get("kamikaze")]
    if not line or not kami:
        return []
    jobs = ["bait_one"]
    if len(line) >= 3 and _kami_pack_live(snap):
        jobs.append("bait_two")
    return jobs


def default_bait_style(jobs: List[str], snap: Dict[str, Any]) -> str:
    if "bait_one" in jobs:
        return "bait_one"
    return jobs[0] if jobs else "bait_one"


def melee_jobs(snap: Dict[str, Any]) -> List[str]:
    line = _fighters(snap, "melee")
    if not line:
        return []
    our_kami = any(a.get("kamikaze") for a in living(snap["allies"]))
    enemy_kami = [e for e in living(snap["enemies"]) if e.get("kamikaze")]
    if snap.get("_open_menu"):
        return ["charge", "hold_choke", "hold"] + (["snipe"] if enemy_kami and not our_kami else [])
    jobs = ["charge"]
    if enemy_kami and not our_kami:
        jobs.append("snipe")
    melee_e = any(e.get("role") == "melee" for e in living(snap["enemies"]))
    allies = living(snap["allies"])
    enemies = living(snap["enemies"])
    n_e = len(enemies)
    # Same gate as the funnel plan: rally-behind is a choice only for an
    # all-melee army that is outnumbered. A ranged line does not sit just
    # because the attack point is behind it. A real pocket still opens it.
    all_melee = not any(a.get("role") == "ranged" for a in allies)
    if (
        melee_e
        and not our_kami
        and n_e >= 2
        and (
            _in_pocket(snap)
            or _in_choke(snap)
            or (all_melee and n_e > len(allies) and _rally_is_behind(snap))
        )
    ):
        jobs.append("hold_choke")
    return jobs


def default_formation(opts: List[str]) -> str:
    if "keep" in opts:
        return "keep"
    if "open" in opts:
        return "open"
    return "keep"


def default_ranged_job(jobs: List[str], snap: Dict[str, Any]) -> str:
    """Dummy / script default is attack-move."""
    if not jobs:
        return "stack"
    if "stack" in jobs:
        return "stack"
    if "stutter" in jobs:
        return "stutter"
    return jobs[0]


def default_melee_job(jobs: List[str], snap: Optional[Dict[str, Any]] = None) -> str:
    if "charge" in jobs:
        return "charge"
    return jobs[0] if jobs else "charge"


def _live_tactic(snap: Dict[str, Any]) -> Dict[str, str]:
    """Named physics class the motor is compiling. Not a map name, not an exam."""
    allies = living(snap["allies"])
    enemies = living(snap["enemies"])
    if not allies or not enemies:
        return {
            "name": "idle",
            "motor": "stack",
            "jev": "none",
            "why": "No fight.",
        }
    plan = army_plan(snap)
    m_jobs = melee_jobs(snap)
    tanks = _fighters(snap, "melee")
    guns = _fighters(snap, "ranged")
    melee_e = any(e.get("role") == "melee" for e in enemies)
    kami_a = any(a.get("kamikaze") for a in allies)
    kami_e = any(e.get("kamikaze") for e in enemies)
    splash = any(a.get("splash") and not a.get("kamikaze") for a in allies)
    static = any(e.get("role") == "static" for e in enemies)
    faster = _speed_advantage(snap) >= 0.5
    guns_in_blades = bool(guns) and _bucket_contact(snap, guns) == "melee_on_us"
    if static:
        return {
            "name": "cycle",
            "motor": "cycle",
            "jev": "none",
            "why": "Immobile building. Dead-zone stagger is physics, not a stance exam.",
        }
    if kami_a:
        return {
            "name": "detonate",
            "motor": "charge+clump",
            "jev": "formation,target",
            "why": "Our bombs charge the densest pack. Open formation only if we would chain.",
        }
    if kami_e:
        return {
            "name": "charge_bombs",
            "motor": "charge",
            "jev": "melee,formation",
            "why": "Enemy suicide wave. Dummy charges. Jev may snipe or open spacing.",
        }
    if splash:
        return {
            "name": "splash_clump",
            "motor": "stack+clump",
            "jev": "target",
            "why": "Splash guns. Attack-move and hit the densest pack.",
        }
    if plan == "funnel" or "hold_choke" in m_jobs:
        return {
            "name": "funnel",
            "motor": "hold_choke",
            "jev": "melee",
            "why": "Outnumbered melee with a choke/pocket. Sit the neck; charge is a surround.",
        }
    if guns and melee_e and not tanks and faster:
        return {
            "name": "outrun_kite",
            "motor": "stack",
            "jev": "ranged,kite",
            "why": "Faster guns, no allied tanks. Dummy attack-moves. Jev may kite.",
        }
    if guns and tanks and melee_e:
        if guns_in_blades:
            return {
                "name": "leftover_kite",
                "motor": "stack",
                "jev": "ranged,kite",
                "why": "Gun line is in blades. Dummy still stacks. Jev may leftover-kite.",
            }
        return {
            "name": "mixed_commit",
            "motor": "stack+charge",
            "jev": "ranged,kite,target",
            "why": "Allied melee is tanking. Dummy stacks. Jev may leftover-kite or retarget.",
        }
    if _must_break_extra_tank(snap):
        return {
            "name": "extra_tank",
            "motor": "stack+heaviest",
            "jev": "target",
            "why": "They have extra heavies and no healer. Attack-move and focus the extra tank. A living healer turns this off: tank-focus is healed, so the whole ball walks in.",
        }
    if guns and melee_e and not faster:
        return {
            "name": "equal_speed_trade",
            "motor": "stack",
            "jev": "none",
            "why": "Equal speed guns vs melee. Walking does not open a gap, so stutter is not legal. Attack-move.",
        }
    return {
        "name": "stack_trade",
        "motor": "stack",
        "jev": "target",
        "why": "Same-range guns. Attack-move and focus. Stance is not a choice.",
    }


def _body_band(unit: Dict[str, Any]) -> str:
    ehp = float(unit.get("max_hp") or 0) + float(unit.get("max_shield") or unit.get("shield") or 0)
    if ehp >= 100:
        return "heavy"
    if ehp >= 60:
        return "medium"
    return "light"


def _target_option(name: str, snap: Dict[str, Any]) -> Dict[str, Any]:
    foc = resolve_focus(name, snap)
    out: Dict[str, Any] = {"rule": TARGET_CRITERIA[name]}
    if foc is None:
        out["picks"] = "nobody"
        return out
    hp = foc["hp"] / max(float(foc.get("max_hp") or 1), 1e-6)
    out["picks"] = f"E{foc['id']}"
    out["kind"] = foc.get("name") or foc.get("type")
    out["role"] = foc.get("role")
    out["hp"] = "critical" if hp <= 0.3 else ("wounded" if hp <= 0.6 else "healthy")
    out["body"] = _body_band(foc)
    out["remaining_ehp"] = int(round(_ehp(foc)))
    our_h = _heavy_count(living(snap["allies"]))
    their_h = _heavy_count(living(snap["enemies"]))
    out["our_heavy"] = our_h
    out["their_heavy"] = their_h
    return out


def _target_criteria(snap: Dict[str, Any], rules: List[str]) -> Dict[str, Any]:
    """Each rule names its concrete unit and how tanky that pick is vs the others."""
    opts = {name: _target_option(name, snap) for name in rules}
    ehps = {
        name: int(opt["remaining_ehp"])
        for name, opt in opts.items()
        if isinstance(opt.get("remaining_ehp"), int)
    }
    if len(ehps) >= 2:
        mx, mn = max(ehps.values()), min(ehps.values())
        spread = mx >= mn * 1.4 + 10
        for name, ehp in ehps.items():
            if not spread:
                opts[name]["among_picks"] = "similar_body"
            elif ehp >= mx - 1:
                opts[name]["among_picks"] = "the_tankiest"
            elif ehp <= mn + 1:
                opts[name]["among_picks"] = "the_squishiest"
            else:
                opts[name]["among_picks"] = "in_between"
    return opts


def _line_physics(snap: Dict[str, Any], role: str) -> Optional[Dict[str, Any]]:
    line = _fighters(snap, role)
    if not line:
        return None
    out: Dict[str, Any] = {
        "alive": len(line),
        "contact": _bucket_contact(snap, line),
        "guns": _guns_status(snap, line),
        "if_we_stand_to_shoot": _if_we_stand_to_shoot(snap, line),
        "if_we_keep_standing": _if_we_keep_standing(snap, line),
        "if_we_withdraw": _if_we_withdraw(snap, line),
        "jobs": ranged_jobs(snap) if role == "ranged" else melee_jobs(snap),
    }
    if role == "ranged":
        tanks = _fighters(snap, "melee")
        out["allied_melee"] = "tanking" if tanks else "none"
        out["this_line_in_blades"] = out["contact"] == "melee_on_us"
    return out


def _ranged_option(name: str, snap: Dict[str, Any]) -> Dict[str, Any]:
    line = _fighters(snap, "ranged")
    tanks = _fighters(snap, "melee")
    contact = _bucket_contact(snap, line) if line else "none"
    out = dict(RANGED_JOB_CRITERIA[name])
    out["this_line_contact"] = contact
    out["allied_melee"] = "tanking" if tanks else "none"
    out["this_line_in_blades"] = contact == "melee_on_us"
    out["gun_count"] = len(line)
    if line:
        out["if_this_line_stands"] = _if_we_stand_to_shoot(snap, line)
        out["if_this_line_keeps_standing"] = _if_we_keep_standing(snap, line)
        out["if_this_line_walks"] = _if_we_withdraw(snap, line)
        out["guns"] = _guns_status(snap, line)
    out["speed"] = _bucket_speed(_speed_advantage(snap))
    out["numbers"] = _bucket_numbers(len(living(snap["allies"])), len(living(snap["enemies"])))
    out["enemy_guns"] = (
        "alive" if any(e.get("role") == "ranged" for e in living(snap["enemies"])) else "none"
    )
    return out


def _kite_option(name: str, snap: Dict[str, Any]) -> Dict[str, Any]:
    line = _fighters(snap, "ranged")
    out = dict(KITE_STYLE_CRITERIA[name])
    enemy_guns = any(e.get("role") == "ranged" for e in living(snap["enemies"]))
    out["speed"] = _bucket_speed(_speed_advantage(snap))
    out["gun_count"] = len(line)
    out["enemy_guns"] = "alive" if enemy_guns else "none"
    out["this_line_contact"] = _bucket_contact(snap, line) if line else "none"
    return out


def _bait_option(name: str, snap: Dict[str, Any]) -> Dict[str, Any]:
    line = _fighters(snap, "melee")
    kami = [e for e in living(snap["enemies"]) if e.get("kamikaze")]
    out = dict(BAIT_CRITERIA[name])
    out["blades"] = len(line)
    out["bombs"] = len(kami)
    out["pack"] = "packed" if _kami_pack_live(snap) else "isolated"
    return out


def _melee_option(name: str, snap: Dict[str, Any]) -> Dict[str, Any]:
    line = _fighters(snap, "melee")
    n_a = len(living(snap["allies"]))
    n_e = len(living(snap["enemies"]))
    out = dict(MELEE_JOB_CRITERIA[name])
    out["numbers"] = _bucket_numbers(n_a, n_e)
    out["pocket"] = _pocket_label(snap)
    out["choke_behind_us"] = _rally_is_behind(snap)
    if line:
        out["this_line_contact"] = _bucket_contact(snap, line)
    return out


def _formation_option(name: str, snap: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(FORMATION_CRITERIA[name])
    out["suicide_blast"] = _suicide_blast(snap)
    out["ally_spacing"] = "clumped" if _min_ally_dist(snap) < 4.0 else "open"
    return out


def _pick_walk_away(pick, snap: Dict[str, Any]) -> Optional[int]:
    away = _group_away_key(snap)
    act = pick(lambda k, m: away is not None and k == away and not _walk_hits_edge(m))
    if act is None:
        act = pick(
            lambda k, m: k.startswith("walk_")
            and _rel(m) == "farther"
            and not _walk_hits_edge(m)
        )
    return act


def _attack_move_act(ally: Dict[str, Any], snap: Dict[str, Any], pick) -> Optional[int]:
    """Fire if possible, else chase, else hold. No kite."""
    act = _pick_fire(pick, snap)
    if act is not None:
        return act
    if _static_enemies(snap) and not any(e.get("role") == "melee" for e in living(snap["enemies"])):
        if not _ready(ally) and not _cycle_may_enter(ally, snap):
            act = pick(lambda k, _m: k == "hold")
            if act is not None:
                return act
    act = pick(lambda k, _m: k.startswith("hold_aim_") or k.startswith("stand_cooling_"))
    if act is not None:
        return act
    act = pick(lambda k, _m: k.startswith("chase_"))
    if act is not None:
        return act
    return pick(lambda k, _m: k == "hold")


def _execute_cycle(ally: Dict[str, Any], snap: Dict[str, Any], pick) -> Optional[int]:
    """Building that outranges us: fire, walk out while cooling, re-enter only if allowed."""
    static = _static_enemies(snap)
    if not static:
        return None
    building = _nearest(ally, static)
    if building is None:
        return None
    if _ready(ally) and _in_weapon_range(ally, building):
        act = pick(lambda k, _m: k.startswith("fire_"))
        if act is not None:
            return act
    if _cycle_out(ally, snap) or (
        (not _ready(ally)) and hypot(ally, building) <= _weapon_reach(building, ally) + 0.05
        and _ehp(building) > sum(_shot_damage(a, building) for a in living(snap["allies"]) if a.get("role") != "heal") + 8
    ):
        act = _pick_walk_away(pick, snap)
        if act is not None:
            return act
    if not _cycle_may_enter(ally, snap):
        act = pick(lambda k, _m: k == "hold")
        if act is not None:
            return act
    if _ready(ally) or _soon(ally):
        act = pick(lambda k, _m: k.startswith("chase_"))
        if act is not None:
            return act
    return pick(lambda k, _m: k == "hold")


def _blast_radius(unit: Dict[str, Any]) -> float:
    r = unit.get("splash_radius")
    if r:
        return float(r)
    if unit.get("kamikaze"):
        return 2.2
    return 0.0


def _kami_safe_dist(ally: Dict[str, Any], bomb: Dict[str, Any]) -> float:
    """Stay outside this tick's explosion plus one enemy step."""
    return (
        _blast_radius(bomb)
        + _radius(ally)
        + float(bomb.get("speed") or 0.0) * 0.55
        + 0.35
    )


def _snipe_picker_ids(snap: Dict[str, Any]) -> set:
    bomb = _snipe_bomb(snap)
    allies = [a for a in living(snap["allies"]) if a.get("role") != "heal"]
    if bomb is None or not allies:
        return set()
    n_pick = 2 if snap.get("_bait_style") == "bait_two" else 1
    ordered = sorted(allies, key=lambda a: (hypot(a, bomb), a["id"]))
    return {a["id"] for a in ordered[: max(1, min(n_pick, len(ordered)))]}


def _execute_snipe(ally: Dict[str, Any], snap: Dict[str, Any], pick) -> Optional[int]:
    """Picker attack-moves the densest wad. The rest hold the blast ring, not the map edge."""
    bomb = _snipe_bomb(snap)
    kami = [e for e in living(snap["enemies"]) if e.get("kamikaze")]
    dest = bomb or (_nearest(ally, kami) if kami else None)
    picker_ids = _snipe_picker_ids(snap)
    if ally["id"] in picker_ids and dest is not None:
        if _in_weapon_range(ally, dest):
            act = pick(lambda k, _m: k == f"fire_E{dest['id']}")
            if act is not None:
                return act
            act = pick(lambda k, _m: k.startswith("fire_"))
            if act is not None:
                return act
        toward = _walk_toward_key(ally, (dest["x"], dest["y"]))
        act = pick(lambda k, m: toward is not None and k == toward and not _walk_hits_edge(m))
        if act is not None:
            return act
        act = pick(lambda k, _m: k.startswith("chase_"))
        if act is not None:
            return act
        return pick(lambda k, _m: k == "hold")
    nearest = _nearest(ally, kami) if kami else None
    if nearest is None:
        return pick(lambda k, _m: k.startswith("fire_")) or pick(lambda k, _m: k.startswith("chase_"))
    d = hypot(ally, nearest)
    if d < _kami_safe_dist(ally, nearest):
        esc = _escape_key(ally, snap)
        act = pick(lambda k, m: esc is not None and k == esc and not _walk_hits_edge(m))
        if act is not None:
            return act
        act = pick(
            lambda k, m: k.startswith("walk_")
            and _rel(m) == "farther"
            and not _walk_hits_edge(m)
        )
        if act is not None:
            return act
    return pick(lambda k, _m: k == "hold")


def _execute_heal(ally: Dict[str, Any], snap: Dict[str, Any], pick) -> Optional[int]:
    """Glue to the cover target. Heal from a comfortable leash, not max range.
    Out of max range the engine heal-move walks continuously; inside max range
    but outside the leash, take one step closer. Never sit at spawn."""
    target = _heal_cover(snap, ally)
    if target is None:
        return pick(lambda k, _m: k == "hold")
    wounded = target["hp"] < target["max_hp"] - 1
    overtake = _healer_would_overtake(ally, target, snap)

    def heal_now():
        if not wounded:
            return None
        act = pick(lambda k, _m: k == f"heal_U{target['id']}")
        if act is not None:
            return act
        return pick(lambda k, _m: k.startswith("heal_"))

    if _heal_comfortable(ally, target) or overtake:
        act = heal_now()
        if act is not None:
            return act
        return pick(lambda k, _m: k == "hold")
    if not _in_weapon_range(ally, target):
        # Attack-move heal: engine walks in, then heals. Better than NESW.
        act = pick(lambda k, _m: k == f"heal_U{target['id']}")
        if act is not None:
            return act
        act = pick(lambda k, _m: k.startswith("heal_"))
        if act is not None:
            return act
    toward = _walk_toward_key(ally, (target["x"], target["y"]))
    act = pick(lambda k, _m: toward is not None and k == toward)
    if act is not None:
        return act
    act = heal_now()
    if act is not None:
        return act
    return pick(lambda k, _m: k == "hold")


def execute_intent(
    ally: Dict[str, Any],
    snap: Dict[str, Any],
    intent: str,
    options: Optional[List[Tuple[int, str, Dict[str, Any]]]] = None,
) -> int:
    if ally.get("role") == "heal":
        if options is None:
            options = legal_options(ally, snap, prune=False)
        def pick_h(pred):
            for act, key, meta in options:
                if pred(key, meta):
                    return act
            return None
        if snap.get("_ranged_job") in {"stutter", "concave"}:
            # Medic stays behind the kite line. Healing a front gun is a dive.
            under_fire = any(
                e.get("role") != "heal" and _in_weapon_range(e, ally)
                for e in living(snap["enemies"])
            )
            act = None
            if not under_fire:
                act = pick_h(lambda k, _m: k.startswith("heal_"))
            if act is None:
                away = _group_away_key(snap)
                act = pick_h(lambda k, m: away is not None and k == away and not _walk_hits_edge(m))
            if act is None:
                act = pick_h(
                    lambda k, m: k.startswith("walk_")
                    and _rel(m) == "farther"
                    and not _walk_hits_edge(m)
                )
            if act is not None:
                return act
        act = _execute_heal(ally, snap, pick_h)
        if act is not None:
            return act
        pruned = legal_options(ally, snap, prune=True)
        return _fallback_action(ally, snap, pruned)
    if options is None:
        options = legal_options(ally, snap, prune=False)
    if not options:
        return 0

    def pick(pred) -> Optional[int]:
        for act, key, meta in options:
            if pred(key, meta):
                return act
        return None

    act: Optional[int] = None
    static_only = bool(_static_enemies(snap)) and not any(
        e.get("role") == "melee" for e in living(snap["enemies"])
    )
    if static_only:
        cyc = _execute_cycle(ally, snap, pick)
        if cyc is not None:
            return cyc
    if intent == "stutter":
        act = _execute_stutter(ally, snap, pick)
        if act is not None:
            return act
        intent = "shoot"
    if intent == "concave":
        act = _execute_concave(ally, snap, pick)
        if act is not None:
            return act
        act = _execute_stutter(ally, snap, pick)
        if act is not None:
            return act
        intent = "shoot"
    if intent == "shoot":
        act = None
        if _cycle_out(ally, snap):
            act = _pick_walk_away(pick, snap)
        if act is None and snap.get("_pre_fan"):
            spread = _line_spread_key(ally, snap)
            if spread is not None:
                act = pick(lambda k, _m: k == spread)
        if act is None:
            act = _attack_move_act(ally, snap, pick)
    elif intent == "aim":
        act = pick(lambda k, _m: k.startswith("hold_aim_") or k.startswith("stand_cooling_"))
        if act is None:
            act = pick(lambda k, _m: k.startswith("fire_"))
        if act is None:
            act = pick(lambda k, _m: k == "hold")
    elif intent == "close":
        # Already in range: shooting is committing. Chase only if we cannot fire.
        enemies = living(snap["enemies"])
        act = None
        if act is None:
            act = pick(lambda k, _m: k.startswith("fire_"))
        bomb_call = snap.get("_bomb_call")
        if (
            act is None
            and bomb_call in {"step", "hold"}
            and ally.get("role") == "melee"
            and not ally.get("kamikaze")
        ):
            bombs = [e for e in living(snap["enemies"]) if e.get("kamikaze")]
            bomb = _nearest(ally, bombs)
            if bomb is not None and abs(hypot(ally, bomb) - _kami_safe_dist(ally, bomb)) <= 0.6:
                if bomb_call == "step":
                    esc = _escape_key(ally, snap)
                    act = pick(lambda k, m: esc is not None and k == esc and not _walk_hits_edge(m))
                    if act is None:
                        act = pick(lambda k, m: k.startswith("walk_") and _rel(m) == "farther" and not _walk_hits_edge(m))
                else:
                    act = pick(lambda k, _m: k == "hold")
        if act is None:
            dest = None
            if ally.get("kamikaze"):
                dest = _densest_enemy(snap)
            fid = snap.get("_focus_id")
            if dest is None and fid is not None:
                dest = next((e for e in enemies if e["id"] == fid), None)
            if dest is None:
                dest = _nearest(ally, enemies)
            if dest is not None and not _in_weapon_range(ally, dest):
                # Group melee uses attack-move. Grid-walk only if chase is stuck
                # (one tile outside blades / wall) so a blob does not NESW-scatter.
                if ally.get("role") == "melee" or ally.get("kamikaze"):
                    n_a = len(living(snap["allies"]))
                    n_e = len(living(snap["enemies"]))
                    in_neck = _in_pocket(snap) or _in_choke(snap)
                    if (
                        in_neck
                        and n_e > n_a
                        and not ally.get("kamikaze")
                        and "hold_choke" in melee_jobs(snap)
                    ):
                        # Charge in a choke means hit who is here, not walk into the hall.
                        act = pick(lambda k, _m: k.startswith("hold_aim_") or k.startswith("stand_cooling_"))
                        if act is None:
                            act = pick(lambda k, _m: k == "hold")
                    else:
                        stuck = ally["id"] in set(snap.get("_stuck_close") or ())
                        closer = _close_walk_key(ally, snap, (dest["x"], dest["y"]), options)
                        if stuck or ally.get("kamikaze"):
                            act = pick(lambda k, _m: closer is not None and k == closer)
                elif _static_enemies(snap) and not _cycle_may_enter(ally, snap):
                    act = pick(lambda k, _m: k == "hold")
        if act is None:
            act = pick(lambda k, _m: k.startswith("chase_"))
        if act is None:
            act = pick(lambda k, _m: k.startswith("hold_aim_") or k.startswith("stand_cooling_"))
    elif intent == "withdraw":
        # Peel: walk the ring / fade. Take only shots that do not gift a 0.5s stand.
        act = None
        in_blades = False
        melee = [e for e in living(snap["enemies"]) if e.get("role") == "melee"]
        static_only = (not melee) and any(e.get("role") == "static" for e in living(snap["enemies"]))
        extra_tank = (not melee) and _must_break_extra_tank(snap)
        if melee:
            nearest = _nearest(ally, melee)
            if nearest is not None and hypot(ally, nearest) <= _weapon_reach(nearest, ally) + 0.05:
                in_blades = True
        nearest = _nearest(ally, melee) if melee else None
        faster = _speed_advantage(snap) >= 0.5
        n_allies = len(living(snap["allies"]))
        outnumbered = len(melee) > n_allies
        kite = None if static_only else _kite_walk_key(ally, snap)
        ring = None if static_only else _ring_slot_key(ally, snap)
        hold_ring = None if static_only else _hold_range_key(ally, snap)
        away = _group_away_key(snap)
        escape = None if static_only else _escape_key(ally, snap)
        free_shot = False
        line = _fighters(snap, "ranged")
        if extra_tank and _ready(ally):
            free_shot = True
        elif melee and _ready(ally) and nearest is not None and _in_weapon_range(ally, nearest):
            if faster:
                free_shot = not in_blades
            else:
                free_shot = _peel_stand_ok(snap, line)
        if free_shot:
            act = pick(lambda k, _m: k.startswith("fire_"))
        if extra_tank:
            # Fade-stutter: shoot on the gun ring, do not walk out of the fight.
            if act is None and not _line_can_shoot(snap, _fighters(snap, "ranged")):
                act = pick(lambda k, _m: k.startswith("chase_"))
            if act is None:
                act = pick(lambda k, m: away is not None and k == away and not _walk_hits_edge(m))
        elif faster:
            # Winning 3s kite: shoot if not in blades, blob-away while cooling.
            if act is None:
                act = pick(lambda k, m: away is not None and k == away and not _walk_hits_edge(m))
            if act is None and (not static_only) and (not outnumbered) and n_allies <= 2:
                act = pick(lambda k, m: kite is not None and k == kite and not _walk_hits_edge(m))
        else:
            # Equal speed: grid-walk the ring. Straight away never enters gun range.
            unsafe = in_blades or (nearest is not None and _shot_lets_melee_in(ally, snap))
            if unsafe:
                if act is None:
                    act = pick(lambda k, m: ring is not None and k == ring and not _walk_hits_edge(m))
                if act is None:
                    act = pick(lambda k, m: away is not None and k == away and not _walk_hits_edge(m))
            else:
                if act is None:
                    act = pick(lambda k, m: ring is not None and k == ring and not _walk_hits_edge(m))
                if act is None:
                    act = pick(lambda k, m: hold_ring is not None and k == hold_ring and not _walk_hits_edge(m))
            if act is None:
                act = pick(lambda k, m: kite is not None and k == kite and not _walk_hits_edge(m))
            if act is None:
                act = pick(lambda k, m: escape is not None and k == escape and not _walk_hits_edge(m))
        if act is None:
            act = pick(
                lambda k, m: k.startswith("walk_")
                and _rel(m) == "farther"
                and not _walk_hits_edge(m)
            )
        if act is None:
            act = pick(lambda k, _m: k == "hold")
    elif intent == "spread":
        spread = _spread_key(ally, snap)
        act = pick(lambda k, _m: spread is not None and k == spread)
        if act is None:
            act = pick(lambda k, _m: k == "hold")
        if act is None:
            act = pick(
                lambda k, m: k.startswith("walk_")
                and _rel(m) == "farther"
                and not _walk_hits_edge(m)
            )
    elif intent == "funnel":
        if _in_pocket(snap):
            act = pick(lambda k, _m: k.startswith("fire_"))
            if act is None:
                act = pick(lambda k, _m: k.startswith("hold_aim_") or k.startswith("stand_cooling_"))
            if act is None and len(living(snap["enemies"])) <= 1:
                # Last body walked out of the neck. Sitting here times out.
                act = pick(lambda k, _m: k.startswith("chase_"))
                if act is None:
                    dest = _nearest(ally, living(snap["enemies"]))
                    closer = (
                        _close_walk_key(ally, snap, (dest["x"], dest["y"]), options)
                        if dest is not None
                        else None
                    )
                    act = pick(lambda k, _m: closer is not None and k == closer)
            if act is None:
                act = pick(lambda k, _m: k == "hold")
        elif _too_deep(snap):
            enemies = living(snap["enemies"])
            back = _army_toward_key(snap, _centroid(enemies)) if enemies else None
            act = pick(lambda k, _m: back is not None and k == back)
            if act is None:
                act = pick(lambda k, m: k.startswith("walk_") and m.get("vs_rally") == "farther")
            if act is None:
                act = pick(lambda k, _m: k.startswith("fire_"))
        else:
            toward = _army_toward_key(snap, _rally_point(snap))
            act = pick(lambda k, _m: toward is not None and k == toward)
            if act is None:
                act = pick(lambda k, m: k.startswith("walk_") and m.get("vs_rally") == "closer")
            if act is None:
                act = pick(lambda k, _m: k.startswith("fire_"))
            if act is None:
                act = pick(lambda k, _m: k == "hold")
    elif intent == "evade":
        act = pick(lambda k, m: k.startswith("walk_") and _rel(m) == "farther" and not _walk_hits_edge(m))
        if act is None:
            act = pick(lambda k, _m: k == "hold")
    elif intent == "snipe":
        act = _execute_snipe(ally, snap, pick)
    if act is not None:
        return act
    pruned = legal_options(ally, snap, prune=True)
    return _fallback_action(ally, snap, pruned or options)


def _bucket_numbers(n_allies: int, n_enemies: int) -> str:
    if n_enemies >= max(8, 2 * n_allies):
        return "they_outnumber_badly"
    if n_enemies > n_allies:
        return "they_have_a_few_more"
    if n_allies > n_enemies:
        return "we_outnumber"
    return "even"


def _bucket_speed(adv: float) -> str:
    if adv >= 0.5:
        return "we_are_faster"
    if adv <= -0.5:
        return "they_are_faster"
    return "even"


def _bucket_pocket(dist: float) -> str:
    if dist <= 4.5:
        return "in_pocket"
    if dist <= 10:
        return "approaching"
    return "far"


def _bucket_building(ehp: float, volley: float) -> str:
    if volley <= 0:
        return "unknown"
    if ehp <= volley + 8:
        return "one_volley"
    if ehp <= volley * 2 + 8:
        return "almost_dead"
    if ehp <= volley * 5:
        return "wounded"
    return "healthy"


# ----------------------------------------------------------------------
# Commander state and exam catalog
# ----------------------------------------------------------------------

def commander_state(
    step: int, snap: Dict[str, Any], recent: List[str], hp_trend: str = "unknown"
) -> Dict[str, Any]:
    allies = living(snap["allies"])
    enemies = living(snap["enemies"])
    static = [e for e in enemies if e.get("role") == "static"]
    ap = tuple(snap.get("attack_point") or snap.get("center") or (16.0, 16.0))
    ax, ay = _centroid(allies) if allies else (0.0, 0.0)
    rally_dist = ((ax - ap[0]) ** 2 + (ay - ap[1]) ** 2) ** 0.5 if allies else 99.0
    our_kinds: Dict[str, int] = {}
    their_kinds: Dict[str, int] = {}
    for a in allies:
        k = str(a.get("name") or a.get("role") or "unit")
        our_kinds[k] = our_kinds.get(k, 0) + 1
    for e in enemies:
        k = str(e.get("name") or e.get("role") or "unit")
        their_kinds[k] = their_kinds.get(k, 0) + 1
    volley = 0.0
    building = None
    if static and allies:
        building = min(static, key=_hp_key)
        volley = sum(_shot_damage(a, building) for a in allies if a.get("role") != "heal")
    wounded = [a for a in allies if a.get("role") != "heal" and a["hp"] < a["max_hp"] - 1]
    wounded.sort(key=lambda u: (u["hp"] / max(float(u["max_hp"]), 1e-6), u["id"]))
    return {
        "objective": {
            "win": "Wipe every enemy before the tick limit.",
            "loss": "All allies dead, or the limit hits with any enemy still alive.",
            "scoring": "Win the battle first. Damage and kills count only as they lead to that wipe.",
        },
        "agenda": {
            "open_jobs_this_tick": list((snap.get("_catalog_options") or {}).keys()),
            "job": (
                "Pick the legal job that wins the wipe. "
                "Your Choice is the order; code executes it. "
                "You never choose compass directions."
            ),
        },
        "tick": f"{step}/{snap.get('limit') or '?'}",
        "our_force": {
            "alive": len(allies),
            "by_kind": our_kinds,
            "roles": {
                "melee": sum(1 for a in allies if a.get("role") == "melee"),
                "ranged": sum(1 for a in allies if a.get("role") == "ranged"),
                "heal": sum(1 for a in allies if a.get("role") == "heal"),
                "suicide": sum(1 for a in allies if a.get("kamikaze")),
            },
            "wounded": [
                {
                    "id": f"U{u['id']}",
                    "kind": u.get("name") or u.get("type"),
                    "hp": "critical" if u["hp"] <= 0.3 * u["max_hp"] else ("wounded" if u["hp"] <= 0.6 * u["max_hp"] else "scratched"),
                }
                for u in wounded[:5]
            ],
        },
        "enemy_force": {
            "alive": len(enemies),
            "by_kind": their_kinds,
            "roles": {
                "melee": sum(1 for e in enemies if e.get("role") == "melee"),
                "ranged": sum(1 for e in enemies if e.get("role") == "ranged"),
                "heal": sum(1 for e in enemies if e.get("role") == "heal"),
                "static": len(static),
                "suicide": sum(1 for e in enemies if e.get("kamikaze")),
            },
            "building": None
            if building is None
            else {
                "kind": building.get("name") or building.get("type"),
                "hp_band": _bucket_building(_ehp(building), volley),
            },
        },
        "situation": _situation(snap),
        "physics": {
            "numbers": _bucket_numbers(len(allies), len(enemies)),
            "speed": _bucket_speed(_speed_advantage(snap)),
            "reach": (
                "we_outrange"
                if _range_advantage(snap) >= 2.0
                else ("they_outrange" if _range_advantage(snap) <= -2.0 else "even")
            ),
            "allied_melee_present": any(a.get("role") == "melee" for a in allies),
            "enemy_melee_present": any(e.get("role") == "melee" for e in enemies),
            "someone_can_shoot_now": _weakest_in_shot(snap) is not None,
            "rally_is_behind_us": _rally_is_behind(snap),
            "pocket": _pocket_label(snap),
            "enemy_air": sum(1 for e in enemies if e.get("plane") == "AIR"),
            "allied_anti_air": sum(
                1 for a in allies if "AIR" in set(a.get("valid_targets") or [])
            ),
            "legal_plans": legal_plans(snap),
            "contact": _bucket_contact(snap),
            "if_we_stand_to_shoot": _if_we_stand_to_shoot(snap),
            "if_we_keep_standing": _if_we_keep_standing(snap),
            "if_we_withdraw": _if_we_withdraw(snap),
            "suicide_blast": _suicide_blast(snap),
            "ally_spacing": "clumped" if _min_ally_dist(snap) < 4.0 else "open",
            "guns": _guns_status(snap),
            "withdraw_edge": _withdraw_edge_risk(snap),
            "attack_stand_seconds": 0.5,
            "hp_trend": hp_trend,
            "stance_held_for": snap.get("_stance_held_for") or "first_tick",
            "legal_intents": list(snap.get("_legal_intents") or []),
            "formation": list(snap.get("_formation_jobs") or []),
            "focus_coverage": _focus_coverage(
                snap,
                next((e for e in enemies if e["id"] == snap.get("_focus_id")), None)
                if snap.get("_focus_id") is not None
                else resolve_focus(default_target_rule(snap), snap),
            ),
        },
        "lines": {
            "ranged": _line_physics(snap, "ranged"),
            "melee": _line_physics(snap, "melee"),
        },
        "recent": recent[-6:],
    }


def _pick_choice(payload: Any, allowed: List[str], default: str) -> str:
    if isinstance(payload, str) and payload in allowed:
        return payload
    if not isinstance(payload, dict):
        return default
    pick = payload.get("choice")
    if pick in allowed:
        return str(pick)
    probs = payload.get("probabilities")
    if isinstance(probs, dict) and probs:
        best = max(allowed, key=lambda k: float(probs.get(k) or -1.0))
        if best in allowed:
            return best
    return default


def _noul_yes(payload: Any, default: bool = False, thresh: float = 0.55) -> bool:
    if not isinstance(payload, dict):
        return default
    p = payload.get("probability")
    if p is None:
        p = payload.get("noul")
    if p is None:
        p = payload.get("p")
    if p is None:
        return default
    try:
        return float(p) >= thresh
    except (TypeError, ValueError):
        return default


def _noul_p(payload: Any) -> float:
    if not isinstance(payload, dict):
        return 0.0
    p = payload.get("probability")
    if p is None:
        p = payload.get("noul")
    if p is None:
        p = payload.get("p")
    try:
        return float(p)
    except (TypeError, ValueError):
        return 0.0


def _choice_prob(payload: Any, pick: str) -> float:
    if not isinstance(payload, dict):
        return 0.0
    probs = payload.get("probabilities")
    if not isinstance(probs, dict):
        return 1.0 if payload.get("choice") == pick else 0.0
    try:
        return float(probs.get(pick) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _option_yes_no(crit: Any) -> Tuple[str, str]:
    if isinstance(crit, str):
        return crit, "This option is dominated this tick."
    if not isinstance(crit, dict):
        return "This option is live this tick.", "This option is dominated this tick."
    yes = crit.get("for_now") or crit.get("covers") or crit.get("rule") or "This option is live this tick."
    no = crit.get("not_for_now") or crit.get("not_for") or "This option is dominated this tick."
    if not isinstance(yes, str):
        yes = str(yes)
    if not isinstance(no, str):
        no = str(no)
    return yes, no



# An exam reaches Jev only if pinning one of its options beat Dummy on a
# seed Dummy lost (python results/_regress.py force; rows in results/force/).
# Kinds not listed still compile, answered with the code default.
# Closed on 2026-09-29, no Force win on 23 maps x 5 seeds:
#   formation, kite (under ranged=stutter), bait (under melee=snipe),
#   stand (under ranged=stutter; shoot lost 3s_vs_5z 5/5), mark.
EXAM_EVIDENCE = {
    "ranged": "results/force/ranged.jsonl",  # stutter: 3s_vs_3z, 3s5z_vs_3s6z
    "melee": "results/force/melee.jsonl",  # hold_choke: corridor 5/5
    "target": "results/force/target__guns.jsonl",  # guns: 1c3s5z 4/5
    "bar": "results/force/bar.jsonl",  # bar: 1c3s5z 5/5
    "wing": "results/force/wing.jsonl",  # step: 10m_vs_11m 5/5, 27m_vs_30m 4/5
    "tie": "results/force/tie.jsonl",  # other body: 10m_vs_11m, 27m_vs_30m, MMM (also loses some)
    "heal": "results/force/heal.jsonl",  # MMM s2 (also loses s4)
}


def build_job_catalog(
    snap: Dict[str, Any],
    form_opts: List[str],
    r_jobs: List[str],
    m_jobs: List[str],
    rules: List[str],
    wounded: List[Dict[str, Any]],
    healers: List[Dict[str, Any]],
    form: str,
    r_job: str,
    m_job: str,
    rule: str,
) -> Dict[str, Dict[str, Any]]:
    """Closed exam bank. A kind is open only when it still has two legal options."""
    catalog: Dict[str, Dict[str, Any]] = {}
    if len(form_opts) > 1:
        option_criteria = {name: _formation_option(name, snap) for name in form_opts}
        catalog["formation"] = {
            "options": list(form_opts),
            "default": form,
            "option_criteria": option_criteria,
            "choice": {
                "type": "choice",
                "instructions": (
                    "Should the army open formation this tick, or keep spacing and fight? "
                    "This is independent of who charges. Code executes it."
                ),
                "criteria": option_criteria,
            },
        }
    if len(r_jobs) > 1:
        option_criteria = {name: _ranged_option(name, snap) for name in r_jobs}
        catalog["ranged"] = {
            "options": list(r_jobs),
            "default": r_job,
            "option_criteria": option_criteria,
            "choice": {
                "type": "choice",
                "instructions": (
                    "How should the gun line act this tick? "
                    "Each option is defined by what the code will execute. "
                    "You never pick compass directions."
                ),
                "criteria": option_criteria,
            },
        }
    k_jobs = kite_jobs(snap)
    if "stutter" in r_jobs and len(k_jobs) > 1:
        k_job = default_kite_style(k_jobs, snap)
        option_criteria = {name: _kite_option(name, snap) for name in k_jobs}
        catalog["kite"] = {
            "options": list(k_jobs),
            "default": k_job,
            "option_criteria": option_criteria,
            "choice": {
                "type": "choice",
                "instructions": (
                    "If the gun line kites this tick, who walks? "
                    "Each option is defined by who the code will move. "
                    "You never pick compass directions."
                ),
                "criteria": option_criteria,
            },
        }
    if len(m_jobs) > 1:
        option_criteria = {name: _melee_option(name, snap) for name in m_jobs}
        catalog["melee"] = {
            "options": list(m_jobs),
            "default": m_job,
            "option_criteria": option_criteria,
            "choice": {
                "type": "choice",
                "instructions": (
                    "What should the melee line do this tick? "
                    "Each option is defined by what the code will execute. "
                    "You never pick compass directions."
                ),
                "criteria": option_criteria,
            },
        }
    b_jobs = bait_jobs(snap)
    if "snipe" in m_jobs and len(b_jobs) > 1:
        b_job = default_bait_style(b_jobs, snap)
        option_criteria = {name: _bait_option(name, snap) for name in b_jobs}
        catalog["bait"] = {
            "options": list(b_jobs),
            "default": b_job,
            "option_criteria": option_criteria,
            "choice": {
                "type": "choice",
                "instructions": (
                    "If the melee snipes suicide units this tick, how many walk in? "
                    "Each option is defined by how many bodies the code sends. "
                    "You never pick compass directions."
                ),
                "criteria": option_criteria,
            },
        }
    distinct_focus = {
        None if resolve_focus(name, snap) is None else resolve_focus(name, snap)["id"]
        for name in rules
    }
    if len(rules) > 1 and len(distinct_focus) > 1 and not _pure_gunline(snap):
        option_criteria = _target_criteria(snap, rules)
        catalog["target"] = {
            "options": list(rules),
            "default": rule,
            "option_criteria": option_criteria,
            "choice": {
                "type": "choice",
                "instructions": (
                    "Which targeting rule should the army use this tick? "
                    "Code focuses fire on the enemy that rule selects."
                ),
                "criteria": option_criteria,
            },
        }
    aimed = _bar_pair(snap)
    if aimed is not None:
        pack_e, bar_e = aimed
        origin = min(_laser_allies(snap), key=lambda a: a["id"])
        beam_enemies = [e for e in living(snap["enemies"]) if e.get("role") != "heal"]
        option_criteria = {
            "pack": {
                "does": "The laser aims at the enemy with the most neighbors. Other units keep the target rule.",
                "picks": f"E{pack_e['id']}",
                "bar_hits": _beam_hits(origin, pack_e, beam_enemies),
            },
            "bar": {
                "does": "The laser aims at the enemy whose perpendicular bar touches the most bodies. Other units keep the target rule.",
                "picks": f"E{bar_e['id']}",
                "bar_hits": _beam_hits(origin, bar_e, beam_enemies),
            },
        }
        catalog["bar"] = {
            "options": ["pack", "bar"],
            "default": "pack",
            "option_criteria": option_criteria,
            "choice": {
                "type": "choice",
                "instructions": (
                    "A laser is firing, and the neighbor circle picks a different body from the perpendicular bar. "
                    "Which body should the laser aim at? Other guns keep their own target rule. "
                    "The circle is the current laser aim. You never pick compass directions."
                ),
                "criteria": option_criteria,
            },
        }
    if _wing_frame(snap) is not None:
        option_criteria = {
            "stay": {
                "does": "Outer guns attack-move with the center. Nobody steps sideways.",
            },
            "step": {
                "does": "Each outer gun takes one step away from the center, perpendicular to the enemy. The center keeps attack-moving.",
                "when": "Both sides are guns, they have more bodies, nobody can shoot yet, the line is narrower than a gun's reach, and at least one gun is in the center.",
            },
        }
        catalog["wing"] = {
            "options": ["stay", "step"],
            "default": "stay",
            "option_criteria": option_criteria,
            "choice": {
                "type": "choice",
                "instructions": (
                    "Before anyone can shoot, the gun line is narrower than its own reach and the enemy has more bodies. "
                    "Should the outer guns take one sideways step, or attack-move with the center? "
                    "The center does not step. You never pick compass directions."
                ),
                "criteria": option_criteria,
            },
        }
    stand_default = _stand_default(snap)
    if stand_default is not None and "stutter" in r_jobs:
        catalog["stand"] = {
            "options": ["shoot", "step"],
            "default": stand_default,
            "option_criteria": {
                "shoot": {
                    "does": "Guns in the 0.15s window around a 0.5s stand take the shot.",
                    "window": "melee_arrives_near_the_shot",
                },
                "step": {
                    "does": "Guns in that same window step away instead of standing to shoot.",
                    "window": "melee_arrives_near_the_shot",
                },
            },
            "choice": {
                "type": "choice",
                "instructions": (
                    "Enemy melee arrives within 0.15s of the 0.5s stand. "
                    "Should those guns shoot or step? Code moves them. Clear cases stay in code."
                ),
                "criteria": {
                    "shoot": {"does": "Take the shot."},
                    "step": {"does": "Step away."},
                },
            },
        }
    marks = _mark_pair(snap)
    if len(marks) == 2:
        labels = [f"E{e['id']}" for e in marks]
        catalog["mark"] = {
            "options": labels,
            "default": labels[0],
            "option_criteria": {
                labels[0]: {"does": "Focus this melee body. Its health is within one shot of the other.", "hp": round(_ehp(marks[0]), 1)},
                labels[1]: {"does": "Focus the other melee body instead.", "hp": round(_ehp(marks[1]), 1)},
            },
            "choice": {
                "type": "choice",
                "instructions": (
                    "Equal-speed guns can shoot two melee bodies whose health differs by at most one shot. "
                    "Which body should they cover this tick? Code fires."
                ),
                "criteria": {
                    labels[0]: {"does": "Cover the lower health body."},
                    labels[1]: {"does": "Cover the other body."},
                },
            },
        }
    pair = _one_shot_pair(snap)
    if len(pair) == 2:
        labels = [f"E{e['id']}" for e in pair]
        option_criteria = {}
        for enemy, other in (pair, (pair[1], pair[0])):
            guns_n = sum(
                1 for a in living(snap["allies"])
                if a.get("role") == "ranged" and _ready(a) and _can_shoot(a, enemy, snap)
            )
            option_criteria[f"E{enemy['id']}"] = {
                "does": "Cover this enemy first. Guns that can shoot it spend this shot here, then the other body.",
                "hp": round(_ehp(enemy), 1),
                "other_hp": round(_ehp(other), 1),
                "guns_ready": guns_n,
                "gap": "within_one_shot",
            }
        catalog["tie"] = {
            "options": labels,
            "default": labels[0],
            "option_criteria": option_criteria,
            "choice": {
                "type": "choice",
                "instructions": (
                    "Two enemies are in range and their health differs by at most one shot. "
                    "Which one should the guns cover first? Code assigns the shots."
                ),
                "criteria": option_criteria,
            },
        }
    if snap.get("_open_menu") and _rotatable(snap):
        catalog["wounded"] = {
            "options": ["stay", "rotate"],
            "default": "stay",
            "option_criteria": {
                "stay": {"does": "Hurt units keep fighting in place."},
                "rotate": {"does": "A unit under 40% health that an enemy can reach steps back out of reach until it is safe."},
            },
            "choice": {
                "type": "choice",
                "instructions": "Should badly hurt units step back out of enemy reach?",
                "criteria": {"stay": {"does": "Keep fighting."}, "rotate": {"does": "Step back."}},
            },
        }
    if healers and len(wounded) > 1:
        heal_opts = [f"U{u['id']}" for u in wounded[:6]]
        preferred = _heal_target(snap, healers[0])
        default_heal = f"U{preferred['id']}" if preferred is not None and f"U{preferred['id']}" in heal_opts else heal_opts[0]
        option_criteria = {
            f"U{u['id']}": {
                "kind": u.get("name") or u.get("type"),
                "hp": "critical" if u["hp"] <= 0.3 * u["max_hp"] else ("wounded" if u["hp"] <= 0.6 * u["max_hp"] else "scratched"),
                "in_heal_range": bool(_in_weapon_range(healers[0], u)),
                "coverage": _aa_label(u, snap),
                "does": "Heal this wounded ally, or fly toward it.",
            }
            for u in wounded[:6]
        }
        catalog["heal"] = {
            "options": heal_opts,
            "default": default_heal,
            "option_criteria": option_criteria,
            "choice": {
                "type": "choice",
                "instructions": (
                    "Which wounded ally should the healer heal or fly toward this tick?"
                ),
                "criteria": option_criteria,
            },
        }
    return catalog


def _hurt(u: Dict[str, Any]) -> bool:
    full = float(u.get("max_hp") or 1) + float(u.get("max_shield") or 0)
    return (float(u["hp"]) + float(u.get("shield") or 0)) < 0.4 * full


def _threatened(u: Dict[str, Any], snap: Dict[str, Any]) -> bool:
    return any(_can_hit(e, u) and hypot(e, u) <= _weapon_reach(e, u) + 1.0 for e in living(snap["enemies"]))


def _rotatable(snap: Dict[str, Any]) -> bool:
    allies = [a for a in living(snap["allies"]) if a.get("role") != "heal" and not a.get("kamikaze")]
    return len(allies) >= 2 and any(_hurt(a) and _threatened(a, snap) for a in allies)


def catalog_questions(catalog: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """One Choice per open job. Jev's pick is the order; code compiles it."""
    return {kind: spec["choice"] for kind, spec in catalog.items()}


def apply_job_catalog(
    catalog: Dict[str, Dict[str, Any]],
    answers: Any,
) -> Tuple[Dict[str, str], List[str]]:
    """Always apply Jev's Choice. Dummy defaults only if the answer is missing."""
    picks = {kind: spec["default"] for kind, spec in catalog.items()}
    if not isinstance(answers, dict) or not catalog:
        return picks, []
    asked: List[str] = []
    for kind in KIND_ORDER:
        if kind not in catalog:
            continue
        spec = catalog[kind]
        picks[kind] = _pick_choice(answers.get(kind), list(spec["options"]), spec["default"])
        asked.append(kind)
    return picks, asked


def build_state(map_name: str, step: int, snap: Dict[str, Any], recent: List[str]) -> Dict[str, Any]:
    """Kept for traces; Jev commander uses commander_state and does not see the map name."""
    st = commander_state(step, snap, recent)
    st["map"] = map_name
    return st



# ----------------------------------------------------------------------
# Fallback motor
# ----------------------------------------------------------------------

def _fallback_action(
    ally: Dict[str, Any], snap: Dict[str, Any], options: List[Tuple[int, str, Dict[str, Any]]]
) -> int:
    if not options:
        return 0
    matchup = _unit_matchup(ally, snap)
    fires = [(act, key) for act, key, _ in options if key.startswith("fire_")]
    if fires:
        return fires[0][0]
    heals = [(act, key, meta) for act, key, meta in options if key.startswith("heal_")]
    wounded_heals = [item for item in heals if item[2].get("needs_heal")]
    if wounded_heals:
        preferred = _heal_target(snap, ally)
        if preferred is not None:
            for act, key, _meta in wounded_heals:
                if key == f"heal_U{preferred['id']}":
                    return act
        wounded_heals.sort(
            key=lambda item: (
                float(item[2].get("hp") or 0) / max(float(item[2].get("hp_max") or 1), 1e-6),
                item[1],
            )
        )
        return wounded_heals[0][0]
    aims = [
        (act, key)
        for act, key, _ in options
        if key.startswith("hold_aim_") or key.startswith("stand_cooling_")
    ]
    chases = [(act, key) for act, key, _ in options if key.startswith("chase_")]
    walks = [(act, key, meta) for act, key, meta in options if key.startswith("walk_")]
    holds = [(act, key) for act, key, _ in options if key == "hold"]

    def best_walk(prefer: str) -> Optional[int]:
        if not walks:
            return None
        best, best_score = walks[0][0], -1e9
        for act, key, meta in walks:
            rel = _rel(meta)
            if prefer == "farther":
                score = 1 if rel == "farther" else (-1 if rel == "closer" else 0)
            else:
                score = 1 if rel == "closer" else (-1 if rel == "farther" else 0)
            if matchup == "kite":
                away = _group_away_key(snap)
                if away and key == away:
                    score += 3
            if matchup == "melee_brawl":
                spread = _spread_key(ally, snap)
                if spread and key == spread:
                    score += 3
            if score > best_score:
                best_score, best = score, act
        return best

    if matchup == "heal":
        preferred = _heal_cover(snap, ally)
        if preferred is not None and not _heal_comfortable(ally, preferred):
            for act, key, meta in walks:
                vs = meta.get("vs_wounded_ally")
                if isinstance(vs, dict) and vs.get("relation") == "closer":
                    return act
            closer = _close_walk_key(ally, snap, (preferred["x"], preferred["y"]), options)
            for act, key, _meta in walks:
                if closer is not None and key == closer:
                    return act
            if heals:
                return heals[0][0]
        if any(u["hp"] < u["max_hp"] - 1 for u in living(snap["allies"]) if u.get("role") != "heal" and u["id"] != ally["id"]):
            if heals:
                return heals[0][0]
            w = best_walk("closer")
            if w is not None:
                return w
        if heals:
            return heals[0][0]
        if holds:
            return holds[0][0]
    if matchup == "melee_brawl":
        if aims:
            return aims[0][0]
        if _should_spread(snap):
            spread = _spread_key(ally, snap)
            if spread:
                for act, key, _meta in walks:
                    if key == spread:
                        return act
            w = best_walk("farther")
            if w is not None and spread:
                return w
        if chases:
            return chases[0][0]
        if holds:
            return holds[0][0]
        return options[0][0]
    if matchup in {"ranged_trade", "detonate"}:
        if aims:
            return aims[0][0]
        if chases:
            return chases[0][0]
        if holds:
            return holds[0][0]
        return options[0][0]
    if matchup in {"kite", "fade"}:
        melee = [e for e in living(snap["enemies"]) if e.get("role") == "melee"] or living(snap["enemies"])
        nearest = _nearest(ally, melee)
        d_melee = hypot(ally, nearest) if nearest is not None else 99.0
        reach = _weapon_reach(ally, nearest) if nearest is not None else 6.0
        speed_ok = _speed_advantage(snap) >= 0.5
        too_close = d_melee <= 2.2
        almost = d_melee <= reach + 2.0
        away = _group_away_key(snap)
        if speed_ok:
            if not _ready(ally):
                if away:
                    for act, key, _meta in walks:
                        if key == away:
                            return act
                w = best_walk("farther")
                if w is not None:
                    return w
            if aims:
                return aims[0][0]
            if chases:
                return chases[0][0]
            if holds:
                return holds[0][0]
        else:
            too_far = d_melee > reach + 3.2
            if too_far:
                if chases:
                    return chases[0][0]
            if away:
                for act, key, _meta in walks:
                    if key == away:
                        return act
            w = best_walk("farther")
            if w is not None:
                return w
            if aims:
                return aims[0][0]
            if chases:
                return chases[0][0]
            if holds:
                return holds[0][0]
    if matchup == "immobile":
        if ctx_finish := snap.get("_finish_now"):
            if aims:
                return aims[0][0]
            if chases:
                return chases[0][0]
        if chases:
            return chases[0][0]
        w = best_walk("farther")
        if w is not None and not _ready(ally):
            return w
        if aims:
            return aims[0][0]
        if holds:
            return holds[0][0]
        w2 = best_walk("closer")
        if w2 is not None:
            return w2
    if matchup == "funnel":
        if _in_pocket(snap):
            if aims:
                return aims[0][0]
            if holds:
                return holds[0][0]
        elif _too_deep(snap):
            back = _army_toward_key(snap, _centroid(living(snap["enemies"]))) if living(snap["enemies"]) else None
            for act, key, _meta in walks:
                if back and key == back:
                    return act
            w = best_walk("closer")
            if w is not None:
                return w
        else:
            ap = snap.get("attack_point") or snap.get("center")
            toward = _army_toward_key(snap, tuple(ap)) if ap is not None else None
            for act, key, _meta in walks:
                if toward and key == toward:
                    return act
            if walks and ap is not None:
                best, bd = walks[0][0], 1e18
                for act, _key, _meta in walks:
                    dx, dy = WALK[act][2]
                    d = (ally["x"] + dx - ap[0]) ** 2 + (ally["y"] + dy - ap[1]) ** 2
                    if d < bd:
                        bd, best = d, act
                return best
        if holds:
            return holds[0][0]
    if matchup == "evade_kami":
        w = best_walk("farther")
        if w is not None:
            return w
        if holds:
            return holds[0][0]
    return options[0][0]



def _pure_ranged(units: List[Dict[str, Any]]) -> bool:
    live = [u for u in units if u.get("alive")]
    if not live:
        return False
    return all(
        u.get("role") == "ranged" and not u.get("splash") and not u.get("kamikaze")
        for u in live
    )


def _wing_frame(snap: Dict[str, Any]):
    """Perpendicular line frame before contact, or None when a wing step is illegal.

    Both sides are guns, they have more bodies, nobody can shoot yet, our line is
    narrower than a gun's reach, and at least one gun sits in the center. A line
    with no center would split apart, so the step stays closed.
    """
    if not _pure_gunline(snap):
        return None
    allies = [a for a in living(snap["allies"]) if a.get("role") == "ranged"]
    enemies = [e for e in living(snap["enemies"]) if e.get("role") != "heal"]
    if len(allies) < 3 or len(enemies) <= len(allies):
        return None
    if any(_can_shoot(a, e, snap) for a in allies for e in enemies):
        return None
    ax, ay = _centroid(allies)
    ex, ey = _centroid(enemies)
    fx, fy = ex - ax, ey - ay
    fn = (fx * fx + fy * fy) ** 0.5 or 1.0
    px, py = -fy / fn, fx / fn
    offs = [a["x"] * px + a["y"] * py for a in allies]
    span = max(offs) - min(offs)
    reach = min(float(a.get("range") or 0) for a in allies)
    if reach <= 0 or span >= reach - 0.5:
        return None
    center = sum(offs) / len(offs)
    half = max(span / 2.0, 0.4)
    if not any(abs(off - center) < half * 0.55 for off in offs):
        return None
    return allies, px, py, center, half


def _line_spread_key(ally: Dict[str, Any], snap: Dict[str, Any]) -> Optional[str]:
    """One sideways step for an outer gun. Inner guns stay on attack-move."""
    if not snap.get("_pre_fan"):
        return None
    frame = _wing_frame(snap)
    if frame is None:
        return None
    _allies, px, py, center, half = frame
    mine = ally["x"] * px + ally["y"] * py
    if abs(mine - center) < half * 0.55:
        return None
    sign = 1.0 if mine >= center else -1.0
    wx, wy = sign * px, sign * py
    best_key, best = None, -1e18
    for _act, (key, _heading, (dx, dy)) in WALK.items():
        score = dx * wx + dy * wy
        if score > best:
            best, best_key = score, key
    return best_key


def _pure_gunline(snap: Dict[str, Any]) -> bool:
    """Both sides are only guns. Each gun shoots whoever is in its own range.
    A shared focus is not a separate rule for a longer line."""
    return _pure_ranged(snap.get("allies") or []) and _pure_ranged(snap.get("enemies") or [])


def _alive_focus(snap: Dict[str, Any], fid: Optional[int]) -> Optional[Dict[str, Any]]:
    if fid is None:
        return None
    return next((e for e in living(snap["enemies"]) if e["id"] == fid), None)


def _stick_focus(rule: str, snap: Dict[str, Any], sticky_id: Optional[int]) -> Optional[Dict[str, Any]]:
    held = _alive_focus(snap, sticky_id)
    if held is not None:
        return held
    return resolve_focus(rule, snap)


def _force_signature(snap: Dict[str, Any]) -> Tuple[int, int, int, int, int, int]:
    allies = living(snap["allies"])
    enemies = living(snap["enemies"])
    return (
        len(allies),
        len(enemies),
        sum(1 for a in allies if a.get("role") == "ranged"),
        sum(1 for a in allies if a.get("role") == "melee"),
        sum(1 for e in enemies if e.get("role") == "melee"),
        sum(1 for e in enemies if e.get("kamikaze")),
    )


def apply_physics_veto(
    snap: Dict[str, Any], form: str, r_job: str, m_job: str
) -> Tuple[str, str, str]:
    """Jev cannot override facts the engine already computed."""
    r_jobs = ranged_jobs(snap)
    m_jobs = melee_jobs(snap)
    form_opts = formation_jobs(snap)
    tanks = _fighters(snap, "melee")
    r_line = _fighters(snap, "ranged")
    contact = _bucket_contact(snap, r_line) if r_line else "none"
    blast = _suicide_blast(snap)
    kami_e = any(e.get("kamikaze") for e in living(snap["enemies"]))
    kami_a = any(a.get("kamikaze") for a in living(snap["allies"]))
    if m_job == "hold_choke" and len(living(snap["enemies"])) < 2 and "charge" in m_jobs:
        m_job = "charge"
    if r_job not in r_jobs and r_jobs:
        r_job = default_ranged_job(r_jobs, snap)
    if m_job not in m_jobs and m_jobs:
        m_job = default_melee_job(m_jobs, snap)
    if form_opts and form not in form_opts:
        form = default_formation(form_opts)
    return form, r_job, m_job


def _exam_needed(
    kind: str,
    spec: Dict[str, Any],
    step: int,
    sticky: Dict[str, Tuple[str, Tuple[str, ...]]],
    sig: Tuple[int, ...],
    prev_sig: Optional[Tuple[int, ...]],
) -> bool:
    if len(spec.get("options") or []) <= 1:
        return False
    if prev_sig != sig:
        return True
    st = sticky.get(kind)
    if st is None:
        return True
    pick, opts = st
    if pick not in spec["options"]:
        return True
    # Target/heal option lists flicker every tick; keep the sticky pick.
    if kind in {"stand", "bomb"}:
        return st[0] != spec.get("default")
    if kind in {"target", "heal"}:
        return False
    if tuple(spec["options"]) != opts:
        return True
    return False


# ----------------------------------------------------------------------
# Main loop
# ----------------------------------------------------------------------

WING_CALLS = ("stay", "step")
# Two-word exams that hold their pick until it goes illegal:
# kind -> (legal picks, snap key the motor reads, physics gate).
STICKY_EXAMS = {
    "stand": (("shoot", "step"), "_stand_call", lambda snap: True),
    "bar": (("pack", "bar"), "_bar_aim", lambda snap: bool(_laser_allies(snap))),
}
# Exams whose answer is applied after the menu write-back.
PENDING_EXAMS = ("tie", "stand", "mark", "bar", "wing")


class JevActionPolicy:

    """Closed job bank; Jev's Choice is the job. Code is the motor."""

    def __init__(self, client=None, tag: str = "jev", full_menu: bool = False, open_menu: bool = False):
        self.client = client if client is not None else JevClient()
        self.tag = tag
        self.open_menu = open_menu
        # full_menu: every legal exam, every tick, no evidence gate. For
        # program clients whose picks change with the situation.
        self.full_menu = full_menu
        self.n_calls = 0
        self.n_fallback = 0
        self.n_guard = 0
        self.n_questions = 0
        self.infer_s = 0.0
        self.tactic_counts: Dict[str, int] = {}
        self.plan_counts: Dict[str, int] = {}
        self._input_tokens = 0
        self.n_override = 0
        self.overrides: List[str] = []
        self.n_asked = 0
        self.asked_counts: Dict[str, int] = {}
        self._reset_episode()

    def _reset_episode(self) -> None:
        self._recent: List[str] = []
        self._focus_id: Optional[int] = None
        self._focus_rule: str = ""
        self._prev_our_hp: Optional[float] = None
        self._prev_their_hp: Optional[float] = None
        self._hp_trend = "no_trade_yet"
        self._stance_age = 0
        self._last_stance = ""
        self._prev_xy: Dict[int, Tuple[float, float]] = {}
        self._sticky: Dict[str, Tuple[str, Tuple[str, ...]]] = {}
        self._force_sig: Optional[Tuple[int, ...]] = None
        # Answers from this tick's exams, consumed after the menu write-back.
        self._pending: Dict[str, Any] = {}
        self._block_stand: bool = False
        self._laser_id: Optional[int] = None

    def _held_pick(self, kind: str, legal: Tuple[str, ...]) -> Optional[str]:
        """This tick's answer if legal, else the held sticky pick if still legal."""
        val = self._pending.pop(kind, None)
        if val in legal:
            return val
        held = self._sticky.get(kind)
        if held and held[0] in legal:
            return held[0]
        return None

    def _apply_sticky_exam(self, kind: str, snap: Dict[str, Any]) -> None:
        legal, snap_key, gate = STICKY_EXAMS[kind]
        val = self._held_pick(kind, legal)
        if val is not None and gate(snap):
            snap[snap_key] = val
            self._sticky[kind] = (val, legal)
        else:
            self._sticky.pop(kind, None)

    def act(self, map_name: str, step: int, snap: Dict[str, Any]) -> List[int]:
        n = snap["n_agents"]
        actions = [0] * n
        allies = living(snap["allies"])
        if not allies:
            return actions

        plans = legal_plans(snap)
        rules = target_rules(snap)
        wounded = [a for a in allies if a.get("role") != "heal" and a["hp"] < a["max_hp"] - 1]
        healers = [a for a in allies if a.get("role") == "heal"]

        if step == 0:
            self._reset_episode()

        if self.open_menu:
            snap["_open_menu"] = True
        stuck = set()
        for a in allies:
            prev = self._prev_xy.get(a["id"])
            if prev is None:
                continue
            dest = None
            fid = self._focus_id
            if fid is not None:
                dest = next((e for e in living(snap["enemies"]) if e["id"] == fid), None)
            if dest is None:
                dest = _nearest(a, living(snap["enemies"]))
            if dest is None:
                continue
            old_d = (prev[0] - dest["x"]) ** 2 + (prev[1] - dest["y"]) ** 2
            now_d = (a["x"] - dest["x"]) ** 2 + (a["y"] - dest["y"]) ** 2
            moved = abs(a["x"] - prev[0]) + abs(a["y"] - prev[1])
            if now_d >= old_d - 0.05 and moved < 0.2:
                stuck.add(a["id"])
        snap["_stuck_close"] = stuck

        our_hp = sum(_ehp(a) for a in allies)
        their_hp = sum(_ehp(e) for e in living(snap["enemies"]))
        if self._prev_our_hp is None:
            self._hp_trend = "no_trade_yet"
        else:
            d_us = our_hp - self._prev_our_hp
            d_them = self._prev_their_hp - their_hp
            if d_us < -8 and d_them <= 8:
                self._hp_trend = "we_are_bleeding"
            elif d_them > 8 and d_us >= -8:
                self._hp_trend = "they_are_bleeding"
            elif d_us < -1 or d_them > 1:
                self._hp_trend = "trading"
            else:
                self._hp_trend = "no_damage"
        self._prev_our_hp = our_hp
        self._prev_their_hp = their_hp

        if any(a.get("role") == "melee" for a in allies):
            self._block_stand = True
        snap["_block_stand"] = self._block_stand
        plan = army_plan(snap)
        snap["_plan"] = plan
        rule = default_target_rule(snap)
        heal_id = None
        intents = army_intents(snap)
        form_opts = formation_jobs(snap)
        r_jobs = ranged_jobs(snap)
        m_jobs = melee_jobs(snap)
        snap["_legal_intents"] = intents
        snap["_formation_jobs"] = form_opts
        if self._stance_age <= 1:
            held = "first_tick"
        elif self._stance_age <= 4:
            held = "a_few_ticks"
        else:
            held = "many_ticks"
        snap["_stance_held_for"] = held

        form = default_formation(form_opts)
        r_job = default_ranged_job(r_jobs, snap)
        m_job = default_melee_job(m_jobs, snap)
        k_jobs = kite_jobs(snap)
        k_job = default_kite_style(k_jobs, snap)
        b_jobs = bait_jobs(snap)
        b_job = default_bait_style(b_jobs, snap)
        code_defaults = {"formation": form, "ranged": r_job, "melee": m_job, "kite": k_job, "bait": b_job, "target": rule}
        sig = _force_signature(snap)
        prev_sig = self._force_sig
        menus = {"formation": form_opts, "ranged": r_jobs, "melee": m_jobs, "kite": k_jobs, "bait": b_jobs}
        if prev_sig != sig:
            self._sticky = {
                k: v for k, v in self._sticky.items()
                if v[0] in (menus.get(k) or [v[0]])
            }
        held_jobs = {}
        for kind, opts in menus.items():
            held = self._sticky.get(kind)
            if held and held[0] in (opts or [held[0]]):
                held_jobs[kind] = held[0]
        form = held_jobs.get("formation", form)
        r_job = held_jobs.get("ranged", r_job)
        m_job = held_jobs.get("melee", m_job)
        k_job = held_jobs.get("kite", k_job)
        b_job = held_jobs.get("bait", b_job)
        form, r_job, m_job = apply_physics_veto(snap, form, r_job, m_job)
        snap["_live_tactic"] = _live_tactic(snap)

        catalog = build_job_catalog(
            snap, form_opts, r_jobs, m_jobs, rules, wounded, healers, form, r_job, m_job, rule
        )
        # "default" is the held pick for menus; "code_default" is what code
        # alone would do this tick. Test clients pin against the latter.
        for kind, spec in catalog.items():
            spec["code_default"] = code_defaults.get(kind, spec["default"])
        # Tell Jev the exams that are really open, not the class's wish list.
        snap["_live_tactic"]["jev"] = ",".join(catalog) or "none"
        if not self.full_menu:
            catalog = {
                kind: spec
                for kind, spec in catalog.items()
                if _exam_needed(kind, spec, step, self._sticky, sig, prev_sig)
            }
        # Only exams with Force evidence reach Jev. Closed ones still run the
        # same path, answered with the code default, exactly like Dummy.
        exams = catalog if self.full_menu else {kind: spec for kind, spec in catalog.items() if kind in EXAM_EVIDENCE}
        snap["_catalog_options"] = {kind: spec["options"] for kind, spec in exams.items()}
        snap["_catalog_defaults"] = {kind: spec["default"] for kind, spec in exams.items()}
        questions = catalog_questions(exams) if exams else {}
        asked: List[str] = []
        self._force_sig = sig

        if catalog:
            # Dummy is a client that takes every default; it runs the same
            # path as Jev so "Jev picked the default" == Dummy.
            local = isinstance(self.client, DummyClient)
            result: Any = {"answers": {}}
            if questions:
                state = None if local else commander_state(step, snap, self._recent, self._hp_trend)
                if hasattr(self.client, "defaults"):
                    self.client.defaults = {kind: spec["code_default"] for kind, spec in exams.items()}
                result = self.client.system_one(state, questions)
                if not local:
                    self.n_calls += 1
                    self.n_questions += len(questions)
                self.infer_s = self.client.infer_s
                self._input_tokens += int((self.client.last_usage or {}).get("input_tokens") or 0)
            answers = (result or {}).get("answers") if isinstance(result, dict) else None
            if not isinstance(answers, dict):
                self.n_fallback += 1
            else:
                picks, asked = apply_job_catalog(catalog, answers)
                form = picks.get("formation", form)
                r_job = picks.get("ranged", r_job)
                m_job = picks.get("melee", m_job)
                k_job = picks.get("kite", k_job)
                b_job = picks.get("bait", b_job)
                rule = picks.get("target", rule)
                form, r_job, m_job = apply_physics_veto(snap, form, r_job, m_job)
                sent = [kind for kind in asked if kind in questions]
                if sent:
                    self.n_asked += 1
                for kind in sent:
                    self.asked_counts[kind] = self.asked_counts.get(kind, 0) + 1
                if "wounded" in asked:
                    snap["_wounded_call"] = picks.get("wounded")
                if "heal" in asked:
                    pick = picks.get("heal")
                    try:
                        heal_id = int(str(pick)[1:])
                    except (TypeError, ValueError):
                        heal_id = None
                for kind in PENDING_EXAMS:
                    if kind in asked:
                        self._pending[kind] = picks.get(kind)
                # Count every exam where Jev left the code default, not only the menus.
                final = {"formation": form, "ranged": r_job, "melee": m_job, "kite": k_job, "bait": b_job, "target": rule}
                for kind in asked:
                    before = catalog[kind]["default"]
                    after = final.get(kind, picks.get(kind))
                    if before != after:
                        self.n_override += 1
                        if len(self.overrides) < 48:
                            self.overrides.append(f"t={step} {kind} {before}->{after}")

        chosen_jobs = {"formation": form, "ranged": r_job, "melee": m_job, "kite": k_job, "bait": b_job}
        for kind, opts in menus.items():
            if opts:
                self._sticky[kind] = (chosen_jobs[kind], tuple(opts))
        self._sticky["target"] = (rule, tuple(rules))
        pair = _one_shot_pair(snap)
        tie_labels = tuple(f"E{e['id']}" for e in pair) if len(pair) == 2 else ()
        tie_pick = self._held_pick("tie", tie_labels)
        if tie_pick is not None:
            try:
                snap["_tie_prefer"] = int(str(tie_pick)[1:])
            except (TypeError, ValueError):
                pass
            self._sticky["tie"] = (tie_pick, tie_labels)
        else:
            self._sticky.pop("tie", None)
        self._apply_sticky_exam("stand", snap)
        mark_id = None
        mark_pick = self._pending.pop("mark", None)
        if mark_pick:
            try:
                mark_id = int(str(mark_pick)[1:])
            except (TypeError, ValueError):
                mark_id = None
        snap["_mark_id"] = mark_id
        self._apply_sticky_exam("bar", snap)
        wing_call = self._held_pick("wing", WING_CALLS)
        if wing_call == "step" and _wing_frame(snap) is not None:
            snap["_pre_fan"] = True
            self._sticky["wing"] = ("step", WING_CALLS)
        elif wing_call == "stay":
            self._sticky["wing"] = ("stay", WING_CALLS)
        else:
            self._sticky.pop("wing", None)
        self._pending.clear()
        snap.pop("_shot_plan", None)

        if _pure_gunline(snap):
            focus = None
            self._focus_id = None
            self._focus_rule = rule
        else:
            if self._focus_rule == rule:
                focus = _alive_focus(snap, self._focus_id)
            else:
                focus = None
            if focus is None:
                focus = resolve_focus(rule, snap)
            self._focus_id = None if focus is None else focus["id"]
            self._focus_rule = rule
        if snap.get("_bar_aim") == "bar" and not _pure_gunline(snap):
            body = _alive_focus(snap, getattr(self, "_laser_id", None)) or _laser_focus(snap)
            self._laser_id = None if body is None else body["id"]
            snap["_laser_id"] = self._laser_id
        else:
            self._laser_id = None
        snap["_focus_id"] = self._focus_id
        if snap.get("_mark_id") is not None and not _pure_gunline(snap):
            snap["_focus_id"] = snap["_mark_id"]
        snap["_formation"] = form
        snap["_ranged_job"] = r_job
        snap["_melee_job"] = m_job
        snap["_kite_style"] = k_job if r_job in {"stutter", "concave"} else "none"
        snap["_bait_style"] = b_job if m_job == "snipe" else "none"
        stance = "spread" if form == "open" else (r_job or m_job or "close")
        snap["_intent"] = stance
        tag = f"f={form}|r={r_job}|k={k_job}|m={m_job}|b={b_job}"
        if tag == self._last_stance:
            self._stance_age += 1
        else:
            self._last_stance = tag
            self._stance_age = 1
        if heal_id is not None:
            snap["_heal_id"] = heal_id

        chosen: Dict[int, str] = {}
        for ally in snap["allies"]:
            i = ally["id"]
            if not ally.get("alive"):
                continue
            if plan == "cycle":
                # Buildings: dead-zone stagger is physics, not a Jev compass pick.
                options = legal_options(ally, snap, prune=True)
                act = _fallback_action(ally, snap, options)
            else:
                options = legal_options(ally, snap, prune=False)
                if ally.get("kamikaze"):
                    intent = "close"
                elif snap.get("_wounded_call") == "rotate" and _hurt(ally) and _threatened(ally, snap):
                    intent = "evade"
                elif any(a.get("kamikaze") for a in living(snap["allies"])) and not ally.get("kamikaze"):
                    # Non-suicide units do not dive the blast their bombs are about to chain.
                    intent = "evade"
                elif form == "open" and _ally_spacing(ally, snap) < 4.0:
                    intent = "spread"
                elif ally.get("role") == "melee" and m_job == "snipe":
                    intent = "snipe"
                elif ally.get("role") == "ranged":
                    intent = JOB_TO_INTENT.get(r_job, "close")
                elif ally.get("role") == "melee":
                    intent = JOB_TO_INTENT.get(m_job, "close")
                else:
                    intent = "close"
                act = execute_intent(ally, snap, intent, options)
            actions[i] = act
            key = next((k for a, k, _ in options if a == act), "none")
            chosen[i] = key
            self.tactic_counts[key] = self.tactic_counts.get(key, 0) + 1
        self.plan_counts[plan] = self.plan_counts.get(plan, 0) + 1
        self.tactic_counts["form:" + form] = self.tactic_counts.get("form:" + form, 0) + 1
        tac = snap.get("_live_tactic") or {}
        if tac.get("name"):
            key = "tactic:" + tac["name"]
            self.tactic_counts[key] = self.tactic_counts.get(key, 0) + 1
        if r_jobs:
            self.tactic_counts["ranged:" + r_job] = self.tactic_counts.get("ranged:" + r_job, 0) + 1
        if m_jobs:
            self.tactic_counts["melee:" + m_job] = self.tactic_counts.get("melee:" + m_job, 0) + 1
        if k_jobs and r_job in {"stutter", "concave"}:
            self.tactic_counts["kite:" + k_job] = self.tactic_counts.get("kite:" + k_job, 0) + 1
        if b_jobs and m_job == "snipe":
            self.tactic_counts["bait:" + b_job] = self.tactic_counts.get("bait:" + b_job, 0) + 1

        focus_lab = "none" if focus is None else f"E{focus['id']}"
        order = " ".join(f"U{i}={chosen.get(i, 'noop')}" for i in range(n) if snap["allies"][i].get("alive"))
        a_hp = ",".join(f"U{a['id']}:{a['hp']:.0f}" for a in living(snap["allies"]))
        e_hp = ",".join(f"E{e['id']}:{e['hp']:.0f}" for e in living(snap["enemies"]))
        r_line = _fighters(snap, "ranged")
        r_contact = _bucket_contact(snap, r_line) if r_line else "-"
        tanks = "tanks" if _fighters(snap, "melee") else "no_tanks"
        self._recent.append(
            f"t={step} form={form} ranged={r_job} melee={m_job} "
            f"contact={_bucket_contact(snap)} r_contact={r_contact} {tanks} "
            f"blast={_suicide_blast(snap)} "
            f"trend={self._hp_trend} A[{a_hp}] E[{e_hp}]"
        )
        ms = 0.0 if self.client.n_calls == 0 else 1000.0 * (self.client.infer_s / max(1, self.client.n_calls))
        openq = ",".join(catalog.keys()) if catalog else "-"
        askedq = ",".join(asked) if asked else "-"
        if not os.environ.get("JEV_QUIET"):
            tac_name = (snap.get("_live_tactic") or {}).get("name") or "-"
            print(
                f"    {self.tag} t={step} tactic={tac_name} form={form} ranged={r_job} kite={snap.get('_kite_style')} "
                f"melee={m_job} bait={snap.get('_bait_style')} "
                f"contact={_bucket_contact(snap)} r_contact={r_contact} {tanks} "
                f"blast={_suicide_blast(snap)} "
                f"plan={plan} target={rule} focus={focus_lab} "
                f"r_jobs={r_jobs} k_jobs={k_jobs} m_jobs={m_jobs} b_jobs={b_jobs} "
                f"open={openq} asked={askedq} {ms:.0f}ms",
                flush=True,
            )
            if step < 3 or step % 15 == 0:
                print(f"      {order}", flush=True)
        self._prev_xy = {
            a["id"]: (float(a["x"]), float(a["y"]))
            for a in snap["allies"]
            if a.get("alive")
        }
        return actions


# ----------------------------------------------------------------------
# Test clients: Force pins picks, Dummy takes defaults
# ----------------------------------------------------------------------

class ForceClient:
    """Stub that sits chosen exams and picks given jobs. Motor + Jev-out-of-loop tests."""

    def __init__(self, picks: Dict[str, str]):
        self.picks = dict(picks)
        self.defaults: Dict[str, str] = {}
        self.n_calls = 0
        self.infer_s = 0.0
        self.last_usage: Dict[str, int] = {}

    def system_one(self, state: Any, questions: Dict[str, Any]) -> Optional[dict]:
        self.n_calls += 1
        answers: Dict[str, Any] = {}
        for qid, q in questions.items():
            qtype = (q or {}).get("type")
            if qtype == "choice" and qid in self.picks:
                pick = self.picks[qid]
                if pick == "!default":
                    # Pin the first option that is not the code default.
                    opts = list((q or {}).get("criteria") or {})
                    alt = [o for o in opts if o != self.defaults.get(qid)]
                    if not alt:
                        continue
                    pick = alt[0]
                answers[qid] = {"choice": pick, "probabilities": {pick: 0.99}}
        return {"answers": answers}


class DummyClient:
    """Answer every exam with its code default. Attack-move baseline for motor tests."""

    def __init__(self):
        self.n_calls = 0
        self.infer_s = 0.0
        self.last_usage: Dict[str, int] = {}

    def system_one(self, state: Any, questions: Dict[str, Any]) -> Optional[dict]:
        return {"answers": {}}


class DummyActionPolicy(JevActionPolicy):
    def __init__(self):
        super().__init__(client=DummyClient(), tag="def")


class ForceActionPolicy(JevActionPolicy):
    def __init__(self, picks: Optional[Dict[str, str]] = None):
        super().__init__(client=ForceClient(picks or {"ranged": "stutter"}), tag="force")


def _program_mode(policy: "JevActionPolicy", prog: Dict[str, Any], step: int, snap: Dict[str, Any]) -> None:
    """Point the policy at the program's menu mode for this tick.

    open: every executable job, program answers every exam; gated: the physics
    gates; dummy: the exact Dummy path. A rule may carry its own mode, so a
    distilled program can be Dummy in one situation and hold in another.
    """
    import tactic_dsl as T

    mode = prog.get("menu") or "open"
    if any(r.get("menu") for r in prog.get("rules") or []):
        state = commander_state(step, dict(snap), list(policy._recent), policy._hp_trend)
        mode = T.menu_for(prog, T.features(state))
    if mode == "dummy":
        policy.client, policy.full_menu, policy.open_menu = policy._dummy_client, False, False
    else:
        policy._prog_client.prog = prog
        policy.client, policy.full_menu, policy.open_menu = policy._prog_client, True, mode == "open"


class ProgramActionPolicy(JevActionPolicy):
    """Runs one tactic program (tactic_dsl) with no model in the loop."""

    def __init__(self, prog: Dict[str, Any], tag: str = "prog"):
        from tactic_dsl import ProgramClient

        # Forged programs run on the open menu; a program marked "menu": "gated"
        # (the hand baseline) keeps the physics gates it was written against.
        super().__init__(client=ProgramClient(prog), tag=tag, full_menu=True, open_menu=prog.get("menu") != "gated")
        self.prog = prog
        self._prog_client = self.client
        self._dummy_client = DummyClient()

    def act(self, map_name: str, step: int, snap: Dict[str, Any]) -> List[int]:
        _program_mode(self, self.prog, step, snap)
        return super().act(map_name, step, snap)


class LibraryPolicy(JevActionPolicy):
    """Pick a forged program from the library, then let it answer every exam.

    chooser: "jev" asks Jev one Choice among the k nearest programs;
    "nearest" takes the closest; "random" takes one of the k at random.
    Re-picks at the start and whenever the force composition changes.
    No simulator in the loop.
    """

    NONE_ID = "none"

    def __init__(
        self,
        lib: List[Dict[str, Any]],
        chooser: str = "jev",
        k: int = 4,
        selector=None,
        seed: int = 0,
        tag: str = "",
        clusters: Optional[Dict[str, Any]] = None,
        fallback: bool = False,
        evidence: Optional[Dict[str, Any]] = None,
        n_neighbors: int = 5,
    ):
        import random as _random

        from tactic_dsl import ProgramClient

        # Starts as Dummy until a program is picked. fallback adds a "none"
        # candidate that runs the exact Dummy path.
        super().__init__(client=DummyClient(), tag=tag or f"lib_{chooser}")
        self._dummy_client = self.client
        self._prog_client = ProgramClient({"name": "none", "rules": [], "else": {}})
        self.lib = lib
        self.chooser = chooser
        self.k = k
        self.clusters = clusters
        self.fallback = fallback
        # evidence: {"train_vecs": {fight: vec}, "programs": {id: {fight: {flip, lose, net}}}}
        self.evidence = evidence
        self.n_neighbors = n_neighbors
        self.selector = selector if selector is not None or chooser not in ("jev", "jev2", "jev3") else JevClient()
        self._rng = _random.Random(seed)
        self._pick_sig: Optional[Tuple[int, ...]] = None
        self.picks_made: List[str] = []
        self.n_select_calls = 0

    def _run(self, entry: Optional[Dict[str, Any]]) -> None:
        self._cur_prog = None if entry is None else entry["program"]
        if entry is None:
            self.client, self.full_menu, self.open_menu = self._dummy_client, False, False
            return
        prog = entry["program"]
        self._prog_client.prog = prog
        self.client, self.full_menu = self._prog_client, True
        self.open_menu = prog.get("menu") != "gated"

    def _candidates(self, vec: List[float]) -> List[Dict[str, Any]]:
        import tactic_dsl as T

        if not self.clusters:
            return T.nearest(self.lib, vec, self.k)
        order = sorted(
            range(len(self.clusters["centroids"])),
            key=lambda j: sum((a - b) ** 2 for a, b in zip(self.clusters["centroids"][j], vec)),
        )
        out: List[Dict[str, Any]] = []
        for j in order:
            out.extend(e for e in self.lib if e.get("cluster") == j)
            if len(out) >= self.k:
                break
        return out[: self.k]

    def _choose(self, step: int, snap: Dict[str, Any]) -> None:
        import tactic_dsl as T

        # Copy so the Dummy path sees exactly the snapshot it would have seen.
        state = commander_state(step, dict(snap), list(self._recent), self._hp_trend)
        vec = T.feature_vector(T.features(state))
        cands: List[Optional[Dict[str, Any]]] = list(self._candidates(vec))
        if self.fallback:
            cands.append(None)
        if not cands:
            return
        pick = cands[0]
        if self.chooser == "random":
            pick = self._rng.choice(cands)
        elif self.chooser == "evidence":
            ev = self._neighbor_evidence(vec, cands)
            best = max(cands, key=lambda e: (ev[self._cid(e)]["net"], -cands.index(e)))
            pick = best if ev[self._cid(best)]["net"] > 0 else (None if self.fallback else best)
        elif self.chooser == "jev2" and len(cands) > 1:
            pick = self._ask_jev2(state, vec, cands)
        elif self.chooser == "jev3" and len(cands) > 1:
            # Evidence decides when it is clear; Jev only breaks unclear cases.
            ev = self._neighbor_evidence(vec, cands)
            ranked = sorted(cands, key=lambda e: (ev[self._cid(e)]["net"], -cands.index(e)), reverse=True)
            top, second = ev[self._cid(ranked[0])]["net"], ev[self._cid(ranked[1])]["net"]
            if top >= 3 and top - second >= 2:
                pick = ranked[0]
            else:
                pick = self._ask_jev2(state, vec, cands)
        elif self.chooser == "jev" and len(cands) > 1:
            criteria = {}
            for e in cands:
                if e is None:
                    criteria[self.NONE_ID] = {
                        "does": "No program: attack-move with the code-default target rule. This is the baseline.",
                        "record": "baseline",
                    }
                    continue
                if "confirm_net" in e:
                    record = (
                        f"on {e['fights']} fresh fights like this, {e['confirm_net']:+d} wins "
                        f"compared with the baseline"
                    )
                else:
                    tr = e.get("transfer") or {}
                    beat = sum(1 for r in tr.values() if r["wins"] > r["dummy"])
                    record = f"won {e['wins']}/5 where it was written; beat attack-move on {beat} of {len(tr)} training fights"
                criteria[e["id"]] = {
                    "does": T.summarize(e["program"]),
                    "idea": e["program"].get("why", ""),
                    "won_fight_like": {
                        k: e["feats"].get(k)
                        for k in ("speed", "reach", "numbers", "our_ranged", "our_melee", "enemy_guns", "enemy_melee_n", "enemy_suicide", "pocket")
                    },
                    "record": record,
                }
            questions = {
                "program": {
                    "type": "choice",
                    "instructions": (
                        "Which tactic program should the army run from now on? Each program sets "
                        "exam picks from physical conditions; code moves the units."
                    ),
                    "criteria": criteria,
                }
            }
            result = self.selector.system_one(state, questions)
            self.n_select_calls += 1
            answers = (result or {}).get("answers") if isinstance(result, dict) else None
            first = self.NONE_ID if cands[0] is None else cands[0]["id"]
            chosen = _pick_choice((answers or {}).get("program"), list(criteria), first)
            pick = next((e for e in cands if (e is None and chosen == self.NONE_ID) or (e is not None and e["id"] == chosen)), None)
        self._run(pick)
        self.picks_made.append(f"t={step} {self.NONE_ID if pick is None else pick['id']}")

    def _cid(self, e: Optional[Dict[str, Any]]) -> str:
        return self.NONE_ID if e is None else e["id"]

    def _neighbor_fights(self, vec: List[float]) -> List[str]:
        tv = (self.evidence or {}).get("train_vecs") or {}
        return sorted(tv, key=lambda f: sum((a - b) ** 2 for a, b in zip(tv[f], vec)))[: self.n_neighbors]

    def _neighbor_evidence(self, vec: List[float], cands: List[Optional[Dict[str, Any]]]) -> Dict[str, Dict[str, int]]:
        """Paired record vs attack-move on the most similar training fights."""
        fights = self._neighbor_fights(vec)
        progs = (self.evidence or {}).get("programs") or {}
        out: Dict[str, Dict[str, int]] = {}
        for e in cands:
            cid = self._cid(e)
            rec = {"flip": 0, "lose": 0, "net": 0, "fights": len(fights)}
            if e is not None:
                for f in fights:
                    r = (progs.get(cid) or {}).get(f)
                    if r:
                        rec["flip"] += r["flip"]
                        rec["lose"] += r["lose"]
                        rec["net"] += r["net"]
            out[cid] = rec
        return out

    def _ask_jev2(self, state: Dict[str, Any], vec: List[float], cands: List[Optional[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
        """Jev picks with similarity rank and paired evidence on similar fights."""
        import tactic_dsl as T

        ev = self._neighbor_evidence(vec, cands)
        ranks = {}
        if self.clusters:
            order = sorted(
                range(len(self.clusters["centroids"])),
                key=lambda j: sum((a - b) ** 2 for a, b in zip(self.clusters["centroids"][j], vec)),
            )
            ranks = {j: i for i, j in enumerate(order)}
        criteria = {}
        for e in cands:
            cid = self._cid(e)
            r = ev[cid]
            if e is None:
                criteria[cid] = {
                    "does": "Baseline: attack-move with the code-default target rule. No program.",
                    "similar_fights_record": "baseline (by definition 0 flips, 0 losses)",
                }
                continue
            rank = ranks.get(e.get("cluster"), 99)
            criteria[cid] = {
                "does": T.summarize(e["program"]),
                "idea": e["program"].get("why", ""),
                "similarity": ["closest cluster", "second closest cluster", "third closest cluster"][rank] if rank < 3 else "farther cluster",
                "similar_fights_record": (
                    f"on the {r['fights']} most similar training fights x 5 seeds, compared seed by seed with "
                    f"attack-move: turned {r['flip']} losses into wins, turned {r['lose']} wins into losses (net {r['net']:+d})"
                ),
            }
        questions = {
            "program": {
                "type": "choice",
                "instructions": (
                    "Pick the tactic program for this fight. Code moves the units; a program only sets exam picks. "
                    "similar_fights_record is paired evidence from training fights most like this one: "
                    "each count compares the program with attack-move on the same fight and spawn. "
                    "Prefer a program whose record is clearly positive and that comes from a close cluster. "
                    "If the evidence is weak, mixed, or negative, choose the baseline."
                ),
                "criteria": criteria,
            }
        }
        result = self.selector.system_one(state, questions)
        self.n_select_calls += 1
        answers = (result or {}).get("answers") if isinstance(result, dict) else None
        chosen = _pick_choice((answers or {}).get("program"), list(criteria), self._cid(cands[0]))
        return next((e for e in cands if self._cid(e) == chosen), None)

    def act(self, map_name: str, step: int, snap: Dict[str, Any]) -> List[int]:
        if step == 0:
            self._pick_sig = None
        # Re-pick only when a role appears or vanishes, not on every death.
        sig = tuple(v > 0 for v in _force_signature(snap)[2:])
        if sig != self._pick_sig and living(snap["allies"]) and living(snap["enemies"]):
            self._choose(step, snap)
            self._pick_sig = sig
        if getattr(self, "_cur_prog", None) is not None:
            _program_mode(self, self._cur_prog, step, snap)
        return super().act(map_name, step, snap)


class OnlinePolicy(LibraryPolicy):
    """The online default: forged cluster library, nearest cluster, Dummy fallback.

    Jev (chooser="jev2") replaces the nearest-cluster pick only once it wins a
    paired comparison against it on test2.
    """

    LIBRARIES = {
        "lib3": ("cluster_programs.json", "evidence.json"),
        "outcome": ("outcome_programs.json", "evidence_outcome.json"),
    }

    def __init__(self, chooser: str = "nearest", seed: int = 0, tag: str = "online", k: int = 4, n_neighbors: int = 5, library: str = "lib3"):
        import json as _json
        from pathlib import Path as _Path

        lib_dir = _Path(__file__).resolve().parent / "kb" / "library"
        lib_file, ev_file = self.LIBRARIES[library]
        lib = [e for e in _json.loads((lib_dir / lib_file).read_text()) if e.get("source") != "hand"]
        clusters = _json.loads((lib_dir / "clusters.json").read_text())
        ev_path = lib_dir / ev_file
        evidence = _json.loads(ev_path.read_text()) if ev_path.is_file() else None
        super().__init__(lib, chooser=chooser, k=k, seed=seed, tag=tag, clusters=clusters, fallback=True, evidence=evidence, n_neighbors=n_neighbors)


class ApiActionPolicy(JevActionPolicy):
    """Same jobs as Jev, answered by the LLM gateway with reasoning off."""

    def __init__(self):
        from system2_api import System2Client

        super().__init__(client=System2Client(), tag="api")


class ScriptActionPolicy:
    """Same motor as Jev, script defaults for plan/target, sticky focus."""

    def __init__(self):
        self._focus_id: Optional[int] = None

    def act(self, map_name: str, step: int, snap: Dict[str, Any]) -> List[int]:
        n = snap["n_agents"]
        actions = [0] * n
        if step == 0:
            self._focus_id = None
        snap["_plan"] = army_plan(snap)
        rule = default_target_rule(snap)
        if _pure_gunline(snap):
            focus = None
        else:
            focus = _stick_focus(rule, snap, self._focus_id)
        self._focus_id = None if focus is None else focus["id"]
        snap["_focus_id"] = self._focus_id
        for ally in snap["allies"]:
            i = ally["id"]
            if not ally.get("alive"):
                continue
            options = legal_options(ally, snap)
            actions[i] = _fallback_action(ally, snap, options)
        return actions
