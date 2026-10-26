"""Puck Peak in the game's dead promo lines (loc.PROMO, written by install.install_names into the same loose text
files as the team names). The disc tests need LEGACY_ROSTER_DISC (read only) and skip without it; the others use
made-up text files."""
import os

import pytest

from legacy_roster import datasource, savedata
from legacy_roster.art import install, loc

DISC = os.environ.get('LEGACY_ROSTER_DISC')
KEPT = ('FUT_NEWS_AND_EVENTS', 'FUT_NEWS_AND_EVENTS_DESC', 'TXT_LOAD_SCREEN_CLASSIC_HEADER')
NAMES = {'teams': [('PHX', 'Utah Mammoth', 'Utah', 'Mammoth', 'UTA')], 'cities': {}, 'force': set(), 'marked': {'PHX'}}


def own_texts(lang):
    """A language file like the game's: the promo keys (hashes that are not their key's CRC) with texts of differing
    length (the Czech news title is shorter than "Puck Peak"), the kept keys, a team."""
    texts = {key: f"{lang} promo text" for key in loc.PROMO}
    texts.update({key: f"{lang} promo text " + 'x' * 100 for key in loc.PROMO if '_BODY_' in key})    # news bodies are long
    texts['TXT_OFFLINE_DYNAMIC_MSG_TITLE_0'] = 'Funkce' if lang == 'cze_cz' else 'Features of the game'
    texts.update({key: f"{lang} kept" for key in KEPT})
    texts.update({'NHLTeamName_PHX': 'Arizona Coyotes®', 'NHLCityName_PHX': 'Arizona'})
    f = loc.LocFile.blank(texts)
    for n, e in enumerate(f.entries):
        if e[1] in texts and e[1].startswith('TXT_OFFLINE'):
            e[0] = 0x100 + n
    f.by_hash = {e[0]: e for e in f.entries}
    return f.build()


class TextDisc:
    def __init__(self, files):
        self.files = files

    def text_file(self, lang):
        return self.files.get(lang)


@pytest.fixture
def game(tmp_path, monkeypatch):
    monkeypatch.setattr(datasource, 'data_home', lambda: str(tmp_path / 'appdata'))
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: None)
    folder = tmp_path / 'dev_hdd0' / 'game' / 'BLES02153' / 'USRDIR'
    folder.mkdir(parents=True)
    return str(folder)


def loose(game, lang):
    return os.path.join(game, 'fe', 'loc', f"nhl_{lang}.db")


def read(game, lang):
    with open(loose(game, lang), 'rb') as f:
        return loc.LocFile(f.read())


def test_the_table_holds_short_texts_for_every_news_panel_text():
    assert len(loc.PROMO) == 16 and all(loc.PROMO.values())
    assert not any(key.startswith('FUT_') for key in loc.PROMO)          # the community server's HUT banner stays
    assert not set(KEPT) & set(loc.PROMO)
    news = [key for key in loc.PROMO if key.startswith('TXT_OFFLINE_DYNAMIC_MSG_')]
    assert len(news) == 12 and {loc.PROMO[key] for key in news if '_BODY_' in key} == {loc._NEWS}
    assert 'gg.puckpeak.com' in loc._NEWS
    assert {len(t.encode()) for t in loc.PROMO.values()} == {9, 16, 56}


def test_promo_texts_go_in_once_and_restore_brings_the_games_own_back(game):
    own = {lang: own_texts(lang) for lang in loc.LANGUAGES}
    disc, says = TextDisc(own), []
    os.makedirs(os.path.dirname(loose(game, 'eng_us')))
    with open(loose(game, 'eng_us'), 'wb') as f:       # a text file someone else put there before
        f.write(own['eng_us'])
    writer = install._Writer([game])
    assert install.install_names(disc, writer, NAMES, says.append) == 7
    writer.save()
    assert says == ["Photos and logos: team names and Puck Peak texts written in 7 languages"]
    for lang in loc.LANGUAGES:
        f = read(game, lang)
        assert {key: f.get_existing(key) for key in loc.PROMO} == loc.PROMO, lang
        assert all(f.get_existing(key) == f"{lang} kept" for key in KEPT)
        assert f.get('NHLTeamName_PHX') == 'Utah Mammoth'                       # one file holds both
        assert len(f.entries) == len(loc.LocFile(own[lang]).entries) + 3 + 4  # names add theirs (and the 4 Select
        #                                                    Teams lines this file lacks), promo texts none
    stamps = [os.stat(loose(game, lang)).st_mtime_ns for lang in loc.LANGUAGES]

    writer = install._Writer([game])                   # the same table again: nothing is written
    assert install.install_names(disc, writer, NAMES, says.append) == 0
    assert [os.stat(loose(game, lang)).st_mtime_ns for lang in loc.LANGUAGES] == stamps

    install.remove(say=lambda m: None)                  # "Restore the game's own pictures"
    with open(loose(game, 'eng_us'), 'rb') as f:
        assert f.read() == own['eng_us']
    assert sorted(os.listdir(os.path.dirname(loose(game, 'eng_us')))) == ['nhl_eng_us.db']


def eb_archive(files):
    """A small "EB" v3 archive (the .big files of the disc and of update 1.01's patch.big), stored, not packed."""
    import struct
    dirs = sorted({name.rsplit('/', 1)[0] for name in files})
    fnl, dnl = 32, 32
    names = b''.join(struct.pack('>H', dirs.index(name.rsplit('/', 1)[0])) + name.rsplit('/', 1)[1].encode().ljust(fnl - 2, b'\0')
                     for name in files)
    names = names.ljust((len(names) + 15) // 16 * 16, b'\0') + b''.join(d.encode().ljust(dnl, b'\0') for d in dirs)
    names_off = 0x30 + len(files) * 16
    data_off = (names_off + len(names) + 15) // 16 * 16
    table, body = b'', b''
    for data in files.values():
        table += struct.pack('>IIII', (data_off + len(body)) // 16, 0, len(data), 0)
        body += data.ljust((len(data) + 15) // 16 * 16, b'\0')
    head = b'EB' + struct.pack('>HIIII', 3, len(files), 0, names_off, len(names)) + bytes([fnl, dnl]) + struct.pack('>H', len(dirs))
    return (head.ljust(0x30, b'\0') + table + names).ljust(data_off, b'\0') + body


def test_a_game_with_update_101_starts_from_the_updates_own_texts(game):
    """Update 1.01's patch.big carries newer text files (13 more texts, 3-on-3 overtime among them): the loose file
    is made from those, else the game would lose them."""
    own = {lang: own_texts(lang) for lang in loc.LANGUAGES}
    newer = loc.LocFile(own['eng_us'])
    newer.set('OT3ThenShootout', '5 Min (3 on 3) then Shootout')
    newer = newer.build()
    disc = TextDisc(own)
    writer = install._Writer([game])
    install.install_names(disc, writer, NAMES, lambda m: None)
    before = writer.manifest['games'][game]['fe/loc/nhl_eng_us.db']['source']
    assert read(game, 'eng_us').get('OT3ThenShootout') is None

    with open(os.path.join(game, 'patch.big'), 'wb') as f:
        f.write(eb_archive({'fe/ion/game/storefront.big': b'x' * 40, 'fe/loc/nhl_eng_us.db': newer}))
    assert install.update_texts([game]) == {'eng_us': newer}
    writer = install._Writer([game])
    assert install.install_names(disc, writer, NAMES, lambda m: None) == 7       # a new source: written again
    assert writer.manifest['games'][game]['fe/loc/nhl_eng_us.db']['source'] != before
    assert read(game, 'eng_us').get('OT3ThenShootout') == '5 Min (3 on 3) then Shootout'
    assert read(game, 'eng_us').get('NHLTeamName_PHX') == 'Utah Mammoth'
    assert read(game, 'fin_fi').get('OT3ThenShootout') is None                  # not in this patch.big: the disc's
    with open(os.path.join(game, 'patch.big'), 'wb') as f:
        f.write(b'not an archive')
    assert install.update_texts([game]) == {}


def test_a_changed_table_rewrites_the_files(game, monkeypatch):
    disc = TextDisc({lang: own_texts(lang) for lang in loc.LANGUAGES})
    writer = install._Writer([game])
    install.install_names(disc, writer, NAMES, lambda m: None)
    first = writer.manifest['games'][game]['fe/loc/nhl_eng_us.db']['source']
    monkeypatch.setitem(loc.PROMO, 'TXT_TUNER_SET_AVAILABLE', 'Puck Peak!')
    assert install.install_names(disc, writer, NAMES, lambda m: None) == 7
    assert writer.manifest['games'][game]['fe/loc/nhl_eng_us.db']['source'] != first
    assert read(game, 'fin_fi').get_existing('TXT_TUNER_SET_AVAILABLE') == 'Puck Peak!'
    monkeypatch.setattr(loc, 'PROMO_VERSION', '#test')
    assert install.install_names(disc, writer, NAMES, lambda m: None) == 7


def test_a_promo_text_longer_than_any_language_keeps_is_refused(game, monkeypatch):
    disc, says = TextDisc({lang: own_texts(lang) for lang in loc.LANGUAGES}), []
    room = loc.promo_limits(loc.LocFile(own_texts(lang)) for lang in loc.LANGUAGES)
    assert room['TXT_OFFLINE_DYNAMIC_MSG_TITLE_0'] == 20               # the longest language, not the Czech 6
    monkeypatch.setitem(loc.PROMO, 'TXT_TUNER_SET_AVAILABLE', 'x' * 40)
    assert install.install_names(disc, install._Writer([game]), NAMES, says.append) == 0
    assert says[0].startswith("Photos and logos: team names and Puck Peak texts NOT written in eng_us: "
                              "TXT_TUNER_SET_AVAILABLE is 40 bytes")
    assert not os.path.exists(loose(game, 'eng_us'))


def test_an_empty_promo_text_leaves_the_games_own(monkeypatch):
    f = loc.LocFile(own_texts('eng_us'))
    monkeypatch.setitem(loc.PROMO, 'TXT_OFFLINE_DYNAMIC_MSG_BODY_0', '')
    loc.apply_promo(f)
    g = loc.LocFile(f.build())
    assert g.get_existing('TXT_OFFLINE_DYNAMIC_MSG_BODY_0') == 'eng_us promo text ' + 'x' * 100
    assert g.get_existing('TXT_OFFLINE_DYNAMIC_MSG_BODY_1') == loc.PROMO['TXT_OFFLINE_DYNAMIC_MSG_BODY_1']
    assert g.get_existing('TXT_TUNER_SET_AVAILABLE') == 'www.puckpeak.com'


# --- on the game's own disc -----------------------------------------------------------------------------------------
@pytest.fixture(scope='module')
def disc():
    if not DISC or not os.path.exists(DISC):
        pytest.skip("no game disc (set LEGACY_ROSTER_DISC to your NHL Legacy disc image)")
    from legacy_roster.art.lab import Disc
    return Disc(DISC)


@pytest.fixture(scope='module')
def disc_files(disc):
    return {lang: loc.LocFile(disc.text_file(lang)) for lang in loc.LANGUAGES}


def test_every_promo_key_is_in_every_language_of_the_disc_and_every_text_fits(disc_files):
    for lang, f in disc_files.items():
        for key in loc.PROMO:
            stored = [e for e in f.entries if e[1].upper() == key.upper() and not e[3]]
            assert len(stored) == 1 and stored[0][1] == key and not stored[0][4], (lang, key)
    room = loc.promo_limits(disc_files.values())
    assert set(room) == set(loc.PROMO)
    assert all(len(text.encode()) <= room[key] for key, text in loc.PROMO.items())
    assert room['TXT_OFFLINE_DYNAMIC_MSG_TITLE_0'] == 22


def test_the_disc_texts_take_puck_peak_once_and_come_back(disc, disc_files, game):
    writer = install._Writer([game])
    assert install.install_names(disc, writer, NAMES, lambda m: None) == 7
    writer.save()
    for lang in loc.LANGUAGES:
        f, own = read(game, lang), disc_files[lang]
        assert {key: f.get_existing(key) for key in loc.PROMO} == loc.PROMO, lang
        assert all(f.get_existing(key) == own.get_existing(key) for key in KEPT + ('TXT_TUNER_SETS_CHECKING',))
        assert f.get('NHLTeamName_PHX') == 'Utah Mammoth'
    writer = install._Writer([game])
    assert install.install_names(disc, writer, NAMES, lambda m: None) == 0
    install.remove(say=lambda m: None)
    assert not os.path.exists(os.path.join(game, 'fe'))         # the game reads its disc's texts again
