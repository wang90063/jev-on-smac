# Qwen2.5-1.5B-Instruct-4bit as SMAC commander

Repo `harshatheg/Qwen-2.5-1B-RLCD` is the parallel-constrained decoder; weights are `mlx-community/Qwen2.5-1.5B-Instruct-4bit` (~850MB, 32k context). n=8.

## Win rate

| Map | closest script | Qwen+KB guard | Laya+KB guard |
|---|---:|---:|---:|
| 3m | 100% | **100%** | 100% |
| 2s3z | 100% | **100%** | 100% |
| 5m_vs_6m | 0% | 0% | 0% |
| 2s_vs_1sc | 0% | 0% | 0% |
| 3s_vs_5z | 0% | 0% (ret 5.7) | 0% (ret 5.7) |

Latency ~230–450 ms/call vs Laya ~60–90 ms.

## ICL retrieval (no recommend leak in live state)

Clean probe (playbook + one situation line, no numbers): 4/4 correct, p>0.96 (FOCUS / CLOSEST / ALTERNATE / KITE).

Live SMAClite state: Qwen almost always outputs **KITE**.
- 3m: raw KITE 152/152, guard rewrote to focus
- 2s3z: raw KITE 440, guard rewrote to closest
- 3s_vs_5z: raw KITE 344 / FOCUS 32 — this map actually wants kite, so retrieval is ok
- 5m: raw KITE 96 / FOCUS 16

Long context does **not** make live tactic ICL reliable. The 1.5B instruct model fits the playbook when the prompt is clean, then collapses to KITE once the battlefield numbers show up. Win rates that look good are still the composition guard + scripted executor, same as Laya.
