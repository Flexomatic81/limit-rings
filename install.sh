#!/usr/bin/env bash
# Installs the collector, systemd timer and plasmoid. Safe to run repeatedly.
# --statusline: insert the status line hook without asking.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
share="$HOME/.local/share/agent-stats"
bin="$HOME/.local/bin/agent-stats-collect"
units="$HOME/.config/systemd/user"
statusline="$HOME/.claude/statusline-command.sh"
marker="# agent-stats: record limits for the plasmoid"
# Marker written by older (German) versions; still recognised so existing installs are not patched twice.
old_marker="# agent-stats: Limits für das Plasmoid mitschneiden"
snippet="$(grep -v '^#' "$here/statusline-snippet.sh")"

auto_statusline=no
[[ "${1:-}" == "--statusline" ]] && auto_statusline=yes

echo "→ Collector to $share"
mkdir -p "$share" "$(dirname "$bin")"
rm -rf "$share/agent_stats"
cp -r "$here/collector/agent_stats" "$share/"
find "$share" -name __pycache__ -prune -exec rm -rf {} +
cat > "$bin" <<'EOF'
#!/bin/sh
PYTHONPATH="$HOME/.local/share/agent-stats${PYTHONPATH:+:$PYTHONPATH}" exec /usr/bin/python3 -m agent_stats.collect "$@"
EOF
chmod 755 "$bin"

echo "→ systemd timer"
mkdir -p "$units"
cp "$here/systemd/agent-stats.service" "$here/systemd/agent-stats.timer" "$units/"
systemctl --user daemon-reload
systemctl --user enable --now agent-stats.timer
systemctl --user start agent-stats.service || echo "  Warning: first run failed – journalctl --user -u agent-stats.service"

echo "→ Plasmoid"
if kpackagetool6 -t Plasma/Applet --show io.github.flexomatic81.agentstats >/dev/null 2>&1; then
    kpackagetool6 -t Plasma/Applet --upgrade "$here/plasmoid/io.github.flexomatic81.agentstats"
else
    kpackagetool6 -t Plasma/Applet --install "$here/plasmoid/io.github.flexomatic81.agentstats"
fi

echo "→ Status line (fallback for Claude limits)"
if [[ ! -f "$statusline" ]]; then
    echo "  $statusline not found – skipped."
elif grep -qF -e "$marker" -e "$old_marker" "$statusline"; then
    echo "  already present."
elif ! grep -q '^input=\$(cat)' "$statusline"; then
    echo "  No line 'input=\$(cat)' found. Please insert manually right after it:"
    printf '    %s\n    %s\n' "$marker" "$snippet"
else
    answer=n
    if [[ $auto_statusline == yes ]]; then
        answer=y
    elif [[ -t 0 ]]; then
        echo "  To be inserted after 'input=\$(cat)':"
        printf '    %s\n    %s\n' "$marker" "$snippet"
        read -r -p "  Insert now? [y/N] " answer || answer=n
    else
        echo "  Not interactive – not inserted. Re-run with --statusline to insert it."
    fi
    if [[ $answer == [yY] ]]; then
        cp -p "$statusline" "$statusline.bak-agent-stats"
        MARKER="$marker" SNIPPET="$snippet" awk '
            { print }
            !done && /^input=\$\(cat\)/ { print ENVIRON["MARKER"]; print ENVIRON["SNIPPET"]; done = 1 }
        ' "$statusline.bak-agent-stats" > "$statusline"
        echo "  inserted (backup: $statusline.bak-agent-stats)."
    fi
fi

echo
echo "Done. Drag the \"Agent Stats\" widget from \"Add Widgets\" onto a panel or the desktop."
echo "After an upgrade you may need: systemctl --user restart plasma-plasmashell"
