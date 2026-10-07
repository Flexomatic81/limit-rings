# Limit Rings

KDE Plasma 6 widget showing usage limits and token statistics for **Claude Code** and **Codex**.

- Panel: one double ring per provider — the outer ring shows the weekly limit, the inner one the
  5-hour limit; the tooltip lists all limits with a countdown.
- A mark on each ring and bar shows how much of the window has passed, and a ring turns to the warning
  colour as soon as it would run out before the reset at the current pace.
- Desktop/popup: limits with a reset countdown, tokens for today/week/month, 30-day history.
- Claude extra usage (amount spent and monthly limit) and Codex credits, when your account has them.
- Forecast of when a limit will be reached at the current pace (5 h: last 30 min, week: last 24 h).
- Desktop notification when a limit reaches 80 % or 95 %, plus an early warning when the forecast
  says the 5-hour limit will be full within 30 minutes (each at most once per window).
- Hint in the card and tooltip when the Claude login has expired.
- Breakdown of Claude tokens since the weekly reset by project (Git repository) and model — only
  for the transcripts on the current machine, as a share of tokens (not of the limit).
- Widget and notifications follow the system language (English, German).

## Important: unofficial APIs and your logins

Limit Rings fetches usage limits from **undocumented endpoints** of Anthropic
(`api.anthropic.com/api/oauth/usage`) and OpenAI (`chatgpt.com/backend-api/wham/usage`) – the
numbers Claude Code and Codex show you themselves. To ask for them, it uses the logins that Claude Code
and Codex store on your machine.

### What is read and where it goes

| | Claude Code | Codex |
|---|---|---|
| File | `~/.claude/.credentials.json` | `~/.codex/auth.json` |
| Read from it | access token, its expiry, plan name | access token, account ID |
| Sent to | `api.anthropic.com` only | `chatgpt.com` only |
| Asked for | the usage numbers of your plan | the usage numbers of your plan |
| How often | at most every 5 minutes | at most every 5 minutes |

If a provider answers "too many requests", Limit Rings waits as long as it asks (at most 6 hours)
before the next request.

### What Limit Rings never does

- Run models or send prompts with your login – it only asks for the usage numbers.
- Refresh, store, copy or log a token. An expired token simply goes unused until Claude Code or Codex
  renews it.
- Write to the login files of Claude Code or Codex.
- Follow redirects – the token could otherwise end up at another host.
- Touch a provider you have switched off: with Claude or Codex unticked under "Show:" in the
  settings, its login and logs are not read and its endpoint is not asked.

### The providers' terms

Anthropic's documentation says that the subscription login is
["intended exclusively for purchasers of Claude Free, Pro, Max, Team, and Enterprise subscription
plans and is designed to support ordinary use of Claude Code and other native Anthropic
applications"](https://code.claude.com/docs/en/legal-and-compliance#authentication-and-credential-use).
Limit Rings is not such an application. It runs no models and keeps no tokens – it reads the usage
numbers that Claude Code's `/usage` shows, for your own account, on your own machine. Anthropic has not
said whether such read-only use is allowed, and it reserves the right to enforce its rules without
prior notice. OpenAI has published no rules for its usage endpoint.

So please check the terms of service of Anthropic and OpenAI yourself and decide whether you are
comfortable with this. If not, switch the provider off in the widget's settings. Should a provider
block these requests, Limit Rings falls back to local data (status line or session logs).

This project is not affiliated with Anthropic or OpenAI; "Claude" and "Codex" are trademarks of their
respective companies.

## How it works

The widget brings its own collector (`collector/`, Python standard library only) and runs it every 60 s.
The collector incrementally reads `~/.claude/projects/**/*.jsonl` and `~/.codex/sessions/**/*.jsonl`,
writes `~/.cache/limit-rings/stats.json` and hands the result and any due notifications back to the
widget; its log is `~/.cache/limit-rings/collector.log`.

Claude limits come from the (undocumented) OAuth usage endpoint; the token from
`~/.claude/.credentials.json` is only read and only sent to `api.anthropic.com`. If the endpoint
fails, a capture of the Claude Code status line serves as a fallback.

Codex limits likewise come directly from the Codex service (ChatGPT login from `~/.codex/auth.json`,
token only read and only sent to `chatgpt.com`); the fallback is the session logs. This is
necessary because Codex running as a Claude Code plugin does not write session logs. For the same
reason, the Codex token statistics only count Codex sessions run in a terminal.

## Installation

Requirements: KDE Plasma 6 and Python ≥ 3.10 (`python3`, no extra packages). `jq` only for the
optional status line fallback.

### From the KDE Store (recommended)

Right-click the panel or desktop → "Add Widgets…" → "Get New Widgets…" → "Download New Plasma Widgets",
search for **Limit Rings**, install it, then drag it onto a panel and/or the desktop.

### From GitHub

```bash
git clone https://github.com/Flexomatic81/limit-rings.git
cd limit-rings
./install.sh                     # asks before modifying the status line
./install.sh --statusline        # inserts the status line hook without asking
./install.sh --migrate-widgets   # switches placed "Agent Stats" widgets without asking
```

`install.sh` checks the requirements first and names the install command for your distribution if
something is missing. Use one way or the other: both install the same widget, the last one wins.

### Updating

The widget tells you when a new version is out (it asks GitHub once a day; switch it off in its
settings). Store installs update via "Get New Widgets…" or Discover; GitHub installs with
`git pull && ./install.sh`. Afterwards restart Plasma (`systemctl --user restart plasma-plasmashell`)
or log out and back in.

### After installing

Place the widget as described above and check:

```bash
jq '.providers | map_values({limits_source, errors})' ~/.cache/limit-rings/stats.json
```

- Token statistics only count the logs of **this** machine; the limits belong to the account and
  are the same on every machine. To use Limit Rings on several machines, simply install it on each.
- If `~/.claude/.credentials.json` holds a valid token, the Claude limits come via OAuth
  (`limits_source: "oauth"`). Claude Code only refreshes the token while it runs in a terminal (it
  is valid for about 8 h); the Claude desktop app does not write a token to this file. Without a
  valid token, the status line provides the limits as long as Claude Code is running in a terminal.
- The status line fallback requires a custom Claude Code status line script at
  `~/.claude/statusline-command.sh` containing a line `input=$(cat)`; `install.sh` inserts the
  required line (`statusline-snippet.sh`) there. Without such a script, this step is skipped.
  Store installs do not touch the status line; add the snippet by hand if you want the fallback.

### Upgrading from Agent Stats

Versions up to 0.1 were called *Agent Stats*. `./install.sh` takes an existing installation over:
it stops and removes the old timer and collector, moves `~/.cache/agent-stats` to
`~/.cache/limit-rings` (history and notification state are kept) and points the status line hook
at the new path (backup: `statusline-command.sh.bak-limit-rings`). Widgets that are already placed
are switched to the new plugin ID after confirmation, keeping position and settings – this
restarts the Plasma shell. `./install.sh --migrate-widgets` does it without asking.
From 0.3 on, `install.sh` also removes the systemd timer of earlier versions; history and
notification state are kept.

## Uninstalling

```bash
./uninstall.sh          # asks whether to delete ~/.cache/limit-rings
./uninstall.sh --purge
```

Store installs: uninstall the widget via "Get New Widgets…" (removing it from the panel does not uninstall
the package), then `rm -r ~/.cache/limit-rings`.

## Troubleshooting

```bash
tail -n 50 ~/.cache/limit-rings/collector.log
jq . ~/.cache/limit-rings/stats.json
# one pass by hand; LIMIT_RINGS_NOTIFY=0 leaves due notices for the widget to show
LIMIT_RINGS_NOTIFY=0 python3 ~/.local/share/plasma/plasmoids/io.github.flexomatic81.limitrings/contents/collector/run.py
```

## Privacy & network

Limit Rings contacts `api.anthropic.com` and `chatgpt.com` (limits, at most every 5 minutes and paused
after "too many requests", with the logins described in
[Important: unofficial APIs and your logins](#important-unofficial-apis-and-your-logins); not for a
provider you have switched off) and `api.github.com` (new version check, once a day, no personal data;
can be switched off). Nothing else leaves your machine.

## Development

Contributions are welcome – see [CONTRIBUTING.md](CONTRIBUTING.md). Pull requests go against `dev`.

```bash
cd collector && uv run --no-project --with pytest pytest -q
/usr/lib/qt6/bin/qmltestrunner -input plasmoid/tests
plasmawindowed io.github.flexomatic81.limitrings
python3 tools/build_plasmoid.py --source store   # dist/limit-rings-<version>.plasmoid
```

Releasing: raise `Version` in `metadata.json`, add a `CHANGELOG.md` section, push a tag `vX.Y.Z`.
The release workflow tests, builds and drafts a GitHub release; upload its `.plasmoid` to the KDE
Store, then publish the draft.

## Translations

Texts live in `po/plasmoid/<lang>.po` (widget) and `po/collector/<lang>.po` (notifications).
To add a language, create empty catalogs from the current texts – `msginit` also sets the
plural rules of the language, which differ from German for e.g. Polish or Russian:

```bash
tmp=$(mktemp -d) && po/update.sh --extract "$tmp"
msginit --no-translator -l <lang> -i "$tmp/plasmoid.pot" -o po/plasmoid/<lang>.po
msginit --no-translator -l <lang> -i "$tmp/collector.pot" -o po/collector/<lang>.po
```

Then translate the `msgstr` entries and run `./install.sh`. gettext is only needed to edit catalogs,
not to install. After changing texts in the code,
run `po/update.sh` to merge them into all catalogs; `collector/tests/test_translations.py` fails
while a catalog is incomplete.

## License

MIT, see [LICENSE](LICENSE).
