import sys, time
from pathlib import Path
ROOT = Path('/Users/wangzhi/Desktop/code/jev')
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / 'smaclite'))
from macsmac.env import StarCraft2Env
from macsmac.snapshot import snapshot
from jev_smac_policy import DummyActionPolicy, ForceActionPolicy, JevActionPolicy

SANITY = ['3m', '5m_vs_6m', '3s5z', '8m_vs_9m', '3s_vs_3z']
KITE = ['3s_vs_5z', '3s_vs_4z', '3s5z_vs_3s6z', '2m_vs_1z', '6h_vs_8z']
HARD = ['corridor', 'MMM2']


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
        'jobs': {k: v for k, v in getattr(pol, 'tactic_counts', {}).items() if k.startswith('ranged:')},
    }


def banner(title):
    print(f'\n===== {title} =====', flush=True)


def show(tag, m, row):
    print(
        f"RESULT {tag} {m} win={row['win']} ret={row['ret']:.2f} "
        f"steps={row['steps']} {row['sec']:.1f}s calls={row['calls']} "
        f"asked={row['asked']} ov={row['ov']} jobs={row['jobs']}",
        flush=True,
    )
    if row['overrides']:
        print(' overrides', row['overrides'], flush=True)


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'dummy'
    if mode == 'dummy':
        banner('DUMMY attack-move')
        pol = DummyActionPolicy()
        for m in SANITY + KITE + HARD:
            reset_pol(pol)
            pol.tactic_counts = {}
            show('dummy', m, run(pol, m))
    elif mode == 'force':
        banner('FORCE stutter')
        pol = ForceActionPolicy({'ranged': 'stutter'})
        for m in KITE:
            reset_pol(pol)
            pol.tactic_counts = {}
            show('force', m, run(pol, m))
    elif mode == 'jev':
        banner('JEV')
        pol = JevActionPolicy()
        maps = sys.argv[2:] or KITE
        for m in maps:
            reset_pol(pol)
            pol.tactic_counts = {}
            show('jev', m, run(pol, m))
    else:
        raise SystemExit(f'unknown mode {mode}')
    print('ALL_DONE', flush=True)
