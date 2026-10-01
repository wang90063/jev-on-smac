def act(obs, mem):
    try:
        A = list(obs.allies)
        E = list(obs.enemies)
        if not A or not E:
            return {}
        out = {}
        nE = len(E)

        def eh(e):
            return e.hp + e.shield

        for u in A:
            if u.role == 'heal' or u.kind == 'medivac':
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
                continue
            if not u.suicide or nE < 4:
                continue
            scored = []
            for e in E:
                s = 0.0
                c = 0
                ex, ey = e.x, e.y
                for o in E:
                    dx = o.x - ex
                    dy = o.y - ey
                    if dx * dx + dy * dy <= 4.84:
                        h = eh(o)
                        s += 80.0 if h > 80.0 else h
                        c += 1
                scored.append((e, s, c))
            inr = [t for t in scored if can_attack(u, t[0])]
            if inr:
                pick = max(inr, key=lambda t: (t[1], -dist(u, t[0])))
                if pick[2] >= 2 or pick[1] >= 50.0:
                    out[u.id] = attack(u, pick[0])
                continue
            near = min(E, key=lambda e: dist(u, e))
            near_s = 0.0
            for e, s, c in scored:
                if e.id == near.id:
                    near_s = s
            best = max(scored, key=lambda t: t[1] - dist(u, t[0]) * 5.0)
            if best[1] >= near_s + 35.0 and best[1] >= 70.0:
                out[u.id] = move_toward(u, best[0].x, best[0].y)
        return out
    except Exception:
        return {}
