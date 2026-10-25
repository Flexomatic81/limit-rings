# KDE Store listing

Category: KDE Plasma Extensions → Plasma 6 Extensions → Plasma 6 Applets. License: MIT. Source: https://github.com/Flexomatic81/limit-rings

## English

**Limit Rings** shows the usage limits and token statistics of **Claude Code** and **Codex** in your panel:
one double ring per provider (outer: weekly limit, inner: 5-hour limit), a popup with reset countdowns,
forecasts and a history of up to 12 months, a breakdown of the tokens since the weekly reset by project and
model, and a notification when a limit reaches 80 % or 95 % (adjustable).

**Requires KDE Plasma 6 and Python 3.10 or newer** (`python3`, preinstalled on most distributions). Nothing else.

**What it reads and where it connects – please read:**
- Reads the local logs of Claude Code (`~/.claude/projects`) and Codex (`~/.codex/sessions`).
- Reads the login tokens of Claude Code (`~/.claude/.credentials.json`) and Codex (`~/.codex/auth.json`)
  and sends them **only** to `api.anthropic.com` and `chatgpt.com` to fetch your limits – at most every
  5 minutes. They are never stored, logged or refreshed, and never used to run models. Untick a provider
  under "Show:" in the settings and neither its login nor its logs are read.
- Rather not hand over your login? Untick a provider under "Live limits via login" in the settings: its
  login file is never opened and its endpoint never asked; the limits then come only from Claude's status
  line or Codex's session logs (fewer details – see "Without login" in the README).
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
Prognose, einem Verlauf über bis zu 12 Monate und einer Aufschlüsselung der Tokens seit dem Wochenreset nach
Projekt und Modell sowie eine Benachrichtigung, wenn ein Limit 80 % oder 95 % erreicht (einstellbar).

**Voraussetzung: KDE Plasma 6 und Python 3.10 oder neuer** (`python3`, auf den meisten Distributionen vorinstalliert).

**Was gelesen und wohin verbunden wird – bitte lesen:**
- Liest die lokalen Logs von Claude Code (`~/.claude/projects`) und Codex (`~/.codex/sessions`).
- Liest die Login-Tokens von Claude Code (`~/.claude/.credentials.json`) und Codex (`~/.codex/auth.json`)
  und schickt sie **nur** an `api.anthropic.com` bzw. `chatgpt.com`, um die Limits abzufragen – höchstens
  alle 5 Minuten. Sie werden nie gespeichert, protokolliert oder erneuert und nie für Modellaufrufe
  genutzt. Wer einen Anbieter in den Einstellungen unter „Anzeigen:“ abwählt, bei dem werden weder Login
  noch Logs gelesen.
- Login lieber nicht hergeben? In den Einstellungen unter „Live-Limits per Login:“ den Anbieter abwählen:
  Dann wird seine Login-Datei nie geöffnet und sein Endpunkt nie gefragt; die Limits kommen nur noch aus
  der Claude-Statuszeile bzw. den Codex-Sitzungslogs (weniger Details – siehe „Without login“ in der README).
- Das sind **inoffizielle, undokumentierte Schnittstellen**, die sich jederzeit ändern können. Anthropic
  sieht den Abo-Login für die eigenen Anwendungen vor und hat sich nicht dazu geäußert, ob solch ein reines
  Lesen erlaubt ist. Ob diese Nutzung mit den Bedingungen von Anthropic und OpenAI vereinbar ist, bitte
  selbst prüfen (Details in der README). Kein Bezug zu
  Anthropic oder OpenAI; „Claude“ und „Codex“ sind Marken ihrer Inhaber.
- Fragt einmal täglich `api.github.com` nach einer neuen Version (in den Einstellungen abschaltbar).
- Führt alle 60 s ein mitgeliefertes Python-Skript aus; Daten und Log liegen in `~/.cache/limit-rings`
  (nach dem Deinstallieren entfernen: `rm -r ~/.cache/limit-rings`).

Mehrere Konten pro Anbieter sind möglich: weitere `CLAUDE_CONFIG_DIR`-/`CODEX_HOME`-Verzeichnisse unter „Weitere Konten“ in den Einstellungen eintragen; jedes bekommt einen eigenen Ring und eine eigene Karte, gelesen werden nur die eingetragenen Verzeichnisse.

Optionaler Statuszeilen-Fallback für Claude-Limits: siehe README auf GitHub (manuell, braucht `jq`).
Fehler und Ideen: https://github.com/Flexomatic81/limit-rings/issues

## Images

The store takes at most five images. Upload them in this order; the files are here in `docs/store/`,
1920 × 1080 each, in the stock Breeze Dark colour scheme.

1. `store-1-overview.png`: name, the three main points, and the open popup with the Claude and Codex cards
   above the rings in a panel
2. `store-2-popup.png`: the Claude card, its parts labelled
3. `store-3-panel-views.png`: the panel views side by side (rings, number, what is left, several accounts,
   vertical panel) and the tooltip
4. `store-4-notifications.png`: the limits with the forecast and two notifications
5. `store-5-login.png`: what happens with the login, and the settings page with "Live limits via login"

### How the images are made

The widget in the images is real: `python3 tools/store_shots.py` renders its views from invented data
(`tools/store_shots/fake.js`) at three times the size into `shots/`: `popup-both.png`, `popup-claude.png`,
`panel-rings.png`, `panel-number.png`, `panel-remaining.png`, `panel-accounts.png`, `panel-vertical.png`,
`tooltip.png` and `settings.png`.

Background, frames, labels, the notifications and the settings dialog around the page are drawn in VectorCraft;
the document is `limit-rings-store.vectorcraft`, one artboard per image, with the views embedded. The
notifications show the texts the widget sends, with the widget's icon (`utilities-system-monitor`); the sidebar of
the settings dialog shows the Breeze icons of its pages. After new shots, replace the embedded images (Links →
Relink, keeping their bounds, then Embed) and export each artboard as PNG at scale 1. Strip the text chunks
(title and creation time) before committing.
