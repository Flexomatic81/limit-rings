# Changelog

## 0.3.0

- Available from the KDE Store ("Get New Widgets…"). The widget brings and runs its own collector:
  no systemd timer, no `gettext`, `notify-send` or `zip` needed – only Python 3.10 or newer.
- Notifications come from the widget and can be switched off in its settings.
- The widget points out new versions (asks GitHub once a day; can be switched off).
- `install.sh` checks its requirements and names the install command for your distribution.
- The collector logs to `~/.cache/limit-rings/collector.log` instead of the journal.

## 0.2.0

- Renamed from Agent Stats to Limit Rings; German translation.
