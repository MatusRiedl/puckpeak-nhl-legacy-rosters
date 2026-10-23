"""The Front office tab without a window toolkit. An NHL team shows its organisation's contracts (frontoffice.org) and
what they commit against the cap for five seasons; any other team its own roster's contracts (frontoffice.club): a club,
a prospect pool, a national team, a copy of an NHL team, an event team; the free agents their list. The contract window
sets a contract by hand for anyone: NHL amounts in an NHL organisation, free amounts with a club (owner, 2026-10-22:
contracts.contract_home); a free agent (or a player on no club) signs with a team he then moves to. Apply keeps it in My
edits (edits.json `players[key]["contract"]`, also `["team"]` for a signing: EditorController.contract_edit); Save writes
it into the roster (edits.apply_contracts, after the real deals of an update). With the Calendar's "My season" switch
on, the record and the standings of the player's own Season or Be a GM save show too (app/season.py, read only).

Amounts are real dollars on either money scale (contracts.real); the unpatched game shows them scaled to its own cap.
"""
import threading

from .. import contracts, frontoffice, gamepatch, seasonsave
from .. import layout as L
from ..editor import model
from ..leagues.pools import is_pool
from .calendar import standing_row, standings_view, team_view
from .season import SeasonSource, conference_rows, place_text, record_text, standing

SLICE, CONTRACT = 'office', 'contract'
SORTS = ('name', 'pos', 'age', 'ovr', 'cap', 'years', 'ext')
GROUPS = ('all',) + frontoffice.GROUPS
FIELDS = ('cap', 'years', 'two_way', 'ext_on', 'ext_years', 'ext_cap')
NO_ROSTER = "Pick a roster in Setup first."
STEP = 5000                             # the contract window's steps (the save's unit)
NOTE_GAME = ("Real dollars. On a roster for the unpatched game, the game shows them scaled to its $71.4M cap. The cap "
             "counts the NHL roster.")
NOTE_REAL = "Real dollars, as the patched game shows them. The cap counts the NHL roster."
NOTE_CLUB = ("Real dollars. Clubs outside the NHL have no salary cap. A player with an NHL team's rights signs with that "
             "team (NHL amounts); everyone else signs with his club, from $5k a season.")
SCALED = " On a roster for the unpatched game, the game shows the amounts scaled to its $71.4M cap."
NUDGE = {True: 250_000, False: 25_000}  # the contract window's - / + (NHL organisation, club)
ORDER = {'C': 0, 'LW': 1, 'RW': 2, 'F': 3, 'D': 4, 'G': 5}
TIGHT = 2_000_000                       # cap space below this shows amber


def tone_of(space):
    return 'bad' if space < 0 else 'amber' if space < TIGHT else 'good'


def deal_text(deal):
    """'$12.5M x 3 years, one-way, then 5 x $13M' ('No contract' for none)."""
    if not deal or not deal.get('cap'):
        return "No contract"
    years = deal['years']
    text = f"{contracts.money(deal['cap'])} x {years} {'year' if years == 1 else 'years'}"
    text += ", two-way" if deal.get('two_way') else ", one-way"
    ext = deal.get('ext')
    return text + (f", then {ext[0]} x {contracts.money(ext[1])}" if ext else "")


def _int(value):
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


class OfficeController:
    def __init__(self, host, editor, season=None):
        self.host, self.editor = host, editor
        self.source = season or SeasonSource(editor)
        self.lock = threading.RLock()
        self.team = None                # the team followed
        self.shown = False
        self._sort, self._dir, self._group = 'cap', -1, 'all'
        self.contract = None            # the contract window: {'key', 'org', 'sign', 'current', 'draft', 'on_nhl'}
        self._index = (None, None)      # (Snapshot, (frontoffice.Index, money scale))
        self._numbers = (None, None, {})    # (frontoffice.Index, the contracts set by hand, rail_numbers)
        follow = getattr(editor, 'follow_with', None)
        if follow is not None:
            follow('office', self)

    def changed(self):
        self.host.changed(SLICE)
        self.host.changed(CONTRACT)

    def _say(self, text, tone='info'):
        say = getattr(self.editor, 'set_status', None)
        if say is not None:
            say(text, tone)

    # --- the followed team --------------------------------------------------------------------------------
    def follow(self, team):
        with self.lock:
            if team != self.team:
                self.contract = None
            self.team, self.shown = team, True
        self.source.load(fresh=True)
        self.changed()

    def hide(self):
        with self.lock:
            self.shown = False

    def roster_changed(self):
        with self.lock:
            self._index = (None, None)
        self.changed()

    # --- the calls ------------------------------------------------------------------------------------------
    def sort(self, key):
        """Sort the lists by column `key`; the same column again turns the order round."""
        with self.lock:
            if key not in SORTS:
                return
            if key == self._sort:
                self._dir = -self._dir
            else:
                self._sort, self._dir = key, 1 if key in ('name', 'pos') else -1
        self.changed()

    def group(self, group):
        with self.lock:
            if group in GROUPS:
                self._group = group
        self.changed()

    def contract_open(self, key):
        """The contract window for player `key` (anyone on a team or on the free-agent list)."""
        with self.lock:
            index, _scale = self._indexed()
            prow = index.by_who(key) if index is not None else None
            if prow is None:
                self._say("Pick a player on a team or on the free-agent list.", 'warn')
                return
            person = self._person(prow)
            home = index.home(prow)
            current = person['deal']
            self.contract = {'key': key, 'prow': prow, 'home': home, 'join': None, 'sign': not current.get('cap'),
                             'current': current, 'touched': False, 'draft': self._draft(person, home)}
        self.changed()

    def _draft(self, person, home):
        """The window's first values: his deal, else a fitting first one (NHL: entry level or the lowest salary; a
        club: contracts.starter_pay)."""
        current = person['deal']
        if current.get('cap'):
            ext = current.get('ext')
            return {'cap': current['cap'], 'years': current['years'], 'two_way': bool(current.get('two_way')),
                    'ext_on': bool(ext), 'ext_years': ext[0] if ext else 2,
                    'ext_cap': ext[1] if ext else round(current['cap'] * 1.1 / STEP) * STEP}
        age = person['age']
        if home is None or home[1]:
            young = age is not None and age < 22
            cap = contracts.ENTRY_LEVEL if young else gamepatch.cap_of(3, 0)
            return {'cap': cap, 'years': 3 if young else 1, 'two_way': True, 'ext_on': False, 'ext_years': 2,
                    'ext_cap': max(gamepatch.cap_of(3, 3 if young else 1), cap)}
        cap = contracts.starter_pay(home[0], person['ovr'] or 0)
        return {'cap': cap, 'years': 1 if age is not None and age >= contracts.STARTER_AGE else 2, 'two_way': False,
                'ext_on': False, 'ext_years': 2, 'ext_cap': cap}

    def _home(self, c):
        """Who the window's contract is with: his own (contracts.contract_home), else the team he signs with."""
        if c['home'] is not None:
            return c['home']
        index, _scale = self._indexed()
        if c['join'] is None or index is None:
            return None
        return index.home(c['prow'], [c['join']])

    def _joinable(self):
        """The teams a player can sign with: every club with room (not a pool, a national team or a copy)."""
        index, _scale = self._indexed()
        snap = self._snap()
        if index is None or snap is None:
            return []
        return [t for t in sorted(index.clubs) if snap.team_names.get(t, '').strip()
                and len(index.on_team.get(t, [])) < L.MAX_PER_TEAM]

    def contract_change(self, field, value):
        with self.lock:
            c = self.contract
            if c is None or field not in FIELDS + ('join',):
                return
            if field == 'join':
                team = _int(value) if value not in (None, '') else None
                if c['home'] is not None or (team is not None and team not in self._joinable()):
                    return
                c['join'] = team
                if not c['touched'] and c['sign']:
                    c['draft'] = self._draft(self._person(c['prow']), self._home(c))
            elif field in ('two_way', 'ext_on'):
                c['draft'][field] = bool(value)
                c['touched'] = True
            else:
                n = _int(value)
                if n is None:
                    return
                if field in ('cap', 'ext_cap'):
                    n = max(0, min(round(n / STEP) * STEP, 99_995_000))
                else:
                    n = max(1, min(n, 15))
                c['draft'][field] = n
                c['touched'] = True
        self.host.changed(CONTRACT)

    def contract_close(self):
        with self.lock:
            self.contract = None
        self.host.changed(CONTRACT)

    def contract_apply(self):
        """Keep the contract in My edits (Save writes it), unless it cannot go into the roster."""
        with self.lock:
            c = self.contract
            if c is None:
                return
            home = self._home(c)
            if home is None:
                self._say("Pick the team he signs with.", 'warn')
                self.host.changed(CONTRACT)
                return
            deal = self._deal(c['draft'], home[1])
            bad = contracts.edit_problems(deal, nhl=home[1])
            if bad:
                self._say(f"This contract cannot go into the roster: {bad[0]}.", 'warn')
                self.host.changed(CONTRACT)
                return
            key, join = c['key'], c['join']
            patch_roster = self._scale() == contracts.REAL
        keep = getattr(self.editor, 'contract_edit', None)
        if keep is None:
            self._say("Contracts cannot be kept here.", 'warn')
            return
        if join is None:
            keep(key, deal)
        else:
            keep(key, deal, team=join)
        with self.lock:
            self.contract = None
        self._say("Applied. On the Update tab, update this roster with My edits on to write it." if patch_roster else
                  "Applied. Save writes it into the roster.", 'good')
        self.changed()

    def contract_reset(self):
        """Take back the contract set by hand for the player in the window (the roster's own comes back)."""
        with self.lock:
            c = self.contract
            if c is None:
                return
            key = c['key']
        keep = getattr(self.editor, 'contract_edit', None)
        if keep is not None:
            keep(key, None)
        with self.lock:
            self.contract = None
        self._say("Taken back. The roster's own contract stays.", 'info')
        self.changed()

    # --- reading the roster -----------------------------------------------------------------------------------
    def _snap(self):
        return getattr(self.editor, 'snap', None)

    def _indexed(self):
        """(frontoffice.Index, money scale) of the shown roster, or (None, None)."""
        snap = self._snap()
        if snap is None:
            return None, None
        if self._index[0] is not snap:
            try:
                from .. import stock
                R = snap.R
                base = 1900 if stock.is_stock(R) and not stock.prepared(R) else 1910   # as editor/model.Snapshot
                value = (frontoffice.Index(R, base), contracts.scale_of(gamepatch.is_patch_roster(R)))
            except Exception:
                value = (None, None)
            self._index = (snap, value)
        return self._index[1]

    def _scale(self):
        return self._indexed()[1]

    def _org_of(self, team):
        index, _scale = self._indexed()
        if index is None or not isinstance(team, int):
            return None
        return index.org_of(team)

    def _edited(self):
        """{person key: deal} of every contract set by hand (My edits)."""
        out = {}
        for k, e in dict(getattr(self.editor, 'edits', None) or {}).items():
            if isinstance(e, dict) and e.get('contract'):
                out[k] = dict(e['contract'])
        return out

    def _org(self, org):
        """frontoffice.org of `org` with the contracts set by hand standing in, and each player's 'age' and 'ovr'."""
        index, scale = self._indexed()
        out = frontoffice.org(index, org, scale, override=self._edited())
        for g in frontoffice.GROUPS:
            for p in out[_list(g)]:
                self._aged(p)
        return out

    def _aged(self, p):
        """`p` (a frontoffice player) with his 'age' and 'ovr' from the shown roster."""
        snap = self._snap()
        year = getattr(snap, 'season_year', None) or 2026
        q = snap.players.get(p['pid']) if snap is not None else None
        p['age'] = q.age(year) if q is not None else None
        p['ovr'] = q.ovr if q is not None else None
        return p

    def _person(self, prow):
        """Player row `prow` as frontoffice.Index.player, with the contract set by hand standing in, 'age' and 'ovr'."""
        index, scale = self._indexed()
        p = index.player(prow, index.club_of(prow), scale)
        edited = self._edited()
        if p['who'] in edited:
            p['deal'] = edited[p['who']]
        return self._aged(p)

    def _deal(self, draft, nhl=True):
        """The window's values as a deal; two-way only in an NHL organisation (a club's deal has no farm)."""
        ext = [int(draft['ext_years']), int(draft['ext_cap']), 0] if draft.get('ext_on') else None
        return {'cap': int(draft['cap']), 'years': int(draft['years']),
                'two_way': 1 if draft.get('two_way') and nhl else 0, 'ext': ext}

    # --- what is shown --------------------------------------------------------------------------------------
    def _row(self, p, where, edited, rights=False):
        """A list row; `rights`: a player without a deal shows "Rights" (his NHL team's), else "None"."""
        deal = p['deal']
        ext = deal.get('ext')
        kind = ("Two-way" if deal.get('two_way') else "One-way") if deal.get('cap') else "Rights" if rights else "None"
        return {'key': p['who'], 'name': p['name'], 'pos': p['pos'], 'age': p['age'], 'ovr': p['ovr'],
                'cap': deal.get('cap') or 0, 'cap_text': contracts.money(deal['cap']) if deal.get('cap') else "No contract",
                'years': deal.get('years') or 0, 'two_way': bool(deal.get('two_way')), 'type': kind,
                'ext': f"{ext[0]} x {contracts.money(ext[1])}" if ext else '', 'ext_cap': ext[1] if ext else 0,
                'ext_sample': False, 'where': where, 'edited': p['who'] in edited, 'rights': not deal.get('cap')}

    def _code(self, team):
        view = team_view(self.editor, team)
        return view['code'] if view else str(team)

    def _sorted(self, rows):
        key, way = self._sort, self._dir

        def value(r):
            if key == 'name':
                return r['name']
            if key == 'pos':
                return ORDER.get(r['pos'], 6)
            if key == 'ext':
                return r['ext_cap']
            return r[key] if r[key] is not None else -1
        rows.sort(key=lambda r: r['name'])
        rows.sort(key=value, reverse=way < 0)
        return rows

    def snapshot(self):
        with self.lock:
            snap = self._snap()
            team = self.team
            if snap is None or team is None:
                return {'team': None, 'why': NO_ROSTER}
            view = team_view(self.editor, team)
            index, _scale = self._indexed()
            if index is None:
                return {'team': view, 'why': "This roster's contracts could not be read."}
            if not isinstance(team, int):
                return self._free_view()
            if team in L.NHL_PRIMARY:
                return self._org_view(team)
            return self._club_view(team)

    def _org_view(self, org):
        """An NHL organisation: its NHL roster, its farm club, its prospects and rights, the cap for five seasons."""
        snap = self._snap()
        index, scale = self._indexed()
        o = self._org(org)
        edited = self._edited()
        name = snap.team_name(org)
        farm_name = snap.team_name(o['farm']) if o['farm'] is not None else None
        nhl = [self._row(p, ' ', edited, rights=True) for p in o['nhl']]
        farm = []
        for p in o['farm_rows']:
            rights = index.R.P.get(p['prow'], gamepatch.RIGHTS)
            where = (farm_name or '') if rights == org + 1 else f"{self._code(rights - 1)} rights" if rights else "AHL deal"
            farm.append(self._row(p, where, edited, rights=rights == org + 1))
        prospects = [self._row(p, snap.team_name(p['where']) if p['where'] is not None else
                               "Free agents" if p['prow'] in index.free else '', edited, rights=True)
                     for p in o['prospects']]
        prospect_note = (f"The game keeps no prospect rights for {name}, so none are listed." if o['no_rights'] else
                         None if prospects else "No prospects or rights in this roster.")
        groups = [
            {'key': 'nhl', 'title': f"{name}: NHL roster", 'rows': self._sorted(nhl),
             'note': None if nhl else "No players on the NHL roster."},
            {'key': 'farm', 'title': f"Farm: {farm_name}" if farm_name else "Farm club", 'rows': self._sorted(farm),
             'note': None if farm else "No players on the farm club." if farm_name else
             "This organisation has no farm club in this roster."},
            {'key': 'prospects', 'title': "Prospects and rights", 'rows': self._sorted(prospects),
             'note': prospect_note},
        ]
        seasons = []
        for y in o['seasons']:
            seasons.append({'label': y['label'], 'committed': contracts.money(y['committed']),
                            'cap': contracts.money(y['cap']), 'space': contracts.money(y['space']),
                            'share': min(1.0, y['committed'] / y['cap']) if y['cap'] else 0.0,
                            'tone': tone_of(y['space']), 'signed': y['signed'], 'space_value': y['space']})
        now = o['seasons'][0]
        tiles = [
            {'label': f"Payroll {now['label']}", 'value': contracts.money(now['committed'])},
            {'label': "Salary cap", 'value': contracts.money(now['cap'])},
            {'label': "Cap space", 'value': contracts.money(now['space']),
             'tone': 'bad' if now['space'] < 0 else 'good'},
            {'label': "Lowest payroll", 'value': contracts.money(now['floor']), 'minor': True},
            {'label': "NHL · farm · prospects", 'value': f"{len(nhl)} · {len(farm)} · {len(prospects)}"},
        ]
        record, standings = self._season(org)
        if record is not None:
            tiles.append({'label': f"My season: {record['place_text']}",
                          'value': f"{record['text']} · {record['pts']} pts", 'tone': 'gold', 'season': True})
        return {
            'kind': 'org', 'team': team_view(self.editor, org), 'about': None, 'link': None,
            'tiles': tiles, 'seasons': seasons,
            'groups': groups if self._group == 'all' else [g for g in groups if g['key'] == self._group],
            'group': self._group, 'counts': {'nhl': len(nhl), 'farm': len(farm), 'prospects': len(prospects)},
            'sort': {'sort': self._sort, 'dir': self._dir, 'group': self._group}, 'edited': len(edited),
            'note': NOTE_REAL if scale == contracts.REAL else NOTE_GAME,
            'record': record, 'standings': standings,
        }

    def _kind(self, team):
        index, _scale = self._indexed()
        if team in index.clubs:
            return 'club'
        if team in L.NATIONAL:
            return 'national'
        if team in L.MIRROR_OF:
            return 'copy'
        if team in L.CONTRACT_CLUB and is_pool(index.R, team):
            return 'pool'
        return 'event'

    def _club_view(self, team):
        """Any team but an NHL one: its own roster with each player's deal (a club pays its own; a player with an NHL
        team's rights is on that team's deal), what the club's deals pay for five seasons."""
        snap = self._snap()
        index, scale = self._indexed()
        edited = self._edited()
        kind = self._kind(team)
        name = snap.team_name(team)
        found = frontoffice.club(index, team, scale, override=edited)
        rows, own, nhl_deals, signed = [], 0, 0, 0
        for p in found['rows']:
            self._aged(p)
            home, rights = p['home'], p['rights']
            if kind in ('club', 'pool'):
                where = (f"{self._code(rights)} rights" if rights is not None else
                         f"{self._code(home[0])} deal" if home is not None and home[1] else
                         "Club deal" if p['deal'].get('cap') else '')
            else:
                where = (snap.team_name(p['where']) if p['where'] is not None else
                         "Free agents" if p['prow'] in index.free else "No club")
            rows.append(self._row(p, where, edited, rights=rights is not None))
            if p['deal'].get('cap'):
                signed += 1
                if home is not None and home[1]:
                    nhl_deals += 1
                elif home == (team, False):
                    own += 1
        parent = index.parent.get(team)
        link = None
        if kind == 'club' and parent is not None:
            link = {'team': team_view(self.editor, parent), 'text': f"Farm club of {snap.team_name(parent)}",
                    'button': f"{snap.team_name(parent)}'s front office"}
        elif kind == 'copy':
            link = {'team': team_view(self.editor, L.MIRROR_OF[team]),
                    'text': f"A copy of {snap.team_name(L.MIRROR_OF[team])}",
                    'button': f"{snap.team_name(L.MIRROR_OF[team])}'s front office"}
        about = {
            'club': None,
            'pool': f"{name} is a prospect pool, not a club: a player with an NHL team's rights signs with that team, "
                    f"anyone else with a club (he moves there).",
            'national': f"{name} is a national team: each player's contract is with his club.",
            'copy': f"The game uses this copy in some modes: its players' contracts are "
                    f"{snap.team_name(L.MIRROR_OF.get(team, team))}'s.",
            'event': f"{name} plays in events only: each player's contract is with his club.",
        }[kind]
        tiles = [{'label': "Players", 'value': str(len(rows))},
                 {'label': "Under contract", 'value': str(signed), 'tone': 'good' if signed == len(rows) else ''}]
        seasons = []
        if kind == 'club':
            now = found['seasons'][0]
            tiles.insert(0, {'label': f"Club payroll {now['label']}", 'value': contracts.money(now['committed'])})
            tiles.append({'label': "Club deals · NHL deals", 'value': f"{own} · {nhl_deals}"})
            top = max(y['committed'] for y in found['seasons']) or 1
            seasons = [{'label': y['label'], 'committed': contracts.money(y['committed']), 'cap': None,
                        'share': y['committed'] / top, 'tone': 'good', 'signed': y['signed'],
                        'signed_text': f"{y['signed']} club {'deal' if y['signed'] == 1 else 'deals'}"}
                       for y in found['seasons']]
        title = {'club': f"{name}: roster", 'pool': f"{name}: prospect pool", 'national': f"{name}: national team",
                 'copy': f"{name}: copy", 'event': f"{name}: event team"}[kind]
        return {
            'kind': kind, 'team': team_view(self.editor, team), 'about': about, 'link': link,
            'tiles': tiles, 'seasons': seasons,
            'groups': [{'key': 'club', 'title': title, 'rows': self._sorted(rows),
                        'note': None if rows else "No players on this team."}],
            'group': None, 'counts': None,
            'sort': {'sort': self._sort, 'dir': self._dir, 'group': None}, 'edited': len(edited),
            'note': NOTE_CLUB + ('' if scale == contracts.REAL else SCALED),
            'record': None, 'standings': None,
        }

    def _free_view(self):
        """The free agents: no contract; a click signs one with a team."""
        index, scale = self._indexed()
        edited = self._edited()
        rows = []
        for prow in sorted(index.free):
            if index.club_of(prow) is not None:
                continue
            p = self._person(prow)
            rights = index.R.P.get(prow, gamepatch.RIGHTS)
            where = f"{self._code(rights - 1)} rights" if rights else ''
            rows.append(self._row(p, where, edited, rights=bool(rights)))
        return {
            'kind': 'free', 'team': team_view(self.editor, model.FREE_AGENTS), 'link': None,
            'about': "Free agents have no contract. Click one to sign him: he moves to the team you pick with the "
                     "contract you set.",
            'tiles': [{'label': "Free agents", 'value': str(len(rows))},
                      {'label': "With an NHL team's rights", 'value': str(sum(1 for r in rows if r['where']))}],
            'seasons': [],
            'groups': [{'key': 'free', 'title': "Free agents", 'rows': self._sorted(rows),
                        'note': None if rows else "No free agents in this roster."}],
            'group': None, 'counts': None,
            'sort': {'sort': self._sort, 'dir': self._dir, 'group': None}, 'edited': len(edited),
            'note': NOTE_CLUB + ('' if scale == contracts.REAL else SCALED),
            'record': None, 'standings': None,
        }

    def _season(self, org):
        """(record, standings) of NHL team `org` in the save shown while the Calendar's switch is on, else (None, None)."""
        season = self.source.shown()
        if season is None:
            return None, None
        try:
            group, row = standing(season, org, seasonsave.NHL)
            if row is None:
                return None, None
            view = lambda t: team_view(self.editor, t)
            record = {'text': record_text(row), 'pts': row['pts'], 'gp': row['gp'], 'place': row['place'],
                      'division': group['division'], 'place_text': f"{place_text(row['place'])} in {group['division']}"}
            standings = standings_view(group, org, view)
            standings['conference_rows'] = [dict(standing_row(r, org, view), division=r['division'], place=n + 1)
                                            for n, r in enumerate(conference_rows(season, group['conference']))]
            standings['label'] = self.source.label()
            return record, standings
        except Exception:
            return None, None

    def contract_snapshot(self):
        with self.lock:
            c = self.contract
            if c is None:
                return None
            snap = self._snap()
            index, scale = self._indexed()
            if snap is None or index is None:
                return None
            person = self._person(c['prow'])
            home = self._home(c)
            nhl = home[1] if home is not None else True
            d = c['draft']
            deal = self._deal(d, nhl)
            problems = [{'tone': 'bad', 'text': f"Not possible: {text}."}
                        for text in contracts.edit_problems(deal, nhl=nhl)]
            if home is None:
                problems.insert(0, {'tone': 'bad', 'text': "Pick the team he signs with."})
                preview = None
            elif nhl:
                o = self._org(home[0])
                name = snap.team_name(home[0])
                on_nhl = any(p['who'] == c['key'] for p in o['nhl']) or c['join'] == home[0]
                before = o['seasons'][0]['space']
                nhl_now = o['nhl'] + ([] if any(p['who'] == c['key'] for p in o['nhl']) else [person])
                after = frontoffice.seasons(nhl_now, swap=(c['key'], deal))[0]['space'] if on_nhl else before
                preview = {'label': f"Cap space of {name} this season", 'before': contracts.money(before),
                           'after': contracts.money(after), 'tone': tone_of(after),
                           'note': None if on_nhl else
                           "He is not on the NHL roster, so his cap hit counts only when he is called up."}
                if after < 0:
                    problems.append({'tone': 'amber', 'text': f"This puts {name} {contracts.money(-after)} over the "
                                     f"{frontoffice.season_label(0)} cap. That is allowed; the game asks you to fix it."})
            else:
                name = snap.team_name(home[0])
                found = frontoffice.club(index, home[0], scale, override=self._edited())
                own = [p for p in found['rows'] if p['home'] == home and p['who'] != c['key']]
                before = sum(contracts.cap_in(p['deal'], 0) for p in found['rows'] if p['home'] == home)
                after = sum(contracts.cap_in(p['deal'], 0) for p in own) + contracts.cap_in(deal, 0)
                preview = {'label': f"Payroll of {name} this season", 'before': contracts.money(before),
                           'after': contracts.money(after), 'tone': 'good', 'note': None}
            if scale != contracts.REAL:
                problems.append({'tone': 'info', 'text': "This roster is for the unpatched game: the game shows the "
                                 "contract scaled to its $71.4M cap."})
            count = min(max(d['years'] + (d['ext_years'] if d['ext_on'] else 0), frontoffice.SEASONS), 8)
            years = [{'label': frontoffice.season_label(k), 'cap': contracts.money(contracts.cap_in(deal, k))
                      if contracts.cap_in(deal, k) else '', 'on': contracts.cap_in(deal, k) > 0, 'ext': k >= d['years']}
                     for k in range(count)]
            if c['home'] is not None:
                current = (deal_text(c['current']) if not c['sign'] else
                           "No contract: his rights belong to the team." if index.R.P.get(c['prow'], gamepatch.RIGHTS)
                           else "No contract yet.")
            else:
                current = "Free agent: no contract." if c['prow'] in index.free else "On no club: no contract."
            join = None
            if c['home'] is None:
                join = {'value': c['join'], 'options': [{'value': t, 'label': f"{snap.team_league.get(t, '')} · "
                                                                              f"{snap.team_name(t)}"}
                                                        for t in self._joinable()]}
            low = gamepatch.cap_of(3, 0) if nhl else contracts.FREE_LOW
            return {
                'key': c['key'], 'name': person['name'], 'pos': person['pos'], 'age': person['age'],
                'team': team_view(self.editor, home[0]) if home is not None else None, 'sign': c['sign'],
                'nhl': nhl, 'join': join, 'current': current,
                'draft': dict(d, two_way=bool(d['two_way']) and nhl), 'years': years, 'preview': preview,
                'problems': problems, 'can_apply': not any(p['tone'] == 'bad' for p in problems),
                'edited': c['key'] in self._edited(),
                'limits': {'min': low, 'max': contracts.MAXIMUM, 'step': STEP, 'nudge': NUDGE[nhl],
                           'ext_min': gamepatch.cap_of(3, d['years']) if nhl else low, 'years': contracts.EDIT_YEARS},
            }

    def rail_numbers(self):
        """{slot: {'text', 'tone', 'tip'}}: each NHL organisation's cap space this season, each club's payroll."""
        with self.lock:
            index, scale = self._indexed()
            if index is None:
                return {}
            edited = self._edited()
            key = tuple(sorted((k, repr(v)) for k, v in edited.items()))
            if self._numbers[0] is index and self._numbers[1] == key:
                return self._numbers[2]
            out = {}
            for team, space in frontoffice.cap_space(index, scale, edited).items():
                out[team] = {'text': f"{'-' if space < 0 else ''}${abs(space) / 1e6:.1f}M",
                             'tone': 'bad' if space < 0 else 'amber' if space < TIGHT else '', 'tip': 'cap space'}
            for team, paid in frontoffice.club_payrolls(index, scale, edited).items():
                if team not in out:
                    out[team] = {'text': f"${paid / 1e6:.1f}M" if paid >= 50_000 else contracts.money(paid),
                                 'tone': '', 'tip': 'club payroll'}
            self._numbers = (index, key, out)
            return out


def _list(group):
    """The key of frontoffice.org's list of a group."""
    return {'nhl': 'nhl', 'farm': 'farm_rows', 'prospects': 'prospects'}[group]
