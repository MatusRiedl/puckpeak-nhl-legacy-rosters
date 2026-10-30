"""Created looks (faces.py LOOK, the game's Create Player "Custom Head"): only new players get one, on the records the
game's Create Player fills; verify refuses a created head anywhere else."""
import pytest

from legacy_roster import edits, faces, pipeline, verify
from legacy_roster import layout as L
from legacy_roster.roster import Roster

LOOK = {'shape': 12, 'tone': 14, 'hair': 8, 'hair_colour': 5, 'facial_hair': 3, 'facial_hair_colour': 4,
        'eyebrow': 4, 'eyebrow_colour': 1, 'eyes': 6, 'black_eye': 2, 'scars': 1, 'freckles': 1}


def find(R, name):
    return next(i for i in range(R.P.cur_rec) if R.name(i) == name)


def new_player(first, last, pos, team, look=None, birth=(2008, 3, 9), country=None):
    e = {'label': f"{first} {last}", 'new': True, 'team': team, 'ovr': 62,
         'set': {'first': first, 'last': last, 'pos': pos, 'birth': list(birth)}}
    if country:
        e['set']['country'] = country
    if look is not None:
        e['look'] = look
    return edits.person_key(first, last, birth), e


def test_the_game_s_choices():
    whole, problems = faces.clean_look({'hair': 1, 'tone': 16, 'eyes': '6', 'scars': 'x'})
    assert whole == dict(faces.DEFAULT_LOOK, tone=16, eyes=6)
    assert len(problems) == 2 and "Hairstyle 1" in problems[0]
    assert faces.look_wrong(LOOK) is None
    assert faces.look_wrong({'facial_hair': 10}) and faces.look_wrong({'eyebrow': 6})
    assert [n for n, _w in faces.LOOK['hair'][1]] == [3, 4, 5, 6, 8, 0, 2, 7]       # the menu's order
    assert faces.wrong({'head': 20500}, {20500}) and faces.wrong({'eyes': 6}, set()) is None


def test_every_roster_keeps_the_create_player_records_free(built, base_bytes):
    for R in (Roster(base_bytes), Roster(built.data)):       # a full update takes none of them
        P = R.P
        rows = [i for i in range(P.cur_rec) if faces.is_reserved(P, i)]
        assert len(rows) == 180
        assert sum(faces.is_free(R, i) for i in rows) == 179         # one community player has one
        assert len(faces.free_reserved(R, True)) == 30 - faces.KEEP_FREE['G']
        assert len(faces.free_reserved(R, False)) == 149 - faces.KEEP_FREE['S']
        assert set(faces.SHAPES) <= faces.heads(R)


@pytest.fixture(scope='module')
def made(base_bytes, data, built):
    R = Roster(built.data)
    crosby = find(R, 'Sidney Crosby')
    mine = dict([new_player('Kaspar', 'Lindqvist', 'C', L.API_TO_SLOT['EDM'], LOOK),
                 new_player('Otto', 'Brandvold', 'G', 'FA', {'shape': 3, 'tone': 2}, country='NOR'),
                 new_player('Milan', 'Rezek', 'D', L.API_TO_SLOT['PIT'])])
    mine[edits.who_of(R.P, crosby)] = {'label': 'Sidney Crosby', 'look': LOOK}
    first = pipeline.build(base_bytes, data, my_edits=mine)
    return mine, first


def test_a_new_player_gets_his_look_on_a_create_player_record(made):
    _mine, first = made
    assert first.ok, first.problems[:5]
    A = Roster(first.data)
    kaspar, otto, milan = find(A, 'Kaspar Lindqvist'), find(A, 'Otto Brandvold'), find(A, 'Milan Rezek')
    assert A.P.get(kaspar, 'zIBw') == 16179 and A.P.get(otto, 'zIBw') == 16029     # from the top down
    assert faces.read_look(A, kaspar) == LOOK
    assert A.P.get(kaspar, 'DaPp') == faces.SHAPES[11] and A.P.get(kaspar, 'QDTK') == faces.TONE_SKIN[13]
    row = faces.look_row(A, kaspar)
    assert A.f['Vzjq'].get(row, 'qFky') == 179 and A.f['Vzjq'].get(row, 'xohz') == 13
    assert faces.read_look(A, otto) == dict(faces.DEFAULT_LOOK, shape=3, tone=2)
    for prow in (kaspar, otto):
        assert A.P.get(prow, 'NYKk') == 1 and not faces.is_free(A, prow)
    assert A.P.get(kaspar, 'hleL') == L.country_code('CAN') and A.P.get(otto, 'hleL') == L.country_code('NOR')
    assert not faces.is_reserved(A.P, milan) and faces.read_look(A, milan) is None   # no look: an ordinary record
    assert sum(faces.is_free(A, i) for i in range(A.P.cur_rec)) == 177
    # listed through the record's own link, as the game's Create Player does (a career copies the look only then)
    assert [A.U.get(e, 'TWSX') for e in range(A.U.cur_rec) if A.link_to_pid.get(A.U.get(e, 'TWSX')) == 16179] \
        == [16179] * len(A.teams_of(kaspar))
    assert 16029 in [A.Q.get(i, 'TWSX') for i in range(A.Q.cur_rec)]
    assert sorted(A.pid_to_links[16179]) == [16179] and sorted(A.pid_to_links[16029]) == [16029]
    assert faces.link_problems(A, A) == []


def ordinary_link(R, pid):
    """Roster `R` as this program made it before lab round 45: the player of Create Player record `pid` listed
    through an ordinary link."""
    links = {R.C.get(i, 'qEfv') for i in range(R.C.cur_rec)}
    link = next(k for k in range(1, 16000) if k not in links)
    R.C.add_record({'BERR': 0, 'qEfv': link, 'qFky': pid})
    for e in range(R.U.cur_rec):
        if R.U.get(e, 'TWSX') == pid:
            R.U.set(e, 'TWSX', link)
    return link


def test_a_player_listed_through_an_ordinary_link_is_refused_and_mended(made, built, data):
    mine, first = made
    A = Roster(first.data)
    link = ordinary_link(A, 16179)
    old = A.f.build()
    problems, _ = verify.verify(old, Roster(built.data))
    assert f"Kaspar Lindqvist: listed through link {link}, not the game's own link of his record" in problems
    res = pipeline.build(old, data, steps=[], my_edits=mine)
    assert res.ok, res.problems[:5]
    B = Roster(res.data)
    assert sorted(B.pid_to_links[16179]) == [16179] and link not in B.link_to_pid
    assert [B.U.get(e, 'TWSX') for e in range(B.U.cur_rec) if B.link_to_pid.get(B.U.get(e, 'TWSX')) == 16179]
    again = pipeline.build(res.data, data, steps=[], my_edits=mine)
    assert again.ok and again.data == res.data


def test_a_look_on_a_player_the_game_has_is_skipped(made, built):
    _mine, first = made
    A, R = Roster(first.data), Roster(built.data)
    crosby = find(A, 'Sidney Crosby')
    assert A.P.get(crosby, 'DaPp') == R.P.get(find(R, 'Sidney Crosby'), 'DaPp')
    assert any(r[1] == 'edit skipped' and r[2] == 'Sidney Crosby' and 'created look' in r[3] for r in first.log)


def test_looks_change_nothing_twice(made, data):
    mine, first = made
    again = pipeline.build(first.data, data, my_edits=mine)
    assert again.ok, again.problems[:5]
    assert again.data == first.data
    A = Roster(again.data)
    assert sum(1 for i in range(A.P.cur_rec) if A.name(i) == 'Kaspar Lindqvist') == 1


def test_a_changed_look_reaches_the_same_record(made, data):
    mine, first = made
    key = next(k for k, e in mine.items() if e['label'] == 'Kaspar Lindqvist')
    changed = dict(mine, **{key: dict(mine[key], look=dict(LOOK, hair=0, freckles=0))})
    res = pipeline.build(first.data, data, steps=[], my_edits=changed)
    assert res.ok, res.problems[:5]
    A = Roster(res.data)
    kaspar = find(A, 'Kaspar Lindqvist')
    assert A.P.get(kaspar, 'zIBw') == 16179 and faces.read_look(A, kaspar) == dict(LOOK, hair=0, freckles=0)


def test_when_the_records_run_out_the_player_is_made_without_his_look(built, data):
    R = Roster(built.data)
    P = R.P
    for prow in faces.free_reserved(R, True):           # the game's Create Player used them all (but those kept free)
        P.set(prow, 'PedH', 'Made')
        P.set(prow, 'RMbQ', f"Ingame{P.get(prow, 'zIBw')}")
        P.set(prow, 'NYKk', 1)
    full = R.f.build()
    mine = dict([new_player('Otto', 'Brandvold', 'G', 'FA', {'shape': 3})])
    res = pipeline.build(full, data, steps=[], my_edits=mine)
    assert res.ok, res.problems[:5]
    A = Roster(res.data)
    otto = find(A, 'Otto Brandvold')
    assert not faces.is_reserved(A.P, otto)
    assert any(r[1] == 'edit skipped' and r[2] == 'Otto Brandvold' and 'created look' in r[3] for r in res.log)
    assert sum(faces.is_free(A, i) for i in range(A.P.cur_rec) if faces.is_reserved(A.P, i, goalie=True)) == 5


def test_verify_refuses_a_created_head_off_the_create_player_records(built, made):
    R = Roster(built.data)
    makar = find(R, 'Cale Makar')
    R.P.set(makar, 'DaPp', faces.SHAPES[0])
    problems, _ = verify.verify(R.f.build(), Roster(built.data))
    assert any(p.startswith("Cale Makar: a created head") for p in problems)
    _mine, first = made
    A = Roster(first.data)
    kaspar = find(A, 'Kaspar Lindqvist')
    A.P.set(kaspar, 'QDTK', 3)                          # not tone 14's colour
    A.f['Vzjq'].set(faces.look_row(A, kaspar), 'TpVs', 1)       # not a hairstyle of the menu
    problems, _ = verify.verify(A.f.build(), Roster(built.data))
    assert "Kaspar Lindqvist: skin colour 3 does not fit skin tone 14" in problems
    assert any(p.startswith("customfacetable row 179: Hairstyle 1") for p in problems)


def test_a_created_head_off_the_menu_that_the_roster_had_is_saved(built, data):
    """A tester's own player (the game's Create Player, or another tool) wore head 20300: one of the game's 24 created
    heads but not one of the menu's 15. Editing him was refused; what the roster already had is never blamed."""
    R = Roster(built.data)
    P = R.P
    prow = faces.free_reserved(R, False)[0]
    P.set(prow, 'PedH', 'Tester')
    P.set(prow, 'RMbQ', 'Ownplayer')
    P.set(prow, 'NYKk', 1)
    P.set(prow, 'DaPp', 20300)
    P.set(prow, 'QDTK', 9)              # not the colour of his row's tone either
    assert 20300 in faces.heads(R) and 20300 not in faces.SHAPES
    old = R.f.build()
    makar = find(R, 'Cale Makar')
    res = pipeline.build(old, data, steps=[], my_edits={edits.who_of(P, makar): {'label': 'Cale Makar',
                                                                                 'set': {'first': 'Kale'}}})
    assert res.ok, res.problems[:5]
    A = Roster(res.data)
    assert find(A, 'Kale Makar') is not None
    tess = find(A, 'Tester Ownplayer')
    assert A.P.get(tess, 'DaPp') == 20300 and A.P.get(tess, 'QDTK') == 9
    # every created head the game draws is fine; a head it lacks is still refused when this program puts it there
    assert set(faces.CREATED_HEADS) <= faces.heads(R)
    A.P.set(tess, 'DaPp', 21000)
    assert not any('head 21000' in p for p in verify.verify(A.f.build(), Roster(old))[0])
    A.P.set(tess, 'DaPp', 20025)
    assert "Tester Ownplayer: head 20025 is not one of the game's created heads" in verify.verify(A.f.build(),
                                                                                              Roster(old))[0]


def test_a_created_head_is_never_a_set_head(built, data):
    R = Roster(built.data)
    makar = find(R, 'Cale Makar')
    res = pipeline.build(built.data, data, steps=[],
                         my_edits={edits.who_of(R.P, makar): {'label': 'Cale Makar', 'set': {'head': 20500}}})
    assert res.ok
    assert Roster(res.data).P.get(find(Roster(res.data), 'Cale Makar'), 'DaPp') == R.P.get(makar, 'DaPp')
    assert any(r[1] == 'edit skipped' and 'created head' in r[3] for r in res.log)
