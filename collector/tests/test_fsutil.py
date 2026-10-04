import json
import os
import stat

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
