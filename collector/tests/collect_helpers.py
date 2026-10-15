"""Builders shared by the collector run tests (test_collect*.py)."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from limit_rings.paths import Paths

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
    p.credentials.write_text(
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": "top-secret",
                    "expiresAt": int((NOW.timestamp() + 3600) * 1000),
                    "subscriptionType": "pro",
                }
            }
        )
    )
    return p


def claude_line(msg_id, ts, out=10):
    return json.dumps(
        {
            "timestamp": ts,
            "requestId": "r",
            "message": {
                "id": msg_id,
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": out,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
            },
        }
    )


def codex_line(ts, total):
    return json.dumps(
        {
            "timestamp": ts,
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {"total_tokens": total},
                    "last_token_usage": {"input_tokens": total, "cached_input_tokens": 0, "output_tokens": 0},
                },
                "rate_limits": {
                    "primary": {"used_percent": 8.0, "window_minutes": 10080, "resets_at": 1791280728},
                    "secondary": None,
                    "plan_type": "plus",
                },
            },
        }
    )


def ok_fetch(token, timeout=10.0):
    return {
        "five_hour": {"utilization": 42.0, "resets_at": None},
        "seven_day": {"utilization": 18.0, "resets_at": None},
    }


def codex_auth(p):
    path = p.claude_root.parent.parent / "codex" / "auth.json"
    path.write_text(json.dumps({"tokens": {"access_token": "top-secret-codex", "account_id": "account-1"}}))
    return path


def codex_api(token, account_id, timeout=10.0):
    return {
        "plan_type": "plus",
        "rate_limit": {
            "primary_window": {"used_percent": 7, "limit_window_seconds": 604800, "reset_at": 1791628596},
            "secondary_window": None,
        },
    }


def make_account(tmp_path, provider="claude", account_id="k7f3a2", name="Work"):
    from limit_rings.accounts import parse_accounts

    d = tmp_path / f"home-{account_id}"
    if provider == "claude":
        (d / "projects" / "proj").mkdir(parents=True)
        (d / ".credentials.json").write_text(
            json.dumps(
                {
                    "claudeAiOauth": {
                        "accessToken": "other-secret",
                        "expiresAt": int((NOW.timestamp() + 3600) * 1000),
                        "subscriptionType": "max",
                    }
                }
            )
        )
    else:
        (d / "sessions").mkdir(parents=True)
        (d / "auth.json").write_text(json.dumps({"tokens": {"access_token": "x", "account_id": "acc"}}))
    (account,) = parse_accounts(
        json.dumps([{"id": account_id, "provider": provider, "dir": str(d), "name": name}]), tmp_path
    )
    return account, d
