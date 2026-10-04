import json

from agent_stats.sources.codex_logs import read_events


def token_count(ts, total, last_in=100, cached=60, out=10, used=8.0, info=True):
    payload = {"type": "token_count",
               "rate_limits": {"limit_id": "codex",
                               "primary": {"used_percent": used, "window_minutes": 10080,
                                           "resets_at": 1791280728},
                               "secondary": None, "plan_type": "plus"}}
    if info:
        payload["info"] = {
            "total_token_usage": {"total_tokens": total},
            "last_token_usage": {"input_tokens": last_in, "cached_input_tokens": cached,
                                 "cache_write_input_tokens": 0, "output_tokens": out,
                                 "reasoning_output_tokens": 3, "total_tokens": last_in + out}}
    else:
        payload["info"] = None
    return json.dumps({"timestamp": ts, "type": "event_msg", "payload": payload})


def write(path, *lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write("\n".join(lines) + "\n")


def test_maps_last_token_usage_without_double_counting_cache(tmp_path):
    f = tmp_path / "2026" / "09" / "29" / "rollout-a.jsonl"
    write(f, json.dumps({"timestamp": "2026-09-29T19:22:41Z", "type": "session_meta", "payload": {}}),
          token_count("2026-09-29T19:22:48.952Z", total=110))
    res = read_events(tmp_path, {}, {})
    assert len(res.events) == 1
    ev = res.events[0]
    assert (ev.input, ev.cache_read, ev.output, ev.cache_write) == (40, 60, 10, 0)
    assert ev.input + ev.cache_read + ev.output + ev.cache_write == 110


def meta(session_id):
    return json.dumps({"timestamp": "2026-09-29T19:22:41Z", "type": "session_meta",
                       "payload": {"id": session_id}})


def test_skips_repeated_totals_and_events_without_info(tmp_path):
    f = tmp_path / "rollout-a.jsonl"
    write(f, token_count("2026-09-29T19:00:00Z", total=110),
          token_count("2026-09-29T19:00:01Z", total=110),          # repetition
          token_count("2026-09-29T19:00:02Z", total=0, info=False),  # limits only
          token_count("2026-09-29T19:00:03Z", total=230))
    files, sessions = {}, {}
    res = read_events(tmp_path, files, sessions)
    assert len(res.events) == 2
    assert sessions[str(f)] == {"total": 230, "day": "2026-09-29"}  # without session_meta: path


def test_genuine_truncation_does_not_double_count(tmp_path):
    f = tmp_path / "rollout-a.jsonl"
    write(f, meta("sess-1"), token_count("2026-09-29T19:00:00Z", total=110),
          token_count("2026-09-29T19:00:05Z", total=230))
    files, sessions = {}, {}
    read_events(tmp_path, files, sessions)
    f.write_text(meta("sess-1") + "\n" + token_count("2026-09-29T19:00:00Z", total=110) + "\n")
    assert read_events(tmp_path, files, sessions).events == []


def test_moved_or_copied_session_is_not_counted_twice(tmp_path):
    a = tmp_path / "2026" / "09" / "29" / "rollout-a.jsonl"
    write(a, meta("sess-1"), token_count("2026-09-29T19:22:48Z", total=110))
    files, sessions = {}, {}
    assert len(read_events(tmp_path, files, sessions).events) == 1

    b = tmp_path / "2026" / "09" / "30" / "rollout-a.jsonl"
    b.parent.mkdir(parents=True)
    b.write_bytes(a.read_bytes())
    a.unlink()                                            # moved
    assert read_events(tmp_path, files, sessions).events == []
    (tmp_path / "copy.jsonl").write_bytes(b.read_bytes())  # copied
    assert read_events(tmp_path, files, sessions).events == []
    assert sessions["sess-1"]["total"] == 110
    assert str(a) not in files


def test_latest_rate_limits_win_across_files(tmp_path):
    write(tmp_path / "a" / "rollout-1.jsonl", token_count("2026-09-30T10:00:00Z", total=1, used=20.0))
    write(tmp_path / "b" / "rollout-2.jsonl", token_count("2026-09-29T10:00:00Z", total=1, used=5.0))
    res = read_events(tmp_path, {}, {})
    assert res.limits[0]["used_percent"] == 20.0
    assert res.plan == "plus"
    assert res.limits_ts.isoformat() == "2026-09-30T10:00:00+00:00"


def test_invalid_lines_are_counted_not_fatal(tmp_path):
    write(tmp_path / "rollout-a.jsonl", "{broken",
          json.dumps({"timestamp": "2026-09-29T19:00:00Z", "type": "event_msg",
                      "payload": {"type": "token_count",
                                  "info": {"total_token_usage": {"total_tokens": 5},
                                           "last_token_usage": {"input_tokens": "x"}}}}),
          token_count("2026-09-29T19:00:03Z", total=230))
    res = read_events(tmp_path, {}, {})
    assert res.invalid == 2
    assert len(res.events) == 1


def test_pathological_line_is_counted_invalid_and_offsets_advance(tmp_path):
    f = tmp_path / "rollout-a.jsonl"
    write(f, token_count("2026-09-29T19:00:00Z", total=100), "[" * 200_000,
          token_count("2026-09-29T19:00:03Z", total=230))
    files = {}
    res = read_events(tmp_path, files, {})
    assert res.invalid == 1
    assert len(res.events) == 2
    assert files[str(f)]["offset"] == f.stat().st_size
