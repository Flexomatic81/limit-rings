#!/usr/bin/env bash
# Installiert Collector, systemd-Timer und Plasmoid. Mehrfach ausführbar.
# --statusline: Statuszeilen-Zeile ohne Rückfrage einfügen.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
share="$HOME/.local/share/agent-stats"
bin="$HOME/.local/bin/agent-stats-collect"
units="$HOME/.config/systemd/user"
statusline="$HOME/.claude/statusline-command.sh"
marker="# agent-stats: Limits für das Plasmoid mitschneiden"
snippet="$(grep -v '^#' "$here/statusline-snippet.sh")"

auto_statusline=no
[[ "${1:-}" == "--statusline" ]] && auto_statusline=yes

echo "→ Collector nach $share"
mkdir -p "$share" "$(dirname "$bin")"
rm -rf "$share/agent_stats"
cp -r "$here/collector/agent_stats" "$share/"
find "$share" -name __pycache__ -prune -exec rm -rf {} +
cat > "$bin" <<'EOF'
#!/bin/sh
PYTHONPATH="$HOME/.local/share/agent-stats${PYTHONPATH:+:$PYTHONPATH}" exec /usr/bin/python3 -m agent_stats.collect "$@"
EOF
chmod 755 "$bin"

echo "→ systemd-Timer"
mkdir -p "$units"
cp "$here/systemd/agent-stats.service" "$here/systemd/agent-stats.timer" "$units/"
systemctl --user daemon-reload
systemctl --user enable --now agent-stats.timer
systemctl --user start agent-stats.service || echo "  Warnung: erster Durchlauf fehlgeschlagen – journalctl --user -u agent-stats.service"

echo "→ Plasmoid"
if kpackagetool6 -t Plasma/Applet --show io.github.flexomatic81.agentstats >/dev/null 2>&1; then
    kpackagetool6 -t Plasma/Applet --upgrade "$here/plasmoid/io.github.flexomatic81.agentstats"
else
    kpackagetool6 -t Plasma/Applet --install "$here/plasmoid/io.github.flexomatic81.agentstats"
fi

echo "→ Statuszeile (Rückfall für Claude-Limits)"
if [[ ! -f "$statusline" ]]; then
    echo "  $statusline nicht gefunden – übersprungen."
elif grep -qF "$marker" "$statusline"; then
    echo "  bereits eingetragen."
elif ! grep -q '^input=\$(cat)' "$statusline"; then
    echo "  Keine Zeile 'input=\$(cat)' gefunden. Bitte von Hand direkt danach einfügen:"
    printf '    %s\n    %s\n' "$marker" "$snippet"
else
    answer=n
    if [[ $auto_statusline == yes ]]; then
        answer=j
    elif [[ -t 0 ]]; then
        echo "  Einzufügen nach 'input=\$(cat)':"
        printf '    %s\n    %s\n' "$marker" "$snippet"
        read -r -p "  Jetzt einfügen? [j/N] " answer || answer=n
    else
        echo "  Nicht interaktiv – nicht eingefügt. Mit --statusline erneut ausführen, um sie einzufügen."
    fi
    if [[ $answer == [jJyY] ]]; then
        cp -p "$statusline" "$statusline.bak-agent-stats"
        MARKER="$marker" SNIPPET="$snippet" awk '
            { print }
            !done && /^input=\$\(cat\)/ { print ENVIRON["MARKER"]; print ENVIRON["SNIPPET"]; done = 1 }
        ' "$statusline.bak-agent-stats" > "$statusline"
        echo "  eingefügt (Sicherung: $statusline.bak-agent-stats)."
    fi
fi

echo
echo "Fertig. Widget „Agent Stats“ über „Widgets hinzufügen“ in Leiste oder Desktop ziehen."
echo "Nach einem Upgrade ggf.: systemctl --user restart plasma-plasmashell"
