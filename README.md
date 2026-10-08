# Jev on SMAC: Can a Fast Choice Model Play StarCraft Micro?

> We set out to see if **Jev**, a fast model that picks among named options, could act as the policy in StarCraft multi-agent micro (SMAC) and approach RL state of the art.
> We tested three things: whether Jev can output per-unit actions, whether it can pick tactics, and whether what it learns generalizes.
>
> | Question | Answer |
> |---|---|
> | 1. Can Jev act per unit, like an RL actor? | **No.** It produces legal actions and wins the easiest map, but it never beat attack-move. A public SC2 project got 3 / 105. |
> | 2. Can it pick tactics instead? | **It can pick, but no better than chance.** In 6 setups, a random pick, a lookup, or a vote over the same information did as well. |
> | 3. Does it generalize to unseen battles? | **No.** Its one big gain was on the maps where its options were written, and random answers got almost the same there. On unseen test sets it never significantly beat the default. |
> | **Is Jev useful for micro?** | **Only as a judge, and in micro that judgment doesn't win battles.** It was the best predictor of *"will we win?"* (AUC 0.874). What actually worked: an LLM writes the micro **code**. Win rate on 1,000 unseen battles went from **47.5% to 72.0%**. |

<p align="center">
  <img src="docs/fight.gif" alt="Same battle, two policies: the scripted baseline loses; the synthesized program wins with all four Stalkers alive" width="100%">
</p>
<p align="center"><sub>
Unseen test battle <code>y0810</code>, seed 4: 4 Stalkers (blue) vs 5 Hydralisks (red), with a wall and a single gap.
Fill = remaining HP; lines = current attack target.
<b>Left:</b> attack-move, damage spread across targets, all four Stalkers dead.
<b>Right:</b> the LLM-written program holds back and focuses one Hydralisk at a time as they come through the gap. No Stalker dies.
</sub></p>

## Why we tried this

**Jev looks like an RL actor.** Jev ([TypeSafe](https://docs.typesafe.ai) System One) does not generate text. You give it a state and a question with named options, and it returns a calibrated probability for each option. That is the same shape as the discrete action head of an RL policy: a state goes in, and a distribution over actions comes out. Unlike an RL policy, it needs no training. Jev is never fine-tuned; you only change the state and the question.

**Jev is fast.** Official figures ([models](https://docs.typesafe.ai/models), [parallel questions](https://docs.typesafe.ai/cookbooks/parallel_questions)):

| | Figure |
|---|---|
| 13 questions about a ~54,000-character document, in one request | **0.27 s** |
| The same 13 questions as 13 separate requests | 2.71 s in total (≈ 0.21 s each) |
| Rate limit | 80 requests/s, 100K tokens/s |
| Questions within one request | evaluated in parallel, independently |
| Median response in real-time SC2 (external project [JEV-Star](https://github.com/sc2musa/Jev_Star)) | 0.38–0.42 s |

A SMAC step is 0.5 s of game time, so on paper Jev is fast enough to choose an action every step.

**The target: RL state of the art on SMAC.** On the original SMAC benchmark (SMACv1, in SC2), current methods reach nearly 100% on every map. HPN-QMIX (ICLR 2023) wins 100% on 9 of the 10 Hard and Super Hard maps, and 98% on the last one. Newer work has moved to SMACv2 because v1 is close to saturated. These are the numbers we aimed at:

| Map | Best published | Method | MAPPO | SMAC's scripted heuristic |
|---|---:|---|---:|---:|
| 3m | 100% | MAPPO | 100% | – |
| 2s3z | 100% | fine-tuned QMIX | 100% | 90% |
| 3s5z | 100% | fine-tuned QMIX | 96.9% | 42% |
| 5m_vs_6m | 100% | HPN-QMIX | 89.1% | 0% |
| 3s_vs_5z | 100% | HPN-QMIX | – | 0% |
| 10m_vs_11m | 96.9% | MAPPO | 96.9% | 12% |
| corridor | 100% | HPN-QMIX | 100% | 0% |
| MMM2 | 100% | HPN-QMIX | 90.6% | – |
| 3s5z_vs_3s6z | 100% | HPN-QMIX | – | – |
| 27m_vs_30m | 100% | HPN-QMIX | 93.8% | 0% |
| 6h_vs_8z | 98% | HPN-QMIX | 88.3% | 0% |

<sub>Sources: HPN-QMIX from [pymarl3](https://github.com/tjuHaoXiaotian/pymarl3) (Hao et al., ICLR 2023); fine-tuned QMIX from [pymarl2](https://github.com/hijkzzz/pymarl2); MAPPO from Yu et al. (NeurIPS 2022); the heuristic (attack the closest enemy) from the original SMAC and QMIX papers. All are median test win rates after millions of training steps per map.</sub>

## Setup and baselines

**Environment.** [SMAClite](smaclite/), a Python re-implementation of SMAC that runs without StarCraft II. One step = 8 ticks ≈ 0.5 s, and a timeout counts as a loss. The game waits for the policy, so latency costs wall-clock time, not wins.

**Battles.**
- **Main evaluation:** procedurally generated scenarios with frozen splits: train (60), train2 (120), val (80), and test2–test6 (200 each).
  - Each test set is run **exactly once**.
  - The generator drops fights the baseline wins 5/5, and fights that both the baseline and a random policy lose 5/5. Every remaining fight is contested.
- **Reference only:** the 23 official SMAC maps × 5 seeds = 115 battles. Some rules were tuned on these maps, so they are not a clean test (see Q3).

**Statistics.** Every comparison is paired by scenario and seed, with an exact sign test on flips vs losses.

**Baselines, defined up front.** For Jev to count as useful, it had to clear two bars:
1. beat **the default**: what the system did at that point without Jev;
2. beat **a baseline given the same information but no Jev**. Otherwise the gain comes from what we put in the prompt, not from Jev's judgment.

| Baseline | What it does |
|---|---|
| **Attack-move** | Every unit attack-moves toward the enemy. The scripted floor, and the fallback in every system below. |
| Random pick | A uniformly random choice among the exact options Jev was offered. |
| Nearest-cluster lookup | Match the battle's physical features (counts, ranges, speeds, terrain) to the closest of 12 training clusters, and run that cluster's program. |
| Evidence vote | Take the similar past battles shown to Jev, and pick the option with the best record among them, or average their outcomes. |
| Value model | Gradient-boosted trees trained on full-battle outcomes found by offline simulation. |
| HP ratio | Our remaining HP ÷ the enemy's, used as a win predictor. |
| Hand rules | Four rules written by hand while looking at the 23 official maps. |
| RL state of the art | HPN-QMIX / fine-tuned QMIX / MAPPO numbers above. Reference only: they come from a different simulator. |

## Q1. Can Jev directly output each unit's action?

**Conclusion: No. Jev can't serve as the actor.** It returns legal actions and wins an easy map, but nothing shows it beats plain attack-move, and every step costs one network round trip.

| Experiment | Setup | Result | Attack-move, same setup |
|---|---|---|---|
| Ours: Jev per-unit actor, map 3m | One request per step, with one Choice per living unit over that unit's legal SMAC actions (move ×4, stop, attack enemy *i*) | 2 / 2 wins, 19 steps each. **0.92 s per request** end to end; 17.6 s per battle | 5 / 5 wins |
| External: [JEV-Star](https://github.com/sc2musa/Jev_Star), real SC2 | Jev alone picks micro actions on 35 SMAC-Hard maps × 3 episodes | **3 wins / 105** | – |
| External: JEV-Star | Same, with an LLM planner giving Jev a plan | 7 / 105 | – |

<sub>The JEV-Star rows are from that project's README and are not our runs.</sub>

Why it fails:
- **The questions can't coordinate.** Questions in one request are scored independently and in parallel, so no answer depends on the others ([docs](https://docs.typesafe.ai/cookbooks/parallel_questions)). Focus fire, the most valuable thing in micro, is a joint assignment: who shoots whom, without overkill. Separate per-unit choices can't express it.
- **The difference between actions is numeric.** Range, cooldown, and distance decide the fight. We asked Jev for P(win) after each of 13 actions at 300 recorded decision points, with 8 similar examples as evidence. Its answers varied by a standard deviation of only **0.047**. Picking the top-rated action gained **+0.1**, out of a possible 37.5 (card ⑦ below).
- **It is slow at our scale.** We measured 0.92 s per request, which is slower than a 0.5 s game step. At 17.6 s per battle, a 1,000-battle test set takes about 5 hours.

*Caveat:* our own per-unit run is small: n = 2, on a map attack-move already wins. The external SC2 result (3 / 105) is the larger sample, and it points the same way.

## Q2. If not, can Jev choose the tactics?

**Conclusion: It can choose, but its choices were never better than a random pick, a lookup, or a vote over the same information.** In this setup, code executes the tactic and Jev only picks which one. We tried this in six places across four generations of the system:

| # | Question Jev answered | Data | Jev | Same information, no Jev | Verdict |
|---|---|---|---:|---|---|
| ① | Which library program runs this battle? (5 options) | test2, 600 battles | 295 wins | lookup (default) **299**; random 273 | below the default |
| ② | Same, plus each program's record in the 8 most similar battles | test2, 600 | +1 net | evidence vote +1. Jev and the vote differed on only 2 / 600 | copies the evidence |
| ③ | Hold position or push? (current system) | 720 battles, leave-one-scenario-out | +6 net | evidence vote +5; best pick in hindsight +25 | = vote |
| ④ | How should each unit group fight right now? (3–5 options) | 23 official maps, 115 | 77 wins | **random answers 74**; attack-move 53; hand rules 92 | ≈ random |
| ⑤ | Which preset tactic for the next 5 steps? (only when the value model is unsure) | test4, 1,000 | 527 wins | value model (default) 523; random 519 | +4, p = 0.61 |
| ⑨ | Of two tactics, which wins more here? | 73 scenarios with a known ≥ 3/5 gap | 45 correct | fixed rule *"keep attack-move"* 46; random 36.5 | = fixed rule |

<p align="center">
  <img src="docs/jev_map.svg" alt="Map of the nine places Jev was tried: for each, what Jev saw, its result, and the baselines with the same information" width="100%">
</p>

Why:
- **Choosing a tactic has almost nothing to gain. The gain is in per-unit actions, and that is where Jev can't act.**
  - *Headroom* here means: if you always picked the best option in hindsight, how many more battles would you win?
    - For hold-or-push, only +25 / 720 battles (3.5%).
    - For choosing from the tactic program library, +24 to +27 / 300.
    - Even a perfect chooser could not do much better, so it doesn't matter whether Jev, a vote, or a coin picks.
  - **Why so little: in most battles, every option ends the same way.**
    - At 2,717 recorded decision points, we replayed all 13 options to the end. Only 284 points (10%) had *any* option that changed win into loss or back.
    - Switching from hold to push at step 20 changed the result in 43 of 720 battles (25 won, 18 lost). The other 677 ended the same way.
  - **What does change the outcome is per-step execution: who shoots whom, and when to step back.** Every tactic option runs the same execution code underneath, so picking between options never touches it. On the same 720 battles:

    | Change | Wins | vs the full program |
    |---|---:|---:|
    | Full program (focus fire + kiting + hold) | 548 | – |
    | Push instead of hold (the choice Jev was asked to make) | 521 | −27 |
    | Turn off kiting | 505 | −43 |
    | Turn off focus fire | 494 | −54 |

    Replacing attack-move with the whole execution program was worth **+245 of 1,000** unseen battles (test6). That is about 10× the tactic choice.
  - **So the room is at the action level, the level of Q1, and Jev can't fill it there.** Focus fire is a joint assignment across units, and Jev's per-unit questions are answered independently. The right action depends on exact range, cooldown, and distance, and Jev barely tells actions apart. Code does both directly, which is why the approach that worked was having an LLM write the code.
- **Jev follows the evidence.** When we gave it similar battles, it agreed with the plain vote (② differed on 2 / 600). When we didn't, it did no better than random (④).

## Q3. Does Jev generalize to unseen battles?

Baselines here are the **default of the day** and **attack-move**. Each is compared on scenarios or seeds that played no part in designing the questions.

**Conclusion: No.** Jev's only large gain came on the maps its options were written for, and even there random answers did almost as well. On unseen data it never significantly beat the default, and once it was significantly worse.

| Where | Jev vs default | Same-information baseline |
|---|---|---|
| 23 official maps, where the exam options and their manual were written (④) | 77 vs attack-move 53 | random answers **74**: the gain is in the options, not the choice |
| Generated scenarios (rounds 2–3), opening program pick | 84 / 200; 92 / 200 with a newer library | random 84 / 94; lookup 85 / 89 |
| test2 (unseen), Jev replaces the lookup | **−4** (p = 0.73); **−24** (p = 0.009, significantly worse) | – |
| test2 (unseen), Jev with neighbor evidence (rounds 5–6) | +1 (p = 1.0); 0 (p = 1.0) | evidence vote +1 |
| test4 (unseen), Jev as mid-battle tie-breaker (⑤) | +4 (p = 0.61) | random pick 519, i.e. −4 vs the default |
| Fresh decision points, *"switch only if Jev says we're losing"* (⑧) | +5.42 on the batch the rule was picked on → **+0.06** on a fresh batch | always switch +2.13; HP-ratio gate +2.07 |

<sub>Sources: `results/winrate_now.md`, `results/iter4_report.md`–`iter6_report.md`, `iter9_report.md`, `iter11_report.md`, and the technical report.</sub>

What did generalize was the code-writing approach:

| Method | test6, 1,000 unseen battles | 23 official maps¹ |
|---|---:|---:|
| Attack-move | 47.5% | 53 / 115 |
| Hand rules (tuned on the official maps) | 49.0% | *92 / 115* |
| Value-guided tactic switching | 51.9% | 51 / 115 |
| LLM-written program, outcome feedback only (Grok-4.7) | 59.5% | 62 / 115 |
| **LLM-written program, source + trace feedback (Claude)** | **72.0%** | **65 / 115** |

<sub>¹ Reference only. The hand rules were picked by looking at these 23 maps: 39 flips and zero losses there, but on fresh battles only +15 over attack-move (p = 0.14). The Claude program never saw the official maps during development.</sub>

Paired comparisons on test6 (same scenario, same seed; exact sign test):

| | Flips (+) | Losses (−) | Net | p |
|---|---:|---:|---:|---:|
| Claude program vs attack-move | 305 | 60 | **+245** | < 0.001 |
| Claude program vs Grok program | 170 | 45 | **+125** | < 0.001 |

## Final answer: is Jev useful in micro?

**For acting, no.** It can't output per-unit actions (Q1), it doesn't pick tactics better than chance (Q2), and nothing it did generalized (Q3).

**What it is good at: judging the state.** At each recorded decision point, Jev was asked *"will we win from here?"* and given the 8 most similar past moments. Its AUC was **0.874**. That beat the HP ratio (0.835) and the average outcome of the same 8 examples (0.77–0.80), though not significantly. But a judgment only matters if some action can use it. SMAC micro has no retreat, reinforcement, or surrender. A rule that switched tactics only when Jev predicted a loss did not replicate on fresh data (+5.42 → +0.06).

**What actually works: an LLM writes the micro program, and the simulator checks it.**
- The current program is [`kb/library/code/general_claude.py`](kb/library/code/general_claude.py). It is about 150 lines and does five things:
  1. **Focus-fire allocation.** Priority = enemy DPS ÷ remaining effective HP. A damage ledger avoids overkill, and armor and type bonuses are counted.
  2. **Medivacs** heal, or retreat when threatened.
  3. **Baneling screening.** Melee units intercept Banelings heading for our ranged units.
  4. **Kiting.** Units step back during weapon cooldown when they out-range or out-speed the enemy.
  5. **Stall breaker.** If no one has taken damage for 10 steps, everyone attacks, because a timeout counts as a loss.
- **Feedback matters more than which model writes the code.** Grok saw only aggregate scores, and reached 59.5%. Claude read the simulator source, traced lost battles step by step, and re-ran a paired test after every edit, and reached 72.0%.
- The biggest single jump came from reading the source. The API doc said `can_attack(u, e)` meant "in range"; it actually means "visible". Units ordered to attack a distant target walked into the enemy line. Fixing that one assumption moved the program from **−100 to +64** (out of 720 battles).

**Did anything reach RL state of the art?** No. RL is at 96.9–100% on every one of these maps; our best systems lose whole maps outright. The table below is per map on the official maps, run in SMAClite with 5 seeds each. RL numbers are from SC2, where the built-in AI differs. For example, attack-move wins 5m_vs_6m in SMAClite, while SMAC's heuristic gets 0% there. Read across a row, not as a leaderboard.

| Map | Best published (SC2) | Attack-move | Jev exams (④) | Claude program |
|---|---:|---:|---:|---:|
| 3m | 100% | 5/5 | 5/5 | 5/5 |
| 2s3z | 100% | 5/5 | 5/5 | 5/5 |
| 3s5z | 100% | 5/5 | 5/5 | 5/5 |
| 5m_vs_6m | 100% | 5/5 | 5/5 | 0/5 |
| 3s_vs_5z | 100% | 0/5 | 5/5 | 0/5 |
| 10m_vs_11m | 96.9% | 0/5 | 0/5 | 5/5 |
| corridor | 100% | 0/5 | 5/5 | 0/5 |
| MMM2 | 100% | 0/5 | 0/5 | 0/5 |
| 3s5z_vs_3s6z | 100% | 0/5 | 0/5 | 5/5 |
| 27m_vs_30m | 100% | 1/5 | 3/5 | 4/5 |
| 6h_vs_8z | 98% | 0/5 | 0/5 | 0/5 |
| **All 23 maps** | – | 53 / 115 | 77 / 115 | 65 / 115 |

**Where a model like Jev could fit:** tasks with a few high-stakes decisions that can be described in words, where a judgment can be turned into an action like retreat, reinforce, or skip this fight. Full-game macro fits that. In JEV-Star's real-time SC2 macro games, Jev alone went 0 / 10, while Jev choosing among actions filtered by an LLM plan went **9 / 10** (external result). Small-scale SMAC micro is the opposite of that kind of task.

## How we'd use a judgment model next time

1. **Measure the headroom first.** Pick the best option per scenario on some seeds, then check it on others. If that is worth only a few percent, it doesn't matter who chooses.
2. **Always compare against "same information, no model".** Use three controls: a random pick among the same candidates, a plain vote over the same examples, and changing nothing.
3. **Confirm small wins on fresh seeds.** Variant g13 looked +7 on its selection seeds and was −14 on fresh ones (p = 0.049).
4. **Don't trust gains on the maps you tuned on.** That applies to both the hand rules and the Jev exams.

## Architecture evolution

```
A0  Exams + motor primitives      Jev answers tactical questions; primitives execute           (Q2 ④)
A1  Tactic program library        offline LLM forging per scenario cluster; online: nearest     (Q2 ①②⑨)
A2  Value-guided macro switching  every 5 steps, a GBDT value model may swap in 1 of 12 tactics (Q2 ⑤)
A3  LLM program synthesis (Grok)  act(obs, mem) in a sandbox, overriding A2 unit by unit
A4  LLM program synthesis (Claude) same runtime as A3; source reading + trace-driven dev loop   ← current
```

Each layer hands the units it doesn't command down to the layer below, so attack-move is always the last fallback. The technical report (in Chinese) covers all 12 Jev experiments: [docs/tech_report.html](docs/tech_report.html).

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
| `AGENTS.md` | Project conventions and evaluation rules |
