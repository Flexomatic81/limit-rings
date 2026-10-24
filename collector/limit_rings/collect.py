"""One collector run: read logs, fetch limits, write stats.json."""

import contextlib
import json
import logging
import os
from collections.abc import Callable, Collection, Sequence
from datetime import datetime, tzinfo
from pathlib import Path

from . import accounts as accounts_mod
from . import changes, entries, forecast, notify, process
from .fsutil import write_json_atomic
from .models import JsonDict
from .paths import Paths
from .process import LOGS_FAILED, Fetch
from .sources import claude_limits, codex_limits
from .state import load_state, prune_state, save_state

log = logging.getLogger("limit_rings")

Notifier = Callable[[notify.Notice], None]

SCHEMA = 2


def _notify(
    state: JsonDict,
    providers: dict[str, list[JsonDict]],
    now_ts: float,
    notifier: Notifier | None,
    thresholds: tuple[int, int],
    reset_notice: bool,
    labels: dict[str, str] | None = None,
) -> None:
    if notifier is None:  # notifications off: leave them due, another widget instance may show them
        return
    for notice in notify.update_notices(providers, state["notified"], now_ts, thresholds, reset_notice, labels):
        try:
            notifier(notice)
        except Exception as e:  # a notification must never abort the run
            log.warning("notification failed: %s", type(e).__name__)


def _update_history(state: JsonDict) -> None:
    providers = {}
    for name, key in (("Claude", "claude"), ("Codex", "codex")):
        rec = state[key]["limits"]
        providers[name] = (rec["limits"], rec["updated_at"]) if rec else ([], None)
    forecast.update_history(state["history"], providers)


def _update_changes(state: JsonDict, providers: Collection[str], now_ts: float) -> None:
    """Note changes to the limit structure of each shown provider (a hidden one is not compared)."""
    for key in ("claude", "codex"):
        if key in providers:
            section = state[key]
            section["structure"] = changes.update(
                section["structure"], section["limits"], entries.limits_source(key, section["limits"]), now_ts
            )


def _fingerprint(state: JsonDict) -> str:
    return json.dumps(state, sort_keys=True, separators=(",", ":"))


PROVIDERS = frozenset({"claude", "codex"})


def _pass(
    paths: Paths,
    now: datetime,
    tz: tzinfo,
    fetch: Fetch,
    codex_fetch: Fetch,
    notifier: Notifier | None,
    providers: Collection[str],
    thresholds: tuple[int, int],
    reset_notice: bool,
    labels: dict[str, str] | None = None,
    login: Collection[str] = PROVIDERS,
) -> JsonDict:
    """Collect one account from its paths and state file; return its provider entries for stats.json.

    A provider missing from providers (hidden in the widget) is neither read nor queried: no logs,
    no login, no request, no notification – its card keeps the last known values.
    A provider missing from login gets its limits only from local copies (see process_claude / process_codex in
    process.py).
    Saves the state, not stats.json."""
    state = load_state(paths.state_file)
    before = _fingerprint(state)
    today = now.astimezone(tz).date()

    claude_errors: list[JsonDict] = []
    claude_plan: str | None = None
    if "claude" in providers:
        claude_errors, claude_plan = process.process_claude(state, paths, now.timestamp(), tz, fetch, "claude" in login)
    codex_errors = (
        process.process_codex(state, paths, now.timestamp(), tz, codex_fetch, "codex" in login)
        if "codex" in providers
        else []
    )
    _update_history(state)
    _update_changes(state, providers, now.timestamp())
    with_forecasts = {
        key: entries.with_forecasts(
            (state[key]["limits"] or {}).get("limits", []), name, state["history"], now.timestamp()
        )
        for name, key in (("Claude", "claude"), ("Codex", "codex"))
    }
    shown = {name: with_forecasts[key] for name, key in (("Claude", "claude"), ("Codex", "codex")) if key in providers}
    _notify(state, shown, now.timestamp(), notifier, thresholds, reset_notice, labels)

    prune_state(state, today)
    if _fingerprint(state) != before:  # state.json is large: only write it if something changed
        save_state(paths.state_file, state)

    claude = state["claude"]
    codex = state["codex"]
    provider_entries = {
        "claude": {
            **entries.provider_entry(
                claude,
                today,
                tz,
                now.timestamp(),
                entries.limits_source("claude", claude["limits"]),
                claude_plan,
                claude_errors,
                claude_limits.OAUTH_MIN_INTERVAL,
            ),
            "auth": (
                entries.auth_entry(paths.credentials, now.timestamp(), tz)
                if "claude" in providers and "claude" in login
                else None
            ),
            "breakdown": entries.breakdown_entry(claude, now.timestamp(), tz),
        },
        "codex": {
            **entries.provider_entry(
                codex,
                today,
                tz,
                now.timestamp(),
                entries.limits_source("codex", codex["limits"]),
                codex["limits"]["plan"] if codex["limits"] else None,
                codex_errors,
                codex_limits.MIN_INTERVAL,
            ),
            "breakdown": entries.breakdown_entry(codex, now.timestamp(), tz),
        },
    }
    for key in ("claude", "codex"):
        provider_entries[key]["login"] = key in login
        if key not in login:  # no request will follow, so none is announced (the throttle state stays as it is)
            provider_entries[key]["limits_next_request_at"] = provider_entries[key]["limits_paused_until"] = None
    for key, limits in with_forecasts.items():
        provider_entries[key]["limits"] = limits
        provider_entries[key]["changes"] = changes.recent(
            state[key]["structure"], now.timestamp(), tz, local_only=key not in login
        )
        if key not in login:  # also a hidden provider, whose state may still hold endpoint data
            entries.strip_login_data(key, provider_entries[key])
    return provider_entries


def _accounts(
    accounts: Sequence[accounts_mod.Account],
    cache: Path,
    now: datetime,
    tz: tzinfo,
    fetch: Fetch,
    codex_fetch: Fetch,
    notifier: Notifier | None,
    thresholds: tuple[int, int],
    reset_notice: bool,
    login: Collection[str],
) -> JsonDict:
    out = {}
    today = now.astimezone(tz).date()
    for account in accounts:
        head = {"provider": account.provider, "name": account.name, "dir": account.dir_text}
        if account.error:
            out[account.id] = {
                **entries.empty_entry(
                    account.provider, today, [{"code": account.error}], login=account.provider in login
                ),
                **head,
            }
            continue
        provider = account.provider
        assert provider is not None  # parse_accounts sets an error on every account without a provider
        paths = accounts_mod.account_paths(account, cache)
        try:
            entry = _pass(
                paths,
                now,
                tz,
                fetch,
                codex_fetch,
                notifier,
                {provider},
                thresholds,
                reset_notice,
                labels={accounts_mod.PROVIDER_NAMES[provider]: account.label},
                login=login,
            )
            entry = entry[provider]
        except Exception as e:
            log.error("account %s: run aborted: %s", account.id, type(e).__name__)
            with contextlib.suppress(OSError):
                os.replace(paths.state_file, paths.state_file.with_name(paths.state_file.name + ".corrupt"))
            entry = entries.empty_entry(account.provider, today, [dict(LOGS_FAILED)], login=account.provider in login)
        if account.provider == "codex":
            if account.provider in login:
                token, _ = codex_limits.read_auth(paths.codex_auth)
                entry["auth"] = {"status": "ok" if token else "missing", "expires_at": None}
            else:
                entry["auth"] = None
        out[account.id] = {**entry, **head}
    accounts_mod.prune_account_states(cache, {a.state_key for a in accounts if not a.error}, now.timestamp())
    return out


def run(
    paths: Paths,
    now: datetime,
    tz: tzinfo,
    fetch: Fetch = claude_limits.fetch_oauth_usage,
    notifier: Notifier | None = None,
    codex_fetch: Fetch = codex_limits.fetch_usage,
    providers: Collection[str] = PROVIDERS,
    thresholds: tuple[int, int] = notify.THRESHOLDS,
    reset_notice: bool = False,
    accounts: Sequence[accounts_mod.Account] = (),
    login: Collection[str] = PROVIDERS,
) -> JsonDict:
    """One pass over the main account and each additional account (see _pass); writes stats.json.
    login: providers whose login may be used (see _pass)."""
    stats = {
        "schema": SCHEMA,
        "generated_at": now.astimezone(tz).isoformat(timespec="seconds"),
        "providers": _pass(
            paths, now, tz, fetch, codex_fetch, notifier, providers, thresholds, reset_notice, login=login
        ),
        "accounts": _accounts(
            accounts, paths.state_file.parent, now, tz, fetch, codex_fetch, notifier, thresholds, reset_notice, login
        ),
    }
    write_json_atomic(paths.stats_file, stats)
    return stats


def run_safely(
    paths: Paths,
    now: datetime,
    tz: tzinfo,
    notifier: Notifier | None,
    providers: Collection[str] = PROVIDERS,
    thresholds: tuple[int, int] = notify.THRESHOLDS,
    reset_notice: bool = False,
    accounts: Sequence[accounts_mod.Account] = (),
    login: Collection[str] = PROVIDERS,
) -> JsonDict | None:
    """One run that never raises: after an unexpected error, state.json and the additional accounts' state
    files are moved aside so the next run starts fresh (their due notices were not delivered)."""
    try:
        return run(
            paths,
            now,
            tz,
            notifier=notifier,
            providers=providers,
            thresholds=thresholds,
            reset_notice=reset_notice,
            accounts=accounts,
            login=login,
        )
    except Exception as e:
        log.error("run aborted: %s", type(e).__name__)
        cache = paths.state_file.parent
        files = [paths.state_file] + [accounts_mod.account_paths(a, cache).state_file for a in accounts if not a.error]
        for f in files:
            with contextlib.suppress(OSError):
                os.replace(f, f.with_name(f.name + ".corrupt"))
        return None
