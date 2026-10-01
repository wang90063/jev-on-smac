def act(obs, mem):
    try:
        A = list(obs.allies)
        E = list(obs.enemies)
        if not A or not E:
            return {}
        out = {}
        claimed = {}
        def shots(u):
            n = u.attacks if u.attacks else 1
            if n < 1:
                n = 1
            return float(u.damage) * n
        def ehp(e):
            return float(e.hp) + float(e.shield)
        for u in A:
            if u.role != 'heal' and u.kind != 'medivac':
                continue
            ne = min(E, key=lambda e: dist(u, e))
            wounded = [a for a in A if a.id != u.id and a.hp < a.max_hp - 1 and dist(u, a) <= u.range + 1e-6]
            if wounded and dist(u, ne) > 2.2:
                t = min(wounded, key=lambda a: (a.hp / (a.max_hp + 1.0), -a.damage))
                out[u.id] = heal(u, t)
            elif dist(u, ne) < 5.5:
                out[u.id] = move_away(u, ne.x, ne.y)
            else:
                hurt = [a for a in A if a.id != u.id and a.hp < a.max_hp - 1 and a.damage > 0]
                if hurt:
                    t = min(hurt, key=lambda a: a.hp / (a.max_hp + 1.0))
                    out[u.id] = move_toward(u, t.x, t.y)
        ready = [u for u in A if u.role == 'ranged' and not u.suicide and u.cooldown <= 0.05 and u.damage > 0]
        ready.sort(key=lambda u: -shots(u))
        nready = len(ready)
        banes = [e for e in E if e.suicide]
        banes.sort(key=lambda e: min(dist(a, e) for a in A))
        for e in banes:
            near = min(dist(a, e) for a in A)
            if near > 5.5:
                continue
            need = ehp(e) - claimed.get(e.id, 0.0)
            if need <= 0:
                continue
            for u in ready:
                if u.id in out or need <= 0 or u.splash:
                    continue
                if not can_attack(u, e):
                    continue
                if dist(u, e) > 4.2 and near > 3.5:
                    continue
                out[u.id] = attack(u, e)
                claimed[e.id] = claimed.get(e.id, 0.0) + shots(u)
                need -= shots(u)
        for u in ready:
            if u.id in out:
                continue
            best = None
            bestk = None
            for e in E:
                if not can_attack(u, e):
                    continue
                left = ehp(e) - claimed.get(e.id, 0.0)
                if left <= 0.0 or left > shots(u) + 0.1:
                    continue
                if e.suicide:
                    pri = 0
                elif e.role == 'heal' or e.kind == 'medivac':
                    pri = 1
                elif e.splash or e.damage >= 10:
                    pri = 2
                else:
                    pri = 3
                if pri >= 3 and nready > 8:
                    continue
                k = (pri, left)
                if bestk is None or k < bestk:
                    bestk = k
                    best = e
            if best is not None:
                out[u.id] = attack(u, best)
                claimed[best.id] = claimed.get(best.id, 0.0) + shots(u)
        fronts = [a for a in A if a.role == 'melee' and not a.suicide]
        for u in A:
            if u.id in out or u.role != 'ranged' or u.suicide:
                continue
            threat = None
            td = 1e9
            for e in E:
                if e.role != 'melee' and not e.suicide:
                    continue
                d = dist(u, e)
                if d < td:
                    td = d
                    threat = e
            if threat is None or u.speed <= threat.speed + 0.3:
                continue
            if any(dist(m, threat) < td - 0.5 for m in fronts):
                continue
            if u.cooldown > 0.18 and td < u.range - 0.2 and td > 1.1:
                out[u.id] = move_away(u, threat.x, threat.y)
        return out
    except Exception:
        return {}
