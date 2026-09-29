# SMAClite tactics freeze

Gate: a compiler may appear on a Jev exam only if a force run beats dummy
on the same seed. Dummy is always attack-move / charge / hold_choke.
Do not invent NESW. Do not add per-map ifs. One architecture.

Live tactic names live in `agenda.live_tactic`. They are physics classes,
not map names. Motor compiles the default. Jev only sits an exam when two
legal compilers remain.

## Classes that already win (motor 15 maps, 6 tactics)

These are not 15 tactics. Dummy already wins them. Lift means: name the
class, keep the real exam, close the fake one.

| Class | Maps | Motor default | Real exam | Fake exam (now closed) |
|---|---|---|---|---|
| `stack_trade` | `3m` `8m` `25m` `5m_vs_6m` `8m_vs_9m` `10m_vs_11m` `27m_vs_30m` `MMM` | `stack` (MMM: + `heaviest`) | `target` when two rules remain | second stance. Only `stack` is legal. |
| `mixed_commit` | `2s3z` `3s5z` | `stack` + `charge` | `target` | `stutter` while allied melee is tanking. Physics veto already forced `stack`; the exam was theater. |
| `funnel` | `corridor` | `hold_choke` | `melee` (`hold_choke` vs `charge`) | none |
| `cycle` | `2s_vs_1sc` | dead-zone stagger | none | `stutter` vs a building. Cycle owns the motor. |
| `splash_clump` | `2c_vs_64zg` `1c3s5z` | `stack` + `clump` | `target` | `stutter` behind tanks |
| `detonate` | `bane_vs_bane` | bombs `charge` the clump | `target` | `hold_choke` for suicide units. Bombs do not camp a choke. |

What Jev actually sees on these maps after the lift:

- Marine trades: `live_tactic=stack_trade`, only `target` is an exam.
- Mixed with tanks: `live_tactic=mixed_commit`, guns stay stacked, `target` is the exam.
- MMM is bio guns, not mixed melee: `stack_trade` + heaviest. Colossus maps are `splash_clump`.
- Corridor: `live_tactic=funnel`, Jev may confirm `hold_choke` (override count was 0; motor already wins).
- Colossus / our bombs: named default plus `target` / `formation`.

That is the generalization: an unseen map with the same roles, speed, and
choke physics gets the same named tactic. Stance is not a free compass.

## Classes Jev already flips (4 maps)

Dummy loses. Force `ranged=stutter` beats dummy. So the exam is legal.

| Class | Maps | Dummy | Jev override | Compiler |
|---|---|---|---|---|
| `outrun_kite` | `3s_vs_3z` `3s_vs_4z` `3s_vs_5z` | `stack` dies | `stack -> stutter`, kite `all` | faster guns, no allied tanks |
| `leftover_kite` | `3s5z_vs_3s6z` | `stack` dies after tanks trade | leftover `stutter` + `bait_one` | stutter is closed while tanks tank. It opens at leftover (force t=28 `stack->stutter` wins 20.35). After tanks die the live name is `outrun_kite`. Kite default is `all`; `bait_one` is legal only after every enemy gun is dead (a bait with a live enemy gun lost). |

`who_kites` stays on the kite exam: `all` / `bait_one` (no enemy guns left, 2+ guns).
Code still compiles walk/fire. Equal-speed is not in this set.

## Classes with no winning compiler (4 maps)

Tried, then closed. Dummy seed=1 bars. Do not reopen until a force run
beats these numbers.

| Class | Map | Dummy bar | Tried compiler | Result | Why it is not an exam |
|---|---|---|---|---|---|
| `equal_speed_trade` | `2m_vs_1z` | 5.44 leftover zealot 52 HP | hold-ring / stutter / hold-gunline / bait_one | 4.61 / 2.33 / 4.61 / 4.61 | Attack-move is continuous; discrete hold misses mid-step shots. 2 marines cannot out-DPS 150 ehp. |
| `equal_speed_trade` | `6h_vs_8z` | 11.46 leftover 3 | stutter / `formation=open` / fan-shoot / bait_one | 2.15 / 0.16 wipe / 9.27 / 8.18 | hydras do not outrun; any peel skips shots and the surround still lands |
| `stack_trade` (healer on) | `MMM2` | 10.36 leftover 8 / 422 | extra-tank hold-behind / medic-dive / fade | 6.04 / 6.12 / 5.54 | Extra tank + living healer: focusing the extra marauder is healed off. Motor commits the whole ball (heaviest still default). Medic glue is physics, not an exam. Still a loss. |
| `charge_bombs` | `so_many_baneling` | 6.08 leftover 17 | snipe / `bait_two` / slot-spread / keep / hold | 5.68 / 1.62 / 2.03 | Engine splash only hits the other faction. Wad-snipe cannot chain. Dummy spread+charge is still best. |

Inventing a new tactic here means writing a compiler that beats those bars
on dummy-vs-force, then opening the exam. Naming a losing compiler and
letting Jev pick it is not a tactic.

## What is not a tactic

- NESW, orbit, hold-ring, per-unit questions.
- A second stance on marine maps.
- `stutter` while allied melee is tanking and guns are not in blades.
- `stutter` vs static buildings.
- `snipe` vs banelings, until it beats 6.08.
- Map-name branches.

Motor keeps physics: mask, cooldown, 0.5s stand, range, edge, attack-move,
healer glue (follow cover, heal inside a comfortable leash not max range).
Those transfer to unseen maps. Hidden `if` inside stutter does not.
Extra-tank hold-behind is off while an enemy healer is alive: the heal
undoes tank-focus, so the ball walks in together.

## How to add a tactic later

1. Write a compiler (`execute_*`) with no map name.
2. Force it vs dummy, same seed. Must beat the dummy bar.
3. Add it as a legal job in `ranged_jobs` / `melee_jobs` / `formation_jobs`
   using physics predicates (speed, roles, choke, blast).
4. Name it in `_live_tactic`.
5. Only then may Jev sit the exam.

## Exam evidence (enforced in code: `EXAM_EVIDENCE`)

Only these kinds reach Jev. Run `python results/_regress.py force --kinds <kind>[=<option>]`;
rows land in `results/force/`. A kind not in `EXAM_EVIDENCE` still compiles,
answered with the code default, the same way Dummy answers it.

| Exam | What the option makes code do | Physics that opens it | Force beat Dummy |
|---|---|---|---|
| `ranged` | `stutter`: guns stand to shoot, walk away while reloading | faster guns vs melee, no allied tanks, no buildings | yes |
| `melee` | `hold_choke`: blades sit the neck and let the enemy come through | outnumbered melee in a choke or pocket | yes |
| `target` | `guns`: focus enemy guns before enemy melee | enemy has both guns and melee | yes |
| `bar` | `bar`: laser aims where its perpendicular bar touches the most bodies | a laser is firing and bar pick ≠ neighbor pick | yes |
| `wing` | `step`: outer guns take one sideways step before contact | gun vs gun, they have more bodies, our line narrower than our reach | yes |
| `tie` | cover the other of two bodies within one shot of each other | two enemies in range, HP gap ≤ one shot | mixed: wins some seeds, loses others |
| `heal` | healer works on the chosen wounded ally | healer alive, 2+ wounded | mixed |

Closed (no Force win on 23 maps × 5 seeds): `formation`, `kite` (tested under
`ranged=stutter`), `bait` (under `melee=snipe`), `stand` (under
`ranged=stutter`; `shoot` lost 3s_vs_5z 5/5), `mark`. `line`, `span`,
`bomb`, `blade` were never built by the catalog and are removed.

## Tactic programs (round 2)

A program is an ordered list of `{"when": {physical feature: value}, "set": {exam: pick}}`
plus an `else`. Each tick the first matching rule is merged over `else`; exams it
does not set take the code default. Vocabulary: `tactic_dsl.FEATURES` (conditions)
and `tactic_dsl.SETTABLE` (picks). No map names anywhere.

Programs run on the open menu (`_open_menu`): every job the motor can execute is
legal, and the simulator, not a hand gate, decides if it is good. Primitives added
for programs only:

| Pick | What code does |
|---|---|
| `ranged=hold` | guns stand ground and shoot what walks into range; never chase |
| `ranged=fall_back` | guns walk back to the rally point or choke, then hold |
| `melee=hold` | melee stands and hits only what comes into reach |
| `target=threat` | focus the enemy with the most damage per second per remaining health |
| `wounded=rotate` | a unit under 40% health that an enemy can reach steps out of reach |

Library entries (`kb/library/programs.json`): program, start features, wins on the
fight it was written for, and a `transfer` table of wins vs Dummy on every train fight.

## Library gate (round 3)

A program enters `kb/library/cluster_programs.json` only if, over every train
fight in its physics cluster, it beats Dummy in net wins on seeds 1-5 (selection)
and again on fresh seeds 6-10 (confirmation). Hand rules take the same gate and
get no reserved slot. Online, the candidate list always ends with `none`, which
runs the exact Dummy path, so a pick can fall back to plain attack-move.
