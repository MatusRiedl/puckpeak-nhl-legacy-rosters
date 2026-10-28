"""The Roster editor's Save on the game's own roster (0.81.0): it stays the game's own 2014 roster (no update step runs, so
stock.prepare does not empty the All-Star teams, move the birth years or add spare records), and a roster updated from the
disc is a roster file like any other. Reports of testers: "Seattle has 0 captain(s)", "that is the game's own roster".

The disc tests need LEGACY_ROSTER_DISC (see test_stock.py)."""
import os

import pytest

from legacy_roster import datasource, edits, stock
from legacy_roster import layout as L
from legacy_roster.app import jobs
from legacy_roster.app.update import UpdateController
from legacy_roster.builder import Builder
from legacy_roster.editor import model
from legacy_roster.roster import Roster

DISC = os.environ.get('LEGACY_ROSTER_DISC')
EDMONTON = L.API_TO_SLOT['EDM']


@pytest.fixture(scope='module')
def disc_bytes():
    if not DISC or not os.path.exists(DISC):
        pytest.skip("no game disc (set LEGACY_ROSTER_DISC to your NHL Legacy disc image)")
    return stock.from_disc(DISC)


@pytest.fixture(scope='module')
def disc_edit(disc_bytes):
    """The disc roster saved with one renamed number and one new player in Edmonton."""
    snap = model.Snapshot(disc_bytes)
    first = snap.players[snap.rosters[EDMONTON][0]]
    mine = {first.who: {'label': first.name, 'set': {'num': 77}},
            edits.person_key('Puck', 'Peak', (2006, 5, 4)): {
                'label': 'Puck Peak', 'new': True, 'team': EDMONTON, 'ovr': 60,
                'set': {'first': 'Puck', 'last': 'Peak', 'pos': 'C', 'birth': [2006, 5, 4], 'country': 'SVK', 'num': 91}}}
    return first, mine, model.apply_edits(disc_bytes, mine, {}, 2026)


def test_saving_the_games_own_roster_keeps_it_the_games_own(disc_bytes):
    assert stock.untouched(Roster(disc_bytes)) and stock.birth_base(Roster(disc_bytes)) == 1900
    res = model.apply_edits(disc_bytes, {}, {}, 2026)
    assert res.problems == []           # was: Seattle and Vegas with 0 captains, 1078 spare players "without a UFA year"
    R, before = Roster(res.data), Roster(disc_bytes)
    assert stock.untouched(R)
    for slot in (30, 31):               # the All-Star teams are still the All-Star teams
        assert len(R.team_roster(slot)) == len(before.team_roster(slot)) > 0
    assert R.P.cur_rec == before.P.cur_rec


def test_edits_on_the_games_own_roster_are_read_back_and_saved_again_as_they_are(disc_bytes, disc_edit):
    first, mine, res = disc_edit
    assert res.problems == []
    R = Roster(res.data)
    assert stock.untouched(R)
    snap = model.Snapshot(res.data)
    again = snap.by_who[first.who]
    assert again.num == 77 and again.birth == first.birth
    puck = snap.by_who[edits.person_key('Puck', 'Peak', (2006, 5, 4))]
    assert puck.birth == (2006, 5, 4)   # the record counts from 1900: not read back ten years off
    assert model.apply_edits(res.data, mine, {}, 2026).data == res.data     # rule 4: a second Save changes nothing


def test_a_roster_updated_from_the_disc_is_not_the_untouched_one(disc_bytes, tmp_path):
    R = Roster(disc_bytes)
    assert stock.prepare(R, 2026)           # what every update of the game's own roster starts with
    R.reindex()
    saved = R.f.build()
    assert stock.is_stock(Roster(saved)) and stock.prepared(Roster(saved)) and not stock.untouched(Roster(saved))
    path = tmp_path / 'SYS-DATA'
    path.write_bytes(saved)
    assert not UpdateController._untouched(str(path))       # an export can start from it: it needs no disc


def test_the_untouched_disc_roster_file_is_refused_for_an_export(disc_bytes, tmp_path):
    path = tmp_path / 'SYS-DATA'
    path.write_bytes(disc_bytes)
    assert UpdateController._untouched(str(path))


def test_a_team_that_cannot_dress_still_gets_its_letters_back(base_bytes, data):
    R = Roster(base_bytes)
    b = Builder(R, data)
    for e in b.entries_on(EDMONTON):
        b.U.set(e, 'lcCm', 0)
    edits._hand_on_letters(b, EDMONTON, {})
    letters = [b.U.get(e, 'lcCm') for e in b.entries_on(EDMONTON)]
    assert letters.count(1) == 1 and letters.count(2) == 2
    assert all(not b.U.get(e, 'lcCm') for e in b.entries_on(EDMONTON) if b.cls(e) == 'G')


def test_nhl_pages_without_a_birthdate_or_a_name_are_left_out_not_a_crash(monkeypatch):
    page = {'forwards': [{'id': 1, 'birthDate': None, 'firstName': {'default': 'No'}, 'lastName': {'default': 'Birth'},
                          'positionCode': 'C'},
                         {'id': 2, 'birthDate': '1990-01-02', 'firstName': None, 'lastName': {'default': 'Name'},
                          'positionCode': 'C'},
                         {'id': 3, 'birthDate': '1990-01-02', 'firstName': {'default': 'Ok'},
                          'lastName': {'default': 'Player'}, 'positionCode': 'C'}]}
    out = datasource.flatten_nhl({'EDM': page})
    assert [p['last'] for p in out] == ['Player']


def test_a_searched_player_with_an_empty_page_is_skipped(monkeypatch):
    pages = {'search': [{'name': 'Some Body', 'active': True, 'playerId': 7}], 'landing': {'birthDate': None}}
    monkeypatch.setattr(datasource, 'http_json', lambda url: pages['landing'] if 'landing' in url else pages['search'])
    monkeypatch.setattr(datasource.time, 'sleep', lambda s: None)
    assert datasource._search_player('Some Body', 1995, 3) is None
    pages['landing'] = None
    assert datasource._search_player('Some Body', 1995, 3) is None
    pages['search'] = None
    assert datasource._search_player('Some Body', 1995, 3) is None


def test_the_error_message_says_where_the_program_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs.datasource, 'app_dir', lambda *parts: str(tmp_path / 'error.log'))
    try:
        datasource.flatten_nhl({'EDM': {'forwards': [None]}})
    except Exception as err:            # a page that is not a player: the real error is a program error
        text = jobs.log_unexpected(err)
    assert 'Something went wrong' in text and 'datasource.py:' in text and ' in flatten_nhl' in text


def test_the_editor_names_the_all_star_teams_of_the_games_own_roster_as_they_are(disc_bytes, base_bytes):
    names = model.Snapshot(disc_bytes).team_names
    assert 'Seattle' not in names[30] and 'Vegas' not in names[31]
    assert model.Snapshot(base_bytes).team_names[30] == 'Seattle Kraken'
