#!/usr/bin/env bash
# Removes the timer, collector and plasmoid. --purge also deletes ~/.cache/agent-stats without asking.
set -euo pipefail

units="$HOME/.config/systemd/user"
cache="$HOME/.cache/agent-stats"

# Stop the timer and any running collector pass first (stop waits), then clean up –
# otherwise a running collector would rewrite the cache after it has been deleted.
systemctl --user stop agent-stats.timer agent-stats.service 2>/dev/null || true
systemctl --user disable agent-stats.timer 2>/dev/null || true
rm -f "$units/agent-stats.timer" "$units/agent-stats.service"
systemctl --user daemon-reload
rm -rf "$HOME/.local/share/agent-stats"
rm -f "$HOME/.local/bin/agent-stats-collect"
kpackagetool6 -t Plasma/Applet --remove io.github.flexomatic81.agentstats 2>/dev/null || true
rm -f "$HOME"/.local/share/locale/*/LC_MESSAGES/plasma_applet_io.github.flexomatic81.agentstats.mo

if [[ -d "$cache" ]]; then
    answer=n
    if [[ "${1:-}" == "--purge" ]]; then
        answer=y
    elif [[ -t 0 ]]; then
        read -r -p "Delete $cache? [y/N] " answer || answer=n
    fi
    [[ $answer == [yY] ]] && rm -rf "$cache" && echo "Cache deleted."
fi

if grep -qF "# agent-stats:" "$HOME/.claude/statusline-command.sh" 2>/dev/null; then
    echo "Note: ~/.claude/statusline-command.sh still contains the agent-stats lines (marker '# agent-stats:')."
    echo "They are harmless but can be removed by hand."
fi
echo "Uninstalled."
