"""The new window's pieces that need no window: the pushes to the page and the page's own files."""
import os
import re

from legacy_roster.window.host import WebHost

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'legacy_roster', 'web')


def test_changes_are_pushed_together_and_only_once():
    host = WebHost()
    calls = []
    host.register('update', lambda: calls.append('update') or {'n': len(calls)})
    host.register('editor', lambda: {'e': 1})
    assert host.take() is None
    host.changed('update')
    host.changed('update')
    host.log('one', 'two')
    host.send('details', {'open': True})
    message = host.take()
    assert message == {'slices': {'update': {'n': 1}}, 'log': {'lines': ['one', 'two'], 'clear': False},
                       'events': [['details', {'open': True}]]}
    assert host.take() is None
    first = host.first()
    assert set(first['slices']) == {'update', 'editor'} and first['log']['lines'] == ['one', 'two']


def test_the_page_names_only_its_own_files():
    """Everything the page loads is in web/ (the program works offline) and every import resolves."""
    with open(os.path.join(WEB, 'index.html'), encoding='utf-8') as f:
        page = f.read()
    for link in re.findall(r'(?:src|href)="([^"]+)"', page):
        assert not re.match(r'(https?:)?//', link), link
        assert os.path.exists(os.path.join(WEB, link)), link
    js = os.path.join(WEB, 'js')
    for name in os.listdir(js):
        with open(os.path.join(js, name), encoding='utf-8') as f:
            text = f.read()
        assert 'http://' not in text and 'cdn' not in text.lower(), name
        for target in re.findall(r"import(?:[^'\"]*from)?\s*\(?\s*'(\.[^']+)'", text):
            assert os.path.exists(os.path.normpath(os.path.join(js, target))), (name, target)


def test_every_call_of_the_page_is_offered_by_the_api():
    from legacy_roster.window.api import Api
    offered = {n for n in dir(Api) if not n.startswith('_')}
    js = os.path.join(WEB, 'js')
    called = set()
    for name in os.listdir(js):
        if name == 'demo.js':
            continue
        with open(os.path.join(js, name), encoding='utf-8') as f:
            called |= set(re.findall(r"call\('([a-z_]+)'", f.read()))
    assert called and called <= offered, called - offered


def test_the_setup_tabs_discord_button_opens_the_puck_peak_discord():
    from legacy_roster.window.api import Api

    class Host:
        opened = []

        def open_url(self, url):
            self.opened.append(url)

    host = Host()
    assert Api(host, None).open_discord() is None
    assert host.opened == ['https://gg.puckpeak.com']
    with open(os.path.join(WEB, 'js', 'shell.js'), encoding='utf-8') as f:
        assert "call('open_discord')" in f.read()
    with open(os.path.join(WEB, 'js', 'update.js'), encoding='utf-8') as f:
        assert '<${DiscordButton}/><${KofiButton}/></div>\n      <${RpcsCard}' in f.read()    # above "Where is RPCS3?" (owner, 0.50.2); Ko-fi beside Discord, one row (0.50.4)
    assert Api(host, None).open_kofi() is None and host.opened[-1] == 'https://ko-fi.com/iksperial'
    with open(os.path.join(WEB, 'js', 'shell.js'), encoding='utf-8') as f:
        assert "call('open_kofi')" in f.read()


def test_the_pages_server_takes_many_connections_at_once():
    """The page asks for its fonts and scripts at once; with Python's queue of 5 Windows refused the rest (lab 47c)."""
    import socket
    from wsgiref.simple_server import WSGIServer
    from legacy_roster.window import main
    was = WSGIServer.request_queue_size
    main.roomy_server()
    try:
        server = WSGIServer(('127.0.0.1', 0), None)
        socks = []
        try:
            for _ in range(30):                          # nobody accepts: every connection waits in the queue
                socks.append(socket.create_connection(server.server_address, timeout=5))
        finally:
            for s in socks:
                s.close()
            server.server_close()
    finally:
        WSGIServer.request_queue_size = was


def test_the_play_online_tab_is_wired_to_python():
    from legacy_roster.window.api import Api

    class Online:
        def __init__(self):
            self.said = []

        def refresh(self):
            self.said.append('refresh')

        def setup(self):
            self.said.append('setup')

        def create(self, public=None):
            self.said.append('create' if public is None else ('create', public))

        def set_public(self, on):
            self.said.append(('public', on))

        def refresh_list(self):
            self.said.append('list')

        def join(self, code):
            self.said.append(('join', code))

        def ready(self, on):
            self.said.append(('ready', on))

        def leave(self):
            self.said.append('leave')

    online = Online()
    api = Api(None, None, online=online)
    api.online_check(), api.online_setup(), api.online_create(), api.online_create(1), api.online_public(1), api.online_list()
    api.online_join('kdm qrs'), api.online_ready(1), api.online_leave()
    assert online.said == ['refresh', 'setup', 'create', ('create', True), ('public', True), 'list', ('join', 'kdm qrs'),
                           ('ready', True), 'leave']
    for name in ('js/online.js', 'js/main.js'):
        with open(os.path.join(WEB, name), encoding='utf-8') as f:
            text = f.read()
        assert ("call('online_setup')" in text) if name == 'js/online.js' else ("{ id: 'online', label: 'MULTIPLAYER', gold: true }" in text)
