"""Qwen typed System-1: ONE commander writes one JSON of all unit actions.

S1 is sequential constrained decoding (later units see earlier choices), not
independent per-unit classification. S2 is an API corrector on that joint draft.
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "local" / "qwen-rlcd"))
sys.path.insert(0, str(ROOT / "src"))

from smac_laya_policy import compact_state, living, hypot, execute_squad, execute_cloze, execute_plan, pick_default_target, pick_plan_target, _guns_on, labels_from_avail, attack_action, move_toward_action, move_away_action, _group_away_lab  # noqa: E402

KB = (ROOT / "kb" / "smac_micro.txt").read_text() if (ROOT / "kb" / "smac_micro.txt").is_file() else ""

LAB2ACT = {
    "HOLD": 1,
    "NORTH": 2,
    "SOUTH": 3,
    "EAST": 4,
    "WEST": 5,
}
WALK_LABS = ("NORTH", "SOUTH", "EAST", "WEST")
WALK_DELTA = {"NORTH": (0.0, 2.0), "SOUTH": (0.0, -2.0), "EAST": (2.0, 0.0), "WEST": (-2.0, 0.0)}
TACTIC_CHOICES = ["FOCUS", "CLOSEST", "ALTERNATE", "KITE"]
TACTIC_MAP = {c: c.lower() for c in TACTIC_CHOICES}

PHYSICS = (
    "You issue one action per living unit. "
    "HOLD stands. NORTH/SOUTH/EAST/WEST walk about 2. "
    "T* attacks that enemy if Can-shoot. "
    "FOCUS is the intended shared target; unit actions are chosen separately."
)


def _engine():
    from core.engine import get_engine, run_joint_generation
    from core.schema import StructuredSchema

    return get_engine, run_joint_generation, StructuredSchema


def _situation(snap) -> str:
    allies = living(snap["allies"])
    enemies = living(snap["enemies"])
    return (
        f"Situation: {len(allies)} allies ["
        + ",".join(a.get("name", a["type"])[:10] for a in allies)
        + f"] vs {len(enemies)} enemies ["
        + ",".join(e.get("name", e["type"])[:10] for e in enemies)
        + "]."
    )


def _context(map_name: str, step: int, snap, last_order: str = "", history: str = "") -> str:
    body = compact_state(map_name, step, snap, prefix=False)
    extra = f"\nLast order: {last_order}" if last_order else ""
    hist = ("\n" + history + "\n") if history else ""
    return (
        KB + "\n" + PHYSICS + "\nYou are ONE commander.\n" + _situation(snap) + extra
        + "\nMap: " + map_name + hist + "\nCURRENT:\n" + body
    )


def _nearest(ally, enemies):
    if not enemies:
        return None
    return min(enemies, key=lambda e: hypot(ally, e))


def _walk_tag(ally, enemies, lab: str) -> str:
    if not enemies:
        return "walk"
    tgt = _nearest(ally, enemies)
    dx, dy = WALK_DELTA[lab]
    cur = hypot(ally, tgt)
    nxt = ((ally["x"] + dx - tgt["x"]) ** 2 + (ally["y"] + dy - tgt["y"]) ** 2) ** 0.5
    if nxt + 0.15 < cur:
        return f"CLOSER to T{tgt['id']} {cur:.1f}->{nxt:.1f}"
    if nxt > cur + 0.15:
        return f"FARTHER from T{tgt['id']} {cur:.1f}->{nxt:.1f}"
    return f"SIDE vs T{tgt['id']}"


def legal_bundle(ally, snap) -> List[Tuple[int, str, str]]:
    """All living SMAC actions except noop. No shot-only / focus clamp."""
    enemies = living(snap["enemies"])
    avail_row = snap["avail"][ally["id"]]
    ready = float(ally.get("cd") or 0) <= 0.08
    out: List[Tuple[int, str, str]] = []
    for a, ok in enumerate(avail_row):
        if not ok:
            continue
        if a == 0:
            continue
        if a == 1:
            out.append((1, "HOLD", "STAND deal 0"))
        elif a == 2:
            out.append((2, "NORTH", _walk_tag(ally, enemies, "NORTH")))
        elif a == 3:
            out.append((3, "SOUTH", _walk_tag(ally, enemies, "SOUTH")))
        elif a == 4:
            out.append((4, "EAST", _walk_tag(ally, enemies, "EAST")))
        elif a == 5:
            out.append((5, "WEST", _walk_tag(ally, enemies, "WEST")))
        else:
            eid = a - 6
            e = next((x for x in enemies if x["id"] == eid), None)
            if e is None:
                continue
            hp = f" hp={e['hp']:.0f}"
            tag = f"FIRE T{eid}{hp}" if ready else f"T{eid} on cooldown{hp} (stand if in range)"
            out.append((a, f"T{eid}", tag))
    return out


def prepare_typed(snap, step: int = 0) -> dict:
    """Opaque option codes so the model cannot latch onto names like T2 or WEST."""
    enemies = living(snap["enemies"])
    allies = living(snap["allies"])
    schema_dict: dict = {}

    def codes(n: int) -> List[str]:
        return [f"P{j}" if n <= 10 else f"P{j:02d}" for j in range(n)]

    focus_items = []
    for e in enemies:
        guns = 0
        for a in allies:
            row = snap["avail"][a["id"]]
            idx = 6 + e["id"]
            if idx < len(row) and row[idx]:
                guns += 1
        focus_items.append((
            f"T{e['id']}",
            f"enemy T{e['id']} {e.get('name', e['type'])} {e.get('role', '?')} "
            f"hp={e['hp']:.0f}/{e['max_hp']:.0f} guns={guns} pos=({e['x']:.1f},{e['y']:.1f})",
        ))
    if not focus_items:
        focus_items = [("T0", "no living enemy")]
    frng = random.Random(step * 7919 + 3)
    frng.shuffle(focus_items)
    fkeys = codes(len(focus_items))
    focus_back = {}
    fbits = []
    for k, (sem, meaning) in zip(fkeys, focus_items):
        focus_back[k] = sem
        fbits.append(f"{k}={meaning}")
    schema_dict["FOCUS"] = {
        "type": "enum",
        "choices": fkeys,
        "description": (
            "Shared fire target. Option codes are random and meaningless; pick by the enemy stats. "
            + " | ".join(fbits)
        ),
    }

    decode: Dict[int, Dict[str, int]] = {}
    sem_maps: Dict[int, Dict[str, str]] = {}
    legal_sem: Dict[str, List[str]] = {}
    tags_sem: Dict[str, Dict[str, str]] = {}
    for ally in snap["allies"]:
        if not ally.get("alive"):
            continue
        i = ally["id"]
        legal = legal_bundle(ally, snap)
        if not legal:
            continue
        items = list(legal)
        random.Random(step * 7919 + 17 + i).shuffle(items)
        keys = codes(len(items))
        amap: Dict[str, int] = {}
        smap: Dict[str, str] = {}
        bits = []
        for k, (act, lab, tag) in zip(keys, items):
            amap[k] = act
            smap[k] = lab
            bits.append(f"{k}={tag}")
        ready = "READY" if float(ally.get("cd") or 0) <= 0.08 else "COOLING"
        schema_dict[f"U{i}"] = {
            "type": "enum",
            "choices": keys,
            "description": (
                f"U{i} {ally.get('name', ally['type'])} {ally.get('role', '?')} "
                f"hp={ally['hp']:.0f} cd={ally['cd']:.2f} {ready}. "
                "Option codes are random; pick by meaning. "
                + " | ".join(bits)
            )[:800],
        }
        decode[i] = amap
        sem_maps[i] = smap
        legal_sem[f"U{i}"] = [lab for _, lab, _ in legal]
        tags_sem[f"U{i}"] = {lab: tag for _, lab, tag in legal}
    return {
        "schema": schema_dict,
        "decode": decode,
        "sem": sem_maps,
        "focus": focus_back,
        "legal_sem": legal_sem,
        "tags_sem": tags_sem,
    }


def diagnose_draft(proposed: Dict[str, str], legal_tags: Dict[str, Dict[str, str]]) -> str:
    fires: Dict[str, List[str]] = {}
    waits = []
    walks = []
    for u, lab in proposed.items():
        tag = (legal_tags.get(u) or {}).get(lab, "")
        if lab.startswith("T") and tag.startswith("FIRE"):
            fires.setdefault(lab, []).append(u)
        elif lab.startswith("T"):
            waits.append(f"{u}={lab}")
        else:
            walks.append(f"{u}={lab}/{tag.split()[0] if tag else '?'}")
    bits = []
    if len(fires) > 1:
        bits.append("SPLIT-FIRE " + " ".join(f"{t}:{len(v)}" for t, v in fires.items()))
    elif len(fires) == 1:
        t, v = next(iter(fires.items()))
        bits.append(f"UNIFIED-FIRE {t} n={len(v)}")
    else:
        bits.append("NO-FIRE")
    if waits:
        bits.append("STANDING-ON-CD " + ",".join(waits))
    if walks:
        bits.append("WALKS " + ",".join(walks))
    return " | ".join(bits)


def _parse_field(parsed, key: str) -> str:
    raw = (parsed or {}).get(key)
    if isinstance(raw, dict):
        raw = raw.get("value")
    return str(raw).strip().upper() if raw is not None else ""


def _fallback_from_maps(label_maps: Dict[int, Dict[str, int]], n: int) -> List[int]:
    actions = [0] * n
    for i, amap in label_maps.items():
        fire = next((amap[k] for k in amap if k.startswith("T")), None)
        actions[i] = fire if fire is not None else next(iter(amap.values()))
    return actions


class QwenCentralPolicy:
    """One commander, one JSON: FOCUS then every living unit action."""

    HIST_CHAR_BUDGET = 8000

    def __init__(self):
        get_engine, run, StructuredSchema = _engine()
        self._run = run
        self._Schema = StructuredSchema
        get_engine()
        self.n_calls = 0
        self.n_fallback = 0
        self.n_guard = 0
        self.infer_s = 0.0
        self.tactic_counts: Dict[str, int] = {}
        self.last_order = ""
        self.last_s1: Dict[str, str] = {}
        self._trace: List[str] = []
        self._states: List[str] = []

    def _history(self) -> str:
        parts = []
        if self._trace:
            parts.append("Past ticks:\n" + "\n".join(self._trace))
        if self._states:
            parts.append("Past states:\n" + "\n-----\n".join(self._states))
        return "\n".join(parts)

    def _remember(self, step: int, snap: Dict[str, Any], order: str) -> None:
        allies = living(snap["allies"])
        enemies = living(snap["enemies"])
        a_hp = ",".join(f"U{a['id']}:{a['hp']:.0f}" for a in allies) or "none"
        e_hp = ",".join(f"T{e['id']}:{e['hp']:.0f}" for e in enemies) or "none"
        self._trace.append(f"t={step} {order} A[{a_hp}] E[{e_hp}]")
        self._states.append(f"t={step}\n" + compact_state("hist", step, snap, prefix=False))
        # Keep every tick's one-line trace; only the last few full states (prefill cost).
        if len(self._states) > 4:
            self._states = self._states[-4:]
        while self._states and (sum(len(s) for s in self._states) + sum(len(x) for x in self._trace)) > self.HIST_CHAR_BUDGET:
            self._states.pop(0)

    def act(self, map_name: str, step: int, snap: Dict[str, Any]) -> List[int]:
        if step == 0:
            self._trace = []
            self._states = []
            self.last_order = ""
        n = snap["n_agents"]
        pack = prepare_typed(snap, step)
        schema_dict, label_maps = pack["schema"], pack["decode"]
        actions = [0] * n
        if not schema_dict:
            return actions
        schema = self._Schema(schema_dict)
        ctx = _context(map_name, step, snap, self.last_order, self._history())
        t0 = time.perf_counter()
        try:
            result = self._run(ctx, schema)
        except Exception:
            self.n_fallback += 1
            self.infer_s += time.perf_counter() - t0
            self.n_calls += 1
            return _fallback_from_maps(label_maps, n)
        self.infer_s += time.perf_counter() - t0
        self.n_calls += 1
        parsed = (result or {}).get("parsed_json") or {}
        proposed = {}
        focus = pack["focus"].get(_parse_field(parsed, "FOCUS"), "")
        for i, amap in label_maps.items():
            op = _parse_field(parsed, f"U{i}")
            if op not in amap:
                op = next(iter(amap))
                self.n_fallback += 1
            sem_lab = pack["sem"][i].get(op, op)
            proposed[f"U{i}"] = sem_lab
            actions[i] = amap[op]
        self.last_s1 = dict(proposed)
        self.last_order = (f"FOCUS={focus} " if focus else "") + " ".join(f"{k}={v}" for k, v in proposed.items())
        self.tactic_counts["central"] = self.tactic_counts.get("central", 0) + 1
        if focus:
            self.tactic_counts["focus_" + focus] = self.tactic_counts.get("focus_" + focus, 0) + 1
        self._remember(step, snap, self.last_order)
        if step < 3:
            print(f"    t={step} {self.last_order}", flush=True)
        return actions


QwenPolicy = QwenCentralPolicy


class TwoStagePolicy:
    """Typed Qwen System-1 (all unit actions, one shot) + API System-2 corrector.

    S1 proposes independently per unit. S2 sees the whole assignment and rewrites it.
    """

    def __init__(self):
        from system2_api import System2Client

        self.s1 = QwenCentralPolicy()
        self.s2 = System2Client()
        self.n_calls = 0
        self.n_fallback = 0
        self.n_guard = 0
        self.infer_s = 0.0
        self.tactic_counts: Dict[str, int] = {}
        self.last_s1: Dict[str, str] = {}
        self.last_s2: Dict[str, str] = {}
        self.last_order = ""
        self._s2_cooldown = 0

    def act(self, map_name: str, step: int, snap: Dict[str, Any]) -> List[int]:
        if step == 0:
            self._s2_cooldown = 0
        n = snap["n_agents"]
        pack = prepare_typed(snap, step)
        schema_dict, label_maps = pack["schema"], pack["decode"]
        legal_labs, legal_tags = pack["legal_sem"], pack["tags_sem"]
        actions = [0] * n
        if not schema_dict:
            return actions
        schema = self.s1._Schema(schema_dict)
        ctx = _context(map_name, step, snap, self.last_order, getattr(self.s1, "_history", lambda: "")())
        t0 = time.perf_counter()
        try:
            result = self.s1._run(ctx, schema)
        except Exception:
            self.n_fallback += 1
            self.infer_s += time.perf_counter() - t0
            self.n_calls += 1
            return _fallback_from_maps(label_maps, n)
        s1_ms = time.perf_counter() - t0
        parsed = (result or {}).get("parsed_json") or {}
        proposed: Dict[str, str] = {}
        focus = pack["focus"].get(_parse_field(parsed, "FOCUS"), "")
        for i, amap in label_maps.items():
            op = _parse_field(parsed, f"U{i}")
            if op not in amap:
                op = next(iter(amap))
                self.n_fallback += 1
            sem_lab = pack["sem"][i].get(op, op)
            if focus:
                for k, sl in pack["sem"][i].items():
                    if sl == focus:
                        op = k
                        sem_lab = focus
                        break
            proposed[f"U{i}"] = sem_lab
            actions[i] = amap[op]
        self.last_s1 = dict(proposed)
        if focus:
            proposed = dict(proposed)  # keep units-only for S2 legal map
            self.tactic_counts["focus_" + focus] = self.tactic_counts.get("focus_" + focus, 0) + 1
        state = compact_state(map_name, step, snap, prefix=False)
        draft_diag = (f"FOCUS={focus} | " if focus else "") + diagnose_draft(proposed, legal_tags)
        t1 = time.perf_counter()
        skip_s2 = False
        corrected = self.s2.correct(state, proposed, legal_labs, legal_tags, draft_diag)
        s2_ms = time.perf_counter() - t1
        self.infer_s += s1_ms + s2_ms
        self.n_calls += 1
        used = proposed
        if corrected:
            self.last_s2 = dict(corrected)
            self.n_guard += sum(1 for k, v in corrected.items() if proposed.get(k) != v)
            self.tactic_counts["s2"] = self.tactic_counts.get("s2", 0) + 1
            for uk, lab in corrected.items():
                i = int(uk[1:])
                if i in label_maps and lab in label_maps[i]:
                    actions[i] = label_maps[i][lab]
            used = {**proposed, **corrected}
        else:
            self.tactic_counts["s2_fail"] = self.tactic_counts.get("s2_fail", 0) + 1
        self.tactic_counts["s1"] = self.tactic_counts.get("s1", 0) + 1
        self.last_order = (f"FOCUS={focus} " if focus else "") + " ".join(f"{k}={v}" for k, v in used.items())
        if step < 4 or (corrected and any(proposed.get(k) != v for k, v in corrected.items())):
            print(f"    t={step} {draft_diag} s1={proposed} s2={corrected}", flush=True)
        return actions


# Persistent attack plan. Filled rarely; adapter follows it every tick.
PLAN = {
    "fight": [
        ("trade", "even_ranged_trade", "Same ranged unit both sides. Everyone walks in and focus-fires."),
        ("kite", "ranged_kiting_melee", "Allies are ranged, enemies are melee (zealot/zergling). Shoot then walk away. Do not stand and trade."),
        ("bait", "one_tank_vs_building", "Few ranged allies vs ONE immobile building/spine. Only one ally goes in; the partner stays out."),
        ("mixed", "melee_front_ranged_back", "Both sides mix melee and ranged. Melee tanks nearest, ranged shoot a shared target."),
        ("outnumbered", "outnumbered_same_type", "Same unit type but we have fewer. Wait until most guns are ready, then focus-fire."),
    ],
    "kill": [
        ("guns_hp", "shared_weakest_already_in_guns", "Everyone shoots the same enemy: most allies already able to shoot it, then lowest HP."),
        ("nearest", "each_fires_closest_enemy", "Each unit fires whichever enemy is closest to itself."),
        ("building", "the_immobile_building", "Focus the one immobile high-damage building."),
        ("melee", "nearest_melee_threat", "Focus the nearest melee enemy."),
    ],
    "tank": [
        ("all", "everyone_commits", "All living allies may enter range and fight."),
        ("melee", "melee_allies_hold_front", "Melee allies go in front; ranged stay behind them."),
        ("one", "only_highest_hp_ally_enters", "Only the healthiest ally enters range. Everyone else stays out."),
        ("none", "nobody_tanks_all_kite", "Nobody holds the line. Whole army kites."),
    ],
    "commit": [
        ("now", "shoot_as_soon_as_in_range", "If a legal shot exists, take it."),
        ("group", "wait_until_most_can_shoot", "Do not shoot until most living allies can shoot the same enemy."),
        ("safe", "shoot_only_if_melee_not_close", "Shoot when ready, but walk away if melee has closed in."),
    ],
    "where": [
        ("push", "close_on_the_target", "If not shooting, walk toward the chosen enemy."),
        ("hold", "hold_ground", "If not shooting, stand still."),
        ("kite", "back_off_on_cooldown_or_melee", "If not shooting, walk away from the nearest enemy (after closing into range)."),
    ],
}

TASK = (
    "Task: You are the PLANNER. First READ the evidence, then fill the JSON. "
    "Win = all enemies dead and at least one ally alive. "
    "The first blank is seen: pick the sentence that matches the counts in EVIDENCE. "
    "Later blanks must agree with seen. Copy fill strings exactly."
)


def _counts(snap):
    allies = living(snap["allies"])
    enemies = living(snap["enemies"])
    return {
        "nA": len(allies),
        "nE": len(enemies),
        "static_e": sum(1 for e in enemies if e.get("role") == "static"),
        "melee_e": sum(1 for e in enemies if e.get("role") == "melee"),
        "melee_a": sum(1 for a in allies if a.get("role") == "melee"),
        "ranged_a": sum(1 for a in allies if a.get("role") == "ranged"),
        "ranged_e": sum(1 for e in enemies if e.get("role") == "ranged"),
    }


def _seen_options(snap):
    c = _counts(snap)
    return [
        (
            "building",
            "enemy_is_an_immobile_building",
            f"EVIDENCE says immobile_enemies={c['static_e']}, ranged_allies={c['ranged_a']}, n_enemies={c['nE']}. "
            "Pick this if there is at least one immobile building and the enemy army is not a melee ball.",
        ),
        (
            "kite",
            "allies_ranged_enemies_melee",
            f"EVIDENCE says melee_enemies={c['melee_e']}, melee_allies={c['melee_a']}, ranged_allies={c['ranged_a']}. "
            "Pick this if allies are ranged and enemies are melee.",
        ),
        (
            "trade",
            "same_ranged_even_fight",
            f"EVIDENCE says n_allies={c['nA']}, n_enemies={c['nE']}, ranged_allies={c['ranged_a']}, ranged_enemies={c['ranged_e']}, immobile={c['static_e']}, melee_e={c['melee_e']}. "
            "Pick this only if both sides are the same ranged unit and counts are similar, with no building and no melee.",
        ),
        (
            "mixed",
            "both_sides_mixed_melee_and_ranged",
            f"EVIDENCE says melee_allies={c['melee_a']}, melee_enemies={c['melee_e']}, ranged_allies={c['ranged_a']}. "
            "Pick this if BOTH sides have melee and ranged.",
        ),
        (
            "outnumbered",
            "same_type_we_have_fewer",
            f"EVIDENCE says n_allies={c['nA']} vs n_enemies={c['nE']}, immobile={c['static_e']}, melee_e={c['melee_e']}. "
            "Pick this if same unit type and we have fewer living units, no building, no enemy melee.",
        ),
    ]


def _plan_sheet(snap) -> str:
    lines = [
        "JSON to fill:",
        "{",
        '  "seen": "____",',
        '  "fight": "____",',
        '  "kill": "____",',
        '  "tank": "____",',
        '  "commit": "____",',
        '  "where": "____"',
        "}",
        "Legal fills (copy one fill string exactly):",
        "seen:",
    ]
    for _sem, fill, meaning in _seen_options(snap):
        lines.append(f"  {fill} = {meaning}")
    for fname, options in PLAN.items():
        lines.append(f"{fname}:")
        for _sem, fill, meaning in options:
            lines.append(f"  {fill} = {meaning}")
    lines.append("If seen is enemy_is_an_immobile_building, fight must be one_tank_vs_building and tank must be only_highest_hp_ally_enters.")
    lines.append("If seen is allies_ranged_enemies_melee, fight must be ranged_kiting_melee and where must be back_off_on_cooldown_or_melee.")
    return "\n".join(lines)

def _hp_line(snap) -> str:
    allies = living(snap["allies"])
    enemies = living(snap["enemies"])
    a = ",".join(f"U{u['id']}:{u['hp']:.0f}({u['x']:.0f},{u['y']:.0f})" for u in allies) or "none"
    e = ",".join(f"T{u['id']}:{u['hp']:.0f}({u['x']:.0f},{u['y']:.0f})" for u in enemies) or "none"
    return f"A[{a}] E[{e}]"


def _squad_facts(snap) -> str:
    allies = living(snap["allies"])
    enemies = living(snap["enemies"])
    nA, nE = len(allies), len(enemies)
    types_a = ",".join(a.get("name", a["type"])[:8] for a in allies) or "none"
    types_e = ",".join(e.get("name", e["type"])[:8] for e in enemies) or "none"
    roles_a = ",".join(sorted({a.get("role", "?") for a in allies})) or "none"
    roles_e = ",".join(sorted({e.get("role", "?") for e in enemies})) or "none"
    static_e = sum(1 for e in enemies if e.get("role") == "static")
    melee_e = sum(1 for e in enemies if e.get("role") == "melee")
    melee_a = sum(1 for a in allies if a.get("role") == "melee")
    ranged_a = sum(1 for a in allies if a.get("role") == "ranged")
    ready = sum(1 for a in allies if float(a.get("cd") or 0) <= 0.08)
    a_hp = sum(a["hp"] + a.get("shield", 0) for a in allies)
    e_hp = sum(e["hp"] + e.get("shield", 0) for e in enemies)
    return (
        f"Now: {nA} allies [{types_a}] roles={roles_a} hp={a_hp:.0f} ready={ready}/{nA} "
        f"vs {nE} enemies [{types_e}] roles={roles_e} hp={e_hp:.0f}. "
        f"immobile_enemies={static_e} melee_enemies={melee_e} melee_allies={melee_a} "
        f"ranged_allies={ranged_a}."
    )


def prepare_plan(snap, step: int = 0) -> dict:
    facts = _squad_facts(snap)
    schema = {}
    back = {}
    fields = [("seen", _seen_options(snap))] + list(PLAN.items())
    for fi, (fname, options) in enumerate(fields):
        items = list(options)
        random.Random(step * 7919 + 17 + fi).shuffle(items)
        fmap = {}
        bits = []
        fills = []
        for sem, fill, meaning in items:
            fmap[fill] = sem
            fills.append(fill)
            bits.append(f"{fill} = {meaning}")
        back[fname] = fmap
        schema[fname] = {
            "type": "enum",
            "choices": fills,
            "description": (f"Blank {fname}. Paste one fill. " + " | ".join(bits))[:1400],
        }
    return {"schema": schema, "facts": facts, "back": back, "sheet": _plan_sheet(snap)}


def _decode_form(parsed, back) -> Dict[str, str]:
    """Map filled strings onto adapter keys. Do not uppercase: fills are snake_case."""
    parsed = parsed or {}
    form = {}
    for fname, fmap in back.items():
        raw = parsed.get(fname)
        if isinstance(raw, dict):
            raw = raw.get("value")
        key = str(raw).strip() if raw is not None else ""
        if key in fmap:
            form[fname] = fmap[key]
            continue
        lower = {k.lower(): v for k, v in fmap.items()}
        form[fname] = lower.get(key.lower(), next(iter(fmap.values())))
    return form


class QwenSquadPolicy:
    """Planner: fill attack plan on events. Adapter executes every tick."""

    HIST_CHAR_BUDGET = 6000
    MAX_FULL_STATES = 3

    def __init__(self):
        get_engine, run, StructuredSchema = _engine()
        self._run = run
        self._Schema = StructuredSchema
        get_engine()
        self.n_calls = 0
        self.n_fallback = 0
        self.n_guard = 0
        self.n_replan = 0
        self.infer_s = 0.0
        self.tactic_counts: Dict[str, int] = {}
        self.last_order = ""
        self.plan: Dict[str, str] = {}
        self._focus: Optional[int] = None
        self._trace: List[str] = []
        self._states: List[str] = []
        self._nA = 0
        self._nE = 0
        self._hp = 0.0

    def _should_replan(self, snap: Dict[str, Any], step: int) -> bool:
        if step == 0 or not self.plan:
            return True
        allies = living(snap["allies"])
        enemies = living(snap["enemies"])
        nA, nE = len(allies), len(enemies)
        hp = sum(a["hp"] + a.get("shield", 0) for a in allies)
        if nA != self._nA or nE != self._nE:
            return True
        if self._hp > 1 and hp < 0.85 * self._hp:
            return True
        return False

    def _remember_plan(self, map_name: str, step: int, snap: Dict[str, Any], plan: Dict[str, str], reason: str) -> None:
        filled = " ".join(f"{k}={v}" for k, v in plan.items())
        self._trace.append(f"t={step} replan={reason} {filled} {_hp_line(snap)}")
        self._states.append(f"t={step}\n" + compact_state(map_name, step, snap, prefix=False))
        if len(self._states) > self.MAX_FULL_STATES:
            self._states = self._states[-self.MAX_FULL_STATES:]
        while self._states and (
            sum(len(s) for s in self._states) + sum(len(x) for x in self._trace)
        ) > self.HIST_CHAR_BUDGET:
            self._states.pop(0)

    def _history(self) -> str:
        parts = []
        if self._trace:
            parts.append("Past plans (oldest first):\n" + "\n".join(self._trace))
        if self._states:
            parts.append("States at those plans:\n" + "\n-----\n".join(self._states))
        return "\n".join(parts)

    def _write_plan(self, map_name: str, step: int, snap: Dict[str, Any], reason: str) -> Dict[str, str]:
        pack = prepare_plan(snap, step)
        schema = self._Schema(pack["schema"])
        hist = self._history()
        last = ""
        if self.plan:
            allies = living(snap["allies"])
            enemies = living(snap["enemies"])
            hp = sum(a["hp"] + a.get("shield", 0) for a in allies)
            last = (
                f"Previous plan outcome: allies {self._nA}->{len(allies)}, "
                f"enemies {self._nE}->{len(enemies)}, our_hp {self._hp:.0f}->{hp:.0f}. "
                "Do not copy a same-ranged-trade plan if EVIDENCE shows a building or melee."
            )
        ctx = (
            TASK
            + "\nReplan reason: " + reason + ".\n"
            + "EVIDENCE (read this before filling seen):\n"
            + _situation(snap) + "\n" + pack["facts"] + "\n"
            + compact_state(map_name, step, snap, prefix=False)
            + (("\n" + last) if last else "")
            + (("\n" + hist) if hist else "")
            + "\nMap: " + map_name + "\n"
            + pack["sheet"]
        )
        fallback = {
            "seen": "trade",
            "fight": "trade",
            "kill": "guns_hp",
            "tank": "all",
            "commit": "now",
            "where": "push",
        }
        t0 = time.perf_counter()
        try:
            result = self._run(ctx, schema)
        except Exception:
            self.n_fallback += 1
            self.infer_s += time.perf_counter() - t0
            self.n_calls += 1
            return fallback
        self.infer_s += time.perf_counter() - t0
        self.n_calls += 1
        parsed = (result or {}).get("parsed_json") or {}
        plan = _decode_form(parsed, pack["back"])
        return plan or fallback

    def act(self, map_name: str, step: int, snap: Dict[str, Any]) -> List[int]:
        if step == 0:
            self._trace = []
            self._states = []
            self.plan = {}
            self.last_order = ""
            self._focus = None
            self._nA = 0
            self._nE = 0
            self._hp = 0.0
        allies = living(snap["allies"])
        enemies = living(snap["enemies"])
        hp_now = sum(a["hp"] + a.get("shield", 0) for a in allies)
        reason = None
        if step == 0 or not self.plan:
            reason = "battle_start"
        elif len(allies) != self._nA or len(enemies) != self._nE:
            reason = "unit_died"
        elif self._hp > 1 and hp_now < 0.70 * self._hp:
            reason = "hp_drop"
        if reason:
            self.plan = self._write_plan(map_name, step, snap, reason)
            self.n_replan += 1
            self.last_order = f"{reason} " + " ".join(f"{k}={v}" for k, v in self.plan.items())
            key = "{seen}/{fight}/{tank}".format(
                **{k: self.plan.get(k, "?") for k in ("seen", "fight", "tank")}
            )
            self.tactic_counts[key] = self.tactic_counts.get(key, 0) + 1
            self.tactic_counts["replan_" + reason] = self.tactic_counts.get("replan_" + reason, 0) + 1
            self._remember_plan(map_name, step, snap, self.plan, reason)
            print(f"    t={step} PLAN {self.last_order}", flush=True)
            self._hp = hp_now
        self._focus = pick_plan_target(snap, self.plan.get("kill", "guns_hp"), self._focus)
        actions = execute_plan(snap, self.plan, self._focus)
        self._nA = len(allies)
        self._nE = len(enemies)
        if not reason:
            pass
        return actions


class ApiPlanPolicy:
    """Planner via LLM gateway Responses API, reasoning off. Adapter executes every tick."""

    HIST_CHAR_BUDGET = 6000
    MAX_FULL_STATES = 3

    def __init__(self):
        from system2_api import System2Client

        self.s2 = System2Client(timeout=8.0)
        self.n_calls = 0
        self.n_fallback = 0
        self.n_guard = 0
        self.n_replan = 0
        self.infer_s = 0.0
        self.tactic_counts: Dict[str, int] = {}
        self.last_order = ""
        self.plan: Dict[str, str] = {}
        self._focus: Optional[int] = None
        self._trace: List[str] = []
        self._states: List[str] = []
        self._nA = 0
        self._nE = 0
        self._hp = 0.0

    def _history(self) -> str:
        parts = []
        if self._trace:
            parts.append("Past plans:\n" + "\n".join(self._trace))
        if self._states:
            parts.append("States at those plans:\n" + "\n-----\n".join(self._states))
        return "\n".join(parts)

    def _remember_plan(self, map_name: str, step: int, snap: Dict[str, Any], plan: Dict[str, str], reason: str) -> None:
        filled = " ".join(f"{k}={v}" for k, v in plan.items())
        self._trace.append(f"t={step} replan={reason} {filled} {_hp_line(snap)}")
        self._states.append(f"t={step}\n" + compact_state(map_name, step, snap, prefix=False))
        if len(self._states) > self.MAX_FULL_STATES:
            self._states = self._states[-self.MAX_FULL_STATES:]
        while self._states and (
            sum(len(s) for s in self._states) + sum(len(x) for x in self._trace)
        ) > self.HIST_CHAR_BUDGET:
            self._states.pop(0)

    def _write_plan(self, map_name: str, step: int, snap: Dict[str, Any], reason: str) -> Dict[str, str]:
        from smac_laya_policy import infer_seen

        pack = prepare_plan(snap, step)
        last = ""
        if self.plan:
            allies = living(snap["allies"])
            enemies = living(snap["enemies"])
            hp = sum(a["hp"] + a.get("shield", 0) for a in allies)
            last = (
                f"Previous plan outcome: allies {self._nA}->{len(allies)}, "
                f"enemies {self._nE}->{len(enemies)}, our_hp {self._hp:.0f}->{hp:.0f}. "
                "Do not copy a same-ranged-trade plan if EVIDENCE shows a building or melee."
            )
        ctx = (
            TASK
            + "\nReplan reason: " + reason + ".\n"
            + "EVIDENCE (read this before filling seen):\n"
            + _situation(snap) + "\n" + pack["facts"] + "\n"
            + compact_state(map_name, step, snap, prefix=False)
            + (("\n" + last) if last else "")
            + (("\n" + self._history()) if self._trace else "")
            + "\nMap: " + map_name + "\n"
            + pack["sheet"]
        )
        fallback = {
            "seen": infer_seen(snap),
            "fight": "trade",
            "kill": "guns_hp",
            "tank": "all",
            "commit": "now",
            "where": "push",
        }
        t0 = time.perf_counter()
        raw = self.s2.fill_json(
            "Fill the JSON cloze. Output one JSON object only. No markdown. "
            "Keys: seen, fight, kill, tank, commit, where. Values must be exact fill strings from the sheet.",
            ctx,
        )
        self.infer_s += time.perf_counter() - t0
        self.n_calls += 1
        if not raw:
            self.n_fallback += 1
            return fallback
        plan = _decode_form(raw, pack["back"])
        if not plan.get("seen") and not plan.get("fight"):
            self.n_fallback += 1
            return fallback
        return plan

    def act(self, map_name: str, step: int, snap: Dict[str, Any]) -> List[int]:
        if step == 0:
            self._trace = []
            self._states = []
            self.plan = {}
            self.last_order = ""
            self._focus = None
            self._nA = 0
            self._nE = 0
            self._hp = 0.0
        allies = living(snap["allies"])
        enemies = living(snap["enemies"])
        hp_now = sum(a["hp"] + a.get("shield", 0) for a in allies)
        reason = None
        if step == 0 or not self.plan:
            reason = "battle_start"
        elif len(allies) != self._nA or len(enemies) != self._nE:
            reason = "unit_died"
        elif self._hp > 1 and hp_now < 0.70 * self._hp:
            reason = "hp_drop"
        if reason:
            self.plan = self._write_plan(map_name, step, snap, reason)
            self.n_replan += 1
            self.last_order = f"{reason} " + " ".join(f"{k}={v}" for k, v in self.plan.items())
            key = "{seen}/{fight}/{tank}".format(
                **{k: self.plan.get(k, "?") for k in ("seen", "fight", "tank")}
            )
            self.tactic_counts[key] = self.tactic_counts.get(key, 0) + 1
            self.tactic_counts["replan_" + reason] = self.tactic_counts.get("replan_" + reason, 0) + 1
            self._remember_plan(map_name, step, snap, self.plan, reason)
            print(f"    t={step} PLAN {self.last_order}", flush=True)
            self._hp = hp_now
        self._focus = pick_plan_target(snap, self.plan.get("kill", "guns_hp"), self._focus)
        actions = execute_plan(snap, self.plan, self._focus, trust_plan=True)
        self._nA = len(allies)
        self._nE = len(enemies)
        return actions


def _stop_action(labels) -> int:
    return next((a for a, lab in labels if lab == "stop"), labels[0][0])


def _dir_action(ally, lab: str, labels, threat) -> int:
    for a, name in labels:
        if name == lab:
            return a
    if threat is not None:
        return move_away_action(ally, threat, labels)
    return _stop_action(labels)


def _plan_stance(plan: Dict[str, str]) -> str:
    return (plan.get("seen") or plan.get("fight") or "trade").lower()


def _pick_tank_id(snap, focus) -> Optional[int]:
    allies = living(snap["allies"])
    if not allies or focus is None:
        return None
    def labels_of(a):
        return labels_from_avail(snap["avail"][a["id"]], snap["n_enemies"])
    ready_in = []
    for a in allies:
        shot = attack_action(labels_of(a), focus["id"])
        if shot is not None and float(a.get("cd") or 0) <= 0.08:
            ready_in.append(a)
    if ready_in:
        return max(ready_in, key=lambda a: a["hp"] + a.get("shield", 0))["id"]
    return min(allies, key=lambda a: hypot(a, focus))["id"]


def prepare_micro(snap, plan: Dict[str, str], focus) -> dict:
    """Tiny per-unit menu implied by the plan. Returns schema + action maps."""
    allies = living(snap["allies"])
    enemies = living(snap["enemies"])
    stance = _plan_stance(plan)
    melee = [e for e in enemies if e.get("role") == "melee"] or enemies
    threat = None
    away_lab = "W"
    if allies and melee:
        cx = sum(a["x"] for a in allies) / len(allies)
        cy = sum(a["y"] for a in allies) / len(allies)
        threat = min(melee, key=lambda e: (e["x"] - cx) ** 2 + (e["y"] - cy) ** 2)
        away_lab = _group_away_lab(allies, threat)
    tank_id = _pick_tank_id(snap, focus) if stance in ("building", "bait") else None
    schema = {}
    decode: Dict[int, Dict[str, int]] = {}
    singles: Dict[int, int] = {}
    for ally in allies:
        i = ally["id"]
        labels = labels_from_avail(snap["avail"][i], snap["n_enemies"])
        ready = float(ally.get("cd") or 0) <= 0.08
        shot = None
        if focus is not None:
            shot = attack_action(labels, focus["id"])
        if shot is None:
            for e in enemies:
                s = attack_action(labels, e["id"])
                if s is not None:
                    shot = s
                    break
        d_threat = hypot(ally, threat) if threat is not None else 99.0
        d_focus = hypot(ally, focus) if focus is not None else 99.0
        items = []  # fill, meaning, action

        if stance in ("building", "bait"):
            if i == tank_id:
                if shot is not None and ready:
                    items.append(("fire_now", "Shoot the building. You are the tank and ready.", shot))
                elif ready:
                    items.append(("walk_in", "Walk toward the building. Only the tank does this.", move_toward_action(ally, focus, labels) if focus else _stop_action(labels)))
                else:
                    items.append(("walk_out", "Weapon cooling. Leave the building range.", move_away_action(ally, focus, labels) if focus else _stop_action(labels)))
            else:
                if d_focus < 8.6 and focus is not None:
                    items.append(("stay_out", "You are not the tank. Leave range.", move_away_action(ally, focus, labels)))
                else:
                    items.append(("hold", "Stay out of the fight.", _stop_action(labels)))
        elif stance in ("kite",) or (plan.get("where") or "") == "kite" or (plan.get("fight") or "") == "kite":
            if d_threat > 7.0 and focus is not None:
                items.append(("close_in", "Melee is far. Walk toward the focus.", move_toward_action(ally, focus, labels)))
            elif shot is not None and ready and d_threat >= 5.0:
                items.append(("volley", "Spacing is safe. Shoot now with the army.", shot))
                items.append(("retreat", "Melee is close enough. Pull back with the army.", _dir_action(ally, away_lab, labels, threat)))
            else:
                items.append(("retreat", "Move with the army away from melee.", _dir_action(ally, away_lab, labels, threat)))
        else:
            if shot is not None:
                items.append(("fire_now", "A legal shot exists. Fire.", shot))
            elif focus is not None:
                items.append(("walk_in", "Walk toward the shared target.", move_toward_action(ally, focus, labels)))
            else:
                items.append(("hold", "Stand still.", _stop_action(labels)))

        # de-dupe fills
        seen = set()
        uniq = []
        for fill, meaning, act in items:
            if fill in seen:
                continue
            seen.add(fill)
            uniq.append((fill, meaning, act))
        items = uniq
        if not items:
            singles[i] = _stop_action(labels)
            continue
        if len(items) == 1:
            singles[i] = items[0][2]
            continue
        fills = [it[0] for it in items]
        amap = {it[0]: it[2] for it in items}
        schema[f"U{i}"] = {
            "type": "enum",
            "choices": fills,
            "description": (
                f"U{i} hp={ally['hp']:.0f} cd={ally['cd']:.2f} d_threat={d_threat:.1f}. "
                + " | ".join(f"{f} = {m}" for f, m, _ in items)
            )[:700],
        }
        decode[i] = amap
    return {"schema": schema, "decode": decode, "singles": singles}


class ApiQwenExecPolicy(ApiPlanPolicy):
    """API planner + Qwen executor on a plan-cropped 2-3 option menu."""

    def __init__(self):
        super().__init__()
        get_engine, run, StructuredSchema = _engine()
        self._run = run
        self._Schema = StructuredSchema
        get_engine()

    def act(self, map_name: str, step: int, snap: Dict[str, Any]) -> List[int]:
        if step == 0:
            self._trace = []
            self._states = []
            self.plan = {}
            self.last_order = ""
            self._focus = None
            self._nA = 0
            self._nE = 0
            self._hp = 0.0
        allies = living(snap["allies"])
        enemies = living(snap["enemies"])
        hp_now = sum(a["hp"] + a.get("shield", 0) for a in allies)
        reason = None
        if step == 0 or not self.plan:
            reason = "battle_start"
        elif len(allies) != self._nA or len(enemies) != self._nE:
            reason = "unit_died"
        elif self._hp > 1 and hp_now < 0.70 * self._hp:
            reason = "hp_drop"
        if reason:
            self.plan = self._write_plan(map_name, step, snap, reason)
            self.n_replan += 1
            self.last_order = f"{reason} " + " ".join(f"{k}={v}" for k, v in self.plan.items())
            key = "{seen}/{fight}/{tank}".format(
                **{k: self.plan.get(k, "?") for k in ("seen", "fight", "tank")}
            )
            self.tactic_counts[key] = self.tactic_counts.get(key, 0) + 1
            self.tactic_counts["replan_" + reason] = self.tactic_counts.get("replan_" + reason, 0) + 1
            self._remember_plan(map_name, step, snap, self.plan, reason)
            print(f"    t={step} PLAN {self.last_order}", flush=True)
            self._hp = hp_now
        self._focus = pick_plan_target(snap, self.plan.get("kill", "guns_hp"), self._focus)
        n = snap["n_agents"]
        actions = [0] * n
        pack = prepare_micro(snap, self.plan, next((e for e in enemies if e["id"] == self._focus), None) if self._focus is not None else None)
        for i, act in pack["singles"].items():
            actions[i] = act
        if pack["schema"]:
            schema = self._Schema(pack["schema"])
            stance = _plan_stance(self.plan)
            ctx = (
                f"You are the executor under a fixed plan. Plan stance={stance}. "
                "Fill one choice per unit. Units should act together: all volley or all retreat. "
                "Never pick map directions; choices already mean fire/walk/hold.\n"
                + _situation(snap) + "\n" + _squad_facts(snap)
                + "\nCURRENT:\n" + compact_state(map_name, step, snap, prefix=False)
            )
            t0 = time.perf_counter()
            try:
                result = self._run(ctx, schema)
            except Exception:
                self.n_fallback += 1
                result = {}
            self.infer_s += time.perf_counter() - t0
            self.n_calls += 1
            parsed = (result or {}).get("parsed_json") or {}
            for i, amap in pack["decode"].items():
                raw = parsed.get(f"U{i}")
                if isinstance(raw, dict):
                    raw = raw.get("value")
                fill = str(raw).strip() if raw is not None else ""
                if fill not in amap:
                    fill = next(iter(amap))
                    self.n_fallback += 1
                actions[i] = amap[fill]
            if step < 3:
                shown = " ".join(f"U{i}={list(pack['decode'][i].keys())[0] if False else ''}" for i in pack["decode"])
                picked = []
                for i, amap in pack["decode"].items():
                    raw = parsed.get(f"U{i}")
                    if isinstance(raw, dict):
                        raw = raw.get("value")
                    picked.append(f"U{i}={raw}")
                print(f"    t={step} EXEC {' '.join(picked)}", flush=True)
        self._nA = len(allies)
        self._nE = len(enemies)
        return actions
