"""seasonsave: a made-up Season / Be a GM save (no game data) read back as calendar, records and standings."""
import datetime
import os
import struct

import pytest

from legacy_roster import seasonsave as ss
from legacy_roster import tdb
from legacy_roster.sfo import FMT_STRING, Sfo

# key: (slot, league, abbr, division, conference)
TEAMS = [(0, 0, 'ANA', 3, 1), (30, 0, 'SEA', 3, 1), (2, 0, 'BOS', 5, 2), (31, 0, 'VGK', 3, 1),
         (220, 15, 'EAS', 2, 2), (221, 15, 'WES', 1, 1), (32, 1, 'UTI', 11, 9), (234, 1, 'CV', 13, 8)]
PAIRS = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
# the first two rounds of PAIRS (the second with home and away swapped): (home goals, away goals, 'OT' / 'SO' / None)
SCORES = [(3, 2, None), (1, 2, 'OT'), (4, 3, 'SO'), (5, 0, None), (2, 4, None), (3, 1, None),
          (1, 4, None), (2, 3, 'SO'), (0, 1, None), (2, 3, 'OT'), (3, 2, None), (2, 5, None)]
FARM_SCORES = [(2, 1, None), (3, 0, None), (1, 4, None), (2, 3, 'OT')]
TODAY = datetime.date(2026, 10, 13)


def _table(tag, fields, rows, room):
    """A table of `fields` [(tag, bits, is_text)] holding `rows` [{tag: value}]."""
    defs, offset = b'', 0
    for name, bits, text in fields:
        defs += struct.pack('>II4sI', 0 if text else 3, offset, name.encode(), bits)
        offset += bits
    rec_len = (offset + 31) // 32 * 4
    header = bytearray(0x28)
    struct.pack_into('>I', header, 8, rec_len)
    struct.pack_into('>HH', header, 0x14, room, 0)
    header[0x1C] = len(fields)
    t = tdb.Table(tag, bytes(header) + defs + bytes(room * rec_len))
    for r in rows:
        t.add_record(r)
    return t


def _date(d):
    return {ss.ROW['month']: d.month - 1, ss.ROW['day']: d.day - 1}


def league(states=None):
    """(tables, games): the made-up league's tables and its schedule as (index, date, league, round, status, home key,
    away key, score)."""
    games = []
    for rnd in range(4):
        for n, (h, a) in enumerate(PAIRS):
            k = len(games)
            games.append((k, datetime.date(2026, 10, 1) + datetime.timedelta(k), 0, ss.SEASON, 0,
                          *((h, a) if rnd % 2 == 0 else (a, h)), SCORES[k] if k < len(SCORES) else None))
    games.append((len(games), datetime.date(2026, 9, 25), 0, ss.PRESEASON, 0, 2, 0, (3, 2, None)))
    games.append((len(games), datetime.date(2027, 2, 6), 0, ss.SEASON, 0, 4, 5, None))
    for n in range(10):
        k = len(games)
        games.append((k, datetime.date(2026, 10, 2) + datetime.timedelta(n), 1, ss.SEASON, 0,
                      *((6, 7) if n % 2 == 0 else (7, 6)), FARM_SCORES[n] if n < len(FARM_SCORES) else None))
    games.append((len(games), datetime.date(2027, 4, 20), 0, 1, 0, 0, 1, (2, 1, 'OT')))
    games.append((len(games), datetime.date(2027, 4, 22), 0, 1, ss.NOT_NEEDED, 1, 0, None))

    R, S, T, Z = ss.ROW, ss.SCORE, ss.TEAM, ss.STATE
    schedule = _table(ss.SCHEDULE, [(R['round'], 3, 0), (R['status'], 2, 0), (R['day'], 5, 0), (R['league'], 3, 0),
                                    (R['month'], 4, 0), (R['index'], 12, 0), (R['home'], 7, 0), (R['away'], 7, 0)],
                      [dict(_date(d), **{R['index']: k, R['league']: lg, R['round']: rnd, R['status']: st,
                                         R['home']: h, R['away']: a})
                       for k, d, lg, rnd, st, h, a, _ in games], 100)
    played = _table(ss.PLAYED, [(S['index'], 12, 0), (S['home'], 7, 0), (S['away'], 7, 0), (S['ot'], 1, 0),
                                (S['so'], 1, 0)],
                    [{S['index']: k, S['home']: sc[0], S['away']: sc[1], S['ot']: int(sc[2] is not None),
                      S['so']: int(sc[2] == 'SO')} for k, *_, sc in games if sc], 100)
    teams = _table(ss.TEAMS, [(T['abbr'], 40, 1), (T['name'], 64, 1), (T['slot'], 8, 0), (T['league'], 4, 0),
                              (T['division'], 6, 0), (T['conference'], 6, 0)],
                   [{T['abbr']: ab, T['name']: ab.title(), T['slot']: slot, T['league']: lg, T['division']: div,
                     T['conference']: conf} for slot, lg, ab, div, conf in TEAMS], 16)
    if states is None:
        states = {(0, ss.TODAY): (TODAY - ss.EPOCH).days, (0, ss.HUMAN_MASK): 1 << 1, (0, ss.HUMAN): 1,
                  (1, ss.HUMAN): 7, (0, ss.YEAR): 2015}
    state = _table(ss.STATES, [(Z['type'], 8, 0), (Z['tier'], 3, 0), (Z['value'], 32, 0)],
                   [{Z['tier']: tier, Z['type']: kind, Z['value']: v} for (tier, kind), v in states.items()], 50)
    return [schedule, played, teams, state], games


def save_bytes(tables, magic=b'PS3DynastyFile'):
    f = tdb.RosterFile.__new__(tdb.RosterFile)
    f.db_header, f.db_trailer = bytearray(b'DB' + bytes(0x16)), b''
    f.order, f.tables = [t.name for t in tables], {t.name: t for t in tables}
    db = f.build_db()
    return tdb.RosterFile.from_db(db, len(db) + 64, magic=magic, version=5).build()


def write_save(savedata, folder, raw, name, chunk=512, when=None):
    path = os.path.join(savedata, folder)
    os.makedirs(path)
    for n in range(0, len(raw), chunk):
        with open(os.path.join(path, f"DATA{n // chunk:04d}"), 'wb') as f:
            f.write(raw[n:n + chunk])
    Sfo.new([('SUB_TITLE', FMT_STRING, name.encode() + b'\0', 128)]).save(os.path.join(path, 'PARAM.SFO'))
    if when is not None:
        for p in os.listdir(path):
            os.utime(os.path.join(path, p), (when, when))
    return path


def later(path):
    return max(os.path.getmtime(os.path.join(path, p)) for p in os.listdir(path)) + 60


@pytest.fixture
def gm(tmp_path):
    tables, _ = league()
    path = write_save(str(tmp_path), 'BLES021530105', save_bytes(tables), 'BE A GM6')
    return ss.read(path, now=later(path))


def test_finds_season_and_gm_saves_newest_first_and_nothing_else(tmp_path):
    tables, _ = league()
    raw = save_bytes(tables)
    write_save(str(tmp_path), 'BLES021530105', raw, 'BE A GM6', when=1_700_000_000)
    write_save(str(tmp_path), 'BLUS315401000A', save_bytes(tables, b'PS3SeasonFile'), 'AUTOSAVE1', when=1_700_000_500)
    write_save(str(tmp_path), 'BLES021530502', b'PS3BeAProFile'.ljust(0x40, b'\0'), 'PRO1')     # Be a Pro
    write_save(str(tmp_path), 'BLES021530203', raw, 'ROSTER')                                    # a roster's number
    os.makedirs(tmp_path / 'BLES021530106')                                                    # no files
    found = ss.find(str(tmp_path))
    assert [(s.folder, s.kind, s.name, s.autosave) for s in found] == [
        ('BLUS315401000A', 'season', 'AUTOSAVE1', True), ('BLES021530105', 'gm', 'BE A GM6', False)]
    assert [s.folder for s in ss.find(str(tmp_path), title_ids=('BLES02153',))] == ['BLES021530105']
    assert found[1].mode == 'Be a GM' and len(found[1].files) > 1
    assert ss.find(str(tmp_path / 'missing')) == []


def test_today_season_and_the_players_teams(gm):
    assert gm.kind == 'gm' and gm.save.name == 'BE A GM6'
    assert gm.today == TODAY and gm.first_year == 2026 and gm.number == 1
    assert gm.human == 30 and gm.farm == 234
    assert gm.team(30).abbr == 'SEA' and gm.team(30).key == 1


def test_games_carry_slots_dates_scores_and_overtime(gm):
    by_index = {g.index: g for g in gm.games}
    assert len(gm.games) == 24 + 2 + 10 + 2
    first = by_index[0]
    assert (first.date, first.home, first.away, first.score, first.extra) == (datetime.date(2026, 10, 1), 0, 30, (3, 2),
                                                                             None)
    assert (by_index[2].score, by_index[2].extra) == ((4, 3), 'SO')
    assert not by_index[12].played and by_index[12].score is None
    playoff, spare = by_index[36], by_index[37]
    assert playoff.playoffs and playoff.date == datetime.date(2027, 4, 20) and playoff.extra == 'OT'
    assert spare.status == ss.NOT_NEEDED and not spare.played
    assert by_index[25].home == 220 and by_index[25].date == datetime.date(2027, 2, 6)


def test_results_keyed_by_date_and_slots(gm):
    nhl = gm.results(ss.NHL)
    assert nhl[('2026-10-01', 0, 30)] == (3, 2, None)
    assert nhl[('2026-10-02', 0, 2)] == (1, 2, 'OT')
    assert nhl[('2026-09-25', 2, 0)] == (3, 2, None)                     # the preseason
    assert nhl[('2027-04-20', 0, 30)] == (2, 1, 'OT')                    # the playoffs
    assert len(nhl) == 12 + 1 + 1 and len(gm.results()) == len(nhl) + 4
    older = gm.results(ss.NHL, first_year=2015)
    assert older[('2015-10-01', 0, 30)] == (3, 2, None) and ('2016-04-20', 0, 30) in older


def test_records_count_overtime_and_shootouts_as_the_game_does(gm):
    recs = gm.records()
    assert set(recs) == {0, 30, 2, 31}                                  # not the All-Star teams, not the farm
    ana = recs[0]
    assert (ana.w, ana.otw, ana.sow, ana.l, ana.otl, ana.sol) == (3, 0, 2, 0, 1, 0)
    assert (ana.gp, ana.points, ana.text(), ana.gf, ana.ga) == (6, 11, '5-0-1', 14, 10)
    assert ana.as_dict()['home'] == '2-0-1' and ana.as_dict()['away'] == '3-0-0'
    assert ana.streak() == 'W4' and ana.as_dict()['last10'] == '5-0-1'
    bos = recs[2]
    assert (bos.text(), bos.points, bos.gf, bos.ga) == ('3-1-2', 8, 14, 14)
    assert sum(r.gf for r in recs.values()) == sum(r.ga for r in recs.values()) == 56
    assert all(r.points == 2 * r.wins + r.ot_losses for r in recs.values())
    farm = gm.records(ss.FARM)
    assert farm[32].text() == '2-2-0' and farm[234].text() == '2-1-1' and farm[234].points == 5


def test_standings_by_division(gm):
    table = gm.standings()
    assert [(g['conference'], g['division']) for g in table] == [('Western', 'Pacific'), ('Eastern', 'Atlantic')]
    assert [(r['abbr'], r['pts'], r['place']) for r in table[0]['rows']] == [('ANA', 11, 1), ('VGK', 5, 2),
                                                                             ('SEA', 4, 3)]
    assert gm.place(30) == (3, 'Pacific') and gm.place(2) == (1, 'Atlantic') and gm.place(220) is None
    assert gm.record(30).text() == '2-4-0'


def test_the_mask_names_the_team_when_the_key_is_missing(tmp_path):
    tables, _ = league({(0, ss.TODAY): (TODAY - ss.EPOCH).days, (0, ss.HUMAN_MASK): 1 << 3, (0, ss.YEAR): 2016})
    path = write_save(str(tmp_path), 'BLES021531003', save_bytes(tables, b'PS3SeasonFile'), 'SEASON4')
    season = ss.read(path, now=later(path))
    assert season.kind == 'season' and season.mode == 'Season'
    assert season.human == 31 and season.farm is None and season.number == 2


def test_a_save_being_written_or_damaged_is_refused(tmp_path):
    tables, _ = league()
    raw = save_bytes(tables)
    path = write_save(str(tmp_path), 'BLES021530105', raw, 'BE A GM6')
    with pytest.raises(ss.SeasonError, match='still saving'):
        ss.read(path, now=later(path) - 60)
    bad = bytearray(raw)
    bad[0x40] ^= 0xFF
    other = write_save(str(tmp_path), 'BLES021530107', bytes(bad), 'BE A GM8')
    with pytest.raises(ss.SeasonError, match='damaged'):
        ss.read(other, now=later(other))
    with pytest.raises(ss.SeasonError, match='not a Season'):
        ss.database(b'PS3RosterFile'.ljust(0x40, b'\0'))
    with pytest.raises(ss.SeasonError, match='not a Season'):
        ss.read(str(tmp_path / 'BLES021530202'))


def test_reading_writes_nothing(tmp_path):
    tables, _ = league()
    path = write_save(str(tmp_path), 'BLES021530105', save_bytes(tables), 'BE A GM6', when=1_700_000_000)

    def snapshot():
        return {n: (os.path.getmtime(os.path.join(path, n)), open(os.path.join(path, n), 'rb').read())
                for n in sorted(os.listdir(path))}

    before = snapshot()
    ss.read(ss.find(str(tmp_path))[0], now=later(path))
    assert snapshot() == before and sorted(os.listdir(tmp_path)) == ['BLES021530105']
