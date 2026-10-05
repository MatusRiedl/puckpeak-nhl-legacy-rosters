"""Real draft data (draft.py): every player gets his own pick, a junior his draft year, nobody
another person's pick."""
from legacy_roster import draft

PICKS = [['Will', 'Smith', 'C', 2023, 1, 4, 'SJS'],
         ['Sebastian', 'Aho', 'C', 2015, 2, 35, 'CAR'],      # the Finn
         ['Sebastian', 'Aho', 'D', 2017, 5, 139, 'NYI'],     # the Swede
         ['Cody', 'Glass', 'C', 2017, 1, 6, 'VGK'],          # Vegas is slot 31: five bits cannot hold 32
         ['Evander', 'Kane', 'C', 2009, 1, 4, 'ATL']]        # Atlanta's picks are Winnipeg's now
WIDTH = {'WzKY': 8, 'Ujcc': 4, 'WfTt': 9, 'uWgv': 5}


class Field:
    def __init__(self, bits):
        self.mask = (1 << bits) - 1


class Table:
    """Just enough of a player table: rows of {field: value}."""

    def __init__(self, rows):
        self.rows = rows
        self.cur_rec = len(rows)

    def get(self, i, f):
        return self.rows[i][f]

    def set(self, i, f, v):
        self.rows[i][f] = v

    def field(self, f):
        return Field(WIDTH[f])


class Roster:
    def __init__(self, rows):
        self.P = Table(rows)


def player(first, last, born, pos=0, month=6, day=1, draft_=(255, 0, 0, 0)):
    """A record: born in `born` (this program's year - 1910), position 0-4, a draft as stored."""
    return {'PedH': first, 'RMbQ': last, 'dnFq': born - 1910, 'pLKJ': month - 1, 'iwsK': day - 1, 'aljv': pos,
            'rnOl': 0, **dict(zip(draft.FIELDS, draft_))}


def drafted(row):
    return tuple(row[f] for f in draft.FIELDS)


def test_every_player_gets_his_own_pick():
    rows = [player('Will', 'Smith', 2005), player('Sebastian', 'Aho', 1997), player('Sebastian', 'Aho', 1996, pos=3),
            player('Cody', 'Glass', 1999), player('Evander', 'Kane', 1991)]
    assert draft.apply(Roster(rows), PICKS, 2026) == 5
    assert drafted(rows[0]) == (123, 1, 4, 26)             # 2023, round 1, 4th overall, San Jose (slot 25 + 1)
    assert drafted(rows[1]) == (115, 2, 35, 6)             # the Finn: 2015, Carolina
    assert drafted(rows[2]) == (117, 5, 139, 19)           # the Swede, a defenceman: 2017, the Islanders
    assert drafted(rows[3]) == (117, 1, 6, 0)              # Vegas cannot be written
    assert drafted(rows[4]) == (109, 1, 4, 2)              # Atlanta -> Winnipeg (slot 1)


def test_a_namesake_of_another_age_gets_no_pick():
    rows = [player('Will', 'Smith', 1996, pos=1)]          # the game's own roster's Moncton junior
    draft.apply(Roster(rows), PICKS, 2026)
    assert drafted(rows[0]) == (255, 0, 0, 0)


def test_a_junior_waits_for_his_draft():
    rows = [player('Young', 'Prospect', 2009, month=3), player('Late', 'Birthday', 2008, month=10)]
    draft.apply(Roster(rows), PICKS, 2026)
    assert drafted(rows[0]) == (127, 0, 0, 0)              # 18 in 2027: the 2027 draft, round 0 (EA's way)
    assert drafted(rows[1]) == (127, 0, 0, 0)              # 18 only after September 15, 2026


def test_another_persons_pick_goes_and_older_picks_stay():
    rows = [player('Ivan', 'Nobody', 1995, draft_=(113, 1, 2, 13)),   # a pick the real 2013 draft does not have
            player('Old', 'Timer', 1985, draft_=(103, 3, 80, 5))]      # before the drafts we know: left alone
    draft.apply(Roster(rows), PICKS, 2026)
    assert drafted(rows[0]) == (255, 0, 0, 0)
    assert drafted(rows[1]) == (103, 3, 80, 5)


def test_applying_twice_changes_nothing_more():
    rows = [player('Will', 'Smith', 2005), player('Young', 'Prospect', 2009, month=11), player('Ivan', 'Nobody', 1995)]
    draft.apply(Roster(rows), PICKS, 2026)
    assert draft.apply(Roster(rows), PICKS, 2026) == 0
