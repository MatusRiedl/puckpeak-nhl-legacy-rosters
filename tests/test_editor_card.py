"""The Roster editor's card without a window (editor/card.py)."""
from legacy_roster.editor import card as C
from legacy_roster.editor import model

LABELS = ('Faceoffs', 'Shot power')
CUR = {'Faceoffs': 35, 'Shot power': 88}
CHOICES = {model.FREE_AGENTS: "Free agents", 3: "NHL · Boston Bruins"}


def typed(**changes):
    values = {'first': 'Jacob', 'last': 'Trouba', 'num': '65', 'pos': 'D', 'shoots': 'R', 'birth': '1994-02-26',
              'country': 'USA', 'height': '191', 'weight': '98', 'team': 3, 'ovr': '81',
              'ratings': {'Faceoffs': '35', 'Shot power': '88'}}
    values.update(changes)
    return values


def player():
    p = model.Player()
    p.who, p.first, p.last, p.num, p.pos, p.shoots = 'jacob|trouba|1994-02-26', 'Jacob', 'Trouba', 65, 'D', 'R'
    p.birth, p.country, p.height_in, p.weight_lb = (1994, 2, 26), 'USA', 75, 216
    p.teams, p.ratings, p.ovr = [3], {'Faceoffs': 35, 'Shot power': 88}, 81
    return p


def test_a_rating_the_game_has_below_40_is_kept_when_not_typed_over():
    values, problem = C.read(typed(), LABELS, False, CHOICES, {'Faceoffs': 35, 'Shot power': 88})
    assert problem is None and values['ratings'] == {'Faceoffs': 35, 'Shot power': 88}
    _values, problem = C.read(typed(ratings={'Faceoffs': '36'}), LABELS, False, CHOICES, {'Faceoffs': 35})
    assert problem == "Faceoffs: ratings go from 40 to 99."


def test_the_card_says_what_is_wrong():
    assert C.read(typed(first=' '), LABELS, False, CHOICES, CUR)[1] == "A player needs a first and a last name."
    assert C.read(typed(num='100'), LABELS, False, CHOICES, CUR)[1] == "The number must be between 1 and 99."
    assert C.read(typed(birth='26.2.1994'), LABELS, False, CHOICES, CUR)[1].startswith("Write the birthdate")
    assert C.read(typed(country='XXX'), LABELS, False, CHOICES, CUR)[1].startswith("The game has no country XXX")
    assert C.read(typed(height='tall'), LABELS, False, CHOICES, CUR)[1] == "Height and weight are whole numbers (cm, kg)."
    assert C.read(typed(team=99), LABELS, False, CHOICES, CUR)[1] == "Pick the team from the list."
    assert C.read(typed(ovr='', ratings={}), LABELS, True, CHOICES)[1] == "Give the new player an overall (40-99)."
    assert C.read(typed(team='FA'), LABELS, False, CHOICES, CUR)[0]['team'] == 'FA'
    assert C.read(typed(team='3'), LABELS, False, CHOICES, CUR)[0]['team'] == 3


def test_an_unchanged_card_is_no_edit_and_a_changed_one_names_only_the_change():
    p = player()
    values, _ = C.read(typed(), LABELS, False, CHOICES, p.ratings)
    assert C.player_edit(p, values) == ({'label': 'Jacob Trouba', 'set': {}}, False)
    values, _ = C.read(typed(num='12', team='FA', ratings={'Faceoffs': '35', 'Shot power': '90'}), LABELS, False,
                       CHOICES, p.ratings)
    edit, real = C.player_edit(p, values)
    assert real and edit == {'label': 'Jacob Trouba', 'set': {'num': 12}, 'ratings': {'Shot power': 90}, 'team': 'FA'}


def test_a_rename_keeps_the_old_name_and_is_found_again():
    p = player()
    values, _ = C.read(typed(last='Troubaa'), LABELS, False, CHOICES, p.ratings)
    edit, real = C.player_edit(p, values)
    assert real and edit['was'] == {'first': 'Jacob', 'last': 'Trouba', 'birth': [1994, 2, 26]}
    renamed = C.renamed({p.who: edit})
    assert list(renamed.values()) == [p.who] and 'troubaa' in next(iter(renamed))
    assert C.renamed({p.who: edit}, only=set()) == {}


def test_a_new_player():
    values, _ = C.read(typed(first='Zed', last='Testman', ovr='70', ratings={}), LABELS, True, CHOICES)
    who, edit = C.new_player(values, 'file:x.png')
    assert edit['new'] and edit['ovr'] == 70 and edit['team'] == 3 and edit['photo'] == 'file:x.png'
    assert edit['set']['pos'] == 'D' and 'ratings' not in edit
    assert C.what_changed(edit)[0] == 'new player'


def test_change_notes():
    old, new = player(), player()
    new.ovr, new.num = 83, 12
    assert C.change_note(old, new, ['ovr', 'num', 'first', 'last']) == "OVR 81 → 83, #65 → 12, name"
    assert C.change_note(None, new, ['ovr']) == "changed"
