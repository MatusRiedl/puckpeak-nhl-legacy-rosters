"""The player's own edits: kept on the PC and applied on top of every roster this program builds.

The roster editor (gui) stores what the player changed by hand; `pipeline.build()` applies it as
its last step, after the downloaded data, so a correction survives every later update. Edits are
about people, not records: each one names a player by plain name and birthdate (`person_key`), so
it finds him in any later roster whichever record he has there.

    edits.json  {"version": 1, "players": {who: edit}, "teams": {slot: team edit}}
    team edit   {"full", "city", "abbr", "logo": "file:<path>",
                 "equipment": {"tape": 1, "sock_tuck": 3, ...},   for every skater of the team, except what he chose himself
                 "uniforms": {"colours": {"primary": "#rrggbb", "secondary": "#rrggbb", "crest": "file:<path>"},
                              "versions": {"<variant>": "game" | "colours" | "file:<path of a 1024 x 1024 colour map>"}},
                 "ice": {"use": "game" | "logo" | "file:<path>", "arena": "<name on the ice>"}}   (apply_teams;
                 the jerseys and the ice are installed by art/looks.py with the photos and logos)
    edit        {"label": "Connor McDavid",              shown in the editor's list
                 "was": {"first", "last", "birth"},         his name before a rename (see restore())
                 "set": {"first", "last", "num", "pos" (C/L/R/D/G), "shoots" (L/R),
                         "birth": [y, m, d], "country" (ISO3), "height_in", "weight_lb"},
                 "ratings": {"Passing": 90, ...},           EA attribute names (schema.EA_SKATER / EA_GOALIE)
                 "ovr": 75,                                 a new player without ratings: all attributes at this level
                 "team": <slot> or "FA",                    move, sign or release
                 "equipment": {"stick": 105, "tape": 1, ...},  skaters: equipment.CHOICES, goalies: equipment.GOALIE_CHOICES
                                                            (the game's own model numbers)
                 "mask_picture": "file:<path>",             a goalie's own picture on his mask (512 x 512)
                 "photo": "file:<path>",                    a picture of the player's own
                 "new": true}                               a player the game does not have: created

Rules the game enforces are kept: at most 40 a team, numbers unique on a team, goalies stay
goalies, a new player needs a spare record. What cannot be done is skipped and written to the
report ("edit skipped: ..."), never half done. `verify()` still checks the result.
"""
import json
import os

from . import datasource, equipment, lines, ratings
from . import layout as L
from .art.portraits import person_key
from .schema import EA_GOALIE, EA_SKATER, RATING_BASE

VERSION = 1
POSITIONS = ('C', 'L', 'R', 'D', 'G')


def path():
    return datasource.app_dir('edits.json')


def _load_all(file=None):
    try:
        with open(file or path(), encoding='utf-8') as f:
            data = json.load(f)
        return data if data.get('version') == VERSION else {}
    except (OSError, ValueError, AttributeError):
        return {}


def load(file=None):
    """The player edits: {who: edit}."""
    return _load_all(file).get('players', {})


def load_teams(file=None):
    """The team edits: {slot (as text): {"full", "city", "abbr", "logo": "file:<path>"}}."""
    return _load_all(file).get('teams', {})


def save(players=None, file=None, teams=None):
    """Store the edits; the part not given (players or teams) stays as it was."""
    target = file or path()
    data = _load_all(target)
    out = {'version': VERSION, 'players': data.get('players', {}) if players is None else players,
           'teams': data.get('teams', {}) if teams is None else teams}
    tmp = target + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, target)


def keep_picture(source):
    """A copy of a picture the player chose, kept with the program's files (the original may be
    moved or deleted later). Returns the 'file:' link edits and photos use."""
    import hashlib
    import shutil
    with open(source, 'rb') as f:
        digest = hashlib.sha1(f.read()).hexdigest()[:16]
    target = datasource.app_dir('art', 'mine', digest + os.path.splitext(source)[1].lower())
    if not os.path.exists(target):
        shutil.copyfile(source, target)
    return 'file:' + target


def apply_teams(b, teams, say=None):
    """The player's own team names and logos (Roster editor). The menus show the names through
    the game's text file, written with photos and logos (art/portraits.names, loc.py)."""
    T = b.R.T
    for key in sorted(teams, key=int):
        slot, e = int(key), teams[key]
        if not 0 <= slot < T.cur_rec:
            continue
        for field, part in (('fullname', 'full'), ('shortname', 'city'), ('abbrname', 'abbr')):
            if e.get(part):
                limit = T.field(field).bits // 8 - 1
                text = e[part]
                while len(text.encode('utf-8')) > limit:
                    text = text[:-1]
                if field == 'shortname':
                    L.set_city(T, slot, text)       # a custom team's city is a key (layout.city_key)
                else:
                    T.set(slot, field, text)
        if any(e.get(p) for p in ('full', 'city', 'abbr')):
            b.team_names[slot] = True
        if e.get('logo'):
            b.logos[slot] = e['logo']
        if e.get('equipment'):
            _team_equipment(b, slot, e['equipment'])
        if e.get('uniforms') or e.get('ice'):
            b.looks_edits[slot] = {k: e[k] for k in ('uniforms', 'ice') if e.get(k)}
        b.log.append(['edits', 'team edited', b.R.team_name(slot), ', '.join(sorted(e)), ''])
    if teams and say:
        say(f"My edits: {len(teams)} teams")


def birth_of(P, prow, base=1910):
    """A record's birthdate. `base` 1900: the game's own roster before stock.prepare moved its
    birth years to this program's convention."""
    return (P.get(prow, 'dnFq') + base, P.get(prow, 'pLKJ') + 1, P.get(prow, 'iwsK') + 1)


def who_of(P, prow, base=1910):
    """The person key of a player record (what an edit names him by)."""
    return person_key(P.get(prow, 'PedH'), P.get(prow, 'RMbQ'), birth_of(P, prow, base))


def people(b):
    """person key -> player row, for everyone on a team or on the free-agent list. A person with
    two records (national-team goalies) is found by the one on a club team."""
    return people_and_copies(b)[0]


def people_and_copies(b):
    """(people(b), person key -> the player's other records): a person on a club and a national team
    (23 goalies, Binnington) has a record for each, and an edit has to reach both."""
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
    out, copies = {}, {}
    for prow in sorted(rank, key=lambda r: (rank[r], r)):
        who = who_of(P, prow)
        if who in out:
            copies.setdefault(who, []).append(prow)
        else:
            out[who] = prow
    return out, copies


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
    found, copies = people_and_copies(b)
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
        if e.get('photo'):                  # a picture of the player's own, installed with photos and logos
            b.photos[prow] = e['photo']
        problems = _set_fields(b, prow, e.get('set') or {}, changed)
        _set_ratings(b, prow, e.get('ratings') or {}, e.get('ovr') if e.get('new') else None)
        problems += _set_equipment(b, prow, e.get('equipment'))
        for other in copies.get(who, []):          # the same person's national-team record: same name, same ratings
            b.edited[1].add(other)
            _set_fields(b, other, {k: v for k, v in (e.get('set') or {}).items() if k not in ('pos', 'num')}, set())
            _set_ratings(b, other, e.get('ratings') or {})
            _set_equipment(b, other, e.get('equipment'))
        if e.get('mask_picture'):
            problems += _mask_picture(b, [prow] + list(copies.get(who, [])), e['mask_picture'])
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


def _set_equipment(b, prow, values):
    """A player's own equipment choices (equipment.CHOICES for skaters, equipment.GOALIE_CHOICES for goalies).
    Returns the problems."""
    if not values:
        return []
    kind = 'goalie' if b.P.get(prow, 'aljv') == 4 else 'skater'
    table = b.R.f[equipment.KINDS[kind][0]]
    row = b.equipment_row(prow, kind)
    if row is None:
        return ["equipment: this player has no equipment record"]
    ok, problems = equipment.clean(values, table, kind)
    equipment.write(table, row, ok, kind)
    if kind == 'goalie' and 'mask' in ok:
        table.set(row, equipment.GOALIE_CODE[equipment.MASK_TYPE], 0)
    if not hasattr(b, 'equipment_set'):
        b.equipment_set = {}
    b.equipment_set.setdefault(prow, set()).update(ok)       # the team's choices do not override these
    return problems


def _mask_picture(b, prows, path):
    """A goalie's own picture on his mask (art/masks.py installs it). The goalie (and his national-team copies, `prows`)
    wears a mask number that has a texture on the disc and that nobody else wears: his own when it is that already (so a
    second run changes nothing), else the highest free one. Returns the problems."""
    rows = [r for r in (b.equipment_row(p, 'goalie') for p in prows if b.P.get(p, 'aljv') == 4) if r is not None]
    if not rows:
        return ["mask picture: only a goalie has a mask"]
    if not hasattr(b, 'mask_looks'):
        b.mask_looks = {}
    table = b.R.f[equipment.GOALIE_TABLE]
    code = equipment.GOALIE_CODE
    now = table.get(rows[0], code['maskid'])
    wearers = {i for i in range(table.cur_rec)
               if table.get(i, code[equipment.MASK_TYPE]) == 0 and table.get(i, code['maskid']) == now}
    same = [n for n, other in b.mask_looks.items() if other == path]       # the same picture, the same mask
    if same:
        n = same[0]
    elif (table.get(rows[0], code[equipment.MASK_TYPE]) == 0 and 0 < now <= equipment.MASK_LARGEST
          and now not in equipment.MASK_FILES_MISSING and now not in b.mask_looks and wearers <= set(rows)):
        n = now
    else:
        free = equipment.free_mask_ids(table, b.mask_looks)
        if not free:
            return ["mask picture: no free mask is left"]
        n = free[0]
    for row in rows:
        table.set(row, code['maskid'], n)
        table.set(row, code[equipment.MASK_TYPE], 0)
    b.mask_looks[n] = path
    return []


def _team_equipment(b, slot, values):
    """Choices for a whole team (tape, tucks, ...): every skater on it, except for what he has a choice of his own."""
    table = b.R.f[equipment.TABLE]
    ok, problems = equipment.clean({c: v for c, v in values.items() if c in equipment.TEAM_WIDE}, table)
    own = getattr(b, 'equipment_set', {})
    n = 0
    for e in b.entries_on(slot):
        prow = b.prow_of_entry(e)
        if prow is None or b.P.get(prow, 'aljv') == 4:
            continue
        row = b.equipment_row(prow)
        if row is not None:
            equipment.write(table, row, {c: v for c, v in ok.items() if c not in own.get(prow, ())})
            n += 1
    for text in problems:
        b.log.append(['edits', 'edit skipped', b.R.team_name(slot), text, ''])
    b.log.append(['edits', 'team equipment', b.R.team_name(slot), f"{n} skaters", ''])


def _too_few_without(b, team, leaving):
    """A plain sentence when `team` can dress 20 now but not without the entry `leaving`, else None. (A team
    that cannot dress its 20 loses its lines and its captain and alternates, and the save is refused.)"""
    def count(skip):
        n = {'G': 0, 'D': 0, 'F': 0}
        for e in b.entries_on(team):
            if e != skip:
                pos = b.P.get(b.prow_of_entry(e), 'aljv')
                n['G' if pos == 4 else 'D' if pos == 3 else 'F'] += 1
        return n
    now, after = count(None), count(leaving)
    if now['G'] < 2 or now['D'] + now['F'] < 18:
        return None
    name = b.R.team_name(team)
    if after['G'] < 2:
        return f"{name} would have only {after['G']} goalie. A team needs 2 goalies and 18 skaters"
    if after['D'] + after['F'] < 18:
        return f"{name} would have only {after['D'] + after['F']} skaters. A team needs 2 goalies and 18 skaters"
    return None


def _move(b, prow, target, changed):
    """Put a player on team `target` (a slot), or release him to the free agents ('FA')."""
    R, U, P = b.R, b.U, b.P
    pid = P.get(prow, 'zIBw')
    live = b.live_entries()
    clubs = [e for e in live.get(pid, []) if U.get(e, 'BSXd') not in L.NATIONAL and U.get(e, 'BSXd') not in L.MIRROR_OF]
    if target != 'FA' and any(U.get(e, 'BSXd') == int(target) for e in clubs):
        return []
    for e in clubs:
        problem = _too_few_without(b, U.get(e, 'BSXd'), e)
        if problem:
            return [problem]
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
    if pos != 4:        # the record's last wearer's gear goes: a new player starts with Edit Pro's plain choices
        row = b.equipment_row(prow)
        if row is not None:
            table = b.R.f[equipment.TABLE]
            equipment.write(table, row, equipment.clean(equipment.NEW_PLAYER, table)[0])
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
            for e in b.entries_on(team):          # no lines, but the captain and alternates keep their letters
                letter = b.U.get(e, 'lcCm')
                b.clear_lines(e)
                b.U.set(e, 'lcCm', letter)
    if any(t in L.NHL_PRIMARY for t in changed):
        b.sync_mirrors()
