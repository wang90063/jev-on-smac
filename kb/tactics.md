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
