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
