"""Print a compact step-by-step story of one fight: python results/dev16/trace.py <prog|empty> <split> <id> <seed> [every]"""
import sys, os
sys.path.insert(0, '.'); sys.path.insert(0, 'smaclite'); sys.path.insert(0, 'results')
os.environ.setdefault("JEV_QUIET", "1")
import scenarios as SC, code_policy as CP, _dev16 as D
from macsmac.snapshot import snapshot
prog, split, sid, seed = sys.argv[1:5]
every = int(sys.argv[5]) if len(sys.argv) > 5 else 1
scen = [s for s in SC.load(split) if s['id'] == sid][0]
print(scen['layout'], scen['ally'], 'vs', scen['enemy'], 'limit', scen['limit'])
env = SC.make_env(scen, int(seed)); env.reset()
pol = CP.CodeActionPolicy(D._src(prog))
step, done, info = 0, False, {}
def short(a):
    return {0: '.', 1: 's', 2: 'N', 3: 'S', 4: 'E', 5: 'W'}.get(a, f'@{a-6}')
while not done:
    snap = snapshot(env)
    base = list(pol.base.act('t', step, snap)) if False else None
    acts = pol.act('t', step, snap)
    if step % every == 0:
        al = ' '.join(f"{a['id']}{a['name'][:2]}({a['x']:.0f},{a['y']:.0f}){int(a['hp']+(a.get('shield') or 0))}{short(acts[a['id']])}" for a in snap['allies'] if a.get('alive'))
        en = ' '.join(f"{e['id']}{e['name'][:2]}({e['x']:.0f},{e['y']:.0f}){int(e['hp']+(e.get('shield') or 0))}" for e in snap['enemies'] if e.get('alive'))
        print(f"{step:3d} A: {al}\n    E: {en}")
    _, done, info = env.step(acts); step += 1
print('won' if info.get('battle_won') else 'lost', 'steps', step)
