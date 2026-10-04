"""The player's own edits: kept on the PC and applied on top of every roster this program builds.

The roster editor (gui) stores what the player changed by hand; `pipeline.build()` applies it as
its last step, after the downloaded data, so a correction survives every later update. Edits are
about people, not records: each one names a player by plain name and birthdate (`person_key`), so
it finds him in any later roster whichever record he has there.

    edits.json  {"version": 1, "players": {who: edit}}
    edit        {"label": "Connor McDavid",              shown in the editor's list
                 "was": {"first", "last", "birth"},         his name before a rename (see restore())
                 "set": {"first", "last", "num", "pos" (C/L/R/D/G), "shoots" (L/R),
                         "birth": [y, m, d], "country" (ISO3), "height_in", "weight_lb"},
                 "ratings": {"Passing": 90, ...},           EA attribute names (schema.EA_SKATER / EA_GOALIE)
                 "ovr": 75,                                 a new player without ratings: all attributes at this level
                 "team": <slot> or "FA",                    move, sign or release
                 "new": true}                               a player the game does not have: created

Rules the game enforces are kept: at most 40 a team, numbers unique on a team, goalies stay
goalies, a new player needs a spare record. What cannot be done is skipped and written to the
report ("edit skipped: ..."), never half done. `verify()` still checks the result.
"""
import json
import os

from . import datasource, lines, ratings
from . import layout as L
from .art.portraits import person_key
from .schema import EA_GOALIE, EA_SKATER, RATING_BASE

VERSION = 1
POSITIONS = ('C', 'L', 'R', 'D', 'G')


def path():
    return datasource.app_dir('edits.json')


def load(file=None):
    try:
        with open(file or path(), encoding='utf-8') as f:
            data = json.load(f)
        return data.get('players', {}) if data.get('version') == VERSION else {}
    except (OSError, ValueError, AttributeError):
        return {}


def save(players, file=None):
    target = file or path()
    tmp = target + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'version': VERSION, 'players': players}, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, target)


def birth_of(P, prow):
    return (P.get(prow, 'dnFq') + 1910, P.get(prow, 'pLKJ') + 1, P.get(prow, 'iwsK') + 1)


def who_of(P, prow):
    """The person key of a player record (what an edit names him by)."""
    return person_key(P.get(prow, 'PedH'), P.get(prow, 'RMbQ'), birth_of(P, prow))


def people(b):
    """person key -> player row, for everyone on a team or on the free-agent list. A person with
    two records (national-team goalies) is found by the one on a club team."""
    R, P = b.R, b.P
    live = b.live_entries()
    fa = {R.link_to_pid.get(l) for l in b.fa_links}
    rank = {}
    for pid, ents in live.items():
        prow = R.p_by_id.get(pid)
        if prow is None or not ents:
            continue
        club = any(b.U.get(e, 'BSXd') not in L.NATIONAL for e in ents)
        rank[prow] = 0 if club else 1
    for pid in fa:
        prow = R.p_by_id.get(pid)
        if prow is not None:
            rank.setdefault(prow, 0)
    out = {}
    for prow in sorted(rank, key=lambda r: (rank[r], r)):
        out.setdefault(who_of(P, prow), prow)
    return out


def restore(R, edits):
    """Before an update: players the player renamed (or gave another birthdate) get their original
    name back, so the downloaded data still recognises them; `apply()` renames them again at the
    end. Without this a renamed NHL player would look new to the update and be created twice."""
    P = R.P
    index = {}
    for prow in range(P.cur_rec):
        index.setdefault(who_of(P, prow), []).append(prow)
    for who in sorted(edits):
        e = edits[who]
        was, now = e.get('was'), e.get('set') or {}
        if not was or not any(now.get(k) for k in ('first', 'last', 'birth')):
            continue
        edited = person_key(now.get('first') or was['first'], now.get('last') or was['last'],
                            now.get('birth') or was['birth'])
        if edited == who:
            continue
        for prow in index.get(edited, []):
            P.set(prow, 'PedH', was['first'])
            P.set(prow, 'RMbQ', was['last'])
            y, m, d = was['birth']
            P.set(prow, 'dnFq', y - 1910)
            P.set(prow, 'pLKJ', m - 1)
            P.set(prow, 'iwsK', d - 1)


def apply(b, edits, say=None):
    """Apply the player's edits to a roster being built. Returns the teams whose players changed."""
    say = say or (lambda msg: None)
    if not edits:
        return set()
    found = people(b)
    changed = set()
    done = skipped = 0
    b.edited = (set(edits), set())     # who the edits name and the records they changed (verify lets them differ)
    for who in sorted(edits):
        e = edits[who]
        label = e.get('label') or who
        prow = found.get(who)
        if prow is None and e.get('new'):
            prow = _create(b, who, e)
            if prow is None:
                b.log.append(['edits', 'edit skipped', label, 'no spare player record left for a new player', ''])
                skipped += 1
                continue
            found[who] = prow
            changed |= _teams_of(b, prow)
        if prow is None:
            b.log.append(['edits', 'edit skipped', label, 'player not found in this roster', ''])
            skipped += 1
            continue
        b.edited[1].add(prow)
        problems = _set_fields(b, prow, e.get('set') or {}, changed)
        _set_ratings(b, prow, e.get('ratings') or {}, e.get('ovr') if e.get('new') else None)
        if 'team' in e:
            problems += _move(b, prow, e['team'], changed)
        for text in problems:
            b.log.append(['edits', 'edit skipped', label, text, ''])
        b.log.append(['edits', 'edited', label, ', '.join(sorted(k for k in e if k not in ('label',))), ''])
        done += 1
    _relines(b, changed, say)
    say(f"My edits: {done} applied" + (f", {skipped} skipped (see the report)" if skipped else ""))
    return changed


# --- the parts of an edit ---------------------------------------------------------------------------
def _teams_of(b, prow):
    pid = b.P.get(prow, 'zIBw')
    return {b.U.get(e, 'BSXd') for e in b.live_entries().get(pid, [])}


def _set_fields(b, prow, fields, changed):
    P, U = b.P, b.U
    problems = []
    if fields.get('first'):
        b.set_text(prow, 'PedH', fields['first'])
    if fields.get('last'):
        b.set_text(prow, 'RMbQ', fields['last'])
    if fields.get('pos') in POSITIONS:
        new, old = L.POS_CODE[fields['pos']], P.get(prow, 'aljv')
        if (new == 4) != (old == 4):
            problems.append("a goalie cannot become a skater or the other way round")
        else:
            b.set_position(prow, new)
            if new != old:
                changed |= _teams_of(b, prow)
    if fields.get('shoots') in ('L', 'R'):
        P.set(prow, 'pkRG', 0 if fields['shoots'] == 'L' else 1)
    if fields.get('birth'):
        y, m, d = fields['birth']
        P.set(prow, 'dnFq', max(0, y - 1910))
        P.set(prow, 'pLKJ', m - 1)
        P.set(prow, 'iwsK', d - 1)
    if fields.get('country'):
        code = L.country_code(fields['country'])
        if code is None:
            problems.append(f"the game has no country {fields['country']}")
        else:
            P.set(prow, 'hleL', code)
    if fields.get('height_in'):
        P.set(prow, 'QBpy', max(0, min(31, int(fields['height_in']) - 54)))
    if fields.get('weight_lb'):
        P.set(prow, 'WZNs', max(0, min(255, int(fields['weight_lb']) - 120)))
    if fields.get('num'):
        n = int(fields['num'])
        if not 1 <= n <= 99:
            problems.append(f"number {n}: numbers go from 1 to 99")
        else:
            P.set(prow, 'tRVs', n)
            pid = P.get(prow, 'zIBw')
            for e in b.live_entries().get(pid, []):
                U.set(e, 'tRVs', n)
                _free_number(b, U.get(e, 'BSXd'), e, n)
    return problems


def _free_number(b, team, keep, n):
    """Another player on `team` wearing `n` gets the next free number (the edited one wins)."""
    U = b.U
    ents = b.entries_on(team)
    taken = {U.get(e, 'tRVs') for e in ents}
    for e in ents:
        if e != keep and U.get(e, 'tRVs') == n:
            free = next(x for x in range(2, 99) if x not in taken)
            U.set(e, 'tRVs', free)
            taken.add(free)
            b.log.append([b.R.team_name(team), 'number changed', b.R.name(b.prow_of_entry(e)),
                          f"#{n} given to an edited player", free])


def _set_ratings(b, prow, values, ovr=None):
    P = b.P
    goalie = P.get(prow, 'aljv') == 4
    tname = ratings.GOALIE_TABLE if goalie else ratings.SKATER_TABLE
    row = b.ai_row[tname].get(P.get(prow, 'zIBw'))
    if row is None:
        return
    table = b.R.f[tname]
    amap = EA_GOALIE if goalie else EA_SKATER
    if ovr and not values:
        ratings.write_attributes(table, row, {'ovr': ovr}, b.ovr_offset[goalie])
    for label, v in values.items():
        if label in amap and v is not None:
            table.set(row, amap[label], ratings.clamp(int(v) - RATING_BASE))


def _move(b, prow, target, changed):
    """Put a player on team `target` (a slot), or release him to the free agents ('FA')."""
    R, U, P = b.R, b.U, b.P
    pid = P.get(prow, 'zIBw')
    live = b.live_entries()
    clubs = [e for e in live.get(pid, []) if U.get(e, 'BSXd') not in L.NATIONAL and U.get(e, 'BSXd') not in L.MIRROR_OF]
    if target == 'FA':
        for e in clubs:
            changed.add(U.get(e, 'BSXd'))
            b.release(e, live)
        P.set(prow, 'BSXd', 0)
        return []
    target = int(target)
    if target in L.MIRROR_OF or not 0 <= target < R.T.cur_rec:
        return [f"team {target} cannot be chosen"]
    if any(U.get(e, 'BSXd') == target for e in clubs):
        return []
    if len(b.entries_on(target)) >= L.MAX_PER_TEAM:
        return [f"{R.team_name(target)} has {L.MAX_PER_TEAM} players already (the most the game allows)"]
    if clubs:
        first, rest = clubs[0], clubs[1:]
        changed.add(U.get(first, 'BSXd'))
        b.move_entry(first, target)
        for e in rest:
            changed.add(U.get(e, 'BSXd'))
            b.release(e, live)
        entry = first
    else:
        fa = [l for l in b.fa_links if R.link_to_pid.get(l) == pid]
        entry = b.new_entry(target, fa[0] if fa else b.new_link(pid), prow)
        b.arrivals.setdefault(target, []).append(entry)
        b.drop_fa(pid)
    changed.add(target)
    _free_number(b, target, entry, U.get(entry, 'tRVs'))
    if target not in L.NATIONAL:        # a player's contract team is his club (as the leagues set it)
        P.set(prow, 'BSXd', target + 1)
    if target in L.NHL_PRIMARY:
        b.set_pro_team(prow, target)
    return []


def _create(b, who, e):
    """A new player on a spare record (as the club leagues create theirs). None when none is left."""
    fields = e.get('set') or {}
    pos = L.POS_CODE.get(fields.get('pos') or 'C', 0)
    name = f"{fields.get('first', '')} {fields.get('last', '')}".strip()
    prow = b.take_record(pos, name, required=False)
    if prow is None:
        return None
    y = (fields.get('birth') or [b.data.season_year - 22, 1, 1])[0]
    b.donors.reset_identity(prow, name, L.country_code(fields.get('country')), y)
    b.P.set(prow, 'JzFM', '')
    b.P.set(prow, 'BSXd', 0)
    b.placed.add(b.P.get(prow, 'zIBw'))
    if not fields.get('birth'):
        fields = dict(fields, birth=[y, 1, 1])
    _set_fields(b, prow, fields, set())
    b.log.append(['edits', 'created', name, 'a new player of your own', fields.get('num') or ''])
    if e.get('team') in (None, 'FA'):
        b.fa_links.append(b.new_link(b.P.get(prow, 'zIBw')))
    return prow


def _relines(b, changed, say):
    """Lines of the teams the edits changed, dealt afresh by rating and position (lines.py): the
    same players always get the same lines, so a later update with the same edits changes nothing.
    (Copying the team's previous line pattern would not: the pattern itself moves between runs.)"""
    from .leagues.clubs import _letters
    for team in sorted(t for t in changed if t not in L.MIRROR_OF):
        if not b.entries_on(team):
            continue
        # the captain and alternates who are still there keep their letters; a missing one is
        # given to the best dressed skater
        letters = {e: {1: 'C', 2: 'A'}.get(b.U.get(e, 'lcCm')) for e in b.entries_on(team)}
        try:
            lines.build_lines(b, team)
            _letters(b, team, letters)
        except lines.NotEnoughPlayers as err:
            say(f"My edits: {err}")
            for e in b.entries_on(team):
                b.clear_lines(e)
    if any(t in L.NHL_PRIMARY for t in changed):
        b.sync_mirrors()
