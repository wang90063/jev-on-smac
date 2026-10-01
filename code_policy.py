"""Policies written as code by the program writer (Grok), run in a small sandbox.

The writer supplies `def act(obs, mem): -> {unit_id: action}` which is called
every step. Units it leaves out, or gives an illegal action, take
default_action(u): the current online default's action for that unit. So a
program that returns nothing plays exactly like the online default, and every
written line is an override on top of it.

Actions: 0 no-op, 1 stop, 2 north (+y), 3 south (-y), 4 east (+x), 5 west (-x),
6 + i attack enemy i (a healer heals ally i instead).
"""

from __future__ import annotations

import math
import signal
from typing import Any, Callable, Dict, List, Optional

STEP_TIMEOUT_S = 0.5
BANNED = ("import", "__", "open(", "exec(", "eval(", "compile(", "globals(", "locals(", "getattr(", "setattr(", "delattr(")
SAFE_BUILTINS = {
    k: __builtins__[k] if isinstance(__builtins__, dict) else getattr(__builtins__, k)
    for k in ("abs", "min", "max", "sum", "len", "range", "enumerate", "zip", "sorted", "list", "dict", "set",
              "tuple", "float", "int", "bool", "any", "all", "round", "isinstance", "map", "filter", "reversed",
              "str", "ValueError", "KeyError", "Exception")
}

DIRS = {2: (0.0, 1.0), 3: (0.0, -1.0), 4: (1.0, 0.0), 5: (-1.0, 0.0)}


class Unit(dict):
    """A unit as a dict that also allows attribute access (u.x or u['x'])."""

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as exc:
            raise AttributeError(k) from exc


def _unit(d: Dict[str, Any]) -> Unit:
    return Unit(
        id=d["id"], kind=d.get("name"), role=d.get("role"), x=float(d["x"]), y=float(d["y"]),
        hp=float(d["hp"]), max_hp=float(d["max_hp"]), shield=float(d.get("shield") or 0),
        max_shield=float(d.get("max_shield") or 0), cooldown=float(d.get("cd") or 0),
        max_cooldown=float(d.get("max_cd") or 0), range=float(d.get("range") or 0), speed=float(d.get("speed") or 0),
        radius=float(d.get("radius") or 0.4), damage=float(d.get("dmg") or 0), attacks=int(d.get("attacks") or 1),
        armor=float(d.get("armor") or 0), suicide=bool(d.get("kamikaze")), splash=bool(d.get("splash")),
    )


def check_source(src: str) -> Optional[str]:
    for b in BANNED:
        if b in src:
            return f"forbidden token {b!r}"
    if "def act" not in src:
        return "no `def act(obs, mem)`"
    return None


class _Timeout(Exception):
    pass


def _alarm(_sig, _frm):
    raise _Timeout()


class CodeActionPolicy:
    """Run a written program; fall back per unit to the online default."""

    def __init__(self, source: str, tag: str = "code", base=None):
        import jev_smac_policy as J

        self.tag = tag
        self.source = source
        self.base = base if base is not None else J.ValueOnlinePolicy(tag="code_base")
        self.errors = 0
        self.steps = 0
        self.overrides = 0
        self.last_error = ""
        self.mem: Dict[str, Any] = {}
        self._fn: Optional[Callable] = None
        err = check_source(source)
        if err:
            self.last_error = err
            return
        env: Dict[str, Any] = {"__builtins__": SAFE_BUILTINS, "math": math}
        try:
            exec(compile(source, "<program>", "exec"), env)  # noqa: S102 - sandboxed writer code
            self._fn = env.get("act")
        except Exception as exc:  # syntax or definition error
            self.last_error = f"{type(exc).__name__}: {exc}"

    # ---- helpers handed to the program ----
    def _helpers(self, snap: Dict[str, Any], base_actions: List[int]):
        avail = snap["avail"]

        def legal(u):
            row = avail[u["id"]]
            return [a for a, ok in enumerate(row) if ok]

        def dist(a, b):
            return math.hypot(a["x"] - b["x"], a["y"] - b["y"])

        def attack(u, e):
            return 6 + int(e["id"])

        def heal(u, ally):
            return 6 + int(ally["id"])

        def can_attack(u, e):
            row = avail[u["id"]]
            k = 6 + int(e["id"])
            return k < len(row) and bool(row[k])

        def _step(u, x, y, sign):
            best, best_d = None, None
            for a, (dx, dy) in DIRS.items():
                if not avail[u["id"]][a]:
                    continue
                d = math.hypot(u["x"] + 2 * dx - x, u["y"] + 2 * dy - y)
                if best is None or (sign * d) < (sign * best_d):
                    best, best_d = a, d
            return best if best is not None else 1

        def move_toward(u, x, y):
            return _step(u, x, y, +1)

        def move_away(u, x, y):
            return _step(u, x, y, -1)

        def stop(u):
            return 1

        def default_action(u):
            return base_actions[u["id"]]

        return dict(legal=legal, dist=dist, attack=attack, heal=heal, can_attack=can_attack,
                    move_toward=move_toward, move_away=move_away, stop=stop, default_action=default_action)

    def act(self, map_name: str, step: int, snap: Dict[str, Any]) -> List[int]:
        base_actions = list(self.base.act(map_name, step, snap))
        if step == 0:
            self.mem = {}
        if self._fn is None:
            self.errors += 1
            self.steps += 1
            return base_actions
        allies = [_unit(a) for a in snap["allies"] if a.get("alive")]
        enemies = [_unit(e) for e in snap["enemies"] if e.get("alive")]
        obs = Unit(allies=allies, enemies=enemies, step=step, limit=snap.get("limit"),
                   width=snap.get("width"), height=snap.get("height"), rally=tuple(snap.get("attack_point") or (16, 16)),
                   walkable=snap.get("walkable"))
        helpers = self._helpers(snap, base_actions)
        g = self._fn.__globals__
        g.update(helpers)
        self.steps += 1
        prev = signal.signal(signal.SIGALRM, _alarm)
        signal.setitimer(signal.ITIMER_REAL, STEP_TIMEOUT_S)
        try:
            out = self._fn(obs, self.mem) or {}
        except Exception as exc:  # includes _Timeout
            self.errors += 1
            self.last_error = f"step {step}: {type(exc).__name__}: {str(exc)[:160]}"
            return base_actions
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, prev)
        actions = list(base_actions)
        if not isinstance(out, dict):
            return actions
        avail = snap["avail"]
        alive = {a["id"] for a in allies}
        for uid, a in out.items():
            try:
                uid, a = int(uid), int(a)
            except (TypeError, ValueError):
                continue
            if uid in alive and 0 <= a < len(avail[uid]) and avail[uid][a] and a != actions[uid]:
                actions[uid] = a
                self.overrides += 1
        return actions

    @property
    def error_rate(self) -> float:
        return self.errors / max(self.steps, 1)


API_DOC = """
Write Python: def act(obs, mem): return {unit_id: action_int}. Called every step (one step ~ a fraction of a second).
No imports; `math` is available. Units you omit, or give an illegal action, keep default_action(u), which is a solid
existing policy (nearest-cluster tactic program plus a learned switch). Override only where you have a clear idea.

obs.allies / obs.enemies: living units with fields id, kind, role ('ranged'|'melee'|'heal'|'static'), x, y, hp, max_hp,
shield, max_shield, cooldown (seconds until next shot; 0 = ready), max_cooldown, range, speed, radius, damage, attacks,
armor, suicide (bool, e.g. baneling), splash (bool). Also obs.step, obs.limit, obs.width, obs.height, obs.rally (x, y),
obs.walkable (grid[y][x], 1 = walkable). mem is a dict kept for the whole episode.

Helpers: dist(a, b); legal(u) -> list of legal actions; can_attack(u, e); attack(u, e); heal(u, ally);
move_toward(u, x, y); move_away(u, x, y); stop(u); default_action(u).
Actions: 0 no-op, 1 stop, 2 north (+y), 3 south (-y), 4 east (+x), 5 west (-x), 6 + i attack enemy i (healers: heal ally i).
A unit can attack only when the enemy is in range (can_attack). A move takes the unit ~2 cells. Win = every enemy dead
before obs.limit steps; timing out is a loss.
"""
