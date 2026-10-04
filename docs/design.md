# Agent-Stats Plasmoid — Design

As of: 2026-10-03 · Status: under review

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

**Explicitly not in version 1** (possible later): cost estimate in $, breakdown by
project/model, active sessions.

## Environment

- KDE Plasma 6, `kpackagetool6`, Python ≥ 3.10.
- Claude Code transcripts: `~/.claude/projects/**/*.jsonl` (incl. `*/subagents/*.jsonl`), often
  several hundred MB.
- Codex session logs: `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`.
- Claude Code status line: a custom status line script (expected by `install.sh` at
  `~/.claude/statusline-command.sh`) receives, among other things,
  `.rate_limits.five_hour.{used_percentage,resets_at}` via stdin.

## Architecture

```
~/.claude/projects/**/*.jsonl ─┐
~/.codex/sessions/**/*.jsonl  ─┼─► agent-stats-collect (Python, systemd user timer, 60 s)
Anthropic OAuth usage API     ─┤        │  incremental: byte offset per file in state.json
Status line cache (fallback)  ─┘        ▼
                              ~/.cache/agent-stats/stats.json  (atomic: tmp + rename)
                                        │
                                        ▼
                         Plasmoid (QML) reads every 30 s → panel + desktop/popup
```

Decisions:

- **Collector separate from the widget** (systemd user timer instead of running from the plasmoid):
  independently testable, no duplicate computation with two widget instances, errors in the
  collector do not affect `plasmashell`.
- **Claude limits from two sources:** OAuth usage endpoint as the primary source (covers all
  usage, including claude.ai/desktop app), status line cache as the fallback.
- **Python standard library only** — no venv, no dependencies.

## Components

| Unit | Responsibility | Dependencies |
|---|---|---|
| `sources/claude_logs.py` | Reads new lines of the Claude transcripts; yields token events (timestamp, input, output, cache read, cache write). Books only increments per `(message.id, requestId)`. | `state` |
| `sources/codex_logs.py` | Reads `event_msg`/`token_count` events; yields token events from `last_token_usage` and the most recent `rate_limits` object with its timestamp. | `state` |
| `sources/codex_limits.py` | Queries the Codex usage endpoint (`chatgpt.com/backend-api/wham/usage`) with the ChatGPT login from `~/.codex/auth.json` (no redirects, at most every 5 min). Needed because Codex via the Claude Code plugin uses ephemeral sessions without a session log. On error, the last state (including from the session log) is kept. | HTTP (urllib), file system |
| `sources/claude_limits.py` | Queries the OAuth usage endpoint (no redirects); on error, the status line cache. Returns limits + source + timestamp. | HTTP (urllib), file system |
| `aggregate.py` | Pure functions: daily buckets → totals for today/week/month, gap-free 30-day series. | none |
| `state.py` | Offset and inode per file, seen message IDs, daily buckets per provider, time of the last OAuth query. | file system |
| `collect.py` | Orchestrates a run, writes `stats.json` atomically. CLI entry point `agent-stats-collect`. | all of the above |
| Plasmoid `io.github.flexomatic81.agentstats` | Presentation only, no computation. | `stats.json` |
| Status line addition | One line in `statusline-command.sh`: writes `.rate_limits` to `~/.cache/agent-stats/claude-statusline-limits.json`. | — |

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

- `~/.cache/agent-stats/state.json` holds `{offset, inode}` per file, the daily buckets per
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

The only interface between collector and widget. Mode `0600`, written atomically.

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
      "plan": "pro",
      "tokens": {
        "today": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "total": 0},
        "week":  {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "total": 0},
        "month": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "total": 0}
      },
      "daily": [{"date": "2026-09-04", "total": 123456}],
      "errors": [],
      "auth": {"status": "ok", "expires_at": "2026-10-04T19:29:15+02:00"}
    },
    "codex": {
      "limits": [
        {"id": "primary", "used_percent": 8.0,
         "resets_at": 1791280728, "window_minutes": 10080}
      ],
      "limits_source": "session_log",
      "limits_updated_at": "2026-09-29T21:30:00+02:00",
      "plan": "plus",
      "tokens": {"today": {}, "week": {}, "month": {}},
      "daily": [],
      "errors": [{"code": "logs_unreadable", "count": 1}]
    }
  }
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

  Card: line below the bar ("Full in ~1 h 20 min at current pace (13:40)", with the weekday
  "(Sat 14:00)" once a day or more away, or "Lasts until reset at current pace"); tooltip: short form.
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
- `errors` lists problems as codes (`logs_unreadable` with `count`, `logs_failed`,
  `limits_unavailable`); the other fields then carry the last good values.
- `stats.json` holds no display texts: the plasmoid builds limit names (from `window_minutes` and
  `model`), error messages and the catch-all entry in the system language. `state.json` keeps an
  English `label` per limit only so that an older collector still reads it after a downgrade.
- The widget ignores a `stats.json` with an unknown `schema` version and shows a notice.

## Presentation

### Panel (compact)

- For each enabled provider, a ring with the abbreviation "C" / "X": **outer** the highest weekly
  limit, **inner** (thinner) the 5-hour limit, each ring with its own threshold colour; without a
  5-hour window only the outer ring, without either kind of window the highest value. "Number"
  display: the highest value.
- Colour by threshold (default): below 70 % neutral, from 70 % warning, from 90 % critical —
  Plasma theme colours (`Kirigami.Theme.neutralTextColor` / `negativeTextColor`).
- Tooltip: all limits with countdown, e.g. "5 h: 42 % · Reset in 2 h 13 min".
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
- `stats.json` missing or older than 5 minutes → notice "Collector not running" with the command
  `systemctl --user status agent-stats.timer`.

### Settings

- Warning/critical thresholds (default 70/90).
- Displayed providers (Claude, Codex; both on by default).
- Panel display: ring or number.

## Notifications

The collector (not the widget) shows a desktop notification via `notify-send` as soon as a
Claude or Codex limit reaches **80 %** or **95 %** — once per limit and level per window.
A new window (different `resets_at`) or a drop below 80 % re-arms the notification; a window whose
reset has passed counts as 0 %. If a limit jumps straight past 95 %, only the 95 % notification is
sent; it is marked as urgent. In addition, the **5-hour limit** gets an early warning when the forecast
sees it full within 30 minutes and 80 % has not yet been reached ("Claude: 5-hour limit full in ~25 min",
"Now 62 % · Reset in …") — likewise once per window, normal urgency; weekly limits
get no early warning. Notifications already sent are recorded in `state.json` under
`notified`. The thresholds are fixed and independent of the widget's colour thresholds. If
`notify-send` is missing or the call fails, this is logged; the run continues normally.

## Error handling

- Invalid JSON lines are skipped and counted (logged at debug level), not an error.
- Each provider is processed in its own `try`; an error only adds an entry to that provider's `errors`.
- **OAuth endpoint:** queried at most every 5 minutes (timestamp in `state.json`), timeout
  10 s. On 401/403, redirect, timeout, network error or unexpected response shape (also:
  not a single usable window) → status line cache or last good values, whichever
  is newer. As long as the last OAuth attempt succeeded, its data stays in place
  during the 5-minute throttle — a newer status line does not displace it. Unexpected
  response shapes are logged to the journal with field names (never with values from the request).
- Collector output goes to the journal: `journalctl --user -u agent-stats`.

## Security

- `~/.claude/.credentials.json` is only read. The collector does **not** refresh any tokens and
  never writes to this file; an expired token leads to the fallback until Claude Code refreshes
  it itself.
- The token is sent exclusively to `api.anthropic.com` — never into `stats.json`,
  `state.json`, logs or error messages. Redirects are rejected because `urllib` would otherwise
  send the `Authorization` header along to the redirect target.
- `stats.json`, `state.json` and the status line cache are created with mode `0600`,
  `~/.cache/agent-stats/` with `0700`.

## Installation

`install.sh` (idempotent) and `uninstall.sh`:

1. Collector to `~/.local/share/agent-stats/`, launcher script `~/.local/bin/agent-stats-collect`.
2. `systemd/agent-stats.service` (oneshot) and `agent-stats.timer` (`OnBootSec=30s`,
   `OnUnitActiveSec=60s`) to `~/.config/systemd/user/`, `daemon-reload`, enable the timer,
   start the first run immediately.
3. Plasmoid via `kpackagetool6 -t Plasma/Applet --install` or `--upgrade`.
4. Status line: the script shows the line to be inserted and only inserts it after explicit
  confirmation — with a backup copy `statusline-command.sh.bak-agent-stats` first. The line
  writes to its own `mktemp` file on each call and renames it afterwards, so that parallel
  Claude sessions do not produce half-written files.

`uninstall.sh` reverts 1–3 and points out the status line addition; it removes
`~/.cache/agent-stats/` only after confirmation.

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

**Widget:** formatting functions (k/M, countdown, threshold colour, "reset") as pure
functions in `contents/code/format.js`, tested with `qmltestrunner`. Presentation checked manually with
`plasmoidviewer` as a panel and as a desktop widget.

**Acceptance:** run against the real logs; compare today's tokens for Claude and Codex with an
independent `jq` count.

## Project structure

```
agent-stats/
  collector/
    agent_stats/
      __init__.py  collect.py  aggregate.py  state.py
      sources/  __init__.py  claude_logs.py  codex_logs.py  claude_limits.py
    tests/
      fixtures/
  plasmoid/io.github.flexomatic81.agentstats/
    metadata.json
    contents/ui/      main.qml  CompactRepresentation.qml  FullRepresentation.qml
                      ProviderCard.qml  configGeneral.qml
    contents/code/    format.js
    contents/config/  main.xml  config.qml
  systemd/  agent-stats.service  agent-stats.timer
  install.sh  uninstall.sh  README.md
  docs/design.md
```

## Open risks

- **The OAuth usage endpoint is undocumented.** Response shape and availability may change.
  Mitigation: encapsulated in `claude_limits.py`, fallback to the status line, logging on
  unexpected shape. The exact response shape is determined at the start of implementation with a
  real query and recorded as a fixture.
- **The status line fallback only works with CLI usage.** Whether the desktop app invokes the status
  line is unclear; if in doubt, the fallback delivers data less often.
- **Codex limits go stale** when Codex has not been used for a while — made visible by the age display.
