import json
from datetime import timedelta

from collect_helpers import BERLIN, NOW, codex_api, codex_auth, codex_line, make_account, make_paths, ok_fetch

from limit_rings.collect import run
from limit_rings.sources import claude_limits, codex_limits


def test_entries_say_whether_the_login_is_used(tmp_path):
    p = make_paths(tmp_path)
    work, _ = make_account(tmp_path)
    stats = run(p, NOW, BERLIN, fetch=ok_fetch, accounts=[work])
    assert stats["providers"]["claude"]["login"] is True and stats["providers"]["codex"]["login"] is True
    assert stats["accounts"]["k7f3a2"]["login"] is True


def write_statusline(p, pct=33.0):
    p.statusline_cache.parent.mkdir(parents=True, exist_ok=True)
    p.statusline_cache.write_text(
        json.dumps(
            {
                "written_at": NOW.timestamp() + 60,
                "rate_limits": {
                    "five_hour": {"used_percentage": pct, "resets_at": None},
                    "seven_day": {"used_percentage": 10.0, "resets_at": None},
                },
            }
        )
    )


def test_claude_without_login_never_opens_the_login_and_uses_the_status_line(tmp_path, monkeypatch):
    p = make_paths(tmp_path)
    run(
        p,
        NOW,
        BERLIN,
        fetch=lambda t, timeout=10.0: {
            **ok_fetch(t),
            "extra_usage": {
                "is_enabled": True,
                "used_credits": 1234,
                "monthly_limit": 5000,
                "utilization": 24.68,
                "currency": "USD",
            },
        },
    )
    before = json.loads(p.state_file.read_text())["claude"]
    write_statusline(p)

    calls = []

    def forbidden(*a, **k):
        calls.append(a)
        raise AssertionError("the login must not be touched")

    for name in ("read_credentials", "credential_status", "fetch_oauth_usage"):
        monkeypatch.setattr(claude_limits, name, forbidden)
    later = NOW + timedelta(minutes=10)
    stats = run(p, later, BERLIN, fetch=forbidden, login={"codex"})
    c = stats["providers"]["claude"]
    assert c["login"] is False and c["auth"] is None and c["plan"] is None
    assert c["limits_source"] == "statusline" and c["extra"] is None
    assert [lim["used_percent"] for lim in c["limits"]] == [33.0, 10.0]
    after = json.loads(p.state_file.read_text())["claude"]
    assert after["oauth_last_attempt"] == before["oauth_last_attempt"]  # switching back on is unaffected
    assert after["oauth_pause"] == before["oauth_pause"]
    assert calls == []  # the forbidden function was never called (provider errors are swallowed)


def test_claude_without_login_and_without_status_line_has_no_limits(tmp_path):
    p = make_paths(tmp_path)
    run(p, NOW, BERLIN, fetch=ok_fetch)

    calls = []

    def forbidden(*a, **k):
        calls.append(a)
        raise AssertionError("must not fetch")

    stats = run(p, NOW + timedelta(minutes=10), BERLIN, fetch=forbidden, login=set())
    assert stats["providers"]["claude"]["limits"] == []
    assert stats["providers"]["claude"]["limits_source"] is None
    assert calls == []  # the forbidden function was never called (provider errors are swallowed)


def test_claude_account_without_login_reads_no_credentials(tmp_path, monkeypatch):
    p = make_paths(tmp_path)
    work, _ = make_account(tmp_path)

    calls = []

    def forbidden(*a, **k):
        calls.append(a)
        raise AssertionError("no Claude login may be touched, neither the main nor the account one")

    for name in ("read_credentials", "credential_status", "fetch_oauth_usage"):
        monkeypatch.setattr(claude_limits, name, forbidden)
    stats = run(p, NOW, BERLIN, fetch=forbidden, accounts=[work], login={"codex"})
    acc = stats["accounts"]["k7f3a2"]
    assert acc["login"] is False and acc["limits"] == [] and acc["auth"] is None
    assert calls == []  # the forbidden function was never called (provider errors are swallowed)


def test_codex_without_login_drops_endpoint_data_and_uses_new_session_logs(tmp_path, monkeypatch):
    from dataclasses import replace

    p = make_paths(tmp_path)
    p = replace(p, codex_auth=codex_auth(p))
    stats = run(p, NOW, BERLIN, fetch=ok_fetch, codex_fetch=codex_api)
    assert stats["providers"]["codex"]["limits_source"] == "oauth"

    calls = []

    def forbidden(*a, **k):
        calls.append(a)
        raise AssertionError("the Codex login must not be touched")

    monkeypatch.setattr(codex_limits, "read_auth", forbidden)
    later = NOW + timedelta(minutes=10)
    stats = run(p, later, BERLIN, fetch=ok_fetch, codex_fetch=forbidden, login={"claude"})
    x = stats["providers"]["codex"]
    assert x["login"] is False and x["limits"] == [] and x["extra"] is None  # nothing from the endpoint stays
    (p.codex_root / "rollout-b.jsonl").write_text(codex_line("2026-10-03T17:50:00Z", 500) + "\n")
    stats = run(p, later + timedelta(minutes=1), BERLIN, fetch=ok_fetch, codex_fetch=forbidden, login={"claude"})
    x = stats["providers"]["codex"]
    assert x["limits_source"] == "session_log" and [lim["used_percent"] for lim in x["limits"]] == [8.0]
    assert calls == []  # the forbidden function was never called (provider errors are swallowed)


def test_codex_account_without_login_reads_no_auth(tmp_path, monkeypatch):
    p = make_paths(tmp_path)
    cx, cx_dir = make_account(tmp_path, "codex", "c0d3x1", "Team")
    (cx_dir / "sessions" / "rollout-a.jsonl").write_text(codex_line("2026-10-03T17:00:00Z", 300) + "\n")

    calls = []

    def forbidden(*a, **k):
        calls.append(a)
        raise AssertionError("the Codex login must not be touched")

    monkeypatch.setattr(codex_limits, "read_auth", forbidden)
    stats = run(p, NOW, BERLIN, fetch=ok_fetch, codex_fetch=forbidden, accounts=[cx], login={"claude"})
    acc = stats["accounts"]["c0d3x1"]
    assert acc["login"] is False and acc["auth"] is None
    assert acc["limits_source"] == "session_log" and acc["tokens"]["today"]["total"] == 300
    assert calls == []  # the forbidden function was never called (provider errors are swallowed)


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


def test_changes_noticed_via_the_login_go_when_it_is_switched_off(tmp_path):
    p = make_paths(tmp_path)
    responses = iter([ok_fetch(None), {**ok_fetch(None), "seven_day_opus": {"utilization": 3.0, "resets_at": None}}])
    run(p, NOW, BERLIN, fetch=lambda t, timeout=10.0: next(responses))
    stats = run(p, NOW + timedelta(minutes=6), BERLIN, fetch=lambda t, timeout=10.0: next(responses))
    assert [c["kind"] for c in stats["providers"]["claude"]["changes"]] == ["new"]
    stats = run(p, NOW + timedelta(minutes=12), BERLIN, fetch=ok_fetch, login={"codex"})
    assert stats["providers"]["claude"]["changes"] == []


def test_withhold_login_data_hides_endpoint_data_of_providers_without_login():
    from limit_rings.entries import withhold_login_data

    oauth = {
        "limits": [{"id": "five_hour"}],
        "limits_source": "oauth",
        "limits_updated_at": "t",
        "extra": {"kind": "x"},
        "plan": "max",
        "auth": {"status": "ok"},
        "changes": [{"kind": "new"}],
        "login": True,
        "tokens": {"a": 1},
        "limits_next_request_at": "t",
        "limits_paused_until": "t",
    }
    local = {**oauth, "limits_source": "session_log", "plan": "plus"}
    stats = {
        "schema": 2,
        "providers": {"claude": dict(oauth), "codex": dict(local)},
        "accounts": {"k1": {**oauth, "provider": "claude"}, "c1": {**oauth, "provider": "codex"}},
    }
    out = withhold_login_data(stats, {"codex"})
    c = out["providers"]["claude"]
    assert (c["limits"], c["limits_source"], c["extra"], c["plan"], c["auth"], c["changes"], c["login"]) == (
        [],
        None,
        None,
        None,
        None,
        [],
        False,
    )
    assert c["limits_next_request_at"] is None and c["limits_paused_until"] is None
    assert c["tokens"] == {"a": 1}  # local data stays
    assert out["providers"]["codex"] == local  # login on: untouched
    assert out["accounts"]["k1"]["limits"] == [] and out["accounts"]["k1"]["auth"] is None
    assert out["accounts"]["c1"] == stats["accounts"]["c1"]
    nologin = withhold_login_data(stats, set())
    assert nologin["providers"]["codex"]["limits"] == [{"id": "five_hour"}]  # session-log limits stay
    assert nologin["providers"]["codex"]["plan"] == "plus" and nologin["providers"]["codex"]["auth"] is None
    assert withhold_login_data(None, set()) is None
    assert withhold_login_data({"schema": 2}, set()) == {"schema": 2}
    assert withhold_login_data({"schema": 2, "providers": [1], "accounts": "x"}, set()) == {
        "schema": 2,
        "providers": [1],
        "accounts": "x",
    }
    assert withhold_login_data({"providers": {"claude": 1}, "accounts": {"k": 2}}, set()) == {
        "providers": {"claude": 1},
        "accounts": {"k": 2},
    }


def test_hidden_provider_without_login_loses_its_endpoint_data(tmp_path):
    p = make_paths(tmp_path)

    def with_extra(token, timeout=10.0):
        return {**ok_fetch(token), "extra_usage": {"is_enabled": True, "monthly_limit": None, "used_credits": 250}}

    first = run(p, NOW, BERLIN, fetch=with_extra)
    assert first["providers"]["claude"]["extra"] is not None
    stats = run(p, NOW + timedelta(minutes=6), BERLIN, fetch=ok_fetch, providers={"codex"}, login={"codex"})
    c = stats["providers"]["claude"]
    assert (c["limits"], c["limits_source"], c["extra"], c["plan"], c["login"]) == ([], None, None, None, False)


def test_a_new_codex_plan_with_other_limits_is_no_change(tmp_path):
    from dataclasses import replace

    p = make_paths(tmp_path)
    p = replace(p, codex_auth=codex_auth(p))

    def api(plan, seconds):
        def fetch(token, account_id, timeout=10.0):
            resp = codex_api(token, account_id)
            resp["plan_type"] = plan
            resp["rate_limit"]["primary_window"]["limit_window_seconds"] = seconds
            return resp

        return fetch

    run(p, NOW, BERLIN, fetch=ok_fetch, codex_fetch=api("plus", 604800))
    stats = run(p, NOW + timedelta(minutes=6), BERLIN, fetch=ok_fetch, codex_fetch=api("team", 2592000))
    assert stats["providers"]["codex"]["plan"] == "team"
    assert stats["providers"]["codex"]["limits"][0]["window_minutes"] == 43200
    assert stats["providers"]["codex"]["changes"] == []
    stats = run(p, NOW + timedelta(minutes=12), BERLIN, fetch=ok_fetch, codex_fetch=api("team", 604800))
    assert [c["kind"] for c in stats["providers"]["codex"]["changes"]] == ["length"]
