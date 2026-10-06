"""Export only SYS-DATA (pipeline.export_sysdata): a roster file is updated without RPCS3 or a save folder."""
import os

import pytest

from legacy_roster import layout, pipeline


def test_a_roster_file_becomes_a_new_sysdata_in_a_new_folder_and_the_original_is_untouched(base_dir, data, tmp_path):
    source = os.path.join(base_dir, 'SYS-DATA')
    before = open(source, 'rb').read()
    res = pipeline.export_sysdata(source, pipeline.CORE_STEPS, data=data, out_root=str(tmp_path))
    assert res.build.ok and res.exported and os.path.isfile(res.exported)
    assert os.path.basename(res.exported) == 'SYS-DATA' and os.path.dirname(os.path.dirname(res.exported)) == str(tmp_path)
    assert open(res.exported, 'rb').read() == pipeline.build(before, data, pipeline.CORE_STEPS).data      # what an update makes
    assert open(source, 'rb').read() == before                                                         # the source is not touched
    assert res.saved_where() == res.exported and res.art_line() is None
    again = pipeline.export_sysdata(res.exported, pipeline.CORE_STEPS, data=data, out_root=str(tmp_path))
    assert again.exported != res.exported and open(again.exported, 'rb').read() == open(res.exported, 'rb').read()   # rule 4


def test_a_file_that_is_no_community_roster_is_refused_and_nothing_is_written(tmp_path):
    bad = tmp_path / 'SYS-DATA'
    bad.write_bytes(b'not a roster')
    with pytest.raises((layout.LayoutError, ValueError, KeyError)):
        pipeline.export_sysdata(str(bad), pipeline.CORE_STEPS, out_root=str(tmp_path / 'out'))
    assert not (tmp_path / 'out').exists()
    with pytest.raises(FileNotFoundError):
        pipeline.export_sysdata(str(tmp_path / 'missing'), pipeline.CORE_STEPS)
