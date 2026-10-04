"""Codex-Nutzungslimits direkt vom Codex-Dienst (ChatGPT-Anmeldung aus ~/.codex/auth.json).

Nötig, weil Codex über das Claude-Code-Plugin flüchtige Sitzungen nutzt und keine Sitzungslogs
schreibt. Der Token wird nur gelesen und ausschließlich an chatgpt.com gesendet; er wird nie
erneuert, gespeichert oder geloggt.
"""

import json
import logging
import urllib.error
from pathlib import Path

from ..limits import normalize_codex_usage
from .http import get_json

log = logging.getLogger(__name__)

USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
MIN_INTERVAL = 300


def read_auth(path: Path | None) -> tuple[str | None, str | None]:
    """(access_token, account_id) aus auth.json; (None, None), wenn nicht vorhanden oder unbrauchbar."""
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


def resolve(previous, last_attempt, now, auth_path: Path | None, fetch=fetch_usage):
    """→ (Limit-Record, letzter Versuch). Bei Drosselung oder Fehler bleibt previous unverändert."""
    due = last_attempt is None or now - last_attempt >= MIN_INTERVAL or now < last_attempt
    if not due:
        return previous, last_attempt
    token, account = read_auth(auth_path)
    if not token:
        return previous, now
    resp = None
    try:
        resp = fetch(token, account, timeout=10.0)
        limits, plan = normalize_codex_usage(resp)
        return {"limits": limits, "plan": plan, "updated_at": now, "source": "oauth"}, now
    except urllib.error.HTTPError as e:
        log.warning("Codex-Usage-Abfrage fehlgeschlagen: HTTP %s", e.code)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        log.warning("Codex-Usage-Abfrage fehlgeschlagen: %s", type(e).__name__)
    except ValueError:
        fields = sorted(resp) if isinstance(resp, dict) else type(resp).__name__
        log.warning("Codex-Usage-Antwort hat unerwartete Form, Felder: %s", fields)
    except Exception as e:  # nie den Durchlauf abbrechen, nie den Text loggen (kann den Token enthalten)
        log.warning("Codex-Usage-Abfrage fehlgeschlagen: %s", type(e).__name__)
    return previous, now
