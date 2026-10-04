#!/usr/bin/env bash
# Entfernt Timer, Collector und Plasmoid. --purge löscht zusätzlich ~/.cache/agent-stats ohne Rückfrage.
set -euo pipefail

units="$HOME/.config/systemd/user"
cache="$HOME/.cache/agent-stats"

# Erst Timer und einen evtl. laufenden Durchlauf anhalten (stop wartet), dann aufräumen –
# sonst schreibt ein laufender Collector nach dem Löschen den Cache neu.
systemctl --user stop agent-stats.timer agent-stats.service 2>/dev/null || true
systemctl --user disable agent-stats.timer 2>/dev/null || true
rm -f "$units/agent-stats.timer" "$units/agent-stats.service"
systemctl --user daemon-reload
rm -rf "$HOME/.local/share/agent-stats"
rm -f "$HOME/.local/bin/agent-stats-collect"
kpackagetool6 -t Plasma/Applet --remove io.github.flexomatic81.agentstats 2>/dev/null || true

if [[ -d "$cache" ]]; then
    answer=n
    if [[ "${1:-}" == "--purge" ]]; then
        answer=j
    elif [[ -t 0 ]]; then
        read -r -p "$cache löschen? [j/N] " answer || answer=n
    fi
    [[ $answer == [jJyY] ]] && rm -rf "$cache" && echo "Cache gelöscht."
fi

if grep -qF "# agent-stats:" "$HOME/.claude/statusline-command.sh" 2>/dev/null; then
    echo "Hinweis: ~/.claude/statusline-command.sh enthält noch die agent-stats-Zeilen (Marker '# agent-stats:')."
    echo "Sie schaden nicht, können aber von Hand entfernt werden."
fi
echo "Deinstalliert."
