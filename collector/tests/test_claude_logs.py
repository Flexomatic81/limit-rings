import json

from agent_stats.sources.claude_logs import parse_line, read_events


def usage_line(msg_id="msg_1", req="req_1", ts="2026-10-03T17:19:57.005Z", **usage):
    u = {"input_tokens": 6, "cache_creation_input_tokens": 100,
         "cache_read_input_tokens": 50, "output_tokens": 7}
    u.update(usage)
    return json.dumps({"type": "assistant", "timestamp": ts, "requestId": req,
                       "message": {"id": msg_id, "model": "claude-opus-4-7", "usage": u}})


def test_parse_line_maps_usage_fields():
    key, ev = parse_line(usage_line())
    assert key == "msg_1|req_1"
    assert (ev.input, ev.output, ev.cache_read, ev.cache_write) == (6, 7, 50, 100)
    assert ev.ts.isoformat() == "2026-10-03T17:19:57.005000+00:00"


def test_parse_line_without_usage_returns_none():
    assert parse_line(json.dumps({"type": "user", "message": {"role": "user"}})) is None
    assert parse_line(json.dumps({"type": "summary"})) is None


def test_parse_line_null_fields_count_as_zero():
    _, ev = parse_line(usage_line(cache_read_input_tokens=None))
    assert ev.cache_read == 0


def test_parse_line_rejects_garbage():
    for bad in ["{broken", "[1]", usage_line(output_tokens="viel"),
                json.dumps({"timestamp": "2026-10-03T00:00:00Z", "message": {"id": "m", "usage": [1]}})]:
        try:
            parse_line(bad)
        except ValueError:
            continue
        raise AssertionError(f"no ValueError for {bad!r}")


def test_read_events_dedupes_repeated_blocks_and_counts_invalid(tmp_path):
    proj = tmp_path / "-home-x-proj"
    (proj / "sess" / "subagents").mkdir(parents=True)
    (proj / "sess.jsonl").write_text(
        "\n".join([usage_line(), usage_line(), usage_line(msg_id="msg_2"), "{broken",
                   json.dumps({"type": "user"})]) + "\n")
    (proj / "sess" / "subagents" / "agent-a.jsonl").write_text(usage_line(msg_id="msg_3") + "\n")

    files, seen = {}, {}
    res = read_events(tmp_path, files, seen)
    assert len(res.events) == 3
    assert res.invalid == 1
    assert set(seen) == {"msg_1|req_1", "msg_2|req_1", "msg_3|req_1"}
    assert seen["msg_1|req_1"]["ts"][:10] == "2026-10-03"
    assert seen["msg_1|req_1"]["u"] == [6, 7, 50, 100]

    res2 = read_events(tmp_path, files, seen)
    assert res2.events == []


def test_streaming_snapshots_count_final_usage_within_and_across_runs(tmp_path):
    f = tmp_path / "p" / "s.jsonl"
    f.parent.mkdir()
    f.write_text(usage_line(output_tokens=8) + "\n" + usage_line(output_tokens=300) + "\n")
    files, seen = {}, {}
    res = read_events(tmp_path, files, seen)
    assert sum(e.output for e in res.events) == 300
    assert sum(e.cache_write for e in res.events) == 100  # unchanged fields not counted twice

    with f.open("a") as fh:
        fh.write(usage_line(output_tokens=3256, ts="2026-10-04T09:00:00Z") + "\n"
                 + usage_line(output_tokens=5) + "\n")
    res2 = read_events(tmp_path, files, seen)
    assert [(e.input, e.output, e.cache_read, e.cache_write) for e in res2.events] == [(0, 2956, 0, 0)]
    assert res2.events[0].ts.isoformat() == "2026-10-03T17:19:57.005000+00:00"  # day of the first line


def test_truncated_file_is_reread_without_double_counting(tmp_path):
    f = tmp_path / "p" / "s.jsonl"
    f.parent.mkdir()
    f.write_text(usage_line() + "\n" + usage_line(msg_id="msg_2") + "\n")
    files, seen = {}, {}
    read_events(tmp_path, files, seen)

    f.write_text(usage_line() + "\n")  # truncated, old content
    res = read_events(tmp_path, files, seen)
    assert res.events == []


def test_deleted_files_disappear_from_state(tmp_path):
    f = tmp_path / "p" / "s.jsonl"
    f.parent.mkdir()
    f.write_text(usage_line() + "\n")
    files, seen = {}, {}
    read_events(tmp_path, files, seen)
    assert str(f) in files

    f.unlink()
    read_events(tmp_path, files, seen)
    assert files == {}


def test_locked_directory_is_reported_and_keeps_offsets(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    f = d / "s.jsonl"
    f.write_text(usage_line() + "\n")
    files, seen = {}, {}
    read_events(tmp_path, files, seen)
    d.chmod(0)
    try:
        res = read_events(tmp_path, files, seen)
    finally:
        d.chmod(0o755)
    assert res.unreadable == 1
    assert str(f) in files


def test_missing_root_is_not_an_error(tmp_path):
    res = read_events(tmp_path / "does-not-exist", {}, {})
    assert res.events == [] and res.invalid == 0


def test_pathological_line_is_counted_invalid_and_offsets_advance(tmp_path):
    f = tmp_path / "p" / "s.jsonl"
    f.parent.mkdir()
    f.write_text("\n".join([usage_line(), "[" * 200_000, usage_line(msg_id="msg_2")]) + "\n")
    files, seen = {}, {}
    res = read_events(tmp_path, files, seen)
    assert res.invalid == 1
    assert len(res.events) == 2
    assert files[str(f)]["offset"] == f.stat().st_size
    assert read_events(tmp_path, files, seen).invalid == 0


def test_unexpected_parse_error_is_counted_invalid(tmp_path, monkeypatch):
    import agent_stats.sources.claude_logs as mod
    real = mod.parse_line
    def parse(line):
        if "msg_bad" in line:
            raise OverflowError("extreme timestamp")
        return real(line)
    monkeypatch.setattr(mod, "parse_line", parse)
    f = tmp_path / "p" / "s.jsonl"
    f.parent.mkdir()
    f.write_text("\n".join([usage_line(msg_id="msg_bad"), usage_line()]) + "\n")
    res = read_events(tmp_path, {}, {})
    assert res.invalid == 1 and len(res.events) == 1


def test_model_and_cwd_are_carried_including_streaming_deltas(tmp_path):
    def line(out):
        return json.dumps({"type": "assistant", "timestamp": "2026-10-03T17:19:57.005Z", "requestId": "r",
                           "cwd": "/home/user/projects/website/frontend",
                           "message": {"id": "m", "model": "claude-opus-5-5",
                                       "usage": {"input_tokens": 1, "output_tokens": out}}})
    f = tmp_path / "p" / "s.jsonl"
    f.parent.mkdir()
    f.write_text(line(8) + "\n" + line(300) + "\n")
    res = read_events(tmp_path, {}, {})
    assert [(e.output, e.model, e.project) for e in res.events] == [
        (8, "claude-opus-5-5", "/home/user/projects/website/frontend"),
        (292, "claude-opus-5-5", "/home/user/projects/website/frontend")]
