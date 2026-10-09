# Jev on SMAC: Can a Fast Choice Model Play StarCraft Micro?

> We set out to see if **Jev**, a fast model that picks among named options, could act as the policy in StarCraft multi-agent micro (SMAC).
> We went down four steps, each one prompted by why the last one failed, and compared every step with baselines that had the same information but no Jev.
>
> | Step | What Jev controlled | Result |
> |---|---|---|
> | 1. Every unit's action | Each unit's raw action, every 0.5 s step | **0 / 35 wins**, the same as random actions. Attack-move won 25. |
> | 2. Tactics per unit group | 2–6 named tactics per group (how to fight, whom to focus); code executes | **91 / 115** on the official maps. But random answers to the same questions won 74, and 4 hand-written rules built from the same knowledge won 92. The credit belongs to the code and the rules, not to Jev. |
> | 3. The same, on unseen battles | – | **196 / 400**, tied with the hand rules (196). Both fail together: the tactical knowledge was fitted to the official maps, and Jev added no judgment of its own. |
> | 4. Choosing on top of systems built to generalize | Library programs, value-model tactics, hold or push | Each system generalized better than the one before (**475 → 720 / 1,000** unseen battles). Jev never added anything on top. |
> | **Is Jev useful for micro?** | | **No.** Its one strength is judging *"will we win?"* (AUC 0.874, best of all methods, not significant), and in micro that judgment doesn't turn into wins. What worked: an LLM writes the micro **code**. |

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

## Setup and baselines

**Environment.** [SMAClite](smaclite/), a Python re-implementation of SMAC that runs without StarCraft II. One step = 8 ticks ≈ 0.5 s, and a timeout counts as a loss. The game waits for the policy, so latency costs wall-clock time, not wins.

**Battles.**
- **Official maps:** the 23 SMAC maps × 5 seeds = 115 battles. The hand rules and the exam questions in step 2 were written by looking at these maps, so for both, the official maps are in-sample.
- **Unseen battles:** procedurally generated scenarios with frozen splits: train (60), train2 (120), val (80), and test2–test6 (200 each). Each scenario is played with 5 seeds.
  - val was never used to write the exam questions or the hand rules. Each test set was run **exactly once**.
  - The generator drops fights that attack-move wins 5/5, and fights that both attack-move and a random policy lose 5/5. Every remaining fight is contested.

**Statistics.** Every comparison is paired by scenario and seed, with an exact sign test on flips vs losses.

**Baselines.** For Jev to count as useful at a decision, it has to beat the controls that share its information but not Jev. Otherwise the gain comes from what we put in the prompt, not from Jev's judgment. Every table uses these names:

| Baseline | What it does | Shares with Jev | Used in |
|---|---|---|---|
| **Attack-move** | Every unit attack-moves toward the enemy. The last fallback in every system here | – | all |
| **Random legal action** | A uniformly random legal action per unit per step | the same actions | step 1 |
| **SMAC heuristic** | Shoot the closest enemy in range (or the lowest-HP one: *focus*), else walk toward it | – | step 1 |
| **Random answers** / **random pick** | A uniformly random choice among exactly the options Jev saw | the same options | steps 2–4 |
| **Hand rules** | 4 fixed picks, written by looking at the official maps: whenever the question is open, gun lines kite, melee holds the choke, the laser aims at the bar, outer guns step aside | the same options and the same knowledge | steps 2–3 |
| **Lookup** / **evidence vote** | The closest cluster's program / the option with the best record among the similar battles shown to Jev | the same options and evidence | step 4 |
| **Best in hindsight** | The best option per battle, known after playing all of them. A ceiling | – | steps 3–4 |

## Step 1. Jev controls every unit's action

**Setup.** One Jev request per step, with one Choice per living unit.
- **Input:** every unit on both sides: type, HP, shield, position, range, speed, damage, weapon cooldown.
- **Options:** exactly that unit's legal actions.
  - stop;
  - move north / south / east / west, with the distance to the nearest enemy after the move;
  - attack enemy *j*, with its type, remaining HP, distance, and whether it is in range.
- **Output:** one action per unit, applied for 0.5 s.

**Result: Jev won none.** 7 official maps (3m, 8m, 5m_vs_6m, 2s3z, 3s5z, 3s_vs_3z, 10m_vs_11m) × 5 seeds; every policy plays the same battles.

| Policy | Wins / 35 | Jev vs this (flips / losses) |
|---|---:|---:|
| **Jev, every unit's action** | **0** | – |
| Random legal action | 0 | 0 / 0 |
| Attack-move | 25 | 0 / 25 |
| SMAC heuristic: shoot the closest | 25 | 0 / 25 |
| SMAC heuristic: focus the lowest HP | 30 | 0 / 30 |
| *External: [JEV-Star](https://github.com/sc2musa/Jev_Star), real SC2, Jev alone, 35 SMAC-Hard maps × 3* | *3 / 105* | – |

<sub>`python results/q1_unit_actor.py table`; raw rows in `results/q1_unit_actor.jsonl`. 745 requests, 1.23 s each end to end, 26 s per battle. The JEV-Star row is from that project's README.</sub>

**Why.** Jev's actions were no better than random ones. On 3m (seed 1), it walked all three Marines east (P = 0.95), then split their fire across all three enemies; the enemy didn't split, and won with 2 units left. Three candidate causes:
1. **The action space is large.** Each unit has 6–17 actions every 0.5 s, and a battle needs dozens of steps in a row to go right.
2. **The questions can't coordinate.** Questions in one request are scored independently ([docs](https://docs.typesafe.ai/cookbooks/parallel_questions)). Focus fire, the most valuable thing in micro, is a joint assignment of who shoots whom. A three-line rule, *focus the lowest HP in range*, wins 10m_vs_11m 5/5, where attack-move and Jev both lose 5/5.
3. **The differences between actions are numeric.** Range, cooldown, and distance decide the fight. Asked for P(win) after each of 13 actions at 300 recorded decision points, Jev's answers varied by a standard deviation of only 0.047 (card ⑦ below).

It is also slow at this scale. 1.23 s per request is longer than a 0.5 s step.

## Step 2. Reduce the dimensions: Jev picks tactics per unit group, code executes

**Why this step.** It removes all three candidate causes at once:
- Units are grouped by role, and each group gets 2–6 named tactics instead of per-unit actions every step.
- Code coordinates: one targeting rule makes the whole army focus the same enemy.
- Code does the numeric execution: who shoots when, who steps where.

This is how a human commander works, with control groups instead of per-unit clicks. It is also how hierarchical multi-agent RL methods such as RODE (ICLR 2021) shrink the action space on SMAC. And it fits Jev's design: a choice question with named options whose meanings differ clearly.

**Setup.** Units are split into a gun line (ranged), a melee line, and healers. At each step where a question is open, Jev gets one request with up to 7 independent Choices:

| Question | Options |
|---|---|
| How should the gun line fight? | stand and shoot / kite (stutter step) |
| What should the melee line do? | charge / hold the choke (/ snipe suicide units) |
| Which targeting rule should the army use? | front line / weakest in range / clump / heaviest / guns first / healer first |
| Where should a firing laser aim? | the densest enemy / the perpendicular bar that hits the most bodies |
| Before contact, should the outer guns step aside? | stay / step |
| Two enemies in range are within one shot of each other: which first? | either one |
| Which wounded ally should the healer heal? | up to 6 wounded allies |

- **Input:** the battle state, plus physical facts attached to each option. Examples: *"if this line stands, the melee reaches it before the next shot"*, speed advantage, numbers, contact, and for each targeting rule the enemy it picks and how tanky it is.
- **Output:** one option per question, with probabilities. Code compiles the picks into every unit's action, every step.
- **Gate:** a question reaches Jev only if pinning one of its options beat attack-move somewhere on the official maps. Otherwise code answers with its default.
- **Cost:** 10.5 requests per battle (0.23 per step), instead of 1 per step.

**Result: it works on these maps, but Jev is not the reason.**

| | Same 35 battles as step 1 | 23 official maps (115) |
|---|---:|---:|
| Attack-move | 25 | 53 |
| Random answers to the same questions | 34 | 74 |
| **Jev's answers** | **35** | **91** |
| Hand rules (same options, same knowledge) | 35 | 92 |

- Jev vs random answers: **+17 / −0** (p < 0.001).
- Jev vs hand rules: +1 / −2. Same outcome in 112 of 115 battles.

<sub>Rerun on the current code: `python results/baseline_rerun.py table`.</sub>

Lowering the dimensions moved Jev from 0 to 35 on the same battles. That fits cause 1 but does not prove it: random answers went to 34 as well, so the code made most of the jump. Jev did beat random answers. But 4 fixed rules, written from the same official maps that the questions and their option text came from, did just as well with no requests at all.

## Step 3. Does it hold on unseen battles?

**Result: no.** On val, battles never used to write the questions or the rules:

| val, 400 battles | Wins | vs attack-move | Jev vs this |
|---|---:|---:|---:|
| Attack-move | 176 | – | +43 / −23 (p = 0.019) |
| Random answers | 189 | +13 | +37 / −30 (p = 0.46) |
| **Jev's answers** | **196** | +20 | – |
| Hand rules | 196 | +20 | +20 / −20 (p = 1.0) |

Jev's edge over random answers fell from +17 / 115 to **+7 / 400**. It still tied the hand rules exactly. On test6 (1,000 unseen battles), the hand rules won 490 vs attack-move's 475, also not significant.

**Why: the tactical knowledge was fitted to the official maps, and Jev added none of its own.** We pinned each option of the menu for the whole battle and played every battle again. The best pin per battle, in hindsight, is a ceiling for what any answerer could get from this menu:

| | Official maps (115) | val (400) |
|---|---:|---:|
| The menu's ceiling: battles over attack-move | +40 | +67 |
| captured by Jev's answers | **38** | **39** |
| captured by the hand rules | 39 | 36 |
| captured by random answers | 23 | 37 |
| Battles attack-move won and Jev lost | 0 | 23 |
| The best option on the official maps (kite), over attack-move | +20 | +1 |

<sub>`python results/baseline_rerun.py force` then `headroom`; 12 pins (6 questions, plus each of the 6 targeting rules). On val many pins flip battles both ways (e.g. *guns first* +25 / −26), so part of the +67 is chance rather than usable room.</sub>

- **The knowledge didn't transfer.** On the official maps, the gun-line kite was the option that won; on val it was worth +1. The hand rules carry exactly this knowledge, and they lost their edge with it.
- **Jev didn't make up for it.** On val the menu still had room, and Jev captured as much of it as random answers did (39 vs 37). On the official maps it captured 38 of 40, because its option text and its gate were written from those maps.
- **The gate wasn't what held it back.** The gate closed 5 kinds of question: formation, kite style, bait, stand, and mark. No pin of theirs had beaten attack-move on the official maps, but they had opened in only 5–15 of the 115 battles there, so we lifted the gate and pinned each of their options on val.
  - The ceiling rose only from +67 to **+73** of 400.
  - Most closed options never changed a result. Of those that did, opening the formation lost more than it won (+4 / −14), and mark was a wash (+4 / −3).
  - Random answers with the gate lifted won 186, versus 189 with it.
  - Lifting the gate added more ways to lose than to win. (`python results/baseline_rerun.py relax`; nested kinds were pinned under their parent option.)

Tactics fitted to the battles they were found on was a pattern from the start:
- **Round 2:** an LLM forged the best program for each training scenario, worth +56 battles in-sample. Moved to other scenarios, 4 of the 33 stayed positive. On the test set the library lost to attack-move (84–85 vs 90), whether Jev, a lookup, or a coin picked the program.
- **Round 4:** a tree trained to imitate an offline search was +18 in its training battles, −10 on fresh seeds, and −21 on test2.
- **Round 16:** a code edit +7 on its selection seeds was −14 on fresh ones (p = 0.049).

## Step 4. Make the tactics generalize, then let Jev choose among them

**Why this step.** If the tactics overfit, build systems that generalize, then give Jev the choice among their candidates. We built three, each judged on unseen battles:
- **Tactic library + lookup:** an LLM forges a program per scenario cluster, and a program is kept only if it wins on fresh seeds.
- **Value switching:** every 5 steps, a value model trained offline may swap in 1 of 12 tactics.
- **LLM-written micro code:** a program `act(obs, mem)` written by Grok, then by Claude, developed against the simulator.

**Result: each system generalized better than the one before. Jev on top never added anything.**

| System | val (400) | test6 (1,000) | Jev's role on top of it | Jev | Same-information control |
|---|---:|---:|---|---:|---|
| Attack-move | 176 | 475 | – | – | – |
| Library + lookup | 184 | – | ① pick the program instead of the lookup (test2, 600) | −4, p = 0.73; hinted library **−24**, p = 0.009 | random pick −26 / −18 |
| | | | ② same, plus each program's record in the 8 most similar battles | +1 | evidence vote +1; Jev and the vote differed on 2 / 600 |
| Value switching | 190 | 519 | ⑤ pick the tactic when the value model is unsure (test4, 1,000) | +4, p = 0.61 | random pick −4 |
| Grok program | 217 | 595 | not tested | – | – |
| **Claude program** | **247** | **720** | ③ hold position or push at the start (720, leave-one-scenario-out) | +6 | evidence vote +5; *best in hindsight +25* |

<sub>val rerun on the current code (`results/baseline_rerun.py`). test6 was used once, in rounds 15–16. Jev rows: `results/iter4_report.md`–`iter16_report.md`.</sub>

**Why: choosing among tactics has almost nothing to gain. The gain is in per-unit actions, and that is where Jev can't act.**
- *Headroom* here means: if you always picked the best option in hindsight, how many more battles would you win?
  - For hold-or-push, only +25 / 720 battles (3.5%).
  - For choosing from the tactic program library, +24 to +27 / 300.
  - Even a perfect chooser could not do much better, so it doesn't matter whether Jev, a vote, or a coin picks.
- **In most battles, every option ends the same way.**
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
- **So the room is at the action level, where step 1 failed.** Code fills it directly, which is why the approach that worked was having an LLM write the code.

All nine places Jev was tried, with what it saw and its controls:

<p align="center">
  <img src="docs/jev_map.svg" alt="Map of the nine places Jev was tried: for each, what Jev saw, its result, and the baselines with the same information" width="100%">
</p>

## Conclusion: is Jev useful in micro?

**No, not for acting.** It can't output per-unit actions (step 1: 0 / 35). As a tactic chooser it matched hand rules written from the same knowledge, on the official maps and off them (steps 2–3). And it added nothing on top of systems that do generalize (step 4).

**Its one strength: judging the state.** At each recorded decision point, Jev was asked *"will we win from here?"* and given the 8 most similar past moments. Its AUC was **0.874**. That beat the HP ratio (0.835) and the average outcome of the same 8 examples (0.77–0.80), though not significantly. But a judgment only matters if some action can use it, and SMAC micro has no retreat, reinforcement, or surrender. A rule that switched tactics only when Jev predicted a loss did not replicate on fresh data (+5.42 → +0.06).

**Scoreboard: every system on the same battles.** All rows except test6 were rerun on the current code.

| System | Jev? | Level | 23 official maps (115) | val (400, unseen) | test6 (1,000, unseen, run once) |
|---|:-:|---|---:|---:|---:|
| Attack-move | | floor | 53 | 176 | 475 |
| Random answers | | tactic | 74 | 189 | – |
| **Jev's answers (step 2)** | ✓ | tactic | **91**¹ | 196 | – |
| Hand rules | | tactic | **92**¹ | 196 | 490 |
| Library + lookup | | tactic | 51 | 184 | – |
| Value switching | | tactic | 51 | 190 | 519 |
| Grok program | | code | 62 | 217 | 595 |
| **Claude program** | | code | 65 | **247**² | **720** |

<sub>¹ In-sample: built by looking at these 23 maps. ² The Claude program was checked once on val before its single test6 run. Data: `results/rerun/`.</sub>

On the maps they were built from, the exams and the hand rules lead (91 and 92 vs 65). On unseen battles the order flips: the Claude program beat Jev's answers 247 vs 196 on val (92 flips, 41 losses, p < 0.001), and beat attack-move by +245 on test6 (305 / 60, p < 0.001).

**What actually works: an LLM writes the micro program, and the simulator checks it.**
- The current program is [`kb/library/code/general_claude.py`](kb/library/code/general_claude.py). It is about 150 lines and does five things:
  1. **Focus-fire allocation.** Priority = enemy DPS ÷ remaining effective HP. A damage ledger avoids overkill, and armor and type bonuses are counted.
  2. **Medivacs** heal, or retreat when threatened.
  3. **Baneling screening.** Melee units intercept Banelings heading for our ranged units.
  4. **Kiting.** Units step back during weapon cooldown when they out-range or out-speed the enemy.
  5. **Stall breaker.** If no one has taken damage for 10 steps, everyone attacks, because a timeout counts as a loss.
- **Feedback matters more than which model writes the code.** Grok saw only aggregate scores, and reached 59.5% on test6. Claude read the simulator source, traced lost battles step by step, and re-ran a paired test after every edit, and reached 72.0%.
- The biggest single jump came from reading the source. The API doc said `can_attack(u, e)` meant "in range"; it actually means "visible". Units ordered to attack a distant target walked into the enemy line. Fixing that one assumption moved the program from **−100 to +64** (out of 720 battles).

**Where a model like Jev could fit:** tasks with a few high-stakes decisions that can be described in words, where a judgment can be turned into an action like retreat, reinforce, or skip this fight. Full-game macro fits that. In JEV-Star's real-time SC2 macro games, Jev alone went 0 / 10, while Jev choosing among actions filtered by an LLM plan went **9 / 10** (external result). Small-scale SMAC micro is the opposite of that kind of task.

## How we'd use a judgment model next time

1. **Measure the headroom first.** Pick the best option per scenario on some seeds, then check it on others. If that is worth only a few percent, it doesn't matter who chooses.
2. **Always compare against "same information, no model".** Use four controls: a random pick among the same candidates, a plain vote over the same examples, fixed rules written from the same knowledge, and changing nothing.
3. **Confirm small wins on fresh seeds.** Variant g13 looked +7 on its selection seeds and was −14 on fresh ones (p = 0.049).
4. **Don't trust gains on the maps you tuned on.** That applies to both the hand rules and the Jev exams.

## Architecture evolution

```
A0  Exams + motor primitives      Jev answers tactical questions; primitives execute           (step 2)
A1  Tactic program library        offline LLM forging per scenario cluster; online: nearest     (step 4 ①②⑨)
A2  Value-guided macro switching  every 5 steps, a GBDT value model may swap in 1 of 12 tactics (step 4 ⑤)
A3  LLM program synthesis (Grok)  act(obs, mem) in a sandbox, overriding A2 unit by unit     (step 4)
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

# Rerun every baseline in this README (scoreboard, steps 1-3)
python results/baseline_rerun.py local && python results/baseline_rerun.py jev && python results/baseline_rerun.py table
python results/baseline_rerun.py force && python results/baseline_rerun.py headroom
python results/q1_unit_actor.py run --policies dummy,closest,focus,random_legal,jev_unit && python results/q1_unit_actor.py table

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
