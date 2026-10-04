"""Claude usage limits: OAuth usage endpoint with the status line cache as fallback.

The OAuth token is only read and sent exclusively to api.anthropic.com.
It is never refreshed, stored or logged.
"""

import json
import logging
import urllib.error
from pathlib import Path

from ..limits import normalize_oauth, normalize_statusline
from .http import get_json

log = logging.getLogger(__name__)

OAUTH_URL = "https://api.anthropic.com/api/oauth/usage"
OAUTH_MIN_INTERVAL = 300


def read_credentials(path: Path, now: float) -> tuple[str | None, str | None]:
    try:
        oauth = json.loads(path.read_text(encoding="utf-8"))["claudeAiOauth"]
    except (OSError, ValueError, KeyError, TypeError):
        return None, None
    if not isinstance(oauth, dict):
        return None, None
    plan = oauth.get("subscriptionType")
    token = oauth.get("accessToken")
    expires_ms = oauth.get("expiresAt")
    if not token or not isinstance(expires_ms, (int, float)) or expires_ms / 1000 <= now:
        return None, plan
    return token, plan


def credential_status(path: Path, now: float) -> tuple[str, float | None]:
    """Login state for display: ("ok" | "expired" | "missing", expiry in epoch seconds)."""
    try:
        oauth = json.loads(path.read_text(encoding="utf-8"))["claudeAiOauth"]
    except (OSError, ValueError, KeyError, TypeError):
        return "missing", None
    if not isinstance(oauth, dict) or not oauth.get("accessToken"):
        return "missing", None
    expires_ms = oauth.get("expiresAt")
    if not isinstance(expires_ms, (int, float)) or isinstance(expires_ms, bool) or expires_ms <= 0:
        return "missing", None
    expires_at = expires_ms / 1000
    return ("ok" if expires_at > now else "expired"), expires_at


def fetch_oauth_usage(token: str, timeout: float = 10.0, url: str = OAUTH_URL) -> dict:
    return get_json(url, {"Authorization": f"Bearer {token}", "anthropic-beta": "oauth-2025-04-20"}, timeout)


def _read_statusline(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        limits = normalize_statusline(data["rate_limits"])
        written_at = float(data["written_at"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    if not limits:
        return None
    return {"limits": limits, "source": "statusline", "updated_at": written_at}


def resolve(previous, last_attempt, now, credentials: Path, statusline_cache: Path,
            fetch=fetch_oauth_usage):
    token, plan = read_credentials(credentials, now)
    # If the clock runs backwards (last_attempt in the future), don't throttle forever.
    if last_attempt is None or now - last_attempt >= OAUTH_MIN_INTERVAL or now < last_attempt:
        last_attempt = now
        if token:
            resp = None
            try:
                resp = fetch(token, timeout=10.0)
                limits = normalize_oauth(resp)
                return {"limits": limits, "source": "oauth", "updated_at": now}, last_attempt, plan
            except urllib.error.HTTPError as e:
                log.warning("OAuth usage request failed: HTTP %s", e.code)
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
