import os

from limit_rings.sources.jsonl import list_jsonl, prune_missing, read_new_lines


def test_reads_complete_lines_and_keeps_partial_line(tmp_path):
    f = tmp_path / "a.jsonl"
    f.write_bytes(b'{"n":1}\n{"n":2}\n{"n":3')

    lines, st = read_new_lines(f, None)
    assert lines == ['{"n":1}', '{"n":2}']
    assert st["offset"] == len(b'{"n":1}\n{"n":2}\n')
    assert st["inode"] == os.stat(f).st_ino

    with f.open("ab") as fh:
        fh.write(b'}\n')
    lines, st = read_new_lines(f, st)
    assert lines == ['{"n":3}']


def test_no_new_data_returns_nothing(tmp_path):
    f = tmp_path / "a.jsonl"
    f.write_bytes(b'{"n":1}\n')
    _, st = read_new_lines(f, None)
    lines, st2 = read_new_lines(f, st)
    assert lines == []
    assert st2 == st


def test_truncated_file_is_read_from_start(tmp_path):
    f = tmp_path / "a.jsonl"
    f.write_bytes(b'{"n":1}\n{"n":2}\n')
    _, st = read_new_lines(f, None)
    f.write_bytes(b'{"n":9}\n')
    lines, _ = read_new_lines(f, st)
    assert lines == ['{"n":9}']


def test_replaced_file_with_new_inode_is_read_from_start(tmp_path):
    f = tmp_path / "a.jsonl"
    f.write_bytes(b'{"n":1}\n')
    _, st = read_new_lines(f, None)
    st = {**st, "inode": st["inode"] + 1}
    lines, _ = read_new_lines(f, st)
    assert lines == ['{"n":1}']


def test_blank_lines_and_invalid_utf8_do_not_raise(tmp_path):
    f = tmp_path / "a.jsonl"
    f.write_bytes(b'\n\xff\xfe\n{"n":1}\n')
    lines, _ = read_new_lines(f, None)
    assert lines[-1] == '{"n":1}'
    assert len(lines) == 2  # blank line is dropped, broken line stays as text (JSON error later)


def test_list_jsonl_reports_unreadable_directories(tmp_path):
    (tmp_path / "ok").mkdir()
    (tmp_path / "ok" / "a.jsonl").write_text("")
    (tmp_path / "ok" / "note.txt").write_text("")
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "b.jsonl").write_text("")
    locked.chmod(0)
    try:
        files, failed = list_jsonl(tmp_path)
    finally:
        locked.chmod(0o755)
    assert files == [tmp_path / "ok" / "a.jsonl"]
    assert failed == [locked]
    assert list_jsonl(tmp_path / "missing") == ([], [])


def test_prune_missing_keeps_entries_under_failed_directories(tmp_path):
    files = {str(tmp_path / "gone.jsonl"): {}, str(tmp_path / "locked" / "b.jsonl"): {},
             str(tmp_path / "here.jsonl"): {}}
    prune_missing(files, {str(tmp_path / "here.jsonl")}, [tmp_path / "locked"])
    assert sorted(files) == [str(tmp_path / "here.jsonl"), str(tmp_path / "locked" / "b.jsonl")]
