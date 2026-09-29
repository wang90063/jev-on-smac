# Laya-MLX on SMAC micro

Env: SMAClite (no StarCraft II). Model: `aac6fef/laya-mlx` English 421M, 512 context, **zero-shot**, not the typed-decisions fine-tune.
n=12 episodes/map except `laya_unit` on 2s3z (n=5). Win rate and mean return (SMAClite scales return to 20).

## This run vs paper baselines

Paper columns are **official SMAC / SC2**. They are not from this machine. Heuristic in the paper is attack-closest.

| Map | random | closest | focus | laya commander | laya unit | QMIX paper | MAPPO paper | Heuristic paper |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 3m Easy | 0% / 1.7 | **100% / 20** | **100% / 20** | **100% / 20** | 0% / 6.0 | 96.9% | 100% | (not in T2) |
| 2s3z Easy | 0% / 4.0 | **100% / 20** | 0% / 9.8 | 0% / 9.8 | 0% / 9.1 | 99% | 100% | 90% |
| 5m_vs_6m Hard | 0% / 1.6 | 0% / 6.3 | 0% / 5.6 | 0% / 3.9 | — | 70% | 89.1% | **0%** |
| 2s_vs_1sc alt-fire | 0% / 1.4 | 0% / 10.0 | 0% / 10.0 | 0% / 10.0 | — | 100% | 100% | **0%** |
| 3s_vs_5z kite | 0% / 3.2 | 0% / 4.9 | 0% / 4.6 | 0% / 4.5 | — | 87% | — | **0%** |

Commander latency ~61–86 ms/call. First flat-action adapter (v1, raw `atkE0` labels, no FOV) scored **0% on 3m** with return 4.6.

## Action-space tricks (SMAC paper)

From Samvelyan et al. 2019:

- Discrete only: `move[N/S/E/W]`, `attack[enemy_id]`, `stop`, `no-op`.
- **Dead units may only no-op; living units cannot no-op.**
- **`attack[id]` is legal only inside shooting range 6.** No attack-move on far enemies.
- Sight 9 > shoot 6, so agents **must walk before they can fire**.
- Joint action space is exponential in agent count (7–70 legal actions each). That is why SMAC is decentralised.
- Medivacs use `heal[agent_id]` instead of attack.
- Built-in heuristic = attack closest. It gets 90% on 2s3z and **0%** on 5m_vs_6m / 2s_vs_1sc / 3s_vs_5z — those maps exist specifically for kiting, alternating fire, surplus control.
- MAPPO/QMIX add **action masks** and death masking; they do not expand the discrete set.

Laya-specific (snake demo + hub config):

- Criteria must be a **dict of label → English description**, not bare IDs.
- Keep K in **3–5** (`choice:3-5` is the calibrated temperature bucket). `choice:11+` temperature is 0.10 and over-peaked.
- Option tokens share `head_max_len=192`. Dumping 6+N SMAC actions starves descriptions.
- Guard like snake: if the argmax is illegal, take argmax over the legal subset.

What we changed after v1 died on 3m:

1. If any shot is legal, **do not offer walk/stop** to Laya (paper: shot only in range; also shrinks K).
2. Commander asks one team question: **who to focus-fire**. Code executes `attack[focus]` if in range else walk toward it. This is Jev/Laya’s intended split: model decides, code acts.
3. Living agents never see `no-op`.

## Input tricks (SMAC paper)

From the same paper + SMAClite `get_obs` / `get_state`:

- Local obs: only units **inside sight 9**. Far allies and dead units are **indistinguishable** (we omit both).
- Per visible unit: distance, relative x/y, hp, shield, unit_type — **all divided by max** (sight 9 or map size).
- Own features: hp ratio, cooldown / max_cd, can-move N/S/E/W, last action.
- Visible allies’ **last actions** are in the vector.
- Attackable bit (in shoot range) is separate from “seen only”.
- Central state (training only): everyone, coords from **map centre**, allied cooldown, last actions of all agents.
- At t=0 on 3m, enemies sit ~15 units away, **outside sight**. A true local policy cannot see them yet.

Laya runtime trick: `build_sequence` **keeps the prefix and drops the tail** of the state. In-shot enemies and own hp are written first.

## How to read the numbers

- **3m**: after the paper tricks, Laya commander matches the scripted micro and the published MAPPO/QMIX ceiling. The v1 flat action head did not.
- **2s3z**: paper heuristic is closest, not lowest-HP. Our focus script and Laya (prompted to pick the weakest) both fail the same way. Closest still 100% here.
- **5m_vs_6m, 2s_vs_1sc, 3s_vs_5z**: paper heuristic is 0%. Laya tracks that scripted floor (damage, no win). QMIX/MAPPO only win these after millions of env steps (kiting, one-stalker-fires, 5v6 surplus). Zero-shot Laya does not invent those micros.
- **laya_unit** (Dec-POMDP, local FOV): 0% even on 3m. Spawn is outside sight; uncoordinated per-unit choices do not focus-fire.

So: as a **central typed decision** (who to shoot) plus a paper-faithful executor, Laya-MLX is about as strong as the SMAC built-in heuristic. It is not a trained MARL policy, and the maps that exist to beat that heuristic still beat it.
