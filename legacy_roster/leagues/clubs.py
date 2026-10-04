"""Give a club league its real clubs: every player of the league's rosters on his club.

The league data (from the data pack) already says which club goes into which team slot. For
each club the players are matched to records in the save; the ones that are not there get a
record of their own with estimated ratings. Whoever was on those slots before and is not on
the new roster leaves: prospect-pool players move to spare custom slots (pools.py), former club
players become free agents.

New players need spare records (donors.py). If those run out, every club first gets the players
it needs to dress a full line-up; the rest of the depth is skipped and listed in the report.
"""
from collections import Counter

from .. import layout as L
from .. import lines, ratings
from ..estimate import Estimator
from ..matching import match_club, norm
from . import pools

CORE = {'G': 2, 'D': 6, 'F': 12}    # a dressed line-up: created before any club's depth players
JUNIOR_AGE = {'chl': 20}            # free agents a junior club may sign to fill its line-up are this young


def group(pos):
    return pos if pos in ('G', 'D') else 'F'


def kind(g):
    """Record pools: goalies have their own attribute table, skaters share one."""
    return 'G' if g == 'G' else 'S'


def listed(teams):
    """The league's players, each once (a feed may list a player twice), with slot and club."""
    people, seen = [], set()
    for t in teams:
        for p in sorted(t['players'], key=lambda p: not p.get('num')):     # a listing with a number first
            key_ = (norm(p['first']), norm(p['last']), tuple(p['birth']))
            if key_ in seen:
                continue
            seen.add(key_)
            q = dict(p)
            q.update(birth=tuple(q['birth']), slot=t['slot'], team=t['abbr'])
            people.append(q)
    return people


def core_needs(b, league):
    """How many new records this league needs to give every club a dressable 20 (by record kind,
    as the save stands now): the pipeline keeps that many back from the depth of earlier leagues."""
    people = match_club(b.R, listed(league['teams']))
    have = Counter((p['slot'], group(p['pos'])) for p in people if p['row'] is not None)
    new = Counter((p['slot'], group(p['pos'])) for p in people if p['row'] is None)
    need = Counter()
    for (slot, g), n in new.items():
        need[kind(g)] += min(n, max(0, CORE[g] - have[(slot, g)]))
    return need


def creation_order(b, key, league, people, live, est):
    """Matched players first, then each club's core line-up, then depth -- so that when player
    records run out, the clubs still dress 20. Depth players are marked p['depth']."""
    on_nhl = lambda p: any(b.U.get(e, 'BSXd') in L.NHL_PRIMARY for e in live.get(b.P.get(p['row'], 'zIBw'), []))
    have = Counter((p['slot'], group(p['pos'])) for p in people if p['row'] is not None and not on_nhl(p))
    fresh = [(k, p) for k, p in enumerate(people) if p['row'] is None]
    level = lambda p: est.target(key, L.POS_CODE.get(p['pos'], 0), b.data.season_year - p['birth'][0],
                                 f"{p['first']} {p['last']}", p.get('letter'), p.get('rookie'), _is_import(p, league))
    core = set()
    for k, p in sorted(fresh, key=lambda kp: (-level(kp[1]), kp[0])):
        g = (p['slot'], group(p['pos']))
        if have[g] < CORE[g[1]]:
            have[g] += 1
            core.add(k)
    for k, p in fresh:
        p['depth'] = k not in core
    return ([p for p in people if p['row'] is not None] + [p for k, p in fresh if k in core]
            + [p for k, p in fresh if k not in core])


def update_league(b, key, league, say):
    """Rebuild the slots of one league. Returns the set of team ids that were rebuilt."""
    R, U, P, T = b.R, b.U, b.P, b.R.T
    teams = league['teams']
    home = L.country_code(league.get('country'))
    people = listed(teams)
    b.donors.reserve(people)
    match_club(R, people)
    est = Estimator(b)
    slots = [t['slot'] for t in teams]
    departures_before = {t: len(v) for t, v in b.departures.items()}

    # who is on these slots now, and what the slots were called before they get their club names
    leftovers = {e: slot for slot in slots for e in b.entries_on(slot)}
    was_pool = {slot: ((T.get(slot, 'JkmY'), T.get(slot, 'RPbr')) if pools.is_pool(R, slot) else None) for slot in slots}
    for t in teams:
        T.set(t['slot'], 'JkmY', t['full'])
        L.set_city(T, t['slot'], t['short'])        # custom slots (Coachella, Henderson): a key, see layout
        T.set(t['slot'], 'nnsx', t['abbr'])
        T.set(t['slot'], 'RPbr', t['art'])
        if t.get('logo'):
            b.logos[t['slot']] = t['logo']

    live = b.live_entries()     # pid -> entries that exist right now
    people = creation_order(b, key, league, people, live, est)
    parents = affiliates(R) if key == 'ahl' else {}
    claimed, changed, numbers = set(), set(), {}
    letters = {}
    stats = Counter()
    forward_cycle = 0
    for p in people:
        target = p['slot']
        name = f"{p['first']} {p['last']}"
        age = b.data.season_year - p['birth'][0]
        row = p['row']
        if row is not None and row in claimed:       # listed twice in the feed
            continue
        if row is not None:
            pid = P.get(row, 'zIBw')
            ents = live.get(pid, [])
            if any(U.get(e, 'BSXd') in L.NHL_PRIMARY for e in ents):
                stats['on an NHL roster'] += 1       # NHL.com is the authority for NHL players
                continue
            if pid in b.placed:                      # another league listed him too: the first one keeps him
                stats['listed by another league too'] += 1
                continue
            claimed.add(row)
            b.placed.add(pid)
            here = [e for e in ents if U.get(e, 'BSXd') == target]
            # one club at a time: his entries on other clubs, pools and junior teams go
            others = [e for e in ents if U.get(e, 'BSXd') != target
                      and U.get(e, 'BSXd') not in L.NATIONAL and U.get(e, 'BSXd') not in L.NHL_ALL]
            if here:
                e = here[0]
            elif others:
                e = others.pop(0)
                frm = R.team_name(leftovers[e]) if e in leftovers and was_pool[leftovers[e]] is None else None
                frm = frm or (was_pool[leftovers[e]][0] if e in leftovers else R.team_name(U.get(e, 'BSXd')))
                b.move_entry(e, target)
                changed.add(target)
                b.log.append([p['team'], 'joined', name, f"from {frm}", p.get('num') or ''])
                stats['moved'] += 1
            else:
                fa = [l for l in b.fa_links if R.link_to_pid.get(l) == pid]
                e = b.new_entry(target, fa[0] if fa else b.new_link(pid), row)
                b.arrivals.setdefault(target, []).append(e)
                live.setdefault(pid, []).append(e)
                changed.add(target)
                b.log.append([p['team'], 'joined', name, 'was a free agent' if fa else 'was without a team',
                              p.get('num') or ''])
                stats['added'] += 1
            for x in others:
                b.depart(x)
                b.deleted.add(x)
                leftovers.pop(x, None)
            live[pid] = [x for x in live.get(pid, []) if x not in b.deleted]
            leftovers.pop(e, None)
            b.drop_fa(pid)
            _feed_position(b, row, p, live, name)
            if key == 'ahl' and pid not in b.ea_rated and b.data.ea_ratings:
                # EA rates NHL and AHL players; one who just came down from the NHL was on neither
                # when the ratings were written
                ea = b.ea_rating_for(P.get(row, 'PedH'), P.get(row, 'RMbQ'), p['birth'], by_name=True)
                if ea and ratings.is_goalie(ea) == (P.get(row, 'aljv') == 4):
                    b.write_ea_rating(row, ea)
            if p.get('stale'):                       # an EA-era record: fix the birth year, re-rate
                P.set(row, 'dnFq', p['birth'][0] - 1910)
                if pid not in b.ea_rated:            # EA's own ratings always win over an estimate
                    est.shift(row, est.target(key, P.get(row, 'aljv'), age, name, p.get('letter'), p.get('rookie'),
                                              _is_import(p, league)))
                    stats['re-rated'] += 1
        else:
            if p['pos'] == 'F':                      # feeds that do not split forwards: C, LW, RW in turn
                pos = forward_cycle % 3
                forward_cycle += 1
            else:
                pos = L.POS_CODE[p['pos']]
            g = kind(group(p['pos']))
            spare = b.donors.left(g) - b.core_reserve[g]
            # depth players only while records remain beyond what later leagues need for their line-ups
            row = b.take_record(pos, name, required=False) if not p['depth'] or spare > 0 else None
            if row is None:                          # no spare record left for this position
                b.log.append([p['team'], 'skipped', name, 'no free player record left', p.get('num') or ''])
                stats['skipped: no free record'] += 1
                continue
            claimed.add(row)
            old = R.name(row)
            pid = P.get(row, 'zIBw')
            b.placed.add(pid)
            b.donors.reset_identity(row, name, L.country_code(p.get('country')) or home, p['birth'][0])
            b.set_text(row, 'PedH', p['first'])
            b.set_text(row, 'RMbQ', p['last'])
            P.set(row, 'JzFM', '')
            y, m, d = p['birth']
            P.set(row, 'iwsK', d - 1)
            P.set(row, 'pLKJ', m - 1)
            P.set(row, 'dnFq', y - 1910)
            ea = b.ea_rating_for(p['first'], p['last'], p['birth'], by_name=key == 'ahl') if b.data.ea_ratings else None
            if not (ea and ratings.is_goalie(ea) == (pos == 4) and b.write_ea_rating(row, ea)):
                est.write(row, est.target(key, pos, age, name, p.get('letter'), p.get('rookie'),
                                          _is_import(p, league)), name, age)
            e = b.new_entry(target, b.new_link(pid), row)
            b.arrivals.setdefault(target, []).append(e)
            live.setdefault(pid, []).append(e)
            changed.add(target)
            note = "; birthdate approximate (the league gives the age only)" if p.get('birth_approx') else ''
            b.log.append([p['team'], 'created', name, f"reused record of {old}{note}", p.get('num') or ''])
            stats['created'] += 1
        _bio(b, row, p)
        if p.get('photo'):
            b.photos[row] = p['photo']
        # a club player's contract team is his club; only NHL property keeps contract terms
        P.set(row, 'BSXd', target + 1)
        if p.get('nhl_contract') and parents.get(target) is not None:
            _nhl_contract(b, row, parents[target])
        if not P.get(row, 'WBbd'):
            for f in ('GDhI', 'dhKk', 'IrlK', 'IzRv'):
                P.set(row, f, 0)
        numbers[e] = p.get('num')
        letters[e] = p.get('letter')

    # a club the feed leaves short at a position (its listed defencemen are with the NHL club, its
    # goalies could not get a record): a former player of that position stays, else a free agent signs
    for slot in slots:
        _fill_lineup(b, slot, leftovers, live, T.get(slot, 'nnsx'), stats, JUNIOR_AGE.get(key))

    # whoever is still on these slots is not on the new rosters
    displaced = {}
    for e, slot in sorted(leftovers.items()):
        changed.add(slot)
        if was_pool[slot] is not None:
            displaced.setdefault(was_pool[slot], []).append(e)
        else:
            name = R.name(b.prow_of_entry(e))
            became_fa = b.release(e, live)
            b.log.append([T.get(slot, 'nnsx'), 'left the club', name, 'now a free agent' if became_fa else '',
                          U.get(e, 'tRVs')])
            stats['left'] += 1
    if displaced:
        pools.relocate(b, displaced)
        stats['pool players moved'] = sum(len(v) for v in displaced.values())

    rebuilt = set(slots)
    for slot in slots:
        ents = b.entries_on(slot)
        for e in sorted(ents, key=lambda e: (b.q(e), e))[:max(0, len(ents) - L.MAX_PER_TEAM)]:   # 40 a team
            name = R.name(b.prow_of_entry(e))
            b.release(e, live)
            b.log.append([T.get(slot, 'nnsx'), 'left the club', name, 'no room (40 players at most)', U.get(e, 'tRVs')])
            changed.add(slot)
        ents = b.entries_on(slot)
        taken = Counter()
        for e in ents:
            if numbers.get(e):
                U.set(e, 'tRVs', min(numbers[e], 99))
        for e in sorted(ents, key=lambda e: (not numbers.get(e), -b.q(e))):      # listed numbers win a clash
            n = U.get(e, 'tRVs')
            if not n or taken[n]:
                n = next(x for x in range(2, 99) if not taken[x])
                U.set(e, 'tRVs', n)
            taken[n] += 1
        complete = len({f for e in ents for f in b.held(e)}) == len(b.flags)
        if slot in changed or not complete:
            short = Counter(group('CLRDG'[P.get(b.prow_of_entry(e), 'aljv')]) for e in ents)
            try:
                if short['G'] < CORE['G'] or short['D'] < CORE['D'] or short['F'] < CORE['F']:
                    raise lines.NotEnoughPlayers(f"{R.team_name(slot)}: {short['G']} goalies, {short['D']} "
                                                 f"defencemen, {short['F']} forwards -- cannot dress 20")
                lines.build_lines(b, slot)
            except lines.NotEnoughPlayers as err:
                # nobody left to fill in: the club keeps its players but no lines, as AHL and junior
                # teams had them in the base roster
                say(str(err))
                for e in ents:
                    b.clear_lines(e)
                rebuilt.discard(slot)
                stats['clubs without a full line-up'] += 1
                continue
            _letters(b, slot, letters)

    # teams elsewhere that lost a player to this league: hand his line slots to a team-mate
    for team, deps in list(b.departures.items()):
        fresh = deps[departures_before.get(team, 0):]
        if fresh and team not in slots and team not in L.NHL_PRIMARY and team not in pools.SPARE_SLOTS:
            b.departures[team] = fresh
            b.fill_lines(team)
            b.departures[team] = deps
    if stats['skipped: no free record']:
        say(f"{league['label']}: {stats['skipped: no free record']} players skipped, "
            "no free player record left (they are listed in the report)")
    for k, v in sorted(stats.items()):
        b.log.append([league['label'], 'summary', k, v, ''])
    b.league_stats[key] = dict(stats)
    return rebuilt


def _fill_lineup(b, slot, leftovers, live, abbr, stats, max_age=None):
    """Top a club up to a dressable 20 (2 G, 6 D, 12 F): first with former players of the slot at the
    missing position (so a second run keeps the same ones), best first, then with prospect-pool
    players and free agents (for a junior club only those of junior age)."""
    P, U, T = b.P, b.U, b.R.T
    young_enough = lambda prow: max_age is None or b.data.season_year - (P.get(prow, 'dnFq') + 1910) <= max_age
    cls = lambda prow: group('CLRDG'[P.get(prow, 'aljv')])
    have = Counter(cls(b.prow_of_entry(e)) for e in b.entries_on(slot) if e not in leftovers)
    for g, need in CORE.items():
        missing = need - have[g]
        if missing <= 0:
            continue
        former = sorted((e for e, s in leftovers.items() if s == slot and cls(b.prow_of_entry(e)) == g),
                        key=lambda e: (-b.q(e), e))
        for e in former[:missing]:
            leftovers.pop(e)
            b.log.append([abbr, 'stays to fill the line-up', b.R.name(b.prow_of_entry(e)), f"needed at {g}",
                          U.get(e, 'tRVs')])
            stats['kept to fill the line-up'] += 1
            missing -= 1
        if missing <= 0:
            continue
        free = []      # (-quality, pid, free-agent link or pool entry, record)
        for link in b.fa_links:
            pid = b.R.link_to_pid.get(link)
            prow = b.R.p_by_id.get(pid)
            if prow is not None and cls(prow) == g and young_enough(prow) and not any(
                    U.get(x, 'BSXd') not in L.NATIONAL for x in live.get(pid, [])):
                free.append((-b.quality.get(pid, 0), pid, ('fa', link), prow))
        for t in pools.SPARE_SLOTS:
            if T.get(t, 'NYKk') and pools.is_pool(b.R, t):
                for e in b.entries_on(t):
                    prow = b.prow_of_entry(e)
                    pid = b.pid_of_entry(e)
                    if cls(prow) == g and young_enough(prow) and pid not in b.placed:
                        free.append((-b.quality.get(pid, 0), pid, ('pool', e), prow))
        for _, pid, (where, x), prow in sorted(free)[:missing]:
            if where == 'fa':
                e = b.new_entry(slot, x, prow)
                b.arrivals.setdefault(slot, []).append(e)
                live.setdefault(pid, []).append(e)
                b.drop_fa(pid)
                detail = f"free agent, needed at {g}"
            else:
                detail = f"from {T.get(U.get(x, 'BSXd'), 'JkmY')}, needed at {g}"
                e = x
                b.move_entry(e, slot)
            b.placed.add(pid)
            P.set(prow, 'BSXd', slot + 1)
            b.log.append([abbr, 'signed to fill the line-up', b.R.name(prow), detail, U.get(e, 'tRVs')])
            stats['signed to fill the line-up'] += 1


def _feed_position(b, row, p, live, name):
    """The league's current position for a player it lists (a feed that only says 'forward' moves a
    defenceman up front, and leaves a forward's position alone). Goalies never change, and neither
    do players on a national team: their squad's lines were dealt by position."""
    cur = b.P.get(row, 'aljv')
    want = (0 if cur == 3 else cur) if p['pos'] == 'F' else L.POS_CODE.get(p['pos'])
    if want is None or want == cur or 4 in (cur, want):
        return
    if any(b.U.get(e, 'BSXd') in L.NATIONAL for e in live.get(b.P.get(row, 'zIBw'), [])):
        return
    b.set_position(row, want)
    b.log.append([p['team'], 'position changed', name, f"{L.POS_NAME[cur]} to {L.POS_NAME[want]}", ''])


def affiliates(R):
    """AHL slot -> its NHL parent slot. NHL teams name their farm team in ttOk.ahlaffiliate (AHL
    slot + 1, six bits); Seattle's and Vegas's farm teams sit in custom slots 234/235, beyond that."""
    T = R.T
    out = {T.get(n, 'TxsC') - 1: n for n in sorted(L.NHL_PRIMARY) if T.get(n, 'TxsC')}
    out.update(L.AHL_PARENT_EXTRA)
    return out


def _nhl_contract(b, row, parent):
    """An AHL player on an NHL contract: his NHL organisation holds his rights, and he has a
    two-way deal (a default one if the save had none)."""
    P = b.P
    b.set_pro_team(row, parent)
    if not P.get(row, 'GDhI') or not P.get(row, 'dhKk'):
        entry_level = P.get(row, 'dnFq') + 1910 >= b.data.season_year - 22
        P.set(row, 'GDhI', 3 if entry_level else 1)
        P.set(row, 'dhKk', 146 if entry_level else 116)      # ~$975k entry-level / ~$775k minimum
        P.set(row, 'IrlK', 0)
        P.set(row, 'IzRv', 0)
    P.set(row, 'contractis2way', 1)


def _is_import(p, league):
    """A player from abroad (only in leagues of one country)."""
    home = L.country_code(league.get('country'))
    return home is not None and bool(p.get('country')) and L.country_code(p['country']) != home


def _bio(b, row, p):
    """Facts the league publishes about a player overwrite what the save had."""
    P = b.P
    if p.get('height_cm'):
        P.set(row, 'QBpy', max(0, min(31, round(p['height_cm'] / 2.54) - 54)))
    if p.get('weight_kg'):
        P.set(row, 'WZNs', max(0, min(255, round(p['weight_kg'] * 2.20462) - 120)))
    if p.get('shoots') in ('L', 'R'):
        P.set(row, 'pkRG', 0 if p['shoots'] == 'L' else 1)
    if p.get('num'):
        P.set(row, 'tRVs', min(p['num'], 99))


def _letters(b, team, listed):
    """One captain and two alternates among the dressed skaters: the club's own where listed."""
    U = b.U
    ents = b.entries_on(team)
    for e in ents:
        U.set(e, 'lcCm', 0)
    dressed = [e for e in ents if U.get(e, 'jZSh') and b.cls(e) != 'G']
    best = sorted(dressed, key=lambda e: (-b.q(e), e))
    captain = next((e for e in dressed if listed.get(e) == 'C'), None) or (best[0] if best else None)
    if captain is None:
        return
    U.set(captain, 'lcCm', 1)
    alternates = [e for e in dressed if listed.get(e) == 'A' and e != captain][:2]
    alternates += [e for e in best if e != captain and e not in alternates][:2 - len(alternates)]
    for e in alternates:
        U.set(e, 'lcCm', 2)
