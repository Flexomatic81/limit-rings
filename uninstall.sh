#!/usr/bin/env bash
# Removes the timer, collector and plasmoid. --purge also deletes ~/.cache/limit-rings without asking.
set -euo pipefail

units="$HOME/.config/systemd/user"
cache="$HOME/.cache/limit-rings"

# Stop the timer and any running collector pass first (stop waits), then clean up –
# otherwise a running collector would rewrite the cache after it has been deleted.
systemctl --user stop limit-rings.timer limit-rings.service 2>/dev/null || true
systemctl --user disable limit-rings.timer 2>/dev/null || true
rm -f "$units/limit-rings.timer" "$units/limit-rings.service"
systemctl --user daemon-reload
rm -rf "$HOME/.local/share/limit-rings"
rm -f "$HOME/.local/bin/limit-rings-collect"
kpackagetool6 -t Plasma/Applet --remove io.github.flexomatic81.limitrings 2>/dev/null || true
rm -f "$HOME"/.local/share/locale/*/LC_MESSAGES/plasma_applet_io.github.flexomatic81.limitrings.mo

if [[ -d "$cache" ]]; then
    answer=n
    if [[ "${1:-}" == "--purge" ]]; then
        answer=y
    elif [[ -t 0 ]]; then
        read -r -p "Delete $cache? [y/N] " answer || answer=n
    fi
    [[ $answer == [yY] ]] && rm -rf "$cache" && echo "Cache deleted."
fi

if grep -qF "# limit-rings:" "$HOME/.claude/statusline-command.sh" 2>/dev/null; then
    echo "Note: ~/.claude/statusline-command.sh still contains the limit-rings lines (marker '# limit-rings:')."
    echo "They are harmless but can be removed by hand."
fi
echo "Uninstalled."
