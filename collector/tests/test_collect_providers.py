import json
from datetime import timedelta

from collect_helpers import BERLIN, NOW, claude_line, codex_api, codex_auth, codex_line, make_paths, ok_fetch

from limit_rings import collect
from limit_rings.collect import run
from limit_rings.sources import claude_limits, claude_logs, codex_limits, codex_logs


def test_rate_limit_pause_is_kept_between_runs_and_published(tmp_path):
    import io
    import urllib.error
    from dataclasses import replace

    p = make_paths(tmp_path)
    p = replace(p, codex_auth=codex_auth(p))

    def limited(*a, **k):
        raise urllib.error.HTTPError(
            "https://example.invalid", 429, "Too Many Requests", {"Retry-After": "1800"}, io.BytesIO(b"")
        )

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
    assert providers["claude"]["extra"] == {
        "kind": "extra_usage",
        "used": 2.5,
        "limit": None,
        "percent": None,
        "currency": "USD",
    }
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
        return [(lim["id"], lim["window_minutes"]) for lim in stats["providers"]["codex"]["limits"]]

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
    stats = run(
        p,
        later + timedelta(minutes=10),
        BERLIN,
        fetch=ok_fetch,
        codex_fetch=answer(five, week),
        notifier=lambda n: notices.append(n) or True,
    )
    assert windows(stats) == [("primary", 300), ("secondary", 10080)]
    state = json.loads(p.state_file.read_text())
    assert len(state["history"]["codex:primary"]["points"]) == 1
    assert [n.key for n in notices if n.key.startswith("codex:")] == ["codex:primary"]


def test_hidden_provider_is_neither_read_nor_queried(tmp_path, monkeypatch):
    from dataclasses import replace

    p = make_paths(tmp_path)
    p = replace(p, codex_auth=codex_auth(p))
    stats = run(p, NOW, BERLIN, fetch=ok_fetch, codex_fetch=codex_api)
    claude_before = stats["providers"]["claude"]["limits"]
    (p.claude_root / "proj").mkdir()
    (p.claude_root / "proj" / "s.jsonl").write_text(claude_line("m1", "2026-10-03T10:00:00Z") + "\n")

    calls = []

    def forbidden(*a, **k):
        calls.append(a)
        raise AssertionError("hidden provider must not be touched")

    for name in ("read_credentials", "credential_status", "fetch_oauth_usage"):
        monkeypatch.setattr(claude_limits, name, forbidden)
    monkeypatch.setattr(claude_logs, "read_events", forbidden)

    later = NOW + timedelta(minutes=10)
    stats = run(p, later, BERLIN, fetch=forbidden, codex_fetch=codex_api, providers={"codex"})
    claude = stats["providers"]["claude"]
    assert claude["limits"] == claude_before  # last known values stay, nothing new is fetched
    assert claude["tokens"]["today"]["total"] == 0  # the new transcript was not read
    assert claude["auth"] is None and claude["plan"] is None
    assert stats["providers"]["codex"]["limits_updated_at"] == later.isoformat(timespec="seconds")
    assert calls == []  # the forbidden function was never called (provider errors are swallowed)


def test_no_providers_means_no_requests_at_all(tmp_path):
    from dataclasses import replace

    p = make_paths(tmp_path)
    p = replace(p, codex_auth=codex_auth(p))

    calls = []

    def forbidden(*a, **k):
        calls.append(a)
        raise AssertionError("must not fetch")

    stats = run(p, NOW, BERLIN, fetch=forbidden, codex_fetch=forbidden, providers=set())
    assert stats["providers"]["claude"]["limits"] == [] and stats["providers"]["codex"]["limits"] == []
    assert calls == []  # the forbidden function was never called (provider errors are swallowed)


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
        raise urllib.error.HTTPError(
            "https://example.invalid", 429, "Too Many Requests", {"Retry-After": "1800"}, io.BytesIO(b"")
        )

    later = NOW + timedelta(minutes=6)
    stats = run(p, later, BERLIN, fetch=limited, codex_fetch=codex_api)
    assert stats["providers"]["claude"]["limits_next_request_at"] == (later + timedelta(minutes=30)).isoformat(
        timespec="seconds"
    )

    fresh = run(make_paths(tmp_path / "fresh"), NOW, BERLIN, fetch=ok_fetch, providers=set())
    assert fresh["providers"]["claude"]["limits_next_request_at"] is None


def test_hidden_provider_does_not_notify_and_keeps_its_notified_entries(tmp_path):
    p = make_paths(tmp_path)

    def hot85(token, timeout=10.0):
        return {"five_hour": {"utilization": 85.0, "resets_at": None}}

    run(p, NOW, BERLIN, fetch=hot85)  # notifications off in this instance: nothing recorded
    notices = []
    run(p, NOW + timedelta(minutes=1), BERLIN, fetch=hot85, notifier=notices.append, providers={"codex"})
    assert notices == []  # hidden: no warning from cached limits
    run(p, NOW + timedelta(minutes=2), BERLIN, fetch=hot85, notifier=notices.append)
    assert [n.key for n in notices] == ["claude:five_hour"]  # shown again: the due warning comes once
    notices.clear()
    run(p, NOW + timedelta(minutes=3), BERLIN, fetch=hot85, notifier=notices.append, providers={"codex"})
    run(p, NOW + timedelta(minutes=10), BERLIN, fetch=hot85, notifier=notices.append)
    assert notices == []  # entry survived the hidden pass: no repeat


def test_pass_returns_the_provider_entries_without_writing_stats(tmp_path):
    p = make_paths(tmp_path)
    out = collect._pass(
        p,
        NOW,
        BERLIN,
        fetch=ok_fetch,
        codex_fetch=codex_api,
        notifier=None,
        providers={"claude", "codex"},
        thresholds=(80, 95),
        reset_notice=False,
    )
    assert set(out) == {"claude", "codex"}
    assert out["claude"]["limits_source"] == "oauth"
    assert not p.stats_file.exists() and p.state_file.exists()


def test_a_codex_log_failure_is_isolated_and_keeps_the_codex_state(tmp_path, monkeypatch):
    p = make_paths(tmp_path)
    (p.codex_root / "rollout-a.jsonl").write_text(codex_line("2026-10-03T10:00:00Z", 500) + "\n")
    run(p, NOW, BERLIN, fetch=ok_fetch)
    before = json.loads(p.state_file.read_text())["codex"]

    def boom(*a, **k):
        raise RuntimeError("broken")

    monkeypatch.setattr(codex_logs, "read_events", boom)
    stats = run(p, NOW + timedelta(minutes=10), BERLIN, fetch=ok_fetch)
    x, c = stats["providers"]["codex"], stats["providers"]["claude"]
    assert x["errors"] == [{"code": "logs_failed"}]
    assert x["tokens"]["today"]["total"] == 500  # the counts read before stay
    assert c["errors"] == [] and c["limits_source"] == "oauth"
    assert json.loads(p.state_file.read_text())["codex"]["files"] == before["files"]


def test_an_unexpected_codex_limits_failure_still_records_the_attempt(tmp_path, monkeypatch):
    p = make_paths(tmp_path)

    def boom(*a, **k):
        raise RuntimeError("broken")

    monkeypatch.setattr(codex_limits, "resolve", boom)
    stats = run(p, NOW, BERLIN, fetch=ok_fetch)
    assert stats["providers"]["claude"]["limits_source"] == "oauth"  # the other provider is untouched
    assert json.loads(p.state_file.read_text())["codex"]["oauth_last_attempt"] == NOW.timestamp()
