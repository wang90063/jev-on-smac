import sys, time
from pathlib import Path
ROOT = Path('/Users/wangzhi/Desktop/code/jev')
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'smaclite'))
from macsmac.env import StarCraft2Env
from macsmac.snapshot import snapshot
from jev_smac_policy import JevActionPolicy, DummyActionPolicy

MAPS = ['3s_vs_5z', '3s_vs_4z', '3s5z_vs_3s6z', '6h_vs_8z', 'MMM2', '2m_vs_1z']


def reset_pol(pol):
    pol.asked_counts = {}
    pol.n_override = 0
    pol.overrides = []
    pol.n_calls = 0
    pol.n_asked = 0
    pol.n_fallback = 0
    pol.n_questions = 0
    pol.n_live_prune = 0
    if hasattr(pol.client, 'n_calls'):
        pol.client.n_calls = 0
    if hasattr(pol.client, 'infer_s'):
        pol.client.infer_s = 0.0


def run(pol, map_name):
    env = StarCraft2Env(map_name=map_name, seed=1)
    env.reset()
    ret = 0.0
    steps = 0
    terminated = False
    info = {}
    t0 = time.perf_counter()
    while not terminated:
        snap = snapshot(env)
        actions = pol.act(map_name, steps, snap)
        reward, terminated, info = env.step(actions)
        ret += float(reward)
        steps += 1
        if steps > env.episode_limit + 5:
            break
    env.close()
    return {
        'win': int(bool(info.get('battle_won'))),
        'ret': ret,
        'steps': steps,
        'sec': time.perf_counter() - t0,
        'asked': dict(getattr(pol, 'asked_counts', {})),
        'ov': getattr(pol, 'n_override', 0),
        'calls': getattr(pol, 'n_calls', 0),
        'overrides': list(getattr(pol, 'overrides', [])[:8]),
    }

print('===== DUMMY =====', flush=True)
dpol = DummyActionPolicy()
for m in MAPS:
    reset_pol(dpol)
    row = run(dpol, m)
    print(
        f"RESULT dummy {m} win={row['win']} ret={row['ret']:.2f} "
        f"steps={row['steps']} {row['sec']:.1f}s",
        flush=True,
    )

print('===== JEV =====', flush=True)
jpol = JevActionPolicy()
for m in MAPS:
    reset_pol(jpol)
    row = run(jpol, m)
    print(
        f"RESULT jev {m} win={row['win']} ret={row['ret']:.2f} "
        f"steps={row['steps']} {row['sec']:.1f}s calls={row['calls']} "
        f"asked={row['asked']} ov={row['ov']}",
        flush=True,
    )
    print(' overrides', row['overrides'], flush=True)
print('ALL_DONE', flush=True)
