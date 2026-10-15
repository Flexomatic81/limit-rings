import json
import os
import stat

import pytest

from limit_rings.fsutil import write_json_atomic


def test_writes_json_with_private_modes(tmp_path):
    target = tmp_path / "cache" / "stats.json"
    write_json_atomic(target, {"a": 1})

    assert json.loads(target.read_text()) == {"a": 1}
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(target.parent).st_mode) == 0o700


def test_replaces_existing_file_without_leftovers(tmp_path):
    target = tmp_path / "stats.json"
    write_json_atomic(target, {"v": 1})
    write_json_atomic(target, {"v": 2})

    assert json.loads(target.read_text()) == {"v": 2}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["stats.json"]


def test_a_failed_write_keeps_the_old_file_and_leaves_no_temp_file(tmp_path):
    target = tmp_path / "stats.json"
    write_json_atomic(target, {"v": 1})
    with pytest.raises(TypeError):
        write_json_atomic(target, {"v": object()})  # not serialisable: fails after the temp file exists
    assert json.loads(target.read_text()) == {"v": 1}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["stats.json"]
