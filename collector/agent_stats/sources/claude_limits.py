"""Claude-Nutzungslimits: OAuth-Usage-Endpunkt mit Statuszeilen-Cache als Rückfall.

Der OAuth-Token wird nur gelesen und ausschließlich an api.anthropic.com gesendet.
Er wird nie erneuert, gespeichert oder geloggt.
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
    """Zustand der Anmeldung für die Anzeige: ("ok" | "expired" | "missing", Ablauf in Epoch-Sekunden)."""
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
    # Läuft die Uhr rückwärts (last_attempt in der Zukunft), nicht auf Dauer drosseln.
    if last_attempt is None or now - last_attempt >= OAUTH_MIN_INTERVAL or now < last_attempt:
        last_attempt = now
        if token:
            resp = None
            try:
                resp = fetch(token, timeout=10.0)
                limits = normalize_oauth(resp)
                return {"limits": limits, "source": "oauth", "updated_at": now}, last_attempt, plan
            except urllib.error.HTTPError as e:
                log.warning("OAuth-Usage-Abfrage fehlgeschlagen: HTTP %s", e.code)
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                log.warning("OAuth-Usage-Abfrage fehlgeschlagen: %s", type(e).__name__)
            except ValueError:
                fields = sorted(resp) if isinstance(resp, dict) else type(resp).__name__
                log.warning("OAuth-Usage-Antwort hat unerwartete Form, Felder: %s", fields)
            except Exception as e:
                # z. B. http.client.IncompleteRead: nur der Typname, Meldungen können den Token enthalten.
                log.warning("OAuth-Usage-Abfrage fehlgeschlagen: %s", type(e).__name__)
    elif previous and previous.get("source") == "oauth" and previous["updated_at"] >= last_attempt:
        # Gedrosselt, letzter OAuth-Versuch war erfolgreich: gesunde Daten behalten.
        return previous, last_attempt, plan

    candidates = [c for c in (previous, _read_statusline(statusline_cache)) if c]
    best = max(candidates, key=lambda c: c["updated_at"], default=None)
    return best, last_attempt, plan
