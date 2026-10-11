"""The new window's controllers (app/) with a pretend window: what the page is told, what its buttons do.
Needs the base roster (conftest.py); nothing is written outside the test's own folder."""
import json
import os
import shutil
import time

import pytest

from legacy_roster import savedata


class FakeHost:
    """What a controller needs from the window, with the answers of file dialogs set by the test."""

    def __init__(self):
        self.dirty, self.lines, self.opened = set(), [], []
        self.pick = None

    def changed(self, name):
        self.dirty.add(name)

    def log(self, *lines):
        self.lines.extend(lines)

    def log_clear(self):
        self.lines = []

    def send(self, event, payload=None):
        pass

    def ask_open(self, *args, **kwargs):
        return self.pick

    def ask_folder(self, *args, **kwargs):
        return self.pick

    def ask_save(self, *args, **kwargs):
        return self.pick

    def open_path(self, path):
        self.opened.append(path)

    def open_url(self, url):
        self.opened.append(url)


def wait(condition, seconds=120):
    end = time.time() + seconds
    while time.time() < end:
        if condition():
            return
        time.sleep(0.05)
    raise AssertionError("timed out")


@pytest.fixture
def app(base_dir, tmp_path, monkeypatch, pack):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'local'))
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: None)
    sd = tmp_path / 'rpcs3' / 'dev_hdd0' / 'home' / '00000001' / 'savedata'
    shutil.copytree(base_dir, sd / os.path.basename(base_dir))
    exe = tmp_path / 'rpcs3' / 'rpcs3.exe'
    exe.write_bytes(b'')
    from legacy_roster.app import settings as S
    monkeypatch.setattr(S, 'save', lambda values: None)
    from legacy_roster.app.editor import EditorController
    from legacy_roster.app.uniforms import UniformsController
    from legacy_roster.app.update import UpdateController
    host = FakeHost()
    upd = UpdateController(host, settings={'rpcs3': str(exe)}, pack=pack, photo_pack=None)
    ed = EditorController(host, upd)
    uni = UniformsController(host, ed)
    upd.start_up()
    wait(lambda: not upd.scanning and upd.slots)
    return host, upd, ed, uni, str(sd)


def idle(ed):
    wait(lambda: not ed.busy and ed.after_busy is None)


def test_the_update_tab_lists_the_roster_and_says_nothing_about_other_versions(app):
    _host, upd, _ed, _uni, _sd = app
    s = upd.snapshot()
    json.dumps(s)
    assert [r['folder'] for r in s['rosters']] == [os.path.basename(upd.slots[0].folder)]
    assert s['selected'] == upd.slots[0].folder
    assert s['rpcs3']['note'] is None           # the "Found 2 rosters ..." line is gone
    assert s['save']['button']['enabled']


def test_editor_shows_teams_and_a_card_and_applies_an_edit(app):
    host, upd, ed, _uni, _sd = app
    ed.opened()
    idle(ed)
    s = ed.snapshot()
    json.dumps(s)
    assert s['loaded'] and s['league'] == 'NHL' and s['rows']
    row = next(r for r in s['rows'] if r['pos'] == 'D')
    ed.pick_player(row['id'])
    card = ed.snapshot()['card']
    assert card['title'] == row['name'] and card['values']['num'] == str(row['num'])
    key = card['key']
    # a defenseman's card goes through unchanged (the game's own ratings may be below 40)
    assert ed.apply(dict(card['values']), quiet=True) == 'nothing'
    new_num = '12' if card['values']['num'] != '12' else '13'
    assert ed.apply(dict(card['values'], num=new_num)) == 'applied'
    idle(ed)
    s = ed.snapshot()
    assert s['card']['key'] != key and s['card']['values']['num'] == new_num and s['card']['undo']
    assert any(r['tag'] == 'edited' for r in s['rows'])
    assert s['edits_count'] == 1 and 'update' in host.dirty
    ed.undo()
    idle(ed)
    assert ed.snapshot()['edits_count'] == 0


def test_a_card_typed_on_but_not_applied_is_applied_on_save_as_new(app):
    _host, upd, ed, _uni, sd = app
    upd.set_save_mode('new')
    ed.opened()
    idle(ed)
    row = ed.snapshot()['rows'][0]
    ed.pick_player(row['id'])
    values = ed.snapshot()['card']['values']
    before = len(savedata.list_rosters(sd))
    ed.save(dict(values, first='Changed'))
    wait(lambda: len(savedata.list_rosters(sd)) == before + 1 and not ed.busy)
    assert ed.status[1] == 'good' and ed.status[0].startswith("Saved as")
    assert any(e['set'].get('first') == 'Changed' for e in ed.edits.values())


def test_a_bad_card_is_named_when_another_player_is_picked(app):
    _host, _upd, ed, _uni, _sd = app
    ed.opened()
    idle(ed)
    rows = ed.snapshot()['rows']
    ed.pick_player(rows[0]['id'])
    ed.pick_player(rows[1]['id'], dict(ed.snapshot()['card']['values'], birth='soon'))
    assert ed.status[1] == 'bad' and "were not taken" in ed.status[0]
    assert ed.snapshot()['card']['title'] == rows[1]['name']


def test_search_team_window_and_my_edits(app):
    _host, _upd, ed, _uni, _sd = app
    ed.opened()
    idle(ed)
    ed.search('a')
    assert ed.snapshot()['searching'] and ed.snapshot()['rows']
    ed.search('')
    assert not ed.snapshot()['searching']
    ed.team_open()
    m = ed.snapshot()['modal']
    assert m['kind'] == 'team' and m['fields']['abbr']
    ed.team_apply({'full': 'Test Team', 'city': '', 'abbr': ''})
    idle(ed)
    assert ed.teams[str(ed.team)] == {'full': 'Test Team'} and ed.snapshot()['team_name'] == 'Test Team'
    ed.edits_open()
    items = ed.snapshot()['modal']['items']
    assert [i['kind'] for i in items] == ['team']
    ed.edits_remove('team', items[0]['key'])
    idle(ed)
    assert ed.teams == {}


def test_new_player_shows_on_the_card_once_added(app):
    _host, _upd, ed, _uni, _sd = app
    ed.opened()
    idle(ed)
    ed.new_player()
    card = ed.snapshot()['card']
    assert card['new'] and card['values']['ovr'] == '70'
    values = dict(card['values'], first='Zed', last='Testman', num='91', birth='2005-01-02')
    assert ed.apply(values) == 'applied'
    idle(ed)
    card = ed.snapshot()['card']
    assert card['title'] == 'Zed Testman' and not card['new']


def test_jerseys_and_ice_keep_only_what_differs(app):
    _host, _upd, ed, uni, _sd = app
    ed.opened()
    idle(ed)
    ed.pick_team(0)
    ed.uniforms_open()
    wait(lambda: uni.snapshot() and uni.snapshot()['loaded'])
    s = uni.snapshot()
    json.dumps(s)
    assert s['rows'] and s['ice']['mode'] == 'game'
    assert uni._collect() == ({}, {})
    uni.set_colour('primary', '#ff0000')
    uni.pick(s['rows'][0]['variant'], 'colours')
    uni.set_arena('Test Arena')
    uniforms, ice = uni._collect()
    assert uniforms['colours'] == {'primary': '#ff0000'} and ice == {'arena': 'Test Arena'}
    assert uniforms['versions'] == {str(s['rows'][0]['variant']): 'colours'}
    uni.apply()
    assert uni.snapshot() is None and ed.teams['0']['ice'] == {'arena': 'Test Arena'}
    ed.uniforms_open()
    wait(lambda: uni.snapshot() and uni.snapshot()['loaded'])
    assert uni.snapshot()['colours']['primary']['hex'] == '#ff0000'
    uni.undo()
    assert '0' not in ed.teams


def test_equipment_choices_go_to_the_player_and_the_team_and_can_be_taken_back(app):
    from legacy_roster.app.equipment import EquipmentController
    host, _upd, ed, _uni, _sd = app
    eq = EquipmentController(host, ed)
    ed.opened()
    idle(ed)
    ed.pick_team(0)
    row = next(r for r in ed.snapshot()['rows'] if r['pos'] == 'D')
    ed.pick_player(row['id'])
    assert ed.snapshot()['card']['equipment']
    eq.open()
    wait(lambda: eq.snapshot() and eq.snapshot()['loaded'])
    s = eq.snapshot()
    json.dumps(s)
    assert [r['choice'] for r in s['rows']][:2] == ['stick', 'tape'] and not s['can_player'] and not s['can_team']
    now = {r['choice']: r['value'] for r in s['rows']}
    eq.pick('tape', 1 - now['tape'])
    eq.pick('stick', 105)
    assert eq.snapshot()['can_player'] and eq.snapshot()['can_team']
    eq.apply_player()
    idle(ed)
    key = ed.edit_key(eq._player())
    assert ed.edits[key]['equipment'] == {'tape': 1 - now['tape'], 'stick': 105}
    wait(lambda: eq._player().equipment['stick'] == 105)    # the roster is read again with the edit in it
    eq.pick('sock_tuck', 3)
    eq.pick('stick', 86)
    eq.apply_team()
    idle(ed)
    wait(lambda: eq._player().equipment['sock_tuck'] == 3)
    assert ed.teams['0']['equipment'] == {'sock_tuck': 3}   # the stick is not a team choice
    assert eq.snapshot()['undo']
    eq.undo()
    idle(ed)
    assert not ed.edits and 'equipment' not in (ed.teams.get('0') or {}) and eq.snapshot() is None


def test_a_goalies_equipment_window_has_the_mask_and_keeps_his_own_mask_picture(app, tmp_path):
    from legacy_roster.app.equipment import EquipmentController
    host, _upd, ed, _uni, _sd = app
    eq = EquipmentController(host, ed)
    ed.opened()
    idle(ed)
    ed.pick_team(0)
    row = next(r for r in ed.snapshot()['rows'] if r['pos'] == 'G')
    ed.pick_player(row['id'])
    assert ed.snapshot()['card']['equipment']
    eq.open()
    wait(lambda: eq.snapshot() is not None)
    s = eq.snapshot()
    json.dumps(s)
    assert s['goalie'] and [r['choice'] for r in s['rows']][:2] == ['mask', 'pads'] and not s['can_player']
    picture = tmp_path / 'mask.png'
    picture.write_bytes(b'x')
    ed.pick_picture = lambda title: 'file:' + str(picture)
    eq.choose_mask_picture()
    assert eq.snapshot()['can_player'] and eq.snapshot()['mask_picture'] == str(picture)
    eq.pick('pads', 7)
    eq.apply_player()
    idle(ed)
    key = ed.edit_key(eq._player())
    assert ed.edits[key]['mask_picture'] == 'file:' + str(picture) and ed.edits[key]['equipment'] == {'pads': 7}
    eq.undo()
    idle(ed)
    assert not ed.edits
