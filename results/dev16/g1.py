PULL_BACK = 3.0
PULL_FRAC = 0.35
PULL_STEPS = 2


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


        # --- pull back: a hurt unit that is being hit steps behind its friends so the attacker retargets ---
        hist = mem.setdefault('ehp', {})
        hold = mem.setdefault('pull', {})
        front = [a for a in A if a.role in ('ranged', 'melee') and not a.suicide]
        if len(front) >= 3:
            cx = sum(a.x for a in front) / len(front)
            cy = sum(a.y for a in front) / len(front)
            ex = sum(e.x for e in E) / len(E)
            ey = sum(e.y for e in E) / len(E)
            dx, dy = cx - ex, cy - ey
            n = math.hypot(dx, dy) or 1.0
            sx, sy = cx + PULL_BACK * dx / n, cy + PULL_BACK * dy / n
            for u in front:
                if u.id in out:
                    continue
                now = ehp(u)
                was = hist.get(u.id, now)
                frac = now / (u.max_hp + u.max_shield)
                hit = was - now > 0.5
                near = [e for e in E if not e.suicide and e.role != 'heal' and dist(u, e) <= e.range + u.radius + e.radius + 1.0]
                if hit and frac < PULL_FRAC:
                    hold[u.id] = PULL_STEPS
                if near and hold.get(u.id, 0) > 0:
                    hold[u.id] -= 1
                    healthier = [a for a in front if a.id != u.id and ehp(a) > now * 1.5]
                    if len(healthier) >= 2:
                        out[u.id] = move_toward(u, sx, sy) if dist(u, {'x': sx, 'y': sy}) > 1.5 else move_away(u, ex, ey)
                else:
                    hold[u.id] = 0
        for u in A:
            hist[u.id] = ehp(u)

        claimed = {}
        ready = [u for u in A if u.role == 'ranged' and not u.suicide and u.cooldown <= 0.05 and u.id not in out]
        ready.sort(key=lambda u: -u.damage)
        for u in ready:
            su = shot(u)
            best = None
            bestk = None
            for e in E:
                if not can_attack(u, e):
                    continue
                left = ehp(e) - claimed.get(e.id, 0.0)
                if left <= 0.3 or left > su + 0.4:
                    continue
                pri = 0 if e.suicide else (1 if (e.role == 'heal' or e.kind == 'medivac') else 2)
                k = (pri, left)
                if bestk is None or k < bestk:
                    bestk = k
                    best = e
            if best is not None:
                out[u.id] = attack(u, best)
                claimed[best.id] = claimed.get(best.id, 0.0) + su

        banes = [e for e in E if e.suicide]
        guns = [a for a in A if a.role == 'ranged' and not a.suicide]
        pool = [a for a in A if a.role == 'melee' and not a.suicide and a.id not in out]
        if banes and guns and pool:
            banes.sort(key=lambda b: min(dist(b, a) for a in guns))
            for b in banes:
                if not pool:
                    break
                nr = min(dist(b, a) for a in guns)
                if nr > 5.5:
                    continue
                m = min(pool, key=lambda a: dist(a, b))
                if dist(m, b) > nr + 1.5:
                    continue
                pool.remove(m)
                if can_attack(m, b):
                    out[m.id] = attack(m, b)
                else:
                    out[m.id] = move_toward(m, b.x, b.y)

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
            if threat is None:
                continue
            if threat.suicide:
                their = 2.25
            else:
                their = threat.range if threat.range and threat.range > 0.4 else 0.85
            faster = u.speed > threat.speed + 0.25
            holds = u.speed + 0.08 >= threat.speed and u.range >= their + 2.0
            if not holds and not faster:
                continue
            if td >= u.range - 0.1:
                continue
            if u.cooldown <= 0.05 and can_attack(u, threat) and td > their:
                out[u.id] = attack(u, threat)
            elif u.cooldown > 0.08 and td > their and holds:
                out[u.id] = move_away(u, threat.x, threat.y)
            elif u.cooldown > 0.08 and faster and td < u.range - 0.2:
                out[u.id] = move_away(u, threat.x, threat.y)
        return out
    except Exception:
        return {}
