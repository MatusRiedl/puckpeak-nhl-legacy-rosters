"""The data pack: which pack the program picks."""
import gzip
import json

from legacy_roster import datasource


def write_pack(path, **fields):
    with gzip.open(path, 'wt', encoding='utf-8') as f:
        json.dump(fields, f)


def test_the_newest_readable_pack_wins_and_a_pack_for_a_newer_program_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.delenv('LEGACY_ROSTER_PACK_URL', raising=False)
    bundled = tmp_path / 'bundled.json.gz'
    write_pack(bundled, format=1, generated='2026-10-01T00:00:00Z', season=2026)
    cached = datasource.app_dir('cache', 'datapack.json.gz')
    write_pack(cached, format=datasource.PACK_FORMAT + 1, generated='2027-01-01T00:00:00Z', season=2026)
    assert datasource.load_pack(offline=True, bundled=str(bundled))['generated'] == '2026-10-01T00:00:00Z'
    write_pack(cached, format=1, generated='2026-12-01T00:00:00Z', season=2026)
    assert datasource.load_pack(offline=True, bundled=str(bundled))['generated'] == '2026-12-01T00:00:00Z'


def test_the_bundled_pack_is_readable_by_this_program(pack):
    assert datasource.usable(pack)
    assert not datasource.usable({'format': datasource.PACK_FORMAT + 1})
    assert not datasource.usable({'generated': 'x'})
