# Laya-MLX on StarCraft Micro (SMAClite)

Zero-shot `aac6fef/laya-mlx` (English 421M, 512 context) as a typed-decision policy on SMAClite.
No StarCraft II on this machine, so the runnable env is SMAClite, not official SMAC/SC2.
Paper columns are **published SMAC win rates** and are not from this run.

## This run

| Map | Policy | n | Win rate | Return | s/ep |
|---|---|---:|---:|---:|---:|
| 3m | jev | 2 | 100.0% | 20.00 | 17.60 |

## Paper baselines (official SMAC / SC2)

| Map | MAPPO | QMIX | Heuristic closest | HPN-QMIX | Source |
|---|---:|---:|---:|---:|---|
| 3m | 100.0% | 96.9% |  |  | Yu et al. MAPPO, median test win % |
| 8m |  |  |  |  | SMAC-Hard Table 3, 2M steps (under-trained vs full MAPPO) |
| 5m_vs_6m | 89.1% | 75.8% | 0.0% |  | MAPPO paper; original QMIX appendix heuristic=closest enemy |
| 2s_vs_1sc | 100.0% | 96.9% | 0.0% |  | MAPPO paper + QMIX appendix. Heuristic 0% because alternating fire is required |
| 2s3z | 100.0% | 95.3% | 90.0% |  | MAPPO paper + QMIX appendix |
| 3s_vs_5z |  | 87.0% | 0.0% |  | QMIX appendix Table 9; MAPPO paper did not report this map |
| 3s5z | 96.9% | 88.3% | 42.0% |  | MAPPO paper + QMIX appendix |
| 10m_vs_11m | 96.9% | 95.3% | 12.0% |  | MAPPO paper + QMIX appendix |
| MMM2 | 90.6% | 87.5% |  | 100.0% | MAPPO paper; HPN-QMIX ICLR 2023 (Hard/SuperHard 9/10 maps 100%) |
| 6h_vs_8z | 88.3% | 9.4% | 0.0% | 98.0% | MAPPO paper; HPN-QMIX ICLR 2023 |
| corridor | 100.0% | 84.4% | 0.0% | 100.0% | MAPPO paper; HPN-QMIX |
| 27m_vs_30m | 93.8% | 39.1% | 0.0% | 100.0% | MAPPO paper; HPN-QMIX |

## How to read this

- MARL numbers are after millions of environment steps. Laya here is **untrained on SMAC**.
- SMAClite preserves SMAC ranking but absolute win rates are not interchangeable with SC2 SMAC.
- `heuristic_closest` is the SMAC paper's built-in scripted baseline (attack nearest).
- `heuristic_focus` is a slightly stronger script: lowest-HP in-range, else walk toward nearest.
- Laya gets a compact English state and one `choice` question per living unit.
- `qwen_squad` picks an army command (FOCUS/NEAREST/KITE/BAIT/BALL); a dumb adapter issues unit actions.
- `jev` is TypeSafe Jev: one request per tick, one Choice per living unit over legal SMAC actions.
- `squad_*` is that adapter with a fixed command, no LLM.
