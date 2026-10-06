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


def test_the_select_teams_lines_are_changed_where_the_game_keeps_them():
    """Play Now's Select Teams reads TEAMLINE1/2 (hashes that are not the CRC of their key): a plain
    `set` would add a text nobody asks for, so they are found by their stored key."""
    f = loc.LocFile.blank({'NHLTeamName_PHX': 'Arizona Coyotes®', 'TEAMLINE1_PHX': 'Arizona',
                           'TEAMLINE2_PHX': 'Coyotes®', 'NICKLINE2_PHX': 'Coyotes®',
                           'NHLTeamName_Abbr3_PHX': 'ARZ', 'NHLTeamName_22': 'Arizona Coyotes®',
                           'NHLCityName_22': 'Arizona', 'CITYLINE1_22': 'Arizona', 'NICKLINE2_22': 'Coyotes®',
                           'NHLTeamName_CHOM': 'Piráti Chomutov', 'TEAMLINE1_CHOM': 'Piráti',
                           'TEAMLINE2_CHOM': 'Chomutov', 'TEAMLINE2_MOD': 'MODO Hockey', 'NHLTeamName_MOD': 'MODO'})
    for n, e in enumerate(f.entries):
        if e[1].startswith(('TEAMLINE', 'NICKLINE', 'CITYLINE', 'NHLTeamName_Abbr3')):
            e[0] = 0x10000 + n                                 # a hash that is not the key's CRC
    f.by_hash = {e[0]: e for e in f.entries}
    f = loc.LocFile(f.build())
    before = len(f.entries)
    names = {'teams': [('PHX', 'Utah Mammoth', 'Utah', 'Mammoth', 'UTA'),
                       ('CHOM', 'Rytíři Kladno', 'Kladno', 'Rytíři', 'KLA'),
                       ('MOD', 'Timrå IK', 'Timrå', 'Timrå IK', 'TIK')],
             'cities': {}, 'force': set(), 'marked': {'PHX'},
             'numbered': {22: ('Utah Mammoth', 'Utah', 'Mammoth', 'UTA')}}
    loc.apply_names(f, names)
    g = loc.LocFile(f.build())
    text = {e[1]: e[2] for e in g.entries}
    assert (text['TEAMLINE1_PHX'], text['TEAMLINE2_PHX'], text['NICKLINE2_PHX']) == ('Utah', 'Mammoth®', 'Mammoth®')
    assert text['NHLTeamName_Abbr3_PHX'] == 'UTA'
    assert (text['NHLTeamName_22'], text['NHLCityName_22'], text['CITYLINE1_22'], text['NICKLINE2_22']) == \
        ('Utah Mammoth', 'Utah', 'Utah', 'Mammoth®')
    assert (text['TEAMLINE1_CHOM'], text['TEAMLINE2_CHOM']) == ('Rytíři', 'Kladno')       # nickname first
    assert (text['TEAMLINE1_MOD'] if 'TEAMLINE1_MOD' in text else None) is None           # no key: not added
    assert text['TEAMLINE2_MOD'] == 'Timrå IK'
    # only texts the game has were changed, plus the five the names always write for the clubs
    assert not {'NICKLINE2_CHOM', 'NHLTeamName_Abbr3_MOD', 'TEAMLINE1_PHX '} & set(text)
    assert len(g.entries) - before <= 3 * 5               # NHLCityName_x, TXT_NICKNAME_x, ... of the three clubs


def test_select_lines_follow_the_games_own_way_of_splitting_a_name():
    assert loc.select_lines('Tampa Bay Lightning', 'Tampa Bay', 'Lightning', '®') == ('Tampa Bay', 'Lightning®')
    assert loc.select_lines('Rytíři Kladno', 'Kladno', 'Rytíři') == ('Rytíři', 'Kladno')
    assert loc.select_lines('Timrå IK', 'Timrå', 'Timrå IK') == ('', 'Timrå IK')
