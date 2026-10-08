"""Can Jev serve as a value model? Offline test on val ground-truth labels.

results/search/rollout_val.json holds, for decision points the online default
reached on val, the whole-episode return of each of 13 actions. Here Jev sees
the same moment (commander_state) and gives P(win) now and P(win | action) for
each action, as two-way choices with probabilities. We compare with the truth
and with the trained value model on the same points. No games are played for
scoring; the val episodes are only replayed to recover each moment's state.

    python src/jev_value.py states     # local: replay val, store states for the labelled points
    python src/jev_value.py ask        # TypeSafe API: ~300 calls
    python src/jev_value.py score      # local: compare
"""

from __future__ import annotations

import json
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("JEV_QUIET", "1")

OUT = ROOT / "results" / "jev_value"
LABELS = ROOT / "results" / "search" / "rollout_val.json"
N_SAMPLE = 300


def _replay(job) -> List[Dict[str, Any]]:
    """Re-run one val episode exactly as the labeller's driver did; return states at its decision points."""
    import jev_smac_policy as J
    import scenarios as SC
    import value as V
    from macsmac.snapshot import snapshot

    scen, seed = job
    env = SC.make_env(scen, seed)
    env.reset()
    pol = J.SwitchPolicy(model=V.load_model(), tau=0.1)
    pol.evidence = None
    s0 = snapshot(env)
    pol._start_ehp = (sum(J._ehp(a) for a in J.living(s0["allies"])), sum(J._ehp(e) for e in J.living(s0["enemies"])))
    out, step, done = [], 0, False
    while not done:
        snap = snapshot(env)
        if step % J.SwitchPolicy.DECIDE == 0 and J.living(snap["allies"]) and J.living(snap["enemies"]):
            state = J.commander_state(step, dict(snap), list(pol._recent), pol._hp_trend)
            out.append({"step": step, "state": state, "x": V.featurize(snap, state, pol._start_ehp)})
        _, done, _ = env.step(pol.act("replay", step, snap))
        step += 1
    env.close()
    return out


def cmd_states() -> None:
    import scenarios as SC

    labels = json.loads(LABELS.read_text())
    scens = {s["id"]: s for s in SC.load("val")}
    with Pool(8) as pool:
        replays = pool.map(_replay, [(scens[ep["id"]], ep["seed"]) for ep in labels], chunksize=1)
    points, mismatch = [], 0
    for ep, rep in zip(labels, replays):
        by_step = {r["step"]: r for r in rep}
        for d in ep["points"]:
            r = by_step.get(d["step"])
            if r is None or np.abs(np.array(r["x"]) - np.array(d["x"])).max() > 1e-6:
                mismatch += 1
                continue
            points.append({"id": ep["id"], "seed": ep["seed"], "step": d["step"], "x": d["x"], "q": d["q"],
                           "won": ep["win"], "state": r["state"]})
    rng = random.Random(7)
    sample = rng.sample(points, min(N_SAMPLE, len(points)))
    OUT.mkdir(parents=True, exist_ok=True)
    if not (OUT / "points.json").is_file():
        (OUT / "points.json").write_text(json.dumps(sample))
    # Second batch for round 11: disjoint from the first, same seed scheme.
    first = {(p["id"], p["seed"], p["step"]) for p in json.loads((OUT / "points.json").read_text())}
    rest = [p for p in points if (p["id"], p["seed"], p["step"]) not in first]
    batch2 = random.Random(11).sample(rest, min(N_SAMPLE, len(rest)))
    (OUT / "points2.json").write_text(json.dumps(batch2))
    print(f"{len(points)} labelled points matched their replay ({mismatch} did not); batch1 {len(first)}, batch2 {len(batch2)}")


def _describe(a: str) -> str:
    import search as SE
    import tactic_dsl as T

    if a == "default":
        return "keep running the program the army runs now (chosen by similarity to past fights)"
    prog = SE.MACROS[a]
    return "plain attack-move with default targeting" if prog is None else T.summarize(prog)


def _questions(actions: List[str]) -> Dict[str, Any]:
    two = {"win": {"does": "Our army wipes the enemy before the time limit."},
           "lose": {"does": "We are wiped, or time runs out with enemies alive."}}
    q = {"win_now": {"type": "choice", "instructions": "If our army keeps fighting the way it is now, which side wins this fight?", "criteria": two}}
    for a in actions:
        q[f"win_if_{a}"] = {
            "type": "choice",
            "instructions": f"If for the next few seconds our army does this: {_describe(a)}; and then fights on as usual, which side wins?",
            "criteria": two,
        }
    return q


def _p_win(ans: Any) -> float:
    if isinstance(ans, dict):
        probs = ans.get("probabilities") or {}
        if "win" in probs:
            return float(probs["win"])
        if ans.get("choice") in ("win", "lose"):
            return 1.0 if ans["choice"] == "win" else 0.0
    return float("nan")


def cmd_ask() -> None:
    import search as SE
    from jev_api import JevClient

    pts = json.loads((OUT / "points.json").read_text())
    actions = list(SE.MACROS) + ["default"]
    questions = _questions(actions)
    client = JevClient()

    def one(p):
        r = client.system_one(p["state"], questions)
        ans = (r or {}).get("answers") or {}
        return {"now": _p_win(ans.get("win_now")), **{a: _p_win(ans.get(f"win_if_{a}")) for a in actions}}

    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(one, pts))
    for p, r in zip(pts, res):
        p["jev"] = r
    (OUT / "answers.json").write_text(json.dumps(pts))
    print(f"asked {len(pts)} points; calls ok {client.n_calls} fail {client.n_fail}")


def _auc(score: np.ndarray, y: np.ndarray) -> float:
    pos, neg = score[y == 1], score[y == 0]
    if not len(pos) or not len(neg):
        return float("nan")
    return float(np.mean([(s > neg).mean() + 0.5 * (s == neg).mean() for s in pos]))


def cmd_score() -> None:
    import search as SE
    import value as V

    pts = [p for p in json.loads((OUT / "answers.json").read_text()) if not np.isnan(p["jev"]["now"])]
    macros = list(SE.MACROS)
    model = V.load_model()
    print(f"{len(pts)} points with answers")

    # 1. State value: does Jev's P(win now) rank outcomes?
    y = np.array([1 if p["q"]["default"] >= 0.5 else 0 for p in pts])  # win if the base policy plays on
    jev_now = np.array([p["jev"]["now"] for p in pts])
    ehp_ratio = np.array([p["x"][-8] for p in pts])  # our ehp / their ehp (value.featurize extras)
    print(f"[state value] AUC vs actual outcome: Jev P(win now) {_auc(jev_now, y):.3f}; "
          f"health ratio alone {_auc(ehp_ratio, y):.3f}; win rate {y.mean():.2f}")

    # 2. Action value: follow Jev's argmax vs the trained model's, on the same points.
    true = np.array([[p["q"][a] - p["q"]["default"] for a in macros] for p in pts])
    jadv = np.array([[p["jev"][a] - p["jev"]["default"] for a in macros] for p in pts])
    madv = np.array([[V.predict_advantages(model, p["x"])[a] for a in macros] for p in pts])
    oracle = np.maximum(true.max(1), 0).sum()

    def realised(adv, tau):
        pick = np.nanargmax(np.nan_to_num(adv, nan=-9), axis=1)
        take = np.nanmax(np.nan_to_num(adv, nan=-9), axis=1) > tau
        return float((true[np.arange(len(pick)), pick] * take).sum()), int(take.sum())

    print(f"[action value] oracle gain {oracle:.2f} over {len(pts)} points")
    for tau in (0.0, 0.05, 0.1, 0.2):
        g, n = realised(jadv, tau)
        print(f"  Jev   tau={tau:<4} gain {g:+.2f}  (departs at {n} points)")
    g, n = realised(madv, 0.1)
    print(f"  model tau=0.1  gain {g:+.2f}  (departs at {n} points)")
    flat_t, flat_j, flat_m = true.ravel(), np.nan_to_num(jadv).ravel(), madv.ravel()
    rank = lambda v: np.argsort(np.argsort(v))
    print(f"  rank correlation with true advantage: Jev {np.corrcoef(rank(flat_j), rank(flat_t))[0, 1]:.3f}, "
          f"model {np.corrcoef(rank(flat_m), rank(flat_t))[0, 1]:.3f}")
    print(f"  Jev answer spread: P(win|action) std across actions, mean over points {np.nanmean(np.nanstd(np.array([[p['jev'][a] for a in macros] for p in pts]), axis=1)):.3f}")

    # 3. Does Jev add information beyond the model? Grouped CV within these points.
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import GroupKFold

    groups = np.repeat([p["id"] for p in pts], len(macros))
    feats_m = flat_m.reshape(-1, 1)
    feats_mj = np.column_stack([flat_m, flat_j])
    for name, F in (("model only", feats_m), ("model + Jev", feats_mj)):
        pred = np.zeros_like(flat_t)
        for tr, te in GroupKFold(n_splits=5).split(F, flat_t, groups):
            pred[te] = Ridge(alpha=1.0).fit(F[tr], flat_t[tr]).predict(F[te])
        p2 = pred.reshape(-1, len(macros))
        pick = p2.argmax(1)
        best = [(true[np.arange(len(pick)), pick] * (p2.max(1) > t)).sum() for t in (0.0, 0.05, 0.1)]
        print(f"  [stacking] {name:12s} realised gain at tau 0/0.05/0.1: " + " / ".join(f"{b:+.2f}" for b in best))


# --- in-context learning: the 8 most similar training moments, with true results ---

K_EXAMPLES = 8
TRAIN_FILES = ["rollout_train.json", "rollout_train_dagger.json", "rollout_train2_B.json", "rollout_train2_dagger.json"]
EXTRA_NAMES = ["our_health_left", "their_health_left", "health_ratio_us_vs_them", "dps_ratio_us_vs_them",
               "distance_over_our_range", "our_share_engaged", "their_share_engaged", "our_spread", "our_units", "their_units"]


def decode(x: List[float]) -> Dict[str, Any]:
    """Readable physics summary from a feature vector (inverse of tactic_dsl.feature_vector + extras)."""
    import tactic_dsl as T

    out: Dict[str, Any] = {}
    i = 0
    for name, allowed in T.FEATURES.items():
        if allowed == "num":
            s = max(min(x[i], 0.999), -0.999)
            out[name] = round(s / (1 - abs(s)), 2)
            i += 1
        else:
            block = x[i:i + len(allowed)]
            out[name] = allowed[int(np.argmax(block))] if max(block) > 0 else None
            i += len(allowed)
    for name, v in zip(EXTRA_NAMES, x[i:]):
        out[name] = round(float(v), 2)
    keep = ("speed", "reach", "numbers", "contact", "pocket", "hp_trend", "if_we_withdraw", "allied_melee", "enemy_melee",
            "our_ranged", "our_melee", "enemy_guns", "enemy_melee_n", "enemy_suicide", "tick_frac", *EXTRA_NAMES)
    return {k: out[k] for k in keep if k in out}


_TRAIN: Dict[str, Any] = {}


def _train_index():
    if not _TRAIN:
        X, Q = [], []
        for name in TRAIN_FILES:
            for ep in json.loads((ROOT / "results" / "search" / name).read_text()):
                for d in ep["points"]:
                    X.append(d["x"])
                    Q.append(d["q"])
        X = np.array(X, dtype=float)
        mu, sd = X.mean(0), X.std(0) + 1e-6
        _TRAIN.update({"Z": (X - mu) / sd, "mu": mu, "sd": sd, "Q": Q, "X": X})
    return _TRAIN


def neighbors(x: List[float], k: int = K_EXAMPLES) -> List[int]:
    t = _train_index()
    z = (np.array(x) - t["mu"]) / t["sd"]
    return list(np.argsort(((t["Z"] - z) ** 2).sum(1))[:k])


def _examples(idx: List[int], actions: List[str]) -> List[Dict[str, Any]]:
    t = _train_index()
    out = []
    for i in idx:
        q = t["Q"][i]
        out.append({
            "situation": decode(list(t["X"][i])),
            "result_of_each_option": {a: ("win" if q[a] >= 0.5 else "lose") for a in actions},
        })
    return out


def cmd_ask_icl(src: str = "answers.json", dst: str = "answers_icl.json") -> None:
    import search as SE
    from jev_api import JevClient

    pts = json.loads((OUT / src).read_text())
    actions = list(SE.MACROS) + ["default"]
    base_q = _questions(actions)
    client = JevClient()

    def one(p):
        idx = neighbors(p["x"])
        state = dict(p["state"])
        state["now_in_numbers"] = decode(p["x"])
        state["similar_training_moments"] = {
            "what": (f"The {K_EXAMPLES} training moments most similar to now, by physics. For each, every option "
                     "was actually played out to the end; 'win'/'lose' is what really happened. Compare them with "
                     "now: weigh moments that match the current situation more, and note where they differ."),
            "moments": _examples(idx, actions),
        }
        r = client.system_one(state, base_q)
        ans = (r or {}).get("answers") or {}
        return {"idx": [int(i) for i in idx],
                "jev_icl": {"now": _p_win(ans.get("win_now")), **{a: _p_win(ans.get(f"win_if_{a}")) for a in actions}},
                "tokens": int(((r or {}).get("usage") or {}).get("input_tokens") or 0)}

    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(one, pts))
    for p, r in zip(pts, res):
        p.update(r)
    (OUT / dst).write_text(json.dumps(pts))
    print(f"asked {len(pts)} points with {K_EXAMPLES} examples each; calls ok {client.n_calls} fail {client.n_fail}; "
          f"mean input tokens {np.mean([r['tokens'] for r in res]):.0f}")


def cmd_score_icl() -> None:
    import search as SE
    import value as V

    pts = [p for p in json.loads((OUT / "answers_icl.json").read_text()) if not np.isnan(p["jev_icl"]["now"])]
    macros = list(SE.MACROS)
    model = V.load_model()
    t = _train_index()
    true = np.array([[p["q"][a] - p["q"]["default"] for a in macros] for p in pts])
    y = np.array([1 if p["q"]["default"] >= 0.5 else 0 for p in pts])
    adv = {
        "Jev (no examples)": np.array([[p["jev"][a] - p["jev"]["default"] for a in macros] for p in pts]),
        "Jev + 8 examples": np.array([[p["jev_icl"][a] - p["jev_icl"]["default"] for a in macros] for p in pts]),
        "kNN average (same 8)": np.array([[np.mean([t["Q"][i][a] - t["Q"][i]["default"] for i in p["idx"]]) for a in macros] for p in pts]),
        "value model": np.array([[V.predict_advantages(model, p["x"])[a] for a in macros] for p in pts]),
    }
    knn_now = np.array([np.mean([t["Q"][i]["default"] >= 0.5 for i in p["idx"]]) for p in pts])
    print(f"{len(pts)} points; oracle gain {np.maximum(true.max(1), 0).sum():.2f}")
    print(f"[state value AUC] Jev no examples {_auc(np.array([p['jev']['now'] for p in pts]), y):.3f}; "
          f"Jev + examples {_auc(np.array([p['jev_icl']['now'] for p in pts]), y):.3f}; "
          f"kNN {_auc(knn_now, y):.3f}; health ratio {_auc(np.array([p['x'][-8] for p in pts]), y):.3f}")
    rank = lambda v: np.argsort(np.argsort(v))
    for name, a in adv.items():
        a = np.nan_to_num(a, nan=-9)
        gains = []
        for tau in (0.0, 0.05, 0.1, 0.2):
            pick = a.argmax(1)
            take = a.max(1) > tau
            gains.append(f"{(true[np.arange(len(pick)), pick] * take).sum():+6.2f}({int(take.sum()):3d})")
        rc = np.corrcoef(rank(a.ravel()), rank(true.ravel()))[0, 1]
        print(f"  {name:22s} gain at tau 0/0.05/0.1/0.2 (departures): {'  '.join(gains)}   rank corr {rc:.3f}")


def gate_rule_gains(pts, thresholds=None, tau: float = 0.05):
    """Fixed round-11 rule: kNN-average proposal above tau, taken only when the
    situation signal is below its threshold (first-batch median)."""
    import search as SE

    macros = list(SE.MACROS)
    t = _train_index()
    true = np.array([[p["q"][a] - p["q"]["default"] for a in macros] for p in pts])
    kadv = np.array([[np.mean([t["Q"][i][a] - t["Q"][i]["default"] for i in p["idx"]]) for a in macros] for p in pts])
    sig = {
        "jev": np.array([p["jev_icl"]["now"] for p in pts]),
        "health": np.array([p["x"][-8] for p in pts]),
        "knn": np.array([np.mean([t["Q"][i]["default"] >= 0.5 for i in p["idx"]]) for p in pts]),
    }
    if thresholds is None:
        thresholds = {k: float(np.median(v)) for k, v in sig.items()}
    pick = kadv.argmax(1)
    g = true[np.arange(len(pick)), pick]
    prop = kadv.max(1) > tau
    out = {"none": (float((g * prop).sum()), int(prop.sum()))}
    for k, v in sig.items():
        take = prop & (v < thresholds[k])
        out[k] = (float((g * take).sum()), int(take.sum()))
    return out, thresholds, float(np.maximum(true.max(1), 0).sum())


def cmd_check2() -> None:
    b1 = [p for p in json.loads((OUT / "answers_icl.json").read_text()) if not np.isnan(p["jev_icl"]["now"])]
    b2 = [p for p in json.loads((OUT / "answers2_icl.json").read_text()) if not np.isnan(p["jev_icl"]["now"])]
    for p in b2:
        p.setdefault("idx", neighbors(p["x"]))
    r1, thr, o1 = gate_rule_gains(b1)
    r2, _, o2 = gate_rule_gains(b2, thr)
    print("thresholds (batch-1 medians):", {k: round(v, 3) for k, v in thr.items()})
    for name, r, o in (("batch 1 (rule chosen here)", r1, o1), ("batch 2 (fresh)", r2, o2)):
        print(f"{name}: oracle {o:.2f}  " + "  ".join(f"{k}: {v[0]:+.2f} ({v[1]})" for k, v in r.items()))


if __name__ == "__main__":
    cmds = {"states": cmd_states, "ask": cmd_ask, "score": cmd_score, "ask_icl": cmd_ask_icl, "score_icl": cmd_score_icl,
            "ask2_icl": lambda: cmd_ask_icl("points2.json", "answers2_icl.json"), "check2": cmd_check2}
    cmds[sys.argv[1]]()
