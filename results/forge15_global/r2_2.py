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
        def blast(e):
            s = 0.0
            n = 0
            for o in E:
                if dist(o, e) <= 2.0:
                    s += ehp(o) + 20.0
                    n += 1
            return s + n * 5.0, n
        for u in A:
            if u.role != 'heal' and u.kind != 'medivac':
                continue
            ne = min(E, key=lambda e: dist(u, e))
            wounded = [a for a in A if a.id != u.id and a.hp < a.max_hp - 1 and dist(u, a) <= u.range + 1e-6]
            if wounded and dist(u, ne) > 2.0:
                t = min(wounded, key=lambda a: (a.hp / (a.max_hp + 1.0) - 0.02 * a.damage, -a.damage))
                out[u.id] = heal(u, t)
            elif dist(u, ne) < 6.5:
                out[u.id] = move_away(u, ne.x, ne.y)
            else:
                hurt = [a for a in A if a.id != u.id and a.hp < a.max_hp - 1 and a.role != 'heal']
                if hurt:
                    t = max(hurt, key=lambda a: a.damage * (1.0 - a.hp / (a.max_hp + 1.0)))
                    out[u.id] = move_toward(u, t.x, t.y)
        for u in A:
            if not u.suicide:
                continue
            touch = min(E, key=lambda e: dist(u, e))
            best = max(E, key=lambda e: blast(e)[0])
            here, hn = blast(touch)
            there, tn = blast(best)
            if best.id == touch.id:
                continue
            if can_attack(u, best) and there > here * 1.6 and tn >= 3:
                out[u.id] = attack(u, best)
            elif hn <= 1 and tn >= 3 and there > here * 2.2 and there >= 100.0 and dist(u, best) <= dist(u, touch) + 3.5:
                out[u.id] = move_toward(u, best.x, best.y)
        healers = [e for e in E if (e.role == 'heal' or e.kind == 'medivac') and ehp(e) <= 90.0]
        healers.sort(key=lambda e: ehp(e))
        ready = [u for u in A if u.role == 'ranged' and not u.suicide and u.cooldown <= 0.05 and u.damage > 0]
        ready.sort(key=lambda u: -shots(u))
        for e in healers:
            need = ehp(e) - claimed.get(e.id, 0.0)
            if need <= 0:
                continue
            used = 0
            for u in ready:
                if u.id in out or used >= 4 or need <= 0:
                    continue
                if not can_attack(u, e):
                    continue
                out[u.id] = attack(u, e)
                claimed[e.id] = claimed.get(e.id, 0.0) + shots(u)
                need -= shots(u)
                used += 1
        for u in A:
            if u.id in out or u.role != 'ranged' or u.suicide or u.speed < 4.0:
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
            if threat is None or u.speed <= threat.speed + 0.25:
                continue
            if u.cooldown > 0.2 and 1.0 < td < u.range - 0.3:
                out[u.id] = move_away(u, threat.x, threat.y)
        return out
    except Exception:
        return {}
