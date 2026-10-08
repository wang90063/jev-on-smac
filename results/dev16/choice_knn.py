"""Wait (g8) vs push (v_aggr) at the start: leave-one-scenario-out kNN vote on composition features."""
import sys, json, collections, math
sys.path.insert(0, '.'); sys.path.insert(0, 'src'); sys.path.insert(0, 'results')
import _dev16 as D, scenarios as SC

KINDS = ['MARINE', 'MARAUDER', 'STALKER', 'ZEALOT', 'COLOSSUS', 'ZERGLING', 'BANELING', 'HYDRALISK', 'MEDIVAC']
LAYOUTS = ['open', 'wall_gap', 'ravine', 'octagon', 'corridor']


def vec(s):
    def side(army):
        tot = sum(SC.COST[k] * n for k, n in army.items())
        return [SC.COST[k] * army.get(k, 0) / tot for k in KINDS]
    va = sum(SC.COST[k] * n for k, n in s['ally'].items())
    ve = sum(SC.COST[k] * n for k, n in s['enemy'].items())
    return side(s['ally']) + side(s['enemy']) + [0.5 * (s['layout'] == l) for l in LAYOUTS] + [math.log(va / ve)]


def load(names=('g8', 'v_aggr'), seeds=(1, 2, 3, 4)):
    H = {n: D._h(D._src(f'results/dev16/{n}.py')) for n in names}
    W = collections.defaultdict(dict)
    for l in open('results/dev16/cache2.jsonl'):
        r = json.loads(l)
        for n, h in H.items():
            if r['h'] == h and r['seed'] in seeds:
                W[n][(r['id'], r['seed'])] = r['win']
    sc = {s['id']: s for sp in ('train', 'train2') for s in SC.load(sp)}
    return sc, W


if __name__ == '__main__':
    sc, W = load()
    ids = sorted(sc)
    V = {i: vec(sc[i]) for i in ids}
    gain = {i: sum(W['v_aggr'][(i, k)] - W['g8'][(i, k)] for k in (1, 2, 3, 4)) for i in ids}
    base = sum(W['g8'][(i, k)] for i in ids for k in (1, 2, 3, 4))
    print('always wait', base, '| always push', sum(W['v_aggr'][(i, k)] for i in ids for k in (1, 2, 3, 4)),
          '| scenario oracle', base + sum(max(g, 0) for g in gain.values()))
    for K in (3, 5, 8, 12, 20):
        for thr in (0, 1, 2):
            tot = 0
            pushed = 0
            for i in ids:
                nb = sorted((j for j in ids if j != i), key=lambda j: sum((a - b) ** 2 for a, b in zip(V[i], V[j])))[:K]
                vote = sum(gain[j] for j in nb)
                if vote > thr:
                    pushed += 1
                    tot += gain[i]
            print(f"kNN K={K:2d} thr={thr}: push on {pushed:3d}/180, net {tot:+d}")
