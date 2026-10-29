"""A fake lobby server that answers as the real one is meant to (the API in legacy_roster/lobby.py's docstring), for the
lobby client's and the Play online tab's tests. The host is the reference: a guest has the roster with the host's CRC and
plays with the host's patch (both need one: "none" cannot start); the game (region + version, "EU 01.00") must be the same; the RPCS3
build is only shown to the friend; the host's roster goes up gzipped and comes down the same.

The ranks and chat of 0.90 (Overtime.Lobby/Board.cs, LobbyStore.Say) answer with the same snake_case keys; `ranks = False` makes it
a server from before 0.90 (those routes 404 with no body, the lobby has no `chat`)."""
import json
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


class FakeServer:
    """In-memory lobbies: a host opens one and sends his roster, a guest joins by code, both Ready -> starting."""

    def __init__(self):
        self.lobbies = {}
        self.codes = ['KDMQRS', 'TWXYZA', 'BCDFGH', 'JKLMNP']          # handed out in turn
        self.calls = []
        self.fail_roster_download = False
        self.ranks = True              # False: a server from before 0.90
        self.players = {}              # name (lower) -> {name, rating, games, w, l, streak, peak, gf, ga}
        self.matches = {}              # name (lower) -> [history rows, newest first]
        self.hidden = set()
        self.said = {}                 # (code, name) -> time of the last chat line
        self.chat_gap = 0.7

    # ---- ranks (a tiny stand-in for MatchBook + Rating: +-16 a game, placing until 5) ------------------------------------

    TIERS = [('Minor League', 0), ('Rookie', 1000), ('Pro', 1100), ('Top 6', 1200), ('Alternate Captain', 1300),
             ('Captain', 1400), ('All-Star', 1500), ('Superstar', 1600), ('Hall of Fame', 1700)]

    def tier(self, p):
        if p['games'] < 5:
            return 'Unranked'
        return [n for n, low in self.TIERS if p['rating'] >= low][-1]

    def play(self, a, b, score_a, score_b, status='confirmed', team_a='MTL', team_b='TOR', at=None):
        """A match between `a` and `b` as the board would show it; waiting / disputed / voided rate nobody. Returns its id."""
        at = int(at or time.time())
        mid = f'B1/{sum(len(v) for v in self.matches.values()) // 2 + 1}'
        rated = status in ('confirmed', 'forfeit')
        for me, other, f, g, team, opp in ((a, b, score_a, score_b, team_a, team_b), (b, a, score_b, score_a, team_b, team_a)):
            p = self.players.setdefault(me.lower(), {'name': me, 'rating': 1000, 'games': 0, 'w': 0, 'l': 0, 'streak': 0,
                                                     'peak': 1000, 'gf': 0, 'ga': 0})
            won = f > g
            delta = (16 if won else -16) if rated else None
            if rated:
                p.update(rating=p['rating'] + delta, games=p['games'] + 1, w=p['w'] + won, l=p['l'] + (not won), gf=p['gf'] + f,
                         ga=p['ga'] + g, streak=(max(p['streak'], 0) + 1) if won else (min(p['streak'], 0) - 1))
                p['peak'] = max(p['peak'], p['rating'])
            self.matches.setdefault(me.lower(), []).insert(0, {
                'id': mid, 'at': at, 'status': status, 'why': None, 'opponent': other, 'team': team, 'opp_team': opp,
                'for': f, 'against': g, 'result': ('W' if won else 'L') if status != 'voided' else None, 'delta': delta,
                'waiting': status == 'waiting'})
        return mid

    def settle(self, name, mid, status='confirmed'):
        """The second report came: match `mid` of `name` (both sides) turns `status`."""
        for rows in self.matches.values():
            for r in rows:
                if r['id'] == mid:
                    r.update(status=status, waiting=False)

    def shown(self, name):
        return 'Hidden player' if name.lower() in self.hidden else name

    def card(self, p, own):
        tier = self.tier(p)
        names = [n for n, _ in self.TIERS]
        nxt = names[names.index(tier) + 1] if tier in names[:-1] else None
        ranked = sorted((q for q in self.players.values() if q['games'] >= 5), key=lambda q: -q['rating'])
        rank = next((i + 1 for i, q in enumerate(ranked) if q is p), None)
        return {'name': p['name'], 'rating': p['rating'], 'tier': tier, 'placing': max(0, 5 - p['games']), 'rank': rank,
                'of': len(ranked), 'w': p['w'], 'l': p['l'], 'streak': p['streak'], 'peak': p['peak'], 'delta7': 0, 'form': '',
                'gf': p['gf'], 'ga': p['ga'], 'curve': [], 'opponents': [], 'teams': [],
                'next_tier': nxt, 'next_at': dict(self.TIERS).get(nxt), 'hidden': p['name'].lower() in self.hidden and own}

    def board(self):
        rows = sorted(self.players.values(), key=lambda q: (q['games'] < 5, -q['rating']))
        players = [{'rank': i + 1 if p['games'] >= 5 else None, 'name': self.shown(p['name']), 'rating': p['rating'],
                    'tier': self.tier(p), 'placing': max(0, 5 - p['games']), 'games': p['games'], 'w': p['w'], 'l': p['l'],
                    'streak': p['streak'], 'peak': p['peak'], 'last': None, 'delta7': 0} for i, p in enumerate(rows)]
        return {'players': players, 'ranked': sum(p['games'] >= 5 for p in rows), 'highlights': [], 'recent': [],
                'tiers': [{'name': n, 'min': low, 'blurb': ''} for n, low in self.TIERS], 'placement': 5,
                'updated': int(time.time())}

    def own(self, name, token):
        return bool(token) and any(m['name'].lower() == str(name).lower() and m['token'] == token
                                   for lob in self.lobbies.values() for m in lob['members'])

    def ranks_route(self, method, parts, query, body, token):
        if parts == ['board'] and method == 'GET':
            return 200, self.board()
        if parts == ['board', 'player'] and method == 'GET':
            name = query.get('name', [''])[0]
            p, own = self.players.get(name.lower()), self.own(name, token)
            if p is None or (name.lower() in self.hidden and not own):
                return 404, {'error': 'unknown', 'message': 'No rated games yet.'}
            return 200, self.card(p, own)
        if parts == ['history'] and method == 'GET':
            name = query.get('name', [''])[0]
            if name.lower() not in self.matches or (name.lower() in self.hidden and not self.own(name, token)):
                return 404, {'error': 'unknown', 'message': 'No matches yet.'}
            rows = [dict(r, opponent=self.shown(r['opponent'])) for r in self.matches[name.lower()]]
            return 200, rows[:int(query.get('limit', ['20'])[0])]
        if parts == ['board', 'hide'] and method == 'POST':
            name = (body or {}).get('name') or ''
            if not 1 <= len(name) <= 64:
                return 400, {'error': 'bad_name', 'message': 'Give a name.'}
            if body.get('hidden'):
                self.hidden.add(name.lower())
            elif self.own(name, token):
                self.hidden.discard(name.lower())
            else:
                return 403, {'error': 'not_member', 'message': 'Only that player can show his name again (be in a lobby).'}
            return 200, {'name': name, 'hidden': bool(body.get('hidden'))}
        return None

    @staticmethod
    def host_of(lob):
        return next((m for m in lob['members'] if m['role'] == 'host'), None)

    def view(self, lob):
        host = self.host_of(lob)
        for m in lob['members']:
            m['roster_ok'] = m['role'] == 'host' or not host['crc'] or m['crc'] == host['crc']
            m['patch_ok'] = m['role'] == 'host' or m['patch'] == host['patch']
        reason = None
        if lob['state'] != 'expired' and len(lob['members']) == 2:
            guest = next(m for m in lob['members'] if m['role'] != 'host')
            if host['crc'] and lob['roster'] is None:
                reason = f"{host['name']}'s roster is still being sent."
            elif not guest['roster_ok']:
                reason = f"Your friend's roster is not on {guest['name']}'s PC yet."
            elif any(m['patch'] in ('', 'none') for m in (host, guest)):
                bare = next(m for m in (host, guest) if m['patch'] in ('', 'none'))
                reason = f"{bare['name']} has no game patch. Online play needs it: press Set up online in the app."
            elif not guest['patch_ok']:
                reason = (f"{host['name']} has game patch {host['patch']}, {guest['name']} has game patch {guest['patch']}. "
                          "Both need the same: update the program.")
        lob['reason'] = reason
        if lob['state'] == 'open' and len(lob['members']) == 2 and all(m['ready'] for m in lob['members']) and reason is None:
            lob['state'] = 'starting'
        roster = None if lob['roster'] is None or host is None else {'crc': host['crc'], 'size': len(lob['roster'])}
        view = {'code': lob['code'], 'state': lob['state'], 'reason': lob['reason'], 'roster': roster,
                'members': [{k: m[k] for k in ('name', 'role', 'roster_ok', 'patch_ok', 'ready', 'progress', 'patch', 'version', 'rpcs3')}
                            for m in lob['members']]}
        if self.ranks:
            view['chat'] = list(lob.setdefault('chat', []))
        return view

    def handle(self, method, path, body, token=None):
        """Returns (status, answer): the answer is a dict (JSON) or bytes (the roster). `token` is the X-Lobby-Token header: create
        and join hand one out, every later request of a member must carry his."""
        self.calls.append((method, path))
        parts = [p for p in path.split('?')[0].split('/') if p][1:]       # the first part is /api
        if parts[:1] in (['board'], ['history']):
            if not self.ranks:
                return 404, b''
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
            return self.ranks_route(method, parts, query, body, token) or (404, b'')
        if parts == ['lobbies'] and method == 'GET':
            return 200, [self.listed(lob) for lob in self.lobbies.values()
                         if lob['public'] and lob['state'] == 'open' and len(lob['members']) == 1 and lob['roster'] is not None]
        if parts == ['lobby'] and method == 'POST':
            code = self.codes[len(self.lobbies) % len(self.codes)]
            self.lobbies[code] = {'code': code, 'state': 'open', 'roster': None, 'members': [self.member(body, 'host')],
                                  'public': bool(body.get('is_public')), 'roster_name': body.get('roster_name') or ''}
            return 200, dict(self.view(self.lobbies[code]), token=self.lobbies[code]['members'][0]['token'])
        lob = self.lobbies.get(parts[1]) if len(parts) > 1 else None
        if lob is None:
            return 404, {'error': 'unknown', 'message': 'No lobby has that code.'}
        name = path.split('name=')[1] if 'name=' in path else (body or {}).get('name') if isinstance(body, dict) else None
        mine = next((m for m in lob['members'] if m['name'] == name), None)
        if lob['state'] == 'expired' and parts[2:] in ([], ['leave']):
            return (200, {}) if parts[2:] == ['leave'] else (200, self.view(lob))
        if parts[2:] == ['join'] and mine is None:
            if len(lob['members']) >= 2:
                return 409, {'error': 'full', 'message': 'That lobby is full.'}
            guest = self.member(body, 'guest')
            lob['members'].append(guest)
            return 200, dict(self.view(lob), token=guest['token'])
        if mine is None or not token or token != mine['token']:
            return 403, {'error': 'not_member', 'message': 'You are not in that lobby.'}
        if parts[2:] == ['join']:
            pass
        elif parts[2:] == ['say'] and method == 'POST':
            if not self.ranks:
                return 404, b''
            text = ' '.join(str(body.get('text') or '').split())[:140]
            if not text:
                return 400, {'error': 'empty', 'message': 'Type something first.'}
            now = time.monotonic()
            if now - self.said.get((lob['code'], mine['name']), -99) < self.chat_gap:
                return 429, {'error': 'slow_down', 'message': 'Wait a moment before the next line.'}
            self.said[(lob['code'], mine['name'])] = now
            chat = lob.setdefault('chat', [])
            chat.append({'seq': (chat[-1]['seq'] if chat else 0) + 1, 'name': mine['name'], 'text': text, 'at': int(time.time())})
            del chat[:-30]
        elif parts[2:] == ['ready']:
            next(m for m in lob['members'] if m['name'] == body['name'])['ready'] = body['ready']
        elif parts[2:] == ['me']:
            me = next(m for m in lob['members'] if m['name'] == body['name'])
            me.update(crc=body['crc'], patch=body['patch'], version=body['version'], rpcs3=body.get('rpcs3', ''), ready=False)
            lob['state'] = 'open'
        elif parts[2:] == ['roster'] and method == 'PUT':
            if not any(m['name'] == name and m['role'] == 'host' for m in lob['members']):
                return 403, {'error': 'not_host', 'message': 'Only the host sends the roster.'}
            lob['roster'] = body
        elif parts[2:] == ['roster'] and method == 'GET':
            if lob['roster'] is None or self.fail_roster_download:
                return 404, {'error': 'no_roster', 'message': 'The host has not sent the roster yet.'}
            return 200, lob['roster']
        elif parts[2:] == ['leave']:
            gone = next((m for m in lob['members'] if m['name'] == body['name']), None)
            lob['members'] = [m for m in lob['members'] if m['name'] != body['name']]
            if gone is not None and gone['role'] == 'host':
                lob.update(state='expired', members=[], roster=None)
            else:
                for m in lob['members']:
                    m['ready'] = False
                lob['state'] = 'open'
            return 200, {}
        return 200, self.view(lob)

    def listed(self, lob):
        host = self.host_of(lob)
        return {'code': lob['code'], 'host': host['name'], 'roster_name': lob['roster_name'], 'patch': host['patch'],
                'version': host['version'], 'roster_size': len(lob['roster']), 'age_seconds': 3, 'members': 1, 'max': 2}

    @staticmethod
    def member(body, role):
        return {'name': body['name'], 'role': role, 'crc': body['crc'], 'patch': body['patch'], 'version': body['version'],
                'rpcs3': body.get('rpcs3', ''), 'ready': False, 'progress': 'in_game', 'token': uuid.uuid4().hex}


@pytest.fixture
def server(monkeypatch):
    from legacy_roster import lobby
    lobby._tokens.clear()
    fake = FakeServer()

    class Handler(BaseHTTPRequestHandler):
        def answer(self, method):
            size = int(self.headers.get('Content-Length') or 0)
            raw_in = self.rfile.read(size) if size else None
            is_roster = self.path.split('?')[0].endswith('/roster')
            body = raw_in if is_roster and method == 'PUT' else (json.loads(raw_in) if raw_in else None)
            status, out = fake.handle(method, self.path, body, self.headers.get('X-Lobby-Token'))
            raw = out if isinstance(out, bytes) else json.dumps(out).encode()
            self.send_response(status)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        do_GET = lambda self: self.answer('GET')
        do_POST = lambda self: self.answer('POST')
        do_PUT = lambda self: self.answer('PUT')

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setenv('LEGACY_ROSTER_ONLINE_URL', f'http://127.0.0.1:{httpd.server_port}/api/')
    yield fake
    httpd.shutdown()
