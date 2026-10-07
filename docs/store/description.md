# KDE Store listing

Category: Plasma 6 Extensions → Plasma Widgets. License: MIT. Source: https://github.com/Flexomatic81/limit-rings

## English

**Limit Rings** shows the usage limits and token statistics of **Claude Code** and **Codex** in your panel:
one double ring per provider (outer: weekly limit, inner: 5-hour limit), a popup with reset countdowns,
forecasts and a 30-day history, and a notification when a limit reaches 80 % or 95 %.

**Requires Python 3.10 or newer** (`python3`, preinstalled on most distributions). Nothing else.

**What it reads and where it connects – please read:**
- Reads the local logs of Claude Code (`~/.claude/projects`) and Codex (`~/.codex/sessions`).
- Reads the login tokens of Claude Code (`~/.claude/.credentials.json`) and Codex (`~/.codex/auth.json`)
  and sends them **only** to `api.anthropic.com` and `chatgpt.com` to fetch your limits – at most every
  5 minutes. They are never stored, logged or refreshed, and never used to run models. Untick a provider
  under "Show:" in the settings and neither its login nor its logs are read.
- These are **unofficial, undocumented endpoints**; they may change at any time. Anthropic intends its
  subscription login for its own applications and has not said whether such read-only use is allowed.
  Check yourself whether this use complies with the terms of Anthropic and OpenAI (details in the
  README). Not affiliated with Anthropic or OpenAI;
  "Claude" and "Codex" are trademarks of their owners.
- Asks `api.github.com` once a day whether a new version exists (switch off in the settings).
- Runs a bundled Python script every 60 s; data and log stay in `~/.cache/limit-rings`
  (remove it after uninstalling: `rm -r ~/.cache/limit-rings`).

Several accounts per provider are possible: list further `CLAUDE_CONFIG_DIR` / `CODEX_HOME` directories under "Additional accounts" in the settings; each gets its own ring and card, and only the listed directories are read.

Optional status line fallback for Claude limits: see the README on GitHub (manual step, needs `jq`).
Bugs and ideas: https://github.com/Flexomatic81/limit-rings/issues

## Deutsch

**Limit Rings** zeigt Nutzungslimits und Token-Statistiken von **Claude Code** und **Codex** im Panel:
ein Doppelring pro Anbieter (außen Wochenlimit, innen 5-Stunden-Limit), ein Popup mit Reset-Countdown,
Prognose und 30-Tage-Verlauf sowie eine Benachrichtigung, wenn ein Limit 80 % oder 95 % erreicht.

**Voraussetzung: Python 3.10 oder neuer** (`python3`, auf den meisten Distributionen vorinstalliert).

**Was gelesen und wohin verbunden wird – bitte lesen:**
- Liest die lokalen Logs von Claude Code (`~/.claude/projects`) und Codex (`~/.codex/sessions`).
- Liest die Login-Tokens von Claude Code (`~/.claude/.credentials.json`) und Codex (`~/.codex/auth.json`)
  und schickt sie **nur** an `api.anthropic.com` bzw. `chatgpt.com`, um die Limits abzufragen – höchstens
  alle 5 Minuten. Sie werden nie gespeichert, protokolliert oder erneuert und nie für Modellaufrufe
  genutzt. Wer einen Anbieter in den Einstellungen unter „Anzeigen:“ abwählt, bei dem werden weder Login
  noch Logs gelesen.
- Das sind **inoffizielle, undokumentierte Schnittstellen**, die sich jederzeit ändern können. Anthropic
  sieht den Abo-Login für die eigenen Anwendungen vor und hat sich nicht dazu geäußert, ob solch ein reines
  Lesen erlaubt ist. Ob diese Nutzung mit den Bedingungen von Anthropic und OpenAI vereinbar ist, bitte
  selbst prüfen (Details in der README). Kein Bezug zu
  Anthropic oder OpenAI; „Claude“ und „Codex“ sind Marken ihrer Inhaber.
- Fragt einmal täglich `api.github.com` nach einer neuen Version (in den Einstellungen abschaltbar).
- Führt alle 60 s ein mitgeliefertes Python-Skript aus; Daten und Log liegen in `~/.cache/limit-rings`
  (nach dem Deinstallieren entfernen: `rm -r ~/.cache/limit-rings`).

Mehrere Konten pro Anbieter sind möglich: weitere `CLAUDE_CONFIG_DIR`-/`CODEX_HOME`-Verzeichnisse unter „Additional accounts“ in den Einstellungen eintragen; jedes bekommt einen eigenen Ring und eine eigene Karte, gelesen werden nur die eingetragenen Verzeichnisse.

Optionaler Statuszeilen-Fallback für Claude-Limits: siehe README auf GitHub (manuell, braucht `jq`).
Fehler und Ideen: https://github.com/Flexomatic81/limit-rings/issues
