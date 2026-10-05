"""NHL.com facts kept in the data pack, so the players' PCs never ask for them: last season's
players and the draft.

  * last_season(): everyone who played in the NHL's last regular season, with birthdate, size,
    hand and his team now (None: unsigned). Who played last season is not retired; who is
    unsigned now is a free agent (builder.settle_free_agents, builder.add_unsigned). Two
    requests to NHL.com's statistics, plus one per unsigned player for his photo.
  * drafts(): every pick of the drafts of the given years, one request per year (round, overall
    pick, team). Players are matched to their pick by name and age (draft.py).
"""
import time
import urllib.parse

from legacy_roster import datasource

BIOS = ("https://api.nhle.com/stats/rest/en/{kind}/bios?isAggregate=false&isGame=false&limit=-1&start=0"
        "&cayenneExp=")
DRAFT = "https://api-web.nhle.com/v1/draft/picks/{year}/all"
LANDING = datasource.NHL_API + "/player/{id}/landing"


def last_season(season_year, log=print):
    """[player] who played in the regular season before the one starting in `season_year`."""
    season = f"{season_year - 1}{season_year}"
    out = []
    for kind in ('skater', 'goalie'):
        url = BIOS.format(kind=kind) + urllib.parse.quote(f"gameTypeId=2 and seasonId={season}")
        for r in datasource.http_json(url).get('data', []):
            full, last = r.get('skaterFullName') or r.get('goalieFullName') or '', r.get('lastName') or ''
            if not r.get('birthDate') or not full.endswith(last):
                continue
            y, m, d = (int(x) for x in r['birthDate'].split('-'))
            out.append({'first': full[:len(full) - len(last)].strip(), 'last': last, 'birth': [y, m, d],
                        'pos': 'G' if kind == 'goalie' else r.get('positionCode'), 'team': r.get('currentTeamAbbrev'),
                        'gp': r.get('gamesPlayed') or 0, 'nhl_id': r.get('playerId'),
                        'shoots': r.get('shootsCatches'), 'height_in': r.get('height'), 'weight_lb': r.get('weight'),
                        'country': r.get('nationalityCode') or r.get('birthCountryCode'), 'city': r.get('birthCity'),
                        'photo': None})
    unsigned = [p for p in out if not p['team']]
    for k, p in enumerate(unsigned):
        try:
            land = datasource.http_json(LANDING.format(id=p['nhl_id']))
        except Exception as err:            # no photo then; the player is still listed
            log(f"last season: no details for {p['first']} {p['last']}: {err}")
            continue
        p['photo'] = land.get('headshot') or None
        p['first'] = (land.get('firstName') or {}).get('default') or p['first']
        time.sleep(0.1)
    log(f"last season {season}: {len(out)} players, {len(unsigned)} of them unsigned now")
    return sorted(out, key=lambda p: p['nhl_id'] or 0)


def drafts(first_year, last_year, log=print):
    """[[first, last, position, year, round, overall pick, team code]] of every pick from
    `first_year` to `last_year`."""
    out = []
    for year in range(first_year, last_year + 1):
        picks = datasource.http_json(DRAFT.format(year=year)).get('picks', [])
        for p in picks:
            first, last = (p.get('firstName') or {}).get('default'), (p.get('lastName') or {}).get('default')
            if first and last and p.get('round') and p.get('overallPick'):
                out.append([first, last, p.get('positionCode'), year, p['round'], p['overallPick'], p.get('teamAbbrev')])
        time.sleep(0.3)
    log(f"drafts {first_year}-{last_year}: {len(out)} picks")
    return out
