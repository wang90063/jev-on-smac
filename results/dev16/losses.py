"""List fights a program loses: python results/dev16/losses.py <prog> [base] -- shows leftover kinds."""
import sys, json, hashlib, collections
sys.path.insert(0, '.'); sys.path.insert(0, 'results')
import scenarios as SC, _dev16 as D
h = lambda p: D._h(D._src(p))
rows = [json.loads(l) for l in open('results/dev16/cache2.jsonl')]
P = {(r['id'], r['seed']): r for r in rows if r['h'] == h(sys.argv[1])}
B = {(r['id'], r['seed']): r for r in rows if r['h'] == h(sys.argv[2])} if len(sys.argv) > 2 else {}
sc = {s['id']: s for sp in ('train', 'train2') for s in SC.load(sp)}
kinds = collections.Counter()
for k, r in sorted(P.items()):
    if r['win']:
        continue
    s = sc[k[0]]
    tag = 'timeout' if r['a_left'] else 'wiped'
    kinds[(tag, tuple(sorted(r['e_left'])))] += 1
    b = B.get(k, {}).get('win', '')
    print(k, D.category(s), s['layout'], s['ally'], 'vs', s['enemy'], '|', tag, 'ours', r['a_left'], 'theirs', r['e_left'], '| base', b)
print()
for k, n in kinds.most_common(15):
    print(n, k)
