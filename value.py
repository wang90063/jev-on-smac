"""Value model: predicted advantage of each macro over the default, from physics only.

Labels come from offline rollouts (search.py rollout): at a state the base
policy B reached, each action runs for 5 steps and then B plays to the end.
The model sees only physical features, so online play never clones state.

    python value.py train      # fit on results/search/rollout_train.json, grouped CV report
"""

from __future__ import annotations

import json
import os
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("JEV_QUIET", "1")

MODEL_PATH = ROOT / "kb" / "library" / "value_model.pkl"
DATA_PATHS = [ROOT / "results" / "search" / "rollout_train.json"]


def _actions() -> List[str]:
    import search as SE

    return list(SE.MACROS)


def featurize(snap: Dict[str, Any], state: Dict[str, Any], start_ehp: Optional[Tuple[float, float]]) -> List[float]:
    """Coarse DSL features plus continuous physical quantities. No map name."""
    import jev_smac_policy as J
    import tactic_dsl as T

    allies = [a for a in J.living(snap["allies"])]
    enemies = [e for e in J.living(snap["enemies"])]
    a0, e0 = start_ehp or (1.0, 1.0)
    a_ehp = sum(J._ehp(a) for a in allies)
    e_ehp = sum(J._ehp(e) for e in enemies)

    def dps(units):
        return sum(float(u.get("dmg") or 0) * max(1, int(u.get("attacks") or 1)) / max(float(u.get("max_cd") or 0.86), 0.1) for u in units)

    if allies and enemies:
        ax, ay = J._centroid(allies)
        ex, ey = J._centroid(enemies)
        dist = ((ax - ex) ** 2 + (ay - ey) ** 2) ** 0.5
        reach = np.mean([float(a.get("range") or 1) for a in allies])
        eng_a = np.mean([any(J.hypot(a, e) <= J._weapon_reach(a, e) + 1 for e in enemies) for a in allies])
        eng_e = np.mean([any(J.hypot(e, a) <= J._weapon_reach(e, a) + 1 for a in allies) for e in enemies])
        spread_a = np.mean([J.hypot(a, {"x": ax, "y": ay}) for a in allies])
    else:
        dist = reach = eng_a = eng_e = spread_a = 0.0
    extra = [
        a_ehp / max(a0, 1.0), e_ehp / max(e0, 1.0), a_ehp / max(e_ehp, 1.0),
        dps(allies) / max(dps(enemies), 1e-3), dist / max(reach, 0.5),
        float(eng_a), float(eng_e), float(spread_a), float(len(allies)), float(len(enemies)),
    ]
    return T.feature_vector(T.features(state)) + extra


def army_distance(snap: Dict[str, Any]) -> float:
    import jev_smac_policy as J

    allies, enemies = J.living(snap["allies"]), J.living(snap["enemies"])
    if not allies or not enemies:
        return 0.0
    ax, ay = J._centroid(allies)
    ex, ey = J._centroid(enemies)
    return float(((ax - ex) ** 2 + (ay - ey) ** 2) ** 0.5)


def featurize_ext(snap: Dict[str, Any], last_dist: Optional[float]) -> List[float]:
    """Round-8 extra physics: per-role health, speed/range mix, wounded share, closing speed."""
    import jev_smac_policy as J

    def full(u):
        return float(u.get("max_hp") or 1) + float(u.get("max_shield") or 0)

    def role_frac(units, role):
        us = [u for u in units if u.get("role") == role]
        return sum(J._ehp(u) for u in us) / max(sum(full(u) for u in us), 1.0) if us else 0.0

    out: List[float] = []
    for side in ("allies", "enemies"):
        units = J.living(snap[side])
        out += [role_frac(units, r) for r in ("ranged", "melee", "heal")]
        out += [
            float(sum(1 for u in units if float(u.get("speed") or 0) >= 4.0)),
            float(sum(1 for u in units if float(u.get("speed") or 0) < 4.0)),
            float(sum(1 for u in units if float(u.get("range") or 0) >= 5.5)),
            float(sum(1 for u in units if 0 < float(u.get("range") or 0) < 5.5)),
            sum(1 for u in units if J._ehp(u) < 0.4 * full(u)) / max(len(units), 1),
        ]
    d = army_distance(snap)
    out.append(0.0 if last_dist is None else d - last_dist)
    return out


def _x(d: Dict[str, Any], ext: bool) -> List[float]:
    return d["x"] + (d.get("x_ext") or [0.0] * 17 if ext else [])


def _rows(data: List[Dict[str, Any]], actions: List[str], target: str = "adv", ext: bool = False):
    """One row per (decision point, action). target=adv: y = Q(a) - Q(default);
    target=q: y = Q(a), with "default" as its own action."""
    acts = actions if target == "adv" else actions + ["default"]
    X, y, g, n_feat = [], [], [], None
    for ep in data:
        for d in ep["points"]:
            q = d["q"]
            x = _x(d, ext)
            for i, a in enumerate(acts):
                onehot = [0.0] * len(acts)
                onehot[i] = 1.0
                X.append(x + onehot)
                y.append(q[a] - q["default"] if target == "adv" else q[a])
                g.append(ep["id"])
            n_feat = len(x)
    return np.array(X), np.array(y), np.array(g), n_feat


def predict_advantages(model: Dict[str, Any], x: List[float]) -> Dict[str, float]:
    acts = model["actions"]
    target = model.get("target", "adv")
    cols = acts if target == "adv" else acts + ["default"]
    rows = []
    for i in range(len(cols)):
        onehot = [0.0] * len(cols)
        onehot[i] = 1.0
        rows.append(list(x) + onehot)
    pred = model["reg"].predict(np.array(rows))
    if target == "adv":
        return {a: float(p) for a, p in zip(acts, pred)}
    base = float(pred[-1])
    return {a: float(p) - base for a, p in zip(acts, pred[:-1])}


def load_model() -> Dict[str, Any]:
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


def _load(paths) -> List[Dict[str, Any]]:
    data = []
    for p in paths:
        if Path(p).is_file():
            data += json.loads(Path(p).read_text())
    return data


def _fit(X, y, depth: int = 4, leaf: int = 40):
    from sklearn.ensemble import HistGradientBoostingRegressor

    return HistGradientBoostingRegressor(max_depth=depth, learning_rate=0.05, max_iter=300,
                                         min_samples_leaf=leaf, l2_regularization=1.0).fit(X, y)


TAUS = (0.05, 0.1, 0.15, 0.2)


def cv_gain(data, target="adv", ext=False, depth=4, leaf=40, folds=5) -> Tuple[Dict[float, float], float]:
    """Grouped CV (by fight): realised advantage of following the model at each tau."""
    from sklearn.model_selection import GroupKFold

    actions = _actions()
    X, y, g, _ = _rows(data, actions, target, ext)
    nc = len(actions) + (0 if target == "adv" else 1)
    gain = {t: 0.0 for t in TAUS}
    oracle = 0.0
    for tr, te in GroupKFold(n_splits=folds).split(X, y, g):
        reg = _fit(X[tr], y[tr], depth, leaf)
        p = reg.predict(X[te]).reshape(-1, nc)
        truth = y[te].reshape(-1, nc)
        if target == "q":
            p = p[:, :-1] - p[:, -1:]
            truth = truth[:, :-1] - truth[:, -1:]
        oracle += np.maximum(truth.max(1), 0).sum()
        pick = p.argmax(1)
        for t in TAUS:
            gain[t] += (truth[np.arange(len(pick)), pick] * (p.max(1) > t)).sum()
    return gain, oracle


def cmd_cv(paths) -> None:
    """Compare target form, features and tree size by grouped CV; train only."""
    data = _load(paths)
    has_ext = [e for e in data if e["points"] and "x_ext" in e["points"][0]]
    print(f"{len(data)} episodes ({len(has_ext)} with extended features)")
    for name, sub, kw in (
        ("adv  base d4 l40", data, dict(target="adv")),
        ("q    base d4 l40", data, dict(target="q")),
        ("adv  base d3 l80", data, dict(target="adv", depth=3, leaf=80)),
        ("adv  base d6 l20", data, dict(target="adv", depth=6, leaf=20)),
        ("adv  base (ext-subset)", has_ext, dict(target="adv")),
        ("adv  ext  (ext-subset)", has_ext, dict(target="adv", ext=True)),
    ):
        if len({e["id"] for e in sub}) < 5:
            continue
        gain, oracle = cv_gain(sub, **kw)
        best = max(gain, key=gain.get)
        print(f"{name:24s} oracle {oracle:7.1f}  " + "  ".join(f"t{t}:{gain[t]:+6.1f}" for t in TAUS)
              + f"  best {gain[best] / max(oracle, 1e-9):.1%}", flush=True)


def cmd_train(paths=None, target: str = "adv", ext: bool = False, depth: int = 4, leaf: int = 40) -> None:
    actions = _actions()
    data = _load(paths or DATA_PATHS)
    if ext:
        data = [e for e in data if e["points"] and "x_ext" in e["points"][0]] or data
    X, y, g, n_feat = _rows(data, actions, target, ext)
    gain, oracle = cv_gain(data, target, ext, depth, leaf)
    print(f"{len(data)} episodes, {n_feat} features; CV oracle {oracle:.1f}; " + ", ".join(f"tau={t}: {gain[t]:+.1f}" for t in TAUS))
    reg = _fit(X, y, depth, leaf)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"reg": reg, "actions": actions, "n_feat": n_feat, "target": target, "ext": ext,
                     "depth": depth, "leaf": leaf,
                     "features": "tactic_dsl.feature_vector + value.featurize extras" + (" + featurize_ext" if ext else "")}, f)
    print("wrote", MODEL_PATH)


if __name__ == "__main__":
    if sys.argv[1:2] == ["train"]:
        cmd_train([Path(p) for p in sys.argv[2:]] or None)
    elif sys.argv[1:2] == ["cv"]:
        cmd_cv([Path(p) for p in sys.argv[2:]])
    else:
        print(__doc__)
