"""The league feed parsers, on small samples shaped like the real responses (no network)."""
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))

from providers import hockeytech, penny_del, sportality, swiss  # noqa: E402
from providers.web import country_of_place, inches_to_cm, pounds_to_kg  # noqa: E402


def test_places_become_countries():
    assert country_of_place('Calgary, AB, ') == 'CAN'
    assert country_of_place('Toronto, ON, CA') == 'CAN'            # CA after a province is Canada, not California
    assert country_of_place('Los Angeles, CA, ') == 'USA'
    assert country_of_place('Kazan, Russia, ') == 'RUS'
    assert country_of_place('Högås, Sweden, ') == 'SWE'
    assert country_of_place('', 'United States') == 'USA'
    assert country_of_place('Nowhere') is None
    assert inches_to_cm('6-3') == 190 and inches_to_cm("5'11") == 180 and inches_to_cm('') is None
    assert pounds_to_kg('210') == 95 and pounds_to_kg('') is None


def test_a_hockeytech_roster_row():
    row = {'first_name': 'Aydar', 'last_name': 'Suniev', 'position': 'LW', 'shoots': 'L', 'catches': None,
           'birthplace': 'Kazan, Russia, ', 'homecntry': 'Russia', 'birthcntry': '', 'status': 'NHL', 'rookie': '0',
           'tp_jersey_number': '61', 'height': '6-2', 'weight': '210', 'rawbirthdate': '2004-11-16'}
    p = hockeytech.parse_player(row)
    assert p == {'photo': None, 'first': 'Aydar', 'last': 'Suniev', 'birth': [2004, 11, 16], 'pos': 'L', 'shoots': 'L',
                 'num': 61, 'height_cm': 188, 'weight_kg': 95, 'country': 'RUS', 'letter': None, 'rookie': False,
                 'nhl_contract': True}
    photo = 'https://assets.leaguestat.com/ahl/240x240/10146.jpg'
    assert hockeytech.parse_player(dict(row, player_image=photo))['photo'] == photo
    assert hockeytech.parse_player(dict(row, player_image='https://lscluster.hockeytech.com/img/nophoto.png'))['photo'] is None
    goalie = dict(row, position='G', shoots='', catches='L', status='AHL', birthplace='Penza, Russia, ')
    assert hockeytech.parse_player(goalie)['shoots'] == 'L' and not hockeytech.parse_player(goalie)['nhl_contract']
    assert hockeytech.parse_player(dict(row, position='RD'))['pos'] == 'D'
    assert hockeytech.parse_player(dict(row, position='')) is None                 # staff
    assert hockeytech.parse_player(dict(row, rawbirthdate='0000-00-00')) is None
    assert hockeytech.parse_player([{'role': 'General Manager'}]) is None          # the staff list inside the roster


def test_a_sportality_player_with_its_details():
    listed = {'uuid': 'x', 'firstName': 'Arvid', 'lastName': 'Holm', 'jerseyNumber': 75, 'nationality': 'SE'}
    details = {'athleteData': {'dateOfBirth': '1998-11-03', 'height': 195, 'weight': 93, 'shoots': 'Left',
                               'nationality': 'SE'}}
    p = sportality.parse_player(listed, details, 'G')
    assert p == {'photo': None, 'first': 'Arvid', 'last': 'Holm', 'birth': [1998, 11, 3], 'pos': 'G', 'shoots': 'L',
                 'num': 75, 'height_cm': 195, 'weight_kg': 93, 'country': 'SWE', 'letter': None, 'rookie': False}
    sizes = ',\n'.join(f"https://img.example/holm.png?w={w}&s=sig{w} {w}w" for w in (100, 256, 400, 640, 1080))
    listed['portraitList'] = [{'type': 'portrait', 'renderedMedia': {'url': 'https://img.example/holm.png?s=x',
                                                                     'srcset': sizes}}]
    assert sportality.parse_player(listed, details, 'G')['photo'] == 'https://img.example/holm.png?w=400&s=sig400'
    assert sportality.parse_player(listed, {'athleteData': {}}, 'G') is None       # no birthdate


DEL_PAGE = """
<h3>Stürmer</h3>
<table class="x"><thead><tr><th>#</th><th>Spieler</th><th>Name</th><th>Nat</th><th>Seite</th><th>Alter</th>
<th>Gr.</th><th>Gew.</th><th>Geb.ort</th></tr></thead><tbody>
<tr><td>9</td><td><img alt="A" class="img-fluid" src="/fileadmin/_processed_/f/3/csm_3429_bf68c799d9.png"/></td><td><a href="/x">Kristian Reichel</a></td><td>CZE</td><td>L</td><td>28</td>
<td>185</td><td>89</td><td>Litvínov</td></tr>
<tr><td>60</td><td><img src="/fileadmin/images/teams/2023/team_6.svg"/></td><td><a href="/y">Felix Noack *</a></td><td>GER</td><td>L</td><td>21</td>
<td>197</td><td>88</td><td>Berlin</td></tr>
</tbody></table>
<h3>Verteidiger</h3>
<table><tr><th>Alter</th></tr><tr><td>49</td><td></td><td><a>Lukas Kälble</a></td><td>GER</td><td>L</td>
<td>28</td><td>185</td><td>93</td><td>Mannheim</td></tr></table>
<h3>Torhüter</h3>
<table><tr><th>Alter</th></tr><tr><td>30</td><td></td><td><a>Jake Hildebrand</a></td><td>GER</td><td>L</td>
<td>33</td><td>183</td><td>83</td><td>Butler, PA</td></tr></table>
"""


def test_a_del_roster_page_gives_an_approximate_birthdate():
    today = datetime.date(2026, 10, 3)
    players = penny_del.parse_roster(DEL_PAGE, today)
    assert [(p['first'], p['last'], p['pos']) for p in players] == [
        ('Kristian', 'Reichel', 'F'), ('Lukas', 'Kälble', 'D'), ('Jake', 'Hildebrand', 'G')]     # '*' is skipped
    assert players[0]['photo'] == 'https://www.penny-del.org/fileadmin/_processed_/f/3/csm_3429_bf68c799d9.png'
    k = players[1]
    assert k['photo'] is None                                                            # no picture in the row
    assert k['birth'] == [1998, 7, 1] and k['birth_approx'] and k['country'] == 'DEU' and k['num'] == 49
    assert penny_del.birth_from_age(28, datetime.date(2027, 3, 1)) == [1998, 7, 1]       # before 1 July


def test_a_national_league_player():
    p = swiss.parse_player({'firstName': 'Robin', 'lastName': 'Zumbühl', 'number': '40', 'position': 'goalkeeper',
                            'birth': '1998-11-16', 'nationality': None, 'height': None, 'weight': None,
                            'hand': None, 'isCaptain': False})
    assert p['birth'] == [1998, 11, 16] and p['pos'] == 'G' and p['num'] == 40 and p['country'] is None
    assert swiss.parse_player(dict(firstName='Sven', lastName='Andrighetto', position='forwarder',
                                   birth='1993-03-21'))['pos'] == 'F'
    assert swiss.parse_player({'firstName': 'A', 'lastName': 'B', 'position': 'coach', 'birth': '1970-01-01'}) is None
