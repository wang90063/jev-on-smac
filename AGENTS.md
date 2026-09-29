# 改战术

代码负责走位。战术分两层：离线锻造负责创造，在线挑选负责执行。同一条条件每张图都用，不要这张图开、那张图关。条件只用速度、射程、人数、隘口这类物理量，不写地图名。

## 在线：Jev 挑，代码走（`jev_smac_policy.py`）

- Dummy 就是每道题都选默认答案的 Jev，不参加考试。
- 菜单列表（`ranged_jobs`、`melee_jobs` 这类）里有两个选项，Jev 才考试；只剩一个时，代码直接执行。
- 只有登记在 `EXAM_EVIDENCE` 里的考题才发给 Jev。一道题要登记，先用 Force 把某个选项钉住，和 Dummy 打同一个种子，并且打赢过。
- `LibraryPolicy`：从战术库里按物理特征找最近的几个程序，让 Jev 挑一个，然后由这个程序回答所有考题。对局中不许复制模拟器状态。

## 离线：锻造战术程序（`tactic_dsl.py`、`forge.py`、`scenarios.py`）

1. 战术程序是一个"物理条件 → 考题选项"的规则列表，格式和可用词表都在 `tactic_dsl.py`。程序在开放菜单下运行，好不好由模拟器评判，不由菜单上的限制条件判断。
2. `forge.py` 让 Codex 当前配置的模型（`~/.codex/config.toml` 里的 `model`，可用 `FORGE_MODEL` 覆盖）在 train 场景上写程序，模拟器跑 5 个抖动种子打分。赢过 Dummy 的程序存进 `kb/library/programs.json`，并测它在其他场景上能不能迁移。
3. 新的走位原语（新 job、新 target 规则、新考题）写进 `jev_smac_policy.py`，只在 `_open_menu` 下出现，不能改变 Dummy 的行为。
4. 泛化只看 test 集（`results/scenarios/test.json`，已冻结）。23 张官方图只作参考，因为人工规则就是从这些图上挑出来的。

## 每次改动都要跑

- `python results/_regress.py trace --policies dummy default force:ranged=stutter --out new.json --compare old.json --actions-only`：确认 Dummy 的逐步动作没变。
- `python results/_regress.py gate`：Dummy 在官方图上不许有任何一局从赢变输。
- `python results/_regress.py holdout --write out.jsonl`：在 test 集上和 `results/iter2_baseline.jsonl` 对比。

Force 是测试用的客户端，把某一个选项钉死，不调用 Jev。Cookbook 是考试题里对每个选项的说明，只写这个选项会让代码做什么、在什么物理条件下出现，不写「这张图请选它」。
