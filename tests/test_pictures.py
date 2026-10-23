"""Player pictures on a PC with several rosters (testers of 0.10.4): the player's own pictures go into the game also
with photos and logos off, a picture number someone else uses is never given out (and ours on it goes back), and a
photo that cannot be made leaves the player the picture he had. Synthetic discs as in test_art.py."""
import os
from types import SimpleNamespace

import pytest

from legacy_roster import edits, pipeline
from legacy_roster.art import install, menus, portraits
from legacy_roster.art.lab import portrait_folder
from legacy_roster.editor import model
from legacy_roster.roster import Roster

from .test_art import SizedDisc, fake_rpcs3, head_photo

QUIET = lambda msg: None


@pytest.fixture(autouse=True)
def no_menu(monkeypatch):
    """The fake discs have no boot.big: the main menu step writes nothing (tests/test_menus.py has it)."""
    monkeypatch.setattr(menus, 'hidden_files', lambda disc, mode: {})


def grey(img):
    return img.convert('LA').convert('RGBA')


# --- who is the same person ------------------------------------------------------------------------
def test_people_are_compared_without_the_birth_year():
    key = portraits.person_key('Zach', 'Benson', (2005, 5, 12))
    loose = portraits.loose_key(key)
    assert loose == 'zach|benson|05-12'
    same = portraits.same_person
    assert same(loose, portraits.loose_key(portraits.person_key('Zach', 'Benson', (1994, 5, 12))))   # patch roster
    assert same('alex|ovechkin|09-17', 'alexander|ovechkin|09-17')
    assert same('mitch|marner|05-05', 'mitchell|marner|01-01')          # a birthday the update corrected
    assert same('zach|benson|05-12', 'zachary|benson|05-12')
    assert not same('daniel|sedin|09-26', 'henrik|sedin|09-26')          # twins
    assert not same('trae|peterson|05-12', 'zach|benson|05-12')
    assert not same('zach|benson|05-12', 'zach|bentley|05-12')


# --- numbers -----------------------------------------------------------------------------------------
def test_a_number_someone_else_uses_is_never_given_out(tmp_path):
    reg = portraits.Registry(str(tmp_path / 'ids.json'))
    benson = portraits.person_key('Zach', 'Benson', (2005, 5, 12))
    claims = portraits.Claims(rosters={40000: {'trae|peterson|01-01'}, 40002: {'zach|benson|05-12'}}, theirs={40001})
    assert reg.id_for(benson, 0, set(), claims) == 40003      # not Peterson's, not a pack's file, not one in use
    reg.ids[benson] = 40000                                   # remembered, but another roster shows Peterson with it
    assert reg.id_for(benson, 0, set(), claims) not in (40000, 40001)
    # the community roster's own numbers are his where nobody else has them, also in its range
    reg = portraits.Registry(str(tmp_path / 'none.json'))
    assert reg.id_for(benson, 25000, set(), portraits.Claims(rosters={25000: {'zachary|benson|05-12'}})) == 25000
    # a copy of him on a national team shares his number: the same person
    assert reg.id_for(benson, 25000, set(), None, here={25000: {'zach|benson|05-12'}}) == 25000


def test_numbers_of_ours_others_use_are_forgotten_and_contested_ones_found():
    benson = portraits.person_key('Zach', 'Benson', (2005, 5, 12))
    knight = portraits.person_key('Spencer', 'Knight', (2001, 4, 30))
    reg = SimpleNamespace(ids={benson: 20100, knight: 20200}, forget=lambda key: reg.ids.pop(key))
    claims = portraits.Claims(rosters={20100: {'zach|benson|05-12', 'trae|peterson|07-26'},
                                       20200: {'spencer|knight|04-30'}},
                              ours={20100, 20200}, urls={20100: 'https://photo/benson.png'})
    assert portraits.forget_conflicts(reg, claims) == {20100: (benson, 'https://photo/benson.png')}
    assert reg.ids == {knight: 20200}
    assert claims.contested() == {20100}


def test_scan_finds_every_roster_and_picture_file_and_gives_ours_back(base_dir, base_bytes, tmp_path, monkeypatch):
    pytest.importorskip('PIL')
    r = fake_rpcs3(base_dir, tmp_path, monkeypatch)
    monkeypatch.setattr(install, 'Disc', SizedDisc)
    monkeypatch.setattr(install, '_download', lambda url: head_photo())
    heads = os.path.join(r.game_folder('BLES02153'), 'fe', 'ion', 'artassets', 'playerheads')
    path = lambda aid: os.path.join(heads, portrait_folder(aid), f"p{aid}.big")
    os.makedirs(os.path.dirname(path(40500)))
    for aid in (40500, 40600):
        with open(path(aid), 'wb') as f:
            f.write(b'another pack')
    install.install(r, 'BLES02153', {40600: 'https://photo/a.png', 40700: 'https://photo/b.png'}, {}, say=QUIET)

    claims = install.scan_claims(r)
    P = Roster(base_bytes).P
    row = next(i for i in range(P.cur_rec) if P.get(i, 'hasportrait'))
    who = portraits.loose_key(portraits.person_key(P.get(row, 'PedH'), P.get(row, 'RMbQ'), portraits.birth_of(P, row)))
    assert who in claims.rosters[P.get(row, 'artid')]
    assert claims.theirs == {40500, 40600}                    # a pack's file, and one we covered (its copy kept)
    assert {40600, 40700} <= claims.ours and claims.urls[40700] == 'https://photo/b.png'

    assert install.give_back({40600, 40700}, say=QUIET) == 2
    assert open(path(40600), 'rb').read() == b'another pack' and not os.path.exists(path(40700))
    assert open(path(40500), 'rb').read() == b'another pack'
    assert install.installed() == 0


# --- the player's own pictures ------------------------------------------------------------------------
def _no_portrait(R):
    return next(i for i in range(R.P.cur_rec) if R.teams_of(i) and not R.P.get(i, 'hasportrait'))


def test_own_pictures_alone_change_only_their_players(base_bytes, tmp_path):
    R0 = Roster(base_bytes)
    prow = _no_portrait(R0)
    mine = {edits.who_of(R0.P, prow): {'photo': 'file:terry.png'}}
    art = SimpleNamespace(registry=portraits.Registry(str(tmp_path / 'ids.json')), own_only=True, moved={},
                          claims=portraits.Claims(rosters={40000: {'trae|peterson|07-26'}}), check=lambda links: {})
    plain = model.apply_edits(base_bytes, mine, {}, 2026)
    res = model.apply_edits(base_bytes, mine, {}, 2026, art=art)
    assert res.ok, res.problems[:5]
    photos, logos, names = res.art
    R, Q = Roster(res.data), Roster(plain.data)
    assert photos == {40001: 'file:terry.png'} and logos == {} and names is None
    assert R.P.get(prow, 'artid') == 40001 and R.P.get(prow, 'hasportrait') == 1
    others = [i for i in range(R.P.cur_rec) if i != prow]
    assert all(R.P.get(i, 'artid') == Q.P.get(i, 'artid') and R.P.get(i, 'hasportrait') == Q.P.get(i, 'hasportrait')
               for i in others)
    assert [R.T.get(t, 'artid') for t in range(R.T.cur_rec)] == [Q.T.get(t, 'artid') for t in range(Q.T.cur_rec)]
    assert [R.T.get(t, 'fullname') for t in range(R.T.cur_rec)] == [Q.T.get(t, 'fullname') for t in range(Q.T.cur_rec)]

    # a picture that cannot be made: he keeps what he had, nothing else changes
    art.check = lambda links: {'file:terry.png': 'no head found in it'}
    bad = model.apply_edits(base_bytes, mine, {}, 2026, art=art)
    assert bad.ok and bad.art[0] == {} and bad.builder.bad_pictures == {'file:terry.png': 'no head found in it'}
    assert bad.data == plain.data


def test_own_pictures_go_in_with_photos_off(base_dir, data, tmp_path, monkeypatch):
    pytest.importorskip('PIL')
    r = fake_rpcs3(base_dir, tmp_path, monkeypatch)
    monkeypatch.setattr(install, 'Disc', SizedDisc)
    monkeypatch.setattr(install.PhotoPack, 'open', classmethod(lambda cls, *a, **k: None))
    photo = tmp_path / 'terry.png'
    head_photo().save(photo)
    R0 = Roster(open(os.path.join(base_dir, 'SYS-DATA'), 'rb').read())
    prow = _no_portrait(R0)
    mine = {edits.who_of(R0.P, prow): {'photo': 'file:' + str(photo)}}
    slot = os.path.basename(base_dir)
    run = lambda: pipeline.update(r.savedata, slot, [], None, data=data, in_place=True,
                                  backup_root=str(tmp_path / 'b'), rpcs3=r, my_edits=mine)
    first = run()
    assert first.build.ok and first.own_pictures
    aid = Roster(first.build.data).P.get(prow, 'artid')
    assert aid in portraits.FRESH_IDS and first.build.art[0] == {aid: 'file:' + str(photo)}
    assert first.art == (1, 0, 0) and first.art_line().startswith("Your own pictures: 1 pictures installed")
    heads = os.path.join(r.game_folder('BLES02153'), 'fe', 'ion', 'artassets')
    assert all(os.path.exists(os.path.join(heads, kind, portrait_folder(aid), f"p{aid}.big"))
               for kind in install.PORTRAIT_KINDS)
    assert not os.path.exists(os.path.join(heads, '..', '..', 'loc'))          # no team names without photos

    again = run()                                     # the same roster again: the same bytes, nothing written
    assert again.build.data == first.build.data and again.art == (0, 1, 0)

    monkeypatch.setattr(install.savedata, 'running_rpcs3', lambda: 'rpcs3.exe')
    with pytest.raises(Exception):                    # in place needs RPCS3 closed anyway
        run()


# --- pictures that are no photo ----------------------------------------------------------------------
def test_a_grey_stand_in_is_no_photo(base_dir, tmp_path, monkeypatch):
    pytest.importorskip('PIL')
    from legacy_roster.art import images
    real = images.portrait(head_photo(), (256, 128))
    assert not images.stand_in(real) and images.stand_in(grey(real))
    r = fake_rpcs3(base_dir, tmp_path, monkeypatch)
    monkeypatch.setattr(install, 'Disc', SizedDisc)
    monkeypatch.setattr(install, '_download', lambda url: grey(head_photo()) if 'grey' in url else head_photo())
    links = ['https://photo/grey.png', 'https://photo/real.png']
    assert install.prefetch(links, r, 'BLES02153', say=QUIET, pack=False) == {'https://photo/grey.png': install.STAND_IN}
    own = tmp_path / 'old.png'                        # a black-and-white picture of the player's own is fine
    grey(head_photo()).save(own)
    assert install.prefetch(['file:' + str(own)], r, 'BLES02153', say=QUIET, pack=False, cache=False) == {}
