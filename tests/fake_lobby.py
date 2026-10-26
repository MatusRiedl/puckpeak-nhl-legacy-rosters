"""A fake lobby server that answers as the real one is meant to (the API in legacy_roster/lobby.py's docstring), for the
lobby client's and the Play online tab's tests. The host is the reference: a guest has the roster with the host's CRC and
plays with the host's patch (both need one: "none" cannot start); the game (region + version, "EU 01.00") must be the same; the RPCS3
build is only shown to the friend; the host's roster goes up gzipped and comes down the same."""
import json
import threading
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
        return {'code': lob['code'], 'state': lob['state'], 'reason': lob['reason'], 'roster': roster,
                'members': [{k: m[k] for k in ('name', 'role', 'roster_ok', 'patch_ok', 'ready', 'progress', 'patch', 'version', 'rpcs3')}
                            for m in lob['members']]}

    def handle(self, method, path, body, token=None):
        """Returns (status, answer): the answer is a dict (JSON) or bytes (the roster). `token` is the X-Lobby-Token header: create
        and join hand one out, every later request of a member must carry his."""
        self.calls.append((method, path))
        parts = [p for p in path.split('?')[0].split('/') if p][1:]       # the first part is /api
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
