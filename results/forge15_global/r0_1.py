def act(obs, mem):
    try:
        A = list(obs.allies)
        E = list(obs.enemies)
        if not A or not E:
            return {}
        out = {}
        fighters = [u for u in A if u.role != 'heal' and not u.suicide]
        have_ranged = any(u.role == 'ranged' for u in A)

        def ehp(e):
            return e.hp + e.shield

        def pr(e):
            h = ehp(e) + 1.0
            n = 0
            for u in fighters:
                if u.role != 'melee' and can_attack(u, e):
                    n += 1
            s = n * 5.0
            if e.suicide:
                s += 100.0
            dmg = e.damage * (e.attacks if e.attacks else 1)
            s += 14.0 * dmg / h
            if h < 28:
                s += 25.0
            return s

        focus = None
        pid = mem.get('f')
        bans_r = [e for e in E if e.suicide and any(u.role == 'ranged' and can_attack(u, e) for u in fighters)]
        if bans_r:
            focus = max(bans_r, key=pr)
        elif pid is not None:
            for e in E:
                if e.id == pid and any(can_attack(u, e) for u in fighters if u.role != 'melee'):
                    mx = e.max_hp + e.max_shield + 1.0
                    if ehp(e) <= 40 or ehp(e) < 0.45 * mx:
                        focus = e
                    break
        if focus is None:
            reach = [e for e in E if any(can_attack(u, e) for u in fighters if not (u.role == 'melee' and e.suicide))]
            if reach:
                focus = max(reach, key=pr)
        if focus is not None:
            mem['f'] = focus.id

        for u in A:
            if u.role == 'heal' or u.kind == 'medivac':
                wounded = [a for a in A if a.id != u.id and a.hp < a.max_hp - 1 and dist(u, a) <= u.range + 1e-6]
                if wounded:
                    t = min(wounded, key=lambda a: a.hp / (a.max_hp + 1e-6))
                    out[u.id] = heal(u, t)
                else:
                    ne = min(E, key=lambda e: dist(u, e))
                    pool = [a for a in A if a.id != u.id and a.hp < a.max_hp - 1]
                    if dist(u, ne) < 5.5:
                        out[u.id] = move_away(u, ne.x, ne.y)
                    elif pool:
                        t = min(pool, key=lambda a: a.hp / (a.max_hp + 1e-6))
                        out[u.id] = move_toward(u, t.x, t.y)
                continue
            if u.suicide:
                best, bs = None, -1.0
                for e in E:
                    s = 0.0
                    for o in E:
                        dx, dy = o.x - e.x, o.y - e.y
                        if dx * dx + dy * dy <= 4.8:
                            h = ehp(o)
                            s += h if h < 80 else 80.0
                    if s > bs:
                        bs, best = s, e
                if best is not None:
                    out[u.id] = attack(u, best) if can_attack(u, best) else move_toward(u, best.x, best.y)
                continue
            if have_ranged and u.role == 'melee':
                bans = [e for e in E if e.suicide]
                if bans:
                    se = min(bans, key=lambda e: dist(u, e))
                    if dist(u, se) < 4.2:
                        out[u.id] = move_away(u, se.x, se.y)
                        continue
            if u.role == 'ranged':
                bans = [e for e in E if e.suicide]
                if bans:
                    se = min(bans, key=lambda e: dist(u, e))
                    sd = dist(u, se)
                    if sd < 3.2 and not (u.cooldown <= 0.05 and can_attack(u, se) and sd >= 1.8):
                        out[u.id] = move_away(u, se.x, se.y)
                        continue
                threat, td = None, 1e9
                for e in E:
                    if e.role == 'melee' or e.range < 1.2:
                        d = dist(u, e)
                        if d < td:
                            td, threat = d, e
                if threat is not None and u.cooldown > 0.22 and 0.8 < td < max(1.5, u.range * 0.8):
                    if u.speed + 0.45 >= threat.speed or td > 2.6:
                        out[u.id] = move_away(u, threat.x, threat.y)
                        continue
            if focus is not None and can_attack(u, focus) and not (focus.suicide and u.role == 'melee'):
                out[u.id] = attack(u, focus)
                continue
            opts = [e for e in E if can_attack(u, e) and not (e.suicide and u.role == 'melee')]
            if opts and (u.cooldown <= 0.05 or u.role == 'melee'):
                out[u.id] = attack(u, max(opts, key=pr))
        return out
    except Exception:
        return {}
