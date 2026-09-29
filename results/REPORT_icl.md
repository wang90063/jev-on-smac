# ICL playbook on SMAClite

Knowledge base: [`kb/smac_micro.txt`](/Users/wangzhi/Desktop/code/jev/kb/smac_micro.txt).
Laya is not a few-shot LLM. ICL here means: tactics go in the **choice question** (state tail is truncated). Laya picks `focus | closest | alternate | kite`. Code executes. A composition guard overrides when the pick contradicts the KB (marines must not alternate).

n=8. Same English `laya-mlx` as before.

## Win rate / return

| Map | closest script | ICL+KB commander | v2 no-playbook | QMIX paper |
|---|---:|---:|---:|---:|
| 3m | 100% / 20 | **100% / 20** | 100% / 20 | 96.9% |
| 2s3z | 100% / 20 | **100% / 20** | 0% / 9.8 | 99% |
| 5m_vs_6m | 0% / 6.3 | 0% / 5.6 | 0% / 3.9 | 70% |
| 2s_vs_1sc | 0% / 10.0 | 0% / 8.8 | 0% / 10.0 | 100% |
| 3s_vs_5z | 0% / 4.9 | 0% / 5.7 | 0% / 4.5 | 87% |

## Did Laya actually retrieve the tactic?

Raw choice vs what the KB says. Guard = times we overrode.

| Map | KB tactic | Laya raw | Guarded / executed |
|---|---|---|---|
| 3m | focus | focus 120, **alternate 32** | focus (guard 32) |
| 2s3z | closest | closest 176, **alternate 164**, focus 100 | closest (guard 164) |
| 2s_vs_1sc | alternate | mixed alternate/focus | still 0% win |
| 3s_vs_5z | kite | **100% alternate** | kite (guard 376) |
| 5m_vs_6m | focus | focus 100% | focus, still 0% |

## What this means

ICL **does not** make Laya a MARL agent. It often picks `alternate` even for 3v3 marines or stalker-zealot mixes. The gain on **2s3z (0% → 100%)** is the KB guard forcing `closest`, which is the paper heuristic.

Spine / kite / 5v6 still lose: those need the real stutter-step and surplus control, not a paragraph in context. QMIX wins them after millions of steps; a 512-token encoder reading a playbook does not.

Files: [`kb/smac_micro.json`](/Users/wangzhi/Desktop/code/jev/kb/smac_micro.json), [`smac_laya_policy.py`](/Users/wangzhi/Desktop/code/jev/smac_laya_policy.py).
