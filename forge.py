"""Offline tactic forge: the Codex model writes programs, the simulator judges them.

Per train scenario: R rounds of (propose K programs -> validate -> 5 jittered
seeds each -> feedback). The best program that beats Dummy goes into the
library with its start features. Then every library program is run on every
train scenario so each entry knows where it transfers.

The simulator is used only here, offline. Nothing in play clones state.

    python forge.py forge      # needs the LLM gateway API (run outside sandbox, no proxy)
    python forge.py transfer   # local only
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results"))
sys.path.insert(0, str(ROOT / "smaclite"))
os.environ.setdefault("JEV_QUIET", "1")

import scenarios as SC  # noqa: E402
import tactic_dsl as T  # noqa: E402

FORGE_DIR = ROOT / "results" / "forge"
LIB_PATH = ROOT / "kb" / "library" / "programs.json"
PROG_DIR = Path(tempfile.gettempdir()) / "jev_forge_progs"
SEEDS = [1, 2, 3, 4, 5]
ROUNDS = 4
K = 6
UNIT_DIR = ROOT / "smaclite" / "smaclite" / "env" / "units" / "smaclite_units"


# --- evaluation -------------------------------------------------------------

def _prog_path(prog: Dict[str, Any]) -> str:
    PROG_DIR.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(prog, sort_keys=True)
    import hashlib

    path = PROG_DIR / (hashlib.md5(blob.encode()).hexdigest()[:12] + ".json")
    if not path.is_file():
        path.write_text(blob)
    return str(path)


def _episode(job: Tuple[str, Dict[str, Any], int]) -> Dict[str, Any]:
    import _regress as R

    spec, scen, seed = job
    return R.run_scenario(spec, scen, seed)


def evaluate(pool: Pool, specs: List[str], scen: Dict[str, Any], seeds: List[int] = SEEDS) -> List[Dict[str, Any]]:
    """Run each policy spec on the scenario's seeds. Returns one summary per spec."""
    jobs = [(sp, scen, s) for sp in specs for s in seeds]
    rows = pool.map(_episode, jobs, chunksize=1)
    out = []
    for i, sp in enumerate(specs):
        rs = rows[i * len(seeds):(i + 1) * len(seeds)]
        wins = sum(r["win"] for r in rs)
        margin = sum(r["A"][1] - r["E"][1] for r in rs) / len(rs)
        out.append({"spec": sp, "wins": wins, "margin": round(margin, 1), "rows": rs})
    return out


def score(summary: Dict[str, Any]) -> float:
    return summary["wins"] * 10000 + summary["margin"]


def failure_note(summary: Dict[str, Any]) -> str:
    rs = summary["rows"]
    lost = [r for r in rs if not r["win"]]
    if not lost:
        return "won every seed"
    r = lost[0]
    return (
        f"lost {len(lost)}/{len(rs)}; e.g. after {r['steps']} steps we had {r['A'][0]} units "
        f"({r['A'][1]} hp) left, enemy {r['E'][0]} units ({r['E'][1]} hp)"
    )


# --- scenario description ---------------------------------------------------

def _unit_stats(kinds: List[str]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for k in kinds:
        d = json.loads((UNIT_DIR / f"{k.lower()}.json").read_text())
        out[k.lower()] = {
            key: d.get(key) for key in ("hp", "shield", "armor", "damage", "cooldown", "speed", "attack_range", "bonuses")
            if d.get(key) is not None
        }
    return out


def start_state(scen: Dict[str, Any]) -> Dict[str, Any]:
    """commander_state at tick 0 (seed 0 = no jitter)."""
    import jev_smac_policy as J
    from macsmac.snapshot import snapshot

    env = SC.make_env(scen, 0)
    try:
        env.reset()
        snap = snapshot(env)
        pol = J.DummyActionPolicy()
        pol.act(scen["id"], 0, snap)
        return J.commander_state(0, snap, [], "no_trade_yet")
    finally:
        env.close()


def describe_scenario(scen: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    kinds = sorted(set(scen["ally"]) | set(scen["enemy"]))
    return {
        "our_army": {k.lower(): n for k, n in scen["ally"].items()},
        "enemy_army": {k.lower(): n for k, n in scen["enemy"].items()},
        "unit_stats": _unit_stats(kinds),
        "terrain": {
            "open": "open field",
            "wall_gap": "a wall between the armies with one gap in the middle (a choke)",
            "ravine": "a ravine split by a long wall",
            "octagon": "an enclosed octagon arena",
            "corridor": "a long diagonal corridor; our rally point is far behind us",
        }[scen["layout"]],
        "start_features": T.features(state),
        "situation": state.get("situation"),
    }


# --- the writer ---------------------------------------------------------------

INSTRUCTIONS = (
    "You design tactic programs for a StarCraft II micro-battle simulator. "
    "Code executes all unit movement; a program only decides, tick by tick, which "
    "named pick each exam takes, based on physical features. "
    "Output one JSON object only, no markdown: "
    '{"programs": [{"name": str, "why": str, "rules": [{"when": {...}, "set": {...}}], "else": {...}}]}. '
    "Rules are checked in order; the first rule whose every condition holds is merged over `else`. "
    "Use only the listed features, values and picks. A numeric feature takes a number or "
    '{">=": n} style tests. Keep each program under 6 rules. Make the programs genuinely '
    "different from each other: different ideas, not small variations."
)


def writer_prompt(desc: Dict[str, Any], neighbors: List[Dict[str, Any]], history: List[Dict[str, Any]], k: int) -> str:
    parts = {
        "task": f"Write {k} programs that make our army win this fight.",
        "fight": desc,
        "dsl": {"features": T.FEATURES, "picks": T.pick_meanings(), "notes": T.NOTES},
        "programs_that_won_similar_fights": [
            {"program": n["program"], "won": f"{n['wins']}/5 on its own fight"} for n in neighbors
        ],
        "your_earlier_attempts_on_this_fight": [
            {"program": h["program"], "result": h["note"]} for h in history[-8:]
        ],
    }
    return json.dumps(parts, ensure_ascii=False)


def propose(client, desc, neighbors, history, k: int) -> Tuple[List[Dict[str, Any]], List[str]]:
    reply = client.fill_json(
        INSTRUCTIONS, writer_prompt(desc, neighbors, history, k), timeout=120, max_tokens=6000, temperature=0.8
    )
    progs, errs = [], []
    for raw in (reply or {}).get("programs") or []:
        clean, e = T.validate(raw)
        if e:
            errs.append(f"{(raw or {}).get('name')}: {e[0]}")
        if clean and (clean["rules"] or clean["else"]):
            progs.append(clean)
    if reply is None:
        errs.append("writer returned nothing")
    return progs, errs


# --- commands -----------------------------------------------------------------

def load_lib() -> List[Dict[str, Any]]:
    return json.loads(LIB_PATH.read_text()) if LIB_PATH.is_file() else []


def save_lib(lib: List[Dict[str, Any]]) -> None:
    LIB_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIB_PATH.write_text(json.dumps(lib, indent=1, ensure_ascii=False))


def writer_model() -> str:
    """The model Codex is configured to use (~/.codex/config.toml), unless FORGE_MODEL is set."""
    if os.environ.get("FORGE_MODEL"):
        return os.environ["FORGE_MODEL"]
    import re

    cfg = Path.home() / ".codex" / "config.toml"
    m = re.search(r'^model\s*=\s*"([^"]+)"', cfg.read_text(), re.M) if cfg.is_file() else None
    return m.group(1) if m else "Grok-4.6"


def cmd_forge(limit: Optional[int] = None) -> None:
    from system2_api import System2Client

    client = System2Client(model=writer_model(), timeout=120)
    print(f"writer model: {client.model}", flush=True)
    FORGE_DIR.mkdir(parents=True, exist_ok=True)
    train = SC.load("train")[:limit] if limit else SC.load("train")
    lib = load_lib()
    with Pool(8) as pool:
        for scen in train:
            out_path = FORGE_DIR / f"{scen['id']}.json"
            if out_path.is_file():
                continue
            state = start_state(scen)
            desc = describe_scenario(scen, state)
            vec = T.feature_vector(T.features(state))
            base = {b["spec"]: b for b in evaluate(pool, ["dummy", "prog:hand_rules"], scen)}
            dummy_w = base["dummy"]["wins"]
            history: List[Dict[str, Any]] = []
            best: Optional[Dict[str, Any]] = None
            log = {"id": scen["id"], "dummy": dummy_w, "hand_rules": base["prog:hand_rules"]["wins"], "rounds": []}
            for rnd in range(ROUNDS):
                neighbors = T.nearest(lib, vec, 3)
                progs, errs = propose(client, desc, neighbors, history, K)
                specs = ["prog:" + _prog_path(p) for p in progs]
                results = evaluate(pool, specs, scen) if specs else []
                rlog = {"round": rnd, "errors": errs, "programs": []}
                for p, r in zip(progs, results):
                    note = failure_note(r)
                    history.append({"program": p, "note": f"{r['wins']}/5 wins; {note}", "score": score(r)})
                    rlog["programs"].append({"program": p, "wins": r["wins"], "margin": r["margin"]})
                    if best is None or score(r) > best["score"]:
                        best = {"program": p, "wins": r["wins"], "margin": r["margin"], "score": score(r)}
                history.sort(key=lambda h: h["score"])
                log["rounds"].append(rlog)
                print(
                    f"{scen['id']} r{rnd} dummy={dummy_w} hand={log['hand_rules']} "
                    f"got={[x['wins'] for x in rlog['programs']]} err={len(errs)} best={best and best['wins']}",
                    flush=True,
                )
                if best and best["wins"] == 5:
                    break
            log["best"] = best
            if best and best["wins"] > dummy_w:
                lib.append({
                    "id": f"L{len(lib):03d}",
                    "program": best["program"],
                    "origin": scen["id"],
                    "wins": best["wins"],
                    "dummy": dummy_w,
                    "feats": T.features(state),
                    "vec": vec,
                    "transfer": {},
                })
                save_lib(lib)
            out_path.write_text(json.dumps(log, indent=1, ensure_ascii=False))
    print(f"library size {len(lib)}; writer calls {client.n_calls} fails {client.n_fail}")


def cmd_transfer() -> None:
    """Run every library program on every train scenario; record wins vs Dummy."""
    lib = load_lib()
    train = SC.load("train")
    with Pool(8) as pool:
        for scen in train:
            specs = ["dummy"] + ["prog:" + _prog_path(e["program"]) for e in lib]
            res = evaluate(pool, specs, scen)
            d = res[0]["wins"]
            for e, r in zip(lib, res[1:]):
                e["transfer"][scen["id"]] = {"wins": r["wins"], "dummy": d}
            print(scen["id"], "dummy", d, "lib", [r["wins"] for r in res[1:]], flush=True)
    save_lib(lib)


# --- round 3: forge per cluster, select on seeds 1-5, confirm on 6-10 ---------

CONFIRM_SEEDS = [6, 7, 8, 9, 10]
N_CLUSTERS = 12
LIB3_PATH = ROOT / "kb" / "library" / "cluster_programs.json"
CLUSTERS_PATH = ROOT / "kb" / "library" / "clusters.json"
FORGE3_DIR = ROOT / "results" / "forge3"
MENUS = ("gated", "open")


def kmeans(vecs: List[List[float]], k: int, seed: int = 20260929, iters: int = 50):
    import numpy as np

    X = np.array(vecs, dtype=float)
    rng = np.random.default_rng(seed)
    # k-means++ init
    cent = [X[rng.integers(len(X))]]
    for _ in range(1, k):
        d = np.min([((X - c) ** 2).sum(1) for c in cent], axis=0)
        cent.append(X[rng.choice(len(X), p=d / d.sum())])
    C = np.array(cent)
    lab = np.zeros(len(X), dtype=int)
    for _ in range(iters):
        lab = np.argmin(((X[:, None, :] - C[None]) ** 2).sum(2), axis=1)
        newC = np.array([X[lab == j].mean(0) if (lab == j).any() else C[j] for j in range(k)])
        if np.allclose(newC, C):
            break
        C = newC
    return C.tolist(), lab.tolist()


def with_menu(prog: Dict[str, Any], menu: str) -> Dict[str, Any]:
    out = dict(prog)
    out["menu"] = menu
    return out


def cluster_eval(pool: Pool, prog: Dict[str, Any], members: List[Dict[str, Any]], dummy: Dict[str, int], seeds: List[int]) -> Dict[str, Any]:
    """Net wins vs Dummy summed over the cluster's scenarios."""
    spec = "prog:" + _prog_path(prog)
    per, net, margin = {}, 0, 0.0
    for scen in members:
        r = evaluate(pool, [spec], scen, seeds)[0]
        per[scen["id"]] = {"wins": r["wins"], "dummy": dummy[scen["id"]], "note": failure_note(r)}
        net += r["wins"] - dummy[scen["id"]]
        margin += r["margin"]
    return {"net": net, "margin": round(margin, 1), "per": per}


def cluster_prompt(members_desc: List[Dict[str, Any]], history: List[Dict[str, Any]], k: int, hints: Optional[Dict[str, Any]] = None) -> str:
    parts: Dict[str, Any] = {
        "task": (
            f"Write {k} programs. ONE program must win as many of these similar fights as possible; "
            "it is scored by wins minus attack-move wins, summed over all of them, then checked on "
            "fresh spawns. A program that wins one fight and loses the others scores badly."
        ),
        "fights": members_desc,
        "dsl": {"features": T.FEATURES, "picks": T.pick_meanings(), "notes": T.NOTES},
        "your_earlier_attempts": [
            {"program": h["program"], "net_vs_attack_move": h["net"], "per_fight": h["per_brief"], "worst": h["worst"]}
            for h in history[-8:]
        ],
    }
    if hints:
        parts["teacher_hints"] = hints
    return json.dumps(parts, ensure_ascii=False)


def propose_cluster(client, desc, history, k: int, hints: Optional[Dict[str, Any]] = None):
    reply = client.fill_json(INSTRUCTIONS, cluster_prompt(desc, history, k, hints), timeout=120, max_tokens=6000, temperature=0.8)
    progs, errs = [], []
    for raw in (reply or {}).get("programs") or []:
        clean, e = T.validate(raw)
        if e:
            errs.append(f"{(raw or {}).get('name')}: {e[0]}")
        if clean and (clean["rules"] or clean["else"]):
            progs.append(clean)
    if reply is None:
        errs.append("writer returned nothing")
    return progs, errs


def teacher_hints(ids: List[str]) -> Dict[str, Any]:
    """What the offline look-ahead search preferred on these fights, by phase.

    Picks are counted only where the best macro beat plain attack-move by a
    clear margin, so ties do not drown the signal."""
    import search as SE

    rows = json.loads((ROOT / "results" / "search" / "train.json").read_text())
    counts: Dict[str, Dict[str, int]] = {"before_contact": {}, "in_contact": {}}
    for r in rows:
        if r["id"] not in ids:
            continue
        for d in r["log"]:
            sc = d["scores"]
            best = max(sc, key=sc.get)
            if best == "none" or sc[best] - sc["none"] < 0.05:
                continue
            phase = "in_contact" if d["feats"].get("someone_can_shoot_now") else "before_contact"
            counts[phase][best] = counts[phase].get(best, 0) + 1
    macros = {n: (None if p is None else {"menu": p.get("menu", "open"), "set": p.get("else")}) for n, p in SE.MACROS.items()}
    return {
        "what": "An offline look-ahead search that tries each macro for 12 steps and keeps the best wins far more often than attack-move. Counts of the macros it preferred on these fights:",
        "preferred_macros": counts,
        "macro_definitions": macros,
        "note": "Rules may set \"menu\": \"open\" | \"gated\" | \"dummy\" per rule; dummy means plain attack-move for that situation.",
    }


def cmd_cluster(lib_path: Path = None, out_dir: Path = None, hints: bool = False) -> None:
    from system2_api import System2Client

    lib_path = lib_path or LIB3_PATH
    out_dir = out_dir or FORGE3_DIR
    client = System2Client(model=writer_model(), timeout=120)
    print(f"writer model: {client.model}", flush=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    train = SC.load("train")
    states = {s["id"]: start_state(s) for s in train}
    vecs = [T.feature_vector(T.features(states[s["id"]])) for s in train]
    if CLUSTERS_PATH.is_file():
        cl = json.loads(CLUSTERS_PATH.read_text())
    else:
        cent, lab = kmeans(vecs, N_CLUSTERS)
        cl = {"centroids": cent, "members": {str(j): [s["id"] for s, l in zip(train, lab) if l == j] for j in range(N_CLUSTERS)}}
        CLUSTERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        CLUSTERS_PATH.write_text(json.dumps(cl))
    by_id = {s["id"]: s for s in train}
    lib = json.loads(lib_path.read_text()) if lib_path.is_file() else []
    with Pool(8) as pool:
        for j, ids in cl["members"].items():
            out_path = out_dir / f"cluster{j}.json"
            if out_path.is_file() or not ids:
                continue
            members = [by_id[i] for i in ids]
            dsel = {m["id"]: evaluate(pool, ["dummy"], m, SEEDS)[0]["wins"] for m in members}
            dcon = {m["id"]: evaluate(pool, ["dummy"], m, CONFIRM_SEEDS)[0]["wins"] for m in members}
            desc = [describe_scenario(m, states[m["id"]]) for m in members]
            log: Dict[str, Any] = {"cluster": j, "members": ids, "dummy_sel": dsel, "dummy_confirm": dcon, "rounds": []}
            history: List[Dict[str, Any]] = []
            cands: List[Dict[str, Any]] = []
            hint = teacher_hints(ids) if hints else None

            def consider(prog: Dict[str, Any], source: str) -> Dict[str, Any]:
                """Score a program on the cluster in each menu mode; keep the better mode."""
                best = None
                for menu in (MENUS if source == "forge" else ("gated",)):
                    p = with_menu(prog, menu)
                    r = cluster_eval(pool, p, members, dsel, SEEDS)
                    if best is None or (r["net"], r["margin"]) > (best["sel"]["net"], best["sel"]["margin"]):
                        best = {"program": p, "sel": r, "source": source}
                return best

            hand = consider(T.HAND_RULES, "hand")
            hand["confirm"] = cluster_eval(pool, hand["program"], members, dcon, CONFIRM_SEEDS)
            log["hand"] = {"sel": hand["sel"]["net"], "confirm": hand["confirm"]["net"]}
            stale = 0
            top = None
            for rnd in range(ROUNDS):
                progs, errs = propose_cluster(client, desc, history, K, hint)
                rb = None
                tried = []
                for prog in progs:
                    c = consider(prog, "forge")
                    brief = {i: f"{v['wins']}/5 vs {v['dummy']}/5" for i, v in c["sel"]["per"].items()}
                    worst = min(c["sel"]["per"].items(), key=lambda kv: kv[1]["wins"] - kv[1]["dummy"])
                    history.append({"program": c["program"], "net": c["sel"]["net"], "per_brief": brief,
                                    "worst": f"{worst[0]}: {worst[1]['note']}"})
                    tried.append(c["sel"]["net"])
                    if rb is None or (c["sel"]["net"], c["sel"]["margin"]) > (rb["sel"]["net"], rb["sel"]["margin"]):
                        rb = c
                history.sort(key=lambda h: h["net"])
                if rb is not None:
                    rb["confirm"] = cluster_eval(pool, rb["program"], members, dcon, CONFIRM_SEEDS)
                    cands.append(rb)
                improved = rb is not None and (top is None or rb["sel"]["net"] > top["sel"]["net"])
                top = rb if improved else top
                stale = 0 if improved else stale + 1
                log["rounds"].append({"round": rnd, "errors": errs, "nets": tried,
                                      "round_best": rb and {"sel": rb["sel"]["net"], "confirm": rb["confirm"]["net"], "program": rb["program"]}})
                print(f"cluster{j} n={len(ids)} r{rnd} nets={tried} best_sel={rb and rb['sel']['net']} "
                      f"confirm={rb and rb['confirm']['net']} hand={log['hand']} err={len(errs)}", flush=True)
                if stale >= 2:
                    break
            # Admit the highest-selection forged program whose fresh-seed net is positive.
            admitted = None
            for c in sorted(cands, key=lambda c: (c["sel"]["net"], c["sel"]["margin"]), reverse=True):
                if c["confirm"]["net"] > 0:
                    admitted = c
                    break
            feats = T.features(states[ids[0]])
            for c in [x for x in (admitted, hand) if x is not None and x["confirm"]["net"] > 0]:
                assert c["confirm"]["net"] > 0
                lib.append({
                    "id": f"C{j}-{c['source']}",
                    "cluster": int(j),
                    "source": c["source"],
                    "program": c["program"],
                    "sel_net": c["sel"]["net"],
                    "confirm_net": c["confirm"]["net"],
                    "fights": len(ids) * len(CONFIRM_SEEDS),
                    "feats": feats,
                    "vec": cl["centroids"][int(j)],
                })
            lib_path.write_text(json.dumps(lib, indent=1, ensure_ascii=False))
            log["admitted"] = admitted and {"sel": admitted["sel"]["net"], "confirm": admitted["confirm"]["net"]}
            out_path.write_text(json.dumps(log, indent=1, ensure_ascii=False))
    print(f"library size {len(lib)}; writer calls {client.n_calls} fails {client.n_fail}")


# --- round 6: search programs by whole-episode outcome ------------------------

OUTCOME_LIB = ROOT / "kb" / "library" / "outcome_programs.json"
OUTCOME_DIR = ROOT / "results" / "forge6"
ACCEPT = 2  # a leaf change must add at least this many net wins


def _batch_net(pool: Pool, progs: List[Dict[str, Any]], members: List[Dict[str, Any]],
               dummy: Dict[Tuple[str, int], int], seeds: List[int]) -> List[int]:
    """Net wins vs Dummy over the cluster for many programs in one pool.map."""
    jobs = [("prog:" + _prog_path(p), m, k) for p in progs for m in members for k in seeds]
    rows = pool.map(_episode, jobs, chunksize=1)
    per = len(members) * len(seeds)
    out = []
    for i in range(len(progs)):
        chunk = zip(jobs[i * per:(i + 1) * per], rows[i * per:(i + 1) * per])
        out.append(sum(r["win"] - dummy[(m["id"], k)] for (_, m, k), r in chunk))
    return out


def tree_program(skeleton: Dict[str, Any], leaves: List[str], name: str) -> Dict[str, Any]:
    """The D3 tree's conditions with a macro on every leaf."""
    import distill as D

    rules = []
    for r, macro in zip(skeleton["rules"], leaves):
        mr = D.macro_rule(macro)
        rules.append({"when": r["when"], "set": mr["set"], "menu": mr["menu"]})
    return {"name": name, "menu": "dummy", "rules": rules, "else": {}, "why": "leaves: " + ", ".join(leaves)}


def cmd_outcome() -> None:
    import distill as D
    import search as SE

    OUTCOME_DIR.mkdir(parents=True, exist_ok=True)
    macros = list(SE.MACROS)
    dist = json.loads((ROOT / "kb" / "library" / "distilled_programs.json").read_text())
    d3 = next(e for e in dist if e["id"] == "D3")
    skeleton = d3["program"]
    start_leaves = [r["macro"] for r in _leaf_macros(d3["tree"])]
    cl = json.loads(CLUSTERS_PATH.read_text())
    train = {s["id"]: s for s in SC.load("train")}
    lib3 = json.loads(LIB3_PATH.read_text())
    lib = json.loads(OUTCOME_LIB.read_text()) if OUTCOME_LIB.is_file() else []
    with Pool(8) as pool:
        for j, ids in cl["members"].items():
            out_path = OUTCOME_DIR / f"cluster{j}.json"
            if out_path.is_file() or not ids:
                continue
            members = [train[i] for i in ids]
            dummy = {}
            for seeds in (SEEDS, CONFIRM_SEEDS):
                jobs = [("dummy", m, k) for m in members for k in seeds]
                for (_, m, k), r in zip(jobs, pool.map(_episode, jobs, chunksize=1)):
                    dummy[(m["id"], k)] = r["win"]
            log: Dict[str, Any] = {"cluster": j, "members": ids, "starts": []}
            cands: List[Dict[str, Any]] = []
            for start_name, leaves, passes in (("d3", list(start_leaves), 2), ("none", ["none"] * len(start_leaves), 1)):
                cur = _batch_net(pool, [tree_program(skeleton, leaves, "x")], members, dummy, SEEDS)[0]
                trail = [cur]
                for _ in range(passes):
                    for i in range(len(leaves)):
                        alts = [m for m in macros if m != leaves[i]]
                        progs = [tree_program(skeleton, leaves[:i] + [m] + leaves[i + 1:], "x") for m in alts]
                        nets = _batch_net(pool, progs, members, dummy, SEEDS)
                        b = max(range(len(alts)), key=lambda t: nets[t])
                        if nets[b] >= cur + ACCEPT:
                            leaves[i], cur = alts[b], nets[b]
                            trail.append(cur)
                prog = tree_program(skeleton, leaves, f"outcome_c{j}_{start_name}")
                cands.append({"program": prog, "leaves": list(leaves), "sel": cur, "source": f"tree_{start_name}"})
                log["starts"].append({"start": start_name, "trail": trail, "leaves": leaves})
                print(f"cluster{j} n={len(ids)} start={start_name} sel_net trail={trail}", flush=True)
            for e in lib3:
                if e.get("cluster") == int(j) and e.get("source") == "forge":
                    net = _batch_net(pool, [e["program"]], members, dummy, SEEDS)[0]
                    cands.append({"program": e["program"], "leaves": None, "sel": net, "source": "lib3"})
            confirms = _batch_net(pool, [c["program"] for c in cands], members, dummy, CONFIRM_SEEDS)
            for c, n in zip(cands, confirms):
                c["confirm"] = n
            admitted: List[Dict[str, Any]] = []
            for c in sorted(cands, key=lambda c: c["sel"], reverse=True):
                if c["confirm"] <= 0 or len(admitted) >= 2:
                    continue
                if any(a["leaves"] and c["leaves"] and sum(x != y for x, y in zip(a["leaves"], c["leaves"])) < 2 for a in admitted):
                    continue
                admitted.append(c)
            for n, c in enumerate(admitted):
                assert c["confirm"] > 0
                lib.append({
                    "id": f"O{j}-{n}", "cluster": int(j), "source": c["source"], "program": c["program"],
                    "sel_net": c["sel"], "confirm_net": c["confirm"], "fights": len(ids) * len(CONFIRM_SEEDS),
                    "feats": T.features(start_state(members[0])), "vec": cl["centroids"][int(j)],
                })
            log["candidates"] = [{k: c[k] for k in ("source", "sel", "confirm", "leaves")} for c in cands]
            log["admitted"] = [c["source"] for c in admitted]
            OUTCOME_LIB.write_text(json.dumps(lib, indent=1, ensure_ascii=False))
            out_path.write_text(json.dumps(log, indent=1, ensure_ascii=False))
            print(f"cluster{j}: " + "; ".join(f"{c['source']} sel={c['sel']} confirm={c['confirm']}" for c in cands)
                  + f" -> admitted {log['admitted']}", flush=True)
    print(f"outcome library size {len(lib)}")


def _leaf_macros(tree: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Leaves in the same order distill.to_program emits rules (yes before no)."""
    if "test" not in tree:
        return [{"macro": tree["leaf"]}]
    return _leaf_macros(tree["yes"]) + _leaf_macros(tree["no"])


EVIDENCE_PATH = ROOT / "kb" / "library" / "evidence.json"


def _paired_table(train, specs: Dict[str, str], seeds: List[int]) -> Dict[str, Dict[str, Dict[str, int]]]:
    jobs = [(sp, s, k) for sp in specs.values() for s in train for k in seeds]
    with Pool(8) as pool:
        rows = pool.map(_episode, jobs, chunksize=2)
    win = {(sp, s["id"], k): r["win"] for (sp, s, k), r in zip(jobs, rows)}
    programs: Dict[str, Dict[str, Dict[str, int]]] = {}
    for pid, sp in specs.items():
        if pid == "dummy":
            continue
        rec = programs.setdefault(pid, {})
        for s in train:
            flip = sum(int(win[(sp, s["id"], k)] and not win[("dummy", s["id"], k)]) for k in seeds)
            lose = sum(int(win[("dummy", s["id"], k)] and not win[(sp, s["id"], k)]) for k in seeds)
            rec[s["id"]] = {"flip": flip, "lose": lose, "net": flip - lose}
    return programs


def cmd_evidence(lib_path: Path = None, out_path: Path = None, headroom: bool = False) -> None:
    """Paired record of every library program vs Dummy on every train fight (seeds 1-5).

    Online choosers look up the fights most similar to the current one here.
    Train only: val and test never feed this table. With headroom, also runs
    seeds 6-10 and reports the cross-validated room for per-fight selection."""
    lib_path = lib_path or LIB3_PATH
    out_path = out_path or EVIDENCE_PATH
    train = SC.load("train")
    lib = json.loads(lib_path.read_text())
    specs = {"dummy": "dummy"}
    for e in lib:
        specs[e["id"]] = "prog:" + _prog_path(e["program"])
    programs = _paired_table(train, specs, SEEDS)
    vecs = {s["id"]: T.feature_vector(T.features(start_state(s))) for s in train}
    out_path.write_text(json.dumps({"train_vecs": vecs, "programs": programs}))
    for pid, rec in programs.items():
        print(pid, "net over train", sum(r["net"] for r in rec.values()), flush=True)
    if not headroom:
        return
    fresh = _paired_table(train, specs, CONFIRM_SEEDS)
    ids = list(programs)
    best_single = max(ids, key=lambda p: sum(r["net"] for r in programs[p].values()))
    single = sum(r["net"] for r in fresh[best_single].values())
    per = 0
    for s in train:
        pick = max(ids + ["none"], key=lambda p: programs[p][s["id"]]["net"] if p != "none" else 0)
        per += 0 if pick == "none" else fresh[pick][s["id"]]["net"]
    print(f"headroom on fresh seeds 6-10: best single program ({best_single}) {single:+d}; "
          f"per-fight pick chosen on seeds 1-5 {per:+d}; room for selection {per - single:+d}", flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "evidence":
        cmd_evidence()
    elif cmd == "evidence_outcome":
        cmd_evidence(OUTCOME_LIB, ROOT / "kb" / "library" / "evidence_outcome.json", headroom=True)
    elif cmd == "headroom_lib3":
        cmd_evidence(LIB3_PATH, Path(tempfile.gettempdir()) / "evidence_lib3_check.json", headroom=True)
    elif cmd == "outcome":
        cmd_outcome()
    elif cmd == "cluster":
        cmd_cluster()
    elif cmd == "cluster_hints":
        cmd_cluster(ROOT / "kb" / "library" / "hinted_programs.json", ROOT / "results" / "forge4", hints=True)
    elif cmd == "forge":
        cmd_forge(int(sys.argv[2]) if len(sys.argv) > 2 else None)
    elif cmd == "transfer":
        cmd_transfer()
    else:
        print(__doc__)
