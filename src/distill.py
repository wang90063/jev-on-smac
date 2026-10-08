"""Distill the offline search into a tactic program.

The search log holds, per decision point, the physical features and the
look-ahead score of every macro. A shallow cost-sensitive tree picks, per
leaf, the macro with the highest total score over the leaf's samples; splits
minimise the regret of that pick. Each root-to-leaf path is one DSL rule, so
the tree is a program: physics conditions only, no map names.

    python src/distill.py tree          # fit depths 2-4, write kb/library/distilled_programs.json
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("JEV_QUIET", "1")

import tactic_dsl as T  # noqa: E402

SEARCH_LOG = ROOT / "results" / "search" / "train.json"
OUT = ROOT / "kb" / "library" / "distilled_programs.json"
MIN_LEAF = 40
N_THRESH = 12


def load_samples(path: Path = SEARCH_LOG) -> Tuple[List[Dict[str, Any]], np.ndarray, List[str]]:
    rows = json.loads(path.read_text())
    feats, scores = [], []
    macros: Optional[List[str]] = None
    for r in rows:
        for d in r["log"]:
            if macros is None:
                macros = list(d["scores"])
            feats.append(d["feats"])
            scores.append([d["scores"][m] for m in macros])
    return feats, np.array(scores, dtype=float), macros or []


def _leaf(S: np.ndarray, macros: List[str]) -> Tuple[int, float]:
    """Best macro for these samples, and the regret of always playing it."""
    tot = S.sum(0)
    none = macros.index("none")
    best = int(np.argmax(tot))
    if tot[none] >= tot[best] - 1e-9:
        best = none  # ties go to plain Dummy
    regret = float(S.max(1).sum() - tot[best])
    return best, regret


def _splits(feats: List[Dict[str, Any]], idx: np.ndarray):
    for name, allowed in T.FEATURES.items():
        vals = [feats[i].get(name) for i in idx]
        if allowed == "num":
            arr = np.array([float(v or 0) for v in vals])
            qs = np.unique(np.quantile(arr, np.linspace(0.05, 0.95, N_THRESH)))
            for t in qs:
                left = arr < t
                if 0 < left.sum() < len(arr):
                    yield (name, "<", float(round(t, 3))), left
        else:
            for v in set(vals):
                if v is None:
                    continue
                left = np.array([x == v for x in vals])
                if 0 < left.sum() < len(arr if False else vals):
                    yield (name, "==", v), left


def grow(feats, S, macros, idx: np.ndarray, depth: int) -> Dict[str, Any]:
    best, regret = _leaf(S[idx], macros)
    node: Dict[str, Any] = {"leaf": macros[best], "n": int(len(idx)), "regret": round(regret, 3)}
    if depth == 0 or len(idx) < 2 * MIN_LEAF:
        return node
    top = None
    for test, left in _splits(feats, idx):
        li, ri = idx[left], idx[~left]
        if len(li) < MIN_LEAF or len(ri) < MIN_LEAF:
            continue
        r = _leaf(S[li], macros)[1] + _leaf(S[ri], macros)[1]
        if top is None or r < top[0]:
            top = (r, test, li, ri)
    if top is None or top[0] >= regret - 1e-6:
        return node
    node["test"] = list(top[1])
    node["yes"] = grow(feats, S, macros, top[2], depth - 1)
    node["no"] = grow(feats, S, macros, top[3], depth - 1)
    return node


def _when(path: List[Tuple[Tuple[str, str, Any], bool]]) -> Dict[str, Any]:
    cat: Dict[str, set] = {}
    lo: Dict[str, float] = {}
    hi: Dict[str, float] = {}
    for (name, op, v), yes in path:
        if op == "<":
            if yes:
                hi[name] = min(hi.get(name, float("inf")), v)
            else:
                lo[name] = max(lo.get(name, float("-inf")), v)
        else:
            allowed = cat.setdefault(name, set(T.FEATURES[name]))
            cat[name] = allowed & {v} if yes else allowed - {v}
    when: Dict[str, Any] = {}
    for name, allowed in cat.items():
        ordered = [a for a in T.FEATURES[name] if a in allowed]
        if len(ordered) < len(T.FEATURES[name]):
            when[name] = ordered[0] if len(ordered) == 1 else ordered
    for name in set(lo) | set(hi):
        test = {}
        if name in lo:
            test[">="] = lo[name]
        if name in hi:
            test["<"] = hi[name]
        when[name] = test
    return when


def macro_rule(macro: str) -> Dict[str, Any]:
    import search as SE

    prog = SE.MACROS[macro]
    if prog is None:
        return {"menu": "dummy", "set": {}}
    return {"menu": prog.get("menu") or "open", "set": dict(prog.get("else") or {})}


def to_program(tree: Dict[str, Any], name: str) -> Dict[str, Any]:
    rules: List[Dict[str, Any]] = []

    def walk(node, path):
        if "test" not in node:
            rule = macro_rule(node["leaf"])
            rule["when"] = _when(path)
            rule["macro"] = node["leaf"]
            rules.append(rule)
            return
        t = tuple(node["test"])
        walk(node["yes"], path + [(t, True)])
        walk(node["no"], path + [(t, False)])

    walk(tree, [])
    prog = {"name": name, "menu": "dummy", "rules": [{k: r[k] for k in ("when", "set", "menu")} for r in rules], "else": {}}
    clean, errs = T.validate(prog)
    assert not errs, errs
    clean["why"] = "distilled from offline look-ahead search: " + ", ".join(r["macro"] for r in rules)
    return clean


def cmd_tree() -> None:
    feats, S, macros = load_samples()
    idx = np.arange(len(feats))
    out = []
    for depth in (1, 2, 3, 4):
        tree = grow(feats, S, macros, idx, depth)
        prog = to_program(tree, f"tree_d{depth}")
        base = _leaf(S, macros)[1]
        leaves = []

        def count(n):
            if "test" in n:
                count(n["yes"]); count(n["no"])
            else:
                leaves.append(f"{n['leaf']}({n['n']})")

        count(tree)
        print(f"depth {depth}: regret {base:.1f} -> tree leaves {leaves}")
        out.append({"id": f"D{depth}", "source": "tree", "program": prog, "tree": tree})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"{len(feats)} samples, macros {macros} -> {OUT}")


DAGGER_DIR = ROOT / "results" / "search"
DAGGER_BETAS = (0.5, 0.0, 0.0)
DAGGER_DEPTH = 4


def cmd_dagger() -> None:
    """Fit on teacher states, then let the student drive and relabel, 3 times."""
    from multiprocessing import Pool

    import scenarios as SC
    import search as SE

    paths = [SEARCH_LOG]
    train = SC.load("train")
    feats, S, macros = load_samples()
    tree = grow(feats, S, macros, np.arange(len(feats)), DAGGER_DEPTH)
    for it, beta in enumerate(DAGGER_BETAS, start=1):
        out = DAGGER_DIR / f"dagger{it}.json"
        if not out.is_file():
            jobs = [(s, k, tree, beta) for s in train for k in (1, 2, 3, 4, 5)]
            with Pool(8) as pool:
                rows = pool.map(SE.search_episode, jobs, chunksize=1)
            out.write_text(json.dumps(rows))
            print(f"dagger iter {it} (beta={beta}): student-driven wins {sum(r['win'] for r in rows)}/{len(rows)}", flush=True)
        paths.append(out)
        F, Ss = [], []
        for p in paths:
            f, s, _ = load_samples(p)
            F += f
            Ss.append(s)
        S_all = np.vstack(Ss)
        tree = grow(F, S_all, macros, np.arange(len(F)), DAGGER_DEPTH)
        print(f"  refit on {len(F)} samples", flush=True)
    lib = json.loads(OUT.read_text()) if OUT.is_file() else []
    lib = [e for e in lib if e["id"] != "DAG"]
    lib.append({"id": "DAG", "source": "dagger", "program": to_program(tree, "dagger_d4"), "tree": tree})
    OUT.write_text(json.dumps(lib, indent=1, ensure_ascii=False))
    print("wrote DAG ->", OUT)


if __name__ == "__main__":
    if sys.argv[1:2] == ["tree"]:
        cmd_tree()
    elif sys.argv[1:2] == ["dagger"]:
        cmd_dagger()
    else:
        print(__doc__)
