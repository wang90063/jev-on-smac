"""One central commander. Role-aware micro using pairwise SMAC masks. No LLM."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from smac_laya_policy import (
    attack_action,
    execute_alternating,
    hypot,
    labels_from_avail,
    living,
    move_away_action,
    move_toward_action,
)


class CentralMicro:
    def __init__(self):
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
        allies = living(snap["allies"])
        enemies = living(snap["enemies"])
        n = snap["n_agents"]
        if not enemies:
            return [0 if not a.get("alive") else 1 for a in snap["allies"]]

        static_e = [e for e in enemies if e.get("role") == "static"]
        melee_e = [e for e in enemies if e.get("role") == "melee"]
        ranged_a = [a for a in allies if a.get("role") == "ranged"]
        melee_a = [a for a in allies if a.get("role") == "melee"]

        # 2 ranged vs 1 static: only one unit occupies shoot range at a time.
        if len(ranged_a) == 2 and len(allies) == 2 and len(static_e) == 1 and not melee_a:
            self.tactic_counts["alternate"] = self.tactic_counts.get("alternate", 0) + 1
            return self._alternate_static(snap, allies, static_e[0])

        focus = self._pick_focus(snap, allies, enemies)
        self._focus = focus
        self.tactic_counts["focus"] = self.tactic_counts.get("focus", 0) + 1

        actions = []
        for i, ally in enumerate(snap["allies"]):
            labels = labels_from_avail(snap["avail"][i], snap["n_enemies"])
            if not ally.get("alive"):
                actions.append(0)
                continue
            if ally.get("role") == "heal":
                actions.append(self._heal_or_follow(ally, labels, snap))
                continue
            actions.append(self._damage_act(ally, labels, snap, enemies, focus, melee_e, melee_a))
        return actions

    def _shots_on(self, snap, allies, enemy_id: int) -> int:
        n = 0
        for a in allies:
            labels = labels_from_avail(snap["avail"][a["id"]], snap["n_enemies"])
            if attack_action(labels, enemy_id) is not None:
                n += 1
        return n

    def _pick_focus(self, snap, allies, enemies) -> int:
        ids = {e["id"] for e in enemies}

        def score(e):
            return (-self._shots_on(snap, allies, e["id"]), e["hp"] + e.get("shield", 0), e["id"])

        best_id = min(enemies, key=score)["id"]
        if self._focus in ids:
            cur_n = self._shots_on(snap, allies, self._focus)
            best_n = self._shots_on(snap, allies, best_id)
            if best_n >= cur_n + 2:
                return best_id
            return self._focus
        return best_id

    @staticmethod
    def _in_shot_enemies(snap, allies, enemies):
        out = []
        for e in enemies:
            for a in allies:
                labels = labels_from_avail(snap["avail"][a["id"]], snap["n_enemies"])
                if attack_action(labels, e["id"]) is not None:
                    out.append(e)
                    break
        return out

    def _alternate_static(self, snap, allies, target) -> List[int]:
        in_range = []
        for a in allies:
            labels = labels_from_avail(snap["avail"][a["id"]], snap["n_enemies"])
            if attack_action(labels, target["id"]) is not None:
                in_range.append(a)
        ready = [a for a in in_range if a["cd"] <= 0.08]
        shooter = max(ready, key=lambda a: a["hp"]) if ready else None
        actions = []
        for i, ally in enumerate(snap["allies"]):
            labels = labels_from_avail(snap["avail"][i], snap["n_enemies"])
            if not ally.get("alive"):
                actions.append(0)
                continue
            can = attack_action(labels, target["id"])
            if can is not None:
                if shooter is not None and ally["id"] == shooter["id"]:
                    actions.append(can)
                else:
                    actions.append(move_away_action(ally, target, labels))
            else:
                inbound = min(allies, key=lambda a: hypot(a, target))
                if not in_range and shooter is None and ally["id"] == inbound["id"]:
                    actions.append(move_toward_action(ally, target, labels))
                else:
                    actions.append(next((a for a, lab in labels if lab == "stop"), labels[0][0]))
        return actions

    def _heal_or_follow(self, ally, labels, snap) -> int:
        # Medivac: 6+ is ally id
        living_a = living(snap["allies"])
        needy = [a for a in living_a if a["id"] != ally["id"] and a["hp"] < a["max_hp"] - 5]
        if not needy:
            # follow the most damaged / front
            if not living_a:
                return next((a for a, lab in labels if lab == "stop"), labels[0][0])
            tgt = min(living_a, key=lambda a: a["hp"] / max(a["max_hp"], 1))
            return move_toward_action(ally, tgt, labels)
        tgt = min(needy, key=lambda a: a["hp"] / max(a["max_hp"], 1))
        want = f"atkE{tgt['id']}"  # heal uses same slot index as attack-on-ally
        # For healers SMAClite uses action 6+ally_id_in_faction
        for a, lab in labels:
            if a == 6 + tgt["id"]:
                return a
        return move_toward_action(ally, tgt, labels)

    def _damage_act(self, ally, labels, snap, enemies, focus_id: int, melee_e, melee_a) -> int:
        focus = next((e for e in enemies if e["id"] == focus_id), None) or enemies[0]
        nearest = min(enemies, key=lambda e: hypot(ally, e))
        shot_focus = attack_action(labels, focus["id"])
        shot_any = []
        for e in enemies:
            s = attack_action(labels, e["id"])
            if s is not None:
                shot_any.append((e, s))

        # Kite: ranged unit vs nearby melee.
        # Pure ranged vs melee (3s_vs_5z). Mixed armies keep shooting; zealots tank.
        if ally.get("role") == "ranged" and melee_e and not melee_a:
            close_m = min(melee_e, key=lambda e: hypot(ally, e))
            d = hypot(ally, close_m)
            if d < 4.8:
                if ally["cd"] <= 0.08 and shot_any:
                    e, s = min(shot_any, key=lambda p: hypot(ally, p[0]))
                    return s
                return move_away_action(ally, close_m, labels)

        if ally.get("role") == "melee":
            if shot_any:
                e, s = min(shot_any, key=lambda p: hypot(ally, p[0]))
                return s
            return move_toward_action(ally, nearest, labels)

        # Homogeneous ranged (8m / 5v6): wait for a firing ball before committing.
        nA = sum(1 for x in snap["allies"] if x.get("alive"))
        nE = len(enemies)
        if shot_focus is not None:
            outnumbered = nA < nE
            if outnumbered and (nA <= 5 or nA >= 20) and ally["cd"] > 0.28 and not melee_e:
                return move_away_action(ally, nearest, labels)
            return shot_focus
        return move_toward_action(ally, focus, labels)
