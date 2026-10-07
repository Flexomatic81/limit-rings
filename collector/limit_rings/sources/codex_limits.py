"""Codex usage limits directly from the Codex service (ChatGPT login from ~/.codex/auth.json).

Needed because Codex, when used through the Claude Code plugin, runs ephemeral sessions and writes
no session logs. The token is only read and sent exclusively to chatgpt.com; it is never
refreshed, stored or logged.
"""

import json
import logging
import urllib.error
from pathlib import Path

from ..limits import normalize_codex_credits, normalize_codex_usage
from . import backoff
from .http import get_json

log = logging.getLogger(__name__)

USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
MIN_INTERVAL = 300


def read_auth(path: Path | None) -> tuple[str | None, str | None]:
    """(access_token, account_id) from auth.json; (None, None) if missing or unusable."""
    if path is None:
        return None, None
    try:
        tokens = json.loads(path.read_text(encoding="utf-8"))["tokens"]
        token, account = tokens["access_token"], tokens["account_id"]
    except (OSError, ValueError, KeyError, TypeError):
        return None, None
    if not isinstance(token, str) or not token or not isinstance(account, str) or not account:
        return None, None
    return token, account


def fetch_usage(token: str, account_id: str, timeout: float = 10.0, url: str = USAGE_URL) -> dict:
    return get_json(url, {"Authorization": f"Bearer {token}", "ChatGPT-Account-Id": account_id}, timeout)


def resolve(previous, last_attempt, now, auth_path: Path | None, fetch=fetch_usage, pause: dict | None = None):
    """→ (limit record, last attempt). When throttled, paused or on error, previous stays unchanged.

    pause: back-off state (backoff.new()), updated in place after 429/503 and after a success.
    """
    pause = backoff.new() if pause is None else pause
    due = last_attempt is None or now - last_attempt >= MIN_INTERVAL or now < last_attempt
    if not due or backoff.blocked_until(pause, now) is not None:
        return previous, last_attempt
    token, account = read_auth(auth_path)
    if not token:
        return previous, now
    resp = None
    try:
        resp = fetch(token, account, timeout=10.0)
        limits, plan = normalize_codex_usage(resp)
        backoff.record_success(pause)
        rec = {"limits": limits, "plan": plan, "updated_at": now, "source": "oauth"}
        extra = normalize_codex_credits(resp)
        if extra:
            rec["extra"] = extra
        return rec, now
    except urllib.error.HTTPError as e:
        log.warning("Codex usage request failed: HTTP %s", e.code)
        if backoff.is_rate_limit(e.code):
            backoff.record_rate_limit(pause, now, e.headers.get("Retry-After") if e.headers else None)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        log.warning("Codex usage request failed: %s", type(e).__name__)
    except ValueError:
        fields = sorted(resp) if isinstance(resp, dict) else type(resp).__name__
        log.warning("Codex usage response has unexpected shape, fields: %s", fields)
    except Exception as e:  # never abort the run, never log the message (it may contain the token)
        log.warning("Codex usage request failed: %s", type(e).__name__)
    return previous, now
