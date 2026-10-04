"""Shared fixtures.

Most tests need a real roster save of the supported family. It cannot be shipped with the
project (it is another modder's work on top of EA's data), so those tests are skipped unless one
is found: set LEGACY_ROSTER_BASE to a roster save folder, or keep one in work/backup/.
"""
import os

import pytest

from legacy_roster import datasource, pipeline
from legacy_roster.builder import Data

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get('LEGACY_ROSTER_BASE') or os.path.join(ROOT, 'work', 'backup', 'BLES021530202')


@pytest.fixture(scope='session')
def base_dir():
    if not os.path.exists(os.path.join(BASE, 'SYS-DATA')):
        pytest.skip("no base roster save available (set LEGACY_ROSTER_BASE)")
    return BASE


@pytest.fixture(scope='session')
def base_bytes(base_dir):
    with open(os.path.join(base_dir, 'SYS-DATA'), 'rb') as f:
        return f.read()


@pytest.fixture(scope='session')
def pack():
    return datasource.read_pack(datasource.BUNDLED_PACK)


@pytest.fixture(scope='session')
def data(pack):
    """The bundled pack only (its NHL snapshot instead of live rosters): fully reproducible."""
    return Data(nhl_players=datasource.flatten_nhl(pack['nhl']), ea_ratings=pack['ea_ratings'],
                iihf=pack['iihf'], season_year=pack['season'])


@pytest.fixture(scope='session')
def built(base_bytes, data):
    return pipeline.build(base_bytes, data)
