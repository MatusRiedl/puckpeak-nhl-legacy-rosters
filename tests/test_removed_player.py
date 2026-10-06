"""The player the game's own save left behind (builder.drop_removed_player): the community's 2026-27
roster names his entry and link rows in two table headers; Season mode crashed on his link once our
update made him a free agent."""
import struct

from legacy_roster import builder, layout as L
from legacy_roster.roster import Roster
from legacy_roster.verify import verify


def with_markers(base_bytes):
    """The base roster with a leftover player: the first club entry of a player with no contract team, named
    in the entry and link table headers the way the community roster does it."""
    R = Roster(base_bytes)
    e = next(i for i in range(R.U.cur_rec) if R.U.get(i, 'BSXd') < 32)
    link = R.U.get(e, 'TWSX')
    prow = R.p_by_id[R.link_to_pid[link]]
    R.P.set(prow, 'BSXd', 0)
    link_row = next(i for i in range(R.C.cur_rec) if R.C.get(i, 'qEfv') == link)
    struct.pack_into('>I', R.U.header, 0x18, 0x10000 | e)
    struct.pack_into('>I', R.C.header, 0x18, 0x10000 | link_row)
    return R, e, link, prow


def test_the_leftover_player_and_his_link_are_removed_and_the_markers_cleared(base_bytes):
    R, e, link, prow = with_markers(base_bytes)
    entries, links, name = R.U.cur_rec, R.C.cur_rec, R.name(prow)
    assert builder.drop_removed_player(R) == name
    assert (R.U.cur_rec, R.C.cur_rec) == (entries - 1, links - 1)
    assert link not in R.link_to_pid and R.p_by_id[R.P.get(prow, 'zIBw')] == prow      # the record stays
    assert all(bytes(R.f[t].header[0x18:0x1C]) == b'\x00\x00\xff\xff' for t in R.f.tables)
    assert R.link_to_pid.get(link) is None and R.entries_by_pid.get(R.P.get(prow, 'zIBw')) is None


def test_a_roster_without_markers_is_left_alone(base_bytes):
    R = Roster(base_bytes)
    before = (R.U.cur_rec, R.C.cur_rec)
    assert builder.drop_removed_player(R) is None and (R.U.cur_rec, R.C.cur_rec) == before


def test_a_marked_player_on_a_team_with_a_contract_or_on_the_free_agent_list_stays(base_bytes):
    R, e, link, prow = with_markers(base_bytes)
    R.P.set(prow, 'BSXd', R.U.get(e, 'BSXd') + 1)          # he has a contract team: a real player
    assert builder.drop_removed_player(R) is None and link in R.link_to_pid
    R, e, link, prow = with_markers(base_bytes)
    R.Q.add_record({'TWSX': link})                         # he is on the free-agent list: not removed
    R.reindex()
    assert builder.drop_removed_player(R) is None
    # the markers go in every case
    assert all(bytes(R.f[t].header[0x18:0x1C]) == b'\x00\x00\xff\xff' for t in R.f.tables)


def test_a_built_roster_that_still_names_a_removed_row_fails_the_check(base_bytes):
    R = Roster(base_bytes)
    struct.pack_into('>I', R.C.header, 0x18, 0x10000 | 5)
    problems, _ = verify(R.f.build(), Roster(base_bytes))
    assert any("still names a removed row" in p for p in problems)


def test_a_roster_with_stale_markers_gets_its_free_agents_on_new_links(base_bytes, data):
    """A roster made by 0.8.0 from the community roster still has the markers, but the rows moved and the
    removed player is a free agent on his old link: every free agent gets a new link so that Season mode
    does not crash on it again; the next run, with the markers gone, leaves the links alone."""
    from legacy_roster import pipeline
    R, e, link, prow = with_markers(base_bytes)
    R.P.set(prow, 'BSXd', R.U.get(e, 'BSXd') + 1)          # no ghost: the markers point at an ordinary player
    marked = R.f.build()
    old_links = {R.Q.get(i, 'TWSX') for i in range(R.Q.cur_rec)}
    first = pipeline.build(marked, data)
    assert first.ok, first.problems[:3]
    F = Roster(first.data)
    new_links = {F.Q.get(i, 'TWSX') for i in range(F.Q.cur_rec)}
    assert F.Q.cur_rec >= len(old_links) and not (new_links & old_links)
    assert all(bytes(F.f[t].header[0x18:0x1C]) == b'\x00\x00\xff\xff' for t in F.f.tables)
    assert pipeline.build(first.data, data).data == first.data           # nothing to relink the second time
