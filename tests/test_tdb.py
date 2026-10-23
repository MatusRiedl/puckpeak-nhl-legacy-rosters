import glob
import os
import struct
import zlib

import pytest

from legacy_roster import tdb
from legacy_roster.roster import Roster
from legacy_roster.tdb import RosterFile

from .conftest import ROOT


def test_crc_check_values():
    # the standard check string for both CRC variants the save uses
    assert tdb.crc32_mpeg2(b"123456789") == 0x0376E6E7
    assert tdb.crc32_bzip2(b"123456789") == 0xFC891918


def test_untouched_roster_rebuilds_byte_identical(base_bytes):
    assert RosterFile(data=base_bytes).build() == base_bytes


@pytest.mark.parametrize('path', sorted(glob.glob(os.path.join(ROOT, 'work', 'backup', '*', 'SYS-DATA'))))
def test_every_backup_roster_rebuilds_to_the_same_database(path):
    """Saves written by other tools are compressed differently, so only the content must match."""
    with open(path, 'rb') as f:
        raw = f.read()
    if not raw.startswith(tdb.ROSTER_MAGIC):
        pytest.skip("not a roster save")
    original = zlib.decompress(raw[0x30:0x30 + struct.unpack_from('<I', raw, 0x2C)[0]])
    f = RosterFile(data=raw)
    assert f.build_db() == original
    rebuilt = f.build()
    assert tdb.check_chain(rebuilt) == [] and RosterFile(data=rebuilt).build_db() == original


def test_fields_read_and_write_back(base_bytes):
    f = RosterFile(data=base_bytes)
    for name in ('cPbu', 'ulGe', 'yvSd', 'ttOk'):
        t = f[name]
        for fname, fld in t.fields.items():
            old = t.get(5, fname)
            if fld.is_string:
                t.set(5, fname, old)
            else:
                for v in (0, fld.mask, old):
                    t.set(5, fname, v)
                    assert t.get(5, fname) == v
    assert f.build() == base_bytes      # everything was put back, neighbours untouched


def test_values_that_do_not_fit_are_refused(base_bytes):
    P = RosterFile(data=base_bytes)['cPbu']
    with pytest.raises(ValueError):
        P.set(0, 'jersey', 128)                  # 7 bits
    with pytest.raises(ValueError):
        P.set(0, 'firstname', 'x' * 25)          # 24 bytes + terminator


def test_real_names_are_aliases_for_tags(base_bytes):
    R = Roster(base_bytes)
    assert R.P.real_name == 'exhibitionplayerbiotable'
    for i in (0, 100, 4000):
        assert R.P.get(i, 'lastname') == R.P.get(i, 'RMbQ')
        assert R.P.get(i, 'game_id') == R.P.get(i, 'zIBw')
    assert R.U.get(0, 'team') == R.U.get(0, 'BSXd')
    assert R.T.has('league') and not R.T.has('no_such_field')


def test_add_and_delete_record(base_bytes):
    U = RosterFile(data=base_bytes)['ulGe']
    n = U.cur_rec
    i = U.add_record({'team': 7, 'jersey': 99})
    assert (i, U.cur_rec, U.get(i, 'team'), U.get(i, 'jersey')) == (n, n + 1, 7, 99)
    first = U.record_bytes(1)
    U.delete_record(0)
    assert U.cur_rec == n and U.record_bytes(0) == first


def test_check_chain_spots_a_broken_checksum(base_bytes):
    assert tdb.check_chain(base_bytes) == []
    bad = bytearray(base_bytes)
    bad[0x10] ^= 0xFF
    assert tdb.check_chain(bytes(bad)) == ["header CRC at 0x10 is wrong"]


def test_a_wider_field_keeps_every_value_and_moves_the_ones_after_it(base_bytes):
    R = Roster(base_bytes)
    P, before = R.P, Roster(base_bytes).P
    old = {n: (f.offset, f.bits) for n, f in P.fields.items()}
    P.widen('WBbd', 6)
    assert P.field('WBbd').bits == 6 and P.rec_len == before.rec_len
    assert all(P.fields[n].offset == o + (o > old['WBbd'][0]) for n, (o, _b) in old.items())
    assert all(P.get(i, n) == before.get(i, n) for i in range(0, P.cur_rec, 5) for n in P.fields)
    P.set(0, 'WBbd', 32)                                         # Vegas fits now
    P.widen('WBbd', 6)                                           # already that wide: nothing changes
    assert P.get(0, 'WBbd') == 32 and Roster(R.f.build()).P.get(0, 'WBbd') == 32
    with pytest.raises(ValueError):
        P.widen('WBbd', 5)
    with pytest.raises(ValueError):
        P.widen('WBbd', 6 + P.rec_bits)
    with pytest.raises(ValueError):
        P.narrow('WBbd', 5)                                      # 32 does not fit in five bits
    P.set(0, 'WBbd', before.get(0, 'WBbd'))
    P.narrow('WBbd', 5)                                          # back as it was, byte for byte
    assert R.f.build() == base_bytes and P.field('WBbd').bits == 5


def test_a_longer_save_section_keeps_the_database(base_bytes):
    f = RosterFile(data=base_bytes)
    size = f.section_size
    f.resize(size + 864)                                         # the game patch's stage S
    out = f.build()
    again = RosterFile(data=out)
    assert len(out) == 0x2C + size + 864 and again.section_size == size + 864
    assert struct.unpack_from('>I', out, 0x24)[0] == size + 864 and again.build_db() == RosterFile(data=base_bytes).build_db()
    again.resize(size)
    assert again.build() == RosterFile(data=base_bytes).build()   # back to the game's own length
