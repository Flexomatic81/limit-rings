# Limit Rings Plasmoid — Design

As of: 2026-10-07 · Status: implemented (0.3.0)

## Goal

A KDE Plasma 6 widget (plasmoid) that shows usage limits and token statistics of **Claude Code**
and **Codex** side by side — so you can see a limit coming before you run into it.

**Success criteria**

- The panel always shows the utilisation of the most heavily used limit per provider.
- The full view shows per provider: all limits with a countdown to the reset, tokens for
  today/week/month and a 30-day history.
- Today's token counts match an independent count over the raw logs.
- If one data source fails, the remaining displays stay correct; the age of every value is
  visible.

**Explicitly not in version 1** (possible later): cost estimate in $, active sessions. (The
breakdown by project/model, first listed here, has been added since — see `breakdown` below.)

## Environment

- KDE Plasma 6, Python ≥ 3.10 (python3 in PATH).
- Claude Code transcripts: `~/.claude/projects/**/*.jsonl` (incl. `*/subagents/*.jsonl`), often
  several hundred MB.
- Codex session logs: `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`.
- Claude Code status line: a custom status line script (expected by `install.sh` at
  `~/.claude/statusline-command.sh`) receives, among other things,
  `.rate_limits.five_hour.{used_percentage,resets_at}` via stdin.

## Architecture

```
~/.claude/projects/**/*.jsonl ─┐
~/.codex/sessions/**/*.jsonl  ─┼─► collector (Python, started by the widget every 60 s, under a file lock)
Anthropic OAuth usage API     ─┤        │  incremental: byte offset per file in state.json
Status line cache (fallback)  ─┘        ▼
                              ~/.cache/limit-rings/stats.json  (atomic: tmp + rename)
                                        │
                                        ▼
                         Plasmoid (QML) gets stats + notices on stdout → panel + desktop/popup + notifications
```

Decisions:

- **The widget runs the collector** (since 0.3; before: systemd user timer). The KDE Store installs
  only the widget package, so everything ships in it. A file lock (`~/.cache/limit-rings/.lock`)
  serialises the passes of several widget instances; a notice is shown by the instance whose pass finds it due.
- **Hidden providers are left alone:** the widget passes the shown providers as
  `LIMIT_RINGS_PROVIDERS=claude,codex` (unset: both). A pass skips the others completely – no logs, no
  login, no request – and publishes their last known values unchanged (`auth: null` for Claude).
- **Claude limits from two sources:** OAuth usage endpoint as the primary source (covers all
  usage, including claude.ai/desktop app), status line cache as the fallback.
- **Additional accounts are their own passes:** the widget passes the shown ones as
  `LIMIT_RINGS_ACCOUNTS` (JSON list of `{id, provider, dir, name}`). Each runs like the main account,
  from its own directory (`<dir>/.credentials.json` and `projects` for Claude, `auth.json` and `sessions`
  for Codex) and with its own state file `~/.cache/limit-rings/accounts/<provider>-<hash>.json`. The hash
  covers provider and canonical directory: a changed directory starts afresh, and two widgets that list
  the same directory share the state. Directories are compared canonically and must differ from the main
  account's and from other accounts of the same provider. Files of accounts that are not shown are removed after 30 days. No status
  line fallback.
- **Python standard library only** — no venv, no dependencies.

## Components

| Unit | Responsibility | Dependencies |
|---|---|---|
| `sources/claude_logs.py` | Reads new lines of the Claude transcripts; yields token events (timestamp, input, output, cache read, cache write). Books only increments per `(message.id, requestId)`. | `state` |
| `sources/codex_logs.py` | Reads `event_msg`/`token_count` events; yields token events from `last_token_usage` and the most recent `rate_limits` object with its timestamp. | `state` |
| `sources/codex_limits.py` | Queries the Codex usage endpoint (`chatgpt.com/backend-api/wham/usage`) with the ChatGPT login from `~/.codex/auth.json` (no redirects, at most every 5 min). Needed because Codex via the Claude Code plugin uses ephemeral sessions without a session log. On error, the last state (including from the session log) is kept. | HTTP (urllib), file system |
| `sources/claude_limits.py` | Queries the OAuth usage endpoint (no redirects); on error, the status line cache. Returns limits + source + timestamp. | HTTP (urllib), file system |
| `sources/backoff.py` | Pause after 429/503 from a usage endpoint: reads `Retry-After` (seconds or HTTP date), otherwise growing pauses; used by both limit sources, pause state in `state.json`. | – |
| `accounts.py` | Additional accounts: `parse_accounts` (validates `LIMIT_RINGS_ACCOUNTS`, canonical directories, at most 8), `account_paths` (state file and directories of one account), `prune_account_states` (removes state files of accounts not shown after 30 days). | `collect` |
| `changes.py` | Changes to the limit structure: compares each new limits record of a provider with the windows seen before (same source only) and notes new, returning, vanished, re-sized and early-reset windows (`structure` in `state.json`). | `limits` |
| `aggregate.py` | Pure functions: daily buckets → totals for today/week/month, gap-free 30-day series. | none |
| `state.py` | Offset and inode per file, seen message IDs, daily buckets per provider, time of the last OAuth query. | file system |
| `collect.py` | Orchestrates a run, writes `stats.json` atomically; `run_safely` quarantines a broken `state.json`. | all of the above |
| `widget.py` | Entry point for the widget: lock, log file, JSON envelope `{envelope, stats, notices}` on stdout. | `collect` |
| `run.py` | Checks Python ≥ 3.10, then calls `widget.main`. | `widget` |
| Plasmoid `io.github.flexomatic81.limitrings` | Presentation, notifications, update check; starts the collector. | collector output |
| Status line addition | One line in `statusline-command.sh`: writes `.rate_limits` to `~/.cache/limit-rings/claude-statusline-limits.json`. | — |

### Token events

**Claude:** Every line with `message.usage` is a candidate. An API response appears several times
(one line per content block), and the values are intermediate streaming states: `output_tokens`
grows from line to line (in about 15 % of responses; "first occurrence counts" underestimates the
output tokens by more than a hundredfold). Therefore, the amount already booked is remembered per
`(message.id, requestId)`; each further line books, field by field, only the increment
`max(0, new − remembered)`, on the date of the first line — even if the later line is only read
in a later collector run. Fields: `input_tokens`, `output_tokens`,
`cache_read_input_tokens`, `cache_creation_input_tokens`. Timestamp from `timestamp` (UTC).

**Codex:** `token_count` events with `info.last_token_usage` provide the consumption per call
(`input_tokens` minus `cached_input_tokens` → input, `cached_input_tokens` → cache read,
`output_tokens` → output, `cache_write_input_tokens` → cache write). Events without `info`
only carry limits and do not count as consumption. As a safeguard against double counting, the
highest `info.total_token_usage.total_tokens` is tracked per **session ID**
(`session_meta.payload.id`, falling back to the file path); an event whose total does not exceed
it is discarded. The session states outlive the disappearance of the file (400 days), so that
moved or copied session files are not counted twice.

### State and incrementality

- `~/.cache/limit-rings/state.json` holds `{offset, inode}` per file, the daily buckets per
  provider (local date → token totals), the booked usage states per Claude response for the
  last 35 days (older ones are discarded; files of that age are no longer written to)
  and the Codex session states.
- Reading only goes up to the last `\n`; an incomplete last line waits for the
  next run.
- File smaller than the offset or a different inode → read from the start; deduplication prevents
  double counting.
- Daily buckets older than 400 days are discarded (the monthly total and the 30-day series need less).
- `state.json` missing or unreadable → full re-read (once, takes seconds).

### Time handling

Local system time zone (Europe/Berlin). "Today" = local calendar date, "week" = from
Monday 00:00 local, "month" = from the 1st of the month 00:00 local. Timestamps are converted to
local time before being sorted into buckets; daylight saving time changes are therefore handled
correctly.

## Interface `stats.json`

The data contract between collector and widget (the widget receives it inside the envelope on the
collector's stdout; the file is the persisted copy). Mode `0600`, written atomically.

```json
{
  "schema": 2,
  "generated_at": "2026-10-03T19:42:00+02:00",
  "providers": {
    "claude": {
      "limits": [
        {"id": "five_hour", "used_percent": 42.0,
         "resets_at": 1791300000, "window_minutes": 300},
        {"id": "seven_day", "used_percent": 18.0,
         "resets_at": 1791800000, "window_minutes": 10080},
        {"id": "seven_day_opus", "used_percent": 4.0,
         "resets_at": 1791800000, "window_minutes": 10080, "model": "Opus"}
      ],
      "limits_source": "oauth",
      "limits_updated_at": "2026-10-03T19:41:30+02:00",
      "limits_paused_until": null,
      "limits_next_request_at": "2026-10-03T19:46:30+02:00",
      "extra": {"kind": "extra_usage", "used": 12.34, "limit": 50.0, "percent": 24.68, "currency": "USD"},
      "plan": "pro",
      "tokens": {
        "today": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "total": 0},
        "week":  {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "total": 0},
        "month": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "total": 0}
      },
      "daily": [{"date": "2026-09-04", "total": 123456}],
      "errors": [],
      "changes": [],
      "auth": {"status": "ok", "expires_at": "2026-10-04T19:29:15+02:00"}
    },
    "codex": {
      "limits": [
        {"id": "primary", "used_percent": 8.0,
         "resets_at": 1791280728, "window_minutes": 10080}
      ],
      "limits_source": "session_log",
      "limits_updated_at": "2026-09-29T21:30:00+02:00",
      "limits_paused_until": null,
      "limits_next_request_at": "2026-10-03T19:46:30+02:00",
      "extra": null,
      "plan": "plus",
      "tokens": {"today": {}, "week": {}, "month": {}},
      "daily": [],
      "errors": [{"code": "logs_unreadable", "count": 1}],
      "changes": [{"kind": "length", "limit": {"id": "primary", "window_minutes": 10080},
                   "previous_minutes": 300, "at": "2026-10-02T09:15:00+02:00"}]
    }
  },
  "accounts": {}
}
```

Rules:

- `limits` is a list of arbitrary length (depending on the plan, Codex only has `primary`, Claude
  two windows). Empty list = no limit data available.
- A limit has no display name; the plasmoid names it from `window_minutes` (300 → "5 h",
  10080 → "Week", otherwise "N h"/"N d") and `model` ("Week Opus"), in the system language.
- Model-specific weekly limits (`seven_day_opus`, `seven_day_sonnet` and the `limits` list of the
  OAuth response with `kind: "weekly_scoped"`, id `weekly_scoped:<model>`) carry `model`;
  malformed entries are dropped, a model that already has a weekly limit is not listed twice.
- `extra`: only from the usage endpoints, otherwise `null`. Claude: `extra_usage` (paid usage beyond
  the plan, only while switched on; the endpoint gives cents, `extra` currency units; `limit` and
  `percent` are `null` without a monthly limit). Codex: `{"kind": "credits", "balance": 120.0,
  "unlimited": false}`, only with a balance above 0 or unlimited credits. Unusable fields give `null`,
  never an error. The card shows a bar (with a monthly limit) or a line of text below the limits.
- `limits_source`: `"oauth"` | `"statusline"` | `"session_log"` | `null`.
  Codex: `"oauth"` (usage endpoint) or `"session_log"`; Codex token statistics only count
  terminal sessions, because the plugin does not store token counts.
- `total` = `input + output + cache_read + cache_write`.
- `daily` has exactly 30 entries, oldest first, missing days with `total: 0`.
- Limits with a 5-hour window (`window_minutes` 300) and a weekly window (10080) can carry a
  `forecast` field: `{"status": "full", "eta": <epoch>}` (full before the reset at the current pace)
  or `{"status": "enough"}`; if it is missing, there is no forecast (yet). It is based on the history in
  `state.json` (`history`):

  | | 5 h | Week |
  |---|---|---|
  | Pace from the increase over the last | 30 min | 24 h |
  | Forecast from a measurement span of | 10 min | 2 h |
  | Most recent point at most | 30 min old | 6 h old |
  | Points kept / minimum spacing | 60 min / – | 24 h / 10 min |

  A new window – different `resets_at` or a different window length under the same id (Codex can
  move its weekly window into `primary`) – restarts the history; entries keep the length as `minutes`.

  Card: a line below the bar only when the limit would run out before the reset ("Full in ~1 h 20 min
  at current pace (13:40)", with the weekday "(Sat 14:00)" once a day or more away); "Lasts until reset
  at current pace" and the reset time ("Resets at Wed 06:00") are in the bar's tooltip. Widget tooltip:
  short form.
- `changes` lists changes to the limit structure of the last 3 days, oldest first: `kind` is `"new"`
  (a window not seen before), `"back"` (a window that had vanished), `"gone"` (missing from fresh data
  for at least an hour; `at` is when it was first missing), `"length"` (same id, other window length;
  with `previous_minutes`) or `"early_reset"` (a new window while the old reset was still more than
  5 minutes away and the usage dropped). `limit` names the window like a limit (`id`,
  `window_minutes`, `model`). Only records of the same source are compared – a switch between the
  usage endpoint and the status line or session log starts afresh without changes; the first run notes
  nothing. `state.json` keeps the known windows and the changes of 30 days (at most 20) per provider
  under `structure`; a malformed `structure` is dropped alone. The card shows one line per change.
- `breakdown` exists only for Claude: token totals since the start of the Claude weekly window
  (weekly limit reset − 7 days; without a known weekly limit the last 7 days, `basis: "7d"`), for
  both `projects` and `models` the four largest entries plus a catch-all entry
  `{"name": null, "other": true, "total": …}` for the rest. Project = Git repository of the
  working directory (worktree → main repository), otherwise the directory name; model as a readable
  name ("Opus 5.5"). Counted hourly (`hourly` in `state.json`, 8 days). The values come only from the
  transcripts of **this** machine and are token shares, not the (undisclosed) limit consumption
  per model. Existing states without `hourly` backfill the hourly count once.
- `auth` exists only for Claude: state of the login token in `~/.claude/.credentials.json`
  (`"ok"` | `"expired"` | `"missing"`) and expiry time. The token is written and refreshed only by
  Claude Code in the terminal (valid for about 8 h). If the state is not `ok`, card and tooltip show
  "Login expired – run claude in a terminal" or "No login found – …".
- `login` (every provider and account entry): whether the live limits via login are on for it
  (`LIMIT_RINGS_LOGIN`, set by the widget from "Live limits via login"; unset = all providers). Off:
  the login file is never opened (`auth` is `null`, no Claude plan), the usage endpoint is not asked,
  a stored record from it is dropped; Claude limits come only from the status line copy, Codex limits
  only from the session logs. The card says so while there are no limits. A `stats.json` returned from
  cache is filtered the same way, change events remember their `source` (only local ones are shown),
  and `limits_next_request_at` / `limits_paused_until` are `null`.
- `errors` lists problems as codes (`logs_unreadable` with `count`, `logs_failed`,
  `limits_unavailable`); the other fields then carry the last good values.
- `stats.json` holds no display texts: the plasmoid builds limit names (from `window_minutes` and
  `model`), error messages and the catch-all entry in the system language. `state.json` keeps an
  English `label` per limit only so that an older collector still reads it after a downgrade.
- `accounts` maps the id of each additional account to the same fields as `providers.claude` /
  `providers.codex`, plus `provider` (`"claude"` | `"codex"`), `name` and `dir` (as typed in the
  settings); `{}` without accounts. A Codex account carries `auth: {"status": "ok" | "missing",
  "expires_at": null}`. Besides the codes above, `errors` can hold `account_invalid` (unusable entry,
  e.g. a missing or duplicate directory) and `logs_failed`.
- The widget ignores a `stats.json` with an unknown `schema` version and shows a notice.

## Presentation

### Panel (compact)

- For each enabled provider, a ring with the abbreviation "C" / "X": **outer** the highest weekly
  limit, **inner** (thinner) the 5-hour limit, each ring with its own threshold colour; without a
  5-hour window only the outer ring, without either kind of window the highest value. "Number"
  display: the highest value.
- Colour by threshold (default): below 70 % neutral, from 70 % warning, from 90 % critical —
  Plasma theme colours (`Kirigami.Theme.neutralTextColor` / `negativeTextColor`). On top of that a
  ring (and a bar in the popup) is at least "warning" while its forecast says full before the reset
  (`Format.limitSeverity`); critical stays with the threshold. "Normal" uses the accent colour
  unless its hue is within 30° of the warning or critical colour (an orange accent next to the orange
  warning colour); then the positive colour, and if that is too close as well, the dimmed text colour
  (`Format.normalColor`). In the popup the percentage is bold and coloured while not normal.
- Time mark: a short stroke across each ring (a vertical one on each bar) at the share of the window
  that has passed, `1 − (resets_at − now) / window` (`Format.elapsedShare`); none without a reset
  time or window length, or after the reset. Usage ahead of the mark runs faster than an even spread.
  Mark and pace colour belong to the limit shown on the ring (`Format.ringLimits`).
- On a vertical panel the gauges stack; the panel width sets their size ("Number": letter and value
  on two lines, shrunk to the width).
- Tooltip: all limits with countdown, e.g. "5 h: 42 % · Reset in 2 h 13 min".
- Context menu "Refresh now": one collector pass right away. The logs are read anew; the limits only
  when due (5-minute interval, pause after a rate limit). For a minute the footer and tooltip then say
  when they come next ("limits again from 14:20", from `limits_next_request_at` – last request plus
  the interval, or the end of a pause; `null` before the first request).
- Clicking opens the full view as a popup.

### Desktop / popup (full)

```
┌─ Claude ── pro ────────────────┐ ┌─ Codex ── plus ────────────────┐
│ 5 h  ██████░░░░ 42%  2h13m     │ │ Week █░░░░░░░░░  8%  6d 4h     │
│ Week ██░░░░░░░░ 18%  4d 2h     │ │                                │
│ Today  1.2 M   Week 8.4 M      │ │ Today  15 k    Week 210 k      │
│ Month 31.0 M                   │ │ Month 890 k                    │
│ ▁▂▅▃▁▇█▄▂▁▃▅ … (30 days)       │ │ ▁▁▂▁▁▃▁▁▁▂▁▁ … (30 days)       │
│ Updated 30 s ago · OAuth       │ │ Updated 3 d ago · Session log  │
└────────────────────────────────┘ └────────────────────────────────┘
```

- Two cards side by side as soon as two cards at their minimum width (usually the
  Today/Week/Month row) plus spacing fit; otherwise stacked.
- Limit data older than 6 h: bar faded, footer in warning colour with "· stale", ring in the
  panel faded, tooltip with "(stale)".
- Token counts compact (k/M, decimal separator of the system language); tooltip with the split
  input/output/cache read/cache write.
- Bar chart: total tokens per day, tooltip with date and value.
- Footer: age of the limit data and source.
- `resets_at` in the past → show the limit as "reset · 0 %" until new data
  arrives.
- `errors` not empty → subtle notice in the card, other values remain visible.
- Collector problems (Python missing or too old, a failed run, a collector newer than the widget's
  QML after an update) → a notice in the widget instead of data; see "Error handling".

### Settings

- Warning/critical thresholds (default 70/90).
- Displayed providers (Claude, Codex; both on by default).
- Additional accounts (up to 8): provider, directory (folder picker), name, short label for the ring, "Show".
  Each shown account gets its own ring and card.
- Panel display: ring or number.
- Notifications on/off (default on).
- Daily update check on/off (default on).

## Notifications

The collector decides, the widget shows: due notices come in the envelope and are sent as
KNotification (`componentName: plasma_workspace`, hint `x-kde-display-appname`) as soon as a
Claude or Codex limit reaches the **first** or **second** threshold (default 80 % and 95 %, set in the
widget) — once per limit and level per window. A new window (different `resets_at` or window length)
or a drop below the first threshold re-arms the notification; a window whose reset has passed counts as
0 %. If a limit jumps straight past the second threshold, only that notification is sent; it is marked
as urgent. Below the first threshold a limit gets an early warning when the forecast sees it full soon:
the **5-hour limit** within 30 minutes, the **weekly limit** within 24 hours ("Claude: 5-hour limit
full in ~25 min", "Now 62 % · Reset in …") — likewise once per window, normal urgency. Optionally (off
by default) a window that had warned says so when it resets ("Claude: 5-hour limit reset").
Additional accounts notify like the main account, under their label ("Claude (Work): 5-hour limit at
82 %"). A provider or account that is not shown produces no notifications; its entries of what was
already notified are kept. Notifications already sent are recorded in `state.json` under `notified`. The notification thresholds
are independent of the widget's colour thresholds.

The widget passes its settings to the collector: `LIMIT_RINGS_NOTIFY=0|1`,
`LIMIT_RINGS_THRESHOLDS=80,95` (two rising values from 1 to 100, otherwise the default) and
`LIMIT_RINGS_RESET_NOTICE=0|1`; `LIMIT_RINGS_PROVIDERS` and `LIMIT_RINGS_ACCOUNTS` say what is shown. With notifications switched off in an instance, its passes leave due
notices untouched (nothing is recorded), so an instance that has them on – or switching them back on –
still shows them. Several instances share what was already notified; with different thresholds the
instance that runs first decides.

## Error handling

- Invalid JSON lines are skipped and counted (logged at debug level), not an error.
- Each provider is processed in its own `try`; an error only adds an entry to that provider's `errors`.
- **OAuth endpoint:** queried at most every 5 minutes (timestamp in `state.json`), timeout
  10 s. On 401/403, redirect, timeout, network error or unexpected response shape (also:
  not a single usable window) → status line cache or last good values, whichever
  is newer. As long as the last OAuth attempt succeeded, its data stays in place
  during the 5-minute throttle — a newer status line does not displace it. Unexpected
  response shapes are logged with field names (never with values from the request).
- **Rate limits:** on 429/503 (`sources/backoff.py`) the source pauses as long as `Retry-After` says,
  otherwise 10, 20, 40, then 60 minutes per further refusal; each pause lasts 5 min to 6 h. The pause
  (`oauth_pause` in `state.json`) survives between runs and ends with the next success. Meanwhile the
  fallbacks above apply, and the provider gets `limits_paused_until` (otherwise `null`) – the footer
  names it.
- Collector output goes to `~/.cache/limit-rings/collector.log` (256 KB, one backup). The widget shows
  missing Python, a failed run or a newer collector than its QML (after an update: restart Plasma).
  While the systemd timer of a version ≤ 0.2 still exists, the collector refuses to run (it would
  collect without the lock) and the widget shows the command that removes the timer.

## Security

- `~/.claude/.credentials.json` (and the login file of each additional account) is only read. The collector does **not** refresh any tokens and
  never writes to this file; an expired token leads to the fallback until Claude Code refreshes
  it itself.
- The token is sent exclusively to `api.anthropic.com` — never into `stats.json`,
  `state.json`, logs or error messages. Redirects are rejected because `urllib` would otherwise
  send the `Authorization` header along to the redirect target.
- The update check sends one unauthenticated GET to `api.github.com` per day and widget instance.
- `stats.json`, `state.json` and the status line cache are created with mode `0600`,
  `~/.cache/limit-rings/` with `0700`.

## Installation

`tools/build_plasmoid.py` builds the one package for both ways: plasmoid, collector
(`contents/collector/`), catalogs compiled by `tools/msgfmt.py` (`contents/locale/`) and
`contents/code/build.js` (install source, store ID, repo path, version).

- **KDE Store:** the release workflow builds the `.plasmoid`; KNewStuff unpacks it to
  `~/.local/share/plasma/plasmoids/`.
- **`install.sh`:** checks `kpackagetool6` and Python ≥ 3.10 (naming the install command per
  distribution), retires the systemd timer of versions ≤ 0.2 and their files, builds the package with
  `--source git` and installs or upgrades it; the Agent Stats migration and the status line hook work
  as before.
- **`uninstall.sh`:** removes the package and leftovers, the cache after confirmation.

## Tests

**Collector (pytest)** with anonymised JSONL fixtures in the format of the real logs:

- Deduplication of the repeated Claude lines.
- An incomplete last line is not read, but is in the next run.
- Truncated or replaced file → re-read without double counting.
- Day/week/month boundaries, incl. DST change (2026-10-25).
- Codex limits with `secondary: null`; Codex events without `info`.
- OAuth success, 401, timeout and unexpected response (HTTP mocked) → correct source.
- An error in one provider leaves the other untouched.
- `stats.json` satisfies the rules from the section "Interface" (30 days, `total` sum).

**Install scripts (pytest, `collector/tests/test_install.py`):** `install.sh` and `uninstall.sh`
run in a scratch `HOME`; `systemctl`, `kpackagetool6` and `pgrep` are stubs that log their calls; a
reduced `PATH` simulates missing programs. Covers the fresh install and every migration step above.

**Tooling and entry point:** `tools/` (msgfmt, build, release notes) with pytest; `widget.py` lock
and envelope.

**Widget:** formatting functions (k/M, countdown, threshold colour, "reset") as pure
functions in `contents/code/format.js`, tested with `qmltestrunner`. Presentation checked manually with
`plasmoidviewer` as a panel and as a desktop widget.

**Acceptance:** run against the real logs; compare today's tokens for Claude and Codex with an
independent `jq` count.

## Project structure

```
limit-rings/
  collector/
    run.py
    limit_rings/  collect.py  widget.py  notify.py  aggregate.py  state.py  …  sources/
    tests/
  plasmoid/io.github.flexomatic81.limitrings/
    metadata.json
    contents/ui/      main.qml  FullRepresentation.qml  UpdateMessage.qml  …
    contents/code/    format.js  build.js
    contents/config/  main.xml  config.qml
  po/  plasmoid/  collector/  update.sh
  tools/  build_plasmoid.py  msgfmt.py  release_notes.py  install-lib.sh
  .github/workflows/  test.yml  release.yml
  install.sh  uninstall.sh  README.md  CHANGELOG.md
  docs/  design.md  store/description.md
```

## Open risks

- **The OAuth usage endpoint is undocumented.** Response shape and availability may change.
  Mitigation: encapsulated in `claude_limits.py`, fallback to the status line, logging on
  unexpected shape. The exact response shape is determined at the start of implementation with a
  real query and recorded as a fixture.
- **The status line fallback only works with CLI usage.** Whether the desktop app invokes the status
  line is unclear; if in doubt, the fallback delivers data less often.
- **Codex limits go stale** when Codex has not been used for a while — made visible by the age display.
