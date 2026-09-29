"""Official SMAC map registry, plus episode limits used by PyMARL/SMAC."""

from __future__ import annotations

from typing import Dict

# Copied from oxwhirl/smac smac_maps.py. Numbers are the research protocol,
# not a claim that this engine is StarCraft II 4.6.2.
MAP_PARAMS: Dict[str, dict] = {
    "3m": {"n_agents": 3, "n_enemies": 3, "limit": 60, "difficulty": "Easy"},
    "8m": {"n_agents": 8, "n_enemies": 8, "limit": 120, "difficulty": "Easy"},
    "25m": {"n_agents": 25, "n_enemies": 25, "limit": 150, "difficulty": "Easy"},
    "5m_vs_6m": {"n_agents": 5, "n_enemies": 6, "limit": 70, "difficulty": "Hard"},
    "8m_vs_9m": {"n_agents": 8, "n_enemies": 9, "limit": 120, "difficulty": "Hard"},
    "10m_vs_11m": {"n_agents": 10, "n_enemies": 11, "limit": 150, "difficulty": "Hard"},
    "27m_vs_30m": {"n_agents": 27, "n_enemies": 30, "limit": 180, "difficulty": "Super Hard"},
    "MMM": {"n_agents": 10, "n_enemies": 10, "limit": 150, "difficulty": "Hard"},
    "MMM2": {"n_agents": 10, "n_enemies": 12, "limit": 180, "difficulty": "Super Hard"},
    "2s3z": {"n_agents": 5, "n_enemies": 5, "limit": 120, "difficulty": "Easy"},
    "3s5z": {"n_agents": 8, "n_enemies": 8, "limit": 150, "difficulty": "Hard"},
    "3s5z_vs_3s6z": {"n_agents": 8, "n_enemies": 9, "limit": 170, "difficulty": "Super Hard"},
    "3s_vs_3z": {"n_agents": 3, "n_enemies": 3, "limit": 150, "difficulty": "Easy"},
    "3s_vs_4z": {"n_agents": 3, "n_enemies": 4, "limit": 200, "difficulty": "Hard"},
    "3s_vs_5z": {"n_agents": 3, "n_enemies": 5, "limit": 250, "difficulty": "Hard"},
    "1c3s5z": {"n_agents": 9, "n_enemies": 9, "limit": 180, "difficulty": "Hard"},
    "2m_vs_1z": {"n_agents": 2, "n_enemies": 1, "limit": 150, "difficulty": "Easy"},
    "corridor": {"n_agents": 6, "n_enemies": 24, "limit": 400, "difficulty": "Super Hard"},
    "6h_vs_8z": {"n_agents": 6, "n_enemies": 8, "limit": 150, "difficulty": "Super Hard"},
    "2s_vs_1sc": {"n_agents": 2, "n_enemies": 1, "limit": 300, "difficulty": "Easy"},
    "so_many_baneling": {"n_agents": 7, "n_enemies": 32, "limit": 100, "difficulty": "Hard"},
    "bane_vs_bane": {"n_agents": 24, "n_enemies": 24, "limit": 200, "difficulty": "Hard"},
    "2c_vs_64zg": {"n_agents": 2, "n_enemies": 64, "limit": 400, "difficulty": "Super Hard"},
}


def list_maps():
    return list(MAP_PARAMS.keys())


def get_map_params(map_name: str) -> dict:
    if map_name not in MAP_PARAMS:
        raise KeyError(map_name)
    return MAP_PARAMS[map_name]
