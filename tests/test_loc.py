"""The game's text file (art/loc.py): team names live there, not in the roster."""
from legacy_roster.art import loc


def test_a_text_file_writes_and_reads_back():
    f = loc.LocFile.blank({'NHLTeamName_CHOM': 'Piráti Chomutov', 'NHLCityName_CHOM': 'Chomutov',
                           'LAS_VEGAS': 'Las Vegas', 'TXT_BOTH': 'Both'})
    again = loc.LocFile(f.build())
    assert again.get('NHLTeamName_CHOM') == 'Piráti Chomutov' and again.get('las_vegas') == 'Las Vegas'
    assert again.build() == f.build()                     # reading and writing change nothing
    assert [e[0] for e in again.entries] == sorted(e[0] for e in again.entries)


def test_team_names_go_where_the_game_looks_for_them():
    f = loc.LocFile(loc.LocFile.blank({'NHLTeamName_CHOM': 'Piráti Chomutov', 'NHLCityName_CHOM': 'Chomutov',
                                       'NHLTeamName_PHX': 'Arizona Coyotes®', 'NHLTeamName_BRP': 'Hamilton Hammers',
                                       'LAS_VEGAS': 'Las Vegas'}).build())
    names = {'teams': [('CHOM', 'Rytíři Kladno', 'Kladno', 'Rytíři', 'KLA'),
                       ('PHX', 'Utah Mammoth', 'Utah', 'Mammoth', 'UTA'),
                       ('BRP', 'Hamilton Hammers', 'Hamilton', 'Hammers', 'HAM')],
             'cities': {'Coachella Valley': 'Coachella Valley', 'LAS_VEGAS': 'Somewhere else'},
             'force': set()}
    assert loc.apply_names(f, names) == 3            # Kladno, Utah, the new city; Hamilton and Las Vegas stay
    g = loc.LocFile(f.build())
    assert g.get('NHLTeamName_CHOM') == 'Rytíři Kladno' and g.get('NHLCityName_CHOM') == 'Kladno'
    assert g.get('X_XLA_TEAM_CHOM') == 'KLA' and g.get('TXT_NICKNAME_CHOM') == 'Rytíři'
    assert g.get('NHLCityName_PHX') == 'Utah' and g.get('NHLCityName_BRP') is None
    assert g.get('COACHELLA VALLEY') == 'Coachella Valley' and g.get('LAS_VEGAS') == 'Las Vegas'
    assert loc.key_hash('LAS_VEGAS') == 1194855491              # as the game's own file has it


def test_a_known_name_still_gets_its_short_code():
    """Frölunda: the game already names it right, but the scoreboard says VF, not FRO."""
    f = loc.LocFile(loc.LocFile.blank({'NHLTeamName_VF': 'Frölunda HC', 'X_XLA_TEAM_VF': 'VF',
                                       'NHLTeamName_FBK': 'Färjestad BK', 'X_XLA_TEAM_FBK': 'FBK'}).build())
    names = {'teams': [('VF', 'Frölunda HC', 'Göteborg', 'Frölunda HC', 'FRO'),
                       ('FBK', 'Färjestad BK', 'Karlstad', 'Färjestad BK', 'FAR')], 'force': set()}
    assert loc.apply_names(f, names) == 2
    g = loc.LocFile(f.build())
    assert g.get('X_XLA_TEAM_VF') == 'FRO' and g.get('X_XLA_TEAM_FBK') == 'FAR'
    assert g.get('NHLTeamName_VF') == 'Frölunda HC'


def test_an_added_text_keeps_its_key_as_the_game_asks_for_it():
    """The game keeps its keys in their own case; texts added under a capitalised key did not show."""
    f = loc.LocFile(loc.LocFile.blank({'NHLTeamName_CHOM': 'Piráti Chomutov'}).build())
    f.set('NHLTeamName_CLG', 'Calgary Wranglers')
    f.set('COACHELLA_VALLEY', 'Coachella Valley Firebirds')
    g = loc.LocFile(f.build())
    keys = {e[1] for e in g.entries}
    assert {'NHLTeamName_CHOM', 'NHLTeamName_CLG', 'COACHELLA_VALLEY'} <= keys
    assert g.get('NHLTeamName_CLG') == 'Calgary Wranglers'


def test_custom_team_cities_become_keys_in_the_games_style():
    from legacy_roster import layout
    assert layout.city_key('Coachella Valley') == 'COACHELLA_VALLEY'
    assert layout.city_key('2026 Prospects 2') == '2026_PROSPECTS_2'
    assert layout.city_key('Vålerenga / Oslo') == 'VALERENGA_OSLO'
    assert layout.is_city_key('LAS_VEGAS') and not layout.is_city_key('NhlCityName_13')


def test_the_select_teams_lines_go_under_the_keys_the_game_asks_for():
    """Play Now's Select Teams reads TEAMLINE1/2, NICKLINE2 and NHLTeamName_Abbr3 under a club's art code. The game hashes
    a key with every byte & 0xdf, digits too: under the upper-case key's CRC (this program's rule until 2026-10-19) every
    text it added under such a key was never found, and clubs the game has no lines for had blank names (lab round 35)."""
    import zlib
    assert loc.key_hash('TEAMLINE1_CHOM') == 0x0ee1dd52 and loc.key_hash('NHLTeamName_Abbr3_CHOM') == 0x89f22d44   # the
    assert loc.key_hash('TEAMLINE1_CHOM') != zlib.crc32(b'TEAMLINE1_CHOM', 0xFFFFFFFF) ^ 0xFFFFFFFF                # disc's
    game = {'NHLTeamName_PHX': 'Arizona Coyotes®', 'TEAMLINE1_PHX': 'Arizona',
            'TEAMLINE2_PHX': 'Coyotes®', 'NICKLINE2_PHX': 'Coyotes®',
            'NHLTeamName_Abbr3_PHX': 'ARZ', 'NHLTeamName_22': 'Arizona Coyotes®',
            'NHLCityName_22': 'Arizona', 'CITYLINE1_22': 'Arizona', 'NICKLINE2_22': 'Coyotes®',
            'NHLTeamName_CHOM': 'Piráti Chomutov', 'TEAMLINE1_CHOM': 'Piráti',
            'TEAMLINE2_CHOM': 'Chomutov', 'TEAMLINE2_MOD': 'MODO Hockey',
            'NHLTeamName_MOD': 'MODO'}
    f = loc.LocFile(loc.LocFile.blank(game).build())
    names = {'teams': [('PHX', 'Utah Mammoth', 'Utah', 'Mammoth', 'UTA'),
                       ('CHOM', 'Rytíři Kladno', 'Kladno', 'Rytíři', 'KLA'),
                       ('MOD', 'Timrå IK', 'Timrå', 'Timrå IK', 'TIK'),
                       ('COLE', 'Colorado Eagles', 'Colorado', 'Eagles', 'COL')],      # no texts in the game at all
             'cities': {}, 'force': set(), 'marked': {'PHX'},
             'numbered': {22: ('Utah Mammoth', 'Utah', 'Mammoth', 'UTA')}}
    loc.apply_names(f, names)
    g = loc.LocFile(f.build())
    text = {e[1]: e[2] for e in g.entries}
    assert len(text) == len(g.entries)                     # every text once: a key the game has is changed, not added
    assert (text['TEAMLINE1_PHX'], text['TEAMLINE2_PHX'], text['NICKLINE2_PHX']) == ('Utah', 'Mammoth®', 'Mammoth®')
    assert text['NHLTeamName_Abbr3_PHX'] == 'UTA'
    assert (text['NHLTeamName_22'], text['NHLCityName_22'], text['CITYLINE1_22'], text['NICKLINE2_22']) == \
        ('Utah Mammoth', 'Utah', 'Utah', 'Mammoth®')
    assert (text['TEAMLINE1_CHOM'], text['TEAMLINE2_CHOM']) == ('Rytíři', 'Kladno')       # nickname first
    assert 'TEAMLINE1_MOD' not in text and text['TEAMLINE2_MOD'] == 'Timrå IK'           # an empty line is not added
    assert [g.get(f"{k}_COLE") for k in ('TEAMLINE1', 'TEAMLINE2', 'NICKLINE2', 'NHLTeamName_Abbr3')] == [
        'Colorado', 'Eagles', 'Eagles', 'COL']
    lines = ('TEAMLINE', 'NICKLINE', 'CITYLINE', 'NHLTeamName_Abbr3')
    added = {k for k in text if k.startswith(lines)} - set(game)
    assert added == {'TEAMLINE1_COLE', 'TEAMLINE2_COLE', 'NICKLINE2_COLE', 'NHLTeamName_Abbr3_COLE', 'NICKLINE2_CHOM',
                     'NICKLINE2_MOD', 'NHLTeamName_Abbr3_CHOM', 'NHLTeamName_Abbr3_MOD',
                     'TEAMLINE1_22', 'TEAMLINE2_22', 'NHLTeamName_Abbr3_22'}


def test_select_lines_follow_the_games_own_way_of_splitting_a_name():
    assert loc.select_lines('Tampa Bay Lightning', 'Tampa Bay', 'Lightning', '®') == ('Tampa Bay', 'Lightning®')
    assert loc.select_lines('Rytíři Kladno', 'Kladno', 'Rytíři') == ('Rytíři', 'Kladno')
    assert loc.select_lines('Timrå IK', 'Timrå', 'Timrå IK') == ('', 'Timrå IK')


def test_long_names_are_split_or_shortened_to_what_the_game_keeps():
    """0.9.3: 'Motor České Budějovice' (25 bytes) on a line the game keeps at 17 overwrote memory and
    crashed Select Teams in the Czech league."""
    for full, city, nick in (('Motor České Budějovice', 'C. Budejovice', 'Motor České Budějovice'),
                             ('HC Vítkovice Ridera', 'Vitkovice', 'HC Vítkovice Ridera'),
                             ('HC Fribourg-Gottéron', 'Fribourg', 'HC Fribourg-Gottéron'),
                             ('Golden Knights', 'Vegas', 'Golden Knights')):
        a, b = loc.select_lines(full, city, nick, '®', 21, 14)
        assert len(a.encode()) <= 21 and len(b.encode()) <= 14, (full, a, b)
    assert loc.select_lines('Motor České Budějovice', 'C. Budejovice', '', '', 21, 17) == ('Motor České', 'Budějovice')
    assert loc.fit('Motor České Budějovice', 16) == 'Budějovice'
    assert loc.fit('Golden Knights®', 14) == 'Golden Knights'
    assert loc.fit('Černý', 3) == 'Če'                # never cut inside a character


def test_a_city_with_accents_still_splits_off_the_name():
    assert loc.select_lines('Litvínov Hockey', 'Litvinov', 'Hockey') == ('Litvínov', 'Hockey')


def test_names_never_go_over_the_limits_of_the_games_file():
    f = loc.LocFile(loc.LocFile.blank({'NHLTeamName_ZLN': 'PSG Zlín', 'TXT_NICKNAME_ZLN': 'Zlín',
                                       'TEAMLINE2_ZLN': 'Zlín', 'NICKLINE2_ZLN': 'Zlín'}).build())
    limits = f.limits()
    loc.apply_names(f, {'teams': [('ZLN', 'Motor České Budějovice', 'C. Budejovice', 'Motor České Budějovice', 'CEB')],
                        'cities': {}, 'force': set()})
    assert f.over_limit(limits) == []
    text = {e[1]: e[2] for e in f.entries}
    assert text['TXT_NICKNAME_ZLN'] == 'Budějovice' and text['NHLTeamName_ZLN'] == 'Motor České Budějovice'
    f.set('TEAMLINE2_ZLN', 'x' * 40)
    assert f.over_limit(limits)[0][0] == 'TEAMLINE2_ZLN'


def test_an_empty_text_is_written_as_no_text_like_the_games_own_file():
    """The game's own files hold no text of length 0 (an empty one is 'no text'); a written one crashed Select Teams."""
    f = loc.LocFile.blank({'Teamline1_MOD': 'MODO', 'Teamline2_MOD': 'MODO Hockey'})
    f.set_existing('Teamline1_MOD', '')
    f.set('Teamline2_MOD', '')
    g = loc.LocFile(f.build())
    assert g.get('Teamline1_MOD') == '' and g.by_hash[loc.key_hash('Teamline1_MOD')][4]
    assert g.by_hash[loc.key_hash('Teamline2_MOD')][4]


def test_european_clubs_have_three_plain_capital_letters():
    """0.10.1: Frölunda FRO, Färjestad FAR, Davos DAV ... (the AHL and junior leagues keep their codes)."""
    import json
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, 'tools', 'club_slots.json'), encoding='utf-8') as f:
        conf = json.load(f)
    for key in ('liiga', 'extraliga', 'shl', 'del', 'nl', 'norway'):
        codes = [c['abbr'] for c in conf[key]['slots'].values()]
        for code in codes:
            assert len(code) == 3 and code.isascii() and code == code.upper(), (key, code)
        assert len(set(codes)) == len(codes), key
    assert conf['shl']['slots']['65']['abbr'] == 'FRO' and conf['shl']['slots']['64']['abbr'] == 'FAR'
