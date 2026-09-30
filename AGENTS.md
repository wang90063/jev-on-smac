# 改战术

代码负责走位。战术分两层：离线锻造负责创造，在线挑选负责执行。同一条条件每张图都用，不要这张图开、那张图关。条件只用速度、射程、人数、隘口这类物理量，不写地图名。

## 在线：Jev 挑，代码走（`jev_smac_policy.py`）

- Dummy 就是每道题都选默认答案的 Jev，不参加考试。
- 菜单列表（`ranged_jobs`、`melee_jobs` 这类）里有两个选项，Jev 才考试；只剩一个时，代码直接执行。
- 只有登记在 `EXAM_EVIDENCE` 里的考题才发给 Jev。一道题要登记，先用 Force 把某个选项钉住，和 Dummy 打同一个种子，并且打赢过。
- **在线默认是 `OnlinePolicy`（最近簇）**：第三轮战术库 + 最近簇 + `none` 兜底。Jev（`jev2`/`jev3` 挑法）是可选项，要替代默认，必须在 test2 的配对统计中显著赢过最近簇；第五轮它只做到持平（净 +1，p=1.0）。
- `LibraryPolicy`：按物理特征找到最近的场景簇，取簇里入库的程序作为候选，另外永远加一个 `none`（不用任何程序，走的是和 Dummy 完全一样的代码路径），让 Jev 挑一个；挑中的程序负责回答所有考题。对局中不许复制模拟器状态。人工规则没有特殊待遇，和锻造出的程序一样要过入库门槛。

## 离线：锻造战术程序（`tactic_dsl.py`、`forge.py`、`scenarios.py`）

1. 战术程序是一个"物理条件 → 考题选项"的规则列表，格式和可用词表都在 `tactic_dsl.py`。程序在开放菜单下运行，好不好由模拟器评判，不由菜单上的限制条件判断。
2. `forge.py cluster` 先把 train 场景按开局物理特征分簇，再让 Codex 当前配置的模型（`~/.codex/config.toml` 里的 `model`，可用 `FORGE_MODEL` 覆盖）为每一簇写程序。入库门槛：
   - **选拔**：程序在簇内所有场景上跑种子 1–5，按相对 Dummy 的净胜局加总打分；原菜单限制和开放菜单两种模式都试，取分高的。
   - **确认**：选出的程序再到簇内所有场景上跑种子 6–10，净胜局也必须为正，才写进 `kb/library/cluster_programs.json`。
   - 人工规则也走这一套选拔和确认。第二轮按单个场景锻造的旧库（`programs.json`）只留作对照。
3. 新的走位原语（新 job、新 target 规则、新考题）写进 `jev_smac_policy.py`，只在 `_open_menu` 下出现，不能改变 Dummy 的行为。
4. 泛化以 test2（`results/scenarios/test2.json`，120 个场景，已冻结）的配对统计为准；test（40 个场景）和 23 张官方图只作参考，因为前者样本太小，后者是人工规则被挑出来的地方。

## 每次改动都要跑

- `python results/_regress.py trace --policies dummy default force:ranged=stutter --out new.json --compare old.json --actions-only`：确认 Dummy 的逐步动作没变。
- `python results/_regress.py gate`：Dummy 在官方图上不许有任何一局从赢变输。
- `python results/_regress.py holdout --split test2 --write out.jsonl`，再用 `python results/_regress.py paired --files <基线> out.jsonl` 看相对 Dummy 的翻盘和丢盘，以及 p 值。泛化结论以 test2（120 个场景 × 5 局）的配对统计为准，40 个场景的 test 集样本太小，只作参考。
- 离线搜索（`search.py`）会复制模拟器状态，只能用来估计上限和给蒸馏打标签，永远不能用在对局里。

Force 是测试用的客户端，把某一个选项钉死，不调用 Jev。Cookbook 是考试题里对每个选项的说明，只写这个选项会让代码做什么、在什么物理条件下出现，不写「这张图请选它」。
