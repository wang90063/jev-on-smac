# macsmac

Linux 论文里的研究 SMAC 是这样装的：

```bash
wget http://blzdistsc2-a.akamaihd.net/Linux/SC2.4.10.zip
unzip -P iagreetotheeula SC2.4.10.zip -d ~
export SC2PATH=~/StarCraftII
from smac.env import StarCraft2Env
env = StarCraft2Env(map_name="3m", difficulty="7")
```

那是 Blizzard 给研究用的 **Linux 无头包**，不是战网。Mac 上没有这份二进制，国服战网也缺 `Versions/`。

`macsmac` 模仿的是 **那套 Python 接口**，不是 SC2 引擎：

```python
from macsmac.env import StarCraft2Env  # 对标 from smac.env import StarCraft2Env

env = StarCraft2Env(map_name="3m", difficulty="7")
obs, state = env.reset()
avail = env.get_avail_actions()
reward, terminated, info = env.step(actions)
```

`reset / step / get_obs / get_state / get_avail_actions / get_env_info / get_stats` 和 oxwhirl SMAC 同名。引擎是 SMAClite。

**不要和 SC2.4.6.2 / 4.10 的表对绝对值。**

```bash
python -m macsmac --list
python -m macsmac --maps 3m 5m_vs_6m --episodes 3 --policy closest
python -m macsmac --maps 3m MMM2 6h_vs_8z --policy jev
```
