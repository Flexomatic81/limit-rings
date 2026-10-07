import io
import json
import urllib.error
from pathlib import Path

from limit_rings.limits import normalize_codex_usage
from limit_rings.sources.codex_limits import read_auth, resolve

FIXTURES = Path(__file__).parent / "fixtures"
NOW = 1_791_112_476.0


def auth(tmp_path, token="top-secret", account="account-1"):
    p = tmp_path / "auth.json"
    p.write_text(json.dumps({"auth_mode": "chatgpt", "OPENAI_API_KEY": None,
                             "tokens": {"access_token": token, "account_id": account,
                                        "id_token": "x", "refresh_token": "y"},
                             "last_refresh": "2026-10-03T19:00:00Z"}))
    return p


def ok_fetch(token, account_id, timeout=10.0):
    return json.loads((FIXTURES / "codex_usage.json").read_text())


def _raiser(exc):
    def fetch(token, account_id, timeout=10.0):
        raise exc
    return fetch


def test_real_response_normalizes():
    """Real response from 2026-10-04 (plus plan), without email and IDs."""
    limits, plan = normalize_codex_usage(json.loads((FIXTURES / "codex_usage.json").read_text()))
    assert plan == "plus"
    assert limits == [{"id": "primary", "label": "Week", "used_percent": 7.0,
                       "resets_at": 1791628596, "window_minutes": 10080}]


def test_normalize_two_windows_and_rejects_unusable():
    limits, _ = normalize_codex_usage({"rate_limit": {
        "primary_window": {"used_percent": 30, "limit_window_seconds": 18000, "reset_at": 1},
        "secondary_window": {"used_percent": 5, "limit_window_seconds": 604800, "reset_at": 2}}})
    assert [l["label"] for l in limits] == ["5 h", "Week"]
    for bad in [{}, [], {"rate_limit": None}, {"rate_limit": {"primary_window": None, "secondary_window": None}},
                {"rate_limit": {"primary_window": {"used_percent": "x", "limit_window_seconds": 1}}}]:
        try:
            normalize_codex_usage(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_read_auth_variants(tmp_path):
    assert read_auth(auth(tmp_path)) == ("top-secret", "account-1")
    assert read_auth(tmp_path / "missing.json") == (None, None)
    assert read_auth(None) == (None, None)
    assert read_auth(auth(tmp_path, token="")) == (None, None)
    broken = tmp_path / "broken.json"
    broken.write_text('{"tokens": null}')
    assert read_auth(broken) == (None, None)


def test_success_gives_fresh_oauth_record(tmp_path):
    rec, attempt = resolve(None, None, NOW, auth(tmp_path), fetch=ok_fetch)
    assert rec == {"limits": [{"id": "primary", "label": "Week", "used_percent": 7.0,
                               "resets_at": 1791628596, "window_minutes": 10080}],
                   "plan": "plus", "updated_at": NOW, "source": "oauth"}
    assert attempt == NOW


def test_failure_keeps_previous_record_and_never_logs_token(tmp_path, caplog):
    prev = {"limits": [], "plan": "plus", "updated_at": NOW - 99999, "source": "session_log"}
    err = urllib.error.HTTPError("https://chatgpt.com/backend-api/wham/usage", 401, "Unauthorized", {},
                                 io.BytesIO(b""))
    for fetch in [_raiser(err), _raiser(TimeoutError()), _raiser(RuntimeError("top-secret")),
                  lambda token, account_id, timeout=10.0: {"foo": 1}]:
        rec, attempt = resolve(prev, None, NOW, auth(tmp_path), fetch=fetch)
        assert rec is prev and attempt == NOW
    assert "top-secret" not in caplog.text
    assert "401" in caplog.text


def test_throttle_and_missing_auth_skip_the_request(tmp_path):
    def forbidden(token, account_id, timeout=10.0):
        raise AssertionError("must not fetch")
    prev = {"limits": [], "plan": None, "updated_at": NOW - 100, "source": "oauth"}
    assert resolve(prev, NOW - 100, NOW, auth(tmp_path), fetch=forbidden) == (prev, NOW - 100)
    assert resolve(prev, None, NOW, tmp_path / "missing.json", fetch=forbidden) == (prev, NOW)
    # clock set back: last attempt lies in the future → still due
    rec, _ = resolve(prev, NOW + 3600, NOW, auth(tmp_path), fetch=ok_fetch)
    assert rec["source"] == "oauth" and rec["updated_at"] == NOW


def _rate_limited(retry_after=None, status=429):
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return _raiser(urllib.error.HTTPError("https://chatgpt.com/backend-api/wham/usage", status, "Too Many Requests",
                                          headers, io.BytesIO(b"")))


def test_rate_limit_pauses_requests_until_the_provider_allows_them(tmp_path):
    from limit_rings.sources import backoff
    prev = {"limits": [], "plan": "plus", "updated_at": NOW - 600, "source": "oauth"}
    pause = backoff.new()
    rec, attempt = resolve(prev, None, NOW, auth(tmp_path), fetch=_rate_limited("1800"), pause=pause)
    assert rec is prev and attempt == NOW
    assert pause == {"until": NOW + 1800, "failures": 1}

    def forbidden(token, account_id, timeout=10.0):
        raise AssertionError("must not fetch during the pause")
    later = NOW + 1000  # past the regular interval, still inside the pause
    assert resolve(prev, NOW, later, auth(tmp_path), fetch=forbidden, pause=pause) == (prev, NOW)

    rec, _ = resolve(prev, NOW, NOW + 1800, auth(tmp_path), fetch=ok_fetch, pause=pause)
    assert rec["updated_at"] == NOW + 1800
    assert pause == backoff.new()


def test_503_pauses_too_but_other_errors_keep_the_regular_interval(tmp_path):
    from limit_rings.sources import backoff
    pause = backoff.new()
    resolve(None, None, NOW, auth(tmp_path), fetch=_rate_limited(status=503), pause=pause)
    assert pause == {"until": NOW + 600, "failures": 1}
    pause = backoff.new()
    resolve(None, None, NOW, auth(tmp_path), fetch=_rate_limited(status=401), pause=pause)
    assert pause == backoff.new()


def test_record_carries_credits_only_with_a_balance(tmp_path):
    base = json.loads((FIXTURES / "codex_usage.json").read_text())
    rec, _ = resolve(None, None, NOW, auth(tmp_path), fetch=lambda token, account_id, timeout=10.0: base)
    assert "extra" not in rec
    rich = {**base, "credits": {**base["credits"], "has_credits": True, "balance": "120"}}
    rec, _ = resolve(None, None, NOW, auth(tmp_path), fetch=lambda token, account_id, timeout=10.0: rich)
    assert rec["extra"] == {"kind": "credits", "balance": 120.0, "unlimited": False}


def test_usage_with_only_a_secondary_or_swapped_windows():
    week = {"used_percent": 7, "limit_window_seconds": 604800, "reset_at": 2}
    five = {"used_percent": 30, "limit_window_seconds": 18000, "reset_at": 1}
    only_secondary, _ = normalize_codex_usage({"rate_limit": {"primary_window": None, "secondary_window": week}})
    assert [(l["id"], l["window_minutes"]) for l in only_secondary] == [("secondary", 10080)]
    swapped, _ = normalize_codex_usage({"rate_limit": {"primary_window": week, "secondary_window": five}})
    assert [(l["id"], l["window_minutes"]) for l in swapped] == [("primary", 10080), ("secondary", 300)]
