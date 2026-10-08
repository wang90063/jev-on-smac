#!/usr/bin/env python3
"""Probe whether SMAClite maps are winnable with explicit micro, no LLM."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "smaclite"))

import numpy as np
from eval_smac import MAPS, make_env, snapshot, heuristic_act
from smac_laya_policy import (
    attack_action,
    hypot,
    labels_from_avail,
    living,
    move_away_action,
    move_toward_action,
)


def shots_on(snap, ally, eid):
    labels = labels_from_avail(snap["avail"][ally["id"]], snap["n_enemies"])
    return attack_action(labels, eid)


def n_guns(snap, allies, eid):
    return sum(1 for a in allies if shots_on(snap, a, eid) is not None)


def pick_focus(snap, allies, enemies, sticky):
    ids = {e["id"] for e in enemies}

    def score(e):
        return (-n_guns(snap, allies, e["id"]), e["hp"] + e.get("shield", 0), e["id"])

    best = min(enemies, key=score)
    if sticky in ids:
        cur = next(e for e in enemies if e["id"] == sticky)
        if n_guns(snap, allies, sticky) + 1 >= n_guns(snap, allies, best["id"]):
            return sticky
    return best["id"]


def walk_or_stop(ally, target, labels, away=False):
    if away:
        return move_away_action(ally, target, labels)
    return move_toward_action(ally, target, labels)


class Oracle:
    def __init__(self, style="auto"):
        self.style = style
        self.focus = None
        self.tank = None
        self.n_calls = 0

    def act(self, map_name, step, snap):
        self.n_calls += 1
        if step == 0:
            self.focus = None
            self.tank = None
        allies = living(snap["allies"])
        enemies = living(snap["enemies"])
        n = snap["n_agents"]
        if not enemies:
            return [0 if not a.get("alive") else 1 for a in snap["allies"]]
        static_e = [e for e in enemies if e.get("role") == "static"]
        melee_e = [e for e in enemies if e.get("role") == "melee"]
        ranged_a = [a for a in allies if a.get("role") == "ranged"]
        melee_a = [a for a in allies if a.get("role") == "melee"]
        if self.style == "closest":
            return heuristic_act(snap, "closest")
        if self.style == "focus":
            return heuristic_act(snap, "focus")
        # auto
        if len(ranged_a) == 2 and len(allies) == 2 and len(static_e) == 1 and not melee_a:
            return self.alt_static(snap, allies, static_e[0])
        if ranged_a and melee_e and not melee_a and len(ranged_a) == len(allies):
            return self.kite(snap, allies, enemies, melee_e)
        if melee_a and melee_e and len(enemies) >= 2 * max(1, len(allies)):
            return self.choke(snap, allies, enemies)
        return self.focus_ball(snap, allies, enemies)

    def alt_static(self, snap, allies, target):
        in_range = []
        for a in allies:
            if shots_on(snap, a, target["id"]) is not None:
                in_range.append(a)
        # pick tank: higher ehp unless current tank is still ok
        def ehp(u):
            return u["hp"] + u.get("shield", 0)

        alive_ids = {a["id"] for a in allies}
        if self.tank not in alive_ids:
            self.tank = max(allies, key=ehp)["id"]
        # swap if tank is much weaker
        other = [a for a in allies if a["id"] != self.tank]
        tank = next(a for a in allies if a["id"] == self.tank)
        if other and ehp(tank) + 25 < ehp(other[0]):
            self.tank = other[0]["id"]
            tank = other[0]
        actions = []
        for i, ally in enumerate(snap["allies"]):
            labels = labels_from_avail(snap["avail"][i], snap["n_enemies"])
            if not ally.get("alive"):
                actions.append(0)
                continue
            can = shots_on(snap, ally, target["id"])
            is_tank = ally["id"] == self.tank
            if is_tank:
                if can is not None and ally["cd"] <= 0.08:
                    actions.append(can)
                elif can is not None and ehp(ally) < 50:
                    actions.append(move_away_action(ally, target, labels))
                elif can is not None:
                    # in range on CD: kite out so spine wastes cooldown
                    actions.append(move_away_action(ally, target, labels))
                else:
                    actions.append(move_toward_action(ally, target, labels))
            else:
                # stay out unless tank is dead/low and we must take over
                if ehp(tank) < 40 and (can is None):
                    actions.append(move_toward_action(ally, target, labels))
                elif can is not None:
                    actions.append(move_away_action(ally, target, labels))
                else:
                    # hold if already out
                    actions.append(next((a for a, lab in labels if lab == "stop"), labels[0][0]))
        return actions

    def kite(self, snap, allies, enemies, melee_e):
        focus = pick_focus(snap, allies, enemies, self.focus)
        self.focus = focus
        foc = next(e for e in enemies if e["id"] == focus)
        actions = []
        for i, ally in enumerate(snap["allies"]):
            labels = labels_from_avail(snap["avail"][i], snap["n_enemies"])
            if not ally.get("alive"):
                actions.append(0)
                continue
            nearest_m = min(melee_e, key=lambda e: hypot(ally, e))
            d = hypot(ally, nearest_m)
            shot = shots_on(snap, ally, focus)
            shot_any = []
            for e in enemies:
                s = shots_on(snap, ally, e["id"])
                if s is not None:
                    shot_any.append((e, s))
            # shoot if ready and in range; else run from melee
            if ally["cd"] <= 0.08 and shot is not None:
                actions.append(shot)
            elif ally["cd"] <= 0.08 and shot_any:
                e, s = min(shot_any, key=lambda p: p[0]["hp"] + p[0].get("shield", 0))
                actions.append(s)
            elif d < 5.5:
                actions.append(move_away_action(ally, nearest_m, labels))
            elif shot is None:
                actions.append(move_toward_action(ally, foc, labels))
            else:
                actions.append(move_away_action(ally, nearest_m, labels))
        return actions

    def choke(self, snap, allies, enemies):
        # retreat toward bottom-left (corridor attack point region), then fight
        cx = float(np.mean([a["x"] for a in allies]))
        cy = float(np.mean([a["y"] for a in allies]))
        nearest = min(enemies, key=lambda e: (e["x"] - cx) ** 2 + (e["y"] - cy) ** 2)
        focus = pick_focus(snap, allies, enemies, self.focus)
        self.focus = focus
        foc = next(e for e in enemies if e["id"] == focus)
        # if zerglings not yet in melee, keep walking SW
        min_d = min(hypot(a, nearest) for a in allies)
        actions = []
        for i, ally in enumerate(snap["allies"]):
            labels = labels_from_avail(snap["avail"][i], snap["n_enemies"])
            if not ally.get("alive"):
                actions.append(0)
                continue
            shot = shots_on(snap, ally, focus)
            if shot is not None:
                actions.append(shot)
                continue
            shot_any = None
            for e in enemies:
                s = shots_on(snap, ally, e["id"])
                if s is not None:
                    shot_any = s
                    break
            if shot_any is not None:
                actions.append(shot_any)
                continue
            if min_d > 3.5:
                # walk toward smaller x,y (corridor mouth)
                dummy = {"x": 5.0, "y": 5.0}
                actions.append(move_toward_action(ally, dummy, labels))
            else:
                actions.append(move_toward_action(ally, foc, labels))
        return actions

    def focus_ball(self, snap, allies, enemies):
        focus = pick_focus(snap, allies, enemies, self.focus)
        self.focus = focus
        foc = next(e for e in enemies if e["id"] == focus)
        guns = n_guns(snap, allies, focus)
        nA, nE = len(allies), len(enemies)
        need = min(nA, 4 if nA <= 6 else max(4, int(0.7 * nA)))
        outnumbered = nA < nE
        formed = guns >= need or guns == nA
        actions = []
        for i, ally in enumerate(snap["allies"]):
            labels = labels_from_avail(snap["avail"][i], snap["n_enemies"])
            if not ally.get("alive"):
                actions.append(0)
                continue
            if ally.get("role") == "heal":
                needy = [a for a in allies if a["id"] != ally["id"] and a["hp"] < a["max_hp"] - 5]
                if needy:
                    tgt = min(needy, key=lambda a: a["hp"] / max(a["max_hp"], 1))
                    want = 6 + tgt["id"]
                    if want < len(snap["avail"][i]) and snap["avail"][i][want]:
                        actions.append(want)
                        continue
                    actions.append(move_toward_action(ally, tgt, labels))
                else:
                    tgt = min(allies, key=lambda a: a["hp"] / max(a["max_hp"], 1))
                    actions.append(move_toward_action(ally, tgt, labels))
                continue
            shot = shots_on(snap, ally, focus)
            if not formed:
                if shot is not None:
                    # wait for ball: kite back so backline catches up
                    actions.append(move_away_action(ally, foc, labels))
                else:
                    actions.append(move_toward_action(ally, foc, labels))
                continue
            if shot is not None:
                if outnumbered and ally["cd"] > 0.20:
                    actions.append(move_away_action(ally, foc, labels))
                else:
                    actions.append(shot)
                continue
            # cannot shoot focus: shoot anyone else rather than walk past
            other = []
            for e in enemies:
                s = shots_on(snap, ally, e["id"])
                if s is not None:
                    other.append((e, s))
            if other:
                e, s = min(other, key=lambda p: (p[0]["hp"] + p[0].get("shield", 0), p[0]["id"]))
                actions.append(s)
            else:
                actions.append(move_toward_action(ally, foc, labels))
        return actions


def run(map_name, style, n=2, seed=0):
    pol = Oracle(style)
    wins = 0
    rets = []
    steps = []
    for ep in range(n):
        env = make_env(map_name, seed=seed + 1000 * ep + sum(map(ord, map_name)))
        obs, info = env.reset()
        done = truncated = False
        ret = 0.0
        t = 0
        pol.focus = None
        pol.tank = None
        while not done and not truncated:
            snap = snapshot(env)
            actions = pol.act(map_name, t, snap)
            obs, reward, done, truncated, info = env.step(actions)
            ret += float(reward)
            t += 1
        won = bool(info.get("battle_won")) and done and not truncated
        wins += int(won)
        rets.append(ret)
        steps.append(t)
        env.close()
        print(f"  {map_name:16s} {style:10s} ep{ep} win={int(won)} ret={ret:.2f} steps={t}", flush=True)
    print(f"SUMMARY {map_name} {style}: wr={wins}/{n} ret={np.mean(rets):.2f} steps={np.mean(steps):.1f}", flush=True)
    return wins


def main():
    maps = [
        "3m",
        "8m",
        "5m_vs_6m",
        "2s3z",
        "2s_vs_1sc",
        "3s_vs_5z",
        "MMM",
        "3s5z",
        "10m_vs_11m",
        "corridor",
        "MMM2",
        "3s5z_vs_3s6z",
        "27m_vs_30m",
    ]
    styles = ["auto"]
    for m in maps:
        if m not in MAPS:
            print("skip", m)
            continue
        for s in styles:
            run(m, s, n=2)


if __name__ == "__main__":
    main()
