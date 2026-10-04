from legacy_roster import pipeline
from legacy_roster.builder import Data
from legacy_roster.progress import fraction, is_remark


def test_counted_messages_move_the_bar_smoothly():
    assert fraction("NHL rosters: ANA (1/32)") < fraction("NHL rosters: TOR (28/32)") < fraction("NHL rosters: VGK (32/32)")
    assert abs(fraction("NHL rosters: VGK (32/32)") - 0.30) < 1e-9
    assert fraction("NHL: checking players the roster lists leave out (61/127)") > 0.30
    assert fraction("Saved as \"2026-10-02 22:40\" in BLES021530209") == 1.0


def test_the_bar_never_goes_back_and_remarks_do_not_move_it():
    assert fraction("NHL rosters: ANA (1/32)", previous=0.5) == 0.5
    assert fraction("Prospect pools: no room left for 3 players; they are free agents now") is None
    first = fraction("Liiga: building the clubs", 0.79)
    second = fraction("Extraliga: building the clubs", first)
    assert 0.79 < first < second < fraction("National teams", second)


def test_with_photos_the_pictures_get_most_of_the_bar():
    at = 0.0
    for message in ("NHL rosters: VGK (32/32)", "Photos and logos: choosing the pictures",
                    "Saved as \"x\" in BLES021530209", "Photos and logos: reading picture templates from your game",
                    "Photos and logos: making 900 pictures (12 are installed already)",
                    "Photos and logos: 450 of 900 pictures made", "Photos and logos: 900 of 900 pictures made",
                    "Photos and logos: 897 pictures installed, 3 could not be downloaded"):
        value = fraction(message, at, photos=True)
        assert value is not None and value >= at, message
        at = value
        if message.startswith("Saved as"):
            assert abs(at - 0.4) < 1e-9
        if '450 of 900' in message:
            assert 0.65 < at < 0.75
    assert abs(at - 1.0) < 1e-9


def test_every_message_of_a_real_update_is_understood_in_order(base_bytes, data, pack):
    """Whatever the engine says while building must map to progress that only goes up."""
    said = ["Starting from \"ROSTER2526\" (BLES021530202)", "Data pack: downloaded the latest",
            "NHL rosters: ANA (1/32)", "NHL rosters: VGK (32/32)",
            "NHL: checking players the roster lists leave out (1/127)",
            "NHL: checking players the roster lists leave out (121/127)"]
    full = Data(nhl_players=data.nhl_players, ea_ratings=data.ea_ratings, iihf=data.iihf,
                season_year=data.season_year, leagues=pack['leagues'])
    pipeline.build(base_bytes, full, steps=pipeline.steps_for(pack), progress=said.append)
    said.append("Saved as \"x\" in BLES021530209")
    at = 0.0
    for message in said:
        value = fraction(message, at)
        if value is not None:
            assert value >= at, message
            at = value
        else:
            assert is_remark(message), f"neither a stage nor a known remark: {message}"
    assert at == 1.0
