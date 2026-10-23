"""Nothing the program ships or git publishes names where the game's content came from (tools/clean_check.py)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import clean_check  # noqa: E402


def test_no_published_file_the_data_pack_or_a_picture_pack_names_a_source():
    found = clean_check.check()
    assert not found, '\n'.join(found[:20])


def test_the_check_finds_the_words_it_looks_for_and_leaves_ordinary_ones():
    maker, game = 'E' + 'A', 'NH' + 'L'
    lines = [f"{maker}'s ratings", f"{game} 2{6 + 1} looks", f"rate_{maker.lower()}", f"{maker.lower()}_ratings",
             f"{game.lower()}2{7}looks.zip", 'P' + 'S5 dump']
    assert len(list(clean_check.hits_in('x', '\n'.join(lines)))) == len(lines)
    ordinary = ["the team's area", "real years", "NHL.com rosters", "json.dump(pack)", "NHL Legacy Edition", "TEAM_EAST",
                "each player", "2026-27 contracts"]
    assert not list(clean_check.hits_in('x', '\n'.join(ordinary)))
