"""Tactic programs: physics conditions -> exam picks. Code still walks.

A program is an ordered rule list plus a fallback:

    {"name": "kite_then_fan",
     "rules": [{"when": {"speed": "we_are_faster", "enemy_melee": true},
                "set": {"ranged": "stutter"}},
               {"when": {"enemy_guns": 0, "our_ranged": {">=": 3}},
                "set": {"ranged": "concave"}}],
     "else": {"target": "guns"}}

Each tick the first rule whose `when` holds is merged over `else`; exams it
does not set take the code default. Conditions read physical features only
(see FEATURES); map names never appear. ProgramClient speaks the same
`system_one(state, questions)` interface as Jev, so the motor is unchanged.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

# Feature -> allowed values. "num" features accept numbers or {op: number}.
FEATURES: Dict[str, Any] = {
    "speed": ["we_are_faster", "even", "they_are_faster"],
    "reach": ["we_outrange", "even", "they_outrange"],
    "numbers": ["we_outnumber", "even", "they_have_a_few_more", "they_outnumber_badly"],
    "contact": ["far", "almost_in_range", "we_can_shoot", "melee_on_us"],
    "pocket": ["open", "in_neck", "at_mouth", "in_pocket", "past_pocket"],
    "hp_trend": ["no_trade_yet", "we_are_bleeding", "they_are_bleeding", "trading", "no_damage"],
    "if_we_stand_to_shoot": ["gap_holds", "melee_reaches_us", "no_enemy_melee"],
    "if_we_keep_standing": [
        "gap_holds", "melee_arrives_within_two_shots", "melee_arrives_before_next_shot",
        "already_in_blades", "no_enemy_melee",
    ],
    "if_we_withdraw": [
        "we_open_a_gap", "they_stand_we_open_gap", "gap_stays_they_chase", "they_catch_us", "no_enemy_melee",
    ],
    "suicide_blast": ["none", "our_bombs", "would_chain"],
    "ally_spacing": ["clumped", "open"],
    "guns_ready": ["some_ready", "all_cooling", "none"],
    "allied_melee": [True, False],
    "enemy_melee": [True, False],
    "someone_can_shoot_now": [True, False],
    "rally_is_behind_us": [True, False],
    "guns_in_blades": [True, False],
    "our_alive": "num",
    "their_alive": "num",
    "alive_ratio": "num",
    "our_ranged": "num",
    "our_melee": "num",
    "our_heal": "num",
    "our_suicide": "num",
    "enemy_guns": "num",
    "enemy_melee_n": "num",
    "enemy_heal": "num",
    "enemy_suicide": "num",
    "enemy_air": "num",
    "tick_frac": "num",
}

# Exam -> picks a program may set. tie takes "first"/"second" (by lower HP).
SETTABLE: Dict[str, List[str]] = {
    "formation": ["keep", "open"],
    "ranged": ["stack", "stutter", "concave"],
    "kite": ["all", "bait_one"],
    "melee": ["charge", "hold_choke", "snipe"],
    "bait": ["bait_one", "bait_two"],
    "target": ["frontline", "weakest_in_range", "clump", "heaviest", "guns", "healer"],
    "bar": ["pack", "bar"],
    "wing": ["stay", "step"],
    "stand": ["shoot", "step"],
    "tie": ["first", "second"],
}

OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b,
       "<": lambda a, b: a < b, "==": lambda a, b: a == b}


def features(state: Dict[str, Any]) -> Dict[str, Any]:
    """Flat physical features from commander_state(). No map name."""
    ph = state.get("physics") or {}
    our = state.get("our_force") or {}
    their = state.get("enemy_force") or {}
    oroles = our.get("roles") or {}
    troles = their.get("roles") or {}
    ranged_line = (state.get("lines") or {}).get("ranged") or {}
    tick = str(state.get("tick") or "0/1").split("/")
    try:
        tick_frac = float(tick[0]) / max(float(tick[1]), 1.0)
    except (ValueError, IndexError):
        tick_frac = 0.0
    our_alive = int(our.get("alive") or 0)
    their_alive = int(their.get("alive") or 0)
    return {
        "speed": ph.get("speed"),
        "reach": ph.get("reach"),
        "numbers": ph.get("numbers"),
        "contact": ph.get("contact"),
        "pocket": ph.get("pocket"),
        "hp_trend": ph.get("hp_trend"),
        "if_we_stand_to_shoot": ph.get("if_we_stand_to_shoot"),
        "if_we_keep_standing": ph.get("if_we_keep_standing"),
        "if_we_withdraw": ph.get("if_we_withdraw"),
        "suicide_blast": ph.get("suicide_blast"),
        "ally_spacing": ph.get("ally_spacing"),
        "guns_ready": ph.get("guns"),
        "allied_melee": bool(ph.get("allied_melee_present")),
        "enemy_melee": bool(ph.get("enemy_melee_present")),
        "someone_can_shoot_now": bool(ph.get("someone_can_shoot_now")),
        "rally_is_behind_us": bool(ph.get("rally_is_behind_us")),
        "guns_in_blades": bool(ranged_line.get("this_line_in_blades")),
        "our_alive": our_alive,
        "their_alive": their_alive,
        "alive_ratio": round(our_alive / max(their_alive, 1), 3),
        "our_ranged": int(oroles.get("ranged") or 0),
        "our_melee": int(oroles.get("melee") or 0),
        "our_heal": int(oroles.get("heal") or 0),
        "our_suicide": int(oroles.get("suicide") or 0),
        "enemy_guns": int(troles.get("ranged") or 0),
        "enemy_melee_n": int(troles.get("melee") or 0),
        "enemy_heal": int(troles.get("heal") or 0),
        "enemy_suicide": int(troles.get("suicide") or 0),
        "enemy_air": int(ph.get("enemy_air") or 0),
        "tick_frac": round(tick_frac, 3),
    }


def _cond_ok(value: Any, want: Any) -> bool:
    if isinstance(want, dict):
        return all(op in OPS and isinstance(value, (int, float)) and OPS[op](value, b) for op, b in want.items())
    if isinstance(want, list):
        return value in want
    return value == want


def matches(when: Dict[str, Any], feats: Dict[str, Any]) -> bool:
    return all(_cond_ok(feats.get(k), v) for k, v in (when or {}).items())


def validate(prog: Any) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Return (clean program, errors). Unknown features/exams/picks are errors."""
    errs: List[str] = []
    if not isinstance(prog, dict):
        return None, ["program is not an object"]
    rules = prog.get("rules") or []
    if not isinstance(rules, list):
        return None, ["rules is not a list"]

    def check_set(where: str, st: Any) -> Dict[str, str]:
        out: Dict[str, str] = {}
        if not isinstance(st, dict):
            errs.append(f"{where}: set is not an object")
            return out
        for kind, pick in st.items():
            if kind not in SETTABLE:
                errs.append(f"{where}: unknown exam {kind!r}")
            elif pick not in SETTABLE[kind]:
                errs.append(f"{where}: {kind}={pick!r} not in {SETTABLE[kind]}")
            else:
                out[kind] = pick
        return out

    def check_when(where: str, when: Any) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if not isinstance(when, dict):
            errs.append(f"{where}: when is not an object")
            return out
        for feat, want in when.items():
            allowed = FEATURES.get(feat)
            if allowed is None:
                errs.append(f"{where}: unknown feature {feat!r}")
            elif allowed == "num":
                if isinstance(want, dict):
                    if not want or any(op not in OPS or not isinstance(b, (int, float)) for op, b in want.items()):
                        errs.append(f"{where}: bad numeric test on {feat}")
                        continue
                elif not isinstance(want, (int, float)) or isinstance(want, bool):
                    errs.append(f"{where}: {feat} needs a number or {{op: number}}")
                    continue
                out[feat] = want
            else:
                vals = want if isinstance(want, list) else [want]
                bad = [v for v in vals if v not in allowed]
                if bad:
                    errs.append(f"{where}: {feat}={bad} not in {allowed}")
                else:
                    out[feat] = want
        return out

    clean_rules = []
    for i, r in enumerate(rules[:12]):
        if not isinstance(r, dict):
            errs.append(f"rule {i}: not an object")
            continue
        clean_rules.append({"when": check_when(f"rule {i}", r.get("when") or {}), "set": check_set(f"rule {i}", r.get("set") or {})})
    clean = {
        "name": str(prog.get("name") or "unnamed")[:60],
        "rules": clean_rules,
        "else": check_set("else", prog.get("else") or {}),
    }
    if prog.get("why"):
        clean["why"] = str(prog["why"])[:300]
    return clean, errs


def settings_for(prog: Dict[str, Any], feats: Dict[str, Any]) -> Dict[str, str]:
    out = dict(prog.get("else") or {})
    for r in prog.get("rules") or []:
        if matches(r.get("when") or {}, feats):
            out.update(r.get("set") or {})
            break
    return out


class ProgramClient:
    """Answers every exam from a program; unset exams take the code default."""

    def __init__(self, prog: Dict[str, Any]):
        self.prog = prog
        self.defaults: Dict[str, str] = {}
        self.n_calls = 0
        self.infer_s = 0.0
        self.last_usage: Dict[str, int] = {}
        self.rule_hits: Dict[str, int] = {}

    def system_one(self, state: Any, questions: Dict[str, Any]) -> Optional[dict]:
        self.n_calls += 1
        want = settings_for(self.prog, features(state or {}))
        answers: Dict[str, Any] = {}
        for kind, q in questions.items():
            opts = list((q or {}).get("criteria") or {})
            pick = want.get(kind)
            if kind == "tie" and pick in ("first", "second") and len(opts) == 2:
                pick = opts[0] if pick == "first" else opts[1]
            if pick not in opts:
                pick = self.defaults.get(kind)
            if pick in opts:
                answers[kind] = {"choice": pick}
                self.rule_hits[f"{kind}={pick}"] = self.rule_hits.get(f"{kind}={pick}", 0) + 1
        return {"answers": answers}


def describe() -> str:
    """DSL reference handed to the program writer."""
    return json.dumps({"features": FEATURES, "settable": SETTABLE, "ops": list(OPS)}, ensure_ascii=False)


# Best hand-written program on the 23 official maps (92/115). The Force-era
# fifth rule, target=guns, loses 2s3z 5/5 once it holds every tick.
HAND_RULES = {
    "name": "hand_rules",
    "rules": [],
    "else": {"ranged": "stutter", "melee": "hold_choke", "bar": "bar", "wing": "step"},
}
