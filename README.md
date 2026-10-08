# Teaching AI to Micro in StarCraft: 16 Rounds, and the Protagonist Didn't Make the Cut

> **The plan:** let **Jev**, a typed-choice model that answers multiple-choice questions with calibrated probabilities, make the tactical calls in SMAC battles.
> **What happened:** Jev was tried in 12 different decision roles across four generations of the system. None of them significantly beat the default of its day.
> **What actually worked:** a ~150-line Python micro program, written by an LLM that read the simulator's source code. It raised the win rate on 1,000 unseen battles from **47.5% to 72.0%**.

<p align="center">
  <img src="docs/fight.gif" alt="Same battle, two policies: the scripted baseline loses; the synthesized program wins with all four Stalkers alive" width="100%">
</p>
<p align="center"><sub>
Unseen test battle <code>y0810</code>, seed 4: 4 Stalkers (blue) vs 5 Hydralisks (red), with a wall and a single gap.
Fill = remaining HP; lines = current attack target.
<b>Left:</b> attack-move, damage spread across targets, all four Stalkers dead.
<b>Right:</b> the synthesized program holds back and focuses one Hydralisk at a time as they come through the gap. No Stalker dies.
</sub></p>

## Results

Held-out set **test6**: 200 freshly generated scenarios × 5 seeds = 1,000 battles. Each test set is run exactly once.
Only contested scenarios are kept: the generator drops fights the baseline wins 5/5, and fights both the baseline and a random policy lose 5/5.

| Method | Win rate (test6) | 23 official SMAC maps¹ |
|---|---:|---:|
| Scripted baseline (attack-move) | 47.5% | 53 / 115 |
| Hand-written rules (4 rules, tuned on the official maps) | 49.0% | *92 / 115* |
| Value-guided macro-action switching | 51.9% | 51 / 115 |
| LLM program synthesis, outcome feedback (Grok-4.7) | 59.5% | 62 / 115 |
| **LLM program synthesis, source + trace feedback (Claude)** | **72.0%** | **65 / 115** |

Paired comparisons (same scenario, same seed; exact sign test):

| | Flips (+) | Losses (−) | Net | p |
|---|---:|---:|---:|---:|
| Claude program vs Grok program | 170 | 45 | **+125** | < 0.001 |
| Claude program vs scripted baseline | 305 | 60 | **+245** | < 0.001 |

<sub>¹ Reference only. The hand-written rules were tuned on these 23 maps, so they are not a clean test. See finding 4.</sub>

## Four counter-intuitive findings

**1. The feedback channel matters more than the model that writes the code.**
The last two rows share the same interface, sandbox, and fallback; only the feedback differs.
- Grok made 4 calls and saw aggregate scores plus auto-generated critiques.
- Claude read the simulator source, traced lost battles step by step, and re-ran a paired test after every single edit.

The biggest single jump came from reading the source. The API doc said `can_attack(u, e)` meant "in range". It actually means "visible". Units ordered to attack a distant target walk into the enemy line. Fixing that one assumption was the difference between **−100 and +64** (out of 720 battles).

**2. The judgment model never beat k-nearest-neighbors.**
Wherever Jev was given similar past battles as evidence, it mostly followed that evidence. On the opening decision "hold or push?":
- Jev with 8 similar fights: **+6 / 720**;
- the same 8 neighbors' plain majority vote: **+5**.
- The ceiling for that decision is only **+25**.

In round 5, Jev and the evidence vote differed on just 2 of 600 battles.

**3. Small wins on the selection seeds are mostly noise.**
Variant g13 looked **+7** better on the seeds used to pick it. On fresh seeds it was **−14** (p = 0.049). Every improvement under ~2% of the selection battles has to be re-confirmed on seeds that played no part in choosing it.

**4. The best score on the official maps is an overfit, not a skill.**
The four hand-written rules score **92 / 115** on the 23 official SMAC maps: 39 flips and **zero** losses against the baseline.
They were picked by looking at those same maps. On 1,000 freshly generated battles they are only +15 over the baseline (49.0% vs 47.5%, p = 0.14, not significant).
The synthesized program goes the other way: 65 / 115 on the official maps and 72.0% on unseen battles. It never saw the official maps during development.
That is why every claim in this project rests on frozen, procedurally generated test sets, and the official maps are reported for reference only.

## Where Jev was tried

**How Jev is called.** Jev (TypeSafe System One) answers multiple-choice questions; it never writes code or moves units.
Every experiment used the same call:
1. Code turns the battle into a short text description: unit types and counts, HP, ranges, speeds, terrain.
2. Code asks **one question with 2–13 named options**. Each option has a one-line description, plus whatever evidence that experiment provided, such as the most similar past battles and how each option did in them.
3. Jev returns a probability for each option. The system takes the most likely one and code executes it.

Jev was never fine-tuned. Between experiments, only the question and the information in the prompt changed.

**How it was judged.** Each time, Jev had to clear two bars:
1. **Beat the default**: whatever the system did at that point without Jev.
2. **Beat a baseline given the same information**. Otherwise any gain comes from what we put in the prompt, not from Jev's judgment.

The baselines, defined once:

| Baseline | What it does | Cards |
|---|---|---|
| Attack-move | The scripted baseline: every unit attack-moves toward the enemy. The default in ④. | ④ ⑨ |
| Random pick | A uniformly random choice among the exact options Jev was offered. | ① ④ ⑤ ⑨ |
| Nearest-cluster lookup | Match the battle's physical features (counts, ranges, speeds, terrain) to the closest of 12 training clusters and run that cluster's program. The default in ①–②. | ① ② |
| Evidence vote | Take the similar past battles shown to Jev and pick the option with the best record among them, or average their outcomes. | ② ③ ⑥ ⑦ ⑧ |
| Value model | A gradient-boosted model trained on full-battle outcomes found by simulation. The default in ⑤ and ⑦. | ⑤ ⑦ |
| HP ratio | Our remaining HP ÷ the enemy's, used as a win predictor. | ⑥ ⑧ |
| Hand rules | Four rules written by hand while looking at the 23 official maps. | ④ |

It cleared neither bar anywhere.

<p align="center">
  <img src="docs/jev_map.svg" alt="Map of the nine places Jev was tried: for each, what Jev saw, its result, and the baselines with the same information" width="100%">
</p>

The nine questions fall into two groups:
- **A. Choosing a tactic** (①–⑤), measured in real battles. Wherever Jev picked, a random pick, a lookup, or a vote did about as well.
- **B. Judging the battle** (⑥–⑨), measured offline. Jev was the best judge of *"will we win?"* (⑥). It even beat averaging the same examples. But using that judgment to act (⑧) gained nothing on fresh data.

<details>
<summary><b>Where each card's numbers come from</b></summary>

| Card | Round | Data | Report |
|---|---|---|---|
| ① | 4 | test2: 120 new scenarios × 5 seeds = 600 battles | `results/iter4_report.md` |
| ② | 5 | test2, 600 battles; tuned on val first | `results/iter5_report.md` |
| ③ | 16 | train + train2, seeds 1–4 = 720 battles, leave-one-scenario-out | `results/iter16_report.md` (appendix) |
| ④ | 0–1 | 23 official SMAC maps × 5 seeds = 115 battles | `results/winrate_now.md`, `results/iter2_report.md` |
| ⑤ | 9 | test4: 200 new scenarios × 5 seeds = 1,000 battles | `results/iter9_report.md` |
| ⑥ | 10–11 | 600 recorded val decision points (two batches of 300) | `results/jev_value/report.md`, `results/iter11_report.md` |
| ⑦ | 10 | 300 recorded val decision points | `results/jev_value/report.md` |
| ⑧ | 11 | rule picked on batch 1, rerun on a fresh batch 2 (max possible: 37.5 and 27.1) | `results/iter11_report.md` |
| ⑨ | 4 | 73 train scenarios where the best and worst tactic differ by ≥ 3 wins of 5 | `results/iter4_report.md` |

The technical report (in Chinese) has all 12 experiments: [docs/tech_report.html](docs/tech_report.html).

</details>

### Why it didn't help
- **Small headroom.** The choices on offer rarely change the outcome. Even picking the best option per scenario in hindsight is worth only +25 / 720 battles (3.5%) for hold-vs-push, and +24 to +27 / 300 for choosing from the tactic program library.
- **The differences are numeric.** Range, cooldown, and positioning are hard to read from text. Asked for P(win) after each of 13 actions, Jev's answers varied by a standard deviation of only 0.047.
- **Judging is not acting.** Its win/loss judgment was the best in the project, but SMAC has no retreat or surrender, so knowing you will lose doesn't give you a move that wins.
- **The gains come from execution.** The real improvements came from per-unit, per-step computation: focus-fire allocation, overkill avoidance, and kiting on cooldown. These are natural to write as code and get lost once you turn them into multiple choice.

## Architecture evolution

```
A0  Exams + motor primitives      Jev answers tactical questions; primitives execute
A1  Tactic program library        offline LLM forging per scenario cluster; online: nearest cluster
A2  Value-guided macro switching  every 5 steps, a GBDT value model may swap in 1 of 12 preset tactics
A3  LLM program synthesis (Grok)  act(obs, mem) in a sandbox, overriding A2 unit by unit
A4  LLM program synthesis (Claude) same runtime as A3; source reading + trace-driven dev loop   ← current
```

Each layer hands the units it doesn't command down to the layer below, so the scripted baseline is always the last fallback.

The current program, [`kb/library/code/general_claude.py`](kb/library/code/general_claude.py), does five things:

1. **Focus-fire allocation.** Priority = enemy DPS ÷ remaining effective HP. A damage ledger avoids overkill. Armor and type bonuses are counted.
2. **Medivacs** heal, or retreat when threatened.
3. **Baneling screening.** Melee units intercept Banelings heading for our ranged units.
4. **Kiting.** Step back during weapon cooldown when out-ranging or out-speeding the enemy.
5. **Stall breaker.** If no one has taken damage for 10 steps, attack, because a timeout counts as a loss.

## Quick start

```bash
# Watch one battle step by step (program, split, scenario id, seed, print every N steps)
python results/dev16/trace.py kb/library/code/general_claude.py val v0042 1 10

# Paired dev comparison on the training splits (results cached by program hash)
python results/_dev16.py cmp kb/library/code/general.py kb/library/code/general_claude.py --seeds 1,2,3,4

# Held-out evaluation, then paired statistics
python results/_regress.py holdout --split val --policies dummy written_online --write out.jsonl
python results/_regress.py paired --base dummy --files out.jsonl

# Regenerate the GIF above
python results/readme_gif.py y0810 4
```

Environment: [SMAClite](smaclite/) (a lightweight Python re-implementation of SMAC); one step = 8 ticks ≈ 0.5 s.

## Repository map

| Path | What it is |
|---|---|
| `src/` | Core modules (flat imports; scripts add `src/` to `sys.path`) |
| `src/code_policy.py` | Sandbox and API for LLM-written `act(obs, mem)` programs |
| `src/jev_smac_policy.py` | Online policies, motor primitives, exam menus (A0–A4) |
| `src/tactic_dsl.py`, `src/forge.py` | Tactic DSL and offline forging (A1, A3) |
| `src/search.py`, `src/value.py` | Offline rollouts and the value model (A2) |
| `src/scenarios.py` | Procedural scenario generator; frozen train / val / test splits |
| `src/jev_api.py`, `src/jev_value.py` | Jev client and the Jev-as-judge experiments |
| `kb/library/code/` | The programs: `general_claude.py` (current), `general.py` (Grok) |
| `macsmac/` | SMAClite wrapper: env, maps, state snapshot, benchmark |
| `smaclite/` | The simulator (git submodule) |
| `results/` | Evaluation scripts (`_regress.py`, `_dev16.py`), per-round reports `iter*_report.md`, raw logs |
| `docs/` | Technical report, README figures |
| `legacy/` | Early experiments (local LLM policies, SC2 runs); not used by the current system |
| `local/` | Git-ignored: model weights and downloads |
| `AGENTS.md` | Project conventions and evaluation rules |

## If you want to use a judgment model like Jev

1. **Measure the headroom first.** Pick the best option per scenario on some seeds, then check it on others. If that is only a few percent, it doesn't matter who chooses.
2. **Always compare against "same information, no model".** Use three controls: a random pick among the same candidates, a plain vote over the same examples, and changing nothing.
3. **Use it to judge the state, not to rank actions.** With 8 retrieved examples, Jev's win/loss AUC rose from 0.787 to 0.857. It still couldn't tell actions apart.

It fits tasks with few, high-stakes decisions that can be described in words, *and* where a judgment can be turned into gain through an action like retreat, reinforce, or skip this fight. Full-game StarCraft macro fits that. Small-scale SMAC micro is the opposite.

## Evaluation discipline

- Procedural scenarios with frozen splits: train (60), train2 (120), val (80), and test2–test6 (200 each, **each used exactly once**).
- Every comparison is paired by scenario and seed, with an exact sign test on flips vs losses.
- Selection seeds and confirmation seeds are always disjoint.
- On every change, a regression check confirms the scripted baseline's step-by-step actions are unchanged.
