import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from limit_rings import collect
from limit_rings.collect import Paths, run, run_safely

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


def hot(token, timeout=10.0):
    return {"five_hour": {"utilization": 85.0, "resets_at": None}}


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
    assert stats["schema"] == 2
    assert stats["generated_at"] == "2026-10-03T19:42:00+02:00"
    c, x = stats["providers"]["claude"], stats["providers"]["codex"]
    assert c["tokens"]["today"]["total"] == 11
    assert c["limits_source"] == "oauth" and c["plan"] == "pro" and c["errors"] == []
    assert "error" not in c
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

    import limit_rings.collect as collect_mod
    def boom(*a, **k):
        raise RuntimeError("broken")
    monkeypatch.setattr(collect_mod.claude_logs, "read_events", boom)

    stats = run(p, NOW, BERLIN, fetch=ok_fetch)
    c, x = stats["providers"]["claude"], stats["providers"]["codex"]
    assert c["errors"] == [{"code": "logs_failed"}]
    assert c["limits_source"] == "oauth"               # limits still work
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
    from limit_rings.collect import local_zone
    monkeypatch.setenv("TZ", "America/New_York")
    assert local_zone().key == "America/New_York"
    monkeypatch.setenv("TZ", "Does/Not_Exist")
    assert local_zone() is not None


def test_unexpected_limits_failure_still_records_attempt(tmp_path, monkeypatch):
    p = make_paths(tmp_path)
    import limit_rings.collect as collect_mod
    def boom(*a, **k):
        raise RuntimeError("broken")
    monkeypatch.setattr(collect_mod.claude_limits, "resolve", boom)

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
    assert x["limits_source"] == "session_log" and x["errors"] == []
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



def test_rate_limit_pause_is_kept_between_runs_and_published(tmp_path):
    import io
    import urllib.error
    from dataclasses import replace
    p = make_paths(tmp_path)
    p = replace(p, codex_auth=codex_auth(p))

    def limited(*a, **k):
        raise urllib.error.HTTPError("https://example.invalid", 429, "Too Many Requests",
                                     {"Retry-After": "1800"}, io.BytesIO(b""))
    stats = run(p, NOW, BERLIN, fetch=limited, codex_fetch=limited)
    until = (NOW + timedelta(seconds=1800)).isoformat(timespec="seconds")
    assert stats["providers"]["claude"]["limits_paused_until"] == until
    assert stats["providers"]["codex"]["limits_paused_until"] == until

    def no_fetch(*a, **k):
        raise AssertionError("must not fetch during the pause")
    stats = run(p, NOW + timedelta(minutes=10), BERLIN, fetch=no_fetch, codex_fetch=no_fetch)
    assert stats["providers"]["claude"]["limits_paused_until"] == until

    stats = run(p, NOW + timedelta(minutes=30), BERLIN, fetch=ok_fetch, codex_fetch=codex_api)
    assert stats["providers"]["claude"]["limits_paused_until"] is None
    assert stats["providers"]["codex"]["limits_paused_until"] is None
    assert stats["providers"]["codex"]["limits_source"] == "oauth"


def test_extra_usage_and_credits_are_published(tmp_path):
    from dataclasses import replace
    p = make_paths(tmp_path)
    p = replace(p, codex_auth=codex_auth(p))

    def claude_extra(token, timeout=10.0):
        return {**ok_fetch(token), "extra_usage": {"is_enabled": True, "monthly_limit": None, "used_credits": 250}}

    def codex_credits(token, account_id, timeout=10.0):
        return {**codex_api(token, account_id), "credits": {"has_credits": True, "unlimited": False, "balance": "7"}}
    providers = run(p, NOW, BERLIN, fetch=claude_extra, codex_fetch=codex_credits)["providers"]
    assert providers["claude"]["extra"] == {"kind": "extra_usage", "used": 2.5, "limit": None, "percent": None,
                                            "currency": "USD"}
    assert providers["codex"]["extra"] == {"kind": "credits", "balance": 7.0, "unlimited": False}

    providers = run(make_paths(tmp_path / "plain"), NOW, BERLIN, fetch=ok_fetch)["providers"]
    assert providers["claude"]["extra"] is None and providers["codex"]["extra"] is None


def test_codex_window_that_vanishes_and_returns_leaves_nothing_behind(tmp_path):
    from dataclasses import replace
    p = make_paths(tmp_path)
    p = replace(p, codex_auth=codex_auth(p))
    reset = int(NOW.timestamp())
    five = {"used_percent": 85, "limit_window_seconds": 18000, "reset_at": reset + 3600}
    week = {"used_percent": 20, "limit_window_seconds": 604800, "reset_at": reset + 5 * 86400}

    def answer(primary, secondary):
        def fetch(token, account_id, timeout=10.0):
            return {"plan_type": "plus", "rate_limit": {"primary_window": primary, "secondary_window": secondary}}
        return fetch

    def windows(stats):
        return [(l["id"], l["window_minutes"]) for l in stats["providers"]["codex"]["limits"]]

    stats = run(p, NOW, BERLIN, fetch=ok_fetch, codex_fetch=answer(five, week), notifier=lambda n: True)
    assert windows(stats) == [("primary", 300), ("secondary", 10080)]
    state = json.loads(p.state_file.read_text())
    assert state["notified"]["codex:primary"]["minutes"] == 300

    # 5-hour window gone, the weekly one moves into "primary"
    later = NOW + timedelta(minutes=10)
    stats = run(p, later, BERLIN, fetch=ok_fetch, codex_fetch=answer(week, None), notifier=lambda n: True)
    assert windows(stats) == [("primary", 10080)]
    state = json.loads(p.state_file.read_text())
    assert sorted(k for k in state["history"] if k.startswith("codex:")) == ["codex:primary"]
    assert state["history"]["codex:primary"]["minutes"] == 10080
    assert "codex:primary" not in state["notified"] and "codex:secondary" not in state["notified"]

    # and back again: the 5-hour window starts fresh and notifies again
    notices = []
    stats = run(p, later + timedelta(minutes=10), BERLIN, fetch=ok_fetch, codex_fetch=answer(five, week),
                notifier=lambda n: notices.append(n) or True)
    assert windows(stats) == [("primary", 300), ("secondary", 10080)]
    state = json.loads(p.state_file.read_text())
    assert len(state["history"]["codex:primary"]["points"]) == 1
    assert [n.key for n in notices if n.key.startswith("codex:")] == ["codex:primary"]


def test_hidden_provider_is_neither_read_nor_queried(tmp_path, monkeypatch):
    from dataclasses import replace
    import limit_rings.collect as collect_mod
    p = make_paths(tmp_path)
    p = replace(p, codex_auth=codex_auth(p))
    stats = run(p, NOW, BERLIN, fetch=ok_fetch, codex_fetch=codex_api)
    claude_before = stats["providers"]["claude"]["limits"]
    (p.claude_root / "proj").mkdir()
    (p.claude_root / "proj" / "s.jsonl").write_text(claude_line("m1", "2026-10-03T10:00:00Z") + "\n")

    def forbidden(*a, **k):
        raise AssertionError("hidden provider must not be touched")
    for name in ("read_credentials", "credential_status", "fetch_oauth_usage"):
        monkeypatch.setattr(collect_mod.claude_limits, name, forbidden)
    monkeypatch.setattr(collect_mod.claude_logs, "read_events", forbidden)

    later = NOW + timedelta(minutes=10)
    stats = run(p, later, BERLIN, fetch=forbidden, codex_fetch=codex_api, providers={"codex"})
    claude = stats["providers"]["claude"]
    assert claude["limits"] == claude_before          # last known values stay, nothing new is fetched
    assert claude["tokens"]["today"]["total"] == 0    # the new transcript was not read
    assert claude["auth"] is None and claude["plan"] is None
    assert stats["providers"]["codex"]["limits_updated_at"] == later.isoformat(timespec="seconds")


def test_no_providers_means_no_requests_at_all(tmp_path):
    from dataclasses import replace
    p = make_paths(tmp_path)
    p = replace(p, codex_auth=codex_auth(p))

    def forbidden(*a, **k):
        raise AssertionError("must not fetch")
    stats = run(p, NOW, BERLIN, fetch=forbidden, codex_fetch=forbidden, providers=set())
    assert stats["providers"]["claude"]["limits"] == [] and stats["providers"]["codex"]["limits"] == []


def test_notice_settings_reach_the_notifications(tmp_path):
    p = make_paths(tmp_path)
    notices = []

    def at(pct):
        def fetch(token, timeout=10.0):
            return {"five_hour": {"utilization": pct, "resets_at": None}}
        return fetch
    run(p, NOW, BERLIN, fetch=at(55.0), notifier=notices.append, thresholds=(50, 75))
    assert [(n.key, n.level) for n in notices] == [("claude:five_hour", 50)]


def test_next_limit_request_is_published(tmp_path):
    import io
    import urllib.error
    from dataclasses import replace
    p = make_paths(tmp_path)
    p = replace(p, codex_auth=codex_auth(p))
    stats = run(p, NOW, BERLIN, fetch=ok_fetch, codex_fetch=codex_api)
    in_5 = (NOW + timedelta(minutes=5)).isoformat(timespec="seconds")
    assert stats["providers"]["claude"]["limits_next_request_at"] == in_5
    assert stats["providers"]["codex"]["limits_next_request_at"] == in_5

    def limited(*a, **k):
        raise urllib.error.HTTPError("https://example.invalid", 429, "Too Many Requests",
                                     {"Retry-After": "1800"}, io.BytesIO(b""))
    later = NOW + timedelta(minutes=6)
    stats = run(p, later, BERLIN, fetch=limited, codex_fetch=codex_api)
    assert stats["providers"]["claude"]["limits_next_request_at"] == (later + timedelta(minutes=30)).isoformat(
        timespec="seconds")

    fresh = run(make_paths(tmp_path / "fresh"), NOW, BERLIN, fetch=ok_fetch, providers=set())
    assert fresh["providers"]["claude"]["limits_next_request_at"] is None


def test_hidden_provider_does_not_notify_and_keeps_its_notified_entries(tmp_path):
    p = make_paths(tmp_path)
    hot85 = lambda token, timeout=10.0: {"five_hour": {"utilization": 85.0, "resets_at": None}}
    run(p, NOW, BERLIN, fetch=hot85)  # notifications off in this instance: nothing recorded
    notices = []
    run(p, NOW + timedelta(minutes=1), BERLIN, fetch=hot85, notifier=notices.append, providers={"codex"})
    assert notices == []                                   # hidden: no warning from cached limits
    run(p, NOW + timedelta(minutes=2), BERLIN, fetch=hot85, notifier=notices.append)
    assert [n.key for n in notices] == ["claude:five_hour"]  # shown again: the due warning comes once
    notices.clear()
    run(p, NOW + timedelta(minutes=3), BERLIN, fetch=hot85, notifier=notices.append, providers={"codex"})
    run(p, NOW + timedelta(minutes=10), BERLIN, fetch=hot85, notifier=notices.append)
    assert notices == []                                   # entry survived the hidden pass: no repeat


def test_pass_returns_the_provider_entries_without_writing_stats(tmp_path):
    p = make_paths(tmp_path)
    out = collect._pass(p, NOW, BERLIN, fetch=ok_fetch, codex_fetch=codex_api, notifier=None,
                        providers={"claude", "codex"}, thresholds=(80, 95), reset_notice=False)
    assert set(out) == {"claude", "codex"}
    assert out["claude"]["limits_source"] == "oauth"
    assert not p.stats_file.exists() and p.state_file.exists()


def make_account(tmp_path, provider="claude", account_id="k7f3a2", name="Work"):
    from limit_rings.accounts import parse_accounts
    d = tmp_path / f"home-{account_id}"
    if provider == "claude":
        (d / "projects" / "proj").mkdir(parents=True)
        (d / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {
            "accessToken": "other-secret", "expiresAt": int((NOW.timestamp() + 3600) * 1000),
            "subscriptionType": "max"}}))
    else:
        (d / "sessions").mkdir(parents=True)
        (d / "auth.json").write_text(json.dumps({"tokens": {"access_token": "x", "account_id": "acc"}}))
    (account,) = parse_accounts(json.dumps([{"id": account_id, "provider": provider, "dir": str(d),
                                             "name": name}]), tmp_path)
    return account, d


def test_without_accounts_the_output_only_gains_an_empty_section(tmp_path):
    p = make_paths(tmp_path)
    stats = run(p, NOW, BERLIN, fetch=ok_fetch)
    assert stats["accounts"] == {}
    assert not (p.state_file.parent / "accounts").exists()


def test_additional_accounts_are_collected_separately(tmp_path):
    p = make_paths(tmp_path)
    work, work_dir = make_account(tmp_path)
    (work_dir / "projects" / "proj" / "s.jsonl").write_text(claude_line("w1", "2026-10-03T10:00:00Z", out=99) + "\n")
    cx, _ = make_account(tmp_path, "codex", "c0d3x1", "Team")
    tokens = []

    def fetch(token, timeout=10.0):
        tokens.append(token)
        return ok_fetch(token) if token == "top-secret" else {"five_hour": {"utilization": 77.0, "resets_at": None}}
    notices = []
    stats = run(p, NOW, BERLIN, fetch=fetch, codex_fetch=codex_api, notifier=notices.append, accounts=[work, cx])
    assert sorted(tokens) == ["other-secret", "top-secret"]
    acc = stats["accounts"]["k7f3a2"]
    assert (acc["provider"], acc["name"], acc["dir"], acc["plan"]) == ("claude", "Work", str(work_dir), "max")
    assert [l["used_percent"] for l in acc["limits"]] == [77.0]
    assert acc["tokens"]["today"]["output"] == 99
    assert stats["providers"]["claude"]["tokens"]["today"]["total"] == 0   # main account untouched
    assert stats["accounts"]["c0d3x1"]["limits_source"] == "oauth"
    assert stats["accounts"]["c0d3x1"]["auth"]["status"] == "ok"
    assert (p.state_file.parent / "accounts" / f"{work.state_key}.json").exists()
    json.loads(p.stats_file.read_text())["accounts"]["k7f3a2"]


def test_changed_directory_starts_with_fresh_state(tmp_path):
    from limit_rings.accounts import parse_accounts
    p = make_paths(tmp_path)
    work, work_dir = make_account(tmp_path)
    (work_dir / "projects" / "proj" / "s.jsonl").write_text(claude_line("w1", "2026-10-03T10:00:00Z", out=11) + "\n")
    run(p, NOW, BERLIN, fetch=ok_fetch, accounts=[work])
    other, other_dir = make_account(tmp_path, account_id="zz9")
    (other_dir / "projects" / "proj" / "s.jsonl").write_text(claude_line("o1", "2026-10-03T11:00:00Z", out=99) + "\n")
    (moved,) = parse_accounts(json.dumps([{"id": "k7f3a2", "provider": "claude", "dir": str(other_dir),
                                           "name": "Work"}]), tmp_path)
    stats = run(p, NOW + timedelta(minutes=10), BERLIN, fetch=ok_fetch, accounts=[moved])
    assert stats["accounts"]["k7f3a2"]["tokens"]["today"]["output"] == 99   # not 110


def test_account_notices_name_the_account(tmp_path):
    p = make_paths(tmp_path)
    work, _ = make_account(tmp_path)
    notices = []
    run(p, NOW, BERLIN, fetch=lambda token, timeout=10.0: {"five_hour": {"utilization": 85.0, "resets_at": None}},
        notifier=notices.append, accounts=[work])
    assert sorted(n.summary for n in notices) == ["Claude (Work): 5-hour limit at 85 %",
                                                  "Claude: 5-hour limit at 85 %"]


def test_rate_limit_in_an_account_pauses_only_that_account(tmp_path):
    import io
    import urllib.error
    p = make_paths(tmp_path)
    work, _ = make_account(tmp_path)

    def fetch(token, timeout=10.0):
        if token == "other-secret":
            raise urllib.error.HTTPError("https://example.invalid", 429, "Too Many Requests",
                                         {"Retry-After": "1800"}, io.BytesIO(b""))
        return ok_fetch(token)
    stats = run(p, NOW, BERLIN, fetch=fetch, accounts=[work])
    assert stats["accounts"]["k7f3a2"]["limits_paused_until"] is not None
    assert stats["providers"]["claude"]["limits_paused_until"] is None


def test_broken_or_missing_accounts_do_not_disturb_the_others(tmp_path, monkeypatch):
    from limit_rings.accounts import parse_accounts
    p = make_paths(tmp_path)
    work, _ = make_account(tmp_path)
    missing, invalid = parse_accounts(json.dumps([
        {"id": "m1", "provider": "codex", "dir": str(tmp_path / "nowhere"), "name": "Gone"},
        {"id": "i1", "provider": "gemini", "dir": "/x", "name": "Bad"}]), tmp_path)
    real_pass = collect._pass

    def flaky(paths, *a, **k):
        if paths.state_file.name == f"{work.state_key}.json":
            raise RuntimeError("boom")
        return real_pass(paths, *a, **k)
    (p.state_file.parent / "accounts").mkdir(parents=True)
    (p.state_file.parent / "accounts" / f"{work.state_key}.json").write_text("{}")
    monkeypatch.setattr(collect, "_pass", flaky)
    stats = run(p, NOW, BERLIN, fetch=ok_fetch, accounts=[work, missing, invalid])
    assert stats["providers"]["claude"]["limits_source"] == "oauth"
    assert stats["accounts"]["k7f3a2"]["errors"] == [{"code": "logs_failed"}]
    assert (p.state_file.parent / "accounts" / f"{work.state_key}.json.corrupt").exists()
    gone = stats["accounts"]["m1"]
    assert gone["auth"]["status"] == "missing" and gone["limits"] == [] and gone["tokens"]["today"]["total"] == 0
    assert stats["accounts"]["i1"]["errors"] == [{"code": "account_invalid"}]
    assert stats["accounts"]["i1"]["provider"] is None


def test_failed_run_sets_the_account_states_aside_too(tmp_path, monkeypatch):
    p = make_paths(tmp_path)
    p.credentials.unlink()   # no logins: no network in run_safely's default fetchers
    work, work_dir = make_account(tmp_path)
    (work_dir / ".credentials.json").unlink()
    (work_dir / "projects" / "proj" / "s.jsonl").write_text(claude_line("w1", "2026-10-03T10:00:00Z") + "\n")
    real = collect.write_json_atomic

    def failing(path, obj):
        if path == p.stats_file:
            raise OSError("disk full")
        return real(path, obj)
    monkeypatch.setattr(collect, "write_json_atomic", failing)
    assert collect.run_safely(p, NOW, BERLIN, None, accounts=[work]) is None
    folder = p.state_file.parent / "accounts"
    assert (folder / f"{work.state_key}.json.corrupt").exists()
    assert not (folder / f"{work.state_key}.json").exists()


def test_hidden_account_states_are_pruned_after_30_days(tmp_path):
    import os
    p = make_paths(tmp_path)
    folder = p.state_file.parent / "accounts"
    folder.mkdir(parents=True)
    old = folder / "claude-0123456789ab.json"
    old.write_text("{}")
    os.utime(old, (NOW.timestamp() - 31 * 86400,) * 2)
    run(p, NOW, BERLIN, fetch=ok_fetch)
    assert not old.exists()


def test_a_new_window_shows_up_as_a_change(tmp_path):
    p = make_paths(tmp_path)
    responses = iter([ok_fetch(None), {**ok_fetch(None), "seven_day_opus": {"utilization": 3.0, "resets_at": None}}])

    def fetch(token, timeout=10.0):
        return next(responses)

    first = run(p, NOW, BERLIN, fetch=fetch, notifier=lambda n: True)
    assert first["providers"]["claude"]["changes"] == [] and first["providers"]["codex"]["changes"] == []
    later = NOW + timedelta(minutes=6)
    stats = run(p, later, BERLIN, fetch=fetch, notifier=lambda n: True)
    assert stats["providers"]["claude"]["changes"] == [
        {"kind": "new", "limit": {"id": "seven_day_opus", "window_minutes": 10080, "model": "Opus"},
         "at": "2026-10-03T19:48:00+02:00"}]


def test_entries_say_whether_the_login_is_used(tmp_path):
    p = make_paths(tmp_path)
    work, _ = make_account(tmp_path)
    stats = run(p, NOW, BERLIN, fetch=ok_fetch, accounts=[work])
    assert stats["providers"]["claude"]["login"] is True and stats["providers"]["codex"]["login"] is True
    assert stats["accounts"]["k7f3a2"]["login"] is True


def write_statusline(p, pct=33.0):
    p.statusline_cache.parent.mkdir(parents=True, exist_ok=True)
    p.statusline_cache.write_text(json.dumps({"written_at": NOW.timestamp() + 60, "rate_limits": {
        "five_hour": {"used_percentage": pct, "resets_at": None},
        "seven_day": {"used_percentage": 10.0, "resets_at": None}}}))


def test_claude_without_login_never_opens_the_login_and_uses_the_status_line(tmp_path, monkeypatch):
    import limit_rings.collect as collect_mod
    p = make_paths(tmp_path)
    run(p, NOW, BERLIN, fetch=lambda t, timeout=10.0: {**ok_fetch(t), "extra_usage": {
        "is_enabled": True, "used_credits": 1234, "monthly_limit": 5000, "utilization": 24.68, "currency": "USD"}})
    before = json.loads(p.state_file.read_text())["claude"]
    write_statusline(p)

    def forbidden(*a, **k):
        raise AssertionError("the login must not be touched")
    for name in ("read_credentials", "credential_status", "fetch_oauth_usage"):
        monkeypatch.setattr(collect_mod.claude_limits, name, forbidden)
    later = NOW + timedelta(minutes=10)
    stats = run(p, later, BERLIN, fetch=forbidden, login={"codex"})
    c = stats["providers"]["claude"]
    assert c["login"] is False and c["auth"] is None and c["plan"] is None
    assert c["limits_source"] == "statusline" and c["extra"] is None
    assert [l["used_percent"] for l in c["limits"]] == [33.0, 10.0]
    after = json.loads(p.state_file.read_text())["claude"]
    assert after["oauth_last_attempt"] == before["oauth_last_attempt"]   # switching back on is unaffected
    assert after["oauth_pause"] == before["oauth_pause"]


def test_claude_without_login_and_without_status_line_has_no_limits(tmp_path):
    p = make_paths(tmp_path)
    run(p, NOW, BERLIN, fetch=ok_fetch)

    def forbidden(*a, **k):
        raise AssertionError("must not fetch")
    stats = run(p, NOW + timedelta(minutes=10), BERLIN, fetch=forbidden, login=set())
    assert stats["providers"]["claude"]["limits"] == []
    assert stats["providers"]["claude"]["limits_source"] is None


def test_claude_account_without_login_reads_no_credentials(tmp_path, monkeypatch):
    import limit_rings.collect as collect_mod
    p = make_paths(tmp_path)
    work, _ = make_account(tmp_path)

    def forbidden(*a, **k):
        raise AssertionError("no Claude login may be touched, neither the main nor the account one")
    for name in ("read_credentials", "credential_status", "fetch_oauth_usage"):
        monkeypatch.setattr(collect_mod.claude_limits, name, forbidden)
    stats = run(p, NOW, BERLIN, fetch=forbidden, accounts=[work], login={"codex"})
    acc = stats["accounts"]["k7f3a2"]
    assert acc["login"] is False and acc["limits"] == [] and acc["auth"] is None


def test_codex_without_login_drops_endpoint_data_and_uses_new_session_logs(tmp_path, monkeypatch):
    from dataclasses import replace
    import limit_rings.collect as collect_mod
    p = make_paths(tmp_path)
    p = replace(p, codex_auth=codex_auth(p))
    stats = run(p, NOW, BERLIN, fetch=ok_fetch, codex_fetch=codex_api)
    assert stats["providers"]["codex"]["limits_source"] == "oauth"

    def forbidden(*a, **k):
        raise AssertionError("the Codex login must not be touched")
    monkeypatch.setattr(collect_mod.codex_limits, "read_auth", forbidden)
    later = NOW + timedelta(minutes=10)
    stats = run(p, later, BERLIN, fetch=ok_fetch, codex_fetch=forbidden, login={"claude"})
    x = stats["providers"]["codex"]
    assert x["login"] is False and x["limits"] == [] and x["extra"] is None   # nothing from the endpoint stays
    (p.codex_root / "rollout-b.jsonl").write_text(codex_line("2026-10-03T17:50:00Z", 500) + "\n")
    stats = run(p, later + timedelta(minutes=1), BERLIN, fetch=ok_fetch, codex_fetch=forbidden, login={"claude"})
    x = stats["providers"]["codex"]
    assert x["limits_source"] == "session_log" and [l["used_percent"] for l in x["limits"]] == [8.0]


def test_codex_account_without_login_reads_no_auth(tmp_path, monkeypatch):
    import limit_rings.collect as collect_mod
    p = make_paths(tmp_path)
    cx, cx_dir = make_account(tmp_path, "codex", "c0d3x1", "Team")
    (cx_dir / "sessions" / "rollout-a.jsonl").write_text(codex_line("2026-10-03T17:00:00Z", 300) + "\n")

    def forbidden(*a, **k):
        raise AssertionError("the Codex login must not be touched")
    monkeypatch.setattr(collect_mod.codex_limits, "read_auth", forbidden)
    stats = run(p, NOW, BERLIN, fetch=ok_fetch, codex_fetch=forbidden, accounts=[cx], login={"claude"})
    acc = stats["accounts"]["c0d3x1"]
    assert acc["login"] is False and acc["auth"] is None
    assert acc["limits_source"] == "session_log" and acc["tokens"]["today"]["total"] == 300


def test_no_next_request_is_published_for_a_provider_without_login(tmp_path):
    from dataclasses import replace
    p = make_paths(tmp_path)
    p = replace(p, codex_auth=codex_auth(p))
    cx, _ = make_account(tmp_path, "codex", "c0d3x1", "Team")
    stats = run(p, NOW, BERLIN, fetch=ok_fetch, codex_fetch=codex_api, accounts=[cx])
    assert stats["providers"]["claude"]["limits_next_request_at"] is not None
    assert stats["providers"]["codex"]["limits_next_request_at"] is not None
    later = NOW + timedelta(minutes=1)
    stats = run(p, later, BERLIN, fetch=ok_fetch, codex_fetch=codex_api, accounts=[cx], login=set())
    for x in (stats["providers"]["claude"], stats["providers"]["codex"], stats["accounts"]["c0d3x1"]):
        assert x["limits_next_request_at"] is None and x["limits_paused_until"] is None
