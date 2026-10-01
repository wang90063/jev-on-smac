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
            return u.damage * n

        for u in A:
            if u.role != 'heal' and u.kind != 'medivac':
                continue
            ne = min(E, key=lambda e: dist(u, e))
            wounded = [a for a in A if a.hp < a.max_hp - 1 and dist(u, a) <= u.range + 1e-6]
            if wounded and dist(u, ne) > 2.2:
                t = min(wounded, key=lambda a: a.hp / (a.max_hp + 1e-6))
                out[u.id] = heal(u, t)
            elif dist(u, ne) < 5.0:
                out[u.id] = move_away(u, ne.x, ne.y)
            else:
                hurt = [a for a in A if a.id != u.id and a.hp < a.max_hp - 1]
                if hurt:
                    t = min(hurt, key=lambda a: a.hp / (a.max_hp + 1e-6))
                    out[u.id] = move_toward(u, t.x, t.y)
        ready = [u for u in A if u.role == 'ranged' and not u.suicide and u.cooldown <= 0.05]
        ready.sort(key=lambda u: -u.damage)
        for u in ready:
            best = None
            bestk = None
            for e in E:
                if not can_attack(u, e):
                    continue
                left = e.hp + e.shield - claimed.get(e.id, 0.0)
                if left <= 0 or left > shots(u) + 0.1:
                    continue
                pri = 0 if e.suicide else (1 if e.role == 'heal' or e.kind == 'medivac' else 2)
                k = (pri, left)
                if bestk is None or k < bestk:
                    bestk = k
                    best = e
            if best is not None:
                out[u.id] = attack(u, best)
                claimed[best.id] = claimed.get(best.id, 0.0) + shots(u)
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
            if u.cooldown > 0.18 and td < u.range - 0.25 and td > 1.0:
                out[u.id] = move_away(u, threat.x, threat.y)
        return out
    except Exception:
        return {}
