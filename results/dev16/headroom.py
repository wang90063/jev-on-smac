"""Selection headroom over the default program, no Jev calls.

For each scenario, pick the variant with the most wins on seeds A (ties -> default),
then score that pick on seeds B. Swap A and B. Compare with the default on the same episodes.
    python results/dev16/headroom.py g8 g7 g10 v_aggr v_nokite v_nofocus
"""
import sys, json, collections
sys.path.insert(0, '.'); sys.path.insert(0, 'src'); sys.path.insert(0, 'results')
import _dev16 as D

names = sys.argv[1:]
H = {n: D._h(D._src(f'results/dev16/{n}.py')) for n in names}
rows = [json.loads(l) for l in open('results/dev16/cache2.jsonl')]
W = collections.defaultdict(dict)  # name -> (id, seed) -> win
for r in rows:
    for n, h in H.items():
        if r['h'] == h:
            W[n][(r['id'], r['seed'])] = r['win']
ids = sorted(set.intersection(*[{k[0] for k in W[n] if k[1] in (1, 2, 3, 4)} for n in names]))
base = names[0]
for n in names:
    print(f"{n:10s} {sum(W[n][(i, s)] for i in ids for s in (1, 2, 3, 4))}/{len(ids) * 4}")
tot_pick = tot_base = 0
switched = collections.Counter()
for A, B in (((1, 2), (3, 4)), ((3, 4), (1, 2))):
    for i in ids:
        score = {n: sum(W[n][(i, s)] for s in A) for n in names}
        best = max(names, key=lambda n: (score[n], n == base))
        if score[best] == score[base]:
            best = base
        switched[best] += 1
        tot_pick += sum(W[best][(i, s)] for s in B)
        tot_base += sum(W[base][(i, s)] for s in B)
print(f"pick-by-other-seeds: {tot_pick} vs default {tot_base} (net {tot_pick - tot_base:+d}) of {len(ids) * 4}; picks {dict(switched)}")
orc = sum(max(W[n][(i, s)] for n in names) for i in ids for s in (1, 2, 3, 4))
print(f"per-episode oracle (loose upper bound, includes luck): {orc}")
