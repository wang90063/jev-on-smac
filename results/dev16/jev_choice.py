"""Can Jev pick 'wait' vs 'push' at the start of a fight better than kNN?

Labels are cached simulator outcomes (results/dev16/cache2.jsonl): every train/train2
scenario was played on seeds 1-4 with g8 (wait: hold, let them come into focused fire)
and v_aggr (push: walk at them). Leave-one-scenario-out: Jev sees the fight plus the
K most similar OTHER fights with their real wait/push results, and picks one.

    python results/dev16/jev_choice.py ask     # TypeSafe API, 180 calls
    python results/dev16/jev_choice.py score
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, '.'); sys.path.insert(0, 'results'); sys.path.insert(0, 'results/dev16')
import choice_knn as CK  # noqa: E402

OUT = Path('results/dev16/jev_choice.json')
K = 8
UNIT_DIR = Path('smaclite/smaclite/env/units/smaclite_units')
AIR = {'MARINE', 'HYDRALISK', 'STALKER'}


def unit_card(kind):
    d = json.loads((UNIT_DIR / f'{kind.lower()}.json').read_text())
    rng = d['attack_range']
    card = {'hp': d['hp'], 'shield': d.get('shield', 0), 'armor': d['armor'], 'damage': d['damage'] * d.get('attacks', 1),
            'cooldown_s': d['cooldown'], 'range': 'melee' if rng == 'MELEE' else rng, 'speed': d['speed'],
            'hits_air': kind in AIR, 'is_air': kind == 'MEDIVAC'}
    if d.get('bonuses'):
        card['bonus_vs'] = d['bonuses']
    if d.get('targeter') == 'KAMIKAZE':
        card['note'] = 'suicide: explodes for area damage (radius 2.2) and dies'
    if d.get('targeter') == 'LASER_BEAM':
        card['note'] = 'splash: its beam hits every unit along a short line'
    if kind == 'MEDIVAC':
        card['note'] = 'heals; only marines, hydralisks and stalkers can shoot it'
    return card


def fight(s):
    return {'ours': {k.lower(): n for k, n in s['ally'].items()}, 'theirs': {k.lower(): n for k, n in s['enemy'].items()},
            'terrain': s['layout']}


QUESTIONS = {'plan': {
    'type': 'choice',
    'instructions': ('Our army starts about 14 cells from the enemy, who always attack-move toward our start. '
                     'Which opening wins this fight more often? Use the similar fights: their wait/push results '
                     'are real outcomes over 4 spawns each; weigh the ones that match this fight most.'),
    'criteria': {
        'wait': {'does': 'Hold near our start in a tight group; they walk into our focused fire, then we fight.'},
        'push': {'does': 'Walk straight at the enemy and engage them where they are.'},
    }}}


def cmd_ask():
    from jev_api import JevClient

    sc, W = CK.load()
    ids = sorted(sc)
    V = {i: CK.vec(sc[i]) for i in ids}
    kinds = sorted({k for s in sc.values() for k in list(s['ally']) + list(s['enemy'])})
    cards = {k.lower(): unit_card(k) for k in kinds}
    client = JevClient(timeout=60)

    def one(i):
        nb = sorted((j for j in ids if j != i), key=lambda j: sum((a - b) ** 2 for a, b in zip(V[i], V[j])))[:K]
        mine = fight(sc[i])
        state = {
            'this_fight': mine,
            'unit_stats': {k: cards[k] for k in set(mine['ours']) | set(mine['theirs'])},
            'similar_fights': [dict(fight(sc[j]),
                                    wait_wins=sum(W['g8'][(j, k)] for k in (1, 2, 3, 4)),
                                    push_wins=sum(W['v_aggr'][(j, k)] for k in (1, 2, 3, 4)),
                                    out_of=4) for j in nb],
        }
        r = client.system_one(state, QUESTIONS)
        ans = ((r or {}).get('answers') or {}).get('plan') or {}
        probs = ans.get('probabilities') or {}
        return {'id': i, 'choice': ans.get('choice'), 'p_push': probs.get('push'), 'nb': nb}

    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(one, ids))
    OUT.write_text(json.dumps(res, indent=0))
    print(f'asked {len(ids)}; calls ok {client.n_calls} fail {client.n_fail}; missing {sum(r["choice"] is None for r in res)}')


def cmd_score():
    sc, W = CK.load()
    res = json.loads(OUT.read_text())
    gain = {i: sum(W['v_aggr'][(i, k)] - W['g8'][(i, k)] for k in (1, 2, 3, 4)) for i in sc}
    print(f"scenario oracle net {sum(max(g, 0) for g in gain.values()):+d}; always push {sum(gain.values()):+d}")
    for thr in (0.5, 0.6, 0.7, 0.8):
        picked = [r['id'] for r in res if r['p_push'] is not None and r['p_push'] > thr]
        print(f"Jev push if P(push) > {thr}: push on {len(picked):3d}/{len(res)}, net {sum(gain[i] for i in picked):+d}")
    ch = [r['id'] for r in res if r['choice'] == 'push']
    print(f"Jev argmax choice: push on {len(ch)}, net {sum(gain[i] for i in ch):+d}")
    # the same neighbours, plain vote, for reference
    vote = [r['id'] for r in res if sum(gain[j] for j in r['nb']) > 0]
    print(f"kNN vote on the same {K} neighbours: push on {len(vote)}, net {sum(gain[i] for i in vote):+d}")


if __name__ == '__main__':
    {'ask': cmd_ask, 'score': cmd_score}[sys.argv[1]]()
