"""Mid-fight 'switch to push' headroom over g8, with a luck control. No Jev calls."""
import sys, json, collections
sys.path.insert(0, '.'); sys.path.insert(0, 'results')
import _dev16 as D

names = ['g8', 'sw10', 'sw20', 'sw30', 'luck20']
H = {n: D._h(D._src(f'results/dev16/{n}.py')) for n in names}
W = collections.defaultdict(dict)
for l in open('results/dev16/cache2.jsonl'):
    r = json.loads(l)
    for n, h in H.items():
        if r['h'] == h and r['seed'] in (1, 2, 3, 4):
            W[n][(r['id'], r['seed'])] = r['win']
keys = sorted(set.intersection(*[set(W[n]) for n in names]))
print('episodes', len(keys))
for n in names:
    print(f'  {n:7s} {sum(W[n][k] for k in keys)}')
g = W['g8']
for n in names[1:]:
    up = sum(1 for k in keys if W[n][k] and not g[k])
    down = sum(1 for k in keys if g[k] and not W[n][k])
    print(f'  {n:7s} vs g8: +{up} / -{down}; per-episode best-of-two {sum(max(g[k], W[n][k]) for k in keys)}')
S = {(r['id'], r['seed']): r for r in json.load(open('results/dev16/states_g8.json'))}
print('gate: switch at T when losing by margin m (theirs - ours health fraction > m)')
for T, n in ((10, 'sw10'), (20, 'sw20'), (30, 'sw30')):
    for m in (-0.1, 0.0, 0.1, 0.2, 0.3):
        sel = [k for k in keys if str(T) in S[k]['states'] and S[k]['states'][str(T)]['theirs'] - S[k]['states'][str(T)]['ours'] > m]
        net = sum(W[n][k] - g[k] for k in sel)
        print(f'  T={T} m={m:+.1f}: switch in {len(sel):3d} episodes, net {net:+d}')
