"""Integrity checks for a built roster.

Every rule here was found the hard way: breaking it either crashes the game in a menu or makes
it silently keep the previous roster. `verify()` compares the built roster with the roster it
was built from, so a flaw the source already had is not blamed on the update -- only what the
update made worse is reported.
"""
from collections import Counter

from . import layout as L
from .art.portraits import person_key
from .matching import match
from .roster import Roster
from .tdb import check_chain

FULL_LINEUP = list(range(32)) + list(range(133, 154))     # teams that must dress a legal 20
TEAM_FLAWS = ('slot twice', 'dressed', 'lineup', 'slots', 'too many', 'entry ids')   # keyed by team id


def contract_violations(R):
    """pid -> (name, team) for players whose contract team is a team they are not on."""
    U, P = R.U, R.P
    on = {}
    for i in range(U.cur_rec):
        on.setdefault(R.link_to_pid[U.get(i, 'TWSX')], set()).add(U.get(i, 'BSXd'))
    bad = {}
    for prow in range(P.cur_rec):
        b = P.get(prow, 'BSXd')
        if not b:
            continue
        t = b - 1
        teams = on.get(P.get(prow, 'zIBw'), set())
        same = {t, L.MIRROR_OF.get(t, t)} | set(L.MIRRORS.get(t, []))
        if not same & teams:
            bad[P.get(prow, 'zIBw')] = (R.name(prow), t)
    return bad


def multi_club(R):
    """pids on two different club teams (mirror copies count as one team)."""
    U = R.U
    club = L.CLUB | set(L.MIRROR_OF)
    teams = {}
    for i in range(U.cur_rec):
        t = U.get(i, 'BSXd')
        if t in club:
            teams.setdefault(R.link_to_pid[U.get(i, 'TWSX')], set()).add(L.MIRROR_OF.get(t, t))
    return {pid for pid, ts in teams.items() if len(ts) > 1}


def structure(R, full_lineup=FULL_LINEUP):
    """Structural flaws of a roster as {key: message}; keys do not depend on record order.

    Teams in `full_lineup` must be playable: 20 dressed with every line slot filled.
    Also returns per-team line-up facts for the report."""
    U, P, Q = R.U, R.P, R.Q
    flags = [n for n, f in U.fields.items() if f.bits == 1 and n != 'jZSh']
    out, teams = {}, {}
    by_team = {}
    for i in range(U.cur_rec):
        by_team.setdefault(U.get(i, 'BSXd'), []).append(i)
    pid = lambda i: R.link_to_pid[U.get(i, 'TWSX')]

    # lines: no slot held twice, dressed == holds a slot; playable teams dress a legal 20
    for t in range(R.T.cur_rec):
        ents = by_team.get(t, [])
        held = Counter(f for i in ents for f in flags if U.get(i, f))
        if any(v > 1 for v in held.values()):
            out[('slot twice', t)] = f"{R.team_name(t)}: a line slot is held by two players"
        for i in ents:
            if bool(U.get(i, 'jZSh')) != any(U.get(i, f) for f in flags):
                out[('dressed', t, pid(i))] = f"{R.team_name(t)}: {R.name(R.p_by_id[pid(i)])} dressed flag and line slots disagree"
        dressed = [i for i in ents if U.get(i, 'jZSh')]
        pos = Counter('CLRDG'[P.get(R.p_by_id[pid(i)], 'aljv')] for i in dressed)
        teams[t] = {'players': len(ents), 'dressed': len(dressed), 'slots': len(held), 'positions': dict(pos)}
        if t in full_lineup and ents:
            if len(dressed) != 20 or pos['G'] != 2 or pos['D'] < 6:
                mix = ", ".join(f"{pos[k]} {name}" for k, name in
                                (('C', 'C'), ('L', 'LW'), ('R', 'RW'), ('D', 'D'), ('G', 'G')) if pos[k])
                out[('lineup', t)] = (f"{R.team_name(t)} dresses {len(dressed)} players ({mix or 'none'}); "
                                      "the game needs 20 with 2 G and at least 6 D")
            elif len(held) != len(flags):
                out[('slots', t)] = f"{R.team_name(t)} has {len(held)} of {len(flags)} line slots filled"

    # mirrors identical to their primary team
    def sig(t):
        return {pid(i): tuple(U.get(i, f) for f in flags + ['jZSh', 'lcCm', 'tRVs']) for i in by_team.get(t, [])}
    for prim, ms in L.MIRRORS.items():
        for m in ms:
            if sig(prim) != sig(m):
                out[('mirror', m)] = f"{R.team_name(m)} (team {m}) is not an exact copy of {R.team_name(prim)}"

    # free agents are listed once, are not on NHL teams and carry no contract
    nhl_pids = {pid(i) for t in range(32) for i in by_team.get(t, [])}
    listed = Counter(R.link_to_pid.get(Q.get(k, 'TWSX')) for k in range(Q.cur_rec))
    for k in range(Q.cur_rec):
        p = R.link_to_pid.get(Q.get(k, 'TWSX'))
        prow = R.p_by_id.get(p)
        if prow is None:
            out[('fa link', Q.get(k, 'TWSX'))] = "a free-agent entry points at no player"
            continue
        if listed[p] > 1:
            out[('fa twice', p)] = f"free agent {R.name(prow)} is on the free-agent list twice"
        if p in nhl_pids:
            out[('fa on team', p)] = f"free agent {R.name(prow)} is also on an NHL team"
        if any(P.get(prow, f) for f in ('BSXd', 'GDhI', 'dhKk', 'IrlK', 'IzRv')):
            out[('fa contract', p)] = f"free agent {R.name(prow)} still has contract data"

    # draft: a pick has a year, a round and an overall pick; an undrafted player (255) none
    for prow in range(P.cur_rec):
        year, rnd, overall = P.get(prow, 'WzKY'), P.get(prow, 'Ujcc'), P.get(prow, 'WfTt')
        if (rnd > 0) != (overall > 0) or (rnd > 0 and year == 255) or (year == 255 and P.get(prow, 'uWgv')):
            out[('draft', P.get(prow, 'zIBw'))] = (f"{R.name(prow)}: draft year {year}, round {rnd}, pick {overall} "
                                                   "do not fit together")

    # NHL teams: three letters (one captain at most), every player under contract
    for t in range(32):
        letters = Counter(U.get(i, 'lcCm') for i in by_team.get(t, []))
        if letters[1] + letters[2] != 3 or letters[1] > 1:
            out[('letters', t)] = f"{R.team_name(t)} has {letters[1]} captain(s) and {letters[2]} alternate(s)"
        for i in by_team.get(t, []):
            prow = R.p_by_id[pid(i)]
            if not P.get(prow, 'GDhI') or not P.get(prow, 'dhKk'):
                out[('no contract', pid(i))] = f"{R.name(prow)} ({R.team_name(t)}) has no contract"

    # roster entry ids: team * 40 + slot, slots 0..n-1 per team, at most 40 players per team
    for t, ents in by_team.items():
        ids = sorted(U.get(i, 'XWot') for i in ents)
        if len(ents) > L.MAX_PER_TEAM:
            out[('too many', t)] = f"{R.team_name(t)} has {len(ents)} players (the game allows {L.MAX_PER_TEAM})"
        elif ids != [t * L.MAX_PER_TEAM + k for k in range(len(ents))]:
            out[('entry ids', t)] = f"{R.team_name(t)}: roster entry ids are not consecutive"
    return out, teams


def verify(built, source, nhl_players=None, rebuilt=(), edited=None, league_moves=()):
    """Check `built` (bytes of a SYS-DATA) against `source` (the Roster it was built from).

    `nhl_players`: the official rosters the build used; when given, every listed player must be
    on exactly his NHL team. `rebuilt`: club teams the build filled from scratch; they must be
    fully playable whatever the source had in those slots. `edited`: (player keys, player rows)
    the player's own edits changed on purpose; only the official-roster check lets them differ.
    `league_moves`: team slots allowed to change league (only the in-game league test, lab.py).
    Returns (problems, info); the save must not be used if there are problems."""
    edited_keys, edited_rows = edited or (set(), set())
    rebuilt = set(rebuilt)
    try:
        problems = list(check_chain(built))
        R = Roster(built)      # re-parses: section, DB and table CRCs checked on load
    except Exception as err:   # not even readable: nothing else can be checked
        return [f"the save cannot be read back: {err}"], {}
    U, P, T = R.U, R.P, R.T

    # hard limits of the game: no new teams, no team changes league
    if T.cur_rec != source.T.cur_rec:
        problems.append(f"team count changed from {source.T.cur_rec} to {T.cur_rec}")
    else:
        for t in range(T.cur_rec):
            if T.get(t, 'jjMx') != source.T.get(t, 'jjMx') and t not in league_moves:
                problems.append(f"{R.team_name(t)} changed league")

    # every link resolves to a player, every roster entry id is unique
    for i in range(U.cur_rec):
        if R.link_to_pid.get(U.get(i, 'TWSX')) not in R.p_by_id:
            problems.append(f"roster entry {i} points at no player")
    xw = U.column('XWot')
    if len(set(xw)) != len(xw):
        problems.append("duplicate roster entry ids")
    if problems:   # the checks below assume resolvable links
        return problems, {}

    # official rosters: each player exactly on his team among the 32 primary slots
    if nhl_players:
        api = match(R, [dict(p) for p in nhl_players
                        if person_key(p['first'], p['last'], p['birth']) not in edited_keys])
        for p in api:
            if p['row'] in edited_rows:
                continue
            if p['row'] is None:
                problems.append(f"not found: {p['first']} {p['last']}")
                continue
            slots = [t for _, t in R.teams_of(p['row']) if t < 32]
            if slots != [L.API_TO_SLOT[p['team']]]:
                problems.append(f"{p['first']} {p['last']} on {slots}, expected {L.API_TO_SLOT[p['team']]}")
        api_rows = {p['row'] for p in api}
        for t in range(32):
            for _, prow, name, _, _ in R.team_roster(t):
                if prow not in api_rows and prow not in edited_rows:
                    problems.append(f"{name} still on {L.SLOT_TO_API[t]}")

    now, teams = structure(R, set(FULL_LINEUP) | rebuilt)
    before, teams_before = structure(source)
    problems += [msg for key, msg in now.items()
                 if key not in before or (key[0] in TEAM_FLAWS and key[1] in rebuilt)]

    # contracts: cPbu.team = team + 1 must point at a team the player is on (mirror slots count)
    baseline = contract_violations(source)
    for p, (name, t) in contract_violations(R).items():
        if p not in baseline:
            problems.append(f"{name} contracted to team {t} but not on it")
    # nobody on two different club teams
    for p in multi_club(R) - multi_club(source):
        problems.append(f"{R.name(R.p_by_id[p])} is on two club teams")

    # not fatal, but worth telling the user: AHL teams that lost players and cannot ice a full line-up
    # (when the AHL step did not rebuild them)
    thinner = [f"{R.team_name(t)} ({teams[t]['players']} players, was {teams_before[t]['players']})"
               for t in sorted(L.AHL) if t not in rebuilt and teams[t]['players'] < min(teams_before[t]['players'], 20)]
    info = {'entries': U.cur_rec, 'players': P.cur_rec, 'free_agents': R.Q.cur_rec,
            'known_flaws_in_source': len(before), 'thinner_ahl_teams': thinner, 'rebuilt_teams': sorted(rebuilt),
            'empty_national_teams': [R.team_name(t) for t in range(133, 154) if not teams[t]['players']],
            'teams': teams}
    return problems, info
