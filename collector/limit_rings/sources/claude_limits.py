"""Claude usage limits: OAuth usage endpoint with the status line cache as fallback.

The OAuth token is only read and sent exclusively to api.anthropic.com.
It is never refreshed, stored or logged.
"""

import json
import logging
import urllib.error
from pathlib import Path

from ..limits import normalize_extra_usage, normalize_oauth, normalize_statusline
from . import backoff
from .http import get_json

log = logging.getLogger(__name__)

OAUTH_URL = "https://api.anthropic.com/api/oauth/usage"
OAUTH_MIN_INTERVAL = 300


def _oauth(source) -> dict | None:
    """source: the credentials file, or the login already read from the keychain (dict or None)."""
    if isinstance(source, Path):
        try:
            source = json.loads(source.read_text(encoding="utf-8"))["claudeAiOauth"]
        except (OSError, ValueError, KeyError, TypeError):
            return None
    return source if isinstance(source, dict) else None


def read_credentials(source, now: float) -> tuple[str | None, str | None]:
    oauth = _oauth(source)
    if oauth is None:
        return None, None
    plan = oauth.get("subscriptionType")
    token = oauth.get("accessToken")
    expires_ms = oauth.get("expiresAt")
    if not token or not isinstance(expires_ms, (int, float)) or expires_ms / 1000 <= now:
        return None, plan
    return token, plan


def credential_status(source, now: float) -> tuple[str, float | None]:
    """Login state for display: ("ok" | "expired" | "missing", expiry in epoch seconds)."""
    return expiry_status(_expires_at(_oauth(source)), now)


def _expires_at(oauth: dict | None) -> float | None:
    """Expiry of a login with a token, None without one."""
    if oauth is None or not oauth.get("accessToken"):
        return None
    expires_ms = oauth.get("expiresAt")
    if not isinstance(expires_ms, (int, float)) or isinstance(expires_ms, bool) or expires_ms <= 0:
        return None
    return expires_ms / 1000


def expiry_status(expires_at: float | None, now: float) -> tuple[str, float | None]:
    if expires_at is None:
        return "missing", None
    return ("ok" if expires_at > now else "expired"), expires_at


def login_summary(source) -> dict:
    """What may be kept of a login between passes: plan and expiry, never the token."""
    oauth = _oauth(source)
    plan = oauth.get("subscriptionType") if oauth else None
    return {"plan": plan if isinstance(plan, str) else None, "expires_at": _expires_at(oauth)}


def is_due(last_attempt: float | None, now: float, pause: dict) -> bool:
    """Whether resolve() would ask the endpoint now."""
    # If the clock runs backwards (last_attempt in the future), don't throttle forever.
    due = last_attempt is None or now - last_attempt >= OAUTH_MIN_INTERVAL or now < last_attempt
    return due and backoff.blocked_until(pause, now) is None


def fetch_oauth_usage(token: str, timeout: float = 10.0, url: str = OAUTH_URL) -> dict:
    return get_json(url, {"Authorization": f"Bearer {token}", "anthropic-beta": "oauth-2025-04-20"}, timeout)


def _read_statusline(path: Path | None) -> dict | None:
    if path is None:  # additional accounts have no status line copy
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        limits = normalize_statusline(data["rate_limits"])
        written_at = float(data["written_at"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    if not limits:
        return None
    return {"limits": limits, "source": "statusline", "updated_at": written_at}


def resolve(previous, last_attempt, now, credentials, statusline_cache: Path | None,
            fetch=fetch_oauth_usage, pause: dict | None = None):
    """credentials: see _oauth. pause: back-off state (backoff.new()), updated in place after 429/503 and after
    a success."""
    pause = backoff.new() if pause is None else pause
    token, plan = read_credentials(credentials, now)
    if is_due(last_attempt, now, pause):
        last_attempt = now
        if token:
            resp = None
            try:
                resp = fetch(token, timeout=10.0)
                limits = normalize_oauth(resp)
                backoff.record_success(pause)
                rec = {"limits": limits, "source": "oauth", "updated_at": now}
                extra = normalize_extra_usage(resp)
                if extra:
                    rec["extra"] = extra
                return rec, last_attempt, plan
            except urllib.error.HTTPError as e:
                log.warning("OAuth usage request failed: HTTP %s", e.code)
                if backoff.is_rate_limit(e.code):
                    backoff.record_rate_limit(pause, now, e.headers.get("Retry-After") if e.headers else None)
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                log.warning("OAuth usage request failed: %s", type(e).__name__)
            except ValueError:
                fields = sorted(resp) if isinstance(resp, dict) else type(resp).__name__
                log.warning("OAuth usage response has unexpected shape, fields: %s", fields)
            except Exception as e:
                # e.g. http.client.IncompleteRead: type name only, messages may contain the token.
                log.warning("OAuth usage request failed: %s", type(e).__name__)
    elif previous and previous.get("source") == "oauth" and previous["updated_at"] >= last_attempt:
        # Throttled and the last OAuth attempt succeeded: keep the healthy data.
        return previous, last_attempt, plan

    candidates = [c for c in (previous, _read_statusline(statusline_cache)) if c]
    best = max(candidates, key=lambda c: c["updated_at"], default=None)
    return best, last_attempt, plan


def resolve_local(previous, statusline_cache: Path | None):
    """Without login: the newer of a stored local record and the status line copy.

    A record from the usage endpoint is dropped, so nothing fetched with the login stays on show.
    """
    candidates = [c for c in (previous, _read_statusline(statusline_cache)) if c and c.get("source") != "oauth"]
    return max(candidates, key=lambda c: c["updated_at"], default=None)
