"""Small helpers the providers share: polite downloads and turning places into countries."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from legacy_roster.datasource import http_get  # noqa: E402

PAUSE = 0.3     # seconds between requests to the same site


def get_text(url, pause=PAUSE):
    raw = http_get(url, timeout=60)
    time.sleep(pause)
    return raw.decode('utf-8', 'replace')


def get_json(url, pause=PAUSE):
    return json.loads(get_text(url, pause))


def inches_to_cm(text):
    """'6-3', "6'3" or '6.3' (feet and inches) -> centimetres, None when unreadable."""
    for sep in ('-', "'", '.'):
        if sep in (text or ''):
            feet, _, inch = text.partition(sep)
            inch = inch.strip('"\' ')
            if feet.strip().isdigit() and (inch.isdigit() or not inch):
                return round((int(feet) * 12 + int(inch or 0)) * 2.54)
    return None


def pounds_to_kg(text):
    try:
        return round(float(text) / 2.20462) if text and float(text) > 0 else None
    except ValueError:
        return None


PROVINCES = {'AB', 'BC', 'MB', 'NB', 'NL', 'NF', 'NS', 'NT', 'NU', 'ON', 'PE', 'PEI', 'QC', 'PQ', 'QUE', 'SK', 'YT'}
STATES = {'AK', 'AL', 'AR', 'AZ', 'CA', 'CO', 'CT', 'DC', 'DE', 'FL', 'GA', 'HI', 'IA', 'ID', 'IL', 'IN', 'KS', 'KY',
          'LA', 'MA', 'MD', 'ME', 'MI', 'MN', 'MO', 'MS', 'MT', 'NC', 'ND', 'NE', 'NH', 'NJ', 'NM', 'NV', 'NY', 'OH',
          'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VA', 'VT', 'WA', 'WI', 'WV', 'WY'}
COUNTRIES = {
    'canada': 'CAN', 'can': 'CAN', 'usa': 'USA', 'united states': 'USA', 'us': 'USA', 'u.s.a.': 'USA',
    'sweden': 'SWE', 'swe': 'SWE', 'finland': 'FIN', 'fin': 'FIN', 'russia': 'RUS', 'rus': 'RUS',
    'czech republic': 'CZE', 'czechia': 'CZE', 'cze': 'CZE', 'slovakia': 'SVK', 'svk': 'SVK',
    'germany': 'DEU', 'ger': 'DEU', 'deu': 'DEU', 'switzerland': 'CHE', 'sui': 'CHE', 'che': 'CHE',
    'austria': 'AUT', 'aut': 'AUT', 'denmark': 'DNK', 'den': 'DNK', 'dnk': 'DNK', 'norway': 'NOR', 'nor': 'NOR',
    'latvia': 'LVA', 'lat': 'LVA', 'lva': 'LVA', 'belarus': 'BLR', 'blr': 'BLR', 'ukraine': 'UKR', 'ukr': 'UKR',
    'kazakhstan': 'KAZ', 'kaz': 'KAZ', 'france': 'FRA', 'fra': 'FRA', 'slovenia': 'SVN', 'slo': 'SVN', 'svn': 'SVN',
    'italy': 'ITA', 'ita': 'ITA', 'poland': 'POL', 'pol': 'POL', 'hungary': 'HUN', 'hun': 'HUN',
    'great britain': 'GBR', 'united kingdom': 'GBR', 'england': 'GBR', 'scotland': 'GBR', 'gbr': 'GBR',
    'netherlands': 'NLD', 'ned': 'NLD', 'japan': 'JPN', 'jpn': 'JPN', 'australia': 'AUS', 'aus': 'AUS',
    'lithuania': 'LTU', 'ltu': 'LTU', 'croatia': 'HRV', 'cro': 'HRV', 'estonia': 'EST', 'south korea': 'KOR',
    'korea': 'KOR', 'china': 'CHN', 'mexico': 'MEX', 'belgium': 'BEL', 'spain': 'ESP', 'israel': 'ISR',
}


ISO2 = {'CA': 'CAN', 'US': 'USA', 'SE': 'SWE', 'FI': 'FIN', 'NO': 'NOR', 'RU': 'RUS', 'CZ': 'CZE', 'SK': 'SVK',
        'DE': 'DEU', 'CH': 'CHE', 'AT': 'AUT', 'DK': 'DNK', 'LV': 'LVA', 'BY': 'BLR', 'UA': 'UKR', 'KZ': 'KAZ',
        'FR': 'FRA', 'SI': 'SVN', 'IT': 'ITA', 'PL': 'POL', 'HU': 'HUN', 'GB': 'GBR', 'NL': 'NLD', 'JP': 'JPN',
        'AU': 'AUS', 'LT': 'LTU', 'HR': 'HRV', 'EE': 'EST', 'KR': 'KOR', 'CN': 'CHN', 'BE': 'BEL', 'ES': 'ESP'}


def country_of_place(*places):
    """ISO country code from texts like 'Calgary, AB', 'Kazan, Russia' or 'Canada' (None if unknown)."""
    for place in places:
        parts = [x.strip() for x in (place or '').split(',') if x.strip()][1:]      # the first is the town
        # a country name first, then a province (CA is California, not Canada), then a state
        for found in ([COUNTRIES.get(p.lower().rstrip('.')) for p in parts],
                      ['CAN' if p.upper() in PROVINCES else None for p in parts],
                      ['USA' if p.upper() in STATES else None for p in parts]):
            code = next((c for c in found if c), None)
            if code:
                return code
        if len(parts) == 0 and (place or '').strip().lower() in COUNTRIES:     # just a country
            return COUNTRIES[place.strip().lower()]
    return None
