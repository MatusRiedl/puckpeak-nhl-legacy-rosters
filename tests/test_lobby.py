"""The lobby client (lobby.py) against a fake server that answers as the real one is meant to (tests/fake_lobby.py)."""
import pytest

from tests.fake_lobby import FakeServer, server  # noqa: F401  (the fixture)
from legacy_roster import lobby

def test_codes_are_six_letters_typed_any_way():
    assert lobby.clean_code('kdm-qrs') == 'KDMQRS' and lobby.clean_code(' KDM QRS ') == 'KDMQRS'
    assert lobby.clean_code('KDMQR') is None and lobby.clean_code('KDMQRI') is None and lobby.clean_code('KDMQR1') is None
    assert lobby.clean_code(None) is None


def test_a_lobby_from_creating_to_both_ready(server):
    made = lobby.create('HostPlayer', 'aabbccdd', '0.26', '01.00')
    code = made['code']
    assert lobby.clean_code(code) == code and made['members'][0]['role'] == 'host' and made['state'] == 'open'
    lobby.put_roster(code, 'HostPlayer', b'roster')
    joined = lobby.join(code, 'GuestPlayer', 'aabbccdd', '0.26', '01.00')
    assert [m['role'] for m in joined['members']] == ['host', 'guest'] and joined['reason'] is None
    assert lobby.ready(code, 'HostPlayer', True)['state'] == 'open'
    both = lobby.ready(code, 'GuestPlayer', True)
    assert both['state'] == 'starting' and all(m['ready'] for m in both['members'])
    assert lobby.status(code, 'HostPlayer')['state'] == 'starting'
    assert lobby.leave(code, 'GuestPlayer') == {}
    assert [m['name'] for m in lobby.status(code, 'HostPlayer')['members']] == ['HostPlayer']


def test_the_hosts_roster_goes_up_gzipped_and_comes_down_for_a_guest_who_lacks_it(server):
    code = lobby.create('HostPlayer', 'aabbccdd', '0.26', '01.00')['code']
    sent = lobby.put_roster(code, 'HostPlayer', b'roster bytes ' * 1000)
    assert sent['roster'] == {'crc': 'aabbccdd', 'size': len(server.lobbies[code]['roster'])}
    assert len(server.lobbies[code]['roster']) < 13000                         # it travelled gzipped
    seen = lobby.join(code, 'GuestPlayer', '', '0.26', '01.00')
    assert [m['roster_ok'] for m in seen['members']] == [True, False] and 'not on GuestPlayer' in seen['reason']
    assert lobby.get_roster(code, 'GuestPlayer') == b'roster bytes ' * 1000
    lobby.ready(code, 'HostPlayer', True)
    assert lobby.ready(code, 'GuestPlayer', True)['state'] == 'open'              # still without the roster
    mine = lobby.update_me(code, 'GuestPlayer', 'aabbccdd', '0.26', '01.00')
    assert mine['reason'] is None and [m['ready'] for m in mine['members']] == [True, False]
    assert lobby.ready(code, 'GuestPlayer', True)['state'] == 'starting'


def test_a_different_patch_is_named_and_never_starts(server):
    code = lobby.create('HostPlayer', 'aabbccdd', '0.26', '01.00')['code']
    lobby.put_roster(code, 'HostPlayer', b'r')
    seen = lobby.join(code, 'GuestPlayer', 'aabbccdd', '0.25', '01.00')
    assert [m['patch_ok'] for m in seen['members']] == [True, False] and 'update the program' in seen['reason']
    assert [m['patch'] for m in seen['members']] == ['0.26', '0.25']
    lobby.ready(code, 'HostPlayer', True)
    assert lobby.ready(code, 'GuestPlayer', True)['state'] == 'open'


def test_a_member_without_the_game_patch_never_starts(server):
    code = lobby.create('HostPlayer', 'aabbccdd', '0.26', '01.00')['code']
    lobby.put_roster(code, 'HostPlayer', b'r')
    seen = lobby.join(code, 'GuestPlayer', 'aabbccdd', 'none', '01.00')
    assert 'GuestPlayer has no game patch' in seen['reason'] and 'Set up online' in seen['reason']
    lobby.ready(code, 'HostPlayer', True)
    assert lobby.ready(code, 'GuestPlayer', True)['state'] == 'open'


def test_the_rpcs3_build_travels_with_the_member_(server):
    code = lobby.create('HostPlayer', 'aabbccdd', '0.26', '01.00', rpcs3=20402)['code']
    lobby.put_roster(code, 'HostPlayer', b'r')
    seen = lobby.join(code, 'GuestPlayer', 'aabbccdd', '0.26', '01.00', '20393')
    assert [m['rpcs3'] for m in seen['members']] == ['20402', '20393'] and seen['reason'] is None
    assert [m['rpcs3'] for m in lobby.update_me(code, 'GuestPlayer', 'aabbccdd', '0.26', '01.00', 20500)['members']] == ['20402', '20500']
    lobby.ready(code, 'HostPlayer', True)
    assert lobby.ready(code, 'GuestPlayer', True)['state'] == 'starting'


def test_another_game_version_or_region_gates_nothing_and_each_member_shows_his_game(server):
    code = lobby.create('HostPlayer', 'aabbccdd', '0.26', 'EU 01.00')['code']
    lobby.put_roster(code, 'HostPlayer', b'r')
    seen = lobby.join(code, 'GuestPlayer', 'aabbccdd', '0.26', 'NA 01.00')
    assert seen['reason'] is None and [m['version'] for m in seen['members']] == ['EU 01.00', 'NA 01.00']
    lobby.ready(code, 'HostPlayer', True)
    assert lobby.ready(code, 'GuestPlayer', True)['state'] == 'starting'


def test_only_the_host_sends_a_roster_and_a_missing_one_has_its_word(server):
    code = lobby.create('HostPlayer', 'aabbccdd', '0.26', '01.00')['code']
    lobby.join(code, 'GuestPlayer', '', '0.26', '01.00')
    with pytest.raises(lobby.LobbyError) as err:
        lobby.put_roster(code, 'GuestPlayer', b'r')
    assert err.value.code == 'not_host'
    with pytest.raises(lobby.LobbyError) as err:
        lobby.get_roster(code, 'GuestPlayer')
    assert err.value.code == 'no_roster'


def test_a_damaged_download_is_a_plain_error(server, monkeypatch):
    monkeypatch.setattr(lobby, '_request', lambda *a, **k: b'not gzip at all')
    with pytest.raises(lobby.LobbyError) as err:
        lobby.get_roster('KDMQRS', 'x')
    assert err.value.code == 'bad_roster'


def test_the_servers_no_comes_with_its_word(server):
    with pytest.raises(lobby.LobbyError) as err:
        lobby.status('ZZZZZZ', 'HostPlayer')
    assert err.value.code == 'unknown' and 'No lobby has that code' in str(err.value)
    code = lobby.create('A', 'aabbccdd', '0.26', '01.00')['code']
    lobby.join(code, 'B', 'aabbccdd', '0.26', '01.00')
    with pytest.raises(lobby.LobbyError) as err:
        lobby.join(code, 'C', 'aabbccdd', '0.26', '01.00')
    assert err.value.code == 'full'


def test_no_server_is_a_plain_unreachable(monkeypatch):
    monkeypatch.setenv('LEGACY_ROSTER_ONLINE_URL', 'http://127.0.0.1:9/api')       # nothing listens on the discard port
    with pytest.raises(lobby.Unreachable) as err:
        lobby.status('KDMQRS', 'x')
    assert err.value.code == 'unreachable' and 'not reachable' in str(err.value)


def test_only_public_lobbies_with_a_roster_are_listed(server):
    private = lobby.create('HostPlayer', 'aabbccdd', '0.26', '01.00', public=False)['code']
    lobby.put_roster(private, 'HostPlayer', b'roster')
    public = lobby.create('GuestPlayer', 'aabbccdd', '0.26', '01.00', public=True, roster_name='My roster')['code']
    assert lobby.lobbies() == []                                    # his roster is not up yet
    lobby.put_roster(public, 'GuestPlayer', b'roster')
    found = lobby.lobbies()
    assert [r['code'] for r in found] == [public] and found[0]['host'] == 'GuestPlayer' and found[0]['roster_name'] == 'My roster'
    assert (found[0]['members'], found[0]['max']) == (1, 2)
    lobby.join(public, 'HostPlayer', 'aabbccdd', '0.26', '01.00')
    assert lobby.lobbies() == []                                    # full lobbies leave the list


def test_a_member_acts_with_his_own_token_and_a_stranger_who_knows_the_code_and_a_name_gets_nowhere(server):
    made = lobby.create('HostPlayer', 'aabbccdd', '0.26', '01.00')
    code = made['code']
    assert 'token' not in made                                                  # kept by the client, never shown to the page
    lobby.put_roster(code, 'HostPlayer', b'roster')
    lobby.join(code, 'GuestPlayer', 'aabbccdd', '0.26', '01.00')
    mine = dict(lobby._tokens)
    lobby._tokens.clear()                                                       # a stranger: no token at all
    for call in (lambda: lobby.status(code, 'HostPlayer'), lambda: lobby.ready(code, 'HostPlayer', True),
                 lambda: lobby.update_me(code, 'HostPlayer', '', 'none', ''), lambda: lobby.get_roster(code, 'HostPlayer'),
                 lambda: lobby.put_roster(code, 'HostPlayer', b'evil'), lambda: lobby.leave(code, 'HostPlayer'),
                 lambda: lobby.join(code, 'HostPlayer', '', 'none', '')):
        with pytest.raises(lobby.LobbyError) as err:
            call()
        assert err.value.code == 'not_member'
    lobby._tokens.update(mine)
    lobby._tokens[lobby._key(code, 'HostPlayer')] = mine[lobby._key(code, 'GuestPlayer')]     # the friend's token is no use either
    with pytest.raises(lobby.LobbyError):
        lobby.ready(code, 'HostPlayer', True)
    lobby._tokens.update(mine)
    assert server.lobbies[code]['roster'] is not None and len(server.lobbies[code]['members']) == 2
    assert not any(m['ready'] for m in lobby.status(code, 'HostPlayer')['members'])
    assert lobby.ready(code, 'HostPlayer', True)['members'][0]['ready']
    lobby.leave(code, 'GuestPlayer')
    assert lobby._key(code, 'GuestPlayer') not in lobby._tokens


def test_a_roster_that_unpacks_to_far_more_than_a_roster_is_refused(server):
    import gzip
    code = lobby.create('HostPlayer', 'aabbccdd', '0.26', '01.00')['code']
    lobby.join(code, 'GuestPlayer', '', '0.26', '01.00')
    server.lobbies[code]['roster'] = b'x'
    original = lobby._request
    bomb = gzip.compress(bytes(lobby.MAX_ROSTER + 1000), 9)         # a few KB that unpack to more than the limit
    assert len(bomb) < 100_000
    lobby._request = lambda *a, **k: bomb
    try:
        with pytest.raises(lobby.LobbyError) as err:
            lobby.get_roster(code, 'GuestPlayer')
        assert err.value.code == 'bad_roster'
        lobby._request = lambda *a, **k: gzip.compress(b'a roster')[:-6]       # cut off
        with pytest.raises(lobby.LobbyError):
            lobby.get_roster(code, 'GuestPlayer')
    finally:
        lobby._request = original


def test_chat_lines_come_back_in_the_lobby_and_a_second_line_at_once_is_told_to_wait(server):
    code = lobby.create('A', 'aabbccdd', '0.26', '01.00')['code']
    lobby.join(code, 'B', 'aabbccdd', '0.26', '01.00')
    assert lobby.say(code, 'A', '  gg  ')['chat'] == [dict(seq=1, name='A', text='gg', at=lobby.status(code, 'A')['chat'][0]['at'])]
    with pytest.raises(lobby.LobbyError) as err:
        lobby.say(code, 'A', 'rematch?')
    assert err.value.code == 'slow_down' and not lobby.missing(err.value)
    assert [c['text'] for c in lobby.say(code, 'B', 'Nice one!')['chat']] == ['gg', 'Nice one!']
    with pytest.raises(lobby.LobbyError) as err:
        lobby.say(code, 'C', 'hi')                       # not in the lobby
    assert err.value.code == 'not_member'


def test_board_card_and_history_with_the_servers_keys(server):
    for _ in range(5):
        server.play('Ann', 'Bo', 3, 1)
    board = lobby.board()
    assert [(p['name'], p['rank'], p['tier']) for p in board['players']] == [('Ann', 1, 'Rookie'), ('Bo', 2, 'Minor League')]
    card = lobby.card('ann')
    assert (card['rating'], card['w'], card['next_tier'], card['next_at']) == (1080, 5, 'Pro', 1100)
    rows = lobby.history('Bo', limit=2)
    assert len(rows) == 2 and rows[0]['opponent'] == 'Ann' and (rows[0]['for'], rows[0]['against'], rows[0]['delta']) == (1, 3, -16)
    with pytest.raises(lobby.LobbyError) as err:
        lobby.card('Nobody')
    assert err.value.code == 'unknown' and not lobby.missing(err.value)


def test_anyone_hides_a_name_but_only_its_owner_shows_it_again_and_sees_his_own_card(server):
    server.play('Ann', 'Bo', 3, 1)
    assert lobby.hide('Bo', True) == {'name': 'Bo', 'hidden': True}
    assert [p['name'] for p in lobby.board()['players']] == ['Ann', 'Hidden player']
    assert lobby.history('Ann')[0]['opponent'] == 'Hidden player'
    with pytest.raises(lobby.LobbyError):
        lobby.card('Bo')                                 # a stranger: unknown
    with pytest.raises(lobby.LobbyError) as err:
        lobby.hide('Bo', False)
    assert err.value.code == 'not_member'
    code = lobby.create('Bo', 'aabbccdd', '0.26', '01.00')['code']   # in a lobby: his token proves it is him
    assert lobby.card('Bo')['hidden'] is True and lobby.history('Bo')[0]['opponent'] == 'Ann'
    assert lobby.hide('Bo', False)['hidden'] is False
    assert lobby.card('Bo')['hidden'] is False and code


def test_a_server_from_before_the_ranks_is_missing_them_not_broken(server):
    server.ranks = False
    code = lobby.create('A', 'aabbccdd', '0.26', '01.00')['code']
    assert 'chat' not in lobby.status(code, 'A')
    for call in (lobby.board, lambda: lobby.card('A'), lambda: lobby.history('A'), lambda: lobby.hide('A', True),
                 lambda: lobby.say(code, 'A', 'gg')):
        with pytest.raises(lobby.LobbyError) as err:
            call()
        assert err.value.code == 'http404' and lobby.missing(err.value)
    assert lobby.missing(lobby.Unreachable()) and not lobby.missing(lobby.LobbyError('unknown', 'x'))
