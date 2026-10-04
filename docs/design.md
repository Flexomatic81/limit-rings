# Agent-Stats Plasmoid — Design

Stand: 2026-10-03 · Status: zur Prüfung

## Ziel

Ein KDE-Plasma-6-Widget (Plasmoid), das Nutzungslimits und Token-Statistiken von **Claude Code**
und **Codex** nebeneinander zeigt — damit man ein Limit kommen sieht, bevor man hineinläuft.

**Erfolgskriterien**

- Die Leiste zeigt jederzeit den Auslastungsgrad des am stärksten belegten Limits je Anbieter.
- Die volle Ansicht zeigt je Anbieter: alle Limits mit Countdown bis zum Reset, Tokens
  heute/Woche/Monat und einen 30-Tage-Verlauf.
- Die Token-Zahlen von heute stimmen mit einer unabhängigen Zählung über die Rohlogs überein.
- Fällt eine Datenquelle aus, bleiben die übrigen Anzeigen korrekt; das Alter jedes Werts ist
  sichtbar.

**Ausdrücklich nicht in Version 1** (später möglich): Kostenschätzung in $, Aufschlüsselung nach
Projekt/Modell, aktive Sitzungen.

## Umgebung

- KDE Plasma 6, `kpackagetool6`, Python ≥ 3.10.
- Claude-Code-Transkripte: `~/.claude/projects/**/*.jsonl` (inkl. `*/subagents/*.jsonl`), oft
  mehrere hundert MB.
- Codex-Sitzungslogs: `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`.
- Claude-Code-Statuszeile: ein eigenes Statuszeilen-Skript (bei `install.sh` unter
  `~/.claude/statusline-command.sh` erwartet) erhält über stdin u. a.
  `.rate_limits.five_hour.{used_percentage,resets_at}`.

## Architektur

```
~/.claude/projects/**/*.jsonl ─┐
~/.codex/sessions/**/*.jsonl  ─┼─► agent-stats-collect (Python, systemd-User-Timer, 60 s)
Anthropic OAuth-Usage-API     ─┤        │  inkrementell: Byte-Offset pro Datei in state.json
Statuszeilen-Cache (Rückfall) ─┘        ▼
                              ~/.cache/agent-stats/stats.json  (atomar: tmp + rename)
                                        │
                                        ▼
                         Plasmoid (QML) liest alle 30 s → Leiste + Desktop/Popup
```

Entscheidungen:

- **Collector getrennt vom Widget** (systemd-User-Timer statt Ausführung aus dem Plasmoid):
  unabhängig testbar, kein doppeltes Rechnen bei zwei Widget-Instanzen, Fehler im Collector
  betreffen `plasmashell` nicht.
- **Claude-Limits aus zwei Quellen:** OAuth-Usage-Endpunkt als Hauptquelle (deckt jede Nutzung
  ab, auch claude.ai/Desktop-App), Statuszeilen-Cache als Rückfall.
- **Nur Python-Standardbibliothek** — kein venv, keine Abhängigkeiten.

## Komponenten

| Einheit | Aufgabe | Abhängigkeiten |
|---|---|---|
| `sources/claude_logs.py` | Liest neue Zeilen der Claude-Transkripte; liefert Token-Ereignisse (Zeitstempel, Input, Output, Cache-Lesen, Cache-Schreiben). Verbucht je `(message.id, requestId)` nur Zuwächse. | `state` |
| `sources/codex_logs.py` | Liest `event_msg`/`token_count`-Ereignisse; liefert Token-Ereignisse aus `last_token_usage` und das jüngste `rate_limits`-Objekt samt Zeitstempel. | `state` |
| `sources/codex_limits.py` | Fragt den Codex-Nutzungsendpunkt (`chatgpt.com/backend-api/wham/usage`) mit der ChatGPT-Anmeldung aus `~/.codex/auth.json` ab (ohne Weiterleitungen, höchstens alle 5 min). Nötig, weil Codex über das Claude-Code-Plugin flüchtige Sitzungen ohne Sitzungslog nutzt. Bei Fehler bleibt der letzte Stand (auch aus dem Sitzungslog). | HTTP (urllib), Dateisystem |
| `sources/claude_limits.py` | Fragt den OAuth-Usage-Endpunkt ab (ohne Weiterleitungen); bei Fehler Statuszeilen-Cache. Liefert Limits + Quelle + Zeitpunkt. | HTTP (urllib), Dateisystem |
| `aggregate.py` | Reine Funktionen: Tages-Buckets → Summen heute/Woche/Monat, lückenlose 30-Tage-Reihe. | keine |
| `state.py` | Offset und Inode je Datei, gesehene Nachrichten-IDs, Tages-Buckets je Anbieter, Zeitpunkt der letzten OAuth-Abfrage. | Dateisystem |
| `collect.py` | Orchestriert einen Durchlauf, schreibt `stats.json` atomar. CLI-Einstieg `agent-stats-collect`. | alle obigen |
| Plasmoid `io.github.flexomatic81.agentstats` | Nur Darstellung, keine Berechnung. | `stats.json` |
| Statuszeilen-Ergänzung | Eine Zeile in `statusline-command.sh`: schreibt `.rate_limits` nach `~/.cache/agent-stats/claude-statusline-limits.json`. | — |

### Token-Ereignisse

**Claude:** Jede Zeile mit `message.usage` ist ein Kandidat. Eine API-Antwort erscheint mehrfach
(je Inhaltsblock eine Zeile), und die Werte sind dabei Streaming-Zwischenstände: `output_tokens`
wächst von Zeile zu Zeile (bei rund 15 % der Antworten; „erstes Vorkommen zählt“ unterschätzt die
Output-Tokens um mehr als das Hundertfache). Je
`(message.id, requestId)` wird deshalb der bereits verbuchte Stand gemerkt; jede weitere Zeile
verbucht feldweise nur den Zuwachs `max(0, neu − gemerkt)`, am Datum der ersten Zeile — auch wenn
die spätere Zeile erst in einem späteren Collector-Lauf gelesen wird. Felder: `input_tokens`, `output_tokens`,
`cache_read_input_tokens`, `cache_creation_input_tokens`. Zeitstempel aus `timestamp` (UTC).

**Codex:** `token_count`-Ereignisse mit `info.last_token_usage` liefern den Verbrauch je Aufruf
(`input_tokens` abzüglich `cached_input_tokens` → Input, `cached_input_tokens` → Cache-Lesen,
`output_tokens` → Output, `cache_write_input_tokens` → Cache-Schreiben). Ereignisse ohne `info`
tragen nur Limits und zählen nicht als Verbrauch. Zur Absicherung gegen Doppelzählung wird je
**Sitzungs-ID** (`session_meta.payload.id`, ersatzweise Dateipfad) die höchste
`info.total_token_usage.total_tokens` mitgeführt; ein Ereignis, dessen Summe diese nicht
übersteigt, wird verworfen. Die Sitzungsstände überdauern das Verschwinden der Datei (400 Tage),
sodass verschobene oder kopierte Sitzungsdateien nicht doppelt zählen.

### Zustand und Inkrementalität

- `~/.cache/agent-stats/state.json` hält je Datei `{offset, inode}`, die Tages-Buckets je
  Anbieter (lokales Datum → Token-Summen), die verbuchten Usage-Stände je Claude-Antwort der
  letzten 35 Tage (ältere werden verworfen; Dateien dieses Alters werden nicht mehr beschrieben)
  und die Codex-Sitzungsstände.
- Gelesen wird nur bis zum letzten `\n`; eine unvollständige letzte Zeile wartet auf den
  nächsten Durchlauf.
- Datei kleiner als Offset oder andere Inode → von vorn lesen; Deduplizierung verhindert
  Doppelzählung.
- Tages-Buckets älter als 400 Tage werden verworfen (Monatssumme und 30-Tage-Reihe brauchen weniger).
- `state.json` fehlt oder ist unlesbar → vollständiges Neueinlesen (einmalig, Sekundenbereich).

### Zeitrechnung

Lokale Zeitzone des Systems (Europe/Berlin). „Heute“ = lokales Kalenderdatum, „Woche“ = ab
Montag 00:00 lokal, „Monat“ = ab dem 1. des Monats 00:00 lokal. Zeitstempel werden vor dem
Einsortieren in lokale Zeit umgerechnet; Sommer-/Winterzeitwechsel werden dadurch korrekt
behandelt.

## Schnittstelle `stats.json`

Einzige Schnittstelle zwischen Collector und Widget. Modus `0600`, atomar geschrieben.

```json
{
  "schema": 1,
  "generated_at": "2026-10-03T19:42:00+02:00",
  "providers": {
    "claude": {
      "limits": [
        {"id": "five_hour", "label": "5 h", "used_percent": 42.0,
         "resets_at": 1791300000, "window_minutes": 300},
        {"id": "seven_day", "label": "Woche", "used_percent": 18.0,
         "resets_at": 1791800000, "window_minutes": 10080}
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
      "error": null,
      "auth": {"status": "ok", "expires_at": "2026-10-04T19:29:15+02:00"}
    },
    "codex": {
      "limits": [
        {"id": "primary", "label": "Woche", "used_percent": 8.0,
         "resets_at": 1791280728, "window_minutes": 10080}
      ],
      "limits_source": "session_log",
      "limits_updated_at": "2026-09-29T21:30:00+02:00",
      "plan": "plus",
      "tokens": {"today": {}, "week": {}, "month": {}},
      "daily": [],
      "error": null
    }
  }
}
```

Regeln:

- `limits` ist eine Liste beliebiger Länge (Codex hat je nach Plan nur `primary`, Claude zwei
  Fenster). Leere Liste = keine Limit-Daten vorhanden.
- `label` wird aus `window_minutes` abgeleitet: 300 → „5 h“, 10080 → „Woche“, sonst „N h“/„N d“.
- Modellbezogene Wochenlimits aus der `limits`-Liste der OAuth-Antwort (`kind: "weekly_scoped"`)
  erscheinen als eigener Eintrag „Woche <Modell>“ (id `weekly_scoped:<modell>`); fehlerhafte
  Einträge entfallen, schon vorhandene Bezeichnungen werden nicht doppelt aufgeführt.
- `limits_source`: `"oauth"` | `"statusline"` | `"session_log"` | `null`.
  Codex: `"oauth"` (Nutzungsendpunkt) oder `"session_log"`; Codex-Token-Statistiken zählen nur
  Terminal-Sitzungen, weil das Plugin keine Token-Zahlen speichert.
- `total` = `input + output + cache_read + cache_write`.
- `daily` hat genau 30 Einträge, ältester zuerst, fehlende Tage mit `total: 0`.
- Limits mit 5-h-Fenster (`window_minutes` 300) und Wochenfenster (10080) können ein Feld
  `forecast` tragen: `{"status": "full", "eta": <Epoch>}` (bei aktuellem Tempo vor dem Reset voll)
  oder `{"status": "enough"}`; fehlt es, gibt es (noch) keine Prognose. Grundlage ist der Verlauf in
  `state.json` (`history`):

  | | 5 h | Woche |
  |---|---|---|
  | Tempo aus dem Anstieg der letzten | 30 min | 24 h |
  | Prognose ab Messabstand | 10 min | 2 h |
  | jüngster Punkt höchstens | 30 min alt | 6 h alt |
  | Punkte aufbewahrt / Mindestabstand | 60 min / – | 24 h / 10 min |

  Karte: Zeile unter dem Balken („Bei aktuellem Tempo voll in ~1 h 20 min (13:40)“, ab einem Tag
  Abstand mit Wochentag „(Sa 14:00)“, bzw. „Reicht bei aktuellem Tempo bis zum Reset“); Tooltip: Kurzform.
- `breakdown` gibt es nur bei Claude: Token-Summen seit Beginn des Claude-Wochenfensters (Reset des
  Wochenlimits − 7 Tage; ohne bekanntes Wochenlimit die letzten 7 Tage, `basis: "7d"`), je für
  `projects` und `models` die vier größten Einträge plus „Andere“. Projekt = Git-Repository des
  Arbeitsverzeichnisses (Worktree → Haupt-Repository), sonst Verzeichnisname; Modell als lesbarer Name
  („Opus 5.5“). Gezählt wird stündlich (`hourly` in `state.json`, 8 Tage). Die Werte stammen nur aus den
  Transkripten **dieses** Rechners und sind Token-Anteile, nicht der (nicht offengelegte) Limit-Verbrauch
  je Modell. Bestehende Zustände ohne `hourly` laden die stündliche Zählung einmal nach.
- `auth` gibt es nur bei Claude: Zustand des Anmelde-Tokens in `~/.claude/.credentials.json`
  (`"ok"` | `"expired"` | `"missing"`) und Ablaufzeit. Den Token schreibt und erneuert nur Claude Code
  im Terminal (ca. 8 h gültig). Ist der Zustand nicht `ok`, zeigen Karte und Tooltip
  „Anmeldung abgelaufen – claude im Terminal starten“ bzw. „Keine Anmeldung gefunden – …“.
- `error` ist `null` oder eine kurze, nutzerlesbare Meldung; die übrigen Felder tragen dann die
  letzten guten Werte.
- Das Widget ignoriert `stats.json` mit unbekannter `schema`-Version und zeigt einen Hinweis.

## Darstellung

### Leiste (kompakt)

- Je aktiviertem Anbieter ein Ring mit Kürzel „C“ / „X“: **außen** das höchste Wochenlimit,
  **innen** (dünner) das 5-h-Limit, jeder Ring mit eigener Schwellenfarbe; ohne 5-h-Fenster nur der
  äußere Ring, ohne beide Fensterarten der höchste Wert. Darstellung „Zahl“: der höchste Wert.
- Farbe nach Schwellen (Standard): unter 70 % neutral, ab 70 % Warnung, ab 90 % kritisch —
  Plasma-Theme-Farben (`Kirigami.Theme.neutralTextColor` / `negativeTextColor`).
- Tooltip: alle Limits mit Countdown, z. B. „5 h: 42 % · Reset in 2 h 13 min“.
- Klick öffnet die volle Ansicht als Popup.

### Desktop / Popup (voll)

```
┌─ Claude ── pro ─────────────┐ ┌─ Codex ── plus ─────────────┐
│ 5 h   ██████░░░░ 42%  2h13m │ │ Woche █░░░░░░░░░  8%  6d 4h │
│ Woche ██░░░░░░░░ 18%  4d 2h │ │                             │
│ Heute   1,2 M  Woche 8,4 M  │ │ Heute  15 k   Woche 210 k   │
│ Monat  31,0 M               │ │ Monat 890 k                 │
│ ▁▂▅▃▁▇█▄▂▁▃▅ … (30 Tage)    │ │ ▁▁▂▁▁▃▁▁▁▂▁▁ … (30 Tage)    │
│ Stand vor 30 s · OAuth      │ │ Stand vor 3 d · Sitzungslog │
└─────────────────────────────┘ └─────────────────────────────┘
```

- Zwei Karten nebeneinander, sobald zwei Karten in ihrer Mindestbreite (meist die Zeile
  Heute/Woche/Monat) samt Abstand hineinpassen; sonst untereinander.
- Limit-Daten älter als 6 h: Balken blass, Fußzeile in Warnfarbe mit „· veraltet“, Ring in der
  Leiste blass, Tooltip mit „(veraltet)“.
- Token-Zahlen kompakt (k/M, deutsches Dezimalkomma); Tooltip mit Aufteilung
  Input/Output/Cache-Lesen/Cache-Schreiben.
- Balkendiagramm: Gesamttokens pro Tag, Tooltip mit Datum und Wert.
- Fußzeile: Alter der Limit-Daten und Quelle.
- `resets_at` in der Vergangenheit → Limit als „zurückgesetzt · 0 %“ anzeigen, bis neue Daten
  eintreffen.
- `error` gesetzt → dezenter Hinweis in der Karte, übrige Werte bleiben sichtbar.
- `stats.json` fehlt oder älter als 5 Minuten → Hinweis „Collector läuft nicht“ mit dem Befehl
  `systemctl --user status agent-stats.timer`.

### Einstellungen

- Schwellen Warnung/kritisch (Standard 70/90).
- Angezeigte Anbieter (Claude, Codex; beide standardmäßig an).
- Leistendarstellung: Ring oder Zahl.

## Benachrichtigungen

Der Collector (nicht das Widget) zeigt per `notify-send` eine Desktop-Benachrichtigung, sobald ein
Limit von Claude oder Codex **80 %** bzw. **95 %** erreicht — je Limit und Stufe einmal pro Zeitfenster.
Ein neues Fenster (anderer `resets_at`) oder ein Rückfall unter 80 % macht die Benachrichtigung wieder
scharf; ein Fenster mit vergangenem Reset zählt als 0 %. Springt ein Limit direkt über 95 %, kommt nur
die 95-%-Meldung; sie ist als dringend markiert. Zusätzlich gibt es beim **5-h-Limit** eine Frühwarnung, wenn die Prognose es in höchstens
30 Minuten voll sieht und 80 % noch nicht erreicht sind („Claude: 5-h-Limit in ~25 min voll“,
„Jetzt 62 % · Reset in …“) — ebenfalls einmal pro Fenster, normale Dringlichkeit; Wochenlimits
bekommen keine Frühwarnung. Bereits Verschicktes steht in `state.json` unter
`notified`. Die Schwellen sind fest und unabhängig von den Farbschwellen des Widgets. Fehlt
`notify-send` oder schlägt der Aufruf fehl, wird das geloggt; der Durchlauf läuft normal weiter.

## Fehlerbehandlung

- Ungültige JSON-Zeilen werden übersprungen und gezählt (Log auf Debug-Niveau), kein Fehler.
- Jeder Anbieter wird in einem eigenen `try` verarbeitet; ein Fehler setzt nur dessen `error`.
- **OAuth-Endpunkt:** höchstens alle 5 Minuten abgefragt (Zeitpunkt in `state.json`), Timeout
  10 s. Bei 401/403, Weiterleitung, Timeout, Netzfehler oder unerwarteter Antwortform (auch:
  kein einziges verwertbares Fenster) → Statuszeilen-Cache bzw. letzte gute Werte, je nachdem,
  was jünger ist. Solange der letzte OAuth-Versuch erfolgreich war, bleiben dessen Daten
  während der 5-Minuten-Drosselung stehen — eine neuere Statuszeile verdrängt sie nicht. Unerwartete
  Antwortformen werden mit Feldnamen (nie mit Werten aus der Anfrage) ins Journal geloggt.
- Collector-Ausgaben gehen ins Journal: `journalctl --user -u agent-stats`.

## Sicherheit

- `~/.claude/.credentials.json` wird nur gelesen. Der Collector erneuert **keine** Tokens und
  schreibt nie in diese Datei; ein abgelaufener Token führt zum Rückfall, bis Claude Code ihn
  selbst erneuert.
- Der Token wird ausschließlich an `api.anthropic.com` gesendet — nie in `stats.json`,
  `state.json`, Log oder Fehlermeldungen. Weiterleitungen werden abgelehnt, weil `urllib` den
  `Authorization`-Header sonst an das Weiterleitungsziel mitschickt.
- `stats.json`, `state.json` und der Statuszeilen-Cache werden mit Modus `0600` angelegt,
  `~/.cache/agent-stats/` mit `0700`.

## Installation

`install.sh` (idempotent) und `uninstall.sh`:

1. Collector nach `~/.local/share/agent-stats/`, Startskript `~/.local/bin/agent-stats-collect`.
2. `systemd/agent-stats.service` (oneshot) und `agent-stats.timer` (`OnBootSec=30s`,
   `OnUnitActiveSec=60s`) nach `~/.config/systemd/user/`, `daemon-reload`, Timer aktivieren,
   ersten Durchlauf sofort starten.
3. Plasmoid per `kpackagetool6 -t Plasma/Applet --install` bzw. `--upgrade`.
4. Statuszeile: Das Skript zeigt die einzufügende Zeile an und fügt sie nur nach ausdrücklicher
  Rückfrage ein — vorher Sicherungskopie `statusline-command.sh.bak-agent-stats`. Die Zeile
  schreibt je Aufruf in eine eigene `mktemp`-Datei und benennt danach um, damit parallele
  Claude-Sitzungen keine halben Dateien erzeugen.

`uninstall.sh` macht 1–3 rückgängig und weist auf die Statuszeilen-Zeile hin, entfernt
`~/.cache/agent-stats/` nur nach Rückfrage.

## Tests

**Collector (pytest)** mit anonymisierten JSONL-Fixtures im Format der echten Logs:

- Deduplizierung der Claude-Mehrfachzeilen.
- Unvollständige letzte Zeile wird nicht gelesen, im nächsten Durchlauf schon.
- Gekürzte bzw. ersetzte Datei → Neueinlesen ohne Doppelzählung.
- Grenzen Tag/Woche/Monat, inkl. Zeitumstellung (2026-10-25).
- Codex-Limits mit `secondary: null`; Codex-Ereignisse ohne `info`.
- OAuth-Erfolg, 401, Timeout und unerwartete Antwort (HTTP gemockt) → richtige Quelle.
- Fehler eines Anbieters lässt den anderen unberührt.
- `stats.json` erfüllt die Regeln aus dem Abschnitt „Schnittstelle“ (30 Tage, `total`-Summe).

**Widget:** Formatierungsfunktionen (k/M, Countdown, Schwellenfarbe, „zurückgesetzt“) als reine
Funktionen in `contents/code/format.js`, getestet mit `qmltestrunner`. Darstellung manuell mit
`plasmoidviewer` als Leiste und als Desktop-Widget.

**Abnahme:** Durchlauf gegen die echten Logs; Tokens von heute für Claude und Codex mit einer
unabhängigen `jq`-Zählung abgleichen.

## Projektstruktur

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

## Offene Risiken

- **OAuth-Usage-Endpunkt ist undokumentiert.** Antwortform und Verfügbarkeit können sich ändern.
  Gegenmaßnahme: gekapselt in `claude_limits.py`, Rückfall auf Statuszeile, Log bei
  unerwarteter Form. Die genaue Antwortform wird zu Beginn der Umsetzung mit einer echten
  Abfrage festgestellt und als Fixture festgehalten.
- **Statuszeilen-Rückfall greift nur bei CLI-Nutzung.** Ob die Desktop-App die Statuszeile
  aufruft, ist ungeklärt; im Zweifel liefert der Rückfall seltener Daten.
- **Codex-Limits veralten**, wenn Codex länger nicht genutzt wird — durch Altersanzeige sichtbar.
