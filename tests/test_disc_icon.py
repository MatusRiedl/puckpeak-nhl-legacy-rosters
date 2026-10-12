from legacy_roster import stock


def test_icon_found_next_to_param_sfo_in_any_folder(tmp_path):
    (tmp_path / 'game').mkdir()
    (tmp_path / 'game' / 'icon0.png').write_bytes(b'\x89PNG the game')
    (tmp_path / 'game' / 'PARAM.SFO').write_bytes(b'x')
    assert stock.disc_icon(str(tmp_path)) == b'\x89PNG the game'


def test_icon_prefers_ps3_game_folder(tmp_path):
    (tmp_path / 'other').mkdir()
    (tmp_path / 'other' / 'ICON0.PNG').write_bytes(b'other')
    (tmp_path / 'PS3_GAME').mkdir()
    (tmp_path / 'PS3_GAME' / 'ICON0.PNG').write_bytes(b'real')
    assert stock.disc_icon(str(tmp_path)) == b'real'


def test_missing_icon_falls_back_to_own_picture(tmp_path):
    assert stock.disc_icon(str(tmp_path)) == stock.own_icon()
    assert stock.own_icon()[:4] == b'\x89PNG'
