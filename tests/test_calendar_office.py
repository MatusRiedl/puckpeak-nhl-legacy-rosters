"""The Calendar and Front office tabs (app/calendar.py, app/office.py) without a window: the roster's calendar on a month
page, an organisation's contracts and cap, the contract window, and a made-up Season / Be a GM save (never a real one)."""
import copy
import datetime
import os
import time

import pytest

from legacy_roster import contracts, frontoffice, gamepatch, pipeline, schedule, seasonsave
from legacy_roster import layout as L
from legacy_roster.app.calendar import ALL_STAR, FARM_NOTE, NORWAY_NOTE, OWN_NOTE, SEASON_NOTE, CalendarController
from legacy_roster.app.office import OfficeController
from legacy_roster.app.season import NO_SAVE, SeasonSource, long_date
from legacy_roster.editor import model
from legacy_roster.roster import Roster
from tests.test_seasonsave import league, save_bytes, write_save

TITLE = 'BLES02153'
IN_SEASON = datetime.date(2026, 10, 20)


class Host:
    def __init__(self):
        self.dirty = set()

    def changed(self, name):
        self.dirty.add(name)


class Slot:
    title_id = TITLE


class Editor:
    """What the two controllers use of the Roster editor (EditorController): the shown roster, My edits, the status."""

    def __init__(self, data, savedata=None, farm_ahl=False):
        self.snap = model.Snapshot(data, season_year=2026, farm_ahl=farm_ahl)
        self.source = (savedata, 'BLES021530202', 0) if savedata else None
        self.slot = Slot()
        self.edits, self.status = {}, None

    def set_status(self, text, tone='info'):
        self.status = (text, tone)

    def contract_of(self, key):
        deal = (self.edits.get(key) or {}).get('contract')
        return dict(deal) if deal else None

    def contract_edit(self, key, deal, team=None):
        if deal is None:
            self.edits.pop(key, None)
        else:
            self.edits[key] = {'label': key, 'contract': dict(deal), **({'team': team} if team is not None else {})}
        return True


def tabs(editor):
    host = Host()
    source = SeasonSource(editor)
    cal, office = CalendarController(host, editor, source), OfficeController(host, editor, source)
    cal.clock = lambda: IN_SEASON
    return cal, office, host


@pytest.fixture(scope='module')
def patch_view(base_bytes, data, pack):
    """A roster made for the game patch (the real 2026-27 calendar, the AHL of 32), as the Roster editor shows it."""
    patch = copy.copy(data)
    patch.schedule, patch.leagues, patch.calendar = pack['schedule'], {'ahl': pack['leagues']['ahl']}, schedule.ALL_PATCH
    res = pipeline.build(base_bytes, patch, list(pipeline.CORE_STEPS) + [pipeline.SCHEDULE, 'ahl'], game_patch=True)
    out, problems, _ = pipeline.patch_roster(res, base_bytes, pack, patch.season_year)
    assert problems == [] and gamepatch.is_patch_roster(Roster(out))
    view = model.apply_edits(out, {}, {}, 2026)
    assert view.problems == []
    return view.data


def made_up_save(savedata, folder='BLES021530105', states=None, settled=True, age=60):
    """A made-up save (tests/test_seasonsave.py) in `savedata`: a Be a GM, or a Season in a 10NN folder."""
    tables, _ = league(states)
    magic = b'PS3SeasonFile' if folder[9:11] == '10' else b'PS3DynastyFile'
    when = time.time() - age if settled else None
    return write_save(str(savedata), folder, save_bytes(tables, magic), 'BE A GM6', when=when)


def find(snap, name):
    return next(p for p in snap.by_who.values() if p.name == name)


# --- the calendar ---------------------------------------------------------------------------------------------------
def test_every_team_s_games_are_counted_as_the_roster_has_them(patch_view):
    cal, _office, _host = tabs(Editor(patch_view, farm_ahl=True))
    R = Roster(patch_view)
    games, stars = schedule.split_all_star(schedule.read(R))
    assert len(stars) == 1
    numbers = cal.rail_numbers()
    for team in sorted(L.NHL_PRIMARY):
        assert numbers[team] == {'text': str(sum(team in g[2:] for g in games)), 'tip': 'games'}
        assert numbers[team]['text'] == str(schedule.PATCH_PER_TEAM)
    for farm in gamepatch.FARM_SLOTS:
        assert numbers[farm]['text'] == '72'
    cal.follow(13)
    s = cal.snapshot()
    assert s['summary']['gp'] == 84 and s['summary']['home'] == s['summary']['away'] == 42
    assert s['league'] == 'NHL' and s['league_note'] is None and s['season']['available'] is False
    assert sum(len(m['games']) for m in s['months']) == 84


def test_the_month_page_runs_monday_to_sunday_with_the_team_s_games(patch_view):
    cal, _office, _host = tabs(Editor(patch_view, farm_ahl=True))
    cal.follow(13)
    s = cal.snapshot()
    assert s['title'] == 'October 2026' and s['month'] == '2026-10'
    first = s['weeks'][0][0]
    assert first['date'] == '2026-09-28' and first['out'] and len(s['weeks'][0]) == 7
    october = [g for m in s['months'] if m['ym'] == '2026-10' for g in m['games']]
    cells = [d for w in s['weeks'] for d in w if d['mine'] and not d['out']]
    assert len(cells) == len(october) > 0
    assert any(d['today'] for w in s['weeks'] for d in w if d['date'] == IN_SEASON.isoformat())
    cal.mode('league')
    s = cal.snapshot()
    assert s['mode'] == 'league' and s['count_note'] == "1,344 games, 84 per team."
    cal.month(-1)
    cal.month(-1)
    s = cal.snapshot()
    assert not s['can_prev'] and s['can_next'] and s['month'] <= '2026-10'


def test_the_all_star_game_has_its_day_and_counts_for_nobody(patch_view):
    cal, _office, _host = tabs(Editor(patch_view, farm_ahl=True))
    _games, stars = schedule.split_all_star(schedule.read(Roster(patch_view)))
    (date, _h, _a), = schedule.dated(stars, 2026)
    cal.follow(0)
    cal.day(date.isoformat())
    s = cal.snapshot()
    cell = next(d for w in s['weeks'] for d in w if d['date'] == date.isoformat())
    assert cell['allstar'] and cell['mine'] is None and cell['sel']
    assert [g['label'] for g in s['day']['games']] == [ALL_STAR] and not s['day']['games'][0]['mine']
    cal.day(date.isoformat())                   # the same day again closes it
    assert cal.snapshot()['day'] is None


def test_the_ahl_calendar_is_the_patch_s_32_or_the_roster_s_30(patch_view, built):
    cal, _office, _host = tabs(Editor(patch_view, farm_ahl=True))
    cal.follow(234)
    s = cal.snapshot()
    assert s['league'] == 'AHL' and s['summary']['gp'] == 72 and s['league_note'] == FARM_NOTE
    cal, _office, _host = tabs(Editor(built.data))
    cal.follow(32)
    s = cal.snapshot()
    games = schedule.read_league(Roster(built.data), 'ahl')
    assert s['league'] == 'AHL' and s['summary']['gp'] == sum(32 in g[2:] for g in games) > 0
    assert cal.rail_numbers()[32]['text'] == str(s['summary']['gp'])
    cal.follow(234)                                 # a custom team on the unpatched game
    assert 'no league with a calendar' in cal.snapshot()['why']


def test_every_league_shows_its_calendar_and_says_whose_it_is(built, pack):
    ed = Editor(built.data)
    ed.update = type('Update', (), {'pack': pack})()
    cal, _office, _host = tabs(ed)
    cal.follow(13)
    s = cal.snapshot()
    assert "game's own calendar" in s['league_note'] and s['month'].startswith('2015')
    cal.follow(30)
    assert 'plays no games' in cal.snapshot()['why']
    cal.follow(min(L.DEL))                          # the game's own DEL season: shown, and said so
    s = cal.snapshot()
    assert s['league'] == 'DEL' and 'why' not in s
    assert s['league_note'] == OWN_NOTE.format(league='DEL') and s['summary']['gp'] > 0
    # this season's SHL in the roster: the real games, and which mode plays them
    R = Roster(built.data)
    schedule.apply_league(R, 'shl', pack['schedules']['shl'])
    ed = Editor(R.f.build())
    ed.update = type('Update', (), {'pack': pack})()
    cal, _office, _host = tabs(ed)
    cal.follow(min(L.SHL))
    s = cal.snapshot()
    real = sorted(g for g in pack['schedules']['shl'] if min(L.SHL) in g[1:])
    assert s['league'] == 'SHL' and s['league_note'] == SEASON_NOTE.format(league='SHL') and s['summary']['gp'] == 52
    first = [g for m in s['months'] for g in m['games']][0]
    assert first['date'] == real[0][0]
    # Norway: no table, the data pack's real season with the clubs the game has no slot for
    cal.follow(min(L.NORWAY))
    s = cal.snapshot()
    assert s['league'] == 'Norway' and s['league_note'] == NORWAY_NOTE and s['summary']['gp'] == 40
    named = next(g for g in pack['schedules']['norway'] if min(L.NORWAY) in g[1:] and
                 any(isinstance(c, str) for c in g[1:]))
    cal.day(named[0])
    other = next(c for c in named[1:] if isinstance(c, str))
    assert other in [x[side]['name'] for x in cal.snapshot()['day']['games'] for side in ('home', 'away')]
    assert cal.rail_numbers()[min(L.NORWAY)]['text'] == '40'
    cal.follow(None)
    assert cal.snapshot() == {'team': None, 'why': "Pick a roster in Setup first."}


# --- my season ------------------------------------------------------------------------------------------------------
def test_my_season_shows_the_save_s_results_record_and_standings(patch_view, tmp_path):
    path = made_up_save(tmp_path)
    before = {n: open(os.path.join(path, n), 'rb').read() for n in os.listdir(path)}
    ed = Editor(patch_view, str(tmp_path), farm_ahl=True)
    cal, office, host = tabs(ed)
    cal.follow(30)
    s = cal.snapshot()
    assert s['season']['available'] and not s['season']['on'] and s['season']['label'].startswith('Be a GM: BE A GM6')
    cal.season(True)
    assert {'calendar', 'office'} <= host.dirty
    s = cal.snapshot()
    assert s['season']['on'] and long_date(datetime.date(2026, 10, 13)) in s['season']['note']
    assert s['month'] == '2026-10'
    rows = {g['date']: g for m in s['months'] for g in m['games']}
    assert rows['2026-10-01']['result'] == {'text': 'L 2-3', 'tone': 'bad'}       # at Anaheim, 3-2
    assert rows['2026-10-04']['result'] == {'text': 'W 5-0', 'tone': 'good'}      # at home against Boston
    assert rows['2027-04-20']['playoffs'] and rows['2027-04-20']['result']['text'] == 'L 1-2 OT'
    assert '2027-04-22' not in rows                     # a playoff game the series did not need
    today = next(d for w in s['weeks'] for d in w if d['today'])
    assert today['date'] == '2026-10-13'
    season = seasonsave.read(path, now=time.time())
    want = season.record(30)
    assert s['record']['text'] == f"{want.wins}-{want.l}-{want.ot_losses}"
    assert s['record']['pts'] == want.points and s['record']['place_text'].endswith('in Pacific')
    assert [r['mine'] for r in s['standings']['rows']].count(True) == 1
    assert s['summary']['next'] and s['summary']['next'].endswith(('BOS', 'ANA', 'VGK'))

    office.follow(30)
    o = office.snapshot()
    tile = next(t for t in o['tiles'] if t.get('season'))
    assert tile['label'].startswith('My season: ') and 'pts' in tile['value']
    assert o['record'] == s['record'] and o['standings']['conference'] == 'Western'
    assert {r['code'] for r in o['standings']['conference_rows']} == {'ANA', 'SEA', 'VGK'}

    cal.follow(234)                                     # the Be a GM's farm club plays the save's farm league
    farm = cal.snapshot()
    assert farm['league'] == 'AHL' and farm['summary']['gp'] == 10 and farm['record'] is not None
    first = next(g for m in farm['months'] for g in m['games'])
    assert first['result']['text'] == 'L 1-2'           # 2-1 at Utica

    cal.follow(0)                                       # the save lists its preseason last: shown in date order
    dates = [g['date'] for m in cal.snapshot()['months'] for g in m['games']]
    assert dates == sorted(dates) and dates[0] == '2026-09-25'

    cal.season(False)
    assert cal.snapshot()['record'] is None and not any(t.get('season') for t in office.snapshot()['tiles'])
    assert {n: open(os.path.join(path, n), 'rb').read() for n in os.listdir(path)} == before     # nothing written


def test_a_save_of_the_unpatched_game_is_shown_in_this_season(built, tmp_path):
    states = {(0, seasonsave.TODAY): (datetime.date(2015, 10, 13) - seasonsave.EPOCH).days, (0, seasonsave.HUMAN): 1,
              (1, seasonsave.HUMAN): 7, (0, seasonsave.YEAR): 2015}
    made_up_save(tmp_path, states=states)
    cal, _office, _host = tabs(Editor(built.data, str(tmp_path)))
    cal.follow(30)
    cal.season(True)
    s = cal.snapshot()
    assert s['month'] == '2026-10'
    assert next(d for w in s['weeks'] for d in w if d['today'])['date'] == '2026-10-13'
    rows = {g['date']: g for m in s['months'] for g in m['games']}
    assert rows['2026-10-01']['result']['text'] == 'L 2-3'
    cal.follow(234)                                     # the AHL is read from the save, not from this roster
    assert cal.snapshot()['summary']['gp'] == 10


def damage(path):
    with open(os.path.join(path, 'DATA0001'), 'r+b') as f:
        f.write(b'\xff' * 16)
    for n in os.listdir(path):
        os.utime(os.path.join(path, n), (time.time() - 30, time.time() - 30))


def test_no_save_a_save_being_written_or_a_damaged_one_gives_a_note(built, tmp_path):
    cal, _office, _host = tabs(Editor(built.data, str(tmp_path)))
    cal.follow(13)
    assert cal.snapshot()['season'] == {'on': False, 'available': False, 'label': None, 'note': NO_SAVE}
    cal.season(True)
    assert cal.snapshot()['season']['on'] is False
    made_up_save(tmp_path, 'BLES021531000', settled=False)
    cal.follow(13)
    assert 'still saving' in cal.snapshot()['season']['note']
    other = tmp_path / 'other'
    damage(made_up_save(other, 'BLES021530100'))
    cal, _office, _host = tabs(Editor(built.data, str(other)))
    cal.follow(13)
    assert 'damaged' in cal.snapshot()['season']['note']
    made_up_save(other, 'BLES021531001', age=120)       # an older Season that can be read
    cal.follow(13)
    s = cal.snapshot()
    assert s['season']['available'] and s['season']['label'].startswith('Season: ')


# --- the front office -----------------------------------------------------------------------------------------------
def test_payroll_and_cap_space_are_the_roster_s(patch_view):
    _cal, office, _host = tabs(Editor(patch_view, farm_ahl=True))
    R = Roster(patch_view)
    numbers = office.rail_numbers()
    assert set(L.NHL_PRIMARY) <= set(numbers) and all(numbers[t]['tip'] == 'cap space' for t in L.NHL_PRIMARY)
    for team in sorted(L.NHL_PRIMARY):
        office.follow(team)
        o = office.snapshot()
        payroll = contracts.payroll(R, team, contracts.REAL)
        cap = gamepatch.cap_of(1, 0)
        assert o['tiles'][0]['value'] == contracts.money(payroll)
        assert o['seasons'][0]['space_value'] == cap - payroll
        space = cap - payroll
        assert numbers[team]['text'] == f"{'-' if space < 0 else ''}${abs(space) / 1e6:.1f}M"
        keys = [{r['key'] for r in g['rows']} for g in o['groups']]
        assert not (keys[0] & keys[1] or keys[0] & keys[2] or keys[1] & keys[2])      # nobody listed twice
        assert len(keys[0]) == o['counts']['nhl'] > 0
    assert o['note'].startswith('Real dollars, as the patched game')


def test_on_a_patch_roster_the_deals_are_the_data_pack_s(patch_view, pack):
    _cal, office, _host = tabs(Editor(patch_view, farm_ahl=True))
    office.follow(L.API_TO_SLOT['EDM'])
    rows = {r['name']: r for r in office.snapshot()['groups'][0]['rows']}
    deal = next(d for d in pack['contracts'] if (d['first'], d['last']) == ('Connor', 'McDavid'))
    assert rows['Connor McDavid']['cap'] == deal['cap'] and rows['Connor McDavid']['years'] == deal['years']


def test_vegas_holds_rights_and_every_other_team_shows_its_own_roster(patch_view):
    """Owner, 2026-10-22: "the exe only showing NHL roster when clicking coachella"; every club holds contracts. A
    patch roster's rights have six bits (lab round 42): Vegas's prospects and Henderson's players are its own."""
    _cal, office, _host = tabs(Editor(patch_view, farm_ahl=True))
    R = Roster(patch_view)
    office.follow(31)
    o = office.snapshot()
    assert 'no prospect rights' not in o['groups'][2]['note']
    assert o['counts']['farm'] == len(R.team_roster(235))                  # everyone on Henderson
    assert sum(1 for x in R.team_roster(235) if x[1] is not None and R.P.get(x[1], 'WBbd') == 32) >= 9
    for farm, parent in ((234, 30), (235, 31)):
        office.follow(farm)
        o = office.snapshot()
        assert o['kind'] == 'club' and o['team']['id'] == farm and o['link']['team']['id'] == parent
        rows = o['groups'][0]['rows']
        assert len(rows) == len(R.team_roster(farm)) and all(r['cap'] for r in rows)    # every player under contract
        assert o['tiles'][0]['label'].startswith('Club payroll') and len(o['seasons']) == frontoffice.SEASONS
    kladno = next(t for t in sorted(L.EXTRALIGA) if R.team_roster(t))
    office.follow(kladno)
    o = office.snapshot()
    assert o['kind'] in ('club', 'pool') and o['groups'][0]['rows'] and not o.get('why')
    office.follow(min(L.NATIONAL))
    o = office.snapshot()
    assert o['kind'] == 'national' and 'his club' in o['about'] and o['seasons'] == []
    office.follow(min(L.MIRROR_OF))
    assert office.snapshot()['kind'] == 'copy'
    office.follow(model.FREE_AGENTS)
    o = office.snapshot()
    assert o['kind'] == 'free' and o['groups'][0]['rows'] and all(r['cap'] == 0 for r in o['groups'][0]['rows'])
    numbers = office.rail_numbers()
    assert numbers[234]['tip'] == 'club payroll' and numbers[30]['tip'] == 'cap space'


def test_sorting_and_one_group(built):
    _cal, office, _host = tabs(Editor(built.data))
    office.follow(13)
    caps = [r['cap'] for r in office.snapshot()['groups'][0]['rows']]
    assert caps == sorted(caps, reverse=True)
    office.sort('name')
    names = [r['name'] for r in office.snapshot()['groups'][0]['rows']]
    assert names == sorted(names)
    office.sort('name')
    assert [r['name'] for r in office.snapshot()['groups'][0]['rows']] == names[::-1]
    office.group('farm')
    o = office.snapshot()
    assert [g['key'] for g in o['groups']] == ['farm'] and o['sort'] == {'sort': 'name', 'dir': -1, 'group': 'farm'}
    assert o['note'].startswith('Real dollars. On a roster for the unpatched game')


def test_the_contract_window_previews_checks_and_keeps_a_contract(built):
    ed = Editor(built.data)
    _cal, office, host = tabs(ed)
    edm = L.API_TO_SLOT['EDM']
    office.follow(edm)
    key = find(ed.snap, 'Connor McDavid').who
    office.contract_open(key)
    c = office.contract_snapshot()
    current = contracts.deal_of(built_roster(built).P, find(ed.snap, 'Connor McDavid').prow, contracts.GAME)
    assert not c['sign'] and c['draft']['cap'] == current['cap'] and c['current'].startswith(contracts.money(current['cap']))
    before = office.snapshot()['seasons'][0]['space_value']
    office.contract_change('cap', current['cap'] - 1_000_000)
    c = office.contract_snapshot()
    assert c['preview']['before'] == contracts.money(before)
    assert c['preview']['after'] == contracts.money(before + 1_000_000)
    assert c['can_apply'] and len(c['years']) >= frontoffice.SEASONS
    office.contract_change('cap', 30_000_000)
    c = office.contract_snapshot()
    assert not c['can_apply'] and any('$30M' in p['text'] for p in c['problems'] if p['tone'] == 'bad')
    office.contract_apply()
    assert ed.edits == {} and ed.status[1] == 'warn'
    office.contract_change('cap', 15_000_000)
    office.contract_change('years', 3)
    office.contract_change('ext_on', True)
    office.contract_change('ext_years', 5)
    office.contract_change('ext_cap', 16_500_000)
    office.contract_apply()
    assert ed.edits[key]['contract'] == {'cap': 15_000_000, 'years': 3, 'two_way': 0, 'ext': [5, 16_500_000, 0]}
    assert office.contract_snapshot() is None and {'office', 'contract'} <= host.dirty
    row = next(r for r in office.snapshot()['groups'][0]['rows'] if r['key'] == key)
    assert row['edited'] and row['cap'] == 15_000_000 and row['ext'] == '5 x $16.5M'
    assert office.snapshot()['edited'] == 1
    office.contract_open(key)
    office.contract_reset()
    assert ed.edits == {}


def test_a_prospect_without_a_contract_is_signed(built):
    ed = Editor(built.data)
    _cal, office, _host = tabs(ed)
    for team in sorted(L.NHL_PRIMARY):
        office.follow(team)
        row = next((r for g in office.snapshot()['groups'] for r in g['rows'] if r['rights']), None)
        if row:
            break
    office.contract_open(row['key'])
    c = office.contract_snapshot()
    assert c['sign'] and c['current'].startswith('No contract') and c['preview']['note'] and c['can_apply']
    office.contract_apply()
    assert ed.edits[row['key']]['contract']['years'] in (1, 3)


def test_a_club_s_contract_pays_free_amounts(built):
    """A junior with no NHL rights signs with his club: from $5k, no two-way, Apply keeps it."""
    ed = Editor(built.data)
    _cal, office, _host = tabs(ed)
    R = built_roster(built)
    prow = next(i for i in range(R.P.cur_rec) if not R.P.get(i, 'WBbd') and R.teams_of(i)
                and all(t in L.OHL for _, t in R.teams_of(i)))
    team = R.teams_of(prow)[0][1]
    key = next(p.who for p in ed.snap.by_who.values() if p.prow == prow)
    office.follow(team)
    row = next(r for r in office.snapshot()['groups'][0]['rows'] if r['key'] == key)
    assert row['cap'] and row['where'] == 'Club deal'                       # the update's starter deal
    office.contract_open(key)
    c = office.contract_snapshot()
    assert not c['nhl'] and c['limits']['min'] == contracts.FREE_LOW and c['join'] is None
    assert c['preview']['label'].startswith("Payroll of")
    office.contract_change('cap', 40_000)
    office.contract_change('two_way', True)
    c = office.contract_snapshot()
    assert c['can_apply'] and not c['draft']['two_way']
    office.contract_apply()
    assert ed.edits[key]['contract'] == {'cap': 40_000, 'years': c['draft']['years'], 'two_way': 0, 'ext': None}


def test_a_free_agent_signs_with_a_team(built):
    ed = Editor(built.data)
    _cal, office, _host = tabs(ed)
    office.follow(model.FREE_AGENTS)
    row = next(r for r in office.snapshot()['groups'][0]['rows'] if not r['where'])      # nobody's rights
    office.contract_open(row['key'])
    c = office.contract_snapshot()
    assert c['sign'] and c['join'] and c['join']['value'] is None and not c['can_apply']
    assert c['current'].startswith('Free agent')
    office.contract_apply()
    assert ed.edits == {} and ed.status[1] == 'warn'
    shl = next(o['value'] for o in c['join']['options'] if o['value'] in L.SHL)
    office.contract_change('join', shl)
    c = office.contract_snapshot()
    assert c['team']['id'] == shl and c['can_apply']
    office.contract_apply()
    e = ed.edits[row['key']]
    assert e['team'] == shl and e['contract']['cap'] >= contracts.FREE_LOW


def built_roster(built):
    return Roster(built.data)
