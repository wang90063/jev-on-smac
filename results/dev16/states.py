"""Log g8's state at steps 10/20/30 on train+train2 seeds 1-4 -> results/dev16/states_g8.json"""
import sys, os, json
sys.path.insert(0, '.'); sys.path.insert(0, 'smaclite'); sys.path.insert(0, 'results')
os.environ.setdefault("JEV_QUIET", "1")
from multiprocessing import Pool
import scenarios as SC, code_policy as CP, _dev16 as D
from macsmac.snapshot import snapshot
TS = (10, 20, 30)


def ehp(u):
    return float(u['hp']) + float(u.get('shield') or 0)


def summary(snap, mA, mE):
    A = [a for a in snap['allies'] if a.get('alive')]
    E = [e for e in snap['enemies'] if e.get('alive')]
    return {'ours': sum(ehp(a) for a in A) / mA, 'theirs': sum(ehp(e) for e in E) / mE,
            'n_ours': len(A), 'n_theirs': len(E),
            'kinds_ours': sorted({a['name'] for a in A}), 'kinds_theirs': sorted({e['name'] for e in E})}


def job(args):
    scen, seed = args
    env = SC.make_env(scen, seed); env.reset()
    pol = CP.CodeActionPolicy(open('results/dev16/g8.py').read())
    out, step, done = {}, 0, False
    while not done:
        snap = snapshot(env)
        if step == 0:
            mA = sum(ehp(a) for a in snap['allies'])
            mE = sum(ehp(e) for e in snap['enemies'])
        if step in TS:
            out[step] = summary(snap, mA, mE)
        _, done, _ = env.step(pol.act('s', step, snap)); step += 1
    env.close()
    return {'id': scen['id'], 'seed': seed, 'states': out, 'steps': step}


if __name__ == '__main__':
    jobs = [(s, k) for sp in ('train', 'train2') for s in SC.load(sp) for k in (1, 2, 3, 4)]
    with Pool(9) as p:
        rows = p.map(job, jobs, chunksize=2)
    json.dump(rows, open('results/dev16/states_g8.json', 'w'))
    print('logged', len(rows))
