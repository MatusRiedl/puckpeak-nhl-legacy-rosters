"""Club logos from English Wikipedia, for leagues whose own sites publish them only as SVG.

The club's article names its logo in the infobox (`| logo = Foo.svg`); Wikipedia renders any
logo, SVG included, as a PNG of the width asked for. Only the link goes into the data pack: the
updater downloads the picture on the player's own PC. `club_slots.json` may give a club a
'wiki' article title when its name in the feed is not the article's.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://en.wikipedia.org/w/api.php"
WIDTH = 512
PAUSE = 1.0
# Wikimedia asks API clients to name themselves; generic browser names are throttled hard
AGENT = "NHLLegacyRosterUpdater-datapack/0.3 (roster tool for the game NHL Legacy Edition; Python urllib)"
FILE = re.compile(r'^\s*\|\s*(?:logo|image|team_logo)\s*=\s*(?:\[\[)?(?:File:|Image:)?\s*([^|\]\n<{}]+?\.(?:svg|png|jpe?g|gif))',
                  re.I | re.M)


def _query(**params):
    params.update(format='json', formatversion=2, maxlag=5)
    req = urllib.request.Request(f"{API}?{urllib.parse.urlencode(params)}", headers={'User-Agent': AGENT})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read())
            time.sleep(PAUSE)
            return data
        except urllib.error.HTTPError as err:
            if err.code != 429 or attempt == 4:
                raise
            time.sleep(int(err.headers.get('Retry-After') or 0) or 10 * (attempt + 1))


def logo_file(title):
    """The logo file named in the infobox of `title` (redirects followed), or None."""
    d = _query(action='parse', page=title, prop='wikitext', section=0, redirects=1)
    text = (d.get('parse') or {}).get('wikitext') or ''
    m = FILE.search(text)
    return m.group(1).strip() if m else None


def png_url(filename, width=WIDTH):
    """A PNG rendering of a Wikipedia file, `width` pixels wide (None when there is none)."""
    d = _query(action='query', titles=f"File:{filename}", prop='imageinfo', iiprop='url', iiurlwidth=width)
    pages = (d.get('query') or {}).get('pages') or []
    info = (pages[0].get('imageinfo') or [{}])[0] if pages else {}
    return info.get('thumburl') or info.get('url')


def logo_url(title):
    name = logo_file(title)
    return png_url(name) if name else None
