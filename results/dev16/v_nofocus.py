READY = 0.5          # a unit whose cooldown ends within this step (seconds) fires this step
USE_FOCUS = False
USE_KITE = True
USE_SCREEN = True
USE_MEDIVAC = True
FOCUS_MELEE = True
USE_STALL = True
KITE_RANGED = True
STALL_STEPS = 10

AIR_HITTERS = ('marine', 'hydralisk', 'stalker')
ARMORED = ('stalker', 'marauder', 'colossus', 'medivac', 'spine_crawler')
LIGHT = ('marine', 'zealot', 'zergling', 'hydralisk')
BONUS = {'marauder': ('armored', 10.0), 'stalker': ('armored', 5.0), 'colossus': ('light', 5.0)}


def hit(u, e):
    """Damage one attack of u removes from e (bonus vs attribute, minus armor)."""
    d = float(u.damage)
    b = BONUS.get(u.kind)
    if b:
        if (b[0] == 'armored' and e.kind in ARMORED) or (b[0] == 'light' and e.kind in LIGHT):
            d += b[1]
    n = u.attacks if u.attacks and u.attacks > 0 else 1
    return max(0.5, d - float(e.armor)) * n


def in_range(u, e, slack=0.3):
    return can_attack(u, e) and dist(u, e) <= u.range + u.radius + e.radius + slack


def ehp(e):
    return float(e.hp) + float(e.shield)


def threat(e, A):
    """Damage per second e takes off us (healers count as their heal)."""
    if e.role == 'heal' or e.kind == 'medivac':
        return 9.0
    if e.suicide:
        near = min((dist(e, a) for a in A), default=99.0)
        return 40.0 if near < 6.0 else 8.0
    cd = e.max_cooldown if e.max_cooldown and e.max_cooldown > 0 else 1.0
    n = e.attacks if e.attacks and e.attacks > 0 else 1
    return float(e.damage) * n / cd


def act(obs, mem):
    A = list(obs.allies)
    E = list(obs.enemies)
    if not A or not E:
        return {}
    out = {}

    if USE_MEDIVAC:
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

    if USE_FOCUS:
        th = {e.id: threat(e, A) for e in E}
        claimed = {}
        ready = [u for u in A if (u.role == 'ranged' or (FOCUS_MELEE and u.role == 'melee')) and not u.suicide and u.cooldown < READY and u.id not in out]
        # units with fewest options choose first, so flexible units fill in around them
        opts = {u.id: [e for e in E if in_range(u, e)] for u in ready}
        ready = [u for u in ready if opts[u.id]]
        ready.sort(key=lambda u: (len(opts[u.id]), -u.damage))
        for u in ready:
            best, bk = None, None
            for e in opts[u.id]:
                left = ehp(e) - claimed.get(e.id, 0.0)
                h = hit(u, e)
                if left <= 0:
                    k = (1, -th[e.id] / max(ehp(e), 1.0))
                else:
                    # value of the shot: threat removed per point of health it still needs, prefer finishing blows
                    k = (0, -th[e.id] / max(left, h) * (1.5 if h >= left else 1.0))
                if bk is None or k < bk:
                    bk, best = k, e
            out[u.id] = attack(u, best)
            claimed[best.id] = claimed.get(best.id, 0.0) + hit(u, best)

    if USE_SCREEN:
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
                out[m.id] = attack(m, b) if can_attack(m, b) else move_toward(m, b.x, b.y)

    if USE_KITE:
        for u in A:
            if u.role != 'ranged' or u.suicide:
                continue
            if u.id in out and u.cooldown < READY:
                continue
            threat_u, td = None, 1e9
            for e in E:
                if e.role == 'heal' or e.kind == 'medivac':
                    continue
                if e.role != 'melee' and not e.suicide and not (KITE_RANGED and e.role == 'ranged'):
                    continue
                d = dist(u, e)
                if d < td:
                    td, threat_u = d, e
            if threat_u is None:
                continue
            their = 2.25 if threat_u.suicide else (threat_u.range if threat_u.range and threat_u.range > 0.4 else 0.85)
            faster = u.speed > threat_u.speed + 0.25
            holds = u.speed + 0.08 >= threat_u.speed and u.range >= their + 2.0
            if not holds and not faster:
                continue
            if td >= u.range - 0.1 or td <= their:
                continue
            if u.cooldown >= READY and (holds or (faster and td < u.range - 0.2)):
                out[u.id] = move_away(u, threat_u.x, threat_u.y)
    # --- stall breaker: nobody has lost health for a while, and a timeout is a loss, so go to them ---
    tot = sum(ehp(a) for a in A) + sum(ehp(e) for e in E) + 100.0 * (len(A) + len(E))
    quiet = 0 if tot < mem.get('tot', tot + 1.0) - 0.5 else mem.get('quiet', 0) + 1  # regeneration does not count
    mem['quiet'], mem['tot'] = quiet, tot
    if USE_STALL and quiet >= STALL_STEPS:
        for u in A:
            if u.id in out or u.role == 'heal' or u.kind == 'medivac':
                continue
            tgt = [e for e in E if e.kind != 'medivac' or u.kind in AIR_HITTERS]
            if not tgt:
                continue
            e = min(tgt, key=lambda e: dist(u, e))
            out[u.id] = attack(u, e) if in_range(u, e) else move_toward(u, e.x, e.y)
    return out
