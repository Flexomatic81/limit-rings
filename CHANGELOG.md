# Changelog

## 0.4.0

- Several accounts per provider (own `CLAUDE_CONFIG_DIR` / `CODEX_HOME`), each with its own ring, card
  and notifications – set up under "Additional accounts" in the settings.
- A mark on each ring and bar shows how much of the window has passed; a ring turns to the warning
  colour as soon as it would run out before the reset at the current pace.
- Shows Claude extra usage and Codex credits when your account has them.
- Early warning for the weekly limit too (when it would be full within 24 hours), adjustable
  notification thresholds and an optional notice when a limit that had warned has reset.
- "Refresh now" in the context menu; the card says when the limits are asked for next.
- Works on vertical panels.
- When a provider answers "too many requests", Limit Rings pauses as long as it asks; the card shows
  until when.
- Unticking Claude or Codex in the settings now stops reading its login and logs, not just its display.
- The normal state no longer looks like a warning when the accent colour is close to the warning
  colour (e.g. orange); the theme's positive colour or grey is used instead.
- A limit whose window changes length starts its forecast and notifications afresh; hidden providers
  no longer send notifications; a reset window says so below the bar; the settings show the chosen
  panel style instead of an empty box.

## 0.3.0

- Available from the KDE Store ("Get New Widgets…"). The widget brings and runs its own collector:
  no systemd timer, no `gettext`, `notify-send` or `zip` needed – only Python 3.10 or newer.
- Notifications come from the widget and can be switched off in its settings.
- The widget points out new versions (asks GitHub once a day; can be switched off).
- `install.sh` checks its requirements and names the install command for your distribution.
- The collector logs to `~/.cache/limit-rings/collector.log` instead of the journal.

## 0.2.0

- Renamed from Agent Stats to Limit Rings; German translation.
