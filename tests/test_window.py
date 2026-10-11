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
