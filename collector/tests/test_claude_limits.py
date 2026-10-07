import http.client
import io
import json
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from limit_rings.limits import normalize_oauth, normalize_statusline
from limit_rings.sources.claude_limits import credential_status, fetch_oauth_usage, read_credentials, resolve

FIXTURES = Path(__file__).parent / "fixtures"
NOW = 1_791_300_000.0


def creds(tmp_path, expires_ms=(NOW + 3600) * 1000):
    p = tmp_path / ".credentials.json"
    p.write_text(json.dumps({"claudeAiOauth": {"accessToken": "top-secret", "expiresAt": int(expires_ms),
                                               "subscriptionType": "pro"}}))
    return p


def statusline(tmp_path, written_at, pct=33.0):
    p = tmp_path / "claude-statusline-limits.json"
    p.write_text(json.dumps({"written_at": written_at, "rate_limits": {
        "five_hour": {"used_percentage": pct, "resets_at": int(NOW) + 600},
        "seven_day": {"used_percentage": 10.0, "resets_at": int(NOW) + 86400}}}))
    return p


def test_real_response_normalizes():
    """Real response from 2026-10-04 (billing details removed); utilization is in percent."""
    resp = json.loads((FIXTURES / "oauth_usage.json").read_text())
    assert normalize_oauth(resp) == [
        {"id": "five_hour", "label": "5 h", "used_percent": 1.0,
         "resets_at": 1791122400, "window_minutes": 300},
        {"id": "seven_day", "label": "Week", "used_percent": 34.0,
         "resets_at": 1791259200, "window_minutes": 10080},
        {"id": "weekly_scoped:fable", "label": "Week Fable", "used_percent": 9.0,
         "resets_at": 1791259200, "window_minutes": 10080, "model": "Fable"},
    ]


def test_scoped_limits_skip_broken_entries_and_duplicates():
    resp = {"five_hour": {"utilization": 5.0, "resets_at": None},
            "seven_day_opus": {"utilization": 20.0, "resets_at": None},
            "limits": [
                {"kind": "session", "percent": 5},
                {"kind": "weekly_scoped", "percent": 21, "scope": {"model": {"display_name": "Opus"}}},
                {"kind": "weekly_scoped", "percent": "lots", "scope": {"model": {"display_name": "Broken"}}},
                {"kind": "weekly_scoped", "percent": 3, "scope": None},
                "not an object",
                {"kind": "weekly_scoped", "percent": 7, "resets_at": None,
                 "scope": {"model": {"id": None, "display_name": "Sonnet"}}},
            ]}
    assert [(l["label"], l["used_percent"]) for l in normalize_oauth(resp)] == [
        ("5 h", 5.0), ("Week Opus", 20.0), ("Week Sonnet", 7.0)]


def test_scoped_limits_alone_are_not_enough():
    try:
        normalize_oauth({"limits": [{"kind": "weekly_scoped", "percent": 9,
                                     "scope": {"model": {"display_name": "Fable"}}}]})
    except ValueError:
        return
    raise AssertionError("without five_hour/seven_day the fallback should apply")


def test_normalize_oauth_null_reset_and_unknown_windows():
    resp = {"five_hour": {"utilization": 42.0, "resets_at": "2026-10-03T20:00:00+00:00"},
            "seven_day": {"utilization": 0.0, "resets_at": None},
            "seven_day_opus": None,
            "something_new": {"utilization": 5.0}}
    limits = normalize_oauth(resp)
    assert [l["id"] for l in limits] == ["five_hour", "seven_day"]
    assert limits[0]["resets_at"] == 1791057600
    assert limits[1]["resets_at"] is None


def test_normalize_oauth_rejects_unknown_shape():
    for bad in [{"foo": 1}, [], {"five_hour": "x"}, {"five_hour": {}},
                {"five_hour": {"utilization": None, "resets_at": None}}]:
        try:
            normalize_oauth(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_normalize_statusline():
    limits = normalize_statusline({"five_hour": {"used_percentage": 12.5, "resets_at": 100}})
    assert limits == [{"id": "five_hour", "label": "5 h", "used_percent": 12.5,
                       "resets_at": 100, "window_minutes": 300}]


def test_read_credentials_expired_token_is_none(tmp_path):
    assert read_credentials(creds(tmp_path), NOW) == ("top-secret", "pro")
    assert read_credentials(creds(tmp_path, expires_ms=(NOW - 1) * 1000), NOW) == (None, "pro")
    assert read_credentials(tmp_path / "missing.json", NOW) == (None, None)


def test_malformed_credentials_still_allow_fallback(tmp_path):
    p = tmp_path / ".credentials.json"
    for body in ['{"claudeAiOauth": null}', '{"claudeAiOauth": []}', "[]"]:
        p.write_text(body)
        assert read_credentials(p, NOW) == (None, None)
        rec, _, _ = resolve(None, None, NOW, p, statusline(tmp_path, NOW - 60))
        assert rec["source"] == "statusline"


def test_oauth_success(tmp_path):
    seen = {}
    def fetch(token, timeout=10.0):
        seen["token"] = token
        return {"five_hour": {"utilization": 42.0, "resets_at": None}}
    rec, attempt, plan = resolve(None, None, NOW, creds(tmp_path), tmp_path / "x", fetch=fetch)
    assert rec["source"] == "oauth" and rec["updated_at"] == NOW
    assert rec["limits"][0]["used_percent"] == 42.0
    assert attempt == NOW and plan == "pro" and seen["token"] == "top-secret"


def _raiser(exc):
    def fetch(token, timeout=10.0):
        raise exc
    return fetch


def test_http_401_falls_back_to_statusline_and_does_not_log_token(tmp_path, caplog):
    err = urllib.error.HTTPError("https://api.anthropic.com/api/oauth/usage", 401, "Unauthorized", {}, io.BytesIO(b""))
    rec, attempt, _ = resolve(None, None, NOW, creds(tmp_path), statusline(tmp_path, NOW - 60), fetch=_raiser(err))
    assert rec["source"] == "statusline" and rec["updated_at"] == NOW - 60
    assert attempt == NOW
    assert "top-secret" not in caplog.text
    assert "401" in caplog.text


def test_timeout_and_unexpected_shape_fall_back(tmp_path):
    for fetch in [_raiser(TimeoutError()), lambda token, timeout=10.0: {"foo": 1},
                  lambda token, timeout=10.0: {"five_hour": {}}]:
        rec, _, _ = resolve(None, None, NOW, creds(tmp_path), statusline(tmp_path, NOW - 60), fetch=fetch)
        assert rec["source"] == "statusline"


def test_throttle_keeps_fresh_oauth_record_without_fetching(tmp_path):
    prev = {"limits": [], "source": "oauth", "updated_at": NOW - 100}
    rec, attempt, _ = resolve(prev, NOW - 100, NOW, creds(tmp_path), statusline(tmp_path, NOW - 500),
                              fetch=_raiser(AssertionError("must not fetch")))
    assert rec is prev and attempt == NOW - 100


def test_newer_statusline_does_not_replace_healthy_oauth_during_throttle(tmp_path):
    opus = {"id": "seven_day_opus", "label": "Week Opus", "used_percent": 95.0,
            "resets_at": None, "window_minutes": 10080, "model": "Opus"}
    prev = {"limits": [opus], "source": "oauth", "updated_at": NOW - 100}
    rec, _, _ = resolve(prev, NOW - 100, NOW, creds(tmp_path), statusline(tmp_path, NOW - 10),
                        fetch=_raiser(AssertionError("throttled")))
    assert rec is prev


def test_fetch_refuses_redirects():
    hits = []

    class Target(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    target = HTTPServer(("127.0.0.1", 0), Target)

    class Redirect(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{target.server_port}/fremd")
            self.end_headers()

        def log_message(self, *args):
            pass

    source = HTTPServer(("127.0.0.1", 0), Redirect)
    for srv in (target, source):
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with pytest.raises(urllib.error.HTTPError):
            fetch_oauth_usage("top-secret", url=f"http://127.0.0.1:{source.server_port}/api/oauth/usage")
        assert hits == []
    finally:
        for srv in (target, source):
            srv.shutdown()


def test_newer_statusline_beats_older_previous(tmp_path):
    prev = {"limits": [], "source": "oauth", "updated_at": NOW - 3000}
    rec, _, _ = resolve(prev, NOW - 100, NOW, creds(tmp_path), statusline(tmp_path, NOW - 50),
                        fetch=_raiser(AssertionError("throttled")))
    assert rec["source"] == "statusline"


def test_no_sources_at_all(tmp_path):
    rec, _, plan = resolve(None, None, NOW, tmp_path / "missing", tmp_path / "missing2")
    assert rec is None and plan is None


def test_unexpected_exception_falls_back_throttles_and_does_not_log_token(tmp_path, caplog):
    """HTTPException subclasses (IncompleteRead) used to slip through all handlers."""
    rec, attempt, plan = resolve(None, None, NOW, creds(tmp_path), statusline(tmp_path, NOW - 60),
                                 fetch=_raiser(http.client.IncompleteRead(b"top-secret")))
    assert rec["source"] == "statusline" and rec["updated_at"] == NOW - 60
    assert attempt == NOW and plan == "pro"
    assert "top-secret" not in caplog.text
    assert "IncompleteRead" in caplog.text


def test_future_last_attempt_after_clock_jump_does_not_block_oauth(tmp_path):
    calls = []
    def fetch(token, timeout=10.0):
        calls.append(token)
        return {"five_hour": {"utilization": 42.0, "resets_at": None}}
    rec, attempt, _ = resolve(None, NOW + 3600, NOW, creds(tmp_path), tmp_path / "x", fetch=fetch)
    assert calls == ["top-secret"]
    assert rec["source"] == "oauth" and attempt == NOW


def test_credential_status(tmp_path):
    assert credential_status(creds(tmp_path), NOW) == ("ok", NOW + 3600)
    assert credential_status(creds(tmp_path, expires_ms=(NOW - 60) * 1000), NOW) == ("expired", NOW - 60)
    assert credential_status(tmp_path / "missing.json", NOW) == ("missing", None)
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"claudeAiOauth": {"accessToken": "", "expiresAt": 0}}))
    assert credential_status(empty, NOW) == ("missing", None)
    broken = tmp_path / "broken.json"
    broken.write_text('{"claudeAiOauth": null}')
    assert credential_status(broken, NOW) == ("missing", None)


def test_reset_times_are_rounded_not_truncated():
    """The API returns 04:00:00.25 one time, 03:59:59.99 the next – both are 04:00:00."""
    early = normalize_oauth({"five_hour": {"utilization": 1.0, "resets_at": "2026-10-06T03:59:59.990000+00:00"}})
    late = normalize_oauth({"five_hour": {"utilization": 1.0, "resets_at": "2026-10-06T04:00:00.253439+00:00"}})
    assert early[0]["resets_at"] == late[0]["resets_at"] == 1791259200


def test_rate_limit_pauses_oauth_and_uses_the_status_line_meanwhile(tmp_path):
    from limit_rings.sources import backoff
    err = urllib.error.HTTPError("https://api.anthropic.com/api/oauth/usage", 429, "Too Many Requests",
                                 {"Retry-After": "3600"}, io.BytesIO(b""))
    pause = backoff.new()
    rec, attempt, _ = resolve(None, None, NOW, creds(tmp_path), statusline(tmp_path, NOW - 60),
                              fetch=_raiser(err), pause=pause)
    assert rec["source"] == "statusline" and attempt == NOW
    assert pause == {"until": NOW + 3600, "failures": 1}

    def forbidden(token, timeout=10.0):
        raise AssertionError("must not fetch during the pause")
    rec, attempt, _ = resolve(rec, NOW, NOW + 1200, creds(tmp_path), statusline(tmp_path, NOW + 1100),
                              fetch=forbidden, pause=pause)
    assert rec["source"] == "statusline" and rec["updated_at"] == NOW + 1100 and attempt == NOW

    ok = json.loads((FIXTURES / "oauth_usage.json").read_text())
    login = creds(tmp_path, expires_ms=(NOW + 7200) * 1000)
    rec, _, _ = resolve(rec, NOW, NOW + 3600, login, statusline(tmp_path, NOW + 1100),
                        fetch=lambda token, timeout=10.0: ok, pause=pause)
    assert rec["source"] == "oauth"
    assert pause == backoff.new()


def test_oauth_record_carries_extra_usage_only_when_enabled(tmp_path):
    base = json.loads((FIXTURES / "oauth_usage.json").read_text())
    rec, _, _ = resolve(None, None, NOW, creds(tmp_path), tmp_path / "x", fetch=lambda token, timeout=10.0: base)
    assert "extra" not in rec
    on = {**base, "extra_usage": {"is_enabled": True, "monthly_limit": 5000, "used_credits": 1234,
                                  "utilization": 24.68, "currency": "USD"}}
    rec, _, _ = resolve(None, None, NOW, creds(tmp_path), tmp_path / "x", fetch=lambda token, timeout=10.0: on)
    assert rec["extra"] == {"kind": "extra_usage", "used": 12.34, "limit": 50.0, "percent": 24.68, "currency": "USD"}
