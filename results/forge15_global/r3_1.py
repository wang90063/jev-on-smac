def act(obs, mem):
    try:
        A = list(obs.allies)
        E = list(obs.enemies)
        if not A or not E:
            return {}
        out = {}

        def shot(u):
            n = u.attacks if u.attacks and u.attacks > 0 else 1
            return float(u.damage) * n

        def ehp(e):
            return float(e.hp) + float(e.shield)

        for u in A:
            if u.role != 'heal' and u.kind != 'medivac':
                continue
            ne = min(E, key=lambda e: dist(u, e))
            if dist(u, ne) < 4.2:
                out[u.id] = move_away(u, ne.x, ne.y)
                continue
            wounded = [a for a in A if a.id != u.id and not a.suicide and a.hp < a.max_hp - 1]
            near = [a for a in wounded if dist(u, a) <= u.range + 1e-6]
            pool = near if near else wounded
            if not pool:
                continue
            t = max(pool, key=lambda a: (a.damage * (a.attacks if a.attacks else 1)) * (a.max_hp - a.hp))
            if near:
                out[u.id] = heal(u, t)
            else:
                out[u.id] = move_toward(u, t.x, t.y)

        for u in A:
            if not u.suicide:
                continue
            inr = [e for e in E if can_attack(u, e)]
            if len(inr) < 2:
                continue
            def fat(e):
                return sum(1 for o in E if dist(e, o) <= 2.2)
            near = min(inr, key=lambda e: dist(u, e))
            best = max(inr, key=fat)
            if fat(best) >= fat(near) + 2:
                out[u.id] = attack(u, best)

        ready = [u for u in A if u.id not in out and u.role == 'ranged' and not u.suicide and u.cooldown <= 0.06]
        ready.sort(key=lambda u: -shot(u))
        claimed = {}
        for u in ready:
            su = shot(u)
            best = None
            bestk = None
            for e in E:
                if not can_attack(u, e):
                    continue
                left = ehp(e) - claimed.get(e.id, 0.0)
                if left <= 0.4:
                    continue
                close = min(dist(e, a) for a in A)
                bomb = 0 if (e.suicide and close < 3.6) else 1
                healer = 0 if (e.role == 'heal' or e.kind == 'medivac') else 1
                if healer == 0 and left > su * 6:
                    healer = 1
                k = (bomb, healer, left)
                if bestk is None or k < bestk:
                    bestk = k
                    best = e
            if best is None:
                continue
            left = ehp(best) - claimed.get(best.id, 0.0)
            close = min(dist(best, a) for a in A)
            close_bomb = best.suicide and close < 3.6
            mates = 0
            for v in ready:
                if can_attack(v, best):
                    mates += 1
                    if mates >= 2:
                        break
            if close_bomb or left <= su + 0.5 or mates >= 2:
                out[u.id] = attack(u, best)
                claimed[best.id] = claimed.get(best.id, 0.0) + su
        return out
    except Exception:
        return {}
