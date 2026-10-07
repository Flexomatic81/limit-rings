import json
import os
import stat
from datetime import date

from limit_rings.state import load_state, new_state, prune_state, save_state


def test_missing_file_gives_fresh_state(tmp_path):
    assert load_state(tmp_path / "state.json") == new_state()


def test_corrupt_or_foreign_file_gives_fresh_state(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{broken")
    assert load_state(p) == new_state()
    p.write_text('{"version": 99}')
    assert load_state(p) == new_state()
    p.write_text("[1, 2]")
    assert load_state(p) == new_state()


def test_roundtrip_and_private_mode(tmp_path):
    p = tmp_path / "state.json"
    s = new_state()
    s["claude"]["seen"]["m|r"] = {"ts": "2026-10-01T10:00:00+00:00", "u": [1, 2, 3, 4]}
    save_state(p, s)
    assert load_state(p) == s
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600


def test_prune_drops_old_seen_ids_sessions_and_buckets():
    s = new_state()
    new = {"ts": "2026-10-01T10:00:00+00:00", "u": [0, 0, 0, 0]}
    s["claude"]["seen"] = {"old|1": {"ts": "2026-09-01T10:00:00+00:00", "u": [0, 0, 0, 0]}, "new|1": new}
    s["codex"]["sessions"] = {"old": {"total": 1, "day": "2025-01-01"}, "new": {"total": 1, "day": "2026-10-01"}}
    s["codex"]["buckets"] = {"2025-01-01": {"input": 1}, "2026-10-01": {"input": 1}}
    prune_state(s, date(2026, 10, 14))
    assert s["claude"]["seen"] == {"new|1": new}
    assert list(s["codex"]["sessions"]) == ["new"]
    assert list(s["codex"]["buckets"]) == ["2026-10-01"]


def _state_with(provider, **changes):
    s = new_state()
    s[provider].update(changes)
    return s


def test_load_state_fills_missing_keys(tmp_path):
    p = tmp_path / "state.json"
    p.write_text('{"version":1,"claude":{},"codex":{}}')
    assert load_state(p) == new_state()


def test_load_state_rejects_wrong_shapes(tmp_path):
    p = tmp_path / "state.json"
    good_seen = {"ts": "2026-10-01T10:00:00+00:00", "u": [1, 2, 3, 4]}
    good_limits = {"limits": [], "source": "oauth", "updated_at": 1.0}
    bad_states = [
        _state_with("claude", seen=None),
        _state_with("claude", seen={"a|b": {"u": [1, 2, 3, 4]}}),                       # without ts
        _state_with("claude", seen={"a|b": {"ts": "x", "u": [1, 2, 3]}}),               # u too short
        _state_with("claude", seen={"a|b": {"ts": "x", "u": [1, 2, 3, "4"]}}),
        _state_with("claude", seen={"a|b": "broken"}),
        _state_with("claude", files=[]),
        _state_with("claude", buckets=None),
        _state_with("claude", limits={"limits": []}),                                    # without updated_at
        _state_with("claude", limits={"limits": [], "updated_at": "yesterday"}),
        _state_with("claude", limits={"updated_at": 1.0}),                               # without limits
        _state_with("claude", oauth_last_attempt="now"),
        _state_with("claude", oauth_pause=None),
        _state_with("claude", limits={"limits": [], "updated_at": 1.0, "extra": "lots"}),
        _state_with("codex", oauth_pause={"until": "soon", "failures": 1}),
        _state_with("codex", oauth_pause={"until": None, "failures": -1}),
        _state_with("codex", oauth_pause={"until": None}),
        _state_with("codex", sessions={"s": {"total": 1}}),                              # without day
        _state_with("codex", sessions={"s": {"total": "1", "day": "2026-10-01"}}),
        _state_with("codex", sessions=None),
        _state_with("codex", limits={"limits": None, "updated_at": 1.0}),
    ]
    for bad in bad_states:
        p.write_text(json.dumps(bad))
        assert load_state(p) == new_state(), bad
    ok = new_state()
    ok["claude"].update(seen={"a|b": good_seen}, limits=good_limits, oauth_last_attempt=5.0,
                        oauth_pause={"until": 9.0, "failures": 2})
    ok["codex"].update(sessions={"s": {"total": 1, "day": "2026-10-01"}},
                       limits={"limits": [], "plan": None, "updated_at": 2})
    p.write_text(json.dumps(ok))
    assert load_state(p) == ok


def test_load_state_rejects_non_dict_provider_section(tmp_path):
    p = tmp_path / "state.json"
    p.write_text('{"version":1,"claude":null,"codex":{}}')
    assert load_state(p) == new_state()


def test_notified_section_defaults_and_validation(tmp_path):
    p = tmp_path / "state.json"
    old = new_state()
    del old["notified"]
    p.write_text(json.dumps(old))
    assert load_state(p)["notified"] == {}
    for bad in [None, [], {"claude:five_hour": None}, {"claude:five_hour": {"level": "80", "resets_at": None}},
                {"claude:five_hour": {"level": 80, "resets_at": "tomorrow"}},
                {"claude:five_hour": {"level": 80, "resets_at": None, "minutes": "5 h"}}]:
        s = new_state()
        s["notified"] = bad
        p.write_text(json.dumps(s))
        assert load_state(p) == new_state()
    good = new_state()
    good["notified"] = {"claude:five_hour": {"level": 95, "resets_at": 1791122400},
                        "codex:primary": {"level": 80, "resets_at": None, "minutes": 10080}}
    p.write_text(json.dumps(good))
    assert load_state(p) == good


def test_history_section_defaults_and_validation(tmp_path):
    p = tmp_path / "state.json"
    old = new_state()
    del old["history"]
    p.write_text(json.dumps(old))
    assert load_state(p)["history"] == {}
    for bad in [None, {"claude:five_hour": None}, {"claude:five_hour": {"resets_at": None, "points": None}},
                {"claude:five_hour": {"resets_at": None, "points": [[1, "x"]]}},
                {"claude:five_hour": {"resets_at": None, "points": [[1]]}},
                {"claude:five_hour": {"resets_at": None, "minutes": 3.5, "points": []}}]:
        s = new_state()
        s["history"] = bad
        p.write_text(json.dumps(s))
        assert load_state(p) == new_state()
    good = new_state()
    good["history"] = {"claude:five_hour": {"resets_at": 1791122400, "points": [[1791100000.5, 10.0]]},
                       "codex:primary": {"resets_at": None, "minutes": 300, "points": []}}
    p.write_text(json.dumps(good))
    assert load_state(p) == good


def test_old_state_without_hourly_requests_a_backfill(tmp_path):
    p = tmp_path / "state.json"
    old = new_state()
    del old["claude"]["hourly"], old["claude"]["hourly_backfill"]
    old["claude"]["seen"] = {"m|r": {"ts": "2026-10-01T10:00:00+00:00", "u": [1, 2, 3, 4]}}
    old["claude"]["files"] = {"/x/s.jsonl": {"offset": 10, "inode": 1}}
    p.write_text(json.dumps(old))
    loaded = load_state(p)
    assert loaded["claude"]["hourly"] == {} and loaded["claude"]["hourly_backfill"] is True
    assert loaded["claude"]["seen"] == old["claude"]["seen"]  # the rest is kept
    assert new_state()["claude"]["hourly_backfill"] is False
    for bad in [None, {"1791100800": None}, {"1791100800": {"p": {}, "m": None}},
                {"1791100800": {"p": {"website": "x"}, "m": {}}}]:
        s = new_state()
        s["claude"]["hourly"] = bad
        p.write_text(json.dumps(s))
        assert load_state(p) == new_state()
