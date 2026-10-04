"""Latest IIHF rosters for the national teams: used for any national team a roster leaves empty
(the eight the base roster never had, and any squad a community roster emptied).

Sources are the official IIHF team-roster PDFs (stats.iihf.com/hydra):
  2026 World Championship (event 969): Austria, Great Britain, Norway, and the other top-division
      teams the game has (Canada, Czechia, Denmark, Finland, Germany, Italy, Latvia, Slovakia,
      Sweden, Switzerland, USA)
  2026 World Championship Division I A (event 722): Kazakhstan, Ukraine, Japan, Poland, France
Belarus and Russia have been banned from IIHF events since 2022; Belarus's last IIHF roster
(2021 Worlds, event 748) is used and topped up with Belarusian professionals by the updater;
Russia has none (an empty Russian squad is filled from NHL and other players in the save).

The pack's keys are the ISO codes layout.NAT_CODE uses (DEU, CHE, LVA, DNK), not the IIHF's. The
last numbers of a PDF's name are its version: the newest one lists every player registered.
Update the URLs below each spring. The PDF text extraction needs Windows' Arial fonts.
"""
import os
import re
import time
import urllib.request

from . import iihf_pdf

PDFS = {
    'AUT': "https://stats.iihf.com/hydra/969/IHM9690AUT_33_2_1.pdf",
    'GBR': "https://stats.iihf.com/hydra/969/IHM9690GBR_33_1_0.pdf",
    'NOR': "https://stats.iihf.com/hydra/969/IHM9690NOR_33_6_1.pdf",
    'KAZ': "https://stats.iihf.com/hydra/722/IHM7220KAZ_33_1_0.pdf",
    'UKR': "https://stats.iihf.com/hydra/722/IHM7220UKR_33_1_0.pdf",
    'JPN': "https://stats.iihf.com/hydra/722/IHM7220JPN_33_1_0.pdf",
    'POL': "https://stats.iihf.com/hydra/722/IHM7220POL_33_1_0.pdf",
    'BLR': "https://stats.iihf.com/Hydra/748/IHM7480BLR_33_2_0_BLR.pdf",  # 2021 Worlds, last IIHF event
    # squads the base roster has; a community roster may leave them empty (2026-27: six of them)
    'CAN': "https://stats.iihf.com/hydra/969/IHM9690CAN_33_3_0.pdf",
    'CZE': "https://stats.iihf.com/hydra/969/IHM9690CZE_33_5_1.pdf",
    'DNK': "https://stats.iihf.com/hydra/969/IHM9690DEN_33_7_0.pdf",
    'FIN': "https://stats.iihf.com/hydra/969/IHM9690FIN_33_6_1.pdf",
    'DEU': "https://stats.iihf.com/hydra/969/IHM9690GER_33_7_1.pdf",
    'ITA': "https://stats.iihf.com/hydra/969/IHM9690ITA_33_3_0.pdf",
    'LVA': "https://stats.iihf.com/hydra/969/IHM9690LAT_33_5_0.pdf",
    'SVK': "https://stats.iihf.com/hydra/969/IHM9690SVK_33_3_0.pdf",
    'SWE': "https://stats.iihf.com/hydra/969/IHM9690SWE_33_7_1.pdf",
    'CHE': "https://stats.iihf.com/hydra/969/IHM9690SUI_33_5_0.pdf",
    'USA': "https://stats.iihf.com/hydra/969/IHM9690USA_33_3_0.pdf",
    'FRA': "https://stats.iihf.com/hydra/722/IHM7220FRA_33_1_0.pdf",
}
MONTHS = {m: i + 1 for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}
ROW = re.compile(r"^(\d+) (.+?) (GK|D|F) ([LR]) (\d{1,2}) ([A-Z]{3}) (\d{4}) (\d\.\d\d) / \S+ (\d+) / \d+ (.*)$")


def cap(word):
    """'OBY-OLSEN' -> 'Oby-Olsen', "O'CONNOR" -> "O'Connor"."""
    return re.sub(r"[^\-']+", lambda m: m.group(0).capitalize(), word)


def split_name(full):
    """IIHF prints 'LASTNAME Firstname' with the surname in capitals."""
    words = full.split()
    k = 0
    while k < len(words) and words[k].replace('-', '').replace("'", '').isupper():
        k += 1
    return ' '.join(words[k:]), ' '.join(cap(w) for w in words[:k])


def from_pdf(path):
    lines = [' '.join(t for _, t in row).replace('  ', ' ').strip() for row in iihf_pdf.rows(path)]
    players = []
    for line in lines:
        m = ROW.match(line)
        if not m:
            continue
        first, last = split_name(m.group(2))
        if not first:  # late replacements: first name only in the note "#6 LAST NAME First replaced ..."
            note = next((l for l in lines if l.startswith(f"#{m.group(1)} {m.group(2)} ")), '')
            first = note[len(f"#{m.group(1)} {m.group(2)} "):].split(' ')[0]
        players.append({'num': int(m.group(1)), 'first': first, 'last': last,
                        'pos': 'G' if m.group(3) == 'GK' else m.group(3), 'shoots': m.group(4),
                        'birth': [int(m.group(7)), MONTHS[m.group(6)], int(m.group(5))],
                        'height_cm': round(float(m.group(8)) * 100), 'weight_kg': int(m.group(9)),
                        'club': m.group(10).strip()})
    return players


def fetch(cache, log=print):
    """Download the PDFs not yet in `cache` and return {'AUT': [player, ...], ...}."""
    os.makedirs(cache, exist_ok=True)
    out = {}
    for team, url in PDFS.items():
        fn = os.path.join(cache, f"{team}.pdf")
        if not os.path.exists(fn):
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with open(fn, 'wb') as f:
                f.write(urllib.request.urlopen(req, timeout=60).read())
            time.sleep(0.5)
        out[team] = from_pdf(fn)
        log(f"{team}: {len(out[team])} players")
    return out
