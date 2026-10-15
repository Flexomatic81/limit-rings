import json
from datetime import datetime, timedelta

from collect_helpers import BERLIN, NOW, claude_line, codex_api, codex_auth, codex_line, make_paths, ok_fetch

from limit_rings import collect
from limit_rings.collect import run, run_safely
from limit_rings.sources import claude_limits, claude_logs


def hot(token, timeout=10.0):
    return {"five_hour": {"utilization": 85.0, "resets_at": None}}


def test_full_run_writes_valid_stats(tmp_path):
    p = make_paths(tmp_path)
    (p.claude_root / "proj").mkdir()
    (p.claude_root / "proj" / "s.jsonl").write_text(
        claude_line("m1", "2026-10-03T10:00:00Z") + "\n" + claude_line("m1", "2026-10-03T10:00:00Z") + "\n"
    )
    (p.codex_root / "rollout-a.jsonl").write_text(codex_line("2026-10-02T10:00:00Z", 500) + "\n")

    stats = run(p, NOW, BERLIN, fetch=ok_fetch)

    assert json.loads(p.stats_file.read_text()) == stats
    assert stats["schema"] == 2
    assert stats["generated_at"] == "2026-10-03T19:42:00+02:00"
    c, x = stats["providers"]["claude"], stats["providers"]["codex"]
    assert c["tokens"]["today"]["total"] == 11
    assert c["limits_source"] == "oauth" and c["plan"] == "pro" and c["errors"] == []
    assert "error" not in c
    assert [lim["id"] for lim in c["limits"]] == ["five_hour", "seven_day"]
    assert all("label" not in lim for lim in c["limits"])
    assert x["tokens"]["today"]["total"] == 0 and x["tokens"]["week"]["total"] == 500
    assert x["limits_source"] == "session_log" and x["plan"] == "plus"
    assert x["limits_updated_at"] == "2026-10-02T12:00:00+02:00"
    for prov in (c, x):
        assert len(prov["daily"]) == 30 and prov["daily"][-1]["date"] == "2026-10-03"
        assert len(prov["weekly"]) == 13 and prov["weekly"][-1]["date"] == "2026-09-28"
        assert len(prov["monthly"]) == 12 and prov["monthly"][-1]["date"] == "2026-10-01"
        for t in prov["tokens"].values():
            assert t["total"] == t["input"] + t["output"] + t["cache_read"] + t["cache_write"]


def test_second_run_is_incremental(tmp_path):
    p = make_paths(tmp_path)
    (p.claude_root / "proj").mkdir()
    f = p.claude_root / "proj" / "s.jsonl"
    f.write_text(claude_line("m1", "2026-10-03T10:00:00Z") + "\n")
    run(p, NOW, BERLIN, fetch=ok_fetch)
    with f.open("a") as fh:
        fh.write(claude_line("m2", "2026-10-03T11:00:00Z") + "\n")
    stats = run(p, NOW, BERLIN, fetch=ok_fetch)
    assert stats["providers"]["claude"]["tokens"]["today"]["total"] == 22


def test_next_day_without_new_events(tmp_path):
    p = make_paths(tmp_path)
    (p.claude_root / "proj").mkdir()
    (p.claude_root / "proj" / "s.jsonl").write_text(claude_line("m1", "2026-10-03T10:00:00Z") + "\n")
    run(p, NOW, BERLIN, fetch=ok_fetch)
    stats = run(p, datetime(2026, 10, 4, 0, 5, tzinfo=BERLIN), BERLIN, fetch=ok_fetch)
    c = stats["providers"]["claude"]
    assert c["tokens"]["today"]["total"] == 0
    assert c["daily"][-2] == {"date": "2026-10-03", "total": 11}
    assert c["weekly"][-1] == {"date": "2026-09-28", "total": 11}
    assert c["monthly"][-1] == {"date": "2026-10-01", "total": 11}


def test_provider_failure_is_isolated(tmp_path, monkeypatch):
    p = make_paths(tmp_path)
    (p.codex_root / "rollout-a.jsonl").write_text(codex_line("2026-10-03T10:00:00Z", 500) + "\n")

    def boom(*a, **k):
        raise RuntimeError("broken")

    monkeypatch.setattr(claude_logs, "read_events", boom)

    stats = run(p, NOW, BERLIN, fetch=ok_fetch)
    c, x = stats["providers"]["claude"], stats["providers"]["codex"]
    assert c["errors"] == [{"code": "logs_failed"}]
    assert c["limits_source"] == "oauth"  # limits still work
    assert x["errors"] == [] and x["tokens"]["today"]["total"] == 500


def test_corrupt_state_triggers_full_reread(tmp_path):
    p = make_paths(tmp_path)
    (p.claude_root / "proj").mkdir()
    (p.claude_root / "proj" / "s.jsonl").write_text(claude_line("m1", "2026-10-03T10:00:00Z") + "\n")
    run(p, NOW, BERLIN, fetch=ok_fetch)
    p.state_file.write_text("{broken")
    stats = run(p, NOW, BERLIN, fetch=ok_fetch)
    assert stats["providers"]["claude"]["tokens"]["today"]["total"] == 11


def test_stats_never_contain_token(tmp_path):
    p = make_paths(tmp_path)
    run(p, NOW, BERLIN, fetch=ok_fetch)
    assert "top-secret" not in p.stats_file.read_text()
    assert "top-secret" not in p.state_file.read_text()


def test_unreadable_transcript_is_reported_but_rest_counts(tmp_path):
    p = make_paths(tmp_path)
    (p.claude_root / "proj").mkdir()
    (p.claude_root / "proj" / "ok.jsonl").write_text(claude_line("m1", "2026-10-03T10:00:00Z") + "\n")
    bad = p.claude_root / "proj" / "bad.jsonl"
    bad.write_text(claude_line("m2", "2026-10-03T10:00:00Z") + "\n")
    bad.chmod(0)
    try:
        stats = run(p, NOW, BERLIN, fetch=ok_fetch)
    finally:
        bad.chmod(0o600)
    c = stats["providers"]["claude"]
    assert c["errors"] == [{"code": "logs_unreadable", "count": 1}]
    assert c["tokens"]["today"]["total"] == 11


def test_local_zone_prefers_tz_variable(monkeypatch):
    from limit_rings.paths import local_zone

    monkeypatch.setenv("TZ", "America/New_York")
    assert local_zone().key == "America/New_York"
    monkeypatch.setenv("TZ", "Does/Not_Exist")
    assert local_zone() is not None


def test_unexpected_limits_failure_still_records_attempt(tmp_path, monkeypatch):
    p = make_paths(tmp_path)

    def boom(*a, **k):
        raise RuntimeError("broken")

    monkeypatch.setattr(claude_limits, "resolve", boom)

    stats = run(p, NOW, BERLIN, fetch=ok_fetch)

    assert {"code": "limits_unavailable"} in stats["providers"]["claude"]["errors"]
    state = json.loads(p.state_file.read_text())
    assert state["claude"]["oauth_last_attempt"] == NOW.timestamp()


def test_unchanged_state_is_not_rewritten_but_stats_are(tmp_path):
    p = make_paths(tmp_path)
    (p.claude_root / "proj").mkdir()
    (p.claude_root / "proj" / "s.jsonl").write_text(claude_line("m1", "2026-10-03T10:00:00Z") + "\n")
    run(p, NOW, BERLIN, fetch=ok_fetch)
    state_mtime, stats_mtime = p.state_file.stat().st_mtime_ns, p.stats_file.stat().st_mtime_ns
    # Within the OAuth throttle and without new data, the state does not change.
    later = datetime(2026, 10, 3, 19, 43, tzinfo=BERLIN)
    stats = run(p, later, BERLIN, fetch=ok_fetch)
    assert p.state_file.stat().st_mtime_ns == state_mtime
    assert p.stats_file.stat().st_mtime_ns != stats_mtime
    assert stats["generated_at"] == "2026-10-03T19:43:00+02:00"


def test_changed_state_is_saved(tmp_path):
    p = make_paths(tmp_path)
    (p.claude_root / "proj").mkdir()
    f = p.claude_root / "proj" / "s.jsonl"
    f.write_text(claude_line("m1", "2026-10-03T10:00:00Z") + "\n")
    run(p, NOW, BERLIN, fetch=ok_fetch)
    with f.open("a") as fh:
        fh.write(claude_line("m2", "2026-10-03T11:00:00Z") + "\n")
    run(p, datetime(2026, 10, 3, 19, 43, tzinfo=BERLIN), BERLIN, fetch=ok_fetch)
    assert "m2|r" in json.loads(p.state_file.read_text())["claude"]["seen"]


def test_run_safely_quarantines_state_after_unexpected_crash(tmp_path, monkeypatch):
    p = make_paths(tmp_path)
    p.state_file.parent.mkdir(parents=True, exist_ok=True)
    p.state_file.write_text('{"broken": true}')
    monkeypatch.setattr(collect, "run", lambda *a, **k: (_ for _ in ()).throw(KeyError("x")))
    assert run_safely(p, NOW, BERLIN, notifier=lambda n: None) is None
    assert not p.state_file.exists()
    assert p.state_file.with_name("state.json.corrupt").read_text() == '{"broken": true}'


def test_run_safely_without_state_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(collect, "run", lambda *a, **k: (_ for _ in ()).throw(KeyError("x")))
    assert run_safely(make_paths(tmp_path), NOW, BERLIN, notifier=lambda n: None) is None


def test_run_without_notifier_leaves_the_notice_for_a_later_run(tmp_path):
    # A widget with notifications switched off must not use up a notice another widget would show.
    p = make_paths(tmp_path)
    run(p, NOW, BERLIN, fetch=hot)
    sent = []
    run(p, NOW + timedelta(minutes=1), BERLIN, fetch=hot, notifier=sent.append)
    assert len(sent) == 1


def test_auth_status_is_reported_for_claude_only(tmp_path):
    p = make_paths(tmp_path)
    stats = run(p, NOW, BERLIN, fetch=ok_fetch, notifier=lambda n: True)
    assert stats["providers"]["claude"]["auth"] == {"status": "ok", "expires_at": "2026-10-03T20:42:00+02:00"}
    assert "auth" not in stats["providers"]["codex"]
    p.credentials.unlink()
    stats = run(p, NOW, BERLIN, fetch=ok_fetch, notifier=lambda n: True)
    assert stats["providers"]["claude"]["auth"] == {"status": "missing", "expires_at": None}


def test_limit_notification_is_sent_once_per_window(tmp_path):
    p = make_paths(tmp_path)
    sent = []
    run(p, NOW, BERLIN, fetch=hot, notifier=sent.append)
    run(p, NOW + timedelta(minutes=1), BERLIN, fetch=hot, notifier=sent.append)
    assert [n.summary for n in sent] == ["Claude: 5-hour limit at 85 %"]


def test_notifier_failure_does_not_break_the_run(tmp_path):
    p = make_paths(tmp_path)

    def hot(token, timeout=10.0):
        return {"five_hour": {"utilization": 99.0, "resets_at": None}}

    def boom(notice):
        raise RuntimeError("broken")

    stats = run(p, NOW, BERLIN, fetch=hot, notifier=boom)
    assert stats["providers"]["claude"]["limits"][0]["used_percent"] == 99.0
    assert p.stats_file.exists()


def test_five_hour_forecast_appears_after_enough_samples(tmp_path):
    p = make_paths(tmp_path)
    values = iter([10.0, 15.0, 20.0])

    def rising(token, timeout=10.0):
        return {
            "five_hour": {"utilization": next(values), "resets_at": "2026-10-03T21:00:00+00:00"},
            "seven_day": {"utilization": 30.0, "resets_at": None},
        }

    first = run(p, NOW, BERLIN, fetch=rising, notifier=lambda n: True)
    assert "forecast" not in first["providers"]["claude"]["limits"][0]
    run(p, NOW + timedelta(minutes=6), BERLIN, fetch=rising, notifier=lambda n: True)
    stats = run(p, NOW + timedelta(minutes=12), BERLIN, fetch=rising, notifier=lambda n: True)
    five, week = stats["providers"]["claude"]["limits"]
    # 10 % in 12 min → 80 % to go → 96 min after the last data point
    assert five["forecast"] == {"status": "full", "eta": int((NOW + timedelta(minutes=12 + 96)).timestamp())}
    assert "forecast" not in week
    assert "forecast" not in p.state_file.read_text()  # forecast only in stats.json, not in the state


def test_codex_limits_come_from_api_when_logged_in(tmp_path):
    from dataclasses import replace

    p = make_paths(tmp_path)
    p = replace(p, codex_auth=codex_auth(p))
    (p.codex_root / "rollout-a.jsonl").write_text(codex_line("2026-09-29T10:00:00Z", 500) + "\n")
    stats = run(p, NOW, BERLIN, fetch=ok_fetch, codex_fetch=codex_api, notifier=lambda n: True)
    x = stats["providers"]["codex"]
    assert x["limits_source"] == "oauth" and x["plan"] == "plus"
    assert x["limits_updated_at"] == "2026-10-03T19:42:00+02:00"
    assert [(lim["window_minutes"], lim["used_percent"]) for lim in x["limits"]] == [(10080, 7.0)]
    assert "top-secret-codex" not in p.state_file.read_text() + p.stats_file.read_text()


def test_codex_falls_back_to_session_log_without_api(tmp_path):
    from dataclasses import replace

    p = make_paths(tmp_path)
    p = replace(p, codex_auth=codex_auth(p))
    (p.codex_root / "rollout-a.jsonl").write_text(codex_line("2026-10-03T10:00:00Z", 500) + "\n")

    def down(token, account_id, timeout=10.0):
        raise TimeoutError()

    x = run(p, NOW, BERLIN, fetch=ok_fetch, codex_fetch=down, notifier=lambda n: True)["providers"]["codex"]
    assert x["limits_source"] == "session_log" and x["errors"] == []
    assert x["limits"][0]["used_percent"] == 8.0
