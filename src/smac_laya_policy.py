"""Laya action heads for SMAClite, using SMAC paper constraints + Laya snake-style options."""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ACTION_NAMES = {0: "noop", 1: "stop", 2: "N", 3: "S", 4: "E", 5: "W"}
MOVE_DELTA = {"N": (0.0, 2.0), "S": (0.0, -2.0), "E": (2.0, 0.0), "W": (-2.0, 0.0)}
KB_PATH = Path(__file__).resolve().parents[1] / "kb" / "smac_micro.txt"
_KB_PREFIX = KB_PATH.read_text() if KB_PATH.is_file() else ""
TACTIC_CRITERIA = {
    "focus": "Allies and enemies are the same ranged unit (marines vs marines, including 5v6). Everyone shoots ONE target. NOT for 2v1 spine. NOT for stalkers vs zealots.",
    "closest": "Mixed army with zealots AND stalkers on the same side. Shoot the nearest enemy. NOT for pure marines.",
    "alternate": "Exactly two ranged allies vs exactly one static/spine. Only one fires each volley. NOT for 3v3 marines.",
    "kite": "Allied stalkers vs enemy zealots (melee). Shoot then walk away. NOT for marine mirrors.",
}


def recommend_tactic(snap) -> str:
    allies = [a["type"] for a in living(snap["allies"])]
    enemies = [e["type"] for e in living(snap["enemies"])]
    a, e = set(allies), set(enemies)
    if not allies or not enemies:
        return "focus"
    # 2v1 is alternating fire ONLY vs a static/spine, not a leftover marine.
    if len(allies) == 2 and len(enemies) == 1 and e <= {"spi", "cra", "sp"}:
        return "alternate"
    if a <= {"sta"} and e <= {"zea"}:
        return "kite"
    if ("sta" in a and "zea" in a) or ("sta" in e and "zea" in e):
        return "closest"
    return "focus"


def situation_line(snap) -> str:
    allies = living(snap["allies"])
    enemies = living(snap["enemies"])
    at = ",".join(a["type"] for a in allies) or "none"
    et = ",".join(e["type"] for e in enemies) or "none"
    rec = recommend_tactic(snap)
    return (
        f"Situation: {len(allies)} allies [{at}] vs {len(enemies)} enemies [{et}]. "
        f"KB recommends tactic={rec}."
    )


def with_kb(snap, body: str) -> str:
    # Laya truncates the *tail* of state. Keep the battlefield first; tactics live in questions.
    return situation_line(snap) + "\n" + body


def labels_from_avail(avail_row: Sequence[int], n_enemies: int) -> List[Tuple[int, str]]:
    out = []
    for a, ok in enumerate(avail_row):
        if not ok:
            continue
        if a in ACTION_NAMES:
            out.append((a, ACTION_NAMES[a]))
        else:
            out.append((a, f"atkE{a - 6}"))
    return out


def living(units):
    return [u for u in units if u.get("alive")]


def hypot(a, b):
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def move_toward_action(ally, target, labels: List[Tuple[int, str]]) -> int:
    moves = [(a, lab) for a, lab in labels if lab in MOVE_DELTA]
    if not moves:
        for a, lab in labels:
            if lab != "noop":
                return a
        return labels[0][0]
    best_a, best = moves[0][0], -1e9
    for a, lab in moves:
        dx, dy = MOVE_DELTA[lab]
        nxt = math.hypot(ally["x"] + dx - target["x"], ally["y"] + dy - target["y"])
        score = hypot(ally, target) - nxt
        if score > best:
            best, best_a = score, a
    return best_a


def move_away_action(ally, target, labels: List[Tuple[int, str]]) -> int:
    moves = [(a, lab) for a, lab in labels if lab in MOVE_DELTA]
    if not moves:
        return next((a for a, lab in labels if lab == "stop"), labels[0][0])
    best_a, best = moves[0][0], -1e9
    for a, lab in moves:
        dx, dy = MOVE_DELTA[lab]
        nxt = math.hypot(ally["x"] + dx - target["x"], ally["y"] + dy - target["y"])
        score = nxt - hypot(ally, target)
        if score > best:
            best, best_a = score, a
    return best_a


def attack_action(labels: List[Tuple[int, str]], enemy_id: int) -> Optional[int]:
    want = f"atkE{enemy_id}"
    for a, lab in labels:
        if lab == want:
            return a
    return None


def in_range_ids(labels: List[Tuple[int, str]]) -> List[int]:
    ids = []
    for _, lab in labels:
        if lab.startswith("atkE"):
            ids.append(int(lab[4:]))
    return ids



def last_action_name(snap, agent_id: int) -> str:
    ids = snap.get("last_action_ids") or []
    if agent_id >= len(ids) or ids[agent_id] < 0:
        return "none"
    a = ids[agent_id]
    if a in ACTION_NAMES:
        return ACTION_NAMES[a]
    if a >= 6:
        return f"atkE{a-6}"
    return str(a)


def describe_enemy(e, allies, snap) -> str:
    """Commander option text uses SMAC state features: hp ratio, relative-to-center, who can shoot."""
    cx, cy = snap.get("center", (16.0, 16.0))
    w = max(1.0, snap.get("width", 32.0))
    h = max(1.0, snap.get("height", 32.0))
    shoot = snap.get("shoot", 6.0)
    hp = e["hp"] / max(1e-6, e["max_hp"])
    sh = e.get("shield", 0) / max(1e-6, e.get("max_hp", 1))
    dx, dy = (e["x"] - cx) / w, (e["y"] - cy) / h
    n_in = 0
    nearest = 99.0
    for a in living(allies):
        d = hypot(a, e)
        nearest = min(nearest, d)
        if d <= shoot + a.get("range", 5) * 0.0 + 1.2:
            # in shooting range if attack action would be available; use 6+radius slack
            if d <= shoot + 1.2:
                n_in += 1
    return (
        f"{e['type']} hp_ratio={hp:.2f} shield_ratio={sh:.2f} "
        f"dx={dx:+.2f} dy={dy:+.2f} nearest={nearest/9.0:.2f}sight "
        f"{n_in} allies already in shooting range. "
        + ("BEST FOCUS: weakest and already shootable." if n_in and hp < 0.7 else
           "Shootable now." if n_in else "Must walk closer before firing.")
    )


def compact_state(map_name: str, step: int, snap: Dict[str, Any], agent_id: Optional[int] = None, *, prefix: bool = True) -> str:
    """Text analogue of SMAC observations.

    Paper tricks baked in:
    - local obs only sees units inside sight=9; far and dead look the same (omitted)
    - relative x/y and distance, all divided by sight or map size
    - hp/shield/cooldown normalised to [0,1]
    - last actions of visible allies
    - own can-move bits
    - attackable (in shooting range 6) marked separately from merely visible
    - in-range enemies first, because Laya truncates the *tail* of the state
    """
    sight = float(snap.get("sight", 9.0))
    shoot = float(snap.get("shoot", 6.0))
    cx, cy = snap.get("center", (16.0, 16.0))
    w = max(1.0, float(snap.get("width", 32.0)))
    h = max(1.0, float(snap.get("height", 32.0)))
    allies = living(snap["allies"])
    enemies = living(snap["enemies"])

    def hp_r(u):
        return u["hp"] / max(1e-6, u["max_hp"])

    def sh_r(u):
        mx = u.get("max_shield") or 0
        return (u.get("shield") or 0) / mx if mx else 0.0

    if agent_id is None:
        # Commander view: pairwise geometry, not critic-style centre offsets.
        limit = snap.get("limit") or 0
        bits = [
            f"Commander state map={map_name} t={step}/{limit}. Sight {sight:.0f}. "
            f"U*=ally T*=enemy id. T* legal iff Can-shoot (center d<=6). "
            f"T* while READY fires then stands. T* while COOLING stands and deals 0. "
            f"Walks are real moves; HOLD deals 0."
        ]
        ap = snap.get("attack_point")
        if ap:
            bits.append(f"Enemy attack-move toward ({float(ap[0]):.0f},{float(ap[1]):.0f}).")
        if snap.get("terrain_ascii"):
            bits.append("Terrain #=wall A=ally E=enemy (x right, y up):\n" + snap["terrain_ascii"])
        a_lines = []
        for a in allies:
            last = last_action_name(snap, a["id"])
            sh = f" sh={a.get('shield',0):.0f}/{a.get('max_shield',0):.0f}" if a.get("max_shield", 0) else ""
            a_lines.append(
                f"U{a['id']} {a.get('name', a['type'])} {a.get('role','?')} "
                f"dmg={a.get('dmg',0):.0f} rng={a.get('range',0):.1f} spd={a.get('speed',0):.2f} "
                f"hp={a['hp']:.0f}/{a['max_hp']:.0f}{sh} cd={a['cd']:.2f}/{a.get('max_cd',0):.2f} "
                f"pos=({a['x']:.1f},{a['y']:.1f}) last={last}"
                + (" HIT" if a.get("hit") else "")
            )
        e_lines = []
        for e in enemies:
            sh = f" sh={e.get('shield',0):.0f}/{e.get('max_shield',0):.0f}" if e.get("max_shield", 0) else ""
            imm = " immobile" if e.get("role") == "static" else ""
            e_lines.append(
                f"E{e['id']}/T{e['id']} {e.get('name', e['type'])} {e.get('role','?')}{imm} "
                f"hp={e['hp']:.0f}/{e['max_hp']:.0f}{sh} pos=({e['x']:.1f},{e['y']:.1f})"
                + (" attacking" if e.get("hit") else "")
            )
        bits.append("Allies: " + " | ".join(a_lines) if a_lines else "Allies: none")
        bits.append("Enemies: " + " | ".join(e_lines) if e_lines else "Enemies: none")
        # Pairwise: who is close, who can fire. Avail mask is SMAC ground truth (shoot=6).
        pair_lines = []
        can_map = {}
        for a in allies:
            i = a["id"]
            avail = snap["avail"][i] if i < len(snap["avail"]) else []
            shots = []
            parts = []
            for e in enemies:
                d = hypot(a, e)
                can = (6 + e["id"]) < len(avail) and bool(avail[6 + e["id"]])
                if can:
                    ready = float(a.get("cd") or 0) <= 0.08
                    tag = "FIRE" if ready else "WAIT-CD"
                    shots.append(f"T{e['id']}:{tag}")
                elif e.get("role") == "melee" and d <= 2.0:
                    tag = "MELEE"
                else:
                    tag = ""
                parts.append(f"T{e['id']} d={d:.1f}{(' '+tag) if tag else ''}")
            can_map[i] = shots
            pair_lines.append(f"U{i}-> " + ", ".join(parts))
        bits.append("Ranges: " + " ; ".join(pair_lines) if pair_lines else "Ranges: none")
        bits.append(
            "Can-shoot: "
            + " ".join(f"U{i}:[{','.join(v) or 'none'}]" for i, v in can_map.items())
        )
        ready_u = [f"U{a['id']}" for a in allies if float(a.get("cd") or 0) <= 0.08]
        cool_u = [f"U{a['id']}(cd={a['cd']:.2f})" for a in allies if float(a.get("cd") or 0) > 0.08]
        bits.append("Ready: " + (",".join(ready_u) or "none") + " Cooling: " + (",".join(cool_u) or "none"))
        text = "\n".join(bits)
        return with_kb(snap, text) if prefix else text

    me = next((a for a in snap["allies"] if a["id"] == agent_id), None)
    if not me or not me["alive"]:
        return f"You are dead. Only no-op is legal."
    avail = snap["avail"][agent_id]
    can = []
    for d, idx in (("N", 2), ("S", 3), ("E", 4), ("W", 5)):
        if agent_id < len(avail) and idx < len(avail) and avail[idx]:
            can.append(d)
    bits = [
        f"SMAC local obs map={map_name} t={step}. Sight {sight:.0f}, shoot {shoot:.0f}. Far/dead omitted (indistinguishable). Allies spawn west, enemies east.",
        (
            f"You A{me['id']} {me['type']} hp={hp_r(me):.2f} sh={sh_r(me):.2f} "
            f"cd={min(me['cd']/max(1e-6, me.get('max_cd') or 0.86),1.0):.2f} can_move={','.join(can) or 'none'} "
            f"last={last_action_name(snap, me['id'])}."
        ),
    ]
    vis_e_shot, vis_e_seen, vis_a = [], [], []
    for e in enemies:
        d = hypot(me, e)
        if d > sight:
            continue
        dx = (e["x"] - me["x"]) / sight
        dy = (e["y"] - me["y"]) / sight
        rec = (
            f"E{e['id']} {e['type']} hp={hp_r(e):.2f} sh={sh_r(e):.2f} "
            f"d={d/sight:.2f} dx={dx:+.2f} dy={dy:+.2f}"
        )
        if d <= shoot + 1.2:
            vis_e_shot.append(rec + " IN_SHOT")
        else:
            vis_e_seen.append(rec + " seen_only")
    for a in allies:
        if a["id"] == me["id"]:
            continue
        d = hypot(me, a)
        if d > sight:
            continue
        dx = (a["x"] - me["x"]) / sight
        dy = (a["y"] - me["y"]) / sight
        vis_a.append(
            f"A{a['id']} {a['type']} hp={hp_r(a):.2f} d={d/sight:.2f} dx={dx:+.2f} dy={dy:+.2f} "
            f"last={last_action_name(snap, a['id'])}"
        )
    # In-shot enemies first: Laya keeps the prefix of state when over budget.
    bits.append("Shootable: " + "; ".join(vis_e_shot) if vis_e_shot else "Shootable: none")
    bits.append("Seen enemies: " + "; ".join(vis_e_seen) if vis_e_seen else "Seen enemies: none")
    bits.append("Visible allies: " + "; ".join(vis_a) if vis_a else "Visible allies: none")
    text = "\n".join(bits)
    return with_kb(snap, text) if prefix else text


def execute_focus(snap: Dict[str, Any], focus_id: int, *, kite: bool = False) -> List[int]:
    """Paper micro: attack[focus] if in shooting range, else move toward it. Optional kite on cooldown."""
    enemies = {e["id"]: e for e in living(snap["enemies"])}
    focus = enemies.get(focus_id) or (next(iter(enemies.values())) if enemies else None)
    actions = []
    for i, ally in enumerate(snap["allies"]):
        labels = labels_from_avail(snap["avail"][i], snap["n_enemies"])
        if not ally["alive"]:
            actions.append(0)
            continue
        if focus is None:
            actions.append(next((a for a, lab in labels if lab == "stop"), labels[0][0]))
            continue
        shot = attack_action(labels, focus["id"])
        if shot is not None and not (kite and ally["cd"] > 0.05):
            actions.append(shot)
            continue
        if kite and ally["cd"] > 0.05:
            actions.append(move_away_action(ally, focus, labels))
        else:
            actions.append(move_toward_action(ally, focus, labels))
    return actions


def execute_alternating(snap: Dict[str, Any], target_id: Optional[int] = None) -> List[int]:
    """Approach until someone can shoot; then only one fires, the other walks out."""
    enemies = living(snap["enemies"])
    target = next((e for e in enemies if e["id"] == target_id), None) if target_id is not None else None
    if target is None:
        target = enemies[0] if enemies else None
    actions = []
    can_shoot = []
    for a in living(snap["allies"]):
        labels = labels_from_avail(snap["avail"][a["id"]], snap["n_enemies"])
        if target is not None and attack_action(labels, target["id"]) is not None and a["cd"] <= 0.05:
            can_shoot.append(a)
    shooter = max(can_shoot, key=lambda a: a["hp"]) if can_shoot else None
    for i, ally in enumerate(snap["allies"]):
        labels = labels_from_avail(snap["avail"][i], snap["n_enemies"])
        if not ally["alive"]:
            actions.append(0)
            continue
        if target is None:
            actions.append(next((a for a, lab in labels if lab == "stop"), labels[0][0]))
            continue
        if shooter is None:
            actions.append(move_toward_action(ally, target, labels))
            continue
        if ally["id"] == shooter["id"]:
            shot = attack_action(labels, target["id"])
            actions.append(shot if shot is not None else move_toward_action(ally, target, labels))
        else:
            shot = attack_action(labels, target["id"])
            actions.append(move_away_action(ally, target, labels) if shot is not None else move_toward_action(ally, target, labels))
    return actions



def execute_scripted(snap: Dict[str, Any], mode: str = "focus") -> List[int]:
    """Same rule as eval_smac.heuristic_act: proven 100% on 3m / 2s3z closest."""
    actions = []
    enemies = living(snap["enemies"])
    for i, ally in enumerate(snap["allies"]):
        labels = labels_from_avail(snap["avail"][i], snap["n_enemies"])
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
            if mode == "focus":
                target = min(attackable, key=lambda e: (e["hp"] + e.get("shield", 0), e["id"]))
            else:
                target = min(attackable, key=lambda e: hypot(ally, e))
            shot = attack_action(labels, target["id"])
            actions.append(shot if shot is not None else labels[0][0])
            continue
        target = min(enemies, key=lambda e: hypot(ally, e))
        actions.append(move_toward_action(ally, target, labels))
    return actions


def _guns_on(snap: Dict[str, Any], enemy_id: int) -> int:
    n = 0
    for a in living(snap["allies"]):
        labels = labels_from_avail(snap["avail"][a["id"]], snap["n_enemies"])
        if attack_action(labels, enemy_id) is not None:
            n += 1
    return n


def pick_default_target(snap: Dict[str, Any], preferred: Optional[int] = None) -> Optional[int]:
    """Sticky focus: keep the current target if it still has guns; else most guns, then lowest HP."""
    enemies = living(snap["enemies"])
    if not enemies:
        return None
    ids = {e["id"] for e in enemies}

    def score(e):
        return (-_guns_on(snap, e["id"]), e["hp"] + e.get("shield", 0), e["id"])

    best = min(enemies, key=score)["id"]
    if preferred in ids:
        if _guns_on(snap, preferred) + 1 >= _guns_on(snap, best):
            return preferred
    return best


def heal_or_follow(ally: Dict[str, Any], labels: List[Tuple[int, str]], snap: Dict[str, Any]) -> int:
    living_a = living(snap["allies"])
    needy = [a for a in living_a if a["id"] != ally["id"] and a["hp"] < a["max_hp"] - 5]
    if not needy:
        others = [a for a in living_a if a["id"] != ally["id"]]
        if not others:
            return next((a for a, lab in labels if lab == "stop"), labels[0][0])
        tgt = min(others, key=lambda a: a["hp"] / max(a["max_hp"], 1))
        return move_toward_action(ally, tgt, labels)
    tgt = min(needy, key=lambda a: a["hp"] / max(a["max_hp"], 1))
    for a, _lab in labels:
        if a == 6 + tgt["id"]:
            return a
    return move_toward_action(ally, tgt, labels)


def _apply_healers(snap: Dict[str, Any], actions: List[int]) -> List[int]:
    out = list(actions)
    for i, ally in enumerate(snap["allies"]):
        if not ally.get("alive") or ally.get("role") != "heal":
            continue
        labels = labels_from_avail(snap["avail"][i], snap["n_enemies"])
        out[i] = heal_or_follow(ally, labels, snap)
    return out


def execute_ball(snap: Dict[str, Any], focus_id: int) -> List[int]:
    """Hold fire until most of the army can shoot the focus, then attack-move it."""
    allies = living(snap["allies"])
    n_alive = max(1, len(allies))
    can_ids = set()
    for a in allies:
        labels = labels_from_avail(snap["avail"][a["id"]], snap["n_enemies"])
        if attack_action(labels, focus_id) is not None:
            can_ids.add(a["id"])
    n_can = len(can_ids)
    commit = n_alive <= 2 or n_can >= max(2, int(0.6 * n_alive + 0.999))
    if commit:
        return execute_focus(snap, focus_id)
    enemies = living(snap["enemies"])
    focus = next((e for e in enemies if e["id"] == focus_id), None)
    actions: List[int] = []
    for i, ally in enumerate(snap["allies"]):
        labels = labels_from_avail(snap["avail"][i], snap["n_enemies"])
        if not ally.get("alive"):
            actions.append(0)
            continue
        if ally["id"] in can_ids:
            actions.append(next((a for a, lab in labels if lab == "stop"), labels[0][0]))
        elif focus is not None:
            actions.append(move_toward_action(ally, focus, labels))
        else:
            actions.append(next((a for a, lab in labels if lab == "stop"), labels[0][0]))
    return actions


def execute_mixed(snap: Dict[str, Any], focus_id: int) -> List[int]:
    """Melee tanks nearest; ranged attack-moves the shared focus."""
    enemies = living(snap["enemies"])
    focus = next((e for e in enemies if e["id"] == focus_id), None)
    actions: List[int] = []
    for i, ally in enumerate(snap["allies"]):
        labels = labels_from_avail(snap["avail"][i], snap["n_enemies"])
        if not ally.get("alive"):
            actions.append(0)
            continue
        if ally.get("role") == "melee":
            nearest = min(enemies, key=lambda e: hypot(ally, e)) if enemies else None
            if nearest is None:
                actions.append(next((a for a, lab in labels if lab == "stop"), labels[0][0]))
                continue
            shot = attack_action(labels, nearest["id"])
            actions.append(shot if shot is not None else move_toward_action(ally, nearest, labels))
            continue
        if focus is None:
            actions.append(next((a for a, lab in labels if lab == "stop"), labels[0][0]))
            continue
        shot = attack_action(labels, focus["id"])
        actions.append(shot if shot is not None else move_toward_action(ally, focus, labels))
    return actions


def execute_squad(snap: Dict[str, Any], cmd: str, target_id: Optional[int]) -> List[int]:
    """Turn one army order into SMAC discrete actions. This is the micro layer."""
    cmd = (cmd or "FOCUS").upper()
    tgt = pick_default_target(snap, target_id)
    if tgt is None:
        return [0 if not a.get("alive") else 1 for a in snap["allies"]]
    allies = living(snap["allies"])
    melee_a = any(a.get("role") == "melee" for a in allies)
    if cmd == "NEAREST":
        actions = execute_scripted(snap, "closest")
    elif cmd == "KITE":
        actions = execute_focus(snap, tgt, kite=True)
    elif cmd in ("BAIT", "ALTERNATE"):
        actions = execute_alternating(snap, tgt)
    elif cmd == "BALL":
        actions = execute_ball(snap, tgt)
    elif melee_a:
        actions = execute_mixed(snap, tgt)
    else:
        actions = execute_focus(snap, tgt)
    return _apply_healers(snap, actions)


def execute_cloze(snap: Dict[str, Any], form: Dict[str, str], target_id: Optional[int]) -> List[int]:
    """Compile a filled cloze form into SMAC discrete actions.

    not_firing=back means kite: close until in range, then shoot when ready and walk
    away on cooldown. who_fires=one means a tank approaches; partners stay out.
    """
    who = (form.get("who_fires") or "all").lower()
    tgt_mode = (form.get("target") or "shared").lower()
    idle = (form.get("not_firing") or "close").lower()
    enemies = living(snap["enemies"])
    allies = living(snap["allies"])
    focus_id = pick_default_target(snap, target_id)
    focus = next((e for e in enemies if e["id"] == focus_id), None) if focus_id is not None else None

    def labels_of(ally):
        return labels_from_avail(snap["avail"][ally["id"]], snap["n_enemies"])

    def shot_for(ally):
        labels = labels_of(ally)
        if tgt_mode == "nearest" or ally.get("role") == "melee":
            attackable = []
            for a, lab in labels:
                if lab.startswith("atkE"):
                    eid = int(lab[4:])
                    e = next((x for x in enemies if x["id"] == eid), None)
                    if e:
                        attackable.append(e)
            if not attackable:
                return None
            e = min(attackable, key=lambda x: hypot(ally, x))
            return attack_action(labels, e["id"])
        if focus is None:
            return None
        return attack_action(labels, focus["id"])

    def walk_to(ally, dest):
        labels = labels_of(ally)
        if dest is None:
            return next((a for a, lab in labels if lab == "stop"), labels[0][0])
        return move_toward_action(ally, dest, labels)

    def walk_away(ally, dest):
        labels = labels_of(ally)
        if dest is None:
            return next((a for a, lab in labels if lab == "stop"), labels[0][0])
        return move_away_action(ally, dest, labels)

    def stand(ally):
        labels = labels_of(ally)
        return next((a for a, lab in labels if lab == "stop"), labels[0][0])

    def threat_of(ally):
        return min(enemies, key=lambda e: hypot(ally, e)) if enemies else None

    n_alive = max(1, len(allies))
    can = [a for a in allies if shot_for(a) is not None]
    who_eff = who
    if who == "wait":
        commit = n_alive <= 2 or len(can) >= max(2, int(0.6 * n_alive + 0.999))
        who_eff = "all" if commit else "none"

    tank_id = None
    if who == "one":
        ready_can = [a for a in can if float(a.get("cd") or 0) <= 0.08]
        if ready_can:
            tank_id = max(ready_can, key=lambda a: a["hp"] + a.get("shield", 0))["id"]
        elif focus is not None and allies:
            tank_id = min(allies, key=lambda a: hypot(a, focus))["id"]
        elif allies:
            tank_id = max(allies, key=lambda a: a["hp"] + a.get("shield", 0))["id"]

    actions: List[int] = []
    for i, ally in enumerate(snap["allies"]):
        if not ally.get("alive"):
            actions.append(0)
            continue
        shot = shot_for(ally)
        ready = float(ally.get("cd") or 0) <= 0.08
        threat = threat_of(ally)
        dest = focus or threat

        if who == "one" and tank_id is not None and ally["id"] != tank_id:
            # Partner stays out: leave range if already in, otherwise hold.
            actions.append(walk_away(ally, dest) if shot is not None else stand(ally))
            continue

        allowed = False
        if who_eff == "all" and shot is not None:
            allowed = True
        elif who == "one" and ally["id"] == tank_id and shot is not None:
            allowed = True

        if allowed and ready:
            if idle == "back" and threat is not None and hypot(ally, threat) < 4.8:
                actions.append(walk_away(ally, threat))
            else:
                actions.append(shot)
        elif allowed and idle == "back":
            actions.append(walk_away(ally, threat or dest))
        elif allowed:
            actions.append(shot)  # T* on cooldown stands
        elif idle == "back" and shot is None:
            actions.append(walk_to(ally, dest))  # close first, then kite
        elif idle == "back":
            actions.append(walk_away(ally, threat or dest))
        elif idle == "stand":
            actions.append(stand(ally))
        else:
            actions.append(walk_to(ally, dest))
    return _apply_healers(snap, actions)



def pick_plan_target(snap: Dict[str, Any], rule: str, preferred: Optional[int] = None) -> Optional[int]:
    enemies = living(snap["enemies"])
    if not enemies:
        return None
    rule = (rule or "guns_hp").lower()
    if rule == "building":
        static = [e for e in enemies if e.get("role") == "static"]
        if static:
            return min(static, key=lambda e: (e["hp"] + e.get("shield", 0), e["id"]))["id"]
    if rule == "melee":
        melee = [e for e in enemies if e.get("role") == "melee"]
        if melee:
            allies = living(snap["allies"])
            origin = allies[0] if allies else melee[0]
            return min(melee, key=lambda e: hypot(origin, e))["id"]
    return pick_default_target(snap, preferred)


def infer_seen(snap: Dict[str, Any]) -> str:
    allies = living(snap["allies"])
    enemies = living(snap["enemies"])
    nA, nE = len(allies), len(enemies)
    static_e = sum(1 for e in enemies if e.get("role") == "static")
    melee_e = sum(1 for e in enemies if e.get("role") == "melee")
    melee_a = sum(1 for a in allies if a.get("role") == "melee")
    ranged_a = sum(1 for a in allies if a.get("role") == "ranged")
    if static_e >= 1 and nE <= max(2, static_e):
        return "building"
    if ranged_a == nA and nA > 0 and melee_e > 0 and melee_a == 0:
        return "kite"
    if melee_a > 0 and melee_e > 0:
        return "mixed"
    if nA < nE and static_e == 0 and melee_e == 0:
        return "outnumbered"
    return "trade"




def execute_bait(snap: Dict[str, Any], target_id: Optional[int]) -> List[int]:
    """Tank walks in only when ready, fires, then leaves spine range on cooldown."""
    enemies = living(snap["enemies"])
    allies = living(snap["allies"])
    focus_id = pick_plan_target(snap, "building", target_id)
    focus = next((e for e in enemies if e["id"] == focus_id), None) if focus_id is not None else (enemies[0] if enemies else None)
    if focus is None or not allies:
        return [0 if not a.get("alive") else 1 for a in snap["allies"]]
    safe = 8.6

    def labels_of(ally):
        return labels_from_avail(snap["avail"][ally["id"]], snap["n_enemies"])

    def shot_of(ally):
        return attack_action(labels_of(ally), focus["id"])

    ready_in = [a for a in allies if shot_of(a) is not None and float(a.get("cd") or 0) <= 0.08]
    if ready_in:
        tank_id = max(ready_in, key=lambda a: a["hp"] + a.get("shield", 0))["id"]
    else:
        tank_id = min(allies, key=lambda a: hypot(a, focus))["id"]

    actions: List[int] = []
    for ally in snap["allies"]:
        if not ally.get("alive"):
            actions.append(0)
            continue
        labels = labels_of(ally)
        d = hypot(ally, focus)
        shot = shot_of(ally)
        ready = float(ally.get("cd") or 0) <= 0.08
        if ally["id"] != tank_id:
            actions.append(move_away_action(ally, focus, labels) if d < safe else next((a for a, lab in labels if lab == "stop"), labels[0][0]))
            continue
        if ready and shot is not None:
            actions.append(shot)
        elif ready:
            actions.append(move_toward_action(ally, focus, labels))
        elif d < safe:
            actions.append(move_away_action(ally, focus, labels))
        else:
            actions.append(next((a for a, lab in labels if lab == "stop"), labels[0][0]))
    return _apply_healers(snap, actions)


def _group_away_lab(allies, threat) -> str:
    best_lab, best = "N", -1e9
    for lab, (dx, dy) in MOVE_DELTA.items():
        score = 0.0
        for a in allies:
            nx, ny = a["x"] + dx, a["y"] + dy
            score += ((nx - threat["x"]) ** 2 + (ny - threat["y"]) ** 2) ** 0.5
        if score > best:
            best, best_lab = score, lab
    return best_lab



def execute_kite(snap: Dict[str, Any], target_id: Optional[int]) -> List[int]:
    """Blob stutter-step. Never walk toward melee while anyone is in the danger band."""
    enemies = living(snap["enemies"])
    allies = living(snap["allies"])
    melee = [e for e in enemies if e.get("role") == "melee"] or enemies
    if not allies or not melee:
        return execute_cloze(snap, {"who_fires": "all", "target": "shared", "not_firing": "back"}, target_id)
    cx = sum(a["x"] for a in allies) / len(allies)
    cy = sum(a["y"] for a in allies) / len(allies)
    threat = min(melee, key=lambda e: (e["x"] - cx) ** 2 + (e["y"] - cy) ** 2)
    focus_id = pick_plan_target(snap, "melee", target_id)
    focus = next((e for e in enemies if e["id"] == focus_id), None) or threat
    away_lab = _group_away_lab(allies, threat)
    min_d = min(hypot(a, threat) for a in allies)
    CLOSE = 7.0
    DANGER = 5.0

    def labels_of(ally):
        return labels_from_avail(snap["avail"][ally["id"]], snap["n_enemies"])

    def dir_action(ally, lab):
        labels = labels_of(ally)
        for a, name in labels:
            if name == lab:
                return a
        return move_away_action(ally, threat, labels)

    actions: List[int] = []
    for ally in snap["allies"]:
        if not ally.get("alive"):
            actions.append(0)
            continue
        labels = labels_of(ally)
        d = hypot(ally, threat)
        ready = float(ally.get("cd") or 0) <= 0.08
        shot = attack_action(labels, focus["id"])
        if shot is None:
            for e in melee:
                s = attack_action(labels, e["id"])
                if s is not None:
                    shot = s
                    break
        if min_d < DANGER:
            actions.append(dir_action(ally, away_lab))
        elif min_d > CLOSE:
            actions.append(move_toward_action(ally, focus, labels))
        elif ready and shot is not None:
            actions.append(shot)
        else:
            actions.append(dir_action(ally, away_lab))
    return _apply_healers(snap, actions)


def execute_plan(snap: Dict[str, Any], plan: Dict[str, str], target_id: Optional[int], *, trust_plan: bool = False) -> List[int]:
    """If trust_plan, follow the planner JSON; else lock stance from unit counts."""
    kill = (plan.get("kill") or "guns_hp").lower()
    if trust_plan:
        seen = (plan.get("seen") or "").lower()
        fight = (plan.get("fight") or "trade").lower()
        tank = (plan.get("tank") or "all").lower()
        commit = (plan.get("commit") or "now").lower()
        where = (plan.get("where") or "push").lower()
        stance = seen or fight
        if stance in ("building", "bait") or tank == "one" or fight == "bait":
            who = "one"
            if stance in ("building", "bait"):
                kill = "building"
        elif stance in ("outnumbered",) or commit == "group" or fight == "outnumbered":
            who = "wait"
        else:
            who = "all"
        tgt_mode = "nearest" if kill == "nearest" else "shared"
        if stance in ("kite",) or tank == "none" or where == "kite" or fight == "kite" or commit == "safe":
            idle = "back"
            if kill == "guns_hp":
                kill = "melee"
        elif where == "hold":
            idle = "stand"
        else:
            idle = "close"
    else:
        stance = infer_seen(snap)
        if stance == "building":
            who, idle, kill = "one", "close", "building"
        elif stance == "kite":
            who, idle = "all", "back"
            if kill == "guns_hp":
                kill = "melee"
        elif stance == "outnumbered":
            who, idle = "wait", "close"
        else:
            who, idle = "all", "close"
        tgt_mode = "nearest" if kill == "nearest" else "shared"
    focus = pick_plan_target(snap, kill, target_id)
    stance_now = (plan.get("seen") or plan.get("fight") or "").lower() if trust_plan else infer_seen(snap)
    if stance_now in ("building", "bait") or (trust_plan and (plan.get("tank") or "").lower() == "one"):
        return execute_bait(snap, focus)
    if stance_now in ("kite",) or (trust_plan and ((plan.get("where") or "").lower() == "kite" or (plan.get("fight") or "").lower() == "kite")):
        return execute_kite(snap, focus)
    return execute_cloze(
        snap,
        {"who_fires": who, "target": tgt_mode, "not_firing": idle},
        focus,
    )


class ScriptedSquadPolicy:

    """No-LLM control: always execute one squad command with sticky auto-focus."""

    def __init__(self, cmd: str = "FOCUS"):
        self.cmd = cmd.upper()
        self._focus: Optional[int] = None
        self.n_calls = 0
        self.n_fallback = 0
        self.n_guard = 0
        self.infer_s = 0.0
        self.tactic_counts: Dict[str, int] = {}

    def act(self, map_name: str, step: int, snap: Dict[str, Any]) -> List[int]:
        self.n_calls += 1
        if step == 0:
            self._focus = None
        self._focus = pick_default_target(snap, self._focus)
        self.tactic_counts[self.cmd] = self.tactic_counts.get(self.cmd, 0) + 1
        return execute_squad(snap, self.cmd, self._focus)


class LayaPolicy:
    def __init__(self, model_dir, style: str = "commander"):
        import laya_mlx as laya

        self.agent = laya.load(str(model_dir))
        self.style = style
        self.n_calls = 0
        self.n_fallback = 0
        self.n_guard = 0
        self.infer_s = 0.0
        self._sticky_focus = None

    def act(self, map_name: str, step: int, snap: Dict[str, Any]) -> List[int]:
        if self.style == "commander":
            return self._commander(map_name, step, snap)
        if self.style == "unit":
            return self._unit(map_name, step, snap)
        raise ValueError(self.style)

    def _predict(self, state: str, questions: dict) -> dict:
        t0 = time.perf_counter()
        try:
            result = self.agent.predict(state, questions)
        except Exception:
            self.n_fallback += 1
            self.infer_s += time.perf_counter() - t0
            self.n_calls += 1
            return {}
        self.infer_s += time.perf_counter() - t0
        self.n_calls += 1
        answers = result.get("answers") if isinstance(result, dict) else None
        return answers if isinstance(answers, dict) else {}

    @staticmethod
    def _choice(payload) -> Optional[str]:
        if isinstance(payload, str):
            return payload
        if isinstance(payload, dict):
            val = payload.get("choice")
            if isinstance(val, str):
                return val
        return None

    @staticmethod
    def _probs(payload) -> Dict[str, float]:
        if isinstance(payload, dict) and isinstance(payload.get("probabilities"), dict):
            return {str(k): float(v) for k, v in payload["probabilities"].items()}
        return {}

    def _commander(self, map_name, step, snap) -> List[int]:
        enemies = living(snap["enemies"])
        if not enemies:
            return execute_focus(snap, 0)
        if not hasattr(self, "tactic_counts"):
            self.tactic_counts = {}
        if step == 0:
            self._sticky_focus = None
        state = compact_state(map_name, step, snap)
        questions = {
            "tactic": {
                "type": "choice",
                "instructions": (
                    "Pick one tactic from the knowledge base. "
                    "Marines vs marines (even 5v6): focus. "
                    "Stalkers plus zealots: closest. "
                    "Two stalkers vs one spine/static: alternate. "
                    "Stalkers vs zealots: kite."
                ),
                "criteria": dict(TACTIC_CRITERIA),
            },
        }
        answers = self._predict(state, questions)
        tactic = self._choice(answers.get("tactic"))
        if tactic not in TACTIC_CRITERIA:
            probs = self._probs(answers.get("tactic"))
            tactic = max(TACTIC_CRITERIA, key=lambda k: probs.get(k, -1.0)) if probs else "focus"
            if tactic not in TACTIC_CRITERIA:
                tactic = "focus"
                self.n_fallback += 1
        self.tactic_counts["raw_" + (tactic if tactic else "none")] = (
            self.tactic_counts.get("raw_" + (tactic if tactic else "none"), 0) + 1
        )
        if tactic not in TACTIC_CRITERIA:
            tactic = "focus"
            self.n_fallback += 1
        self.tactic_counts[tactic] = self.tactic_counts.get(tactic, 0) + 1
        ids = {e["id"] for e in enemies}
        me = living(snap["allies"])
        origin = me[0] if me else None

        def nearest_id():
            return min(enemies, key=lambda e: hypot(origin, e) if origin else e["id"])["id"]

        def weakest_in_shot_id():
            in_shot = []
            for e in enemies:
                for a in me:
                    i = a["id"]
                    labels = labels_from_avail(snap["avail"][i], snap["n_enemies"])
                    if attack_action(labels, e["id"]) is not None:
                        in_shot.append(e)
                        break
            pool = in_shot or enemies
            return min(pool, key=lambda e: (e["hp"] + e.get("shield", 0), e["id"]))["id"]

        if tactic == "alternate":
            return execute_alternating(snap)
        if tactic == "kite":
            return execute_focus(snap, nearest_id(), kite=True)
        if tactic == "closest":
            return execute_scripted(snap, "closest")
        return execute_scripted(snap, "focus")

    def _unit(self, map_name, step, snap) -> List[int]:
        """Per-agent SMAC discrete actions, but snake-style labeled criteria and shoot-range mask."""
        actions = []
        for ally in snap["allies"]:
            i = ally["id"]
            labels = labels_from_avail(snap["avail"][i], snap["n_enemies"])
            if not ally["alive"]:
                actions.append(0)  # paper: dead agents may only no-op
                continue
            legal = [(a, lab) for a, lab in labels if lab != "noop"]  # paper: living cannot no-op
            attacks = [(a, lab) for a, lab in legal if lab.startswith("atkE")]
            # Paper: attack[id] only in shooting range — already masked. If any shot exists,
            # drop wander/stop so Laya is not choosing among 10+ equally named moves.
            offered = attacks if attacks else [(a, lab) for a, lab in legal if lab in MOVE_DELTA or lab == "stop"]
            if not offered:
                offered = legal
            criteria = {}
            enemies = {e["id"]: e for e in living(snap["enemies"])}
            for a, lab in offered:
                if lab.startswith("atkE"):
                    e = enemies.get(int(lab[4:]))
                    if e:
                        criteria[lab] = (
                            f"Fire now on {e['type']} E{e['id']} (hp {e['hp']:.0f}, "
                            f"d={hypot(ally, e):.1f}). Legal shot."
                        )
                    else:
                        criteria[lab] = "Fire on that enemy."
                elif lab in MOVE_DELTA:
                    if enemies:
                        tgt = min(enemies.values(), key=lambda e: hypot(ally, e))
                        dx, dy = MOVE_DELTA[lab]
                        nxt = math.hypot(ally["x"] + dx - tgt["x"], ally["y"] + dy - tgt["y"])
                        closer = nxt < hypot(ally, tgt) - 0.05
                        criteria[lab] = (
                            f"Walk {lab}. {'CLOSER to' if closer else 'Farther from'} nearest enemy E{tgt['id']}."
                        )
                    else:
                        criteria[lab] = f"Walk {lab}."
                else:
                    criteria[lab] = "Hold position. Do this only if already in range next tick."
            questions = {
                "act": {
                    "type": "choice",
                    "instructions": (
                        "Pick this unit's SMAC action. If a shot is listed, shooting is legal and usually best. "
                        "Do not idle. Dead units are not you."
                    ),
                    "criteria": criteria,
                }
            }
            state = compact_state(map_name, step, snap, agent_id=i)
            answers = self._predict(state, questions)
            payload = answers.get("act")
            chosen = self._choice(payload)
            amap = {lab: a for a, lab in offered}
            if chosen in amap:
                actions.append(amap[chosen])
                continue
            # Snake-style guard: argmax over legal option probabilities.
            probs = self._probs(payload)
            if probs:
                best = max(amap, key=lambda lab: probs.get(lab, -1.0))
                if best in amap:
                    self.n_guard += 1
                    actions.append(amap[best])
                    continue
            self.n_fallback += 1
            if attacks:
                actions.append(attacks[0][0])
            else:
                tgt = min(living(snap["enemies"]), key=lambda e: hypot(ally, e), default=None)
                actions.append(move_toward_action(ally, tgt, labels) if tgt else legal[0][0])
        return actions
