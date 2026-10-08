import time, json, sys
from pathlib import Path
sys.path.insert(0, "/Users/wangzhi/Desktop/code/jev")
sys.path.insert(0, "/Users/wangzhi/Desktop/code/jev/src")
sys.path.insert(0, "/Users/wangzhi/Desktop/code/jev/src")
from macsmac.env import StarCraft2Env
from macsmac.snapshot import snapshot
from macsmac.bench import _closest_policy, _script_policy
from jev_smac_policy import _matchup, _unit_matchup, _speed_advantage, living

OFFICIAL = [
    "2s3z","3s_vs_5z","2s_vs_1sc","3s5z","2c_vs_64zg",
    "corridor","bane_vs_bane","MMM","MMM2",
    "10m_vs_11m","3s5z_vs_3s6z","27m_vs_30m",
]

def run(map_name, policy, polname):
    env = StarCraft2Env(map_name=map_name)
    env.reset()
    snap0 = snapshot(env)
    allies=living(snap0['allies']); enemies=living(snap0['enemies'])
    mu=_matchup(snap0)
    um={a['id']:_unit_matchup(a,snap0) for a in allies}
    kinds={}
    for a in allies:
        k=a.get('name') or a['type']
        kinds[k]=kinds.get(k,0)+1
    ekinds={}
    for e in enemies:
        k=e.get('name') or e['type']
        ekinds[k]=ekinds.get(k,0)+1
    terminated=False; steps=0; ret=0; info={}
    t0=time.perf_counter()
    while not terminated:
        snap=snapshot(env)
        actions=policy(map_name, steps, snap)
        reward, terminated, info = env.step(actions)
        ret += float(reward); steps += 1
        if steps > env.episode_limit + 5:
            break
    dt=time.perf_counter()-t0
    env.close()
    return {
        'map': map_name, 'pol': polname, 'win': int(bool(info.get('battle_won'))),
        'ret': round(ret,2), 'steps': steps,
        'deadA': info.get('dead_allies'), 'deadE': info.get('dead_enemies'),
        'limit': env.episode_limit, 'sec': round(dt,2),
        'matchup': mu, 'unit_mu': um,
        'A': kinds, 'E': ekinds, 'spd': round(_speed_advantage(snap0),2),
        'ap': snap0.get('attack_point'),
        'nA': len(allies), 'nE': len(enemies),
    }

rows=[]
for m in OFFICIAL:
    for pol, name in [(_closest_policy,'closest'), (_script_policy,'script')]:
        try:
            row=run(m, pol, name)
        except Exception as e:
            row={'map':m,'pol':name,'err':repr(e)}
        rows.append(row)
        if 'err' in row:
            print(f"{m:16s} {name:8s} ERR {row['err']}", flush=True)
        else:
            print(f"{m:16s} {name:8s} win={row['win']} ret={row['ret']:6.2f} steps={row['steps']:3d}/{row['limit']} deadA={row['deadA']} deadE={row['deadE']} mu={row['matchup']} spd={row['spd']} {row['sec']}s A={row['A']} E={row['E']}", flush=True)

Path("/Users/wangzhi/Desktop/code/jev/results/official_baseline.json").write_text(json.dumps(rows, indent=2))
print('wrote results/official_baseline.json')
