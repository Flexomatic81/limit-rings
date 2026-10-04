import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from agent_stats.collect import Paths, run

BERLIN = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 10, 3, 19, 42, tzinfo=BERLIN)


def make_paths(tmp_path):
    p = Paths(
        claude_root=tmp_path / "claude" / "projects",
        codex_root=tmp_path / "codex" / "sessions",
        credentials=tmp_path / "claude" / ".credentials.json",
        statusline_cache=tmp_path / "cache" / "claude-statusline-limits.json",
        state_file=tmp_path / "cache" / "state.json",
        stats_file=tmp_path / "cache" / "stats.json",
    )
    p.claude_root.mkdir(parents=True)
    p.codex_root.mkdir(parents=True)
    p.credentials.write_text(json.dumps({"claudeAiOauth": {
        "accessToken": "top-secret", "expiresAt": int((NOW.timestamp() + 3600) * 1000),
        "subscriptionType": "pro"}}))
    return p


def claude_line(msg_id, ts, out=10):
    return json.dumps({"timestamp": ts, "requestId": "r", "message": {
        "id": msg_id, "usage": {"input_tokens": 1, "output_tokens": out,
                                "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}})


def codex_line(ts, total):
    return json.dumps({"timestamp": ts, "type": "event_msg", "payload": {
        "type": "token_count",
        "info": {"total_token_usage": {"total_tokens": total},
                 "last_token_usage": {"input_tokens": total, "cached_input_tokens": 0, "output_tokens": 0}},
        "rate_limits": {"primary": {"used_percent": 8.0, "window_minutes": 10080, "resets_at": 1791280728},
                        "secondary": None, "plan_type": "plus"}}})


def ok_fetch(token, timeout=10.0):
    return {"five_hour": {"utilization": 42.0, "resets_at": None},
            "seven_day": {"utilization": 18.0, "resets_at": None}}


def test_full_run_writes_valid_stats(tmp_path):
    p = make_paths(tmp_path)
    (p.claude_root / "proj").mkdir()
    (p.claude_root / "proj" / "s.jsonl").write_text(
        claude_line("m1", "2026-10-03T10:00:00Z") + "\n" + claude_line("m1", "2026-10-03T10:00:00Z") + "\n")
    (p.codex_root / "rollout-a.jsonl").write_text(codex_line("2026-10-02T10:00:00Z", 500) + "\n")

    stats = run(p, NOW, BERLIN, fetch=ok_fetch)

    assert json.loads(p.stats_file.read_text()) == stats
    assert stats["schema"] == 1
    assert stats["generated_at"] == "2026-10-03T19:42:00+02:00"
    c, x = stats["providers"]["claude"], stats["providers"]["codex"]
    assert c["tokens"]["today"]["total"] == 11
    assert c["limits_source"] == "oauth" and c["plan"] == "pro" and c["error"] is None
    assert [l["id"] for l in c["limits"]] == ["five_hour", "seven_day"]
    assert all("label" not in l for l in c["limits"])
    assert x["tokens"]["today"]["total"] == 0 and x["tokens"]["week"]["total"] == 500
    assert x["limits_source"] == "session_log" and x["plan"] == "plus"
    assert x["limits_updated_at"] == "2026-10-02T12:00:00+02:00"
    for prov in (c, x):
        assert len(prov["daily"]) == 30 and prov["daily"][-1]["date"] == "2026-10-03"
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


def test_provider_failure_is_isolated(tmp_path, monkeypatch):
    p = make_paths(tmp_path)
    (p.codex_root / "rollout-a.jsonl").write_text(codex_line("2026-10-03T10:00:00Z", 500) + "\n")

    import agent_stats.collect as collect_mod
    def boom(*a, **k):
        raise RuntimeError("broken")
    monkeypatch.setattr(collect_mod.claude_logs, "read_events", boom)

    stats = run(p, NOW, BERLIN, fetch=ok_fetch)
    c, x = stats["providers"]["claude"], stats["providers"]["codex"]
    assert c["error"] == "Claude data could not be processed"
    assert c["limits_source"] == "oauth"               # limits still work
    assert x["error"] is None and x["tokens"]["today"]["total"] == 500


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
    assert c["error"] == "1 file(s) unreadable – numbers incomplete"
    assert c["tokens"]["today"]["total"] == 11


def test_local_zone_prefers_tz_variable(monkeypatch):
    from agent_stats.collect import local_zone
    monkeypatch.setenv("TZ", "America/New_York")
    assert local_zone().key == "America/New_York"
    monkeypatch.setenv("TZ", "Does/Not_Exist")
    assert local_zone() is not None


def test_unexpected_limits_failure_still_records_attempt(tmp_path, monkeypatch):
    p = make_paths(tmp_path)
    import agent_stats.collect as collect_mod
    def boom(*a, **k):
        raise RuntimeError("broken")
    monkeypatch.setattr(collect_mod.claude_limits, "resolve", boom)

    stats = run(p, NOW, BERLIN, fetch=ok_fetch)

    assert "Claude limits unavailable" in stats["providers"]["claude"]["error"]
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


def test_main_quarantines_state_after_unexpected_crash(tmp_path, monkeypatch):
    import agent_stats.collect as collect_mod
    cache = tmp_path / ".cache" / "agent-stats"
    cache.mkdir(parents=True)
    (cache / "state.json").write_text("{}")
    monkeypatch.setattr(collect_mod.Path, "home", lambda: tmp_path)
    def boom(*a, **k):
        raise RuntimeError("broken")
    monkeypatch.setattr(collect_mod, "run", boom)

    assert collect_mod.main() == 1
    assert not (cache / "state.json").exists()
    assert (cache / "state.json.corrupt").exists()


def test_main_without_state_file_and_crash_still_returns_one(tmp_path, monkeypatch):
    import agent_stats.collect as collect_mod
    monkeypatch.setattr(collect_mod.Path, "home", lambda: tmp_path)
    def boom(*a, **k):
        raise RuntimeError("broken")
    monkeypatch.setattr(collect_mod, "run", boom)
    assert collect_mod.main() == 1


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

    def hot(token, timeout=10.0):
        return {"five_hour": {"utilization": 85.0, "resets_at": None}}

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
        return {"five_hour": {"utilization": next(values), "resets_at": "2026-10-03T21:00:00+00:00"},
                "seven_day": {"utilization": 30.0, "resets_at": None}}

    first = run(p, NOW, BERLIN, fetch=rising, notifier=lambda n: True)
    assert "forecast" not in first["providers"]["claude"]["limits"][0]
    run(p, NOW + timedelta(minutes=6), BERLIN, fetch=rising, notifier=lambda n: True)
    stats = run(p, NOW + timedelta(minutes=12), BERLIN, fetch=rising, notifier=lambda n: True)
    five, week = stats["providers"]["claude"]["limits"]
    # 10 % in 12 min → 80 % to go → 96 min after the last data point
    assert five["forecast"] == {"status": "full", "eta": int((NOW + timedelta(minutes=12 + 96)).timestamp())}
    assert "forecast" not in week
    assert "forecast" not in p.state_file.read_text()  # forecast only in stats.json, not in the state


def codex_auth(p):
    path = p.claude_root.parent.parent / "codex" / "auth.json"
    path.write_text(json.dumps({"tokens": {"access_token": "top-secret-codex", "account_id": "account-1"}}))
    return path


def codex_api(token, account_id, timeout=10.0):
    return {"plan_type": "plus", "rate_limit": {"primary_window": {
        "used_percent": 7, "limit_window_seconds": 604800, "reset_at": 1791628596}, "secondary_window": None}}


def test_codex_limits_come_from_api_when_logged_in(tmp_path):
    from dataclasses import replace
    p = make_paths(tmp_path)
    p = replace(p, codex_auth=codex_auth(p))
    (p.codex_root / "rollout-a.jsonl").write_text(codex_line("2026-09-29T10:00:00Z", 500) + "\n")
    stats = run(p, NOW, BERLIN, fetch=ok_fetch, codex_fetch=codex_api, notifier=lambda n: True)
    x = stats["providers"]["codex"]
    assert x["limits_source"] == "oauth" and x["plan"] == "plus"
    assert x["limits_updated_at"] == "2026-10-03T19:42:00+02:00"
    assert [(l["window_minutes"], l["used_percent"]) for l in x["limits"]] == [(10080, 7.0)]
    assert "top-secret-codex" not in p.state_file.read_text() + p.stats_file.read_text()


def test_codex_falls_back_to_session_log_without_api(tmp_path):
    from dataclasses import replace
    p = make_paths(tmp_path)
    p = replace(p, codex_auth=codex_auth(p))
    (p.codex_root / "rollout-a.jsonl").write_text(codex_line("2026-10-03T10:00:00Z", 500) + "\n")

    def down(token, account_id, timeout=10.0):
        raise TimeoutError()

    x = run(p, NOW, BERLIN, fetch=ok_fetch, codex_fetch=down, notifier=lambda n: True)["providers"]["codex"]
    assert x["limits_source"] == "session_log" and x["error"] is None
    assert x["limits"][0]["used_percent"] == 8.0


def week_fetch(token, timeout=10.0):
    return {"five_hour": {"utilization": 5.0, "resets_at": None},
            "seven_day": {"utilization": 30.0, "resets_at": "2026-10-06T04:00:00+00:00"}}


def project_line(msg_id, ts, cwd, out=10, model="claude-opus-5"):
    return json.dumps({"timestamp": ts, "requestId": "r", "cwd": cwd, "message": {
        "id": msg_id, "model": model, "usage": {"input_tokens": 1, "output_tokens": out}}})


def breakdown_setup(tmp_path):
    p = make_paths(tmp_path)
    repo = tmp_path / "work" / "website"
    (repo / ".git").mkdir(parents=True)
    (repo / "frontend").mkdir()
    (p.claude_root / "proj").mkdir()
    (p.claude_root / "proj" / "s.jsonl").write_text("\n".join([
        project_line("m1", "2026-10-03T10:00:00Z", str(repo / "frontend")),
        project_line("m2", "2026-09-28T10:00:00Z", str(repo)),               # before the weekly window
        project_line("m3", "2026-10-02T10:00:00Z", str(tmp_path / "scratch"), model="claude-sonnet-5"),
    ]) + "\n")
    return p


def test_breakdown_covers_the_claude_week_window(tmp_path):
    p = breakdown_setup(tmp_path)
    b = run(p, NOW, BERLIN, fetch=week_fetch, notifier=lambda n: True)["providers"]["claude"]["breakdown"]
    assert b == {"since": "2026-09-29T06:00:00+02:00", "basis": "window", "total": 22,
                 "projects": [{"name": "scratch", "total": 11}, {"name": "website", "total": 11}],
                 "models": [{"name": "Opus 5", "total": 11}, {"name": "Sonnet 5", "total": 11}]}


def test_breakdown_falls_back_to_last_seven_days(tmp_path):
    p = breakdown_setup(tmp_path)
    b = run(p, NOW, BERLIN, fetch=ok_fetch, notifier=lambda n: True)["providers"]["claude"]["breakdown"]
    assert b["basis"] == "7d" and b["since"] == "2026-09-26T19:42:00+02:00"
    assert b["total"] == 33


def test_backfill_for_existing_state_counts_once(tmp_path):
    p = breakdown_setup(tmp_path)
    run(p, NOW, BERLIN, fetch=week_fetch, notifier=lambda n: True)
    state = json.loads(p.state_file.read_text())
    del state["claude"]["hourly"], state["claude"]["hourly_backfill"]   # state from before the update
    p.state_file.write_text(json.dumps(state))
    stats = run(p, NOW + timedelta(minutes=6), BERLIN, fetch=week_fetch, notifier=lambda n: True)
    c = stats["providers"]["claude"]
    assert c["breakdown"]["total"] == 22
    assert c["tokens"]["today"]["total"] == 11          # daily totals not counted twice
    assert json.loads(p.state_file.read_text())["claude"]["hourly_backfill"] is False


def test_fresh_state_without_hourly_is_not_counted_twice(tmp_path):
    p = breakdown_setup(tmp_path)
    p.state_file.parent.mkdir(parents=True, exist_ok=True)
    p.state_file.write_text('{"version": 1, "claude": {}, "codex": {}}')  # empty, without hourly
    b = run(p, NOW, BERLIN, fetch=week_fetch, notifier=lambda n: True)["providers"]["claude"]["breakdown"]
    assert b["total"] == 22


def test_state_keeps_legacy_labels_for_older_collectors(tmp_path):
    p = make_paths(tmp_path)
    run(p, NOW, BERLIN, fetch=ok_fetch)
    state = json.loads(p.state_file.read_text())
    assert all("label" in l for l in state["claude"]["limits"]["limits"])


def test_legacy_state_limits_are_published_with_model(tmp_path):
    p = make_paths(tmp_path)
    run(p, NOW, BERLIN, fetch=ok_fetch)
    state = json.loads(p.state_file.read_text())
    state["claude"]["limits"]["limits"].append({"id": "seven_day_opus", "label": "Woche Opus", "used_percent": 3.0,
                                                 "resets_at": None, "window_minutes": 10080})
    state["claude"]["oauth_last_attempt"] = NOW.timestamp()  # throttled: keeps the saved limits
    p.state_file.write_text(json.dumps(state))

    def no_fetch(*a, **k):
        raise AssertionError("must not fetch while throttled")
    stats = run(p, NOW, BERLIN, fetch=no_fetch)
    opus = [l for l in stats["providers"]["claude"]["limits"] if l["id"] == "seven_day_opus"]
    assert opus and opus[0]["model"] == "Opus" and "label" not in opus[0]
