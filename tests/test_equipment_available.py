"""Which equipment models NHL Legacy can draw (equipment.available)."""
import os

import pytest

from legacy_roster import equipment as E


def test_available_reads_the_model_numbers_from_the_file_names():
    names = ['rendering/skate/texlib_41.rpsgl', 'rendering/skate/texlib_7.rpsgl', 'rendering/glove/feglove_83_0_tm.rpsgl',
             'rendering/glove/feglove_83_1_tm.rpsgl', 'rendering/playerstick/texlib_105.rpsgl',
             'rendering/helmet/helmet_0_21_0_dm.rpsgl', 'rendering/helmet/padding_6_0.rpsgl',
             'rendering/other/texlib_9.rpsgl']
    got = E.available(names)
    assert got['skates'] == {41, 7} and got['gloves'] == {83} and got['stick'] == {105}
    assert got['helmet'] == {21, 6}
    goalie = E.available(['rendering/blocker/blocker_0_11_0_dm.rpsgl', 'rendering/goaliehelmet/goaliehelmet_0_100_cm.rpsgl'], 'goalie')
    assert goalie['blocker'] == {11} and goalie['mask'] == {100}


@pytest.mark.skipif(not os.environ.get('LEGACY_ROSTER_DISC'), reason="needs the game disc (LEGACY_ROSTER_DISC)")
def test_the_models_the_community_roster_wears_all_have_pictures_and_old_skates_do_not():
    from legacy_roster.art.disc import EbArchive, IsoImage
    path = os.environ['LEGACY_ROSTER_DISC']
    src = IsoImage(path) if os.path.isfile(path) else path
    names = list(EbArchive.open(src, 'cacherender.big').entries)
    got = E.available(names)
    assert {41, 43, 44, 45, 46, 47, 48} <= got['skates']
    assert not got['skates'] & set(range(100, 110))
    assert {105, 109, 112} <= got['stick']
