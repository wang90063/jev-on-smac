# CentralMicro vs closest (SMAClite, n=8)

One central controller, pairwise focus fire, no LLM, no composition-guard on an LM.
Kite only when the army is pure ranged vs melee. Sticky focus = most guns, then lowest HP.

| Map | paper | micro WR | closest WR | micro ret | closest ret |
|---|---|---:|---:|---:|---:|
| 3m | Easy | **100%** | 100% | 20 | 20 |
| 2s3z | Easy | **100%** | 100% | 20 | 20 |
| MMM | Hard | **100%** | 0% | 24.4 | 11.7 |
| 8m | Easy | 0% | 0% | 11.6 | 10.7 |
| 3s5z | Hard | 0% | 0% | 10.3 | 9.3 |
| 3s_vs_5z | Hard | 0% | 0% | 8.4 | 4.9 |
| 5m_vs_6m | Hard | 0% | 0% | 4.9 | 6.3 |
| 10m_vs_11m | Hard | 0% | 0% | 8.2 | 12.5 |
| MMM2 | Super Hard | 0% | 0% | 9.2 | 7.8 |
| 3s5z_vs_3s6z | Super Hard | 0% | 0% | 12.2 | 9.9 |
| 27m_vs_30m | Super Hard | 0% | 0% | 6.9 | 11.9 |
| corridor | Super Hard | 0% | 0% | 15.0 | ? |
| 2s_vs_1sc | micro-trick | 0% | 0% | 5.7 | 10.0 |

SMAClite built-in attack-move beats even closest on 8m and every Super Hard map. Official SMAC QMIX 8m is ~100%; this env is harsher. MMM is the one Hard map we beat closest 100% vs 0% (medivac + focus). Super Hard still unsolved without RL or map-specific choke scripts.
