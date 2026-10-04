# Agent Stats

KDE-Plasma-6-Widget für Nutzungslimits und Token-Statistiken von **Claude Code** und **Codex**.

- Leiste: ein Doppelring je Anbieter — außen das Wochenlimit, innen das 5-h-Limit; Tooltip mit allen
  Limits und Countdown.
- Desktop/Popup: Limits mit Reset-Countdown, Tokens heute/Woche/Monat, 30-Tage-Verlauf.
- Prognose, wann ein Limit bei aktuellem Tempo voll ist (5 h: letzte 30 min, Woche: letzte 24 h).
- Desktop-Benachrichtigung, sobald ein Limit 80 % bzw. 95 % erreicht, und Frühwarnung, wenn das
  5-h-Limit laut Prognose in höchstens 30 Minuten voll ist (jeweils einmal pro Zeitfenster).
- Hinweis in Karte und Tooltip, wenn die Claude-Anmeldung abgelaufen ist.
- Aufschlüsselung der Claude-Tokens seit dem Wochen-Reset nach Projekt (Git-Repository) und Modell —
  nur für die Transkripte des jeweiligen Rechners, als Anteil an Tokens (nicht am Limit).

## Wichtiger Hinweis: inoffizielle Schnittstellen

Die Nutzungslimits fragt Agent Stats über **nicht dokumentierte Endpunkte** von Anthropic
(`api.anthropic.com/api/oauth/usage`) und OpenAI (`chatgpt.com/backend-api/wham/usage`) ab. Dafür
liest es die Anmelde-Tokens, die Claude Code (`~/.claude/.credentials.json`) und Codex
(`~/.codex/auth.json`) lokal ablegen.

- Die Tokens werden nur gelesen, nie erneuert, gespeichert oder geloggt, und nur an den jeweiligen
  Anbieter gesendet; Weiterleitungen werden abgelehnt. Abgefragt wird höchstens alle 5 Minuten.
- Die Endpunkte können sich jederzeit ändern oder wegfallen; dann fällt Agent Stats auf lokale Daten
  (Statuszeile bzw. Sitzungslogs) zurück.
- Ob diese Nutzung mit den Nutzungsbedingungen von Anthropic bzw. OpenAI vereinbar ist, prüfe bitte
  selbst. Das Projekt steht in keiner Verbindung zu Anthropic oder OpenAI; „Claude“ und „Codex“ sind
  Marken der jeweiligen Unternehmen.

## Aufbau

Ein Python-Collector (`collector/`, nur Standardbibliothek) läuft als systemd-User-Timer alle 60 s,
liest `~/.claude/projects/**/*.jsonl` und `~/.codex/sessions/**/*.jsonl` inkrementell und schreibt
`~/.cache/agent-stats/stats.json`. Das Plasmoid (`plasmoid/io.github.flexomatic81.agentstats`) liest nur diese Datei.

Claude-Limits kommen vom (undokumentierten) OAuth-Usage-Endpunkt; der Token aus
`~/.claude/.credentials.json` wird nur gelesen und nur an `api.anthropic.com` gesendet. Fällt der
Endpunkt aus, dient ein Mitschnitt der Claude-Code-Statuszeile als Rückfall.

Codex-Limits kommen ebenso direkt vom Codex-Dienst (ChatGPT-Anmeldung aus `~/.codex/auth.json`,
Token nur gelesen und nur an `chatgpt.com` gesendet); Rückfall sind die Sitzungslogs. Das ist nötig,
weil Codex als Claude-Code-Plugin keine Sitzungslogs schreibt. Die Codex-Token-Statistik zählt
deshalb nur Codex-Sitzungen im Terminal.

## Installation

Voraussetzungen: KDE Plasma 6 (`kpackagetool6`), Python ≥ 3.10 unter `/usr/bin/python3`
(keine Zusatzpakete), systemd-User-Session; `jq` nur für den Statuszeilen-Rückfall.

```bash
./install.sh            # fragt vor Änderung der Statuszeile nach
./install.sh --statusline   # fügt die Statuszeilen-Zeile ohne Rückfrage ein
```

Danach „Agent Stats“ über „Widgets hinzufügen“ in Leiste und/oder Desktop ziehen.

Der Statuszeilen-Rückfall setzt ein eigenes Claude-Code-Statuszeilen-Skript unter
`~/.claude/statusline-command.sh` mit einer Zeile `input=$(cat)` voraus; `install.sh` fügt die
nötige Zeile (`statusline-snippet.sh`) dort ein. Ohne dieses Skript wird der Schritt übersprungen.

### Herunterladen und installieren

```bash
git clone https://github.com/Flexomatic81/agent-stats.git
cd agent-stats
./install.sh
```

Dann das Widget wie oben platzieren und prüfen:

```bash
systemctl --user list-timers agent-stats.timer   # nächster Lauf ≤ 60 s
jq '.providers | map_values({limits_source, error})' ~/.cache/agent-stats/stats.json
```

- Token-Statistiken zählen nur die Logs **dieses** Rechners; die Limits gehören zum Konto und
  sind auf allen Rechnern gleich. Nutzt man Agent Stats auf mehreren Rechnern, einfach auf jedem
  installieren.
- Liegt in `~/.claude/.credentials.json` ein gültiger Token, kommen die Claude-Limits per OAuth
  (`limits_source: "oauth"`). Claude Code erneuert den Token nur, wenn es im Terminal läuft (er
  gilt ca. 8 h); die Claude-Desktop-App schreibt keinen Token in diese Datei. Ohne gültigen Token
  liefert die Statuszeile die Limits, solange Claude Code im Terminal läuft.

### Aktualisieren

```bash
git pull
./install.sh
systemctl --user restart plasma-plasmashell   # nur nötig, wenn sich das Widget geändert hat
```

## Deinstallation

```bash
./uninstall.sh          # fragt, ob ~/.cache/agent-stats gelöscht werden soll
./uninstall.sh --purge
```

## Fehlersuche

```bash
systemctl --user status agent-stats.timer
journalctl --user -u agent-stats.service -n 50
jq . ~/.cache/agent-stats/stats.json
```

## Entwicklung

```bash
cd collector && uv run --no-project --with pytest pytest -q
/usr/lib/qt6/bin/qmltestrunner -input plasmoid/tests
plasmawindowed io.github.flexomatic81.agentstats
```

## Lizenz

MIT, siehe [LICENSE](LICENSE).
