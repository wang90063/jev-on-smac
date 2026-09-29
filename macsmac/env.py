"""Linux-research SMAC API, Mac runtime.

Papers on Linux do:

    wget http://blzdistsc2-a.akamaihd.net/Linux/SC2.4.10.zip
    unzip -P iagreetotheeula
    export SC2PATH=~/StarCraftII
    from smac.env import StarCraft2Env

This class keeps that Python surface (`reset/step/get_obs/...`) so PyMARL-style
code runs on Mac. The game engine is SMAClite, not SC2.4.10. Do not mix tables.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SMACLITE = ROOT / "smaclite"
if str(SMACLITE) not in sys.path:
    sys.path.insert(0, str(SMACLITE))

import smaclite  # noqa: F401
from smaclite.env.smaclite import SMACliteEnv

from .maps import MAP_PARAMS, get_map_params


class StarCraft2Env:
    """Drop-in for `smac.env.starcraft2.StarCraft2Env` on Mac."""

    def __init__(
        self,
        map_name="8m",
        step_mul=8,
        move_amount=2,
        difficulty="7",
        game_version=None,
        seed=None,
        continuing_episode=False,
        obs_all_health=True,
        obs_own_health=True,
        obs_last_action=False,
        obs_pathing_grid=False,
        obs_terrain_height=False,
        obs_instead_of_state=False,
        obs_timestep_number=False,
        state_last_action=True,
        state_timestep_number=False,
        reward_sparse=False,
        reward_only_positive=True,
        reward_death_value=10,
        reward_win=200,
        reward_defeat=0,
        reward_negative_scale=0.5,
        reward_scale=True,
        reward_scale_rate=20,
        replay_dir="",
        replay_prefix="",
        window_size_x=1920,
        window_size_y=1200,
        heuristic_ai=False,
        heuristic_rest=False,
        debug=False,
        attack_move=True,
        map_file=None,
        limit=None,
        **_ignored,
    ):
        if map_file is not None:
            # Generated scenario: counts come from the JSON, limit from the caller.
            import json

            path = Path(map_file)
            info = json.loads(path.read_text())
            map_params = {
                "n_agents": info["num_allied_units"],
                "n_enemies": info["num_enemy_units"],
                "limit": int(limit or 150),
            }
        else:
            if map_name not in MAP_PARAMS:
                raise ValueError(f"Unknown map {map_name}. Known: {sorted(MAP_PARAMS)}")
            path = SMACLITE / "smaclite" / "env" / "maps" / "smaclite_maps" / f"{map_name}.json"
            if not path.exists():
                raise FileNotFoundError(path)
            map_params = get_map_params(map_name)
        self.map_name = map_name
        self.n_agents = int(map_params["n_agents"])
        self.n_enemies = int(map_params["n_enemies"])
        self.episode_limit = int(map_params["limit"])
        self._move_amount = move_amount
        self._step_mul = step_mul
        self.difficulty = difficulty
        self.game_version = game_version or "smaclite"
        self._seed = seed
        self.continuing_episode = continuing_episode
        self.obs_instead_of_state = obs_instead_of_state
        self.reward_sparse = reward_sparse
        self.reward_scale = reward_scale
        self.reward_scale_rate = reward_scale_rate
        self.n_actions_no_attack = 6

        self.attack_move = bool(attack_move)
        self._gym = SMACliteEnv(
            map_file=str(path),
            seed=seed,
            use_cpp_rvo2=False,
            render_mode="rgb_array",
            attack_move=self.attack_move,
        )
        self.n_actions = int(self._gym.n_actions)
        self._episode_steps = 0
        self._episode_count = 0
        self._total_steps = 0
        self._last_obs = None
        self.last_action = np.zeros((self.n_agents, self.n_actions), dtype=np.float32)
        self.battles_won = 0
        self.battles_game = 0
        self.timeouts = 0
        self.force_restarts = 0
        self.win_counted = False
        self.defeat_counted = False

    @property
    def agents(self):
        return self._gym.agents

    @property
    def enemies(self):
        return self._gym.enemies

    def get_unit_by_id(self, a_id: int):
        return self._gym.agents.get(a_id)

    def reset(self):
        self._last_obs, _info = self._gym.reset()
        self._episode_steps = 0
        self.win_counted = False
        self.defeat_counted = False
        self.last_action = np.zeros((self.n_agents, self.n_actions), dtype=np.float32)
        return self.get_obs(), self.get_state()

    def step(self, actions):
        actions_int = [int(a) for a in actions]
        avail = self._gym.get_avail_actions()
        safe = []
        for i, a in enumerate(actions_int):
            row = avail[i]
            if 0 <= a < len(row) and row[a]:
                safe.append(a)
            else:
                safe.append(1 if len(row) > 1 and row[1] else 0)
        actions_int = safe
        self.last_action = np.eye(self.n_actions, dtype=np.float32)[np.array(actions_int)]
        obs, reward, done, truncated, info = self._gym.step(actions_int)
        self._last_obs = obs
        self._episode_steps += 1
        self._total_steps += 1

        timed_out = self._episode_steps >= self.episode_limit
        terminated = bool(done or truncated or timed_out)
        won = bool(info.get("battle_won")) and bool(done)
        if timed_out and not done:
            won = False

        dead_allies = self.n_agents - sum(
            1 for u in self._gym.agents.values() if getattr(u, "hp", 0) > 0
        )
        dead_enemies = self.n_enemies - sum(
            1 for u in self._gym.enemies.values() if getattr(u, "hp", 0) > 0
        )
        out: Dict[str, Any] = {
            "battle_won": won,
            "dead_allies": int(dead_allies),
            "dead_enemies": int(dead_enemies),
        }
        if timed_out and self.continuing_episode:
            out["episode_limit"] = True

        if terminated:
            self.battles_game += 1
            self._episode_count += 1
            if won and not self.win_counted:
                self.battles_won += 1
                self.win_counted = True
            if timed_out and not done:
                self.timeouts += 1

        if self.reward_sparse:
            if terminated and won:
                reward = 1.0
            elif terminated:
                reward = -1.0
            else:
                reward = 0.0
        return float(reward), terminated, out

    def get_obs(self):
        if self._last_obs is None:
            self._last_obs = self._gym.get_obs()
        return list(self._last_obs)

    def get_obs_agent(self, agent_id: int):
        return self.get_obs()[agent_id]

    def get_obs_size(self) -> int:
        return int(self._gym.obs_size)

    def get_state(self):
        if self.obs_instead_of_state:
            return np.concatenate(self.get_obs(), axis=0).astype(np.float32)
        return self._gym.get_state()

    def get_state_size(self) -> int:
        if self.obs_instead_of_state:
            return self.get_obs_size() * self.n_agents
        return int(self._gym.state_size)

    def get_avail_actions(self) -> List[List[int]]:
        return [list(map(int, row)) for row in self._gym.get_avail_actions()]

    def get_avail_agent_actions(self, agent_id: int) -> List[int]:
        return self.get_avail_actions()[agent_id]

    def get_total_actions(self) -> int:
        return self.n_actions

    def get_env_info(self) -> Dict[str, Any]:
        return {
            "state_shape": self.get_state_size(),
            "obs_shape": self.get_obs_size(),
            "n_actions": self.get_total_actions(),
            "n_agents": self.n_agents,
            "episode_limit": self.episode_limit,
            "map_name": self.map_name,
            "engine": "macsmac/smaclite",
            "game_version": self.game_version,
        }

    def get_stats(self) -> Dict[str, Any]:
        games = max(self.battles_game, 1)
        return {
            "battles_won": self.battles_won,
            "battles_game": self.battles_game,
            "battles_draw": self.timeouts,
            "win_rate": self.battles_won / games,
            "timeouts": self.timeouts,
            "restarts": self.force_restarts,
        }

    def seed(self):
        return self._seed

    def save_replay(self):
        return None

    def close(self):
        self._gym.close()

    def render(self, mode="human"):
        return self._gym.render()
