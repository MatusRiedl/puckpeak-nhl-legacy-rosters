import os
import struct

import pytest

from legacy_roster.sfo import FMT_INT, FMT_STRING, Sfo


def make_sfo(entries):
    """A minimal PARAM.SFO: [(key, format, value bytes, max length)]."""
    keys, data, index = b'', b'', b''
    for key, fmt, value, dmax in entries:
        index += struct.pack('<HHIII', len(keys), fmt, len(value), dmax, len(data))
        keys += key.encode() + b'\0'
        data += value + b'\0' * (dmax - len(value))
    keys += b'\0' * (-len(keys) % 4)
    kstart = 20 + len(index)
    return struct.pack('<4sIIII', b'\0PSF', 0x101, kstart, kstart + len(keys), len(entries)) + index + keys + data


def sample():
    return make_sfo([('ATTRIBUTE', FMT_INT, struct.pack('<I', 0), 4),
                     ('SAVEDATA_DIRECTORY', FMT_STRING, b'BLES021530202\0', 32),
                     ('SUB_TITLE', FMT_STRING, b'ROSTER2526\0', 128),
                     ('TITLE', FMT_STRING, 'NHL™ Legacy Edition'.encode() + b'\0', 128)])


def test_reads_strings_and_raw_values():
    s = Sfo(sample())
    assert s.get('SUB_TITLE') == 'ROSTER2526'
    assert s.get('TITLE') == 'NHL™ Legacy Edition'
    assert s.get('ATTRIBUTE') == b'\0\0\0\0'
    assert s.get('MISSING', 'x') == 'x'


def test_a_longer_and_a_shorter_name_both_fit_without_resizing_the_file():
    raw = sample()
    for name in ('2026-10-02 20:45', 'R'):
        s = Sfo(raw)
        s.set_str('SUB_TITLE', name)
        s.set_str('SAVEDATA_DIRECTORY', 'BLES021530207')
        out = Sfo(s.to_bytes())
        assert len(s.to_bytes()) == len(raw)
        assert out.get('SUB_TITLE') == name
        assert out.entries['SUB_TITLE'][2] == len(name) + 1        # stored length includes the terminator
        assert out.get('SAVEDATA_DIRECTORY') == 'BLES021530207'
        assert out.get('TITLE') == 'NHL™ Legacy Edition'     # neighbours untouched


def test_too_long_or_wrong_kind_is_refused():
    s = Sfo(sample())
    with pytest.raises(ValueError):
        s.set_str('SUB_TITLE', 'x' * 128)
    with pytest.raises(ValueError):
        s.set_str('ATTRIBUTE', 'x')
    with pytest.raises(ValueError):
        Sfo(b'not an sfo file at all')


def test_real_save_keeps_its_size(base_dir):
    path = os.path.join(base_dir, 'PARAM.SFO')
    s = Sfo.load(path)
    s.set_str('SUB_TITLE', '2026-10-02 20:45')
    assert len(s.to_bytes()) == os.path.getsize(path)
    assert Sfo(s.to_bytes()).get('DETAIL') == 'Rosters'
