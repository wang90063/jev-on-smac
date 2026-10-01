def act(obs, mem):
    try:
        A = list(obs.allies)
        E = list(obs.enemies)
        if not A or not E:
            return {}
        out = {}
        splash = [e for e in E if e.splash or e.suicide]
        have_ranged = any(u.role == 'ranged' for u in A)

        def ehp(e):
            return e.hp + e.shield

        for u in A:
            if u.role == 'heal' or u.kind == 'medivac':
                wounded = [a for a in A if a.id != u.id and a.hp < a.max_hp - 1 and dist(u, a) <= u.range + 1e-6]
                if wounded:
                    t = min(wounded, key=lambda a: (a.hp + a.shield) / (a.max_hp + a.max_shield + 1e-6))
                    out[u.id] = heal(u, t)
                else:
                    ne = min(E, key=lambda e: dist(u, e))
                    if dist(u, ne) < 6:
                        out[u.id] = move_away(u, ne.x, ne.y)
                    else:
                        pool = [a for a in A if a.id != u.id and a.hp < a.max_hp - 1]
                        if pool:
                            t = min(pool, key=lambda a: a.hp / (a.max_hp + 1e-6))
                            out[u.id] = move_toward(u, t.x, t.y)
                continue
            if u.suicide:
                best, bs = None, -1.0
                for e in E:
                    s, n = 0.0, 0
                    for o in E:
                        dx, dy = o.x - e.x, o.y - e.y
                        if dx * dx + dy * dy <= 4.8:
                            h = ehp(o)
                            s += h if h < 80 else 80.0
                            n += 1
                    s += n * 8.0
                    if s > bs:
                        bs, best = s, e
                if best is not None:
                    out[u.id] = attack(u, best) if can_attack(u, best) else move_toward(u, best.x, best.y)
                continue
            if splash:
                se = min(splash, key=lambda e: dist(u, e))
                sd = dist(u, se)
                if se.suicide and sd < 3.8 and not u.suicide and (have_ranged or u.role == 'ranged'):
                    if u.role == 'ranged' and u.cooldown <= 0.05 and can_attack(u, se) and sd >= 1.8:
                        out[u.id] = attack(u, se)
                    else:
                        out[u.id] = move_away(u, se.x, se.y)
                    continue
                if sd < 8.0:
                    mates = [a for a in A if a.id != u.id]
                    if mates:
                        f = min(mates, key=lambda a: dist(u, a))
                        if dist(u, f) < 1.7 and u.cooldown > 0.12 and not (u.role == 'ranged' and can_attack(u, se) and u.cooldown <= 0.05):
                            out[u.id] = move_away(u, f.x, f.y)
                            continue
            if u.role == 'ranged':
                ne = min(E, key=lambda e: dist(u, e))
                d = dist(u, ne)
                melee_close = ne.role == 'melee' or ne.suicide or ne.range < 1.2
                if melee_close and u.cooldown > 0.22 and d < max(1.6, u.range * 0.7):
                    if u.speed + 0.45 >= ne.speed or d > 2.5:
                        out[u.id] = move_away(u, ne.x, ne.y)
                        continue
                if u.cooldown <= 0.05:
                    opts = [e for e in E if can_attack(u, e)]
                    if opts:
                        def key(e):
                            return (0 if e.suicide else 1, ehp(e) / (e.damage + 1.0))
                        out[u.id] = attack(u, min(opts, key=key))
                continue
            if u.role == 'melee' and (u.cooldown <= 0.05 or True):
                opts = [e for e in E if can_attack(u, e) and not e.suicide]
                if opts:
                    out[u.id] = attack(u, min(opts, key=ehp))
        return out
    except Exception:
        return {}
