"""The lines the Czech Extraliga's clubs play, from hokej.cz's own match pages (data pack part `extraliga_lines`, 0.51.0;
owner, 2026-10-24: Extraliga is a focus for the Czech players).

The match page's line-up ("Rozestavení", hokej.cz/zapas/<id>/roster) is filled from a public file: the day's match list
`json.esports.cz/hokejcz/scoreboard/onlajny/<date>.json` (league "16" = Extraliga; each match: both clubs and their
`onlajny_id`) and one roster file per match `data.onlajny.com/hockey/roster/<year>/<onlajny_id>.json`. In `rosters` home /
guest hold the players by slot code: 101 / 102 the goalies, 211-242 the defence pairs 1-4 (left, right), 311-343 the forward
lines 1-4 (three each: left wing, centre, right wing). The lines show shortly before the game ("hasRoster"), so a club's
newest game with a line-up is its current lines. hokej.cz's robots.txt allows everything; the files are unofficial and
undocumented: a day or a club that fails is left to the other source (a larger database's lines, the rating deal).
Output: {club slot (str): {'date', 'game', 'slots': {slot name (schema.SLOT_TAG): [first, last, birth year]}}}.
"""
import datetime
import json
import os
import re
import time
from collections import Counter
import unicodedata

from legacy_roster import datasource

DAYS = "https://json.esports.cz/hokejcz/scoreboard/onlajny/{date}.json"
ROSTER = "https://s3-eu-west-1.amazonaws.com/data.onlajny.com/hockey/roster/{year}/{game}.json"
LEAGUE = '16'                   # Extraliga in the day files
BACK = 14                       # days looked back for a club's newest line-up
SLOTS = {'g1': '101', 'g2': '102'}
for _n in (1, 2, 3, 4):
    for _k, _spot in enumerate(('lw', 'c', 'rw'), 1):
        SLOTS[f"l{_n}{_spot}"] = f"3{_n}{_k}"           # forward line n: 311-313, 321-323, 331-333, 341-343
for _n in (1, 2, 3):
    SLOTS[f"l{_n}ld"], SLOTS[f"l{_n}rd"] = f"2{_n}1", f"2{_n}2"   # pair n: 211/212, 221/222, 231/232


def plain(text):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode().lower())


def club_slots(slots_file):
    """{plain club name or short code: slot} of the Extraliga clubs from tools/club_slots.json."""
    with open(slots_file, encoding='utf-8') as f:
        clubs = json.load(f)['extraliga']['slots']
    out = {}
    for slot, c in clubs.items():
        for word in (c['full'], c['short'], c['abbr']):
            out.setdefault(plain(word), slot)
    return out


def club_of(team, known):
    """The slot of a day file's club (its name, short name or shortcut)."""
    for word in (team.get('name'), team.get('short_name'), team.get('shortcut')):
        if plain(word) in known:
            return known[plain(word)]
    full = plain(team.get('name'))                     # "Banes Motor České Budějovice" ends in the club's own name
    return next((slot for key, slot in sorted(known.items(), key=lambda kv: -len(kv[0]))
                 if len(key) >= 8 and full.endswith(key)), None)


def lines_of(side):
    """{slot name: [first, last, birth year]} of one side of a roster file; a place without a player is left out."""
    out = {}
    for name, code in SLOTS.items():
        p = side.get(code)
        if p and p.get('name') and p.get('surname') and (p.get('birth_date') or {}).get('date'):
            out[name] = [p['name'].strip(), p['surname'].strip(), int(p['birth_date']['date'][:4])]
    return out


def lines(season_year, slots_file, today=None, log=print):
    """{club slot: {'date', 'game', 'games', 'slots'}}: each club's newest line-up of the last `BACK` days (and today's, out
    in the morning). The first goalie is the one who started most of those games (a game's own starter is only a rotation)."""
    known = club_slots(slots_file)
    today = today or datetime.date.today()
    seen = {}                                          # club slot -> [(date, game id, slots)] newest first
    for back in range(-1, BACK):
        day = today - datetime.timedelta(days=back)
        try:
            data = datasource.http_json(DAYS.format(date=day.isoformat()))
        except Exception as err:
            log(f"lines (extraliga): {day}: {err}")
            continue
        for m in (data.get(LEAGUE) or {}).get('matches', []):
            try:
                game = datasource.http_json(ROSTER.format(year=season_year, game=m['onlajny_id']))
            except Exception as err:                     # a game whose file is not there yet (404) is no news
                if '404' not in str(err):
                    log(f"lines (extraliga): game {m.get('onlajny_id')}: {err}")
                continue
            time.sleep(0.3)
            if not game.get('hasRoster'):
                continue
            for side, team in (('home', m.get('home') or {}), ('guest', m.get('visitor') or {})):
                slot, got = club_of(team, known), lines_of((game.get('rosters') or {}).get(side) or {})
                if slot and len(got) >= 18:
                    seen.setdefault(slot, []).append((day.isoformat(), m['onlajny_id'], got))
    out = {}
    for slot, games in seen.items():
        games.sort(key=lambda g: g[0], reverse=True)
        date, game, got = games[0]
        got = dict(got)
        starts = Counter(tuple(g[2]['g1']) for g in games if 'g1' in g[2])
        if starts and 'g1' in got and 'g2' in got:
            top = starts.most_common(1)[0][0]
            if top == tuple(got['g2']):                 # today's backup is the usual first goalie
                got['g1'], got['g2'] = got['g2'], got['g1']
        out[slot] = {'date': date, 'game': game, 'games': len(games), 'slots': got}
    log(f"lines (extraliga): {len(out)} of {len(set(known.values()))} clubs")
    return out


CATEGORIES = {'l': 18, 'g': 2}         # slot-name prefix: how many slots a whole category has (the match pages give no special teams)


def merge(base, extraliga):
    """{club slot: {'date', 'source', 'slots'}}: the base lines (a larger database's, per club slot) with the Extraliga
    clubs' own match line-ups over their even-strength lines and goalies where the match page gave all of them; the rest
    (power play, penalty kill) stays the base's."""
    out = {}
    for slot in sorted(set(base) | set(extraliga), key=int):
        mine, theirs = base.get(slot) or {}, extraliga.get(slot) or {}
        slots, source = dict(mine.get('slots') or {}), ['database'] if mine.get('slots') else []
        for prefix, size in CATEGORIES.items():
            got = {k: v for k, v in (theirs.get('slots') or {}).items() if k.startswith(prefix)}
            if len(got) == size:
                slots = {k: v for k, v in slots.items() if not k.startswith(prefix)}
                slots.update(got)
                source.append(f"{prefix}:match")
        out[slot] = {'date': theirs.get('date') or mine.get('date') or '', 'source': ' '.join(source), 'slots': slots}
    return out
