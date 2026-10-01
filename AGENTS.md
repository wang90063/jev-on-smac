# 改战术

走位由代码执行，代码有两种来源：人写的走位原语（`jev_smac_policy.py`），以及大模型写、在沙箱里运行的微操程序（`code_policy.py`）。战术分两层：离线锻造负责创造，在线负责执行。同一条条件每张图都用，不要这张图开、那张图关。条件只用速度、射程、人数、隘口、血量这类物理量，不写地图名。对局中永远不复制模拟器状态。

## 在线默认：`WrittenOnlinePolicy`（第十五轮起）

- 运行 `kb/library/code/general.py`：一个由 Grok-4.7 写、经模拟器反馈迭代出来的通用微操程序，主要做四件事：
  - 医疗艇治疗或后撤；
  - 远程单位补刀分配，避免溢出伤害，优先打自爆兵和治疗单位；
  - 近战拦截冲向我方远程的自爆兵；
  - 射程占优时，冷却期间后撤拉扯。
- 程序没有下令的单位，执行 `ValueOnlinePolicy` 的动作，所以新默认 = 价值模型策略 + Grok 写的微操覆盖层。
- 切换依据（`results/iter15_report.md`）：
  - val：相对上一任默认 +27（44 / 17，p=0.001）；
  - **test5（200 个场景 × 5 局，只用一次）：相对上一任默认 +65（112 / 47，p<0.001），相对 Dummy +141**。
- 程序接口：`def act(obs, mem) -> {unit_id: action}`，说明见 `code_policy.API_DOC`。
  - 沙箱规则：不能 import，只开放 `math` 和辅助函数，单步有超时，抛异常或返回非法动作时退回默认动作。
  - 异常步数超过 10% 的程序不合格。

### 历任默认（保留作对照）

- `ValueOnlinePolicy`（第 8–14 轮）：每 5 步决定一次。默认执行最近簇的程序，价值模型（`kb/library/value_model.pkl`）预测某个宏动作的优势超过 τ=0.1 时才换成它。训练标签来自离线复制状态得到的完整对局回报（`search.py rollout`）。
- `OnlinePolicy`（第 5–7 轮）：第三轮战术库 + 最近簇 + `none` 兜底。
- Dummy：每道考题都选代码默认的 Jev 路径，是所有比较的基线。

### Jev

- 菜单考题（`EXAM_EVIDENCE`、Force 钉选）的机制保留，但 Jev 目前不在在线默认里。
- 第 2–14 轮测过的角色都没有显著赢过当时的默认，包括：开局挑程序、对局中途在模型拿不准时挑、当价值模型。
- 唯一稳定的长处是：给它相似历史示例后判断"能不能赢"（AUC 0.874，高于血量比的 0.835，但还不显著）。
- Jev 要进入默认，必须在一个没用过的测试集上，显著赢过当前默认。

## 离线：锻造

1. **微操程序**（`forge.py code_global`，第十五轮的做法）：
   - 写程序的模型由 `FORGE_MODEL` 指定，第十五轮用的是 Grok-4.7，推理强度 medium。
   - 每轮写 2 个程序，最多 4 轮，两次调用之间至少隔 2 分钟（网关有每分钟 token 上限）。
   - 每个程序在 train 60 个场景 × 种子 1–2 上和当前默认逐局比较；自动生成的轨迹评审（输局里谁先死、集火了几个目标、接敌时的到位情况）作为下一轮的反馈。
   - 最好的程序还要在种子 3–5 上确认净胜为正，然后上 val，最后在没用过的测试集上只跑一次。
   - 分簇版本（`forge.py code`）也已实现，但调用量大，暂不使用。
2. **战术程序**（`tactic_dsl.py`、`forge.py cluster` / `outcome`）：是"物理条件 → 考题选项"的规则列表，按场景簇选拔，再用新种子确认后入库。新的走位原语只在 `_open_menu` 下出现，不能改变 Dummy 的行为。
3. **价值模型**（`search.py rollout`、`value.py`）：离线标签允许复制模拟器状态，在线绝不允许。评估新模型时，以在线 val 为准，不以离线交叉验证为准。离线交叉验证好、在线却变差的情况已经出现过三次。

## 评测

- 场景集都已冻结：train / train2 用于训练；val 用于选参数；test2、test3、test4、test5 已经用过，各自用于一次最终判断。下一个需要做最终判断的改动，要生成新的测试集，id 前缀用一个没用过的字母。
- `python results/_regress.py holdout --split <集合> --policies ... --write out.jsonl`，再用 `python results/_regress.py paired --base <基线> --files ...` 看翻盘、丢盘和 p 值。
- 每次改动都要跑：
  - `python results/_regress.py trace --policies dummy default force:ranged=stutter --out new.json --compare old.json --actions-only`：确认 Dummy 的逐步动作没变；
  - `python results/_regress.py gate`：Dummy 在官方图上不许有任何一局从赢变输。
- 23 张官方图只作参考：人工规则就是在这些图上挑出来的（它们在官方图上有 92/115）。
